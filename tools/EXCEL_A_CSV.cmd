@echo off
REM ====================================================================
REM  EXCEL_A_CSV.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  El reverso de TXT_A_EXCEL: por cada Excel deja un NOMBRE.csv
REM  delimitado por comas (ANSI), listo para las plataformas. El Excel
REM  original nunca se toca y jamas pisa un .csv que ya exista.
REM
REM  Se instala solo Python si falta. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title EXCEL A CSV - delimitado por comas - Motor Glosas HUS

echo.
echo ============================================================
echo   EXCEL A CSV - delimitado por comas
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 2) Asegurar openpyxl (para el Excel), verificando que quedo ----
%PYEXE% -c "import openpyxl" >nul 2>&1 && goto motor
echo [i] Instalando el componente de Excel (openpyxl) por unica vez, espera...
%PYEXE% -m pip install --quiet --user openpyxl >nul 2>&1
%PYEXE% -c "import openpyxl" >nul 2>&1 && goto motor
echo [ATENCION] No quedo instalado openpyxl (revisa el internet). El Excel
echo            de salida puede fallar en esta corrida.
echo.

:motor
REM --- 3) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0excel_a_csv.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\excel_a_csv.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\excel_a_csv_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Pedir carpeta (por defecto, donde esta este .cmd) -----------
set "DEFCARP=%~dp0"
if "%DEFCARP:~-1%"=="\" set "DEFCARP=%DEFCARP:~0,-1%"
set "CARPETA=%DEFCARP%"
echo   Carpeta a procesar (Enter para usar la carpeta de este .cmd):
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
set "RECUR=S"
set /p "RECUR=  Incluir subcarpetas? (S/N, Enter = S): "
set "RECUR=%RECUR:"=%"
if not defined RECUR set "RECUR=S"
echo.

REM --- 5) Ejecutar -----------------------------------------------------
if /i "%RECUR:~0,1%"=="N" (
  %PYEXE% "%MOTOR%" "%CARPETA%" --sin-recursion
) else (
  %PYEXE% "%MOTOR%" "%CARPETA%"
)

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
echo [ERROR] No se pudo preparar el motor. Copia tambien "excel_a_csv.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\excel_a_csv.py).
REM  cmd.exe nunca llega aqui (termina con exit /b mas arriba).
REM ====================================================================
#PYSTART#
"""excel_a_csv.py — El reverso de TXT_A_EXCEL: por cada Excel deja un
NOMBRE.csv delimitado por comas, listo para las plataformas que exigen ese
formato. Usado por EXCEL_A_CSV.cmd.

Sirve para una carpeta o masivo con subcarpetas. El Excel original nunca se
toca. Reglas:

    - Convierte la hoja ACTIVA; con --todas convierte cada hoja a
      NOMBRE_HOJA.csv. Si el libro tiene fórmulas, se usa el último valor
      calculado por Excel.
    - Fechas salen como dd/mm/aaaa (y hora si la trae); los números sin
      ".0" sobrando; comillas solo si el dato trae coma o salto de línea.
    - En ANSI (cp1252), que es lo que esperan las plataformas; si un dato
      no cabe en ANSI, ese archivo sale en UTF-8 y se avisa.
    - Si el NOMBRE.csv ya existe se OMITE (no pisa nada); con --forzar se
      regenera.

USO:
    py tools\\excel_a_csv.py CARPETA
    py tools\\excel_a_csv.py CARPETA --sin-recursion --todas --forzar

Requiere openpyxl. El repo ya lo fija.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from datetime import datetime, time
from pathlib import Path

_RE_NOMBRE_HOJA = re.compile(r"[^\w\-]+")


def celda_a_texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        if v.hour or v.minute or v.second:
            return v.strftime("%d/%m/%Y %H:%M")
        return v.strftime("%d/%m/%Y")
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, bool):
        return "SI" if v else "NO"
    return str(v)


def _campo_csv(campo: str) -> str:
    if "," in campo or "\n" in campo or "\r" in campo:
        return '"' + campo.replace('"', '""') + '"'
    return campo


def hoja_a_csv(ws, destino: Path) -> str:
    """Escribe una hoja como csv por comas. Devuelve nota si salió en UTF-8."""
    lineas = []
    for fila in ws.iter_rows(values_only=True):
        campos = [_campo_csv(celda_a_texto(v)) for v in fila]
        lineas.append(",".join(campos))
    # recorta filas vacías del final
    while lineas and not lineas[-1].strip(","):
        lineas.pop()
    contenido = "\r\n".join(lineas) + "\r\n"
    nota = ""
    try:
        crudo = contenido.encode("cp1252")
    except UnicodeEncodeError:
        crudo = contenido.encode("utf-8-sig")
        nota = "en UTF-8 (trae caracteres fuera de ANSI)"
    tmp = destino.with_name(destino.name + ".tmp")
    try:
        tmp.write_bytes(crudo)
        tmp.replace(destino)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return nota


def convertir_uno(ruta: Path, todas: bool = False, forzar: bool = False) -> dict:
    res = {"archivo": ruta.name, "estado": "ok", "motivo": "", "csvs": 0}
    try:
        from openpyxl import load_workbook

        wb = load_workbook(str(ruta), read_only=True, data_only=True)
    except Exception as exc:
        res.update(estado="error", motivo=f"Excel ilegible ({type(exc).__name__})")
        return res
    try:
        hojas = wb.worksheets if todas else [wb.active]
        notas = []
        for ws in hojas:
            if todas and len(wb.worksheets) > 1:
                sufijo = _RE_NOMBRE_HOJA.sub("_", ws.title).strip("_") or "Hoja"
                destino = ruta.with_name(f"{ruta.stem}_{sufijo}.csv")
            else:
                destino = ruta.with_suffix(".csv")
            if destino.exists() and not forzar:
                notas.append(f"{destino.name} ya existe (usa --forzar para regenerar)")
                continue
            nota = hoja_a_csv(ws, destino)
            res["csvs"] += 1
            if nota:
                notas.append(nota)
        if not todas and len(wb.worksheets) > 1:
            notas.append(f"el libro tiene {len(wb.worksheets)} hojas; se convirtio la activa")
        res["motivo"] = " · ".join(notas)
        if res["csvs"] == 0 and notas:
            res["estado"] = "omitido"
    except Exception as exc:
        res.update(estado="error", motivo=f"no se pudo escribir ({type(exc).__name__})")
    finally:
        wb.close()
    return res


def procesar(
    raiz: Path, sin_recursion: bool = False, todas: bool = False, forzar: bool = False
) -> int:
    buscador = raiz.glob if sin_recursion else raiz.rglob
    archivos = []
    for patron in ("*.xlsx", "*.xlsm"):
        archivos += [a for a in buscador(patron) if a.is_file() and not a.name.startswith("~$")]
    archivos = sorted(set(archivos), key=lambda p: str(p).lower())

    print("=" * 66)
    print("  EXCEL A CSV — deja cada Excel delimitado por comas")
    print("=" * 66)
    print(
        f"  Carpeta: {raiz}" + ("  (sin subcarpetas)" if sin_recursion else "  (con subcarpetas)")
    )
    print(f"  Excel encontrados: {len(archivos)}")
    print("-" * 66)
    if not archivos:
        print("  No hay Excel para convertir aqui.")
        print("=" * 66)
        return 0

    ok = omitidos = errores = 0
    for a in archivos:
        r = convertir_uno(a, todas=todas, forzar=forzar)
        rel = a.relative_to(raiz) if a.is_relative_to(raiz) else a
        extra = f"  [{r['motivo']}]" if r["motivo"] else ""
        if r["estado"] == "ok":
            ok += 1
            print(f"  ✓ {rel}  ->  {r['csvs']} csv{extra}")
        elif r["estado"] == "omitido":
            omitidos += 1
            print(f"  · {rel}  omitido{extra}")
        else:
            errores += 1
            print(f"  ✗ {rel}  ERROR: {r['motivo']}")

    print("-" * 66)
    print(f"  Convertidos: {ok}   Omitidos: {omitidos}   Errores: {errores}")
    print("=" * 66)
    return 0 if errores == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte cada Excel a .csv delimitado por comas."
    )
    parser.add_argument("carpeta", nargs="?", default=".", help="Carpeta con los Excel.")
    parser.add_argument("--sin-recursion", action="store_true", help="Solo la carpeta raíz.")
    parser.add_argument(
        "--todas", action="store_true", help="Convierte todas las hojas, no solo la activa."
    )
    parser.add_argument("--forzar", action="store_true", help="Regenera aunque el .csv exista.")
    args = parser.parse_args(argv)

    raiz = Path(args.carpeta).expanduser()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    return procesar(raiz.resolve(), args.sin_recursion, args.todas, args.forzar)


if __name__ == "__main__":
    raise SystemExit(main())
