#!/usr/bin/env python3
"""
晚晴 Custom Tools - FastAPI 服务
可部署为 Agent Stack 的 Custom Tool 后端
"""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from custom_tools import (
    init_db, create_task, query_tasks, complete_task, 
    delay_task, create_note, query_notes
)

app = FastAPI(
    title="晚晴 Tools API",
    description="任务管理、备忘管理的 REST API",
    version="1.0.0"
)

# ============ Request Models ============

class CreateTaskRequest(BaseModel):
    title: str
    due_time: Optional[str] = None
    category: str = "其他"

class QueryTasksRequest(BaseModel):
    date_range: Optional[str] = None  # today, week, all
    status: str = "pending"

class CompleteTaskRequest(BaseModel):
    task_ref: str  # task ID or title

class DelayTaskRequest(BaseModel):
    task_ref: str
    minutes: int = 30

class CreateNoteRequest(BaseModel):
    content: str
    category: str = "其他"

class QueryNotesRequest(BaseModel):
    category: Optional[str] = None

# ============ API Routes ============

@app.on_event("startup")
async def startup():
    """启动时初始化数据库"""
    init_db()

@app.get("/")
async def root():
    return {"message": "晚晴 Tools API", "status": "running"}

@app.post("/tasks/create")
async def api_create_task(req: CreateTaskRequest):
    """创建任务"""
    return create_task(req.title, req.due_time, req.category)

@app.post("/tasks/query")
async def api_query_tasks(req: QueryTasksRequest):
    """查询任务"""
    return query_tasks(req.date_range, req.status)

@app.post("/tasks/complete")
async def api_complete_task(req: CompleteTaskRequest):
    """完成任务"""
    result = complete_task(req.task_ref)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.post("/tasks/delay")
async def api_delay_task(req: DelayTaskRequest):
    """延期任务"""
    result = delay_task(req.task_ref, req.minutes)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.post("/notes/create")
async def api_create_note(req: CreateNoteRequest):
    """创建备忘"""
    return create_note(req.content, req.category)

@app.post("/notes/query")
async def api_query_notes(req: QueryNotesRequest):
    """查询备忘"""
    return query_notes(req.category)

# ============ 运行 ============

if __name__ == "__main__":
    import uvicorn
    print("🚀 启动晚晴 Tools API...")
    uvicorn.run(app, host="0.0.0.0", port=8100)
