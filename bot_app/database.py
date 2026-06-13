from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def normalize_phone(phone: str | int | None) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def plus_days(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")


def read_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def write_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def working_hours() -> list[int]:
    return list(range(8, 19))


def schedule_template_for_date(date: str) -> str:
    day = datetime.fromisoformat(date).day
    return "odd" if day % 2 else "even"


@dataclass
class User:
    phone: str
    role: str
    name: str
    surname: str
    language: str
    telegram_id: int | None
    chat_id: int | None
    username: str
    no_show_count: int
    banned_until: str | None


@dataclass
class Category:
    id: int
    name: str
    active: bool


@dataclass
class SupportTeacher:
    id: int
    phone: str
    name: str
    surname: str
    ielts: str
    cefr: str
    sat: str
    rating: float
    rating_count: int
    categories: list[int]
    schedule: dict[str, Any]
    conducted_lessons: int
    monthly_conducted: dict[str, int]


@dataclass
class Booking:
    id: int
    role: str
    user_phone: str
    support_teacher_id: int
    category_id: int
    date: str
    start_hour: int
    duration: int
    hours: list[int]
    status: str
    reminded20: bool
    reminded5: bool
    feedback_requested: bool
    feedback_given: bool


class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self) -> None:
        self.db.close()

    def migrate(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              phone TEXT PRIMARY KEY,
              role TEXT NOT NULL,
              name TEXT NOT NULL DEFAULT '',
              surname TEXT NOT NULL DEFAULT '',
              language TEXT NOT NULL DEFAULT 'uz',
              telegram_id INTEGER UNIQUE,
              chat_id INTEGER,
              telegram_json TEXT,
              no_show_count INTEGER NOT NULL DEFAULT 0,
              banned_until TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS support_teachers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              phone TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              surname TEXT NOT NULL,
              ielts TEXT NOT NULL DEFAULT '',
              cefr TEXT NOT NULL DEFAULT '',
              sat TEXT NOT NULL DEFAULT '',
              rating REAL NOT NULL DEFAULT 0,
              rating_count INTEGER NOT NULL DEFAULT 0,
              categories_json TEXT NOT NULL,
              schedule_json TEXT NOT NULL,
              conducted_lessons INTEGER NOT NULL DEFAULT 0,
              monthly_conducted_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              role TEXT NOT NULL,
              user_phone TEXT NOT NULL,
              support_teacher_id INTEGER NOT NULL,
              category_id INTEGER NOT NULL,
              lesson_date TEXT NOT NULL,
              start_hour INTEGER NOT NULL,
              duration INTEGER NOT NULL,
              hours_json TEXT NOT NULL,
              status TEXT NOT NULL,
              reminded20 INTEGER NOT NULL DEFAULT 0,
              reminded5 INTEGER NOT NULL DEFAULT 0,
              feedback_requested INTEGER NOT NULL DEFAULT 0,
              feedback_given INTEGER NOT NULL DEFAULT 0,
              cancel_reason TEXT,
              cancelled_at TEXT,
              completed_at TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              booking_id INTEGER NOT NULL,
              rating INTEGER NOT NULL,
              text TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
            CREATE INDEX IF NOT EXISTS idx_bookings_support_date ON bookings(support_teacher_id, lesson_date, status);
            CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_phone, status);
            """
        )
        self._ensure_column("users", "language", "TEXT NOT NULL DEFAULT 'uz'")
        self.db.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _user(self, row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            phone=row["phone"],
            role=row["role"],
            name=row["name"] or "",
            surname=row["surname"] or "",
            language=row["language"] or "uz",
            telegram_id=row["telegram_id"],
            chat_id=row["chat_id"],
            username=read_json(row["telegram_json"], {}).get("username") or "",
            no_show_count=row["no_show_count"] or 0,
            banned_until=row["banned_until"],
        )

    def _category(self, row: sqlite3.Row | None) -> Category | None:
        if row is None:
            return None
        return Category(id=row["id"], name=row["name"], active=bool(row["active"]))

    def _support(self, row: sqlite3.Row | None) -> SupportTeacher | None:
        if row is None:
            return None
        return SupportTeacher(
            id=row["id"],
            phone=row["phone"],
            name=row["name"],
            surname=row["surname"],
            ielts=row["ielts"] or "",
            cefr=row["cefr"] or "",
            sat=row["sat"] or "",
            rating=row["rating"] or 0,
            rating_count=row["rating_count"] or 0,
            categories=read_json(row["categories_json"], []),
            schedule=read_json(row["schedule_json"], {}),
            conducted_lessons=row["conducted_lessons"] or 0,
            monthly_conducted=read_json(row["monthly_conducted_json"], {}),
        )

    def _booking(self, row: sqlite3.Row | None) -> Booking | None:
        if row is None:
            return None
        return Booking(
            id=row["id"],
            role=row["role"],
            user_phone=row["user_phone"],
            support_teacher_id=row["support_teacher_id"],
            category_id=row["category_id"],
            date=row["lesson_date"],
            start_hour=row["start_hour"],
            duration=row["duration"],
            hours=read_json(row["hours_json"], []),
            status=row["status"],
            reminded20=bool(row["reminded20"]),
            reminded5=bool(row["reminded5"]),
            feedback_requested=bool(row["feedback_requested"]),
            feedback_given=bool(row["feedback_given"]),
        )

    def refresh_ban(self, user: User | None) -> User | None:
        if not user or not user.banned_until:
            return user
        if datetime.fromisoformat(user.banned_until) > datetime.now():
            return user
        self.db.execute(
            "UPDATE users SET no_show_count = 0, banned_until = NULL, updated_at = ? WHERE phone = ?",
            (now(), user.phone),
        )
        self.db.commit()
        return self.get_user_by_phone(user.phone)

    def upsert_allowed_user(self, phone: str, role: str, name: str = "", surname: str = "") -> User:
        clean_phone = normalize_phone(phone)
        existing = self.get_user_by_phone(clean_phone)
        stamp = now()
        self.db.execute(
            """
            INSERT INTO users (phone, role, name, surname, language, telegram_id, chat_id, telegram_json, no_show_count, banned_until, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
              role = excluded.role,
              name = excluded.name,
              surname = excluded.surname,
              updated_at = excluded.updated_at
            """,
            (
                clean_phone,
                role,
                name,
                surname,
                existing.language if existing else "uz",
                existing.telegram_id if existing else None,
                existing.chat_id if existing else None,
                None,
                existing.no_show_count if existing else 0,
                existing.banned_until if existing else None,
                stamp,
                stamp,
            ),
        )
        self.db.commit()
        user = self.get_user_by_phone(clean_phone)
        assert user is not None
        return user

    def link_telegram_user(self, phone: str, telegram_id: int, chat_id: int, telegram_data: dict[str, Any], language: str = "uz") -> User | None:
        clean_phone = normalize_phone(phone)
        user = self.get_user_by_phone(clean_phone)
        if not user:
            return None
        self.db.execute(
            "UPDATE users SET telegram_id = ?, chat_id = ?, language = ?, telegram_json = ?, updated_at = ? WHERE phone = ?",
            (telegram_id, chat_id, language, write_json(telegram_data), now(), user.phone),
        )
        self.db.commit()
        return self.get_user_by_phone(user.phone)

    def get_user_by_telegram_id(self, telegram_id: int | None) -> User | None:
        if telegram_id is None:
            return None
        row = self.db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return self.refresh_ban(self._user(row))

    def get_user_by_phone(self, phone: str) -> User | None:
        row = self.db.execute("SELECT * FROM users WHERE phone = ?", (normalize_phone(phone),)).fetchone()
        return self.refresh_ban(self._user(row))

    def list_users(self, role: str | None = None) -> list[User]:
        if role:
            rows = self.db.execute("SELECT * FROM users WHERE role = ? ORDER BY created_at DESC", (role,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [user for row in rows if (user := self.refresh_ban(self._user(row)))]

    def create_category(self, name: str) -> Category:
        cursor = self.db.execute("INSERT INTO categories (name, active, created_at) VALUES (?, 1, ?)", (name, now()))
        self.db.commit()
        category = self.get_category(cursor.lastrowid)
        assert category is not None
        return category

    def list_categories(self) -> list[Category]:
        rows = self.db.execute("SELECT * FROM categories WHERE active = 1 ORDER BY id ASC").fetchall()
        return [category for row in rows if (category := self._category(row))]

    def get_category(self, category_id: int) -> Category | None:
        row = self.db.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
        return self._category(row)

    def create_support_teacher(self, data: dict[str, Any]) -> SupportTeacher:
        clean_phone = normalize_phone(data["phone"])
        cursor = self.db.execute(
            """
            INSERT INTO support_teachers (
              phone, name, surname, ielts, cefr, sat, categories_json, schedule_json,
              conducted_lessons, monthly_conducted_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                clean_phone,
                data["name"],
                data["surname"],
                data.get("ielts", ""),
                data.get("cefr", ""),
                data.get("sat", ""),
                write_json(data.get("categories", [])),
                write_json({}),
                write_json({}),
                now(),
            ),
        )
        self.upsert_allowed_user(clean_phone, "support_teacher", data["name"], data["surname"])
        self.db.commit()
        support = self.get_support_teacher(cursor.lastrowid)
        assert support is not None
        return support

    def get_support_teacher(self, support_id: int) -> SupportTeacher | None:
        row = self.db.execute("SELECT * FROM support_teachers WHERE id = ?", (support_id,)).fetchone()
        return self._support(row)

    def find_support_teacher_by_phone(self, phone: str) -> SupportTeacher | None:
        row = self.db.execute("SELECT * FROM support_teachers WHERE phone = ?", (normalize_phone(phone),)).fetchone()
        return self._support(row)

    def list_support_teachers(self, category_id: int | None = None) -> list[SupportTeacher]:
        rows = self.db.execute("SELECT * FROM support_teachers ORDER BY id ASC").fetchall()
        supports = [support for row in rows if (support := self._support(row))]
        if category_id is None:
            return supports
        return [support for support in supports if int(category_id) in support.categories]

    def get_open_slots(self, support_id: int, date: str) -> list[int]:
        support = self.get_support_teacher(support_id)
        if not support:
            return []
        template_key = schedule_template_for_date(date)
        template_closed = support.schedule.get("templates", {}).get(template_key, {}).get("closed", [])
        closed = set(support.schedule.get(date, {}).get("closed", template_closed))
        rows = self.db.execute(
            "SELECT hours_json FROM bookings WHERE support_teacher_id = ? AND lesson_date = ? AND status = 'booked'",
            (support.id, date),
        ).fetchall()
        booked = {hour for row in rows for hour in read_json(row["hours_json"], [])}
        return [hour for hour in working_hours() if hour not in closed and hour not in booked]

    def get_template_open_slots(self, support_id: int, template_key: str) -> list[int]:
        support = self.get_support_teacher(support_id)
        if not support or template_key not in {"odd", "even"}:
            return []
        closed = set(support.schedule.get("templates", {}).get(template_key, {}).get("closed", []))
        return [hour for hour in working_hours() if hour not in closed]

    def set_template_slot_open(self, support_id: int, template_key: str, hour: int, is_open: bool) -> dict[str, Any]:
        support = self.get_support_teacher(support_id)
        if not support:
            return {"ok": False, "reason": "missing_support_teacher"}
        if template_key not in {"odd", "even"}:
            return {"ok": False, "reason": "invalid_template"}
        support.schedule.setdefault("templates", {})
        support.schedule["templates"].setdefault(template_key, {"closed": []})
        closed = set(support.schedule["templates"][template_key]["closed"])
        if is_open:
            closed.discard(hour)
        else:
            closed.add(hour)
        support.schedule["templates"][template_key]["closed"] = sorted(closed)
        self.db.execute("UPDATE support_teachers SET schedule_json = ? WHERE id = ?", (write_json(support.schedule), support.id))
        self.db.commit()
        return {"ok": True}

    def set_slot_open(self, support_id: int, date: str, hour: int, is_open: bool) -> dict[str, Any]:
        support = self.get_support_teacher(support_id)
        if not support:
            return {"ok": False, "reason": "missing_support_teacher"}
        support.schedule.setdefault(date, {"closed": []})
        closed = set(support.schedule[date]["closed"])
        if is_open:
            closed.discard(hour)
        else:
            closed.add(hour)
        support.schedule[date]["closed"] = sorted(closed)
        self.db.execute("UPDATE support_teachers SET schedule_json = ? WHERE id = ?", (write_json(support.schedule), support.id))
        self.db.commit()
        return {"ok": True}

    def create_booking(self, role: str, user_phone: str, support_id: int, category_id: int, date: str, start_hour: int, duration: int) -> Booking | None:
        user = self.get_user_by_phone(user_phone)
        if user and user.banned_until and datetime.fromisoformat(user.banned_until) > datetime.now():
            return None
        hours = [start_hour + index for index in range(duration)]
        free_hours = self.get_open_slots(support_id, date)
        if any(hour not in free_hours for hour in hours):
            return None
        cursor = self.db.execute(
            """
            INSERT INTO bookings (
              role, user_phone, support_teacher_id, category_id, lesson_date, start_hour,
              duration, hours_json, status, reminded20, reminded5, feedback_requested,
              feedback_given, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'booked', 0, 0, 0, 0, ?)
            """,
            (role, normalize_phone(user_phone), support_id, category_id, date, start_hour, duration, write_json(hours), now()),
        )
        self.db.commit()
        return self.get_booking(cursor.lastrowid)

    def get_booking(self, booking_id: int) -> Booking | None:
        row = self.db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return self._booking(row)

    def list_bookings(self, *, status: str | None = None, support_id: int | None = None, user_phone: str | None = None) -> list[Booking]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if support_id:
            conditions.append("support_teacher_id = ?")
            params.append(support_id)
        if user_phone:
            conditions.append("user_phone = ?")
            params.append(normalize_phone(user_phone))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.db.execute(f"SELECT * FROM bookings {where} ORDER BY lesson_date ASC, start_hour ASC", params).fetchall()
        return [booking for row in rows if (booking := self._booking(row))]

    def cancel_booking(self, booking_id: int, reason: str = "cancelled") -> Booking | None:
        booking = self.get_booking(booking_id)
        if not booking or booking.status != "booked":
            return None
        status = "no_show" if reason == "student_no_show" else "cancelled"
        self.db.execute(
            "UPDATE bookings SET status = ?, cancel_reason = ?, cancelled_at = ? WHERE id = ?",
            (status, reason, now(), booking_id),
        )
        self.db.commit()
        return self.get_booking(booking_id)

    def complete_booking(self, booking_id: int) -> Booking | None:
        booking = self.get_booking(booking_id)
        if not booking or booking.status != "booked":
            return None
        support = self.get_support_teacher(booking.support_teacher_id)
        self.db.execute("UPDATE bookings SET status = 'completed', completed_at = ? WHERE id = ?", (now(), booking_id))
        if support:
            month = booking.date[:7]
            monthly = dict(support.monthly_conducted)
            monthly[month] = monthly.get(month, 0) + 1
            self.db.execute(
                "UPDATE support_teachers SET conducted_lessons = conducted_lessons + 1, monthly_conducted_json = ? WHERE id = ?",
                (write_json(monthly), support.id),
            )
        self.db.commit()
        return self.get_booking(booking_id)

    def record_no_show(self, booking_id: int) -> dict[str, Any] | None:
        booking = self.get_booking(booking_id)
        if not booking or booking.status != "booked":
            return None
        user = self.get_user_by_phone(booking.user_phone)
        if not user:
            return None
        count = min(user.no_show_count + 1, 3)
        banned_until = plus_days(14) if count >= 3 else None
        self.cancel_booking(booking.id, "student_no_show")
        self.db.execute(
            "UPDATE users SET no_show_count = ?, banned_until = ?, updated_at = ? WHERE phone = ?",
            (count, banned_until, now(), user.phone),
        )
        self.db.commit()
        return {"booking": self.get_booking(booking.id), "user": self.get_user_by_phone(user.phone), "count": count, "banned_until": banned_until}

    def add_feedback(self, booking_id: int, rating: int, text: str = "") -> dict[str, Any] | None:
        booking = self.get_booking(booking_id)
        if not booking or booking.feedback_given:
            return None
        support = self.get_support_teacher(booking.support_teacher_id)
        self.db.execute(
            "INSERT INTO feedback (booking_id, rating, text, created_at) VALUES (?, ?, ?, ?)",
            (booking_id, rating, text, now()),
        )
        self.db.execute("UPDATE bookings SET feedback_given = 1 WHERE id = ?", (booking_id,))
        if support:
            total = support.rating * support.rating_count + rating
            count = support.rating_count + 1
            self.db.execute("UPDATE support_teachers SET rating = ?, rating_count = ? WHERE id = ?", (round(total / count, 2), count, support.id))
        self.db.commit()
        return {"booking_id": booking_id, "rating": rating, "text": text}

    def mark_booking(self, booking_id: int, **patch: Any) -> Booking | None:
        booking = self.get_booking(booking_id)
        if not booking:
            return None
        reminded20 = int(patch.get("reminded20", booking.reminded20))
        reminded5 = int(patch.get("reminded5", booking.reminded5))
        feedback_requested = int(patch.get("feedback_requested", booking.feedback_requested))
        feedback_given = int(patch.get("feedback_given", booking.feedback_given))
        self.db.execute(
            "UPDATE bookings SET reminded20 = ?, reminded5 = ?, feedback_requested = ?, feedback_given = ? WHERE id = ?",
            (reminded20, reminded5, feedback_requested, feedback_given, booking_id),
        )
        self.db.commit()
        return self.get_booking(booking_id)

    def stats(self) -> dict[str, int]:
        def count(query: str) -> int:
            return int(self.db.execute(query).fetchone()[0])

        return {
            "users": count("SELECT COUNT(*) FROM users"),
            "students": count("SELECT COUNT(*) FROM users WHERE role = 'student'"),
            "teachers": count("SELECT COUNT(*) FROM users WHERE role = 'teacher'"),
            "support_teachers": count("SELECT COUNT(*) FROM support_teachers"),
            "categories": count("SELECT COUNT(*) FROM categories WHERE active = 1"),
            "booked": count("SELECT COUNT(*) FROM bookings WHERE status = 'booked'"),
            "completed": count("SELECT COUNT(*) FROM bookings WHERE status = 'completed'"),
            "no_shows": count("SELECT COUNT(*) FROM bookings WHERE status = 'no_show'"),
            "banned": count("SELECT COUNT(*) FROM users WHERE banned_until IS NOT NULL"),
            "feedback": count("SELECT COUNT(*) FROM feedback"),
        }
