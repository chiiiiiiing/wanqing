#!/usr/bin/env python3
"""
晚晴 Custom Tools
提供任务管理、备忘管理的 REST API
"""

import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional
from contextlib import contextmanager

# 数据库路径
DB_PATH = os.path.expanduser("~/.roro/wanqing.db")

# 初始化数据库
def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, 'r') as f:
        schema = f.read()
    
    with get_db() as conn:
        conn.executescript(schema)
    print(f"✅ 数据库初始化完成: {DB_PATH}")

@contextmanager
def get_db():
    """数据库连接上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

# ============ 任务管理 ============

def create_task(title: str, due_time: Optional[str] = None, category: str = "其他") -> dict:
    """创建任务"""
    task_id = str(uuid.uuid4())[:8]
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, title, due_time, category, status) VALUES (?, ?, ?, ?, 'pending')",
            (task_id, title, due_time, category)
        )
    
    return {
        "success": True,
        "task_id": task_id,
        "title": title,
        "due_time": due_time,
        "category": category
    }

def query_tasks(date_range: Optional[str] = None, status: str = "pending") -> dict:
    """查询任务"""
    with get_db() as conn:
        if date_range == "today":
            today = datetime.now().strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? AND date(due_time) = ? ORDER BY due_time",
                (status, today)
            ).fetchall()
        elif date_range == "week":
            week_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? AND date(due_time) <= ? ORDER BY due_time",
                (status, week_end)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY due_time",
                (status,)
            ).fetchall()
        
        tasks = [dict(row) for row in rows]
    
    return {
        "success": True,
        "count": len(tasks),
        "tasks": tasks
    }

def complete_task(task_ref: str) -> dict:
    """完成任务（通过 ID 或标题模糊匹配）"""
    with get_db() as conn:
        # 先尝试精确匹配 ID
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_ref,)).fetchone()
        
        # 如果没找到，尝试模糊匹配标题
        if not row:
            row = conn.execute(
                "SELECT * FROM tasks WHERE title LIKE ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
                (f"%{task_ref}%",)
            ).fetchone()
        
        if not row:
            return {"success": False, "error": f"未找到任务: {task_ref}"}
        
        # 更新状态
        conn.execute(
            "UPDATE tasks SET status = 'completed', updated_at = datetime('now', 'localtime') WHERE id = ?",
            (row["id"],)
        )
        
        return {
            "success": True,
            "task_id": row["id"],
            "title": row["title"],
            "message": f"已完成: {row['title']}"
        }

def delay_task(task_ref: str, minutes: int = 30) -> dict:
    """延期任务"""
    with get_db() as conn:
        # 查找任务
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_ref,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM tasks WHERE title LIKE ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
                (f"%{task_ref}%",)
            ).fetchone()
        
        if not row:
            return {"success": False, "error": f"未找到任务: {task_ref}"}
        
        # 计算新时间
        if row["due_time"]:
            old_time = datetime.fromisoformat(row["due_time"])
        else:
            old_time = datetime.now()
        
        new_time = old_time + timedelta(minutes=minutes)
        new_time_str = new_time.strftime("%Y-%m-%dT%H:%M:%S")
        
        # 更新
        conn.execute(
            "UPDATE tasks SET due_time = ?, status = 'delayed', updated_at = datetime('now', 'localtime') WHERE id = ?",
            (new_time_str, row["id"])
        )
        
        return {
            "success": True,
            "task_id": row["id"],
            "title": row["title"],
            "old_time": row["due_time"],
            "new_time": new_time_str,
            "message": f"已延期到: {new_time.strftime('%Y年%m月%d日 %H:%M')}"
        }

# ============ 备忘管理 ============

def create_note(content: str, category: str = "其他") -> dict:
    """创建备忘"""
    note_id = str(uuid.uuid4())[:8]
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO notes (id, content, category) VALUES (?, ?, ?)",
            (note_id, content, category)
        )
    
    return {
        "success": True,
        "note_id": note_id,
        "content": content,
        "category": category
    }

def query_notes(category: Optional[str] = None) -> dict:
    """查询备忘"""
    with get_db() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM notes WHERE category = ? ORDER BY created_at DESC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY created_at DESC"
            ).fetchall()
        
        notes = [dict(row) for row in rows]
    
    return {
        "success": True,
        "count": len(notes),
        "notes": notes
    }

# ============ 测试 ============

if __name__ == "__main__":
    import json
    
    # 初始化数据库
    init_db()
    
    print("\n=== 测试 Custom Tools ===\n")
    
    # 测试创建任务
    print("1. 创建任务:")
    result = create_task("买菜", "2026-08-28T15:00:00", "生活")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 测试创建备忘
    print("\n2. 创建备忘:")
    result = create_note("鸡蛋快没了", "生活")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 测试查询任务
    print("\n3. 查询今日任务:")
    result = query_tasks("today")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 测试完成任务
    print("\n4. 完成任务:")
    result = complete_task("买菜")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 测试查询所有任务
    print("\n5. 查询所有任务:")
    result = query_tasks()
    print(json.dumps(result, ensure_ascii=False, indent=2))
