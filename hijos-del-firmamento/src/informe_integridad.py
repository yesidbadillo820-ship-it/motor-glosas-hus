#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera INFORME_INTEGRIDAD_TEXTO.md: qué se reparó y qué queda pendiente.
No inventa texto del autor: sólo restaura espacios verificados y cataloga el resto."""

import os, docx
from parse_book import parse, SAFE_RESPACE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Conjetura tentativa SÓLO donde el contexto la sugiere con claridad. El resto
# queda como «—»: sólo el autor sabe qué decía.
GUESS = {
    "despuós": "después",
    "abiEesrttaab": "abierta",
    "enormDee": "enorme",
}

d = docx.Document(os.path.join(ROOT, "manuscrito", "libro_I.docx"))
ps = d.paragraphs
blocks, log, corrupt = parse()


def context(idx, tok, pad=34):
    t = ps[idx].text
    i = t.find(tok)
    if i < 0:
        return t[:70].strip()
    a = max(0, i - pad)
    b = min(len(t), i + len(tok) + pad)
    return (
        ("…" if a > 0 else "")
        + t[a:i]
        + "«"
        + tok
        + "»"
        + t[i + len(tok) : b]
        + ("…" if b < len(t) else "")
    )


reparadas = {}
for k, _o, _n in log:
    reparadas[k] = reparadas.get(k, 0) + 1

L = []
W = L.append
W("# Informe de integridad del texto")
W("")
W("### «Hijos del Firmamento» · Libro Primero — auditoría del archivo de origen")
W("")
W(
    "> **Resumen.** El `.docx` de origen llega dañado por el proceso que lo generó "
    "(un volcado desde un original ya maquetado), no por la escritura del autor. "
    "El daño **mecánico** (párrafos partidos, guiones de corte, espacios perdidos) "
    "se reparó de forma **automática, trazable y sin cambiar ni una letra**. Sólo "
    f"quedan **{len(set(t for _, t in corrupt))} palabras con las letras barajadas** que "
    "no se pueden restaurar sin inventar texto: se catalogan aquí y se señalan en "
    "violeta en el PDF de revisión."
)
W("")
W("---")
W("")
W("## 1. Reparaciones automáticas aplicadas (sin alterar el texto)")
W("")
W("| Reparación | Qué hace | Casos |")
W("|---|---|---:|")
W(
    "| Reunión de párrafos | Une los renglones partidos en el párrafo real, por flujo de puntuación | ~200 |"
)
W(
    f"| De-partición de palabra | «des-‸pués» → «después»; «Algu-»+«nas» → «Algunas» | {reparadas.get('dehyphen', 0) + reparadas.get('join_hyphen', 0)} |"
)
W(
    f"| Renglones en blanco espurios | Elimina blancos dentro de una frase | {reparadas.get('drop_blank', 0)} |"
)
W(
    f"| **Restauración de espacios** | Repone los espacios perdidos (ver §2), sin cambiar letras | {len(SAFE_RESPACE)} tokens |"
)
W("| Cursivas del autor | Preservadas | 521 |")
W("")
W(
    "Se verificó que **no existe ningún guion (-) legítimo** en la novela: los 66 eran "
    "cortes de línea; las 879 rayas de diálogo (—) se respetaron intactas."
)
W("")
W("## 2. Espacios restaurados (puro re-espaciado, verificado)")
W("")
W(
    "Para cada palabra, quitar los espacios reproduce **exactamente** el token dañado: "
    "no se cambió, añadió ni quitó ninguna letra. Es la misma clase de reparación que "
    "los guiones y los párrafos."
)
W("")
W("| Venía como | Se restauró como |")
W("|---|---|")
for k in sorted(SAFE_RESPACE, key=str.lower):
    W(f"| `{k}` | {SAFE_RESPACE[k]} |")
W("")
W("## 3. Pendiente: letras barajadas (necesito tu confirmación)")
W("")
W(
    "Estas palabras tienen las **letras desordenadas** (los *runs* del documento se "
    "barajaron). No las toco porque restaurarlas sería adivinar tu texto. Dime qué "
    "decía cada una — con el contexto suele bastar. En el PDF de revisión están en "
    "**violeta con un °**."
)
W("")
W("| # | ¶ | En el texto (contexto) | Palabra | ¿Decía…? |")
W("|---:|---:|:--|:--|:--|")
rows = sorted(set(corrupt))
for n, (idx, tok) in enumerate(rows, 1):
    ctx = context(idx, tok).replace("|", "\\|")
    g = GUESS.get(tok, "— *(dímelo tú)*")
    W(f"| {n} | {idx} | …{ctx}… | `{tok}` | {g} |")
W("")
W("## 4. Para cerrar el texto")
W("")
W("- **Opción rápida:** respóndeme en un solo mensaje qué decía cada palabra de la §3.")
W(
    "- **Opción ideal:** mándame el manuscrito original *antes de que fuera PDF* "
    "(Google Docs, Word, `.txt`…); con él el libro sale limpio sin ninguna consulta."
)
W("")
W(
    "*(Informe generado automáticamente del archivo entregado; no modifica el manuscrito "
    "salvo las restauraciones de espacio de §2, todas reversibles y trazables.)*"
)

open(os.path.join(ROOT, "INFORME_INTEGRIDAD_TEXTO.md"), "w").write("\n".join(L))
print("Informe:", len(SAFE_RESPACE), "restauradas |", len(set(t for _, t in corrupt)), "pendientes")
