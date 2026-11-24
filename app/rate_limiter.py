from dataclasses import dataclass
from time import time
from uuid import uuid4

from redis.asyncio import Redis


_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local cutoff_ms = now_ms - tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local window_ms = tonumber(ARGV[2])
local member = ARGV[4]

redis.call("ZREMRANGEBYSCORE", key, "-inf", cutoff_ms)
local count = redis.call("ZCARD", key)

if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local retry_after = math.ceil((tonumber(oldest[2]) + window_ms - now_ms) / 1000)
    redis.call("PEXPIRE", key, window_ms)
    return {0, 0, retry_after}
end

redis.call("ZADD", key, now_ms, member)
redis.call("PEXPIRE", key, window_ms)
return {1, limit - count - 1, 0}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


class SlidingWindowRateLimiter:
    def __init__(self, redis: Redis, limit: int, window_seconds: int) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")

        self._redis = redis
        self._limit = limit
        self._window_ms = window_seconds * 1000

    async def check(self, identity: str) -> RateLimitResult:
        now_ms = int(time() * 1000)
        result = await self._redis.eval(
            _SLIDING_WINDOW_SCRIPT,
            1,
            f"rate-limit:{identity}",
            now_ms,
            self._window_ms,
            self._limit,
            f"{now_ms}:{uuid4().hex}",
        )
        return RateLimitResult(
            allowed=bool(result[0]),
            remaining=int(result[1]),
            retry_after=int(result[2]),
        )
