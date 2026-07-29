"""
nucleo.pdf_tools — Caja de herramientas PDF de la Suite Cartera HUS (offline).

Un solo motor (PyMuPDF / fitz) para las operaciones que en cartera se hacen a
diario con facturas, glosas y soportes, SIN internet y SIN abrir Acrobat:

    unir · dividir · eliminar/extraer/ordenar páginas · rotar · recortar ·
    números de página · marca de agua · imágenes→PDF · PDF→imágenes ·
    comprimir · proteger · desbloquear · censurar · reparar · info ·
    renombrar (el truco PDF↔.cmd del HUS).

Todas las funciones reciben rutas, escriben el resultado y devuelven la ruta de
salida. `log` recibe el avance (para la consola de la Suite).
"""

import os

try:
    import fitz  # PyMuPDF
except ImportError:  # el launcher avisa; aquí solo evitamos romper el import
    fitz = None


def _exigir_fitz():
    if fitz is None:
        raise RuntimeError(
            "Falta PyMuPDF. Ejecute INICIAR_SUITE.bat con internet una vez, "
            "o instale manualmente:  pip install pymupdf"
        )


# ------------------------------------------------------------------ helpers


def parse_paginas(spec, total):
    """'1-3,5,7-' -> [0,1,2,4,6,...] (0-based, dentro de 1..total). Ordenado y sin repetir."""
    if not spec or str(spec).strip().lower() in ("todas", "all", "*"):
        return list(range(total))
    out = []
    for trozo in str(spec).replace(" ", "").split(","):
        if not trozo:
            continue
        if "-" in trozo:
            a, _, b = trozo.partition("-")
            ini = int(a) if a else 1
            fin = int(b) if b else total
        else:
            ini = fin = int(trozo)
        for n in range(ini, fin + 1):
            if 1 <= n <= total and (n - 1) not in out:
                out.append(n - 1)
    return out


def _salida(ruta, sufijo, carpeta=None, ext=".pdf"):
    base = os.path.splitext(os.path.basename(ruta))[0]
    carpeta = carpeta or os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, "%s_%s%s" % (base, sufijo, ext))


# ------------------------------------------------------------------ operaciones


def info(ruta, log=print):
    """Devuelve un dict con páginas, cifrado y metadatos del PDF."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    d = {
        "archivo": os.path.basename(ruta),
        "paginas": doc.page_count,
        "cifrado": bool(doc.needs_pass),
        "metadatos": dict(doc.metadata or {}),
    }
    doc.close()
    log(
        "  %s: %d páginas%s" % (d["archivo"], d["paginas"], "  (protegido)" if d["cifrado"] else "")
    )
    return d


def unir(rutas, salida, log=print):
    """Une varios PDF (en el orden dado) en uno solo."""
    _exigir_fitz()
    if len(rutas) < 2:
        raise ValueError("Para unir se necesitan al menos 2 PDF.")
    dst = fitz.open()
    total = 0
    for r in rutas:
        with fitz.open(r) as src:
            dst.insert_pdf(src)
            total += src.page_count
            log("  + %s (%d pág.)" % (os.path.basename(r), src.page_count))
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    dst.save(salida, garbage=3, deflate=True)
    dst.close()
    log("Unido: %s (%d páginas)" % (salida, total))
    return salida


def dividir(ruta, carpeta=None, cada=1, log=print):
    """Parte el PDF en archivos de `cada` páginas (por defecto, 1 por archivo)."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    carpeta = carpeta or _salida(ruta, "dividido", ext="")
    os.makedirs(carpeta, exist_ok=True)
    rutas = []
    n = 0
    for ini in range(0, doc.page_count, cada):
        fin = min(ini + cada, doc.page_count)
        parte = fitz.open()
        parte.insert_pdf(doc, from_page=ini, to_page=fin - 1)
        n += 1
        rp = os.path.join(carpeta, "parte_%03d.pdf" % n)
        parte.save(rp, garbage=3, deflate=True)
        parte.close()
        rutas.append(rp)
    doc.close()
    log("Dividido en %d archivo(s) → %s" % (len(rutas), carpeta))
    return rutas


def extraer_paginas(ruta, paginas, salida=None, log=print):
    """Conserva SOLO las páginas indicadas ('1-3,5'). El resto se descarta."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    idx = parse_paginas(paginas, doc.page_count)
    if not idx:
        raise ValueError("No hay páginas válidas en el rango '%s'." % paginas)
    doc.select(idx)
    salida = salida or _salida(ruta, "extraido")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Extraídas %d página(s) → %s" % (len(idx), salida))
    return salida


def eliminar_paginas(ruta, paginas, salida=None, log=print):
    """Quita las páginas indicadas ('2,4-6') y conserva el resto."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    quitar = set(parse_paginas(paginas, doc.page_count))
    quedan = [i for i in range(doc.page_count) if i not in quitar]
    if not quedan:
        raise ValueError("Eliminaría todas las páginas: revise el rango.")
    doc.select(quedan)
    salida = salida or _salida(ruta, "sin_paginas")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Eliminadas %d página(s), quedan %d → %s" % (len(quitar), len(quedan), salida))
    return salida


def reordenar(ruta, orden, salida=None, log=print):
    """Reordena las páginas según `orden` (lista 1-based, p. ej. [3,1,2])."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    idx = [n - 1 for n in orden if 1 <= n <= doc.page_count]
    if len(idx) != doc.page_count:
        log("  [!] El orden no cubre todas las páginas; se usa el subconjunto dado.")
    doc.select(idx)
    salida = salida or _salida(ruta, "reordenado")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Reordenado (%d páginas) → %s" % (len(idx), salida))
    return salida


def rotar(ruta, grados=90, paginas=None, salida=None, log=print):
    """Rota páginas (90/180/270). `paginas` None = todas."""
    _exigir_fitz()
    if grados % 90 != 0:
        raise ValueError("Los grados deben ser múltiplo de 90.")
    doc = fitz.open(ruta)
    objetivo = parse_paginas(paginas, doc.page_count) if paginas else range(doc.page_count)
    for i in objetivo:
        p = doc[i]
        p.set_rotation((p.rotation + grados) % 360)
    salida = salida or _salida(ruta, "rotado")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Rotadas %d°  → %s" % (grados, salida))
    return salida


def recortar(ruta, margen=0.05, salida=None, log=print):
    """Recorta un margen relativo (0.05 = 5% por lado) de cada página."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    for p in doc:
        r = p.rect
        dx, dy = r.width * margen, r.height * margen
        p.set_cropbox(fitz.Rect(r.x0 + dx, r.y0 + dy, r.x1 - dx, r.y1 - dy))
    salida = salida or _salida(ruta, "recortado")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Recortado %.0f%% por lado → %s" % (margen * 100, salida))
    return salida


def numerar(ruta, salida=None, inicio=1, log=print):
    """Inserta el número de página abajo al centro ('n / total')."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    total = doc.page_count
    for i, p in enumerate(doc):
        texto = "%d / %d" % (inicio + i, inicio + total - 1)
        x = p.rect.width / 2 - 20
        y = p.rect.height - 24
        p.insert_text((x, y), texto, fontsize=10, color=(0.25, 0.25, 0.25))
    salida = salida or _salida(ruta, "numerado")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Numeradas %d páginas → %s" % (total, salida))
    return salida


def marca_agua(ruta, texto, salida=None, log=print):
    """Estampa una marca de agua diagonal (texto) en todas las páginas."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    for p in doc:
        r = p.rect
        # insert_text solo rota en múltiplos de 90; para la diagonal (45°) se
        # usa un TextWriter con matriz de rotación alrededor del centro.
        tw = fitz.TextWriter(r)
        tw.append(fitz.Point(r.width * 0.12, r.height * 0.62), texto, fontsize=40)
        pivote = fitz.Point(r.width / 2, r.height / 2)
        tw.write_text(p, color=(0.6, 0.6, 0.6), opacity=0.28, morph=(pivote, fitz.Matrix(45)))
    salida = salida or _salida(ruta, "marca_agua")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Marca de agua '%s' → %s" % (texto[:30], salida))
    return salida


def imagenes_a_pdf(rutas_img, salida, log=print):
    """Une imágenes (PNG/JPG) en un PDF, una por página."""
    _exigir_fitz()
    if not rutas_img:
        raise ValueError("No se dieron imágenes.")
    doc = fitz.open()
    for img in rutas_img:
        with fitz.open(img) as imd:
            pdfbytes = imd.convert_to_pdf()
        with fitz.open("pdf", pdfbytes) as imgpdf:
            doc.insert_pdf(imgpdf)
        log("  + %s" % os.path.basename(img))
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    doc.save(salida)
    doc.close()
    log("Imágenes → %s (%d)" % (salida, len(rutas_img)))
    return salida


def pdf_a_imagenes(ruta, carpeta=None, dpi=150, log=print):
    """Renderiza cada página a PNG (para pantallazos/soportes)."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    carpeta = carpeta or _salida(ruta, "imagenes", ext="")
    os.makedirs(carpeta, exist_ok=True)
    rutas = []
    for i, p in enumerate(doc, 1):
        pix = p.get_pixmap(dpi=dpi)
        rp = os.path.join(carpeta, "pagina_%03d.png" % i)
        pix.save(rp)
        rutas.append(rp)
    doc.close()
    log("PDF → %d imagen(es) @ %d dpi → %s" % (len(rutas), dpi, carpeta))
    return rutas


def comprimir(ruta, salida=None, log=print):
    """Comprime: recolecta basura, deflate y limpia objetos redundantes."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    salida = salida or _salida(ruta, "comprimido")
    doc.save(salida, garbage=4, deflate=True, clean=True, deflate_images=True, deflate_fonts=True)
    doc.close()
    antes = os.path.getsize(ruta)
    despues = os.path.getsize(salida)
    log(
        "Comprimido: %d → %d KB (%.0f%%) → %s"
        % (antes // 1024, despues // 1024, 100 * (1 - despues / antes) if antes else 0, salida)
    )
    return salida


def proteger(ruta, password, salida=None, log=print):
    """Cifra el PDF con contraseña (AES-256)."""
    _exigir_fitz()
    if not password:
        raise ValueError("Debe indicar una contraseña.")
    doc = fitz.open(ruta)
    salida = salida or _salida(ruta, "protegido")
    doc.save(
        salida,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw=password,
        garbage=3,
        deflate=True,
    )
    doc.close()
    log("Protegido con contraseña → %s" % salida)
    return salida


def desbloquear(ruta, password="", salida=None, log=print):
    """Quita la contraseña (hay que conocerla) y guarda el PDF abierto."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        raise ValueError("Contraseña incorrecta: no se pudo desbloquear.")
    salida = salida or _salida(ruta, "desbloqueado")
    doc.save(salida, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    doc.close()
    log("Desbloqueado → %s" % salida)
    return salida


def censurar(ruta, textos, salida=None, log=print):
    """Tacha (redacción real, no solo negro encima) los textos indicados."""
    _exigir_fitz()
    if isinstance(textos, str):
        textos = [textos]
    doc = fitz.open(ruta)
    n = 0
    for p in doc:
        for t in textos:
            for area in p.search_for(t):
                p.add_redact_annot(area, fill=(0, 0, 0))
                n += 1
        p.apply_redactions()
    salida = salida or _salida(ruta, "censurado")
    doc.save(salida, garbage=3, deflate=True)
    doc.close()
    log("Censuradas %d coincidencia(s) → %s" % (n, salida))
    return salida


def reparar(ruta, salida=None, log=print):
    """Reabre y reescribe el PDF: sana referencias rotas y objetos huérfanos."""
    _exigir_fitz()
    doc = fitz.open(ruta)
    salida = salida or _salida(ruta, "reparado")
    doc.save(salida, garbage=4, clean=True, deflate=True)
    doc.close()
    log("Reparado → %s" % salida)
    return salida


def renombrar_extension(ruta, nueva_ext, salida=None, log=print):
    """El truco del HUS: renombra .pdf ↔ .cmd (u otra) sin tocar el contenido."""
    if not nueva_ext.startswith("."):
        nueva_ext = "." + nueva_ext
    base = os.path.splitext(ruta)[0]
    salida = salida or (base + nueva_ext)
    with open(ruta, "rb") as f, open(salida, "wb") as g:
        g.write(f.read())
    log("Renombrado %s → %s" % (os.path.basename(ruta), os.path.basename(salida)))
    return salida
