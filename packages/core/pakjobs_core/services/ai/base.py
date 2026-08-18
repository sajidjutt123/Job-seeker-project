"""AI provider abstraction.

The platform must never depend on a single vendor, and must never break when AI is unavailable.
Every AI service therefore:
  * goes through the `AIProvider` protocol (OpenAI / Gemini / Anthropic / local / null),
  * has a deterministic non-AI fallback,
  * is time-boxed and exception-safe.

`NullProvider` is the default, so a fresh install works with no API keys at all.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from typing import Any

import httpx

from pakjobs_core.config import settings
from pakjobs_core.http import http_verify
from pakjobs_core.logging import get_logger

logger = get_logger("ai")


class AIUnavailable(RuntimeError):
    """Raised internally when a provider cannot serve a request; callers fall back."""


@dataclass(slots=True)
class AIResponse:
    text: str
    provider: str
    model: str | None = None
    usage: dict[str, Any] | None = None

    def as_json(self) -> Any:
        """Parse a JSON object out of the model output, tolerating code fences."""
        cleaned = self.text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
            cleaned = cleaned.removeprefix("json").strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end == -1:
            raise AIUnavailable("AI response contained no JSON")
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIUnavailable(f"AI response was not valid JSON: {exc}") from exc


class AIProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 600) -> AIResponse: ...

    @property
    def available(self) -> bool:
        return True


class NullProvider(AIProvider):
    """Default provider: always unavailable, so every service uses its deterministic fallback."""

    name = "null"

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 600) -> AIResponse:
        raise AIUnavailable("AI is disabled (AI_PROVIDER=null or AI_ENABLED=false)")

    @property
    def available(self) -> bool:
        return False


class OpenAIProvider(AIProvider):
    name = "openai"

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 600) -> AIResponse:
        if not settings.openai_api_key:
            raise AIUnavailable("OPENAI_API_KEY is not configured")
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        payload = {"model": settings.openai_model, "messages": messages, "max_tokens": max_tokens}
        data = await _post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            {"Authorization": f"Bearer {settings.openai_api_key}"},
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIUnavailable(f"Unexpected OpenAI response shape: {exc}") from exc
        return AIResponse(text=text, provider=self.name, model=settings.openai_model, usage=data.get("usage"))

    @property
    def available(self) -> bool:
        return bool(settings.openai_api_key)


class AnthropicProvider(AIProvider):
    name = "anthropic"

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 600) -> AIResponse:
        if not settings.anthropic_api_key:
            raise AIUnavailable("ANTHROPIC_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": settings.anthropic_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        data = await _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
        )
        try:
            text = "".join(block.get("text", "") for block in data["content"])
        except (KeyError, TypeError) as exc:
            raise AIUnavailable(f"Unexpected Anthropic response shape: {exc}") from exc
        return AIResponse(text=text, provider=self.name, model=settings.anthropic_model, usage=data.get("usage"))

    @property
    def available(self) -> bool:
        return bool(settings.anthropic_api_key)


class GeminiProvider(AIProvider):
    name = "gemini"

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 600) -> AIResponse:
        if not settings.gemini_api_key:
            raise AIUnavailable("GEMINI_API_KEY is not configured")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
        )
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data = await _post_json(url, payload, {})
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise AIUnavailable(f"Unexpected Gemini response shape: {exc}") from exc
        return AIResponse(text=text, provider=self.name, model=settings.gemini_model)

    @property
    def available(self) -> bool:
        return bool(settings.gemini_api_key)


class LocalProvider(AIProvider):
    """OpenAI-compatible local endpoint (Ollama, vLLM, LM Studio, ...)."""

    name = "local"

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 600) -> AIResponse:
        if not settings.local_ai_base_url:
            raise AIUnavailable("LOCAL_AI_BASE_URL is not configured")
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        data = await _post_json(
            f"{settings.local_ai_base_url.rstrip('/')}/chat/completions",
            {"model": settings.openai_model, "messages": messages, "max_tokens": max_tokens},
            {},
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIUnavailable(f"Unexpected local provider response: {exc}") from exc
        return AIResponse(text=text, provider=self.name, model=settings.openai_model)

    @property
    def available(self) -> bool:
        return bool(settings.local_ai_base_url)


async def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.ai_timeout_seconds), verify=http_verify()
        ) as client:
            response = await client.post(url, json=payload, headers={"Content-Type": "application/json", **headers})
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"AI provider network error: {exc}") from exc
    if response.status_code >= 300:
        raise AIUnavailable(f"AI provider HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()
    except ValueError as exc:
        raise AIUnavailable(f"AI provider returned non-JSON: {exc}") from exc


_PROVIDERS: dict[str, type[AIProvider]] = {
    "null": NullProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "local": LocalProvider,
}


def get_ai_provider() -> AIProvider:
    if not settings.ai_enabled:
        return NullProvider()
    provider_cls = _PROVIDERS.get(settings.ai_provider, NullProvider)
    provider = provider_cls()
    if not provider.available:
        logger.warning("ai.provider_unavailable", provider=settings.ai_provider)
        return NullProvider()
    return provider
