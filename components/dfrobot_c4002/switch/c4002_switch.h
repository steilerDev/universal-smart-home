#pragma once

#include "esphome/components/switch/switch.h"
#include "esphome/core/component.h"
#include "../dfrobot_c4002.h"

namespace esphome {
namespace dfrobot_c4002 {

class C4002SwitchFactoryReset : public switch_::Switch, public Component, public Parented<C4002Component> {
 protected:
  void write_state(bool state) override;
};

class C4002SwitchCalibrate : public switch_::Switch, public Component, public Parented<C4002Component> {
 protected:
  void write_state(bool state) override;
};

}  // namespace dfrobot_c4002
}  // namespace esphome
