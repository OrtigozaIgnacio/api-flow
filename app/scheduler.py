import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

TIMEZONE = "America/Argentina/Buenos_Aires"
TZ       = ZoneInfo(TIMEZONE)

# Usamos la misma DB de Supabase para evitar que Render borre los jobs
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db")

jobstores = {
    "default": SQLAlchemyJobStore(url=DATABASE_URL)
}

scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=TIMEZONE)


def start_scheduler():
    if not scheduler.running:
        scheduler.start()


async def _send_reminder(
    phone_number_id: str,
    patient_phone: str,
    slot_display: str,
    prof_name: str,
):
    """Se ejecuta automáticamente 24 hs antes del turno."""
    from app.main import send_message
    from app.database import SessionLocal, ConversationSession
    import json

    msg = (
        f"¡Hola! Te recuerdo que mañana tenés turno con {prof_name} "
        f"a las {slot_display} 🗓️\n\n"
        "¿Vas a poder venir? Respondeme sí o no."
    )

    await send_message(patient_phone, msg, phone_number_id)

    db  = SessionLocal()
    row = db.query(ConversationSession).filter_by(
        phone_number_id=phone_number_id,
        patient_phone=patient_phone,
    ).first()

    if row:
        data = json.loads(row.data)
        data["reminder_sent"] = True
        row.step = "awaiting_confirmation"
        row.data = json.dumps(data)
        db.commit()
    db.close()


def schedule_reminder(
    phone_number_id: str,
    patient_phone: str,
    slot: dict,
    prof_name: str,
):
    slot_start  = datetime.fromisoformat(slot["start"])
    reminder_at = slot_start - timedelta(hours=24)
    now         = datetime.now(tz=TZ)

    if reminder_at <= now:
        reminder_at = now + timedelta(minutes=1)

    job_id = f"reminder_{phone_number_id}_{patient_phone}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        _send_reminder,
        trigger="date",
        run_date=reminder_at,
        args=[phone_number_id, patient_phone, slot["display"], prof_name],
        id=job_id,
        replace_existing=True,
    )

    print(f"[SCHEDULER] Recordatorio programado para {reminder_at} — {patient_phone}")


def cancel_reminder(phone_number_id: str, patient_phone: str):
    job_id = f"reminder_{phone_number_id}_{patient_phone}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        print(f"[SCHEDULER] Recordatorio cancelado — {patient_phone}")