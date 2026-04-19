import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.database import Professional, SessionLocal, WorkingHours

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_calendar_service(prof: Professional):
    """Crea el cliente de Google Calendar leyendo desde entorno o archivo."""
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    
    if creds_json:
        # Modo Producción (Render)
        creds_dict = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
    else:
        # Fallback Modo Local
        creds = service_account.Credentials.from_service_account_file(
            prof.credentials_file, scopes=SCOPES
        )
        
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _get_working_hours(prof: Professional) -> dict[int, tuple[str, str]]:
    db = SessionLocal()
    rows = db.query(WorkingHours).filter_by(
        professional_id=prof.id, active=True
    ).all()
    db.close()
    return {r.day_of_week: (r.start_time, r.end_time) for r in rows}


def _candidate_slots(prof: Professional, start_from: datetime, count: int = 30) -> list[datetime]:
    hours    = _get_working_hours(prof)
    duration = timedelta(minutes=prof.session_minutes)
    
    # Manejar zona horaria del profesional dinámicamente
    prof_tz  = ZoneInfo(prof.timezone)
    current  = start_from.astimezone(prof_tz).replace(second=0, microsecond=0)

    if current.minute % 30 != 0:
        current += timedelta(minutes=30 - current.minute % 30)

    candidates   = []
    days_checked = 0

    while len(candidates) < count and days_checked < prof.slot_advance_days:
        weekday = current.weekday()

        if weekday not in hours:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            days_checked += 1
            continue

        start_h, end_h = hours[weekday]
        start_hour = int(start_h.split(":")[0])
        end_hour   = int(end_h.split(":")[0])

        if current.hour < start_hour:
            current = current.replace(hour=start_hour, minute=0)
            continue

        slot_end = current + duration
        if current.hour >= end_hour or slot_end.hour > end_hour:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            days_checked += 1
            continue

        candidates.append(current)
        current += duration

    return candidates


async def get_available_slots(
    prof: Professional,
    skip: int = 0,
    preference: str | None = None,
) -> list[dict]:
    service = _get_calendar_service(prof)

    now        = datetime.now(tz=ZoneInfo(prof.timezone))
    end_search = now + timedelta(days=prof.slot_advance_days)

    events_result = service.events().list(
        calendarId=prof.calendar_id,
        timeMin=now.isoformat(),
        timeMax=end_search.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    busy_blocks = []
    for event in events_result.get("items", []):
        start = event["start"].get("dateTime")
        end   = event["end"].get("dateTime")
        if start and end:
            busy_blocks.append((
                datetime.fromisoformat(start).astimezone(ZoneInfo(prof.timezone)),
                datetime.fromisoformat(end).astimezone(ZoneInfo(prof.timezone)),
            ))

    start_from = now + timedelta(hours=2)
    candidates = _candidate_slots(prof, start_from, count=30)

    if preference:
        # Ahora pasamos el profesional para que sepa en qué país está
        candidates = _filter_by_preference(prof, candidates, preference)

    duration = timedelta(minutes=prof.session_minutes)
    free_slots = []

    for candidate in candidates:
        candidate_end = candidate + duration
        overlap = any(
            not (candidate_end <= busy_start or candidate >= busy_end)
            for busy_start, busy_end in busy_blocks
        )
        if not overlap:
            free_slots.append(candidate)

    free_slots = free_slots[skip: skip + 3]

    return [
        {
            "start":    slot.isoformat(),
            "end":      (slot + duration).isoformat(),
            "display":  _format_slot(slot),
            "event_id": None,
        }
        for slot in free_slots
    ]


def _filter_by_preference(prof: Professional, candidates: list[datetime], preference: str) -> list[datetime]:
    import re
    pref = preference.lower()

    DAY_MAP = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4,
    }
    MORNING   = range(9, 13)
    AFTERNOON = range(13, 18)
    EVENING   = range(18, 21)

    day_filter      = None
    time_filter     = None
    specific_hour   = None
    specific_minute = 0

    for name, num in DAY_MAP.items():
        if name in pref:
            day_filter = num
            break

    time_match = re.search(r'(\d{1,2}):(\d{2})', pref)
    if time_match:
        specific_hour   = int(time_match.group(1))
        specific_minute = int(time_match.group(2))
    else:
        hour_match = re.search(r'las?\s+(\d{1,2})\b', pref)
        if hour_match:
            specific_hour   = int(hour_match.group(1))
            specific_minute = 0

    if any(w in pref for w in ("mañana", "manana", "mañanas")):
        time_filter = MORNING
    elif any(w in pref for w in ("tarde", "tardes")):
        time_filter = AFTERNOON
    elif any(w in pref for w in ("noche", "noches", "última hora", "ultima hora")):
        time_filter = EVENING

    next_week = None
    if "semana que viene" in pref or "próxima semana" in pref or "proxima semana" in pref:
        # AQUÍ ESTABA EL ERROR: Usamos la zona horaria del profesional
        today      = datetime.now(tz=ZoneInfo(prof.timezone)).date()
        days_ahead = 7 - today.weekday()
        next_week  = today + timedelta(days=days_ahead)

    filtered = []
    for c in candidates:
        if day_filter is not None and c.weekday() != day_filter:
            continue
        if specific_hour is not None:
            if c.hour != specific_hour or c.minute != specific_minute:
                continue
        elif time_filter is not None and c.hour not in time_filter:
            continue
        if next_week is not None and c.date() < next_week:
            continue
        filtered.append(c)

    return filtered if len(filtered) >= 1 else candidates


def _format_slot(dt: datetime) -> str:
    DAYS = {
        0: "lunes", 1: "martes", 2: "miércoles",
        3: "jueves", 4: "viernes", 5: "sábado", 6: "domingo",
    }
    MONTHS = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    day_name = DAYS[dt.weekday()]
    month    = MONTHS[dt.month]
    return f"{day_name} {dt.day} de {month} a las {dt.strftime('%H:%M')} hs"


async def block_slot(slot: dict, prof: Professional) -> str:
    service = _get_calendar_service(prof)

    event = {
        "summary": f"Turno — {prof.name}",
        "description": "Turno reservado por el asistente automático.",
        "start": {
            "dateTime": slot["start"],
            "timeZone": prof.timezone,
        },
        "end": {
            "dateTime": slot["end"],
            "timeZone": prof.timezone,
        },
        "reminders": {"useDefault": False},
    }

    created = service.events().insert(
        calendarId=prof.calendar_id,
        body=event,
    ).execute()

    slot["event_id"] = created["id"]
    return created["id"]


async def unblock_slot(slot: dict, prof: Professional):
    event_id = slot.get("event_id")
    if not event_id:
        return

    service = _get_calendar_service(prof)

    try:
        service.events().delete(
            calendarId=prof.calendar_id,
            eventId=event_id,
        ).execute()
    except Exception as e:
        print(f"[ERROR] No se pudo liberar el evento {event_id}: {e}")

async def create_event(calendar_id: str, start_time: str, end_time: str, summary: str, description: str, prof: Professional):
    """Crea el evento final una vez validado el pago."""
    service = _get_calendar_service(prof)
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": prof.timezone},
        "end": {"dateTime": end_time, "timeZone": prof.timezone},
    }
    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    return created["id"]