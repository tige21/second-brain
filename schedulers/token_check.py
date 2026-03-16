import logging

logger = logging.getLogger(__name__)


async def check_google_tokens(bot) -> None:
    """
    Check Google OAuth token validity for all connected users.
    Sends a Telegram notification if the token has expired or been revoked.
    Runs daily so users are notified promptly instead of discovering it mid-use.
    """
    from db.database import get_conn
    from db.models import list_connected_users
    from services.google_auth import get_credentials, GoogleAuthExpiredError

    conn = get_conn()
    user_ids = list_connected_users(conn)

    for chat_id in user_ids:
        try:
            get_credentials(chat_id)
        except GoogleAuthExpiredError:
            logger.warning(f"Token expired for chat_id={chat_id}, sending notification")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ <b>Авторизация Google истекла.</b>\n\n"
                        "Отправь /connect чтобы снова подключить Google Calendar и Tasks."
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Failed to notify chat_id={chat_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error checking token for chat_id={chat_id}: {e}")
