# 晚晴 — 老年人的随身 AI 管家

> 这是仓库子目录 `wanqing/` 的快速参考。**完整复现说明、硬件接线、目录结构、Agent Stack 配置和交付物索引请查看仓库根目录 [`README.md`](../README.md)。**

## 快速启动

```bash
cd wanqing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example ~/.rorolee/bridge.env    # 填入 Agent Stack 凭证
python backend/mcp_server.py             # :8200
# 另开终端
bash bridge/install.sh                   # 部署 claude-bridge + shim
claude
```

## 子目录速查

| 路径 | 说明 |
|------|------|
| `prompts/system_prompt.md` | Agent MEMORY.md 提示词 |
| `backend/mcp_server.py` | MCP Server（5 个工具） |
| `backend/api/server.py` | FastAPI REST :8100 |
| `backend/models/database.py` | SQLite 数据层 |
| `bridge/` | roro ↔ Agent Stack 桥接程序与安装脚本 |
| `docs/ble_protocol_v1.md` | BLE 应用层协议 v1.0 |
| `docs/agent_stack_usage.md` | Agent Stack 使用说明（交付物六） |
| `deliverables/` | 一页架构图 + 脱敏 trace |
| `tests/` | 意图识别与端到端测试 |

## MCP Tools

| Tool | 用途 |
|------|------|
| `create_task` | 创建提醒任务 |
| `create_note` | 创建备忘笔记 |
| `query_tasks` | 查询任务列表 |
| `complete_task` | 标记任务完成 |
| `delay_task` | 推迟任务 |

## 测试结果

- 意图识别：62/64 通过（96.9%）
- MCP Server：5 个工具已注册并验证
- NDJSON 流式回复：完整事件流已验证
