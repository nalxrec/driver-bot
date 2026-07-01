from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.reply import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Это бот-кабинет водителя.\n"
        "Выбери нужное действие:",
        reply_markup=main_menu_keyboard()
    )


@router.message(F.text == "📋 Зарегистрироваться")
async def btn_register(message: Message, state: FSMContext):
    from bot.handlers.registration import cmd_register
    await cmd_register(message, state)


@router.message(F.text == "🔒 Сверка пломб")
async def btn_checkseals(message: Message, state: FSMContext):
    from bot.handlers.seals_loading import cmd_checkseals
    await cmd_checkseals(message, state)


@router.message(F.text == "🚢 Проверка перед портом")
async def btn_portcheck(message: Message, state: FSMContext):
    from bot.handlers.port_checkin import cmd_portcheck
    await cmd_portcheck(message, state)
