import os
import uuid
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Integer,
    Boolean, Text, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,   # reconecta si la conexión cayó
    )

SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


def _uuid():
    return str(uuid.uuid4())


class Professional(Base):
    __tablename__ = "professionals"

    id                = Column(String, primary_key=True, default=_uuid)
    phone_number_id   = Column(String, unique=True, nullable=False)
    name              = Column(String, nullable=False)
    title             = Column(String, default="")
    niche             = Column(String, default="general")
    address           = Column(String, default="")
    schedule          = Column(String, default="")
    timezone          = Column(String, default="America/Argentina/Buenos_Aires")
    country_code      = Column(String, default="AR")
    locale            = Column(String, default="es_AR")
    calendar_id       = Column(String, nullable=False)
    credentials_file  = Column(String, nullable=False)
    session_minutes   = Column(Integer, default=50)
    slot_advance_days = Column(Integer, default=14)
    active            = Column(Boolean, default=True)
    created_at        = Column(String, default=lambda: datetime.utcnow().isoformat())


class WorkingHours(Base):
    __tablename__ = "working_hours"

    id              = Column(String, primary_key=True, default=_uuid)
    professional_id = Column(String, nullable=False)
    day_of_week     = Column(Integer, nullable=False)
    start_time      = Column(String, nullable=False)
    end_time        = Column(String, nullable=False)
    active          = Column(Boolean, default=True)


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id              = Column(String, primary_key=True, default=_uuid)
    professional_id = Column(String, nullable=False)
    patient_phone   = Column(String, nullable=False)
    patient_name    = Column(String, default="")
    step            = Column(String, default="menu")
    data            = Column(Text, default="{}")
    last_activity   = Column(String, default=lambda: datetime.utcnow().isoformat())

    __table_args__ = (
        UniqueConstraint("professional_id", "patient_phone", name="uq_session"),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id                = Column(String, primary_key=True, default=_uuid)
    professional_id   = Column(String, nullable=False)
    patient_phone     = Column(String, nullable=False)
    patient_name      = Column(String, default="")
    start_at          = Column(String, nullable=False)
    end_at            = Column(String, nullable=False)
    calendar_event_id = Column(String, default="")
    status            = Column(String, default="pending")
    reminder_sent_at  = Column(String, default="")
    created_at        = Column(String, default=lambda: datetime.utcnow().isoformat())


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    msg_id     = Column(String, primary_key=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()