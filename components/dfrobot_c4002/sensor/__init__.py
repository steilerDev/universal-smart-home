import esphome.codegen as cg
from esphome.components import sensor
import esphome.config_validation as cv
from esphome.const import CONF_ID, ENTITY_CATEGORY_DIAGNOSTIC

from .. import CONF_C4002_ID, C4002Component, dfrobot_c4002_ns

C4002Sensor = dfrobot_c4002_ns.class_("C4002Sensor", cg.Component)

CONF_TARGET_STATUS = "target_status"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(C4002Sensor),
        cv.Required(CONF_C4002_ID): cv.use_id(C4002Component),
        cv.Optional(CONF_TARGET_STATUS): sensor.sensor_schema(
            icon="mdi:target",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            accuracy_decimals=0,
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    c4002_sensor = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(c4002_sensor, config)

    if CONF_TARGET_STATUS in config:
        sens = await sensor.new_sensor(config[CONF_TARGET_STATUS])
        cg.add(c4002_sensor.set_target_status_sensor(sens))

    c4002_component = await cg.get_variable(config[CONF_C4002_ID])
    cg.add(c4002_component.register_listener(c4002_sensor))
