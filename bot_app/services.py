from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot

from bot_app.database import Storage, local_now


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
                    await bot.send_message(user.chat_id, f"⏰ Dars #{booking.id} 20 daqiqadan keyin boshlanadi.")
            storage.mark_booking(booking.id, reminded20=True)

        if minutes <= 5 and minutes > 0 and not booking.reminded5:
            for user in (learner, support_user):
                if user and user.chat_id:
                    await bot.send_message(user.chat_id, f"🔔 Dars #{booking.id} 5 daqiqadan keyin boshlanadi.")
            storage.mark_booking(booking.id, reminded5=True)
