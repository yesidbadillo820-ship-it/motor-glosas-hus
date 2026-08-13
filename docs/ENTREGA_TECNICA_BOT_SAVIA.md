# ENTREGA TÉCNICA — Módulo "BOT SAVIA: organizador de objeciones (formato 16 columnas)"

> **Documento oficial de entrega del módulo al equipo principal.**
> Reconstruye TODO lo realizado en la conversación/rama
> `claude/savia-salud-objections-bot-fni6dq` (Pull Request **#164** contra la
> rama principal `motor-glosas` del repositorio
> `yesidbadillo820-ship-it/motor-glosas-hus`), incluidas las decisiones
> técnicas, los cambios de enfoque, las soluciones descartadas y los trabajos
> colaterales (bitácora del proyecto y arreglo de pruebas del CI).
>
> Período de la sesión: 16–17 de julio de 2026 (fechas de commits del
> contenedor) y 22 de julio de 2026 (bitácora + arreglo de CI).
> Idioma del proyecto: **español**. Usuario final: auditor (no programador).

---

## 1. Objetivo del desarrollo

**Por qué se creó.** El equipo de glosas del HUS recibe de la EPS **SAVIA
SALUD** una relación de objeciones en un Excel plano de **8 columnas**
(`SAVIA_SALUD_8.03.xlsx`). Para tramitar esas objeciones, el equipo trabaja con
un formato interno de **16 columnas** (hoja `OBJECIONES`) — el mismo layout de
los archivos `OBJECIONES_DISPENSARIO_HUS*.xlsx` y `OBJECIONES_EMSSANAR_*.xlsx`
que ya se usan para otras entidades. Pasar de un formato al otro a mano es
lento y propenso a errores (consecutivos, tipos de celda, textos con el valor
pegado, un archivo por factura).

**Qué problema resolvía.** Automatizar por completo esa conversión:
`Excel de SAVIA (8 col) → formato de trabajo de 16 columnas`, con todas las
reglas operativas del equipo incorporadas y verificadas contra archivos reales.

**Qué necesidad cubría.** La usuaria pidió: *"crear un bot que me organice las
objeciones de la entidad SAVIA SALUD como lo hizo con COOSALUD"*, adjuntando
dos Excel: el de SAVIA (los datos) y uno del Dispensario (**la guía/plantilla
de columnas** — ver §13.1 sobre el malentendido inicial de dirección).

El bot sigue el patrón ya establecido en el repo por
`tools/convertir_tramite_masivo.py` (convertidor CRRP→SIMED): una herramienta
CLI de un solo archivo en `tools/`, con README propio y tests en
`tests/test_tools/`.

---

## 2. Arquitectura

### 2.1 Estructura del módulo (archivos NUEVOS)

```
tools/
├── organizar_objeciones_savia.py          ← el bot (CLI, ~470 líneas)
└── README_organizar_objeciones_savia.md   ← guía de uso completa
tests/
└── test_tools/
    └── test_organizar_objeciones_savia.py ← 36 tests unitarios + end-to-end
docs/
└── ENTREGA_TECNICA_BOT_SAVIA.md           ← este documento
BITACORA.md                                 ← memoria común del proyecto (nuevo)
CLAUDE.md                                   ← regla de uso de la bitácora (nuevo)
```

### 2.2 Archivos EXISTENTES modificados (trabajo colateral)

```
tests/test_api/test_import_history.py       ← newline final faltante (CI Lint)
tests/test_api/test_heatmap_actividad.py    ← time-bomb de fechas (CI Tests)
tests/test_api/test_por_dia_semana.py       ← time-bomb de fechas (CI Tests)
```

### 2.3 Componentes internos del bot (en orden de aparición en el archivo)

| Componente | Tipo | Rol |
|---|---|---|
| `COLUMNAS_DISPENSARIO` | tupla (16 strings) | Orden EXACTO de columnas de salida |
| `CDCONSEC_DEFAULT = 1` | constante | Número inicial del consecutivo por factura |
| `CROCLAOBJ_CONST = 0` | constante (int) | Valor fijo de la columna CROCLAOBJ |
| `GENUSUARIO4_CONST = "999"` | constante (**str**) | Valor fijo de GENUSUARIO4 (texto, ver §13.5) |
| `CODIGO_SUFIJO_DEFAULT = "01"` | constante | Sufijo para completar el código 4→6 |
| `COLUMNAS_SAVIA` | dict de sets | Alias de encabezados de entrada (tolerante) |
| `IDX_FALLBACK` | dict | Índices fijos 0..7 de respaldo |
| `_norm_header` | función | Normaliza encabezados (mayúsculas, sin tildes) |
| `_resolver_columnas` | función | Mapea encabezado→índice con respaldo |
| `_cell` | función | Lectura segura de celda (filas cortas) |
| `_num` | función | Conversión robusta a entero |
| `factura_larga` | función | HUS443697 → HUS0000443697 |
| `codigo_dispensario` | función | TA08 → TA0801 (sufijo/mapa) |
| `GRUPO_CLINICO = "CL"` | constante | Grupo clínico para CROTIPOBJ |
| `crotipobj_factura` | función | Regla 0/1/2 por mezcla de conceptos |
| `construir_crdobserv` | función | "<código> <texto>$<valor>" |
| `construir_registros` | función | Pipeline de lectura+transformación |
| `FORMATOS_DISPENSARIO` | dict | number_format por columna (16/16 del real) |
| `_escribir_hoja` | función | Escritura de una hoja OBJECIONES |
| `PREFIJO_DEFAULT = "OBJECIONES_SAVIA"` | constante | Prefijo de archivos por factura |
| `escribir_por_factura` | función | Un .xlsx por factura |
| `escribir_consolidado` | función | Un solo .xlsx con todo |
| `_cargar_mapa` | función | Carga del JSON --mapa-codigos |
| `_parse_fecha` | función | Valida --fecha (YYYY-MM-DD) |
| `_resumen` | función | Resumen final en el log |
| `main` | función | CLI (argparse) |

### 2.4 Dependencias y librerías

- **openpyxl** — única dependencia de ejecución (lectura/escritura .xlsx).
  Verificada en el PC de la usuaria: 3.1.5 (con `et-xmlfile` 2.0.0).
- Biblioteca estándar: `argparse`, `datetime`, `json`, `logging`, `re`, `sys`,
  `unicodedata`, `collections.defaultdict`, `pathlib.Path`.
- **Sin IA, sin red, sin base de datos, sin credenciales** (a diferencia de los
  bots Playwright del repo, este es un transformador de archivos puro).
- Desarrollo/pruebas: `pytest` (9.1.1 en el entorno de la sesión), `ruff`
  0.11.8 (la versión pineada en `.pre-commit-config.yaml`).
- Python: el repo exige ≥3.11 (`pyproject.toml`); probado en 3.11.15
  (contenedor de la sesión) y funciona en el 3.14 del PC de la usuaria.

### 2.5 APIs / modelos / servicios

Ninguno. El módulo NO toca `app/` (el motor de glosas web), no expone
endpoints, no usa modelos de base de datos ni servicios. Es una herramienta de
línea de comandos autocontenida, deliberadamente, siguiendo el patrón de
`tools/` del repo.

---

## 3. Funciones implementadas (lista completa, estado final)

Para cada una: qué hace, cómo funciona, por qué existe, dependencias.

1. **`_norm_header(h) -> str`**
   - Qué hace: normaliza un encabezado de Excel — mayúsculas, sin tildes
     (NFKD + descarte de combining), espacios colapsados.
   - Por qué existe: los Excel reales traen encabezados inconsistentes; el
     mapeo por nombre debe ser tolerante (mismo criterio que el bot COOSALUD).
   - Usada por: `_resolver_columnas`.

2. **`_resolver_columnas(headers) -> dict[str, int]`**
   - Qué hace: para cada campo lógico de SAVIA (`factura`, `cod_servicio`,
     `servicio`, `cantidad`, `valor_unitario`, `valor_glosa`, `motivo`,
     `observacion`) busca el índice de columna por nombre contra los alias de
     `COLUMNAS_SAVIA`; si no lo encuentra, cae al índice fijo de `IDX_FALLBACK`
     (0..7, el layout observado de `SAVIA_SALUD_8.03.xlsx`) con un
     `logger.debug`.
   - Por qué existe: robustez ante cambios menores de encabezados sin romper
     con archivos "tal cual".

3. **`_cell(row, idx, clave)`**
   - Qué hace: devuelve `row[idx[clave]]` o `None` si la fila es más corta que
     el índice (filas recortadas de exportaciones).
   - Historia: nació como cierre (closure) dentro del bucle y se extrajo a
     nivel de módulo para resolver la alerta **B023** de ruff (función que
     captura la variable de bucle `r`) — ver §13.7.

4. **`_num(v) -> int`**
   - Qué hace: convierte a entero tolerando `None`, floats, `'$1.234'`,
     `'1,234'`, texto no numérico (→ 0). Regex: quita todo lo que no sea
     dígito o signo.

5. **`factura_larga(fac, ancho=10) -> str`**
   - Qué hace: `HUS443697` → `HUS0000443697` (prefijo alfabético en mayúsculas
     + parte numérica con ceros a la izquierda hasta 10 dígitos). Idempotente
     (`HUS0000443697` se queda igual). Si el texto no matchea
     `^([A-Za-z]+)0*(\d+)$`, se devuelve tal cual.
   - Por qué existe: el formato de trabajo usa la factura larga (verificado en
     la guía y en EMSSANAR). Es la operación INVERSA de
     `radicar_facturacion.factura_corta` que ya existía en el repo.

6. **`codigo_dispensario(motivo, sufijo="01", mapa=None) -> str`**
   - Qué hace: completa el código de objeción de SAVIA (4 caracteres,
     grupo+concepto: `TA08`) al de 6 del formato de trabajo
     (grupo+concepto+consecutivo: `TA0801`).
   - Cómo: (1) si `mapa` (dict de `--mapa-codigos`) trae el código exacto, ese
     gana; (2) si el código matchea `[A-Z]{2}\d{2}` exacto se le agrega el
     `sufijo`; (3) si ya viene con 6+ caracteres se deja tal cual. Tolera
     espacios y minúsculas.
   - ⚠️ Supuesto pendiente de confirmación: el sufijo `01` (ver §15.1).

7. **`crotipobj_factura(grupos: set[str]) -> int`**
   - Qué hace: aplica la regla de negocio del equipo para `CROTIPOBJ`:
     solo administrativos (TA/FA/SO/AU…) → `0`; solo `CL` → `1`;
     administrativos + `CL` → `2`.
   - Cómo: `tiene_cl = "CL" in grupos`; `tiene_admin = any(g != "CL")`.
     Cualquier grupo distinto de CL cuenta como administrativo (decisión: la
     usuaria enumeró TA/FA/SO/AU; se generalizó a "no-CL" para cubrir grupos
     no vistos, p. ej. CO).
   - Origen: corrección directa de la usuaria (ver §13.6). Los archivos reales
     de referencia traían `0` constante incluso en facturas mezcladas; la
     regla de trabajo del equipo prevalece sobre lo observado en esos archivos.

8. **`construir_crdobserv(codigo, observacion, valor) -> str`**
   - Qué hace: arma la columna `CRDOBSERV` con el formato de los archivos
     reales: `"<código> <texto>$<valor>"` (ej.:
     `TA0801 LOS CARGOS POR APOYO…POR VALOR DE 55200$15400`).
   - Cómo: quita el código del inicio del texto si ya viniera (case-insensitive)
     y un `$NNN` final si ya viniera (`_RE_VALOR_FINAL = \$\s*[\d.,]+\s*$`),
     y concatena `f"{cod} {texto}${valor}"`. Así es idempotente y no duplica.
   - Verificación: la regla se validó contra el archivo EMSSANAR — 37/37 filas
     empiezan con el código y contienen `$<CROVALOBJ>`; la salida quedó
     161/161.

9. **`construir_registros(ruta, fecha, consecutivo, codigo_sufijo, mapa_codigos) -> list[dict]`**
   - Qué hace: lee el Excel de SAVIA (hoja activa, `read_only`, `data_only`) y
     devuelve una lista de dicts con las 16 claves de `COLUMNAS_DISPENSARIO`.
   - Lógica interna, en orden:
     1. Lee encabezados y resuelve índices (`_resolver_columnas`).
     2. Recorre filas; salta las que no tienen factura ni observación ni motivo.
     3. `CDCONSEC`: mantiene `consec_por_factura` — la 1ª factura que aparece
        recibe `consecutivo` (default 1), la 2ª `consecutivo+1`, etc.; TODAS
        las filas de una factura llevan su número, **como texto** (`"1"`,
        `"2"`). Numeración por orden de aparición.
     4. Campos: `CRNCXC=factura_larga(...)`, `CRNCONOBJ=codigo_dispensario(...)`,
        `SLNSERPRO=Cod_Servicio` tal cual (conserva sufijos `-NN` de
        medicamentos — EMSSANAR también los trae), `CROVALOBJ=_num(Valor_Glosa)`,
        `CRDOBSERV=construir_crdobserv(...)`, `CDFECDOC=CROFECOBJ=fecha`,
        `CROCLAOBJ=0`, `GENUSUARIO4="999"`, `CROTIPOBJ=0` (placeholder),
        `CROREFERE/CROOBSERV/CRNCLAOBJ/IDRIPS/CTNCENCOS=None`.
     5. **Segunda pasada**: agrupa por `CRNCXC` los prefijos de 2 letras de
        `CRNCONOBJ` y asigna `CROTIPOBJ=crotipobj_factura(grupos)` a todas las
        filas de cada factura.
   - Nota: las columnas de SAVIA `Servicio`, `Cantidad_Servicio` y
     `Valor_Unitario` **no se usan** en la salida final (el formato de 16
     columnas no las tiene como campo propio); sus alias se conservan en
     `COLUMNAS_SAVIA` por si se necesitan a futuro.

10. **`_escribir_hoja(registros, salida)`**
    - Qué hace: escribe UN .xlsx con hoja `OBJECIONES`: encabezado con fondo
      azul `1F4E78` y letra blanca en negrita (estilo de los tools del repo),
      `freeze_panes="A2"`, y **number_format por columna** tomado de
      `FORMATOS_DISPENSARIO` (copiado 1:1 del archivo real EMSSANAR):
      `CDFECDOC`/`CROFECOBJ`=`mm-dd-yy` (fecha corta builtin de Excel — se ve
      `dd/mm/yyyy` según configuración regional, SIN horas), texto `@` en
      CDCONSEC, CRNCXC, CROREFERE, CROOBSERV, CRNCLAOBJ, GENUSUARIO4,
      CRNCONOBJ, SLNSERPRO, IDRIPS, CTNCENCOS y CRDOBSERV; `General` en
      CROCLAOBJ; formato **contable de miles**
      `_-* #,##0_-;\-* #,##0_-;_-* "-"_-;_-@_-` en CROVALOBJ; `0` en
      CROTIPOBJ. Crea la carpeta destino si no existe.

11. **`escribir_por_factura(registros, carpeta, prefijo="OBJECIONES_SAVIA", consecutivo=1) -> list[Path]`**
    - Qué hace: agrupa por `CRNCXC` y escribe
      `<prefijo>_<CRNCXC>.xlsx` por cada factura, ordenadas alfabéticamente.
    - Detalle: como cada archivo standalone lleva UNA sola factura, su
      `CDCONSEC` se **reinicia** a `str(consecutivo)` (default `"1"`), igual
      que la guía original de una factura.

12. **`escribir_consolidado(registros, salida)`** — todo en un único .xlsx
    (aquí sí se conserva la numeración 1,2,3… por factura).

13. **`_cargar_mapa(ruta) -> dict`** — lee el JSON de `--mapa-codigos`
    (`{"TA08": "TA0805", …}`); valida que sea objeto JSON; claves a mayúsculas.
    Sale con código 2 ante error de lectura/parseo.

14. **`_parse_fecha(texto) -> datetime`** — `--fecha` en `YYYY-MM-DD`; default
    hoy a medianoche. Formato inválido → error claro y exit 2.

15. **`_resumen(registros)`** — imprime: nº de facturas, nº de objeciones,
    valor glosado total, y conteo por código `CRNCONOBJ` (orden desc.).

16. **`main(argv) -> int`** — CLI completa (ver §12.2). Retorna 0 éxito,
    1 error de entrada (archivo inexistente / sin objeciones).

### 3.1 Funciones que EXISTIERON y fueron descartadas (v1, ver §13.1)

La primera versión (dirección invertida, commit `d7dbf34`) contenía funciones
que ya NO están en el módulo final pero quedan en el historial de git:
`factura_corta`, `codigo_savia` (CL0801→CL08), `extraer_cantidad`
("SE FACTURA UNA UNIDAD"→1, con diccionario de números en palabra 1–12),
`extraer_valor_unitario` ("POR VALOR DE N PESOS" ÷ cantidad),
`extraer_servicio` (texto tras "SE GLOSA CODIGO <cod>"), `limpiar_observacion`
(quitaba el `$NNN` final y opcionalmente el encabezado), `ENCABEZADOS_SAVIA`,
flags `--codigo corto/completo`, `--limpiar-encabezado`,
`--sin-normalizar-factura`, y soporte de `--entrada` múltiple/carpeta.
Se descartaron porque la dirección real es SAVIA→16 columnas.

---

## 4. Flujo completo (paso a paso)

**Uso normal (por la auditora, en Windows):**

1. La usuaria descarga `organizar_objeciones_savia.py` y coloca el Excel de
   SAVIA en la misma carpeta (recomendado: `Descargas`).
2. En PowerShell:
   `cd $HOME\Downloads` y luego
   `py .\organizar_objeciones_savia.py --entrada "SAVIA_SALUD_8.03.xlsx" --salida "OBJECIONES_SAVIA"`
   (o `--salida archivo.xlsx --consolidado` para un único Excel).
3. Internamente el bot:
   1. Valida que `--entrada` exista (si no: error y exit 1).
   2. Parsea `--fecha` (default hoy) y `--mapa-codigos` (default vacío).
   3. `construir_registros`: lee la hoja activa, mapea columnas por nombre
      (fallback índices 0..7), arma los 16 campos por fila, asigna el
      consecutivo por factura y, en segunda pasada, el `CROTIPOBJ` 0/1/2.
   4. Escribe la salida: por factura (`OBJECIONES_SAVIA_<factura>.xlsx`, con
      CDCONSEC reiniciado a 1 en cada archivo) o consolidada (numeración
      1,2,3… por factura), con los 16 formatos de celda del archivo real.
   5. Imprime el resumen (facturas, objeciones, valor total, códigos).
4. La usuaria toma los .xlsx generados y los usa en su trámite habitual.

**Resultado real verificado con `SAVIA_SALUD_8.03.xlsx`:**
- 161 objeciones → `OBJECIONES_SAVIA_HUS0000443697.xlsx` (148 filas,
  CDCONSEC=1, CROTIPOBJ=2 por mezclar CL+FA+SO+TA) y
  `OBJECIONES_SAVIA_HUS0000503425.xlsx` (13 filas, CDCONSEC=2 en el
  consolidado / 1 standalone, CROTIPOBJ=0 por ser solo TA).
- Valor glosado total: **$4.177.858**.
- Códigos resultantes: TA0801×142, CL0701×6, TA0201×6, FA5801×2, CL0801×1,
  FA0101×1, SO6101×1, TA0101×1, TA5801×1.

**Vía alterna usada en la práctica:** la usuaria sube el Excel de SAVIA al chat
de Claude Code y el bot se ejecuta en el entorno remoto; se le devuelven los
.xlsx ya convertidos (así se entregaron todos los resultados de esta sesión,
porque la corrida local en su PC no se concretó — ver §15.3).

---

## 5. Base de datos

**El módulo NO usa base de datos** (ni tablas, ni migraciones, ni índices).
Lee un .xlsx y escribe .xlsx.

Referencia colateral: el arreglo de CI (§9.3) tocó tests que usan los modelos
existentes del motor (`app/models/db.py`): `GlosaRecord` (campos observados en
los tests: `eps`, `paciente`, `codigo_glosa`, `valor_objetado`, `etapa`,
`estado`, `creado_en`) y `UsuarioRecord` (`id`, `email`, `rol`, `activo`), con
SQLite en memoria vía SQLAlchemy. No se modificó ningún modelo ni esquema.

## 6. Backend

**No aplica al módulo** (no hay endpoints, controladores, middleware ni
permisos — es CLI puro). Validaciones y errores del CLI:

- `--entrada` inexistente → `ERROR` en log y exit 1.
- Hoja vacía / sin objeciones → `ERROR` y exit 1.
- `--fecha` mal formada → mensaje con el formato esperado y exit 2.
- `--mapa-codigos` ilegible o no-objeto JSON → mensaje y exit 2.
- Falta openpyxl → mensaje con el comando de instalación y exit 2.

Referencia colateral: los tests de CI arreglados corresponden a los endpoints
existentes `GET /glosas/stats/heatmap-actividad` y
`GET /glosas/stats/por-dia-semana` del motor, ambos con **ventana móvil default
de 90 días** — dato clave del diagnóstico (§9.3). Ninguno fue modificado.

## 7. Frontend

**No aplica.** No hay pantallas, componentes ni formularios. La "interfaz" es
la línea de comandos + los Excel generados (encabezado azul institucional,
panel congelado, columnas con ancho/formato correctos).

## 8. IA

**El módulo NO usa IA** en ejecución: es 100 % determinista (regex + reglas).
No hay prompts, proveedores, modelos, temperatura ni fallbacks.

La IA participó únicamente como **herramienta de desarrollo** (esta sesión de
Claude Code escribió el código, los tests y la documentación, guiada por las
correcciones de la usuaria). No queda ninguna dependencia de IA en el runtime.

## 9. Automatizaciones

1. **El bot mismo** — convierte lotes completos sin intervención (por factura o
   consolidado). Se ejecuta manualmente cuando llega una relación de SAVIA.
2. **CI del repositorio** (ya existía; `.github/workflows/ci.yml`): en cada
   push a `claude/**` corren 3 jobs — Lint (`ruff check . --select F,W6` +
   `ruff format --check .`), Tests (pytest con `SECRET_KEY`, `DATABASE_URL`
   sqlite, `PYTHONPATH`, `DISABLE_SCHEDULERS=1`), Security (`pip-audit` con
   `--ignore-vuln GHSA-h75v-3vvj-5mfj`). El PR #164 quedó verde tras los
   arreglos de §9.3 y §10.
3. **Vigilancia del PR #164** — la sesión quedó suscrita a la actividad del PR
   (webhooks de comentarios y fallos de CI). Así se detectó y corrigió el
   fallo del 22-jul. Se usaron auto-chequeos programados (`send_later`) durante
   la sesión para verificar el CI; la usuaria **rechazó** el último
   re-agendamiento, por lo que se dejó solo la vigilancia por webhook (decisión
   registrada — no reactivar chequeos programados sin pedirlo ella).
4. **Regla de bitácora** (`CLAUDE.md`): toda sesión futura de Claude Code en el
   repo debe leer `BITACORA.md` al iniciar y actualizarla al terminar (fecha,
   hecho, pendiente, mañana). Es una automatización de proceso, no de código.

### 9.3 Trabajo colateral: arreglo de las pruebas "bomba de tiempo" del CI

- **Síntoma** (webhook, 22-jul): job Tests rojo en un commit que solo agregaba
  documentación. 3 fallos / 4.114 pasando:
  `test_heatmap_actividad.py::test_ubica_eventos_en_celda_correcta`
  (assert 0 == 2), `test_por_dia_semana.py::test_clasifica_por_dia`
  (assert 0 == 2) y `::test_pct_del_total` (assert 0.0 == 80.0).
- **Diagnóstico**: esos tests sembraban glosas en fechas FIJAS (20/21/22 de
  abril de 2026) contra endpoints con ventana móvil de 90 días (el propio
  archivo lo prueba en `test_excluye_fuera_ventana`). 20-abr + 90 días ≈
  19-jul: desde esa fecha los conteos daban 0. El repo ya había tenido un caso
  igual (commit de junio: "test time-bomb").
- **Arreglo**: helper `_dia_semana_reciente(weekday, hora[, minuto])` en ambos
  archivos — devuelve el lunes/martes/miércoles más reciente de hace ≥7 días
  (entre 7 y 13 días atrás), siempre dentro de la ventana, cualquiera sea el
  día en que corra el CI. Mismas horas de siembra (09:30/09:45/14:15 y
  10:00/11:00) para no alterar las celdas esperadas del heatmap
  (fila=weekday, col=hora). De paso, `ruff --fix` aplicó el alias
  `datetime.UTC` (regla UP017) en el archivo del heatmap y se eliminó un
  import local redundante de `timedelta` en el otro.
- **Verificación local**: 20/20 tests de la familia (los 2 archivos arreglados
  + `test_picos_historicos.py`, `test_desempeno_trimestral.py`,
  `test_stats_por_anio.py`, que también usan fechas fijas pero contra
  endpoints sin esa ventana — pasaron sin tocar; ver riesgo §13.8).

---

## 10. Archivos modificados (lista completa, commit por commit)

Rama: `claude/savia-salud-objections-bot-fni6dq`. Commits en orden:

| Commit | Archivos | Qué cambió exactamente |
|---|---|---|
| `d7dbf34` | `tools/organizar_objeciones_savia.py`, `tools/README_organizar_objeciones_savia.md`, `tests/test_tools/test_organizar_objeciones_savia.py` (nuevos) | **v1 (dirección equivocada)**: Dispensario→SAVIA 8 col, extracción por texto, 38 tests. |
| `01cd9ce` | `tests/test_api/test_import_history.py` | Newline final faltante (preexistente, de un merge 8 días antes) que rompía `ruff format --check .` en el job Lint. |
| `f7307c5` | los 3 archivos del módulo | **v2 (reescritura total)**: dirección correcta SAVIA→16 columnas, un archivo por factura `OBJECIONES_DISPENSARIO_<CRNCXC>.xlsx`, `factura_larga`, `codigo_dispensario`, constantes de la guía, `--consolidado`, 28 tests nuevos. |
| `2a2ed51` | los 3 archivos del módulo | Salida renombrada a `OBJECIONES_SAVIA_<factura>.xlsx` + flag `--prefijo` (corrección de la usuaria: los archivos son de SAVIA, el del Dispensario era solo guía). |
| `69a90c9` | tool + tests | `construir_crdobserv`: CRDOBSERV = `<código> <texto>$<valor>` (verificado 37/37 contra EMSSANAR; salida 161/161). +3 tests. |
| `7d4bc17` | tool + tests | `CDCONSEC` = consecutivo POR FACTURA (1-1-1, 2-2-2…) por orden de aparición; `--consecutivo` pasa a ser número inicial; standalone reinicia en 1. +2 tests. |
| `264d405` | tool + tests | Tipos de celda: `CDCONSEC` y `GENUSUARIO4` como TEXTO (`'1'`, `'999'`), igual que los archivos reales; valores siguen como número. |
| `05c4972` | tool + tests | Fechas en FECHA CORTA (`mm-dd-yy`, sin horas) y `FORMATOS_DISPENSARIO` con los 16 number_format copiados 1:1 de EMSSANAR (verificado 16/16). +1 test. |
| `0eb09fb` | tool + tests | `CROTIPOBJ` por factura (regla 0/1/2 de la usuaria) con `crotipobj_factura` en segunda pasada. +2 tests (total 36). |
| `5a88d51` | README del módulo | Documentadas todas las reglas finales en la tabla de mapeo. |
| `53d26e1` | `BITACORA.md`, `CLAUDE.md` (nuevos) | Memoria común del proyecto (217 commits reconstruidos, 12-jun→17-jul, por fecha + PENDIENTE + PARA MAÑANA) y regla de lectura/actualización obligatoria. |
| `575e9ce` | `tests/test_api/test_heatmap_actividad.py`, `tests/test_api/test_por_dia_semana.py`, `BITACORA.md` | Time-bomb de fechas desactivada (helper de fechas relativas); alias `datetime.UTC` (UP017); bitácora con la entrada del 22-jul. |

*(Después de `575e9ce` se agrega este documento en `docs/`.)*

## 11. Dependencias nuevas

**En el repositorio: NINGUNA.** El bot solo necesita `openpyxl`, que ya es
dependencia del ecosistema de tools del repo (los otros convertidores también
lo usan) y no se agregó a `requirements.txt` (los tools se instalan aparte:
`py -m pip install openpyxl`).

En los entornos de trabajo de la sesión (no del repo): `openpyxl` 3.1.5,
`et-xmlfile` 2.0.0, `pytest` 9.1.1, `ruff` 0.11.8. En el PC de la usuaria ya
estaba `openpyxl` 3.1.5 instalado.

## 12. Configuración

### 12.1 Variables de entorno / tokens
**Ninguna.** El bot no usa credenciales ni configuración externa (a diferencia
del bot COOSALUD, que usa `COOSALUD_USER`/`COOSALUD_PASSWORD`).

### 12.2 Parámetros del CLI (configuración por corrida)

| Flag | Default | Uso |
|---|---|---|
| `--entrada` | (requerido) | Excel de SAVIA (8 columnas). |
| `--salida` | (requerido) | Carpeta destino, o `.xlsx` si `--consolidado`. |
| `--prefijo` | `OBJECIONES_SAVIA` | Prefijo de los archivos por factura. |
| `--consolidado` | off | Un solo Excel con todas las facturas. |
| `--fecha` | hoy | `YYYY-MM-DD` para `CDFECDOC`/`CROFECOBJ`. |
| `--codigo-sufijo` | `01` | Consecutivo con que se completa el código 4→6. |
| `--mapa-codigos` | — | JSON `{"TA08": "TA0805", …}` que fuerza códigos. |
| `--consecutivo` | `1` | Número inicial del consecutivo por factura. |
| `--log` | — | Log adicional a archivo. |

### 12.3 Rutas relevantes
- Bot: `tools/organizar_objeciones_savia.py` · Guía: `tools/README_organizar_objeciones_savia.md`
- Tests: `tests/test_tools/test_organizar_objeciones_savia.py`
- Memoria del proyecto: `BITACORA.md` (raíz) · Regla: `CLAUDE.md` (raíz)

---

## 13. Riesgos y decisiones técnicas (incluye cambios de enfoque y descartes)

1. **Cambio de enfoque #1 — dirección de la conversión (el mayor).** La v1
   convirtió Dispensario→SAVIA porque el pedido inicial era ambiguo ("tomo ese
   excel como punto de apoyo"). La usuaria aclaró: el Excel del Dispensario era
   **solo la guía de columnas**; los datos son de SAVIA y la salida debe tener
   el layout de 16 columnas. Se reescribió el módulo completo (v2) y se
   descartó toda la extracción por texto de la v1 (§3.1). Lección operativa
   registrada: ante ambigüedad de dirección de datos, confirmar antes de
   construir.
2. **Nombre de salida.** La v2 nombraba `OBJECIONES_DISPENSARIO_<factura>` por
   imitar la guía; la usuaria corrigió (los archivos son de SAVIA). Se
   parametrizó con `--prefijo` (default `OBJECIONES_SAVIA`). Se usó
   `AskUserQuestion` para confirmar que era SOLO el nombre (respuesta: "Solo el
   nombre") antes de tocar contenido.
3. **`CRDOBSERV`.** Al comparar con el archivo real de EMSSANAR aportado por la
   usuaria se detectó que el texto real SIEMPRE es `<código> <texto>$<valor>`;
   la salida ponía solo la observación. Regla verificada 37/37 y aplicada con
   protección anti-duplicado.
4. **`CDCONSEC`.** Se asumió constante 1 (así venía la guía de UNA factura);
   la usuaria explicó la convención real: consecutivo POR factura (1-1-1,
   2-2-2…). Decisión adicional: en archivos standalone (una factura por
   archivo) se reinicia a 1; en el consolidado se numera por orden de
   aparición.
5. **Tipos de celda.** Comparación celda a celda contra EMSSANAR reveló que
   `CDCONSEC` y `GENUSUARIO4` van como TEXTO y los valores como número; se
   igualaron para evitar rechazos del sistema receptor por tipo.
6. **`CROTIPOBJ`.** Se asumió constante 0 (lo que traían los archivos de
   referencia). La usuaria definió la regla real 0/1/2 por mezcla de conceptos.
   **Discrepancia documentada**: los archivos reales de referencia (guía y
   EMSSANAR) traen 0 constante incluso en facturas mezcladas; prevalece la
   regla de trabajo dictada por la usuaria. Si el sistema receptor rechazara un
   2, revisar esta decisión con ella.
7. **Calidad de código.** B023 de ruff (cierre sobre variable de bucle) se
   resolvió extrayendo `_cell` a nivel de módulo. `ruff format` reordenó
   literales. En el arreglo de CI, `ruff --fix` aplicó UP017 (`datetime.UTC`).
8. **Riesgo latente en el CI (fuera del módulo)**: `test_desempeno_trimestral.py`,
   `test_picos_historicos.py` y `test_stats_por_anio.py` también siembran
   fechas fijas (abril 2026). Hoy pasan (sus endpoints no usan la ventana de
   90 días o la superan), pero son candidatos a "bombas" futuras (p. ej. al
   cambiar de año). Vigilarlos; si estallan, replicar el patrón
   `_dia_semana_reciente`/fechas relativas.
9. **Supuestos del formato que podrían romper la integración**: ancho de 10
   dígitos en `factura_larga`; sufijo `01` en códigos (§15.1); prefijos no-CL
   tratados como administrativos; el `mm-dd-yy` es formato builtin de Excel
   (se RENDERIZA según la configuración regional del equipo que abra el
   archivo — no es un texto fijo `dd/mm/yyyy`).
10. **Conflictos de merge esperables**: prácticamente nulos para los archivos
    nuevos. Los 3 tests de `tests/test_api/` modificados podrían chocar si otra
    rama los tocó; resolver conservando las fechas relativas (nunca volver a
    fechas fijas). El PR #164 mezcla el módulo con 2 arreglos de higiene de CI
    (newline y time-bombs) y la bitácora — fue deliberado para mantener el CI
    verde, pero el equipo principal debe saber que van juntos.

## 14. Dependencias con otros módulos

- **No depende de ningún módulo del repo** (import-level): no importa nada de
  `app/` ni de otros tools. La función `factura_larga` replica la convención
  de `radicar_facturacion.factura_corta` (inversa) por diseño, sin importarla,
  para mantener el tool autocontenido y ejecutable con un solo archivo en el
  PC de la usuaria.
- **Módulos que lo usan**: ninguno todavía (es la punta del flujo de SAVIA).
  Análogos en el repo: `convertir_tramite_masivo.py` (CRRP→SIMED) alimenta a
  `responder_glosas_simed.py`; si a futuro existe un portal/carga masiva de
  SAVIA, este bot sería su alimentador natural.
- **Convenciones compartidas** con el resto del repo: estilo de encabezado
  Excel (azul 1F4E78), normalización de encabezados, patrón de tests
  (`sys.path.insert` hacia `tools/`), ruff (line-length 100), español.

## 15. Pendientes (estado exacto al cierre)

1. **`CRNCONOBJ` — CONFIRMACIÓN DE LA USUARIA (el único pendiente funcional
   del módulo).** Hoy se completa `TA08→TA0801` con sufijo `01`. En EMSSANAR
   los subíndices reales VARÍAN (`FA0205`, `FA0502`, `FA0603`, `FA5802`,
   `SO0601`, `SO0603`, `TA0701`). Mapeo actual de los datos de SAVIA:
   TA08→TA0801, TA02→TA0201, TA01→TA0101, TA58→TA5801, FA01→FA0101,
   FA58→FA5801, CL07→CL0701, CL08→CL0801, SO61→SO6101. Si la usuaria entrega
   la tabla oficial, fijarla vía `--mapa-codigos` o cambiando
   `CODIGO_SUFIJO_DEFAULT`/un dict interno.
2. **Merge del PR #164** a `motor-glosas` (draft, CI verde al cierre).
3. **Instalación local en el PC de cartera**: no se concretó — la descarga del
   `.py` no llegó a las carpetas del usuario (búsqueda en
   Downloads/Desktop/Documents/OneDrive sin resultados) y hubo fricción con
   PowerShell (los bloques `if/elseif/else` multi-línea pegados por partes
   fallan; los comentarios `::` de CMD no valen en PS). Mientras tanto el
   flujo operativo es: subir el Excel al chat → recibir los .xlsx convertidos.
4. **Del contexto general (BITACORA)**: seguimiento a las 12 notas crédito del
   Lote V2 (informe a gerencia ya entregado en commits previos a esta sesión).
5. **Mejora prevista no implementada**: ninguna otra quedó comprometida. Ideas
   mencionadas pero no pedidas: subtotales/separador por factura en el
   consolidado (ofrecido, la usuaria no lo pidió).

## 16. Recomendaciones para fusionarlo (paso a paso)

1. **Antes del merge**: obtener de la usuaria la tabla de códigos `CRNCONOBJ`
   (§15.1). Si existe, agregarla como JSON versionado (p. ej.
   `data/mapa_codigos_savia.json`) y documentar su uso con `--mapa-codigos`, o
   incorporarla como dict default en el tool.
2. Revisar el PR #164 sabiendo que contiene 4 bloques: (a) el módulo SAVIA
   completo, (b) fix de newline en `test_import_history.py`, (c) fix de
   time-bombs en 2 tests de stats, (d) `BITACORA.md` + `CLAUDE.md` + este
   documento. Son separables por commit si el equipo prefiere cherry-pick.
3. **Merge normal a `motor-glosas`** (el CI ya valida lint+tests+security). No
   hay migraciones, ni variables de entorno, ni pasos de deploy: el módulo no
   corre en el servidor, corre en el PC del equipo de cartera (o en el chat).
4. Post-merge: verificar que `pytest tests/test_tools/test_organizar_objeciones_savia.py`
   (36 tests) y `pytest tests/test_api/test_heatmap_actividad.py tests/test_api/test_por_dia_semana.py`
   pasen en la rama principal.
5. **Al consolidar con el "proyecto principal" multi-repositorio**: llevar
   SIEMPRE juntos los 3 archivos del módulo (tool + README + tests) y este
   documento; conservar la `BITACORA.md` como memoria (o fusionar su contenido
   en la bitácora del proyecto principal, manteniendo las entradas por fecha).
6. Si el proyecto principal ya tiene otro conversor de SAVIA: comparar contra
   las 7 reglas de la tabla del §17 antes de elegir uno — estas reglas están
   verificadas contra archivos reales y contra la operación del equipo.
7. No renombrar los archivos de salida sin consultar: el nombre
   `OBJECIONES_SAVIA_<factura>.xlsx` fue decisión explícita de la usuaria.

## 17. Resumen ejecutivo (para quien lo mantenga)

**Qué es**: un conversor determinista de un solo archivo
(`tools/organizar_objeciones_savia.py`, solo requiere `openpyxl`) que
transforma la relación de objeciones de SAVIA SALUD (8 columnas) al formato de
trabajo de 16 columnas (hoja `OBJECIONES`), un .xlsx por factura o consolidado.

**Las 7 reglas de oro del formato** (todas salieron de correcciones de la
usuaria y/o de verificación contra archivos reales — no cambiarlas sin ella):

| # | Regla |
|---|---|
| 1 | `CRNCXC` en formato largo: `HUS443697` → `HUS0000443697` (10 dígitos). |
| 2 | `CDCONSEC` = consecutivo POR FACTURA (1-1-1…, 2-2-2…), como TEXTO; standalone reinicia en 1. |
| 3 | `CRNCONOBJ` = código SAVIA + sufijo `01` (⚠️ pendiente tabla oficial). |
| 4 | `CRDOBSERV` = `<código> <texto>$<valor>`, sin duplicar si ya vienen. |
| 5 | `CROTIPOBJ` por factura: solo TA/FA/SO/AU=0, solo CL=1, mezcla=2 (todas las filas iguales). |
| 6 | Fechas (`CDFECDOC`/`CROFECOBJ`) en FECHA CORTA (`mm-dd-yy`), sin horas. |
| 7 | Tipos y number_format de las 16 columnas copiados 1:1 del archivo real (texto `@` casi todo; `GENUSUARIO4='999'`; contable en `CROVALOBJ`). |

**Cómo saber que sigue sano**: `ruff check` + `ruff format --check` limpios y
los **36 tests** de `tests/test_tools/test_organizar_objeciones_savia.py` en
verde (cubren cada regla, los formatos de celda y el CLI end-to-end con Excel
sintéticos del layout real).

**Dónde está el conocimiento**: este documento (visión completa), el README del
tool (uso operativo), la `BITACORA.md` (historia del proyecto y pendientes) y
los mensajes de commit de la rama (cada regla tiene su commit con el porqué).

**El único cabo suelto**: la tabla oficial de códigos `CRNCONOBJ` de SAVIA
(§15.1). Todo lo demás está verificado contra archivos reales y en producción
operativa vía el flujo "subir Excel → recibir convertidos".

---

*Documento generado como entrega oficial del módulo — rama
`claude/savia-salud-objections-bot-fni6dq`, PR #164. Julio de 2026.*
