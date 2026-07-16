# Manual de estilos editorial
## «Hijos del Firmamento» · Libro Primero — *Las voces que nacieron del fuego*

> Documento de dirección editorial. Registra cada decisión y su porqué, para que
> la edición sea reproducible y coherente en los tres libros de la trilogía.
> Principio rector: **la palabra del autor es intocable; todo lo demás está al
> servicio de que se lea mejor.**

---

## 0. Diagnóstico y criterio

La novela es una confesión en primera persona: un padre archivero que mide el
tiempo, las estrellas y la pérdida a la altura de su hija Dania y su esposa
Daniela. Prosa cálida, exacta, de frase corta y respiración larga. El diseño
persigue **desaparecer**: que nada se interponga entre esa voz y el lector, y que
al abrir el libro se sienta el peso de una edición cuidada, no de un documento.

Referentes de principio (no de copia): Acantilado, Impedimenta, Libros del
Asteroide, Anagrama. De todos ellos se extrae la misma lección: **una sola
familia tipográfica excelente, mucho blanco, un acento mínimo y jerarquías
claras.** La contención es lujo.

---

## 1. Formato y mancha tipográfica

| Parámetro | Valor | Justificación |
|---|---|---|
| Formato | **130 × 200 mm** | Proporción 1:1,54, la «novela» clásica europea (Acantilado/Impedimenta). Íntimo, manejable, elegante. |
| Caja de texto | ~**97 × 158 mm** | Medida de **60–66 caracteres** por línea, el óptimo de legibilidad para lectura inmersiva. |
| Margen interior (lomo) | 19 mm | Mayor que el exterior para compensar la encuadernación (rústica fresada) y que el texto no se hunda en el pliegue. |
| Margen exterior | 16 mm | Aire para el pulgar; respira sin desperdiciar página. |
| Margen superior | 18 mm | Aloja la cornisa. |
| Margen inferior | 19 mm | Aloja el folio; algo mayor que el superior, según canon clásico (el texto «se apoya» arriba). |
| Márgenes espejados | sí | `@page:left` / `@page:right` intercambian interior/exterior: la doble página queda equilibrada hacia el lomo. |

La mancha se sitúa según un canon clásico de proporciones (interior:superior:
exterior:inferior crecientes), la lógica que subyace a Van de Graaf y a la
tradición del libro renacentista.

---

## 2. Tipografía

### 2.1 Elección de familia: **Alegreya** + **Alegreya SC**

Se evaluó **EB Garamond** (grabado completo, con versalitas y cifras
elzevirianas) frente a **Alegreya** componiendo el Prólogo real en ambas
(ver `specimen/`). Se elige **Alegreya**, de Juan Pablo del Peral / Huerta
Tipográfica, por razones técnicas, no de gusto:

1. **Diseñada para narrativa larga en español.** Alegreya nace en una fundición
   argentina para lectura inmersiva; su ritmo, sus acentos, la ñ y los signos
   `¿ ¡` son nativos, no adaptaciones de una fuente pensada para otro idioma.
2. **Mancha más robusta.** Mayor altura de x y color de página más firme: se lee
   con menos fatiga y **aguanta mejor la impresión offset** (la ganancia de punto
   no la adelgaza). EB Garamond, más delicado, tiende a verse anémico en papel
   ahuesado barato.
3. **Cursiva de autor.** Alegreya tiene una de las mejores cursivas libres: viva,
   pareja, ideal para los 521 tramos en cursiva del manuscrito.
4. **Sistema completo de una sola familia.** Alegreya + **Alegreya SC**
   (versalitas verdaderas, no falseadas) cubren cuerpo, énfasis, versalitas y
   titulares sin mezclar ADN tipográfico. Una familia, explotada a fondo: la vía
   más elegante y más «editorial».
5. **Cifras elzevirianas por defecto.** Los números viejo-estilo (que suben y
   bajan como las minúsculas) son el estándar de la tipografía de libro fino; en
   Alegreya son el glifo por defecto, ideal para folios y fechas.

EB Garamond queda documentada y disponible en `fonts/ebgaramond/` como
alternativa clásica, por si en algún momento se prefiere ese carácter más austero.

### 2.2 Jerarquía y tamaños

| Elemento | Fuente | Cuerpo | Tratamiento |
|---|---|---|---|
| Cuerpo | Alegreya Regular | 10,7 pt / 15,9 pt | Justificado, sangría 1,2 em, cifras elzevirianas |
| Énfasis | Alegreya Italic | — | Cursiva del autor, preservada |
| Íncipit de capítulo | Alegreya SC | 10,7 pt | Primeras 3 palabras en versalitas (arranque clásico, sin capitular) |
| Cornisa | Alegreya SC | 7,7 pt | Versalitas, tracking 1,4 px, gris |
| Folio | Alegreya | 9,3 pt | Cifras elzevirianas, gris |
| Número de capítulo | Alegreya Medium | 40 pt | Violeta |
| Romano de parte | Alegreya Medium | 46 pt | Violeta |
| Título de capítulo | Alegreya Italic | 16,5 pt | Negro fuerte |
| Título de portada | Alegreya SC | 33 pt | Versalitas, negro fuerte |

**Íncipit en versalitas, no capitular.** Se descartó la letra capitular: la
versalita de arranque es más sobria, más «Acantilado», y evita el riesgo estético
de la capital que compite con el título. Cada capítulo abre con sus tres primeras
palabras en versalitas: reconocible, elegante, silencioso.

### 2.3 Composición fina

- **Justificación** con partición automática en español (motor de silabación
  Hunspell/Pyphen).
- **Viudas y huérfanas** controladas (`widows:2; orphans:2`): ninguna línea suelta
  al pie ni a la cabeza de una columna.
- **Partición limitada** (`hyphenate-limit-chars: 6 3 2`): no se parten palabras
  de menos de 6 letras ni dejando menos de 3+2; se evita el exceso de guiones y
  los «ríos» de espacios.
- **Ligaduras y kerning** activados; `optimizeLegibility`.

---

## 3. Color

Ver `paleta/PALETA.md`. En síntesis: **negro cálido, gris y un violeta**. El
violeta sólo marca estructura (números, romanos, rótulos, filetes, ornamentos) y
**jamás** el cuerpo. Una página al azar, vista de lejos, es blanco y negro.

---

## 4. Páginas maestras

- **Cornisa (encabezado).** Verso: *Hijos del Firmamento*. Recto: título del
  capítulo o sección. Ambas en versalitas grises, discretas.
- **Supresión automática en aperturas.** En la página donde arranca un capítulo o
  el prólogo, la cornisa **desaparece** (`string(..., first-except)`), como en las
  ediciones de lujo: el gran número respira sin competencia. Reaparece en las
  páginas de continuación.
- **Folio.** Centrado al pie, en cifras elzevirianas. Ausente en preliminares,
  aperturas de libro/parte y páginas de cortesía.
- **Marcadores PDF.** El PDF lleva índice navegable jerárquico
  (Libro › Parte/Prólogo › Capítulo).

---

## 5. Aperturas

- **Libro** (recto, página propia): rótulo «LIBRO PRIMERO» en versalitas violeta,
  el título en grandes versalitas, el subtítulo en cursiva y una estrella. Es el
  umbral de una etapa.
- **Parte** (recto, página propia): romano gigante en violeta, «PRIMERA PARTE» en
  versalitas y la **constelación** (tres estrellas enlazadas). Marca el cambio de
  movimiento.
- **Capítulo / Prólogo**: la mancha «se hunde» ~⅓ de página (aire deliberado),
  rótulo «CAPÍTULO» en versalitas, número grande en violeta, filete finísimo,
  título en cursiva e íncipit en versalitas. Cada capítulo se siente importante.

---

## 6. Preliminares y finales

Secuencia (con disciplina de recto/verso y páginas de cortesía en blanco):
**portadilla → portada interior → página legal → dedicatoria → epígrafe → [novela]
→ colofón de cierre → índice → colofón**.

- **Portadilla** (half-title): sólo el título en versalitas y una estrella.
- **Portada interior**: autor, título en grandes versalitas, filete, «LIBRO
  PRIMERO», subtítulo en cursiva, pie de editorial. Minimalista, mucho blanco.
- **Página legal**: copyright, ISBN, depósito, crédito tipográfico y de licencia,
  alineada abajo, en gris pequeño.
- **Dedicatoria** (nueva, escrita para esta edición): dirigida a la esposa
  **Daniela** y a la hija **Dania** (los nombres del original venían cambiados: ver
  §8). Compuesta en cursiva, alineada a la derecha como un poema, con los nombres
  en versalitas violeta. Evoca la voz del libro (la estrella, el archivo, la luz)
  sin frases hechas.
- **Epígrafe**: el epitafio de las Termópilas elegido por el autor, en cursiva,
  con la fuente en versalitas.
- **Colofón**: nota final centrada que ata el cierre al motivo del libro
  («cuando la luz de estrellas ya apagadas seguía, todavía, llegando»).

---

## 7. Elementos especiales

- **Salto de escena**: una estrella de cuatro puntas centrada, con aire. Motivo
  del firmamento; discreto.
- **Entrada de cuaderno/diario** («Martes. Despejado. Nada.»): inserto en cursiva,
  cuerpo menor, con filete violeta a la izquierda y la fecha en versalitas. Da voz
  visual a los registros diarios del narrador.
- **Atlas de las Voces**: subtítulo interior en versalitas violeta con filete.
- **Onomatopeya** («Rrrrip.»): centrada, en cursiva violeta.

---

## 8. Decisiones tomadas por criterio (no solicitadas explícitamente)

Según la regla final del encargo, se documentan las decisiones adoptadas por
mejorar objetivamente el libro:

1. **Nombres de la dedicatoria corregidos.** El original decía «A mi esposa Dania
   y a mi hija Daniela», pero **la propia novela** establece que **Daniela es la
   esposa** (le muestra Orión, barre el patio) y **Dania la hija** de siete años.
   La nueva dedicatoria usa la asignación correcta, coincidente con las
   instrucciones del encargo.
2. **Reparación mecánica del volcado.** Reunión de párrafos partidos y
   de-partición de palabras cortadas con guion, sin alterar el texto (ver
   `INFORME_INTEGRIDAD_TEXTO.md`).
3. **Normalización de rótulos estructurales.** «SEGUNDAPARTE» → «SEGUNDA PARTE»
   (falta de espacio en el rótulo, no en la novela).
4. **Catálogo de corrupción del origen** en lugar de adivinar palabras del autor:
   50 palabras dañadas se señalan, no se inventan.
5. **Índice navegable y cifras elzevirianas** en folios: refinamientos de edición
   de lujo que el encargo no pedía pero que elevan el resultado.

---

## 9. Producción

Motor: **WeasyPrint** (CSS Paged Media), elegido por dar control tipográfico de
imprenta (cornisas, folios, referencias cruzadas, partición, viudas/huérfanas,
incrustación de fuentes) de forma **reproducible y versionable** en texto plano
—lo contrario de un binario de maquetación cerrado.

```bash
python3 src/build_book.py              # PDF final
REVISION=1 python3 src/build_book.py   # PDF que señala la corrupción del origen
python3 src/rasterize.py <pdf> 150     # prueba a PNG para revisión visual
```

- **Cambiar el violeta**: una línea en `paleta/paleta.css` (ver PALETA.md).
- **Incorporar el manuscrito limpio**: reemplazar `manuscrito/libro_I.docx` y
  recompilar. El parser reconstruye la estructura automáticamente.
- **Fuentes**: Alegreya y Alegreya SC (SIL Open Font License) en `fonts/`.
