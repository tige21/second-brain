# Second Brain PWA — Design Spec

## Overview

Progressive Web App replacing Telegram bot as primary interface for managing Google Calendar, Google Tasks, reminders, routes, and address book via both classic UI and AI chat. Runs parallel to the existing bot.

**Problem:** Telegram is blocked in the user's country; VPN causes reliability issues with the bot.

**Solution:** Standalone PWA with the same feature set, installable on mobile, with push notifications replacing Telegram messages.

## Tech Stack

### Frontend
- **React 19** + **Vite** (SPA)
- **React Router v7** — client-side routing
- **Zustand** — state management
- **TanStack Query** — server state, caching, optimistic updates
- **shadcn/ui** + **Tailwind CSS** — component library + styling
- **Lucide React** — icons (direct imports, no barrel files)
- **Workbox** — service worker for offline + push notifications
- **Web Audio API** — voice recording in-browser

### Backend
- **FastAPI** + **Uvicorn** — async HTTP + WebSocket server
- **Pydantic v2** — request/response validation
- **SQLAlchemy 2.0 async** — ORM with connection pooling
- **SQLite** (dev) / **PostgreSQL** (prod)
- **LangChain** + **OpenAI** (gpt-4o-mini) — AI agent with tools
- **APScheduler** — 6 background jobs (push instead of Telegram)
- **pywebpush** — Web Push notifications (VAPID)
- **OpenAI Whisper** — speech-to-text

### Monorepo Structure

```
second-brain-web/
├── frontend/
│   └── src/
│       ├── app/              # Router, layouts, providers
│       ├── pages/            # Dashboard, Calendar, Tasks, Chat, Settings
│       ├── components/       # shadcn/ui based components
│       ├── features/         # Feature-specific business logic
│       ├── hooks/            # React hooks
│       ├── services/         # API client, push, audio recorder
│       ├── stores/           # Zustand stores
│       └── theme/            # Forest color palette, Tailwind config
├── backend/
│   └── app/
│       ├── api/              # REST endpoints + WebSocket
│       ├── agent/            # LangChain agent, tools, system prompt
│       ├── services/         # Google Calendar/Tasks, Whisper, OSRM
│       ├── db/               # Models, migrations, repository layer
│       ├── schedulers/       # 6 background jobs
│       └── auth/             # Google OAuth, JWT sessions
└── shared/                   # Types, constants
```

## Color Palette — Forest Theme

From the Spark project's Forest palette:

| Token | Value | Usage |
|-------|-------|-------|
| `background` | `#235347` | Main background |
| `backgroundSecondary` | `#163832` | Input fields, secondary areas |
| `backgroundTertiary` | `#0B2B26` | Cards, elevated surfaces |
| `surface` | `#0B2B26` | Card backgrounds |
| `text` | `#FFFFFF` | Primary text |
| `textSecondary` | `rgba(255,255,255,0.7)` | Secondary text |
| `textMuted` | `rgba(255,255,255,0.4)` | Muted/placeholder text |
| `primary` | `#8EB69B` | Primary actions, active states |
| `primaryHover` | `#DAF1DE` | Hover states |
| `primaryActive` | `#6A9A7B` | Active/pressed states |
| `primaryText` | `#051F20` | Text on primary backgrounds |
| `accent` | `#DAF1DE` | Accent highlights |
| `border` | `rgba(142,182,155,0.2)` | Default borders |
| `success` | `#8EB69B` | Success states |
| `warning` | `#FBBF24` | Warning/upcoming events |
| `error` | `#EF4444` | Errors, overdue tasks |
| `info` | `#60A5FA` | Informational |

## Authentication

**Google Sign-In** — single auth flow for both login and Google API access.

Flow:
1. User taps "Sign in with Google" → Google OAuth consent screen
2. Backend receives auth code → exchanges for access + refresh tokens
3. Backend creates JWT (access: 15min, refresh: 30 days) → returns to frontend
4. Frontend stores JWT in httpOnly cookie (access) + localStorage (refresh)
5. Google tokens stored in DB, used server-side for Calendar/Tasks API
6. JWT refresh via `/api/auth/refresh` endpoint

Scopes requested: `openid`, `email`, `profile`, `calendar`, `tasks`.

## UI Screens

### 1. Dashboard (Home)
- Greeting with user name + date
- 4 quick-action buttons: New Event, New Task, Reminder, Route
- Today's events list with colored time indicators (green=soon, yellow=later, blue=evening)
- Today's tasks with checkboxes, completed tasks struck through
- Links to full Calendar and Tasks views

### 2. AI Chat
- Messenger-style interface: user bubbles (primary #8EB69B), AI bubbles (surface #0B2B26)
- Voice message recording with waveform visualization
- AI responses include structured cards (event details, route info)
- WebSocket streaming for real-time AI responses
- Chat history persisted (last 6 exchanges, same as bot)

### 3. Calendar
- Month grid with event indicator dots (colored per category)
- Day view: timeline list with colored time bars
- Tap event to edit/delete
- Quick-create from calendar view

### 4. Tasks
- Filter chips: All, Today, This Week, No Date
- Grouped by date sections
- Overdue tasks highlighted in red
- Event-linked tasks show calendar icon
- Checkbox to complete, swipe to delete
- FAB button to create new task

### 5. Settings
- Profile card (avatar, name, email from Google)
- Timezone selector
- Address book management
- Notification preferences (toggle per notification type)
- AI model selector
- Google account connection status

### Navigation
- Bottom tab bar with 5 tabs: Home, Calendar, Chat (elevated center), Tasks, Settings
- Lucide SVG icons, active tab highlighted in primary color
- Chat button elevated with circular primary background + shadow

## API Design

### REST Endpoints

```
Auth:
  POST   /api/auth/google         — Exchange Google auth code for JWT
  POST   /api/auth/refresh         — Refresh JWT
  DELETE /api/auth/logout           — Invalidate session

Events:
  GET    /api/events               — List events (query: start, end)
  POST   /api/events               — Create event
  PATCH  /api/events/:id           — Update event
  DELETE /api/events/:id           — Delete event

Tasks:
  GET    /api/tasks                — List tasks (query: status, due_before)
  POST   /api/tasks                — Create task
  PATCH  /api/tasks/:id            — Update task
  DELETE /api/tasks/:id            — Delete task

Addresses:
  GET    /api/addresses            — List addresses
  POST   /api/addresses            — Create address
  PATCH  /api/addresses/:id        — Update / set active
  DELETE /api/addresses/:id        — Delete address

Routes:
  POST   /api/routes/calculate     — Calculate route (driving + transit)

Reminders:
  GET    /api/reminders            — List reminders
  POST   /api/reminders            — Create reminder
  DELETE /api/reminders/:id        — Delete reminder

Settings:
  GET    /api/settings             — Get user settings
  PATCH  /api/settings             — Update settings

Push:
  POST   /api/push/subscribe       — Subscribe to Web Push
  DELETE /api/push/unsubscribe     — Unsubscribe
```

### WebSocket — AI Chat

Endpoint: `WS /api/chat`

Authentication: JWT passed as query param on connection.

**Client → Server:**
```json
{ "type": "text", "content": "Перенеси созвон на 11:00" }
{ "type": "audio", "data": "<base64 encoded audio>" }
```

**Server → Client (streamed):**
```json
{ "type": "chunk", "content": "Готово! Перенёс " }
{ "type": "chunk", "content": "«Созвон с командой» на 11:00." }
{ "type": "done", "actions": [{"tool": "update_calendar_event", "event_id": "abc123", "changes": {"start": "11:00"}}] }
```

The `actions` array in the `done` message tells the frontend which data to refetch (e.g., invalidate events query after calendar change).

## Database Schema

| Table | Key Fields | Notes |
|-------|-----------|-------|
| `users` | id, google_id, email, name, avatar_url, created_at | Google profile data |
| `sessions` | id, user_id, refresh_token, expires_at, device_info | JWT refresh tokens |
| `google_tokens` | user_id, access_token, refresh_token, expires_at, scopes | Server-side Google API access |
| `user_settings` | user_id, timezone_offset, active_address_id, notification_prefs (JSON) | Per-user config |
| `addresses` | id, user_id, name, address, lat, lng, is_active | Saved locations |
| `reminders` | id, user_id, text, remind_at (UTC), sent, created_at | One-time reminders |
| `conversation_memory` | user_id, messages_json | Last 6 exchanges |
| `push_subscriptions` | id, user_id, endpoint, p256dh, auth, device_name | Web Push endpoints |
| `notified_events` | user_id, event_id, notified_at | Prevent duplicate notifications |
| `event_task_links` | id, user_id, event_id, task_id, event_summary, notified | Event↔Task relations |

All tables scoped by `user_id`. No `chat_id` — replaced by Google user ID.

## Background Schedulers

Same 6 jobs as the Telegram bot, but sending Web Push instead of Telegram messages:

| Job | Frequency | Action |
|-----|-----------|--------|
| Morning summary | Daily 07:00 UTC | Push: today's events + tasks |
| Evening summary | Daily 18:00 UTC | Push: tomorrow's events + pending tasks |
| Reminder check | Every 1 min | Push for due reminders |
| Departure check | Every 15 min | Push: "leave in X min" for events with locations |
| Event-task notify | Every 15 min | Push: task reminder 4h before linked event |
| Token check | Daily 09:00 UTC | Push: alert if Google token expired |

Each job iterates over all users with valid push subscriptions, respecting per-user timezone offset and notification preferences.

## PWA Features

### Service Worker (Workbox)
- **Precache:** app shell (HTML, CSS, JS, icons)
- **Runtime cache:** API responses (events, tasks) with stale-while-revalidate strategy
- **Offline:** show cached data when offline, queue mutations for sync
- **Push:** receive and display push notifications, handle click → open relevant screen

### Install Experience
- Custom install banner: "Добавьте Second Brain на главный экран"
- Manifest with Forest theme colors, standalone display mode
- App icon set (192px, 512px)

### Mobile UX
- **Optimistic UI** — mutations applied instantly, synced in background
- **Pull-to-refresh** — refresh current view data
- **Swipe actions** — swipe task/event for quick delete/edit
- **Deep links** — `/calendar/2026-04-03`, `/tasks`, `/chat`
- **Haptic feedback** — on task completion, button presses (if supported)

## Agent — LangChain Tools

Same tools as the Telegram bot, adapted for web context:

| Tool | Description |
|------|-------------|
| `get_calendar_events` | Fetch events by date range |
| `create_calendar_event` | Create event (title, time, location, recurrence) |
| `update_calendar_event` | Modify event details |
| `delete_calendar_event` | Delete event or series |
| `get_tasks` | List active tasks |
| `create_task` | Create task (title, due date, notes) |
| `update_task` | Change task details |
| `complete_task` | Mark task as done |
| `delete_task` | Remove task |
| `set_reminder` | One-time reminder at specific time |
| `save_address` / `switch_address` | Address book management |
| `calculate_route` | Route via OSRM (driving + transit) |
| `batch_delete_events` | Bulk event deletion |
| `deduplicate_recurring_events` | Remove duplicate series |
| `think` | Internal reasoning for complex voice messages |

System prompt: same Russian-language rules as the bot (15 rules), adapted for web context (no Telegram-specific formatting).

## Architecture Patterns (from agent/skill guidelines)

### Frontend
- Direct lucide-react imports (no barrel files) for bundle optimization
- React.lazy() + Suspense for route-based code splitting
- Compound components over boolean prop proliferation
- Promise.all() for parallel data fetching (events + tasks simultaneously)
- TanStack Query for server state with optimistic mutations

### Backend
- Async-first: all endpoints `async def`
- Pydantic v2 models for all request/response schemas
- Repository + Service pattern with FastAPI dependency injection
- WebSocket with heartbeat and JWT auth
- Cursor-based pagination for event/task lists
- CORS restricted to frontend domain
- Rate limiting per user
- Input validation via Pydantic on every endpoint

## Deployment

- **Frontend:** Static build → Vercel / Cloudflare Pages / Nginx on VPS
- **Backend:** Uvicorn → systemd service on VPS (same server as bot, different port)
- **Database:** SQLite file for dev, PostgreSQL for production
- **Push keys:** VAPID key pair generated once, stored in env vars
- **SSL:** Required for PWA (service worker, push notifications)
