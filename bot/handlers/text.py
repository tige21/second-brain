from datetime import datetime, timezone, timedelta, date as date_type
from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM_CHAT_ID
from agent.executor import run_agent
from db.database import get_conn
from db.models import (
    clear_memory, get_setting, set_setting, pop_undo_session,
    approve_user, list_pending_users,
)
from bot.formatters import md_to_html, chunk_message
from services import google_calendar as gcal
from services import google_tasks as gtasks
from services.google_auth import get_auth_url


_MONTHS_RU = ['','января','февраля','марта','апреля','мая','июня',
              'июля','августа','сентября','октября','ноября','декабря']
_DAYS_RU = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']


def _schedule_lines(
    events: list,
    tasks: list,
    tz_offset: int,
    start_date: date_type,
    end_date: date_type,
    show_overdue: bool = True,
) -> list[str]:
    """Build combined events+tasks lines grouped by day (variant B: tasks indented under events)."""
    # Group events by local date
    events_by_date: dict[date_type, list[tuple]] = {}
    for e in events:
        dt_str = e.get('start', {}).get('dateTime') or e.get('start', {}).get('date', '')
        if 'T' in dt_str:
            dt_utc = datetime.fromisoformat(dt_str.replace('Z', '+00:00')).astimezone(timezone.utc)
            dt_local = dt_utc + timedelta(hours=tz_offset)
            day = dt_local.date()
            time_str = dt_local.strftime('%H:%M')
        elif dt_str:
            day = date_type.fromisoformat(dt_str)
            time_str = "весь день"
        else:
            continue
        if start_date <= day <= end_date:
            events_by_date.setdefault(day, []).append((time_str, e))

    # Group tasks by due date
    tasks_by_date: dict[date_type, list] = {}
    tasks_overdue: list = []
    tasks_no_date: list = []
    for t in tasks:
        due = t.get('due', '')
        if not due:
            tasks_no_date.append(t)
        else:
            due_date = date_type.fromisoformat(due[:10])
            if due_date < start_date:
                tasks_overdue.append(t)
            elif due_date <= end_date:
                tasks_by_date.setdefault(due_date, []).append(t)

    lines: list[str] = []

    # Overdue block at top
    if show_overdue and tasks_overdue:
        lines.append("⚠️ <b>Просрочено:</b>")
        for t in tasks_overdue:
            lines.append(f"  📋 {t.get('title', '')}")
        lines.append("")

    # Day sections
    current = start_date
    while current <= end_date:
        day_events = events_by_date.get(current, [])
        day_tasks = tasks_by_date.get(current, [])
        if not day_events and not day_tasks:
            current += timedelta(days=1)
            continue

        day_label = f"{_DAYS_RU[current.weekday()]}, {current.day} {_MONTHS_RU[current.month]}"
        lines.append(f"<b>{day_label}</b>")

        for time_str, e in day_events:
            summary = e.get('summary', 'Без названия')
            loc = f" 📍{e['location']}" if e.get('location') else ""
            lines.append(f"⏰ <b>{time_str}</b>  {summary}{loc}")

        if day_tasks:
            if day_events:
                lines.append("")
            for t in day_tasks:
                lines.append(f"  📋 {t.get('title', '')}")

        lines.append("")
        current += timedelta(days=1)

    # No-date block at bottom
    if tasks_no_date:
        lines.append("📋 <b>Без срока:</b>")
        for t in tasks_no_date:
            lines.append(f"  📋 {t.get('title', '')}")

    return lines


def _is_auth_code(text: str) -> bool:
    """Detect Google OAuth authorization code (starts with '4/', no spaces, long)."""
    text = text.strip()
    return text.startswith('4/') and len(text) > 20 and ' ' not in text


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages and bot commands."""
    message = update.message or update.edited_message
    chat_id = message.chat_id
    text = message.text or ""

    # /start or /help
    if text.startswith('/start') or text.startswith('/help'):
        is_admin = (chat_id == TELEGRAM_CHAT_ID)
        help_text = (
            "🤖 <b>Second Brain Bot</b>\n\n"
            "Я управляю твоим Google Calendar и Google Tasks.\n\n"
            "<b>Что я умею:</b>\n"
            "• 📅 Создавать, изменять, удалять события\n"
            "• ✅ Управлять задачами (создавать, выполнять, удалять)\n"
            "• 🎙️ Распознавать голосовые сообщения\n"
            "• 📍 Сохранять адреса и рассчитывать маршруты\n"
            "• 🌅 Утренняя сводка в 10:00 MSK\n"
            "• 🌆 Вечерняя сводка в 21:00 MSK\n"
            "• 🚀 Напоминание о выезде (каждые 15 мин)\n\n"
            "<b>Команды:</b>\n"
            "/connect — подключить Google Calendar\n"
            "/help — эта справка\n"
            "/week — события на 7 дней\n"
            "/tomorrow — события завтра\n"
            "/tasks — все активные задачи\n"
            "/go — когда выходить на ближайшее событие\n"
            "/undo — отменить последнее созданное\n"
            "/tz +3 — установить часовой пояс\n"
            "/reset — сбросить историю диалога"
        )
        if is_admin:
            help_text += "\n/approve — управление пользователями (только для админа)"
        await message.reply_text(help_text, parse_mode="HTML")
        return

    # /connect — OAuth flow
    if text.startswith('/connect'):
        try:
            auth_url = get_auth_url(chat_id)
            await message.reply_text(
                "🔗 <b>Подключение Google Calendar</b>\n\n"
                f"Открой ссылку и войди в аккаунт Google — после авторизации бот получит доступ автоматически:\n\n"
                f"{auth_url}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            await message.reply_text(f"⚠️ Ошибка при генерации ссылки: {e}")
        return

    # /approve — user management (admin only)
    if text.startswith('/approve'):
        if chat_id != TELEGRAM_CHAT_ID:
            return
        conn = get_conn()
        parts = text.split()
        if len(parts) < 2:
            pending = list_pending_users(conn)
            if not pending:
                await message.reply_text("✅ Нет ожидающих пользователей.")
            else:
                lines = ["👥 <b>Ожидают одобрения:</b>"]
                for u in pending:
                    uname = f"@{u['username']}" if u.get('username') else "без username"
                    lines.append(f"• <code>{u['chat_id']}</code> ({uname})")
                lines.append("\n/approve &lt;chat_id&gt; — одобрить")
                await message.reply_text("\n".join(lines), parse_mode="HTML")
            return
        try:
            target_id = int(parts[1])
            approve_user(conn, target_id)
            await message.reply_text(f"✅ Пользователь {target_id} одобрен.")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="✅ Доступ одобрен! Используй /connect для подключения Google Calendar."
                )
            except Exception:
                pass
        except ValueError:
            await message.reply_text("⚠️ Укажи числовой chat_id: /approve 123456789")
        return

    if text.startswith('/reset'):
        conn = get_conn()
        clear_memory(conn, chat_id)
        await message.reply_text("✅ История диалога сброшена.")
        return

    if text.startswith('/tz'):
        parts = text.split()
        if len(parts) < 2:
            conn = get_conn()
            current = get_setting(conn, chat_id, 'timezone_offset') or '3'
            await message.reply_text(f"Текущий часовой пояс: UTC+{current}\nИспользуй /tz +5 или /tz 5")
            return
        try:
            offset = int(parts[1].lstrip('+'))
            conn = get_conn()
            set_setting(conn, chat_id, 'timezone_offset', str(offset))
            await message.reply_text(f"✅ Часовой пояс установлен: UTC+{offset}")
        except ValueError:
            await message.reply_text("⚠️ Укажи число, например /tz +3")
        return

    if text.startswith('/week'):
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        try:
            conn = get_conn()
            tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)
            now_utc = datetime.now(timezone.utc)
            local_now = now_utc + timedelta(hours=tz_offset)
            today = local_now.date()
            week_end_date = today + timedelta(days=6)
            week_end_utc = now_utc + timedelta(days=7)

            events = gcal.list_events(chat_id, now_utc.isoformat(), week_end_utc.isoformat(), single_events=True)
            tasks = gtasks.list_tasks(chat_id)

            body = _schedule_lines(events, tasks, tz_offset, today, week_end_date, show_overdue=True)
            if not body:
                await message.reply_text("📅 На ближайшие 7 дней ничего нет.")
                return

            if today.month == week_end_date.month:
                range_str = f"{today.day} — {week_end_date.day} {_MONTHS_RU[week_end_date.month]}"
            else:
                range_str = f"{today.day} {_MONTHS_RU[today.month]} — {week_end_date.day} {_MONTHS_RU[week_end_date.month]}"
            header = f"📅 <b>{range_str}:</b>\n"
            await message.reply_text(header + "\n".join(body), parse_mode="HTML")
        except Exception as ex:
            await message.reply_text(f"⚠️ Ошибка при загрузке: {ex}")
        return

    if text.startswith('/undo'):
        conn = get_conn()
        actions = pop_undo_session(conn, chat_id)
        if not actions:
            await message.reply_text("Нет действий для отмены.")
            return
        done, errors = [], []
        for action in actions:
            try:
                if action['action_type'] == 'create_event':
                    gcal.delete_event(chat_id, action['item_id'])
                    done.append(f"🗓 «{action['summary']}»")
                elif action['action_type'] == 'create_task':
                    gtasks.delete_task(chat_id, action['item_id'])
                    done.append(f"✅ «{action['summary']}»")
                elif action['action_type'] == 'complete_task':
                    gtasks.update_task(chat_id, action['item_id'], status='needsAction')
                    done.append(f"↩️ «{action['summary']}» возвращена в активные")
                elif action['action_type'] == 'delete_occurrence':
                    gcal.restore_occurrence(chat_id, action['item_id'])
                    done.append(f"🗓 «{action['summary']}» восстановлено")
            except Exception as ex:
                errors.append(f"«{action['summary']}»: {ex}")
        lines = ["↩️ <b>Отменено:</b>"] + done
        if errors:
            lines.append("\n⚠️ Не удалось отменить:")
            lines.extend(errors)
        await message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if text.startswith('/tasks'):
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        try:
            tasks = gtasks.list_tasks(chat_id)
            if not tasks:
                await message.reply_text("✅ Активных задач нет.")
                return
            conn = get_conn()
            tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)
            now_local = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
            today_str = now_local.strftime('%Y-%m-%d')
            lines = ["✅ <b>Задачи:</b>\n"]
            overdue, today_tasks, upcoming, no_date = [], [], [], []
            for t in tasks:
                due = t.get('due', '')
                title = t.get('title', '')
                if not due:
                    no_date.append(f"  • {title}")
                elif due[:10] < today_str:
                    overdue.append(f"  • ⚠️ {title} (до {due[:10]})")
                elif due[:10] == today_str:
                    today_tasks.append(f"  • {title}")
                else:
                    upcoming.append(f"  • {title} ({due[:10]})")
            if overdue:
                lines.append("<b>Просрочено:</b>")
                lines.extend(overdue)
                lines.append("")
            if today_tasks:
                lines.append("<b>На сегодня:</b>")
                lines.extend(today_tasks)
                lines.append("")
            if upcoming:
                lines.append("<b>Предстоящие:</b>")
                lines.extend(upcoming)
                lines.append("")
            if no_date:
                lines.append("<b>Без срока:</b>")
                lines.extend(no_date)
            await message.reply_text("\n".join(lines), parse_mode="HTML")
        except Exception as ex:
            await message.reply_text(f"⚠️ Ошибка: {ex}")
        return

    if text.startswith('/go'):
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        try:
            from services.yandex_geocoder import geocode_address, get_travel_time_minutes
            from db.models import get_address
            from config import DEFAULT_TRAVEL_MINUTES

            conn = get_conn()
            tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)
            now = datetime.now(timezone.utc)
            window_end = now + timedelta(hours=24)
            events = gcal.list_events(chat_id, now.isoformat(), window_end.isoformat())
            events_with_loc = [e for e in events if e.get('location') and e.get('start', {}).get('dateTime')]

            if not events_with_loc:
                await message.reply_text("📅 Ближайших событий с адресом нет.")
                return

            active_name = get_setting(conn, chat_id, 'active_address') or ''
            active_addr = get_address(conn, chat_id, active_name) if active_name else None
            origin_coords = active_addr['coords'] if active_addr else None

            lines = ["🗺 <b>Когда выходить:</b>\n"]
            for event in events_with_loc[:3]:
                start_str = event['start']['dateTime']
                event_start = datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(timezone.utc)
                local_start = event_start + timedelta(hours=tz_offset)
                destination = event.get('location', '')
                summary = event.get('summary', 'Событие')

                driving_minutes = DEFAULT_TRAVEL_MINUTES
                transit_minutes = int(DEFAULT_TRAVEL_MINUTES * 1.5)
                is_estimate = True

                if origin_coords:
                    try:
                        dest_geo = await geocode_address(destination)
                        if dest_geo:
                            dest_coords = f"{dest_geo['lat']},{dest_geo['lon']}"
                            driving_minutes = await get_travel_time_minutes(origin_coords, dest_coords, mode="driving")
                            transit_minutes = int(driving_minutes * 1.5)
                            is_estimate = False
                    except Exception:
                        pass

                worst_case = max(driving_minutes, transit_minutes)
                depart_at = event_start - timedelta(minutes=worst_case + 20)
                local_depart = depart_at + timedelta(hours=tz_offset)
                transit_label = " (оценка)" if is_estimate else ""

                lines.append(
                    f"📍 <b>{summary}</b>\n"
                    f"🕐 Начало в {local_start.strftime('%H:%M')}\n"
                    f"⏰ Выйти в <b>{local_depart.strftime('%H:%M')}</b>\n"
                    f"🚗 Такси: ~{driving_minutes} мин\n"
                    f"🚌 Транспорт: ~{transit_minutes} мин{transit_label}\n"
                    f"📌 {destination}"
                )

            await message.reply_text("\n\n".join(lines), parse_mode="HTML")
        except Exception as ex:
            await message.reply_text(f"⚠️ Ошибка: {ex}")
        return

    if text.startswith('/tomorrow'):
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        try:
            conn = get_conn()
            tz_offset = int(get_setting(conn, chat_id, 'timezone_offset') or 3)
            now_utc = datetime.now(timezone.utc)
            local_now = now_utc + timedelta(hours=tz_offset)
            local_tomorrow = (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            tmrw_date = local_tomorrow.date()
            tmrw_start = local_tomorrow - timedelta(hours=tz_offset)
            tmrw_end = tmrw_start + timedelta(days=1)

            events = gcal.list_events(chat_id, tmrw_start.isoformat(), tmrw_end.isoformat(), single_events=True)
            tasks = gtasks.list_tasks(chat_id)

            date_str = f"{local_tomorrow.day} {_MONTHS_RU[local_tomorrow.month]}"
            body = _schedule_lines(events, tasks, tz_offset, tmrw_date, tmrw_date, show_overdue=False)
            if not body:
                await message.reply_text(f"📅 Завтра ({date_str}) ничего нет.")
                return

            header = f"📅 <b>Завтра, {date_str}:</b>\n"
            await message.reply_text(header + "\n".join(body), parse_mode="HTML")
        except Exception as ex:
            await message.reply_text(f"⚠️ Ошибка: {ex}")
        return


    # Forwarded messages
    user_input = text
    if message.forward_origin:
        user_input = f'📨 Пересланное сообщение: "{text}"\nИзвлеки задачу или событие.'

    # Reply to another message
    elif message.reply_to_message and message.reply_to_message.text:
        original = message.reply_to_message.text
        user_input = f'📨 Сообщение: "{original}"\n💬 Комментарий: {text}'

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = await run_agent(chat_id, user_input)
    html_response = md_to_html(response)

    for chunk in chunk_message(html_response):
        await message.reply_text(chunk, parse_mode="HTML")
