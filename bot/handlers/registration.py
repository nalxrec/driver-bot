from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.states.fsm_states import RegistrationStates
from bot.keyboards.inline import moderation_keyboard
from bot.db.database import save_driver, set_driver_status
from bot import config

router = Router()


# ─── Шаг 1: /register — начало сценария ────────────────────────────────────

@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    # Проверяем, что команда пришла из личного чата, а не из группы
    if message.chat.type != "private":
        await message.answer("Регистрацию нужно проходить в личном чате с ботом.")
        return

    await state.set_state(RegistrationStates.waiting_for_name)
    await message.answer(
        "Начинаем регистрацию.\n\n"
        "Шаг 1 из 3: Введи своё ФИО точно так, как написано в паспорте.\n"
        "Например: Иванов Иван Иванович"
    )


# ─── Шаг 2: получаем ФИО ───────────────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""

    if len(name) < 5:
        await message.answer("Похоже, это слишком короткое имя. Введи полное ФИО.")
        return

    await state.update_data(full_name=name)
    await state.set_state(RegistrationStates.waiting_for_passport)
    await message.answer(
        f"Отлично, записал: {name}\n\n"
        "Шаг 2 из 3: Пришли фото паспорта (разворот с фотографией).\n"
        "Фото должно быть чётким, все данные — читаемыми."
    )


# ─── Шаг 3: получаем фото паспорта ─────────────────────────────────────────

@router.message(RegistrationStates.waiting_for_passport)
async def process_passport(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Нужно прислать именно фото (не файл, не текст). Попробуй ещё раз.")
        return

    # Берём фото с наилучшим разрешением (последнее в списке)
    photo_id = message.photo[-1].file_id
    await state.update_data(passport_photo_id=photo_id)
    await state.set_state(RegistrationStates.waiting_for_selfie)
    await message.answer(
        "Паспорт получен ✅\n\n"
        "Шаг 3 из 3: Пришли селфи (фото твоего лица на камеру телефона).\n"
        "Лицо должно быть хорошо видно, без маски и очков."
    )


# ─── Шаг 4: получаем селфи, отправляем на модерацию ────────────────────────

@router.message(RegistrationStates.waiting_for_selfie)
async def process_selfie(message: Message, state: FSMContext, bot: Bot):
    if not message.photo:
        await message.answer("Нужно прислать именно фото. Попробуй ещё раз.")
        return

    selfie_id = message.photo[-1].file_id
    data = await state.get_data()
    full_name = data["full_name"]
    passport_id = data["passport_photo_id"]
    driver_tg_id = message.from_user.id
    driver_tg_username = f"@{message.from_user.username}" if message.from_user.username else "нет username"

    await state.clear()

    # Сохраняем водителя в базу данных
    save_driver(
        telegram_id=driver_tg_id,
        full_name=full_name,
        username=message.from_user.username
    )

    # Сообщаем водителю, что заявка принята
    await message.answer(
        "Селфи получено ✅\n\n"
        "Заявка на верификацию отправлена сотруднику.\n"
        "Ожидай подтверждения — обычно это занимает до 30 минут.\n"
        "Как только сотрудник проверит документы, ты получишь уведомление."
    )

    # Отправляем документы в группу модерации
    if not config.MODERATION_CHAT_ID:
        return

    mod_chat = int(config.MODERATION_CHAT_ID)
    caption = (
        f"📋 Новая заявка на верификацию водителя\n\n"
        f"👤 ФИО: {full_name}\n"
        f"🆔 Telegram ID: {driver_tg_id}\n"
        f"📱 Username: {driver_tg_username}\n\n"
        f"Проверь, что лицо на паспорте совпадает с селфи, "
        f"и нажми кнопку ниже."
    )

    # Паспорт
    await bot.send_photo(
        chat_id=mod_chat,
        photo=passport_id,
        caption="📄 Паспорт"
    )

    # Селфи + кнопки модерации
    await bot.send_photo(
        chat_id=mod_chat,
        photo=selfie_id,
        caption=caption,
        reply_markup=moderation_keyboard(driver_tg_id)
    )


# ─── Обработка кнопок модерации ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("verify_approve:"))
async def approve_driver(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])

    set_driver_status(driver_tg_id, "approved")

    # Уведомляем водителя
    await bot.send_message(
        chat_id=driver_tg_id,
        text=(
            "✅ Верификация пройдена!\n\n"
            "Твои документы подтверждены. "
            "Теперь ты можешь пользоваться всеми функциями бота:\n"
            "/myseals — посмотреть пломбы"
        )
    )

    # Обновляем сообщение в группе модерации
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ ПОДТВЕРЖДЕНО сотрудником: "
                                          f"{callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель уведомлён об одобрении.")


@router.callback_query(F.data.startswith("verify_reject:"))
async def reject_driver(callback: CallbackQuery, bot: Bot):
    driver_tg_id = int(callback.data.split(":")[1])

    set_driver_status(driver_tg_id, "rejected")

    # Уведомляем водителя
    await bot.send_message(
        chat_id=driver_tg_id,
        text=(
            "❌ Верификация не пройдена.\n\n"
            "Сотрудник отклонил заявку. Возможные причины:\n"
            "• Фото паспорта нечёткое или нечитаемое\n"
            "• Лицо на селфи не совпадает с паспортом\n"
            "• Данные не найдены в базе\n\n"
            "Попробуй снова: /register"
        )
    )

    # Обновляем сообщение в группе модерации
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ ОТКЛОНЕНО сотрудником: "
                                          f"{callback.from_user.full_name}",
        reply_markup=None
    )
    await callback.answer("Водитель уведомлён об отклонении.")
