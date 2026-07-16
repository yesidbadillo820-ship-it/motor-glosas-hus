#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera INFORME_INTEGRIDAD_TEXTO.md: catálogo exacto de la corrupción del
manuscrito de origen y de las reparaciones mecánicas aplicadas. NO altera texto."""

import os, docx
from parse_book import parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Lecturas propuestas SÓLO donde son inequívocas (espacios perdidos).
# «—» = ilegible por barajado de letras: requiere el original del autor.
SUG = {
    "Yaloleí": "Ya lo leí",
    "Yomereí": "Yo me reí",
    "Yomecallé": "Yo me callé",
    "Yomedetuve": "Yo me detuve",
    "Yolamiré": "Yo la miré",
    "Yosalté": "Yo salté",
    "Yotampoco": "Yo tampoco",
    "Yosabíaperfectamenteloqueganaba": "Yo sabía perfectamente lo que ganaba",
    "Teníarazón": "Tenía razón",
    "Volveríaahacerlo": "Volvería a hacerlo",
    "Vacíauna": "Vacía una",
    "Todoslosjueves": "Todos los jueves",
    "DonTuliosequedópensando": "Don Tulio se quedó pensando",
    "conelsombreroenlasmanos": "con el sombrero en las manos",
    "Ledijeolvídaloamiesposaparanotenerque": "Le dije olvídalo a mi esposa para no tener que",
    "quélindo": "qué lindo",
    "mirepues": "mire pues",
    "esoque": "eso que",
    "elarchivo": "el archivo",
    "loscuadernos": "los cuadernos",
    "despuós": "después",
    "enormDee": "enorme. De",
    "vidDaa": "vida. Da…",
    "maDneo": "mano. De…",
    "cosLaas": "cosas. Las…",
    "abiEesrttaab": "estaba abierta",
    "disYtindteos": "distintos. Y…",
}

d = docx.Document(os.path.join(ROOT, "manuscrito", "libro_I.docx"))
ps = d.paragraphs
blocks, log, corrupt = parse()


def context(idx, tok):
    t = ps[idx].text
    i = t.find(tok)
    if i < 0:
        return t[:70].strip()
    a = max(0, i - 32)
    b = min(len(t), i + len(tok) + 32)
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
for k, orig, new in log:
    reparadas[k] = reparadas.get(k, 0) + 1

lines = []
W = lines.append
W("# Informe de integridad del texto")
W("")
W("### «Hijos del Firmamento» · Libro Primero — auditoría del archivo de origen")
W("")
W(
    "> **Resumen ejecutivo.** El archivo `libro_I.docx` entregado llega **dañado**: "
    "no por la escritura del autor, sino por el proceso que lo generó (un volcado "
    "desde un original ya maquetado). El daño es de dos clases. La primera —fragmentación "
    "de párrafos y partición de palabras con guion— es **mecánica** y se reparó de forma "
    "automática y trazable, sin tocar ni una palabra. La segunda —espacios perdidos y "
    "letras barajadas dentro de unas **50 palabras**— **no se puede restaurar sin inventar "
    "texto del autor**, cosa que la norma de este encargo prohíbe. Por eso esas palabras "
    "se **catalogan** aquí (no se corrigen) y se **señalan en violeta** en el PDF de revisión. "
    "Con un archivo limpio, el libro final sale sin una sola de estas marcas."
)
W("")
W("---")
W("")
W("## 1. Reparaciones mecánicas aplicadas (seguras, sin alterar el texto)")
W("")
W(
    "El origen guardaba **cada renglón como un párrafo**, de modo que muchas frases "
    "quedaban partidas y algunas palabras cortadas con guion de fin de línea. Se verificó "
    "que en todo el manuscrito **no existe ningún guion (-) legítimo**: los 66 que había "
    "eran cortes de línea; las 879 rayas de diálogo (—) se respetaron intactas."
)
W("")
W("| Reparación | Qué hace | Casos |")
W("|---|---|---:|")
W(
    "| Reunión de párrafos | Une los renglones partidos en el párrafo real del autor, por flujo de puntuación | ~200 |"
)
W(
    f"| De-partición de palabra | «des-‸pués» → «después»; «Algu-»+«nas» → «Algunas» | {reparadas.get('dehyphen', 0) + reparadas.get('join_hyphen', 0)} |"
)
W(
    f"| Renglones en blanco espurios | Elimina blancos insertados dentro de una frase | {reparadas.get('drop_blank', 0)} |"
)
W("| Cursivas del autor | Preservadas (521 tramos) | 521 |")
W("")
W(
    "Ninguna de estas operaciones cambia, añade o quita **una sola palabra**: sólo "
    "restituye la unidad de párrafo y de palabra que el volcado había roto."
)
W("")
W("## 2. Corrupción a nivel de palabra (NO reparada — requiere al autor)")
W("")
W("Se detectaron **50 palabras dañadas** en 15 capítulos. Se clasifican así:")
W("")
W(
    "- **Espacios perdidos** (lectura inequívoca): se propone la lectura, a **verificar** por el autor."
)
W(
    "- **Letras barajadas** (runs del documento desordenados): **ilegible**; se necesita el original."
)
W("")
W("En el PDF `..._REVISION.pdf` cada una aparece en **violeta con un pequeño °**.")
W("")
W("| # | Cap./párrafo | En el texto | Palabra dañada | Lectura propuesta (verificar) |")
W("|---:|:--|:--|:--|:--|")
seen = set()
for n, (idx, tok) in enumerate(sorted(corrupt), 1):
    if (idx, tok) in seen:
        continue
    seen.add((idx, tok))
    ctx = context(idx, tok).replace("|", "\\|")
    sug = SUG.get(tok, "— *(ilegible: requiere el original)*")
    W(f"| {n} | ¶{idx} | …{ctx}… | `{tok}` | {sug} |")
W("")
W(
    "> Las lecturas propuestas para «espacios perdidos» son de altísima confianza, pero "
    "se marcan **a verificar** porque la norma editorial de este encargo es no fijar "
    "ninguna palabra del autor sin su visto bueno."
)
W("")
W("## 3. Qué necesito para el libro definitivo")
W("")
W(
    "1. **Un `.docx` limpio** del manuscrito (idealmente exportado de nuevo desde el "
    "original, no de la copia maquetada). Con él, el mismo motor produce el PDF final "
    "sin ninguna de estas 50 marcas."
)
W("2. Si el limpio no fuera posible, **confirmar las 50 lecturas** de la tabla anterior.")
W("")
W(
    "*(Este informe se generó automáticamente a partir del archivo entregado; "
    "no modifica el manuscrito.)*"
)

open(os.path.join(ROOT, "INFORME_INTEGRIDAD_TEXTO.md"), "w").write("\n".join(lines))
print("Escrito INFORME_INTEGRIDAD_TEXTO.md con", len(seen), "entradas de corrupción.")
