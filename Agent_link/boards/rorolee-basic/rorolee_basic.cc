// RoRoLee-S3 (ESP32-S3)

#include "board.h"
#include "config.h"
#include "sh8501_panel.h"
#include "es_codec.h"
#include "bq27220.h"

#include "agent_link.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/stream_buffer.h"
#include "freertos/timers.h"
#include "freertos/queue.h"
#include "esp_heap_caps.h"


#include <atomic>

#define TAG "RoRoLeeS3"

class RoRoLeeS3Board : public Board {
public:
    RoRoLeeS3Board() {
        PowerOnRail();
        InitDisplay();
        InitUi();
        InitCodec();
        InitFuelGauge();
        InitHaptic();
        InitButton();
    }

    const char* Name() const override { return "ROROLEE_BASIC"; }

    uint32_t Capabilities() const override {
        return AGENT_CAP_MIC | AGENT_CAP_SPEAKER | AGENT_CAP_SCREEN |
               AGENT_CAP_BUTTON | AGENT_CAP_HAPTIC | AGENT_CAP_BATTERY |
               AGENT_CAP_RECORDING;
    }

    // The tiny display uses semantic animation states; text remains available in logs for diagnostics.
    void ShowText(const char* utf8) override {
        ESP_LOGI(TAG, "ShowText \"%s\" -> thinking animation", utf8 ? utf8 : "");
    }

    void SetUiState(DeviceUiState state) override {
        base_ui_state_.store(state, std::memory_order_release);
        ResolveUiState();
    }

    void PlayHapticPattern(HapticPattern pattern) override {
        if (!haptic_queue_) return;
        if (xQueueSend(haptic_queue_, &pattern, 0) != pdTRUE)
            ESP_LOGW(TAG, "haptic queue full; pattern dropped");
    }

    // TTS callback runs in the BLE host task: enqueue only, never write I2S here.
    void PlayAudio(const uint8_t* pcm16, size_t bytes) override {
        if (!play_buf_ || !pcm16 || bytes == 0) return;
        last_audio_rx_tick_.store(static_cast<uint32_t>(xTaskGetTickCount()), std::memory_order_release);
        audio_end_pending_.store(false, std::memory_order_release);
        playback_active_.store(true, std::memory_order_release);
        if (capture_active_.load(std::memory_order_acquire))
            playback_preempt_requested_.store(true, std::memory_order_release);
        ResolveUiState();

        const size_t sent = xStreamBufferSend(play_buf_, pcm16, bytes, 0);
        if (sent < bytes) {
            ESP_LOGW(TAG, "play buffer full - dropped %u/%u bytes",
                     static_cast<unsigned>(bytes - sent), static_cast<unsigned>(bytes));
        }
    }

    void AudioEnd() override {
        audio_end_pending_.store(true, std::memory_order_release);
        ESP_LOGI(TAG, "AudioEnd received; waiting for queued PCM and codec tail");
    }

    void SetRemoteListening(bool start, uint32_t max_ms) override {
        remote_capture_max_ms_.store(max_ms, std::memory_order_release);
        remote_capture_requested_.store(start, std::memory_order_release);
        if (ptt_task_) xTaskNotifyGive(ptt_task_);
        ESP_LOGI(TAG, "BLE capture request: %s, max_ms=%u", start ? "start" : "stop",
                 static_cast<unsigned>(max_ms));
    }

    void Vibrate(uint32_t ms) override {
        if (!haptic_timer_) return;
        if (ms > 2000) ms = 2000;
        gpio_set_level(HAPTIC_PIN, ms ? 1 : 0);
        if (ms) {
            xTimerChangePeriod(haptic_timer_, pdMS_TO_TICKS(ms), 0);
            xTimerStart(haptic_timer_, 0);
        }
        ESP_LOGI(TAG, "haptic GPIO%d active-high for %u ms", (int)HAPTIC_PIN, (unsigned)ms);
    }
    // Device -> Agent: battery / charging (app_main polls every 5s -> agent_link_report_battery -> event 0x14 + 0x2A19).
    int  GetBatteryLevel() override { return gauge_ok_ ? gauge_.Soc() : -1; }
    bool IsCharging()      override { return gauge_ok_ && gauge_.IsCharging(); }

private:
    static const char* StateName(DeviceUiState state) {
        switch (state) {
        case DeviceUiState::Boot: return "BOOT";
        case DeviceUiState::Idle: return "IDLE";
        case DeviceUiState::Listening: return "LISTENING";
        case DeviceUiState::Uploading: return "UPLOADING";
        case DeviceUiState::Thinking: return "THINKING";
        case DeviceUiState::Speaking: return "SPEAKING";
        case DeviceUiState::Reminder: return "REMINDER";
        case DeviceUiState::FamilyMessage: return "FAMILY_MESSAGE";
        case DeviceUiState::Offline: return "OFFLINE";
        case DeviceUiState::Error: return "ERROR";
        case DeviceUiState::LowBattery: return "LOW_BATTERY";
        }
        return "UNKNOWN";
    }

    void ResolveUiState() {
        const DeviceUiState requested = base_ui_state_.load(std::memory_order_acquire);
        DeviceUiState resolved = requested;

        // Connectivity/fatal errors are always visible. Capture then owns the face.
        // Playback owns only the generic conversational states; reminder/family/error
        // keep their semantic animation while their TTS is playing.
        if (requested == DeviceUiState::Offline || requested == DeviceUiState::Error) {
            resolved = requested;
        } else if (capture_active_.load(std::memory_order_acquire)) {
            resolved = DeviceUiState::Listening;
        } else if (playback_active_.load(std::memory_order_acquire)) {
            if (requested != DeviceUiState::Reminder &&
                requested != DeviceUiState::FamilyMessage) {
                resolved = DeviceUiState::Speaking;
            }
        }

        const DeviceUiState old = ui_state_.exchange(resolved, std::memory_order_acq_rel);
        if (old != resolved) {
            ESP_LOGI(TAG, "device state: %s -> %s (requested=%s)",
                     StateName(old), StateName(resolved), StateName(requested));
        }
    }

    static void HapticOff(TimerHandle_t timer) {
        auto* self = static_cast<RoRoLeeS3Board*>(pvTimerGetTimerID(timer));
        gpio_set_level(HAPTIC_PIN, 0);
        if (self->gauge_ok_) ESP_LOGI(TAG, "haptic off, battery current=%d mA", self->gauge_.CurrentMa());
    }

    static void HapticTaskEntry(void* arg) {
        auto* self = static_cast<RoRoLeeS3Board*>(arg);
        HapticPattern pattern;
        while (true) {
            if (xQueueReceive(self->haptic_queue_, &pattern, portMAX_DELAY) != pdTRUE) continue;
            uint16_t pulse[3] = {};
            uint8_t count = 0;
            switch (pattern) {
            case HapticPattern::Success:           pulse[0] = 100; count = 1; break;
            case HapticPattern::Reminder:          pulse[0] = 140; pulse[1] = 140; count = 2; break;
            case HapticPattern::FamilyMessage:     pulse[0] = 450; pulse[1] = 140; count = 2; break;
            case HapticPattern::ImportantReminder: pulse[0] = 140; pulse[1] = 140; pulse[2] = 140; count = 3; break;
            case HapticPattern::Error:             pulse[0] = 650; count = 1; break;
            }
            for (uint8_t i = 0; i < count; ++i) {
                self->Vibrate(pulse[i]);
                vTaskDelay(pdMS_TO_TICKS(pulse[i] + 180));
            }
        }
    }

    void InitHaptic() {
        gpio_config_t c = {};
        c.pin_bit_mask = 1ULL << HAPTIC_PIN;
        c.mode = GPIO_MODE_OUTPUT;
        c.pull_down_en = GPIO_PULLDOWN_ENABLE;
        gpio_config(&c);
        gpio_set_level(HAPTIC_PIN, 0);
        haptic_timer_ = xTimerCreate("haptic_off", pdMS_TO_TICKS(100), pdFALSE, this, &RoRoLeeS3Board::HapticOff);
        haptic_queue_ = xQueueCreate(6, sizeof(HapticPattern));
        if (!haptic_timer_ || !haptic_queue_) { ESP_LOGE(TAG, "haptic manager creation failed"); return; }
        xTaskCreate(&RoRoLeeS3Board::HapticTaskEntry, "haptic_mgr", 2048, this, 3, &haptic_task_);
        ESP_LOGI(TAG, "haptic manager ready on GPIO%d (active high)", (int)HAPTIC_PIN);
    }
    static void UiTaskEntry(void* arg) { static_cast<RoRoLeeS3Board*>(arg)->UiLoop(); }

    void InitUi() {
        if (!panel_.Ready()) return;
        frame_ = static_cast<uint16_t*>(heap_caps_malloc(
            DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (!frame_) { ESP_LOGE(TAG, "UI framebuffer allocation failed"); return; }
        xTaskCreate(&RoRoLeeS3Board::UiTaskEntry, "ui_anim", 4096, this, 3, &ui_task_);
        ESP_LOGI(TAG, "UI animation ready: %dx%d RGB565", DISPLAY_WIDTH, DISPLAY_HEIGHT);
    }

    // UI uses a logical 240x120 landscape canvas, rotated counter-clockwise into the physical panel.
    void PutPixel(int x, int y, uint16_t color) {
        if ((unsigned)x >= 240 || (unsigned)y >= 120) return;
        const int physical_x = y;
        const int physical_y = 239 - x;
        frame_[physical_y * DISPLAY_WIDTH + physical_x] = color;
    }

    void FillRect(int x, int y, int w, int h, uint16_t color) {
        for (int yy = y; yy < y + h; ++yy)
            for (int xx = x; xx < x + w; ++xx) PutPixel(xx, yy, color);
    }

    void FillCircle(int cx, int cy, int r, uint16_t color) {
        for (int y = -r; y <= r; ++y)
            for (int x = -r; x <= r; ++x)
                if (x * x + y * y <= r * r) PutPixel(cx + x, cy + y, color);
    }

    void FillEllipse(int cx, int cy, int rx, int ry, uint16_t color) {
        const int rr = rx * rx * ry * ry;
        for (int y = -ry; y <= ry; ++y)
            for (int x = -rx; x <= rx; ++x)
                if (x * x * ry * ry + y * y * rx * rx <= rr) PutPixel(cx + x, cy + y, color);
    }
    void Ring(int cx, int cy, int r, int thickness, uint16_t color) {
        const int inner = (r - thickness) * (r - thickness);
        const int outer = r * r;
        for (int y = -r; y <= r; ++y)
            for (int x = -r; x <= r; ++x) {
                const int d = x * x + y * y;
                if (d <= outer && d >= inner) PutPixel(cx + x, cy + y, color);
            }
    }

    void DrawDotEyes(uint16_t color) {
        FillCircle(76, 50, 7, color);
        FillCircle(164, 50, 7, color);
    }

    void DrawZ(int x, int y, int scale, uint16_t color) {
        const int thick = 2 * scale;
        const int side = 10 * scale;
        FillRect(x, y, side, thick, color);
        for (int i = 0; i < side - thick; ++i)
            FillRect(x + side - thick - i, y + thick + i, thick, thick, color);
        FillRect(x, y + side, side, thick, color);
    }

    void RenderUi(DeviceUiState state, uint32_t tick) {
        constexpr uint16_t ink = rgb565::kWhite;
        constexpr uint16_t bg = rgb565::kBlack;
        for (int i = 0; i < DISPLAY_WIDTH * DISPLAY_HEIGHT; ++i) frame_[i] = bg;
        const int phase = tick % 12;
        const int breathe = phase <= 6 ? phase : 12 - phase;

        switch (state) {
        case DeviceUiState::Boot:
            DrawDotEyes(ink);
            FillRect(109, 82, 22, 5, ink);
            Ring(120, 65, 35 + breathe, 3, ink);
            break;

        case DeviceUiState::Idle:
            // Relaxed, widely spaced sleeping eyes and gently rising Zs.
            FillRect(58, 52, 36, 5, ink);
            FillRect(146, 52, 36, 5, ink);
            FillRect(110, 84, 20, 4, ink);
            if (phase >= 2) DrawZ(174, 33 - breathe, 1, ink);
            if (phase >= 5) DrawZ(193, 19 - breathe, 1, ink);
            if (phase >= 8) DrawZ(211, 5, 1, ink);
            break;

        case DeviceUiState::Listening:
            DrawDotEyes(ink);
            FillCircle(120, 84, 6 + breathe / 2, ink);
            Ring(120, 84, 17 + breathe * 2, 3, ink);
            break;

        case DeviceUiState::Uploading:
            DrawDotEyes(ink);
            FillRect(116, 72 - breathe, 8, 25, ink);
            FillRect(105, 72 - breathe, 30, 6, ink);
            FillRect(99, 101, 42, 4, ink);
            break;

        case DeviceUiState::Thinking:
            DrawDotEyes(ink);
            FillCircle(105, 87, 4, ink);
            FillCircle(122, 84 - breathe / 2, 6, ink);
            FillCircle(143, 78 - breathe, 8, ink);
            break;

        case DeviceUiState::Speaking:
            DrawDotEyes(ink);
            FillEllipse(120, 85, 12 + breathe * 2, 5 + breathe, ink);
            break;

        case DeviceUiState::Reminder:
            DrawDotEyes(ink);
            FillCircle(120, 88, 7, ink);
            FillRect(116, 65 - breathe, 8, 17, ink);
            FillCircle(120, 58 - breathe, 5, ink);
            break;

        case DeviceUiState::FamilyMessage:
            DrawDotEyes(ink);
            FillCircle(108, 82, 11 + breathe / 3, ink);
            FillCircle(132, 82, 11 + breathe / 3, ink);
            for (int y = 0; y < 22; ++y)
                FillRect(97 + y, 82 + y, 46 - 2 * y, 1, ink);
            break;

        case DeviceUiState::Offline:
            FillRect(58, 52, 36, 4, ink);
            FillRect(146, 52, 36, 4, ink);
            FillRect(105, 88, 30, 4, ink);
            FillRect(116, 78, 8, 4, ink);
            break;

        case DeviceUiState::Error:
            for (int i = 0; i < 18; ++i) {
                FillRect(61 + i, 42 + i, 4, 4, ink);
                FillRect(79 - i, 42 + i, 4, 4, ink);
                FillRect(149 + i, 42 + i, 4, 4, ink);
                FillRect(167 - i, 42 + i, 4, 4, ink);
            }
            Ring(120, 89, 10 + breathe / 2, 3, ink);
            break;

        case DeviceUiState::LowBattery:
            DrawDotEyes(ink);
            FillRect(101, 79, 38, 20, ink);
            FillRect(105, 83, 27, 12, bg);
            FillRect(139, 85, 5, 8, ink);
            FillRect(108, 86, 7 + breathe * 3, 6, ink);
            break;
        }
    }
    bool DrawUiFrame(DeviceUiState state, uint32_t tick) {
        RenderUi(state, tick);
        const esp_err_t err = panel_.DrawRgb565(frame_, DISPLAY_WIDTH, DISPLAY_HEIGHT);
        if (err != ESP_OK) ESP_LOGE(TAG, "UI frame failed: %s", esp_err_to_name(err));
        return err == ESP_OK;
    }

    void UiLoop() {
        panel_.DisplayOn();
        panel_.SetBrightness(0xFF);
        uint32_t tick = 0;
        for (int i = 0; i < 10; ++i) {
            if (!DrawUiFrame(DeviceUiState::Boot, tick++)) break;
            vTaskDelay(pdMS_TO_TICKS(150));
        }
        if (base_ui_state_.load(std::memory_order_acquire) == DeviceUiState::Boot) {
            SetUiState(agent_link_state() == AGENT_STATE_READY ?
                       DeviceUiState::Idle : DeviceUiState::Offline);
        }
        ESP_LOGI(TAG, "UI boot animation complete");
        while (true) {
            DrawUiFrame(ui_state_.load(std::memory_order_acquire), tick++);
            vTaskDelay(pdMS_TO_TICKS(150));
        }
    }    void InitCodec() {
        EsCodecConfig cc = {};
        cc.i2c_port    = I2C_NUM_0;
        cc.pin_sda     = AUDIO_I2C_SDA;
        cc.pin_scl     = AUDIO_I2C_SCL;
        cc.pin_mclk    = AUDIO_I2S_MCLK;
        cc.pin_bclk    = AUDIO_I2S_BCLK;
        cc.pin_ws      = AUDIO_I2S_WS;
        cc.pin_din     = AUDIO_I2S_DIN;
        cc.pin_dout    = AUDIO_I2S_DOUT;
        cc.pin_pa_en   = AUDIO_PA_EN;
        cc.es7210_addr = ES7210_ADDR;
        cc.es8311_addr = ES8311_ADDR;
        cc.sample_rate = AUDIO_SAMPLE_RATE;
        cc.mic_gain    = 30;
        cc.out_volume  = 80;
        if (codec_.Init(cc) != ESP_OK) { ESP_LOGE(TAG, "codec init failed"); return; }
        codec_ok_ = true;

        play_storage_ = static_cast<uint8_t*>(heap_caps_malloc(kPlayBufBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        play_stream_struct_ = static_cast<StaticStreamBuffer_t*>(
            heap_caps_malloc(sizeof(StaticStreamBuffer_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
        if (!play_storage_ || !play_stream_struct_) {
            ESP_LOGE(TAG, "play buffer allocation failed");
            return;
        }
        play_buf_ = xStreamBufferCreateStatic(kPlayBufBytes, 1, play_storage_, play_stream_struct_);
        if (!play_buf_) { ESP_LOGE(TAG, "play stream creation failed"); return; }
        xTaskCreate(&RoRoLeeS3Board::PlayTaskEntry, "spk_play", 4096, this, 5, &play_task_);
    }

    static void PlayTaskEntry(void* arg) { static_cast<RoRoLeeS3Board*>(arg)->PlayLoop(); }

    // Single speaker owner. It never drains PCM while the microphone is active,
    // preventing acoustic feedback and concurrent codec ownership.
    void PlayLoop() {
        int16_t buf[256];
        while (true) {
            if (capture_active_.load(std::memory_order_acquire)) {
                vTaskDelay(pdMS_TO_TICKS(10));
                continue;
            }

            const size_t n = xStreamBufferReceive(play_buf_, buf, sizeof(buf), pdMS_TO_TICKS(20));
            if (n >= sizeof(int16_t)) {
                const esp_err_t err = codec_.WritePcm(buf, n / sizeof(int16_t));
                if (err != ESP_OK) ESP_LOGE(TAG, "speaker write failed: %s", esp_err_to_name(err));
            }

            if (!playback_active_.load(std::memory_order_acquire) ||
                xStreamBufferBytesAvailable(play_buf_) != 0) {
                continue;
            }

            const uint32_t now = static_cast<uint32_t>(xTaskGetTickCount());
            const uint32_t last = last_audio_rx_tick_.load(std::memory_order_acquire);
            const uint32_t quiet_ms = pdTICKS_TO_MS(now - last);
            const bool explicit_end = audio_end_pending_.load(std::memory_order_acquire);
            if ((explicit_end && quiet_ms >= 120) || (!explicit_end && quiet_ms >= 800)) {
                audio_end_pending_.store(false, std::memory_order_release);
                playback_active_.store(false, std::memory_order_release);
                SetUiState(agent_link_state() == AGENT_STATE_READY ?
                           DeviceUiState::Idle : DeviceUiState::Offline);
                ESP_LOGI(TAG, "speaker drained; playback complete (explicit_end=%d)",
                         static_cast<int>(explicit_end));
            }
        }
    }

    // ── Fuel gauge (BQ27220) ──
    void InitFuelGauge() {
        if (!codec_ok_) { ESP_LOGW(TAG, "codec/I2C not ready; skipping fuel-gauge init"); return; }
        if (gauge_.Init(I2C_NUM_0, BQ27220_ADDR) != ESP_OK) {
            ESP_LOGW(TAG, "BQ27220 init failed, battery unavailable (GetBatteryLevel returns -1)");
            return;
        }
        gauge_ok_ = true;
        ESP_LOGI(TAG, "fuel gauge ready: SOC=%d%% charging=%d", gauge_.Soc(), (int)gauge_.IsCharging());
    }

    // GPIO0 (BOOT) is push-to-talk; GPIO39/40 are local volume controls.
    void InitButton() {
        gpio_config_t c = {};
        c.pin_bit_mask = (1ULL << BUTTON_BOOT_PIN) |
                         (1ULL << BUTTON_VOL_UP_PIN) |
                         (1ULL << BUTTON_VOL_DOWN_PIN);
        c.mode         = GPIO_MODE_INPUT;
        c.pull_up_en   = GPIO_PULLUP_ENABLE;    // keys ground when pressed -> high idle, low when pressed
        c.pull_down_en = GPIO_PULLDOWN_DISABLE;
        c.intr_type    = GPIO_INTR_DISABLE;     // polling + debounce, simple and reliable
        gpio_config(&c);
        if (!codec_ok_) { ESP_LOGW(TAG, "codec not ready; PTT task not started"); return; }
        xTaskCreate(&RoRoLeeS3Board::PttTaskEntry, "ptt_voice", 4096, this, 5, &ptt_task_);
        xTaskCreate(&RoRoLeeS3Board::VolumeTaskEntry, "volume_keys", 2048, this, 4, &volume_task_);
        ESP_LOGI(TAG, "keys ready: PTT GPIO%d, volume GPIO%d/%d", (int)BUTTON_BOOT_PIN,
                 (int)BUTTON_VOL_UP_PIN, (int)BUTTON_VOL_DOWN_PIN);
    }

    static void PttTaskEntry(void* arg) { static_cast<RoRoLeeS3Board*>(arg)->PttLoop(); }
    static void VolumeTaskEntry(void* arg) { static_cast<RoRoLeeS3Board*>(arg)->VolumeLoop(); }

    void RunLocalDemo() {
        ESP_LOGI(TAG, "local state/haptic demo started");
        const DeviceUiState states[] = {DeviceUiState::Idle, DeviceUiState::Listening,
            DeviceUiState::Uploading, DeviceUiState::Thinking, DeviceUiState::Speaking,
            DeviceUiState::Reminder, DeviceUiState::FamilyMessage, DeviceUiState::Offline,
            DeviceUiState::Error, DeviceUiState::LowBattery};
        for (DeviceUiState state : states) {
            SetUiState(state);
            if (state == DeviceUiState::Reminder) PlayHapticPattern(HapticPattern::Reminder);
            if (state == DeviceUiState::FamilyMessage) PlayHapticPattern(HapticPattern::FamilyMessage);
            if (state == DeviceUiState::Error) PlayHapticPattern(HapticPattern::Error);
            vTaskDelay(pdMS_TO_TICKS(1200));
        }
        SetUiState(agent_link_state() == AGENT_STATE_READY ? DeviceUiState::Idle : DeviceUiState::Offline);
        ESP_LOGI(TAG, "local state/haptic demo complete");
    }

    void VolumeLoop() {
        while (true) {
            if (gpio_get_level(BUTTON_VOL_UP_PIN) == 0) {
                vTaskDelay(pdMS_TO_TICKS(30));
                if (gpio_get_level(BUTTON_VOL_UP_PIN) == 0) {
                    AdjustVolume(+10);
                    while (gpio_get_level(BUTTON_VOL_UP_PIN) == 0) vTaskDelay(pdMS_TO_TICKS(20));
                }
            }
            if (gpio_get_level(BUTTON_VOL_DOWN_PIN) == 0) {
                vTaskDelay(pdMS_TO_TICKS(30));
                if (gpio_get_level(BUTTON_VOL_DOWN_PIN) == 0) {
                    int held_ms = 0;
                    while (gpio_get_level(BUTTON_VOL_DOWN_PIN) == 0 && held_ms < 2000) {
                        vTaskDelay(pdMS_TO_TICKS(50));
                        held_ms += 50;
                    }
                    if (held_ms >= 2000) {
                        RunLocalDemo();
                    } else {
                        AdjustVolume(-10);
                    }
                    while (gpio_get_level(BUTTON_VOL_DOWN_PIN) == 0)
                        vTaskDelay(pdMS_TO_TICKS(20));
                }
            }
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
    void AdjustVolume(int delta) {
        int next = volume_ + delta;
        if (next < 0) next = 0;
        if (next > 100) next = 100;
        if (codec_.SetVolume(static_cast<uint8_t>(next)) != ESP_OK) return;
        volume_ = next;
        ESP_LOGI(TAG, "speaker volume %d%%", volume_);
    }

    void SetVolumePercent(uint8_t percent) override {
        const uint8_t bounded = percent > 100 ? 100 : percent;
        if (codec_.SetVolume(bounded) != ESP_OK) return;
        volume_ = bounded;
        ESP_LOGI(TAG, "speaker volume set to %d%%", volume_);
    }

    // One microphone owner handles both local BOOT PTT and BLE 0x3C/0x3D capture.
    // This prevents transport callbacks and the button task from opening/closing the codec concurrently.
    void PttLoop() {
        enum class CaptureSource : uint8_t { None, ButtonVoice, RemoteAsr };
        constexpr size_t kFrame = AUDIO_SAMPLE_RATE / 50;  // 20 ms @ 16 kHz
        int16_t buf[kFrame];
        CaptureSource source = CaptureSource::None;
        TickType_t started_tick = 0;
        uint32_t frames = 0;
        uint32_t tx_errors = 0;

        while (true) {
            const bool button_pressed = gpio_get_level(BUTTON_BOOT_PIN) == 0;
            const bool remote_requested = remote_capture_requested_.load(std::memory_order_acquire);

            if (source == CaptureSource::None) {
                if (!button_pressed && !remote_requested) {
                    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(20));
                    continue;
                }

                CaptureSource requested = remote_requested ? CaptureSource::RemoteAsr
                                                            : CaptureSource::ButtonVoice;
                if (requested == CaptureSource::ButtonVoice) {
                    vTaskDelay(pdMS_TO_TICKS(20));
                    if (gpio_get_level(BUTTON_BOOT_PIN) != 0) continue;
                }

                if (playback_active_.load(std::memory_order_acquire)) {
                    ESP_LOGI(TAG, "%s capture ignored while TTS is playing",
                             requested == CaptureSource::RemoteAsr ? "BLE" : "BOOT");
                    if (requested == CaptureSource::RemoteAsr) {
                        remote_capture_requested_.store(false, std::memory_order_release);
                    } else {
                        while (gpio_get_level(BUTTON_BOOT_PIN) == 0)
                            vTaskDelay(pdMS_TO_TICKS(20));
                    }
                    continue;
                }

                if (agent_link_state() != AGENT_STATE_READY) {
                    ESP_LOGW(TAG, "%s capture requested but App is not READY",
                             requested == CaptureSource::RemoteAsr ? "BLE" : "BOOT");
                    SetUiState(DeviceUiState::Offline);
                    PlayHapticPattern(HapticPattern::Error);
                    if (requested == CaptureSource::RemoteAsr) {
                        remote_capture_requested_.store(false, std::memory_order_release);
                    } else {
                        while (gpio_get_level(BUTTON_BOOT_PIN) == 0)
                            vTaskDelay(pdMS_TO_TICKS(50));
                    }
                    continue;
                }

                if (requested == CaptureSource::RemoteAsr) {
                    const esp_err_t asr_err = agent_link_asr_start("rorolee-mic");
                    if (asr_err != ESP_OK) {
                        ESP_LOGE(TAG, "BLE ASR stream start failed: %s", esp_err_to_name(asr_err));
                        remote_capture_requested_.store(false, std::memory_order_release);
                        SetUiState(DeviceUiState::Error);
                        continue;
                    }
                }

                const esp_err_t mic_err = codec_.StartMic();
                if (mic_err != ESP_OK) {
                    ESP_LOGE(TAG, "mic start failed: %s", esp_err_to_name(mic_err));
                    if (requested == CaptureSource::RemoteAsr) {
                        (void)agent_link_asr_end(false);
                        remote_capture_requested_.store(false, std::memory_order_release);
                    } else {
                        while (gpio_get_level(BUTTON_BOOT_PIN) == 0)
                            vTaskDelay(pdMS_TO_TICKS(50));
                    }
                    SetUiState(DeviceUiState::Error);
                    continue;
                }

                source = requested;
                started_tick = xTaskGetTickCount();
                frames = 0;
                tx_errors = 0;
                capture_active_.store(true, std::memory_order_release);
                SetUiState(DeviceUiState::Listening);
                ESP_LOGI(TAG, "%s capture started",
                         source == CaptureSource::RemoteAsr ? "BLE ASR" : "BOOT PTT");
                continue;
            }

            bool complete = agent_link_state() == AGENT_STATE_READY;
            bool should_stop = !complete ||
                playback_preempt_requested_.load(std::memory_order_acquire);
            size_t got = 0;
            const esp_err_t read_err = codec_.ReadPcm(buf, kFrame, &got);
            if (read_err == ESP_OK && got > 0 && complete) {
                if (frames == 0) {
                    int32_t peak = 0;
                    for (size_t i = 0; i < got; ++i) {
                        int32_t sample = buf[i];
                        if (sample < 0) sample = -sample;
                        if (sample > peak) peak = sample;
                    }
                    ESP_LOGI(TAG, "first mic frame: samples=%u peak=%ld",
                             static_cast<unsigned>(got), static_cast<long>(peak));
                }
                const esp_err_t tx_err = source == CaptureSource::RemoteAsr
                    ? agent_link_asr_push(reinterpret_cast<const uint8_t*>(buf), got * sizeof(int16_t))
                    : agent_link_push_voice(reinterpret_cast<const uint8_t*>(buf), got * sizeof(int16_t));
                ++frames;
                if (tx_err != ESP_OK) {
                    ++tx_errors;
                    if (tx_errors == 1 || tx_errors % 25 == 0) {
                        ESP_LOGW(TAG, "voice transport error #%u: %s",
                                 static_cast<unsigned>(tx_errors), esp_err_to_name(tx_err));
                    }
                }
            } else if (read_err != ESP_OK) {
                ESP_LOGE(TAG, "mic read failed: %s", esp_err_to_name(read_err));
                complete = false;
                should_stop = true;
            }

            if (source == CaptureSource::ButtonVoice) {
                if (gpio_get_level(BUTTON_BOOT_PIN) != 0) {
                    vTaskDelay(pdMS_TO_TICKS(20));
                    should_stop = gpio_get_level(BUTTON_BOOT_PIN) != 0;
                }
            } else {
                should_stop = should_stop ||
                    !remote_capture_requested_.load(std::memory_order_acquire);
                const uint32_t max_ms = remote_capture_max_ms_.load(std::memory_order_acquire);
                if (max_ms > 0 && pdTICKS_TO_MS(xTaskGetTickCount() - started_tick) >= max_ms) {
                    ESP_LOGI(TAG, "BLE capture reached max_ms=%u", static_cast<unsigned>(max_ms));
                    remote_capture_requested_.store(false, std::memory_order_release);
                    should_stop = true;
                }
            }

            if (!should_stop) continue;

            const esp_err_t end_err = source == CaptureSource::RemoteAsr
                ? agent_link_asr_end(complete)
                : agent_link_voice_end();
            const esp_err_t stop_err = codec_.StopMic();
            remote_capture_requested_.store(false, std::memory_order_release);
            capture_active_.store(false, std::memory_order_release);
            playback_preempt_requested_.store(false, std::memory_order_release);
            ESP_LOGI(TAG, "%s capture ended: frames=%u tx_errors=%u end=%s mic_stop=%s",
                     source == CaptureSource::RemoteAsr ? "BLE ASR" : "BOOT PTT",
                     static_cast<unsigned>(frames), static_cast<unsigned>(tx_errors),
                     esp_err_to_name(end_err), esp_err_to_name(stop_err));
            source = CaptureSource::None;

            if (complete && playback_active_.load(std::memory_order_acquire)) {
                ResolveUiState();
            } else if (complete) {
                SetUiState(DeviceUiState::Uploading);
                PlayHapticPattern(HapticPattern::Success);
                vTaskDelay(pdMS_TO_TICKS(300));
                SetUiState(DeviceUiState::Thinking);
            } else {
                SetUiState(DeviceUiState::Offline);
            }
        }
    }

    // Power on the peripheral rail.
    void PowerOnRail() {
        gpio_config_t cfg = {};
        cfg.pin_bit_mask = 1ULL << POWER_CTRL_PIN;
        cfg.mode         = GPIO_MODE_OUTPUT;
        if (gpio_config(&cfg) != ESP_OK) { ESP_LOGE(TAG, "power gpio cfg failed"); return; }
        gpio_set_level(POWER_CTRL_PIN, POWER_CTRL_ACTIVE_HIGH ? 1 : 0);  // active low
        (void)gpio_hold_en(POWER_CTRL_PIN);
        vTaskDelay(pdMS_TO_TICKS(50));   // wait for the supply to settle
        ESP_LOGI(TAG, "peripheral power on (GPIO%d)", (int)POWER_CTRL_PIN);
    }
    // Initialize the display.
    void InitDisplay() {
        Sh8501Config c = {};
        c.spi_host = DISPLAY_SPI_HOST;
        c.pin_sck  = DISPLAY_SCK_PIN;
        c.pin_mosi = DISPLAY_MOSI_PIN;
        c.pin_cs   = DISPLAY_CS_PIN;
        c.pin_dc   = DISPLAY_DC_PIN;
        c.pin_rst  = DISPLAY_RST_PIN;
        c.width    = DISPLAY_WIDTH;
        c.height   = DISPLAY_HEIGHT;
        c.pclk_hz  = DISPLAY_SPI_CLK_HZ;
        c.spi_mode = DISPLAY_SPI_MODE;
        if (panel_.Init(c) != ESP_OK) {
            ESP_LOGE(TAG, "display init failed");
            return;
        }
        // Boot self-test: red/green/blue/white in turn, to eyeball that the panel lights up with no dead pixels or color cast.
        const uint16_t seq[] = { rgb565::kRed, rgb565::kGreen, rgb565::kBlue, rgb565::kWhite };
        for (uint16_t color : seq) {
            panel_.FillSolid(color);
            vTaskDelay(pdMS_TO_TICKS(400));
        }
        panel_.DisplayOn();
        panel_.SetBrightness(0xFF);
        panel_.FillSolid(rgb565::kWhite);   // regression target: remain visibly white
        ESP_LOGI(TAG, "display lit + self-test done");
    }

    static constexpr size_t kPlayBufBytes = 256 * 1024;  // 8 s PCM16/16k mono, stored in PSRAM

    Sh8501Panel         panel_;
    EsCodec             codec_;
    bool                codec_ok_  = false;
    Bq27220             gauge_;
    bool                gauge_ok_  = false;
    TaskHandle_t        ptt_task_  = nullptr;
    TaskHandle_t        volume_task_ = nullptr;
    StreamBufferHandle_t play_buf_ = nullptr;
    uint8_t*            play_storage_ = nullptr;
    StaticStreamBuffer_t* play_stream_struct_ = nullptr;
    TaskHandle_t        play_task_ = nullptr;
    TimerHandle_t       haptic_timer_ = nullptr;
    QueueHandle_t       haptic_queue_ = nullptr;
    TaskHandle_t        haptic_task_ = nullptr;
    TaskHandle_t        ui_task_ = nullptr;
    uint16_t*           frame_ = nullptr;
    std::atomic<DeviceUiState> ui_state_{DeviceUiState::Boot};
    std::atomic<DeviceUiState> base_ui_state_{DeviceUiState::Boot};
    std::atomic<bool>    capture_active_{false};
    std::atomic<bool>    remote_capture_requested_{false};
    std::atomic<uint32_t> remote_capture_max_ms_{0};
    std::atomic<bool>    playback_active_{false};
    std::atomic<bool>    playback_preempt_requested_{false};
    std::atomic<uint32_t> last_audio_rx_tick_{0};
    std::atomic<bool>    audio_end_pending_{false};
    int                 volume_ = 80;
};

DECLARE_BOARD(RoRoLeeS3Board);
