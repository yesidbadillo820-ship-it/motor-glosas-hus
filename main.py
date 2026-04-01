import os
import re
import io
import csv
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from jose import JWTError, jwt
from pydantic import BaseModel

from services import GlosaService, crear_oficio_pdf
from models import GlosaInput, GlosaResult, PDFRequest, GlosaRecord, ContratoRecord, ContratoInput, UsuarioRecord
from database import engine, Base, get_db, SessionLocal
from auth import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM
from dotenv import load_dotenv

load_dotenv()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Motor Glosas HUS - V2 Pro")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

glosa_service = GlosaService(api_key=os.getenv("GROQ_API_KEY"))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credenciales_excepcion = HTTPException(
        status_code=401, detail="No se pudieron validar las credenciales", headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None: raise credenciales_excepcion
    except JWTError:
        raise credenciales_excepcion
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if usuario is None: raise credenciales_excepcion
    return usuario

BASE_CONTRATOS_DEFAULT = {
    "COOSALUD": "CONTRATOS: 68001S00060339-24 y 68001C00060340-24. TARIFA: SOAT -15% e Institucionales. OBS: MAOS por HUS, Oncológicos por EPS.",
    "COMPENSAR": "CONTRATO: CSS009-2024. TARIFA: SOAT -15% y Tarifas Propias. OBS: Excluye oncológicos. MAOS por EPS.",
    "FAMISANAR": "CARTA DE INTENCIÓN. TARIFA: SOAT UVB -5% e Institucionales.",
    "FOMAG": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15%, Institucionales y Paquetes (Tórax, IVE, Columna, Terapias, Gastro).",
    "LA PREVISORA": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15% y Paquetes.",
    "DISPENSARIO MEDICO": "CONTRATO: 440-DIGSA/DMBUG-2025. TARIFA: SOAT SMLV -20% e Institucionales.",
    "POLICIA NACIONAL": "CONTRATOS: 068-5-200004-26 y 068-5-200006-26. TARIFA: SOAT UVB -8% e Institucionales. OBS: Contrato 0006-26 INCLUYE medicamentos oncológicos.",
    "NUEVA EPS": "CONTRATO: 02-01-06-00077-2017. TARIFA: SOAT -20% e Institucionales. OBS: Meds Oncológicos por HUS.",
    "PPL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%. OBS: MAOS y Meds por HUS.",
    "FIDUCIARIA CENTRAL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%.",
    "POSITIVA": "CONTRATO: 525 - OTROSÍ 3. TARIFA: SOAT SMLV -15%. OBS: Solo accidentes/laboral.",
    "PRECIMED": "CONTRATO: 319 DE 2024. TARIFA: Tarifas anexos / Institucionales.",
    "SALUD MIA": "CONTRATOS: SSA2025EVE3A005 y CSA2025EVE3A005. TARIFA: SOAT -15%. OBS: Urgencias Circular 019/2023.",
    "AURORA": "CONTRATOS: GID ARL 0090 y GID AP 0090. TARIFA: SOAT -3%.",
    "SECRETARIA DE SANTANDER": "MARCO LEGAL: Resolución 15997 de 2017 (Tarifas obligatorias ente territorial).",
    "SUMIMEDICAL": "CONTRATO: FPS23-050. TARIFA: SOAT -15%. OBS: MAOS y Oncológicos por EPS.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 DE 2026_0001 / DECRETO 441 DE 2022)."
}

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    if db.query(ContratoRecord).count() == 0:
        for k, v in BASE_CONTRATOS_DEFAULT.items():
            db.add(ContratoRecord(eps=k, detalles=v))
        db.commit()
    if db.query(UsuarioRecord).count() == 0:
        admin_pwd = get_password_hash("admin123")
        db.add(UsuarioRecord(nombre="Auditor Principal", email="admin@hus.gov.co", password_hash=admin_pwd))
        db.commit()
    db.close()

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/token")
def login_para_token(req: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == req.username.strip()).first()
    if not usuario or not verify_password(req.password.strip(), usuario.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    return {"access_token": create_access_token(data={"sub": usuario.email}), "token_type": "bearer"}

@app.get("/")
async def read_index():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: No se encontró static/index.html</h1>", status_code=404)

def limpiar_numero(v: str) -> float:
    c = re.sub(r'[^\d]', '', str(v))
    return float(c) if c else 0.0

@app.post("/analizar", response_model=GlosaResult)
async def analizar_endpoint(
    eps: str = Form(...), etapa: str = Form(...), fecha_radicacion: str = Form(None),
    fecha_recepcion: str = Form(None), valor_aceptado: str = Form("0"), tabla_excel: str = Form(...),
    archivos: list[UploadFile] = File(None), db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    
    contexto_pdf = ""
    if archivos:
        for arc in archivos:
            if arc.filename: contexto_pdf += await glosa_service.extraer_pdf(await arc.read())
    
    input_data = GlosaInput(eps=eps, etapa=etapa, fecha_radicacion=fecha_radicacion, fecha_recepcion=fecha_recepcion, valor_aceptado=valor_aceptado, tabla_excel=tabla_excel)
    dict_contratos = {c.eps: c.detalles for c in db.query(ContratoRecord).all()}
    
    resultado = await glosa_service.analizar(input_data, contexto_pdf, dict_contratos)
    val_obj, val_acep = limpiar_numero(resultado.valor_objetado), limpiar_numero(valor_aceptado)
    
    db.add(GlosaRecord(
        eps=eps, paciente=resultado.paciente, codigo_glosa=resultado.codigo_glosa, valor_objetado=val_obj, 
        valor_aceptado=val_acep, etapa=etapa, estado="ACEPTADA" if val_acep > 0 else "LEVANTADA", dictamen=resultado.dictamen
    ))
    db.commit()
    return resultado

@app.post("/descargar-pdf")
async def descargar_pdf(req: PDFRequest, usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    pdf_bytes = crear_oficio_pdf(req.eps, req.resumen, req.dictamen)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=Oficio_HUS.pdf"})

@app.get("/glosas")
def obtener_historial(limit: int = 50, db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(limit).all()

@app.get("/contratos")
def get_contratos(db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(ContratoRecord).order_by(ContratoRecord.eps).all()
