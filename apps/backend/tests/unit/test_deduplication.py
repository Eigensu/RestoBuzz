import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_not_duplicate_first_call():
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)

    from app.services.deduplication import is_duplicate
    result = await is_duplicate(mock_redis, "wamid.abc123")
    assert result is False


@pytest.mark.asyncio
async def test_is_duplicate_second_call():
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)

    from app.services.deduplication import is_duplicate
    result = await is_duplicate(mock_redis, "wamid.abc123")
    assert result is True


@pytest.mark.asyncio
async def test_mark_seen_sets_key_with_ttl():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    from app.services.deduplication import mark_seen
    await mark_seen(mock_redis, "wamid.abc123")

    mock_redis.set.assert_called_once_with("dedup:wa:wamid.abc123", "1", ex=86400)
