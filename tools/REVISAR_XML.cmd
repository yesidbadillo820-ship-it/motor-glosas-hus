@echo off
REM ====================================================================
REM  REVISAR_XML.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Revisa los XML de factura electronica en salud y saca a un Excel la
REM  informacion de CONTRATO de cada factura (para responder la glosa
REM  "factura sin contrato"): NUMERO_CONTRATO, FACTURA_SIN_CONTRATO,
REM  MODALIDAD_PAGO, cobertura, validacion DIAN, valor y fecha.
REM
REM  Te pide la carpeta con los XML (por defecto la ruta de red del HUS).
REM  Si pones un archivo "facturas.txt" (una factura por linea) junto a
REM  este .cmd, solo revisa esas; si no, revisa todos los XML.
REM  El Excel queda junto a este archivo (INFORME_REVISION_XML.xlsx).
REM
REM  Se instala solo Python y openpyxl si faltan. No cambia nada del PC.
REM  USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title REVISAR XML - Motor Glosas HUS

echo.
echo ============================================================
echo   REVISAR XML  -  info de contrato de las facturas en salud
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
set "MOTOR=%~dp0revisar_xml_facturas.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\revisar_xml_facturas.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\revisar_xml_facturas_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Pedir la carpeta con los XML (con ruta por defecto) ---------
set "CARPETA=\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD"
echo   Carpeta con los XML (Enter para usar la de por defecto):
echo   [%CARPETA%]
set /p "CARPETA=  Ruta: "
echo.

REM --- 5) Ejecutar (con lista si existe facturas.txt al lado) ---------
if exist "%~dp0facturas.txt" (
  echo [i] Usando la lista facturas.txt que esta junto a este .cmd.
  %PYEXE% "%MOTOR%" "%CARPETA%" --lista "%~dp0facturas.txt" --salida "%~dp0INFORME_REVISION_XML.xlsx"
) else (
  echo [i] No hay facturas.txt: se revisan TODOS los XML de la carpeta.
  %PYEXE% "%MOTOR%" "%CARPETA%" --salida "%~dp0INFORME_REVISION_XML.xlsx"
)
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Revisa el INFORME_REVISION_XML.xlsx junto a este archivo. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
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
echo [ERROR] No se pudo preparar el motor. Copia tambien "revisar_xml_facturas.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\revisar_xml_facturas.py).
REM  cmd.exe nunca llega aqui (termina con exit /b mas arriba).
REM ====================================================================
#PYSTART#
"""revisar_xml_facturas.py — Revisa los XML de factura electrónica en salud y
extrae la información de CONTRATO para responder la glosa "factura sin contrato".

Por cada XML (AttachedDocument de la DIAN) entra a la factura embebida (el
Invoice que va dentro del CDATA) y lee los campos de interoperabilidad del
sector salud:

    NUMERO_CONTRATO, NUMERO_POLIZA, FACTURA_SIN_CONTRATO, MODALIDAD_PAGO,
    COBERTURA_PLAN_BENEFICIOS, CODIGO_PRESTADOR

...además del número de factura, fecha, valor, la EPS adquirente y el estado
de validación de la DIAN. Con eso arma un Excel (una fila por factura) que
sirve como anexo de prueba: muestra que el XML SÍ trae número de contrato y/o
la causa de atención (p. ej. ATENCION DE URGENCIAS).

Puede filtrar por una lista de facturas (archivo de texto, una por línea) o
procesar todos los XML de la carpeta.

USO:
    py tools\\revisar_xml_facturas.py "\\\\172.16.32.83\\factura_electronica_net22\\202607\\FACTURAS_SALUD"
    py tools\\revisar_xml_facturas.py CARPETA --lista facturas.txt --salida INFORME.xlsx
    py tools\\revisar_xml_facturas.py .        # carpeta actual, todos los XML

Requiere openpyxl (para el Excel). El repo ya lo fija.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# Campos de salud que nos interesan (nombre tal cual en el XML).
CAMPOS_SALUD = [
    "NUMERO_CONTRATO",
    "NUMERO_POLIZA",
    "FACTURA_SIN_CONTRATO",
    "MODALIDAD_PAGO",
    "COBERTURA_PLAN_BENEFICIOS",
    "CODIGO_PRESTADOR",
]


def _local(tag: str) -> str:
    """Nombre de la etiqueta sin el namespace ({...}Algo -> Algo)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _texto(elem, nombre: str) -> str:
    """Primer texto de un descendiente cuyo nombre local sea `nombre`."""
    for e in elem.iter():
        if _local(e.tag) == nombre and e.text and e.text.strip():
            return e.text.strip()
    return ""


def _cdata_con(raiz, marcador: str) -> str | None:
    """Devuelve el texto (CDATA) de la primera Description que contenga
    `marcador` (p. ej. '<Invoice' o 'ApplicationResponse')."""
    for e in raiz.iter():
        if _local(e.tag) == "Description" and e.text and marcador in e.text:
            return e.text
    return None


def _parse_xml(texto: str):
    """Parsea un string XML tolerando el prologo <?xml ...?>."""
    limpio = re.sub(r"^\s*<\?xml[^>]*\?>", "", texto).strip()
    return ET.fromstring(limpio)


def normalizar_factura(valor: str) -> str:
    """HUS0000533470 / HUS533470 / 533470 -> '533470' (para comparar)."""
    digitos = re.sub(r"\D", "", valor or "")
    return digitos.lstrip("0") or digitos


def revisar_uno(ruta: Path) -> dict | None:
    """Extrae los datos de un XML de factura. None si no es una factura válida."""
    try:
        raiz = ET.parse(str(ruta)).getroot()
    except Exception as exc:
        return {"archivo": ruta.name, "error": f"XML ilegible ({type(exc).__name__})"}

    factura = _texto(raiz, "ParentDocumentID")
    eps = _texto(raiz, "RegistrationName")  # ReceiverParty va primero en el AttachedDocument
    validacion = _texto(raiz, "ValidationResultCode")

    datos = {
        "archivo": ruta.name,
        "factura": factura,
        "eps": eps,
        "fecha": "",
        "valor": "",
        "validacion_dian": "02 (validado)" if validacion == "02" else (validacion or ""),
        "error": "",
    }
    for c in CAMPOS_SALUD:
        datos[c] = ""

    # Entrar a la factura embebida (Invoice dentro del CDATA).
    cdata = _cdata_con(raiz, "<Invoice")
    if not cdata:
        datos["error"] = "sin Invoice embebido (¿no es factura?)"
        return datos
    try:
        inv = _parse_xml(cdata)
    except Exception as exc:
        datos["error"] = f"Invoice embebido ilegible ({type(exc).__name__})"
        return datos

    if not datos["factura"]:
        datos["factura"] = _texto(inv, "ID")
    datos["fecha"] = _texto(inv, "IssueDate")
    datos["valor"] = _texto(inv, "PayableAmount")

    # Campos de interoperabilidad en salud (pares Name/Value).
    for ai in inv.iter():
        if _local(ai.tag) != "AdditionalInformation":
            continue
        nombre = ""
        valor = ""
        for hijo in ai:
            if _local(hijo.tag) == "Name":
                nombre = (hijo.text or "").strip()
            elif _local(hijo.tag) == "Value":
                valor = (hijo.text or "").strip()
        if nombre in CAMPOS_SALUD:
            datos[nombre] = valor

    return datos


def conclusion(d: dict) -> str:
    """Frase de argumento para la glosa 'sin contrato'."""
    if d.get("error"):
        return f"REVISAR: {d['error']}"
    partes = []
    if d.get("NUMERO_CONTRATO"):
        partes.append(f"SÍ trae contrato: {d['NUMERO_CONTRATO']}")
    else:
        partes.append("Sin NUMERO_CONTRATO en el XML")
    if d.get("FACTURA_SIN_CONTRATO"):
        partes.append(f"causa de cobertura: {d['FACTURA_SIN_CONTRATO']}")
    if d.get("validacion_dian", "").startswith("02"):
        partes.append("validada por DIAN")
    return " · ".join(partes)


def cargar_lista(ruta: Path) -> set[str]:
    pedidas = set()
    for ln in ruta.read_text(encoding="utf-8-sig").splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            pedidas.add(normalizar_factura(s))
    return pedidas


def escribir_excel(filas: list[dict], salida: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl.  py -m pip install openpyxl\n")
        sys.exit(2)

    wb = Workbook()
    ws = wb.active
    ws.title = "Revision XML"
    encabezados = [
        "Factura",
        "Fecha",
        "Valor (XML)",
        "EPS adquirente",
        "NUMERO_CONTRATO",
        "FACTURA_SIN_CONTRATO",
        "MODALIDAD_PAGO",
        "COBERTURA_PLAN_BENEFICIOS",
        "NUMERO_POLIZA",
        "CODIGO_PRESTADOR",
        "Validación DIAN",
        "Conclusión (argumento glosa)",
        "Archivo XML",
    ]
    ws.append(encabezados)
    azul = PatternFill("solid", fgColor="1F4E79")
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = azul
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    verde = PatternFill("solid", fgColor="E2EFDA")
    amarillo = PatternFill("solid", fgColor="FFF2CC")
    for d in filas:
        ws.append(
            [
                d.get("factura", ""),
                d.get("fecha", ""),
                d.get("valor", ""),
                d.get("eps", ""),
                d.get("NUMERO_CONTRATO", ""),
                d.get("FACTURA_SIN_CONTRATO", ""),
                d.get("MODALIDAD_PAGO", ""),
                d.get("COBERTURA_PLAN_BENEFICIOS", ""),
                d.get("NUMERO_POLIZA", ""),
                d.get("CODIGO_PRESTADOR", ""),
                d.get("validacion_dian", ""),
                conclusion(d),
                d.get("archivo", ""),
            ]
        )
        fila = ws[ws.max_row]
        if d.get("error"):
            for c in fila:
                c.fill = amarillo
        elif d.get("NUMERO_CONTRATO") or d.get("FACTURA_SIN_CONTRATO"):
            for c in fila:
                c.fill = verde

    anchos = [16, 12, 14, 34, 22, 24, 16, 28, 14, 16, 16, 46, 26]
    for i, w in enumerate(anchos, start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    wb.save(str(salida))


def procesar(raiz: Path, lista: Path | None, salida: Path) -> int:
    xmls = sorted(raiz.rglob("*.xml"), key=lambda p: p.name.lower())
    if not xmls:
        print(f"No se encontraron archivos .xml en {raiz}")
        return 0

    pedidas = cargar_lista(lista) if lista else None

    print("=" * 66)
    print("  REVISION DE XML — informacion de contrato para la glosa")
    print("=" * 66)
    print(f"  Carpeta: {raiz}")
    print(
        f"  XML encontrados: {len(xmls)}"
        + (f"  |  Lista pedida: {len(pedidas)}" if pedidas else "")
    )
    print("-" * 66)

    filas = []
    vistas = set()
    con_contrato = 0
    for x in xmls:
        d = revisar_uno(x)
        if not d:
            continue
        norm = normalizar_factura(d.get("factura", ""))
        if pedidas is not None and norm not in pedidas:
            continue
        filas.append(d)
        if norm:
            vistas.add(norm)
        if d.get("NUMERO_CONTRATO"):
            con_contrato += 1
        marca = "✓" if (d.get("NUMERO_CONTRATO") or d.get("FACTURA_SIN_CONTRATO")) else "·"
        if d.get("error"):
            marca = "✗"
        print(
            f"  {marca} {d.get('factura', '?'):16s}  contrato={d.get('NUMERO_CONTRATO', ''):20s} "
            f"sin_contrato={d.get('FACTURA_SIN_CONTRATO', '')}"
        )

    # ordenar por factura
    filas.sort(key=lambda d: normalizar_factura(d.get("factura", "")))
    escribir_excel(filas, salida)

    print("-" * 66)
    print(f"  Facturas en el informe: {len(filas)}")
    print(f"  Con NUMERO_CONTRATO en el XML: {con_contrato}")
    print(
        f"  Con marca FACTURA_SIN_CONTRATO: {sum(1 for d in filas if d.get('FACTURA_SIN_CONTRATO'))}"
    )
    if pedidas is not None:
        faltan = sorted(pedidas - vistas)
        if faltan:
            print(f"  OJO: {len(faltan)} factura(s) de la lista NO se encontraron como XML:")
            print("       " + ", ".join(faltan[:30]) + (" ..." if len(faltan) > 30 else ""))
    print(f"  Informe Excel: {salida}")
    print("=" * 66)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Revisa los XML de factura en salud y saca la info de contrato.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("carpeta", nargs="?", default=".", help="Carpeta con los XML.")
    parser.add_argument(
        "--lista", type=Path, help="Archivo .txt con las facturas a filtrar (una por línea)."
    )
    parser.add_argument("--salida", type=Path, help="Ruta del Excel de salida.")
    args = parser.parse_args(argv)

    raiz = Path(args.carpeta).expanduser()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    salida = args.salida or (raiz / "INFORME_REVISION_XML.xlsx")
    if args.lista and not args.lista.is_file():
        sys.stderr.write(f"ERROR: no existe la lista: {args.lista}\n")
        return 2

    return procesar(raiz.resolve(), args.lista, salida)


if __name__ == "__main__":
    raise SystemExit(main())
