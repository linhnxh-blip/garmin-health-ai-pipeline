import os
from config.settings import settings

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
