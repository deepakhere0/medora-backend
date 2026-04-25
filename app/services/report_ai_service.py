import asyncio
import logging
from typing import Optional
from uuid import UUID

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Same prompt as the live AI endpoint in ai.py — kept in sync manually.
_REPORT_ANALYSIS_PROMPT = """You are Medora AI, a helpful and professional medical report analyzer.

TASK: Analyze the uploaded medical report image and explain the findings clearly.

RULES:
- Identify the type of report (blood test, X-ray, MRI, urine test, etc.)
- List each parameter/finding with its value and whether it is NORMAL, HIGH, or LOW
- Explain what abnormal values might indicate in simple, easy-to-understand language
- Do NOT invent or fabricate any data — only analyze what is visible in the image
- Keep medical terms but always add a simple explanation in parentheses
- If the image is unclear or not a medical report, say so honestly

RESPONSE FORMAT — respond ONLY in this JSON structure, no markdown, no backticks:
{
    "report_type": "Type of medical report identified",
    "summary": "A 2-3 sentence plain-language overview of the report",
    "findings": [
        {
            "parameter": "Parameter name",
            "value": "Value shown in report",
            "status": "NORMAL / HIGH / LOW / ABNORMAL",
            "explanation": "What this means in simple language"
        }
    ],
    "concerns": ["List of any values that need attention"],
    "recommendations": "General advice based on the findings",
    "disclaimer": "This is an AI-powered analysis by Medora AI. Please consult a verified Medora doctor for official diagnosis and treatment."
}

If the image is NOT a medical report, respond with:
{
    "report_type": "Not a medical report",
    "summary": "The uploaded image does not appear to be a medical report.",
    "findings": [],
    "concerns": [],
    "recommendations": "Please upload a clear image of your medical report.",
    "disclaimer": "This is an AI-powered analysis by Medora AI. Please consult a verified Medora doctor for official diagnosis and treatment."
}"""


def _call_gemini_sync(image_bytes: bytes, mime_type: str) -> str:
    """Synchronous Gemini Vision call — run via asyncio.to_thread."""
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    parts = [
        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        genai_types.Part.from_text(text="Analyze this medical report and provide findings."),
    ]
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=parts,
        config=genai_types.GenerateContentConfig(
            system_instruction=_REPORT_ANALYSIS_PROMPT,
            max_output_tokens=2000,
        ),
    )
    return resp.text


async def analyze_report_with_gemini(
    file_url: str,
    file_type: str,
) -> tuple[Optional[str], str]:
    """
    Fetch image from public URL and run Gemini Vision analysis.

    Returns (analysis_text | None, status).
    PDFs → (None, 'skipped').
    Any failure → (None, 'failed'). Never raises.
    """
    if file_type == "application/pdf":
        return None, "skipped"

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.get(file_url)
            resp.raise_for_status()
            image_bytes = resp.content

        analysis = await asyncio.to_thread(_call_gemini_sync, image_bytes, file_type)
        return analysis, "completed"

    except Exception as exc:
        logger.error("Gemini report analysis failed: %s: %s", type(exc).__name__, exc)
        return None, "failed"


async def run_ai_analysis_background(
    report_id: UUID,
    file_url: str,
    file_type: str,
) -> None:
    """
    Background task: run AI analysis and persist the result.
    Opens its own DB session — safe to run after the request context is torn down.
    """
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.report import Report

    analysis, ai_status = await analyze_report_with_gemini(file_url, file_type)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Report).where(Report.id == report_id))
            report = result.scalar_one_or_none()
            if report is not None:
                report.ai_analysis = analysis
                report.ai_analysis_status = ai_status
                await db.commit()
    except Exception as exc:
        logger.error(
            "Failed to persist AI analysis for report %s: %s: %s",
            report_id,
            type(exc).__name__,
            exc,
        )
