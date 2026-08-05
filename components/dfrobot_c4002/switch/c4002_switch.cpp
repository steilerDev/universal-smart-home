#include "c4002_switch.h"
#include "esphome/core/log.h"

namespace esphome {
namespace dfrobot_c4002 {

static const char *const TAG = "dfrobot_c4002.switch";

void C4002SwitchFactoryReset::write_state(bool state) {
  if (!this->parent_)
    return;
  if (state) {
    this->publish_state(true);
    bool ok = this->parent_->factory_reset();
    if (ok) {
      this->set_timeout(1500, [this]() { this->publish_state(false); });
    } else {
      ESP_LOGW(TAG, "Factory reset command failed");
      this->publish_state(false);
    }
  } else {
    this->publish_state(false);
  }
}

void C4002SwitchCalibrate::write_state(bool state) {
  if (!this->parent_)
    return;
  if (state) {
    this->parent_->publish_text("Calibrating \xe2\x80\x94 please leave the room");
    this->parent_->start_env_calibration(5, 30);
    this->publish_state(true);
    // 5s delay + 30s measurement + 5s margin = 40s total
    this->set_timeout(40000, [this]() {
      this->publish_state(false);
      ESP_LOGD(TAG, "Calibration window closed, switch auto-reset to OFF");
    });
  } else {
    this->publish_state(false);
  }
}

}  // namespace dfrobot_c4002
}  // namespace esphome
