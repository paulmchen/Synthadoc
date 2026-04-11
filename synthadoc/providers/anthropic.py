# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import asyncio
from typing import Optional
import anthropic as anthropic_lib
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

_RETRYABLE = (anthropic_lib.RateLimitError, anthropic_lib.InternalServerError)
_MAX_RETRIES = 3


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig) -> None:
        self._client = anthropic_lib.AsyncAnthropic(api_key=api_key)
        self._config = config

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.messages.create(**kwargs)
                text = "".join(b.text for b in resp.content if hasattr(b, "text"))
                return CompletionResponse(text=text,
                                         input_tokens=resp.usage.input_tokens,
                                         output_tokens=resp.usage.output_tokens)
            except _RETRYABLE as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(0)  # yield; real backoff added in orchestrator
                continue
            except Exception:
                raise
        raise last_exc
