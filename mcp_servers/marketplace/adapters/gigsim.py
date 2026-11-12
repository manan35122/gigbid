"""GigSim adapter: the only code that knows GigSim's REST shape."""
import asyncio
import os
from typing import Any

import httpx


class MarketplaceUnavailable(Exception):
    """Raised when the marketplace cannot be reached after retries (degraded mode)."""


class GigSimAdapter:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 retries: int = 3, timeout: float = 10.0):
        self.base = (base_url or os.getenv("GIGSIM_BASE_URL", "http://localhost:8081")).rstrip("/")
        self.headers = {"Authorization": f"Bearer {token or os.getenv('GIGSIM_API_TOKEN', 'dev-token-123')}"}
        self.retries, self.timeout = retries, timeout

    async def _call(self, method: str, path: str, **kw) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r = await c.request(method, self.base + path, headers=self.headers, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    last = MarketplaceUnavailable(f"{r.status_code} from marketplace")
                    await asyncio.sleep(min(0.5 * 2 ** attempt, 4))
                    continue
                if r.status_code >= 400:
                    detail = r.json().get("detail", r.text) if r.headers.get(
                        "content-type", "").startswith("application/json") else r.text
                    raise ValueError(f"marketplace rejected request ({r.status_code}): {detail}")
                return r.json()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last = MarketplaceUnavailable(f"cannot reach marketplace: {e}")
                await asyncio.sleep(min(0.5 * 2 ** attempt, 4))
        raise MarketplaceUnavailable(str(last))

    async def search_jobs(self, query: str = "", limit: int = 20, offset: int = 0):
        return await self._call("GET", "/jobs", params=dict(q=query, limit=limit, offset=offset))

    async def get_job(self, job_id: str):
        return await self._call("GET", f"/jobs/{job_id}")

    async def get_client_history(self, client_id: str):
        return await self._call("GET", f"/clients/{client_id}")

    async def get_connects_balance(self):
        return await self._call("GET", "/connects")

    async def job_price_history(self, skill: str = "", limit: int = 200):
        return await self._call("GET", "/jobs/history", params=dict(skill=skill, limit=limit))

    async def list_messages(self, proposal_id: str = ""):
        return await self._call("GET", "/messages", params=dict(proposal_id=proposal_id))

    async def create_proposal_draft(self, payload: dict, idempotency_key: str, dry_run: bool = False):
        return await self._call("POST", "/proposals",
                                json=dict(payload, idempotency_key=idempotency_key, dry_run=dry_run))

    async def submit_proposal(self, proposal_id: str, idempotency_key: str):
        return await self._call("POST", f"/proposals/{proposal_id}/submit",
                                json=dict(idempotency_key=idempotency_key))

    async def get_proposal(self, proposal_id: str):
        return await self._call("GET", f"/proposals/{proposal_id}")

    async def send_message(self, proposal_id: str, text: str, idempotency_key: str):
        return await self._call("POST", "/messages",
                                json=dict(proposal_id=proposal_id, text=text, idempotency_key=idempotency_key))