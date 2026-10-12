from aiogram import BaseMiddleware

from telegram_bot.i18n import detect_language


class I18nMiddleware(BaseMiddleware):
    def __init__(self, repo, translator):
        self.repo, self.translator = repo, translator

    async def __call__(self, handler, event, data):
        actor = event.from_user
        if actor is None:
            return
        user = await self.repo.ensure_user(
            actor.id, actor.username, detect_language(actor.language_code)
        )
        data["db_user"] = user
        data["t"] = self.translator.for_language(user.language_code)
        return await handler(event, data)
