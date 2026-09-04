# Análisis de velas japonesas — guía

Detecta los **28 patrones** del libro de Luis M. González sobre el histórico de
precios que usted exporte, y —lo que de verdad importa— **mide si cumplen lo
que el libro promete**.

Vive en `mercados/`. Es un módulo **independiente**: no importa nada de `app/`
ni de `tools/` y solo usa la librería estándar de Python 3.11.

---

## Lo primero: qué hace y qué NO hace

| Sí | No |
|---|---|
| Encuentra los 28 patrones en su histórico | **No predice precios** |
| Explica qué dice el libro de cada uno, con su página | **No dice cuándo comprar ni cuándo vender** |
| Mide qué pasó de verdad después de cada aparición | **No es asesoría de inversión** |
| Dice cuándo la muestra no alcanza para concluir nada | |

Nada en el libro —ni en la evidencia pública sobre velas japonesas— sostiene
que un patrón por sí solo prediga el precio. Construir un generador de señales
sería inventar, que es justo lo que las reglas de este repositorio prohíben.

---

## 1. Sacar el histórico

Exporte el CSV desde su bróker o desde TradingView. Se aceptan:

- **Cabeceras** en español o inglés: `Fecha/Date`, `Apertura/Open`,
  `Máximo/High`, `Mínimo/Low`, `Cierre/Close`, `Volumen/Volume`.
- **Separador** coma, punto y coma o tabulador (Excel en español usa `;`).
- **Decimales** con punto o con coma: `1.234,56` y `1,234.56` entran igual.
- **Orden** de nuevo a viejo o al revés: se reordena solo.

Si falta una columna, el programa dice **cuál** y muestra la cabecera que
encontró, en vez de fallar sin explicación.

> **Cuántos datos hacen falta:** con menos de 60 sesiones no se mide nada
> serio, y para que un patrón llegue a las **30 apariciones** que hacen falta
> para concluir algo, normalmente se necesitan **varios años** de sesiones
> diarias.

## 2. Los comandos

```bash
python -m mercados patrones                 # los 28, con lo que promete el libro
python -m mercados ficha martillo           # una ficha completa
python -m mercados revisar                  # valida el catálogo contra los detectores
python -m mercados detectar historico.csv   # qué patrones hay ahí
python -m mercados medir historico.csv      # ¿cumplen lo que prometen?
python -m mercados exportar historico.csv   # genera la aplicación del celular
```

`medir` acepta `--sesiones 1|3|5|10`: a cuántas sesiones vista comparar.

## 3. Cómo se lee la medición

Esta es la parte que hay que entender bien; sin ella los números engañan.

| Columna | Qué es |
|---|---|
| **Casos** | Cuántas veces apareció el patrón. Por debajo de **30** no se concluye nada. |
| **Acierta** | Qué porcentaje de esas veces el precio fue hacia donde el libro dice. |
| **Base** | Cuántas veces fue en esa dirección **en todas las sesiones**, patrón o no. |
| **Ventaja** | Acierta − base. **Esta es la cifra que importa.** |
| **Margen** | El intervalo de confianza. Si abarca la base, el patrón no se distingue del azar. |

**Por qué la base lo cambia todo.** Si el precio sube el 54 % de los días de
todos modos, un patrón alcista que «acierta el 55 %» no está diciendo nada.
Sin esa comparación, en un mercado que viene subiendo *todos* los patrones
alcistas parecen funcionar. Ese es el error clásico del análisis técnico
casero, y aquí no se comete.

### La corrección que evita hallazgos falsos

Se miden 28 patrones contra 4 horizontes: **112 preguntas de una sentada**. Con
el 95 % de confianza de siempre, **una de cada veinte da «significativo» por
pura casualidad** — unas seis de esas 112 iban a parecer buenas aunque los
patrones no sirvieran para nada.

Se comprobó: con datos **completamente aleatorios**, sin corregir salían
«hallazgos» (un patrón acertando 19 puntos por encima de su base sobre 37
casos). Con la corrección de Bonferroni aplicada, **ninguno**.

Por eso los márgenes salen anchos. No es pesimismo: es que preguntar muchas
cosas a la vez da menos derecho a creerse cada respuesta.

## 4. La aplicación del celular

```bash
python -m mercados exportar historico.csv --titulo "ECOPETROL"
```

Genera `static/mercados/` con cuatro pantallas —Resumen, Patrones, Medición e
Histórico—, instalable y funcional sin internet. Para abrirla desde el celular,
con el servidor del motor levantado:

```
<la dirección con la que entra al Motor de Glosas>/static/mercados/index.html
```

Todo lo que la pantalla muestra **se calcula en Python** y se inyecta como
datos; la aplicación solo dibuja. Si el detector estuviera además escrito en
JavaScript, tarde o temprano las dos versiones dirían cosas distintas y nadie
sabría cuál creer.

### Por qué las velas se dibujan huecas y llenas

El verde y el rojo **fallan la prueba de daltonismo**: el validador de gráficas
mide ΔE 4,1 entre los dos en visión deutan, muy por debajo del mínimo de 8. Así
que el color no lleva el significado:

- **hueca** = la sesión cerró subiendo
- **llena** = la sesión cerró bajando
- **▲ / ▼** acompañan a la palabra en cada etiqueta de dirección

Es además la forma original japonesa —el propio libro dice «verde (o blanca)» y
«roja (o negra)»—, así que lo correcto y lo tradicional coinciden.

Las barras de la medición usan **un solo color**, y la base es una marca de
referencia, no una segunda serie. Lo que no llega a 30 casos sale **rayado**.

---

## 5. Los 28 patrones

| Familia | Patrones |
|---|---|
| **Individuales · reversión** | Doji Libélula, Vela Martillo, Martillo Invertido, Lápida Doji, Hombre Colgado, Estrella Fugaz |
| **Individuales · continuidad** | Marubozu Blanca, Elefante Verde, Marubozu Negra, Elefante Rojo |
| **Individuales · indecisión** | Doji, Peonza |
| **Combinados · alcistas** | Pauta Penetrante, Pauta Envolvente, Tres Soldados Blancos, Harami Alcista, Tres Estrellas en el Sur, Estrella de la Mañana, Bebé Abandonado, Toro 180 |
| **Combinados · bajistas** | Tres Cuervos Negros, Estrella Vespertina, Bebé Abandonado, Cubierta de la Nube Oscura, Harami Bajista, Oso 180 |
| **Combinados · continuidad** | Triple Formación Alcista, Triple Formación Bajista |

**Los patrones neutros (Doji, Peonza) no se miden**: el libro no les atribuye
dirección, así que no hay nada que comprobar. Inventarles una sería inventar.

### Cuándo un patrón no aparece nunca

El **Bebé Abandonado** y la **Triple Formación** exigen huecos completos a
ambos lados. En 18.000 sesiones simuladas no salieron ni una vez. **No están
rotos**: son así de raros. Por eso cada detector tiene además su caso
construido a mano en las pruebas — si la única comprobación fueran datos
reales, un detector roto y uno correcto se verían igual, los dos en cero.

## 6. No se inventa nada

Cada detector implementa la definición que el libro da, **ni más ni menos**.
Cuando la literatura clásica añade una condición que el libro no menciona, no
se agrega a escondidas: se anota con `"revisar"` en
`mercados/catalogo/patrones.json` y sale marcada en pantalla y en la ficha.

Hoy hay una: la **Cubierta de la Nube Oscura**. El libro no exige que la
segunda vela cierre por debajo de la mitad del cuerpo de la primera, condición
que sí pide la literatura clásica. Se implementa lo que dice el libro, y el
aviso queda a la vista.

Las etiquetas de fiabilidad —«muy alta», «baja»— son **afirmaciones del autor**.
El libro no publica ninguna medición que las respalde. El programa las muestra
diciendo de quién son, y ofrece contrastarlas.

---

## 7. Los archivos

| Archivo | Qué hace |
|---|---|
| `mercados/dominio.py` | La vela y sus medidas: cuerpo, mechas, rango, color. Los umbrales. |
| `mercados/patrones.py` | Los 28 detectores y el buscador. |
| `mercados/catalogo/patrones.json` | El texto del libro: cómo identificarlo, significado, página. |
| `mercados/catalogo.py` | Carga y valida ese catálogo contra los detectores. |
| `mercados/datos.py` | Lee el CSV del bróker en cualquiera de sus formatos. |
| `mercados/medicion.py` | La medición contra el histórico, con base y corrección. |
| `mercados/exportar_web.py` | Arma la aplicación: HTML + manifest + service worker + iconos. |
| `mercados/plantilla_web.html` | La aplicación: HTML, CSS y JavaScript. |
| `mercados/cli.py` | `python -m mercados patrones\|ficha\|revisar\|detectar\|medir\|exportar` |

Pruebas: `python -m pytest tests/test_mercados -q` (112).

## Fuente

Luis M. González, *Velas Japonesas: patrones simples y combinados. Significado
e interpretación (nivel principiante e intermedio)* — detrading.org.
Diseño de Carlos Pérez Fiallo.
