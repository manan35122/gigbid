"""MCP access for agents. Each node may call only the tools on its allowlist (A6)."""
import asyncio
import json
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

SERVERS = {
    "marketplace": {"url": os.getenv("MARKETPLACE_MCP_URL", "http://localhost:8101/mcp"),
                    "transport": "streamable_http"},
    "portfolio": {"url": os.getenv("PORTFOLIO_MCP_URL", "http://localhost:8102/mcp"),
                  "transport": "streamable_http"},
}
ALLOW = {
    "load_job": {"marketplace.get_job", "marketplace.get_client_history"},
    "analyst": set(),
    "risk_assessor": {"marketplace.get_client_history"},
    "fit_matcher": {"portfolio.search_evidence"},
    "pricing": {"marketplace.get_price_history", "marketplace.get_connects_balance"},
    "writer": {"portfolio.search_evidence"},
    "critic": {"portfolio.search_evidence"},
    "liaison": {"marketplace.list_messages"},
    "preview": {"marketplace.create_proposal_draft"},
    "submit": {"marketplace.create_proposal_draft", "marketplace.submit_proposal"},
}


class ToolUnavailable(Exception):
    """MCP server unreachable after retries: the UI shows degraded mode and queues the work."""


def _parse(res):
    if res.isError:
        raise ValueError("".join(getattr(c, "text", "") for c in res.content))
    sc = res.structuredContent
    if sc is not None:
        return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads("".join(c.text for c in res.content if getattr(c, "text", None)))


async def call(node: str, server: str, tool: str, args: dict, retries: int = 2, timeout: float = 25.0):
    if f"{server}.{tool}" not in ALLOW.get(node, set()):
        raise PermissionError(f"node '{node}' may not call {server}.{tool}")
    last = None
    for attempt in range(retries + 1):
        try:
            client = MultiServerMCPClient({server: SERVERS[server]})
            async with client.session(server) as s:
                return _parse(await asyncio.wait_for(s.call_tool(tool, args), timeout))
        except ValueError:
            raise  # a tool-level rejection is not retryable
        except Exception as e:
            last = e
            await asyncio.sleep(min(0.5 * 2 ** attempt, 4))
    raise ToolUnavailable(f"{server}.{tool}: {last}")