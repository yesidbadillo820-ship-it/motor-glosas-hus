"""verificar_glosas_coosalud.py — ¿Qué facturas siguen pendientes en el portal?

En vez de buscar factura por factura (≈2 min cada una entre los dos timeouts),
lee UNA sola vez la grilla completa de la Bolsa de Respuestas y la de En Pausa
(paginando o con 'Mostrar: Todos') y cruza contra tu lista. 140 facturas se
verifican en ~3 minutos.

Veredictos:
  - PENDIENTE_EN_BOLSA : está en la Bolsa, sin abrir (el bot la puede responder)
  - ABIERTA_EN_PAUSA   : se abrió y no se terminó (grupos a medias / soportes)
  - CERRADA            : no aparece en ninguna grilla (ya respondida y terminada)

USO:
    REM con la lista en un TXT (una factura por línea):
    py tools\\verificar_glosas_coosalud.py ^
        --lista "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\lote_140.txt" ^
        --salida "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\verificacion_coosalud.csv"

    REM o directo contra la hoja BASE del Excel (sin armar TXT):
    py tools\\verificar_glosas_coosalud.py ^
        --excel "D:\\USUARIO CARTERA\\Downloads\\CONSOLIDADO COOSALUD DIA 28.xlsx" ^
        --salida "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\verificacion_coosalud.csv"

Credenciales: las mismas variables de entorno del responder
(COOSALUD_USER / COOSALUD_PASSWORD).
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

import responder_glosas_coosalud as core

logger = logging.getLogger("verificar_coosalud")

JS_SCRAPE_FACTURAS = """() => {
    const out = [];
    for (const td of document.querySelectorAll('tbody td')) {
        const t = (td.innerText || '').trim();
        if (/^HUS\\d{5,9}$/.test(t)) out.push(t);
    }
    return out;
}"""

# Busca el botón/lin 'Siguiente' visible; si está habilitado lo clickea y
# devuelve 'sigue', si está deshabilitado devuelve 'fin'.
JS_SIGUIENTE = """() => {
    const cands = [...document.querySelectorAll('a, button')]
        .filter(e => /^Siguiente$/i.test((e.innerText || '').trim()))
        .filter(e => e.offsetParent !== null);
    if (!cands.length) return 'fin';
    const el = cands[cands.length - 1];
    const li = el.closest('li');
    const off = el.classList.contains('disabled')
        || (li && li.classList.contains('disabled'))
        || el.hasAttribute('disabled');
    if (off) return 'fin';
    el.click();
    return 'sigue';
}"""

JS_TOTAL_ENTRADAS = """() => {
    const m = (document.body.innerText || '').match(/de\\s+([\\d.,]+)\\s+(?:total\\s+)?Entradas/i);
    return m ? m[1] : '';
}"""


def _poner_mostrar_todos(page) -> bool:
    """Intenta poner 'Mostrar: Todos' en la grilla actual."""
    try:
        selects = page.locator("select").all()
    except Exception:
        return False
    for s in selects:
        try:
            if not s.is_visible():
                continue
            opciones = s.locator("option").all_inner_texts()
            etiqueta = next((o for o in opciones if "Todos" in o), None)
            if etiqueta:
                s.select_option(label=etiqueta)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    return False


def _leer_facturas_grilla(page, nombre: str) -> set[str]:
    """Devuelve TODOS los números HUS visibles en la grilla actual, paginando
    con 'Siguiente' si 'Mostrar: Todos' no está disponible."""
    core._esperar_caja_buscar(page, nombre)
    if _poner_mostrar_todos(page):
        logger.info(f"  {nombre}: 'Mostrar: Todos' aplicado")
    total_txt = ""
    try:
        total_txt = page.evaluate(JS_TOTAL_ENTRADAS)
    except Exception:
        pass
    if total_txt:
        logger.info(f"  {nombre}: el portal reporta {total_txt} entradas")

    visto: set[str] = set()
    for pagina in range(1, 301):
        # Estabilizar la página actual (el datatable redibuja async).
        filas: list[str] = []
        previo = -1
        for _ in range(40):
            try:
                filas = page.evaluate(JS_SCRAPE_FACTURAS)
            except Exception:
                filas = []
            if len(filas) == previo:
                break
            previo = len(filas)
            page.wait_for_timeout(600)
        visto.update(filas)
        try:
            estado = page.evaluate(JS_SIGUIENTE)
        except Exception:
            break
        if estado != "sigue":
            break
        page.wait_for_timeout(900)
    logger.info(f"  {nombre}: {len(visto)} facturas leídas de la grilla")
    return visto


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    fuente = parser.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--lista", type=Path, help="TXT con una factura por línea.")
    fuente.add_argument("--facturas", type=str, help="Lista separada por coma.")
    fuente.add_argument("--excel", type=Path, help="Excel consolidado: toma las facturas de la hoja.")
    parser.add_argument("--hoja", type=str, default="BASE", help="Hoja del Excel (default BASE).")
    parser.add_argument("--salida", type=Path, default=Path("verificacion_coosalud.csv"))
    parser.add_argument("--con-cabeza", action="store_true", help="Mostrar el browser.")
    args = parser.parse_args()
    core.setup_logging(None)

    core._exigir_playwright()
    user, password = core.cargar_credenciales()

    # ── Lista objetivo ──
    if args.lista:
        if not args.lista.is_file():
            logger.error(f"No existe: {args.lista}")
            return 1
        texto = args.lista.read_text(encoding="utf-8-sig", errors="replace")
        objetivo = [x.strip().upper() for x in texto.replace(",", "\n").splitlines() if x.strip()]
    elif args.facturas:
        objetivo = [x.strip().upper() for x in args.facturas.split(",") if x.strip()]
    else:
        datos = core.leer_excel(args.excel, args.hoja)
        objetivo = sorted(datos.keys())
    # dedup preservando orden
    vistos_l: set[str] = set()
    objetivo = [f for f in objetivo if not (f in vistos_l or vistos_l.add(f))]
    logger.info(f"Facturas a verificar: {len(objetivo)}")

    # ── Leer las dos grillas del portal ──
    with core.sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.con_cabeza)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_navigation_timeout(120000)
        page.set_default_timeout(30000)
        page.on("dialog", lambda d: d.accept())
        logger.info("Login al portal COOSALUD...")
        core.login(page, user, password)
        logger.info("Login OK")

        core.ir_a_bolsa(page)
        en_bolsa = _leer_facturas_grilla(page, "Bolsa")

        core.ir_a_en_pausa(page)
        en_pausa = _leer_facturas_grilla(page, "En Pausa")

        try:
            browser.close()
        except Exception:
            pass

    # ── Cruce ──
    pend_bolsa = [f for f in objetivo if f in en_bolsa]
    abiertas_pausa = [f for f in objetivo if f in en_pausa and f not in en_bolsa]
    cerradas = [f for f in objetivo if f not in en_bolsa and f not in en_pausa]
    fuera_lista_bolsa = sorted(en_bolsa - set(objetivo))
    fuera_lista_pausa = sorted(en_pausa - set(objetivo))

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["factura", "estado"])
        for fac in objetivo:
            if fac in en_bolsa:
                w.writerow([fac, "PENDIENTE_EN_BOLSA"])
            elif fac in en_pausa:
                w.writerow([fac, "ABIERTA_EN_PAUSA"])
            else:
                w.writerow([fac, "CERRADA"])
        for fac in fuera_lista_bolsa:
            w.writerow([fac, "EN_BOLSA_FUERA_DE_LISTA"])
        for fac in fuera_lista_pausa:
            w.writerow([fac, "EN_PAUSA_FUERA_DE_LISTA"])

    logger.info("")
    logger.info(f"════ RESULTADO ({len(objetivo)} facturas) ════")
    logger.info(f"  ✅ CERRADAS:            {len(cerradas)}")
    logger.info(f"  🟡 PENDIENTES EN BOLSA: {len(pend_bolsa)}")
    for fac in pend_bolsa:
        logger.info(f"       {fac}")
    logger.info(f"  🟠 ABIERTAS EN PAUSA:   {len(abiertas_pausa)}")
    for fac in abiertas_pausa:
        logger.info(f"       {fac}")
    if fuera_lista_bolsa or fuera_lista_pausa:
        logger.info(f"  ℹ Además, fuera de tu lista: {len(fuera_lista_bolsa)} en Bolsa, "
                    f"{len(fuera_lista_pausa)} En Pausa (ver CSV).")
    logger.info(f"\nCSV: {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
