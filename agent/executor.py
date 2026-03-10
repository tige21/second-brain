import asyncio
import json
import sqlite3
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from config import OPENAI_API_KEY, OPENAI_MODEL, TIMEZONE_OFFSET, OPENAI_PROXY_URL
from db.database import get_conn
from db.models import load_memory, save_memory, get_setting, get_address, list_addresses
from agent.system_prompt import build_system_prompt
from agent.prefetch import prefetch_context
from agent.context import set_current_chat_id, set_current_session_id, _chat_id_var, _session_id_var
from agent.tools.calendar_tool import get_calendar_events, create_calendar_event, update_calendar_event, delete_calendar_event, delete_future_occurrences, delete_single_occurrence, exclude_recurring_weekday
from agent.tools.tasks_tool import get_tasks, create_task, update_task, complete_task, delete_task
from agent.tools.batch_delete import batch_delete_events, deduplicate_recurring_events
from agent.tools.route_tool import calculate_route
from agent.tools.address_book import address_book
from agent.tools.reminder_tool import set_reminder
from agent.tools.think import think

TOOLS = [
    get_calendar_events,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    delete_future_occurrences,
    delete_single_occurrence,
    exclude_recurring_weekday,
    batch_delete_events,
    deduplicate_recurring_events,
    get_tasks,
    create_task,
    update_task,
    complete_task,
    delete_task,
    calculate_route,
    address_book,
    set_reminder,
    think,
]

_llm = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0.3,
    max_tokens=8192,
    api_key=OPENAI_API_KEY,
)

_prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_message}"),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

_agent = create_openai_tools_agent(_llm, TOOLS, _prompt)

_executor = AgentExecutor(
    agent=_agent,
    tools=TOOLS,
    verbose=False,
    handle_parsing_errors=True,
    max_iterations=15,
    return_intermediate_steps=False,
)


def _load_langchain_history(chat_id: int) -> list[BaseMessage]:
    conn = get_conn()
    raw = load_memory(conn, chat_id)
    messages: list[BaseMessage] = []
    for msg in raw:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    return messages


def _save_to_memory(chat_id: int, user_msg: str, assistant_msg: str, window: int = 6) -> None:
    conn = get_conn()
    current = load_memory(conn, chat_id)
    current.append({"role": "user", "content": user_msg})
    current.append({"role": "assistant", "content": assistant_msg})
    trimmed = current[-(window * 2):]
    save_memory(conn, chat_id, trimmed)


def _get_address_context(conn: sqlite3.Connection, chat_id: int) -> dict[str, str]:
    active_name = get_setting(conn, chat_id, 'active_address') or ''
    active_addr = get_address(conn, chat_id, active_name) if active_name else None
    active_str = f"{active_name}: {active_addr['address']}" if active_addr else "не задан"

    all_addrs = list_addresses(conn, chat_id)
    saved_str = json.dumps(
        {a['name']: a['address'] for a in all_addrs},
        ensure_ascii=False
    ) if all_addrs else "{}"

    pending_json = get_setting(conn, chat_id, 'pending_location') or ''
    pending_str = "нет"
    if pending_json:
        try:
            p = json.loads(pending_json)
            pending_str = p.get('address', p.get('coords', 'есть'))
        except Exception:
            pending_str = "есть"

    return {
        "active_address": active_str,
        "saved_addresses": saved_str,
        "pending_location": pending_str,
    }


async def run_agent(chat_id: int, user_message: str) -> str:
    """Run the AI agent for a given message. Returns response text."""
    import uuid
    session_id = uuid.uuid4().hex

    token_chat = set_current_chat_id(chat_id)
    token_session = set_current_session_id(session_id)

    try:
        conn = get_conn()
        context = await asyncio.to_thread(prefetch_context, chat_id)
        addr_ctx = _get_address_context(conn, chat_id)
        tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or TIMEZONE_OFFSET)

        system_message = build_system_prompt(
            today_events=context['today_events'],
            today_tasks=context['today_tasks'],
            timezone_offset=tz_offset,
            **addr_ctx,
        )

        chat_history = _load_langchain_history(chat_id)

        result = await _executor.ainvoke({
            "input": user_message,
            "system_message": system_message,
            "chat_history": chat_history,
        })

        response = result.get("output", "Нет ответа")
        _save_to_memory(chat_id, user_message, response)
        return response
    finally:
        _chat_id_var.reset(token_chat)
        _session_id_var.reset(token_session)
