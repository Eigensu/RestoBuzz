import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from redis.asyncio import Redis


class RedLockError(Exception):
    pass


class RedLock:
    """Single-instance async Redlock implementation."""

    def __init__(self, redis: Redis, key: str, ttl_ms: int = 60_000):
        self.redis = redis
        self.key = f"redlock:{key}"
        self.ttl_ms = ttl_ms
        self._token: str | None = None

    async def acquire(self, retry: int = 3, retry_delay: float = 0.1) -> bool:
        token = str(uuid.uuid4())
        for _ in range(retry):
            ok = await self.redis.set(self.key, token, px=self.ttl_ms, nx=True)
            if ok:
                self._token = token
                return True
            await asyncio.sleep(retry_delay)
        return False

    async def release(self) -> None:
        if not self._token:
            return
        # Lua: only delete if we own the lock
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        await self.redis.eval(script, 1, self.key, self._token)
        self._token = None

    @asynccontextmanager
    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise RedLockError(f"Could not acquire lock: {self.key}")
        try:
            yield self
        finally:
            await self.release()

    async def __aexit__(self, *args):
        pass
