import os
from typing import List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from services import GlosaService, crear_oficio_pdf
from models import GlosaRecord, ContratoRecord, PlantillaGlosa, GlosaInput
from database import engine, Base, get_db, SessionLocal

Base.metadata.create_all(bind=engine)

# ✅ Diccionario inyectable para auto-reparar la Base de Datos
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
        # Verifica si está vacío, si lo está, inyecta los 17 contratos
        if db.query(ContratoRecord).count() == 0:
            for eps_name, detalle in BASE_CONTRATOS_DEFAULT.items():
                db.add(ContratoRecord(eps=eps_name, detalles=detalle))
            db.commit()
    finally:
        db.close()
    yield

app = FastAPI(title="Motor Glosas HUS", version="2.4", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://motor-glosas-hus.onrender.com", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

glosa_service = GlosaService(api_key=os.getenv("GROQ_API_KEY"))

@app.get("/")
def root():
    return FileResponse("static/index.html", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

@app.post("/analizar")
@limiter.limit("20/minute")
async def analizar_endpoint(
    request: Request,
    eps: str = Form(...),
    etapa: str = Form(...),
    fecha_radicacion: str = Form(...),
    fecha_recepcion: str = Form(...),
    valor_aceptado: str = Form(...),
    tabla_excel: str = Form(...),
    archivos: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    contexto_pdf = ""
    if archivos:
        for arc in archivos:
            if arc.filename:
                content = await arc.read()
                contexto_pdf += await glosa_service.extraer_pdf(content)

    contratos = db.query(ContratoRecord).all()
    contratos_db = {c.eps: c.detalles for c in contratos}

    data = GlosaInput(
        eps=eps,
        etapa=etapa,
        fecha_radicacion=fecha_radicacion,
        fecha_recepcion=fecha_recepcion,
        valor_aceptado=valor_aceptado,
        tabla_excel=tabla_excel,
    )

    resultado = await glosa_service.analizar(
        data=data,
        contexto_pdf=contexto_pdf,
        contratos_db=contratos_db,
    )

    try:
        val_num = glosa_service.convertir_numero(resultado.valor_objetado)
        val_ac_num = glosa_service.convertir_numero(valor_aceptado)
        estado = "ACEPTADA" if val_ac_num > 0 else "LEVANTADA"
        registro = GlosaRecord(
            eps=eps,
            paciente=resultado.paciente,
            codigo_glosa=resultado.codigo_glosa,
            valor_objetado=val_num,
            valor_aceptado=val_ac_num,
            etapa=etapa,
            estado=estado,
            dictamen=resultado.dictamen,
        )
        db.add(registro)
        db.commit()
    except Exception:
        pass 

    return resultado


_analytics_cache = {"data": None, "ts": None}

@app.get("/analytics")
def obtener_analytics(db: Session = Depends(get_db)):
    global _analytics_cache
    ahora = datetime.now()
    if _analytics_cache["ts"] and (ahora - _analytics_cache["ts"]).seconds < 300:
        return _analytics_cache["data"]

    hoy = ahora.date()
    mes_inicio = hoy.replace(day=1)

    glosas_hoy = db.query(GlosaRecord).filter(func.date(GlosaRecord.creado_en) == hoy).count()
    glosas_mes = db.query(GlosaRecord).filter(func.date(GlosaRecord.creado_en) >= mes_inicio).count()

    stats = db.query(
        func.sum(GlosaRecord.valor_objetado).label('obj'),
        func.sum(GlosaRecord.valor_aceptado).label('acep')
    ).filter(func.date(GlosaRecord.creado_en) >= mes_inicio).first()

    v_obj = stats.obj or 0
    v_def = v_obj - (stats.acep or 0)
    tasa = round((v_def / v_obj) * 100, 1) if v_obj > 0 else 0

    eps_q = db.query(GlosaRecord.eps, func.count(GlosaRecord.id).label('n')) \
        .group_by(GlosaRecord.eps) \
        .order_by(func.count(GlosaRecord.id).desc()) \
        .limit(5).all()

    res = {
        "glosas_hoy": glosas_hoy,
        "glosas_mes": glosas_mes,
        "valor_objetado_mes": v_obj,
        "valor_recuperado_mes": v_def,
        "tasa_exito_pct": tasa,
        "top_eps": [{"eps": r.eps, "total": r.n} for r in eps_q],
        "top_codigos": [],
        "graficas": {}
    }
    _analytics_cache.update({"data": res, "ts": ahora})
    return res


@app.get("/plantillas")
def listar_plantillas(db: Session = Depends(get_db)):
    return db.query(PlantillaGlosa).all()

@app.post("/plantillas")
async def crear_plantilla(data: dict, db: Session = Depends(get_db)):
    nueva = PlantillaGlosa(titulo=data['titulo'], texto=data['texto'])
    db.add(nueva)
    db.commit()
    return {"status": "ok"}

@app.get("/glosas")
def listar_historial(db: Session = Depends(get_db)):
    return db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(100).all()

@app.get("/contratos")
def listar_contratos(db: Session = Depends(get_db)):
    return db.query(ContratoRecord).all()

@app.post("/contratos")
def guardar_contrato(data: dict, db: Session = Depends(get_db)):
    existente = db.query(ContratoRecord).filter(ContratoRecord.eps == data['eps']).first()
    if existente:
        existente.detalles = data['detalles']
    else:
        db.add(ContratoRecord(eps=data['eps'], detalles=data['detalles']))
    db.commit()
    return {"status": "ok"}

@app.delete("/contratos/{eps}")
def eliminar_contrato(eps: str, db: Session = Depends(get_db)):
    contrato = db.query(ContratoRecord).filter(ContratoRecord.eps == eps).first()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    db.delete(contrato)
    db.commit()
    return {"status": "ok"}

@app.get("/exportar-historial")
def exportar_historial(db: Session = Depends(get_db)):
    glosas = db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).all()
    lines = ["Fecha,EPS,Paciente,Código Glosa,Valor Objetado,Valor Aceptado,Estado"]
    for g in glosas:
        fecha = g.creado_en.strftime("%Y-%m-%d") if g.creado_en else ""
        lines.append(
            f"{fecha},{g.eps},{g.paciente or ''},{g.codigo_glosa},"
            f"{g.valor_objetado or 0},{g.valor_aceptado or 0},{g.estado}"
        )
    csv_content = "\n".join(lines)
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Reporte_Glosas_HUS.csv"}
    )

@app.post("/descargar-pdf")
async def generar_pdf_endpoint(data: dict):
    pdf_bytes = crear_oficio_pdf(data['eps'], data['resumen'], data['dictamen'])
    
    # ✅ NOMBRE INTELIGENTE DEL PDF
    fecha_hoy = datetime.now().strftime("%d-%m-%Y")
    nombre_limpio = data['eps'].replace(" ", "_").replace("/", "-")
    nombre_archivo = f"Respuesta_{nombre_limpio}_{fecha_hoy}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )
