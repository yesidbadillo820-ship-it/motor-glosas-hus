"""responder_glosas_coosalud.py — Respuesta masiva de glosas en el portal COOSALUD (vco.ctamedicas.com).

Para cada factura del Excel consolidado (hoja BASE), agrupa las glosas por
(código de respuesta + justificación) y usa el "Responder Masivamente" del
portal: marca los checkboxes del grupo, abre el modal, selecciona el código,
pega la justificación, adjunta el PDF PDX si el grupo es de SOPORTES, confirma,
y al final le da "Terminar Respuesta" capturando el pantallazo de evidencia
("¡Usted ha cerrado una cuenta!") en la carpeta EVIDENCIA.

FLUJO POR FACTURA:
  1. Bolsa de Respuestas → Buscar la factura → botón azul ▶.
  2. Sección GLOSAS → Mostrar: Todos.
  3. Por cada grupo de respuesta del Excel (saltando las ya RESPONDIDA):
     checkboxes → Responder Masivamente → modal (código + justificación
     [+ PDF PDX para SOPORTES]) → Responder Glosa → Continuar.
  4. Cuando no quedan SIN RESPUESTA → Terminar Respuesta → "Sí, Terminar!"
     → pantallazo del cartel "¡Usted ha cerrado una cuenta!" → Continuar.

REGLA DE SOPORTES (verificada contra el Excel, 0 excepciones):
  grupo con tipo_glosa == SOPORTES ⟺ justificación contiene "ANEXA SOPORTE"
  → se adjunta el PDF tipificado PDX_*.pdf de la carpeta de la factura
  (ubicada vía el índice TXT). Si no se encuentra el PDX, el grupo se SALTA y
  la factura queda sin terminar (reportada como PENDIENTE_PDX) para no
  prometer un soporte que no se adjuntó.

CONCEPTOS DE CALIDAD (PERTINENCIA): NO se responden — la hoja CALIDAD del
Excel se ignora (sólo se lee la hoja BASE).

CREDENCIALES (variables de entorno, NO en el código):
    setx COOSALUD_USER <usuario>
    setx COOSALUD_PASSWORD <contraseña>
    (cerrar y reabrir la terminal para que tomen efecto)

USO:
    REM Piloto: una factura, browser visible
    py responder_glosas_coosalud.py ^
        --excel  "D:\\...\\CONSOLIDADO COOSALUD DIA 28.xlsx" ^
        --indice "D:\\USUARIO CARTERA\\Desktop\\BUSCADOR_HUS\\indice_facturas_HUS.txt" ^
        --solo HUS496197 --con-cabeza

    REM Masivo (140 facturas de la hoja BASE)
    py responder_glosas_coosalud.py ^
        --excel ... --indice ... --todas ^
        --reporte "D:\\...\\reporte_coosalud.csv"

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
from collections import defaultdict
from pathlib import Path

try:
    from playwright.sync_api import (
        Page,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except ImportError:
    Page = object  # type: ignore[assignment,misc]
    PlaywrightTimeout = Exception  # type: ignore[assignment,misc]
    sync_playwright = None  # type: ignore[assignment]


def _exigir_playwright() -> None:
    if sync_playwright is None:
        sys.stderr.write(
            "ERROR: falta playwright.\n"
            "    py -m pip install playwright\n"
            "    py -m playwright install chromium\n"
        )
        sys.exit(2)


PORTAL_BASE = "https://vco.ctamedicas.com"
PORTAL_LOGIN = f"{PORTAL_BASE}/app/login"
PORTAL_HOME = f"{PORTAL_BASE}/app/inicio"
PORTAL_BOLSA = f"{PORTAL_BASE}/app/respuestaGlosaSearch"

MAX_PDF_MB = 10

logger = logging.getLogger("responder_coosalud")


# ─── Setup ──────────────────────────────────────────────────────────────────


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def cargar_credenciales() -> tuple[str, str]:
    user = os.environ.get("COOSALUD_USER", "").strip()
    password = os.environ.get("COOSALUD_PASSWORD", "").strip()
    if not user or not password:
        sys.stderr.write(
            "ERROR: faltan credenciales. Setealas con:\n"
            "    setx COOSALUD_USER <usuario>\n"
            "    setx COOSALUD_PASSWORD <contraseña>\n"
            "Despues cerra y reabri la terminal.\n"
        )
        sys.exit(2)
    return user, password


# ─── Lectura del Excel consolidado (hoja BASE) ──────────────────────────────


def _norm_header(h: str) -> str:
    s = unicodedata.normalize("NFKD", (h or "").strip().upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


COLUMNAS = {
    "id_glosa": {"ID_GLOSA", "ID GLOSA"},
    "factura": {"NUMERO_FACTURA", "NUMERO FACTURA"},
    "tipo": {"TIPO_GLOSA", "TIPO GLOSA"},
    "cod_rta": {"COD RESPUESTA GLOSA", "CODIGO RESPUESTA GLOSA"},
    "obs_rta": {"OBSERVACION RTA GLOSA", "OBSERVACION RESPUESTA GLOSA"},
}


def leer_excel(ruta: Path, hoja: str) -> dict[str, dict]:
    """Devuelve {factura: {"grupos": [...], "calidad": N}} donde cada grupo es
    {cod, cod_corto, obs, ids: [id_glosa...], es_soporte: bool}.

    Las glosas con tipo_glosa == CALIDAD (pertinencia) NO se responden: se
    excluyen de los grupos y sólo se cuentan en "calidad" — esas facturas
    quedan abiertas (sin Terminar) para el equipo médico.
    Los grupos preservan el orden de aparición en el Excel."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl. py -m pip install openpyxl\n")
        sys.exit(2)

    wb = load_workbook(filename=str(ruta), data_only=True, read_only=True)
    if hoja not in wb.sheetnames:
        raise ValueError(f"El Excel no tiene la hoja '{hoja}'. Hojas: {wb.sheetnames}")
    ws = wb[hoja]
    rows = ws.iter_rows(values_only=True)
    headers = [_norm_header(str(h or "")) for h in next(rows)]

    idx: dict[str, int] = {}
    for clave, opciones in COLUMNAS.items():
        for i, h in enumerate(headers):
            if h in opciones:
                idx[clave] = i
                break
        if clave not in idx:
            raise ValueError(f"Falta la columna '{clave}' (acepto {sorted(opciones)}). Headers: {headers}")

    # factura → lista ordenada de (clave_grupo → grupo)
    grupos_por_fac: dict[str, dict] = defaultdict(dict)
    calidad_por_fac: dict[str, int] = defaultdict(int)
    for r in rows:
        if r is None:
            continue
        fac = str(r[idx["factura"]] or "").strip()
        id_glosa = str(r[idx["id_glosa"]] or "").strip()
        if not fac or not id_glosa:
            continue
        tipo = str(r[idx["tipo"]] or "").strip().upper()
        if tipo == "CALIDAD":
            calidad_por_fac[fac] += 1
            continue  # pertinencia: NO se responde
        cod = str(r[idx["cod_rta"]] or "").strip()
        obs = str(r[idx["obs_rta"]] or "").strip()
        if not cod or not obs:
            continue  # sin respuesta definida: no se puede responder
        key = (cod, obs)
        g = grupos_por_fac[fac].get(key)
        if g is None:
            m = re.match(r"([A-Z]{2}\d{4})", cod)
            g = {
                "cod": cod,
                "cod_corto": m.group(1) if m else cod[:6],
                "obs": obs,
                "ids": [],
                "es_soporte": False,
            }
            grupos_por_fac[fac][key] = g
        g["ids"].append(id_glosa)
        if tipo == "SOPORTES":
            g["es_soporte"] = True

    todas = set(grupos_por_fac) | set(calidad_por_fac)
    return {
        fac: {"grupos": list(grupos_por_fac.get(fac, {}).values()),
              "calidad": calidad_por_fac.get(fac, 0)}
        for fac in todas
    }


# ─── Índice de soportes (factura → carpeta del share) ───────────────────────


def cargar_indice(ruta: Path) -> dict[str, Path]:
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
        m = re.search(r"\\(HUS\d+)\s*$", linea, re.IGNORECASE)
        if m:
            mapa[m.group(1).upper()] = Path(linea)
    return mapa


def buscar_pdx(factura: str, indice: dict[str, Path]) -> tuple[Path | None, str]:
    """Busca el PDF tipificado PDX_*.pdf en la carpeta de la factura.
    Devuelve (ruta o None, detalle)."""
    carpeta = indice.get(factura.upper())
    if carpeta is None:
        return None, f"{factura} no está en el índice"
    if not carpeta.is_dir():
        return None, f"carpeta no accesible: {carpeta}"
    candidatos = sorted(carpeta.glob("PDX*.pdf")) or sorted(carpeta.rglob("PDX*.pdf"))
    if not candidatos:
        return None, f"sin PDX*.pdf en {carpeta}"
    pdf = candidatos[0]
    mb = pdf.stat().st_size / (1024 * 1024)
    if mb > MAX_PDF_MB:
        return None, f"{pdf.name} pesa {mb:.1f}MB (límite {MAX_PDF_MB}MB)"
    if len(candidatos) > 1:
        logger.warning(f"  ({factura}: {len(candidatos)} PDX, uso {pdf.name})")
    return pdf, pdf.name


# ─── Browser: sesión y navegación ───────────────────────────────────────────


def _screenshot_debug(page: Page, etiqueta: str) -> None:
    out = Path("debug_screenshots")
    out.mkdir(exist_ok=True)
    ruta = out / f"{time.strftime('%H%M%S')}_{etiqueta}.png"
    try:
        page.screenshot(path=str(ruta), full_page=True)
        logger.info(f"  Screenshot de diagnóstico: {ruta}")
    except Exception as e:
        logger.warning(f"  No pude tomar screenshot: {e}")


def login(page: Page, user: str, password: str) -> None:
    logger.info("Login al portal COOSALUD...")
    page.goto(PORTAL_LOGIN, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    # Si ya hay sesión (el portal redirige al home con el menú), no hay login.
    if page.locator("text=Respuesta Glosas").count() > 0:
        logger.info("Sesión ya activa.")
        return
    user_input = page.locator(
        "input[type='text']:visible, input[type='email']:visible, "
        "input[name*='user' i]:visible, input[name*='usuario' i]:visible"
    ).first
    pwd_input = page.locator("input[type='password']:visible").first
    user_input.fill(user)
    pwd_input.fill(password)
    boton = page.locator(
        "button[type='submit']:visible, input[type='submit']:visible, "
        "button:has-text('Ingresar'):visible, button:has-text('Iniciar'):visible, "
        "button:has-text('Entrar'):visible, button:has-text('Login'):visible"
    ).first
    try:
        boton.click(timeout=4000)
    except PlaywrightTimeout:
        pwd_input.press("Enter")
    # Señal de adentro: el menú lateral con "Respuesta Glosas".
    page.wait_for_selector("text=Respuesta Glosas", timeout=20000)
    logger.info("Login OK")


class FacturaNoEnBolsa(Exception):
    """La factura no aparece en la Bolsa de Respuestas (ya cerrada / no glosada)."""


# Latch global: una vez que cargamos la Bolsa por primera vez (paciente, por
# el menú), las siguientes navegaciones usan el goto directo, que es mucho
# más rápido en la sesión ya "calentada".
_BOLSA_VISITADA = False


def _esta_en_bolsa(page: Page) -> bool:
    try:
        return ("respuestaGlosaSearch" in (page.url or "")
                and page.locator("text=FILTROS BOLSA RESPUESTA").count() > 0)
    except Exception:
        return False


def ir_a_bolsa(page: Page) -> None:
    """Navega a Respuesta Glosas → Bolsa Respuesta.

    PRIMERA vez en la sesión: paciente. Vamos al home y clickeamos el menú
    lateral, esperando hasta 90s a que el datatable termine de cargar (el
    usuario confirmó que esa carga inicial es lenta).
    SIGUIENTES veces: goto directo a /respuestaGlosaSearch, que sí responde
    rápido una vez que la página ya corrió la primera vez en la sesión.
    """
    global _BOLSA_VISITADA
    if _esta_en_bolsa(page):
        return

    if _BOLSA_VISITADA:
        # Camino rápido (sesión ya calentada).
        try:
            page.goto(PORTAL_BOLSA, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeout:
            page.goto(PORTAL_BOLSA, wait_until="commit", timeout=60000)
        page.wait_for_selector("text=FILTROS BOLSA RESPUESTA", timeout=60000)
        page.wait_for_timeout(500)
        return

    # Primera vez: por el menú, con paciencia.
    try:
        page.goto(PORTAL_HOME, wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        page.goto(PORTAL_HOME, wait_until="commit", timeout=60000)
    page.wait_for_selector("text=Respuesta Glosas", timeout=30000)
    try:
        page.locator("xpath=//a[normalize-space()='Respuesta Glosas'] | "
                     "//span[normalize-space()='Respuesta Glosas']/ancestor::a[1]").first.click(timeout=5000)
    except PlaywrightTimeout:
        page.get_by_text("Respuesta Glosas").first.click()
    page.wait_for_timeout(500)
    sub = page.locator(
        "xpath=//a[contains(normalize-space(), 'Bolsa')] | "
        "//span[contains(normalize-space(), 'Bolsa')]/ancestor::a[1]"
    ).first
    # no_wait_after: el click dispara una navegación LENTA (la carga inicial
    # del datatable); si el click la espera, revienta su propio timeout.
    sub.click(timeout=10000, no_wait_after=True)
    # La PRIMERA carga del datatable puede tardar más de un minuto.
    page.wait_for_selector("text=FILTROS BOLSA RESPUESTA", timeout=120000)
    page.wait_for_timeout(1500)
    _BOLSA_VISITADA = True


def abrir_factura(page: Page, factura: str) -> None:
    """Bolsa de Respuestas → buscar la factura → click botón azul ▶."""
    ir_a_bolsa(page)
    # La caja "Buscar:" del datatable aparece recién cuando la grilla terminó
    # de cargar las facturas — y esa carga es LENTA (cartel FILTROS sale antes).
    # Esperamos con paciencia (hasta 3 min), probando los selectores en orden.
    buscar = None
    deadline = time.time() + 180
    aviso = False
    while buscar is None and time.time() < deadline:
        for sel in (
            "input[type='search']",
            "xpath=//label[contains(., 'Buscar')]//input",
            "input[placeholder*='Buscar' i]",
        ):
            loc = page.locator(sel)
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    buscar = loc.first
                    break
            except Exception:
                continue
        if buscar is None:
            if not aviso:
                logger.info("  esperando que cargue la grilla de la Bolsa (es lenta)…")
                aviso = True
            page.wait_for_timeout(1500)
    if buscar is None:
        _screenshot_debug(page, "sin_caja_buscar")
        raise RuntimeError("La grilla de la Bolsa no cargó en 3 min (sin caja 'Buscar:').")
    buscar.fill(factura)
    page.wait_for_timeout(1200)  # debounce del datatable

    fila = page.locator(f"tr:has-text('{factura}')").first
    inicio = time.time()
    while True:
        try:
            if fila.is_visible():
                break
        except Exception:
            pass
        if time.time() - inicio > 8:
            raise FacturaNoEnBolsa(f"{factura} no aparece en la Bolsa de Respuestas (¿ya cerrada?).")
        page.wait_for_timeout(300)

    boton = fila.locator("button, a").last  # botón azul ▶ en OPCIONES
    boton.click()
    # Página de detalle: aparece la sección GLOSAS.
    page.wait_for_selector("text=GLOSAS", timeout=25000)
    page.wait_for_timeout(800)


def preparar_grilla(page: Page) -> None:
    """Pone 'Mostrar: Todos' en la sección GLOSAS (hay facturas de 800+ glosas)."""
    candidatos = (
        "xpath=//*[contains(text(),'GLOSAS')]/following::select[1]",
        "select[name*='length']",
        "select",
    )
    for sel in candidatos:
        loc = page.locator(sel)
        try:
            n = loc.count()
        except Exception:
            continue
        for i in range(min(n, 6)):
            s = loc.nth(i)
            try:
                if not s.is_visible():
                    continue
                opciones = s.locator("option").all_inner_texts()
                if any("Todos" in o for o in opciones):
                    s.select_option(label=next(o for o in opciones if "Todos" in o))
                    page.wait_for_timeout(800)
                    return
            except Exception:
                continue
    # Algunos datatables ya vienen en 'Todos' (como en los pantallazos).
    logger.info("  (no pude setear Mostrar=Todos; sigo con lo visible)")


def leer_estados(page: Page) -> dict[str, str]:
    """Devuelve {id_glosa: estado} de la grilla GLOSAS ('SIN RESPUESTA'/'RESPONDIDA')."""
    estados: dict[str, str] = {}
    datos = page.evaluate(
        """() => {
            const out = [];
            for (const tr of document.querySelectorAll('tr')) {
                const tds = tr.querySelectorAll('td');
                if (tds.length < 5) continue;
                const id = (tds[0].innerText || '').trim();
                if (!/^\\d{6,}$/.test(id)) continue;
                const texto = (tr.innerText || '').toUpperCase();
                let estado = '';
                if (texto.includes('SIN RESPUESTA')) estado = 'SIN RESPUESTA';
                else if (texto.includes('RESPONDIDA')) estado = 'RESPONDIDA';
                if (estado) out.push([id, estado]);
            }
            return out;
        }"""
    )
    for id_glosa, estado in datos:
        estados[id_glosa] = estado
    return estados


def _contar_marcadas(page: Page) -> int:
    try:
        return page.evaluate(
            "() => document.querySelectorAll(\"tbody input[type='checkbox']:checked\").length"
        )
    except Exception:
        return 0


def marcar_checkboxes(page: Page, ids: list[str], todas_pendientes: bool) -> int:
    """Marca los checkboxes de las glosas `ids` y devuelve cuántas quedaron
    marcadas (verificado contando en el DOM).

    El JS del portal maneja el estado de los checkboxes a su manera, así que
    NO usamos check()/uncheck() (su verificación estricta revienta con
    'Clicking the checkbox did not change its state'): clickeamos sin
    verificación y validamos nosotros contando los marcados."""
    if todas_pendientes:
        maestro = page.locator("thead input[type='checkbox']").last
        if maestro.count() > 0:
            maestro.click(force=True)
            page.wait_for_timeout(700)
            if _contar_marcadas(page) >= len(ids):
                return len(ids)
            logger.info("  (checkbox maestro no marcó todo; voy fila por fila)")
    marcadas = 0
    for id_glosa in ids:
        fila = page.locator(f"tr:has(td:text-is('{id_glosa}'))").first
        try:
            cb = fila.locator("input[type='checkbox']").last
            if cb.evaluate("el => el.checked"):
                marcadas += 1
                continue
            cb.click(force=True, timeout=3000)
            page.wait_for_timeout(60)
            if cb.evaluate("el => el.checked"):
                marcadas += 1
                continue
            # Último recurso: setear el estado y disparar los eventos que
            # escucha el framework del portal.
            cb.evaluate(
                "el => { el.checked = true;"
                " el.dispatchEvent(new Event('click', {bubbles: true}));"
                " el.dispatchEvent(new Event('change', {bubbles: true})); }"
            )
            if cb.evaluate("el => el.checked"):
                marcadas += 1
        except Exception as e:
            logger.warning(f"  no pude marcar id_glosa {id_glosa}: {e}")
    page.wait_for_timeout(300)
    return marcadas


def _desmarcar_todo(page: Page) -> None:
    """Desmarca todos los checkboxes de la grilla clickeando los marcados
    (sin uncheck(): misma incompatibilidad que check())."""
    try:
        for _ in range(3):
            if _contar_marcadas(page) == 0:
                return
            page.evaluate(
                """() => { for (const cb of document.querySelectorAll("tbody input[type='checkbox']:checked")) cb.click(); }"""
            )
            page.wait_for_timeout(300)
    except Exception:
        pass


def responder_grupo(page: Page, grupo: dict, pdf: Path | None) -> None:
    """Abre el modal 'Responder Masivamente' y carga código + justificación
    (+ PDF si aplica). Lanza excepción si el portal no confirma."""
    page.locator("button:has-text('Responder Masivamente')").first.click()
    page.wait_for_selector("text=Respondiendo Masivamente", timeout=15000)

    # ── Código de respuesta (dropdown, posiblemente select2) ──
    cod = grupo["cod_corto"]
    seleccionado = False
    # 1) <select> nativo (aunque esté estilizado, select_option suele funcionar).
    for sel in page.locator("select").all():
        try:
            opciones = sel.locator("option").all_inner_texts()
            match = next((o for o in opciones if cod in o), None)
            if match:
                sel.select_option(label=match)
                seleccionado = True
                break
        except Exception:
            continue
    # 2) Combo select2: click + tipear + Enter. (No mezclar CSS y XPath en
    # un mismo selector: se prueban en orden.)
    if not seleccionado:
        combo = None
        for sel_combo in (
            ".select2-selection",
            "[role='combobox']",
            "xpath=//*[contains(text(),'RESPUESTA')]/following::span[contains(@class,'select2')][1]",
        ):
            loc = page.locator(sel_combo)
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    combo = loc.first
                    break
            except Exception:
                continue
        if combo is None:
            raise RuntimeError("No encontré el dropdown de RESPUESTA en el modal.")
        combo.click()
        page.wait_for_timeout(400)
        caja = page.locator("input.select2-search__field:visible, input[type='search']:visible").last
        caja.fill(cod)
        page.wait_for_timeout(800)
        page.locator(f"li:has-text('{cod}')").first.click()
        seleccionado = True
    page.wait_for_timeout(500)

    # ── Justificación (textarea) — el portal ACEPTA tildes, va tal cual ──
    textarea = page.locator("textarea:visible").first
    textarea.fill(grupo["obs"])

    # ── PDF (solo grupos de soporte) ──
    if pdf is not None:
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(str(pdf))
        page.wait_for_timeout(800)
        logger.info(f"    adjunto: {pdf.name}")

    # ── Responder Glosa ──
    page.locator("button:has-text('Responder Glosa')").first.click()
    # Confirmación: "¡Se ha dado Respuesta a N Glosas!"
    page.wait_for_selector("text=Se ha dado Respuesta", timeout=40000)
    page.locator("button:has-text('Continuar')").first.click()
    page.wait_for_timeout(800)


def terminar_respuesta(page: Page, factura: str, evidencias: Path) -> str:
    """Click 'Terminar Respuesta' → 'Sí, Terminar!' → pantallazo del cartel
    '¡Usted ha cerrado una cuenta!' en EVIDENCIA → Continuar."""
    evidencias.mkdir(parents=True, exist_ok=True)
    page.locator("button:has-text('Terminar Respuesta')").first.click()
    page.wait_for_selector("text=Desea Terminar", timeout=15000)
    page.locator("button:has-text('Terminar!'), button:has-text('Si, Terminar')").first.click()

    # Cartel final de evidencia.
    try:
        page.wait_for_selector("text=ha cerrado una cuenta", timeout=30000)
    except PlaywrightTimeout:
        _screenshot_debug(page, f"sin_cartel_cierre_{factura}")
        return "TERMINADA_SIN_CARTEL"
    ruta = evidencias / f"{factura}_cierre.png"
    page.screenshot(path=str(ruta), full_page=True)
    logger.info(f"  📸 Evidencia: {ruta}")
    try:
        page.locator("button:has-text('Continuar')").first.click(timeout=5000)
    except PlaywrightTimeout:
        pass
    return "OK"


# ─── Driver por factura ─────────────────────────────────────────────────────


def procesar_factura(
    page: Page,
    factura: str,
    grupos: list[dict],
    calidad: int,
    indice: dict[str, Path],
    evidencias: Path,
    max_grupos: int = 0,
) -> dict:
    total_glosas = sum(len(g["ids"]) for g in grupos)
    reg = {"factura": factura, "grupos": len(grupos), "glosas": total_glosas,
           "estado": "", "detalle": ""}
    try:
        abrir_factura(page, factura)
        preparar_grilla(page)
        estados = leer_estados(page)

        respondidas_previas = sum(1 for e in estados.values() if e == "RESPONDIDA")
        pendientes_portal = {i for i, e in estados.items() if e == "SIN RESPUESTA"}
        logger.info(
            f"  portal: {len(estados)} glosas en grilla, "
            f"{respondidas_previas} ya respondidas, {len(pendientes_portal)} pendientes"
        )

        grupos_hechos = 0
        grupos_saltados_pdx: list[str] = []
        a_procesar = grupos[:max_grupos] if max_grupos > 0 else grupos
        for n, g in enumerate(a_procesar, start=1):
            ids_pend = [i for i in g["ids"] if i in pendientes_portal]
            if not ids_pend:
                logger.info(f"  grupo {n}/{len(grupos)}: ya respondido → omito")
                continue

            pdf = None
            if g["es_soporte"]:
                pdf, detalle_pdx = buscar_pdx(factura, indice)
                if pdf is None:
                    logger.warning(f"  grupo {n} es SOPORTES pero {detalle_pdx} → SALTO el grupo")
                    grupos_saltados_pdx.append(detalle_pdx)
                    continue

            logger.info(
                f"  → grupo {n}/{len(grupos)}: {len(ids_pend)} glosas, cod {g['cod_corto']}"
                + (" + PDF" if pdf else "")
            )
            todas = set(ids_pend) == pendientes_portal
            marcadas = marcar_checkboxes(page, ids_pend, todas_pendientes=todas)
            if marcadas == 0:
                raise RuntimeError(f"no pude marcar ningún checkbox del grupo {n}")
            responder_grupo(page, g, pdf)
            grupos_hechos += 1
            pendientes_portal -= set(ids_pend)
            _desmarcar_todo(page)

        if max_grupos > 0:
            reg["estado"] = "PILOTO_PARCIAL"
            reg["detalle"] = f"{grupos_hechos} grupos respondidos (sin Terminar)"
            return reg

        # ¿Quedó algo sin responder?
        estados = leer_estados(page)
        aun_pendientes = sum(1 for e in estados.values() if e == "SIN RESPUESTA")
        if grupos_saltados_pdx:
            reg["estado"] = "PENDIENTE_PDX"
            reg["detalle"] = f"{grupos_hechos} grupos ok; sin PDX: {'; '.join(grupos_saltados_pdx)}"
            return reg
        if calidad > 0:
            # Los conceptos CALIDAD no se responden: la factura queda ABIERTA
            # (sin Terminar) para que el equipo médico maneje la pertinencia.
            reg["estado"] = "OK_CALIDAD_ABIERTA"
            reg["detalle"] = (
                f"{grupos_hechos} grupos respondidos; {calidad} glosas CALIDAD no se "
                f"responden (portal muestra {aun_pendientes} sin respuesta); queda SIN Terminar"
            )
            return reg
        if aun_pendientes:
            reg["estado"] = "PENDIENTES"
            reg["detalle"] = (
                f"{grupos_hechos} grupos ok, pero el portal aún muestra {aun_pendientes} "
                "SIN RESPUESTA (glosas del portal que no están en el Excel)"
            )
            return reg

        estado_fin = terminar_respuesta(page, factura, evidencias)
        reg["estado"] = estado_fin
        reg["detalle"] = f"{grupos_hechos} grupos respondidos, evidencia capturada"
    except FacturaNoEnBolsa as e:
        reg["estado"] = "NO_EN_BOLSA"
        reg["detalle"] = str(e)
        logger.info(f"  ⏭ {e}")
    except Exception as e:
        reg["estado"] = "ERROR"
        reg["detalle"] = f"{type(e).__name__}: {e}"
        logger.error(f"  ✗ {factura}: {reg['detalle']}")
        _screenshot_debug(page, f"error_{factura}")
    return reg


# ─── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Respuesta masiva de glosas en COOSALUD (vco.ctamedicas.com).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--excel", type=Path, required=True, help="Excel consolidado de glosas COOSALUD.")
    parser.add_argument("--hoja", type=str, default="BASE", help="Hoja a procesar (default BASE; CALIDAD no se responde).")
    parser.add_argument("--indice", type=Path, default=None, help="TXT índice factura→carpeta (para el PDX de SOPORTES).")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--solo", type=str, help="Procesar solo esta factura (HUS...).")
    grupo.add_argument("--todas", action="store_true", help="Procesar todas las facturas de la hoja.")
    parser.add_argument("--max-grupos", type=int, default=0, help="Responder como mucho N grupos (piloto; no Termina la factura).")
    parser.add_argument("--evidencias", type=Path, default=Path("EVIDENCIA"), help="Carpeta para los pantallazos de cierre (default: EVIDENCIA).")
    parser.add_argument("--con-cabeza", action="store_true", help="Mostrar el browser.")
    parser.add_argument("--lento", action="store_true", help="Slow-motion 300ms (debug).")
    parser.add_argument("--reporte", type=Path, default=Path("reporte_coosalud.csv"))
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()
    setup_logging(args.log)

    _exigir_playwright()
    user, password = cargar_credenciales()
    logger.info(f"Usuario COOSALUD: {user}")

    facturas = leer_excel(args.excel, args.hoja)
    tot_glosas = sum(len(g["ids"]) for f in facturas.values() for g in f["grupos"])
    tot_calidad = sum(f["calidad"] for f in facturas.values())
    logger.info(f"Hoja {args.hoja}: {len(facturas)} facturas, {tot_glosas:,} glosas a responder"
                + (f" (+{tot_calidad} CALIDAD excluidas)" if tot_calidad else "") + ".")

    if args.solo:
        objetivo = args.solo.strip().upper()
        facturas = {k: v for k, v in facturas.items() if k.upper() == objetivo}
        if not facturas:
            logger.error(f"No hallé la factura {args.solo} en la hoja {args.hoja}.")
            return 1

    indice: dict[str, Path] = {}
    if args.indice is not None:
        indice = cargar_indice(args.indice)
        logger.info(f"Índice cargado: {len(indice):,} facturas mapeadas.")
    else:
        n_sop = sum(1 for f in facturas.values() for g in f["grupos"] if g["es_soporte"])
        if n_sop:
            logger.warning(f"⚠ Sin --indice: {n_sop} grupos de SOPORTES quedarán PENDIENTE_PDX.")

    # Reporte CSV incremental (append-as-you-go).
    args.reporte.parent.mkdir(parents=True, exist_ok=True)
    f_rep = args.reporte.open("w", newline="", encoding="utf-8-sig")
    w_rep = csv.DictWriter(f_rep, fieldnames=["factura", "grupos", "glosas", "estado", "detalle"])
    w_rep.writeheader()
    resultados: list[dict] = []

    def registrar(reg: dict) -> None:
        resultados.append(reg)
        w_rep.writerow(reg)
        if len(resultados) % 5 == 0:
            f_rep.flush()

    def _sesion_muerta(detalle: str) -> bool:
        d = detalle.lower()
        return ("target page, context or browser has been closed" in d
                or "target closed" in d or "browser has been closed" in d
                or "connection closed" in d or "targetclosederror" in d)

    def _abrir_sesion(p):
        b = p.chromium.launch(headless=not args.con_cabeza, slow_mo=300 if args.lento else 0)
        c = b.new_context(accept_downloads=True)
        pg = c.new_page()
        pg.on("dialog", lambda d: d.accept())
        login(pg, user, password)
        return b, c, pg

    t0 = time.time()
    with sync_playwright() as p:
        browser, ctx, page = _abrir_sesion(p)
        relogins = 0
        MAX_RELOGINS = 5
        try:
            for i, (factura, datos) in enumerate(facturas.items(), start=1):
                grupos = datos["grupos"]
                calidad = datos["calidad"]
                extra = f" (+{calidad} CALIDAD excluidas)" if calidad else ""
                logger.info(f"[{i}/{len(facturas)}] {factura} — {len(grupos)} grupo(s), "
                            f"{sum(len(g['ids']) for g in grupos)} glosas{extra}")
                if not grupos:
                    registrar({"factura": factura, "grupos": 0, "glosas": 0,
                               "estado": "SOLO_CALIDAD",
                               "detalle": f"{calidad} glosas CALIDAD; nada que responder"})
                    continue
                for intento in range(2):
                    reg = procesar_factura(page, factura, grupos, calidad, indice,
                                           args.evidencias, max_grupos=args.max_grupos)
                    if reg["estado"] == "ERROR" and _sesion_muerta(reg["detalle"]):
                        if relogins >= MAX_RELOGINS:
                            logger.error("Sesión irrecuperable; re-corré el comando para continuar.")
                            registrar(reg)
                            raise RuntimeError("Sesión irrecuperable")
                        relogins += 1
                        logger.warning(f"  ⚠ Sesión caída. Re-login {relogins}/{MAX_RELOGINS}…")
                        try:
                            browser.close()
                        except Exception:
                            pass
                        browser, ctx, page = _abrir_sesion(p)
                        continue
                    registrar(reg)
                    break
        except RuntimeError:
            pass
        finally:
            try:
                browser.close()
            except Exception:
                pass
            f_rep.close()

    dur = (time.time() - t0) / 60
    logger.info(f"\nReporte: {args.reporte}")
    logger.info(f"Evidencias: {args.evidencias}")
    logger.info(f"Facturas procesadas: {len(resultados)} en {dur:.1f} min")
    from collections import Counter
    for estado, n in Counter(r["estado"] for r in resultados).items():
        logger.info(f"  {estado}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
