#include "c4002_number.h"
#include "esphome/core/log.h"

namespace esphome {
namespace dfrobot_c4002 {

static const char *const TAG = "dfrobot_c4002.number: ";

void TargetDisappeardDelayTimeNumber::control(float value) {
  if (this->parent_->set_target_disappear_delay((uint16_t) value)) {
    ESP_LOGD(TAG, "Set target disappear delay: %.0f s", value);
    this->publish_state(value);
  } else {
    ESP_LOGW(TAG, "Set target disappear delay failed");
  }
}

void SensitivityThresholdNumber::control(float value) {
  if (this->parent_) {
    uint8_t floor_val = (uint8_t) value;
    ESP_LOGD(TAG, "Set sensitivity floor to %d", floor_val);
    if (this->parent_->set_sensitivity_threshold(floor_val)) {
      ESP_LOGD(TAG, "Sensitivity floor applied");
      this->publish_state(value);
    } else {
      ESP_LOGW(TAG, "Set sensitivity floor failed");
    }
  }
}

}  // namespace dfrobot_c4002
}  // namespace esphome
