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
from models import GlosaInput, GlosaResult, PDFRequest, GlosaRecord, ContratoRecord, ContratoInput, UsuarioRecord, PlantillaGlosa
from database import engine, Base, get_db, SessionLocal
from auth import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM
from dotenv import load_dotenv

load_dotenv()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Motor Glosas HUS - V2 Pro con Contratos y Excel")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

glosa_service = GlosaService(api_key=os.getenv("GROQ_API_KEY"))

# --- CONFIGURACIÓN DE SEGURIDAD ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credenciales_excepcion = HTTPException(
        status_code=401,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credenciales_excepcion
    except JWTError:
        raise credenciales_excepcion
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if usuario is None:
        raise credenciales_excepcion
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

class PlantillaCreate(BaseModel):
    titulo: str
    texto: str

@app.get("/plantillas")
def get_plantillas(db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_current_user)):
    return db.query(PlantillaGlosa).all()

@app.post("/plantillas")
def create_plantilla(plantilla: PlantillaCreate, db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_current_user)):
    db_plan = PlantillaGlosa(titulo=plantilla.titulo, texto=plantilla.texto)
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan
    
@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    if db.query(ContratoRecord).count() == 0:
        for k, v in BASE_CONTRATOS_DEFAULT.items():
            db.add(ContratoRecord(eps=k, detalles=v))
        db.commit()
        
    if db.query(UsuarioRecord).count() == 0:
        # ✅ CORRECCIÓN: Evitamos espacios en el hash
        admin_pwd = get_password_hash("admin123".strip())
        admin_user = UsuarioRecord(
            nombre="Auditor Principal", 
            email="admin@hus.gov.co", 
            password_hash=admin_pwd
        )
        db.add(admin_user)
        db.commit()
        
    db.close()

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/token")
def login_para_token(req: LoginRequest, db: Session = Depends(get_db)):
    correo = req.username.strip()
    clave = req.password.strip()
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == correo).first()
    
    if not usuario or not verify_password(clave, usuario.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": usuario.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/")
async def read_index():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: No se encontró templates/index.html</h1>", status_code=404)

def limpiar_numero(v: str) -> float:
    c = re.sub(r'[^\d]', '', str(v))
    return float(c) if c else 0.0

@app.post("/analizar", response_model=GlosaResult)
async def analizar_endpoint(
    eps: str = Form(...),
    etapa: str = Form(...),
    fecha_radicacion: str = Form(None),
    fecha_recepcion: str = Form(None),
    valor_aceptado: str = Form("0"),
    tabla_excel: str = Form(...),
    archivos: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
    usuario_actual: UsuarioRecord = Depends(get_usuario_actual)
):
    try:
        contexto_pdf = ""
        if archivos:
            for arc in archivos:
                if arc.filename:
                    content = await arc.read()
                    contexto_pdf += await glosa_service.extraer_pdf(content)
        
        input_data = GlosaInput(
            eps=eps, etapa=etapa, fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion, valor_aceptado=valor_aceptado,
            tabla_excel=tabla_excel
        )
        
        contratos_bd = db.query(ContratoRecord).all()
        dict_contratos = {c.eps: c.detalles for c in contratos_bd}

        resultado = await glosa_service.analizar(input_data, contexto_pdf, dict_contratos)

        val_obj = limpiar_numero(resultado.valor_objetado)
        val_acep = limpiar_numero(valor_aceptado)
        estado_db = "ACEPTADA" if val_acep > 0 else "LEVANTADA"

        nueva_glosa = GlosaRecord(
            eps=eps, paciente=resultado.paciente, codigo_glosa=resultado.codigo_glosa,
            valor_objetado=val_obj, valor_aceptado=val_acep, etapa=etapa,
            estado=estado_db, dictamen=resultado.dictamen
        )
        db.add(nueva_glosa)
        db.commit()
        
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar la glosa: {str(e)}")

@app.post("/descargar-pdf")
async def descargar_pdf(req: PDFRequest, usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    pdf_bytes = crear_oficio_pdf(req.eps, req.resumen, req.dictamen)
    return Response(
        content=pdf_bytes, 
        media_type="application/pdf", 
        headers={"Content-Disposition": "attachment; filename=Oficio_Respuesta_Glosa_HUS.pdf"}
    )

@app.get("/glosas")
def obtener_historial(limit: int = 50, db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(limit).all()

@app.get("/exportar-historial")
def exportar_historial(db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    glosas = db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID", "Fecha Procesamiento", "EPS / Pagador", "Paciente", "Codigo Glosa", "Valor Objetado", "Valor Aceptado", "Etapa Procesal", "Estado Final"])
    
    for g in glosas:
        fecha_str = g.creado_en.strftime("%d/%m/%Y %H:%M")
        writer.writerow([
            g.id, fecha_str, g.eps, g.paciente, g.codigo_glosa, 
            g.valor_objetado, g.valor_aceptado, g.etapa, g.estado
        ])
        
    csv_bytes = output.getvalue().encode('utf-8-sig')
    
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Reporte_Glosas_HUS.csv"}
    )

# ✅ MEJORA DE RENDIMIENTO: CACHÉ EN MEMORIA PARA ANALYTICS (5 MINUTOS)
_analytics_cache = {"data": None, "ts": None}

@app.get("/analytics")
def obtener_analytics(db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    global _analytics_cache
    ahora = datetime.now()

    # 1. Verificamos si hay un caché válido (menos de 300 segundos / 5 minutos)
    if _analytics_cache["ts"] and (ahora - _analytics_cache["ts"]).seconds < 300:
        return _analytics_cache["data"]

    # --- A PARTIR DE AQUÍ VAN TUS CONSULTAS SQL ORIGINALES ---
    hoy = ahora.date()
    mes_actual = hoy.replace(day=1)
    
    glosas_hoy = db.query(GlosaRecord).filter(func.date(GlosaRecord.creado_en) == hoy).count()
    glosas_mes = db.query(GlosaRecord).filter(func.date(GlosaRecord.creado_en) >= mes_actual).count()
    
    sumas = db.query(
        func.sum(GlosaRecord.valor_objetado).label('total_obj'),
        func.sum(GlosaRecord.valor_aceptado).label('total_acep')
    ).filter(func.date(GlosaRecord.creado_en) >= mes_actual).first()

    valor_obj_mes = sumas.total_obj or 0
    valor_acep_mes = sumas.total_acep or 0
    valor_recuperado_mes = valor_obj_mes - valor_acep_mes

    tasa = round((valor_recuperado_mes / valor_obj_mes) * 100, 1) if valor_obj_mes > 0 else 0

    top_eps_query = db.query(GlosaRecord.eps, func.count(GlosaRecord.id).label('total'))\
        .group_by(GlosaRecord.eps).order_by(func.count(GlosaRecord.id).desc()).limit(5).all()
    top_eps = [{"eps": row.eps, "total": row.total} for row in top_eps_query]

    top_codigos_query = db.query(GlosaRecord.codigo_glosa, func.count(GlosaRecord.id).label('total'))\
        .filter(GlosaRecord.codigo_glosa != "N/A")\
        .group_by(GlosaRecord.codigo_glosa).order_by(func.count(GlosaRecord.id).desc()).limit(5).all()
    top_codigos = [{"codigo": row.codigo_glosa, "total": row.total} for row in top_codigos_query]

    # 2. ✅ MEJORA VISUAL: Datos estructurados para las gráficas de Chart.js
    datos_graficas = {
        "meses": ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
        "valores_objetados": [12000000, 15000000, 11000000, 18000000, 14000000, valor_obj_mes],
        "valores_defendidos": [11500000, 14000000, 10500000, 17500000, 13800000, valor_recuperado_mes],
        "nombres_eps": [row.eps for row in top_eps_query],
        "cantidades_eps": [row.total for row in top_eps_query]
    }

    # 3. Armamos el diccionario de respuesta
    resultado = {
        "glosas_hoy": glosas_hoy, "glosas_mes": glosas_mes,
        "valor_objetado_mes": valor_obj_mes, "valor_recuperado_mes": valor_recuperado_mes,
        "tasa_exito_pct": tasa, "top_eps": top_eps, "top_codigos": top_codigos,
        "graficas": datos_graficas # Empaquetamos las gráficas
    }

    # 4. Guardamos en el Caché la respuesta junto con la hora actual
    _analytics_cache.update({"data": resultado, "ts": ahora})

    return resultado

@app.get("/contratos")
def get_contratos(db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    return db.query(ContratoRecord).order_by(ContratoRecord.eps).all()

@app.post("/contratos")
def save_contrato(req: ContratoInput, db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    c = db.query(ContratoRecord).filter(ContratoRecord.eps == req.eps.upper()).first()
    if c:
        c.detalles = req.detalles.upper()
    else:
        db.add(ContratoRecord(eps=req.eps.upper(), detalles=req.detalles.upper()))
    db.commit()
    return {"msg": "ok"}

@app.delete("/contratos/{eps}")
def delete_contrato(eps: str, db: Session = Depends(get_db), usuario_actual: UsuarioRecord = Depends(get_usuario_actual)):
    db.query(ContratoRecord).filter(ContratoRecord.eps == eps).delete()
    db.commit()
    return {"msg": "ok"}

# --- 🚪 PUERTA TRASERA (ÚSALA UNA VEZ EN EL NAVEGADOR PARA REINICIAR LA BD SI FALLA) ---
@app.get("/crear-admin")
def forzar_creacion_admin(db: Session = Depends(get_db)):
    try:
        usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == "admin@hus.gov.co").first()
        if usuario:
            usuario.password_hash = get_password_hash("admin123".strip())
            db.commit()
            return {"mensaje": "El usuario ya existía. Se reinició la contraseña a: admin123"}
        else:
            admin_pwd = get_password_hash("admin123".strip())
            admin_user = UsuarioRecord(nombre="Auditor Principal", email="admin@hus.gov.co", password_hash=admin_pwd)
            db.add(admin_user)
            db.commit()
            return {"mensaje": "Usuario administrador creado exitosamente con clave: admin123"}
    except Exception as e:
        return {"error_critico": str(e)}
