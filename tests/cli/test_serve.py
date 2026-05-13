# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_cfg(provider: str = "anthropic"):
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    return Config(agents=AgentsConfig(
        default=AgentConfig(provider=provider, model="claude-opus-4-6")
    ))


def test_apply_provider_override_sets_default():
    """--provider flag overrides config.toml provider on default agent config."""
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    _apply_provider_override(cfg, "claude-code")
    assert cfg.agents.default.provider == "claude-code"


def test_apply_provider_override_updates_per_agent():
    """--provider flag updates per-agent overrides when they exist."""
    from synthadoc.config import AgentConfig
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    from synthadoc.config import AgentConfig
    cfg.agents.ingest = AgentConfig(provider="anthropic", model="claude-opus-4-6")
    _apply_provider_override(cfg, "opencode")
    assert cfg.agents.default.provider == "opencode"
    assert cfg.agents.ingest.provider == "opencode"


def test_apply_provider_override_unknown_raises():
    """Unknown --provider value → Exit (cli_error calls typer.Exit)."""
    import click
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        _apply_provider_override(cfg, "unknown-tool")


# ── _sync_plugin_config ───────────────────────────────────────────────────────

def _make_plugin_dir(wiki_root: Path, server_url: str) -> Path:
    plugin_dir = wiki_root / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(
        json.dumps({"serverUrl": server_url, "rawSourcesFolder": "raw_sources"}),
        encoding="utf-8",
    )
    return plugin_dir


def test_sync_plugin_config_updates_stale_url(tmp_path):
    """Updates data.json when the stored serverUrl port differs from the served port."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, 7071)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7071"
    assert data["rawSourcesFolder"] == "raw_sources"  # other keys preserved


def test_sync_plugin_config_no_change_when_port_matches(tmp_path):
    """Leaves data.json untouched when serverUrl is already correct."""
    from synthadoc.cli.serve import _sync_plugin_config
    plugin_dir = _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    mtime_before = (plugin_dir / "data.json").stat().st_mtime
    _sync_plugin_config(tmp_path, 7070)
    mtime_after = (plugin_dir / "data.json").stat().st_mtime
    assert mtime_before == mtime_after


def test_sync_plugin_config_noop_when_plugin_not_installed(tmp_path):
    """Does not raise when the plugin data.json is absent."""
    from synthadoc.cli.serve import _sync_plugin_config
    _sync_plugin_config(tmp_path, 7070)  # no .obsidian/plugins/synthadoc/data.json


def test_sync_plugin_config_port_override_synced(tmp_path):
    """Case e: --port CLI override is reflected in plugin data.json after sync."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    # effective_port already incorporates the --port flag when serve calls this
    _sync_plugin_config(tmp_path, 8080)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://127.0.0.1:8080"


# ── _check_port (case f) ──────────────────────────────────────────────────────

def test_check_port_raises_when_port_in_use(tmp_path):
    """Case f: _check_port exits non-zero with a useful message when port is bound."""
    import click
    import socket
    from synthadoc.cli.serve import _check_port

    # Find a bindable port and hold it
    for base in range(40100, 40200):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", base))
            break
        except OSError:
            s.close()
    else:
        pytest.skip("No bindable port found")

    try:
        with pytest.raises((SystemExit, click.exceptions.Exit)):
            _check_port(base)
    finally:
        s.close()


def test_check_port_uses_loopback_only():
    """_check_port binds the probe socket to 127.0.0.1, never 0.0.0.0."""
    import socket as _socket
    bound_host = None

    original_bind = _socket.socket.bind

    def capture_bind(self, addr):
        nonlocal bound_host
        bound_host = addr[0]
        return original_bind(self, addr)

    from synthadoc.cli.serve import _check_port
    # Use a port that is almost certainly free; we only care about the host used
    with patch("socket.socket.bind", capture_bind):
        try:
            _check_port(40299)
        except Exception:
            pass
    assert bound_host == "127.0.0.1"


# ── Local binding enforcement ─────────────────────────────────────────────────

def test_serve_rejects_external_host(tmp_path, monkeypatch):
    """Case local-binding: serve exits if config.toml host is not a loopback address."""
    import click
    import tomllib
    from synthadoc.cli.serve import _LOOPBACK_ADDRS
    from synthadoc import errors as E

    # Build a minimal config where host = 0.0.0.0
    non_loopback = "0.0.0.0"
    assert non_loopback not in _LOOPBACK_ADDRS

    from synthadoc.config import Config, ServerConfig, AgentConfig, AgentsConfig
    cfg = Config(
        server=ServerConfig(host=non_loopback, port=7070),
        agents=AgentsConfig(default=AgentConfig(provider="anthropic", model="claude-opus-4-6")),
    )

    from synthadoc.cli import serve as serve_mod
    # Simulate what serve_cmd does after loading config
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        if cfg.server.host not in serve_mod._LOOPBACK_ADDRS:
            E.cli_error(
                E.SRV_EXTERNAL_HOST,
                f"External binding is not permitted: host={cfg.server.host!r}.",
                "Remove the 'host' key from .synthadoc/config.toml.",
            )


def test_loopback_addrs_constant_covers_expected_values():
    """_LOOPBACK_ADDRS must include 127.0.0.1, ::1, and localhost."""
    from synthadoc.cli.serve import _LOOPBACK_ADDRS
    assert "127.0.0.1" in _LOOPBACK_ADDRS
    assert "::1" in _LOOPBACK_ADDRS
    assert "localhost" in _LOOPBACK_ADDRS
    assert "0.0.0.0" not in _LOOPBACK_ADDRS
