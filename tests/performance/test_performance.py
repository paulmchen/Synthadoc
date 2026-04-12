# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""
Performance tests — verifies SLOs from design doc Section 22.
Run with: pytest tests/performance/ -v --benchmark-disable  (CI: skip timings)
         pytest tests/performance/ -v --benchmark-only      (local: full benchmarks)
"""
import pytest
import time
from unittest.mock import AsyncMock


def test_bm25_search_under_50ms(tmp_wiki):
    """BM25 search over 100 pages must complete in < 200 ms (conservative cross-platform bound).
    The design SLO is 50 ms on Linux; use pytest-benchmark for precise per-platform numbers."""
    import platform
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch

    # macOS and Windows CI runners are slower and noisier than Linux bare-metal.
    # The 50ms SLO applies to Linux only; use a generous bound elsewhere.
    # The benchmark test below records the real number for per-platform analysis.
    threshold_ms = 50 if platform.system() == "Linux" else 200

    store = WikiStorage(tmp_wiki / "wiki")
    for i in range(100):
        store.write_page(f"page-{i:03d}", f"# Page {i}\nContent about topic {i}.", {})

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    start = time.perf_counter()
    results = search.bm25_search(["topic", "content"], top_n=10)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < threshold_ms, f"BM25 search took {elapsed_ms:.1f}ms — exceeds {threshold_ms}ms SLO"


def test_bm25_search_benchmark(benchmark, tmp_wiki):
    """pytest-benchmark version for CI reporting."""
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch

    store = WikiStorage(tmp_wiki / "wiki")
    for i in range(100):
        store.write_page(f"page-{i:03d}", f"# Page {i}\nContent about topic {i}.", {})
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    benchmark(search.bm25_search, ["topic", "content"], top_n=10)


@pytest.mark.asyncio
async def test_cache_hit_makes_zero_llm_calls(tmp_wiki):
    """Second identical ingest (force=True) must make 0 analysis/decision LLM calls.

    _update_overview() is excluded from this count — it always runs after a write
    and is tested separately. We patch it out so this test focuses purely on the
    analysis + decision cache behaviour.
    """
    from unittest.mock import patch
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager
    from synthadoc.providers.base import CompletionResponse

    call_count = 0

    async def counted_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(
            text='{"entities":[],"concepts":[],"tags":[]}',
            input_tokens=10, output_tokens=5)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=counted_complete)

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    source = tmp_wiki / "raw_sources" / "cached.md"
    source.write_text("# Cache test\nSame content every time.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
                        wiki_root=tmp_wiki)

    # Patch _update_overview so it doesn't consume LLM calls in this test
    async def _noop_overview(self):
        pass

    with patch.object(IngestAgent, "_update_overview", _noop_overview):
        await agent.ingest(str(source))
        first_count = call_count
        call_count = 0
        await agent.ingest(str(source), force=True)
        second_count = call_count

    assert first_count > 0, "First ingest should have called LLM"
    assert second_count == 0, f"Cache hit should make 0 LLM calls, made {second_count}"


@pytest.mark.asyncio
async def test_web_search_fanout_enqueue_is_fast(tmp_wiki):
    """Enqueueing 20 web search child jobs must complete in < 5 seconds.

    Simulates a full web search fan-out: WebSearchSkill returns 20 URLs,
    IngestAgent returns them as child_sources, Orchestrator enqueues each.
    The queue is SQLite-backed; all 20 enqueues should finish well under 5s.
    """
    from synthadoc.core.queue import JobQueue

    sd = tmp_wiki / ".synthadoc"
    sd.mkdir(parents=True, exist_ok=True)
    queue = JobQueue(sd / "jobs.db", max_retries=3)
    await queue.init()

    child_sources = [f"https://example.com/page-{i}" for i in range(20)]

    start = time.perf_counter()
    for url in child_sources:
        await queue.enqueue("ingest", {"source": url, "force": False})
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"Enqueueing 20 child jobs took {elapsed:.2f}s — exceeds 5s SLO"

    # Verify all jobs were queued
    from synthadoc.core.queue import JobStatus
    jobs = await queue.list_jobs(status=JobStatus.PENDING)
    assert len(jobs) == 20, f"Expected 20 queued jobs, got {len(jobs)}"


def test_health_endpoint_under_10ms(tmp_wiki):
    """GET /health must respond in < 10 ms."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    client = TestClient(create_app(wiki_root=tmp_wiki))
    # warm up
    client.get("/health")
    start = time.perf_counter()
    resp = client.get("/health")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert elapsed_ms < 10, f"/health took {elapsed_ms:.1f}ms — exceeds 10ms SLO"
