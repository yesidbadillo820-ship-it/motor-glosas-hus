"""coosalud_todo.py — TODO EN UNO interactivo: organiza el ZIP y genera OBJECIONES.

Pensado para el equipo de cartera: NO recibe argumentos. Se ejecuta y pregunta
todo en español, aceptando rutas arrastradas a la ventana (quita las comillas
solo). Encuentra la base DGH automáticamente si está en la carpeta de los bots,
en el Escritorio o en Descargas.

    py coosalud_todo.py

Hace los dos pasos:
  1) organizar_cargue_masivo_coosalud  (ZIP -> DETALLES/FACTURAS/GLOSAS en lotes de 300)
  2) consolidar_coosalud               (consolidados + OBJECIONES.xlsx para DGH)

Al final abre la carpeta CONSOLIDADOS y deja un registro en _log_coosalud.txt.
La ventana NUNCA se cierra sola: siempre espera un Enter.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LOG = AQUI / "_log_coosalud.txt"

DESTINOS = [Path(r"D:\USUARIO CARTERA\Desktop"), Path.home() / "Desktop"]
RE_BASE_DGH = re.compile(r"SERVICIOS.*FACTURADOS.*\.(xlsx|xlsm|csv|txt)$", re.IGNORECASE)


def preparar_consola() -> None:
    """Que los acentos no revienten la consola de Windows (cmd con cp850)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def preparar_logging() -> None:
    """Todo lo que impriman los bots va a pantalla Y a _log_coosalud.txt."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(logging.Formatter("%(message)s"))
    archivo = logging.FileHandler(LOG, mode="w", encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(consola)
    root.addHandler(archivo)


def limpiar_ruta(texto: str) -> str:
    """Quita comillas y espacios de una ruta pegada o arrastrada a la ventana."""
    return texto.strip().strip('"').strip("'").strip()


def pedir(mensaje: str) -> str:
    try:
        return input(mensaje)
    except EOFError:
        return ""


def asegurar_openpyxl() -> None:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("\n  Instalando openpyxl (solo la primera vez)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
        import importlib

        importlib.invalidate_caches()


def buscar_zips() -> list[Path]:
    """ZIPs candidatos: junto a los bots, Escritorio y Descargas (recientes primero)."""
    lugares = [AQUI, AQUI.parent, Path.home() / "Downloads", *DESTINOS]
    encontrados: dict[Path, float] = {}
    for lugar in lugares:
        if lugar.is_dir():
            for z in lugar.glob("*.zip"):
                encontrados[z] = z.stat().st_mtime
    return sorted(encontrados, key=encontrados.get, reverse=True)[:6]


def buscar_base_dgh() -> Path | None:
    """Busca 'SERVICIOS FACTURADOS...' cerca (bots, Escritorio, Descargas)."""
    lugares = [AQUI, AQUI.parent, Path.home() / "Downloads", *DESTINOS]
    candidatos: list[Path] = []
    for lugar in lugares:
        if lugar.is_dir():
            candidatos += [f for f in lugar.iterdir() if f.is_file() and RE_BASE_DGH.search(f.name)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda f: f.stat().st_mtime)


def elegir_zip() -> Path | None:
    print("\n--- PASO A: el ZIP de COOSALUD ---")
    zips = buscar_zips()
    if zips:
        print("  ZIPs encontrados:")
        for i, z in enumerate(zips, 1):
            print(f"    {i}) {z}")
        r = pedir("  Escribe el numero, o arrastra aqui otro ZIP y Enter: ")
    else:
        r = pedir("  Arrastra aqui el ZIP y presiona Enter: ")
    r = limpiar_ruta(r)
    if r.isdigit() and zips and 1 <= int(r) <= len(zips):
        return zips[int(r) - 1]
    if r:
        p = Path(r)
        if p.is_file():
            return p
        print(f"  ERROR: no existe el archivo: {p}")
        return None
    return zips[0] if zips else None


def elegir_fecha() -> str | None:
    print("\n--- PASO B: la fecha del dia que se revisa ---")
    hoy = datetime.now().strftime("%d/%m/%Y")
    while True:
        r = pedir(f"  Fecha DD/MM/AAAA (Enter = {hoy}): ").strip()
        if not r:
            return hoy
        try:
            datetime.strptime(r, "%d/%m/%Y")
            return r
        except ValueError:
            print("  Fecha invalida, ejemplo valido: 08/07/2026. Intenta de nuevo.")


def elegir_base() -> Path | None:
    print("\n--- PASO C: la base DGH (SERVICIOS FACTURADOS COOSALUD) ---")
    print('  Es el Excel que se descarga de DGH, llamado tipo "SERVICIOS')
    print('  FACTURADOS COOSALUD DGH.xlsx" (pesa bastante, 50MB+).')
    auto = buscar_base_dgh()
    if auto:
        r = pedir(
            f'  Encontre: "{auto.name}"\n    en {auto.parent}\n  Enter = usarla · n = sin base · o arrastra otra: '
        )
    else:
        r = pedir(
            "  No la encontre cerca. Arrastra aqui el Excel y Enter (o Enter para seguir SIN base): "
        )
    r = limpiar_ruta(r)
    if r.lower() in ("n", "no"):
        return None
    if r:
        p = Path(r)
        if not p.is_file():
            print(f"  AVISO: no existe '{p}', se sigue SIN base DGH.")
            return None
        if not RE_BASE_DGH.search(p.name):
            print(f'\n  OJO: "{p.name}" NO parece la base DGH')
            print('  (la base se llama tipo "SERVICIOS FACTURADOS COOSALUD DGH.xlsx").')
            conf = pedir(
                "  ¿Usar ese archivo de todas formas? (s = si / Enter = NO, seguir sin base): "
            )
            if conf.strip().lower() not in ("s", "si", "sí"):
                return None
        return p
    return auto


def main() -> int:
    preparar_consola()
    preparar_logging()

    print("=" * 72)
    print("   BOT COOSALUD - TODO EN UNO (organizar + consolidar + OBJECIONES)")
    print("=" * 72)

    asegurar_openpyxl()

    sys.path.insert(0, str(AQUI))
    try:
        import consolidar_coosalud as con
        import organizar_cargue_masivo_coosalud as org
    except ImportError as exc:
        print(f"\n  ERROR: falta un archivo junto a este script: {exc}")
        print("  Deben estar los 3 juntos: coosalud_todo.py,")
        print("  organizar_cargue_masivo_coosalud.py y consolidar_coosalud.py")
        return 1

    zip_path = elegir_zip()
    if not zip_path:
        print("\n  Sin ZIP no puedo continuar.")
        return 1
    fecha = elegir_fecha()
    base = elegir_base()

    destino = next((d for d in DESTINOS if d.is_dir()), DESTINOS[-1])
    carpeta = destino / "CARGUE MASIVO COOSALUD"

    print("\n" + "=" * 72)
    print(f"   ZIP    : {zip_path}")
    print(f"   Fecha  : {fecha}")
    print(f"   Base   : {base if base else '(sin base DGH: SLNSERPRO saldra del detalle)'}")
    print(f"   Salida : {carpeta}\\CONSOLIDADOS")
    print("=" * 72)

    print("\n>>> PASO 1/2: organizando el ZIP...\n")
    rc = org.main(["--zip", str(zip_path), "--destino", str(destino)])
    if rc != 0:
        print("\n  ERROR en el paso 1. Revisa arriba (y en _log_coosalud.txt).")
        return rc

    print("\n>>> PASO 2/2: consolidando y generando OBJECIONES...\n")
    argumentos = ["--carpeta", str(carpeta), "--fecha", fecha]
    if base:
        argumentos += ["--servicios", str(base)]
    # Si junto a los bots hay un "FACTURAS YA OBJETADAS.txt" (una factura por
    # línea), esas se dejan fuera del OBJECIONES: DGH rechaza el cargue
    # completo si va una factura que ya está objetada.
    ya_objetadas = AQUI / "FACTURAS YA OBJETADAS.txt"
    if ya_objetadas.is_file():
        print(f'  (Usando "{ya_objetadas.name}": esas facturas no van al OBJECIONES)')
        argumentos += ["--omitir-facturas", str(ya_objetadas)]
    rc = con.main(argumentos)
    if rc != 0:
        print("\n  ERROR en el paso 2. Revisa arriba (y en _log_coosalud.txt).")
        return rc

    consolidados = carpeta / "CONSOLIDADOS"
    print("\n" + "=" * 72)
    print("   LISTO. Resultados en:")
    print(f"   {consolidados}")
    print("   Hay una carpeta por LOTE (max 300 facturas), cada una con su")
    print("   OBJECIONES para subir a DGH por separado. Lo que DGH no acepta")
    print('   queda aparte en "REVISAR (no van en el cargue)".')
    print("=" * 72)
    try:
        os.startfile(consolidados)  # abre la carpeta en el Explorador (solo Windows)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    codigo = 1
    try:
        codigo = main()
    except KeyboardInterrupt:
        print("\n  Cancelado por el usuario.")
    except Exception:
        print("\n  ERROR INESPERADO:\n")
        traceback.print_exc()
        try:
            LOG.open("a", encoding="utf-8").write("\n" + traceback.format_exc())
        except Exception:
            pass
    print(f"\n  (Registro guardado en: {LOG})")
    pedir("  Presiona Enter para salir...")
    raise SystemExit(codigo)
