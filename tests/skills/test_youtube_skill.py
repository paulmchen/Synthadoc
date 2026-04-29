# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from synthadoc.skills.base import ExtractedContent


def _load_skill():
    from synthadoc.agents.skill_agent import SkillAgent
    from pathlib import Path
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "wiki").mkdir()
    agent = SkillAgent(wiki_root=tmp)
    return agent.get_skill("youtube")


def _fake_transcript():
    from types import SimpleNamespace
    return [
        SimpleNamespace(text="Hello world.", start=0.0, duration=2.0),
        SimpleNamespace(text="This is a test.", start=2.0, duration=3.0),
    ]


@pytest.mark.asyncio
async def test_extract_returns_transcript_text():
    """Successful extraction joins all caption entries into a single text string."""
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text == "Hello world. This is a test."
    assert result.source_path == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_extract_no_transcript_returns_empty():
    """NoTranscriptFound must return empty ExtractedContent, not raise."""
    from youtube_transcript_api import NoTranscriptFound
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               side_effect=NoTranscriptFound("dQw4w9WgXcQ", [], [])):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text == ""
    assert result.metadata.get("no_transcript") is True


@pytest.mark.asyncio
async def test_extract_video_unavailable_returns_empty():
    """VideoUnavailable must return empty ExtractedContent, not raise."""
    from youtube_transcript_api import VideoUnavailable
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               side_effect=VideoUnavailable("dQw4w9WgXcQ")):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text == ""


@pytest.mark.asyncio
async def test_extract_invalid_url_returns_empty():
    """URL from which no video ID can be parsed must return empty content silently."""
    skill = _load_skill()
    result = await skill.extract("https://www.youtube.com/")
    assert result.text == ""


def test_extract_video_id_from_watch_url():
    """Standard watch URL: extract video ID from ?v= query param."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://www.youtube.com/watch?v=abc123&t=30s") == "abc123"


def test_extract_video_id_from_youtu_be():
    """Short youtu.be URL: extract video ID from path."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://youtu.be/abc123?t=42") == "abc123"


def test_extract_video_id_from_embed_url():
    """Embed URL: extract video ID from /embed/ path segment."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_returns_none_for_invalid():
    """URL with no recognisable video ID must return None."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/channel/UC1234") is None
    assert _extract_video_id("https://www.youtube.com/") is None


@pytest.mark.asyncio
async def test_extract_runs_in_thread():
    """Transcript fetch must use asyncio.to_thread to avoid blocking the event loop."""
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())) as mock_thread:
        await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    mock_thread.assert_called_once()


@pytest.mark.asyncio
async def test_metadata_contains_video_id_and_url():
    """ExtractedContent metadata must include video_id and url keys."""
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.metadata["video_id"] == "dQw4w9WgXcQ"
    assert result.metadata["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
