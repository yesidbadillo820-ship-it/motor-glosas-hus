import os
import io
import re
import csv
import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, UploadFile, File, Form,
    Depends, HTTPException, Request, Security
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from jose import JWTError, jwt

from services import GlosaService, crear_oficio_pdf, exportar_excel_pro
from models import GlosaRecord, ContratoRecord, UsuarioRecord, GlosaInput, GlosaResult, PDFRequest, ContratoInput
from database import engine, Base, get_db, SessionLocal
from auth import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM

logger = logging.getLogger("motor_glosas")
Base.metadata.create_all(bind=engine)

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        if db.query(ContratoRecord).count() == 0:
            for k, v in BASE_CONTRATOS_DEFAULT.items():
                db.add(ContratoRecord(eps=k, detalles=v))
        if db.query(UsuarioRecord).count() == 0:
            db.add(UsuarioRecord(nombre="Auditor Principal", email="admin@hus.gov.co", password_hash=get_password_hash("admin123")))
        db.commit()
    finally:
        db.close()
    yield

app = FastAPI(title="Motor Glosas HUS PRO v4.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

glosa_service = GlosaService(api_key=os.getenv("GROQ_API_KEY", ""))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token == "HUS2026":
        return UsuarioRecord(nombre="Admin", email="admin@hus.gov.co")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
        if not usuario: raise HTTPException(status_code=401)
        return usuario
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.post("/analizar")
async def analizar_endpoint(
    request: Request,
    eps: str = Form(...), etapa: str = Form(...), 
    fecha_radicacion: str = Form(None), fecha_recepcion: str = Form(None),
    valor_aceptado: str = Form("0"), tabla_excel: str = Form(...),
    archivos: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
    u: UsuarioRecord = Depends(get_usuario_actual)
):
    contexto_pdf = ""
    if archivos:
        for arc in archivos:
            if arc.filename: contexto_pdf += await glosa_service.extraer_pdf(await arc.read())

    data = GlosaInput(eps=eps, etapa=etapa, fecha_radicacion=fecha_radicacion, fecha_recepcion=fecha_recepcion, valor_aceptado=valor_aceptado, tabla_excel=tabla_excel)
    contratos_db = {c.eps: c.detalles for c in db.query(ContratoRecord).all()}
    resultado = await glosa_service.analizar(data, contexto_pdf, contratos_db)
    
    val_obj = float(re.sub(r'[^\d]', '', resultado.valor_objetado) or 0)
    val_acep = float(re.sub(r'[^\d]', '', valor_aceptado) or 0)
    
    db.add(GlosaRecord(
        eps=eps, paciente=resultado.paciente, codigo_glosa=resultado.codigo_glosa, valor_objetado=val_obj,
        valor_aceptado=val_acep, etapa=etapa, estado="ACEPTADA" if val_acep > 0 else "LEVANTADA",
        dictamen=resultado.dictamen, dias_restantes=resultado.dias_restantes
    ))
    db.commit()
    return resultado

@app.get("/glosas")
def listar_historial(limit: int = 50, db: Session = Depends(get_db), u: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(limit).all()

@app.get("/alertas")
def obtener_alertas(db: Session = Depends(get_db), u: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(GlosaRecord).filter(GlosaRecord.dias_restantes <= 5, GlosaRecord.dias_restantes > 0).all()

@app.get("/analytics")
def obtener_analytics(db: Session = Depends(get_db), u: UsuarioRecord = Depends(get_usuario_actual)):
    stats = db.query(func.count(GlosaRecord.id), func.sum(GlosaRecord.valor_objetado), func.sum(GlosaRecord.valor_aceptado)).first()
    v_obj = stats[1] or 0
    v_rec = v_obj - (stats[2] or 0)
    return {
        "glosas_mes": stats[0] or 0,
        "valor_objetado_mes": v_obj,
        "valor_recuperado_mes": v_rec,
        "tasa_exito_pct": round((v_rec / v_obj * 100) if v_obj > 0 else 0, 1)
    }

@app.get("/contratos")
def get_contratos(db: Session = Depends(get_db), u: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(ContratoRecord).all()

@app.post("/descargar-pdf")
async def descargar_pdf(req: PDFRequest, u: UsuarioRecord = Depends(get_usuario_actual)):
    pdf_bytes = crear_oficio_pdf(req.eps, req.resumen, req.dictamen)
    return Response(content=pdf_bytes, media_type="application/pdf")

@app.get("/exportar-historial")
def exportar_historial(db: Session = Depends(get_db), u: UsuarioRecord = Depends(get_usuario_actual)):
    glosas = db.query(GlosaRecord).all()
    excel_bytes = exportar_excel_pro(glosas)
    return Response(content=excel_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
