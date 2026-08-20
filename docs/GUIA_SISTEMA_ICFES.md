# Sistema de preparación para el ICFES Saber 11

Guía completa del módulo `icfes/`. Está escrita para la persona que va a
estudiar, no para programadores.

---

## 1. Qué es esto

Un sistema para preparar el examen Saber 11 durante un año completo. No es un
banco de preguntas suelto: es el ciclo entero de una preparación seria.

1. **Diagnóstico** — un simulacro dice en qué nivel estás en cada una de las
   cinco áreas.
2. **Plan** — reparte tus horas de la semana según lo que más pesa en el
   puntaje y dónde estás más flojo, y lo distribuye en cuatro fases hasta el
   día del examen.
3. **Práctica diaria** — preguntas con explicación y con el aviso de cuál es
   la trampa de cada una.
4. **Repaso espaciado** — el sistema decide qué te toca repasar cada día para
   que lo de marzo no se te haya olvidado en agosto.
5. **Simulacros cronometrados** — con la estructura y el tiempo reales.
6. **Cuaderno de errores** — agrupa tus fallas por causa: no es lo mismo
   fallar por no saber el tema que por ir de afán.
7. **Proyección** — a qué puntaje vas a llegar si sostienes el ritmo.

Todo funciona **sin internet** y **sin cuentas**. Tus datos no salen de tu
computador.

---

## 2. Las dos formas de usarlo

### A. La aplicación web (la de todos los días)

Es un solo archivo HTML que se abre con doble clic. Sirve en el celular y en
el computador, no necesita internet y guarda tu avance en el navegador.

**En Windows:** doble clic en `tools\ICFES_APP.cmd`. Genera la aplicación en
el Escritorio como `ICFES.html` y la abre. De ahí en adelante, doble clic
directo en `ICFES.html`.

**Desde la consola:**

```bash
python -m icfes exportar-web --salida ICFES.html
```

Para llevarla al celular: manda el archivo `ICFES.html` por WhatsApp o por
cable y ábrelo con el navegador del teléfono.

> **Ojo con los datos.** El avance vive en el navegador donde abriste el
> archivo. Si estudias en el PC, tu avance está en el PC; el celular lleva su
> propia cuenta. En **Ajustes → Descargar mi avance** puedes sacar una copia y
> cargarla en el otro. Si borras los datos de navegación, se pierde.

### B. El programa de consola (para el plan y los informes)

**La forma fácil: doble clic en `tools\ICFES.cmd`.** Abre un menú con todo
(hoy, practicar, repasar, simulacro, progreso, plan) y se para solo en la
carpeta correcta.

> **Si prefieres escribir los comandos, lee esto primero.** `python -m icfes`
> **solo funciona si la consola está parada dentro de la carpeta del
> repositorio.** Si la abres en `C:\Users\tu-usuario` y escribes el comando,
> Python responde `No module named icfes` — no es que el sistema esté dañado,
> es que no está mirando ahí. Empieza siempre con el `cd`:

```bash
# PRIMERO: pararse en la carpeta del repositorio (en el PC de cartera es esta)
cd C:\temp-notas

# Una sola vez: configurar
python -m icfes iniciar --examen 2027-08-08 --meta 400 --horas 12

# Todos los días
python -m icfes hoy                       # qué toca hoy
python -m icfes practicar --area mat -n 10
python -m icfes repaso

# De vez en cuando
python -m icfes simulacro --tipo completo
python -m icfes progreso
python -m icfes plan                      # el plan entero
python -m icfes plan --semana 12          # el detalle de una semana
python -m icfes banco                     # qué hay en el banco
```

Nombres cortos de las áreas: `lc`, `mat`, `soc`, `cn`, `ing`.

Si no sabes dónde quedó el repositorio, entra a la carpeta que creas que es y
escribe `git rev-parse --show-toplevel`: si responde una ruta, esa es; si
responde un error, no es esa carpeta.

El avance de la consola se guarda en `~/.icfes/progreso.db`. Se puede mover
con la variable de entorno `ICFES_DATOS` o con `--datos ruta`.

---

## 3. Cómo es el examen de verdad

Estos datos salen de la Guía de orientación del examen Saber 11 del ICFES y
están en un solo archivo del código (`icfes/dominio.py`): si el ICFES cambia
algo, se cambia ahí y todo el sistema queda actualizado.

| Área | Preguntas | Peso | Sesión 1 | Sesión 2 |
|---|---:|---:|---:|---:|
| Lectura Crítica | 41 | 3 | 41 | — |
| Matemáticas | 50 | 3 | 25 | 25 |
| Sociales y Ciudadanas | 50 | 3 | 25 | 25 |
| Ciencias Naturales | 58 | 3 | 29 | 29 |
| Inglés | 55 | 1 | — | 55 |
| **Total calificable** | **254** | **13** | **120** | **134** |

- El cuadernillo trae **278 preguntas**: las 24 de más son de pilotaje y no dan
  puntaje (el ICFES las usa para calibrar exámenes futuros).
- Son **dos sesiones de 4 horas y 30 minutos** cada una.
- **Lectura Crítica** se responde completa en la primera sesión; **Inglés**
  completo en la segunda.

### El dato que decide la estrategia

| Sesión | Preguntas | Tiempo | Por pregunta |
|---|---:|---:|---:|
| Sesión 1 | 120 | 4 h 30 | **2 min 15 s** |
| Sesión 2 | 134 | 4 h 30 | **2 min 1 s** |

Si te demoras más de eso de forma sostenida, no alcanzas a terminar aunque te
sepas el tema. Por eso todos los simulacros del sistema van con cronómetro.

### Cómo se calcula el puntaje global

Fórmula oficial:

```
Puntaje global = ( 3·LC + 3·MAT + 3·SOC + 3·CN + 1·ING ) / 13 × 5
```

Escala de 0 a 500, sin decimales. **Consecuencia práctica:** un punto en
Lectura Crítica, Matemáticas, Sociales o Ciencias Naturales vale **1,15**
puntos del global; un punto en Inglés vale **0,38**. Un punto de Matemáticas
vale tres veces un punto de Inglés.

Eso no significa abandonar Inglés — el sistema nunca le da menos del 8 % del
tiempo — pero sí que la hora que te sobra casi siempre rinde más en las áreas
de peso 3.

---

## 4. Lo que el sistema NO promete

Tres advertencias que el sistema repite en pantalla, porque prometer de más es
la forma más rápida de que un plan de un año se abandone:

1. **El puntaje por área (0 a 100) es una estimación, no el puntaje del
   ICFES.** El ICFES usa un modelo estadístico que pesa cada pregunta según su
   dificultad real, medida con miles de estudiantes. Aquí se usa una curva
   declarada y editable (`CURVA_PUNTAJE` en `icfes/puntaje.py`). Sirve para
   compararte contigo mismo a lo largo del año, no para anunciar un puntaje.
   El **puntaje global sí es la fórmula oficial exacta**, aplicada a esos
   puntajes estimados.

2. **Las preguntas del banco son de práctica, no del examen real.** Están
   escritas siguiendo la estructura, las competencias y los componentes del
   Saber 11. Los cuadernillos con preguntas oficiales los publica el ICFES
   gratis en su página: úsalos también.

3. **Los simulacros van "a escala".** El banco tiene 110 preguntas y el examen
   real 254, así que un simulacro completo sale más corto, conservando la
   proporción por área y los segundos por pregunta. Entrena el ritmo pero
   **no** entrena el cansancio de las 4 h 30. Para eso hay que hacer, al
   menos, los cuadernillos oficiales completos.

---

## 5. Cómo agregar preguntas al banco

El banco vive en `icfes/banco/`, un archivo JSON por área. Se puede abrir con
cualquier editor de texto.

```json
{
  "id": "MAT-025",
  "competencia": "Argumentación",
  "componente": "Aleatorio",
  "tema": "Probabilidad condicional",
  "dificultad": 3,
  "contexto": "Texto o tabla, si la pregunta la necesita. Puede ir vacío.",
  "enunciado": "La pregunta.",
  "opciones": ["Primera", "Segunda", "Tercera", "Cuarta"],
  "correcta": 2,
  "explicacion": "Por qué esa es la correcta. Mínimo 40 caracteres.",
  "trampa": "Cuál distractor atrae más y por qué."
}
```

Reglas que el sistema verifica solo (`python -m icfes banco`):

- `competencia` y `componente` tienen que existir en esa área.
- Siempre **cuatro** opciones; `correcta` va de 0 a 3 (0 es la primera).
- La explicación no puede estar vacía ni ser demasiado corta.
- **La explicación no puede nombrar letras** ("la opción B"). Las opciones se
  barajan en cada práctica para que no te aprendas la posición, así que una
  letra escrita en la explicación quedaría mentirosa. Nombra el contenido:
  *«el distractor "300 g" sale de…»*.
- Los ids no se pueden repetir.

Después de agregar preguntas, corre `python -m icfes banco`. Si dice
«el banco está bien», ya quedaron.

---

## 6. Cómo está organizado el código

| Archivo | Qué hace |
|---|---|
| `icfes/dominio.py` | Cómo es el examen: áreas, pesos, competencias, tiempos. |
| `icfes/puntaje.py` | Puntaje 0-100 por área y global 0-500. Metas por área. |
| `icfes/banco.py` | Carga, valida, filtra y baraja las preguntas. |
| `icfes/repaso.py` | Repetición espaciada (SM-2), sin programar nada después del examen. |
| `icfes/plan.py` | El plan por fases hasta el día del examen. |
| `icfes/simulacro.py` | Arma y califica simulacros con la estructura real. |
| `icfes/progreso.py` | Dominio, cuaderno de errores, racha y proyección. |
| `icfes/almacen.py` | Guarda todo en un SQLite local. |
| `icfes/fechas.py` | Fechas en español, sin depender del idioma del sistema. |
| `icfes/cli.py` | El programa de consola. |
| `icfes/exportar_web.py` | Genera la app web de un solo archivo. |
| `icfes/plantilla_web.html` | El HTML, CSS y JavaScript de esa app. |

El módulo es **autónomo**: no depende de nada más del repositorio ni de
librerías externas. Solo librería estándar de Python 3.11. Se puede copiar la
carpeta `icfes/` a cualquier computador con Python y funciona.

Pruebas: `python -m pytest tests/test_icfes -q`.

---

## 7. Fuentes

- Guía de orientación del Examen Saber 11.º, ICFES —
  <https://www.icfes.gov.co/evaluaciones-icfes/saber-11/guia-de-orientacion-examen-saber-11/>
- Saber 11 (página oficial, cuadernillos de práctica) —
  <https://www.icfes.gov.co/evaluaciones-icfes/saber-11/>
- Fórmula del puntaje global y ponderaciones 3-3-3-3-1.
- Niveles de desempeño de la prueba de Inglés (Pre-A1, A1, A2, B1), ICFES.

Los fragmentos literarios del banco de Lectura Crítica son de obras
colombianas en dominio público: *María* de Jorge Isaacs (1867), el
*Nocturno III* de José Asunción Silva (1894) y *La vorágine* de José Eustasio
Rivera (1924).
