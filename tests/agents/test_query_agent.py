# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.query_agent import QueryAgent, QueryResult
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch
from synthadoc.core.cache import CacheManager


@pytest.mark.asyncio
async def test_query_returns_answer(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("transformers", WikiPage(title="Transformers", tags=["ai"],
        content="Transformers use self-attention.", status="active",
        confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Transformers use self-attention.", input_tokens=200, output_tokens=30)
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("How do transformers work?")
    assert isinstance(result, QueryResult)
    assert result.answer
