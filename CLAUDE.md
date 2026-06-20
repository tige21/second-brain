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

## Hard-won rules (Second Brain PWA `/Users/macbook/Documents/projects/second-brain-web/`)

These are not style preferences. Each rule maps to a real bug that took 15+ minutes to find. Read this list before touching the relevant area.

### Deployment

- **Backend systemd path = `/root/second-brain-pwa/backend/`**, NOT `/var/www/second-brain-api/`. Verify with `systemctl cat second-brain-pwa | grep WorkingDirectory` if unsure. The frontend still goes to `/var/www/second-brain-pwa/`. Both paths are documented in `SERVER.md`.
- After every backend deploy, restart with `systemctl restart second-brain-pwa` AND tail logs (`journalctl -u second-brain-pwa -n 30`) to confirm clean startup before claiming "done".
- Never claim a fix is deployed without verifying via Playwright or curl that the actual served bundle/code reflects the change. Bundle hash in `<script src>` is a quick check.
- **After `rsync`-ing backend `.py` files, clear the bytecode cache before restart: `ssh … 'find /root/second-brain-pwa/backend/app -name __pycache__ -type d -prune -exec rm -rf {} +'`.** `rsync -a` preserves the *local* file's mtime; if that mtime is older than the server's cached `__pycache__/*.pyc` (e.g. the file was edited locally before a prior deploy recompiled it on the server), Python loads the STALE bytecode and silently runs old code — the `.py` on disk is correct (grep passes) but the new migration/endpoint never executes. Symptom we hit on the grammar-drills deploy: `_migrate_grammar_drills` didn't add its column, `PRAGMA table_info` showed the old schema, even though `grep` confirmed the function was in the deployed `main.py`. Verify the migration actually ran via `PRAGMA table_info(<table>)`, not just service "active". Clearing `__pycache__` (or rsyncing without `-t`) forces a fresh recompile of the whole app.
- **A backend endpoint that reads `await request.form()` or uses FastAPI `File`/`Form`/`UploadFile` params needs `python-multipart` installed in the server venv** — it is NOT a transitive dep of fastapi/starlette and was missing on the prod venv even though `/api/voice` already uses `request.form()`. Without it, the form parse raises at runtime (or, for `File`/`Form` route params, fails at route-registration/import → the app won't start). Add it to `backend/pyproject.toml` and `pip install python-multipart` in `/root/second-brain-pwa/backend/.venv`. Verify with `.venv/bin/python -c "import multipart"`. Discovered on the speaking-drill deploy. (Reading multipart via `request.form()` instead of `File`/`Form` params avoids the import-time failure for local tests where the package may be absent — but the runtime still needs it on the server.)
- **Make the LLM model for a new feature configurable with a fallback, never hardcode an unverified model id.** The speaking analysis model is `settings.english_analysis_model or settings.openai_model` (empty env → fall back to the proven `gpt-4o-mini`). When the owner requested `gpt-5.4-lite`, the provider returned `404 model_not_found`; because the id was a *configurable env var with fallback* (not hardcoded), leaving `ENGLISH_ANALYSIS_MODEL` unset kept the feature working on `gpt-4o-mini` instead of hard-breaking. Always smoke-test a requested model in-process (one real call) before wiring it into `.env`.

### Service Worker + React Query (the most painful trap)

- **Any `/api/*` endpoint the user mutates from the UI MUST be `NetworkOnly` in `frontend/vite.config.ts` workbox `runtimeCaching`.** Both `StaleWhileRevalidate` and `NetworkFirst` will silently serve pre-mutation JSON to React Query — SWR always, NetworkFirst every time the network timeout fires (very common on DPI-throttled links from Russia). The symptom: "I toggled X, saw the success toast, refreshed, and X reverted." Offline reads are covered by `PersistQueryClientProvider` (IDB), so dropping the SW layer for mutable data costs nothing.
- Only genuinely immutable assets (fonts, avatars) belong in `StaleWhileRevalidate`/`CacheFirst`.
- Push subscribe/unsubscribe (`sw/register.ts`) MUST call `fetchWithAuth`, never raw `fetch`. Raw `fetch` skips the 401 refresh flow, so a stale JWT silently fails the POST `/api/push/subscribe` while the caller happily sets `notification_prefs.enabled = true` — we end up with an empty `push_subscriptions` table and a toggle that appears to work.
- After changing workbox rules, the new SW takes a full page reload to activate. For testing locally, unregister the old SW and clear caches via DevTools or programmatically: `caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k))))`.
- The `controllerchange` listener in `frontend/src/main.tsx` auto-reloads when a new SW takes control — don't remove it.
- **When a `staleTime: Infinity` reference query's response SHAPE changes (new fields), bump a version segment in its `queryKey` (e.g. `['english','grammar']` → `['english','grammar','v2']`) — or bump `RQ_PERSIST_BUSTER` in `frontend/src/lib/persist-client.ts`.** `PersistQueryClientProvider` dehydrates every query except keys `chat`/`voice`/`auth` into IDB (7-day maxAge), and `staleTime: Infinity` means it never refetches on mount/focus. So after you add fields server-side + force-reseed, a user who opened the screen in the last week rehydrates the OLD-shape payload forever and the new fields never appear ("I redeployed, the data is correct in the DB and the API, but the page still shows the old flat version"). `NetworkOnly` on the endpoint does NOT save you here — the SW is bypassed but RQ never makes the request. Bumping the key forces a one-time fresh fetch; the buster nukes all persisted cache once. This bit us on the rich-grammar deploy.

### Mutations & user feedback

- **Every React Query mutation hook MUST have both `onSuccess` and `onError` with `showToast(...)`** (`frontend/src/components/toast.tsx`). Silent failures are forbidden — they were the #1 source of "I clicked save and nothing happened" reports.
- For mutations that should refresh other queries, prefer `await queryClient.refetchQueries(...)` inside the `mutationFn` over `invalidateQueries` in `onSuccess`. `invalidate` is lazy and easy to lose to component remount races.
- Optimistic updates must `await queryClient.cancelQueries(...)` BEFORE snapshotting state. See `useDeleteEvent` in `frontend/src/hooks/use-events.ts` for the canonical pattern.

### Google API integration

- All `googleapiclient` `.execute()` calls in `backend/app/services/google_calendar.py` and `google_tasks.py` MUST be wrapped with `try/except HttpError as e: raise _translate_http_error(e)`. The wrapper produces typed `GoogleApiError(status, reason, message)` with Russian human messages. Never let raw `HttpError` reach API endpoints or schedulers.
- API endpoints (`api/events.py`, `tasks.py`, `search.py`, `addresses.py`) catch `GoogleApiError` and call `_raise_http(e)` to map to `HTTPException` with `{reason, message}` body. `reason="reauth_required"` → 401, `quota`/`rateLimit` → 429, `notFound` → 404.
- `get_google_credentials()` in `services/google_auth.py` catches `RefreshError` and raises `GoogleApiError(401, "reauth_required", ...)`. Never silently store a stale access_token.

### Agent tools (`backend/app/chat/tools.py`)

- Tools that return formatted text for the user MUST also embed event/task IDs the LLM can quote back. Use the `⟦id=…⟧` block convention. The system prompt rule 11 strips these from final user output. **Without IDs in the response, the LLM cannot call subsequent update/delete tools — it has no handle.** This was the rename-event bug.
- **Tools returning multi-day data (e.g. `get_calendar_events` for a week) MUST group results by local date with `📅 <weekday>, <day> <month>` headers.** A flat list of `HH:MM` lines across days is unreadable — the user can't tell which day each event belongs to. Use the `_local_date(ev)` + `_format_date_header(date_str)` helpers in `tools.py`. Single-day ranges skip the header. The system prompt rule 11 explicitly tells the agent to preserve these headers verbatim.
- For recurring events: `delete_calendar_event` and `update_calendar_event` MUST accept a `scope: "instance"|"following"|"all"` parameter and the system prompt MUST instruct the agent to ask the user which scope before calling. Same for the frontend `EventDetailSheet` delete confirmation.
- **Patching a recurring master with `scope="all"` for a time-of-day change MUST preserve the master's original DATE.** Google rejects (400) any patch that shifts `DTSTART` of a recurring series with existing instances/exceptions. Use the `_merge_time_into_master_date(master_dt_obj, new_dt_iso)` helper in `tools.py` — it keeps `master_date` from the master's existing `start.dateTime` and substitutes only the `T<HH:MM:SS><tz>` portion from the agent's payload. Same applies to a future API endpoint that allows full-series time changes.
- Every chat tool wraps Google calls in `try: ... except Exception as e: return f"Ошибка...: {_gcal_err(e)}"`. `_gcal_err` checks for `GoogleApiError` and returns the human message.

### Long-running operations

- Agent invocations in `backend/app/chat/websocket.py` and `backend/app/api/voice.py` MUST be wrapped in `asyncio.wait_for(..., timeout=90)`. On `TimeoutError`, send a user-facing error message — never let the UI hang on a stuck LLM/proxy.
- Voice push notification text must be sanitized: strip newlines, truncate to ~120 chars. Raw exception strings break push body formatting.

### Schedulers (`backend/app/schedulers/`)

- Every job MUST have `coalesce=True, max_instances=1, misfire_grace_time=60` in `setup.py` `_COMMON`. Without these, a slow `reminder_check` (1 min interval) can spawn parallel instances and produce duplicate pushes.
- Per-user loops MUST be wrapped in `try/except Exception as e: logger.warning(...)` so one user's broken token doesn't kill the job for everyone else.
- Jobs that depend on local time-of-day (morning/evening summaries) MUST compute the window using each user's `UserSettings.timezone_offset`. Hardcoded UTC `now.replace(hour=0, ...)` is a bug.
- Push delivery in any scheduler MUST go through `send_push_and_cleanup(db, sub, payload)` (`services/push.py`), which deletes 404/410 subscriptions and wraps the sync `webpush()` in `asyncio.to_thread`. Never call raw `send_push()` from a scheduler.
- Reminders are only marked `sent=True` if at least one push succeeded OR there are zero subscriptions OR 24h have passed (give-up cap). Don't mark sent unconditionally.
- Per-user dispatch with at-most-once-per-day semantics (e.g. `summary_dispatch_job`): use a dedup table like `SentSummary(user_id, kind, date_local)` with `UniqueConstraint`, INSERT first then send, rollback the insert on send failure.

### Frontend auth

- `frontend/src/lib/api.ts` MUST distinguish transient errors (network/5xx on refresh) from hard auth failures. Transient → return original 401 to caller, do not log out. Only `reason: "reauth_required"` from backend → `redirectToLogin('google')` with banner on `/login?reason=google`.
- Never call `redirectToLogin()` on a network error or 429.

### Frontend UI conventions

- The `EventDetailSheet` non-editing branch shows a `Repeat` `InfoRow` with `formatRecurrenceLabel(event)` when `isRecurringEvent(event)` is true. Don't hide recurrence info behind a delete-button click.
- The dashboard renders ONE unified empty-state card («🌿 Сегодня свободный день») when both events and tasks are empty — not two stacked grey "nothing here" cards.
- Calendar timeline events (`TimelineEvent`, `AllDayChip` in `pages/calendar.tsx`) MUST have `onClick` wired to open `EventDetailSheet`. Tap-to-edit on today's events is the most-used flow.
- Mutations triggered by rapid taps (task complete, task delete) need module-level `inFlightMutations: Set<string>` dedup keyed by id+state. See `useCompleteTask`/`useDeleteTask` in `hooks/use-tasks.ts`.

### Process

- **Don't write code → deploy → test → fix → re-deploy in a loop.** Before writing, read the relevant existing files and check if the failure mode is a known one from this list. Most "weird" bugs in this codebase are SW caching, deployment path mismatch, missing onError, or hardcoded UTC.
- Run `python3 -c "import ast; ast.parse(open(f).read())"` on every modified Python file and `npx tsc --noEmit` on every frontend change BEFORE deploying. Both are <2 seconds. They catch syntax errors that would otherwise ship to prod.
- After any backend change touching schedulers, services, or models: tail `journalctl -u second-brain-pwa -n 30 --no-pager` after restart to verify clean startup.
