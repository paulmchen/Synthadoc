# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import resolve_wiki_path

schedule_app = typer.Typer(help="Manage recurring scheduled operations.")
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("add")
def add_cmd(
    op: str = typer.Option(..., "--op", help="synthadoc operation (e.g. 'lint')"),
    cron: str = typer.Option(..., "--cron", help="Cron expression"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Register a recurring operation with the OS scheduler."""
    from synthadoc.core.scheduler import Scheduler
    from pathlib import Path
    root = resolve_wiki_path(wiki) if wiki else Path(".")
    sched = Scheduler(wiki=wiki or "default", wiki_root=str(root))
    entry_id = sched.add(op=op, cron=cron)
    typer.echo(f"Scheduled: {entry_id}")


@schedule_app.command("list")
def list_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    """List all synthadoc-registered scheduled jobs."""
    from synthadoc.core.scheduler import Scheduler
    from pathlib import Path
    root = resolve_wiki_path(wiki) if wiki else Path(".")
    sched = Scheduler(wiki=wiki or "default", wiki_root=str(root))
    for e in sched.list():
        typer.echo(f"{e.id}  {e.cron}  {e.op}")


@schedule_app.command("remove")
def remove_cmd(
    entry_id: str = typer.Argument(...),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Remove a scheduled job by ID."""
    from synthadoc.core.scheduler import Scheduler
    from pathlib import Path
    root = resolve_wiki_path(wiki) if wiki else Path(".")
    sched = Scheduler(wiki=wiki or "default", wiki_root=str(root))
    sched.remove(entry_id)
    typer.echo(f"Removed: {entry_id}")


@schedule_app.command("apply")
def apply_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    """Register all jobs declared in [schedule] in the project config."""
    from synthadoc.config import load_config
    from synthadoc.core.scheduler import Scheduler, ScheduleEntry
    from pathlib import Path
    root = resolve_wiki_path(wiki) if wiki else Path(".")
    cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    sched = Scheduler(wiki=wiki or "default", wiki_root=str(root))
    ids = sched.apply([ScheduleEntry(op=j.op, cron=j.cron, wiki=wiki or "default")
                       for j in cfg.schedule.jobs])
    for entry_id in ids:
        typer.echo(f"Registered: {entry_id}")
