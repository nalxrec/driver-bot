import os
import json
import tempfile
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SHEET_WORKSHEET_NAME = os.getenv("GOOGLE_SHEET_WORKSHEET_NAME", "Лист1")
MODERATION_CHAT_ID = os.getenv("MODERATION_CHAT_ID")

# Підтримка двох способів передачі Google credentials:
# 1. Файл (локально): GOOGLE_SERVICE_ACCOUNT_FILE=credentials/google_service_account.json
# 2. JSON рядок (Railway/сервер): GOOGLE_SERVICE_ACCOUNT_JSON='{...}'
_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if _json_str:
    # Записуємо JSON у тимчасовий файл
    _tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    _tmp.write(_json_str)
    _tmp.close()
    GOOGLE_SERVICE_ACCOUNT_FILE = _tmp.name
else:
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "credentials/google_service_account.json"
    )

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")
if not GOOGLE_SHEET_ID:
    raise RuntimeError("GOOGLE_SHEET_ID не задан в .env")

TOPIC_VERIFICATION = int(os.getenv("TOPIC_VERIFICATION", "2"))
TOPIC_SEALS = int(os.getenv("TOPIC_SEALS", "4"))
TOPIC_PORT = int(os.getenv("TOPIC_PORT", "6"))
