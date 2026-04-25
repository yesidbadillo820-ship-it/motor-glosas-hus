"""Aprendizaje por retroalimentación de la EPS (Ronda 3).

Cuando la EPS **LEVANTA** una glosa (nos dio la razón), el argumento que
ganó se promueve automáticamente a Plantilla Gold para esa combinación
(EPS + código) — así la IA la usa como few-shot en nuevas glosas.

Cuando **RATIFICA** (nos mantuvo la glosa), desactivamos cualquier Gold
previa de esa combinación para que no se siga sugiriendo un argumento
que demostró no ser eficaz. Creamos un registro de "argumento bloqueado"
en notas para aprender qué NO hacer.

Cuando **ACEPTA** (HUS aceptó pagar), no hay nada que aprender.

Reglas operativas:
  - No promover si la glosa tuvo valor_recuperado == 0 (no hubo ganancia real).
  - No promover si el dictamen es una plantilla fija (texto_fijo, plantilla,
    pre-analisis/*) — esas ya están curadas, promover duplicaría.
  - Limitar a 5 plantillas Gold por (eps, código) para no inflar la BD:
    si hay 5+, rotar la más antigua.
"""
from __future__ import annotations

import re

from app.core.tz import ahora_utc

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.models.db import GlosaRecord, PlantillaGoldRecord

# Modelos "plantilla" que NO necesitan aprender (ya están curados)
_MODELOS_SKIP = (
    "texto_fijo", "plantilla", "error", "cache", "db-cache",
    "pre-analisis/texto_fijo",
)

_MAX_GOLD_POR_COMBINACION = 5


def _extraer_argumento_del_dictamen(dictamen_html: str) -> str:
    """Extrae el argumento en texto plano del HTML del dictamen.

    Busca el marker 'ARGUMENTACIÓN JURÍDICA' y toma el texto hasta la nota
    de IA o el footer. Si no encuentra, devuelve vacío.
    """
    if not dictamen_html:
        return ""
    # Quitar tags HTML básicos
    txt = re.sub(r"<script[\s\S]*?</script>", " ", dictamen_html, flags=re.IGNORECASE)
    txt = re.sub(r"<style[\s\S]*?</style>", " ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    # Buscar marker
    m = re.search(r"ARGUMENTACI[ÓO]N\s+JUR[ÍI]DICA", txt, re.IGNORECASE)
    if m:
        txt = txt[m.end():].strip()
    # Cortar en cierres conocidos
    for cierre in [
        "Nota: Generado con asistencia",
        "FUNDAMENTO NORMATIVO",
        "📎 RELACIÓN DE SOPORTES",
        "RELACIÓN DE SOPORTES",
        "SINAC SC SAS",
        "Documento generado por",
    ]:
        idx = txt.find(cierre)
        if idx > -1:
            txt = txt[:idx].strip()
            break
    return txt[:4000]  # Limitar tamaño


def aprender_de_decision_eps(
    db: Session,
    glosa: GlosaRecord,
    decision: str,
    creado_por: str,
) -> dict:
    """Actualiza la base de conocimiento según la decisión de la EPS.

    Retorna un dict con la acción tomada (promovida, bloqueada, skip).
    """
    decision = (decision or "").upper()
    eps = (glosa.eps or "").strip()
    codigo = (glosa.codigo_glosa or "").strip()
    if not eps or not codigo:
        return {"accion": "skip", "razon": "sin eps o código"}

    modelo = (glosa.modelo_ia or "").lower()
    if any(m in modelo for m in _MODELOS_SKIP):
        return {"accion": "skip", "razon": f"modelo {modelo} ya curado"}

    if decision == "LEVANTADA":
        return _promover_a_gold(db, glosa, eps, codigo, creado_por)
    if decision == "RATIFICADA":
        return _desactivar_gold(db, glosa, eps, codigo, creado_por)
    return {"accion": "skip", "razon": f"decisión {decision} no dispara aprendizaje"}


def _promover_a_gold(
    db: Session, glosa: GlosaRecord, eps: str, codigo: str, creado_por: str
) -> dict:
    """Crea una nueva Plantilla Gold a partir del argumento ganador."""
    if (glosa.valor_recuperado or 0.0) <= 0:
        return {"accion": "skip", "razon": "sin valor_recuperado > 0"}

    argumento = _extraer_argumento_del_dictamen(glosa.dictamen or "")
    if len(argumento) < 100:
        return {"accion": "skip", "razon": "argumento demasiado corto"}

    # Evitar duplicados: si ya existe Gold con el mismo argumento (primeros
    # 200 chars) no crear otra.
    firma = argumento[:200].strip()
    existente = (
        db.query(PlantillaGoldRecord)
        .filter(PlantillaGoldRecord.eps == eps)
        .filter(PlantillaGoldRecord.codigo_glosa == codigo)
        .filter(PlantillaGoldRecord.activa == 1)
        .filter(PlantillaGoldRecord.argumento.like(firma + "%"))
        .first()
    )
    if existente:
        return {"accion": "skip", "razon": "argumento ya existe en Gold", "gold_id": existente.id}

    # Rotar si ya hay 5 plantillas — desactivar la más antigua
    activas = (
        db.query(PlantillaGoldRecord)
        .filter(PlantillaGoldRecord.eps == eps)
        .filter(PlantillaGoldRecord.codigo_glosa == codigo)
        .filter(PlantillaGoldRecord.activa == 1)
        .order_by(PlantillaGoldRecord.creado_en.asc())
        .all()
    )
    if len(activas) >= _MAX_GOLD_POR_COMBINACION:
        activas[0].activa = 0
        logger.info(
            f"[GOLD-ROTATE] Desactivada Gold #{activas[0].id} "
            f"({eps}/{codigo}) por límite de {_MAX_GOLD_POR_COMBINACION}"
        )

    nueva = PlantillaGoldRecord(
        eps=eps,
        codigo_glosa=codigo,
        tipo=(codigo[:2] or "FA").upper(),
        titulo=f"Gold auto · {eps[:40]} · {codigo} · ${int(glosa.valor_recuperado or 0):,}",
        argumento=argumento,
        glosa_origen_id=glosa.id,
        valor_recuperado=float(glosa.valor_recuperado or 0.0),
        usos=0,
        creado_por=f"auto-feedback ({creado_por})",
        notas=(
            f"Promovida automáticamente el {ahora_utc().isoformat()} "
            f"tras decisión EPS=LEVANTADA. Valor recuperado: "
            f"${int(glosa.valor_recuperado or 0):,}."
        ),
        activa=1,
    )
    db.add(nueva)
    db.commit()
    logger.info(
        f"[GOLD-AUTO] Promovida argumento de glosa #{glosa.id} → Gold #{nueva.id} "
        f"({eps}/{codigo}, recuperado=${int(glosa.valor_recuperado or 0):,})"
    )
    return {"accion": "promovida", "gold_id": nueva.id, "eps": eps, "codigo": codigo}


def _desactivar_gold(
    db: Session, glosa: GlosaRecord, eps: str, codigo: str, creado_por: str
) -> dict:
    """Si hay Gold activa para (eps, código) y el argumento del ratificado
    es similar, marca la Gold como NO eficaz (activa=0 + nota)."""
    argumento_ratificado = _extraer_argumento_del_dictamen(glosa.dictamen or "")
    if len(argumento_ratificado) < 100:
        return {"accion": "skip", "razon": "sin argumento identificable"}

    firma = argumento_ratificado[:200].strip()
    activas = (
        db.query(PlantillaGoldRecord)
        .filter(PlantillaGoldRecord.eps == eps)
        .filter(PlantillaGoldRecord.codigo_glosa == codigo)
        .filter(PlantillaGoldRecord.activa == 1)
        .all()
    )
    desactivadas = 0
    for g in activas:
        if g.argumento and g.argumento[:200].strip() == firma:
            g.activa = 0
            g.notas = (
                (g.notas or "") +
                f"\n[DESACTIVADA auto {ahora_utc().isoformat()}] "
                f"El mismo argumento fue ratificado por la EPS en glosa #{glosa.id}."
            )
            desactivadas += 1
    if desactivadas:
        db.commit()
        logger.warning(
            f"[GOLD-DEACTIVATE] {desactivadas} Gold(s) desactivadas para "
            f"{eps}/{codigo} tras ratificación de glosa #{glosa.id}"
        )
    return {
        "accion": "desactivadas",
        "cantidad": desactivadas,
        "eps": eps,
        "codigo": codigo,
    }
