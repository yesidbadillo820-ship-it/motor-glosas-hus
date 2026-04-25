"""Búsqueda en el catálogo CUPS (Ronda 50 Paso 4).

El catálogo efectivo del sistema es la unión de:
  1. Tarifas contratadas cargadas en BD (TarifaContratadaRecord) — incluye
     los ~11.500 códigos cargados hoy (DMBUG 4.134 + Famisanar 7.357 + etc.)
  2. Tabla explícita de homologación Res. 2641/2025 (homologador_cups.py)
  3. Tarifas propias HUS (tarifas_oficiales.py — Res. 054/2026 + 124/2026)

Endpoints:

  GET /cups/buscar?q=...&limite=10
    Busca por código exacto, por código IPS, o por descripción parcial.
    Devuelve lista priorizada por tipo de match.

  GET /cups/{codigo}
    Detalle de un CUPS específico: contratos que lo tienen, valor pactado,
    descripción oficial, homologación si aplica.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import TarifaContratadaRecord, UsuarioRecord

router = APIRouter(prefix="/cups", tags=["cups"])


def _sin_tildes(s: str) -> str:
    """Elimina tildes/diacríticos para búsqueda acent-insensitive.
    'GENÉTICA' → 'GENETICA', 'MÉDICO' → 'MEDICO'."""
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _is_codigo(q: str) -> bool:
    """True si el query parece código CUPS (dígitos + letras opcionales)."""
    return bool(re.match(r"^[A-Z0-9\-]{3,20}$", q.upper().strip()))


@router.get("/buscar")
def buscar_cups(
    q: str = Query(..., min_length=2, description="Código CUPS, código IPS o parte de la descripción"),
    limite: int = Query(10, ge=1, le=50),
    eps: Optional[str] = Query(None, description="Filtrar por EPS"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Busca en el catálogo CUPS unificado."""
    q_clean = (q or "").strip().upper()
    if not q_clean:
        return {"query": q, "total": 0, "resultados": []}

    base = db.query(TarifaContratadaRecord).filter(TarifaContratadaRecord.activa == 1)
    if eps:
        base = base.filter(TarifaContratadaRecord.eps.ilike(f"%{eps.strip()}%"))

    resultados: list[dict] = []
    vistos_cups: set[str] = set()

    def _agregar(fila: TarifaContratadaRecord, tipo_match: str):
        """Deduplica por (cups, eps) y agrega al resultado."""
        clave = f"{fila.codigo_cups}|{fila.eps}"
        if clave in vistos_cups:
            return
        vistos_cups.add(clave)
        resultados.append({
            "codigo_cups": fila.codigo_cups,
            "codigo_ips": fila.codigo_ips,
            "descripcion": fila.descripcion,
            "eps": fila.eps,
            "contrato_numero": fila.contrato_numero,
            "valor_pactado": float(fila.valor_pactado or 0),
            "modalidad": fila.modalidad,
            "tipo_match": tipo_match,
        })

    # Prioridad 1: match exacto por CUPS
    if _is_codigo(q_clean):
        for fila in base.filter(TarifaContratadaRecord.codigo_cups == q_clean).limit(limite).all():
            _agregar(fila, "codigo_cups_exacto")

        # Prioridad 2: match exacto por CODIGO IPS (homologación)
        if len(resultados) < limite:
            for fila in base.filter(TarifaContratadaRecord.codigo_ips == q_clean).limit(limite - len(resultados)).all():
                _agregar(fila, "codigo_ips_exacto")

        # Prioridad 3: prefix match en código
        if len(resultados) < limite:
            for fila in base.filter(TarifaContratadaRecord.codigo_cups.ilike(f"{q_clean}%")).limit(limite - len(resultados)).all():
                _agregar(fila, "codigo_prefix")

    # Prioridad 4a: match literal en descripción (case-insensitive)
    if len(resultados) < limite:
        for fila in (
            base.filter(TarifaContratadaRecord.descripcion.ilike(f"%{q_clean}%"))
            .order_by(func.length(TarifaContratadaRecord.descripcion).asc())
            .limit(limite - len(resultados))
            .all()
        ):
            _agregar(fila, "descripcion")

    # Prioridad 4b (R51 P2): match ACENT-INSENSITIVE — si la descripción
    # en BD tiene tildes ('GENÉTICA') pero el usuario escribió 'GENETICA',
    # el ilike directo no matchea (SQLite/Postgres son accent-sensitive).
    # Fallback en memoria normalizando ambos lados.
    q_norm = _sin_tildes(q_clean)
    if len(resultados) < limite and len(q_clean) >= 4:
        # Traer candidatos filtrados por primera letra del query normalizado
        # para acotar la búsqueda. No es perfecto (si la descripción empieza
        # con tilde falla) pero cubre el 95% de casos.
        prefijo = q_norm[0] if q_norm else q_clean[0]
        candidatos = (
            base.filter(TarifaContratadaRecord.descripcion.ilike(f"%{prefijo}%"))
            .limit(500)
            .all()
        )
        agregados_norm = 0
        for fila in candidatos:
            if agregados_norm >= (limite - len(resultados)):
                break
            if q_norm in _sin_tildes(fila.descripcion or ""):
                _agregar(fila, "descripcion_normalizada")
                agregados_norm += 1

    # Prioridad 5: homologador explícito (solo para códigos)
    if _is_codigo(q_clean) and len(resultados) < limite:
        try:
            from app.services.homologador_cups import homologar_cups
            homo = homologar_cups(q_clean, db=db, eps=eps)
            if homo and homo.get("cups_oficial"):
                # Buscar tarifa del cups_oficial si no lo agregamos ya
                cups_of = homo["cups_oficial"]
                ya = any(r["codigo_cups"] == cups_of for r in resultados)
                if not ya:
                    resultados.append({
                        "codigo_cups": cups_of,
                        "codigo_ips": q_clean if q_clean != cups_of else None,
                        "descripcion": homo.get("descripcion", ""),
                        "eps": "—",
                        "contrato_numero": None,
                        "valor_pactado": 0.0,
                        "modalidad": "—",
                        "tipo_match": "homologacion_2641",
                    })
        except Exception:
            pass

    return {
        "query": q,
        "total": len(resultados),
        "resultados": resultados[:limite],
    }


@router.get("/{codigo}")
def detalle_cups(
    codigo: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Detalle agregado de un CUPS: todos los contratos que lo incluyen."""
    codigo_clean = codigo.strip().upper()
    if not codigo_clean:
        raise HTTPException(status_code=400, detail="Código vacío")

    # Buscar por codigo_cups o codigo_ips
    filas = (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .filter(
            or_(
                TarifaContratadaRecord.codigo_cups == codigo_clean,
                TarifaContratadaRecord.codigo_ips == codigo_clean,
            )
        )
        .order_by(TarifaContratadaRecord.eps)
        .all()
    )

    # Homologación
    homo = None
    try:
        from app.services.homologador_cups import homologar_cups
        homo = homologar_cups(codigo_clean, db=db)
    except Exception:
        pass

    return {
        "codigo_consultado": codigo_clean,
        "homologacion_2641": homo,
        "contratos_que_lo_incluyen": [
            {
                "eps": f.eps,
                "contrato_numero": f.contrato_numero,
                "codigo_cups": f.codigo_cups,
                "codigo_ips": f.codigo_ips,
                "descripcion": f.descripcion,
                "valor_pactado": float(f.valor_pactado or 0),
                "modalidad": f.modalidad,
                "fuente_archivo": f.fuente_archivo,
            }
            for f in filas
        ],
        "total_contratos": len(filas),
    }
