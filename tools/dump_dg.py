"""dump_dg.py — Vuelca el árbol de controles UIA de Dinámica Gerencial .NET
para poder escribir selectores de automatización (pywinauto).

Es una herramienta de DIAGNÓSTICO de solo-lectura: no toca ni modifica nada en
DG, solo inspecciona y guarda el árbol de controles a un archivo de texto.

IMPORTANTE — DG es UNA sola ventana ('Dinámica Gerencial .NET' / DGFRMPrincipal).
El "Editor de Trámite de Objeción" NO es una ventana aparte: es una PESTAÑA
dentro de esa ventana. Por eso, para volcar el Editor, hay que dejar esa
pestaña ACTIVA (al frente) en el momento de capturar. Los modales (p.ej.
"Conceptos del trámite de objeción", "Registro grabado correctamente") SÍ son
ventanas separadas: hay que tenerlos ABIERTOS al capturar.

Por eso este script usa una ESPERA con cuenta regresiva: lo lanzás, te cambiás
a DG, dejás al frente la pantalla/modal que querés, y cuando termina la cuenta
vuelca TODAS las ventanas top-level del proceso.

USO
---
    cd C:\\temp-notas

    REM 1) Editor: abrí el Editor (AGREGAR), cargá una factura, y al frente esa pestaña.
    py tools\\dump_dg.py --espera 8 --salida dump_editor.txt

    REM 2) Modal: abrí el modal (doble-click en un concepto) y dejalo al frente.
    py tools\\dump_dg.py --espera 8 --salida dump_modal.txt

    REM 3) Diálogo "Registro grabado correctamente": cuando aparezca, dejalo al frente.
    py tools\\dump_dg.py --espera 8 --salida dump_dialogo.txt

Flags:
    --espera N   segundos de cuenta regresiva antes de capturar (default 8).
    --depth N    profundidad del árbol (default 14).
    --pid N      PID de DG.WinDG.exe (si hay varios; normalmente no hace falta).
    --salida F   archivo .txt de salida.

DEPENDENCIAS
------------
    py -m pip install pywinauto

NOTA: solo corre en Windows.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path


def _pids_dg(nombre_exe: str = "DG.WinDG.exe") -> list[int]:
    import subprocess

    pids: list[int] = []
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
                    pids.append(int(campos[1]))
    except Exception:
        pass
    return pids


def _info(ctrl):
    """Extrae atributos de un control de forma defensiva (element_info)."""
    ei = getattr(ctrl, "element_info", None)
    g = lambda k, d="": getattr(ei, k, d) if ei is not None else d  # noqa: E731
    rect = g("rectangle", "")
    return {
        "ct": g("control_type", "?"),
        "name": g("name", ""),
        "aid": g("automation_id", ""),
        "cls": g("class_name", ""),
        "rect": str(rect),
    }


def _walk(ctrl, depth: int, max_depth: int, indent: int = 0) -> None:
    """Recorrido propio del árbol (no usa print_control_identifiers, que crashea
    en algunos wrappers). Imprime tipo/nombre/auto_id/clase/rect por control."""
    d = _info(ctrl)
    pad = "  " * indent
    print(
        f"{pad}{d['ct']} | name={d['name']!r} | auto_id={d['aid']!r} | class={d['cls']!r} | {d['rect']}"
    )
    if depth >= max_depth:
        return
    try:
        hijos = ctrl.children()
    except Exception as e:
        print(f"{pad}  <no pude leer hijos: {e}>")
        return
    for h in hijos:
        _walk(h, depth + 1, max_depth, indent + 1)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--espera", type=int, default=8, help="Segundos de cuenta regresiva (default 8)."
    )
    p.add_argument("--depth", type=int, default=14, help="Profundidad del árbol (default 14).")
    p.add_argument("--pid", type=int, default=None, help="PID de DG.WinDG.exe (si hay varios).")
    p.add_argument("--salida", type=Path, default=None, help="Archivo .txt de salida.")
    args = p.parse_args()

    if sys.platform != "win32":
        sys.stderr.write("Solo corre en Windows.\n")
        return 2
    try:
        from pywinauto import Application
    except ImportError:
        sys.stderr.write("ERROR: falta pywinauto.\n    py -m pip install pywinauto\n")
        return 2

    pids = [args.pid] if args.pid else _pids_dg()
    if not pids:
        sys.stderr.write("No encontré DG.WinDG.exe corriendo. Abrí DG primero.\n")
        return 1

    # Cuenta regresiva: el usuario trae al frente la pantalla/modal a capturar.
    if args.espera > 0:
        print("Cambiate a DG y dejá AL FRENTE la pantalla/modal que querés volcar.")
        for s in range(args.espera, 0, -1):
            print(f"  capturando en {s}s…", end="\r", flush=True)
            time.sleep(1)
        print(" " * 40, end="\r")
        print("Capturando ahora.")

    salida = args.salida or Path(f"dump_dg_{time.strftime('%H%M%S')}.txt")
    buf = io.StringIO()
    with redirect_stdout(buf):
        for pid in pids:
            print(f"==================== PID {pid} ====================")
            try:
                app = Application(backend="uia").connect(process=pid, timeout=5)
            except Exception as e:
                print(f"  no pude conectar al PID {pid}: {e}")
                continue
            try:
                ventanas = app.windows()
            except Exception as e:
                print(f"  no pude listar ventanas: {e}")
                continue
            print(f"--- {len(ventanas)} ventana(s) top-level ---")
            for w in ventanas:
                try:
                    print(f"  · {w.window_text()!r}  class={w.class_name()!r}")
                except Exception:
                    pass
            for w in ventanas:
                try:
                    titulo = w.window_text()
                except Exception:
                    titulo = "?"
                print(f"\n========== ÁRBOL de {titulo!r} (depth={args.depth}) ==========")
                _walk(w, 0, args.depth)

    contenido = buf.getvalue()
    salida.write_text(contenido, encoding="utf-8")
    print(f"Volcado escrito en: {salida.resolve()}  ({contenido.count(chr(10))} líneas)")
    print("Mandame ese archivo .txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
