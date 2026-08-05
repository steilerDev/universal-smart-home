#include "dfrobot_c4002.h"
#include <string>
#include <cstdio>

namespace esphome {
namespace dfrobot_c4002 {

static const char *const TAG = "dfrobot_c4002: ";

void C4002Component::setup() {
  update_config_param();
  if (!this->is_failed()) {
    this->publish_text("C4002 initialized");
  }
}

void C4002Component::dump_config() {
  ESP_LOGCONFIG(TAG, "DFRobot C4002 mmWave Radar:");
  if (this->is_failed()) {
    if (this->last_uart_probe_bytes_ == 0) {
      ESP_LOGE(TAG, "  FAILED: no bytes received from sensor");
      ESP_LOGE(TAG, "  -> check power (VCC/GND) and that sensor TX -> ESP GPIO36");
    } else if (this->last_uart_probe_bytes_ > 0) {
      ESP_LOGE(TAG, "  FAILED: %d bytes received but frame invalid", this->last_uart_probe_bytes_);
      ESP_LOGE(TAG, "  -> possible baud rate mismatch or protocol error");
    } else {
      ESP_LOGE(TAG, "  FAILED: begin() not attempted (init error)");
    }
  } else {
    ESP_LOGCONFIG(TAG, "  Setup successful, detect range: %d cm", max_detect_range_cm_);
  }
}

void C4002Component::print_config() { ESP_LOGD(TAG, "run print config"); }

void C4002Component::loop() {
  static uint32_t last_time = 0;
  uint32_t now = millis();
  RetResult ret = {};

  ret = get_note_info_loop();
  if (ret.noteType == NOTE_INFO_RESULT) {
    ESP_LOGV(TAG, "NOTE_INFO_RESULT");
  } else if (ret.noteType == NOTE_INFO_CALIBRATION) {
    char msg[80];
    if (ret.calibCountdown > 0) {
      snprintf(msg, sizeof(msg), "Calibrating: %d s remaining...", ret.calibCountdown);
      this->publish_text(msg);
      ESP_LOGD(TAG, "Calibration countdown: %2d s", ret.calibCountdown);
    } else {
      // Calibration complete: read per-gate thresholds and apply sensitivity floor
      uint8_t cal_move[15] = {}, cal_exist[15] = {};
      get_distance_presence_threshold(MOVE_DIST_DOOR, cal_move);
      get_distance_presence_threshold(EXIST_DIST_DOOR, cal_exist);

      uint8_t sensitivity_floor = 0;
#ifdef USE_NUMBER
      if (sensitivity_threshold_number_ != nullptr && sensitivity_threshold_number_->has_state()) {
        sensitivity_floor = (uint8_t) sensitivity_threshold_number_->state;
      }
#endif

      uint8_t eff_move[15], eff_exist[15];
      uint8_t cal_min = 99, cal_max_val = 0;
      for (int i = 0; i < 15; i++) {
        if (cal_move[i] < cal_min) cal_min = cal_move[i];
        if (cal_move[i] > cal_max_val) cal_max_val = cal_move[i];
        if (cal_exist[i] < cal_min) cal_min = cal_exist[i];
        if (cal_exist[i] > cal_max_val) cal_max_val = cal_exist[i];
        eff_move[i] = (cal_move[i] > sensitivity_floor) ? cal_move[i] : sensitivity_floor;
        eff_exist[i] = (cal_exist[i] > sensitivity_floor) ? cal_exist[i] : sensitivity_floor;
      }
      set_distance_door_threshold(MOVE_DIST_DOOR, eff_move);
      set_distance_door_threshold(EXIST_DIST_DOOR, eff_exist);

      snprintf(msg, sizeof(msg), "Cal done. Range: %d-%d. Floor: %d.", cal_min, cal_max_val, sensitivity_floor);
      this->publish_text(msg);
      ESP_LOGD(TAG, "Calibration complete: %s", msg);
    }
  }

  if (now - last_time >= 1000) {
    last_time = now;
    get_data();
  }

  if (reset_flag_ == 1) {
    reset_flag_ = 0;
    restart();
    this->publish_text("Factory reset complete");
  }
}

void C4002Component::get_data() {
  TargetState target_state = get_target_state();
  for (auto &listener : this->listeners_) {
    if (listener != nullptr) {
      listener->on_target_status((uint8_t) target_state);
    }
  }
}

void C4002Component::update_config_param() {
  ESP_LOGD(TAG, "update config param");

  bool init_ok = false;
  for (int attempt = 1; attempt <= 3; attempt++) {
    this->uart_clear_buffer();
    if (begin()) {
      init_ok = true;
      break;
    }
    uint8_t probe[8] = {};
    size_t got = this->uart_read_raw(probe, sizeof(probe), 50);
    this->last_uart_probe_bytes_ = (int) got;
    ESP_LOGW(TAG, "C4002 begin failed (attempt %d/3) — %d bytes on UART (0=no power/wiring, >0=baud/protocol mismatch)",
             attempt, (int) got);
    delay(300);
  }
  if (!init_ok) {
    ESP_LOGE(TAG, "C4002 sensor not responding after 3 attempts — marking failed");
    this->mark_failed();
    return;
  }
  ESP_LOGI(TAG, "C4002 begin success");

  if (set_out_mode(OUT_MODE2)) {
    ESP_LOGD(TAG, "Output mode: presence-only (Mode_2)");
  }

  if (set_detect_range(0, (uint16_t) max_detect_range_cm_)) {
    ESP_LOGD(TAG, "Detect range: 0 - %d cm", max_detect_range_cm_);
  }

  set_run_led(LED_OFF);
  set_out_led(LED_OFF);

  float current_delay_time = (float) get_target_disappear_delay();
#ifdef USE_NUMBER
  if (target_disappeard_delay_time_number_ != nullptr) {
    target_disappeard_delay_time_number_->publish_state(current_delay_time);
  }
  if (sensitivity_threshold_number_ != nullptr) {
    uint8_t current_sensitivity = get_current_sensitivity_threshold();
    sensitivity_threshold_number_->publish_state(current_sensitivity);
    ESP_LOGD(TAG, "Sensitivity floor: %d", current_sensitivity);
  }
#endif

  if (set_report_period(10)) {
    ESP_LOGD(TAG, "set report period success");
  }
}

bool C4002Component::set_out_mode(OutMode out_mode) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 5;
  send_date[data_len++] = CMD_CONFIG_OUT_MODE;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = (uint8_t) out_mode;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  if (SUCCEED == rec_pack.resPonCode) {
    out_mode_ = out_mode;
    return true;
  }
  return false;
}

bool C4002Component::factory_reset() {
  uint8_t send_date[10];
  uint16_t data_len = 5;

  // Vendor order: CMD_FACTORY_RESET_USER (0x02) first, then CMD_FACTORY_RESET (0x80)
  send_date[0] = CMD_FACTORY_RESET_USER;
  send_date[1] = READ_AND_WRITE_REQ;
  send_date[2] = data_len >> 0 & 0xFF;
  send_date[3] = data_len >> 8 & 0xFF;
  send_date[4] = 0x00;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);
  RecvPack rec_pack = recv_pack();
  if (SUCCEED != rec_pack.resPonCode) {
    return false;
  }
  delay(10);

  send_date[0] = CMD_FACTORY_RESET;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);
  rec_pack = recv_pack();
  if (SUCCEED != rec_pack.resPonCode) {
    return false;
  }
  reset_flag_ = 1;
  return true;
}

bool C4002Component::set_resolution_mode(ResolutionMode mode) {
  uint8_t send_date[10];
  uint16_t data_len = 5;
  send_date[0] = CMD_GET_AND_SET_RESOLUTION_MODE;
  send_date[1] = READ_AND_WRITE_REQ;
  send_date[2] = data_len >> 0 & 0xFF;
  send_date[3] = data_len >> 8 & 0xFF;
  send_date[4] = (uint8_t) mode;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  if (SUCCEED == rec_pack.resPonCode) {
    resolution_mode_ = mode;
    return true;
  }
  return false;
}

bool C4002Component::enable_distance_door(DistanceDoorType door_type, const uint8_t *door_data) {
  uint8_t send_date[40];
  uint16_t data_len = 0;
  uint16_t temp = 5;
  int door_num = (resolution_mode_ == RESOLUTION_20CM) ? 25 : 15;
  temp += door_num;

  send_date[data_len++] = CMD_SET_DISTANCE_DOOR;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = (uint8_t) door_type;
  for (int i = 0; i < door_num; i++) {
    send_date[data_len++] = door_data[i];
  }
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

bool C4002Component::set_detect_range(uint16_t closest, uint16_t farthest) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 8;
  uint16_t closest_temp = closest, farthest_temp = farthest;
  send_date[data_len++] = CMD_SET_DETECT_RANGE;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;

  if (farthest_temp > 1100) {
    farthest_temp = 1100;
  }
  if (closest_temp > farthest_temp) {
    return false;
  }
  send_date[data_len++] = closest_temp >> 0 & 0xFF;
  send_date[data_len++] = closest_temp >> 8 & 0xFF;
  send_date[data_len++] = farthest_temp >> 0 & 0xFF;
  send_date[data_len++] = farthest_temp >> 8 & 0xFF;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

void C4002Component::start_env_calibration(uint16_t delay_time, uint16_t cont_time) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 9;
  send_date[data_len++] = CMD_ENVIRNMENT_CALIBRATION;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = delay_time >> 0 & 0xFF;
  send_date[data_len++] = delay_time >> 8 & 0xFF;
  send_date[data_len++] = cont_time >> 0 & 0xFF;
  send_date[data_len++] = cont_time >> 8 & 0xFF;
  send_date[data_len++] = 0x01;  // auto-generate per-gate thresholds
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);
  recv_pack();
}

bool C4002Component::set_run_led(LedMode run_led) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 6;
  send_date[data_len++] = CMD_SET_LED_MODE;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = run_led;
  send_date[data_len++] = LED_KEEP;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

bool C4002Component::set_out_led(LedMode out_led) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 6;
  send_date[data_len++] = CMD_SET_LED_MODE;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = LED_KEEP;
  send_date[data_len++] = out_led;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

bool C4002Component::set_target_disappear_delay(uint16_t delay_time) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 6;
  send_date[data_len++] = CMD_TARGET_DISAPPEAR_DELAY_TIME;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = delay_time >> 0 & 0xFF;
  send_date[data_len++] = delay_time >> 8 & 0xFF;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

// Packet format (vendor-corrected): CMD + REQ + len(2) + door_type + doorIndux(0x03) + activate(0x01) + 15 thresholds
bool C4002Component::set_distance_door_threshold(DistanceDoorType door_type, const uint8_t *threshold_data) {
  uint8_t send_date[45];
  uint16_t data_len = 0;
  uint16_t temp = 7 + 15;  // header(4) + door_type(1) + doorIndux(1) + activate(1) + 15 thresholds

  send_date[data_len++] = CMD_SET_DISTANCE_DOOR_THRESHOLD;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = (uint8_t) door_type;
  send_date[data_len++] = 0x03;  // doorIndux = eCustomThreshGroup
  send_date[data_len++] = 0x01;  // write/activate flag
  for (int i = 0; i < 15; i++) {
    send_date[data_len++] = threshold_data[i];
  }
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

// Apply floor_value as minimum per gate — never lowers a gate below its current calibrated value.
bool C4002Component::set_sensitivity_threshold(uint8_t floor_value) {
  uint8_t cur_move[15] = {}, cur_exist[15] = {};
  get_distance_presence_threshold(MOVE_DIST_DOOR, cur_move);
  get_distance_presence_threshold(EXIST_DIST_DOOR, cur_exist);
  for (int i = 0; i < 15; i++) {
    if (cur_move[i] < floor_value) cur_move[i] = floor_value;
    if (cur_exist[i] < floor_value) cur_exist[i] = floor_value;
  }
  bool ok = set_distance_door_threshold(MOVE_DIST_DOOR, cur_move);
  ok &= set_distance_door_threshold(EXIST_DIST_DOOR, cur_exist);
  return ok;
}

// Returns the minimum across all 30 gate values — represents the effective threshold floor.
uint8_t C4002Component::get_current_sensitivity_threshold() {
  uint8_t move_data[15] = {}, exist_data[15] = {};
  get_distance_presence_threshold(MOVE_DIST_DOOR, move_data);
  get_distance_presence_threshold(EXIST_DIST_DOOR, exist_data);
  uint8_t min_val = 99;
  for (int i = 0; i < 15; i++) {
    if (move_data[i] < min_val) min_val = move_data[i];
    if (exist_data[i] < min_val) min_val = exist_data[i];
  }
  return min_val;
}

uint16_t C4002Component::get_target_disappear_delay() {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 4;
  send_date[data_len++] = CMD_TARGET_DISAPPEAR_DELAY_TIME;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_pack(send_date, data_len, FRAME_TYPE_READ_REQUSET);

  RecvPack rec_pack = recv_pack();
  if (SUCCEED == rec_pack.resPonCode) {
    return (rec_pack.data[1] << 8) | rec_pack.data[0];
  }
  return 0;
}

int8_t C4002Component::restart() {
  int8_t ret = 0;
  uint8_t send_date[10];
  uint16_t data_len = 5;
  send_date[0] = CMD_RESTART;
  send_date[1] = READ_AND_WRITE_REQ;
  send_date[2] = data_len >> 0 & 0xFF;
  send_date[3] = data_len >> 8 & 0xFF;
  send_date[4] = 0x00;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  ret = (SUCCEED == rec_pack.resPonCode) ? 0 : -1;

  for (int i = 0; i < 50; i++) {
    delay(10);
  }
  update_config_param();
  delay(10);
  return ret;
}

void C4002Component::get_distance_presence_threshold(DistanceDoorType door_type, uint8_t *gate_data) {
  uint8_t send_data[10];
  uint16_t data_len = 0;
  uint16_t temp = 7;
  uint8_t door_num = 15;
  uint8_t i = 0;

  send_data[data_len++] = CMD_SET_DISTANCE_DOOR_THRESHOLD;
  send_data[data_len++] = READ_AND_WRITE_REQ;
  send_data[data_len++] = temp >> 0 & 0xFF;
  send_data[data_len++] = temp >> 8 & 0xFF;
  send_data[data_len++] = door_type;
  send_data[data_len++] = 0xff;
  send_data[data_len++] = 0x00;

  RecvPack rec_pack;
  rec_pack.resPonCode = CMD_ERR;

  while (SUCCEED != rec_pack.resPonCode) {
    send_pack(send_data, data_len, FRAME_TYPE_READ_REQUSET);
    rec_pack = recv_pack();
    if (SUCCEED == rec_pack.resPonCode) {
      memcpy(gate_data, &rec_pack.data[3], door_num);
      return;
    }
    if (i++ > 5) {
      return;
    }
    delay(20);
  }
}

// Publish current per-gate thresholds for both door types as a diagnostic log message.
void C4002Component::analysis_text_report() {
  uint8_t move_data[15] = {}, exist_data[15] = {};
  get_distance_presence_threshold(MOVE_DIST_DOOR, move_data);
  get_distance_presence_threshold(EXIST_DIST_DOOR, exist_data);

  char buf[180];
  int n = snprintf(buf, sizeof(buf), "Cal M:[");
  for (int i = 0; i < 15 && n < (int) sizeof(buf) - 1; i++)
    n += snprintf(buf + n, sizeof(buf) - n, i < 14 ? "%d," : "%d", move_data[i]);
  n += snprintf(buf + n, sizeof(buf) - n, "] E:[");
  for (int i = 0; i < 15 && n < (int) sizeof(buf) - 1; i++)
    n += snprintf(buf + n, sizeof(buf) - n, i < 14 ? "%d," : "%d", exist_data[i]);
  snprintf(buf + n, sizeof(buf) - n, "]");

  this->publish_text(buf);
}

TargetState C4002Component::get_target_state() { return (TargetState) detect_result_.targetStatus; }

bool C4002Component::begin() {
  bool ret;
  ret = set_report_period(255);
  if (!ret) return false;
  delay(10);
  ret = set_resolution_mode(resolution_mode_);
  if (!ret) return false;
  uint8_t all_on[DOOR_COUNT];
  for (int i = 0; i < DOOR_COUNT; i++) all_on[i] = 1;
  return enable_all_distance_door(all_on);
}

bool C4002Component::enable_all_distance_door(uint8_t *door_data) {
  bool ret = enable_distance_door(MOVE_DIST_DOOR, door_data);
  if (!ret) return false;
  return enable_distance_door(EXIST_DIST_DOOR, door_data);
}

RetResult C4002Component::get_note_info_loop() {
  RetResult ret = {};
  RecvPack rec_data = {};
  rec_data = recv_pack();

  if (SUCCEED == rec_data.resPonCode) {
    if (rec_data.packType == FRAME_TYPE_NOTIFICATION) {
      if (rec_data.dataHeader.cmd == NOTE_RESULT_CMD) {
        this->detect_result_.targetStatus = rec_data.data[0];
        this->detect_result_.light = rec_data.data[2] << 8 | rec_data.data[1];
        this->detect_result_.existDistIndex =
            rec_data.data[6] << 24 | rec_data.data[5] << 16 | rec_data.data[4] << 8 | rec_data.data[3];
        this->detect_result_.existCountDown = rec_data.data[8] << 8 | rec_data.data[7];
        this->detect_result_.existTargetDist = rec_data.data[10] << 8 | rec_data.data[9];
        this->detect_result_.existTargetEnery = rec_data.data[11];
        this->detect_result_.moveTargetDist = rec_data.data[13] << 8 | rec_data.data[12];
        this->detect_result_.moveTargetSpeed = rec_data.data[15] << 8 | rec_data.data[14];
        this->detect_result_.moveTargetEnery = rec_data.data[16];
        this->detect_result_.moveTargetDirect = rec_data.data[17];
        ret.noteType = NOTE_INFO_RESULT;
      } else if (rec_data.dataHeader.cmd == NOTE_ENVIRNMENT_CALIBRATION_CMD) {
        ret.calibCountdown = rec_data.data[1] << 8 | rec_data.data[0];
        ret.noteType = NOTE_INFO_CALIBRATION;
      } else {
        ret.noteType = NO_NOTE;
      }
    } else {
      ret.noteType = NO_NOTE;
    }
  } else {
    ret.noteType = NO_NOTE;
  }
  return ret;
}

bool C4002Component::get_resolution_mode() {
  uint8_t send_date[10];
  uint16_t data_len = 4;
  send_date[0] = CMD_GET_AND_SET_RESOLUTION_MODE;
  send_date[1] = READ_AND_WRITE_REQ;
  send_date[2] = data_len >> 0 & 0xFF;
  send_date[3] = data_len >> 8 & 0xFF;
  send_pack(send_date, data_len, FRAME_TYPE_READ_REQUSET);

  RecvPack rec_pack = recv_pack();
  if (SUCCEED == rec_pack.resPonCode) {
    resolution_mode_ = (ResolutionMode) rec_pack.data[0];
    return true;
  }
  return false;
}

bool C4002Component::set_report_period(uint8_t period) {
  uint8_t send_date[10];
  uint16_t data_len = 0;
  uint16_t temp = 5;
  send_date[data_len++] = CMD_SET_REPORT_PERIOD;
  send_date[data_len++] = READ_AND_WRITE_REQ;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = period;
  send_pack(send_date, data_len, FRAME_TYPE_WRITE_REQUSET);

  RecvPack rec_pack = recv_pack();
  return (SUCCEED == rec_pack.resPonCode);
}

void C4002Component::send_pack(void *pdata, uint16_t len, uint8_t msg_type) {
  uint8_t send_date[50] = {0};
  uint16_t data_len = 0;
  uint16_t check_sums = 0;

  send_date[data_len++] = C4002_FRAME_HEADER1;
  send_date[data_len++] = C4002_FRAME_HEADER2;
  send_date[data_len++] = C4002_FRAME_HEADER3;
  send_date[data_len++] = C4002_FRAME_HEADER4;
  uint16_t temp = len + 10;
  send_date[data_len++] = temp >> 0 & 0xFF;
  send_date[data_len++] = temp >> 8 & 0xFF;
  send_date[data_len++] = 0x00;
  send_date[data_len++] = msg_type;
  memcpy(&send_date[data_len], pdata, len);
  data_len += len;
  check_sums = get_check_sum((uint8_t *) send_date, data_len);

  send_date[data_len++] = check_sums >> 0 & 0xFF;
  send_date[data_len++] = check_sums >> 8 & 0xFF;

  uart_write_data(send_date, (size_t) data_len);
}

RecvPack C4002Component::recv_pack() {
  RecvPack recv_dat;
  memset(&recv_dat, 0, sizeof(recv_dat));

  std::vector<uint8_t> pdata(60, 0);

  size_t recv_len = uart_read_raw(pdata.data(), 8, 20);

  if (recv_len == 8 && pdata[0] == C4002_FRAME_HEADER1 && pdata[1] == C4002_FRAME_HEADER2 &&
      pdata[2] == C4002_FRAME_HEADER3 && pdata[3] == C4002_FRAME_HEADER4) {
    size_t pack_len = (pdata[5] << 8) | pdata[4];

    recv_len = uart_read_raw(&pdata[8], (size_t) (pack_len - 8), 20);

    if (recv_len == (pack_len - 8)) {
      recv_dat.packType = pdata[7];
      if (check_sum(pdata.data(), pack_len)) {
        uint16_t data_len = (pdata[11] << 8) | pdata[10];

        memcpy(&recv_dat, &pdata[8], data_len);
        recv_dat.resPonCode = (ResponseCode) recv_dat.dataHeader.respCode;

        if (recv_dat.packType == FRAME_TYPE_NOTIFICATION) {
          ESP_LOGV(TAG, "get note result");
        } else if (recv_dat.packType == FRAME_TYPE_WRITE_RESPOND) {
          ESP_LOGD(TAG, "get write respond");
        } else if (recv_dat.packType == FRAME_TYPE_READ_RESPOND) {
          ESP_LOGD(TAG, "get read respond");
        } else {
          ESP_LOGD(TAG, "this is error pack");
          recv_dat.resPonCode = CMD_ERR;
        }
      } else {
        recv_dat.resPonCode = AUTHENTICATION_ERR;
        ESP_LOGD(TAG, "Authentication error");
      }
    } else {
      recv_dat.resPonCode = DATALEN_ERR;
      ESP_LOGD(TAG, "recvlen error");
    }
  } else {
    recv_dat.resPonCode = AUTHENTICATION_ERR;
  }
  return recv_dat;
}

bool C4002Component::check_sum(const uint8_t *pdata, uint8_t len) {
  uint16_t calculateparity = 0;
  for (uint8_t i = 0; i < len - 2; i++) {
    calculateparity += pdata[i];
  }
  uint16_t temp = (pdata[len - 1] << 8) | pdata[len - 2];
  return (calculateparity == temp);
}

uint16_t C4002Component::get_check_sum(const uint8_t *pdata, uint16_t len) {
  uint16_t parity = 0;
  for (uint16_t i = 0; i < len; i++) {
    parity += pdata[i];
  }
  return parity;
}

void C4002Component::uart_clear_buffer() {
  uint8_t tmp[64];
  while (this->available() > 0) {
    size_t toread = std::min(static_cast<size_t>(this->available()), sizeof(tmp));
    this->read_array(tmp, toread);
  }
}

void C4002Component::uart_write_data(uint8_t *datas, size_t len) {
  uart_clear_buffer();
  this->write_array(datas, len);
}

size_t C4002Component::uart_read_raw(uint8_t *buf, size_t bufsize, uint32_t timeout_ms) {
  if (!buf) return 0;
  size_t idx = 0;
  uint32_t start = millis();
  buf[0] = '\0';
  while ((millis() - start) < timeout_ms && idx < bufsize) {
    size_t avail = this->available();
    if (avail > 0) {
      size_t toread = std::min(avail, bufsize - idx);
      this->read_array(buf + idx, toread);
      idx += toread;
      if (idx >= bufsize) break;
      continue;
    }
    delay(1);
  }
  buf[idx] = '\0';
  return idx;
}

void C4002Component::publish_text(const std::string &msg) {
#ifdef USE_TEXT_SENSOR
  if (this->text_sensor_ != nullptr) {
    this->text_sensor_->publish_state(msg);
  }
#else
  (void) msg;
#endif
}

}  // namespace dfrobot_c4002
}  // namespace esphome
