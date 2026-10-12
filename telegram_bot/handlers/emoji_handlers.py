from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.handlers.states import Flow
from telegram_bot.handlers.upload import submit

router = Router(name="emoji")


@router.callback_query(Flow.grid, F.data.regexp(r"^grid:[2-8]$"))
async def select_grid(query: CallbackQuery, state: FSMContext, t):
    grid = int(query.data.split(":")[1])
    await query.answer()
    await state.update_data(grid=grid)
    await state.set_state(Flow.emoji_image)
    await query.message.answer(t("emoji_upload", grid=grid))


@router.message(Flow.emoji_image)
async def upload_emoji(
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
        "emoji_pack",
        t,
        settings,
        repo,
        images,
        censor,
        payments,
        worker,
        input_slots,
    )
