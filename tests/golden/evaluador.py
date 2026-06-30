"""Evaluador del golden set — corre los detectores y sanitizers DETERMINISTAS
del motor sobre casos reales y verifica criterios objetivos de calidad.

NO llama al LLM (caro, no determinista, requiere API key). Mide exactamente
el pipeline determinista donde estuvieron las 20 rondas de bugs:
  - Detección de EPS efectiva (dropdown vs texto)
  - Detección de sub-conceptos (concepto×concepto)
  - Detección de complejidad (escalación a Claude)
  - Detección de sanciones ilegales
  - Detección de contrato y cláusulas citadas
  - Sanitizers que limpian dictámenes con bugs conocidos

Uso programático:
    from tests.golden.evaluador import evaluar_todo
    reporte = evaluar_todo()
    assert reporte["fallidos"] == 0
"""

from __future__ import annotations

import json
import os

_CASOS_PATH = os.path.join(os.path.dirname(__file__), "casos_glosas.json")


def cargar_casos() -> dict:
    with open(_CASOS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _evaluar_caso_glosa(caso: dict) -> list[dict]:
    """Corre los detectores sobre una glosa y verifica sus criterios.
    Devuelve lista de {criterio, ok, detalle}.
    """
    from app.services.cups_soat_service import homologar_cups_a_soat  # noqa: F401
    from app.services.glosa_ia_prompts import resolver_eps_efectiva
    from app.services.glosa_service import (
        _RE_SANCION_EPS_MENCIONADA,
        _auditar_clausulas_citadas_en_glosa,
        _detectar_contrato_citado_en_glosa,
    )
    from app.services.routing_complejidad import detectar_complejidad_critica
    from app.services.subconceptos_glosa import detectar_subconceptos

    glosa = caso["glosa"]
    crit = caso.get("criterios", {})
    res: list[dict] = []

    def _check(nombre: str, ok: bool, detalle: str = "") -> None:
        res.append({"criterio": nombre, "ok": bool(ok), "detalle": detalle})

    # EPS efectiva
    if "eps_efectiva_contiene" in crit:
        eps_ef, corregida, _ = resolver_eps_efectiva(caso.get("eps_dropdown", ""), glosa)
        _check(
            "eps_efectiva_contiene",
            crit["eps_efectiva_contiene"].upper() in eps_ef.upper(),
            f"esperado≈{crit['eps_efectiva_contiene']} obtenido={eps_ef}",
        )
        if "eps_fue_corregida" in crit:
            _check(
                "eps_fue_corregida",
                corregida == crit["eps_fue_corregida"],
                f"corregida={corregida}",
            )

    # Sub-conceptos
    subs = detectar_subconceptos(glosa)
    if "min_subconceptos" in crit:
        _check(
            "min_subconceptos",
            len(subs) >= crit["min_subconceptos"],
            f"esperado>={crit['min_subconceptos']} obtenido={len(subs)}",
        )
    if "max_subconceptos" in crit:
        _check(
            "max_subconceptos",
            len(subs) <= crit["max_subconceptos"],
            f"esperado<={crit['max_subconceptos']} obtenido={len(subs)}",
        )

    # Sanción ilegal
    if "detecta_sancion_ilegal" in crit:
        tiene = bool(_RE_SANCION_EPS_MENCIONADA.search(glosa))
        _check(
            "detecta_sancion_ilegal",
            tiene == crit["detecta_sancion_ilegal"],
            f"esperado={crit['detecta_sancion_ilegal']} obtenido={tiene}",
        )

    # Contrato citado
    if "contrato_citado" in crit:
        cod = _detectar_contrato_citado_en_glosa(glosa)
        _check(
            "contrato_citado",
            cod == crit["contrato_citado"],
            f"esperado={crit['contrato_citado']} obtenido={cod}",
        )

    # Cláusulas citadas
    if "clausulas_citadas" in crit:
        # Dictamen dummy NO vacío que no menciona cláusulas → las citadas en
        # la glosa quedan "evadidas" = exactamente las detectadas. (Con
        # dictamen vacío la función retorna temprano sin evaluar.)
        _ok, evadidas = _auditar_clausulas_citadas_en_glosa(
            "dictamen de prueba sin mencion de clausulas", glosa
        )
        detectadas = sorted(evadidas)
        esperadas = sorted(crit["clausulas_citadas"])
        _check(
            "clausulas_citadas",
            all(c in detectadas for c in esperadas),
            f"esperadas={esperadas} detectadas={detectadas}",
        )

    # Complejidad (escalación a Claude)
    if "es_complejo" in crit:
        try:
            valor = int(caso.get("valor_objetado") or 0)
        except (TypeError, ValueError):
            valor = 0
        comp = detectar_complejidad_critica(
            valor=valor,
            num_codigos=len(subs),
            texto_glosa=glosa,
        )
        _check(
            "es_complejo",
            comp.es_complejo == crit["es_complejo"],
            f"esperado={crit['es_complejo']} obtenido={comp.es_complejo} motivos={comp.motivos}",
        )
        if "complejidad_motivo_contiene" in crit:
            motivos_txt = " ".join(comp.motivos).upper()
            _check(
                "complejidad_motivo_contiene",
                crit["complejidad_motivo_contiene"].upper() in motivos_txt,
                f"esperado≈{crit['complejidad_motivo_contiene']} motivos={comp.motivos}",
            )

    return res


def _evaluar_dictamen_con_bugs(caso: dict) -> list[dict]:
    """Aplica el sanitizer indicado a un dictamen sucio y verifica que
    limpie el bug (no_debe_contener) y conserve lo bueno (debe_contener).
    """
    from app.services.glosa_service import (
        _neutralizar_alucinaciones_prompt,
        _rechazar_sancion_eps_ilegal,
        _reescribir_negacion_contrato,
    )

    sucio = caso["dictamen_sucio"]
    aplicar = caso["aplicar"]
    glosa_ctx = caso.get("glosa_contexto", "")

    if aplicar == "neutralizar_alucinaciones_prompt":
        limpio = _neutralizar_alucinaciones_prompt(sucio)
    elif aplicar == "reescribir_negacion_contrato":
        limpio = _reescribir_negacion_contrato(sucio, texto_glosa=glosa_ctx)
    elif aplicar == "rechazar_sancion_eps_ilegal":
        limpio = _rechazar_sancion_eps_ilegal(sucio, texto_glosa=glosa_ctx)
    else:
        return [{"criterio": "aplicar_desconocido", "ok": False, "detalle": aplicar}]

    res: list[dict] = []
    limpio_low = limpio.lower()
    for frag in caso.get("no_debe_contener", []):
        res.append(
            {
                "criterio": f"no_contiene:{frag[:30]}",
                "ok": frag.lower() not in limpio_low,
                "detalle": f"resultado={limpio[:120]}",
            }
        )
    for frag in caso.get("debe_contener", []):
        res.append(
            {
                "criterio": f"contiene:{frag[:30]}",
                "ok": frag.lower() in limpio_low,
                "detalle": f"resultado={limpio[:120]}",
            }
        )
    alguno = caso.get("debe_contener_alguno", [])
    if alguno:
        res.append(
            {
                "criterio": "contiene_alguno",
                "ok": any(f.lower() in limpio_low for f in alguno),
                "detalle": f"resultado={limpio[:120]}",
            }
        )
    return res


def evaluar_todo() -> dict:
    """Corre TODOS los casos y devuelve un reporte agregado.

    Returns:
        {
          "total_criterios": int,
          "aprobados": int,
          "fallidos": int,
          "detalle_por_caso": {caso_id: [{criterio, ok, detalle}, ...]},
          "fallos": [{caso, criterio, detalle}, ...],
        }
    """
    data = cargar_casos()
    detalle: dict[str, list] = {}
    fallos: list[dict] = []
    total = aprobados = 0

    for caso in data.get("casos_glosa", []):
        res = _evaluar_caso_glosa(caso)
        detalle[caso["id"]] = res
        for r in res:
            total += 1
            if r["ok"]:
                aprobados += 1
            else:
                fallos.append({"caso": caso["id"], **r})

    for caso in data.get("dictamenes_con_bugs", []):
        res = _evaluar_dictamen_con_bugs(caso)
        detalle[caso["id"]] = res
        for r in res:
            total += 1
            if r["ok"]:
                aprobados += 1
            else:
                fallos.append({"caso": caso["id"], **r})

    return {
        "total_criterios": total,
        "aprobados": aprobados,
        "fallidos": total - aprobados,
        "detalle_por_caso": detalle,
        "fallos": fallos,
    }
