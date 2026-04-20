import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db")

engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")

def actualizar_base_de_datos():
    with engine.connect() as conn:
        try:
            # Agregamos la columna a la tabla de turnos con valor por defecto en falso
            conn.execute(text("ALTER TABLE appointments ADD COLUMN is_billed BOOLEAN DEFAULT FALSE;"))
            print("✅ Columna 'is_billed' agregada exitosamente a la tabla appointments.")
        except Exception as e:
            print("⚠️ La columna 'is_billed' ya existe. Omitiendo...")
            
    print("🚀 ¡Actualización terminada!")

if __name__ == "__main__":
    actualizar_base_de_datos()