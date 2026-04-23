"""Detector de anomalías / anti-fraude (Ronda 16).

Tres detectores complementarios que corren sobre GlosaRecord:

  1. detectar_duplicados(db, ventana_dias)
     Glosas con mismo (factura, cups_servicio, eps) pagado dos veces.
     Indica error de digitación o intento de doble radicación.

  2. detectar_patron_sospechoso_eps(db, ventana_dias)
     EPS cuya tasa de ratificación o volumen mensual saltó > 30 %
     respecto del promedio anterior. Apunta a glosas masivas con
     motivos dudosos.

  3. detectar_valor_anomalo(db, glosa)
     Z-score del valor objetado contra el histórico del mismo CUPS.
     Útil en tiempo real al radicar: alerta inmediata si el valor
     es > 3σ del promedio.

Todo es puro SQL + numpy-free; no dependemos de librerías pesadas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import GlosaRecord


@dataclass
class Anomalia:
    tipo: str            # "duplicado" | "patron_eps" | "valor_anomalo"
    severidad: str       # "ALTA" | "MEDIA" | "BAJA"
    descripcion: str
    entidad: dict        # datos relacionados (glosa_ids, eps, etc.)


# ─── 1) Duplicados ─────────────────────────────────────────────────────────

def detectar_duplicados(db: Session, ventana_dias: int = 90) -> list[Anomalia]:
    """Detecta glosas con misma (factura, cups_servicio, eps) dentro de
    la ventana. Ignora factura 'N/A' y cups vacío para evitar falsos
    positivos masivos."""
    desde = datetime.now(timezone.utc) - timedelta(days=max(1, int(ventana_dias)))
    q = (
        db.query(
            GlosaRecord.factura,
            GlosaRecord.cups_servicio,
            GlosaRecord.eps,
            func.count(GlosaRecord.id).label("n"),
            func.min(GlosaRecord.id).label("id_min"),
            func.max(GlosaRecord.id).label("id_max"),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .filter(GlosaRecord.cups_servicio.isnot(None))
        .filter(GlosaRecord.cups_servicio != "")
        .group_by(GlosaRecord.factura, GlosaRecord.cups_servicio, GlosaRecord.eps)
        .having(func.count(GlosaRecord.id) > 1)
    )
    result: list[Anomalia] = []
    for row in q.all():
        sev = "ALTA" if row.n >= 3 else "MEDIA"
        result.append(
            Anomalia(
                tipo="duplicado",
                severidad=sev,
                descripcion=(
                    f"Factura {row.factura} con CUPS {row.cups_servicio} "
                    f"radicada {row.n} veces por {row.eps}"
                ),
                entidad={
                    "factura": row.factura,
                    "cups": row.cups_servicio,
                    "eps": row.eps,
                    "n": int(row.n),
                    "glosa_id_min": int(row.id_min),
                    "glosa_id_max": int(row.id_max),
                },
            )
        )
    return result


# ─── 2) Patrón sospechoso por EPS ──────────────────────────────────────────

def detectar_patron_sospechoso_eps(
    db: Session, ventana_dias: int = 30, umbral_salto: float = 0.30
) -> list[Anomalia]:
    """Compara volumen y tasa de ratificación del último periodo vs el
    anterior. Si el volumen subió > umbral o la tasa de ratif > umbral,
    lo marca como sospechoso."""
    ahora = datetime.now(timezone.utc)
    periodo_reciente = ahora - timedelta(days=ventana_dias)
    periodo_previo = ahora - timedelta(days=ventana_dias * 2)

    def _stats(desde: datetime, hasta: datetime) -> dict[str, dict]:
        q = (
            db.query(
                GlosaRecord.eps,
                func.count(GlosaRecord.id).label("total"),
                func.sum(
                    func.coalesce(GlosaRecord.valor_objetado, 0.0)
                ).label("valor"),
            )
            .filter(GlosaRecord.creado_en >= desde, GlosaRecord.creado_en < hasta)
            .group_by(GlosaRecord.eps)
        )
        out: dict[str, dict] = {}
        for r in q.all():
            if not r.eps:
                continue
            out[r.eps] = {"total": int(r.total or 0), "valor": float(r.valor or 0.0)}

        # Tasa de ratificación (estado RATIFICADA / total) por EPS
        qr = (
            db.query(
                GlosaRecord.eps,
                func.count(GlosaRecord.id).label("ratif"),
            )
            .filter(GlosaRecord.creado_en >= desde, GlosaRecord.creado_en < hasta)
            .filter(GlosaRecord.decision_eps == "RATIFICADA")
            .group_by(GlosaRecord.eps)
        )
        for r in qr.all():
            if r.eps in out:
                out[r.eps]["ratif"] = int(r.ratif or 0)
        for eps_data in out.values():
            eps_data.setdefault("ratif", 0)
            t = eps_data["total"] or 1
            eps_data["tasa_ratif"] = eps_data["ratif"] / t
        return out

    stats_rec = _stats(periodo_reciente, ahora)
    stats_prev = _stats(periodo_previo, periodo_reciente)

    result: list[Anomalia] = []
    for eps, rec in stats_rec.items():
        prev = stats_prev.get(eps)
        if not prev or prev["total"] < 5:
            # Muy poca data previa → no podemos inferir patrón
            continue
        salto_vol = (rec["total"] - prev["total"]) / max(1, prev["total"])
        salto_tasa = rec["tasa_ratif"] - prev["tasa_ratif"]
        if salto_vol >= umbral_salto or salto_tasa >= umbral_salto:
            sev = "ALTA" if (salto_vol >= 0.6 or salto_tasa >= 0.5) else "MEDIA"
            result.append(
                Anomalia(
                    tipo="patron_eps",
                    severidad=sev,
                    descripcion=(
                        f"EPS {eps}: volumen {prev['total']}→{rec['total']} "
                        f"({salto_vol:+.0%}), tasa ratif {prev['tasa_ratif']:.0%}→"
                        f"{rec['tasa_ratif']:.0%}"
                    ),
                    entidad={
                        "eps": eps,
                        "salto_volumen": round(salto_vol, 3),
                        "salto_tasa": round(salto_tasa, 3),
                        "total_previo": prev["total"],
                        "total_reciente": rec["total"],
                        "tasa_previa": round(prev["tasa_ratif"], 3),
                        "tasa_reciente": round(rec["tasa_ratif"], 3),
                    },
                )
            )
    return result


# ─── 3) Valor anómalo (z-score por CUPS) ───────────────────────────────────

def detectar_valor_anomalo(
    db: Session, glosa: GlosaRecord, umbral_sigma: float = 3.0
) -> Optional[Anomalia]:
    """Compara el valor_objetado de esta glosa con el histórico del mismo
    cups_servicio. Retorna Anomalia si z-score > umbral_sigma."""
    if not glosa.cups_servicio or not glosa.valor_objetado:
        return None

    rows = (
        db.query(GlosaRecord.valor_objetado)
        .filter(GlosaRecord.cups_servicio == glosa.cups_servicio)
        .filter(GlosaRecord.id != glosa.id)
        .filter(GlosaRecord.valor_objetado.isnot(None))
        .filter(GlosaRecord.valor_objetado > 0)
        .limit(500)
        .all()
    )
    valores = [float(r[0]) for r in rows if r[0]]
    if len(valores) < 10:
        # Muestra insuficiente — skip
        return None

    n = len(valores)
    media = sum(valores) / n
    varianza = sum((v - media) ** 2 for v in valores) / n
    sigma = math.sqrt(varianza) if varianza > 0 else 0.0
    if sigma <= 0:
        return None

    z = (float(glosa.valor_objetado) - media) / sigma
    if abs(z) < umbral_sigma:
        return None
    sev = "ALTA" if abs(z) >= 5 else "MEDIA"
    return Anomalia(
        tipo="valor_anomalo",
        severidad=sev,
        descripcion=(
            f"Glosa #{glosa.id} valor ${int(glosa.valor_objetado):,} "
            f"(z={z:+.2f}σ vs promedio CUPS {glosa.cups_servicio} "
            f"${int(media):,})"
        ),
        entidad={
            "glosa_id": glosa.id,
            "cups": glosa.cups_servicio,
            "valor": float(glosa.valor_objetado),
            "media_historica": round(media, 2),
            "sigma": round(sigma, 2),
            "z_score": round(z, 3),
            "muestra": n,
        },
    )


# ─── Dashboard agregado ────────────────────────────────────────────────────

def resumen_anomalias(db: Session, ventana_dias: int = 30) -> dict:
    """Combina los detectores y arma un dashboard unificado."""
    dup = detectar_duplicados(db, ventana_dias=ventana_dias)
    patr = detectar_patron_sospechoso_eps(db, ventana_dias=ventana_dias)
    return {
        "ventana_dias": ventana_dias,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "totales": {
            "duplicados": len(dup),
            "patrones_eps": len(patr),
            "alta": sum(1 for a in dup + patr if a.severidad == "ALTA"),
            "media": sum(1 for a in dup + patr if a.severidad == "MEDIA"),
        },
        "duplicados": [a.__dict__ for a in dup[:50]],
        "patrones_eps": [a.__dict__ for a in patr[:50]],
    }
