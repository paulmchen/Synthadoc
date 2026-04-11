# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

"""Shared HTTP client helpers for CLI thin-client commands."""

import httpx
import typer

from synthadoc.config import load_config
from synthadoc.cli.install import resolve_wiki_path


def server_url(wiki: str) -> str:
    """Return the base URL for the wiki's server."""
    root = resolve_wiki_path(wiki)
    cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    port = cfg.server.port
    return f"http://127.0.0.1:{port}"


def get(wiki: str, path: str, **params) -> dict:
    url = server_url(wiki)
    try:
        resp = httpx.get(f"{url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.HTTPStatusError as e:
        typer.echo(f"Server error: {e.response.status_code} {e.response.text}", err=True)
        raise typer.Exit(1)


def post(wiki: str, path: str, body: dict) -> dict:
    url = server_url(wiki)
    try:
        resp = httpx.post(f"{url}{path}", json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.HTTPStatusError as e:
        typer.echo(f"Server error: {e.response.status_code} {e.response.text}", err=True)
        raise typer.Exit(1)


def delete(wiki: str, path: str) -> dict:
    url = server_url(wiki)
    try:
        resp = httpx.delete(f"{url}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.HTTPStatusError as e:
        typer.echo(f"Server error: {e.response.status_code} {e.response.text}", err=True)
        raise typer.Exit(1)


def _no_server(wiki: str) -> None:
    typer.echo(
        f"\nError: no synthadoc server is running for wiki '{wiki}'.\n"
        f"Start it with:\n"
        f"  synthadoc serve -w {wiki}\n",
        err=True,
    )
    raise typer.Exit(1)
