from aiogram import Router
from aiogram.types import CallbackQuery, Message

from telegram_bot.keyboards.inline import main_menu

router = Router(name="fallback")


@router.callback_query()
async def stale(query: CallbackQuery, t):
    await query.answer(t("stale_action"), show_alert=True)


@router.message()
async def fallback(message: Message, t):
    await message.answer(t("welcome"), reply_markup=main_menu(t))
