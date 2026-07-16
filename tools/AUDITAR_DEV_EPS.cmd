@echo off
REM ====================================================================
REM  AUDITAR_DEV_EPS.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Audita las devoluciones de Nueva EPS: por cada factura del Excel
REM  cruza el RIPS (JSON) con los soportes de autorizacion (OPF/PDE) y
REM  llena los bloques RIPS-JSON y SOPORTES + la OBSERVACION, mas una
REM  hoja DETALLE con todos los usuarios/servicios.
REM
REM  Pon el Excel de devoluciones (NUEVA_EPS_DEV.xlsx) junto a este .cmd.
REM  Te pide la base de las facturas/JSON (red del HUS) y la base de los
REM  soportes (Y:). El Excel auditado queda como *_AUDITADO.xlsx.
REM
REM  Se instala solo Python, openpyxl y el lector de PDF si faltan.
REM  USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title AUDITAR DEVOLUCIONES EPS - Motor Glosas HUS

echo.
echo ============================================================
echo   AUDITAR DEVOLUCIONES EPS  -  DGH vs RIPS(JSON) vs soportes
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 2) Asegurar openpyxl (Excel) y pymupdf (leer PDF) --------------
%PYEXE% -c "import openpyxl, fitz" >nul 2>&1 && goto motor
echo [i] Instalando componentes (Excel y lector de PDF) por unica vez, espera...
%PYEXE% -m pip install --quiet --user openpyxl pymupdf >nul 2>&1
%PYEXE% -c "import openpyxl" >nul 2>&1 || ( echo [ATENCION] No quedo openpyxl: el Excel puede fallar. )
%PYEXE% -c "import fitz" >nul 2>&1 || ( echo [ATENCION] No quedo el lector de PDF: los soportes saldran vacios. )

:motor
REM --- 3) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0auditar_devoluciones_eps.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\auditar_devoluciones_eps.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%TEMP%\auditar_dev_eps_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:pedir
REM --- 4) Excel de devoluciones (detecta el primero junto al cmd) -----
set "EXCEL="
for /f "delims=" %%F in ('dir /b /a-d "%~dp0*.xlsx" 2^>nul ^| findstr /i "DEV"') do if not defined EXCEL set "EXCEL=%~dp0%%F"
if not defined EXCEL for /f "delims=" %%F in ('dir /b /a-d "%~dp0*.xlsx" 2^>nul ^| findstr /v /i "_AUDITADO"') do if not defined EXCEL set "EXCEL=%~dp0%%F"
echo   Excel de devoluciones (Enter para usar el detectado):
setlocal EnableDelayedExpansion
echo   [!EXCEL!]
endlocal
set /p "EXCEL=  Ruta: "
set "EXCEL=%EXCEL:"=%"
if not defined EXCEL (
  echo [ERROR] No hay Excel de devoluciones junto a este .cmd.
  echo.
  pause
  exit /b 2
)
echo.
REM --- 5) Base de facturas/JSON (red del HUS) -------------------------
set "FBASE=\\172.16.32.83\factura_electronica_net22"
echo   Carpeta de las facturas/JSON (Enter para la ruta de red del HUS):
setlocal EnableDelayedExpansion
echo   [!FBASE!]
endlocal
set /p "FBASE=  Ruta: "
set "FBASE=%FBASE:"=%"
if not defined FBASE set "FBASE=\\172.16.32.83\factura_electronica_net22"
:fbs
if "%FBASE:~-1%"=="\" ( set "FBASE=%FBASE:~0,-1%" & goto fbs )
echo.
REM --- 6) Base de soportes (OPF/PDE) ---------------------------------
set "SBASE=Y:\"
echo   Carpeta de los soportes de autorizacion (Enter para Y:\):
setlocal EnableDelayedExpansion
echo   [!SBASE!]
endlocal
set /p "SBASE=  Ruta: "
set "SBASE=%SBASE:"=%"
if not defined SBASE set "SBASE=Y:\"
echo.

REM --- 7) Ejecutar ---------------------------------------------------
%PYEXE% "%MOTOR%" "%EXCEL%" --facturas-base "%FBASE%" --soportes-base "%SBASE%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Revisa el Excel *_AUDITADO.xlsx junto al original. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
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
echo [ERROR] No se pudo preparar el motor. Copia tambien "auditar_devoluciones_eps.py"
echo         junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  Motor Python embebido (copia de tools\auditar_devoluciones_eps.py).
REM ====================================================================
#PYSTART#
"""auditar_devoluciones_eps.py — Audita las devoluciones de Nueva EPS cruzando,
por cada factura, TRES fuentes: la factura del DGH (soportes), el RIPS (JSON) y
los soportes de autorización (PDF OPF/PDE). Usado por AUDITAR_DEV_EPS.cmd.

Sigue la guía de auditoría del HUS: del Excel de devoluciones toma cada factura
y verifica en el JSON de RIPS el tipo y número de documento del usuario y el
número de autorización, comparándolos con lo que traen los soportes de
autorización. Llena en el Excel los bloques:

    FACTURA DGH          -> TIPO, NUMERO DE DOCUMENTO, NOMBRE, SERVICIO
    RIPS - JSON          -> TIPO, NUMERO DE DOCUMENTO, Nº AUTORIZACION
    SOPORTES AUTORIZACION-> Nº AUTORIZACION, TIPO, NUMERO DE DOCUMENTO
    OBSERVACION          -> hallazgo de la auditoría (diferencias)

El hallazgo típico: en recién nacidos el JSON trae un documento provisional
(RC largo) distinto al de la factura y los soportes -> se marca la diferencia.

De dónde saca los archivos (busca por número de factura, una sola pasada):
    - JSON de RIPS: en la base de facturas (por defecto la ruta de red del
      HUS) como Rips_<FAC>.json dentro de la carpeta de la factura.
    - Soportes OPF/PDE: en la base de soportes (por defecto Y:) como
      OPF_*_<FAC>.pdf y PDE_*_<FAC>.pdf.

USO:
    py tools\\auditar_devoluciones_eps.py NUEVA_EPS_DEV.xlsx
    py tools\\auditar_devoluciones_eps.py DEV.xlsx --facturas-base "\\\\172.16.32.83\\factura_electronica_net22" --soportes-base "Y:\\" --salida DEV_AUDITADO.xlsx

Requiere openpyxl y pymupdf (fitz). El repo ya los fija.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Tipos de documento del sector salud (para reconocer "RC 12345"). Se dejan
# fuera 'DE' (choca con la preposicion) y 'SI' (choca con el "si"): darian
# falsos positivos en texto OCR en mayusculas.
TIPOS_DOC = ("RC", "TI", "CC", "CE", "PA", "MS", "AS", "PE", "CN", "NV", "SC", "PT", "CD")
# Números institucionales que NO son el documento del paciente.
_INSTITUCIONALES = {"900006037", "9000060374", "680010079201", "6800100792"}

_RE_DOC_TIPADO = re.compile(r"\b(" + "|".join(TIPOS_DOC) + r")\b[\s:\-.]{0,3}(\d{5,20})")
_RE_NUM = re.compile(r"\d{5,20}")
# etiquetas cerca de las que un número NO es el documento del paciente
_RE_NO_DOC = re.compile(
    r"(?:TELEFONO|CELULAR|\bTEL\b|\bCEL\b|FAX|VALOR|VIGENCIA|FECHA|RADICAD|NIT)", re.I
)
# contexto que sube/baja la probabilidad de ser el documento del PACIENTE
_CTX_MAS = re.compile(r"(?:PACIENTE|AFILIADO|USUARIO|NI[NÑ]O|BENEFICIARIO|IDENTIFICAC)", re.I)
_CTX_MENOS = re.compile(
    r"(?:MEDIC|PROFESIONAL|TRATANTE|ORDENA|SOLICITAD|PRESTADOR|AUTORIZAD|LIQUIDAD|REVISOR)", re.I
)


def normalizar_factura(valor: str) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.lstrip("0") or digitos


def _patron_factura(norm: str) -> re.Pattern:
    """Reconoce la factura como token 'HUS<num>' (con ceros opcionales),
    sin confundir HUS532392 con HUS5323921 ni concatenar el NIT."""
    return re.compile(rf"HUS0*{re.escape(norm)}(?![0-9])", re.I)


def _texto_pdf(ruta: Path) -> str:
    try:
        import fitz
    except ImportError:
        return ""
    try:
        doc = fitz.open(str(ruta))
    except Exception:
        return ""
    partes = []
    try:
        for pg in doc:
            try:
                partes.append(pg.get_text())
            except Exception:
                continue  # página dañada/cifrada: se omite, no revienta
    finally:
        doc.close()
    return "\n".join(partes)


# --------------------------------------------------------------------------
#  RIPS - JSON
# --------------------------------------------------------------------------

_SERVICIOS_JSON = (
    "consultas",
    "procedimientos",
    "medicamentos",
    "urgencias",
    "hospitalizacion",
    "recienNacidos",
    "otrosServicios",
)


def leer_rips(ruta: Path) -> dict:
    """Devuelve {factura, usuarios:[{tipo,doc,servicios:[...]}], error}."""
    datos = {"factura": "", "usuarios": [], "error": ""}
    try:
        crudo = ruta.read_bytes()
    except OSError as exc:
        datos["error"] = f"no se pudo leer el JSON ({type(exc).__name__})"
        return datos
    texto = None
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = crudo.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        datos["error"] = "JSON con codificacion no reconocida"
        return datos
    try:
        raw = json.loads(texto)
    except Exception as exc:
        datos["error"] = f"JSON ilegible ({type(exc).__name__})"
        return datos
    try:
        if not isinstance(raw, dict):
            datos["error"] = "JSON con estructura inesperada (no es un objeto)"
            return datos
        datos["factura"] = str(raw.get("numFactura") or "")
        for u in raw.get("usuarios") or []:
            if not isinstance(u, dict):
                continue
            usuario = {
                "tipo": str(u.get("tipoDocumentoIdentificacion") or "").strip().upper(),
                "doc": str(u.get("numDocumentoIdentificacion") or "").strip(),
                "servicios": [],
            }
            servicios = u.get("servicios") or {}
            if isinstance(servicios, dict):
                for clave in _SERVICIOS_JSON:
                    for s in servicios.get(clave) or []:
                        if not isinstance(s, dict):
                            continue
                        usuario["servicios"].append(
                            {
                                "grupo": clave,
                                "autoriz": str(s.get("numAutorizacion") or "").strip(),
                                "cod": str(
                                    s.get("codProcedimiento")
                                    or s.get("codConsulta")
                                    or s.get("codTecnologiaSalud")
                                    or ""
                                ).strip(),
                                "codServicio": str(s.get("codServicio") or "").strip(),
                                "valor": s.get("vrServicio") or s.get("vrServicios") or "",
                                "dx": str(s.get("codDiagnosticoPrincipal") or "").strip(),
                            }
                        )
            datos["usuarios"].append(usuario)
    except Exception as exc:
        datos["error"] = f"JSON con estructura inesperada ({type(exc).__name__})"
    return datos


def autorizaciones_del_json(rips: dict) -> list[str]:
    """Todas las autorizaciones del JSON (sin vacías, sin repetir, en orden)."""
    vistas, out = set(), []
    for u in rips["usuarios"]:
        for s in u["servicios"]:
            a = s["autoriz"]
            if a and a not in vistas:
                vistas.add(a)
                out.append(a)
    return out


# --------------------------------------------------------------------------
#  Soportes de autorización (PDF)
# --------------------------------------------------------------------------


def extraer_autorizacion(texto: str, esperadas: list[str] | None = None) -> str:
    """Nº de autorización del soporte. Si alguna del JSON aparece cerca de la
    etiqueta o como token aislado, se prefiere esa."""
    esperadas = esperadas or []
    for esp in esperadas:
        # aparece pegada a "autoriza..." (hasta 40 chars, incluye salto de linea)
        if re.search(r"autoriza\w*[\s\S]{0,40}?(?<!\d)" + re.escape(esp) + r"(?!\d)", texto, re.I):
            return esp
        # o como token realmente aislado (rodeado de espacios/parentesis, no dentro de fecha 2024-88123-01)
        if re.search(r"(?:^|[\s(])" + re.escape(esp) + r"(?:[\s).]|$)", texto):
            return esp
    # sin esperada util: el PRIMER numero de 5+ digitos tras "autoriza" (el mas
    # cercano; evita radicados/fechas que vienen despues), cruzando saltos de
    # linea y saltando rellenos como "No", ":", "(POS) 5251-".
    for m in re.finditer(r"autoriza\w*[\s\S]{0,25}?(\d{5,20})", texto, re.I):
        if m.group(1) not in _INSTITUCIONALES:
            return m.group(1)
    return ""


def extraer_documento(texto: str) -> tuple[str, str]:
    """(tipo, numero) del PACIENTE en el soporte. Puntúa por contexto para no
    tomar el documento del médico, teléfonos, valores ni fechas."""
    candidatos = []
    for m in _RE_DOC_TIPADO.finditer(texto):
        tipo, num = m.group(1).upper(), m.group(2)
        if num in _INSTITUCIONALES:
            continue
        # el tipo (RC/CC/...) ya distingue un documento de un telefono/valor;
        # se puntua por lo que PRECEDE al documento (ahi va la etiqueta).
        ventana_prev = texto[max(0, m.start() - 25) : m.start()]
        score = 0
        if _CTX_MAS.search(ventana_prev):
            score += 2
        if _CTX_MENOS.search(ventana_prev):
            score -= 2
        candidatos.append((score, tipo, num))
    if candidatos:
        # el documento del paciente: mejor contexto; a igualdad, el mas repetido
        frec = Counter((t, n) for _, t, n in candidatos)
        mejor = max(candidatos, key=lambda c: (c[0], frec[(c[1], c[2])]))
        return mejor[1], mejor[2]
    # sin tipo explícito: tras "IDENTIFICACION"/"Historia clinica", evitando telefonos
    for m in re.finditer(
        r"(?:IDENTIFICACION|Historia\s+clinica)\b([\s\S]{0,40}?)(\d{5,20})", texto, re.I
    ):
        entre = m.group(1)
        if _RE_NO_DOC.search(entre):
            continue
        if m.group(2) not in _INSTITUCIONALES:
            return "", m.group(2)
    return "", ""


_STOP_NOMBRE = re.compile(
    r"\b(?:NUMERO|IDENTIFIC|CODIGO|EPS|EDAD|FECHA|DIRECCION|TIPO|HISTORIA|LIQUIDADOR|"
    r"REVISOR|AUXILIAR|INSTITUCION|INGRESO|NIT|NOMBRE|No|VALOR|AFILIADO|OrIGEN|DX)\b",
    re.I,
)


def _limpiar_nombre(bruto: str) -> str:
    nombre = re.sub(r"\s+", " ", bruto).strip()
    nombre = _STOP_NOMBRE.split(nombre)[0]
    tokens = [t for t in re.split(r"[\s/]+", nombre) if t]
    while tokens and len(re.sub(r"[^A-Za-zÁÉÍÓÚÑ]", "", tokens[-1])) <= 2:
        tokens.pop()
    limpio = " ".join(tokens).strip(" .,-/")
    return limpio if len(limpio.split()) >= 2 else ""


def extraer_nombre(texto: str) -> str:
    """Nombre del paciente en el soporte (varios formatos, sin cruzar líneas)."""
    patrones = (
        r"Nombre\s+del\s+usuario[:\s]+([^\n]{6,60})",
        r"Identificaci[oó]n\s+del\s+Ni[nñ]o[:\s]+([^\n]{6,60})",
        r"NOMBRES\s*\n\s*([^\n]{4,40})\s*\n\s*APELLIDOS\s*\n\s*([^\n]{4,40})",
        r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{6,55})[^\n]{0,4}\n\s*NUMERO DE IDENTIFICACION",
    )
    for pat in patrones:
        m = re.search(pat, texto)
        if not m:
            continue
        bruto = " ".join(g for g in m.groups() if g) if m.re.groups > 1 else m.group(1)
        nombre = _limpiar_nombre(bruto)
        if nombre:
            return nombre
    return ""


def extraer_servicio(texto: str) -> str:
    """Descripción del servicio/programa autorizado."""
    for pat in (
        r"PAQUETE\s+MENSUAL[^\n]{0,60}",
        r"PROGRAMA\s+MADRE\s+CANGURO[^\n]{0,30}",
        r"Descripci[oó]n\s+Servicio\s*\n(?:[^\n]*\n){0,2}?\s*([A-ZÁÉÍÓÚÑ][^\n]{6,60})",
    ):
        m = re.search(pat, texto, re.I)
        if m:
            frag = m.group(1) if m.groups() else m.group(0)
            frag = re.sub(r"\s+", " ", frag).strip(" .:-")
            frag = re.sub(r"[^A-Za-zÁÉÍÓÚÑñáéíóú0-9 ]+.*$", "", frag).strip()
            if len(frag) >= 4:
                return frag.upper()
    return ""


def leer_soportes(pdfs: list[Path], autoriz_json: list[str]) -> dict:
    """Combina el texto de los soportes (OPF/PDE) y extrae los campos clave."""
    res = {
        "autoriz": "",
        "tipo": "",
        "doc": "",
        "nombre": "",
        "servicio": "",
        "archivos": [],
        "sin_texto": False,
    }
    textos = []
    for p in pdfs:
        t = _texto_pdf(p)
        res["archivos"].append(p.name)
        if t.strip():
            textos.append(t)
    if not textos:
        res["sin_texto"] = bool(pdfs)  # había PDF pero sin texto (¿escaneado?)
        return res
    texto = "\n".join(textos)
    res["autoriz"] = extraer_autorizacion(texto, autoriz_json)
    res["tipo"], res["doc"] = extraer_documento(texto)
    res["nombre"] = extraer_nombre(texto)
    res["servicio"] = extraer_servicio(texto)
    return res


# --------------------------------------------------------------------------
#  Índice de archivos (una sola pasada por cada base, tolerante a fallos)
# --------------------------------------------------------------------------


def indexar(base: Path, facturas_norm: set[str]) -> dict[str, dict]:
    """Recorre `base` una vez y agrupa por factura los archivos de interés.

    Empareja por el token 'HUS<num>' del NOMBRE del archivo; si el archivo no
    trae factura en el nombre (p. ej. la factura fv), usa la carpeta. Así no
    confunde HUS532392 con HUS5323921, no concatena el NIT, y no roba archivos
    de otra factura que estén en una carpeta mal rotulada."""
    indice = {
        n: {"json": None, "fv": None, "opf": [], "pde": [], "otros": []} for n in facturas_norm
    }
    patrones = {n: _patron_factura(n) for n in facturas_norm}
    if not base:
        return indice
    try:
        es_dir = base.is_dir()
    except OSError:
        es_dir = False
    if not es_dir:
        return indice

    for root, _dirs, files in os.walk(str(base), onerror=lambda _e: None):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in (".json", ".pdf"):
                continue
            objetivo = next((n for n, pat in patrones.items() if pat.search(fn)), None)
            if objetivo is None and "HUS" not in fn.upper():
                # archivo sin factura en el nombre (fv...): usar la carpeta
                objetivo = next((n for n, pat in patrones.items() if pat.search(root)), None)
            if objetivo is None:
                continue
            p = Path(root) / fn
            up = fn.upper()
            slot = indice[objetivo]
            if ext == ".json" and "RIPS" in up:
                slot["json"] = slot["json"] or p
            elif ext == ".pdf" and up.startswith("OPF"):
                slot["opf"].append(p)
            elif ext == ".pdf" and up.startswith("PDE"):
                slot["pde"].append(p)
            elif ext == ".pdf" and up.startswith("FV"):
                slot["fv"] = slot["fv"] or p
            elif ext == ".pdf":
                slot["otros"].append(p)
    return indice


# --------------------------------------------------------------------------
#  Comparación y observación
# --------------------------------------------------------------------------


def observacion(rips_doc: str, autoriz_json: list[str], sop: dict) -> str:
    """Compara el documento y la autorización del JSON contra el soporte."""
    partes = []
    sop_aut = sop.get("autoriz", "")
    sop_doc = sop.get("doc", "")
    set_json = {normalizar_factura(a) for a in autoriz_json}

    # --- autorización ---
    if not autoriz_json and not sop_aut:
        partes.append("SIN AUTORIZACION EN JSON NI SOPORTE")
    elif not autoriz_json:
        partes.append("SIN AUTORIZACION EN EL JSON")
    elif not sop_aut:
        if sop.get("sin_texto"):
            partes.append("SOPORTE SIN TEXTO (revisar/OCR)")
        else:
            partes.append("SIN AUTORIZACION EN EL SOPORTE")
    elif normalizar_factura(sop_aut) in set_json:
        partes.append("OK")
    else:
        muestra = ", ".join(autoriz_json[:2])
        partes.append(f"AUTORIZACION DIFERENTE (JSON {muestra} vs SOPORTE {sop_aut})")

    # --- documento del paciente: JSON (RIPS) vs soporte (= FACTURA DGH) ---
    if not rips_doc:
        partes.append("SIN USUARIO EN EL JSON")
    elif not sop_doc:
        if sop.get("sin_texto"):
            pass  # ya avisado arriba
        else:
            partes.append("SIN DOCUMENTO EN EL SOPORTE (no verificado)")
    elif normalizar_factura(rips_doc) != normalizar_factura(sop_doc):
        partes.append("DIFERENCIA DEL NUMERO DE DOCUMENTO DGH VS JSON")

    return " - ".join(partes) if partes else "REVISAR"


# --------------------------------------------------------------------------
#  Excel
# --------------------------------------------------------------------------


def _detectar_cabecera(ws) -> int | None:
    for fila in range(1, 8):
        vals = [
            str(ws.cell(fila, c).value or "").strip().upper() for c in range(1, ws.max_column + 1)
        ]
        if "FACTURA" in vals and "FAC" in vals:
            return fila
    return None


def _es_factura(valor) -> bool:
    """La celda FAC parece una factura (no una fila de TOTAL/subtotal)."""
    s = str(valor or "").strip()
    if not s:
        return False
    if not re.search(r"\d", s):
        return False
    if re.search(r"TOTAL|SUBTOTAL|SUMA|GENERAL", s, re.I):
        return False
    return True


def procesar(excel: Path, facturas_base: Path, soportes_base: Path, salida: Path) -> int:
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill

    try:
        wb = load_workbook(str(excel))
    except Exception as exc:
        sys.stderr.write(
            f"ERROR: no se pudo abrir el Excel ({type(exc).__name__}). ¿Está abierto?\n"
        )
        return 2
    ws = wb.active
    fila_cab = _detectar_cabecera(ws)
    if fila_cab is None:
        sys.stderr.write("ERROR: no encontre la cabecera (FACTURA / FAC) en el Excel.\n")
        return 2
    COL = {
        "fac": 2,
        "fecha": 4,
        "dgh_tipo": 7,
        "dgh_doc": 8,
        "dgh_nombre": 9,
        "dgh_serv": 10,
        "js_tipo": 11,
        "js_doc": 12,
        "js_aut": 13,
        "sop_aut": 14,
        "sop_tipo": 15,
        "sop_doc": 16,
        "obs": 17,
    }

    facturas = []
    for fila in range(fila_cab + 1, ws.max_row + 1):
        fac = ws.cell(fila, COL["fac"]).value
        if _es_factura(fac):
            facturas.append((fila, str(fac).strip()))

    print("=" * 66)
    print("  AUDITAR DEVOLUCIONES EPS — DGH vs RIPS(JSON) vs soportes")
    print("=" * 66)
    print(f"  Excel: {excel.name}   Facturas: {len(facturas)}")
    print(f"  Base facturas/JSON: {facturas_base}")
    print(f"  Base soportes:      {soportes_base}")
    print("  Indexando archivos (una pasada por cada base)...")

    norms = {normalizar_factura(fac) for _, fac in facturas}
    idx_fact = indexar(facturas_base, norms)
    idx_sop = indexar(soportes_base, norms)
    print("-" * 66)

    verde = PatternFill("solid", fgColor="E2EFDA")
    amarillo = PatternFill("solid", fgColor="FFF2CC")
    rojo = PatternFill("solid", fgColor="F8CBAD")

    detalle = [
        [
            "Factura",
            "Usuario #",
            "Grupo servicio",
            "JSON tipo",
            "JSON documento",
            "Nº autorizacion JSON",
            "Cod servicio",
            "Cod procedimiento",
            "Valor",
            "Diagnostico",
        ]
    ]
    con_dif = con_ok = sin_datos = 0

    for fila, fac in facturas:
        norm = normalizar_factura(fac)
        arch_f = idx_fact.get(norm, {})
        arch_s = idx_sop.get(norm, {})
        pdfs = (
            (arch_s.get("opf") or [])
            + (arch_s.get("pde") or [])
            + (arch_f.get("opf") or [])
            + (arch_f.get("pde") or [])
        )

        rips = (
            leer_rips(arch_f["json"])
            if arch_f.get("json")
            else {"factura": "", "usuarios": [], "error": "sin JSON"}
        )
        autoriz_json = autorizaciones_del_json(rips)
        primer = (
            rips["usuarios"][0] if rips["usuarios"] else {"tipo": "", "doc": "", "servicios": []}
        )
        sop = leer_soportes(pdfs, autoriz_json)

        ws.cell(fila, COL["dgh_tipo"]).value = sop["tipo"]
        ws.cell(fila, COL["dgh_doc"]).value = sop["doc"]
        ws.cell(fila, COL["dgh_nombre"]).value = sop["nombre"]
        ws.cell(fila, COL["dgh_serv"]).value = sop["servicio"]
        ws.cell(fila, COL["js_tipo"]).value = primer["tipo"]
        ws.cell(fila, COL["js_doc"]).value = primer["doc"]
        ws.cell(fila, COL["js_aut"]).value = ", ".join(autoriz_json)
        ws.cell(fila, COL["sop_aut"]).value = sop["autoriz"]
        ws.cell(fila, COL["sop_tipo"]).value = sop["tipo"]
        ws.cell(fila, COL["sop_doc"]).value = sop["doc"]

        if rips.get("error") and not pdfs:
            obs = "SIN JSON NI SOPORTES (revisar ruta)"
            sin_datos += 1
            pintura = amarillo
        else:
            obs = observacion(primer["doc"], autoriz_json, sop)
            if "DIFERENCIA" in obs or "DIFERENTE" in obs:
                con_dif += 1
                pintura = rojo
            elif obs == "OK":
                con_ok += 1
                pintura = verde
            else:
                sin_datos += 1
                pintura = amarillo
        n_serv = sum(len(u["servicios"]) for u in rips["usuarios"])
        if len(rips["usuarios"]) > 1 or n_serv > 1:
            obs += f"  (+{len(rips['usuarios'])} usuario(s)/{n_serv} servicio(s): ver hoja DETALLE)"
        ws.cell(fila, COL["obs"]).value = obs
        ws.cell(fila, COL["obs"]).fill = pintura

        for iu, u in enumerate(rips["usuarios"], 1):
            if not u["servicios"]:
                detalle.append([fac, iu, "", u["tipo"], u["doc"], "", "", "", "", ""])
            for s in u["servicios"]:
                detalle.append(
                    [
                        fac,
                        iu,
                        s["grupo"],
                        u["tipo"],
                        u["doc"],
                        s["autoriz"],
                        s["codServicio"],
                        s["cod"],
                        s["valor"],
                        s["dx"],
                    ]
                )

        marca = "!" if pintura is rojo else ("·" if pintura is amarillo else "OK")
        print(
            f"  {marca:2s} {fac:16s} JSON doc={primer['doc'] or '-':16s} sop doc={sop['doc'] or '-':12s} aut={', '.join(autoriz_json) or '-'}"
        )

    if "DETALLE" in wb.sheetnames:
        del wb["DETALLE"]
    ws2 = wb.create_sheet("DETALLE")
    for r in detalle:
        ws2.append(r)
    azul = PatternFill("solid", fgColor="1F4E79")
    for c in ws2[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = azul
    ws2.freeze_panes = "A2"

    try:
        wb.save(str(salida))
    except PermissionError:
        sys.stderr.write(
            f"\nERROR: no se pudo guardar {salida.name} (¿lo tienes abierto en Excel?).\n"
            "       Cierralo y vuelve a correr el bot.\n"
        )
        return 2
    except OSError as exc:
        sys.stderr.write(f"\nERROR: no se pudo guardar el Excel ({type(exc).__name__}).\n")
        return 2

    print("-" * 66)
    print(f"  Con diferencia: {con_dif}   OK: {con_ok}   Sin datos/revisar: {sin_datos}")
    print(f"  Informe: {salida}")
    print("=" * 66)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita devoluciones EPS: DGH vs RIPS(JSON) vs soportes."
    )
    parser.add_argument("excel", help="Excel de devoluciones (NUEVA_EPS_DEV.xlsx).")
    parser.add_argument(
        "--facturas-base",
        default=r"\\172.16.32.83\factura_electronica_net22",
        help="Carpeta raíz de las facturas/JSON (red del HUS).",
    )
    parser.add_argument(
        "--soportes-base", default="Y:\\", help="Carpeta raíz de los soportes de autorización."
    )
    parser.add_argument("--salida", type=Path, help="Ruta del Excel auditado.")
    args = parser.parse_args(argv)

    excel = Path(args.excel).expanduser()
    if not excel.is_file():
        sys.stderr.write(f"ERROR: no existe el Excel: {excel}\n")
        return 2
    salida = args.salida or excel.with_name(excel.stem + "_AUDITADO.xlsx")
    return procesar(excel, Path(args.facturas_base), Path(args.soportes_base), salida)


if __name__ == "__main__":
    raise SystemExit(main())
