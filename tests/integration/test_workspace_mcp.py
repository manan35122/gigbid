import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace.server import mcp

pytestmark = pytest.mark.asyncio


async def test_slots_and_idempotent_hold():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        slots = (await s.call_tool("free_slots", {})).structuredContent
        slots = slots.get("result", slots)
        assert len(slots) > 0
        args = dict(start=slots[0]["start"], title="Interview", idempotency_key="key-12345678")
        a = (await s.call_tool("create_tentative_hold", args)).structuredContent
        b = (await s.call_tool("create_tentative_hold", args)).structuredContent
        assert a["id"] == b["id"]