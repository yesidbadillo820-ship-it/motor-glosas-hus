"""Operaciones administrativas peligrosas (reset de datos).

Requiere rol SUPER_ADMIN y confirmación explícita para todas las acciones.
Cada operación queda registrada en audit_log para trazabilidad.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.db import (
    UsuarioRecord,
    GlosaRecord,
    ConciliacionRecord,
    AuditLogRecord,
)
from app.api.deps import get_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/admin", tags=["admin"])

# Frase de confirmación obligatoria en el body
CONFIRMACION_REQUERIDA = "CONFIRMAR-BORRADO-TOTAL"


class ResetDatosRequest(BaseModel):
    confirmar: str  # debe ser exactamente CONFIRMACION_REQUERIDA
    borrar_historial: bool = True
    borrar_conciliaciones: bool = True
    borrar_audit_log: bool = False


@router.post("/reset-datos")
def reset_datos(
    data: ResetDatosRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Borra datos transaccionales del sistema dejando intactos:
    - Usuarios
    - Contratos
    - Plantillas

    Solo SUPER_ADMIN. Requiere confirmación explícita en el body.
    """
    if data.confirmar != CONFIRMACION_REQUERIDA:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Para confirmar el borrado debes enviar el campo 'confirmar' con "
                f"el valor exacto: {CONFIRMACION_REQUERIDA}"
            ),
        )

    resumen = {"historial": 0, "conciliaciones": 0, "audit_log": 0}

    try:
        if data.borrar_conciliaciones:
            # Primero conciliaciones (referencian historial por FK)
            resumen["conciliaciones"] = db.query(ConciliacionRecord).delete(synchronize_session=False)

        if data.borrar_historial:
            resumen["historial"] = db.query(GlosaRecord).delete(synchronize_session=False)

        db.commit()

        # Registrar la acción en audit_log ANTES de borrarlo (si aplica)
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="RESET_DATOS",
            tabla="multiple",
            detalle=(
                f"Borrado: historial={resumen['historial']}, "
                f"conciliaciones={resumen['conciliaciones']}, "
                f"audit_log_solicitado={data.borrar_audit_log}"
            ),
        )

        if data.borrar_audit_log:
            # Borramos TODO el audit_log excepto el registro recién creado (el del reset)
            # para mantener al menos la trazabilidad de este mismo reset.
            ultimo = db.query(AuditLogRecord).order_by(AuditLogRecord.id.desc()).first()
            q = db.query(AuditLogRecord)
            if ultimo:
                q = q.filter(AuditLogRecord.id != ultimo.id)
            resumen["audit_log"] = q.delete(synchronize_session=False)
            db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al ejecutar el borrado: {str(e)}",
        )

    return {
        "message": "Datos transaccionales eliminados correctamente",
        "registros_borrados": resumen,
        "preservado": ["usuarios", "contratos", "plantillas"],
        "ejecutado_por": current_user.email,
    }


@router.get("/estadisticas")
def estadisticas_admin(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Cuenta rápida de registros por tabla (útil antes/después de un reset)."""
    return {
        "usuarios": db.query(UsuarioRecord).count(),
        "historial": db.query(GlosaRecord).count(),
        "conciliaciones": db.query(ConciliacionRecord).count(),
        "audit_log": db.query(AuditLogRecord).count(),
    }


@router.post("/pre-analisis")
async def disparar_pre_analisis(
    limite: int = 20,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Dispara manualmente el pre-análisis de glosas pendientes.

    Por defecto corre automáticamente cada día a las 6 AM, pero este
    endpoint permite forzarlo sobre demanda (ej. antes de una capacitación
    para pre-calentar respuestas).
    """
    from app.services.ia_auditora_proactiva import ejecutar_pre_analisis_background
    stats = await ejecutar_pre_analisis_background(limite=limite)
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PRE_ANALISIS_MANUAL",
        tabla="historial",
        detalle=f"stats={stats}",
    )
    return {"ok": True, "stats": stats}


@router.get("/pre-analisis/estado")
def estado_pre_analisis(
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Estado del scheduler de pre-análisis (activo, última ejecución)."""
    from app.services.ia_auditora_proactiva import obtener_estado
    return obtener_estado()


@router.get("/tokens-hoy")
def consumo_tokens_hoy(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Monitor de consumo de IA del día actual (optimización #9).

    Cuenta llamadas al motor que gastan tokens y compara contra las que
    fueron servidas desde caché o plantilla fija. Ideal para detectar
    spikes de consumo en tiempo real durante la capacitación.
    """
    from sqlalchemy import func as _func
    from app.core.tz import ahora_utc
    from app.models.db import AICacheRecord

    ahora = ahora_utc()
    hoy_ini = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

    # Análisis del día que tocaron la IA (crean glosa con modelo_ia)
    glosas_hoy = db.query(GlosaRecord).filter(GlosaRecord.creado_en >= hoy_ini).all()
    total = len(glosas_hoy)
    # Desglose por modelo usado
    desglose: dict[str, int] = {}
    ahorro_tpl = 0       # plantillas fijas (extemp, ratif, aceptadas, match)
    ahorro_cache = 0     # respuestas de caché
    llamadas_ia = 0      # llamadas reales a Groq/Claude
    for g in glosas_hoy:
        mod = (g.modelo_ia or "desconocido").strip()
        desglose[mod] = desglose.get(mod, 0) + 1
        if mod in ("texto_fijo", "plantilla"):
            ahorro_tpl += 1
        elif mod in ("cache", "db-cache"):
            ahorro_cache += 1
        else:
            llamadas_ia += 1

    # Consumo del caché BD del día (cuántas veces se sirvieron respuestas cacheadas)
    try:
        cache_hits_hoy = db.query(_func.sum(AICacheRecord.hit_count)).filter(
            AICacheRecord.ultimo_hit >= hoy_ini
        ).scalar() or 0
        cache_total_entradas = db.query(AICacheRecord).count()
    except Exception:
        cache_hits_hoy = 0
        cache_total_entradas = 0

    # Top usuarios (para detectar abuso)
    from app.models.db import AuditLogRecord
    try:
        top_users_rows = (
            db.query(
                AuditLogRecord.usuario_email,
                _func.count(AuditLogRecord.id).label("n"),
            )
            .filter(AuditLogRecord.timestamp >= hoy_ini)
            .filter(AuditLogRecord.accion.in_(["GENERAR_LOTE", "REFINAR_IA", "ANALIZAR_GLOSA"]))
            .group_by(AuditLogRecord.usuario_email)
            .order_by(_func.count(AuditLogRecord.id).desc())
            .limit(10)
            .all()
        )
        top_users = [{"email": e, "acciones": int(n)} for e, n in top_users_rows]
    except Exception:
        top_users = []

    return {
        "fecha": ahora.isoformat(),
        "glosas_analizadas_hoy": total,
        "llamadas_ia_reales": llamadas_ia,
        "ahorro_por_plantilla": ahorro_tpl,
        "ahorro_por_cache": ahorro_cache,
        "pct_ahorro": round(100 * (ahorro_tpl + ahorro_cache) / total, 1) if total else 0.0,
        "desglose_por_modelo": desglose,
        "cache_bd_hits_hoy": int(cache_hits_hoy or 0),
        "cache_bd_entradas_totales": int(cache_total_entradas or 0),
        "top_usuarios_hoy": top_users,
    }


@router.post("/enviar-alertas-vencimiento")
async def enviar_alertas_vencimiento(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Dispara el envío de correos masivos con glosas próximas a vencer
    o vencidas a todos los gestores configurados en ALERTAS_EMAIL.
    Solo SUPER_ADMIN."""
    from app.services.email_service import enviar_alertas_vencimiento_masivo
    try:
        resumen = await enviar_alertas_vencimiento_masivo(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ENVIAR_ALERTAS",
        tabla="historial",
        detalle=f"Destinatarios={resumen.get('destinatarios',0)} Enviados={resumen.get('correos_enviados',0)} Glosas={resumen.get('glosas_alertadas',0)}",
    )
    return resumen


@router.post("/backfill-historial")
def backfill_historial(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Rellena los campos nuevos (cups_servicio, servicio_descripcion,
    concepto_glosa, codigo_respuesta, texto_glosa_original) en glosas
    antiguas que fueron creadas antes de que existieran esas columnas.

    Solo toca glosas con al menos UN campo nuevo vacío. No modifica el
    dictamen ni los valores monetarios. Solo SUPER_ADMIN.
    """
    import re
    from app.main import _concepto_glosa, _extraer_cups_servicio

    # Query: glosas con al menos un campo nuevo en NULL
    glosas = db.query(GlosaRecord).filter(
        (GlosaRecord.concepto_glosa.is_(None)) |
        (GlosaRecord.codigo_respuesta.is_(None)) |
        (GlosaRecord.cups_servicio.is_(None)) |
        (GlosaRecord.servicio_descripcion.is_(None))
    ).all()

    actualizadas = 0
    for g in glosas:
        cambios = False

        # 1. Concepto por código (siempre derivable si hay código)
        if not g.concepto_glosa and g.codigo_glosa:
            g.concepto_glosa = _concepto_glosa(g.codigo_glosa)
            cambios = True

        # 2. CUPS y servicio desde el texto_glosa_original o desde el dictamen
        if (not g.cups_servicio or not g.servicio_descripcion):
            fuente = g.texto_glosa_original or ""
            if not fuente and g.dictamen:
                # Del dictamen HTML quitamos tags y tomamos texto
                fuente = re.sub(r"<[^>]+>", " ", g.dictamen)
            cups, servicio = _extraer_cups_servicio(fuente, "")
            if not g.cups_servicio and cups:
                g.cups_servicio = cups
                cambios = True
            if not g.servicio_descripcion and servicio:
                g.servicio_descripcion = servicio[:400]
                cambios = True

        # 3. Código de respuesta: extraer del dictamen (ej. "RE9901") o de un
        #    tipo guardado ("RESPUESTA RE9901")
        if not g.codigo_respuesta and g.dictamen:
            m = re.search(r"\bRE\d{4}\b", g.dictamen)
            if m:
                g.codigo_respuesta = m.group(0)
                cambios = True

        if cambios:
            actualizadas += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar backfill: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="BACKFILL_HISTORIAL",
        tabla="historial",
        detalle=f"Glosas actualizadas: {actualizadas} de {len(glosas)} con campos nulos",
    )

    return {
        "message": "Backfill completado",
        "glosas_con_campos_nulos": len(glosas),
        "glosas_actualizadas": actualizadas,
        "ejecutado_por": current_user.email,
    }


@router.post("/mantenimiento/purgar")
def mantenimiento_purgar(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R57 P1: ejecuta limpieza completa de tablas históricas.

    - ai_cache: purga entradas > 30 días (TTL del caché)
    - ai_calls: purga métricas > 90 días (historial)
    - glosas_eliminadas: purga ya caducadas (>30 días, fuera de la
      ventana de restauración)

    Pasar dry_run=true para solo contar sin eliminar.
    Solo SUPER_ADMIN.
    """
    from app.services.mantenimiento import ejecutar_mantenimiento_completo
    return ejecutar_mantenimiento_completo(db, dry_run=dry_run)


@router.get("/backup-db.json")
def descargar_backup_db(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R62 P2: backup selectivo de tablas críticas en JSON.

    Exporta tablas que NO son derivables (datos de negocio reales):
      - glosas
      - contratos
      - tarifas_contratadas
      - usuarios (sin password_hash)
      - audit_log (últimos 90 días)
      - conciliaciones
      - plantillas_gold (las que el equipo curó manualmente)

    NO incluye tablas regenerables:
      - ai_cache (caché)
      - ai_calls (métricas históricas)
      - glosas_eliminadas (papelera)

    Solo SUPER_ADMIN. La respuesta tiene Content-Disposition:
    attachment para descarga directa.

    Tamaño esperado: 1-50 MB para una IPS típica con 10k glosas.
    """
    import json
    from datetime import datetime, timedelta, timezone

    from fastapi.responses import Response
    from sqlalchemy import inspect

    from app.models.db import (
        ContratoRecord, GlosaRecord, TarifaContratadaRecord,
        ConciliacionRecord, PlantillaGoldRecord,
    )

    def _serializar(rec, exclude: tuple = ()) -> dict:
        out = {}
        for col in inspect(rec).mapper.column_attrs:
            if col.key in exclude:
                continue
            val = getattr(rec, col.key)
            if isinstance(val, datetime):
                val = val.isoformat()
            out[col.key] = val
        return out

    backup = {
        "metadata": {
            "exportado_en": datetime.now(timezone.utc).isoformat(),
            "exportado_por": current_user.email,
            "version_schema": "1.0",
            "incluye_tablas": [
                "glosas", "contratos", "tarifas_contratadas",
                "usuarios", "audit_log_90d", "conciliaciones",
                "plantillas_gold",
            ],
        },
    }

    backup["glosas"] = [_serializar(g) for g in db.query(GlosaRecord).all()]
    backup["contratos"] = [_serializar(c) for c in db.query(ContratoRecord).all()]
    backup["tarifas_contratadas"] = [
        _serializar(t) for t in db.query(TarifaContratadaRecord).all()
    ]
    # Usuarios SIN password_hash (seguridad: el backup no debe servir
    # para login en otra instancia)
    backup["usuarios"] = [
        _serializar(u, exclude=("password_hash", "totp_secret"))
        for u in db.query(UsuarioRecord).all()
    ]
    # Audit log: solo últimos 90 días para mantener tamaño manejable
    corte_audit = datetime.now(timezone.utc) - timedelta(days=90)
    backup["audit_log_90d"] = [
        _serializar(a) for a in db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= corte_audit)
        .order_by(AuditLogRecord.timestamp.desc())
        .all()
    ]
    backup["conciliaciones"] = [
        _serializar(c) for c in db.query(ConciliacionRecord).all()
    ]
    backup["plantillas_gold"] = [
        _serializar(p) for p in db.query(PlantillaGoldRecord)
        .filter(PlantillaGoldRecord.activa == 1).all()
    ]

    fname = f"backup-hus-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.json"
    payload = json.dumps(backup, ensure_ascii=False, default=str).encode("utf-8")
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
