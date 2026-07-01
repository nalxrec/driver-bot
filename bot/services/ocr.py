"""
OCR сервис через Google Cloud Vision API.
Бесплатно до 1000 запросов в месяц.
Использует тот же google_service_account.json что и для Google Sheets.
"""

import ssl
import certifi
import aiohttp
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import json
import base64

from bot import config

VISION_SCOPES = ["https://www.googleapis.com/auth/cloud-vision"]

# SSL контекст с правильными сертификатами (фикс для Mac)
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def get_vision_token() -> str:
    """Получаем access token через сервисный аккаунт."""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=VISION_SCOPES
    )
    creds.refresh(Request())
    return creds.token


async def download_photo(url: str) -> bytes:
    """Скачивает фото по URL и возвращает байты."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=SSL_CONTEXT) as response:
            return await response.read()


async def extract_text_from_photo(photo_bytes: bytes) -> str:
    """
    Отправляет фото в Google Vision API и возвращает весь распознанный текст.
    """
    token = get_vision_token()
    image_b64 = base64.b64encode(photo_bytes).decode("utf-8")

    payload = {
        "requests": [
            {
                "image": {"content": image_b64},
                "features": [{"type": "TEXT_DETECTION", "maxResults": 1}]
            }
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://vision.googleapis.com/v1/images:annotate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            data=json.dumps(payload),
            ssl=SSL_CONTEXT
        ) as response:
            result = await response.json()

    try:
        text = result["responses"][0]["fullTextAnnotation"]["text"]
        return text.strip()
    except (KeyError, IndexError):
        return ""


def parse_seal_numbers(raw_text: str) -> list[str]:
    """
    Из сырого текста с фото пломб вычленяет номера.
    """
    import re
    candidates = re.findall(r'\b[A-Z0-9]{4,12}\b', raw_text.upper())
    numbers = [c for c in candidates if any(ch.isdigit() for ch in c)]
    return list(dict.fromkeys(numbers))


def parse_container_number(raw_text: str) -> str:
    """
    Из текста с фото контейнера вычленяет номер контейнера.
    Стандартный формат: 4 буквы + 6-7 цифр, например MRKU9448140
    """
    import re
    match = re.search(r'\b([A-Z]{3,4}[UJZ])\s*(\d{6,7})\b', raw_text.upper())
    if match:
        return match.group(1) + match.group(2)
    return ""


async def extract_seal_numbers(photo_bytes: bytes) -> list[str]:
    """Распознаёт номера пломб с фото."""
    raw_text = await extract_text_from_photo(photo_bytes)
    if not raw_text:
        return []
    return parse_seal_numbers(raw_text)


async def extract_container_number(photo_bytes: bytes) -> str:
    """Распознаёт номер контейнера с фото."""
    raw_text = await extract_text_from_photo(photo_bytes)
    if not raw_text:
        return ""
    return parse_container_number(raw_text)


async def extract_passport_data(photo_bytes: bytes) -> dict:
    """
    Распознаёт данные с фото паспорта (украинский ID или книжечка).
    Возвращает словарь с ФИО и номером паспорта.
    """
    import re
    raw_text = await extract_text_from_photo(photo_bytes)
    if not raw_text:
        return {"full_name": "", "passport_number": "", "raw_text": ""}

    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    # Ищем номер паспорта:
    # ID-карта: 9 цифр (123456789)
    # Книжечка: серия АВ + 6 цифр (АВ123456) или латиница AB123456
    passport_number = ""
    for line in lines:
        # Книжечка: две буквы + 6 цифр
        match = re.search(r'\b([А-ЯA-Z]{2}\d{6})\b', line.upper())
        if match:
            passport_number = match.group(1)
            break
        # ID-карта: 9 цифр
        match = re.search(r'\b(\d{9})\b', line)
        if match:
            passport_number = match.group(1)
            break

    # Ищем ФИО — строки из кириллических слов длиннее 3 символов
    full_name = ""
    for line in lines:
        words = line.split()
        cyrillic_words = [w for w in words if re.match(r'^[А-ЯҐЄІЇа-яґєії\'-]+$', w) and len(w) > 2]
        if len(cyrillic_words) >= 2:
            full_name = " ".join(cyrillic_words[:3])
            break

    return {
        "full_name": full_name,
        "passport_number": passport_number,
        "raw_text": raw_text
    }
