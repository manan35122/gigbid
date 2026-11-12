import uuid

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace.server import mcp

pytestmark = pytest.mark.asyncio


async def call(session, name, args):
    res = await session.call_tool(name, args)
    return res


async def test_tools_listed_with_annotations():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert {"search_jobs", "get_job", "create_proposal_draft", "submit_proposal"} <= set(tools)
        assert tools["search_jobs"].annotations.readOnlyHint is True
        assert tools["submit_proposal"].annotations.destructiveHint is True


async def test_dry_run_then_draft_is_idempotent():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        job = (await call(s, "search_jobs", {"limit": 1})).structuredContent
        job_id = (job.get("result") or job)[0]["job_id"]
        args = dict(job_id=job_id, bid_amount=300, cover_letter=" ".join(["word"] * 40),
                    idempotency_key=uuid.uuid4().hex)
        dry = await call(s, "create_proposal_draft", {**args, "dry_run": True})
        assert not dry.isError and dry.structuredContent["dry_run"] is True
        a = await call(s, "create_proposal_draft", args)
        b = await call(s, "create_proposal_draft", args)
        assert a.structuredContent["id"] == b.structuredContent["id"]


async def test_bad_input_rejected_by_schema():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        res = await call(s, "create_proposal_draft", dict(job_id="x", cover_letter="short",
                                                           bid_amount=-5, idempotency_key="k"))
        assert res.isError