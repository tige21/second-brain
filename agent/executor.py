import json
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from config import OPENAI_API_KEY, OPENAI_MODEL, TIMEZONE_OFFSET
from db.database import get_conn
from db.models import load_memory, save_memory, get_setting, get_address, list_addresses
from agent.system_prompt import build_system_prompt
from agent.prefetch import prefetch_context
from agent.tools.calendar_tool import get_calendar_events, create_calendar_event, update_calendar_event
from agent.tools.tasks_tool import get_tasks, create_task, update_task, delete_task
from agent.tools.batch_delete import batch_delete_events
from agent.tools.route_tool import calculate_route
from agent.tools.address_book import address_book
from agent.tools.think import think

TOOLS = [
    get_calendar_events,
    create_calendar_event,
    update_calendar_event,
    batch_delete_events,
    get_tasks,
    create_task,
    update_task,
    delete_task,
    calculate_route,
    address_book,
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


def _load_langchain_history(chat_id: int) -> list:
    conn = get_conn()
    raw = load_memory(conn, chat_id)
    messages = []
    for msg in raw:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    return messages


def _save_to_memory(chat_id: int, user_msg: str, assistant_msg: str, window: int = 3) -> None:
    conn = get_conn()
    current = load_memory(conn, chat_id)
    current.append({"role": "user", "content": user_msg})
    current.append({"role": "assistant", "content": assistant_msg})
    trimmed = current[-(window * 2):]
    save_memory(conn, chat_id, trimmed)


def _get_address_context(conn) -> dict:
    active_name = get_setting(conn, 'active_address') or ''
    active_addr = get_address(conn, active_name) if active_name else None
    active_str = f"{active_name}: {active_addr['address']}" if active_addr else "не задан"

    all_addrs = list_addresses(conn)
    saved_str = json.dumps(
        {a['name']: a['address'] for a in all_addrs},
        ensure_ascii=False
    ) if all_addrs else "{}"

    pending_json = get_setting(conn, 'pending_location') or ''
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
    conn = get_conn()
    context = prefetch_context()
    addr_ctx = _get_address_context(conn)
    tz_offset = int(get_setting(conn, 'timezone_offset') or TIMEZONE_OFFSET)

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
