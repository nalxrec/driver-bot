import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/google_service_account.json"
)
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SHEET_WORKSHEET_NAME = os.getenv("GOOGLE_SHEET_WORKSHEET_NAME", "Лист1")

MODERATION_CHAT_ID = os.getenv("MODERATION_CHAT_ID")  # ID группы сотрудников

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")
if not GOOGLE_SHEET_ID:
    raise RuntimeError("GOOGLE_SHEET_ID не задан в .env")
