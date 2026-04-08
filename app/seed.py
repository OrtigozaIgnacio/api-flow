from dotenv import load_dotenv
load_dotenv()  # cargar .env ANTES de importar database

from app.database import SessionLocal, Professional, WorkingHours, init_db

init_db()

def add_professional():
    db = SessionLocal()

    existing = db.query(Professional).filter_by(
        phone_number_id="1027318013800289"
    ).first()

    if existing:
        # Actualizar campos del existente
        existing.name              = "Martínez"
        existing.title             = "Lic."
        existing.niche             = "psychology"
        existing.address           = "Av. Corrientes 1234, CABA"
        existing.timezone          = "America/Argentina/Buenos_Aires"
        existing.country_code      = "AR"
        existing.locale            = "es_AR"
        existing.calendar_id       = "TU_CALENDAR_ID"
        existing.credentials_file  = "credentials_martinez.json"
        existing.session_minutes   = 50
        existing.slot_advance_days = 14
        existing.active            = True
        prof = existing
    else:
        prof = Professional(
            phone_number_id   = "1027318013800289",
            name              = "Martínez",
            title             = "Lic.",
            niche             = "psychology",
            address           = "Av. Corrientes 1234, CABA",
            timezone          = "America/Argentina/Buenos_Aires",
            country_code      = "AR",
            locale            = "es_AR",
            calendar_id       = "TU_CALENDAR_ID",
            credentials_file  = "credentials_martinez.json",
            session_minutes   = 50,
            slot_advance_days = 14,
            active            = True,
        )
        db.add(prof)

    db.flush()  # genera el id si es nuevo
    print(f"ID del profesional: {prof.id}")

    # Limpiar horarios anteriores
    db.query(WorkingHours).filter_by(professional_id=prof.id).delete()

    # Lunes a viernes 9 a 20 hs
    for day in range(5):
        db.add(WorkingHours(
            professional_id = prof.id,
            day_of_week     = day,
            start_time      = "09:00",
            end_time        = "20:00",
            active          = True,
        ))

    db.commit()
    print(f"Profesional '{prof.title} {prof.name}' guardado con horarios.")
    db.close()

if __name__ == "__main__":
    add_professional()