"""Auto-Pilot Zero-Touch con las cuatro salvaguardas del auditor (V2, Pilar 2).

03-09-2026. La DECISIÓN ya existía (`autopilot_service` evalúa, `auto_pilot_
decision` clasifica). Lo que faltaba —y lo que este módulo agrega— son las
cuatro reglas de gobierno que ordenó el auditor antes de dejar que la máquina
toque el estado de una glosa:

1. FEATURE FLAG DE SEGURIDAD. Todo gobernado por AUTO_PILOT_ENABLED (apagado
   por defecto). Si está en falso, `procesar()` aborta EN SU PRIMERA LÍNEA:
   no consulta, no escribe, no registra.

2. ESTADO DE CUARENTENA. La IA tiene PROHIBIDO usar «RESPONDIDA» o «ENVIADA».
   Toda glosa que pase las reglas muta únicamente a
   PENDIENTE_APROBACION_HUMANA — la bandeja de borradores. La liberación
   final la hace UNA PERSONA con un clic afirmativo (`liberar()`), y solo
   entonces la glosa queda RESPONDIDA, a nombre de esa persona.

3. BITÁCORA INMUTABLE. Cada decisión de la máquina queda en la tabla
   `auto_pilot_bitacora`: glosa, regla aplicada, confianza matemática,
   riesgo y los identificadores de lo que analizó. Solo se INSERTA: la
   liberación humana es una fila nueva, jamás se edita una existente.

4. REGLAS DE NEGOCIO ESTRICTAS. Candidata solo si: confianza > 92 %, valor
   objetado < $500.000 y riesgo BAJO. Y además: nunca una abstención (el
   caso «sin nada» se RECHAZA), nunca una aceptación parcial (repartir plata
   la aprueba un humano), nunca sin dictamen. Un rechazo es un fallo
   CONTROLADO: decisión registrada con su porqué, sin excepciones al aire.

Escudos de resiliencia (hotfix 03-09-2026), condición del auditor para
encender el flag:

- TRAZABILIDAD DEL FALLBACK. Cada fila de la bitácora registra
  `modelo_utilizado`: el modelo que produjo el dictamen decidido — Claude
  (Anthropic) o el fallback de Groq, tal como quedó en historial.modelo_ia.
- BLOQUEO DEL INDEXADOR. Si el indexador de soportes reporta
  «construyendo: true» (o su estado no se puede leer), el ciclo ABORTA
  entero antes de evaluar nada: un índice a medio armar hace ver vacíos
  expedientes que están completos, y sobre esa mentira no se decide.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging_utils import logger

# El único estado que la máquina puede escribir. Los prohibidos, por escrito.
ESTADO_CUARENTENA = "PENDIENTE_APROBACION_HUMANA"
ESTADOS_PROHIBIDOS_PARA_IA = ("RESPONDIDA", "ENVIADA", "ENVIADA_A_EPS")

# Reglas de negocio del auditor (03-09-2026).
UMBRAL_CONFIANZA = 0.92
TOPE_VALOR_COP = 500_000.0
RIESGO_REQUERIDO = "BAJO"

ACTOR_MAQUINA = "auto-pilot"


def habilitado() -> bool:
    """AUTO_PILOT_ENABLED — apagado por defecto."""
    return (os.getenv("AUTO_PILOT_ENABLED", "") or "").strip().lower() in ("1", "true", "si", "sí")


def indexador_en_construccion() -> tuple[bool, str]:
    """¿El indexador de soportes está a medio construir?

    Devuelve (True, motivo) si reporta «construyendo: true» O si su estado no
    se puede leer — en la duda, el ciclo no corre. Un índice incompleto le
    haría creer a la máquina que facturas con expediente completo no tienen
    soportes, y esa mentira contamina confianza, riesgo y bitácora.
    """
    try:
        from app.services.soportes_autodiscovery_service import get_indexer

        stats = get_indexer().stats() or {}
    except Exception as e:  # noqa: BLE001 — estado ilegible = no se decide
        return True, f"Estado del indexador ilegible ({str(e)[:120]}): no se decide a ciegas."
    if bool(stats.get("construyendo")):
        return True, "El indexador de soportes reporta construyendo=true."
    return False, ""


def _modelo_utilizado_de(glosa: Any) -> str:
    """Qué modelo produjo el dictamen que se está decidiendo (trazabilidad
    del fallback): el valor real de historial.modelo_ia — el nombre del
    modelo de Anthropic o del fallback de Groq que enrutó ia_router."""
    return str(getattr(glosa, "modelo_ia", "") or "")


def _soportes_analizados(glosa: Any, senales: Optional[dict] = None) -> list[str]:
    """Identificadores REALES de lo que la evaluación tuvo a la vista.

    Marcas «DOCUMENTO: x.pdf» del expediente guardado, más las señales del
    evaluador (plantillas gold, calidad del dictamen). Si no hay nada, lista
    vacía: no se inventan soportes.
    """
    import re

    ids: list[str] = []
    for campo in ("texto_glosa_original", "dictamen"):
        texto = str(getattr(glosa, campo, "") or "")
        for m in re.findall(r"DOCUMENTO:\s*([^\s═»\"]+)", texto):
            marca = f"documento:{m.strip()}"
            if marca not in ids:
                ids.append(marca)
    if getattr(glosa, "dictamen", None):
        ids.append(f"dictamen:glosa_{getattr(glosa, 'id', 's/n')}")
    for clave in ("plantillas_gold", "calidad_dictamen"):
        if senales and senales.get(clave) is not None:
            ids.append(f"senal:{clave}")
    return ids


def evaluar_candidata(db: Any, glosa: Any) -> dict:
    """Aplica las reglas estrictas a UNA glosa. Devuelve la decisión con su
    porqué — un rechazo es un resultado, no una excepción.

    {"decision": "CANDIDATA"|"RECHAZADA", "regla_aplicada": str,
     "confianza": float|None, "riesgo": str, "soportes": [str, ...]}
    """
    from app.services.autopilot_service import evaluar_glosa_autopilot
    from app.services.riesgo_ratificacion import calcular_riesgo

    modelo_utilizado = _modelo_utilizado_de(glosa)

    def _rechazo(regla: str, confianza=None, riesgo="", soportes=None) -> dict:
        return {
            "decision": "RECHAZADA",
            "regla_aplicada": regla,
            "confianza": confianza,
            "riesgo": riesgo,
            "soportes": soportes or [],
            "modelo_utilizado": modelo_utilizado,
        }

    modelo = modelo_utilizado.lower()
    dictamen = str(getattr(glosa, "dictamen", "") or "").strip()

    # Los rechazos duros primero: lo que jamás se auto-envía.
    if not dictamen:
        return _rechazo("Sin dictamen generado: no hay nada que enviar.")
    if "abstencion" in modelo:
        return _rechazo(
            "Dictamen de ABSTENCIÓN (glosa sin soportes ni elementos): el caso "
            "«sin nada» no se auto-envía — lo mira una persona."
        )
    cod_resp = str(getattr(glosa, "codigo_respuesta", "") or "")
    if "RE9801" in cod_resp or "PARCIAL" in str(getattr(glosa, "estado", "") or "").upper():
        return _rechazo(
            "Aceptación PARCIAL: repartir dinero entre aceptar y defender lo "
            "aprueba un humano, no la máquina."
        )

    # Señales del evaluador que ya existía (confianza matemática 0-1).
    resultado = evaluar_glosa_autopilot(db, glosa)
    confianza = float(getattr(resultado, "confianza", 0.0) or 0.0)
    senales = getattr(resultado, "detalle", {}) or {}
    soportes = _soportes_analizados(glosa, senales)

    if getattr(resultado, "estado", "") == "INTERVENIR":
        return _rechazo(
            "El evaluador marcó INTERVENIR: " + "; ".join(resultado.razones_en_contra[:3]),
            confianza,
            "",
            soportes,
        )
    if confianza <= UMBRAL_CONFIANZA:
        return _rechazo(
            f"Confianza {confianza:.0%} no supera el umbral estricto del {UMBRAL_CONFIANZA:.0%}.",
            confianza,
            "",
            soportes,
        )

    try:
        valor = float(getattr(glosa, "valor_objetado", 0) or 0)
    except (TypeError, ValueError):
        valor = 0.0
    if valor <= 0 or valor >= TOPE_VALOR_COP:
        return _rechazo(
            f"Valor objetado ${valor:,.0f} fuera del rango auto-enviable "
            f"(0 < valor < ${TOPE_VALOR_COP:,.0f}).".replace(",", "."),
            confianza,
            "",
            soportes,
        )

    riesgo = calcular_riesgo(
        codigo_glosa=str(getattr(glosa, "codigo_glosa", "") or ""),
        eps=str(getattr(glosa, "eps", "") or ""),
        tiene_contrato=bool(getattr(glosa, "contrato", None)),
        tiene_pdf_soportes=any(s.startswith("documento:") for s in soportes),
        texto_glosa=str(getattr(glosa, "texto_glosa_original", "") or ""),
        es_extemporanea="extempor" in modelo,
        es_ratificacion="ratificada" in modelo,
        score_dictamen=confianza * 100,
    )
    nivel = str(riesgo.get("nivel", "") or "")
    if nivel != RIESGO_REQUERIDO:
        return _rechazo(
            f"Riesgo de ratificación {nivel or 'desconocido'}: solo se "
            f"auto-envía con riesgo {RIESGO_REQUERIDO}.",
            confianza,
            nivel,
            soportes,
        )

    return {
        "decision": "CANDIDATA",
        "regla_aplicada": (
            f"Confianza {confianza:.0%} > {UMBRAL_CONFIANZA:.0%} · valor "
            f"${valor:,.0f} < ${TOPE_VALOR_COP:,.0f} · riesgo {nivel}".replace(",", ".")
        ),
        "confianza": confianza,
        "riesgo": nivel,
        "soportes": soportes,
        "modelo_utilizado": modelo_utilizado,
    }


def _registrar(db: Any, glosa_id: Optional[int], decision: dict, actor: str) -> None:
    """Una fila NUEVA en la bitácora. Nunca se edita una existente."""
    from app.models.db import AutoPilotBitacoraRecord

    db.add(
        AutoPilotBitacoraRecord(
            glosa_id=glosa_id,
            decision=decision.get("decision", ""),
            regla_aplicada=(decision.get("regla_aplicada", "") or "")[:2000],
            confianza=decision.get("confianza"),
            riesgo=(decision.get("riesgo", "") or "")[:20],
            soportes_analizados=json.dumps(decision.get("soportes", []), ensure_ascii=False)[:4000],
            actor=actor[:120],
            modelo_utilizado=(decision.get("modelo_utilizado", "") or "")[:100],
        )
    )


def procesar(db: Any, limite: int = 50) -> dict:
    """El worker. LA PRIMERA LÍNEA ES EL FLAG: apagado, no toca nada."""
    if not habilitado():  # ← salvaguarda nº 1: aborta aquí mismo
        return {"estado": "deshabilitado", "detalle": "AUTO_PILOT_ENABLED no está activo."}

    # Bloqueo del indexador (hotfix 03-09-2026): con el índice de soportes a
    # medio construir el ciclo entero ABORTA — sin evaluar, sin escribir, sin
    # registrar. El siguiente ciclo lo reintenta cuando el índice esté quieto.
    construyendo, motivo = indexador_en_construccion()
    if construyendo:
        logger.warning(f"[AUTO-PILOT] Ciclo abortado por el indexador: {motivo}")
        return {"estado": "abortado_por_indexador", "detalle": motivo}

    from app.models.db import GlosaRecord
    from app.services.motor_vencimientos import ESTADOS_CERRADOS

    parte = {"estado": "ok", "evaluadas": 0, "en_cuarentena": 0, "rechazadas": 0}
    q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.dictamen.isnot(None))
        .filter(
            ~GlosaRecord.workflow_state.in_(
                [ESTADO_CUARENTENA, *ESTADOS_PROHIBIDOS_PARA_IA, *ESTADOS_CERRADOS]
            )
        )
        .order_by(GlosaRecord.id.desc())
        .limit(limite)
    )
    for glosa in q.all():
        parte["evaluadas"] += 1
        try:
            decision = evaluar_candidata(db, glosa)
        except Exception as e:  # noqa: BLE001 — fallo CONTROLADO, nunca al aire
            decision = {
                "decision": "RECHAZADA",
                "regla_aplicada": f"Evaluación cayó ({str(e)[:120]}): en la duda, humano.",
                "confianza": None,
                "riesgo": "",
                "soportes": [],
                "modelo_utilizado": _modelo_utilizado_de(glosa),
            }
        _registrar(db, glosa.id, decision, ACTOR_MAQUINA)
        if decision["decision"] == "CANDIDATA":
            # Salvaguarda nº 2: SOLO el estado de cuarentena. Jamás RESPONDIDA.
            glosa.workflow_state = ESTADO_CUARENTENA
            parte["en_cuarentena"] += 1
        else:
            parte["rechazadas"] += 1
    db.commit()
    logger.info(
        f"[AUTO-PILOT] evaluadas={parte['evaluadas']} "
        f"cuarentena={parte['en_cuarentena']} rechazadas={parte['rechazadas']}"
    )
    return parte


def devolver(db: Any, glosa_id: int, usuario_email: str, motivo: str = "") -> dict:
    """El otro clic humano: sacar un borrador de la bandeja SIN radicarlo.

    La glosa vuelve a revisión manual (RADICADA) con el porqué en la nota,
    y la devolución queda en la bitácora como fila nueva — igual que la
    liberación, a nombre de quien la decidió."""
    from app.models.db import GlosaRecord

    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if glosa is None:
        return {"estado": "no_existe"}
    if glosa.workflow_state != ESTADO_CUARENTENA:
        return {"estado": "no_esta_en_borradores", "workflow_state": glosa.workflow_state}
    motivo_txt = (motivo or "").strip()
    glosa.workflow_state = "RADICADA"
    glosa.nota_workflow = (
        f"Devuelta de borradores del Auto-Pilot por {usuario_email}"
        + (f": {motivo_txt}" if motivo_txt else "")
    )[:500]
    _registrar(
        db,
        glosa_id,
        {
            "decision": "DEVUELTA_POR_HUMANO",
            "regla_aplicada": (
                "Clic de devolución en la bandeja de borradores."
                + (f" Motivo: {motivo_txt}" if motivo_txt else "")
            ),
            "confianza": None,
            "riesgo": "",
            "soportes": [],
            "modelo_utilizado": _modelo_utilizado_de(glosa),
        },
        usuario_email,
    )
    db.commit()
    return {"estado": "devuelta", "glosa_id": glosa_id}


def liberar(db: Any, glosa_id: int, usuario_email: str) -> dict:
    """El clic humano afirmativo. Solo una persona saca un borrador de la
    bandeja; queda a su nombre en la bitácora (fila nueva, nada se edita)."""
    from app.models.db import GlosaRecord

    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if glosa is None:
        return {"estado": "no_existe"}
    if glosa.workflow_state != ESTADO_CUARENTENA:
        return {"estado": "no_esta_en_borradores", "workflow_state": glosa.workflow_state}
    glosa.workflow_state = "RESPONDIDA"  # acción HUMANA: sí puede
    if not getattr(glosa, "fecha_decision_eps", None):
        glosa.fecha_decision_eps = datetime.now(timezone.utc)
    glosa.nota_workflow = f"Liberada de borradores del Auto-Pilot por {usuario_email}"
    _registrar(
        db,
        glosa_id,
        {
            "decision": "LIBERADA_POR_HUMANO",
            "regla_aplicada": "Clic afirmativo en la bandeja de borradores.",
            "confianza": None,
            "riesgo": "",
            "soportes": [],
            "modelo_utilizado": _modelo_utilizado_de(glosa),
        },
        usuario_email,
    )
    db.commit()
    return {"estado": "liberada", "glosa_id": glosa_id}
