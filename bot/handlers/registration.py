from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.fsm_states import RegistrationStates
from bot.keyboards.inline import moderation_keyboard
from bot.keyboards.reply import main_menu_keyboard
from bot.services.ocr import extract_passport_data, extract_license_data, download_photo
from bot.db.database import save_driver, set_driver_status
from bot import config

router = Router()

CHECK_LICENSE_URL = "https://opendata.hsc.gov.ua/check-driver-license/"


def passport_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Всё верно", callback_data="passport_ok"),
            InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="passport_manual"),
        ]
    ])


def check_license_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Проверить права на сайте МВД", url=CHECK_LICENSE_URL)]
    ])


# ─── Шаг 1: /register ────────────────────────────────────────────────────────

@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Регистрацию нужно проходить в личном чате с ботом.")
        return

    await state.set_state(RegistrationStates.waiting_for_passport)
    await message.answer(
        "📋 Регистрация водителя.\n\n"
        "Шаг 1 из 7: Пришли фото паспорта (разворот с фотографией).\n"
        "Фото должно быть чётким, все данные — читаемыми."
    )


# ─── Шаг 2: паспорт → OCR ────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_passport, F.photo)
async def process_passport(message: Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    await message.answer("Обрабатываю паспорт, подожди немного...")

    file = await bot.get_file(photo_id)
    file_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file.file_path}"
    photo_bytes = await download_photo(file_url)
    passport_data = await extract_passport_data(photo_bytes)

    await state.update_data(
        passport_photo_id=photo_id,
        full_name=passport_data["full_name"],
        passport_number=passport_data["passport_number"]
    )

    if passport_data["full_name"] or passport_data["passport_number"]:
        await message.answer(
            f"Из паспорта распознано:\n\n"
            f"👤 ФИО: {passport_data['full_name'] or 'не распознано'}\n"
            f"📄 Номер паспорта: {passport_data['passport_number'] or 'не распознано'}\n\n"
            f"Всё верно?",
            reply_markup=passport_confirm_keyboard()
        )
    else:
        await state.set_state(RegistrationStates.waiting_for_name)
        await message.answer(
            "Не удалось распознать данные автоматически.\n"
            "Введи ФИО вручную:"
        )


@router.message(RegistrationStates.waiting_for_passport)
async def passport_not_photo(message: Message):
    await message.answer("Нужно прислать именно фото паспорта.")


@router.callback_query(F.data == "passport_ok")
async def passport_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(RegistrationStates.waiting_for_selfie)
    await callback.message.answer(
        "Отлично! ✅\n\n"
        "Шаг 2 из 7: Пришли селфи (фото твоего лица).\n"
        "Лицо должно быть хорошо видно, без маски и очков."
    )
    await callback.answer()


@router.callback_query(F.data == "passport_manual")
async def passport_manual(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(RegistrationStates.waiting_for_name)
    await callback.message.answer("Введи своё ФИО полностью:")
    await callback.answer()


@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if len(name) < 5:
        await message.answer("Введи полное ФИО.")
        return
    await state.update_data(full_name=name)
    await state.set_state(RegistrationStates.waiting_for_selfie)
    await message.answer(
        f"ФИО записано: {name}\n\n"
        "Шаг 2 из 7: Пришли селфи (фото твоего лица).\n"
        "Лицо должно быть хорошо видно, без маски и очков."
    )


# ─── Шаг 3: селфи ────────────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_selfie, F.photo)
async def process_selfie(message: Message, state: FSMContext):
    await state.update_data(selfie_photo_id=message.photo[-1].file_id)
    await state.set_state(RegistrationStates.waiting_for_license)
    await message.answer(
        "Селфи получено ✅\n\n"
        "Шаг 3 из 7: Пришли фото водительского удостоверения.\n"
        "Лицевая сторона с фото и данными должна быть чётко видна."
    )


@router.message(RegistrationStates.waiting_for_selfie)
async def selfie_not_photo(message: Message):
    await message.answer("Нужно прислать именно фото (селфи).")


# ─── Шаг 4: права → OCR ──────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_license, F.photo)
async def process_license(message: Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    await message.answer("Обрабатываю права, подожди немного...")

    file = await bot.get_file(photo_id)
    file_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file.file_path}"
    photo_bytes = await download_photo(file_url)
    license_data = await extract_license_data(photo_bytes)

    await state.update_data(
        license_photo_id=photo_id,
        license_series=license_data["series"],
        license_number=license_data["number"],
        license_birth_date=license_data["birth_date"]
    )

    recognized_text = (
        f"🪪 Из прав распознано:\n\n"
        f"Серия: {license_data['series'] or 'не распознана'}\n"
        f"Номер: {license_data['number'] or 'не распознан'}\n"
        f"Дата рождения: {license_data['birth_date'] or 'не распознана'}\n\n"
        f"Диспетчер проверит права на сайте МВД."
    )
    await message.answer(recognized_text)

    await state.set_state(RegistrationStates.waiting_for_truck_doc)
    await message.answer(
        "Шаг 4 из 7: Пришли фото техпаспорта ТЯГАЧА.\n\n"
        "📸 Сфотографируй техпаспорт с обеих сторон:\n"
        "• Лицевая сторона (марка, госномер)\n"
        "• Обратная сторона (VIN номер)\n\n"
        "Пришли оба фото по очереди, затем переходим к следующему шагу."
    )


@router.message(RegistrationStates.waiting_for_license)
async def license_not_photo(message: Message):
    await message.answer("Нужно прислать фото водительского удостоверения.")


# ─── Шаг 5: техпаспорт тягача ────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_truck_doc, F.photo)
async def process_truck_doc(message: Message, state: FSMContext):
    await state.update_data(truck_doc_photo_id=message.photo[-1].file_id)
    await state.set_state(RegistrationStates.waiting_for_truck_vin)
    await message.answer(
        "Техпаспорт тягача получен ✅\n\n"
        "Шаг 5 из 7: Пришли фото VIN номера на ТЯГАЧЕ.\n\n"
        "📍 Где найти VIN на тягаче:\n"
        "• Табличка на стойке водительской двери\n"
        "• Под капотом на раме\n"
        "• На лобовом стекле снизу\n\n"
        "⚠️ Фотографируй VIN непосредственно на машине, не в документах."
    )


@router.message(RegistrationStates.waiting_for_truck_doc)
async def truck_doc_not_photo(message: Message):
    await message.answer("Нужно прислать фото техпаспорта тягача.")


# ─── Шаг 6: VIN тягача ───────────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_truck_vin, F.photo)
async def process_truck_vin(message: Message, state: FSMContext):
    await state.update_data(truck_vin_photo_id=message.photo[-1].file_id)
    await state.set_state(RegistrationStates.waiting_for_trailer_doc)
    await message.answer(
        "Фото VIN тягача получено ✅\n\n"
        "Шаг 6 из 7: Пришли фото техпаспорта ПРИЦЕПА.\n\n"
        "📸 Сфотографируй техпаспорт с обеих сторон:\n"
        "• Лицевая сторона (марка, госномер)\n"
        "• Обратная сторона (VIN номер)\n\n"
        "Пришли оба фото по очереди."
    )


@router.message(RegistrationStates.waiting_for_truck_vin)
async def truck_vin_not_photo(message: Message):
    await message.answer("Нужно прислать фото VIN номера тягача.")


# ─── Шаг 7: техпаспорт прицепа ───────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_trailer_doc, F.photo)
async def process_trailer_doc(message: Message, state: FSMContext):
    await state.update_data(trailer_doc_photo_id=message.photo[-1].file_id)
    await state.set_state(RegistrationStates.waiting_for_trailer_vin)
    await message.answer(
        "Техпаспорт прицепа получен ✅\n\n"
        "Шаг 7 из 7: Пришли фото VIN номера на ПРИЦЕПЕ.\n\n"
        "📍 Где найти VIN на прицепе:\n"
        "• Табличка на раме прицепа\n"
        "• На передней балке\n\n"
        "⚠️ Фотографируй VIN непосредственно на прицепе, не в документах."
    )


@router.message(RegistrationStates.waiting_for_trailer_doc)
async def trailer_doc_not_photo(message: Message):
    await message.answer("Нужно прислать фото техпаспорта прицепа.")


# ─── Шаг 8: VIN прицепа → отправка на модерацию ─────────────────────────────

@router.message(RegistrationStates.waiting_for_trailer_vin, F.photo)
async def process_trailer_vin(message: Message, state: FSMContext, bot: Bot):
    trailer_vin_photo_id = message.photo[-1].file_id
    data = await state.get_data()

    full_name = data.get("full_name", message.from_user.full_name)
    passport_number = data.get("passport_number", "")
    license_series = data.get("license_series", "")
    license_number = data.get("license_number", "")
    license_birth_date = data.get("license_birth_date", "")

    await state.clear()

    save_driver(
        telegram_id=message.from_user.id,
        full_name=full_name,
        username=message.from_user.username
    )

    await message.answer(
        "Все документы получены ✅\n\n"
        "Заявка на верификацию отправлена диспетчеру.\n"
        "Ожидай подтверждения — обычно до 30 минут.",
        reply_markup=main_menu_keyboard()
    )

    if not config.MODERATION_CHAT_ID:
        return

    mod_chat = int(config.MODERATION_CHAT_ID)

    # 1. Паспорт
    if data.get("passport_photo_id"):
        await bot.send_photo(chat_id=mod_chat, photo=data["passport_photo_id"], caption="📄 Паспорт")

    # 2. Селфи
    if data.get("selfie_photo_id"):
        await bot.send_photo(chat_id=mod_chat, photo=data["selfie_photo_id"], caption="🤳 Селфи водителя")

    # 3. Права + кнопка проверки
    if data.get("license_photo_id"):
        license_caption = (
            f"🪪 Водительское удостоверение\n\n"
            f"Серия: {license_series or 'не распознана'}\n"
            f"Номер: {license_number or 'не распознан'}\n"
            f"Дата рождения: {license_birth_date or 'не распознана'}"
        )
        await bot.send_photo(
            chat_id=mod_chat,
            photo=data["license_photo_id"],
            caption=license_caption,
            reply_markup=check_license_keyboard()
        )

    # 4. Техпаспорт тягача
    if data.get("truck_doc_photo_id"):
        await bot.send_photo(chat_id=mod_chat, photo=data["truck_doc_photo_id"], caption="🚛 Техпаспорт тягача")

    # 5. VIN тягача
    if data.get("truck_vin_photo_id"):
        await bot.send_photo(chat_id=mod_chat, photo=data["truck_vin_photo_id"], caption="🔢 VIN тягача (на машине)")

    # 6. Техпаспорт прицепа
    if data.get("trailer_doc_photo_id"):
        await bot.send_photo(chat_id=mod_chat, photo=data["trailer_doc_photo_id"], caption="🚚 Техпаспорт прицепа")

    # 7. VIN прицепа + итоговая карточка + кнопки
    caption = (
        f"🔢 VIN прицепа (на машине)\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 ЗАЯВКА НА ВЕРИФИКАЦИЮ\n\n"
        f"👤 ФИО: {full_name}\n"
        f"📄 Паспорт: {passport_number or 'не распознан'}\n"
        f"🪪 Права: {license_series}{license_number or 'не распознаны'}\n"
        f"🆔 Telegram ID: {message.from_user.id}\n"
        f"📱 Username: @{message.from_user.username or 'нет'}\n\n"
        f"Проверь все документы и нажми кнопку:"
    )

    await bot.send_photo(
        chat_id=mod_chat,
        photo=trailer_vin_photo_id,
        caption=caption,
        reply_markup=moderation_keyboard(message.from_user.id)
    )


@router.message(RegistrationStates.waiting_for_trailer_vin)
async def trailer_vin_not_photo(message: Message):
    await message.answer("Нужно прислать фото VIN номера прицепа.")


# ─── Кнопки модерации ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("verify_approve:"))
async def approve_driver(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])
    set_driver_status(driver_tg_id, "approved")
    await bot.send_message(
        chat_id=driver_tg_id,
        text="✅ Верификация пройдена!\n\nТвои документы подтверждены."
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ ПОДТВЕРЖДЕНО: {callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель уведомлён.")



