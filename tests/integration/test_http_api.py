# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


def test_health(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_status_returns_page_count(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        data = client.get("/status").json()
    assert "pages" in data


def test_query_endpoint(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    app = create_app(wiki_root=tmp_wiki)
    mock = QueryResult(question="q", answer="answer", citations=["p1"])
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=mock)):
        with TestClient(app) as client:
            resp = client.post("/query", json={"question": "What is AI?"})
    assert resp.json()["answer"] == "answer"


def test_ingest_endpoint_returns_job_id(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    app = create_app(wiki_root=tmp_wiki)
    with patch("synthadoc.core.orchestrator.Orchestrator.ingest",
               new=AsyncMock(return_value="job-abc")):
        with TestClient(app) as client:
            resp = client.post("/ingest", json={"source": "paper.pdf"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-abc"


def test_lint_endpoint_returns_report(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.lint_agent import LintReport
    app = create_app(wiki_root=tmp_wiki)
    mock_report = LintReport(contradictions_found=1, orphan_slugs=["stale-page"])
    with patch("synthadoc.core.orchestrator.Orchestrator.lint",
               new=AsyncMock(return_value=mock_report)):
        with TestClient(app) as client:
            resp = client.post("/lint", params={"scope": "contradictions"})
    assert resp.status_code == 200
    assert resp.json()["contradictions_found"] == 1


def test_query_empty_question_returns_422(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/query", json={"question": ""})
    assert resp.status_code == 422
