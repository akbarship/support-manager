import tempfile
import unittest
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

    def test_contact_must_be_preapproved_and_stores_language(self):
        self.assertIsNone(self.storage.link_telegram_user(
            "+998903333333",
            123,
            456,
            {"first_name": "Madina", "last_name": "Aliyeva"},
            "ru",
        ))

        self.storage.upsert_allowed_user("+998903333333", "student", "Madina", "Aliyeva")
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

    def test_feedback_once(self):
        _, _, _, booking = self.seed()
        self.storage.complete_booking(booking.id)
        self.assertIsNotNone(self.storage.add_feedback(booking.id, 5))
        self.assertIsNone(self.storage.add_feedback(booking.id, 1))


if __name__ == "__main__":
    unittest.main()
