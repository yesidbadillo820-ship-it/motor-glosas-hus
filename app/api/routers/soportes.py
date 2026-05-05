"""Endpoints para auto-descubrimiento de soportes en el share de radicación.

Flujo:
  GET  /soportes-auto/healthz                  → estado público para monitor
  GET  /soportes-auto/stats                    → estado detallado (auth)
  GET  /soportes-auto/factura/{numero}         → soportes detectados (auth + audit PHI)
  POST /soportes-auto/reindex                  → rebuild manual (auditor+)
  POST /soportes-auto/upload-bulk              → jump-box agent: subir lote de archivos (auditor+)
  GET  /soportes-auto/manifest                 → jump-box agent: estado del mirror local

Cada `GET /factura/{numero}` registra acceso PHI en audit_log con
acción `LISTAR_SOPORTES_FACTURA` — obligatorio para auditoría de
historias clínicas.

Los endpoints de jump-box solo aplican cuando el motor no tiene mount
CIFS directo y depende de un agente externo que lee el share desde
una PC Windows y empuja los archivos. Path traversal está bloqueado
por validación estricta antes de escribir a disco.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.database import get_db
from app.models.db import UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.services.soportes_autodiscovery_service import get_indexer

router = APIRouter(prefix="/soportes-auto", tags=["soportes-auto"])

# Si el último build fue hace más de este umbral, el healthz reporta degradado.
_UMBRAL_BUILD_OBSOLETO_SEG = 25 * 3600  # 25 horas (1 ciclo + margen)


@router.get("/healthz")
def healthz():
    """Health check público — no requiere auth, para monitor externo.

    Retorna:
      200 + {status: "ok", ...}        → indexador caliente y raíz accesible
      503 + {status: "degraded", ...}  → mount caído, build obsoleto o error
    """
    s = get_indexer().stats()
    razones = []
    if not s["raiz_existe"]:
        razones.append(f"raiz_no_accesible:{s['raiz']}")
    if s["ultimo_error"]:
        razones.append(f"error:{s['ultimo_error']}")
    if s["construido_en_epoch"] == 0:
        razones.append("indice_nunca_construido")
    elif s["construido_hace_seg"] is not None and s["construido_hace_seg"] > _UMBRAL_BUILD_OBSOLETO_SEG:
        razones.append(f"build_obsoleto:{s['construido_hace_seg']/3600:.1f}h")

    body = {
        "status": "ok" if not razones else "degraded",
        "facturas_indexadas": s["facturas_indexadas"],
        "archivos_indexados": s["archivos_indexados"],
        "construido_hace_seg": s["construido_hace_seg"],
        "raiz": s["raiz"],
        "razones_degradacion": razones,
    }
    if razones:
        # 503 hace que el balanceador / monitor lo detecte como caído
        raise HTTPException(status_code=503, detail=body)
    return body


@router.get("/stats")
def stats(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Estado detallado del indexador. Requiere auth."""
    return get_indexer().stats()


@router.get("/factura/{numero}")
def soportes_de_factura(
    numero: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve los soportes detectados en disco para una factura.

    Acepta el número en cualquier formato (`HUS487523`, `HUS0000495050`,
    `495050`) — internamente se normaliza por la parte numérica.

    Auditoría PHI: cada llamada registra `LISTAR_SOPORTES_FACTURA` con
    factura, cantidad de archivos y usuario. Es obligatorio porque
    saber qué historias clínicas existen para un paciente ya es PHI.
    """
    if not numero or len(numero) < 3:
        raise HTTPException(400, "Número de factura inválido")
    indexer = get_indexer()
    soportes = indexer.lookup(numero)

    # Auditoría PHI
    try:
        ip = request.client.host if request.client else None
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="LISTAR_SOPORTES_FACTURA",
            tabla="soportes_share",
            detalle=(
                f"factura={numero[:50]} encontrados={len(soportes)} "
                f"tipos={sorted({s['tipo_codigo'] for s in soportes})}"
            ),
            ip=ip,
        )
    except Exception:
        pass  # nunca tumbar la respuesta por fallo de audit

    return {
        "factura": numero,
        "soportes": soportes,
        "total": len(soportes),
        "tipos_detectados": sorted({s["tipo_codigo"] for s in soportes}),
    }


@router.get("/buscar")
def buscar_soportes(
    q: str,
    request: Request,
    limite: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Búsqueda flexible sobre el indice de soportes.

    Acepta:
      - Numero de factura: "HUS245200", "245200" (con o sin prefijo)
      - Numero ENV: "ENV-189840", "189840"
      - Nombre EPS: "ALIANZA MEDELLIN", "FAMISANAR"
      - Combinaciones: "FAMISANAR ENV-189840"
      - Substring de archivo: "factura.pdf"

    Devuelve grupos por factura, cada uno con sus archivos detectados,
    EPS, ENV, año/mes, y la ruta absoluta de la carpeta para que el
    gestor pueda copiarla y pegarla en el explorador.

    Auditoria PHI: cada llamada se loggea (saber que historias clinicas
    consulta cada usuario es PHI segun politica HUS).
    """
    if not q or len(q.strip()) < 2:
        raise HTTPException(400, "Query debe tener al menos 2 caracteres")
    if limite < 1 or limite > 100:
        limite = 30

    indexer = get_indexer()
    resultados = indexer.buscar(q.strip(), limite=limite)

    # Audit log
    try:
        ip = request.client.host if request.client else None
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="BUSCAR_SOPORTES",
            tabla="soportes_share",
            detalle=f"q={q[:100]} encontrados={len(resultados)}",
            ip=ip,
        )
    except Exception:
        pass

    return {
        "query": q,
        "total": len(resultados),
        "limite": limite,
        "resultados": resultados,
    }


@router.post("/reindex")
def reindex(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Fuerza una reconstrucción del índice. Auditor+ por costo de I/O."""
    inicio = time.time()
    stats_resultado = get_indexer().rebuild()
    duracion = round(time.time() - inicio, 2)
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="REINDEX_SOPORTES",
            tabla="soportes_share",
            detalle=(
                f"archivos={stats_resultado['archivos_indexados']} "
                f"facturas={stats_resultado['facturas_indexadas']} "
                f"duracion_s={duracion} "
                f"error={stats_resultado.get('ultimo_error') or 'ninguno'}"
            ),
            ip=request.client.host if request.client else None,
        )
    except Exception:
        pass
    return {"duracion_segundos": duracion, **stats_resultado}


# ─── Jump-box agent (Plan B sin mount CIFS) ──────────────────────────
#
# Cuando Infra no puede montar el share en el server, una PC Windows
# que ya ve `Y:\` corre tools/jumpbox_sync.py y empuja los archivos
# vía POST. Los archivos se guardan bajo SOPORTES_LOCAL_ROOT preservando
# la estructura de carpetas del share. El indexador apunta al mismo
# directorio (SOPORTES_ROOT == SOPORTES_LOCAL_ROOT en este modo) y no
# nota la diferencia.

_EXT_PERMITIDAS = {".pdf", ".json", ".xml", ".txt", ".csv"}
_MAX_BYTES_POR_ARCHIVO = 50 * 1024 * 1024   # 50 MB
_MAX_BYTES_POR_LOTE = 200 * 1024 * 1024     # 200 MB total por request
_MAX_ARCHIVOS_POR_LOTE = 50


def _local_root() -> Path:
    """Raíz donde el motor guarda los archivos empujados por el agente.

    Modo jump-box: el agente sube por HTTP, el motor escribe acá y el
    indexador lee de acá (SOPORTES_ROOT == SOPORTES_LOCAL_ROOT).

    Default `/tmp/motor-soportes`: existe siempre en Linux, es writable
    en Render Free, y es ephemeral (se borra en cada redeploy — pero
    el agente re-sincroniza en cada pasada cada 30 min, así que es
    aceptable).
    """
    raiz = os.getenv("SOPORTES_LOCAL_ROOT") or os.getenv(
        "SOPORTES_ROOT", "/tmp/motor-soportes"
    )
    p = Path(raiz)
    # Crear si no existe (idempotente). Sin esto el primer upload
    # falla con FileNotFoundError.
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _safe_join(base: Path, rel_path: str) -> Optional[Path]:
    """Une `rel_path` (recibido del cliente) bajo `base` con validación
    estricta. Devuelve `None` si el path es inseguro.

    Bloquea: rutas absolutas, drive letters Windows, segmentos `..`,
    bytes nulos, paths que después de `.resolve()` salen de `base`.
    """
    if not rel_path or len(rel_path) > 500 or "\x00" in rel_path:
        return None
    # Normalizar separadores Windows → POSIX
    rel = rel_path.replace("\\", "/").lstrip("/")
    # Drive letter al inicio (Y:/foo, C:/foo)
    if len(rel) >= 2 and rel[1] == ":":
        return None
    # Segmentos peligrosos
    partes = [p for p in rel.split("/") if p]
    if any(p in {"..", "."} or not p.strip() for p in partes):
        return None
    candidato = (base / "/".join(partes)).resolve()
    base_resuelto = base.resolve()
    try:
        candidato.relative_to(base_resuelto)
    except ValueError:
        return None
    return candidato


@router.get("/facturas-objetivo")
def facturas_objetivo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Devuelve la lista de facturas con glosas PENDIENTES de respuesta.

    Pensado para que el jump-box agent corra en modo `--solo-pendientes`
    y solo sincronice los PDFs de las facturas que el gestor realmente
    necesita responder ahora — en vez de los 144k archivos del share
    completo.

    Criterio "pendiente":
      • estado NO IN (LEVANTADA, CONCILIADA, ACEPTADA, RATIFICADA,
        ARCHIVADA, DUPLICADA_OCULTA)
      • workflow_state NO IN (RESPONDIDA, CONCILIADA, LEVANTADA)

    Devuelve facturas únicas + el conteo. La normalización (quitar
    ceros a la izquierda, quitar prefijo HUS) la hace el agente al
    matchear vs nombres de archivo del share.
    """
    from app.models.db import GlosaRecord
    estados_terminales = (
        "LEVANTADA", "CONCILIADA", "ACEPTADA", "RATIFICADA",
        "ARCHIVADA", "DUPLICADA_OCULTA",
    )
    workflow_terminales = ("RESPONDIDA", "CONCILIADA", "LEVANTADA")
    rows = (
        db.query(GlosaRecord.factura)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "")
        .filter(~GlosaRecord.estado.in_(estados_terminales))
        .filter(
            (GlosaRecord.workflow_state.is_(None))
            | (~GlosaRecord.workflow_state.in_(workflow_terminales))
        )
        .distinct()
        .limit(5000)
        .all()
    )
    facturas = sorted({r[0].strip().upper() for r in rows if r[0]})
    return {
        "total": len(facturas),
        "facturas": facturas,
    }


@router.get("/manifest")
def manifest(
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Resumen del mirror local — lo usa el agente para saber qué
    archivos ya subió y evitar transferencias redundantes.

    Devuelve `{rel_path: {tamaño, mtime}}` para todos los archivos
    bajo SOPORTES_LOCAL_ROOT. El agente compara con su lado y solo
    sube los que cambiaron.
    """
    raiz = _local_root()
    if not raiz.exists():
        return {"raiz": str(raiz), "raiz_existe": False, "archivos": {}}
    archivos = {}
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(raiz)).replace(os.sep, "/")
            st = p.stat()
            archivos[rel] = {"size": st.st_size, "mtime": int(st.st_mtime)}
        except OSError:
            continue
    return {
        "raiz": str(raiz),
        "raiz_existe": True,
        "total_archivos": len(archivos),
        "archivos": archivos,
    }


@router.post("/upload-bulk")
async def upload_bulk(
    request: Request,
    files: list[UploadFile] = File(...),
    rel_paths: list[str] = Form(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Recibe un lote de archivos del agente jump-box y los guarda en
    `SOPORTES_LOCAL_ROOT` preservando la estructura indicada en
    `rel_paths`.

    Args:
        files: lista de archivos (multipart). Máx 50 archivos / 200 MB.
        rel_paths: ruta relativa para cada archivo, en el mismo orden.
                   Ej. ["ABRIL 2026 - SOPORTES RADICACION/.../FEV_X.pdf", ...]

    Validaciones:
        - Path traversal bloqueado (`_safe_join`).
        - Solo extensiones de soporte (.pdf .json .xml .txt .csv).
        - Tamaño por archivo y por lote.

    Tras escribir, NO dispara reindex automático para no recalcular en
    cada batch del agente. El agente debe llamar a `/reindex` cuando
    termine su pasada.
    """
    if len(files) != len(rel_paths):
        raise HTTPException(400, "Cantidad de files y rel_paths no coincide")
    if len(files) > _MAX_ARCHIVOS_POR_LOTE:
        raise HTTPException(400, f"Máx {_MAX_ARCHIVOS_POR_LOTE} archivos por lote")

    raiz = _local_root()
    raiz.mkdir(parents=True, exist_ok=True)

    resumen = {
        "guardados": 0,
        "ignorados_iguales": 0,
        "rechazados": [],
        "bytes_escritos": 0,
    }
    total_bytes = 0

    for upload, rel in zip(files, rel_paths):
        nombre = upload.filename or rel.split("/")[-1]
        # Validación de path
        destino = _safe_join(raiz, rel)
        if destino is None:
            resumen["rechazados"].append({"rel": rel[:200], "motivo": "path_invalido"})
            continue
        # Validación de extensión
        if destino.suffix.lower() not in _EXT_PERMITIDAS:
            resumen["rechazados"].append({"rel": rel[:200], "motivo": "extension_no_permitida"})
            continue
        # Leer en memoria con tope de tamaño
        contenido = await upload.read(_MAX_BYTES_POR_ARCHIVO + 1)
        if len(contenido) > _MAX_BYTES_POR_ARCHIVO:
            resumen["rechazados"].append({"rel": rel[:200], "motivo": "demasiado_grande"})
            continue
        total_bytes += len(contenido)
        if total_bytes > _MAX_BYTES_POR_LOTE:
            resumen["rechazados"].append({"rel": rel[:200], "motivo": "lote_excede_total"})
            continue
        # Skip si ya existe con mismo tamaño (rápido — no compara hash)
        if destino.exists() and destino.stat().st_size == len(contenido):
            resumen["ignorados_iguales"] += 1
            continue
        # Escribir atómico (tmp → rename)
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            tmp = destino.with_suffix(destino.suffix + ".tmp")
            tmp.write_bytes(contenido)
            tmp.replace(destino)
            resumen["guardados"] += 1
            resumen["bytes_escritos"] += len(contenido)
        except OSError as e:
            resumen["rechazados"].append({"rel": rel[:200], "motivo": f"io:{e}"})
        finally:
            # Liberar bytes en memoria explícitamente — Python no siempre
            # libera buffers grandes ad-hoc, y en Render Free 512 MB cada
            # batch de 50 PDFs acumula 50-200 MB que no se devuelven al
            # heap hasta el próximo GC. Forzamos del + recolectado.
            try:
                del contenido
            except NameError:
                pass

    # Audit
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="UPLOAD_BULK_SOPORTES",
            tabla="soportes_share",
            detalle=(
                f"guardados={resumen['guardados']} "
                f"ignorados={resumen['ignorados_iguales']} "
                f"rechazados={len(resumen['rechazados'])} "
                f"bytes={resumen['bytes_escritos']}"
            ),
            ip=request.client.host if request.client else None,
        )
    except Exception as _e:
        import logging as _l
        _l.getLogger("motor_glosas").debug(f"audit upload-bulk falló: {_e}")

    # Forzar GC después de procesar el batch — Render Free 512 MB
    # acumula bytes de PDFs sin liberar entre requests si no.
    try:
        import gc as _gc
        _gc.collect()
    except Exception:
        pass

    return resumen
