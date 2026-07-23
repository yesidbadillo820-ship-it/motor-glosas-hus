"""piloto_conciliacion_dispensario.py — Orquestador del piloto (extremo a extremo).

Corre TODO el flujo sobre unos pocos casos representativos y mide si el sistema
esta listo antes de seguir con el Modulo Juridico:

    indice -> expediente -> evidencia -> hechos probados -> decision

Selecciona casos representativos (mayor valor, mas glosas, contrato 287, 440, y
uno "conocido") o los que le indiques, y deja una CARPETA POR EXPEDIENTE con
cada etapa en su archivo, mas un tablero de METRICAS y la evaluacion de los
UMBRALES DE ACEPTACION.

Salida:
    <salida-dir>/
      HUS0000446262/
        expediente.json  evidencia.json  hechos.json  decision.json
        resumen.txt      log.txt
      ...
      METRICAS.json      (indicadores + umbrales de aceptacion)

USO
---
    py tools\\piloto_conciliacion_dispensario.py ^
        --excel   "D:\\...\\HUS.xlsx" ^
        --indice  "D:\\...\\indice_soportes.json" ^
        --cartera "D:\\...\\Estado_Cartera_JUN_2026.xlsx" ^
        --auto  --conocido HUS0000436483 ^
        --salida-dir "D:\\...\\Piloto"

    # O casos explicitos:
    ...  --facturas "HUS0000446262,HUS0000452150,HUS0000426013"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from asistente_conciliacion_dispensario import cargar_glosas, factura_corta  # noqa: E402
from expediente_conciliacion import cartera_desde_xlsx, construir_expedientes  # noqa: E402
from motor_decision_dispensario import decidir_expedientes  # noqa: E402
from motor_evidencia_dispensario import enriquecer_expedientes  # noqa: E402
from motor_verificacion_dispensario import verificar_expedientes  # noqa: E402

logger = logging.getLogger("piloto")

# Umbrales de aceptacion (los propuso el auditor). Si no se cumplen, la
# prioridad es corregir el flujo, no agregar funcionalidades.
UMBRALES = {
    "pct_facturas_con_soporte": 95.0,
    "pct_glosas_con_evidencia": 90.0,
    "pct_hechos_evaluados": 90.0,
    "decisiones_sin_soporte_probatorio": 0,  # 0 levantamientos sin hecho probado
    "pct_decisiones_trazables": 100.0,
}


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# Seleccion de casos representativos
# ---------------------------------------------------------------------------
def seleccionar_casos(expedientes: list[dict], conocido: str | None) -> list[str]:
    """Devuelve hasta 5 facturas (cortas) representativas, sin repetir."""
    if not expedientes:
        return []

    def corta(e):
        return e["factura_corta"]

    elegidos: list[str] = []

    def agregar(e):
        if e and corta(e) not in elegidos:
            elegidos.append(corta(e))

    agregar(max(expedientes, key=lambda e: e.get("valor_objetado_total", 0)))  # mayor valor
    agregar(max(expedientes, key=lambda e: len(e.get("glosas", []))))  # mas glosas
    c287 = [
        e
        for e in expedientes
        if e.get("contrato", {}).get("codigo") == "287" and corta(e) not in elegidos
    ]
    if c287:
        agregar(max(c287, key=lambda e: e.get("valor_objetado_total", 0)))  # 287 distinto
    c440 = [e for e in expedientes if e.get("contrato", {}).get("codigo") == "440"]
    if c440:
        agregar(max(c440, key=lambda e: e.get("valor_objetado_total", 0)))  # 440
    if conocido:
        ck = factura_corta(conocido)
        e = next((x for x in expedientes if corta(x) == ck), None)
        if e:
            agregar(e)
    return elegidos[:5]


# ---------------------------------------------------------------------------
# Salidas por expediente
# ---------------------------------------------------------------------------
def _glosas_slice(exp: dict, campos: list[str]) -> list[dict]:
    out = []
    for g in exp.get("glosas", []):
        fila = {"codigo_corto": g.get("codigo_corto", ""), "servicio": g.get("servicio", "")}
        for c in campos:
            if c in g:
                fila[c] = g[c]
        out.append(fila)
    return out


def escribir_expediente(exp: dict, base: Path) -> None:
    carpeta = base / exp["factura"]
    carpeta.mkdir(parents=True, exist_ok=True)

    # expediente.json (nucleo, sin las capas derivadas)
    nucleo = {k: v for k, v in exp.items() if k not in ("glosas",)}
    nucleo["glosas"] = _glosas_slice(exp, [])
    (carpeta / "expediente.json").write_text(
        json.dumps(nucleo, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (carpeta / "evidencia.json").write_text(
        json.dumps({"glosas": _glosas_slice(exp, ["evidencias"])}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (carpeta / "hechos.json").write_text(
        json.dumps(
            {"alertas": exp.get("alertas", []), "glosas": _glosas_slice(exp, ["hechos_probados"])},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    (carpeta / "decision.json").write_text(
        json.dumps(
            {
                "defendibilidad_promedio": exp.get("defendibilidad_promedio"),
                "decision_dominante": exp.get("decision_dominante"),
                "glosas": _glosas_slice(exp, ["decision"]),
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    # resumen.txt legible
    lineas = [
        f"EXPEDIENTE {exp['factura']}  —  {exp.get('paciente', {}).get('nombre', '')}",
        f"Contrato: {exp.get('contrato', {}).get('codigo')}  "
        f"({exp.get('contrato', {}).get('base_tarifaria', '')})",
        f"Cartera: saldo ${exp.get('cartera', {}).get('saldo', 0):,}  "
        f"edad {exp.get('cartera', {}).get('edad_dias', 0)}d",
        f"Defendibilidad promedio: {exp.get('defendibilidad_promedio')}%   "
        f"Decision dominante: {exp.get('decision_dominante')}",
        "",
    ]
    if exp.get("alertas"):
        lineas.append("ALERTAS / CONTRADICCIONES:")
        lineas += [f"  - {a}" for a in exp["alertas"]]
        lineas.append("")
    lineas.append("GLOSAS:")
    for g in exp.get("glosas", []):
        d = g.get("decision", {})
        lineas.append(
            f"  [{g.get('codigo_corto')}] {str(g.get('servicio', ''))[:50]}  "
            f"${g.get('valor_objetado', 0):,}"
        )
        lineas.append(
            f"      defendibilidad {d.get('defendibilidad', 0)}%  ->  "
            f"{d.get('decision', '')}  ({d.get('motivo_decision', '')})"
        )
        for h in g.get("hechos_probados", []):
            ok = "OK " if h["probado"] else "NO "
            ev = "; ".join(h.get("evidencia", [])) or "; ".join(h.get("faltantes", []))
            lineas.append(f"        {ok}{h['hecho']}  [{ev}]")
    (carpeta / "resumen.txt").write_text("\n".join(lineas), encoding="utf-8")

    # log.txt: traza de las etapas aplicadas
    ev_n = sum(len(g.get("evidencias", [])) for g in exp.get("glosas", []))
    hp_n = sum(
        1 for g in exp.get("glosas", []) for h in g.get("hechos_probados", []) if h.get("probado")
    )
    (carpeta / "log.txt").write_text(
        "\n".join(
            [
                f"Pipeline aplicado a {exp['factura']}:",
                f"  1. Expediente: contrato {exp.get('contrato', {}).get('codigo')}, "
                f"{len(exp.get('glosas', []))} glosas, {len(exp.get('soportes', []))} soportes.",
                f"  2. Evidencia: {ev_n} localizadas.",
                f"  3. Hechos probados: {hp_n}; alertas: {len(exp.get('alertas', []))}.",
                f"  4. Decision dominante: {exp.get('decision_dominante')}.",
            ]
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Metricas + umbrales
# ---------------------------------------------------------------------------
def calcular_metricas(
    payload: dict, indice: dict, lote_facturas: set[str], segundos: float
) -> dict:
    exps = payload.get("expedientes", [])
    glosas = [g for e in exps for g in e.get("glosas", [])]

    docs_idx = indice.get("documentos", [])
    huerfanos = sum(1 for d in docs_idx if str(d.get("factura", "")) not in lote_facturas)
    docs_encontrados = sum(len(e.get("soportes", [])) for e in exps)
    fact_con_soporte = sum(1 for e in exps if e.get("soportes"))

    evid = [ev for g in glosas for ev in g.get("evidencias", [])]
    fuertes = sum(1 for ev in evid if ev.get("fuerza") == "fuerte")
    glosas_con_ev = sum(1 for g in glosas if g.get("evidencias"))

    hechos = [h for g in glosas for h in g.get("hechos_probados", [])]
    probados = sum(1 for h in hechos if h.get("probado"))
    glosas_con_hechos = sum(1 for g in glosas if g.get("hechos_probados"))
    contradicciones = sum(len(e.get("alertas", [])) for e in exps)

    decisiones = Counter(g.get("decision", {}).get("decision", "") for g in glosas)
    # guardarrail: levantamientos sin ningun hecho probado
    lev_sin_prueba = sum(
        1
        for g in glosas
        if g.get("decision", {}).get("decision") == "SOLICITAR_LEVANTAMIENTO"
        and not any(h.get("probado") for h in g.get("hechos_probados", []))
    )
    trazables = sum(1 for g in glosas if "documentos_requeridos" in g.get("decision", {}))

    n_exp = len(exps) or 1
    n_gl = len(glosas) or 1
    aceptacion = {
        "pct_facturas_con_soporte": round(100 * fact_con_soporte / n_exp, 1),
        "pct_glosas_con_evidencia": round(100 * glosas_con_ev / n_gl, 1),
        # % de glosas cuyos hechos fueron evaluados (0-100), no hechos/glosa.
        "pct_hechos_evaluados": round(100 * glosas_con_hechos / n_gl, 1),
        "decisiones_sin_soporte_probatorio": lev_sin_prueba,
        "pct_decisiones_trazables": round(100 * trazables / n_gl, 1),
    }
    cumple = {
        k: (
            aceptacion[k] >= UMBRALES[k]
            if k != "decisiones_sin_soporte_probatorio"
            else aceptacion[k] <= UMBRALES[k]
        )
        for k in UMBRALES
    }
    return {
        "tiempo_pipeline_seg": round(segundos, 2),
        "indice": {
            "facturas_piloto": len(exps),
            "documentos_encontrados": docs_encontrados,
            "facturas_con_soporte": fact_con_soporte,
            "documentos_huerfanos_en_indice": huerfanos,
        },
        "evidencia": {
            "localizadas": len(evid),
            "fuertes": fuertes,
            "debiles": len(evid) - fuertes,
            "glosas_sin_evidencia": n_gl - glosas_con_ev,
        },
        "hechos": {
            "probados": probados,
            "no_probados": len(hechos) - probados,
            "contradicciones": contradicciones,
        },
        "decision": dict(decisiones),
        "aceptacion": aceptacion,
        "umbrales": UMBRALES,
        "cumple_umbrales": cumple,
        "piloto_ok": all(cumple.values()),
    }


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------
def correr_piloto(
    excel: Path,
    indice_ruta: Path | None,
    cartera_ruta: Path | None,
    facturas: list[str] | None,
    auto: bool,
    conocido: str | None,
    salida_dir: Path,
) -> dict:
    t0 = time.perf_counter()
    glosas_all = cargar_glosas(excel, None)
    lote_facturas = {factura_corta(g.factura) for g in glosas_all}

    indice = {}
    if indice_ruta and indice_ruta.exists():
        indice = json.loads(indice_ruta.read_text(encoding="utf-8"))
    cartera = {}
    if cartera_ruta and cartera_ruta.exists():
        cartera = cartera_desde_xlsx(cartera_ruta, lote_facturas)

    # Todos los expedientes (para seleccionar) — barato, sin leer PDFs.
    todos = construir_expedientes(glosas_all, indice, cartera)
    if facturas:
        objetivo = {factura_corta(f) for f in facturas}
    elif auto:
        objetivo = set(seleccionar_casos(_as_dicts(todos), conocido))
    else:
        objetivo = lote_facturas  # todo (no recomendado para piloto)

    sel_glosas = [g for g in glosas_all if factura_corta(g.factura) in objetivo]
    expedientes = construir_expedientes(sel_glosas, indice, cartera)
    payload = {"expedientes": [_as_dict(e) for e in expedientes]}

    # Pipeline: evidencia -> hechos -> decision
    payload = enriquecer_expedientes(payload)
    payload = verificar_expedientes(payload)
    payload = decidir_expedientes(payload)

    salida_dir.mkdir(parents=True, exist_ok=True)
    for exp in payload["expedientes"]:
        escribir_expediente(exp, salida_dir)

    metricas = calcular_metricas(payload, indice, lote_facturas, time.perf_counter() - t0)
    (salida_dir / "METRICAS.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return metricas


def _as_dict(e):
    from dataclasses import asdict, is_dataclass

    return asdict(e) if is_dataclass(e) else e


def _as_dicts(lst):
    return [_as_dict(e) for e in lst]


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(description="Piloto extremo a extremo de la conciliacion.")
    ap.add_argument("--excel", type=Path, required=True, help="HUS.xlsx")
    ap.add_argument("--indice", type=Path, default=None, help="indice_soportes.json")
    ap.add_argument("--cartera", type=Path, default=None, help="Estado de cartera (xlsx)")
    ap.add_argument("--facturas", default=None, help="Lista separada por coma (casos explicitos)")
    ap.add_argument("--auto", action="store_true", help="Seleccionar 5 casos representativos")
    ap.add_argument("--conocido", default=None, help="Factura que ya conoces (caso 5)")
    ap.add_argument("--salida-dir", type=Path, required=True, help="Carpeta de salida del piloto")
    args = ap.parse_args(argv)

    facturas = [f.strip() for f in args.facturas.split(",")] if args.facturas else None
    metricas = correr_piloto(
        args.excel, args.indice, args.cartera, facturas, args.auto, args.conocido, args.salida_dir
    )
    logger.info("Piloto -> %s", args.salida_dir)
    logger.info(
        "  Facturas: %d | Docs: %d | Evidencias: %d (fuertes %d) | Hechos probados: %d/%d | Contradicciones: %d",
        metricas["indice"]["facturas_piloto"],
        metricas["indice"]["documentos_encontrados"],
        metricas["evidencia"]["localizadas"],
        metricas["evidencia"]["fuertes"],
        metricas["hechos"]["probados"],
        metricas["hechos"]["probados"] + metricas["hechos"]["no_probados"],
        metricas["hechos"]["contradicciones"],
    )
    logger.info("  Decisiones: %s", metricas["decision"])
    logger.info(
        "  UMBRALES cumplidos: %s  ->  piloto_ok=%s",
        metricas["cumple_umbrales"],
        metricas["piloto_ok"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
