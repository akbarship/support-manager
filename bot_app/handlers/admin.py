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
    category_button_rows,
    inline,
    support_category_keyboard,
)
from bot_app.states import AddAdmin, AddSupportTeacher, AddUser, Broadcast, CreateCategory, EditCategory
from bot_app.texts import ROLE_LABELS, title

router = Router()


def is_admin(user_id: int | None, config: Config, storage: Storage | None = None) -> bool:
    return bool(user_id and (user_id in config.admin_ids or (storage and storage.is_admin_telegram_id(user_id))))


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


@router.message(Command("admin"))
async def admin_panel(message: Message, config: Config, state: FSMContext, storage: Storage) -> None:
    if not is_admin(message.from_user.id if message.from_user else None, config, storage):
        await message.answer("🚫 Admin panelga ruxsat yo‘q.")
        return
    await state.clear()
    await message.answer("👑 Admin panel", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin:menu")
async def admin_menu(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await state.clear()
    await delete_callback_message(callback)
    if callback.message and is_admin(callback.from_user.id, config, storage):
        await callback.message.answer("👑 Admin panel", reply_markup=admin_keyboard())


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
        await callback.message.answer("👑 Admin panel", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin:add_teacher")
async def start_add_user(callback: CallbackQuery, config: Config, state: FSMContext, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not callback.message or not is_admin(callback.from_user.id, config, storage):
        return
    role = "teacher"
    await state.set_state(AddUser.phone)
    await state.update_data(role=role)
    await admin_prompt(callback.message, state, title("📱 Telefon raqam", f"{ROLE_LABELS[role]} telefon raqamini kiriting."), "phone")


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
        await callback.message.answer(f"✅ Support Teacher qo‘shildi\n#{support.id} {support.name} {support.surname}", reply_markup=back_to_main_keyboard({"role": "admin"}))


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
            f"#{category.id} {category.name}",
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
    await message.answer(f"✅ Yo‘nalish yangilandi: #{category.id} {category.name}", reply_markup=back_to_main_keyboard({"role": "admin"}))


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
            f"🗑 #{category.id} {category.name} o‘chirilsinmi?",
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
    await message.answer(f"✅ Yo‘nalish yaratildi: #{category.id} {category.name}", reply_markup=back_to_main_keyboard({"role": "admin"}))


@router.callback_query(F.data == "admin:sending")
async def sending(callback: CallbackQuery, config: Config, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if not is_admin(callback.from_user.id, config, storage):
        return
    if callback.message:
        await callback.message.answer(title("📣 Xabar yuborish", "Kimlarga yuboriladi?"), reply_markup=inline([
            [("🎓 O‘quvchilar", "broadcast:student")],
            [("👩‍🏫 Teacherlar", "broadcast:teacher")],
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
