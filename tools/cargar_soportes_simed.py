"""cargar_soportes_simed.py — Carga masiva de soportes al portal SIMED (auditool25).

Para cada carpeta `<destino>/<GESTOR>/<NOTA>/` con los 3 archivos finales
(NC_<NE>_HUS<n>.pdf, XML_<NE>_HUS<n>.xml, CUV_<NE>_HUS<n>.json):

1. Hace login al portal (una sola vez, mantiene sesión).
2. Por cada factura:
   - Va a "Facturas Conciliadas" y filtra por # Factura.
   - Abre el editor de la fila.
   - Pone la Nota Crédito Conciliación.
   - Abre "Soportes NC" → sube los 3 archivos.
   - Click "Actualizar Respuestas" → "Confirmar".
   - Verifica el mensaje "Registro completado".
3. Genera un reporte CSV con el estado de cada factura.

CREDENCIALES (en variables de entorno, NO en el código):

    setx SIMED_USER 900006037
    setx SIMED_PASSWORD Glosashus2025
    # cerrá y reabrí PowerShell para que tome las variables

USO:

    # Test inicial con UNA factura
    py cargar_soportes_simed.py ^
        --destino "C:\\notas-extraidas-v2\\documentos" ^
        --solo 309246

    # Con browser visible para debug
    py cargar_soportes_simed.py --destino ... --solo 309246 --con-cabeza

    # Cuando funcione la prueba, todas las facturas
    py cargar_soportes_simed.py ^
        --destino "C:\\notas-extraidas-v2\\documentos" ^
        --todas ^
        --reporte "C:\\notas-extraidas-v2\\05_reporte_carga_simed.csv"

INSTALACIÓN (una vez):

    py -m pip install playwright
    py -m playwright install chromium
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import (
        Page,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except ImportError:
    sys.stderr.write(
        "ERROR: falta playwright.\n"
        "Instalalo con:\n"
        "    py -m pip install playwright\n"
        "    py -m playwright install chromium\n"
    )
    sys.exit(2)

PORTAL_LOGIN = "https://auditool25.tool.com.co/gamexamplelogin.aspx"
PORTAL_FACTURAS = "https://auditool25.tool.com.co/glosasfacturaconww.aspx"

RE_PDF = re.compile(r"^NC_(\d{4,})_(HUS\d{6,12})\.pdf$", re.IGNORECASE)

logger = logging.getLogger("cargar_simed")


# ─── Setup ──────────────────────────────────────────────────────────────────


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def cargar_credenciales() -> tuple[str, str]:
    user = os.environ.get("SIMED_USER", "").strip()
    password = os.environ.get("SIMED_PASSWORD", "").strip()
    if not user or not password:
        sys.stderr.write(
            "ERROR: faltan credenciales. Setealas con:\n"
            "    setx SIMED_USER 900006037\n"
            "    setx SIMED_PASSWORD <tu_password>\n"
            "Después cerrá y reabrí PowerShell.\n"
        )
        sys.exit(2)
    return user, password


# ─── Búsqueda de carpetas ───────────────────────────────────────────────────


def buscar_carpetas(base: Path, solo: str | None = None) -> list[dict]:
    """Devuelve [{'nota','factura','factura_corta','gestor','pdf','xml','json','carpeta'}]."""
    carpetas = []
    # Recorre <base>/<GESTOR>/<NOTA>/  y <base>/<NOTA>/ por si no se organizó por gestor
    for sub in base.rglob("NC_*_HUS*.pdf"):
        if not sub.is_file():
            continue
        m = RE_PDF.match(sub.name)
        if not m:
            continue
        nota = m.group(1)
        factura = m.group(2)  # HUS0000466879
        factura_corta = factura.replace("HUS", "").lstrip("0") or "0"
        if solo and nota != solo:
            continue
        carpeta = sub.parent
        xml = carpeta / f"XML_{nota}_{factura}.xml"
        cuv = carpeta / f"CUV_{nota}_{factura}.json"
        gestor = carpeta.parent.name if carpeta.parent != base else ""  # ej. CAMILO o vacío
        carpetas.append(
            {
                "nota": nota,
                "factura": factura,
                "factura_corta": factura_corta,
                "gestor": gestor,
                "carpeta": carpeta,
                "pdf": sub,
                "xml": xml if xml.is_file() else None,
                "json": cuv if cuv.is_file() else None,
            }
        )
    carpetas.sort(key=lambda c: (c["gestor"], c["nota"]))
    return carpetas


# ─── Playwright: login y navegación ─────────────────────────────────────────


def login(page: Page, user: str, password: str) -> None:
    logger.info("Login al portal...")
    page.goto(PORTAL_LOGIN, wait_until="networkidle")

    # Los inputs de GeneXus suelen tener IDs como vUSRCOD/vPSW, pero usamos
    # selectores tolerantes por type/placeholder.
    user_input = page.locator(
        "input[type='text']:visible, input[name*='USR']:visible, input[id*='vUSR']:visible"
    ).first
    pwd_input = page.locator("input[type='password']:visible").first

    # click + type para que GeneXus dispare los eventos blur/change que
    # habilitan el botón submit (con .fill() solos a veces no alcanza).
    user_input.click()
    user_input.fill("")
    user_input.type(user, delay=30)
    user_input.press("Tab")  # dispara blur del usuario

    pwd_input.click()
    pwd_input.fill("")
    pwd_input.type(password, delay=30)

    # Estrategia 1: presionar Enter en el password (la forma más común de
    # submitir en GeneXus, evita lidiar con el botón que puede estar disabled).
    pwd_input.press("Enter")

    # Estrategia 2 (fallback): si después de 2s no se redirigió, esperar a
    # que el botón se habilite y darle click.
    try:
        page.wait_for_url(lambda url: "gamexamplelogin" not in url, timeout=3000)
    except PlaywrightTimeout:
        logger.info("  (Enter no submiteó, probando click en el botón)")
        boton = page.locator(
            "button:has-text('Iniciar'):not([disabled]), "
            "button:has-text('Ingresar'):not([disabled]), "
            "button:has-text('Aceptar'):not([disabled]), "
            "input[type='submit']:not([disabled])"
        ).first
        try:
            boton.wait_for(state="visible", timeout=5000)
            boton.click(timeout=10000)
        except PlaywrightTimeout:
            # Último recurso: forzar submit del form via JS
            logger.info("  (botón sigue disabled, forzando submit por JS)")
            page.evaluate("document.forms[0] && document.forms[0].submit()")

    # Esperar a que cargue index o cualquier página interna
    try:
        page.wait_for_url("**/index.aspx", timeout=15000)
    except PlaywrightTimeout:
        # Quizá no redirige a index, esperá el sidebar
        page.wait_for_selector("text=Procesos", timeout=10000)

    logger.info("Login OK")


def ir_a_facturas_conciliadas(page: Page) -> None:
    page.goto(PORTAL_FACTURAS, wait_until="networkidle")
    # Esperar la tabla
    page.wait_for_selector("text=Facturas Conciliadas", timeout=15000)


def _screenshot_debug(page: Page, etiqueta: str) -> Path:
    """Toma un screenshot full-page para diagnóstico, devuelve la ruta."""
    out_dir = Path("debug_screenshots")
    out_dir.mkdir(exist_ok=True)
    ts = time.strftime("%H%M%S")
    ruta = out_dir / f"{ts}_{etiqueta}.png"
    try:
        page.screenshot(path=str(ruta), full_page=True)
        logger.info(f"  Screenshot de diagnóstico: {ruta}")
    except Exception as e:
        logger.warning(f"  No pude tomar screenshot: {e}")
    return ruta


def filtrar_por_factura(page: Page, factura_corta: str) -> None:
    """Aplica el filtro de columna # Factura usando el DropDownOptions de GeneXus."""
    # 1. Click en el chevron DDO del header "# Factura".
    # En GeneXus el trigger es un img con src DDODefault.png o DDOFiltered.png,
    # o un link con clase dropdown-toggle.
    header = page.locator("th").filter(has_text="# Factura").first
    if header.count() == 0:
        # Fallback: cualquier th que contenga "Factura"
        header = page.locator("th").filter(has_text="Factura").first

    triggers = [
        "img[src*='DDO']",
        "[data-toggle='dropdown']",
        "a.dropdown-toggle",
        "a[onclick*='DropDownOptions']",
        "a",
    ]
    abierto = False
    for sel in triggers:
        try:
            header.locator(sel).first.click(timeout=2000)
            abierto = True
            break
        except PlaywrightTimeout:
            continue
    if not abierto:
        header.click()

    # 2. Esperar a que el dropdown se abra
    page.wait_for_timeout(1200)

    # 3. Buscar el input de búsqueda con selectores amplios
    input_selectores = [
        ".dropdown-menu.show input[type='text']:visible",
        ".dropdown-menu input[type='text']:visible",
        ".gx-dropdown-options input[type='text']:visible",
        ".DDOOptionFilteringDataContainer input:visible",
        ".DDOOptionFilter input:visible",
        "div[class*='DDO'] input[type='text']:visible",
        "div[class*='dropdown'] input[type='text']:visible",
        "input[type='text']:visible:not([readonly]):not([disabled])",
    ]
    input_buscar = None
    for sel in input_selectores:
        try:
            elem = page.locator(sel).first
            elem.wait_for(state="visible", timeout=2000)
            input_buscar = elem
            logger.info(f"  Input filtro encontrado con selector: {sel}")
            break
        except PlaywrightTimeout:
            continue

    if input_buscar is None:
        _screenshot_debug(page, f"filtro_no_encontrado_{factura_corta}")
        raise PlaywrightTimeout(
            "No encontré el input de búsqueda del filtro de # Factura. "
            "Mirá debug_screenshots/ para ver qué aparece en pantalla."
        )

    input_buscar.fill(factura_corta)
    page.wait_for_timeout(800)  # debounce

    # 4. Aplicar filtro: lupa o Enter
    try:
        page.locator(
            "img[src*='ApplyFilter']:visible, "
            "img[title*='Apply' i]:visible, "
            "img[title*='Aplicar' i]:visible, "
            "img[src*='Search']:visible"
        ).first.click(timeout=2000)
    except PlaywrightTimeout:
        input_buscar.press("Enter")

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)


class FacturaYaProcesada(Exception):
    """La factura no aparece en la grilla (probablemente ya tiene NC asignada)."""


def abrir_factura(page: Page, factura_corta: str) -> None:
    """Click en el ícono de editar (lápiz) de la fila filtrada.

    Si la grilla está vacía después del filtro (la factura ya fue procesada
    o no corresponde a este NIT), lanza FacturaYaProcesada.
    """
    # Esperar un poco a que la grilla termine de refrescar
    page.wait_for_timeout(1500)

    # Detectar si la grilla muestra "No se encontraron registros"
    no_resultados = page.locator("text=No se encontraron registros").first
    try:
        if no_resultados.is_visible(timeout=2000):
            raise FacturaYaProcesada(
                f"Factura {factura_corta} no aparece en la grilla "
                "(probablemente ya tiene NC asignada o no corresponde al NIT)"
            )
    except PlaywrightTimeout:
        pass  # no encontró el cartel, hay resultados

    # La fila debe contener el número de factura. Buscamos primero un selector
    # estricto (la columna de # Factura con ese valor exacto) y caemos a
    # uno más amplio si no encontramos.
    fila_estricta = page.locator("tr").filter(has_text=factura_corta).first
    try:
        fila_estricta.wait_for(state="visible", timeout=5000)
        fila = fila_estricta
    except PlaywrightTimeout:
        _screenshot_debug(page, f"fila_no_encontrada_{factura_corta}")
        raise

    # Botón editar: ícono <a> al inicio de la fila. Suele ser una imagen
    # con title="Actualizar" o un link a glosasfactura.aspx
    boton_editar = fila.locator(
        "a[title*='Actualizar' i], a[title*='Editar' i], a[title*='Edit' i], "
        "a:has(img[src*='ActionUpdate']), a:has(img[title*='Actualizar' i]), "
        "img[title*='Actualizar' i], img[title*='Editar' i], "
        "a[href*='glosasfactura.aspx']"
    ).first

    try:
        boton_editar.wait_for(state="visible", timeout=5000)
        boton_editar.click()
    except PlaywrightTimeout:
        _screenshot_debug(page, f"editar_no_encontrado_{factura_corta}")
        raise

    page.wait_for_url("**/glosasfactura.aspx*", timeout=15000)
    # Esperar a que cargue el editor. "Información General" siempre aparece.
    page.wait_for_selector("text=Información General", timeout=10000)


def ingresar_nota_y_subir(page: Page, info: dict) -> str:
    """Llena Nota Crédito Conciliación, sube los 3 archivos en el iframe."""
    nota = info["nota"]

    # Campo "Nota Credito Conciliación" — el del bloque "Conciliación Glosa".
    # En este portal hay UN solo campo visible para esta nota (el de respuesta
    # IPS no es editable; sólo Cartera tiene el de Conciliación).
    campo_nota = page.locator(
        "input[name*='FCTNOTCRECONGLO']:visible, input[id*='FCTNOTCRECONGLO']:visible"
    ).first
    if campo_nota.count() == 0:
        # Fallback: buscar por label asociado
        campo_nota = page.locator("label:has-text('Nota Credito Conciliacion'):visible").locator(
            "xpath=following::input[1]"
        )

    # type() + Tab para disparar los eventos blur/change que GeneXus necesita
    # para habilitar el botón "Soportes NC".
    campo_nota.click()
    campo_nota.fill("")
    campo_nota.type(nota, delay=30)
    campo_nota.press("Tab")
    page.wait_for_timeout(800)  # dejá que GeneXus haga su validación

    # Click "Soportes NC" del bloque de Conciliación. Esperar a que se habilite.
    soportes_btn = page.locator(
        "button:has-text('Soportes NC'):not([disabled]), "
        "input[value='Soportes NC']:not([disabled]), "
        "a:has-text('Soportes NC'):not([disabled])"
    ).last
    try:
        soportes_btn.wait_for(state="visible", timeout=8000)
        soportes_btn.click(timeout=8000)
    except PlaywrightTimeout:
        _screenshot_debug(page, f"soportes_btn_disabled_{nota}")
        raise

    # Esperar a que aparezca el iframe wcargarsoportesrtaips
    page.wait_for_selector(
        "iframe[src*='wcargarsoportesrtaips'], iframe[src*='soportes']", timeout=10000
    )
    iframe = page.frame_locator("iframe[src*='wcargarsoportesrtaips'], iframe[src*='soportes']")

    # Subir los 3 archivos
    archivos = [str(info["pdf"]), str(info["xml"]), str(info["json"])]
    file_input = iframe.locator("input[type='file']").first
    file_input.set_input_files(archivos)

    # Esperar a que termine la subida (FileUpload muestra progress)
    # El upload se hace por archivo, esperamos un margen amplio
    page.wait_for_timeout(5000)

    # Confirmar la subida (botón Aceptar/Confirmar/Cargar dentro del iframe)
    try:
        iframe.locator(
            "button:has-text('Aceptar'), button:has-text('Cargar'), "
            "button:has-text('Subir'), button:has-text('Confirmar'), "
            "input[value='Aceptar'], input[value='Confirmar']"
        ).first.click(timeout=5000)
    except PlaywrightTimeout:
        logger.info("  (sin botón Aceptar/Cargar visible, asumo upload automático)")

    page.wait_for_timeout(2000)

    # Cerrar/regresar del iframe (suele haber un "Regresar" o "X")
    try:
        iframe.locator(
            "button:has-text('Regresar'), a:has-text('Regresar'), button:has-text('Cerrar')"
        ).first.click(timeout=3000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(1500)

    return "soportes_subidos"


def confirmar_factura(page: Page) -> str:
    """Click Actualizar Respuestas + Confirmar. Verifica 'Registro completado'."""
    # Actualizar Respuestas (puede no existir en algunos casos)
    try:
        page.locator(
            "button:has-text('Actualizar Respuestas'), input[value='Actualizar Respuestas']"
        ).first.click(timeout=3000)
        page.wait_for_timeout(1000)
    except PlaywrightTimeout:
        pass

    # Confirmar (botón rojo principal)
    page.locator(
        "button:has-text('Confirmar'):not(:has-text('Cancelar')), input[value='Confirmar']"
    ).first.click()

    # Esperar mensaje de confirmación
    try:
        page.wait_for_selector("text=Registro completado", timeout=15000)
        return "OK"
    except PlaywrightTimeout:
        # Quizá el mensaje viene en un iframe mensajes.aspx
        try:
            mensajes = page.frame_locator("iframe[src*='mensajes']")
            mensajes.locator("text=Registro completado").wait_for(timeout=5000)
            return "OK"
        except PlaywrightTimeout:
            return "SIN_CONFIRMACION"


# ─── Orquestación ───────────────────────────────────────────────────────────


def procesar_una(page: Page, info: dict) -> dict:
    nota = info["nota"]
    factura = info["factura"]
    factura_corta = info["factura_corta"]
    registro = {
        "nota": nota,
        "factura": factura,
        "gestor": info["gestor"],
        "carpeta": str(info["carpeta"]),
        "estado": "",
        "detalle": "",
    }

    # Validar que los 3 archivos existen
    if info["xml"] is None or info["json"] is None:
        registro["estado"] = "FALTAN_ARCHIVOS"
        faltan = []
        if info["xml"] is None:
            faltan.append("XML")
        if info["json"] is None:
            faltan.append("CUV/JSON")
        registro["detalle"] = "Faltan: " + ", ".join(faltan)
        return registro

    try:
        ir_a_facturas_conciliadas(page)
        filtrar_por_factura(page, factura_corta)
        abrir_factura(page, factura_corta)
        ingresar_nota_y_subir(page, info)
        estado = confirmar_factura(page)
        registro["estado"] = estado
    except FacturaYaProcesada as e:
        registro["estado"] = "YA_PROCESADA"
        registro["detalle"] = str(e)[:200]
    except PlaywrightTimeout as e:
        registro["estado"] = "TIMEOUT"
        registro["detalle"] = str(e)[:200]
        _screenshot_debug(page, f"timeout_{nota}")
    except Exception as e:
        registro["estado"] = "ERROR"
        registro["detalle"] = f"{type(e).__name__}: {str(e)[:200]}"
        _screenshot_debug(page, f"error_{nota}")

    return registro


def escribir_reporte(resultados: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = ["nota", "factura", "gestor", "carpeta", "estado", "detalle"]
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for r in resultados:
            writer.writerow({k: r.get(k, "") for k in campos})
    logger.info(f"Reporte: {ruta}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--destino", type=Path, required=True, help="Base con subcarpetas <GESTOR>/<NOTA>/"
    )
    parser.add_argument(
        "--solo", type=str, help="Procesar solo esta NOTA (recomendado para test inicial)"
    )
    parser.add_argument(
        "--todas", action="store_true", help="Procesar todas las facturas encontradas"
    )
    parser.add_argument(
        "--con-cabeza", action="store_true", help="Mostrar el browser (no headless)"
    )
    parser.add_argument("--lento", action="store_true", help="Frenar 500ms entre acciones (debug)")
    parser.add_argument("--reporte", type=Path, default=Path("reporte_carga_simed.csv"))
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()

    setup_logging(args.log)

    if not args.solo and not args.todas:
        logger.error("Pasá --solo <NOTA> para test, o --todas para procesar todo.")
        return 1
    if not args.destino.is_dir():
        logger.error(f"--destino no existe: {args.destino}")
        return 1

    user, password = cargar_credenciales()
    logger.info(f"Usuario SIMED: {user}")

    carpetas = buscar_carpetas(args.destino, solo=args.solo)
    if not carpetas:
        logger.error(f"No encontré carpetas con PDF NC_*_HUS*.pdf bajo {args.destino}")
        return 1
    logger.info(f"Facturas a procesar: {len(carpetas)}")

    resultados: list[dict] = []
    inicio = time.time()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not args.con_cabeza,
                slow_mo=500 if args.lento else 0,
            )
            context = browser.new_context(accept_downloads=False)
            page = context.new_page()
            page.set_default_timeout(20000)

            login(page, user, password)

            for i, info in enumerate(carpetas, 1):
                logger.info(
                    f"[{i}/{len(carpetas)}] nota {info['nota']} ({info['factura']}) — gestor: {info['gestor']}"
                )
                r = procesar_una(page, info)
                logger.info(f"  → {r['estado']} {('— ' + r['detalle']) if r['detalle'] else ''}")
                resultados.append(r)
                # Pequeña pausa entre facturas para no saturar
                page.wait_for_timeout(1500)

            context.close()
            browser.close()
    finally:
        escribir_reporte(resultados, args.reporte)
        dur = time.time() - inicio
        resumen: dict[str, int] = {}
        for r in resultados:
            resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
        logger.info("=" * 60)
        logger.info("RESUMEN FINAL")
        logger.info(f"  Facturas procesadas: {len(resultados)} en {dur / 60:.1f} min")
        for k, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
            logger.info(f"    {k}: {n}")

    problemas = sum(n for k, n in resumen.items() if k != "OK")
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
