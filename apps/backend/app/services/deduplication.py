from redis.asyncio import Redis

_TTL = 86_400  # 24 hours — covers >99% of Meta's retry window (full window is 72h)


async def is_duplicate(redis: Redis | None, key: str) -> bool:
    """Return True if this key has already been seen within the TTL window.

    If redis is None (e.g. emergency fallback path), dedup is skipped and
    False is always returned so processing continues without crashing.
    """
    if redis is None:
        return False
    return bool(await redis.exists(f"wa_dedup:{key}"))


async def mark_seen(redis: Redis | None, key: str) -> None:
    """Mark a key as seen with a 24-hour TTL.

    No-op if redis is None (emergency fallback path).
    """
    if redis is None:
        return
    await redis.set(f"wa_dedup:{key}", "1", ex=_TTL)
