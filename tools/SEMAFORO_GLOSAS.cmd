@echo off
REM ====================================================================
REM  SEMAFORO_GLOSAS.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Calcula la fecha limite de respuesta de cada glosa contando DIAS
REM  HABILES (sin sabados, domingos ni festivos de Colombia) y pinta el
REM  semaforo: NEGRO vencida, ROJO 1-4 dias, AMARILLO 5-10, VERDE 11+.
REM  Deja SEMAFORO_GLOSAS.xlsx junto a este archivo.
REM
REM  Se instala solo Python si falta. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title SEMAFORO GLOSAS - plazos de respuesta - Motor Glosas HUS

echo.
echo ============================================================
echo   SEMAFORO GLOSAS - plazos de respuesta
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
set "MOTOR=%~dp0semaforo_vencimientos.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\semaforo_vencimientos.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\semaforo_vencimientos_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Excel con las glosas notificadas ----------------------------
set "GLOSAS="
for /f "delims=" %%F in ('dir /b /a-d "%~dp0*.xlsx" 2^>nul ^| findstr /v /i /b "CRUCE_ SEMAFORO_ VERIFICACION_ INFORME_ BORRADORES_"') do if not defined GLOSAS set "GLOSAS=%~dp0%%F"
echo   Excel con las glosas (factura + fecha de notificacion):
setlocal EnableDelayedExpansion
echo   [!GLOSAS!]
endlocal
set /p "GLOSAS=  Ruta: "
set "GLOSAS=%GLOSAS:"=%"
if not defined GLOSAS (
  echo [ERROR] No hay Excel de glosas: copialo junto a este .cmd o escribe su ruta.
  echo.
  pause
  exit /b 2
)
echo.
set "PLAZO=20"
set /p "PLAZO=  Plazo en dias habiles (Enter = 20): "
echo %PLAZO%|findstr /r "^[0-9][0-9]*$" >nul || set "PLAZO=20"
echo.

REM --- 5) Ejecutar -----------------------------------------------------
%PYEXE% "%MOTOR%" "%GLOSAS%" --plazo %PLAZO% --salida "%~dp0SEMAFORO_GLOSAS.xlsx"

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
echo [ERROR] No se pudo preparar el motor. Copia tambien "semaforo_vencimientos.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\semaforo_vencimientos.py).
REM  cmd.exe nunca llega aqui (termina con exit /b mas arriba).
REM ====================================================================
#PYSTART#
"""semaforo_vencimientos.py — Semáforo de plazos para responder glosas.
Usado por SEMAFORO_GLOSAS.cmd.

Lee un Excel con las glosas notificadas (detecta solo las columnas de factura
y fecha de notificación) y calcula, para cada una, la FECHA LÍMITE de
respuesta contando días HÁBILES (excluye sábados, domingos y festivos de
Colombia 2025-2028, la misma tabla del Motor de Glosas web) y cuántos días
hábiles quedan.

Semáforo (los mismos umbrales del Motor web):
    NEGRO    = vencida (0 o menos días)
    ROJO     = quedan 1 a 4 días hábiles
    AMARILLO = quedan 5 a 10 días hábiles
    VERDE    = quedan 11 o más

El plazo por defecto es 20 días hábiles (Art. 57 Ley 1438 de 2011 para la
respuesta del prestador); se cambia con --plazo.

USO:
    py tools\\semaforo_vencimientos.py GLOSAS.xlsx
    py tools\\semaforo_vencimientos.py GLOSAS.xlsx --plazo 20 --salida SEMAFORO.xlsx
    py tools\\semaforo_vencimientos.py GLOSAS.xlsx --hoy 2026-07-16   # para pruebas

Requiere openpyxl. El repo ya lo fija.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Festivos Colombia (la misma tabla FERIADOS_CO del Motor de Glosas web).
FERIADOS_CO = {
    # 2025
    "2025-01-01",
    "2025-01-06",
    "2025-03-24",
    "2025-04-17",
    "2025-04-18",
    "2025-05-01",
    "2025-06-02",
    "2025-06-23",
    "2025-06-30",
    "2025-07-20",
    "2025-08-07",
    "2025-08-18",
    "2025-10-13",
    "2025-11-03",
    "2025-11-17",
    "2025-12-08",
    "2025-12-25",
    # 2026
    "2026-01-01",
    "2026-01-12",
    "2026-03-23",
    "2026-04-02",
    "2026-04-03",
    "2026-05-01",
    "2026-05-18",
    "2026-06-08",
    "2026-06-15",
    "2026-06-29",
    "2026-07-20",
    "2026-08-07",
    "2026-08-17",
    "2026-10-12",
    "2026-11-02",
    "2026-11-16",
    "2026-12-08",
    "2026-12-25",
    # 2027
    "2027-01-01",
    "2027-01-11",
    "2027-03-22",
    "2027-04-01",
    "2027-04-02",
    "2027-05-01",
    "2027-05-17",
    "2027-06-07",
    "2027-06-14",
    "2027-06-28",
    "2027-07-20",
    "2027-08-07",
    "2027-08-16",
    "2027-10-11",
    "2027-11-01",
    "2027-11-15",
    "2027-12-08",
    "2027-12-25",
    # 2028 (estimados)
    "2028-01-01",
    "2028-01-10",
    "2028-03-20",
    "2028-04-13",
    "2028-04-14",
    "2028-05-01",
    "2028-05-15",
    "2028-06-05",
    "2028-06-12",
    "2028-06-26",
    "2028-07-20",
    "2028-08-07",
    "2028-08-14",
    "2028-10-09",
    "2028-10-30",
    "2028-11-06",
    "2028-11-13",
    "2028-12-08",
    "2028-12-25",
}

_COLS = {
    "factura": ("FACTURA", "FACT", "DOCUMENTO", "NRO", "NUMERO"),
    "fecha": ("FECHA",),
    "valor": ("VALOR", "VLR", "MONTO"),
    "eps": ("EPS", "ENTIDAD", "ASEGURADOR", "PAGADOR"),
}
# Entre varias columnas FECHA, preferimos la de notificación/radicación de la glosa.
_FECHA_PREFERIDA = ("NOTIF", "GLOSA", "OBJEC", "RADIC")


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in FERIADOS_CO


def sumar_habiles(desde: date, dias: int) -> date:
    """Fecha resultante de contar `dias` hábiles a partir de `desde`."""
    actual, faltan = desde, dias
    while faltan > 0:
        actual += timedelta(days=1)
        if es_habil(actual):
            faltan -= 1
    return actual


def habiles_entre(desde: date, hasta: date) -> int:
    """Días hábiles de desde (exclusivo) a hasta (inclusivo); negativo si ya pasó."""
    if desde == hasta:
        return 0
    signo = 1 if hasta > desde else -1
    a, b = (desde, hasta) if hasta > desde else (hasta, desde)
    dias = 0
    actual = a
    while actual < b:
        actual += timedelta(days=1)
        if es_habil(actual):
            dias += 1
    return signo * dias


def semaforo(dias_restantes: int) -> str:
    if dias_restantes <= 0:
        return "NEGRO (vencida)"
    if dias_restantes < 5:
        return "ROJO"
    if dias_restantes < 11:
        return "AMARILLO"
    return "VERDE"


def parsear_fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor or "").strip()
    if not s:
        return None
    s = s.split(" ")[0]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _detectar_columnas(ws) -> tuple[int, dict[str, int]] | None:
    for fila in range(1, 11):
        textos = {}
        for col in range(1, min(ws.max_column, 40) + 1):
            v = ws.cell(row=fila, column=col).value
            if v is not None:
                textos[col] = str(v).upper()
        if not textos:
            continue
        mapa = {}
        for campo, claves in _COLS.items():
            candidatas = [c for c, t in textos.items() if any(k in t for k in claves)]
            if not candidatas:
                continue
            if campo == "fecha" and len(candidatas) > 1:
                preferidas = [
                    c for c in candidatas if any(p in textos[c] for p in _FECHA_PREFERIDA)
                ]
                candidatas = preferidas or candidatas
            mapa[campo] = candidatas[0]
        if "factura" in mapa and "fecha" in mapa:
            return fila, mapa
    return None


def cargar_glosas(excel: Path) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(str(excel), read_only=True, data_only=True)
    ws = wb.active
    deteccion = _detectar_columnas(ws)
    if not deteccion:
        wb.close()
        raise ValueError("no encontre columnas de FACTURA y FECHA en el Excel")
    fila_enc, mapa = deteccion
    filas = []
    vacias = 0
    for fila in ws.iter_rows(min_row=fila_enc + 1, values_only=False):
        celdas = {c.column: c.value for c in fila}
        factura = celdas.get(mapa["factura"])
        if factura is None or not str(factura).strip():
            vacias += 1
            if vacias > 20:
                break
            continue
        vacias = 0
        filas.append(
            {
                "factura": str(factura).strip(),
                "fecha": parsear_fecha(celdas.get(mapa["fecha"])),
                "valor": celdas.get(mapa.get("valor")) or "",
                "eps": str(celdas.get(mapa.get("eps")) or "").strip(),
            }
        )
    wb.close()
    return filas


def escribir_excel(filas: list[dict], salida: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Semaforo"
    ws.append(
        [
            "Semáforo",
            "Días hábiles restantes",
            "Fecha límite",
            "Factura",
            "Fecha notificación",
            "Valor",
            "EPS",
            "Nota",
        ]
    )
    azul = PatternFill("solid", fgColor="1F4E79")
    colores = {
        "NEGRO (vencida)": PatternFill("solid", fgColor="D9D9D9"),
        "ROJO": PatternFill("solid", fgColor="F8CBAD"),
        "AMARILLO": PatternFill("solid", fgColor="FFF2CC"),
        "VERDE": PatternFill("solid", fgColor="E2EFDA"),
    }
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = azul
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for f in filas:
        ws.append(
            [
                f.get("semaforo", ""),
                f.get("restantes", ""),
                f["limite"].strftime("%d/%m/%Y") if f.get("limite") else "",
                f["factura"],
                f["fecha"].strftime("%d/%m/%Y") if f.get("fecha") else "",
                f.get("valor", ""),
                f.get("eps", ""),
                f.get("nota", ""),
            ]
        )
        pintura = colores.get(f.get("semaforo", ""))
        if pintura:
            for c in ws[ws.max_row]:
                c.fill = pintura
    for i, w in enumerate([16, 12, 14, 18, 14, 14, 28, 34], start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    wb.save(str(salida))


def procesar(excel: Path, plazo: int, hoy: date, salida: Path) -> int:
    filas = cargar_glosas(excel)
    print("=" * 66)
    print("  SEMAFORO DE GLOSAS — plazo de respuesta en días hábiles")
    print("=" * 66)
    print(f"  Glosas: {len(filas)}   Plazo: {plazo} días hábiles   Hoy: {hoy.strftime('%d/%m/%Y')}")
    print("-" * 66)

    conteo = {}
    for f in filas:
        if not f["fecha"]:
            f["nota"] = "fecha ilegible: revisar manualmente"
            f["semaforo"] = "SIN FECHA"
        else:
            f["limite"] = sumar_habiles(f["fecha"], plazo)
            f["restantes"] = habiles_entre(hoy, f["limite"])
            f["semaforo"] = semaforo(f["restantes"])
            if f["fecha"].strftime("%Y-%m-%d") < "2025-01-01" or f["fecha"].year > 2028:
                f["nota"] = "fecha fuera de la tabla de festivos (2025-2028)"
        conteo[f["semaforo"]] = conteo.get(f["semaforo"], 0) + 1

    filas.sort(key=lambda f: f.get("restantes", 9999))
    escribir_excel(filas, salida)

    for k in ("NEGRO (vencida)", "ROJO", "AMARILLO", "VERDE", "SIN FECHA"):
        if conteo.get(k):
            print(f"  {k:16s}: {conteo[k]}")
    print("-" * 66)
    urgentes = [f for f in filas if f["semaforo"] in ("ROJO", "NEGRO (vencida)")]
    for f in urgentes[:15]:
        lim = f["limite"].strftime("%d/%m/%Y") if f.get("limite") else "?"
        print(f"  ! {f['factura']:16s} {f['semaforo']:16s} límite {lim}")
    if len(urgentes) > 15:
        print(f"  ... y {len(urgentes) - 15} urgentes más (ver Excel)")
    print(f"  Informe: {salida}")
    print("=" * 66)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Semáforo de plazos de respuesta a glosas (días hábiles CO)."
    )
    parser.add_argument("glosas", help="Excel con las glosas (factura + fecha de notificación).")
    parser.add_argument(
        "--plazo", type=int, default=20, help="Días hábiles de plazo (por defecto 20)."
    )
    parser.add_argument("--hoy", help="Fecha de corte AAAA-MM-DD (por defecto, hoy).")
    parser.add_argument("--salida", type=Path, help="Ruta del Excel de salida.")
    args = parser.parse_args(argv)

    excel = Path(args.glosas).expanduser()
    if not excel.is_file():
        sys.stderr.write(f"ERROR: no existe el Excel: {excel}\n")
        return 2
    if args.hoy and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.hoy):
        sys.stderr.write("ERROR: --hoy debe ser AAAA-MM-DD\n")
        return 2
    hoy = datetime.strptime(args.hoy, "%Y-%m-%d").date() if args.hoy else date.today()
    salida = args.salida or (excel.parent / "SEMAFORO_GLOSAS.xlsx")
    if salida.resolve() == excel.resolve():
        salida = excel.parent / "SEMAFORO_GLOSAS_2.xlsx"
    try:
        return procesar(excel, args.plazo, hoy, salida)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
