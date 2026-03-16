import json
import logging
from langchain_core.tools import tool
from services import google_tasks as gtasks
from services.google_auth import GoogleAuthExpiredError
from db.database import get_conn
from db.models import push_undo, add_event_task_link
from agent.context import get_current_chat_id, get_current_session_id

_AUTH_ERROR_MSG = "❌ Авторизация Google истекла. Отправь /connect для повторной авторизации."


@tool
def get_tasks() -> str:
    """
    Get all active (incomplete) Google Tasks.
    Returns JSON array of tasks with id, title, due, notes, status fields.
    """
    try:
        chat_id = get_current_chat_id()
        tasks = gtasks.list_tasks(chat_id)
        result = []
        for t in tasks:
            result.append({
                "id": t.get("id"),
                "title": t.get("title", ""),
                "due": t.get("due"),
                "notes": t.get("notes"),
                "status": t.get("status"),
            })
        return json.dumps(result, ensure_ascii=False)
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при получении задач: {e}"


@tool
def create_task(
    title: str,
    due: str = None,
    notes: str = None,
    parent_id: str = None,
) -> str:
    """
    Create a Google Task.
    title: task title (use user's exact words).
    due: ISO 8601 UTC datetime. If no date given by user use today T00:00:00Z.
         If date only (no time) use date T00:00:00Z.
         If date + time convert to UTC (subtract timezone offset).
    notes: optional description.
    parent_id: optional parent task ID for subtasks.
    IMPORTANT: always set due date. Never omit it.
    """
    try:
        chat_id = get_current_chat_id()
        task = gtasks.create_task(chat_id, title, due, notes, parent_id)
        push_undo(get_conn(), chat_id, 'create_task', task['id'], task['title'], get_current_session_id())
        return f"✅ Задача создана: {task['title']} (id: {task['id']}, due: {task.get('due', 'не задано')})"
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при создании задачи: {e}"


@tool
def update_task(
    task_id: str,
    title: str = None,
    due: str = None,
    notes: str = None,
    status: str = None,
) -> str:
    """
    Update an existing Google Task by task_id.
    Only provide fields that need changing.
    status: 'completed' to mark task as done, 'needsAction' to reopen.
    Use this for: adding/changing deadline, renaming, adding notes, completing.
    Examples: "добавь срок на пятницу", "поменяй название", "отметь выполненной".
    """
    try:
        chat_id = get_current_chat_id()
        fields = {}
        if title:
            fields['title'] = title
        if due:
            fields['due'] = due
        if notes is not None:
            fields['notes'] = notes
        if status:
            fields['status'] = status
        if not fields:
            return "❌ Не указано ни одного поля для обновления задачи."
        task = gtasks.update_task(chat_id, task_id, **fields)
        return f"✅ Задача обновлена: {task.get('title')} (id: {task_id})"
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при обновлении задачи: {e}"


@tool
def complete_task(task_id: str) -> str:
    """
    Mark a Google Task as completed (done).
    Use when user says: "выполнил", "сделал", "готово", "отметь выполненной", "зачеркни".
    Keeps the task in Google Tasks history (unlike delete which removes it entirely).
    """
    try:
        chat_id = get_current_chat_id()
        task = gtasks.complete_task(chat_id, task_id)
        push_undo(get_conn(), chat_id, 'complete_task', task_id, task.get('title', task_id), get_current_session_id())
        return f"✅ Задача выполнена: {task.get('title')} (id: {task_id})"
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при выполнении задачи: {e}"


@tool
def delete_task(task_id: str) -> str:
    """
    Delete a Google Task by task_id. Use only when user explicitly says 'удали задачу'.
    For 'выполнил'/'сделал'/'готово' — use complete_task instead.
    """
    try:
        chat_id = get_current_chat_id()
        gtasks.delete_task(chat_id, task_id)
        return f"✅ Задача удалена (id: {task_id})"
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при удалении задачи: {e}"


@tool
def create_task_for_event(
    event_id: str,
    event_summary: str,
    event_start_utc: str,
    title: str,
    notes: str = None,
) -> str:
    """
    Create a Google Task linked to a specific calendar event.
    Use when user says: "добавь задачу к событию", "привяжи задачу к встрече",
    "к этому событию нужно сделать X", "добавь к встрече задачу".
    Do NOT use create_task when the user links a task to a calendar event — use
    create_task_for_event instead to ensure the notification link is stored.
    event_id: calendar event ID (get via get_calendar_events if not known).
    event_summary: event title (from get_calendar_events or conversation context).
    event_start_utc: event start datetime in ISO 8601 UTC, e.g. "2026-03-18T09:50:00Z".
    title: task title (use user's exact words).
    notes: optional extra description.
    The user will receive a Telegram reminder ~4 hours before the event.
    """
    try:
        chat_id = get_current_chat_id()
        due = event_start_utc[:10] + "T00:00:00Z"
        task = gtasks.create_task(chat_id, title, due, notes)
        try:
            conn = get_conn()
            add_event_task_link(
                conn,
                chat_id=chat_id,
                event_id=event_id,
                task_id=task['id'],
                event_summary=event_summary,
                event_start_utc=event_start_utc,
                task_title=title,
            )
            push_undo(conn, chat_id, 'create_task', task['id'], title, get_current_session_id())
        except Exception as db_err:
            logging.getLogger(__name__).error(
                "event_task_link DB write failed for task %s: %s", task['id'], db_err
            )
            try:
                gtasks.delete_task(chat_id, task['id'])
            except Exception:
                pass
            return f"❌ Не удалось сохранить привязку задачи к событию: {db_err}"
        return (
            f"✅ Задача создана и привязана к событию «{event_summary}»: "
            f"{title} (id: {task['id']}). Напомню за 4 часа до начала."
        )
    except GoogleAuthExpiredError:
        return _AUTH_ERROR_MSG
    except Exception as e:
        return f"❌ Ошибка при создании задачи: {e}"
