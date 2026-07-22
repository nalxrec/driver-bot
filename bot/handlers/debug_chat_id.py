"""
ВРЕМЕННЫЙ файл — нужен только чтобы узнать ID тем в группе модерации.
После получения всех ID — удалить этот файл и убрать из main.py.
"""

from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def show_topic_id(message: Message):
    chat_id = message.chat.id
    topic_id = message.message_thread_id
    print(f"\n=== Группа ID: {chat_id} | Тема ID: {topic_id} ===\n")
    await message.answer(
        f"Chat ID: `{chat_id}`\n"
        f"Topic ID: `{topic_id}`",
        parse_mode="Markdown"
    )
