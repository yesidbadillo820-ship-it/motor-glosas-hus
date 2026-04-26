import re
import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.tz import ahora_utc
from app.database import get_db, SessionLocal
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.audit_repository import AuditRepository
from app.services.glosa_service import GlosaService
from app.core.config import get_settings
from app.core.logging_utils import set_request_id, logger
from app.api.deps import get_usuario_actual, get_auditor_o_superior, get_coordinador_o_admin
from app.services.rate_limit_ia import consumir_cupo_ia as _consumir_cupo_ia
from app.models.db import UsuarioRecord, GlosaRecord, ConceptoGlosaRecord

router = APIRouter(prefix="/glosas", tags=["glosas"])


class GlosaFilaInput(BaseModel):
    fila: int
    texto: str
    eps: str
    fecha_radicacion: Optional[str] = None
    fecha_recepcion: Optional[str] = None


class ImportacionMasivaRequest(BaseModel):
    # Si se deja vacío o "AUTO", la EPS se detecta de la primera columna de cada fila.
    eps: Optional[str] = None
    texto_excel: str
    fecha_radicacion: Optional[str] = None
    fecha_recepcion: Optional[str] = None


# ─── Normalizador de nombres de EPS ──────────────────────────────────────────
# El Excel suele traer razones sociales completas (p. ej.
# "ENTIDAD PROMOTORA DE SALUD SANITAS S.A.S") que deben mapearse a la clave
# canónica que usa el resto del sistema (contratos, perfiles, aseguradoras).
_EPS_ALIASES: list[tuple[str, str]] = [
    # (substring a buscar en el texto upper, clave canónica)
    ("SANITAS",                      "SANITAS"),
    ("NUEVA EPS",                    "NUEVA EPS"),
    ("COOSALUD",                     "COOSALUD"),
    ("COMPENSAR",                    "COMPENSAR"),
    ("FAMISANAR",                    "FAMISANAR"),
    ("SALUD TOTAL",                  "SALUD TOTAL"),
    ("SURA",                         "SURA"),
    ("MUTUAL SER",                   "MUTUAL SER"),
    ("SAVIA SALUD",                  "SAVIA SALUD"),
    ("CAPITAL SALUD",                "CAPITAL SALUD"),
    ("ASMET SALUD",                  "ASMET SALUD"),
    ("EMSSANAR",                     "EMSSANAR"),
    ("CAJACOPI",                     "CAJACOPI"),
    ("COMFAMILIAR",                  "COMFAMILIAR"),
    ("COMFENALCO",                   "COMFENALCO"),
    ("ECOOPSOS",                     "ECOOPSOS"),
    ("ALIANSALUD",                   "ALIANSALUD"),
    ("ANAS WAYUU",                   "ANAS WAYUU"),
    ("DUSAKAWI",                     "DUSAKAWI"),
    ("PIJAOS SALUD",                 "PIJAOS SALUD"),
    ("MALLAMAS",                     "MALLAMAS"),
    ("CAPRESOCA",                    "CAPRESOCA"),
    ("SERVICIO OCCIDENTAL DE SALUD", "SOS"),
    ("SOS ",                         "SOS"),
    # Aseguradoras (SOAT / ARL / pólizas)
    ("SEGUROS COMERCIALES BOLIVAR",  "SEGUROS BOLIVAR"),
    ("SEGUROS BOLIVAR",              "SEGUROS BOLIVAR"),
    ("SEGUROS DEL ESTADO",           "SEGUROS DEL ESTADO"),
    ("SEGUROS GENERALES SURAMERICANA", "SURA"),
    ("MAPFRE",                       "MAPFRE"),
    ("AXA COLPATRIA",                "AXA COLPATRIA"),
    ("LA PREVISORA",                 "FOMAG"),
    ("FIDEICOMISOS PATRIMONIOS",     "FOMAG"),
    ("FOMAG",                        "FOMAG"),
    # Regímenes especiales
    ("DISPENSARIO MEDICO",           "DISPENSARIO MEDICO"),
    ("FUERZAS MILITARES",            "DISPENSARIO MEDICO"),
    ("POLICIA NACIONAL",             "SANIDAD POLICIA"),
    ("SANIDAD POLICIA",              "SANIDAD POLICIA"),
    ("UNIDAD DE SERVICIOS PENITENCIARIOS", "USPEC"),
    ("USPEC",                        "USPEC"),
    ("MAGISTERIO",                   "FOMAG"),
]


def _normalizar_eps(valor: str) -> str:
    """Convierte la razón social que viene en el Excel a la clave canónica
    usada por el sistema. Si no encuentra match, devuelve el texto tal cual
    en mayúsculas (sin perder información, el analizador luego trabaja con eso)."""
    if not valor:
        return ""
    texto = re.sub(r"\s+", " ", str(valor).upper().strip())
    for patron, clave in _EPS_ALIASES:
        if patron in texto:
            return clave
    return texto


class GenerarLoteRequest(BaseModel):
    glosa_ids: list[int]
    sobrescribir: bool = False  # si True regenera aunque ya tenga dictamen


class RefinarRequest(BaseModel):
    mensaje: str
    guardar: bool = False  # si True persiste el dictamen refinado en la BD


class ValidarRequest(BaseModel):
    forzar: bool = False


class ReanalizarRequest(BaseModel):
    """R60 P2: petición de re-análisis sobre glosa existente.
    Sin duplicar la fila — actualiza el dictamen de la glosa actual."""
    tono: Optional[str] = "conciliador"
    modo_respuesta: Optional[str] = "defender"


class BulkActualizarEstadoRequest(BaseModel):
    """R71 P1: cambio masivo de estado. Útil cuando llega un Excel
    de respuesta de la EPS con N decisiones (LEVANTADAS, RATIFICADAS)
    para procesar de un golpe."""
    glosa_ids: list[int] = Field(..., min_length=1, max_length=500)
    nuevo_estado: str = Field(..., min_length=3, max_length=50)
    nota: Optional[str] = Field(default=None, max_length=300)


class BulkMoverPapeleraRequest(BaseModel):
    """R71 P2: mueve N glosas a la papelera en una sola transacción.
    Soporta dry_run para preview antes de ejecutar."""
    glosa_ids: list[int] = Field(..., min_length=1, max_length=200)
    motivo: Optional[str] = Field(default=None, max_length=300)
    dry_run: bool = False


def _limpiar_observacion(dictamen_html: str) -> str:
    """Extrae solo el texto del argumento jurídico del dictamen, quitando la
    tabla superior (código/valor/respuesta), los badges, la tabla de resumen
    de valores y la nota al pie de 'asistencia de IA'."""
    if not dictamen_html:
        return ""
    from html import unescape
    import re as _re
    txt = _re.sub(r"<[^>]+>", " ", dictamen_html)
    txt = _re.sub(r"\s+", " ", unescape(txt)).strip()

    # Cortar desde "ARGUMENTACIÓN JURÍDICA" (siempre precede al argumento real)
    for marker in ("ARGUMENTACIÓN JURÍDICA", "RESPUESTA A GLOSA"):
        if marker in txt:
            parts = txt.split(marker, 1)
            # Solo tomar lo que va después si el marker está cerca del inicio
            # (es el header de la tabla) o si hay muy poco texto antes.
            if len(parts) == 2 and len(parts[0]) < 500:
                txt = parts[1].strip()
                break

    # Cortar ANTES de la nota al pie de IA o del resumen de valores
    for cierre in (
        "Nota: Generado con asistencia",
        "Nota: Este documento constituye",
        "Nota: Generado con IA",
        "RESUMEN DE VALORES",
        "Valor objetado Valor aceptado",
    ):
        if cierre in txt:
            txt = txt.split(cierre)[0].strip()

    return txt.strip()


@router.get("/historial", response_model=list)
def historial(
    limit: int = 50,
    eps:   Optional[str] = None,
    db:    Session        = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Historial detallado con todos los campos relevantes para vista IPS."""
    from app.main import _extraer_motivo_glosa
    from app.services.resolver_entidad import resolver_entidad_mostrar
    repo = GlosaRepository(db)
    glosas = repo.listar(limit=limit, eps=eps)
    items = []
    for g in glosas:
        obs_texto = _limpiar_observacion(g.dictamen)
        entidad_real = resolver_entidad_mostrar(
            eps=g.eps,
            tercero_nombre=getattr(g, "tercero_nombre", None),
            eps_codigo=getattr(g, "eps_codigo", None),
        )
        items.append({
            "id": g.id,
            "fecha": g.creado_en.isoformat() if g.creado_en else None,
            "fecha_recepcion": g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
            "fecha_entrega": g.fecha_entrega.isoformat() if g.fecha_entrega else None,
            "entidad": entidad_real,
            "eps": g.eps,  # alias para compatibilidad (valor raw, sin resolver)
            "paciente": g.paciente,
            "factura": g.factura,
            "codigo_glosa": g.codigo_glosa,
            "concepto_glosa": g.concepto_glosa,
            "cups": g.cups_servicio,
            "servicio": g.servicio_descripcion,
            "valor_objetado": g.valor_objetado,
            "valor_aceptado": g.valor_aceptado,
            "glosa_original": _extraer_motivo_glosa(g.texto_glosa_original or ""),
            "codigo_respuesta": g.codigo_respuesta,
            "observacion": obs_texto,
            "etapa": g.etapa,
            "estado": g.estado,
            "dictamen": g.dictamen,
            "dias_restantes": g.dias_restantes,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
        })
    return items


@router.get("/historial-paginado")
def historial_paginado(
    page: int = 1,
    per_page: int = Query(20, ge=1, le=100),
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    search: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    valor_min: Optional[float] = None,
    valor_max: Optional[float] = None,
    tipo: Optional[str] = None,
    semaforo: Optional[str] = None,
    workflow: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Historial con paginación y filtros avanzados (vista detallada IPS)."""
    from app.main import _extraer_motivo_glosa
    repo = GlosaRepository(db)
    resultado = repo.listar_paginado(
        page=page, per_page=per_page,
        eps=eps, estado=estado, search=search,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        valor_min=valor_min, valor_max=valor_max,
        tipo=tipo, semaforo=semaforo, workflow=workflow,
    )

    from app.services.resolver_entidad import resolver_entidad_mostrar
    items = []
    for g in resultado["items"]:
        obs_texto = _limpiar_observacion(g.dictamen)
        entidad_real = resolver_entidad_mostrar(
            eps=g.eps,
            tercero_nombre=getattr(g, "tercero_nombre", None),
            eps_codigo=getattr(g, "eps_codigo", None),
        )
        items.append({
            "id": g.id,
            "eps": g.eps,
            "entidad": entidad_real,
            "paciente": g.paciente,
            "factura": g.factura,
            "codigo_glosa": g.codigo_glosa,
            "concepto_glosa": g.concepto_glosa,
            "cups": g.cups_servicio,
            "servicio": g.servicio_descripcion,
            "valor_objetado": g.valor_objetado,
            "valor_aceptado": g.valor_aceptado,
            "glosa_original": _extraer_motivo_glosa(g.texto_glosa_original or ""),
            "codigo_respuesta": g.codigo_respuesta,
            "observacion": obs_texto,
            "etapa": g.etapa,
            "estado": g.estado,
            "dias_restantes": g.dias_restantes,
            "fecha_recepcion": g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
            "fecha_entrega": g.fecha_entrega.isoformat() if g.fecha_entrega else None,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
        })

    return {
        "items": items,
        "total": resultado["total"],
        "page": resultado["page"],
        "per_page": resultado["per_page"],
        "pages": resultado["pages"],
    }


@router.get("/exportar-xlsx")
def exportar_xlsx(
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    search: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    valor_min: Optional[float] = None,
    valor_max: Optional[float] = None,
    tipo: Optional[str] = None,
    semaforo: Optional[str] = None,
    workflow: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Exporta el historial filtrado a XLSX con las 13 columnas IPS + observación."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from fastapi.responses import StreamingResponse

    repo = GlosaRepository(db)
    glosas = repo.listar_para_export(
        eps=eps, estado=estado, search=search,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        valor_min=valor_min, valor_max=valor_max,
        tipo=tipo, semaforo=semaforo, workflow=workflow,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Historial Glosas HUS"

    headers = [
        "ID", "Fecha Creación", "EPS/Entidad", "Paciente", "Factura",
        "Código Glosa", "Concepto", "CUPS", "Servicio",
        "Valor Objetado", "Valor Aceptado", "Valor Recuperado",
        "Código Respuesta", "Observación EPS", "Dictamen HUS",
        "Etapa", "Estado",
        "Workflow", "Semáforo", "Días Restantes",
        "Fecha Recepción", "Fecha Entrega",
    ]
    ws.append(headers)

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="0B5D8A", end_color="0B5D8A", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    for g in glosas:
        # Observación EPS: lo que la EPS registró al glosar (lo que el
        # auditor VE y REGISTRA en el sistema). Prioridad:
        # observacion_eps (campo explícito) → texto_glosa_original (texto del
        # Excel DGH o del editor) → concepto_glosa (descripción canónica).
        obs_eps_raw = (
            (getattr(g, "observacion_eps", None) or "").strip()
            or (g.texto_glosa_original or "").strip()
            or (g.concepto_glosa or "").strip()
        )
        # Dictamen: el texto limpio (sin HTML) generado por la defensa.
        dictamen_txt = _limpiar_observacion(g.dictamen) or ""
        recuperado = (g.valor_objetado or 0) - (g.valor_aceptado or 0)
        ws.append([
            g.id,
            g.creado_en.strftime("%Y-%m-%d %H:%M") if g.creado_en else "",
            g.eps or "",
            g.paciente or "",
            g.factura or "",
            g.codigo_glosa or "",
            g.concepto_glosa or "",
            g.cups_servicio or "",
            g.servicio_descripcion or "",
            float(g.valor_objetado or 0),
            float(g.valor_aceptado or 0),
            float(recuperado),
            g.codigo_respuesta or "",
            obs_eps_raw[:600] if obs_eps_raw else "",
            dictamen_txt[:800] if dictamen_txt else "",
            g.etapa or "",
            g.estado or "",
            g.workflow_state or "",
            g.prioridad or "",
            g.dias_restantes if g.dias_restantes is not None else "",
            g.fecha_recepcion.strftime("%Y-%m-%d") if g.fecha_recepcion else "",
            g.fecha_entrega.strftime("%Y-%m-%d") if g.fecha_entrega else "",
        ])

    # Ajuste de anchos (22 columnas: Observación EPS 60, Dictamen HUS 80)
    widths = [6, 18, 22, 28, 14, 12, 26, 10, 32, 14, 14, 14, 12, 60, 80, 14, 14, 14, 10, 10, 14, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Formato condicional premium (requirement #8 del user):
    # - Días Restantes columna S (col 19): rojo si ≤ 3, amarillo si ≤ 7, verde si > 7
    # - Estado columna P (col 16): resaltado según valor
    # - Valor Recuperado columna L (col 12): verde si > 0, rojo si negativo
    try:
        from openpyxl.styles import PatternFill
        from openpyxl.formatting.rule import CellIsRule, FormulaRule
        # Aplicar desde fila 2 hasta el final
        last_row = ws.max_row
        if last_row > 1:
            rango_dias = f"S2:S{last_row}"
            rango_recup = f"L2:L{last_row}"
            rango_estado = f"P2:P{last_row}"
            fill_rojo = PatternFill(start_color="FECACA", end_color="FECACA", fill_type="solid")
            fill_amarillo = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
            fill_verde = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
            fill_verde_fuerte = PatternFill(start_color="A7F3D0", end_color="A7F3D0", fill_type="solid")
            # Días restantes — semáforo
            ws.conditional_formatting.add(rango_dias, CellIsRule(operator="lessThanOrEqual", formula=["3"], fill=fill_rojo))
            ws.conditional_formatting.add(rango_dias, CellIsRule(operator="between", formula=["4", "7"], fill=fill_amarillo))
            ws.conditional_formatting.add(rango_dias, CellIsRule(operator="greaterThan", formula=["7"], fill=fill_verde))
            # Valor recuperado
            ws.conditional_formatting.add(rango_recup, CellIsRule(operator="greaterThan", formula=["0"], fill=fill_verde_fuerte))
            # Estado
            ws.conditional_formatting.add(rango_estado, FormulaRule(formula=['EXACT(P2,"CERRADA")'], fill=fill_verde))
            ws.conditional_formatting.add(rango_estado, FormulaRule(formula=['EXACT(P2,"RATIFICADA")'], fill=fill_rojo))
            ws.conditional_formatting.add(rango_estado, FormulaRule(formula=['EXACT(P2,"EXTEMPORANEA")'], fill=fill_amarillo))
    except Exception:
        # Sin formato condicional el Excel sigue siendo válido.
        pass

    # Registrar auditoría de la exportación
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="EXPORTAR_XLSX",
        tabla="historial",
        detalle=f"Registros exportados: {len(glosas)}",
    )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"historial_glosas_hus_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/buscar/{termino}")
def buscar_por_id_o_factura(
    termino: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Busca una glosa por ID interno, factura, consecutivo DGH o radicado.
    Útil para formularios donde el auditor no sabe el ID interno.

    Devuelve lista de coincidencias (puede ser 0, 1 o varias)."""
    termino = (termino or "").strip()
    if not termino:
        raise HTTPException(400, "Término vacío")

    from sqlalchemy import or_
    q = db.query(GlosaRecord)

    # Si es número puro, intentar como ID interno primero
    matches = []
    if termino.isdigit():
        g = q.filter(GlosaRecord.id == int(termino)).first()
        if g:
            matches.append(g)

    # Además buscar por factura / consecutivo / radicado (incluye partial)
    extra = (
        db.query(GlosaRecord)
        .filter(
            or_(
                GlosaRecord.factura.ilike(f"%{termino}%"),
                GlosaRecord.consecutivo_dgh.ilike(f"%{termino}%"),
                GlosaRecord.numero_radicado.ilike(f"%{termino}%"),
            )
        )
        .order_by(GlosaRecord.creado_en.desc())
        .limit(10)
        .all()
    )
    ya = {m.id for m in matches}
    for g in extra:
        if g.id not in ya:
            matches.append(g)

    return [
        {
            "id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "consecutivo_dgh": g.consecutivo_dgh,
            "numero_radicado": g.numero_radicado,
            "codigo_glosa": g.codigo_glosa,
            "paciente": g.paciente,
            "valor_objetado": float(g.valor_objetado or 0),
            "estado": g.estado,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
        }
        for g in matches[:10]
    ]


@router.post("/generar-lote")
async def generar_lote(
    data: GenerarLoteRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Genera respuestas IA en lote para varias glosas pendientes.

    Toma las glosas por ID, reconstruye el input a partir de los campos
    guardados (texto_glosa_original, eps, etapa, fechas, factura) y llama
    al servicio para producir el dictamen. Las glosas que ya tienen
    dictamen se saltan salvo que `sobrescribir=True`.

    Ejecuta hasta 5 en paralelo con `asyncio.Semaphore` para no saturar Groq.
    """
    import asyncio
    from app.models.schemas import GlosaInput

    if not data.glosa_ids:
        raise HTTPException(400, "Lista de IDs vacía")
    if len(data.glosa_ids) > 100:
        raise HTTPException(400, "Máximo 100 glosas por lote")

    repo = GlosaRepository(db)
    contratos = ContratoRepository(db).como_dict()

    cfg = get_settings()
    service = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
    )

    sem = asyncio.Semaphore(5)
    resumen = {
        "total": len(data.glosa_ids),
        "procesadas": 0,
        "saltadas": 0,
        "fallidas": 0,
        "detalle_fallidas": [],
    }

    async def _procesar_una(gid: int):
        async with sem:
            g = repo.obtener_por_id(gid)
            if not g:
                resumen["fallidas"] += 1
                resumen["detalle_fallidas"].append({"id": gid, "error": "no encontrada"})
                return
            if g.dictamen and not data.sobrescribir:
                resumen["saltadas"] += 1
                return
            # Construir input desde los campos del registro
            texto = g.texto_glosa_original or ""
            if not texto and g.codigo_glosa:
                # Fallback mínimo si no hay texto original
                texto = f"{g.codigo_glosa} $ {int(g.valor_objetado or 0):,} {g.concepto_glosa or ''}".strip()
            if not texto:
                resumen["fallidas"] += 1
                resumen["detalle_fallidas"].append({"id": gid, "error": "sin texto_glosa_original"})
                return
            try:
                gi = GlosaInput(
                    eps=g.eps or "SIN DEFINIR",
                    etapa=g.etapa or "RESPUESTA A GLOSA",
                    fecha_radicacion=g.fecha_radicacion_factura.isoformat() if g.fecha_radicacion_factura else None,
                    fecha_recepcion=g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
                    valor_aceptado=str(int(g.valor_aceptado or 0)),
                    tabla_excel=texto,
                    numero_factura=g.factura,
                    numero_radicado=g.numero_radicado,
                )
                # Few-shots según (EPS, código)
                from app.api.routers.plantillas_gold import obtener_few_shot, marcar_usos
                pg = obtener_few_shot(db, eps=gi.eps, codigo_glosa=g.codigo_glosa or "", limite=2)
                res = await service.analizar(gi, contexto_pdf="", contratos_db=contratos, few_shots=[p.argumento for p in pg])
                if pg:
                    marcar_usos(db, [p.id for p in pg])
                g.dictamen = res.dictamen
                g.score = res.score
                g.modelo_ia = res.modelo_ia
                if not g.codigo_respuesta:
                    g.codigo_respuesta = res.tipo.replace("RESPUESTA ", "").strip() or None
                db.commit()
                resumen["procesadas"] += 1
            except Exception as e:
                resumen["fallidas"] += 1
                resumen["detalle_fallidas"].append({"id": gid, "error": str(e)[:200]})
                logger.error(f"Lote: falló glosa {gid}: {e}")

    await asyncio.gather(*[_procesar_una(gid) for gid in data.glosa_ids])

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="GENERAR_LOTE",
        tabla="historial",
        detalle=(
            f"total={resumen['total']} procesadas={resumen['procesadas']} "
            f"saltadas={resumen['saltadas']} fallidas={resumen['fallidas']}"
        ),
    )
    return resumen


@router.post("/{glosa_id}/refinar")
async def refinar_dictamen_endpoint(
    glosa_id: int,
    data: RefinarRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
    _cupo_ia: None = Depends(_consumir_cupo_ia),
):
    """Refina el dictamen de una glosa con instrucciones en lenguaje natural.

    Si `guardar=true`, reemplaza el argumento dentro del HTML actual y persiste.
    Si no, solo devuelve el texto refinado para preview en el modal.
    """
    if not data.mensaje or len(data.mensaje.strip()) < 3:
        raise HTTPException(400, "Mensaje demasiado corto")

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "La glosa no tiene dictamen generado aún")

    cfg = get_settings()
    service = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
    )
    nuevo_argumento = await service.refinar_dictamen(
        dictamen_actual_html=glosa.dictamen,
        mensaje_usuario=data.mensaje,
        eps=glosa.eps or "",
        codigo=glosa.codigo_glosa or "",
    )

    # Reemplazar el bloque de argumento dentro del HTML existente
    import re as _re
    nuevo_html = glosa.dictamen
    patron = _re.compile(
        r'(<div style="font-size:12px;line-height:1\.9;[^"]*">)(.*?)(</div>)',
        _re.DOTALL,
    )
    argumento_html = nuevo_argumento.replace("\n", "<br/>")
    nuevo_html, n = patron.subn(
        lambda m: m.group(1) + argumento_html + m.group(3),
        nuevo_html,
        count=1,
    )
    if n == 0:
        # Si no encontramos el bloque esperado, adjuntamos al final como fallback
        nuevo_html = glosa.dictamen + (
            "<div style='margin-top:12px;padding:12px;background:#ecfeff;"
            "border-left:4px solid #0891b2;border-radius:8px;font-size:12px;line-height:1.8;'>"
            "<b>REFINADO:</b><br/>" + argumento_html + "</div>"
        )

    if data.guardar:
        glosa.dictamen = nuevo_html
        db.commit()
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="REFINAR_IA",
            tabla="historial",
            registro_id=glosa_id,
            campo="dictamen",
            detalle=f"instrucción: {data.mensaje[:200]}",
        )
        # Guardar snapshot en historial de versiones
        try:
            from app.api.routers.versiones import guardar_version
            guardar_version(
                db=db, glosa_id=glosa_id, dictamen_html=nuevo_html,
                accion="REFINAR", autor_email=current_user.email,
                mensaje_refinar=data.mensaje[:500],
            )
        except Exception:
            pass

    return {
        "argumento_refinado": nuevo_argumento,
        "dictamen_html": nuevo_html,
        "guardado": data.guardar,
    }


class ValidarNormasInput(BaseModel):
    texto: str = Field(..., min_length=20, max_length=20000)


@router.post("/validar-normas")
def validar_normas_texto(
    data: ValidarNormasInput,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Valida citas normativas en un texto libre (sin persistir).
    Útil para que el auditor chequee rápido un borrador."""
    from app.services.normativa import validar_citas
    return validar_citas(data.texto)


@router.post("/{glosa_id}/validar")
async def validar_pre_radicacion(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Valida el dictamen antes de radicarlo ante la EPS.

    Hace checks locales (placeholders, factura, normas esperadas,
    citas derogadas) + consulta a la IA para verificar solidez.
    Retorna score de calidad 0-100, hallazgos y si puede_radicar.
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "La glosa aún no tiene dictamen generado")

    cfg = get_settings()
    service = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
    )

    # Calcular días hábiles si hay fechas
    dias = glosa.dias_restantes if glosa.dias_restantes is not None else 0
    # dias_restantes es lo que queda; para el validador queremos días transcurridos
    # cuando no es extemporánea. Si es 0 o negativo asumimos vencida.
    dias_transcurridos = max(0, 20 - dias) if dias > 0 else 25

    resultado = await service.validar_pre_radicacion(
        dictamen_html=glosa.dictamen,
        eps=glosa.eps or "",
        codigo_glosa=glosa.codigo_glosa or "",
        valor_objetado=float(glosa.valor_objetado or 0),
        numero_factura=glosa.factura or "",
        dias_habiles=dias_transcurridos,
    )

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="VALIDAR_PRE_RADICACION",
        tabla="historial",
        registro_id=glosa_id,
        detalle=f"score={resultado['score_calidad']} errores={resultado['errores']} warnings={resultado['warnings']}",
    )
    return resultado


@router.get("/alertas")
def alertas(
    dias: int = 5,
    db:   Session       = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    alertas = repo.alertas_proximas(dias_limite=dias)
    return [
        {
            "id": a.id,
            "eps": a.eps,
            "paciente": a.paciente,
            "codigo_glosa": a.codigo_glosa,
            "valor_objetado": a.valor_objetado,
            "dias_restantes": a.dias_restantes,
            "estado": a.estado,
        }
        for a in alertas
    ]


@router.get("/metrics")
def metrics(
    db:   Session       = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.metrics()


@router.get("/analitica-predictiva")
def analitica_predictiva(
    ventana_dias: int = Query(180, ge=7, le=730),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Analítica agregada: top EPS, tasa de éxito por código/tipo,
    distribución semanal y recomendaciones automáticas."""
    repo = GlosaRepository(db)
    return repo.analitica_predictiva(ventana_dias=ventana_dias)


# Rutas estáticas (sin parámetros) ANTES que rutas dinámicas /{glosa_id}
@router.get("/semaforo")
def semaforo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Retorna el conteo de glosas activas agrupadas por color de semáforo
    (VERDE / AMARILLO / ROJO / NEGRO). Útil para el dashboard."""
    repo = GlosaRepository(db)
    return repo.semaforo_counts()


@router.get("/facetas")
def facetas_glosas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R88 P1: facetas únicas de las glosas para construir filtros UI.

    Devuelve los valores DISTINCT no-nulos de eps, etapa, estado,
    codigo_glosa y gestor_nombre. Útil para que el frontend renderice
    <select> con valores reales en lugar de inputs libres (mejor UX,
    menos typos al filtrar).

    Hace un solo round-trip por columna; cada columna tiene índice
    en BD así que es O(distinct) eficiente.
    """
    def _distinct(col):
        rows = (
            db.query(col)
            .filter(col.isnot(None))
            .distinct()
            .order_by(col.asc())
            .all()
        )
        return [r[0] for r in rows if r[0]]

    return {
        "eps": _distinct(GlosaRecord.eps),
        "etapas": _distinct(GlosaRecord.etapa),
        "estados": _distinct(GlosaRecord.estado),
        "codigos_glosa": _distinct(GlosaRecord.codigo_glosa),
        "gestores": _distinct(GlosaRecord.gestor_nombre),
    }


@router.get("/por-factura")
def glosas_por_factura(
    numero_factura: str = Query(..., min_length=1, max_length=60),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Retorna los conceptos asociados a un número de factura.

    Dos fuentes posibles:
      • Si la factura fue importada desde el Excel de recepción con sus
        hojas I/R, cada fila del listado es un ConceptoGlosaRecord
        (motivo, CUPS, servicio, valor parcial, observación de la EPS).
      • Si no hay conceptos (flujo legacy de masiva), cada fila es un
        GlosaRecord individual por concepto.

    La UI del Analizar usa esto para precargar automáticamente cada
    concepto al auditor sin pegar texto.
    """
    from app.models.db import GlosaRecord as _GR
    factura_limpio = numero_factura.strip()
    if not factura_limpio:
        return {"numero_factura": "", "glosas": []}

    def _nombre_corto_entidad(plan_eps: str, tercero: str = "") -> str:
        """Devuelve el nombre corto de la entidad:
          1. tercero_nombre si existe (FacturaCartera.Tercero.NombreCompletoNA).
          2. sino: último segmento del plan EPS tras " - " / " — " / " – ".
          Ej: "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO
               BUCARAMANG" → "DISPENSARIO MEDICO BUCARAMANG".
        """
        t = (tercero or "").strip()
        if t:
            return t
        p = (plan_eps or "").strip()
        if not p:
            return ""
        # Separar por guiones largos o cortos rodeados de espacios
        import re as _rex
        partes = _rex.split(r"\s+[-–—]\s+", p)
        # Filtrar códigos tipo "U220311" (solo letras+digitos cortos) al inicio
        filtradas = [x.strip() for x in partes if x.strip()]
        if len(filtradas) >= 2:
            # Último segmento suele ser el nombre comercial
            return filtradas[-1]
        return p

    glosas_padre = (
        db.query(_GR)
        .filter(_GR.factura == factura_limpio)
        .order_by(_GR.id.asc())
        .limit(50)
        .all()
    )
    items: list[dict] = []
    glosa_ids = [g.id for g in glosas_padre]

    # Conceptos del nuevo modelo (importación recepción hojas I/R)
    conceptos = []
    if glosa_ids:
        conceptos = (
            db.query(ConceptoGlosaRecord)
            .filter(ConceptoGlosaRecord.glosa_id.in_(glosa_ids))
            .order_by(ConceptoGlosaRecord.codigo_glosa.asc(), ConceptoGlosaRecord.id.asc())
            .all()
        )
    # Mapa glosa_id -> GlosaRecord para enriquecer cada concepto con eps/fechas
    mapa_padre = {g.id: g for g in glosas_padre}

    if conceptos:
        # Caso normal: Excel de recepción completo con hojas I/R
        for c in conceptos:
            padre = mapa_padre.get(c.glosa_id)
            items.append({
                "id": c.glosa_id,                    # glosa padre (para analizar llamando al endpoint)
                "concepto_id": c.id,                  # identificador del concepto específico
                "oid_dgh": c.oid_dgh or "",
                "codigo_glosa": c.codigo_glosa or "",
                "nombre_glosa": c.nombre_glosa or "",
                "cups": c.cups_codigo or "",
                "servicio": c.cups_descripcion or "",
                "centro_costo": c.centro_costo or "",
                "observacion_eps": c.observacion_eps or "",
                "valor_objetado": c.valor_objetado or 0,
                "valor_aceptado": 0,
                "estado": (padre.estado if padre else "") or "",
                "eps": (padre.eps if padre else "") or "",
                # Nombre comercial corto (FacturaCartera.Tercero.NombreCompletoNA),
                # ej: "DISPENSARIO MEDICO BUCARAMANGA". La UI lo prefiere sobre
                # el plan EPS cuando existe.
                "tercero_nombre": _nombre_corto_entidad(
                    padre.eps if padre else "",
                    getattr(padre, "tercero_nombre", None) if padre else "",
                ),
                "concepto_glosa": c.nombre_glosa or "",
                "texto_glosa_original": (c.observacion_eps or "")[:400],
                "fecha_radicacion_factura": padre.fecha_radicacion_factura.isoformat() if padre and padre.fecha_radicacion_factura else None,
                "fecha_recepcion": padre.fecha_recepcion.isoformat() if padre and padre.fecha_recepcion else None,
                "dictamen_generado": bool(c.dictamen_html),
            })
    else:
        # Fallback legacy: 1 GlosaRecord por concepto (flujo importación masiva)
        for g in glosas_padre:
            items.append({
                "id": g.id,
                "concepto_id": None,
                "codigo_glosa": g.codigo_glosa or "",
                "nombre_glosa": g.concepto_glosa or "",
                "concepto_glosa": g.concepto_glosa or "",
                "cups": g.cups_servicio or "",
                "servicio": g.servicio_descripcion or "",
                "centro_costo": "",
                "observacion_eps": "",
                "valor_objetado": g.valor_objetado or 0,
                "valor_aceptado": g.valor_aceptado or 0,
                "estado": g.estado or "",
                "eps": g.eps or "",
                "texto_glosa_original": (g.texto_glosa_original or "")[:400],
                "fecha_radicacion_factura": g.fecha_radicacion_factura.isoformat() if g.fecha_radicacion_factura else None,
                "fecha_recepcion": g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
                "dictamen_generado": bool(g.dictamen),
            })

    eps_unicas = list({g.eps for g in glosas_padre if g.eps})
    # Nombre comercial corto de la entidad (Tercero.NombreCompletoNA). Si todas
    # las glosas padre apuntan al mismo tercero, exponemos ese nombre en la
    # cabecera de la respuesta. Si no, None (la UI cae al plan EPS).
    # Usar el helper para fallback: si tercero_nombre esta vacio, extrae el
    # nombre corto del plan EPS. Así las glosas importadas antes del campo
    # tercero_nombre también muestran el nombre comercial limpio.
    terceros_unicos = list({
        _nombre_corto_entidad(g.eps, getattr(g, "tercero_nombre", None))
        for g in glosas_padre if g.eps
    })
    terceros_unicos = [t for t in terceros_unicos if t]
    total_objetado = sum(i["valor_objetado"] or 0 for i in items)
    return {
        "numero_factura": factura_limpio,
        "total_conceptos": len(items),
        "total_objetado": total_objetado,
        "eps": eps_unicas[0] if len(eps_unicas) == 1 else None,
        "eps_multiples": eps_unicas if len(eps_unicas) > 1 else None,
        "tercero_nombre": terceros_unicos[0] if len(terceros_unicos) == 1 else None,
        "glosa_id": glosa_ids[0] if glosa_ids else None,
        "glosas": items,
    }


@router.get("/facturas-pendientes")
def facturas_pendientes_agrupadas(
    limite: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista facturas con glosas pendientes agrupadas.

    Útil para el flujo "responder por factura" — muestra facturas con
    N conceptos pendientes cada una, asignadas al usuario actual o su
    equipo.
    """
    from app.models.db import GlosaRecord as _GR
    from sqlalchemy import or_ as _or
    repo = GlosaRepository(db)
    # Filtrar por gestor/equipo (igual que mis-asignaciones)
    equipo = getattr(current_user, "equipo", None)
    emails = repo.emails_del_mismo_equipo(equipo) if equipo else [current_user.email]
    if not emails:
        emails = [current_user.email]
    prefijos_nombre = [e.split("@")[0] for e in emails]

    # SUPER_ADMIN/COORDINADOR ve todas
    if current_user.rol in ("SUPER_ADMIN", "COORDINADOR"):
        base_q = db.query(_GR).filter(_GR.factura.isnot(None))
    else:
        condiciones = [_GR.auditor_email.in_(emails)]
        if current_user.nombre:
            condiciones.append(_GR.gestor_nombre.ilike(f"%{current_user.nombre.strip()}%"))
        for p in prefijos_nombre:
            condiciones.append(_GR.gestor_nombre.ilike(f"%{p}%"))
        base_q = db.query(_GR).filter(_or(*condiciones), _GR.factura.isnot(None))
    # Solo estados activos (no LEVANTADA ni CONCILIADA)
    base_q = base_q.filter(_GR.estado.notin_(["LEVANTADA", "CONCILIADA"]))
    # Agrupar por factura
    agrupados: dict[str, list] = {}
    for g in base_q.limit(500).all():
        fact = g.factura
        if not fact:
            continue
        agrupados.setdefault(fact, []).append(g)

    resultado = []
    for fact, glosas in agrupados.items():
        eps_set = {g.eps for g in glosas if g.eps}
        total = sum(g.valor_objetado or 0 for g in glosas)
        codigos = [g.codigo_glosa for g in glosas if g.codigo_glosa]
        fecha_mas_reciente = max((g.fecha_recepcion for g in glosas if g.fecha_recepcion), default=None)
        resultado.append({
            "numero_factura": fact,
            "eps": list(eps_set)[0] if len(eps_set) == 1 else None,
            "cantidad_conceptos": len(glosas),
            "valor_total_objetado": total,
            "codigos": codigos[:10],
            "fecha_recepcion_mas_reciente": fecha_mas_reciente.isoformat() if fecha_mas_reciente else None,
        })
    # Orden: mas conceptos primero, luego mayor valor
    resultado.sort(key=lambda x: (-x["cantidad_conceptos"], -x["valor_total_objetado"]))
    return {"total_facturas": len(resultado), "facturas": resultado[:limite]}


@router.get("/mis-asignaciones")
def mis_asignaciones(
    todas: bool = False,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista las glosas asignadas al usuario actual.

    Los SUPER_ADMIN y COORDINADOR pueden pasar `?todas=true` para ver todas.
    """
    repo = GlosaRepository(db)
    if todas and current_user.rol in ("SUPER_ADMIN", "COORDINADOR"):
        from app.models.db import GlosaRecord as _GR
        glosas = (
            db.query(_GR)
            .filter(_GR.estado.notin_(["LEVANTADA", "CONCILIADA"]))
            .order_by(_GR.dias_restantes.asc())
            .limit(500)
            .all()
        )
    else:
        # Si el usuario pertenece a un equipo (ej. EQUIPO_ASEGURADORAS),
        # agrupar asignaciones de todos los miembros del equipo.
        equipo = getattr(current_user, "equipo", None)
        emails_equipo = repo.emails_del_mismo_equipo(equipo) if equipo else None
        glosas = repo.listar_por_gestor(
            current_user.email, current_user.nombre,
            emails_equipo=emails_equipo,
        )
    from app.services.resolver_entidad import resolver_entidad_mostrar
    return [
        {
            "id": g.id,
            "eps": resolver_entidad_mostrar(
                eps=g.eps,
                tercero_nombre=getattr(g, "tercero_nombre", None),
                eps_codigo=getattr(g, "eps_codigo", None),
            ),
            "eps_raw": g.eps,
            "factura": g.factura,
            "numero_radicado": g.numero_radicado,
            "consecutivo_dgh": g.consecutivo_dgh,
            "gestor_nombre": g.gestor_nombre,
            "valor_objetado": g.valor_objetado,
            "estado": g.estado,
            "prioridad": g.prioridad,
            "dias_restantes": g.dias_restantes,
            "dias_radicacion_dgh": getattr(g, "dias_radicacion_dgh", None),
            "fecha_vencimiento": g.fecha_vencimiento.isoformat() if g.fecha_vencimiento else None,
            "fecha_entrega": g.fecha_entrega.isoformat() if g.fecha_entrega else None,
            "fecha_radicacion_factura": g.fecha_radicacion_factura.isoformat() if g.fecha_radicacion_factura else None,
            "fecha_documento_dgh": g.fecha_documento_dgh.isoformat() if g.fecha_documento_dgh else None,
            "fecha_recepcion": g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
            "radicado_info": g.radicado_info,
            "referencia": g.referencia,
            # Flag para que el front muestre el boton "Marcar Respondida" solo
            # si ya hay un dictamen generado (sino no hay nada que cerrar).
            "dictamen_generado": bool(g.dictamen),
            "observacion_tecnico": g.observacion_tecnico,
            "tipo_glosa_excel": g.tipo_glosa_excel,
            "profesional_medico": g.profesional_medico,
            "dictamen": g.dictamen,
            "workflow_state": g.workflow_state or "BORRADOR",
            "nota_workflow": g.nota_workflow,
        }
        for g in glosas
    ]


@router.patch("/{glosa_id}/estado")
def actualizar_estado(
    glosa_id: int,
    nuevo_estado: str,
    db:    Session        = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosa = repo.actualizar_estado(glosa_id, nuevo_estado, responsable="sistema")
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    logger.info(f"Estado actualizado | glosa_id={glosa_id} | nuevo_estado={nuevo_estado}")
    return {"message": "Estado actualizado", "glosa": glosa}


@router.get("/{glosa_id}")
def obtener_glosa(
    glosa_id: int,
    db:    Session       = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    return {
        "id": glosa.id,
        "eps": glosa.eps,
        "paciente": glosa.paciente,
        "codigo_glosa": glosa.codigo_glosa,
        "valor_objetado": glosa.valor_objetado,
        "valor_aceptado": glosa.valor_aceptado,
        "etapa": glosa.etapa,
        "estado": glosa.estado,
        "dictamen": glosa.dictamen,
        "dias_restantes": glosa.dias_restantes,
        "factura": glosa.factura,
        "numero_radicado": glosa.numero_radicado,
        "consecutivo_dgh": glosa.consecutivo_dgh,
        "gestor_nombre": glosa.gestor_nombre,
        "fecha_radicacion_factura": glosa.fecha_radicacion_factura.isoformat() if glosa.fecha_radicacion_factura else None,
        "fecha_documento_dgh": glosa.fecha_documento_dgh.isoformat() if glosa.fecha_documento_dgh else None,
        "fecha_recepcion": glosa.fecha_recepcion.isoformat() if glosa.fecha_recepcion else None,
        "fecha_entrega": glosa.fecha_entrega.isoformat() if glosa.fecha_entrega else None,
        "fecha_vencimiento": glosa.fecha_vencimiento.isoformat() if glosa.fecha_vencimiento else None,
        "radicado_info": glosa.radicado_info,
        "referencia": glosa.referencia,
        "observacion_tecnico": glosa.observacion_tecnico,
        "tipo_glosa_excel": glosa.tipo_glosa_excel,
        "profesional_medico": glosa.profesional_medico,
        "creado_en": glosa.creado_en.isoformat() if glosa.creado_en else None,
    }


@router.delete("/{glosa_id}")
def eliminar_glosa(
    glosa_id: int,
    motivo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Elimina una glosa del historial. Se mueve a la papelera (restaurable
    por 30 días) antes de borrarla de la tabla principal."""
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    # Mover a papelera (soft-delete con snapshot)
    try:
        from app.api.routers.papelera import mover_a_papelera
        pap_id = mover_a_papelera(db, glosa, eliminado_por=current_user.email, motivo=motivo or "")
    except Exception as e:
        logger.warning(f"No se pudo mover a papelera: {e}")
        pap_id = None
    db.delete(glosa)
    db.commit()
    logger.info(f"Glosa eliminada ID={glosa_id} por {current_user.email} (papelera #{pap_id})")
    return {
        "message": f"Glosa {glosa_id} eliminada",
        "papelera_id": pap_id,
        "restaurable_hasta": "30 días",
    }


class DecisionEPSInput(BaseModel):
    decision_eps: str
    valor_recuperado: float = 0.0
    observacion_eps: Optional[str] = None


class AsignarAuditorInput(BaseModel):
    auditor_email: str


class WorkflowTransicionInput(BaseModel):
    nuevo_estado: str  # BORRADOR | EN_REVISION | APROBADA | RADICADA
    comentario: Optional[str] = None


# Transiciones válidas del workflow (from_estado -> set(to_estado))
_WORKFLOW_TRANSICIONES = {
    "BORRADOR": {"EN_REVISION"},
    "EN_REVISION": {"BORRADOR", "APROBADA"},
    "APROBADA": {"RADICADA", "EN_REVISION"},
    "RADICADA": set(),  # estado final
}


@router.patch("/{glosa_id}/workflow")
def cambiar_workflow(
    glosa_id: int,
    data: WorkflowTransicionInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Cambia el estado del workflow de aprobación.

    Transiciones permitidas:
      BORRADOR -> EN_REVISION       (auditor solicita revisión)
      EN_REVISION -> APROBADA       (coordinador/admin aprueba)
      EN_REVISION -> BORRADOR       (coordinador devuelve para corregir)
      APROBADA -> RADICADA          (una vez radicada ante la EPS)
      APROBADA -> EN_REVISION       (se detecta algo para revisar)

    Permisos:
    - AUDITOR puede mover BORRADOR -> EN_REVISION de sus propias glosas.
    - COORDINADOR y SUPER_ADMIN pueden hacer cualquier transición.
    """
    nuevo = data.nuevo_estado.upper().strip()
    if nuevo not in {"BORRADOR", "EN_REVISION", "APROBADA", "RADICADA"}:
        raise HTTPException(400, f"Estado inválido: {nuevo}")

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    actual = (glosa.workflow_state or "BORRADOR").upper()

    # Si no existe transición desde el estado actual, inicializar como BORRADOR
    if actual not in _WORKFLOW_TRANSICIONES:
        actual = "BORRADOR"

    if nuevo not in _WORKFLOW_TRANSICIONES.get(actual, set()):
        raise HTTPException(
            400,
            f"Transición no permitida: {actual} -> {nuevo}. "
            f"Desde {actual} solo puedes ir a: {sorted(_WORKFLOW_TRANSICIONES.get(actual, set())) or 'ninguno (estado final)'}",
        )

    # Validar permisos por transición
    if current_user.rol == "AUDITOR":
        # Auditor solo puede enviar a revisión sus glosas
        if nuevo != "EN_REVISION" or actual != "BORRADOR":
            raise HTTPException(403, "Como AUDITOR solo puedes enviar glosas propias a revisión")
        if glosa.auditor_email and glosa.auditor_email != current_user.email:
            # Si está asignada a otro auditor, no puede
            raise HTTPException(403, "Esta glosa está asignada a otro auditor")
    elif current_user.rol == "VIEWER":
        raise HTTPException(403, "VIEWER no puede cambiar estados")

    glosa.workflow_state = nuevo
    if data.comentario:
        nota = (glosa.nota_workflow or "")
        nueva_nota = f"[{ahora_utc().strftime('%Y-%m-%d %H:%M')} {current_user.email} {actual}->{nuevo}] {data.comentario}"
        glosa.nota_workflow = (nota + " | " + nueva_nota)[-500:] if nota else nueva_nota[:500]

    db.commit()
    db.refresh(glosa)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="WORKFLOW",
        tabla="historial",
        registro_id=glosa_id,
        campo="workflow_state",
        valor_anterior=actual,
        valor_nuevo=nuevo,
        detalle=data.comentario or f"Transición {actual} -> {nuevo}",
    )
    return {
        "message": "Workflow actualizado",
        "glosa_id": glosa_id,
        "estado_anterior": actual,
        "estado_nuevo": nuevo,
        "nota_workflow": glosa.nota_workflow,
    }


@router.patch("/{glosa_id}/decision-eps")
def registrar_decision_eps(glosa_id: int, data: DecisionEPSInput,
                           db: Session = Depends(get_db),
                           current_user: UsuarioRecord = Depends(get_auditor_o_superior)):
    DECISIONES = {"LEVANTADA", "ACEPTADA", "RATIFICADA", "PENDIENTE"}
    decision = data.decision_eps.upper()
    if decision not in DECISIONES:
        raise HTTPException(400, f"Decisión inválida. Use: {', '.join(DECISIONES)}")
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    glosa.decision_eps = decision
    glosa.fecha_decision_eps = ahora_utc()
    glosa.valor_recuperado = data.valor_recuperado
    if data.observacion_eps:
        glosa.observacion_eps = data.observacion_eps
    if decision in ("LEVANTADA", "ACEPTADA", "RATIFICADA"):
        glosa.estado = decision
    db.commit()

    # Ronda 3 — Aprendizaje por retroalimentación:
    # Si la EPS LEVANTÓ la glosa, promover el argumento exitoso a Plantilla
    # Gold automáticamente (si no existe ya una para esa combinación EPS+código).
    # Si RATIFICÓ, desactivar cualquier Gold previa de esa combinación para
    # que la IA no la sugiera más.
    try:
        from app.services.aprendizaje_feedback import aprender_de_decision_eps
        aprender_de_decision_eps(
            db=db, glosa=glosa, decision=decision, creado_por=current_user.email,
        )
    except Exception as _e:
        # El aprendizaje nunca debe bloquear la decisión; solo logear.
        import logging as _l
        _l.getLogger("motor_glosas").warning(f"Aprendizaje feedback falló: {_e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="DECISION_EPS", tabla="glosas", registro_id=glosa_id,
        campo="decision_eps", valor_nuevo=decision,
        detalle=f"Decisión: {decision} | recuperado: ${data.valor_recuperado:,.0f}")
    return {"message": "Decisión registrada", "glosa_id": glosa_id, "decision_eps": decision}


@router.patch("/{glosa_id}/asignar")
def asignar_auditor(glosa_id: int, data: AsignarAuditorInput,
                    db: Session = Depends(get_db),
                    current_user: UsuarioRecord = Depends(get_coordinador_o_admin)):
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    anterior = glosa.auditor_email
    glosa.auditor_email = data.auditor_email
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="ASIGNAR", tabla="glosas", registro_id=glosa_id,
        campo="auditor_email", valor_anterior=anterior, valor_nuevo=data.auditor_email)
    return {"message": f"Glosa #{glosa_id} asignada a {data.auditor_email}"}


@router.get("/casos-similares/{glosa_id}")
def casos_similares(glosa_id: int, db: Session = Depends(get_db),
                    current_user: UsuarioRecord = Depends(get_usuario_actual)):
    from app.services.rag_service import RAGService
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    casos = RAGService().buscar_casos_similares(
        texto_glosa=glosa.dictamen or "", eps=glosa.eps,
        codigo_glosa=glosa.codigo_glosa or "", db=db, top_k=5, solo_exitosos=False)
    return {"glosa_id": glosa_id, "casos_similares": casos}


@router.get("/{glosa_id}/conceptos")
def listar_conceptos_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista el detalle por concepto de una glosa (cargados desde hojas I/R).

    Devuelve también el encabezado de la glosa para que el front pueda
    pintar de una sola llamada la factura completa (fechas, vencimiento,
    semáforo, y todos los conceptos precargados para analizar).
    """
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    conceptos = (
        db.query(ConceptoGlosaRecord)
        .filter(ConceptoGlosaRecord.glosa_id == glosa_id)
        .order_by(ConceptoGlosaRecord.codigo_glosa, ConceptoGlosaRecord.cups_codigo)
        .all()
    )

    total_conceptos_valor = sum(float(c.valor_objetado or 0) for c in conceptos)

    return {
        "glosa": {
            "id": glosa.id,
            "factura": glosa.factura,
            "consecutivo_dgh": glosa.consecutivo_dgh,
            "eps": glosa.eps,
            "eps_codigo": glosa.eps_codigo,
            "gestor_nombre": glosa.gestor_nombre,
            "tecnico_recepcion": glosa.tecnico_recepcion,
            "tipo_glosa_excel": glosa.tipo_glosa_excel,
            "profesional_medico": glosa.profesional_medico,
            "estado": glosa.estado,
            "valor_objetado": glosa.valor_objetado,
            "valor_factura": glosa.valor_factura,
            "saldo_factura": glosa.saldo_factura,
            "tercero_nit": glosa.tercero_nit,
            "fecha_radicacion_factura": glosa.fecha_radicacion_factura.isoformat() if glosa.fecha_radicacion_factura else None,
            "fecha_documento_dgh": glosa.fecha_documento_dgh.isoformat() if glosa.fecha_documento_dgh else None,
            "fecha_recepcion": glosa.fecha_recepcion.isoformat() if glosa.fecha_recepcion else None,
            "fecha_entrega": glosa.fecha_entrega.isoformat() if glosa.fecha_entrega else None,
            "fecha_vencimiento": glosa.fecha_vencimiento.isoformat() if glosa.fecha_vencimiento else None,
            "fecha_objecion_eps": glosa.fecha_objecion_eps.isoformat() if glosa.fecha_objecion_eps else None,
            "dias_restantes": glosa.dias_restantes,
            "prioridad": glosa.prioridad,
        },
        "conceptos": [
            {
                "id": c.id,
                "oid_dgh": c.oid_dgh,
                "codigo_glosa": c.codigo_glosa,
                "nombre_glosa": c.nombre_glosa,
                "cups_codigo": c.cups_codigo,
                "cups_descripcion": c.cups_descripcion,
                "centro_costo": c.centro_costo,
                "valor_objetado": c.valor_objetado,
                "observacion_eps": c.observacion_eps,
                "dictamen_html": c.dictamen_html,
                "score": c.score,
                "respondido_en": c.respondido_en.isoformat() if c.respondido_en else None,
                "respondido_por": c.respondido_por,
            }
            for c in conceptos
        ],
        "totales": {
            "conceptos": len(conceptos),
            "valor_suma_conceptos": total_conceptos_valor,
            "valor_glosa_cabecera": glosa.valor_objetado or 0,
        },
    }


def _parsear_filas_excel(texto: str) -> list[dict]:
    """
    Parsea el texto pegado de Excel y extrae cada fila como diccionario.
    Formato esperado (8 columnas): ENTIDAD | FACTURA | VALOR | CODIGO |
    CONCEPTO GLOSA | CUPS | SERVICIO | MOTIVO

    Acepta como separador **Tab** (copy/paste directo del Excel) o **"|"**
    (pipe, cuando el usuario exporta desde Office y lo pega aquí). Si una
    fila trae más columnas que las esperadas (porque el MOTIVO contiene el
    mismo separador), las columnas extra se re-unen al final en `motivo`.
    """
    filas: list[dict] = []
    if not texto:
        return filas

    lineas = texto.strip().split('\n')
    CAMPOS = ['eps', 'factura', 'valor', 'codigo', 'descripcion', 'cups', 'servicio', 'motivo']

    for i, linea in enumerate(lineas):
        linea = linea.strip()
        if not linea:
            continue

        # Auto-detectar separador: Tab si existe, sino pipe.
        if '\t' in linea:
            partes = [p.strip() for p in linea.split('\t')]
        elif '|' in linea:
            partes = [p.strip() for p in linea.split('|')]
        else:
            # Sin separador válido → saltar
            continue

        if len(partes) < 4:
            continue

        # Si hay más de 8 columnas, re-unir el excedente al motivo (último campo)
        if len(partes) > len(CAMPOS):
            motivo_extendido = ' '.join(partes[len(CAMPOS) - 1:]).strip()
            partes = partes[:len(CAMPOS) - 1] + [motivo_extendido]

        fila_data: dict = {'fila': i + 1}
        # Campo legacy 'servicio' (col 7) no existe en downstream — se mapea
        # al 'descripcion' adicional cuando hay 8 columnas.
        for idx, campo in enumerate(CAMPOS):
            fila_data[campo] = partes[idx] if idx < len(partes) else ''

        # Si hay columna 'servicio' (col 7) y la 'descripcion' está vacía,
        # promover servicio a descripcion. Si ambas tienen valor, concatenar.
        if fila_data.get('servicio'):
            if fila_data.get('descripcion') and fila_data['descripcion'] != fila_data['servicio']:
                fila_data['descripcion'] = f"{fila_data['descripcion']} — {fila_data['servicio']}"
            else:
                fila_data['descripcion'] = fila_data['servicio']

        if fila_data['codigo'] and len(fila_data['codigo']) >= 2:
            filas.append(fila_data)

    return filas


async def _procesar_fila_en_background(fila_data: dict, servicio_id: str, req_id: str, eps_formulario: str):
    """Procesa una fila individual en segundo plano.

    Si `eps_formulario` viene vacío o "AUTO", se usa la EPS detectada de la
    primera columna de la fila (razón social del Excel)."""
    db = SessionLocal()
    try:
        cfg = get_settings()
        service = GlosaService(
            groq_api_key=cfg.groq_api_key,
            anthropic_api_key=cfg.anthropic_api_key,
            primary_ai=cfg.primary_ai,
            anthropic_model=cfg.anthropic_model,
            groq_model=cfg.groq_model,
        )

        from app.models.schemas import GlosaInput

        contrato_repo = ContratoRepository(db)
        contratos = contrato_repo.como_dict()

        # Resolver EPS: formulario > detectada de la fila
        eps_formulario_limpio = (eps_formulario or "").strip().upper()
        usa_auto = (not eps_formulario_limpio) or eps_formulario_limpio == "AUTO"
        if usa_auto:
            eps_final = _normalizar_eps(fila_data.get('eps', '')) or "SIN EPS"
        else:
            eps_final = eps_formulario

        texto_glosa = f"{fila_data['codigo']} {fila_data['valor']} {fila_data['descripcion']} {fila_data['cups']} {fila_data['motivo']}"

        data = GlosaInput(
            eps=eps_final,
            etapa="RESPUESTA A GLOSA",
            tabla_excel=texto_glosa,
            numero_factura=fila_data.get('factura'),
            numero_radicado=servicio_id,
        )
        
        resultado = await service.analizar(data, "", contratos)

        repo = GlosaRepository(db)
        # Campos adicionales para que el flujo "responder por factura"
        # los pueda listar con contexto (servicio, CUPS, concepto).
        concepto_excel = fila_data.get('motivo') or fila_data.get('descripcion') or ''
        kwargs_extra = {}
        if fila_data.get('descripcion'):
            kwargs_extra['servicio_descripcion'] = fila_data['descripcion'][:400]
        if concepto_excel:
            kwargs_extra['concepto_glosa'] = concepto_excel[:500]
        if fila_data.get('cups'):
            kwargs_extra['cups_servicio'] = fila_data['cups'][:20]
        # Texto glosa original para que el auditor pueda revisar
        kwargs_extra['texto_glosa_original'] = texto_glosa[:2000]
        try:
            repo.crear(
                eps=eps_final,
                paciente="N/A",
                codigo_glosa=resultado.codigo_glosa,
                valor_objetado=float(re.sub(r'[^\d]', '', fila_data.get('valor', '0')) or 0),
                valor_aceptado=0,
                etapa="RESPUESTA A GLOSA",
                estado="RESPONDIDA",
                dictamen=resultado.dictamen,
                dias_restantes=resultado.dias_restantes,
                modelo_ia=resultado.modelo_ia,
                score=resultado.score,
                numero_radicado=servicio_id,
                factura=fila_data.get('factura'),
                **kwargs_extra,
            )
        except TypeError:
            # Fallback si repo.crear no soporta los kwargs extra
            repo.crear(
                eps=eps_final,
                paciente="N/A",
                codigo_glosa=resultado.codigo_glosa,
                valor_objetado=float(re.sub(r'[^\d]', '', fila_data.get('valor', '0')) or 0),
                valor_aceptado=0,
                etapa="RESPUESTA A GLOSA",
                estado="RESPONDIDA",
                dictamen=resultado.dictamen,
                dias_restantes=resultado.dias_restantes,
                modelo_ia=resultado.modelo_ia,
                score=resultado.score,
                numero_radicado=servicio_id,
                factura=fila_data.get('factura'),
            )
        
        logger.info(f"[{req_id}] Fila {fila_data['fila']} procesada: {resultado.codigo_glosa}")
    except Exception as e:
        logger.error(f"[{req_id}] Error procesando fila {fila_data['fila']}: {e}")
    finally:
        db.close()


@router.post("/importar-masiva")
async def importar_glosas_masiva(
    request: ImportacionMasivaRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Importa glosas masivamente desde texto pegado de Excel.

    - Si se envía `eps` = nombre específico, todas las filas usan esa EPS.
    - Si se envía `eps` = null, "" o "AUTO", la EPS se detecta de la primera
      columna de cada fila (razón social) y se normaliza a la clave canónica.

    Recibe: texto_excel (con tabs), fechas opcionales, eps opcional.
    Procesa en segundo plano y retorna el ID del lote para seguimiento.
    """
    req_id = uuid.uuid4().hex[:8]
    eps_formulario = (request.eps or "").strip()
    modo_auto = not eps_formulario or eps_formulario.upper() == "AUTO"
    logger.info(
        f"[{req_id}] Importación masiva iniciada | "
        f"modo={'AUTO' if modo_auto else eps_formulario}"
    )

    filas = _parsear_filas_excel(request.texto_excel)

    if not filas:
        raise HTTPException(status_code=400, detail="No se detectaron filas válidas en el texto")

    # Detectar EPS/facturas únicas para dar feedback inmediato en el response
    eps_detectadas: dict[str, int] = {}
    facturas_detectadas: set[str] = set()
    for f in filas:
        clave = _normalizar_eps(f.get('eps', '')) if modo_auto else eps_formulario
        eps_detectadas[clave or "SIN EPS"] = eps_detectadas.get(clave or "SIN EPS", 0) + 1
        if f.get('factura'):
            facturas_detectadas.add(f['factura'])

    servicio_id = f"BATCH-{req_id}"

    for fila_data in filas:
        background_tasks.add_task(
            _procesar_fila_en_background,
            fila_data,
            servicio_id,
            req_id,
            eps_formulario if not modo_auto else "AUTO",
        )

    logger.info(
        f"[{req_id}] {len(filas)} filas enviadas | batch_id={servicio_id} | "
        f"EPS detectadas: {dict(eps_detectadas)} | facturas: {len(facturas_detectadas)}"
    )

    return {
        "message": f"{len(filas)} glosas procesándose en segundo plano",
        "batch_id": servicio_id,
        "total_filas": len(filas),
        "eps": eps_formulario if not modo_auto else "AUTO",
        "eps_detectadas": eps_detectadas,
        "facturas_detectadas": sorted(facturas_detectadas),
        "estado": "PROCESANDO",
    }


@router.post("/importar-recepcion")
async def importar_recepcion(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sube el Excel que envía el equipo de recepción (GESTOR, FECHAS, EPS,
    FACTURA, CONSECUTIVO DGH, VALOR, VENCE, RADICADO, etc.) y registra cada
    fila como una glosa, detectando automáticamente extemporaneidad y
    ratificaciones. Al terminar envía un correo broadcast a ALERTAS_EMAIL.
    """
    req_id = set_request_id()
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if len(contenido) > 15_000_000:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (>15 MB)")

    from app.services.recepcion_service import RecepcionService
    from app.services.email_service import enviar_resumen_importacion_recepcion
    from app.repositories.audit_repository import AuditRepository

    servicio = RecepcionService(db)
    resumen = servicio.procesar_excel(contenido)

    logger.info(
        f"[{req_id}] Importación recepción por {current_user.email} | "
        f"total={resumen.total} nuevas={resumen.creadas} actualizadas={resumen.actualizadas} "
        f"ratificadas={resumen.ratificadas} extemporaneas={resumen.extemporaneas}"
    )

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="IMPORTAR_RECEPCION",
        tabla="historial",
        detalle=(
            f"total={resumen.total} nuevas={resumen.creadas} "
            f"actualizadas={resumen.actualizadas} ratificadas={resumen.ratificadas} "
            f"extemporaneas={resumen.extemporaneas}"
        ),
    )

    resumen_dict = resumen.to_dict()

    # Notificación broadcast (no bloquea la respuesta si falla)
    # Pasamos db para que la funcion busque usuarios cuyo nombre matchee
    # con los gestores del resumen (ej. EQUIPO ASEGURADORAS) y los incluya
    # en la lista de destinatarios aunque no esten en ALERTAS_EMAIL.
    try:
        enviados = await enviar_resumen_importacion_recepcion(resumen_dict, db=db)
        resumen_dict["correos_enviados"] = enviados
    except Exception as e:
        logger.error(f"[{req_id}] Error enviando correo: {e}")
        resumen_dict["correos_enviados"] = 0
        resumen_dict["email_error"] = str(e)

    return resumen_dict


@router.get("/batch/{batch_id}")
def obtener_estado_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Obtiene el estado de un lote de importación."""
    glosas_batch = db.query(GlosaRecord).filter(
        GlosaRecord.numero_radicado == batch_id
    ).all()
    
    return {
        "batch_id": batch_id,
        "total": len(glosas_batch),
        "glosas": [
            {
                "id": g.id,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": g.valor_objetado,
                "estado": g.estado,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
            }
            for g in glosas_batch
        ]
    }


@router.get("/duplicados")
def listar_duplicados_factura(
    factura: str,
    eps: Optional[str] = None,
    limite: int = 5,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R58 P2: lista glosas previamente registradas con la misma factura.

    Útil para detección de duplicados antes de cargar una glosa nueva.
    Match exacto sobre numero_factura, opcional filtro por EPS.

    Query params:
      factura  número de factura a buscar (case-insensitive, trim)
      eps      EPS opcional para restringir
      limite   máximo de resultados (default 5)

    Respuesta:
      {
        "factura_consultada": "FE-2026-001",
        "total": 1,
        "duplicados": [
          {"id": 42, "eps": "FAMISANAR", "creado_en": "...",
           "estado": "RADICADA", "valor_objetado": 168563.0,
           "auditor_email": "x@hus.com"}
        ]
      }
    """
    from app.repositories.glosa_repository import buscar_duplicados_factura

    duplicados = buscar_duplicados_factura(
        db, numero_factura=factura, eps=eps, limite=limite,
    )
    return {
        "factura_consultada": factura,
        "eps_filtro": eps,
        "total": len(duplicados),
        "duplicados": [
            {
                "id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": float(g.valor_objetado or 0),
                "valor_aceptado": float(g.valor_aceptado or 0),
                "estado": g.estado,
                "auditor_email": g.auditor_email,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
            }
            for g in duplicados
        ],
    }


@router.post("/{glosa_id}/reanalizar")
async def reanalizar_glosa(
    glosa_id: int,
    data: ReanalizarRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
    _cupo_ia: None = Depends(_consumir_cupo_ia),
):
    """R60 P2: re-corre el análisis IA sobre una glosa existente.

    Útil cuando el gestor hizo primero 'auditoria_previa' y ahora quiere
    el dictamen de defensa, o cuando quiere cambiar el tono. NO duplica
    la fila — sobreescribe el dictamen de la glosa actual y guarda
    snapshot en versiones con accion='REANALIZAR'.

    Reusa los datos persistidos: eps, texto_glosa_original, etapa,
    factura, radicado.
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.texto_glosa_original:
        raise HTTPException(
            400,
            "Glosa sin texto_glosa_original — fue creada antes de R59 o por flujo legacy. "
            "No se puede reanalizar.",
        )

    # Construir GlosaInput a partir de los campos persistidos
    from app.models.schemas import GlosaInput
    try:
        glosa_input = GlosaInput(
            eps=glosa.eps or "",
            etapa=glosa.etapa or "RESPUESTA",
            fecha_radicacion=None,  # opcional, ya pasaron los chequeos al crear
            fecha_recepcion=None,
            valor_aceptado=str(int(glosa.valor_aceptado or 0)),
            tabla_excel=glosa.texto_glosa_original,
            numero_factura=glosa.factura,
            numero_radicado=glosa.numero_radicado,
            tono=data.tono or "conciliador",
            modo_respuesta=data.modo_respuesta or "defender",
        )
    except Exception as e:
        raise HTTPException(422, f"No se pudo reconstruir el GlosaInput: {e}")

    # Trazabilidad request-scoped (R56 P1)
    from app.core.logging_utils import glosa_id_var, user_email_var
    user_email_var.set(current_user.email or "")
    glosa_id_var.set(glosa.id)

    cfg = get_settings()
    service = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
    )

    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()
    resultado = await service.analizar(glosa_input, "", contratos)

    # Sobreescribir dictamen + metadata. NO crear nueva fila.
    glosa.dictamen = resultado.dictamen
    glosa.tipo_analisis = resultado.tipo if hasattr(glosa, "tipo_analisis") else None
    glosa.modelo_ia = resultado.modelo_ia
    if hasattr(glosa, "score"):
        glosa.score = resultado.score
    glosa.actualizado_en = ahora_utc()
    db.commit()
    db.refresh(glosa)

    # Snapshot del dictamen como nueva versión
    try:
        from app.api.routers.versiones import guardar_version
        guardar_version(
            db=db, glosa_id=glosa.id, dictamen_html=resultado.dictamen,
            accion="REANALIZAR", autor_email=current_user.email,
        )
    except Exception as _e:
        logger.warning(f"No se pudo guardar version: {_e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="REANALIZAR_GLOSA", tabla="glosas", registro_id=glosa.id,
        detalle=f"tono={data.tono} modo={data.modo_respuesta}",
    )

    return {
        "message": "Glosa reanalizada",
        "glosa_id": glosa.id,
        "modo": data.modo_respuesta,
        "tono": data.tono,
        "modelo_ia": resultado.modelo_ia,
        "dictamen": resultado.dictamen,
        "tipo": resultado.tipo,
    }


@router.post("/{glosa_id}/clonar")
def clonar_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """R65 P1: clona una glosa existente como BORRADOR para acelerar
    captura de glosas similares (mismo paciente, mismo servicio, valor
    distinto, o multi-conceptos sobre la misma factura).

    Comportamiento:
      - Copia campos descriptivos: eps, paciente, codigo_glosa, etapa,
        factura, numero_radicado, texto_glosa_original, cups_servicio,
        servicio_descripcion, concepto_glosa, fecha_recepcion.
      - NO copia: dictamen, modelo_ia, score, valor_aceptado, decisiones
        EPS, fechas de respuesta. La nueva glosa empieza limpia para
        que el gestor decida tono/modo.
      - Estado inicial: BORRADOR (no RADICADA — no se ha generado dictamen).
      - valor_objetado y valor_aceptado quedan en 0 para forzar al gestor
        a digitarlos según el nuevo concepto.

    Audit log registrado con detalle de la glosa origen.
    """
    repo = GlosaRepository(db)
    original = repo.obtener_por_id(glosa_id)
    if not original:
        raise HTTPException(404, "Glosa origen no encontrada")

    nueva = repo.crear(
        eps=original.eps,
        paciente=original.paciente,
        codigo_glosa=original.codigo_glosa,
        valor_objetado=0,
        valor_aceptado=0,
        etapa=original.etapa,
        estado="BORRADOR",
        dictamen=None,
        dias_restantes=original.dias_restantes,
        modelo_ia=None,
        score=0,
        numero_radicado=original.numero_radicado,
        factura=original.factura,
        texto_glosa_original=original.texto_glosa_original,
        codigo_respuesta=None,
        cups_servicio=original.cups_servicio,
        servicio_descripcion=original.servicio_descripcion,
        concepto_glosa=original.concepto_glosa,
        fecha_recepcion=original.fecha_recepcion,
    )

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="CLONAR_GLOSA", tabla="glosas", registro_id=nueva.id,
        detalle=f"Clonada desde glosa #{glosa_id}",
    )

    return {
        "message": "Glosa clonada como BORRADOR",
        "id_origen": glosa_id,
        "id_nueva": nueva.id,
        "estado": "BORRADOR",
    }


@router.get("/{glosa_id}/paquete-evidencia.json")
def descargar_paquete_evidencia(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R85 P2: paquete completo de evidencia para una disputa.

    Bundle JSON listo para entregar al equipo legal o EPS contraparte
    cuando se necesita demostrar:
      - Cuál fue el dictamen exacto (texto + hash)
      - Quién lo firmó y cuándo
      - Qué pasó con esa glosa (timeline completo)
      - Calls IA que la generaron (auditoría regulatoria)

    Estructura:
      {
        "metadata": {generado_en, generado_por, glosa_id},
        "glosa": {...campos descriptivos...},
        "dictamen_actual": {texto, hash, firma, alg, timestamp},
        "timeline": [...eventos cronológicos...],
        "ia_calls": [...calls atribuidos...]
      }
    """
    import json
    from fastapi.responses import Response

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    # 1. Datos descriptivos
    glosa_data = {
        "id": glosa.id,
        "eps": glosa.eps,
        "paciente": glosa.paciente,
        "codigo_glosa": glosa.codigo_glosa,
        "factura": glosa.factura,
        "numero_radicado": glosa.numero_radicado,
        "valor_objetado": float(glosa.valor_objetado or 0),
        "valor_aceptado": float(glosa.valor_aceptado or 0),
        "estado": glosa.estado,
        "modelo_ia": glosa.modelo_ia,
        "creado_en": glosa.creado_en.isoformat() if glosa.creado_en else None,
    }

    # 2. Firma del dictamen actual (si existe)
    firma_info = None
    if glosa.dictamen:
        from app.services.firma_digital import firmar_dictamen
        firma_info = firmar_dictamen(
            texto_dictamen=glosa.dictamen,
            firmante_email=current_user.email,
            glosa_id=glosa.id,
        )
        firma_info["texto_dictamen_html"] = glosa.dictamen

    # 3. Timeline reusable: invocamos la función directamente
    from app.models.db import (
        AICallRecord, AuditLogRecord, ComentarioGlosaRecord,
        DictamenVersionRecord,
    )
    eventos = []
    for v in db.query(DictamenVersionRecord).filter_by(glosa_id=glosa_id).all():
        eventos.append({
            "tipo": f"VERSION_{v.accion or 'CREAR'}",
            "actor": v.autor_email,
            "timestamp": v.creado_en.isoformat() if v.creado_en else None,
        })
    for a in (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla.in_(("glosas", "historial")))
        .filter(AuditLogRecord.registro_id == glosa_id)
        .all()
    ):
        eventos.append({
            "tipo": f"AUDIT_{a.accion or 'ACCION'}",
            "actor": a.usuario_email,
            "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            "detalle": (a.detalle or "")[:200],
        })
    for c in db.query(ComentarioGlosaRecord).filter_by(glosa_id=glosa_id).all():
        eventos.append({
            "tipo": "COMENTARIO",
            "actor": c.autor_email,
            "timestamp": c.creado_en.isoformat() if c.creado_en else None,
            "texto": (c.texto or "")[:200],
        })
    eventos.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    # 4. Calls IA atribuidos
    ia_calls = []
    for c in db.query(AICallRecord).filter_by(glosa_id=glosa_id).all():
        ia_calls.append({
            "modelo": c.modelo,
            "tokens_total": (c.input_tokens or 0)
                            + (c.cache_creation_input_tokens or 0)
                            + (c.cache_read_input_tokens or 0)
                            + (c.output_tokens or 0),
            "cost_usd": c.cost_usd,
            "latency_ms": c.latency_ms,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        })

    payload = {
        "metadata": {
            "generado_en": ahora_utc().isoformat(),
            "generado_por": current_user.email,
            "glosa_id": glosa_id,
            "version_paquete": "R85 P2",
        },
        "glosa": glosa_data,
        "dictamen_actual": firma_info,
        "timeline": eventos,
        "ia_calls": ia_calls,
    }
    fname = f"paquete-evidencia-glosa-{glosa.id}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{glosa_id}/firma-dictamen")
def obtener_firma_dictamen(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R84 P1: genera la firma digital del dictamen actual.

    Útil para evidenciar integridad antes de radicar a la EPS:
    si la EPS modifica el documento, el hash cambia y la firma
    deja de validar.

    Usa RSA asimétrica si FIRMA_DIGITAL_PRIVATE_KEY está configurada
    (R50 P8); fallback a HMAC con SECRET_KEY.

    Devuelve:
      {
        "glosa_id": 42,
        "hash": "sha256-hex",
        "firma": "base64",
        "timestamp": "ISO",
        "firmante": "auditor@hus.com",
        "alg": "RSA-PSS-SHA256-v1" | "HMAC-SHA256",
        "verificable": "Endpoint /firma/verificar (futuro)"
      }
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "La glosa no tiene dictamen generado")

    from app.services.firma_digital import firmar_dictamen
    info = firmar_dictamen(
        texto_dictamen=glosa.dictamen,
        firmante_email=current_user.email,
        glosa_id=glosa.id,
    )
    return {
        "glosa_id": glosa.id,
        **info,
    }


@router.get("/{glosa_id}/dictamen.txt")
def descargar_dictamen_txt(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R81 P1: descarga el dictamen como texto plano sin formato.

    Más portable que .md para sistemas que no entienden Markdown
    (integraciones legacy, copia/pega a correo electrónico, etc.).

    Strip total de HTML + entidades + normalización de whitespace.
    """
    import re

    from fastapi.responses import Response

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "La glosa no tiene dictamen generado")

    html = glosa.dictamen
    # Reemplazos para preservar estructura visual
    txt = re.sub(r"</p>", "\n\n", html, flags=re.IGNORECASE)
    txt = re.sub(r"</h[1-6]>", "\n\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"</li>", "\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"</tr>", "\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"</td>", " | ", txt, flags=re.IGNORECASE)
    # Quitar todos los tags
    txt = re.sub(r"<[^>]+>", "", txt)
    # Decode entidades
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&#39;", "'"))
    # Normalizar líneas en blanco
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r" +\n", "\n", txt).strip()

    cabecera = (
        f"DICTAMEN GLOSA #{glosa.id}\n"
        f"{'=' * 50}\n"
        f"EPS:              {glosa.eps or '—'}\n"
        f"Código glosa:     {glosa.codigo_glosa or '—'}\n"
        f"Valor objetado:   ${(glosa.valor_objetado or 0):,.0f}\n"
        f"Estado:           {glosa.estado or '—'}\n"
        f"Factura:          {glosa.factura or '—'}\n"
        f"{'=' * 50}\n\n"
    )
    payload = (cabecera + txt).encode("utf-8")
    fname = f"dictamen-glosa-{glosa.id}.txt"
    return Response(
        content=payload,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/stats/por-codigo-respuesta")
def stats_por_codigo_respuesta(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R68 P1: agregaciones por código de respuesta (RE97xx, RE98xx, RE99xx).

    Útil para reportes mensuales: "este mes el HUS aceptó 23% (RE9702),
    aceptó parcial 15% (RE9801) y defendió 62% (RE9901)."

    Ventana configurable. Devuelve:
      {
        "ventana_dias": 30,
        "total": 145,
        "por_codigo": [
          {"codigo": "RE9901", "descripcion": "Glosa no aceptada",
           "count": 90, "valor_total": 12_345_678, "porcentaje": 62.1}
        ]
      }
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))

    rows = (
        db.query(
            GlosaRecord.codigo_respuesta,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .group_by(GlosaRecord.codigo_respuesta)
        .all()
    )

    descripciones = {
        "RE9901": "Glosa no aceptada (defensa)",
        "RE9701": "Glosa aceptada total (texto fijo)",
        "RE9702": "Glosa aceptada al 100%",
        "RE9801": "Glosa aceptada y subsanada parcialmente",
        "RE9502": "Glosa extemporánea",
        "": "Sin código de respuesta",
        None: "Sin código de respuesta",
    }

    total = sum(r[1] for r in rows) or 0
    por_codigo = []
    for codigo, count, valor in rows:
        porcentaje = (count / total * 100) if total else 0
        por_codigo.append({
            "codigo": codigo or "—",
            "descripcion": descripciones.get(codigo, "Otro"),
            "count": count,
            "valor_total": float(valor or 0),
            "porcentaje": round(porcentaje, 1),
        })
    por_codigo.sort(key=lambda x: x["count"], reverse=True)

    return {
        "ventana_dias": dias,
        "total": total,
        "por_codigo": por_codigo,
    }


@router.get("/stats/por-eps")
def stats_por_eps(
    dias: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R68 P2: distribución de glosas por EPS con tasa de recuperación.

    Útil para identificar:
      - EPS más conflictivas (más glosas formuladas)
      - EPS que más recursos absorben (mayor valor objetado)
      - EPS donde tenemos peor tasa de éxito (rev pertinencia)
      - EPS donde defendemos bien (replicar argumentos)

    Devuelve por EPS:
      count, valor_objetado, valor_aceptado, valor_recuperado,
      tasa_exito_pct (= valor_recuperado / valor_objetado * 100)

    Ordenado DESC por valor_objetado.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))

    rows = (
        db.query(
            GlosaRecord.eps,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
            _f.sum(GlosaRecord.valor_aceptado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.eps.isnot(None))
        .group_by(GlosaRecord.eps)
        .all()
    )

    items = []
    for eps, count, v_obj, v_ac in rows:
        v_obj = float(v_obj or 0)
        v_ac = float(v_ac or 0)
        v_rec = v_obj - v_ac
        tasa = (v_rec / v_obj * 100) if v_obj > 0 else 0
        items.append({
            "eps": eps,
            "count": count,
            "valor_objetado": v_obj,
            "valor_aceptado": v_ac,
            "valor_recuperado": v_rec,
            "tasa_exito_pct": round(tasa, 1),
        })
    items.sort(key=lambda x: x["valor_objetado"], reverse=True)

    return {
        "ventana_dias": dias,
        "total_eps": len(items),
        "items": items,
    }


@router.get("/{glosa_id}/dictamen.md")
def descargar_dictamen_markdown(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R69 P2: descarga el dictamen de una glosa como archivo Markdown.

    HTML → Markdown legible para:
      - Compartir con equipo legal externo (no abre HTML stylado)
      - Integración con sistemas de gestión documental que solo
        aceptan texto plano
      - Diff manual entre versiones en herramientas estándar (VSCode,
        BBEdit, etc.)

    No requiere librería externa — conversión simple por regex que
    cubre los tags reales del dictamen (h3, p, b, ul, li, tabla
    códigos al inicio).
    """
    import re
    from fastapi.responses import Response

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "Esta glosa aún no tiene dictamen generado")

    html = glosa.dictamen
    # 1) headers
    md = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1\n", html, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1\n", md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1\n", md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r"<h4[^>]*>(.*?)</h4>", r"#### \1\n", md, flags=re.IGNORECASE | re.DOTALL)
    # 2) negritas
    md = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r"<(i|em)[^>]*>(.*?)</\1>", r"*\2*", md, flags=re.IGNORECASE | re.DOTALL)
    # 3) listas
    md = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", md, flags=re.IGNORECASE | re.DOTALL)
    # 4) saltos
    md = re.sub(r"<br\s*/?>", "\n", md, flags=re.IGNORECASE)
    md = re.sub(r"</p>", "\n\n", md, flags=re.IGNORECASE)
    md = re.sub(r"</div>", "\n", md, flags=re.IGNORECASE)
    md = re.sub(r"</tr>", "\n", md, flags=re.IGNORECASE)
    md = re.sub(r"</td>", " | ", md, flags=re.IGNORECASE)
    # 5) tags restantes
    md = re.sub(r"<[^>]+>", "", md)
    # 6) entidades comunes
    md = (md.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'"))
    # 7) normalizar líneas en blanco múltiples
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"[ \t]+", " ", md)
    md = re.sub(r" +\n", "\n", md)
    md = md.strip()

    # Header informativo del archivo
    cabecera = (
        f"# Dictamen Glosa #{glosa.id}\n\n"
        f"- **EPS:** {glosa.eps or '—'}\n"
        f"- **Código glosa:** {glosa.codigo_glosa or '—'}\n"
        f"- **Valor objetado:** ${(glosa.valor_objetado or 0):,.0f}\n"
        f"- **Estado:** {glosa.estado or '—'}\n"
        f"- **Factura:** {glosa.factura or '—'}\n"
        f"- **Modelo IA:** {glosa.modelo_ia or '—'}\n\n"
        f"---\n\n"
    )
    payload = (cabecera + md).encode("utf-8")

    fname = f"dictamen-glosa-{glosa.id}.md"
    return Response(
        content=payload,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/bulk-actualizar-estado")
def bulk_actualizar_estado(
    data: BulkActualizarEstadoRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """R71 P1: actualiza el estado de N glosas en una sola transacción.

    Útil cuando llega Excel de respuesta de la EPS con decisiones para
    múltiples glosas. En vez de llamar PATCH /glosas/{id}/estado N veces,
    una sola llamada con la lista.

    Estados válidos típicos:
      LEVANTADA, RATIFICADA, ACEPTADA, ACEPTADA_PARCIAL, RESUELTA,
      CONCILIADA, EN_REVISION

    Devuelve:
      {
        "actualizadas": N,
        "no_encontradas": [ids_no_encontrados],
        "estado": "LEVANTADA"
      }

    Audit log: 1 entry por glosa con accion=BULK_UPDATE_ESTADO.
    """
    estados_validos = {
        "RADICADA", "BORRADOR", "EN_REVISION", "RESPONDIDA",
        "LEVANTADA", "RATIFICADA", "ACEPTADA", "PARCIALMENTE_ACEPTADA",
        "RESUELTA", "CONCILIADA", "ARCHIVADA",
    }
    nuevo_estado_norm = data.nuevo_estado.strip().upper()
    if nuevo_estado_norm not in estados_validos:
        raise HTTPException(
            422,
            f"Estado '{nuevo_estado_norm}' inválido. Use uno de: "
            f"{', '.join(sorted(estados_validos))}",
        )

    repo = GlosaRepository(db)
    actualizadas = 0
    no_encontradas = []
    audit_repo = AuditRepository(db)

    for gid in data.glosa_ids:
        g = repo.obtener_por_id(gid)
        if not g:
            no_encontradas.append(gid)
            continue
        estado_anterior = g.estado
        g.estado = nuevo_estado_norm
        actualizadas += 1
        audit_repo.registrar(
            usuario_email=current_user.email, usuario_rol=current_user.rol,
            accion="BULK_UPDATE_ESTADO", tabla="glosas", registro_id=gid,
            campo="estado", valor_anterior=estado_anterior,
            valor_nuevo=nuevo_estado_norm,
            detalle=(data.nota or "Bulk update de estado")[:300],
        )
    db.commit()

    return {
        "actualizadas": actualizadas,
        "no_encontradas": no_encontradas,
        "estado": nuevo_estado_norm,
    }


@router.post("/bulk-mover-papelera")
def bulk_mover_papelera(
    data: BulkMoverPapeleraRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R71 P2: mueve N glosas a la papelera (soft-delete) de un golpe.

    Útil cuando se importó un Excel duplicado por error y hay 50
    glosas para depurar. Auth restringido a coordinador/admin (no
    auditor) por riesgo.

    Soporta dry_run=true para PREVIEW: lista qué glosas se moverían
    sin tocar la BD. UI puede mostrar al usuario qué borrará y pedir
    confirm.

    Cada glosa movida queda en glosas_eliminadas (R52, papelera con
    TTL 30 días) y se borra de historial. Si una glosa no existe,
    se reporta en no_encontradas pero el batch continúa.
    """
    repo = GlosaRepository(db)
    movidas = 0
    no_encontradas = []
    fallidas = []

    for gid in data.glosa_ids:
        g = repo.obtener_por_id(gid)
        if not g:
            no_encontradas.append(gid)
            continue
        if data.dry_run:
            movidas += 1
            continue
        try:
            from app.api.routers.papelera import mover_a_papelera
            mover_a_papelera(
                db, g,
                eliminado_por=current_user.email,
                motivo=(data.motivo or "Bulk delete")[:300],
            )
            db.delete(g)
            movidas += 1
        except Exception as e:
            fallidas.append({"id": gid, "error": str(e)[:200]})

    if not data.dry_run:
        db.commit()
        logger.info(
            f"[BULK-PAPELERA] {movidas} glosas movidas a papelera por "
            f"{current_user.email} | {len(fallidas)} fallidas"
        )

    return {
        "dry_run": data.dry_run,
        "movidas_a_papelera": movidas,
        "no_encontradas": no_encontradas,
        "fallidas": fallidas,
    }


@router.get("/{glosa_id}/acciones-disponibles")
def acciones_disponibles_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R78 P1: lista las acciones que el gestor puede tomar sobre esta
    glosa según su estado actual y contexto.

    Combina:
      - Transiciones válidas del workflow (state machine)
      - Acciones operativas disponibles
      - Sugerencia principal heurística

    Útil para que la UI muestre solo las acciones aplicables.
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    from app.services.workflow_service import WorkflowService
    transiciones = WorkflowService.obtener_transiciones_validas(
        glosa.estado or "RADICADA",
    )

    tiene_dictamen = bool(glosa.dictamen and len(glosa.dictamen) > 50)
    tiene_texto_original = bool(glosa.texto_glosa_original)
    tiene_factura = bool(glosa.factura)

    return {
        "glosa_id": glosa.id,
        "estado_actual": glosa.estado,
        "transiciones_workflow": [
            {"hacia": t.hacia, "accion": t.accion, "requiere_nota": t.requiere_nota}
            for t in transiciones
        ],
        "acciones_operativas": {
            "puede_descargar_pdf": tiene_dictamen,
            "puede_descargar_md": tiene_dictamen,
            "puede_refinar": tiene_dictamen,
            "puede_reanalizar": tiene_texto_original,
            "puede_clonar": True,
            "puede_validar_rapido": tiene_dictamen,
            "puede_ver_timeline": True,
            "puede_ver_metricas_ia": True,
            "puede_buscar_duplicados": tiene_factura,
            "puede_ver_versiones": tiene_dictamen,
        },
        "sugerencia_principal": _sugerir_accion_principal(glosa),
    }


def _sugerir_accion_principal(glosa) -> Optional[str]:
    """Heurística: sugiere la próxima acción más útil según contexto."""
    estado = (glosa.estado or "").upper()
    tiene_dict = bool(glosa.dictamen and len(glosa.dictamen) > 50)
    dias = glosa.dias_restantes or 0
    if not tiene_dict:
        if (glosa.texto_glosa_original or ""):
            return "Generar dictamen con IA"
        return "Pegar texto de la glosa para empezar"
    if estado == "BORRADOR":
        return "Marcar como respondida cuando esté lista"
    if estado == "RADICADA" and dias > 0 and dias <= 2:
        return "URGENTE: vence en 2 días o menos — radicar respuesta YA"
    if estado == "RESPONDIDA":
        return "Esperar decisión EPS · monitor de plazos activo"
    if estado == "RATIFICADA":
        return "Considerar conciliación o escalar a SuperSalud"
    if estado == "LEVANTADA":
        return "Glosa exitosa · considerar guardar argumento como Plantilla Gold"
    return None


@router.get("/{glosa_id}/validar-rapido")
def validar_rapido_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R70 P1: validación instantánea del dictamen sin IA (solo checks
    locales programáticos del validador_dictamen).

    Diferencia con POST /{id}/validar (validar_pre_radicacion):
      - validar_pre_radicacion       → llama IA, ~5 seg, ~$0.05 USD
      - validar-rapido (este)        → solo checks locales, <50 ms, $0

    Útil para feedback rápido al gestor mientras edita o como
    pre-check antes del validador completo.

    Aplica los 11 checks del validador_dictamen.evaluar_dictamen():
      apertura, cups_real, sin_cifras_inventadas, normas_citadas,
      enumeracion, invitacion_conciliacion, extension,
      codigo_respuesta_coherente, contrato_mencionado, placeholders,
      cita_literal_normativa, anti_rebatimiento.

    Devuelve score 0-100, total checks, aprobados, lista detallada.
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "La glosa aún no tiene dictamen generado")

    from app.services.validador_dictamen import evaluar_dictamen
    resultado = evaluar_dictamen(
        glosa.dictamen or "",
        codigo_glosa=glosa.codigo_glosa or "",
        cups_esperado=glosa.cups_servicio,
        valor_original=str(int(glosa.valor_objetado or 0)),
        codigo_respuesta=glosa.codigo_respuesta,
        eps=glosa.eps or "",
    )
    return {
        "glosa_id": glosa.id,
        **resultado,
    }


@router.get("/stats/por-gestor")
def stats_por_gestor(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R73 P1: productividad por gestor en la ventana indicada.

    Solo coordinador/admin (datos sensibles de equipo).

    Devuelve por gestor:
      count_glosas      glosas asignadas / creadas en la ventana
      valor_objetado    suma total
      valor_aceptado    suma aceptada
      valor_recuperado  v_obj - v_ac
      tasa_exito_pct    % defendido
      tiempo_promedio_dias_a_decision  (si hay fecha_decision_eps)

    Ordenado DESC por count_glosas.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))

    # Agregar por auditor_email (gestor responsable)
    rows = (
        db.query(
            GlosaRecord.auditor_email,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
            _f.sum(GlosaRecord.valor_aceptado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.auditor_email.isnot(None))
        .group_by(GlosaRecord.auditor_email)
        .all()
    )

    items = []
    for email, count, v_obj, v_ac in rows:
        v_obj = float(v_obj or 0)
        v_ac = float(v_ac or 0)
        v_rec = v_obj - v_ac
        tasa = (v_rec / v_obj * 100) if v_obj > 0 else 0
        items.append({
            "auditor_email": email,
            "count_glosas": int(count),
            "valor_objetado": v_obj,
            "valor_aceptado": v_ac,
            "valor_recuperado": v_rec,
            "tasa_exito_pct": round(tasa, 1),
        })
    items.sort(key=lambda x: x["count_glosas"], reverse=True)

    return {
        "ventana_dias": dias,
        "total_gestores_activos": len(items),
        "items": items,
    }


@router.get("/stats/comparativa-eps")
def stats_comparativa_eps(
    min_glosas: int = Query(5, ge=1, le=100,
                            description="Mínimo de glosas para incluir EPS"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R90 P2: ranking comparativo de EPS por desempeño.

    Desde la perspectiva del HUS (IPS):
      - LEVANTADA = HUS defendió con éxito (HUS recupera el valor)
      - ACEPTADA = HUS aceptó la glosa (EPS no paga)
      - RATIFICADA = EPS sostuvo la glosa
      - CONCILIADA = acuerdo intermedio

    "Mejor EPS" desde HUS = mayor tasa de levantamiento (HUS le gana
    más casos a esa EPS), porque indica que la EPS objeta cosas que
    no debería y HUS las defiende bien.

    Devuelve por EPS (filtradas por min_glosas):
      - total_glosas
      - levantadas / aceptadas / ratificadas / pendientes
      - tasa_levantamiento_pct
      - valor_objetado_total
      - valor_recuperado_total
      - tiempo_promedio_decision_dias
    Ordenado DESC por tasa_levantamiento_pct.
    """
    todas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in todas:
        eps = (g.eps or "SIN_EPS").strip()
        if eps not in por_eps:
            por_eps[eps] = {
                "total": 0, "levantadas": 0, "aceptadas": 0,
                "ratificadas": 0, "pendientes": 0,
                "valor_objetado": 0.0, "valor_recuperado": 0.0,
                "tiempos": [],
            }
        b = por_eps[eps]
        b["total"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)
        b["valor_recuperado"] += float(g.valor_recuperado or 0)

        estado = (g.estado or "").upper()
        if estado == "LEVANTADA":
            b["levantadas"] += 1
        elif estado == "ACEPTADA":
            b["aceptadas"] += 1
        elif estado == "RATIFICADA":
            b["ratificadas"] += 1
        else:
            b["pendientes"] += 1

        if g.fecha_decision_eps and g.creado_en:
            delta = (g.fecha_decision_eps - g.creado_en).total_seconds() / 86400
            b["tiempos"].append(delta)

    items = []
    for eps, b in por_eps.items():
        if b["total"] < min_glosas:
            continue
        decididas = b["levantadas"] + b["aceptadas"] + b["ratificadas"]
        tasa = (
            round(100 * b["levantadas"] / decididas, 2)
            if decididas else 0.0
        )
        tiempo_prom = (
            round(sum(b["tiempos"]) / len(b["tiempos"]), 2)
            if b["tiempos"] else 0.0
        )
        items.append({
            "eps": eps,
            "total_glosas": b["total"],
            "levantadas": b["levantadas"],
            "aceptadas": b["aceptadas"],
            "ratificadas": b["ratificadas"],
            "pendientes": b["pendientes"],
            "tasa_levantamiento_pct": tasa,
            "valor_objetado_total": int(b["valor_objetado"]),
            "valor_recuperado_total": int(b["valor_recuperado"]),
            "tiempo_promedio_decision_dias": tiempo_prom,
        })

    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps_evaluadas": len(items),
        "items": items,
    }


@router.get("/stats/cumplimiento-sla")
def stats_cumplimiento_sla(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R90 P1: cumplimiento de SLA agregado para dashboard ejecutivo.

    Resolución 2284/2023 fija términos máximos para cada etapa del
    ciclo glosa→respuesta→ratificación→conciliación. Este endpoint
    agrega el estado actual de la cartera de glosas frente a esos
    plazos.

    Devuelve:
      {
        "total": int,
        "vencidas": int,           # dias_restantes < 0 y no cerradas
        "criticas": int,           # 0 <= dias_restantes <= 3
        "en_tiempo": int,          # dias_restantes > 3
        "cerradas": int,           # estado in cerrados
        "tasa_cumplimiento_pct": float,  # cerradas a_tiempo / cerradas
        "tiempo_promedio_resolucion_dias": float,
        "valor_en_riesgo": int,    # suma valor_objetado de vencidas+críticas
      }
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()
    total = len(todas)

    vencidas = 0
    criticas = 0
    en_tiempo = 0
    cerradas = 0
    cerradas_a_tiempo = 0
    tiempos_resolucion: list[float] = []
    valor_en_riesgo = 0.0

    for g in todas:
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            cerradas += 1
            if g.fecha_decision_eps and g.fecha_vencimiento:
                if g.fecha_decision_eps <= g.fecha_vencimiento:
                    cerradas_a_tiempo += 1
            if g.fecha_decision_eps and g.creado_en:
                delta = (g.fecha_decision_eps - g.creado_en).total_seconds() / 86400
                tiempos_resolucion.append(delta)
            continue

        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            vencidas += 1
            valor_en_riesgo += float(g.valor_objetado or 0)
        elif dr <= 3:
            criticas += 1
            valor_en_riesgo += float(g.valor_objetado or 0)
        else:
            en_tiempo += 1

    tasa = (
        round(100 * cerradas_a_tiempo / cerradas, 2)
        if cerradas else 0.0
    )
    tiempo_promedio = (
        round(sum(tiempos_resolucion) / len(tiempos_resolucion), 2)
        if tiempos_resolucion else 0.0
    )

    return {
        "total": total,
        "vencidas": vencidas,
        "criticas": criticas,
        "en_tiempo": en_tiempo,
        "cerradas": cerradas,
        "cerradas_a_tiempo": cerradas_a_tiempo,
        "tasa_cumplimiento_pct": tasa,
        "tiempo_promedio_resolucion_dias": tiempo_promedio,
        "valor_en_riesgo": int(valor_en_riesgo),
    }


@router.get("/stats/distribucion-valores")
def stats_distribucion_valores(
    dias: int = Query(180, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R89 P2: histograma del valor_objetado de las glosas.

    Útil para entender la distribución económica de las glosas
    (¿son mayoría < 100k pero pocas > 10M concentran el valor?).

    Buckets en COP, pensados para el rango típico HUS:
      - <100k, 100k-500k, 500k-1M, 1M-5M, 5M-10M, 10M-50M, 50M+

    Devuelve:
      {
        "ventana_dias": 180,
        "total_glosas": int,
        "valor_total": int,           # suma COP
        "valor_promedio": float,
        "valor_mediano": float,
        "buckets": [
          {"rango": "<100k", "min": 0, "max": 100000,
           "count": int, "valor": int, "pct_count": float, "pct_valor": float},
          ...
        ]
      }
    """
    from datetime import timedelta

    BUCKETS = [
        ("<100k",    0,         100_000),
        ("100k-500k", 100_000,   500_000),
        ("500k-1M",  500_000,   1_000_000),
        ("1M-5M",    1_000_000, 5_000_000),
        ("5M-10M",   5_000_000, 10_000_000),
        ("10M-50M",  10_000_000, 50_000_000),
        ("50M+",     50_000_000, None),
    ]

    corte = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(GlosaRecord.valor_objetado)
        .filter(GlosaRecord.creado_en >= corte)
        .filter(GlosaRecord.valor_objetado.isnot(None))
        .all()
    )

    valores = [float(v[0] or 0) for v in rows]
    total_glosas = len(valores)
    valor_total = sum(valores)

    # Mediana
    if valores:
        ordenado = sorted(valores)
        mid = total_glosas // 2
        if total_glosas % 2 == 0:
            valor_mediano = (ordenado[mid - 1] + ordenado[mid]) / 2
        else:
            valor_mediano = ordenado[mid]
    else:
        valor_mediano = 0.0

    # Distribución por bucket
    buckets_out = []
    for nombre, lo, hi in BUCKETS:
        en_bucket = [
            v for v in valores
            if v >= lo and (hi is None or v < hi)
        ]
        n = len(en_bucket)
        v_sum = sum(en_bucket)
        buckets_out.append({
            "rango": nombre,
            "min": lo,
            "max": hi,
            "count": n,
            "valor": int(v_sum),
            "pct_count": round(100 * n / total_glosas, 2) if total_glosas else 0.0,
            "pct_valor": round(100 * v_sum / valor_total, 2) if valor_total else 0.0,
        })

    return {
        "ventana_dias": int(dias),
        "total_glosas": total_glosas,
        "valor_total": int(valor_total),
        "valor_promedio": round(valor_total / total_glosas, 2) if total_glosas else 0.0,
        "valor_mediano": round(valor_mediano, 2),
        "buckets": buckets_out,
    }


@router.get("/stats/heatmap-actividad")
def stats_heatmap_actividad(
    dias: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R89 P1: heatmap de glosas creadas por día-de-semana × hora-del-día.

    Útil para:
      - Detectar picos de carga (¿se concentran las cargas masivas
        de glosas los lunes a las 9am? ¿hay actividad nocturna sospechosa?)
      - Planeación de capacidad de auditores
      - Identificar anomalías (carga repentina fuera de horario)

    Devuelve matriz 7×24:
      {
        "ventana_dias": 90,
        "total": 1234,
        "matriz": [[lunes_0h, lunes_1h, ...], [martes_0h, ...], ...],
        "dias_semana": ["Lunes", "Martes", ...],
        "horas": [0..23]
      }

    Día-de-semana siguiendo ISO 8601 (Lunes=0, Domingo=6).
    Agregación se hace en Python para portabilidad SQLite/PostgreSQL.
    """
    from datetime import timedelta

    corte = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(GlosaRecord.creado_en)
        .filter(GlosaRecord.creado_en >= corte)
        .all()
    )

    matriz = [[0 for _ in range(24)] for _ in range(7)]
    total = 0
    for (creado,) in rows:
        if creado is None:
            continue
        dow = creado.weekday()  # Lunes=0, Domingo=6
        hr = creado.hour
        matriz[dow][hr] += 1
        total += 1

    return {
        "ventana_dias": int(dias),
        "total": total,
        "matriz": matriz,
        "dias_semana": [
            "Lunes", "Martes", "Miércoles", "Jueves",
            "Viernes", "Sábado", "Domingo",
        ],
        "horas": list(range(24)),
    }


@router.get("/stats/tendencia-diaria")
def stats_tendencia_diaria(
    dias: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R72 P1: serie temporal diaria de glosas creadas.

    Útil para gráficos de línea en dashboard:
      - Detectar spikes (días con muchas glosas → carga de trabajo)
      - Tendencia semanal (lunes vs viernes)
      - Comparación mes-a-mes

    GET /glosas/stats/tendencia-diaria?dias=30

    Devuelve serie completa (rellenando días con 0 glosas):
      {
        "ventana_dias": 30,
        "serie": [
          {"fecha": "2026-04-01", "count": 5, "valor_objetado": 250000},
          {"fecha": "2026-04-02", "count": 0, "valor_objetado": 0},
          ...
        ]
      }
    """
    from datetime import date, timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc

    desde = (ahora_utc() - timedelta(days=int(dias))).date()

    # Agregar por fecha (truncando a date)
    rows = (
        db.query(
            _f.date(GlosaRecord.creado_en).label("fecha"),
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .group_by(_f.date(GlosaRecord.creado_en))
        .all()
    )

    # Indexar por fecha
    por_fecha = {}
    for fecha, count, valor in rows:
        # SQLAlchemy puede devolver date o str según el motor
        if isinstance(fecha, str):
            from datetime import datetime
            try:
                fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
            except Exception:
                continue
        por_fecha[fecha.isoformat()] = {
            "count": int(count or 0),
            "valor_objetado": float(valor or 0),
        }

    # Rellenar serie completa
    serie = []
    hoy = ahora_utc().date()
    cursor = desde
    while cursor <= hoy:
        clave = cursor.isoformat()
        info = por_fecha.get(clave, {"count": 0, "valor_objetado": 0.0})
        serie.append({
            "fecha": clave,
            "count": info["count"],
            "valor_objetado": info["valor_objetado"],
        })
        cursor += timedelta(days=1)

    return {
        "ventana_dias": dias,
        "total_glosas": sum(s["count"] for s in serie),
        "valor_total": sum(s["valor_objetado"] for s in serie),
        "serie": serie,
    }


@router.get("/stats/por-tipo")
def stats_por_tipo_glosa(
    dias: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R68 P3: distribución por tipo de glosa (prefijo Res. 2284/2023).

    Resolución 2284 de 2023 (Manual Único de Glosas) clasifica con
    prefijos:
      TA  Tarifas
      SO  Soportes
      AU  Autorización
      CO  Cobertura
      CL  Pertinencia clínica
      PE  Pertinencia
      FA  Facturación
      SE  Servicios
      IN  Insumos
      ME  Medicamentos
      EX  Extemporánea / proceso

    Útil para identificar dónde tenemos brechas:
      - Mucho SO → deficiente entrega de soportes operativos
      - Mucho TA → desfase con tarifas pactadas
      - Mucho AU → fallas en autorización previa
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))

    descripciones = {
        "TA": "Tarifas",
        "SO": "Soportes",
        "AU": "Autorización",
        "CO": "Cobertura",
        "CL": "Pertinencia clínica",
        "PE": "Pertinencia",
        "FA": "Facturación",
        "SE": "Servicios",
        "IN": "Insumos",
        "ME": "Medicamentos",
        "EX": "Extemporánea / proceso",
    }

    rows = (
        db.query(
            GlosaRecord.codigo_glosa,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .group_by(GlosaRecord.codigo_glosa)
        .all()
    )

    # Agrupar por prefijo
    por_prefijo = {}
    for codigo, count, valor in rows:
        prefijo = (codigo or "??")[:2].upper()
        d = por_prefijo.setdefault(
            prefijo,
            {"count": 0, "valor_objetado": 0.0, "codigos_unicos": set()},
        )
        d["count"] += count
        d["valor_objetado"] += float(valor or 0)
        d["codigos_unicos"].add(codigo)

    items = []
    total_count = sum(d["count"] for d in por_prefijo.values()) or 0
    for prefijo, d in por_prefijo.items():
        items.append({
            "prefijo": prefijo,
            "tipo": descripciones.get(prefijo, "Otro"),
            "count": d["count"],
            "valor_objetado": d["valor_objetado"],
            "codigos_distintos": len(d["codigos_unicos"]),
            "porcentaje": round(d["count"] / total_count * 100, 1) if total_count else 0,
        })
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "ventana_dias": dias,
        "total": total_count,
        "items": items,
    }


@router.get("/{glosa_id}/audit-resumen")
def audit_resumen_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R88 P2: resumen agregado del audit log de una glosa.

    Mientras /audit/glosa/{id} devuelve los eventos en bruto y
    /glosas/{id}/timeline los enriquece narrativamente, este
    endpoint da el "TL;DR":
      - total_cambios
      - primer_cambio_en / ultimo_cambio_en
      - usuarios_que_intervinieron (lista DISTINCT)
      - eventos_por_accion (conteo)
      - eventos_por_campo (qué columnas se modificaron y cuántas veces)

    Útil para mostrar un mini-widget "Actividad" en la ficha
    de la glosa sin tener que renderizar todo el audit raw.
    """
    from app.models.db import AuditLogRecord

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.registro_id == glosa_id)
        .all()
    )

    total = len(eventos)
    if total == 0:
        return {
            "glosa_id": glosa_id,
            "total_cambios": 0,
            "primer_cambio_en": None,
            "ultimo_cambio_en": None,
            "usuarios_que_intervinieron": [],
            "eventos_por_accion": {},
            "eventos_por_campo": {},
        }

    timestamps = [e.timestamp for e in eventos if e.timestamp]
    usuarios = sorted({e.usuario_email for e in eventos if e.usuario_email})

    por_accion: dict[str, int] = {}
    por_campo: dict[str, int] = {}
    for e in eventos:
        if e.accion:
            por_accion[e.accion] = por_accion.get(e.accion, 0) + 1
        if e.campo:
            por_campo[e.campo] = por_campo.get(e.campo, 0) + 1

    return {
        "glosa_id": glosa_id,
        "total_cambios": total,
        "primer_cambio_en": (
            min(timestamps).isoformat() if timestamps else None
        ),
        "ultimo_cambio_en": (
            max(timestamps).isoformat() if timestamps else None
        ),
        "usuarios_que_intervinieron": usuarios,
        "eventos_por_accion": por_accion,
        "eventos_por_campo": por_campo,
    }


@router.get("/{glosa_id}/timeline")
def timeline_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R67 P2: cronología consolidada de eventos de una glosa.

    Combina eventos de múltiples tablas en un solo timeline ordenado:
      - Creación de la glosa (creado_en del GlosaRecord)
      - Snapshots de versiones (DictamenVersionRecord — CREAR, REFINAR,
        REANALIZAR, RESTAURAR)
      - Cambios de estado (audit_log accion=ACTUALIZAR_ESTADO)
      - Decisión EPS (audit_log accion=DECISION_EPS)
      - Comentarios resueltos
      - Calls IA con costo (AICallRecord)

    Útil para:
      - Investigación de glosas con dictamen extraño
      - Auditoría regulatoria (¿quién tocó esta glosa, cuándo, qué hizo?)
      - Trazabilidad post-decisión de la EPS

    Respuesta: lista de {timestamp, tipo, actor, detalle, metadata}
    ordenada DESC (más reciente primero).
    """
    from app.models.db import (
        AICallRecord, AuditLogRecord, ComentarioGlosaRecord,
        DictamenVersionRecord,
    )

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    eventos = []

    # 1. Creación de la glosa
    if glosa.creado_en:
        eventos.append({
            "timestamp": glosa.creado_en.isoformat(),
            "tipo": "CREAR_GLOSA",
            "actor": glosa.auditor_email or "—",
            "detalle": f"Glosa creada · {glosa.eps} · {glosa.codigo_glosa}",
            "metadata": {
                "valor_objetado": float(glosa.valor_objetado or 0),
                "estado": glosa.estado,
            },
        })

    # 2. Versiones del dictamen
    versiones = (
        db.query(DictamenVersionRecord)
        .filter(DictamenVersionRecord.glosa_id == glosa_id)
        .all()
    )
    for v in versiones:
        eventos.append({
            "timestamp": v.creado_en.isoformat() if v.creado_en else None,
            "tipo": f"VERSION_{v.accion or 'CREAR'}",
            "actor": v.autor_email or "—",
            "detalle": v.mensaje_refinar or f"Snapshot del dictamen ({v.accion})",
            "metadata": {"version_id": v.id},
        })

    # 3. Audit log para esta glosa
    auditorias = (
        db.query(AuditLogRecord)
        .filter(
            AuditLogRecord.tabla.in_(("glosas", "historial")),
            AuditLogRecord.registro_id == glosa_id,
        )
        .all()
    )
    for a in auditorias:
        eventos.append({
            "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            "tipo": f"AUDIT_{a.accion or 'ACCION'}",
            "actor": a.usuario_email or "—",
            "detalle": (a.detalle or "")[:300],
            "metadata": {
                "campo": a.campo,
                "valor_anterior": (a.valor_anterior or "")[:80],
                "valor_nuevo": (a.valor_nuevo or "")[:80],
                "ip": a.ip,
            },
        })

    # 4. Comentarios resueltos
    comentarios = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.glosa_id == glosa_id)
        .all()
    )
    for c in comentarios:
        if c.creado_en:
            eventos.append({
                "timestamp": c.creado_en.isoformat(),
                "tipo": "COMENTARIO",
                "actor": c.autor_email or "—",
                "detalle": (c.texto or "")[:300],
                "metadata": {"resuelto": bool(c.resuelto_en)},
            })
        if c.resuelto_en:
            eventos.append({
                "timestamp": c.resuelto_en.isoformat(),
                "tipo": "COMENTARIO_RESUELTO",
                "actor": c.resuelto_por or "—",
                "detalle": "Comentario marcado como resuelto",
                "metadata": {"comentario_id": c.id},
            })

    # 5. Calls IA con costo
    calls = (
        db.query(AICallRecord)
        .filter(AICallRecord.glosa_id == glosa_id)
        .all()
    )
    for c in calls:
        if c.creado_en:
            eventos.append({
                "timestamp": c.creado_en.isoformat(),
                "tipo": "AI_CALL",
                "actor": c.user_email or "—",
                "detalle": f"{c.proveedor}/{c.modelo} · {c.latency_ms}ms · ${c.cost_usd:.5f}",
                "metadata": {
                    "tokens_in": (c.input_tokens or 0)
                                 + (c.cache_creation_input_tokens or 0)
                                 + (c.cache_read_input_tokens or 0),
                    "tokens_out": c.output_tokens,
                    "cost_usd": c.cost_usd,
                },
            })

    # Ordenar DESC (más reciente primero)
    eventos.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    return {
        "glosa_id": glosa_id,
        "total_eventos": len(eventos),
        "eventos": eventos,
    }
