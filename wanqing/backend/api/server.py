"""
晚晴 — FastAPI Backend
REST API for Task/Note management and Scheduler integration.
"""
import os
import sys
import json
import re
import time
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import asynccontextmanager

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# bridge 目录（mqttws 零依赖 MQTT 客户端）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "bridge"))

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from models.database import (
    init_db, create_task, get_task, query_tasks, complete_task, cancel_task,
    find_task_by_title, create_note, query_notes, create_reminder,
    get_pending_reminders, fire_reminder, db,
    create_family_message, query_family_messages,
)

CST = timezone(timedelta(hours=8))

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="晚晴 API",
    description="Task, Note and Reminder management for WanQing AI Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Schemas ===

class TaskCreate(BaseModel):
    user_id: str = "default_user"
    title: str
    description: Optional[str] = None
    due_time: Optional[str] = None
    category: str = "life"
    scheduler_id: Optional[str] = None

class NoteCreate(BaseModel):
    user_id: str = "default_user"
    content: str
    category: str = "general"

class TaskComplete(BaseModel):
    task_id: Optional[str] = None
    title_keyword: Optional[str] = None
    user_id: str = "default_user"

class ReminderCreate(BaseModel):
    task_id: str
    remind_at: str

class WebhookPayload(BaseModel):
    schedulerId: str
    prompt: str
    sessionId: Optional[str] = None

# === Task Endpoints ===

@app.post("/api/tasks")
def api_create_task(body: TaskCreate):
    task = create_task(
        user_id=body.user_id,
        title=body.title,
        due_time=body.due_time,
        description=body.description,
        category=body.category,
        scheduler_id=body.scheduler_id,
    )
    return {"success": True, "task": task}


@app.get("/api/tasks")
def api_query_tasks(
    user_id: str = "default_user",
    status: str = "pending",
    date: Optional[str] = None,
):
    tasks = query_tasks(user_id, status, date)
    return {"tasks": tasks, "count": len(tasks)}


@app.get("/api/tasks/{task_id}")
def api_get_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"task": task}


@app.post("/api/tasks/complete")
def api_complete_task(body: TaskComplete):
    if body.task_id:
        task = complete_task(body.task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return {"success": True, "task": task}

    if body.title_keyword:
        matches = find_task_by_title(body.user_id, body.title_keyword)
        if len(matches) == 0:
            raise HTTPException(404, f"No task found matching '{body.title_keyword}'")
        if len(matches) == 1:
            task = complete_task(matches[0]["id"])
            return {"success": True, "task": task}
        # Multiple matches — return candidates for disambiguation
        return {"success": False, "candidates": matches, "message": "找到多个匹配任务，请确认是哪一个"}

    raise HTTPException(400, "Must provide task_id or title_keyword")


@app.post("/api/tasks/cancel")
def api_cancel_task(task_id: str):
    task = cancel_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"success": True, "task": task}


@app.get("/api/tasks/search")
def api_search_tasks(user_id: str = "default_user", keyword: str = ""):
    tasks = find_task_by_title(user_id, keyword)
    return {"tasks": tasks, "count": len(tasks)}


# === Note Endpoints ===

@app.post("/api/notes")
def api_create_note(body: NoteCreate):
    note = create_note(
        user_id=body.user_id,
        content=body.content,
        category=body.category,
    )
    return {"success": True, "note": note}


@app.get("/api/notes")
def api_query_notes(
    user_id: str = "default_user",
    category: Optional[str] = None,
    limit: int = 20,
):
    notes = query_notes(user_id, category, limit)
    return {"notes": notes, "count": len(notes)}


# === Reminder Endpoints ===

@app.post("/api/reminders")
def api_create_reminder(body: ReminderCreate):
    reminder = create_reminder(body.task_id, body.remind_at)
    return {"success": True, "reminder": reminder}


@app.get("/api/reminders/pending")
def api_pending_reminders(until: Optional[str] = None):
    reminders = get_pending_reminders(until)
    return {"reminders": reminders, "count": len(reminders)}


@app.post("/api/reminders/{reminder_id}/fire")
def api_fire_reminder(reminder_id: str):
    reminder = fire_reminder(reminder_id)
    if not reminder:
        raise HTTPException(404, "Reminder not found")
    return {"success": True, "reminder": reminder}


# === Webhook Endpoints ===

@app.post("/api/webhook/scheduler")
def api_scheduler_webhook(payload: WebhookPayload):
    """
    Receive Scheduler webhook callbacks.
    When a Scheduler fires, Agent Stack calls this endpoint.
    We look up the associated task and generate a notification.
    """
    with db() as conn:
        task = conn.execute(
            "SELECT * FROM tasks WHERE scheduler_id = ?", (payload.schedulerId,)
        ).fetchone()

    if task:
        return {
            "type": "reminder",
            "task_id": task["id"],
            "title": task["title"],
            "text": f"提醒：{task['title']}",
            "importance": "normal",
            "scheduler_id": payload.schedulerId,
        }

    return {
        "type": "reminder",
        "text": payload.prompt,
        "scheduler_id": payload.schedulerId,
    }


# === Health Check ===

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(CST).isoformat()}


# === Family Endpoints（家人关注） ===

RORO_STATE = os.path.expanduser("~/.roro/state.json")
PUSHER_STATE = os.path.expanduser("~/.roro/reminder-pusher-state.json")
PUSHER_LOG = os.path.expanduser("~/.roro/reminder-pusher.log")
FAMILY_TOKEN_FILE = os.path.expanduser("~/.rorolee/family.token")

MQTT_BROKER = "mqtt.deotaland.ai"
MQTT_PORT = 8083
MQTT_USER_ID = "106"
MQTT_DEVICE_ID = "d-c0065571f81bbe36"


def get_family_token() -> str:
    """FAMILY_TOKEN 环境变量优先；否则 ~/.rorolee/family.token（首次自动生成）。"""
    env = os.environ.get("FAMILY_TOKEN")
    if env:
        return env
    if not os.path.isfile(FAMILY_TOKEN_FILE):
        os.makedirs(os.path.dirname(FAMILY_TOKEN_FILE), exist_ok=True)
        token = secrets.token_urlsafe(12)
        with open(FAMILY_TOKEN_FILE, "w") as f:
            f.write(token)
        os.chmod(FAMILY_TOKEN_FILE, 0o600)
        print(f"[family] 已生成家人端访问 token: {FAMILY_TOKEN_FILE}", flush=True)
    with open(FAMILY_TOKEN_FILE) as f:
        return f.read().strip()


def require_family(x_family_token: Optional[str] = Header(None),
                   token: Optional[str] = Query(None)):
    expected = get_family_token()
    provided = x_family_token or token
    if not provided or provided != expected:
        raise HTTPException(401, "invalid family token")


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _today_pushed_reminders() -> list:
    """从 reminder-pusher 日志解析今日已推送的提醒。"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    out = []
    if not os.path.isfile(PUSHER_LOG):
        return out
    pat = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] 已推送提醒 \[([^\]]+)\] (.*)$")
    try:
        with open(PUSHER_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pat.match(line.strip())
                if m and m.group(1).startswith(today):
                    body = m.group(3)
                    title, _, text = body.partition(": ")
                    out.append({"time": m.group(1), "channel": m.group(2),
                                "title": title, "text": text})
    except OSError:
        pass
    return out


class FamilyMessageCreate(BaseModel):
    sender: str
    text: str


@app.get("/family/report")
def family_report(
    x_family_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    """家人端日报：老人今日任务/提醒/最近互动 + 无互动告警。"""
    require_family(x_family_token, token)
    alert_hours = float(os.environ.get("FAMILY_ALERT_HOURS", "24"))
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")

    # ── 最近互动时间：pusher 观察的 /in 流量 + 任务/备忘操作时间 ──
    candidates = []
    pusher_state = {}
    try:
        with open(PUSHER_STATE) as f:
            pusher_state = json.load(f)
    except Exception:
        pass
    candidates.append(_parse_ts(pusher_state.get("last_interaction_at")))
    with db() as conn:
        for col in ("created_at", "completed_at"):
            row = conn.execute(
                f"SELECT MAX({col}) AS m FROM tasks").fetchone()
            candidates.append(_parse_ts(row["m"] if row else None))
        row = conn.execute("SELECT MAX(created_at) AS m FROM notes").fetchone()
        candidates.append(_parse_ts(row["m"] if row else None))
    last_interaction = max((c for c in candidates if c), default=None)
    hours_since = (now - last_interaction).total_seconds() / 3600 if last_interaction else None

    # ── App 在线状态（roro daemon state）──
    app_online = None
    try:
        with open(RORO_STATE) as f:
            app_online = bool(json.load(f).get("app_online"))
    except Exception:
        pass

    return {
        "generated_at": now.isoformat(),
        "elder": {
            "last_interaction_at": last_interaction.isoformat() if last_interaction else None,
            "hours_since_interaction": round(hours_since, 1) if hours_since is not None else None,
            "no_interaction_alert": hours_since is not None and hours_since > alert_hours,
            "alert_threshold_hours": alert_hours,
            "app_online": app_online,
            "device_channel": pusher_state.get("last_channel"),
        },
        "today": {
            "tasks_pending": query_tasks("default_user", "pending", today),
            "tasks_completed": query_tasks("default_user", "completed", today),
            "reminders_pushed": _today_pushed_reminders(),
            "family_messages": query_family_messages(10),
        },
    }


@app.post("/family/message")
def family_send_message(
    body: FamilyMessageCreate,
    x_family_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    """家人留言 → 落库 + MQTT 推送到设备（TTS 播报 + family_message 表情）。"""
    require_family(x_family_token, token)
    if not body.sender.strip() or not body.text.strip():
        raise HTTPException(400, "sender and text are required")
    record = create_family_message(body.sender.strip(), body.text.strip())

    pushed = False
    error = None
    try:
        from mqttws import MQTTWebSocket
        channel = "main"
        try:
            with open(PUSHER_STATE) as f:
                channel = json.load(f).get("last_channel") or channel
        except Exception:
            pass
        mqtt = MQTTWebSocket(MQTT_BROKER, MQTT_PORT)
        mqtt.connect(client_id=f"family-api-{os.getpid()}")
        out_topic = f'announcement/{MQTT_USER_ID}/{MQTT_DEVICE_ID}/chat/{channel}/out'
        now_ms = int(time.time() * 1000)
        # 1) assistant 文本：App 现有路径，保证 TTS 播报
        mqtt.publish(out_topic, json.dumps({
            "type": "assistant",
            "text": f"💌 {record['sender']}的留言：{record['text']}",
            "timestamp": now_ms,
        }, ensure_ascii=False))
        # 2) 结构化 family_message：协议 v1，设备播爱心表情 + 振动
        mqtt.publish(out_topic, json.dumps({
            "type": "family_message",
            "sender": record["sender"],
            "text": record["text"],
            "timestamp": now_ms,
        }, ensure_ascii=False))
        mqtt.close()
        pushed = True
    except Exception as e:
        error = str(e)

    return {"success": True, "message": record, "pushed": pushed,
            **({"push_error": error} if error else {})}


@app.get("/family/messages")
def family_messages(
    limit: int = 20,
    x_family_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    require_family(x_family_token, token)
    msgs = query_family_messages(limit)
    return {"messages": msgs, "count": len(msgs)}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8100))
    uvicorn.run(app, host="0.0.0.0", port=port)
