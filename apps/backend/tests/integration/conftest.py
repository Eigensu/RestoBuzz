import pytest

from app.database import close_db


@pytest.fixture(autouse=True)
async def _reset_db_client():
    """pytest-asyncio gives each test function its own event loop by default.
    app.database's global Motor client binds to whichever loop is running
    when it's first used, so a client created in one test's loop raises
    "Event loop is closed" when a later test (in a fresh loop) reuses it.
    Close it after every test so the next one lazily creates its own.
    """
    yield
    await close_db()
