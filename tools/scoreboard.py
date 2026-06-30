#!/usr/bin/env python3
"""Tablero de calidad de dictámenes — con MEMORIA.

Puntúa los casos del benchmark (tests/benchmark/casos.json) con el scorer
determinista y:
  1. Imprime un tablero por caso (score 0–10, aprobado si >= 7).
  2. Anexa el resultado a tests/benchmark/historial.jsonl (memoria: cada
     corrida queda con su fecha y commit).
  3. Compara contra la corrida anterior y AVISA si algún caso REGRESÓ
     ("sábana sucia por sábana sucia": mejorar uno y empeorar otro).

Uso:
    python tools/scoreboard.py                 # puntúa la línea base (producción)
    python tools/scoreboard.py --caso medimas_davinci --archivo dictamen.txt
                                               # puntúa un dictamen nuevo para un caso

Regla del proyecto: la IA es BUENA solo si TODOS los casos sacan >= 7.
"""

from __future__ import annotations

import argparse
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
_HIST = os.path.join(_RAIZ, "tests", "benchmark", "historial.jsonl")


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


def _ultima_corrida() -> dict | None:
    if not os.path.exists(_HIST):
        return None
    ultima = None
    with open(_HIST, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                ultima = json.loads(linea)
    return ultima


def _emoji(score: float) -> str:
    if score >= UMBRAL_BUENO:
        return "✅"
    if score >= 5:
        return "🟡"
    return "🔴"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--caso", help="id de caso a puntuar con un dictamen externo")
    ap.add_argument("--archivo", help="archivo .txt con el dictamen a puntuar")
    ap.add_argument("--no-guardar", action="store_true", help="no anexar al historial")
    args = ap.parse_args()

    casos = {c["id"]: c for c in _cargar_casos()}

    # Modo: puntuar un dictamen externo para un caso puntual
    if args.caso and args.archivo:
        if args.caso not in casos:
            print(f"Caso desconocido: {args.caso}. Disponibles: {list(casos)}")
            return 2
        with open(args.archivo, encoding="utf-8") as f:
            dictamen = f.read()
        r = puntuar_dictamen(dictamen, casos[args.caso])
        _imprimir_caso(r)
        return 0 if r["aprobado"] else 1

    # Modo línea base: puntuar el dictamen de producción de cada caso
    prev = _ultima_corrida()
    prev_scores = {d["caso"]: d["score"] for d in (prev or {}).get("detalle", [])}

    resultados = []
    print("\n" + "═" * 64)
    print("  TABLERO DE CALIDAD DE DICTÁMENES  ·  BUENO = todos >= 7.0")
    print("═" * 64)
    for cid, caso in casos.items():
        r = puntuar_dictamen(caso["dictamen_produccion"], caso)
        resultados.append(r)
        delta = ""
        if cid in prev_scores:
            d = round(r["score"] - prev_scores[cid], 1)
            if d > 0:
                delta = f"  (▲ +{d} vs anterior)"
            elif d < 0:
                delta = f"  (▼ {d} vs anterior · ¡REGRESIÓN!)"
            else:
                delta = "  (= igual)"
        print(f"\n{_emoji(r['score'])}  {caso['titulo']}")
        print(f"     score: {r['score']}/10{delta}")
        for df in r["defectos"]:
            print(
                f"       − {df['gravedad']:8} −{df['peso']}  {df['criterio']}: {df['evidencia'][:70]}"
            )
        if not r["defectos"]:
            print("       (sin defectos detectados)")

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
    print("═" * 64 + "\n")

    # Memoria: anexar al historial
    if not args.no_guardar:
        registro = {
            "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "commit": _commit(),
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
        # Avisar regresiones
        regresiones = [
            r["caso"]
            for r in resultados
            if r["caso"] in prev_scores and r["score"] < prev_scores[r["caso"]]
        ]
        if regresiones:
            print(
                f"⚠️  REGRESIÓN detectada en: {regresiones} (un cambio mejoró algo y empeoró esto)"
            )

    return 0 if aprobados == len(resultados) else 1


def _imprimir_caso(r: dict) -> None:
    print(
        f"\n{_emoji(r['score'])}  caso {r['caso']}: {r['score']}/10  ({'APROBADO' if r['aprobado'] else 'NO APTO'})"
    )
    for df in r["defectos"]:
        print(f"   − {df['gravedad']:8} −{df['peso']}  {df['criterio']}: {df['evidencia'][:80]}")


if __name__ == "__main__":
    raise SystemExit(main())
