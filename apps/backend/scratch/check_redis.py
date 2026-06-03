import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.config import settings
import redis

def check_redis():
    print("Connecting to Redis...")
    try:
        r = redis.from_url(settings.redis_url, socket_timeout=5)
        r.ping()
        print("Redis Ping OK")
    except Exception as e:
        print(f"Redis Ping Failed: {e}")

if __name__ == "__main__":
    check_redis()
