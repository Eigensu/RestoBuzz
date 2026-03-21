from redis.asyncio import Redis

_PREFIX = "dedup:wa:"
_TTL = 86_400  # 24 hours


async def is_duplicate(redis: Redis, wa_message_id: str) -> bool:
    return bool(await redis.exists(f"{_PREFIX}{wa_message_id}"))


async def mark_seen(redis: Redis, wa_message_id: str) -> None:
    await redis.set(f"{_PREFIX}{wa_message_id}", "1", ex=_TTL)
