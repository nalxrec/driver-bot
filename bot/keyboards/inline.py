from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def moderation_keyboard(driver_telegram_id: int) -> InlineKeyboardMarkup:
    """Кнопки Подтвердить/Отклонить для сотрудника в группе модерации."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"verify_approve:{driver_telegram_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"verify_reject:{driver_telegram_id}"
            ),
        ]
    ])
