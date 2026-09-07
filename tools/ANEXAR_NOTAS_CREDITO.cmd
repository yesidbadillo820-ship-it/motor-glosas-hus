@echo off
REM ====================================================================
REM  ANEXAR_NOTAS_CREDITO.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM
REM  Pega la NOTA CREDITO de cada factura como ULTIMA HOJA del folio de
REM  esa factura (los archivos *_FACTURA.pdf de la carpeta de radicacion).
REM
REM  COMO SE USA:
REM    1) Copia este archivo DENTRO de la carpeta "NC ADRES"
REM       (la que tiene HUS354116.pdf, HUS354131.pdf, ...).
REM    2) Dale doble clic.
REM
REM  El bot busca solo la carpeta de radicacion: la carpeta hermana que
REM  empieza por "GI-" (por ejemplo GI-XX-XXXXX-2026). Si no la encuentra
REM  o hay varias, la pide.
REM
REM  PRIMERO SIMULA y muestra el cuadro de lo que haria; solo escribe si
REM  contestas que SI. Antes de tocar una factura guarda el folio original
REM  en la subcarpeta _FOLIOS_SIN_NOTA, asi que nada se pierde. Si lo
REM  corres otra vez NO vuelve a pegar la nota.
REM
REM  Deja el informe INFORME_NOTAS_CREDITO.csv en esta misma carpeta.
REM
REM  Es autocontenido: lleva el motor Python adentro. Si el equipo no
REM  tiene Python, el bot lo INSTALA SOLO (via winget o descargando el
REM  instalador oficial de python.org, sin pedir administrador). Solo
REM  necesita internet la primera vez.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion
title ANEXAR NOTAS CREDITO - Motor Glosas HUS

REM Carpeta donde vive este .cmd: ahi estan las notas credito.
set "NOTAS=%~dp0"
if "%NOTAS:~-1%"=="\" set "NOTAS=%NOTAS:~0,-1%"

echo.
echo ============================================================
echo   NOTAS CREDITO  -^>  ULTIMA HOJA DE LA FACTURA
echo ============================================================
echo   Notas credito: "%NOTAS%"

REM --- 1) Buscar la carpeta de radicacion (la hermana "GI-*") ---------
set "RADICACION=%~1"
if defined RADICACION goto tengorad
set "PADRE=%NOTAS%\.."
set "CUANTAS=0"
for /d %%D in ("%PADRE%\GI-*") do (
  set /a CUANTAS+=1
  set "RADICACION=%%~fD"
)
if "%CUANTAS%"=="1" goto tengorad
if "%CUANTAS%"=="0" (
  echo.
  echo [ATENCION] No encontre la carpeta de radicacion "GI-..." al lado
  echo            de esta carpeta.
) else (
  echo.
  echo [ATENCION] Hay %CUANTAS% carpetas "GI-..." al lado. No adivino cual es.
)
echo.
echo   Arrastra aqui la carpeta de radicacion y pulsa ENTER
set /p "RADICACION=   Carpeta: "
set "RADICACION=%RADICACION:"=%"

:tengorad
if not exist "%RADICACION%\" (
  echo.
  echo [ERROR] No existe la carpeta de radicacion: "%RADICACION%"
  echo.
  pause
  exit /b 2
)
echo   Radicacion  : "%RADICACION%"
echo.

REM --- 2) Buscar Python en el equipo ----------------------------------
REM  Se valida EJECUTANDO cada candidato (no con "where"): en Windows
REM  10/11 sin Python, "where python" encuentra el alias falso de la
REM  Microsoft Store y el bot moriria con codigo 9009.
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 3) Asegurar el componente PDF (PyPDF2 / pypdf) -----------------
%PYEXE% -c "import PyPDF2" >nul 2>&1 && goto haspdf
%PYEXE% -c "import pypdf"  >nul 2>&1 && goto haspdf
echo [i] Instalando el componente PDF (PyPDF2) por unica vez, espera...
%PYEXE% -m pip install --quiet --user PyPDF2 >nul 2>&1
:haspdf

REM --- 4) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0anexar_notas_credito_adres.py"
if exist "%MOTOR%" goto simular
set "MOTOR=%~dp0tools\anexar_notas_credito_adres.py"
if exist "%MOTOR%" goto simular
set "MOTOR=%TEMP%\anexar_notas_credito_hus.py"
set "ORIGENCMD=%~f0"
REM  Borrar cualquier motor viejo cacheado: si la extraccion fallara, NO
REM  se debe ejecutar en silencio una version anterior desde %TEMP%.
del "%MOTOR%" >nul 2>&1
REM  Las rutas viajan por variables de entorno ($env:...) y no interpoladas
REM  en el comando: asi un apostrofe o comilla en la ruta no rompe PowerShell.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:simular
REM --- 5) Primero el simulacro: no se toca nada -----------------------
echo ------------------------------------------------------------
echo   PASO 1 de 2 - SIMULACRO (no se modifica ningun archivo)
echo ------------------------------------------------------------
%PYEXE% "%MOTOR%" "%NOTAS%" "%RADICACION%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [ATENCION] El simulacro termino con codigo %RC% - revisa arriba.
  echo.
  pause
  exit /b %RC%
)

echo ------------------------------------------------------------
echo   PASO 2 de 2 - APLICAR
echo ------------------------------------------------------------
echo   Revisa el cuadro de arriba. Si esta bien, escribe  SI  y ENTER.
echo   Cualquier otra cosa cancela y no se toca nada.
set "SEGUIR="
set /p "SEGUIR=   Aplicar? (SI/NO): "
if /i not "%SEGUIR%"=="SI" (
  echo.
  echo   Cancelado. No se modifico ningun archivo.
  echo.
  pause
  exit /b 0
)

%PYEXE% "%MOTOR%" "%NOTAS%" "%RADICACION%" --aplicar
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Cada factura quedo con su nota credito de ultima hoja. & echo      Los folios originales estan en "%RADICACION%\_FOLIOS_SIN_NOTA". ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
echo.
pause
exit /b %RC%

REM ==== Instalacion automatica de Python ==============================
REM  Se intenta primero winget (viene con Windows 10/11) y si no,
REM  descargando el instalador oficial de python.org. Instalacion
REM  por-usuario: NO pide permisos de administrador.
:instalarpython
echo [i] No se encontro Python en este equipo.
echo [i] Instalando Python automaticamente - es gratis y no pide permisos
echo     de administrador. Puede tardar unos minutos, NO cierres esta
echo     ventana...
echo.

where winget >nul 2>&1 || goto py_descarga
echo [i] Instalando Python con winget...
winget install -e --id Python.Python.3.12 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements >nul 2>&1
call :redetectar
if defined PYEXE goto pyok

:py_descarga
set "PYINST=%TEMP%\python_instalador_hus.exe"
set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
del "%PYINST%" >nul 2>&1
echo [i] Descargando Python desde python.org - 25 MB aprox., espera...
curl.exe -L -s -o "%PYINST%" "%PYURL%" 2>nul
if exist "%PYINST%" goto py_instalar
powershell -NoProfile -Command "Invoke-WebRequest -Uri $env:PYURL -OutFile $env:PYINST" >nul 2>&1
if not exist "%PYINST%" goto sinpython

:py_instalar
echo [i] Instalando Python - solo para tu usuario, sin administrador...
"%PYINST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYINST%" >nul 2>&1
call :redetectar
if defined PYEXE goto pyok
goto sinpython

:pyok
echo [OK] Python quedo instalado en este equipo. Continuando...
echo.
goto deps

REM  Vuelve a buscar Python despues de instalarlo. Se revisa tambien la
REM  carpeta tipica de la instalacion por-usuario, porque el PATH de la
REM  ventana actual no se refresca solo.
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
echo [ERROR] No se pudo instalar Python automaticamente en este equipo.
echo         Suele pasar cuando no hay internet o las politicas del
echo         equipo bloquean instalaciones.
echo.
echo   Para instalarlo a mano (gratis, 2 minutos):
echo     1^) Descargalo de:  https://www.python.org/downloads/
echo     2^) En el instalador MARCA la casilla "Add python.exe to PATH".
echo     3^) Vuelve a dar doble clic a este archivo.
echo.
pause
exit /b 1

:sinmotor
echo [ERROR] No se pudo preparar el motor.
echo         Copia tambien "anexar_notas_credito_adres.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python
REM  (copia embebida de tools\anexar_notas_credito_adres.py, salvo el fin
REM  de linea). cmd.exe NUNCA llega aqui: el script termina con "exit /b"
REM  mas arriba. Esta copia solo se usa si el .cmd viaja solo, sin el
REM  .py al lado.
REM ====================================================================
#PYSTART#
"""anexar_notas_credito_adres.py — Pega la nota crédito al final de la factura.

Para radicar en el ADRES, la nota crédito de cada factura tiene que quedar
DENTRO del folio de la factura, como última hoja. Este bot lo hace solo.

    NC ADRES\\HUS354116.pdf
              +
    GI-XX-XXXXX-2026\\680010079201_HUS354116_FACTURA.pdf
              ↓
    GI-XX-XXXXX-2026\\680010079201_HUS354116_FACTURA.pdf
        (las hojas de siempre + la nota crédito de última)

Cómo empareja: toma el número de factura del nombre de la nota (`HUS354116.pdf`)
y busca en la carpeta de radicación el archivo que termine en
`_HUS354116_FACTURA.pdf`. Los ceros de más no estorban: `HUS0000354116` y
`HUS354116` se consideran la misma factura.

Nunca destruye nada: antes de tocar una factura guarda el original en la
subcarpeta `_FOLIOS_SIN_NOTA`. Si esa copia ya existe, esa factura YA tiene su
nota pegada y el bot la salta — así se puede correr las veces que haga falta sin
que la nota quede dos veces. Con `--rehacer` restaura desde esa copia y vuelve a
pegar la nota (útil si cambió la nota crédito).

Por defecto SOLO SIMULA: muestra el cuadro de lo que haría y no escribe nada.
Para que escriba de verdad hay que pasarle `--aplicar`.

USO:
    py tools\\anexar_notas_credito_adres.py "Z:\\...\\NC ADRES" "Z:\\...\\GI-XX-XXXXX-2026"
    py tools\\anexar_notas_credito_adres.py "...\\NC ADRES" "...\\GI-XX-XXXXX-2026" --aplicar
    py tools\\anexar_notas_credito_adres.py "...\\NC ADRES" "...\\GI-XX-XXXXX-2026" --rehacer --aplicar

Deja siempre el informe `INFORME_NOTAS_CREDITO.csv` en la carpeta de las notas:
factura por factura, cuántas hojas tenía, cuántas trae la nota, cuántas quedaron
y qué pasó. Ese es el papel para el auditor.

Normalmente NO se ejecuta a mano: `ANEXAR_NOTAS_CREDITO.cmd` lo lanza con doble
clic.

Requiere PyPDF2 (o pypdf). El repo ya fija PyPDF2==3.0.1.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Donde se guarda el folio tal como estaba antes de pegarle la nota.
RESPALDO = "_FOLIOS_SIN_NOTA"
INFORME = "INFORME_NOTAS_CREDITO.csv"

SUFIJO_FACTURA = "_FACTURA.pdf"

# `HUS354116.pdf`, `HUS 0000354116.pdf`, `NC HUS354116.pdf`…
_RE_FACTURA = re.compile(r"HUS\s*0*(\d+)", re.IGNORECASE)


def _cargar_lector_escritor():
    """Devuelve (PdfReader, PdfWriter) desde pypdf o PyPDF2, lo que haya."""
    try:
        from pypdf import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        sys.stderr.write(
            "\nERROR: falta el componente para leer PDF (PyPDF2 / pypdf).\n"
            "       Instálalo con:  py -m pip install PyPDF2\n\n"
        )
        raise SystemExit(2)


def numero_de_factura(nombre: str) -> str | None:
    """`680010079201_HUS0000354116_FACTURA.pdf` → `HUS354116`.

    Devuelve None si el nombre no trae un número de factura reconocible.
    """
    hallado = _RE_FACTURA.search(nombre)
    return f"HUS{hallado.group(1).lstrip('0') or '0'}" if hallado else None


def notas_de_la_carpeta(carpeta: Path) -> dict[str, Path]:
    """Las notas crédito de la carpeta, indexadas por número de factura.

    Si dos archivos apuntan a la misma factura se queda con el primero en orden
    alfabético y el otro se reporta aparte (ver `notas_repetidas`).
    """
    notas: dict[str, Path] = {}
    for pdf in sorted(carpeta.glob("*.pdf")):
        if pdf.parent.name == RESPALDO:
            continue
        factura = numero_de_factura(pdf.name)
        if factura:
            notas.setdefault(factura, pdf)
    return notas


def notas_repetidas(carpeta: Path) -> list[tuple[str, Path]]:
    """Las notas que apuntan a una factura que ya tenía otra nota."""
    vistas: set[str] = set()
    repetidas: list[tuple[str, Path]] = []
    for pdf in sorted(carpeta.glob("*.pdf")):
        factura = numero_de_factura(pdf.name)
        if not factura:
            continue
        if factura in vistas:
            repetidas.append((factura, pdf))
        vistas.add(factura)
    return repetidas


def facturas_de_la_radicacion(carpeta: Path) -> dict[str, Path]:
    """Los folios `*_FACTURA.pdf` de la carpeta de radicación, por factura."""
    folios: dict[str, Path] = {}
    for pdf in sorted(carpeta.glob(f"*{SUFIJO_FACTURA}")):
        factura = numero_de_factura(pdf.name)
        if factura:
            folios.setdefault(factura, pdf)
    return folios


def hojas(pdf: Path, PdfReader=None) -> int:
    """Cuántas páginas tiene el PDF. 0 si no se puede leer."""
    if PdfReader is None:
        PdfReader, _ = _cargar_lector_escritor()
    try:
        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return 0


@dataclass
class Resultado:
    """Lo que pasó con una factura. Es lo que sale en el informe."""

    factura: str
    nota: str = ""
    folio: str = ""
    hojas_antes: int = 0
    hojas_nota: int = 0
    hojas_despues: int = 0
    estado: str = ""

    @property
    def cuadra(self) -> bool:
        """Las hojas de después tienen que ser las de antes más las de la nota."""
        return self.hojas_despues == self.hojas_antes + self.hojas_nota


def _pegar(folio: Path, nota: Path, PdfReader, PdfWriter) -> int:
    """Escribe el folio con la nota de última hoja. Devuelve las hojas que quedaron."""
    escritor = PdfWriter()
    for pagina in PdfReader(str(folio)).pages:
        escritor.add_page(pagina)
    for pagina in PdfReader(str(nota)).pages:
        escritor.add_page(pagina)
    # Se escribe a un temporal y solo al final se reemplaza: si el disco de red
    # se cae a mitad de camino, el folio bueno no queda partido.
    temporal = folio.with_suffix(".pdf.tmp")
    with temporal.open("wb") as destino:
        escritor.write(destino)
    temporal.replace(folio)
    return len(escritor.pages)


def anexar(
    carpeta_notas: Path,
    carpeta_radicacion: Path,
    aplicar: bool = False,
    rehacer: bool = False,
) -> list[Resultado]:
    """Pega cada nota crédito al final de su factura. Devuelve el informe."""
    PdfReader, PdfWriter = _cargar_lector_escritor()
    notas = notas_de_la_carpeta(carpeta_notas)
    folios = facturas_de_la_radicacion(carpeta_radicacion)
    respaldos = carpeta_radicacion / RESPALDO

    resultados: list[Resultado] = []
    for factura in sorted(notas):
        nota = notas[factura]
        folio = folios.get(factura)
        r = Resultado(factura=factura, nota=nota.name)
        if folio is None:
            r.estado = "la factura no está en la carpeta de radicación"
            resultados.append(r)
            continue

        r.folio = folio.name
        r.hojas_nota = hojas(nota, PdfReader)
        respaldo = respaldos / folio.name
        ya_estaba = respaldo.exists()

        if ya_estaba and not rehacer:
            r.hojas_antes = hojas(respaldo, PdfReader)
            r.hojas_despues = hojas(folio, PdfReader)
            r.estado = "ya tenía la nota pegada, no se toca"
            resultados.append(r)
            continue

        origen = respaldo if (ya_estaba and rehacer) else folio
        r.hojas_antes = hojas(origen, PdfReader)
        if r.hojas_antes == 0 or r.hojas_nota == 0:
            r.estado = "no se pudo leer el PDF (¿dañado o abierto en otro programa?)"
            resultados.append(r)
            continue

        if not aplicar:
            r.hojas_despues = r.hojas_antes + r.hojas_nota
            r.estado = "SIMULACRO: se pegaría la nota de última hoja"
            resultados.append(r)
            continue

        try:
            if ya_estaba and rehacer:
                shutil.copy2(respaldo, folio)
            else:
                respaldos.mkdir(parents=True, exist_ok=True)
                shutil.copy2(folio, respaldo)
            r.hojas_despues = _pegar(folio, nota, PdfReader, PdfWriter)
        except Exception as e:  # el folio original sigue guardado en el respaldo
            r.estado = f"ERROR: {e}"
            resultados.append(r)
            continue

        r.estado = "nota pegada de última hoja" if r.cuadra else "OJO: las hojas no cuadran"
        resultados.append(r)

    # Las facturas del paquete que no tienen nota crédito también se reportan:
    # el auditor necesita saber cuáles quedaron sin nota.
    for factura in sorted(set(folios) - set(notas)):
        resultados.append(
            Resultado(
                factura=factura,
                folio=folios[factura].name,
                estado="sin nota crédito en la carpeta",
            )
        )
    return resultados


def escribir_informe(resultados: list[Resultado], destino: Path) -> Path:
    """Deja el CSV con lo que pasó factura por factura."""
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(
            [
                "FACTURA",
                "NOTA CREDITO",
                "FOLIO DE LA FACTURA",
                "HOJAS ANTES",
                "HOJAS DE LA NOTA",
                "HOJAS DESPUES",
                "QUE PASO",
            ]
        )
        for r in resultados:
            escritor.writerow(
                [
                    r.factura,
                    r.nota,
                    r.folio,
                    r.hojas_antes or "",
                    r.hojas_nota or "",
                    r.hojas_despues or "",
                    r.estado,
                ]
            )
    return destino


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Pega la nota crédito de cada factura como última hoja de su folio."
    )
    p.add_argument("notas", type=Path, help="carpeta con las notas crédito (NC ADRES)")
    p.add_argument("radicacion", type=Path, help="carpeta de radicación (GI-XX-XXXXX-2026)")
    p.add_argument(
        "--aplicar",
        action="store_true",
        help="escribir de verdad (sin esto solo simula y no toca nada)",
    )
    p.add_argument(
        "--rehacer",
        action="store_true",
        help="volver a pegar la nota partiendo del folio guardado en " + RESPALDO,
    )
    a = p.parse_args(argv)

    for carpeta in (a.notas, a.radicacion):
        if not carpeta.is_dir():
            print(f"No existe la carpeta: {carpeta}")
            return 2

    repetidas = notas_repetidas(a.notas)
    resultados = anexar(a.notas, a.radicacion, aplicar=a.aplicar, rehacer=a.rehacer)
    informe = escribir_informe(resultados, a.notas / INFORME)

    pegadas = [r for r in resultados if r.estado.startswith("nota pegada")]
    simuladas = [r for r in resultados if r.estado.startswith("SIMULACRO")]
    ya = [r for r in resultados if r.estado.startswith("ya tenía")]
    sin_folio = [r for r in resultados if r.estado.startswith("la factura no está")]
    sin_nota = [r for r in resultados if r.estado.startswith("sin nota")]
    malos = [r for r in resultados if r.estado.startswith(("ERROR", "OJO", "no se pudo"))]

    print()
    print("=" * 68)
    print("  NOTAS CRÉDITO -> ÚLTIMA HOJA DE LA FACTURA")
    print("=" * 68)
    print(f"  notas crédito en la carpeta : {len(notas_de_la_carpeta(a.notas))}")
    print(f"  facturas en la radicación   : {len(facturas_de_la_radicacion(a.radicacion))}")
    print()
    if a.aplicar:
        print(f"  notas pegadas               : {len(pegadas)}")
    else:
        print(f"  se pegarían (SIMULACRO)     : {len(simuladas)}")
    print(f"  ya la tenían pegada         : {len(ya)}")
    print(f"  notas sin factura           : {len(sin_folio)}")
    print(f"  facturas sin nota           : {len(sin_nota)}")
    print(f"  con problema                : {len(malos)}")
    if repetidas:
        print(f"  notas repetidas (se usó la primera): {len(repetidas)}")

    for r in sin_folio + malos:
        print(f"     - {r.factura}: {r.estado}")
    for factura, pdf in repetidas:
        print(f"     - {factura}: también existe {pdf.name}")

    if not a.aplicar:
        print()
        print("  Esto fue un SIMULACRO: no se tocó ningún archivo.")
        print("  Para hacerlo de verdad, vuelve a correrlo con  --aplicar")
    else:
        print()
        print(f"  Los folios originales quedaron guardados en: {RESPALDO}")
    print(f"  Informe: {informe}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
