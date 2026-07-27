# Entrega técnica — Módulo «Organizador de Objeciones VCO» (rama `claude/savia-salud-objections-bot-o9qloo`)

**Documento de entrega al equipo principal.**
Reconstrucción completa de todo lo desarrollado en la conversación
"Bot objeciones VCO – Savia Salud (+ Bitácora)" (17–27 de julio de 2026).
Autor de la entrega: sesión de Claude Code actuando como desarrollador líder
del módulo. Repositorio: `yesidbadillo820-ship-it/motor-glosas-hus`.
Pull Request asociado: **#167** (draft, base `motor-glosas`). Estado del CI al
cierre: **verde** (Lint, Tests, Security scan).

---

## 1. Objetivo del desarrollo

### Por qué se creó

Pedido literal del usuario (auditor de cartera del HUS, cuenta
`auditoriasinac9@gmail.com`): *"ORGANIZAR VCO — necesito crear un bot que me
organice las objeciones de la entidad SAVIA SALUD como lo hizo con COOSALUD y
todas las demás entidades. Toma ese excel como punto de apoyo y partida de
ejemplo y ármame uno nuevo a base del archivo que te adjunto"*.

Adjuntó dos archivos:

1. `CONSOLIDADO_VCO.xlsx` — ejemplo del trabajo ya hecho para otra entidad
   (FIDUPREVISORA): 58 filas de objeciones en 10 columnas.
2. `OBJECIONES.xlsx` — plantilla de 16 columnas técnicas del ERP del
   hospital, **que llegó solo con la fila de encabezados, sin datos**.

### Qué problema resuelve

El equipo de cartera del HUS recibe actas de objeciones (glosas) de las EPS a
través del portal VCO (`vco.ctamedicas.com`, de CTA Médicas — usado por
COOSALUD, FIDUPREVISORA, SAVIA SALUD y otras). Ese material debe:

- organizarse en un **consolidado por servicio objetado** (formato del acta,
  10 columnas), y/o
- convertirse en el **archivo de cargue masivo de objeciones** que espera el
  ERP del hospital (16 columnas con nombres de campo técnicos:
  `CDCONSEC`, `CRNCXC`, `CROVALOBJ`, etc.).

Antes esto se hacía a mano por entidad. El módulo lo automatiza para
**cualquier entidad**, con SAVIA SALUD como caso que disparó el pedido.

### Necesidad que cubre

- Repetibilidad: mismo procedimiento para cada acta nueva de cualquier EPS.
- Control: imprime un resumen (facturas, número de objeciones, valor glosado
  por acta) para cuadrar contra el acta antes de cargar al ERP.
- Tolerancia: los Excel reales traen encabezados con variantes (tildes,
  mayúsculas, nombres distintos); el bot los reconoce por alias.

---

## 2. Arquitectura

### Naturaleza del módulo

Herramienta de línea de comandos **autónoma** (no toca la aplicación web, ni
la base de datos, ni la IA del motor). Sigue el patrón de los demás bots del
repo en `tools/` (scripts con `argparse`, docstring en español, README
`README_<tool>.md`, tests en `tests/test_tools/`).

### Archivos del módulo

| Archivo | Rol |
|---|---|
| `tools/organizar_objeciones_vco.py` | El bot. CLI + toda la lógica de conversión. |
| `tools/README_organizar_objeciones_vco.md` | Guía de uso completa (formatos, mapeo, flags, tests). |
| `tests/test_tools/test_organizar_objeciones_vco.py` | 31 tests (30 iniciales + 1 agregado el 21-jul). |

Además, el trabajo de esta rama tocó archivos ajenos al módulo (ver §10):
`tests/test_api/test_import_history.py`, `tests/test_api/test_por_dia_semana.py`,
`tests/test_api/test_heatmap_actividad.py`, `BITACORA.md`, `CLAUDE.md`.

### Dependencias y librerías

- **openpyxl** — única dependencia externa; ya estaba en `requirements.txt`
  (`openpyxl==3.1.5`). Import perezoso dentro de las funciones que lo usan
  (patrón copiado de `tools/convertir_tramite_masivo.py`), con lectura en
  modo `read_only=True, data_only=True`.
- Resto: biblioteca estándar (`argparse`, `datetime`, `logging`, `re`, `sys`,
  `unicodedata`, `collections.OrderedDict`, `pathlib`).
- **No usa** pandas, ni APIs, ni red, ni base de datos, ni IA en runtime.

### Los dos formatos que maneja (contratos de datos)

**Formato A — CONSOLIDADO VCO** (una fila por servicio objetado; constante
`COLUMNAS_CONSOLIDADO`):

```
CROOBSERV | NUMERO FACTURA | VALOR GLOSA | CODIGO GLOSA ESPECIFICA |
OBSERVACION | CODIGO SERVICIO | DESCRIPCION SERVICIO | CANTIDAD |
VALOR UNITARIO SERVICIO | VALOR TOTAL SERVICIO
```

- `CROOBSERV` (columna A) trae la referencia del acta, p. ej.
  `VCO-FIDUPREVISORA-2024-R1-14920`.
- Hoja del ejemplo real: `Hoja1`; valores monetarios con formato contable
  `_-* #,##0_-;\-* #,##0_-;_-* "-"_-;_-@_-`; columna E con ancho 19; sin
  freeze panes ni autofiltro; fuente Calibri 11 sin negrilla.

**Formato B — Plantilla OBJECIONES (cargue ERP)** (constante
`COLUMNAS_CARGUE`, 16 columnas, orden exacto):

```
CDCONSEC | CDFECDOC | CRNCXC | CROFECOBJ | CROREFERE | CROOBSERV |
CROCLAOBJ | CRNCLAOBJ | GENUSUARIO4 | CRNCONOBJ | SLNSERPRO | IDRIPS |
CTNCENCOS | CROVALOBJ | CRDOBSERV | CROTIPOBJ
```

- Hoja `OBJECIONES`, fila 1 congelada (`freeze_panes = "A2"`), tal como la
  plantilla real del usuario.
- Dato forense clave de la plantilla original: `docProps/core.xml` decía
  `creator = openpyxl` y `lastModifiedBy = cartera` — es decir, **fue
  generada por un bot anterior** (fuera de este repo) y el usuario le borró
  los datos antes de adjuntarla. Su XML declara `<dimension ref="A1:P1"/>`.

---

## 3. Funciones implementadas

Todas en `tools/organizar_objeciones_vco.py`.

### Constantes y expresiones regulares

- `COLUMNAS_CARGUE` / `COLUMNAS_CONSOLIDADO` — listas con los encabezados
  exactos de cada formato (ver §2).
- `_ALIAS_CONSOLIDADO` — diccionario campo → lista de alias normalizados.
  Campos: `acta`, `factura`, `valor_glosa`, `codigo_glosa`, `observacion`,
  `codigo_servicio`, `descripcion_servicio`, `cantidad`, `valor_unitario`,
  `valor_total`. Alias notables: `acta` acepta `CROOBSERV`, `ACTA`,
  `REFERENCIA`, `NUMERO ACTA`, `ACTA VCO`, y (agregados el 21-jul tras ver el
  archivo real de Fiduprevisora) `NUMERO RADICADO`, `NRO RADICADO`,
  `RADICADO`; `observacion` acepta `OBSERVACION`, `OBSERVACIONES`,
  `DETALLE`, `DETALLE GLOSA` y (21-jul) `DESCRIPCION GLOSA AUDITOR`,
  `DESCRIPCION GLOSA`, `OBSERVACION GLOSA`; `codigo_servicio` acepta `CUPS`.
- `_ALIAS_CARGUE` — identidad: cada campo del cargue se matchea por su
  propio nombre.
- `_RE_CODIGO_GLOSA = ^([A-Z]{2})\s*(\d{2})\s*(\d{2})$` — código de glosa
  Resolución 3047 (2 letras + concepto general + específico), aplicado sobre
  el texto normalizado (acepta `ta 29 01`).
- `_RE_DETALLE_OBS = \(([^()]*?)\s+CANTIDAD\s+(\d+)\s*\)\s*$` — patrón
  `(DESCRIPCION CANTIDAD n)` al final de la observación del acta (así vienen
  muchas observaciones reales, p. ej. `(CEFRADINA AMP X 1 GR CANTIDAD 5)`).

### Utilidades puras

- **`_norm(texto)`** — normaliza para comparar: convierte a texto, quita
  tildes (NFKD + remoción de combining chars), colapsa espacios repetidos,
  recorta y pasa a MAYÚSCULAS. Existe porque los encabezados reales varían
  en tildes/espacios/mayúsculas. `None` → `""`.
- **`_texto(valor)`** — celda → string limpio; un float entero (`890426.0`)
  se vuelve `"890426"` (los códigos de servicio numéricos de Excel).
- **`_numero(valor)`** — parser monetario tolerante es-CO. Acepta números
  nativos; en strings elimina todo salvo dígitos/coma/punto/signo y decide:
  ambos separadores → el último es el decimal; solo comas → decimal si el
  bloque final no tiene 3 dígitos; **varios puntos → separadores de miles**
  (`$ 1.234.567` → `1234567`); un punto con exactamente 3 decimales → miles
  (`8.500` → `8500`). Devuelve `int` si es entero, `float` si no, `None` si
  no parsea. (El caso multi-punto fue un bug encontrado por el propio test
  en la primera corrida y corregido en el momento.)
- **`_fecha(valor)`** — parsea `DD/MM/YYYY`, `YYYY-MM-DD` o `DD-MM-YYYY`;
  sin valor → fecha de hoy; inválida → `SystemExit` con mensaje claro.
- **`_partir_codigo_glosa(codigo)`** — `'TA2901'` → `('TA', 29)`; si no
  calza el patrón → `('', '')`.
- **`_mapear_encabezados(fila, alias)`** — devuelve `{campo: índice}`
  buscando cada alias (ya normalizado) dentro de los encabezados
  normalizados de la fila 1.

### Lectura y detección

- **`_abrir_hoja(ruta, nombre_hoja)`** — abre el workbook
  (`data_only=True, read_only=True`); si se pasó `--hoja` busca por nombre
  con `_norm` (tolerante); si no existe → `SystemExit` listando las hojas
  disponibles; sin `--hoja` usa la primera.
- **`leer_entrada(ruta, nombre_hoja)`** — pieza central de entrada:
  1. Llama `ws.reset_dimensions()` si está disponible — **imprescindible**:
     la plantilla real declara `<dimension A1:P1>` y sin esto openpyxl solo
     vería la fila 1 aunque hubiera datos (aprendizaje de esta sesión:
     `reset_dimensions()` solo existe en modo `read_only`).
  2. Itera todas las filas y descarta las totalmente vacías.
  3. Sin filas → `SystemExit`.
  4. **Autodetección**: si los encabezados contienen `CRNCXC` **y**
     `CROVALOBJ` → formato `"cargue"`; si contienen un alias de `factura`
     **y** de `valor_glosa` → `"consolidado"`; si ninguno → `SystemExit`
     mostrando los encabezados encontrados y qué se esperaba.
  5. Devuelve `(formato, filas_sin_encabezado, índices)`.

### Conversión ida (consolidado → cargue ERP)

- **`consolidado_a_cargue(filas, idx, cfg)`** — por cada fila:
  - factura vacía → se omite con `logger.warning` (no aborta el lote);
  - **`CDCONSEC`**: consecutivo **por factura** — un `OrderedDict`
    factura→número; todas las filas de una misma factura comparten
    consecutivo; arranca en `cfg.consecutivo_inicial`;
  - `CDFECDOC` = `cfg.fecha_documento`; `CROFECOBJ` = `cfg.fecha_objecion`;
  - `CRNCXC` = factura; con `--sin-prefijo` se quita el prefijo alfabético
    (`HUS521454` → `521454`, regex `^[A-Za-z]+`);
  - `CROREFERE` y `CROOBSERV` = referencia del acta (columna `acta` del
    consolidado, o `cfg.referencia` si el archivo no trae esa columna);
  - `CROCLAOBJ`/`CRNCLAOBJ` = clase y concepto general derivados del código
    (`TA2901` → `TA` / `29`);
  - `GENUSUARIO4` = `cfg.usuario`; `CRNCONOBJ` = código de glosa completo;
  - `SLNSERPRO` = código de servicio; `IDRIPS` = vacío (el consolidado no
    lo trae); `CTNCENCOS` = `cfg.centro_costos`;
  - `CROVALOBJ` = `_numero(valor glosa)`;
  - `CRDOBSERV` = observación tal cual; con `--detalle-servicio` se anexa
    `— SERVICIO <desc> CANT <n> VLR UNIT <u> VLR TOTAL <t>` (solo las partes
    disponibles);
  - `CROTIPOBJ` = `cfg.tipo_objecion` (vacío por defecto — ver riesgos §13).
- **`escribir_cargue(filas, ruta)`** — workbook nuevo, hoja `OBJECIONES`,
  encabezados exactos, `freeze_panes="A2"` (como la plantilla real), anchos
  de columna autoajustados `min(max(len contenido, len encabezado, 8)+2, 80)`,
  formato `DD/MM/YYYY` en `CDFECDOC`/`CROFECOBJ` (se escriben como fechas
  reales, no texto) y `#,##0` en `CROVALOBJ`.

### Conversión vuelta (cargue/export ERP → consolidado)

- **`cargue_a_consolidado(filas, idx)`** — por cada fila:
  - sin `CRNCXC` → se omite con warning;
  - código de glosa: `CRNCONOBJ`; si viene vacío se reconstruye de
    `CROCLAOBJ` + `CRNCLAOBJ` (`SO` + `8` → `SO08`);
  - observación = `CRDOBSERV`; acta = `CROOBSERV` o, en su defecto,
    `CROREFERE`;
  - **mejor esfuerzo**: si la observación termina en
    `(DESCRIPCION CANTIDAD n)` se extraen descripción y cantidad
    (`_RE_DETALLE_OBS` sobre el texto normalizado);
  - `VALOR UNITARIO`/`VALOR TOTAL` quedan vacíos — el layout del ERP no los
    trae y **no** se inventan (decisión explícita: la verificación mostró
    que en el acta real el valor glosado ≠ cantidad × unitario, así que no
    son derivables).
- **`escribir_consolidado(filas, ruta)`** — hoja `Hoja1` (como el ejemplo
  real), 10 encabezados exactos, formato contable
  `_-* #,##0_-;\-* #,##0_-;_-* "-"_-;_-@_-` en VALOR GLOSA / VALOR UNITARIO /
  VALOR TOTAL (idéntico carácter a carácter al del archivo real), anchos
  fijos `A:32 B:16 C:13 D:12 E:19 F:14 G:45 H:10 I:14 J:14` (E=19 coincide
  con el único ancho definido en el ejemplo real).

### Control y CLI

- **`_resumen(filas, idx_factura, idx_valor, idx_acta)`** — agrupa por acta
  y devuelve el texto "RESUMEN DE CONTROL (validar contra el acta)": por
  acta, número de facturas distintas, número de objeciones y valor glosado;
  más una línea TOTAL. Es la herramienta de cuadre del auditor.
- **`main(argv)`** — `argparse` con todos los flags (§12); valida existencia
  de la entrada (código de salida 2 si no existe); resuelve fechas; llama
  `leer_entrada`; según el formato ejecuta ida o vuelta; construye el nombre
  de salida por defecto junto a la entrada
  (`OBJECIONES_<ENTIDAD>.xlsx` o `CONSOLIDADO_VCO_<ENTIDAD>.xlsx`, entidad
  normalizada con `_` por espacios); imprime `OK: ... → <ruta>` y el resumen
  de control. **Caso especial**: un archivo OBJECIONES con solo encabezados
  produce el error explícito *"el archivo OBJECIONES no tiene filas de datos
  (solo encabezados). Exportá/pegá las objeciones de la entidad y volvé a
  correr el bot."* con código de salida 2 — respuesta directa al hecho de
  que el adjunto de SAVIA llegó vacío.

---

## 4. Flujo completo

No hay clic: es un CLI. Flujo desde el comando hasta el archivo final:

1. El auditor corre (Windows del HUS):
   `py tools\organizar_objeciones_vco.py --entrada "ARCHIVO.xlsx" --entidad "SAVIA SALUD" [flags]`.
2. `main` parsea flags, configura logging (`INFO`, formato
   `%(levelname)s %(message)s`), verifica que la entrada exista (si no,
   `ERROR: no existe ...` y exit 2), resuelve `--fecha-documento` (default
   hoy) y `--fecha-objecion` (default = fecha documento).
3. `leer_entrada` abre el Excel en modo lectura, corrige dimensiones
   mentirosas, descarta filas vacías, toma la fila 1 como encabezado y
   **autodetecta** el formato por los encabezados normalizados.
4. **Si es consolidado** → `consolidado_a_cargue`: se recorren las filas en
   su orden original; se asigna consecutivo por factura (primera aparición);
   se derivan clase/concepto del código de glosa; se arma la fila de 16
   columnas. → `escribir_cargue` produce `OBJECIONES_<ENTIDAD>.xlsx` con el
   formato exacto de la plantilla del ERP.
5. **Si es cargue/export** → `cargue_a_consolidado`: mapeo inverso, con
   reconstrucción del código si falta y extracción best-effort de
   descripción/cantidad de la observación. → `escribir_consolidado` produce
   `CONSOLIDADO_VCO_<ENTIDAD>.xlsx` con el formato del ejemplo de las demás
   entidades. Si el export no tiene filas → error claro y exit 2.
6. En ambos casos se imprime el **resumen de control** por acta para que el
   auditor cuadre facturas/objeciones/valores contra el acta antes de usar
   el archivo.

**Corridas reales ejecutadas en esta sesión:**

- `CONSOLIDADO_VCO.xlsx` (ejemplo, 58 filas Fiduprevisora) → cargue de 58
  filas. Control: acta `...14920`: 2 facturas, 32 objeciones, $3.263.265;
  acta `...14902`: 1 factura, 26 objeciones, $5.855.891; total $9.119.156.
  Consecutivos: 1=HUS521454, 2=HUS523499, 3=HUS526426. Entregado al usuario
  como `OBJECIONES_SAVIA_SALUD_DEMO.xlsx`.
- `OBJECIONES.xlsx` (vacío) → error controlado, exit 2 (comportamiento
  correcto demostrado).
- `CONSOLIDADO_VCO_FIDUPREVISORA.xlsx` (archivo real subido el 21-jul, 41
  filas, hoja `Hoja1`) → cargue de 41 filas. Control: acta `...14902`:
  2 facturas, 37 objeciones, $58.153.039; `...14904`: 1 factura, 3
  objeciones, $209.913; `...14951`: 1 factura, 1 objeción, $152.225; total
  $58.515.177. Consecutivos 1–4: HUS526971, HUS525731, HUS527275, HUS525559.
  0 filas sin observación, 0 sin acta. Entregado como
  `OBJECIONES_FIDUPREVISORA.xlsx`.

> Nota de custodia: los .xlsx generados se entregaron por el chat y viven en
> el scratchpad efímero de la sesión — **no** están versionados en el repo
> (decisión deliberada: son datos, no código). Se regeneran en segundos con
> el bot a partir del insumo.

---

## 5. Base de datos

**Ninguna.** El módulo no crea tablas, ni columnas, ni migraciones, ni toca
SQLite/PostgreSQL del motor. Su "modelo de datos" son los dos contratos de
columnas del §2. (Los nombres `CRNCXC`, `CROVALOBJ`, etc. son campos del ERP
del hospital — externos a este repo; el bot solo produce/lee el Excel.)

## 6. Backend

**No hay backend web.** Es un proceso batch local. Equivalencias:

- "Endpoints" → el CLI (`main(argv)`), invocable también programáticamente
  (así lo usan los tests: `org.main([...])`).
- Validaciones → existencia del archivo, formato reconocible, hoja
  existente, fechas parseables, filas con factura, montos parseables.
- Manejo de errores → mensajes en español por `stderr`; `SystemExit` con
  mensaje (formato/hoja/fecha inválidos) y `return 2` (entrada inexistente,
  consolidado sin filas válidas, cargue vacío); filas individuales inválidas
  se omiten con warning sin abortar el lote.
- Permisos → ninguno propio; hereda permisos del filesystem.

## 7. Frontend

**No aplica.** No se tocó `static/`, ni pantallas, ni componentes. La
"interfaz" es el CLI y el resumen de control impreso.

## 8. IA

**El módulo no usa IA en runtime** (es determinista a propósito: un cargue al
ERP no admite creatividad).

La IA se usó **en el proceso de desarrollo** como control de calidad:

- Se lanzó un workflow multi-agente (`review-organizar-objeciones-vco`) con
  3 revisores paralelos con lentes distintas — (1) correctness/parsing,
  (2) fidelidad del Excel contra las plantillas reales, (3) tests y
  convenciones del repo — con esquema de hallazgos tipado
  (file/line/title/detail/severity), dedup y verificación adversarial
  prevista de 2 escépticos por hallazgo (se confirmaba con ≥2 votos).
- El workflow quedó interrumpido por un reinicio de la sesión remota; se
  recuperó el resultado desde su `journal.jsonl`. La lente **fidelidad**
  terminó completa y verificó contra los 3 xlsx reales: encabezados
  byte-exactos y en orden, hoja y freeze idénticos, fechas como fecha y
  `CROVALOBJ` numérico, formato contable idéntico carácter a carácter al del
  archivo real (que incluso lo aplica de forma inconsistente — C17:C33 del
  ejemplo real quedaron en formato General; el bot es más consistente),
  58/58 filas sin discrepancias en los 7 campos mapeados, clase/concepto
  bien derivados para los 11 códigos de glosa presentes, autodetección
  correcta en ambos sentidos, y extracción inversa que recupera la cantidad
  exacta en las 27/58 filas donde el acta trae el patrón `( ... CANTIDAD n)`.
  Hallazgos: 2 de severidad baja (ver §15). Las lentes correctness y tests
  arrancaron pero no llegaron a terminar (ver §15).

## 9. Automatizaciones

1. **El bot mismo** — reemplaza la reorganización manual de actas; se
   ejecuta a demanda por comando.
2. **Vigilancia del PR #167** — la sesión quedó suscrita a los eventos del
   PR (webhooks de GitHub): fallos de CI y comentarios de revisión llegan a
   la conversación y se atienden. Con esa vigilancia se detectaron y
   resolvieron los dos incidentes de CI (§10, puntos 4–6). **Importante:**
   el usuario rechazó explícitamente el auto-chequeo programado cada hora
   (`send_later`); la vigilancia depende solo de webhooks — que **no**
   notifican éxito de CI, nuevos pushes ni conflictos de merge.
3. **CI del repo** (conocimiento operativo relevante levantado en la
   sesión): 3 jobs — *Lint (ruff)*: instala ruff **sin versión fija**
   (`pip install ruff`; ese día resolvió 0.15.22) y corre
   `ruff check . --select F,W6` + `ruff format --check .`; *Tests (pytest)*:
   suite completa (~4.110 tests, ~4 min) con
   `SECRET_KEY=ci-test-secret...`, `DATABASE_URL=sqlite:///./test_ci.db`,
   `PYTHONPATH=<repo>`, `DISABLE_SCHEDULERS=1`, sube artefactos
   `pytest-output-log` y `junit-results`; *Security scan (pip-audit)*.
4. **Auto-deploy del HUS** (contexto de docs del repo): la máquina del
   hospital se auto-actualiza desde Git (`auto_update.sh` + cron) — mergear
   a `motor-glosas` es lo que lleva el bot a producción.

## 10. Archivos modificados (lista completa, commit a commit)

Rama: `claude/savia-salud-objections-bot-o9qloo` (creada desde
`motor-glosas`, HEAD inicial `128b9eb`). Cinco commits propios:

1. **`411a199`** (17-jul) — *SAVIA SALUD: bot organizador de objeciones VCO
   (consolidado ↔ cargue ERP)* — 3 archivos nuevos, 1.177 líneas:
   - `tools/organizar_objeciones_vco.py` (nuevo): todo el §3.
   - `tests/test_tools/test_organizar_objeciones_vco.py` (nuevo): 30 tests.
   - `tools/README_organizar_objeciones_vco.md` (nuevo): guía completa.
2. **`b86d976`** (17-jul) — *style: newline final en test_import_history* —
   `tests/test_api/test_import_history.py`: 1 línea (+1/−1). **Motivo:** el
   job Lint de CI falló, pero el log demostró que los 2 archivos del bot
   estaban entre los "837 files already formatted"; el fallo era de este
   archivo preexistente al que le faltaba el salto de línea final que exige
   el ruff nuevo que CI instala sin pin. Mismo patrón del commit histórico
   `61f07ea` del repo.
3. **`e9a6856`** (21-jul) — *alias NUMERO RADICADO y DESCRIPCION GLOSA
   AUDITOR* — 2 archivos (+41/−2):
   - `tools/organizar_objeciones_vco.py`: 6 alias nuevos en
     `_ALIAS_CONSOLIDADO` (`NUMERO RADICADO`, `NRO RADICADO`, `RADICADO`
     para `acta`; `DESCRIPCION GLOSA AUDITOR`, `DESCRIPCION GLOSA`,
     `OBSERVACION GLOSA` para `observacion`). **Motivo:** el archivo real
     `CONSOLIDADO_VCO_FIDUPREVISORA.xlsx` traía esos dos encabezados; sin
     los alias el bot detectaba el formato pero dejaba acta y observación
     vacías en el cargue.
   - `tests/test_tools/test_organizar_objeciones_vco.py`: test nuevo
     `test_detecta_consolidado_variante_radicado` con los 10 encabezados
     reales de ese archivo (verifica además que `DESCRIPCION GLOSA AUDITOR`
     no se confunda con `DESCRIPCION SERVICIO`).
4. **`8bd6e84`** (21-jul) — *test: fechas relativas en por-dia-semana y
   heatmap (bomba de tiempo 90d)* — 2 archivos (+36/−13):
   - `tests/test_api/test_por_dia_semana.py`: import `timedelta`, helper
     nuevo `_lunes_pasado()` (lunes de la semana pasada 10:00 UTC),
     `test_clasifica_por_dia` y `test_pct_del_total` reescritos con fechas
     relativas (asserts intactos).
   - `tests/test_api/test_heatmap_actividad.py`: helper `_lunes_pasado()`
     (versión `date`), `test_ubica_eventos_en_celda_correcta` reescrito
     (`f"{lunes} 09:30"`, `09:45`, miércoles `14:15`; celdas de la matriz
     intactas). **Motivo (diagnóstico completo):** el 21-jul CI reportó
     `3 failed, 4109 passed`. Los 3 tests sembraban glosas con fechas fijas
     del 20–22 de abril de 2026 y los endpoints filtran con ventana default
     de 90 días desde "hoy": el 17-jul abril-20 estaba a 88 días (adentro,
     verde) y el 21-jul a 92 (afuera → `assert 0 == 2`). Se auditó el resto
     de la suite: los demás usos de fechas fijas de abril no filtran por
     ventana o mockean el reloj (p. ej. `test_audit_heatmap`,
     `test_heatmap_usuario` pasaron ese mismo día), así que el fix se limitó
     a los 2 archivos rotos. Verificado local: 8/8 tests de ambos archivos.
5. **`891283c`** (22-jul) — *docs: BITACORA.md + CLAUDE.md* — 2 archivos
   nuevos (+213): `BITACORA.md` (memoria común de sesiones: historial
   completo abril–julio reconstruido tras des-shallow del clon —
   `git fetch --unshallow`, primer commit real 2026-04-08 —, secciones LO YA
   HECHO por fecha, PENDIENTE, PARA MAÑANA, reglas de mantenimiento) y
   `CLAUDE.md` (obliga a cada sesión a leer la bitácora al inicio y
   actualizarla al cierre con commit y push).

Con esta entrega se agrega: `docs/ENTREGA_MODULO_ORGANIZAR_OBJECIONES_VCO.md`
(este documento) y la actualización de fecha correspondiente en
`BITACORA.md`.

## 11. Dependencias nuevas

**En el repositorio: ninguna.** `openpyxl==3.1.5` ya estaba pineado en
`requirements.txt` (línea 13) y es todo lo que el bot necesita.

En el **entorno de desarrollo** de la sesión (contenedor efímero) se
instalaron para trabajar: `openpyxl 3.1.5`, `pandas 3.0.3` (solo
inspección), `pytest`, `ruff` (local 0.15.8; CI usaba 0.15.22 — la
discrepancia es conocimiento útil: CI no pinea ruff), `black` (descartado:
el repo formatea con **ruff-format**, no black), y el grueso de
`requirements.txt` para correr los tests de API localmente (con dos
paquetes excluidos por no compilar en el contenedor: `http-ece`,
`sgmllib3k`, y `--ignore-installed cryptography` por el paquete de Debian).
Nada de esto cambia el proyecto.

## 12. Configuración

**Variables de entorno del módulo: ninguna. Tokens: ninguno. Rutas fijas:
ninguna.** Toda la parametrización es por flags del CLI:

| Flag | Default | Efecto |
|---|---|---|
| `--entrada` | (obligatorio) | Excel de entrada |
| `--salida` | junto a la entrada | Ruta exacta del Excel de salida |
| `--hoja` | primera hoja | Hoja a leer (match tolerante) |
| `--entidad` | `SAVIA SALUD` | Solo nombra el archivo de salida |
| `--referencia` | `""` | Acta a usar si el consolidado no trae columna de acta |
| `--fecha-documento` | hoy | `CDFECDOC` (DD/MM/YYYY) |
| `--fecha-objecion` | = fecha documento | `CROFECOBJ` |
| `--usuario` | `CARTERA` | `GENUSUARIO4` |
| `--centro-costos` | `""` | `CTNCENCOS` |
| `--tipo-objecion` | `""` | `CROTIPOBJ` |
| `--consecutivo-inicial` | `1` | Primer `CDCONSEC` (uno por factura) |
| `--sin-prefijo` | off | `HUS521454` → `521454` en `CRNCXC` |
| `--detalle-servicio` | off | Anexa servicio/cantidad/valores a `CRDOBSERV` |

Convenciones de estilo que el módulo debe respetar (config del repo):
pre-commit con `ruff` v0.11.8 + `ruff-format` + end-of-file-fixer +
no-commit-to-`main`; CI lint solo `--select F,W6` + `format --check`.

## 13. Riesgos

1. **Campos del ERP asumidos, no confirmados** (el riesgo principal). El
   usuario borró los datos de la plantilla OBJECIONES, así que nunca vimos
   un cargue aceptado por el ERP. Supuestos documentados y ajustables:
   `CDCONSEC` por factura; `CROCLAOBJ`=letras y `CRNCLAOBJ`=concepto general
   del código 3047; `CRNCONOBJ`=código completo (`TA2901`); `CROTIPOBJ`,
   `CTNCENCOS`, `IDRIPS` vacíos; `GENUSUARIO4`="CARTERA". Si el ERP usa
   catálogos propios (p. ej. tipo de objeción numérico), el cargue podría
   rechazarse. **Mitigación:** cotejar contra un cargue previo aceptado; los
   valores se corrigen con flags sin tocar código, o con cambios de 1 línea.
2. **Ambigüedad monetaria es-CO**: `1.234` se interpreta como 1234 (miles),
   no 1.234 decimal. Correcto para pesos, pero es una decisión.
3. **Dirección del pedido**: el mensaje original era ambiguo sobre qué
   formato era origen y cuál destino. Se resolvió con evidencia forense
   (metadatos openpyxl/cartera y timeline de los adjuntos) y cubriendo
   **ambas direcciones** con autodetección — solución elegida precisamente
   para que el riesgo de haber elegido mal la dirección desaparezca. Se
   descartó preguntar al usuario (sesión autónoma) y se descartó una
   herramienta unidireccional.
4. **Conflictos de merge**: los 3 archivos del módulo son nuevos (sin
   riesgo). Los 3 tests de API tocados (`test_import_history`,
   `test_por_dia_semana`, `test_heatmap_actividad`) sí existen en otras
   ramas — si otra rama los tocó, resolver conservando fechas relativas.
   `BITACORA.md`/`CLAUDE.md` son nuevos aquí; si el proyecto principal ya
   tiene un `CLAUDE.md`, fusionar contenidos a mano.
5. **CI con ruff sin pin**: cualquier release de ruff puede volver a romper
   el gate de formato con archivos que hoy pasan (ya ocurrió en esta rama).
   Recomendación al equipo principal: pinear la versión en el workflow.
6. **Tests con reloj**: la suite ya tenía historia de "time bombs" (commits
   previos del repo lo mencionan). El patrón `_lunes_pasado()` de esta rama
   es la referencia para no reintroducirlos.
7. **`SLNSERPRO` como texto**: los códigos de servicio numéricos se escriben
   como texto (`"890426"`). No hay evidencia de qué tipo espera el ERP
   (hallazgo baja del revisor); si exige número, es un cambio puntual en
   `consolidado_a_cargue`.

## 14. Dependencias con otros módulos

- **No importa nada de `app/`** ni de otros tools: es autónomo.
- **Convenciones heredadas** de `tools/convertir_tramite_masivo.py` (CLI,
  import perezoso de openpyxl, mensajes es-CO) y del patrón de matching
  tolerante de encabezados del bot COOSALUD (commit `5ec2713`).
- **Relación funcional** (no de código) con el ecosistema de glosas:
  produce el insumo de cargue del ERP del HUS (el sistema donde también
  opera `responder_glosas_dgh.py`), y consume los consolidados del portal
  VCO donde opera `responder_glosas_coosalud.py`.
- **Tests**: siguen el patrón de `tests/test_tools/` (import por ruta con
  `sys.path.insert` porque `tools/` no tiene `__init__.py`;
  `pytest.importorskip("openpyxl")`).
- Nada en el repo depende de este módulo todavía.

## 15. Pendientes

1. **El archivo real de SAVIA SALUD nunca llegó** — el `OBJECIONES.xlsx`
   adjuntado tenía solo encabezados. El bot está listo; falta el insumo.
2. **Validación contra el ERP** de los campos asumidos (§13.1) con un cargue
   previamente aceptado.
3. **PR #167 sigue en borrador** con CI verde — falta marcarlo listo y
   mergearlo a `motor-glosas` (eso además publica el bot en la máquina del
   HUS por el auto-update, y lleva BITACORA/CLAUDE.md a la rama principal).
4. **Revisión multi-agente incompleta**: de las 3 lentes solo terminó
   "fidelidad Excel" (resultado: sin defectos reales; 2 hallazgos baja
   aceptados conscientemente: anchos de columna que las plantillas no
   definen —cosmético y beneficioso— y la nota de tipo de `SLNSERPRO`).
   Las lentes "correctness" y "tests/convenciones" quedaron truncadas por
   el reinicio de la sesión; si el equipo quiere el cinturón completo,
   re-correr una revisión sobre `tools/organizar_objeciones_vco.py`.
5. **Errores conocidos**: ninguno reproducible a la fecha; 31 tests del
   módulo y suite completa de CI en verde.
6. Mejora prevista (no comprometida): mapa configurable de catálogos del
   ERP (tipo objeción/centro de costos por entidad) si la validación del
   punto 2 muestra que varían.

## 16. Recomendaciones para fusionarlo al proyecto principal

Paso a paso, sin perder nada:

1. **Mergear el PR #167** (`claude/savia-salud-objections-bot-o9qloo` →
   `motor-glosas`). Es la vía que preserva los 5 commits con su historia y
   mensajes (que documentan el porqué de cada cambio). Alternativa si el
   proyecto principal vive en otro repo: cherry-pick de `411a199`,
   `e9a6856` (el bot y sus alias) y llevar aparte `b86d976`/`8bd6e84`
   (higiene de CI, específicos de este repo).
2. **Verificar post-merge**:
   `python3 -m pytest tests/test_tools/test_organizar_objeciones_vco.py -q`
   (31 pass) y `ruff check --select F,W6` + `ruff format --check` sobre los
   archivos del módulo.
3. **Prueba funcional de humo**: correr el bot contra
   `CONSOLIDADO_VCO_FIDUPREVISORA.xlsx` (el usuario lo tiene) y comparar el
   resumen de control con los totales de §4 ($58.515.177 / 41 objeciones).
4. **Antes del primer cargue real al ERP**: ejecutar la validación del
   §13.1 con un cargue histórico aceptado; ajustar flags o los 3 puntos de
   mapeo si difieren.
5. **Si el proyecto principal ya tiene CLAUDE.md/bitácora**: fusionar el
   contenido de `BITACORA.md` de esta rama (es la reconstrucción completa
   abril–julio del repo) dentro del documento maestro, en vez de
   sobreescribir.
6. **Endurecer CI** (opcional, recomendado): pinear ruff en
   `.github/workflows/ci.yml` para que el gate de formato no dependa del
   release del día.
7. No hay migraciones, variables de entorno, seeds ni pasos de despliegue
   propios del módulo: con el merge, está entregado.

## 17. Resumen ejecutivo (para quien lo mantenga)

- **Qué es**: un conversor determinista y bidireccional entre el consolidado
  de actas de objeciones del portal VCO (10 columnas) y la plantilla de
  cargue masivo de objeciones del ERP del HUS (16 columnas), con
  autodetección de formato, alias tolerantes de encabezados, consecutivo por
  factura, derivación de clase/concepto desde el código de glosa
  (Res. 3047), parser monetario es-CO y resumen de control por acta.
- **Dónde vive**: `tools/organizar_objeciones_vco.py` + README + 31 tests.
  Sin BD, sin backend, sin frontend, sin IA, sin env vars. Una sola
  dependencia (openpyxl, ya en requirements).
- **Cómo se corre**:
  `py tools\organizar_objeciones_vco.py --entrada "X.xlsx" --entidad "SAVIA SALUD"`.
  El resumen impreso es la herramienta de cuadre del auditor.
- **La regla de oro para modificarlo**: los encabezados de salida de ambos
  formatos son un **contrato** (el ERP y el equipo de cartera los esperan
  byte-exactos). Nuevas variantes de entrada se resuelven agregando alias a
  `_ALIAS_CONSOLIDADO` + un test con los encabezados reales (patrón del
  commit `e9a6856`).
- **El único cabo suelto real**: los valores por defecto de
  `CROTIPOBJ`/`CTNCENCOS`/`GENUSUARIO4` y la semántica exacta de
  `CROCLAOBJ`/`CRNCLAOBJ`/`CRNCONOBJ` nunca se validaron contra un cargue
  aceptado por el ERP (el insumo llegó vacío). Todo es ajustable por flag.
- **Contexto de operación**: PR #167 (draft, CI verde) vigilado por
  webhooks; el usuario no quiso chequeos programados por hora. El detalle
  del día a día del proyecto completo está en `BITACORA.md` — leerla
  primero, siempre.
