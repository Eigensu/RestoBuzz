import pytest
from unittest.mock import AsyncMock, MagicMock


def _redis_returning(value):
    """A fake Redis whose registered Lua script resolves to `value`.

    `register_script` is synchronous in redis-py and returns a callable script
    object, so it is a MagicMock wrapping an AsyncMock. That mirrors the real
    client — the previous stubs patched script_load/evalsha directly, which no
    longer exist here because the hand-cached SHA could not recover from
    NOSCRIPT after a Redis restart.
    """
    script = AsyncMock(return_value=value)
    redis = AsyncMock()
    redis.register_script = MagicMock(return_value=script)
    return redis, script


@pytest.mark.asyncio
async def test_acquire_allowed():
    """Token available → returns True."""
    from app.services import rate_limiter

    rate_limiter._script = None
    mock_redis, script = _redis_returning(1)

    result = await rate_limiter.acquire_token(mock_redis, "test_waba")

    assert result is True
    assert script.await_args.kwargs["keys"] == ["rate_limit:test_waba"]


@pytest.mark.asyncio
async def test_acquire_throttled():
    """No tokens → returns False."""
    from app.services import rate_limiter

    rate_limiter._script = None
    mock_redis, _ = _redis_returning(0)

    result = await rate_limiter.acquire_token(mock_redis, "test_waba")

    assert result is False


@pytest.mark.asyncio
async def test_script_is_reused_across_calls():
    """The script is registered once, not re-registered per send."""
    from app.services import rate_limiter

    rate_limiter._script = None
    mock_redis, _ = _redis_returning(1)

    for _ in range(5):
        await rate_limiter.acquire_token(mock_redis, "test_waba")

    assert mock_redis.register_script.call_count == 1


@pytest.mark.asyncio
async def test_timestamp_is_not_supplied_by_the_caller():
    """The bucket clock comes from Redis TIME, so no timestamp is passed in.

    Worker clocks drift; a backwards jump made `elapsed` negative and silently
    under-refilled the shared bucket.
    """
    from app.services import rate_limiter

    rate_limiter._script = None
    mock_redis, script = _redis_returning(1)

    await rate_limiter.acquire_token(mock_redis, "test_waba", capacity=80, refill_rate=80)

    assert script.await_args.kwargs["args"] == ["80", "80"]
    assert "redis.call('TIME')" in rate_limiter._LUA_SCRIPT
