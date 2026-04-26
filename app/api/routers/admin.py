"""Operaciones administrativas peligrosas (reset de datos).

Requiere rol SUPER_ADMIN y confirmación explícita para todas las acciones.
Cada operación queda registrada en audit_log para trazabilidad.
"""
from typing import Optional

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


@router.get("/ai-cache/stats")
def ai_cache_stats(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R86 P1: estadísticas del cache de respuestas IA persistido en BD.

    Útil para evaluar el ahorro real del caché:
      - Cuánto se reutiliza (hit_count promedio/máximo)
      - Cuáles entradas tienen más impacto
      - Tamaño total del cache (chars almacenados)
      - Edad de las entradas

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import AICacheRecord

    total = db.query(_f.count(AICacheRecord.id)).scalar() or 0
    if total == 0:
        return {
            "total_entradas": 0,
            "hit_count_total": 0,
            "espacio_chars": 0,
            "top_5_mas_usadas": [],
            "viejas_30d": 0,
        }

    hit_total = db.query(_f.sum(AICacheRecord.hit_count)).scalar() or 0
    chars_total = db.query(_f.sum(_f.length(AICacheRecord.respuesta))).scalar() or 0
    avg_hits = (hit_total / total) if total else 0
    max_hits = db.query(_f.max(AICacheRecord.hit_count)).scalar() or 0

    top_5 = (
        db.query(AICacheRecord)
        .order_by(AICacheRecord.hit_count.desc())
        .limit(5)
        .all()
    )

    corte_30 = ahora_utc() - timedelta(days=30)
    viejas = (
        db.query(_f.count(AICacheRecord.id))
        .filter(AICacheRecord.creado_en < corte_30)
        .scalar() or 0
    )

    return {
        "total_entradas": int(total),
        "hit_count_total": int(hit_total),
        "hit_count_promedio": round(float(avg_hits), 1),
        "hit_count_max": int(max_hits),
        "espacio_chars": int(chars_total),
        "espacio_kb": round(int(chars_total) / 1024, 1),
        "viejas_30d": int(viejas),
        "top_5_mas_usadas": [
            {
                "clave": r.clave[:20] + "…" if r.clave else "—",
                "modelo": r.modelo,
                "hits": r.hit_count or 0,
                "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            }
            for r in top_5
        ],
    }


@router.post("/ai-cache/limpiar")
def limpiar_ai_cache(
    dias: int = 30,
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R86 P2: limpia el cache de respuestas IA con corte configurable.

    Variante manual del scheduler de mantenimiento (R57 P2). Útil
    cuando el admin quiere forzar limpieza con un threshold distinto
    al default 30 días (ej. dias=7 para liberar espacio agresivamente
    antes de un demo).

    Reusa la función pura de R57 P1.
    """
    from app.services.mantenimiento import purgar_ai_cache_viejo
    return purgar_ai_cache_viejo(db, dias=int(dias), dry_run=dry_run)


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


@router.get("/usuarios/exportar.csv")
def admin_exportar_usuarios_csv(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R105 P1: exporta lista de usuarios como CSV (sin secretos).

    Útil para reportes HR / auditoría interna. Excluye TODO lo
    sensible: password_hash, totp_secret, sesiones, tokens.

    Columnas (10): id, email, nombre, rol, activo, totp_activo,
    must_change_password, creado_en, ultimo_login, fallos_login.

    StreamingResponse para no cargar toda la lista en memoria si
    eventualmente hay miles de usuarios.

    Solo SUPER_ADMIN.
    """
    import csv
    import io
    from datetime import datetime, timezone

    from fastapi.responses import StreamingResponse

    usuarios = db.query(UsuarioRecord).order_by(UsuarioRecord.id).all()

    def _generar():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "id", "email", "nombre", "rol", "activo",
            "totp_activo", "must_change_password",
            "creado_en", "ultimo_login", "fallos_login",
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        for u in usuarios:
            w.writerow([
                u.id,
                u.email or "",
                u.nombre or "",
                u.rol or "",
                int(bool(u.activo)),
                int(bool(getattr(u, "totp_activo", 0))),
                int(bool(getattr(u, "must_change_password", 0))),
                u.creado_en.isoformat() if getattr(u, "creado_en", None) else "",
                (
                    u.ultimo_login.isoformat()
                    if getattr(u, "ultimo_login", None) else ""
                ),
                getattr(u, "fallos_login_consecutivos", 0) or 0,
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    fname = f"usuarios-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        _generar(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/snapshot.json")
def admin_snapshot_json(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R117 P1: snapshot point-in-time del estado del sistema.

    Captura métricas clave en un momento dado, ideal para:
      - Auditoría regulatoria periódica ("estado al cierre de mes")
      - Comparación temporal (snapshot mes A vs mes B)
      - Rollback verification (¿el sistema quedó bien tras cambio X?)

    NO incluye datos sensibles ni dumps masivos — es un resumen
    estructurado descargable como archivo JSON con
    Content-Disposition.

    Solo SUPER_ADMIN.
    """
    from datetime import timezone
    import json
    from fastapi.responses import Response

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import (
        AICacheRecord, AICallRecord, AuditLogRecord,
        ContratoRecord, GlosaEliminadaRecord, GlosaRecord,
        PlantillaGoldRecord,
    )

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()

    # Counts
    counts = {
        "glosas_total": db.query(_f.count(GlosaRecord.id)).scalar() or 0,
        "usuarios_activos": (
            db.query(_f.count(UsuarioRecord.id))
            .filter(UsuarioRecord.activo == 1)
            .scalar() or 0
        ),
        "contratos": (
            db.query(_f.count(ContratoRecord.eps)).scalar() or 0
        ),
        "plantillas_gold": (
            db.query(_f.count(PlantillaGoldRecord.id)).scalar() or 0
        ),
        "ai_cache": db.query(_f.count(AICacheRecord.id)).scalar() or 0,
        "ai_calls": db.query(_f.count(AICallRecord.id)).scalar() or 0,
        "audit_log": db.query(_f.count(AuditLogRecord.id)).scalar() or 0,
        "papelera": (
            db.query(_f.count(GlosaEliminadaRecord.id)).scalar() or 0
        ),
    }

    # Glosas por estado (snapshot)
    abiertas = 0
    cerradas = 0
    valor_total_pendiente = 0.0
    valor_total_recuperado = 0.0
    for g in db.query(GlosaRecord).all():
        v = float(g.valor_objetado or 0)
        valor_total_recuperado += float(g.valor_recuperado or 0)
        if (g.estado or "").upper() in ESTADOS_CERRADOS:
            cerradas += 1
        else:
            abiertas += 1
            valor_total_pendiente += v

    payload = {
        "snapshot_id": ahora.strftime("%Y%m%d-%H%M%S"),
        "generado_en": ahora.isoformat(),
        "generado_por": current_user.email,
        "counts": counts,
        "glosas": {
            "abiertas": abiertas,
            "cerradas": cerradas,
            "valor_pendiente_total": int(valor_total_pendiente),
            "valor_recuperado_acumulado": int(valor_total_recuperado),
        },
    }

    fname = f"snapshot-{payload['snapshot_id']}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/diagnostico-bd")
def admin_diagnostico_bd(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R101 P2: diagnóstico de tamaños y conteos de BD.

    Útil para detectar:
      - Tablas creciendo descontroladamente
      - Tablas que necesitan purga
      - Predecir cuándo la BD necesitará escalado

    Devuelve por tabla:
      - filas: count
      - tamano_estimado_mb: estimación basada en filas × tamaño promedio
        de fila (heurística — no usa pg_total_relation_size para
        ser portable SQLite/PostgreSQL)

    Solo SUPER_ADMIN.
    """
    from sqlalchemy import func as _f

    from app.models.db import (
        AICacheRecord, AICallRecord, AuditLogRecord,
        ContratoRecord, DictamenVersionRecord, GlosaEliminadaRecord,
        GlosaRecord, PlantillaGoldRecord, TarifaContratadaRecord,
    )

    # Heurística de tamaño promedio por fila (bytes, aproximado)
    TABLAS = [
        ("glosas", GlosaRecord, 2000),
        ("usuarios", UsuarioRecord, 500),
        ("contratos", ContratoRecord, 5000),
        ("tarifas_contratadas", TarifaContratadaRecord, 200),
        ("plantillas_gold", PlantillaGoldRecord, 3000),
        ("ai_cache", AICacheRecord, 4000),
        ("ai_calls", AICallRecord, 800),
        ("audit_log", AuditLogRecord, 600),
        ("dictamen_versiones", DictamenVersionRecord, 4000),
        ("glosas_eliminadas", GlosaEliminadaRecord, 2500),
    ]

    items = []
    total_filas = 0
    total_mb = 0.0
    for nombre, model, bytes_por_fila in TABLAS:
        try:
            n = db.query(_f.count()).select_from(model).scalar() or 0
        except Exception:
            n = 0
        mb = round(n * bytes_por_fila / 1024 / 1024, 2)
        items.append({
            "tabla": nombre,
            "filas": n,
            "tamano_estimado_mb": mb,
        })
        total_filas += n
        total_mb += mb

    items.sort(key=lambda x: x["tamano_estimado_mb"], reverse=True)

    return {
        "total_filas_todas_tablas": total_filas,
        "total_estimado_mb": round(total_mb, 2),
        "items": items,
    }


@router.get("/glosas/exportar.csv")
def admin_exportar_glosas_csv(
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R116 P2: exporta glosas como CSV streaming (lightweight, sin formato).

    Complementa /glosas/exportar-xlsx (Excel completo con formato)
    con un CSV simple de 11 columnas, ideal para:
      - Importar a Excel/Sheets sin abrir XLSX
      - Procesar con scripts/jq/awk
      - Backup ligero (CSV es texto plano)

    Filtros opcionales: eps, estado.

    StreamingResponse para no cargar todo en memoria.

    Solo SUPER_ADMIN.
    """
    import csv
    import io
    from datetime import datetime, timezone

    from fastapi.responses import StreamingResponse

    from app.models.db import GlosaRecord

    q = db.query(GlosaRecord)
    if eps:
        q = q.filter(GlosaRecord.eps == eps)
    if estado:
        q = q.filter(GlosaRecord.estado == estado.upper())
    glosas = q.order_by(GlosaRecord.id.asc()).all()

    def _generar():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "id", "creado_en", "eps", "factura", "codigo_glosa",
            "valor_objetado", "valor_recuperado", "estado", "etapa",
            "decision_eps", "gestor_nombre",
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        for g in glosas:
            w.writerow([
                g.id,
                g.creado_en.isoformat() if g.creado_en else "",
                g.eps or "",
                g.factura or "",
                g.codigo_glosa or "",
                float(g.valor_objetado or 0),
                float(g.valor_recuperado or 0),
                g.estado or "",
                g.etapa or "",
                g.decision_eps or "",
                g.gestor_nombre or "",
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    fname = f"glosas-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        _generar(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/glosas-revisar-bandeja")
def admin_glosas_revisar_bandeja(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R256 P1: bandeja de glosas que el coordinador debe revisar.

    Filtra glosas que están en estado RESPONDIDA pero llevan
    >7 días sin que la EPS responda (señal de que requiere
    seguimiento) O glosas RADICADA con dictamen presente >200
    chars (listas para revisión final).

    Útil para coordinador como cola de "cosas que mirar".

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ahora = ahora_utc()
    siete_dias = ahora - timedelta(days=7)

    # 1) RESPONDIDA con respuesta HUS hace >7 días
    pendientes_eps = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RESPONDIDA")
        .filter(GlosaRecord.creado_en < siete_dias)
        .filter(GlosaRecord.fecha_decision_eps.is_(None))
        .all()
    )

    # 2) RADICADA con dictamen ya redactado pero no enviado
    para_revision = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RADICADA")
        .filter(GlosaRecord.dictamen.isnot(None))
        .all()
    )
    para_revision = [
        g for g in para_revision
        if g.dictamen and len(g.dictamen) >= 200
    ]

    items_pe = []
    for g in pendientes_eps:
        items_pe.append({
            "id": g.id, "eps": g.eps, "factura": g.factura,
            "valor_objetado": float(g.valor_objetado or 0),
            "razon": "EPS no responde tras 7d",
        })
    items_pr = []
    for g in para_revision:
        items_pr.append({
            "id": g.id, "eps": g.eps, "factura": g.factura,
            "valor_objetado": float(g.valor_objetado or 0),
            "razon": "Dictamen listo, falta envío",
        })

    return {
        "total_pendiente_eps": len(items_pe),
        "total_listas_envio": len(items_pr),
        "pendiente_eps": items_pe[:30],
        "listas_envio": items_pr[:30],
    }


@router.get("/audit-recientes")
def admin_audit_recientes(
    horas: int = 24,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R249 P1: últimos eventos audit (últimas N horas).

    Devuelve los N eventos audit más recientes con metadata.
    Útil como feed live de actividad del sistema.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    desde = ahora_utc() - timedelta(hours=int(horas))
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .order_by(AuditLogRecord.timestamp.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for e in eventos:
        items.append({
            "id": e.id,
            "timestamp": (
                e.timestamp.isoformat() if e.timestamp else None
            ),
            "usuario_email": e.usuario_email,
            "accion": e.accion,
            "tabla": e.tabla,
            "registro_id": e.registro_id,
            "campo": e.campo,
        })

    return {
        "ventana_horas": int(horas),
        "total": len(eventos),
        "items": items,
    }


@router.get("/dictamenes-recientes")
def admin_dictamenes_recientes(
    horas: int = 24,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R247 P1: últimas versiones de dictamen (últimas N horas).

    Útil como feed de actividad reciente del equipo:
      "alice@x refinó la glosa #123 hace 2h"
      "bob@x creó dictamen para glosa #456 hace 30min"

    Devuelve hasta 100 versiones DESC por creado_en.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import DictamenVersionRecord

    desde = ahora_utc() - timedelta(hours=int(horas))
    versiones = (
        db.query(DictamenVersionRecord)
        .filter(DictamenVersionRecord.creado_en >= desde)
        .order_by(DictamenVersionRecord.creado_en.desc())
        .limit(100)
        .all()
    )

    items = []
    for v in versiones:
        items.append({
            "id": v.id,
            "glosa_id": v.glosa_id,
            "accion": v.accion,
            "autor_email": v.autor_email,
            "creado_en": (
                v.creado_en.isoformat() if v.creado_en else None
            ),
            "longitud_dictamen": (
                len(v.dictamen_html) if v.dictamen_html else 0
            ),
        })

    return {
        "ventana_horas": int(horas),
        "total_versiones": len(versiones),
        "items": items,
    }


@router.get("/usuarios-actividad-mensual")
def admin_usuarios_actividad_mensual(
    usuario_email: str,
    meses: int = 6,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R242 P1: actividad audit mes-a-mes de un usuario.

    Para investigar el ritmo histórico de un usuario:
      "¿Alice ha bajado su actividad en últimos meses?"

    Param `usuario_email`: email exacto.

    Devuelve serie ASC por mes con count de eventos audit.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    if not usuario_email or len(usuario_email) < 3:
        raise HTTPException(400, "usuario_email requerido")

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.usuario_email == usuario_email)
        .filter(AuditLogRecord.timestamp >= desde)
        .all()
    )

    por_mes: dict[str, int] = {}
    for e in eventos:
        ts = e.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if not ts:
            continue
        k = ts.strftime("%Y-%m")
        por_mes[k] = por_mes.get(k, 0) + 1

    serie = []
    for k in sorted(por_mes.keys()):
        serie.append({"mes": k, "eventos": por_mes[k]})

    return {
        "usuario_email": usuario_email,
        "ventana_meses": int(meses),
        "total_eventos": len(eventos),
        "serie": serie,
    }


@router.get("/glosas-sin-codigo-respuesta")
def admin_glosas_sin_codigo_respuesta(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R278 P1: glosas decididas pero sin codigo_respuesta.

    Una glosa decidida (LEVANTADA/RATIFICADA/ACEPTADA) sin
    `codigo_respuesta` es un dato incompleto: la EPS debió
    haber emitido un código de respuesta (RE9501, RE9701,
    etc) según Res. 2284/2023.

    Útil para campañas de calidad de datos: completar
    información histórica.

    Solo SUPER_ADMIN. Ordena por valor_objetado DESC.
    """
    ESTADOS_DECIDIDOS = ["LEVANTADA", "RATIFICADA", "ACEPTADA"]

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(
            (GlosaRecord.codigo_respuesta.is_(None))
            | (GlosaRecord.codigo_respuesta == "")
        )
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": int(float(g.valor_objetado or 0)),
        })
    items.sort(key=lambda x: x["valor_objetado"], reverse=True)

    return {
        "total_sin_codigo_respuesta": len(items),
        "items": items[: int(limit)],
    }


@router.get("/audit-actividad-mensual")
def admin_audit_actividad_mensual(
    meses: int = 6,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R272 P1: actividad audit_log agregada por mes.

    Diferente a /admin/audit-recientes (feed live): aquí
    serie temporal de cuántos eventos audit se generaron
    cada mes en los últimos N meses.

    Útil para detectar tendencias: ¿el sistema está
    siendo más usado o menos? ¿hay meses con picos?

    Por mes: total_eventos, usuarios_distintos, top_acciones.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .all()
    )

    por_mes: dict[str, dict] = {}
    for e in eventos:
        ts = e.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if not ts:
            continue
        k = ts.strftime("%Y-%m")
        b = por_mes.setdefault(k, {
            "count": 0, "usuarios": set(), "acciones": {},
        })
        b["count"] += 1
        if e.usuario_email:
            b["usuarios"].add(e.usuario_email)
        accion = e.accion or "?"
        b["acciones"][accion] = b["acciones"].get(accion, 0) + 1

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        top = sorted(
            b["acciones"].items(), key=lambda x: x[1], reverse=True,
        )[:3]
        serie.append({
            "mes": k,
            "total_eventos": b["count"],
            "usuarios_distintos": len(b["usuarios"]),
            "top_acciones": [
                {"accion": a, "count": c} for a, c in top
            ],
        })

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@router.get("/glosas-sin-gestor")
def admin_glosas_sin_gestor(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R271 P1: glosas abiertas sin gestor asignado.

    Cualquier glosa cuyo `gestor_nombre` sea NULL o vacío
    debe asignarse a alguien para iniciar el ciclo de
    gestión. Útil para el coordinador hacer asignación
    masiva.

    Solo SUPER_ADMIN. Ordena por valor_objetado DESC para
    priorizar las de mayor cuantía.
    """
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(
            (GlosaRecord.gestor_nombre.is_(None))
            | (GlosaRecord.gestor_nombre == "")
        )
        .all()
    )

    items = []
    for g in abiertas:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "dias_restantes": g.dias_restantes,
        })
    items.sort(key=lambda x: x["valor_objetado"], reverse=True)

    return {
        "total_sin_gestor": len(items),
        "valor_total_pendiente": sum(it["valor_objetado"] for it in items),
        "items": items[: int(limit)],
    }


@router.get("/distribucion-rol")
def admin_distribucion_rol(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R266 P1: distribución de usuarios por rol.

    Por rol: total y activos. Útil para revisar mix de
    equipo: ¿hay suficientes auditores? ¿muchos
    inactivos?

    Solo SUPER_ADMIN.
    """
    usuarios = db.query(UsuarioRecord).all()

    bucket: dict[str, dict] = {}
    for u in usuarios:
        rol = (u.rol or "SIN_ROL").upper()
        b = bucket.setdefault(rol, {"total": 0, "activos": 0})
        b["total"] += 1
        if int(u.activo or 0) == 1:
            b["activos"] += 1

    items = []
    for rol, b in bucket.items():
        items.append({
            "rol": rol,
            "total": b["total"],
            "activos": b["activos"],
            "inactivos": b["total"] - b["activos"],
        })
    items.sort(key=lambda x: x["total"], reverse=True)

    return {
        "total_usuarios": sum(it["total"] for it in items),
        "total_activos": sum(it["activos"] for it in items),
        "items": items,
    }


@router.get("/eps-conteos")
def admin_eps_conteos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R239 P1: lista compacta de TODAS las EPS con conteos.

    Útil como índice global de EPS, ordenado por count_total
    DESC. Para cada EPS:
      - count_total
      - count_abiertas
      - valor_total_objetado

    Solo SUPER_ADMIN.
    """
    from sqlalchemy import func as _f

    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"total": 0, "abiertas": 0, "valor": 0.0}
        b = por_eps[eps]
        b["total"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        if (g.estado or "").upper() not in ESTADOS_CERRADOS:
            b["abiertas"] += 1

    items = []
    for eps, b in por_eps.items():
        items.append({
            "eps": eps,
            "count_total": b["total"],
            "count_abiertas": b["abiertas"],
            "valor_total_objetado": int(b["valor"]),
        })
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "total_eps": len(items),
        "items": items,
    }


@router.get("/usuarios-mas-cargados")
def admin_usuarios_mas_cargados(
    top: int = 10,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R212 P1: top N gestores con más glosas abiertas asignadas.

    Diferente a /admin/distribucion-cargas (todos los gestores):
    aquí solo los más sobrecargados, útil para revisión rápida
    "¿quién está al límite?"

    Devuelve top N ordenado DESC por carga.

    Solo SUPER_ADMIN.
    """
    from sqlalchemy import func as _f

    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    rows = (
        db.query(
            GlosaRecord.gestor_nombre,
            _f.count().label("n"),
        )
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .group_by(GlosaRecord.gestor_nombre)
        .order_by(_f.count().desc())
        .limit(int(top))
        .all()
    )

    items = []
    for nombre, n in rows:
        items.append({
            "gestor": nombre,
            "glosas_abiertas": int(n),
        })

    return {
        "top_solicitado": int(top),
        "items": items,
    }


@router.get("/conciliaciones-proximas")
def admin_conciliaciones_proximas(
    dias: int = 14,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R207 P1: conciliaciones con audiencia próxima.

    Lista las que tienen fecha_audiencia entre hoy y +N días.
    Útil para preparación: "estas son las audiencias de las
    próximas 2 semanas, prepara los argumentos".

    Devuelve listado ordenado ASC por fecha_audiencia.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import ConciliacionRecord

    ahora = ahora_utc()
    futuro = ahora + timedelta(days=int(dias))

    todas = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.fecha_audiencia.isnot(None))
        .all()
    )

    items = []
    for c in todas:
        fa = c.fecha_audiencia
        if fa and fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        if not fa or fa < ahora or fa > futuro:
            continue
        dias_para = (fa - ahora).days
        items.append({
            "id": c.id,
            "glosa_id": c.glosa_id,
            "fecha_audiencia": fa.isoformat(),
            "estado_bilateral": c.estado_bilateral,
            "dias_para_audiencia": dias_para,
            "valor_ratificado_hus": float(c.valor_ratificado_hus or 0),
        })
    items.sort(key=lambda x: x["dias_para_audiencia"])

    return {
        "ventana_dias": int(dias),
        "total_proximas": len(items),
        "items": items,
    }


@router.get("/conciliaciones-vencidas")
def admin_conciliaciones_vencidas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R206 P1: conciliaciones con audiencia atrasada.

    Lista las conciliaciones con fecha_audiencia pasada y
    estado_bilateral != ACTA_FIRMADA / CERRADA. Audiencias ya
    pasadas que no se cerraron formalmente: riesgo legal.

    Devuelve listado ordenado DESC por dias_atraso.

    Solo SUPER_ADMIN.
    """
    from datetime import timezone

    from app.core.tz import ahora_utc
    from app.models.db import ConciliacionRecord

    ahora = ahora_utc()
    CERRADAS = {"ACTA_FIRMADA", "CERRADA"}

    todas = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.fecha_audiencia.isnot(None))
        .all()
    )

    items = []
    for c in todas:
        fa = c.fecha_audiencia
        if fa and fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        if not fa or fa >= ahora:
            continue
        if (c.estado_bilateral or "") in CERRADAS:
            continue
        dias_atraso = (ahora - fa).days
        items.append({
            "id": c.id,
            "glosa_id": c.glosa_id,
            "fecha_audiencia": fa.isoformat(),
            "estado_bilateral": c.estado_bilateral,
            "dias_atraso": dias_atraso,
            "valor_ratificado_hus": float(c.valor_ratificado_hus or 0),
        })
    items.sort(key=lambda x: x["dias_atraso"], reverse=True)

    return {
        "total_atrasadas": len(items),
        "items": items,
    }


@router.get("/dictamenes-versiones-limpieza")
def admin_dictamenes_versiones_limpieza(
    max_versiones_por_glosa: int = 10,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R205 P1: identifica glosas con demasiadas versiones.

    Cada refinación de dictamen crea una fila en
    DictamenVersionRecord. Glosas refinadas N veces ocupan N
    filas. Si max>10, sugerir purga de versiones intermedias.

    Sin ejecutar nada, solo reporta:
      - cuántas glosas exceden el max
      - cuántas filas exceden el max
      - bytes estimados a recuperar (~5KB/version)

    Solo SUPER_ADMIN.
    """
    from sqlalchemy import func as _f

    from app.models.db import DictamenVersionRecord

    rows = (
        db.query(
            DictamenVersionRecord.glosa_id,
            _f.count().label("n"),
        )
        .group_by(DictamenVersionRecord.glosa_id)
        .having(_f.count() > int(max_versiones_por_glosa))
        .all()
    )

    glosas_excedidas = len(rows)
    filas_excedentes = sum(
        max(0, n - int(max_versiones_por_glosa)) for _, n in rows
    )

    BYTES_POR_VERSION = 5000
    bytes_estimados = filas_excedentes * BYTES_POR_VERSION

    return {
        "max_versiones_por_glosa": int(max_versiones_por_glosa),
        "glosas_que_exceden_max": glosas_excedidas,
        "filas_excedentes": filas_excedentes,
        "bytes_estimados_recuperables": bytes_estimados,
        "mb_estimados_recuperables": round(
            bytes_estimados / (1024 * 1024), 2,
        ),
    }


@router.get("/historial-cambios-rol")
def admin_historial_cambios_rol(
    dias: int = 90,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R203 P1: historial de cambios de rol de usuarios.

    Filtra audit_log a cambios del campo `rol` en tabla
    `usuarios`. Crítico para auditoría de seguridad:
      "¿quién promovió a Bob de AUDITOR a SUPER_ADMIN?"

    Devuelve transiciones ordenadas DESC con metadata.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .filter(AuditLogRecord.tabla == "usuarios")
        .filter(AuditLogRecord.campo == "rol")
        .order_by(AuditLogRecord.timestamp.desc())
        .all()
    )

    items = []
    for e in eventos:
        items.append({
            "timestamp": (
                e.timestamp.isoformat() if e.timestamp else None
            ),
            "usuario_que_cambio": e.usuario_email,
            "usuario_afectado_id": e.registro_id,
            "rol_anterior": e.valor_anterior,
            "rol_nuevo": e.valor_nuevo,
        })

    return {
        "ventana_dias": int(dias),
        "total_cambios": len(items),
        "items": items,
    }


@router.get("/audit-cleanup-recomendado")
def admin_audit_cleanup_recomendado(
    dias_retencion: int = 365,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R202 P1: sugerencia de purga de audit log antiguo.

    Estima cuántos eventos audit son más viejos que el período
    de retención configurado y sugiere la purga.

    Útil para mantener la BD pequeña sin perder cumplimiento:
      - Habeas Data: retención típica 5 años
      - Pero solo los críticos; rutinarios pueden archivarse

    Devuelve:
      - dias_retencion configurado
      - fecha_corte (timestamp ISO)
      - eventos_total / eventos_a_purgar
      - bytes_estimados_ahorro (~200 bytes/row)
      - mb_estimados_ahorro

    Solo SUPER_ADMIN. NO ejecuta nada — solo reporta.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    desde = ahora_utc() - timedelta(days=int(dias_retencion))
    total = (
        db.query(_f.count(AuditLogRecord.id)).scalar() or 0
    )
    a_purgar = (
        db.query(_f.count(AuditLogRecord.id))
        .filter(AuditLogRecord.timestamp < desde)
        .scalar() or 0
    )

    BYTES_POR_ROW = 200
    bytes_ahorro = a_purgar * BYTES_POR_ROW

    return {
        "dias_retencion": int(dias_retencion),
        "fecha_corte": desde.isoformat(),
        "eventos_total": int(total),
        "eventos_a_purgar": int(a_purgar),
        "bytes_estimados_ahorro": bytes_ahorro,
        "mb_estimados_ahorro": round(bytes_ahorro / (1024 * 1024), 2),
    }


@router.get("/heatmap-usuario")
def admin_heatmap_usuario(
    usuario_email: str,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R188 P1: heatmap día×hora de actividad de un usuario específico.

    Para investigar patrones individuales:
      "¿Alice trabaja a horas extrañas?"
      "¿Bob tiene picos los lunes?"

    Devuelve matriz sparse 7×24 con eventos audit del usuario.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    if not usuario_email or len(usuario_email) < 3:
        raise HTTPException(400, "usuario_email requerido")

    desde = ahora_utc() - timedelta(days=int(dias))
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.usuario_email == usuario_email)
        .filter(AuditLogRecord.timestamp >= desde)
        .all()
    )

    matriz: dict[tuple[int, int], int] = {}
    for e in eventos:
        ts = e.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if not ts:
            continue
        key = (ts.weekday(), ts.hour)
        matriz[key] = matriz.get(key, 0) + 1

    DIAS = ["Lunes", "Martes", "Miércoles", "Jueves",
            "Viernes", "Sábado", "Domingo"]
    items = []
    for (dia_idx, hora), count in matriz.items():
        items.append({
            "dia_semana": dia_idx,
            "dia_nombre": DIAS[dia_idx],
            "hora": hora,
            "count": count,
        })
    items.sort(key=lambda x: (x["dia_semana"], x["hora"]))

    return {
        "usuario_email": usuario_email,
        "ventana_dias": int(dias),
        "total_eventos": len(eventos),
        "items": items,
    }


@router.get("/stats-asignacion")
def admin_stats_asignacion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R184 P1: métricas de asignación de glosas.

    Vista global del balanceo de cargas:
      - cuántas glosas tienen gestor asignado
      - cuántas tienen auditor_email
      - cuántas están sin nadie
      - distribución de carga (mín, máx, mediana)

    Útil para detectar:
      - Imbalance: 1 gestor con 200, otro con 5
      - Glosas huérfanas que nadie atiende

    Solo SUPER_ADMIN.
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    con_gestor = 0
    con_auditor = 0
    sin_nadie = 0
    cargas: dict[str, int] = {}

    for g in abiertas:
        tiene_gestor = bool(g.gestor_nombre)
        tiene_auditor = bool(g.auditor_email)
        if tiene_gestor:
            con_gestor += 1
            cargas[g.gestor_nombre] = cargas.get(g.gestor_nombre, 0) + 1
        if tiene_auditor:
            con_auditor += 1
        if not tiene_gestor and not tiene_auditor:
            sin_nadie += 1

    if cargas:
        valores = sorted(cargas.values())
        n = len(valores)
        mediana = (
            (valores[n // 2 - 1] + valores[n // 2]) / 2
            if n % 2 == 0 else valores[n // 2]
        )
        carga_min = valores[0]
        carga_max = valores[-1]
    else:
        mediana = 0
        carga_min = 0
        carga_max = 0

    return {
        "total_abiertas": len(abiertas),
        "con_gestor": con_gestor,
        "con_auditor": con_auditor,
        "sin_nadie": sin_nadie,
        "gestores_distintos": len(cargas),
        "carga_min_por_gestor": carga_min,
        "carga_max_por_gestor": carga_max,
        "carga_mediana_por_gestor": mediana,
    }


@router.get("/incidentes-criticos")
def admin_incidentes_criticos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R162 P1: incidentes críticos del sistema en tiempo real.

    Diferente a /admin/alertas-inteligentes (alertas tácticas
    de operación): aquí solo CRÍTICAS de tiempo real que
    requieren atención inmediata.

    Reglas:
      1. Glosas vencidas hace >60 días (riesgo regulatorio)
      2. Conciliaciones con audiencia atrasada
      3. Plantillas Gold con 0% éxito en últimos 30d (algo malo)

    Pensado para alimentar pantalla NOC / Slack canal #incidentes.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import (
        ConciliacionRecord, GlosaRecord, PlantillaGoldRecord,
    )

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ahora = ahora_utc()
    incidentes = []

    # 1. Glosas muy vencidas (>60d)
    muy_vencidas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < -60)
        .count()
    )
    if muy_vencidas:
        incidentes.append({
            "tipo": "GLOSAS_MUY_VENCIDAS",
            "severidad": "CRITICAL",
            "count": muy_vencidas,
            "descripcion": (
                f"{muy_vencidas} glosas vencidas hace más de 60 días — "
                "riesgo regulatorio"
            ),
        })

    # 2. Conciliaciones con audiencia atrasada
    audiencias_atrasadas = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.fecha_audiencia.isnot(None))
        .filter(ConciliacionRecord.fecha_audiencia < ahora)
        .filter(ConciliacionRecord.estado_bilateral != "CERRADA")
        .filter(ConciliacionRecord.estado_bilateral != "ACTA_FIRMADA")
        .count()
    )
    if audiencias_atrasadas:
        incidentes.append({
            "tipo": "AUDIENCIAS_ATRASADAS",
            "severidad": "WARNING",
            "count": audiencias_atrasadas,
            "descripcion": (
                f"{audiencias_atrasadas} audiencias bilaterales pasadas "
                "sin acta firmada"
            ),
        })

    # 3. Plantillas Gold con muchos usos pero valor_recuperado=0
    plantillas_malas = (
        db.query(PlantillaGoldRecord)
        .filter(PlantillaGoldRecord.activa == 1)
        .filter(PlantillaGoldRecord.usos >= 5)
        .filter((PlantillaGoldRecord.valor_recuperado == 0) |
                (PlantillaGoldRecord.valor_recuperado.is_(None)))
        .count()
    )
    if plantillas_malas:
        incidentes.append({
            "tipo": "PLANTILLAS_GOLD_INEFECTIVAS",
            "severidad": "WARNING",
            "count": plantillas_malas,
            "descripcion": (
                f"{plantillas_malas} plantillas Gold con 5+ usos pero "
                "$0 recuperado — revisar o desactivar"
            ),
        })

    return {
        "evaluado_en": ahora.isoformat(),
        "total_incidentes": len(incidentes),
        "items": incidentes,
    }


@router.get("/historial-reasignaciones")
def admin_historial_reasignaciones(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R156 P2: detecta reasignaciones de gestor en glosas.

    Filtra audit log a cambios del campo `gestor_nombre` o
    `auditor_email` y reporta:
      - cuántas reasignaciones hubo
      - quién la hizo
      - de quién a quién

    Útil para:
      - Auditoría: detectar reasignación masiva sospechosa
      - Análisis: ¿se reasignan mucho ciertos casos?
      - Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.campo.in_(["gestor_nombre", "auditor_email"]))
        .order_by(AuditLogRecord.timestamp.desc())
        .all()
    )

    items = []
    por_quien_reasigna: dict[str, int] = {}
    for e in eventos:
        if e.usuario_email:
            por_quien_reasigna[e.usuario_email] = (
                por_quien_reasigna.get(e.usuario_email, 0) + 1
            )
        items.append({
            "timestamp": (
                e.timestamp.isoformat() if e.timestamp else None
            ),
            "usuario_que_reasigna": e.usuario_email,
            "glosa_id": e.registro_id,
            "campo": e.campo,
            "anterior": e.valor_anterior,
            "nuevo": e.valor_nuevo,
        })

    top_reasignadores = sorted(
        por_quien_reasigna.items(), key=lambda x: x[1], reverse=True,
    )[:5]

    return {
        "ventana_dias": int(dias),
        "total_reasignaciones": len(eventos),
        "top_5_quien_reasigna": [
            {"usuario": u, "reasignaciones": n}
            for u, n in top_reasignadores
        ],
        "items": items[:100],  # cap a 100 items
    }


@router.get("/usuarios-sin-glosas")
def admin_usuarios_sin_glosas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R156 P1: usuarios activos sin glosas asignadas.

    Detecta usuarios con cuenta activa pero sin trabajo asignado
    como gestor. Útil para:
      - Identificar capacidad ociosa que puede absorber backlog
      - Revisar si hay usuarios que ya no deberían estar activos
      - Balanceo de cargas

    Devuelve lista de usuarios con rol AUDITOR/COORDINADOR sin
    aparecer como gestor en ninguna glosa abierta.

    Solo SUPER_ADMIN.
    """
    from sqlalchemy import func as _f

    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    # Set de gestores con glosas abiertas
    gestores_con_carga = {
        n[0] for n in (
            db.query(GlosaRecord.gestor_nombre)
            .filter(GlosaRecord.gestor_nombre.isnot(None))
            .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
            .distinct()
            .all()
        )
        if n[0]
    }

    # Usuarios activos con rol gestor
    usuarios = (
        db.query(UsuarioRecord)
        .filter(UsuarioRecord.activo == 1)
        .filter(UsuarioRecord.rol.in_(["AUDITOR", "COORDINADOR"]))
        .all()
    )

    items = []
    for u in usuarios:
        nombre = u.nombre or u.email
        if nombre not in gestores_con_carga:
            items.append({
                "id": u.id,
                "email": u.email,
                "nombre": u.nombre,
                "rol": u.rol,
            })

    return {
        "total_usuarios_activos_evaluados": len(usuarios),
        "total_sin_glosas_asignadas": len(items),
        "items": items,
    }


@router.get("/gestor-mensual")
def admin_gestor_mensual(
    gestor: str,
    meses: int = 6,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R153 P1: desempeño mensual de un gestor específico.

    Diferente a /usuarios/yo/performance-historica (self-service):
    aquí el admin puede consultar a cualquier gestor por nombre.

    Útil para revisión de desempeño individual:
      "¿Cómo viene Alice mes-a-mes?"

    Devuelve serie ASC por mes con métricas mensuales del gestor.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    if not gestor or len(gestor.strip()) < 2:
        raise HTTPException(400, "gestor debe tener >=2 caracteres")

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    desde = ahora_utc() - timedelta(days=int(meses) * 31)

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == gestor)
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in glosas:
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not dec:
            continue
        k = dec.strftime("%Y-%m")
        if k not in por_mes:
            por_mes[k] = {
                "cerradas": 0, "levantadas": 0, "valor_rec": 0.0,
            }
        b = por_mes[k]
        b["cerradas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["levantadas"] += 1
        b["valor_rec"] += float(g.valor_recuperado or 0)

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        tasa = (
            round(100 * b["levantadas"] / b["cerradas"], 2)
            if b["cerradas"] else 0.0
        )
        serie.append({
            "mes": k,
            "glosas_cerradas": b["cerradas"],
            "levantadas": b["levantadas"],
            "tasa_levantamiento_pct": tasa,
            "valor_recuperado": int(b["valor_rec"]),
        })

    return {
        "gestor": gestor,
        "ventana_meses": int(meses),
        "total_meses_con_actividad": len(serie),
        "serie": serie,
    }


@router.get("/ranking-gestores")
def admin_ranking_gestores(
    dias: int = 90,
    min_glosas: int = 3,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R148 P1: ranking de gestores con rating y badge.

    Diferente a /glosas/stats/eficiencia-gestor (data raw): aquí
    se agregan ranking position, rating estrellas y badge,
    pensado para gamificación / reconocimiento del equipo.

    Filtros:
      - Glosas cerradas en últimos `dias` días
      - Solo gestores con >= min_glosas

    Por gestor:
      - position (1=mejor)
      - glosas_cerradas / levantadas
      - tasa_levantamiento_pct
      - rating (1-5 estrellas: 80+=5★, 60+=4★, 40+=3★,
        20+=2★, <20=1★)
      - badge: TOP_PERFORMER (>=80%) / DESTACADO (>=40%) /
               EN_PROGRESO (<40%)

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    desde = ahora_utc() - timedelta(days=int(dias))

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    por_gestor: dict[str, dict] = {}
    for g in glosas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        if gestor not in por_gestor:
            por_gestor[gestor] = {"cerradas": 0, "levantadas": 0}
        por_gestor[gestor]["cerradas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_gestor[gestor]["levantadas"] += 1

    items = []
    for gestor, b in por_gestor.items():
        if b["cerradas"] < min_glosas:
            continue
        tasa = round(100 * b["levantadas"] / b["cerradas"], 2)
        if tasa >= 80:
            rating, badge = 5, "TOP_PERFORMER"
        elif tasa >= 60:
            rating, badge = 4, "DESTACADO"
        elif tasa >= 40:
            rating, badge = 3, "DESTACADO"
        elif tasa >= 20:
            rating, badge = 2, "EN_PROGRESO"
        else:
            rating, badge = 1, "EN_PROGRESO"
        items.append({
            "gestor": gestor,
            "glosas_cerradas": b["cerradas"],
            "levantadas": b["levantadas"],
            "tasa_levantamiento_pct": tasa,
            "rating": rating,
            "badge": badge,
        })
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)
    for idx, it in enumerate(items, start=1):
        it["position"] = idx

    return {
        "ventana_dias": int(dias),
        "min_glosas_filtro": int(min_glosas),
        "total_gestores_evaluados": len(items),
        "items": items,
    }


@router.get("/glosas-prioritarias")
def admin_glosas_prioritarias(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R112 P1: worklist priorizada de glosas que necesitan atención.

    Ranking heurístico para que el coordinador asigne trabajo:
    score = peso_vencimiento + peso_valor + peso_falta_dictamen +
            peso_sin_gestor

    Útil al inicio del día: "estas son las glosas que el equipo
    debe atacar primero".

    Devuelve top N glosas no-cerradas ordenadas DESC por score
    con razon (string explicando por qué entra al top).

    Solo SUPER_ADMIN.
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    items = []
    for g in abiertas:
        score = 0.0
        razones = []

        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            score += 100
            razones.append(f"vencida {abs(dr)}d")
        elif dr <= 3:
            score += 50
            razones.append(f"crítica {dr}d")
        elif dr <= 7:
            score += 20

        v_obj = float(g.valor_objetado or 0)
        if v_obj > 10_000_000:
            score += 30
            razones.append("alto valor (>10M)")
        elif v_obj > 1_000_000:
            score += 15

        if not g.dictamen or len(g.dictamen) < 50:
            score += 25
            razones.append("sin dictamen")

        if not g.gestor_nombre:
            score += 15
            razones.append("sin gestor")

        if score == 0:
            continue

        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "valor_objetado": int(v_obj),
            "dias_restantes": dr,
            "estado": g.estado,
            "gestor_nombre": g.gestor_nombre,
            "score": round(score, 2),
            "razones": razones,
        })

    items.sort(key=lambda x: x["score"], reverse=True)

    return {
        "limit": int(limit),
        "total_evaluadas": len(abiertas),
        "total_priorizadas": len(items),
        "items": items[:limit],
    }


@router.get("/reporte-mensual.csv")
def admin_reporte_mensual_csv(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R126 P2: reporte ejecutivo mensual descargable como CSV.

    Una fila por mes con métricas clave:
      mes, glosas_creadas, glosas_cerradas,
      valor_objetado, valor_recuperado,
      tasa_levantamiento_pct, tasa_recuperacion_pct,
      ia_calls, costo_ia_usd

    Útil para reporting periódico a gerencia (cargar a Power BI,
    Tableau, archivar como evidencia de gestión).

    Solo SUPER_ADMIN.
    """
    import csv
    import io
    from datetime import datetime, timezone

    from fastapi.responses import StreamingResponse

    from app.models.db import AICallRecord, GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()
    ia_calls = db.query(AICallRecord).all()

    por_mes: dict[str, dict] = {}

    def _ensure(k):
        if k not in por_mes:
            por_mes[k] = {
                "creadas": 0, "cerradas": 0,
                "valor_obj": 0.0, "valor_rec": 0.0,
                "decididas": 0, "levantadas": 0,
                "ia_calls": 0, "ia_cost": 0.0,
            }
        return por_mes[k]

    for g in glosas:
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        if creado:
            _ensure(creado.strftime("%Y-%m"))["creadas"] += 1

        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        estado = (g.estado or "").upper()
        if dec and estado in ESTADOS_CERRADOS:
            b = _ensure(dec.strftime("%Y-%m"))
            b["cerradas"] += 1
            b["valor_obj"] += float(g.valor_objetado or 0)
            b["valor_rec"] += float(g.valor_recuperado or 0)
            if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
                b["decididas"] += 1
                if estado == "LEVANTADA":
                    b["levantadas"] += 1

    for c in ia_calls:
        cre = c.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if cre:
            b = _ensure(cre.strftime("%Y-%m"))
            b["ia_calls"] += 1
            b["ia_cost"] += float(c.cost_usd or 0)

    def _generar():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "mes", "glosas_creadas", "glosas_cerradas",
            "valor_objetado", "valor_recuperado",
            "tasa_levantamiento_pct", "tasa_recuperacion_pct",
            "ia_calls", "costo_ia_usd",
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        for k in sorted(por_mes.keys()):
            b = por_mes[k]
            tasa_lev = (
                round(100 * b["levantadas"] / b["decididas"], 2)
                if b["decididas"] else 0.0
            )
            tasa_rec = (
                round(100 * b["valor_rec"] / b["valor_obj"], 2)
                if b["valor_obj"] else 0.0
            )
            w.writerow([
                k,
                b["creadas"],
                b["cerradas"],
                int(b["valor_obj"]),
                int(b["valor_rec"]),
                tasa_lev,
                tasa_rec,
                b["ia_calls"],
                round(b["ia_cost"], 4),
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    fname = f"reporte-mensual-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        _generar(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/conteo-rapido")
def admin_conteo_rapido(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R135 P2: contadores instantáneos para banner / pills UI.

    Endpoint MUY ligero (solo COUNT queries, sin agregaciones
    pesadas) que se puede llamar cada N segundos para alimentar
    el badge global del header.

    Devuelve solo enteros básicos:
      - glosas_total / abiertas / cerradas / criticas / vencidas
      - usuarios_activos
      - audit_log_24h

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord, GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    ahora = ahora_utc()
    desde_24h = ahora - timedelta(hours=24)

    glosas_total = db.query(_f.count(GlosaRecord.id)).scalar() or 0
    cerradas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar() or 0
    )
    abiertas = glosas_total - cerradas
    criticas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes <= 3)
        .filter(GlosaRecord.dias_restantes >= 0)
        .scalar() or 0
    )
    vencidas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < 0)
        .scalar() or 0
    )

    usuarios_activos = (
        db.query(_f.count(UsuarioRecord.id))
        .filter(UsuarioRecord.activo == 1)
        .scalar() or 0
    )

    audit_24h = (
        db.query(_f.count(AuditLogRecord.id))
        .filter(AuditLogRecord.timestamp >= desde_24h)
        .scalar() or 0
    )

    return {
        "glosas_total": glosas_total,
        "glosas_abiertas": abiertas,
        "glosas_cerradas": cerradas,
        "glosas_criticas": criticas,
        "glosas_vencidas": vencidas,
        "usuarios_activos": usuarios_activos,
        "audit_log_24h": audit_24h,
        "consultado_en": ahora.isoformat(),
    }


@router.get("/inconsistencias-datos")
def admin_inconsistencias_datos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R133 P1: detecta inconsistencias estructurales en datos.

    Revisa reglas de integridad:
      1. Glosas LEVANTADA con valor_recuperado=0 (¿se cobró?)
      2. Glosas ACEPTADA con valor_recuperado>0 (no debería)
      3. Glosas con fecha_decision_eps pero estado abierto
      4. Glosas con dias_restantes negativo en estado cerrado
      5. Glosas sin EPS (no debería pasar por NOT NULL pero check)

    Útil para limpieza de datos y auditoría regulatoria.

    Devuelve por regla: count + sample (max 5 IDs).

    Solo SUPER_ADMIN.
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    incons = {
        "levantadas_sin_recupero": [],
        "aceptadas_con_recupero": [],
        "decision_eps_en_estado_abierto": [],
        "dias_negativos_en_cerrada": [],
        "sin_eps": [],
    }

    for g in glosas:
        estado = (g.estado or "").upper()

        if estado == "LEVANTADA" and float(g.valor_recuperado or 0) == 0:
            incons["levantadas_sin_recupero"].append(g.id)

        if estado == "ACEPTADA" and float(g.valor_recuperado or 0) > 0:
            incons["aceptadas_con_recupero"].append(g.id)

        if g.fecha_decision_eps and estado not in ESTADOS_CERRADOS:
            incons["decision_eps_en_estado_abierto"].append(g.id)

        if (estado in ESTADOS_CERRADOS and
                (g.dias_restantes or 0) < 0):
            incons["dias_negativos_en_cerrada"].append(g.id)

        if not g.eps:
            incons["sin_eps"].append(g.id)

    items = []
    for regla, ids in incons.items():
        items.append({
            "regla": regla,
            "count": len(ids),
            "sample_ids": ids[:5],
        })

    total = sum(it["count"] for it in items)

    return {
        "total_inconsistencias": total,
        "reglas_evaluadas": len(items),
        "items": items,
    }


@router.get("/timeline-equipo")
def admin_timeline_equipo(
    horas: int = 24,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R126 P1: timeline cronológico del equipo (últimas N horas).

    Diferente a /admin/actividad-reciente (lista plana mezclada),
    aquí se agrupan eventos por hora con desglose por usuario.

    Útil para:
      - Reconstruir lo que pasó en una ventana específica
      - Ver patrones de actividad por hora del día
      - Auditoría retroactiva

    Devuelve serie por hora (orden ASC, hora-más-vieja primero):
      [{"hora": "2026-04-26T10", "total_eventos": 12,
        "por_usuario": {"alice@x": 8, "bob@x": 4},
        "acciones_top": [{"accion": "UPDATE", "n": 7}, ...]}]

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    ahora = ahora_utc()
    desde = ahora - timedelta(hours=int(horas))

    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .all()
    )

    por_hora: dict[str, dict] = {}
    for e in eventos:
        ts = e.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if not ts:
            continue
        # Bucket de hora: YYYY-MM-DDTHH
        key = ts.strftime("%Y-%m-%dT%H")
        if key not in por_hora:
            por_hora[key] = {
                "total": 0,
                "por_usuario": {},
                "por_accion": {},
            }
        b = por_hora[key]
        b["total"] += 1
        if e.usuario_email:
            b["por_usuario"][e.usuario_email] = (
                b["por_usuario"].get(e.usuario_email, 0) + 1
            )
        if e.accion:
            b["por_accion"][e.accion] = (
                b["por_accion"].get(e.accion, 0) + 1
            )

    serie = []
    for k in sorted(por_hora.keys()):
        b = por_hora[k]
        acciones_top = sorted(
            b["por_accion"].items(), key=lambda x: x[1], reverse=True,
        )[:3]
        serie.append({
            "hora": k,
            "total_eventos": b["total"],
            "por_usuario": b["por_usuario"],
            "acciones_top": [
                {"accion": a, "n": n} for a, n in acciones_top
            ],
        })

    return {
        "ventana_horas": int(horas),
        "total_eventos": len(eventos),
        "horas_con_actividad": len(serie),
        "serie": serie,
    }


@router.get("/cierre-del-dia")
def admin_cierre_del_dia(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R122 P1: reporte de cierre del día (stand-up matutino).

    Resumen de las últimas 24h, listo para que el coordinador lo
    lea/comparta:
      - Glosas creadas / cerradas / valor recuperado / IA calls
      - Top 3 gestores con más actividad
      - Glosas que vencen mañana

    Útil como insumo para Slack/email diario.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import (
        AICallRecord, AuditLogRecord, GlosaRecord,
    )

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ahora = ahora_utc()
    hace_24h = ahora - timedelta(hours=24)

    # Glosas creadas últimas 24h
    creadas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= hace_24h)
        .all()
    )

    # Glosas cerradas últimas 24h (basado en fecha_decision_eps)
    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= hace_24h)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    valor_recuperado_dia = sum(
        float(g.valor_recuperado or 0) for g in cerradas
    )

    # IA calls últimas 24h
    ia_calls = (
        db.query(AICallRecord)
        .filter(AICallRecord.creado_en >= hace_24h)
        .count()
    )

    # Top 3 gestores con más eventos audit
    rows = (
        db.query(AuditLogRecord.usuario_email)
        .filter(AuditLogRecord.timestamp >= hace_24h)
        .filter(AuditLogRecord.usuario_email.isnot(None))
        .all()
    )
    por_user: dict[str, int] = {}
    for (email,) in rows:
        por_user[email] = por_user.get(email, 0) + 1
    top_gestores = sorted(
        por_user.items(), key=lambda x: x[1], reverse=True,
    )[:3]

    # Glosas que vencen mañana (dias_restantes == 1)
    vencen_manana = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.dias_restantes == 1)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )
    valor_que_vence_manana = sum(
        float(g.valor_objetado or 0) for g in vencen_manana
    )

    return {
        "fecha_reporte": ahora.isoformat(),
        "ventana_horas": 24,
        "glosas_creadas_24h": len(creadas),
        "glosas_cerradas_24h": len(cerradas),
        "valor_recuperado_24h": int(valor_recuperado_dia),
        "ia_calls_24h": ia_calls,
        "top_3_gestores": [
            {"usuario": u, "eventos": n} for u, n in top_gestores
        ],
        "vencen_manana": {
            "count": len(vencen_manana),
            "valor_total": int(valor_que_vence_manana),
        },
    }


@router.get("/alertas-inteligentes")
def admin_alertas_inteligentes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R121 P1: alertas accionables consolidadas a nivel sistema.

    Diferente a /glosas/alertas (por glosa individual), este
    endpoint detecta condiciones agregadas que requieren
    intervención del coordinador/admin.

    Categorías:
      - CRITICAL: condiciones graves (datos perdidos, servicio caído)
      - WARNING: degradación notable (muchas vencidas, gestores
                 sobrecargados)
      - INFO: cambios notables (nueva EPS, picos de carga)
      - BUSINESS: oportunidades (alto valor sin gestor)

    Cada alerta tiene: {tipo, categoria, titulo, descripcion, accion,
                        endpoint?, count?}.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas_abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    ahora = ahora_utc()
    alertas = []

    # CRITICAL: Vencidas hace mucho (>30d en negativo)
    muy_vencidas = [
        g for g in todas_abiertas
        if (g.dias_restantes or 0) < -30
    ]
    if muy_vencidas:
        alertas.append({
            "tipo": "CRITICAL",
            "categoria": "SLA",
            "titulo": f"{len(muy_vencidas)} glosas vencidas hace más de 30 días",
            "descripcion": (
                "Estas glosas pueden ratificarse automáticamente. "
                "Acción urgente requerida."
            ),
            "accion": "Revisar y atender",
            "endpoint": "/admin/glosas-prioritarias",
            "count": len(muy_vencidas),
        })

    # WARNING: Muchas críticas
    criticas = [
        g for g in todas_abiertas
        if 0 <= (g.dias_restantes or 0) <= 3
    ]
    if len(criticas) >= 5:
        alertas.append({
            "tipo": "WARNING",
            "categoria": "SLA",
            "titulo": f"{len(criticas)} glosas críticas (≤3 días para vencer)",
            "descripcion": "Concentración inusual de glosas próximas a vencer.",
            "accion": "Reasignar y priorizar",
            "endpoint": "/admin/glosas-prioritarias",
            "count": len(criticas),
        })

    # WARNING: Glosas sin gestor
    sin_gestor = [g for g in todas_abiertas if not g.gestor_nombre]
    if len(sin_gestor) >= 10:
        alertas.append({
            "tipo": "WARNING",
            "categoria": "ASIGNACION",
            "titulo": f"{len(sin_gestor)} glosas sin gestor asignado",
            "descripcion": "Estas glosas no tienen responsable.",
            "accion": "Asignar gestores",
            "endpoint": "/admin/distribucion-cargas",
            "count": len(sin_gestor),
        })

    # BUSINESS: Alto valor sin gestor
    alto_valor_sin_gestor = [
        g for g in todas_abiertas
        if not g.gestor_nombre and float(g.valor_objetado or 0) > 5_000_000
    ]
    if alto_valor_sin_gestor:
        valor_total = sum(
            float(g.valor_objetado or 0) for g in alto_valor_sin_gestor
        )
        alertas.append({
            "tipo": "BUSINESS",
            "categoria": "OPORTUNIDAD",
            "titulo": (
                f"{len(alto_valor_sin_gestor)} glosas de alto valor "
                "(>$5M) sin gestor"
            ),
            "descripcion": (
                f"Valor total no asignado: ${int(valor_total):,} COP. "
                "Riesgo de no defenderlas a tiempo."
            ),
            "accion": "Asignar a auditor senior",
            "count": len(alto_valor_sin_gestor),
        })

    # WARNING: Glosas sin dictamen en estados avanzados
    sin_dictamen_avanzadas = [
        g for g in todas_abiertas
        if (g.estado or "").upper() in {"RESPONDIDA", "RATIFICADA"}
        and (not g.dictamen or len(g.dictamen) < 50)
    ]
    if sin_dictamen_avanzadas:
        alertas.append({
            "tipo": "WARNING",
            "categoria": "CALIDAD",
            "titulo": (
                f"{len(sin_dictamen_avanzadas)} glosas en estado avanzado "
                "sin dictamen"
            ),
            "descripcion": (
                "Inconsistencia: el workflow avanzó sin generar el "
                "dictamen formal."
            ),
            "accion": "Generar dictámenes",
            "endpoint": "/glosas/incompletas",
            "count": len(sin_dictamen_avanzadas),
        })

    # INFO: EPS nuevas en últimos 7 días
    desde_7d = ahora - timedelta(days=7)
    eps_recientes: set[str] = set()
    eps_historicas: set[str] = set()
    for g in db.query(GlosaRecord).all():
        eps = (g.eps or "").strip()
        if not eps:
            continue
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        if creado and creado >= desde_7d:
            eps_recientes.add(eps)
        elif creado:
            eps_historicas.add(eps)
    eps_nuevas = eps_recientes - eps_historicas
    if eps_nuevas:
        alertas.append({
            "tipo": "INFO",
            "categoria": "DATOS",
            "titulo": f"{len(eps_nuevas)} EPS nuevas detectadas en última semana",
            "descripcion": (
                f"EPS sin histórico previo: {', '.join(sorted(eps_nuevas))}. "
                "Verificar contratos."
            ),
            "accion": "Validar contratos",
            "endpoint": "/glosas/stats/eps-emergentes",
            "count": len(eps_nuevas),
        })

    return {
        "generado_en": ahora.isoformat(),
        "total_alertas": len(alertas),
        "por_tipo": {
            "CRITICAL": sum(1 for a in alertas if a["tipo"] == "CRITICAL"),
            "WARNING": sum(1 for a in alertas if a["tipo"] == "WARNING"),
            "INFO": sum(1 for a in alertas if a["tipo"] == "INFO"),
            "BUSINESS": sum(1 for a in alertas if a["tipo"] == "BUSINESS"),
        },
        "items": alertas,
    }


@router.get("/actividad-reciente")
def admin_actividad_reciente(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R110 P2: últimos N eventos del sistema (audit log + IA).

    Vista "live" de qué está pasando ahora mismo en el sistema.
    Combina:
      - Audit log (acciones de usuarios)
      - AI calls recientes (usos de modelos IA)

    Útil para el coordinador en stand-up daily o para soporte
    investigando incidentes "¿qué pasó hace 5 minutos?".

    Devuelve eventos ordenados DESC por timestamp con tipo
    discriminado: AUDIT vs AI_CALL.
    """
    from app.models.db import AICallRecord, AuditLogRecord

    audit_eventos = (
        db.query(AuditLogRecord)
        .order_by(AuditLogRecord.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    ia_eventos = (
        db.query(AICallRecord)
        .order_by(AICallRecord.creado_en.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for e in audit_eventos:
        items.append({
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "tipo": "AUDIT",
            "usuario": e.usuario_email,
            "descripcion": (
                f"{e.accion or '?'} en {e.tabla or '?'}"
                + (f" (id={e.registro_id})" if e.registro_id else "")
            ),
            "id_evento": e.id,
        })
    for e in ia_eventos:
        items.append({
            "timestamp": (
                e.creado_en.isoformat() if e.creado_en else None
            ),
            "tipo": "AI_CALL",
            "usuario": getattr(e, "usuario_email", None),
            "descripcion": (
                f"{getattr(e, 'modelo', '?')} "
                f"({getattr(e, 'tipo_operacion', '?')})"
            ),
            "id_evento": e.id,
        })

    # Mezclar y reordenar DESC por timestamp
    items.sort(
        key=lambda x: x["timestamp"] or "",
        reverse=True,
    )

    return {
        "limit": int(limit),
        "total_devueltos": len(items[:limit]),
        "items": items[:limit],
    }


@router.get("/usuarios-inactivos")
def admin_usuarios_inactivos(
    dias: int = 60,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R98 P2: usuarios sin actividad reciente (basado en audit log).

    Útil para que el admin identifique cuentas candidatas a desactivar
    por no-uso (cleanup de licencias, política de mínimos accesos).

    Considera "actividad" cualquier evento del usuario en audit_log
    en los últimos `dias` días (default 60).

    Devuelve usuarios activos en BD que NO han tenido eventos:
      - id, email, nombre, rol
      - ultimo_evento_en (puede ser null si nunca tuvo)
      - dias_sin_actividad

    Ordenado DESC por dias_sin_actividad. Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    ahora = ahora_utc()
    corte = ahora - timedelta(days=int(dias))

    # Fecha del último evento por email (todos los usuarios)
    eventos_por_email: dict[str, "object"] = {}
    rows = (
        db.query(
            AuditLogRecord.usuario_email,
            AuditLogRecord.timestamp,
        )
        .filter(AuditLogRecord.usuario_email.isnot(None))
        .all()
    )
    for email, ts in rows:
        if not ts:
            continue
        prev = eventos_por_email.get(email)
        if prev is None or ts > prev:
            eventos_por_email[email] = ts

    activos = (
        db.query(UsuarioRecord)
        .filter(UsuarioRecord.activo == 1)
        .all()
    )

    inactivos = []
    for u in activos:
        ult = eventos_por_email.get(u.email)
        # Normalizar tz si SQLite devuelve naive
        if ult is not None and getattr(ult, "tzinfo", None) is None:
            from datetime import timezone
            ult = ult.replace(tzinfo=timezone.utc)

        if ult and ult >= corte:
            continue  # tiene actividad reciente

        dias_sin = (
            (ahora - ult).days if ult else None
        )
        inactivos.append({
            "id": u.id,
            "email": u.email,
            "nombre": u.nombre,
            "rol": u.rol,
            "ultimo_evento_en": ult.isoformat() if ult else None,
            "dias_sin_actividad": dias_sin,
        })

    # nulls al final, los más antiguos arriba
    inactivos.sort(
        key=lambda x: (x["dias_sin_actividad"] is None,
                       -(x["dias_sin_actividad"] or 0)),
    )

    return {
        "umbral_dias": int(dias),
        "total_inactivos": len(inactivos),
        "items": inactivos,
    }


@router.get("/distribucion-cargas")
def admin_distribucion_cargas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R95 P2: distribución de cargas de glosas por gestor.

    Útil para que el coordinador detecte:
      - Gestores sobrecargados (re-balancear)
      - Gestores subutilizados
      - Glosas sin asignar (nadie las está procesando)

    Devuelve por gestor (incluyendo "SIN_ASIGNAR"):
      - total_glosas (abiertas, no cerradas)
      - vencidas (dias_restantes < 0)
      - criticas (0 <= dias_restantes <= 3)
      - valor_objetado_total
      - tasa_atraso_pct (vencidas / total)

    Ordenado DESC por total_glosas. Solo SUPER_ADMIN.
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    por_gestor: dict[str, dict] = {}
    for g in abiertas:
        gestor = (g.gestor_nombre or "").strip() or "SIN_ASIGNAR"
        if gestor not in por_gestor:
            por_gestor[gestor] = {
                "total": 0, "vencidas": 0, "criticas": 0,
                "valor_objetado": 0.0,
            }
        b = por_gestor[gestor]
        b["total"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)

        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            b["vencidas"] += 1
        elif dr <= 3:
            b["criticas"] += 1

    items = []
    for gestor, b in por_gestor.items():
        tasa = (
            round(100 * b["vencidas"] / b["total"], 2)
            if b["total"] else 0.0
        )
        items.append({
            "gestor": gestor,
            "total_glosas": b["total"],
            "vencidas": b["vencidas"],
            "criticas": b["criticas"],
            "valor_objetado_total": int(b["valor_objetado"]),
            "tasa_atraso_pct": tasa,
        })
    items.sort(key=lambda x: x["total_glosas"], reverse=True)

    return {
        "total_gestores": len(items),
        "total_glosas_abiertas": len(abiertas),
        "items": items,
    }


@router.post("/recalcular-dias-restantes")
def recalcular_dias_restantes(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R91 P1: recalcula dias_restantes para todas las glosas activas
    basado en fecha_vencimiento actual.

    El campo dias_restantes se mantiene sincronizado por triggers
    al crear/actualizar glosas, pero puede desincronizarse cuando:
      - Se importan glosas masivamente sin recalc
      - El cron diario falla
      - Se modifica fecha_vencimiento manualmente

    Estrategia:
      - Solo glosas no-cerradas (estado != ACEPTADA, LEVANTADA,
        ARCHIVADA, CONCILIADA)
      - dias_nuevo = (fecha_vencimiento - now).days
      - dry_run=True solo cuenta cuántas se actualizarían sin tocar BD

    Solo SUPER_ADMIN.
    """
    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    activas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_vencimiento.isnot(None))
        .all()
    )

    ahora = ahora_utc()
    actualizadas = 0
    sin_cambios = 0
    cerradas_ignoradas = 0

    for g in activas:
        if (g.estado or "").upper() in ESTADOS_CERRADOS:
            cerradas_ignoradas += 1
            continue

        # SQLite puede devolver fechas naive — normalizar a UTC tz-aware
        # para comparar de forma uniforme con ahora_utc().
        venc = g.fecha_vencimiento
        if venc.tzinfo is None:
            from datetime import timezone
            venc = venc.replace(tzinfo=timezone.utc)

        delta_dias = (venc - ahora).days
        anterior = g.dias_restantes if g.dias_restantes is not None else 0

        if anterior == delta_dias:
            sin_cambios += 1
            continue

        if not dry_run:
            g.dias_restantes = delta_dias
        actualizadas += 1

    if not dry_run and actualizadas:
        db.commit()

    return {
        "total_glosas_evaluadas": len(activas),
        "actualizadas": actualizadas,
        "sin_cambios": sin_cambios,
        "cerradas_ignoradas": cerradas_ignoradas,
        "dry_run": bool(dry_run),
        "ejecutado_por": current_user.email,
        "ejecutado_en": ahora.isoformat(),
    }


@router.get("/system-info")
def admin_system_info(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R73 P2: información operativa consolidada del sistema.

    Datos útiles para soporte y operaciones día-a-día:
      - Conteos: cuántas glosas, contratos, plantillas Gold, etc.
      - Última actividad: cuándo se creó la última glosa, último login
      - Métricas IA agregadas (últimos 30 días)
      - Estado de schedulers
      - Variables de entorno SI están configuradas (sin revelar valores)

    Solo SUPER_ADMIN.
    """
    import os
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import (
        AICacheRecord, AICallRecord, AuditLogRecord,
        ContratoRecord, GlosaEliminadaRecord, GlosaRecord,
        PlantillaGoldRecord, TarifaContratadaRecord,
    )

    desde_30 = ahora_utc() - timedelta(days=30)

    # Conteos por tabla
    counts = {
        "glosas": db.query(_f.count(GlosaRecord.id)).scalar() or 0,
        "usuarios": db.query(_f.count(UsuarioRecord.id)).scalar() or 0,
        "contratos": db.query(_f.count(ContratoRecord.eps)).scalar() or 0,
        "tarifas_contratadas": db.query(_f.count(TarifaContratadaRecord.id)).scalar() or 0,
        "plantillas_gold_activas": (
            db.query(_f.count(PlantillaGoldRecord.id))
            .filter(PlantillaGoldRecord.activa == 1).scalar() or 0
        ),
        "ai_cache": db.query(_f.count(AICacheRecord.id)).scalar() or 0,
        "ai_calls_30d": (
            db.query(_f.count(AICallRecord.id))
            .filter(AICallRecord.creado_en >= desde_30).scalar() or 0
        ),
        "audit_log_30d": (
            db.query(_f.count(AuditLogRecord.id))
            .filter(AuditLogRecord.timestamp >= desde_30).scalar() or 0
        ),
        "papelera": db.query(_f.count(GlosaEliminadaRecord.id)).scalar() or 0,
    }

    # Última actividad
    ultima_glosa = (
        db.query(_f.max(GlosaRecord.creado_en)).scalar()
    )

    # Costo IA total (30d)
    cost_30d = (
        db.query(_f.sum(AICallRecord.cost_usd))
        .filter(AICallRecord.creado_en >= desde_30).scalar() or 0
    )

    # Estado de schedulers
    scheduler_pre, scheduler_mant = True, True
    try:
        from app.services.ia_auditora_proactiva import _task as _t_pa
        scheduler_pre = _t_pa is not None and not _t_pa.done()
    except Exception:
        scheduler_pre = None
    try:
        from app.services.mantenimiento_scheduler import _task as _t_mant
        scheduler_mant = _t_mant is not None and not _t_mant.done()
    except Exception:
        scheduler_mant = None

    # Env vars: solo si están definidas, NO sus valores
    env_status = {
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        "GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
        "SENTRY_DSN": bool(os.getenv("SENTRY_DSN")),
        "FIRMA_DIGITAL_PRIVATE_KEY": bool(os.getenv("FIRMA_DIGITAL_PRIVATE_KEY")),
        "GLOSAS_ENCRYPTION_KEY": bool(os.getenv("GLOSAS_ENCRYPTION_KEY")),
        "DIGEST_DESTINATARIOS": bool(os.getenv("DIGEST_DESTINATARIOS")),
        "ALERTAS_EMAIL": bool(os.getenv("ALERTAS_EMAIL")),
    }

    return {
        "counts": counts,
        "ultima_glosa_creada_en": (
            ultima_glosa.isoformat() if ultima_glosa else None
        ),
        "ia_cost_usd_30d": round(float(cost_30d), 4),
        "schedulers": {
            "pre_analisis": scheduler_pre,
            "mantenimiento": scheduler_mant,
        },
        "env_configurada": env_status,
        "consultado_por": current_user.email,
        "consultado_en": ahora_utc().isoformat(),
    }


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
