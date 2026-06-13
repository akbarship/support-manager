# support-manager

Telegram bot for managing Support Teacher lessons.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill `BOT_TOKEN` and comma-separated `ADMIN_IDS`.
3. Install dependencies and start the aiogram bot:

```bash
python3 -m pip install --target .python_deps -r requirements.txt
python main.py
```

## Features

- Onboarding starts with language selection: Uzbek or Russian.
- Users must share phone contact after choosing language.
- Phone number must already be added by admin.
- Admin panel is available only via `/admin`.
- Admin can add teachers and Support Teachers.
- Admin can create support categories, send broadcasts with copy-message, and view stats.
- Students and teachers can book Support Teachers by support direction.
- Support Teachers can manage schedule, complete/cancel lessons, and mark `O‘quvchi kelmadi`.
- If a Support Teacher cancels early, the bot tries to assign another free Support Teacher automatically.
- No-show cycle: 1-warning, 2-warning, 3-warning then 2-week ban. Admins are notified.
- Lesson reminders: 20 minutes and 5 minutes before start.

If Telegram API is blocked on your network, set `TELEGRAM_PROXY` in `.env`, for example:

```env
TELEGRAM_PROXY=http://127.0.0.1:7890
```
