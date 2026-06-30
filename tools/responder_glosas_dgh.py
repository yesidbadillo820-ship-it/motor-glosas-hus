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
    REM Piloto seguro (NO graba; sólo llena para que verifiques):
    py tools\\responder_glosas_dgh.py --excel "D:\\...\\respuestas.xlsx" --solo HUS0000516474

    REM Cuando confíes, que grabe + confirme + imprima el PDF de evidencia:
    py tools\\responder_glosas_dgh.py --excel "D:\\...\\respuestas.xlsx" --solo HUS0000516474 --grabar

    REM Volcar el modal/diálogo si hace falta afinar selectores:
    py tools\\responder_glosas_dgh.py --excel ... --solo HUS... --dump-al-fallar

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
        sanitizar,
    )
except Exception:  # pragma: no cover - sólo si se mueve el archivo
    leer_excel_respuestas = normalizar_factura = sanitizar = None  # type: ignore

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


def _set_editor(ctl, texto: str) -> bool:
    """Escribe en un editor DevExpress (PART_Editor TextBox dentro del control).
    Click → seleccionar todo → tipear."""
    try:
        editor = ctl.child_window(auto_id="PART_Editor", control_type="Edit")
        target = editor.wrapper_object() if editor.exists() else ctl
    except Exception:
        target = ctl
    try:
        target.click_input()
        time.sleep(0.2)
        target.type_keys("^a{DEL}", pause=0.03)
        target.type_keys(_escapar(texto), with_spaces=True, pause=0.01)
        return True
    except Exception as e:
        logger.warning(f"  no pude escribir {texto!r}: {e}")
        return False


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


def _modal_conceptos(timeout: float = 12.0):
    """Devuelve un WindowSpecification del modal 'Conceptos del trámite de
    objeción', o None.

    CLAVE: el modal es una ventana WPF hosteada dentro de la app WinForms. Su
    INTERIOR (Concepto / Observaciones / Aplicar campos / la grilla de conceptos
    / GRABAR) NO es alcanzable caminando el árbol desde DGFRMPrincipal: el
    recorrido se corta en el borde WinForms→WPF y sólo expone el TitleBar del
    modal (por eso los volcados anteriores nunca mostraron sus campos). Hay que
    tomar el modal como ventana TOP-LEVEL del escritorio, rooteando la búsqueda
    UIA en su propio HWND; recién ahí el proveedor WPF expone los controles
    internos."""
    try:
        from pywinauto import Desktop
    except Exception:
        return None
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            m = Desktop(backend="uia").window(
                title_re="Conceptos del tr.mite de objeci.n", control_type="Window"
            )
            if m.exists():
                return m
        except Exception:
            pass
        time.sleep(0.4)
    return None


def _hwnds_modal() -> list[int]:
    """HWNDs de la(s) ventana(s) cuyo título es el del modal de conceptos.
    win32 EnumWindows ve ventanas top-level (incluidas las propias/owned) que la
    enumeración UIA Desktop().windows() no lista."""
    try:
        from pywinauto import findwindows

        return list(findwindows.find_windows(title_re="Conceptos del tr.mite de objeci.n"))
    except Exception:
        return []


def _dump_modal(etiqueta: str) -> None:
    """Vuelca el INTERIOR del modal de conceptos probando VARIAS estrategias en
    UNA sola corrida. El modal es una ventana WPF *owned*: su interior no se
    alcanza caminando desde DGFRMPrincipal (sólo sale el TitleBar) y Desktop UIA
    no la lista como top-level. La forma robusta es localizar su HWND con win32 y
    rootear una conexión UIA fresca en ese HWND. Se escriben todas las secciones;
    la que tenga 'Aplicar campos' es la buena y de ahí salen los selectores."""
    from contextlib import redirect_stdout
    from io import StringIO

    try:
        from dump_dg import _walk
        from pywinauto import Application
    except Exception as e:
        logger.warning(f"  no pude importar dependencias del volcado ({e}); vuelco el proceso.")
        _dump(etiqueta)
        return

    out = Path(f"dump_dgh_{etiqueta}_{time.strftime('%H%M%S')}.txt")
    buf = StringIO()
    with redirect_stdout(buf):
        hwnds = _hwnds_modal()
        print(f"HWNDs del modal (win32): {hwnds}\n")

        # [A] Conexión UIA fresca rooteada en el HWND del modal (lo más probable).
        print("========== [A] UIA connect(handle=HWND del modal) ==========")
        if not hwnds:
            print("(sin HWND del modal)")
        for h in hwnds:
            try:
                app = Application(backend="uia").connect(handle=h, timeout=5)
                _walk(app.window(handle=h).wrapper_object(), 0, 18)
            except Exception as e:
                print(f"(error HWND {h}: {e})")

        # [B] Finder UIA del escritorio por título.
        print("\n========== [B] Desktop().window(title=...) ==========")
        try:
            m = _modal_conceptos(timeout=4)
            if m is not None:
                _walk(m.wrapper_object(), 0, 18)
            else:
                print("(no encontrado por finder)")
        except Exception as e:
            print(f"(error: {e})")

        # [C] win32: por si el modal expone controles nativos hijos.
        print("\n========== [C] win32 connect(handle=HWND del modal) ==========")
        for h in hwnds:
            try:
                appw = Application(backend="win32").connect(handle=h, timeout=5)
                _walk(appw.window(handle=h).wrapper_object(), 0, 18)
            except Exception as e:
                print(f"(error win32 HWND {h}: {e})")

    out.write_text(buf.getvalue() or "(vacío)", encoding="utf-8")
    logger.info(f"  volcado del modal (multi-estrategia): {out.resolve()}")


_CT_NOMBRES = {
    50000: "Button",
    50002: "CheckBox",
    50003: "ComboBox",
    50004: "Edit",
    50005: "RadioButton",
    50008: "DataItem",
    50011: "List",
    50020: "Text",
    50026: "Group",
    50032: "Window",
    50033: "Pane",
}


def _diag_foco_modal(hwnd, pasos: int = 28) -> None:
    """Con el modal abierto, enfoca su ventana y TABULA campo por campo, logueando
    el control con foco REAL en cada parada (GetFocusedElement funciona aunque el
    árbol WPF del modal no se pueda caminar por UIA). Revela el orden de tabulado
    y la identidad (control_type / auto_id / name) de cada campo, que es lo que se
    necesita para cablear el llenado por teclado.

    Sólo navega (TAB); no manda ENTER/SPACE, así no dispara botones ni cambia
    datos."""
    from pywinauto import Application
    from pywinauto.keyboard import send_keys
    from pywinauto.uia_defines import IUIA

    try:
        app = Application(backend="uia").connect(handle=hwnd, timeout=5)
        app.window(handle=hwnd).set_focus()
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"  no pude enfocar el modal para el diag de foco: {e}")
    logger.info("  ── secuencia de foco del modal (TAB por TAB) ──")
    for i in range(pasos):
        aid = nm = ""
        ct = 0
        try:
            el = IUIA().iuia.GetFocusedElement()
            aid = el.CurrentAutomationId or ""
            nm = el.CurrentName or ""
            ct = el.CurrentControlType
        except Exception:
            pass
        ctn = _CT_NOMBRES.get(ct, str(ct))
        logger.info(f"    foco modal #{i:02d}: [{ctn}] auto_id={aid!r} name={nm!r}")
        try:
            send_keys("{TAB}")
        except Exception:
            pass
        time.sleep(0.35)


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
    """(grid_spec, datos_spec) de la PRIMERA grilla 'gcConceptosObjecion' cuyo
    panel de datos tiene una fila (DataItem), sin importar en qué pestaña Editor
    esté. Robusto a editores duplicados y a la carga asíncrona: una grilla vacía
    (Record 0 of 0) tiene dataPresenter pero NO DataItem, así distinguimos la
    autocargada."""
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
                return grid, grid.child_window(auto_id="dataPresenter", found_index=0)
        except Exception:
            continue
    return None, None


# ─── Flujo por factura ───────────────────────────────────────────────────────


def procesar_factura(win, factura_larga, objeciones, cod_respuesta, grabar, dump_al_fallar):
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
    aid0, nm0 = _foco_actual()
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
    grid = datos = None
    espera_max = 120
    fin = time.time() + espera_max
    prox_aviso = time.time() + 15
    while time.time() < fin:
        grid, datos = _grid_con_fila(win)
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
    # El interior del modal es WPF y NO se puede caminar por UIA ni win32 (lo
    # confirmé: rooteando en su HWND, las 3 vías sólo dan el TitleBar). PERO el
    # control con FOCO sí se lee (GetFocusedElement). Así que en vez de volcar el
    # árbol, tabulamos por el modal y logueamos el foco en cada parada: eso revela
    # el orden y la identidad de los campos para cablear el llenado por teclado.
    hwnds = _hwnds_modal()
    if hwnds:
        _diag_foco_modal(hwnds[0])
    else:
        logger.warning("  no encontré el HWND del modal para el diag de foco.")
    logger.warning(
        "  ⚠ El interior del modal es WPF: NO se camina por UIA (las 3 vías sólo dieron "
        "el TitleBar). Pero el FOCO sí se lee. Pasame la secuencia 'foco modal #NN' de "
        "arriba y con eso cableo el llenado por teclado (fila → RE9901 → Observaciones → "
        "Aplicar campos → GRABAR)."
    )
    return "MODAL_ABIERTO"
    # ── (v2: aquí va el llenado del modal una vez tengamos sus auto_id) ──

    # 5) GRABAR + diálogo 'Registro grabado' (Confirmar=Sí, Imprimir=Sí).
    grabar_btn = _buscar(
        win, auto_id="BarButtonItemLink0", control_type="Button", timeout=4
    ) or _buscar(win, name="GRABAR", control_type="Button", timeout=4)
    if grabar_btn is None:
        logger.error("  no hallé el botón GRABAR.")
        if dump_al_fallar:
            _dump("sin_grabar")
        return "ERROR_GRABAR"
    grabar_btn.click_input()
    time.sleep(2.0)
    # El diálogo 'Registro grabado' (Confirmar/Imprimir) aún no lo capturamos;
    # con --dump-al-fallar lo volcamos JUSTO ahora que está en pantalla, para v2.
    if dump_al_fallar:
        _dump("dialogo_grabado")
    logger.warning(
        "  ⚠ v1: el diálogo 'Registro grabado' (Confirmar/Imprimir) aún no está "
        "automatizado. Confirmá/Imprimí a mano esta vez. Si corriste con "
        "--dump-al-fallar, ya quedó capturado para automatizarlo en v2."
    )
    return "GRABADO_SIN_DIALOGO"


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
                win, factura_larga, objeciones, args.cod_respuesta, args.grabar, args.dump_al_fallar
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
