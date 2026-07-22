import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot import config
from bot.db.database import init_db
from bot.handlers import start, registration, seals_loading, port_checkin, moderation


async def main():
    logging.basicConfig(level=logging.INFO)

    init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(seals_loading.router)
    dp.include_router(port_checkin.router)
    dp.include_router(moderation.router)
    

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
