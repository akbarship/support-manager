import tempfile
import unittest
import sqlite3
from pathlib import Path

from bot_app.database import Storage


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.temp_dir.name) / "test.sqlite"))

    def tearDown(self):
        self.storage.close()
        self.temp_dir.cleanup()

    def seed(self):
        category = self.storage.create_category("CEFR Support")
        support = self.storage.create_support_teacher({
            "phone": "+998901111111",
            "name": "Ali",
            "surname": "Valiyev",
            "ielts": "8",
            "cefr": "C1",
            "sat": "1400",
            "categories": [category.id],
        })
        student = self.storage.upsert_allowed_user("+998902222222", "student", "Aziz", "Karimov")
        booking = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-01", 10, 1)
        return category, support, student, booking

    def test_filters_support_teachers_by_category(self):
        category, support, _, _ = self.seed()
        self.assertEqual(self.storage.list_support_teachers(category.id)[0].id, support.id)

    def test_support_teacher_can_have_multiple_categories(self):
        first = self.storage.create_category("IELTS Support")
        second = self.storage.create_category("SAT Support")
        support = self.storage.create_support_teacher({
            "phone": "+998901234567",
            "name": "Sardor",
            "surname": "Rahimov",
            "categories": [first.id, second.id],
        })

        self.assertEqual(support.categories, [first.id, second.id])
        self.assertEqual(self.storage.list_support_teachers(first.id)[0].id, support.id)
        self.assertEqual(self.storage.list_support_teachers(second.id)[0].id, support.id)

    def test_updates_category_name(self):
        category = self.storage.create_category("Old name")
        updated = self.storage.update_category(category.id, "New name")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.name, "New name")
        self.assertEqual(self.storage.list_categories()[0].name, "New name")

    def test_deletes_category_and_detaches_from_support_teachers(self):
        first = self.storage.create_category("IELTS Support")
        second = self.storage.create_category("SAT Support")
        support = self.storage.create_support_teacher({
            "phone": "+998901234567",
            "name": "Sardor",
            "surname": "Rahimov",
            "categories": [first.id, second.id],
        })

        self.assertTrue(self.storage.delete_category(first.id))

        self.assertEqual([category.id for category in self.storage.list_categories()], [second.id])
        self.assertEqual(self.storage.get_support_teacher(support.id).categories, [second.id])
        self.assertEqual(self.storage.list_support_teachers(first.id), [])

    def test_unknown_contact_becomes_student_and_stores_language(self):
        user = self.storage.link_telegram_user(
            "+998903333333",
            123,
            456,
            {"first_name": "Madina", "last_name": "Aliyeva"},
            "ru",
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.role, "student")
        self.assertEqual(user.phone, "998903333333")
        self.assertEqual(user.name, "Madina")
        self.assertEqual(user.language, "ru")
        self.assertEqual(self.storage.get_user_by_telegram_id(123).phone, user.phone)

    def test_legacy_teacher_role_is_saved_as_student(self):
        user = self.storage.upsert_allowed_user("+998904444444", "teacher", "Dilshod", "Nazarov")

        self.assertEqual(user.role, "student")

    def test_adds_and_removes_admin_without_changing_role(self):
        student = self.storage.upsert_allowed_user("+998904444444", "student", "Dilshod", "Nazarov")
        admin = self.storage.add_admin(student.phone)

        self.assertEqual(admin.role, "student")
        self.assertEqual([user.phone for user in self.storage.list_admins()], [student.phone])

        linked = self.storage.link_telegram_user(
            student.phone,
            444,
            555,
            {"first_name": "Dilshod", "last_name": "Nazarov"},
            "uz",
        )
        self.assertIsNotNone(linked)
        self.assertTrue(self.storage.is_admin_telegram_id(444))
        self.assertEqual(self.storage.list_admin_chat_ids(), [555])

        self.assertTrue(self.storage.remove_admin(student.phone))
        self.assertFalse(self.storage.is_admin_telegram_id(444))
        self.assertEqual(self.storage.get_user_by_phone(student.phone).role, "student")

    def test_support_teacher_contact_gets_support_role(self):
        _, support, _, _ = self.seed()
        user = self.storage.link_telegram_user(
            support.phone,
            789,
            987,
            {"first_name": "Ali", "last_name": "Valiyev", "username": "ali_support"},
            "uz",
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.role, "support_teacher")
        self.assertEqual(user.phone, support.phone)
        self.assertEqual(user.username, "ali_support")

    def test_books_only_free_slots(self):
        category, support, student, _ = self.seed()
        duplicate = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-01", 10, 1)
        self.assertIsNone(duplicate)

    def test_odd_even_schedule_templates_control_open_slots(self):
        category, support, student, _ = self.seed()
        self.assertTrue(self.storage.set_template_slot_open(support.id, "odd", 9, False)["ok"])
        self.assertTrue(self.storage.set_template_slot_open(support.id, "even", 10, False)["ok"])

        self.assertNotIn(9, self.storage.get_open_slots(support.id, "2099-01-03"))
        self.assertIn(10, self.storage.get_open_slots(support.id, "2099-01-03"))
        self.assertIn(9, self.storage.get_open_slots(support.id, "2099-01-04"))
        self.assertNotIn(10, self.storage.get_open_slots(support.id, "2099-01-04"))

        odd_blocked = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-03", 9, 1)
        even_allowed = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-04", 9, 1)
        self.assertIsNone(odd_blocked)
        self.assertIsNotNone(even_allowed)

    def test_no_show_cycle_bans_on_third_absence(self):
        category, support, student, booking = self.seed()
        first = self.storage.record_no_show(booking.id)
        self.assertEqual(first["count"], 1)
        self.assertIsNone(first["banned_until"])

        second_booking = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-02", 10, 1)
        second = self.storage.record_no_show(second_booking.id)
        self.assertEqual(second["count"], 2)
        self.assertIsNone(second["banned_until"])

        third_booking = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-03", 10, 1)
        third = self.storage.record_no_show(third_booking.id)
        self.assertEqual(third["count"], 3)
        self.assertIsNotNone(third["banned_until"])

        blocked = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-04", 10, 1)
        self.assertIsNone(blocked)

    def test_admin_can_ban_and_unban_student(self):
        category, support, student, _ = self.seed()

        banned = self.storage.ban_student(student.phone, 14)
        blocked = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-02", 10, 1)
        unbanned = self.storage.unban_student(student.phone)
        allowed = self.storage.create_booking("student", student.phone, support.id, category.id, "2099-01-02", 10, 1)

        self.assertIsNotNone(banned)
        self.assertIsNotNone(banned.banned_until)
        self.assertIsNone(blocked)
        self.assertIsNotNone(unbanned)
        self.assertIsNone(unbanned.banned_until)
        self.assertIsNotNone(allowed)

    def test_deletes_student_only_without_active_bookings(self):
        _, _, student, booking = self.seed()

        self.assertFalse(self.storage.delete_student(student.phone))
        self.storage.complete_booking(booking.id)

        self.assertTrue(self.storage.delete_student(student.phone))
        self.assertIsNone(self.storage.get_user_by_phone(student.phone))

    def test_student_list_excludes_admins(self):
        student = self.storage.upsert_allowed_user("+998907777777", "student", "Aziz", "Karimov")
        admin = self.storage.add_admin("+998908888888", "Admin", "User")

        self.assertIn(student.phone, [user.phone for user in self.storage.list_students()])
        self.assertNotIn(admin.phone, [user.phone for user in self.storage.list_students()])

    def test_feedback_once(self):
        _, _, _, booking = self.seed()
        self.storage.complete_booking(booking.id)
        self.assertIsNotNone(self.storage.add_feedback(booking.id, 5))
        self.assertIsNone(self.storage.add_feedback(booking.id, 1))

    def test_support_teacher_stats_include_lessons_and_feedback(self):
        _, support, _, booking = self.seed()
        self.storage.complete_booking(booking.id)
        self.storage.add_feedback(booking.id, 4)

        stats = self.storage.support_teacher_stats(support.id)

        self.assertIsNotNone(stats)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["booked"], 0)
        self.assertEqual(stats["support"].conducted_lessons, 1)
        self.assertEqual(stats["support"].rating, 4)
        self.assertEqual(stats["recent_feedback"][0]["rating"], 4)

    def test_updates_support_teacher_profile_and_categories(self):
        first, support, _, _ = self.seed()
        second = self.storage.create_category("SAT Support")

        updated = self.storage.update_support_teacher(
            support.id,
            phone="+998909999999",
            name="Vali",
            surname="Aliyev",
            ielts="7.5",
            cefr="B2",
            sat="-",
            categories=[second.id],
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.phone, "998909999999")
        self.assertEqual(updated.name, "Vali")
        self.assertEqual(updated.categories, [second.id])
        self.assertEqual(self.storage.list_support_teachers(first.id), [])
        self.assertEqual(self.storage.get_user_by_phone(updated.phone).role, "support_teacher")
        self.assertEqual(self.storage.get_user_by_phone(support.phone).role, "student")

    def test_deletes_support_teacher_only_without_active_bookings(self):
        _, support, _, booking = self.seed()

        self.assertFalse(self.storage.delete_support_teacher(support.id))
        self.storage.complete_booking(booking.id)

        self.assertTrue(self.storage.delete_support_teacher(support.id))
        self.assertIsNone(self.storage.get_support_teacher(support.id))
        self.assertEqual(self.storage.get_user_by_phone(support.phone).role, "student")

    def test_searches_students_by_phone_name_and_username(self):
        student = self.storage.upsert_allowed_user("+998901234567", "student", "Madina", "Aliyeva")
        self.storage.link_telegram_user(
            student.phone,
            123,
            456,
            {"first_name": "Madina", "last_name": "Aliyeva", "username": "madina_support"},
            "uz",
        )

        self.assertEqual(self.storage.search_students("90123")[0].phone, student.phone)
        self.assertEqual(self.storage.search_students("madina ali")[0].phone, student.phone)
        self.assertEqual(self.storage.search_students("@MADINA_SUPPORT")[0].phone, student.phone)

    def test_cancels_all_active_bookings(self):
        category, support, student, first = self.seed()
        second = self.storage.create_booking(
            "student",
            student.phone,
            support.id,
            category.id,
            "2099-01-02",
            11,
            1,
        )

        self.assertEqual(self.storage.cancel_all_bookings(), 2)
        self.assertEqual(self.storage.get_booking(first.id).status, "cancelled")
        self.assertEqual(self.storage.get_booking(second.id).status, "cancelled")
        self.assertEqual(self.storage.cancel_all_bookings(), 0)

    def test_creates_consistent_database_backup(self):
        self.seed()
        backup_path = Path(self.temp_dir.name) / "backup.sqlite"

        self.storage.create_backup(str(backup_path))

        with sqlite3.connect(backup_path) as backup:
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
