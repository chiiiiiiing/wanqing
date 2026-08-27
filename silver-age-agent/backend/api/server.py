"""
银龄AI助手 — FastAPI Backend
REST API for Task/Note management and Scheduler integration.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from contextlib import asynccontextmanager

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from models.database import (
    init_db, create_task, get_task, query_tasks, complete_task, cancel_task,
    find_task_by_title, create_note, query_notes, create_reminder,
    get_pending_reminders, fire_reminder, db
)

CST = timezone(timedelta(hours=8))

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="银龄AI助手 API",
    description="Task, Note and Reminder management for Silver Age AI Assistant",
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8100))
    uvicorn.run(app, host="0.0.0.0", port=port)
