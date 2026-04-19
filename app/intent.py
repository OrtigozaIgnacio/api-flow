import os
from pydantic import BaseModel
from typing import Literal
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 1. Contrato de salida (Actualizado con TODAS las intenciones que usa tu bot.py)
class IntentOutput(BaseModel):
    intent: Literal[
        "schedule", "info", "see_more", "specify_preference", 
        "confirm", "cancel", "unclear", "request_other", 
        "select_a", "select_b", "select_c"
    ]
    confidence: float

INTENTS_PROMPTS = {
    "menu": "El paciente quiere agendar (schedule), pedir info (info) o saluda (unclear).",
    "awaiting_slot_selection": "El paciente elige la opción A (select_a), B (select_b), C (select_c) o pide otros horarios (request_other).",
    "awaiting_preference": "El paciente indica cuándo prefiere su turno (specify_preference) o pide ver más opciones (see_more).",
    "awaiting_confirmation": "El paciente confirma (confirm) o cancela (cancel) su asistencia."
}

async def classify_intent(step: str, user_text: str, local_time_str: str = "") -> str:
    if step not in INTENTS_PROMPTS:
        return "unclear"

    context = INTENTS_PROMPTS[step]
    
    # Inyectamos el reloj local del profesional si nos lo pasan
    time_context = f"\nContexto temporal: Hoy es {local_time_str} en la zona horaria del consultorio." if local_time_str else ""
    
    prompt = f"""{time_context}
    Contexto de la conversación: {context}
    Mensaje del paciente: "{user_text}"
    
    Analiza el mensaje y determina la intención técnica correspondiente estrictamente en formato JSON.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': IntentOutput,
                'temperature': 0.0  # Cero creatividad para evitar alucinaciones
            },
        )
        
        output = IntentOutput.model_validate(response.parsed)
        
        # Si la IA no está muy segura, es mejor que el bot pida aclaración
        if output.confidence < 0.6:
            return "unclear"
            
        return output.intent

    except Exception as e:
        print(f"[INTENT] Error en clasificación estructurada: {e}")
        return "unclear"