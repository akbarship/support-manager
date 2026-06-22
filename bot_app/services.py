from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot
from aiogram.types import FSInputFile

from bot_app.database import Storage, local_now
from bot_app.texts import t


def start_at(date: str, hour: int) -> datetime:
    return datetime.fromisoformat(f"{date}T{hour:02d}:00:00")


async def reminder_loop(bot: Bot, storage: Storage) -> None:
    while True:
        try:
            await process_reminders(bot, storage)
        except Exception as error:
            print(f"Reminder xatosi: {error}")
        await asyncio.sleep(60)


async def process_reminders(bot: Bot, storage: Storage) -> None:
    for booking in storage.list_bookings(status="booked"):
        minutes = (start_at(booking.date, booking.start_hour) - local_now()).total_seconds() / 60
        learner = storage.get_user_by_phone(booking.user_phone)
        support = storage.get_support_teacher(booking.support_teacher_id)
        support_user = storage.get_user_by_phone(support.phone) if support else None

        if minutes <= 20 and minutes > 5 and not booking.reminded20:
            for user in (learner, support_user):
                if user and user.chat_id:
                    await bot.send_message(user.chat_id, f"⏰ {t('reminder_20', user.language)}")
            storage.mark_booking(booking.id, reminded20=True)

        if minutes <= 5 and minutes > 0 and not booking.reminded5:
            for user in (learner, support_user):
                if user and user.chat_id:
                    await bot.send_message(user.chat_id, f"🔔 {t('reminder_5', user.language)}")
            storage.mark_booking(booking.id, reminded5=True)


async def send_database_backup(bot: Bot, storage: Storage, channel_id: str, reason: str) -> None:
    timestamp = local_now().strftime("%Y-%m-%d_%H-%M-%S")
    with TemporaryDirectory() as temp_dir:
        backup_path = Path(temp_dir) / f"support-manager_{timestamp}.sqlite"
        storage.create_backup(str(backup_path))
        await bot.send_document(
            channel_id,
            FSInputFile(backup_path),
            caption=f"🗄 Database backup\nSabab: {reason}\nVaqt: {local_now():%Y-%m-%d %H:%M:%S}",
        )


async def backup_loop(bot: Bot, storage: Storage, channel_id: str) -> None:
    while True:
        current = local_now()
        tomorrow = current.replace(hour=0, minute=5, second=0, microsecond=0)
        if tomorrow <= current:
            tomorrow += timedelta(days=1)
        await asyncio.sleep((tomorrow - current).total_seconds())
        try:
            await send_database_backup(bot, storage, channel_id, "Kunlik backup")
        except Exception as error:
            print(f"Backup xatosi: {error}")
