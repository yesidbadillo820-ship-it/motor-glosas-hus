# Documentación oficial del módulo — Diagnóstico y destrabe de notas crédito del Lote V2 (Dispensario DMBUG)

**Repositorio:** `motor-glosas-hus` · **Rama:** `claude/excel-reconciliation-data-9Bnpj` · **Carpeta:** `docs/diagnostico_lote_v2_pendientes/`
**Período de desarrollo:** 25-jun-2026 a 22-jul-2026 (una sola conversación de Claude Code, en 6 jornadas de trabajo)
**Commits del módulo:** `a316542`(→`a852dee`), `aec074c`, `d3afa14`, `fcaab7c`, `6ef2eb6`, `128b9eb`, `94fef18`, `4579f34`, `937f318`
**Documento de entrega para consolidación en el proyecto principal. Todo lo aquí descrito ocurrió en esta conversación; nada es inventado.**

---

## 1. Objetivo del desarrollo

**Problema:** al cierre del lote `LOTE_DISPENSARIO_2026-06_V2` quedaron **12 facturas del Dispensario Médico Bucaramanga (DMBUG)** con nota crédito (NC) pendiente de radicar en el portal SIMED (`auditool25.tool.com.co`), sin claridad de por qué. El registro que se llevaba (sección 7 de `docs/CONTEXTO_DISPENSARIO_NOTAS.md`) decía que 5 estaban "✅ Subidas", 1 necesitaba "re-correr el cargue" y el resto tenía motivos varios — pero las 12 volvían a aparecer pendientes.

**Necesidad cubierta:** el auditor pidió literalmente *"armame una carpeta con la información que se tenga de estas facturas para saber por qué no se subieron"*. El módulo respondió tres necesidades encadenadas que fueron apareciendo:

1. **Diagnóstico**: saber el estado REAL de cada factura (archivos en disco + validez del CUV de MinSalud), no el estado registrado.
2. **Organización**: carpetas de trabajo con los soportes y una ficha por factura.
3. **Escalamiento**: informes con evidencia técnica exacta (para SISTEMAS y para gerencia) que destraben las facturas.

**Las 12 facturas:** HUS0000404136, HUS0000411234, HUS0000410675, HUS0000413266, HUS0000417459, HUS0000420099, HUS0000421733, HUS0000418576, HUS0000420160, HUS0000422238, HUS0000435485, HUS0000440328. Valores (11 de 12 con dato en el histórico): **$108.570.548 facturado, $23.891.565 en glosas, $8.712.457 aceptado en conciliación** (= valor de las NC a radicar).

**Hallazgo central que justificó el módulo:** el registro estaba equivocado en 6 de 12. Los archivos `CUV_*.json` de 6 facturas no eran CUVs sino **el texto del error de conexión** al servicio interno `dockerrips.hus.gov.co:9443` (caído cuando se generaron las notas): la validación ante MinSalud **nunca se ejecutó**, el sistema guardó el error como si fuera el resultado, `consolidar_carpetas_notas.py` lo renombró a `CUV_*.json` sin detectar que era basura, el bot subió eso al portal y el portal dejó las NC en limbo. Otras 3 tenían el CUV **rechazado por MinSalud con código RVC086** ("Código de diagnóstico repetido"). Conclusión operativa: **9 de 12 facturas (75%) no eran destrabables desde Cartera** — dependían de SISTEMAS.

---

## 2. Arquitectura

### 2.1 Estructura del módulo (todo bajo `docs/diagnostico_lote_v2_pendientes/`)

| Archivo | Tipo | Rol |
|---|---|---|
| `README.md` | doc | Resumen ejecutivo del diagnóstico, cuadro por causa raíz, cómo usar los scripts, explicación del hallazgo dockerrips |
| `estado_facturas.md` | doc | Ficha detallada de cada una de las 12 facturas (NE V2 + NE histórico + radicado + acta + valores + causa + acción), agrupamiento por causa, orden de ataque |
| `resumen.csv` | dato | La misma información en tabla: columnas `Factura, HUS_corto, NE_historico_TSV, NE_V2_vigente, Radicado, Acta, Valor_Factura, Total_Glosas, Valor_Aceptado, Estado_real_en_disco, Causa_raiz, Quien_resuelve, Accion` |
| `correo_sistemas.md` | doc | Plantilla de correo de escalamiento a SISTEMAS: Grupo A (6 NEs dockerrips) + Grupo B (3 NEs RVC086), con el texto del error y el procedimiento de verificación de cierre |
| `diagnosticar_local.ps1` | script | Diagnóstico local: verifica triada NC/XML/CUV por carpeta, parsea el CUV, clasifica estado. Genera `reporte_diagnostico.csv` |
| `armar_carpetas_pendientes.ps1` | script | Arma `PENDIENTES_12\` en el disco D: del auditor: 12 subcarpetas con prefijo de causa + `_ESTADO.txt` + `_INDICE_PENDIENTES.csv` |
| `extraer_rechazos_cuv.ps1` | script | Extrae el detalle COMPLETO (sin truncar) del rechazo del CUV de las 4 facturas conciliadas, leyendo el JSON vigente del share. Genera `INFORME_RECHAZOS_CUV.md` + `rechazos_cuv.csv` |
| `INFORME_GERENCIA.md` | doc | Informe de gestión para gerencia (efectividad del trabajo vs. proceso manual) |
| `INFORME_RECHAZOS_CUV.docx` | doc | Versión Word del informe técnico para SISTEMAS (binario commiteado) |

**Archivos generados localmente y NO commiteados (por diseño):** `reporte_diagnostico.csv` (salida de diagnosticar), `INFORME_RECHAZOS_CUV.md` y `rechazos_cuv.csv` (salidas de extraer — el usuario los tiene en su working tree local).

**En la raíz del repo (parte de esta entrega):** `BITACORA.md` (memoria común de todos los chats, fusionada con la versión de un chat paralelo) y `CLAUDE.md` (protocolo: leer bitácora al iniciar, actualizarla al cerrar, más reglas fijas del repo).

**En el PC del auditor (D:, fuera del repo):** `D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\PENDIENTES_12\` con las 12 carpetas armadas (verificado por el usuario en su corrida: 9 con los 3 archivos, 3 solo con `_ESTADO.txt`).

### 2.2 Dependencias y librerías

- **PowerShell 5.1 (Windows PowerShell)** — los 3 scripts usan SOLO stdlib de PS (`Get-ChildItem`, `ConvertFrom-Json`, `Export-Csv`, `System.Text.StringBuilder`). **Cero dependencias instalables**: decisión deliberada porque corren en el PC del hospital.
- **`docx` (npm)** — usada UNA vez, en el sandbox de Claude (no en el PC del usuario), por el generador `gen_informe_docx.js` que produjo el `.docx`. Instalada con `npm install docx` sin fijar versión (la última disponible al 22-jul-2026). El generador vive en el scratchpad de la sesión, NO en el repo — si se quiere regenerar el Word, el `.md` generado por `extraer_rechazos_cuv.ps1` es la fuente.
- **Herramientas del repo de las que depende el flujo** (preexistentes, no tocadas): `tools/verificar_cuv_notas.py`, `tools/cargar_soportes_simed.py`, `tools/consolidar_carpetas_notas.py`, `tools/extraer_notas_credito.py`, `tools/renombrar_y_organizar_notas.py`.

### 2.3 Fuentes de datos (no hay base de datos)

1. **`docs/CONTEXTO_DISPENSARIO_NOTAS.md` §7** — estado del lote V2 según el chat anterior (NE V2 311xxx por factura). Resultó parcialmente FALSO y fue corregido por este módulo.
2. **`tools/notas_credito_ejemplo.tsv`** — histórico de conciliación: Radicado, Acta, Prefijo, # Factura, NOTA CREDITO (NE histórico), Valor Factura, Total Glosas, Valor Aceptado. De aquí salieron radicados/actas/valores de 11 de las 12 (HUS422238 no figura).
3. **Share UNC `\\172.16.32.83\factura_electronica_net22\<AAAAMM>\FACTURAS_NOTA\<NE>\`** — fuente oficial: `ad*.xml` (XML de la NC) y `RIPS\ResultadosDoker_*.json` (resultado de validación MinSalud, el nombre lleva timestamp; el más reciente es el vigente).
4. **Disco local del auditor** — `LOTE_DISPENSARIO_2026-06_V2\NOTAS\<NE>\` (triada renombrada `NC_/XML_/CUV_`), lotes anteriores `NOTAS_DISP_9\NOTAS\311147` y `NOTAS_DISP_10\NOTAS\311131`, y `_papelera` (residuos de consolidación, se ignoran).

**Dato clave del modelo de datos descubierto en la sesión:** cada factura tiene DOS números de NC: el **NE histórico** del TSV (263xxx/243xxx/234xxx/264xxx/302xxx, emitidos en actas AC000456/AC000619) y el **NE V2 vigente** (311xxx, re-emisiones de junio 2026). No se deben mezclar: el SIMED espera el V2. Excepción: HUS440328 no tiene NE V2 asignado (el TSV trae 302111 — discrepancia a resolver con Facturación).

### 2.4 Estructura del JSON del CUV (`ResultadosDoker_*.json`) — conocimiento crítico

```
ResultState            → booleano NATIVO (true = CUV aprobado, false = rechazado)
CodigoUnicoValidacion  → el CUV cuando aprobado (cuando hay rechazo es un mensaje, no un hash útil)
FechaRadicacion        → timestamp de la validación (se recorta a 19 chars)
ResultadosValidacion[] → lista de hallazgos:
    .Clase          → "RECHAZADO" (bloqueante) o "NOTIFICACION" (informativa)
    .Codigo         → RVC086, RVC063, TOT003, ...
    .Observaciones  → texto del hallazgo
    .PathFuente     → ubicación exacta del error dentro del RIPS
```

**Modo de falla documentado:** cuando `dockerrips.hus.gov.co:9443` está caído, el archivo NO es JSON — es texto plano que empieza con `"Se ha generado un error en el consumo"` seguido del stack trace .NET (`DG.Entidades.Generales.GEENRips.ObtenerTokenRips()`). Dos variantes vistas: `"actively refused it"` (servicio caído — NE 311147) y `"A connection attempt failed"` (timeout — NEs 311188, 311190, 311194, 311197, 311199).

---

## 3. Funciones implementadas (lista completa)

### `diagnosticar_local.ps1`

| Función | Qué hace |
|---|---|
| `New-InfoCarpeta` | Devuelve el esqueleto `[ordered]@{}` del resultado de inspección (13 campos: Existe, TienePDF/XML/CUV, Nombres, CUV_State, CUV_CodigoError, CUV_Observacion, CUV_NumRechazos, CUV_FechaValidacion, Archivos). Existe para que la función de inspección y el fallback de facturas sin NE usen EXACTAMENTE la misma forma — antes divergían y el CSV salía con columnas vacías. |
| `Inspeccionar-Carpeta $path` | Corazón del diagnóstico. Si el path no existe → `Existe=false`. Lista archivos y por cada uno clasifica: `^NC_.*\.pdf$`, `^XML_.*\.xml$`, `^CUV_.*\.json$`. Para el CUV: (1) si el contenido matchea los patrones de error dockerrips → `CUV_State="INVALIDO_RIPS_DOWN"`, código `DOCKERRIPS_DOWN`, observación según variante (refused/timeout) y **`continue`** (ver bug corregido en §15); (2) si no, `ConvertFrom-Json`: normaliza `ResultState` bool→"True"/"False", extrae `FechaRadicacion`, filtra `ResultadosValidacion` por `Clase -eq "RECHAZADO"`, toma código y observación del primero (truncada a 200 chars para el CSV); (3) si el parseo revienta → `JSON_ILEGIBLE` con los primeros 200 chars. |
| Cuerpo principal | Itera el array `$facturas` (las 12, hardcodeadas con Factura/HUS/NE_V2/NE_TSV/OrigenAlt/Motivo), inspecciona la carpeta V2 y el origen alterno (DISP_9/DISP_10 para 311147/311131), calcula `Estado_real` (ver §4), imprime con colores (verde OK / rojo rechazado / magenta dockerrips / amarillo faltantes), y exporta `reporte_diagnostico.csv` + resumen agrupado por estado. |

**Estados posibles calculados:** `COMPLETA_CUV_OK`, `COMPLETA_CUV_RECHAZADO_<código>` (o `_SIN_CODIGO`), `COMPLETA_CUV_INVALIDO_DOCKERRIPS`, `COMPLETA_CUV_JSON_ILEGIBLE`, `COMPLETA_CUV_DESCONOCIDO`, `FALTAN_<PDF+XML+CUV>`, `CARPETA_NO_EXISTE_EN_V2`, `SIN_NE_V2`.

### `armar_carpetas_pendientes.ps1`

| Función | Qué hace |
|---|---|
| `Copiar-Archivos-NC $origen $destino [-SoloFaltantes]` | Copia `NC_*.pdf`, `XML_*.xml`, `CUV_*.json` del origen al destino. Con `-SoloFaltantes` NO pisa archivos ya existentes (se usa para el origen alterno: **el V2 es la fuente vigente y gana siempre**; el lote anterior solo rellena huecos). Devuelve la lista de nombres realmente copiados. |
| `Generar-EstadoTxt $f $carpeta $archivos $origenes` | Escribe `_ESTADO.txt` con StringBuilder: factura, HUS corto, NE V2, NE TSV, radicado, acta, los 3 valores, causa, detalle, qué falta, próxima acción, archivos presentes y origen de cada copia. Si no hay archivos lo dice explícitamente. |
| Cuerpo principal | Crea `PENDIENTES_12\`, y por factura una subcarpeta `<CAUSA>_HUS<n>_NE<ne>` (`RVC086_`, `DOCKERRIPS_`, `SIN_PDF_`, `SIN_NE_` — el prefijo hace que un simple `dir` agrupe visualmente por causa). Copia V2 primero, luego origen alterno con `-SoloFaltantes`, genera la ficha, imprime con color por causa y exporta `_INDICE_PENDIENTES.csv`. **Idempotente**: re-correrlo sobreescribe fichas y no duplica. **No toca `V2\NOTAS\`** (solo lee). |

### `extraer_rechazos_cuv.ps1`

| Función | Qué hace |
|---|---|
| `Buscar-JsonCuv $f` | Localiza el JSON de validación VIGENTE: busca `ResultadosDoker_*.json` en `share\<periodo>\FACTURAS_NOTA\<NE>\RIPS\` y luego en la raíz de la carpeta NE, ordena por nombre DESCENDENTE (el nombre lleva timestamp → el primero es el más reciente) y toma ese. Fallback: `CUV_*.json` local del V2. Devuelve `@{Path; Origen="share"|"local (V2)"}` o `$null`. Leer del share y no de la copia local fue una decisión explícita: capturar el estado vigente por si SISTEMAS regeneró algo. |
| `Analizar-Cuv $rutaJson` | Clasifica: `SIN_ARCHIVO` / `ERROR_SERVICIO_INTERNO` (patrones dockerrips, texto a 600 chars) / `JSON_ILEGIBLE` / `CUV`. Para CUV: ResultState → "true (APROBADO)"/"false (RECHAZADO)", CUV, fecha, **TODOS los rechazos SIN truncar** (a diferencia de diagnosticar) y conteo de notificaciones. |
| Cuerpo principal | Para las 4 facturas conciliadas (hardcodeadas con radicado/acta/valores/periodo 202606) arma: bloque Markdown por factura (tabla de ficha + rechazos numerados con código/observación/PathFuente, o el bloque de error de servicio), y genera `INFORME_RECHAZOS_CUV.md` completo (secciones: Resumen / Antecedente objeción→error / Facturas afectadas / Detalle / Solicitud al área / Verificación de cierre) + `rechazos_cuv.csv` (una fila por rechazo). Si una nota aparece con `ResultState:true` la marca "CUV APROBADO (ya destrabada)" — detección automática de destrabe. |

### `gen_informe_docx.js` (generador del Word, scratchpad)

Funciones auxiliares: `t()` (TextRun), `p()` (Paragraph), `h()` (heading), `celda()`, `tablaFicha()` (tabla Campo/Valor con sombreado), `mono()` (Consolas), `bloqueCodigo()` (párrafo sombreado con borde). Produce el `.docx` tamaño carta con: título institucional, tabla de facturas con encabezado azul, ficha por factura, estado en color (rojo `C00000` rechazado / morado `7030A0` dockerrips), rechazos con código en rojo, bloque monoespaciado con el error textual, lista numerada de solicitudes (numbering config `LevelFormat.DECIMAL` — nunca viñetas literales), pie de página "Página X de Y", y **tildes restauradas** (el `.md` va sin acentos por limitación de PS 5.1; el Word no tiene esa restricción).

---

## 4. Flujo completo (paso a paso)

### Flujo operativo del módulo (el ciclo humano-script)

El patrón de TODA la conversación: **Claude no tiene acceso al disco D:, al share ni a los portales** (regla del repo). Cada paso es: Claude escribe/pushea el script → el auditor hace `git pull` en `C:\temp-notas` → corre el comando entregado → pega la salida de consola → Claude la interpreta y decide el siguiente paso.

### Paso a paso ejecutado en la sesión

1. **Cruce documental** (25-jun): contexto §7 + TSV histórico + `tools/lotes/lote_29_dispensario_2026-06.txt` → primera versión de `estado_facturas.md`/`resumen.csv` con el estado SEGÚN REGISTRO.
2. **Primera corrida de `diagnosticar_local.ps1`** → reveló que el registro no cuadraba: 3 `RECHAZADO_` (sin código, por bug v1) y 6 `DESCONOCIDO`.
3. **Fix del parseo** (commit `aec074c`): alinear con `verificar_cuv_notas.py` — `ResultState` es bool nativo (la comparación `-eq "True"` de v1 fallaba siempre) y el código vive en `ResultadosValidacion[].Codigo` con `Clase="RECHAZADO"` (v1 buscaba `ResultErrors[0].Code`, campo que NO existe).
4. **Segunda corrida** → `RVC086` visible en 3 (404136, 410675, 435485) pero 6 seguían `DESCONOCIDO`.
5. **Inspección manual de un JSON** (comando ad-hoc sobre NE 311147) → el archivo es TEXTO del error dockerrips, no JSON. Verificación en las otras 5 → mismo error (1 refused, 5 timeout). **Hallazgo que reescribió todo el diagnóstico.**
6. **Reescritura completa** (commit `d3afa14`): estado_facturas/resumen/README con causa raíz real + detección automática de dockerrips en el script + `correo_sistemas.md`.
7. **Armado de carpetas** (commit `fcaab7c`; decisión del usuario vía pregunta estructurada: carpeta nueva `PENDIENTES_12` al lado del V2 — sin tocar el lote — y contenido = archivos + `_ESTADO.txt`). Corrida del usuario: 12/12 carpetas OK.
8. **Revisión de código en frío** (2-jul, commit `6ef2eb6`): 2 bugs reales corregidos ANTES de que produjeran daño (ver §15).
9. **Localización de rutas** (10-jul): localizador share+local entregado; resultados: las 4 del lote en periodo `202606`; las 4 NC viejas de conciliación (309363→HUS466929 en 202605, 309385→HUS468094 en 202605, 310199→HUS471130 en 202605, 303565→HUS476124 en 202603) **solo existen en el share, sin carpeta local**. Se entregó snippet de descarga (renombra `ad*.xml`→`XML_` y `ResultadosDoker`→`CUV_`; el PDF CRRP no vive en el share, sale del DIAN). Hallazgo colateral: copia de 311136 en `LOTE_RECARGUE_20_2026-06` — evidencia de un reintento posterior por otra sesión.
10. **Informe de gerencia** (10-jul, commit `128b9eb`).
11. **Extracción de rechazos + informes** (17-jul, commits `94fef18` y `4579f34`): corrida real del usuario con datos vigentes del share:
    - 311131: RVC086, validado 2026-06-19 21:06:49, 5 notificaciones.
    - 311136: RVC086, validado 2026-06-25 16:52:11, 4 notificaciones.
    - 311222: RVC086, validado 2026-06-25 16:58:35, 4 notificaciones.
    - 311188: error dockerrips (timeout), archivo del 22-jun. Sin validación de MinSalud.
    - PathFuente idéntico en las 3: `usuarios[0].servicios.procedimiento[0].codDiagnosticoRelacionado`.
    - **Inferencia clave:** las fechas 25-jun demuestran que SISTEMAS ya reintentó DESPUÉS del diagnóstico y volvió a fallar → el reintento sin corregir el RIPS no sirve; deben cambiar el diagnóstico relacionado.
12. **Word final** con el argumento pedido por el auditor: *"al radicar las facturas ese error salía como objeciones, y esa objeción se convirtió en error cuando se generó la nota crédito"* — formalizado como sección 2 del informe ("de objeción a error bloqueante": en la radicación de la factura la inconsistencia del RIPS era una objeción subsanable; al validar el RIPS de la NC ante MinSalud/SISPRO se vuelve bloqueante, `ResultState:false`, sin CUV el SIMED no acepta la NC).
13. **Bitácora y protocolo** (22-jul, commit `937f318`): reconstrucción de ~1.600 commits del repo (8-abr→17-jul) por fecha y tema; al pushear se descubrió que **un chat paralelo había creado BITACORA.md/CLAUDE.md el mismo día** → resolución por FUSIÓN (base: la versión del otro chat, más al día en COOSALUD; aportes de esta sesión: historia abril-mayo, pendientes detallados del Dispensario, reglas extra de CLAUDE.md), rebase con conflicto resuelto a mano y mensaje enmendado.

---

## 5. Base de datos

**No hay base de datos en este módulo.** Persistencia usada:

- **CSV**: `resumen.csv` (commiteado, 12 filas), `reporte_diagnostico.csv` (generado local, 18 columnas), `rechazos_cuv.csv` (generado local, columnas: Factura, NE, Radicado, Acta, Estado, Codigo, Observacion, PathFuente, FechaValidacion, ArchivoAnalizado), `_INDICE_PENDIENTES.csv` (en D:, columnas: Carpeta, Factura, NE_V2, Causa, ArchivosCopiados, Origenes). Todos `Export-Csv -Encoding UTF8`.
- **TXT**: `_ESTADO.txt` por carpeta de factura.
- **Markdown/Word**: los informes.
- Sin tablas, sin migraciones, sin índices. (La aplicación web del repo tiene su propia BD — alembic existe en el repo — pero NO fue tocada en esta conversación.)

## 6. Backend

**No aplica: no se crearon endpoints, servicios web, controladores, middleware ni permisos.** El módulo es 100% scripts de línea de comandos + documentos. Validaciones y manejo de errores viven dentro de los scripts (§3): `Test-Path` antes de leer, `try/catch` en lecturas y parseos, `-ErrorAction SilentlyContinue` en listados, estados explícitos para cada modo de falla (JSON ilegible, archivo ausente, share caído → cae a copia local).

## 7. Frontend

**No aplica: no hay pantallas, componentes ni formularios.** La "interfaz" es la consola PowerShell (salida con colores semánticos: verde=OK, rojo=rechazado, magenta=inválido, amarillo=faltante, gris=informativo) y los documentos entregables. El único elemento interactivo de la sesión fue una **pregunta estructurada al usuario** (herramienta AskUserQuestion) para decidir destino y contenido de las carpetas (eligió: `PENDIENTES_12` nuevo + archivos con `_ESTADO.txt`).

## 8. IA

**El módulo en sí NO invoca ningún modelo de IA** — los 3 scripts son deterministas. La IA de esta conversación fue Claude Code como herramienta de desarrollo (con cambio a modelo Fable a mitad de sesión, a pedido del usuario, para la revisión de código). No hay prompts, temperaturas, proveedores ni fallbacks que documentar en el módulo. (El "motor de glosas" de la carpeta `app/` sí usa IA, pero no fue desarrollado en esta conversación — solo aparece en la reconstrucción histórica de la bitácora.)

## 9. Automatizaciones

Nada corre solo (sin cron, sin scheduler): las 3 automatizaciones son **bajo demanda**, ejecutadas por el auditor:

1. `diagnosticar_local.ps1` — reemplaza la revisión manual carpeta-por-carpeta + apertura de JSONs (estimado en la sesión: 20-30 min/factura manual → segundos el lote).
2. `armar_carpetas_pendientes.ps1` — reemplaza el armado manual de carpetas de trabajo.
3. `extraer_rechazos_cuv.ps1` — reemplaza abrir cada JSON del share y transcribir el error a un informe; genera el informe completo listo para enviar.

Cuándo re-ejecutarlas: cada vez que SISTEMAS anuncie una corrección (diagnosticar y extraer detectan automáticamente el destrabe: `COMPLETA_CUV_OK` / "CUV APROBADO (ya destrabada)").

## 10. Archivos creados/modificados (lista completa por commit)

| Commit | Archivo | Qué cambió exactamente |
|---|---|---|
| `a316542`→`a852dee` (25-jun) | `README.md`, `estado_facturas.md`, `resumen.csv`, `diagnosticar_local.ps1` (nuevos) | Versión inicial basada en el registro documental. El push inicial rebotó (remoto adelantado) → `pull --rebase` → push |
| `aec074c` (25-jun) | `diagnosticar_local.ps1` | Fix parseo CUV: bool nativo, `ResultadosValidacion[Clase=RECHAZADO].Codigo`, +columnas NumRechazos/FechaValidacion/Observacion, print del rechazo en consola |
| `d3afa14` (25-jun) | `estado_facturas.md` (reescrito), `resumen.csv` (reescrito), `README.md` (reescrito), `diagnosticar_local.ps1`, `correo_sistemas.md` (nuevo) | Hallazgo dockerrips: causa raíz real por factura, detección automática del error texto-plano, nuevo estado `COMPLETA_CUV_INVALIDO_DOCKERRIPS` |
| `fcaab7c` (25-jun) | `armar_carpetas_pendientes.ps1` (nuevo) | Armador de PENDIENTES_12 completo |
| `6ef2eb6` (2-jul) | `diagnosticar_local.ps1`, `armar_carpetas_pendientes.ps1` | Los 2 bugs de la revisión (return prematuro → continue; -Force → -SoloFaltantes) + New-InfoCarpeta + RECHAZADO_SIN_CODIGO + limpieza (ver §15) |
| `128b9eb` (10-jul) | `INFORME_GERENCIA.md` (nuevo) | Informe de gestión con cifras y comparativo |
| `94fef18` (17-jul) | `extraer_rechazos_cuv.ps1` (nuevo) | Extractor + generador de informe |
| `4579f34` (17-jul) | `INFORME_RECHAZOS_CUV.docx` (nuevo, binario) | Word generado con datos reales de la corrida del usuario |
| `937f318` (22-jul) | `BITACORA.md`, `CLAUDE.md` (raíz) | Fusión con la versión del chat paralelo (rebase con conflicto resuelto manualmente; mensaje enmendado post-rebase) |

## 11. Dependencias nuevas

- **En el repo / PC del usuario: NINGUNA.** (Decisión de diseño: PS 5.1 stdlib.)
- **En el sandbox de Claude, efímera:** `docx` (npm, sin versión fijada) para generar el Word. No requerida para operar el módulo.

## 12. Configuración

- **Variables de entorno** (preexistentes del flujo, NO creadas aquí, NUNCA commiteadas): `SIMED_USER`/`SIMED_PASSWORD` (portal SIMED). En la sesión se observaron también `FOMAG_USER`/`FOMAG_PASSWORD` (flujo FOMAG del usuario, ajeno al módulo).
- **Rutas hardcodeadas al inicio de cada script (editables, documentado en comentarios):**
  - `$baseV2 = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\NOTAS"`
  - `$origenDisp9/10 = "D:\USUARIO CARTERA\Documents\NOTAS_DISP_9|10\NOTAS"`
  - `$share = "\\172.16.32.83\factura_electronica_net22"`
  - Salidas de diagnosticar/extraer: `$PSScriptRoot` (la propia carpeta del módulo).
- **Metadata de las 12 facturas**: hardcodeada como array `$facturas` DENTRO de cada script (ver riesgo en §13).
- **Repo local Windows:** `C:\temp-notas`; rama de trabajo `claude/excel-reconciliation-data-9Bnpj` (regla en CLAUDE.md).

## 13. Riesgos al integrarlo

1. **Triple duplicación de la metadata de facturas**: el array de las 12 vive en `diagnosticar_local.ps1`, `armar_carpetas_pendientes.ps1` (con textos de causa) y `extraer_rechazos_cuv.ps1` (las 4), además de `estado_facturas.md`/`resumen.csv`. Cambiar un NE exige tocar hasta 5 lugares. Mitigación conocida (no implementada, ver §15): un CSV único como fuente y que los 3 scripts lo lean.
2. **Encoding PowerShell 5.1**: los `.ps1` se mantienen **100% ASCII** a propósito (PS 5.1 lee archivos sin BOM como ANSI → mojibake). Si alguien edita y agrega tildes o em-dashes, la salida se corrompe. Regla al editar: sin caracteres no-ASCII, o guardar con BOM.
3. **Backticks en strings de comillas dobles (PS)**: el backtick es carácter de escape; `` `r `` minúscula inyecta un retorno de carro invisible. En `extraer_rechazos_cuv.ps1` los backticks de Markdown van en strings de comilla simple o doblados (`` `` ``). Documentado en el propio commit `94fef18`.
4. **Orden alfabético de `Get-ChildItem`**: `CUV_` < `NC_` < `XML_` — cualquier lógica nueva que corte el loop al procesar el CUV repetirá el bug del return prematuro.
5. **Estado vigente vs. copia local**: la copia `CUV_*.json` del V2 puede estar DESACTUALIZADA respecto al share (caso real: 311136 revalidada el 25-jun; y la copia extra en `LOTE_RECARGUE_20_2026-06`). Todo consumo de CUV debe preferir el share (como hace `extraer_rechazos_cuv.ps1`); tras un destrabe hay que re-extraer del share antes de subir (re-correr `extraer_notas_credito`/`consolidar` o el snippet de descarga).
6. **Conflictos de bitácora entre chats paralelos**: ocurrió en vivo (22-jul). Resolución canónica aplicada y documentada: fusionar tomando la versión más reciente como base, jamás force-push.
7. **`.docx` binario en git**: no diffeable; regenerar desde el `.md` si cambia el contenido.
8. **Rama del sistema vs. rama del repo**: la sesión arrancó apuntada por el sistema a otra rama (`claude/dazzling-cannon-lnifgh`); la regla del repo manda `claude/excel-reconciliation-data-9Bnpj`. Al integrar, verificar SIEMPRE la rama antes de pushear. El PR #134 (draft) ya trackea esta rama; los pushes de la sesión viajaron por él — no se creó PR nuevo.
9. **El repo está muy activo** (3 rebotes de push en la sesión por remoto adelantado): integrar con `pull --rebase` + reintento, nunca con force.

## 14. Dependencias con otros módulos

**Este módulo necesita:**
- `tools/verificar_cuv_notas.py` — es la REFERENCIA del parseo del CUV (el fix `aec074c` se hizo copiando su lógica) y el verificador post-corrección.
- `tools/consolidar_carpetas_notas.py` — produce los `CUV_*.json` locales que diagnosticar lee. **Es también el origen del problema**: renombra `ResultadosDoker_*.json` a `CUV_*.json` sin validar que sea JSON (mejora propuesta en §15).
- `tools/cargar_soportes_simed.py` — el robot que radicará las NC cuando los CUV estén aprobados (`--solo <NE>` por factura, con la regla del repo: piloto antes de masivo).
- `tools/extraer_notas_credito.py` + workaround PowerShell del contexto — para refrescar XML/CUV desde el share.
- `docs/CONTEXTO_DISPENSARIO_NOTAS.md` — contexto del flujo (su §7 quedó SUPERSEDIDO por `estado_facturas.md` de este módulo; no se editó el contexto).
- `tools/notas_credito_ejemplo.tsv` — histórico de conciliación (radicados/actas/valores).

**A este módulo lo usan:** el protocolo BITACORA.md/CLAUDE.md (los pendientes #6-9 de la bitácora apuntan aquí), el informe de gerencia (cita sus archivos como soporte), y cualquier chat futuro que retome el destrabe.

## 15. Pendientes, errores conocidos y decisiones descartadas

### Trabajo operativo pendiente (según la bitácora fusionada, 22-jul)
1. Seguimiento a SISTEMAS por las 9 notas: 3 RVC086 (corregir `codDiagnosticoRelacionado` en el RIPS — el reintento del 25-jun sin corregir volvió a fallar) + 6 dockerrips (reejecutar la validación). Informe Word enviado el 17-jul según la bitácora del chat paralelo; esta sesión lo dejó generado con la nota "falta destinatarios y firma".
2. Descargar del DIAN los PDF CRRP de HUS413266 (radicado 492346) y HUS417459 (radicado 521665) y armar sus carpetas (pipeline completo desde `renombrar --hus-corto`).
3. Facturación: confirmar NE de HUS440328 (¿302111 vigente?) y correspondencia HUS422238↔311199.
4. Verificar si las 10 facturas "COMPLETA" restantes del lote V2 ya quedaron radicadas (HUS409574, 410979, 416671, 428425, 428523, 431722, 432292, 432884, 437357, 437582).
5. Al confirmar SISTEMAS: `verificar_cuv_notas.py` sobre las 9 → si OK, refrescar JSONs del share → `cargar_soportes_simed.py`.

### Bugs encontrados y CORREGIDOS durante el desarrollo (documentados para no repetirlos)
- **v1 del parseo CUV** buscaba `ResultErrors[0].Code` (campo inexistente) y comparaba `ResultState` como string → todo salía `DESCONOCIDO`/`RECHAZADO_` sin código. Corregido en `aec074c`.
- **Return prematuro en el foreach** (introducido en `d3afa14`, corregido en `6ef2eb6` ANTES de que el usuario corriera esa versión — bug latente, ningún reporte generado quedó mal): al detectar dockerrips retornaba sin procesar NC_/XML_ (que ordenan después) → habría reportado `FALTAN_PDF+XML` en vez de `COMPLETA_CUV_INVALIDO_DOCKERRIPS`.
- **Pisado de archivos del V2** por el origen alterno con `-Force` (contradecía su propio comentario "copiar lo que no haya quedado"): inofensivo en la corrida real (fuentes idénticas) pero peligroso tras un destrabe. Corregido con `-SoloFaltantes`.
- **Fallback sin columnas nuevas** para la factura sin NE → columnas `$null` silenciosas en el CSV. Corregido con `New-InfoCarpeta`.
- **`RECHAZADO_` con guion colgando** cuando no hay código parseable → `RECHAZADO_SIN_CODIGO`.

### Limitaciones conocidas NO resueltas
- El `.docx` no pudo verificarse visualmente (LibreOffice del sandbox falla con "source file could not be loaded" incluso con perfil limpio; `pdftoppm`/`pandoc` ausentes). Se verificó por extracción de texto del XML interno (todas las validaciones de contenido OK, las 4 rutas de archivo presentes). Riesgo visual residual bajo.
- La metadata triplicada (§13.1).
- `consolidar_carpetas_notas.py` sigue renombrando errores como CUV — la mejora (validar que el JSON parsee y tenga `ResultState` antes de renombrar) quedó identificada pero NO implementada.
- El síntoma raíz de por qué el bot SIMED reportó "Subida OK" con CUV basura (el portal acepta el upload) está documentado en el contexto pero el bot no valida CUV antes de subir — la regla operativa "validar CUV ANTES de cargar" es el control compensatorio.

### Enfoques descartados (y por qué)
- **Re-correr el bot para HUS435485** (lo que decía el registro): descartado al descubrir que su CUV está rechazado — el problema es el RIPS, no el bot.
- **Verificar el portal SIMED factura por factura** para las 5 "subidas que volvían": descartado al hallar la causa en los archivos (más rápido y con evidencia).
- **Escribir el detalle del rechazo con truncado a 200 chars** en el informe final: descartado; el informe para SISTEMAS exige el texto completo + PathFuente (por eso existe `extraer_rechazos_cuv.ps1` además de `diagnosticar_local.ps1`).
- **Pisar la bitácora del chat paralelo** con force-push: descartado; se fusionó.

## 16. Recomendaciones para fusionarlo al proyecto principal

1. **Llevar la carpeta completa** `docs/diagnostico_lote_v2_pendientes/` tal cual (los 9 archivos commiteados). No renombrar los scripts: la bitácora, el README y los informes se citan entre sí por esos nombres.
2. **Llevar `BITACORA.md` y `CLAUDE.md` de la raíz** — son la memoria transversal; si el proyecto principal ya tiene un CLAUDE.md, fusionar las reglas (las 9 de este repo están listadas en §12/§13 y en el propio archivo) en vez de reemplazar.
3. **Integración git**: la rama `claude/excel-reconciliation-data-9Bnpj` tiene el PR #134 (draft) hacia `motor-glosas`. Los 9 commits del módulo están entrelazados con trabajo de otros frentes en la misma rama — integrar vía el PR existente (no cherry-pick suelto, se perdería la historia de fixes).
4. **Revisar las rutas hardcodeadas** (§12) si cambia el PC/las carpetas del auditor: son las primeras líneas de cada script.
5. **No mover los outputs generados localmente** (`reporte_diagnostico.csv`, `INFORME_RECHAZOS_CUV.md`, `rechazos_cuv.csv`) al repo sin decidirlo: hoy quedan fuera a propósito (datos de corrida, no fuente).
6. **Preservar el conocimiento no-código**: las secciones 2.4 (estructura del CUV y modo de falla dockerrips), 4.11 (fechas que prueban que el reintento sin corregir falla) y 13 (trampas de PS 5.1) son el valor difícil de regenerar. Este documento es la fuente.
7. **Antes de retomar la operación**: leer `BITACORA.md` (protocolo de CLAUDE.md) — los pendientes #6-9 son de este módulo — y verificar con `git log --oneline -- docs/diagnostico_lote_v2_pendientes/` si otro chat avanzó después del 22-jul.
8. **Si se implementa la mejora de `consolidar_carpetas_notas.py`** (validar JSON antes de renombrar a CUV_), actualizar también §6 del README del módulo, que hoy documenta el comportamiento actual como causa raíz.

## 17. Resumen ejecutivo (para el desarrollador que lo mantenga)

Este módulo es la **investigación forense + herramientas de destrabe** de 12 notas crédito del Dispensario atascadas en SIMED. Su valor no es el código (3 scripts PowerShell sin dependencias) sino el **diagnóstico probado**: 6 facturas tienen como "CUV" un error de conexión guardado por accidente (servicio `dockerrips.hus.gov.co:9443` caído — la validación ante MinSalud nunca corrió), 3 tienen el RIPS rechazado por RVC086 con el campo exacto a corregir (`usuarios[0].servicios.procedimiento[0].codDiagnosticoRelacionado`), 2 no tienen PDF (se bajan del DIAN con radicados 492346/521665) y 1 no tiene NE confirmado (¿302111?). **El 75% depende de SISTEMAS, no de Cartera** — los informes generados (Word técnico + informe de gerencia) son la gestión de destrabe.

Para mantenerlo: (a) los tres scripts se corren con `powershell -ExecutionPolicy Bypass -File docs\diagnostico_lote_v2_pendientes\<script>.ps1` desde `C:\temp-notas` tras `git pull`; (b) el estado real SIEMPRE se lee del share (el más reciente `ResultadosDoker_*.json`), nunca de la copia local; (c) los `.ps1` son ASCII puro y con backticks tratados con cuidado — leer §13 antes de editarlos; (d) cuando SISTEMAS corrija, la cadena es `verificar_cuv_notas.py` → refrescar share→local → `cargar_soportes_simed.py --solo <NE>` con piloto primero; (e) la memoria viva del estado está en `BITACORA.md` — leerla al empezar, actualizarla al terminar. El error histórico a no repetir: **confiar en un registro que dice "subida OK" sin verificar el contenido real del CUV**.
