"""
services/report_ai_service.py
------------------------------
OCR + AI analysis pipeline for patient-uploaded medical report images.

Pipeline (run as a background task after upload):
  1. Fetch image bytes from Supabase public URL
  2. Run Google Cloud Vision OCR  → extracted_text, clean_text
  3. Run Gemini Vision analysis   → structured JSON (ai_analysis)
  4. Persist all fields to the DB

Gemini receives BOTH the raw image AND the OCR-cleaned text as context,
which significantly improves the accuracy and depth of the analysis.

Design rules:
• Never raise — all exceptions are caught; the report row gets status="failed"
  rather than crashing the background worker.
• Never log API keys or patient file content.
• PDFs: OCR is run (Vision supports single-page PDFs), but Gemini image
  analysis is skipped (Vision multimodal doesn't support PDF inline content).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.services.vision_service import OCRResult, run_ocr
from app.utils.ai_wrapper import get_safe_system_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini system prompt (kept in sync with ai.py router prompt)
# ---------------------------------------------------------------------------

_REPORT_ANALYSIS_PROMPT = """\
You are a medical AI assistant inside a healthcare application called MEDORA.

Your task is to analyze a medical report (OCR text extracted from lab reports, prescriptions, or diagnostic reports) and return a structured, patient-friendly response.

---

## 🎯 OBJECTIVE

Analyze the provided medical report text and extract meaningful insights in a structured JSON format.

---

## 🧠 INPUT

You will receive raw OCR-extracted text from a medical report.

---

## 📤 OUTPUT FORMAT (STRICT — DO NOT CHANGE)

Return ONLY valid JSON. No extra text.

{
"summary": "Short, calm, easy-to-understand overview of the report",
"important_points": [
"List key observations (high/low/abnormal values)"
],
"values": [
{
"name": "Test name",
"value": "Observed value",
"status": "normal" | "high" | "low"
}
],
"explanation": "Detailed but simple explanation for a non-medical user"
}

---

## ⚠️ RULES

* Use simple, patient-friendly language
* DO NOT use complex medical jargon without explaining it
* DO NOT create panic — keep tone calm and reassuring
* If values are outside normal range → mark as "high" or "low"
* If unsure → mark as "normal"
* Extract as many relevant values as possible

---

## 🧪 MEDICAL LOGIC GUIDELINES

* Identify common lab values:

  * Hemoglobin
  * WBC
  * RBC
  * Platelets
  * Blood Sugar
  * Cholesterol
* Compare values with general normal ranges
* Highlight abnormal values in important_points

---

## 🧹 CLEANING RULES

* Ignore irrelevant text (headers, addresses, etc.)
* Normalize inconsistent OCR text
* Merge broken lines logically

---

## 🚫 DO NOT

* Do NOT return plain text
* Do NOT add markdown
* Do NOT add explanation outside JSON
* Do NOT hallucinate unknown values

---

## 🎯 GOAL

Make the output ready to directly power a UI like Apple Health + ChatGPT style report cards.
"""


# ---------------------------------------------------------------------------
# Gemini (Vision + text context) — sync, called via asyncio.to_thread
# ---------------------------------------------------------------------------

def _call_gemini_sync(
    image_bytes: bytes,
    mime_type: str,
    clean_text: str,
) -> str:
    """
    Call Gemini with the raw image AND OCR-extracted text for richer analysis.

    The OCR text is prepended as context so Gemini doesn't have to rely solely
    on its vision capabilities — this is especially helpful for dense text
    documents like blood test reports.
    """
    import time
    from google import genai
    from google.genai import types as genai_types
    from google.genai.errors import ClientError

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    parts: list[genai_types.Part] = []

    # If OCR succeeded, include the cleaned text as additional context
    if clean_text:
        ocr_context = (
            f"OCR-extracted text from the document:\n\n{clean_text}\n\n"
            "Use the above extracted text alongside the image to provide "
            "a comprehensive analysis."
        )
        parts.append(genai_types.Part.from_text(text=ocr_context))

    # Always include the image (Vision handles the visual structure)
    parts.append(
        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    )
    parts.append(
        genai_types.Part.from_text(
            text="Analyze this medical report and provide structured findings."
        )
    )

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=parts,
                config=genai_types.GenerateContentConfig(
                    system_instruction=get_safe_system_prompt(_REPORT_ANALYSIS_PROMPT, mode="report"),
                    max_output_tokens=2000,
                    response_mime_type="application/json",
                ),
            )
            
            # Safely extract text from response
            try:
                response_text = resp.candidates[0].content.parts[0].text
                if not response_text:
                    raise ValueError("Empty text in parts")
                return response_text
            except Exception as extract_err:
                logger.error(f"Gemini text extraction failed: {extract_err}")
                return '{"report_type": "Unknown", "summary": "⚠️ Unexpected response format from AI. Please try again.", "findings": [], "concerns": [], "recommendations": ""}'
                
        except ClientError as e:
            if e.code == 429 and attempt < max_retries:
                logger.warning(f"Gemini 429 error, retrying in 2 seconds (attempt {attempt + 1})...")
                time.sleep(2)
                continue
            logger.error(f"Gemini ClientError: {e}")
            if e.code == 429:
                return '{"report_type": "Unknown", "summary": "⏳ Server is busy. Please try again in a few seconds.", "findings": [], "concerns": [], "recommendations": ""}'
            raise e
        except Exception as e:
            logger.error(f"Gemini General Error: {e}")
            raise e

    return '{"report_type": "Unknown", "summary": "⚠️ AI analysis failed. Please try again later.", "findings": [], "concerns": [], "recommendations": ""}'


# ---------------------------------------------------------------------------
# Public: full OCR + Gemini analysis pipeline
# ---------------------------------------------------------------------------

async def analyze_report_with_gemini(
    file_url: str,
    file_type: str,
) -> tuple[Optional[str], str, Optional[str], Optional[str]]:
    """
    Run the full OCR → Gemini pipeline for a medical report.

    Args:
        file_url:  Public Supabase URL of the uploaded file.
        file_type: MIME type ("image/jpeg", "image/png", "application/pdf").

    Returns:
        (ai_analysis, ai_status, extracted_text, clean_text)

        ai_analysis   : Gemini JSON string, or None
        ai_status     : "completed" | "failed" | "skipped"
        extracted_text: Raw Vision OCR text, or None
        clean_text    : Cleaned OCR text, or None
    """
    # ------------------------------------------------------------------
    # Step 1: Fetch the file
    # ------------------------------------------------------------------
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.get(file_url)
            resp.raise_for_status()
            file_bytes = resp.content
    except Exception as exc:
        logger.error(
            "report_fetch_failed url_len=%d error_type=%s",
            len(file_url),
            type(exc).__name__,
        )
        return None, "failed", None, None

    # ------------------------------------------------------------------
    # Step 2: OCR via Google Cloud Vision
    # ------------------------------------------------------------------
    ocr: OCRResult = await run_ocr(file_bytes, file_type)

    extracted_text: Optional[str] = ocr.extracted_text or None
    clean_text: Optional[str] = ocr.clean_text or None

    # 4. If no text, and it's a PDF, we must abort because Gemini Vision
    #    doesn't natively read PDFs via the text/image parts (needs Document API).

    if ocr.success:
        logger.info(
            "vision_ocr_completed file_type=%s chars=%d",
            file_type,
            len(ocr.clean_text),
        )
    else:
        logger.warning(
            "vision_ocr_failed file_type=%s reason=%s",
            file_type,
            ocr.error,
        )

    if not extracted_text:
        return '{"report_type": "Unknown", "summary": "No readable text found in this report.", "findings": [], "concerns": [], "recommendations": ""}', "failed", None, None

    # ------------------------------------------------------------------
    # Step 3: Gemini Vision analysis (images only)
    # PDFs: Gemini multimodal doesn't accept PDF bytes inline → skip
    # ------------------------------------------------------------------
    if file_type == "application/pdf":
        logger.info("report_ai_skipped file_type=application/pdf")
        return None, "skipped", extracted_text, clean_text

    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured — AI analysis skipped")
        return None, "skipped", extracted_text, clean_text

    try:
        analysis = await asyncio.to_thread(
            _call_gemini_sync,
            file_bytes,
            file_type,
            ocr.clean_text,
        )
        logger.info("gemini_analysis_completed file_type=%s", file_type)
        return analysis, "completed", extracted_text, clean_text

    except Exception as exc:
        import traceback
        traceback.print_exc()
        logger.error(
            "gemini_analysis_failed file_type=%s error_type=%s",
            file_type,
            type(exc).__name__,
            exc_info=False,
        )
        # OCR succeeded even though Gemini failed — preserve the OCR data
        return None, "failed", extracted_text, clean_text


# ---------------------------------------------------------------------------
# Background task entry point (called from the router)
# ---------------------------------------------------------------------------

async def run_ai_analysis_background(
    report_id: UUID,
    file_url: str,
    file_type: str,
) -> None:
    """
    Background task: run the OCR + AI pipeline and persist results.

    Opens its own DB session — safe to run after the HTTP request context
    has been torn down.
    """
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.report import Report

    ai_analysis, ai_status, extracted_text, clean_text = (
        await analyze_report_with_gemini(file_url, file_type)
    )

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Report).where(Report.id == report_id)
            )
            report = result.scalar_one_or_none()
            if report is not None:
                report.ai_analysis = ai_analysis
                report.ai_analysis_status = ai_status
                # Persist OCR fields — even if Gemini failed the text is valuable
                report.extracted_text = extracted_text
                report.clean_text = clean_text
                await db.commit()
                logger.info(
                    "report_pipeline_persisted report_id=%s status=%s "
                    "ocr=%s gemini=%s",
                    report_id,
                    ai_status,
                    "ok" if extracted_text else "none",
                    "ok" if ai_analysis else "none",
                )
    except Exception as exc:
        logger.error(
            "report_pipeline_persist_failed report_id=%s error_type=%s",
            report_id,
            type(exc).__name__,
        )
