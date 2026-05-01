def get_safe_system_prompt(base_prompt: str, mode: str = None) -> str:
    """
    Centralized AI safety wrapper.
    Ensures all AI interactions across the app enforce the non-diagnostic rule.
    """
    safety_prefix = "SAFETY INSTRUCTION: Do NOT provide medical diagnosis. Provide guidance only. You are a clinical decision-support assistant.\n"
    
    if mode == "patient":
        safety_prefix += "Constraints: base your guidance primarily on the patient's existing lab reports and current consultation notes.\n"
    elif mode == "report":
        safety_prefix += "Constraints: explicitly highlight any abnormal values and list potential next clinical steps.\n"
        
    safety_prefix += "\n"
    return f"{safety_prefix}{base_prompt}"
