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
    // 7 Braille fill levels — each is exactly 3 UTF-8 bytes (U+28xx range)
    static const char *const LEVELS[7] = {
        "\xe2\xa3\x80",  // ⣀ inactive / baseline
        "\xe2\xa3\x84",  // ⣄
        "\xe2\xa3\xa4",  // ⣤
        "\xe2\xa3\xa6",  // ⣦ above threshold (active gate, energy unknown)
        "\xe2\xa3\xb6",  // ⣶
        "\xe2\xa3\xb7",  // ⣷
        "\xe2\xa3\xbf",  // ⣿ full
    };

    if (state == 0) {
      this->publish_state("--");
      return;
    }

    // Build 15-gate bar: 15 × 3 UTF-8 bytes + null
    char gates[46];
    char *p = gates;

    if (state == 1) {
      // EXIST: dominant gate scaled by energy; other active gates at ⣦; rest at ⣀
      int dom_gate = (exist_dist > 0) ? (int) ((exist_dist - 1) / 80) : 0;
      if (dom_gate > 14) dom_gate = 14;
      int dom_level = (int) (exist_energy * 6 / 100);
      if (dom_level > 6) dom_level = 6;
      for (int i = 0; i < 15; i++) {
        const char *lev;
        if (i == dom_gate)
          lev = LEVELS[dom_level];
        else if ((exist_index >> i) & 1)
          lev = LEVELS[3];  // ⣦ — crossed threshold, exact energy unknown
        else
          lev = LEVELS[0];  // ⣀ — inactive
        *p++ = lev[0]; *p++ = lev[1]; *p++ = lev[2];
      }
      *p = '\0';
      char buf[96];
      snprintf(buf, sizeof(buf), "E: %s | %dcm e%d", gates, exist_dist, exist_energy);
      this->publish_state(buf);
    } else {
      // MOVE: single gate scaled by energy; all others at ⣀
      int gate = (move_dist > 0) ? (int) ((move_dist - 1) / 80) : 0;
      if (gate > 14) gate = 14;
      int mov_level = (int) (move_energy * 6 / 100);
      if (mov_level > 6) mov_level = 6;
      for (int i = 0; i < 15; i++) {
        const char *lev = (i == gate) ? LEVELS[mov_level] : LEVELS[0];
        *p++ = lev[0]; *p++ = lev[1]; *p++ = lev[2];
      }
      *p = '\0';
      char buf[96];
      snprintf(buf, sizeof(buf), "M: %s | %dcm e%d %+dcm/s", gates, move_dist, move_energy, move_speed);
      this->publish_state(buf);
    }
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
