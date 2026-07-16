@echo off
REM ====================================================================
REM  TXT_A_EXCEL.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Por cada .txt deja DOS archivos junto al original:
REM    NOMBRE.csv  = delimitado por comas, para subir a la plataforma
REM    NOMBRE.xlsx = Excel con columnas, para revisarlo facil
REM
REM  Entiende .txt separados por comas (FURIPS), punto y coma, TAB o
REM  barra |, y tambien reportes con columnas alineadas con espacios
REM  (ancho fijo). El .txt original nunca se toca.
REM
REM  Sirve para UNA carpeta o masivo (carpeta + subcarpetas): el bot
REM  pregunta. Por defecto procesa la carpeta donde pongas este .cmd
REM  (funciona tambien en carpetas compartidas de red).
REM
REM  Se instala solo Python y openpyxl si faltan. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title TXT A EXCEL - Motor Glosas HUS

echo.
echo ============================================================
echo   TXT A EXCEL  -  deja cada .txt como .csv por comas + .xlsx
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 2) Asegurar openpyxl (para el Excel) ---------------------------
%PYEXE% -c "import openpyxl" >nul 2>&1 && goto motor
echo [i] Instalando el componente de Excel (openpyxl) por unica vez, espera...
%PYEXE% -m pip install --quiet --user openpyxl >nul 2>&1

:motor
REM --- 3) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0txt_a_excel.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\txt_a_excel.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\txt_a_excel_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Pedir carpeta (por defecto, donde esta este .cmd) -----------
set "CARPETA=%~dp0"
if "%CARPETA:~-1%"=="\" set "CARPETA=%CARPETA:~0,-1%"
echo   Carpeta a procesar (Enter para usar la carpeta de este .cmd):
echo   [%CARPETA%]
set /p "CARPETA=  Ruta: "
set "CARPETA=%CARPETA:"=%"
if "%CARPETA:~-1%"=="\" set "CARPETA=%CARPETA:~0,-1%"
if "%CARPETA:~-1%"==":" set "CARPETA=%CARPETA%/"
echo.
set "RECUR=S"
set /p "RECUR=  Incluir subcarpetas? (S/N, Enter = S): "
echo.

REM --- 5) Ejecutar -----------------------------------------------------
if /i "%RECUR%"=="N" (
  %PYEXE% "%MOTOR%" "%CARPETA%" --sin-recursion
) else (
  %PYEXE% "%MOTOR%" "%CARPETA%"
)
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Junto a cada .txt quedo su .csv por comas y su Excel. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
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
echo [ERROR] No se pudo preparar el motor. Copia tambien "txt_a_excel.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\txt_a_excel.py).
REM  cmd.exe nunca llega aqui (termina con exit /b mas arriba).
REM ====================================================================
#PYSTART#
"""txt_a_excel.py — Convierte archivos .txt "normales" (columnas alineadas con
espacios, ancho fijo) en archivos DELIMITADOS POR COMAS (.csv) listos para
subir a la plataforma, más un Excel (.xlsx) para revisarlos fácil. Usado por
TXT_A_EXCEL.cmd.

Pensado para las carpetas compartidas de auditoría: se puede apuntar a UNA
carpeta o correr masivamente sobre carpetas y subcarpetas. El .txt original
nunca se toca; junto a él quedan NOMBRE.csv y NOMBRE.xlsx.

Cómo parte las columnas (por archivo, automático):

    1. Si el .txt ya viene delimitado (TAB, ";", "|" o ","), usa ese signo.
    2. Si no, detecta el ANCHO FIJO: las posiciones que son espacio en TODAS
       las líneas marcan la frontera entre columnas (reportes alineados).
    3. Si tampoco, parte por tandas de 2+ espacios; y en el peor caso cada
       línea queda como una sola celda.

Reglas de seguridad (datos de facturación):

    - El .csv va delimitado por comas tal cual (comillas solo si el dato trae
      coma), en ANSI (cp1252), que es lo que esperan las plataformas.
    - En el .xlsx, los códigos con ceros a la izquierda (HUS0000533470, 001)
      y los números de más de 15 dígitos (NIT, CUFE) quedan como TEXTO.
      Lo ambiguo tipo 480.200 no se toca. En el .csv todo va textual.
    - Si el NOMBRE.csv / NOMBRE.xlsx destino ya existe y NO lo generó este
      bot, se omite (jamás pisa un archivo ajeno). Los del bot sí se refrescan.

USO:
    py tools\\txt_a_excel.py CARPETA
    py tools\\txt_a_excel.py CARPETA --sin-recursion
    py tools\\txt_a_excel.py CARPETA --simulacro
    py tools\\txt_a_excel.py CARPETA --delimitador ";"

Requiere openpyxl (para el Excel). El repo ya lo fija.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import re
import sys
from pathlib import Path

MARCA_CREADOR = "TXT_A_EXCEL - Motor Glosas HUS"
DELIMITADORES = ("\t", ";", "|", ",")  # estructurales primero: ganan el empate
MAX_FILAS_HOJA = 1_048_576  # límite duro de Excel por hoja
MAX_LARGO_CELDA = 32_767  # límite duro de Excel por celda

_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_RE_ENTERO = re.compile(r"-?\d+")
_RE_DECIMAL = re.compile(r"-?\d+\.\d+")
_RE_MILES_AMBIGUO = re.compile(r"-?\d{1,3}(\.\d{3})+")  # 480.200 / 1.234.567
_RE_DECORACION = re.compile(r"^[\s\-=_*·.]+$")  # líneas de adorno: ----- =====
_RE_DOS_ESPACIOS = re.compile(r" {2,}")


def decodificar(crudo: bytes) -> str:
    """UTF-8 (con o sin BOM) y, si no, cp1252 (tildes típicas de Windows)."""
    for cod in ("utf-8-sig", "cp1252"):
        try:
            return crudo.decode(cod)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", errors="replace")


def lineas_datos(texto: str) -> list[str]:
    """Líneas con contenido, sin las vacías ni las de adorno (-----)."""
    out = []
    for ln in texto.splitlines():
        if not ln.strip() or _RE_DECORACION.match(ln):
            continue
        out.append(ln)
    return out


def detectar_delimitador(lineas: list[str]) -> str | None:
    """El delimitador si el archivo YA viene delimitado; None si es de espacios."""
    muestra = lineas[:30]
    mejor, mejor_puntaje = None, 0.0
    for d in DELIMITADORES:
        cuentas = [ln.count(d) for ln in muestra]
        if not cuentas or max(cuentas) == 0:
            continue
        moda = max(set(cuentas), key=cuentas.count)
        if moda == 0:
            continue
        consistencia = cuentas.count(moda) / len(cuentas)
        if consistencia < 0.7:
            continue  # aparece suelto: no es el delimitador del archivo
        puntaje = consistencia * 100 + moda
        if puntaje > mejor_puntaje:
            mejor_puntaje, mejor = puntaje, d
    return mejor


def cortes_ancho_fijo(lineas: list[str]) -> list[tuple[int, int | None]]:
    """Campos (ini, fin) de un reporte alineado: las posiciones que son espacio
    en TODAS las líneas de la muestra separan las columnas."""
    muestra = lineas[:400]
    ancho = max(len(ln) for ln in muestra)
    perfil = [True] * ancho  # True = espacio en todas las líneas
    for ln in muestra:
        for i, ch in enumerate(ln):
            if ch != " " and perfil[i]:
                perfil[i] = False
    campos: list[tuple[int, int | None]] = []
    i = 0
    while i < ancho:
        if not perfil[i]:
            j = i
            while j < ancho and not perfil[j]:
                j += 1
            campos.append((i, j))
            i = j
        else:
            i += 1
    if campos:
        # el último campo llega hasta el final real de cada línea, por si
        # alguna línea fuera de la muestra es más larga
        campos[-1] = (campos[-1][0], None)
    return campos


def partir_lineas(lineas: list[str], delimitador: str | None = None) -> tuple[list[list[str]], str]:
    """Parte las líneas en campos. Devuelve (filas, método usado)."""
    d = delimitador or detectar_delimitador(lineas)
    if d:
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
        crudas = csv.reader(io.StringIO("\n".join(lineas)), delimiter=d)
        filas = [[c.strip() for c in f] for f in crudas if f]
        nombres = {"\t": "TAB", ",": "comas"}
        return filas, nombres.get(d, d)

    campos = cortes_ancho_fijo(lineas)
    if len(campos) >= 2:
        filas = [[ln[a:b].strip() for a, b in campos] for ln in lineas]
        return filas, "ancho fijo"

    filas = [_RE_DOS_ESPACIOS.split(ln.strip()) for ln in lineas]
    if max(len(f) for f in filas) >= 2:
        return filas, "espacios"

    return [[ln.strip()] for ln in lineas], "linea completa"


def valor_celda(campo: str):
    """Texto -> valor de celda (.xlsx) sin dañar códigos ni valores."""
    t = campo.strip()
    if not t:
        return None
    if _RE_ENTERO.fullmatch(t):
        sin_signo = t.lstrip("-")
        if len(sin_signo) > 1 and sin_signo.startswith("0"):
            return t  # código con ceros a la izquierda (HUS0000..., 001)
        if len(sin_signo) > 15:
            return t  # Excel pierde precisión: NIT largos, CUFE, etc.
        return int(t)
    if _RE_DECIMAL.fullmatch(t):
        if t.lstrip("-").startswith("0."):
            return float(t)
        if _RE_MILES_AMBIGUO.fullmatch(t):
            return t  # 480.200 podría ser 480200: en la duda, texto
        return float(t)
    return t


def texto_celda(v):
    """Limpia caracteres de control y respeta el largo máximo de celda."""
    if isinstance(v, str):
        v = _RE_CONTROL.sub("", v)
        if len(v) > MAX_LARGO_CELDA:
            v = v[:MAX_LARGO_CELDA]
    return v


def parece_encabezado(valores: list[list]) -> bool:
    """Primera fila toda texto (y con 2+ celdas) -> se resalta como encabezado."""
    if len(valores) < 2 or len(valores[0]) < 2:
        return False
    primera = [v for v in valores[0] if v is not None]
    if len(primera) < 2:
        return False
    return all(isinstance(v, str) for v in primera)


def es_del_bot(ruta: Path) -> bool:
    """True solo si el .xlsx lo generó este bot (marca en las propiedades)."""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(str(ruta), read_only=True)
        creador = wb.properties.creator or ""
        wb.close()
        return MARCA_CREADOR in creador
    except Exception:
        return False


def _anchos_columnas(valores: list[list], max_col: int) -> list[int]:
    anchos = [0] * max_col
    for fila in valores[:300]:
        for i, v in enumerate(fila):
            if v is None:
                continue
            largo = len(str(v))
            if largo > anchos[i]:
                anchos[i] = largo
    return [min(60, max(8, a + 2)) for a in anchos]


def escribir_csv(filas: list[list[str]], destino: Path) -> None:
    """CSV delimitado por comas, en ANSI (cp1252): es lo que esperan las
    plataformas y lo que Excel asume al abrir un .csv sin BOM."""
    datos = io.StringIO()
    csv.writer(datos).writerows(filas)
    contenido = datos.getvalue()
    try:
        crudo = contenido.encode("cp1252")
    except UnicodeEncodeError:
        crudo = contenido.encode("utf-8-sig")  # tiene caracteres fuera de ANSI
    tmp = destino.with_name(destino.name + ".tmp")
    try:
        tmp.write_bytes(crudo)
        tmp.replace(destino)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def escribir_xlsx(filas: list[list[str]], destino: Path) -> str:
    """Excel de revisión. Devuelve una nota si hubo que repartir en hojas."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    max_col = max(len(f) for f in filas)
    valores = [[texto_celda(valor_celda(c)) for c in f] for f in filas]
    encabezado = parece_encabezado(valores)
    anchos = _anchos_columnas(valores, max_col)

    wb = Workbook(write_only=True)
    wb.properties.creator = MARCA_CREADOR
    total = len(valores)
    inicio, num_hoja = 0, 0
    while inicio < total:
        num_hoja += 1
        ws = wb.create_sheet("Datos" if num_hoja == 1 else f"Datos_{num_hoja}")
        for i, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[get_column_letter(i)].width = ancho
        if encabezado and num_hoja == 1:
            ws.freeze_panes = "A2"
        for j, fila in enumerate(valores[inicio : inicio + MAX_FILAS_HOJA]):
            if encabezado and num_hoja == 1 and j == 0:
                celdas = []
                for v in fila:
                    c = WriteOnlyCell(ws, value=v)
                    c.font = Font(bold=True)
                    celdas.append(c)
                ws.append(celdas)
            else:
                ws.append(fila)
        inicio += MAX_FILAS_HOJA

    tmp = destino.with_name(destino.name + ".tmp")
    try:
        wb.save(str(tmp))
        tmp.replace(destino)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return f"repartido en {num_hoja} hojas (limite de Excel)" if num_hoja > 1 else ""


def convertir_uno(ruta: Path, delimitador: str | None = None, simulacro: bool = False) -> dict:
    """Convierte un .txt en NOMBRE.csv + NOMBRE.xlsx. Devuelve el resultado."""
    res = {
        "archivo": ruta.name,
        "estado": "ok",
        "motivo": "",
        "filas": 0,
        "columnas": 0,
        "metodo": "",
    }
    destino_csv = ruta.with_suffix(".csv")
    destino_xlsx = ruta.with_suffix(".xlsx")

    try:
        crudo = ruta.read_bytes()
    except OSError as exc:
        res.update(estado="error", motivo=f"no se pudo leer ({type(exc).__name__})")
        return res
    lineas = lineas_datos(decodificar(crudo))
    if not lineas:
        res.update(estado="omitido", motivo="archivo vacio")
        return res

    filas, metodo = partir_lineas(lineas, delimitador)
    filas = [f for f in filas if any(c for c in f)]
    if not filas:
        res.update(estado="omitido", motivo="sin datos")
        return res
    res["filas"] = len(filas)
    res["columnas"] = max(len(f) for f in filas)
    res["metodo"] = metodo

    # Jamás pisar archivos ajenos: la marca vive en el .xlsx del par.
    nuestro = destino_xlsx.exists() and es_del_bot(destino_xlsx)
    if destino_xlsx.exists() and not nuestro:
        res.update(
            estado="omitido", motivo=f"ya existe {destino_xlsx.name} y no lo genero este bot"
        )
        return res
    if destino_csv.exists() and not nuestro:
        res.update(estado="omitido", motivo=f"ya existe {destino_csv.name} y no lo genero este bot")
        return res
    if simulacro:
        res["estado"] = "simulacro"
        return res

    try:
        escribir_csv(filas, destino_csv)
    except Exception as exc:
        res.update(estado="error", motivo=f"no se pudo escribir el .csv ({type(exc).__name__})")
        return res
    try:
        nota = escribir_xlsx(filas, destino_xlsx)
        if nota:
            res["motivo"] = nota
    except Exception as exc:
        res.update(
            estado="error", motivo=f"el .csv quedo, pero fallo el Excel ({type(exc).__name__})"
        )
    return res


def procesar(
    raiz: Path,
    sin_recursion: bool = False,
    delimitador: str | None = None,
    simulacro: bool = False,
) -> int:
    buscador = raiz.glob if sin_recursion else raiz.rglob
    archivos = sorted(
        (a for a in buscador("*.txt") if a.is_file() and not a.name.startswith("~$")),
        key=lambda p: str(p).lower(),
    )

    print("=" * 66)
    print("  TXT A EXCEL — deja cada .txt delimitado por comas (.csv) + .xlsx")
    print("=" * 66)
    print(
        f"  Carpeta: {raiz}" + ("  (sin subcarpetas)" if sin_recursion else "  (con subcarpetas)")
    )
    print(f"  Archivos .txt encontrados: {len(archivos)}" + ("  |  SIMULACRO" if simulacro else ""))
    print("-" * 66)
    if not archivos:
        print("  No hay .txt para convertir aqui.")
        print("=" * 66)
        return 0

    ok = omitidos = errores = 0
    for a in archivos:
        r = convertir_uno(a, delimitador=delimitador, simulacro=simulacro)
        rel = a.relative_to(raiz) if a.is_relative_to(raiz) else a
        if r["estado"] in ("ok", "simulacro"):
            ok += 1
            extra = f"  [{r['motivo']}]" if r["motivo"] else ""
            print(
                f"  ✓ {rel}  ->  .csv + .xlsx"
                f"  ({r['filas']} fila(s) x {r['columnas']} col, {r['metodo']}){extra}"
            )
        elif r["estado"] == "omitido":
            omitidos += 1
            print(f"  · {rel}  omitido: {r['motivo']}")
        else:
            errores += 1
            print(f"  ✗ {rel}  ERROR: {r['motivo']}")

    print("-" * 66)
    print(f"  Convertidos: {ok}   Omitidos: {omitidos}   Errores: {errores}")
    if simulacro:
        print("  (simulacro: nada quedo escrito)")
    print("=" * 66)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte .txt (ancho fijo o delimitados) a .csv por comas + .xlsx.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("carpeta", nargs="?", default=".", help="Carpeta con los .txt.")
    parser.add_argument(
        "--sin-recursion", action="store_true", help="Solo la carpeta raíz, sin subcarpetas."
    )
    parser.add_argument(
        "--delimitador", help="Fuerza el delimitador de ENTRADA (p. ej. ';' o 'TAB')."
    )
    parser.add_argument("--simulacro", action="store_true", help="Muestra qué haría, sin escribir.")
    args = parser.parse_args(argv)

    raiz = Path(args.carpeta).expanduser()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    delim = args.delimitador
    if delim and delim.upper() == "TAB":
        delim = "\t"
    if delim and len(delim) != 1:
        sys.stderr.write("ERROR: el delimitador debe ser UN caracter (o TAB).\n")
        return 2

    return procesar(
        raiz.resolve(),
        sin_recursion=args.sin_recursion,
        delimitador=delim,
        simulacro=args.simulacro,
    )


if __name__ == "__main__":
    raise SystemExit(main())
