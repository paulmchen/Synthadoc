# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import platform
import pytest
from unittest.mock import patch
from synthadoc.core.scheduler import Scheduler, ScheduleEntry


def test_schedule_entry_parses_cron():
    entry = ScheduleEntry(op="lint", cron="0 3 * * 0", wiki="research")
    assert entry.op == "lint"
    assert entry.cron == "0 3 * * 0"


def test_scheduler_add_returns_id():
    sched = Scheduler(wiki="research", wiki_root="/tmp/wiki")
    with patch.object(sched, "_register_os_task", return_value="sched-001"):
        entry_id = sched.add(op="lint", cron="0 3 * * 0")
    assert entry_id.startswith("sched-")


def test_scheduler_list_returns_registered_entries():
    sched = Scheduler(wiki="research", wiki_root="/tmp/wiki")
    with patch.object(sched, "_list_os_tasks", return_value=[
        ScheduleEntry(id="s1", op="lint", cron="0 3 * * 0", wiki="research"),
    ]):
        entries = sched.list()
    assert len(entries) == 1
    assert entries[0].op == "lint"


def test_scheduler_remove_calls_os():
    sched = Scheduler(wiki="research", wiki_root="/tmp/wiki")
    with patch.object(sched, "_remove_os_task") as mock_remove:
        sched.remove("sched-001")
    mock_remove.assert_called_once_with("sched-001")


@pytest.mark.skipif(platform.system() != "Linux", reason="crontab only on Linux/macOS")
def test_scheduler_linux_generates_crontab_entry(tmp_path):
    sched = Scheduler(wiki="research", wiki_root=str(tmp_path))
    line = sched._build_crontab_line(op="lint", cron="0 3 * * 0", entry_id="s1")
    assert "0 3 * * 0" in line
    assert "synthadoc" in line
    assert "lint" in line
    assert "# synthadoc:s1" in line


@pytest.mark.skipif(platform.system() != "Windows", reason="schtasks only on Windows")
def test_scheduler_windows_generates_schtasks_args(tmp_path):
    sched = Scheduler(wiki="research", wiki_root=str(tmp_path))
    args = sched._build_schtasks_args(op="lint", cron="0 3 * * 0", entry_id="s1")
    assert "/TN" in args
    assert "synthadoc-s1" in " ".join(args)


def test_scheduler_apply_from_config(tmp_path):
    """schedule apply registers all jobs declared in config.toml."""
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n'
        '[[schedule.jobs]]\nop = "lint"\ncron = "0 3 * * 0"\n'
        '[[schedule.jobs]]\nop = "ingest --batch raw_sources/"\ncron = "0 2 * * *"\n'
    )
    cfg = load_config(project_config=cfg_file)
    assert len(cfg.schedule.jobs) == 2
    assert cfg.schedule.jobs[0].op == "lint"
    assert cfg.schedule.jobs[1].cron == "0 2 * * *"
