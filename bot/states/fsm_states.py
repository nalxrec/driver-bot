from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_passport = State()
    waiting_for_selfie = State()


class SealsStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_container = State()
    waiting_for_seals_photo = State()


class PortCheckStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_container = State()
    waiting_for_seals_photo = State()
    waiting_for_container_photo = State()
