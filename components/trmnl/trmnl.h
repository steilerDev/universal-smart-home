#pragma once

#include <string>
#include <vector>

#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/display/display.h"
#include "esphome/components/http_request/http_request.h"
#include "esphome/components/online_image/online_image.h"

namespace esphome {
namespace trmnl {

/// TRMNL BYOS (Build Your Own Server) e-ink display client.
///
/// Polls a TRMNL-compatible server (e.g. LaraPaper) for the current screen and
/// hands the rendered image URL to an OnlineImage for fetch/decode/render. The
/// server dictates the refresh cadence via the `refresh_rate` response field;
/// scheduling is therefore self-driven (set_timeout re-arm) rather than a fixed
/// PollingComponent interval.
class TrmnlDisplay : public Component {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::LATE; }

  void set_http_request(http_request::HttpRequestComponent *http) { this->http_ = http; }
  void set_online_image(online_image::OnlineImage *image) { this->image_ = image; }
  void set_display(display::Display *disp) { this->display_ = disp; }
  void set_server(const std::string &server) { this->server_ = strip_trailing_slash_(server); }
  void set_mac_address(const std::string &mac) { this->mac_ = mac; }
  void set_access_token(const std::string &token) {
    this->token_ = token;
    this->have_config_token_ = true;
  }
  void set_dimensions(int width, int height) {
    this->width_ = width;
    this->height_ = height;
  }
  void set_model(const std::string &model) { this->model_ = model; }
  void set_fw_version(const std::string &version) { this->fw_version_ = version; }
  void set_default_refresh_rate(uint32_t seconds) { this->default_refresh_ = seconds; }

  /// Force an immediate poll (e.g. from a button or HA service).
  void refresh_now();

 protected:
  void schedule_poll_(uint32_t seconds);
  void poll_();
  bool do_setup_();
  bool do_display_();
  void post_log_(const std::string &message, const std::string &level);

  std::vector<http_request::Header> device_headers_();
  bool http_get_json_(const std::string &url, std::string &body_out, int &status_out);

  void load_token_();
  void save_token_();
  static std::string strip_trailing_slash_(const std::string &s);

  http_request::HttpRequestComponent *http_{nullptr};
  online_image::OnlineImage *image_{nullptr};
  display::Display *display_{nullptr};

  std::string server_;
  std::string mac_;
  std::string token_;
  bool have_config_token_{false};
  std::string model_{"esphome"};
  std::string fw_version_{"1.0.0"};
  int width_{800};
  int height_{480};
  uint32_t default_refresh_{900};
  uint32_t current_refresh_{900};

  ESPPreferenceObject pref_;
  bool image_pending_{false};
};

}  // namespace trmnl
}  // namespace esphome
