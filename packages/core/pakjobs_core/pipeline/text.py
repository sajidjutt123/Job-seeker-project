"""Text utilities shared across the ingestion pipeline."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"[ \t\u00a0]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")
_BLOCK_TAGS = re.compile(r"</(p|div|li|ul|ol|h[1-6]|br|tr|table|section)>", re.IGNORECASE)
_BR_TAGS = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LI_TAGS = re.compile(r"<li[^>]*>", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_html(value: str | None) -> str:
    """Convert an HTML fragment to readable plain text (no external parser dependency)."""
    if not value:
        return ""
    text = _SCRIPT_RE.sub(" ", value)
    text = _LI_TAGS.sub("\n• ", text)
    text = _BR_TAGS.sub("\n", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTINEWLINE_RE.sub("\n\n", text)
    return text.strip()


def collapse_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def normalize_text(value: str | None) -> str:
    """Lowercase, de-accent and collapse — the canonical comparison form."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return collapse_whitespace(text.lower())


def slugify(value: str, max_length: int = 80) -> str:
    text = normalize_text(value)
    text = _NON_ALNUM.sub("-", text).strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "item"


def sha256_hex(*parts: str | None) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update((part or "").encode("utf-8", errors="ignore"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def truncate(value: str, limit: int, suffix: str = "…") -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - len(suffix))].rstrip() + suffix


BULLET_PREFIX = re.compile(r"^\s*(?:[-*•·–—]|\d+[.)])\s+")


def extract_bullets(text: str, headings: tuple[str, ...]) -> list[str]:
    """Pull bullet lines that appear under any of the given section headings.

    Falls back to an empty list rather than guessing, so the UI can hide the section
    instead of showing noise.
    """
    if not text:
        return []
    lines = text.split("\n")
    heading_re = re.compile(r"^\s*[#*\s]*(" + "|".join(headings) + r")\b[:\s]*$", re.IGNORECASE)
    other_heading_re = re.compile(
        r"^\s*[#*\s]*(responsibilit|requirement|qualification|benefit|what you|about|skills|"
        r"experience|we offer|perks|how to apply|salary|compensation)", re.IGNORECASE
    )
    collected: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if heading_re.match(stripped):
            capturing = True
            continue
        if capturing:
            if not stripped:
                if collected:
                    continue
                continue
            if other_heading_re.match(stripped) and not BULLET_PREFIX.match(stripped):
                break
            if BULLET_PREFIX.match(stripped):
                item = BULLET_PREFIX.sub("", stripped).strip()
                if 3 < len(item) <= 400:
                    collected.append(item)
            elif collected:
                break
    return collected[:20]
