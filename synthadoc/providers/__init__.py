# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import os
from synthadoc.config import Config, AgentConfig
from synthadoc.providers.base import LLMProvider


def _require_env(var: str, provider: str, url: str) -> str:
    value = os.environ.get(var, "").strip()
    if not value:
        raise SystemExit(
            f"\nError: {var} is not set.\n"
            f"synthadoc uses {provider} as its LLM provider.\n\n"
            f"  1. Get your API key at: {url}\n"
            f"  2. Set it for the current session:\n"
            f"       Linux / macOS (bash/zsh):\n"
            f"         export {var}=<your-key>\n"
            f"       Windows cmd.exe:\n"
            f"         set {var}=<your-key>\n"
            f"       Windows PowerShell:\n"
            f"         $env:{var}='<your-key>'\n\n"
            f"  3. To set it permanently (survives terminal restarts):\n"
            f"       Linux / macOS:  echo 'export {var}=<your-key>' >> ~/.bashrc\n"
            f"       Windows:        [System.Environment]::SetEnvironmentVariable('{var}', '<your-key>', 'User')\n"
            f"                       (run in PowerShell, then reopen all terminals)\n\n"
            f"  Note: variables set in one terminal session (cmd.exe / PowerShell / bash)\n"
            f"  are not visible in other sessions until set permanently.\n\n"
            f"  Alternatively, set provider = \"ollama\" in .synthadoc/config.toml\n"
            f"  to use a local model with no API key required.\n"
        )
    return value


def make_provider(agent_name: str, config: Config) -> LLMProvider:
    agent_cfg = config.agents.resolve(agent_name)
    name = agent_cfg.provider
    if name == "anthropic":
        from synthadoc.providers.anthropic import AnthropicProvider
        key = _require_env("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/")
        return AnthropicProvider(api_key=key, config=agent_cfg)
    if name == "openai":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys")
        return OpenAIProvider(api_key=key, config=agent_cfg)
    if name == "gemini":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("GEMINI_API_KEY", "Google Gemini",
                           "https://aistudio.google.com/app/apikey")
        cfg_with_url = AgentConfig(
            provider="gemini", model=agent_cfg.model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url)
    if name == "groq":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys")
        cfg_with_url = AgentConfig(
            provider="groq", model=agent_cfg.model,
            base_url="https://api.groq.com/openai/v1",
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url)
    if name == "ollama":
        from synthadoc.providers.ollama import OllamaProvider
        return OllamaProvider(config=agent_cfg)
    raise ValueError(f"Unknown provider: {name!r}")
