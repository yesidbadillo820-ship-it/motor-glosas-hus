# ENTREGA TÉCNICA — MÓDULO DE GESTIÓN MASIVA DE GLOSAS COOSALUD

**Documento oficial de entrega del módulo al equipo principal.**
Reconstruye TODO lo desarrollado y aprendido en la rama `claude/zip-extract-organize-folders-9fv7oy`
(PR #158) y en las sesiones de trabajo asociadas, entre el 08/07/2026 y el 22/07/2026.
Autor operativo: analista de cartera ESE Hospital Universitario de Santander (HUS, NIT 900006037-4).

---

## 1. OBJETIVO DEL DESARROLLO

### Por qué se creó

COOSALUD EPS glosa (objeta el pago de) miles de facturas del HUS. El proceso manual exigía:

1. Descargar del portal VCO de COOSALUD un ZIP con **miles de archivos Excel sueltos** (3 por factura).
2. Consolidarlos a mano (Power Query + BUSCARV).
3. Armar a mano el archivo de OBJECIONES para el sistema contable **DGH (Dinámica Gerencial Hospitalaria)**, cruzando cada código de servicio del portal contra la base de servicios de DGH.
4. Responder cada glosa una por una en el portal VCO (clic por clic).
5. Llenar a mano el archivo de respuesta de trámites que DGH exige después.
6. Guardar evidencias (pantallazos) y archivarlas en el servidor de la coordinación.

Con lotes de 2.000+ facturas ese proceso era inviable. El módulo lo automatiza de punta a punta.

### Problema que resolvía / necesidad que cubría

- Cargues masivos con **límites duros de DGH**: máx. 300 facturas por cargue de objeciones, ~500 por cargue de trámites.
- **DGH no guarda nada si el cargue trae un error** → había que poder rearmar el archivo completo corregido.
- Reglas de negocio complejas: extemporaneidad (art. 57 Ley 1438/2011), glosas de CALIDAD que responde auditoría médica, copagos que DGH descuenta, cruce de códigos portal↔DGH con medicamentos ambiguos.
- Trazabilidad: evidencias unificadas en Word/PDF con radicado GI-33-XXXX-2026 en el servidor compartido.

### Resultados operativos comprobados (con este módulo)

| Fecha | Operación | Cifras |
|---|---|---|
| 14/07/2026 | Masivo grande objetado en DGH | 2.170 facturas · **$4.740.970.568** · 8 lotes |
| 14/07/2026 | Trámites DGH (5 archivos) | 2.133 facturas · 40.043 ítems |
| día récord | Respuesta portal VCO con bot | **1.481 facturas cerradas en una jornada** (10:14–16:30) |
| 16/07/2026 | Lote 41 facturas objetado | 8.801 ítems · **$754.206.720** |
| 21/07/2026 | Lote nuevo 1.600 facturas procesado completo en un día | 4.257 ítems · **$230.736.952** |
| 22/07/2026 | Portal en paralelo (4 ventanas) | 1.425 cerradas en 2,5 h (antes ~13 h) |
| 22/07/2026 | Trámites entregados | 4 lotes de ≤499 (1.599 fact/4.026 ítems) + 35 restantes (6.171 ítems) |

---

## 2. ARQUITECTURA

### Naturaleza del módulo

**No es una aplicación web.** Son **bots de escritorio en Python 3 (solo stdlib + openpyxl)** que corren
en el equipo Windows del analista, lanzados por archivos `.bat`. Conviven en el repositorio
`motor-glosas-hus` (que además contiene una app FastAPI, NO tocada por este desarrollo salvo 2
archivos de test — ver §10).

### Estructura de carpetas relevante

```
motor-glosas-hus/
├── BITACORA.md                  ← memoria común de todos los chats (creada en este desarrollo)
├── CLAUDE.md                    ← instrucción: leer/actualizar BITACORA.md en cada sesión
├── docs/
│   ├── CONTEXTO_COOSALUD.md     ← reglas del proceso (previo)
│   └── ENTREGA_MODULO_COOSALUD.md  ← este documento
└── tools/
    ├── organizar_cargue_masivo_coosalud.py   (bot 1: ZIP → carpetas por lote)
    ├── consolidar_coosalud.py                (bot 2: consolidados + OBJECIONES + respuestas)  ~72 KB
    ├── coosalud_todo.py                      (orquestador interactivo de 1+2)
    ├── corregir_errores_dgh.py               (bot 3: reintento tras errores DGH)
    ├── respuesta_tramites_dgh.py             (bot 4: archivo de trámites DGH)  ~16 KB
    ├── responder_glosas_coosalud.py          (bot 5: portal VCO con Playwright)  ~72 KB (previo, usado y explotado aquí)
    ├── evidencias_a_word.py                  (pantallazos → .docx, 1 factura/página)
    ├── evidencias_a_pdf.py                   (pantallazos → PDF multipágina)
    ├── HACER TODO COOSALUD.bat               (lanza coosalud_todo.py)
    ├── ORGANIZAR CARGUE COOSALUD.bat
    ├── CONSOLIDAR COOSALUD.bat
    ├── CORREGIR ERRORES DGH.bat
    ├── RESPUESTA TRAMITES DGH.bat
    └── FACTURAS YA OBJETADAS.txt             (100 facturas del piloto — no repetir)
```

En el equipo del usuario los bots se distribuyen como carpeta **"BOTS COOSALUD"** (zip entregado:
`BOTS COOSALUD (CORRECCION COPAGO).zip` — 5 .py + 5 .bat + TXT + READMEs + LEEME).
El bot del portal vive en `C:\temp-notas\tools\` (checkout de la rama
`claude/excel-reconciliation-data-9Bnpj`, distinta a la de este desarrollo).

### Dependencias / librerías

| Paquete | Uso | Nota |
|---|---|---|
| `openpyxl` | todo el manejo de .xlsx | `coosalud_todo.py` lo auto-instala con pip si falta |
| `playwright` + Chromium | bot del portal VCO | `py -m playwright install chromium` |
| `python-docx` | evidencias_a_word | |
| `Pillow` | evidencias_a_pdf | |
| stdlib | zipfile, io, re, argparse, logging, datetime, unicodedata, csv | sin dependencias exóticas |

### Sistemas externos (APIs "de facto")

- **Portal VCO COOSALUD** (`vco.ctamedicas.com`): UI web automatizada con Playwright (no hay API).
- **DGH / Dinámica Gerencial**: se integra por **archivos Excel** (cargue de OBJECIONES, cargue de trámites, exports de pantallas). No hay API; los formatos exactos están en §4.
- **Servidor de coordinación** `Z:\SERVIDOR GLOSAS\...` para evidencias.

### Modelos / servicios / BD

No hay base de datos ni modelos propios: el "estado" vive en los archivos Excel y TXT. (La app web
del repo tiene su BD, pero este módulo no la usa.)

---

## 3. FUNCIONES IMPLEMENTADAS (lista completa por archivo)

### 3.1 `tools/organizar_cargue_masivo_coosalud.py`

- **`_iter_archivos_zip(zf, _nivel)`** — generador `(nombre, bytes)` que **entra recursivamente en ZIPs anidados** (el masivo real viene como ZIP con 16–22 zips adentro; algunos ZIP de Windows usan `\` como separador interno). ZIP interno ilegible → warning y se salta.
- **`organizar_zip(zip_path, ...)`** — clasifica cada `.xlsx` por su nombre: `DETALLE HUS*` → DETALLES, `GLOSAS HUS*` → GLOSAS, `HUS*` → FACTURAS; lo demás (PDFs de oficios, etc.) → `SIN_CLASIFICAR`. Reparte en subcarpetas `LOTE 01, LOTE 02…` de **máx. 300 archivos**, ordenados por número de factura para que los lotes queden alineados entre las 3 carpetas. **Idempotente** (correr 2 veces no duplica; `--sobrescribir` para reemplazar).
- **CLI**: `--zip` (obligatorio), `--destino` (def. Escritorio), `--nombre` (def. "CARGUE MASIVO COOSALUD"), `--max-por-lote` (300), `--reporte` (CSV), `--dry-run`, `--sobrescribir`, `-v`.

### 3.2 `tools/consolidar_coosalud.py` (núcleo, ~1.700 líneas)

**Normalización y parseo**
- `norm_texto`, `norm_header` (mayúsculas, espacios colapsados), `norm_codigo` (quita `.0` de códigos tipados número), `norm_desc`, `norm_factura` / `_num_factura` (HUS0000512396 / HUS512396 / 512396 → misma clave), `factura_dgh` (→ `HUS0000nnnnnn` para CRNCXC).
- **`a_numero(v)`** — parsea moneda en formato colombiano (`1.234.567,89`), US (`1,234,567.89`), **miles ambiguos** (`26,140` = 26140) y negativos contables. Este parser evitó errores de ×1000 en `CROVALOBJ`.
- `valor_o_numero` — número si se puede, texto si no.
- `leer_xlsx` — primera hoja; **`reset_dimensions()`** porque los xlsx del portal declaran dimensión incorrecta; ignora archivos `~$`; xlsx corrupto aborta con nombre claro.
- `alinear_filas` — reordena por nombre de encabezado cuando los lotes traen columnas en distinto orden.
- Deduplicación por `id_glosa` y por `id_detalle` con aviso (archivos repetidos no duplican valores).

**Cruce portal → DGH (`SLNSERPRO`)**
- **`cargar_base_dgh(path, facturas_trabajadas)`** — lee la base "SERVICIOS FACTURADOS COOSALUD DGH.xlsx" **en streaming** (la real pesa 80 MB+; antes consumía ~1,2 GB de RAM). Filtra solo las facturas trabajadas. Hace el **"arreglo"** del proceso manual: en filas de medicamentos (SLNSERPRO_SERVICIO vacío) rellena SERVICIO/CUPS y descripciones con CODIGO_MEDICAMENTO / NOMBRE_MEDICAMENTO. Valida que el archivo SÍ sea la base (si faltan ≥5 columnas esperadas → error explicativo). Construye los índices de cruce:
  - `srv_exact` (código == SLNSERPRO_SERVICIO propio, máxima prioridad)
  - `exact` (código idéntico en cualquiera de: SLNSERPRO_SERVICIO, SLNSERPRO_CUPS, CODIGO_MEDICAMENTO, COD_MED_FACTURA)
  - `sufijo` (código con sufijo sin ceros → conjunto de códigos DGH)
  - `base` (misma base, presentación distinta)
  - `desc` (por descripción, solo si es inequívoca)
  - **`nom_med`** (factura → {(nombre_medicamento_normalizado, código DGH)}) — se indexa por `cod_med`, funciona con base cruda Y ya-arreglada. *Decisión documentada: primero se puso el guard `if not servicio and cod_med` y no poblaba con bases ya arregladas; se cambió a `if cod_med:`.*
  - `valor` (suma Vr_SERVICIO por (factura, código)) y `saldo` (SALDO_FACT por factura) para el guardián.
- **`cruzar_codigo(cruces, factura, codigo_portal, descripcion)`** — cruce en niveles, en orden: exacto-servicio → exacto-cualquier-columna → **por NOMBRE de medicamento** → sufijo sin ceros → misma base → (último respaldo, fuera de la función) por descripción. *Por qué existe el nivel por nombre:* dos medicamentos distintos compartían base+cero a la izquierda (portal `20048691-1` = KETAMINA vs `20048691-01` = SALBUTAMOL) y se robaban el código; el nombre único (prefijo bidireccional, mínimo 4 caracteres) los separa — el DGH real de SALBUTAMOL era otra base (`20083667-1`).
- `_cod_sufijo_norm`, `_cod_base`, `_cruzar_por_nombre_med` — auxiliares de lo anterior.

**Generación de OBJECIONES (`generar_objeciones`)**
- Formato exacto de la plantilla DGH — 16 columnas: `CDCONSEC` (texto, consecutivo por factura **sin huecos** aunque se excluyan filas), `CDFECDOC`/`CROFECOBJ` (fecha Excel de `--fecha`), `CRNCXC` (`HUS0000nnnnnn`), `CROREFERE`/`CROOBSERV`/`CRNCLAOBJ`/`IDRIPS`/`CTNCENCOS` vacíos, `CROCLAOBJ`=0, `GENUSUARIO4`="999" (texto), `CRNCONOBJ`, `SLNSERPRO`, `CROVALOBJ` (número), `CRDOBSERV` (observación, recortada a 90), `CROTIPOBJ`.
- **`CRNCONOBJ` — regla de prioridad CL**: si la factura/ítem tiene glosa CL (médica), **CL manda sobre cualquier administrativa sin importar el valor**; entre glosas del mismo tipo gana la de mayor valor; empate conserva la primera. *(Cambio de enfoque documentado: primero era "mayor valor"; el área corrigió: "SI TIENE CL GANA POR ENCIMA DE TODO".)*
- **`CROTIPOBJ` por FACTURA completa**: solo CL → 1 en todas sus filas; CL + otros → 2 (mixta) en todas; sin CL → 0.
- **Servicios que no cruzan** → hoja/archivo **REVISAR ("no está en DGH")** y por defecto quedan FUERA del archivo (DGH marcaría error); `--incluir-no-cruzados` los deja.
- **Guardián de valor/saldo**: DGH no acepta objetar más que el valor del servicio ni más que el saldo de la cuenta. Se acumula lo objetado por (factura, código) y por factura; si la objeción excede el cupo se **CAPA** (no se pierde) y se registra en VALOR_AJUSTADO; si no queda cupo → REVISAR "sin cupo en DGH".
- **Corrección de COPAGO (17/07)**: DGH descuenta la cuota moderadora del valor del servicio; el máximo objetable por línea es `valor_total − valor_cuota_moderadora`. El generador lee ambas columnas del DETALLE y capa automáticamente (contador `capados_copago` + log). *Evidencia que motivó el fix:* 8 errores DGH "El VALOR OBJECION no puede ser mayor al valor del servicio" en HUS517650; la resta cuadró al peso en las 8 (p. ej. 711.889 − 81.872 = 630.017).*
- Aviso previo de **facturas con copago** (top 5 por valor) al consolidar, porque son la causa típica de errores de valor.
- Facturas con patrón raro (no HUS) se reportan como malformadas.

**Días hábiles y respuestas (`generar_respuestas_glosas`)**
- Motor de días hábiles de Colombia: `_pascua` (algoritmo de Gauss), `festivos_colombia` (Ley Emiliani: festivos trasladables al lunes), `_es_habil`, `dias_habiles_entre` (exclusivo inicio, inclusivo fin), `sumar_dias_habiles`, `a_fecha`. Validado contra casos reales: DIA=38 (rad 06/05→03/07), DIA=21 (rad 01/06→03/07), vencimiento 27/07 = 03/07 + 15 hábiles. Fórmula Excel equivalente entregada al área: `=DIA.LAB(O141;15;$Z$1:$Z$18)` con los 18 festivos de 2026.
- Constantes: `DIAS_HABILES_EPS=20` (plazo de la EPS para glosar, art. 57 Ley 1438/2011), `DIAS_HABILES_RESPUESTA=15` (plazo del HUS para responder), `COD_RTA_EXTEMPORANEA="RE9502"`, `COD_RTA_NORMAL="RE9901"`, `OBS_EXTEMPORANEA` (texto legal "ESE HUS NO ACEPTA GLOSA…extemporánea…"), **`OBS_POR_TIPO`** con los 4 textos oficiales del área (TARIFAS con contratos 68001S00060339-24 y 68001C00060340-24, SOAT SMLV-15% y tarifas institucionales; AUTORIZACION con AT 02/AT 03 y envíos 1–4, Res. 3047/2008 y Dto. 4747/2007; FACTURACION con Dto. 2423/96; SOPORTES "se anexa soporte"), `TIPO_POR_PREFIJO` (TA/AU/FA/SO/CL/DE/CO → tipo).
- Produce **CONSOLIDADO RESPUESTAS GLOSAS** por lote: hoja BASE = todas las glosas + columnas `FECHA RADICACION`, `FECHA GLOSA`, `FECHA DE VENCIMIENTO` (+15 hábiles), `DEVOLUCIONES`, `DIA` (hábiles rad→glosa), `EXTEMPORANEA` (SI/NO), `COD RESPUESTA GLOSA`, `COD`, `OBSERVACION RTA GLOSA`; hoja FACTURAS. Regla: DIA>20 → RE9502+texto extemporánea para TODO; a tiempo → RE9901+texto del área según tipo; **CALIDAD a tiempo → código y observación EN BLANCO** (las responden las doctoras — "ESO NO LO PODEMOS SACAR NOSOTROS").

**Por lotes**
- `descubrir_lotes(carpeta)` agrupa archivos por subcarpeta LOTE de cada categoría; `main()` itera por lote y escribe TODO en `CONSOLIDADOS\LOTE XX\`: `CONSOLIDADO GLOSAS/DETALLE/FACTURAS`, `SERVICIOS FACTURADOS COOSALUD` (base filtrada/arreglada, si `--servicios`), `OBJECIONES LOTE XX`, `REVISAR (no van en el cargue)`, `CONSOLIDADO RESPUESTAS GLOSAS`. *Razón: DGH solo acepta 300 facturas por cargue → un OBJECIONES por lote.*
- `--omitir-facturas archivo.txt` — excluye del OBJECIONES facturas ya objetadas (si van, **DGH rechaza el cargue COMPLETO**). Los consolidados sí las conservan.
- CLI: `--carpeta` `--fecha DD/MM/AAAA` `--servicios` `--incluir-no-cruzados` `--omitir-facturas` `--salida` `-v`.

### 3.3 `tools/coosalud_todo.py`

TODO-EN-UNO interactivo sin argumentos (doble clic en `HACER TODO COOSALUD.bat`): pregunta ZIP, fecha y base; auto-instala openpyxl con pip si falta; usa `FACTURAS YA OBJETADAS.txt` automáticamente si está junto al script; exige los 3 .py juntos (coosalud_todo + organizar + consolidar).

### 3.4 `tools/corregir_errores_dgh.py`

- Lee el Excel de errores que devuelve DGH (hoja `VALIDACIONIMPORTACION`, columnas Documento/Validacion/MensajeValidacion/FilaValidacion) + el OBJECIONES que se intentó cargar.
- Regexes `RE_YA` (ya objetado), `RE_VALOR` ("VALOR OBJECION no puede ser mayor al valor del servicio (X)"), `RE_TOTAL`.
- `capar_valores` (heurísticas: 90% de tarifa pactada / valor unitario) y `capar_totales`.
- **Regla clave: DGH no guarda NADA si el cargue trae un error** ("toca cerrar todo y volver a cargar el excel completo"). Por eso el reintento lleva **TODAS las facturas corregidas**, menos las ya-objetadas y las de corrección manual (que salen a un TXT aparte).
- Lanzador: `CORREGIR ERRORES DGH.bat` (requiere consolidar_coosalud.py al lado).

### 3.5 `tools/respuesta_tramites_dgh.py`

- **`cargar_radicaciones(carpeta)`** — factura → fecha_radicacion desde las cabeceras `HUS*.xlsx` de la carpeta FACTURAS del masivo.
- **`procesar(plantilla, carpeta, fecha_cargue, salida, max_facturas=499, omitir=None)`** — dos pasadas:
  - **PASADA 1**: por cada fila del export calcula la respuesta. `dias_habiles_entre(radicación, FechaObjecion) > 20` → RE9502 + OBS extemporánea para TODOS los ítems (incluidos CL). A tiempo → RE9901 + `OBS_POR_TIPO[tipo]`; si el tipo no tiene texto (CALIDAD/COBERTURA) o no hay radicación → la factura se marca **incompleta**. `omitir` (ya subidas) se salta contando.
  - **PASADA 2 — REGLA DE FACTURA COMPLETA**: las facturas incompletas se quitan **ENTERAS** del archivo (no solo el concepto CL) — "se suben después, cuando las doctoras respondan"; su lista queda en TXT `... - FACTURAS PENDIENTES AUDITORIA MEDICA.txt`.
  - **Partición en LOTES de máx. 499 facturas** (límite del cargue de trámites de DGH ~500), sin partir jamás una factura entre lotes; 1 solo lote → sin sufijo, varios → `LOTE 01, 02…`.
- Columnas agregadas **exactamente** (`COLS_NUEVAS`): `"FECHA DE CARGUE "`, `"CODIGO RESPUESTA "` (⚠️ **con espacio final**, así lo trae el ejemplo real del área), `"VALOR ACEPTADO"` (=0 siempre: el HUS no acepta), `"OBSERVACION"`. Si la plantilla ya las trae (re-corrida) no se duplican. Formato fecha `DD/MM/YYYY`.
- Conserva TODAS las columnas base y el **nombre de hoja** del export.
- CLI: `--plantilla --carpeta --fecha-cargue --salida --omitir-facturas --max-facturas-lote`; sin argumentos pregunta todo (acepta rutas arrastradas). `RESPUESTA TRAMITES DGH.bat`.

### 3.6 `tools/responder_glosas_coosalud.py` (previo — conocimiento operativo generado aquí)

- Lee el consolidado (hoja `BASE` por defecto) mapeando encabezados: `NUMERO_FACTURA`, `ID_GLOSA`, `TIPO_GLOSA`, `COD RESPUESTA GLOSA`/`CODIGO RESPUESTA GLOSA`, `OBSERVACION RTA GLOSA`/`OBSERVACION RESPUESTA GLOSA`.
- ⚠️ **La clave de factura es el formato CORTO** (`HUS521695`, columna `numero_factura`) — las listas `--lista` deben venir así, NO `HUS0000521695` (error real corregido: "Ninguna de las facturas pedidas está en la hoja BASE").
- Flujo por factura: Bolsa de Respuestas → buscar → ▶ → GLOSAS → Mostrar: Todos → por cada grupo (código+justificación): checkboxes → Responder Masivamente → modal (código, justificación, PDF PDX si SOPORTES) → Responder → al final Terminar Respuesta → pantallazo "¡Usted ha cerrado una cuenta!" → `EVIDENCIA\HUS######_cierre.png`.
- Regla SOPORTES: grupo es-soporte ⟺ justificación contiene "ANEXA SOPORTE" → adjunta `PDX_*.pdf` localizado vía índice TXT (`--indice`, `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt`); si no hay PDX la factura queda PENDIENTE_PDX (no promete soporte que no adjuntó). Fallback PDX→HAM→PDE.
- CALIDAD NO se responde por defecto (queda para médicas); **`--incluir-calidad`** cuando la planilla ya trae respuesta (p. ej. extemporáneas: TODO va RE9502).
- Selección: `--solo` | `--facturas` | `--lista txt` | `--todas`; pilotos `--max-grupos/--max-facturas`; `--evidencias` (def. EVIDENCIA), `--reporte` CSV, **`--saltar-csv`** (reanudar: omite estados terminales OK, OK_CALIDAD_ABIERTA, SOLO_CALIDAD, NO_EN_BOLSA, TERMINADA_SIN_CARTEL; acumulable), `--cerrar-residuales` (glosas del portal no listadas en el Excel → RE9901 texto genérico), `--con-cabeza`, `--lento`, `--log`.
- Credenciales por variables de entorno: `setx COOSALUD_USER` / `setx COOSALUD_PASSWORD` (NUNCA en código).
- **Paralelización comprobada (22/07)**: 4 ventanas PowerShell simultáneas, listas disjuntas de 400 (`PARALELO_1..4.txt`), carpetas R1..R4, reportes separados y `--saltar-csv` común → 1.425 facturas en ~2,5 h; el portal ACEPTA sesiones concurrentes del mismo usuario. Estado `NO_EN_BOLSA` = la EPS aún no puso la factura en bolsa (no es error; reaparecen luego como pendientes).

### 3.7 `tools/evidencias_a_word.py` y `tools/evidencias_a_pdf.py` (previos, integrados al flujo)

- Word: 1 factura por página (encabezado + imagen escalada A4); `--carpeta` o `--lista` + `--salida` + `--patron`.
- PDF: PNG/JPG → PDF multipágina; `--lista`/`--paginas`/`--carpeta` + `--salida` (ejemplo de nombre real: `GI-33-5096-2026.pdf`).
- Flujo de archivo final en el servidor (procedimiento entregado):
  `Z:\SERVIDOR GLOSAS\F\COMPARTIDA_GLOSAS\0-INFORMACION COORDINACION\0. GESTION ENTIDADES\2. TRAMITE DE GLOSAS\2026\RESPUESTA GLOSAS (GI-GR-DEV)\07.JULIO\COOSALUD\RESPUESTA GLOSA INICIAL\GI-33-5181-2026\` con `GI-33-5181-2026.pdf` + subcarpeta `EVIDENCIAS SUBIDAS\` (los .png). Dedupe de pantallazos por nombre al juntar varias carpetas R#.

### 3.8 Arreglo de tests del CI (app web)

- `tests/test_api/test_por_dia_semana.py` y `tests/test_api/test_heatmap_actividad.py`: sembraban con **fechas fijas de abril/2026** y los endpoints cuentan una **ventana móvil de 90 días** → los tests caducaron solos el 19/07. Fix: fechas **relativas** (el lunes de la semana pasada, 7–13 días atrás, + su martes/miércoles), conservando día-de-semana y hora esperados. Mismo defecto ya corregido antes en `test_fecha_objecion_mensual::test_serie`.

---

## 4. FLUJO COMPLETO (paso a paso, ciclo real de un lote)

1. **Portal VCO** entrega ZIP (remesas con zips internos; 3 xlsx por factura: `HUS#.xlsx` cabecera 15 col con `fecha_radicacion`; `DETALLE HUS#.xlsx` 15 col con `id_detalle, codigo_servicio, cantidad, valor_unitario, valor_cuota_moderadora, valor_total, valor_aprobado, valor_glosado…`; `GLOSAS HUS#.xlsx` 12 col con `id_glosa, id_detalle, codigo_glosa, tipo_glosa, justificacion_glosa, valor_total_glosa, fecha_glosa…`).
2. **`HACER TODO COOSALUD.bat`** → organiza en `CARGUE MASIVO COOSALUD\{FACTURAS,DETALLES,GLOSAS}\LOTE XX` (≤300) → consolida por lote → cruza con la base DGH → capa copago/valor/saldo → escribe por lote: consolidados + `OBJECIONES LOTE XX.xlsx` + `REVISAR` + `CONSOLIDADO RESPUESTAS GLOSAS`.
3. **Cargue a DGH** de cada OBJECIONES (uno por lote). Si DGH devuelve el Excel de errores → **`CORREGIR ERRORES DGH.bat`** arma el reintento COMPLETO (DGH no guardó nada).
4. **Respuesta en portal VCO**: `responder_glosas_coosalud.py` con el CONSOLIDADO RESPUESTAS (masivo unificado si son varios lotes) — en paralelo con listas si el volumen lo pide. Reanudación con `--saltar-csv`. Las que salgan NO_EN_BOLSA se reintentan después (la plataforma da la lista de pendientes).
5. **Evidencias**: lista de `HUS*_cierre.png` → Word (`CARGUE PLATAFORMA GI-33-XXXX-2026.docx`) → PDF (`GI-33-XXXX-2026.pdf`) → carpeta `GI-33-XXXX-2026` en Z: con subcarpeta `EVIDENCIAS SUBIDAS`.
6. **Export de trámites de DGH**: pantalla de **SEGUIMIENTO** (hoja `CRRPSEGUIMIENTORECEPCIONOBJECIO`, 34 columnas, con `Oid` de trámite y **`ListadoConceptos.Oid`** por concepto). ⚠️ La cuadrícula **solo exporta lo cargado en pantalla**: bajar el scroll hasta el final o exportar por tandas.
7. **`RESPUESTA TRAMITES DGH.bat`** → `MASIVO COOSALUD <ddmmaaaa> LOTE 01..NN.xlsx` (≤499/archivo, 34+4 columnas) + TXT de facturas apartadas (CL/CO a tiempo). Se envía por correo al Ing. de sistemas DGH indicando **facturas e ítems totales y por archivo** (plantilla de correo documentada en la conversación).
8. **Bitácora**: actualizar `BITACORA.md` (hecho/pendiente/mañana con fecha).

### Conocimiento crítico de los formatos DGH (descubierto y validado aquí)

- **Export de trámites válido**: hoja `CRRPSEGUIMIENTORECEPCIONOBJECIO`, 34 columnas, con `ListadoConceptos.Oid` **único por fila/concepto** (llave con la que DGH pega cada respuesta). Rango observado de Oid de trámite ~598k–604k (uno por factura); de concepto ~1,27M–1,29M.
- **Export INVÁLIDO para trámites**: pantalla de RECEPCIÓN (hoja `CRRPRECEPCIONOBJECION`, 26 columnas) — trae el Oid del trámite pero **NO** `ListadoConceptos.Oid`. *Decisión documentada: se generó un MASIVO desde este formato y luego se descartó/desaconsejó; inventar o dejar vacíos los Oids arriesga pegar respuestas a trámites equivocados. Se pidió re-export de la pantalla correcta.*
- DGH **agrupa** al registrar: varias líneas de OBJECIONES del mismo servicio+concepto quedan como UN concepto (suma valores). Por eso `filas OBJECIONES ≥ conceptos export` (p. ej. 4.252 → 4.026) — es normal, no es pérdida.
- En el export, `ConceptoObjecion.Codigo/Nombre` (nivel trámite) vienen vacíos, `ValorObjecion` (trámite) = 0, `FacturaCartera.Saldo` = `FacturaCartera.Valor` en todas las filas observadas, `NombreCompletoNA` = `NombreCompletoAN` (entidad jurídica). Entidad: `COOSALUD ENTIDAD PROMOTORA DE SALUD S.A.`, código `ESS024`, NIT 900226715.

---

## 5. BASE DE DATOS

**Este módulo no usa base de datos.** No hay tablas, migraciones ni índices propios. Persistencia = archivos:
- Entradas: ZIP del portal, base DGH de servicios, exports DGH.
- Salidas: consolidados, OBJECIONES, REVISAR, RESPUESTAS, MASIVO trámites, TXT (pendientes/omitir/listas), CSV (reportes del bot del portal), PNG/DOCX/PDF (evidencias).
(Las tablas de la app web del repo no fueron tocadas.)

---

## 6. BACKEND

No hay backend HTTP propio. Los "endpoints" equivalentes son las CLIs de los 5 bots (§3) con sus
validaciones (archivos faltantes, base DGH que no parece serlo, hoja inexistente, columnas faltantes
con mensaje de cuáles acepta) y su manejo de errores (logs con niveles, códigos de salida ≠0,
pantallazos de diagnóstico `debug_screenshots\` en el bot del portal).
Del CI del repo: `ruff check --select F,W6` + `ruff format --check` + pytest (2.681 tests) — todo debe quedar en verde.

---

## 7. FRONTEND

No hay frontend propio. La "UI" es: consolas interactivas de los .bat (con `chcp 65001` para tildes) y
la automatización de la UI del portal VCO (Playwright/Chromium; `--con-cabeza` para ver el browser).
No se modificó nada de `static/` de la app web.

---

## 8. IA

- **El módulo NO usa IA en runtime.** Ningún bot llama a modelos, no hay prompts, proveedores, temperatura ni fallbacks de IA en el código entregado.
- El desarrollo se realizó en sesiones de Claude Code (asistente de programación); el conocimiento de esas sesiones es lo que este documento y `BITACORA.md` preservan. Regla operativa de esas sesiones: el identificador del modelo no se incluye en commits/PRs/código.

---

## 9. AUTOMATIZACIONES

| Automatización | Qué hace | Cuándo/cómo |
|---|---|---|
| HACER TODO COOSALUD.bat | organiza ZIP + consolida + OBJECIONES por lote | manual, doble clic, interactivo |
| ORGANIZAR / CONSOLIDAR .bat | cada paso por separado | manual |
| CORREGIR ERRORES DGH.bat | reintento completo desde el Excel de errores | manual, tras rechazo de DGH |
| RESPUESTA TRAMITES DGH.bat | archivo de trámites en lotes de 499 | manual, tras export de seguimiento |
| responder_glosas_coosalud.py | respuesta masiva en portal + evidencias + reporte | manual; paralelizable en N ventanas con listas disjuntas |
| evidencias_a_word/pdf | unificación de pantallazos | manual, fin de jornada |
| auto-instalación openpyxl | pip install si falta | dentro de coosalud_todo.py |
| omisión de ya-objetadas | lee FACTURAS YA OBJETADAS.txt automáticamente | dentro de coosalud_todo.py |
| CI GitHub Actions | ruff + pytest + pip-audit en cada push del PR | automático |
| Bitácora | memoria entre sesiones (CLAUDE.md la exige al abrir/cerrar) | cada sesión de Claude Code |

No hay tareas programadas (cron/scheduler) en el módulo.

---

## 10. ARCHIVOS MODIFICADOS/CREADOS EN ESTA RAMA (qué cambió exactamente)

**Creados (módulo COOSALUD):**
- `tools/organizar_cargue_masivo_coosalud.py` + `ORGANIZAR CARGUE COOSALUD.bat` + README (08/07).
- `tools/consolidar_coosalud.py` + `CONSOLIDAR COOSALUD.bat` + README (08/07) — luego endurecido: 9 defectos de revisión adversarial (08/07), cruce 4 niveles y respaldo por descripción (09/07), exclusión de no-cruzados por defecto (09/07), guardián valor/saldo + una sola hoja (09/07), prioridad CL en CRNCONOBJ (09/07), cruce por nombre de medicamento (09/07), lotes de 300 con salidas por lote (09/07), aviso de copago (10/07), CONSOLIDADO RESPUESTAS GLOSAS con RE9502/RE9901 (14/07), CALIDAD en blanco (14/07), **capado por copago** (17/07: nuevas capturas `valor_servicio`/`copago` en glosados, tope `vt−cm` en el guardián, contador y log).
- `tools/coosalud_todo.py` + `HACER TODO COOSALUD.bat` (08/07).
- `tools/corregir_errores_dgh.py` + `CORREGIR ERRORES DGH.bat` (09/07); reintento completo + omisión (09/07).
- `tools/respuesta_tramites_dgh.py` + `RESPUESTA TRAMITES DGH.bat` (14/07): creación, regla de factura completa, lotes de 499, `--omitir-facturas`.
- `tools/FACTURAS YA OBJETADAS.txt` (las 100 del piloto).
- `BITACORA.md` (22/07, con cierre del día) y `CLAUDE.md` (22/07).
- `docs/ENTREGA_MODULO_COOSALUD.md` (este documento).

**Modificados (app web, solo tests):**
- `tests/test_api/test_por_dia_semana.py` — 2 tests a fechas relativas; import `timedelta` arriba, removido import local duplicado.
- `tests/test_api/test_heatmap_actividad.py` — 1 test a fechas relativas (strftime sobre lunes/miércoles de la semana pasada).
- (Previo en la rama: estabilización de `test_fecha_objecion_mensual::test_serie` por el mismo motivo.)

**En la OTRA rama (`claude/excel-reconciliation-data-9Bnpj`, checkout en C:\temp-notas):**
`responder_glosas_coosalud.py`, `evidencias_a_word.py`, `evidencias_a_pdf.py` — usados intensivamente; el conocimiento de uso quedó aquí.

---

## 11. DEPENDENCIAS NUEVAS

Ninguna librería nueva en `requirements.txt` del repo. En el equipo del analista: `openpyxl`
(auto-instalable), `playwright`+Chromium, `python-docx`, `Pillow` — sin versiones fijadas
(instalación `py -m pip install ...`).

---

## 12. CONFIGURACIÓN

- **Variables de entorno** (equipo del analista, vía `setx`, nunca en código): `COOSALUD_USER`, `COOSALUD_PASSWORD`.
- **Sin tokens ni secretos en el repo** (regla de docs/CONTEXTO_COOSALUD.md).
- **Rutas operativas** (equipo/red del analista): `D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD\` (masivo), `D:\USUARIO CARTERA\Desktop\RESPUESTA COOSALUD 1600\{R1..R4}\` (paralelo, EVIDENCIA, reportes), `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt` (índice factura→carpeta de soportes), `C:\temp-notas\tools\` (bot portal), `Z:\SERVIDOR GLOSAS\...\GI-33-XXXX-2026\` (evidencias oficiales).
- **Parámetros clave**: 300 (objeciones/lote), 499 (trámites/lote), 20 y 15 días hábiles, fecha de cargue `DD/MM/AAAA`, radicado GI del mes (ej. GI-33-5181-2026 para julio/COOSALUD).
- CI del repo: `SECRET_KEY` y `DATABASE_URL=sqlite:///./test_ci.db` de prueba, `DISABLE_SCHEDULERS=1`.

---

## 13. RIESGOS (qué puede romperse al integrar)

1. **Encabezados con espacio final** en trámites (`"FECHA DE CARGUE "`, `"CODIGO RESPUESTA "`): si alguien los "limpia", el cargue de DGH deja de reconocerlos.
2. **Formatos de factura**: portal usa corto (`HUS521695`), DGH largo (`HUS0000521695`). Todo cruce debe pasar por `norm_factura`; el bot del portal exige CORTO en `--lista` (error ya sufrido y corregido).
3. **Export de trámites equivocado**: la pantalla de RECEPCIÓN (26 col) NO sirve (sin `ListadoConceptos.Oid`). Nunca fabricar Oids.
4. **Cuadrículas DGH exportan solo lo cargado**: exports truncados silenciosos (pasó: 6 de 41 facturas). Validar SIEMPRE conteos contra lo esperado antes de generar.
5. **DGH agrupa conceptos**: no validar "filas objeciones == filas export" (falso negativo); validar por factura/cobertura.
6. **Copago**: si se toca el guardián, mantener el tope `valor_total − cuota_moderadora` por línea; regresión = rechazo del cargue.
7. **DGH todo-o-nada**: cualquier flujo de reintento debe regenerar el archivo COMPLETO.
8. **Tests con fechas fijas** en la app: patrón que ya reventó 2 veces; usar siempre fechas relativas.
9. **Paralelo del portal**: funciona con sesiones concurrentes hoy; si el portal cambia a sesión única, degradar a 1–2 ventanas. Listas SIEMPRE disjuntas + `--saltar-csv` compartido para no responder doble.
10. **Códigos de glosa**: COOSALUD ya envió un lote con codificación vieja (Res. 3047: 206/207/223/423). La homologación a la nueva (letras+4 dígitos) está deducida y parcialmente confirmada (§15.4); si DGH solo acepta códigos nuevos en CRNCONOBJ, hay que aplicar la tabla antes del cargue.
11. **Scratchpad/temporales de sesiones**: los archivos generados en chats se pierden; lo permanente debe ir al repo o al equipo del usuario (motivo de BITACORA.md y de este documento).

---

## 14. DEPENDENCIAS CON OTROS MÓDULOS

- `respuesta_tramites_dgh.py` y `corregir_errores_dgh.py` **importan de** `consolidar_coosalud.py` (textos oficiales, códigos RE, motor de días hábiles, normalizadores) → deben distribuirse JUNTOS.
- `coosalud_todo.py` importa `organizar_cargue_masivo_coosalud` y `consolidar_coosalud`.
- `responder_glosas_coosalud.py` consume el CONSOLIDADO RESPUESTAS (hoja BASE) que produce `consolidar_coosalud.py` y el índice del BUSCADOR_HUS; produce los PNG que consumen `evidencias_a_word/pdf`.
- Independencia total de la app web del repo (solo comparten repositorio y CI). No confundir con el frente SIMED/Dispensario (otra EPS, otros bots del mismo `tools/`).

---

## 15. PENDIENTES (estado al 22/07/2026)

1. Correr en portal el paquete de **137 pendientes** (`CONSOLIDADO RESPUESTAS PENDIENTES 137.xlsx` + `PENDIENTES_BOT.txt`, con `--incluir-calidad`) y cuadrar su reporte.
2. Que sistemas DGH suba los **5 archivos de trámites** del 22/07 (4 lotes del 1600 + 35 restantes = 1.634 facturas / 10.197 ítems) y el parcial de 6 del 21/07 si no se subió.
3. **Evidencias** del lote 1600 → PDF `GI-33-5181-2026` → carpeta en Z:.
4. **Homologación de códigos** vieja→nueva resolución: 206→TA0601 · **207→TA0701 (confirmado en DGH)** · 223→TA2301 · 423→AU2301 (los otros 3 deducidos del patrón del catálogo: letras = concepto general [FA/TA/SO/AU/CO/CL/DE/RE], dígitos 1–2 = concepto específico heredado de la 3047 [01 estancia, 02 consulta, 06 dispositivos, 07 medicamentos, 08 apoyo dx, 23 otros procedimientos, 29 recargos, 57 apoyo terapéutico, 58 quirúrgicos], dígitos 3–4 = detalle). Confirmar en DGH y agregar la tabla al consolidador.
5. **Registro manual en DGH**: `HUS506920` y `HUS530335` — sus servicios no están en la base DGH. Patrón repetido: código **906340 (SARS COV 2 antígeno, $24.380)** no cruza (3 casos: HUS513595, HUS520580, HUS530335) → pedir a DGH arreglar la base.
6. **4 de las 5 no-cruzadas ya registradas a mano en DGH** (513595, 515251, 516765, 520580, fecha 06/07): definir respuesta y generar su mini-trámite.
7. **37 facturas de auditoría médica** (masivo 14/07; incluye HUS520206): subir trámites cuando las doctoras respondan (sus 4.773 conceptos ya están identificados en el export del 22/07).
8. **HUS531067**: trámite suelto del 14/07 — verificar si su respuesta ya se subió.
9. Errores conocidos menores: 1 estado ERROR en reporte R2 del paralelo (por identificar; probablemente cubierto por las 137).

---

## 16. RECOMENDACIONES PARA FUSIONARLO AL PROYECTO PRINCIPAL

1. **Mergear el PR #158 completo** (rama `claude/zip-extract-organize-folders-9fv7oy` → `motor-glosas`): trae los 5 bots, los .bat, BITACORA.md, CLAUDE.md, los fixes de tests y este documento. CI ya está en verde.
2. **Traer de la rama hermana** (`claude/excel-reconciliation-data-9Bnpj`) `responder_glosas_coosalud.py`, `evidencias_a_word.py`, `evidencias_a_pdf.py` si el principal no los tiene en su última versión — y unificar para que el equipo no dependa del checkout `C:\temp-notas`.
3. Mantener los archivos del módulo **juntos en `tools/`** (imports cruzados, §14) y los `.bat` junto a los `.py`.
4. NO renombrar columnas ni hojas de los formatos DGH (¡espacios finales!, §13.1) ni "normalizar" los nombres de archivo `MASIVO COOSALUD <fecha> LOTE NN.xlsx`.
5. Ejecutar una regresión mínima post-merge: `ruff check --select F,W6`, `ruff format --check`, pytest; y un ciclo de humo con un ZIP pequeño del portal + una base DGH de prueba (existen generadores sintéticos usados en el desarrollo).
6. Conservar `FACTURAS YA OBJETADAS.txt` y la disciplina de `--omitir-facturas` (una factura repetida tumba el cargue completo de DGH).
7. Adoptar la **BITÁCORA** como práctica del proyecto principal (CLAUDE.md ya la exige): es el mecanismo anti-pérdida de conocimiento entre sesiones/chats.
8. Cuando se confirme la homologación (§15.4), implementarla como diccionario en `consolidar_coosalud.py` aplicado a `CRNCONOBJ` cuando el código de glosa venga numérico.

---

## 17. RESUMEN EJECUTIVO (para el desarrollador que lo reciba)

Este módulo automatiza el ciclo completo de glosas COOSALUD del HUS: **ZIP del portal → lotes de 300 →
consolidados + OBJECIONES para DGH (con cruce de códigos, prioridad CL, capado por copago/valor/saldo) →
respuesta masiva en el portal VCO (Playwright, paralelizable) → evidencias Word/PDF con radicado GI →
archivo de trámites DGH en lotes de 499 → bitácora**. Son 5 bots de escritorio en Python/openpyxl
lanzados por .bat; sin BD, sin API, sin IA en runtime: todo el estado va en Excel/TXT/CSV.

Lo que DEBES saber para mantenerlo: (a) los **formatos DGH son sagrados** — 16 columnas de OBJECIONES,
34+4 de trámites con dos encabezados que terminan en espacio, y el export válido es el de SEGUIMIENTO
porque trae `ListadoConceptos.Oid`; (b) **DGH es todo-o-nada** en los cargues y **agrupa** conceptos al
registrar; (c) las reglas de negocio no son técnicas sino legales/del área: 20 días hábiles para
extemporaneidad (RE9502), 15 para responder, CALIDAD es de las doctoras, el copago no se objeta, y los
4 textos de respuesta son oficiales del área — no los edites sin el área; (d) los números de factura
tienen dos formatos y TODO cruce pasa por `norm_factura`; (e) si DGH devuelve errores, se corrige y se
recarga el archivo COMPLETO; (f) la memoria del proyecto está en `BITACORA.md` — léela al empezar,
actualízala al terminar. Con eso, un lote de 1.600 facturas se procesa, responde y documenta en un día.
