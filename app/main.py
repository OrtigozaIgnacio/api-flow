from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import httpx
from app.config import VERIFY_TOKEN
from app.bot import handle_message
from app.database import init_db
from app.database import SessionLocal, ProcessedMessage
from app.scheduler import start_scheduler
from sqlalchemy.exc import IntegrityError

app = FastAPI()

@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Token inválido")


@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()

    try:
        entry    = body["entry"][0]
        change   = entry["changes"][0]["value"]
        messages = change.get("messages")

        if not messages:
            return {"status": "no_message"}

        phone_number_id = change["metadata"]["phone_number_id"]
        msg             = messages[0]
        msg_id          = msg["id"]
        from_num        = msg["from"]
        msg_type        = msg.get("type")

        # Deduplicación persistente en DB
        db = SessionLocal()
        try:
            db.add(ProcessedMessage(msg_id=msg_id))
            db.commit()
        except IntegrityError:
            db.rollback()
            db.close()
            print(f"[WEBHOOK] Duplicado ignorado (race condition): {msg_id}")
            return {"status": "duplicate"}
        finally:
            db.close()

        print(f"[WEBHOOK] phone_number_id={phone_number_id} | from={from_num} | tipo={msg_type}")

        if msg_type == "text":
            text = msg["text"]["body"].strip()
        elif msg_type == "interactive":
            text = msg["interactive"]["button_reply"]["id"]
        else:
            print(f"[WEBHOOK] Tipo no soportado: {msg_type}")
            return {"status": "unsupported_type"}

        print(f"[WEBHOOK] Texto recibido: '{text}'")
        await handle_message(phone_number_id, from_num, text)

    except (KeyError, IndexError) as e:
        print(f"[WEBHOOK] Error parseando body: {e}")

    return {"status": "ok"}


def _normalize_phone(phone: str) -> str:
    """
    Meta a veces rechaza números argentinos con el 9 incluido.
    Si el envío falla, el fallback intenta sin el 9.
    """
    phone = phone.strip().lstrip("+")
    return phone


async def send_message(to: str, text: str, phone_number_id: str):
    from app.config import WHATSAPP_TOKEN
    url     = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    # Intentar primero con el número tal como llegó
    # Si falla 131030, intentar sin el 9 (formato alternativo Argentina)
    numbers_to_try = [to]
    if to.startswith("549") and len(to) == 13:
        numbers_to_try.append("54" + to[3:])  # sacar el 9

    async with httpx.AsyncClient() as client:
        for number in numbers_to_try:
            payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": text},
            }
            print(f"[SEND] Intentando enviar a {number}")
            try:
                response = await client.post(url, json=payload, headers=headers)
                print(f"[SEND] Respuesta Meta: {response.status_code}")
                if response.status_code == 200:
                    return  # éxito
                data = response.json()
                if data.get("error", {}).get("code") == 131030 and len(numbers_to_try) > 1:
                    print(f"[SEND] Número {number} no autorizado, probando formato alternativo...")
                    continue
                response.raise_for_status()
            except Exception as e:
                print(f"[SEND] ERROR: {e}")
                if number == numbers_to_try[-1]:
                    raise