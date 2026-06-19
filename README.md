# support-manager

Telegram bot for managing Support Teacher lessons.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill `BOT_TOKEN` and comma-separated `ADMIN_IDS`.
3. Optional: set `FEEDBACK_CHANNEL_ID` to a Telegram channel/group id where all Support Teacher feedback summaries should be sent. Add the bot to that channel/group and allow it to post messages.
   Database backups are sent to `-1004400631365` by default. Override it with `BACKUP_CHANNEL_ID` if needed.
4. Install dependencies and start the aiogram bot:

```bash
python3 -m pip install --target .python_deps -r requirements.txt
python main.py
```

Telegram long polling works with only one running instance per bot token. If you see
`TelegramConflictError: terminated by other getUpdates request`, stop the other local
terminal/service or any deployed copy that uses the same `BOT_TOKEN`, then start this
app again.

## Features

- Onboarding starts with language selection: Uzbek or Russian.
- Users must share phone contact after choosing language.
- Phone number must already be added by admin.
- Admin panel is available only via `/admin`.
- Admin can add, edit, delete, and inspect detailed statistics for Support Teachers.
- Admin can view, ban, unban, and delete students without active lessons.
- Admin can create support categories, send broadcasts with copy-message, and view stats.
- Student and Support Teacher admin lists are paginated; students can be searched by phone, name, or username.
- Admin can cancel all active lessons after two confirmation steps.
- Sunday is excluded from booking dates and Sunday bookings are rejected by storage validation.
- Admin can view every active lesson with its student, Support Teacher, date, time, and topic.
- `/reset_sunday_lessons` cancels mistakenly created Sunday lessons and politely notifies affected students.
- Students can book Support Teachers by support direction.
- Support Teachers can manage schedule, complete/cancel lessons, and mark `O‘quvchi kelmadi`.
- If a Support Teacher cancels early, the bot tries to assign another free Support Teacher automatically.
- No-show cycle: 1-warning, 2-warning, 3-warning then 2-week ban. Admins are notified.
- Lesson reminders: 20 minutes and 5 minutes before start.
- Database backups are sent on startup, daily at 00:05, and before a graceful shutdown.
- Support Teacher feedback can be collected in a Telegram channel via `FEEDBACK_CHANNEL_ID`.

If Telegram API is blocked on your network, set `TELEGRAM_PROXY` in `.env`, for example:

```env
TELEGRAM_PROXY=http://127.0.0.1:7890
```
