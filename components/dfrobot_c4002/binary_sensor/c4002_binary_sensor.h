#pragma once

#include "../dfrobot_c4002.h"
#include "esphome/components/binary_sensor/binary_sensor.h"

namespace esphome {
namespace dfrobot_c4002 {

class C4002BinarySensorPresence : public binary_sensor::BinarySensor, public C4002Listener {
 public:
  void on_target_status(uint8_t state) override {
    this->publish_state(state != (uint8_t) NO_BODY);
  }
};

}  // namespace dfrobot_c4002
}  // namespace esphome
