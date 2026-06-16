from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from os import getenv
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def normalize_phone(phone: str | int | None) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def local_now() -> datetime:
    timezone = getenv("TZ", "Asia/Tashkent")
    try:
        return datetime.now(ZoneInfo(timezone)).replace(tzinfo=None)
    except ZoneInfoNotFoundError:
        return datetime.now()


def now() -> str:
    return local_now().isoformat(timespec="seconds")


def plus_days(days: int) -> str:
    return (local_now() + timedelta(days=days)).isoformat(timespec="seconds")


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

            CREATE TABLE IF NOT EXISTS admins (
              phone TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              FOREIGN KEY(phone) REFERENCES users(phone) ON DELETE CASCADE
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
        self.db.execute("UPDATE users SET role = 'student', updated_at = ? WHERE role = 'teacher'", (now(),))
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
        if datetime.fromisoformat(user.banned_until) > local_now():
            return user
        self.db.execute(
            "UPDATE users SET no_show_count = 0, banned_until = NULL, updated_at = ? WHERE phone = ?",
            (now(), user.phone),
        )
        self.db.commit()
        return self.get_user_by_phone(user.phone)

    def upsert_allowed_user(self, phone: str, role: str, name: str = "", surname: str = "") -> User:
        if role == "teacher":
            role = "student"
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
        support = self.find_support_teacher_by_phone(clean_phone)
        if not user:
            user = self.upsert_allowed_user(
                clean_phone,
                "support_teacher" if support else "student",
                support.name if support else telegram_data.get("first_name") or "",
                support.surname if support else telegram_data.get("last_name") or "",
            )
        elif support and user.role != "support_teacher":
            user = self.upsert_allowed_user(clean_phone, "support_teacher", support.name, support.surname)
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

    def list_students(self) -> list[User]:
        rows = self.db.execute(
            """
            SELECT users.*
            FROM users
            LEFT JOIN admins ON admins.phone = users.phone
            WHERE users.role = 'student' AND admins.phone IS NULL
            ORDER BY users.created_at DESC
            """
        ).fetchall()
        return [user for row in rows if (user := self.refresh_ban(self._user(row)))]

    def student_stats(self, phone: str) -> dict[str, Any] | None:
        user = self.get_user_by_phone(phone)
        if not user or user.role != "student":
            return None

        def count(status: str | None = None) -> int:
            if status:
                return int(
                    self.db.execute(
                        "SELECT COUNT(*) FROM bookings WHERE user_phone = ? AND status = ?",
                        (user.phone, status),
                    ).fetchone()[0]
                )
            return int(
                self.db.execute(
                    "SELECT COUNT(*) FROM bookings WHERE user_phone = ?",
                    (user.phone,),
                ).fetchone()[0]
            )

        upcoming_rows = self.db.execute(
            """
            SELECT *
            FROM bookings
            WHERE user_phone = ? AND status = 'booked'
            ORDER BY lesson_date ASC, start_hour ASC
            LIMIT 3
            """,
            (user.phone,),
        ).fetchall()
        return {
            "user": user,
            "total": count(),
            "booked": count("booked"),
            "completed": count("completed"),
            "cancelled": count("cancelled"),
            "no_show": count("no_show"),
            "upcoming": [booking for row in upcoming_rows if (booking := self._booking(row))],
        }

    def ban_student(self, phone: str, days: int) -> User | None:
        user = self.get_user_by_phone(phone)
        if not user or user.role != "student":
            return None
        self.db.execute(
            "UPDATE users SET banned_until = ?, updated_at = ? WHERE phone = ?",
            (plus_days(days), now(), user.phone),
        )
        self.db.commit()
        return self.get_user_by_phone(user.phone)

    def unban_student(self, phone: str) -> User | None:
        user = self.get_user_by_phone(phone)
        if not user or user.role != "student":
            return None
        self.db.execute(
            "UPDATE users SET no_show_count = 0, banned_until = NULL, updated_at = ? WHERE phone = ?",
            (now(), user.phone),
        )
        self.db.commit()
        return self.get_user_by_phone(user.phone)

    def delete_student(self, phone: str) -> bool:
        user = self.get_user_by_phone(phone)
        if not user or user.role != "student":
            return False
        active_bookings = self.db.execute(
            "SELECT COUNT(*) FROM bookings WHERE user_phone = ? AND status = 'booked'",
            (user.phone,),
        ).fetchone()[0]
        if active_bookings:
            return False
        cursor = self.db.execute("DELETE FROM users WHERE phone = ?", (user.phone,))
        self.db.commit()
        return cursor.rowcount > 0

    def add_admin(self, phone: str, name: str = "", surname: str = "") -> User:
        clean_phone = normalize_phone(phone)
        user = self.get_user_by_phone(clean_phone)
        if not user:
            user = self.upsert_allowed_user(clean_phone, "student", name, surname)
        elif (name or surname) and (not user.name or not user.surname):
            user = self.upsert_allowed_user(
                clean_phone,
                user.role,
                name or user.name,
                surname or user.surname,
            )
        self.db.execute(
            "INSERT OR IGNORE INTO admins (phone, created_at) VALUES (?, ?)",
            (clean_phone, now()),
        )
        self.db.commit()
        refreshed = self.get_user_by_phone(clean_phone)
        assert refreshed is not None
        return refreshed

    def remove_admin(self, phone: str) -> bool:
        cursor = self.db.execute("DELETE FROM admins WHERE phone = ?", (normalize_phone(phone),))
        self.db.commit()
        return cursor.rowcount > 0

    def list_admins(self) -> list[User]:
        rows = self.db.execute(
            """
            SELECT users.*
            FROM admins
            JOIN users ON users.phone = admins.phone
            ORDER BY admins.created_at DESC
            """
        ).fetchall()
        return [user for row in rows if (user := self.refresh_ban(self._user(row)))]

    def is_admin_telegram_id(self, telegram_id: int | None) -> bool:
        if telegram_id is None:
            return False
        row = self.db.execute(
            """
            SELECT 1
            FROM admins
            JOIN users ON users.phone = admins.phone
            WHERE users.telegram_id = ?
            LIMIT 1
            """,
            (telegram_id,),
        ).fetchone()
        return row is not None

    def list_admin_chat_ids(self) -> list[int]:
        rows = self.db.execute(
            """
            SELECT users.chat_id
            FROM admins
            JOIN users ON users.phone = admins.phone
            WHERE users.chat_id IS NOT NULL
            ORDER BY admins.created_at DESC
            """
        ).fetchall()
        return [int(row["chat_id"]) for row in rows]

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

    def update_category(self, category_id: int, name: str) -> Category | None:
        self.db.execute(
            "UPDATE categories SET name = ? WHERE id = ? AND active = 1",
            (name, category_id),
        )
        self.db.commit()
        category = self.get_category(category_id)
        return category if category and category.active else None

    def delete_category(self, category_id: int) -> bool:
        category = self.get_category(category_id)
        if not category or not category.active:
            return False

        self.db.execute("UPDATE categories SET active = 0 WHERE id = ?", (category_id,))
        for support in self.list_support_teachers():
            categories = [item for item in support.categories if int(item) != int(category_id)]
            if categories != support.categories:
                self.db.execute(
                    "UPDATE support_teachers SET categories_json = ? WHERE id = ?",
                    (write_json(categories), support.id),
                )
        self.db.commit()
        return True

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

    def update_support_teacher(self, support_id: int, **patch: Any) -> SupportTeacher | None:
        support = self.get_support_teacher(support_id)
        if not support:
            return None

        allowed = {"phone", "name", "surname", "ielts", "cefr", "sat", "categories"}
        updates: dict[str, Any] = {key: value for key, value in patch.items() if key in allowed}
        if not updates:
            return support

        old_phone = support.phone
        if "phone" in updates:
            updates["phone"] = normalize_phone(updates["phone"])
        if "categories" in updates:
            updates["categories_json"] = write_json([int(category_id) for category_id in updates.pop("categories")])

        columns = ", ".join(f"{column} = ?" for column in updates)
        params = list(updates.values()) + [support.id]
        self.db.execute(f"UPDATE support_teachers SET {columns} WHERE id = ?", params)

        refreshed = self.get_support_teacher(support.id)
        if refreshed:
            if refreshed.phone != old_phone:
                self.upsert_allowed_user(refreshed.phone, "support_teacher", refreshed.name, refreshed.surname)
                old_user = self.get_user_by_phone(old_phone)
                if old_user and old_user.role == "support_teacher":
                    self.db.execute("UPDATE users SET role = 'student', updated_at = ? WHERE phone = ?", (now(), old_phone))
            else:
                self.upsert_allowed_user(refreshed.phone, "support_teacher", refreshed.name, refreshed.surname)
        self.db.commit()
        return self.get_support_teacher(support.id)

    def delete_support_teacher(self, support_id: int) -> bool:
        support = self.get_support_teacher(support_id)
        if not support:
            return False
        active_bookings = self.db.execute(
            "SELECT COUNT(*) FROM bookings WHERE support_teacher_id = ? AND status = 'booked'",
            (support.id,),
        ).fetchone()[0]
        if active_bookings:
            return False
        self.db.execute("DELETE FROM support_teachers WHERE id = ?", (support.id,))
        user = self.get_user_by_phone(support.phone)
        if user and user.role == "support_teacher":
            self.db.execute("UPDATE users SET role = 'student', updated_at = ? WHERE phone = ?", (now(), user.phone))
        self.db.commit()
        return True

    def support_teacher_stats(self, support_id: int) -> dict[str, Any] | None:
        support = self.get_support_teacher(support_id)
        if not support:
            return None

        def count(status: str | None = None) -> int:
            if status:
                return int(
                    self.db.execute(
                        "SELECT COUNT(*) FROM bookings WHERE support_teacher_id = ? AND status = ?",
                        (support.id, status),
                    ).fetchone()[0]
                )
            return int(
                self.db.execute(
                    "SELECT COUNT(*) FROM bookings WHERE support_teacher_id = ?",
                    (support.id,),
                ).fetchone()[0]
            )

        feedback_rows = self.db.execute(
            """
            SELECT feedback.rating, feedback.text, feedback.created_at, bookings.id AS booking_id, bookings.lesson_date
            FROM feedback
            JOIN bookings ON bookings.id = feedback.booking_id
            WHERE bookings.support_teacher_id = ?
            ORDER BY feedback.created_at DESC
            LIMIT 5
            """,
            (support.id,),
        ).fetchall()
        upcoming = self.db.execute(
            """
            SELECT *
            FROM bookings
            WHERE support_teacher_id = ? AND status = 'booked'
            ORDER BY lesson_date ASC, start_hour ASC
            LIMIT 3
            """,
            (support.id,),
        ).fetchall()
        return {
            "support": support,
            "total": count(),
            "booked": count("booked"),
            "completed": count("completed"),
            "cancelled": count("cancelled"),
            "no_show": count("no_show"),
            "feedback_count": support.rating_count,
            "recent_feedback": [dict(row) for row in feedback_rows],
            "upcoming": [booking for row in upcoming if (booking := self._booking(row))],
        }

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
        if user and user.banned_until and datetime.fromisoformat(user.banned_until) > local_now():
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
            "support_teachers": count("SELECT COUNT(*) FROM support_teachers"),
            "categories": count("SELECT COUNT(*) FROM categories WHERE active = 1"),
            "booked": count("SELECT COUNT(*) FROM bookings WHERE status = 'booked'"),
            "completed": count("SELECT COUNT(*) FROM bookings WHERE status = 'completed'"),
            "no_shows": count("SELECT COUNT(*) FROM bookings WHERE status = 'no_show'"),
            "banned": count("SELECT COUNT(*) FROM users WHERE banned_until IS NOT NULL"),
            "feedback": count("SELECT COUNT(*) FROM feedback"),
        }
