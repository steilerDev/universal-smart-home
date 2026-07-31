"""TRMNL BYOS display client for ESPHome.

Implements the TRMNL "Build Your Own Server" (BYOS) device protocol so an
ESP32 running ESPHome behaves like a native TRMNL e-ink display against a
self-hosted server such as LaraPaper:

  - GET /api/setup    — first-boot provisioning, obtains + persists an api_key
  - GET /api/display  — polls the server for the current screen image_url and
                        the server-driven refresh_rate
  - POST /api/log     — best-effort error reporting

Image fetch/decode/render is delegated to an ``online_image`` component (set
its URL at runtime + trigger a download); this component only speaks the
protocol and schedules refreshes.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import display, http_request
from esphome.components.online_image import OnlineImage
from esphome.const import CONF_ID, CONF_MODEL

CODEOWNERS = ["@steilerdev"]
DEPENDENCIES = ["network", "http_request"]
AUTO_LOAD = ["json"]

trmnl_ns = cg.esphome_ns.namespace("trmnl")
TrmnlDisplay = trmnl_ns.class_("TrmnlDisplay", cg.Component)

CONF_HTTP_REQUEST_ID = "http_request_id"
CONF_ONLINE_IMAGE_ID = "online_image_id"
CONF_DISPLAY_ID = "display_id"
CONF_SERVER = "server"
CONF_MAC_ADDRESS = "mac_address"
CONF_ACCESS_TOKEN = "access_token"
CONF_WIDTH = "width"
CONF_HEIGHT = "height"
CONF_FW_VERSION = "fw_version"
CONF_DEFAULT_REFRESH_RATE = "default_refresh_rate"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TrmnlDisplay),
        cv.GenerateID(CONF_HTTP_REQUEST_ID): cv.use_id(
            http_request.HttpRequestComponent
        ),
        cv.Required(CONF_ONLINE_IMAGE_ID): cv.use_id(OnlineImage),
        cv.Optional(CONF_DISPLAY_ID): cv.use_id(display.Display),
        cv.Required(CONF_SERVER): cv.string,
        cv.Optional(CONF_MAC_ADDRESS): cv.string,
        cv.Optional(CONF_ACCESS_TOKEN): cv.string,
        cv.Optional(CONF_WIDTH, default=800): cv.positive_int,
        cv.Optional(CONF_HEIGHT, default=480): cv.positive_int,
        cv.Optional(CONF_MODEL, default="esphome"): cv.string,
        cv.Optional(CONF_FW_VERSION, default="1.0.0"): cv.string,
        cv.Optional(
            CONF_DEFAULT_REFRESH_RATE, default="15min"
        ): cv.positive_time_period_seconds,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    http = await cg.get_variable(config[CONF_HTTP_REQUEST_ID])
    cg.add(var.set_http_request(http))

    image = await cg.get_variable(config[CONF_ONLINE_IMAGE_ID])
    cg.add(var.set_online_image(image))

    if CONF_DISPLAY_ID in config:
        disp = await cg.get_variable(config[CONF_DISPLAY_ID])
        cg.add(var.set_display(disp))

    cg.add(var.set_server(config[CONF_SERVER]))
    if CONF_MAC_ADDRESS in config:
        cg.add(var.set_mac_address(config[CONF_MAC_ADDRESS]))
    if CONF_ACCESS_TOKEN in config:
        cg.add(var.set_access_token(config[CONF_ACCESS_TOKEN]))
    cg.add(var.set_dimensions(config[CONF_WIDTH], config[CONF_HEIGHT]))
    cg.add(var.set_model(config[CONF_MODEL]))
    cg.add(var.set_fw_version(config[CONF_FW_VERSION]))
    cg.add(var.set_default_refresh_rate(config[CONF_DEFAULT_REFRESH_RATE]))
