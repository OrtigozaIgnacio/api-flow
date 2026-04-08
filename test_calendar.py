# test_calendar.py — correlo con: python test_calendar.py
import asyncio
from app.database import init_db, SessionLocal, Professional
from app.calendar_service import get_available_slots

async def test():
    init_db()
    db  = SessionLocal()
    prof = db.query(Professional).first()
    db.close()

    if not prof:
        print("No hay profesionales en la DB. Corré primero: python -m app.seed")
        return

    print(f"Buscando turnos para {prof.name}...")
    slots = await get_available_slots(prof)

    if not slots:
        print("No se encontraron turnos. Revisá que el calendario esté compartido correctamente.")
        return

    for slot in slots:
        print(f"  - {slot['display']}")

asyncio.run(test())