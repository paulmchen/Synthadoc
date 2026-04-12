# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
from synthadoc.skills.base import BaseSkill, ExtractedContent

import re

# Matches all intents declared in SKILL.md; colon and leading whitespace optional
_INTENT_RE = re.compile(
    r"^(search\s+for|find\s+on\s+the\s+web|look\s+up|web\s+search|browse):?\s*",
    re.IGNORECASE,
)
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
        query = _INTENT_RE.sub("", source).strip() or source

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
