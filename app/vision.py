# app/vision.py
import os
import httpx
from pydantic import BaseModel
from google import genai
from typing import Literal, Optional

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class PaymentValidation(BaseModel):
    is_valid_receipt: bool
    status: Literal["approved", "pending", "rejected", "unclear"]
    amount: Optional[float]
    recipient_name: Optional[str]
    date_on_receipt: Optional[str] # Fecha que la IA leyó en el ticket
    date_match: bool              # ¿Coincide con la fecha del turno?
    confidence_score: float

async def process_payment_receipt(media_id: str, expected_amount: float, prof_name: str, expected_date: str) -> PaymentValidation:
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    
    async with httpx.AsyncClient() as http_client:
        res = await http_client.get(f"https://graph.facebook.com/v19.0/{media_id}", headers=headers)
        media_url = res.json().get("url")
        img_res = await http_client.get(media_url, headers=headers)
        img_bytes = img_res.content

    # EL PROMPT: Ahora incluye la variable de fecha
    prompt = f"""
    Analiza este comprobante de transferencia y extrae la información para validarla contra estos datos oficiales:
    - Destinatario esperado: {prof_name}
    - Monto esperado: {expected_amount}
    - Fecha del turno: {expected_date} (El pago debería ser de hoy o máximo 48hs antes).

    Tu tarea:
    1. Verifica si el nombre del destinatario coincide razonablemente.
    2. Verifica si el monto coincide exactamente.
    3. Extrae la fecha que figura en el comprobante y compárala con la fecha del turno.
    
    Responde estrictamente en formato JSON siguiendo el esquema proporcionado.
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[{"mime_type": "image/jpeg", "data": img_bytes}, prompt],
        config={
            'response_mime_type': 'application/json', 
            'response_schema': PaymentValidation,
            'temperature': 0.0
        }
    )
    
    return PaymentValidation.model_validate(response.parsed)