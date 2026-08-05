#pragma once

#include "../dfrobot_c4002.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome {
namespace dfrobot_c4002 {

class C4002Sensor : public C4002Listener, public Component {
 public:
  void setup() override {
    if (target_status_)
      this->target_status_->publish_state(0.0f);
  }

  void set_target_status_sensor(sensor::Sensor *sensor) { this->target_status_ = sensor; }

  void on_target_status(uint8_t state) override {
    if (this->target_status_ != nullptr) {
      if (this->target_status_->get_state() != (float) state) {
        this->target_status_->publish_state((float) state);
      }
    }
  }

 protected:
  sensor::Sensor *target_status_{nullptr};
};

}  // namespace dfrobot_c4002
}  // namespace esphome
