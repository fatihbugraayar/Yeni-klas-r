import asyncio
import logging

from aiogram import Dispatcher
from aiogram.types import Update

logger = logging.getLogger(__name__)


class DurableDispatcher(Dispatcher):
    """Persist successful payments before getUpdates acknowledges their offset.

    The override wraps aiogram's retrying reader. Keep this integration covered when
    updating aiogram because _listen_updates is a protected framework API.
    """

    def __init__(self, *, repo, **kwargs):
        super().__init__(repo=repo, **kwargs)
        self.repo = repo

    async def _listen_updates(self, bot, **kwargs):
        async for update in super()._listen_updates(bot, **kwargs):
            if update.message and update.message.successful_payment:
                while True:
                    try:
                        await self.repo.save_payment_update(
                            update.update_id, update.model_dump(mode="json", exclude_none=True)
                        )
                        break
                    except Exception as exc:
                        logger.error("Payment inbox unavailable (%s)", type(exc).__name__)
                        await asyncio.sleep(1)
            yield update

    async def recover_payments(self, bot):
        while True:
            try:
                for item in await self.repo.pending_payment_updates():
                    update = Update.model_validate(item.payload, context={"bot": bot})
                    await self.feed_update(bot, update)
            except Exception as exc:
                logger.error("Payment replay interrupted (%s)", type(exc).__name__)
            await asyncio.sleep(5)
