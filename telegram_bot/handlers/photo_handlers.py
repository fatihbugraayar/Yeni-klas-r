from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.handlers.states import Flow
from telegram_bot.handlers.upload import submit

router = Router(name="photo")


@router.callback_query(Flow.photo_mode, F.data.in_({"mode:pixelate", "mode:blur"}))
async def select_mode(query: CallbackQuery, state: FSMContext, t):
    await query.answer()
    await state.update_data(mode=query.data.split(":")[1])
    await state.set_state(Flow.photo_image)
    await query.message.answer(t("photo_upload"))


@router.message(Flow.photo_image)
async def upload_photo(
    message: Message,
    state: FSMContext,
    t,
    settings,
    repo,
    images,
    censor,
    payments,
    worker,
    input_slots,
):
    await submit(
        message,
        state,
        "face_censor",
        t,
        settings,
        repo,
        images,
        censor,
        payments,
        worker,
        input_slots,
    )
