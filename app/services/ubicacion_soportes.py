"""Dónde está, exactamente, el soporte dentro del PDF adjunto (V2, Pilar 3).

03-09-2026. Hasta ahora el dictamen podía decir «la epicrisis está adjunta» y
eso, para un auditor de la EPS, no prueba nada: le toca buscarla. Este módulo
abre los PDF con PyMuPDF, busca el documento pedido página por página y devuelve
el FOLIO REAL donde aparece, para que el escrito diga:

    «EL SOPORTE REQUERIDO SE ENCUENTRA ÍNTEGRAMENTE VISIBLE EN EL FOLIO 4 DEL
     ARCHIVO ADJUNTO epicrisis.pdf»

Es la misma disciplina de siempre: **Python encuentra el hecho, la IA no lo
inventa**. Si el término no aparece en ningún folio, aquí no sale nada y el
dictamen no puede citar una ubicación que no existe.

Diferencia con `extractor_folios.py` (que ya existía y sigue igual): aquel lee
el TEXTO y detecta folios *mencionados* («folio 59») para vigilar que el
dictamen no los invente. Este ubica la POSICIÓN FÍSICA de un documento dentro
del PDF. Se complementan, no se pisan.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.core.logging_utils import logger

# Qué buscar dentro de los PDF, por documento. La clave es el nombre con que se
# le habla al auditor; los valores son las formas en que ese documento se
# titula de verdad en un expediente del HUS.
TERMINOS_POR_DOCUMENTO: dict[str, tuple[str, ...]] = {
    "la epicrisis": ("EPICRISIS", "RESUMEN DE EGRESO", "RESUMEN DE HISTORIA CLINICA"),
    "el formato MIPRES": ("MIPRES",),
    "la historia clínica": ("HISTORIA CLINICA", "ANAMNESIS", "NOTA DE INGRESO"),
    "la nota operatoria": ("NOTA OPERATORIA", "DESCRIPCION QUIRURGICA", "PROTOCOLO QUIRURGICO"),
    "el récord de anestesia": ("RECORD DE ANESTESIA", "REGISTRO DE ANESTESIA", "HOJA DE ANESTESIA"),
    "el kardex": ("KARDEX", "HOJA DE ADMINISTRACION DE MEDICAMENTOS"),
    "los RIPS": ("RIPS",),
    "la orden médica": ("ORDEN MEDICA", "FORMULA MEDICA", "PRESCRIPCION"),
    "el consentimiento informado": ("CONSENTIMIENTO INFORMADO",),
    "el certificado de agotamiento del SOAT": (
        "CERTIFICADO DE AGOTAMIENTO",
        "CERTIFICACION DE AGOTAMIENTO",
        "AGOTAMIENTO DE LA COBERTURA",
    ),
    "la factura": ("FACTURA DE VENTA", "FACTURA ELECTRONICA"),
}


def _sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def _paginas_de(pdf_bytes: bytes) -> list[str]:
    """Texto de cada página del PDF, en orden. Lista vacía si no se puede leer.

    Nunca lanza: un PDF escaneado sin capa de texto, corrupto o protegido
    simplemente no aporta ubicaciones — y el dictamen entonces no cita folio.
    """
    try:
        import pymupdf  # PyMuPDF
    except Exception as e:  # noqa: BLE001 — sin la librería, se degrada elegante
        logger.debug(f"[FOLIOS] PyMuPDF no disponible: {e}")
        return []
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            return [(pagina.get_text() or "") for pagina in doc]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[FOLIOS] PDF ilegible: {e}")
        return []


def ubicar_documentos(
    pdfs: list[tuple[str, bytes]],
    documentos: Optional[list[str]] = None,
) -> list[dict]:
    """Busca cada documento pedido dentro de los PDF y devuelve dónde está.

    `pdfs` es [(nombre_archivo, bytes), …] tal como llegan los adjuntos.
    `documentos` limita la búsqueda a esos nombres (claves de
    TERMINOS_POR_DOCUMENTO); si es None, busca todos.

    Devuelve [{documento, archivo, folio, termino}, …] con el PRIMER folio
    donde aparece cada documento en cada archivo (folio = página, 1 en
    adelante). Sin coincidencias, lista vacía: no se inventa ubicación.
    """
    hallazgos: list[dict] = []
    if not pdfs:
        return hallazgos
    buscados = {
        k: v
        for k, v in TERMINOS_POR_DOCUMENTO.items()
        if documentos is None or k in set(documentos)
    }
    if not buscados:
        return hallazgos

    for nombre, datos in pdfs:
        if not datos:
            continue
        paginas = _paginas_de(datos)
        if not paginas:
            continue
        planas = [_sin_tildes(p) for p in paginas]
        for documento, terminos in buscados.items():
            for termino in terminos:
                t = _sin_tildes(termino)
                encontrado = next((i for i, p in enumerate(planas) if t in p), None)
                if encontrado is not None:
                    hallazgos.append(
                        {
                            "documento": documento,
                            "archivo": nombre,
                            "folio": encontrado + 1,  # folio = página, base 1
                            "termino": termino,
                        }
                    )
                    break  # con el primer término que aparezca basta
    return hallazgos


def parrafo_ubicacion_soportes(hallazgos: list[dict]) -> str:
    """El párrafo que cita la ubicación real, armado en Python.

    Con un solo hallazgo queda la frase que pidió el auditor; con varios, se
    enumeran todos. Sin hallazgos devuelve cadena vacía (no hay nada que citar).
    """
    if not hallazgos:
        return ""
    partes = []
    for h in hallazgos:
        partes.append(
            f"{h['documento'].upper()} EN EL FOLIO {h['folio']} DEL ARCHIVO ADJUNTO "
            f"«{h['archivo']}»"
        )
    if len(partes) == 1:
        cuerpo = partes[0]
    else:
        cuerpo = ", ".join(partes[:-1]) + " Y " + partes[-1]
    return (
        "EL SOPORTE REQUERIDO SE ENCUENTRA ÍNTEGRAMENTE VISIBLE EN EL EXPEDIENTE "
        f"REMITIDO: {cuerpo}. SE SOLICITA A LA ENTIDAD VERIFICARLO EN LA UBICACIÓN "
        "INDICADA Y LEVANTAR LA GLOSA."
    )


def documentos_que_pide_la_glosa(texto_glosa: str) -> list[str]:
    """Qué documentos echa de menos la entidad, según el texto de la glosa.

    Se usa para buscar SOLO lo que la glosa reclama: si pide la epicrisis, se
    ubica la epicrisis, no todo el expediente.
    """
    u = _sin_tildes(texto_glosa)
    pedidos = []
    for documento, terminos in TERMINOS_POR_DOCUMENTO.items():
        if any(_sin_tildes(t) in u for t in terminos):
            pedidos.append(documento)
    return pedidos
