import os
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

INTENTS = {
    "menu": {
        "options": ["schedule", "info", "unclear"],
        "prompt": (
            "Sos el asistente de un profesional de salud. "
            "El paciente acaba de escribir su primer mensaje o volvió al inicio. "
            "Si el paciente quiere sacar turno, reservar, agendar, o dice que sí cuando "
            "le preguntamos si quiere agendar, la intención es schedule. "
            "Si pregunta por dirección, horarios, dónde queda, cuánto sale, o información "
            "del consultorio, la intención es info. "
            "Si saluda, dice hola, o el mensaje es ambiguo, la intención es unclear."
        ),
    },
    "awaiting_slot_selection": {
        "options": ["select_a", "select_b", "select_c", "request_other", "unclear"],
        "prompt": (
            "El paciente está eligiendo entre tres turnos disponibles que le mostramos. "
            "El turno A es el primero, B el segundo, C el tercero. "
            "Si menciona el primero, lunes, o cualquier referencia al turno A, es select_a. "
            "Si menciona el segundo, martes, o cualquier referencia al turno B, es select_b. "
            "Si menciona el tercero, miércoles, o cualquier referencia al turno C, es select_c. "
            "Si dice que ninguno le viene, que no puede en esos horarios, que quiere otros "
            "turnos, o cualquier rechazo de las opciones, la intención es request_other."
        ),
    },
    "awaiting_preference": {
        "options": ["see_more", "specify_preference", "unclear"],
        "prompt": (
            "El paciente no pudo con los turnos ofrecidos y le preguntamos qué prefiere. "
            "Si quiere ver más opciones sin especificar día o franja, es see_more. "
            "Si menciona un día, una franja horaria, una semana específica, o cualquier "
            "preferencia concreta de cuándo puede, es specify_preference."
        ),
    },
    "awaiting_confirmation": {
        "options": ["confirm", "cancel", "unclear"],
        "prompt": (
            "El paciente tiene un turno reservado y le preguntamos si va a poder venir. "
            "Cualquier respuesta afirmativa, confirmación, o que indique que va a ir es confirm. "
            "Cualquier negación, que no puede, que quiere cancelar o no va a poder ir es cancel."
        ),
    },
}


async def classify_intent(step: str, user_text: str) -> str:
    if step not in INTENTS:
        return "unclear"

    config      = INTENTS[step]
    options     = config["options"]
    context     = config["prompt"]
    options_str = ", ".join(options)

    prompt = (
        f"{context}\n\n"
        f"El paciente escribió: \"{user_text}\"\n\n"
        f"Respondé ÚNICAMENTE con una de estas opciones exactas, sin explicación ni puntos: "
        f"{options_str}"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        intent = response.text.strip().lower().replace(".", "")
        return intent if intent in options else "unclear"

    except Exception as e:
        print(f"[INTENT] Error Gemini: {e}")
        return "unclear"