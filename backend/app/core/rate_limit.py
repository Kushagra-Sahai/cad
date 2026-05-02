from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Small per-process limiter for API abuse protection.

    In production with multiple backend replicas, put Redis/API-gateway limiting
    in front of the app. This lightweight limiter keeps the standalone Docker
    setup safe by default.
    """

    def __init__(self, app, requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self.hits: dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.endswith("/health"):
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        bucket = self.hits[key]

        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()

        if len(bucket) >= self.requests:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please wait before trying again.",
                },
            )

        bucket.append(now)
        return await call_next(request)

    @staticmethod
    def _client_key(request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
