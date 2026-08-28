#!/usr/bin/env python3
"""
deliver.py — 晚晴消息 → ROROLEE App 的正确投递方式

实测确认：App 并不消费第三方直接发布到 chat/{channel}/out 的消息；
它通过 roro daemon 的 watermark/replay 协议拉取会话条目，
而 daemon 的数据源是「被托管会话」的 Claude JSONL 会话文件（mirror 机制）。

因此正确投递姿势：
  往被托管会话的 JSONL 追加一条 assistant 条目（fsync）
  → daemon mirror 察觉 → watermark entry_count+1 → App replay 新条目 → TTS + UI + BLE 下发设备。

无托管会话时（App 未打开托管终端）返回 mqtt-fallback，由调用方自行直接发布兜底。
"""

import json
import os
import time
import uuid

CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")


def cwd_to_project(cwd):
    """/Users/nibelung -> -Users-nibelung（与 claude projects 目录命名一致）"""
    return cwd.replace("/", "-")


def managed_jsonl(state):
    """从 pusher state 取当前被托管会话的 JSONL 路径；无则 None。"""
    ms = state.get("managed_session") or {}
    sid, cwd = ms.get("id"), ms.get("cwd")
    if not sid or not cwd:
        return None
    p = os.path.join(CLAUDE_PROJECTS, cwd_to_project(cwd), f"{sid}.jsonl")
    return p if os.path.exists(p) else None


def _last_uuid(path):
    try:
        with open(path, "rb") as f:
            for line in reversed(f.read().splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line).get("uuid")
                except Exception:
                    continue
    except Exception:
        pass
    return None


def append_assistant(jsonl_path, text, session_id, cwd):
    """追加一条 assistant 条目（claude JSONL 格式）并 fsync，daemon mirror 会投递给 App。"""
    entry = {
        "parentUuid": _last_uuid(jsonl_path),
        "isSidechain": False,
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
        "uuid": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "userType": "external",
        "entrypoint": "cli",
        "cwd": cwd,
        "sessionId": session_id,
    }
    fd = os.open(jsonl_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def deliver(state, text):
    """优先 JSONL mirror 投递。返回 (via, detail)；via=='mqtt-fallback' 时调用方自行发布。"""
    path = managed_jsonl(state)
    if path:
        ms = state.get("managed_session")
        append_assistant(path, text, ms["id"], ms["cwd"])
        return "jsonl", path
    return "mqtt-fallback", None
