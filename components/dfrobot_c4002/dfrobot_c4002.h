#pragma once

#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include <string>
#include <stdint.h>

#ifdef USE_NUMBER
#include "esphome/components/number/number.h"
#endif
#ifdef USE_SWITCH
#include "esphome/components/switch/switch.h"
#endif
#ifdef USE_TEXT_SENSOR
#include "esphome/components/text_sensor/text_sensor.h"
#endif

namespace esphome {
namespace dfrobot_c4002 {

class C4002Listener {
 public:
  virtual void on_target_status(uint8_t state){};
};

static const uint8_t TIME_OUT = 0x64;

static const uint8_t C4002_FRAME_HEADER1 = 0xFA;
static const uint8_t C4002_FRAME_HEADER2 = 0xF5;
static const uint8_t C4002_FRAME_HEADER3 = 0xAA;
static const uint8_t C4002_FRAME_HEADER4 = 0xA5;

static const uint8_t FRAME_TYPE_WRITE_REQUSET = 0x00;
static const uint8_t FRAME_TYPE_READ_REQUSET = 0x01;
static const uint8_t FRAME_TYPE_WRITE_RESPOND = 0x02;
static const uint8_t FRAME_TYPE_READ_RESPOND = 0x03;
static const uint8_t FRAME_TYPE_NOTIFICATION = 0x04;
static const uint8_t FRAME_ERROR = 0xFF;

static const uint8_t CMD_SET_LED_MODE = 0xA1;
static const uint8_t CMD_CONFIG_OUT_MODE = 0xA0;
static const uint8_t CMD_ENVIRNMENT_CALIBRATION = 0x60;
static const uint8_t CMD_RESTART = 0x00;
static const uint8_t CMD_SET_DETECT_RANGE = 0x86;
static const uint8_t CMD_FACTORY_RESET = 0x80;
static const uint8_t CMD_SET_REPORT_PERIOD = 0x83;
static const uint8_t CMD_SET_DISTANCE_DOOR = 0x62;
static const uint8_t CMD_GET_VERSION = 0x82;
static const uint8_t CMD_GET_AND_SET_RESOLUTION_MODE = 0x66;
static const uint8_t CMD_SET_DISTANCE_DOOR_THRESHOLD = 0x63;
static const uint8_t CMD_SET_BAUDRATE = 0x21;
static const uint8_t CMD_TARGET_DISAPPEAR_DELAY_TIME = 0x84;
static const uint8_t CMD_FACTORY_RESET_USER = 0x02;

static const uint8_t NOTE_RESULT_CMD = 0x60;
static const uint8_t NOTE_ENVIRNMENT_CALIBRATION_CMD = 0x03;

static const uint8_t SOFTWARE_VERSION = 0x01;
static const uint8_t HARDWARE_VERSION = 0x00;
static const int DOOR_COUNT = 15;

enum ResolutionMode { RESOLUTION_80CM = 0x00, RESOLUTION_20CM = 0x01 };

enum DistanceDoorType { MOVE_DIST_DOOR = 0x00, EXIST_DIST_DOOR = 0x01 };

enum ResponseCode {
  READ_AND_WRITE_REQ = 0x00,
  SUCCEED = 0x01,
  CMD_ERR = 0x02,
  AUTHENTICATION_ERR = 0x03,
  RESOURCES_BUSY = 0x04,
  PARAMS_ERR = 0x05,
  DATALEN_ERR = 0x06,
  INTERNAL_ERR = 0x07
};

enum OutMode {
  OUT_MODE1 = 0x01,
  OUT_MODE2 = 0x02,
  OUT_MODE3 = 0x03,
  OUT_MODEX = 0xFF
};

enum TargetState { NO_BODY = 0, EXIST = 1, MOVE = 2, TARGET_ERROR = 255 };

enum LedMode { LED_OFF = 0x00, LED_ON = 0x01, LED_KEEP = 0xFF };

enum NoteType {
  NO_NOTE = 0x00,
  NOTE_INFO_RESULT = 0x01,
  NOTE_INFO_CALIBRATION = 0x02,
};

struct DetectResult {
  uint8_t targetStatus;
  uint16_t light;
  uint32_t existDistIndex;
  uint16_t existCountDown;
  uint16_t existTargetDist;
  uint8_t existTargetEnery;
  uint16_t moveTargetDist;
  int16_t moveTargetSpeed;
  uint8_t moveTargetEnery;
  uint8_t moveTargetDirect;
};

using DetectRet = DetectResult;

struct DataHeader {
  uint8_t cmd;
  uint8_t respCode;
  uint16_t dataLen;
};
using DetectHead = DataHeader;

struct RecvPack {
  DetectHead dataHeader;
  uint8_t data[50];
  uint8_t packType;
  ResponseCode resPonCode;
};

using RecvPck = RecvPack;

struct ReturnResult {
  NoteType noteType;
  uint16_t calibCountdown;
};

using RetResult = ReturnResult;

class C4002Component : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;

  void uart_clear_buffer();
  void print_config();
  void update_config_param();
  void get_data();

  void register_listener(C4002Listener *listener) { this->listeners_.push_back(listener); }

  bool begin();

  bool factory_reset();
  bool set_resolution_mode(ResolutionMode mode);
  bool enable_distance_door(DistanceDoorType door_type, const uint8_t *door_data);
  bool enable_all_distance_door(uint8_t *door_data);
  bool set_detect_range(uint16_t closest, uint16_t farthest);
  void start_env_calibration(uint16_t delay_time, uint16_t cont_time);
  bool set_run_led(LedMode run_led);
  bool set_out_led(LedMode out_led);
  bool set_out_mode(OutMode out_mode);
  bool set_report_period(uint8_t period);
  bool set_target_disappear_delay(uint16_t delay_time);
  bool set_distance_door_threshold(DistanceDoorType door_type, const uint8_t *threshold_data);
  bool set_sensitivity_threshold(uint8_t floor_value);
  uint8_t get_current_sensitivity_threshold();

  void analysis_text_report();
  void get_distance_presence_threshold(DistanceDoorType door_type, uint8_t *gate_data);
  uint16_t get_target_disappear_delay();
  TargetState get_target_state();
  bool get_resolution_mode();
  RetResult get_note_info_loop();

  int8_t restart();
  void send_pack(void *pdata, uint16_t len, uint8_t msg_type);
  RecvPck recv_pack();
  bool check_sum(const uint8_t *pdata, uint8_t len);
  uint16_t get_check_sum(const uint8_t *pdata, uint16_t len);
  size_t uart_read_raw(uint8_t *buf, size_t bufsize, uint32_t timeout_ms = 200);
  void uart_write_data(uint8_t *datas, size_t len);

  void set_max_detect_range_cm(int cm) { max_detect_range_cm_ = cm; }

#ifdef USE_SWITCH
  void set_factory_reset_switch(switch_::Switch *sw) { this->factory_reset_switch_ = sw; }
  void set_calibrate_switch(switch_::Switch *sw) { this->env_calibration_switch_ = sw; }
#endif

#ifdef USE_NUMBER
  void set_target_disappeard_delay_time_number(number::Number *number) {
    this->target_disappeard_delay_time_number_ = number;
  }
  void set_sensitivity_threshold_number(number::Number *number) { this->sensitivity_threshold_number_ = number; }
#endif

#ifdef USE_TEXT_SENSOR
  void set_text_sensor(text_sensor::TextSensor *ts) { this->text_sensor_ = ts; }
#endif
  void publish_text(const std::string &msg);

 protected:
  int last_uart_probe_bytes_{-1};

  DetectRet detect_result_;
  ResolutionMode resolution_mode_ = RESOLUTION_80CM;
  OutMode out_mode_;
  int max_detect_range_cm_{500};
  uint8_t reset_flag_ = 0;

#ifdef USE_SWITCH
  switch_::Switch *factory_reset_switch_{nullptr};
  switch_::Switch *env_calibration_switch_{nullptr};
#endif

#ifdef USE_NUMBER
  number::Number *target_disappeard_delay_time_number_{nullptr};
  number::Number *sensitivity_threshold_number_{nullptr};
#endif

#ifdef USE_TEXT_SENSOR
  text_sensor::TextSensor *text_sensor_{nullptr};
#endif

  std::vector<C4002Listener *> listeners_{};
};

}  // namespace dfrobot_c4002
}  // namespace esphome
