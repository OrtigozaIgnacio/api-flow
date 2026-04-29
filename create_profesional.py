import uuid
from datetime import datetime, timedelta
from app.database import SessionLocal, User, UserRole, Professional, Appointment, init_db
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_test_professional():
    init_db()
    db = SessionLocal()

    # Credenciales de acceso para tu cliente de prueba
    email = "doctor@test.com"
    password = "password123"

    # Verificamos si ya existe
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        print("⚠️ El usuario de prueba ya existe. Podés loguearte directamente.")
        db.close()
        return

    try:
        # 1. Creamos el Perfil del Profesional
        prof_id = str(uuid.uuid4())
        new_prof = Professional(
            id=prof_id,
            name="Gregory House",
            title="Dr.",
            niche="Diagnóstico Médico",
            session_price=25000.0,
            phone_number_id="123456789_test",
            calendar_id="house@test.com",
            timezone="America/Argentina/Buenos_Aires",
            active=True,
            credentials_file="",
            schedule="Lunes a Viernes 9 a 18 hs"
        )
        db.add(new_prof)

        # 2. Creamos su Usuario (El acceso al panel)
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=pwd_context.hash(password),
            role=UserRole.PROFESSIONAL, # <--- Rol clave
            professional_id=prof_id     # <--- Lo vinculamos
        )
        db.add(new_user)

        # 3. Le inyectamos turnos de prueba para ver el Dashboard
        now = datetime.utcnow()
        apt1 = Appointment(
            professional_id=prof_id,
            patient_phone="5491122334455",
            patient_name="Juan Pérez",
            start_at=(now + timedelta(days=1, hours=2)).isoformat(),
            end_at=(now + timedelta(days=1, hours=3)).isoformat(),
            status="confirmed",
            is_billed=True
        )
        apt2 = Appointment(
            professional_id=prof_id,
            patient_phone="5491199887766",
            patient_name="María Gómez",
            start_at=(now + timedelta(days=2)).isoformat(),
            end_at=(now + timedelta(days=2, hours=1)).isoformat(),
            status="pending",
            is_billed=False
        )
        db.add(apt1)
        db.add(apt2)

        db.commit()
        print("✅ Profesional de prueba y turnos creados con éxito.")
        print(f"📧 Email: {email}")
        print(f"🔑 Contraseña: {password}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error al crear los datos: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_test_professional()