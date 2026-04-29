from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

# Configuración de seguridad
SECRET_KEY = os.getenv("JWT_SECRET", "una_clave_muy_secreta_para_caleta_olivia")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # El token dura 24 horas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict):
    """Genera el token que el frontend guardará en localStorage."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)