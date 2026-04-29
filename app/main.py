import os
from datetime import datetime, timedelta
from typing import List
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import VERIFY_TOKEN
from app.bot import handle_message
from app.database import init_db, SessionLocal, ProcessedMessage, Professional, Appointment, User, WorkingHours
from app.scheduler import start_scheduler
from app.vision import process_payment_receipt
from app.whatsapp import send_message

app = FastAPI()

# --- 1. CONFIGURACIÓN DE SEGURIDAD (JWT Y HASHING) ---
SECRET_KEY = os.getenv("JWT_SECRET", "una_clave_muy_secreta_para_caleta_olivia")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 2. MIDDLEWARES Y ARCHIVOS ESTÁTICOS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()

# --- 3. DEPENDENCIAS DE AUTENTICACIÓN ---
def verify_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        print("[DEBUG SECURITY] Token faltante o formato incorrecto")
        raise HTTPException(status_code=401, detail="Sesión no iniciada")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        print(f"[DEBUG SECURITY] Error al decodificar token: {e}")
        raise HTTPException(status_code=401, detail="Sesión expirada")

def verify_admin(authorization: str = Header(None)):
    payload = verify_token(authorization)
    if payload.get("role") != "superadmin":
        print(f"[DEBUG SECURITY] Rol insuficiente: {payload.get('role')}")
        raise HTTPException(status_code=403, detail="Acceso restringido")
    return payload

# --- 4. ESQUEMAS (PYDANTIC) ---
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

class ProfessionalUpdate(BaseModel):
    name: str
    title: str
    niche: str
    session_price: float
    session_minutes: int

class WorkingHourItem(BaseModel):
    day_of_week: int
    active: bool
    start_time: str
    end_time: str

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

# --- 5. ENDPOINTS DE CUENTA Y LOGIN ---
@app.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    
    print(f"[DEBUG LOGIN] Intento de login para: {email}")
    
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        print(f"[DEBUG LOGIN] Usuario no encontrado")
        db.close()
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    if not verify_password(password, user.password_hash):
        print(f"[DEBUG LOGIN] Contraseña incorrecta")
        db.close()
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    role_name = user.role.value if hasattr(user.role, 'value') else user.role
    
    access_token = create_access_token(data={
        "sub": user.email, 
        "role": role_name,
        "prof_id": user.professional_id
    })
    db.close()
    return {"access_token": access_token, "token_type": "bearer"}

@app.put("/auth/change-password")
async def change_password(data: PasswordChange, token_data: dict = Depends(verify_token)):
    email = token_data.get("sub")
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(data.old_password, user.password_hash):
        db.close()
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    
    user.password_hash = pwd_context.hash(data.new_password)
    db.commit()
    db.close()
    return {"status": "success"}

# --- 6. ENDPOINTS DEL PANEL DE CLIENTE (PROFESIONAL) ---

@app.get("/client/me")
async def get_client_me(token_data: dict = Depends(verify_token)):
    prof_id = token_data.get("prof_id")
    if not prof_id:
        raise HTTPException(status_code=403, detail="No sos un profesional")
    
    db = SessionLocal()
    prof = db.query(Professional).filter_by(id=prof_id).first()
    if not prof:
        db.close()
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    week_count = db.query(Appointment).filter(
        Appointment.professional_id == prof_id,
        Appointment.created_at >= week_ago
    ).count()
    
    total_patients = db.query(func.count(func.distinct(Appointment.patient_phone))).filter_by(professional_id=prof_id).scalar()
    
    stats = {
        "week_count": week_count,
        "estimated_revenue": week_count * prof.session_price,
        "total_patients": total_patients
    }
    
    response = {
        "name": f"{prof.title} {prof.name}",
        "full_name": prof.name,
        "title": prof.title,
        "niche": prof.niche,
        "session_price": prof.session_price,
        "session_minutes": prof.session_minutes,
        "stats": stats
    }
    db.close()
    return response

@app.put("/client/settings")
async def update_client_settings(data: ProfessionalUpdate, token_data: dict = Depends(verify_token)):
    prof_id = token_data.get("prof_id")
    if not prof_id:
        raise HTTPException(status_code=403, detail="No sos un profesional")
    
    db = SessionLocal()
    prof = db.query(Professional).filter_by(id=prof_id).first()
    if not prof:
        db.close()
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    
    prof.name = data.name
    prof.title = data.title
    prof.niche = data.niche
    prof.session_price = data.session_price
    prof.session_minutes = data.session_minutes
    
    db.commit()
    db.close()
    return {"status": "success"}

@app.get("/client/working-hours")
async def get_client_working_hours(token_data: dict = Depends(verify_token)):
    prof_id = token_data.get("prof_id")
    if not prof_id:
        raise HTTPException(status_code=403, detail="No sos un profesional")
    
    db = SessionLocal()
    hours = db.query(WorkingHours).filter_by(professional_id=prof_id).order_by(WorkingHours.day_of_week).all()
    db.close()
    return hours

@app.post("/client/working-hours")
async def update_client_working_hours(data: List[WorkingHourItem], token_data: dict = Depends(verify_token)):
    prof_id = token_data.get("prof_id")
    if not prof_id:
        raise HTTPException(status_code=403, detail="No sos un profesional")
    
    db = SessionLocal()
    try:
        for item in data:
            row = db.query(WorkingHours).filter_by(professional_id=prof_id, day_of_week=item.day_of_week).first()
            if row:
                row.active = item.active
                row.start_time = item.start_time
                row.end_time = item.end_time
            else:
                new_row = WorkingHours(
                    professional_id=prof_id,
                    day_of_week=item.day_of_week,
                    active=item.active,
                    start_time=item.start_time,
                    end_time=item.end_time
                )
                db.add(new_row)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/client/appointments")
async def get_client_appointments(token_data: dict = Depends(verify_token)):
    prof_id = token_data.get("prof_id")
    if not prof_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    
    db = SessionLocal()
    appts = db.query(Appointment).filter_by(professional_id=prof_id).order_by(Appointment.start_at.desc()).limit(50).all()
    db.close()
    return appts

# --- 7. ENDPOINTS DEL PANEL SUPERADMIN ---

@app.get("/admin/stats", dependencies=[Depends(verify_admin)])
async def get_admin_stats():
    db = SessionLocal()
    total_profs = db.query(Professional).count()
    active_profs = db.query(Professional).filter_by(active=True).count()
    mrr = active_profs * 35 
    total_appts = db.query(Appointment).filter_by(status="confirmed").count()
    db.close()
    return {
        "total_professionals": total_profs,
        "active_professionals": active_profs,
        "estimated_mrr": mrr,
        "total_appointments_confirmed": total_appts
    }

@app.get("/admin/professionals", dependencies=[Depends(verify_admin)])
async def get_professionals():
    db = SessionLocal()
    profs = db.query(Professional).all()
    db.close()
    return profs

@app.post("/admin/professionals", dependencies=[Depends(verify_admin)])
async def create_professional(prof_data: ProfessionalCreate):
    db = SessionLocal()
    try:
        new_prof = Professional(
            name=prof_data.name, title=prof_data.title, niche=prof_data.niche,
            session_price=prof_data.session_price, phone_number_id=prof_data.phone_number_id,
            calendar_id=prof_data.calendar_id, timezone=prof_data.timezone,
            address=prof_data.address, active=prof_data.active,
            credentials_file="", schedule="", country_code="AR", locale="es_AR",
            session_minutes=50, slot_advance_days=14
        )
        db.add(new_prof)
        db.commit()
        db.refresh(new_prof)
        return {"status": "success", "id": new_prof.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/admin/professionals/{prof_id}/toggle", dependencies=[Depends(verify_admin)])
async def toggle_professional(prof_id: str):
    db = SessionLocal()
    prof = db.query(Professional).filter_by(id=prof_id).first()
    if prof:
        prof.active = not prof.active
        db.commit()
    db.close()
    return {"status": "success"}

# --- 8. WEBHOOK DE WHATSAPP ---
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Token inválido")

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages")

        if not messages: return {"status": "no_message"}

        msg = messages[0]
        db = SessionLocal()
        try:
            db.add(ProcessedMessage(msg_id=msg["id"]))
            db.commit()
        except IntegrityError:
            db.rollback()
            db.close()
            return {"status": "duplicate"}

        phone_id = change["metadata"]["phone_number_id"]
        from_num = msg["from"]
        msg_type = msg.get("type")

        if msg_type == "text":
            await handle_message(phone_id, from_num, msg["text"]["body"].strip())
        elif msg_type == "interactive":
            await handle_message(phone_id, from_num, msg["interactive"]["button_reply"]["id"])
        elif msg_type == "image":
            prof = db.query(Professional).filter_by(phone_number_id=phone_id).first()
            turno = db.query(Appointment).filter_by(patient_phone=from_num, status="pending").first()
            if prof and turno:
                res = await process_payment_receipt(msg["image"]["id"], prof.session_price, prof.name, turno.start_at[:10])
                if res.is_valid_receipt and res.status == "approved" and res.date_match:
                    turno.status = "confirmed"
                    turno.is_billed = True
                    db.commit()
                    await send_message(to=from_num, text="✅ ¡Pago validado!", phone_number_id=phone_id)
                else:
                    await send_message(to=from_num, text="❌ Comprobante inválido.", phone_number_id=phone_id)
        db.close()
    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")
    return {"status": "ok"}