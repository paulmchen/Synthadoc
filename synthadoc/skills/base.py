# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Paul Chen / axoviq.com
# Plugin interface — third-party skills may extend these base classes under any licence.
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SkillMeta:
    name: str
    description: str
    extensions: list[str]


@dataclass
class ExtractedContent:
    text: str
    source_path: str
    metadata: dict


class BaseSkill(ABC):
    meta: SkillMeta
    _resources_dir: Optional[Path] = None

    def __init__(self):
        self._resource_cache: dict[str, str] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._resource_cache: dict[str, str] = {}

    def get_resource(self, name: str) -> str:
        """Tier 3: load a resource file lazily from the skill's resources/ directory."""
        if name not in self._resource_cache:
            if self._resources_dir is None:
                raise FileNotFoundError(f"No resources dir configured for skill '{self.meta.name}'")
            self._resource_cache[name] = (self._resources_dir / name).read_text(encoding="utf-8")
        return self._resource_cache[name]

    @abstractmethod
    async def extract(self, source: str) -> ExtractedContent: ...
