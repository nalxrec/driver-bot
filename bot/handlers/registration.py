from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.fsm_states import RegistrationStates
from bot.keyboards.inline import moderation_keyboard
from bot.keyboards.reply import main_menu_keyboard
from bot.services.ocr import extract_passport_data, download_photo
from bot.db.database import save_driver, set_driver_status
from bot import config

router = Router()


def passport_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Всё верно", callback_data="passport_ok"),
            InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="passport_manual"),
        ]
    ])


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Регистрацию нужно проходить в личном чате с ботом.")
        return

    await state.set_state(RegistrationStates.waiting_for_passport)
    await message.answer(
        "📋 Регистрация водителя.\n\n"
        "Шаг 1 из 2: Пришли фото паспорта (разворот с фотографией).\n"
        "Фото должно быть чётким, все данные — читаемыми."
    )


@router.message(RegistrationStates.waiting_for_passport, F.photo)
async def process_passport(message: Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id

    await message.answer("Обрабатываю паспорт, подожди немного...")

    # OCR паспорта
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
        await message.answer(
            "Не удалось распознать данные с паспорта автоматически.\n"
            "Введи ФИО вручную:"
        )
        await state.set_state(RegistrationStates.waiting_for_name)


@router.message(RegistrationStates.waiting_for_passport)
async def passport_not_photo(message: Message):
    await message.answer("Нужно прислать именно фото паспорта.")


@router.callback_query(F.data == "passport_ok")
async def passport_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(RegistrationStates.waiting_for_selfie)
    await callback.message.answer(
        "Отлично! ✅\n\n"
        "Шаг 2 из 2: Пришли селфи (фото твоего лица).\n"
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
        "Теперь пришли селфи (фото твоего лица).\n"
        "Лицо должно быть хорошо видно, без маски и очков."
    )


@router.message(RegistrationStates.waiting_for_selfie, F.photo)
async def process_selfie(message: Message, state: FSMContext, bot: Bot):
    selfie_id = message.photo[-1].file_id
    data = await state.get_data()
    full_name = data.get("full_name", message.from_user.full_name)
    passport_number = data.get("passport_number", "")
    passport_id = data.get("passport_photo_id")
    driver_tg_id = message.from_user.id

    await state.clear()

    save_driver(
        telegram_id=driver_tg_id,
        full_name=full_name,
        username=message.from_user.username
    )

    await message.answer(
        "Селфи получено ✅\n\n"
        "Заявка на верификацию отправлена диспетчеру.\n"
        "Ожидай подтверждения.",
        reply_markup=main_menu_keyboard()
    )

    if not config.MODERATION_CHAT_ID:
        return

    mod_chat = int(config.MODERATION_CHAT_ID)
    caption = (
        f"📋 Новая заявка на верификацию\n\n"
        f"👤 ФИО: {full_name}\n"
        f"📄 Номер паспорта: {passport_number or 'не распознан'}\n"
        f"🆔 Telegram ID: {driver_tg_id}\n"
        f"📱 Username: @{message.from_user.username or 'нет'}"
    )

    if passport_id:
        await bot.send_photo(chat_id=mod_chat, photo=passport_id, caption="📄 Паспорт")

    await bot.send_photo(
        chat_id=mod_chat,
        photo=selfie_id,
        caption=caption,
        reply_markup=moderation_keyboard(driver_tg_id)
    )


@router.message(RegistrationStates.waiting_for_selfie)
async def selfie_not_photo(message: Message):
    await message.answer("Нужно прислать именно фото (селфи).")


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


@router.callback_query(F.data.startswith("verify_reject:"))
async def reject_driver(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])
    set_driver_status(driver_tg_id, "rejected")
    await bot.send_message(
        chat_id=driver_tg_id,
        text="❌ Верификация не пройдена.\n\nОбратитесь к диспетчеру.\n\nПопробуй снова: /register"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ ОТКЛОНЕНО: {callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель уведомлён.")
