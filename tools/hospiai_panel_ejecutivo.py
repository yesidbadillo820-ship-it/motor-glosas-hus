#!/usr/bin/env python3
"""HOSPIAI — Panel Ejecutivo (Fase 2 · Sprint 2B).

El tablero para la coordinación y la gerencia: seis vistas alimentadas
EXCLUSIVAMENTE desde la API de HOSPIAI (`hospiai_api.Servicios`) — este módulo
no toca SQLite ni conoce el esquema. Arriba, las seis preguntas de aceptación
respondidas de frente, para contestarlas en menos de un minuto:

  1. ¿Cuánto dinero puedo radicar hoy?      4. ¿Qué funcionario necesita apoyo?
  2. ¿Qué me impide radicar el resto?       5. ¿Qué EPS presenta más problemas?
  3. ¿Cuál es el principal cuello de botella? 6. ¿Qué 3 acciones generan mayor impacto?

Vistas: 1 Estado General · 2 Riesgo Financiero · 3 Responsables · 4 EPS ·
5 Hallazgos · 6 Predicción y Recomendaciones.

Uso:
    py tools\\hospiai_panel_ejecutivo.py --salida "%USERPROFILE%\\Desktop\\panel_ejecutivo.html"
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hospiai_api import DB_DEFAULT, Servicios  # noqa: E402

_CSS = """
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
.wrap{max-width:1180px;margin:0 auto;padding:22px 20px 50px}
header{background:linear-gradient(135deg,#1e3a8a,#2563eb);border-radius:14px;padding:22px 26px;
color:#fff;margin-bottom:16px}
header h1{margin:0 0 4px;font-size:22px}header p{margin:0;opacity:.85;font-size:13px}
.preguntas{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:10px;margin:14px 0 22px}
.preg{background:#1e293b;border:1px solid #334155;border-left:4px solid #38bdf8;border-radius:10px;
padding:12px 14px;font-size:13px}
.preg b{display:block;color:#7dd3fc;margin-bottom:4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
nav{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 18px}
nav a{color:#93c5fd;text-decoration:none;font-size:13px;background:#1e293b;border:1px solid #334155;
padding:6px 12px;border-radius:999px}
h2{font-size:16px;margin:28px 0 10px;color:#f8fafc;border-bottom:1px solid #334155;padding-bottom:6px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.kpi{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 16px}
.kpi b{display:block;font-size:21px;font-variant-numeric:tabular-nums;color:#fff}
.kpi span{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8}
.kpi.ok b{color:#4ade80}.kpi.mal b{color:#f87171}
table{width:100%;border-collapse:collapse;background:#1e293b;border:1px solid #334155;
border-radius:10px;overflow:hidden;font-size:13px;margin-top:8px}
th{background:#0b2a6b;color:#e0e7ff;text-align:left;padding:8px 10px}
td{padding:7px 10px;border-top:1px solid #273449;font-variant-numeric:tabular-nums}
.num{text-align:right}.pillR{color:#f87171;font-weight:700}.pillV{color:#4ade80;font-weight:700}
.barra{background:#0f172a;border-radius:6px;height:10px;overflow:hidden}
.barra i{display:block;height:100%;background:linear-gradient(90deg,#22c55e,#4ade80)}
footer{margin-top:30px;color:#64748b;font-size:12px}
"""


def _p(v) -> str:
    return f"$ {v:,.0f}"


def _tabla(headers: list[str], filas: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    cuerpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{cuerpo}</tbody></table>"


def render(servicios: Servicios) -> str:
    inf = servicios.informe()
    caja = servicios.caja()
    tareas = servicios.tareas()
    r = inf["resumen"]
    rec = inf["recomendaciones"][:3]
    peor_resp = min(inf["responsables"], key=lambda x: x["pct_listas"], default=None)
    top_ent = inf["entidades"][0] if inf["entidades"] else None
    cuello = inf["prediccion"][0] if inf["prediccion"] else None

    preguntas = [
        (
            "1 · ¿Cuánto dinero puedo radicar hoy?",
            f"{_p(r['valor_listas'])} ({r['listas']:,} facturas listas)",
        ),
        (
            "2 · ¿Qué me impide radicar el resto?",
            " · ".join(
                f"{c['dictamen']}: {c['n']:,} ({_p(c['v'])})"
                for c in inf["riesgo_financiero"]["por_causa"][:3]
            )
            or "Nada pendiente",
        ),
        (
            "3 · ¿Principal cuello de botella?",
            f"{cuello['causa']}: {cuello['facturas']:,} facturas por {_p(cuello['valor'])}"
            if cuello
            else "Sin causas únicas medibles",
        ),
        (
            "4 · ¿Qué funcionario necesita apoyo?",
            f"{peor_resp['responsable']}: {peor_resp['pct_listas']:.0f}% listas, "
            f"{_p(peor_resp['v_detenido'])} detenido"
            if peor_resp
            else "Sin responsables en las rutas",
        ),
        (
            "5 · ¿Qué EPS presenta más problemas?",
            f"{top_ent['pagador_nombre']}: {top_ent['pendientes']:,} pendientes "
            f"(causa: {top_ent['causa_principal'] or '—'})"
            if top_ent
            else "Sin pendientes",
        ),
        (
            "6 · ¿3 acciones de mayor impacto esta semana?",
            " · ".join(f"P{x['prioridad']}: {x['accion']} ({_p(x['impacto'])})" for x in rec)
            or "Sin recomendaciones aún",
        ),
    ]

    partes = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>HOSPIAI — Panel Ejecutivo</title><style>{_CSS}</style></head><body>",
        "<div class='wrap'>",
        "<header><h1>HOSPIAI — Panel Ejecutivo de Cuentas Médicas</h1>",
        f"<p>ESE HUS · corrida #{inf['corrida'].get('id', '—')} · generado {inf['generado']}"
        " · alimentado 100% desde la API</p></header>",
        "<div class='preguntas'>",
        *(f"<div class='preg'><b>{html.escape(t)}</b>{html.escape(v)}</div>" for t, v in preguntas),
        "</div>",
        "<nav>"
        + "".join(
            f"<a href='#v{i}'>{n}</a>"
            for i, n in enumerate(
                [
                    "Estado General",
                    "Riesgo Financiero",
                    "Responsables",
                    "EPS",
                    "Hallazgos",
                    "Predicción",
                ],
                1,
            )
        )
        + "</nav>",
        # Vista 1 — Estado General
        "<h2 id='v1'>Vista 1 · Estado General</h2><div class='kpis'>",
        f"<div class='kpi'><b>{r['facturas']:,}</b><span>Facturas procesadas</span></div>",
        f"<div class='kpi'><b>{_p(r['valor_total'])}</b><span>Valor total</span></div>",
        f"<div class='kpi ok'><b>{r['listas']:,} · {r['listas_pct']:.1f}%</b><span>Listas para radicar</span></div>",
        f"<div class='kpi ok'><b>{_p(r['valor_listas'])}</b><span>Valor listo</span></div>",
        f"<div class='kpi mal'><b>{r['no_listas']:,} · {r['no_listas_pct']:.1f}%</b><span>No listas</span></div>",
        "</div>",
        # Vista 2 — Riesgo Financiero
        "<h2 id='v2'>Vista 2 · Riesgo Financiero</h2>",
        f"<div class='kpis'><div class='kpi mal'><b>{_p(inf['riesgo_financiero']['detenido'])}</b>"
        "<span>Dinero detenido</span></div></div>",
        _tabla(
            ["Por qué está detenido", "Facturas", "Valor"],
            [
                [html.escape(c["dictamen"]), f"<span class='num'>{c['n']:,}</span>", _p(c["v"])]
                for c in inf["riesgo_financiero"]["por_causa"]
            ],
        ),
        # Vista 3 — Responsables
        "<h2 id='v3'>Vista 3 · Responsables (ranking)</h2>",
        _tabla(
            [
                "Funcionario",
                "Facturas",
                "% Listas",
                "% Observadas",
                "Valor listo",
                "Valor detenido",
                "Avance",
            ],
            [
                [
                    html.escape(x["responsable"]),
                    f"{x['n']:,}",
                    f"<span class='pillV'>{x['pct_listas']:.0f}%</span>",
                    f"<span class='pillR'>{x['pct_observadas']:.0f}%</span>",
                    _p(x["v_listas"]),
                    _p(x["v_detenido"]),
                    f"<div class='barra'><i style='width:{x['pct_listas']:.0f}%'></i></div>",
                ]
                for x in sorted(inf["responsables"], key=lambda y: -y["pct_listas"])
            ],
        ),
        # Vista 4 — EPS
        "<h2 id='v4'>Vista 4 · EPS (pendientes y causa principal)</h2>",
        _tabla(
            ["Entidad", "Pendientes", "Valor detenido", "Causa principal"],
            [
                [
                    html.escape(x["pagador_nombre"] or "—"),
                    f"{x['pendientes']:,}",
                    _p(x["v_detenido"]),
                    html.escape(x["causa_principal"] or "—"),
                ]
                for x in inf["entidades"][:15]
            ],
        ),
        # Vista 5 — Hallazgos
        "<h2 id='v5'>Vista 5 · Hallazgos (valorizados, con su norma)</h2>",
        _tabla(
            ["Hallazgo", "Criticidad", "Facturas", "Valor económico", "Norma relacionada"],
            [
                [
                    html.escape(x["causa"]),
                    html.escape(x["criticidad"]),
                    f"{x['facturas']:,}",
                    _p(x["valor"]),
                    html.escape((x["norma"] or "—")[:70]),
                ]
                for x in inf["hallazgos"][:12]
            ],
        ),
        # Vista 6 — Predicción
        "<h2 id='v6'>Vista 6 · Predicción y Recomendaciones</h2>",
        _tabla(
            ["Si se corrige…", "Suben (facturas)", "Se libera"],
            [
                [html.escape(x["causa"]), f"{x['facturas']:,}", _p(x["valor"])]
                for x in inf["prediccion"][:8]
            ],
        ),
        _tabla(
            ["Prioridad", "Acción recomendada", "Facturas", "Impacto económico"],
            [
                [
                    f"P{x['prioridad']}",
                    html.escape(x["accion"]),
                    f"{x['facturas']:,}",
                    _p(x["impacto"]),
                ]
                for x in inf["recomendaciones"]
            ],
        ),
    ]
    if tareas:
        import json as _json

        filas = []
        for t in tareas[:15]:
            d = _json.loads(t["datos"] or "{}")
            filas.append(
                [
                    html.escape(t["codigo"]),
                    html.escape(d.get("responsable", "—")),
                    html.escape(d.get("accion", "")),
                    _p(d.get("valor", 0)),
                ]
            )
        partes += [
            "<h2>Tareas del día (AG013 — pendientes de asignar a personas)</h2>",
            _tabla(["Misión", "Responsable", "Acción", "Valor en juego"], filas),
        ]
    partes += [
        "<h2>Respuestas de caja (AG014)</h2>",
        _tabla(
            ["Pregunta", "Respuesta"],
            [[html.escape(c["pregunta"]), html.escape(c["respuesta"])] for c in caja],
        ),
        "<footer>HOSPIAI · ESE Hospital Universitario de Santander — panel generado desde la API"
        " (tools/hospiai_panel_ejecutivo.py); ninguna vista consulta la base directamente.</footer>",
        "</div></body></html>",
    ]
    return "".join(partes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Panel Ejecutivo HOSPIAI (consume solo la API).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    p.add_argument("--salida", type=Path, default=Path("panel_ejecutivo.html"))
    args = p.parse_args(argv)
    if not Path(args.db).is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador.")
        return 1
    contenido = render(Servicios(args.db))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(contenido, encoding="utf-8")
    print(f"Panel Ejecutivo: {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
