import asyncio

import fakeredis.aioredis
from fastapi.testclient import TestClient

from app.main import create_app
from app.rate_limiter import SlidingWindowRateLimiter


def test_resource_is_limited_and_returns_retry_headers() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app = create_app(redis_client=redis, limit=2, window_seconds=60)

    with TestClient(app) as client:
        dashboard = client.get("/")
        first = client.get("/resource")
        second = client.get("/resource")
        third = client.get("/resource")

    assert dashboard.status_code == 200
    assert "Rate Limit Studio" in dashboard.text
    assert first.status_code == 200
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.status_code == 200
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert third.status_code == 429
    assert third.headers["retry-after"].isdigit()
    assert third.json() == {"detail": "Rate limit exceeded"}


def test_concurrent_requests_cannot_exceed_limit() -> None:
    async def run_checks() -> list[bool]:
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        limiter = SlidingWindowRateLimiter(redis, limit=5, window_seconds=60)
        results = await asyncio.gather(
            *(limiter.check("same-client") for _ in range(20))
        )
        await redis.aclose()
        return [result.allowed for result in results]

    assert sum(asyncio.run(run_checks())) == 5
