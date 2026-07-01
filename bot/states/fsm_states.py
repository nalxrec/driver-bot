from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_name = State()       # ожидаем ввод ФИО
    waiting_for_passport = State()   # ожидаем фото паспорта
    waiting_for_selfie = State()     # ожидаем селфи
