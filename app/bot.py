import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import SessionLocal, Professional, ConversationSession
from app.intent import classify_intent
from app.whatsapp import send_message


def _get_professional(phone_number_id: str) -> Professional | None:
    db = SessionLocal()
    prof = db.query(Professional).filter_by(
        phone_number_id=phone_number_id, active=True
    ).first()
    db.close()
    return prof


def _get_session(phone_number_id: str, patient_phone: str) -> dict:
    db = SessionLocal()
    row = db.query(ConversationSession).filter_by(
        phone_number_id=phone_number_id,
        patient_phone=patient_phone,
    ).first()
    db.close()
    if row:
        return {"step": row.step, "data": json.loads(row.data)}
    return {"step": "menu", "data": {}}


def _save_session(phone_number_id: str, patient_phone: str, session: dict):
    db = SessionLocal()
    row = db.query(ConversationSession).filter_by(
        phone_number_id=phone_number_id,
        patient_phone=patient_phone,
    ).first()
    if row:
        row.step = session["step"]
        row.data = json.dumps(session["data"])
    else:
        db.add(ConversationSession(
            phone_number_id=phone_number_id,
            patient_phone=patient_phone,
            step=session["step"],
            data=json.dumps(session["data"]),
        ))
    db.commit()
    db.close()

def _save_appointment(
    professional_id: str,
    patient_phone: str,
    patient_name: str,
    slot: dict,
    status: str = "pending",
) -> str:
    """Guarda el turno en la tabla appointments y devuelve el id."""
    from app.database import Appointment
    db  = SessionLocal()
    apt = Appointment(
        professional_id   = professional_id,
        patient_phone     = patient_phone,
        patient_name      = patient_name,
        start_at          = slot["start"],
        end_at            = slot["end"],
        calendar_event_id = slot.get("event_id", ""),
        status            = status,
    )
    db.add(apt)
    db.commit()
    apt_id = apt.id
    db.close()
    return apt_id


def _update_appointment_status(apt_id: str, status: str):
    from app.database import Appointment
    db  = SessionLocal()
    apt = db.query(Appointment).filter_by(id=apt_id).first()
    if apt:
        apt.status = status
        db.commit()
    db.close()


async def handle_message(phone_number_id: str, patient_phone: str, text: str):
    prof = _get_professional(phone_number_id)
    if not prof:
        return

    # Inyectamos la hora local del profesional
    prof_tz = ZoneInfo(prof.timezone)
    now_str = datetime.now(tz=prof_tz).strftime("%A, %d de %B de %Y - %H:%M")

    text    = text.strip()
    session = _get_session(phone_number_id, patient_phone)
    step    = session["step"]

    async def reply(msg: str):
        # Usamos kwargs explícitos para no cruzar los argumentos de destino
        await send_message(to=patient_phone, text=msg, phone_number_id=phone_number_id)

    WELCOME = (
        f"¡Hola! 👋 Soy el asistente de {prof.title} {prof.name}.\n"
        "¿En qué te puedo ayudar? ¿Querés agendar un turno?"
    )

    INFO = (
        f"¡Claro! Te cuento:\n\n"
        f"📍 *Consultorio:* {prof.address}\n"
        f"🕐 *Días y horarios:* {prof.schedule}\n\n"
        "¿Querés que te busque un turno disponible?"
    )

    if text.lower() in ("hola", "buenas", "buen día", "buenos días",
                         "buenas tardes", "buenas noches", "inicio", "menu", "start"):
        session = {"step": "menu", "data": {}}
        _save_session(phone_number_id, patient_phone, session)
        await reply(WELCOME)
        return

    if step == "confirmed":
        session["step"] = "menu"
        step = "menu"
        _save_session(phone_number_id, patient_phone, session)

    # ── Menú ──
    if step == "menu":
        intent = await classify_intent("menu", text, local_time_str=now_str)

        if intent == "schedule":
            session["step"] = "loading_slots"
            _save_session(phone_number_id, patient_phone, session)
            await reply("¡Perfecto! Dejame revisar la agenda un momento... 📅")
            await _send_slots(phone_number_id, patient_phone, prof, session, reply)

        elif intent == "info":
            await reply(INFO)

        elif intent == "unclear":
            session = {"step": "menu", "data": {}}
            _save_session(phone_number_id, patient_phone, session)
            await reply(WELCOME)

        return

    # ── Eligiendo turno ──
    if step == "awaiting_slot_selection":
        await _handle_slot_choice(
            phone_number_id, patient_phone, text, session, prof, reply
        )
        return

    # ── Indicando preferencia ──
    if step == "awaiting_preference":
        await _handle_preference(
            phone_number_id, patient_phone, text, session, prof, reply
        )
        return

    # ── Confirmando asistencia ──
    if step == "awaiting_confirmation":
        await _handle_confirmation(
            phone_number_id, patient_phone, text, session, prof, reply
        )
        return

    # Fallback
    session = {"step": "menu", "data": {}}
    _save_session(phone_number_id, patient_phone, session)
    await reply(WELCOME)


async def _send_slots(phone_number_id, patient_phone, prof, session, reply):
    from app.calendar_service import get_available_slots

    slots = await get_available_slots(prof)

    if not slots:
        await reply(
            "Mmm, no encuentro turnos disponibles en los próximos días 😕\n"
            "Te recomiendo que te comuniques directamente con el consultorio."
        )
        session["step"] = "menu"
        _save_session(phone_number_id, patient_phone, session)
        return

    session["data"]["available_slots"] = slots
    session["data"]["unclear_count"]   = 0
    session["step"] = "awaiting_slot_selection"
    _save_session(phone_number_id, patient_phone, session)

    lines = ["Tengo estos horarios libres:\n"]
    for label, slot in zip(["A", "B", "C"], slots[:3]):
        lines.append(f"*{label}.* {slot['display']}")
    lines.append("\n¿Alguno te viene bien?")

    await reply("\n".join(lines))


async def _handle_slot_choice(phone_number_id, patient_phone, text, session, prof, reply):
    from app.calendar_service import block_slot
    from app.scheduler import schedule_reminder
    
    slots = session["data"].get("available_slots", [])
    prof_tz = ZoneInfo(prof.timezone)
    now_str = datetime.now(tz=prof_tz).strftime("%A, %d de %B de %Y - %H:%M")

    selected_slot = None

    time_match = re.search(
        r'(?:las?\s+(\d{1,2})(?::(\d{2}))?|(\d{1,2}):(\d{2}))\s*(?:hs?)?',
        text.lower()
    )
    if time_match:
        if time_match.group(1) is not None:
            hour   = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
        else:
            hour   = int(time_match.group(3))
            minute = int(time_match.group(4))

        for slot in slots:
            slot_dt = datetime.fromisoformat(slot["start"]).astimezone(prof_tz)
            if slot_dt.hour == hour and slot_dt.minute == minute:
                selected_slot = slot
                break

        if not selected_slot:
            await reply(
                f"No tengo un turno disponible a las {hour:02d}:{minute:02d} hs 😕\n"
                "Esos son los horarios que tengo libres. ¿Cuál te queda mejor?"
            )
            return

    if not selected_slot:
        intent   = await classify_intent("awaiting_slot_selection", text, local_time_str=now_str)
        slot_map = {"select_a": 0, "select_b": 1, "select_c": 2}

        if intent in slot_map:
            idx = slot_map[intent]
            if idx < len(slots):
                selected_slot = slots[idx]

        elif intent == "request_other":
            session["data"]["unclear_count"] = 0
            session["step"] = "awaiting_preference"
            _save_session(phone_number_id, patient_phone, session)
            await reply(
                "Sin problema, buscamos otro 🙌\n"
                "¿Tenés alguna preferencia? Por ejemplo, un día de la semana "
                "o una franja horaria que te venga mejor."
            )
            return

        else:
            await _handle_unclear(
                phone_number_id, patient_phone, session, reply,
                fallback_msg="No entendí bien 😅 ¿Cuál de los tres turnos te queda mejor?"
            )
            return

    if not selected_slot:
        await reply("No encontré ese turno entre los disponibles. ¿Podés indicarme cuál de los tres preferís?")
        return

    await block_slot(selected_slot, prof)

    patient_name = session["data"].get("patient_name", "")
    apt_id = _save_appointment(
        professional_id = prof.id,
        patient_phone   = patient_phone,
        patient_name    = patient_name,
        slot            = selected_slot,
        status          = "pending",
    )

    session["data"] = {
        "confirmed_slot":  selected_slot,
        "appointment_id":  apt_id,
        "unclear_count":   0,
    }
    # Lo dejamos en pending visualmente para que sepa que falta el pago,
    # aunque a nivel chatbot vuelve al inicio
    session["step"] = "menu"
    _save_session(phone_number_id, patient_phone, session)
    
    schedule_reminder(phone_number_id, patient_phone, selected_slot, prof.name)

    await reply(
        f"¡Listo! 🎉 Te reservé el lugar para el {selected_slot['display']}.\n\n"
        f"Para confirmar el turno definitivamente, por favor enviá una foto o captura del comprobante de transferencia por el valor de la consulta.\n"
        f"Te espero."
    )


async def _handle_preference(phone_number_id, patient_phone, text, session, prof, reply):
    from app.calendar_service import get_available_slots
    
    prof_tz = ZoneInfo(prof.timezone)
    now_str = datetime.now(tz=prof_tz).strftime("%A, %d de %B de %Y - %H:%M")

    intent = await classify_intent("awaiting_preference", text, local_time_str=now_str)

    if intent == "see_more":
        slots = await get_available_slots(prof, skip=3)
    elif intent == "specify_preference":
        slots = await get_available_slots(prof, preference=text)
    else:
        await _handle_unclear(
            phone_number_id, patient_phone, session, reply,
            fallback_msg="¿Tenés algún día o horario preferido? Contame y busco opciones."
        )
        return

    if not slots:
        await reply(
            "No encontré turnos en esa franja 😕\n"
            "¿Querés que busque en otro día u horario?"
        )
        return

    session["data"]["available_slots"] = slots
    session["data"]["unclear_count"]   = 0
    session["step"] = "awaiting_slot_selection"
    _save_session(phone_number_id, patient_phone, session)

    lines = ["Encontré estas opciones:\n"]
    for label, slot in zip(["A", "B", "C"], slots[:3]):
        lines.append(f"*{label}.* {slot['display']}")
    lines.append("\n¿Alguno te viene bien?")

    await reply("\n".join(lines))


async def _handle_confirmation(phone_number_id, patient_phone, text, session, prof, reply):
    from app.calendar_service import unblock_slot
    from app.scheduler import cancel_reminder

    prof_tz = ZoneInfo(prof.timezone)
    now_str = datetime.now(tz=prof_tz).strftime("%A, %d de %B de %Y - %H:%M")

    slot   = session["data"].get("confirmed_slot")
    intent = await classify_intent("awaiting_confirmation", text, local_time_str=now_str)

    if intent == "confirm":
        apt_id = session["data"].get("appointment_id")
        if apt_id:
            _update_appointment_status(apt_id, "confirmed")
        session["data"]["unclear_count"] = 0
        session["step"] = "menu"
        _save_session(phone_number_id, patient_phone, session)
        await reply("¡Perfecto, te esperamos! 🗓️ Cualquier cosa, escribime por acá.")

    elif intent == "cancel":
        apt_id = session["data"].get("appointment_id")
        if apt_id:
            _update_appointment_status(apt_id, "cancelled")
        if slot:
            await unblock_slot(slot, prof)
        cancel_reminder(phone_number_id, patient_phone)
        session = {"step": "menu", "data": {}}
        _save_session(phone_number_id, patient_phone, session)
        await reply(
            "Entendido, cancelamos el turno 🔓\n"
            "Cuando puedas, escribime y te busco otro horario."
        )

    else:
        await _handle_unclear(
            phone_number_id, patient_phone, session, reply,
            fallback_msg=(
                f"Tenés turno el {slot['display'] if slot else 'próximo turno'}.\n"
                "¿Vas a poder venir? Respondeme sí o no."
            )
        )


async def _handle_unclear(
    phone_number_id: str,
    patient_phone: str,
    session: dict,
    reply,
    fallback_msg: str = "",
):
    count = session["data"].get("unclear_count", 0) + 1
    session["data"]["unclear_count"] = count
    _save_session(phone_number_id, patient_phone, session)

    if count >= 2:
        session = {"step": "menu", "data": {}}
        _save_session(phone_number_id, patient_phone, session)
        await reply(
            "Perdoná, no logré entenderte 😅\n"
            "¿Querés agendar un turno o necesitás información del consultorio?"
        )
    else:
        msg = fallback_msg or "No entendí bien, ¿podés contarme un poco más?"
        await reply(msg)