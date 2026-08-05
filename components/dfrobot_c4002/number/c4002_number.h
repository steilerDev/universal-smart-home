#pragma once

#include "esphome/components/number/number.h"
#include "../dfrobot_c4002.h"

namespace esphome {
namespace dfrobot_c4002 {

class TargetDisappeardDelayTimeNumber : public number::Number, public Parented<C4002Component> {
 protected:
  void control(float value) override;
};

class SensitivityThresholdNumber : public number::Number, public Parented<C4002Component> {
 protected:
  void control(float value) override;
};

}  // namespace dfrobot_c4002
}  // namespace esphome
