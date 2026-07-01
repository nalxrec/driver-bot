"""
Сервис для работы с Google Sheets: чтение/поиск строк вида
водитель | контейнер | пломбы | статус

Ожидаемые заголовки в первой строке таблицы:
    Водитель | Контейнер | Пломбы | Статус
("Пломбы" — пломбы через запятую, например: "12345, 67890")
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
        """Возвращает все строки таблицы как список словарей по заголовкам."""
        return self.sheet.get_all_records()

    def find_row_by_driver(self, driver_name: str) -> dict | None:
        """Ищет первую строку, где имя водителя совпадает (без учёта регистра)."""
        rows = self.get_all_rows()
        driver_name_norm = driver_name.strip().lower()
        for row in rows:
            if str(row.get("Водитель", "")).strip().lower() == driver_name_norm:
                return row
        return None

    def get_seals_for_driver(self, driver_name: str) -> list[str]:
        """Возвращает список номеров пломб, ожидаемых для данного водителя."""
        row = self.find_row_by_driver(driver_name)
        if not row:
            return []
        seals_raw = str(row.get("Пломбы", ""))
        return [s.strip() for s in seals_raw.split(",") if s.strip()]

    def update_status(self, driver_name: str, status: str) -> bool:
        """Обновляет колонку 'Статус' для строки водителя."""
        cell = self.sheet.find(driver_name)
        if not cell:
            return False
        headers = self.sheet.row_values(1)
        if "Статус" not in headers:
            return False
        status_col = headers.index("Статус") + 1
        self.sheet.update_cell(cell.row, status_col, status)
        return True
