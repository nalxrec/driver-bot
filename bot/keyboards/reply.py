from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню водителя."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Зарегистрироваться")],
            [KeyboardButton(text="🔒 Сверка пломб")],
            [KeyboardButton(text="🚢 Проверка перед портом")],
        ],
        resize_keyboard=True,
        persistent=True
    )


def done_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка 'Готово' при отправке фото пломб."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Готово, все фото отправил")],
        ],
        resize_keyboard=True
    )


def next_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка 'Далее' после фото пломб перед портом."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➡️ Далее — фото у контейнера")],
        ],
        resize_keyboard=True
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Убирает клавиатуру."""
    return ReplyKeyboardRemove()
