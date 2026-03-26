import json
import traceback

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from anthropic import Anthropic

from app.core.config import settings
from app.core.dependencies import get_current_patient
from app.models.patient import Patient

router = APIRouter(prefix="/patient/ai", tags=["Patient AI"])

SYSTEM_PROMPT = """You are "Medora AI", a compassionate health assistant for patients in Indian Tier 2/3 cities. You speak the user's language — if they write in Hindi (Devanagari or Romanized), reply in Hindi. If English, reply in English. Mix naturally if they mix.

IMPORTANT RULES:
1. Detect the user's language from their message and ALWAYS respond in the SAME language.
2. For every symptom query, respond with EXACTLY this JSON structure — no markdown, no extra text:
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
{"greeting": "...", "is_general": true, "message": "A helpful response in their language asking them to describe symptoms"}"""


class SymptomCheckRequest(BaseModel):
    message: str
    language: str = "hi"


@router.post("/symptom-check")
async def symptom_check(
    request: SymptomCheckRequest,
    current_patient: Patient = Depends(get_current_patient),
):
    try:
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": request.message}],
        )
        raw = response.content[0].text

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
            return {"success": True, "data": parsed}
        except json.JSONDecodeError:
            return {"success": True, "data": {"is_general": True, "message": raw}}

    except Exception as e:
        traceback.print_exc()
        print(f"AI ERROR: {type(e).__name__}: {str(e)}")
        return {"success": False, "error": "AI service temporarily unavailable", "detail": str(e)}
