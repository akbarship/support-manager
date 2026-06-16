from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot_app.database import Storage
from bot_app.keyboards import contact_keyboard, language_keyboard, main_keyboard
from bot_app.states import Onboarding
from bot_app.texts import ROLE_LABELS, t

router = Router()


async def delete_callback_message(callback: CallbackQuery) -> None:
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass


async def show_main_menu(message: Message, storage: Storage, telegram_id: int | None) -> None:
    user = storage.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer(t("choose_language", "uz"), reply_markup=language_keyboard())
        return
    await message.answer(f"🏠 {t('main_menu', user.language)}", reply_markup=main_keyboard(user, storage.is_admin_telegram_id(telegram_id)))


async def finish_onboarding(message: Message, storage: Storage, state: FSMContext, phone: str, language: str) -> None:
    if not message.from_user:
        return
    user = storage.link_telegram_user(
        phone=phone,
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        telegram_data={
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "username": message.from_user.username,
        },
        language=language,
    )
    if not user:
        await message.answer(t("not_allowed", language), reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return
    await state.clear()
    await message.answer("✅ Telefon raqam saqlandi.", reply_markup=ReplyKeyboardRemove())
    await message.answer(f"{t('onboarded', user.language)} {ROLE_LABELS[user.role]}", reply_markup=main_keyboard(user))


@router.message(CommandStart())
async def start(message: Message, storage: Storage, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(message, storage, message.from_user.id if message.from_user else None)


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    language = callback.data.split(":")[1]
    await state.set_state(Onboarding.contact)
    await state.update_data(language=language)
    if callback.message:
        await callback.message.answer(t("share_contact", language), reply_markup=contact_keyboard(language))


@router.message(F.contact)
async def handle_contact(message: Message, storage: Storage, state: FSMContext) -> None:
    if not message.from_user or not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("📱 Iltimos, o‘zingizning kontaktingizni yuboring.")
        return
    data = await state.get_data()
    language = data.get("language", "uz")
    await finish_onboarding(message, storage, state, message.contact.phone_number, language)


@router.message(Onboarding.contact, F.text)
async def handle_phone_text(message: Message, storage: Storage, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not phone:
        return
    data = await state.get_data()
    language = data.get("language", "uz")
    await finish_onboarding(message, storage, state, phone, language)


@router.callback_query(F.data == "main:menu")
async def main_menu_callback(callback: CallbackQuery, storage: Storage) -> None:
    await callback.answer()
    await delete_callback_message(callback)
    if callback.message:
        await show_main_menu(callback.message, storage, callback.from_user.id)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
