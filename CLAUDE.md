# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot ("Second Brain") that manages Google Calendar and Google Tasks via natural language in Russian. Built with python-telegram-bot, LangChain (OpenAI tools agent), and Google APIs. Multi-user with admin approval. SQLite for persistence.

## Commands

```bash
# Run the bot
python main.py

# Run tests
pytest
pytest tests/test_agent_live.py -v    # single file

# Install dependencies
pip install -r requirements.txt
```

No linter or formatter is configured. pytest uses `asyncio_mode = auto` (see `pytest.ini`).

## Architecture

**Message flow:** Telegram message → `bot/router.py` (auth + rate limit) → handler (`bot/handlers/`) → `agent/executor.py::run_agent()` → LangChain agent with tools → response formatted as HTML → sent back.

**Key modules:**
- `agent/executor.py` — Creates the LangChain `AgentExecutor`, loads chat history, prefetches calendar/task context into the system prompt, invokes the agent, saves to memory
- `agent/system_prompt.py` — Extensive Russian-language system prompt with 10 numbered rules governing agent behavior (time formats, deduplication, route modes, etc.)
- `agent/tools/` — LangChain `@tool` functions for calendar CRUD, task CRUD, routes, address book, reminders, and a `think` tool for long voice messages
- `agent/context.py` — Python `contextvars` for passing `chat_id` and `session_id` to tools without threading them through function args
- `bot/router.py` — Single entry point for all Telegram messages; handles auth checks, rate limiting, routing to text/voice/location handlers
- `services/` — Wrappers around external APIs (Google Calendar, Google Tasks, Whisper STT, Yandex geocoder, OSRM routing)
- `db/` — SQLite layer with auto-migration (`database.py`) and CRUD functions (`models.py`)
- `schedulers/` — 6 APScheduler jobs registered in `main.py`: morning/evening summaries, reminder checks (1min), departure checks (15min), event-task notifications (15min), token refresh check (daily)

**Data scoping:** All user data (tokens, addresses, settings, conversation memory) is scoped by `chat_id`. Context vars set in `executor.py` make `chat_id` available to tools without explicit passing.

**Timezone handling:** Times stored in UTC. User input is in local time; tools convert using `timezone_offset` from user settings (default UTC+3 MSK). No DST support — offset-based only.

**Conversation memory:** Sliding window of last 6 exchanges (12 messages) stored as JSON in `conversation_memory` table, loaded before each agent invocation.

## Environment

Requires `.env` file (see `config.py` for all variables). Key required vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (owner), `OPENAI_API_KEY`. Optional: `OPENAI_PROXY_URL`, `OPENAI_MODEL` (default `gpt-4o-mini`).

## Deployment

`deploy.sh` handles server deployment. `second-brain.service` is the systemd unit file. Logs via `journalctl -u second-brain -f`.

## Installed Agents & Skills

**Subagents** (`.claude/agents/`): frontend-developer, ui-designer, api-designer, backend-developer, fullstack-developer, react-specialist, typescript-pro, python-pro, fastapi-developer, qa-expert, accessibility-tester, performance-engineer, code-reviewer.

**Skills** (`.claude/skills/`): react-best-practices, web-design-guidelines, composition-patterns, react-view-transitions, frontend-design, webapp-testing, theme-factory, playwright-best-practices, deploy-to-vercel, and others.

### Rules for Using Agents & Skills

- **On every design/architecture iteration:** validate decisions against relevant agent guidelines (api-designer, fastapi-developer, react-specialist, etc.)
- **Before writing frontend code:** invoke `frontend-design` skill for UI quality; follow `react-best-practices` and `composition-patterns` skill guidelines
- **Before writing backend code:** follow `fastapi-developer` and `api-designer` agent patterns (async-first, Pydantic v2, dependency injection, repository+service pattern)
- **After completing a feature:** run `code-reviewer` agent and `webapp-testing` skill checks
- **For UI components:** use `accessibility-tester` agent guidelines, follow `web-design-guidelines` skill
- **For performance:** consult `performance-engineer` agent on bundle size, lazy loading, caching strategies
