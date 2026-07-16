#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_book.py — Maquetador de «Hijos del Firmamento · Libro Primero».
Ensambla preliminares + novela + finales en un HTML editable y lo compone en
PDF con WeasyPrint (CSS Paged Media, estilos en src/estilos.css).

Uso:
    python3 src/build_book.py            -> pdf/HIJOS_DEL_FIRMAMENTO_Libro_I.pdf
    REVISION=1 python3 src/build_book.py -> marca las consultas editoriales
"""

import os, re, html
from parse_book import parse, KNOWN_CORRUPT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVISION = bool(os.environ.get("REVISION"))

# --- Metadatos (SUSTITUIR por los reales; ver informe) --------------------
META = dict(
    autor="N. N.",  # ‹ falta el nombre del autor ›
    titulo="Hijos del Firmamento",
    libro="Libro Primero",
    subtitulo="Las voces que nacieron del fuego",
    editorial="Nombre de la editorial",
    ciudad="Ciudad",
    anio="2026",
    isbn="978-XXX-XXXX-XX-X",
    imprenta="nombre de la imprenta",
)

ESTRELLA = open(os.path.join(ROOT, "recursos", "estrella.svg")).read()
CONSTEL = open(os.path.join(ROOT, "recursos", "constelacion.svg")).read()

ROMANOS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
ORD = {1: "PRIMERA", 2: "SEGUNDA", 3: "TERCERA", 4: "CUARTA", 5: "QUINTA"}

# --- Marcado de consultas (corrupción del origen), sin alterar el texto ---
_CORRUPT_RE = None


def mark_corrupt(h):
    global _CORRUPT_RE
    if _CORRUPT_RE is None:
        toks = sorted(KNOWN_CORRUPT, key=len, reverse=True)
        _CORRUPT_RE = re.compile(
            r"(?<![\w])(" + "|".join(re.escape(t) for t in toks) + r")(?![\w])"
        )
    return _CORRUPT_RE.sub(r'<span class="q">\1</span>', h)


def incipit(h, n=3):
    """Primeras n palabras del párrafo en versalitas (incipit de capítulo)."""
    # respeta una posible raya inicial de diálogo
    plain = re.sub("<[^>]+>", "", h)
    words = plain.split()
    if not words:
        return h
    take = min(n, len(words))
    # Los íncipits no llevan cursiva: se opera sobre texto plano.
    target = " ".join(words[:take])
    rest = " ".join(words[take:])
    return f'<span class="incipit">{html.escape(target)}</span> {html.escape(rest)}'


def para_html(b, first=False):
    h = b["html"]
    if REVISION:
        h = mark_corrupt(h)
    txt = re.sub("<[^>]+>", "", h).strip()
    # onomatopeya aislada
    if txt in ("Rrrrip.", "Rrrrip"):
        return f'<p class="onoma">{txt}</p>'
    cls = "primero" if first else ""
    if first and not h.lstrip().startswith("—") and "<em>" not in h[:40]:
        h = incipit(h)
        if REVISION:
            h = mark_corrupt(h)
    return f'<p class="{cls}">{h}</p>'


def diary_html(b):
    h = b["html"]
    if REVISION:
        h = mark_corrupt(h)
    # primera oración = fecha/encabezado del cuaderno
    m = re.match(r"\s*([^.]{1,40}\.)(.*)", re.sub("<[^>]+>", "", h), re.S)
    if m:
        fecha = html.escape(m.group(1).strip())
        resto = html.escape(m.group(2).strip())
        return f'<div class="diario"><span class="fecha">{fecha}</span> {resto}</div>'
    return f'<div class="diario">{h}</div>'


# --- Construcción del cuerpo ----------------------------------------------
def build_body(blocks):
    out = []
    toc = []  # (nivel, etiqueta, id, tipo)
    first_para_pending = False
    for b in blocks:
        t = b["type"]
        if t == "book_open":
            out.append(f"""<section class="abre-libro">
  <div class="kicker">{b["label"]}</div>
  <h1>{META["titulo"].upper()}</h1>
  <div class="subt">{html.escape(b["subtitle"])}</div>
  <div class="estrella-grande">{ESTRELLA}</div>
</section>""")
        elif t == "prologue_open":
            toc.append((2, "Prólogo", "prologo", "prol", html.escape(b["title"])))
            out.append(f"""<section class="abre-cap prologo set-cornisa" id="prologo">
  <span class="caprotulo">{html.escape(b["label"])}</span>
  <div class="estrella-grande" style="width:12px;margin:0 auto 4mm">{ESTRELLA}</div>
  <hr class="filete">
  <h2>{html.escape(b["title"])}</h2>
</section>""")
            first_para_pending = True
        elif t == "part_open":
            num = {"PRIMERA PARTE": 1, "SEGUNDA PARTE": 2, "TERCERA PARTE": 3}.get(b["label"], 1)
            pid = f"parte-{num}"
            toc.append((1, b["label"], pid, "parte", ""))
            out.append(f'''<section class="abre-parte" id="{pid}">
  <div class="rom">{ROMANOS.get(num, num)}</div>
  <div class="rotulo">{ORD.get(num, "")} PARTE</div>
  <div class="constel">{CONSTEL}</div>
</section>''')
        elif t == "chapter_open":
            cid = f"cap-{b['num']}"
            toc.append((2, f"Capítulo {b['num']}", cid, "cap", html.escape(b["title"])))
            out.append(f'''<section class="abre-cap set-cornisa" id="{cid}">
  <span class="caprotulo">Capítulo</span>
  <div class="capnum">{b["num"]}</div>
  <hr class="filete">
  <h2>{html.escape(b["title"])}</h2>
</section>''')
            first_para_pending = True
        elif t == "para":
            out.append(para_html(b, first=first_para_pending))
            first_para_pending = False
        elif t == "scene":
            out.append(f'<div class="escena">{ESTRELLA}</div>')
        elif t == "diary":
            out.append(diary_html(b))
        elif t == "special_head":
            out.append(
                f'<div class="atlas"><span class="r">{html.escape(b["text"])}</span><hr></div>'
            )
            first_para_pending = False
        elif t == "end_matter":
            teaser = html.escape(b["teaser"])
            teaser = re.sub(r"(Libro II:.*?)(\.|$)", r"<b>\1</b>\2", teaser)
            out.append(f"""<section class="cierre">
  <div class="fin">{html.escape(b["text"])}</div>
  <div class="estrella">{ESTRELLA}</div>
  <div class="teaser">{teaser}</div>
</section>""")
    return "\n".join(out), toc


# --- Preliminares ----------------------------------------------------------
def front_matter():
    m = META
    dedic = """Para <span class="n">Daniela</span>,<br>que me mostró la primera estrella.<br><br>
Para <span class="n">Dania</span>,<br>que me enseñó a preguntar por ella.<br><br>
Todo lo que he guardado<br>—cada papel, cada fecha, cada luz—<br>
lo guardé, sin saberlo, para ustedes."""
    return f"""<section class="portadilla">
  <div class="t">{m["titulo"].upper()}</div>
  <div class="estrella">{ESTRELLA}</div>
</section>
<section class="blanca"></section>

<section class="portada">
  <div class="autor">{html.escape(m["autor"])}</div>
  <h1 class="titulo">{m["titulo"].upper()}</h1>
  <hr class="hair">
  <div class="vol">{m["libro"].upper()}</div>
  <div class="subt">{html.escape(m["subtitulo"])}</div>
  <div class="pie">{m["editorial"].upper()}</div>
</section>

<section class="legal abajo">
  <div class="fill"></div>
  <div class="marca">{m["titulo"].upper()}</div>
  <div class="estrella">{ESTRELLA}</div>
  <p>Primera edición: {m["anio"]}</p>
  <p>© {m["anio"]}, {html.escape(m["autor"])}, por el texto</p>
  <p>© {m["anio"]}, {m["editorial"]}, por la presente edición</p>
  <p>{m["ciudad"]}</p>
  <p>ISBN: {m["isbn"]}</p>
  <p>Depósito legal: ————</p>
  <p style="margin-top:3mm">Compuesto en tipografía Alegreya, de Juan Pablo del Peral
     (Huerta&nbsp;Tipográfica), bajo licencia SIL&nbsp;Open&nbsp;Font.</p>
  <p>Reservados todos los derechos. Queda prohibida la reproducción total o
     parcial de esta obra por cualquier medio sin autorización escrita de los
     titulares del copyright.</p>
  <p>Impreso en {html.escape(m["imprenta"])}.</p>
</section>

<section class="dedicatoria">
  <div class="texto">{dedic}</div>
</section>
<section class="blanca"></section>

<section class="epigrafe">
  <span class="estrella">{ESTRELLA}</span>
  <p class="cita">Extranjero, ve y cuéntale a los nuestros que aquí quedamos,
     cumpliendo lo que nos mandaron.</p>
  <div class="fuente">Epitafio de las Termópilas</div>
</section>
<section class="blanca"></section>"""


# --- Índice y colofón ------------------------------------------------------
def back_matter(toc):
    filas = ['<section class="indice"><h2>Índice</h2>']
    for nivel, etiqueta, cid, tipo, *rest in toc:
        titulo = rest[0] if rest else ""
        if tipo == "parte":
            filas.append(f'<div class="grupo">{html.escape(etiqueta)}</div>')
        elif tipo == "prol":
            filas.append(
                f'<a class="fila prol" href="#{cid}">'
                f'<span class="tit">{titulo}</span>'
                f'<span class="pts"></span></a>'
            )
        else:  # capítulo
            num = etiqueta.split()[-1]
            filas.append(
                f'<a class="fila" href="#{cid}">'
                f'<span class="tit"><span class="num">{num}</span>{titulo}</span>'
                f'<span class="pts"></span></a>'
            )
    filas.append("</section>")
    m = META
    colofon = f"""<section class="colofon"><div class="in">
  <div class="estrella">{ESTRELLA}</div>
  <p>Este primer libro de <span class="sc">{m["titulo"]}</span>,<br>
  <span style="font-style:italic">{html.escape(m["subtitulo"])}</span>,<br>
  se terminó de imprimir en {html.escape(m["ciudad"])}<br>
  en el mes de ———— de {m["anio"]},<br>
  cuando la luz de estrellas ya apagadas<br>
  seguía, todavía, llegando.</p>
  <div class="estrella" style="width:9px;margin:8mm auto 0">{ESTRELLA}</div>
</div></section>"""
    return "\n".join(filas) + "\n" + colofon


# --- Documento -------------------------------------------------------------
def build():
    blocks, log, corrupt = parse()
    body, toc = build_body(blocks)
    doc = f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{META["titulo"]} · {META["libro"]}</title>
<link rel="stylesheet" href="estilos.css">
</head>
<body class="{"revision" if REVISION else ""}">
{front_matter()}
{body}
{back_matter(toc)}
</body>
</html>'''
    editable = os.path.join(ROOT, "src", "libro_editable.html")
    open(editable, "w").write(doc)

    from weasyprint import HTML

    outname = "HIJOS_DEL_FIRMAMENTO_Libro_I" + ("_REVISION" if REVISION else "") + ".pdf"
    outpdf = os.path.join(ROOT, "pdf", outname)
    HTML(filename=editable).write_pdf(outpdf)
    print("PDF:", outpdf)
    print("HTML editable:", editable)
    print("Capítulos en índice:", sum(1 for x in toc if x[3] == "cap"))
    return outpdf


if __name__ == "__main__":
    build()
