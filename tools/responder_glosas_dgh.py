"""responder_glosas_dgh.py — Carga respuestas de glosa en Dinámica Gerencial .NET
(módulo Cartera → Procesos → Trámite de Objeción), vía pywinauto.

ESTADO: v1 PILOTO. DGH es una app de escritorio DevExpress WPF; este bot no se
puede probar fuera de la máquina del usuario. Está pensado para correr UNA
factura a la vez (--solo) y, por seguridad, NO graba salvo que se pase --grabar.

PRE-REQUISITOS
--------------
1. DG abierto y LOGUEADO (Hospitalización / centro 01). Si no, corré antes:
       py tools\\login_dg.py
2. Dejá DG con la pantalla **"Listado de Tramite de Objeción"** abierta
   (Cartera → Procesos → Tramite de Objeción). El bot parte de ahí.
3. El Excel de respuestas (el mismo que usás para SIMED) con columnas:
       Factura | # Objeción | Valor Aceptado | Detalle Respuesta
   y, opcionalmente, una columna de código de respuesta (Cod Respuesta / RE).
   Si no está, se usa --cod-respuesta (default RE9901).

USO
---
    REM 0) CALIBRAR (recomendado la 1a vez): mueve el mouse a cada control del
    REM    modal SIN clickear, para verificar las coordenadas. Riesgo cero.
    py tools\\responder_glosas_dgh.py --excel "D:\\...\\respuestas.xlsx" --solo HUS0000516474 --calibrar

    REM 1) Piloto: llena el modal (fila → RE9901 → Observaciones → Aplicar campos)
    REM    pero NO graba, para que verifiques que quedó bien.
    py tools\\responder_glosas_dgh.py --excel "D:\\...\\respuestas.xlsx" --solo HUS0000516474

    REM 2) Cuando confíes, que grabe:
    py tools\\responder_glosas_dgh.py --excel "D:\\...\\respuestas.xlsx" --solo HUS0000516474 --grabar

    REM Volcar el árbol/diálogo si algo no se encuentra:
    py tools\\responder_glosas_dgh.py --excel ... --solo HUS... --dump-al-fallar

NOTA: el interior del modal WPF es opaco a UIA; se maneja por COORDENADAS sobre el
rect real del modal. Si algún click cae corrido, se ajustan los _MODAL_OFFSETS.

DEPENDENCIAS
------------
    py -m pip install pywinauto openpyxl

NOTA: solo corre en Windows.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Reutilizamos el lector de Excel y el sanitizador del bot de SIMED.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from responder_glosas_simed import (
        leer_excel_respuestas,
        normalizar_factura,
    )
except Exception:  # pragma: no cover - sólo si se mueve el archivo
    leer_excel_respuestas = normalizar_factura = None  # type: ignore

logger = logging.getLogger("responder_glosas_dgh")

COD_RESPUESTA_DEFAULT = "RE9901"  # "no acepta / glosa justificada subsanada"


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


# ─── Conexión a DG ───────────────────────────────────────────────────────────


def _pid_dg(nombre_exe: str = "DG.WinDG.exe") -> int | None:
    import subprocess

    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {nombre_exe}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        for linea in out.splitlines():
            if nombre_exe.lower() in linea.lower():
                campos = [c.strip().strip('"') for c in linea.split(",")]
                if len(campos) >= 2 and campos[1].isdigit():
                    return int(campos[1])
    except Exception:
        pass
    return None


def _conectar(pid: int):
    from pywinauto import Application

    app = Application(backend="uia").connect(process=pid, timeout=10)
    win = app.window(auto_id="DGFRMPrincipal", control_type="Window")
    win.wait("visible", timeout=15)
    return app, win


# ─── Helpers de UIA ──────────────────────────────────────────────────────────


def _buscar(parent, *, auto_id=None, control_type=None, name=None, name_re=None, timeout=10):
    """Devuelve un WindowSpecification del primer descendiente que matchee, o
    None tras `timeout` s.

    CLAVE: devuelve un *spec* (no un wrapper). Un WindowSpecification soporta
    tanto `.child_window()` (para anidar búsquedas) como los métodos de acción
    (`.click_input()`, `.type_keys()`, `.rectangle()`, …) por proxy al wrapper.
    Si devolviéramos `wrapper_object()`, las búsquedas anidadas fallarían: los
    wrappers de pywinauto NO tienen `.child_window()`.

    `found_index=0` fija la primera coincidencia → el spec nunca es ambiguo."""
    fin = time.time() + timeout
    crit = {}
    if auto_id:
        crit["auto_id"] = auto_id
    if control_type:
        crit["control_type"] = control_type
    if name:
        crit["title"] = name
    if name_re:
        crit["title_re"] = name_re
    while time.time() < fin:
        try:
            if parent.child_window(**crit).exists():
                return parent.child_window(**crit, found_index=0)
        except Exception:
            pass
        time.sleep(0.4)
    return None


def _foco_actual() -> tuple[str, str]:
    """(auto_id, name) del control que tiene el foco AHORA (vía UIA). Sirve para
    saber en qué campo estamos al tabular (los editores DevExpress comparten
    estructura y 'aparecer en el árbol' no implica tener el foco)."""
    try:
        from pywinauto.uia_defines import IUIA

        el = IUIA().iuia.GetFocusedElement()
        return (el.CurrentAutomationId or "", el.CurrentName or "")
    except Exception:
        return ("", "")


def _escapar(t: str) -> str:
    """Escapa caracteres especiales de type_keys ({}()+^%~)."""
    for ch in "{}":
        t = t.replace(ch, "{" + ch + "}")
    for ch in "+^%~()":
        t = t.replace(ch, "{" + ch + "}")
    return t


def _dump(etiqueta: str) -> None:
    """Vuelca TODAS las ventanas top-level del proceso DG (incluye modales/
    diálogos transitorios) usando el walker robusto de dump_dg.py."""
    from contextlib import redirect_stdout
    from io import StringIO

    try:
        from dump_dg import _walk
        from pywinauto import Application
    except Exception as e:
        logger.warning(f"  no pude preparar el volcado: {e}")
        return
    pid = _pid_dg()
    if pid is None:
        return
    out = Path(f"dump_dgh_{etiqueta}_{time.strftime('%H%M%S')}.txt")
    buf = StringIO()
    try:
        app = Application(backend="uia").connect(process=pid, timeout=5)
        with redirect_stdout(buf):
            for w in app.windows():
                print(f"========== {w.window_text()!r} ==========")
                _walk(w, 0, 12)
        out.write_text(buf.getvalue() or "(vacío)", encoding="utf-8")
        logger.info(f"  volcado de diagnóstico: {out.resolve()}")
    except Exception as e:
        logger.warning(f"  no pude volcar {etiqueta}: {e}")


def _hwnds_modal() -> list[int]:
    """HWNDs de la(s) ventana(s) cuyo título es el del modal de conceptos.
    win32 EnumWindows ve ventanas top-level (incluidas las propias/owned) que la
    enumeración UIA Desktop().windows() no lista."""
    try:
        from pywinauto import findwindows

        return list(findwindows.find_windows(title_re="Conceptos del tr.mite de objeci.n"))
    except Exception:
        return []


# ─── Modal de conceptos: llenado por COORDENADAS ─────────────────────────────
# El interior del modal es WPF y es OPACO a UIA/win32 por todas las vías probadas
# (árbol desde DGFRMPrincipal, conexión al HWND propio, win32, y GetFocusedElement
# tabulando: siempre devuelve la Window, nunca el campo). PERO el input real de
# mouse/teclado SÍ llega (el usuario lo llena a mano). Por eso lo manejamos por
# COORDENADAS de pantalla, calculadas desde el rect REAL del modal en runtime.
#
# Offsets (x, y) de cada control medidos desde la esquina sup-izq del modal en las
# capturas del usuario (modal en 360,166 @ 1920x1080). Son relativos al rect real,
# así siguen andando si el modal abre en otra posición. Si algún target cae
# corrido, se ajustan estos números — usar --calibrar (mueve el mouse SIN clickear
# para verificar dónde caería cada click).
_MODAL_REF_TL = (360, 166)
_MODAL_OFFSETS = {
    "grabar": (50, 51),  # botón GRABAR (toolbar del modal)
    "concepto": (150, 83),  # combo Concepto (fila superior, izq)
    "observaciones": (130, 109),  # campo Observaciones (fila debajo de Concepto)
    "aplicar": (1029, 135),  # botón "Aplicar campos"
    "check_fila": (47, 296),  # checkbox de la fila del concepto en la grilla
}


def _rect_modal(hwnd):
    """(L, T, R, B) del modal en pantalla, o None."""
    try:
        from pywinauto import Application

        w = Application(backend="uia").connect(handle=hwnd, timeout=5).window(handle=hwnd)
        r = w.rectangle()
        return (r.left, r.top, r.right, r.bottom)
    except Exception as e:
        logger.warning(f"  no pude leer el rect del modal: {e}")
        return None


def _targets_modal(hwnd):
    """{nombre: (x, y)} absolutos de cada control, desde el rect real del modal."""
    rect = _rect_modal(hwnd)
    if rect is None:
        return None
    left, top = rect[0], rect[1]
    return {k: (left + ox, top + oy) for k, (ox, oy) in _MODAL_OFFSETS.items()}


def _click_abs(x: int, y: int, doble: bool = False) -> None:
    from pywinauto import mouse

    if doble:
        mouse.double_click(button="left", coords=(int(x), int(y)))
    else:
        mouse.click(button="left", coords=(int(x), int(y)))


def _calibrar_modal(hwnd) -> None:
    """Mueve el mouse a cada target SIN clickear (2s de pausa + log), para verificar
    que las coordenadas caen sobre los controles. Riesgo cero."""
    from pywinauto import mouse

    tg = _targets_modal(hwnd)
    if tg is None:
        logger.error("  no pude leer el rect del modal para calibrar.")
        return
    logger.info(f"  rect del modal: {_rect_modal(hwnd)}")
    logger.info("  ── calibración: mirá dónde queda el cursor en cada paso ──")
    for nombre, (x, y) in tg.items():
        logger.info(f"    → {nombre}: mouse a ({x},{y})")
        try:
            mouse.move(coords=(int(x), int(y)))
        except Exception as e:
            logger.warning(f"      no pude mover el mouse: {e}")
        time.sleep(2.0)
    logger.info("  calibración lista. Decime qué targets caen corridos y ajusto los offsets.")


def _responder_modal(hwnd, cod_respuesta: str, detalle: str, grabar: bool, dump_al_fallar: bool):
    """Llena el modal por coordenadas: selecciona la fila → Concepto=RE9901 →
    Observaciones → 'Aplicar campos' → (si --grabar) GRABAR."""
    from pywinauto.keyboard import send_keys

    tg = _targets_modal(hwnd)
    if tg is None:
        logger.error("  no pude leer el rect del modal para responder.")
        return "ERROR_MODAL"

    # 1) Seleccionar la fila del concepto (checkbox). El usuario recalcó que la
    #    factura/fila SIEMPRE debe estar tildada para 'Aplicar campos' + GRABAR.
    logger.info(f"  1) tildo la fila (checkbox) en {tg['check_fila']}")
    _click_abs(*tg["check_fila"])
    time.sleep(0.5)

    # 2) Concepto = RE9901 (click en el combo → borrar → tipear → ENTER para que
    #    el lookup fije el código y autocomplete el nombre).
    logger.info(f"  2) Concepto={cod_respuesta} en {tg['concepto']}")
    _click_abs(*tg["concepto"])
    time.sleep(0.4)
    send_keys("^a{DEL}")
    send_keys(_escapar(cod_respuesta), pause=0.04)
    time.sleep(0.4)
    send_keys("{ENTER}")
    time.sleep(0.5)

    # 3) Observaciones = detalle de respuesta del Excel.
    logger.info(f"  3) Observaciones en {tg['observaciones']} ({len(detalle)} chars)")
    _click_abs(*tg["observaciones"])
    time.sleep(0.4)
    send_keys("^a{DEL}")
    if detalle:
        send_keys(_escapar(detalle), with_spaces=True, pause=0.005)
    time.sleep(0.4)

    # 4) Aplicar campos (copia Concepto+Observaciones a la fila tildada).
    logger.info(f"  4) 'Aplicar campos' en {tg['aplicar']}")
    _click_abs(*tg["aplicar"])
    time.sleep(1.0)

    if not grabar:
        logger.warning(
            "  ✓ modal LLENADO (SIN grabar). Revisá que Concepto/Observaciones/valor "
            "quedaron en la fila y que está tildada. Si está OK, corré con --grabar."
        )
        return "MODAL_LLENADO"

    # 5) GRABAR.
    logger.info(f"  5) GRABAR en {tg['grabar']}")
    _click_abs(*tg["grabar"])
    time.sleep(2.0)
    if dump_al_fallar:
        _dump("dialogo_grabado")  # el diálogo 'Registro grabado' SÍ es ventana normal
    logger.warning(
        "  ⚠ GRABAR clickeado. El diálogo 'Registro grabado' (Confirmar/Imprimir) "
        "aún no está automatizado: confirmá/imprimí a mano. Con --dump-al-fallar lo "
        "capturé para automatizarlo."
    )
    return "GRABADO_SIN_DIALOGO"


def _diag_grids(win):
    """Loguea cuántas grillas gcConceptosObjecion hay y si cada una tiene fila.
    Sirve para diagnosticar 'no autocargó' sin pedir un dump."""
    n = 0
    for i in range(40):
        try:
            grid = win.child_window(auto_id="gcConceptosObjecion", found_index=i)
            if not grid.exists():
                break
        except Exception:
            break
        n += 1
        tiene_dp = tiene_fila = False
        try:
            datos = grid.child_window(auto_id="dataPresenter")
            tiene_dp = datos.exists()
            if tiene_dp:
                tiene_fila = datos.child_window(control_type="DataItem").exists()
        except Exception:
            pass
        logger.info(f"    diag grid #{i}: dataPresenter={tiene_dp} fila={tiene_fila}")
    logger.info(f"    diag: {n} grilla(s) gcConceptosObjecion visibles en el árbol de DG")


def _grid_con_fila(win):
    """dataPresenter (spec) de la PRIMERA grilla 'gcConceptosObjecion' cuyo panel
    de datos tiene una fila (DataItem), sin importar en qué pestaña Editor esté.
    Robusto a editores duplicados y a la carga asíncrona: una grilla vacía
    (Record 0 of 0) tiene dataPresenter pero NO DataItem, así distinguimos la
    autocargada. Devuelve None si ninguna grilla tiene fila."""
    for i in range(40):
        try:
            grid = win.child_window(auto_id="gcConceptosObjecion", found_index=i)
            if not grid.exists():
                break
        except Exception:
            break
        try:
            datos = grid.child_window(auto_id="dataPresenter")
            if datos.exists() and datos.child_window(control_type="DataItem").exists():
                return grid.child_window(auto_id="dataPresenter", found_index=0)
        except Exception:
            continue
    return None


# ─── Flujo por factura ───────────────────────────────────────────────────────


def procesar_factura(
    win, factura_larga, objeciones, cod_respuesta, grabar, dump_al_fallar, calibrar
):
    logger.info(f"[{factura_larga}] {len(objeciones)} objeción(es)")

    # 1) Activar 'Listado de Tramite de Objeción' y darle AGREGAR para abrir un
    #    Editor nuevo. CLAVE (causa raíz de "no abrió el Editor"): hay que traer DG
    #    al FRENTE primero (win.set_focus). Si DG no está en foreground, el primer
    #    click se consume como click de ACTIVACIÓN y el botón no dispara — se ve el
    #    tooltip "AGREGAR (Ctrl+N)" pero el Editor no abre. Por eso, además del
    #    click, usamos el atajo Ctrl+N (que el propio tooltip revela) y verificamos
    #    que el Editor realmente aparezca.
    from pywinauto.keyboard import send_keys

    try:
        win.set_focus()
        time.sleep(0.4)
    except Exception:
        pass
    tab_listado = _buscar(win, name_re="Listado de Tr.mite", control_type="TabItem", timeout=5)
    if tab_listado is not None:
        try:
            tab_listado.click_input()
            time.sleep(0.6)
            win.set_focus()  # re-asegurar foreground tras activar la pestaña
            time.sleep(0.3)
        except Exception:
            pass

    def _esperar_editor(segundos):
        fin_ = time.time() + segundos
        while time.time() < fin_:
            te = _buscar(win, name_re="Editor de Tr.mite", control_type="TabItem", timeout=1)
            if te is not None:
                return te
            time.sleep(0.4)
        return None

    # AGREGAR: 1º por click (auto_id único; fallback por nombre).
    agregar = _buscar(win, auto_id="BarButtonItemLinkbbiAgregar", control_type="Button", timeout=8)
    if agregar is None:
        agregar = _buscar(win, name="AGREGAR", control_type="Button", timeout=4)
    if agregar is None:
        logger.error(
            "  no hallé AGREGAR. Abrí 'Listado de Tramite de Objeción' (Cartera→Procesos→Tramite de Objeción)."
        )
        if dump_al_fallar:
            _dump("sin_agregar")
        return "ERROR_NAV"
    try:
        agregar.click_input()
    except Exception:
        pass
    tab_editor = _esperar_editor(6)
    # Si el click no disparó (DG no estaba al frente / WPF ocupado), atajo Ctrl+N.
    if tab_editor is None:
        logger.info("  AGREGAR por click no abrió el Editor; pruebo el atajo Ctrl+N…")
        try:
            win.set_focus()
            time.sleep(0.3)
            send_keys("^n")
        except Exception:
            pass
        tab_editor = _esperar_editor(8)
    if tab_editor is None:
        logger.error(
            "  AGREGAR no abrió el Editor (ni por click ni por Ctrl+N). ¿Estaba el "
            "'Listado de Tramite de Objeción' al frente y DG visible al correr?"
        )
        if dump_al_fallar:
            _dump("sin_editor")
        return "ERROR_NAV"
    # Activar la pestaña Editor recién abierta.
    try:
        tab_editor.click_input()
        time.sleep(0.6)
    except Exception:
        pass

    # 2) Ir al campo Factura operando por FOCO. Anclamos el foco en el Editor
    #    (DG ya está al frente) clickeando Consecutivo (primer campo); de ahí TAB
    #    hasta que el control con foco real se llame 'Factura' (orden
    #    Consecutivo→Fecha→[Estado]→Factura).
    try:
        win.set_focus()
        time.sleep(0.5)
    except Exception:
        pass
    cons = _buscar(win, auto_id="ctrlConsecutivo", timeout=8)
    if cons is None:
        logger.error(
            "  no hallé Consecutivo para anclar el foco. ¿Se abrió el Editor tras AGREGAR?"
        )
        if dump_al_fallar:
            _dump("sin_consecutivo")
        return "ERROR_FACTURA"
    try:
        cons.click_input()
        time.sleep(0.4)
    except Exception as e:
        logger.warning(f"  no pude clickear Consecutivo para anclar el foco: {e}")
    _, nm0 = _foco_actual()
    if nm0 not in ("Consecutivo", "Factura") and "Consecutivo" not in nm0:
        logger.warning(
            f"  ⚠ tras anclar, el foco está en {nm0!r} (no en el Editor). NO toques el "
            "mouse/teclado mientras corre el bot."
        )

    en_factura = False
    for intento in range(20):
        aid, nm = _foco_actual()
        if nm == "Factura" or aid == "ctrlFactura":
            logger.info(f"  Factura enfocada tras {intento} TAB(s).")
            en_factura = True
            break
        send_keys("{TAB}")
        time.sleep(0.4)
    if not en_factura:
        aid, nm = _foco_actual()
        logger.error(
            f"  no llegué a Factura (último foco: name={nm!r} auto_id={aid!r}). Mandame el dump."
        )
        if dump_al_fallar:
            _dump("sin_factura")
        return "ERROR_FACTURA"
    time.sleep(0.3)
    send_keys("^a{DEL}")
    send_keys(_escapar(factura_larga) + "{ENTER}")
    logger.info(f"  factura {factura_larga} escrita; esperando autocargue…")

    # 3) Autocargue ASÍNCRONO (DevExpress.Data.Async). La factura resuelve el
    #    encabezado enseguida, pero la grilla de conceptos llega después por carga
    #    asíncrona; en sesiones de DG "cansadas" (varias corridas) puede tardar
    #    bastante (se vio ~70s). Poll hasta que ALGUNA grilla gcConceptosObjecion
    #    tenga su fila, hasta 120s, con aviso de progreso + diag cada 15s.
    datos = None
    espera_max = 120
    fin = time.time() + espera_max
    prox_aviso = time.time() + 15
    while time.time() < fin:
        datos = _grid_con_fila(win)
        if datos is not None:
            break
        if time.time() >= prox_aviso:
            logger.info(f"  … aún esperando autocargue ({int(fin - time.time())}s restantes)")
            _diag_grids(win)
            prox_aviso = time.time() + 15
        time.sleep(0.8)
    if datos is None:
        logger.error(
            f"  la factura no autocargó (ninguna grilla con fila en {espera_max}s). "
            "Si la pantalla SÍ muestra la grilla cargada, la sesión de DG está muy "
            "lenta: reiniciá DG fresco (con DG fresco autocarga en ~4s)."
        )
        _diag_grids(win)
        if dump_al_fallar:
            _dump("sin_autocargue")
        return "NO_AUTOCARGA"
    logger.info("  ✓ datos autocargados (grilla con fila).")

    # 4) Abrir el MODAL de respuesta. La respuesta NO se edita inline en esta
    #    grilla: hay que dar DOBLE-CLICK en la fila de concepto, lo que abre el
    #    modal "Conceptos del trámite de objeción" donde se carga la respuesta
    #    (Concepto RE9901 / Valor aceptado / Observaciones / Aceptar / Grabar).
    fila = _buscar(datos, control_type="DataItem", timeout=5)
    if fila is None:
        logger.error("  no hallé la fila de concepto para doble-click.")
        if dump_al_fallar:
            _dump("sin_fila")
        return "ERROR_FILA"
    try:
        fila.double_click_input()
    except Exception as e:
        logger.warning(f"  fallo doble-click en la fila: {e}")
    time.sleep(2.0)
    logger.info("  doble-click en la fila; modal de respuesta abierto.")
    # El interior del modal es WPF y es OPACO a UIA/win32 (probado por 4 vías: árbol
    # desde DGFRMPrincipal, conexión a su HWND, win32, y GetFocusedElement tabulando
    # —siempre devolvió la Window—). Se maneja por COORDENADAS sobre el rect real
    # del modal (ver _responder_modal / _calibrar_modal).
    hwnds = _hwnds_modal()
    if not hwnds:
        logger.error("  no encontré el HWND del modal para responder.")
        if dump_al_fallar:
            _dump("sin_modal")
        return "ERROR_MODAL"
    hwnd = hwnds[0]
    if calibrar:
        _calibrar_modal(hwnd)
        return "CALIBRACION"
    detalle = objeciones[0].get("detalle", "") if objeciones else ""
    return _responder_modal(hwnd, cod_respuesta, detalle, grabar, dump_al_fallar)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Carga respuestas de glosa en DGH (Trámite de Objeción). v1 piloto.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--excel", type=Path, required=True, help="Excel de respuestas (igual que SIMED)."
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--solo", type=str, help="Procesar SOLO esta factura (recomendado en v1).")
    grupo.add_argument(
        "--todas", action="store_true", help="Todas las facturas (NO recomendado hasta validar v1)."
    )
    parser.add_argument(
        "--cod-respuesta",
        default=COD_RESPUESTA_DEFAULT,
        help=f"Código RE por defecto (default {COD_RESPUESTA_DEFAULT}).",
    )
    parser.add_argument(
        "--grabar", action="store_true", help="Grabar de verdad (por defecto NO graba: piloto)."
    )
    parser.add_argument(
        "--calibrar",
        action="store_true",
        help="Sólo mueve el mouse a cada control del modal (SIN clickear) para verificar "
        "coordenadas. Riesgo cero; no llena ni graba.",
    )
    parser.add_argument(
        "--dump-al-fallar",
        action="store_true",
        help="Volcar el árbol de controles si algo no se encuentra.",
    )
    parser.add_argument(
        "--lento", type=int, default=0, help="Pausa extra (segundos) entre pasos para mirar."
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    if sys.platform != "win32":
        logger.error("Solo corre en Windows (DGH es .NET nativo).")
        return 2
    if leer_excel_respuestas is None:
        logger.error("No pude importar responder_glosas_simed (debe estar en tools/).")
        return 2
    try:
        import pywinauto  # noqa: F401
    except ImportError:
        logger.error("Falta pywinauto:  py -m pip install pywinauto")
        return 2

    facturas = leer_excel_respuestas(args.excel)
    if args.solo:
        objetivo = normalizar_factura(args.solo)
        facturas = {k: v for k, v in facturas.items() if k == objetivo}
        if not facturas:
            logger.error(f"No hallé la factura {args.solo} en el Excel.")
            return 1
    logger.info(f"Facturas a procesar: {len(facturas)}")

    pid = _pid_dg()
    if pid is None:
        logger.error(
            "DG.WinDG.exe no está corriendo. Abrí y logueá DG (o corré tools\\login_dg.py)."
        )
        return 1
    logger.info(f"Conectado a DG (PID {pid}).")
    _app, win = _conectar(pid)

    resultados = []
    for factura_corta, objeciones in facturas.items():
        factura_larga = objeciones[0]["factura"]
        try:
            estado = procesar_factura(
                win,
                factura_larga,
                objeciones,
                args.cod_respuesta,
                args.grabar,
                args.dump_al_fallar,
                args.calibrar,
            )
        except Exception as e:
            logger.error(f"  ✗ {factura_larga}: {type(e).__name__}: {e}")
            estado = "ERROR"
        resultados.append((factura_larga, estado))
        if args.lento:
            time.sleep(args.lento)

    logger.info("\nResumen:")
    for f, e in resultados:
        logger.info(f"  {f}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
