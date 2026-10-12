from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.handlers.states import Flow
from telegram_bot.keyboards.inline import grids, languages, main_menu, photo_modes, terms

router = Router(name="start")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, t):
    await state.clear()
    await message.answer(t("welcome"), reply_markup=main_menu(t))


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, t):
    await state.clear()
    await message.answer(t("cancelled"), reply_markup=main_menu(t))


@router.message(Command("language"))
async def language_command(message: Message, t):
    await message.answer(t("choose_language"), reply_markup=languages())


@router.callback_query(F.data == "menu:language")
async def language_menu(query: CallbackQuery, t):
    await query.answer()
    await query.message.answer(t("choose_language"), reply_markup=languages())


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(query: CallbackQuery, repo, translator, t):
    language = query.data.split(":", 1)[1]
    if language not in {"tr", "en", "de"}:
        await query.answer(t("stale_action"), show_alert=True)
        return
    await repo.set_language(query.from_user.id, language)
    t = translator.for_language(language)
    await query.answer(t("language_saved"))
    await query.message.answer(t("welcome"), reply_markup=main_menu(t))


async def show_quota(message, t, user):
    await message.answer(
        t(
            "quota",
            emoji=user.free_emoji_credits,
            studio=user.free_ai_studio_credits,
            initial=user.initial_photo_credits,
            daily=user.daily_photo_credits,
        ),
        reply_markup=main_menu(t),
    )


@router.message(Command("quota"))
async def quota_command(message: Message, t, db_user):
    await show_quota(message, t, db_user)


@router.callback_query(F.data == "menu:quota")
async def quota_menu(query: CallbackQuery, t, db_user):
    await query.answer()
    await show_quota(query.message, t, db_user)


@router.message(Command("terms"))
async def terms_command(message: Message, t, settings):
    await message.answer(t("terms", support=settings.support_contact), reply_markup=terms(t))


@router.callback_query(F.data == "menu:terms")
async def terms_menu(query: CallbackQuery, t, settings):
    await query.answer()
    await query.message.answer(t("terms", support=settings.support_contact), reply_markup=terms(t))


@router.callback_query(F.data == "terms:accept")
async def accept_terms(query: CallbackQuery, repo, t):
    await repo.accept_terms(query.from_user.id)
    await query.answer(t("terms_accepted"), show_alert=True)


@router.message(Command("support", "paysupport"))
async def support(message: Message, t, settings):
    await message.answer(t("support", support=settings.support_contact))


@router.message(Command("status"))
async def status(message: Message, repo, t):
    jobs = await repo.recent_jobs(message.from_user.id)
    if not jobs:
        await message.answer(t("empty_status"), reply_markup=main_menu(t))
        return
    lines = []
    for job in jobs:
        service = t(
            {
                "emoji_pack": "emoji_button",
                "face_censor": "photo_button",
                "ai_studio_pack": "studio_button",
            }[job.service_type]
        )
        line = f"{job.id[:8]} · {service} · {t('status_' + job.status)}"
        lines.append(line + (f"\n{job.result_url}" if job.result_url else ""))
    await message.answer(t("status", jobs="\n".join(lines)), reply_markup=main_menu(t))
    for job in jobs:
        if job.status in {"awaiting_payment", "approved"}:
            await message.answer(
                f"{job.id[:8]}: {t('payment_prompt', stars=job.stars_amount)}",
                reply_markup=terms(t, job.id),
            )


@router.message(Command("emoji_pack"))
async def emoji_command(message: Message, state: FSMContext, t):
    await state.clear()
    await state.set_state(Flow.grid)
    await message.answer(t("grid_prompt"), reply_markup=grids())


@router.callback_query(F.data == "menu:emoji")
async def emoji_menu(query: CallbackQuery, state: FSMContext, t):
    await query.answer()
    await emoji_command(query.message, state, t)


@router.message(Command("photo_edit"))
async def photo_command(message: Message, state: FSMContext, t):
    await state.clear()
    await state.set_state(Flow.photo_mode)
    await message.answer(t("photo_prompt"), reply_markup=photo_modes(t))


@router.callback_query(F.data == "menu:photo")
async def photo_menu(query: CallbackQuery, state: FSMContext, t):
    await query.answer()
    await photo_command(query.message, state, t)
