"""Detección de dictámenes obsoletos (stale) tras carga de tarifas/contratos.

Si una tarifa relevante para la EPS de la glosa se cargó después de que se
generó el dictamen, el argumento jurídico puede haber quedado desactualizado
(p.ej. el dictamen original argumentaba "no existe contrato" pero después se
cargó el tarifario y ese argumento es ahora falso). En ese caso la UI marca
el dictamen como obsoleto y sugiere re-analizar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import GlosaRecord, TarifaContratadaRecord


def es_stale(glosa: GlosaRecord, db: Session) -> bool:
    """True si hay tarifas activas para la EPS cargadas después del dictamen.

    Conservador: si `dictamen_generado_en` está vacío (campo nuevo, dictámenes
    antiguos) NO se marca como stale para no inundar la UI; el usuario puede
    re-analizar manualmente.
    """
    return motivo_stale(glosa, db) is not None


def motivo_stale(glosa: GlosaRecord, db: Session) -> Optional[str]:
    """Retorna un mensaje legible si el dictamen está stale, o None si vigente."""
    if not glosa or not glosa.dictamen:
        return None
    generado: Optional[datetime] = getattr(glosa, "dictamen_generado_en", None)
    if not generado:
        return None
    eps = (glosa.eps or "").strip()
    if not eps:
        return None
    # Buscamos tarifas activas para esta EPS cargadas después del dictamen.
    # Matching de EPS: case-insensitive y permite que la EPS del catálogo
    # contenga la EPS de la glosa o viceversa (planes vs nombre comercial).
    from app.services import pagador_normalizer
    eps_corto = pagador_normalizer.nombre_corto(eps)
    q = (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .filter(TarifaContratadaRecord.creado_en > generado)
    )
    candidatos = q.limit(50).all()
    if not candidatos:
        return None
    for t in candidatos:
        t_eps = (t.eps or "").strip()
        if not t_eps:
            continue
        if pagador_normalizer.son_equivalentes(t_eps, eps) or (
            eps_corto and eps_corto in t_eps.upper()
        ):
            fecha_str = t.creado_en.strftime("%d/%m/%Y") if t.creado_en else "?"
            return (
                f"Hay tarifas nuevas cargadas el {fecha_str} para esta EPS. "
                f"El dictamen puede estar desactualizado — re-analizar es recomendable."
            )
    return None
