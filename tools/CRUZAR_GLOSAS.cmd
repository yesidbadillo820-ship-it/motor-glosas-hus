@echo off
REM ====================================================================
REM  CRUZAR_GLOSAS.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Cruza el Excel de glosas que mando la EPS con los XML radicados y
REM  genera CRUCE_GLOSAS.xlsx (evidencia de contrato por factura) y
REM  BORRADORES_RESPUESTA.txt (borrador de respuesta por causal, para
REM  revision del auditor). Pon el Excel de la EPS junto a este .cmd.
REM
REM  Se instala solo Python si falta. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title CRUZAR GLOSAS - Excel EPS contra XML - Motor Glosas HUS

echo.
echo ============================================================
echo   CRUZAR GLOSAS - Excel EPS contra XML
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
set "MOTOR=%~dp0cruzar_glosas_xml.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\cruzar_glosas_xml.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\cruzar_glosas_xml_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Excel de glosas de la EPS (detecta el primero junto al cmd) -
set "GLOSAS="
for /f "delims=" %%F in ('dir /b /a-d "%~dp0*.xlsx" 2^>nul ^| findstr /v /i /b "CRUCE_ SEMAFORO_ VERIFICACION_ INFORME_ BORRADORES_"') do if not defined GLOSAS set "GLOSAS=%~dp0%%F"
echo   Excel de GLOSAS que mando la EPS (Enter para usar el detectado):
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
REM --- 5) Carpeta con los XML radicados -------------------------------
set "DEFCARP=\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD"
set "CARPETA=%DEFCARP%"
echo   Carpeta con los XML radicados (Enter para usar la de por defecto):
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

REM --- 6) Ejecutar -----------------------------------------------------
%PYEXE% "%MOTOR%" "%GLOSAS%" "%CARPETA%" --salida "%~dp0CRUCE_GLOSAS.xlsx"

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
echo [ERROR] No se pudo preparar el motor. Copia tambien "cruzar_glosas_xml.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\cruzar_glosas_xml.py).
REM  cmd.exe nunca llega aqui (termina con exit /b mas arriba).
REM ====================================================================
#PYSTART#
"""cruzar_glosas_xml.py — Cruza el Excel de glosas que manda la EPS con los
XML radicados y genera, por cada glosa, la evidencia del XML y un BORRADOR de
respuesta según la causal. Usado por CRUZAR_GLOSAS.cmd.

Entradas:
    - El Excel de la EPS (detecta solo las columnas de factura, causal, valor
      y detalle, aunque cambien de nombre o de posición).
    - La carpeta con los XML radicados (AttachedDocument DIAN).

Salidas (junto al Excel de entrada, o donde diga --salida):
    - CRUCE_GLOSAS.xlsx: una fila por glosa con la evidencia del XML
      (NUMERO_CONTRATO, causa de cobertura, validación DIAN) y el borrador.
    - BORRADORES_RESPUESTA.txt: los borradores en texto, listos para pegar.

Los borradores son un PUNTO DE PARTIDA para el auditor: citan la evidencia
real del XML y dejan [COMPLETAR: ...] donde falta criterio humano.

USO:
    py tools\\cruzar_glosas_xml.py GLOSAS.xlsx CARPETA_XML
    py tools\\cruzar_glosas_xml.py GLOSAS.xlsx CARPETA_XML --salida CRUCE.xlsx

Requiere openpyxl. El repo ya lo fija.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

CAMPOS_SALUD = [
    "NUMERO_CONTRATO",
    "NUMERO_POLIZA",
    "FACTURA_SIN_CONTRATO",
    "MODALIDAD_PAGO",
    "COBERTURA_PLAN_BENEFICIOS",
    "CODIGO_PRESTADOR",
]

# Encabezados que reconocemos en el Excel de la EPS (por palabra clave).
_COLS = {
    "factura": ("FACTURA", "FACT", "DOCUMENTO", "NRO", "NUMERO"),
    "causal": ("CAUSAL", "COD", "CONCEPTO", "GLOSA", "MOTIVO", "DEVOL", "OBJEC"),
    "valor": ("VALOR", "VLR", "MONTO"),
    "detalle": ("OBSERV", "DETALL", "DESCRIP", "JUSTIF"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _texto(elem, nombre: str) -> str:
    for e in elem.iter():
        if _local(e.tag) == nombre and e.text and e.text.strip():
            return e.text.strip()
    return ""


def _cdata_con(raiz, marcador: str) -> str | None:
    for e in raiz.iter():
        if _local(e.tag) == "Description" and e.text and marcador in e.text:
            return e.text
    return None


def _parse_xml(texto: str):
    limpio = re.sub(r"^\s*<\?xml[^>]*\?>", "", texto).strip()
    return ET.fromstring(limpio)


def normalizar_factura(valor: str) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.lstrip("0") or digitos


def leer_xml_factura(ruta: Path) -> dict | None:
    """Datos del XML que sirven de evidencia. None si no es una factura."""
    try:
        raiz = ET.parse(str(ruta)).getroot()
    except Exception:
        return None
    datos = {
        "archivo": ruta.name,
        "factura": _texto(raiz, "ParentDocumentID"),
        "eps": _texto(raiz, "RegistrationName"),
        "validacion": _texto(raiz, "ValidationResultCode"),
        "fecha": "",
        "valor": "",
    }
    for c in CAMPOS_SALUD:
        datos[c] = ""
    cdata = _cdata_con(raiz, "<Invoice")
    if not cdata:
        return None
    try:
        inv = _parse_xml(cdata)
    except Exception:
        return None
    if not datos["factura"]:
        datos["factura"] = _texto(inv, "ID")
    datos["fecha"] = _texto(inv, "IssueDate")
    datos["valor"] = _texto(inv, "PayableAmount")
    for ai in inv.iter():
        if _local(ai.tag) != "AdditionalInformation":
            continue
        nombre = valor = ""
        for hijo in ai:
            if _local(hijo.tag) == "Name":
                nombre = (hijo.text or "").strip()
            elif _local(hijo.tag) == "Value":
                valor = (hijo.text or "").strip()
        if nombre in CAMPOS_SALUD:
            datos[nombre] = valor
    return datos


def indexar_xmls(carpeta: Path) -> dict[str, dict]:
    indice = {}
    for x in sorted(carpeta.rglob("*.xml"), key=lambda p: p.name.lower()):
        d = leer_xml_factura(x)
        if d:
            norm = normalizar_factura(d["factura"])
            if norm and norm not in indice:
                indice[norm] = d
    return indice


def _detectar_columnas(ws) -> tuple[int, dict[str, int]] | None:
    """(fila_encabezado, {campo: nro_columna}) buscando en las primeras filas."""
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
            for col, txt in textos.items():
                if col in mapa.values():
                    continue
                if any(k in txt for k in claves):
                    mapa[campo] = col
                    break
        if "factura" in mapa:  # con la factura basta para cruzar
            return fila, mapa
    return None


def cargar_glosas(excel: Path) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(str(excel), read_only=True, data_only=True)
    ws = wb.active
    deteccion = _detectar_columnas(ws)
    if not deteccion:
        wb.close()
        raise ValueError("no encontre una columna de FACTURA en el Excel de glosas")
    fila_enc, mapa = deteccion
    glosas = []
    vacias = 0
    for fila in ws.iter_rows(min_row=fila_enc + 1, values_only=False):
        celdas = {c.column: c.value for c in fila}
        factura = celdas.get(mapa.get("factura"))
        if factura is None or not str(factura).strip():
            vacias += 1
            if vacias > 20:
                break
            continue
        vacias = 0
        glosas.append(
            {
                "factura": str(factura).strip(),
                "causal": str(celdas.get(mapa.get("causal")) or "").strip(),
                "valor": celdas.get(mapa.get("valor")) or "",
                "detalle": str(celdas.get(mapa.get("detalle")) or "").strip(),
            }
        )
    wb.close()
    return glosas


def clasificar_causal(causal: str, detalle: str = "") -> tuple[str, str]:
    """(clave, nombre legible) a partir del código o del texto de la causal."""
    txt = f"{causal} {detalle}".upper()
    prefijo = re.match(r"\s*([A-Z]{2})\d", causal.upper().strip() or "")
    por_codigo = {
        "TA": "tarifas",
        "SO": "soportes",
        "AU": "autorizacion",
        "CO": "cobertura",
        "PE": "pertinencia",
        "CL": "pertinencia",
        "FA": "facturacion",
        "DE": "devolucion",
    }
    clave = por_codigo.get(prefijo.group(1)) if prefijo else None
    if "SIN CONTRATO" in txt or "4401" in txt:
        clave = "contrato"
    elif clave is None:
        for k, palabras in [
            ("contrato", ("CONTRAT",)),
            ("tarifas", ("TARIF",)),
            ("soportes", ("SOPORT",)),
            ("autorizacion", ("AUTORIZ",)),
            ("cobertura", ("COBERT",)),
            ("pertinencia", ("PERTINEN", "CALIDAD")),
            ("devolucion", ("DEVOL",)),
            ("facturacion", ("FACTURAC",)),
        ]:
            if any(p in txt for p in palabras):
                clave = k
                break
    nombres = {
        "contrato": "Sin contrato / devolución",
        "tarifas": "Tarifas",
        "soportes": "Soportes",
        "autorizacion": "Autorización",
        "cobertura": "Cobertura",
        "pertinencia": "Pertinencia / calidad",
        "facturacion": "Facturación",
        "devolucion": "Devolución",
    }
    clave = clave or "general"
    return clave, nombres.get(clave, "General")


def _primera_mayuscula(s: str) -> str:
    """Sube solo la primera letra, sin dañar el resto (códigos, contratos)."""
    return s[:1].upper() + s[1:] if s else s


def borrador_respuesta(glosa: dict, xml: dict | None) -> str:
    """Borrador de respuesta con la evidencia real del XML. Para revisión."""
    clave, _ = clasificar_causal(glosa["causal"], glosa["detalle"])
    f = glosa["factura"]
    partes = [f"Factura {f} — causal {glosa['causal'] or '(sin código)'}:"]

    evidencia = []
    if xml:
        if xml.get("NUMERO_CONTRATO"):
            evidencia.append(f"el XML radicado registra NUMERO_CONTRATO = {xml['NUMERO_CONTRATO']}")
        if xml.get("FACTURA_SIN_CONTRATO"):
            evidencia.append(f"causa de cobertura '{xml['FACTURA_SIN_CONTRATO']}'")
        if xml.get("validacion") == "02":
            evidencia.append("documento validado por la DIAN (código 02)")

    if clave == "contrato":
        partes.append(
            "NO SE ACEPTA. "
            + (_primera_mayuscula("; ".join(evidencia)) + ". " if evidencia else "")
            + "El campo FACTURA_SIN_CONTRATO del estándar registra la causa de cobertura, "
            "no una ausencia de contrato. Tratándose de atención de urgencias, su pago es "
            "obligatorio para la EPS con o sin contrato, conforme a la normativa vigente. "
            "[COMPLETAR: cita normativa avalada por Jurídica]"
        )
    elif clave == "tarifas":
        partes.append(
            "NO SE ACEPTA. Las tarifas facturadas corresponden a las pactadas en el contrato "
            + (f"{xml['NUMERO_CONTRATO']} " if xml and xml.get("NUMERO_CONTRATO") else "")
            + "vigente a la fecha de prestación. [COMPLETAR: anexar folio del tarifario y "
            "los ítems comparados]"
        )
    elif clave == "soportes":
        partes.append(
            "NO SE ACEPTA. Los soportes exigidos por la Resolución 3047/2008 (modificada por "
            "la Res. 2284/2023) fueron radicados con la factura"
            + (" validada por la DIAN" if xml and xml.get("validacion") == "02" else "")
            + ". Se reenvían como anexo. [COMPLETAR: listar los soportes anexos]"
        )
    elif clave == "autorizacion":
        partes.append(
            "NO SE ACEPTA. "
            + (
                f"El servicio corresponde a '{xml['FACTURA_SIN_CONTRATO']}', que no requiere "
                "autorización previa. "
                if xml and xml.get("FACTURA_SIN_CONTRATO")
                else "La atención inicial de urgencias no requiere autorización previa. "
            )
            + "[COMPLETAR: nro de autorización o soporte de la solicitud si aplica]"
        )
    elif clave == "pertinencia":
        partes.append(
            "NO SE ACEPTA. La pertinencia está soportada en la historia clínica y en el "
            "criterio del médico tratante. [COMPLETAR: resumen clínico del caso — requiere "
            "revisión del auditor médico]"
        )
    elif clave == "cobertura":
        partes.append(
            "NO SE ACEPTA. "
            + (
                f"El XML registra cobertura '{xml['COBERTURA_PLAN_BENEFICIOS']}'"
                + (
                    f" y causa '{xml['FACTURA_SIN_CONTRATO']}'"
                    if xml.get("FACTURA_SIN_CONTRATO")
                    else ""
                )
                + ". "
                if xml and xml.get("COBERTURA_PLAN_BENEFICIOS")
                else ""
            )
            + "[COMPLETAR: validar cobertura del plan de beneficios para el servicio glosado]"
        )
    else:
        partes.append(
            "EN REVISIÓN. "
            + (_primera_mayuscula("; ".join(evidencia)) + ". " if evidencia else "")
            + "[COMPLETAR: argumento según el detalle de la causal]"
        )

    if not xml:
        partes.append("OJO: no se encontró el XML de esta factura en la carpeta indicada.")
    return " ".join(partes)


def escribir_salidas(glosas: list[dict], indice: dict[str, dict], salida: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Cruce"
    ws.append(
        [
            "Factura",
            "Causal",
            "Tipo",
            "Valor glosado",
            "Detalle EPS",
            "NUMERO_CONTRATO (XML)",
            "FACTURA_SIN_CONTRATO (XML)",
            "Validación DIAN",
            "XML hallado",
            "Borrador de respuesta (revisar)",
        ]
    )
    azul = PatternFill("solid", fgColor="1F4E79")
    verde = PatternFill("solid", fgColor="E2EFDA")
    amarillo = PatternFill("solid", fgColor="FFF2CC")
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = azul
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    lineas_txt = ["BORRADORES DE RESPUESTA A GLOSAS — para revisión del auditor", "=" * 64, ""]
    for g in glosas:
        xml = indice.get(normalizar_factura(g["factura"]))
        _, tipo = clasificar_causal(g["causal"], g["detalle"])
        borrador = borrador_respuesta(g, xml)
        ws.append(
            [
                g["factura"],
                g["causal"],
                tipo,
                g["valor"],
                g["detalle"],
                (xml or {}).get("NUMERO_CONTRATO", ""),
                (xml or {}).get("FACTURA_SIN_CONTRATO", ""),
                "02 (validado)" if xml and xml.get("validacion") == "02" else "",
                "SI" if xml else "NO",
                borrador,
            ]
        )
        for c in ws[ws.max_row]:
            c.fill = verde if xml else amarillo
        lineas_txt += [borrador, "-" * 64, ""]

    for i, w in enumerate([16, 12, 18, 14, 30, 22, 22, 14, 10, 80], start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    wb.save(str(salida))

    txt = salida.with_name("BORRADORES_RESPUESTA.txt")
    txt.write_text("\r\n".join(lineas_txt), encoding="utf-8")
    return txt


def procesar(excel: Path, carpeta_xml: Path, salida: Path) -> int:
    print("=" * 66)
    print("  CRUZAR GLOSAS — Excel de la EPS contra los XML radicados")
    print("=" * 66)
    glosas = cargar_glosas(excel)
    print(f"  Glosas en el Excel: {len(glosas)}")
    indice = indexar_xmls(carpeta_xml)
    print(f"  XML de factura hallados: {len(indice)}")
    print("-" * 66)

    con_xml = 0
    for g in glosas:
        xml = indice.get(normalizar_factura(g["factura"]))
        if xml:
            con_xml += 1
        _, tipo = clasificar_causal(g["causal"], g["detalle"])
        marca = "✓" if xml else "·"
        print(f"  {marca} {g['factura']:16s} {tipo:22s} {'XML ok' if xml else 'SIN XML'}")

    txt = escribir_salidas(glosas, indice, salida)
    print("-" * 66)
    print(f"  Con evidencia XML: {con_xml} / {len(glosas)}")
    print(f"  Informe: {salida}")
    print(f"  Borradores: {txt}")
    print("=" * 66)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cruza el Excel de glosas de la EPS con los XML radicados."
    )
    parser.add_argument("glosas", help="Excel de glosas que envió la EPS.")
    parser.add_argument("carpeta_xml", help="Carpeta con los XML radicados.")
    parser.add_argument("--salida", type=Path, help="Ruta del Excel de salida.")
    args = parser.parse_args(argv)

    excel = Path(args.glosas).expanduser()
    if not excel.is_file():
        sys.stderr.write(f"ERROR: no existe el Excel de glosas: {excel}\n")
        return 2
    carpeta = Path(args.carpeta_xml).expanduser()
    if not carpeta.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta de XML: {carpeta}\n")
        return 2
    salida = args.salida or (excel.parent / "CRUCE_GLOSAS.xlsx")
    if salida.resolve() == excel.resolve():
        salida = excel.parent / "CRUCE_GLOSAS_2.xlsx"
    try:
        return procesar(excel, carpeta.resolve(), salida)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
