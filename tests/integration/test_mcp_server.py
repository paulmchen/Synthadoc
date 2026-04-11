# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock, patch


def test_mcp_server_has_required_tools(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    # _tool_manager.list_tools() is synchronous and returns Tool objects with .name
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    for expected in ("synthadoc_ingest", "synthadoc_query", "synthadoc_lint",
                     "synthadoc_search", "synthadoc_status"):
        assert expected in tool_names


@pytest.mark.asyncio
async def test_mcp_query_tool_returns_answer(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.agents.query_agent import QueryResult
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    mock_result = QueryResult(question="q", answer="the answer", citations=["p1"])
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=mock_result)):
        # Use convert_result=False to get the raw dict back
        result = await mcp._tool_manager.call_tool(
            "synthadoc_query", {"question": "What is AI?"}, convert_result=False
        )
    assert result["answer"] == "the answer"


@pytest.mark.asyncio
async def test_mcp_ingest_tool_returns_job_id(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    with patch("synthadoc.core.orchestrator.Orchestrator.ingest",
               new=AsyncMock(return_value="job-xyz")):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_ingest", {"source": "paper.pdf"}, convert_result=False
        )
    assert result["job_id"] == "job-xyz"
