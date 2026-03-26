import os
from typing import List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from auth import get_current_user, create_access_token, verify_password
from services import GlosaService, crear_oficio_pdf
from models import (
    GlosaRecord, ContratoRecord, UsuarioRecord,
    PlantillaGlosa, GlosaResult
)
from database import engine, Base, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Motor Glosas HUS", version="2.2")

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://motor-glosas-hus.onrender.com", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

glosa_service = GlosaService(api_key=os.getenv("GROQ_API_KEY"))


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.post("/token")
async def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(UsuarioRecord).filter(UsuarioRecord.email == data.get("username")).first()
    if not user or not verify_password(data.get("password"), user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


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
    user: UsuarioRecord = Depends(get_current_user)
):
    contexto_pdf = ""
    if archivos:
        for arc in archivos:
            if arc.filename:
                content = await arc.read()
                contexto_pdf += await glosa_service.extraer_pdf(content)

    return await glosa_service.analizar(
        db=db, eps=eps, etapa=etapa,
        fecha_radicacion=fecha_radicacion, fecha_recepcion=fecha_recepcion,
        valor_aceptado=valor_aceptado, tabla_excel=tabla_excel,
        contexto_pdf=contexto_pdf
    )


_analytics_cache = {"data": None, "ts": None}


@app.get("/analytics")
def obtener_analytics(
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
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
def listar_plantillas(
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
    return db.query(PlantillaGlosa).all()


@app.post("/plantillas")
async def crear_plantilla(
    data: dict,
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
    nueva = PlantillaGlosa(titulo=data['titulo'], texto=data['texto'])
    db.add(nueva)
    db.commit()
    return {"status": "ok"}


@app.get("/glosas")
def listar_historial(
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
    return db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(100).all()


@app.get("/contratos")
def listar_contratos(
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
    return db.query(ContratoRecord).all()


@app.post("/contratos")
def guardar_contrato(
    data: dict,
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
    nuevo = ContratoRecord(eps=data['eps'], detalles=data['detalles'])
    db.add(nuevo)
    db.commit()
    return {"status": "ok"}


@app.delete("/contratos/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
    contrato = db.query(ContratoRecord).filter(ContratoRecord.eps == eps).first()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    db.delete(contrato)
    db.commit()
    return {"status": "ok"}


@app.get("/exportar-historial")
def exportar_historial(
    db: Session = Depends(get_db),
    user: UsuarioRecord = Depends(get_current_user)
):
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
async def generar_pdf_endpoint(
    data: dict,
    user: UsuarioRecord = Depends(get_current_user)
):
    pdf_bytes = crear_oficio_pdf(data['eps'], data['resumen'], data['dictamen'])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Respuesta_{data['eps']}.pdf"}
    )
    
@app.get("/setup-admin")
def setup_admin(db: Session = Depends(get_db)):
    from auth import get_password_hash
    existente = db.query(UsuarioRecord).filter(UsuarioRecord.email == "admin@hus.gov.co").first()
    if existente:
        return {"msg": "El usuario ya existe"}
    nuevo = UsuarioRecord(
        email="admin@hus.gov.co",
        nombre="Administrador HUS",
        hashed_password=get_password_hash("HUS2026*")
    )
    db.add(nuevo)
    db.commit()
    return {"msg": "Usuario creado", "email": "admin@hus.gov.co", "password": "HUS2026*"}
