from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    grid = State()
    emoji_image = State()
    photo_mode = State()
    photo_image = State()
    studio_grid = State()
    studio_image = State()
    studio_format = State()
    payment = State()
