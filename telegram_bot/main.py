import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from telegram_bot.config import Settings
from telegram_bot.database.base import Database
from telegram_bot.database.repository import Repository
from telegram_bot.handlers import (
    ai_studio_handlers,
    emoji_handlers,
    fallback,
    payment_handlers,
    photo_handlers,
    start,
)
from telegram_bot.i18n import Translator
from telegram_bot.middlewares.i18n_middleware import I18nMiddleware
from telegram_bot.middlewares.quota_middleware import PrivateFlowMiddleware
from telegram_bot.polling import DurableDispatcher
from telegram_bot.runtime_lock import RuntimeLock
from telegram_bot.services.face_censor import FaceCensor
from telegram_bot.services.image_service import ImageService, MediaStore
from telegram_bot.services.payment_service import PaymentService
from telegram_bot.services.sticker_service import StickerService
from telegram_bot.services.template_service import TemplateService
from telegram_bot.services.worker import Worker


def configure_dispatcher(repo, translator, **dependencies) -> Dispatcher:
    dispatcher = DurableDispatcher(
        storage=MemoryStorage(), repo=repo, translator=translator, **dependencies
    )
    # Checkout deliberately bypasses database user loading and per-user input locks.
    i18n, flow = I18nMiddleware(repo, translator), PrivateFlowMiddleware(translator)
    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.outer_middleware(flow)
        observer.outer_middleware(i18n)
    dispatcher.include_routers(
        payment_handlers.router,
        start.router,
        emoji_handlers.router,
        photo_handlers.router,
        ai_studio_handlers.router,
        fallback.router,
    )
    return dispatcher


async def main():
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    bot = Bot(settings.bot_token.get_secret_value())
    runtime_lock = RuntimeLock(settings.data_dir.parent / "bot.lock")
    db = Database(settings.database_url)
    worker_task = None
    payment_recovery_task = None
    dispatcher = None
    try:
        await db.initialize()
        repo, translator = Repository(db), Translator()
        store = MediaStore(settings.data_dir)
        identity = await bot.get_me()
        if not identity.username:
            raise RuntimeError("The bot needs a username for sticker pack branding")
        images = ImageService(store, settings.max_image_pixels, settings.cpu_concurrency)
        stickers = StickerService(bot, repo, store, identity.username)
        payments = PaymentService(bot, repo, translator, store)
        worker = Worker(bot, repo, store, stickers, translator, settings.cpu_concurrency)
        dispatcher = configure_dispatcher(
            repo,
            translator,
            settings=settings,
            images=images,
            templates=TemplateService(images.slots),
            censor=FaceCensor(),
            payments=payments,
            worker=worker,
            input_slots=asyncio.Semaphore(settings.cpu_concurrency),
        )
        commands = [
            ("start", "Main menu"),
            ("emoji_pack", "Create an emoji pack"),
            ("photo_edit", "Hide faces"),
            ("ai_studio", "AI grid templates and sticker packs"),
            ("language", "Change language"),
            ("quota", "Free uses"),
            ("status", "Recent jobs and invoices"),
            ("terms", "Terms and privacy"),
            ("paysupport", "Payment support"),
            ("cancel", "Cancel new input"),
        ]
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in commands])
        # Keep pending payments: never drop_pending_updates=True for a paid bot.
        await bot.delete_webhook(drop_pending_updates=False)
        worker_task = asyncio.create_task(worker.run(), name="durable-job-recovery")
        payment_recovery_task = asyncio.create_task(
            dispatcher.recover_payments(bot), name="payment-inbox-recovery"
        )
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            tasks_concurrency_limit=64,
            close_bot_session=False,
        )
    finally:
        if payment_recovery_task:
            payment_recovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await payment_recovery_task
        if worker_task:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
        if dispatcher:
            # Stop in-flight handlers before closing their database and Bot dependencies.
            handlers = tuple(dispatcher._handle_update_tasks)
            for task in handlers:
                task.cancel()
            await asyncio.gather(*handlers, return_exceptions=True)
            await dispatcher.storage.close()
        await bot.session.close()
        await db.close()
        runtime_lock.close()


if __name__ == "__main__":
    asyncio.run(main())
