"""The single marketplace interface (R1). Adapters: GigSim now, live Upwork later."""
import os
from typing import Any, Protocol


class MarketplaceError(Exception):
    """Base class for marketplace failures."""


class MarketplaceUnavailable(MarketplaceError):
    """Network down, timeout, or retries exhausted on 429/5xx. Degraded mode triggers on this."""


class MarketplaceRejected(MarketplaceError):
    """The marketplace refused the request (4xx): bad input, policy, no Connects, duplicate."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class MarketplacePort(Protocol):
    # reads
    async def search_jobs(self, query: str) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def get_job_history(self, skill: str = "", limit: int = 200) -> list[dict[str, Any]]: ...
    async def list_messages(self, proposal_id: str = "") -> list[dict[str, Any]]: ...
    async def get_proposal(self, proposal_id: str) -> dict[str, Any]: ...
    # writes (every write takes an idempotency key)
    async def create_proposal_draft(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...
    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict[str, Any]: ...
    async def send_message(self, proposal_id: str, text: str, idempotency_key: str) -> dict[str, Any]: ...


def get_marketplace(mode: str | None = None) -> MarketplacePort:
    """Factory: the ONLY place that knows which adapter is in use."""
    mode = (mode or os.getenv("MARKETPLACE_MODE", "gigsim")).lower()
    if mode == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
        return GigSimAdapter()
    if mode == "upwork":
        raise NotImplementedError("live Upwork adapter comes later (Part A4)")
    raise ValueError(f"unknown MARKETPLACE_MODE: {mode}")