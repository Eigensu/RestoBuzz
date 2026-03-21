import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_acquire_allowed():
    """Token available → returns True."""
    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(return_value="sha123")
    mock_redis.evalsha = AsyncMock(return_value=1)

    from app.services import rate_limiter
    rate_limiter._sha = None  # reset cached sha

    with patch.object(rate_limiter, "_sha", None):
        result = await rate_limiter.acquire_token(mock_redis, "test_waba")

    assert result is True


@pytest.mark.asyncio
async def test_acquire_throttled():
    """No tokens → returns False."""
    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(return_value="sha123")
    mock_redis.evalsha = AsyncMock(return_value=0)

    from app.services import rate_limiter
    rate_limiter._sha = "sha123"

    result = await rate_limiter.acquire_token(mock_redis, "test_waba")
    assert result is False
