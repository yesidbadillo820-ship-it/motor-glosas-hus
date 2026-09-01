"""Borra una glosa del historial para obligar al motor a generar una nueva.

Para qué sirve
──────────────
Cuando la pantalla del Motor de Glosas sigue mostrando el MISMO dictamen
corrida tras corrida —el consecutivo «GL-147» no sube—, el motor está
reusando el registro que ya tenía guardado en vez de pedirle uno nuevo a la
IA. Borrar ese registro lo obliga a empezar de cero.

Cómo se usa
───────────
    cd C:\\motor-glosas\\repo
    .\\venv\\Scripts\\python.exe tools\\borrar_glosa_hus.py HUS0000601892

Primero MUESTRA lo que va a borrar y pide confirmación escrita. Nada se toca
hasta que usted escriba BORRAR. Para saltarse la pregunta (por ejemplo en un
bot): agregue --si al final.

Lo que hace antes de borrar
───────────────────────────
1. Busca sola la base de datos. NO asume el nombre del archivo: recorre el
   disco desde esta carpeta y reconoce la base por sus columnas, no por cómo
   se llame. Si mañana el archivo cambia de nombre, sigue funcionando.
2. Saca una copia de seguridad con fecha y hora al lado del original. Un
   DELETE en SQLite no se deshace; la copia es lo único que lo salva.
3. Le muestra id, fecha, entidad, código y valor de cada fila que va a borrar.

Después borra en el orden correcto: primero las versiones del dictamen y
después la glosa. Al revés quedarían versiones huérfanas apuntando a una
glosa que ya no existe.
"""

from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# La tabla de glosas se reconoce por estas columnas, no por su nombre. Hoy se
# llama «historial»; si mañana se llamara distinto, esto la sigue encontrando.
FIRMA_GLOSAS = {"factura", "valor_objetado", "creado_en", "codigo_glosa"}
# La de versiones del dictamen: apunta a la glosa por glosa_id.
FIRMA_VERSIONES = {"glosa_id", "dictamen_html"}


def bases_de_datos() -> list[str]:
    """Los .db que haya, sin repetir, mirando las rutas de siempre."""
    patrones = ("*.db", "data/*.db", "db/*.db", "instance/*.db", "**/*.db")
    encontrados: list[str] = []
    vistos: set[str] = set()
    for patron in patrones:
        for ruta in sorted(glob.glob(patron, recursive=True)):
            real = os.path.realpath(ruta)
            if real in vistos or not os.path.isfile(ruta):
                continue
            vistos.add(real)
            encontrados.append(ruta)
    return encontrados


def tabla_con_firma(con: sqlite3.Connection, firma: set[str]) -> str | None:
    """El nombre real de la tabla que tenga esas columnas."""
    for (nombre,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        columnas = {fila[1] for fila in con.execute(f'PRAGMA table_info("{nombre}")')}
        if firma.issubset(columnas):
            return nombre
    return None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sin_preguntar = "--si" in sys.argv
    factura = args[0] if args else "HUS0000601892"

    print(f"Factura a borrar: {factura}")
    print(f"Carpeta actual  : {os.getcwd()}\n")

    objetivos: list[tuple[str, str, str | None, list[tuple]]] = []

    for ruta in bases_de_datos():
        try:
            con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        except sqlite3.Error as e:
            print(f"[!] {ruta}: no se pudo abrir ({e})")
            continue
        try:
            t_glosas = tabla_con_firma(con, FIRMA_GLOSAS)
            if not t_glosas:
                continue
            filas = list(
                con.execute(
                    f"SELECT id, creado_en, eps, codigo_glosa, valor_objetado "
                    f'FROM "{t_glosas}" WHERE factura = ?',
                    (factura,),
                )
            )
            if not filas:
                print(f"    {ruta}: tabla «{t_glosas}», sin filas de esa factura.")
                continue
            t_versiones = tabla_con_firma(con, FIRMA_VERSIONES)
            objetivos.append((ruta, t_glosas, t_versiones, filas))
        finally:
            con.close()

    if not objetivos:
        print("\nNo se encontró ninguna glosa con esa factura. No hay nada que borrar.")
        print("Si esperaba encontrarla, corra primero verificar_glosas.py.")
        return 1

    print("\n" + "=" * 66)
    print("ESTO ES LO QUE SE VA A BORRAR")
    print("=" * 66)
    total_glosas = 0
    for ruta, t_glosas, t_versiones, filas in objetivos:
        print(f"\n  Base: {ruta}")
        print(f"  Tabla de glosas   : {t_glosas}")
        print(f"  Tabla de versiones: {t_versiones or '(no existe en esta base)'}")
        for gid, creado, eps, cod, valor in filas:
            print(f"    id={gid}  {creado}  {eps}  {cod}  $ {valor or 0:,.0f}".replace(",", "."))
            total_glosas += 1
    print(f"\n  TOTAL: {total_glosas} glosa(s)")
    print("=" * 66)

    if not sin_preguntar:
        print("\nEsto NO se puede deshacer (queda la copia de seguridad).")
        if input("Escriba BORRAR para continuar: ").strip() != "BORRAR":
            print("Cancelado. No se tocó nada.")
            return 1

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    for ruta, t_glosas, t_versiones, _filas in objetivos:
        copia = f"{ruta}.backup_{sello}"
        shutil.copy2(ruta, copia)
        print(f"\n  Copia de seguridad: {copia}")

        con = sqlite3.connect(ruta)
        try:
            con.execute("PRAGMA foreign_keys = ON")
            n_ver = 0
            if t_versiones:
                # Primero las versiones: al revés quedarían huérfanas.
                n_ver = con.execute(
                    f'DELETE FROM "{t_versiones}" WHERE glosa_id IN '
                    f'(SELECT id FROM "{t_glosas}" WHERE factura = ?)',
                    (factura,),
                ).rowcount
            n_glo = con.execute(f'DELETE FROM "{t_glosas}" WHERE factura = ?', (factura,)).rowcount
            con.commit()
            print(f"  Borradas en {t_versiones or 'versiones'}: {n_ver} fila(s)")
            print(f"  Borradas en {t_glosas}: {n_glo} fila(s)")
        except sqlite3.Error as e:
            con.rollback()
            print(f"  [!] ERROR, no se borró nada en esta base: {e}")
            print(f"      La base quedó como estaba. Copia intacta en {copia}")
            return 2
        finally:
            con.close()

    print("\nListo. Reinicie el motor y vuelva a analizar la glosa:")
    print(
        "  Get-Process python | Where-Object {$_.CommandLine -like '*uvicorn*'} | Stop-Process -Force"
    )
    print(
        "  Start-Process -FilePath .\\venv\\Scripts\\python.exe -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000' -WindowStyle Hidden"
    )
    print("\nEl consecutivo tiene que subir: si sigue en el mismo GL-, avise.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
