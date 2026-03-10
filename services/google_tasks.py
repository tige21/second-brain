from datetime import datetime, timezone
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential
from services.google_auth import get_credentials
from config import GOOGLE_TASKS_LIST_ID


def _service(chat_id: int):
    return build('tasks', 'v1', credentials=get_credentials(chat_id))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def list_tasks(chat_id: int, show_completed: bool = False) -> list[dict]:
    result = _service(chat_id).tasks().list(
        tasklist=GOOGLE_TASKS_LIST_ID,
        showCompleted=show_completed,
        maxResults=100,
    ).execute()
    return result.get('items', [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def create_task(
    chat_id: int,
    title: str,
    due: str = None,
    notes: str = None,
    parent: str = None,
) -> dict:
    if not due:
        due = datetime.now(timezone.utc).strftime('%Y-%m-%dT00:00:00Z')
    body = {'title': title, 'due': due}
    if notes:
        body['notes'] = notes
    kwargs = {'tasklist': GOOGLE_TASKS_LIST_ID, 'body': body}
    if parent:
        kwargs['parent'] = parent
    return _service(chat_id).tasks().insert(**kwargs).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def update_task(chat_id: int, task_id: str, **fields) -> dict:
    svc = _service(chat_id)
    task = svc.tasks().get(tasklist=GOOGLE_TASKS_LIST_ID, task=task_id).execute()
    task.update(fields)
    return svc.tasks().update(
        tasklist=GOOGLE_TASKS_LIST_ID, task=task_id, body=task
    ).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def delete_task(chat_id: int, task_id: str) -> None:
    _service(chat_id).tasks().delete(tasklist=GOOGLE_TASKS_LIST_ID, task=task_id).execute()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def complete_task(chat_id: int, task_id: str) -> dict:
    return update_task(chat_id, task_id, status='completed')
