from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from redis.asyncio import Redis

from app.rate_limiter import SlidingWindowRateLimiter


def create_app(
    redis_client: Redis | None = None,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> FastAPI:
    max_requests = limit if limit is not None else int(os.getenv("RATE_LIMIT", "10"))
    window = (
        window_seconds
        if window_seconds is not None
        else int(os.getenv("RATE_WINDOW_SECONDS", "60"))
    )
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = redis_client or Redis.from_url(redis_url, decode_responses=True)
        app.state.redis = client
        app.state.limiter = SlidingWindowRateLimiter(client, max_requests, window)
        try:
            yield
        finally:
            if redis_client is None:
                await client.aclose()

    app = FastAPI(title="Redis Rate Limiter", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/resource")
    async def resource(request: Request) -> JSONResponse:
        if request.client is None:
            raise RuntimeError("Unable to determine request client identity")

        result = await request.app.state.limiter.check(request.client.host)
        headers = {
            "X-RateLimit-Limit": str(max_requests),
            "X-RateLimit-Remaining": str(result.remaining),
        }
        if not result.allowed:
            headers["Retry-After"] = str(result.retry_after)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers=headers,
            )

        return JSONResponse(
            content={"message": "Request allowed"},
            headers=headers,
        )

    return app


app = create_app()
