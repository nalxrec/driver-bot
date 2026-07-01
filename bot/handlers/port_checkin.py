from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.sheets import SheetsService
from bot.services.ocr import extract_seal_numbers, extract_container_number, download_photo
from bot.db.database import get_driver_name
from bot.keyboards.reply import next_keyboard, main_menu_keyboard
from bot import config

router = Router()
sheets_service = SheetsService()


class PortCheckStates(StatesGroup):
    waiting_for_seals_photo = State()
    waiting_for_container_photo = State()


def port_moderation_keyboard(driver_tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Допустить к въезду",
                callback_data=f"port_ok:{driver_tg_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отказать",
                callback_data=f"port_fail:{driver_tg_id}"
            ),
        ]
    ])


@router.message(Command("portcheck"))
async def cmd_portcheck(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Эту команду нужно использовать в личном чате с ботом.")
        return

    full_name = get_driver_name(message.from_user.id)
    if not full_name:
        await message.answer(
            "Ты не зарегистрирован в системе.\n"
            "Сначала пройди регистрацию — нажми «Зарегистрироваться»."
        )
        return

    await state.set_state(PortCheckStates.waiting_for_seals_photo)
    await state.update_data(seal_photos=[])
    await message.answer(
        "🚢 Финальная проверка перед въездом в порт.\n\n"
        "Шаг 1 из 2: Пришли фото ВСЕХ пломб на контейнере.\n"
        "Когда пришлёшь все фото — нажми кнопку ниже.",
        reply_markup=next_keyboard()
    )


@router.message(PortCheckStates.waiting_for_seals_photo, F.photo)
async def receive_port_seal_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("seal_photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(seal_photos=photos)
    await message.answer(
        f"Фото получено ({len(photos)} шт.). Пришли ещё или нажми кнопку.",
        reply_markup=next_keyboard()
    )


@router.message(
    PortCheckStates.waiting_for_seals_photo,
    F.text == "➡️ Далее — фото у контейнера"
)
async def port_seals_done(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("seal_photos"):
        await message.answer(
            "Ты не прислал ни одного фото пломб. Пришли фото.",
            reply_markup=next_keyboard()
        )
        return

    await state.set_state(PortCheckStates.waiting_for_container_photo)
    await message.answer(
        "Фото пломб получены ✅\n\n"
        "Шаг 2 из 2: Пришли фото на фоне контейнера.\n"
        "На фото должны быть видны:\n"
        "• Номер контейнера (крупные буквы и цифры на стенке)\n"
        "• Ты сам рядом с контейнером",
        reply_markup=main_menu_keyboard()
    )


@router.message(PortCheckStates.waiting_for_container_photo, F.photo)
async def receive_container_photo(message: Message, state: FSMContext, bot: Bot):
    container_photo_id = message.photo[-1].file_id
    data = await state.get_data()
    seal_photos = data.get("seal_photos", [])

    await state.clear()
    await message.answer(
        "Фото получено, ожидай — диспетчер проверяет.",
        reply_markup=main_menu_keyboard()
    )

    full_name = get_driver_name(message.from_user.id)
    driver_tg_id = message.from_user.id

    # OCR пломб
    recognized_seals = []
    for photo_id in seal_photos:
        file = await bot.get_file(photo_id)
        file_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file.file_path}"
        photo_bytes = await download_photo(file_url)
        numbers = await extract_seal_numbers(photo_bytes)
        recognized_seals.extend(numbers)
    recognized_seals = list(dict.fromkeys(recognized_seals))

    # OCR контейнера
    container_file = await bot.get_file(container_photo_id)
    container_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{container_file.file_path}"
    container_bytes = await download_photo(container_url)
    container_number = await extract_container_number(container_bytes)

    # Сверка с таблицей
    expected_seals = sheets_service.get_seals_for_driver(full_name)
    recognized_set = set(s.upper() for s in recognized_seals)
    expected_set = set(s.upper() for s in expected_seals)
    missing = expected_set - recognized_set
    extra = recognized_set - expected_set

    driver_row = sheets_service.find_row_by_driver(full_name)
    expected_container = str(driver_row.get("Контейнер", "")).strip().upper() if driver_row else ""
    container_match = (
        container_number.upper() == expected_container
        if container_number and expected_container else None
    )

    report = (
        f"🚢 Финальная проверка перед портом\n\n"
        f"👤 Водитель: {full_name}\n"
        f"🆔 Telegram ID: {driver_tg_id}\n\n"
        f"📦 Контейнер:\n"
        f"  Распознан: {container_number or 'не удалось распознать'}\n"
        f"  Ожидался:  {expected_container or 'нет данных'}\n"
        f"  {'✅ Совпадает' if container_match else '❌ Не совпадает' if container_match is False else '⚠️ Нет данных'}\n\n"
        f"🔒 Пломбы:\n"
        f"  Распознаны: {', '.join(recognized_seals) if recognized_seals else 'не удалось распознать'}\n"
        f"  Ожидались:  {', '.join(expected_seals) if expected_seals else 'нет данных'}\n"
    )
    if missing:
        report += f"  ❌ Не найдены на фото: {', '.join(missing)}\n"
    if extra:
        report += f"  ➕ Лишние: {', '.join(extra)}\n"
    if not missing and not extra and expected_seals:
        report += f"  ✅ Все пломбы совпадают\n"
    report += "\nДиспетчер, проверь фото и прими решение:"

    if config.MODERATION_CHAT_ID:
        mod_chat = int(config.MODERATION_CHAT_ID)
        for photo_id in seal_photos:
            await bot.send_photo(chat_id=mod_chat, photo=photo_id)
        await bot.send_photo(
            chat_id=mod_chat,
            photo=container_photo_id,
            caption=report,
            reply_markup=port_moderation_keyboard(driver_tg_id)
        )


@router.callback_query(F.data.startswith("port_ok:"))
async def port_approved(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])
    await bot.send_message(
        chat_id=driver_tg_id,
        text="✅ ДОПУЩЕН К ВЪЕЗДУ\n\nДиспетчер подтвердил проверку.\nМожешь въезжать в порт."
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ ДОПУЩЕН: {callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель допущен к въезду.")


@router.callback_query(F.data.startswith("port_fail:"))
async def port_rejected(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])
    await bot.send_message(
        chat_id=driver_tg_id,
        text="❌ ВЪЕЗД НЕ РАЗРЕШЁН\n\nДиспетчер обнаружил несоответствие.\nСвяжитесь с диспетчером."
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n❌ ОТКАЗАНО: {callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водителю отказано во въезде.")
