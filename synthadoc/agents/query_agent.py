# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
from dataclasses import dataclass, field

from synthadoc.core.cache import CacheManager
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage


@dataclass
class QueryResult:
    question: str
    answer: str
    citations: list[str]
    tokens_used: int = 0


class QueryAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 search: HybridSearch, cache: CacheManager, top_n: int = 8) -> None:
        self._provider = provider
        self._store = store
        self._search = search
        self._cache = cache
        self._top_n = top_n

    async def query(self, question: str) -> QueryResult:
        resp = await self._provider.complete(
            messages=[Message(role="user",
                content=f"Extract 5-8 key search terms from: {question}\n"
                        "Return JSON array of strings only.")],
            temperature=0.0,
        )
        try:
            terms = json.loads(resp.text)
        except json.JSONDecodeError:
            terms = question.split()

        candidates = self._search.bm25_search(terms, top_n=self._top_n)
        citations = [r.slug for r in candidates]
        context = "\n\n".join(
            f"### {p.title}\n{p.content[:1000]}"
            for r in candidates
            if (p := self._store.read_page(r.slug))
        ) or "No relevant pages found."

        resp2 = await self._provider.complete(
            messages=[Message(role="user",
                content=f"Answer using ONLY these wiki pages. Cite with [[PageTitle]].\n\n"
                        f"Question: {question}\n\nPages:\n{context}")],
            temperature=0.0,
        )
        return QueryResult(question=question, answer=resp2.text, citations=citations,
                           tokens_used=resp.total_tokens + resp2.total_tokens)
