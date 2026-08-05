import esphome.codegen as cg
from esphome.components import binary_sensor
import esphome.config_validation as cv
from esphome.const import DEVICE_CLASS_OCCUPANCY

from .. import CONF_C4002_ID, C4002Component, dfrobot_c4002_ns

CONF_PRESENCE = "presence"

C4002BinarySensorPresence = dfrobot_c4002_ns.class_(
    "C4002BinarySensorPresence", binary_sensor.BinarySensor
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_C4002_ID): cv.use_id(C4002Component),
        cv.Optional(CONF_PRESENCE): binary_sensor.binary_sensor_schema(
            C4002BinarySensorPresence,
            device_class=DEVICE_CLASS_OCCUPANCY,
        ),
    }
)


async def to_code(config):
    c4002_component = await cg.get_variable(config[CONF_C4002_ID])

    if presence_config := config.get(CONF_PRESENCE):
        bs = await binary_sensor.new_binary_sensor(presence_config)
        cg.add(c4002_component.register_listener(bs))
