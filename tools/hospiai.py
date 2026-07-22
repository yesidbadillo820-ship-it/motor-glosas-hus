#!/usr/bin/env python3
"""HOSPIAI — consola del Expediente Digital (Fase 1).

Consulta la base `data/hospiai.db` que alimenta el radicador:

    py tools\\hospiai.py init                      # crea la base vacía
    py tools\\hospiai.py resumen                   # estado en consola
    py tools\\hospiai.py panel --salida panel.html # panel HTML autocontenido

Solo LEE la base y ESCRIBE el HTML del panel. No toca los shares.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402

DB_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "hospiai.db"


def _q(con, sql, args=()):
    return con.execute(sql, args).fetchall()


def _datos(con) -> dict:
    """Agregados del expediente para el resumen y el panel."""
    d: dict = {}
    d["total"] = _q(con, "SELECT COUNT(*) n, COALESCE(SUM(valor_total),0) v FROM expedientes")[0]
    d["dictamen"] = _q(
        con,
        "SELECT dictamen, COUNT(*) n, COALESCE(SUM(valor_total),0) v FROM expedientes"
        " GROUP BY dictamen ORDER BY n DESC",
    )
    d["responsables"] = _q(
        con,
        "SELECT responsable, COUNT(*) n,"
        " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
        " COALESCE(SUM(valor_total),0) v FROM expedientes WHERE responsable<>''"
        " GROUP BY responsable ORDER BY n DESC LIMIT 15",
    )
    d["pagadores"] = _q(
        con,
        "SELECT pagador_nombre, COUNT(*) n,"
        " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
        " COALESCE(SUM(valor_total),0) v FROM expedientes"
        " GROUP BY pagador_nombre ORDER BY n DESC LIMIT 15",
    )
    ultima = _q(con, "SELECT MAX(id) m FROM corridas")[0]["m"]
    d["hallazgos"] = _q(
        con,
        "SELECT codigo, tipo, criticidad, COUNT(*) n FROM hallazgos WHERE corrida_id=?"
        " GROUP BY codigo, tipo, criticidad ORDER BY n DESC LIMIT 12",
        (ultima or 0,),
    )
    d["corridas"] = _q(
        con,
        "SELECT id, iniciada, terminada, total_expedientes, total_hallazgos, version_reglas,"
        " version_motor FROM corridas ORDER BY id DESC LIMIT 8",
    )
    return d


def cmd_resumen(db: Path) -> int:
    con = hospiai_db.abrir(db)
    try:
        d = _datos(con)
    finally:
        con.close()
    t = d["total"]
    print("=" * 64)
    print(f"HOSPIAI · Expediente Digital — {db}")
    print(f"  Expedientes: {t['n']:,}   Valor: $ {t['v']:,.0f}")
    print("  Por dictamen:")
    for r in d["dictamen"]:
        print(f"    {r['dictamen'] or '—':<24} {r['n']:>6,}  $ {r['v']:,.0f}")
    if d["responsables"]:
        print("  Por responsable:")
        for r in d["responsables"]:
            print(
                f"    {r['responsable'][:24]:<24} {r['n']:>6,} | {r['listas']:>5,} listas"
                f" | $ {r['v']:,.0f}"
            )
    print("  Corridas recientes:")
    for c in d["corridas"]:
        print(
            f"    #{c['id']:<4} {c['iniciada']}  {c['total_expedientes']:>6,} exp."
            f"  {c['total_hallazgos']:>6,} hallazgos  reglas v{c['version_reglas']}"
        )
    print("=" * 64)
    return 0


_CSS = """
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;margin:0;background:#f1f5f9;color:#0f172a}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 48px}
header{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;border-radius:12px;
padding:22px 26px;margin-bottom:18px}
header h1{margin:0 0 4px;font-size:22px}header p{margin:0;opacity:.85;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
.kpi{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.kpi span{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#64748b}
h2{font-size:15px;margin:22px 0 8px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0;
border-radius:10px;overflow:hidden;font-size:13px}
th{background:#1e3a8a;color:#fff;text-align:left;padding:8px 10px;font-weight:600}
td{padding:7px 10px;border-top:1px solid #eef2f7;font-variant-numeric:tabular-nums}
tr:nth-child(even) td{background:#f8fafc}
.num{text-align:right}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.ok{background:#dcfce7;color:#166534}.warn{background:#fef3c7;color:#92400e}
.bad{background:#fee2e2;color:#991b1b}.neu{background:#e2e8f0;color:#334155}
footer{margin-top:26px;color:#64748b;font-size:12px}
"""

_PILL = {
    "LISTA": "ok",
    "REVISAR_TIPIFICACION": "warn",
    "PARTICULAR": "neu",
}


def _tabla(headers: list[str], filas: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for f in filas:
        tds = "".join(
            f'<td class="num">{c}</td>'
            if isinstance(c, str) and c.startswith("$")
            else f"<td>{c}</td>"
            for c in f
        )
        trs.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def cmd_panel(db: Path, salida: Path, titulo: str) -> int:
    con = hospiai_db.abrir(db)
    try:
        d = _datos(con)
    finally:
        con.close()
    t = d["total"]
    listas = next((r["n"] for r in d["dictamen"] if r["dictamen"] == "LISTA"), 0)
    pct = 100 * listas / t["n"] if t["n"] else 0

    dictamen_rows = []
    for r in d["dictamen"]:
        clase = _PILL.get(r["dictamen"], "bad")
        dictamen_rows.append(
            [
                f'<span class="pill {clase}">{html.escape(r["dictamen"] or "—")}</span>',
                f"{r['n']:,}",
                f"$ {r['v']:,.0f}",
            ]
        )
    resp_rows = [
        [html.escape(r["responsable"]), f"{r['n']:,}", f"{r['listas']:,}", f"$ {r['v']:,.0f}"]
        for r in d["responsables"]
    ]
    pag_rows = [
        [
            html.escape(r["pagador_nombre"] or "—"),
            f"{r['n']:,}",
            f"{r['listas']:,}",
            f"$ {r['v']:,.0f}",
        ]
        for r in d["pagadores"]
    ]
    hall_rows = [
        [
            html.escape(r["codigo"] or r["tipo"]),
            html.escape(r["criticidad"]),
            f"{r['n']:,}",
        ]
        for r in d["hallazgos"]
    ]
    corr_rows = [
        [
            f"#{c['id']}",
            html.escape(c["iniciada"] or ""),
            f"{c['total_expedientes']:,}",
            f"{c['total_hallazgos']:,}",
            html.escape(f"v{c['version_reglas']} · motor {c['version_motor']}"),
        ]
        for c in d["corridas"]
    ]

    partes = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{html.escape(titulo)}</title><style>{_CSS}</style></head><body>",
        "<div class='wrap'>",
        f"<header><h1>{html.escape(titulo)}</h1>",
        "<p>Expediente Digital · HOSPIAI Fase 1 — solo lectura sobre los shares</p></header>",
        "<div class='kpis'>",
        f"<div class='kpi'><b>{t['n']:,}</b><span>Expedientes</span></div>",
        f"<div class='kpi'><b>{listas:,} ({pct:.0f}%)</b><span>Listas para radicar</span></div>",
        f"<div class='kpi'><b>$ {t['v']:,.0f}</b><span>Valor auditado</span></div>",
        f"<div class='kpi'><b>{len(d['corridas'])}</b><span>Corridas recientes</span></div>",
        "</div>",
        "<h2>Por dictamen</h2>",
        _tabla(["Dictamen", "Facturas", "Valor"], dictamen_rows),
    ]
    if resp_rows:
        partes += [
            "<h2>Por responsable (Dominio 5 — Operacional)</h2>",
            _tabla(["Responsable", "Facturas", "Listas", "Valor"], resp_rows),
        ]
    partes += [
        "<h2>Por pagador</h2>",
        _tabla(["Pagador", "Facturas", "Listas", "Valor"], pag_rows),
        "<h2>Hallazgos de la última corrida</h2>",
        _tabla(["Código / tipo", "Criticidad", "Cantidad"], hall_rows),
        "<h2>Corridas</h2>",
        _tabla(["#", "Iniciada", "Expedientes", "Hallazgos", "Versión"], corr_rows),
        "<footer>ESE Hospital Universitario de Santander · Cuentas Médicas y Cartera — "
        "generado por tools/hospiai.py</footer>",
        "</div></body></html>",
    ]
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("".join(partes), encoding="utf-8")
    print(f"Panel HOSPIAI: {salida}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Consola del Expediente Digital HOSPIAI (solo lee).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT, help="Ruta de hospiai.db.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Crea la base vacía con el esquema.")
    sub.add_parser("resumen", help="Resumen del expediente en consola.")
    sp = sub.add_parser("panel", help="Panel HTML autocontenido leyendo de la base.")
    sp.add_argument("--salida", type=Path, default=Path("panel_hospiai.html"))
    sp.add_argument("--titulo", type=str, default="HOSPIAI — Panel de Cuentas Médicas · ESE HUS")
    args = p.parse_args(argv)

    if args.cmd == "init":
        hospiai_db.abrir(args.db).close()
        print(f"Expediente Digital creado/verificado: {args.db}")
        return 0
    if not Path(args.db).is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador o 'init'.")
        return 1
    if args.cmd == "resumen":
        return cmd_resumen(args.db)
    return cmd_panel(args.db, args.salida, args.titulo)


if __name__ == "__main__":
    sys.exit(main())
