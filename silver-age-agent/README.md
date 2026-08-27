# 银龄AI助手 (Silver Age AI Assistant)

AI assistant for elderly people, built on TiDB Agent Stack with MCP tool integration.

## Architecture

```
老人说话 → 板卡D(录音) → BLE → ROROLEE App → Agent Stack
                                                    ├── Audio Turn (ASR)
                                                    ├── 银龄AI Agent (NLU + Scheduler)
                                                    │     └── MCP Tools → Our Backend → SQLite
                                                    └── NDJSON流式回复
                                                        → App → BLE → 板卡D (TTS+震动+屏幕)
```

## Project Structure

```
silver-age-agent/
├── prompts/
│   └── system_prompt.md          # Agent system prompt (需手动设置到 MEMORY.md)
├── backend/
│   ├── models/
│   │   └── database.py          # SQLite 数据库层 (tasks, notes, reminders)
│   ├── api/
│   │   └── server.py            # FastAPI REST API (port 8100)
│   ├── mcp_server.py            # MCP Server (port 8200) - 5 tools
│   └── silver_age.db            # SQLite database file
├── tools/
│   └── silver-age-tools/        # Custom Tool package (备用方案)
│       ├── manifest.json
│       └── index.mjs
├── tests/
│   ├── test_sentences.json      # 100条中文测试语句
│   ├── run_action_tests.py      # Agent 行为测试
│   └── demo_e2e.py              # 端到端验证脚本
└── .venv/                       # Python virtual environment
```

## Verified Capabilities

| 能力 | 状态 | 说明 |
|------|------|------|
| Agent NLU (意图解析) | ✅ | 96.9% 通过率 (62/64 tests) |
| Agent Scheduler (内置提醒) | ✅ | Agent 自动创建定时提醒 |
| MCP Server (5 tools) | ✅ | create_task, create_note, query_tasks, complete_task, delay_task |
| MCP on Agent Stack | ✅ | 已注册并激活 (serverId: mcp_ed84d40c-...) |
| SQLite 持久化 | ✅ | Task/Note/Reminder CRUD 全部工作 |
| NDJSON 流式回复 | ✅ | 完整事件流: turn_started → drafts → message → finished |

## MCP Tools

All 5 tools are exposed via MCP (Model Context Protocol) at `http://localhost:8200/mcp`:

| Tool | 功能 | 参数 |
|------|------|------|
| `create_task` | 创建提醒任务 | title, due_time, category, description |
| `create_note` | 创建备忘笔记 | content, category |
| `query_tasks` | 查询任务列表 | date, status |
| `complete_task` | 标记任务完成 | title_keyword, task_id |
| `delay_task` | 延期任务 | title_keyword, minutes, new_due_time |

## Quick Start

### 1. Start the MCP server
```bash
cd silver-age-agent
source .venv/bin/activate
python backend/mcp_server.py
# MCP server running on http://0.0.0.0:8200
```

### 2. (Optional) Start the REST API
```bash
python backend/api/server.py
# REST API on http://0.0.0.0:8100
```

### 3. Set up public tunnel
```bash
ssh -T -o StrictHostKeyChecking=no -R 80:localhost:8200 serveo.net
# Gives you: https://xxxx.serveousercontent.com
```

### 4. Register MCP on Agent Stack
```bash
# Create registration
curl -X POST "https://ventured-agent-stack.pingcap.cn/api/mcp/servers" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"displayName":"银龄助手工具包","endpointUrl":"https://YOUR_TUNNEL/mcp","transport":"streamable_http","scope":{"kind":"agent","agentId":"agent_cc0aa5c6ff600adf4d6c31718e3fc9bb"}}'

# Set credential to none
curl -X PUT "https://ventured-agent-stack.pingcap.cn/api/mcp/servers/$SERVER_ID/credential" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"authKind":"none"}'

# Activate
curl -X POST "https://ventured-agent-stack.pingcap.cn/api/mcp/servers/$SERVER_ID/activate" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"expectedServerVersion":1}'
```

### 5. Run tests
```bash
python tests/demo_e2e.py --skip-agent --skip-scheduler
```

## Manual Steps Required (Console GUI)

1. **Set MEMORY.md**: Log into https://ventured-agent-stack.pingcap.cn and paste `prompts/system_prompt.md` content into the Agent's MEMORY.md. This is required for the Agent to use our MCP tools.

2. **Audio Turn testing**: Test Chinese ASR with real audio files from the board.

3. **Scheduler webhook**: Configure a webhook URL for Scheduler fire events to trigger notifications.

## Key Resources

| Resource | Value |
|----------|-------|
| Agent Stack URL | `ventured-agent-stack.pingcap.cn` |
| Project ID | `proj_6c440f8173104d06b005d9c552bfe774` |
| Agent ID | `agent_cc0aa5c6ff600adf4d6c31718e3fc9bb` |
| MCP Server ID | `mcp_ed84d40c-abbb-403f-8007-223d1bdca5e5` |
| Agent Model | `qwen3.7-plus` |

## Test Results

### Intent Parsing (62/64 passed, 96.9%)

| Intent | Tests | Pass Rate |
|--------|-------|-----------|
| CREATE_TASK | 27/27 | 100% |
| CREATE_NOTE | 10/10 | 100% |
| QUERY_TASK | 7/7 | 100% |
| COMPLETE_TASK | 6/7 | 86% |
| DELAY_TASK | 3/5 | 60% |
| GENERAL_QA | 6/6 | 100% |
| UNKNOWN | 3/3 | 100% |

Failed cases: ambiguous inputs without conversation context ("好了好了做完了" and "等一下再说").
