# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from pathlib import Path

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import _DEMOS, _read_registry

demo_app = typer.Typer(help="Demo wiki templates.")
app.add_typer(demo_app, name="demo")


@demo_app.command("list")
def list_demos():
    """List available demo templates and their install status."""
    registry = _read_registry()
    for name in _DEMOS:
        entry = registry.get(name)
        if entry:
            typer.echo(f"  {name}  (installed at {entry['path']})")
        else:
            typer.echo(f"  {name}")
