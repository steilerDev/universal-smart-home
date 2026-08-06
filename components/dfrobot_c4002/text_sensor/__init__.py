import esphome.codegen as cg
from esphome.components import text_sensor
import esphome.config_validation as cv
from esphome.const import ENTITY_CATEGORY_DIAGNOSTIC

from .. import CONF_C4002_ID, C4002Component, dfrobot_c4002_ns

C4002TextSensorHub = dfrobot_c4002_ns.class_("C4002TextSensorHub", cg.Component)
C4002GateStatusSensor = dfrobot_c4002_ns.class_(
    "C4002GateStatusSensor", text_sensor.TextSensor
)

CONF_C4002_TEXT_SENSOR = "c4002_text_sensor"
CONF_GATE_STATUS = "gate_status"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_C4002_ID): cv.use_id(C4002Component),
        cv.Optional(CONF_C4002_TEXT_SENSOR): text_sensor.text_sensor_schema(
            icon="mdi:message-text-outline"
        ),
        cv.Optional(CONF_GATE_STATUS): text_sensor.text_sensor_schema(
            C4002GateStatusSensor,
            icon="mdi:radar",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_C4002_ID])

    if CONF_C4002_TEXT_SENSOR in config:
        ts = await text_sensor.new_text_sensor(config[CONF_C4002_TEXT_SENSOR])
        cg.add(parent.set_text_sensor(ts))

    if gate_config := config.get(CONF_GATE_STATUS):
        gs = await text_sensor.new_text_sensor(gate_config)
        cg.add(parent.register_listener(gs))
