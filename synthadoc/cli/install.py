# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app

_REGISTRY = Path.home() / ".synthadoc" / "wikis.json"

_DEMOS = {
    "history-of-computing": Path(__file__).parent.parent / "demos" / "history-of-computing",
}


def _read_registry() -> dict:
    if _REGISTRY.exists():
        return json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return {}


def _write_registry(data: dict) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve_wiki_path(wiki: str) -> Path:
    """Resolve a --wiki value to an absolute Path.

    Lookup order:
    1. Registry name match  — ``synthadoc status -w history-of-computing``
    2. Filesystem path      — ``synthadoc status -w ~/wikis/history-of-computing``

    If neither resolves to an existing directory, returns the path as-is and
    lets the caller surface the error (e.g. Orchestrator will fail clearly).
    """
    registry = _read_registry()
    if wiki in registry:
        return Path(registry[wiki]["path"])
    return Path(wiki)


@app.command("install")
def install_cmd(
    name: str = typer.Argument(help="Name for the new wiki"),
    target: str = typer.Option(..., "--target", "-t", help="Parent directory to install into"),
    demo: bool = typer.Option(False, "--demo", "-d", help="Install from a demo template matching <name>"),
    domain: str = typer.Option("General", "--domain", help="Knowledge domain (fresh wikis only)"),
):
    """Create a new wiki, optionally from a demo template.

    Examples:

      synthadoc install my-research --target ~/wikis

      synthadoc install history-of-computing --target ~/wikis --demo
    """
    dest = (Path(target) / name).resolve()

    if dest.exists():
        registry = _read_registry()
        if name in registry:
            entry = registry[name]
            kind = f"demo ({entry['demo']})" if entry.get("demo") else "wiki"
            typer.echo(
                f"'{name}' is already installed as a {kind} at {dest}.\n"
                f"To reinstall, run: synthadoc uninstall {name}  then install again.",
                err=True,
            )
        else:
            typer.echo(
                f"Error: '{name}' already exists at {dest} but is not tracked by synthadoc.\n"
                f"It may be a leftover from a previous install. To remove it:\n"
                f"  rm -rf \"{dest}\"    # Linux / macOS\n"
                f"  Remove-Item -Recurse -Force \"{dest}\"    # Windows PowerShell\n"
                f"Then run install again.",
                err=True,
            )
        raise typer.Exit(1)

    if demo:
        if name not in _DEMOS:
            typer.echo(
                f"Error: no demo template named '{name}'.\n"
                f"Available demos: {', '.join(_DEMOS)}",
                err=True,
            )
            raise typer.Exit(1)
        shutil.copytree(_DEMOS[name], dest)
        # Ensure operational directories exist — the demo template may not include
        # empty dirs (git doesn't track them) and shutil.copytree won't create them.
        (dest / ".synthadoc" / "logs").mkdir(parents=True, exist_ok=True)
    else:
        from synthadoc.cli._init import init_wiki
        init_wiki(dest, domain)

    registry = _read_registry()
    registry[name] = {
        "path": str(dest),
        "demo": name if demo else None,
        "installed": date.today().isoformat(),
    }
    _write_registry(registry)

    typer.echo(f"Wiki '{name}' installed at {dest}")
    typer.echo(f"Open {dest}/ as an Obsidian vault — pages are in {dest}/wiki/")


@app.command("uninstall")
def uninstall_cmd(
    name: str = typer.Argument(help="Name of the wiki to remove"),
):
    """Permanently delete an installed wiki.

    Requires two confirmations: a y/N prompt followed by typing the wiki name.
    There is no --yes flag — this operation is irreversible.
    """
    registry = _read_registry()

    if name not in registry:
        typer.echo(
            f"Wiki '{name}' is not in the registry — it may have already been uninstalled,\n"
            f"or it was never installed via `synthadoc install`.\n"
            f"If the directory still exists, remove it manually:\n"
            f"  rm -rf <path-to-wiki>    # Linux / macOS\n"
            f"  Remove-Item -Recurse -Force <path-to-wiki>    # Windows PowerShell",
            err=True,
        )
        raise typer.Exit(1)

    dest = Path(registry[name]["path"])

    if not dest.exists():
        typer.echo(f"Registered path {dest} no longer exists — removing from registry.")
        del registry[name]
        _write_registry(registry)
        raise typer.Exit(0)

    # First confirmation
    typer.confirm(
        f"Delete wiki '{name}' at {dest} and all its contents?",
        abort=True,
    )

    # Second confirmation — must type the exact name
    typed = typer.prompt(f"Type '{name}' to confirm permanent deletion")
    if typed != name:
        typer.echo("Name did not match — aborted. Nothing was deleted.")
        raise typer.Exit(1)

    shutil.rmtree(dest)
    del registry[name]
    _write_registry(registry)
    typer.echo(f"Removed {dest}")
