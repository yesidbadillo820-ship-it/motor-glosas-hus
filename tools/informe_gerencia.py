"""informe_gerencia.py — Arma el informe de gestión para gerencia a partir de
la bitácora REGISTRO_BOTS.csv que llena el menú MOTOR_HUS.cmd. Usado por
INFORME_GERENCIA.cmd.

Lee la bitácora (fecha;hora;usuario;equipo;bot) y genera un HTML institucional
listo para imprimir o enviar: total de usos, bots más usados, usuarios y
equipos que los usan, y la actividad por semana. Sin trabajo manual: la
evidencia de la eficiencia del equipo se arma sola.

USO:
    py tools\\informe_gerencia.py REGISTRO_BOTS.csv
    py tools\\informe_gerencia.py REGISTRO_BOTS.csv --salida INFORME.html

No requiere componentes adicionales (solo Python).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path

_RE_FECHA = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")

DESCRIPCION_BOTS = {
    "UNIR_PDFS.cmd": "Union de PDF por carpeta",
    "PDF_A_CMD.cmd": "Copia .cmd de PDF",
    "EXCEL_A_CMD.cmd": "Copia .cmd de Excel",
    "COMPRIMIR_ZIP.cmd": "Compresion de .zip",
    "PARTIR_ZIP_30MB.cmd": "Particion de .zip en 30 MB",
    "TXT_A_EXCEL.cmd": "Conversion .txt a .csv/.xlsx",
    "EXCEL_A_CSV.cmd": "Conversion Excel a .csv",
    "REVISAR_XML.cmd": "Revision de XML (contrato)",
    "VERIFICAR_RADICACION.cmd": "Verificacion pre-radicacion",
    "CRUZAR_GLOSAS.cmd": "Cruce de glosas EPS vs XML",
    "SEMAFORO_GLOSAS.cmd": "Semaforo de vencimientos",
    "BUSCAR_FACTURA.cmd": "Recoleccion de soportes",
}


def parsear_fecha(texto: str) -> date | None:
    m = _RE_FECHA.search(texto or "")
    if not m:
        return None
    a, b, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # %DATE% suele ser dd/mm/aaaa en Colombia; si el segundo número no puede
    # ser mes, el equipo estaba en formato mm/dd y se voltea.
    dia, mes = (a, b) if b <= 12 else (b, a)
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def parsear_bitacora(ruta: Path) -> list[dict]:
    registros = []
    for ln in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        partes = [p.strip() for p in ln.split(";")]
        if len(partes) < 5 or partes[0].lower() == "fecha":
            continue
        registros.append(
            {
                "fecha": parsear_fecha(partes[0]),
                "hora": partes[1],
                "usuario": partes[2] or "(sin usuario)",
                "equipo": partes[3] or "(sin equipo)",
                "bot": partes[4] or "(sin bot)",
            }
        )
    return registros


def _semana(f: date) -> str:
    iso = f.isocalendar()
    return f"{iso[0]}-S{iso[1]:02d}"


def resumir(registros: list[dict]) -> dict:
    fechas = [r["fecha"] for r in registros if r["fecha"]]
    return {
        "total": len(registros),
        "por_bot": Counter(r["bot"] for r in registros),
        "por_usuario": Counter(r["usuario"] for r in registros),
        "por_equipo": Counter(r["equipo"] for r in registros),
        "por_semana": Counter(_semana(f) for f in fechas),
        "desde": min(fechas) if fechas else None,
        "hasta": max(fechas) if fechas else None,
    }


def _tabla(titulo: str, conteo: Counter, total: int, describe: bool = False) -> str:
    filas = []
    for nombre, n in conteo.most_common():
        pct = (n * 100 // total) if total else 0
        desc = DESCRIPCION_BOTS.get(nombre, "")
        extra = f"<td class='desc'>{escape(desc)}</td>" if describe else ""
        filas.append(
            f"<tr><td>{escape(str(nombre))}</td>{extra}"
            f"<td class='num'>{n}</td>"
            f"<td class='barra'><div style='width:{max(pct, 2)}%'></div><span>{pct}%</span></td></tr>"
        )
    cab_desc = "<th>Qué hace</th>" if describe else ""
    return (
        f"<section><h2>{escape(titulo)}</h2><table>"
        f"<thead><tr><th>Nombre</th>{cab_desc}<th>Usos</th><th>Participación</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table></section>"
    )


def escribir_html(res: dict, salida: Path, origen: Path) -> None:
    periodo = ""
    if res["desde"] and res["hasta"]:
        periodo = f"{res['desde'].strftime('%d/%m/%Y')} — {res['hasta'].strftime('%d/%m/%Y')}"
    semanas = sorted(res["por_semana"].items())
    max_sem = max((n for _, n in semanas), default=1)
    barras_sem = "".join(
        f"<div class='sem'><div class='caja'><div style='height:{max(n * 100 // max_sem, 4)}%'></div></div>"
        f"<span class='n'>{n}</span><span class='l'>{escape(s)}</span></div>"
        for s, n in semanas
    )
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Informe de gestión — bots Motor Glosas HUS</title>
<style>
 body{{margin:0;background:#EEF3F4;color:#17242A;font-family:"Segoe UI",Arial,sans-serif;line-height:1.55}}
 .hoja{{max-width:820px;margin:28px auto;background:#fff;border:1px solid #D7E0E3;border-radius:4px;padding:44px 52px}}
 h1,h2{{font-family:Georgia,serif}} h1{{font-size:1.5rem;margin:18px 0 4px}}
 .lh{{border-bottom:3px solid #0E6E77;padding-bottom:12px;display:flex;justify-content:space-between;align-items:baseline}}
 .lh b{{color:#0A4E55;font-size:.78rem;letter-spacing:.12em;text-transform:uppercase}}
 .lh span{{font-size:.72rem;color:#54666E}}
 .dek{{color:#54666E;margin:0 0 18px}}
 .kpis{{display:flex;gap:12px;margin:20px 0}}
 .kpi{{flex:1;border:1px solid #D7E0E3;border-radius:5px;padding:10px 14px}}
 .kpi b{{display:block;font-family:Georgia,serif;font-size:1.4rem;color:#0A4E55}}
 .kpi span{{font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;color:#54666E}}
 section{{margin-top:26px}} h2{{font-size:1.05rem;border-bottom:1px solid #D7E0E3;padding-bottom:6px}}
 table{{width:100%;border-collapse:collapse;font-size:.85rem}}
 th{{background:#0A4E55;color:#fff;text-align:left;padding:7px 10px;font-weight:600}}
 td{{padding:6px 10px;border-top:1px solid #E7EDEF}} td.num{{text-align:right;width:64px;font-weight:700}}
 td.desc{{color:#54666E}}
 td.barra{{width:200px}} td.barra div{{height:10px;background:#0E6E77;border-radius:5px;display:inline-block;vertical-align:middle;max-width:140px}}
 td.barra span{{font-size:.72rem;color:#54666E;margin-left:6px}}
 .semanas{{display:flex;gap:10px;align-items:flex-end;margin-top:10px;flex-wrap:wrap}}
 .sem{{text-align:center;font-size:.66rem;color:#54666E}}
 .sem .caja{{height:90px;width:34px;display:flex;align-items:flex-end;background:#E4F0F0;border-radius:3px}}
 .sem .caja div{{width:100%;background:#0E6E77;border-radius:3px}}
 .sem .n{{display:block;font-weight:700;color:#17242A}}
 .pie{{margin-top:30px;border-top:1px solid #D7E0E3;padding-top:10px;font-size:.72rem;color:#54666E}}
 @media print{{body{{background:#fff}} .hoja{{border:none;margin:0;padding:0 6mm}}}}
</style></head><body><div class="hoja">
<div class="lh"><div><b>E.S.E. Hospital Universitario de Santander</b><br>
<span>Auditoría de Cuentas Médicas · Automatización de procesos</span></div>
<span>Generado automáticamente desde la bitácora</span></div>
<h1>Informe de gestión — bots de auditoría</h1>
<p class="dek">Uso real de las herramientas del Motor Glosas HUS{f" · período {periodo}" if periodo else ""}.</p>
<div class="kpis">
 <div class="kpi"><b>{res["total"]}</b><span>Usos registrados</span></div>
 <div class="kpi"><b>{len(res["por_bot"])}</b><span>Bots utilizados</span></div>
 <div class="kpi"><b>{len(res["por_usuario"])}</b><span>Usuarios</span></div>
 <div class="kpi"><b>{len(res["por_equipo"])}</b><span>Equipos</span></div>
</div>
{_tabla("Uso por bot", res["por_bot"], res["total"], describe=True)}
{_tabla("Uso por persona", res["por_usuario"], res["total"])}
<section><h2>Actividad por semana</h2><div class="semanas">{barras_sem or "<p class='dek'>Sin fechas legibles aún.</p>"}</div></section>
<p class="pie">Fuente: {escape(str(origen.name))} (se llena solo cada vez que alguien usa un bot desde MOTOR_HUS.cmd).
Cada uso representa una tarea que antes era manual: unir/comprimir soportes, convertir FURIPS,
revisar XML de contratos, cruzar glosas o armar paquetes de respuesta.</p>
</div></body></html>"""
    salida.write_text(html, encoding="utf-8")


def procesar(bitacora: Path, salida: Path) -> int:
    registros = parsear_bitacora(bitacora)
    print("=" * 66)
    print("  INFORME GERENCIA — uso real de los bots (desde la bitacora)")
    print("=" * 66)
    if not registros:
        print("  La bitacora existe pero aun no tiene usos registrados.")
        print("  Usa los bots desde MOTOR_HUS.cmd y vuelve a generar el informe.")
        print("=" * 66)
        return 0
    res = resumir(registros)
    print(
        f"  Usos: {res['total']}   Bots: {len(res['por_bot'])}   Usuarios: {len(res['por_usuario'])}"
    )
    for bot, n in res["por_bot"].most_common(8):
        print(f"    {bot:28s} {n}")
    escribir_html(res, salida, bitacora)
    print("-" * 66)
    print(f"  Informe HTML: {salida}")
    print("  (abrelo con doble clic; se imprime o se manda por correo tal cual)")
    print("=" * 66)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Informe de gestion desde REGISTRO_BOTS.csv.")
    parser.add_argument(
        "bitacora", nargs="?", default="REGISTRO_BOTS.csv", help="Ruta del REGISTRO_BOTS.csv."
    )
    parser.add_argument("--salida", type=Path, help="Ruta del HTML de salida.")
    args = parser.parse_args(argv)

    bitacora = Path(args.bitacora).expanduser()
    if not bitacora.is_file():
        sys.stderr.write(
            f"ERROR: no existe la bitacora {bitacora}.\n"
            "       Usa los bots desde MOTOR_HUS.cmd (el menu la crea sola) y reintenta.\n"
        )
        return 2
    salida = args.salida or bitacora.with_name("INFORME_GERENCIA.html")
    return procesar(bitacora, salida)


if __name__ == "__main__":
    raise SystemExit(main())
