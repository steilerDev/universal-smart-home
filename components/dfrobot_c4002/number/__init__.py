import esphome.codegen as cg
from esphome.components import number
import esphome.config_validation as cv
from esphome.const import ENTITY_CATEGORY_CONFIG

from .. import CONF_C4002_ID, C4002Component, dfrobot_c4002_ns

CONF_TARGET_DISAPPEAR_DELAY = "target_disappear_delay"
CONF_SENSITIVITY_THRESHOLD = "sensitivity_threshold"

TargetDisappeardDelayTimeNumber = dfrobot_c4002_ns.class_(
    "TargetDisappeardDelayTimeNumber", number.Number
)
SensitivityThresholdNumber = dfrobot_c4002_ns.class_(
    "SensitivityThresholdNumber", number.Number
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_C4002_ID): cv.use_id(C4002Component),
        cv.Optional(CONF_TARGET_DISAPPEAR_DELAY): number.number_schema(
            TargetDisappeardDelayTimeNumber,
            entity_category=ENTITY_CATEGORY_CONFIG,
            icon="mdi:timer",
            unit_of_measurement="s",
        ),
        cv.Optional(CONF_SENSITIVITY_THRESHOLD): number.number_schema(
            SensitivityThresholdNumber,
            entity_category=ENTITY_CATEGORY_CONFIG,
            icon="mdi:signal-cellular-3",
        ),
    }
)


async def to_code(config):
    number_component = await cg.get_variable(config[CONF_C4002_ID])

    if delay_config := config.get(CONF_TARGET_DISAPPEAR_DELAY):
        n = await number.new_number(delay_config, min_value=0, max_value=3600, step=1)
        await cg.register_parented(n, config[CONF_C4002_ID])
        cg.add(number_component.set_target_disappeard_delay_time_number(n))

    if sensitivity_config := config.get(CONF_SENSITIVITY_THRESHOLD):
        n = await number.new_number(sensitivity_config, min_value=0, max_value=99, step=1)
        await cg.register_parented(n, config[CONF_C4002_ID])
        cg.add(number_component.set_sensitivity_threshold_number(n))
