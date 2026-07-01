"""responder_glosas_mutual_ser.py — Respuesta a glosas en el portal MUTUAL SER (Zona Ser).

Portal: https://portalzonaser.mutualser.com
Módulo: AUDITORIA DE CUENTAS MEDICAS → GESTIÓN DE RESPUESTAS DE GLOSAS →
        CONSULTAR CUENTAS MÉDICAS GLOSADAS

Bot Playwright que carga las respuestas a glosas del HUS (una fila por objeción,
generadas por `extraer_respuestas_glosa_mutualser.py`) sin intervención humana,
siguiendo el mismo patrón que responder_glosas_coosalud.py / _simed.py.

⚠ ESTADO: v0 — ANDAMIAJE + CALIBRACIÓN.
    Lo que YA funciona (probado con la infraestructura del repo):
      - Login con manejo de reCAPTCHA vía sesión persistida (storage_state):
        el humano resuelve el captcha UNA vez con --con-cabeza y el bot reusa la
        cookie en las corridas siguientes.
      - Lectura del Excel de respuestas (columnas del extractor de MUTUAL SER).
      - Agrupación por (código respuesta + texto) — en glosa ratificada TODOS los
        ítems comparten RE9901 + el mismo texto, así que es UN solo grupo.
      - Modo --explorar: navega al módulo y VUELCA el DOM (inputs, botones, selects,
        cabeceras de la grilla) + screenshot, para calibrar los selectores reales
        (equivalente web del dump_dg.py de DGH).
      - Reporte CSV incremental, logging, screenshots de diagnóstico.

    Lo que FALTA calibrar contra el portal real (marcado con  # TODO(portal)  ):
      - Selectores de la grilla, apertura de factura, formulario de respuesta por
        glosa (código + valor aceptado + texto), y el botón de finalizar.
      Corré primero:  py responder_glosas_mutual_ser.py --explorar --con-cabeza
      y con el volcado se completan los  # TODO(portal).

CREDENCIALES (variables de entorno, NO en el código):
    setx MUTUALSER_USER  gerencia@hus.gov.co
    setx MUTUALSER_PASSWORD  <contraseña>
    (cerrar y reabrir la terminal para que tomen efecto)

INSTALACIÓN (una vez):
    py -m pip install playwright openpyxl
    py -m playwright install chromium

USO:
    REM 1) Explorar/calibrar el portal (browser visible, resolver captcha a mano):
    py responder_glosas_mutual_ser.py --explorar --con-cabeza

    REM 2) Piloto de una factura (con cabeza), reutilizando la sesión guardada:
    py responder_glosas_mutual_ser.py --excel respuestas_mutualser.xlsx ^
        --solo HUS0000492542 --con-cabeza

    REM 3) Masivo:
    py responder_glosas_mutual_ser.py --excel respuestas_mutualser.xlsx --todas ^
        --reporte reporte_mutualser.csv
"""

from __future__ import annotations

import argparse
import contextlib
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
        sync_playwright,
    )
    from playwright.sync_api import (
        TimeoutError as PlaywrightTimeout,
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


# ─── Constantes del portal ───────────────────────────────────────────────────

PORTAL_BASE = "https://portalzonaser.mutualser.com"
PORTAL_LOGIN = f"{PORTAL_BASE}/auth/login"
PORTAL_DASHBOARD = f"{PORTAL_BASE}/dashboard"
PORTAL_MODULO = (
    f"{PORTAL_BASE}/dashboard/applications/auditoria-de-cuentas-medicas/GESTION-RESPUESTAS-GLOSAS"
)

# Señal de login exitoso: textos/URL que sólo aparecen ya autenticado.
LOGIN_OK_TEXTOS = ("Inicio", "AUDITORIA DE CUENTAS MEDICAS", "GESTIÓN DE RESPUESTAS")

STORAGE_STATE_DEFAULT = "mutualser_session.json"
MAX_PDF_MB = 10

logger = logging.getLogger("responder_mutualser")


# ─── Setup ───────────────────────────────────────────────────────────────────


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def cargar_credenciales() -> tuple[str, str]:
    user = os.environ.get("MUTUALSER_USER", "").strip()
    password = os.environ.get("MUTUALSER_PASSWORD", "").strip()
    if not user or not password:
        sys.stderr.write(
            "ERROR: faltan credenciales. Setealas con:\n"
            "    setx MUTUALSER_USER <correo>\n"
            "    setx MUTUALSER_PASSWORD <contraseña>\n"
            "Despues cerra y reabri la terminal.\n"
        )
        sys.exit(2)
    return user, password


# ─── Lectura del Excel de respuestas (salida del extractor MUTUAL SER) ────────


def _norm_header(h: str) -> str:
    s = unicodedata.normalize("NFKD", (h or "").strip().upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# Alias tolerantes por columna (acepta la salida del extractor y variantes manuales).
COLUMNAS = {
    "factura": {"FACTURA", "# FACTURA", "NUMERO FACTURA", "NUMERO_FACTURA"},
    "num": {"# OBJECION", "NUM OBJECION", "OBJECION", "ITEM", "# OBJECIÓN"},
    "cod_glosa": {"CODIGO GLOSA", "COD GLOSA", "CODIGO_GLOSA", "COD."},
    "cod_rta": {"CODIGO RESPUESTA", "COD RESPUESTA", "COD RESPUESTA GLOSA"},
    "servicio": {"SERVICIO"},
    "aceptado": {"VALOR ACEPTADO", "ACEPTADO"},
    "objetado": {"VALOR OBJETADO", "OBJETADO"},
    "detalle": {"DETALLE RESPUESTA", "OBSERVACION RTA GLOSA", "OBSERVACIONES", "DETALLE"},
}


def normalizar_factura(f: str) -> str:
    """'HUS0000492542' -> '492542' (sin prefijo HUS ni ceros a la izquierda)."""
    s = re.sub(r"(?i)^hus", "", (f or "").strip())
    s = s.lstrip("0")
    return s or "0"


def _to_int(s) -> int:
    if s is None:
        return 0
    if isinstance(s, (int, float)):
        return int(s)
    txt = str(s).split(",")[0]
    return int(re.sub(r"[^\d]", "", txt) or "0")


def leer_excel_respuestas(ruta: Path) -> dict[str, dict]:
    """Devuelve {factura: {"items": [...], "grupos": [...]}} donde cada item es
    {num, cod_glosa, cod_rta, servicio, aceptado, detalle} y cada grupo agrupa los
    items por (cod_rta, detalle) idénticos (respuesta masiva)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl. Instalalo con: py -m pip install openpyxl\n")
        sys.exit(2)

    wb = load_workbook(ruta, data_only=True, read_only=True)
    ws = wb.active
    filas = ws.iter_rows(values_only=True)
    encabezados = [_norm_header(str(c)) for c in next(filas)]

    idx: dict[str, int] = {}
    for clave, alias in COLUMNAS.items():
        for i, h in enumerate(encabezados):
            if h in alias:
                idx[clave] = i
                break

    faltan = [k for k in ("factura", "detalle") if k not in idx]
    if faltan:
        sys.stderr.write(
            f"ERROR: el Excel no tiene columnas {faltan}. Encabezados: {encabezados}\n"
        )
        sys.exit(2)

    por_factura: dict[str, dict] = {}
    for fila in filas:
        if not fila:
            continue
        fac_raw = fila[idx["factura"]] if idx.get("factura") is not None else None
        detalle = fila[idx["detalle"]] if idx.get("detalle") is not None else None
        if not fac_raw or not detalle:
            continue
        fac = str(fac_raw).strip().upper()
        item = {
            "num": _to_int(fila[idx["num"]]) if "num" in idx else 0,
            "cod_glosa": str(fila[idx["cod_glosa"]]).strip()
            if "cod_glosa" in idx and fila[idx["cod_glosa"]]
            else "",
            "cod_rta": str(fila[idx["cod_rta"]]).strip()
            if "cod_rta" in idx and fila[idx["cod_rta"]]
            else "",
            "servicio": str(fila[idx["servicio"]]).strip()
            if "servicio" in idx and fila[idx["servicio"]]
            else "",
            "aceptado": _to_int(fila[idx["aceptado"]]) if "aceptado" in idx else 0,
            "objetado": _to_int(fila[idx["objetado"]]) if "objetado" in idx else 0,
            "detalle": str(detalle).strip(),
        }
        por_factura.setdefault(fac, {"items": []})["items"].append(item)

    # Agrupar por (cod_rta, detalle) idénticos — en glosa ratificada es un solo grupo.
    for datos in por_factura.values():
        grupos: dict[tuple, dict] = {}
        for it in datos["items"]:
            clave = (it["cod_rta"], it["detalle"])
            g = grupos.setdefault(
                clave, {"cod_rta": it["cod_rta"], "detalle": it["detalle"], "items": []}
            )
            g["items"].append(it)
        datos["grupos"] = list(grupos.values())
    return por_factura


def sanitizar(texto: str) -> str:
    """Deja SOLO [A-Za-z0-9] y espacios, translitera tildes/ñ. Se usa SOLO si el
    portal de MUTUAL SER rechaza caracteres especiales (a confirmar en --explorar;
    por defecto el bot manda el texto tal cual)."""
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ─── Login con reCAPTCHA (sesión persistida) ─────────────────────────────────


def _login_ok(page: Page) -> bool:
    try:
        if "/auth/login" in page.url:
            return False
        for t in LOGIN_OK_TEXTOS:
            if page.get_by_text(t, exact=False).count() > 0:
                return True
        return "/dashboard" in page.url
    except Exception:
        return False


def login_interactivo(page: Page, user: str, password: str, timeout_captcha_s: int = 240) -> None:
    """Login que rellena usuario/clave y ESPERA a que un humano resuelva el
    reCAPTCHA y entre. Al detectar la sesión activa, el llamador guarda el
    storage_state para reusarlo sin captcha en corridas posteriores."""
    logger.info("Abriendo login de MUTUAL SER…")
    page.goto(PORTAL_LOGIN, wait_until="domcontentloaded")
    if _login_ok(page):
        logger.info("Sesión ya activa.")
        return

    # Rellenar credenciales (selectores tolerantes).
    try:
        page.locator(
            "input[type=email], input[name*=correo i], input[name*=email i], input[type=text]"
        ).first.fill(user)
        page.locator("input[type=password]").first.fill(password)
        logger.info("Usuario y contraseña rellenados.")
    except Exception as e:
        logger.warning(f"No pude rellenar credenciales automáticamente: {e}")

    logger.warning(
        "⏳ RESOLVÉ EL reCAPTCHA y hacé clic en INGRESAR en la ventana del browser. "
        f"Espero hasta {timeout_captcha_s}s a que entres…"
    )
    t0 = time.time()
    while time.time() - t0 < timeout_captcha_s:
        if _login_ok(page):
            logger.info("✅ Login exitoso (sesión activa).")
            return
        time.sleep(2)
    raise RuntimeError("No se detectó login tras esperar el captcha (timeout).")


def abrir_sesion(p, args, user: str, password: str):
    """Abre browser + contexto. Si existe --storage-state válido, lo reutiliza
    (evita el captcha). Si no, hace login interactivo y lo guarda."""
    storage = Path(args.storage_state)
    browser = p.chromium.launch(headless=not args.con_cabeza, slow_mo=300 if args.lento else 0)
    ctx_kwargs = {"accept_downloads": True}
    if storage.is_file():
        logger.info(f"Reutilizando sesión guardada: {storage}")
        ctx_kwargs["storage_state"] = str(storage)
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()
    page.set_default_navigation_timeout(120000)
    page.set_default_timeout(30000)
    page.on("dialog", lambda d: d.accept())

    # Validar la sesión reutilizada; si no sirve, re-login interactivo.
    page.goto(PORTAL_MODULO, wait_until="domcontentloaded")
    if not _login_ok(page):
        if not args.con_cabeza:
            raise RuntimeError(
                "Sesión inválida/expirada y estás headless. Corré una vez con "
                "--con-cabeza para resolver el captcha y regenerar la sesión."
            )
        login_interactivo(page, user, password)
        ctx.storage_state(path=str(storage))
        logger.info(f"Sesión guardada en {storage} (reutilizable sin captcha).")
        page.goto(PORTAL_MODULO, wait_until="domcontentloaded")
    return browser, ctx, page


# ─── Exploración/calibración del DOM (equivalente web de dump_dg.py) ──────────


def explorar(page: Page, salida_dir: Path) -> None:
    """Vuelca la estructura del módulo para calibrar los  # TODO(portal):
    screenshot + inventario de inputs, botones, selects, links y cabeceras de tabla."""
    salida_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    page.wait_for_timeout(3000)
    shot = salida_dir / f"explorar_{ts}.png"
    try:
        page.screenshot(path=str(shot), full_page=True)
        logger.info(f"Screenshot: {shot}")
    except Exception as e:
        logger.warning(f"No pude sacar screenshot: {e}")

    dump = page.evaluate(
        """() => {
        const txt = el => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0,80);
        const desc = el => {
            const a = [];
            for (const at of ['id','name','type','placeholder','role','class']) {
                const v = el.getAttribute(at); if (v) a.push(at+'='+v.slice(0,60));
            }
            return el.tagName.toLowerCase()+' {'+a.join(' ')+'} '+txt(el);
        };
        const pick = sel => Array.from(document.querySelectorAll(sel)).slice(0,60).map(desc);
        return {
            url: location.href,
            botones: pick('button, [role=button], input[type=button], input[type=submit], a.btn'),
            inputs: pick('input, textarea'),
            selects: pick('select, [role=combobox], mat-select'),
            th: Array.from(document.querySelectorAll('th, [role=columnheader]')).slice(0,40).map(e=>txt(e)),
            links: Array.from(document.querySelectorAll('a')).slice(0,60).map(a=>({t:txt(a), href:a.getAttribute('href')})),
        };
    }"""
    )
    out = salida_dir / f"explorar_{ts}.txt"
    with out.open("w", encoding="utf-8") as f:
        f.write(f"URL: {dump.get('url')}\n\n")
        for seccion in ("th", "botones", "selects", "inputs", "links"):
            f.write(f"===== {seccion.upper()} =====\n")
            for row in dump.get(seccion, []):
                f.write(f"  {row}\n")
            f.write("\n")
    logger.info(f"Volcado del DOM: {out}")
    logger.info(
        "Usá este volcado para completar los  # TODO(portal)  de este script "
        "(grilla, apertura de factura, formulario de respuesta, finalizar)."
    )


# ─── Procesamiento por factura (TODO: calibrar contra el portal) ─────────────


class CalibracionPendiente(NotImplementedError):
    """El flujo del portal aún no está calibrado (faltan los  # TODO(portal))."""


def buscar_factura_en_grilla(page: Page, factura: str) -> bool:
    """Abre la factura desde CONSULTAR CUENTAS MÉDICAS GLOSADAS (link azul de la
    columna FACTURA). Devuelve "YA" si ya tiene FECHA RESPUESTA SUBSANACIÓN."""
    # TODO(portal): con los selectores del volcado de --explorar:
    #   1) filtrar/buscar la factura en la grilla (o paginar hasta encontrarla).
    #   2) idempotencia: si FECHA RESPUESTA SUBSANACIÓN != vacío -> return "YA".
    #   3) click en el link azul de la factura -> abre "Detalle de respuesta de glosa".
    raise CalibracionPendiente(
        "buscar_factura_en_grilla: falta calibrar selectores (corré --explorar)."
    )


def subsanar_items(page: Page, items: list[dict], evidencias: Path) -> None:
    """Flujo de SUBSANACIÓN ítem por ítem (ver docs/CONTEXTO_MUTUAL_SER.md §6):
    click SUBSANAR GLOSA (modo edición) y, por cada ítem, llenar valor aceptado +
    observación (modal ≤1000 chars) + soporte PDF."""
    # TODO(portal): con los selectores del volcado de --explorar:
    #   1) click en el botón "SUBSANAR GLOSA" (habilita edición).
    #   2) por cada fila de ítem del portal (el portal CONSOLIDA por CUPS, así que
    #      la respuesta uniforme se aplica a TODOS los ítems que muestre):
    #      a) expandir con el botón "+" azul de la columna TECNOLOGÍA;
    #      b) VALOR RATIFICADO ACEPTADO IPS = item['aceptado'] (0 en rechazo) -> check verde;
    #      c) click en el ícono azul de libro/chat -> modal "Observaciones de
    #         subsanación" -> escribir item['detalle'] (≤1000; ya viene en 832) -> ACEPTAR;
    #      d) (si aplica) ícono de nube -> modal "SOPORTE" -> set_input_files(pdf) ->
    #         GUARDAR -> esperar toast "Carga de archivo exitosa" + check verde.
    #   3) verificar que ACEPTAR TOTAL RATIFICADO quedó habilitado (azul).
    # OJO: si "CÓDIGO SUBSANACIÓN" permite carga masiva, preferirlo para facturas
    # con cientos de ítems (evita abrir el "+" de cada uno).
    raise CalibracionPendiente(
        "subsanar_items: falta calibrar el formulario de subsanación (corré --explorar)."
    )


def finalizar_factura(page: Page, factura: str, evidencias: Path) -> str:
    """Cierra la subsanación (ACEPTAR TOTAL RATIFICADO) y captura evidencia."""
    # TODO(portal): click en "ACEPTAR TOTAL RATIFICADO" (azul cuando está todo
    #   diligenciado) -> esperar confirmación -> screenshot evidencias/f"{factura}_ok.png".
    #   (Confirmar relación con "ENVIAR SUBSANACIÓN".)
    raise CalibracionPendiente("finalizar_factura: falta calibrar el cierre (corré --explorar).")


def procesar_factura(page: Page, factura: str, datos: dict, evidencias: Path) -> dict:
    items = [it for g in datos["grupos"] for it in g["items"]]
    reg = {
        "factura": factura,
        "grupos": len(datos["grupos"]),
        "items": len(items),
        "estado": "",
        "detalle": "",
    }
    try:
        estado = buscar_factura_en_grilla(page, factura)
        if estado == "YA":
            reg["estado"] = "YA_RESPONDIDA"
            reg["detalle"] = "FECHA RESPUESTA SUBSANACIÓN ya registrada"
            return reg
        subsanar_items(page, items, evidencias)
        estado_fin = finalizar_factura(page, factura, evidencias)
        reg["estado"] = "OK"
        reg["detalle"] = estado_fin or f"{len(items)} ítems subsanados"
    except CalibracionPendiente as e:
        reg["estado"] = "CALIBRACION_PENDIENTE"
        reg["detalle"] = str(e)
    except Exception as e:
        reg["estado"] = "ERROR"
        reg["detalle"] = str(e)[:300]
    return reg


# ─── CLI / main ──────────────────────────────────────────────────────────────


def _seleccionar_facturas(por_factura: dict, args) -> dict:
    if args.solo:
        objetivo = {args.solo.strip().upper()}
    elif args.facturas:
        objetivo = {f.strip().upper() for f in args.facturas.split(",") if f.strip()}
    elif args.lista:
        objetivo = {
            ln.strip().upper()
            for ln in Path(args.lista).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }
    else:  # --todas
        return por_factura
    return {f: d for f, d in por_factura.items() if f in objetivo}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Respuesta a glosas en el portal MUTUAL SER (Zona Ser).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--excel", type=Path, help="Excel de respuestas (extraer_respuestas_glosa_mutualser.py)."
    )
    grupo = parser.add_mutually_exclusive_group(required=False)
    grupo.add_argument("--solo", type=str, help="Procesar SOLO esta factura (piloto).")
    grupo.add_argument("--facturas", type=str, help="Lista separada por coma.")
    grupo.add_argument("--lista", type=Path, help="TXT con una factura por línea.")
    grupo.add_argument("--todas", action="store_true", help="Todas las facturas del Excel.")
    parser.add_argument(
        "--explorar",
        action="store_true",
        help="Volcar el DOM del módulo para calibrar (no responde).",
    )
    parser.add_argument(
        "--storage-state",
        type=str,
        default=STORAGE_STATE_DEFAULT,
        help="JSON de sesión (evita el captcha).",
    )
    parser.add_argument(
        "--evidencias",
        type=Path,
        default=Path("EVIDENCIA_MUTUALSER"),
        help="Carpeta de screenshots de cierre.",
    )
    parser.add_argument(
        "--con-cabeza",
        action="store_true",
        help="Browser visible (necesario para resolver el captcha).",
    )
    parser.add_argument("--lento", action="store_true", help="slow_mo 300ms (debug visual).")
    parser.add_argument(
        "--reporte", type=Path, default=Path("reporte_mutualser.csv"), help="CSV de salida."
    )
    parser.add_argument("--log", type=Path, default=None, help="Archivo de log adicional.")
    args = parser.parse_args()

    setup_logging(args.log)
    _exigir_playwright()
    user, password = cargar_credenciales()

    if not args.explorar and not args.excel:
        parser.error("indicá --excel (o usá --explorar para calibrar el portal).")
    if not args.explorar and not (args.solo or args.facturas or args.lista or args.todas):
        parser.error("elegí qué facturas procesar: --solo / --facturas / --lista / --todas.")

    with sync_playwright() as p:
        browser, ctx, page = abrir_sesion(p, args, user, password)
        try:
            if args.explorar:
                explorar(page, args.evidencias)
                return 0

            por_factura = leer_excel_respuestas(args.excel)
            seleccion = _seleccionar_facturas(por_factura, args)
            if not seleccion:
                logger.warning("No hay facturas que coincidan con la selección.")
                return 0
            logger.info(f"Facturas a procesar: {len(seleccion)}")

            args.reporte.parent.mkdir(parents=True, exist_ok=True)
            f_rep = args.reporte.open("w", newline="", encoding="utf-8-sig")
            w_rep = csv.DictWriter(
                f_rep, fieldnames=["factura", "grupos", "items", "estado", "detalle"]
            )
            w_rep.writeheader()
            resultados: list[dict] = []
            t0 = time.time()
            for i, (factura, datos) in enumerate(seleccion.items(), start=1):
                n_items = sum(len(g["items"]) for g in datos["grupos"])
                logger.info(
                    f"[{i}/{len(seleccion)}] {factura} — {len(datos['grupos'])} grupo(s), {n_items} ítems"
                )
                reg = procesar_factura(page, factura, datos, args.evidencias)
                resultados.append(reg)
                w_rep.writerow(reg)
                if i % 5 == 0:
                    f_rep.flush()
                logger.info(f"    → {reg['estado']}: {reg['detalle']}")
            f_rep.close()

            from collections import Counter

            dur = (time.time() - t0) / 60
            logger.info(f"\nReporte: {args.reporte} | {len(resultados)} facturas en {dur:.1f} min")
            for estado, n in Counter(r["estado"] for r in resultados).items():
                logger.info(f"  {estado}: {n}")
            if any(r["estado"] == "CALIBRACION_PENDIENTE" for r in resultados):
                logger.warning(
                    "Hay pasos sin calibrar. Corré  --explorar --con-cabeza  y completá "
                    "los  # TODO(portal)  de responder_glosas_mutual_ser.py."
                )
        finally:
            with contextlib.suppress(Exception):
                browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
