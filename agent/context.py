from contextvars import ContextVar

_chat_id_var: ContextVar[int] = ContextVar('chat_id', default=0)
_session_id_var: ContextVar[str] = ContextVar('session_id', default='')


def get_current_chat_id() -> int:
    return _chat_id_var.get()


def set_current_chat_id(chat_id: int):
    return _chat_id_var.set(chat_id)


def get_current_session_id() -> str:
    return _session_id_var.get()


def set_current_session_id(session_id: str):
    return _session_id_var.set(session_id)
