from html import escape
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from telegram_bot.handlers.states import Flow
from telegram_bot.handlers.upload import submit
from telegram_bot.keyboards.inline import studio_formats, studio_grids

router = Router(name="ai_studio")


@router.message(Command("ai_studio"))
async def studio_command(message: Message, state: FSMContext, t):
    await state.clear()
    await state.set_state(Flow.studio_grid)
    await message.answer(t("studio_grid_prompt"), reply_markup=studio_grids())


@router.callback_query(F.data == "menu:studio")
async def studio_menu(query: CallbackQuery, state: FSMContext, t):
    await query.answer()
    await studio_command(query.message, state, t)


@router.callback_query(Flow.studio_grid, F.data.regexp(r"^studio_grid:[1-9]$"))
async def select_grid(query: CallbackQuery, state: FSMContext, t, templates):
    await query.answer()
    grid = int(query.data.split(":")[1])
    blueprint = await templates.generate(grid)
    await query.message.answer_document(
        BufferedInputFile(blueprint, filename=f"grid_{grid}x{grid}.png"),
        caption=t("studio_blueprint", grid=grid),
    )
    await query.message.answer(t("studio_prompt_help"))
    await query.message.answer(
        f"<pre>{escape(t('studio_ai_prompt', grid=grid))}</pre>", parse_mode="HTML"
    )
    await state.update_data(grid=grid)
    await state.set_state(Flow.studio_image)
    await query.message.answer(t("studio_upload", grid=grid))


@router.message(Flow.studio_image)
@router.message(Flow.studio_format)
async def receive_image(message: Message, state: FSMContext, t, settings):
    media = message.document or (message.photo[-1] if message.photo else None)
    if media is None:
        await message.answer(t("expected_image"))
        return
    if media.file_size and media.file_size > settings.max_upload_bytes:
        await message.answer(
            t(
                "invalid_image",
                mb=settings.max_upload_bytes // 1_000_000,
                pixels=settings.max_image_pixels / 1_000_000,
            )
        )
        return
    token = uuid4().hex[:12]
    # Keep Telegram metadata only, never decoded images or raw bytes in the FSM.
    await state.update_data(
        studio_source=message.model_dump(mode="json", exclude_none=True), format_token=token
    )
    await state.set_state(Flow.studio_format)
    await message.answer(t("studio_format_prompt"), reply_markup=studio_formats(t, token))


@router.callback_query(
    Flow.studio_format, F.data.regexp(r"^studio_format:[a-f0-9]{12}:(custom_emoji|regular)$")
)
async def select_format(
    query: CallbackQuery,
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
    _, token, output_type = query.data.split(":")
    data = await state.get_data()
    source = data.get("studio_source")
    if token != data.get("format_token") or not source:
        await query.answer(t("stale_action"), show_alert=True)
        return
    message = Message.model_validate(source, context={"bot": query.bot})
    if message.from_user.id != query.from_user.id:
        await query.answer(t("stale_action"), show_alert=True)
        return
    await query.answer()
    await state.update_data(output_type=output_type)
    await submit(
        message,
        state,
        "ai_studio_pack",
        t,
        settings,
        repo,
        images,
        censor,
        payments,
        worker,
        input_slots,
    )
