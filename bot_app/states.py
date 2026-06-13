from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    contact = State()


class AddUser(StatesGroup):
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


class CreateCategory(StatesGroup):
    name = State()


class Broadcast(StatesGroup):
    message = State()
