"""AI-assisted services with deterministic fallbacks.

Contract for every service here: if AI is disabled, misconfigured, slow or erroring, the method
still returns a useful result. `used_ai` tells the caller which path produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pakjobs_core.logging import get_logger
from pakjobs_core.pipeline.classifier import ClassificationResult, classify_job
from pakjobs_core.pipeline.normalizer import extract_skills
from pakjobs_core.pipeline.text import collapse_whitespace, truncate
from pakjobs_core.services.ai.base import AIProvider, AIUnavailable, get_ai_provider

logger = get_logger("ai.services")


@dataclass(slots=True)
class AIResult:
    value: Any
    used_ai: bool = False
    provider: str = "fallback"
    note: str = ""


class AIJobSummary:
    """Short plain-language summary of a job description."""

    SYSTEM = (
        "You summarise job advertisements for a Pakistani job board. Reply with 2 short sentences, "
        "plain language, no marketing tone, no invented facts."
    )

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or get_ai_provider()

    async def summarize(self, *, title: str, description: str, company: str | None = None) -> AIResult:
        fallback = self._fallback(description)
        if not self.provider.available:
            return AIResult(fallback, used_ai=False, note="ai_disabled")
        prompt = (
            f"Job title: {title}\nCompany: {company or 'not stated'}\n\n"
            f"Description:\n{truncate(description, 4000)}\n\nSummary:"
        )
        try:
            response = await self.provider.complete(prompt, system=self.SYSTEM, max_tokens=180)
        except AIUnavailable as exc:
            logger.warning("ai.summary_failed", error=str(exc))
            return AIResult(fallback, used_ai=False, note=str(exc))
        return AIResult(collapse_whitespace(response.text), used_ai=True, provider=response.provider)

    @staticmethod
    def _fallback(description: str) -> str:
        """First meaningful sentences of the description — always available."""
        text = collapse_whitespace(description)
        if not text:
            return "No description was provided by the source. Open the original posting for details."
        sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if len(s.strip()) > 25]
        return truncate(". ".join(sentences[:2]) + ("." if sentences else ""), 320)


class AIJobClassification:
    """Category assignment with the rules engine as the guaranteed baseline."""

    SYSTEM = (
        "You classify job adverts into exactly one category slug from the provided list. "
        'Reply with JSON only: {"category": "<slug>", "confidence": <0-1>}'
    )

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or get_ai_provider()

    async def classify(
        self, *, title: str, description: str, company: str | None = None, allowed: list[str] | None = None
    ) -> AIResult:
        baseline: ClassificationResult = classify_job(title=title, description=description, company_name=company)
        # Trust the rules engine when it is confident — cheaper and equally good.
        if not self.provider.available or baseline.confidence >= 0.7:
            return AIResult(baseline, used_ai=False, note="rules_confident" if baseline.confidence >= 0.7 else "ai_disabled")

        from pakjobs_core.domain.enums import JobCategorySlug

        categories = allowed or [c.value for c in JobCategorySlug]
        prompt = (
            f"Categories: {', '.join(categories)}\n\nTitle: {title}\nCompany: {company or 'unknown'}\n"
            f"Description: {truncate(description, 2500)}\n\nJSON:"
        )
        try:
            response = await self.provider.complete(prompt, system=self.SYSTEM, max_tokens=120)
            data = response.as_json()
            category = str(data.get("category", "")).strip()
            if category not in categories:
                raise AIUnavailable(f"AI returned unknown category '{category}'")
            baseline.category = category
            baseline.confidence = float(data.get("confidence", 0.6))
            baseline.method = "ai"
            return AIResult(baseline, used_ai=True, provider=response.provider)
        except (AIUnavailable, ValueError, TypeError) as exc:
            logger.warning("ai.classification_failed", error=str(exc))
            return AIResult(baseline, used_ai=False, note=str(exc))


class AISkillExtraction:
    SYSTEM = (
        "Extract required technical and professional skills from a job advert. "
        'Reply with JSON only: {"skills": ["Skill One", "Skill Two"]}. Max 15 items, no duplicates.'
    )

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or get_ai_provider()

    async def extract(self, *, title: str, description: str) -> AIResult:
        fallback = extract_skills(title, description)
        if not self.provider.available:
            return AIResult(fallback, used_ai=False, note="ai_disabled")
        try:
            response = await self.provider.complete(
                f"Title: {title}\n\n{truncate(description, 4000)}\n\nJSON:", system=self.SYSTEM, max_tokens=250
            )
            skills = response.as_json().get("skills", [])
            cleaned = [collapse_whitespace(str(s))[:60] for s in skills if s][:15]
            if not cleaned:
                raise AIUnavailable("AI returned no skills")
            # Union with the dictionary result: AI adds recall, rules guarantee precision.
            merged = list(dict.fromkeys([*fallback, *cleaned]))[:20]
            return AIResult(merged, used_ai=True, provider=response.provider)
        except (AIUnavailable, AttributeError, TypeError) as exc:
            logger.warning("ai.skill_extraction_failed", error=str(exc))
            return AIResult(fallback, used_ai=False, note=str(exc))


class AIJobMatch:
    """Explains why a job matches a candidate. Falls back to the deterministic reasons."""

    SYSTEM = (
        "You explain in one short sentence why a job suits a candidate. Be factual, never invent "
        "qualifications the candidate does not have."
    )

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or get_ai_provider()

    async def explain(self, *, job_title: str, job_skills: list[str], profile_skills: list[str],
                      deterministic_reasons: list[str]) -> AIResult:
        fallback = deterministic_reasons[0] if deterministic_reasons else "Matches your saved preferences."
        if not self.provider.available:
            return AIResult(fallback, used_ai=False, note="ai_disabled")
        prompt = (
            f"Job: {job_title}\nJob skills: {', '.join(job_skills[:10]) or 'not listed'}\n"
            f"Candidate skills: {', '.join(profile_skills[:10]) or 'not listed'}\n\nOne sentence:"
        )
        try:
            response = await self.provider.complete(prompt, system=self.SYSTEM, max_tokens=80)
            return AIResult(collapse_whitespace(response.text)[:200], used_ai=True, provider=response.provider)
        except AIUnavailable as exc:
            return AIResult(fallback, used_ai=False, note=str(exc))


class AICareerAssistant:
    """Conversational career guidance. Refuses gracefully when AI is off."""

    SYSTEM = (
        "You are a careers adviser for job seekers in Pakistan. Give concrete, realistic, locally "
        "relevant advice. Never promise jobs, never request money or personal documents. "
        "Keep answers under 200 words."
    )
    UNAVAILABLE_MESSAGE = (
        "The career assistant is not enabled on this deployment. "
        "You can still search jobs, save them and create alerts."
    )

    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or get_ai_provider()

    async def ask(self, question: str, *, context: str | None = None) -> AIResult:
        if not self.provider.available:
            return AIResult(self.UNAVAILABLE_MESSAGE, used_ai=False, note="ai_disabled")
        prompt = f"{('Context: ' + context) if context else ''}\n\nQuestion: {question}".strip()
        try:
            response = await self.provider.complete(prompt, system=self.SYSTEM, max_tokens=500)
            return AIResult(response.text.strip(), used_ai=True, provider=response.provider)
        except AIUnavailable as exc:
            logger.warning("ai.assistant_failed", error=str(exc))
            return AIResult(
                "The career assistant is temporarily unavailable. Please try again shortly.",
                used_ai=False, note=str(exc),
            )
