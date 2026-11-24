# Redis Sliding-Window Rate Limiter

A small FastAPI backend that limits requests to `GET /resource` by the caller's
IP address. Redis sorted sets store each accepted request timestamp. A Lua
script prunes expired entries, checks the current count, records an allowed
request, and refreshes the key expiry atomically so concurrent workers share
one consistent limit.

## Run locally

1. Start Redis with `docker compose up -d`.
2. Create and activate a Python virtual environment, then install
   `requirements.txt`.
3. Run `uvicorn app.main:app --reload`.
4. Open `http://localhost:8000` for the dashboard, or request
   `http://localhost:8000/resource` directly. The default is 10 requests per
   60-second rolling window. Configure `REDIS_URL`, `RATE_LIMIT`, and
   `RATE_WINDOW_SECONDS` through environment variables.

The endpoint returns `X-RateLimit-Limit` and `X-RateLimit-Remaining`. Once the
limit is reached it returns HTTP 429 with a `Retry-After` header. `/health`
does not consume a rate-limit request.

## Tests

Install `requirements-dev.txt` and run `pytest`.

The application uses the direct peer IP as the identity. If it is deployed
behind a reverse proxy, configure trusted-proxy handling at the deployment
layer rather than trusting arbitrary client-supplied forwarding headers.
