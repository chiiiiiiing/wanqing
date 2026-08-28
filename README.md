# 晚晴 — 老年人的随身 AI 管家

**WanQing · A Wearable AI Butler for the Elderly** — 基于 ESP32-S3 + BLE + ROROLEE App + TiDB Agent Stack 的 Physical AI 闭环。

> 晚晴取自李商隐"天意怜幽草，人间重晚晴"——为老年人做一个听得清、记得住、会提醒的随身管家。

## 赛题交付物索引

| 交付物 | 文件位置 |
|--------|----------|
| **四、一页架构图** | [`wanqing/deliverables/architecture_verified.pdf`](wanqing/deliverables/architecture_verified.pdf)（附可编辑 PPTX 与高清 PNG） |
| **项目展示页** | [wanqing/docs/project_intro.html](wanqing/docs/project_intro.html)（背景、用户场景、Physical AI 闭环与核心体验） |
| **三分钟 Demo 视频** | [`wanqing/deliverables/family_care_demo.mp4`](wanqing/deliverables/family_care_demo.mp4)（家人关注功能演示，69s 中文旁白；构建脚本 `wanqing/deliverables/demo_build/`） |
| **五、代码与运行说明** | 本 README.md |
| **六、Agent Stack 使用说明** | [`wanqing/docs/agent_stack_usage.md`](wanqing/docs/agent_stack_usage.md) |

---

## 1. 项目概述与核心 Physical AI 闭环

老人按一下 BOOT 键说话 → 设备采集语音经 BLE 上行到手机 App → App 通过 roro 中继链路送达 **TiDB Agent Stack** 上的晚晴 Agent → Agent 理解意图后调用 MCP 工具（创建提醒/备忘/查询/完成/延期）→ Agent 决定的回复经原路返回 → 设备屏幕播放表情动画、扬声器播报 TTS、振动马达给出触觉反馈。到点的提醒由 **Scheduler** 准点触发，**reminder-pusher 守护进程**检测到后写入被托管会话的 JSONL，经 roro daemon mirror 协议投给 App、再经 BLE 送达设备（实测 4s 内送达，无需用户语音输入）。

```
┌────────┐  按键/语音  ┌─────────┐  BLE   ┌──────────┐  TCP   ┌───────────────┐
│ 老人   │────────────>│ ESP32-S3 │───────>│ ROROLEE  │───────>│ claude-bridge │
│ (输入) │             │ (设备)    │  GATT/ │ App      │  roro  │ (自研桥接)     │
└────────┘             └─────────┘  L2CAP  └──────────┘  daemon└──────┬────────┘
                           ↑  │                              │
                    TTS/振动/屏幕 │ 语音上行                     ▼
                           │  │                       ┌─────────────────┐
                           │  └──── BLE 0x70 JSON ◄───│ TiDB Agent Stack│
                           └────────── TTS PCM ◄──────│ 晚晴 Agent      │
                                                     │  ├─ MCP 5 工具   │
                                                     │  ├─ Scheduler   │
                                                     │  └─ Session 上下文│
                                                     └────────┬────────┘
                                                              ▼
                                                     ┌─────────────────┐
                                                     │ 自研后端+SQLite  │
                                                     │ 任务/备忘持久化   │
                                                     └─────────────────┘
```

**一页架构图**：[`wanqing/deliverables/architecture_verified.pdf`](wanqing/deliverables/architecture_verified.pdf)（同目录提供可编辑 PPTX 与高清 PNG）

**Agent Stack 使用说明**：[`wanqing/docs/agent_stack_usage.md`](wanqing/docs/agent_stack_usage.md)

---

## 2. 硬件清单与接线说明

### 2.1 硬件清单

| 器件 | 型号 | 用途 | 来源 |
|------|------|------|------|
| 主控板 | **ROROLEE Basic（ESP32-S3-WROOM，PSRAM Octal 80M）** | 设备主控 | 主办方提供 |
| 音频编解码 | ES8311（播放）+ ES7210（录音，4 麦） | TTS 播放 / 语音采集 16kHz PCM | 板载 |
| 显示屏 | SH8501 AMOLED 120×240（SPI） | 表情状态机动画 | 板载 |
| 电量计 | BQ27220（I²C） | 电量上报（事件 0x14 / 0x2A19） | 板载 |
| 触觉 | 振动马达（板载驱动电路，GPIO 高电平控制） | 提醒/家人消息/错误触觉模式 | 板载 |
| 存储 | SD 卡（SDIO 4-bit，选配） | 未来本地录音/离线数据 | 板载 |
| 网关 | iPhone/Android 手机 + ROROLEE App | BLE ↔ 云端中继 | 主办方提供 |
| 服务器 | 任意可访问 Agent Stack 的 macOS/Linux 主机 | MCP Server + 桥接 + 隧道 | 团队自备 |

### 2.2 引脚定义（`Agent_link/boards/rorolee-basic/config.h`）

| 外设 | 引脚 | 说明 |
|------|------|------|
| BOOT 按键（PTT 一键通话） | GPIO0 | 低电平按下，内部上拉 |
| 音量+ / 音量−（长按音量− 2s = 自检演示） | GPIO39 / GPIO40 | 低电平按下 |
| 外设电源锁存 | GPIO46 | 低电平使能（`gpio_hold` 保持） |
| I²S MCLK / BCLK / WS | GPIO9 / GPIO10 / GPIO11 | 音频总线 |
| I²S DOUT（ES8311 扬声器） | GPIO41 | |
| I²S DIN（ES7210 麦克风） | GPIO12 | |
| PA 使能 | GPIO3 | 高电平开功放 |
| I²C SDA / SCL | GPIO45 / GPIO48 | 编解码 + 电量计共享总线 |
| 振动马达 | GPIO1 | 高电平振动 |
| 屏幕 CS / DC / RST / SCK / MOSI | GPIO7 / GPIO15 / GPIO6 / GPIO5 / GPIO4 | SPI Mode3 @40MHz |
| SD D0-D3 / CLK / CMD | GPIO8/21/47/16 / GPIO17 / GPIO18 | SDIO 4-bit |

> 所有外设均为板载，**无需额外接线**。仅 USB-C 供电（≥500mA）即可运行全部演示。`config.h` 中 GPIO 均为 3.3 V 逻辑；禁止向 GPIO 输入 5 V，也不要用 GPIO 直接驱动裸马达或扬声器。
> ES8311 地址 0x18、ES7210 地址 0x40、BQ27220 地址 0x55，均在音频 I²C 总线上。

---

## 3. 固件、SDK 与依赖版本

| 组件 | 版本 | 备注 |
|------|------|------|
| ESP-IDF | **v5.5.4** | 固件编译框架 |
| agent_link SDK | 仓库内 `Agent_link/components/agent_link` | 主办方提供，BLE 传输 + 语音/TTS 通道 |
| espressif/esp_codec_dev | 1.6.2 | ES8311/ES7210 驱动 |
| espressif/esp32-camera | 2.1.7 | （本板未用，其他板型使用） |
| Python | ≥ 3.11（已在 3.12 / 3.14 验证） | 后端 + MCP Server |
| mcp (python-sdk) | 2.1.1 | MCP streamable-http 传输 |
| FastAPI / Uvicorn | 0.141.1 / 0.52.4 | REST API（家人端预留）；完整锁定见 `requirements.txt` |
| Claude Code CLI | 2.x（shim 兼容层） | roro 托管入口 |
| TiDB Agent Stack | ventured-agent-stack.pingcap.cn | Agent 运行平台，模型 qwen3.7-plus |

---

## 4. 目录结构与模块职责

```
VentureD/
├── README.md                       ← 本文件
├── Agent_link/                     ← ESP32 固件工程（ESP-IDF）
│   ├── boards/rorolee-basic/       ← ★ 晚晴板级固件（UI状态机/PTT/触觉/协议解析）
│   │   ├── rorolee_basic.cc        ←   761 行核心：11 种表情、麦克风独占管理、按键逻辑
│   │   └── config.h                ←   全部引脚定义
│   ├── boards/common/
│   │   ├── device_protocol.cc/.h   ← ★ 0x70 JSON 下行协议解析（5 类消息→设备动作）
│   │   ├── sh8501_panel.cc/.h      ←   AMOLED 驱动封装
│   │   └── bq27220.cc/.h           ←   电量计驱动
│   ├── components/agent_link/      ←   主办方 SDK（勿改）：BLE/语音/TTS/事件
│   └── main/app_main.cpp           ←   SDK 回调 → Board 方法映射
├── wanqing/                        ← ★ 云端与智能层（团队开发）
│   ├── prompts/system_prompt.md    ←   Agent 系统提示词（同步至 MEMORY.md）
│   ├── backend/
│   │   ├── mcp_server.py           ←   MCP Server :8200，5 个工具
│   │   ├── models/database.py      ←   SQLite 数据层（任务/备忘/提醒）
│   │   └── api/server.py           ←   FastAPI REST :8100（家人端：日报/留言/告警）
│   ├── bridge/
│   │   ├── claude-bridge           ←   ★ roro ↔ Agent Stack 协议桥（Python, stdlib only）
│   │   ├── claude-shim             ←   PATH shim：重启 daemon + 注入 bridge
│   │   ├── reminder-pusher         ←   ★ 主动提醒守护进程：Scheduler 触发 → JSONL mirror 投递（launchd 托管）
│   │   ├── ai.rorolee.reminder-pusher.plist ← launchd 配置（入库版）
│   │   ├── ai.rorolee.family-api.plist ← 家人端 REST 服务 launchd 模板（install.sh 渲染）
│   │   └── install.sh              ←   一键部署到 ~/.rorolee/bin/（含 pusher/family-api 注册）
│   ├── tools/wanqing-tools/        ←   Custom Tool 包（manifest.json + index.mjs，备选方案）
│   ├── docs/
│   │   ├── ble_protocol_v1.md      ←   BLE 应用层协议 v1.0（0x70/0x64 全量定义）
│   │   └── agent_stack_usage.md    ←   ★ 交付物六：Agent Stack 使用说明
│   ├── deliverables/               ←   ★ 交付物四：一页架构图（PDF/PNG/HTML）
│   ├── tests/                      ←   100 条中文意图测试 + 端到端脚本
│   ├── .env.example                ←   配置模板（无真实凭证）
│   └── requirements.txt            ←   Python 依赖
└── agent-stack-dev-guide/          ←   Agent Stack 开发者资料（主办方提供）
```

---

## 5. 环境准备与依赖安装

### 5.1 ESP32 固件（烧录机）

```bash
# 安装 ESP-IDF v5.5.4（官方安装器或手动 clone）
git clone -b v5.5.4 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh && source export.sh

cd Agent_link
idf.py set-target esp32s3
idf.py menuconfig   # Agent Link Device -> Board Type -> ESP32S3_ROROLEE_BASIC
idf.py build
idf.py -p /dev/cu.usbmodem* flash monitor
```

### 5.2 云端主机（MCP Server + 桥接）

```bash
cd wanqing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置 Agent Stack 凭证（参考 .env.example）
cp .env.example ~/.rorolee/bridge.env
vim ~/.rorolee/bridge.env   # 填入 BASE_URL / API_KEY / PROJECT_ID / AGENT_ID

# 部署桥接到 roro（需先安装 rorolee 插件）
bash bridge/install.sh
Windows PowerShell 安装后端依赖：

```powershell
cd wanqing
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`.env.example` 只是变量名模板，代码不会自动加载仓库内 `.env`；请把真实值注入当前 shell、`~/.rorolee/bridge.env` 或密钥管理服务。
```

---

## 6. 运行步骤（端到端）

```bash
# ① 启动 MCP Server（Agent 的工具入口）
cd wanqing && source .venv/bin/activate
python backend/mcp_server.py          # :8200/mcp

# ② 公网隧道（让 Agent Stack 云端可达本机 MCP）
ssh -T -o StrictHostKeyChecking=no -R 80:localhost:8200 serveo.net
# 输出形如 https://xxxx.serveousercontent.com —— 用于第 ③ 步注册

# ③ 在 Agent Stack 注册 MCP（一次性，见 §7.2 的 curl 命令）

# ④ 部署桥接 + 提醒守护进程 + 家人端服务（自动重启 roro daemon 并连接 Agent Stack）
bash bridge/install.sh   # 安装 claude-bridge/reminder-pusher，注册 launchd 自启（含 family-api :8100）
claude
# 输出 [bridge] TiDB Agent Stack — session xxxx 即就绪
# reminder-pusher 由 launchd 托管：开机自启、崩溃自重启，日志 ~/.roro/reminder-pusher.log

# ⑤ 手机打开 ROROLEE App，BLE 连接设备（广播名 ROROLEE_BASIC）
#    App 会话指向运行 ④ 的主机 —— 完整链路打通
```

---

## 7. Agent / Tool / Custom Service 配置方式

### 7.1 Agent（Console 配置，一次性）

1. 登录 Agent Stack Console → 选择项目 → Agent。
2. **模型**：`qwen3.7-plus`。
3. **MEMORY.md**：粘贴 [`wanqing/prompts/system_prompt.md`](wanqing/prompts/system_prompt.md) 全文——定义适老化语气、6 类意图、口语时间解析表、最小追问策略、安全边界。
4. 桥接每次新会话也会自动注入同样的系统提示词（双保险，见 `bridge/claude-bridge` 的 `init_session_prompt`）。

### 7.2 MCP Server（API 注册，一次性）

```bash
BASE="https://ventured-agent-stack.pingcap.cn"; KEY="$AGENT_STACK_USER_API_KEY"
TUNNEL="https://xxxx.serveousercontent.com"   # ② 的隧道地址

# 注册
curl -X POST "$BASE/api/mcp/servers" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"displayName":"晚晴工具包","endpointUrl":"'"$TUNNEL"'/mcp","transport":"streamable_http","scope":{"kind":"agent","agentId":"'"$AGENT_STACK_AGENT_ID"'"}}'
# → 记下 serverId

# 免鉴权 + 激活
curl -X PUT "$BASE/api/mcp/servers/$SERVER_ID/credential" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"authKind":"none"}'
curl -X POST "$BASE/api/mcp/servers/$SERVER_ID/activate" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"expectedServerVersion":1}'
```

### 7.3 Custom Tool（备选方案，未启用）

`wanqing/tools/wanqing-tools/` 提供等价的 Custom Tool 包（`manifest.json` + `index.mjs`，经 `BACKEND_URL` 凭证调用 REST API）。当前作品走 MCP 方案；Custom Tool 保留作为 Agent Stack 功能验证与降级路径。

### 7.4 家人端（家人关注 MVP）

`install.sh` 会渲染 `bridge/ai.rorolee.family-api.plist` 并注册 launchd，FastAPI :8100 常驻。访问 token 首次请求时自动生成于 `~/.rorolee/family.token`（0600），也可用环境变量 `FAMILY_TOKEN` 指定；无互动告警阈值 `FAMILY_ALERT_HOURS` 默认 24h。

**家人留言入口（浏览器）**：`http://<主机>:8100/family/web?token=<token>` —— 移动端适配的家人门户，可留言下发到设备、查看日报/告警/留言已读状态（30s 自动刷新）。界面截图：[`wanqing/deliverables/family_web_screenshot.png`](wanqing/deliverables/family_web_screenshot.png)。链接即钥匙，勿外泄。

```bash
TOK=$(cat ~/.rorolee/family.token)

# 家人日报：今日任务/已推提醒/最近互动/无互动告警/App 在线状态
curl -s -H "X-Family-Token: $TOK" localhost:8100/family/report

# 家人留言 → 设备 TTS 播报 + 爱心表情 + 振动（JSONL mirror 投递）
curl -s -X POST -H "X-Family-Token: $TOK" -H "Content-Type: application/json" \
  -d '{"sender":"女儿","text":"妈，我周末回来陪你吃饭"}' localhost:8100/family/message

# 留言列表（含已读状态）
curl -s -H "X-Family-Token: $TOK" localhost:8100/family/messages
```

老人侧闭环：老人说“有留言吗？”→ Agent 调 MCP `query_family_messages` → TTS 念出并标记已读。验证 trace：[`wanqing/deliverables/family_care_trace.json`](wanqing/deliverables/family_care_trace.json)。

---

## 8. 最短验证路径（一条完整闭环）

**前提**：§5~§7 已完成（约 15 分钟）。手机与设备、主机在同一演示环境。

1. **设备就绪**：ESP32 上电 → 屏幕播开机动画 → BLE 连接后变"待机瞌睡眼"。
2. **发起对话**：老人按住 BOOT 键说 *"明天下午三点提醒我吃降压药"*，松开。
   - 屏幕依次切换 倾听 → 上传 → 思考（带呼吸动画）；
3. **Agent 决策**（云端）：晚晴 Agent 解析意图 = CREATE_TASK，时间解析"明天下午三点" → 调用 `create_task(title="吃降压药", due_time=明天15:00+08:00)` → SQLite 落库。
4. **结果回传**：屏幕切"说话"表情，扬声器播报 *"好的，明天下午三点提醒你吃降压药。"*，振动一次确认。
5. **验证持久化**：再按 BOOT 说 *"明天有什么安排？"* → Agent 调 `query_tasks` → 播报 *"明天下午三点有一件事：吃降压药。"*
6. **（加分）主动提醒**：到点 Scheduler fire → reminder-pusher 30s 内检测 → 写入被托管会话 JSONL → roro daemon 经 mirror 协议投给 App → App 经 BLE 下发 → 设备播“提醒”动画 + 三连振动 + TTS 播报提醒内容（实测触发后 4s 内送达，trace 见 `wanqing/deliverables/reminder_e2e_trace.json`）。

无需写任何代码即可复现；每一步的日志见 §9 验证材料。

---

## 9. 已知限制与未完成部分

| 项 | 状态 | 说明 |
|----|------|------|
| 语音上行（0x40 VoiceChunk） | 已实现，真机验证通过 | BOOT 按住说话进入 Agent 当前会话；不能映射到会议 Recording 通道 |
| TTS 下行播放 | 已实现，真机验证通过 | 16kHz PCM L2CAP 流 + 静音尾判停 |
| 唤醒词"小晚晴" | 协议已定义（0x64 wakeup 事件） | 板端依赖乐鑫唤醒词方案，未集成 |
| 摄像头 / SD 卡录音 | 未启用 | 引脚与驱动预留，非 MVP 范围 |
| 家人消息（family_message） | **家人关注 MVP 已实现** | 家人端 REST :8100（日报/留言/告警，§7.4）；设备端 TTS 待 App 上线真机复现 |
| serveo 隧道稳定性 | 可用但偶发过期 | 生产建议换 cloudflared / 自建 frp |
| 意图识别 | 96.9%（62/64） | 2 个失败用例为无上下文指代（"好了好了做完了"），多轮 Session 下可解 |
| SQLite 单用户 | 当前 `default_user` | 多用户需 App 传 device_id（后端已支持 user_id 字段） |
| Android App 交付 | **当前仓库未包含 App 源码/APK** | 评审前必须补充可访问的 App 仓库或 Release/APK 链接与版本号，否则无法独立复现手机桥接 |
| BLE 长 JSON | 尚有限制 | GATT 单次写入有效 payload 约 506 字节，超长 0x70 JSON 的多帧重组尚未完整实现 |

---

## 10. 配置与凭证管理

- **真实凭证只存在于 `~/.rorolee/bridge.env`**（仓库外），由 `claude-bridge` 启动时读取；同名的环境变量优先。
- 历史提交曾出现过 User API Key；仅删除当前文件不等于失效，维护者必须在 Agent Stack 控制台撤销并轮换旧密钥。
- 仓库只提交 [`wanqing/.env.example`](wanqing/.env.example) 模板，`*.env / *.key / *.pem` 均在 `.gitignore`。
- MCP Server 与 Agent Stack 之间使用免鉴权（`authKind=none`）+ serveo 随机域名，演示后可随时吊销。

---

## 11. 测试

本地 MCP 测试不需要云端密钥。终端 A：

```bash
cd wanqing && source .venv/bin/activate
python backend/mcp_server.py
```

终端 B：

```bash
cd wanqing && source .venv/bin/activate
python tests/demo_e2e.py --skip-agent --skip-scheduler
```

云端意图测试需先注入 `.env.example` 中的四个 `AGENT_STACK_*` 变量，再运行：

```bash
python tests/test_intent.py --start 1 --end 100
```

> 评测口径说明：`test_intent.py` 校验 Agent 实际发起的工具调用（tool_calls）与关键参数，
> 而非要求模型输出结构化意图标签——与线上对话式体验一致。凭证一律读环境变量，仓库内无硬编码。

意图测试结果：**62/64 通过（96.9%）**，明细见 [`wanqing/tests/test_results_*.json`](wanqing/tests/)。

---

## 12. 评委访问

- 仓库：**https://github.com/chiiiiiiing/wanqing**（如为私有请向评委账号授权）
- 关键路径：`wanqing/deliverables/`（架构图）、`wanqing/docs/`（协议+Agent 说明）、`wanqing/bridge/`（桥接）、`Agent_link/boards/rorolee-basic/`（固件）
- 硬件同款：ROROLEE Basic 板 + ROROLEE App 账号即可复现 §8 全流程
- **待补交**：Android App 源码或可下载 APK/Release 链接。当前仅凭本仓库无法从零构建手机侧桥接。

---

*晚晴团队 · VentureD 2026*
