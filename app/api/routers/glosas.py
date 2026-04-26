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


@router.get("/exportar-json")
def exportar_json(
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    valor_min: Optional[float] = None,
    valor_max: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R92 P1: export streaming en formato NDJSON (newline-delimited JSON).

    NDJSON > JSON-array para datos grandes:
      - Cada línea es un objeto independiente parseable
      - Permite streaming sin cargar todo en memoria
      - Compatible con jq, pandas.read_json(lines=True), etc.

    Útil para integrar con BI/data warehouse (Snowflake, BigQuery)
    que aceptan NDJSON nativo.

    Filtros opcionales: eps, estado, fecha_desde, fecha_hasta,
    valor_min, valor_max.
    """
    import json

    from fastapi.responses import StreamingResponse

    repo = GlosaRepository(db)
    glosas = repo.listar_para_export(
        eps=eps, estado=estado,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        valor_min=valor_min, valor_max=valor_max,
    )

    def _generar():
        for g in glosas:
            obj = {
                "id": g.id,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
                "eps": g.eps,
                "paciente": g.paciente,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": float(g.valor_objetado or 0),
                "valor_aceptado": float(g.valor_aceptado or 0),
                "valor_recuperado": float(g.valor_recuperado or 0),
                "etapa": g.etapa,
                "estado": g.estado,
                "decision_eps": g.decision_eps,
                "dias_restantes": g.dias_restantes,
                "gestor_nombre": g.gestor_nombre,
                "fecha_vencimiento": (
                    g.fecha_vencimiento.isoformat()
                    if g.fecha_vencimiento else None
                ),
                "fecha_decision_eps": (
                    g.fecha_decision_eps.isoformat()
                    if g.fecha_decision_eps else None
                ),
            }
            yield json.dumps(obj, ensure_ascii=False) + "\n"

    fname = f"glosas-{ahora_utc().strftime('%Y%m%d-%H%M%S')}.ndjson"
    return StreamingResponse(
        _generar(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


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


@router.get("/codigos-respuesta-catalogo")
def codigos_respuesta_catalogo(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R137 P1: catálogo de códigos de respuesta IPS (Res 2284/2023).

    Códigos RE oficiales que IPS usa para responder a una glosa
    o devolución de la EPS:
      - RE9901: Glosa no aceptada (defensa total) — más común
      - RE9801: Glosa aceptada parcialmente
      - RE9602: Glosa injustificada al 100%
      - RE9502: Glosa improcedente por extemporánea
      - etc.

    Útil para que el frontend renderice un dropdown contextual
    al responder una glosa.

    Devuelve los códigos con descripción + clasificación
    funcional (DEFENSA / ACEPTACION / EXTEMPORANEA / OTRO).
    """
    from app.services.catalogo_glosas import CODIGOS_RESPUESTA

    DEFENSA = {"RE9901", "RE9602", "RE9502", "RE9601", "RE9501"}
    ACEPTACION = {"RE9701", "RE9801"}
    EXTEMPORANEA = {"RE2201", "RE2202"}

    items = []
    for codigo, descripcion in sorted(CODIGOS_RESPUESTA.items()):
        if codigo in DEFENSA:
            tipo = "DEFENSA"
        elif codigo in ACEPTACION:
            tipo = "ACEPTACION"
        elif codigo in EXTEMPORANEA:
            tipo = "EXTEMPORANEA"
        else:
            tipo = "OTRO"
        items.append({
            "codigo": codigo,
            "descripcion": descripcion,
            "tipo_funcional": tipo,
        })

    return {
        "regulacion": "Resolución 2284/2023 — Códigos de respuesta IPS",
        "total_codigos": len(items),
        "items": items,
    }


@router.get("/codigos-glosa-catalogo")
def codigos_glosa_catalogo(
    grupo: Optional[str] = None,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R136 P2: catálogo de códigos de glosa Resolución 2284/2023.

    Expone el catálogo oficial del Manual Único usado por la IA
    para que el frontend pueda:
      - Mostrar autocomplete de códigos
      - Renderizar tooltip con descripción al hover
      - Validar que un código sea oficial antes de enviar

    Param `grupo` opcional filtra por familia (FA, TA, SO, AU,
    CO, CL, SA).

    Devuelve:
      - total_codigos
      - por_grupo: counts
      - items: [{codigo, grupo, descripcion}]
    """
    from app.services.catalogo_glosas import (
        CODIGOS_AU, CODIGOS_CL, CODIGOS_CO, CODIGOS_FA,
        CODIGOS_SA, CODIGOS_SO, CODIGOS_TA,
    )

    grupos = {
        "FA": CODIGOS_FA, "TA": CODIGOS_TA, "SO": CODIGOS_SO,
        "AU": CODIGOS_AU, "CO": CODIGOS_CO, "CL": CODIGOS_CL,
        "SA": CODIGOS_SA,
    }

    if grupo:
        g_upper = grupo.upper()
        if g_upper not in grupos:
            raise HTTPException(
                400,
                f"grupo inválido. Válidos: {sorted(grupos.keys())}",
            )
        grupos = {g_upper: grupos[g_upper]}

    items = []
    por_grupo: dict[str, int] = {}
    for nombre_grupo, dic in grupos.items():
        for codigo, descripcion in dic.items():
            items.append({
                "codigo": codigo,
                "grupo": nombre_grupo,
                "descripcion": descripcion,
            })
            por_grupo[nombre_grupo] = por_grupo.get(nombre_grupo, 0) + 1

    items.sort(key=lambda x: x["codigo"])

    return {
        "regulacion": "Resolución 2284/2023 — Manual Único de Glosas",
        "total_codigos": len(items),
        "por_grupo": por_grupo,
        "filtro_grupo": grupo,
        "items": items,
    }


@router.get("/estados-disponibles")
def estados_disponibles(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R136 P1: catálogo machine-readable de estados de glosa.

    Devuelve la lista oficial de estados con:
      - clave (valor en BD)
      - nombre amigable
      - descripcion
      - es_cerrado (bool)
      - color sugerido para UI (semáforo)

    Útil para que el frontend renderice dropdowns y badges
    consistentes sin hardcodear listas que se desactualizan.
    """
    estados = [
        {
            "clave": "RADICADA",
            "nombre": "Radicada",
            "descripcion": "Glosa recién recibida, esperando respuesta HUS.",
            "es_cerrado": False,
            "color": "AMARILLO",
        },
        {
            "clave": "RESPONDIDA",
            "nombre": "Respondida",
            "descripcion": (
                "HUS ya respondió la glosa, esperando decisión EPS."
            ),
            "es_cerrado": False,
            "color": "AZUL",
        },
        {
            "clave": "RATIFICADA",
            "nombre": "Ratificada por EPS",
            "descripcion": (
                "EPS sostuvo la glosa tras respuesta HUS. Pasa a "
                "siguiente etapa o se acepta."
            ),
            "es_cerrado": False,
            "color": "ROJO",
        },
        {
            "clave": "LEVANTADA",
            "nombre": "Levantada (HUS ganó)",
            "descripcion": "EPS retiró la glosa. HUS recupera el valor.",
            "es_cerrado": True,
            "color": "VERDE",
        },
        {
            "clave": "ACEPTADA",
            "nombre": "Aceptada por HUS",
            "descripcion": "HUS aceptó la glosa. EPS no paga ese ítem.",
            "es_cerrado": True,
            "color": "GRIS",
        },
        {
            "clave": "CONCILIADA",
            "nombre": "Conciliada bilateralmente",
            "descripcion": (
                "HUS y EPS llegaron a acuerdo en audiencia bilateral."
            ),
            "es_cerrado": True,
            "color": "AZUL",
        },
        {
            "clave": "ARCHIVADA",
            "nombre": "Archivada",
            "descripcion": (
                "Glosa retirada del flujo activo (sin valor a defender)."
            ),
            "es_cerrado": True,
            "color": "GRIS",
        },
        {
            "clave": "EXTEMPORANEA",
            "nombre": "Extemporánea",
            "descripcion": (
                "EPS objetó fuera del término legal. HUS puede rechazar."
            ),
            "es_cerrado": False,
            "color": "AMARILLO",
        },
    ]

    return {
        "total": len(estados),
        "estados": estados,
    }


@router.get("/buscar-similares-texto")
def buscar_similares_texto(
    texto: str = Query(..., min_length=10, max_length=2000),
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R103 P2: búsqueda de glosas con texto similar al dado.

    Útil para auditor que recibe glosa nueva: "¿hemos visto algo
    parecido antes?". Permite reusar respuestas/dictámenes
    previos como punto de partida.

    Algoritmo: Jaccard similarity sobre tokens del texto_glosa_original.
    Liviano, sin dependencias ML — bueno para datasets pequeños/medianos.

    Devuelve hasta `top` glosas con score 0-1 (1 = idéntico).
    Solo glosas con texto_glosa_original no-vacío.
    """
    import re

    def _tokenizar(s: str) -> set[str]:
        s = (s or "").lower()
        # Tokens alfanuméricos de >=3 caracteres (filtra "el", "de", etc.)
        return {t for t in re.findall(r"\w+", s) if len(t) >= 3}

    tokens_query = _tokenizar(texto)
    if not tokens_query:
        return {"total_evaluadas": 0, "items": []}

    candidatas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.texto_glosa_original.isnot(None))
        .all()
    )

    items = []
    for g in candidatas:
        tokens_g = _tokenizar(g.texto_glosa_original or "")
        if not tokens_g:
            continue
        union = tokens_query | tokens_g
        inter = tokens_query & tokens_g
        score = len(inter) / len(union) if union else 0
        if score < 0.05:  # threshold mínimo
            continue
        items.append({
            "id": g.id,
            "eps": g.eps,
            "codigo_glosa": g.codigo_glosa,
            "estado": g.estado,
            "score_similitud": round(score, 4),
            "preview": (g.texto_glosa_original or "")[:200],
        })

    items.sort(key=lambda x: x["score_similitud"], reverse=True)

    return {
        "total_evaluadas": len(candidatas),
        "total_con_score_minimo": len(items),
        "items": items[:top],
    }


@router.get("/buscar-avanzado")
def buscar_avanzado(
    eps: Optional[str] = None,
    paciente: Optional[str] = None,
    factura: Optional[str] = None,
    codigo_glosa: Optional[str] = None,
    estado: Optional[str] = None,
    etapa: Optional[str] = None,
    gestor: Optional[str] = None,
    valor_min: Optional[float] = None,
    valor_max: Optional[float] = None,
    fecha_desde: Optional[str] = Query(None, description="ISO YYYY-MM-DD"),
    fecha_hasta: Optional[str] = Query(None, description="ISO YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R94 P1: búsqueda multi-campo combinable (AND entre filtros).

    Complementa /buscar/{termino} (un solo término en factura/ID)
    permitiendo consultas precisas tipo:
      "glosas SANITAS de Pedro entre 1M-5M de marzo"

    Filtros opcionales combinables vía AND. Strings usan ILIKE %x%
    (búsqueda parcial case-insensitive). Fechas en ISO YYYY-MM-DD.

    Devuelve hasta `limit` resultados (default 50, max 500), ordenados
    DESC por creado_en.
    """
    from datetime import datetime, timezone

    q = db.query(GlosaRecord)
    if eps:
        q = q.filter(GlosaRecord.eps.ilike(f"%{eps}%"))
    if paciente:
        q = q.filter(GlosaRecord.paciente.ilike(f"%{paciente}%"))
    if factura:
        q = q.filter(GlosaRecord.factura.ilike(f"%{factura}%"))
    if codigo_glosa:
        q = q.filter(GlosaRecord.codigo_glosa.ilike(f"%{codigo_glosa}%"))
    if estado:
        q = q.filter(GlosaRecord.estado == estado.upper())
    if etapa:
        q = q.filter(GlosaRecord.etapa.ilike(f"%{etapa}%"))
    if gestor:
        q = q.filter(GlosaRecord.gestor_nombre.ilike(f"%{gestor}%"))
    if valor_min is not None:
        q = q.filter(GlosaRecord.valor_objetado >= valor_min)
    if valor_max is not None:
        q = q.filter(GlosaRecord.valor_objetado <= valor_max)
    if fecha_desde:
        try:
            dt = datetime.strptime(fecha_desde, "%Y-%m-%d").replace(
                tzinfo=timezone.utc,
            )
            q = q.filter(GlosaRecord.creado_en >= dt)
        except ValueError:
            raise HTTPException(400, "fecha_desde debe ser YYYY-MM-DD")
    if fecha_hasta:
        try:
            dt = datetime.strptime(fecha_hasta, "%Y-%m-%d").replace(
                tzinfo=timezone.utc,
            )
            q = q.filter(GlosaRecord.creado_en <= dt)
        except ValueError:
            raise HTTPException(400, "fecha_hasta debe ser YYYY-MM-DD")

    total = q.count()
    glosas = q.order_by(GlosaRecord.creado_en.desc()).limit(limit).all()

    return {
        "total_coincidencias": total,
        "limit": int(limit),
        "items": [
            {
                "id": g.id,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
                "eps": g.eps,
                "paciente": g.paciente,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": float(g.valor_objetado or 0),
                "estado": g.estado,
                "etapa": g.etapa,
                "gestor_nombre": g.gestor_nombre,
            }
            for g in glosas
        ],
    }


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


@router.get("/paciente-resumen")
def paciente_resumen(
    paciente: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R130 P1: resumen de glosas asociadas a un paciente.

    Útil para investigar el histórico de glosas de un paciente
    específico (mismo paciente puede tener varias hospitalizaciones
    objetadas).

    Query param `paciente` se usa con ILIKE para tolerancia a
    variaciones en mayúsculas/acentos.

    Devuelve:
      - total_glosas
      - facturas_distintas
      - eps_distintas
      - valor_objetado_total / valor_recuperado_total
      - estados (mapa)
      - glosas: lista resumida (id, factura, codigo_glosa, valor)
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.paciente.ilike(f"%{paciente}%"))
        .order_by(GlosaRecord.creado_en.desc())
        .all()
    )

    if not glosas:
        return {
            "paciente_buscado": paciente,
            "total_glosas": 0,
            "facturas_distintas": 0,
            "eps_distintas": 0,
            "valor_objetado_total": 0,
            "valor_recuperado_total": 0,
            "estados": {},
            "glosas": [],
        }

    facturas: set[str] = set()
    epss: set[str] = set()
    estados: dict[str, int] = {}
    valor_obj = 0.0
    valor_rec = 0.0

    for g in glosas:
        if g.factura and g.factura != "N/A":
            facturas.add(g.factura)
        if g.eps:
            epss.add(g.eps)
        e = g.estado or "?"
        estados[e] = estados.get(e, 0) + 1
        valor_obj += float(g.valor_objetado or 0)
        valor_rec += float(g.valor_recuperado or 0)

    return {
        "paciente_buscado": paciente,
        "total_glosas": len(glosas),
        "facturas_distintas": len(facturas),
        "eps_distintas": len(epss),
        "valor_objetado_total": int(valor_obj),
        "valor_recuperado_total": int(valor_rec),
        "estados": estados,
        "glosas": [
            {
                "id": g.id,
                "creado_en": (
                    g.creado_en.isoformat() if g.creado_en else None
                ),
                "factura": g.factura,
                "eps": g.eps,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": float(g.valor_objetado or 0),
                "estado": g.estado,
            }
            for g in glosas[:50]  # cap a 50 para no inflar
        ],
    }


@router.get("/sin-actividad")
def glosas_sin_actividad(
    dias: int = Query(15, ge=1, le=180),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R99 P1: glosas abiertas sin actualizaciones recientes.

    Detecta glosas no-cerradas que llevan más de N días sin
    movimiento en audit_log. Útil para que el coordinador
    identifique:
      - Glosas "olvidadas" en el flujo
      - Casos que necesitan seguimiento o reasignación
      - Trabajo estancado por carga de un gestor

    Por glosa devuelve:
      - id, eps, factura, estado, dias_restantes
      - ultimo_movimiento_en (max(creado_en, max(audit.timestamp)))
      - dias_sin_movimiento
      - gestor_nombre

    Ordenado DESC por dias_sin_movimiento.
    """
    from datetime import timedelta, timezone

    from app.models.db import AuditLogRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    # Última actividad por glosa según audit_log
    ultimas: dict[int, "object"] = {}
    rows = (
        db.query(AuditLogRecord.registro_id, AuditLogRecord.timestamp)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.registro_id.isnot(None))
        .all()
    )
    for rid, ts in rows:
        if not ts:
            continue
        prev = ultimas.get(rid)
        if prev is None or ts > prev:
            ultimas[rid] = ts

    ahora = ahora_utc()
    corte = ahora - timedelta(days=int(dias))

    items = []
    for g in abiertas:
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)

        ult = ultimas.get(g.id)
        if ult is not None and ult.tzinfo is None:
            ult = ult.replace(tzinfo=timezone.utc)

        # Última actividad = max(creación, último audit)
        ultimo_mov = creado
        if ult and (ultimo_mov is None or ult > ultimo_mov):
            ultimo_mov = ult

        if ultimo_mov is None or ultimo_mov >= corte:
            continue

        dias_sin = (ahora - ultimo_mov).days
        items.append({
            "id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "dias_restantes": g.dias_restantes,
            "gestor_nombre": g.gestor_nombre,
            "ultimo_movimiento_en": ultimo_mov.isoformat(),
            "dias_sin_movimiento": dias_sin,
        })

    items.sort(key=lambda x: x["dias_sin_movimiento"], reverse=True)

    return {
        "umbral_dias": int(dias),
        "total_sin_actividad": len(items),
        "limit": int(limit),
        "items": items[:limit],
    }


@router.get("/incompletas")
def glosas_incompletas(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R96 P2: lista glosas con datos críticos faltantes.

    Complementa /glosas/{id}/checklist (vista por glosa) con una
    vista agregada: ¿qué glosas tienen huecos que necesitan
    completarse?

    Filtra glosas no-cerradas a las que les falta AL MENOS UNO de:
      - texto_glosa_original
      - dictamen (vacío o muy corto)
      - factura (vacía o "N/A")
      - valor_objetado (0 o NULL)

    Útil para batch cleanup masivo del coordinador.

    Devuelve cada glosa con un campo "campos_faltantes" indicando
    cuáles específicamente, ordenadas DESC por número de huecos.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    # Pre-filtramos por estado en SQL; los criterios de huecos los
    # evaluamos en Python para tener semántica consistente (ej.
    # "dictamen corto" requiere len() y SQL LENGTH no es portable).
    candidatas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    items = []
    for g in candidatas:
        faltantes = []
        if not g.texto_glosa_original:
            faltantes.append("texto_glosa_original")
        if not g.dictamen or len(g.dictamen) <= 50:
            faltantes.append("dictamen")
        if not g.factura or g.factura == "N/A":
            faltantes.append("factura")
        if not g.valor_objetado or g.valor_objetado == 0:
            faltantes.append("valor_objetado")

        if not faltantes:
            continue

        items.append({
            "id": g.id,
            "creado_en": (
                g.creado_en.isoformat() if g.creado_en else None
            ),
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "campos_faltantes": faltantes,
            "total_huecos": len(faltantes),
        })

    items.sort(key=lambda x: x["total_huecos"], reverse=True)

    return {
        "total_incompletas": len(items),
        "limit": int(limit),
        "items": items[:limit],
    }


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


@router.get("/exportar-paquete-multi.zip")
def exportar_paquete_multi_zip(
    ids: str = Query(..., description="IDs CSV, ej '1,2,3'"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R138 P2: ZIP con evidencias de múltiples glosas en una
    sola descarga.

    Complementa /glosas/{id}/exportar-evidencia.zip (1 glosa)
    con la versión multi: descarga un ZIP con subcarpetas
    glosa-{id}/ por cada ID solicitado.

    Útil para entregas masivas a legal/compliance:
      "manda las 50 glosas de SANITAS de marzo en un paquete"

    Param `ids`: lista CSV de IDs (max 100 por request).

    Cada subcarpeta: glosa.json + dictamen.txt (si existe),
    plus README.txt en raíz con índice general.

    Declarado ANTES de /{glosa_id} para evitar collisión con
    el path resolver de FastAPI.
    """
    import io
    import json
    import zipfile

    from fastapi.responses import StreamingResponse

    try:
        ids_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids debe ser CSV de enteros")

    if not ids_list:
        raise HTTPException(400, "ids no puede estar vacío")
    if len(ids_list) > 100:
        raise HTTPException(400, "máximo 100 glosas por paquete")

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.id.in_(ids_list))
        .all()
    )
    if not glosas:
        raise HTTPException(404, "Ninguna glosa encontrada")

    encontrados = {g.id for g in glosas}
    no_encontrados = [i for i in ids_list if i not in encontrados]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        indice = (
            f"PAQUETE MULTI-GLOSA — {len(glosas)} glosas\n"
            f"Generado: {ahora_utc().isoformat()}\n"
            f"Por: {current_user.email}\n\n"
            f"IDs solicitados: {ids_list}\n"
            f"IDs encontrados: {sorted(encontrados)}\n"
            f"IDs no encontrados: {no_encontrados}\n"
        )
        zf.writestr("README.txt", indice)

        for g in glosas:
            subdir = f"glosa-{g.id}/"
            datos = {
                "id": g.id,
                "creado_en": (
                    g.creado_en.isoformat() if g.creado_en else None
                ),
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": float(g.valor_objetado or 0),
                "valor_recuperado": float(g.valor_recuperado or 0),
                "estado": g.estado,
                "decision_eps": g.decision_eps,
            }
            zf.writestr(
                f"{subdir}glosa.json",
                json.dumps(datos, ensure_ascii=False, indent=2),
            )
            if g.dictamen:
                zf.writestr(f"{subdir}dictamen.txt", g.dictamen)

    buf.seek(0)
    fname = f"glosas-paquete-{ahora_utc().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


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


@router.get("/stats/anomalias")
def stats_anomalias(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R114 P1: detecta glosas con valores atípicos (outliers).

    Usa IQR (interquartile range) sobre valor_objetado:
      - Q1 = percentil 25
      - Q3 = percentil 75
      - IQR = Q3 - Q1
      - Outlier alto: valor > Q3 + 1.5 * IQR
      - Outlier bajo: valor < Q1 - 1.5 * IQR

    Útil para identificar:
      - Glosas con valores monstruosos (revisar, ¿typo?)
      - Glosas mini (¿vale la pena pelearlas?)
      - Patrones inusuales

    Devuelve estadísticas + lista de outliers (max 50).
    """
    glosas = db.query(GlosaRecord).all()
    valores = [
        (g, float(g.valor_objetado or 0))
        for g in glosas
        if g.valor_objetado and float(g.valor_objetado) > 0
    ]

    if len(valores) < 4:
        return {
            "total_glosas_evaluadas": len(valores),
            "razon": "Necesitas al menos 4 glosas con valor>0 para "
                    "calcular cuartiles.",
            "outliers_altos": [],
            "outliers_bajos": [],
        }

    sorted_valores = sorted([v for _, v in valores])
    n = len(sorted_valores)
    q1 = sorted_valores[n // 4]
    q3 = sorted_valores[3 * n // 4]
    iqr = q3 - q1
    upper = q3 + 1.5 * iqr
    lower = max(0, q1 - 1.5 * iqr)

    outliers_altos = []
    outliers_bajos = []
    for g, v in valores:
        if v > upper:
            outliers_altos.append({
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "valor_objetado": int(v),
                "veces_sobre_q3": round(v / q3, 2) if q3 else 0,
            })
        elif v < lower:
            outliers_bajos.append({
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "valor_objetado": int(v),
            })

    outliers_altos.sort(key=lambda x: x["valor_objetado"], reverse=True)
    outliers_bajos.sort(key=lambda x: x["valor_objetado"])

    return {
        "total_glosas_evaluadas": len(valores),
        "estadisticas": {
            "q1": int(q1),
            "q3": int(q3),
            "iqr": int(iqr),
            "limite_superior_outlier": int(upper),
            "limite_inferior_outlier": int(lower),
        },
        "total_outliers_altos": len(outliers_altos),
        "total_outliers_bajos": len(outliers_bajos),
        "outliers_altos": outliers_altos[:50],
        "outliers_bajos": outliers_bajos[:50],
    }


@router.get("/stats/concentracion-pareto")
def stats_concentracion_pareto(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R113 P1: análisis Pareto (80/20) sobre EPS y valor.

    Identifica si el valor está concentrado en pocas EPS:
      - ¿Cuántas EPS aportan el 80% del valor objetado?
      - ¿Cuál es el coeficiente de Gini?

    Útil para entender la dependencia HUS-EPS:
      - Alta concentración: foco en pocas EPS clave
      - Baja concentración: gestión más distribuida

    Devuelve:
      - eps_para_80_pct: int (cuántas EPS suman 80% del valor)
      - top_eps_concentracion: serie con cumulative_pct
      - gini_coefficient: 0 (igual) ... 1 (concentración total)
    """
    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, float] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        por_eps[eps] = por_eps.get(eps, 0.0) + float(g.valor_objetado or 0)

    if not por_eps:
        return {
            "total_eps": 0,
            "valor_total": 0,
            "eps_para_80_pct": 0,
            "gini_coefficient": 0.0,
            "top_eps_concentracion": [],
        }

    valores = sorted(por_eps.values(), reverse=True)
    total = sum(valores)

    # Pareto: cuántas EPS para 80%
    acumulado = 0.0
    eps_80 = 0
    cuantas_para_80 = 0
    for i, v in enumerate(valores):
        acumulado += v
        if acumulado / total >= 0.80 and cuantas_para_80 == 0:
            cuantas_para_80 = i + 1
            break

    # Gini coefficient (formulación Lorenz)
    n = len(valores)
    valores_asc = sorted(valores)
    suma_pesada = sum((i + 1) * v for i, v in enumerate(valores_asc))
    gini = (2 * suma_pesada) / (n * sum(valores_asc)) - (n + 1) / n
    gini = round(gini, 4)

    # Top concentración (DESC) con cumulative_pct
    items_eps = sorted(por_eps.items(), key=lambda x: x[1], reverse=True)
    cum = 0.0
    top_concentracion = []
    for eps, v in items_eps[:20]:  # Top 20
        cum += v
        top_concentracion.append({
            "eps": eps,
            "valor": int(v),
            "pct_individual": round(100 * v / total, 2),
            "pct_acumulado": round(100 * cum / total, 2),
        })

    return {
        "total_eps": len(por_eps),
        "valor_total": int(total),
        "eps_para_80_pct": cuantas_para_80,
        "gini_coefficient": gini,
        "top_eps_concentracion": top_concentracion,
    }


@router.get("/stats/refinaciones")
def stats_refinaciones(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R129 P2: métricas globales de refinaciones de dictámenes.

    Agregado del versionado de TODOS los dictámenes en la
    ventana. Útil para detectar si los auditores están
    "refinando demasiado" (señal de que el dictamen IA inicial
    no satisface).

    Devuelve:
      - total_acciones
      - por_accion: counts por tipo (CREAR, REFINAR, REGENERAR,
                    RESTAURAR)
      - top_5_autores: usuarios que más refinan
      - glosas_con_refinaciones (DISTINCT glosa_id)
      - promedio_versiones_por_glosa
      - tasa_refinacion_pct (REFINAR / total acciones)
    """
    from datetime import timedelta

    from app.models.db import DictamenVersionRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    versiones = (
        db.query(DictamenVersionRecord)
        .filter(DictamenVersionRecord.creado_en >= desde)
        .all()
    )

    if not versiones:
        return {
            "ventana_dias": int(dias),
            "total_acciones": 0,
            "por_accion": {},
            "top_5_autores": [],
            "glosas_con_refinaciones": 0,
            "promedio_versiones_por_glosa": 0.0,
            "tasa_refinacion_pct": 0.0,
        }

    por_accion: dict[str, int] = {}
    por_autor: dict[str, int] = {}
    glosas_set: set[int] = set()
    for v in versiones:
        if v.accion:
            por_accion[v.accion] = por_accion.get(v.accion, 0) + 1
        if v.autor_email:
            por_autor[v.autor_email] = por_autor.get(v.autor_email, 0) + 1
        if v.glosa_id is not None:
            glosas_set.add(v.glosa_id)

    top_5 = sorted(
        por_autor.items(), key=lambda x: x[1], reverse=True,
    )[:5]

    refinar = por_accion.get("REFINAR", 0)
    tasa = round(100 * refinar / len(versiones), 2)

    return {
        "ventana_dias": int(dias),
        "total_acciones": len(versiones),
        "por_accion": por_accion,
        "top_5_autores": [
            {"autor": u, "acciones": n} for u, n in top_5
        ],
        "glosas_con_refinaciones": len(glosas_set),
        "promedio_versiones_por_glosa": (
            round(len(versiones) / len(glosas_set), 2)
            if glosas_set else 0.0
        ),
        "tasa_refinacion_pct": tasa,
    }


@router.get("/stats/conciliaciones")
def stats_conciliaciones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R128 P1: métricas de conciliaciones bilaterales HUS-EPS.

    La conciliación es la última instancia antes del litigio: si
    EPS no levanta y HUS no acepta, hay audiencia bilateral con
    acta firmada.

    Útil para entender:
      - ¿Cuántas glosas terminan en conciliación?
      - ¿Cuál es el valor promedio defendido vs conciliado?
      - ¿Estados bilaterales en pipeline?

    Devuelve:
      - total_conciliaciones
      - por_resultado (mapa)
      - por_estado_bilateral (mapa)
      - valor_total_conciliado
      - valor_total_defendido_hus (valor_ratificado_hus)
      - tasa_recuperacion_conciliacion_pct
      - audiencias_proximas_30d
    """
    from datetime import timedelta, timezone

    from app.models.db import ConciliacionRecord

    todas = db.query(ConciliacionRecord).all()

    if not todas:
        return {
            "total_conciliaciones": 0,
            "por_resultado": {},
            "por_estado_bilateral": {},
            "valor_total_conciliado": 0,
            "valor_total_defendido_hus": 0,
            "tasa_recuperacion_conciliacion_pct": 0.0,
            "audiencias_proximas_30d": 0,
        }

    por_resultado: dict[str, int] = {}
    por_estado: dict[str, int] = {}
    valor_conc = 0.0
    valor_def = 0.0

    ahora = ahora_utc()
    en_30d = ahora + timedelta(days=30)
    audiencias_proximas = 0

    for c in todas:
        if c.resultado:
            por_resultado[c.resultado] = (
                por_resultado.get(c.resultado, 0) + 1
            )
        eb = c.estado_bilateral or "?"
        por_estado[eb] = por_estado.get(eb, 0) + 1
        valor_conc += float(c.valor_conciliado or 0)
        valor_def += float(c.valor_ratificado_hus or 0)

        fa = c.fecha_audiencia
        if fa and fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        if fa and ahora <= fa <= en_30d:
            audiencias_proximas += 1

    tasa = (
        round(100 * valor_conc / valor_def, 2)
        if valor_def else 0.0
    )

    return {
        "total_conciliaciones": len(todas),
        "por_resultado": por_resultado,
        "por_estado_bilateral": por_estado,
        "valor_total_conciliado": int(valor_conc),
        "valor_total_defendido_hus": int(valor_def),
        "tasa_recuperacion_conciliacion_pct": tasa,
        "audiencias_proximas_30d": audiencias_proximas,
    }


@router.get("/stats/serie-mensual-cantidad")
def stats_serie_mensual_cantidad(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R124 P2: serie temporal mensual con creadas Y cerradas.

    Diferente a /stats/recuperacion-mensual (solo valor) y
    /stats/cohorte-mensual (% cierre por cohorte de creación):
    aquí se muestra el flujo entrante vs saliente del backlog.

    Útil para gráficos de doble línea:
      - Línea 1: glosas creadas en el mes
      - Línea 2: glosas cerradas en el mes
      - Si línea 1 > línea 2 sostenidamente → backlog crece

    Devuelve serie ascendente:
      [{"mes": "2026-04", "creadas": 50, "cerradas": 35,
        "delta_neto": 15, "ratio_cierre": 0.7}, ...]
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    creadas_mes: dict[str, int] = {}
    cerradas_mes: dict[str, int] = {}

    for g in glosas:
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        if creado:
            k = creado.strftime("%Y-%m")
            creadas_mes[k] = creadas_mes.get(k, 0) + 1

        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if (dec and (g.estado or "").upper() in ESTADOS_CERRADOS):
            k = dec.strftime("%Y-%m")
            cerradas_mes[k] = cerradas_mes.get(k, 0) + 1

    todos_meses = sorted(set(creadas_mes.keys()) | set(cerradas_mes.keys()))
    meses_recientes = todos_meses[-int(meses):]

    serie = []
    for k in meses_recientes:
        c = creadas_mes.get(k, 0)
        cer = cerradas_mes.get(k, 0)
        ratio = round(cer / c, 2) if c else None
        serie.append({
            "mes": k,
            "creadas": c,
            "cerradas": cer,
            "delta_neto": c - cer,
            "ratio_cierre": ratio,
        })

    return {
        "meses_solicitados": int(meses),
        "total_meses_disponibles": len(todos_meses),
        "serie": serie,
    }


@router.get("/stats/facturas-hot")
def stats_facturas_hot(
    min_glosas: int = Query(3, ge=2, le=20),
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R124 P1: facturas con múltiples glosas asociadas.

    "Hot facturas" = facturas con N+ glosas distintas. Indican:
      - Servicio/episodio complejo bajo objeción múltiple
      - Posible glosa fraccionada (mala práctica EPS)
      - Caso de litigio prioritario

    Devuelve top N facturas con >= min_glosas:
      - factura, eps
      - count_glosas
      - valor_objetado_total
      - estados (mapa estado→count)
      - codigos_distintos
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .all()
    )

    por_factura: dict[str, dict] = {}
    for g in glosas:
        f = g.factura
        if f not in por_factura:
            por_factura[f] = {
                "eps": g.eps,
                "count": 0,
                "valor_objetado": 0.0,
                "estados": {},
                "codigos": set(),
            }
        b = por_factura[f]
        b["count"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)
        estado = g.estado or "?"
        b["estados"][estado] = b["estados"].get(estado, 0) + 1
        if g.codigo_glosa:
            b["codigos"].add(g.codigo_glosa)

    items = []
    for f, b in por_factura.items():
        if b["count"] < min_glosas:
            continue
        items.append({
            "factura": f,
            "eps": b["eps"],
            "count_glosas": b["count"],
            "valor_objetado_total": int(b["valor_objetado"]),
            "estados": b["estados"],
            "codigos_distintos": sorted(b["codigos"]),
        })
    items.sort(key=lambda x: x["count_glosas"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_facturas_calientes": len(items),
        "items": items[:top],
    }


@router.get("/stats/cobranza-por-eps")
def stats_cobranza_por_eps(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R122 P2: ranking de EPS por valor pendiente de cobro.

    Cruza /stats/cobranza-pendiente (global) con la EPS deudora
    para identificar contra quién hay más plata por defender:
      "$50M pendientes de SANITAS, $30M de NUEVA EPS, ..."

    Devuelve top N EPS ordenadas DESC por valor_pendiente con:
      - count_pendientes
      - valor_pendiente (sum de valor_objetado en abiertas)
      - valor_recuperable_estimado (con tasa histórica de la EPS)
      - tasa_historica_recuperacion_pct
      - antiguedad_promedio_dias
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ahora = ahora_utc()

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {
                "pendiente_count": 0, "pendiente_valor": 0.0,
                "antiguedades": [],
                "cerradas_obj": 0.0, "cerradas_rec": 0.0,
            }
        b = por_eps[eps]
        v = float(g.valor_objetado or 0)
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            b["cerradas_obj"] += v
            b["cerradas_rec"] += float(g.valor_recuperado or 0)
        else:
            b["pendiente_count"] += 1
            b["pendiente_valor"] += v
            creado = g.creado_en
            if creado and creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            if creado:
                b["antiguedades"].append((ahora - creado).days)

    items = []
    for eps, b in por_eps.items():
        if b["pendiente_count"] == 0:
            continue
        tasa_hist = (
            round(100 * b["cerradas_rec"] / b["cerradas_obj"], 2)
            if b["cerradas_obj"] else 0.0
        )
        recuperable = b["pendiente_valor"] * (tasa_hist / 100)
        antig_prom = (
            round(sum(b["antiguedades"]) / len(b["antiguedades"]), 1)
            if b["antiguedades"] else 0.0
        )
        items.append({
            "eps": eps,
            "count_pendientes": b["pendiente_count"],
            "valor_pendiente": int(b["pendiente_valor"]),
            "tasa_historica_recuperacion_pct": tasa_hist,
            "valor_recuperable_estimado": int(recuperable),
            "antiguedad_promedio_dias": antig_prom,
        })
    items.sort(key=lambda x: x["valor_pendiente"], reverse=True)

    return {
        "top_solicitado": int(top),
        "total_eps_con_pendientes": len(items),
        "valor_pendiente_global": sum(it["valor_pendiente"] for it in items),
        "items": items[:top],
    }


@router.get("/stats/cobranza-pendiente")
def stats_cobranza_pendiente(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R120 P2: valor pendiente de cobro segmentado por antigüedad.

    Complementa /stats/proyeccion-recuperacion (forecast global) con
    desglose por buckets de antigüedad — útil para priorizar
    cobranza:
      - <30d: cobranza temprana, alta probabilidad
      - 30-60d: cobranza estándar
      - 60-90d: cobranza tardía, alerta amarilla
      - >90d: cobranza dudosa, alerta roja

    Solo cuenta glosas no-cerradas con valor_objetado > 0.

    Devuelve por bucket:
      - count, valor_pendiente
      - pct_count y pct_valor
      - tasa_recuperacion_historica_pct (estimada del histórico)
      - valor_recuperable_estimado
    """
    from datetime import timedelta, timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    BUCKETS = [
        ("<30d",   0,    30),
        ("30-60d", 30,   60),
        ("60-90d", 60,   90),
        (">90d",   90,   None),
    ]

    ahora = ahora_utc()
    glosas = db.query(GlosaRecord).all()

    # Tasa histórica global para extrapolar
    cerradas_obj = 0.0
    cerradas_rec = 0.0
    pendientes = []
    for g in glosas:
        v = float(g.valor_objetado or 0)
        if v <= 0:
            continue
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            cerradas_obj += v
            cerradas_rec += float(g.valor_recuperado or 0)
        else:
            creado = g.creado_en
            if creado and creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            antig = (ahora - creado).days if creado else 0
            pendientes.append((antig, v))

    tasa_historica = (
        round(100 * cerradas_rec / cerradas_obj, 2)
        if cerradas_obj else 0.0
    )

    total_count = len(pendientes)
    total_valor = sum(v for _, v in pendientes)

    items = []
    for nombre, lo, hi in BUCKETS:
        en_bucket = [
            (a, v) for a, v in pendientes
            if a >= lo and (hi is None or a < hi)
        ]
        n = len(en_bucket)
        v_sum = sum(v for _, v in en_bucket)
        recuperable = v_sum * (tasa_historica / 100)
        items.append({
            "rango_antiguedad": nombre,
            "antiguedad_min_dias": lo,
            "antiguedad_max_dias": hi,
            "count": n,
            "valor_pendiente": int(v_sum),
            "pct_count": round(100 * n / total_count, 2) if total_count else 0.0,
            "pct_valor": round(100 * v_sum / total_valor, 2) if total_valor else 0.0,
            "valor_recuperable_estimado": int(recuperable),
        })

    return {
        "tasa_historica_recuperacion_pct": tasa_historica,
        "total_pendientes": total_count,
        "valor_pendiente_total": int(total_valor),
        "valor_recuperable_estimado_total": int(
            total_valor * (tasa_historica / 100),
        ),
        "buckets": items,
    }


@router.get("/stats/eps-emergentes")
def stats_eps_emergentes(
    dias: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R120 P1: detecta EPS que aparecen como nuevas en el período.

    Una EPS es "emergente" si:
      - Tiene glosas creadas en los últimos N días
      - NO tenía glosas en el histórico previo

    Útil para alertar al coordinador:
      "¡Aparece una nueva EPS en el sistema! Verificar contrato."

    Devuelve:
      - eps_nuevas: lista de EPS emergentes con count y valor
      - eps_continuas: count de EPS que vienen del histórico
    """
    from datetime import timedelta, timezone

    ahora = ahora_utc()
    corte = ahora - timedelta(days=int(dias))

    eps_recientes: dict[str, dict] = {}
    eps_historicas: set[str] = set()

    for g in db.query(GlosaRecord).all():
        eps = (g.eps or "").strip()
        if not eps:
            continue
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)

        if creado and creado >= corte:
            if eps not in eps_recientes:
                eps_recientes[eps] = {
                    "count": 0, "valor_objetado": 0.0,
                    "primer_visto": None,
                }
            b = eps_recientes[eps]
            b["count"] += 1
            b["valor_objetado"] += float(g.valor_objetado or 0)
            if b["primer_visto"] is None or creado < b["primer_visto"]:
                b["primer_visto"] = creado
        elif creado:
            eps_historicas.add(eps)

    nuevas = []
    continuas = 0
    for eps, b in eps_recientes.items():
        if eps in eps_historicas:
            continuas += 1
            continue
        nuevas.append({
            "eps": eps,
            "glosas_recientes": b["count"],
            "valor_objetado_total": int(b["valor_objetado"]),
            "primer_glosa_en": (
                b["primer_visto"].isoformat() if b["primer_visto"] else None
            ),
        })

    nuevas.sort(key=lambda x: x["glosas_recientes"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_eps_nuevas": len(nuevas),
        "total_eps_continuas": continuas,
        "items": nuevas,
    }


@router.get("/stats/estatus-eps")
def stats_estatus_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R137 P2: estado consolidado por EPS con semáforo.

    Para cada EPS calcula un estatus VERDE/AMARILLO/ROJO basado
    en señales agregadas:
      - ROJO: 15+ vencidas O (tasa_lev<30% con >=5 decididas)
      - AMARILLO: 5+ vencidas O tasa_lev<60% con >=5 decididas
      - VERDE: el resto

    Útil como vista resumen rápida: "¿con qué EPS estamos
    teniendo problemas?"

    Devuelve por EPS: status, razones (lista), + métricas detalladas.
    Items ordenados ROJO → AMARILLO → VERDE.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {
                "total": 0, "decididas": 0, "levantadas": 0,
                "vencidas": 0, "criticas": 0,
            }
        b = por_eps[eps]
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            if estado in {"LEVANTADA", "ACEPTADA"}:
                b["decididas"] += 1
                if estado == "LEVANTADA":
                    b["levantadas"] += 1
        else:
            dr = g.dias_restantes if g.dias_restantes is not None else 0
            if dr < 0:
                b["vencidas"] += 1
            elif dr <= 3:
                b["criticas"] += 1

    items = []
    for eps, b in por_eps.items():
        tasa = (
            round(100 * b["levantadas"] / b["decididas"], 2)
            if b["decididas"] else 0.0
        )
        razones = []
        if b["vencidas"] > 15:
            status = "ROJO"
            razones.append(f"{b['vencidas']} glosas vencidas")
        elif tasa < 30 and b["decididas"] >= 5:
            status = "ROJO"
            razones.append(f"tasa_levantamiento_pct={tasa} muy baja")
        elif b["vencidas"] > 5 or (tasa < 60 and b["decididas"] >= 5):
            status = "AMARILLO"
            if b["vencidas"] > 5:
                razones.append(f"{b['vencidas']} vencidas")
            if tasa < 60 and b["decididas"] >= 5:
                razones.append(
                    f"tasa_levantamiento_pct={tasa} bajo target"
                )
        else:
            status = "VERDE"
            razones.append("operación saludable")

        items.append({
            "eps": eps,
            "status": status,
            "razones": razones,
            "total_glosas": b["total"],
            "decididas": b["decididas"],
            "levantadas": b["levantadas"],
            "vencidas": b["vencidas"],
            "criticas": b["criticas"],
            "tasa_levantamiento_pct": tasa,
        })

    orden_status = {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}
    items.sort(key=lambda x: (orden_status[x["status"]], x["eps"]))

    counts = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0}
    for it in items:
        counts[it["status"]] += 1

    return {
        "total_eps": len(items),
        "por_status": counts,
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


@router.get("/stats/comparar-periodos")
def stats_comparar_periodos(
    dias: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R118 P1: compara métricas del período actual vs anterior.

    Útil para reportes "vs mes pasado":
      - "Este mes creamos 50 glosas; el mes pasado fueron 40
        → +25%"
      - "Recuperamos $5M vs $3M → +66%"

    Devuelve métricas de ambos períodos + delta absoluto y %:
      - glosas_creadas
      - glosas_cerradas
      - valor_recuperado
      - tiempo_promedio_resolucion_dias

    Período actual = últimos N días.
    Período previo = los N días anteriores a esos.
    """
    from datetime import timedelta, timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()
    hoy_inicio = ahora - timedelta(days=int(dias))
    prev_inicio = hoy_inicio - timedelta(days=int(dias))

    todas = db.query(GlosaRecord).all()

    def _stats(desde, hasta):
        creadas = 0
        cerradas = 0
        valor_rec = 0.0
        tiempos = []
        for g in todas:
            creado = g.creado_en
            if creado and creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            dec = g.fecha_decision_eps
            if dec and dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)

            if creado and desde <= creado < hasta:
                creadas += 1

            if (dec and desde <= dec < hasta and
                    (g.estado or "").upper() in ESTADOS_CERRADOS):
                cerradas += 1
                valor_rec += float(g.valor_recuperado or 0)
                if creado:
                    tiempos.append((dec - creado).days)

        return {
            "glosas_creadas": creadas,
            "glosas_cerradas": cerradas,
            "valor_recuperado": int(valor_rec),
            "tiempo_promedio_resolucion_dias": (
                round(sum(tiempos) / len(tiempos), 2)
                if tiempos else 0.0
            ),
        }

    actual = _stats(hoy_inicio, ahora)
    previo = _stats(prev_inicio, hoy_inicio)

    def _delta(a, p):
        diff = a - p
        pct = round(100 * diff / p, 2) if p else None
        return {"absoluto": diff, "pct": pct}

    deltas = {
        k: _delta(actual[k], previo[k])
        for k in actual.keys()
    }

    return {
        "ventana_dias": int(dias),
        "periodo_actual": {
            "desde": hoy_inicio.isoformat(),
            "hasta": ahora.isoformat(),
            **actual,
        },
        "periodo_previo": {
            "desde": prev_inicio.isoformat(),
            "hasta": hoy_inicio.isoformat(),
            **previo,
        },
        "deltas": deltas,
    }


@router.get("/stats/forecast-cierres")
def stats_forecast_cierres(
    semanas: int = Query(8, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R115 P2: proyección de cierres en las próximas N semanas.

    Basado en velocidad_diaria_promedio_30d (de R115 P1) extrapolado
    a futuro. Modelo simple: lineal, asume velocidad estable.

    Útil para gráficos de proyección "burndown" del backlog:
      - ¿Cuándo terminamos de cerrar las 500 pendientes?
      - ¿La velocidad actual alcanza para el deadline?

    Devuelve serie semanal:
      [{"semana": "2026-W18", "cierres_estimados": 35,
        "pendientes_restantes_estimados": 465}, ...]
    """
    from datetime import timedelta, timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()
    desde_30 = ahora - timedelta(days=30)

    cerradas_30d = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(GlosaRecord.fecha_decision_eps >= desde_30)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .count()
    )
    velocidad_diaria = cerradas_30d / 30 if cerradas_30d else 0
    velocidad_semanal = velocidad_diaria * 7

    pendientes_actuales = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .count()
    )

    serie = []
    pendientes = pendientes_actuales
    for w in range(1, int(semanas) + 1):
        cierres = min(int(velocidad_semanal), pendientes)
        pendientes -= cierres
        fecha = ahora + timedelta(weeks=w)
        serie.append({
            "semana": f"{fecha.year}-W{fecha.isocalendar()[1]:02d}",
            "cierres_estimados": cierres,
            "pendientes_restantes_estimados": max(0, pendientes),
        })
        if pendientes <= 0:
            break

    return {
        "semanas_solicitadas": int(semanas),
        "velocidad_semanal_actual": round(velocidad_semanal, 2),
        "pendientes_inicial": pendientes_actuales,
        "serie": serie,
    }


@router.get("/stats/velocidad-equipo")
def stats_velocidad_equipo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R115 P1: throughput del equipo (glosas cerradas por período).

    Mide la velocidad de cierre del equipo, útil para:
      - Capacity planning ("¿podemos cerrar las 500 pendientes en
        un mes con la velocidad actual?")
      - Detectar caídas de productividad
      - Trends semana-a-semana

    Devuelve:
      - cerradas_ultimos_7d / 30d / 90d (counts)
      - velocidad_diaria_promedio_30d
      - dias_para_cerrar_pendientes (estimado)
    """
    from datetime import timedelta, timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()

    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    cerradas_7d = 0
    cerradas_30d = 0
    cerradas_90d = 0
    for g in cerradas:
        dec = g.fecha_decision_eps
        if dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        delta = (ahora - dec).days
        if delta <= 7:
            cerradas_7d += 1
        if delta <= 30:
            cerradas_30d += 1
        if delta <= 90:
            cerradas_90d += 1

    pendientes = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .count()
    )

    velocidad_diaria_30d = round(cerradas_30d / 30, 2)
    dias_para_cerrar = (
        round(pendientes / velocidad_diaria_30d, 1)
        if velocidad_diaria_30d > 0 else None
    )

    return {
        "ahora": ahora.isoformat(),
        "cerradas_ultimos_7d": cerradas_7d,
        "cerradas_ultimos_30d": cerradas_30d,
        "cerradas_ultimos_90d": cerradas_90d,
        "velocidad_diaria_promedio_30d": velocidad_diaria_30d,
        "pendientes_actuales": pendientes,
        "dias_estimados_cerrar_pendientes": dias_para_cerrar,
    }


@router.get("/stats/desempeno-trimestral")
def stats_desempeno_trimestral(
    trimestres: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R109 P1: evolución del desempeño HUS por trimestre.

    Útil para informe ejecutivo periódico: ¿estamos mejorando?
    Cada trimestre devuelve:
      - total_glosas (creadas en el trimestre)
      - decididas / pendientes
      - tasa_levantamiento_pct
      - valor_objetado_total / valor_recuperado_total
      - tasa_recuperacion_pct

    Útil para gráficos de evolución (línea trimestre-a-trimestre).
    Trimestre se calcula con ((mes-1)//3 + 1) → Q1, Q2, Q3, Q4.
    """
    from datetime import timezone

    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA",
                        "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    por_trim: dict[str, dict] = {}
    for g in glosas:
        if not g.creado_en:
            continue
        creado = g.creado_en
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        anio = creado.year
        trim = (creado.month - 1) // 3 + 1
        key = f"{anio}-Q{trim}"

        if key not in por_trim:
            por_trim[key] = {
                "total": 0, "decididas": 0, "levantadas": 0,
                "valor_obj": 0.0, "valor_rec": 0.0,
            }
        b = por_trim[key]
        b["total"] += 1
        b["valor_obj"] += float(g.valor_objetado or 0)
        b["valor_rec"] += float(g.valor_recuperado or 0)

        estado = (g.estado or "").upper()
        if estado in ESTADOS_DECIDIDOS:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

    # Ordenar por trimestre y limitar a últimos N
    keys_ordenados = sorted(por_trim.keys())
    keys_recientes = keys_ordenados[-int(trimestres):]

    serie = []
    for key in keys_recientes:
        b = por_trim[key]
        tasa_lev = (
            round(100 * b["levantadas"] / b["decididas"], 2)
            if b["decididas"] else 0.0
        )
        tasa_rec = (
            round(100 * b["valor_rec"] / b["valor_obj"], 2)
            if b["valor_obj"] else 0.0
        )
        serie.append({
            "trimestre": key,
            "total_glosas": b["total"],
            "decididas": b["decididas"],
            "pendientes": b["total"] - b["decididas"],
            "levantadas": b["levantadas"],
            "tasa_levantamiento_pct": tasa_lev,
            "valor_objetado_total": int(b["valor_obj"]),
            "valor_recuperado_total": int(b["valor_rec"]),
            "tasa_recuperacion_pct": tasa_rec,
        })

    return {
        "trimestres_solicitados": int(trimestres),
        "total_trimestres_disponibles": len(por_trim),
        "serie": serie,
    }


@router.get("/stats/picos-historicos")
def stats_picos_historicos(
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R104 P2: top N días con más glosas creadas (picos de carga).

    Útil para:
      - Identificar fechas de "embotellamiento" históricas
      - Correlacionar con eventos externos (cargas masivas EPS,
        cambios normativos, fin de mes)
      - Planeación: "los días X-Y de cada mes pico hay alta carga"

    Devuelve top N días ordenados DESC por glosas creadas:
      [{"fecha": "2026-04-15", "glosas": 47, "valor_total": 8500000}, ...]
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).all()

    por_dia: dict[str, dict] = {}
    for g in glosas:
        if not g.creado_en:
            continue
        creado = g.creado_en
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        key = creado.date().isoformat()
        if key not in por_dia:
            por_dia[key] = {"glosas": 0, "valor": 0.0}
        por_dia[key]["glosas"] += 1
        por_dia[key]["valor"] += float(g.valor_objetado or 0)

    items = [
        {
            "fecha": k,
            "glosas": v["glosas"],
            "valor_total": int(v["valor"]),
        }
        for k, v in por_dia.items()
    ]
    items.sort(key=lambda x: x["glosas"], reverse=True)

    return {
        "top_solicitado": int(top),
        "total_dias_con_actividad": len(items),
        "items": items[:top],
    }


@router.get("/stats/correlacion-codigos")
def stats_correlacion_codigos(
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R108 P2: pares de códigos de glosa que aparecen juntos en una factura.

    Cruza ConceptoGlosaRecord (multi-concepto por glosa) para
    detectar patrones de co-ocurrencia: "cuando objetan TA0201,
    también suelen objetar FA0603".

    Útil para:
      - Anticipar argumentación: si veo TA0201, prepararme para
        FA0603 también
      - Detectar bundles típicos de objeción de cada EPS
      - Capacitación: "estos códigos van casi siempre juntos"

    Devuelve top N pares ordenados DESC por co-frecuencia:
      [{"codigo_a": "TA0201", "codigo_b": "FA0603",
        "co_frecuencia": 12, "facturas": ["F001", "F015", ...]}, ...]
    """
    from itertools import combinations

    conceptos = db.query(ConceptoGlosaRecord).all()

    # Agrupar códigos por factura
    por_factura: dict[str, set[str]] = {}
    for c in conceptos:
        if not c.factura or not c.codigo_glosa:
            continue
        por_factura.setdefault(c.factura, set()).add(c.codigo_glosa)

    # Contar pares
    pares: dict[tuple, dict] = {}
    for factura, codigos in por_factura.items():
        if len(codigos) < 2:
            continue
        codigos_lista = sorted(codigos)
        for a, b in combinations(codigos_lista, 2):
            key = (a, b)
            if key not in pares:
                pares[key] = {"co_frecuencia": 0, "facturas": []}
            pares[key]["co_frecuencia"] += 1
            if len(pares[key]["facturas"]) < 5:  # cap muestra
                pares[key]["facturas"].append(factura)

    items = [
        {
            "codigo_a": a,
            "codigo_b": b,
            "co_frecuencia": v["co_frecuencia"],
            "facturas_muestra": v["facturas"],
        }
        for (a, b), v in pares.items()
    ]
    items.sort(key=lambda x: x["co_frecuencia"], reverse=True)

    return {
        "total_pares_unicos": len(items),
        "top_solicitado": int(top),
        "items": items[:top],
    }


@router.get("/stats/cohorte-mensual")
def stats_cohorte_mensual(
    meses: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R103 P1: cohort analysis de glosas por mes de creación.

    Para cada cohorte mensual (mes en que se creó la glosa),
    calcula qué % se cerraron dentro de 30/60/90 días.

    Útil para identificar si el equipo mejora con el tiempo:
      - ¿Cohorte de marzo cierra al 30d más rápido que cohorte de enero?
      - ¿Empeoró tras nuevo proceso/cambio?

    Devuelve serie ordenada por mes con métricas de retención
    (% aún sin cerrar a los 30/60/90 días).

    Estados cerrados: ACEPTADA, LEVANTADA, ARCHIVADA, CONCILIADA.
    """
    from datetime import timedelta, timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    corte = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= corte)
        .all()
    )

    cohortes: dict[str, list] = {}
    for g in glosas:
        creado = g.creado_en
        if not creado:
            continue
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        key = creado.strftime("%Y-%m")
        cohortes.setdefault(key, []).append(g)

    serie = []
    for key in sorted(cohortes.keys()):
        cohorte = cohortes[key]
        total = len(cohorte)
        cerradas_30 = 0
        cerradas_60 = 0
        cerradas_90 = 0
        for g in cohorte:
            estado = (g.estado or "").upper()
            if estado not in ESTADOS_CERRADOS:
                continue
            if not (g.fecha_decision_eps and g.creado_en):
                continue
            dec = g.fecha_decision_eps
            cre = g.creado_en
            if dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)
            if cre.tzinfo is None:
                cre = cre.replace(tzinfo=timezone.utc)
            dias = (dec - cre).days
            if dias <= 30:
                cerradas_30 += 1
            if dias <= 60:
                cerradas_60 += 1
            if dias <= 90:
                cerradas_90 += 1

        serie.append({
            "cohorte": key,
            "total_glosas": total,
            "cierre_30d_pct": round(100 * cerradas_30 / total, 2),
            "cierre_60d_pct": round(100 * cerradas_60 / total, 2),
            "cierre_90d_pct": round(100 * cerradas_90 / total, 2),
        })

    return {
        "ventana_meses": int(meses),
        "total_cohortes": len(serie),
        "serie": serie,
    }


@router.get("/stats/proyeccion-recuperacion")
def stats_proyeccion_recuperacion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R102 P2: forecast simple de recuperación esperada.

    Usa la tasa histórica de recuperación (sobre glosas cerradas)
    aplicada al valor pendiente como predicción gruesa de cuánto
    podría recuperar el HUS si el patrón histórico se mantiene.

    Útil para:
      - Cash flow planning del coordinador
      - Reporte ejecutivo con proyección
      - Detectar cuándo la pendiente excede capacidad histórica

    NO es ML — es una regla simple. Para una proyección más
    sofisticada usar /analitica-predictiva.

    Devuelve:
      - tasa_historica_recuperacion_pct
      - valor_pendiente_total (no cerradas)
      - proyeccion_recuperable
      - intervalo: {"min": ..., "max": ...} con ±20% de margen
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()

    cerradas_obj = 0.0
    cerradas_rec = 0.0
    pendientes_obj = 0.0
    pendientes_count = 0

    for g in todas:
        estado = (g.estado or "").upper()
        v_obj = float(g.valor_objetado or 0)
        if estado in ESTADOS_CERRADOS:
            cerradas_obj += v_obj
            cerradas_rec += float(g.valor_recuperado or 0)
        else:
            pendientes_obj += v_obj
            pendientes_count += 1

    tasa = (
        round(100 * cerradas_rec / cerradas_obj, 2)
        if cerradas_obj else 0.0
    )

    proyeccion = pendientes_obj * (tasa / 100)

    # Intervalo ±20% como margen de incertidumbre
    margen = proyeccion * 0.20

    return {
        "tasa_historica_recuperacion_pct": tasa,
        "valor_pendiente_total": int(pendientes_obj),
        "glosas_pendientes": pendientes_count,
        "proyeccion_recuperable": int(proyeccion),
        "intervalo": {
            "min": int(max(0, proyeccion - margen)),
            "max": int(proyeccion + margen),
            "margen_pct": 20,
        },
        "basado_en_glosas_cerradas": int(cerradas_obj > 0),
    }


@router.get("/stats/dashboard-snapshot")
def stats_dashboard_snapshot(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R109 P2: snapshot agregado para dashboard ejecutivo (single-call).

    Combina las métricas más usadas del dashboard en un solo
    round-trip. Reduce latencia y simplifica el frontend.

    Devuelve:
      - kpis: counts globales (total, abiertas, cerradas, vencidas,
              criticas, en_tiempo)
      - economico: valor_objetado_total, valor_recuperado_total,
                   tasa_recuperacion_pct
      - resoluciones: tasa_levantamiento_pct
      - sla: % en tiempo, criticas, vencidas

    Si necesitas más detalle, usar endpoints específicos
    (cumplimiento-sla, comparativa-eps, recuperacion-mensual).
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ESTADOS_DECIDIDOS = ESTADOS_CERRADOS | {"RATIFICADA"}

    todas = db.query(GlosaRecord).all()
    total = len(todas)

    abiertas = 0
    cerradas = 0
    vencidas = 0
    criticas = 0
    en_tiempo = 0
    levantadas = 0
    decididas = 0
    valor_obj_total = 0.0
    valor_rec_total = 0.0

    for g in todas:
        estado = (g.estado or "").upper()
        v_obj = float(g.valor_objetado or 0)
        valor_obj_total += v_obj
        valor_rec_total += float(g.valor_recuperado or 0)

        if estado in ESTADOS_CERRADOS:
            cerradas += 1
        else:
            abiertas += 1
            dr = g.dias_restantes if g.dias_restantes is not None else 0
            if dr < 0:
                vencidas += 1
            elif dr <= 3:
                criticas += 1
            else:
                en_tiempo += 1

        if estado in ESTADOS_DECIDIDOS:
            decididas += 1
            if estado == "LEVANTADA":
                levantadas += 1

    return {
        "kpis": {
            "total": total,
            "abiertas": abiertas,
            "cerradas": cerradas,
            "vencidas": vencidas,
            "criticas": criticas,
            "en_tiempo": en_tiempo,
        },
        "economico": {
            "valor_objetado_total": int(valor_obj_total),
            "valor_recuperado_total": int(valor_rec_total),
            "tasa_recuperacion_pct": (
                round(100 * valor_rec_total / valor_obj_total, 2)
                if valor_obj_total else 0.0
            ),
        },
        "resoluciones": {
            "decididas": decididas,
            "levantadas": levantadas,
            "tasa_levantamiento_pct": (
                round(100 * levantadas / decididas, 2)
                if decididas else 0.0
            ),
        },
        "sla": {
            "vencidas": vencidas,
            "criticas": criticas,
            "en_tiempo": en_tiempo,
            "pct_en_tiempo": (
                round(100 * en_tiempo / abiertas, 2)
                if abiertas else 0.0
            ),
        },
        "generado_en": ahora_utc().isoformat(),
    }


@router.get("/stats/cuellos-botella")
def stats_cuellos_botella(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R135 P1: detecta etapas con tiempo elevado (cuellos de botella).

    Diferente a /stats/abandono-por-etapa (% abiertas): aquí mide
    TIEMPO promedio que las glosas pasan en cada estado antes
    de transicionar al siguiente, usando transiciones del
    audit_log (campo='estado').

    Útil para identificar:
      - Estados que requieren más recursos
      - Procesos lentos que necesitan optimización
      - Comparación HUS vs SLA de la Resolución

    Devuelve por estado:
      - count_glosas_con_transicion
      - tiempo_promedio_dias
      - tiempo_mediano_dias
    Ordenado DESC por tiempo_promedio.
    """
    from datetime import timezone

    from app.models.db import AuditLogRecord

    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.campo == "estado")
        .filter(AuditLogRecord.timestamp.isnot(None))
        .filter(AuditLogRecord.registro_id.isnot(None))
        .order_by(
            AuditLogRecord.registro_id.asc(),
            AuditLogRecord.timestamp.asc(),
        )
        .all()
    )

    # Agrupar por glosa, ordenadas cronológicamente.
    # Por cada evento guardamos (timestamp, valor_nuevo). El estado en
    # el que está la glosa entre evento[i] y evento[i+1] es valor_nuevo
    # del evento[i] (el "destino" de esa transición).
    por_glosa: dict[int, list] = {}
    for e in eventos:
        ts = e.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        por_glosa.setdefault(e.registro_id, []).append(
            (ts, e.valor_nuevo)
        )

    # Para cada glosa, tiempo entre transiciones consecutivas
    por_estado: dict[str, list[float]] = {}
    for transiciones in por_glosa.values():
        transiciones.sort(key=lambda x: x[0])
        for i in range(1, len(transiciones)):
            ts_prev, estado_durante = transiciones[i - 1]
            ts_act, _ = transiciones[i]
            if not estado_durante or not ts_prev or not ts_act:
                continue
            dias = (ts_act - ts_prev).total_seconds() / 86400
            if dias < 0:
                continue
            por_estado.setdefault(estado_durante, []).append(dias)

    items = []
    for estado, tiempos in por_estado.items():
        tiempos.sort()
        n = len(tiempos)
        promedio = sum(tiempos) / n
        if n % 2 == 0:
            mediano = (tiempos[n // 2 - 1] + tiempos[n // 2]) / 2
        else:
            mediano = tiempos[n // 2]
        items.append({
            "estado": estado,
            "count_glosas_con_transicion": n,
            "tiempo_promedio_dias": round(promedio, 2),
            "tiempo_mediano_dias": round(mediano, 2),
        })
    items.sort(
        key=lambda x: x["tiempo_promedio_dias"], reverse=True,
    )

    return {
        "total_estados_con_data": len(items),
        "items": items,
    }


@router.get("/stats/abandono-por-etapa")
def stats_abandono_por_etapa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R106 P1: identifica en qué etapa se "atascan" más las glosas.

    Útil para detectar bottlenecks del proceso:
      - ¿Las glosas mueren en RESPUESTA_PRIMERA?
      - ¿Hay un cuello en RATIFICACION?

    Devuelve por etapa:
      - total_glosas
      - abiertas (no cerradas)
      - tasa_abandono_pct (% que sigue en esta etapa)
      - tiempo_promedio_dias (cuánto llevan en la etapa, basado en
        días desde creación)

    Ordenado DESC por tasa_abandono_pct.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()
    ahora = ahora_utc()

    por_etapa: dict[str, dict] = {}
    for g in todas:
        etapa = (g.etapa or "SIN_ETAPA").strip() or "SIN_ETAPA"
        if etapa not in por_etapa:
            por_etapa[etapa] = {
                "total": 0, "abiertas": 0, "tiempos": [],
            }
        b = por_etapa[etapa]
        b["total"] += 1

        estado = (g.estado or "").upper()
        if estado not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
            if g.creado_en:
                creado = g.creado_en
                if creado.tzinfo is None:
                    creado = creado.replace(tzinfo=timezone.utc)
                b["tiempos"].append((ahora - creado).days)

    items = []
    for etapa, b in por_etapa.items():
        tiempo_prom = (
            round(sum(b["tiempos"]) / len(b["tiempos"]), 2)
            if b["tiempos"] else 0.0
        )
        tasa = (
            round(100 * b["abiertas"] / b["total"], 2)
            if b["total"] else 0.0
        )
        items.append({
            "etapa": etapa,
            "total_glosas": b["total"],
            "abiertas": b["abiertas"],
            "tasa_abandono_pct": tasa,
            "tiempo_promedio_dias_abiertas": tiempo_prom,
        })

    items.sort(key=lambda x: x["tasa_abandono_pct"], reverse=True)

    return {
        "total_etapas": len(items),
        "items": items,
    }


@router.get("/stats/exito-por-codigo-respuesta")
def stats_exito_por_codigo_respuesta(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R116 P1: efectividad de cada código de respuesta IPS.

    Códigos de respuesta (Resolución 2284/2023):
      - RE9901: Acepta glosa
      - RE9502: Rechaza por concepto técnico
      - RE9801: Rechaza por concepto jurídico
      - RE9702: No procede
      - RE9602: Aclaración

    Útil para entender cuáles argumentos funcionan mejor:
      "Cuando respondemos con RE9502, ¿qué % de glosas se levantan?"

    Devuelve por código_respuesta:
      - total_usado
      - levantadas (HUS ganó)
      - tasa_levantamiento_pct
    """
    glosas = db.query(GlosaRecord).all()

    por_codigo: dict[str, dict] = {}
    for g in glosas:
        cod = g.codigo_respuesta
        if not cod:
            continue
        if cod not in por_codigo:
            por_codigo[cod] = {
                "total": 0, "levantadas": 0, "decididas": 0,
            }
        b = por_codigo[cod]
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

    items = []
    for cod, b in por_codigo.items():
        tasa = (
            round(100 * b["levantadas"] / b["decididas"], 2)
            if b["decididas"] else 0.0
        )
        items.append({
            "codigo_respuesta": cod,
            "total_usado": b["total"],
            "decididas": b["decididas"],
            "levantadas": b["levantadas"],
            "tasa_levantamiento_pct": tasa,
        })
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "total_codigos_respuesta_unicos": len(items),
        "items": items,
    }


@router.get("/stats/codigos-mas-objetados")
def stats_codigos_mas_objetados(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R102 P1: ranking de códigos de glosa por frecuencia y valor.

    Útil para:
      - Identificar dónde se "pelean" más las EPS
        (¿es siempre TA0201 por insumos?)
      - Decidir capacitación enfocada (top códigos = más impacto)
      - Análisis de cumplimiento Resolución 2284/2023

    Devuelve top N códigos ordenados DESC por frecuencia, con:
      - codigo
      - frecuencia (count de glosas con ese código)
      - valor_objetado_total
      - tasa_levantamiento_pct (LEVANTADAS / decididas)
      - eps_principales (top 3 EPS que más usan ese código)
    """
    todas = db.query(GlosaRecord).all()

    por_codigo: dict[str, dict] = {}
    for g in todas:
        cod = g.codigo_glosa
        if not cod:
            continue
        if cod not in por_codigo:
            por_codigo[cod] = {
                "freq": 0, "valor": 0.0,
                "decididas": 0, "levantadas": 0,
                "por_eps": {},
            }
        b = por_codigo[cod]
        b["freq"] += 1
        b["valor"] += float(g.valor_objetado or 0)

        estado = (g.estado or "").upper()
        if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

        if g.eps:
            b["por_eps"][g.eps] = b["por_eps"].get(g.eps, 0) + 1

    items = []
    for cod, b in por_codigo.items():
        tasa = (
            round(100 * b["levantadas"] / b["decididas"], 2)
            if b["decididas"] else 0.0
        )
        eps_top3 = sorted(
            b["por_eps"].items(), key=lambda x: x[1], reverse=True,
        )[:3]
        items.append({
            "codigo": cod,
            "frecuencia": b["freq"],
            "valor_objetado_total": int(b["valor"]),
            "tasa_levantamiento_pct": tasa,
            "eps_principales": [
                {"eps": e, "veces": n} for e, n in eps_top3
            ],
        })
    items.sort(key=lambda x: x["frecuencia"], reverse=True)

    return {
        "total_codigos_unicos": len(items),
        "top_solicitado": int(top),
        "items": items[:top],
    }


@router.get("/stats/eficiencia-gestor")
def stats_eficiencia_gestor(
    min_glosas: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R98 P1: métricas de eficiencia por gestor.

    Diferente a /admin/distribucion-cargas (que cuenta workload):
    este mide DESEMPEÑO — qué tan bien defiende cada gestor las
    glosas asignadas.

    Para gestores con >= min_glosas cerradas, devuelve:
      - total_cerradas
      - tasa_levantamiento_pct (LEVANTADAS / cerradas, mejor=más alto)
      - valor_recuperado_total
      - valor_objetado_total
      - tasa_recuperacion_pct (recuperado / objetado)
      - tiempo_promedio_resolucion_dias

    Ordenado DESC por tasa_levantamiento_pct.
    Útil para identificar best practices y oportunidades de mentoría.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    por_gestor: dict[str, dict] = {}
    for g in cerradas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        if gestor not in por_gestor:
            por_gestor[gestor] = {
                "total": 0, "levantadas": 0,
                "valor_recuperado": 0.0, "valor_objetado": 0.0,
                "tiempos": [],
            }
        b = por_gestor[gestor]
        b["total"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["levantadas"] += 1
        b["valor_recuperado"] += float(g.valor_recuperado or 0)
        b["valor_objetado"] += float(g.valor_objetado or 0)

        if g.fecha_decision_eps and g.creado_en:
            delta = (g.fecha_decision_eps - g.creado_en).total_seconds() / 86400
            b["tiempos"].append(delta)

    items = []
    for gestor, b in por_gestor.items():
        if b["total"] < min_glosas:
            continue
        tasa_lev = round(100 * b["levantadas"] / b["total"], 2)
        tasa_rec = (
            round(100 * b["valor_recuperado"] / b["valor_objetado"], 2)
            if b["valor_objetado"] else 0.0
        )
        tiempo_prom = (
            round(sum(b["tiempos"]) / len(b["tiempos"]), 2)
            if b["tiempos"] else 0.0
        )
        items.append({
            "gestor": gestor,
            "total_cerradas": b["total"],
            "levantadas": b["levantadas"],
            "tasa_levantamiento_pct": tasa_lev,
            "valor_recuperado_total": int(b["valor_recuperado"]),
            "valor_objetado_total": int(b["valor_objetado"]),
            "tasa_recuperacion_pct": tasa_rec,
            "tiempo_promedio_resolucion_dias": tiempo_prom,
        })
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_gestores_evaluados": len(items),
        "items": items,
    }


@router.get("/stats/recuperacion-mensual")
def stats_recuperacion_mensual(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R97 P2: serie temporal mensual de valor recuperado.

    Útil para reporte ejecutivo: ¿cuánto plata le hemos sacado a las
    EPS este año? Tendencia mes-a-mes para detectar mejoras /
    degradaciones del proceso de defensa de glosas.

    Calcula valor_recuperado por mes basado en fecha_decision_eps
    (cuándo se cerró el ciclo). Solo cuenta glosas cerradas con
    valor_recuperado > 0.

    Devuelve serie ordenada ascendentemente:
      [{"mes": "2026-01", "recuperado": 1500000, "glosas_cerradas": 12,
        "valor_objetado_total": 5000000, "tasa_recuperacion_pct": 30.0}, ...]
    """
    from datetime import timedelta, timezone

    corte = ahora_utc() - timedelta(days=int(meses) * 31)

    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(GlosaRecord.fecha_decision_eps >= corte)
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in cerradas:
        fecha = g.fecha_decision_eps
        if fecha and fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        if not fecha:
            continue
        key = fecha.strftime("%Y-%m")
        if key not in por_mes:
            por_mes[key] = {
                "recuperado": 0.0,
                "glosas_cerradas": 0,
                "valor_objetado_total": 0.0,
            }
        b = por_mes[key]
        b["glosas_cerradas"] += 1
        b["recuperado"] += float(g.valor_recuperado or 0)
        b["valor_objetado_total"] += float(g.valor_objetado or 0)

    serie = []
    for key in sorted(por_mes.keys()):
        b = por_mes[key]
        tasa = (
            round(100 * b["recuperado"] / b["valor_objetado_total"], 2)
            if b["valor_objetado_total"] else 0.0
        )
        serie.append({
            "mes": key,
            "recuperado": int(b["recuperado"]),
            "glosas_cerradas": b["glosas_cerradas"],
            "valor_objetado_total": int(b["valor_objetado_total"]),
            "tasa_recuperacion_pct": tasa,
        })

    return {
        "ventana_meses": int(meses),
        "total_recuperado": sum(s["recuperado"] for s in serie),
        "serie": serie,
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


@router.get("/{glosa_id}/checklist")
def checklist_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R96 P1: checklist de progreso de una glosa en el ciclo.

    Útil para que el auditor vea de un vistazo qué falta en cada
    glosa. Cada item dice si está completo + si es opcional.

    Devuelve:
      {
        "glosa_id": int,
        "items": [
          {"id": "texto_original", "descripcion": "...",
           "completado": true, "opcional": false},
          ...
        ],
        "total_items": int,
        "completados": int,
        "obligatorios_pendientes": int,
        "porcentaje_avance": float (0-100, solo obligatorios)
      }
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    items = [
        {
            "id": "texto_original",
            "descripcion": "Texto de glosa original capturado",
            "completado": bool(glosa.texto_glosa_original),
            "opcional": False,
        },
        {
            "id": "factura",
            "descripcion": "Factura asociada (no N/A)",
            "completado": bool(glosa.factura and glosa.factura != "N/A"),
            "opcional": False,
        },
        {
            "id": "valor_objetado",
            "descripcion": "Valor objetado registrado",
            "completado": bool(glosa.valor_objetado and glosa.valor_objetado > 0),
            "opcional": False,
        },
        {
            "id": "dictamen",
            "descripcion": "Dictamen HUS generado",
            "completado": bool(glosa.dictamen and len(glosa.dictamen) > 50),
            "opcional": False,
        },
        {
            "id": "gestor",
            "descripcion": "Gestor asignado",
            "completado": bool(glosa.gestor_nombre),
            "opcional": True,
        },
        {
            "id": "auditor",
            "descripcion": "Auditor asignado",
            "completado": bool(glosa.auditor_email),
            "opcional": True,
        },
        {
            "id": "fecha_recepcion",
            "descripcion": "Fecha de recepción registrada",
            "completado": bool(glosa.fecha_recepcion),
            "opcional": True,
        },
        {
            "id": "respuesta_eps",
            "descripcion": "Decisión EPS registrada",
            "completado": bool(glosa.decision_eps),
            "opcional": False,
        },
        {
            "id": "cierre",
            "descripcion": "Glosa cerrada",
            "completado": (glosa.estado or "").upper() in ESTADOS_CERRADOS,
            "opcional": False,
        },
    ]

    total = len(items)
    completados = sum(1 for it in items if it["completado"])
    obligatorios = [it for it in items if not it["opcional"]]
    obl_completados = sum(1 for it in obligatorios if it["completado"])
    obl_pendientes = len(obligatorios) - obl_completados
    pct = (
        round(100 * obl_completados / len(obligatorios), 2)
        if obligatorios else 0.0
    )

    return {
        "glosa_id": glosa_id,
        "items": items,
        "total_items": total,
        "completados": completados,
        "obligatorios_pendientes": obl_pendientes,
        "porcentaje_avance": pct,
    }


@router.get("/{glosa_id}/contexto-completo")
def contexto_completo_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R94 P2: contexto agregado para vista detalle de una glosa.

    Combina en un solo round-trip:
      - glosa (campos clave)
      - sla (estado_sla, color_semaforo, dias_restantes)
      - audit_resumen (total_cambios, ultimo_cambio_en, usuarios)
      - relacionadas_count (sin items para no inflar — usar
        /relacionadas para detalle)

    Reduce N+1 calls del frontend al cargar la ficha de una glosa.
    Si el frontend necesita detalle de cada sección, puede invocar
    los endpoints individuales.
    """
    from datetime import timezone

    from app.models.db import AuditLogRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    # ─── SLA ─────────────────────────────────────────────────
    ahora = ahora_utc()
    estado = (glosa.estado or "").upper()
    cerrada = estado in ESTADOS_CERRADOS

    venc = glosa.fecha_vencimiento
    if venc and venc.tzinfo is None:
        venc = venc.replace(tzinfo=timezone.utc)
    dec = glosa.fecha_decision_eps
    if dec and dec.tzinfo is None:
        dec = dec.replace(tzinfo=timezone.utc)

    if not venc:
        estado_sla, color = "SIN_VENCIMIENTO", "GRIS"
    elif cerrada:
        if dec and dec <= venc:
            estado_sla, color = "CERRADA_A_TIEMPO", "VERDE"
        else:
            estado_sla, color = "CERRADA_TARDE", "NEGRO"
    else:
        dr = glosa.dias_restantes if glosa.dias_restantes is not None else 0
        if dr < 0:
            estado_sla, color = "VENCIDA", "ROJO"
        elif dr <= 3:
            estado_sla, color = "CRITICA", "AMARILLO"
        else:
            estado_sla, color = "EN_TIEMPO", "VERDE"

    # ─── Audit resumen ──────────────────────────────────────
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.registro_id == glosa_id)
        .all()
    )
    timestamps = [e.timestamp for e in eventos if e.timestamp]
    usuarios = sorted({e.usuario_email for e in eventos if e.usuario_email})

    # ─── Relacionadas (counts only) ─────────────────────────
    rel_factura = 0
    if glosa.factura and glosa.factura != "N/A":
        rel_factura = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.factura == glosa.factura)
            .filter(GlosaRecord.id != glosa_id)
            .count()
        )
    rel_paciente = 0
    if glosa.paciente:
        rel_paciente = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.paciente == glosa.paciente)
            .filter(GlosaRecord.id != glosa_id)
            .count()
        )
    rel_patron = 0
    if glosa.codigo_glosa and glosa.eps:
        rel_patron = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.codigo_glosa == glosa.codigo_glosa)
            .filter(GlosaRecord.eps == glosa.eps)
            .filter(GlosaRecord.id != glosa_id)
            .count()
        )

    return {
        "glosa": {
            "id": glosa.id,
            "creado_en": (
                glosa.creado_en.isoformat() if glosa.creado_en else None
            ),
            "eps": glosa.eps,
            "paciente": glosa.paciente,
            "factura": glosa.factura,
            "codigo_glosa": glosa.codigo_glosa,
            "valor_objetado": float(glosa.valor_objetado or 0),
            "valor_recuperado": float(glosa.valor_recuperado or 0),
            "estado": glosa.estado,
            "etapa": glosa.etapa,
            "decision_eps": glosa.decision_eps,
        },
        "sla": {
            "estado_sla": estado_sla,
            "color_semaforo": color,
            "cerrada": cerrada,
            "dias_restantes": glosa.dias_restantes,
            "fecha_vencimiento": venc.isoformat() if venc else None,
        },
        "audit_resumen": {
            "total_cambios": len(eventos),
            "ultimo_cambio_en": (
                max(timestamps).isoformat() if timestamps else None
            ),
            "usuarios_que_intervinieron": usuarios,
        },
        "relacionadas_count": {
            "misma_factura": rel_factura,
            "mismo_paciente": rel_paciente,
            "mismo_codigo_y_eps": rel_patron,
        },
    }


@router.get("/{glosa_id}/score-prioridad")
def score_prioridad_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R112 P2: score individual de prioridad para UNA glosa.

    Misma fórmula que /admin/glosas-prioritarias (R112 P1) pero
    aplicada a una sola glosa, con desglose detallado de cada
    componente.

    Útil para mostrar en la ficha de la glosa: "esta glosa tiene
    score 130 porque está vencida + alto valor".

    Devuelve:
      - score_total
      - desglose: {[{componente, peso, razon}]}
      - banner_recomendado: "URGENTE" | "ALTA" | "MEDIA" | "BAJA"
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    estado = (glosa.estado or "").upper()
    if estado in ESTADOS_CERRADOS:
        return {
            "glosa_id": glosa_id,
            "score_total": 0,
            "desglose": [],
            "banner_recomendado": "INFO",
            "razon": "Glosa cerrada — sin score de prioridad.",
        }

    desglose = []
    score = 0

    dr = glosa.dias_restantes if glosa.dias_restantes is not None else 0
    if dr < 0:
        desglose.append({"componente": "vencimiento", "peso": 100,
                         "razon": f"vencida hace {abs(dr)}d"})
        score += 100
    elif dr <= 3:
        desglose.append({"componente": "vencimiento", "peso": 50,
                         "razon": f"crítica ({dr}d restantes)"})
        score += 50
    elif dr <= 7:
        desglose.append({"componente": "vencimiento", "peso": 20,
                         "razon": f"próxima ({dr}d restantes)"})
        score += 20

    v_obj = float(glosa.valor_objetado or 0)
    if v_obj > 10_000_000:
        desglose.append({"componente": "valor", "peso": 30,
                         "razon": f"alto valor ({int(v_obj):,} COP)"})
        score += 30
    elif v_obj > 1_000_000:
        desglose.append({"componente": "valor", "peso": 15,
                         "razon": f"valor medio ({int(v_obj):,} COP)"})
        score += 15

    if not glosa.dictamen or len(glosa.dictamen) < 50:
        desglose.append({"componente": "dictamen", "peso": 25,
                         "razon": "sin dictamen generado"})
        score += 25

    if not glosa.gestor_nombre:
        desglose.append({"componente": "asignacion", "peso": 15,
                         "razon": "sin gestor asignado"})
        score += 15

    if score >= 100:
        banner = "URGENTE"
    elif score >= 50:
        banner = "ALTA"
    elif score >= 25:
        banner = "MEDIA"
    elif score > 0:
        banner = "BAJA"
    else:
        banner = "INFO"

    return {
        "glosa_id": glosa_id,
        "estado": glosa.estado,
        "score_total": score,
        "desglose": desglose,
        "banner_recomendado": banner,
    }


@router.get("/{glosa_id}/versiones-resumen")
def versiones_resumen_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R129 P1: resumen del versionado del dictamen de una glosa.

    Cada refinación, regeneración o restauración del dictamen
    crea un DictamenVersionRecord. Este endpoint resume:
      - Cuántas versiones tiene el dictamen
      - Quién lo refinó cuándo
      - Cuántas veces se REFINO (con instrucción humana) vs
        REGENERO (con IA pura)

    Útil para entender la "historia editorial" de un dictamen
    sin tener que ir versión por versión.

    Devuelve:
      - total_versiones
      - por_accion: mapa {CREAR, REFINAR, REGENERAR, RESTAURAR}
      - autores_distintos
      - primera_version_en / ultima_version_en
      - ultima_accion
    """
    from datetime import timezone

    from app.models.db import DictamenVersionRecord

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    versiones = (
        db.query(DictamenVersionRecord)
        .filter(DictamenVersionRecord.glosa_id == glosa_id)
        .order_by(DictamenVersionRecord.creado_en.asc())
        .all()
    )

    if not versiones:
        return {
            "glosa_id": glosa_id,
            "total_versiones": 0,
            "por_accion": {},
            "autores_distintos": [],
            "primera_version_en": None,
            "ultima_version_en": None,
            "ultima_accion": None,
        }

    por_accion: dict[str, int] = {}
    autores: set[str] = set()
    for v in versiones:
        if v.accion:
            por_accion[v.accion] = por_accion.get(v.accion, 0) + 1
        if v.autor_email:
            autores.add(v.autor_email)

    primera = versiones[0].creado_en
    ultima = versiones[-1].creado_en
    if primera and primera.tzinfo is None:
        primera = primera.replace(tzinfo=timezone.utc)
    if ultima and ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)

    return {
        "glosa_id": glosa_id,
        "total_versiones": len(versiones),
        "por_accion": por_accion,
        "autores_distintos": sorted(autores),
        "primera_version_en": primera.isoformat() if primera else None,
        "ultima_version_en": ultima.isoformat() if ultima else None,
        "ultima_accion": versiones[-1].accion,
    }


@router.get("/{glosa_id}/dialogo-bilateral")
def dialogo_bilateral(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R138 P1: narrativa cronológica del intercambio HUS↔EPS.

    Construye un diálogo entre las partes basado en datos reales:
      1. EPS objeta: codigo_glosa + valor_objetado
      2. HUS responde: dictamen + codigo_respuesta
      3. EPS decide: decision_eps + valor_recuperado
      4. (Opcional) Conciliación bilateral

    Cada paso: {actor, fecha, mensaje, estado_resultante}.

    Útil para mostrar la "historia" completa de la glosa de
    forma legible para no-técnicos (legal, gerencia).
    """
    from datetime import timezone

    from app.models.db import ConciliacionRecord

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    pasos = []

    # 1) EPS objeta
    if glosa.creado_en:
        ts = glosa.creado_en
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        valor = float(glosa.valor_objetado or 0)
        pasos.append({
            "actor": "EPS",
            "fecha": ts.isoformat(),
            "mensaje": (
                f"Objeta con código {glosa.codigo_glosa or '?'} por "
                f"${int(valor):,} COP"
            ),
            "estado_resultante": "RADICADA",
        })

    # 2) HUS responde
    if glosa.dictamen and len(glosa.dictamen) > 50:
        pasos.append({
            "actor": "HUS",
            "fecha": None,
            "mensaje": (
                f"Responde con código {glosa.codigo_respuesta or '?'} "
                f"y dictamen técnico-jurídico "
                f"({len(glosa.dictamen)} chars)"
            ),
            "estado_resultante": glosa.estado or "RESPONDIDA",
        })

    # 3) EPS decide
    if glosa.decision_eps:
        ts = glosa.fecha_decision_eps
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        v_rec = float(glosa.valor_recuperado or 0)
        pasos.append({
            "actor": "EPS",
            "fecha": ts.isoformat() if ts else None,
            "mensaje": (
                f"Decisión: {glosa.decision_eps}. "
                f"Recuperado: ${int(v_rec):,} COP"
            ),
            "estado_resultante": glosa.estado or "?",
        })

    # 4) Conciliación si existe
    conciliaciones = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.glosa_id == glosa_id)
        .order_by(ConciliacionRecord.creado_en.asc())
        .all()
    )
    for c in conciliaciones:
        ts = c.fecha_audiencia or c.creado_en
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        v_conc = float(c.valor_conciliado or 0)
        pasos.append({
            "actor": "BILATERAL",
            "fecha": ts.isoformat() if ts else None,
            "mensaje": (
                f"Conciliación: {c.resultado or 'pendiente'}. "
                f"Valor conciliado: ${int(v_conc):,} COP"
            ),
            "estado_resultante": c.estado_bilateral or "?",
        })

    return {
        "glosa_id": glosa_id,
        "estado_actual": glosa.estado,
        "total_pasos": len(pasos),
        "dialogo": pasos,
    }


@router.get("/{glosa_id}/historial-workflow")
def historial_workflow(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R134 P2: historial específico de cambios de workflow_state.

    Filtra audit_log a los eventos de cambio de workflow_state /
    estado para una glosa, mostrando solo las transiciones de
    máquina de estados (no toda la auditoría).

    Útil para responder: "¿cómo evolucionó el estado de esta glosa?"

    Devuelve transiciones ordenadas ASC por timestamp:
      [{"timestamp", "usuario", "valor_anterior", "valor_nuevo",
        "accion"}]
    """
    from app.models.db import AuditLogRecord

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.registro_id == glosa_id)
        .filter(AuditLogRecord.campo.in_(["estado", "workflow_state"]))
        .order_by(AuditLogRecord.timestamp.asc())
        .all()
    )

    items = [
        {
            "timestamp": (
                e.timestamp.isoformat() if e.timestamp else None
            ),
            "usuario": e.usuario_email,
            "campo": e.campo,
            "valor_anterior": e.valor_anterior,
            "valor_nuevo": e.valor_nuevo,
            "accion": e.accion,
        }
        for e in eventos
    ]

    return {
        "glosa_id": glosa_id,
        "estado_actual": glosa.estado,
        "workflow_state_actual": glosa.workflow_state,
        "total_transiciones": len(items),
        "items": items,
    }


@router.get("/{glosa_id}/comparar-con-promedio")
def comparar_con_promedio(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R133 P2: compara una glosa con el promedio histórico de su
    cohorte (mismo EPS + mismo codigo_glosa).

    Útil para responder: "¿es esta glosa típica o atípica?"

    Si el valor objetado es 5x el promedio del cohorte, podría
    indicar:
      - Caso extraordinario que requiere atención senior
      - Posible error de captura de datos
      - Glosa fraccionada (mala práctica EPS)

    Devuelve:
      - glosa: valor_objetado, dias_restantes
      - cohorte: count, valor_promedio, valor_mediano,
                 tasa_levantamiento_pct
      - posicion: percentil aproximado del valor en el cohorte
      - flags: {valor_atipico, vencimiento_atipico}
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    if not glosa.eps or not glosa.codigo_glosa:
        return {
            "glosa_id": glosa_id,
            "razon_no_evaluable": "Glosa sin EPS o codigo_glosa",
        }

    cohorte = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == glosa.eps)
        .filter(GlosaRecord.codigo_glosa == glosa.codigo_glosa)
        .filter(GlosaRecord.id != glosa_id)
        .all()
    )

    if not cohorte:
        return {
            "glosa_id": glosa_id,
            "razon_no_evaluable": (
                f"No hay otras glosas con eps={glosa.eps} y "
                f"codigo={glosa.codigo_glosa}"
            ),
        }

    valores = sorted(float(g.valor_objetado or 0) for g in cohorte)
    n = len(valores)
    valor_glosa = float(glosa.valor_objetado or 0)

    valor_promedio = sum(valores) / n
    if n % 2 == 0:
        valor_mediano = (valores[n // 2 - 1] + valores[n // 2]) / 2
    else:
        valor_mediano = valores[n // 2]

    decididas = [
        g for g in cohorte
        if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA",
                                         "RATIFICADA"}
    ]
    levantadas = [
        g for g in decididas
        if (g.estado or "").upper() == "LEVANTADA"
    ]
    tasa = (
        round(100 * len(levantadas) / len(decididas), 2)
        if decididas else 0.0
    )

    # Percentil aproximado
    menores = sum(1 for v in valores if v < valor_glosa)
    percentil = round(100 * menores / n, 1)

    valor_atipico = (
        valor_glosa > 3 * valor_promedio
        or valor_glosa < valor_promedio / 5
    ) if valor_promedio > 0 else False

    return {
        "glosa_id": glosa_id,
        "glosa": {
            "eps": glosa.eps,
            "codigo_glosa": glosa.codigo_glosa,
            "valor_objetado": valor_glosa,
            "dias_restantes": glosa.dias_restantes,
        },
        "cohorte": {
            "count": n,
            "valor_promedio": round(valor_promedio, 2),
            "valor_mediano": round(valor_mediano, 2),
            "tasa_levantamiento_pct": tasa,
        },
        "posicion": {
            "percentil_valor": percentil,
            "ratio_vs_promedio": round(
                valor_glosa / valor_promedio, 2,
            ) if valor_promedio else None,
        },
        "flags": {
            "valor_atipico": valor_atipico,
        },
    }


@router.get("/{glosa_id}/recomendaciones")
def recomendaciones_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R111 P1: sugerencias heurísticas de próximas acciones.

    Sin IA — usa reglas determinísticas basadas en el estado actual
    de la glosa. Útil para guiar al auditor: "¿qué debería hacer
    a continuación?".

    Devuelve lista de recomendaciones con prioridad y descripción:
      - HIGH: vencidas, sin dictamen
      - MEDIUM: sin gestor, datos incompletos
      - LOW: enriquecer información

    Cada recomendación tiene: {prioridad, accion, descripcion, endpoint?}
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    estado = (glosa.estado or "").upper()
    cerrada = estado in ESTADOS_CERRADOS
    recomendaciones = []

    if cerrada:
        recomendaciones.append({
            "prioridad": "INFO",
            "accion": "ARCHIVAR",
            "descripcion": "Glosa cerrada — sin acciones pendientes.",
        })
        return {
            "glosa_id": glosa_id,
            "total": len(recomendaciones),
            "items": recomendaciones,
        }

    # ── Reglas críticas ───────────────────────────────────────
    dr = glosa.dias_restantes if glosa.dias_restantes is not None else 0
    if dr < 0:
        recomendaciones.append({
            "prioridad": "HIGH",
            "accion": "ATENDER_VENCIDA",
            "descripcion": (
                f"Glosa vencida hace {abs(dr)} días. Responder "
                "urgentemente para evitar ratificación automática."
            ),
        })
    elif dr <= 3:
        recomendaciones.append({
            "prioridad": "HIGH",
            "accion": "ATENDER_CRITICA",
            "descripcion": f"Faltan {dr} días para vencimiento.",
        })

    if not glosa.dictamen or len(glosa.dictamen) < 50:
        recomendaciones.append({
            "prioridad": "HIGH",
            "accion": "GENERAR_DICTAMEN",
            "descripcion": "No hay dictamen generado. Usar IA para crear uno.",
            "endpoint": f"POST /glosas/{glosa_id}/refinar",
        })

    # ── Reglas medias ─────────────────────────────────────────
    if not glosa.gestor_nombre:
        recomendaciones.append({
            "prioridad": "MEDIUM",
            "accion": "ASIGNAR_GESTOR",
            "descripcion": "Glosa sin gestor asignado.",
            "endpoint": f"PATCH /glosas/{glosa_id}/asignar",
        })

    if not glosa.factura or glosa.factura == "N/A":
        recomendaciones.append({
            "prioridad": "MEDIUM",
            "accion": "COMPLETAR_FACTURA",
            "descripcion": "Falta número de factura.",
        })

    if not glosa.texto_glosa_original:
        recomendaciones.append({
            "prioridad": "MEDIUM",
            "accion": "CAPTURAR_TEXTO_ORIGINAL",
            "descripcion": "Sin texto original — el contexto IA será débil.",
        })

    # ── Reglas bajas ──────────────────────────────────────────
    if not glosa.cups_servicio:
        recomendaciones.append({
            "prioridad": "LOW",
            "accion": "AGREGAR_CUPS",
            "descripcion": "Sin código CUPS — útil para validación normativa.",
        })

    if not recomendaciones:
        recomendaciones.append({
            "prioridad": "INFO",
            "accion": "MONITOREAR",
            "descripcion": "Glosa en buen estado — esperar respuesta EPS.",
        })

    return {
        "glosa_id": glosa_id,
        "estado_actual": glosa.estado,
        "total": len(recomendaciones),
        "items": recomendaciones,
    }


@router.get("/{glosa_id}/resumen-pdf")
def resumen_pdf_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R119 P1: PDF de 1 página con resumen ejecutivo de una glosa.

    Útil para imprimir/adjuntar a expedientes físicos sin tener
    que armar el PDF manualmente.

    Contenido:
      - Header con logo HUS (texto)
      - Datos clave: id, EPS, factura, valor objetado
      - Estado y SLA
      - Resumen del dictamen (primeros 1500 chars)
      - Footer con fecha de generación + auditor

    Usa reportlab (ya instalado en el stack).
    """
    import io

    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(
        f"<b>RESUMEN GLOSA #{glosa_id} — HUS</b>",
        styles["Title"],
    ))
    story.append(Spacer(1, 0.2 * inch))

    # Datos clave (tabla)
    valor_obj = float(glosa.valor_objetado or 0)
    valor_rec = float(glosa.valor_recuperado or 0)
    datos = [
        ["EPS", glosa.eps or "-"],
        ["Factura", glosa.factura or "-"],
        ["Código glosa", glosa.codigo_glosa or "-"],
        ["Valor objetado", f"${valor_obj:,.0f} COP"],
        ["Valor recuperado", f"${valor_rec:,.0f} COP"],
        ["Estado", glosa.estado or "-"],
        ["Etapa", glosa.etapa or "-"],
        ["Días restantes", str(glosa.dias_restantes or "-")],
        ["Gestor", glosa.gestor_nombre or "-"],
        ["Decisión EPS", glosa.decision_eps or "Pendiente"],
    ]
    tabla = Table(datos, colWidths=[2.2 * inch, 4.5 * inch])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#0B5D8A")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(tabla)
    story.append(Spacer(1, 0.3 * inch))

    # Resumen del dictamen
    if glosa.dictamen:
        story.append(Paragraph("<b>Dictamen HUS:</b>", styles["Heading3"]))
        # Limpiar HTML básico
        import re
        texto_dict = re.sub(r"<[^>]+>", " ", glosa.dictamen)
        texto_dict = re.sub(r"\s+", " ", texto_dict).strip()
        story.append(Paragraph(texto_dict[:1500], styles["BodyText"]))
        story.append(Spacer(1, 0.2 * inch))

    # Footer
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(
        f"<i>Generado por {current_user.email} el {ahora_utc().strftime('%Y-%m-%d %H:%M UTC')}</i>",
        styles["BodyText"],
    ))

    doc.build(story)
    buf.seek(0)

    fname = f"resumen-glosa-{glosa_id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{glosa_id}/exportar-evidencia.zip")
def exportar_evidencia_zip(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R108 P1: paquete ZIP completo de evidencia para una glosa.

    Complementa /paquete-evidencia.json (solo datos) con un ZIP
    multi-archivo listo para entregar a legal/compliance:

      glosa.json      — todos los datos de la glosa
      dictamen.txt    — texto plano del dictamen
      audit_log.json  — eventos de auditoría asociados
      README.txt      — explicación del contenido

    StreamingResponse con el ZIP en memoria (suficiente para
    glosas individuales — el límite es ~10MB típicamente).
    """
    import io
    import json
    import zipfile

    from fastapi.responses import StreamingResponse

    from app.models.db import AuditLogRecord

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    # Datos de la glosa (campos públicos)
    glosa_dict = {
        "id": glosa.id,
        "creado_en": glosa.creado_en.isoformat() if glosa.creado_en else None,
        "eps": glosa.eps,
        "paciente": glosa.paciente,
        "factura": glosa.factura,
        "codigo_glosa": glosa.codigo_glosa,
        "valor_objetado": float(glosa.valor_objetado or 0),
        "valor_recuperado": float(glosa.valor_recuperado or 0),
        "etapa": glosa.etapa,
        "estado": glosa.estado,
        "decision_eps": glosa.decision_eps,
        "gestor_nombre": glosa.gestor_nombre,
        "auditor_email": glosa.auditor_email,
        "fecha_vencimiento": (
            glosa.fecha_vencimiento.isoformat()
            if glosa.fecha_vencimiento else None
        ),
    }

    # Audit log
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.registro_id == glosa_id)
        .order_by(AuditLogRecord.timestamp.asc())
        .all()
    )
    audit_list = [
        {
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "usuario_email": e.usuario_email,
            "accion": e.accion,
            "campo": e.campo,
            "valor_anterior": e.valor_anterior,
            "valor_nuevo": e.valor_nuevo,
        }
        for e in eventos
    ]

    readme = (
        f"PAQUETE DE EVIDENCIA — GLOSA #{glosa_id}\n"
        f"Generado: {ahora_utc().isoformat()}\n"
        f"Generado por: {current_user.email}\n\n"
        "Contenido:\n"
        "  - glosa.json: datos estructurados completos\n"
        "  - dictamen.txt: texto del dictamen HUS (si existe)\n"
        "  - audit_log.json: histórico de eventos sobre esta glosa\n"
    )

    # Construir ZIP en memoria
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("glosa.json",
                    json.dumps(glosa_dict, ensure_ascii=False, indent=2))
        zf.writestr("audit_log.json",
                    json.dumps(audit_list, ensure_ascii=False, indent=2))
        if glosa.dictamen:
            zf.writestr("dictamen.txt", glosa.dictamen)

    buf.seek(0)
    fname = f"evidencia-glosa-{glosa_id}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{glosa_id}/duplicados-potenciales")
def duplicados_potenciales_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R99 P2: detecta posibles duplicados de UNA glosa específica.

    Diferente a /glosas/duplicados (que escanea TODAS): este se enfoca
    en una glosa puntual. Útil para validar al crear/clonar:
      "¿Estoy generando un duplicado?"

    Heurística (DEBE coincidir TODO):
      - Misma EPS
      - Misma factura (no N/A)
      - Mismo codigo_glosa
      - Diferencia de valor_objetado < 1% (tolera redondeos)

    Excluye la propia glosa. Devuelve hasta 20 candidatas con
    score de similitud (0-100).
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    # Sin factura "real" no hay forma de identificar duplicado fiable
    if not glosa.factura or glosa.factura == "N/A":
        return {
            "glosa_id": glosa_id,
            "razon_no_evaluable": "factura ausente o N/A",
            "candidatos": [],
        }

    candidatos = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.id != glosa_id)
        .filter(GlosaRecord.eps == glosa.eps)
        .filter(GlosaRecord.factura == glosa.factura)
        .filter(GlosaRecord.codigo_glosa == glosa.codigo_glosa)
        .limit(20)
        .all()
    )

    valor_origen = float(glosa.valor_objetado or 0)
    items = []
    for c in candidatos:
        v = float(c.valor_objetado or 0)
        # Score: 100 si valores idénticos, decrece según diferencia relativa
        if valor_origen == 0 and v == 0:
            score = 100.0
        elif valor_origen == 0 or v == 0:
            score = 50.0  # Uno tiene valor y otro no — sospechoso pero menos
        else:
            diff_pct = abs(v - valor_origen) / max(v, valor_origen) * 100
            score = round(max(0, 100 - diff_pct), 2)

        items.append({
            "id": c.id,
            "creado_en": (
                c.creado_en.isoformat() if c.creado_en else None
            ),
            "valor_objetado": v,
            "estado": c.estado,
            "score_similitud": score,
        })

    items.sort(key=lambda x: x["score_similitud"], reverse=True)

    return {
        "glosa_id": glosa_id,
        "total_candidatos": len(items),
        "candidatos": items,
    }


@router.get("/{glosa_id}/relacionadas")
def glosas_relacionadas(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R93 P2: glosas relacionadas a una glosa dada.

    Identifica vínculos por:
      - Misma factura: glosas que objetan distintos servicios de
        la misma factura (suelen ir/venir juntas en el ciclo)
      - Mismo paciente: histórico clínico-administrativo del paciente
      - Mismo código_glosa + misma EPS: patrones repetidos

    Devuelve cada grupo limitado a 10 entradas para no inflar
    el response. Ordenado DESC por creado_en (más reciente primero).
    """
    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    def _serializar(g):
        return {
            "id": g.id,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
            "eps": g.eps,
            "factura": g.factura,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": float(g.valor_objetado or 0),
            "estado": g.estado,
            "etapa": g.etapa,
        }

    LIMITE = 10

    # Misma factura (excluyendo la glosa actual)
    misma_factura = []
    if glosa.factura and glosa.factura != "N/A":
        misma_factura = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.factura == glosa.factura)
            .filter(GlosaRecord.id != glosa_id)
            .order_by(GlosaRecord.creado_en.desc())
            .limit(LIMITE)
            .all()
        )

    # Mismo paciente
    mismo_paciente = []
    if glosa.paciente:
        mismo_paciente = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.paciente == glosa.paciente)
            .filter(GlosaRecord.id != glosa_id)
            .order_by(GlosaRecord.creado_en.desc())
            .limit(LIMITE)
            .all()
        )

    # Mismo código + misma EPS (patrones repetidos)
    mismo_patron = []
    if glosa.codigo_glosa and glosa.eps:
        mismo_patron = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.codigo_glosa == glosa.codigo_glosa)
            .filter(GlosaRecord.eps == glosa.eps)
            .filter(GlosaRecord.id != glosa_id)
            .order_by(GlosaRecord.creado_en.desc())
            .limit(LIMITE)
            .all()
        )

    return {
        "glosa_id": glosa_id,
        "misma_factura": [_serializar(g) for g in misma_factura],
        "mismo_paciente": [_serializar(g) for g in mismo_paciente],
        "mismo_codigo_y_eps": [_serializar(g) for g in mismo_patron],
        "limite_por_grupo": LIMITE,
    }


@router.get("/{glosa_id}/diff/{otra_id}")
def diff_entre_glosas(
    glosa_id: int,
    otra_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R93 P1: comparativa lado-a-lado entre dos glosas.

    Útil para:
      - Identificar casos similares con mismo código pero distinto
        outcome (¿por qué SANITAS aceptó la TA0201 de Pedro pero
        ratificó la de Juan?)
      - Entrenar a auditores nuevos mostrando ejemplos contrastantes
      - Investigar inconsistencias en decisiones EPS

    Devuelve los campos clave de ambas glosas y un set de campos
    "diferentes" para destacar.
    """
    repo = GlosaRepository(db)
    g1 = repo.obtener_por_id(glosa_id)
    if not g1:
        raise HTTPException(404, f"Glosa {glosa_id} no encontrada")
    g2 = repo.obtener_por_id(otra_id)
    if not g2:
        raise HTTPException(404, f"Glosa {otra_id} no encontrada")

    CAMPOS = [
        "eps", "paciente", "factura", "codigo_glosa",
        "valor_objetado", "valor_aceptado", "valor_recuperado",
        "etapa", "estado", "decision_eps",
        "gestor_nombre", "cups_servicio", "codigo_respuesta",
    ]

    snapshot1 = {c: getattr(g1, c, None) for c in CAMPOS}
    snapshot2 = {c: getattr(g2, c, None) for c in CAMPOS}

    diferentes = sorted(
        c for c in CAMPOS
        if snapshot1.get(c) != snapshot2.get(c)
    )

    # Casteamos floats para serialización JSON consistente
    def _normalizar(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if isinstance(v, (int, float)) and v is not None:
                out[k] = float(v) if isinstance(v, float) else v
            else:
                out[k] = v if v is not None else None
        return out

    return {
        "glosa_a": {"id": g1.id, **_normalizar(snapshot1)},
        "glosa_b": {"id": g2.id, **_normalizar(snapshot2)},
        "campos_diferentes": diferentes,
        "total_diferencias": len(diferentes),
    }


@router.get("/{glosa_id}/sla")
def sla_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R92 P2: estado SLA detallado de una glosa individual.

    Útil para el panel de detalle: muestra de un vistazo si esta
    glosa específica está cumpliendo el SLA o está en riesgo.

    Devuelve:
      - estado_sla: VENCIDA | CRITICA | EN_TIEMPO |
                    CERRADA_A_TIEMPO | CERRADA_TARDE | SIN_VENCIMIENTO
      - color_semaforo: ROJO | AMARILLO | VERDE | NEGRO | GRIS
      - dias_restantes
      - dias_transcurridos (desde creación)
      - fecha_creado / fecha_vencimiento / fecha_decision_eps
      - tiempo_total_resolucion_dias (si cerrada)
      - cerrada (bool)
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosa = GlosaRepository(db).obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    ahora = ahora_utc()
    estado = (glosa.estado or "").upper()
    cerrada = estado in ESTADOS_CERRADOS

    creado = glosa.creado_en
    if creado and creado.tzinfo is None:
        creado = creado.replace(tzinfo=timezone.utc)
    venc = glosa.fecha_vencimiento
    if venc and venc.tzinfo is None:
        venc = venc.replace(tzinfo=timezone.utc)
    dec = glosa.fecha_decision_eps
    if dec and dec.tzinfo is None:
        dec = dec.replace(tzinfo=timezone.utc)

    dias_transcurridos = (
        (ahora - creado).days if creado else None
    )

    tiempo_total = None
    if cerrada and dec and creado:
        tiempo_total = (dec - creado).days

    # Determinar estado_sla
    if not venc:
        estado_sla = "SIN_VENCIMIENTO"
        color = "GRIS"
    elif cerrada:
        if dec and dec <= venc:
            estado_sla = "CERRADA_A_TIEMPO"
            color = "VERDE"
        else:
            estado_sla = "CERRADA_TARDE"
            color = "NEGRO"
    else:
        dr = glosa.dias_restantes if glosa.dias_restantes is not None else 0
        if dr < 0:
            estado_sla = "VENCIDA"
            color = "ROJO"
        elif dr <= 3:
            estado_sla = "CRITICA"
            color = "AMARILLO"
        else:
            estado_sla = "EN_TIEMPO"
            color = "VERDE"

    return {
        "glosa_id": glosa_id,
        "estado": glosa.estado,
        "cerrada": cerrada,
        "estado_sla": estado_sla,
        "color_semaforo": color,
        "dias_restantes": glosa.dias_restantes,
        "dias_transcurridos": dias_transcurridos,
        "fecha_creado": creado.isoformat() if creado else None,
        "fecha_vencimiento": venc.isoformat() if venc else None,
        "fecha_decision_eps": dec.isoformat() if dec else None,
        "tiempo_total_resolucion_dias": tiempo_total,
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
