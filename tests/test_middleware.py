from __future__ import annotations

import asyncio
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import TimeoutMiddleware


class TimeoutMiddlewareTests(unittest.TestCase):
    def test_timeout_returns_504(self) -> None:
        app = FastAPI()
        app.add_middleware(TimeoutMiddleware, timeout_seconds=0.01)

        @app.get("/slow")
        async def slow() -> dict[str, str]:
            await asyncio.sleep(0.05)
            return {"status": "ok"}

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/slow")

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"], "Gateway Timeout")
