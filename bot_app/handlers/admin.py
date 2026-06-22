from __future__ import annotations

import sqlite3
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot_app.config import Config
from bot_app.database import Booking, Storage, User, is_sunday, local_now
from bot_app.keyboards import (
    admin_flow_keyboard,
    admin_keyboard,
    back_to_main_keyboard,
    category_button_rows,
    inline,
    support_category_keyboard,
)
from bot_app.states import AddAdmin, AddSupportTeacher, Broadcast, CreateCategory, EditCategory, EditSupportTeacher, StudentSearch
from bot_app.texts import ROLE_LABELS, title

router = Router()
PAGE_SIZE = 8


def is_admin(user_id: int | None, config: Config, storage: Storage | None = None) -> bool:
    return bool(user_id and (user_id in config.admin_ids or (storage and storage.is_admin_telegram_id(user_id))))


def is_env_admin(user_id: int | None, config: Config) -> bool:
    return bool(user_id and user_id in config.admin_ids)


async def delete_callback_message(callback: CallbackQuery) -> None:
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass


async def admin_prompt(message: Message, state: FSMContext, text: str, step: str | None = None) -> None:
    await message.answer(text, reply_markup=admin_flow_keyboard(step))


async def support_prompt(message: Message, text: str, step: str | None = None) -> None:
    await message.answer(text, reply_markup=admin_flow_keyboard(step))


async def delete_previous_prompt(message: Message, state: FSMContext) -> None:
    return


async def require_text(message: Message, state: FSMContext, prompt_text: str, step: str | None = None) -> str | None:
    value = (message.text or "").strip()
    if value:
        return value
    await admin_prompt(message, state, prompt_text, step)
    return None


def category_admin_rows(storage: Storage) -> list[list[tuple[str, str]]]:
    rows = [[("➕ Yo‘nalish yaratish", "create_category")]]
    rows.extend(
        category_button_rows(
            storage.list_categories(),
            lambda category: f"category:open:{category.id}",
        )
    )
    rows.append([("🏠 Admin menyu", "admin:menu")])
    return rows


def managed_admin_rows(storage: Storage) -> list[list[tuple[str, str]]]:
    rows = [[("➕ Admin qo‘shish", "admin:add_admin")]]
    for admin in storage.list_admins():
        name = f"{admin.name} {admin.surname}".strip()
        label = f"{name or admin.phone} | {admin.phone}"
        rows.append([(label, f"admin_user:open:{admin.phone}")])
    rows.append([("🏠 Admin menyu", "admin:menu")])
    return rows


def pagination_row(prefix: str, page: int, total: int) -> list[tuple[str, str]]:
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    row: list[tuple[str, str]] = []
    if page > 0:
        row.append(("⬅️", f"{prefix}:{page - 1}"))
    row.append((f"{page + 1}/{pages}", "noop"))
    if page + 1 < pages:
        row.append(("➡️", f"{prefix}:{page + 1}"))
    return row


def managed_support_rows(storage: Storage, page: int = 0) -> list[list[tuple[str, str]]]:
    supports = storage.list_support_teachers()
    pages = max(1, (len(supports) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    rows = [[("➕ Support Teacher qo‘shish", "admin:add_support")]]
    for support in supports[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        rating = f"{support.rating}/5"
        rows.append([(f"{support.name} {support.surname} | {rating}", f"support_admin:open:{support.id}")])
    rows.append(pagination_row("admin:supports_page", page, len(supports)))
    rows.append([("🏠 Admin menyu", "admin:menu")])
    return rows


def managed_student_rows(
    storage: Storage,
    page: int = 0,
    students: list[User] | None = None,
    prefix: str = "admin:students_page",
) -> list[list[tuple[str, str]]]:
    students = storage.list_students() if students is None else students
    pages = max(1, (len(students) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    rows: list[list[tuple[str, str]]] = [[("🔎 O‘quvchi qidirish", "admin:student_search")]]
    for student in students[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        name = f"{student.name} {student.surname}".strip()
        status = "🚫 Ban" if student.banned_until else "✅ Aktiv"
        rows.append([(f"{status} {name or student.phone} | {student.phone}", f"student_admin:open:{student.phone}")])
    rows.append(pagination_row(prefix, page, len(students)))
    rows.append([("🏠 Admin menyu", "admin:menu")])
    return rows


def student_admin_text(storage: Storage, phone: str) -> str:
    stats_data = storage.student_stats(phone)
    if not stats_data:
        return "⚠️ O‘quvchi topilmadi."
    user = stats_data["user"]
    ban_line = f"🚫 Ban tugaydi: {user.banned_until[:10]}" if user.banned_until else "✅ Ban yo‘q"
    upcoming_lines = [
        f"  {booking.date} {booking.start_hour}:00 ({booking.duration} soat)"
        + (f" — {booking.topic}" if booking.topic else "")
        for booking in stats_data["upcoming"]
    ] or ["  Aktiv dars yo‘q"]
    return "\n".join([
        f"🎓 {user.name} {user.surname}".strip(),
        f"📱 {user.phone}",
        f"🔗 Username: @{user.username}" if user.username else "🔗 Username: -",
        ban_line,
        f"👤 Kelmaganlar: {user.no_show_count}/3",
        "",
        "📊 Darslar",
        f"Jami: {stats_data['total']}",
        f"Aktiv: {stats_data['booked']}",
        f"Yakunlangan: {stats_data['completed']}",
        f"Bekor qilingan: {stats_data['cancelled']}",
        f"Kelmaganlar: {stats_data['no_show']}",
        "",
        "📅 Yaqin darslar",
        *upcoming_lines,
    ])


def support_categories_text(storage: Storage, category_ids: list[int]) -> str:
    names = [
        category.name
        for category_id in category_ids
        if (category := storage.get_category(int(category_id))) and category.active
    ]
    return ", ".join(names) if names else "-"


def support_admin_text(storage: Storage, support_id: int) -> str:
    stats_data = storage.support_teacher_stats(support_id)
    if not stats_data:
        return "⚠️ Support Teacher topilmadi."

    support = stats_data["support"]
    month = local_now().date().isoformat()[:7]
    rating = f"{support.rating}/5 ({support.rating_count})"
    recent_feedback = stats_data["recent_feedback"]
    feedback_lines = [
        f"  {item['lesson_date']} | {item['rating']}/5"
        for item in recent_feedback
    ] or ["  Hali yo‘q"]
    upcoming_lines = [
        f"  {booking.date} {booking.start_hour}:00 ({booking.duration} soat)"
        + (f" — {booking.topic}" if booking.topic else "")
        for booking in stats_data["upcoming"]
    ] or ["  Aktiv dars yo‘q"]

    return "\n".join([
        f"🧑‍🏫 {support.name} {support.surname}",
        f"📱 {support.phone}",
        f"🎧 IELTS: {support.ielts or '-'}",
        f"📖 CEFR: {support.cefr or '-'}",
        f"🧮 SAT: {support.sat or '-'}",
        f"🧭 Yo‘nalishlar: {support_categories_text(storage, support.categories)}",
        f"⭐ Reyting: {rating}",
        f"✅ O‘tilgan darslar: {support.conducted_lessons}",
        f"🏆 Shu oy: {support.monthly_conducted.get(month, 0)}/100",
        "",
        "📊 Darslar",
        f"Jami: {stats_data['total']}",
        f"Aktiv: {stats_data['booked']}",
        f"Yakunlangan: {stats_data['completed']}",
        f"Bekor qilingan: {stats_data['cancelled']}",
        f"Kelmaganlar: {stats_data['no_show']}",
        "",
        "📅 Yaqin darslar",
        *upcoming_lines,
        "",
        "⭐ Oxirgi feedbacklar",
        *feedback_lines,
    ])


def active_lessons_text(storage: Storage, page: int) -> tuple[str, int, int]:
    bookings = storage.list_bookings(status="booked")
    pages = max(1, (len(bookings) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    visible = bookings[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    blocks: list[str] = []
    for booking in visible:
        student = storage.get_user_by_phone(booking.user_phone)
        support = storage.get_support_teacher(booking.support_teacher_id)
        blocks.append("\n".join(filter(None, [
            f"🎓 {student.name} {student.surname}".strip() if student else f"🎓 {booking.user_phone}",
            f"📱 O‘quvchi: {student.phone}" if student else f"📱 O‘quvchi: {booking.user_phone}",
            f"🔗 @{student.username}" if student and student.username else "",
            f"🧑‍🏫 {support.name} {support.surname}" if support else "🧑‍🏫 Support Teacher topilmadi",
            f"📱 Support Teacher: {support.phone}" if support else "",
            f"📅 {booking.date}",
            f"🕘 {booking.start_hour}:00",
            f"📝 Mavzu: {booking.topic}" if booking.topic else "",
        ])))
    body = "\n\n".join(blocks) if blocks else "📭 Aktiv darslar yo‘q."
    return f"📚 Aktiv darslar: {len(bookings)}\n\n{body}", page, len(bookings)


def sunday_student_notice(booking: Booking, language: str) -> str:
    if language == "ru":
        return "\n".join(filter(None, [
            "Здравствуйте!",
            "",
            "К сожалению, по воскресеньям наш учебный центр не работает.",
            "Из-за технической ошибки ваш урок был записан на воскресенье, поэтому нам пришлось отменить эту запись.",
            "",
            f"📅 Отменённая дата: {booking.date}",
            f"🕘 Время: {booking.start_hour}:00",
            f"📝 Тема: {booking.topic}" if booking.topic else "",
            "",
            "Пожалуйста, откройте бот и выберите новое удобное время с понедельника по субботу.",
            "Приносим искренние извинения за неудобство и благодарим за понимание.",
        ]))
    return "\n".join(filter(None, [
        "Assalomu alaykum!",
        "",
        "Afsuski, o‘quv markazimiz yakshanba kunlari ishlamaydi.",
        "Texnik xatolik sabab darsingiz yakshanba kuniga band qilingan edi. Shu sababli ushbu darsni bekor qilishga majbur bo‘ldik.",
        "",
        f"📅 Bekor qilingan sana: {booking.date}",
        f"🕘 Vaqt: {booking.start_hour}:00",
        f"📝 Mavzu: {booking.topic}" if booking.topic else "",
        "",
        "Iltimos, bot orqali dushanbadan shanbagacha bo‘lgan kunlardan o‘zingizga qulay yangi vaqtni tanlang.",
        "Yuzaga kelgan noqulaylik uchun chin dildan uzr so‘raymiz va tushunganingiz uchun rahmat.",
    ]))


async def send_sunday_reset_prompt(message: Message, storage: Storage) -> None:
    sunday_count = sum(
        1 for booking in storage.list_bookings(status="booked")
        if is_sunday(booking.date)
    )
    await message.answer(
        "\n".join([
            "☀️ Yakshanbaga noto‘g‘ri band qilingan darslarni bekor qilish",
            f"Topilgan aktiv yakshanba darslari: {sunday_count}",
            "",
            "Tasdiqlasangiz, ushbu darslar bekor qilinadi va har bir o‘quvchiga sabab hamda boshqa kunni tanlash bo‘yicha muloyim xabar yuboriladi.",
        ]),
        reply_markup=inline([
            [("✅ Tasdiqlash va xabar yuborish", "admin:reset_sunday_execute")],
            [("❌ Bekor qilish", "admin:menu")],
        ]),
    )


@router.message(Command("admin"))
async def admin_panel(message: Message, config: Config, state: FSMContext, storage: Storage) -> None:
    if not is_admin(message.from_user.id if message.from_user else None, config, storage):
        await message.answer("🚫 Admin panelga ruxsat yo‘q.")
        return
    await state.clear()
    await message.answer(
        "👑 Admin panel",
        reply_markup=admin_keyboard(is_env_admin(message.from_user.id if message.from_user else None, config)),
    )


@router.callback_query(F.data == "admin:menu")
async def admin_menu(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config, storage):
        await callback.message.answer(
            "👑 Admin panel",
            reply_markup=admin_keyboard(is_env_admin(callback.from_user.id, config)),
        )


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config, storage):
        await callback.message.answer("❌ Amal bekor qilindi.", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config, storage):
        await callback.message.answer(
            "👑 Admin panel",
            reply_markup=admin_keyboard(is_env_admin(callback.from_user.id, config)),
        )


@router.callback_query(F.data == "admin:active_lessons")
async def active_lessons(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    text, page, total = active_lessons_text(storage, 0)
    rows = [pagination_row("admin:active_lessons_page", page, total)]
    rows.append([("🏠 Admin menyu", "admin:menu")])
    await callback.message.answer(text, reply_markup=inline(rows))


@router.callback_query(F.data.startswith("admin:active_lessons_page:"))
async def active_lessons_page(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    requested_page = int(callback.data.rsplit(":", 1)[1])
    text, page, total = active_lessons_text(storage, requested_page)
    rows = [pagination_row("admin:active_lessons_page", page, total)]
    rows.append([("🏠 Admin menyu", "admin:menu")])
    await callback.message.answer(text, reply_markup=inline(rows))


@router.message(Command("reset_sunday_lessons"))
async def reset_sunday_lessons_command(message: Message, config: Config, storage: Storage) -> None:
    if not is_env_admin(message.from_user.id if message.from_user else None, config):
        await message.answer("🚫 Bu buyruq faqat .env faylidagi ADMIN_IDS ro‘yxatida bor adminlar uchun.")
        return
    await send_sunday_reset_prompt(message, storage)


@router.callback_query(F.data == "admin:reset_sunday_lessons")
async def reset_sunday_lessons_menu(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message:
        return
    if not is_env_admin(callback.from_user.id, config):
        await callback.message.answer("🚫 Bu amal faqat asosiy admin uchun ruxsat etilgan.")
        return
    await send_sunday_reset_prompt(callback.message, storage)


@router.callback_query(F.data == "admin:reset_sunday_execute")
async def reset_sunday_lessons_execute(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message:
        return
    if not is_env_admin(callback.from_user.id, config):
        await callback.message.answer("🚫 Bu amal faqat asosiy admin uchun ruxsat etilgan.")
        return
    cancelled = storage.cancel_sunday_bookings()
    notified = 0
    for booking in cancelled:
        student = storage.get_user_by_phone(booking.user_phone)
        if student and student.chat_id:
            try:
                await callback.bot.send_message(
                    student.chat_id,
                    sunday_student_notice(booking, student.language),
                )
                notified += 1
            except Exception:
                pass
        support = storage.get_support_teacher(booking.support_teacher_id)
        support_user = storage.get_user_by_phone(support.phone) if support else None
        if support_user and support_user.chat_id:
            try:
                await callback.bot.send_message(
                    support_user.chat_id,
                    "\n".join(filter(None, [
                        "☀️ Assalomu alaykum. Noqulaylik uchun uzr so‘raymiz. Texnik xatolik sababli botda yakshanba kuni uchun dars vaqtlari noto‘g‘ri ochib yuborilgan. Aslida markazimiz yakshanba kunlari faoliyat yuritmaydi, shu sababli rejalashtirilgan darsingizni o‘tkaza olmaymiz.\n\nDarsni boshqa kunga ko‘chirish uchun iltimos, o‘zingizga qulay kun va vaqtni tanlab, qayta bron qiling. Biz siz bilan tanlangan vaqtda darsni mamnuniyat bilan o‘tkazamiz.\n\nYana bir bor yuzaga kelgan noqulaylik uchun uzr so‘raymiz va vaziyatni tushunganingiz uchun rahmat. Agar savollaringiz bo‘lsa, bemalol murojaat qilishingiz mumkin. 🙏",
                        f"📅 {booking.date}",
                        f"🕘 {booking.start_hour}:00",
                        f"📝 Mavzu: {booking.topic}" if booking.topic else "",
                    ])),
                )
            except Exception:
                pass
    await callback.message.answer(
        "\n".join([
            f"✅ Bekor qilingan yakshanba darslari: {len(cancelled)}",
            f"📨 Xabar yetkazilgan o‘quvchilar: {notified}",
        ]),
        reply_markup=admin_keyboard(True),
    )


@router.callback_query(F.data == "admin:reset_lessons")
async def reset_lessons_first_confirmation(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message:
        return
    if not is_env_admin(callback.from_user.id, config):
        await callback.message.answer("🚫 Bu amal faqat asosiy admin uchun ruxsat etilgan.")
        return
    active_count = len(storage.list_bookings(status="booked"))
    await callback.message.answer(
        "\n".join([
            "⚠️ Barcha aktiv darslar bekor qilinadi.",
            f"Aktiv darslar: {active_count}",
            "Davom etasizmi?",
        ]),
        reply_markup=inline([
            [("Davom etish", "admin:reset_lessons_confirm")],
            [("❌ Bekor qilish", "admin:menu")],
        ]),
    )


@router.callback_query(F.data == "admin:reset_lessons_confirm")
async def reset_lessons_second_confirmation(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message:
        return
    if not is_env_admin(callback.from_user.id, config):
        await callback.message.answer("🚫 Bu amal faqat asosiy admin uchun ruxsat etilgan.")
        return
    await callback.message.answer(
        "🚨 Oxirgi tasdiqlash\nBu amal barcha aktiv darslarni darhol bekor qiladi.",
        reply_markup=inline([
            [("✅ Ha, barchasini bekor qilish", "admin:reset_lessons_execute")],
            [("❌ Yo‘q", "admin:menu")],
        ]),
    )


@router.callback_query(F.data == "admin:reset_lessons_execute")
async def reset_lessons_execute(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message:
        return
    if not is_env_admin(callback.from_user.id, config):
        await callback.message.answer("🚫 Bu amal faqat asosiy admin uchun ruxsat etilgan.")
        return
    cancelled = storage.cancel_all_bookings()
    await callback.message.answer(
        f"✅ {cancelled} ta aktiv dars bekor qilindi.",
        reply_markup=admin_keyboard(True),
    )


@router.callback_query(F.data == "admin:admins")
async def admins(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await callback.message.answer(title("👑 Adminlar", "Bot adminlarini boshqaring."), reply_markup=inline(managed_admin_rows(storage)))


@router.callback_query(F.data == "admin:add_admin")
async def add_admin_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await state.set_state(AddAdmin.phone)
    await admin_prompt(callback.message, state, title("📱 Telefon raqam", "Yangi admin telefon raqamini kiriting."), "phone")


@router.message(AddAdmin.phone)
async def add_admin_phone(message: Message, state: FSMContext) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Telefon raqamni matn ko‘rinishida yuboring.", "phone")
    if not value:
        return
    await state.update_data(phone=value)
    await state.set_state(AddAdmin.name)
    await admin_prompt(message, state, title("👤 Ism", "Admin ismini kiriting."), "name")


@router.message(AddAdmin.name)
async def add_admin_name(message: Message, state: FSMContext) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Ismni matn ko‘rinishida yuboring.", "name")
    if not value:
        return
    await state.update_data(name=value)
    await state.set_state(AddAdmin.surname)
    await admin_prompt(message, state, title("👤 Familiya", "Admin familiyasini kiriting."), "surname")


@router.message(AddAdmin.surname)
async def add_admin_surname(message: Message, state: FSMContext, storage: Storage) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Familiyani matn ko‘rinishida yuboring.", "surname")
    if not value:
        return
    data = await state.get_data()
    user = storage.add_admin(data["phone"], data["name"], value)
    await state.clear()
    await message.answer(
        f"✅ Admin qo‘shildi\n👤 {user.name} {user.surname}\n📱 {user.phone}",
        reply_markup=back_to_main_keyboard({"role": "admin"}),
    )


@router.callback_query(F.data.startswith("admin_user:open:"))
async def open_admin(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    user = storage.get_user_by_phone(phone)
    if not user:
        await callback.message.answer("⚠️ Admin topilmadi.", reply_markup=inline(managed_admin_rows(storage)))
        return
    await callback.message.answer(
        "\n".join([
            f"👤 {user.name} {user.surname}".strip(),
            f"📱 {user.phone}",
            f"🔐 Role: {ROLE_LABELS.get(user.role, user.role)}",
        ]),
        reply_markup=inline([
            [("🗑 Adminlikdan olish", f"admin_user:delete:{user.phone}")],
            [("⬅️ Adminlar", "admin:admins")],
        ]),
    )


@router.callback_query(F.data.startswith("admin_user:delete:"))
async def delete_admin_confirm(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    user = storage.get_user_by_phone(phone)
    if not user:
        await callback.message.answer("⚠️ Admin topilmadi.", reply_markup=inline(managed_admin_rows(storage)))
        return
    await callback.message.answer(
        f"🗑 {user.name or user.phone} adminlikdan olinsinmi?",
        reply_markup=inline([
            [("✅ Ha, olish", f"admin_user:delete_confirm:{user.phone}")],
            [("⬅️ Bekor qilish", f"admin_user:open:{user.phone}")],
        ]),
    )


@router.callback_query(F.data.startswith("admin_user:delete_confirm:"))
async def delete_admin_finish(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    if storage.get_user_by_telegram_id(callback.from_user.id) and storage.get_user_by_telegram_id(callback.from_user.id).phone == phone:
        await callback.message.answer("⚠️ O‘zingizni adminlikdan ola olmaysiz.", reply_markup=inline(managed_admin_rows(storage)))
        return
    removed = storage.remove_admin(phone)
    if not removed:
        await callback.message.answer("⚠️ Admin topilmadi.", reply_markup=inline(managed_admin_rows(storage)))
        return
    await callback.message.answer("✅ Admin o‘chirildi.", reply_markup=inline(managed_admin_rows(storage)))


@router.callback_query(F.data == "admin:add_support")
async def start_add_support(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await state.set_state(AddSupportTeacher.phone)
    await state.update_data(prompt_message_id=None)
    await support_prompt(callback.message, title("📱 Telefon raqam", "Support Teacher telefon raqamini kiriting."), "phone")


@router.message(AddSupportTeacher.phone)
async def add_support_phone(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await support_prompt(message, "⚠️ Telefon raqamni matn ko‘rinishida yuboring.", "phone")
        return
    await state.update_data(phone=value)
    await state.set_state(AddSupportTeacher.name)
    await support_prompt(message, title("👤 Ism", "Ismini kiriting."), "name")


@router.message(AddSupportTeacher.name)
async def add_support_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await support_prompt(message, "⚠️ Ismni matn ko‘rinishida yuboring.", "name")
        return
    await state.update_data(name=value)
    await state.set_state(AddSupportTeacher.surname)
    await support_prompt(message, title("👤 Familiya", "Familiyasini kiriting."), "surname")


@router.message(AddSupportTeacher.surname)
async def add_support_surname(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await support_prompt(message, "⚠️ Familiyani matn ko‘rinishida yuboring.", "surname")
        return
    await state.update_data(surname=value)
    await state.set_state(AddSupportTeacher.ielts)
    await support_prompt(message, title("🎧 IELTS", 'Ballni kiriting. Yo‘q bo‘lsa "-" yuboring.'), "ielts")


@router.message(AddSupportTeacher.ielts)
async def add_support_ielts(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await support_prompt(message, '⚠️ IELTS ballni yuboring. Yo‘q bo‘lsa "-" yuboring.', "ielts")
        return
    await state.update_data(ielts=value)
    await state.set_state(AddSupportTeacher.cefr)
    await support_prompt(message, title("📖 CEFR", 'Darajani kiriting. Yo‘q bo‘lsa "-" yuboring.'), "cefr")


@router.message(AddSupportTeacher.cefr)
async def add_support_cefr(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value:
        await support_prompt(message, '⚠️ CEFR darajani yuboring. Yo‘q bo‘lsa "-" yuboring.', "cefr")
        return
    await state.update_data(cefr=value)
    await state.set_state(AddSupportTeacher.sat)
    await support_prompt(message, title("🧮 SAT", 'Ballni kiriting. Yo‘q bo‘lsa "-" yuboring.'), "sat")


@router.message(AddSupportTeacher.sat)
async def add_support_sat(message: Message, state: FSMContext, storage: Storage) -> None:
    value = (message.text or "").strip()
    if not value:
        await support_prompt(message, '⚠️ SAT ballni yuboring. Yo‘q bo‘lsa "-" yuboring.', "sat")
        return
    await state.update_data(sat=value, categories=[])
    await state.set_state(AddSupportTeacher.categories)
    if not storage.list_categories():
        await message.answer(
            "⚠️ Avval kamida bitta yo‘nalish yarating.",
            reply_markup=inline([[("➕ Yo‘nalish yaratish", "create_category")], [("❌ Bekor qilish", "admin:cancel")]]),
        )
        return
    await message.answer(title("🧭 Yo‘nalishlar", "Support Teacher ishlaydigan yo‘nalishlarni tanlang."), reply_markup=support_category_keyboard(storage, []))


@router.callback_query(AddSupportTeacher.categories, F.data.startswith("support_category:"))
async def toggle_support_category(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    data = await state.get_data()
    selected = set(data.get("categories", []))
    category_id = int(callback.data.split(":")[1])
    if category_id in selected:
        selected.remove(category_id)
    else:
        selected.add(category_id)
    categories = sorted(selected)
    await state.update_data(categories=categories)
    if callback.message:
        await callback.message.answer(title("🧭 Yo‘nalishlar", "Support Teacher ishlaydigan yo‘nalishlarni tanlang."), reply_markup=support_category_keyboard(storage, categories))


@router.callback_query(AddSupportTeacher.categories, F.data == "support_category_done")
async def finish_support_teacher(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    data = await state.get_data()
    if not data.get("categories"):
        if callback.message:
            await callback.message.answer("⚠️ Kamida bitta yo‘nalish tanlang.", reply_markup=support_category_keyboard(storage, []))
        return
    try:
        support = storage.create_support_teacher(data)
    except sqlite3.IntegrityError:
        if callback.message:
            await callback.message.answer("⚠️ Bu telefon raqam bilan Support Teacher allaqachon mavjud.", reply_markup=back_to_main_keyboard({"role": "admin"}))
        await state.clear()
        return
    await state.clear()
    if callback.message:
        await callback.message.answer(f"✅ Support Teacher qo‘shildi\n{support.name} {support.surname}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:students")
async def students(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await callback.message.answer(
        title("🎓 O‘quvchilar", "O‘quvchini tanlang: ban, unban yoki o‘chirish."),
        reply_markup=inline(managed_student_rows(storage)),
    )


@router.callback_query(F.data.startswith("admin:students_page:"))
async def students_page(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    page = int(callback.data.rsplit(":", 1)[1])
    await callback.message.answer(
        title("🎓 O‘quvchilar", "O‘quvchini tanlang: ban, unban yoki o‘chirish."),
        reply_markup=inline(managed_student_rows(storage, page)),
    )


@router.callback_query(F.data == "admin:student_search")
async def student_search_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await state.set_state(StudentSearch.query)
    await admin_prompt(
        callback.message,
        state,
        title("🔎 O‘quvchi qidirish", "Telefon raqam, ism yoki username kiriting."),
        "query",
    )


@router.message(StudentSearch.query)
async def student_search_result(message: Message, config: Config, state: FSMContext, storage: Storage) -> None:
    if not is_admin(message.from_user.id if message.from_user else None, config, storage):
        await state.clear()
        return
    query = (message.text or "").strip()
    if not query:
        await admin_prompt(message, state, "⚠️ Qidiruv so‘zini kiriting.", "query")
        return
    await state.update_data(query=query)
    results = storage.search_students(query)
    await message.answer(
        title("🔎 Qidiruv natijalari", f"“{query}” bo‘yicha {len(results)} ta o‘quvchi topildi."),
        reply_markup=inline(managed_student_rows(storage, students=results, prefix="admin:student_search_page")),
    )


@router.callback_query(F.data.startswith("admin:student_search_page:"))
async def student_search_page(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    data = await state.get_data()
    query = data.get("query", "")
    results = storage.search_students(query) if query else []
    page = int(callback.data.rsplit(":", 1)[1])
    await callback.message.answer(
        title("🔎 Qidiruv natijalari", f"“{query}” bo‘yicha {len(results)} ta o‘quvchi topildi."),
        reply_markup=inline(managed_student_rows(storage, page, results, "admin:student_search_page")),
    )


@router.callback_query(F.data.startswith("student_admin:open:"))
async def open_student(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    user = storage.get_user_by_phone(phone)
    if not user or user.role != "student":
        await callback.message.answer("⚠️ O‘quvchi topilmadi.", reply_markup=inline(managed_student_rows(storage)))
        return
    rows = [
        [("🚫 Ban berish", f"student_admin:ban:{user.phone}")],
    ]
    if user.banned_until:
        rows.append([("✅ Bandan chiqarish", f"student_admin:unban:{user.phone}")])
    rows.extend([
        [("🗑 O‘chirish", f"student_admin:delete:{user.phone}")],
        [("⬅️ O‘quvchilar", "admin:students")],
    ])
    await callback.message.answer(student_admin_text(storage, user.phone), reply_markup=inline(rows))


@router.callback_query(F.data.startswith("student_admin:ban:"))
async def ban_student_menu(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    user = storage.get_user_by_phone(phone)
    if not user or user.role != "student":
        await callback.message.answer("⚠️ O‘quvchi topilmadi.", reply_markup=inline(managed_student_rows(storage)))
        return
    await callback.message.answer(
        f"🚫 {user.name or user.phone} nechchi kunga ban qilinsin?",
        reply_markup=inline([
            [("7 kun", f"student_admin:ban_days:{user.phone}:7"), ("14 kun", f"student_admin:ban_days:{user.phone}:14")],
            [("30 kun", f"student_admin:ban_days:{user.phone}:30")],
            [("⬅️ Bekor qilish", f"student_admin:open:{user.phone}")],
        ]),
    )


@router.callback_query(F.data.startswith("student_admin:ban_days:"))
async def ban_student_finish(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    _, _, _, phone, days = callback.data.split(":")
    user = storage.ban_student(phone, int(days))
    if not user:
        await callback.message.answer("⚠️ O‘quvchi topilmadi.", reply_markup=inline(managed_student_rows(storage)))
        return
    if user.chat_id:
        try:
            text = (
                f"🚫 Вы заблокированы на {days} дней.\nБлокировка закончится: {user.banned_until[:10]}"
                if user.language == "ru"
                else f"🚫 Siz {days} kunga ban qilindingiz.\nBan tugaydi: {user.banned_until[:10]}"
            )
            await callback.bot.send_message(user.chat_id, text)
        except Exception:
            pass
    await callback.message.answer(f"✅ O‘quvchi {days} kunga ban qilindi.", reply_markup=inline([[("⬅️ Profilga qaytish", f"student_admin:open:{user.phone}")]]))


@router.callback_query(F.data.startswith("student_admin:unban:"))
async def unban_student(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    user = storage.unban_student(phone)
    if not user:
        await callback.message.answer("⚠️ O‘quvchi topilmadi.", reply_markup=inline(managed_student_rows(storage)))
        return
    if user.chat_id:
        try:
            await callback.bot.send_message(
                user.chat_id,
                "✅ Вы разблокированы." if user.language == "ru" else "✅ Siz bandan chiqarildingiz.",
            )
        except Exception:
            pass
    await callback.message.answer("✅ O‘quvchi bandan chiqarildi.", reply_markup=inline([[("⬅️ Profilga qaytish", f"student_admin:open:{user.phone}")]]))


@router.callback_query(F.data.startswith("student_admin:delete:"))
async def delete_student_confirm(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    stats_data = storage.student_stats(phone)
    if not stats_data:
        await callback.message.answer("⚠️ O‘quvchi topilmadi.", reply_markup=inline(managed_student_rows(storage)))
        return
    user = stats_data["user"]
    await callback.message.answer(
        "\n".join([
            f"🗑 {user.name or user.phone} o‘chirilsinmi?",
            f"Aktiv darslar: {stats_data['booked']}",
            "Aktiv dars bo‘lsa o‘chirish bajarilmaydi.",
        ]),
        reply_markup=inline([
            [("✅ Ha, o‘chirish", f"student_admin:delete_confirm:{user.phone}")],
            [("⬅️ Bekor qilish", f"student_admin:open:{user.phone}")],
        ]),
    )


@router.callback_query(F.data.startswith("student_admin:delete_confirm:"))
async def delete_student_finish(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    phone = callback.data.split(":")[2]
    deleted = storage.delete_student(phone)
    if not deleted:
        await callback.message.answer("⚠️ O‘chirilmadi. O‘quvchi topilmadi yoki aktiv darslari bor.", reply_markup=inline(managed_student_rows(storage)))
        return
    await callback.message.answer("✅ O‘quvchi o‘chirildi.", reply_markup=inline(managed_student_rows(storage)))


@router.callback_query(F.data == "admin:supports")
async def support_teachers(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await callback.message.answer(
        title("🧑‍🏫 Support Teacherlar", "Tanlang: statistika, tahrirlash yoki o‘chirish."),
        reply_markup=inline(managed_support_rows(storage)),
    )


@router.callback_query(F.data.startswith("admin:supports_page:"))
async def support_teachers_page(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    page = int(callback.data.rsplit(":", 1)[1])
    await callback.message.answer(
        title("🧑‍🏫 Support Teacherlar", "Tanlang: statistika, tahrirlash yoki o‘chirish."),
        reply_markup=inline(managed_support_rows(storage, page)),
    )


@router.callback_query(F.data.startswith("support_admin:open:"))
async def open_support_teacher(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    support_id = int(callback.data.split(":")[2])
    if not storage.get_support_teacher(support_id):
        await callback.message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
        return
    await callback.message.answer(
        support_admin_text(storage, support_id),
        reply_markup=inline([
            [("✏️ Tahrirlash", f"support_admin:edit:{support_id}")],
            [("🗑 O‘chirish", f"support_admin:delete:{support_id}")],
            [("⬅️ Support Teacherlar", "admin:supports")],
        ]),
    )


@router.callback_query(F.data.startswith("support_admin:edit:"))
async def edit_support_teacher_menu(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    support_id = int(callback.data.split(":")[2])
    support = storage.get_support_teacher(support_id)
    if not support:
        await callback.message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
        return
    await callback.message.answer(
        f"✏️ {support.name} {support.surname}\nQaysi ma’lumot o‘zgartiriladi?",
        reply_markup=inline([
            [("📱 Telefon", f"support_admin:edit_field:{support.id}:phone")],
            [("👤 Ism", f"support_admin:edit_field:{support.id}:name"), ("👤 Familiya", f"support_admin:edit_field:{support.id}:surname")],
            [("🎧 IELTS", f"support_admin:edit_field:{support.id}:ielts"), ("📖 CEFR", f"support_admin:edit_field:{support.id}:cefr")],
            [("🧮 SAT", f"support_admin:edit_field:{support.id}:sat")],
            [("🧭 Yo‘nalishlar", f"support_admin:edit_categories:{support.id}")],
            [("⬅️ Orqaga", f"support_admin:open:{support.id}")],
        ]),
    )


@router.callback_query(F.data.startswith("support_admin:edit_field:"))
async def edit_support_teacher_field_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    _, _, support_id, field = callback.data.split(":")
    support = storage.get_support_teacher(int(support_id))
    if not support:
        await callback.message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
        return
    labels = {
        "phone": "telefon raqam",
        "name": "ism",
        "surname": "familiya",
        "ielts": "IELTS ball",
        "cefr": "CEFR daraja",
        "sat": "SAT ball",
    }
    await state.set_state(EditSupportTeacher.value)
    await state.update_data(support_id=support.id, field=field)
    await admin_prompt(callback.message, state, title("✏️ Support Teacher", f"Yangi {labels.get(field, field)} kiriting."), "value")


@router.message(EditSupportTeacher.value)
async def edit_support_teacher_field_finish(message: Message, state: FSMContext, storage: Storage) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Yangi qiymatni matn ko‘rinishida yuboring.", "value")
    if not value:
        return
    data = await state.get_data()
    support_id = int(data["support_id"])
    field = data["field"]
    try:
        support = storage.update_support_teacher(support_id, **{field: value})
    except sqlite3.IntegrityError:
        await state.clear()
        await message.answer("⚠️ Bu telefon raqam boshqa Support Teacherda bor.", reply_markup=inline(managed_support_rows(storage)))
        return
    await state.clear()
    if not support:
        await message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
        return
    await message.answer(f"✅ Yangilandi: {support.name} {support.surname}", reply_markup=inline([[("⬅️ Profilga qaytish", f"support_admin:open:{support.id}")]]))


def support_edit_category_keyboard(storage: Storage, support_id: int, selected_ids: list[int]):
    selected = {int(category_id) for category_id in selected_ids}
    rows = category_button_rows(
        storage.list_categories(),
        lambda category: f"support_edit_category:{category.id}",
        lambda category: f"{'[x]' if category.id in selected else '[ ]'} {category.name}",
    )
    rows.append([("✅ Saqlash", "support_edit_category_done")])
    rows.append([("⬅️ Orqaga", f"support_admin:edit:{support_id}")])
    return inline(rows)


@router.callback_query(F.data.startswith("support_admin:edit_categories:"))
async def edit_support_categories_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    support_id = int(callback.data.split(":")[2])
    support = storage.get_support_teacher(support_id)
    if not support:
        await callback.message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
        return
    await state.set_state(EditSupportTeacher.categories)
    await state.update_data(support_id=support.id, categories=support.categories)
    await callback.message.answer(
        title("🧭 Yo‘nalishlar", "Support Teacher ishlaydigan yo‘nalishlarni tanlang."),
        reply_markup=support_edit_category_keyboard(storage, support.id, support.categories),
    )


@router.callback_query(EditSupportTeacher.categories, F.data.startswith("support_edit_category:"))
async def edit_support_category_toggle(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    data = await state.get_data()
    selected = set(data.get("categories", []))
    category_id = int(callback.data.split(":")[1])
    if category_id in selected:
        selected.remove(category_id)
    else:
        selected.add(category_id)
    categories = sorted(selected)
    await state.update_data(categories=categories)
    if callback.message:
        await callback.message.answer(
            title("🧭 Yo‘nalishlar", "Support Teacher ishlaydigan yo‘nalishlarni tanlang."),
            reply_markup=support_edit_category_keyboard(storage, int(data["support_id"]), categories),
        )


@router.callback_query(EditSupportTeacher.categories, F.data == "support_edit_category_done")
async def edit_support_categories_finish(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    data = await state.get_data()
    support_id = int(data["support_id"])
    categories = data.get("categories", [])
    if not categories:
        if callback.message:
            await callback.message.answer("⚠️ Kamida bitta yo‘nalish tanlang.", reply_markup=support_edit_category_keyboard(storage, support_id, []))
        return
    support = storage.update_support_teacher(support_id, categories=categories)
    await state.clear()
    if callback.message:
        if not support:
            await callback.message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
            return
        await callback.message.answer("✅ Yo‘nalishlar yangilandi.", reply_markup=inline([[("⬅️ Profilga qaytish", f"support_admin:open:{support.id}")]]))


@router.callback_query(F.data.startswith("support_admin:delete:"))
async def delete_support_teacher_confirm(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    support_id = int(callback.data.split(":")[2])
    support = storage.get_support_teacher(support_id)
    if not support:
        await callback.message.answer("⚠️ Support Teacher topilmadi.", reply_markup=inline(managed_support_rows(storage)))
        return
    stats_data = storage.support_teacher_stats(support.id)
    active = stats_data["booked"] if stats_data else 0
    await callback.message.answer(
        "\n".join([
            f"🗑 {support.name} {support.surname} o‘chirilsinmi?",
            f"Aktiv darslar: {active}",
            "Aktiv dars bo‘lsa o‘chirish bajarilmaydi.",
        ]),
        reply_markup=inline([
            [("✅ Ha, o‘chirish", f"support_admin:delete_confirm:{support.id}")],
            [("⬅️ Bekor qilish", f"support_admin:open:{support.id}")],
        ]),
    )


@router.callback_query(F.data.startswith("support_admin:delete_confirm:"))
async def delete_support_teacher_finish(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    support_id = int(callback.data.split(":")[2])
    deleted = storage.delete_support_teacher(support_id)
    if not deleted:
        await callback.message.answer("⚠️ O‘chirilmadi. Support Teacher topilmadi yoki aktiv darslari bor.", reply_markup=inline(managed_support_rows(storage)))
        return
    await callback.message.answer("✅ Support Teacher o‘chirildi.", reply_markup=inline(managed_support_rows(storage)))


@router.callback_query(F.data == "admin:categories")
async def categories(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not is_admin(callback.from_user.id, config, storage):
        return
    if callback.message:
        await callback.message.answer(title("🧭 Yo‘nalishlar", "Support yo‘nalishlarini boshqaring."), reply_markup=inline(category_admin_rows(storage)))


@router.callback_query(F.data.startswith("category:open:"))
async def open_category(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return

    category_id = int(callback.data.split(":")[2])
    category = storage.get_category(category_id)
    if not category or not category.active:
        await callback.message.answer("⚠️ Yo‘nalish topilmadi.", reply_markup=inline(category_admin_rows(storage)))
        return

    attached = len(storage.list_support_teachers(category.id))
    await callback.message.answer(
        "\n".join([
            category.name,
            f"🧑‍🏫 Biriktirilgan Support Teacherlar: {attached}",
        ]),
        reply_markup=inline([
            [("✏️ Nomini o‘zgartirish", f"category:edit:{category.id}")],
            [("🗑 O‘chirish", f"category:delete:{category.id}")],
            [("⬅️ Yo‘nalishlar", "admin:categories")],
        ]),
    )


@router.callback_query(F.data.startswith("category:edit:"))
async def edit_category_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return

    category_id = int(callback.data.split(":")[2])
    category = storage.get_category(category_id)
    if not category or not category.active:
        await callback.message.answer("⚠️ Yo‘nalish topilmadi.", reply_markup=inline(category_admin_rows(storage)))
        return

    await state.set_state(EditCategory.name)
    await state.update_data(category_id=category.id)
    await admin_prompt(callback.message, state, title("✏️ Yo‘nalish nomi", f"Yangi nomni kiriting.\nHozirgi nom: {category.name}"), "name")


@router.message(EditCategory.name)
async def edit_category_name(message: Message, state: FSMContext, storage: Storage) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Yangi nomni matn ko‘rinishida yuboring.", "name")
    if not value:
        return

    data = await state.get_data()
    category = storage.update_category(int(data["category_id"]), value)
    await state.clear()
    if not category:
        await message.answer("⚠️ Yo‘nalish topilmadi.", reply_markup=back_to_main_keyboard({"role": "admin"}))
        return
    await message.answer(f"✅ Yo‘nalish yangilandi: {category.name}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data.startswith("category:delete:"))
async def delete_category_confirm(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return

    category_id = int(callback.data.split(":")[2])
    category = storage.get_category(category_id)
    if not category or not category.active:
        await callback.message.answer("⚠️ Yo‘nalish topilmadi.", reply_markup=inline(category_admin_rows(storage)))
        return

    attached = len(storage.list_support_teachers(category.id))
    await callback.message.answer(
        "\n".join([
            f"🗑 {category.name} o‘chirilsinmi?",
            f"Bu yo‘nalish {attached} ta Support Teacherdan olib tashlanadi.",
        ]),
        reply_markup=inline([
            [("✅ Ha, o‘chirish", f"category:delete_confirm:{category.id}")],
            [("⬅️ Bekor qilish", f"category:open:{category.id}")],
        ]),
    )


@router.callback_query(F.data.startswith("category:delete_confirm:"))
async def delete_category_finish(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return

    category_id = int(callback.data.split(":")[2])
    deleted = storage.delete_category(category_id)
    if not deleted:
        await callback.message.answer("⚠️ Yo‘nalish topilmadi.", reply_markup=inline(category_admin_rows(storage)))
        return
    await callback.message.answer("✅ Yo‘nalish o‘chirildi.", reply_markup=inline(category_admin_rows(storage)))


@router.callback_query(F.data == "create_category")
async def create_category_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    await state.set_state(CreateCategory.name)
    if callback.message:
        await admin_prompt(callback.message, state, title("🧭 Yo‘nalish", "Yo‘nalish nomini kiriting."), "name")


@router.message(CreateCategory.name)
async def create_category_name(message: Message, state: FSMContext, storage: Storage) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Yo‘nalish nomini matn ko‘rinishida yuboring.", "name")
    if not value:
        return
    category = storage.create_category(value)
    await state.clear()
    await message.answer(f"✅ Yo‘nalish yaratildi: {category.name}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:sending")
async def sending(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not is_admin(callback.from_user.id, config, storage):
        return
    if callback.message:
        await callback.message.answer(title("📣 Xabar yuborish", "Kimlarga yuboriladi?"), reply_markup=inline([
            [("🎓 O‘quvchilar", "broadcast:student")],
            [("🧑‍🏫 Support Teacherlar", "broadcast:support_teacher")],
            [("🏠 Admin menyu", "admin:menu")],
        ]))


@router.callback_query(F.data.startswith("broadcast:"))
async def broadcast_start(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    role = callback.data.split(":")[1]
    await state.set_state(Broadcast.message)
    await state.update_data(role=role)
    if callback.message:
        await admin_prompt(callback.message, state, title("📣 Xabar", "Yuboriladigan xabarni tashlang. Bot uni copy qiladi."), "message")


@router.message(Broadcast.message)
async def broadcast_message(message: Message, state: FSMContext, storage: Storage) -> None:
    await delete_previous_prompt(message, state)
    data = await state.get_data()
    users = [user for user in storage.list_users(data["role"]) if user.chat_id]
    sent = 0
    for user in users:
        try:
            await message.bot.copy_message(user.chat_id, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            pass
    await state.clear()
    await message.answer(f"✅ Xabar {sent}/{len(users)} foydalanuvchiga yuborildi.", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:stats")
async def stats(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not is_admin(callback.from_user.id, config, storage):
        return
    stats_data = storage.stats()
    if callback.message:
        await callback.message.answer(
            "\n".join([
                "📊 Statistika",
                f"👥 Foydalanuvchilar: {stats_data['users']}",
                f"🎓 O‘quvchilar: {stats_data['students']}",
                f"🧑‍🏫 Support Teacherlar: {stats_data['support_teachers']}",
                f"🧭 Yo‘nalishlar: {stats_data['categories']}",
                f"📚 Aktiv darslar: {stats_data['booked']}",
                f"✅ Yakunlangan: {stats_data['completed']}",
                f"👤 Kelmaganlar: {stats_data['no_shows']}",
                f"🚫 Ban: {stats_data['banned']}",
                f"⭐ Feedback: {stats_data['feedback']}",
            ]),
            reply_markup=inline([
                [("📚 Barcha aktiv darslar", "admin:active_lessons")],
                [("🧑‍🏫 Support Teacher statistikasi", "admin:supports")],
                [("🏠 Admin menyu", "admin:menu")],
            ]),
        )
