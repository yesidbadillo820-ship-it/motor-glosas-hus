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


def _buscar(parent, *, auto_id=None, control_type=None, name=None, timeout=10):
    """Devuelve el primer descendiente que matchee, o None tras `timeout` s."""
    fin = time.time() + timeout
    crit = {}
    if auto_id:
        crit["auto_id"] = auto_id
    if control_type:
        crit["control_type"] = control_type
    if name:
        crit["title"] = name
    while time.time() < fin:
        try:
            ctl = parent.child_window(**crit)
            if ctl.exists():
                return ctl.wrapper_object()
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


# ─── Flujo por factura ───────────────────────────────────────────────────────


def procesar_factura(win, factura_larga, objeciones, cod_respuesta, grabar, dump_al_fallar):
    logger.info(f"[{factura_larga}] {len(objeciones)} objeción(es)")

    # 1) AGREGAR (toolbar del Listado o del Editor) → abre Editor en blanco.
    agregar = _buscar(win, name="AGREGAR", control_type="Button", timeout=10)
    if agregar is None:
        logger.error(
            "  no hallé el botón AGREGAR. ¿Está abierta la pantalla 'Listado de Tramite de Objeción'?"
        )
        if dump_al_fallar:
            _dump("sin_agregar")
        return "ERROR_NAV"
    agregar.click_input()
    time.sleep(1.5)

    # 2) Escribir la Factura → DG autocarga los datos de la objeción.
    factura_ctl = _buscar(win, auto_id="ctrlFactura", timeout=10)
    if factura_ctl is None:
        logger.error("  no hallé el campo Factura (ctrlFactura).")
        if dump_al_fallar:
            _dump("sin_factura")
        return "ERROR_FACTURA"
    _set_editor(factura_ctl, factura_larga)
    factura_ctl.type_keys("{ENTER}")
    logger.info(f"  factura {factura_larga} escrita; esperando autocargue…")

    # 3) Esperar a que cargue (el Tercero deja de estar vacío).
    cargado = False
    fin = time.time() + 20
    while time.time() < fin:
        tercero = _buscar(win, auto_id="ctrlTercero", timeout=1)
        try:
            if tercero is not None and (tercero.window_text() or "").strip():
                cargado = True
                break
        except Exception:
            pass
        time.sleep(0.5)
    if not cargado:
        logger.error("  la factura no autocargó (Tercero vacío). ¿Número correcto / ya tramitada?")
        if dump_al_fallar:
            _dump("sin_autocargue")
        return "NO_AUTOCARGA"
    logger.info("  ✓ datos de la factura autocargados.")

    # 4) Llenar la grilla de conceptos (gcConceptosObjecion), fila por fila.
    grid = _buscar(win, auto_id="gcConceptosObjecion", timeout=10)
    if grid is None:
        logger.error("  no hallé la grilla de conceptos (gcConceptosObjecion).")
        if dump_al_fallar:
            _dump("sin_grilla")
        return "ERROR_GRILLA"
    # Las celdas de DATOS comparten auto_id con la fila de filtros y el footer;
    # hay que buscarlas DENTRO del panel de datos (dataPresenter) para no agarrar
    # la celda equivocada.
    datos = _buscar(grid, auto_id="dataPresenter", timeout=5) or grid

    # Las celdas de respuesta editables exponen auto_id = binding:
    #   ConceptoObjecion.Codigo  → código de respuesta (RE9901)
    #   ValorAceptado            → valor aceptado
    #   Observaciones            → detalle
    respondidas = 0
    for i, ob in enumerate(objeciones, start=1):
        detalle = sanitizar(ob["detalle"]) if sanitizar else ob["detalle"]
        logger.info(
            f"  → objeción #{ob['num']}: {cod_respuesta}, aceptado={ob['aceptado']}, {len(detalle)} chars"
        )
        cel_cod = _buscar(datos, auto_id="ConceptoObjecion.Codigo", timeout=4)
        cel_val = _buscar(datos, auto_id="ValorAceptado", timeout=2)
        cel_obs = _buscar(datos, auto_id="Observaciones", timeout=2)
        if not all([cel_cod, cel_val, cel_obs]):
            logger.error(
                "  no hallé las celdas de respuesta en la grilla (inline). Vuelco para revisar."
            )
            if dump_al_fallar:
                _dump("sin_celdas")
            return "ERROR_CELDAS"
        # Código de respuesta: doble-click para entrar en edición, tipear, Enter.
        try:
            cel_cod.double_click_input()
            time.sleep(0.2)
            cel_cod.type_keys(cod_respuesta + "{ENTER}", with_spaces=True, pause=0.03)
        except Exception as e:
            logger.warning(f"  fallo set código respuesta: {e}")
        # Valor aceptado.
        try:
            cel_val.double_click_input()
            time.sleep(0.15)
            cel_val.type_keys("^a{DEL}" + str(ob["aceptado"]) + "{ENTER}", pause=0.03)
        except Exception as e:
            logger.warning(f"  fallo set valor aceptado: {e}")
        # Observaciones (MemoEdit).
        try:
            cel_obs.double_click_input()
            time.sleep(0.15)
            cel_obs.type_keys("^a{DEL}", pause=0.03)
            cel_obs.type_keys(_escapar(detalle), with_spaces=True, pause=0.005)
            cel_obs.type_keys("{ENTER}")
        except Exception as e:
            logger.warning(f"  fallo set observaciones: {e}")
        respondidas += 1
        # NOTA v1: si hay >1 objeción, mover el foco de fila requiere lógica
        # adicional (la grilla DevExpress edita la fila activa). Por ahora
        # avisamos y procesamos sólo la fila activa de forma confiable.
        if len(objeciones) > 1 and i == 1:
            logger.warning(
                "  ⚠ v1: esta factura tiene varias objeciones; el bot llenó la fila activa. "
                "Verificá las demás filas manualmente o esperá v2 (navegación de filas)."
            )
            break

    logger.info(f"  ✓ {respondidas} fila(s) llenada(s).")

    if not grabar:
        logger.info("  (PILOTO: no grabo. Revisá en pantalla. Usá --grabar para confirmar.)")
        return "PILOTO_OK"

    # 5) GRABAR + diálogo 'Registro grabado' (Confirmar=Sí, Imprimir=Sí).
    grabar_btn = _buscar(win, name="GRABAR", control_type="Button", timeout=5)
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
