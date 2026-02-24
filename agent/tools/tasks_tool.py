import json
from langchain_core.tools import tool
from services import google_tasks as gtasks


@tool
def get_tasks() -> str:
    """
    Get all active (incomplete) Google Tasks.
    Returns JSON array of tasks with id, title, due, notes, status fields.
    """
    try:
        tasks = gtasks.list_tasks()
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
    except Exception as e:
        return f"Ошибка при получении задач: {e}"


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
        task = gtasks.create_task(title, due, notes, parent_id)
        return f"✅ Задача создана: {task['title']} (id: {task['id']}, due: {task.get('due', 'не задано')})"
    except Exception as e:
        return f"Ошибка при создании задачи: {e}"


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
        fields = {}
        if title:
            fields['title'] = title
        if due:
            fields['due'] = due
        if notes is not None:
            fields['notes'] = notes
        if status:
            fields['status'] = status
        task = gtasks.update_task(task_id, **fields)
        return f"✅ Задача обновлена: {task.get('title')} (id: {task_id})"
    except Exception as e:
        return f"Ошибка при обновлении задачи: {e}"


@tool
def delete_task(task_id: str) -> str:
    """Delete a Google Task by task_id."""
    try:
        gtasks.delete_task(task_id)
        return f"✅ Задача удалена (id: {task_id})"
    except Exception as e:
        return f"Ошибка при удалении задачи: {e}"
