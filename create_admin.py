import uuid
# Agregamos init_db a la importación
from app.database import SessionLocal, User, UserRole, init_db 
from passlib.context import CryptContext

# Configuramos el encriptador (debe ser igual al de main.py)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_superadmin():
    # 1. ESTO ES LO NUEVO: Fuerza la creación de las tablas faltantes
    init_db()
    
    db = SessionLocal()
    
    # Datos de tu cuenta maestra
    email = "nicolas@test.com" 
    password = "1234" 
    
    # Verificamos si ya existe
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        print(f"⚠️ El usuario {email} ya existe.")
        db.close()
        return

    # Creamos el hash de la contraseña
    hashed_password = pwd_context.hash(password)
    
    # Creamos el registro
    new_admin = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hashed_password,
        role=UserRole.SUPERADMIN,
        professional_id=None 
    )

    try:
        db.add(new_admin)
        db.commit()
        print(f"✅ Superadmin creado con éxito: {email}")
    except Exception as e:
        db.rollback()
        print(f"❌ Error al crear admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_superadmin()