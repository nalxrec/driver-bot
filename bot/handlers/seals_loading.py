from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup

from bot.services.sheets import SheetsService
from bot.services.ocr import extract_seal_numbers, download_photo
from bot.db.database import get_driver_name
from bot.keyboards.reply import done_keyboard, main_menu_keyboard
from bot import config

router = Router()
sheets_service = SheetsService()


class SealsStates(StatesGroup):
    waiting_for_seals_photo = State()


def seals_moderation_keyboard(driver_tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтверждаю",
                callback_data=f"seals_ok:{driver_tg_id}"
            ),
            InlineKeyboardButton(
                text="❌ Есть проблема",
                callback_data=f"seals_fail:{driver_tg_id}"
            ),
        ]
    ])


@router.message(Command("checkseals"))
async def cmd_checkseals(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Эту команду нужно использовать в личном чате с ботом.")
        return

    await state.set_state(SealsStates.waiting_for_seals_photo)
    await state.update_data(seal_photos=[])
    await message.answer(
        "📸 Пришли фото пломб на контейнере.\n\n"
        "Убедись, что все номера пломб хорошо видны.\n"
        "Можно прислать несколько фото.\n\n"
        "Когда пришлёшь все фото — нажми кнопку ниже.",
        reply_markup=done_keyboard()
    )


@router.message(SealsStates.waiting_for_seals_photo, F.photo)
async def receive_seal_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("seal_photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(seal_photos=photos)
    await message.answer(
        f"Фото получено ({len(photos)} шт.). Пришли ещё или нажми «Готово».",
        reply_markup=done_keyboard()
    )


@router.message(
    SealsStates.waiting_for_seals_photo,
    F.text == "✅ Готово, все фото отправил"
)
async def process_seals_done(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    photos = data.get("seal_photos", [])

    if not photos:
        await message.answer(
            "Ты не прислал ни одного фото. Пришли фото пломб.",
            reply_markup=done_keyboard()
        )
        return

    await state.clear()
    await message.answer(
        "Фото получено, ожидай — диспетчер проверяет пломбы.",
        reply_markup=main_menu_keyboard()
    )

    # OCR
    recognized_seals = []
    for photo_id in photos:
        file = await bot.get_file(photo_id)
        file_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file.file_path}"
        photo_bytes = await download_photo(file_url)
        numbers = await extract_seal_numbers(photo_bytes)
        recognized_seals.extend(numbers)
    recognized_seals = list(dict.fromkeys(recognized_seals))

    full_name = get_driver_name(message.from_user.id)
    if not full_name:
        if config.MODERATION_CHAT_ID:
            mod_chat = int(config.MODERATION_CHAT_ID)
            for photo_id in photos:
                await bot.send_photo(chat_id=mod_chat, photo=photo_id)
            await bot.send_message(
                chat_id=mod_chat,
                text=(
                    f"⚠️ Фото пломб от незарегистрированного пользователя\n"
                    f"Telegram ID: {message.from_user.id}\n"
                    f"Username: @{message.from_user.username or 'нет'}"
                )
            )
        return

    expected_seals = sheets_service.get_seals_for_driver(full_name)
    recognized_set = set(s.upper() for s in recognized_seals)
    expected_set = set(s.upper() for s in expected_seals)
    missing = expected_set - recognized_set
    extra = recognized_set - expected_set

    if expected_seals:
        if not missing and not extra:
            match_status = "✅ Все пломбы совпадают с таблицей"
        else:
            match_status = "⚠️ Есть расхождения с таблицей"
    else:
        match_status = "⚠️ Водитель не найден в таблице — проверьте вручную"

    report = (
        f"📋 Сверка пломб после погрузки\n\n"
        f"👤 Водитель: {full_name}\n"
        f"🆔 Telegram ID: {message.from_user.id}\n\n"
        f"🔍 Распознано на фото: {', '.join(recognized_seals) if recognized_seals else 'не удалось распознать'}\n"
        f"📊 Ожидалось по таблице: {', '.join(expected_seals) if expected_seals else 'нет данных'}\n\n"
    )
    if missing:
        report += f"❌ Не найдено на фото: {', '.join(missing)}\n"
    if extra:
        report += f"➕ Лишние (нет в таблице): {', '.join(extra)}\n"
    report += f"\n{match_status}"

    if config.MODERATION_CHAT_ID:
        mod_chat = int(config.MODERATION_CHAT_ID)
        for photo_id in photos:
            await bot.send_photo(chat_id=mod_chat, photo=photo_id)
        await bot.send_message(
            chat_id=mod_chat,
            text=report,
            reply_markup=seals_moderation_keyboard(message.from_user.id)
        )


@router.callback_query(F.data.startswith("seals_ok:"))
async def seals_approved(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])
    await bot.send_message(
        chat_id=driver_tg_id,
        text="✅ Пломбы проверены и подтверждены диспетчером.\nМожешь продолжать."
    )
    await callback.message.edit_text(
        text=callback.message.text + f"\n\n✅ ПОДТВЕРЖДЕНО: {callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель уведомлён.")


@router.callback_query(F.data.startswith("seals_fail:"))
async def seals_rejected(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])
    await bot.send_message(
        chat_id=driver_tg_id,
        text=(
            "❌ Диспетчер обнаружил проблему с пломбами.\n\n"
            "Пожалуйста, свяжитесь с диспетчером для уточнения."
        )
    )
    await callback.message.edit_text(
        text=callback.message.text + f"\n\n❌ ПРОБЛЕМА: {callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель уведомлён.")
