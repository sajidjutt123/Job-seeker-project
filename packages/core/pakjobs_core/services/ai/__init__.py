"""Modular AI layer. Never a hard dependency."""

from pakjobs_core.services.ai.base import AIProvider, AIResponse, AIUnavailable, get_ai_provider
from pakjobs_core.services.ai.services import (
    AICareerAssistant,
    AIJobClassification,
    AIJobMatch,
    AIJobSummary,
    AIResult,
    AISkillExtraction,
)

__all__ = [
    "AIProvider", "AIResponse", "AIUnavailable", "get_ai_provider",
    "AICareerAssistant", "AIJobClassification", "AIJobMatch", "AIJobSummary",
    "AIResult", "AISkillExtraction",
]
