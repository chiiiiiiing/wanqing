# 晚晴 — BLE 下行/上行消息协议 v1.0

> **适用范围**：App ↔ ESP32 设备端（基于 agent_link SDK）
> **传输层**：BLE GATT + L2CAP CoC
> **最后更新**：2026-08-27（§6 修正：BOOT 对话语音通道由 `agent_link_asr_push` → `agent_link_push_voice`）

---

## 1. 下行命令（App → 设备）

### 1.1 命令 ID

| 字段 | 值 |
|------|-----|
| Command ID | `0x70` |
| Message Type | `0x01` (Command) |
| 传输通道 | GATT Service `0xFFC0`, Characteristic `0xFFC1` (WRITE) |
| ACK | SDK 自动回复空 ACK（走 `on_custom` 回调） |

**无冲突确认**：已排查 agent_link SDK 占用的 command_id（0x03, 0x05, 0x33–0x36, 0x3C, 0x3D），0x70 未被使用。

### 1.2 Payload 格式

- 编码：UTF-8 JSON，不带 BOM
- 最大长度：4096 字节

> **帧分片说明**：GATT 单次写入缓冲区为 512 字节，扣除 6 字节帧头后可用 payload = 506 字节。超过 506 字节的 JSON 需要 App 端分片写入，设备端做帧重组。设备端 0xFFC1 写入回调需支持多帧拼接。

### 1.3 消息类型定义

#### (a) `ai_reply` — AI 文本回复

```json
{
  "type": "ai_reply",
  "text": "今天天气不错，适合出去走走。",
  "tts": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 固定 `"ai_reply"` |
| text | string | 是 | Agent 回复文本，设备可直接显示 |
| tts | bool | 是 | `true` = L2CAP 随后下发 TTS 音频；`false` = 仅文本 |

#### (b) `reminder` — 定时提醒

```json
{
  "type": "reminder",
  "id": "r001",
  "title": "吃药提醒",
  "text": "请服用降压药，饭后半小时。",
  "importance": "important"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 固定 `"reminder"` |
| id | string | 是 | 提醒唯一 ID，用于完成/延迟操作 |
| title | string | 是 | 提醒标题（短文本，适合屏幕显示） |
| text | string | 是 | 提醒详情，同时作为 TTS 文本 |
| importance | string | 是 | `"normal"` 普通 / `"important"` 重要（设备应加强反馈：长振动 + 重复 TTS） |

**始终包含 TTS 音频。**

#### (c) `family_message` — 家人消息

```json
{
  "type": "family_message",
  "sender": "女儿",
  "text": "爸，晚上8点我给您打电话，别忘了接。"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 固定 `"family_message"` |
| sender | string | 是 | 发送者称呼 |
| text | string | 是 | 消息内容，同时作为 TTS 文本 |

**始终包含 TTS 音频。**

#### (d) `device_command` — 设备控制

```json
{
  "type": "device_command",
  "action": "set_volume",
  "value": 80
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 固定 `"device_command"` |
| action | string | 是 | 操作类型（见下表） |
| value | any | 否 | 操作参数 |

**action 枚举**：

| action | value 类型 | 说明 |
|--------|-----------|------|
| `set_volume` | int (0–100) | 设置音量 |
| `set_brightness` | int (0–100) | 设置屏幕亮度 |
| `reboot` | — | 重启设备 |

**不包含 TTS。**

#### (e) `error` — 错误通知

```json
{
  "type": "error",
  "code": "NETWORK_ERROR",
  "message": "网络不太好，请稍后再试。"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 固定 `"error"` |
| code | string | 是 | 错误码（见下表） |
| message | string | 否 | 人类可读错误描述，可作为 TTS 文本 |

**code 枚举**：

| code | 说明 |
|------|------|
| `NETWORK_ERROR` | 云端连接失败 |
| `AGENT_TIMEOUT` | Agent 响应超时 |
| `ASR_ERROR` | 语音识别失败 |
| `TTS_ERROR` | TTS 合成失败 |

**可选包含 TTS**（当 `message` 非空时）。

---

## 2. TTS 音频通道

| 参数 | 值 |
|------|-----|
| 传输方式 | BLE L2CAP CoC |
| PSM | `0x0081` |
| 音频格式 | 16 kHz, 16-bit, mono PCM |
| MTU | 4096 字节 |

与 agent_link SDK 现有 TTS 通道一致，设备端通过 `on_audio_out` 回调接收音频数据。

---

## 3. 发送顺序与时序

```
 ┌──────────┐         ┌──────────┐         ┌──────────┐
 │   App    │         │  BLE链路  │         │  ESP32   │
 └────┬─────┘         └────┬─────┘         └────┬─────┘
      │                    │                     │
      │ ① cmd=0x70 JSON    │                     │
      │───GATT 0xFFC1─────>│────────────────────>│ 解析 JSON, 显示文本
      │                    │                     │
      │ ② TTS PCM 流       │                     │
      │═══L2CAP 0x0081════>│════════════════════>│ on_audio_out 播放
      │   (分片传输)        │                     │
      │                    │                     │
      │                    │  ③ 播放结束          │
      │                    │<────────────────────│ on_audio_end
      │ ④ VoiceReply       │                     │
      │<───cmd=0x05────────│<────────────────────│ status=3
      │   status=3         │                     │
      │                    │                     │
```

**顺序约定**：
1. JSON 命令先到（GATT）
2. TTS 音频后到（L2CAP）
3. `on_audio_end` 标记音频播放结束
4. 设备回复 `VoiceReply (cmd=0x05, status=3)` 通知 App

**配对规则**：同一条 0x70 命令的 JSON 和 TTS 音频按到达顺序配对，无需额外关联字段。

---

## 4. TTS 包含规则总表

| 消息类型 | 是否含 TTS | TTS 内容来源 |
|---------|-----------|-------------|
| `ai_reply` | 由 `tts` 字段决定 | `text` |
| `reminder` | **始终包含** | `text` |
| `family_message` | **始终包含** | `text` |
| `device_command` | 不包含 | — |
| `error` | 可选（message 非空时） | `message` |

---

## 5. 上行事件（设备 → App）

### 5.1 事件 ID

使用 `AGENT_EVT_CUSTOM (0x64)` 事件类型，通过 `agent_link_push_event()` 发送。

传输通道：GATT Characteristic `0xFFC4` (NOTIFY)。

### 5.2 事件格式

Payload 为 UTF-8 JSON，不含 BOM。

#### 语音交互请求

```json
{"action": "voice_input", "session_id": "s001"}
```

设备检测到按钮按下或唤醒词后发送，App 开始 ASR 录音流程。

#### 查询今日提醒

```json
{"action": "query_reminders", "date": "2026-08-27"}
```

#### 联系家人

```json
{"action": "contact_family", "target": "女儿", "message": "帮我给女儿发消息"}
```

#### 按钮事件

```json
{"action": "button", "button_id": 0, "action_type": "short_press"}
```

`action_type` 枚举：`short_press` / `long_press` / `double_press`

#### 唤醒词检测

```json
{"action": "wakeup", "keyword": "小晚晴"}
```

#### 任务操作

```json
{"action": "complete_task", "task_id": "r001"}
{"action": "delay_task", "task_id": "r001", "delay_minutes": 10}
```

---

## 6. App → 云端语音流程

> **通道语义区分**（参见 agent_link SDK）：
>
> | 通道 | API | BLE 传输 | 事件 ID | 用途 |
> |------|-----|----------|---------|------|
> | VoiceChunk（实时对话） | `agent_link_push_voice()` / `voice_end()` | GATT Notify `0xFFA1` | `0x40` | 实时 Agent 对话：设备端采集 PCM → App 识别/提交 → Agent 回复 |
> | ASR/Recording（录音） | `agent_link_asr_start()` / `asr_push()` / `asr_end()` | L2CAP CoC `PSM 0x0081` | `0x52` / `0x53` | 会议录音转写：长时间录音流，App 端转写/存档 |
>
> 晚晴 Agent 对话场景使用 **VoiceChunk 通道**（`push_voice`），不使用 ASR/Recording 通道。

```
设备端                    App 端                     Agent Stack 云端
  │                        │                              │
  │ button/wakeup 事件     │                              │
  │────0x64 JSON──────────>│                              │
  │   (GATT 0xFFC4)        │                              │
  │                        │                              │
  │ Voice 音频流           │                              │
  │═══GATT Notify═════════>│ ASR 识别 → 文本              │
  │   0xFFA1 (0x40)        │                              │
  │ push_voice()/voice_end │                              │
  │                        │                              │
  │                        │ 提交 Turn (text)             │
  │                        │─────────────────────────────>│
  │                        │                              │
  │                        │ Agent 回复 (NDJSON 流)       │
  │                        │<─────────────────────────────│
  │                        │                              │
  │ ① cmd=0x70 JSON       │                              │
  │<──GATT 0xFFC1─────────│                              │
  │                        │                              │
  │ ② TTS PCM 流          │                              │
  │<══L2CAP 0x0081════════│                              │
  │                        │                              │
  │ ③ VoiceReply 0x05     │                              │
  │───GATT 0xFFC1────────>│                              │
```

### 上行音频帧格式（VoiceChunk 0x40）

每帧由 6 字节公共帧头 + VoiceChunk 专有字段 + PCM 数据组成：

```
┌─────────┬──────────┬──────────┬────────────┬────────────┬─────────┬─────────┐
│ ver (1) │ type (1) │ cmd (1)  │  seq (1)   │  len (2)   │sess(4)  │seq (4)  │
│  0x01   │   0x03   │   0x40   │   0x00     │ payload len│session_id│sequence │
└─────────┴──────────┴──────────┴────────────┴────────────┴─────────┴─────────┘
┌──────────┬──────────────┐
│flags (1) │  PCM 数据    │
│          │ (≤205 bytes) │
└──────────┴──────────────┘
```

- `session_id` (4B, LE)：语音会话编号，首帧自动分配
- `sequence` (4B, LE)：帧序号，从 0 递增
- `flags` (1B)：`0x01` = 末帧（等同于 `voice_end()`）
- PCM：16kHz / 16bit / mono，单帧 ≤ 205 字节（220 - 15 帧开销），偶数对齐

### 会话 ID 管理

- Agent Stack 的 session ID 由 App 端维护
- 设备端无需感知 session ID，仅通过按钮/唤醒词触发交互
- App 将设备事件映射到对应的 Agent Stack session

### 异常重试规则

| 场景 | 重试策略 |
|------|---------|
| BLE 断连 | 自动重连，重连后恢复 session |
| ASR 失败 | 向设备发送 `{"type":"error","code":"ASR_ERROR"}` |
| Agent 超时 (>30s) | 向设备发送 `{"type":"error","code":"AGENT_TIMEOUT"}` |
| 云端不可达 | 3 次重试后发送 `{"type":"error","code":"NETWORK_ERROR"}` |

---

## 7. 真实测试数据

以下每条消息均通过 Agent Stack 晚晴实际生成，可直接用于联调：

### 下行测试

```json
{"type":"ai_reply","text":"今天天气不错，适合出去走走。","tts":true}
```

```json
{"type":"reminder","id":"r001","title":"吃药提醒","text":"请服用降压药，饭后半小时。","importance":"important"}
```

```json
{"type":"family_message","sender":"女儿","text":"爸，晚上8点我给您打电话，别忘了接。"}
```

```json
{"type":"device_command","action":"set_volume","value":80}
```

```json
{"type":"error","code":"NETWORK_ERROR","message":"网络不太好，请稍后再试。"}
```

### 上行测试

```json
{"action":"button","button_id":0,"action_type":"short_press"}
```

```json
{"action":"query_reminders","date":"2026-08-27"}
```

```json
{"action":"contact_family","target":"女儿","message":"帮我给女儿发消息"}
```

---

## 8. 帧格式速查

### 控制帧（GATT 0xFFC1 / 0xFFC4）

```
┌─────────┬──────────┬────────────┬──────────┬─────────────┬─────────┐
│ ver (1) │ type (1) │  cmd (1)   │ seq (1)  │ len (2, LE) │ payload │
│  0x01   │ 0x01/0x03│   0x70     │   0x00   │  JSON len   │ UTF-8   │
└─────────┴──────────┴────────────┴──────────┴─────────────┴─────────┘
```

- `type`: `0x01` = Command（App→设备），`0x03` = Event（设备→App）
- `cmd`: `0x70` = 下行 JSON 消息，`0x64` = 上行自定义事件
- `seq`: 请求-响应配对序号（fire-and-forget 时为 0x00）
- `len`: payload 长度，小端序

---

## 附录 A：已占用 Command ID 清单

| ID | 方向 | SDK 内部处理 |
|----|------|-------------|
| 0x03 | App→设备 | GetChargingStatus |
| 0x05 | App→设备 | VoiceReply（TTS 播放状态确认） |
| 0x18 | 设备→App | IoManifest（I/O 清单上报） |
| 0x33 | App→设备 | IoActuate |
| 0x34 | App→设备 | GetIoManifest |
| 0x35 | App→设备 | GetReading |
| 0x36 | App→设备 | SetReadingConfig |
| 0x3C | App→设备 | StartCapture（开始录音） |
| 0x3D | App→设备 | StopCapture（停止录音） |
| 0x40 | 设备→App | VoiceChunk（实时对话语音分片，GATT Notify `0xFFA1`） |
| 0x52 | 设备→App | StreamStart（录音/ASR 流开始，L2CAP `PSM 0x0081`） |
| 0x53 | 设备→App | StreamEnd（录音/ASR 流结束） |
| 0x54 | 设备→App | ImageStart（图片流开始） |
| 0x55 | 设备→App | ImageEnd（图片流结束） |
| **0x64** | **设备→App** | **AGENT_EVT_CUSTOM（上行自定义事件）** |
| **0x70** | **App→设备** | **下行 JSON 消息（本协议）** |
