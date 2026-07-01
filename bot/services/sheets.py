"""
Сервис для работы с Google Sheets.
Лист с колонками: Водитель | Контейнер | Пломбы | Статус
"""

import gspread
from google.oauth2.service_account import Credentials

from bot import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsService:
    def __init__(self):
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(config.GOOGLE_SHEET_ID).worksheet(
            config.GOOGLE_SHEET_WORKSHEET_NAME
        )

    def get_all_rows(self) -> list[dict]:
        return self.sheet.get_all_records()

    def find_row_by_container(self, container_number: str) -> dict | None:
        """Ищет строку по номеру контейнера (без учёта регистра и пробелов)."""
        rows = self.get_all_rows()
        container_norm = container_number.strip().upper().replace(" ", "")
        for row in rows:
            row_container = str(row.get("Контейнер", "")).strip().upper().replace(" ", "")
            if row_container == container_norm:
                return row
        return None

    def find_row_by_driver(self, driver_name: str) -> dict | None:
        """Ищет строку по имени водителя."""
        rows = self.get_all_rows()
        driver_norm = driver_name.strip().lower()
        for row in rows:
            if str(row.get("Водитель", "")).strip().lower() == driver_norm:
                return row
        return None

    def get_seals_for_container(self, container_number: str) -> list[str]:
        """Возвращает список пломб для контейнера."""
        row = self.find_row_by_container(container_number)
        if not row:
            return []
        seals_raw = str(row.get("Пломбы", ""))
        return [s.strip() for s in seals_raw.split(",") if s.strip()]

    def update_status(self, container_number: str, status: str) -> bool:
        """Обновляет колонку 'Статус' для строки контейнера."""
        rows = self.get_all_rows()
        container_norm = container_number.strip().upper()
        for i, row in enumerate(rows, start=2):
            if str(row.get("Контейнер", "")).strip().upper() == container_norm:
                headers = self.sheet.row_values(1)
                if "Статус" not in headers:
                    return False
                status_col = headers.index("Статус") + 1
                self.sheet.update_cell(i, status_col, status)
                return True
        return False
