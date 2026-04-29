# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse, parse_qs

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

logger = logging.getLogger(__name__)


def _extract_video_id(url: str) -> str | None:
    """Return the YouTube video ID from any recognised URL form, or None."""
    parsed = urlparse(url)
    # youtu.be/<id>
    if parsed.hostname in ("youtu.be",):
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None
    # youtube.com/watch?v=<id>
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0] or None
    # youtube.com/embed/<id>
    parts = parsed.path.split("/")
    try:
        idx = parts.index("embed")
        vid = parts[idx + 1] if idx + 1 < len(parts) else ""
        return vid or None
    except ValueError:
        pass
    return None


class YoutubeSkill(BaseSkill):
    meta = SkillMeta(
        name="youtube",
        description="Extract transcripts from YouTube videos via the YouTube caption system",
        extensions=["https://www.youtube.com/", "https://youtu.be/"],
    )

    async def extract(self, source: str) -> ExtractedContent:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            VideoUnavailable,
        )

        video_id = _extract_video_id(source)
        if not video_id:
            logger.warning("youtube: could not parse video ID from %s — skipping", source)
            return ExtractedContent(text="", source_path=source, metadata={"url": source})

        api = YouTubeTranscriptApi()
        try:
            fetched = await asyncio.to_thread(api.fetch, video_id)
        except NoTranscriptFound:
            logger.warning(
                "youtube: no captions available for %s — "
                "enable auto-generated captions or choose a different video",
                source,
            )
            return ExtractedContent(
                text="",
                source_path=source,
                metadata={"url": source, "video_id": video_id, "no_transcript": True},
            )
        except VideoUnavailable:
            logger.warning(
                "youtube: video unavailable (private or deleted): %s — skipping", source
            )
            return ExtractedContent(
                text="", source_path=source, metadata={"url": source}
            )

        text = " ".join(snippet.text for snippet in fetched)
        return ExtractedContent(
            text=text,
            source_path=source,
            metadata={"url": source, "video_id": video_id},
        )
