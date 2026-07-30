"""
nucleo.archivos — Utilidades de archivos para la Suite Cartera HUS.

- Detecta el TIPO REAL de un archivo por su firma binaria (no por la extensión,
  porque en el flujo del HUS los PDF suelen venir renombrados como .cmd).
- Extrae ZIP con ZIPs adentro (recursivo) de forma segura (anti zip-slip).
- Clasifica archivos en DETALLE / GLOSAS / FACTURA por patrones del nombre.
- Extrae el número de factura del nombre del archivo.
"""

import os
import re
import shutil
import zipfile

# ---------------------------------------------------------------- tipo real

FIRMAS = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "zip",  # zip, xlsx, docx, pptx (se afina abajo)
    b"\xd0\xcf\x11\xe0": "ole",  # xls / doc antiguos
}


def tipo_real(ruta):
    """Devuelve el tipo real del archivo: pdf, xlsx, docx, zip, xls, csv, txt, desconocido.

    Ignora la extensión: lee la firma binaria. Un .cmd que en realidad es un
    PDF se reporta como 'pdf'.
    """
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(8)
    except OSError:
        return "desconocido"

    for firma, tipo in FIRMAS.items():
        if cabecera.startswith(firma):
            if tipo == "zip":
                return _afinar_zip(ruta)
            if tipo == "ole":
                return "xls"
            return tipo

    # ¿Texto plano / CSV?
    try:
        with open(ruta, "rb") as f:
            trozo = f.read(4096)
        trozo.decode("utf-8")
        primera = trozo.split(b"\n", 1)[0]
        if b";" in primera or b"," in primera or b"\t" in primera:
            return "csv"
        return "txt"
    except (UnicodeDecodeError, OSError):
        return "desconocido"


def _afinar_zip(ruta):
    """Un contenedor ZIP puede ser xlsx/docx/zip: se distingue por su contenido."""
    try:
        with zipfile.ZipFile(ruta) as z:
            nombres = set(z.namelist())
        if any(n.startswith("xl/") for n in nombres):
            return "xlsx"
        if any(n.startswith("word/") for n in nombres):
            return "docx"
        return "zip"
    except (zipfile.BadZipFile, OSError):
        return "desconocido"


# ------------------------------------------------------- extracción segura


def _destino_seguro(base, nombre):
    """Evita zip-slip: el archivo extraído debe quedar DENTRO de `base`."""
    destino = os.path.realpath(os.path.join(base, nombre))
    if not destino.startswith(os.path.realpath(base) + os.sep):
        raise ValueError("Entrada de ZIP insegura: %s" % nombre)
    return destino


def extraer_zip_recursivo(ruta_zip, carpeta_destino, log=print):
    """Extrae un ZIP y todos los ZIP que traiga adentro (recursivo).

    Devuelve la lista de rutas de todos los archivos finales extraídos
    (sin contar los .zip intermedios).
    """
    os.makedirs(carpeta_destino, exist_ok=True)
    extraidos = []
    # Cada pendiente es (zip, carpeta donde extraer SUS miembros). El ZIP de
    # nivel superior va a carpeta_destino; cada ZIP anidado se extrae en su
    # propia subcarpeta (por el nombre del zip), para que dos "GLOSAS.xlsx" de
    # ramas distintas no se pisen entre sí.
    pendientes = [(ruta_zip, carpeta_destino)]
    nivel = 0

    while pendientes and nivel < 6:  # tope de anidamiento por seguridad
        siguientes = []
        for z_path, base_ext in pendientes:
            try:
                with zipfile.ZipFile(z_path) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        try:
                            destino = _destino_seguro(base_ext, info.filename)
                        except ValueError:
                            # entrada con ../ o ruta absoluta: se omite SOLO esa,
                            # sin abortar el resto del ZIP (nada más se pierde).
                            log("  [!] Entrada omitida por ruta insegura: %s" % info.filename)
                            continue
                        os.makedirs(os.path.dirname(destino), exist_ok=True)
                        with z.open(info) as origen, open(destino, "wb") as salida:
                            shutil.copyfileobj(origen, salida)
                        if tipo_real(destino) == "zip":
                            stem = os.path.splitext(os.path.basename(destino))[0]
                            siguientes.append(
                                (destino, os.path.join(os.path.dirname(destino), stem))
                            )
                        else:
                            extraidos.append(destino)
            except zipfile.BadZipFile:
                log("  [!] ZIP dañado u omitido: %s" % os.path.basename(z_path))
        # los ZIP internos recién escritos se procesan en la vuelta siguiente;
        # la limpieza de los intermedios se hace al final del bucle.
        pendientes = siguientes
        nivel += 1

    # limpieza de zips intermedios que quedaron dentro del destino
    for raiz, _, archivos in os.walk(carpeta_destino):
        for a in archivos:
            r = os.path.join(raiz, a)
            if r != ruta_zip and tipo_real(r) == "zip":
                try:
                    os.remove(r)
                except OSError:
                    pass

    log("  Extraídos %d archivos (anidamiento: %d nivel(es))." % (len(extraidos), nivel))
    return extraidos


# ------------------------------------------------------------ clasificación

PATRONES_TIPO_DEFECTO = {
    "DETALLE": [r"DETALLE"],
    "GLOSAS": [r"GLOSA"],
    "FACTURA": [r"FACTURA"],
}

# Patrón del HUS (HUS####) y genérico de 6-10 dígitos. El genérico usa
# lookarounds (no \b) para reconocer facturas numéricas pegadas a un guion
# bajo, p. ej. "123456_GLOSAS.xlsx" (con \b no calzaban: '_' es de palabra).
PATRON_FACTURA_HUS = r"HUS0*\d{4,}"
PATRON_FACTURA_NUM = r"(?<!\d)\d{6,10}(?!\d)"
# Combinado, por compatibilidad con quien lo importe o lo pase a mano.
PATRON_FACTURA_DEFECTO = r"(HUS0*\d{4,})|(?<!\d)(\d{6,10})(?!\d)"


def clasificar_archivo(nombre, patrones=None):
    """Devuelve 'DETALLE', 'GLOSAS', 'FACTURA' o None según el nombre."""
    patrones = patrones or PATRONES_TIPO_DEFECTO
    mayus = nombre.upper()
    for tipo, lista in patrones.items():
        for pat in lista:
            if re.search(pat, mayus):
                return tipo
    return None


def extraer_factura(nombre, patron=None):
    """Extrae el identificador de factura del nombre de archivo (o None).

    Da prioridad al formato del HUS (HUS####) aunque aparezca DESPUÉS de otro
    número en el nombre (p. ej. una fecha "20240115"); sólo si no hay HUS cae
    al genérico de 6-10 dígitos. Con `patron` explícito conserva el modo previo.
    """
    up = nombre.upper()
    if patron is not None:
        m = re.search(patron, up)
        if not m:
            return None
        for grupo in m.groups():
            if grupo:
                return grupo
        return m.group(0)
    m = re.search(PATRON_FACTURA_HUS, up)
    if m:
        return m.group(0)
    m = re.search(PATRON_FACTURA_NUM, up)
    return m.group(0) if m else None


def inventariar(carpeta):
    """Recorre una carpeta y devuelve [(ruta, tipo_real)] de todos los archivos."""
    resultado = []
    for raiz, _, archivos in os.walk(carpeta):
        for a in archivos:
            r = os.path.join(raiz, a)
            resultado.append((r, tipo_real(r)))
    return resultado
