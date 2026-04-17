import re
import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db, SessionLocal
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.audit_repository import AuditRepository
from app.services.glosa_service import GlosaService
from app.core.config import get_settings
from app.core.logging_utils import set_request_id, logger
from app.api.deps import get_usuario_actual, get_auditor_o_superior, get_coordinador_o_admin
from app.models.db import UsuarioRecord, GlosaRecord

router = APIRouter(prefix="/glosas", tags=["glosas"])


class GlosaFilaInput(BaseModel):
    fila: int
    texto: str
    eps: str
    fecha_radicacion: Optional[str] = None
    fecha_recepcion: Optional[str] = None


class ImportacionMasivaRequest(BaseModel):
    eps: str
    texto_excel: str
    fecha_radicacion: Optional[str] = None
    fecha_recepcion: Optional[str] = None


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
    repo = GlosaRepository(db)
    glosas = repo.listar(limit=limit, eps=eps)
    items = []
    for g in glosas:
        obs_texto = _limpiar_observacion(g.dictamen)
        items.append({
            "id": g.id,
            "fecha": g.creado_en.isoformat() if g.creado_en else None,
            "fecha_recepcion": g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
            "fecha_entrega": g.fecha_entrega.isoformat() if g.fecha_entrega else None,
            "entidad": g.eps,
            "eps": g.eps,  # alias para compatibilidad
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

    items = []
    for g in resultado["items"]:
        obs_texto = _limpiar_observacion(g.dictamen)
        items.append({
            "id": g.id,
            "eps": g.eps,
            "entidad": g.eps,
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
    from app.main import _extraer_motivo_glosa

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
        "Código Respuesta", "Observación", "Etapa", "Estado",
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
        obs = _limpiar_observacion(g.dictamen)
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
            obs[:500] if obs else "",
            g.etapa or "",
            g.estado or "",
            g.workflow_state or "",
            g.prioridad or "",
            g.dias_restantes if g.dias_restantes is not None else "",
            g.fecha_recepcion.strftime("%Y-%m-%d") if g.fecha_recepcion else "",
            g.fecha_entrega.strftime("%Y-%m-%d") if g.fecha_entrega else "",
        ])

    # Ajuste de anchos
    widths = [6, 18, 22, 28, 14, 12, 26, 10, 32, 14, 14, 14, 12, 60, 14, 14, 14, 10, 10, 14, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

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
        glosas = repo.listar_por_gestor(current_user.email, current_user.nombre)
    return [
        {
            "id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "numero_radicado": g.numero_radicado,
            "consecutivo_dgh": g.consecutivo_dgh,
            "gestor_nombre": g.gestor_nombre,
            "valor_objetado": g.valor_objetado,
            "estado": g.estado,
            "prioridad": g.prioridad,
            "dias_restantes": g.dias_restantes,
            "fecha_vencimiento": g.fecha_vencimiento.isoformat() if g.fecha_vencimiento else None,
            "fecha_entrega": g.fecha_entrega.isoformat() if g.fecha_entrega else None,
            "fecha_radicacion_factura": g.fecha_radicacion_factura.isoformat() if g.fecha_radicacion_factura else None,
            "fecha_documento_dgh": g.fecha_documento_dgh.isoformat() if g.fecha_documento_dgh else None,
            "fecha_recepcion": g.fecha_recepcion.isoformat() if g.fecha_recepcion else None,
            "radicado_info": g.radicado_info,
            "referencia": g.referencia,
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
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Elimina permanentemente una glosa del historial."""
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    db.delete(glosa)
    db.commit()
    logger.info(f"Glosa eliminada ID={glosa_id} por {current_user.email}")
    return {"message": f"Glosa {glosa_id} eliminada"}


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
        nueva_nota = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} {current_user.email} {actual}->{nuevo}] {data.comentario}"
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
    glosa.fecha_decision_eps = datetime.utcnow()
    glosa.valor_recuperado = data.valor_recuperado
    if data.observacion_eps:
        glosa.observacion_eps = data.observacion_eps
    if decision in ("LEVANTADA", "ACEPTADA", "RATIFICADA"):
        glosa.estado = decision
    db.commit()
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


def _parsear_filas_excel(texto: str) -> list[dict]:
    """
    Parsea el texto pegado de Excel y extrae cada fila como diccionario.
    Formato esperado: EPS | Factura | Valor | Codigo | Descripcion | CUPS | Motivo
    """
    filas = []
    lineas = texto.strip().split('\n')
    
    for i, linea in enumerate(lineas):
        linea = linea.strip()
        if not linea:
            continue
        
        partes = [p.strip() for p in linea.split('\t')]
        
        if len(partes) >= 4:
            fila_data = {
                'fila': i + 1,
                'eps': partes[0] if len(partes) > 0 else '',
                'factura': partes[1] if len(partes) > 1 else '',
                'valor': partes[2] if len(partes) > 2 else '',
                'codigo': partes[3] if len(partes) > 3 else '',
                'descripcion': partes[4] if len(partes) > 4 else '',
                'cups': partes[5] if len(partes) > 5 else '',
                'motivo': partes[6] if len(partes) > 6 else '',
            }
            
            if fila_data['codigo'] and len(fila_data['codigo']) >= 2:
                filas.append(fila_data)
    
    return filas


async def _procesar_fila_en_background(fila_data: dict, servicio_id: str, req_id: str, eps_formulario: str):
    """Procesa una fila individual en segundo plano."""
    db = SessionLocal()
    try:
        cfg = get_settings()
        service = GlosaService(groq_api_key=cfg.groq_api_key, anthropic_api_key=cfg.anthropic_api_key)
        
        from app.models.schemas import GlosaInput
        
        contrato_repo = ContratoRepository(db)
        contratos = contrato_repo.como_dict()
        
        texto_glosa = f"{fila_data['codigo']} {fila_data['valor']} {fila_data['descripcion']} {fila_data['cups']} {fila_data['motivo']}"
        
        data = GlosaInput(
            eps=eps_formulario,
            etapa="RESPUESTA A GLOSA",
            tabla_excel=texto_glosa,
            numero_factura=fila_data.get('factura'),
            numero_radicado=servicio_id,
        )
        
        resultado = await service.analizar(data, "", contratos)
        
        repo = GlosaRepository(db)
        repo.crear(
            eps=eps_formulario,
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
    Recibe: eps, texto_excel (con tabs), fechas opcionales
    Procesa en segundo plano y retorna el ID del lote para seguimiento.
    """
    req_id = uuid.uuid4().hex[:8]
    logger.info(f"[{req_id}] Importación masiva iniciada | eps={request.eps} | filas detectadas: ?")
    
    filas = _parsear_filas_excel(request.texto_excel)
    
    if not filas:
        raise HTTPException(status_code=400, detail="No se detectaron filas válidas en el texto")
    
    servicio_id = f"BATCH-{req_id}"
    
    contrato_repo = ContratoRepository(db)
    # Se consulta contratos solo para validar que la BD es accesible
    # (no es requerido pasarlos al background task porque se obtienen allí).

    for fila_data in filas:
        background_tasks.add_task(
            _procesar_fila_en_background,
            fila_data,
            servicio_id,
            req_id,
            request.eps
        )
    
    logger.info(f"[{req_id}] {len(filas)} filas enviadas a procesamiento | batch_id={servicio_id}")
    
    return {
        "message": f"{len(filas)} glosas procesándose en segundo plano",
        "batch_id": servicio_id,
        "total_filas": len(filas),
        "eps": request.eps,
        "estado": "PROCESANDO"
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
    try:
        enviados = await enviar_resumen_importacion_recepcion(resumen_dict)
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
