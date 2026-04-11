# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from synthadoc.storage.wiki import WikiStorage


@dataclass
class SearchResult:
    slug: str
    score: float
    title: str
    snippet: str


class HybridSearch:
    """BM25 full-text search. Vector re-ranking added in a future task."""

    def __init__(self, store: WikiStorage, index_path: Path) -> None:
        self._store = store
        self._index_path = index_path

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split into BM25 tokens. ASCII words + individual CJK characters (no word boundaries in CJK)."""
        ascii_tokens = re.findall(r"[a-z0-9]+", text.lower())
        cjk_tokens = re.findall(
            r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]", text
        )
        return ascii_tokens + cjk_tokens

    def _corpus(self) -> tuple[list[str], list[list[str]]]:
        slugs = self._store.list_pages()
        tokenized = []
        for slug in slugs:
            page = self._store.read_page(slug)
            text = f"{page.title} {' '.join(page.tags)} {page.content}" if page else ""
            tokenized.append(self._tokenize(text))
        return slugs, tokenized

    def bm25_search(self, query_terms: list[str], top_n: int = 10) -> list[SearchResult]:
        slugs, corpus = self._corpus()
        if not corpus:
            return []
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(self._tokenize(" ".join(query_terms)))
        ranked = sorted(zip(slugs, scores), key=lambda x: x[1], reverse=True)
        results = []
        for slug, score in ranked[:top_n]:
            if score <= 0:
                continue
            page = self._store.read_page(slug)
            snippet = (page.content[:120] + "...") if page and len(page.content) > 120 \
                      else (page.content if page else "")
            results.append(SearchResult(
                slug=slug, score=float(score),
                title=page.title if page else slug,
                snippet=snippet,
            ))
        return results

    def hybrid_search(self, query_terms: list[str], top_n: int = 10) -> list[SearchResult]:
        """BM25 for now; vector re-ranking added later."""
        return self.bm25_search(query_terms, top_n=top_n)
