# 晚晴 — Agent Stack 使用说明

> 本文说明 **TiDB Agent Stack** 在"晚晴"作品中的真实职责、配置方式、自定义工具、硬件能力映射和可验证的运行证据。所有关键 trace 和日志均已脱敏处理。

---

## 1. Agent Stack 在作品中的职责

| 职责 | 说明 |
|------|------|
| 自然语言理解 | 把老人口语化的语音/文本输入解析为 6 类意图之一：`CREATE_TASK`、`CREATE_NOTE`、`QUERY_TASK`、`COMPLETE_TASK`、`DELAY_TASK`、`GENERAL_QA` |
| 口语时间解析 | 将"后天早上九点"、"一会儿"等模糊表达映射为精确的 ISO 8601 时间 |
| 工具/调度决策 | 根据意图决定调用 MCP 工具（任务/备忘 CRUD）还是 Agent Stack 内置 Scheduler（定时提醒触发） |
| 上下文记忆 | 维护多轮 Session，支持指代消解（"晚一点"→前面提到的任务） |
| 适老化回复生成 | 输出简短、温暖、无英文、无技术术语的中文，必要时控制在一句话 |

**未使用 Agent Stack 替代方案**：所有智能处理均依赖 Agent Stack；Custom Tool 包（`wanqing/tools/wanqing-tools/`）仅作为备用链路保留。

---

## 2. Agent 配置

### 2.1 模型与角色

| 项 | 配置 |
|----|------|
| 模型 | `qwen3.7-plus`（TiDB Agent Stack 提供） |
| Agent ID | `agent_cc0aa5c6ff600adf4d6c31718e3fc9bb`（项目级固定） |
| 项目 | `proj_6c440f8173104d06b005d9c552bfe774` |

### 2.2 系统提示词（MEMORY.md）

完整提示词见 [`wanqing/prompts/system_prompt.md`](../prompts/system_prompt.md)，核心约束包括：

1. **角色**：你是"晚晴"，专为 60 岁以上老人服务的 AI 管家。
2. **语气**：短句、温暖、不用英文、不用技术词。
3. **6 类意图**： CREATE_TASK、CREATE_NOTE、QUERY_TASK、COMPLETE_TASK、DELAY_TASK、GENERAL_QA。
4. **时间解析表**：今天上午=09:00、今天下午=15:00、今天晚上=19:00、一会儿=30 分钟后、后天=后天 09:00 等。
5. **最小追问（Minimum Clarification）**：能执行就不追问，一次最多问一个问题。
6. **安全边界**：不诊断医疗、不处理财务、不虚构信息。

**配置方式**：登录 Agent Stack Console → Agent 设置 → 将 `system_prompt.md` 内容粘贴到 **MEMORY.md**。桥接程序 `claude-bridge` 也会在每个新 Session 启动时自动注入同一份提示词，形成双保险。

### 2.3 关键行为边界

| 场景 | 行为 |
|------|------|
| 用户说"提醒我买菜"（缺时间） | 追问："什么时候提醒你？" |
| 用户说"明天提醒我"（缺事项） | 追问："提醒你做什么呢？" |
| 用户说"记一下鸡蛋快没了" | 直接创建备忘，不追问 |
| 用户说"晚一点" | 结合 Session 上下文，指代最近任务，调用 delay_task |
| 医疗/财务/诊断类问题 | 拒绝并给出安全提示 |

---

## 3. Skill 与 Tool

### 3.1 自定义 MCP Server（当前主链路）

MCP Server 地址：`http://localhost:8200/mcp`（经 serveo 公网暴露后注册到 Agent Stack）。

| Tool | 解决的问题 | 参数 | 返回值 |
|------|-----------|------|--------|
| `create_task` | 创建提醒任务 | `title`, `due_time`(ISO8601), `category`(health/life/social/finance/other), `description` | `✅ 任务「xxx」已创建，提醒时间：...` |
| `create_note` | 创建备忘笔记 | `content`, `category`(health/life/recipe/contact/general) | `✅ 备忘已保存：...` |
| `query_tasks` | 查询待办/已完成任务 | `date`(YYYY-MM-DD，可选), `status`(pending/completed/cancelled) | 任务列表文本 |
| `complete_task` | 标记任务完成 | `title_keyword`(模糊匹配), `task_id`(精确 ID，可选) | 完成确认 |
| `delay_task` | 推迟任务 | `title_keyword`, `minutes`(默认 30), `new_due_time`(可选) | 推迟确认 |

### 3.2 自定义 Custom Tool（备用方案）

`wanqing/tools/wanqing-tools/` 包含与 MCP 等价的 Custom Tool 包（manifest.json + index.mjs），用于：
- 在 Agent Stack 无法直接访问 MCP 时作为降级；
- 验证 Agent Stack 的 Custom Tool 能力。

配置方式：上传 zip → 在 Agent Console 安装 → 绑定 `BACKEND_URL` 环境变量指向 FastAPI 后端。

---

## 4. 硬件能力调用映射

Agent 或 Tool 的**文本决策**通过 BLE 0x70 JSON 协议下发，设备固件 `device_protocol.cc` 解析后映射到 SDK 能力，再转为具体硬件动作。

| Agent / Tool 决策 | BLE 0x70 JSON | SDK / 固件动作 | 硬件输出 |
|-------------------|---------------|----------------|----------|
| 普通回复 `tts=true` | `{"type":"ai_reply","text":"...","tts":true}` | `ShowText()` + `PlayAudio()` | 屏幕"说话"表情 + 扬声器 TTS |
| Scheduler 触发提醒 | `{"type":"reminder","id":"r1","title":"吃药","text":"...","importance":"important"}` | `SetUiState(Reminder)` + `PlayHapticPattern(ImportantReminder)` | 提醒表情 + 三连振动 + TTS |
| 家人消息下发 | `{"type":"family_message","sender":"女儿","text":"..."}` | `SetUiState(FamilyMessage)` + 触觉 | 爱心表情 + 振动 + TTS |
| 调节音量 | `{"type":"device_command","action":"set_volume","value":80}` | `SetVolumePercent()` → ES8311 | 扬声器音量变化 |
| 网络/Agent 超时 | `{"type":"error","code":"AGENT_TIMEOUT","message":"..."}` | `SetUiState(Error)` + 错误触觉 | 错误表情 + 长振 |
| 电量低（设备主动） | 事件 `0x14` + 0x2A19 | `SetUiState(LowBattery)` | 低电量表情 |

### 关键 SDK 方法到硬件的链路

```
Agent 决策文本
    ↓
claude-bridge → ROROLEE App → BLE 0x70 JSON
    ↓
ESP32 device_protocol.cc 解析
    ↓
Board 抽象方法（ShowText / PlayAudio / SetUiState / PlayHapticPattern / SetVolumePercent）
    ↓
agent_link SDK（L2CAP TTS / GATT 事件 / GPIO）
    ↓
具体硬件（SH8501 屏幕 / ES8311 功放 / ES7210 麦克风 / 振动马达 / GPIO 按键）
```

---

## 5. 任务能力（Session + Scheduler）

### 5.1 Session 上下文

- **生命周期**：桥接程序启动时创建或复用 `~/.rorolee/bridge-session.json` 中的 session_id。
- **作用**：Agent 记住本轮对话中的"当前任务"，支持多轮指代。
- **示例**：
  - 第 1 轮："提醒我买菜" → Agent 追问"什么时候"
  - 第 2 轮："明天下午三点" → Agent 创建任务"买菜"
  - 第 3 轮："晚一点" → Agent 识别指代，调用 `delay_task` 修改"买菜"

### 5.2 Scheduler 主动提醒（已实现端到端闭环）

- **触发条件**：Agent 创建提醒任务时，同时创建 Agent Stack Scheduler（一次性 `runAt` 或周期性 `cron`）。
- **运行过程**：
  1. Agent 调用 `create_task` 写入本地 SQLite，并创建 Scheduler；
  2. Scheduler 到点触发（`lastFiredAt` 更新）；
  3. **`reminder-pusher` 守护进程**（`wanqing/bridge/reminder-pusher`，launchd 自启）每 30 秒轮询 `GET /api/schedulers`，检测到新触发后从 prompt 提取提醒文案；
  4. 通过 MQTT 推送到 App 的 chat 下行 topic `announcement/{user}/{device}/chat/{channel}/out`（channel 自动从 roro 流量学习）；
  5. App 经 BLE 下发到设备。
- **推送格式**：同时发送两条——`{"type":"assistant","text":...}`（App 现有解析路径，保证送达+TTS）与协议 v1 的结构化 `{"type":"reminder",...}`（App 支持后可触发专属提醒 UI）。
- **用户感知**：设备 TTS 播报提醒内容；老人按 BOOT 键或说"好了"即可调用 `complete_task` 关闭提醒。
- **验证记录**（2026-08-28）：创建 2 分钟后触发的测试提醒，Scheduler 准点触发，pusher 4 秒内完成 MQTT 推送，channel 与文案均正确，见 [`../deliverables/reminder_e2e_trace.json`](../deliverables/reminder_e2e_trace.json)。

---

## 6. 验证材料（已脱敏）

### 6.1 MCP Server 工具列表验证

```bash
curl -X POST http://localhost:8200/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <session-id>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

返回 5 个自定义工具：

```json
{
  "tools": [
    {"name": "create_task", "description": "创建一个新的提醒任务并保存到数据库。当老人说...时调用。"},
    {"name": "create_note", "description": "创建一条备忘笔记并保存到数据库。当老人说...时调用。"},
    {"name": "query_tasks", "description": "查询老人的任务列表。当老人说...时调用。"},
    {"name": "complete_task", "description": "将一个任务标记为已完成。当老人说...时调用。"},
    {"name": "delay_task", "description": "推迟一个任务的时间。当老人说...时调用。"}
  ]
}
```

### 6.2 create_task 工具调用 + SQLite 持久化验证

**输入**：

```json
{
  "name": "create_task",
  "arguments": {
    "title": "评委验证：提醒吃降压药",
    "due_time": "2026-08-29T09:00:00+08:00",
    "category": "health",
    "description": "社区医院量血压"
  }
}
```

**Tool 返回**：

```
✅ 任务「评委验证：提醒吃降压药」已创建，提醒时间：8月29日 09:00
```

**持久化证明**（SQLite）：

```bash
sqlite3 wanqing/backend/wanqing.db \
  "SELECT id, title, due_time, status FROM tasks WHERE title LIKE '%评委验证%';"
```

```
task_f983738e135b | 评委验证：提醒吃降压药 | 2026-08-29T09:00:00+08:00 | pending
```

完整 trace 文件：[`wanqing/deliverables/agent_stack_trace.json`](../deliverables/agent_stack_trace.json)

### 6.3 Agent Stack NDJSON 流式回复验证

**输入**："后天早上九点提醒我去社区医院量血压"

Agent Stack 返回的 NDJSON 事件流：

```json
{"event": "turn_started", "payload": {"execution": {"backend": "pi", "model": "qwen3.7-plus"}}}
{"event": "operation_step", "payload": {"operationId": "op_5fdc...", "status": "succeeded", "label": "Completed thinking"}}
{"event": "operation_step", "payload": {"operationId": "op_2a68...", "status": "running", "label": "Working"}}
{"event": "operation_step", "payload": {"operationId": "op_2a68...", "status": "succeeded", "label": "Operation completed"}}
{"event": "assistant_draft", "payload": {"text": "已"}}
{"event": "operation_step", "payload": {"operationId": "op_1733...", "status": "succeeded", "label": "Completed thinking"}}
{"event": "assistant_draft", "payload": {"text": "已设好提醒 ✅\n\n**后天（8月29日，周六）早上 9:00** 会提醒你去社区医院量血压。到时候我会准时通知你！"}}
{"event": "assistant_message", "payload": {"text": "已设好提醒 ✅\n\n**后天（8月29日，周六）早上 9:00** 会提醒你去社区医院量血压。到时候我会准时通知你！"}}
{"event": "turn_finished", "payload": {"status": "succeeded"}}
```

完整 trace 文件：[`wanqing/deliverables/agent_ndjson_trace.json`](../deliverables/agent_ndjson_trace.json)

### 6.4 意图识别测试结果

```bash
cd wanqing && source .venv/bin/activate
export AGENT_STACK_USER_API_KEY=...  AGENT_STACK_PROJECT_ID=...  AGENT_STACK_AGENT_ID=...   # 参见 ../.env.example，仓库内无硬编码凭证
python tests/test_intent.py --start 1 --end 100   # 工具调用口径：校验实际 tool_calls + 参数
```

结果：**62/64 通过，96.9%**

| Intent | 测试数 | 通过率 |
|--------|--------|--------|
| CREATE_TASK | 27/27 | 100% |
| CREATE_NOTE | 10/10 | 100% |
| QUERY_TASK | 7/7 | 100% |
| COMPLETE_TASK | 6/7 | 86% |
| DELAY_TASK | 3/5 | 60% |
| GENERAL_QA | 6/6 | 100% |
| UNKNOWN | 3/3 | 100% |

失败用例为无上下文指代（如"好了好了做完了"），Session 多轮场景下可解。

---

## 7. 典型流程示例

### 示例 1：创建提醒（含工具调用）

| 步骤 | 内容 |
|------|------|
| **用户/设备输入** | 老人按住 BOOT 键说："明天下午三点提醒我买菜" |
| **Agent 理解** | 意图 = `CREATE_TASK`；标题 = "买菜"；时间 = 明天 15:00 |
| **调用能力** | Agent 调用 MCP `create_task(title="买菜", due_time="...", category="life")` |
| **后端动作** | SQLite 写入任务记录 |
| **设备/用户结果** | 屏幕"说话"表情 + 扬声器："好的，明天下午三点提醒你买菜。" + 一次确认振动 |

### 示例 2：查询今日事项

| 步骤 | 内容 |
|------|------|
| **用户/设备输入** | "明天有什么安排？" |
| **Agent 理解** | 意图 = `QUERY_TASK`；日期 = 明天 |
| **调用能力** | Agent 调用 MCP `query_tasks(date="2026-08-29", status="pending")` |
| **后端动作** | SQLite 返回待办列表 |
| **设备/用户结果** | 扬声器："明天下午三点有一件事：买菜。" |

### 示例 3：完成提醒（多轮上下文）

| 步骤 | 内容 |
|------|------|
| **用户/设备输入** | 提醒 TTS 播放后，老人说："已经吃完了" |
| **Agent 理解** | 意图 = `COMPLETE_TASK`；结合当前/最近任务，匹配到"吃药" |
| **调用能力** | Agent 调用 MCP `complete_task(title_keyword="吃药")` |
| **后端动作** | SQLite 将该任务 status 改为 `completed` |
| **设备/用户结果** | 屏幕回到"待机"表情，扬声器："好的，已标记完成。" |

---

## 8. 截图与 Trace 文件索引

| 文件 | 说明 |
|------|------|
| `wanqing/deliverables/architecture.pdf` | 一页架构图（已脱敏） |
| `wanqing/deliverables/agent_stack_trace.json` | MCP `tools/list` + `create_task` 脱敏 trace |
| `wanqing/deliverables/agent_ndjson_trace.json` | Agent Stack 完整 NDJSON 流脱敏 trace |
| `wanqing/deliverables/reminder_e2e_trace.json` | Scheduler 准点触发 → reminder-pusher → MQTT 推送闭环脱敏 trace |
| `wanqing/tests/test_results_*.json` | 意图识别 62/64 通过原始结果 |
| Agent Stack Console | Agent MEMORY.md / MCP 服务器列表截图需评委自行查看（已脱敏，无凭证） |

---

*所有 API Key、Token、完整 session_id 均已从本文档与 trace 文件中移除。评委如需复现，请按根目录 `README.md` §5-§7 配置 `.env` 与 Agent Stack 控制台后运行。*
