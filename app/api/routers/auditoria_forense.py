"""Auditoría forense por glosa (Ronda 11 incluida en Ronda 10).

Consolida en un único endpoint toda la trazabilidad de una glosa:
  - Creación (quién, cuándo, desde qué IP)
  - Asignaciones de auditor
  - Análisis IA (modelo usado, tokens caché/real)
  - Refinamientos (con texto antes/después)
  - Decisión EPS (levantada/ratificada + fecha + valor)
  - Exportaciones PDF/Excel
  - Cambios de workflow
  - Comentarios internos
  - Firma digital (si se aplicó)

Output: timeline cronológico listo para mostrar como <ol> en UI forense.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import (
    AuditLogRecord, DictamenVersionRecord, GlosaRecord,
    ComentarioGlosaRecord, UsuarioRecord,
)

router = APIRouter(prefix="/auditoria-forense", tags=["auditoria-forense"])


@router.get("/{glosa_id}/timeline")
def timeline_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Timeline forense completo de una glosa, cronológico."""
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    eventos: list[dict] = []

    # 1) Creación
    eventos.append({
        "tipo": "creacion",
        "titulo": "📝 Glosa creada",
        "timestamp": glosa.creado_en.isoformat() if glosa.creado_en else None,
        "detalle": f"Código {glosa.codigo_glosa} · EPS {glosa.eps} · ${int(glosa.valor_objetado or 0):,}",
        "actor": glosa.auditor_email or "sistema",
    })

    # 2) Versiones del dictamen (cada refinar deja una versión)
    try:
        versiones = (
            db.query(DictamenVersionRecord)
            .filter(DictamenVersionRecord.glosa_id == glosa_id)
            .order_by(DictamenVersionRecord.creado_en.asc())
            .all()
        )
        for v in versiones:
            eventos.append({
                "tipo": "version",
                "titulo": f"📝 {v.accion or 'Actualización'} del dictamen",
                "timestamp": v.creado_en.isoformat() if v.creado_en else None,
                "detalle": (v.mensaje_refinar or "")[:200],
                "actor": v.autor_email or "—",
                "version_id": v.id,
            })
    except Exception:
        pass

    # 3) Comentarios del equipo
    try:
        comentarios = (
            db.query(ComentarioGlosaRecord)
            .filter(ComentarioGlosaRecord.glosa_id == glosa_id)
            .order_by(ComentarioGlosaRecord.creado_en.asc())
            .all()
        )
        for c in comentarios:
            eventos.append({
                "tipo": "comentario",
                "titulo": "💬 Comentario interno",
                "timestamp": c.creado_en.isoformat() if c.creado_en else None,
                "detalle": (c.texto or "")[:200],
                "actor": c.autor_email or "—",
            })
    except Exception:
        pass

    # 4) Registros de audit_log referentes a esta glosa
    try:
        audits = (
            db.query(AuditLogRecord)
            .filter(AuditLogRecord.tabla == "glosas")
            .filter(AuditLogRecord.registro_id == glosa_id)
            .order_by(AuditLogRecord.timestamp.asc())
            .all()
        )
        iconos = {
            "DECISION_EPS": "⚖️",
            "ASIGNAR": "👤",
            "WORKFLOW": "🔄",
            "REFINAR_IA": "🧠",
            "ANALIZAR_GLOSA": "📊",
            "EXPORTAR_PDF": "📄",
            "EXPORTAR_XLSX": "📤",
            "FIRMAR": "🖊️",
        }
        for a in audits:
            icon = iconos.get(a.accion, "•")
            eventos.append({
                "tipo": "audit",
                "accion": a.accion,
                "titulo": f"{icon} {a.accion.replace('_', ' ').title()}",
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "detalle": (a.detalle or "")[:300],
                "actor": a.usuario_email or "—",
                "ip": a.ip or "",
                "cambio": {
                    "campo": a.campo,
                    "anterior": a.valor_anterior,
                    "nuevo": a.valor_nuevo,
                } if a.campo else None,
            })
    except Exception:
        pass

    # 5) Decisión final EPS (si se registró)
    if glosa.decision_eps:
        eventos.append({
            "tipo": "decision_eps",
            "titulo": f"🏁 Decisión EPS: {glosa.decision_eps}",
            "timestamp": glosa.fecha_decision_eps.isoformat() if glosa.fecha_decision_eps else None,
            "detalle": f"Recuperado: ${int(glosa.valor_recuperado or 0):,}. {glosa.observacion_eps or ''}",
            "actor": "EPS",
        })

    # Ordenar cronológicamente (timestamp None al final)
    def _ts(e):
        t = e.get("timestamp") or ""
        return (t == "", t)
    eventos.sort(key=_ts)

    # Estadísticas
    stats = {
        "total_eventos": len(eventos),
        "refinamientos": sum(1 for e in eventos if e["tipo"] == "version"),
        "comentarios": sum(1 for e in eventos if e["tipo"] == "comentario"),
        "cambios_workflow": sum(
            1 for e in eventos
            if e["tipo"] == "audit" and e.get("accion") == "WORKFLOW"
        ),
    }

    return {
        "glosa_id": glosa_id,
        "codigo_glosa": glosa.codigo_glosa,
        "eps": glosa.eps,
        "estado_actual": glosa.estado,
        "decision_eps": glosa.decision_eps,
        "valor_objetado": float(glosa.valor_objetado or 0),
        "valor_recuperado": float(glosa.valor_recuperado or 0),
        "stats": stats,
        "timeline": eventos,
    }


@router.post("/{glosa_id}/firmar")
def firmar_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Firma digital del dictamen para radicación (Ronda 10).

    Genera hash SHA-256 + firma HMAC con SECRET_KEY. Queda registrado
    en audit_log. El PDF puede incluir los datos de firma en el footer.
    """
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    if not glosa.dictamen:
        raise HTTPException(400, "La glosa no tiene dictamen para firmar")

    from app.services.firma_digital import firmar_dictamen
    from app.repositories.audit_repository import AuditRepository

    firma = firmar_dictamen(
        texto_dictamen=glosa.dictamen,
        firmante_email=current_user.email,
        glosa_id=glosa_id,
    )
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="FIRMAR",
        tabla="glosas",
        registro_id=glosa_id,
        campo="dictamen_firma",
        valor_nuevo=firma["firma"][:60] + "…",
        detalle=f"Firma digital generada. Hash: {firma['hash'][:16]}...",
    )
    return {
        "mensaje": "Dictamen firmado digitalmente",
        "glosa_id": glosa_id,
        **firma,
    }


@router.get("/{glosa_id}/prediccion-ratificacion")
def predecir_ratificacion_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Predice si la EPS ratificará esta glosa (Ronda 12).

    Usa regresión logística manual sobre 13 features del dominio
    (histórico EPS, tipo glosa, calidad dictamen, plantilla, match
    perfecto, régimen, valor objetado, ratificaciones previas...).
    """
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    from app.services.ml_ratificacion import predecir_ratificacion
    return predecir_ratificacion(db, glosa)


@router.get("/buscar-por-ip")
def buscar_por_ip(
    ip: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R131 P1: busca eventos audit asociados a una IP específica.

    Útil para investigar incidentes de seguridad:
      "¿Qué hizo la IP 192.168.1.50 ayer?"

    También sirve para identificar accesos sospechosos:
      - IP de país no esperado
      - Múltiples usuarios desde misma IP
      - Acciones masivas desde una sola IP

    Devuelve eventos ordenados DESC por timestamp con:
      - usuarios_distintos: lista emails que usaron esa IP
      - acciones_distintas: tipos de acciones realizadas
      - rango temporal (primer/ultimo evento)
    """
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.ip == ip)
        .order_by(AuditLogRecord.timestamp.desc())
        .limit(int(limit))
        .all()
    )

    usuarios = sorted({
        e.usuario_email for e in eventos if e.usuario_email
    })
    acciones = sorted({
        e.accion for e in eventos if e.accion
    })

    return {
        "ip_buscada": ip,
        "total_eventos": len(eventos),
        "usuarios_distintos": usuarios,
        "acciones_distintas": acciones,
        "primer_evento_en": (
            eventos[-1].timestamp.isoformat()
            if eventos and eventos[-1].timestamp else None
        ),
        "ultimo_evento_en": (
            eventos[0].timestamp.isoformat()
            if eventos and eventos[0].timestamp else None
        ),
        "items": [
            {
                "id": e.id,
                "timestamp": (
                    e.timestamp.isoformat() if e.timestamp else None
                ),
                "usuario_email": e.usuario_email,
                "accion": e.accion,
                "tabla": e.tabla,
                "registro_id": e.registro_id,
            }
            for e in eventos
        ],
    }


@router.post("/verificar-firma")
def verificar(
    payload: dict,
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Verifica una firma digital. Body: {hash, firma, firmante, glosa_id, timestamp}."""
    from app.services.firma_digital import verificar_firma
    try:
        ok = verificar_firma(
            hash_esperado=payload.get("hash", ""),
            firma_base64=payload.get("firma", ""),
            firmante=payload.get("firmante", ""),
            glosa_id=int(payload.get("glosa_id", 0)),
            timestamp=payload.get("timestamp", ""),
        )
    except Exception as e:
        raise HTTPException(400, f"Payload inválido: {e}")
    return {"valida": bool(ok)}
