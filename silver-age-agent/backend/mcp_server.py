"""
银龄AI助手 — MCP Server
Exposes Task/Note management tools via MCP (Model Context Protocol)
for the Agent Stack to consume.

Tools:
  - create_task: Create a reminder task
  - create_note: Create a memo note
  - query_tasks: Query task list
  - complete_task: Mark a task as done
  - delay_task: Postpone a task
"""
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

# Add parent to path so we can import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.mcpserver import MCPServer
from models.database import (
    init_db,
    create_task as db_create_task,
    get_task as db_get_task,
    query_tasks as db_query_tasks,
    complete_task as db_complete_task,
    cancel_task as db_cancel_task,
    find_task_by_title as db_find_task_by_title,
    create_note as db_create_note,
    query_notes as db_query_notes,
    create_reminder as db_create_reminder,
    get_pending_reminders as db_get_pending_reminders,
    fire_reminder as db_fire_reminder,
)

CST = timezone(timedelta(hours=8))

# Create MCP server
mcp = MCPServer(
    name="silver-age-tools",
    description="银龄AI助手的任务和备忘管理工具",
    version="0.1.0",
)


def format_time(iso_string: Optional[str]) -> str:
    """Format ISO time string to human-readable Chinese."""
    if not iso_string:
        return "未设定"
    try:
        d = datetime.fromisoformat(iso_string)
        return f"{d.month}月{d.day}日 {d.hour:02d}:{d.minute:02d}"
    except Exception:
        return iso_string


def truncate(text: str, max_len: int = 30) -> str:
    if not text:
        return ""
    return text[:max_len] + "..." if len(text) > max_len else text


# ── Tool Definitions ─────────────────────────────────────────

@mcp.tool()
def create_task(
    title: str,
    due_time: str,
    category: str = "life",
    description: str = "",
) -> str:
    """创建一个新的提醒任务并保存到数据库。
    当老人说"提醒我..."、"明天要..."、"帮我记一下..."时调用。

    Args:
        title: 任务标题，简短描述要做的事
        due_time: 到期时间，ISO 8601 格式（如 2025-08-28T15:00:00+08:00）
        category: 任务分类，可选值：health（健康）、life（生活）、social（社交）、finance（财务）、other（其他）
        description: 任务详细描述（可选）
    """
    if not title:
        return "❌ 缺少任务标题"
    if not due_time:
        return "❌ 缺少提醒时间"

    try:
        task = db_create_task(
            user_id="default_user",
            title=title,
            due_time=due_time,
            category=category,
            description=description or None,
        )
        return f"✅ 任务「{task['title']}」已创建，提醒时间：{format_time(task['due_time'])}"
    except Exception as e:
        return f"❌ 创建任务失败：{e}"


@mcp.tool()
def create_note(content: str, category: str = "general") -> str:
    """创建一条备忘笔记并保存到数据库。
    当老人说"记一下..."、"帮我记住..."时调用。备忘不需要时间。

    Args:
        content: 备忘内容
        category: 备忘分类，可选值：health（健康）、life（生活）、recipe（菜谱）、contact（联系人）、general（通用）
    """
    if not content:
        return "❌ 缺少备忘内容"

    try:
        note = db_create_note(
            user_id="default_user",
            content=content,
            category=category,
        )
        return f"✅ 备忘已保存：{truncate(content)}"
    except Exception as e:
        return f"❌ 创建备忘失败：{e}"


@mcp.tool()
def query_tasks(date: str = "", status: str = "pending") -> str:
    """查询老人的任务列表。
    当老人说"今天有什么事"、"帮我看看..."、"还有什么安排"时调用。

    Args:
        date: 查询日期，格式 YYYY-MM-DD（如 2025-08-28）。不填则查询所有待办。
        status: 任务状态筛选，可选值：pending（待办）、completed（已完成）、cancelled（已取消）
    """
    try:
        tasks = db_query_tasks(
            user_id="default_user",
            status=status,
            date=date if date else None,
        )

        if not tasks:
            if date:
                return f"📋 {date} 没有待办事项。"
            return "📋 目前没有待办事项。"

        lines = []
        for i, t in enumerate(tasks, 1):
            time_str = format_time(t.get("due_time"))
            lines.append(f"{i}. {t['title']}（{time_str}）")

        summary = "\n".join(lines)
        return f"📋 找到 {len(tasks)} 个任务：\n{summary}"
    except Exception as e:
        return f"❌ 查询任务失败：{e}"


@mcp.tool()
def complete_task(title_keyword: str, task_id: str = "") -> str:
    """将一个任务标记为已完成。
    当老人说"...做完了"、"...好了"、"已经...了"时调用。

    Args:
        title_keyword: 任务标题中的关键词，用于模糊匹配要完成的任务
        task_id: 任务的精确 ID（如果已知）
    """
    if not title_keyword and not task_id:
        return "❌ 缺少任务标识"

    try:
        if task_id:
            task = db_complete_task(task_id)
            if not task:
                return "❌ 未找到该任务"
            return f"✅ 「{task['title']}」已标记为完成。"
        
        # Fuzzy match by title
        matches = db_find_task_by_title("default_user", title_keyword)
        if not matches:
            return f"❌ 没有找到包含\u201c{title_keyword}\u201d的任务"
        if len(matches) == 1:
            task = db_complete_task(matches[0]["id"])
            return f"✅ 「{task['title']}」已标记为完成。"

        # Multiple matches
        lines = [f"{i}. {t['title']}" for i, t in enumerate(matches, 1)]
        return f"🤔 找到多个匹配任务，请确认是哪一个：\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ 完成任务失败：{e}"


@mcp.tool()
def delay_task(title_keyword: str, minutes: int = 30, new_due_time: str = "") -> str:
    """推迟一个任务的时间。
    当老人说"晚一点"、"推迟..."、"等一下再..."时调用。

    Args:
        title_keyword: 任务标题中的关键词，用于模糊匹配要延期的任务
        minutes: 推迟的分钟数，默认30分钟
        new_due_time: 新的到期时间，ISO 8601 格式（如果指定了具体新时间）
    """
    if not title_keyword:
        return "❌ 缺少任务标识"

    try:
        matches = db_find_task_by_title("default_user", title_keyword)
        if not matches:
            return f"❌ 没有找到包含\u201c{title_keyword}\u201d的任务"

        task = matches[0]
        old_time = task.get("due_time", "")

        # Calculate new time
        if new_due_time:
            target = new_due_time
        else:
            base = datetime.fromisoformat(old_time) if old_time else datetime.now(CST)
            target_dt = base + timedelta(minutes=minutes)
            target = target_dt.isoformat()

        return (
            f"✅ 「{task['title']}」已推迟 {minutes} 分钟。\n"
            f"原时间：{format_time(old_time)}\n"
            f"新时间：{format_time(target)}\n"
            f"请使用 Scheduler 工具更新提醒时间到 {target}"
        )
    except Exception as e:
        return f"❌ 延期任务失败：{e}"


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("MCP_PORT", 8200))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
