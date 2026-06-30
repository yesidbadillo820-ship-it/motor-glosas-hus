"""dump_dg.py — Vuelca el árbol de controles UIA de una ventana de Dinámica
Gerencial .NET para poder escribir selectores de automatización (pywinauto).

Es una herramienta de DIAGNÓSTICO de solo-lectura: no toca ni modifica nada en
DG, solo inspecciona y guarda el árbol de controles a un archivo de texto.

USO
---
1. Dejá DG abierto en la pantalla que querés inspeccionar (p.ej. el "Editor de
   Trámite de Objeción", o el modal "Conceptos del trámite de objeción", o el
   diálogo "Registro grabado correctamente").
2. Corré:

       cd C:\\temp-notas
       py tools\\dump_dg.py --titulo "Editor de Tramite"
       py tools\\dump_dg.py --titulo "Conceptos del tramite"
       py tools\\dump_dg.py --titulo "Dinamica Gerencial"   REM el dialogo de grabado

   - --titulo: substring (sin tildes, case-insensitive) del título de la ventana
     a volcar. Si se omite, lista todas las ventanas top-level del proceso y
     vuelca la que esté en primer plano.
   - --depth: profundidad del árbol (default 10).
   - --salida: archivo de salida (default dump_dg_<HHMMSS>.txt en la carpeta actual).

3. Mandame el archivo .txt generado.

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
import unicodedata
from contextlib import redirect_stdout
from pathlib import Path


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode()
    return s.strip().lower()


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


def _ventanas_proceso(pid: int):
    from pywinauto import Application

    app = Application(backend="uia").connect(process=pid, timeout=5)
    return app, app.windows()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--titulo", default=None, help="Substring del título de la ventana a volcar.")
    p.add_argument("--pid", type=int, default=None, help="PID de DG.WinDG.exe (si hay varios).")
    p.add_argument("--depth", type=int, default=10, help="Profundidad del árbol (default 10).")
    p.add_argument("--salida", type=Path, default=None, help="Archivo .txt de salida.")
    args = p.parse_args()

    if sys.platform != "win32":
        sys.stderr.write("Solo corre en Windows.\n")
        return 2
    try:
        import pywinauto  # noqa: F401
    except ImportError:
        sys.stderr.write("ERROR: falta pywinauto.\n    py -m pip install pywinauto\n")
        return 2

    pids = [args.pid] if args.pid else _pids_dg()
    if not pids:
        sys.stderr.write("No encontré DG.WinDG.exe corriendo. Abrí DG primero.\n")
        return 1

    salida = args.salida or Path(f"dump_dg_{time.strftime('%H%M%S')}.txt")
    buf = io.StringIO()

    with redirect_stdout(buf):
        for pid in pids:
            print(f"==================== PID {pid} ====================")
            try:
                app, ventanas = _ventanas_proceso(pid)
            except Exception as e:
                print(f"  no pude conectar al PID {pid}: {e}")
                continue

            # 1) Listar todas las ventanas top-level del proceso.
            print("--- Ventanas top-level ---")
            objetivo = None
            for w in ventanas:
                try:
                    t = w.window_text() or ""
                    cls = w.class_name()
                    print(f"  title={t!r}  class={cls!r}")
                    if args.titulo and args.titulo.lower() in _norm(t):
                        objetivo = w
                except Exception:
                    continue

            # 2) Elegir la ventana a volcar.
            if objetivo is None:
                if args.titulo:
                    print(f"\n[!] No hallé una ventana cuyo título contenga {args.titulo!r}.")
                # Fallback: la que esté activa/en primer plano.
                try:
                    objetivo = app.top_window()
                    print(f"\n[i] Vuelco la ventana activa: {objetivo.window_text()!r}")
                except Exception:
                    objetivo = ventanas[0] if ventanas else None

            if objetivo is None:
                print("  no hay ventana para volcar.")
                continue

            # 3) Volcar el árbol de controles.
            print(
                f"\n--- Árbol de controles (depth={args.depth}) de {objetivo.window_text()!r} ---"
            )
            try:
                objetivo.print_control_identifiers(depth=args.depth)
            except Exception as e:
                print(f"  print_control_identifiers falló: {e}")

    contenido = buf.getvalue()
    salida.write_text(contenido, encoding="utf-8")
    # Eco a consola: resumen corto + dónde quedó.
    n_lineas = contenido.count("\n")
    print(f"Volcado escrito en: {salida.resolve()}  ({n_lineas} líneas)")
    print("Mandame ese archivo .txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
