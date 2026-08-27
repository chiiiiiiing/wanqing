#include "device_protocol.h"

#include <cstring>
#include <memory>

#include "cJSON.h"
#include "esp_log.h"

#include "board.h"

namespace {
constexpr const char* TAG = "device.protocol";

const char* StringField(const cJSON* root, const char* name, const char* fallback = "") {
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(root, name);
    return cJSON_IsString(item) && item->valuestring ? item->valuestring : fallback;
}
}  // namespace

bool HandleDeviceJson(const uint8_t* payload, size_t len, Board& board) {
    if (!payload || len == 0 || len > 4096) {
        ESP_LOGW(TAG, "invalid JSON payload length: %u", static_cast<unsigned>(len));
        return false;
    }

    std::unique_ptr<char[]> text(new char[len + 1]);
    std::memcpy(text.get(), payload, len);
    text[len] = '\0';
    cJSON* root = cJSON_Parse(text.get());
    if (!root) {
        ESP_LOGW(TAG, "invalid JSON payload");
        return false;
    }

    const char* type = StringField(root, "type");
    bool handled = true;
    if (std::strcmp(type, "ai_reply") == 0) {
        const char* reply = StringField(root, "text");
        const cJSON* tts = cJSON_GetObjectItemCaseSensitive(root, "tts");
        ESP_LOGI(TAG, "AI reply: %s", reply);
        board.ShowText(reply);
        board.SetUiState(cJSON_IsTrue(tts) ? DeviceUiState::Thinking : DeviceUiState::Idle);
    } else if (std::strcmp(type, "reminder") == 0) {
        const char* importance = StringField(root, "importance", "normal");
        ESP_LOGI(TAG, "reminder id=%s title=%s text=%s importance=%s",
                 StringField(root, "id"), StringField(root, "title"),
                 StringField(root, "text"), importance);
        board.SetUiState(DeviceUiState::Reminder);
        const bool important = std::strcmp(importance, "important") == 0 ||
                               std::strcmp(importance, "high") == 0;
        board.PlayHapticPattern(important ? HapticPattern::ImportantReminder : HapticPattern::Reminder);
    } else if (std::strcmp(type, "family_message") == 0) {
        ESP_LOGI(TAG, "family message sender=%s text=%s",
                 StringField(root, "sender"), StringField(root, "text"));
        board.SetUiState(DeviceUiState::FamilyMessage);
        board.PlayHapticPattern(HapticPattern::FamilyMessage);
    } else if (std::strcmp(type, "device_command") == 0) {
        const char* action = StringField(root, "action");
        const cJSON* value = cJSON_GetObjectItemCaseSensitive(root, "value");
        if (std::strcmp(action, "set_volume") == 0 && cJSON_IsNumber(value)) {
            int percent = value->valueint;
            if (percent < 0) percent = 0;
            if (percent > 100) percent = 100;
            board.SetVolumePercent(static_cast<uint8_t>(percent));
        } else {
            ESP_LOGW(TAG, "unsupported device command: %s", action);
            handled = false;
        }
    } else if (std::strcmp(type, "error") == 0) {
        ESP_LOGE(TAG, "App error code=%s message=%s",
                 StringField(root, "code"), StringField(root, "message"));
        board.SetUiState(DeviceUiState::Error);
        board.PlayHapticPattern(HapticPattern::Error);
    } else {
        ESP_LOGW(TAG, "unsupported JSON message type: %s", type);
        handled = false;
    }

    cJSON_Delete(root);
    return handled;
}
