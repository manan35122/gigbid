import uuid

import httpx
import pytest

from agent.marketplace_port import MarketplaceRejected, get_marketplace

BASE = "http://localhost:8081"


def _sim_up() -> bool:
    try:
        return httpx.get(f"{BASE}/health", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _sim_up(), reason="GigSim-local not running on :8081")


@pytest.fixture
async def mp():
    httpx.post(f"{BASE}/admin/reset", headers={"Authorization": "Bearer dev-token-123"})
    m = get_marketplace("gigsim")
    yield m
    await m.aclose()


async def test_read_path(mp):
    jobs = await mp.search_jobs("", limit=3)
    assert len(jobs) == 3
    job = await mp.get_job(jobs[0]["job_id"])
    client = await mp.get_client_history(job["client_id"])
    assert "average_rating" in client
    assert (await mp.get_connects_balance())["balance"] == 100


async def test_dry_run_spends_nothing(mp):
    job = (await mp.search_jobs("", limit=1))[0]
    letter = "I built a similar system for a client and can share details. " * 3
    out = await mp.create_proposal_draft(
        dict(job_id=job["job_id"], cover_letter=letter, bid_amount=300, dry_run=True), uuid.uuid4().hex)
    assert out["dry_run"] is True
    assert (await mp.get_connects_balance())["balance"] == 100


async def test_submit_is_idempotent(mp):
    job = (await mp.search_jobs("", limit=1))[0]
    letter = "I built a similar system for a client and can share details. " * 3
    p = await mp.create_proposal_draft(
        dict(job_id=job["job_id"], cover_letter=letter, bid_amount=300), uuid.uuid4().hex)
    key = uuid.uuid4().hex
    await mp.submit_proposal(p["id"], key)
    await mp.submit_proposal(p["id"], key)  # retry with the same key
    bal = (await mp.get_connects_balance())["balance"]
    assert bal == 100 - job["connects_cost"]  # charged exactly once


async def test_policy_rejection(mp):
    job = (await mp.search_jobs("", limit=1))[0]
    bad = "Contact me on WhatsApp so we can talk about the work in detail today please. " * 2
    with pytest.raises(MarketplaceRejected):
        await mp.create_proposal_draft(
            dict(job_id=job["job_id"], cover_letter=bad, bid_amount=300), uuid.uuid4().hex)