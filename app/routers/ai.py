import base64
import json
import logging
import traceback
from datetime import date
from typing import Optional

from groq import Groq
from google import genai
from google.genai import types as genai_types
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from sqlalchemy import select, func

from app.core.config import settings
from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.utils.ai_wrapper import get_safe_system_prompt

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


REPORT_ANALYSIS_PROMPT = """You are Medora AI, a helpful and professional medical report analyzer.

TASK: Analyze the uploaded medical report image and explain the findings clearly.

RULES:
- Identify the type of report (blood test, X-ray, MRI, urine test, etc.)
- List each parameter/finding with its value and whether it is NORMAL, HIGH, or LOW
- Explain what abnormal values might indicate in simple, easy-to-understand language
- If the user asked a specific question about the report, answer that directly
- Do NOT invent or fabricate any data — only analyze what is visible in the image
- Keep medical terms but always add a simple explanation in parentheses
- If the image is unclear or not a medical report, say so honestly

LANGUAGE RULES (same as main chat):
- If user writes in English → reply in professional English
- If user writes in Hinglish → reply in Hinglish
- If user writes in Hindi → reply in Hindi Devanagari
- Medicine/parameter names always in English

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
    "recommendations": "Please upload a clear image of your medical report (blood test, X-ray, prescription, etc.)",
    "disclaimer": "This is an AI-powered analysis by Medora AI. Please consult a verified Medora doctor for official diagnosis and treatment."
}"""


class SymptomCheckRequest(BaseModel):
    message: str
    language: str = "auto"
    image_base64: Optional[str] = None   # Base64-encoded image string (no data:image prefix)
    mime_type: Optional[str] = None      # "image/png", "image/jpeg", etc.


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


def _parse_report_response(raw_text: str) -> dict:
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
        parsed["is_report_analysis"] = True
        return parsed
    except json.JSONDecodeError:
        return {
            "is_report_analysis": True,
            "report_type": "Analysis",
            "summary": raw_text,
            "findings": [],
            "concerns": [],
            "recommendations": "",
            "disclaimer": "This is an AI-powered analysis by Medora AI. Please consult a verified Medora doctor for official diagnosis and treatment.",
        }


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

    has_image = bool(request.image_base64 and request.mime_type)

    # --- Image analysis path: Gemini Vision only, no Groq fallback ---
    if has_image:
        try:
            user_text = request.message if request.message else "Analyze this medical report and explain the findings."
            image_bytes = base64.b64decode(request.image_base64)
            parts = [
                genai_types.Part.from_bytes(data=image_bytes, mime_type=request.mime_type),
                genai_types.Part.from_text(text=user_text),
            ]
            response = _gemini_client.models.generate_content(
                model=settings.GEMINI_VISION_MODEL,
                contents=parts,
                config=genai_types.GenerateContentConfig(
                    system_instruction=get_safe_system_prompt(REPORT_ANALYSIS_PROMPT, mode="report"),
                    max_output_tokens=2000,
                ),
            )
            parsed_report = _parse_report_response(response.text)
            return {"success": True, "data": parsed_report, "remaining_calls": remaining}

        except Exception as img_err:
            traceback.print_exc()
            logger.error("gemini_vision_error type=%s", type(img_err).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable. Please try again shortly.",
            )

    # --- Primary: Gemini (text-only) ---
    try:
        response = _gemini_client.models.generate_content(
            model=settings.GEMINI_TEXT_MODEL,
            contents=request.message,
            config=genai_types.GenerateContentConfig(
                system_instruction=get_safe_system_prompt(SYSTEM_PROMPT, mode="patient"),
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
        logger.error("gemini_text_error type=%s", type(gemini_err).__name__)

    # --- Fallback: Groq (text-only) ---
    try:
        fb_response = _groq_client.chat.completions.create(
            model=settings.GROQ_TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": get_safe_system_prompt(SYSTEM_PROMPT, mode="patient")
                },
                {
                    "role": "user",
                    "content": request.message
                }
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
        logger.error("groq_fallback_error type=%s", type(groq_err).__name__)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI service temporarily unavailable. Please try again shortly.",
    )


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


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_patient: Patient = Depends(get_current_patient),
):
    """
    Transcribe an audio recording using Groq Whisper.
    Accepts any audio format supported by Whisper (m4a, mp4, webm, wav, mp3, etc.)
    Returns { "text": "transcribed text" }
    """
    import tempfile, os

    SUPPORTED = {".m4a", ".mp4", ".webm", ".wav", ".mp3", ".ogg", ".flac"}
    ext = os.path.splitext(file.filename or "audio.m4a")[1].lower() or ".m4a"
    if ext not in SUPPORTED:
        raise HTTPException(status_code=415, detail=f"Unsupported audio format: {ext}")

    audio_bytes = await file.read()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB).")

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            transcription = _groq_client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), audio_file),
                model="whisper-large-v3-turbo",
                response_format="json",
            )

        os.unlink(tmp_path)
        return {"text": transcription.text.strip()}

    except HTTPException:
        raise
    except Exception as err:
        traceback.print_exc()
        print(f"TRANSCRIPTION ERROR: {type(err).__name__}: {err}")
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again.")


