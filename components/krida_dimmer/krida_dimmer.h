#pragma once

#include "esphome/core/component.h"
#include "esphome/components/i2c/i2c.h"
#include "esphome/components/light/light_output.h"
#include "esphome/components/light/light_traits.h"

namespace esphome {
namespace krida_dimmer {

// KRIDA single-channel trailing-edge MOSFET AC dimmer (I2C address 0x10).
// Protocol: write one byte 0–255 (0=off, 255=full power) to the device address.
// Ref: https://www.tindie.com/products/bugrovs2012/i2c-mosfet-trailing-edge-ac-led-dimmer-light/
class KridaDimmerOutput : public Component, public light::LightOutput, public i2c::I2CDevice {
 public:
  light::LightTraits get_traits() override {
    auto traits = light::LightTraits();
    traits.set_supported_color_modes({light::ColorMode::BRIGHTNESS});
    return traits;
  }

  void write_state(light::LightState *state) override {
    float brightness;
    state->current_values_as_brightness(&brightness);
    uint8_t value = static_cast<uint8_t>(brightness * 255.0f);
    auto err = this->write(&value, 1);
    if (err != i2c::ERROR_OK) {
      ESP_LOGW("krida_dimmer", "I2C write failed (err %d)", (int) err);
    }
  }
};

}  // namespace krida_dimmer
}  // namespace esphome
