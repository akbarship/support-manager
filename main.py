from __future__ import annotations

import asyncio
import site
from pathlib import Path

site.addsitedir(str(Path(__file__).resolve().parent / ".python_deps"))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from bot_app.config import load_config
from bot_app.database import Storage
from bot_app.handlers import setup_routers
from bot_app.services import reminder_loop


async def main() -> None:
    config = load_config()
    session = AiohttpSession(proxy=config.telegram_proxy) if config.telegram_proxy else AiohttpSession()
    bot = Bot(token=config.bot_token, session=session, default=DefaultBotProperties(parse_mode=None))
    dispatcher = Dispatcher(storage=MemoryStorage())
    storage = Storage(config.database_path)

    dispatcher["config"] = config
    dispatcher["storage"] = storage
    dispatcher.include_router(setup_routers())

    reminder_task = asyncio.create_task(reminder_loop(bot, storage))
    try:
        print("Support Manager aiogram polling orqali ishga tushdi.")
        await dispatcher.start_polling(bot, drop_pending_updates=True)
    finally:
        reminder_task.cancel()
        storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
