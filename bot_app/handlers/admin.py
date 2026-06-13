from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot_app.config import Config
from bot_app.database import Storage
from bot_app.keyboards import (
    admin_flow_keyboard,
    admin_keyboard,
    back_to_main_keyboard,
    inline,
    support_category_keyboard,
)
from bot_app.states import AddSupportTeacher, AddUser, Broadcast, CreateCategory
from bot_app.texts import ROLE_LABELS, title

router = Router()


def is_admin(user_id: int | None, config: Config) -> bool:
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


@router.message(Command("admin"))
async def admin_panel(message: Message, config: Config, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None, config):
        await message.answer("🚫 Admin panelga ruxsat yo‘q.")
        return
    await state.clear()
    await message.answer("👑 Admin panel", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin:menu")
async def admin_menu(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config):
        await callback.message.answer("👑 Admin panel", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config):
        await callback.message.answer("❌ Amal bekor qilindi.", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config):
        await callback.message.answer("👑 Admin panel", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin:add_teacher")
async def start_add_user(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config):
        return
    role = "teacher"
    await state.set_state(AddUser.phone)
    await state.update_data(role=role)
    await admin_prompt(callback.message, state, title("📱 Telefon raqam", f"{ROLE_LABELS[role]} telefon raqamini kiriting."), "phone")


@router.message(AddUser.phone)
async def add_user_phone(message: Message, state: FSMContext) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Telefon raqamni matn ko‘rinishida yuboring.", "phone")
    if not value:
        return
    await state.update_data(phone=value)
    await state.set_state(AddUser.name)
    await admin_prompt(message, state, title("👤 Ism", "Ismini kiriting."), "name")


@router.message(AddUser.name)
async def add_user_name(message: Message, state: FSMContext) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Ismni matn ko‘rinishida yuboring.", "name")
    if not value:
        return
    await state.update_data(name=value)
    await state.set_state(AddUser.surname)
    await admin_prompt(message, state, title("👤 Familiya", "Familiyasini kiriting."), "surname")


@router.message(AddUser.surname)
async def add_user_surname(message: Message, state: FSMContext, storage: Storage) -> None:
    await delete_previous_prompt(message, state)
    value = await require_text(message, state, "⚠️ Familiyani matn ko‘rinishida yuboring.", "surname")
    if not value:
        return
    data = await state.get_data()
    user = storage.upsert_allowed_user(data["phone"], data["role"], data["name"], value)
    await state.clear()
    await message.answer(f"✅ {ROLE_LABELS[user.role]} qo‘shildi\n👤 {user.name} {user.surname}\n📱 {user.phone}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:add_support")
async def start_add_support(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config):
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
        await callback.message.answer(f"✅ Support Teacher qo‘shildi\n#{support.id} {support.name} {support.surname}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:categories")
async def categories(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not is_admin(callback.from_user.id, config):
        return
    if callback.message:
        rows = [[("➕ Yo‘nalish yaratish", "create_category")]]
        rows.extend([[(f"📘 {category.name}", "noop")] for category in storage.list_categories()])
        rows.append([("🏠 Admin menyu", "admin:menu")])
        await callback.message.answer(title("🧭 Yo‘nalishlar", "Support yo‘nalishlarini boshqaring."), reply_markup=inline(rows))


@router.callback_query(F.data == "create_category")
async def create_category_start(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config):
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
    await message.answer(f"✅ Yo‘nalish yaratildi: #{category.id} {category.name}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:sending")
async def sending(callback: CallbackQuery, config: Config) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not is_admin(callback.from_user.id, config):
        return
    if callback.message:
        await callback.message.answer(title("📣 Xabar yuborish", "Kimlarga yuboriladi?"), reply_markup=inline([
            [("🎓 O‘quvchilar", "broadcast:student")],
            [("👩‍🏫 Teacherlar", "broadcast:teacher")],
            [("🧑‍🏫 Support Teacherlar", "broadcast:support_teacher")],
            [("🏠 Admin menyu", "admin:menu")],
        ]))


@router.callback_query(F.data.startswith("broadcast:"))
async def broadcast_start(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config):
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
    if not is_admin(callback.from_user.id, config):
        return
    stats_data = storage.stats()
    if callback.message:
        await callback.message.answer(
            "\n".join([
                "📊 Statistika",
                f"👥 Foydalanuvchilar: {stats_data['users']}",
                f"🎓 O‘quvchilar: {stats_data['students']}",
                f"👩‍🏫 Teacherlar: {stats_data['teachers']}",
                f"🧑‍🏫 Support Teacherlar: {stats_data['support_teachers']}",
                f"🧭 Yo‘nalishlar: {stats_data['categories']}",
                f"📚 Aktiv darslar: {stats_data['booked']}",
                f"✅ Yakunlangan: {stats_data['completed']}",
                f"👤 Kelmaganlar: {stats_data['no_shows']}",
                f"🚫 Ban: {stats_data['banned']}",
                f"⭐ Feedback: {stats_data['feedback']}",
            ]),
            reply_markup=back_to_main_keyboard({"role": "admin"}),
        )
