# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import threading
from synthadoc.storage.wiki import WikiStorage, WikiPage


def test_write_and_read_page(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(title="Test", tags=["ai"], content="Hello [[Other]].",
                    status="active", confidence="medium", sources=[])
    store.write_page("test", page)
    loaded = store.read_page("test")
    assert loaded.title == "Test"
    assert "ai" in loaded.tags
    assert "[[Other]]" in loaded.content


def test_frontmatter_in_file(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("x", WikiPage(title="X", tags=["t1"], content="body",
                     status="active", confidence="high", sources=[]))
    raw = (tmp_wiki / "wiki" / "x.md").read_text()
    assert "title: X" in raw
    assert "status: active" in raw


def test_list_pages(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    for name in ("alpha", "beta", "gamma"):
        store.write_page(name, WikiPage(title=name, tags=[], content="",
                         status="active", confidence="medium", sources=[]))
    assert set(store.list_pages()) == {"alpha", "beta", "gamma"}


def test_page_not_found_returns_none(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    assert store.read_page("nonexistent") is None


def test_write_lock_serialises_writes(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    results = []
    def write(n):
        with store.page_lock("shared"):
            results.append(n)
    threads = [threading.Thread(target=write, args=(i,)) for i in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(results) == [0, 1, 2, 3, 4]
