"""
utils/file_utils.py
-------------------
Utility functions for processing and cleaning text extracted from medical
documents via OCR.

Design principle: keep medical numeric values intact (e.g., "Hb 12.4 g/dL")
while removing artefacts introduced by OCR engines (double spaces, stray
newlines, etc.).

Future: summary generation can be replaced with a Gemini call once the
text-context Gemini pipeline is live.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_ocr_text(raw_text: str) -> str:
    """
    Normalise OCR output while preserving medically significant tokens.

    Steps applied in order:
    1. Collapse runs of whitespace (spaces / tabs) to a single space.
    2. Collapse runs of blank lines to a single blank line (paragraph break).
    3. Strip leading/trailing whitespace from every line.
    4. Remove lines that contain only punctuation or digits with no letters
       (common OCR artefacts like "--- --- ---" or "· · ·").
    5. Final strip of leading/trailing whitespace.
    """
    if not raw_text:
        return ""

    # Step 1: normalise in-line whitespace (preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", raw_text)

    # Step 2: collapse multiple blank lines → single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Step 3 & 4: strip lines, drop pure-noise lines
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        # Drop lines with no alphabetic character (e.g., "--- *** ---", "12 34")
        if stripped and re.search(r"[A-Za-z]", stripped):
            lines.append(stripped)
        elif stripped and re.search(r"\d", stripped):
            # Keep lines that mix digits with recognisable medical separators
            if re.search(r"[\w./%]", stripped):
                lines.append(stripped)

    text = "\n".join(lines).strip()
    return text


def generate_basic_summary(clean_text: str, max_chars: int = 500) -> str:
    """
    Generate a naive extractive summary: first `max_chars` characters of the
    cleaned text, terminated at the last complete sentence if possible.

    This is a placeholder; replace with a Gemini /summarise call when ready.
    """
    if not clean_text:
        return "No text could be extracted from the document."

    if len(clean_text) <= max_chars:
        return clean_text

    truncated = clean_text[:max_chars]
    # Try to end at a sentence boundary
    last_period = max(
        truncated.rfind("."),
        truncated.rfind("!"),
        truncated.rfind("?"),
    )
    if last_period > max_chars // 2:
        truncated = truncated[: last_period + 1]

    return truncated + " …"


def extract_important_points(clean_text: str) -> list[str]:
    """
    Heuristically extract lines that are likely to be important clinical values.

    Looks for lines that contain:
    • A numeric value followed by a unit (g/dL, mg/L, mmol/L, U/L, %, etc.)
    • Keywords like NORMAL / HIGH / LOW / ABNORMAL / POSITIVE / NEGATIVE

    Returns up to 20 candidate lines.
    """
    if not clean_text:
        return []

    _UNIT_RE = re.compile(
        r"\b\d+\.?\d*\s*"
        r"(g/dL|mg/dL|mmol/L|mEq/L|U/L|IU/L|ng/mL|pg/mL|"
        r"µg/dL|mcg/dL|%|bpm|mmHg|cells/µL|×10\^?\d+)",
        re.IGNORECASE,
    )
    _FLAG_RE = re.compile(
        r"\b(NORMAL|HIGH|LOW|ABNORMAL|POSITIVE|NEGATIVE|REACTIVE|"
        r"NON[- ]REACTIVE|ELEVATED|DECREASED|CRITICAL)\b",
        re.IGNORECASE,
    )

    important: list[str] = []
    for line in clean_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _UNIT_RE.search(stripped) or _FLAG_RE.search(stripped):
            important.append(stripped)
        if len(important) >= 20:
            break

    return important
