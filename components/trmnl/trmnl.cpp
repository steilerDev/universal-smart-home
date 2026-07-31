#include "trmnl.h"

#include "esphome/core/application.h"
#include "esphome/core/alloc_helpers.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/network/util.h"

namespace esphome {
namespace trmnl {

static const char *const TAG = "trmnl";

// Persisted across reboots so a provisioned device never re-runs /api/setup.
struct TrmnlPref {
  char token[64];
};

std::string TrmnlDisplay::strip_trailing_slash_(const std::string &s) {
  if (!s.empty() && s.back() == '/')
    return s.substr(0, s.size() - 1);
  return s;
}

void TrmnlDisplay::setup() {
  if (this->mac_.empty())
    this->mac_ = get_mac_address_pretty();
  this->current_refresh_ = this->default_refresh_;

  if (!this->have_config_token_)
    this->load_token_();

  // OnlineImage does the actual download/decode; we react to its outcome.
  // OnlineImage's finished callback carries a `cached` flag (unused here).
  this->image_->add_on_finished_callback([this](bool cached) {
    ESP_LOGI(TAG, "Screen image ready (cached=%s), refreshing panel", YESNO(cached));
    if (this->display_ != nullptr)
      this->display_->update();
    this->image_pending_ = false;
  });
  this->image_->add_on_error_callback([this]() {
    ESP_LOGW(TAG, "Screen image download/decode failed");
    this->post_log_("image download/decode failed", "error");
    this->image_pending_ = false;
  });

  // Give Ethernet/network a moment to come up before the first poll.
  this->schedule_poll_(3);
}

void TrmnlDisplay::dump_config() {
  ESP_LOGCONFIG(TAG, "TRMNL BYOS display client:");
  ESP_LOGCONFIG(TAG, "  Server: %s", this->server_.c_str());
  ESP_LOGCONFIG(TAG, "  Device ID (MAC): %s", this->mac_.c_str());
  ESP_LOGCONFIG(TAG, "  Model: %s  FW: %s", this->model_.c_str(), this->fw_version_.c_str());
  ESP_LOGCONFIG(TAG, "  Panel: %dx%d", this->width_, this->height_);
  ESP_LOGCONFIG(TAG, "  Default refresh: %us", this->default_refresh_);
  ESP_LOGCONFIG(TAG, "  Provisioned: %s", this->token_.empty() ? "NO (will run /api/setup)" : "yes");
}

void TrmnlDisplay::refresh_now() {
  this->cancel_timeout("trmnl_poll");
  this->schedule_poll_(0);
}

void TrmnlDisplay::schedule_poll_(uint32_t seconds) {
  this->set_timeout("trmnl_poll", seconds * 1000, [this]() { this->poll_(); });
}

void TrmnlDisplay::poll_() {
  if (!network::is_connected()) {
    ESP_LOGD(TAG, "Network not connected yet; retrying in 5s");
    this->schedule_poll_(5);
    return;
  }

  if (this->token_.empty() && !this->do_setup_()) {
    ESP_LOGW(TAG, "Provisioning (/api/setup) failed; retrying in 60s");
    this->schedule_poll_(60);
    return;
  }

  if (!this->do_display_()) {
    ESP_LOGW(TAG, "Screen fetch (/api/display) failed; retrying in 60s");
    this->schedule_poll_(60);
    return;
  }

  // current_refresh_ was updated from the server response.
  ESP_LOGD(TAG, "Next poll in %us", this->current_refresh_);
  this->schedule_poll_(this->current_refresh_);
}

bool TrmnlDisplay::do_setup_() {
  ESP_LOGI(TAG, "Provisioning against %s/api/setup", this->server_.c_str());
  std::string body;
  int status = 0;
  if (!this->http_get_json_(this->server_ + "/api/setup", body, status))
    return false;
  if (status != 200) {
    ESP_LOGW(TAG, "/api/setup returned HTTP %d — is device %s registered on the server?", status,
             this->mac_.c_str());
    return false;
  }

  bool ok = false;
  json::parse_json(body, [&](JsonObject root) -> bool {
    // LaraPaper/TRMNL setup returns the persistent device token as "api_key".
    if (!root["api_key"].isNull()) {
      this->token_ = root["api_key"].as<std::string>();
      ok = true;
    } else if (!root["access_token"].isNull()) {
      this->token_ = root["access_token"].as<std::string>();
      ok = true;
    }
    return true;
  });

  if (ok) {
    this->save_token_();
    ESP_LOGI(TAG, "Provisioned successfully; token persisted");
  } else {
    ESP_LOGW(TAG, "/api/setup response contained no api_key");
  }
  return ok;
}

bool TrmnlDisplay::do_display_() {
  std::string body;
  int status = 0;
  if (!this->http_get_json_(this->server_ + "/api/display", body, status))
    return false;
  if (status == 200) {
    // fall through
  } else if (status == 401 || status == 403) {
    ESP_LOGW(TAG, "/api/display unauthorized (HTTP %d); clearing token to re-provision", status);
    this->token_.clear();
    this->save_token_();
    return false;
  } else {
    ESP_LOGW(TAG, "/api/display returned HTTP %d", status);
    return false;
  }

  std::string image_url;
  json::parse_json(body, [&](JsonObject root) -> bool {
    if (!root["image_url"].isNull())
      image_url = root["image_url"].as<std::string>();
    this->current_refresh_ = root["refresh_rate"] | this->default_refresh_;
    if (this->current_refresh_ < 5)  // guard against a hot loop on a bad value
      this->current_refresh_ = this->default_refresh_;

    // Firmware lifecycle is managed by ESPHome/OTA, not the TRMNL server:
    // acknowledge these flags in the log but never act on them.
    if (root["update_firmware"] | false)
      ESP_LOGW(TAG, "Server requested firmware update (ignored; firmware is managed by ESPHome)");
    if (root["reset_firmware"] | false)
      ESP_LOGW(TAG, "Server requested firmware reset (ignored)");
    const char *special = root["special_function"] | "";
    if (special[0] != '\0')
      ESP_LOGI(TAG, "special_function: %s", special);
    return true;
  });

  if (image_url.empty()) {
    ESP_LOGW(TAG, "/api/display response had no image_url");
    return false;
  }

  ESP_LOGI(TAG, "New screen: %s (next refresh in %us)", image_url.c_str(), this->current_refresh_);
  this->image_->set_url(image_url);
  this->image_->update();
  this->image_pending_ = true;
  return true;
}

std::vector<http_request::Header> TrmnlDisplay::device_headers_() {
  std::vector<http_request::Header> headers;
  headers.push_back({"ID", this->mac_});
  if (!this->token_.empty())
    headers.push_back({"Access-Token", this->token_});
  headers.push_back({"FW-Version", this->fw_version_});
  headers.push_back({"Model", this->model_});
  headers.push_back({"Width", to_string(this->width_)});
  headers.push_back({"Height", to_string(this->height_)});
  headers.push_back({"Refresh-Rate", to_string(this->current_refresh_)});
  headers.push_back({"Content-Type", "application/json"});
  return headers;
}

bool TrmnlDisplay::http_get_json_(const std::string &url, std::string &body_out, int &status_out) {
  auto container = this->http_->get(url, this->device_headers_());
  if (container == nullptr) {
    ESP_LOGW(TAG, "HTTP GET %s failed (no connection)", url.c_str());
    return false;
  }

  status_out = container->status_code;
  body_out.clear();

  uint8_t buf[256];
  const uint32_t start = millis();
  while (!container->is_read_complete()) {
    int read = container->read(buf, sizeof(buf));
    if (read > 0)
      body_out.append(reinterpret_cast<char *>(buf), read);
    if (millis() - start > 10000) {
      ESP_LOGW(TAG, "HTTP GET %s timed out while reading body", url.c_str());
      break;
    }
    App.feed_wdt();
  }
  container->end();
  return true;
}

void TrmnlDisplay::post_log_(const std::string &message, const std::string &level) {
  // Best-effort structured log matching the TRMNL /api/log shape.
  std::string payload = "{\"log\":{\"logs_array\":[{\"level\":\"" + level +
                        "\",\"message\":\"" + message + "\",\"device_status_stamp\":{\"fw_version\":\"" +
                        this->fw_version_ + "\"}}]}}";
  auto container = this->http_->post(this->server_ + "/api/log", payload, this->device_headers_());
  if (container != nullptr)
    container->end();
}

void TrmnlDisplay::load_token_() {
  this->pref_ = global_preferences->make_preference<TrmnlPref>(fnv1_hash("trmnl_token"));
  TrmnlPref stored{};
  if (this->pref_.load(&stored)) {
    stored.token[sizeof(stored.token) - 1] = '\0';
    if (stored.token[0] != '\0')
      this->token_ = std::string(stored.token);
  }
}

void TrmnlDisplay::save_token_() {
  TrmnlPref stored{};
  strncpy(stored.token, this->token_.c_str(), sizeof(stored.token) - 1);
  this->pref_.save(&stored);
}

}  // namespace trmnl
}  // namespace esphome
