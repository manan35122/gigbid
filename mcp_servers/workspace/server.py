"""Workspace MCP server (MOCK calendar + email drafts, no Google APIs). Run: python -m mcp_servers.workspace.server"""
import os
import uuid
from datetime import datetime, timedelta
from typing import Annotated
from typing import Annotated, Any
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

mcp = FastMCP("gigbid-workspace", host="0.0.0.0", port=int(os.getenv("WORKSPACE_MCP_PORT", "8103")))
HOLDS: dict[str, dict] = {}
DRAFTS: dict[str, dict] = {}
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def free_slots(days_ahead: Annotated[int, Field(ge=1, le=14)] = 5,
               duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30) -> list[dict]:
    """Free interview slots on weekdays (mock calendar: 10:00, 14:00 and 16:00 UTC), minus existing holds."""
    out, day = [], datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    taken = {h["start"] for h in HOLDS.values()}
    while len(out) < 6 and (day - datetime.utcnow()).days < days_ahead + 3:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        for hr in (10, 14, 16):
            s = day.replace(hour=hr).isoformat()
            if s not in taken and len(out) < 6:
                out.append(dict(start=s, end=(day.replace(hour=hr) + timedelta(minutes=duration_minutes)).isoformat()))
    return out


@mcp.tool(annotations=WRITE)
def create_tentative_hold(start: Annotated[str, Field(min_length=10, max_length=40)],
                          title: Annotated[str, Field(max_length=120)],
                          idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]) -> dict[str, Any]:
    """Create a TENTATIVE calendar hold. Idempotent per key."""
    for h in HOLDS.values():
        if h["key"] == idempotency_key:
            return h
    hid = f"hold-{uuid.uuid4().hex[:8]}"
    HOLDS[hid] = dict(id=hid, start=start, title=title, status="tentative", key=idempotency_key)
    return HOLDS[hid]


@mcp.tool(annotations=WRITE)
def create_email_draft(to: Annotated[str, Field(max_length=200)], subject: Annotated[str, Field(max_length=200)],
                       body: Annotated[str, Field(max_length=5000)],
                       idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]) -> dict[str, Any]:
    """Create an email DRAFT (never sent). Idempotent per key."""
    for d in DRAFTS.values():
        if d["key"] == idempotency_key:
            return d
    did = f"draft-{uuid.uuid4().hex[:8]}"
    DRAFTS[did] = dict(id=did, to=to, subject=subject, body=body, status="draft", key=idempotency_key)
    return DRAFTS[did]


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))