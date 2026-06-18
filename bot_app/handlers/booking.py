from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot_app.config import Config
from bot_app.database import Storage, User, local_now
from bot_app.keyboards import (
    back_to_main_keyboard,
    category_keyboard,
    contact_keyboard,
    date_keyboard,
    duration_keyboard,
    inline,
    learner_booking_actions_keyboard,
    rating_keyboard,
    slots_keyboard,
    support_browser_keyboard,
    support_info,
    support_keyboard,
    language_keyboard,
)
from bot_app.texts import t, title

router = Router()


async def delete_callback_message(callback: CallbackQuery) -> None:
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass


def today(offset: int = 0) -> str:
    return (local_now() + timedelta(days=offset)).date().isoformat()


def start_at(date: str, hour: int) -> datetime:
    return datetime.fromisoformat(f"{date}T{hour:02d}:00:00")


def hours_until(date: str, hour: int) -> float:
    return (start_at(date, hour) - local_now()).total_seconds() / 3600


def current_user(callback: CallbackQuery, storage: Storage) -> User | None:
    return storage.get_user_by_telegram_id(callback.from_user.id)


def username_line(user: User | None) -> str:
    if not user or not user.username:
        return ""
    return f"🔗 Username: @{user.username}"


async def require_user(callback: CallbackQuery, storage: Storage) -> User | None:
    user = current_user(callback, storage)
    if not user and callback.message:
        await callback.message.answer(t("choose_language", "uz"), reply_markup=language_keyboard())
    return user


@router.callback_query(F.data == "show_categories")
async def show_categories(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    if not storage.list_categories():
        await callback.message.answer(f"📭 {t('no_support_types')}", reply_markup=back_to_main_keyboard(user))
        return
    await callback.message.answer(f"🧑‍🏫 {t('support_teachers', user.language)}\n{t('choose_support_type', user.language)}", reply_markup=category_keyboard(storage))


@router.callback_query(F.data.startswith("cat:"))
async def show_supports(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    category_id = int(callback.data.split(":")[1])
    await send_support_browser(callback, storage, category_id, 0)


@router.callback_query(F.data.startswith("browse:"))
async def browse_supports(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, category_id, index = callback.data.split(":")
    await send_support_browser(callback, storage, int(category_id), int(index))


async def send_support_browser(callback: CallbackQuery, storage: Storage, category_id: int, index: int) -> None:
    if not callback.message:
        return
    user = await require_user(callback, storage)
    supports = storage.list_support_teachers(category_id)
    if not supports:
        await callback.message.answer(
            f"📭 {t('no_support')}",
            reply_markup=inline([[("⬅️ Yo‘nalishlarga qaytish", "show_categories")]]),
        )
        return
    safe_index = max(0, min(index, len(supports) - 1))
    support = supports[safe_index]
    await callback.message.answer(
        support_info(storage, support, category_id),
        reply_markup=support_browser_keyboard(category_id, safe_index, len(supports), support.id),
    )


@router.callback_query(F.data.startswith("choose_support:"))
async def choose_support(callback: CallbackQuery) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    parts = callback.data.split(":")
    _, category_id, support_id = parts[:3]
    support_index = int(parts[3]) if len(parts) > 3 else 0
    if callback.message:
        await callback.message.answer(title("📅 Sana tanlang", "Dars kunini tanlang."), reply_markup=date_keyboard(today, int(support_id), int(category_id), support_index))


@router.callback_query(F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    parts = callback.data.split(":")
    if len(parts) == 5:
        _, category_id, support_id, support_index, date = parts
    else:
        _, category_id, support_id, date = parts
        support_index = "0"
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    await callback.message.answer(
        title("🕘 Bo‘sh vaqt", "Quyidan vaqtni tanlang."),
        reply_markup=slots_keyboard(storage, int(category_id), int(support_id), int(support_index), date, user, hours_until, start_at),
    )


@router.callback_query(F.data.startswith("slot:"))
async def choose_slot(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    parts = callback.data.split(":")
    if len(parts) == 6:
        _, category_id, support_id, support_index, date, hour = parts
    else:
        _, category_id, support_id, date, hour = parts
        support_index = "0"
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    await callback.message.answer(
        title("⏱ Davomiylik", "Dars necha soat bo‘ladi?"),
        reply_markup=duration_keyboard(int(category_id), int(support_id), int(support_index), date, int(hour)),
    )


@router.callback_query(F.data.startswith("book:"))
async def book(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    parts = callback.data.split(":")
    if len(parts) == 7:
        _, category_id, support_id, support_index, date, hour, duration = parts
    else:
        _, category_id, support_id, date, hour, duration = parts
        support_index = "0"
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    if user.banned_until and datetime.fromisoformat(user.banned_until) > local_now():
        await callback.message.answer(f"🚫 Siz vaqtincha band qila olmaysiz.\nBan tugaydi: {user.banned_until[:10]}", reply_markup=back_to_main_keyboard(user))
        return
    booking = storage.create_booking(user.role, user.phone, int(support_id), int(category_id), date, int(hour), int(duration))
    if not booking:
        await callback.message.answer(
            "⚠️ Bu vaqt band yoki mavjud emas.",
            reply_markup=inline([[("⬅️ Bo‘sh vaqtlarga qaytish", f"date:{category_id}:{support_id}:{support_index}:{date}")]]),
        )
        return
    support = storage.get_support_teacher(int(support_id))
    support_user = storage.get_user_by_phone(support.phone) if support else None
    await callback.message.answer(
        "\n".join(filter(None, [
            f"✅ {t('booked', user.language)}",
            f"📅 {date}",
            f"🕘 {hour}:00",
            f"⏱ {duration} soat",
            f"🧑‍🏫 Support Teacher: {support.name} {support.surname}" if support else "",
            f"📱 Telefon: {support.phone}" if support else "",
            username_line(support_user),
        ])),
        reply_markup=back_to_main_keyboard(user),
    )
    if support_user and support_user.chat_id:
        await callback.bot.send_message(
            support_user.chat_id,
            "\n".join(filter(None, [
                "📚 Yangi dars",
                f"📅 {date}",
                f"🕘 {hour}:00",
                f"⏱ {duration} soat",
                f"👤 {user.name} {user.surname}",
                f"📱 Telefon: {user.phone}",
                username_line(user),
            ])),
            reply_markup=support_keyboard(),
        )


@router.callback_query(F.data == "learner:bookings")
async def learner_bookings(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    bookings = storage.list_bookings(user_phone=user.phone, status="booked")
    if not bookings:
        await callback.message.answer("📭 Aktiv darslaringiz yo‘q.", reply_markup=back_to_main_keyboard(user))
        return
    visible = bookings[:10]
    for index, booking in enumerate(visible):
        support = storage.get_support_teacher(booking.support_teacher_id)
        await callback.message.answer(
            "\n".join(filter(None, [
                "📚 Dars",
                f"📅 {booking.date}",
                f"🕘 {booking.start_hour}:00 ({booking.duration} soat)",
                f"🧑‍🏫 Support Teacher: {support.name if support else ''} {support.surname if support else ''}",
                f"📱 Telefon: {support.phone if support else ''}",
                username_line(storage.get_user_by_phone(support.phone) if support else None),
            ])),
            reply_markup=learner_booking_actions_keyboard(booking.id, user, index == len(visible) - 1),
        )


@router.callback_query(F.data.startswith("learner_cancel:"))
async def learner_cancel(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    booking_id = int(callback.data.split(":")[1])
    booking = storage.get_booking(booking_id)
    if not booking or booking.user_phone != user.phone or booking.status != "booked":
        await callback.message.answer(
            "⚠️ Bu dars topilmadi yoki allaqachon bekor qilingan.",
            reply_markup=inline([[("⬅️ Darslarimga qaytish", "learner:bookings")]]),
        )
        return
    if hours_until(booking.date, booking.start_hour) < 2:
        await callback.message.answer(
            "⏳ Darsni kamida 2 soat oldin bekor qilish mumkin.",
            reply_markup=inline([[("⬅️ Darslarimga qaytish", "learner:bookings")]]),
        )
        return
    storage.cancel_booking(booking.id, "learner_cancelled")
    support = storage.get_support_teacher(booking.support_teacher_id)
    support_user = storage.get_user_by_phone(support.phone) if support else None
    await callback.message.answer(
        "✅ Dars bekor qilindi.",
        reply_markup=inline([[("⬅️ Darslarimga qaytish", "learner:bookings")]]),
    )
    if support_user and support_user.chat_id:
        await callback.bot.send_message(
            support_user.chat_id,
            "\n".join([
                "🚫 Dars bekor qilindi",
                f"📅 {booking.date}",
                f"🕘 {booking.start_hour}:00 ({booking.duration} soat)",
                f"👤 {user.name} {user.surname}",
                f"📱 Telefon: {user.phone}",
                username_line(user),
            ]),
            reply_markup=support_keyboard(),
        )


@router.callback_query(F.data.startswith("rate:"))
async def rate(callback: CallbackQuery, storage: Storage, config: Config) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, booking_id, rating = callback.data.split(":")
    user = await require_user(callback, storage)
    if not user or not callback.message:
        return
    feedback = storage.add_feedback(int(booking_id), int(rating))
    if not feedback:
        await callback.message.answer("⚠️ Bu dars uchun feedback allaqachon yuborilgan.", reply_markup=back_to_main_keyboard(user))
        return
    booking = storage.get_booking(int(booking_id))
    support = storage.get_support_teacher(booking.support_teacher_id) if booking else None
    support_user = storage.get_user_by_phone(support.phone) if support else None
    learner = storage.get_user_by_phone(booking.user_phone) if booking else None
    if support_user and support_user.chat_id and booking and support:
        updated_support = storage.get_support_teacher(support.id)
        await callback.bot.send_message(
            support_user.chat_id,
            "\n".join([
                "⭐ Yangi anonim feedback",
                "📚 Dars",
                f"📅 {booking.date}",
                f"🕘 {booking.start_hour}:00",
                f"⭐ Baho: {rating}/5",
                f"📊 Reyting: {updated_support.rating}/5 ({updated_support.rating_count})",
            ]),
            reply_markup=back_to_main_keyboard({"role": "support_teacher"}),
        )
    if config.feedback_channel_id and booking and support:
        updated_support = storage.get_support_teacher(support.id)
        try:
            await callback.bot.send_message(
                config.feedback_channel_id,
                "\n".join(filter(None, [
                    "⭐ Support Teacher feedback",
                    f"🧑‍🏫 {support.name} {support.surname}",
                    f"📱 Support telefon: {support.phone}",
                    "📚 Dars",
                    f"📅 {booking.date}",
                    f"🕘 {booking.start_hour}:00 ({booking.duration} soat)",
                    f"⭐ Baho: {rating}/5",
                    f"📊 Reyting: {updated_support.rating}/5 ({updated_support.rating_count})" if updated_support else "",
                    f"👤 Feedback bergan: {learner.name} {learner.surname}" if learner else "",
                    f"📱 Telefon: {learner.phone}" if learner else "",
                ])),
            )
        except Exception:
            pass
    await callback.message.answer("🙏 Feedback uchun rahmat.", reply_markup=back_to_main_keyboard(user))


def rating_markup_for_reminder(booking_id: int):
    return rating_keyboard(booking_id)
