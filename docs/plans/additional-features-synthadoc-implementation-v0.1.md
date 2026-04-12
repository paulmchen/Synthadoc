# Synthadoc v0.1 Additional Features — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement six features for v0.1: multi-provider LLM (Gemini + Groq), audit CLI commands, purpose.md scope filtering, two-step ingest with analysis caching, overview.md auto-summary, and Tavily web search skill.

**Architecture:** Multi-provider reuses `OpenAIProvider` with a `base_url` field. Audit CLI adds read methods to `AuditDB` and a new `audit.py` CLI module. purpose.md and overview.md extend `IngestAgent`. Two-step ingest separates entity extraction into a cached `_analyse()` method. Web search fans out Tavily results as child ingest jobs via the orchestrator queue.

**Tech Stack:** Python 3.11+, OpenAI SDK (already present), Tavily Python SDK, aiosqlite, Typer + Rich, pytest-asyncio.

**Rollout order (each task is independent of later tasks except where noted):**
1. Multi-provider → 2. Audit CLI → 3. purpose.md → 4. Two-step ingest → 5. overview.md → 6. Web search

**Run all tests after each task:**
```bash
pytest tests/ -x -q
```

---

### Task 1: Multi-Provider LLM (Gemini + Groq)

**Files:**
- Modify: `synthadoc/config.py`
- Modify: `synthadoc/providers/openai.py`
- Modify: `synthadoc/providers/__init__.py`
- Modify: `synthadoc/cli/serve.py`
- Test: `tests/providers/test_providers.py`

**Background:** `AgentConfig` currently has `provider` and `model` only. Both Gemini and Groq expose OpenAI-compatible REST APIs, so we reuse `OpenAIProvider` with a `base_url` field. No new provider class is needed.

---

**Step 1: Write the failing tests**

Add to `tests/providers/test_providers.py`:

```python
def test_make_provider_missing_gemini_key_exits(monkeypatch):
    from synthadoc.providers import make_provider
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(SystemExit) as exc_info:
        make_provider("ingest", _make_cfg("gemini", "gemini-2.0-flash"))
    assert "GEMINI_API_KEY" in str(exc_info.value)
    assert "aistudio.google.com" in str(exc_info.value)


def test_make_provider_missing_groq_key_exits(monkeypatch):
    from synthadoc.providers import make_provider
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(SystemExit) as exc_info:
        make_provider("ingest", _make_cfg("groq", "llama-3.3-70b-versatile"))
    assert "GROQ_API_KEY" in str(exc_info.value)
    assert "console.groq.com" in str(exc_info.value)


def test_make_provider_gemini_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    provider = make_provider("ingest", _make_cfg("gemini", "gemini-2.0-flash"))
    assert isinstance(provider, OpenAIProvider)
    assert "generativelanguage" in provider._client.base_url.host


def test_make_provider_groq_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    provider = make_provider("ingest", _make_cfg("groq", "llama-3.3-70b-versatile"))
    assert isinstance(provider, OpenAIProvider)
    assert "groq" in str(provider._client.base_url)


def test_unknown_provider_raises_value_error():
    from synthadoc.providers import make_provider
    with pytest.raises(ValueError, match="Unknown provider"):
        make_provider("ingest", _make_cfg("unknown_llm", "some-model"))


def test_config_rejects_unknown_provider():
    import tomllib, io
    from synthadoc.config import load_config
    from pathlib import Path
    import tempfile, os
    toml_content = b'[agents.default]\nprovider = "bad_provider"\nmodel = "x"\n'
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(toml_content)
        f.flush()
        path = Path(f.name)
    try:
        with pytest.raises(ValueError, match="Unknown provider"):
            load_config(project_config=path)
    finally:
        os.unlink(path)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/providers/test_providers.py::test_make_provider_missing_gemini_key_exits -v
```
Expected: `FAILED` — `ValueError: Unknown provider 'gemini'`

**Step 3: Add `base_url` to `AgentConfig` and expand `KNOWN_PROVIDERS` in `synthadoc/config.py`**

In `config.py`, change:
```python
KNOWN_PROVIDERS = {"anthropic", "openai", "ollama"}
```
to:
```python
KNOWN_PROVIDERS = {"anthropic", "openai", "ollama", "gemini", "groq"}
```

Change `AgentConfig`:
```python
@dataclass
class AgentConfig:
    provider: str
    model: str
    base_url: str = ""
```

**Step 4: Update `OpenAIProvider` to accept `base_url` in `synthadoc/providers/openai.py`**

Replace the `__init__` method:
```python
def __init__(self, api_key: str, config: AgentConfig) -> None:
    kwargs = {"api_key": api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    self._client = AsyncOpenAI(**kwargs)
    self._config = config
```

**Step 5: Add Gemini and Groq branches in `synthadoc/providers/__init__.py`**

After the `openai` branch and before `ollama`, add:
```python
if name == "gemini":
    from synthadoc.providers.openai import OpenAIProvider
    key = _require_env("GEMINI_API_KEY", "Google Gemini",
                       "https://aistudio.google.com/app/apikey")
    cfg_with_url = AgentConfig(
        provider="gemini", model=agent_cfg.model,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    return OpenAIProvider(api_key=key, config=cfg_with_url)
if name == "groq":
    from synthadoc.providers.openai import OpenAIProvider
    key = _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys")
    cfg_with_url = AgentConfig(
        provider="groq", model=agent_cfg.model,
        base_url="https://api.groq.com/openai/v1",
    )
    return OpenAIProvider(api_key=key, config=cfg_with_url)
```

Also add `AgentConfig` to the import at the top of `__init__.py`:
```python
from synthadoc.config import Config, AgentConfig
```

**Step 6: Add pre-flight checks in `synthadoc/cli/serve.py`**

In `serve_cmd()`, after the existing `elif provider == "openai":` block, add:
```python
elif provider == "gemini":
    _require_env("GEMINI_API_KEY", "Google Gemini",
                 "https://aistudio.google.com/app/apikey")
elif provider == "groq":
    _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys")
```

**Step 7: Run tests to verify they pass**

```bash
pytest tests/providers/test_providers.py -v
```
Expected: All pass including the 6 new tests.

**Step 8: Run full test suite**

```bash
pytest tests/ -x -q
```
Expected: All pass.

**Step 9: Commit**

```bash
git add synthadoc/config.py synthadoc/providers/openai.py synthadoc/providers/__init__.py synthadoc/cli/serve.py tests/providers/test_providers.py
git commit -m "feat: add Gemini and Groq provider support via OpenAI-compatible base_url"
```

---

### Task 2: Audit CLI Commands

**Files:**
- Modify: `synthadoc/storage/log.py`
- Create: `synthadoc/cli/audit.py`
- Modify: `synthadoc/cli/main.py`
- Test: `tests/cli/test_audit_cli.py` (create new)

**Background:** `AuditDB` in `storage/log.py` has `ingests` and `audit_events` tables but no read methods. Users currently query SQLite directly. We add three read methods and a `synthadoc audit` sub-command with `history`, `cost`, and `events` commands.

---

**Step 1: Write the failing tests**

Create `tests/cli/test_audit_cli.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
import json
from datetime import datetime, timezone
from synthadoc.storage.log import AuditDB


@pytest.fixture
async def populated_audit_db(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(3):
        await db.record_ingest(
            source_hash=f"hash{i}", source_size=1000 + i,
            source_path=f"/wiki/raw/doc{i}.pdf", wiki_page=f"page-{i}",
            tokens=500 + i * 100, cost_usd=0.01 * (i + 1),
        )
    await db.record_audit_event("job-1", "ingest_complete", {"pages": 1})
    await db.record_audit_event("job-2", "lint_complete", {"resolved": 0})
    return db


@pytest.mark.asyncio
async def test_list_ingests_returns_records(populated_audit_db):
    records = await populated_audit_db.list_ingests(limit=10)
    assert len(records) == 3
    assert records[0]["source_path"] == "/wiki/raw/doc0.pdf"
    assert "tokens" in records[0]
    assert "cost_usd" in records[0]
    assert "ingested_at" in records[0]


@pytest.mark.asyncio
async def test_list_ingests_respects_limit(populated_audit_db):
    records = await populated_audit_db.list_ingests(limit=2)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_events_returns_records(populated_audit_db):
    events = await populated_audit_db.list_events(limit=10)
    assert len(events) == 2
    assert events[0]["event"] in ("ingest_complete", "lint_complete")


@pytest.mark.asyncio
async def test_cost_summary_aggregates_correctly(populated_audit_db):
    summary = await populated_audit_db.cost_summary(days=30)
    assert summary["total_tokens"] == 500 + 600 + 700
    assert abs(summary["total_cost_usd"] - 0.06) < 0.001
    assert "daily" in summary


def test_audit_history_command_prints_table(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    import asyncio

    runner = CliRunner()
    # audit history needs a running wiki with audit.db — use tmp_path wiki
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki)])
    # No records yet — should print empty table, not error
    assert result.exit_code == 0


def test_audit_history_json_flag(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_audit_cli.py -v
```
Expected: `FAILED` — `ImportError` or attribute errors (methods don't exist yet).

**Step 3: Add read methods to `AuditDB` in `synthadoc/storage/log.py`**

Add these three methods to the `AuditDB` class:

```python
async def list_ingests(self, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(self._path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT source_path, wiki_page, tokens, cost_usd, ingested_at "
            "FROM ingests ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def list_events(self, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(self._path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT job_id, event, timestamp, metadata "
            "FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def cost_summary(self, days: int = 30) -> dict:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(self._path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT SUM(tokens) as total_tokens, SUM(cost_usd) as total_cost_usd, "
            "DATE(ingested_at) as day, SUM(cost_usd) as day_cost "
            "FROM ingests WHERE ingested_at >= ? GROUP BY day ORDER BY day DESC",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

    total_tokens = 0
    total_cost = 0.0
    daily = []
    for r in rows:
        rd = dict(r)
        total_tokens += rd.get("total_tokens") or 0
        total_cost += rd.get("total_cost_usd") or 0.0
        daily.append({"day": rd["day"], "cost_usd": rd.get("day_cost") or 0.0})

    return {"total_tokens": total_tokens, "total_cost_usd": total_cost, "daily": daily}
```

**Step 4: Create `synthadoc/cli/audit.py`**

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from synthadoc.cli.install import resolve_wiki_path

audit_app = typer.Typer(name="audit", help="Inspect ingest history and costs.")
console = Console()


def _get_audit_db(wiki: Optional[str]):
    from synthadoc.storage.log import AuditDB
    root = resolve_wiki_path(wiki) if wiki else Path(".")
    return AuditDB(root / ".synthadoc" / "audit.db"), root


@audit_app.command("history")
def history_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent ingest history."""
    db, _ = _get_audit_db(wiki)
    records = asyncio.run(_fetch_history(db, limit))
    if as_json:
        typer.echo(json.dumps(records, indent=2))
        return
    table = Table(title=f"Ingest History (last {limit})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Source")
    table.add_column("Wiki Page", style="cyan")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")
    for r in records:
        table.add_row(
            r.get("ingested_at", "")[:16],
            Path(r.get("source_path", "")).name,
            r.get("wiki_page", ""),
            str(r.get("tokens") or 0),
            f"${r.get('cost_usd') or 0:.4f}",
        )
    console.print(table)


@audit_app.command("cost")
def cost_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    days: int = typer.Option(30, "--days"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show token and cost summary."""
    db, _ = _get_audit_db(wiki)
    summary = asyncio.run(_fetch_cost(db, days))
    if as_json:
        typer.echo(json.dumps(summary, indent=2))
        return
    console.print(f"\n[bold]Cost summary — last {days} days[/bold]")
    console.print(f"  Total tokens : {summary['total_tokens']:,}")
    console.print(f"  Total cost   : ${summary['total_cost_usd']:.4f}")
    if summary["daily"]:
        table = Table(title="Daily breakdown")
        table.add_column("Day")
        table.add_column("Cost (USD)", justify="right")
        for row in summary["daily"]:
            table.add_row(row["day"], f"${row['cost_usd']:.4f}")
        console.print(table)


@audit_app.command("events")
def events_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(100, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show raw audit events."""
    db, _ = _get_audit_db(wiki)
    events = asyncio.run(_fetch_events(db, limit))
    if as_json:
        typer.echo(json.dumps(events, indent=2))
        return
    table = Table(title=f"Audit Events (last {limit})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Job ID", style="dim")
    table.add_column("Event", style="cyan")
    table.add_column("Metadata")
    for e in events:
        table.add_row(
            e.get("timestamp", "")[:16],
            e.get("job_id") or "",
            e.get("event", ""),
            e.get("metadata") or "",
        )
    console.print(table)


async def _fetch_history(db, limit):
    await db.init()
    return await db.list_ingests(limit=limit)


async def _fetch_cost(db, days):
    await db.init()
    return await db.cost_summary(days=days)


async def _fetch_events(db, limit):
    await db.init()
    return await db.list_events(limit=limit)
```

**Step 5: Register `audit_app` in `synthadoc/cli/main.py`**

Add to the end of the imports block in `main.py`:
```python
from synthadoc.cli.audit import audit_app  # noqa: F401, E402
app.add_typer(audit_app)
```

**Step 6: Run tests to verify they pass**

```bash
pytest tests/cli/test_audit_cli.py -v
```
Expected: All pass.

**Step 7: Run full test suite**

```bash
pytest tests/ -x -q
```

**Step 8: Commit**

```bash
git add synthadoc/storage/log.py synthadoc/cli/audit.py synthadoc/cli/main.py tests/cli/test_audit_cli.py
git commit -m "feat: add audit CLI commands (history, cost, events)"
```

---

### Task 3: `purpose.md` Scope Filtering

**Files:**
- Modify: `synthadoc/agents/ingest_agent.py`
- Modify: `synthadoc/cli/_init.py`
- Test: `tests/agents/test_ingest_agent.py`

**Background:** If `<wiki_root>/wiki/purpose.md` exists, its content is prepended to the decision prompt as a scope filter. The LLM may respond with `action="skip"` when a source is out of scope. Backward compatible — if the file is absent, behaviour is unchanged.

---

**Step 1: Write the failing tests**

Add to `tests/agents/test_ingest_agent.py`:

```python
@pytest.mark.asyncio
async def test_purpose_md_filters_out_of_scope_source(tmp_wiki, mock_provider):
    """When purpose.md says 'AI only' and LLM returns action=skip, result is skipped."""
    (tmp_wiki / "wiki" / "purpose.md").write_text(
        "This wiki covers AI and machine learning only.", encoding="utf-8")

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta Recipes\nHow to make carbonara.", encoding="utf-8")

    # Override mock: entity response then skip response
    from synthadoc.providers.base import CompletionResponse
    entity_resp = CompletionResponse(
        text='{"entities":["pasta"],"concepts":["cooking"],"tags":["food"]}',
        input_tokens=50, output_tokens=20)
    skip_resp = CompletionResponse(
        text='{"reasoning":"Out of scope","action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=50, output_tokens=20)
    import itertools
    mock_provider.complete.side_effect = itertools.cycle([entity_resp, skip_resp])

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
                        wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.skipped
    assert "scope" in result.skip_reason.lower()


@pytest.mark.asyncio
async def test_purpose_md_absent_does_not_break_ingest(tmp_wiki, mock_provider):
    """No purpose.md — ingest proceeds normally."""
    assert not (tmp_wiki / "wiki" / "purpose.md").exists()
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# AI Safety\nAlignment research.", encoding="utf-8")
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert not result.skipped


def test_init_wiki_creates_purpose_md(tmp_path):
    from synthadoc.cli._init import init_wiki
    init_wiki(tmp_path, domain="AI Research")
    purpose = tmp_path / "wiki" / "purpose.md"
    assert purpose.exists()
    text = purpose.read_text(encoding="utf-8")
    assert "AI Research" in text
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/agents/test_ingest_agent.py::test_purpose_md_filters_out_of_scope_source -v
```
Expected: `FAILED`

**Step 3: Add purpose.md reading to `IngestAgent.__init__`**

In `ingest_agent.py`, add a `_purpose` attribute. In `__init__`, after `self._skill_agent = SkillAgent()`:

```python
self._purpose = self._load_purpose()
```

Add the method:
```python
def _load_purpose(self) -> str:
    """Load wiki/purpose.md content for scope filtering. Returns '' if absent."""
    if self._wiki_root is None:
        return ""
    p = self._wiki_root / "wiki" / "purpose.md"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")[:500]
```

**Step 4: Inject purpose into `_DECISION_PROMPT` at call time**

In the `ingest()` method, change the decision call (currently around line 254) to build the prompt dynamically:

```python
decision_prompt = _DECISION_PROMPT
if self._purpose:
    purpose_block = (
        f"Wiki scope (from purpose.md):\n{self._purpose}\n\n"
        "If the source is clearly outside this scope, respond with action=\"skip\".\n\n"
    )
    decision_prompt = purpose_block + _DECISION_PROMPT

resp2 = await self._provider.complete(
    messages=[Message(role="user", content=decision_prompt.format(
        pages=pages_str,
        summary=text[:1500],
        entities=entities,
    ))],
    temperature=0.0,
)
```

**Step 5: Handle `action="skip"` in the write pass**

In the action dispatch block (around line 272), add before the `if action == "flag"` check:

```python
if action == "skip":
    result.skipped = True
    result.skip_reason = "out of scope (purpose.md)"
    return result
```

**Step 6: Add `purpose.md` starter to `init_wiki()` in `synthadoc/cli/_init.py`**

Add the template constant at the top of the file:
```python
_PURPOSE_MD = """\
# Wiki Purpose

This wiki covers: {domain}.

Include: topics directly related to {domain}.
Exclude: unrelated domains. When in doubt, ingest and review.
"""
```

In `init_wiki()`, after the `index.md` write:
```python
(root / "wiki" / "purpose.md").write_text(
    _PURPOSE_MD.format(domain=domain), encoding="utf-8", newline="\n")
```

**Step 7: Run tests to verify they pass**

```bash
pytest tests/agents/test_ingest_agent.py -v -k "purpose"
```
Expected: All three purpose tests pass.

**Step 8: Run full test suite**

```bash
pytest tests/ -x -q
```

**Step 9: Commit**

```bash
git add synthadoc/agents/ingest_agent.py synthadoc/cli/_init.py tests/agents/test_ingest_agent.py
git commit -m "feat: add purpose.md scope filtering to ingest agent"
```

---

### Task 4: Two-Step Ingest

**Files:**
- Modify: `synthadoc/agents/ingest_agent.py`
- Modify: `synthadoc/integration/http_server.py`
- Modify: `synthadoc/cli/ingest.py`
- Test: `tests/agents/test_ingest_agent.py`

**Background:** Split Pass 1 (entity extraction) into a richer `_analyse()` method that produces entities + tags + a 3-sentence summary. Cache it separately from the decision cache. The decision prompt receives the analysis `summary` rather than raw text. A new `POST /analyse` endpoint and `--analyse-only` CLI flag run Step 1 only without writing pages.

---

**Step 1: Write the failing tests**

Add to `tests/agents/test_ingest_agent.py`:

```python
@pytest.mark.asyncio
async def test_analyse_returns_structured_result(tmp_wiki, mock_provider):
    """_analyse() returns entities, tags, and a summary string."""
    from synthadoc.providers.base import CompletionResponse
    analysis_resp = CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"This source discusses AI safety.","relevant":true}',
        input_tokens=50, output_tokens=20)
    mock_provider.complete.side_effect = [analysis_resp]

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent._analyse("AI safety content here", bust_cache=True)
    assert "entities" in result
    assert "summary" in result
    assert isinstance(result["summary"], str)


@pytest.mark.asyncio
async def test_analyse_is_cached_on_second_call(tmp_wiki):
    """Second call with same text must return cached result with 0 LLM calls."""
    from synthadoc.providers.base import CompletionResponse
    call_count = 0

    async def counting_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(
            text='{"entities":["X"],"tags":[],"summary":"Test.","relevant":true}',
            input_tokens=10, output_tokens=5)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=counting_complete)

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    await agent._analyse("some text", bust_cache=False)
    first_calls = call_count
    await agent._analyse("some text", bust_cache=False)
    assert call_count == first_calls  # second call hits cache
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/agents/test_ingest_agent.py::test_analyse_returns_structured_result -v
```
Expected: `FAILED` — `AttributeError: 'IngestAgent' object has no attribute '_analyse'`

**Step 3: Add `_ANALYSIS_PROMPT` constant and `_analyse()` method to `ingest_agent.py`**

Add after `_ENTITY_PROMPT`:
```python
_ANALYSIS_PROMPT = (
    "Analyse the source text below. Return ONLY valid JSON with no markdown fences:\n"
    '{"entities": [...], "tags": [...], "summary": "One to three sentences describing '
    'the main topic, key claims, and relevance.", "relevant": true}\n\n'
    "Keep entities and tags under 10 items each.\n\n"
)
```

Add method to `IngestAgent` (before `ingest()`):
```python
async def _analyse(self, text: str, bust_cache: bool = False) -> dict:
    """Step 1 — analysis pass: entity extraction + summary. Cached by content hash."""
    import hashlib as _hashlib
    text_hash = _hashlib.sha256(text.encode()).hexdigest()
    ck = make_cache_key("analyse-v1", {"text_hash": text_hash})
    if not bust_cache:
        cached = await self._cache.get(ck)
        if cached:
            return cached
    resp = await self._provider.complete(
        messages=[Message(role="user", content=f"{_ANALYSIS_PROMPT}{text[:3000]}")],
        temperature=0.0,
    )
    data = _parse_json_response(resp.text)
    # Ensure required keys exist with safe defaults
    data.setdefault("entities", [])
    data.setdefault("tags", [])
    data.setdefault("summary", text[:200])
    data.setdefault("relevant", True)
    data["_tokens"] = resp.total_tokens
    await self._cache.set(ck, data)
    return data
```

**Step 4: Refactor `ingest()` to use `_analyse()`**

In `ingest()`, replace Pass 1 (entity extraction, approx lines 203-231) with:

```python
# Step 1: analysis pass (cached separately from decision)
analysis = await self._analyse(text, bust_cache=bust_cache)
result.tokens_used += analysis.pop("_tokens", 0)
if analysis.get("_cache_hit"):
    result.cache_hits += 1

entities = analysis.get("entities", [])
tags = analysis.get("tags", [])
summary = analysis.get("summary", text[:1500])

# Fallback entity extraction if LLM returned nothing
if not entities:
    english = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', text[:2000])
    cjk = re.findall(
        r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]{2,6}',
        text[:2000])
    entities = list(dict.fromkeys(english + cjk))[:12]
```

Then update Pass 3 (decision prompt) to use `summary` from analysis instead of `text[:1500]`:
```python
resp2 = await self._provider.complete(
    messages=[Message(role="user", content=decision_prompt.format(
        pages=pages_str,
        summary=summary,        # ← was text[:1500]
        entities=entities,
    ))],
    temperature=0.0,
)
```

**Step 5: Add `POST /analyse` endpoint to `http_server.py`**

Add after the `QueryRequest` model:
```python
class AnalyseRequest(BaseModel):
    source: str

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v):
        if not v.strip():
            raise ValueError("source must not be empty")
        return v
```

Add after the `/query` endpoints:
```python
@app.post("/analyse")
async def analyse_source(req: AnalyseRequest):
    """Run Step 1 analysis on a source and return structured result without writing pages."""
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.providers import make_provider
    orch = app.state.orch
    agent = IngestAgent(
        provider=make_provider("ingest", orch._cfg),
        store=orch._store, search=orch._search,
        log_writer=orch._log, audit_db=orch._audit,
        cache=orch._cache, max_pages=orch._cfg.ingest.max_pages_per_ingest,
        wiki_root=orch._root,
    )
    from synthadoc.skills.skill_agent import SkillAgent
    skill = SkillAgent()
    extracted = await skill.extract(req.source)
    text = extracted.text[:8000]
    analysis = await agent._analyse(text, bust_cache=False)
    analysis.pop("_tokens", None)
    return {"source": req.source, "analysis": analysis}
```

Also add `GET /analyse` endpoint listing in the `index()` response:
```python
f"  POST /analyse         analyse source without writing pages\n"
```

**Step 6: Add `--analyse-only` flag to `synthadoc/cli/ingest.py`**

Add parameter to `ingest_cmd`:
```python
analyse_only: bool = typer.Option(False, "--analyse-only",
    help="Run analysis pass only; print result without writing wiki pages."),
```

In the loop over sources, before the existing `post()` call:
```python
if analyse_only:
    result = post(wiki, "/analyse", {"source": s}, method="POST")
    import json as _json
    typer.echo(_json.dumps(result, indent=2))
    continue
```

Then in `synthadoc/cli/_http.py`, verify `post()` works for all endpoints (no change needed if it's generic).

**Step 7: Run tests to verify they pass**

```bash
pytest tests/agents/test_ingest_agent.py -v -k "analyse"
```
Expected: Both analyse tests pass.

**Step 8: Run full test suite**

```bash
pytest tests/ -x -q
```

**Step 9: Commit**

```bash
git add synthadoc/agents/ingest_agent.py synthadoc/integration/http_server.py synthadoc/cli/ingest.py tests/agents/test_ingest_agent.py
git commit -m "feat: two-step ingest with cached analysis pass and --analyse-only flag"
```

---

### Task 5: `overview.md` Auto-Summary

**Files:**
- Modify: `synthadoc/agents/ingest_agent.py`
- Test: `tests/agents/test_ingest_agent.py`

**Background:** After any ingest that creates or updates at least one page, call `_update_overview()`. It reads the 10 most-recently-modified wiki pages, asks the LLM for a 2-paragraph overview, and writes it to `wiki/overview.md`. Skipped on flag-only and skip results.

---

**Step 1: Write the failing tests**

Add to `tests/agents/test_ingest_agent.py`:

```python
@pytest.mark.asyncio
async def test_overview_md_created_after_ingest(tmp_wiki, mock_provider):
    """overview.md must be written after a successful page creation."""
    from synthadoc.providers.base import CompletionResponse
    import itertools

    entity_resp = CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"AI safety research.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"New topic","action":"create","target":"","new_slug":"ai-safety","update_content":""}',
        input_tokens=50, output_tokens=20)
    overview_resp = CompletionResponse(
        text="This wiki covers AI safety research.\n\nKey themes include alignment and interpretability.",
        input_tokens=50, output_tokens=30)

    mock_provider.complete.side_effect = itertools.cycle(
        [entity_resp, decision_resp, overview_resp])

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "ai.md"
    source.write_text("# AI Safety\nAlignment is important.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.pages_created
    overview = tmp_wiki / "wiki" / "overview.md"
    assert overview.exists(), "overview.md should be created after page creation"
    text = overview.read_text(encoding="utf-8")
    assert "overview" in text.lower() or "wiki" in text.lower()


@pytest.mark.asyncio
async def test_overview_md_not_written_on_skip(tmp_wiki, mock_provider):
    """overview.md must NOT be written when ingest is skipped."""
    from synthadoc.providers.base import CompletionResponse
    import itertools

    entity_resp = CompletionResponse(
        text='{"entities":[],"tags":[],"summary":"Out of scope.","relevant":false}',
        input_tokens=10, output_tokens=5)
    skip_resp = CompletionResponse(
        text='{"action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=10, output_tokens=5)
    mock_provider.complete.side_effect = itertools.cycle([entity_resp, skip_resp])

    (tmp_wiki / "wiki" / "purpose.md").write_text("AI only.", encoding="utf-8")
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta\nHow to cook.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    await agent.ingest(str(source))
    assert not (tmp_wiki / "wiki" / "overview.md").exists()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/agents/test_ingest_agent.py::test_overview_md_created_after_ingest -v
```
Expected: `FAILED`

**Step 3: Add `_OVERVIEW_PROMPT` and `_update_overview()` to `ingest_agent.py`**

Add constant after `_VISION_PROMPT`:
```python
_OVERVIEW_PROMPT = (
    "Write a 2-paragraph overview of a knowledge wiki based on the page titles and "
    "excerpts below.\n"
    "First paragraph: what topics this wiki covers.\n"
    "Second paragraph: key themes and concepts found.\n"
    "Keep it under 200 words. Plain text only — no markdown headings.\n\n"
    "Pages:\n{pages}"
)
```

Add method to `IngestAgent`:
```python
async def _update_overview(self) -> None:
    """Regenerate wiki/overview.md from the 10 most-recently-modified pages."""
    if self._wiki_root is None:
        return
    wiki_dir = self._wiki_root / "wiki"
    pages = sorted(
        [p for p in wiki_dir.glob("*.md")
         if p.stem not in {"overview", "index", "dashboard", "log"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    if not pages:
        return
    page_ctx = []
    for p in pages:
        text = p.read_text(encoding="utf-8")
        snippet = text[:200].replace("\n", " ")
        page_ctx.append(f"- {p.stem}: {snippet}")
    pages_str = "\n".join(page_ctx)
    resp = await self._provider.complete(
        messages=[Message(role="user",
                          content=_OVERVIEW_PROMPT.format(pages=pages_str))],
        temperature=0.3,
        max_tokens=512,
    )
    from datetime import date as _date
    overview_path = wiki_dir / "overview.md"
    content = (
        f"---\ntitle: Wiki Overview\nstatus: auto\nupdated: {_date.today().isoformat()}\n---\n\n"
        f"# Wiki Overview\n\n{resp.text.strip()}\n"
    )
    overview_path.write_text(content, encoding="utf-8", newline="\n")
```

**Step 4: Call `_update_overview()` after successful writes**

At the end of `ingest()`, before `self._log.log_ingest(...)`, add:

```python
if result.pages_created or result.pages_updated:
    await self._update_overview()
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/agents/test_ingest_agent.py -v -k "overview"
```
Expected: Both overview tests pass.

**Step 6: Run full test suite**

```bash
pytest tests/ -x -q
```

**Step 7: Commit**

```bash
git add synthadoc/agents/ingest_agent.py tests/agents/test_ingest_agent.py
git commit -m "feat: auto-generate overview.md after each ingest that creates or updates pages"
```

---

### Task 6: Web Search Skill (Tavily)

**Files:**
- Modify: `pyproject.toml`
- Modify: `synthadoc/config.py`
- Modify: `synthadoc/skills/web_search/scripts/main.py`
- Modify: `synthadoc/skills/web_search/scripts/fetcher.py`
- Modify: `synthadoc/skills/web_search/assets/search-providers.json`
- Modify: `synthadoc/skills/web_search/SKILL.md`
- Modify: `synthadoc/agents/ingest_agent.py`
- Modify: `synthadoc/core/orchestrator.py`
- Modify: `synthadoc/cli/serve.py`
- Test: `tests/skills/test_web_search.py` (create new)
- Test: `tests/performance/test_performance.py`

**Background:**
- `WebSearchSkill.extract()` calls Tavily, returns `ExtractedContent` with `metadata["child_sources"] = [list of URLs]`.
- `IngestAgent.ingest()` detects `child_sources` and returns early with `IngestResult(child_sources=[...])`.
- `Orchestrator._run_ingest()` sees `result.child_sources` and enqueues each as a new ingest job.
- API key: `TAVILY_API_KEY` env var (checked at serve startup).
- `max_results` config: stored in `WebSearchConfig`, surfaced to skill via `SYNTHADOC_WEB_SEARCH_MAX_RESULTS` env var set by orchestrator.

---

**Step 1: Add `tavily-python` to `pyproject.toml`**

In the `dependencies` list, add:
```toml
"tavily-python>=0.5",
```

**Step 2: Add `WebSearchConfig` to `synthadoc/config.py`**

Add the dataclass:
```python
@dataclass
class WebSearchConfig:
    provider: str = "tavily"
    max_results: int = 20
```

Add to `Config`:
```python
web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
```

Add parsing in `_raw_to_config()` before the return statement:
```python
ws = raw.get("web_search", {})
web_search = WebSearchConfig(
    provider=ws.get("provider", "tavily"),
    max_results=ws.get("max_results", 20),
)
```

Update the `Config(...)` constructor call to include `web_search=web_search`.

Also update the bare default Config at the bottom of `load_config()`:
```python
return Config(
    agents=AgentsConfig(default=AgentConfig(provider="anthropic", model="claude-opus-4-6")),
    web_search=WebSearchConfig(),
)
```

**Step 3: Write the failing tests**

Create `tests/skills/test_web_search.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_tavily_response(n: int = 3) -> dict:
    return {
        "results": [
            {"url": f"https://example.com/article-{i}", "content": f"Content {i}",
             "title": f"Article {i}"}
            for i in range(n)
        ]
    }


@pytest.mark.asyncio
async def test_web_search_extract_returns_child_sources(monkeypatch):
    """WebSearchSkill.extract() must return child_sources URLs from Tavily."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", "5")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    skill = WebSearchSkill()

    mock_response = _make_tavily_response(3)
    with patch("synthadoc.skills.web_search.scripts.fetcher.search_tavily",
               new=AsyncMock(return_value=mock_response)):
        result = await skill.extract("search for: quantum computing")

    assert result.metadata.get("child_sources") is not None
    assert len(result.metadata["child_sources"]) == 3
    assert all(u.startswith("https://") for u in result.metadata["child_sources"])
    assert result.text == ""  # parent job has no text; child jobs handle ingestion


@pytest.mark.asyncio
async def test_web_search_extracts_query_from_intent(monkeypatch):
    """Query extracted from 'search for: <query>' prefix."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", "5")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured_query = []

    async def capture_search(query, max_results, api_key):
        captured_query.append(query)
        return _make_tavily_response(1)

    with patch.object(fetcher, "search_tavily", side_effect=capture_search):
        skill = WebSearchSkill()
        await skill.extract("search for: Dennis Ritchie contributions to computing")

    assert len(captured_query) == 1
    assert "Dennis Ritchie" in captured_query[0]
    assert "search for:" not in captured_query[0]


@pytest.mark.asyncio
async def test_web_search_respects_max_results(monkeypatch):
    """max_results from env var is passed to Tavily."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", "7")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured = []

    async def capture(query, max_results, api_key):
        captured.append(max_results)
        return _make_tavily_response(7)

    with patch.object(fetcher, "search_tavily", side_effect=capture):
        skill = WebSearchSkill()
        await skill.extract("search for: test query")

    assert captured[0] == 7


def test_ingest_result_has_child_sources_field():
    """IngestResult must have a child_sources field."""
    from synthadoc.agents.ingest_agent import IngestResult
    r = IngestResult(source="search for: test")
    assert hasattr(r, "child_sources")
    assert r.child_sources == []


@pytest.mark.asyncio
async def test_ingest_agent_returns_child_sources_for_web_search(tmp_wiki, monkeypatch):
    """When extract() returns child_sources, ingest() returns them without LLM calls."""
    from unittest.mock import AsyncMock
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    provider = AsyncMock()
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    child_urls = ["https://example.com/a", "https://example.com/b"]
    mock_extracted = ExtractedContent(
        text="", source_path="search for: test",
        metadata={"child_sources": child_urls})

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("search for: test")

    assert result.child_sources == child_urls
    provider.complete.assert_not_called()  # no LLM calls for parent web search job
```

**Step 4: Run tests to verify they fail**

```bash
pytest tests/skills/test_web_search.py -v
```
Expected: `FAILED` — ImportError or NotImplementedError

**Step 5: Implement `fetcher.py`**

Replace `synthadoc/skills/web_search/scripts/fetcher.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Tavily search client wrapper for web_search skill."""
from __future__ import annotations


async def search_tavily(query: str, max_results: int, api_key: str) -> dict:
    """Call Tavily search API and return raw response dict."""
    from tavily import AsyncTavilyClient
    client = AsyncTavilyClient(api_key=api_key)
    return await client.search(query, max_results=max_results)
```

**Step 6: Implement `WebSearchSkill.extract()` in `main.py`**

Replace `synthadoc/skills/web_search/scripts/main.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
from synthadoc.skills.base import BaseSkill, ExtractedContent

_INTENT_PREFIX = "search for:"
_DEFAULT_MAX_RESULTS = 20


class WebSearchSkill(BaseSkill):
    async def extract(self, source: str) -> ExtractedContent:
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "TAVILY_API_KEY is not set. Get a free key at https://tavily.com "
                "and set it with: export TAVILY_API_KEY=<your-key>"
            )
        max_results = int(
            os.environ.get("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", _DEFAULT_MAX_RESULTS)
        )
        query = source
        lower = source.lower()
        if lower.startswith(_INTENT_PREFIX):
            query = source[len(_INTENT_PREFIX):].strip()

        from synthadoc.skills.web_search.scripts.fetcher import search_tavily
        response = await search_tavily(query, max_results=max_results, api_key=api_key)

        child_sources = [
            r["url"] for r in response.get("results", [])
            if r.get("url")
        ]
        return ExtractedContent(
            text="",
            source_path=source,
            metadata={
                "child_sources": child_sources,
                "query": query,
                "results_count": len(child_sources),
            },
        )
```

**Step 7: Update `search-providers.json`**

```json
{
  "_comment": "Search provider configuration",
  "providers": [
    {
      "name": "tavily",
      "api_key_env": "TAVILY_API_KEY",
      "free_tier": true,
      "free_limit": "1000 searches/month",
      "signup_url": "https://tavily.com"
    }
  ]
}
```

**Step 8: Update `SKILL.md` for web_search**

Remove "v2 feature" notice. Update description to reflect Tavily. (Read the existing file first, then edit the relevant lines.)

**Step 9: Add `child_sources` to `IngestResult` in `ingest_agent.py`**

Change `IngestResult`:
```python
@dataclass
class IngestResult:
    source: str
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    pages_flagged: list[str] = field(default_factory=list)
    child_sources: list[str] = field(default_factory=list)   # ← add this
    tokens_used: int = 0
    cost_usd: float = 0.0
    cache_hits: int = 0
    skipped: bool = False
    skip_reason: str = ""
```

**Step 10: Handle `child_sources` in `ingest()` after `skill_agent.extract()`**

After `extracted = await self._skill_agent.extract(source)`, add:

```python
# Web search fan-out: return child sources immediately; orchestrator enqueues them
if extracted.metadata.get("child_sources"):
    result.child_sources = extracted.metadata["child_sources"]
    return result
```

**Step 11: Handle `child_sources` in `Orchestrator._run_ingest()`**

In `synthadoc/core/orchestrator.py`, in `_run_ingest()` after `await self._queue.complete(job_id, result={...})`:

```python
# Fan out child sources from web search
for child_source in result.child_sources:
    await self._queue.enqueue("ingest", {"source": child_source, "force": False})
```

Also add `child_sources` to the complete result dict:
```python
await self._queue.complete(job_id, result={
    "pages_created": result.pages_created,
    "pages_updated": result.pages_updated,
    "pages_flagged": result.pages_flagged,
    "child_sources_enqueued": len(result.child_sources),
    "tokens_used": result.tokens_used,
    "cost_usd": result.cost_usd,
})
```

**Step 12: Add Tavily key check to `serve.py`**

In the serve pre-flight block, after the existing provider key checks, add:

```python
import os as _os
if cfg.web_search.provider == "tavily" and not _os.environ.get("TAVILY_API_KEY"):
    typer.echo(
        "Warning: TAVILY_API_KEY is not set. Web search jobs will fail.\n"
        "Get a free key at https://tavily.com",
        err=True,
    )
```

Also set the max_results env var so the skill reads it from config:
```python
_os.environ.setdefault(
    "SYNTHADOC_WEB_SEARCH_MAX_RESULTS",
    str(cfg.web_search.max_results)
)
```

**Step 13: Run skill tests to verify they pass**

```bash
pytest tests/skills/test_web_search.py -v
```
Expected: All 5 tests pass.

**Step 14: Add web search performance benchmark to `tests/performance/test_performance.py`**

```python
@pytest.mark.asyncio
async def test_web_search_fanout_enqueue_is_fast(tmp_wiki, monkeypatch):
    """Enqueueing 20 web search child jobs must complete in < 5 seconds."""
    import time
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", "20")

    from synthadoc.skills.base import ExtractedContent
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager
    from unittest.mock import AsyncMock, patch

    provider = AsyncMock()
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    child_urls = [f"https://example.com/article-{i}" for i in range(20)]
    mock_extracted = ExtractedContent(
        text="", source_path="search for: benchmark test",
        metadata={"child_sources": child_urls})

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    start = time.perf_counter()
    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("search for: benchmark test")
    elapsed = time.perf_counter() - start

    assert result.child_sources == child_urls
    assert elapsed < 5.0, f"Fan-out took {elapsed:.2f}s — expected < 5s"
```

**Step 15: Run full test suite**

```bash
pytest tests/ -x -q
```
Expected: All pass.

**Step 16: Install new dependency**

```bash
pip install tavily-python
```

**Step 17: Commit**

```bash
git add pyproject.toml synthadoc/config.py synthadoc/skills/web_search/ synthadoc/agents/ingest_agent.py synthadoc/core/orchestrator.py synthadoc/cli/serve.py tests/skills/test_web_search.py tests/performance/test_performance.py
git commit -m "feat: implement Tavily web search skill with child job fan-out"
```

---

## Final Verification

After all 6 tasks are complete:

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All tests pass. Then push to remote and open PR.

```bash
git push origin pdev1
```
