"""
Общий обработчик для комментариев при отклонении заявок.
Когда диспетчер нажимает кнопку «Отклонить» — бот просит ввести причину,
потом отправляет её водителю.
"""

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

router = Router()


class ModerationStates(StatesGroup):
    waiting_for_reject_comment = State()


# ─── Регистрация: отклонить ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("verify_reject:"))
async def verify_reject_ask_comment(callback: CallbackQuery, state: FSMContext):
    driver_tg_id = int(callback.data.split(":")[1])

    await state.set_state(ModerationStates.waiting_for_reject_comment)
    await state.update_data(
        reject_type="verify",
        driver_tg_id=driver_tg_id,
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
        original_caption=callback.message.caption or callback.message.text or ""
    )

    await callback.message.answer(
        f"✏️ Укажи причину отклонения заявки водителя (ID: {driver_tg_id}).\n"
        "Напиши комментарий — он будет отправлен водителю:"
    )
    await callback.answer()


# ─── Сверка пломб: отклонить ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("seals_fail:"))
async def seals_fail_ask_comment(callback: CallbackQuery, state: FSMContext):
    driver_tg_id = int(callback.data.split(":")[1])

    await state.set_state(ModerationStates.waiting_for_reject_comment)
    await state.update_data(
        reject_type="seals",
        driver_tg_id=driver_tg_id,
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
        original_text=callback.message.text or ""
    )

    await callback.message.answer(
        f"✏️ Укажи причину — что именно не так с пломбами (ID: {driver_tg_id}).\n"
        "Напиши комментарий — он будет отправлен водителю:"
    )
    await callback.answer()


# ─── Проверка перед портом: отклонить ────────────────────────────────────────

@router.callback_query(F.data.startswith("port_fail:"))
async def port_fail_ask_comment(callback: CallbackQuery, state: FSMContext):
    driver_tg_id = int(callback.data.split(":")[1])

    await state.set_state(ModerationStates.waiting_for_reject_comment)
    await state.update_data(
        reject_type="port",
        driver_tg_id=driver_tg_id,
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
        original_caption=callback.message.caption or callback.message.text or ""
    )

    await callback.message.answer(
        f"✏️ Укажи причину отказа во въезде (ID: {driver_tg_id}).\n"
        "Напиши комментарий — он будет отправлен водителю:"
    )
    await callback.answer()


# ─── Получаем комментарий и отправляем водителю ───────────────────────────────

@router.message(ModerationStates.waiting_for_reject_comment)
async def process_reject_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip() if message.text else ""

    if not comment:
        await message.answer("Напиши текстовый комментарий.")
        return

    data = await state.get_data()
    await state.clear()

    reject_type = data.get("reject_type")
    driver_tg_id = data.get("driver_tg_id")
    original_message_id = data.get("original_message_id")
    original_chat_id = data.get("original_chat_id")

    # Отправляем водителю в зависимости от типа отклонения
    if reject_type == "verify":
        await bot.send_message(
            chat_id=driver_tg_id,
            text=(
                "❌ Верификация не пройдена.\n\n"
                f"💬 Причина: {comment}\n\n"
                "Исправь замечания и попробуй снова: /register"
            )
        )
        # Обновляем сообщение в группе
        try:
            original_caption = data.get("original_caption", "")
            await bot.edit_message_caption(
                chat_id=original_chat_id,
                message_id=original_message_id,
                caption=original_caption + f"\n\n❌ ОТКЛОНЕНО: {message.from_user.full_name}\n💬 {comment}",
                reply_markup=None
            )
        except Exception:
            pass

    elif reject_type == "seals":
        await bot.send_message(
            chat_id=driver_tg_id,
            text=(
                "❌ Диспетчер обнаружил проблему с пломбами.\n\n"
                f"💬 Причина: {comment}\n\n"
                "Свяжитесь с диспетчером для уточнения."
            )
        )
        try:
            original_text = data.get("original_text", "")
            await bot.edit_message_text(
                chat_id=original_chat_id,
                message_id=original_message_id,
                text=original_text + f"\n\n❌ ПРОБЛЕМА: {message.from_user.full_name}\n💬 {comment}",
                reply_markup=None
            )
        except Exception:
            pass

    elif reject_type == "port":
        await bot.send_message(
            chat_id=driver_tg_id,
            text=(
                "❌ ВЪЕЗД НЕ РАЗРЕШЁН\n\n"
                f"💬 Причина: {message.from_user.full_name}: {comment}\n\n"
                "Свяжитесь с диспетчером."
            )
        )
        try:
            original_caption = data.get("original_caption", "")
            await bot.edit_message_caption(
                chat_id=original_chat_id,
                message_id=original_message_id,
                caption=original_caption + f"\n\n❌ ОТКАЗАНО: {message.from_user.full_name}\n💬 {comment}",
                reply_markup=None
            )
        except Exception:
            pass

    await message.answer(
        f"✅ Комментарий отправлен водителю (ID: {driver_tg_id}):\n«{comment}»"
    )
