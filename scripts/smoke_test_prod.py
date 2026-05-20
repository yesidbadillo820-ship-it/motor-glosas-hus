#!/usr/bin/env python3
"""Smoke test producción: hits read-only a endpoints clave.

Verifica que cada endpoint responda con código esperado (200, 401, 404 según
sea público/privado). No hace mutaciones, no requiere auth.

Uso:
    python scripts/smoke_test_prod.py [--base-url https://motor-glosas-hus.fly.dev]

Devuelve exit code 0 si TODOS los checks pasan, 1 si alguno falla.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Endpoints a testear. Cada tupla:
#   (path, status_codes_aceptables, etiqueta)
ENDPOINTS = [
    # Frontend / health
    ("/health", {200}, "Health check"),
    ("/", {200}, "Landing page"),
    ("/static/index.html", {200}, "Index estático"),
    ("/static/importar-masiva.html", {200}, "Página importar masiva"),
    ("/static/importar-recepcion.html", {200}, "Página importar recepción"),
    # Endpoints públicos (sin auth)
    ("/glosas/importar-masiva/plantilla.csv", {200}, "Plantilla CSV pública"),
    ("/api/version", {200, 404}, "Version endpoint (opcional)"),
    # Endpoints protegidos: deben devolver 401 sin token
    ("/glosas/historial", {401, 403}, "Glosas historial (debe pedir auth)"),
    ("/sistema/diagnostico-ia", {401, 403, 404}, "Diagnóstico IA (debe pedir auth)"),
    ("/plantillas-gold/", {401, 403}, "Plantillas gold listar (debe pedir auth)"),
    ("/admin/health", {401, 403, 404}, "Admin health (debe pedir auth)"),
    # SSE/streaming (debe responder rápido aunque no haya cola)
    ("/eventos/analizar/trace-no-existe", {200, 404, 401, 403}, "SSE analizar (no debe colgar)"),
]


def check(base_url: str, path: str, expected: set[int], etiqueta: str, timeout: int = 10) -> dict:
    url = base_url.rstrip("/") + path
    t0 = time.time()
    try:
        req = Request(url, headers={"User-Agent": "smoke-test-prod/1.0"})
        with urlopen(req, timeout=timeout) as r:
            status = r.status
            body_len = len(r.read())
    except HTTPError as e:
        status = e.code
        body_len = 0
    except URLError as e:
        return {
            "path": path,
            "etiqueta": etiqueta,
            "status": None,
            "esperado": list(expected),
            "ok": False,
            "ms": round((time.time() - t0) * 1000),
            "error": f"URLError: {e.reason}",
        }
    except Exception as e:
        return {
            "path": path,
            "etiqueta": etiqueta,
            "status": None,
            "esperado": list(expected),
            "ok": False,
            "ms": round((time.time() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
        }

    return {
        "path": path,
        "etiqueta": etiqueta,
        "status": status,
        "esperado": list(expected),
        "ok": status in expected,
        "ms": round((time.time() - t0) * 1000),
        "body_len": body_len,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://motor-glosas-hus.fly.dev")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    args = parser.parse_args()

    resultados = []
    print(f"[SMOKE] base_url = {args.base_url}", file=sys.stderr)
    for path, expected, etiqueta in ENDPOINTS:
        r = check(args.base_url, path, expected, etiqueta)
        resultados.append(r)
        if not args.json:
            icono = "OK " if r["ok"] else "FAIL"
            err = f" ERR={r.get('error', '')}" if not r["ok"] else ""
            print(f"[{icono}] {r['status']} ({r['ms']}ms) {r['etiqueta']:40s} {r['path']}{err}")

    pasados = sum(1 for r in resultados if r["ok"])
    total = len(resultados)
    if args.json:
        print(json.dumps({"resultados": resultados, "pasados": pasados, "total": total}, indent=2))
    else:
        print(f"\n[SMOKE] {pasados}/{total} checks pasados", file=sys.stderr)

    sys.exit(0 if pasados == total else 1)


if __name__ == "__main__":
    main()
