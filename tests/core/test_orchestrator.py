# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock, patch
from synthadoc.core.orchestrator import Orchestrator
from synthadoc.config import load_config


@pytest.mark.asyncio
async def test_orchestrator_init_creates_dbs(tmp_wiki):
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    assert (tmp_wiki / ".synthadoc" / "jobs.db").exists()
    assert (tmp_wiki / ".synthadoc" / "audit.db").exists()
    assert (tmp_wiki / ".synthadoc" / "cache.db").exists()


@pytest.mark.asyncio
async def test_orchestrator_ingest_returns_job_id(tmp_wiki):
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# Test\nContent.", encoding="utf-8")
    with patch.object(orch, "_run_ingest", new=AsyncMock()):
        job_id = await orch.ingest(str(source))
    assert job_id
