# Guía: `responder_glosas_coosalud.py` — Respuesta masiva de glosas en COOSALUD

Bot Playwright que recorre el portal de COOSALUD (`vco.ctamedicas.com`) y carga
las respuestas a glosas que vienen tipificadas en un Excel del HUS, sin
intervención humana. Reemplaza la operación manual de:

> *abrir cada factura, marcar checkboxes, llenar el modal de respuesta,
> adjuntar PDX, dar Terminar Respuesta, y bajar el pantallazo de evidencia*

por una corrida desatendida que procesa cientos de facturas con CSV de
seguimiento y carpeta de evidencias por factura.

---

## 1) Por qué existe

El portal COOSALUD obliga a contestar cada glosa abriendo la factura,
buscando la grilla GLOSAS, abriendo el modal "Responder Masivamente" por
**cada combinación distinta de (código de respuesta + texto de justificación)**.
Para una factura con 800 glosas distribuidas en 3-4 grupos, el flujo manual
toma 5-10 minutos. En lotes de 140-250 facturas → días de trabajo repetitivo.

El bot elimina ese costo y suma controles que a mano son difíciles de garantizar:

- **Reanudabilidad**: si una factura quedó a medias (algunos grupos respondidos
  y otros no), el bot lee la grilla del portal, identifica las glosas que ya
  están `RESPONDIDA` y salta los grupos hechos.
- **Idempotencia**: si lo corrés dos veces no duplica respuestas.
- **Evidencia automática**: pantallazo del cartel "¡Usted ha cerrado una cuenta!"
  guardado como `HUS<num>_cierre.png` en una carpeta dedicada.
- **CSV incremental**: cada factura procesada se anota en el reporte (flush
  cada 5) — si la red cae a mitad podés ver hasta dónde llegó.

---

## 2) Insumos que necesita

### A) Excel consolidado de glosas (`--excel`)

Lo genera el equipo de pertinencia / cartera del HUS. Tiene **una fila por
glosa individual** (no por factura). Hojas relevantes:

- `BASE` — glosas administrativas (TARIFAS, FACTURACIÓN, SOPORTES). Default.
- `CALIDAD` — glosas de pertinencia. Por defecto se ignoran; con
  `--incluir-calidad` también se responden si traen respuesta tipificada.

Columnas que el bot lee (los nombres pueden variar — usa alias normalizados):

| Concepto | Columna típica |
|---|---|
| Factura | `numero_factura` |
| Id glosa | `id_glosa` |
| Tipo de glosa | `tipo_glosa` (TARIFAS / FACTURACIÓN / SOPORTES / CALIDAD) |
| Código de respuesta | `COD RESPUESTA GLOSA` (`RE9901`, `RE9602`, etc.) |
| Texto de respuesta | `OBSERVACION RTA GLOSA` |

El bot **agrupa por (código + texto idéntico)** dentro de cada factura. Cada
grupo se responde con UNA invocación del modal "Responder Masivamente" del
portal — exactamente lo que hace un humano cuando ve varias glosas con la
misma respuesta.

### B) Índice de soportes (`--indice`)

TXT con 133.000+ líneas tipo:
```
HUS500258	Y:\5. MAYO 2026 - SOPORTES RADICACION\COOSALUD\VANESSA\RIPS\ENV-226686-OK\HUS500258
```

Una factura por línea con su carpeta en el share `\\172.16.32.83\...` o en el
mapeo Y:. Lo usa para encontrar el PDF de soporte (PDX/HAM/PDE) cuando un
grupo es de tipo SOPORTES.

### C) Credenciales del portal (variables de entorno)

```cmd
setx COOSALUD_USER 680010079201
setx COOSALUD_PASSWORD <password>
```

Una sola vez por máquina. Después se cierra y reabre la terminal para que
las tome. **Nunca pongas la contraseña en el comando** — queda en el historial
de PowerShell.

### D) Carpeta de evidencias (`--evidencias`)

Dónde se guardan los `HUS<num>_cierre.png`. Si no existe la crea.

---

## 3) Flujo paso a paso por factura

### 3.1 Login al portal

`POST` a `https://vco.ctamedicas.com/app/login` con user + password.
Espera el cartel "¡Bienvenido!" o la redirección al home como señal de éxito.
Soporta re-login automático: si la sesión se cae mid-corrida, vuelve a
loguearse hasta 5 veces antes de abortar.

### 3.2 Localización de la factura

Cada factura puede estar en uno de **dos lugares**:

- **Bolsa de Respuestas** (`/app/respuestaGlosaSearch`) — factura nueva, sin
  abrir.
- **En Pausa** (`/app/respuestaGlosaPause`) — factura que ya se abrió alguna
  vez (manual o por el bot) y no se Terminó.

El bot busca primero en Bolsa. Si no la encuentra, prueba En Pausa. Si
tampoco aparece, marca la factura como `NO_EN_BOLSA` (ya está cerrada o
sale del scope del lote del día).

La búsqueda es robusta a la grilla lenta del portal: la caja "Buscar"
recién aparece cuando el datatable termina de cargar (hasta 3 min en
peak); el bot polea con paciencia y dispara `keyup` por JS porque
`fill()` de Playwright no lo dispara solo.

### 3.3 Apertura de la factura

Click en el botón ▶ azul de la fila. El portal abre la cuenta y muestra:

1. **Cartel "¡Se ha asignado la cuenta!"** — modal que el bot cierra
   automáticamente apretando Continuar.
2. **Sección GESTION CUENTA** — los ítems facturados (CUPS).
3. **Sección GLOSAS** — la grilla que el bot necesita, con
   `Cargando…` hasta que termina.

### 3.4 Lectura del estado real de la grilla

Antes de responder nada, el bot llama a `leer_estados(page)` que recorre
todas las filas y arma `{id_glosa: estado}` donde `estado` es:

- `SIN RESPUESTA` → la glosa está pendiente.
- `RESPONDIDA` → ya tiene respuesta.

Compara con los grupos del Excel para saber:
- **Cuáles grupos están totalmente respondidos** (todos sus ids → `RESPONDIDA`)
  → los salta.
- **Cuáles grupos están parcialmente pendientes** (algunos ids
  `SIN RESPUESTA`) → responde sólo esos.

Esto es lo que hace al bot **reanudable**: si fallaste a mitad o si una
factura quedó a medias del día anterior, vuelve y completa.

### 3.5 Procesamiento de cada grupo

Por cada grupo a responder:

#### 3.5.1 Búsqueda del soporte (solo grupos SOPORTES)

`buscar_pdx(factura, indice)` busca un PDF de soporte probando prefijos en
orden:

1. `PDX_*.pdf` (el preferido — el que el HUS tipifica para respuestas)
2. `HAM_*.pdf` (historia clínica — fallback aceptado por COOSALUD)
3. `PDE_*.pdf` (resumen clínico — segundo fallback)

Y prueba en dos ubicaciones:

1. **Carpeta del índice** directamente.
2. **Carpeta hermana de IMG/** — el HUS separa los JSONs/RIPS en una
   carpeta y los PDFs en otra:
   - `\KARIN\RIPS\ENV-227237-OK\HUS508259\` ← índice
   - `\KARIN\ENV-227237-OK-C-DGH\IMG\HUS508259\` ← PDFs
   - `\VANESSA\RIPS\ENV-226686-OK\HUS500258\` ← índice
   - `\VANESSA\ENV-226686-R-C\IMG\HUS500258\` ← PDFs

   El matcher reconoce hermanas por `ENV-<numero>-*` (sufijo libre).

Si no encuentra ningún soporte, el grupo se **salta** y la factura queda como
`PENDIENTE_PDX` (no se Termina). El log dice qué PDFs encontró en la
carpeta para diagnosticar.

#### 3.5.2 Marcado de checkboxes

Si todas las glosas del grupo coinciden con las `SIN RESPUESTA` del portal,
intenta primero el **checkbox maestro** del thead (más rápido). Si no marcó
todo, va fila por fila marcando los checkboxes individuales por
`id_glosa`.

Usa un evaluate JS en bloque (un solo round-trip) en vez de
click-por-fila para evitar 0.7s × N glosas — para grupos de 200 esto
hace la diferencia entre 2.5 min y 2 segundos.

#### 3.5.3 Submodal "Responder Masivamente"

El portal abre un modal en cascada con:

- **Dropdown de código de respuesta** (`RE9901`, `RE9602`, etc.) — el bot
  trata 3 estrategias: select nativo → set por JS + jQuery change →
  combo select2 clickeable.
- **Textarea de justificación** — escribe el texto del Excel.
  Dispara `input`/`change`/`blur` para que la validación JS del portal
  habilite el botón.
- **Input file** — adjunta el PDX/HAM/PDE si aplica. Espera 2.5s para
  que el upload asíncrono termine.
- **Botón "Responder Glosa"** — espera a que se habilite (hasta 90s).
  Si después de ese tiempo sigue disabled, aborta con error claro.

Click Responder Glosa → espera que el modal `Respondiendo Masivamente`
**se cierre** (señal cierta de submit OK) → espera el sweet alert
`Se ha dado Respuesta` → click Continuar.

#### 3.5.4 Recargar entre grupos

El portal tiene un bug: **el modal "Responder Masivamente" funciona una
sola vez por carga de página**. Si lo abrís de nuevo sin recargar, el
botón Responder Glosa queda permanentemente disabled.

Solución: después de cada grupo respondido, el bot hace `page.reload()`
y vuelve a entrar a la sección GLOSAS. Cuesta ~15s, pero evita los
errores de "botón disabled 90s" que aparecían en pasadas anteriores
y que forzaban reintento de la factura entera (5 min perdidos).

#### 3.5.5 Tandas para grupos enormes

Si un grupo tiene más de 200 glosas, el dropdown del modal se rompe (no
carga los códigos de respuesta). El bot **lo parte en tandas de 200**,
cada una con su recarga.

Casos reales que esto resolvió:
- `HUS500253`: 817 glosas en un grupo → 5 tandas.
- `HUS506545`: 757 glosas → 4 tandas.

#### 3.5.6 Espera de confirmación

Después de responder el grupo, el bot espera hasta 90s a que las glosas
recién respondidas aparezcan como `RESPONDIDA` en la grilla (releyendo
estados). Solo entonces continúa con el grupo siguiente.

### 3.6 Terminar la factura

Cuando no quedan `SIN RESPUESTA` (y no hay grupos saltados por falta de
PDX), el bot:

1. Click "Terminar Respuesta".
2. Sweet alert "Desea Terminar?" → click "Sí, Terminar!".
3. Espera el cartel **"¡Usted ha cerrado una cuenta!"** (señal cierta del
   cierre).
4. Toma `page.screenshot(full_page=True)` → guarda como
   `<evidencias>\HUS<num>_cierre.png`.
5. Click Continuar.

### 3.7 Casos donde NO se Termina

| Situación | Estado en reporte | Por qué |
|---|---|---|
| Falta PDX/HAM/PDE de un grupo SOPORTES | `PENDIENTE_PDX` | No querés prometer un soporte que no se adjuntó. |
| Hay glosas tipo CALIDAD (sin `--incluir-calidad`) | `OK_CALIDAD_ABIERTA` | El equipo médico maneja pertinencia manualmente. |
| El portal muestra `SIN RESPUESTA` con id que no está en el Excel | `PENDIENTES` | Hay glosas en el portal que no vienen tipificadas — no se inventa respuesta. |
| La factura no aparece ni en Bolsa ni en Pausa | `NO_EN_BOLSA` | Ya está cerrada de una corrida anterior, o sale del scope. |
| Excepción durante el flujo | `ERROR` | Screenshot de diagnóstico en `debug_screenshots\` para investigar. |

---

## 4) Argumentos del CLI

### Selección de facturas (uno requerido)

| Flag | Para qué |
|---|---|
| `--solo HUS<n>` | Una sola factura (piloto). |
| `--facturas HUS1,HUS2,...` | Lista corta, separada por coma. |
| `--lista archivo.txt` | TXT con una factura por línea (lotes grandes). |
| `--todas` | Todas las facturas de la hoja. |

### Filtros y modificadores

| Flag | Default | Uso |
|---|---|---|
| `--hoja` | `BASE` | Qué hoja del Excel leer (`BASE` o `CALIDAD`). |
| `--incluir-calidad` | off | Responder también glosas tipo CALIDAD con su texto del Excel (cierra la factura sin dejarla en pausa). |
| `--max-grupos N` | 0 | Responder máximo N grupos por factura (debug). |
| `--max-facturas N` | 0 | Procesar máximo N facturas (piloto). |
| `--saltar-csv arch.csv` | — | Lee reportes previos y omite facturas ya marcadas `OK`, `NO_EN_BOLSA`, `OK_CALIDAD_ABIERTA` o `SOLO_CALIDAD`. Se puede repetir varias veces. |

### Comportamiento

| Flag | Para qué |
|---|---|
| `--con-cabeza` | Browser visible (default headless). Usalo en pilotos. |
| `--lento` | `slow_mo=300ms` entre acciones (debug visual). |
| `--evidencias <dir>` | Carpeta de los `*_cierre.png`. Default `EVIDENCIA`. |
| `--reporte <csv>` | CSV de salida. Default `reporte_coosalud.csv`. |
| `--log <ruta>` | Guarda log adicional al archivo. |

---

## 5) Anatomía del reporte CSV

Columnas:

| Columna | Significado |
|---|---|
| `factura` | `HUS<num>` |
| `grupos` | Cantidad de grupos del Excel |
| `glosas` | Cantidad total de glosas a responder |
| `estado` | `OK` / `OK_CALIDAD_ABIERTA` / `PENDIENTE_PDX` / `PENDIENTES` / `NO_EN_BOLSA` / `SOLO_CALIDAD` / `ERROR` |
| `detalle` | Texto explicativo (ej. "5 grupos respondidos; sin PDX: HUS501978") |

El CSV se actualiza cada 5 facturas (flush). Si Ctrl+C a mitad podés ver lo
hecho.

Para reanudar saltando las exitosas:

```cmd
--saltar-csv reporte_dia1.csv --saltar-csv reporte_dia2.csv ...
```

---

## 6) Comandos típicos

### Piloto con una factura (con cabeza)

```cmd
py tools\responder_glosas_coosalud.py ^
  --excel "D:\...\CONSOLIDADO COOSALUD DIA 28.xlsx" ^
  --indice "D:\...\BUSCADOR_HUS\indice_facturas_HUS.txt" ^
  --solo HUS500258 ^
  --con-cabeza
```

### Masivo todas las facturas (BASE)

```cmd
py tools\responder_glosas_coosalud.py ^
  --excel "D:\...\CONSOLIDADO COOSALUD DIA 28.xlsx" ^
  --indice "D:\...\BUSCADOR_HUS\indice_facturas_HUS.txt" ^
  --evidencias "D:\...\COOSALUD\EVIDENCIA" ^
  --reporte "D:\...\COOSALUD\reporte.csv" ^
  --todas
```

### Lote acotado (lista TXT con pendientes)

```cmd
py tools\responder_glosas_coosalud.py ^
  --excel "...PERTINENCIA.xlsx" --indice ... ^
  --lista "D:\...\pendientes_coosalud.txt" ^
  --reporte "D:\...\reporte_pendientes.csv"
```

### Hoja CALIDAD con respuestas tipificadas (cierra la factura completa)

```cmd
py tools\responder_glosas_coosalud.py ^
  --excel "...PERTINENCIA.xlsx" --indice ... ^
  --hoja CALIDAD --incluir-calidad ^
  --lista "D:\...\pendientes.txt" ^
  --reporte "D:\...\reporte_calidad_full.csv"
```

### Reanudar lote saltando lo ya hecho

```cmd
py tools\responder_glosas_coosalud.py ^
  --excel ... --indice ... --todas ^
  --saltar-csv "...\reporte_pasada1.csv" ^
  --saltar-csv "...\reporte_pasada2.csv" ^
  --reporte "...\reporte_pasada3.csv"
```

---

## 7) Soportes y evidencia de cada decisión

| Decisión de diseño | Por qué — caso real que la motivó |
|---|---|
| Recargar página entre grupos | HUS502954, HUS503590, HUS501978, HUS500435 — todas multi-grupo, segundo grupo siempre quedaba con "Responder Glosa disabled 90s" hasta que descubrimos que el modal es de uso único. |
| Esperar `Respondiendo Masivamente` se cierre como señal de submit | El selector "Se ha dado Respuesta" matcheaba texto residual del DOM del grupo anterior y devolvía inmediato — el portal nunca llegaba a guardar. |
| Buscar PDX en carpeta hermana IMG/ | HUS508259, HUS505218, HUS505348 — el índice apunta a RIPS/ pero los PDFs están en `ENV-XXX-OK-C-DGH/IMG/`. |
| Generalizar matcher de hermana a `ENV-<num>-*` | HUS500258, HUS501978, HUS506545, HUS507533 — patrón `ENV-226686-R-C` (no `OK-C-DGH`). |
| Fallback PDX → HAM → PDE | Lotes donde el HUS no generó PDX pero sí HAM (historia clínica) — COOSALUD acepta el HAM como soporte equivalente. |
| Partir grupos >200 glosas en tandas | HUS500253 (817), HUS506545 (757) — el dropdown del modal se rompe con tantos checkboxes. |
| Marcar checkboxes en bloque por JS | Click por fila tardaba 2.5 min en grupos de 200. Con un solo `evaluate` baja a 2 seg. |
| `--saltar-csv` con reportes previos | Las facturas ya cerradas tardaban 2 min cada una sólo en confirmar que no aparecían en Bolsa ni En Pausa. Con esto se omiten antes de empezar. |
| Auto-relogin si la sesión se cae | El portal cierra sesión por inactividad o cuando hay demasiados requests. El bot detecta `Target page closed` y vuelve a loguearse hasta 5 veces. |

---

## 8) Carpeta de evidencias — qué se genera

```
D:\USUARIO CARTERA\Documents\COOSALUD\EVIDENCIA\
├── HUS500258_cierre.png   ← cartel "¡Usted ha cerrado una cuenta!"
├── HUS501978_cierre.png
├── HUS506545_cierre.png
├── HUS507533_cierre.png
└── ...
```

Cada PNG es el pantallazo completo del browser en el momento exacto del
cierre — sirve como evidencia auditable de que esa factura quedó cerrada en
el portal.

Para juntar las evidencias en un Word de entrega:

```cmd
py tools\evidencias_a_word.py ^
  --carpeta "D:\...\EVIDENCIA" ^
  --salida "D:\...\evidencias_COOSALUD.docx"
```

Genera un .docx con una factura por página: encabezado con el número de
factura en negrita centrado + el pantallazo escalado para entrar en A4.

---

## 9) Diagnóstico cuando algo sale mal

### Carpeta `debug_screenshots\`

Cada error genera un PNG con timestamp + tipo de error:

```
debug_screenshots\
├── 103414_Bolsa_sin_fila_HUS501978.png
├── 103547_Bolsa_sin_fila_HUS500258.png
├── 100330_error_HUS508259.png
├── 132821_responder_glosa_disabled.png
└── ...
```

Útil para ver en qué parte del flujo se trabó si después aparece un `ERROR`
en el reporte.

### Reintentos automáticos por factura

Si una factura falla por:
- **Timeout o lentitud del portal** → reintento desde cero hasta 2 veces.
- **Sesión caída** → re-login y reintento (hasta 5 re-logins por corrida).

Si después de los reintentos sigue fallando, queda como `ERROR` en el
reporte y el bot sigue con la siguiente.

### Modo `--con-cabeza --lento`

Para mirar paso a paso un problema reproducible: el browser queda visible y
cada acción de Playwright se ralentiza 300ms.

---

## 10) Limitaciones conocidas

- **Codes de respuesta no estándar**: el bot busca códigos tipo `RE9901`
  exactos. Si el Excel tiene formato distinto (espacios, variantes) la
  selección del dropdown puede fallar.
- **Textos enormes**: justificaciones de >10.000 caracteres pueden tardar
  más de lo previsto en cargar al textarea.
- **Cambios del portal**: si COOSALUD modifica selectores CSS o textos
  de los modales, hay que actualizar `responder_grupo` o
  `terminar_respuesta`. El bot ya tiene fallbacks pero no son infinitos.
- **Concurrencia**: una sola instancia por usuario — dos bots con la misma
  cuenta pelean por la sesión.
