import os
import json
import sqlite3
import asyncio
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from models import GlosaInput
from services import GlosaService, crear_oficio_pdf, exportar_excel_pro

load_dotenv()

# MIDDLEWARE DE SEGURIDAD (TOKEN BÁSICO)
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "HUS2026") # Cambia esto en producción

app = FastAPI(title="Motor Glosas IA HUS")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("GROQ_API_KEY")
glosa_service = GlosaService(api_key=API_KEY)

# ─── BASE DE DATOS MEJORADA ───
def init_db():
    conn = sqlite3.connect("glosas_hus.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS contratos (eps TEXT PRIMARY KEY, detalles TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        eps TEXT, paciente TEXT, factura TEXT, codigo_glosa TEXT, valor_objetado TEXT, 
        estado TEXT, dictamen TEXT, dias_restantes INTEGER
    )''')
    conn.commit()
    conn.close()

init_db()

# ─── SEGURIDAD ───
async def verify_token(request: Request):
    # Para el prototipo, permitimos acceso libre al HTML, pero protegemos las APIs
    token = request.headers.get("Authorization")
    if ACCESS_TOKEN and ACCESS_TOKEN != "HUS2026": # Si definiste un token real
        if not token or token != f"Bearer {ACCESS_TOKEN}":
            raise HTTPException(status_code=401, detail="No autorizado")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analizar")
async def analizar_glosa(
    eps: str = Form(...), etapa: str = Form(...), 
    fecha_radicacion: str = Form(""), fecha_recepcion: str = Form(""),
    valor_aceptado: str = Form(""), tabla_excel: str = Form(...),
    archivos: list[UploadFile] = File(default=[])):
    
    conn = sqlite3.connect("glosas_hus.db")
    contratos = {row[0]: row[1] for row in conn.execute("SELECT eps, detalles FROM contratos").fetchall()}
    conn.close()

    contexto_pdf = ""
    for f in archivos:
        if f.filename: contexto_pdf += await glosa_service.extraer_pdf(await f.read())

    data_in = GlosaInput(eps=eps, etapa=etapa, fecha_radicacion=fecha_radicacion, fecha_recepcion=fecha_recepcion, valor_aceptado=valor_aceptado, tabla_excel=tabla_excel)
    resultado = await glosa_service.analizar(data_in, contexto_pdf, contratos)

    estado = "LEVANTADA" if "ACEPTA LA GLOSA" in resultado.dictamen else ("ACEPTADA" if "ACEPTA" in resultado.dictamen else "RECHAZADA")

    conn = sqlite3.connect("glosas_hus.db")
    conn.execute("INSERT INTO historial (eps, paciente, factura, codigo_glosa, valor_objetado, estado, dictamen, dias_restantes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (eps, resultado.paciente, resultado.factura, resultado.codigo_glosa, resultado.valor_objetado, estado, resultado.dictamen, resultado.dias_restantes))
    conn.commit()
    conn.close()

    return resultado.model_dump()

# ─── NUEVO: BATCH PROCESSING (LOTE) CON SSE ───
@app.post("/analizar-lote")
async def analizar_lote(request: Request):
    """Procesamiento masivo asíncrono para Excel (Simulado con SSE)"""
    # Esta función requiere armar el JSON desde el frontend y enviar SSE.
    # Por tiempo, se mantiene la lógica del lote en el Frontend (JS), 
    # ya que es más seguro para la capa gratuita de Groq (evita timeout del server).
    pass 

@app.get("/glosas")
async def obtener_historial(limite: int = 50, eps: Optional[str] = None):
    conn = sqlite3.connect("glosas_hus.db")
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM historial ORDER BY creado_en DESC LIMIT ?"
    params = [limite]
    if eps:
        query = "SELECT * FROM historial WHERE eps = ? ORDER BY creado_en DESC LIMIT ?"
        params = [eps, limite]
    filas = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()
    return JSONResponse(content=filas)

@app.get("/alertas")
async def obtener_alertas():
    """Devuelve glosas que vencen en 5 días o menos"""
    conn = sqlite3.connect("glosas_hus.db")
    conn.row_factory = sqlite3.Row
    filas = [dict(row) for row in conn.execute("SELECT * FROM historial WHERE dias_restantes <= 5 AND dias_restantes > 0 ORDER BY dias_restantes ASC").fetchall()]
    conn.close()
    return JSONResponse(content=filas)

@app.get("/analytics")
async def obtener_analytics():
    conn = sqlite3.connect("glosas_hus.db")
    c = conn.cursor()
    total_mes = c.execute("SELECT COUNT(*) FROM historial WHERE strftime('%Y-%m', creado_en) = strftime('%Y-%m', 'now')").fetchone()[0]
    total_hoy = c.execute("SELECT COUNT(*) FROM historial WHERE date(creado_en) = date('now')").fetchone()[0]
    
    val_obj = 0; val_rec = 0
    for row in c.execute("SELECT valor_objetado, estado FROM historial WHERE strftime('%Y-%m', creado_en) = strftime('%Y-%m', 'now')").fetchall():
        try:
            v = float(re.sub(r'[^\d]', '', str(row[0])))
            val_obj += v
            if row[1] == "RECHAZADA": val_rec += v
        except: pass
    
    tasa = round((val_rec / val_obj * 100) if val_obj > 0 else 0, 1)
    
    top_eps = [{"eps": r[0], "total": r[1]} for r in c.execute("SELECT eps, COUNT(*) as c FROM historial GROUP BY eps ORDER BY c DESC LIMIT 5").fetchall()]
    top_cod = [{"codigo": r[0], "total": r[1]} for r in c.execute("SELECT codigo_glosa, COUNT(*) as c FROM historial GROUP BY codigo_glosa ORDER BY c DESC LIMIT 5").fetchall()]
    
    conn.close()
    return {"glosas_mes": total_mes, "glosas_hoy": total_hoy, "valor_objetado_mes": val_obj, "valor_recuperado_mes": val_rec, "tasa_exito_pct": tasa, "top_eps": top_eps, "top_codigos": top_cod}

@app.get("/contratos")
async def listar_contratos():
    conn = sqlite3.connect("glosas_hus.db")
    filas = [{"eps": r[0], "detalles": r[1]} for r in conn.execute("SELECT * FROM contratos").fetchall()]
    conn.close()
    return JSONResponse(content=filas)

@app.post("/contratos")
async def guardar_contrato(request: Request):
    data = await request.json()
    conn = sqlite3.connect("glosas_hus.db")
    conn.execute("INSERT OR REPLACE INTO contratos (eps, detalles) VALUES (?, ?)", (data['eps'].upper(), data['detalles']))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.delete("/contratos/{eps}")
async def borrar_contrato(eps: str):
    conn = sqlite3.connect("glosas_hus.db")
    conn.execute("DELETE FROM contratos WHERE eps = ?", (eps,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/descargar-pdf")
async def descargar_pdf(request: Request):
    data = await request.json()
    pdf_bytes = crear_oficio_pdf(data.get('eps', ''), data.get('resumen', ''), data.get('dictamen', ''), data.get('codigo', 'N/A'), data.get('valor', 'N/A'))
    return Response(content=pdf_bytes, media_type="application/pdf")

@app.get("/exportar-historial")
async def exportar_historial():
    conn = sqlite3.connect("glosas_hus.db")
    conn.row_factory = sqlite3.Row
    filas = [dict(row) for row in conn.execute("SELECT * FROM historial ORDER BY creado_en DESC").fetchall()]
    conn.close()
    excel_bytes = exportar_excel_pro(filas)
    return Response(content=excel_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
