# Hijos del Firmamento · Libro Primero — edición editorial

Rediseño editorial completo de la novela *Hijos del Firmamento — Las voces que
nacieron del fuego*, con calidad comparable a las colecciones de narrativa de
Acantilado, Impedimenta o Libros del Asteroide.

**El texto literario es intocable.** Todo el trabajo es de composición,
tipografía, retícula, color y paratextos. Las palabras del autor no se cambian:
donde el archivo de origen llega dañado, se **cataloga** (no se inventa).

---

## Qué hay aquí (entregables)

| Entregable | Ruta |
|---|---|
| **PDF del libro** (maqueta sobre el texto actual) | `pdf/HIJOS_DEL_FIRMAMENTO_Libro_I.pdf` |
| **PDF de revisión** (señala la corrupción del origen en violeta) | `pdf/HIJOS_DEL_FIRMAMENTO_Libro_I_REVISION.pdf` |
| **Documento editable** (HTML, fuente de la maqueta) | `src/libro_editable.html` |
| **Estilos** (hoja de estilo maestra) | `src/estilos.css` |
| **Páginas maestras** (retícula, cornisas, folios) | dentro de `src/estilos.css` (`@page`) |
| **Motor de maquetación** (parser + build) | `src/parse_book.py`, `src/build_book.py` |
| **Paleta de color** | `paleta/paleta.css` · `paleta/PALETA.md` |
| **Recursos gráficos** (ornamentos SVG) | `recursos/` |
| **Manual de estilos** | `MANUAL_DE_ESTILOS.md` |
| **Informe de integridad del texto** | `INFORME_INTEGRIDAD_TEXTO.md` |
| **Comparativa tipográfica y muestrario** | `specimen/` |
| **Tipografías** (Alegreya + Alegreya SC + EB Garamond) | `fonts/` |

---

## Cómo compilar

Requiere Python 3 con `weasyprint`, `python-docx` y `pymupdf`:

```bash
pip install weasyprint python-docx pymupdf pyphen
python3 src/build_book.py               # -> pdf/…_Libro_I.pdf
REVISION=1 python3 src/build_book.py    # -> pdf/…_Libro_I_REVISION.pdf
python3 src/rasterize.py pdf/HIJOS_DEL_FIRMAMENTO_Libro_I.pdf 150   # PNG de prueba
```

---

## Lo que necesito para el libro DEFINITIVO

Este PDF ya es de calidad de imprenta en su diseño, pero hay tres cosas que sólo
tú puedes aportar y que **no se pueden inventar**:

1. **Un `.docx` limpio del manuscrito.** El archivo entregado llega dañado en
   ~50 palabras (espacios perdidos y letras barajadas por el proceso que lo
   generó). Está todo catalogado en `INFORME_INTEGRIDAD_TEXTO.md`. Con un archivo
   limpio, el libro final sale sin una sola marca.
2. **La portada** (imagen), para muestrear su **violeta exacto** y sustituirlo en
   una línea de `paleta/paleta.css`. Mientras tanto se usa un violeta provisional.
3. **Datos de edición**: nombre del **autor**, editorial, ISBN, ciudad, mes de
   impresión. Ahora aparecen como marcadores (`N. N.`, «Nombre de la editorial»…)
   en la portada, la página legal y el colofón.

---

## Estructura del repositorio

```
hijos-del-firmamento/
├─ manuscrito/      libro_I.docx (origen)
├─ src/             parser, maquetador, estilos.css, rasterizador, HTML editable
├─ paleta/          paleta.css (tokens) + PALETA.md
├─ recursos/        estrella.svg, constelacion.svg (ornamentos)
├─ fonts/           alegreya/  ebgaramond/  (OFL)
├─ specimen/        comparativa EB Garamond vs Alegreya + muestrario de páginas
├─ pdf/             PDFs
├─ MANUAL_DE_ESTILOS.md
└─ INFORME_INTEGRIDAD_TEXTO.md
```
