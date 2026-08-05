import math

import esphome.codegen as cg
from esphome.components import uart
import esphome.config_validation as cv
from esphome.const import CONF_ID

DEPENDENCIES = ["uart"]
MULTI_CONF = True
CODEOWNERS = ["@jiaziui"]

dfrobot_c4002_ns = cg.esphome_ns.namespace("dfrobot_c4002")
C4002Component = dfrobot_c4002_ns.class_(
    "C4002Component", cg.Component, uart.UARTDevice
)

CONF_C4002_ID = "c4002_id"
CONF_ROOM_WIDTH = "room_width"
CONF_ROOM_DEPTH = "room_depth"
CONF_CEILING_HEIGHT = "ceiling_height"

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(C4002Component),
            cv.Optional(CONF_ROOM_WIDTH): cv.positive_float,
            cv.Optional(CONF_ROOM_DEPTH): cv.positive_float,
            cv.Optional(CONF_CEILING_HEIGHT): cv.positive_float,
        }
    )
    .extend(uart.UART_DEVICE_SCHEMA)
    .extend(cv.COMPONENT_SCHEMA)
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)

    if (
        CONF_ROOM_WIDTH in config
        and CONF_ROOM_DEPTH in config
        and CONF_CEILING_HEIGHT in config
    ):
        w = config[CONF_ROOM_WIDTH]
        d = config[CONF_ROOM_DEPTH]
        h = config[CONF_CEILING_HEIGHT]
        horizontal = math.sqrt((w / 2) ** 2 + (d / 2) ** 2)
        slant = math.sqrt(h**2 + horizontal**2)
        detect_range_cm = int(slant * 100)
        detect_range_cm = min(detect_range_cm, 1100)
        cg.add(var.set_max_detect_range_cm(detect_range_cm))
