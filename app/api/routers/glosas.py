import re
import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import get_db, SessionLocal
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.audit_repository import AuditRepository
from app.services.glosa_service import GlosaService
from app.services.pdf_service import PdfService
from app.core.config import get_settings
from app.core.logging_utils import set_request_id, get_request_id, logger
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


@router.get("/historial", response_model=list)
def historial(
    limit: int = 50,
    eps:   Optional[str] = None,
    db:    Session        = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosas = repo.listar(limit=limit, eps=eps)
    return [
        {
            "id": g.id,
            "eps": g.eps,
            "paciente": g.paciente,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": g.valor_objetado,
            "valor_aceptado": g.valor_aceptado,
            "etapa": g.etapa,
            "estado": g.estado,
            "dictamen": g.dictamen,
            "dias_restantes": g.dias_restantes,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
        }
        for g in glosas
    ]


@router.get("/historial-paginado")
def historial_paginado(
    page: int = 1,
    per_page: int = Query(20, ge=1, le=100),
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Historial con paginación y filtros"""
    repo = GlosaRepository(db)
    resultado = repo.listar_paginado(page=page, per_page=per_page, eps=eps, estado=estado, search=search)
    
    return {
        "items": [
            {
                "id": g.id,
                "eps": g.eps,
                "paciente": g.paciente,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": g.valor_objetado,
                "valor_aceptado": g.valor_aceptado,
                "etapa": g.etapa,
                "estado": g.estado,
                "dias_restantes": g.dias_restantes,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
            }
            for g in resultado["items"]
        ],
        "total": resultado["total"],
        "page": resultado["page"],
        "per_page": resultado["per_page"],
        "pages": resultado["pages"],
    }


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
    contratos_db = {c.eps: c.detalles or "" for c in contrato_repo.listar()}
    
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
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista las glosas asignadas al usuario actual (por email o nombre de gestor)."""
    repo = GlosaRepository(db)
    glosas = repo.listar_por_gestor(current_user.email)
    return [
        {
            "id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "consecutivo_dgh": g.consecutivo_dgh,
            "gestor_nombre": g.gestor_nombre,
            "valor_objetado": g.valor_objetado,
            "estado": g.estado,
            "prioridad": g.prioridad,
            "dias_restantes": g.dias_restantes,
            "fecha_vencimiento": g.fecha_vencimiento.isoformat() if g.fecha_vencimiento else None,
            "fecha_entrega": g.fecha_entrega.isoformat() if g.fecha_entrega else None,
            "radicado_info": g.radicado_info,
        }
        for g in glosas
    ]


@router.get("/batch/{batch_id}")
def obtener_estado_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Obtiene el estado de un lote de importación."""
    repo = GlosaRepository(db)
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
