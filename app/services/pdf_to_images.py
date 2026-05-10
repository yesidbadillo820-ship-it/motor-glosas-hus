"""Conversion PDF a imagenes PNG.

Util cuando un proveedor IA no tiene PDF nativo pero si tiene
multi-modal con imagenes (Gemini, Groq vision, OpenAI vision).

Usa pdfplumber (ya en requirements.txt) que internamente usa
Pillow para renderizar paginas a PNG. No requiere poppler ni
otros binarios externos como pdf2image.
"""
from __future__ import annotations
import io
import logging
from typing import Optional

import pdfplumber

logger = logging.getLogger("motor_glosas")


def pdf_a_imagenes_png(
    pdf_bytes: bytes,
    max_paginas: int = 15,
    dpi: int = 130,
    max_bytes_por_imagen: int = 4 * 1024 * 1024,
) -> list[bytes]:
    """Convierte un PDF a lista de bytes PNG (uno por pagina).

    Args:
        pdf_bytes: contenido del PDF.
        max_paginas: cap (default 15). PDFs muy largos se truncan
            para no quemar tokens del LLM ni exceder limites.
        dpi: resolucion de renderizado. 130 es legible para texto
            de historia clinica sin inflar el tamano. Subir a 200+
            si se necesita leer letra muy chica.
        max_bytes_por_imagen: si una pagina render >4MB, baja el
            quality. Algunos LLMs rechazan imagenes muy pesadas.

    Returns:
        Lista de bytes en formato PNG. Vacia si el PDF no se
        pudo abrir.
    """
    if not pdf_bytes or len(pdf_bytes) < 100:
        return []
    imagenes: list[bytes] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            n_total = len(pdf.pages)
            n_proc = min(n_total, max_paginas)
            for i in range(n_proc):
                try:
                    page = pdf.pages[i]
                    pil_img = page.to_image(resolution=dpi).original
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG", optimize=True)
                    img_bytes = buf.getvalue()
                    # Si la pagina es >max_bytes, re-render con dpi mas bajo
                    if len(img_bytes) > max_bytes_por_imagen and dpi > 80:
                        pil_img2 = page.to_image(resolution=80).original
                        buf2 = io.BytesIO()
                        pil_img2.save(buf2, format="PNG", optimize=True)
                        img_bytes = buf2.getvalue()
                    imagenes.append(img_bytes)
                except Exception as e:
                    logger.warning(f"[PDF2IMG] Pagina {i} fallo: {e}")
                    continue
        if n_total > max_paginas:
            logger.info(
                f"[PDF2IMG] PDF de {n_total} pags truncado a {max_paginas}. "
                f"Total renderizadas: {len(imagenes)}"
            )
    except Exception as e:
        logger.error(f"[PDF2IMG] No se pudo abrir PDF: {e}")
        return []
    return imagenes


def pdfs_a_imagenes_combinadas(
    pdfs_raw: list[tuple[str, bytes]],
    max_imagenes_total: int = 30,
    dpi: int = 130,
) -> list[tuple[str, bytes]]:
    """Convierte multiples PDFs a un unico flujo de imagenes con
    nombre 'archivo.pdf-pag-N.png'.

    Util para mandar varios PDFs como imagenes a un modelo vision
    (Gemini, Groq Llama 4, etc) cuando el modelo no soporta PDF
    nativo o cuando se quiere homogeneizar el input.
    """
    out: list[tuple[str, bytes]] = []
    paginas_por_pdf = max(2, max_imagenes_total // max(1, len(pdfs_raw)))
    for nombre, data in pdfs_raw:
        imgs = pdf_a_imagenes_png(data, max_paginas=paginas_por_pdf, dpi=dpi)
        for i, img in enumerate(imgs):
            if len(out) >= max_imagenes_total:
                break
            base = nombre.rsplit(".", 1)[0]
            out.append((f"{base}-pag-{i+1}.png", img))
        if len(out) >= max_imagenes_total:
            break
    return out
