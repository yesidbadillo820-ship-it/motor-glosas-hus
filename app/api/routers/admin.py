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


@router.get("/usuarios-actividad-resumen")
def admin_usuarios_actividad_resumen(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R346 P1: por usuario, count agregado de actividad audit.

    Por usuario_email, count de eventos audit_log en los
    últimos N días con desglose por accion y por tabla.
    Útil para auditoría: "¿quién está más activo?".

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .filter(AuditLogRecord.usuario_email.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for e in rows:
        email = (e.usuario_email or "").strip()
        if not email:
            continue
        b = bucket.setdefault(email, {
            "count": 0, "acciones": {}, "tablas": {},
        })
        b["count"] += 1
        a = (e.accion or "?").upper()
        t = (e.tabla or "?").lower()
        b["acciones"][a] = b["acciones"].get(a, 0) + 1
        b["tablas"][t] = b["tablas"].get(t, 0) + 1

    items = []
    for email, b in bucket.items():
        items.append({
            "usuario_email": email,
            "count_total": b["count"],
            "acciones": b["acciones"],
            "tablas": b["tablas"],
        })
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_usuarios": len(items),
        "items": items,
    }


@router.get("/asignaciones-recientes")
def admin_asignaciones_recientes(
    dias: int = 7,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R345 P1: vista global de glosas con cambio reciente
    de gestor_nombre.

    Lista del audit_log entries de cambios en
    gestor_nombre en los últimos N días. Útil para
    auditar reasignaciones realizadas por el coordinador.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .filter(AuditLogRecord.campo == "gestor_nombre")
        .order_by(AuditLogRecord.timestamp.desc())
        .all()
    )

    items = []
    for e in rows:
        items.append({
            "audit_id": e.id,
            "timestamp": (
                e.timestamp.isoformat() if e.timestamp else None
            ),
            "glosa_id": e.registro_id,
            "valor_anterior": e.valor_anterior,
            "valor_nuevo": e.valor_nuevo,
            "usuario_email": e.usuario_email,
        })

    return {
        "ventana_dias": int(dias),
        "total_reasignaciones": len(items),
        "items": items,
    }


@router.get("/anomalias-asignacion")
def admin_anomalias_asignacion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R390 P1: la IA detecta inequidades en la asignación.

    Reglas:
      - GESTOR_ESPECIALIZADO: gestor maneja >= 80% de las
        glosas de una EPS (riesgo de bus-factor)
      - EPS_DESATENDIDA: EPS con > 5 glosas abiertas y
        ningún gestor con histórico decidido en ella
      - VALOR_CONCENTRADO: gestor con >= 50% del valor
        objetado pendiente del equipo

    Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    todas = db.query(GlosaRecord).all()
    abiertas = [
        g for g in todas
        if (g.estado or "").upper() not in ESTADOS_CERRADOS
    ]

    # GESTOR_ESPECIALIZADO: por EPS, qué gestor toma > 80%
    eps_glosas: dict[str, dict[str, int]] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        gestor = (g.gestor_nombre or "").strip()
        if not eps or not gestor:
            continue
        eps_glosas.setdefault(eps, {})
        eps_glosas[eps][gestor] = eps_glosas[eps].get(gestor, 0) + 1

    items = []
    for eps, by_gestor in eps_glosas.items():
        total = sum(by_gestor.values())
        if total < 10:
            continue
        for gestor, count in by_gestor.items():
            ratio = count / total
            if ratio >= 0.8:
                items.append({
                    "tipo": "GESTOR_ESPECIALIZADO",
                    "gestor": gestor,
                    "eps": eps,
                    "count": count,
                    "ratio_pct": round(100 * ratio, 1),
                    "mensaje": (
                        f"{gestor} concentra el "
                        f"{ratio*100:.0f}% de las {total} "
                        f"glosas abiertas de {eps}. "
                        "Considera repartir para reducir bus-factor."
                    ),
                })

    # EPS_DESATENDIDA: EPS con >5 abiertas y ningún gestor con histórico
    historico_decidido_por_eps: dict[str, set] = {}
    for g in todas:
        eps = (g.eps or "").strip()
        gestor = (g.gestor_nombre or "").strip()
        if not eps or not gestor:
            continue
        if (g.estado or "").upper() in ESTADOS_DECIDIDOS:
            historico_decidido_por_eps.setdefault(eps, set()).add(gestor)

    abiertas_por_eps: dict[str, int] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        if eps:
            abiertas_por_eps[eps] = abiertas_por_eps.get(eps, 0) + 1

    for eps, count in abiertas_por_eps.items():
        if count < 6:
            continue
        if not historico_decidido_por_eps.get(eps):
            items.append({
                "tipo": "EPS_DESATENDIDA",
                "eps": eps,
                "abiertas": count,
                "mensaje": (
                    f"{eps} tiene {count} glosas abiertas y "
                    "ningún gestor del equipo cerró nunca una. "
                    "Asignar a alguien con experiencia."
                ),
            })

    # VALOR_CONCENTRADO: gestor con >50% del valor pendiente
    bucket_v: dict[str, float] = {}
    valor_total = 0.0
    for g in abiertas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        v = float(g.valor_objetado or 0)
        bucket_v[gestor] = bucket_v.get(gestor, 0.0) + v
        valor_total += v
    if valor_total > 0:
        for gestor, v in bucket_v.items():
            ratio = v / valor_total
            if ratio >= 0.5:
                items.append({
                    "tipo": "VALOR_CONCENTRADO",
                    "gestor": gestor,
                    "valor_pendiente": int(v),
                    "ratio_pct": round(100 * ratio, 1),
                    "mensaje": (
                        f"{gestor} concentra el "
                        f"{ratio*100:.0f}% del valor pendiente "
                        f"(${int(v):,}). Riesgo financiero "
                        "si se va o se atrasa."
                    ),
                })

    return {
        "total_anomalias": len(items),
        "items": items,
    }


@router.get("/insight-financiero")
def admin_insight_financiero(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R386 P1: insight financiero ejecutivo (single-call).

    Resumen para CFO / coordinador:
      - top_3_eps_recuperacion: las EPS donde mejor
        recuperamos $ (sobre valor objetado)
      - bottom_3_eps_recuperacion: peores
      - tasa_recuperacion_global_pct
      - valor_recuperado_total
      - valor_objetado_total

    Solo SUPER_ADMIN.
    """
    decididas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(
            ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
        ))
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    obj_global = 0.0
    rec_global = 0.0
    for g in decididas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(eps, {"obj": 0.0, "rec": 0.0, "n": 0})
        v_obj = float(g.valor_objetado or 0)
        v_rec = float(g.valor_recuperado or 0)
        b["obj"] += v_obj
        b["rec"] += v_rec
        b["n"] += 1
        obj_global += v_obj
        rec_global += v_rec

    items = []
    for eps, b in bucket.items():
        if b["n"] < 3 or b["obj"] <= 0:
            continue
        tasa = round(100 * b["rec"] / b["obj"], 2)
        items.append({
            "eps": eps,
            "n_decididas": b["n"],
            "valor_objetado": int(b["obj"]),
            "valor_recuperado": int(b["rec"]),
            "tasa_recuperacion_pct": tasa,
        })
    items.sort(
        key=lambda x: x["tasa_recuperacion_pct"], reverse=True,
    )

    tasa_global = (
        round(100 * rec_global / obj_global, 2) if obj_global else 0.0
    )

    return {
        "tasa_recuperacion_global_pct": tasa_global,
        "valor_objetado_total": int(obj_global),
        "valor_recuperado_total": int(rec_global),
        "top_3_eps_recuperacion": items[:3],
        "bottom_3_eps_recuperacion": list(reversed(items[-3:]))
        if len(items) >= 3 else [],
        "total_eps_evaluadas": len(items),
    }


@router.get("/equipo-pulse")
def admin_equipo_pulse(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R384 P1: pulso del equipo (single-call para admin).

    Resumen rápido del estado del equipo: total gestores
    activos, glosas abiertas totales, vencidas globales,
    top 3 gestores con más vencidas, gestores
    sobrecargados/subcargados (mediana). Todo en una
    sola llamada para el dashboard del coordinador.

    Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )
    n_total_abiertas = len(abiertas)
    n_total_vencidas = sum(
        1 for g in abiertas if (g.dias_restantes or 0) < 0
    )

    bucket: dict[str, dict] = {}
    sin_gestor = 0
    for g in abiertas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            sin_gestor += 1
            continue
        b = bucket.setdefault(gestor, {
            "count": 0, "vencidas": 0, "valor": 0.0,
        })
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        if (g.dias_restantes or 0) < 0:
            b["vencidas"] += 1

    if bucket:
        counts_ord = sorted(b["count"] for b in bucket.values())
        mediana = counts_ord[len(counts_ord) // 2]
        umbral_alto = max(int(mediana * 1.5), mediana + 5)
        umbral_bajo = max(int(mediana * 0.5), 1)
    else:
        mediana = umbral_alto = umbral_bajo = 0

    sobrecargados = []
    subcargados = []
    for gestor, b in bucket.items():
        if b["count"] >= umbral_alto:
            sobrecargados.append({
                "gestor": gestor,
                "abiertas": b["count"],
                "vencidas": b["vencidas"],
            })
        elif b["count"] <= umbral_bajo:
            subcargados.append({
                "gestor": gestor,
                "abiertas": b["count"],
            })

    top_vencidas = sorted(
        [
            {
                "gestor": g,
                "vencidas": b["vencidas"],
                "abiertas": b["count"],
            }
            for g, b in bucket.items() if b["vencidas"] > 0
        ],
        key=lambda x: x["vencidas"], reverse=True,
    )[:3]

    # Sugerencias usuarios SUPER_ADMIN/COORDINADOR
    activos = (
        db.query(UsuarioRecord)
        .filter(UsuarioRecord.activo == 1)
        .count()
    )

    return {
        "total_gestores_con_carga": len(bucket),
        "total_usuarios_activos": activos,
        "abiertas_totales": n_total_abiertas,
        "vencidas_globales": n_total_vencidas,
        "glosas_sin_gestor": sin_gestor,
        "mediana_carga": int(mediana),
        "sobrecargados": sobrecargados,
        "subcargados": subcargados,
        "top_3_con_vencidas": top_vencidas,
    }


@router.get("/balance-carga-gestores")
def admin_balance_carga_gestores(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R379 P1: balance de carga del equipo.

    Para cada gestor con glosas abiertas calcula counts,
    valor pendiente y un estado_carga:
      SOBRECARGADO (>= mediana × 1.5)
      NORMAL
      SUBCARGADO (<= mediana × 0.5)

    Útil para rebalancear asignaciones objetivamente.
    Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .filter(GlosaRecord.gestor_nombre != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in abiertas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        b = bucket.setdefault(gestor, {
            "count": 0, "vencidas": 0, "criticas": 0, "valor": 0.0,
        })
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            b["vencidas"] += 1
        elif dr <= 3:
            b["criticas"] += 1

    if not bucket:
        return {"total_gestores": 0, "items": []}

    counts = sorted(b["count"] for b in bucket.values())
    mediana = counts[len(counts) // 2]
    umbral_alto = max(int(mediana * 1.5), mediana + 5)
    umbral_bajo = max(int(mediana * 0.5), 1)

    items = []
    for gestor, b in bucket.items():
        if b["count"] >= umbral_alto:
            estado = "SOBRECARGADO"
        elif b["count"] <= umbral_bajo:
            estado = "SUBCARGADO"
        else:
            estado = "NORMAL"
        items.append({
            "gestor": gestor,
            "count_abiertas": b["count"],
            "count_vencidas": b["vencidas"],
            "count_criticas": b["criticas"],
            "valor_objetado_pendiente": int(b["valor"]),
            "estado_carga": estado,
        })
    items.sort(key=lambda x: x["count_abiertas"], reverse=True)

    return {
        "total_gestores": len(items),
        "mediana_abiertas": int(mediana),
        "umbral_sobrecarga": int(umbral_alto),
        "umbral_subcarga": int(umbral_bajo),
        "items": items,
    }


@router.get("/auto-asignacion-sugerencias")
def admin_auto_asignacion_sugerencias(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R377 P1: la IA sugiere a quién asignar cada glosa
    abierta sin gestor.

    Para cada glosa abierta sin gestor, busca el gestor
    con mejor tasa histórica para el par (eps,
    codigo_glosa). Si no hay datos, sugiere el de mejor
    tasa global con esa EPS. Útil para asignación
    masiva inteligente del coordinador.

    Por glosa:
      - glosa_id, eps, codigo_glosa, valor_objetado
      - gestor_sugerido (con tasa y muestras)
      - razon (por qué se sugiere)

    Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    sin_gestor = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(
            (GlosaRecord.gestor_nombre.is_(None))
            | (GlosaRecord.gestor_nombre == "")
        )
        .order_by(GlosaRecord.valor_objetado.desc())
        .limit(int(limit))
        .all()
    )

    if not sin_gestor:
        return {
            "total_pendientes": 0,
            "items": [],
        }

    # Pre-cargar histórico decidido relevante en una sola pasada
    epss = {(g.eps or "").strip() for g in sin_gestor if g.eps}
    historicas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .filter(GlosaRecord.eps.in_(epss))
        .all()
    ) if epss else []

    # Indexamos por par y por eps
    par_idx: dict[tuple, dict] = {}
    eps_idx: dict[str, dict] = {}
    for h in historicas:
        eps = (h.eps or "").strip()
        cod = (h.codigo_glosa or "").strip()
        gestor = (h.gestor_nombre or "").strip()
        if not eps or not gestor:
            continue
        # par index
        kp = (eps, cod, gestor)
        bp = par_idx.setdefault(kp, {"dec": 0, "lev": 0})
        bp["dec"] += 1
        if (h.estado or "").upper() == "LEVANTADA":
            bp["lev"] += 1
        # eps index
        ke = (eps, gestor)
        be = eps_idx.setdefault(ke, {"dec": 0, "lev": 0})
        be["dec"] += 1
        if (h.estado or "").upper() == "LEVANTADA":
            be["lev"] += 1

    items = []
    for g in sin_gestor:
        eps = (g.eps or "").strip()
        cod = (g.codigo_glosa or "").strip()

        # Buscar mejor gestor en par (eps, codigo)
        candidatos_par = [
            (gestor, b["dec"], b["lev"])
            for (e, c, gestor), b in par_idx.items()
            if e == eps and c == cod and b["dec"] >= 2
        ]
        sugerido = None
        razon = None
        if candidatos_par:
            candidatos_par.sort(
                key=lambda x: (100*x[2]/x[1], x[1]), reverse=True,
            )
            ge, dec, lev = candidatos_par[0]
            sugerido = {
                "gestor": ge,
                "tasa_pct": round(100*lev/dec, 2),
                "muestras": dec,
                "fuente": "par_eps_codigo",
            }
            razon = f"Mejor tasa en (EPS, código) con {dec} casos"
        else:
            # Fallback: mejor en EPS global
            candidatos_eps = [
                (gestor, b["dec"], b["lev"])
                for (e, gestor), b in eps_idx.items()
                if e == eps and b["dec"] >= 3
            ]
            if candidatos_eps:
                candidatos_eps.sort(
                    key=lambda x: (100*x[2]/x[1], x[1]), reverse=True,
                )
                ge, dec, lev = candidatos_eps[0]
                sugerido = {
                    "gestor": ge,
                    "tasa_pct": round(100*lev/dec, 2),
                    "muestras": dec,
                    "fuente": "eps_global",
                }
                razon = f"Sin datos del par; mejor en la EPS con {dec} casos"
            else:
                razon = "Sin datos históricos suficientes"

        items.append({
            "glosa_id": g.id,
            "eps": eps,
            "codigo_glosa": cod,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "dias_restantes": g.dias_restantes,
            "gestor_sugerido": sugerido,
            "razon": razon,
        })

    return {
        "total_pendientes": len(items),
        "items": items,
    }


@router.get("/glosas-altas-cuantia-vencidas")
def admin_glosas_altas_cuantia_vencidas(
    umbral: float = 5_000_000,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R367 P1: alta cuantía + vencidas (intersección crítica).

    Glosas abiertas con valor_objetado >= umbral Y
    dias_restantes < 0. Esto es el "red flag" del CFO:
    casos grandes en mora.

    Solo SUPER_ADMIN. Ordena DESC por valor_objetado.
    """
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    rows = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < 0)
        .filter(GlosaRecord.valor_objetado >= float(umbral))
        .order_by(GlosaRecord.valor_objetado.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "dias_vencido": abs(int(g.dias_restantes or 0)),
            "gestor_nombre": g.gestor_nombre,
        })

    return {
        "umbral": int(umbral),
        "total_red_flags": len(items),
        "valor_total": sum(it["valor_objetado"] for it in items),
        "items": items,
    }


@router.get("/glosas-saldo-cero-detalle")
def admin_glosas_saldo_cero_detalle(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R360 P1: glosas abiertas con saldo_factura = 0.

    Una glosa abierta sin saldo pendiente es ambigua:
    posiblemente fue pagada parcialmente, mal codificada,
    o falta actualizar. Útil para ronda de calidad.

    Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(
            (GlosaRecord.saldo_factura == 0)
            | (GlosaRecord.saldo_factura.is_(None))
        )
        .filter(GlosaRecord.valor_factura > 0)
        .order_by(GlosaRecord.valor_factura.desc())
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "valor_factura": int(float(g.valor_factura or 0)),
            "saldo_factura": int(float(g.saldo_factura or 0)),
        })

    return {
        "total_glosas_anomalas": len(items),
        "items": items[: int(limit)],
    }


@router.get("/glosas-vencen-manana")
def admin_glosas_vencen_manana(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R358 P1: glosas que vencen mañana (dias_restantes == 1).

    Vista crítica del coordinador: cada caso requiere
    decisión hoy mismo. Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes == 1)
        .order_by(GlosaRecord.valor_objetado.desc())
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
            "gestor_nombre": g.gestor_nombre,
        })

    return {
        "total_vencen_manana": len(items),
        "valor_total": sum(it["valor_objetado"] for it in items),
        "items": items,
    }


@router.get("/eps-tendencia-volumen")
def admin_eps_tendencia_volumen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R355 P1: tendencia de volumen por EPS mes vs mes anterior.

    Para cada EPS, compara volumen del mes en curso vs el
    anterior. Útil para detectar EPS que están enviando
    más glosas (señal de cambio de patrón).

    Solo SUPER_ADMIN.
    """
    from datetime import timezone

    from app.core.tz import ahora_utc

    ahora = ahora_utc()
    inicio_actual = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    if inicio_actual.month == 1:
        inicio_anterior = inicio_actual.replace(
            year=inicio_actual.year - 1, month=12,
        )
    else:
        inicio_anterior = inicio_actual.replace(
            month=inicio_actual.month - 1,
        )

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= inicio_anterior)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    actual: dict[str, int] = {}
    anterior: dict[str, int] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        if cre >= inicio_actual:
            actual[eps] = actual.get(eps, 0) + 1
        else:
            anterior[eps] = anterior.get(eps, 0) + 1

    todos = set(actual) | set(anterior)
    items = []
    for eps in todos:
        a = actual.get(eps, 0)
        p = anterior.get(eps, 0)
        if p == 0:
            delta_pct = 100.0 if a > 0 else 0.0
        else:
            delta_pct = round(100 * (a - p) / p, 2)
        items.append({
            "eps": eps,
            "count_actual": a,
            "count_anterior": p,
            "delta_abs": a - p,
            "delta_pct": delta_pct,
        })
    items.sort(key=lambda x: x["delta_pct"], reverse=True)

    return {
        "mes_actual": inicio_actual.strftime("%Y-%m"),
        "mes_anterior": inicio_anterior.strftime("%Y-%m"),
        "total_eps": len(items),
        "items": items,
    }


@router.get("/comentarios-no-resueltos")
def admin_comentarios_no_resueltos(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R353 P1: glosas con más comentarios sin resolver.

    Cuenta comentarios donde resuelto=0 por glosa. Útil
    para identificar casos con discusión pendiente.

    Solo SUPER_ADMIN.
    """
    from app.models.db import ComentarioGlosaRecord

    rows = (
        db.query(ComentarioGlosaRecord)
        .filter(
            (ComentarioGlosaRecord.resuelto == 0)
            | (ComentarioGlosaRecord.resuelto.is_(None))
        )
        .all()
    )

    bucket: dict[int, dict] = {}
    for c in rows:
        if not c.glosa_id:
            continue
        b = bucket.setdefault(c.glosa_id, {
            "count": 0, "menciones": 0, "ultimo_autor": None,
        })
        b["count"] += 1
        if c.mencion:
            b["menciones"] += 1
        b["ultimo_autor"] = c.autor_email

    items = []
    for g_id, b in bucket.items():
        items.append({
            "glosa_id": g_id,
            "comentarios_no_resueltos": b["count"],
            "menciones_pendientes": b["menciones"],
            "ultimo_autor": b["ultimo_autor"],
        })
    items.sort(
        key=lambda x: x["comentarios_no_resueltos"], reverse=True,
    )

    return {
        "total_glosas": len(items),
        "items": items[: int(limit)],
    }


@router.get("/codigo-respuesta-cobertura")
def admin_codigo_respuesta_cobertura(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R343 P1: cobertura del uso de codigo_respuesta.

    Por codigo_respuesta de HUS:
      - count_total
      - eps_distintas (con cuántas EPS se usó)
      - codigos_glosa_distintos (en respuesta a cuántos)
      - ratio_eps_por_uso

    Útil para ver si HUS usa los códigos "ampliamente"
    (muchas EPS) o "específicamente" (pocas).

    Solo SUPER_ADMIN.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.codigo_respuesta != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        c = (g.codigo_respuesta or "").strip()
        if not c:
            continue
        b = bucket.setdefault(c, {
            "count": 0, "eps": set(), "codigos": set(),
        })
        b["count"] += 1
        if g.eps:
            b["eps"].add(g.eps.strip())
        if g.codigo_glosa:
            b["codigos"].add(g.codigo_glosa.strip())

    items = []
    for c, b in bucket.items():
        n_eps = len(b["eps"])
        ratio = round(n_eps / b["count"], 3) if b["count"] else 0.0
        items.append({
            "codigo_respuesta": c,
            "count_total": b["count"],
            "eps_distintas": n_eps,
            "codigos_glosa_distintos": len(b["codigos"]),
            "ratio_eps_por_uso": ratio,
        })
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "items": items,
    }


@router.get("/audit-cambios-criticos")
def admin_audit_cambios_criticos(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R341 P1: cambios audit en campos críticos.

    Cuenta cambios en campos críticos (estado, eps,
    valor_objetado, gestor_nombre) en los últimos N días.
    Cambios manuales en estos campos son sensibles —
    útil revisar quién los hace.

    Por campo:
      - count_cambios
      - usuarios_distintos
      - top_3_usuarios

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc

    CAMPOS_CRITICOS = [
        "estado", "eps", "valor_objetado", "gestor_nombre",
        "auditor_email", "fecha_decision_eps",
    ]

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .filter(AuditLogRecord.campo.in_(CAMPOS_CRITICOS))
        .all()
    )

    bucket: dict[str, dict] = {}
    for e in rows:
        campo = e.campo
        b = bucket.setdefault(campo, {
            "count": 0, "usuarios": {},
        })
        b["count"] += 1
        u = e.usuario_email or "?"
        b["usuarios"][u] = b["usuarios"].get(u, 0) + 1

    items = []
    for campo, b in bucket.items():
        top3 = sorted(
            b["usuarios"].items(), key=lambda x: x[1], reverse=True,
        )[:3]
        items.append({
            "campo": campo,
            "count_cambios": b["count"],
            "usuarios_distintos": len(b["usuarios"]),
            "top_3_usuarios": [
                {"usuario_email": u, "count": c}
                for u, c in top3
            ],
        })
    items.sort(key=lambda x: x["count_cambios"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "items": items,
    }


@router.get("/conciliaciones-bilateral-resumen")
def admin_conciliaciones_bilateral_resumen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R328 P1: distribución de conciliaciones por estado_bilateral.

    Estados del ciclo bilateral HUS-EPS (campo
    estado_bilateral del modelo ConciliacionRecord):
      PROGRAMADA → EPS_RESPONDIO → AUDIENCIA_REALIZADA →
      ACTA_FIRMADA → CERRADA

    Útil para ver cuántas conciliaciones están en cada
    paso del flujo bilateral.

    Solo SUPER_ADMIN.
    """
    from app.models.db import ConciliacionRecord

    rows = db.query(ConciliacionRecord).all()

    bucket: dict[str, dict] = {}
    for c in rows:
        estado = (c.estado_bilateral or "?").upper()
        b = bucket.setdefault(estado, {
            "count": 0, "valor": 0.0, "valor_ratificado": 0.0,
        })
        b["count"] += 1
        b["valor"] += float(c.valor_conciliado or 0)
        b["valor_ratificado"] += float(c.valor_ratificado_hus or 0)

    items = []
    for estado, b in bucket.items():
        items.append({
            "estado_bilateral": estado,
            "count": b["count"],
            "valor_conciliado_total": int(b["valor"]),
            "valor_ratificado_hus_total": int(b["valor_ratificado"]),
        })
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_conciliaciones": sum(it["count"] for it in items),
        "items": items,
    }


@router.get("/audit-log-stats")
def admin_audit_log_stats(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R326 P1: distribución de eventos audit_log por acción.

    Cuenta los eventos audit_log por valor de `accion`
    (UPDATE, INSERT, DELETE, LOGIN, etc.) en los últimos
    N días. Útil para entender patrones de uso del
    sistema.

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .all()
    )

    total = len(rows)

    bucket: dict[str, int] = {}
    for e in rows:
        accion = (e.accion or "?").upper()
        bucket[accion] = bucket.get(accion, 0) + 1

    items = []
    for accion, c in bucket.items():
        items.append({
            "accion": accion,
            "count": c,
            "pct": round(100 * c / total, 2) if total else 0.0,
        })
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_eventos": total,
        "items": items,
    }


@router.get("/cierre-mes-anterior")
def admin_cierre_mes_anterior(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R316 P1: cierre del mes anterior (retrospectiva).

    Snapshot agregado de las glosas cerradas el mes
    anterior:
      - count_decididas, count_levantadas, count_ratificadas
      - tasa_levantamiento_pct
      - valor_objetado_total, valor_recuperado_total
      - tasa_recuperacion_monetaria_pct
      - top_gestores: 5 gestores con más decisiones

    Útil para reporte mensual al comité directivo.
    Solo SUPER_ADMIN.
    """
    from datetime import timezone

    from app.core.tz import ahora_utc

    ahora = ahora_utc()
    inicio_mes_actual = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    if inicio_mes_actual.month == 1:
        inicio_anterior = inicio_mes_actual.replace(
            year=inicio_mes_actual.year - 1, month=12,
        )
    else:
        inicio_anterior = inicio_mes_actual.replace(
            month=inicio_mes_actual.month - 1,
        )

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= inicio_anterior)
        .filter(GlosaRecord.fecha_decision_eps < inicio_mes_actual)
        .filter(GlosaRecord.estado.in_(
            ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
        ))
        .all()
    )

    levantadas = sum(
        1 for g in glosas
        if (g.estado or "").upper() == "LEVANTADA"
    )
    ratificadas = sum(
        1 for g in glosas
        if (g.estado or "").upper() == "RATIFICADA"
    )
    n = len(glosas)
    obj_total = sum(float(g.valor_objetado or 0) for g in glosas)
    rec_total = sum(float(g.valor_recuperado or 0) for g in glosas)

    tasa_lev = round(100 * levantadas / n, 2) if n else 0.0
    tasa_rec = (
        round(100 * rec_total / obj_total, 2) if obj_total else 0.0
    )

    por_gestor: dict[str, int] = {}
    for g in glosas:
        gestor = (g.gestor_nombre or "").strip()
        if gestor:
            por_gestor[gestor] = por_gestor.get(gestor, 0) + 1
    top_gestores = sorted(
        por_gestor.items(), key=lambda x: x[1], reverse=True,
    )[:5]

    return {
        "mes": inicio_anterior.strftime("%Y-%m"),
        "count_decididas": n,
        "count_levantadas": levantadas,
        "count_ratificadas": ratificadas,
        "tasa_levantamiento_pct": tasa_lev,
        "valor_objetado_total": int(obj_total),
        "valor_recuperado_total": int(rec_total),
        "tasa_recuperacion_monetaria_pct": tasa_rec,
        "top_gestores": [
            {"gestor": g, "decididas": c}
            for g, c in top_gestores
        ],
    }


@router.get("/sugerencias-asignacion")
def admin_sugerencias_asignacion(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R315 P1: sugiere gestores con mejor tasa para una EPS.

    Útil al asignar nuevas glosas: "¿quién tiene mejor
    track record con SANITAS?". Devuelve gestores
    ordenados por tasa de levantamiento histórica con esa
    EPS específica.

    Por gestor:
      - count_decididas (volumen histórico con esa EPS)
      - levantadas
      - tasa_levantamiento_pct

    Solo SUPER_ADMIN.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.ilike(eps))
        .filter(GlosaRecord.estado.in_(
            ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
        ))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        b = bucket.setdefault(gestor, {"dec": 0, "lev": 0})
        b["dec"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1

    items = []
    for gestor, b in bucket.items():
        if b["dec"] < 1:
            continue
        tasa = round(100 * b["lev"] / b["dec"], 2)
        items.append({
            "gestor": gestor,
            "count_decididas": b["dec"],
            "levantadas": b["lev"],
            "tasa_levantamiento_pct": tasa,
        })
    items.sort(
        key=lambda x: (x["tasa_levantamiento_pct"], x["count_decididas"]),
        reverse=True,
    )

    return {
        "eps": eps,
        "total_gestores_con_historial": len(items),
        "items": items,
    }


@router.get("/conciliaciones-resultado-distribucion")
def admin_conciliaciones_resultado_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R312 P1: distribución de conciliaciones por `resultado`.

    Diferente a /stats/conciliaciones-mensual (serie
    temporal): aquí agregado total por resultado
    (FAVORABLE_HUS, RATIFICADA, PARCIAL, etc.) con count
    y valor_conciliado total.

    Útil para entender dónde se está cerrando el
    proceso bilateral.

    Solo SUPER_ADMIN.
    """
    from app.models.db import ConciliacionRecord

    rows = db.query(ConciliacionRecord).all()

    bucket: dict[str, dict] = {}
    for c in rows:
        res = (c.resultado or "SIN_RESULTADO").upper()
        b = bucket.setdefault(res, {"count": 0, "valor": 0.0})
        b["count"] += 1
        b["valor"] += float(c.valor_conciliado or 0)

    items = []
    for res, b in bucket.items():
        items.append({
            "resultado": res,
            "count": b["count"],
            "valor_conciliado_total": int(b["valor"]),
        })
    items.sort(key=lambda x: x["count"], reverse=True)

    total = sum(it["count"] for it in items)
    for it in items:
        it["pct"] = (
            round(100 * it["count"] / total, 2) if total else 0.0
        )

    return {
        "total_conciliaciones": total,
        "items": items,
    }


@router.get("/usuarios-mas-comentarios")
def admin_usuarios_mas_comentarios(
    dias: int = 90,
    top: int = 20,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R294 P1: ranking de usuarios por comentarios emitidos.

    Diferente a /admin/heatmap-usuario (todas las acciones):
    aquí solo se cuentan comentarios internos, que son
    indicador específico de colaboración entre el equipo.

    Por usuario:
      - total_comentarios
      - menciones_emitidas
      - resueltos_emitidos
      - glosas_distintas

    Solo SUPER_ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import ComentarioGlosaRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.creado_en >= desde)
        .filter(ComentarioGlosaRecord.autor_email.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for c in rows:
        email = (c.autor_email or "").strip()
        if not email:
            continue
        b = bucket.setdefault(email, {
            "total": 0, "menciones": 0, "resueltos": 0,
            "glosas": set(),
        })
        b["total"] += 1
        if c.mencion:
            b["menciones"] += 1
        if int(c.resuelto or 0) == 1:
            b["resueltos"] += 1
        if c.glosa_id:
            b["glosas"].add(c.glosa_id)

    items = []
    for email, b in bucket.items():
        items.append({
            "autor_email": email,
            "total_comentarios": b["total"],
            "menciones_emitidas": b["menciones"],
            "resueltos_emitidos": b["resueltos"],
            "glosas_distintas": len(b["glosas"]),
        })
    items.sort(key=lambda x: x["total_comentarios"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_usuarios": len(items),
        "items": items[: int(top)],
    }


@router.get("/eps-cartera-detalle")
def admin_eps_cartera_detalle(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R292 P1: drill-down completo de cartera para una EPS.

    Single-call con todo lo necesario para una revisión de
    cobranza:
      - resumen: counts y totales
      - top_facturas: 10 facturas con mayor saldo
      - top_codigos: 10 códigos más recurrentes en abiertas

    Solo SUPER_ADMIN.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.ilike(eps))
        .all()
    )

    if not rows:
        return {
            "eps": eps,
            "resumen": {
                "total": 0, "abiertas": 0, "cerradas": 0,
                "valor_objetado_total": 0, "saldo_total": 0,
            },
            "top_facturas": [],
            "top_codigos": [],
        }

    abiertas_count = 0
    cerradas_count = 0
    valor_total = 0.0
    saldo_total = 0.0
    facturas: dict[str, float] = {}
    codigos: dict[str, int] = {}

    for g in rows:
        valor_total += float(g.valor_objetado or 0)
        saldo_total += float(g.saldo_factura or 0)
        cerrada = (g.estado or "").upper() in ESTADOS_CERRADOS
        if cerrada:
            cerradas_count += 1
        else:
            abiertas_count += 1
            f = (g.factura or "").strip()
            if f and f != "N/A":
                facturas[f] = (
                    facturas.get(f, 0.0) + float(g.saldo_factura or 0)
                )
            c = (g.codigo_glosa or "").strip()
            if c:
                codigos[c] = codigos.get(c, 0) + 1

    top_facturas = sorted(
        facturas.items(), key=lambda x: x[1], reverse=True,
    )[:10]
    top_codigos = sorted(
        codigos.items(), key=lambda x: x[1], reverse=True,
    )[:10]

    return {
        "eps": eps,
        "resumen": {
            "total": len(rows),
            "abiertas": abiertas_count,
            "cerradas": cerradas_count,
            "valor_objetado_total": int(valor_total),
            "saldo_total": int(saldo_total),
        },
        "top_facturas": [
            {"factura": f, "saldo": int(s)}
            for f, s in top_facturas
        ],
        "top_codigos": [
            {"codigo_glosa": c, "count": n}
            for c, n in top_codigos
        ],
    }


@router.get("/glosas-creadas-hoy-detalle")
def admin_glosas_creadas_hoy_detalle(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R290 P1: detalle de las glosas creadas el día de hoy.

    Diferente a /glosas/stats/creadas-hoy (solo count):
    aquí lista completa con datos clave. Útil para morning
    briefing del coordinador o admin.

    Solo SUPER_ADMIN.
    """
    from app.core.tz import ahora_utc

    inicio = ahora_utc().replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= inicio)
        .order_by(GlosaRecord.valor_objetado.desc())
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "codigo_glosa": g.codigo_glosa,
            "estado": g.estado,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "gestor_nombre": g.gestor_nombre,
            "creado_en": (
                g.creado_en.isoformat() if g.creado_en else None
            ),
        })

    valor_total = sum(it["valor_objetado"] for it in items)

    return {
        "fecha": inicio.date().isoformat(),
        "total_creadas": len(items),
        "valor_objetado_total": valor_total,
        "items": items,
    }


@router.get("/consecutivos-duplicados")
def admin_consecutivos_duplicados(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R287 P1: detección de `consecutivo_dgh` duplicados.

    Cada glosa debe tener un consecutivo_dgh único (es la
    llave del DGH). Si aparecen duplicados, hay una
    importación errada o una colisión de datos.

    Devuelve solo los consecutivos que aparecen >= 2 veces,
    con los IDs de las glosas duplicadas.

    Solo SUPER_ADMIN. Crítico para integridad de datos.
    """
    from sqlalchemy import func as _f

    rows = (
        db.query(
            GlosaRecord.consecutivo_dgh,
            _f.count(GlosaRecord.id),
        )
        .filter(GlosaRecord.consecutivo_dgh.isnot(None))
        .filter(GlosaRecord.consecutivo_dgh != "")
        .group_by(GlosaRecord.consecutivo_dgh)
        .having(_f.count(GlosaRecord.id) > 1)
        .all()
    )

    items = []
    for cons, count in rows:
        glosas = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.consecutivo_dgh == cons)
            .all()
        )
        items.append({
            "consecutivo_dgh": cons,
            "count": int(count),
            "glosa_ids": [g.id for g in glosas],
            "estados": list({(g.estado or "?") for g in glosas}),
        })
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_duplicados": len(items),
        "items": items,
    }


@router.get("/sistema-resumen")
def admin_sistema_resumen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R281 P1: resumen ejecutivo del sistema (single-call).

    Compone en una sola respuesta totales globales del
    sistema, útil como landing page admin:
      - glosas: total, abiertas, cerradas
      - usuarios: total, activos
      - comentarios: total
      - conciliaciones: total
      - audit_events: total

    Solo SUPER_ADMIN.
    """
    from app.models.db import (
        ComentarioGlosaRecord,
        ConciliacionRecord,
    )

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    total_glosas = db.query(GlosaRecord).count()
    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .count()
    )
    cerradas = total_glosas - abiertas

    total_users = db.query(UsuarioRecord).count()
    activos = db.query(UsuarioRecord).filter(UsuarioRecord.activo == 1).count()

    total_comentarios = db.query(ComentarioGlosaRecord).count()
    total_concil = db.query(ConciliacionRecord).count()
    total_audit = db.query(AuditLogRecord).count()

    return {
        "glosas": {
            "total": total_glosas,
            "abiertas": abiertas,
            "cerradas": cerradas,
        },
        "usuarios": {
            "total": total_users,
            "activos": activos,
        },
        "comentarios": total_comentarios,
        "conciliaciones": total_concil,
        "audit_events": total_audit,
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
