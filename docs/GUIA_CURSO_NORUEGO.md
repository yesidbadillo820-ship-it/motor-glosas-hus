# Curso de noruego — guía

Aplicación web para aprender **noruego (bokmål)** desde cero, pensada para
hispanohablantes y para usarse desde el celular.

Vive en `noruego/`. Es un módulo **independiente**: no importa nada de `app/`
ni de `tools/` y solo usa la librería estándar de Python 3.11.

---

## 1. Cómo abrirla en el celular

**En Windows: doble clic en `tools\NORUEGO.cmd`.** Genera la aplicación,
**escribe en pantalla el enlace completo** de tu computador y levanta el
servidor. Deja esa ventana abierta.

El enlace se ve así, con el número de tu computador:

```
http://192.168.1.15:8000/static/noruego/index.html
```

> Ese número **cambia en cada computador y en cada wifi**. Copie el que
> muestre su ventana; no escriba el del ejemplo.

Después, en el celular conectado al **mismo wifi**:

1. Abre el navegador y escribe el enlace **tal cual**, en la barra de
   direcciones de arriba. No lo busques en Google.
2. Cuando cargue la aplicación, instálala (ver abajo).
3. Ábrela desde el ícono. A partir de ahí funciona **sin internet**.

### Dónde sale «Agregar a la pantalla de inicio»

Es una opción **del celular**. En el navegador del computador no aparece con
ese nombre.

| Dónde | Qué tocar |
|---|---|
| **Android (Chrome)** | Los **tres puntos** de arriba a la derecha → **«Agregar a la pantalla principal»** o **«Instalar aplicación»**. |
| **iPhone (Safari)** | El botón de **compartir** (el cuadrito con la flecha hacia arriba, abajo en el centro) → **«Añadir a pantalla de inicio»**. |
| **En el computador** | No hace falta: abra `static\noruego\index.html` con doble clic. (En Chrome de escritorio la opción existe, pero se llama **«Instalar página como aplicación…»**, dentro de *Enviar, guardar y compartir*.) |

Si la opción no aparece, es porque **la página no cargó**. Revise que el
celular esté en el mismo wifi y que el enlace esté escrito completo.

### Desde la consola

```bash
python -m noruego exportar      # arma la aplicación
python -m noruego direccion     # imprime el enlace para el celular
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`direccion` averigua la IP con la que este equipo sale a la red y arma el
enlace completo. Si no hay red, no imprime nada y devuelve código 1.

> El archivo también se puede abrir con doble clic (`static/noruego/index.html`).
> Así funciona todo menos la instalación y el guardado sin conexión: los
> navegadores no permiten *service workers* en archivos locales.

---

## 2. Qué trae

| Pantalla | Qué hace |
|---|---|
| **Inicio** | Objetivo del día, racha, XP, nivel, la lección recomendada, el repaso pendiente y los últimos errores. |
| **Curso** | La ruta completa: módulos y lecciones, con desbloqueo progresivo y estrellas por lección. |
| **Repaso** | Las palabras que estás a punto de olvidar. El sistema las elige solo. |
| **Palabras** | Diccionario buscable, gramática explicada y conversaciones. |
| **Perfil** | Estadísticas, logros, ajustes, copia de seguridad y el panel para agregar contenido. |

**Tipos de ejercicio:** elegir respuesta, completar frase, ordenar palabras,
traducir en las dos direcciones, escuchar y elegir, escuchar y escribir, unir
parejas, conjugar verbos, identificar el género, formar el sustantivo,
encontrar el error, completar conversaciones y repetir la pronunciación.

**Gamificación:** XP, niveles de jugador, racha diaria, objetivo diario,
corazones por lección, estrellas, logros y desbloqueo progresivo. Todo apoya el
aprendizaje: los corazones obligan a repetir la lección que no se entendió, y
las estrellas solo llegan a tres cuando no se falla nada.

---

## 3. La ruta del curso

18 módulos y 73 lecciones, de nivel cero a B2:

| Nivel | Módulos |
|---|---|
| **Desde cero** | Primer contacto (sonidos) · Saludos y presentaciones · Personas y el verbo ser |
| **A1** | Sustantivos y géneros · Números y hora · Familia y personas · Verbos y orden de la frase · Comida y restaurante |
| **A2** | La casa · Ciudad y transporte · Compras y dinero · Hablar del pasado · Trabajo · Salud y cuerpo · Clima y naturaleza |
| **B1** | Opiniones y frases largas · Trámites y vida en Noruega |
| **B2** | Noruego profesional |

La estructura llega hasta C2: los niveles están definidos en `dominio.py` y
basta agregar módulos para extenderla.

---

## 4. Lo que este curso no promete

Tres advertencias que la aplicación repite en pantalla:

1. **Las pronunciaciones son aproximaciones para hispanohablantes**, no
   transcripciones del Alfabeto Fonético Internacional. «Hei» se escribe como
   «jei» porque es lo más cercano a un oído español, pero la *h* noruega es un
   soplido suave, no la jota española. Sirven para arrancar; el oído se afina
   escuchando.
2. **El audio usa la voz del propio celular.** Si el aparato no tiene voz
   noruega instalada, la aplicación lo dice y muestra el texto en vez de leerlo
   con acento español, que enseñaría mal. En Android se agrega en
   *Ajustes → Idiomas → Texto a voz*; en iPhone, en *Ajustes → Accesibilidad →
   Contenido hablado → Voces*.
3. **Enseña bokmål**, no nynorsk. Es la forma escrita que usa la gran mayoría
   de los noruegos y la única que se evalúa en la prueba oficial para
   extranjeros.

**Regla del contenido: no se inventa noruego.** Si una palabra, una forma o una
traducción está en duda, se marca con `"revisar": true` en el JSON y el
validador la reporta, en vez de presentarla como un hecho.

---

## 5. Agregar contenido sin tocar código

**Desde la aplicación:** *Perfil → Contenido*. Se agregan palabras, verbos y
frases, quedan guardadas en el dispositivo y entran de inmediato al diccionario
y al repaso. El botón *Exportar* entrega el JSON listo para incorporarlo al
curso oficial.

**En el repositorio:** los datos viven en `noruego/lexico/`, un JSON por tipo.

```json
{
  "id": "s-vindu",
  "no": "vindu",
  "genero": "et",
  "def": "vinduet",
  "plural": "vinduer",
  "defPl": "vinduene",
  "es": "ventana",
  "tema": "casa",
  "nivel": "A1",
  "pron": "VIN-du",
  "nota": ""
}
```

Después de editar, corre `python -m noruego revisar`. El validador verifica que
el género exista, que un neutro haga el definido en `-et`, que un verbo del
grupo 2 haga el pretérito en `-te`, que ninguna palabra quede sin pronunciación
y que ningún id se repita.

**Agregar una lección** es agregar una entrada a `MODULOS` en `curso.py`. Una
lección no lista sus palabras una por una: declara de qué **temas** y de qué
**niveles** salen, y qué reglas de gramática enseña. Así, cuando el léxico
crece, las lecciones crecen solas.

---

## 6. Cómo está hecho

| Archivo | Qué hace |
|---|---|
| `noruego/dominio.py` | Niveles MCER, temas, géneros, grupos verbales, tipos de ejercicio. |
| `noruego/lexico/` | Los datos del idioma en JSON: sustantivos, verbos, adjetivos, frases, números, sonidos, gramática y diálogos. |
| `noruego/lexico.py` | Carga y valida esos datos. |
| `noruego/curso.py` | La ruta: 18 módulos y 73 lecciones. |
| `noruego/ejercicios.py` | Genera los ejercicios a partir de los datos. |
| `noruego/exportar_web.py` | Arma la PWA: HTML + manifest + service worker + iconos. |
| `noruego/plantilla_web.html` | La aplicación: HTML, CSS y JavaScript. |
| `noruego/red.py` | Averigua el enlace con el que el celular alcanza este computador. |
| `noruego/cli.py` | `python -m noruego revisar\|curso\|leccion\|exportar\|direccion` |

**La idea de fondo del motor:** no se escriben ejercicios a mano. Se escribe una
sola vez que «bil» es masculino y que su definido es «bilen», y de ahí salen
solos el ejercicio de género, el de forma, el de traducción, el de escucha y el
de parejas. Agregar una palabra agrega ejercicios a todo el curso.

Pruebas: `python -m pytest tests/test_noruego -q` (193).

---

## 7. Fuentes

- Estructura de niveles del Marco Común Europeo (A1 a C2).
- La prueba oficial de noruego para extranjeros es la **Norskprøven**, que
  evalúa de A1 a B2; el nivel B1 es el que se exige para la ciudadanía noruega
  y B2 el que piden muchas universidades y empleos. La antigua *Bergenstesten*
  ya no se aplica.
- Gramática y morfología del bokmål: formas de género, definido y plural del
  sustantivo, los cuatro grupos verbales regulares y la regla V2.
