from redis.asyncio import Redis
from app.config import settings

# Token bucket Lua script — atomic, no race conditions
_LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])

-- Time comes from Redis, never the caller. Worker hosts drift, and a backwards
-- jump makes `elapsed` negative, silently under-refilling the shared bucket.
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

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

# Registered through redis-py's Script wrapper rather than caching a SHA by
# hand, because that wrapper reloads the body on NOSCRIPT. A hand-cached SHA
# goes stale the moment Redis restarts or is flushed, and because this gates
# every outbound message, that turned a brief Redis blip into "all campaigns
# stop until the workers are restarted".
_script = None


def _get_script(redis: Redis):
    global _script
    if _script is None:
        _script = redis.register_script(_LUA_SCRIPT)
    return _script


async def acquire_token(
    redis: Redis,
    waba_id: str = "default",
    capacity: int | None = None,
    refill_rate: int | None = None,
) -> bool:
    """Returns True if a send slot is available, False if throttled."""
    # Use provided values or fallback to default
    cap = capacity if capacity is not None else settings.rate_limit_mps
    refill = refill_rate if refill_rate is not None else settings.rate_limit_mps

    script = _get_script(redis)
    result = await script(
        keys=[f"rate_limit:{waba_id}"],
        args=[str(cap), str(refill)],
        client=redis,
    )
    return bool(result)
