import json
import traceback
from datetime import date

from google import genai
from google.genai import types as genai_types
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient

router = APIRouter(prefix="/patient/ai", tags=["Patient AI"])

# Gemini client (new SDK)
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

DAILY_AI_LIMIT = 5

SYSTEM_PROMPT = """You are "Medora AI", a compassionate health assistant for patients in Indian Tier 2/3 cities. You speak the user's language — if they write in Hindi (Devanagari or Romanized), reply in Hindi. If English, reply in English. Mix naturally if they mix.

IMPORTANT RULES:
1. Detect the user's language from their message and ALWAYS respond in the SAME language.
2. For every symptom query, respond with EXACTLY this JSON structure — no markdown, no extra text, no backticks:
{
  "greeting": "A warm 1-line acknowledgment of their concern in their language",
  "condition_name": "Likely condition name in their language",
  "severity": "mild | moderate | severe",
  "detailed_cure": {
    "title": "Section title in their language like 'उपचार और सुझाव' or 'Treatment & Suggestions'",
    "home_remedies": ["3-4 home remedies in their language with details"],
    "medicines": ["2-3 OTC medicine suggestions with dosage guidance — remind to consult doctor"],
    "lifestyle": ["2-3 lifestyle tips in their language"],
    "warning_signs": ["2-3 red flags when they MUST see a doctor immediately"]
  },
  "specialist_type": "Which specialist to see (e.g. Neurologist, Cardiologist)",
  "specialist_reason": "Why this specialist, in their language",
  "alt_specialist_type": "Alternative specialist option",
  "alt_specialist_reason": "Why alternative, in their language",
  "follow_up_question": "A caring follow-up question in their language to understand better"
}

3. Be warm, caring, and detailed — these patients may not have easy access to doctors.
4. Always include the disclaimer that this is guidance, not diagnosis.
5. If the message is just a greeting or not symptom-related, respond with:
{"greeting": "...", "is_general": true, "message": "A helpful response in their language asking them to describe symptoms"}
6. ONLY output valid JSON. No markdown, no backticks, no explanation outside the JSON."""


class SymptomCheckRequest(BaseModel):
    message: str
    language: str = "auto"


async def _check_and_update_rate_limit(patient: Patient, db: AsyncSession) -> bool:
    """Returns True if the call is allowed, False if daily limit reached."""
    today = date.today()

    if patient.ai_calls_date != today:
        patient.ai_calls_today = 0
        patient.ai_calls_date = today

    if patient.ai_calls_today >= DAILY_AI_LIMIT:
        return False

    patient.ai_calls_today += 1
    await db.commit()
    return True


def _parse_ai_response(raw: str) -> dict:
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"is_general": True, "message": raw}


@router.post("/symptom-check")
async def symptom_check(
    request: SymptomCheckRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    allowed = await _check_and_update_rate_limit(current_patient, db)
    if not allowed:
        return {
            "success": False,
            "error": f"Daily limit reached. You can use Medora AI {DAILY_AI_LIMIT} times per day. Please try again tomorrow.",
            "limit_reached": True,
            "daily_limit": DAILY_AI_LIMIT,
        }

    remaining = DAILY_AI_LIMIT - current_patient.ai_calls_today

    # --- Primary: Gemini ---
    try:
        response = _gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=request.message,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1500,
            ),
        )
        parsed = _parse_ai_response(response.text)
        return {"success": True, "data": parsed, "remaining_calls": remaining}

    except Exception as gemini_err:
        traceback.print_exc()
        print(f"GEMINI ERROR: {type(gemini_err).__name__}: {gemini_err}")

    # --- Fallback: Anthropic ---
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        fb_response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": request.message}],
        )
        parsed = _parse_ai_response(fb_response.content[0].text)
        return {"success": True, "data": parsed, "remaining_calls": remaining}

    except Exception as anthropic_err:
        traceback.print_exc()
        print(f"ANTHROPIC FALLBACK ERROR: {type(anthropic_err).__name__}: {anthropic_err}")

    return {"success": False, "error": "AI service temporarily unavailable. Please try again later."}


@router.get("/usage")
async def get_ai_usage(
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    used = current_patient.ai_calls_today if current_patient.ai_calls_date == today else 0

    return {
        "daily_limit": DAILY_AI_LIMIT,
        "used_today": used,
        "remaining": DAILY_AI_LIMIT - used,
    }
