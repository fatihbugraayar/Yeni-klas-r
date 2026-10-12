import pytest

from telegram_bot.runtime_lock import RuntimeLock


def test_runtime_lock_excludes_second_process_and_releases(tmp_path):
    first = RuntimeLock(tmp_path / "bot.lock")
    try:
        with pytest.raises(RuntimeError, match="already owns"):
            RuntimeLock(tmp_path / "bot.lock")
    finally:
        first.close()
    second = RuntimeLock(tmp_path / "bot.lock")
    second.close()
