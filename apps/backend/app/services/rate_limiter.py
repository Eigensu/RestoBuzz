import time
from redis.asyncio import Redis
from app.config import settings

# Token bucket Lua script — atomic, no race conditions
_LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = (now - last_refill) / 1000.0
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 0
end
"""

_sha: str | None = None


async def _get_sha(redis: Redis) -> str:
    global _sha
    if _sha is None:
        _sha = await redis.script_load(_LUA_SCRIPT)
    return _sha


async def acquire_token(
    redis: Redis,
    waba_id: str = "default",
    capacity: int | None = None,
    refill_rate: int | None = None,
) -> bool:
    """Returns True if a send slot is available, False if throttled."""
    sha = await _get_sha(redis)
    now_ms = int(time.time() * 1000)

    # Use provided values or fallback to default
    cap = capacity if capacity is not None else settings.rate_limit_mps
    refill = refill_rate if refill_rate is not None else settings.rate_limit_mps

    result = await redis.evalsha(
        sha,
        1,
        f"rate_limit:{waba_id}",
        str(cap),
        str(refill),
        str(now_ms),
    )
    return bool(result)
