async def check_reminders(bot) -> None:
    """Send any due reminders to the user."""
    from db.database import get_conn
    from db.models import get_due_reminders, mark_reminder_sent

    conn = get_conn()
    due = get_due_reminders(conn)
    for reminder in due:
        try:
            await bot.send_message(
                chat_id=reminder["chat_id"],
                text=f"🔔 <b>Напоминание:</b> {reminder['text']}",
                parse_mode="HTML",
            )
            mark_reminder_sent(conn, reminder["id"])
        except Exception:
            pass
