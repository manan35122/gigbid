import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio.server import mcp

pytestmark = pytest.mark.asyncio


def rows(res):
    sc = res.structuredContent
    return sc.get("result", sc) if isinstance(sc, dict) else sc


async def test_search_returns_relevant_non_proposal_evidence():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        res = await s.call_tool("search_evidence", {"requirement": "RAG pipeline with reranking", "k": 5})
        hits = rows(res)
        assert len(hits) == 5
        assert all(h["type"] != "past_proposal" for h in hits)
        assert any("RAG" in h["skills"] or "rag" in h["project"] for h in hits)


async def test_get_case_study_and_skills():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        item = (await s.call_tool("get_case_study", {"evidence_id": "ai_engineer-cs-00"})).structuredContent
        assert item["evidence_id"] == "ai_engineer-cs-00"
        skills = (await s.call_tool("list_skills", {})).structuredContent
        assert "Python" in skills["skills"]


async def test_resource_templates_and_prompts_exist():
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        tmpl = [t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates]
        assert "portfolio://case/{evidence_id}" in tmpl
        assert any(p.name == "answer_screening_question" for p in (await s.list_prompts()).prompts)