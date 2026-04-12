# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
from typing import Optional
from openai import AsyncOpenAI
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig) -> None:
        kwargs: dict = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**kwargs)
        self._config = config

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        resp = await self._client.chat.completions.create(
            model=self._config.model, messages=msgs,
            temperature=temperature, max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        return CompletionResponse(text=choice.message.content or "",
                                  input_tokens=resp.usage.prompt_tokens,
                                  output_tokens=resp.usage.completion_tokens)
