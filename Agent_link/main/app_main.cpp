#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "agent_link.h"
#include "board.h"
#include "device_protocol.h"

namespace {
constexpr const char* TAG = "agent_link.app";

void on_audio_out(const uint8_t* pcm16, size_t bytes, void*) {
    Board::GetInstance().PlayAudio(pcm16, bytes);
}
void on_audio_end(void*) {
    Board::GetInstance().AudioEnd();
}
void on_show_text(const char* utf8, void*) {
    Board::GetInstance().SetUiState(DeviceUiState::Thinking);
    Board::GetInstance().ShowText(utf8);
}
void on_haptic(uint32_t duration_ms, void*) { Board::GetInstance().Vibrate(duration_ms); }
void on_led(uint32_t rgb, void*) { Board::GetInstance().SetLed(rgb); }
void on_listen(bool start, uint32_t max_ms, void*) {
    Board::GetInstance().SetRemoteListening(start, max_ms);
}
void on_custom(uint16_t cmd, const uint8_t* payload, size_t len, void*) {
    if (cmd != 0x70) {
        ESP_LOGD(TAG, "ignoring non-project custom command 0x%04x", static_cast<unsigned>(cmd));
        return;
    }
    ESP_LOGI(TAG, "custom command 0x%04x, payload=%u bytes",
             static_cast<unsigned>(cmd), static_cast<unsigned>(len));
    if (!HandleDeviceJson(payload, len, Board::GetInstance())) {
        ESP_LOGW(TAG, "custom command 0x%04x was not handled", static_cast<unsigned>(cmd));
    }
}

void on_state(agent_state_t state, void*) {
    ESP_LOGI(TAG, "[state] %s",
             state == AGENT_STATE_READY     ? "READY" :
             state == AGENT_STATE_CONNECTED ? "CONNECTED" : "DISCONNECTED");
    Board::GetInstance().SetUiState(
        state == AGENT_STATE_READY ? DeviceUiState::Idle :
        state == AGENT_STATE_CONNECTED ? DeviceUiState::Boot : DeviceUiState::Offline);
    if (state == AGENT_STATE_READY) Board::GetInstance().PlayHapticPattern(HapticPattern::Success);
}
}  // namespace

extern "C" void app_main(void) {
    Board& board = Board::GetInstance();
    ESP_LOGI(TAG, "board = %s, caps = 0x%04x", board.Name(), static_cast<unsigned>(board.Capabilities()));

    //Callback function registration
    agent_output_cb_t out = {};
    out.on_audio_out = on_audio_out;
    out.on_audio_end = on_audio_end;
    out.on_show_text = on_show_text;
    out.on_haptic    = on_haptic;
    out.on_led       = on_led;
    out.on_custom    = on_custom;
    out.on_listen    = on_listen;

    agent_link_config_t cfg = {};
    cfg.device_name = board.Name();
    cfg.caps        = board.Capabilities();
    cfg.output      = &out;
    cfg.on_state    = on_state;
#if CONFIG_AGENT_LINK_TRANSPORT_WIFI
    cfg.transport   = AGENT_TRANSPORT_WIFI;  // WiFi station + captive-portal provisioning
#endif

    ESP_ERROR_CHECK(agent_link_init(&cfg));     //agent_link initialization
    ESP_ERROR_CHECK(agent_link_start());

    while (true) {
        if (agent_link_state() == AGENT_STATE_READY) {
            const int batt = board.GetBatteryLevel();
            if (batt >= 0) {
                const bool charging = board.IsCharging();
                agent_link_report_battery(static_cast<uint8_t>(batt), charging);
                if (batt <= 10 && !charging) board.SetUiState(DeviceUiState::LowBattery);
            }
            ESP_LOGD(TAG, "battery poll (batt=%d)", batt);
        }
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
