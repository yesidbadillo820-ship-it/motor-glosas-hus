"""Mapeo factura HUS -> ruta de carpeta de soportes en el share local.

El gestor sube un CSV/XLSX con dos columnas (factura, ruta) y la UI
del Auditor Forense consulta esta tabla cuando va a auditar una
factura. El browser del gestor (que SI tiene visibilidad del share
Y:\\FEBRERO 2026 ...) descarga los PDFs del servidor HTTP local y los
sube al motor para que Claude los analice.

Endpoints:
    GET    /rutas-facturas/{factura}            - lookup por factura
    POST   /rutas-facturas/import-csv           - upload CSV/TSV/Excel
    POST   /rutas-facturas/manual               - alta manual de 1 ruta
    DELETE /rutas-facturas/{factura}            - borrar
    GET    /rutas-facturas/stats                - cuantas rutas hay
"""
from __future__ import annotations
import csv
import io
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import RutaFacturaRecord, UsuarioRecord
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/rutas-facturas", tags=["rutas-facturas"])


_FACTURA_RE = re.compile(r"HUS\s*0*(\d+)", re.IGNORECASE)


def _normalizar_factura(raw: str) -> str:
    """Acepta 'HUS466775', 'HUS0000466775', '466775' y devuelve
    'HUS466775' (sin ceros a la izquierda, prefijo HUS forzado).
    """
    if not raw:
        return ""
    s = str(raw).strip()
    m = _FACTURA_RE.search(s)
    if m:
        return f"HUS{m.group(1)}"
    if s.isdigit():
        return f"HUS{int(s)}"
    return s.upper().replace(" ", "")


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    total = db.query(RutaFacturaRecord).count()
    sample = (
        db.query(RutaFacturaRecord)
        .order_by(RutaFacturaRecord.actualizado_en.desc())
        .limit(3)
        .all()
    )
    return {
        "total_rutas": total,
        "ultimas": [
            {
                "factura": r.factura_hus,
                "ruta": r.ruta_carpeta,
                "actualizado_en": r.actualizado_en.isoformat() if r.actualizado_en else None,
            }
            for r in sample
        ],
    }


@router.get("/{factura}")
def lookup_ruta(
    factura: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve la ruta de carpeta para la factura. 404 si no existe."""
    fac_norm = _normalizar_factura(factura)
    r = db.query(RutaFacturaRecord).filter(
        RutaFacturaRecord.factura_hus == fac_norm
    ).first()
    if not r:
        raise HTTPException(404, f"Sin ruta registrada para {fac_norm}")
    meta = {}
    if r.meta:
        try:
            meta = json.loads(r.meta)
        except Exception:
            meta = {}
    return {
        "factura": r.factura_hus,
        "ruta_carpeta": r.ruta_carpeta,
        "meta": meta,
        "actualizado_en": r.actualizado_en.isoformat() if r.actualizado_en else None,
        "importado_por": r.importado_por,
    }


class RutaManualInput(BaseModel):
    factura: str = Field(..., min_length=3)
    ruta_carpeta: str = Field(..., min_length=3, max_length=800)
    meta: dict | None = None


@router.post("/manual")
def alta_manual(
    data: RutaManualInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Alta manual de 1 ruta. Si ya existe, actualiza."""
    fac_norm = _normalizar_factura(data.factura)
    if not fac_norm:
        raise HTTPException(400, "Factura invalida")
    ruta = (data.ruta_carpeta or "").strip()
    if not ruta:
        raise HTTPException(400, "ruta_carpeta vacia")

    r = db.query(RutaFacturaRecord).filter(
        RutaFacturaRecord.factura_hus == fac_norm
    ).first()
    if r:
        r.ruta_carpeta = ruta[:800]
        r.actualizado_en = ahora_utc()
        r.importado_por = current_user.email
        if data.meta:
            r.meta = json.dumps(data.meta, ensure_ascii=False)
    else:
        r = RutaFacturaRecord(
            factura_hus=fac_norm,
            ruta_carpeta=ruta[:800],
            importado_por=current_user.email,
            meta=json.dumps(data.meta, ensure_ascii=False) if data.meta else None,
        )
        db.add(r)
    db.commit()
    return {"ok": True, "factura": fac_norm, "ruta_carpeta": r.ruta_carpeta}


@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    columna_factura: str = Form("factura"),
    columna_ruta: str = Form("ruta"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Importa rutas masivamente desde CSV/TSV.

    Args:
        file: archivo CSV/TSV (max 10MB).
        columna_factura: nombre del header de la columna que contiene
            la factura HUS (default 'factura'). Tambien acepta
            'factura_hus', 'numero_factura', etc por fuzzy match.
        columna_ruta: nombre del header de la ruta (default 'ruta').
            Tambien acepta 'ruta_carpeta', 'path', 'directorio'.

    Detecta auto-magicamente si es TAB o COMA. Idempotente: si la
    factura ya existe, actualiza la ruta.

    Solo AUDITOR/COORDINADOR/SUPER_ADMIN.
    """
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "Archivo excede 10MB")
    try:
        texto = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            texto = raw.decode("latin-1")
        except Exception:
            raise HTTPException(400, "No se pudo decodificar el archivo (usa UTF-8 o latin-1)")

    # Detectar separador: TAB > pipe > coma > punto y coma
    primera_linea = texto.split("\n", 1)[0] if texto else ""
    if "\t" in primera_linea:
        sep = "\t"
    elif "|" in primera_linea:
        sep = "|"
    elif ";" in primera_linea and primera_linea.count(";") > primera_linea.count(","):
        sep = ";"
    else:
        sep = ","

    reader = csv.DictReader(io.StringIO(texto), delimiter=sep)
    if not reader.fieldnames:
        raise HTTPException(400, "Archivo sin encabezados")

    # Fuzzy match de columnas
    headers_low = [h.strip().lower() for h in reader.fieldnames]
    col_factura_low = (columna_factura or "factura").strip().lower()
    col_ruta_low = (columna_ruta or "ruta").strip().lower()

    def _find_header(target: str, alts: list[str]) -> Optional[str]:
        for cand in [target] + alts:
            for i, h in enumerate(headers_low):
                if h == cand:
                    return reader.fieldnames[i]
        for cand in [target] + alts:
            for i, h in enumerate(headers_low):
                if cand in h:
                    return reader.fieldnames[i]
        return None

    h_fac = _find_header(col_factura_low, ["factura", "factura_hus", "numero_factura", "factura hus", "fac"])
    h_ruta = _find_header(col_ruta_low, ["ruta", "ruta_carpeta", "path", "directorio", "carpeta"])
    if not h_fac:
        raise HTTPException(400, f"No se encontro columna de factura. Headers: {reader.fieldnames}")
    if not h_ruta:
        raise HTTPException(400, f"No se encontro columna de ruta. Headers: {reader.fieldnames}")

    insertadas = 0
    actualizadas = 0
    invalidas = 0
    errores: list[str] = []

    for i, row in enumerate(reader, start=2):
        try:
            factura_raw = (row.get(h_fac) or "").strip()
            ruta_raw = (row.get(h_ruta) or "").strip()
            if not factura_raw or not ruta_raw:
                invalidas += 1
                continue
            fac_norm = _normalizar_factura(factura_raw)
            if not fac_norm or len(fac_norm) < 4:
                invalidas += 1
                if len(errores) < 20:
                    errores.append(f"fila {i}: factura invalida '{factura_raw}'")
                continue
            # Capturar metadata extra (todas las columnas que no son factura/ruta)
            meta_extra = {}
            for k, v in row.items():
                if k in (h_fac, h_ruta):
                    continue
                if v and str(v).strip():
                    meta_extra[k.strip()] = str(v).strip()[:200]

            r = db.query(RutaFacturaRecord).filter(
                RutaFacturaRecord.factura_hus == fac_norm
            ).first()
            if r:
                r.ruta_carpeta = ruta_raw[:800]
                r.actualizado_en = ahora_utc()
                r.importado_por = current_user.email
                if meta_extra:
                    r.meta = json.dumps(meta_extra, ensure_ascii=False)
                actualizadas += 1
            else:
                db.add(RutaFacturaRecord(
                    factura_hus=fac_norm,
                    ruta_carpeta=ruta_raw[:800],
                    importado_por=current_user.email,
                    meta=json.dumps(meta_extra, ensure_ascii=False) if meta_extra else None,
                ))
                insertadas += 1
        except Exception as e:
            invalidas += 1
            if len(errores) < 20:
                errores.append(f"fila {i}: {e}")
    db.commit()

    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="IMPORT_RUTAS",
            tabla="rutas_factura",
            detalle=f"insertadas={insertadas} actualizadas={actualizadas} invalidas={invalidas}",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "insertadas": insertadas,
        "actualizadas": actualizadas,
        "invalidas": invalidas,
        "total_procesadas": insertadas + actualizadas + invalidas,
        "separador_detectado": sep if sep != "\t" else "TAB",
        "columna_factura_usada": h_fac,
        "columna_ruta_usada": h_ruta,
        "errores": errores,
    }


@router.delete("/{factura}")
def borrar_ruta(
    factura: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    fac_norm = _normalizar_factura(factura)
    r = db.query(RutaFacturaRecord).filter(
        RutaFacturaRecord.factura_hus == fac_norm
    ).first()
    if not r:
        raise HTTPException(404, "Sin ruta para borrar")
    db.delete(r)
    db.commit()
    return {"ok": True, "factura": fac_norm}
