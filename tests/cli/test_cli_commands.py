# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from synthadoc.cli.main import app

runner = CliRunner()


def test_ingest_batch_dir(tmp_path):
    """--batch scans directory for supported files and enqueues each."""
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 dummy")
    (tmp_path / "skip.xyz").write_text("ignored")
    with patch("synthadoc.cli.ingest.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.ingest = AsyncMock(return_value="job-1")
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["ingest", "--batch", str(tmp_path), "--yes"])
    assert result.exit_code == 0
    assert mock_orch.ingest.call_count == 2    # a.md + b.pdf, not skip.xyz


def test_ingest_resume_replays_pending_jobs(tmp_path):
    """--resume calls orchestrator.resume() without a source argument."""
    with patch("synthadoc.cli.ingest.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.resume = AsyncMock(return_value=2)
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["ingest", "--resume"])
    assert result.exit_code == 0
    mock_orch.resume.assert_called_once()


def test_ingest_force_bypasses_dedup(tmp_path):
    """--force passes force=True to orchestrator.ingest()."""
    source = tmp_path / "doc.md"
    source.write_text("# Doc", encoding="utf-8")
    with patch("synthadoc.cli.ingest.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.ingest = AsyncMock(return_value="job-1")
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["ingest", str(source), "--force", "--yes"])
    assert result.exit_code == 0
    _, kwargs = mock_orch.ingest.call_args
    assert kwargs.get("force") is True


def test_jobs_list_filtered_by_dead_status(tmp_path):
    """jobs list --status dead returns only dead jobs."""
    with patch("synthadoc.cli.jobs.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.queue = AsyncMock()
        mock_orch.queue.list_jobs = AsyncMock(return_value=[
            MagicMock(id="a1", status="dead", operation="ingest"),
        ])
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["jobs", "list", "--status", "dead"])
    assert result.exit_code == 0
    assert "a1" in result.output


def test_jobs_retry_dead_reenqueues(tmp_path):
    """jobs retry <id> resets the job to pending."""
    with patch("synthadoc.cli.jobs.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.queue = AsyncMock()
        mock_orch.queue.retry = AsyncMock()
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["jobs", "retry", "a1"])
    assert result.exit_code == 0
    mock_orch.queue.retry.assert_called_once_with("a1")


def test_jobs_purge_older_than(tmp_path):
    """jobs purge --older-than 30 removes stale jobs."""
    with patch("synthadoc.cli.jobs.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.queue = AsyncMock()
        mock_orch.queue.purge = AsyncMock(return_value=5)
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["jobs", "purge", "--older-than", "30"])
    assert result.exit_code == 0
    mock_orch.queue.purge.assert_called_once_with(older_than_days=30)


import asyncio as _asyncio


def test_cache_clear_removes_entries(tmp_path):
    """cache clear deletes all LLM response cache entries and reports count."""
    import asyncio
    from synthadoc.core.cache import CacheManager

    # Populate the cache with 3 entries
    sd = tmp_path / ".synthadoc"
    sd.mkdir()

    async def _seed():
        cm = CacheManager(sd / "cache.db")
        await cm.init()
        await cm.set("k1", {"v": 1})
        await cm.set("k2", {"v": 2})
        await cm.set("k3", {"v": 3})

    asyncio.run(_seed())

    result = runner.invoke(app, ["cache", "clear", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    assert "3" in result.output
    assert "removed" in result.output.lower()


def test_cache_clear_no_db_reports_nothing(tmp_path):
    """cache clear on a wiki with no cache.db exits cleanly with an informational message."""
    result = runner.invoke(app, ["cache", "clear", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing" in result.output.lower() or "no cache" in result.output.lower()


def test_cache_clear_unknown_action_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["cache", "bogus"])
    assert result.exit_code != 0
