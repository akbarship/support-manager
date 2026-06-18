from __future__ import annotations

import asyncio
import fcntl
import site
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

site.addsitedir(str(Path(__file__).resolve().parent / ".python_deps"))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from bot_app.config import load_config
from bot_app.database import Storage
from bot_app.handlers import setup_routers
from bot_app.services import backup_loop, reminder_loop, send_database_backup


class BotAlreadyRunningError(RuntimeError):
    pass


@contextmanager
def polling_lock(database_path: str) -> Iterator[None]:
    lock_path = Path(database_path).with_suffix(".polling.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BotAlreadyRunningError(
                "Bot allaqachon shu kompyuterda ishlayapti. Telegram polling uchun "
                "faqat bitta bot instance bo'lishi kerak."
            ) from exc

        lock_file.write(f"{Path.cwd()}\n")
        lock_file.flush()
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


async def main() -> None:
    config = load_config()

    with polling_lock(config.database_path):
        session = AiohttpSession(proxy=config.telegram_proxy) if config.telegram_proxy else AiohttpSession()
        bot = Bot(token=config.bot_token, session=session, default=DefaultBotProperties(parse_mode=None))
        dispatcher = Dispatcher(storage=MemoryStorage())
        storage = Storage(config.database_path)

        dispatcher["config"] = config
        dispatcher["storage"] = storage
        dispatcher.include_router(setup_routers())

        try:
            await send_database_backup(bot, storage, config.backup_channel_id, "Bot ishga tushdi")
        except Exception as error:
            print(f"Boshlang‘ich backup xatosi: {error}")
        reminder_task = asyncio.create_task(reminder_loop(bot, storage))
        backup_task = asyncio.create_task(backup_loop(bot, storage, config.backup_channel_id))
        try:
            print("Support Manager aiogram polling orqali ishga tushdi.")
            await dispatcher.start_polling(bot, drop_pending_updates=True)
        finally:
            reminder_task.cancel()
            backup_task.cancel()
            await asyncio.gather(reminder_task, backup_task, return_exceptions=True)
            try:
                await send_database_backup(bot, storage, config.backup_channel_id, "Bot to‘xtamoqda")
            except Exception as error:
                print(f"Yakuniy backup xatosi: {error}")
            storage.close()
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except BotAlreadyRunningError as exc:
        print(exc)
