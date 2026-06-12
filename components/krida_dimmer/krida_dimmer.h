#pragma once

#include "esphome/core/component.h"
#include "esphome/components/i2c/i2c.h"
#include "esphome/components/light/light_output.h"
#include "esphome/components/light/light_traits.h"
#include <cmath>

namespace esphome {
namespace krida_dimmer {

// KRIDA single-channel trailing-edge MOSFET AC dimmer (I2C address 0x10).
// Protocol: write one byte 0–255, but firmware misbehaves at high values; safe range 0–250.
// Ref: https://www.tindie.com/products/bugrovs2012/i2c-mosfet-trailing-edge-ac-led-dimmer-light/
class KridaDimmerOutput : public Component, public light::LightOutput, public i2c::I2CDevice {
 public:
  void set_min_power(float min_power) { min_power_ = min_power; }
  void set_max_power(float max_power) { max_power_ = max_power; }

  light::LightTraits get_traits() override {
    auto traits = light::LightTraits();
    traits.set_supported_color_modes({light::ColorMode::BRIGHTNESS});
    return traits;
  }

  void write_state(light::LightState *state) override {
    // Read raw brightness directly — do NOT use current_values_as_brightness(),
    // which applies gamma_correct and corrupts the value (gamma=0 → pow(x,0)=1).
    float brightness = state->current_values.get_brightness() * state->current_values.get_state();

    uint8_t value;
    if (brightness <= 0.0f) {
      // Off
      value = 0;
    } else if (state->remote_values.is_on()) {
      // On: map [0,1] → [min_power_, max_power_].
      // At HA 1% (brightness ≈ 1/255 ≈ 0.004) output ≈ min_power_ so LED always fires.
      // At HA 100% (brightness = 1.0) output = max_power_.
      float output = min_power_ + brightness * (max_power_ - min_power_);
      value = static_cast<uint8_t>(roundf(output * 250.0f));
      if (value > 250) value = 250;
    } else {
      // Fading to off: no floor — LED drops out naturally below its firing threshold
      // instead of sticking at min brightness for the whole fade duration.
      value = static_cast<uint8_t>(roundf(brightness * max_power_ * 250.0f));
      if (value > 250) value = 250;
    }

    // KRIDA firmware misbehaves at high byte values (255 and 254 confirmed bad).
    // Safe range: 0–250.
    auto err = this->write(&value, 1);
    if (err != i2c::ERROR_OK) {
      ESP_LOGW("krida_dimmer", "I2C write failed (err %d)", (int) err);
    }
  }

 protected:
  float min_power_{0.0f};
  float max_power_{1.0f};
};

}  // namespace krida_dimmer
}  // namespace esphome
