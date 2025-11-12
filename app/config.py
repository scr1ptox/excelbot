from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    spreadsheet_id: str = os.getenv("SPREADSHEET_ID", "")
    sheet_name: str = os.getenv("SHEET_NAME", "Tasks")
    group_chat_id: int = int(os.getenv("GROUP_CHAT_ID", "0"))
    send_interval_sec: int = int(os.getenv("SEND_INTERVAL_SEC", "180"))

settings = Settings()

# валидация на старте (падает рано, если не заполнено)
for field in ("bot_token", "spreadsheet_id"):
    if not getattr(settings, field):
        raise RuntimeError(f"Missing required env: {field.upper()}")