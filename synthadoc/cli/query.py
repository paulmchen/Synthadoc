# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get


@app.command("query")
def query_cmd(
    question: str = typer.Argument(..., help="Question to ask the wiki"),
    save: bool = typer.Option(False, "--save", help="Save answer as wiki page"),
    wiki: str = typer.Option(".", "--wiki", "-w"),
):
    """Query the wiki. Requires synthadoc serve to be running."""
    result = get(wiki, "/query", q=question)
    typer.echo(result["answer"])
    if result.get("citations"):
        typer.echo("\nSources: " + ", ".join(f"[[{c}]]" for c in result["citations"]))
