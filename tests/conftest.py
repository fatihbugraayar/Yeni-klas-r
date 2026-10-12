from datetime import timedelta
from uuid import uuid4

import pytest

from telegram_bot.database.base import Database
from telegram_bot.database.models import Job, utcnow
from telegram_bot.database.repository import Repository


@pytest.fixture
async def repo(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await db.initialize()
    repository = Repository(db)
    await repository.ensure_user(101, "tester", "en")
    yield repository
    await db.close()


def new_job(service="emoji_pack", user_id=101, **values):
    job_id = uuid4().hex
    defaults = dict(
        id=job_id,
        source_key=job_id,
        telegram_id=user_id,
        chat_id=user_id,
        service_type=service,
        params={},
        expires_at=utcnow() + timedelta(hours=1),
    )
    defaults.update(values)
    return Job(**defaults)
