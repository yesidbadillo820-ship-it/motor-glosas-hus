#!/usr/bin/env python3
"""Specimen comparativo: EB Garamond (OTF) vs Alegreya con texto real del Prólogo.
Renderiza dos páginas-libro equivalentes para decidir la familia de texto.
"""

import html, os
import docx
from weasyprint import HTML

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def runs_to_html(p):
    out = []
    for r in p.runs:
        t = html.escape(r.text)
        if not t:
            continue
        if r.italic:
            t = f"<em>{t}</em>"
        out.append(t)
    return "".join(out) or html.escape(p.text)


def prologue_paras(n=9):
    d = docx.Document(os.path.join(ROOT, "manuscrito", "libro_I.docx"))
    ps = d.paragraphs
    # PRÓLOGO heading at idx 64, subtitle 'La primera pregunta' ~65, body after
    start = None
    for i, p in enumerate(ps):
        if p.text.strip() == "PRÓLOGO":
            start = i
            break
    collected = []
    for p in ps[start + 1 :]:
        t = p.text.strip()
        if not t:
            continue
        if t == "La primera pregunta":
            continue
        collected.append(runs_to_html(p))
        if len(collected) >= n:
            break
    return collected


PAGE_CSS = """
@page {
  size: 130mm 200mm;
  margin: 22mm 20mm 24mm 22mm;
  @top-center { content: string(rh); font-family: var(--sc); font-size: 7.2pt;
                letter-spacing: 1.6px; color: #6b6b6b; }
  @bottom-center { content: counter(page); font-family: var(--txt);
                   font-feature-settings: "onum" 1; font-size: 9pt; color: #333; }
}
:root { --txt: BODY; --sc: SC; --violet: #4a2f6b; }
html { font-family: var(--txt); }
body { margin:0; }
.rh { string-set: rh "HIJOS DEL FIRMAMENTO"; }
.chaphead { margin-top: 6mm; margin-bottom: 12mm; text-align:center; }
.chaplabel { font-size: 9pt; letter-spacing: 4px; text-transform: uppercase;
             color: var(--violet); }
.rule { width: 26px; height: 0; border:0; border-top: 0.6pt solid var(--violet);
        margin: 8px auto 10px; }
.chaptitle { font-style: italic; font-size: 15pt; color:#1a1a1a; }
p.body { text-align: justify; hyphens: auto; font-size: 10.6pt; line-height: 1.42;
         margin: 0; text-indent: 1.2em; color:#111; }
p.body.first { text-indent: 0; }
p.body.first::first-letter { }
.drop::first-letter {
  font-family: var(--txt); float:left; font-size: 3.05em; line-height: 0.82;
  padding: 0.02em 0.06em 0 0; color: var(--violet); font-weight: 500;
}
.figs { font-feature-settings: "onum" 1; }
em { font-style: italic; }
"""


def render(name, body_family, sc_family, extra_face):
    paras = prologue_paras()
    ps_html = []
    for i, ptext in enumerate(paras):
        cls = "body"
        if i == 0:
            cls += " first drop"
        ps_html.append(f'<p class="{cls}">{ptext}</p>')
    body = "\n".join(ps_html)
    css = extra_face + PAGE_CSS.replace("BODY", body_family).replace("SC", sc_family)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<style>{css}</style></head>
<body><span class="rh"></span>
<div class="chaphead">
  <div class="chaplabel">Pr&oacute;logo</div>
  <hr class="rule">
  <div class="chaptitle">La primera pregunta</div>
</div>
{body}
</body></html>"""
    out = os.path.join(ROOT, "specimen", f"specimen_{name}.pdf")
    HTML(string=doc, base_url=ROOT).write_pdf(out)
    print("wrote", out)
    return out


FACE_EBG = """
@font-face{font-family:EBG;src:url('fonts/ebgaramond/EBGaramond-Regular.otf');font-weight:400;font-style:normal;}
@font-face{font-family:EBG;src:url('fonts/ebgaramond/EBGaramond-Italic.otf');font-weight:400;font-style:italic;}
@font-face{font-family:EBG;src:url('fonts/ebgaramond/EBGaramond-Medium.otf');font-weight:500;font-style:normal;}
@font-face{font-family:EBGSC;src:url('fonts/ebgaramond/EBGaramond-Regular.otf');font-weight:400;}
"""
# For EBG small caps we use the smcp feature via a utility class rather than a separate family.

FACE_ALE = """
@font-face{font-family:ALE;src:url('fonts/alegreya/Alegreya-Regular.ttf');font-weight:400;font-style:normal;}
@font-face{font-family:ALE;src:url('fonts/alegreya/Alegreya-Italic.ttf');font-weight:400;font-style:italic;}
@font-face{font-family:ALE;src:url('fonts/alegreya/Alegreya-Medium.ttf');font-weight:500;font-style:normal;}
@font-face{font-family:ALESC;src:url('fonts/alegreya/AlegreyaSC-Regular.ttf');font-weight:400;}
"""

if __name__ == "__main__":
    render("ebgaramond", "EBG", "EBGSC", FACE_EBG)
    render("alegreya", "ALE", "ALESC", FACE_ALE)
