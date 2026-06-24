"""responder_glosas_fomag.py — Respuesta de glosas RATIFICADAS en FOMAG (Horus Health).

Portal: https://horus2.horus-health.com  (administrado por Fiduprevisora).

FLUJO EN LA WEB (verificado con pantallazos):

  1. Login: email + contraseña + reCAPTCHA "No soy un robot" + botón INGRESAR.
     OJO: el reCAPTCHA NO se puede resolver de forma desatendida. Por eso el bot
     usa un PERFIL DE NAVEGADOR PERSISTENTE: la primera vez corrés con
     --con-cabeza, resolvés el captcha vos a mano, y la sesión queda guardada en
     disco. Las siguientes corridas reusan esa sesión (mientras no expire) y ya
     no piden captcha.

  2. Menú: Cuentas médicas → Auditoría  (URL /cuentasMedicas/auditoria).

  3. Cuadro naranja "Facturas prestador": se clickea para desplegar las
     pestañas con contadores:
       RADICADAS · PENDIENTES · RATIFICADAS · CONCILIACIÓN · CONSOLIDADO ·
       HISTÓRICO CONCILIACIÓN

  4. Pestaña RATIFICADAS (default). Por cada factura:
       a) Escribir la factura en "Número factura" → botón FILTRAR.
       b) Click en el botón verde "RESPUESTA" de la fila.
       c) Se abre el formulario "Respuesta" (1 fila por servicio glosado). Por
          cada fila, EN ESTE ORDEN:
            - "Cod Rta2 RAT" (dropdown): elegir RE9901.
            - "Detalle Rta 2 prestador" (lápiz ✏️): cargar el texto de respuesta.
            - "Archivo": subir el PDF <factura>.pdf  (ANTES del ✓: una vez
              guardada la fila queda bloqueada y el botón de Archivo se apaga).
            - Guardar la fila con el ✓ ("chulito") → cartel "Respuesta guardada
              con exito!".
       d) Pantallazo de evidencia ANTES de que cierre la página.
       e) "GUARDAR RESPUESTA" (botón verde, arriba a la derecha) → vuelve a la
          grilla.

RESPUESTA ESTÁNDAR (igual para todas las ratificadas, salvo --cod/--texto-archivo):
  Código  : RE9901  ("la glosa siendo justificada ha podido ser subsanada
            totalmente" → el HUS no acepta la glosa ratificada y mantiene la
            objeción / pide conciliación).
  Detalle : el texto fijo TEXTO_RATIFICADA_DEFAULT (ver abajo).

CREDENCIALES (variables de entorno, NUNCA en el código ni en el comando):
    setx FOMAG_USER 1098612385@fomag.com
    setx FOMAG_PASSWORD <contraseña>
    (cerrar y reabrir la terminal para que las tome)

USO:
    REM 1) Primera corrida del día: iniciar sesión a mano (resolvés el captcha)
    py responder_glosas_fomag.py --listar --con-cabeza

    REM 2) PILOTO seguro: carga código + detalle + PDF pero NO guarda nada
    py responder_glosas_fomag.py --responder --solo HUS511575 ^
        --pdf-dir "D:\\...\\FOMAG\\GLOSAS\\2026\\5-JUNIO\\PDF" ^
        --con-cabeza --sin-guardar

    REM 3) Responder UNA factura de verdad (con browser visible para mirar)
    py responder_glosas_fomag.py --responder --solo HUS511575 ^
        --pdf-dir "D:\\...\\FOMAG\\GLOSAS\\2026\\5-JUNIO\\PDF" --con-cabeza

    REM 4) Lote: varias facturas
    py responder_glosas_fomag.py --responder ^
        --lista "D:\\FOMAG\\ratificadas.txt" ^
        --pdf-dir "D:\\...\\FOMAG\\GLOSAS\\2026\\5-JUNIO\\PDF" ^
        --reporte "D:\\FOMAG\\reporte_ratificadas.csv"

    REM Inventario de la pestaña a CSV (read-only)
    py responder_glosas_fomag.py --listar --reporte "D:\\FOMAG\\ratificadas.csv"

INSTALACIÓN (una vez):
    py -m pip install playwright openpyxl
    py -m playwright install chromium
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
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


PORTAL_BASE = "https://horus2.horus-health.com"
PORTAL_LOGIN = f"{PORTAL_BASE}/"
PORTAL_AUDITORIA = f"{PORTAL_BASE}/cuentasMedicas/auditoria"

# Pestañas de "Facturas prestador" (texto normalizado → texto del match laxo).
TABS = {
    "RADICADAS": "RADICADAS",
    "PENDIENTES": "PENDIENTES",
    "RATIFICADAS": "RATIFICADAS",
    "CONCILIACION": "CONCILIACION",
    "CONSOLIDADO": "CONSOLIDADO",
    "HISTORICO": "HISTORICO",
}

# Código de respuesta por default para ratificadas: el HUS no acepta la glosa
# ratificada (la glosa, siendo justificada, pudo ser subsanada totalmente).
COD_RTA2_DEFAULT = "RE9901"

# Texto fijo de respuesta a la ratificada (transcrito del portal HUS). El portal
# acepta tildes/ñ, así que va tal cual.
TEXTO_RATIFICADA_DEFAULT = (
    "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN "
    "TRÁMITE DE LA GLOSA INICIAL Y SE DA CONTINUACIÓN AL PROCESO DE CONFORMIDAD "
    "CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 Y EL ARTÍCULO 20 DEL DECRETO "
    "4747 DE 2007. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE CONCILIACIÓN DE "
    "AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. DE NO LLEGARSE A ACUERDO, "
    "SE ELEVARÁ EL CONFLICTO ANTE LA SUPERINTENDENCIA NACIONAL DE SALUD SEGÚN "
    "LO DISPUESTO EN EL ART. 126 DE LA LEY 1438/2011. CUALQUIER INFORMACIÓN AL "
    "CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO, "
    "GLOSASYDEVOLUCIONES@HUS.GOV.CO, VENTANILLA ÚNICA DE LA ESE HUS CARRERA 33 "
    "NO. 28-126. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, DE "
    "NO OBTENERSE RESPUESTA A LA GLOSA RATIFICADA EN LOS TÉRMINOS ESTABLECIDOS, "
    "SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN."
)

# Perfil de navegador persistente por default: guarda cookies/sesión para no
# tener que resolver el reCAPTCHA en cada corrida.
PERFIL_DEFAULT = Path.home() / ".fomag_horus_profile"

logger = logging.getLogger("responder_fomag")


# ─── Setup ──────────────────────────────────────────────────────────────────


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def cargar_credenciales() -> tuple[str, str]:
    user = os.environ.get("FOMAG_USER", "").strip()
    password = os.environ.get("FOMAG_PASSWORD", "").strip()
    if not user or not password:
        sys.stderr.write(
            "ERROR: faltan credenciales. Setealas con:\n"
            "    setx FOMAG_USER 1098612385@fomag.com\n"
            "    setx FOMAG_PASSWORD <contraseña>\n"
            "Despues cerra y reabri la terminal.\n"
        )
        sys.exit(2)
    return user, password


# ─── Helpers de texto / DOM ─────────────────────────────────────────────────


def _norm(s: str) -> str:
    """Mayúsculas, sin tildes ni combinantes, espacios colapsados."""
    s = unicodedata.normalize("NFKD", (s or "").strip().upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def _norm_col(s: str) -> str:
    """Como _norm pero sin puntuación ni espacios — para matchear encabezados:
    'Cod Rta2 RAT' → 'CODRTA2RAT', 'Detalle Rta 2 prestador' → 'DETALLERTA2PRESTADOR'."""
    base = _norm(s)
    return "".join(c for c in base if c.isalnum())


def _primer_visible(loc):
    """Primer elemento VISIBLE de un locator, o None (los .first a secas pueden
    agarrar plantillas ocultas del DOM)."""
    try:
        n = loc.count()
    except Exception:
        return None
    for i in range(n):
        e = loc.nth(i)
        try:
            if e.is_visible():
                return e
        except Exception:
            continue
    return None


def _screenshot_debug(page: Page, etiqueta: str) -> Path | None:
    out = Path("debug_screenshots")
    out.mkdir(exist_ok=True)
    ruta = out / f"{time.strftime('%H%M%S')}_{etiqueta}.png"
    try:
        page.screenshot(path=str(ruta), full_page=True)
        logger.info(f"  📸 Screenshot de diagnóstico: {ruta}")
        return ruta
    except Exception as e:
        logger.warning(f"  No pude tomar screenshot: {e}")
        return None


# ─── Login (perfil persistente + reCAPTCHA manual) ──────────────────────────


def _en_login(page: Page) -> bool:
    """True si estamos en la pantalla de LOGIN. Se detecta por el campo de
    contraseña + botón INGRESAR / 'RECUPERAR CONTRASEÑA' (solo existen acá).
    OJO: la pantalla de login dice 'Bienvenido' igual que el header de adentro,
    así que ese texto NO sirve para detectar sesión."""
    try:
        if page.locator("text=/RECUPERAR CONTRASE/i").count() > 0:
            return True
        pwd = _primer_visible(page.locator("input[type='password']"))
        ingresar = _primer_visible(page.locator(
            "button:has-text('INGRESAR'), button:has-text('Ingresar'), input[type='submit']"
        ))
        if pwd is not None and ingresar is not None:
            return True
    except Exception:
        pass
    return False


def _logueado(page: Page) -> bool:
    """True si estamos DENTRO del portal (no en la pantalla de login)."""
    if _en_login(page):
        return False
    try:
        url = page.url or ""
        if any(s in url for s in ("/inicio", "/cuentasMedicas", "/aseguramiento",
                                  "/historicos", "/rips", "/solicitudes")):
            return True
        # Ítems del menú lateral que sólo existen ya adentro.
        for t in ("Cuentas medicas", "Aseguramiento", "Informe prestador"):
            if page.get_by_text(t, exact=False).count() > 0:
                return True
    except Exception:
        pass
    return False


def login(page: Page, user: str, password: str, timeout_login_s: int = 240) -> None:
    """Inicia sesión en Horus. Si el perfil persistente ya tiene sesión válida,
    no hace nada. Si no, completa email + contraseña y ESPERA a que el humano
    resuelva el reCAPTCHA y la página entre (el captcha no se automatiza)."""
    logger.info("Abriendo el portal FOMAG (Horus)…")
    try:
        page.goto(PORTAL_LOGIN, wait_until="domcontentloaded", timeout=90000)
    except PlaywrightTimeout:
        page.goto(PORTAL_LOGIN, wait_until="commit", timeout=90000)
    page.wait_for_timeout(2500)

    if _logueado(page):
        logger.info("Sesión ya activa (perfil persistente). No hace falta login.")
        return

    email = _primer_visible(page.locator(
        "input[type='email'], input[type='text'], "
        "input[name*='user' i], input[name*='mail' i], input[formcontrolname*='user' i]"
    ))
    pwd = _primer_visible(page.locator("input[type='password']"))
    if email is not None and pwd is not None:
        try:
            email.click()
            email.fill(user)
            pwd.click()
            pwd.fill(password)
            # Disparar input/change/blur para que el form de Angular registre
            # los valores y habilite INGRESAR.
            for campo in (email, pwd):
                try:
                    campo.evaluate(
                        "el => { el.dispatchEvent(new Event('input', {bubbles:true}));"
                        " el.dispatchEvent(new Event('change', {bubbles:true}));"
                        " el.dispatchEvent(new Event('blur', {bubbles:true})); }"
                    )
                except Exception:
                    pass
            logger.info("  Email y contraseña cargados.")
        except Exception as e:
            logger.warning(f"  No pude autollenar el formulario ({e}); completalo a mano.")
    else:
        logger.warning("  No encontré los campos de login; completá email y contraseña a mano.")

    logger.info(
        "\n  👉 RESOLVÉ el reCAPTCHA ('No soy un robot') y hacé clic en INGRESAR "
        "en la ventana del browser.\n"
        f"     (El captcha no se automatiza; te espero hasta {timeout_login_s}s.)\n"
    )

    deadline = time.time() + timeout_login_s
    while time.time() < deadline:
        if _logueado(page):
            logger.info("Login OK — sesión iniciada.")
            page.wait_for_timeout(1500)
            return
        page.wait_for_timeout(1000)
    _screenshot_debug(page, "login_no_completado")
    raise RuntimeError(
        f"No se completó el login en {timeout_login_s}s. Corré con --con-cabeza, "
        "resolvé el captcha y dale INGRESAR."
    )


# ─── Navegación a la grilla (Auditoría → cuadro naranja → pestaña) ──────────


def _pestanas_visibles(page: Page) -> bool:
    """True si hay una pestaña RATIFICADAS/RADICADAS VISIBLE (no oculta en el DOM)."""
    return (_primer_visible(page.get_by_text("RATIFICADAS", exact=False)) is not None
            or _primer_visible(page.get_by_text("RADICADAS", exact=False)) is not None)


def _abrir_facturas_prestador(page: Page) -> None:
    """Clickea el cuadro naranja 'Facturas prestador' para desplegar las
    pestañas. Idempotente: si ya hay una pestaña VISIBLE, no hace nada.

    El handler de click suele estar en el contenedor del card, no en el <span>
    del texto, así que probamos el texto y sus ancestros hasta que aparezcan
    las pestañas."""
    if _pestanas_visibles(page):
        return
    # Esperar a que el cuadro naranja aparezca (el SPA puede tardar).
    caja = None
    deadline = time.time() + 20
    while time.time() < deadline:
        caja = (
            _primer_visible(page.get_by_text("Facturas prestador", exact=False))
            or _primer_visible(page.get_by_text("Factures prestador", exact=False))
        )
        if caja is not None:
            break
        page.wait_for_timeout(700)
    if caja is None:
        _screenshot_debug(page, "sin_cuadro_naranja")
        raise RuntimeError("No encontré el cuadro 'Facturas prestador'.")

    # Candidatos a clickear: el texto y sus contenedores (a/button/div padre).
    candidatos = [caja]
    for xp in ("xpath=ancestor-or-self::a[1]", "xpath=ancestor-or-self::button[1]",
               "xpath=ancestor::div[1]", "xpath=ancestor::div[2]"):
        try:
            c = _primer_visible(caja.locator(xp))
            if c is not None:
                candidatos.append(c)
        except Exception:
            continue

    for cand in candidatos:
        try:
            cand.click(timeout=4000)
        except Exception:
            continue
        fin = time.time() + 6
        while time.time() < fin:
            if _pestanas_visibles(page):
                page.wait_for_timeout(600)
                return
            page.wait_for_timeout(400)
    _screenshot_debug(page, "tabs_no_aparecen")
    raise RuntimeError("Clickeé 'Facturas prestador' pero no aparecieron las pestañas.")


def _click_tab(page: Page, tab_label: str) -> None:
    """Clickea la pestaña pedida (RADICADAS / RATIFICADAS / …)."""
    objetivo = _norm(tab_label)
    candidatos = page.locator("a, li, span, button, div")
    n = min(candidatos.count(), 500)
    for i in range(n):
        el = candidatos.nth(i)
        try:
            if not el.is_visible():
                continue
            t = _norm(el.inner_text())
            # Match por prefijo (el texto puede traer el contador pegado:
            # "RATIFICADAS42") evitando el ítem de menú lateral.
            if t.startswith(objetivo) and len(t) <= len(objetivo) + 8:
                el.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue
    _screenshot_debug(page, f"sin_pestana_{objetivo}")
    raise RuntimeError(f"No encontré la pestaña '{tab_label}'.")


def _senal_auditoria(page: Page) -> bool:
    """True si hay alguna señal de la vista de Auditoría de facturas (cuadro
    naranja, pestañas, o el título — tolerante a tildes)."""
    for txt in ("Facturas prestador", "Factures prestador", "RATIFICADAS", "RADICADAS"):
        try:
            if page.get_by_text(txt, exact=False).count() > 0:
                return True
        except Exception:
            pass
    try:
        if page.locator("text=/AUDITOR[IÍ]A DE FACTURAS/i").count() > 0:
            return True
    except Exception:
        pass
    return False


def _esperar_auditoria(page: Page, timeout_s: int = 30) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _senal_auditoria(page):
            return True
        page.wait_for_timeout(800)
    return False


def _navegar_por_menu(page: Page) -> None:
    """Fallback: Cuentas médicas → Auditoría por el menú lateral (cuando el
    goto directo a la URL no rinde la vista)."""
    try:
        cm = (_primer_visible(page.locator("text=/Cuentas m[eé]dicas/i"))
              or _primer_visible(page.get_by_text("Cuentas medicas", exact=False)))
        if cm is not None:
            cm.click()
            page.wait_for_timeout(800)
        aud = (_primer_visible(page.locator("text=/Auditor[ií]a/i"))
               or _primer_visible(page.get_by_text("Auditoria", exact=False)))
        if aud is not None:
            aud.click()
            page.wait_for_timeout(1800)
    except Exception as e:
        logger.info(f"  no pude navegar por el menú lateral: {e}")


def _ir_a_auditoria(page: Page) -> None:
    """Carga la vista de Auditoría de facturas: prueba el goto directo y, si la
    vista no aparece, navega por el menú lateral. Lanza si ninguna funciona."""
    try:
        page.goto(PORTAL_AUDITORIA, wait_until="domcontentloaded", timeout=90000)
    except PlaywrightTimeout:
        page.goto(PORTAL_AUDITORIA, wait_until="commit", timeout=90000)
    if _esperar_auditoria(page, timeout_s=25):
        return
    logger.info("  la vista de Auditoría no apareció con la URL directa; pruebo el menú lateral…")
    _navegar_por_menu(page)
    if _esperar_auditoria(page, timeout_s=25):
        return
    _screenshot_debug(page, "sin_auditoria")
    cuerpo = ""
    try:
        cuerpo = " ".join((page.inner_text("body") or "").split())[:400]
    except Exception:
        pass
    raise RuntimeError(
        f"No cargó la vista de Auditoría de facturas (URL {page.url}). "
        f"Texto visible: {cuerpo!r}"
    )


def ir_a_pestana(page: Page, tab_label: str) -> None:
    """Navega Auditoría → cuadro naranja → pestaña pedida y espera la grilla."""
    logger.info(f"Navegando a Auditoría → Facturas prestador → {tab_label}…")
    _ir_a_auditoria(page)
    page.wait_for_timeout(500)
    _abrir_facturas_prestador(page)
    _click_tab(page, tab_label)
    # No bloqueamos en la grilla sin filtrar (puede venir vacía hasta filtrar);
    # el filtro por factura ya espera la fila con su propio poll.
    try:
        page.wait_for_selector("table tbody tr, button:has-text('RESPUESTA'), "
                               "input", timeout=15000)
    except PlaywrightTimeout:
        logger.info("  (la grilla tardó; sigo con lo visible)")
    page.wait_for_timeout(600)


# ─── Lectura de la grilla de facturas ───────────────────────────────────────


def _dump_inputs(page: Page) -> None:
    """Vuelca los inputs visibles (tag/type/name/placeholder/label/valor) para
    diagnosticar cuál es la caja 'Número factura'."""
    try:
        data = page.evaluate(
            r"""() => {
                const vis = el => { const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; };
                const out = [];
                for (const el of document.querySelectorAll('input, textarea')) {
                    if (!vis(el)) continue;
                    const ff = el.closest('mat-form-field, .mat-form-field, .form-field, .field');
                    out.push({tag: el.tagName.toLowerCase(), type: el.type||'',
                              name: el.getAttribute('name')||el.getAttribute('formcontrolname')||'',
                              ph: el.getAttribute('placeholder')||'',
                              label: ff ? (ff.innerText||'').trim().slice(0,50) : '',
                              val: el.value||''});
                }
                return out;
            }"""
        )
        logger.info(f"  [diag] inputs visibles ({len(data)}):")
        for d in data:
            logger.info(f"    <{d['tag']}> type={d['type']!r} name={d['name']!r} "
                        f"ph={d['ph']!r} label={d['label']!r} val={d['val']!r}")
    except Exception as e:
        logger.info(f"  [diag] no pude volcar inputs: {e}")


def _caja_numero_factura(page: Page):
    """Localiza el input 'Número factura'. Es un campo de Angular Material SIN
    placeholder (la etiqueta flota aparte), así que probamos por label."""
    # 1) get_by_label: maneja <label for>, aria-label y mat-label de Material.
    for etiqueta in ("Número factura", "Numero factura"):
        try:
            c = _primer_visible(page.get_by_label(etiqueta, exact=False))
            if c is not None:
                return c
        except Exception:
            pass
    # 2) input dentro del mat-form-field cuyo texto dice '...mero factura', o el
    #    input que sigue a ese texto (tolerante a tilde con 'mero factura').
    for sel in (
        "xpath=//mat-form-field[.//*[contains(normalize-space(.),'mero factura')]]//input",
        "xpath=//*[contains(normalize-space(.),'mero factura')]/following::input[1]",
    ):
        c = _primer_visible(page.locator(sel))
        if c is not None:
            return c
    # 3) placeholder / name / formcontrol.
    c = _primer_visible(page.locator(
        "input[placeholder*='actura' i], input[name*='factura' i], "
        "input[formcontrolname*='factura' i]"
    ))
    if c is not None:
        return c
    # 4) primer input de texto visible.
    return _primer_visible(page.locator("input[type='text'], input:not([type])"))


def _set_page_size_max(page: Page) -> None:
    """Pone el selector de tamaño de página en su valor más grande."""
    sel = _primer_visible(page.locator("select"))
    if sel is None:
        return
    try:
        opciones = sel.locator("option").all_inner_texts()
        numericas = [o for o in opciones if o.strip().isdigit()]
        if numericas:
            mayor = max(numericas, key=lambda o: int(o.strip()))
            sel.select_option(label=mayor)
            page.wait_for_timeout(1200)
            logger.info(f"  Tamaño de página = {mayor.strip()}")
    except Exception:
        pass


def _leer_pagina(page: Page) -> list[dict]:
    """Lee las filas visibles de la grilla de facturas mapeando por encabezado."""
    datos = page.evaluate(
        r"""() => {
            const tabla = document.querySelector('table');
            if (!tabla) return {headers: [], rows: []};
            const ths = Array.from(tabla.querySelectorAll('thead th, thead td'))
                .map(th => (th.innerText || '').trim());
            const rows = [];
            for (const tr of tabla.querySelectorAll('tbody tr')) {
                const tds = Array.from(tr.querySelectorAll('td'));
                if (!tds.length) continue;
                const cells = tds.map(td => (td.innerText || '').trim());
                const txt = cells.join(' ').trim();
                if (txt === '') continue;
                // Fila placeholder de grilla vacía ("Sin datos para mostrar").
                if (/sin datos|no hay datos|sin registros|no data|no records/i.test(txt)) continue;
                rows.push(cells);
            }
            return {headers: ths, rows};
        }"""
    )
    headers = [_norm(h) for h in datos.get("headers", [])]

    def _col(*claves: str) -> int:
        for clave in claves:
            for i, h in enumerate(headers):
                if clave in h:
                    return i
        return -1

    idx = {
        "nit": _col("NIT"),
        "fecha_radicacion": _col("FECHA RADICACION", "RADICACION FACTURA"),
        "radicado": _col("RADICADO"),
        "quien_radica": _col("QUIEN RADICA"),
        "factura": _col("FACTURA"),
        "valor": _col("VALOR"),
        "estado": _col("ESTADO"),
        "fecha_ratificacion": _col("FECHA RATIFICACION", "RATIFICACION"),
        "semaforo": _col("SEMAFORO"),
    }
    out: list[dict] = []
    for cells in datos.get("rows", []):
        def g(k: str) -> str:
            i = idx[k]
            return cells[i].strip() if 0 <= i < len(cells) else ""
        reg = {k: g(k) for k in idx}
        if any(reg.values()):
            out.append(reg)
    return out


def leer_grilla_completa(page: Page, max_paginas: int = 200) -> list[dict]:
    """Recorre todas las páginas de la grilla y devuelve la lista de filas."""
    _set_page_size_max(page)
    todas: list[dict] = []
    vistos: set[tuple] = set()
    huella_anterior = None
    for _ in range(max_paginas):
        filas = _leer_pagina(page)
        for f in filas:
            clave = (f.get("radicado", ""), f.get("factura", ""))
            if clave in vistos and clave != ("", ""):
                continue
            vistos.add(clave)
            todas.append(f)
        huella = tuple((f.get("radicado"), f.get("factura")) for f in filas)
        if huella == huella_anterior:
            break
        huella_anterior = huella
        nxt = _primer_visible(page.locator(
            "button[aria-label*='next' i], li[aria-label*='next' i] button, "
            "button:has-text('›'), a[aria-label*='Next' i]"
        ))
        if nxt is None:
            break
        try:
            disabled = nxt.evaluate(
                "el => !!el.disabled || el.getAttribute('disabled')!==null || "
                "(el.closest('li')&&el.closest('li').classList.contains('disabled'))"
            )
        except Exception:
            disabled = False
        if disabled:
            break
        try:
            nxt.click(timeout=4000)
        except Exception:
            break
        page.wait_for_timeout(1200)
    logger.info(f"  Grilla leída: {len(todas)} filas.")
    return todas


def _grilla_dice_sin_datos(page: Page) -> bool:
    try:
        return page.locator("text=/sin datos|no hay datos|sin registros|no data/i").count() > 0
    except Exception:
        return False


def filtrar_por_factura(page: Page, factura: str, timeout_s: int = 35) -> bool:
    """Escribe la factura en 'Número factura', dispara FILTRAR y ESPERA a que la
    grilla (que es LENTA) traiga la fila. True si aparece al menos una fila;
    False si la grilla queda estable en 'Sin datos' o vence el plazo."""
    caja = _caja_numero_factura(page)
    if caja is None:
        logger.warning("  No encontré la caja 'Número factura'; sigo sin filtrar.")
        return True
    try:
        caja.click()
        caja.fill("")
        caja.type(factura, delay=30)
        # Eventos para que el form de Angular registre el valor antes de FILTRAR.
        caja.evaluate(
            "el => { el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true})); }"
        )
    except Exception:
        pass
    # Log del valor que quedó en la caja (diagnóstico siempre).
    try:
        val_leido = caja.input_value()
    except Exception:
        val_leido = "?"
    logger.info(f"  caja 'Número factura' = {val_leido!r}")
    if factura.upper() not in (val_leido or "").upper():
        logger.warning("  ⚠ la caja de filtro no tomó la factura; vuelco inputs visibles:")
        _dump_inputs(page)
    # Disparar el filtro: botón FILTRAR y, por las dudas, Enter en la caja.
    btn = _primer_visible(page.locator("button:has-text('FILTRAR'), button:has-text('Filtrar')"))
    if btn is not None:
        try:
            btn.click()
        except Exception:
            pass
    try:
        caja.press("Enter")
    except Exception:
        pass
    # Poll: la grilla puede tardar varios segundos en responder.
    inicio = time.time()
    sin_datos_seguidas = 0
    aviso = False
    while time.time() - inicio < timeout_s:
        if _leer_pagina(page):
            return True
        # Tras una gracia inicial, si dice 'Sin datos' de forma estable, no está.
        if time.time() - inicio > 8 and _grilla_dice_sin_datos(page):
            sin_datos_seguidas += 1
            if sin_datos_seguidas >= 3:
                return False
        else:
            sin_datos_seguidas = 0
        if not aviso and time.time() - inicio > 5:
            logger.info("  esperando que la grilla traiga la factura (es lenta)…")
            aviso = True
        page.wait_for_timeout(900)
    return bool(_leer_pagina(page))


# ─── Formulario de RESPUESTA (RTA2) ─────────────────────────────────────────


def abrir_respuesta(page: Page, factura: str) -> bool:
    """Filtra la factura y clickea su botón 'RESPUESTA'. True si abrió el form."""
    if not filtrar_por_factura(page, factura):
        logger.warning(f"  {factura}: no aparece en la grilla tras filtrar.")
        return False
    fila = _primer_visible(page.locator(f"tr:has-text('{factura}')"))
    btn = None
    if fila is not None:
        btn = _primer_visible(fila.locator("button:has-text('RESPUESTA'), a:has-text('RESPUESTA')"))
    if btn is None:
        btn = _primer_visible(page.locator("button:has-text('RESPUESTA'), a:has-text('RESPUESTA')"))
    if btn is None:
        _screenshot_debug(page, f"sin_boton_respuesta_{factura}")
        logger.warning(f"  {factura}: no encontré el botón RESPUESTA.")
        return False
    btn.click()
    # El form abre como página completa: título 'Respuesta' + 'Factura # ...'.
    try:
        page.wait_for_selector("text=GUARDAR RESPUESTA", timeout=30000)
    except PlaywrightTimeout:
        page.wait_for_timeout(2500)
    page.wait_for_timeout(800)
    return True


def _headers_formulario(page: Page) -> list[str]:
    """Devuelve los encabezados de la tabla del formulario de respuesta."""
    try:
        return page.evaluate(
            r"""() => {
                const t = document.querySelector('table');
                if (!t) return [];
                const cells = t.querySelectorAll('thead th, thead td, mat-header-cell, [role=columnheader]');
                return Array.from(cells).map(c => (c.innerText || '').trim());
            }"""
        )
    except Exception:
        return []


def _idx_columna(headers: list[str], *needles_nospace: str) -> int:
    """Índice de la 1ra columna cuyo encabezado (sin puntuación/espacios)
    contiene alguno de los needles. Evita falsos positivos por prefijos
    pidiendo el match más específico primero."""
    norm = [_norm_col(h) for h in headers]
    for needle in needles_nospace:
        for i, h in enumerate(norm):
            if needle in h:
                return i
    return -1


def _filas_formulario(page: Page):
    """Locators de las filas de servicio del formulario (tbody)."""
    filas = page.locator("table tbody tr, mat-table mat-row")
    visibles = []
    try:
        n = filas.count()
    except Exception:
        n = 0
    for i in range(n):
        f = filas.nth(i)
        try:
            if not f.is_visible():
                continue
            # Saltar filas vacías / de "no data".
            if (f.inner_text() or "").strip() == "":
                continue
            visibles.append(f)
        except Exception:
            continue
    return visibles


def _celda(fila, idx: int):
    """Celda (td/mat-cell) en la posición idx de la fila."""
    if idx < 0:
        return None
    celdas = fila.locator(":scope > td, :scope > mat-cell, :scope > [role=cell]")
    try:
        if idx < celdas.count():
            return celdas.nth(idx)
    except Exception:
        pass
    return None


def _elegir_codigo_en_celda(page: Page, celda, codigo: str) -> bool:
    """Selecciona `codigo` en el dropdown que vive en `celda`. Maneja <select>
    nativo y dropdowns tipo Angular Material (overlay con las opciones)."""
    if celda is None:
        return False
    # 1) <select> nativo.
    sel = _primer_visible(celda.locator("select"))
    if sel is not None:
        try:
            opciones = sel.locator("option").all_inner_texts()
            match = next((o for o in opciones if codigo in o), None)
            if match:
                sel.select_option(label=match)
                page.wait_for_timeout(400)
                return True
        except Exception:
            pass
    # 2) Dropdown custom: abrir y elegir del overlay.
    trigger = (
        _primer_visible(celda.locator(
            "mat-select, [role=combobox], .mat-select-trigger, .mat-mdc-select-trigger, "
            "[aria-haspopup], button, .mat-select"
        ))
        or celda  # como último recurso, clickeo la celda entera
    )
    try:
        trigger.click()
    except Exception:
        try:
            celda.click()
        except Exception:
            return False
    page.wait_for_timeout(600)
    # Las opciones aparecen en un overlay a nivel body.
    opcion = _primer_visible(page.locator(
        f".cdk-overlay-pane [role=option]:has-text('{codigo}'), "
        f".cdk-overlay-pane mat-option:has-text('{codigo}'), "
        f".cdk-overlay-container li:has-text('{codigo}'), "
        f"[role=listbox] [role=option]:has-text('{codigo}'), "
        f"li:has-text('{codigo}')"
    ))
    if opcion is None:
        _screenshot_debug(page, f"dropdown_sin_{codigo}")
        # Cerrar el overlay para no bloquear la pantalla.
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False
    try:
        opcion.click()
        page.wait_for_timeout(400)
        return True
    except Exception:
        return False


def _cargar_detalle_en_celda(page: Page, celda, texto: str) -> bool:
    """Click en el lápiz de 'Detalle Rta 2 prestador' y carga el texto. El
    editor puede abrir como modal o como campo inline."""
    if celda is None:
        return False
    lapiz = (
        _primer_visible(celda.locator(
            "button, [class*=edit i], [class*=pencil i], mat-icon, i, svg, a"
        ))
        or celda
    )
    try:
        lapiz.click()
    except Exception:
        try:
            celda.click()
        except Exception:
            return False
    page.wait_for_timeout(700)
    # Campo de edición: textarea / contenteditable / input (en modal o inline).
    campo = (
        _primer_visible(page.locator(
            ".cdk-overlay-pane textarea, .modal textarea, [role=dialog] textarea, textarea"
        ))
        or _primer_visible(page.locator(
            ".cdk-overlay-pane [contenteditable=true], [role=dialog] [contenteditable=true], "
            "[contenteditable=true]"
        ))
        or _primer_visible(celda.locator("input, textarea"))
    )
    if campo is None:
        _screenshot_debug(page, "detalle_sin_editor")
        return False
    try:
        try:
            campo.fill(texto)
        except Exception:
            # contenteditable no soporta fill(): tipear.
            campo.click()
            campo.type(texto, delay=2)
        campo.evaluate(
            "el => { el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true}));"
            " el.dispatchEvent(new Event('blur', {bubbles:true})); }"
        )
    except Exception as e:
        logger.warning(f"  No pude escribir el detalle: {e}")
        return False
    page.wait_for_timeout(300)
    # Confirmar el editor si tiene botón propio (Aceptar/Guardar/OK/Listo/✓).
    conf = _primer_visible(page.locator(
        ".cdk-overlay-pane button:has-text('Aceptar'), [role=dialog] button:has-text('Aceptar'), "
        ".cdk-overlay-pane button:has-text('Guardar'), [role=dialog] button:has-text('Guardar'), "
        ".cdk-overlay-pane button:has-text('OK'), [role=dialog] button:has-text('Listo')"
    ))
    if conf is not None:
        try:
            conf.click()
            page.wait_for_timeout(400)
        except Exception:
            pass
    return True


def _guardar_fila(page: Page, fila, idx_guardar: int) -> bool:
    """Click en el ✓ ('chulito') de Guardar de la fila y espera el cartel verde
    'Respuesta guardada con exito!'."""
    celda = _celda(fila, idx_guardar)
    btn = None
    if celda is not None:
        btn = _primer_visible(celda.locator("button, [class*=check i], mat-icon, i, svg, a"))
    if btn is None:
        return False
    try:
        btn.click()
    except Exception:
        return False
    try:
        page.wait_for_selector("text=/guardada con exito/i", timeout=8000)
        logger.info("    ✓ fila guardada ('guardada con exito').")
    except PlaywrightTimeout:
        logger.info("    ✓ fila guardada (no vi el cartel; sigo).")
    page.wait_for_timeout(600)
    return True


def _buscar_pdf_factura(pdf_dir: Path | None, factura: str) -> Path | None:
    """Busca <factura>.pdf en pdf_dir (case-insensitive, .pdf/.PDF)."""
    if pdf_dir is None or not pdf_dir.is_dir():
        return None
    objetivo = factura.strip().upper()
    try:
        for p in pdf_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".pdf" and p.stem.strip().upper() == objetivo:
                return p
    except OSError:
        return None
    return None


def _subir_pdf_en_celda(page: Page, celda, pdf_path: Path) -> bool:
    """Sube el PDF a la columna 'Archivo' de la fila. Usa el input[type=file]
    directo si existe; si no, intercepta el file chooser del icono (evita el
    diálogo del sistema operativo)."""
    if celda is None:
        return False
    inp = celda.locator("input[type=file]")
    try:
        if inp.count() > 0:
            inp.first.set_input_files(str(pdf_path))
            page.wait_for_timeout(1200)
            return True
    except Exception:
        pass
    icono = _primer_visible(celda.locator("button, a, i, mat-icon, svg, img")) or celda
    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            icono.click()
        fc_info.value.set_files(str(pdf_path))
        page.wait_for_timeout(1200)
        return True
    except Exception as e:
        logger.warning(f"    no pude subir el PDF: {e}")
        return False


def _set_rows_per_page_form(page: Page) -> None:
    """En el form, subir 'Rows per page' a su máximo para ver todas las filas."""
    _set_page_size_max(page)


def responder_glosa(
    page: Page,
    factura: str,
    codigo: str,
    texto: str,
    evidencias: Path,
    max_filas: int = 0,
    guardar: bool = True,
    pdf_dir: Path | None = None,
) -> dict:
    """Abre el formulario de la factura y, por cada fila de servicio, elige el
    código RTA2 y carga el detalle de respuesta; luego GUARDA. Devuelve un dict
    de reporte."""
    reg = {"factura": factura, "filas": 0, "ok": 0, "estado": "", "detalle": ""}
    if not abrir_respuesta(page, factura):
        reg["estado"] = "NO_EN_PESTANA"
        reg["detalle"] = ("no aparece en la pestaña tras filtrar "
                          "(¿ya respondida, o no es de esta pestaña?)")
        return reg

    _set_rows_per_page_form(page)
    headers = _headers_formulario(page)
    if not headers:
        _screenshot_debug(page, f"form_sin_headers_{factura}")
        reg["estado"] = "ERROR"
        reg["detalle"] = "no leí los encabezados del formulario"
        return reg

    i_cod = _idx_columna(headers, "CODRTA2RAT", "CODRTA2RA", "RTA2RAT")
    i_det = _idx_columna(headers, "DETALLERTA2PRESTADOR", "DETALLERTA2")
    i_arch = _idx_columna(headers, "ARCHIVO")
    i_guardar = _idx_columna(headers, "GUARDAR")
    if i_cod < 0 or i_det < 0:
        _screenshot_debug(page, f"form_columnas_{factura}")
        reg["estado"] = "ERROR"
        reg["detalle"] = (f"no ubiqué las columnas RTA2 (cod={i_cod}, detalle={i_det}); "
                          f"headers={headers}")
        logger.error(f"  {reg['detalle']}")
        return reg

    filas = _filas_formulario(page)
    if max_filas > 0:
        filas = filas[:max_filas]
    reg["filas"] = len(filas)
    if not filas:
        reg["estado"] = "SIN_FILAS"
        reg["detalle"] = "el formulario no mostró filas de servicio"
        return reg

    pdf = _buscar_pdf_factura(pdf_dir, factura)
    if pdf_dir is not None and pdf is None:
        logger.warning(f"  ⚠ no encontré {factura}.pdf en {pdf_dir} — la fila se guardará sin archivo.")

    logger.info(f"  {factura}: {len(filas)} fila(s) de servicio; cod={codigo}"
                + (f"; pdf={pdf.name}" if pdf else ""))
    for n, fila in enumerate(filas, start=1):
        ok_cod = _elegir_codigo_en_celda(page, _celda(fila, i_cod), codigo)
        if not ok_cod:
            logger.warning(f"    fila {n}: no pude elegir {codigo} en 'Cod Rta2 RAT'.")
            continue
        ok_det = _cargar_detalle_en_celda(page, _celda(fila, i_det), texto)
        if not ok_det:
            logger.warning(f"    fila {n}: no pude cargar 'Detalle Rta 2 prestador'.")
            continue
        # El PDF se sube ANTES del ✓: tras guardar, la fila queda bloqueada y el
        # botón de Archivo se apaga.
        if pdf is not None and i_arch >= 0:
            if _subir_pdf_en_celda(page, _celda(fila, i_arch), pdf):
                logger.info(f"    📎 PDF adjunto: {pdf.name}")
        if guardar and i_guardar >= 0:
            if not _guardar_fila(page, fila, i_guardar):
                logger.warning(f"    fila {n}: no pude dar el ✓ de Guardar.")
        reg["ok"] += 1
        logger.info(f"    fila {n}/{len(filas)} ✔")

    # Evidencia ANTES de 'GUARDAR RESPUESTA' (ese botón cierra el formulario).
    evidencias.mkdir(parents=True, exist_ok=True)
    ruta = evidencias / f"{factura}_ratificada.png"
    try:
        page.screenshot(path=str(ruta), full_page=True)
        logger.info(f"  📸 Evidencia: {ruta}")
    except Exception:
        pass

    if not guardar:
        reg["estado"] = "PILOTO_SIN_GUARDAR"
        reg["detalle"] = f"{reg['ok']}/{reg['filas']} filas cargadas (sin ✓ ni GUARDAR RESPUESTA)"
        return reg

    # GUARDAR RESPUESTA (botón verde, arriba a la derecha) → vuelve a la grilla.
    btn_guardar = _primer_visible(page.locator(
        "button:has-text('GUARDAR RESPUESTA'), button:has-text('Guardar Respuesta')"
    ))
    if btn_guardar is None:
        _screenshot_debug(page, f"sin_guardar_respuesta_{factura}")
        reg["estado"] = "SIN_BOTON_GUARDAR"
        reg["detalle"] = f"{reg['ok']}/{reg['filas']} filas cargadas pero no vi 'GUARDAR RESPUESTA'"
        return reg
    btn_guardar.click()
    page.wait_for_timeout(2500)

    if reg["ok"] == reg["filas"]:
        reg["estado"] = "OK"
        reg["detalle"] = f"{reg['ok']} fila(s) respondidas y guardadas"
    else:
        reg["estado"] = "PARCIAL"
        reg["detalle"] = f"{reg['ok']}/{reg['filas']} filas cargadas; revisar evidencia"
    return reg


def diagnosticar_respuesta(page: Page, factura: str) -> None:
    """Abre 'RESPUESTA' y vuelca la estructura del formulario (headers + campos
    + HTML + screenshot) sin escribir nada. Para depurar selectores."""
    logger.info(f"[DIAGNÓSTICO] {factura}: abriendo el formulario de RESPUESTA…")
    if not abrir_respuesta(page, factura):
        logger.error(f"  No pude abrir RESPUESTA para {factura}.")
        return
    out = Path("debug_screenshots")
    out.mkdir(exist_ok=True)
    _screenshot_debug(page, f"respuesta_form_{factura}")
    headers = _headers_formulario(page)
    logger.info(f"  Encabezados del formulario ({len(headers)}): {headers}")
    logger.info(f"    idx Cod Rta2 RAT      = {_idx_columna(headers, 'CODRTA2RAT', 'RTA2RAT')}")
    logger.info(f"    idx Detalle Rta 2     = {_idx_columna(headers, 'DETALLERTA2PRESTADOR', 'DETALLERTA2')}")
    logger.info(f"    idx Guardar           = {_idx_columna(headers, 'GUARDAR')}")
    try:
        dump = out / f"respuesta_form_{factura}.html"
        dump.write_text(page.content(), encoding="utf-8")
        logger.info(f"  HTML del formulario: {dump}")
    except Exception as e:
        logger.warning(f"  No pude volcar el HTML: {e}")


# ─── Driver ─────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Respuesta de glosas RATIFICADAS en FOMAG / Horus (horus2.horus-health.com).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tab", default="RATIFICADAS",
        help="Pestaña: RADICADAS / PENDIENTES / RATIFICADAS (default) / "
             "CONCILIACION / CONSOLIDADO / HISTORICO.",
    )
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--listar", action="store_true",
                      help="Sólo listar la grilla de la pestaña a un CSV (read-only).")
    modo.add_argument("--diagnostico", action="store_true",
                      help="Abrir el formulario de RESPUESTA de una factura y volcar su estructura.")
    modo.add_argument("--responder", action="store_true",
                      help="Responder las glosas ratificadas (cod RE9901 + texto fijo).")
    sel = parser.add_mutually_exclusive_group()
    sel.add_argument("--solo", type=str, help="Una sola factura (ej. HUS511575).")
    sel.add_argument("--facturas", type=str, help="Lista de facturas separadas por coma.")
    sel.add_argument("--lista", type=Path, help="TXT con una factura por línea.")
    parser.add_argument("--cod", default=COD_RTA2_DEFAULT,
                        help=f"Código RTA2 a seleccionar (default {COD_RTA2_DEFAULT}).")
    parser.add_argument("--texto-archivo", type=Path, default=None,
                        help="TXT con el texto de respuesta (default: texto fijo de ratificada).")
    parser.add_argument("--pdf-dir", type=Path, default=None,
                        help="Carpeta con los PDF de respuesta nombrados <factura>.pdf "
                             "(ej. HUS511575.pdf) para la columna 'Archivo'.")
    parser.add_argument("--max-filas", type=int, default=0,
                        help="Piloto: responder como mucho N filas de servicio por factura.")
    parser.add_argument("--sin-guardar", action="store_true",
                        help="Carga código + detalle pero NO da 'GUARDAR RESPUESTA' (piloto seguro).")
    parser.add_argument("--perfil", type=Path, default=PERFIL_DEFAULT,
                        help=f"Carpeta del perfil de navegador persistente (default {PERFIL_DEFAULT}).")
    parser.add_argument("--con-cabeza", action="store_true",
                        help="Mostrar el browser. OBLIGATORIO la primera vez (resolver el captcha).")
    parser.add_argument("--lento", action="store_true", help="Slow-motion 300ms (debug).")
    parser.add_argument("--evidencias", type=Path, default=Path("EVIDENCIA_FOMAG"),
                        help="Carpeta para los pantallazos de cierre.")
    parser.add_argument("--reporte", type=Path, default=Path("reporte_fomag.csv"),
                        help="CSV de salida (--listar) o de seguimiento (--responder).")
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()
    setup_logging(args.log)

    _exigir_playwright()
    user, password = cargar_credenciales()
    logger.info(f"Usuario FOMAG: {user}")

    tab_label = TABS.get(_norm_col(args.tab), args.tab.strip().upper())

    texto = TEXTO_RATIFICADA_DEFAULT
    if args.texto_archivo is not None:
        if not args.texto_archivo.is_file():
            logger.error(f"No existe --texto-archivo: {args.texto_archivo}")
            return 1
        texto = args.texto_archivo.read_text(encoding="utf-8-sig", errors="replace").strip()

    objetivos: list[str] = []
    if args.solo:
        objetivos = [args.solo.strip().upper()]
    elif args.facturas:
        objetivos = [f.strip().upper() for f in args.facturas.split(",") if f.strip()]
    elif args.lista:
        if not args.lista.is_file():
            logger.error(f"No existe el archivo de lista: {args.lista}")
            return 1
        contenido = args.lista.read_text(encoding="utf-8-sig", errors="replace")
        objetivos = [x.strip().upper() for x in contenido.replace(",", "\n").splitlines() if x.strip()]

    if (args.diagnostico or args.responder) and not objetivos:
        logger.error("Para --diagnostico/--responder pasá --solo / --facturas / --lista.")
        return 1

    args.perfil.mkdir(parents=True, exist_ok=True)
    resultados: list[dict] = []

    t0 = time.time()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(args.perfil),
            headless=not args.con_cabeza,
            slow_mo=300 if args.lento else 0,
            accept_downloads=True,
            viewport={"width": 1600, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_navigation_timeout(120000)
        page.set_default_timeout(30000)
        page.on("dialog", lambda d: d.accept())
        try:
            login(page, user, password)
            ir_a_pestana(page, tab_label)

            if args.listar:
                filas = leer_grilla_completa(page)
                args.reporte.parent.mkdir(parents=True, exist_ok=True)
                campos = ["nit", "fecha_radicacion", "radicado", "quien_radica",
                          "factura", "valor", "estado", "fecha_ratificacion", "semaforo"]
                with args.reporte.open("w", newline="", encoding="utf-8-sig") as fh:
                    w = csv.DictWriter(fh, fieldnames=campos)
                    w.writeheader()
                    for f in filas:
                        w.writerow({k: f.get(k, "") for k in campos})
                logger.info(f"\n✅ Inventario de {tab_label}: {len(filas)} facturas → {args.reporte}")

            elif args.diagnostico:
                for fac in objetivos:
                    diagnosticar_respuesta(page, fac)
                    # Volver a la grilla para la siguiente.
                    ir_a_pestana(page, tab_label)

            elif args.responder:
                logger.info(f"Respondiendo {len(objetivos)} factura(s) de {tab_label} "
                            f"con código {args.cod}"
                            + (" [SIN GUARDAR]" if args.sin_guardar else "") + ".")
                args.reporte.parent.mkdir(parents=True, exist_ok=True)
                f_rep = args.reporte.open("w", newline="", encoding="utf-8-sig")
                w_rep = csv.DictWriter(f_rep, fieldnames=["factura", "filas", "ok", "estado", "detalle"])
                w_rep.writeheader()
                for i, fac in enumerate(objetivos, start=1):
                    logger.info(f"[{i}/{len(objetivos)}] {fac}")
                    try:
                        reg = responder_glosa(
                            page, fac, args.cod, texto, args.evidencias,
                            max_filas=args.max_filas, guardar=not args.sin_guardar,
                            pdf_dir=args.pdf_dir,
                        )
                    except Exception as e:
                        _screenshot_debug(page, f"error_{fac}")
                        reg = {"factura": fac, "filas": 0, "ok": 0,
                               "estado": "ERROR", "detalle": str(e)[:300]}
                        logger.error(f"  ERROR en {fac}: {e}")
                    resultados.append(reg)
                    w_rep.writerow(reg)
                    f_rep.flush()
                    # Volver a la grilla para la siguiente factura.
                    try:
                        ir_a_pestana(page, tab_label)
                    except Exception:
                        pass
                f_rep.close()
                from collections import Counter
                logger.info(f"\n✅ Reporte: {args.reporte}")
                for estado, n in Counter(r["estado"] for r in resultados).items():
                    logger.info(f"  {estado}: {n}")
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    logger.info(f"Listo en {(time.time() - t0) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
