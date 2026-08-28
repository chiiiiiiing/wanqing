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
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from models.database import (
    init_db, create_task, get_task, query_tasks, complete_task, cancel_task,
    find_task_by_title, create_note, query_notes, create_reminder,
    get_pending_reminders, fire_reminder, db,
    create_family_message, query_family_messages, mark_family_message_read,
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
            "family_messages": query_family_messages(10, direction=None),
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
    via = None
    error = None
    try:
        from deliver import deliver
        with open(PUSHER_STATE) as f:
            pusher_state = json.load(f)
        tts_text = f"💌 {record['sender']}的留言：{record['text']}"
        via, _detail = deliver(pusher_state, tts_text)
        if via == "mqtt-fallback":
            # App 未托管会话时直接发布兜底
            from mqttws import MQTTWebSocket
            channel = pusher_state.get("last_channel") or "main"
            mqtt = MQTTWebSocket(MQTT_BROKER, MQTT_PORT)
            mqtt.connect(client_id=f"family-api-{os.getpid()}")
            out_topic = f'announcement/{MQTT_USER_ID}/{MQTT_DEVICE_ID}/chat/{channel}/out'
            now_ms = int(time.time() * 1000)
            mqtt.publish(out_topic, json.dumps({
                "type": "assistant",
                "text": tts_text,
                "timestamp": now_ms,
            }, ensure_ascii=False))
            # 结构化 family_message：协议 v1，设备播爱心表情 + 振动
            mqtt.publish(out_topic, json.dumps({
                "type": "family_message",
                "sender": record["sender"],
                "text": record["text"],
                "timestamp": now_ms,
            }, ensure_ascii=False))
            mqtt.close()
        pushed = True
        if via == "jsonl":
            # mirror 投递成功 = 设备将播报，语义上记为已播/已读
            mark_family_message_read(record["id"])
    except Exception as e:
        error = str(e)

    return {"success": True, "message": record, "pushed": pushed,
            "via": via,
            **({"push_error": error} if error else {})}


@app.get("/family/messages")
def family_messages(
    limit: int = 20,
    x_family_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    require_family(x_family_token, token)
    msgs = query_family_messages(limit, direction=None)
    return {"messages": msgs, "count": len(msgs)}


FAMILY_WEB_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>晚晴 · 家人关注</title>
<style>
  :root { --orange:#ea580c; --green:#059669; --red:#dc2626; --bg:#faf7f2; }
  * { margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
  body { background:var(--bg); color:#1f2937; padding:16px; max-width:640px; margin:0 auto; }
  h1 { font-size:20px; text-align:center; margin:8px 0 2px; }
  .sub { text-align:center; color:#6b7280; font-size:12px; margin-bottom:14px; }
  .card { background:#fff; border-radius:14px; padding:14px 16px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  .card h2 { font-size:14px; color:#374151; margin-bottom:10px; }
  .alert { border-left:4px solid var(--red); background:#fef2f2; }
  .ok { border-left:4px solid var(--green); background:#f0fdf4; }
  .alert .t, .ok .t { font-size:14px; font-weight:600; }
  .row { display:flex; justify-content:space-between; font-size:13px; padding:4px 0; color:#4b5563; }
  .row b { color:#111827; }
  input,textarea,button { width:100%; border:1px solid #d1d5db; border-radius:10px; padding:10px; font-size:14px; margin-bottom:8px; }
  button { background:var(--orange); color:#fff; border:none; font-weight:600; }
  button:disabled { opacity:.6; }
  .msg { border-bottom:1px solid #f3f4f6; padding:8px 0; font-size:13px; }
  .msg .meta { color:#6b7280; font-size:11px; display:flex; justify-content:space-between; }
  .badge { border-radius:8px; padding:1px 6px; font-size:10px; }
  .badge.reply { background:#fff7ed; color:#ea580c; }
  .unread { background:#fef3c7; color:#92400e; }
  .read { background:#e5e7eb; color:#6b7280; }
  .chip { display:inline-block; background:#fff7ed; border:1px solid #fed7aa; color:#9a3412; border-radius:10px; padding:2px 8px; font-size:11px; margin:2px 4px 2px 0; }
  #toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#111827; color:#fff; border-radius:10px; padding:8px 16px; font-size:13px; opacity:0; transition:opacity .3s; pointer-events:none; }
</style>
</head>
<body>
<h1>晚晴 · 家人关注</h1>
<div class="sub">妈妈今天的状态，一目了然</div>

<div class="card" id="alertCard"></div>

<div class="card">
  <h2>💌 给妈妈留言</h2>
  <input id="sender" placeholder="你的名字（如：女儿）" value="女儿">
  <textarea id="text" rows="3" placeholder="想对妈妈说的话…"></textarea>
  <button id="send">发送留言到设备</button>
</div>

<div class="card">
  <h2>📋 今日动态</h2>
  <div id="today"></div>
</div>

<div class="card">
  <h2>🗒️ 留言记录</h2>
  <div id="msgs"></div>
</div>

<div id="toast"></div>

<script>
const tok = new URLSearchParams(location.search).get('token') || '';
const H = {'X-Family-Token': tok, 'Content-Type':'application/json'};
async function api(path, opt) {
  const r = await fetch(path, Object.assign({headers:H}, opt));
  if (r.status === 401) { toast('token 无效'); throw new Error('401'); }
  return r.json();
}
function toast(t) { const el = document.getElementById('toast'); el.textContent = t; el.style.opacity = 1; setTimeout(()=>el.style.opacity=0, 2200); }
function esc(s) { return (s||'').replace(/[<>&"]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c])); }

async function refresh() {
  const rep = await api('/family/report');
  const e = rep.elder;
  const ac = document.getElementById('alertCard');
  if (e.no_interaction_alert) {
    ac.className = 'card alert';
    ac.innerHTML = '<div class="t">⚠️ 超过 ' + e.alert_threshold_hours + ' 小时没有互动</div>' +
      '<div class="row"><span>最近互动</span><b>' + (e.hours_since_interaction!=null? e.hours_since_interaction+' 小时前':'未知') + '</b></div>' +
      '<div class="row"><span>建议</span><b>打个电话问候一下</b></div>';
  } else {
    ac.className = 'card ok';
    ac.innerHTML = '<div class="t">✅ 互动正常</div>' +
      '<div class="row"><span>最近互动</span><b>' + (e.hours_since_interaction!=null? e.hours_since_interaction+' 小时前':'暂无记录') + '</b></div>' +
      '<div class="row"><span>手机 App</span><b>' + (e.app_online? '在线':'离线') + '</b></div>';
  }
  const t = rep.today;
  const pend = t.tasks_pending.map(x=>'<span class="chip">'+esc(x.title)+'</span>').join('') || '<span class="chip">暂无待办</span>';
  const pushed = t.reminders_pushed.map(x=>'<div class="row"><span>⏰ '+esc(x.title)+'</span><b>'+x.time.slice(11)+'</b></div>').join('') || '<div class="row"><span>今日已推送提醒</span><b>0 条</b></div>';
  document.getElementById('today').innerHTML =
    '<div class="row"><span>待办事项</span></div><div style="margin-bottom:8px">'+pend+'</div>' +
    '<div class="row"><span>今日已完成</span><b>'+t.tasks_completed.length+' 件</b></div>' + pushed;
  document.getElementById('msgs').innerHTML = t.family_messages.map(m =>
    '<div class="msg"><div class="meta"><span>'+esc(m.sender)+' · '+m.created_at.slice(5,16).replace('T',' ')+'</span>' +
    (m.direction==='elder_to_family'
      ? '<span class="badge reply">妈妈回复</span>'
      : '<span class="badge '+(m.read_at?'read':'unread')+'">'+(m.read_at?'已播':'未播')+'</span>')+'</div>' +
    '<div>'+esc(m.text)+'</div></div>'
  ).join('') || '<div class="row"><span>暂无留言</span></div>';
}

document.getElementById('send').onclick = async () => {
  const sender = document.getElementById('sender').value.trim();
  const text = document.getElementById('text').value.trim();
  if (!sender || !text) return toast('请填写名字和留言');
  const btn = document.getElementById('send'); btn.disabled = true;
  try {
    const r = await api('/family/message', {method:'POST', body: JSON.stringify({sender, text})});
    toast(r.pushed ? '已发送，设备将播报' : '已保存（设备暂离线）');
    document.getElementById('text').value = '';
    refresh();
  } catch(e) { toast('发送失败'); }
  btn.disabled = false;
};

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
"""


@app.get("/family/web", response_class=HTMLResponse)
def family_web():
    """家人关注网页入口：浏览器打开 /family/web?token=xxx 即可留言/看日报。
    链接即钥匙（token 在 URL 中），勿外泄。"""
    return FAMILY_WEB_HTML


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8100))
    uvicorn.run(app, host="0.0.0.0", port=port)
