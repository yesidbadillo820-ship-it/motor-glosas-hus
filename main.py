import os
from typing import List, Optional
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

# Importamos el cerebro de la IA y el generador de PDFs
from services import GlosaService, crear_oficio_pdf
from models import GlosaRecord, ContratoRecord, PlantillaGlosa, GlosaInput
from database import engine, Base, get_db, SessionLocal

# Crear tablas si no existen
Base.metadata.create_all(bind=engine)

# =====================================================================
# 🛡️ DICCIONARIO MAESTRO DE CONTRATOS (EL ARSENAL LEGAL)
# =====================================================================
BASE_CONTRATOS_DEFAULT = {
    "FOMAG": "CONTRATOS VIGENTES: 12076-604-2024 y 12076-359-2025. TARIFAS ACORDADAS: SOAT -15% (aplicable a 2.653 CUPS según negociación), Tarifas Institucionales y Paquetes Integrales específicos (Tórax, IVE, Columna, Terapias Física/Ocupacional/Lenguaje y Gastro). SOPORTE LEGAL Y DE VIGENCIA: Acta de Negociación Precontractual N.° 09 (agosto 2024) y Carta de Ratificación de Manifestación de Interés del 29 de julio de 2025, suscrita por el Gerente Ricardo Arturo Hoyos Lanziano. Dicha carta establece expresamente en su numeral 3 que 'Las tarifas actuales seguirán vigentes... teniendo como punto de partida lo establecido en el manual tarifario E.S.E. HUS y el Anexo 1 Tarifario Dinámico de FOMAG'.",
    
    "AURORA": "CONTRATOS VIGENTES: GID ARL 0090 (Atención ATEL / Riesgos Laborales) y GID AP 0090 (Accidentes Personales y Vida). TARIFAS ACORDADAS: Manual SOAT vigente con un descuento del 3% (SOAT - 3%). CONDICIÓN ESPECIAL FACTURACIÓN INSUMOS Y MEDICAMENTOS: Según la Cláusula Novena de ambos contratos (suscritos en agosto de 2024), los medicamentos, materiales e insumos que no se encuentren contemplados en el manual tarifario SOAT se facturarán al precio de costo de adquisición (factura de compra del proveedor) más un diez por ciento (10%) por concepto de recuperación, administración o manejo.",
    
    "COMPENSAR": "CONTRATO VIGENTE Y ACUERDO TARIFARIO: Contrato CSS009-2024 y Acuerdo Tarifario formalizado con la E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER (NIT 900006037). TARIFAS ACORDADAS: La liquidación de los servicios se rige estrictamente por los anexos contractuales, aplicando el Manual Tarifario SOAT vigente con un descuento del quince por ciento (SOAT -15%) y Tarifas Propias (Institucionales) debidamente pactadas entre las partes. EXCLUSIONES Y RESPONSABILIDADES (MAOS Y ONCOLÓGICOS): El acuerdo excluye expresamente la cobertura de patologías y medicamentos oncológicos. Asimismo, se establece contractualmente que el suministro de Medicamentos e Insumos de Alto Costo (MAOS) es responsabilidad directa y exclusiva de la EPS COMPENSAR. CONDICIÓN PARA INSUMOS NO TARIFADOS: Todo material, medicamento o insumo utilizado que carezca de tarifa pactada en los anexos, se facturará obligatoriamente al costo de adquisición (soportado en la factura de compra) más el porcentaje de administración aplicable según el contrato CSS009-2024.",
    
    "COOSALUD": "CONTRATOS VIGENTES: 68001S00060339-24 y 68001C00060340-24. TARIFAS ACORDADAS: La facturación se rige por los anexos tarifarios pactados, aplicando el Manual Tarifario SOAT vigente con un descuento del quince por ciento (SOAT -15%) y un anexo específico de Tarifas Institucionales (Propias). RESPONSABILIDADES ESPECIALES (MAOS Y ONCOLÓGICOS): El acuerdo contractual establece una delimitación estricta de responsabilidades en los suministros: Los Medicamentos de Alto Costo (MAOS) son responsabilidad y provisión de la E.S.E. HUS (por lo cual su cobro es plenamente procedente, pertinente y amparado por el contrato), mientras que los tratamientos y medicamentos oncológicos son responsabilidad directa y exclusiva de la EPS COOSALUD. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento o insumo utilizado que carezca de tarifa en los anexos, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra) más el porcentaje de administración aplicable.",
    
    "DISPENSARIO MEDICO": "CONTRATO VIGENTE: 440-DIGSA/DMBUG-2025 suscrito con la Dirección General de Sanidad Militar (DIGSA) - Dispensario Médico Bucaramanga. TARIFAS ACORDADAS Y ANEXOS: La liquidación de los servicios se rige estrictamente por el Manual Tarifario SOAT (liquidado en SMLV) con un descuento del veinte por ciento (SOAT -20%), y por el documento contractual 'Anexo 6.2 Precios de Referencia', el cual establece de forma vinculante las Tarifas Institucionales Propias para: Servicios de Procedimientos, Paquetes y/o Programas, Laboratorio Clínico e Imagenología. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento de alto costo o insumo utilizado que no se encuentre expresamente codificado ni tarifado en los anexos descritos, se facturará obligatoriamente al costo de adquisición (soportado con la factura de compra del proveedor) más el porcentaje de administración pactado. DEFENSA CONTRACTUAL: El valor cobrado obedece fielmente a la liquidación correcta bajo los anexos mencionados, por lo que aplicar tarifas diferentes o desconocer los precios de referencia propios y de adquisición constituye un incumplimiento al acuerdo de voluntades y al principio de buena fe contractual.",
    
    "NUEVA EPS": "CONTRATO VIGENTE: 02-01-06-00077-2017. SOPORTE TARIFARIO Y ACTAS: Acta de Negociación No. 1388 de 2024 y Acta de Negociación 2025. TARIFAS ACORDADAS: La facturación se rige por los anexos tarifarios pactados, aplicando el Manual Tarifario SOAT con un descuento del veinte por ciento (SOAT -20%) y un anexo específico de Tarifas Institucionales (Propias). RESPONSABILIDAD EXPRESA EN ONCOLÓGICOS: El marco contractual con NUEVA EPS establece expresamente que la provisión y suministro de Medicamentos Oncológicos está a cargo de la E.S.E. HUS. Por consiguiente, cualquier glosa que pretenda objetar estos medicamentos bajo el argumento de 'responsabilidad de la EPS' o 'falta de autorización' es improcedente, siendo su cobro totalmente legítimo y amparado por el contrato. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento o insumo utilizado que carezca de tarifa en los anexos, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable. Desconocer este esquema o aplicar tarifas unilaterales constituye un incumplimiento del contrato y vulnera el principio de buena fe (Art. 871 del Código de Comercio).",
    
    "POLICIA NACIONAL": "CONTRATOS VIGENTES: 068-5-200004-26 (Servicios de Salud Generales) y 068-5-200006-26 (Atención y Ruta Oncológica Integral). TARIFAS ACORDADAS Y ANEXOS: La liquidación de los servicios se rige estrictamente por el Manual Tarifario SOAT vigente, liquidado y expresado obligatoriamente en Unidades de Valor Básico (UVB) con un descuento del ocho por ciento (SOAT UVB -8%). ADEMAS, aplican de forma vinculante los anexos de: Tarifas Propias, Paquetes, Servicios Ambulatorios y Órtesis/Prótesis. COBERTURA ONCOLÓGICA EXPRESA: En virtud del contrato 068-5-200006-26, el HUS es responsable directo de la atención integral en oncología, LO QUE INCLUYE EXPRESAMENTE la provisión y cobro de medicamentos oncológicos; por lo tanto, cualquier glosa que alegue 'no cobertura' o 'responsabilidad de la EPS' en el manejo oncológico es contractualmente falsa e improcedente. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo insumo, material o medicamento (incluyendo alto costo) que carezca de tarifa en los anexos, se facturará obligatoriamente al costo de adquisición (soportado con la factura de compra) más el porcentaje de administración pactado. Liquidar por debajo del anexo o usar SMLV en lugar de UVB constituye una violación al acuerdo.",
    
    "POSITIVA": "CONTRATO VIGENTE Y ANEXOS: Contrato N.° 525 de 2017, modificado y actualizado mediante el OTROSÍ N.° 3 (OT3-0525-2017). TARIFAS ACORDADAS: La facturación se rige estrictamente por los anexos tarifarios pactados, aplicando el Manual Tarifario SOAT (liquidado en SMLV) con un descuento del quince por ciento (SOAT -15%) y el Anexo 1 de Tarifas Institucionales (Propias). ALCANCE DE LA COBERTURA (ATEL): Al tratarse de una cobertura por Riesgos Laborales (Accidente de Trabajo o Enfermedad Laboral - ATEL), la integralidad del servicio está garantizada normativamente, por lo que toda glosa de 'pertinencia' que intente evadir la cobertura de servicios derivados del trauma o evento laboral es improcedente. INSUMOS Y MATERIAL DE OSTEOSÍNTESIS: Todo material de osteosíntesis, medicamento o insumo de alto costo utilizado que carezca de tarifa en el Anexo contractual, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable. Desconocer este esquema, o glosar por 'falta de lista de precios', constituye un incumplimiento flagrante del Otrosí 3 y vulnera el principio de buena fe (Art. 871 del Código de Comercio).",
    
    "PPL": "CONTRATO VIGENTE Y ANEXOS: Contrato N.° IPS-001B-2022 suscrito con el Consorcio Fondo de Atención en Salud PPL (Fiduciaria Central S.A.), vigente y actualizado mediante el OTROSÍ N.° 26. TARIFAS ACORDADAS: La facturación se rige por los anexos tarifarios pactados, aplicando el Manual Tarifario SOAT vigente con un descuento del quince por ciento (SOAT -15%) y un anexo específico de Tarifas Institucionales (Propias). RESPONSABILIDAD EXPRESA EN MEDICAMENTOS Y MAOS: El acuerdo contractual establece expresamente que la provisión, suministro y cobro de Medicamentos (incluyendo los de Alto Costo - MAOS) están a cargo de la E.S.E. HUS para la Población Privada de la Libertad (PPL). Por consiguiente, cualquier glosa que pretenda objetar estos medicamentos o insumos bajo el argumento de 'responsabilidad del asegurador', 'falta de autorización' o 'no cobertura' es contractualmente improcedente y atenta contra el principio de integralidad garantizado a esta población. INSUMOS NO TARIFADOS: Todo material, medicamento o insumo utilizado que carezca de tarifa en los anexos, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable. Aplicar tarifas diferentes u objetar la lista de precios constituye un incumplimiento del contrato y vulnera el principio de buena fe (Art. 871 del Código de Comercio).",
    
    "FIDUCIARIA CENTRAL": "CONTRATO VIGENTE Y ANEXOS: Contrato N.° IPS-001B-2022 suscrito con el Consorcio Fondo de Atención en Salud PPL (Fiduciaria Central S.A.), vigente y actualizado mediante el OTROSÍ N.° 26. TARIFAS ACORDADAS: La facturación se rige por los anexos tarifarios pactados, aplicando el Manual Tarifario SOAT vigente con un descuento del quince por ciento (SOAT -15%) y un anexo específico de Tarifas Institucionales (Propias). RESPONSABILIDAD EXPRESA EN MEDICAMENTOS Y MAOS: El acuerdo contractual establece expresamente que la provisión, suministro y cobro de Medicamentos (incluyendo los de Alto Costo - MAOS) están a cargo de la E.S.E. HUS para la Población Privada de la Libertad (PPL). Por consiguiente, cualquier glosa que pretenda objetar estos medicamentos o insumos bajo el argumento de 'responsabilidad del asegurador', 'falta de autorización' o 'no cobertura' es contractualmente improcedente y atenta contra el principio de integralidad garantizado a esta población. INSUMOS NO TARIFADOS: Todo material, medicamento o insumo utilizado que carezca de tarifa en los anexos, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable. Aplicar tarifas diferentes u objetar la lista de precios constituye un incumplimiento del contrato y vulnera el principio de buena fe (Art. 871 del Código de Comercio).",
    
    "PRECIMED": "CONTRATO VIGENTE Y ANEXOS: Contrato N.° 319 de 2024. TARIFAS ACORDADAS: La facturación y liquidación de los servicios se rige estrictamente por los anexos tarifarios pactados entre las partes, aplicando de manera exclusiva y vinculante las Tarifas Institucionales (Propias) definidas en el acuerdo. DEFENSA TARIFARIA: Cualquier glosa que pretenda reliquidar o reducir el valor de los procedimientos utilizando el Manual Tarifario SOAT, ISS u otro esquema externo no contemplado expresamente en el anexo de Tarifas Institucionales es contractualmente improcedente y será rechazada de plano. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento o insumo utilizado que carezca de tarifa en el anexo institucional, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable. Desconocer este esquema, o aplicar tarifas de forma unilateral, constituye un incumplimiento directo del Contrato N.° 319 de 2024 y vulnera el principio de buena fe contractual (Art. 871 del Código de Comercio).",
    
    "SALUD MIA": "CONTRATOS VIGENTES 2025: CSA2025EVE3A005 (Régimen Contributivo) y SSA2025EVE3A005 (Régimen Subsidiado). TARIFAS ACORDADAS: La liquidación de los servicios se rige estrictamente por los anexos tarifarios pactados para la vigencia 2025, aplicando el Manual Tarifario SOAT vigente con el descuento establecido en la negociación y el Anexo de Tarifas Institucionales (Propias). DEFENSA TARIFARIA Y DE COBERTURA: Se rechaza de plano cualquier glosa de 'mayor valor' o 'no cobertura' que pretenda desconocer las tarifas propias pactadas o confundir los alcances de los contratos CSA2025EVE3A005 y SSA2025EVE3A005. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento (incluyendo Alto Costo/MAOS) o insumo utilizado que carezca de tarifa explícita en los anexos, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable. Aplicar tarifas diferentes, objetar la lista de precios o negar la cobertura estando el paciente activo, constituye un incumplimiento del contrato vigente para 2025 y vulnera el principio de buena fe contractual (Art. 871 del Código de Comercio).",
    
    "SECRETARIA DE SANTANDER": "MARCO NORMATIVO Y LEGAL VIGENTE: La prestación de servicios y su respectiva facturación se rigen de manera estricta y vinculante por la Resolución Departamental 15997 de 2017, amparada y ratificada mediante el 'Acta de Certificación y Concepto Jurídico sobre la aplicabilidad de la Resolución 15997 de 2017' emitida por el propio ente territorial. TARIFAS ACORDADAS: La liquidación de todos los procedimientos, estancias y honorarios se realiza dando cumplimiento irrestricto a los lineamientos tarifarios dictados en dicha Resolución. DEFENSA JURÍDICA: Se rechaza de plano cualquier glosa (ya sea de pertinencia, cobertura o mayor valor) que pretenda desconocer o inaplicar la Resolución 15997 de 2017. Objetar estas tarifas equivale a que la Secretaría de Salud desconozca su propio concepto jurídico y certificación vigente. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento o insumo de alto costo utilizado que carezca de tarifa explícita en la mencionada Resolución, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable y legalmente reconocido. La no aceptación de esta premisa vulnera el principio de confianza legítima y el equilibrio económico del prestador público (E.S.E. HUS).",
    
    "SUMIMEDICAL": "CONTRATO Y VIGENCIA: Acuerdos tarifarios notificados, aceptados y pactados para la vigencia 2025. TARIFAS ACORDADAS: La facturación y liquidación de los servicios prestados se rige de manera estricta y vinculante por los anexos tarifarios pactados, aplicando el Manual Tarifario SOAT vigente con el porcentaje de negociación establecido y el respectivo Anexo de Tarifas Institucionales (Propias) de la E.S.E. HUS. DEFENSA TARIFARIA: Se rechaza de plano cualquier glosa de 'mayor valor' (Ej. TA5801) que pretenda desconocer las tarifas propias pactadas en el anexo Institucional, intentando aplicar errónea y unilateralmente el manual SOAT para procedimientos que ya cuentan con un valor integral acordado entre las partes. INSUMOS Y MEDICAMENTOS NO TARIFADOS: Todo material, medicamento (incluyendo de Alto Costo/MAOS) o insumo utilizado que carezca de tarifa explícita en los anexos mencionados, se facturará obligatoriamente al costo de adquisición (soportado en factura de compra del proveedor) más el porcentaje de administración aplicable según el acuerdo. Aplicar tarifas diferentes, objetar la lista de precios o desconocer los anexos de 2025 constituye un incumplimiento contractual y vulnera el principio de buena fe (Art. 871 del Código de Comercio).",

    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO. En ausencia de un acuerdo contractual vigente entre las partes, la facturación se rige obligatoriamente por el marco legal aplicable a la venta de servicios de salud, liquidando los procedimientos, estancias y honorarios con base en el Manual Tarifario SOAT vigente sin ningún tipo de descuento. Cualquier objeción de 'mayor valor' (TA5801) o intento de imposición unilateral de tarifas por parte de la EPS carece de fundamento jurídico, contraviniendo la jurisprudencia y las resoluciones del Ministerio de Salud. Así mismo, los insumos y materiales no tarifados se facturarán al costo de adquisición soportado en la factura de compra del proveedor."
}

# Inicializador de la DB (Asegura que los contratos se carguen la primera vez)
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        if db.query(ContratoRecord).count() == 0:
            for eps_name, detalle in BASE_CONTRATOS_DEFAULT.items():
                db.add(ContratoRecord(eps=eps_name, detalles=detalle))
            db.commit()
    finally:
        db.close()
    yield

# =====================================================================
# CONFIGURACIÓN DE LA APLICACIÓN FASTAPI
# =====================================================================
app = FastAPI(title="Motor Glosas HUS - Edición Producción", version="3.0", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS para que el Frontend funcione perfecto en Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir todos para evitar bloqueos en el lanzamiento
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

# =====================================================================
# ENDPOINT PRINCIPAL DE ANÁLISIS (100% BLINDADO)
# =====================================================================
@app.post("/analizar")
@limiter.limit("20/minute")
async def analizar_endpoint(request: Request, db: Session = Depends(get_db)):
    # Leemos el formulario de forma segura (multipart/form-data)
    form = await request.form()
    
    eps = str(form.get("eps", "OTRA / SIN DEFINIR"))
    etapa = str(form.get("etapa", "INICIAL"))
    fecha_radicacion = str(form.get("fecha_radicacion", ""))
    fecha_recepcion = str(form.get("fecha_recepcion", ""))
    valor_aceptado = str(form.get("valor_aceptado", "0"))
    tabla_excel = str(form.get("tabla_excel", ""))
    
    # Extraemos los archivos PDF adjuntos
    archivos = form.getlist("archivos")
    
    contexto_pdf = ""
    for arc in archivos:
        if hasattr(arc, "filename") and arc.filename:
            content = await arc.read()
            contexto_pdf += await glosa_service.extraer_pdf(content)

    # Obtenemos los contratos de la Base de Datos en vivo
    contratos = db.query(ContratoRecord).all()
    contratos_db = {c.eps: c.detalles for c in contratos}

    # Empaquetamos los datos para el servicio
    data = GlosaInput(
        eps=eps,
        etapa=etapa,
        fecha_radicacion=fecha_radicacion,
        fecha_recepcion=fecha_recepcion,
        valor_aceptado=valor_aceptado,
        tabla_excel=tabla_excel,
    )

    # Enviamos a la IA / Cerebro de Auditoría (services.py)
    resultado = await glosa_service.analizar(
        data=data,
        contexto_pdf=contexto_pdf,
        contratos_db=contratos_db,
    )

    # Guardar en Base de Datos el historial de la glosa procesada
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
    except Exception as e:
        logger.error(f"Error guardando en BD: {e}")

    return resultado


# =====================================================================
# RUTAS DE ESTADÍSTICAS Y PANEL DE CONTROL
# =====================================================================
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

@app.get("/glosas")
def listar_historial(db: Session = Depends(get_db)):
    return db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(100).all()

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

# =====================================================================
# RUTAS DE GESTIÓN DE CONTRATOS
# =====================================================================
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

# =====================================================================
# RUTAS DE PDF Y PLANTILLAS
# =====================================================================
@app.post("/descargar-pdf")
async def generar_pdf_endpoint(data: dict):
    # Llama a la función importada desde services.py
    pdf_bytes = crear_oficio_pdf(data['eps'], data['resumen'], data['dictamen'])
    
    fecha_hoy = datetime.now().strftime("%d-%m-%Y")
    nombre_limpio = data['eps'].replace(" ", "_").replace("/", "-")
    nombre_archivo = f"Respuesta_{nombre_limpio}_{fecha_hoy}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )

@app.get("/plantillas")
def listar_plantillas(db: Session = Depends(get_db)):
    return db.query(PlantillaGlosa).all()

@app.post("/plantillas")
async def crear_plantilla(data: dict, db: Session = Depends(get_db)):
    nueva = PlantillaGlosa(titulo=data['titulo'], texto=data['texto'])
    db.add(nueva)
    db.commit()
    return {"status": "ok"}

# =====================================================================
# ARRANQUE PARA RENDER Y LOCAL
# =====================================================================
if __name__ == "__main__":
    import uvicorn
    # Render asigna el puerto dinámicamente. 0.0.0.0 permite acceso externo.
    puerto = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=puerto, reload=False)
