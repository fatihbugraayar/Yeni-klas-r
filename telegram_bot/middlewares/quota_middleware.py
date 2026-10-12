import asyncio
from weakref import WeakValueDictionary

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from telegram_bot.i18n import detect_language


class PrivateFlowMiddleware(BaseMiddleware):
    """Serialize only input messages/callbacks, never the 10-second checkout path.

    Daily UTC refresh is atomic in Repository.ensure_user and create_job.
    """

    def __init__(self, translator):
        self.locks = WeakValueDictionary()
        self.translator = translator

    async def __call__(self, handler, event, data):
        if event.from_user is None:
            return
        message = event.message if isinstance(event, CallbackQuery) else event
        if not isinstance(message, Message) or message.chat.type != "private":
            t = self.translator.for_language(detect_language(event.from_user.language_code))
            if isinstance(event, CallbackQuery):
                await event.answer(t("private_only"), show_alert=True)
            elif isinstance(message, Message):
                await message.answer(t("private_only"))
            return
        lock = self.locks.setdefault(event.from_user.id, asyncio.Lock())
        async with lock:
            return await handler(event, data)
