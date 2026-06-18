from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    contact = State()


class AddAdmin(StatesGroup):
    phone = State()
    name = State()
    surname = State()


class AddSupportTeacher(StatesGroup):
    phone = State()
    name = State()
    surname = State()
    ielts = State()
    cefr = State()
    sat = State()
    categories = State()


class EditSupportTeacher(StatesGroup):
    value = State()
    categories = State()


class CreateCategory(StatesGroup):
    name = State()


class EditCategory(StatesGroup):
    name = State()


class Broadcast(StatesGroup):
    message = State()


class StudentSearch(StatesGroup):
    query = State()


class LessonBooking(StatesGroup):
    topic = State()
