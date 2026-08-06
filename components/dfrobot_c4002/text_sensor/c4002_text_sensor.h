#pragma once

#include "esphome/core/component.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "../dfrobot_c4002.h"

namespace esphome {
namespace dfrobot_c4002 {

class C4002GateStatusSensor : public text_sensor::TextSensor, public C4002Listener {
 public:
  void on_detection_detail(uint8_t state, uint32_t exist_index, uint16_t exist_dist,
                            uint8_t exist_energy, uint16_t move_dist, uint8_t move_energy,
                            int16_t move_speed) override {
    char buf[64];
    if (state == 0) {
      snprintf(buf, sizeof(buf), "--");
    } else if (state == 1) {
      // Exist: show bitmask (gate 0=closest on left), then dist+energy
      char gates[16];
      for (int i = 0; i < 15; i++)
        gates[i] = ((exist_index >> i) & 1) ? '#' : '.';
      gates[15] = '\0';
      snprintf(buf, sizeof(buf), "E: %s | %dcm e%d", gates, exist_dist, exist_energy);
    } else {
      // Move: mark the gate corresponding to reported distance
      int gate = (move_dist > 0) ? (int) ((move_dist - 1) / 80) : 0;
      if (gate > 14) gate = 14;
      char gates[16];
      for (int i = 0; i < 15; i++) gates[i] = '.';
      gates[gate] = 'M';
      gates[15] = '\0';
      snprintf(buf, sizeof(buf), "M: %s | %dcm e%d %+dcm/s", gates, move_dist, move_energy, move_speed);
    }
    this->publish_state(buf);
  }
};

class C4002TextSensorHub : public Component {
 public:
  void set_text_sensor(text_sensor::TextSensor *ts) { this->text_sensor_ = ts; }

  void publish(const std::string &msg) {
    if (this->text_sensor_ != nullptr) {
      this->text_sensor_->publish_state(msg);
    }
  }

 private:
  text_sensor::TextSensor *text_sensor_{nullptr};
};

}  // namespace dfrobot_c4002
}  // namespace esphome
