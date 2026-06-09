"""responder_glosas_simed.py — Carga masiva de respuestas a glosas en SIMED.

Para cada factura del Excel (generado por `extraer_respuestas_glosa.py` y
revisado por vos), recorre las objeciones una por una en el portal SIMED:

1. Login (una sola vez).
2. Por cada factura:
   - Va a "Respuesta Glosa Rad. WEB" (glosasfacturaww.aspx).
   - Filtra por # Factura.
   - Click en el lápiz → abre "Glosas Factura".
   - PARA CADA OBJECIÓN (1..N) del Excel:
     a) Click en el ícono gris de la fila → abre modal "Respuesta Glosa Ips Web".
     b) Tab "Información Glosa": escribe Aceptado, deja NC vacío, escribe
        el Detalle Respuesta sanitizado (sin tildes/ñ).
     c) Tab "Soportes": sube el Trámite + todos los archivos de la carpeta
        de soportes de la factura (las dos fuentes que pasaste).
     d) Click "Confirmar" del modal.
   - Click "Confirmar" del form principal (debajo de la grilla).
   - Click botón verde de la grilla (Enviar/Finalizar) y espera el OK.
3. Reporte CSV con el estado de cada factura.

CREDENCIALES (en variables de entorno):
    setx SIMED_USER 900006037
    setx SIMED_PASSWORD <tu_password>

USO:
    REM Piloto con una factura, browser visible para verificar
    py responder_glosas_simed.py ^
        --excel          "D:\\GLOSAS_2026\\respuestas_glosa.xlsx" ^
        --soportes-glosa "D:\\USUARIO CARTERA\\Documents\\GLOSAS 2026\\DISPENSARIO MEDICO\\Nueva carpeta\\SOPORTES" ^
        --indice         "D:\\indice_facturas_HUS.txt" ^
        --solo HUS0000452150 ^
        --con-cabeza

    REM Lote completo
    py responder_glosas_simed.py ^
        --excel ... --soportes-glosa ... --indice ... ^
        --todas ^
        --reporte "D:\\GLOSAS_2026\\reporte_glosa.csv"

INSTALACIÓN (una vez):
    py -m pip install playwright openpyxl
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
import unicodedata
from pathlib import Path

try:
    from playwright.sync_api import (
        Page,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except ImportError:
    # Permitir importar helpers (sanitizar, leer_excel_respuestas, etc.) sin
    # playwright instalado. Las funciones de browser fallarán en runtime con
    # un mensaje claro si se ejecuta sin la dependencia.
    Page = object  # type: ignore[assignment,misc]
    PlaywrightTimeout = Exception  # type: ignore[assignment,misc]
    sync_playwright = None  # type: ignore[assignment]


def _exigir_playwright() -> None:
    if sync_playwright is None:
        sys.stderr.write(
            "ERROR: falta playwright.\n"
            "Instalalo con:\n"
            "    py -m pip install playwright\n"
            "    py -m playwright install chromium\n"
        )
        sys.exit(2)

PORTAL_LOGIN = "https://auditool25.tool.com.co/gamexamplelogin.aspx"
PORTAL_GLOSAS = "https://auditool25.tool.com.co/glosasfacturaww.aspx"

logger = logging.getLogger("responder_glosas")


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
            "Despues cerra y reabri PowerShell.\n"
        )
        sys.exit(2)
    return user, password


# ─── Sanitización de texto (sin tildes/ñ/caracteres especiales) ─────────────


def sanitizar(s: str) -> str:
    """Quita tildes y deja solo ASCII imprimible. SIMED no acepta especiales."""
    if not s:
        return ""
    # NFKD separa la letra de su tilde; luego filtramos los diacríticos.
    base = unicodedata.normalize("NFKD", s)
    sin_tildes = "".join(c for c in base if not unicodedata.combining(c))
    # Quedarnos sólo con ASCII imprimible (espacios, números, letras, puntuación básica).
    limpio = "".join(c if 32 <= ord(c) < 127 else " " for c in sin_tildes)
    # Colapsar espacios.
    return re.sub(r"\s+", " ", limpio).strip()


# ─── Lectura del Excel de respuestas ────────────────────────────────────────


def normalizar_factura(s: str) -> str:
    """HUS0000452150 → 452150 (sin prefijo y sin ceros a la izquierda)."""
    s = (s or "").strip().upper()
    m = re.match(r"HUS0*(\d+)$", s)
    return m.group(1) if m else s.lstrip("0") or s


def leer_excel_respuestas(ruta: Path) -> list[dict]:
    """Devuelve una lista de dicts {factura, factura_corta, num, aceptado, detalle}.

    Acepta cabeceras con variantes (tolerante mayúsculas/acentos/espacios).
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl. Instalalo con: py -m pip install openpyxl\n")
        sys.exit(2)

    def norm(h: str) -> str:
        s = unicodedata.normalize("NFKD", (h or "").strip().upper())
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", s)

    alias = {
        "factura": {"FACTURA", "# FACTURA", "NUM FACTURA", "NUMERO FACTURA"},
        "num": {"# OBJECION", "NUM OBJECION", "OBJECION", "NUMERO OBJECION", "ITEM"},
        "aceptado": {"VALOR ACEPTADO", "ACEPTADO", "VI ACEPTADO"},
        "detalle": {"DETALLE RESPUESTA", "RESPUESTA", "OBSERVACIONES", "DETALLE"},
    }

    wb = load_workbook(filename=str(ruta), data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    headers = ["" if h is None else str(h) for h in next(rows)]
    headers_norm = [norm(h) for h in headers]

    idx: dict[str, int] = {}
    for clave, opciones in alias.items():
        for i, h in enumerate(headers_norm):
            if h in opciones:
                idx[clave] = i
                break
        if clave not in idx:
            raise ValueError(
                f"No encontre la columna '{clave}'. Acepto cualquiera de {sorted(opciones)}. "
                f"Headers detectados: {headers}"
            )

    filas: list[dict] = []
    for row in rows:
        if row is None or all(v in (None, "") for v in row):
            continue
        factura = str(row[idx["factura"]] or "").strip()
        if not factura:
            continue
        try:
            num = int(row[idx["num"]] or 0)
        except (TypeError, ValueError):
            continue
        if num <= 0:
            continue
        aceptado_raw = row[idx["aceptado"]]
        try:
            aceptado = int(float(str(aceptado_raw).replace(",", ".") or 0))
        except (TypeError, ValueError):
            aceptado = 0
        detalle = sanitizar(str(row[idx["detalle"]] or ""))
        filas.append(
            {
                "factura": factura,
                "factura_corta": normalizar_factura(factura),
                "num": num,
                "aceptado": aceptado,
                "detalle": detalle,
            }
        )

    # Agrupar por factura, ordenado por # objeción.
    facturas: dict[str, list[dict]] = {}
    for f in filas:
        facturas.setdefault(f["factura_corta"], []).append(f)
    for fac in facturas.values():
        fac.sort(key=lambda r: r["num"])
    return facturas


# ─── Índice de soportes por factura ─────────────────────────────────────────


def cargar_indice(ruta: Path) -> dict[str, Path]:
    """Lee el TXT indice_facturas_HUS.txt y devuelve {factura_corta: Path}.

    Cada línea es una ruta tipo:
        X:\\SERVIDOR RADICACION\\... \\HUS452150
    El último segmento es HUS<numero>; lo usamos como clave.
    """
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el indice: {ruta}")
    mapa: dict[str, Path] = {}
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = ruta.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"No pude decodificar el indice: {ruta}")

    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        m = re.search(r"\\(HUS\d{6,12})\s*$", linea, re.IGNORECASE)
        if not m:
            continue
        factura_corta = normalizar_factura(m.group(1))
        mapa[factura_corta] = Path(linea)
    return mapa


def buscar_soportes(
    factura_corta: str,
    factura_larga: str,
    carpeta_glosa: Path,
    indice: dict[str, Path] | None,
    carpeta_share_override: Path | None = None,
) -> tuple[list[Path], list[str]]:
    """Devuelve (lista_de_archivos_a_subir, advertencias).

    Fuentes (en orden):
      1. PDF de respuesta a la glosa en `carpeta_glosa\\HUS<factura>.pdf`.
      2. Todos los archivos de la carpeta del share — viene de
         `carpeta_share_override` (override directo), o del `indice` si se dio.
         Si no hay ninguna, se omite la fuente 2 (sólo se sube el Trámite).
    """
    archivos: list[Path] = []
    avisos: list[str] = []

    # 1) PDF Trámite/respuesta de la glosa. Buscamos por nombre tolerante.
    candidatos_glosa = [
        carpeta_glosa / f"{factura_larga}.pdf",
        carpeta_glosa / f"HUS{factura_corta}.pdf",
        carpeta_glosa / f"HUS0000{factura_corta}.pdf",
    ]
    encontrado = None
    for c in candidatos_glosa:
        if c.is_file():
            encontrado = c
            break
    if not encontrado and carpeta_glosa.is_dir():
        # Búsqueda relajada: cualquier *.pdf que contenga el número.
        for p in carpeta_glosa.glob("*.pdf"):
            if factura_corta in p.stem:
                encontrado = p
                break
    if encontrado:
        archivos.append(encontrado)
    else:
        avisos.append(f"No hallé el PDF de respuesta para HUS{factura_corta} en {carpeta_glosa}")

    # 2) Carpeta de soportes de la factura (HC, HEV, HAM, etc.).
    carpeta_soportes: Path | None = None
    if carpeta_share_override is not None:
        carpeta_soportes = carpeta_share_override
    elif indice is not None:
        carpeta_soportes = indice.get(factura_corta)
        if carpeta_soportes is None:
            avisos.append(f"No hallé HUS{factura_corta} en el indice (sin soportes del share).")
    else:
        avisos.append("Sin --indice ni --carpeta-share: subo sólo el PDF de Trámite (no los HC/HEV/HAM).")

    if carpeta_soportes is not None:
        if not carpeta_soportes.is_dir():
            avisos.append(f"La carpeta de soportes no es accesible: {carpeta_soportes}")
        else:
            for p in sorted(carpeta_soportes.iterdir()):
                if p.is_file():
                    archivos.append(p)
    return archivos, avisos


# ─── Helpers de browser (reusados/adaptados de cargar_soportes_simed) ───────


def _screenshot_debug(page: Page, etiqueta: str) -> Path:
    out_dir = Path("debug_screenshots")
    out_dir.mkdir(exist_ok=True)
    ts = time.strftime("%H%M%S")
    ruta = out_dir / f"{ts}_{etiqueta}.png"
    try:
        page.screenshot(path=str(ruta), full_page=True)
        logger.info(f"  Screenshot de diagnostico: {ruta}")
    except Exception as e:
        logger.warning(f"  No pude tomar screenshot: {e}")
    return ruta


def login(page: Page, user: str, password: str) -> None:
    logger.info("Login al portal...")
    page.goto(PORTAL_LOGIN, wait_until="networkidle")
    u = page.locator(
        "input[type='text']:visible, input[name*='USR']:visible, input[id*='vUSR']:visible"
    ).first
    p = page.locator("input[type='password']:visible").first
    u.click(); u.fill(""); u.type(user, delay=30); u.press("Tab")
    p.click(); p.fill(""); p.type(password, delay=30); p.press("Enter")
    try:
        page.wait_for_url(lambda url: "gamexamplelogin" not in url, timeout=3000)
    except PlaywrightTimeout:
        boton = page.locator(
            "button:has-text('Iniciar'):not([disabled]), "
            "button:has-text('Ingresar'):not([disabled]), "
            "button:has-text('Aceptar'):not([disabled]), "
            "input[type='submit']:not([disabled])"
        ).first
        try:
            boton.wait_for(state="visible", timeout=5000); boton.click(timeout=10000)
        except PlaywrightTimeout:
            page.evaluate("document.forms[0] && document.forms[0].submit()")
    try:
        page.wait_for_url("**/index.aspx", timeout=15000)
    except PlaywrightTimeout:
        page.wait_for_selector("text=Procesos", timeout=10000)
    logger.info("Login OK")


def ir_a_respuesta_glosa_web(page: Page) -> None:
    """Va a la grilla 'Respuesta Glosa Rad. WEB' (glosasfacturaww.aspx)."""
    page.goto(PORTAL_GLOSAS, wait_until="networkidle")
    page.wait_for_selector("text=Respuesta a Glosas", timeout=15000)


def filtrar_por_factura(page: Page, factura_corta: str) -> None:
    """Aplica el filtro de columna '# Factura' (DropDownOptions de GeneXus).

    Idéntica lógica a cargar_soportes_simed.py — el portal es el mismo.
    """
    header = page.locator("th").filter(has_text="# Factura").first
    if header.count() == 0:
        header = page.locator("th").filter(has_text="Factura").first

    for sel in (
        "img[src*='DDO']",
        "[data-toggle='dropdown']",
        "a.dropdown-toggle",
        "a[onclick*='DropDownOptions']",
        "a",
    ):
        try:
            header.locator(sel).first.click(timeout=2000); break
        except PlaywrightTimeout:
            continue
    else:
        header.click()

    page.wait_for_timeout(1200)
    input_buscar = None
    for sel in (
        ".dropdown-menu.show input[type='text']:visible",
        ".dropdown-menu input[type='text']:visible",
        ".DDOOptionFilteringDataContainer input:visible",
        ".DDOOptionFilter input:visible",
        "div[class*='DDO'] input[type='text']:visible",
        "div[class*='dropdown'] input[type='text']:visible",
        "input[type='text']:visible:not([readonly]):not([disabled])",
    ):
        try:
            elem = page.locator(sel).first
            elem.wait_for(state="visible", timeout=2000)
            input_buscar = elem; break
        except PlaywrightTimeout:
            continue
    if input_buscar is None:
        _screenshot_debug(page, f"filtro_no_encontrado_{factura_corta}")
        raise PlaywrightTimeout("No encontre el input del filtro # Factura.")

    input_buscar.fill(factura_corta)
    page.wait_for_timeout(800)
    try:
        page.locator(
            "img[src*='ApplyFilter']:visible, img[title*='Apply' i]:visible, "
            "img[title*='Aplicar' i]:visible, img[src*='Search']:visible"
        ).first.click(timeout=2000)
    except PlaywrightTimeout:
        input_buscar.press("Enter")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)


def abrir_factura(page: Page, factura_corta: str) -> None:
    """Click en el lápiz de la fila filtrada → abre glosasfactura.aspx."""
    page.wait_for_timeout(1500)
    no_resultados = page.locator("text=No se encontraron registros").first
    try:
        if no_resultados.is_visible(timeout=2000):
            raise RuntimeError(f"Factura {factura_corta} no aparece en la grilla.")
    except PlaywrightTimeout:
        pass
    fila = page.locator("tr").filter(has_text=factura_corta).first
    try:
        fila.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeout:
        _screenshot_debug(page, f"fila_no_encontrada_{factura_corta}"); raise
    boton_editar = fila.locator(
        "a[title*='Actualizar' i], a[title*='Editar' i], a[title*='Edit' i], "
        "a:has(img[src*='ActionUpdate']), a:has(img[title*='Actualizar' i]), "
        "img[title*='Actualizar' i], img[title*='Editar' i], "
        "a[href*='glosasfactura.aspx']"
    ).first
    try:
        boton_editar.wait_for(state="visible", timeout=5000); boton_editar.click()
    except PlaywrightTimeout:
        _screenshot_debug(page, f"editar_no_encontrado_{factura_corta}"); raise
    page.wait_for_url("**/glosasfactura.aspx*", timeout=15000)
    page.wait_for_selector("text=Información General", timeout=10000)


# ─── Lógica nueva: iterar objeciones y rellenar el modal ────────────────────


def _localizar_fila_objecion(page: Page, num_objecion: int):
    """Devuelve la fila <tr> de la objeción N en la grilla visible, o None."""
    # En la grilla 'Respuesta Glosa Ips' la columna '# Objeción' contiene un
    # link con el número (en el screenshot, los números 1..10 son links azules
    # debajo del header "# Objeción").
    target = str(num_objecion)
    # Estrategia 1: la celda con SÓLO el número.
    fila = page.locator("tr").filter(
        has=page.locator(f"xpath=.//td[normalize-space(.)='{target}']")
    ).first
    if fila.count() > 0:
        try:
            fila.wait_for(state="visible", timeout=2000)
            return fila
        except PlaywrightTimeout:
            pass
    # Estrategia 2: link con SÓLO el número.
    fila = page.locator("tr").filter(
        has=page.locator(f"xpath=.//a[normalize-space(.)='{target}']")
    ).first
    if fila.count() > 0:
        try:
            fila.wait_for(state="visible", timeout=2000)
            return fila
        except PlaywrightTimeout:
            pass
    return None


def _siguiente_pagina_grilla(page: Page) -> bool:
    """Click en 'Sig' de la paginación. Devuelve True si avanzó, False si no hay más."""
    # En GeneXus la paginación suele ser "Ant | 1 2 3 ... | Sig" con links.
    # Buscamos un link 'Sig' o 'Siguiente' habilitado.
    boton_sig = page.locator(
        "a:has-text('Sig'):not(.disabled), a:has-text('Siguiente'):not(.disabled), "
        "img[title*='Sig' i]:visible, img[title*='Siguiente' i]:visible"
    ).first
    try:
        if boton_sig.count() == 0 or not boton_sig.is_visible(timeout=1500):
            return False
        boton_sig.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(700)
        return True
    except PlaywrightTimeout:
        return False


def abrir_modal_objecion(page: Page, num_objecion: int) -> None:
    """Abre el modal 'Respuesta Glosa Ips Web' de la objeción N.

    En la grilla 'Respuesta Glosa Ips' (dentro de la pantalla 'Glosas Factura')
    cada fila trae el número de objeción como un LINK azul (clickable) en la
    columna '# Objeción'. Click ahí abre el modal.

    Recorre las páginas de la grilla hasta encontrar la objeción.
    """
    page.wait_for_selector("text=Respuesta Glosa Ips", timeout=10000)

    fila = None
    for _ in range(10):  # hasta 10 páginas
        fila = _localizar_fila_objecion(page, num_objecion)
        if fila is not None:
            break
        if not _siguiente_pagina_grilla(page):
            break
    if fila is None:
        _screenshot_debug(page, f"objecion_no_hallada_{num_objecion}")
        raise RuntimeError(
            f"No encontre la objecion #{num_objecion} en la grilla "
            "(¿el Excel quedó desincronizado del portal?)"
        )

    target = str(num_objecion)
    # Estrategias en orden — la PRIMERA que abra el modal gana.
    estrategias = [
        # 1) Ícono LÁPIZ ROJO con tooltip "Dar Respuesta" (la forma oficial del portal).
        ("dar_respuesta", lambda f: f.locator(
            "a[title*='Dar Respuesta' i], a:has(img[title*='Dar Respuesta' i]), "
            "img[title*='Dar Respuesta' i], a[title*='Responder' i], "
            "a:has(img[title*='Responder' i])"
        ).first),
        # 2) Link con el número exacto en la columna # Objeción.
        ("link_numero_obj", lambda f: f.locator(
            f"xpath=.//a[normalize-space(.)='{target}']"
        ).first),
        # 3) Ícono "Modificar/Actualizar/Editar" con title o img conocido.
        ("icono_modificar", lambda f: f.locator(
            "a[title*='Modificar' i], a[title*='Actualizar' i], a[title*='Editar' i], "
            "a:has(img[src*='ActionUpdate' i]), a:has(img[src*='Edit' i]), "
            "a:has(img[src*='Modify' i]), img[title*='Modificar' i], img[title*='Editar' i]"
        ).first),
        # 4) Cualquier link clickable en las primeras 3 celdas con href real (no '#').
        ("link_inicio_fila", lambda f: f.locator(
            "xpath=.//td[position()<=3]//a[@href and @href!='#' and not(contains(@href,'javascript:void'))]"
        ).first),
    ]

    ultimo_error = None
    for nombre, hacer_loc in estrategias:
        candidato = hacer_loc(fila)
        try:
            if candidato.count() == 0:
                continue
            candidato.wait_for(state="visible", timeout=2500)
        except PlaywrightTimeout as e:
            ultimo_error = e
            continue
        # Intentar click.
        try:
            candidato.click(timeout=4000)
            logger.info(f"  estrategia para abrir modal: {nombre}")
        except PlaywrightTimeout as e:
            ultimo_error = e
            continue
        # Verificar que el modal apareció.
        try:
            page.wait_for_selector("text=Respuesta Glosa Ips Web", timeout=4500)
            page.wait_for_selector("text=Información Glosa", timeout=3000)
            return  # éxito
        except PlaywrightTimeout as e:
            ultimo_error = e
            # No abrió modal; cierro algún popup accidental y reintento con la próxima.
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            continue

    _screenshot_debug(page, f"modal_no_abrio_{num_objecion}")
    raise RuntimeError(
        f"No pude abrir el modal de la objecion #{num_objecion} con ninguna "
        f"estrategia (último error: {ultimo_error})"
    )


def llenar_informacion_glosa(page: Page, aceptado: int, detalle: str) -> None:
    """Tab 'Información Glosa' del modal: Aceptado, NC (vacío), Detalle Respuesta."""
    # Asegurar que estamos en el tab 'Información Glosa'.
    try:
        tab = page.locator("a:has-text('Información Glosa'), li:has-text('Información Glosa') a").first
        tab.click(timeout=2000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(300)

    # Campo Aceptado: input numérico tras el label 'Aceptado'.
    aceptado_input = page.locator(
        "input[name*='ACEPTADO']:visible, input[id*='ACEPTADO']:visible, "
        "label:has-text('Aceptado') + * input:visible"
    ).first
    if aceptado_input.count() == 0:
        # Fallback por XPath del label.
        aceptado_input = page.locator(
            "xpath=//label[contains(., 'Aceptado')]/following::input[1]"
        )
    aceptado_input.click()
    aceptado_input.fill("")
    aceptado_input.type(str(aceptado), delay=20)
    aceptado_input.press("Tab")

    # Campo Nota Credito: limpiar (queda vacío) — ya no van NCs.
    nc_input = page.locator(
        "input[name*='NOTA']:visible, input[id*='NOTA']:visible, "
        "label:has-text('Nota Credito') + * input:visible"
    ).first
    if nc_input.count() > 0:
        try:
            nc_input.fill("")
        except Exception:
            pass

    # Campo Detalle Respuesta (textarea, 4000 chars).
    detalle_input = page.locator(
        "textarea[name*='DETALLE']:visible, textarea[id*='DETALLE']:visible, "
        "textarea:visible"
    ).first
    detalle_input.click()
    detalle_input.fill("")
    # Type con velocidad moderada — algunos portales validan onkey.
    detalle_input.type(detalle[:4000], delay=2)


def subir_soportes_modal(page: Page, archivos: list[Path]) -> None:
    """Tab 'Soportes' del modal: sube todos los archivos de la lista."""
    if not archivos:
        return
    # Click en el tab 'Soportes'.
    try:
        tab = page.locator("a:has-text('Soportes'), li:has-text('Soportes') a").first
        tab.click(timeout=2000)
        page.wait_for_timeout(500)
    except PlaywrightTimeout:
        logger.warning("  No pude clickear el tab Soportes (¿ya estaba activo?)")

    page.wait_for_selector("text=Agregar Soportes", timeout=8000)

    # set_input_files al <input type='file'> oculto (esquina del fileupload).
    file_input = page.locator("input[type='file']").first
    file_input.set_input_files([str(p) for p in archivos])
    page.wait_for_timeout(800)

    # Click 'Iniciar subida'.
    try:
        page.locator("button:has-text('Iniciar subida'), a:has-text('Iniciar subida')").first.click(timeout=5000)
    except PlaywrightTimeout:
        logger.warning("  Sin botón 'Iniciar subida' visible; intento seguir igual.")

    # Esperar a que termine la subida. Heurística simple: dar tiempo proporcional
    # al número de archivos y verificar que no haya barras de progreso activas.
    timeout_total_ms = 5000 + 4000 * len(archivos)
    deadline = time.time() + timeout_total_ms / 1000
    while time.time() < deadline:
        en_progreso = page.locator(".progress-bar:not([aria-valuenow='100'])").count()
        if en_progreso == 0:
            break
        page.wait_for_timeout(500)

    # Click 'Agregar' (botón rojo que registra los archivos en la tabla).
    try:
        page.locator("button:has-text('Agregar'):not(:has-text('archivos')), input[value='Agregar']").first.click(timeout=5000)
        page.wait_for_timeout(500)
    except PlaywrightTimeout:
        logger.warning("  No encontré el botón 'Agregar' del modal de soportes.")


def confirmar_modal(page: Page) -> None:
    """Click 'Confirmar' al pie del modal — guarda la respuesta y cierra."""
    # El modal tiene su propio Confirmar; lo distinguimos buscando uno
    # visible dentro de un contenedor que tenga 'Respuesta Glosa Ips Web'.
    try:
        # Volver a la pestaña 'Información Glosa' donde está Confirmar.
        try:
            page.locator("a:has-text('Información Glosa')").first.click(timeout=1500)
            page.wait_for_timeout(300)
        except PlaywrightTimeout:
            pass
        page.locator(
            "button:has-text('Confirmar'):visible, input[type='button'][value='Confirmar']:visible"
        ).first.click(timeout=5000)
    except PlaywrightTimeout:
        _screenshot_debug(page, "modal_sin_confirmar"); raise
    # Esperar a que el modal desaparezca.
    try:
        page.wait_for_selector("text=Respuesta Glosa Ips Web", state="hidden", timeout=10000)
    except PlaywrightTimeout:
        logger.warning("  El modal no se cerró tras Confirmar (puede ser por validación).")


def confirmar_form_principal(page: Page) -> None:
    """Click 'Confirmar' de la pantalla 'Glosas Factura' (debajo de la grilla)."""
    page.locator(
        "button:has-text('Confirmar'):visible, input[type='button'][value='Confirmar']:visible"
    ).first.click(timeout=8000)
    page.wait_for_load_state("networkidle")


def enviar_finalizar(page: Page, factura_corta: str) -> str:
    """Click botón verde de la grilla (igual que las NCs) y valida el OK del portal."""
    ir_a_respuesta_glosa_web(page)
    filtrar_por_factura(page, factura_corta)
    page.wait_for_timeout(1500)
    fila = page.locator("tr").filter(has_text=factura_corta).first
    fila.wait_for(state="visible", timeout=8000)
    boton_verde = fila.locator(
        "a:has(img[src*='ActionExportFile2']), img[src*='ActionExportFile2'], "
        "a:has(img[title*='Enviar' i]), img[title*='Enviar' i], "
        "a:has(img[title*='Finalizar' i]), img[title*='Finalizar' i]"
    ).first
    boton_verde.wait_for(state="visible", timeout=5000)
    boton_verde.click()

    # Esperar el iframe/diálogo de confirmación final.
    try:
        page.wait_for_selector(
            "iframe[src*='mensajes'], iframe[src*='mensaje'], "
            "text=Respuesta cargada, text=Registro completado, text=Completada",
            timeout=10000,
        )
    except PlaywrightTimeout:
        _screenshot_debug(page, f"sin_dialogo_final_{factura_corta}")
        return "OK_SIN_DIALOGO"

    # Si hay iframe mensajes, leer su texto.
    iframes = page.frames
    for fr in iframes:
        if "mensaje" in (fr.url or ""):
            try:
                texto = (fr.locator("body").inner_text(timeout=2000) or "").strip()
                if any(k in texto.upper() for k in ("RESPUESTA CARGADA", "COMPLETADA", "COMPLETADO")):
                    # Confirmar el OK del popup.
                    try:
                        fr.locator("button:has-text('Confirmar'), button:has-text('OK')").first.click(timeout=2000)
                    except PlaywrightTimeout:
                        pass
                    return "OK"
                return f"RECHAZADA: {texto[:200]}"
            except PlaywrightTimeout:
                continue
    return "OK"


# ─── Driver principal ───────────────────────────────────────────────────────


def procesar_factura(
    page: Page,
    factura_corta: str,
    factura_larga: str,
    objeciones: list[dict],
    archivos_soportes: list[Path],
) -> dict:
    """Procesa UNA factura: filtra, abre, loop objeciones, confirma, envia."""
    reg = {"factura": factura_larga, "objeciones": len(objeciones), "estado": "", "detalle": ""}
    try:
        ir_a_respuesta_glosa_web(page)
        filtrar_por_factura(page, factura_corta)
        abrir_factura(page, factura_corta)

        for ob in objeciones:
            logger.info(f"  → objecion #{ob['num']} (aceptado={ob['aceptado']}, detalle {len(ob['detalle'])} chars)")
            abrir_modal_objecion(page, ob["num"])
            llenar_informacion_glosa(page, ob["aceptado"], ob["detalle"])
            subir_soportes_modal(page, archivos_soportes)
            confirmar_modal(page)
            page.wait_for_timeout(800)

        confirmar_form_principal(page)
        estado = enviar_finalizar(page, factura_corta)
        reg["estado"] = estado
    except Exception as e:
        reg["estado"] = "ERROR"
        reg["detalle"] = f"{type(e).__name__}: {e}"
        logger.error(f"  ✗ {factura_larga}: {reg['detalle']}")
        _screenshot_debug(page, f"error_{factura_corta}")
    return reg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Carga masiva de respuestas a glosas en SIMED (item por item).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--excel", type=Path, required=True, help="Excel con respuestas (de extraer_respuestas_glosa.py).")
    parser.add_argument("--soportes-glosa", type=Path, required=True, help="Carpeta con HUS<factura>.pdf (Trámite/Respuesta).")
    parser.add_argument(
        "--indice",
        type=Path,
        default=None,
        help="TXT con rutas <ruta_share>\\HUS<factura>. Si se omite, se usa --carpeta-share o se sube sólo el Trámite.",
    )
    parser.add_argument(
        "--carpeta-share",
        type=Path,
        default=None,
        help="Carpeta del share con los soportes de la factura (HC/HEV/HAM). "
        "Útil para piloto sin tener el indice TXT armado.",
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--solo", type=str, help="Procesar solo esta factura (HUS... o número corto).")
    grupo.add_argument("--todas", action="store_true", help="Procesar todas las facturas del Excel.")
    parser.add_argument("--con-cabeza", action="store_true", help="Mostrar el browser (no headless).")
    parser.add_argument("--lento", action="store_true", help="Slow-motion 300ms (debug).")
    parser.add_argument("--reporte", type=Path, default=Path("reporte_glosa.csv"))
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()
    setup_logging(args.log)

    _exigir_playwright()
    user, password = cargar_credenciales()
    logger.info(f"Usuario SIMED: {user}")

    facturas = leer_excel_respuestas(args.excel)
    if args.solo:
        objetivo = normalizar_factura(args.solo)
        facturas = {k: v for k, v in facturas.items() if k == objetivo}
        if not facturas:
            logger.error(f"No hallé la factura {args.solo} en el Excel.")
            return 1

    indice: dict[str, Path] | None = None
    if args.indice is not None:
        indice = cargar_indice(args.indice)
        logger.info(f"Indice cargado: {len(indice):,} facturas mapeadas a soportes del share.")
    elif args.carpeta_share is not None:
        if not args.carpeta_share.is_dir():
            logger.error(f"--carpeta-share no es una carpeta accesible: {args.carpeta_share}")
            return 1
        logger.info(f"Carpeta share fija: {args.carpeta_share}")
    else:
        logger.warning("Sin --indice ni --carpeta-share: subiré sólo el PDF de Trámite por objeción.")
    if args.carpeta_share is not None and args.todas:
        logger.error("--carpeta-share sólo tiene sentido con --solo (1 factura). Para masivo usá --indice.")
        return 1
    logger.info(f"Facturas a procesar: {len(facturas)}")

    resultados: list[dict] = []
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.con_cabeza, slow_mo=300 if args.lento else 0)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()
        try:
            login(page, user, password)
            for i, (factura_corta, objeciones) in enumerate(facturas.items(), start=1):
                factura_larga = objeciones[0]["factura"]
                archivos, avisos = buscar_soportes(
                    factura_corta, factura_larga, args.soportes_glosa, indice,
                    carpeta_share_override=args.carpeta_share,
                )
                for a in avisos:
                    logger.warning(f"  ⚠ {a}")
                logger.info(
                    f"[{i}/{len(facturas)}] {factura_larga} — {len(objeciones)} objeciones, "
                    f"{len(archivos)} archivos soporte"
                )
                if not archivos:
                    resultados.append(
                        {"factura": factura_larga, "objeciones": len(objeciones),
                         "estado": "SIN_SOPORTES", "detalle": "; ".join(avisos)}
                    )
                    continue
                resultados.append(
                    procesar_factura(page, factura_corta, factura_larga, objeciones, archivos)
                )
        finally:
            browser.close()

    # Reporte CSV.
    args.reporte.parent.mkdir(parents=True, exist_ok=True)
    with args.reporte.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["factura", "objeciones", "estado", "detalle"])
        w.writeheader()
        for r in resultados:
            w.writerow(r)

    dur = (time.time() - t0) / 60
    logger.info(f"\nReporte: {args.reporte}")
    logger.info(f"Facturas procesadas: {len(resultados)} en {dur:.1f} min")
    from collections import Counter
    c = Counter(r["estado"] for r in resultados)
    for estado, n in c.items():
        logger.info(f"  {estado}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
