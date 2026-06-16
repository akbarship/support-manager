from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot_app.config import Config
from bot_app.database import Booking, Storage, SupportTeacher, User, schedule_template_for_date
from bot_app.keyboards import (
    back_to_main_keyboard,
    booking_actions_keyboard,
    rating_keyboard,
    schedule_edit_keyboard,
    schedule_template_edit_keyboard,
    schedule_template_keyboard,
)

router = Router()


async def delete_callback_message(callback: CallbackQuery) -> None:
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass


def today(offset: int = 0) -> str:
    return (datetime.now() + timedelta(days=offset)).date().isoformat()


def start_at(date: str, hour: int) -> datetime:
    return datetime.fromisoformat(f"{date}T{hour:02d}:00:00")


def hours_until(date: str, hour: int) -> float:
    return (start_at(date, hour) - datetime.now()).total_seconds() / 3600


def current_support(callback: CallbackQuery, storage: Storage) -> tuple[User | None, SupportTeacher | None]:
    user = storage.get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role != "support_teacher":
        return user, None
    return user, storage.find_support_teacher_by_phone(user.phone)


def username_line(user: User | None) -> str:
    if not user or not user.username:
        return ""
    return f"🔗 Username: @{user.username}"


def completion_block_reason(booking: Booking) -> str | None:
    if datetime.now().date().isoformat() != booking.date:
        return f"⚠️ Bu darsni bugun yakunlab bo‘lmaydi.\n📅 Dars sanasi: {booking.date}"
    end_time = start_at(booking.date, booking.start_hour + booking.duration)
    if datetime.now() < end_time:
        return f"⚠️ Dars tugamasidan yakunlab bo‘lmaydi.\n🕘 Tugash vaqti: {booking.start_hour + booking.duration}:00"
    return None


async def notify_admins(config: Config, storage: Storage, text: str, callback: CallbackQuery) -> None:
    admin_ids = set(config.admin_ids) | set(storage.list_admin_chat_ids())
    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(admin_id, text)
        except Exception:
            pass


def find_replacement(storage: Storage, booking: Booking, old_support_id: int) -> SupportTeacher | None:
    return next(
        (
            candidate
            for candidate in storage.list_support_teachers(booking.category_id)
            if candidate.id != old_support_id and all(hour in storage.get_open_slots(candidate.id, booking.date) for hour in booking.hours)
        ),
        None,
    )


def move_booking_to_replacement(storage: Storage, booking: Booking, old_support_id: int) -> tuple[SupportTeacher | None, Booking | None]:
    replacement = find_replacement(storage, booking, old_support_id)
    storage.cancel_booking(booking.id, "support_teacher_cancelled")
    if not replacement:
        return None, None
    new_booking = storage.create_booking(
        booking.role,
        booking.user_phone,
        replacement.id,
        booking.category_id,
        booking.date,
        booking.start_hour,
        booking.duration,
    )
    return replacement, new_booking


async def notify_reassigned_booking(callback: CallbackQuery, storage: Storage, old_booking: Booking, replacement: SupportTeacher | None, new_booking: Booking | None) -> None:
    learner = storage.get_user_by_phone(old_booking.user_phone)
    if replacement and new_booking:
        replacement_user = storage.get_user_by_phone(replacement.phone)
        if learner and learner.chat_id:
            await callback.bot.send_message(
                learner.chat_id,
                "\n".join(filter(None, [
                    f"🔄 Darsingiz boshqa Support Teacherga o‘tkazildi",
                    f"📚 Yangi dars #{new_booking.id}",
                    f"📅 {old_booking.date}",
                    f"🕘 {old_booking.start_hour}:00 ({old_booking.duration} soat)",
                    f"🧑‍🏫 {replacement.name} {replacement.surname}",
                    f"📱 Telefon: {replacement.phone}",
                    username_line(replacement_user),
                ])),
            )
        if replacement_user and replacement_user.chat_id:
            await callback.bot.send_message(
                replacement_user.chat_id,
                "\n".join(filter(None, [
                    f"📚 Sizga yangi dars biriktirildi #{new_booking.id}",
                    f"📅 {old_booking.date}",
                    f"🕘 {old_booking.start_hour}:00 ({old_booking.duration} soat)",
                    f"👤 {learner.name if learner else ''} {learner.surname if learner else ''}",
                    f"📱 Telefon: {learner.phone if learner else old_booking.user_phone}",
                    username_line(learner),
                ])),
            )
        return
    if learner and learner.chat_id:
        await callback.bot.send_message(
            learner.chat_id,
            f"🚫 Dars #{old_booking.id} bekor qilindi.\nHozircha o‘rniga bo‘sh Support Teacher topilmadi.",
        )


@router.callback_query(F.data == "support:schedule")
async def schedule(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    if support and callback.message:
        await callback.message.answer(
            "🗓 Jadval shabloni\nQaysi kunlar uchun vaqtlarni sozlaysiz?",
            reply_markup=schedule_template_keyboard(),
        )


@router.callback_query(F.data.startswith("schedule_template:"))
async def schedule_template(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    if not support or not callback.message:
        return
    template_key = callback.data.split(":")[1]
    label = "Toq kunlar" if template_key == "odd" else "Juft kunlar"
    await callback.message.answer(
        f"🗓 {label} shabloni\nOchiq yoki yopiq vaqtlarni tanlang.",
        reply_markup=schedule_template_edit_keyboard(storage, support.id, template_key),
    )


@router.callback_query(F.data.startswith("toggle_template_slot:"))
async def toggle_template_slot(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    if not support or not callback.message:
        return
    _, template_key, hour = callback.data.split(":")
    hour_int = int(hour)
    is_open = hour_int in storage.get_template_open_slots(support.id, template_key)
    storage.set_template_slot_open(support.id, template_key, hour_int, not is_open)
    label = "Toq kunlar" if template_key == "odd" else "Juft kunlar"
    moved_count = 0
    cancelled_count = 0
    if is_open:
        affected_bookings = [
            booking
            for booking in storage.list_bookings(support_id=support.id, status="booked")
            if schedule_template_for_date(booking.date) == template_key
            and hour_int in booking.hours
            and start_at(booking.date, booking.start_hour) > datetime.now()
        ]
        for booking in affected_bookings:
            replacement, new_booking = move_booking_to_replacement(storage, booking, support.id)
            await notify_reassigned_booking(callback, storage, booking, replacement, new_booking)
            if replacement and new_booking:
                moved_count += 1
            else:
                cancelled_count += 1
    summary = ""
    if moved_count or cancelled_count:
        summary = f"\n🔄 Ko‘chirilgan darslar: {moved_count}\n🚫 Bekor qilingan darslar: {cancelled_count}"
    await callback.message.answer(
        f"🗓 {label} shabloni\nOchiq yoki yopiq vaqtlarni tanlang.{summary}",
        reply_markup=schedule_template_edit_keyboard(storage, support.id, template_key),
    )


@router.callback_query(F.data.startswith("toggle_slot:"))
async def toggle_slot(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    if not support or not callback.message:
        return
    _, date, hour = callback.data.split(":")
    hour_int = int(hour)
    is_open = hour_int in storage.get_open_slots(support.id, date)
    storage.set_slot_open(support.id, date, hour_int, not is_open)
    moved_count = 0
    cancelled_count = 0
    if is_open:
        affected_bookings = [
            booking
            for booking in storage.list_bookings(support_id=support.id, status="booked")
            if booking.date == date
            and hour_int in booking.hours
            and start_at(booking.date, booking.start_hour) > datetime.now()
        ]
        for booking in affected_bookings:
            replacement, new_booking = move_booking_to_replacement(storage, booking, support.id)
            await notify_reassigned_booking(callback, storage, booking, replacement, new_booking)
            if replacement and new_booking:
                moved_count += 1
            else:
                cancelled_count += 1
    summary = ""
    if moved_count or cancelled_count:
        summary = f"\n🔄 Ko‘chirilgan darslar: {moved_count}\n🚫 Bekor qilingan darslar: {cancelled_count}"
    await callback.message.answer(f"🗓 {date} jadvali\nOchiq yoki yopiq vaqtlarni tanlang.{summary}", reply_markup=schedule_edit_keyboard(storage, support.id, date))


@router.callback_query(F.data == "support:bookings")
async def support_bookings(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    if not support or not callback.message:
        return
    bookings = storage.list_bookings(support_id=support.id, status="booked")
    if not bookings:
        await callback.message.answer("📭 Aktiv darslar yo‘q.", reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
        return
    visible = bookings[:10]
    for index, booking in enumerate(visible):
        user = storage.get_user_by_phone(booking.user_phone)
        await callback.message.answer(
            "\n".join([
                f"📚 Dars #{booking.id}",
                f"📅 {booking.date}",
                f"🕘 {booking.start_hour}:00 ({booking.duration} soat)",
                f"👤 {user.name if user else ''} {user.surname if user else ''}",
            ]),
            reply_markup=booking_actions_keyboard(booking.id, index == len(visible) - 1),
        )


@router.callback_query(F.data == "support:stats")
async def support_stats(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    if not support or not callback.message:
        return
    month = today()[:7]
    await callback.message.answer(
        "\n".join([
            f"🧑‍🏫 {support.name} {support.surname}",
            f"⭐ Reyting: {support.rating}/5" if support.rating_count else "⭐ Reyting: Hali yo‘q",
            f"🏆 Shu oy: {support.monthly_conducted.get(month, 0)}/100",
            f"✅ Jami: {support.conducted_lessons}",
        ]),
        reply_markup=back_to_main_keyboard({"role": "support_teacher"}),
    )


@router.callback_query(F.data.startswith("support_cancel:"))
async def support_cancel(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    booking_id = int(callback.data.split(":")[1])
    booking = storage.get_booking(booking_id)
    if not support or not booking or booking.support_teacher_id != support.id or not callback.message:
        return
    if hours_until(booking.date, booking.start_hour) < 4:
        await callback.message.answer("⏳ Darsni kamida 4 soat oldin bekor qilish mumkin.", reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
        return
    replacement, new_booking = move_booking_to_replacement(storage, booking, support.id)
    if replacement and new_booking:
        await callback.message.answer(f"✅ Dars bekor qilindi. O‘rniga {replacement.name} {replacement.surname} biriktirildi.", reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
        await notify_reassigned_booking(callback, storage, booking, replacement, new_booking)
        return

    await callback.message.answer(f"✅ Dars #{booking.id} bekor qilindi. Bo‘sh Support Teacher topilmadi.", reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
    await notify_reassigned_booking(callback, storage, booking, replacement, new_booking)


@router.callback_query(F.data.startswith("no_show:"))
async def no_show(callback: CallbackQuery, storage: Storage, config: Config) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    booking_id = int(callback.data.split(":")[1])
    booking = storage.get_booking(booking_id)
    if not support or not booking or booking.support_teacher_id != support.id or not callback.message:
        return
    if datetime.now().date().isoformat() != booking.date or datetime.now() < start_at(booking.date, booking.start_hour):
        await callback.message.answer("⚠️ O‘quvchi kelmadi deb belgilash faqat dars vaqti kelgandan keyin mumkin.", reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
        return
    result = storage.record_no_show(booking.id)
    if not result:
        return
    user = result["user"]
    count = result["count"]
    banned_until = result["banned_until"]
    learner_text = (
        f"🚫 Siz darsga 3 marta kelmadingiz.\n2 haftaga ban berildi.\nBan tugaydi: {banned_until[:10]}"
        if banned_until
        else f"⚠️ Ogohlantirish {count}/3.\nDarsga kelmaslik 3 martaga yetsa 2 haftalik ban beriladi."
    )
    if user.chat_id:
        await callback.bot.send_message(user.chat_id, learner_text)
    await notify_admins(
        config,
        storage,
        "\n".join(filter(None, [
            "🚫 O‘quvchiga ban berildi" if banned_until else "⚠️ O‘quvchiga ogohlantirish berildi",
            f"👤 {user.name} {user.surname}",
            f"📱 {user.phone}",
            f"📚 Dars #{booking.id}",
            f"Hisob: {count}/3",
            f"Ban tugaydi: {banned_until[:10]}" if banned_until else "",
        ])),
        callback,
    )
    await callback.message.answer(
        "🚫 O‘quvchi 2 haftaga ban qilindi." if banned_until else f"⚠️ Ogohlantirish berildi: {count}/3",
        reply_markup=back_to_main_keyboard({"role": "support_teacher"}),
    )


@router.callback_query(F.data.startswith("complete:"))
async def complete(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    _, support = current_support(callback, storage)
    booking_id = int(callback.data.split(":")[1])
    booking = storage.get_booking(booking_id)
    if not support or not booking or booking.support_teacher_id != support.id or not callback.message:
        return
    block_reason = completion_block_reason(booking)
    if block_reason:
        await callback.message.answer(block_reason, reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
        return
    storage.complete_booking(booking.id)
    learner = storage.get_user_by_phone(booking.user_phone)
    if learner and learner.chat_id:
        await callback.bot.send_message(learner.chat_id, f"⭐ Dars #{booking.id} uchun baho bering.", reply_markup=rating_keyboard(booking.id))
    await callback.message.answer(f"✅ Dars #{booking.id} yakunlandi.", reply_markup=back_to_main_keyboard({"role": "support_teacher"}))
