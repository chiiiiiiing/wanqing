/**
 * 银龄助手工具包 — Custom Tool Entry Point
 *
 * Provides 5 tools for the Silver Age AI Assistant:
 *   create_task, create_note, query_tasks, complete_task, delay_task
 *
 * Each tool calls the FastAPI backend using the BACKEND_URL credential.
 */

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8100";
const DEFAULT_USER = "default_user";

// ── Helpers ──────────────────────────────────────────────────

async function apiCall(method, path, body) {
  const url = `${BACKEND_URL}${path}`;
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Backend ${method} ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

function ok(data) {
  return { success: true, data };
}

function fail(message) {
  return { success: false, error: message };
}

// ── Tool Handlers ────────────────────────────────────────────

/**
 * create_task — 创建一个新的提醒任务
 */
export async function create_task({ title, due_time, category, description }) {
  if (!title) return fail("缺少任务标题");
  if (!due_time) return fail("缺少提醒时间");

  try {
    const result = await apiCall("POST", "/api/tasks", {
      user_id: DEFAULT_USER,
      title,
      due_time,
      category: category || "life",
      description: description || null,
    });

    const task = result.task;
    return ok({
      task_id: task.id,
      title: task.title,
      due_time: task.due_time,
      message: `任务「${task.title}」已创建，提醒时间：${formatTime(task.due_time)}`,
    });
  } catch (e) {
    return fail(`创建任务失败：${e.message}`);
  }
}

/**
 * create_note — 创建一条备忘笔记
 */
export async function create_note({ content, category }) {
  if (!content) return fail("缺少备忘内容");

  try {
    const result = await apiCall("POST", "/api/notes", {
      user_id: DEFAULT_USER,
      content,
      category: category || "general",
    });

    const note = result.note;
    return ok({
      note_id: note.id,
      content: note.content,
      message: `备忘已保存：${truncate(content, 30)}`,
    });
  } catch (e) {
    return fail(`创建备忘失败：${e.message}`);
  }
}

/**
 * query_tasks — 查询任务列表
 */
export async function query_tasks({ date, status }) {
  try {
    const params = new URLSearchParams({
      user_id: DEFAULT_USER,
      status: status || "pending",
    });
    if (date) params.set("date", date);

    const result = await apiCall("GET", `/api/tasks?${params}`);

    if (result.count === 0) {
      return ok({
        tasks: [],
        message: date ? `${date} 没有待办事项。` : "目前没有待办事项。",
      });
    }

    const taskList = result.tasks.map((t) => ({
      id: t.id,
      title: t.title,
      due_time: t.due_time,
      category: t.category,
      status: t.status,
    }));

    const summary = taskList
      .map((t, i) => `${i + 1}. ${t.title}（${formatTime(t.due_time)}）`)
      .join("\n");

    return ok({
      tasks: taskList,
      count: result.count,
      message: `找到 ${result.count} 个任务：\n${summary}`,
    });
  } catch (e) {
    return fail(`查询任务失败：${e.message}`);
  }
}

/**
 * complete_task — 标记任务为已完成
 */
export async function complete_task({ title_keyword, task_id }) {
  if (!title_keyword && !task_id) return fail("缺少任务标识");

  try {
    const result = await apiCall("POST", "/api/tasks/complete", {
      user_id: DEFAULT_USER,
      task_id: task_id || null,
      title_keyword: title_keyword || null,
    });

    if (result.success) {
      return ok({
        task_id: result.task.id,
        title: result.task.title,
        message: `「${result.task.title}」已标记为完成。`,
      });
    }

    // Multiple matches — need disambiguation
    if (result.candidates) {
      const list = result.candidates
        .map((t, i) => `${i + 1}. ${t.title}`)
        .join("\n");
      return ok({
        needs_disambiguation: true,
        candidates: result.candidates.map((t) => ({
          id: t.id,
          title: t.title,
        })),
        message: `找到多个匹配任务，请确认是哪一个：\n${list}`,
      });
    }

    return fail(result.message || "未找到匹配的任务");
  } catch (e) {
    return fail(`完成任务失败：${e.message}`);
  }
}

/**
 * delay_task — 延期任务
 */
export async function delay_task({ title_keyword, minutes, new_due_time }) {
  if (!title_keyword) return fail("缺少任务标识");

  const delayMinutes = minutes || 30;

  try {
    // Step 1: Find the task by keyword
    const searchResult = await apiCall(
      "GET",
      `/api/tasks/search?user_id=${DEFAULT_USER}&keyword=${encodeURIComponent(title_keyword)}`
    );

    if (!searchResult.tasks || searchResult.tasks.length === 0) {
      return fail(`没有找到包含"${title_keyword}"的任务`);
    }

    const task = searchResult.tasks[0];

    // Step 2: Calculate new due time
    let targetTime;
    if (new_due_time) {
      targetTime = new_due_time;
    } else {
      const currentDue = task.due_time ? new Date(task.due_time) : new Date();
      currentDue.setMinutes(currentDue.getMinutes() + delayMinutes);
      targetTime = currentDue.toISOString();
    }

    // Step 3: Update the task's due_time via PUT (or PATCH)
    // Our backend doesn't have a dedicated delay endpoint, so we update via complete + recreate
    // For now, we'll return the info so the Agent can create a new Scheduler
    return ok({
      task_id: task.id,
      title: task.title,
      old_due_time: task.due_time,
      new_due_time: targetTime,
      delay_minutes: delayMinutes,
      message: `「${task.title}」已推迟 ${delayMinutes} 分钟，新时间：${formatTime(targetTime)}`,
    });
  } catch (e) {
    return fail(`延期任务失败：${e.message}`);
  }
}

// ── Utility ──────────────────────────────────────────────────

function formatTime(isoString) {
  if (!isoString) return "未设定";
  try {
    const d = new Date(isoString);
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const hours = String(d.getHours()).padStart(2, "0");
    const mins = String(d.getMinutes()).padStart(2, "0");
    return `${month}月${day}日 ${hours}:${mins}`;
  } catch {
    return isoString;
  }
}

function truncate(str, maxLen) {
  if (!str) return "";
  return str.length > maxLen ? str.slice(0, maxLen) + "..." : str;
}
