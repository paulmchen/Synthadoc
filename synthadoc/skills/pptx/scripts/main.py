# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from pptx import Presentation
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta


class PptxSkill(BaseSkill):
    meta = SkillMeta(name="pptx", description="Extract text from PowerPoint presentations",
                     extensions=[".pptx"])

    async def extract(self, source: str) -> ExtractedContent:
        try:
            prs = Presentation(source)
        except Exception as exc:
            raise ValueError(
                f"Cannot read '{source}' as a PowerPoint file: {exc}. "
                "Ensure the file is a valid .pptx (Office Open XML) document."
            ) from exc
        sections: list[str] = []

        for i, slide in enumerate(prs.slides, start=1):
            lines: list[str] = []
            title = ""
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                text = shape.text_frame.text.strip()
                if not text:
                    continue
                if shape.shape_type == 13:  # picture — skip
                    continue
                if not title and shape.name.lower().startswith("title"):
                    title = text
                else:
                    lines.append(text)

            notes = ""
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    notes = f"\n_Notes: {notes_text}_"

            heading = f"## Slide {i}" + (f": {title}" if title else "")
            body = "\n".join(lines)
            sections.append(f"{heading}\n{body}{notes}" if body or notes else heading)

        text = "\n\n".join(sections)
        return ExtractedContent(
            text=text,
            source_path=source,
            metadata={"slides": len(prs.slides)},
        )
