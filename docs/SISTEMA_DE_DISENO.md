# El sistema de diseño de las tres aplicaciones

ICFES (`icfes/`), noruego (`noruego/`) y velas japonesas (`mercados/`) son tres
programas **independientes** —ninguno importa nada del otro ni del motor— pero
para quien las usa son **tres pantallas del mismo autor**. Este documento
explica cómo se consigue eso sin acoplarlos.

---

## 1. El problema que resolvió

Cada aplicación traía su propio acabado, y se notaba: tres escalas de letra,
tres formas de botón, tres maneras de marcar la pestaña activa. Y las tres
usaban **emoji como juego de iconos** — 40 en el noruego, 15 en el ICFES, 8 en
el de velas.

Los emoji parecen gratis y salen caros:

| | Por qué importa |
|---|---|
| **Cada aparato los dibuja distinto** | El mismo 🔁 no se parece en Android, en iPhone y en el PC del hospital: la pantalla nunca se ve igual dos veces. |
| **No toman el color del texto** | Son imágenes a todo color: no se pueden apagar cuando una fila está bloqueada ni encender cuando está activa. |
| **No se alinean con la letra** | Quedan altos o bajos respecto a la palabra que acompañan. Es el detalle que hace que algo «se vea barato». |

---

## 2. Cómo funciona

### El puente

Cada aplicación conserva **sus propios nombres de color** —`--aurora` en el
noruego, `--marca` en el ICFES, `--acento` en el de velas— y solo los traduce a
los nombres del sistema (`--ds-*`) en su `:root`, arriba, junto a los demás:

```css
--ds-acento:var(--aurora); --ds-acento-hondo:var(--aurora2);
--ds-vidrio:color-mix(in srgb, var(--sup) 78%, transparent);
```

### El sistema

De ahí para abajo, las tres llevan **el mismo bloque de CSS, carácter por
carácter**, al final de su hoja de estilos. Cubre diez cosas:

1. **Tipografía** — una escala fluida con `clamp()`, no tamaños sueltos; y
   `tabular-nums` en toda cifra, para que las columnas de números no tiemblen.
2. **La luz del fondo** — dos degradados suaves arriba de la pantalla.
3. **Superficies** — tres niveles de elevación, no quince.
4. **Interacción** — todo lo que se toca responde; el anillo de foco siempre se ve.
5. **El botón principal** — degradado, sombra de apoyo y hundido al pulsar.
6. **Iconos** — tamaños relativos a la letra que acompañan.
7. **Barra de navegación** — vidrio esmerilado y una pastilla bajo el icono activo.
8. **Avisos y estados vacíos**.
9. **Movimiento** — uno solo, y se apaga entero si el sistema lo pide.
10. **Impresión** — que salga legible en papel.

### Los iconos

Un juego propio de SVG **incrustado en cada archivo** (las tres funcionan sin
internet). Trazo uniforme de 24 px, grosor 1,75, y toman el color de donde se
ponen. Se piden con `ic("casa")`.

Cada aplicación lleva **solo los iconos que usa** — son archivos que viajan al
celular, y un icono que nadie usa es peso muerto.

---

## 3. Las trampas, y las pruebas que las vigilan

`tests/test_diseno/` existe porque cada una de estas ya pasó de verdad:

| Trampa | Qué pasa | Prueba |
|---|---|---|
| **Llamar `ic` a una variable** | `([id,ic,t])` en la barra **tapa** la función `ic()`. La barra sale escribiendo el *nombre* del icono en vez del dibujo. | `test_nadie_tapa_la_funcion_ic` |
| **Levantar el contenido con `position:relative`** para dejarlo encima del fondo | Le **pisa el `position:fixed`** a la barra de abajo: deja de quedarse pegada a la pantalla y se va con el desplazamiento. La luz va detrás con `z-index:-1`. | `test_la_luz_del_fondo_no_le_pisa_la_posicion_a_la_barra` |
| **Pedir un icono que no existe** | **No da error**: deja un hueco en blanco que nadie nota hasta que se abre la pantalla. | `test_todo_icono_que_se_pide_existe` |
| **Arreglar una sola de las tres** | Vuelven a parecer tres productos de tres autores. | `test_las_tres_llevan_el_mismo_sistema_palabra_por_palabra` |
| **Escribir un color después del bloque oscuro** | Se queda sin valor por defecto y la página sale ilegible en claro. | (en `tests/test_icfes/`) |

**Si arregla el sistema en una, va en las tres.** La prueba se pone roja si no.

---

## 4. Accesibilidad: lo que no se negocia

- **Contraste comprobado, no supuesto.** El botón verde del noruego lleva letra
  oscura a propósito: con blanco da 3,5:1 y hace falta 4,5:1; con tinta oscura
  da 5,4:1.
- **El color nunca lleva solo el significado.** En las velas, la sesión que sube
  se dibuja hueca y la que baja llena, con ▲/▼ junto a la palabra: el verde y el
  rojo fallan la prueba de daltonismo (ΔE 4,1 en visión deutan, contra el 8
  mínimo).
- **El foco siempre se ve** (`:focus-visible`, anillo de 3 px).
- **El movimiento se apaga entero** si el sistema lo pide
  (`prefers-reduced-motion`).
- **Objetivos táctiles** de 48–52 px.

---

## 5. Los archivos

| Dónde | Qué |
|---|---|
| `*/plantilla_web.html` | Cada app: su `:root` con el puente, sus piezas propias y el sistema común al final. |
| `tests/test_diseno/test_sistema_comun.py` | Que las tres lleven el mismo sistema y lo traduzcan entero. |
| `tests/test_diseno/test_iconos_de_las_tres.py` | Que no vuelvan los emoji, que todo icono exista y que ninguno sobre. |

Cómo ver el resultado:

```bash
python -m icfes exportar-web            # icfes-app.html
python -m noruego exportar              # static/noruego/
python -m mercados exportar datos.csv   # static/mercados/
```
