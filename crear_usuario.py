import os
from dotenv import load_dotenv
from database import engine, Base, get_db
from models import UsuarioRecord
from auth import get_password_hash
from sqlalchemy.orm import Session

load_dotenv()

# ✏️ CAMBIA ESTOS DATOS
EMAIL = "admin@hus.gov.co"
PASSWORD = "HUS2026*"
NOMBRE = "Administrador HUS"

Base.metadata.create_all(bind=engine)

db = Session(engine)

# Verificar si ya existe
existente = db.query(UsuarioRecord).filter(UsuarioRecord.email == EMAIL).first()
if existente:
    print(f"⚠️  El usuario {EMAIL} ya existe.")
else:
    nuevo = UsuarioRecord(
        email=EMAIL,
        nombre=NOMBRE,
        hashed_password=get_password_hash(PASSWORD)
    )
    db.add(nuevo)
    db.commit()
    print(f"✅ Usuario creado exitosamente:")
    print(f"   Email:    {EMAIL}")
    print(f"   Password: {PASSWORD}")

db.close()
