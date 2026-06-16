ROLE_LABELS = {
    "admin": "👑 Admin",
    "support_teacher": "🧑‍🏫 Support Teacher",
    "student": "🎓 O‘quvchi",
}

TEXT = {
    "uz": {
        "choose_language": "Tilni tanlang:",
        "main_menu": "Nima qilamiz?",
        "share_contact": "Davom etish uchun telefon raqamingizni yuboring yoki raqamni yozing.",
        "share_contact_button": "Telefon raqamni yuborish",
        "not_allowed": "Bu telefon raqam ro‘yxatda yo‘q. Iltimos, administratorga murojaat qiling.",
        "onboarded": "Xush kelibsiz.",
        "support_teachers": "Support Teacherlar",
        "choose_support_type": "Qaysi yo‘nalish bo‘yicha yordam kerak?",
        "my_lessons": "Mening darslarim",
        "no_support_types": "Hali yo‘nalishlar qo‘shilmagan.",
        "no_support": "Bu yo‘nalishda hozircha Support Teacher yo‘q.",
        "booked": "Dars band qilindi.",
        "main_menu_button": "Asosiy menyu",
    },
    "ru": {
        "choose_language": "Выберите язык:",
        "main_menu": "Что делаем?",
        "share_contact": "Чтобы продолжить, отправьте контакт или напишите номер телефона.",
        "share_contact_button": "Отправить номер телефона",
        "not_allowed": "Этот номер телефона не добавлен в список. Обратитесь к администратору.",
        "onboarded": "Добро пожаловать.",
        "support_teachers": "Support Teacher",
        "choose_support_type": "По какому направлению нужна помощь?",
        "my_lessons": "Мои уроки",
        "no_support_types": "Направления ещё не добавлены.",
        "no_support": "В этом направлении пока нет Support Teacher.",
        "booked": "Урок забронирован.",
        "main_menu_button": "Главное меню",
    },
}


def normalize_lang(language: str | None) -> str:
    return language if language in TEXT else "uz"


def t(key: str, language: str | None = "uz") -> str:
    return TEXT[normalize_lang(language)].get(key, key)


def title(title_text: str, body: str) -> str:
    return f"{title_text}\n{body}"
