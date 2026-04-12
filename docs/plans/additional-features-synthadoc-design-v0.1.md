# Synthadoc v0.1 Additional Features — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add six features to the v0.1 release: web search via Tavily, two-step ingest with analysis caching, purpose.md scope filtering, overview.md auto-summary, multi-provider LLM support (Gemini + Groq), and audit CLI commands.

**Architecture:** All features extend the existing ingest pipeline, provider abstraction, and CLI module pattern without breaking backward compatibility. Web search fans out to the existing job queue. Multi-provider reuses `OpenAIProvider` with a `base_url` override for OpenAI-compatible APIs.

**Tech Stack:** Python 3.11+, Tavily Python SDK, OpenAI SDK (already present), Typer + Rich for CLI, aiosqlite for audit reads.

---

## Feature 1 — Web Search Skill (Tavily)

### Overview

The intent trigger `search for: <query>` already routes to `WebSearchSkill` via the skill registry. The `extract()` method currently raises `NotImplementedError`. This feature implements it.

### Flow

1. `WebSearchSkill.extract("search for: quantum computing 2025")` is called by the ingest pipeline.
2. It calls the Tavily API with the cleaned query string, requesting up to `max_results` results.
3. For each result URL, it enqueues a new `ingest` child job via the orchestrator's queue.
4. The parent job returns immediately with a summary payload: `{"search_jobs_enqueued": N, "query": "..."}`.
5. Each child job is a standard ingest job — URL/PDF/image skills handle extraction as normal.

### Configuration

New `[web_search]` section in `.synthadoc/config.toml`:

```toml
[web_search]
provider = "tavily"   # "brave" also supported in future
max_results = 20
```

Environment variable: `TAVILY_API_KEY` (checked at serve startup, same pattern as `ANTHROPIC_API_KEY`).

### New Dependency

`tavily-python>=0.3` added to `pyproject.toml` core dependencies.

### Files Changed

- `synthadoc/skills/web_search/scripts/main.py` — implement `extract()`; call Tavily, fan-out to queue
- `synthadoc/skills/web_search/scripts/fetcher.py` — Tavily client wrapper (thin; most logic is in `main.py`)
- `synthadoc/skills/web_search/assets/search-providers.json` — add Tavily entry
- `synthadoc/config.py` — add `WebSearchConfig` dataclass; parse `[web_search]` section; add to `Config`
- `synthadoc/cli/serve.py` — add `TAVILY_API_KEY` pre-flight check when provider is `tavily`
- `pyproject.toml` — add `tavily-python>=0.3`

### Performance Test

`tests/benchmark/test_web_search_perf.py` — mock Tavily response (20 results) + mock LLM provider; measure wall-clock time for full fan-out. Baseline target: < 5s for enqueue phase (LLM calls happen asynchronously in worker).

### Skill Metadata Update

`synthadoc/skills/web_search/SKILL.md` — remove "v2 feature" notice; update description to reflect Tavily.

---

## Feature 2 — Two-Step Ingest

### Overview

The current single-pass ingest combines entity extraction and page decision in one flow. Two-step separates these into:

- **Step 1 — Analysis pass:** entity extraction + 3-sentence source summary + relevance flag. Cached independently by content hash.
- **Step 2 — Generation pass:** uses cached analysis as input to the decision prompt. Writes pages.

The analysis cache is keyed separately from the decision cache so a re-ingest with the same source can skip Step 1 entirely.

### New Method: `_analyse()`

```python
async def _analyse(self, text: str, bust_cache: bool = False) -> dict:
    """Run Step 1: entity extraction + summary. Returns cached result if available."""
```

Returns:
```json
{
  "entities": [...],
  "tags": [...],
  "summary": "Three-sentence description of the source content.",
  "relevant": true
}
```

### Decision Prompt Change

`_DECISION_PROMPT` receives `summary` from analysis instead of raw `text[:1500]`. This produces more consistent decisions and reduces token usage in Step 2.

### New CLI Flag

`synthadoc ingest --analyse-only <source>` — runs Step 1 only, prints analysis JSON to stdout, no wiki writes. Useful for previewing what Synthadoc thinks a source contains before committing.

### Files Changed

- `synthadoc/agents/ingest_agent.py` — add `_analyse()` method; refactor `ingest()` to call it; update `_DECISION_PROMPT` to use `{summary}` instead of raw text
- `synthadoc/cli/ingest.py` — add `--analyse-only` flag

---

## Feature 3 — `purpose.md`

### Overview

A user-authored file at `<wiki_root>/wiki/purpose.md` declares the wiki's scope. The ingest agent reads it once per instantiation and prepends it to the decision prompt as a scope filter. A new `action = "skip"` response from the LLM marks the job as skipped (not failed).

### purpose.md Format

Plain markdown. The ingest agent reads the full content (up to 500 chars); no special structure required.

### Starter Template (created by `synthadoc install`)

```markdown
# Wiki Purpose

This wiki covers [describe your domain here].

Include: [topics to include]
Exclude: [topics to exclude]
```

### Decision Prompt Addition

```
Wiki scope (purpose.md):
{purpose}

If the source is clearly outside this scope, respond with action="skip".
```

### Backward Compatibility

If `purpose.md` does not exist, the prompt addition is omitted and behaviour is identical to v0.1 baseline.

### Files Changed

- `synthadoc/agents/ingest_agent.py` — read `purpose.md` in `__init__`; inject into `_DECISION_PROMPT`; handle `action="skip"` in write pass
- `synthadoc/cli/_init.py` (install scaffold) — create starter `purpose.md`
- `synthadoc/cli/install.py` — pass `wiki_root` to scaffold so `purpose.md` lands in `wiki/`

---

## Feature 4 — `overview.md`

### Overview

An auto-maintained wiki page at `<wiki_root>/wiki/overview.md`. Updated after any ingest that creates or updates at least one page. Summarises the wiki's current coverage based on the 10 most-recently-modified pages.

### Update Logic

After the write pass in `ingest_agent.py`:

```python
if result.pages_created or result.pages_updated:
    await self._update_overview()
```

`_update_overview()`:
1. List all pages, sort by `mtime`, take top 10.
2. Collect title + first 200 chars of each.
3. Call LLM: "Write a 2-paragraph overview of this wiki's current coverage based on these pages."
4. Write result to `wiki/overview.md` with frontmatter `title: Wiki Overview`, `status: auto`.

### Frontmatter

```yaml
---
title: Wiki Overview
status: auto
updated: 2026-04-11
---
```

### Performance Note

`_update_overview()` adds one LLM call per ingest that produces changes. It is skipped on flag-only and skip ingests. The call uses the ingest provider (same model, same cost bucket).

### Files Changed

- `synthadoc/agents/ingest_agent.py` — add `_update_overview()` method; call after successful writes
- `synthadoc/cli/_init.py` — do NOT pre-create `overview.md` at install (auto-generated on first ingest)

---

## Feature 5 — Multi-Provider LLM (Gemini + Groq)

### Overview

Both Gemini and Groq expose OpenAI-compatible REST APIs. The existing `OpenAIProvider` is reused with a `base_url` override — no new provider class required.

### Config Changes

`AgentConfig` gains an optional `base_url: str = ""` field. When non-empty, it is passed to `AsyncOpenAI(base_url=base_url)`.

`KNOWN_PROVIDERS` expands to:
```python
KNOWN_PROVIDERS = {"anthropic", "openai", "ollama", "gemini", "groq"}
```

### Provider Routing in `make_provider()`

```python
if name == "gemini":
    key = _require_env("GEMINI_API_KEY", "Google Gemini", "https://aistudio.google.com/app/apikey")
    cfg_with_url = AgentConfig(provider="gemini", model=agent_cfg.model,
                               base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    return OpenAIProvider(api_key=key, config=cfg_with_url)

if name == "groq":
    key = _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys")
    cfg_with_url = AgentConfig(provider="groq", model=agent_cfg.model,
                               base_url="https://api.groq.com/openai/v1")
    return OpenAIProvider(api_key=key, config=cfg_with_url)
```

### serve.py Pre-flight

Add `gemini` and `groq` branches to the provider key check block, matching the existing `anthropic`/`openai` pattern.

### Recommended Free Models

| Provider | Free model | Notes |
|---------|-----------|-------|
| Gemini | `gemini-2.0-flash` | 15 RPM, 1M tokens/day free |
| Groq | `llama-3.3-70b-versatile` | 30 RPM free tier |

### Files Changed

- `synthadoc/config.py` — add `base_url` to `AgentConfig`; expand `KNOWN_PROVIDERS`
- `synthadoc/providers/openai.py` — pass `base_url` to `AsyncOpenAI` when set
- `synthadoc/providers/__init__.py` — add `gemini` and `groq` branches in `make_provider()`
- `synthadoc/cli/serve.py` — add pre-flight key checks for `gemini` and `groq`

---

## Feature 6 — Audit CLI Commands

### Overview

Replace raw SQLite access with three commands under `synthadoc audit`. All read from the existing `AuditDB` schema; no schema changes required.

### Commands

```
synthadoc audit history [--limit 50] [--json]
    Table: ingested_at | source | wiki_page | tokens | cost_usd

synthadoc audit cost [--days 30] [--json]
    Aggregate: total_tokens | total_cost_usd | daily breakdown table

synthadoc audit events [--limit 100] [--json]
    Table: timestamp | job_id | event | metadata
```

### Output Format

Default: `rich.table.Table` for human reading.
`--json` flag: prints a JSON array to stdout (for scripting or export).

### New AuditDB Read Methods

```python
async def list_ingests(self, limit: int = 50) -> list[dict]: ...
async def list_events(self, limit: int = 100) -> list[dict]: ...
async def cost_summary(self, days: int = 30) -> dict: ...
```

### Files Changed

- `synthadoc/storage/log.py` — add `list_ingests()`, `list_events()`, `cost_summary()` to `AuditDB`
- `synthadoc/cli/audit.py` — new file; three commands; registered in `main.py`
- `synthadoc/cli/main.py` — import `audit` module

---

## Testing Strategy

| Feature | Test file |
|---------|-----------|
| Web search (unit) | `tests/test_web_search_skill.py` — mock Tavily; assert child jobs enqueued |
| Web search (perf) | `tests/benchmark/test_web_search_perf.py` — 20-result fan-out timing |
| Two-step ingest | `tests/test_ingest_agent.py` — extend existing; assert analysis cached separately; `--analyse-only` returns no writes |
| purpose.md | `tests/test_ingest_agent.py` — assert out-of-scope source returns `skipped=True` |
| overview.md | `tests/test_ingest_agent.py` — assert overview written after create; not written after flag-only |
| Multi-provider | `tests/test_providers.py` — assert Gemini/Groq map to OpenAIProvider with correct base_url |
| Audit CLI | `tests/test_audit_cli.py` — assert table output + JSON flag for all three commands |

---

## Rollout Order (for implementation plan)

1. Multi-provider (isolated, no dependencies on other features)
2. Audit CLI (isolated)
3. purpose.md (small ingest change)
4. Two-step ingest (builds on ingest agent)
5. overview.md (builds on two-step ingest)
6. Web search skill (builds on config + queue fan-out)
