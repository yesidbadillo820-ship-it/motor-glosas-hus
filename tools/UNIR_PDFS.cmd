@echo off
REM ====================================================================
REM  UNIR_PDFS.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Une (combina) todos los PDF de cada carpeta en un unico PDF
REM  consolidado (_UNIDO_<carpeta>.pdf) y deja ademas una copia identica
REM  con extension .cmd (_UNIDO_<carpeta>.cmd) lista para subir donde
REM  pidan ese formato.  Trabaja sobre la carpeta donde este ubicado
REM  este archivo y todas sus subcarpetas.
REM
REM  El consolidado se comprime automaticamente cuando hay margen (los
REM  escaneos a color/grises de alta resolucion bajan mucho de peso).
REM  Si un PDF ya esta en su minimo (escaneos B/N tipo fax) se deja tal
REM  cual: la compresion NUNCA agranda un archivo ni pierde paginas.
REM
REM  OJO: los _UNIDO_*.cmd generados NO son programas - son el mismo PDF
REM  con otra extension. No hay que darles doble clic; para verlos como
REM  documento se renombran de vuelta a .pdf.
REM
REM  USO:  copia este archivo a la carpeta que tiene tus PDF y dale
REM        doble clic.  Nada mas.
REM
REM  Es autocontenido: lleva el motor Python adentro. Si el equipo no
REM  tiene Python, el bot lo INSTALA SOLO (via winget o descargando el
REM  instalador oficial de python.org, sin pedir administrador). Solo
REM  necesita internet la primera vez. Si las politicas del equipo lo
REM  impiden, muestra las instrucciones para instalarlo a mano.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title UNIR PDFS - Motor Glosas HUS

REM Carpeta donde vive este .cmd (sin la barra final, para no romper el "").
set "RAIZ=%~dp0"
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ:~0,-1%"

echo.
echo ============================================================
echo   UNIR PDFS  -  une los PDF de cada carpeta en un solo PDF
echo ============================================================
echo   Carpeta de trabajo:
echo   "%RAIZ%"
echo.

REM --- 1) Buscar Python en el equipo ----------------------------------
REM  Se valida EJECUTANDO cada candidato (no con "where"): en Windows
REM  10/11 sin Python, "where python" encuentra el alias falso de la
REM  Microsoft Store y el bot moriria con codigo 9009 en vez de mostrar
REM  las instrucciones de instalacion.
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 2) Asegurar el componente PDF (PyPDF2 / pypdf) -----------------
%PYEXE% -c "import PyPDF2" >nul 2>&1 && goto haspdf
%PYEXE% -c "import pypdf"  >nul 2>&1 && goto haspdf
echo [i] Instalando el componente PDF (PyPDF2) por unica vez, espera...
%PYEXE% -m pip install --quiet --user PyPDF2 >nul 2>&1
:haspdf

REM --- 2b) Asegurar el compresor de PDF (pymupdf) ----------------------
REM  Opcional: si no se puede instalar, el motor sigue sin comprimir y
REM  los archivos salen igual de validos, solo mas pesados.
%PYEXE% -c "import fitz" >nul 2>&1 && goto hascomp
echo [i] Instalando el compresor de PDF pymupdf por unica vez, espera...
%PYEXE% -m pip install --quiet --user pymupdf >nul 2>&1
:hascomp

REM --- 3) Localizar el motor Python -----------------------------------
REM  Preferimos el .py al lado (o en tools\); si el .cmd viaja solo,
REM  extraemos la copia embebida que va despues del marcador.
set "MOTOR=%~dp0unir_pdfs_carpetas.py"
if exist "%MOTOR%" goto run
set "MOTOR=%~dp0tools\unir_pdfs_carpetas.py"
if exist "%MOTOR%" goto run
set "MOTOR=%TEMP%\unir_pdfs_carpetas_hus.py"
set "ORIGENCMD=%~f0"
REM  Borrar cualquier motor viejo cacheado: si la extraccion fallara, NO
REM  se debe ejecutar en silencio una version anterior desde %TEMP%.
del "%MOTOR%" >nul 2>&1
REM  Las rutas viajan por variables de entorno ($env:...) y no interpoladas
REM  en el comando: asi un apostrofe o comilla en la ruta no rompe PowerShell.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:run
REM --- 4) Ejecutar la union -------------------------------------------
%PYEXE% "%MOTOR%" "%RAIZ%" --tambien-cmd --comprimir %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. En cada carpeta quedo _UNIDO_*.pdf y su copia _UNIDO_*.cmd para subir. & echo      OJO: a los _UNIDO_*.cmd NO les des doble clic - son el PDF con otra extension. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
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
echo   (Tambien sirve instalar "Python" desde la Microsoft Store, o
echo    pedirselo al area de SISTEMAS.)
echo.
pause
exit /b 1

:sinmotor
echo [ERROR] No se pudo preparar el motor de union.
echo         Copia tambien "unir_pdfs_carpetas.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python
REM  (copia embebida de tools\unir_pdfs_carpetas.py, salvo el fin de
REM  linea). cmd.exe NUNCA llega aqui: el script termina con "exit /b"
REM  mas arriba. Esta copia solo se usa si el .cmd viaja solo, sin el
REM  .py al lado.
REM ====================================================================
#PYSTART#
"""unir_pdfs_carpetas.py — Une (combina) todos los PDF de cada carpeta en uno solo.

Pensado para consolidar los soportes de glosas/notas de crédito: cada carpeta
(por factura / NE) suele tener varios PDF sueltos (factura, epicrisis, notas,
autorizaciones…). Este script recorre una carpeta raíz y, para CADA carpeta que
contenga varios PDF, los une en un único PDF consolidado llamado
`_UNIDO_<nombre-de-la-carpeta>.pdf` dentro de esa misma carpeta.

Con `--tambien-cmd` deja además una copia idéntica con extensión `.cmd`
(`_UNIDO_<carpeta>.cmd`): mismo contenido PDF, solo cambia la extensión. Es lo
que exige el flujo de auditoría para subir el consolidado donde piden ".cmd".
Esa copia NO es ejecutable ni hay que darle doble clic — para verla como
documento, se renombra de vuelta a `.pdf`.

Si una carpeta ya tiene su copia `_UNIDO_*.cmd` de una corrida previa, se
refresca SIEMPRE al regenerar el consolidado, aunque no se pase
`--tambien-cmd`: el .cmd es lo que se sube al portal y no puede quedar
divergente del .pdf.

Con `--comprimir` (requiere pymupdf) el consolidado se recomprime antes de
sacar la copia .cmd: los escaneos con resolución alta se bajan a 150 dpi
(de sobra para leer e imprimir) y se re-encoda como JPEG calidad 80. Solo se
reemplaza si de verdad queda más liviano y conserva todas las páginas; ante
cualquier fallo se mantiene el original tal cual.

Es idempotente: en cada corrida vuelve a generar los `_UNIDO_*.pdf` y NUNCA los
toma como entrada (se excluyen por el prefijo), así que puedes correrlo las veces
que quieras sin que se aniden.

Orden de las páginas: los PDF de cada carpeta se ordenan por nombre de archivo
de forma "natural" (2 antes que 10). Si necesitas un orden exacto, antepón un
número al nombre: `01_factura.pdf`, `02_epicrisis.pdf`, `03_autorizacion.pdf`.

USO:
    py tools\\unir_pdfs_carpetas.py "D:\\USUARIO CARTERA\\Documents\\SOPORTES"
    py tools\\unir_pdfs_carpetas.py .                      # carpeta actual
    py tools\\unir_pdfs_carpetas.py . --simulacro          # solo mostrar, sin escribir
    py tools\\unir_pdfs_carpetas.py . --minimo 1           # unir aunque haya 1 solo PDF
    py tools\\unir_pdfs_carpetas.py . --sin-recursion      # solo la carpeta raíz
    py tools\\unir_pdfs_carpetas.py . --tambien-cmd        # dejar copia .cmd del consolidado
    py tools\\unir_pdfs_carpetas.py . --comprimir          # reducir el peso del consolidado

Normalmente NO se ejecuta a mano: el archivo `UNIR_PDFS.cmd` lo lanza con doble
clic sobre la carpeta donde esté ubicado.

Requiere PyPDF2 (o pypdf). El repo ya fija PyPDF2==3.0.1.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys
from pathlib import Path


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
        sys.exit(2)


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def listar_pdfs(carpeta: Path, prefijo: str) -> list[Path]:
    """PDF sueltos en `carpeta` (no recursivo), excluyendo los ya unidos."""
    pref = prefijo.upper()
    pdfs = []
    for entrada in os.scandir(carpeta):
        if not entrada.is_file():
            continue
        nombre = entrada.name
        if not nombre.lower().endswith(".pdf"):
            continue
        if nombre.upper().startswith(pref):
            continue  # es un _UNIDO_ de una corrida previa
        pdfs.append(Path(entrada.path))
    return sorted(pdfs, key=lambda p: clave_natural(p.name))


def unir_pdfs(pdfs: list[Path], destino: Path, PdfReader, PdfWriter) -> tuple[int, list[str]]:
    """Une `pdfs` en `destino`. Devuelve (n_paginas, [archivos_omitidos])."""
    escritor = PdfWriter()
    paginas = 0
    omitidos: list[str] = []
    for pdf in pdfs:
        try:
            lector = PdfReader(str(pdf))
            if lector.is_encrypted:
                # PDFs "protegidos" sin contraseña real: se intenta abrir vacío.
                with contextlib.suppress(Exception):
                    lector.decrypt("")
            n = 0
            for pagina in lector.pages:
                escritor.add_page(pagina)
                n += 1
            if n == 0:
                omitidos.append(f"{pdf.name} (sin páginas legibles)")
            else:
                paginas += n
        except Exception as exc:  # PDF dañado/ilegible: se omite y se sigue
            omitidos.append(f"{pdf.name} ({type(exc).__name__})")
    if paginas == 0:
        return 0, omitidos
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        escritor.write(fh)
    os.replace(tmp, destino)  # escritura atómica: no deja PDFs a medias
    return paginas, omitidos


def copiar_como(origen: Path, destino: Path) -> None:
    """Copia byte a byte con escritura atómica (mismo patrón que unir_pdfs)."""
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        shutil.copyfile(origen, tmp)
        os.replace(tmp, destino)
    except Exception:
        # No dejar el .tmp huérfano (p. ej. destino solo-lectura o bloqueado
        # por antivirus/portal en Windows).
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


def comprimir_pdf(destino: Path, dpi: int = 150, calidad: int = 80) -> tuple[int, int] | None:
    """Reduce el peso del PDF consolidado sin perder páginas ni legibilidad.

    Recomprime los escaneos: las imágenes con resolución mayor al umbral se
    bajan a `dpi` (150 es de sobra para leer e imprimir un contrato) y todo se
    re-encoda como JPEG calidad `calidad`. Además limpia objetos basura y
    duplicados que quedan al unir varios PDF.

    Red de seguridad: el archivo SOLO se reemplaza si el resultado abre bien,
    conserva el mismo número de páginas y pesa menos. Ante cualquier duda se
    conserva el original intacto. Devuelve (bytes_antes, bytes_despues) si
    comprimió, o None si no hubo ganancia / falta pymupdf / algo falló.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return None
    antes = destino.stat().st_size
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        with fitz.open(str(destino)) as doc:
            paginas = doc.page_count
            if hasattr(doc, "rewrite_images"):  # pymupdf >= 1.24.10
                doc.rewrite_images(
                    dpi_threshold=int(dpi * 4 / 3),
                    dpi_target=dpi,
                    quality=calidad,
                    set_to_gray=False,
                )
            doc.save(str(tmp), garbage=4, deflate=True, clean=True)
        with fitz.open(str(tmp)) as chk:  # el comprimido debe abrir y estar completo
            if chk.page_count != paginas:
                raise ValueError("el comprimido no conserva las páginas")
        despues = tmp.stat().st_size
        if despues >= antes:
            tmp.unlink()
            return None
        os.replace(tmp, destino)
        return antes, despues
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        return None


def procesar(
    raiz: Path,
    prefijo: str,
    minimo: int,
    recursivo: bool,
    simulacro: bool,
    tambien_cmd: bool,
    comprimir: bool,
) -> int:
    PdfReader, PdfWriter = _cargar_lector_escritor()

    if comprimir and not simulacro:
        try:
            import fitz  # noqa: F401  (pymupdf)
        except ImportError:
            comprimir = False
            print("AVISO: compresión no disponible (falta pymupdf).")
            print("       Instálala con:  py -m pip install pymupdf")
            print("       Se continúa sin comprimir; los archivos salen igual de válidos.")

    carpetas = [Path(dp) for dp, _dn, _fn in os.walk(raiz)] if recursivo else [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    generados = 0
    total_paginas = 0
    saltadas = 0
    copias_cmd = 0
    ahorrado = 0
    con_error: list[str] = []

    print("=" * 64)
    print("  UNIR PDFS — un PDF consolidado por carpeta")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | mínimo {minimo} PDF por carpeta"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    for carpeta in carpetas:
        pdfs = listar_pdfs(carpeta, prefijo)
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        if len(pdfs) < minimo:
            if pdfs:  # había algo pero no alcanza el mínimo
                saltadas += 1
                print(f"  ·  {rel}: {len(pdfs)} PDF (menos de {minimo}, se omite)")
            continue

        base = carpeta.name or "SALIDA"
        destino = carpeta / f"{prefijo}{base}.pdf"

        destino_cmd = destino.with_suffix(".cmd")
        # Si ya existe una copia .cmd de una corrida previa, se refresca SIEMPRE
        # (aunque no venga --tambien-cmd): el .cmd es lo que se sube al portal y
        # no puede quedar divergente del .pdf recién regenerado.
        escribir_cmd = tambien_cmd or destino_cmd.exists()

        if simulacro:
            extra = f"  (+ {destino_cmd.name})" if escribir_cmd else ""
            print(f"  →  {rel}: uniría {len(pdfs)} PDF  →  {destino.name}{extra}")
            generados += 1
            continue

        paginas, omitidos = unir_pdfs(pdfs, destino, PdfReader, PdfWriter)
        if paginas == 0:
            print(f"  ✗  {rel}: no se pudo leer ningún PDF, se omite")
            con_error.append(str(carpeta))
            continue
        generados += 1
        total_paginas += paginas
        detalle = f"({len(pdfs)} PDF, {paginas} págs.)"
        if comprimir:
            resultado = comprimir_pdf(destino)
            if resultado:
                antes, despues = resultado
                ahorrado += antes - despues
                detalle += f"  comprimido {_mb(antes)} → {_mb(despues)}"
        if escribir_cmd:
            try:
                copiar_como(destino, destino_cmd)
                copias_cmd += 1
                detalle += f"  + {destino_cmd.name}"
            except Exception as exc:  # p. ej. .cmd solo-lectura: seguir con el resto
                detalle += f"  [copia .cmd falló: {type(exc).__name__}]"
                con_error.append(str(carpeta))
        if omitidos:
            detalle += f"  [omitidos: {', '.join(omitidos)}]"
            con_error.append(str(carpeta))
        print(f"  ✓  {rel}: {destino.name} {detalle}")

    print("-" * 64)
    verbo = "se unirían" if simulacro else "generados"
    print(
        f"  Resumen: {generados} PDF consolidados {verbo}"
        f"{'' if simulacro else f', {total_paginas} páginas en total'}."
    )
    if ahorrado:
        print(f"           Compresión: se ahorraron {_mb(ahorrado)} en total sin perder páginas.")
    if copias_cmd:
        print(
            f"           {copias_cmd} consolidado(s) quedaron también como .cmd (mismo PDF, otra extensión)."
        )
        print("           OJO: a los _UNIDO_*.cmd NO les des doble clic — no son programas.")
        print("           Para ver uno como documento, renómbralo de vuelta a .pdf.")
    if saltadas:
        print(f"           {saltadas} carpeta(s) con menos de {minimo} PDF, omitidas.")
    if con_error:
        print(f"           {len(con_error)} carpeta(s) con algún PDF ilegible (revisa arriba).")
    if generados == 0 and saltadas == 0:
        print("           No se encontraron PDF para unir en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Une los PDF de cada carpeta en un solo PDF consolidado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--minimo",
        type=int,
        default=2,
        help="Mínimo de PDF en una carpeta para unirla (por defecto 2).",
    )
    parser.add_argument(
        "--prefijo", default="_UNIDO_", help="Prefijo del PDF resultante (por defecto _UNIDO_)."
    )
    parser.add_argument(
        "--sin-recursion",
        action="store_true",
        help="Procesar solo la carpeta raíz, sin subcarpetas.",
    )
    parser.add_argument(
        "--tambien-cmd",
        action="store_true",
        help="Dejar además una copia idéntica del consolidado con extensión .cmd "
        "(mismo contenido PDF, solo cambia la extensión).",
    )
    parser.add_argument(
        "--comprimir",
        action="store_true",
        help="Reducir el peso del consolidado recomprimiendo los escaneos (150 dpi, "
        "JPEG 80): sigue perfectamente legible e imprimible. Requiere pymupdf; "
        "si falta, se continúa sin comprimir. Solo se aplica si de verdad reduce "
        "el tamaño y nunca pierde páginas.",
    )
    parser.add_argument(
        "--simulacro",
        "--dry-run",
        action="store_true",
        help="Mostrar qué haría, sin escribir ningún archivo.",
    )
    args = parser.parse_args(argv)

    raiz = Path(args.raiz).expanduser().resolve()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    if args.minimo < 1:
        sys.stderr.write("ERROR: --minimo debe ser 1 o más.\n")
        return 2

    return procesar(
        raiz=raiz,
        prefijo=args.prefijo,
        minimo=args.minimo,
        recursivo=not args.sin_recursion,
        simulacro=args.simulacro,
        tambien_cmd=args.tambien_cmd,
        comprimir=args.comprimir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
