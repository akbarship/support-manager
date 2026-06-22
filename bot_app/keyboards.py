from __future__ import annotations

from datetime import datetime
from typing import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot_app.database import Category, Storage, SupportTeacher, User, local_now, working_hours
from bot_app.texts import ROLE_LABELS, t


def language_keyboard() -> InlineKeyboardMarkup:
    return inline([
        [("🇺🇿 O‘zbekcha", "lang:uz"), ("🇷🇺 Русский", "lang:ru")],
    ])


def contact_keyboard(language: str = "uz") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"📱 {t('share_contact_button', language)}", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def inline(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data) for text, callback_data in row]
            for row in rows
        ]
    )


def category_button_rows(
    categories: list[Category],
    callback_data: Callable[[Category], str],
    label: Callable[[Category], str] | None = None,
) -> list[list[tuple[str, str]]]:
    if not categories:
        return []

    label = label or (lambda category: category.name)
    longest_category = max(categories, key=lambda category: len(category.name))
    rows: list[list[tuple[str, str]]] = []
    current_row: list[tuple[str, str]] = []

    for category in categories:
        button = (label(category), callback_data(category))
        if category.id == longest_category.id:
            if current_row:
                rows.append(current_row)
                current_row = []
            rows.append([button])
            continue

        current_row.append(button)
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    return rows


def admin_keyboard(show_destructive_actions: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [("🧑‍🏫 Support Teacherlar", "admin:supports")],
        [("🎓 O‘quvchilar", "admin:students")],
        [("📚 Aktiv darslar", "admin:active_lessons")],
        [("👑 Adminlar", "admin:admins"), ("🧭 Yo‘nalishlar", "admin:categories")],
        [("📣 Xabar yuborish", "admin:sending")],
        [("📊 Statistika", "admin:stats")],
    ]
    if show_destructive_actions:
        rows.extend([
            [("☀️ Yakshanba darslarini bekor qilish", "admin:reset_sunday_lessons")],
            [("🧹 Barcha darslarni bekor qilish", "admin:reset_lessons")],
        ])
    return inline(rows)


def support_keyboard() -> InlineKeyboardMarkup:
    return inline([
        [("🗓 Jadvalim", "support:schedule")],
        [("📚 Band qilingan darslar", "support:bookings")],
        [("🏆 Natijalarim", "support:stats")],
    ])


def learner_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return inline([
        [(f"🧑‍🏫 {t('support_teachers', language)}", "show_categories")],
        [(f"📚 {t('my_lessons', language)}", "learner:bookings")],
    ])


def main_keyboard(
    user: User,
    is_admin: bool = False,
    show_destructive_actions: bool = False,
) -> InlineKeyboardMarkup:
    if is_admin or user.role == "admin":
        return admin_keyboard(show_destructive_actions)
    if user.role == "support_teacher":
        return support_keyboard()
    return learner_keyboard(user.language)


def back_to_main_keyboard(user: User | dict[str, str]) -> InlineKeyboardMarkup:
    role = user.role if isinstance(user, User) else user.get("role", "")
    language = user.language if isinstance(user, User) else user.get("language", "uz")
    return inline([[(f"🏠 {t('main_menu_button', language)}", "admin:menu" if role == "admin" else "main:menu")]])


def admin_flow_keyboard(step: str | None = None) -> InlineKeyboardMarkup:
    row = []
    if step and step != "phone":
        row.append(("⬅️ Orqaga", "admin:back"))
    row.append(("❌ Bekor qilish", "admin:cancel"))
    return inline([row])


def support_category_keyboard(storage: Storage, selected_ids: list[int]) -> InlineKeyboardMarkup:
    selected = {int(category_id) for category_id in selected_ids}
    rows = category_button_rows(
        storage.list_categories(),
        lambda category: f"support_category:{category.id}",
        lambda category: f"{'[x]' if category.id in selected else '[ ]'} {category.name}",
    )
    rows.append([("✅ Tayyor", "support_category_done")])
    rows.append([("⬅️ Orqaga", "admin:back"), ("❌ Bekor qilish", "admin:cancel")])
    return inline(rows)


def category_keyboard(storage: Storage, language: str = "uz") -> InlineKeyboardMarkup:
    rows = category_button_rows(storage.list_categories(), lambda category: f"cat:{category.id}")
    rows.append([(f"🏠 {t('main_menu_button', language)}", "main:menu")])
    return inline(rows)


def support_info(storage: Storage, support: SupportTeacher, category_id: int | None = None, language: str = "uz") -> str:
    rating = f"{support.rating}/5 ({support.rating_count})"
    selected_category = storage.get_category(category_id) if category_id else None
    categories = ", ".join(
        category_item.name
        for category_id_item in support.categories
        if (category_item := storage.get_category(category_id_item))
    )
    achievements = [
        (label, value)
        for label, value in [
            ("🎧 IELTS", support.ielts),
            ("📖 CEFR", support.cefr),
            ("🧮 SAT", support.sat),
        ]
        if value and value.strip() != "-"
    ]
    return "\n".join([
        f"🧑‍🏫 {support.name} {support.surname}",
        *[f"{label}: {value}" for label, value in achievements],
        f"⭐ {'Рейтинг' if language == 'ru' else 'Reyting'}: {rating}",
        f"🧭 {'Направление' if language == 'ru' else 'Yo‘nalish'}: {selected_category.name if selected_category else categories or '-'}",
        f"✅ {'Проведено уроков' if language == 'ru' else 'O‘tilgan darslar'}: {support.conducted_lessons}",
    ])


def support_browser_keyboard(category_id: int, index: int, count: int, support_id: int, language: str = "uz") -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    nav = []
    if index > 0:
        nav.append((f"⬅️ {t('previous', language)}", f"browse:{category_id}:{index - 1}"))
    if index < count - 1:
        nav.append((f"➡️ {t('next', language)}", f"browse:{category_id}:{index + 1}"))
    if nav:
        rows.append(nav)
    rows.extend([
        [(f"✅ {t('select', language)}", f"choose_support:{category_id}:{support_id}:{index}")],
        [(f"⬅️ {t('back_to_categories', language)}", "show_categories")],
    ])
    return inline(rows)


def date_keyboard(today, support_id: int, category_id: int, support_index: int = 0, language: str = "uz") -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    offset = 0
    while len(rows) < 3:
        date = today(offset)
        if datetime.fromisoformat(date).weekday() != 6:
            prefix = f"{t('today', language)} " if offset == 0 else f"{t('tomorrow', language)} " if offset == 1 else ""
            rows.append([
                (
                    f"📅 {prefix}{date}",
                    f"date:{category_id}:{support_id}:{support_index}:{date}",
                )
            ])
        offset += 1
    rows.append([(f"⬅️ {t('back_to_supports', language)}", f"browse:{category_id}:{support_index}")])
    return inline(rows)


def slots_keyboard(storage: Storage, category_id: int, support_id: int, support_index: int, date: str, user: User, hours_until, start_at) -> InlineKeyboardMarkup:
    slots = []
    for hour in storage.get_open_slots(support_id, date):
        if start_at(date, hour) <= local_now():
            continue
        slots.append(hour)
    rows = [[(f"🕘 {hour}:00", f"slot:{category_id}:{support_id}:{support_index}:{date}:{hour}")] for hour in slots]
    if not rows:
        rows = [
            [(f"📭 {t('no_free_time', user.language)}", "noop")],
            [(f"🧑‍🏫 {t('choose_other_support', user.language)}", f"browse:{category_id}:0")],
        ]
    rows.extend([
        [(f"⬅️ {t('choose_other_date', user.language)}", f"choose_support:{category_id}:{support_id}:{support_index}")],
    ])
    return inline(rows)


def duration_keyboard(category_id: int, support_id: int, support_index: int, date: str, hour: int, language: str = "uz") -> InlineKeyboardMarkup:
    rows = [[(f"✅ {t('continue_one_hour', language)}", f"book:{category_id}:{support_id}:{support_index}:{date}:{hour}:1")]]
    rows.append([(f"⬅️ {t('back_to_slots', language)}", f"date:{category_id}:{support_id}:{support_index}:{date}")])
    return inline(rows)


def schedule_template_keyboard() -> InlineKeyboardMarkup:
    return inline([
        [("1️⃣ Toq kunlar", "schedule_template:odd")],
        [("2️⃣ Juft kunlar", "schedule_template:even")],
        [("🏠 Asosiy menyu", "main:menu")],
    ])


def schedule_template_edit_keyboard(storage: Storage, support_id: int, template_key: str) -> InlineKeyboardMarkup:
    open_slots = set(storage.get_template_open_slots(support_id, template_key))
    rows = [
        [(f"{'🟢 Ochiq' if hour in open_slots else '🔴 Yopiq'} {hour}:00", f"toggle_template_slot:{template_key}:{hour}")]
        for hour in working_hours()
    ]
    rows.append([("⬅️ Shablon tanlash", "support:schedule")])
    return inline(rows)


def schedule_edit_keyboard(storage: Storage, support_id: int, date: str) -> InlineKeyboardMarkup:
    open_slots = set(storage.get_open_slots(support_id, date))
    rows = [
        [(f"{'🟢 Ochiq' if hour in open_slots else '🔴 Yopiq'} {hour}:00", f"toggle_slot:{date}:{hour}")]
        for hour in working_hours()
    ]
    rows.append([("⬅️ Jadvalga qaytish", "support:schedule")])
    return inline(rows)


def booking_actions_keyboard(booking_id: int, is_last: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [("🚫 Bekor qilish", f"support_cancel:{booking_id}")],
        [("👤 O‘quvchi kelmadi", f"no_show:{booking_id}")],
        [("✅ Yakunlandi", f"complete:{booking_id}")],
    ]
    if is_last:
        rows.append([("🏠 Asosiy menyu", "main:menu")])
    return inline(rows)


def learner_booking_actions_keyboard(booking_id: int, user: User, is_last: bool = False) -> InlineKeyboardMarkup:
    rows = [[("🚫 Darsni bekor qilish", f"learner_cancel:{booking_id}")]]
    if is_last:
        rows.append([("🏠 Asosiy menyu", "main:menu")])
    return inline(rows)


def rating_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return inline([[(str(rating), f"rate:{booking_id}:{rating}") for rating in range(1, 6)]])


ROLE_OPTIONS = ROLE_LABELS
