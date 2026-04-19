from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import httpx
from app.config import VERIFY_TOKEN
from app.bot import handle_message
from app.database import init_db
from app.database import SessionLocal, ProcessedMessage, Professional, Appointment
from app.scheduler import start_scheduler
from sqlalchemy.exc import IntegrityError
from app.vision import process_payment_receipt
from app.whatsapp import send_message



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

        # 1. Deduplicación persistente en DB
        db = SessionLocal()
        try:
            db.add(ProcessedMessage(msg_id=msg_id))
            db.commit()
        except IntegrityError:
            db.rollback()
            db.close()
            print(f"[WEBHOOK] Duplicado ignorado: {msg_id}")
            return {"status": "duplicate"}

        print(f"[WEBHOOK] phone_number_id={phone_number_id} | from={from_num} | tipo={msg_type}")

        # 2. PROCESAMIENTO DE TEXTO (Agendamiento inicial)
        if msg_type == "text":
            text = msg["text"]["body"].strip()
            print(f"[WEBHOOK] Texto recibido: '{text}'")
            await handle_message(phone_number_id, from_num, text)

        elif msg_type == "interactive":
            text = msg["interactive"]["button_reply"]["id"]
            print(f"[WEBHOOK] Botón recibido: '{text}'")
            await handle_message(phone_number_id, from_num, text)

        # 3. PROCESAMIENTO DE IMAGEN (Validación de Pago y Cierre de Turno)
        elif msg_type == "image":
            media_id = msg["image"]["id"]
            print(f"[WEBHOOK] Imagen recibida. Media ID: {media_id}")

            # A. Buscar Profesional y Turno Pendiente
            prof = db.query(Professional).filter_by(phone_number_id=phone_number_id).first()
            turno_pendiente = db.query(Appointment).filter_by(
                professional_id=prof.id,
                patient_phone=from_num,
                status="pending"
            ).first() if prof else None

            if not prof or not turno_pendiente:
                await send_message(to=from_num, text="No encontramos un turno pendiente para validar. Por favor, iniciá el agendamiento escribiendo 'Hola'.", phone_number_id=phone_number_id)
                db.close()
                return {"status": "no_context"}

            # B. Validación con Gemini Vision
            fecha_esperada = turno_pendiente.start_at[:10]
            resultado = await process_payment_receipt(
                media_id=media_id,
                expected_amount=prof.session_price,
                prof_name=prof.name,
                expected_date=fecha_esperada
            )

            if resultado.is_valid_receipt and resultado.status == "approved" and resultado.date_match:
                # C. ÉXITO: Actualizar DB
                turno_pendiente.status = "confirmed"
                turno_pendiente.is_billed = True
                db.commit()

                # D. AGENDAR EN GOOGLE CALENDAR
                try:
                    from app.calendar_service import create_event
                    event_id = await create_event(
                        calendar_id=prof.calendar_id,
                        start_time=turno_pendiente.start_at,
                        end_time=turno_pendiente.end_at,
                        summary=f"Turno: {turno_pendiente.patient_name}",
                        description=f"Pago validado por IA.\nPaciente: {turno_pendiente.patient_name}\nTel: {from_num}"
                    )
                    turno_pendiente.calendar_event_id = event_id
                    db.commit()
                except Exception as e:
                    print(f"[CALENDAR] Error al sincronizar: {e}")

                # E. MENSAJE FINAL DE CONFIRMACIÓN
                hora_turno = turno_pendiente.start_at[11:16]
                mensaje_exito = (
                    f"✅ *¡Turno Confirmado!*\n\n"
                    f"📅 *Fecha:* {fecha_esperada}\n"
                    f"⏰ *Hora:* {hora_turno} hs\n"
                    f"📍 *Dirección:* {prof.address}\n\n"
                    f"¡Te esperamos! Se ha enviado un evento a la agenda del profesional."
                )
                await send_message(to=from_num, text=mensaje_exito, phone_number_id=phone_number_id)
            
            else:
                await send_message(to=from_num, text="❌ No pudimos validar el comprobante. Por favor, verificá que el monto, la fecha y el destinatario sean correctos y volvé a enviarlo.", phone_number_id=phone_number_id)

        else:
            print(f"[WEBHOOK] Tipo no soportado: {msg_type}")

        db.close()

    except Exception as e:
        print(f"[WEBHOOK] Error crítico: {e}")
        if 'db' in locals(): db.close()

    return {"status": "ok"}





