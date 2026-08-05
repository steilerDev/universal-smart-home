import esphome.codegen as cg
from esphome.components import switch
import esphome.config_validation as cv
from esphome.const import ENTITY_CATEGORY_CONFIG

from .. import CONF_C4002_ID, C4002Component, dfrobot_c4002_ns

CONF_CALIBRATE = "calibrate"
CONF_FACTORY_RESET = "factory_reset"

C4002SwitchCalibrate = dfrobot_c4002_ns.class_("C4002SwitchCalibrate", switch.Switch)
C4002SwitchFactoryReset = dfrobot_c4002_ns.class_(
    "C4002SwitchFactoryReset", switch.Switch
)

CONFIG_SCHEMA = {
    cv.GenerateID(CONF_C4002_ID): cv.use_id(C4002Component),
    cv.Optional(CONF_CALIBRATE): switch.switch_schema(
        C4002SwitchCalibrate,
        entity_category=ENTITY_CATEGORY_CONFIG,
        icon="mdi:radar",
    ),
    cv.Optional(CONF_FACTORY_RESET): switch.switch_schema(
        C4002SwitchFactoryReset,
        entity_category=ENTITY_CATEGORY_CONFIG,
        icon="mdi:restart",
    ),
}


async def to_code(config):
    switch_component = await cg.get_variable(config[CONF_C4002_ID])

    if calibrate_config := config.get(CONF_CALIBRATE):
        sw = await switch.new_switch(calibrate_config)
        await cg.register_parented(sw, config[CONF_C4002_ID])
        cg.add(switch_component.set_calibrate_switch(sw))

    if factory_reset_config := config.get(CONF_FACTORY_RESET):
        sw = await switch.new_switch(factory_reset_config)
        await cg.register_parented(sw, config[CONF_C4002_ID])
        cg.add(switch_component.set_factory_reset_switch(sw))
