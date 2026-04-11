# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from pathlib import Path


def create_mcp_server(wiki_root: Path):
    from mcp.server.fastmcp import FastMCP
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator

    cfg = load_config(project_config=wiki_root / ".synthadoc" / "config.toml")
    mcp = FastMCP("synthadoc")

    async def _orch() -> Orchestrator:
        o = Orchestrator(wiki_root=wiki_root, config=cfg)
        await o.init()
        return o

    @mcp.tool()
    async def synthadoc_ingest(source: str) -> dict:
        """Ingest a source document or URL into the wiki."""
        o = await _orch()
        job_id = await o.ingest(source, auto_confirm=True)
        return {"job_id": job_id, "source": source}

    @mcp.tool()
    async def synthadoc_query(question: str) -> dict:
        """Query the wiki and return a synthesized answer with citations."""
        o = await _orch()
        result = await o.query(question)
        return {"answer": result.answer, "citations": result.citations}

    @mcp.tool()
    async def synthadoc_lint(scope: str = "all") -> dict:
        """Run lint checks on the wiki."""
        o = await _orch()
        report = await o.lint(scope=scope)
        return {"contradictions_found": report.contradictions_found,
                "orphans": report.orphan_slugs}

    @mcp.tool()
    async def synthadoc_search(terms: str) -> dict:
        """Search the wiki with BM25 hybrid search."""
        o = await _orch()
        results = o._search.bm25_search(terms.split(), top_n=10)
        return {
            "results": [
                {"slug": r.slug, "score": r.score, "title": r.title, "snippet": r.snippet}
                for r in results
            ]
        }

    @mcp.tool()
    async def synthadoc_status() -> dict:
        """Get wiki status: page count and path."""
        o = await _orch()
        return {"pages": len(o._store.list_pages()), "wiki": str(wiki_root)}

    return mcp
