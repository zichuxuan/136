import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_healthz_ok():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
