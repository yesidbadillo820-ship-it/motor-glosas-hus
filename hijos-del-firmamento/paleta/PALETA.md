# Paleta editorial · «Hijos del Firmamento»

Tres tintas. Ni una más. La contención cromática es la primera señal de una
edición seria: el color grita, el gris y el negro leen.

| Rol | Muestra | HEX | Uso |
|---|---|---|---|
| **Violeta de marca** | 🟣 | `#4a2c6d` | Numerales de capítulo, romanos de parte, rótulos, filetes, ornamentos, detalles. **Nunca** en el cuerpo de texto. |
| Violeta oscuro | 🟪 | `#35204e` | Versalitas pequeñas y subtítulos sobre blanco (mejor contraste). |
| Violeta tenue | ▫️ | `#8f78ad` | Filetes finísimos, filete de la constelación. |
| Violeta niebla | ⬜ | `#efeaf4` | Veladuras y reservas (uso mínimo). |
| **Negro tipográfico** | ⬛ | `#1c1a22` | Cuerpo de texto. Negro **cálido**, con un alma violeta imperceptible; nunca `#000`. |
| Negro fuerte | ⬛ | `#100e16` | Titulares y grandes cuerpos. |
| Gris cornisa | ◾ | `#6d6a74` | Cornisas / encabezados. |
| Gris folio | ◾ | `#4b4954` | Folios. |
| Gris fino | ▫️ | `#b9b6c0` | Filetes neutros, puntos guía del índice. |
| Papel | ⬜ | `#fdfcfb` | Blanco cálido, ahuesado. |

## El violeta es la única variable de marca

La portada ya posee identidad visual; **este violeta es provisional**. Para
adoptar el violeta exacto de la portada basta con muestrearlo (con cualquier
cuentagotas) y sustituir **una sola línea** en `paleta/paleta.css`:

```css
--violeta: #4a2c6d;   /* ← pega aquí el HEX de la portada */
```

Todo el libro —numerales, romanos, filetes, estrellas, colofón— se reafina
solo, porque cada uno de esos elementos hereda de este token. No hay ningún
violeta «quemado» en el resto de los archivos.

## Por qué negro cálido y no negro puro

El `#000` sobre papel ahuesado produce un contraste duro, «digital», que delata
el origen de impresora. Los negros de imprenta literaria son cálidos y
ligeramente desaturados. Nuestro `#1c1a22` lleva una gota del violeta de la
portada: imperceptible como color, pero hace que **toda la página pertenezca a
la misma familia** que el acento. Es el truco silencioso de las buenas ediciones.

## Regla de oro del color

El violeta **jamás** toca el cuerpo del texto. Aparece sólo donde el ojo busca
estructura —números, rótulos, ornamentos— y siempre en pequeña dosis. Una
página abierta al azar debe verse, a un metro de distancia, **en blanco y
negro**; el violeta es un susurro que sólo se nota de cerca.
