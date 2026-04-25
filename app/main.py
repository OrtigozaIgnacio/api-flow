import os
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from app.config import VERIFY_TOKEN
from app.bot import handle_message
from app.database import init_db, SessionLocal, ProcessedMessage, Professional, Appointment
from app.scheduler import start_scheduler
from app.vision import process_payment_receipt
from app.whatsapp import send_message

app = FastAPI()

# --- SEGURIDAD DEL PANEL DE CONTROL ---
# Debes configurar esta variable en Render para proteger tu negocio
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "mi_clave_secreta_123")

def verify_admin(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Acceso denegado: API Key administrativa inválida")
    return True

# Esquema para validar los datos que vienen del Panel de Control
class ProfessionalCreate(BaseModel):
    name: str
    title: str
    niche: str
    session_price: float
    phone_number_id: str
    calendar_id: str
    timezone: str = "America/Argentina/Buenos_Aires"
    address: str = ""
    active: bool = True

@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()

# --- WEBHOOK DE WHATSAPP (EXISTENTE) ---

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

        db = SessionLocal()
        try:
            db.add(ProcessedMessage(msg_id=msg_id))
            db.commit()
        except IntegrityError:
            db.rollback()
            db.close()
            return {"status": "duplicate"}

        if msg_type == "text":
            text = msg["text"]["body"].strip()
            await handle_message(phone_number_id, from_num, text)

        elif msg_type == "interactive":
            text = msg["interactive"]["button_reply"]["id"]
            await handle_message(phone_number_id, from_num, text)

        elif msg_type == "image":
            media_id = msg["image"]["id"]
            prof = db.query(Professional).filter_by(phone_number_id=phone_number_id).first()
            turno = db.query(Appointment).filter_by(patient_phone=from_num, status="pending").first()

            if prof and turno:
                res = await process_payment_receipt(media_id, prof.session_price, prof.name, turno.start_at[:10])
                if res.is_valid_receipt and res.status == "approved" and res.date_match:
                    turno.status = "confirmed"
                    turno.is_billed = True
                    # Aquí podrías llamar a create_event de calendar_service
                    db.commit()
                    await send_message(to=from_num, text="✅ ¡Pago validado!", phone_number_id=phone_number_id)
                else:
                    await send_message(to=from_num, text="❌ Comprobante inválido.", phone_number_id=phone_number_id)
        db.close()
    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")
    return {"status": "ok"}

# --- ENDPOINTS PARA EL PANEL DE CONTROL (NUEVOS) ---

@app.get("/admin/stats", dependencies=[Depends(verify_admin)])
async def get_global_stats():
    """Métricas para el Dashboard principal."""
    db = SessionLocal()
    total_profs = db.query(Professional).count()
    active_profs = db.query(Professional).filter_by(active=True).count()
    total_confirmed = db.query(Appointment).filter_by(status="confirmed").count()
    
    # Estimación de ingresos (30 USD por cada activo)
    estimated_mrr = active_profs * 30
    
    db.close()
    return {
        "total_professionals": total_profs,
        "active_professionals": active_profs,
        "total_appointments_confirmed": total_confirmed,
        "estimated_mrr": estimated_mrr
    }

@app.get("/admin/professionals", dependencies=[Depends(verify_admin)])
async def list_professionals():
    """Lista de clientes para la tabla de gestión."""
    db = SessionLocal()
    profs = db.query(Professional).all()
    db.close()
    return profs

@app.post("/admin/professionals/{prof_id}/toggle", dependencies=[Depends(verify_admin)])
async def toggle_professional(prof_id: str):
    """El interruptor para activar/suspender clientes."""
    db = SessionLocal()
    prof = db.query(Professional).filter_by(id=prof_id).first()
    if not prof:
        db.close()
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    
    prof.active = not prof.active
    new_status = "activado" if prof.active else "suspendido"
    db.commit()
    db.close()
    return {"status": "success", "message": f"Profesional {new_status}"}

@app.post("/admin/professionals", dependencies=[Depends(verify_admin)])
async def create_professional(prof_data: ProfessionalCreate):
    """Crea un nuevo cliente (Profesional) en la base de datos."""
    db = SessionLocal()
    try:
        # Creamos la instancia del modelo de SQLAlchemy
        new_prof = Professional(
            name=prof_data.name,
            title=prof_data.title,
            niche=prof_data.niche,
            session_price=prof_data.session_price,
            phone_number_id=prof_data.phone_number_id,
            calendar_id=prof_data.calendar_id,
            timezone=prof_data.timezone,
            address=prof_data.address,
            active=prof_data.active
        )
        
        db.add(new_prof)
        db.commit()
        db.refresh(new_prof)
        return {"status": "success", "message": "Profesional creado", "id": new_prof.id}
    
    except Exception as e:
        db.rollback()
        print(f"[ADMIN] Error al crear profesional: {e}")
        raise HTTPException(status_code=500, detail="Error interno al guardar en la base de datos")
    finally:
        db.close()