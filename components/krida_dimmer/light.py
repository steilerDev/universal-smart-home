import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import light, i2c
from esphome.const import CONF_OUTPUT_ID, CONF_MIN_POWER, CONF_MAX_POWER

DEPENDENCIES = ["i2c"]
AUTO_LOAD = ["light"]

krida_dimmer_ns = cg.esphome_ns.namespace("krida_dimmer")
KridaDimmerOutput = krida_dimmer_ns.class_(
    "KridaDimmerOutput", light.LightOutput, cg.Component, i2c.I2CDevice
)

CONFIG_SCHEMA = (
    light.BRIGHTNESS_ONLY_LIGHT_SCHEMA.extend(
        {
            cv.GenerateID(CONF_OUTPUT_ID): cv.declare_id(KridaDimmerOutput),
            cv.Optional(CONF_MIN_POWER, default=0.0): cv.percentage,
            cv.Optional(CONF_MAX_POWER, default=1.0): cv.percentage,
        }
    )
    .extend(i2c.i2c_device_schema(0x10))
    .extend(cv.COMPONENT_SCHEMA)
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_OUTPUT_ID])
    await cg.register_component(var, config)
    await light.register_light(var, config)
    await i2c.register_i2c_device(var, config)
    cg.add(var.set_min_power(config[CONF_MIN_POWER]))
    cg.add(var.set_max_power(config[CONF_MAX_POWER]))
