# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from docx import Document
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta


class DocxSkill(BaseSkill):
    meta = SkillMeta(name="docx", description="Extract text from Word documents",
                     extensions=[".docx"])

    async def extract(self, source: str) -> ExtractedContent:
        try:
            doc = Document(source)
        except Exception as exc:
            raise ValueError(
                f"Cannot read '{source}' as a Word document: {exc}. "
                "Ensure the file is a valid .docx (Office Open XML) document."
            ) from exc
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return ExtractedContent(text=text, source_path=source,
                                metadata={"paragraphs": len(doc.paragraphs)})
