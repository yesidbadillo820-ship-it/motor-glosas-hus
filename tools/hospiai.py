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


def _norm_factura(fac: str) -> str:
    f = (fac or "").strip().upper()
    f = f[3:] if f.startswith("HUS") else f
    return f.lstrip("0") or "0"


def cmd_evidencia(db: Path, factura: str) -> int:
    """Motor de Evidencias: la cadena completa hallazgo → regla → norma →
    evidencia → confianza de UNA factura. Es la vista con la que un auditor
    defiende (o corrige) el dictamen."""
    norm = _norm_factura(factura)
    con = hospiai_db.abrir(db)
    try:
        exp = con.execute("SELECT * FROM expedientes WHERE factura_norm=?", (norm,)).fetchone()
        if exp is None:
            print(f"No hay expediente para '{factura}' (clave {norm}).")
            return 1
        evs = _q(
            con,
            "SELECT * FROM vw_evidencias WHERE factura_norm=? ORDER BY fecha DESC, id DESC",
            (norm,),
        )
        eventos = _q(
            con,
            "SELECT fecha, agente, tipo, resultado, version_reglas FROM eventos"
            " WHERE factura_norm=? ORDER BY fecha DESC LIMIT 10",
            (norm,),
        )
    finally:
        con.close()
    print("=" * 70)
    print(f"EXPEDIENTE {exp['factura']}  ·  {exp['pagador_nombre']}")
    print(
        f"  dictamen: {exp['dictamen']}   valor: $ {exp['valor_total']:,.0f}"
        f"   responsable: {exp['responsable'] or '—'}   lote: {exp['lote'] or '—'}"
    )
    print(f"  carpeta: {exp['carpeta']}")
    if not evs:
        print("  Sin hallazgos registrados: expediente limpio en la última auditoría. ✔")
    for h in evs:
        print("-" * 70)
        print(
            f"  HALLAZGO [{h['criticidad']}] {h['tipo']}{' · ' + h['codigo'] if h['codigo'] else ''}"
        )
        print(f"    detalle   : {h['detalle']}")
        if h["regla_id"]:
            print(f"    regla     : {h['regla_id']}")
            print(f"    norma     : {h['fuente_normativa'] or '—'}")
        if h["evidencia"]:
            print(f"    evidencia : {h['evidencia']}")
        print(
            f"    confianza : {h['confianza']:.2f}   fecha: {h['fecha']}   reglas v{h['version_reglas']}"
        )
    print("-" * 70)
    print("  Línea de tiempo:")
    for ev in eventos:
        print(f"    {ev['fecha']}  {ev['agente']}  {ev['tipo']} → {ev['resultado']}")
    print("=" * 70)
    return 0


def cmd_decision(db: Path, factura: str) -> int:
    """Decision Records: cada dictamen como objeto auditable con las versiones
    exactas de motor y reglas que lo produjeron."""
    norm = _norm_factura(factura)
    con = hospiai_db.abrir(db)
    try:
        filas = _q(
            con,
            "SELECT * FROM decisiones WHERE factura_norm=? ORDER BY id DESC LIMIT 10",
            (norm,),
        )
    finally:
        con.close()
    if not filas:
        print(f"Sin decisiones registradas para '{factura}' (clave {norm}).")
        return 1
    for d in filas:
        print("=" * 70)
        print(f"{d['codigo']}  ·  {d['fecha']}  ·  corrida #{d['corrida_id']}")
        print(f"  dictamen : {d['dictamen']}   confianza: {d['confianza']:.2f}")
        print(f"  motivo   : {d['motivo']}")
        if d["regla_id"]:
            print(f"  regla    : {d['regla_id']}")
        print(
            f"  agente   : {d['agente']}   motor v{d['version_motor']}   reglas v{d['version_reglas']}"
        )
    print("=" * 70)
    return 0


def cmd_catalogo(db: Path) -> int:
    """Catálogo institucional: la ficha operativa de cada pagador."""
    con = hospiai_db.abrir(db)
    try:
        rows = _q(
            con,
            "SELECT p.id, p.nombre, p.nit, p.regimen, p.canal, c.plazo_dias, c.periodicidad,"
            " (SELECT COUNT(*) FROM expedientes e WHERE e.pagador_id=p.id) n"
            " FROM pagadores p LEFT JOIN contratos c"
            "   ON c.pagador_id=p.id AND c.nombre='FICHA-CATALOGO'"
            " ORDER BY n DESC",
        )
    finally:
        con.close()
    print("=" * 96)
    print(
        f"{'ID':<20} {'NIT':<11} {'RÉGIMEN':<12} {'CANAL':<10} {'PLAZO':<6} {'PERIOD.':<10} {'EXP.':>6}"
    )
    for r in rows:
        print(
            f"{r['id'][:20]:<20} {r['nit'] or '—':<11} {(r['regimen'] or '—')[:12]:<12}"
            f" {(r['canal'] or '—')[:10]:<10} {r['plazo_dias'] or '—':<6}"
            f" {(r['periodicidad'] or '—')[:10]:<10} {r['n']:>6,}"
        )
    print("=" * 96)
    print("Plazo/periodicidad vacíos = ficha contractual pendiente de cargar por el área.")
    return 0


def cmd_grafo(db: Path, salida: Path, limite: int) -> int:
    """Exporta el grafo de conocimiento (nodos y relaciones) a JSON: pagador ←
    expediente → responsable/lote/regla-incumplida. Base para visualizadores y
    para el agente conversacional (Fase 1.5 entrega 2)."""
    con = hospiai_db.abrir(db)
    try:
        exps = _q(
            con,
            "SELECT factura_norm, factura, pagador_id, pagador_nombre, responsable, lote,"
            " dictamen, valor_total FROM expedientes LIMIT ?",
            (limite,),
        )
        ultima = con.execute("SELECT MAX(id) m FROM corridas").fetchone()["m"] or 0
        halls = _q(
            con,
            "SELECT factura_norm, regla_id FROM hallazgos WHERE corrida_id=? AND regla_id<>''",
            (ultima,),
        )
    finally:
        con.close()
    nodos: dict[str, dict] = {}
    aristas: list[dict] = []
    for e in exps:
        nid = f"exp:{e['factura_norm']}"
        nodos[nid] = {
            "id": nid,
            "tipo": "expediente",
            "label": e["factura"],
            "dictamen": e["dictamen"],
            "valor": e["valor_total"],
        }
        if e["pagador_id"]:
            pid = f"pag:{e['pagador_id']}"
            nodos.setdefault(pid, {"id": pid, "tipo": "pagador", "label": e["pagador_nombre"]})
            aristas.append({"de": nid, "a": pid, "tipo": "PAGA"})
        if e["responsable"]:
            rid = f"resp:{e['responsable']}"
            nodos.setdefault(rid, {"id": rid, "tipo": "responsable", "label": e["responsable"]})
            aristas.append({"de": rid, "a": nid, "tipo": "RADICA"})
        if e["lote"]:
            lid = f"lote:{e['lote']}"
            nodos.setdefault(lid, {"id": lid, "tipo": "lote", "label": e["lote"]})
            aristas.append({"de": nid, "a": lid, "tipo": "EN_LOTE"})
    en_grafo = {f"exp:{e['factura_norm']}" for e in exps}
    for h in halls:
        nid = f"exp:{h['factura_norm']}"
        if nid not in en_grafo:
            continue
        gid = f"regla:{h['regla_id']}"
        nodos.setdefault(gid, {"id": gid, "tipo": "regla", "label": h["regla_id"]})
        aristas.append({"de": nid, "a": gid, "tipo": "INCUMPLE"})
    import json as _json

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        _json.dumps(
            {"nodos": list(nodos.values()), "aristas": aristas}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    print(f"Grafo: {len(nodos)} nodo(s), {len(aristas)} relación(es) → {salida}")
    return 0


def cmd_agentes() -> int:
    """Registro Central de Agentes: identidad, versión, estado y capacidades."""
    from hospiai_agentes import registro_con_implementaciones

    reg = registro_con_implementaciones()
    print("=" * 92)
    print(f"{'ID':<7} {'NOMBRE':<24} {'DOM.':<6} {'VER.':<6} {'ESTADO':<14} CAPACIDADES")
    for a in reg.listar():
        print(
            f"{a['id']:<7} {a.get('nombre', ''):<24} {a.get('dominio', ''):<6}"
            f" {a.get('version', ''):<6} {a.get('estado', ''):<14}"
            f" {', '.join(a.get('capacidades') or [])}"
        )
    print("=" * 92)
    activos = len(reg.disponibles())
    print(
        f"{activos} activo(s) de {len(reg.listar())} registrados. "
        "El Supervisor consume este registro, nunca clases concretas."
    )
    return 0


def cmd_misiones(db: Path) -> int:
    """Estado de la cola de misiones (el bus de trabajo entre agentes)."""
    con = hospiai_db.abrir(db)
    try:
        estados = _q(con, "SELECT estado, COUNT(*) n FROM misiones GROUP BY estado")
        ultimas = _q(
            con,
            "SELECT codigo, tipo, expediente, prioridad, estado, agente_asignado, actualizada"
            " FROM misiones ORDER BY id DESC LIMIT 12",
        )
    finally:
        con.close()
    print("=" * 80)
    print("Cola de misiones:")
    if not estados:
        print("  (vacía — ningún agente ha publicado trabajo todavía)")
    for e in estados:
        print(f"  {e['estado']:<12} {e['n']:>5,}")
    if ultimas:
        print("  Últimas:")
        for m in ultimas:
            print(
                f"    {m['codigo']}  {m['tipo']:<20} {m['expediente'] or '—':<10}"
                f" [{m['prioridad']}] {m['estado']:<10} {m['agente_asignado'] or ''}"
            )
    print("=" * 80)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Consola del Expediente Digital HOSPIAI (solo lee).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT, help="Ruta de hospiai.db.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Crea la base vacía con el esquema.")
    sub.add_parser("resumen", help="Resumen del expediente en consola.")
    sub.add_parser("catalogo", help="Catálogo institucional: ficha por pagador.")
    sub.add_parser("agentes", help="Registro Central de Agentes (identidad/estado/capacidades).")
    sub.add_parser("misiones", help="Estado de la cola de misiones.")
    sp = sub.add_parser("panel", help="Panel HTML autocontenido leyendo de la base.")
    sp.add_argument("--salida", type=Path, default=Path("panel_hospiai.html"))
    sp.add_argument("--titulo", type=str, default="HOSPIAI — Panel de Cuentas Médicas · ESE HUS")
    se = sub.add_parser("evidencia", help="Cadena hallazgo→regla→norma→evidencia de una factura.")
    se.add_argument("factura", help="Número de factura (HUS528043 o 528043).")
    sd = sub.add_parser("decision", help="Decision Records de una factura (dictámenes auditables).")
    sd.add_argument("factura")
    sg = sub.add_parser("grafo", help="Exporta el grafo de conocimiento a JSON.")
    sg.add_argument("--salida", type=Path, default=Path("grafo_hospiai.json"))
    sg.add_argument("--limite", type=int, default=5000, help="Máx. expedientes (def. 5000).")
    args = p.parse_args(argv)

    if args.cmd == "init":
        hospiai_db.abrir(args.db).close()
        print(f"Expediente Digital creado/verificado: {args.db}")
        return 0
    if args.cmd == "agentes":  # lee el registro, no la base
        return cmd_agentes()
    if not Path(args.db).is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador o 'init'.")
        return 1
    if args.cmd == "resumen":
        return cmd_resumen(args.db)
    if args.cmd == "misiones":
        return cmd_misiones(args.db)
    if args.cmd == "catalogo":
        return cmd_catalogo(args.db)
    if args.cmd == "evidencia":
        return cmd_evidencia(args.db, args.factura)
    if args.cmd == "decision":
        return cmd_decision(args.db, args.factura)
    if args.cmd == "grafo":
        return cmd_grafo(args.db, args.salida, args.limite)
    return cmd_panel(args.db, args.salida, args.titulo)


if __name__ == "__main__":
    sys.exit(main())
