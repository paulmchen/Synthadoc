# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.core.cache import CacheManager, make_cache_key, CACHE_VERSION


@pytest.mark.asyncio
async def test_miss_returns_none(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_set_and_get(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    await cache.set("k1", {"result": "Paris"})
    result = await cache.get("k1")
    assert result["result"] == "Paris"


def test_cache_key_deterministic():
    k1 = make_cache_key("op", {"text": "hello"})
    k2 = make_cache_key("op", {"text": "hello"})
    k3 = make_cache_key("op", {"text": "world"})
    assert k1 == k2
    assert k1 != k3


def test_cache_version_changes_key():
    """Keys must differ across cache versions so stale entries are never served."""
    import synthadoc.core.cache as cache_mod
    original = cache_mod.CACHE_VERSION
    try:
        k1 = make_cache_key("op", {"text": "hello"})
        cache_mod.CACHE_VERSION = str(int(original) + 1)
        k2 = make_cache_key("op", {"text": "hello"})
        assert k1 != k2
    finally:
        cache_mod.CACHE_VERSION = original


@pytest.mark.asyncio
async def test_clear_deletes_all_entries(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    await cache.set("a", {"v": 1})
    await cache.set("b", {"v": 2})
    await cache.set("c", {"v": 3})

    removed = await cache.clear()
    assert removed == 3
    assert await cache.get("a") is None
    assert await cache.get("b") is None


@pytest.mark.asyncio
async def test_clear_on_empty_cache_returns_zero(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    assert await cache.clear() == 0
