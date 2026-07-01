"""
ВРЕМЕННЫЙ файл — нужен только чтобы один раз узнать ID группы модерации.
После того как впишешь MODERATION_CHAT_ID в .env, этот файл и его подключение
в main.py можно удалить.
"""

from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def show_chat_id(message: Message):
    print(f"\n=== ID этого чата: {message.chat.id} (название: {message.chat.title or message.chat.full_name}) ===\n")
    await message.answer(f"ID этого чата: `{message.chat.id}`", parse_mode="Markdown")
