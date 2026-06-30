#!/usr/bin/env python3
"""Benchmark EN VIVO — corre las 4 glosas por el MOTOR REAL y las puntúa.

A diferencia de tools/scoreboard.py (que puntúa el texto guardado), este
script LLAMA al LLM: genera el dictamen de cada caso con GlosaService.analizar
y luego lo puntúa con el scorer determinista. Así se mide el efecto REAL de
los cambios de prompt/generación (Ronda 21/22) en el número 0–10.

Costo: ~4 llamadas al LLM por corrida (una por caso; más si hay multi-código
o reintentos). Requiere las API keys en el entorno (GROQ_API_KEY y/o
ANTHROPIC_API_KEY) — por eso se corre en la VM, no en CI.

Uso (en la VM, dentro del contenedor o con el venv del motor):
    python tools/scoreboard_live.py                  # corre los 4, mide y guarda
    python tools/scoreboard_live.py --primary anthropic   # forzar proveedor

Resultado: tablero 0–10 por caso + promedio + veredicto, y guarda los
dictámenes generados en tests/benchmark/salidas/<fecha>/ para que puedas
leerlos y compararlos contra docs/EJEMPLOS_DICTAMENES_ESPERADOS.md.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import subprocess
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
sys.path.insert(0, _RAIZ)

from tests.benchmark.scorer import UMBRAL_BUENO, puntuar_dictamen  # noqa: E402

_CASOS = os.path.join(_RAIZ, "tests", "benchmark", "casos.json")
_HIST = os.path.join(_RAIZ, "tests", "benchmark", "historial_live.jsonl")
_SALIDAS = os.path.join(_RAIZ, "tests", "benchmark", "salidas")


def _cargar_casos() -> list[dict]:
    with open(_CASOS, encoding="utf-8") as f:
        return json.load(f)["casos"]


def _commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=_RAIZ)
            .decode()
            .strip()
        )
    except Exception:
        return "desconocido"


def _construir_service(primary: str | None):
    """Mismo factory que el endpoint /analizar (lee keys del entorno)."""
    from app.core.config import get_settings
    from app.services.glosa_service import GlosaService

    cfg = get_settings()
    return GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=primary or cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
        groq_model_fallback_1=cfg.groq_model_fallback_1,
        groq_model_fallback_2=cfg.groq_model_fallback_2,
        groq_model_fallback_3=getattr(cfg, "groq_model_fallback_3", "llama-3.3-70b-versatile"),
        gemini_api_key=cfg.gemini_api_key,
        gemini_model=cfg.gemini_model,
    )


def _emoji(score: float) -> str:
    if score >= UMBRAL_BUENO:
        return "✅"
    if score >= 5:
        return "🟡"
    return "🔴"


async def _generar(service, caso: dict) -> str:
    from app.models.schemas import GlosaInput

    data = GlosaInput(
        eps=caso.get("eps_dropdown", "OTRA / SIN DEFINIR"),
        etapa="RESPUESTA A GLOSA",
        tabla_excel=caso["glosa"],
        valor_aceptado="0",
    )
    resultado = await service.analizar(data)
    return resultado.dictamen or ""


async def _run(primary: str | None) -> int:
    casos = _cargar_casos()
    service = _construir_service(primary)

    sello = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    dir_salida = os.path.join(_SALIDAS, sello)
    os.makedirs(dir_salida, exist_ok=True)

    print("\n" + "═" * 64)
    print(f"  BENCHMARK EN VIVO  ·  motor real  ·  commit {_commit()}")
    print("  BUENO = todos >= 7.0")
    print("═" * 64)

    resultados = []
    total = len(casos)
    for i, caso in enumerate(casos, 1):
        print(
            f"\n⏳ Generando {i}/{total}: {caso['titulo']} "
            "(llama a Claude — puede tardar 1-2 min, NO presiones Ctrl+C)...",
            flush=True,
        )
        try:
            # Timeout amplio por caso para que uno lento no cuelgue todo,
            # pero sin cortar generaciones legítimas (con reintentos).
            dictamen = await asyncio.wait_for(_generar(service, caso), timeout=420)
        except asyncio.TimeoutError:
            print(f"🔴  {caso['titulo']}: TIMEOUT (>7 min) — se omite", flush=True)
            resultados.append({"caso": caso["id"], "score": 0.0, "aprobado": False, "defectos": []})
            continue
        except Exception as e:
            print(f"🔴  {caso['titulo']}: ERROR generando — {e}", flush=True)
            resultados.append({"caso": caso["id"], "score": 0.0, "aprobado": False, "defectos": []})
            continue
        # guardar el dictamen para inspección humana
        with open(os.path.join(dir_salida, f"{caso['id']}.txt"), "w", encoding="utf-8") as f:
            f.write(dictamen)
        r = puntuar_dictamen(dictamen, caso)
        resultados.append(r)
        print(f"{_emoji(r['score'])}  {caso['titulo']} → score: {r['score']}/10", flush=True)
        for df in r["defectos"]:
            print(
                f"       − {df['gravedad']:8} −{df['peso']}  {df['criterio']}: {df['evidencia'][:60]}",
                flush=True,
            )
        if not r["defectos"]:
            print("       (sin defectos detectados) ✨", flush=True)

    aprobados = sum(1 for r in resultados if r["aprobado"])
    promedio = round(sum(r["score"] for r in resultados) / len(resultados), 2)
    print("\n" + "═" * 64)
    print(f"  RESUMEN: {aprobados}/{len(resultados)} casos >= 7  ·  promedio {promedio}/10")
    veredicto = (
        "✅ IA BUENA"
        if aprobados == len(resultados)
        else "🔴 IA NO APTA (falta llegar a 7 en todos)"
    )
    print(f"  VEREDICTO: {veredicto}")
    print(f"  Dictámenes guardados en: {dir_salida}")
    print("═" * 64 + "\n")

    registro = {
        "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commit": _commit(),
        "modo": "live",
        "promedio": promedio,
        "aprobados": aprobados,
        "total": len(resultados),
        "detalle": [
            {
                "caso": r["caso"],
                "score": r["score"],
                "defectos": [d["criterio"] for d in r["defectos"]],
            }
            for r in resultados
        ],
    }
    with open(_HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return 0 if aprobados == len(resultados) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", choices=["groq", "anthropic"], help="forzar proveedor primario")
    args = ap.parse_args()
    return asyncio.run(_run(args.primary))


if __name__ == "__main__":
    raise SystemExit(main())
