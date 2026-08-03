@echo off
REM ====================================================================
REM  BUSCAR_FACTURA.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Busca en la carpeta que le digas (y sus subcarpetas) TODOS los
REM  archivos cuyo nombre traiga las facturas de facturas.txt y los
REM  copia organizados en SOPORTES_ENCONTRADOS\<factura>\. Los
REM  originales no se tocan. Deja un RESUMEN_BUSQUEDA.txt al final.
REM
REM  Se instala solo Python si falta. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title BUSCAR FACTURA - recolector de soportes - Motor Glosas HUS

echo.
echo ============================================================
echo   BUSCAR FACTURA - recolector de soportes
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 2) Este bot no necesita componentes adicionales ----------------

:motor
REM --- 3) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0buscar_facturas.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\buscar_facturas.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\buscar_facturas_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Requiere facturas.txt y pide donde buscar -------------------
if not exist "%~dp0facturas.txt" (
  echo [ERROR] Falta facturas.txt junto a este .cmd - una factura por linea
  echo         (sirve HUS0000533470, HUS533470 o 533470).
  echo.
  pause
  exit /b 2
)
set "DEFCARP=%~dp0"
if "%DEFCARP:~-1%"=="\" set "DEFCARP=%DEFCARP:~0,-1%"
set "CARPETA=%DEFCARP%"
echo   Carpeta donde BUSCAR los soportes (Enter para usar la de este .cmd):
setlocal EnableDelayedExpansion
echo   [!CARPETA!]
endlocal
set /p "CARPETA=  Ruta: "
set "CARPETA=%CARPETA:"=%"
if not defined CARPETA set "CARPETA=%DEFCARP%"
:quitarbs
if "%CARPETA:~-1%"=="\" ( set "CARPETA=%CARPETA:~0,-1%" & goto quitarbs )
if not defined CARPETA set "CARPETA=%DEFCARP%"
if "%CARPETA:~-1%"==":" set "CARPETA=%CARPETA%/"
echo.

REM --- 5) Ejecutar -----------------------------------------------------
%PYEXE% "%MOTOR%" "%CARPETA%" --lista "%~dp0facturas.txt" --destino "%~dp0SOPORTES_ENCONTRADOS"

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Revisa los mensajes y el archivo de salida de arriba. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
echo.
pause
exit /b %RC%

REM ==== Instalacion automatica de Python ==============================
:instalarpython
echo [i] No se encontro Python. Instalandolo automaticamente (sin admin),
echo     puede tardar unos minutos, NO cierres la ventana...
echo.
where winget >nul 2>&1 || goto py_descarga
winget install -e --id Python.Python.3.12 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements >nul 2>&1
call :redetectar
if defined PYEXE goto pyok
:py_descarga
set "PYINST=%TEMP%\python_instalador_hus.exe"
set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
del "%PYINST%" >nul 2>&1
echo [i] Descargando Python desde python.org - 25 MB aprox., espera...
curl.exe -L -s -o "%PYINST%" "%PYURL%" 2>nul
if not exist "%PYINST%" powershell -NoProfile -Command "Invoke-WebRequest -Uri $env:PYURL -OutFile $env:PYINST" >nul 2>&1
if not exist "%PYINST%" goto sinpython
"%PYINST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYINST%" >nul 2>&1
call :redetectar
if defined PYEXE goto pyok
goto sinpython
:pyok
echo [OK] Python quedo instalado. Continuando...
echo.
goto deps
:redetectar
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if defined PYEXE goto :eof
python -c "import sys" >nul 2>&1 && set "PYEXE=python"
if defined PYEXE goto :eof
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set PYEXE="%%D\python.exe"
if defined PYEXE %PYEXE% -c "import sys" >nul 2>&1 || set "PYEXE="
goto :eof

:sinpython
echo [ERROR] No se pudo instalar Python. Instalalo de https://www.python.org/downloads/
echo         (marca "Add python.exe to PATH") y vuelve a intentar.
echo.
pause
exit /b 1

:sinmotor
echo [ERROR] No se pudo preparar el motor. Copia tambien "buscar_facturas.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\buscar_facturas.py).
REM  cmd.exe nunca llega aqui (termina con exit /b mas arriba).
REM ====================================================================
#PYSTART#
"""buscar_facturas.py — Recolector de soportes: busca en las carpetas
compartidas TODOS los archivos de una lista de facturas y los copia
organizados en una carpeta por factura. Usado por BUSCAR_FACTURA.cmd.

Para armar el paquete de respuesta de una glosa hoy toca abrir carpeta por
carpeta buscando la factura. Este bot recibe la lista (facturas.txt, una por
línea: sirve HUS0000533470, HUS533470 o 533470) y recorre la carpeta que le
digas (y sus subcarpetas) copiando a DESTINO\\<factura>\\ cada archivo cuyo
nombre traiga ese número. Los originales NO se tocan ni se mueven.

Al final deja un RESUMEN_BUSQUEDA.txt con cuántos archivos halló por factura
y cuáles facturas quedaron SIN soportes.

USO:
    py tools\\buscar_facturas.py CARPETA_DONDE_BUSCAR --lista facturas.txt --destino SOPORTES
    py tools\\buscar_facturas.py \\\\servidor\\soportes --lista facturas.txt --destino D:\\PAQUETE

No requiere componentes adicionales (solo Python).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def normalizar_factura(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    return digitos.lstrip("0") or digitos


def cargar_lista(ruta: Path) -> list[str]:
    facturas = []
    vistas = set()
    for ln in ruta.read_text(encoding="utf-8-sig").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        norm = normalizar_factura(s)
        if norm and norm not in vistas:
            vistas.add(norm)
            facturas.append(s)
    return facturas


def compilar_patrones(facturas: list[str]) -> dict[str, re.Pattern]:
    """{factura original: patrón} — el número no puede ir pegado a más dígitos."""
    patrones = {}
    for f in facturas:
        norm = normalizar_factura(f)
        if norm:
            patrones[f] = re.compile(rf"(?<!\d)0*{re.escape(norm)}(?!\d)")
    return patrones


def copiar_sin_pisar(origen: Path, carpeta: Path) -> str:
    """Copia conservando fecha; si ya existe uno distinto, numera la copia."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / origen.name
    n = 1
    while destino.exists():
        if destino.stat().st_size == origen.stat().st_size:
            return "ya estaba"
        n += 1
        destino = carpeta / f"{origen.stem}_{n}{origen.suffix}"
    shutil.copy2(str(origen), str(destino))
    return "copiado"


def procesar(raiz: Path, lista: Path, destino: Path) -> int:
    facturas = cargar_lista(lista)
    patrones = compilar_patrones(facturas)

    print("=" * 66)
    print("  BUSCAR FACTURA — recolector de soportes por lista")
    print("=" * 66)
    print(f"  Buscando en: {raiz}")
    print(f"  Facturas en la lista: {len(facturas)}   Destino: {destino}")
    print("-" * 66)

    conteo = dict.fromkeys(facturas, 0)
    revisados = errores = 0
    destino_res = destino.resolve()
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        try:
            if destino_res in p.resolve().parents:
                continue  # no re-copiar lo ya recolectado
        except OSError:
            continue
        revisados += 1
        for f, patron in patrones.items():
            if patron.search(p.name):
                try:
                    copiar_sin_pisar(p, destino / f)
                    conteo[f] += 1
                except OSError as exc:
                    errores += 1
                    print(f"  ✗ {p.name}: no se pudo copiar ({type(exc).__name__})")
                break  # un archivo se guarda con la primera factura que coincida

    con_algo = {f: n for f, n in conteo.items() if n}
    sin_nada = [f for f, n in conteo.items() if not n]
    for f in facturas:
        marca = "✓" if conteo[f] else "·"
        print(f"  {marca} {f:18s} {conteo[f]} archivo(s)")

    resumen = destino / "RESUMEN_BUSQUEDA.txt"
    destino.mkdir(parents=True, exist_ok=True)
    lineas = [
        "RESUMEN DE BUSQUEDA DE SOPORTES",
        f"Carpeta revisada: {raiz}",
        f"Archivos revisados: {revisados}",
        "",
        "FACTURAS CON SOPORTES:",
        *(f"  {f}: {n} archivo(s)" for f, n in con_algo.items()),
        "",
        "FACTURAS SIN NINGUN ARCHIVO (buscar manualmente):",
        *(f"  {f}" for f in sin_nada),
    ]
    resumen.write_text("\r\n".join(lineas), encoding="utf-8")

    print("-" * 66)
    print(f"  Archivos revisados: {revisados}")
    print(
        f"  Facturas con soportes: {len(con_algo)}   Sin soportes: {len(sin_nada)}   Errores: {errores}"
    )
    print(f"  Resumen: {resumen}")
    print("=" * 66)
    return 0 if errores == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Busca y copia los soportes de una lista de facturas."
    )
    parser.add_argument(
        "carpeta", nargs="?", default=".", help="Carpeta donde buscar (incluye subcarpetas)."
    )
    parser.add_argument(
        "--lista", type=Path, required=True, help="Archivo .txt con las facturas (una por línea)."
    )
    parser.add_argument(
        "--destino", type=Path, required=True, help="Carpeta donde dejar lo encontrado."
    )
    args = parser.parse_args(argv)

    raiz = Path(args.carpeta).expanduser()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    if not args.lista.is_file():
        sys.stderr.write(f"ERROR: no existe la lista: {args.lista}\n")
        return 2
    return procesar(raiz.resolve(), args.lista, args.destino)


if __name__ == "__main__":
    raise SystemExit(main())
