"""Notificaciones consolidadas del usuario logueado (Ronda 25).

Un endpoint único que el frontend puede pollear cada 30-60s para pintar
el badge rojo del header. Devuelve el número total de notificaciones
accionables + lista top 10.

Categorías:
  - glosas_criticas_mias    Mis glosas que vencen en <48h hábiles
  - glosas_vencidas_mias    Mis glosas con dias_restantes < 0
  - listas_para_enviar_mias Mis glosas LISTA_ENVIAR (texto fijo o autopilot
                              con confianza ≥ 0.85)
  - menciones_pendientes    Comentarios donde me mencionaron y no resolví
  - gold_nuevas             Plantillas Gold activas creadas en últimos 7d
                              de MIS EPS habituales (top 5)

Diseñada para ser barata: cada sub-query está indexada.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import (
    ComentarioGlosaRecord,
    GlosaRecord,
    PlantillaGoldRecord,
    UsuarioRecord,
)


def _glosas_criticas(db: Session, email: str, horas: int = 48) -> int:
    """Mis glosas con dias_restantes <= ceil(horas/24) y > 0."""
    ahora = datetime.now(timezone.utc)
    # Aproximación: dias_restantes ≤ 2 y > 0
    return (
        db.query(func.count(GlosaRecord.id))
        .filter(GlosaRecord.auditor_email == email)
        .filter(GlosaRecord.estado == "PENDIENTE")
        .filter(GlosaRecord.dias_restantes > 0)
        .filter(GlosaRecord.dias_restantes <= 2)
        .scalar() or 0
    )


def _glosas_vencidas(db: Session, email: str) -> int:
    return (
        db.query(func.count(GlosaRecord.id))
        .filter(GlosaRecord.auditor_email == email)
        .filter(GlosaRecord.estado == "PENDIENTE")
        .filter(GlosaRecord.dias_restantes < 0)
        .scalar() or 0
    )


def _glosas_texto_fijo_listas(db: Session, email: str) -> list[GlosaRecord]:
    """Mis glosas con dictamen texto fijo ya aplicado pero aún sin enviar."""
    q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.auditor_email == email)
        .filter(GlosaRecord.estado.in_(["PENDIENTE", "RATIFICADA", "EXTEMPORANEA"]))
        .filter(GlosaRecord.modelo_ia.ilike("%texto_fijo%"))
        .order_by(GlosaRecord.dias_restantes.asc())
        .limit(50)
    )
    return q.all()


def _menciones_pendientes(db: Session, email: str, dias: int = 14) -> list[ComentarioGlosaRecord]:
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    q = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.mencion == email)
        .filter(ComentarioGlosaRecord.resuelto == 0)
        .filter(ComentarioGlosaRecord.creado_en >= desde)
        .order_by(ComentarioGlosaRecord.creado_en.desc())
        .limit(20)
    )
    return q.all()


def _gold_nuevas_de_mis_eps(db: Session, email: str, dias: int = 7) -> list[PlantillaGoldRecord]:
    """Plantillas Gold creadas en los últimos `dias` cuyo EPS coincide con
    las EPS en las que el usuario ha trabajado (últimos 90 días)."""
    desde_nuevas = datetime.now(timezone.utc) - timedelta(days=dias)
    desde_trabajo = datetime.now(timezone.utc) - timedelta(days=90)

    # EPS en las que trabajé
    mis_eps_rows = (
        db.query(GlosaRecord.eps)
        .filter(GlosaRecord.auditor_email == email)
        .filter(GlosaRecord.creado_en >= desde_trabajo)
        .distinct()
        .limit(30)
        .all()
    )
    mis_eps = [r[0] for r in mis_eps_rows if r[0]]
    if not mis_eps:
        return []

    q = (
        db.query(PlantillaGoldRecord)
        .filter(PlantillaGoldRecord.eps.in_(mis_eps))
        .filter(PlantillaGoldRecord.activa == 1)
        .filter(PlantillaGoldRecord.creado_en >= desde_nuevas)
        .order_by(PlantillaGoldRecord.creado_en.desc())
        .limit(10)
    )
    return q.all()


def notificaciones_de(db: Session, usuario: UsuarioRecord) -> dict:
    """Arma el dict completo de notificaciones para el usuario dado."""
    email = (usuario.email or "").lower().strip()
    if not email:
        return {"total": 0, "items": {}}

    criticas = _glosas_criticas(db, email)
    vencidas = _glosas_vencidas(db, email)
    listas = _glosas_texto_fijo_listas(db, email)
    menciones = _menciones_pendientes(db, email)
    gold = _gold_nuevas_de_mis_eps(db, email)

    total = criticas + vencidas + len(listas) + len(menciones) + len(gold)

    return {
        "total": total,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "items": {
            "criticas_48h": {
                "conteo": criticas,
                "nivel": "alta" if criticas >= 3 else ("media" if criticas else "ok"),
            },
            "vencidas": {
                "conteo": vencidas,
                "nivel": "critica" if vencidas else "ok",
            },
            "listas_para_enviar": {
                "conteo": len(listas),
                "nivel": "info",
                "top": [
                    {
                        "glosa_id": g.id,
                        "codigo": g.codigo_glosa,
                        "eps": g.eps,
                        "valor": float(g.valor_objetado or 0),
                        "dias_restantes": g.dias_restantes,
                    }
                    for g in listas[:10]
                ],
            },
            "menciones": {
                "conteo": len(menciones),
                "nivel": "alta" if len(menciones) >= 3 else "info",
                "top": [
                    {
                        "glosa_id": c.glosa_id,
                        "autor": c.autor_nombre or c.autor_email,
                        "texto": (c.texto or "")[:160],
                        "fecha": c.creado_en.isoformat() if c.creado_en else None,
                    }
                    for c in menciones[:10]
                ],
            },
            "gold_nuevas": {
                "conteo": len(gold),
                "nivel": "info",
                "top": [
                    {
                        "id": p.id,
                        "eps": p.eps,
                        "codigo": p.codigo_glosa,
                        "titulo": p.titulo,
                    }
                    for p in gold[:5]
                ],
            },
        },
    }
