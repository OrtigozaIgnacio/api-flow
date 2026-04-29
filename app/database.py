import uuid
import enum
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Boolean, ForeignKey, Enum, Float, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

def _uuid():
    return str(uuid.uuid4())

# Configuración con protección contra desconexiones de Supabase
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserRole(str, enum.Enum):
    SUPERADMIN = "superadmin"
    PROFESSIONAL = "professional"

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True, default=_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.PROFESSIONAL)
    professional_id = Column(String, ForeignKey("professionals.id"), nullable=True)

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
    currency          = Column(String, default="ARS") # <-- NUEVO: USD, ARS, etc.
    locale            = Column(String, default="es_AR")
    calendar_id       = Column(String, nullable=False)
    credentials_file  = Column(String, nullable=False)
    session_minutes   = Column(Integer, default=50)
    slot_advance_days = Column(Integer, default=14)
    session_price     = Column(Float, default=50000.0)
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
    __table_args__ = (UniqueConstraint("professional_id", "patient_phone", name="uq_session"),)

class Appointment(Base):
    __tablename__ = "appointments"
    id                = Column(String, primary_key=True, default=_uuid)
    professional_id   = Column(String, nullable=False)
    patient_phone     = Column(String, nullable=False)
    patient_name      = Column(String, default="")
    start_at          = Column(String, nullable=False)
    end_at            = Column(String, nullable=False)
    price             = Column(Float, default=0.0) # <-- NUEVO: Precio congelado
    calendar_event_id = Column(String, default="")
    status            = Column(String, default="pending")
    is_billed         = Column(Boolean, default=False)
    created_at        = Column(String, default=lambda: datetime.utcnow().isoformat())

class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    msg_id     = Column(String, primary_key=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

def init_db():
    Base.metadata.create_all(bind=engine)