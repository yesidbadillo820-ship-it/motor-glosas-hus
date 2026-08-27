# Documento técnico de entrega — Módulo «Trámite/Acta en consolidados de glosas aceptadas» + Bitácora del proyecto

**Repositorio:** `yesidbadillo820-ship-it/motor-glosas-hus`
**Rama base (default del repo):** `motor-glosas` (⚠️ **no** `main` — ver §13)
**Fecha del documento:** 27 de julio de 2026 · **actualizado:** 27 de agosto de 2026
**Autor de la rama:** sesión de Claude Code (modelo `claude-fable-5` durante el desarrollo; documento redactado en `claude-opus-5`)
**Área usuaria:** Auditoría de Cartera / Glosas — ESE Hospital Universitario de Santander (NIT 900.006.037-4), operación SINAC SC SAS

**Alcance de este documento:** reconstrucción íntegra de todo lo producido en la conversación que originó esta rama. Incluye el código entregado, los entregables ofimáticos generados para el auditor, las decisiones técnicas tomadas, las alternativas descartadas, los hallazgos de datos, los incidentes de CI resueltos y los pendientes. No se omite ningún artefacto, por pequeño que sea.

---

## ⚠️ Estado actual (27-ago-2026) — leer antes que el resto

Este documento se escribió el 27 de julio describiendo el módulo tal como
estaba ese día. **Desde entonces el módulo evolucionó bastante**, a partir de
cuatro rondas de trabajo con el auditor sobre los datos de julio. Lo que
cambió respecto de lo que se lee más abajo:

| Antes (lo que describe este documento) | Ahora |
|---|---|
| Columnas fijas W/X/Y, hoja `BD`, encabezados en fila 4 | **Todo se detecta por el texto del encabezado**: hoja, fila y columnas. Julio venía con hoja `BD VLR ACEPTADO`, encabezados en fila 3 y las columnas corridas a X/Y/Z |
| Conceptos unidos por `" \| "` | **Un párrafo por glosa aceptada**, separados por línea en blanco |
| Conceptos deduplicados (decisión D8) | **Ya NO se deduplican**: dos renglones iguales son dos glosas y agruparlos escondía la plata de uno |
| Entraban las glosas de valor $0 | **Solo entra lo aceptado**. Las levantadas/ratificadas/no aceptadas valen $0 y su texto contradecía a la nota crédito |
| Solo se avisaba si la suma no cuadraba | **Columna nueva de novedad** con dos chequeos: diferencia de plata, y texto del acta descuadrado con su propio valor |
| Solo llenaba filas totalmente vacías | Modo **`--rehacer`** para reprocesar filas de tipo ACTA ya diligenciadas |
| Lector de pesos propio | Usa **`tools/_dinero.py`**, el lector compartido de los bots |

**El Anexo A ya está regenerado con el código actual.** Las secciones §3 y §4
describen el diseño de julio: la arquitectura por capas y la cascada de
resolución siguen siendo válidas, pero los detalles de formato de salida y de
deduplicación hay que leerlos con la tabla de arriba al lado.

---

## Índice

1. [Objetivo del desarrollo](#1-objetivo-del-desarrollo)
2. [Arquitectura](#2-arquitectura)
3. [Funciones implementadas](#3-funciones-implementadas)
4. [Flujo completo](#4-flujo-completo)
5. [Base de datos](#5-base-de-datos)
6. [Backend](#6-backend)
7. [Frontend](#7-frontend)
8. [IA](#8-ia)
9. [Automatizaciones](#9-automatizaciones)
10. [Archivos modificados](#10-archivos-modificados)
11. [Dependencias nuevas](#11-dependencias-nuevas)
12. [Configuración](#12-configuración)
13. [Riesgos](#13-riesgos)
14. [Dependencias con otros módulos](#14-dependencias-con-otros-módulos)
15. [Pendientes](#15-pendientes)
16. [Recomendaciones para fusionarlo](#16-recomendaciones-para-fusionarlo)
17. [Resumen ejecutivo](#17-resumen-ejecutivo)
- [Anexo A — Código fuente completo](#anexo-a--código-fuente-completo-del-módulo)
- [Anexo B — Datos de referencia del cruce (junio 2026)](#anexo-b--datos-de-referencia-del-cruce-junio-2026)
- [Anexo C — Entregables ofimáticos producidos](#anexo-c--entregables-ofimáticos-producidos)
- [Anexo D — Cronología literal de la sesión](#anexo-d--cronología-literal-de-la-sesión)

---

## 1. Objetivo del desarrollo

### 1.1 El problema de negocio

Cada mes, el área de Auditoría de Cartera produce un **consolidado de glosas aceptadas** (archivo `ARCHIVO <MES> <AÑO>-GLOSAS ACEPTADAS.xlsx`, hoja `BD`). Ese archivo lista, fila por fila, cada **nota crédito** emitida por el hospital al aceptar total o parcialmente una glosa de una EPS/aseguradora. Es el documento que sustenta contablemente por qué se rebajó valor de una factura.

Tres columnas de ese consolidado deben quedar diligenciadas para que la nota crédito sea auditable:

| Columna | Encabezado literal | Qué debe contener |
|---|---|---|
| **W** | `RESPUESTA TRAMITE GLOSA Y/O ACTA` | El texto unificado de la respuesta/acuerdo que dio origen a la aceptación |
| **X** | `NO DE TRAMITE Y/O ACTA` | El número del trámite de objeción o del acta de conciliación |
| **Y** | `FECHA DE TRAMITE Y/O ACTA` | La fecha de ese trámite o de firma del acta |

Estas tres columnas se llenaban **a mano**, buscando cada factura dentro del archivo maestro **`CIRCULARIZACIÓN DE GLOSAS 2026.xlsx`** (hoja `GENERAL`, 7.399 filas, 4.036 facturas distintas), leyendo el concepto de conciliación pactado y copiándolo. Con 76 filas pendientes solo en junio de 2026, el trabajo era lento, propenso a error de copiado y no dejaba rastro de por qué se eligió un texto y no otro.

### 1.2 La necesidad que cubre

- **Automatizar el cruce** factura ↔ acta de conciliación, con la regla de negocio explícita: *el VALOR ACEPTADO de la nota crédito debe coincidir con lo que el acta registra como aceptado por la IPS*.
- **Dejar auditoría del cruce**: no basta con llenar las celdas; el auditor necesita saber en cuáles filas el dato es exacto y en cuáles hubo una discrepancia (valor que no cuadra, número de acta citado distinto al registrado, factura que no aparece en la circularización).
- **Ser repetible cada mes** con un solo comando, sobre cualquier consolidado mensual futuro.
- **No dañar el libro original**: el consolidado tiene fórmulas de totales, formatos y filas ya diligenciadas que sirven de ejemplo. La herramienta debe escribir *solo* en las celdas pendientes.

### 1.3 Objetivo secundario cubierto en la misma rama: la Bitácora

Durante la misma sesión el usuario planteó un segundo problema, de naturaleza organizativa: el proyecto se desarrolla en **múltiples conversaciones paralelas de Claude Code y múltiples ramas**, y no existía una memoria común. Cada chat nuevo empezaba sin saber el estado real del proyecto.

Se resolvió creando **`BITACORA.md`** (memoria común, escrita para un auditor de cartera, no para un programador) y **`CLAUDE.md`** (instrucción permanente para que toda sesión la lea al iniciar y la actualice al terminar). Esto es lo que hoy permite este mismo ejercicio de consolidación.

### 1.4 Objetivo terciario: estabilización del CI

Al integrar lo anterior aparecieron dos fallos del pipeline de integración continua, ajenos al módulo pero bloqueantes para poder fusionarlo. Se corrigieron ambos (ver §10.4 y §10.5). Se documentan porque forman parte del trabajo entregado y porque el segundo revela un **patrón de defecto recurrente en la suite de pruebas del proyecto principal** que el equipo debe conocer.

---

## 2. Arquitectura

### 2.1 Naturaleza del módulo

Este módulo es un **utilitario de línea de comandos (CLI), sin estado, ejecutado bajo demanda por el auditor**. No es un servicio, no expone endpoints, no escribe en base de datos y no tiene interfaz gráfica. Se ubica en la familia de herramientas `tools/` del repositorio, junto a los demás utilitarios ofimáticos y robots de portal.

Esta decisión fue deliberada (ver §2.5).

### 2.2 Ubicación en el árbol del repositorio

```
motor-glosas-hus/
├── BITACORA.md                                  ← NUEVO (memoria común de sesiones)
├── CLAUDE.md                                    ← NUEVO (instrucción permanente de sesión)
├── docs/
│   └── HANDOVER_TRAMITE_GLOSAS_ACEPTADAS.md     ← NUEVO (este documento)
├── tools/
│   ├── completar_tramite_glosas_aceptadas.py    ← NUEVO (el módulo)
│   ├── convertir_tramite_masivo.py              (preexistente, familia afín)
│   ├── dividir_notas_por_acta.py                (preexistente, familia afín)
│   ├── extraer_notas_credito.py                 (preexistente, familia afín)
│   ├── consolidar_carpetas_notas.py             (preexistente, familia afín)
│   ├── verificar_cuv_notas.py                   (preexistente, familia afín)
│   ├── responder_glosas_coosalud.py             (preexistente, robot de portal)
│   ├── responder_glosas_simed.py                (preexistente, robot de portal)
│   ├── responder_glosas_dgh.py                  (preexistente, robot de portal)
│   └── ...
└── tests/
    └── test_api/
        ├── test_heatmap_actividad.py            ← MODIFICADO (fix de CI)
        ├── test_por_dia_semana.py               ← MODIFICADO (fix de CI)
        └── test_import_history.py               ← MODIFICADO (solo formato)
```

### 2.3 Componentes internos del módulo

El archivo `tools/completar_tramite_glosas_aceptadas.py` (290 líneas) está organizado en cuatro capas conceptuales, sin clases (funciones puras + un `main()` orquestador):

```
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 0 — Configuración declarativa (constantes de módulo)       │
│   Mapa de columnas BD_* y GEN_*, expresiones regulares          │
│   RE_ACTA / RE_FECHA_DMA / RE_FECHA_TEXTO, diccionario MESES    │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 1 — Normalización (funciones puras, sin dependencias)      │
│   limpiar()  ·  a_numero()  ·  a_fecha()  ·  normalizar_encabezado() │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 2 — Extracción e indexación                                │
│   parsear_obs()      (texto libre → acta, fecha, respuesta)     │
│   cargar_general()   (hoja GENERAL → índice en memoria)         │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 3 — Motor de decisión                                      │
│   buscar_subconjunto()  (suma exacta = valor aceptado)          │
│   resolver_fila()       (cascada de 4 estrategias + notas)      │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 4 — Orquestación e I/O                                     │
│   main()  (argv → carga → recorrido → escritura → reporte CSV)  │
└─────────────────────────────────────────────────────────────────┘
```

**Sin clases, sin estado global mutable, sin efectos secundarios fuera de `main()`.** Todas las funciones de las capas 1–3 son puras y unitariamente testeables; `main()` es el único punto que toca el sistema de archivos.

### 2.4 Dependencias

| Dependencia | Tipo | Uso |
|---|---|---|
| `openpyxl` (3.1.5) | Externa, PyPI | Lectura y escritura de `.xlsx` preservando formatos y fórmulas |
| `et-xmlfile` (2.0.0) | Transitiva de openpyxl | Escritura incremental del XML de OOXML |
| `csv` | Biblioteca estándar | Emisión del reporte de revisión |
| `re` | Biblioteca estándar | Extracción de acta/fecha/respuesta del texto libre |
| `sys` | Biblioteca estándar | Lectura de `sys.argv` |
| `unicodedata` | Biblioteca estándar | Normalización NFD de encabezados (quita tildes) |
| `collections.defaultdict` | Biblioteca estándar | Índice factura → lista de glosas |
| `datetime.datetime` | Biblioteca estándar | Manejo de fechas de acta |

**No se agregó ninguna dependencia nueva al proyecto.** `openpyxl` ya está en `requirements.txt` porque toda la familia `tools/` y el backend lo usan. Ver §11 para el detalle completo, incluidas las dependencias instaladas *solo en el entorno efímero de desarrollo* para reproducir el CI.

### 2.5 Decisiones de arquitectura y alternativas descartadas

| # | Decisión | Alternativa descartada | Por qué |
|---|---|---|---|
| **D1** | Script CLI en `tools/` | Endpoint FastAPI + pantalla en la app web | El insumo son dos Excel que el auditor tiene en su máquina, el resultado es otro Excel que él revisa y entrega. Meter la app web en el medio (subir, procesar, descargar) agrega infraestructura, autenticación y almacenamiento temporal sin aportar nada al flujo real. La familia `tools/` ya es la convención del repo para exactamente este tipo de trabajo. |
| **D2** | Lógica **determinista** (regex + aritmética) | Usar el motor de IA del proyecto para redactar/emparejar las respuestas | Es un dato **contable y auditable**: la respuesta debe ser *literalmente* el concepto pactado en el acta, no una redacción nueva. Un LLM introduciría variación, costo por token, latencia, y —lo decisivo— haría imposible explicarle al auditor por qué salió ese texto. La regla «el valor debe cuadrar» es aritmética exacta, no un juicio. Ver §8. |
| **D3** | Cruce contra la hoja `GENERAL` | Cruce contra `CONCILIACIONES REALIZADAS` | Se inspeccionaron ambas. `CONCILIACIONES REALIZADAS` es un **resumen por acta** (una fila por acta: entidad, fecha de firma, valor total aceptado, gestor, auditor). No tiene el detalle por factura ni el concepto de conciliación. `GENERAL` sí: una fila por *glosa* de *factura*, con `VALOR ACEPTADO POR IPS`, `N° ACTA`, `FECHA DE FIRMA ACTAS`, `CONCEPTO CONCILIACIÓN` y `CÓDIGO DE LA GLOSA`. `CONCILIACIONES REALIZADAS` se usó únicamente como fuente de verificación cruzada de metadatos de acta durante el análisis. |
| **D4** | Emparejamiento por **subconjunto de suma exacta** | Sumar todas las glosas del acta y comparar | Una factura puede tener varias glosas en un acta, y la nota crédito acredita solo algunas (otras se levantaron, o se acreditaron en otra nota). Sumar todo daba un total que no coincide con la nota en 19 de 76 casos. El subconjunto exacto identifica *cuáles* conceptos corresponden a esta nota. |
| **D5** | Cascada con **fallback al texto de la propia nota crédito** | Dejar la celda vacía / marcarla `REVISAR` cuando no hay match | 21 de 76 filas correspondían a un acta de **vigencia 2025** (acta 599) que no existe en la circularización 2026 — el dato nunca iba a aparecer allí. Pero la columna `OBSERVC NOTA CREDITO` de la propia fila **ya contiene el texto del acta** (es lo que se le escribió a la nota al emitirla). Dejar 21 celdas vacías habría sido devolverle al auditor el 28% del trabajo. El fallback las llena con el texto correcto y el reporte CSV dice de dónde salió. |
| **D6** | **Reporte CSV separado**, no marcas dentro del Excel | Colorear celdas / agregar columna de observaciones en el libro | El consolidado es un entregable formal que va a contabilidad; agregarle columnas o colores lo altera. El CSV es un anexo de trabajo que el auditor abre al lado. |
| **D7** | Escribir **solo** en filas donde W, X **y** Y están vacías | Reescribir todas las filas | Las filas 5–123 ya estaban diligenciadas y son la referencia de estilo que el propio usuario pidió tomar como ejemplo. Sobrescribirlas destruiría trabajo humano previo. |
| **D8** | ~~Deduplicar conceptos con `dict.fromkeys`~~ **REVERTIDA en agosto**: ya no se deduplica | `set()` | `set()` no preserva el orden. El orden de los conceptos en el acta importa: refleja el orden de las glosas de la factura. `dict.fromkeys` deduplica preservando el orden de aparición. Esta corrección se aplicó *después* de la primera corrida, al detectar en la fila 128 el texto `EN CONCILIACIÓN ENTIDAD LEVANTA GLOSA | EN CONCILIACIÓN ENTIDAD LEVANTA GLOSA | EN CONCILIACIÓN ENTIDAD LEVANTA GLOSA | ...` (tres glosas distintas de la misma factura con idéntico concepto de levantamiento). |
| **D9** | Colapsar texto duplicado en `parsear_obs()` | Dejarlo tal cual | La fila 161 (`HUS0000467327`) traía la observación con la **misma frase escrita dos veces seguidas**, error de captura del gestor al emitir la nota. Se detecta partiendo el texto por la mitad y comparando ambas mitades. |
| **D10** | Validación del encabezado con `assert` | Confiar en los índices fijos | Si el mes siguiente alguien inserta una columna, los índices se corren y el script llenaría columnas equivocadas *en silencio*. El `assert` sobre el encabezado de la columna W (normalizado sin tildes) hace que falle ruidosamente en vez de corromper el archivo. |

---

## 3. Funciones implementadas

Se documentan las **9 funciones** del módulo, en orden de dependencia.

---

### 3.1 `limpiar(texto) -> str`

**Qué hace.** Normaliza cualquier valor de celda a una cadena limpia: `None` → `""`, elimina el artefacto `_x000D_` y los retornos de carro `\r`, y recorta espacios de los extremos.

**Cómo funciona.**
```python
def limpiar(texto):
    if texto is None:
        return ""
    return str(texto).replace("_x000D_", "").replace("\r", "").strip()
```

**Por qué existe.** Los Excel exportados del DGH (Dinámica Gerencial) traen los saltos de línea codificados como el literal `_x000D_` seguido de `\n`. Si no se limpia, ese texto aparece dentro de la respuesta escrita en el consolidado y el auditor lo ve como basura. Además, **las filas pendientes del consolidado de junio no tenían la celda W vacía (`None`) sino con un espacio en blanco (`' '`)** — hallazgo real durante la exploración. Sin `limpiar()`, la detección de "fila pendiente" habría fallado en las 76 filas y el script no habría llenado nada.

**Archivos que modifica.** Ninguno (función pura).

**Qué depende de ella.** `a_numero()`, `a_fecha()`, `parsear_obs()`, `cargar_general()`, `normalizar_encabezado()`, `main()`. Es la función más usada del módulo.

---

### 3.2 `a_numero(v) -> int`

**Qué hace.** Convierte un valor de celda a entero redondeado. `None` → `0`. Tolera cadenas con separador de miles (`"1,195,740"`). Ante cualquier valor no convertible devuelve `0`.

**Cómo funciona.**
```python
def a_numero(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return round(float(v))
    try:
        return round(float(str(v).replace(",", "").strip()))
    except ValueError:
        return 0
```

**Por qué existe.** La columna `VALOR ACEPTADO` del consolidado viene como número, pero la columna `VALOR ACEPTADO POR IPS ESE HUS EN CONCILIACION` de la circularización viene **como texto en muchas filas** (se verificó: los valores de `GENERAL` se leyeron como `'200'`, `'1222800'`, cadenas). Comparar `12465` con `'12465'` da falso siempre. El redondeo a entero elimina además los decimales flotantes que hacían fallar la comparación de sumas exactas (pesos colombianos no tienen centavos en este flujo).

El retorno `0` ante error es deliberado: una celda vacía o con basura equivale a "no aportó valor a la suma", que es semánticamente correcto en este dominio.

**Archivos que modifica.** Ninguno.

**Qué depende de ella.** `cargar_general()` (para `val` y `acta`), `main()` (para el valor aceptado de la fila).

---

### 3.3 `a_fecha(v) -> datetime | None`

**Qué hace.** Convierte a `datetime`. Si ya es `datetime`, lo devuelve tal cual. Si es texto, intenta los formatos `%Y-%m-%d %H:%M:%S` y `%Y-%m-%d`. Si nada funciona, `None`.

**Cómo funciona.**
```python
def a_fecha(v):
    if isinstance(v, datetime):
        return v
    s = limpiar(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
```

**Por qué existe.** La columna `FECHA DE FIRMA ACTAS` de la hoja `GENERAL` viene inconsistente: en unas filas es un `datetime` real de Excel, en otras es la cadena `'2026-01-05 00:00:00'`. Se comprobó en la exploración (`Row 3: ... (13, '2026-01-05 00:00:00')`).

**Archivos que modifica.** Ninguno.

**Qué depende de ella.** `cargar_general()`.

---

### 3.4 `normalizar_encabezado(v) -> str`

**Qué hace.** Pasa un encabezado a mayúsculas y le quita las tildes mediante descomposición Unicode NFD, eliminando los caracteres combinantes.

**Cómo funciona.**
```python
def normalizar_encabezado(v):
    s = unicodedata.normalize("NFD", limpiar(v).upper())
    return "".join(ch for ch in s if not unicodedata.combining(ch))
```

**Por qué existe.** Da soporte a la validación defensiva del `assert` en `main()` (decisión **D10**). Los encabezados del consolidado varían entre meses en tildes y espacios (`'RESPUESTA TRAMITE GLOSA Y/O ACTA'`, `'NO DE GLOSA '` con espacio final, `'FECHA DE GLOSA  '` con dos). Comparar contra el texto crudo sería frágil.

**Archivos que modifica.** Ninguno.

**Qué depende de ella.** `main()`.

---

### 3.5 `parsear_obs(obs) -> tuple[int|None, datetime|None, str]`

**Qué hace.** Es el **extractor de texto libre**. Recibe el contenido de la columna `OBSERVC NOTA CREDITO` (col I del consolidado) y devuelve una tripleta `(acta, fecha, respuesta)`.

**Cómo funciona, paso a paso.**

1. **Limpia** el texto con `limpiar()`.
2. **Busca el número de acta** con `RE_ACTA`:
   ```python
   RE_ACTA = re.compile(r"ACTA\s*(?:DE\s+CONCILIACI\w+\s*)?(?:N\s*[°º\.]?\s*)?(\d{3,4})", re.I)
   ```
   Este patrón absorbe todas las variantes reales encontradas en los datos:
   - `ACTA DE CONCILIACION N° 599 DE 14/11/2025`
   - `ACTA DE CONCILIACION N. 803 DEL 28 DE MAYO DE 2026`
   - `ACTA N° 862 EN CONCILIACIÓN...`
   - `ACTA N°862 EN CONCILIACIÓN...` (sin espacio)
   - `ACTA 805 DE 10/06/2026, DONDE:`
   - `ACTA DE CONCILIACIÓN N° 786 DE 07/05/2026,`

   `\w+` tras `CONCILIACI` cubre `CONCILIACION` y `CONCILIACIÓN`. El grupo `(\d{3,4})` limita a números de acta de 3 o 4 dígitos, evitando capturar años o valores.

3. **Busca la fecha** en el texto que sigue al acta (`resto`), con dos estrategias en cascada:
   - `RE_FECHA_DMA` sobre los primeros **60 caracteres**: formato `dd/mm/aaaa` o `dd-mm-aaaa`.
   - Si no hay, `RE_FECHA_TEXTO` sobre los primeros **80 caracteres**: formato `28 DE MAYO DE 2026`, resuelto con el diccionario `MESES`.

   La ventana acotada (60/80 chars) es intencional: **evita capturar fechas que aparecen dentro del cuerpo del argumento** (por ejemplo `ESTANCIA DEL DIA 29/01/2026`, presente en la fila 159). Solo interesa la fecha que acompaña inmediatamente al número de acta.

   Ambas conversiones van dentro de `try/except ValueError` para que una fecha imposible (`31/02/2026`) devuelva `None` en vez de reventar la corrida completa.

4. **Extrae la respuesta** buscando un ancla que marque dónde termina el preámbulo y empieza el acuerdo:
   - Ancla primaria: `DONDE\s*:?` o `EN LA CUAL\s*[;:]?` → toma todo lo que sigue.
   - Ancla secundaria (si no hay primaria): `EN CONCILI\w+` o `ESE HUS` → toma desde ahí.

   Esto convierte
   `'GLOSA VIG ANTERIOR | ADMINISTRATIVO | SE REALIZA NC SEGÚN ACTA DE CONCILIACION N° 599 DE 14/11/2025, DISPENSARIO MÉDICO DE BUCARAMANGA DONDE EN CONCILIACION LA ESE HUS ACEPTA GLOSA TOTAL DE $10.218 POR MVC EN LABORATORIO...'`
   en
   `'EN CONCILIACION LA ESE HUS ACEPTA GLOSA TOTAL DE $10.218 POR MVC EN LABORATORIO...'`.

5. **Colapsa duplicados** (decisión **D9**): si el texto resultante mide más de 80 caracteres y su primera mitad es idéntica a la segunda, se queda con una sola.

6. Devuelve `(acta, fecha, respuesta.strip())`.

**Por qué existe.** Es el único camino para llenar las filas cuya acta no está en la circularización (las 21 del acta 599 de vigencia 2025) y las filas donde el valor no cuadra con el acta (19 casos). Sin esta función el módulo cubriría solo el 47% de las filas.

**Archivos que modifica.** Ninguno.

**Qué depende de ella.** `resolver_fila()`.

---

### 3.6 `buscar_subconjunto(vals, objetivo) -> list[int] | None`

**Qué hace.** Dado un listado de valores (las glosas de una factura dentro de un acta) y un objetivo (el `VALOR ACEPTADO` de la nota crédito), devuelve **los índices cuyos valores suman exactamente el objetivo**, o `None` si no existe tal combinación.

**Cómo funciona.** Tres estrategias en orden de costo creciente:

1. **Caso «todo»**: si la suma de todos los valores positivos ya es el objetivo, devuelve `list(range(len(vals)))` — **todos los índices, incluidos los de valor 0**. Este detalle es clave: las glosas levantadas por la entidad tienen valor 0 pero su concepto (`EN CONCILIACIÓN ENTIDAD LEVANTA GLOSA`) sí debe aparecer en la respuesta, porque forma parte del acuerdo del acta.
2. **Caso «uno solo»**: si algún valor individual iguala el objetivo, devuelve ese único índice. Cubre el caso mayoritario (una factura con una sola glosa acreditada).
3. **Programación dinámica**: construye un diccionario `alcanzables` de `suma → lista de índices`, partiendo de `{0: []}` y expandiéndolo con cada valor positivo. Se poda toda suma que exceda el objetivo (`if ns <= objetivo`) y no se re-registra una suma ya alcanzada (se queda con el primer subconjunto que la produce). Al final consulta `alcanzables.get(objetivo)`.

**Guarda de seguridad.** `if len(alcanzables) > 500000: break`. Una factura con muchas glosas de valores dispares podría hacer explotar el espacio de sumas. Con el corte, el peor caso degrada a "no encontré subconjunto" → el módulo cae al fallback de la observación, que sigue siendo un resultado correcto y trazable. En los datos reales de junio 2026 el caso más grande fue una factura con 23 glosas (`HUS0000475082`) y nunca se acercó al límite.

**Por qué existe.** Materializa la regla de negocio que el usuario enunció explícitamente: *«el VALOR ACEPTADO debe coincidir con los valores contenidos dentro de la columna RESPUESTA TRAMITE GLOSA Y/O ACTA»*. Es el corazón de la correctitud del módulo.

**Archivos que modifica.** Ninguno.

**Qué depende de ella.** `resolver_fila()` — la invoca dos veces: una para escoger el acta candidata y otra para escoger los conceptos dentro del acta elegida.

---

### 3.7 `cargar_general(ruta) -> defaultdict[str, list[dict]]`

**Qué hace.** Lee la hoja `GENERAL` del archivo de circularización y devuelve un índice en memoria: `{ "HUS0000418576": [ {val, acta, fecha, concepto}, ... ], ... }`.

**Cómo funciona.**
```python
wb = openpyxl.load_workbook(ruta, read_only=True)
ws = wb["GENERAL"]
for fila in ws.iter_rows(min_row=3, values_only=True):
    factura = limpiar(fila[GEN_FACTURA])
    if not factura.upper().startswith("HUS"):
        continue
    ...
wb.close()
```

- `read_only=True` + `values_only=True`: modo de lectura en streaming de openpyxl, sin construir objetos `Cell`. Necesario porque la hoja tiene 7.399 filas y el libro completo contiene además `CRONOGRAMA DE CONCILIACIONES` con **1.048.155 filas declaradas × 1.025 columnas**; cargarlo en modo normal consume memoria innecesariamente.
- `min_row=3` porque la fila 1 son subtotales (`=SUBTOTAL(9,E3:E7349)`) y la fila 2 son los encabezados.
- El filtro `startswith("HUS")` descarta filas de totales, filas vacías y cualquier basura al final de la hoja: **toda factura del hospital empieza con el prefijo `HUS`**.
- `wb.close()` explícito, obligatorio en modo `read_only` para liberar el descriptor de archivo.

**Por qué existe.** Sin el índice, cada una de las 76 filas del consolidado exigiría recorrer 7.399 filas — 562.324 comparaciones. Con el índice, cada consulta es O(1) sobre un diccionario. La carga completa toma menos de dos segundos.

**Archivos que modifica.** Ninguno (abre en solo lectura y cierra).

**Qué depende de ella.** `main()`.

---

### 3.8 `resolver_fila(factura, valor, obs, general) -> tuple[str, int|None, datetime|None, list[str]]`

**Qué hace.** Es el **motor de decisión**. Para una fila pendiente devuelve `(respuesta, acta, fecha, notas_de_revision)`.

**Cómo funciona — la cascada completa:**

```
                    ┌──────────────────────────────────┐
                    │ parsear_obs(obs)                 │
                    │ → acta_obs, fecha_obs, resp_obs  │
                    └──────────────────────────────────┘
                                    │
                    ¿la factura está en GENERAL?
                    │                              │
                   NO                             SÍ
                    │                              │
                    ▼                              ▼
        ┌───────────────────────┐    Agrupa sus glosas por N° de acta
        │ ESTRATEGIA D          │                  │
        │ resp_obs, acta_obs,   │    ¿el acta citada en la NC está
        │ fecha_obs             │     entre esos grupos?
        │ + nota: "factura no   │      │                    │
        │   está en la          │     SÍ                   NO
        │   circularización"    │      │                    │
        └───────────────────────┘      │         Elige grupo: primero los que
                                       │         cuadran por suma; si ninguno,
                                       │         el de fecha de acta más reciente
                                       │         + nota: "NC cita acta X;
                                       │           circularización la registra
                                       │           en acta Y"
                                       │                    │
                                       └────────┬───────────┘
                                                ▼
                              ¿existe subconjunto que sume el valor?
                                    │                     │
                                   SÍ                    NO
                                    │                     │
                                    ▼                     ▼
                    ┌───────────────────────┐  ┌────────────────────────────┐
                    │ ESTRATEGIA A          │  │ ¿hay texto en resp_obs?    │
                    │ Conceptos del         │  │   SÍ → ESTRATEGIA B        │
                    │ subconjunto,          │  │      resp_obs + acta/fecha │
                    │ deduplicados,         │  │      de GENERAL            │
                    │ unidos por " | "      │  │   NO → ESTRATEGIA C        │
                    │ Acta y fecha de       │  │      todos los conceptos   │
                    │ GENERAL               │  │      del acta unificados   │
                    │ SIN notas → exacto    │  │ + nota: "valor X no cuadra │
                    └───────────────────────┘  │   con el acta (Y)"         │
                                               └────────────────────────────┘
```

**Detalle de la selección de acta cuando la citada no coincide** (línea 188-196):
```python
con_cuadre = [g for g in por_acta.values() if buscar_subconjunto([c["val"] for c in g], valor)]
candidatos = con_cuadre or list(por_acta.values())
grupo = max(candidatos, key=lambda g: g[0]["fecha"] or datetime.min)
```
Prioriza las actas cuyos valores **cuadran** con la nota; entre ellas (o entre todas, si ninguna cuadra) elige la de **fecha de firma más reciente**, porque una factura puede pasar por varias conciliaciones sucesivas y la nota crédito del mes corresponde a la más nueva. El `or datetime.min` protege contra actas sin fecha.

**Por qué existe.** Concentra toda la política de negocio en un solo lugar. Cualquier cambio de criterio (por ejemplo, si el auditor decide que el acta citada en la NC debe prevalecer siempre) se hace aquí y en ningún otro sitio.

**Las notas de revisión son parte del contrato de la función**, no un log: alimentan el CSV que el auditor usa para saber qué verificar. Los tres textos posibles son:
- `factura no esta en la circularizacion; datos tomados de la observacion de la NC`
- `NC cita acta {N}; circularizacion la registra en acta {M}`
- `valor aceptado {V} no cuadra con el acta ({T}); respuesta tomada de la observacion de la NC`
- (raro) `sin texto extraible en la observacion; se unifican todos los conceptos del acta`

**Archivos que modifica.** Ninguno.

**Qué depende de ella.** `main()`.

---

### 3.9 `main() -> None`

**Qué hace.** Orquesta todo el proceso: valida argumentos, carga el índice, recorre el consolidado, escribe las celdas, guarda el libro y emite el reporte.

**Cómo funciona, paso a paso.**

1. **Valida `sys.argv`**: si hay menos de 4 argumentos, imprime el docstring del módulo (que es el manual de uso) y sale con código 1.
2. **Carga el índice** de la circularización con `cargar_general()`.
3. **Abre el consolidado en modo normal** (no `read_only`, porque va a escribir) y selecciona la hoja `BD`.
4. **Valida el encabezado** (decisión **D10**):
   ```python
   encabezado = [normalizar_encabezado(c.value) for c in ws[BD_HEADER_ROW]]
   assert "RESPUESTA TRAMITE" in encabezado[BD_RESPUESTA], encabezado[BD_RESPUESTA]
   ```
   Si la columna 23 (índice 22 = W) no es la de respuesta, aborta con `AssertionError` mostrando qué encontró.
5. **Recorre desde la fila 5** (`BD_HEADER_ROW + 1`):
   - Salta filas sin factura (`if not factura: continue`) — esto excluye la fila de totales 200 y las vacías 201-202.
   - Determina si está **pendiente**: `limpiar(W)` vacío **y** `X is None` **y** `Y is None`. Los tres deben cumplirse; una fila con W lleno y X vacío no se toca (se considera intervención humana deliberada).
   - Llama a `resolver_fila()`.
   - **Escribe condicionalmente**: `if respuesta:` W, `if acta:` X, `if fecha:` Y. Nunca escribe `None` ni cadena vacía sobre una celda.
   - Al escribir Y, fija `number_format = "dd/mm/yyyy"` para igualar el formato de las filas ya diligenciadas (verificado: `Y5` tenía `numfmt='dd/mm/yyyy'`).
   - Si alguno de los tres campos quedó sin dato, añade la nota `INCOMPLETA: revisar manualmente`.
   - Acumula una entrada de reporte **por cada nota** (una fila puede generar dos: acta discrepante + valor que no cuadra).
6. **Guarda** en la ruta de salida (nunca sobre el original).
7. **Emite el reporte**: si se pasó el 4º argumento, escribe el CSV con `encoding="utf-8-sig"` (el BOM hace que Excel en español abra las tildes correctamente sin pasar por el asistente de importación); si no, lo imprime por consola.

**Por qué existe.** Es el único punto de entrada y el único con efectos secundarios.

**Archivos que modifica.**
- **Escribe** el `.xlsx` de salida (argumento 3).
- **Escribe** el `.csv` de reporte (argumento 4, opcional).
- **Lee** el consolidado y la circularización. **Nunca los modifica.**

---

## 4. Flujo completo

### 4.1 Flujo del módulo de glosas aceptadas, de principio a fin

**Punto de partida: el auditor tiene dos archivos en su máquina.**

```bash
python tools/completar_tramite_glosas_aceptadas.py \
    "ARCHIVO JUNIO 2026-GLOSAS ACEPTADAS.xlsx" \
    "CIRCULARIZACIÓN DE GLOSAS 2026.xlsx" \
    "ARCHIVO JUNIO 2026-GLOSAS ACEPTADAS - DILIGENCIADO.xlsx" \
    "reporte_revision.csv"
```

**Paso 1 — Validación de argumentos.** `main()` verifica que haya al menos 3 rutas. Si no, imprime el manual y termina.

**Paso 2 — Indexación de la circularización (≈2 s).**
`cargar_general()` abre `CIRCULARIZACIÓN DE GLOSAS 2026.xlsx` en modo streaming, recorre las 7.399 filas de la hoja `GENERAL` desde la fila 3, descarta las que no empiezan por `HUS`, y construye un diccionario de **4.036 facturas** → lista de sus glosas, cada una con valor aceptado, número de acta, fecha de firma y concepto de conciliación. Cierra el archivo.

**Paso 3 — Apertura del consolidado.**
`openpyxl.load_workbook()` en modo lectura-escritura sobre la hoja `BD`. Se preservan fórmulas (`J200 = =SUM(J5:J199)`), formatos, anchos y las 119 filas ya diligenciadas.

**Paso 4 — Validación defensiva del encabezado.**
Se lee la fila 4, se normaliza sin tildes, y se comprueba que la posición 22 contenga `RESPUESTA TRAMITE`. Si el formato del mes cambió, se aborta aquí.

**Paso 5 — Recorrido fila por fila (filas 5 a 202).**

Para cada fila:

- **5.1** Se lee la factura (col C). Si está vacía → se salta (filas 200-202: totales y vacías).
- **5.2** Se evalúa si está pendiente: W vacío/en blanco **y** X nulo **y** Y nulo. Las filas 5–123 fallan esta prueba (ya tienen dato) → se saltan. Las filas 124–199 la pasan → se procesan. **76 filas.**
- **5.3** Se lee el `VALOR ACEPTADO` (col J) y se normaliza a entero.
- **5.4** Se invoca `resolver_fila(factura, valor, observacion, indice)`:
  - **5.4.1** `parsear_obs()` extrae del texto de la col I el número de acta citado, su fecha y el fragmento de respuesta.
  - **5.4.2** Se busca la factura en el índice.
    - *Camino A (55 filas de 76):* la factura existe. Se agrupan sus glosas por acta.
      - Si el acta citada en la NC coincide con una del índice → ese grupo.
      - Si no coincide (14 filas) → se prefiere el grupo cuyos valores cuadran; si ninguno cuadra, el de fecha más reciente. Se emite la nota `NC cita acta X; circularizacion la registra en acta Y`.
      - Se busca el subconjunto de glosas que suma exactamente el valor de la nota.
        - **Cuadra (36 filas):** la respuesta son esos conceptos, deduplicados en orden, unidos por `" | "`. Acta y fecha salen de la circularización. **Sin notas de revisión — es el caso exacto.**
        - **No cuadra (19 filas):** se emite la nota con ambos valores y se usa el texto de la observación de la NC como respuesta, conservando acta y fecha de la circularización.
    - *Camino B (21 filas de 76):* la factura no está en la circularización (todas del acta 599 de 2025). Se usan los tres datos extraídos de la observación y se emite la nota `factura no esta en la circularizacion`.
- **5.5** Se escriben las celdas W, X, Y —solo las que tengan dato— y se fija el formato `dd/mm/yyyy` en Y.
- **5.6** Se acumulan las notas en el reporte, con número de fila, factura, valor y acta.

**Paso 6 — Guardado.** El libro se escribe en la ruta de salida. El archivo original queda intacto en disco.

**Paso 7 — Reporte.** Se escribe el CSV con encabezados `fila, factura, valor_aceptado, acta, nota` y BOM UTF-8.

**Paso 8 — Salida por consola.**
```
Filas diligenciadas: 76
Archivo generado: ARCHIVO JUNIO 2026-GLOSAS ACEPTADAS - DILIGENCIADO.xlsx
Reporte de revision (54 notas): reporte_revision.csv
```

**Paso 9 — Verificación (ejecutada manualmente en la sesión, no automatizada).**
Se comprobó celda por celda contra el original que:
- Las 195 filas de datos tienen W, X, Y completos (0 incompletas).
- **0 celdas modificadas fuera de W/X/Y** (comparación exhaustiva de las 28 columnas × 202 filas).
- La fórmula `J200 = =SUM(J5:J199)` quedó intacta.
- `Y124.number_format == 'dd/mm/yyyy'`, `X` como entero, `Y` como `datetime`.

**Paso 10 — Entrega.** El auditor recibe el `.xlsx` diligenciado y el `.csv` de revisión.

### 4.2 Flujo del sub-módulo de llenado de `#N/D` (archivos de nota crédito individual)

Este flujo se ejecutó **dos veces** en la sesión, sobre `archivo.xlsx` y `archivo_1.xlsx`, mediante scripts en línea (no persistidos en el repositorio — ver §15.4).

1. **Inspección**: se detecta que la hoja `Hoja1` tiene encabezados en dos niveles (fila 4 general, fila 5 el desglose S/T/U/V) y datos en las filas 6 y 7.
2. **Localización de errores**: se buscan celdas cuyo valor sea la cadena `#N/A` / `#N/D`. Se encuentran exactamente 2: `V6` y `V7`, en la columna `RESPUESTA A LA GLOSA INICIAL Y/O ACTA`. **Se verifica que no son fórmulas rotas sino valores literales** — el `BUSCARV` original fue pegado como valor, por lo que no hay fórmula que reparar.
3. **Verificación de origen**: se busca cada factura en la hoja `GENERAL` de la circularización 2026. **Ninguna aparece**, confirmando la hipótesis: las actas 509 (04/06/2025) y 604 (20/11/2025) son de **vigencia 2025**.
4. **Extracción**: se aplica la misma regla de anclaje que `parsear_obs()` sobre la columna `W` (`OBSERVACION DE LA NOTA`), con la cascada `EN LA CUAL` → `FIRMADA POR ... .` → `DONDE`, y luego `EN CONCILIACION|ESE HUS`.
5. **Escritura** en V6 y V7.
6. **Verificación**: comparación exhaustiva contra el original → solo `V6` y `V7` cambiaron; no queda ninguna cadena `#N/`.
7. **Entrega** y **reporte verbal de discrepancia** al auditor (ver §4.3).

### 4.3 Hallazgo entregado al auditor en este sub-flujo

En la fila 7 (`HUS0000384193`, CAPITAL SALUD, acta 604) el acta registra **dos aceptaciones parciales de $55.100 y $58.600 = $113.700**, pero la nota crédito es por **$52.100**. Se llenó con el texto del acta y se advirtió explícitamente al usuario que validara contra el acta física, por si esa NC cubre solo una parte o existe otra nota por la diferencia. En la fila 6 (`HUS0000340948`, SURA SOAT, acta 509) el valor **sí coincide**: $12.465 en el acta y en la nota.

---

## 5. Base de datos

**Este módulo no utiliza base de datos.** No define modelos, no ejecuta consultas, no crea migraciones y no requiere datos semilla.

Es una decisión de diseño (**D1**): el estado vive en los archivos Excel que el auditor gestiona, que son el registro oficial del área. Introducir una tabla intermedia crearía una segunda fuente de verdad que habría que sincronizar.

**Lo que sí conviene saber para la consolidación**, porque el proyecto principal sí tiene base de datos y este módulo *podría* conectarse a ella en el futuro (ver §15.5):

- El proyecto principal usa **SQLAlchemy** sobre **SQLite en volumen** (migrado desde Neon/PostgreSQL el 17-jun-2026), con **Alembic** para migraciones (`alembic/`, `alembic.ini`).
- Los modelos relevantes al dominio de este módulo, observados en los tests que se corrigieron, son `GlosaRecord` (con campos `eps`, `paciente`, `codigo_glosa`, `valor_objetado`, `etapa`, `estado`, `creado_en`) y `UsuarioRecord` (`id`, `email`, `rol`, `activo`). Existen además tablas de nota crédito: el 27-abr-2026 se registró en el historial `feat(nota-credito): registro de NC en glosas aceptadas (parcial o total)` y un `hotfix(prod): auto-migrar 4 columnas nota_credito a tabla historial`.
- **Ninguna de esas tablas fue leída, escrita ni alterada por este desarrollo.**

**Migraciones aportadas por esta rama: ninguna.**

---

## 6. Backend

**Este módulo no aporta backend.** No hay endpoints, servicios, controladores, middleware ni permisos nuevos.

Se documentan a continuación los elementos que en un módulo web serían "backend" y cuál es su equivalente aquí:

| Concepto backend | Equivalente en este módulo |
|---|---|
| **Endpoint** | Invocación CLI: `python tools/completar_tramite_glosas_aceptadas.py <bd> <circ> <salida> [reporte]` |
| **Controlador** | `main()` |
| **Servicio de dominio** | `resolver_fila()` |
| **Repositorio / DAO** | `cargar_general()` |
| **Serializadores** | `limpiar()`, `a_numero()`, `a_fecha()` |
| **Validación de entrada** | Conteo de `sys.argv` + `assert` sobre el encabezado de la hoja `BD` |
| **Autorización** | Sistema de archivos del sistema operativo: quien puede leer los Excel, puede correrlo. No hay secretos ni credenciales involucradas. |

### 6.1 Manejo de errores — comportamiento documentado

| Situación | Comportamiento | Diseño |
|---|---|---|
| Menos de 3 argumentos | Imprime el docstring (manual de uso) y `sys.exit(1)` | Fallo controlado |
| Archivo inexistente | `FileNotFoundError` de openpyxl, traza completa | Fallo ruidoso, deliberado: mejor que continuar |
| Hoja `BD` o `GENERAL` ausente | `KeyError` de openpyxl | Fallo ruidoso |
| Encabezado corrido / formato distinto | `AssertionError` mostrando el encabezado hallado | **Protección crítica** (D10): evita corromper el archivo en silencio |
| Fecha imposible en el texto (`31/02/2026`) | `try/except ValueError` → fecha `None` → nota `INCOMPLETA: revisar manualmente` | Degradación elegante |
| Valor no numérico en la circularización | `a_numero()` → `0` | Degradación elegante |
| Factura ausente de la circularización | Fallback a la observación + nota en el CSV | Camino de negocio previsto, no error |
| Explosión combinatoria en el subconjunto | Corte a 500.000 sumas → `None` → fallback | Guarda de seguridad |

**Ningún `except` silencioso.** Todos los `try` capturan `ValueError` específicamente y el resultado degradado queda reflejado en el reporte de revisión. Esto responde a un criterio del propio repositorio: la ronda 29 del proyecto (07-jul-2026) fue precisamente una limpieza de *«bugs, excepts silenciosos y limpieza»*.

---

## 7. Frontend

**Este módulo no aporta frontend.** No hay pantallas, componentes, formularios, botones, tablas, modales, animaciones ni validaciones de interfaz.

La interfaz de usuario es **la terminal** (tres líneas de salida) y **los dos archivos entregables**. El "frontend" real, desde la perspectiva del auditor, es Microsoft Excel abriendo el `.xlsx` resultante y el `.csv` de revisión.

**Detalles de presentación que sí se cuidaron**, porque son lo que el usuario final ve:

- **Separador de conceptos `" | "`**: elegido para coincidir con la convención ya presente en el archivo, donde los códigos de glosa múltiples aparecen como `CL0101 | FA0201 | FA0301 | FA0601`.
- **Formato de fecha `dd/mm/yyyy`** en la columna Y, idéntico al de las filas ya diligenciadas.
- **Número de acta como entero**, no como texto, igual que las filas existentes (`X5` era `int`).
- **CSV con BOM UTF-8** (`utf-8-sig`) para que Excel en español muestre las tildes sin pasar por el asistente de importación de texto.
- **Preservación total** del formato del libro: `wrap_text`, fuentes (Calibri 11 en W, Arial 10 en X), anchos de columna y la fórmula de totales.

---

## 8. IA

### 8.1 Uso de IA **en tiempo de ejecución del módulo: ninguno**

Este es un punto que el equipo debe entender bien, porque el proyecto principal es una aplicación de IA y podría suponerse lo contrario.

**El módulo no llama a ningún proveedor de IA.** No hay prompts, no hay contexto de modelo, no hay temperatura, no hay fallback entre proveedores, no hay manejo de errores de API, no hay consumo de tokens y no hay costo por ejecución.

**Por qué se decidió así (decisión D2), en detalle:**

1. **Es un dato contable, no una redacción.** La columna `RESPUESTA TRAMITE GLOSA Y/O ACTA` debe contener el concepto **literal** pactado en el acta de conciliación, que es un documento firmado por ambas partes. Cualquier reformulación —por buena que sea— rompe la trazabilidad entre la nota crédito y el acta que la sustenta.
2. **La regla de negocio es aritmética, no interpretativa.** "El valor aceptado debe coincidir" se resuelve con una suma exacta, no con un juicio. Un LLM aquí solo podría equivocarse.
3. **Auditabilidad.** El auditor debe poder explicarle a un revisor externo por qué esa celda dice lo que dice. Con el algoritmo determinista la respuesta es: *«porque el acta 862 registra ese concepto por ese valor exacto»*. Con un LLM la respuesta sería *«porque el modelo lo generó»*, que no es defendible ante una auditoría de cartera.
4. **Reproducibilidad.** La misma entrada produce siempre la misma salida. Se puede re-correr el mes que viene y comparar.
5. **Costo cero y velocidad.** 76 filas en segundos, sin cuota de API.

Esto es coherente con la trayectoria del proyecto principal, que ha ido moviendo trabajo *desde* la IA *hacia* detectores deterministas cuando el determinismo alcanza: el 27-abr-2026 se implementó el *«auditor pre-IA detecta mentiras de la EPS sin gastar tokens»* y el *«panel pre-auditoría gratis (sin tokens)»*, y el 10-jun-2026 el Quality Gate con *«pre-val incondicional + detector de valores/contratos fabricados»*.

### 8.2 Uso de IA **en tiempo de desarrollo: sí, y así se hizo**

El módulo fue desarrollado íntegramente mediante **Claude Code** (modelo `claude-fable-5` durante el desarrollo; este documento redactado con `claude-opus-5`), en modo agente con acceso a shell, sistema de archivos y a la API de GitHub vía MCP.

**Metodología aplicada, en el orden real en que ocurrió:**

1. **Exploración antes que código.** Se inspeccionaron ambos Excel con openpyxl (hojas, dimensiones, encabezados, tipos de dato, estilos de celda) *antes* de escribir una sola línea del módulo. Se descubrió así que las celdas "vacías" contenían un espacio en blanco, que los valores de la circularización venían como texto, y que las fechas eran inconsistentes.
2. **Análisis de datos antes que diseño.** Se hizo un cruce exploratorio para medir el problema: 55 de 76 facturas presentes, 21 ausentes, 23 discrepancias de valor. Ese diagnóstico determinó la arquitectura de cascada; sin él se habría escrito un `VLOOKUP` que fallaba en el 28% de los casos.
3. **Verificación adversarial del propio resultado.** Tras la primera corrida se comparó celda por celda contra el original (28 columnas × 202 filas) para probar que no se tocó nada fuera de W/X/Y, y se revisó el contenido generado en 8 filas de muestra. Esa revisión detectó la duplicación de conceptos que motivó la corrección **D8**.
4. **Entrega con hallazgos, no solo con archivo.** Las discrepancias encontradas (acta 786 inexistente, valores parciales, acta 599 de 2025) se reportaron explícitamente al auditor en vez de resolverlas por cuenta propia, porque son decisiones de negocio suyas.

**Sobre la skill `xlsx`.** En los dos últimos encargos de la sesión (los archivos con `#N/D`) se invocó la skill `xlsx` del entorno, que aporta guías de manejo de openpyxl. De sus indicaciones se aplicaron: la doble carga (`data_only=True` para valores cacheados y carga normal para fórmulas), la advertencia de que guardar un libro abierto con `data_only=True` destruye las fórmulas, y la verificación de que no hubiera fórmulas que recalcular. Ver §15.3 para la única indicación de esa skill que quedó pendiente de aplicar (`recalc.py`).

---

## 9. Automatizaciones

### 9.1 Lo que este módulo automatiza

| Automatización | Qué hace | Cuándo se ejecuta | Cómo se ejecuta |
|---|---|---|---|
| **Cruce factura ↔ acta** | Empareja cada nota crédito con su acta de conciliación en la circularización | Bajo demanda, típicamente al cierre de mes | Comando CLI |
| **Validación de valor** | Comprueba que el valor de la nota cuadre con lo aceptado en el acta, identificando el subconjunto exacto de conceptos | En cada fila procesada | Automático dentro del cruce |
| **Extracción de acta/fecha del texto libre** | Lee el número y la fecha del acta desde la observación de la nota crédito | En cada fila procesada | Automático |
| **Unificación de conceptos** | Concatena los conceptos del acta deduplicados y en orden | En cada fila con match exacto | Automático |
| **Reporte de excepciones** | Genera el CSV con todos los casos que requieren ojo humano | Al final de la corrida | Automático |
| **Preservación del libro** | Escribe solo en celdas pendientes; no toca fórmulas, formatos ni filas ya diligenciadas | Siempre | Por diseño |

**Trabajo manual eliminado:** para junio de 2026 fueron **76 filas × 3 columnas = 228 celdas**, cada una de las cuales exigía buscar la factura entre 7.399 filas, identificar cuál acta y cuáles conceptos aplicaban, verificar el valor y copiar el texto. La corrida completa toma **menos de 30 segundos**.

### 9.2 Lo que **no** está automatizado (deliberadamente)

- **La decisión sobre las excepciones.** Las 54 notas del reporte requieren criterio del auditor. El módulo las identifica y las explica; no las resuelve.
- **La ejecución programada.** No hay cron, ni scheduler, ni disparador. Se corre cuando el auditor tiene los dos archivos listos. Automatizarlo exigiría que ambos Excel vivieran en una ruta fija y estuvieran siempre actualizados, cosa que no ocurre.

### 9.3 Automatización de proceso aportada por la Bitácora

`CLAUDE.md` instituye un **protocolo obligatorio de sesión** que el harness de Claude Code aplica automáticamente en cada conversación nueva sobre este repositorio:

1. **Al iniciar**: leer `BITACORA.md` antes de cualquier otra cosa.
2. **Al terminar**: actualizarla con (a) lo hecho hoy con fecha, (b) los pendientes agregados/retirados, (c) la sección "PARA MAÑANA" reescrita, (d) una fila nueva en la tabla de historial.
3. **Estilo obligatorio**: español claro, sin tecnicismos, destinatario auditor de cartera.
4. **Commit y push** de la bitácora antes de cerrar.

Se verificó que funciona: al abrir la sesión en la que se redactó este documento, el contenido de `CLAUDE.md` fue inyectado automáticamente en el contexto por el harness.

---

## 10. Archivos modificados

Diferencia completa de la rama contra `origin/motor-glosas`:

```
 BITACORA.md                                 | 253 +++++++++++++++++++++++
 CLAUDE.md                                   |  27 +++
 tests/test_api/test_heatmap_actividad.py    |  27 ++-
 tests/test_api/test_import_history.py       |   2 +-
 tests/test_api/test_por_dia_semana.py       |  27 ++-
 tools/completar_tramite_glosas_aceptadas.py | 290 +++++++++++++++++++++++++
 6 files changed, 607 insertions(+), 19 deletions(-)
```

Más este documento (`docs/HANDOVER_TRAMITE_GLOSAS_ACEPTADAS.md`), agregado al redactar la entrega.

### 10.1 `tools/completar_tramite_glosas_aceptadas.py` — **NUEVO** (290 líneas)

Commit `c11fb6f` (creación) + `496e2c7` (formato).

Archivo completo del módulo. Contenido íntegro en el [Anexo A](#anexo-a--código-fuente-completo-del-módulo). Estructura: docstring-manual de 25 líneas, 8 constantes de configuración, 3 expresiones regulares, 1 diccionario de meses, 9 funciones, guard `if __name__ == "__main__"`.

**No modifica ningún archivo existente del proyecto.** Es puramente aditivo.

### 10.2 `BITACORA.md` — **NUEVO** (253 líneas)

Commit `d3f95f2`.

Memoria común del proyecto, reconstruida a partir del **historial completo de git: 1.647 commits desde el 8 de abril de 2026** (fue necesario ejecutar `git fetch --unshallow` porque el clon de la sesión estaba truncado y solo mostraba desde el 12 de junio), más `CHANGELOG.md`, `AUDITORIA.md`, `AUDIT_CHECKLIST.md`, `PLAN_TRANSFORMACION_2026.md` y `docs/diagnostico_lote_v2_pendientes/INFORME_GERENCIA.md`.

Contenido:
- **Encabezado** con la instrucción de uso y fecha de última actualización.
- **«Qué es este proyecto (para ubicarse en 1 minuto)»**: los tres frentes del trabajo (app web con IA, robots de portales, utilitarios de Excel/notas crédito).
- **«Resumen de lo ya hecho»** agrupado por fecha, cubriendo abril, mayo, junio y julio de 2026, escrito en lenguaje de auditor.
- **«PENDIENTE»**: 5 bloques (Lote V2 del Dispensario, casos por confirmar del Excel de junio, PR #166, checklist técnico de la auditoría de mayo, robot de Dinámica Gerencial).
- **«PARA MAÑANA»**: 4 pasos concretos.
- **Tabla «Historial de actualizaciones de esta bitácora»**.

### 10.3 `CLAUDE.md` — **NUEVO** (27 líneas)

Commit `d3f95f2`.

Instrucción permanente para todas las sesiones de Claude Code sobre el repositorio. Dos secciones: «Bitácora obligatoria» (el protocolo de 4 puntos + la regla de estilo + commit/push) y «Contexto rápido» (qué es el proyecto y dónde están los documentos de contexto).

### 10.4 `tests/test_api/test_import_history.py` — **MODIFICADO** (1 línea)

Commit `496e2c7`. Cambio: **solo formato** — se agregó el salto de línea final que faltaba (`\ No newline at end of file`).

**Por qué se tocó.** El job `Lint (ruff)` del CI ejecuta `ruff format --check .` sobre **todo el repositorio**. Este archivo ya venía sin formatear desde antes de esta rama, y hacía fallar el gate junto con el módulo nuevo. No es posible dejar el CI verde sin corregirlo. **Es una corrección de deuda preexistente, ajena a este módulo**, y así se declaró en el mensaje del commit.

### 10.5 `tests/test_api/test_heatmap_actividad.py` — **MODIFICADO** (+18 / −9)

Commit `8a6f85d`.

**Cambios exactos:**
- Import reducido de `from datetime import datetime, timedelta, timezone` a `from datetime import timedelta`.
- `_seed(db, fecha_iso)` cambió de firma a `_seed(db, creado)`: ya no parsea una cadena ISO, recibe el `datetime` directamente.
- **Función nueva `_fecha_reciente(weekday, hora, minuto)`**: devuelve el día de semana pedido (0 = lunes) más reciente dentro de la ventana de 7–13 días atrás, con hora y minuto exactos.
  ```python
  base = ahora_utc() - timedelta(days=7)
  base -= timedelta(days=(base.weekday() - weekday) % 7)
  return base.replace(hour=hora, minute=minuto, second=0, microsecond=0)
  ```
- `test_ubica_eventos_en_celda_correcta` pasó de sembrar `"2026-04-20 09:30"`, `"2026-04-20 09:45"` y `"2026-04-22 14:15"` a `_fecha_reciente(0, 9, 30)`, `_fecha_reciente(0, 9, 45)` y `_fecha_reciente(2, 14, 15)`.

### 10.6 `tests/test_api/test_por_dia_semana.py` — **MODIFICADO** (+18 / −9)

Commit `8a6f85d`. Mismo patrón:
- Se eliminó el import `from datetime import datetime, timezone`.
- Se agregó `_fecha_reciente(weekday, hora=10, minuto=0)` (con `timedelta` importado localmente dentro de la función, siguiendo el estilo que el propio archivo ya usaba en `test_excluye_fuera_ventana`).
- `test_clasifica_por_dia`: `datetime(2026, 4, 20, 10, 0, ...)` → `_fecha_reciente(0, hora=10)`, etc.
- `test_pct_del_total`: `datetime(2026, 4, 20, ...)` ×4 → `_fecha_reciente(0)` ×4; `datetime(2026, 4, 21, ...)` → `_fecha_reciente(1)`.

### 10.7 Diagnóstico completo del fallo de CI que motivó 10.5 y 10.6

**Síntoma.** El 22-jul-2026, tras el push del commit de documentación `d3f95f2` (que solo agregaba `BITACORA.md` y `CLAUDE.md`), el job `Tests (pytest)` falló:

```
FAILED tests/test_api/test_heatmap_actividad.py::TestHeatmapActividad::test_ubica_eventos_en_celda_correcta - assert 0 == 2
FAILED tests/test_api/test_por_dia_semana.py::TestPorDiaSemana::test_clasifica_por_dia - assert 0 == 2
FAILED tests/test_api/test_por_dia_semana.py::TestPorDiaSemana::test_pct_del_total - assert 0.0 == 80.0
============ 3 failed, 4078 passed, 2 warnings in 242.45s (0:04:02) ============
```

**Causa raíz.** Bomba de tiempo de fecha. Ambos tests sembraban glosas con fechas fijas del **20–22 de abril de 2026**, y los endpoints que prueban (`/glosas/stats/heatmap-actividad` y `/glosas/stats/por-dia-semana`) solo cuentan registros dentro de una **ventana móvil de 90 días**. El 17 de julio, el 20 de abril estaba a 88 días → dentro de la ventana → los tests pasaban. El 22 de julio pasó a 93 días → fuera → los conteos dieron 0 y los asserts fallaron.

**Prueba de que no era regresión de esta rama:** el commit inmediatamente anterior no tocaba código de aplicación (solo dos `.md`), y estos mismos tests habían pasado en verde en la ejecución del 17 de julio sobre esta misma rama.

**Antecedente en el repositorio.** El proyecto ya había sufrido este patrón al menos tres veces: `fix: test caduco por fechas fijas + 7 errores ruff (F) preexistentes` (30-jun), `CI: corrige fallos preexistentes de lint y un test time-bomb` (24-jun), `fix(quality-gate): cierra 4 huecos del pipeline + 2 tests date-flaky` (09-jun). **Es un defecto sistémico de la suite, no un incidente aislado** — ver §15.6.

**Solución.** Fechas relativas al momento de ejecución, ancladas al día de la semana requerido, siempre dentro de la ventana. Verificado localmente: **8 tests pasan** (los 4 de cada archivo), `ruff check --select F,W6` limpio y `ruff format --check` limpio.

### 10.8 Segundo incidente de CI — ruff 0.16.0 empieza a formatear Markdown

**Síntoma.** El 27-jul-2026, tras el push del commit `28044fa` (que **solo agregaba este documento y actualizaba la bitácora**, ambos `.md`), el job `Lint (ruff)` falló:

```
unformatted: File would be reformatted
  --> docs/HANDOVER_TRAMITE_GLOSAS_ACEPTADAS.md:1:1
1 file would be reformatted, 868 files already formatted
```

**Causa raíz.** El workflow instala el linter **sin fijar versión** (`pip install ruff`). Entre la ejecución anterior y esta, ruff pasó de la serie 0.15 a **0.16.0**, versión que introduce el **formateo de bloques de código Python embebidos en archivos Markdown**. Los fragmentos ` ```python ` de este documento —escritos a mano para legibilidad— quedaron sujetos al formateador.

Detalle revelador del propio log: la corrida contaba **869 archivos** (`1 file would be reformatted, 868 files already formatted`), mientras que localmente con ruff 0.15.8 contaba **837**. Los 32 archivos de diferencia son los `.md` del repositorio, que la versión anterior ni siquiera miraba.

**Diagnóstico complementario.** En el contenedor de desarrollo había **dos binarios de ruff** (`/root/.local/bin/ruff` en 0.15.8, que sombreaba a `/usr/local/bin/ruff`), lo que ocultó el problema al intentar reproducirlo: el `ruff --version` del PATH seguía reportando la versión vieja aunque `pip` hubiera instalado la nueva. Hubo que invocar el binario por ruta absoluta para reproducir el fallo.

**Solución aplicada.** `ruff format` sobre el documento con la versión 0.16.0. Los tres cambios son **exclusivamente de espaciado, sin ninguna alteración semántica**:

1. Una comprensión de lista partida a mano en dos líneas se unificó en una sola (99 caracteres, dentro del límite de 100 del proyecto).
2. Los comentarios alineados con espacios múltiples en el bloque de constantes se normalizaron a dos espacios.
3. En el fragmento del Anexo C: se añadieron las dos líneas en blanco reglamentarias alrededor del `def` y se normalizó el *slice* `t[m.end():]` a `t[m.end() :]`.

Verificado con **ambas versiones**: `ruff format --check .` limpio en 0.16.0 (869 archivos) y en 0.15.8 (837 archivos), y `ruff check . --select F,W6` limpio.

**Implicación para el equipo, más allá de este documento.** Un linter sin versión fijada significa que **una publicación nueva de la herramienta puede tumbar el build sobre un commit que no cambió nada relevante** — exactamente lo que ocurrió aquí. Además, desde ahora **todo archivo Markdown del repositorio con bloques ` ```python ` queda sujeto al formateador**, incluidos `README.md`, `CHANGELOG.md`, `ARCHITECTURE.md` y los documentos de `docs/`. Ver riesgo **R11** y pendiente **§15.10**.

### 10.9 Archivos **NO** modificados que conviene declarar

Para tranquilidad de la integración, esta rama **no toca**: `app/` (ningún router, servicio, modelo o middleware), `alembic/`, `data/`, `static/`, `scripts/`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `pytest.ini`, `Dockerfile`, `docker-compose.yml`, `fly.toml`, `.github/workflows/`, ni ninguna otra herramienta de `tools/`.

---

## 11. Dependencias nuevas

### 11.1 Dependencias agregadas al proyecto: **NINGUNA**

`requirements.txt` y `requirements-dev.txt` **no fueron modificados**. El módulo usa exclusivamente `openpyxl` (ya presente, porque toda la familia `tools/` y el backend lo usan) y biblioteca estándar de Python.

### 11.2 Paquetes instalados **solo en el entorno efímero de desarrollo**

Estos **no** son dependencias del módulo. Se instalaron en el contenedor de la sesión para (a) poder manipular los Excel y (b) reproducir localmente el fallo del CI antes de corregirlo. **No deben añadirse a los requirements del proyecto por causa de esta rama** — la mayoría ya están allí por otras razones.

**Para el módulo:**

| Paquete | Versión | Para qué |
|---|---|---|
| `openpyxl` | 3.1.5 | Lectura/escritura de `.xlsx` |
| `et-xmlfile` | 2.0.0 | Transitiva de openpyxl |
| `ruff` | (última) | Reproducir los gates `ruff check` y `ruff format --check` del CI |

**Para reproducir la suite de tests localmente** (necesarias porque `pip install -r requirements-dev.txt` falla en este entorno, ver §11.3):

`pytest`, `pytest-asyncio`, `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `pydantic-settings`, `httpx`, `python-multipart`, `bcrypt<4`, `PyJWT`, `slowapi`, `jinja2`, `reportlab`, `anthropic`, `groq`, `alembic`, `email-validator`, `python-jose`, `passlib`, `apscheduler`, `cachetools`, `tenacity`, `aiofiles`, `requests`, `beautifulsoup4`, `rank_bm25`, `pdfplumber`, `holidays`, `psutil`, `PyPDF2`, `pillow`, `qrcode`, `posthog`.

**Nota sobre `bcrypt`:** hubo que fijar `bcrypt<4`. Con bcrypt 4.x los tests abortaban con `pyo3_runtime.PanicException: Python API call failed` al construir el `UsuarioRecord` de la fixture. **Este dato es útil para el equipo**: si alguien monta el entorno local y ve ese pánico, la causa es la versión de bcrypt, no su código.

### 11.3 Paquetes que **no** se pudieron instalar en el entorno

| Paquete | Error | Impacto |
|---|---|---|
| `http-ece` | `Could not build wheels` | Ninguno para este módulo. Es dependencia de notificaciones push web (VAPID), funcionalidad que fue retirada del proyecto el 09-may-2026 (`cleanup: push (VAPID no configurado)`). |
| `sgmllib3k` | `Could not build wheels` | Es dependencia de `feedparser` (ticker de noticias RSS, también retirado el 09-may-2026). Su fallo hace abortar el `pip install` completo de `requirements-dev.txt`, por eso hubo que instalar paquete por paquete. |

**Consecuencia práctica y advertencia para el equipo:** `pip install -r requirements-dev.txt` **falla en un entorno Linux limpio** por estos dos paquetes. El CI de GitHub Actions sí lo logra (usa runners con toolchain de compilación completo), pero un desarrollador nuevo se topará con esto. Ver §15.7.

---

## 12. Configuración

### 12.1 Variables de entorno requeridas por el módulo: **NINGUNA**

El módulo no lee `os.environ` en ningún punto. No usa `.env`, no usa `app/core/config.py`, no requiere `SECRET_KEY`, ni claves de API, ni cadena de conexión. **No maneja ningún secreto.**

### 12.2 Parámetros: los cuatro argumentos de línea de comandos

| Pos. | Nombre | Obligatorio | Descripción |
|---|---|---|---|
| 1 | `ACEPTADAS.xlsx` | Sí | Consolidado mensual de glosas aceptadas. Debe tener hoja `BD` con encabezados en la fila 4. |
| 2 | `CIRCULARIZACION.xlsx` | Sí | Archivo maestro de circularización. Debe tener hoja `GENERAL` con encabezados en la fila 2 y datos desde la 3. |
| 3 | `SALIDA.xlsx` | Sí | Ruta del archivo resultante. **Se recomienda que sea distinta de la 1** para conservar el original. |
| 4 | `REPORTE.csv` | No | Ruta del reporte de revisión. Si se omite, el reporte se imprime en consola. |

### 12.3 Configuración interna (constantes del módulo)

Si el formato de los Excel cambia, **solo hay que tocar estas líneas**:

```python
# Hoja BD del consolidado de glosas aceptadas (índices 0-based)
BD_FACTURA, BD_OBS, BD_VALOR = 2, 8, 9  # C, I, J
BD_RESPUESTA, BD_NUM, BD_FECHA, BD_TIPO_TRAMITE = 22, 23, 24, 26  # W, X, Y, AA
BD_HEADER_ROW = 4

# Hoja GENERAL de la circularización (índices 0-based)
GEN_FACTURA, GEN_VAL_ACEPTADO, GEN_ACTA, GEN_FECHA, GEN_CONCEPTO = 1, 5, 11, 12, 13  # B, F, L, M, N
```

**Nota:** `BD_TIPO_TRAMITE` (columna AA, `TRAMITE Y/O ACTA`, con valores `TRAMITE` / `ACTA`) está **definida pero no utilizada** en la versión entregada. Se dejó porque documenta el mapa completo de la hoja y porque es el gancho natural si en el futuro se quiere diferenciar el tratamiento de filas `TRAMITE` (objeciones) frente a `ACTA` (conciliaciones). Ver §15.2.

### 12.4 Rutas y convenciones

- **Ruta del módulo:** `tools/completar_tramite_glosas_aceptadas.py`, ejecutable desde la raíz del repositorio.
- **No requiere `PYTHONPATH`** ni instalación del paquete: no importa nada de `app/`.
- **Codificación del CSV:** `utf-8-sig` (BOM) para compatibilidad con Excel en español.
- **Formato de fecha escrito en Excel:** `dd/mm/yyyy`.

### 12.5 Configuración de CI que afecta a este módulo

El workflow `.github/workflows/*.yml` corre en `push` a `main`, `develop` y `claude/**`, y en `pull_request` contra `main` y `develop`. Tres jobs:

| Job | Comandos | Estado con esta rama |
|---|---|---|
| **Lint (ruff)** | `ruff check . --select F,W6` y `ruff format --check .` | ✅ Verde tras `496e2c7` |
| **Tests (pytest)** | `python -m pytest tests/ -v --tb=long --maxfail=5 --junitxml=junit.xml` con `SECRET_KEY`, `DATABASE_URL=sqlite:///./test_ci.db`, `PYTHONPATH`, `DISABLE_SCHEDULERS=1` | ✅ Corregido en `8a6f85d` |
| **Security scan (pip-audit)** | — | ✅ Verde desde el inicio |

**`DISABLE_SCHEDULERS=1` es obligatorio** para correr la suite: sin él, los `TestClient` acumulan tareas de asyncio hasta agotar la memoria del runner (documentado en el propio workflow).

---

## 13. Riesgos

### 13.1 Riesgos de integración — ordenados por probabilidad × impacto

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| **R1** | **La rama base no es `main`.** El repositorio tiene como default `motor-glosas`. Un `git merge` o un PR apuntando a `main` **falla con HTTP 422** (ocurrió en esta sesión al crear el PR). | Alta | Bloqueante | Al consolidar, verificar siempre `git remote show origin \| grep "HEAD branch"`. Existen además las ramas `master` y `flyio-new-files`, que **no** son la línea de trabajo. |
| **R2** | **Colisión en `CLAUDE.md`.** Si el proyecto principal ya tiene un `CLAUDE.md`, la fusión lo sobrescribe o entra en conflicto. | Alta | Medio | **Fusionar el contenido, no reemplazar el archivo.** El de esta rama tiene dos secciones independientes y ambas pueden convivir con otras instrucciones. |
| **R3** | **Colisión o duplicación de `BITACORA.md`.** Si otras ramas paralelas crearon su propia bitácora, habrá varias memorias en conflicto. | Alta | Alto | Elegir **una sola** bitácora canónica en la raíz del proyecto consolidado e **intercalar por fecha** el contenido de las demás. La de esta rama abarca abril–julio de 2026 completo, por lo que sirve de columna vertebral. |
| **R4** | **Los tests con bomba de tiempo vuelven a fallar.** Si otra rama trae la versión antigua de `test_heatmap_actividad.py` o `test_por_dia_semana.py`, la fusión puede revertir el arreglo y el CI se cae de nuevo — con una causa que parece inexplicable. | Media | Alto | Al resolver conflictos en esos dos archivos, **quedarse siempre con la versión que usa `_fecha_reciente()`**. Auditar la suite completa en busca de otras fechas fijas (§15.6). |
| **R5** | **`ruff format --check` corre sobre todo el repositorio.** Cualquier archivo sin formatear que llegue de otra rama tumba el gate de lint, aunque no tenga nada que ver con el cambio. | Media | Medio | Ejecutar `ruff format .` sobre el árbol consolidado **antes** del primer push, en un commit de formato separado. |
| **R6** | **Cambio de formato del Excel mensual.** Si el consolidado de otro mes tiene columnas en otro orden, el `assert` del encabezado aborta la corrida. | Media | Bajo | Es el comportamiento diseñado (falla ruidosa). Se corrige actualizando las constantes `BD_*`. |
| **R7** | **Pérdida del valor cacheado de la fórmula de totales.** openpyxl conserva la fórmula `=SUM(J5:J199)` en `J200`, pero **descarta su valor cacheado** al guardar. Excel lo recalcula solo al abrir, pero cualquier lectura programática (`pandas.read_excel`, `load_workbook(data_only=True)`) verá `None` en esa celda hasta que alguien abra y guarde el archivo. | Media | Bajo | Documentado. Si algún proceso aguas abajo lee ese total programáticamente, correr `python scripts/recalc.py <salida>` (existe en la skill `xlsx`) o abrir y guardar en Excel. Ver §15.3. |
| **R8** | **openpyxl y los elementos no soportados.** Al reescribir un `.xlsx`, openpyxl puede perder elementos que no modela (algunos gráficos, tablas dinámicas, ciertos objetos de dibujo). En los archivos procesados no había ninguno, pero un consolidado futuro podría traerlos. | Baja | Medio | Antes de entregar, comparar visualmente el archivo de salida con el original. La verificación programática que se hizo cubre valores de celda, no objetos gráficos. |
| **R9** | **Nombre de herramienta similar a otra existente.** Ya existe `tools/convertir_tramite_masivo.py`. Un desarrollador puede confundirlas. | Baja | Bajo | Los docstrings de ambas son explícitos. Considerar un `tools/README.md` índice. |
| **R10** | **Ejecución sobre el mismo archivo de entrada y salida.** Si alguien pasa la misma ruta en los argumentos 1 y 3, se sobrescribe el original y se pierde la posibilidad de comparar. | Baja | Medio | El módulo **no lo impide**. Ver §15.1. |
| **R11** | **El CI instala ruff sin versión fijada** (`pip install ruff`). Cada publicación nueva del linter puede tumbar el build sobre commits que no cambiaron nada relevante. Ya ocurrió el 27-jul-2026: ruff 0.16.0 empezó a formatear los bloques ` ```python ` de los `.md` y el gate falló sobre un commit de solo documentación (§10.8). Desde esa versión, **todo Markdown del repo con código Python embebido está sujeto al formateador** (`README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `docs/`). | Alta | Medio | Fijar la versión en el workflow (`pip install "ruff==0.16.0"`) y subirla deliberadamente, corriendo `ruff format .` en el mismo commit. Ver §15.10. |

### 13.2 Riesgos de datos (los que debe conocer el auditor, no el programador)

| # | Riesgo | Detalle |
|---|---|---|
| **RD1** | **Acta 786 no existe en la circularización 2026.** 11 notas crédito la citan; esas facturas figuran bajo el acta 879 (10 casos) o 862 (1 caso), ambas del 20/05/2026. El módulo escribió el número que registra la circularización. **Si el acta física es realmente la 786, hay 11 celdas con el número equivocado.** Decisión pendiente del auditor. |
| **RD2** | **19 filas con valor que no cuadra.** El acta registra un valor mayor al de la nota crédito (ej.: acta $19.206 vs nota $5.746). La hipótesis es que el resto se acreditó en otra nota. El módulo usó el texto de la observación, cuyo valor **sí** coincide con la nota. Requiere validación. |
| **RD3** | **21 filas del acta 599 (vigencia 2025).** No están en la circularización 2026 y se llenaron íntegramente desde la observación de la nota crédito. Es correcto, pero el dato no está corroborado contra una fuente independiente. |
| **RD4** | **Discrepancia en `HUS0000384193` (acta 604).** El acta suma $113.700 y la nota crédito es por $52.100. Reportado al auditor al entregar `archivo.xlsx` y `archivo_1.xlsx`. |
| **RD5** | **Las notas crédito citan actas de conciliación que a veces corresponden a otra entidad.** Caso concreto: tres facturas del Dispensario Nivel II Bogotá citaban «acta 862» (que es del Dispensario Bucaramanga); su conciliación real es el **acta 806 del 12/06/2026**. El módulo lo detectó y corrigió automáticamente, dejando la nota en el CSV. Es un error de captura recurrente que vale la pena atacar en el origen. |

---

## 14. Dependencias con otros módulos

### 14.1 Qué necesita este módulo

| Necesita | Tipo | Naturaleza |
|---|---|---|
| `openpyxl` | Paquete Python | Ya en `requirements.txt` |
| Archivo consolidado mensual de glosas aceptadas | **Dato externo** | Producido por el flujo de notas crédito del área. No lo genera este repositorio. |
| Archivo `CIRCULARIZACIÓN DE GLOSAS <AÑO>.xlsx` | **Dato externo** | Mantenido manualmente por el área de conciliaciones. **Es la dependencia crítica: si está desactualizado, el módulo llena con datos viejos.** |

**No importa nada de `app/`.** No depende de la base de datos, ni de la configuración, ni de los servicios de IA, ni de la autenticación. **Puede extraerse del repositorio y correr aislado** con solo `openpyxl` instalado. Esto es intencional y facilita enormemente la consolidación.

### 14.2 Qué usa este módulo (hoy: nadie)

Ningún componente del proyecto lo invoca. Es una hoja del árbol de dependencias.

### 14.3 Relaciones conceptuales (familia funcional, sin acoplamiento de código)

Este módulo pertenece al **frente de notas crédito y conciliaciones**, que agrupa:

| Herramienta | Relación |
|---|---|
| `tools/extraer_notas_credito.py` | Extrae los documentos de nota crédito del share. **Aguas arriba.** |
| `tools/renombrar_y_organizar_notas.py` | Renombra y organiza los PDF por carpeta/gestor. **Aguas arriba.** |
| `tools/consolidar_carpetas_notas.py` | Deja solo NC.pdf + XML + CUV.json por carpeta. **Aguas arriba.** |
| `tools/verificar_cuv_notas.py` | Verifica el CUV (validación MinSalud) de cada nota. **Paralelo.** |
| `tools/dividir_notas_por_acta.py` | Decide qué notas van por correo y cuáles por SIMED, según el acta. **Consume el mismo concepto de «acta» que este módulo.** |
| `tools/responder_glosas_simed.py` | Carga las notas crédito y sus soportes al portal SIMED. **Aguas abajo.** |
| `tools/convertir_tramite_masivo.py` | Convierte formatos de trámite masivo. **Familia afín, sin relación directa.** |
| **`tools/completar_tramite_glosas_aceptadas.py`** | **Cierra el ciclo documental: deja el consolidado contable listo y auditable.** |

**El vínculo conceptual más fuerte es con `dividir_notas_por_acta.py`**, porque ambos interpretan el número de acta desde el texto de la nota crédito. Si en la consolidación se decide unificar esa lógica de parseo en una utilidad compartida, esos dos son los candidatos naturales (ver §15.8).

### 14.4 Relación de la Bitácora con el resto del proyecto

`BITACORA.md` y `CLAUDE.md` son **transversales a todo el repositorio**: no dependen de ningún módulo y todos los módulos (y todas las sesiones futuras) dependen de ellos como fuente de contexto. En la consolidación deben quedar en la **raíz del proyecto principal**, no dentro de una carpeta de módulo.

---

## 15. Pendientes

### 15.1 Del módulo — mejoras identificadas y no implementadas

| # | Pendiente | Por qué no se hizo | Prioridad sugerida |
|---|---|---|---|
| **P1** | **Tests unitarios del módulo.** No hay ni un test para `buscar_subconjunto()`, `parsear_obs()` ni `resolver_fila()`, que son lógica no trivial y perfectamente testeable (funciones puras). | La sesión priorizó entregar el Excel diligenciado, que era la necesidad inmediata del auditor. | **Alta** — es la deuda técnica más relevante que deja esta entrega. |
| **P2** | **Guarda contra entrada = salida.** Si se pasa la misma ruta como argumento 1 y 3, se sobrescribe el original sin aviso. | No se detectó durante el uso real. | Media |
| **P3** | **Modo `--dry-run`.** Mostrar qué se llenaría sin escribir el archivo. | No se pidió. | Baja |
| **P4** | **Parametrizar el nombre de las hojas.** `"BD"` y `"GENERAL"` están fijos en el código. | Son estables mes a mes. | Baja |
| **P5** | **Resumen estadístico al final de la corrida.** Hoy imprime cuántas filas llenó y cuántas notas generó, pero no el desglose (cuántas por match exacto, cuántas por fallback). | No se pidió. | Baja |

### 15.2 Código presente pero no utilizado

`BD_TIPO_TRAMITE = 26` (columna AA) está definida y nunca se usa. Deliberado: documenta el mapa completo y es el gancho para diferenciar filas `TRAMITE` de filas `ACTA`. **Si el equipo prefiere código sin residuos, puede eliminarse sin ningún efecto.** Nótese que `ruff` con las reglas del proyecto no la marca por ser una constante de módulo.

### 15.3 Recálculo de fórmulas no ejecutado

La guía de la skill `xlsx` indica correr `scripts/recalc.py` (LibreOffice headless) sobre cualquier libro con fórmulas después de escribirlo con openpyxl, para regenerar los valores cacheados. **No se ejecutó.** Motivos: el archivo tiene una sola fórmula (`J200`), no fue modificada, y Excel la recalcula al abrir. El impacto es el descrito en **R7**. Si el flujo aguas abajo llegara a leer ese total programáticamente, hay que ejecutarlo.

### 15.4 Los scripts de llenado de `#N/D` no quedaron versionados

Los dos últimos encargos de la sesión (`archivo.xlsx` y `archivo_1.xlsx`, celdas V6 y V7) se resolvieron con **scripts en línea ejecutados en el scratchpad**, no con un archivo del repositorio. La lógica de extracción es una variante de `parsear_obs()` con anclas ampliadas (`EN LA CUAL` → `FIRMADA POR ... .` → `DONDE`).

**Recomendación:** si ese formato de archivo (`Hoja1`, encabezados en filas 4–5, columna V con `#N/D`) se repite mensualmente, promoverlo a una herramienta propia —por ejemplo `tools/completar_respuesta_glosa_inicial.py`— reutilizando `parsear_obs()`. La lógica exacta usada queda registrada en el [Anexo C.3](#c3-lógica-de-llenado-de-nd-no-versionada) de este documento para no perderla.

### 15.5 Integración opcional con la aplicación web

Explorada conceptualmente y **descartada para esta entrega** (decisión D1). Si en el futuro se quisiera, el camino natural sería un endpoint que reciba ambos Excel, ejecute `resolver_fila()` y devuelva el resultado. La arquitectura del módulo lo permite sin refactor: la lógica de negocio está aislada de la I/O.

### 15.6 Auditoría pendiente de bombas de tiempo en la suite de tests

**Este es el pendiente más importante para el proyecto principal, más allá de este módulo.**

Se corrigieron los dos archivos que fallaron. **No se auditó el resto de la suite** (4.081 tests) en busca del mismo patrón. Dado que el defecto ya se manifestó al menos cuatro veces en el proyecto (09-jun, 24-jun, 30-jun y 22-jul), es muy probable que haya más tests con fechas fijas esperando su turno.

**Acción recomendada:** un barrido buscando literales de fecha en `tests/` (`datetime(2026`, `"2026-`, `date(2026`) y convertir a fechas relativas todos los que alimenten endpoints con ventana móvil. Es un trabajo acotado y de alto retorno: elimina una clase entera de fallos que aparecen "solos" y confunden a quien esté trabajando en otra cosa.

### 15.7 `requirements-dev.txt` no instalable en entorno limpio

`pip install -r requirements-dev.txt` falla en Linux limpio por `http-ece` y `sgmllib3k` (§11.3). Ambos son dependencias de funcionalidades **ya retiradas del proyecto** el 09-may-2026 (notificaciones push VAPID y ticker de noticias RSS).

**Acción recomendada:** revisar si siguen siendo necesarios en los requirements. Si no, retirarlos: el entorno de desarrollo quedaría instalable de una sola pasada.

### 15.8 Unificación del parseo de actas

`parsear_obs()` de este módulo y la lógica de `tools/dividir_notas_por_acta.py` interpretan el mismo dato (el número de acta dentro del texto de la nota crédito) por caminos separados. Candidatos a unificarse en una utilidad compartida durante la consolidación.

### 15.9 Pendientes de negocio heredados (registrados en `BITACORA.md`)

No son de este módulo, pero forman parte del estado que esta rama documenta y **no deben perderse en la consolidación**:

1. **Lote V2 del Dispensario — 12 notas crédito, ~$8,7 millones.** 9 dependen de SISTEMAS (RIPS sin validar por el servicio `dockerrips.hus.gov.co:9443` caído, o rechazado por MinSalud con código RVC086), 2 requieren descargar el PDF del DIAN (Cartera) y 1 confirmar el número de nota con Facturación (`HUS440328`, NE histórico 302111). Falta seguimiento a SISTEMAS y, cuando validen, re-correr `diagnosticar_local.ps1` y radicar en SIMED.
2. **Casos por confirmar del Excel de junio:** los tres bloques descritos en **RD1**, **RD2** y **RD3**.
3. **PR #166** pendiente de aprobar y fusionar.
4. **Checklist técnico de la auditoría de mayo** (`AUDIT_CHECKLIST.md`): siguen abiertos los puntos de seguridad de nivel medio (endurecer `migracion_emergencia` y `dedup_historial` en `admin.py`, exigir `password_actual` al cambiar contraseña, aplicar rate-limit a `/auth/login`, `/usuarios/{id}/password` y los endpoints de 2FA) y los de consistencia de datos en `contratos.py` y `glosas.py`. **Los puntos relativos a Fly.io ya no aplican**: el despliegue se retiró el 08-jul-2026 y todo corre en servidor propio del HUS.
5. **Robot de Dinámica Gerencial** (`tools/responder_glosas_dgh.py`): quedó en piloto con modo `--calibrar`; falta puesta en marcha completa en la máquina del HUS.

### 15.10 Fijar la versión de ruff en el CI

El workflow instala el linter con `pip install ruff` sin versión. El 27-jul-2026 eso hizo fallar el gate de lint sobre un commit de solo documentación, porque ruff 0.16.0 empezó a formatear los bloques de código Python dentro de los Markdown (incidente completo en §10.8, riesgo **R11**).

**Acción recomendada:** fijar `pip install "ruff==0.16.0"` en `.github/workflows/` (y en `.pre-commit-config.yaml` si aplica), y subir de versión deliberadamente: en el mismo commit del cambio de versión, correr `ruff format .` sobre todo el árbol para absorber los cambios de formato de la versión nueva. **No se hizo en esta rama** porque tocar el workflow del CI excede el alcance de la entrega y merece su propio cambio revisado.

### 15.11 Errores conocidos del módulo

**Ninguno.** No se detectó ningún defecto funcional durante el desarrollo, la verificación ni el uso real. Las limitaciones conocidas son las de §15.1 y §15.2, que son ausencias de funcionalidad, no fallos.

---

## 16. Recomendaciones para fusionarlo

### 16.1 Orden de integración recomendado

Los cuatro commits son **independientes entre sí** y pueden integrarse por separado. Orden sugerido, de menor a mayor riesgo:

```
1º  8a6f85d  test: fechas relativas               → arregla el CI. Integrar PRIMERO.
2º  496e2c7  style: ruff format                   → deja el gate de lint verde.
3º  c11fb6f  tools: completar_tramite_...         → el módulo. Puramente aditivo.
4º  d3f95f2  docs: BITACORA.md + CLAUDE.md        → requiere decisión de fusión de contenido.
```

**Razón del orden:** integrando primero los arreglos de CI, cualquier problema que aparezca después es atribuible sin ambigüedad al código nuevo.

### 16.2 Procedimiento paso a paso

**Paso 1 — Verificar la rama base.**
```bash
git remote show origin | grep "HEAD branch"     # debe decir: motor-glosas
```
⚠️ **No asumir `main`.** Crear un PR contra `main` devuelve HTTP 422 (ocurrió en esta sesión).

**Paso 2 — Traer la rama.**
```bash
git fetch origin claude/excel-glosas-aceptadas-campos-l3ru9n
git log --oneline origin/motor-glosas..origin/claude/excel-glosas-aceptadas-campos-l3ru9n
```
Deben aparecer los cuatro commits.

**Paso 3 — Integrar el módulo (sin conflicto posible).**
`tools/completar_tramite_glosas_aceptadas.py` es un archivo nuevo que no existe en ninguna otra rama. Se puede hacer `git cherry-pick c11fb6f` o copiar el archivo directamente.

**Paso 4 — Integrar los arreglos de tests (conflicto posible).**
Si otra rama modificó `test_heatmap_actividad.py` o `test_por_dia_semana.py`, al resolver el conflicto **conservar la función `_fecha_reciente()` y las llamadas que la usan**. Criterio simple: *si en el archivo consolidado queda algún `datetime(2026, ...)` sembrando datos, el arreglo se perdió.*

**Paso 5 — Integrar la Bitácora (requiere decisión).**
- Si el proyecto principal **no** tiene bitácora: copiar `BITACORA.md` tal cual a la raíz.
- Si **ya** tiene: **intercalar por fecha**, no reemplazar. La de esta rama cubre abril–julio de 2026 completo y sirve de columna vertebral; el contenido de otras ramas se inserta en las fechas correspondientes. Unificar también la sección **PENDIENTE** (sin perder ninguno de los 5 bloques de §15.9) y reescribir **PARA MAÑANA** con la prioridad consolidada.

**Paso 6 — Integrar `CLAUDE.md` (fusionar, no reemplazar).**
Si ya existe uno, **añadir** la sección «Bitácora obligatoria» al existente. Es autocontenida y no contradice otras instrucciones. Verificar que la ruta que menciona (`BITACORA.md`) coincida con dónde quedó el archivo.

**Paso 7 — Normalizar formato antes del primer push.**
```bash
ruff format .
ruff check . --select F,W6
```
En un commit de formato separado, para que el gate de lint no falle por deuda ajena (riesgo **R5**).

**Paso 8 — Correr la suite completa.**
```bash
SECRET_KEY=ci-test-secret DATABASE_URL=sqlite:///./test.db \
PYTHONPATH=$(pwd) DISABLE_SCHEDULERS=1 \
python -m pytest tests/ -q
```
Referencia: **4.081 tests** (4.078 verdes + los 3 corregidos) en ~4 minutos en el runner de CI.

**Paso 9 — Prueba funcional de humo del módulo.**
Con un consolidado real y su circularización:
```bash
python tools/completar_tramite_glosas_aceptadas.py \
    "ARCHIVO <MES> <AÑO>-GLOSAS ACEPTADAS.xlsx" \
    "CIRCULARIZACIÓN DE GLOSAS <AÑO>.xlsx" \
    "SALIDA.xlsx" "reporte.csv"
```
Verificar: (a) el conteo de filas diligenciadas es el esperado, (b) el CSV tiene sentido, (c) abrir el `.xlsx` y comprobar que las filas previas y la fórmula de totales están intactas.

**Paso 10 — Cerrar el PR #166** una vez integrado, para que nadie lo fusione dos veces.

### 16.3 Qué **no** hacer

- ❌ **No** fusionar contra `main` (riesgo R1).
- ❌ **No** reemplazar un `CLAUDE.md` o `BITACORA.md` existente sin fusionar el contenido (R2, R3).
- ❌ **No** descartar los cambios de los dos archivos de tests al resolver conflictos (R4).
- ❌ **No** agregar a `requirements.txt` los paquetes de §11.2: **no** son dependencias de este módulo.
- ❌ **No** correr el módulo con la misma ruta de entrada y salida hasta que se implemente **P2**.

### 16.4 Verificación post-fusión (lista de comprobación)

- [ ] `tools/completar_tramite_glosas_aceptadas.py` existe y se ejecuta sin argumentos mostrando el manual.
- [ ] `BITACORA.md` en la raíz, con el historial abril–julio 2026 y los 5 bloques de PENDIENTE.
- [ ] `CLAUDE.md` en la raíz, con la sección «Bitácora obligatoria».
- [ ] `grep -rn "datetime(2026" tests/test_api/test_heatmap_actividad.py tests/test_api/test_por_dia_semana.py` no devuelve nada.
- [ ] `ruff check . --select F,W6` → limpio.
- [ ] `ruff format --check .` → limpio.
- [ ] Suite completa en verde.
- [ ] Prueba de humo del módulo sobre un consolidado real.
- [ ] PR #166 cerrado.

---

## 17. Resumen ejecutivo

### 17.1 Qué es esto, en un párrafo

Una herramienta de línea de comandos que **diligencia automáticamente las tres columnas de trámite/acta del consolidado mensual de glosas aceptadas**, cruzando cada nota crédito contra el archivo maestro de circularización de glosas, con validación aritmética de que el valor acreditado coincida con lo pactado en el acta, y generación de un reporte de excepciones para el auditor. Más, en la misma rama, **la bitácora del proyecto como memoria común de todas las sesiones de desarrollo** y **la corrección de dos fallos de CI** que bloqueaban la integración.

### 17.2 Lo que un desarrollador nuevo debe saber para mantenerlo

**1. Es determinista a propósito.** No usa IA en ejecución. Si alguien propone "mejorarlo con el motor de glosas", la respuesta es no, y la razón está en §8.1: es un dato contable que debe ser literal, trazable y reproducible ante una auditoría.

**2. Toda la política de negocio vive en `resolver_fila()`.** Cualquier cambio de criterio (qué acta prevalece, qué hacer cuando el valor no cuadra) se hace ahí y en ningún otro sitio. Las demás funciones son mecánica.

**3. La regla de oro es la suma exacta.** El `VALOR ACEPTADO` de la nota crédito **debe** coincidir con la suma de los conceptos que se escriben en la respuesta. `buscar_subconjunto()` es el corazón de la correctitud; si se rompe, el módulo escribe textos que no corresponden al valor acreditado y eso es un error contable, no cosmético.

**4. Nunca toca lo que ya está lleno.** Solo escribe donde W, X e Y están las tres vacías. Las filas ya diligenciadas son trabajo humano y son la referencia de estilo.

**5. Cuidado con las celdas "vacías" que no lo están.** En el consolidado real las celdas pendientes contenían un espacio en blanco, no `None`. Por eso todo pasa por `limpiar()`. Si alguien "optimiza" quitando esa llamada, el módulo dejará de detectar filas pendientes y no llenará nada, en silencio.

**6. El `assert` del encabezado es un seguro, no un estorbo.** Si el formato del Excel cambia, es preferible que aborte a que llene columnas equivocadas. No lo quiten; actualicen las constantes `BD_*`.

**7. El reporte CSV es parte del entregable, no un log.** Las 54 notas de junio no son ruido: son las filas donde un humano debe decidir. Entregar el Excel sin el CSV es entregar la mitad.

**8. La rama base del repositorio es `motor-glosas`, no `main`.**

**9. La suite de tests tiene bombas de tiempo.** Se corrigieron dos archivos; casi seguro quedan más (§15.6). Si un día el CI falla con `assert 0 == 2` en un test que no tocaron, miren primero si el test siembra fechas fijas.

**10. La deuda técnica declarada es P1: faltan tests unitarios del módulo.** Las funciones son puras y triviales de testear. Es lo primero que haría falta si el módulo va a evolucionar.

### 17.3 Estado de entrega

| Ítem | Estado |
|---|---|
| Módulo `completar_tramite_glosas_aceptadas.py` | ✅ Funcionando, usado en producción real (junio 2026) |
| Excel de junio 2026 diligenciado | ✅ Entregado al auditor — 76 filas, 228 celdas |
| Reporte de revisión (54 notas) | ✅ Entregado |
| `archivo.xlsx` y `archivo_1.xlsx` (celdas `#N/D`) | ✅ Entregados — 2 celdas cada uno |
| `BITACORA.md` + `CLAUDE.md` | ✅ En la rama, protocolo verificado |
| Arreglos de CI | ✅ Lint verde; tests corregidos y verificados localmente |
| PR #166 | 🟡 Abierto en borrador, pendiente de aprobación |
| Tests unitarios del módulo | ❌ Pendiente (P1) |

---

## Anexo A — Código fuente completo del módulo

`tools/completar_tramite_glosas_aceptadas.py`, versión vigente al 27-ago-2026 (505 líneas):

```python
"""Completa RESPUESTA/NO/FECHA DE TRAMITE Y/O ACTA en el consolidado de glosas aceptadas.

Cruza el archivo mensual de glosas aceptadas contra la hoja GENERAL de la
CIRCULARIZACION DE GLOSAS y llena, en las filas que les falte la respuesta:

  - RESPUESTA TRAMITE GLOSA Y/O ACTA  (conceptos de conciliacion unificados)
  - NO DE TRAMITE Y/O ACTA            (numero de acta; solo si viene vacio)
  - FECHA DE TRAMITE Y/O ACTA         (fecha de firma; solo si viene vacio)

El formato del consolidado cambia de un mes a otro (nombre de la hoja, fila de
encabezados y posicion de las columnas), asi que TODO se detecta por el texto
del encabezado, nunca por posicion fija. Los meses vistos hasta hoy:

  jun-2026  hoja "BD"              encabezados fila 4   respuesta en col W
  jul-2026  hoja "BD VLR ACEPTADO" encabezados fila 3   respuesta en col X

Reglas de resolucion, por fila a completar:
  1. Se busca la factura en GENERAL. Si la fila ya trae numero de acta, se usa
     ese; si no, el que se pueda leer en la observacion de la nota credito.
  2. Se escribe UN PARRAFO POR CADA GLOSA ACEPTADA del acta (valor aceptado > 0),
     separados por una linea en blanco. NO se agrupan los que repiten texto:
     dos renglones iguales son dos glosas distintas y agruparlos escondería la
     plata de uno de ellos. Las glosas de valor 0 (las que la entidad levanto,
     las ratificadas y las que la ESE no acepto) NO entran: no pintan en una
     nota credito y su texto dice lo contrario de lo que la nota documenta.
  3. Si el acta no registra nada aceptado para esa factura, o la factura no esta
     en la circularizacion (p.ej. actas de vigencia anterior), la respuesta se
     toma del texto de la propia observacion de la nota credito (la parte
     posterior a "DONDE"/"EN LA CUAL").
  4. Numero y fecha solo se escriben si la celda venia vacia: nunca se pisa un
     dato que ya puso el auditor.
  5. Cuando lo aceptado en el acta no coincide con lo que acredito la nota, se
     escribe el aviso en una columna nueva al final ("NOVEDAD ACEPTADO VS NOTA
     CREDITO") y tambien queda en el reporte CSV.

Uso:
    python tools/completar_tramite_glosas_aceptadas.py ACEPTADAS.xlsx CIRCULARIZACION.xlsx SALIDA.xlsx [REPORTE.csv] [--rehacer]

    --rehacer  reescribe tambien las filas de tipo ACTA que ya tienen respuesta
               (para volver a correr sobre un archivo ya diligenciado). Las de
               tipo TRAMITE nunca se tocan.
"""

import csv
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl

# Lector unico de pesos colombianos, compartido por todos los bots de tools/
# (ver tools/_dinero.py). El que vivia aqui solo quitaba comas, asi que un
# valor escrito "1.234.567" lo leia como cero.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dinero import a_entero, a_texto  # noqa: E402

# Encabezados que identifican cada columna del consolidado. Se compara por
# "contiene", sobre el texto normalizado (mayusculas y sin tildes), asi que
# basta con un fragmento distintivo. El orden importa: gana el primero que
# aparezca en la fila de encabezados.
COLUMNAS_BD = {
    "factura": ["FACTURA"],
    "obs": ["OBSERVC NOTA CREDITO", "OBSERVC NTA", "OBSERVACION NOTA", "OBSERVC"],
    "valor": ["VALOR ACEPTADO", "VLR NOTA", "VALOR NOTA"],
    "respuesta": ["RESPUESTA TRAMITE"],
    "num": ["NO DE TRAMITE", "N DE TRAMITE", "NRO DE TRAMITE"],
    "fecha": ["FECHA DE TRAMITE"],
    "tipo_tramite": ["TRAMITE Y/O ACTA"],
}
# Columnas cuyo nombre esta contenido en el de otra ("FACTURA" dentro de "VALOR
# FACTURA"; "TRAMITE Y/O ACTA" dentro de "NO DE TRAMITE Y/O ACTA"): para estas
# se exige que el encabezado sea exactamente el alias, no que lo contenga.
EXACTAS = {"factura", "tipo_tramite"}

# Columnas (0-based) de la hoja GENERAL de la circularizacion (estable)
GEN_FACTURA, GEN_VAL_ACEPTADO, GEN_ACTA, GEN_FECHA, GEN_CONCEPTO = 1, 5, 11, 12, 13

RE_ACTA = re.compile(r"ACTA\s*(?:DE\s+CONCILIACI\w+\s*)?(?:N[O°ºRo\.\s]{0,4})?\s*(\d{3,4})", re.I)
RE_SOLO_NUM = re.compile(r"(\d{3,4})")
RE_FECHA_DMA = re.compile(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})")
MESES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}
RE_FECHA_TEXTO = re.compile(r"(\d{1,2})\s+DE\s+(" + "|".join(MESES) + r")\s+DE\s+(\d{4})", re.I)


def limpiar(texto):
    if texto is None:
        return ""
    return str(texto).replace("_x000D_", "").replace("\r", "").strip()


def normalizar(v):
    """Mayusculas y sin tildes, para comparar encabezados entre meses."""
    s = unicodedata.normalize("NFD", limpiar(v).upper())
    return " ".join("".join(ch for ch in s if not unicodedata.combining(ch)).split())


def a_numero(v):
    """Pesos enteros con el lector compartido de tools/_dinero.py."""
    return a_entero(v)


def a_fecha(v):
    if isinstance(v, datetime):
        return v
    s = limpiar(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


RE_CIFRA = re.compile(r"\$\s*(\d[\d.,]*\d|\d)")


def cifra_encabezado(texto):
    """Primera cifra en pesos que aparece en el texto de un renglon del acta.

    La circularizacion mezcla separadores de miles: unas filas escriben
    $163.325 y otras $163,325. Se aceptan los dos. Si al final hay un
    separador seguido de exactamente dos digitos Y antes venia otro
    separador, esos dos digitos son centavos y se descartan ($1.234,50).
    """
    m = RE_CIFRA.search(texto or "")
    if not m:
        return None
    return a_entero(m.group(1))


def numero_de_acta(v):
    """Lee el numero de una celda de acta: 862, '862', 'Acta No. 828'."""
    s = limpiar(v)
    if not s:
        return None
    m = RE_ACTA.search(s) or RE_SOLO_NUM.search(s)
    return int(m.group(1)) if m else None


def parsear_obs(obs):
    """Extrae (acta, fecha, respuesta) de la observacion de la nota credito."""
    texto = limpiar(obs)
    m = RE_ACTA.search(texto)
    acta = int(m.group(1)) if m else None
    fecha = None
    resto = texto[m.end() :] if m else texto
    mf = RE_FECHA_DMA.search(resto[:60])
    if mf:
        d, mth, y = (int(x) for x in mf.groups())
        try:
            fecha = datetime(y, mth, d)
        except ValueError:
            fecha = None
    else:
        mt = RE_FECHA_TEXTO.search(resto[:80])
        if mt:
            try:
                fecha = datetime(int(mt.group(3)), MESES[mt.group(2).upper()], int(mt.group(1)))
            except ValueError:
                fecha = None

    respuesta = ""
    ancla = re.search(r"DONDE\s*:?|EN LA CUAL\s*[;:]?", resto, re.I)
    if ancla:
        respuesta = resto[ancla.end() :]
    else:
        inicio = re.search(r"EN CONCILI\w+|ESE HUS", resto, re.I)
        if inicio:
            respuesta = resto[inicio.start() :]
    respuesta = respuesta.strip(" :;,.\n")
    # colapsa el texto cuando la observacion trae la misma respuesta duplicada
    mitad = len(respuesta) // 2
    if mitad > 40:
        a, b = respuesta[:mitad].strip(" .\n"), respuesta[mitad:].strip(" .\n")
        if a and a == b:
            respuesta = a
    return acta, fecha, respuesta.strip()


def buscar_subconjunto(vals, objetivo):
    """Indices cuyo valor suma exactamente `objetivo`; None si no existe.

    Solo se devuelven glosas con valor aceptado > 0. Las de valor 0 son las
    que la entidad levanto o que la ESE no acepto: sumar cero no altera el
    total, asi que si se incluyeran la comprobacion de "cuadra exacto" las
    dejaria pasar y el texto de una nota credito terminaria diciendo "ESE HUS
    NO ACEPTA GLOSA", que es lo contrario de lo que la nota documenta.
    """
    no_cero = [(i, v) for i, v in enumerate(vals) if v > 0]
    if objetivo == sum(v for _, v in no_cero):
        return [i for i, _ in no_cero]
    for i, v in no_cero:
        if v == objetivo:
            return [i]
    alcanzables = {0: []}
    for i, v in no_cero:
        nuevos = {}
        for s, idxs in alcanzables.items():
            ns = s + v
            if ns <= objetivo and ns not in alcanzables and ns not in nuevos:
                nuevos[ns] = idxs + [i]
        alcanzables.update(nuevos)
        if len(alcanzables) > 500000:
            break
    return alcanzables.get(objetivo)


def cargar_general(ruta):
    wb = openpyxl.load_workbook(ruta, read_only=True)
    ws = wb["GENERAL"]
    por_factura = defaultdict(list)
    for fila in ws.iter_rows(min_row=3, values_only=True):
        factura = limpiar(fila[GEN_FACTURA])
        if not factura.upper().startswith("HUS"):
            continue
        por_factura[factura.upper()].append(
            {
                "val": a_numero(fila[GEN_VAL_ACEPTADO]),
                "acta": numero_de_acta(fila[GEN_ACTA]),
                "fecha": a_fecha(fila[GEN_FECHA]),
                "concepto": limpiar(fila[GEN_CONCEPTO]),
            }
        )
    wb.close()
    return por_factura


def localizar_hoja_y_encabezados(wb, hoja_pedida=None):
    """Devuelve (worksheet, fila_encabezados, {campo: indice_0based}).

    Busca en cada hoja la fila (entre las 15 primeras) que contenga el
    encabezado de RESPUESTA TRAMITE, que es la columna que da sentido al
    archivo. Sobre esa fila mapea el resto de columnas por nombre.
    """
    hojas = [wb[hoja_pedida]] if hoja_pedida else wb.worksheets
    for ws in hojas:
        for nfila, fila in enumerate(ws.iter_rows(min_row=1, max_row=15), 1):
            encabezados = [normalizar(c.value) for c in fila]
            if not any("RESPUESTA TRAMITE" in h for h in encabezados):
                continue
            mapa = {}
            for campo, alias in COLUMNAS_BD.items():
                for idx, h in enumerate(encabezados):
                    if not h:
                        continue
                    hit = (
                        any(h == a for a in alias)
                        if campo in EXACTAS
                        else any(a in h for a in alias)
                    )
                    if hit:
                        mapa[campo] = idx
                        break
            faltan = {"factura", "obs", "valor", "respuesta", "num", "fecha"} - set(mapa)
            if faltan:
                raise SystemExit(
                    f"En la hoja '{ws.title}' fila {nfila} no se hallaron las columnas: "
                    f"{sorted(faltan)}. Encabezados leidos: "
                    f"{[h for h in encabezados if h][:30]}"
                )
            return ws, nfila, mapa
    raise SystemExit(
        "No se encontro ninguna hoja con la columna 'RESPUESTA TRAMITE GLOSA Y/O ACTA'. "
        f"Hojas del archivo: {wb.sheetnames}"
    )


def resolver_fila(factura, valor, obs, acta_fila, general):
    """Devuelve (respuesta, acta, fecha, notas_de_revision).

    `acta_fila` es el numero de acta que ya trae la fila (o None). Cuando
    existe manda sobre el que se lea en la observacion: lo puso el auditor.
    """
    acta_obs, fecha_obs, resp_obs = parsear_obs(obs)
    acta_ref = acta_fila or acta_obs
    notas = []
    if acta_fila and acta_obs and acta_fila != acta_obs:
        notas.append(f"la fila dice acta {acta_fila} y la observacion dice acta {acta_obs}")
    candidatas = general.get(factura.upper(), [])

    grupo = []
    if candidatas:
        por_acta = defaultdict(list)
        for c in candidatas:
            por_acta[c["acta"]].append(c)
        if acta_ref in por_acta:
            grupo = por_acta[acta_ref]
        else:
            con_cuadre = [
                g for g in por_acta.values() if buscar_subconjunto([c["val"] for c in g], valor)
            ]
            candidatos = con_cuadre or list(por_acta.values())
            grupo = max(candidatos, key=lambda g: g[0]["fecha"] or datetime.min)
            if acta_ref and grupo:
                notas.append(
                    f"la NC cita acta {acta_ref}; circularizacion la registra en acta {grupo[0]['acta']}"
                )

    if grupo:
        acta, fecha = grupo[0]["acta"], grupo[0]["fecha"]
        # Solo lo ACEPTADO. Las glosas de valor 0 son las que la entidad levanto,
        # las que se ratificaron o las que la ESE no acepto: no pintan en una nota
        # credito. Se escribe un parrafo por cada renglon aceptado, SIN agrupar los
        # que repiten texto, porque dos renglones iguales son dos glosas y agrupar
        # los esconderia la plata de uno de ellos.
        aceptadas = [c for c in grupo if c["val"] > 0]
        if aceptadas:
            conceptos = [c["concepto"] for c in aceptadas if c["concepto"]]
            sin_aceptar = [c for c in aceptadas if "ACEPTA" not in c["concepto"].upper()]
            if sin_aceptar:
                notas.append(
                    f"{len(sin_aceptar)} renglon(es) tienen valor aceptado pero su texto "
                    f"no dice que la ESE acepte: revisar redaccion en la circularizacion"
                )
            # El valor registrado del renglon y la cifra que su texto anuncia
            # pueden no coincidir: el acta se digita a mano. Se comparan uno a
            # uno. Ojo con el patron habitual de que el PRIMER renglon encabeza
            # con el total de la nota y despues desglosa los servicios: eso no
            # es un error de plata, solo de redaccion, y se avisa aparte.
            descuadres, encabeza_total = [], 0
            for c in aceptadas:
                cifra = cifra_encabezado(c["concepto"])
                if cifra is None or cifra == c["val"]:
                    continue
                if cifra == valor:
                    encabeza_total += 1
                else:
                    descuadres.append((cifra, c["val"]))
            avisos = []
            if descuadres:
                detalle = "; ".join(
                    f"el texto dice {a_texto(x)} pero el valor aceptado es {a_texto(y)}"
                    for x, y in descuadres[:3]
                )
                mas = f" (y {len(descuadres) - 3} mas)" if len(descuadres) > 3 else ""
                avisos.append(f"Texto del acta descuadrado con su propio valor: {detalle}{mas}")
                notas.append(avisos[-1])
            if encabeza_total:
                notas.append(
                    f"{encabeza_total} renglon(es) encabezan con el total de la nota "
                    f"({a_texto(valor)}) y luego lo desglosan: no es diferencia de plata"
                )

            total = sum(c["val"] for c in aceptadas)
            novedad = ""
            if total != valor:
                dif = total - valor
                sobra = "de mas en el acta" if dif > 0 else "de mas en la nota"
                cuadra = buscar_subconjunto([c["val"] for c in aceptadas], valor)
                pista = (
                    " (la nota corresponde a algunos renglones del acta, no a todos)"
                    if cuadra
                    else " (ningun grupo de renglones del acta da el valor de la nota)"
                )
                novedad = (
                    f"El acta acepta {a_texto(total)} y la nota credito acredita "
                    f"{a_texto(valor)}: diferencia {a_texto(abs(dif))} {sobra}.{pista}"
                )
                notas.append(novedad)
            novedad = " · ".join([n for n in ([novedad] if novedad else []) + avisos])
            return "\n\n".join(conceptos), acta, fecha, novedad, notas
        novedad = (
            f"El acta no registra ningun valor aceptado para esta factura y la nota "
            f"credito acredita {a_texto(valor)}. Respuesta tomada de la observacion de la nota."
        )
        notas.append(novedad)
        return resp_obs, acta, fecha, novedad, notas

    novedad = (
        "La factura no aparece en la circularizacion bajo esa acta. "
        "Respuesta y datos tomados de la observacion de la nota credito."
    )
    notas.append(novedad)
    return resp_obs, acta_ref, fecha_obs, novedad, notas


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rehacer = "--rehacer" in sys.argv
    if len(args) < 3:
        print(__doc__)
        sys.exit(1)
    ruta_bd, ruta_circ, ruta_salida = args[:3]
    ruta_reporte = args[3] if len(args) > 3 else None

    # El orden de los dos archivos no importa: la circularizacion es la que
    # trae la hoja GENERAL. Asi el lanzador puede recibirlos arrastrados en
    # cualquier orden sin que el auditor tenga que acordarse de cual va primero.
    def tiene_general(ruta):
        wb = openpyxl.load_workbook(ruta, read_only=True)
        try:
            return "GENERAL" in wb.sheetnames
        finally:
            wb.close()

    if tiene_general(ruta_bd) and not tiene_general(ruta_circ):
        ruta_bd, ruta_circ = ruta_circ, ruta_bd
        print("(los archivos venian al reves; se corrigio el orden solo)")

    general = cargar_general(ruta_circ)
    wb = openpyxl.load_workbook(ruta_bd)
    ws, fila_enc, col = localizar_hoja_y_encabezados(wb)
    letra = openpyxl.utils.get_column_letter
    print(
        f"Hoja '{ws.title}', encabezados en la fila {fila_enc}. Columnas detectadas: "
        + ", ".join(f"{c}={letra(i + 1)}" for c, i in sorted(col.items(), key=lambda x: x[1]))
    )

    # Columna nueva al final para avisar diferencias entre lo aceptado en el acta
    # y lo que realmente acredito la nota credito.
    ENC_NOVEDAD = "NOVEDAD ACEPTADO VS NOTA CREDITO"
    col_novedad = None
    for c in ws[fila_enc]:  # reutilizar la columna si el archivo ya la trae
        if normalizar(c.value) == ENC_NOVEDAD:
            col_novedad = c.column - 1
            break
    if col_novedad is None:
        col_novedad = max(i for c, i in col.items()) + 1
        while ws.cell(row=fila_enc, column=col_novedad + 1).value not in (None, ""):
            col_novedad += 1
        ws.cell(row=fila_enc, column=col_novedad + 1).value = ENC_NOVEDAD
    print(f"Novedades se escriben en la columna {letra(col_novedad + 1)}")

    reporte, llenas, solo_respuesta = [], 0, 0
    for fila in ws.iter_rows(min_row=fila_enc + 1):
        factura = limpiar(fila[col["factura"]].value)
        if not factura:
            continue
        # Se trabaja la fila cuando le falta la respuesta, que es la columna que
        # da sentido al registro. Numero y fecha pueden venir ya puestos.
        # Con --rehacer se reescriben ademas las filas de tipo ACTA que ya
        # tienen respuesta, para poder volver a correr sobre un archivo ya
        # diligenciado cuando cambian las reglas o se corrige la circularizacion.
        # Las de tipo TRAMITE nunca se tocan: ese texto no sale del acta.
        es_acta = (
            normalizar(fila[col["tipo_tramite"]].value) == "ACTA"
            if "tipo_tramite" in col
            else False
        )
        if limpiar(fila[col["respuesta"]].value) and not (rehacer and es_acta):
            continue
        valor = a_numero(fila[col["valor"]].value)
        acta_fila = numero_de_acta(fila[col["num"]].value)
        respuesta, acta, fecha, novedad, notas = resolver_fila(
            factura, valor, fila[col["obs"]].value, acta_fila, general
        )
        if respuesta:
            celda = fila[col["respuesta"]]
            celda.value = respuesta
            celda.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")
        ws.cell(row=fila[0].row, column=col_novedad + 1).value = novedad or None
        # Nunca se pisa un numero o una fecha que ya estaban escritos.
        if acta and fila[col["num"]].value is None:
            fila[col["num"]].value = acta
        if fecha and fila[col["fecha"]].value is None:
            fila[col["fecha"]].value = fecha
            fila[col["fecha"]].number_format = "dd/mm/yyyy"
        llenas += 1
        if acta_fila and fila[col["fecha"]].value is not None:
            solo_respuesta += 1
        if not respuesta:
            notas.append("SIN RESPUESTA: revisar manualmente")
        for n in notas:
            reporte.append(
                {
                    "fila": fila[0].row,
                    "factura": factura,
                    "valor_nota": valor,
                    "acta": acta,
                    "nota": n,
                }
            )

    wb.save(ruta_salida)
    print(f"Filas diligenciadas: {llenas} (de ellas {solo_respuesta} ya traian numero y fecha)")
    print(f"Archivo generado: {ruta_salida}")
    if ruta_reporte:
        with open(ruta_reporte, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["fila", "factura", "valor_nota", "acta", "nota"])
            w.writeheader()
            w.writerows(reporte)
        print(f"Reporte de revision ({len(reporte)} notas): {ruta_reporte}")
    else:
        for r in reporte:
            print(f"  fila {r['fila']} {r['factura']}: {r['nota']}")


if __name__ == "__main__":
    main()
```

---

## Anexo B — Datos de referencia del cruce (junio 2026)

### B.1 Estructura de la hoja `BD` del consolidado de glosas aceptadas

Título en `A2`: `CONSOLIDADO VLR ACEPTADOS X NOTAS  JUNIO 2026`. Encabezados en la **fila 4**. Datos en las **filas 5–199** (195 filas). Fila 200: totales (`J200 = =SUM(J5:J199)`). Filas 201–202 vacías.

| Col | Idx | Encabezado literal |
|---|---|---|
| A | 0 | `NO NOTA` |
| B | 1 | `FECHA NOTA` |
| C | 2 | `FACTURA` |
| D | 3 | `NATURALEZA` |
| E | 4 | `VIGENCIA FACTURA` |
| F | 5 | `FECHA FACTURA` |
| G | 6 | `NIT` |
| H | 7 | `ENTIDAD` |
| I | 8 | `OBSERVC NOTA CREDITO` |
| J | 9 | `VALOR ACEPTADO` |
| K | 10 | `REGIMEN` |
| L | 11 | `CONTRATO` |
| M | 12 | `COD ENTIDAD` |
| N | 13 | `VALOR FACTURA` |
| O | 14 | `DOC` |
| P | 15 | `PACIENTE` |
| Q | 16 | `FECHA FACTURA` |
| R | 17 | `NO DE GLOSA ` |
| S | 18 | `FECHA DE GLOSA  ` |
| T | 19 | `COD GLOSA` |
| U | 20 | `CONCEPTO` |
| V | 21 | `OBSERV. GLOSA` |
| **W** | **22** | **`RESPUESTA TRAMITE GLOSA Y/O ACTA`** ← se llena |
| **X** | **23** | **`NO DE TRAMITE Y/O ACTA`** ← se llena |
| **Y** | **24** | **`FECHA DE TRAMITE Y/O ACTA`** ← se llena |
| Z | 25 | `TIPO` (`Medica` / `Administrativo` / `Mixta`) |
| AA | 26 | `TRAMITE Y/O ACTA` (`TRAMITE` / `ACTA`) |

**Estilos observados y replicados:** `W`: Calibri 11, `wrap_text=True`, formato `General`. `X`: entero, `General`. `Y`: formato `dd/mm/yyyy`.

### B.2 Estructura de `CIRCULARIZACIÓN DE GLOSAS 2026.xlsx`

| Hoja | Filas × Cols | Uso |
|---|---|---|
| `Hoja1` | 733 × 2 | Tabla dinámica (`Suma de VALOR ACEPTADO POR IPS ESE HUS EN CONCILIACION`). No usada. |
| **`GENERAL`** | **7.399 × 16** | **Fuente del cruce.** Encabezados fila 2, datos desde fila 3, subtotales en fila 1. |
| `CONCILIACIONES REALIZADAS` | 7.265 × 1.025 | Resumen por acta. Usada solo para verificación cruzada (D3). |
| `CRONOGRAMA DE CONCILIACIONES` | 1.048.155 × 1.025 | No usada. |
| `TRAMITE JURIDICA ` | 2 × 10 | Vacía de datos. |

**Columnas de `GENERAL`:**

| Col | Idx | Encabezado |
|---|---|---|
| A | 0 | `N` |
| **B** | **1** | **`NUMERO FACTURA`** ← clave del cruce |
| C | 2 | `VALOR FACTURA` |
| D | 3 | `ENTIDAD` |
| E | 4 | `VALOR GLOSA A CONCILIAR` |
| **F** | **5** | **`VALOR ACEPTADO POR IPS ESE HUS EN CONCILIACION `** ← validación |
| G | 6 | `VALOR LEVANTADO POR ERP EN CONCILIACION` |
| H | 7 | `VALOR NO CONCILIADO PARA SEGUNDA INSTANCIA ` |
| I | 8 | `NUMERO OFICIO NOTIFICADO A JURIDICA NO ACUERDO ` |
| J | 9 | `VALOR PARA REFACTURAR ` |
| K | 10 | `NUMERO DE OFICIO REFACTURAR ` |
| **L** | **11** | **`N° ACTA`** → col X |
| **M** | **12** | **`FECHA DE FIRMA ACTAS`** → col Y |
| **N** | **13** | **`CONCEPTO CONCILIACIÓN`** → col W |
| O | 14 | `CÓDIGO DE LA GLOSA` |

### B.3 Actas presentes en `GENERAL` (2026)

| Acta | Filas | Fecha de firma | Entidad |
|---|---|---|---|
| 666 | 20 | 2026-01-05 | SEGUROS DEL ESTADO SOAT |
| 709 | 260 | 2026-01-28 | DIRECCION DE SANIDAD EJERCITO |
| 743 | 101 | 2026-03-18 | HDI SEGUROS COLOMBIA S.A. |
| 766 | 68 | 2026-04-14 | HDI SEGUROS COLOMBIA S.A. |
| 771 | 90 | 2026-04-17 | FIDEICOMISOS PATRIMONIOS AUTÓNOMOS |
| 803 | 13 | 2026-05-28 | HDI SEGUROS COLOMBIA S.A. |
| 805 | 75 | 2026-06-10 | FIDEICOMISOS PATRIMONIOS AUTÓNOMOS |
| 806 | 3 | 2026-06-12 | DISPENSARIO MEDICO NIVEL II BOGOTÁ |
| 821 | 57 | 2026-06-23 | FUNDACION SALUD MIA |
| 862 | 420 | 2026-05-20 | DISPENSARIO MEDICO BUCARAMANGA |
| 879 | 1.066 | 2026-05-20 | DISPENSARIO MEDICO BUCARAMANGA |

**Actas citadas en notas crédito que NO existen en `GENERAL`:** **599** (14/11/2025, vigencia anterior) y **786** (07/05/2026, número no registrado — ver **RD1**).

### B.4 Resultado del cruce de junio 2026

```
Filas de datos en BD:                195  (filas 5–199)
Filas ya diligenciadas:              119  (filas 5–123)
Filas pendientes procesadas:          76  (filas 124–199)  ← todas con TIPO = ACTA
Facturas indexadas de GENERAL:     4.036
Notas de revisión generadas:          54
Celdas escritas:                     228  (76 × 3)
Celdas modificadas fuera de W/X/Y:     0
```

**Desglose de las 76 filas por estrategia:**

| Estrategia | Filas | Detalle |
|---|---|---|
| **A — Match exacto** | 36 | Subconjunto de conceptos que suma el valor. Sin notas de revisión. |
| **B — Valor no cuadra** | 19 | Se usó el texto de la NC; acta y fecha de la circularización. |
| **D — Fuera de circularización** | 21 | Acta 599 de vigencia 2025. Todo desde la observación de la NC. |

**Desglose de las 54 notas de revisión:**

| Tipo de nota | Cantidad |
|---|---|
| `factura no esta en la circularizacion` (acta 599) | 21 |
| `valor aceptado X no cuadra con el acta (Y)` | 19 |
| `NC cita acta 786; circularizacion la registra en acta 879` | 10 |
| `NC cita acta 862; circularizacion la registra en acta 806` | 3 |
| `NC cita acta 786; circularizacion la registra en acta 862` | 1 |

**Las 19 filas con valor discrepante:**

| Fila | Factura | Valor NC | Valor acta | Acta |
|---|---|---|---|---|
| 157 | HUS0000487175 | 408.020 | 423.520 | 806 |
| 158 | HUS0000487009 | 46.470 | 49.750 | 806 |
| 164 | HUS0000485551 | 5.746 | 19.206 | 862 |
| 165 | HUS0000485841 | 5.746 | 19.206 | 862 |
| 166 | HUS0000482981 | 16.209 | 19.209 | 862 |
| 167 | HUS0000483189 | 5.746 | 19.209 | 862 |
| 168 | HUS0000483269 | 5.746 | 19.209 | 862 |
| 169 | HUS0000483542 | 16.209 | 19.209 | 862 |
| 170 | HUS0000484044 | 5.746 | 16.209 | 862 |
| 171 | HUS0000485015 | 16.209 | 19.209 | 862 |
| 172 | HUS0000483927 | 16.209 | 19.209 | 862 |
| 173 | HUS0000483928 | 16.209 | 19.209 | 862 |
| 174 | HUS0000483928 | 16.209 | 19.209 | 862 |
| 175 | HUS0000480181 | 7.473 | 23.606 | 862 |
| 186 | HUS0000475082 | 1.582.649 | 4.163.907 | 879 |
| 187 | HUS0000485280 | 1.549.599 | 3.199.720 | 879 |
| 188 | HUS0000476124 | 189.929 | 257.901 | 879 |
| 194 | HUS0000480782 | 1.314.109 | 1.538.761 | 879 |
| 196 | HUS0000483862 | 160.330 | 160.500 | 862 |

**Las 21 facturas del acta 599** (14/11/2025, Dispensario Médico Bucaramanga), filas 124–151:
`HUS0000413469`, `HUS0000410233`, `HUS0000413462`, `HUS0000409574`, `HUS0000411363`, `HUS0000409690`, `HUS0000411234`, `HUS0000410302`, `HUS0000409981`, `HUS0000404136`, `HUS0000411338`, `HUS0000410675`, `HUS0000412364`, `HUS0000413118`, `HUS0000413073`, `HUS0000411587`, `HUS0000409621`, `HUS0000409451`, `HUS0000409872`, `HUS0000410979`, `HUS0000413266`.

**Las 11 facturas que citan el acta 786 inexistente:** filas 161, 182, 183, 186, 187, 188, 192, 193, 194, 197 (→ acta 879) y 195 (→ acta 862).

---

## Anexo C — Entregables ofimáticos producidos

### C.1 `ARCHIVO JUNIO 2026-GLOSAS ACEPTADAS - DILIGENCIADO.xlsx`

Consolidado de junio con las 228 celdas diligenciadas. Entregado al auditor. Verificaciones ejecutadas: 0 filas incompletas, 0 celdas modificadas fuera de W/X/Y, fórmula `J200` intacta, formatos correctos.

### C.2 `reporte_revision.csv`

54 filas + encabezado (`fila, factura, valor_aceptado, acta, nota`), codificación `utf-8-sig`. Entregado junto al Excel.

### C.3 Lógica de llenado de `#N/D` (no versionada)

Aplicada a `archivo.xlsx` y `archivo_1.xlsx`. Se registra íntegra aquí para que no se pierda (ver §15.4):

```python
import openpyxl, re


def extraer_respuesta(obs):
    """Parte de la observacion posterior a la referencia del acta (misma regla
    usada en el consolidado de junio: el texto tras 'EN LA CUAL'/'FIRMADA...')."""
    t = str(obs).replace("_x000D_", "").replace("\r", "").strip()
    m = re.search(r"EN LA CUAL\s*[:;,]?\s*", t)
    if not m:
        m = re.search(r"FIRMADA POR[^.]*\.\s*", t)
    if not m:
        m = re.search(r"DONDE\s*:?\s*", t)
    resto = t[m.end() :] if m else t
    ini = re.search(r"EN CONCILIACION|ESE HUS", resto)
    return (resto[ini.start() :] if ini else resto).strip(" :;,.\n")


wb = openpyxl.load_workbook(path)
ws = wb.active
for fila in (6, 7):
    resp = extraer_respuesta(ws.cell(row=fila, column=23).value)  # W -> V
    ws.cell(row=fila, column=22).value = resp
wb.save(out)
```

**Estructura de esos archivos** (`Hoja1`, 7 filas × 24 columnas): encabezados generales en fila 4 (A–S, W, X) y desglose en fila 5 (S, T, U, V). Datos en filas 6 y 7.

| Col | Encabezado |
|---|---|
| A | `CONTRATISTA RESPONSABLE ACEPTACION` |
| B | `FACTURA` |
| C | `HISTORIA CLÍNICA` |
| D | `PACIENTE` |
| E | `ENTIDAD` |
| F | `NIT` |
| G | `FECHA FACTURA ` |
| H | `CONTRATO` |
| I | `CODIGO ENTIDAD` |
| J | `REGIMEN` |
| K | `VALOR FACTURA` |
| L | `Nº GLOSA INICIAL` |
| M | `FECHA GLOSA ` |
| N | `VALOR CONCEPTO GLOSA NOTA` |
| O | `NOTA  DEBITO` |
| P | `VALOR  ACEPTADO POR NOTA CREDITO` |
| Q | `Nº TRAMITE Y/O ACTA` |
| R | `FECHA TRAMITE Y/O ACTA` |
| S | `CODIGO GLOSA INICIAL` |
| T | `CONCEPTO GLOSA INICIAL ` |
| U | `MOTIVO GLOSA  INICIAL` |
| **V** | **`RESPUESTA A LA GLOSA INICIAL Y/O ACTA`** ← contenía `#N/D` |
| W | `OBSERVACION DE LA NOTA` |
| X | `FECHA NOTA CREDITO ` |

**Datos de las dos filas procesadas (idénticas en ambos archivos):**

| | Fila 6 | Fila 7 |
|---|---|---|
| Factura | HUS0000340948 | HUS0000384193 |
| Historia clínica | 1102355798 | 1005177110 |
| Paciente | JOSE MANUEL DURAN ROJAS | MARIA ALEJANDRA MEZA HERRERA |
| Entidad | SEGUROS GENERALES SURAMERICANA S. A. | CAPITAL SALUD EPS-S S.A.S. |
| NIT | 890903407 | 900298372 |
| Contrato | U22012 | U22033 |
| Cód. entidad | AT1318 | EPS040 |
| Régimen | SOAT (accidentes de tránsito) | PBSS subsidiado |
| Valor factura | 96.265 | 7.562.798 |
| Nº glosa inicial | 120537 | 126822 |
| Valor NC | 12.465 | 52.100 |
| Acta | ACTA 509 (04/06/2025) | ACTA 604 (20/11/2025) |
| Código glosa | 849 | AU0102 \| AU5802 \| TA0201 \| TA0801 |
| Fecha NC | 2026-03-10 13:46:24 | 2026-03-19 14:53:26 |
| **Cuadre de valor** | ✅ coincide ($12.465) | ⚠️ acta suma $113.700 vs NC $52.100 |

---

## Anexo D — Cronología literal de la sesión

Reconstrucción del orden real de los hechos, para que el equipo entienda cómo se llegó a cada decisión.

| # | Hecho |
|---|---|
| 1 | El usuario aporta `CIRCULARIZACIÓN DE GLOSAS 2026.xlsx` y `ARCHIVO JUNIO 2026-GLOSAS ACEPTADAS.xlsx` y pide llenar W, X, Y tomando como ejemplo las filas ya diligenciadas, con la regla de que **el VALOR ACEPTADO debe coincidir** con los valores de la respuesta. |
| 2 | Se instala `openpyxl` (no estaba en el contenedor) y se inspeccionan ambos libros: hojas, dimensiones, encabezados, tipos y estilos. |
| 3 | Se descubre que **las 76 filas pendientes tienen W con un espacio en blanco, no vacío**, y que ya están todas clasificadas como `ACTA` en la columna AA. |
| 4 | Primer cruce exploratorio: 55 de 76 facturas presentes en `GENERAL`, 21 ausentes, 23 con valor discrepante. |
| 5 | Se investigan las ausencias: todas citan el **acta 599 de 14/11/2025** (vigencia anterior), que no existe en la circularización 2026. Se decide el **fallback a la observación de la NC** (D5). |
| 6 | Se investigan las discrepancias de acta: la **786 no existe**; esas facturas están bajo 879/862. Tres facturas del Dispensario Bogotá citan la 862 pero corresponden a la 806. Se decide **priorizar el registro de la circularización** y dejar nota. |
| 7 | Se inspecciona `CONCILIACIONES REALIZADAS` y se **descarta** como fuente (D3): es resumen por acta, sin detalle por factura. |
| 8 | Se escribe `tools/completar_tramite_glosas_aceptadas.py` con la cascada de 4 estrategias y el motor de subconjunto exacto. |
| 9 | Primera corrida: 76 filas, 54 notas. Se revisa el resultado fila por fila. |
| 10 | Se detecta en la fila 128 el concepto repetido tres veces → se agrega la **deduplicación con `dict.fromkeys`** (D8) y se re-ejecuta. |
| 11 | Verificación exhaustiva: 0 celdas modificadas fuera de W/X/Y; fórmula `J200` intacta; formatos correctos. |
| 12 | Se entregan al usuario el `.xlsx` diligenciado y el `.csv` de revisión, con explicación de los tres bloques de casos a validar. |
| 13 | Commit `c11fb6f` y push a `claude/excel-glosas-aceptadas-campos-l3ru9n`. |
| 14 | Se intenta crear el PR contra `main` → **HTTP 422**. Se descubre que el default del repo es `motor-glosas`. Se crea el PR **#166** en borrador. |
| 15 | El CI falla en `Lint (ruff)`. Se reproduce localmente: `ruff check` pasa pero `ruff format --check` señala el módulo nuevo **y** `tests/test_api/test_import_history.py` (deuda preexistente). Se formatean ambos → commit `496e2c7`. |
| 16 | Se activa la suscripción a eventos del PR. Lint y Security quedan en verde. |
| 17 | El usuario pide la **bitácora**. Se detecta que el clon es **shallow**; se ejecuta `git fetch --unshallow` y aparecen **1.647 commits desde el 8 de abril de 2026**. |
| 18 | Se reconstruye el historial completo por fechas y se redactan `BITACORA.md` y `CLAUDE.md`. Commit `d3f95f2`, push, y actualización de la descripción del PR. |
| 19 | Llega webhook: falla `Tests (pytest)` — 3 fallos, 4.078 verdes. Se diagnostica la **bomba de tiempo de fechas** (20-abr quedó fuera de la ventana de 90 días entre el 17 y el 22 de julio). |
| 20 | Se reproduce localmente instalando dependencias una a una (falla `requirements-dev.txt` por `http-ece`/`sgmllib3k`; hay que fijar `bcrypt<4` por un `PanicException`). Se corrigen ambos archivos con `_fecha_reciente()`. 8 tests verdes. Commit `8a6f85d`, push. |
| 21 | El usuario pide un nombre para el chat. Se propone «Excel glosas aceptadas + Bitácora (PR #166)». |
| 22 | El usuario aporta `archivo.xlsx` con celdas `#N/D`. Se invoca la skill `xlsx`. Se localizan `V6` y `V7`, se confirma que **no son fórmulas** sino valores pegados, y que las facturas **no están** en la circularización 2026 (actas 509/604 son de 2025). Se llenan desde la observación de la nota. Se reporta la discrepancia de valor de la fila 7. |
| 23 | El usuario aporta `archivo_1.xlsx`: mismas dos facturas, mismo tratamiento, misma advertencia. |
| 24 | El usuario solicita este documento técnico de entrega para consolidar el módulo en el proyecto principal. |

---

*Fin del documento.*
