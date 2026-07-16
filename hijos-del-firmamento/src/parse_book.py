#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_book.py — Reconstructor semántico del manuscrito «Hijos del Firmamento».

Convierte el .docx (con líneas fragmentadas por el volcado desde un original
maquetado) en una estructura de bloques limpia y editable, SIN alterar una sola
palabra de la novela. Sólo realiza reparaciones MECÁNICAS y trazables:

  1. Reune las líneas fragmentadas en los párrafos reales del autor
     (une por flujo de puntuación terminal; nunca funde párrafos legítimos).
  2. Deshace la partición de guiones de fin de línea  (des-  pués -> después;
     «Algu-» + «nas» -> «Algunas»).  Verificado: NO existe ningún guion legítimo
     (U+002D) en el manuscrito; los 879 guiones largos (—) de diálogo se respetan.
  3. Elimina los renglones en blanco espurios insertados dentro de una frase.
  4. Preserva las cursivas del autor (521 tramos) como <em>.

NO repara —sólo cataloga— la corrupción a nivel de palabra (letras barajadas o
espacios perdidos), porque restaurarla exigiría inventar texto del autor.
El catálogo se entrega en el informe de integridad para consulta del autor.
"""

import html as _html
import re
import os
import json
import docx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCX = os.path.join(ROOT, "manuscrito", "libro_I.docx")

# Puntuación que cierra un párrafo/frase.
TERM = tuple(list('.!?…:»”")') + ["—", "*"])
# Con qué caracteres empieza un párrafo NUEVO (mayúscula, raya de diálogo, etc.)
NEWSTART = re.compile(r'^[«"“¿¡—–(0-9A-ZÁÉÍÓÚÜÑ]')

# ---------------------------------------------------------------------------
# Detección de corrupción a nivel de palabra (letras barajadas / espacios perdidos)
# ---------------------------------------------------------------------------
_ALLCAPS_OK = {  # rótulos estructurales legítimos en mayúsculas
    "LIBRO",
    "PRIMERO",
    "SEGUNDO",
    "TERCERO",
    "PRÓLOGO",
    "PRIMERA",
    "SEGUNDA",
    "TERCERA",
    "PARTE",
    "ATLAS",
    "VOCES",
    "DEL",
    "LAS",
    "DE",
    "FIN",
}
_ROMAN = re.compile(r"^[IVXLCDM]+$")


def is_corrupt_token(tok):
    """Heurística conservadora para señalar (no corregir) tokens dañados."""
    if tok in _ALLCAPS_OK or _ROMAN.match(tok):
        return False
    core = tok.strip(".,;:¿?¡!—«»\"'()")
    if len(core) < 4:
        return False
    # (a) mayúscula intercalada (indicio de runs barajados: abiEesrttaab, vidDaa)
    if any(c.isupper() for c in core[1:]) and not core.isupper():
        return True
    # (b) 4+ consonantes seguidas (rarísimo en español correcto)
    if re.search(r"[bcdfghjklmnpqrstvwxyzñ]{5,}", core.lower()):
        return True
    # (c) aglutinaciones larguísimas sin espacio (>=15 letras minúsculas)
    if len(core) >= 15 and core[0].islower() and core.isalpha():
        return True
    return False


# Conjunto curado de tokens dañados detectados en la auditoría (respaldo del
# detector heurístico, para el manuscrito actual).  Con un manuscrito limpio,
# este conjunto simplemente no se activa.
KNOWN_CORRUPT = {
    "Yaloleí",
    "Yomereí",
    "Yomecallé",
    "Yomedetuve",
    "Yolamiré",
    "Yosalté",
    "Yotampoco",
    "Yosabíaperfectamenteloqueganaba",
    "Teníarazón",
    "Volveríaahacerlo",
    "Vacíauna",
    "Todoslosjueves",
    "DonTuliosequedópensando",
    "conelsombreroenlasmanos",
    "Ledijeolvídaloamiesposaparanotenerque",
    "quélindo",
    "mirepues",
    "esoque",
    "elarchivo",
    "loscuadernos",
    "reaszótrna",
    "mesecnritbiríad",
    "comnienngtúanrio",
    "quNeollalosréd",
    "ceosntatasrehñaosrtaa",
    "edsótnádleocllae",
    "rersatacabdaoe",
    "deHscaoynmocuicdhoa",
    "pSiagruaee",
    "tenEesro",
    "enormDee",
    "vidDaa",
    "YquAeqrueirl",
    "QYuméi",
    "abiEesrttaab",
    "cosLaas",
    "disYtindteos",
    "enaTmenogroamtroesin",
    "esAtheolribarsoé",
    "maDneo",
    "nLsoióqnu",
    "nadYayomnáos",
    "nYioñallesgaalíbaapaeilnaas",
    "vAollavsíad",
    "despuós",
    "ELos",
    "bídecirle",
}


def flag_corrupt(text):
    return any(
        (is_corrupt_token(t) or t in KNOWN_CORRUPT)
        for t in re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", text)
    )


# ---------------------------------------------------------------------------
# Extracción de runs -> HTML con cursivas preservadas y coalescidas
# ---------------------------------------------------------------------------
def runs_html(p):
    parts = []
    cur_ital = None
    buf = []

    def flush():
        if not buf:
            return
        txt = _html.escape("".join(buf))
        parts.append(f"<em>{txt}</em>" if cur_ital else txt)

    for r in p.runs:
        if not r.text:
            continue
        ital = bool(r.italic)
        if ital != cur_ital:
            flush()
            buf = []
            cur_ital = ital
        buf.append(r.text)
    flush()
    out = "".join(parts) if parts else _html.escape(p.text)
    # coalescer cursivas adyacentes fragmentadas
    out = re.sub(r"</em>(\s*)<em>", r"\1", out)
    return out


# ---------------------------------------------------------------------------
# Reconstrucción de párrafos a partir de fragmentos de línea
# ---------------------------------------------------------------------------
def _dehyphenate(s, log):
    # guiones internos de palabra (des-pués -> después)
    def repl(m):
        log.append(("dehyphen", m.group(0), m.group(1) + m.group(2)))
        return m.group(1) + m.group(2)

    return re.sub(r"([a-záéíóúüñ])-([a-záéíóúüñ])", repl, s)


def reconstruct(fragments, log):
    """fragments: lista de (texto_plano, html) o None para blanco.
    Devuelve lista de párrafos (html) y marcas de salto de escena."""
    out = []  # items: ("para", html) | ("scene",)
    buf_txt = ""
    buf_html = ""
    pending_scene = False

    def ends_term(t):
        t = t.rstrip()
        return t.endswith(TERM) if t else True

    def flush():
        nonlocal buf_txt, buf_html
        if buf_txt.strip():
            out.append(("para", buf_html.strip()))
        buf_txt = ""
        buf_html = ""

    def add_scene():
        # sólo saltos de escena ENTRE párrafos: nunca al inicio, ni dobles
        if out and out[-1][0] == "para":
            out.append(("scene",))

    for frag in fragments:
        if frag is None:  # línea en blanco
            if buf_txt and not ends_term(buf_txt):
                # blanco espurio DENTRO de una frase -> ignorar
                log.append(("drop_blank", buf_txt[-30:], ""))
                continue
            flush()
            pending_scene = True
            continue

        ptxt, phtml = frag
        if not buf_txt:
            if pending_scene:
                add_scene()
                pending_scene = False
            buf_txt, buf_html = ptxt, phtml
            continue

        # ¿nuevo párrafo o continuación?
        start_new = ends_term(buf_txt) and bool(NEWSTART.match(ptxt.lstrip()))
        if start_new:
            flush()
            if pending_scene:
                add_scene()
                pending_scene = False
            buf_txt, buf_html = ptxt, phtml
        else:
            # continuación: unir. ¿guion de partición?
            if buf_txt.rstrip().endswith("-") and not buf_txt.rstrip().endswith("--"):
                # quitar guion y unir sin espacio
                buf_txt = buf_txt.rstrip()[:-1] + ptxt.lstrip()
                buf_html = re.sub(r"-\s*$", "", buf_html.rstrip()) + phtml.lstrip()
                log.append(("join_hyphen", ptxt[:20], ""))
            else:
                buf_txt = buf_txt.rstrip() + " " + ptxt.lstrip()
                buf_html = buf_html.rstrip() + " " + phtml.lstrip()
            pending_scene = False
    flush()

    # de-hyphenación interna de palabra en cada párrafo final
    final = []
    for item in out:
        if item[0] == "para":
            final.append(("para", _dehyphenate(item[1], log)))
        else:
            final.append(item)
    return final


# ---------------------------------------------------------------------------
# Clasificación estructural del documento completo
# ---------------------------------------------------------------------------
CHAP_RE = re.compile(r"^Cap[íi]tulo\s+(\d+)\s*[—\-–]\s*(.+)$")
PART_RE = re.compile(r"^(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA)\s*PARTE$")


def parse():
    d = docx.Document(DOCX)
    ps = d.paragraphs
    log = []
    corrupt = []  # (loc, token)

    # localizar corrupción por índice de párrafo (para el informe)
    for i, p in enumerate(ps):
        for tok in re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", p.text):
            if is_corrupt_token(tok) or tok in KNOWN_CORRUPT:
                corrupt.append((i, tok))

    blocks = []
    i = 0
    n = len(ps)

    def nexttext(j):
        while j < n and not ps[j].text.strip():
            j += 1
        return (ps[j].text.strip() if j < n else ""), j

    # --- recorrido principal ---
    section_frags = []

    def flush_section():
        nonlocal section_frags
        if section_frags:
            for kind, *rest in reconstruct(section_frags, log):
                if kind == "para":
                    blocks.append({"type": "para", "html": rest[0]})
                else:
                    blocks.append({"type": "scene"})
            section_frags = []

    i = 53  # saltar dedicatoria y epígrafe originales (se rediseñan aparte);
    # el epígrafe se inserta manualmente en el maquetador.
    # Insertar apertura de libro
    blocks.append(
        {
            "type": "book_open",
            "label": "LIBRO PRIMERO",
            "subtitle": "Las voces que nacieron del fuego",
        }
    )

    while i < n:
        p = ps[i]
        st = p.style.name
        t = p.text.strip()
        if not t and st != "Heading 3":
            section_frags.append(None)
            i += 1
            continue

        if st == "Heading 2" and t == "PRÓLOGO":
            flush_section()
            sub, j = nexttext(i + 1)
            blocks.append({"type": "prologue_open", "label": "PRÓLOGO", "title": sub})
            i = j + 1
            continue
        if st == "Heading 1" and PART_RE.match(t.replace("SEGUNDAPARTE", "SEGUNDA PARTE")):
            flush_section()
            label = t.replace("SEGUNDAPARTE", "SEGUNDA PARTE")
            blocks.append({"type": "part_open", "label": label})
            i += 1
            continue
        m = CHAP_RE.match(t)
        if st == "Heading 2" and m:
            flush_section()
            blocks.append(
                {"type": "chapter_open", "num": int(m.group(1)), "title": m.group(2).strip()}
            )
            i += 1
            continue
        if st == "Heading 3":
            # secciones especiales del cierre o entradas de diario
            if t in ("ATLAS DE LAS VOCES",):
                flush_section()
                blocks.append({"type": "special_head", "text": t})
                i += 1
                continue
            if t.startswith("FIN DEL LIBRO"):
                flush_section()
                teaser, j = nexttext(i + 1)
                blocks.append({"type": "end_matter", "text": t, "teaser": teaser})
                i = j + 1
                continue
            # resto de Heading 3 -> entrada de diario/inserto
            flush_section()
            blocks.append({"type": "diary", "html": runs_html(p)})
            i += 1
            continue
        if st == "Title":
            # ya insertamos la apertura de libro manualmente
            i += 1
            continue

        # cuerpo / onomatopeyas
        if st in ("Body Text", "Normal"):
            # onomatopeya aislada tipo «Rrrrip.» (Normal, corta, sola)
            section_frags.append((t, runs_html(p)))
            i += 1
            continue
        i += 1

    flush_section()
    return blocks, log, corrupt


if __name__ == "__main__":
    blocks, log, corrupt = parse()
    from collections import Counter

    print("BLOQUES:", len(blocks))
    print("Tipos:", dict(Counter(b["type"] for b in blocks)))
    print("Reparaciones mecánicas:", dict(Counter(x[0] for x in log)))
    print(
        "Tokens de corrupción catalogados (ocurrencias):",
        len(corrupt),
        "| distintos:",
        len(set(t for _, t in corrupt)),
    )
    # muestra
    print("\n--- primeros bloques ---")
    for b in blocks[:12]:
        if b["type"] == "para":
            print(f"  para: {re.sub('<[^>]+>', '', b['html'])[:80]}")
        else:
            print(" ", b)
    if os.environ.get("DUMP"):
        json.dump(
            blocks, open(os.path.join(ROOT, "src", "book.json"), "w"), ensure_ascii=False, indent=1
        )
