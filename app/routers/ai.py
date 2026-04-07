import json
import traceback
from datetime import date

from groq import Groq
from google import genai
from google.genai import types as genai_types
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, func

from app.core.config import settings
from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.patient import Patient

router = APIRouter(prefix="/patient/ai", tags=["Patient AI"])

# Gemini client (new SDK)
_gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
_groq_client = Groq(api_key=settings.GROQ_API_KEY)

DAILY_AI_LIMIT = 5

SYSTEM_PROMPT = """You are "Medora AI", a compassionate health assistant for patients in Indian Tier 2/3 cities.

LANGUAGE RULES (VERY IMPORTANT):
1. If the user writes in ENGLISH → Reply in CLEAR, PROFESSIONAL English. Use proper sentences, not WhatsApp/texting slang. Keep the tone warm and caring but professional — like a doctor explaining to a patient. Example: "It sounds like you're experiencing a headache. Here are some suggestions that may help you feel better."
2. If the user writes in HINGLISH (Hindi words in Roman script mixed with English, like "mujhe headache ho raha hai") → Reply in HINGLISH. Use Roman Hindi mixed with English. Keep medical terms, medicine names, dosages, and commonly understood words in English. Example: "Aapko paracetamol 500mg le sakte ho, din mein 2-3 baar. Zyada pani piyo aur rest karo."
3. If the user writes in pure HINDI (Devanagari script like "मुझे सिरदर्द हो रहा है") → Reply in Hindi Devanagari, but keep medicine names and dosages in English.
4. NEVER reply in pure formal Hindi if the user wrote in casual Hinglish. Match their tone and script.

RESPONSE FORMAT:
For every symptom query, respond with EXACTLY this JSON structure — no markdown, no extra text, no backticks:
{
  "greeting": "A warm 1-line acknowledgment in the SAME language/script the user used",
  "condition_name": "Likely condition name (use English medical term + local language term if helpful)",
  "severity": "mild | moderate | severe",
  "detailed_cure": {
    "title": "Treatment & Suggestions (or Hinglish/Hindi equivalent matching user's language)",
    "home_remedies": ["3-4 home remedies in user's language style with practical details"],
    "medicines": ["2-3 OTC medicine suggestions with dosage — medicine names ALWAYS in English — remind to consult doctor"],
    "lifestyle": ["2-3 lifestyle tips in user's language style"],
    "warning_signs": ["2-3 red flags when they MUST see a doctor immediately"]
  },
  "specialist_type": "English name of specialist (e.g. Neurologist, Cardiologist, General Physician)",
  "specialist_reason": "Why this specialist, in user's language style",
  "alt_specialist_type": "Alternative specialist in English",
  "alt_specialist_reason": "Why alternative, in user's language style",
  "follow_up_question": "A caring follow-up question in user's language style"
}

OTHER RULES:
- Be warm, caring, and detailed — these patients may not have easy access to doctors.
- Always include the disclaimer that this is AI guidance, not a medical diagnosis.
- Do NOT suggest any specific doctor names or hospital names. Only mention the specialist TYPE needed (like "Neurologist" or "Dermatologist"). The app will handle showing available doctors.
- If the message is just a greeting or not symptom-related, respond with:
  {"greeting": "...", "is_general": true, "message": "A helpful response in user's language asking them to describe symptoms"}
- When replying in English, use complete proper sentences. Avoid casual slang, abbreviations, or texting language. Be warm but professional.
- ONLY output valid JSON. No markdown, no backticks, no explanation outside the JSON."""


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


async def _find_matching_doctors(specialist_type: str, org_id, db: AsyncSession) -> list:
    """Find doctors in the patient's organization matching the recommended specialty."""
    if not specialist_type:
        return []

    # Search for doctors whose specialization matches (case-insensitive partial match)
    query = select(Doctor).where(
        Doctor.organization_id == org_id,
        func.lower(Doctor.specialization).contains(specialist_type.lower()),
        Doctor.is_active == True,
    )
    result = await db.execute(query)
    doctors = result.scalars().all()

    return [
        {
            "id": str(doc.id),
            "name": f"Dr. {doc.name}",
            "specialization": doc.specialization,
            "experience_years": doc.experience_years,
        }
        for doc in doctors
    ]


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

        # Find matching doctors from patient's organization
        recommended_doctors = []
        alt_doctors = []
        if not parsed.get("is_general"):
            specialist = parsed.get("specialist_type", "")
            alt_specialist = parsed.get("alt_specialist_type", "")
            recommended_doctors = await _find_matching_doctors(specialist, current_patient.organization_id, db)
            if alt_specialist and alt_specialist != specialist:
                alt_doctors = await _find_matching_doctors(alt_specialist, current_patient.organization_id, db)

        parsed["recommended_doctors"] = recommended_doctors
        parsed["alt_recommended_doctors"] = alt_doctors

        return {"success": True, "data": parsed, "remaining_calls": remaining}

    except Exception as gemini_err:
        traceback.print_exc()
        print(f"GEMINI ERROR: {type(gemini_err).__name__}: {gemini_err}")

    # --- Fallback: Groq (Llama 3) ---
    try:
        fb_response = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.message},
            ],
            max_tokens=1500,
            temperature=0.7,
        )
        parsed = _parse_ai_response(fb_response.choices[0].message.content)

        # Find matching doctors from patient's organization
        recommended_doctors = []
        alt_doctors = []
        if not parsed.get("is_general"):
            specialist = parsed.get("specialist_type", "")
            alt_specialist = parsed.get("alt_specialist_type", "")
            recommended_doctors = await _find_matching_doctors(specialist, current_patient.organization_id, db)
            if alt_specialist and alt_specialist != specialist:
                alt_doctors = await _find_matching_doctors(alt_specialist, current_patient.organization_id, db)

        parsed["recommended_doctors"] = recommended_doctors
        parsed["alt_recommended_doctors"] = alt_doctors

        return {"success": True, "data": parsed, "remaining_calls": remaining}

    except Exception as groq_err:
        traceback.print_exc()
        print(f"GROQ FALLBACK ERROR: {type(groq_err).__name__}: {groq_err}")

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
