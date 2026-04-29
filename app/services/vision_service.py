"""
services/vision_service.py
--------------------------
Google Cloud Vision API — OCR pipeline for medical reports.

Security rules (never break these):
• The API key is read ONLY from settings (env vars). Never log it, never
  return it, never pass it outside this module.
• This module is BACKEND-ONLY; it must never be imported by frontend code.

Supported inputs:
• image/jpeg, image/png  → Vision TEXT_DETECTION via base64 content
• application/pdf        → Vision DOCUMENT_TEXT_DETECTION via base64 content
                           (Vision handles single-page PDFs natively; for
                           multi-page PDFs it returns text from the first page
                           — acceptable for medical reports which are usually
                           1–2 pages)

Pipeline:
  raw bytes → base64 → Vision REST API → fullTextAnnotation.text
            → clean_ocr_text()          → stored as clean_text
            → extract_important_points() → returned to caller
            → generate_basic_summary()  → returned to caller

Future extension:
  The cleaned text is designed to be piped directly into Gemini as a text
  prompt, enabling richer analysis without re-running Vision:

      gemini_prompt = f"{REPORT_ANALYSIS_PROMPT}\\n\\n{clean_text}"
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.utils.file_utils import (
    clean_ocr_text,
    extract_important_points,
    generate_basic_summary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
_REQUEST_TIMEOUT = 30.0  # seconds


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class OCRResult:
    """Structured result returned by the Vision OCR pipeline."""
    success: bool
    extracted_text: str
    clean_text: str
    summary: str
    important_points: list[str]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_vision_request(
    file_bytes: bytes,
    mime_type: str,
) -> dict:
    """
    Build the annotate request body for the Vision REST API.

    Uses TEXT_DETECTION for images and DOCUMENT_TEXT_DETECTION for PDFs —
    the latter is optimised for dense, formatted documents.
    """
    encoded = base64.b64encode(file_bytes).decode("utf-8")

    # Choose the best feature for the content type
    if mime_type == "application/pdf":
        feature_type = "DOCUMENT_TEXT_DETECTION"
    else:
        feature_type = "TEXT_DETECTION"

    return {
        "requests": [
            {
                "image": {"content": encoded},
                "features": [{"type": feature_type, "maxResults": 1}],
                # Hint: medical/health context to improve recognition accuracy
                "imageContext": {
                    "languageHints": ["en"],
                },
            }
        ]
    }


def _extract_text_from_response(response_json: dict) -> str:
    """
    Pull the full text from a Vision API response.

    Prefers fullTextAnnotation.text (structured); falls back to the first
    textAnnotation description (unstructured).
    """
    try:
        responses = response_json.get("responses", [{}])
        if not responses:
            return ""

        first = responses[0]

        # Error returned by Vision (e.g., unsupported image format)
        if "error" in first:
            code = first["error"].get("code", "?")
            msg = first["error"].get("message", "Unknown Vision API error")
            logger.warning("Vision API returned error %s: %s", code, msg)
            return ""

        # Best source: fullTextAnnotation
        full_text_annotation = first.get("fullTextAnnotation") or {}
        full_text = full_text_annotation.get("text", "")
        if full_text:
            return full_text

        # Fallback: first textAnnotation (bounding-box level, concatenated)
        annotations = first.get("textAnnotations") or []
        if annotations:
            return annotations[0].get("description", "")

        return ""

    except Exception as exc:
        logger.error("Failed to parse Vision API response: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_ocr(
    file_bytes: bytes,
    mime_type: str,
) -> OCRResult:
    """
    Run Google Cloud Vision OCR on a file.

    Args:
        file_bytes: Raw file content (already validated and size-checked by
                    the caller).
        mime_type:  MIME type string — "image/jpeg", "image/png", or
                    "application/pdf".

    Returns:
        An OCRResult dataclass. Never raises — all exceptions are caught and
        returned as a failed OCRResult.
    """
    api_key = settings.GOOGLE_CLOUD_VISION_API_KEY

    # Guard: treat the .env placeholder as "not configured"
    _is_placeholder = (
        not api_key
        or api_key.startswith("YOUR_")
        or api_key == "your-google-cloud-vision-api-key"
    )
    if _is_placeholder:
        logger.warning(
            "GOOGLE_CLOUD_VISION_API_KEY is not configured — OCR skipped"
        )
        return OCRResult(
            success=False,
            extracted_text="",
            clean_text="",
            summary="",
            important_points=[],
            error="Vision API key not configured",
        )

    logger.info(
        "vision_ocr_start mime=%s size_kb=%d",
        mime_type,
        len(file_bytes) // 1024,
    )

    payload = _build_vision_request(file_bytes, mime_type)
    url = f"{_VISION_ENDPOINT}?key={api_key}"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            response_json = response.json()

    except httpx.TimeoutException:
        logger.error("vision_ocr_timeout mime=%s", mime_type)
        return OCRResult(
            success=False,
            extracted_text="",
            clean_text="",
            summary="",
            important_points=[],
            error="Vision API request timed out",
        )
    except httpx.HTTPStatusError as exc:
        # Log only the status code — never the URL (which contains the API key)
        logger.error(
            "vision_ocr_http_error status=%s",
            exc.response.status_code,
        )
        return OCRResult(
            success=False,
            extracted_text="",
            clean_text="",
            summary="",
            important_points=[],
            error=f"Vision API HTTP error {exc.response.status_code}",
        )
    except Exception as exc:
        logger.error("vision_ocr_unexpected_error type=%s", type(exc).__name__)
        return OCRResult(
            success=False,
            extracted_text="",
            clean_text="",
            summary="",
            important_points=[],
            error="Unexpected error during OCR",
        )

    # --- Parse response ---
    extracted_text = _extract_text_from_response(response_json)

    if not extracted_text:
        logger.info("vision_ocr_no_text mime=%s", mime_type)
        return OCRResult(
            success=False,
            extracted_text="",
            clean_text="",
            summary="No text could be detected in this document.",
            important_points=[],
            error="No text detected",
        )

    clean_text = clean_ocr_text(extracted_text)
    summary = generate_basic_summary(clean_text)
    important_points = extract_important_points(clean_text)

    logger.info(
        "vision_ocr_success mime=%s chars=%d points=%d",
        mime_type,
        len(clean_text),
        len(important_points),
    )

    return OCRResult(
        success=True,
        extracted_text=extracted_text,
        clean_text=clean_text,
        summary=summary,
        important_points=important_points,
    )
