"""
OCR сервис через Google Cloud Vision API.
Бесплатно до 1000 запросов в месяц.
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
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def get_vision_token() -> str:
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=VISION_SCOPES
    )
    creds.refresh(Request())
    return creds.token


async def download_photo(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=SSL_CONTEXT) as response:
            return await response.read()


async def extract_text_from_photo(photo_bytes: bytes) -> str:
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
        print(f"[OCR] Полный ответ Vision API: {result}")
        return ""


def parse_seal_numbers(raw_text: str) -> list[str]:
    import re
    candidates = re.findall(r'\b[A-Z0-9]{4,12}\b', raw_text.upper())
    numbers = [c for c in candidates if any(ch.isdigit() for ch in c)]
    return list(dict.fromkeys(numbers))


def parse_container_number(raw_text: str) -> str:
    import re
    match = re.search(r'\b([A-Z]{3,4}[UJZ])\s*(\d{6,7})\b', raw_text.upper())
    if match:
        return match.group(1) + match.group(2)
    return ""


async def extract_seal_numbers(photo_bytes: bytes) -> list[str]:
    raw_text = await extract_text_from_photo(photo_bytes)
    if not raw_text:
        return []
    return parse_seal_numbers(raw_text)


async def extract_container_number(photo_bytes: bytes) -> str:
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

    # Слова которые нужно игнорировать при поиске ФИО
    IGNORE_WORDS = {
        "ПАСПОРТ", "ГРОМАДЯНИНА", "УКРАЇНИ", "UKRAINE", "УКРАЇНА",
        "PASSPORT", "CITIZEN", "REPUBLIC", "SURNAME", "NAME",
        "ПРІЗВИЩЕ", "ІМЯ", "NATIONALITY", "DATE", "EXPIRY",
        "BORN", "SEX", "СТАТЬ", "ГРОМАДЯНСТВО", "ДАТА", "НАРОДЖЕННЯ",
        "ЗАКІНЧЕННЯ", "ДІЇ", "ДОКУМЕНТА", "UKR", "МЧМ", "ЧМ", "МЧ"
    }

    # Ищем номер паспорта
    passport_number = ""
    for line in lines:
        # ID-карта: 9 цифр
        match = re.search(r'\b(\d{9})\b', line)
        if match:
            passport_number = match.group(1)
            break
        # Книжечка: две буквы + 6 цифр
        match = re.search(r'\b([А-ЯҐЄІЇ]{2}\d{6})\b', line.upper())
        if match:
            passport_number = match.group(1)
            break

    # Ищем ФИО по меткам Прізвище/Ім'я
    full_name_parts = []

    for i, line in enumerate(lines):
        line_upper = line.upper()

        if any(label in line_upper for label in ["ПРІЗВИЩЕ", "SURNAME"]):
            candidate = re.sub(r'(ПРІЗВИЩЕ|SURNAME)', '', line, flags=re.IGNORECASE).strip()
            if not candidate and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
            words = [
                w for w in candidate.split()
                if re.match(r'^[А-ЯҐЄІЇ\'-]+$', w.upper())
                and w.upper() not in IGNORE_WORDS
                and len(w) > 1
            ]
            if words:
                full_name_parts.extend(words[:1])

        if any(label in line_upper for label in ["ІМ'Я", "ІМЯ", "GIVEN"]) and "SURNAME" not in line_upper:
            candidate = re.sub(r"(ІМ'Я|ІМЯ|GIVEN NAMES?)", '', line, flags=re.IGNORECASE).strip()
            if not candidate and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
            words = [
                w for w in candidate.split()
                if re.match(r'^[А-ЯҐЄІЇ\'-]+$', w.upper())
                and w.upper() not in IGNORE_WORDS
                and len(w) > 1
            ]
            if words:
                full_name_parts.extend(words[:2])

    # Если метки не нашли — ищем строки с кириллическими словами
    if not full_name_parts:
        for line in lines:
            words = line.split()
            cyrillic_words = [
                w for w in words
                if re.match(r'^[А-ЯҐЄІЇ\'-]+$', w.upper())
                and w.upper() not in IGNORE_WORDS
                and len(w) > 2
            ]
            if cyrillic_words:
                full_name_parts.extend(cyrillic_words)
            if len(full_name_parts) >= 3:
                break

    full_name = " ".join(full_name_parts[:3]) if full_name_parts else ""

    return {
        "full_name": full_name,
        "passport_number": passport_number,
        "raw_text": raw_text
    }


async def extract_license_data(photo_bytes: bytes) -> dict:
    """
    Распознаёт данные с фото водительского удостоверения.
    Возвращает серию, номер и дату рождения.
    """
    import re

    raw_text = await extract_text_from_photo(photo_bytes)
    if not raw_text:
        return {"series": "", "number": "", "birth_date": "", "raw_text": ""}

    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    # Ищем номер ПВ — украинские права: 3 буквы + 6 цифр (ДКМ123456)
    # или просто 6 цифр отдельно
    series = ""
    number = ""

    for line in lines:
        # Формат: ДКМ123456 или AAA123456
        match = re.search(r'\b([А-ЯҐЄІЇA-Z]{2,3})[\s\-]?(\d{6})\b', line.upper())
        if match:
            series = match.group(1)
            number = match.group(2)
            break
        # Просто 6 цифр
        match = re.search(r'\b(\d{6})\b', line)
        if match and not number:
            number = match.group(1)

    # Ищем дату рождения — формат ДД.ММ.РРРР или ДД/ММ/РРРР
    birth_date = ""
    for line in lines:
        match = re.search(r'\b(\d{2}[\.\-\/]\d{2}[\.\-\/]\d{4})\b', line)
        if match:
            birth_date = match.group(1).replace("-", ".").replace("/", ".")
            break

    return {
        "series": series,
        "number": number,
        "birth_date": birth_date,
        "raw_text": raw_text
    }
