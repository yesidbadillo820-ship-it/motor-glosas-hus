# DOCUMENTACIÓN OFICIAL DE ENTREGA — Módulo "Organizador de Objeciones EMSSANAR"

**Repositorio:** `yesidbadillo820-ship-it/motor-glosas-hus`
**Rama de desarrollo:** `claude/emsannar-objections-bot-xa7g6l`
**Pull Request:** #162 (borrador) — "Bot organizador de objeciones EMSSANAR → Excel OBJECIONES (cargue DGH)"
**Período de desarrollo:** 15 al 22 de julio de 2026
**Documento generado:** 22 de julio de 2026, como acta de entrega al proyecto principal.

Este documento reconstruye TODO lo realizado en la conversación que produjo el
módulo: análisis, decisiones, descartes, código, pruebas, verificaciones,
incidentes de integración y pendientes. Nada de lo aquí escrito es inventado:
todo proviene del trabajo efectivamente ejecutado y verificable en el
historial de la rama.

---

## 1. OBJETIVO DEL DESARROLLO

**Petición original del usuario (literal):** *"NECESITO CREAR UN BOT QUE ME
ORGANIZE LAS OBJECCIONES DE LA ENTIDAD EMSANNAR COMO LO HIZO CON COOSALUD.
TOMO ESE EXCEL COMO PUNTO DE APOYO Y PARTIDA DE EJEMPLO Y ME LO ARME UNO NUEVO
A BASE DEL PDF QUE ADJUNTO."*

**Problema que resuelve.** La EPS EMSSANAR radica sus objeciones (glosas) al
hospital como PDFs generados por la plataforma **ripslink.app**, titulados
"Objeción a Factura N° HUS…" (archivos `DETALLES_DE_SERVICIOS_FACTURA_HUS*.pdf`).
Para registrar esas objeciones en el sistema de cartera del HUS (Dinámica
Gerencial), el equipo necesita un Excel de cargue con la hoja **OBJECIONES**
en un formato exacto de 16 columnas — el mismo formato del lote que ya se usa
con COOSALUD (`OBJECIONES_LOTE_03_LISTO_sin_HUS512249.xlsx`, 7.869 filas de
269 facturas, cargado con éxito). Transcribir cada PDF a mano es lento y
propenso a errores de digitación de valores y códigos.

**Necesidad cubierta.** Automatizar la conversión PDF de objeción EMSSANAR →
Excel OBJECIONES, con validación contable exacta contra el total del PDF, para
que el equipo de cartera solo tenga que correr un comando y subir el archivo.

**Insumos entregados por el usuario:**
- `OBJECIONES_LOTE_03_LISTO_sin_HUS512249.xlsx` — Excel de referencia (formato
  destino, lote COOSALUD ya aceptado por el sistema).
- `DETALLES_DE_SERVICIOS_FACTURA_HUS0000515948.pdf` — PDF real de EMSSANAR
  (6 páginas) usado como caso de desarrollo y validación.

---

## 2. ARQUITECTURA

### 2.1 Naturaleza del módulo

Es una **herramienta de línea de comandos autónoma** (patrón "bot de tools/"
del repo, igual que `responder_glosas_coosalud.py` o `radicar_facturacion.py`).
**No** es un servicio del motor web: no toca la base de datos, no expone
endpoints, no tiene interfaz gráfica y no usa IA en tiempo de ejecución. Corre
en el PC del auditor (Windows, invocado con `py`) o en cualquier máquina con
Python 3.11+.

### 2.2 Archivos del módulo (los 3 que componen la entrega)

| Archivo | Rol |
|---|---|
| `tools/organizar_objeciones_emssanar.py` | El bot completo (parser + reglas + generador Excel + CLI), ~700 líneas |
| `tools/README_organizar_objeciones_emssanar.md` | Guía de uso y de reglas para el operador |
| `tests/test_tools/test_organizar_objeciones_emssanar.py` | 23 pruebas automáticas (sin dependencia de PDFs binarios) |

Además, como parte de la misma entrega viajan en el PR #162:
- `BITACORA.md` — bitácora central del proyecto (memoria común de chats),
  fusionada con la versión creada en paralelo por otra sesión (ver §13.3).

### 2.3 Estructura interna del script (secciones en orden)

1. Docstring de cabecera con el contrato completo (columnas, reglas, uso).
2. Constantes de layout del PDF: `BANDAS_X`, expresiones regulares.
3. `COLUMNAS_OBJECIONES` — las 16 columnas exactas del formato destino.
4. `CUPS_A_DGH` — tabla de homologación de 145 códigos (dict literal).
5. Importadores perezosos `_exigir_pdfplumber()` / `_exigir_openpyxl()`.
6. Helpers de parseo puro (dinero, factura, código-descripción, texto).
7. Parseo del encabezado de la página 1.
8. Parseo de la tabla "Detalle glosas" (palabras → líneas → registros).
9. Fusión de dobles glosas.
10. Armado de filas OBJECIONES (`CRDOBSERV`, fila de 16 columnas).
11. Procesamiento por PDF (`procesar_pdf`) con validación de suma.
12. Descubrimiento de PDFs (`buscar_pdfs`).
13. Escritura del Excel (`escribir_excel`) con formatos de celda exactos.
14. `main()` — CLI con argparse.

### 2.4 Dependencias

- **pdfplumber** — extracción de palabras con coordenadas del PDF. **Ya estaba
  en `requirements.txt` del proyecto (0.11.5)**; no se agregó dependencia nueva.
- **openpyxl** — escritura del Excel. También preexistente en el proyecto.
- Librería estándar: `argparse, logging, re, sys, unicodedata, collections,
  datetime, pathlib`.
- Ambas dependencias externas se importan de forma **perezosa** con mensaje de
  instalación amable si faltan (mismo patrón del bot COOSALUD con playwright).

### 2.5 APIs / modelos / servicios

No consume APIs externas, no define modelos de base de datos y no registra
servicios en `app/`. Es deliberadamente independiente del motor web para poder
correr en el PC del auditor sin el servidor.

---

## 3. CONOCIMIENTO DE NEGOCIO DESCUBIERTO (ingeniería inversa de los formatos)

Esta sección es el conocimiento más valioso de la entrega: se obtuvo analizando
los dos insumos reales y NO está documentado en ningún otro lugar.

### 3.1 El formato OBJECIONES (Excel de cargue al sistema de cartera)

Derivado del análisis exhaustivo del lote COOSALUD real (7.869 filas):

| # | Columna | Contenido observado en el lote real | Tipo/formato de celda |
|---|---|---|---|
| 1 | `CDCONSEC` | Consecutivo del documento: **uno por factura** (no por fila), asignado en orden de aparición (verificado: factura 1 → "1", … factura 269 → "269"; las 922 filas de HUS0000513221 comparten el "211") | Texto (formato `@`) |
| 2 | `CDFECDOC` | Fecha del documento (en el lote, una única fecha 2026-07-06 para todo el lote) | datetime, formato `mm-dd-yy` |
| 3 | `CRNCXC` | Factura como `HUS` + **10 dígitos con ceros a la izquierda** (`HUS0000511916`) | Texto `@` |
| 4 | `CROFECOBJ` | Fecha de la objeción — igual a CDFECDOC en el lote | datetime `mm-dd-yy` |
| 5 | `CROREFERE` | **Siempre vacía** | `@` |
| 6 | `CROOBSERV` | **Siempre vacía** | `@` |
| 7 | `CROCLAOBJ` | **Siempre 0** | int, formato `General` |
| 8 | `CRNCLAOBJ` | **Siempre vacía** | `@` |
| 9 | `GENUSUARIO4` | **Siempre "999"** (usuario de cargue) | Texto `@` |
| 10 | `CRNCONOBJ` | Código de objeción del Manual Único (`TA2901`, `TA0701`, `AU0202`, `CL0801`, …; 24 códigos distintos en el lote) | Texto `@` |
| 11 | `SLNSERPRO` | Código del servicio/producto **en la nomenclatura del sistema de cartera** (ver §3.3: sufijo `H`) | Texto `@` |
| 12 | `IDRIPS` | **Siempre vacía** | `@` |
| 13 | `CTNCENCOS` | **Siempre vacía** | `@` |
| 14 | `CROVALOBJ` | Valor objetado en pesos, entero | int, formato de miles `_-* #,##0_-;\-* #,##0_-;_-* "-"_-;_-@_-` |
| 15 | `CRDOBSERV` | Observación completa. Estilo: `COD TEXTO (código-descripción)$valor`; cuando una fila agrupa varios códigos, van **separados por salto de línea**, cada uno con su `$valor`. Longitudes reales: mediana 81, p95 244, máximo 1.816 caracteres | Texto `@` |
| 16 | `CROTIPOBJ` | 0 o 2, **constante por factura** (250 facturas en 0, ~19 facturas grandes en 2) | int, formato `0` |

Otros hechos del lote de referencia: 1.009 pares (factura, servicio) se repiten
(duplicados legales, p. ej. el mismo insumo objetado dos veces), y existen
filas multi-código reales (p. ej. `AU0202 …$374200\nTA2901 …$63780` con
`CRNCONOBJ=AU0202` y `CROVALOBJ=374200` — el código y valor de la fila son los
del componente de **mayor valor**).

### 3.2 El PDF de objeción EMSSANAR (reporte de ripslink.app)

- **Encabezado (página 1):** `Objeción a Factura N° HUS515948`, EPS (EMSSANAR
  EPS SAS, NIT 901021565), prestador (ESE HUS, NIT 900006037),
  `Tipo objeción: Glosa`, `Fecha de Objeción: 09-07-2026` (formato DD-MM-AAAA),
  `Valor Bruto`, `Valor Concepto Recaudo`, `Valor Factura: $9.895.000`,
  `Valor Objetado: $2.177.341`.
- **Tabla "Detalle glosas" de 7 columnas:** Tecnología (código - descripción) ·
  Cantidad · Valor Tecnología · Cantidad Objetada · Valor Objetado ·
  Código Objeción (código - texto estándar) · Observación (nota libre de la
  auditora de la EPS).
- **Peculiaridades del layout que obligaron el diseño del parser:**
  - Las celdas **envuelven en varias líneas** (una descripción de hemograma
    ocupó 11 líneas).
  - Los renglones **cruzan páginas** sin repetir encabezado (pág. 2+ arranca
    directo con texto de continuación).
  - Existen renglones donde la tecnología va en una línea y **los números en
    la línea siguiente** (caso `1982214-2 - DEXTROSA`).
  - Un renglón puede traer **dos códigos de objeción apilados**, el segundo sin
    valores propios (caso real: `FMQ3054 - CÁNULA YANKAUER` con `SO0601` y
    debajo `FA0603` sin números).
  - `Cantidad Objetada` puede ser un número (glosa de valor total) o `--`
    (glosa de diferencia tarifaria).
  - Pie de página en cada hoja: `Reporte generado por ripslink.app Impreso: …`
    y `Página N de M`; al final del documento hay un bloque de firmas
    (`Auditor Principal:`, nombre, `Correo:`, `Notificado por:`).
  - La detección automática de tablas de pdfplumber (`extract_tables`) **no
    separa** la columna "Código Objeción" de "Observación" (las une en una
    celda) — por eso se descartó (ver §16 decisiones).

### 3.3 Homologación de códigos: el sufijo "H"

En el sistema de cartera, muchos servicios existen con un **código
institucional con sufijo `H`** (`876802` → `876802H`). El PDF de EMSSANAR trae
CUPS "planos". Del lote COOSALUD real se derivó la tabla `CUPS_A_DGH`:
- 146 códigos aparecieron con `H` como `SLNSERPRO`;
- 6 códigos aparecieron en AMBAS formas (`340401`, `879301`, `881701`,
  `890283`, `895001`, `906841`) — se resolvieron **por mayoría de frecuencia**
  (quedaron con H: 890283H 7-1, 906841H 7-1, 881701H 5-2; quedaron planos:
  879301 7-3, 895001 y 340401 por mayoría/empate);
- resultado final: **145 entradas** plano → H en el dict `CUPS_A_DGH`.
- Los medicamentos (códigos tipo `19931880-02`, `32606-01`) y los insumos
  (`FMQ0923`, `FMQ0169-3`) van **tal cual** — nunca llevan H en el lote real.
- Verificación puntual: TODOS los códigos presentes en el PDF de prueba
  (890701, 902045, 898201, 902049, 902210, 903813, 903603, 903839, 903854,
  903859, 903864, 906913, etc.) están confirmados **planos** en el lote real,
  así que para esta factura la homologación no altera nada — la tabla protege
  PDFs futuros.

### 3.4 La regla de la "doble glosa" (hallazgo contable clave)

Al sumar los 40 renglones del PDF de prueba se obtienen **$2.245.341**, pero el
encabezado dice **$2.177.341**. La diferencia, **$68.000 exactos**, se explica
así: cuando la EPS objeta el mismo servicio con (a) una glosa de **valor
total** (Cantidad Objetada numérica) y (b) una de **diferencia tarifaria**
(`--`), su total **solo cuenta la mayor**. En la factura de prueba:
- `890701` (consulta urgencias): TA0201 $24.800 (`--`) + FA0205 $114.900 (1)
  → el total solo cuenta $114.900 (excluye $24.800);
- `906913` (proteína C reactiva, 5 renglones): 3×TA0801 $21.600 (`--`) +
  2×CL0801 $98.600 (1) → excluye 2×$21.600.
- $24.800 + $21.600 + $21.600 = **$68.000** ✓ (cuadra al peso).

Esto coincide con las filas multi-código del lote COOSALUD (§3.1), así que el
bot **fusiona** esas parejas. Sin la fusión, el Excel inflaría la cartera en
$68.000 respecto de lo que la EPS radicó.

### 3.5 CROTIPOBJ: hipótesis documentada

En el lote COOSALUD, `CROTIPOBJ` es constante por factura (0 o 2) y las
facturas en 2 son pocas pero enormes (900+ filas). El PDF de EMSSANAR declara
`Tipo objeción: Glosa`. **Hipótesis adoptada (y documentada como supuesto):**
0 = Glosa, 2 = Devolución. El bot lo deriva del encabezado del PDF (busca
"devolu" en el tipo, sin tildes) y permite forzarlo con `--tipobj {0,2}`.
**Queda pendiente confirmarlo con un cargue real** (§15).

---

## 4. FUNCIONES IMPLEMENTADAS (lista completa)

Todas en `tools/organizar_objeciones_emssanar.py` salvo indicación.

| Función | Qué hace / cómo / por qué |
|---|---|
| `parsear_dinero(texto)` | `'$114.900'` → `114900`. Solo acepta celdas que empiezan con `$` (regex `RE_DINERO`); delega en `_a_entero`. Existe porque los valores del PDF traen separador de miles con punto. |
| `_a_entero(texto)` | Convierte cifra con miles/decimales a entero de pesos, distinguiendo **coma decimal** (`'$1.365,50'` → 1365, no 136550). Se agregó en la corrección post-verificación adversarial (commit `5cc1a34`): si los centavos se trataran como miles, encabezado y renglones se inflarían ×100 y la validación de suma NO lo detectaría (se inflan igual ambos lados). |
| `normalizar_factura(cruda)` | `'HUS515948'`/`'HUS 515948'`/`'hus…'` → `'HUS0000515948'` (prefijo alfabético + número a 10 dígitos). Formato exigido por `CRNCXC` (verificado contra el lote real). |
| `separar_codigo_descripcion(texto)` | Divide `'890701 - CONSULTA…'` en (código, descripción) partiendo por `' - '` (espacio-guion-espacio) para no romper códigos con guion interno (`32606-01`). |
| `homologar_servicio(codigo, aplicar_sufijo_h)` | Aplica la tabla `CUPS_A_DGH` (145 entradas, §3.3); si el código no está, lo devuelve tal cual. Con `aplicar_sufijo_h=False` (flag `--sin-sufijo-h`) no toca nada. |
| `_limpiar_texto(palabras)` | Une lista de palabras y colapsa espacios. |
| `parsear_encabezado(texto_pagina1)` | Extrae con regex: factura (normalizada), tipo de objeción, fecha (DD-MM-AAAA → datetime), valor factura y valor objetado del bloque superior de la página 1. Tolerante a tildes y variantes N°/Nº. |
| `tipobj_desde_encabezado(tipo)` | `'Glosa'` → 0, `'Devolución'/'DEVOLUCION'` → 2 (normaliza tildes con `unicodedata`). |
| `_columna_de(palabra)` | Asigna una palabra a una de las 7 columnas según el **centro** de su caja X contra `BANDAS_X = (140, 180, 272, 320, 395, 588)`. Centro y no borde: una palabra larga pegada al límite no se cae a la columna siguiente. Bandas calibradas midiendo las coordenadas reales del PDF de prueba. |
| `_lineas_de_pagina(page)` | Agrupa `page.extract_words()` en líneas visuales por coordenada `top` redondeada, ordenadas por X. |
| `_nuevo_registro()` | Estructura cruda de un renglón: tecnología, cantidad, valor tecnología, cantidad objetada, valor objetado, componentes. |
| `extraer_registros(pdf)` | **Corazón del parser.** Recorre todas las páginas: detecta y salta el encabezado de la tabla (línea con "Código" y "Observación", + 13pt de margen que cubre la segunda línea del encabezado), salta pies de página (`RE_PIE_PAGINA`), corta en el bloque de firmas (`Auditor Principal`/`Notificado por`/`Correo:`). Un registro NUEVO inicia cuando la columna Tecnología trae `CÓDIGO -` (primer token cumple `RE_CODIGO_TEC` y el segundo es `-`). Los valores numéricos se toman en su **primera aparición** dentro del registro (cubre el caso DEXTROSA con números en la línea siguiente). Dentro del registro, un **componente** nuevo de objeción inicia cuando la columna Código trae `XX9999 -` (`RE_CODIGO_OBJ`) — así los códigos apilados quedan separados con sus textos y observaciones correctamente ruteados. Los registros continúan a través de saltos de página de forma natural. |
| `consolidar_registro(reg)` | Registro crudo → renglón limpio: separa código/descripción de la tecnología y de cada componente, limpia textos. |
| `fusionar_dobles_glosas(renglones)` | Implementa la regla §3.4: agrupa por código de tecnología; empareja **en orden del documento** cada renglón de valor total (cantidad objetada numérica) con uno de diferencia (`--`), 1 a 1 con `zip(strict=False)` (los sobrantes quedan como filas propias — caso 906913: 3 diffs y 2 totales → 2 fusiones + 1 fila sola). El renglón resultante conserva código/valor del total (siempre el mayor) y adjunta los absorbidos en `renglon["fusionados"]`. Nunca fusiona dos `--` entre sí ni dos totales entre sí, ni cruza tecnologías distintas. |
| `_texto_componente(comp, tec_codigo, tec_desc, valor)` | Un componente → `'COD TEXTO ESTÁNDAR (código-descripción): NOTA DE LA AUDITORA$valor'`, todo en MAYÚSCULAS (estilo del lote COOSALUD). El `$valor` solo va cuando el componente lo tiene. |
| `armar_crdobserv(renglon)` | Concatena con `\n`: componente principal (con el valor del renglón) + componentes apilados sin valor + los renglones fusionados (cada uno con su propio `$valor`). Reproduce exactamente el estilo multi-código del lote real. |
| `renglon_a_fila(renglon, consec, factura, fecha, usuario, tipobj, aplicar_sufijo_h)` | Renglón → dict con las 16 columnas: CDCONSEC como texto, fechas datetime, vacíos en las 5 columnas siempre-vacías, CROCLAOBJ=0, CRNCONOBJ del componente principal, SLNSERPRO homologado, CROVALOBJ entero, CRDOBSERV armado, CROTIPOBJ. |
| `procesar_pdf(ruta, aplicar_sufijo_h)` | Pipeline de un PDF: abrir con pdfplumber → encabezado → registros → consolidar → avisar renglones incompletos (log) → fusionar → **validar**: suma de valores vs `Valor Objetado` del encabezado. Devuelve `{"encabezado", "renglones", "suma", "cuadra"}`. |
| `buscar_pdfs(rutas)` | Expande archivos y carpetas (recursivo `DETALLES_DE_SERVICIOS_FACTURA_*.pdf` y `.PDF`), deduplica rutas preservando orden, avisa rutas inexistentes. |
| `escribir_excel(filas, salida)` | Crea el libro con hoja **OBJECIONES**, encabezados exactos y **formatos de celda idénticos al lote real** (§3.1): `@` texto, `mm-dd-yy` fechas, `General` CROCLAOBJ, formato de miles CROVALOBJ, `0` CROTIPOBJ. Crea carpetas de salida si no existen. |
| `main(argv)` | CLI completo: parseo de flags, fecha forzada (`--fecha DD-MM-AAAA` con validación), descubrimiento de PDFs, procesamiento con manejo de excepciones por PDF (`✗ … no se pudo parsear`), log por factura `✓/⚠ … suma $X vs encabezado $Y → OK/NO CUADRA`, `--estricto` descarta las que no cuadran, **deduplicación por factura** (si el mismo PDF está en dos carpetas se toma el primero, con aviso), orden por número de factura (como el lote real), CDCONSEC desde `--consec-inicial`, fecha por PDF o forzada, CROTIPOBJ por PDF o forzado, escritura y resumen final. Código de salida: 0 limpio, 1 si hubo PDFs con problemas, 2 errores de invocación. |

**Helpers de pruebas** (en el archivo de tests): `PaginaFalsa` y `PdfFalso`
(duck typing de `pdfplumber.Page`/PDF — solo `extract_words()` y `.pages`),
`_linea()/_w()` para fabricar palabras con coordenadas, `X_COLS` con centros
representativos de cada columna.

---

## 5. FLUJO COMPLETO (paso a paso)

1. **El operador ejecuta** `py tools\organizar_objeciones_emssanar.py --pdf <carpeta o PDFs> [--salida … --consec-inicial … --fecha … --usuario … --tipobj … --sin-sufijo-h --estricto]`.
2. `main()` valida `--fecha` (si viene) y llama `buscar_pdfs()`: carpetas se
   expanden recursivamente al patrón `DETALLES_DE_SERVICIOS_FACTURA_*.pdf`,
   archivos sueltos se toman tal cual, sin duplicados.
3. **Por cada PDF**, `procesar_pdf()`:
   a. Extrae el texto de la página 1 y `parsear_encabezado()` obtiene factura,
      tipo, fecha, valor factura y valor objetado.
   b. `extraer_registros()` recorre página por página: agrupa palabras en
      líneas; salta encabezados de tabla, pies de página y bloque de firmas;
      abre registro nuevo al ver `CÓDIGO -` en la columna Tecnología; acumula
      texto por columna; abre componente nuevo al ver `XX9999 -` en la columna
      Código; captura la primera aparición de cada número.
   c. `consolidar_registro()` limpia cada registro.
   d. Se registran en el log los renglones incompletos (sin valor o sin código).
   e. `fusionar_dobles_glosas()` aplica la regla §3.4.
   f. Se suma `valor_objetado` de los renglones finales y se compara con el
      encabezado → `cuadra: True/False`.
4. En consola queda una línea por factura: `✓ HUS0000515948: 37 renglones,
   suma $2,177,341 vs encabezado $2,177,341 → OK` (o `⚠ … NO CUADRA`). Con
   `--estricto`, las que no cuadran se excluyen del Excel.
5. Se **deduplican facturas repetidas** (mismo PDF en dos carpetas → aviso y
   se ignora el duplicado).
6. Se ordenan los resultados por número de factura ascendente y se asigna
   `CDCONSEC` consecutivo desde `--consec-inicial` (default 1), uno por factura.
7. Por cada renglón se arma la fila de 16 columnas (`renglon_a_fila`), con la
   fecha del PDF (o la forzada) en CDFECDOC/CROFECOBJ y el CROTIPOBJ derivado
   del tipo del PDF (o el forzado).
8. `escribir_excel()` genera la hoja OBJECIONES con los formatos exactos.
9. Resumen final en consola: ruta del Excel, filas, facturas, total objetado.
   Exit code 1 si algún PDF tuvo problemas (para que un script llamador lo
   detecte).

**Resultado validado con el PDF real:** 40 renglones del PDF → **37 filas**
(3 fusiones), suma **$2.177.341 == encabezado, al peso**.

---

## 6. BASE DE DATOS

**No aplica.** El módulo no crea tablas, no ejecuta migraciones y no lee ni
escribe la base de datos del motor. Su única "base de datos" es la tabla
estática `CUPS_A_DGH` (dict de 145 entradas embebido en el script, §3.3),
derivada del Excel real del lote COOSALUD. El Excel que produce es el que
luego un humano carga al sistema de cartera (Dinámica Gerencial) — ese cargue
está fuera del alcance de este módulo.

## 7. BACKEND

**No aplica** (sin endpoints, controladores, middleware ni permisos). Las
validaciones y el manejo de errores viven en la CLI:
- Validación contable por PDF (suma vs encabezado) con aviso `NO CUADRA` y
  exit code 1; `--estricto` excluye.
- PDFs no parseables: capturados por PDF (no tumban el lote), log `✗`.
- `--fecha` malformada → mensaje y exit code 2. Sin PDFs → exit code 2.
- Dependencias ausentes → mensaje de instalación y exit code 2.
- Renglones incompletos → warning en log con factura y tecnología.

## 8. FRONTEND

**No aplica.** Sin pantallas, componentes ni modales. La "interfaz" es la
consola (logs con ✓/⚠/✗ y resumen final) y el Excel generado.

## 9. IA

**El módulo NO usa IA en tiempo de ejecución** — es 100 % determinista (regex
+ geometría de coordenadas + reglas contables). Esto fue deliberado: el
resultado debe ser reproducible y auditable al peso.

**IA usada durante el desarrollo** (proceso, no producto):
- El desarrollo corrió en Claude Code con modo "ultracode"; antes de publicar
  se lanzó un **workflow de verificación adversarial con 3 agentes
  independientes en paralelo**: (1) verificación de DATOS fila por fila
  (re-extrajo el PDF con método independiente y comparó contra el Excel
  generado), (2) revisión adversarial del CÓDIGO buscando casos límite,
  (3) fidelidad de FORMATO contra el Excel del lote real (tipos, formatos de
  celda, columnas vacías).
- Producto de esa verificación: el commit `5cc1a34` — "Corregir 4 casos límite
  del parser EMSSANAR hallados en verificación adversarial" — que entre otras
  cosas introdujo `_a_entero()` con manejo de **coma decimal** (el caso
  '$1.365,50', §4) y ajustó el README (el proceso termina con exit code 1
  cuando una factura no cuadra, aunque igual la incluye salvo `--estricto`),
  y elevó los tests de 19 a 23.

## 10. AUTOMATIZACIONES

1. **CI de GitHub Actions** (preexistente, aplica al PR): job Lint
   (`ruff check . --select F,W6` + `ruff format --check .`, con ruff SIN
   versión fijada — ver riesgo §13.2), job Tests (pytest, ~4.100 pruebas,
   con `SECRET_KEY`, `DATABASE_URL=sqlite`, `PYTHONPATH`,
   `DISABLE_SCHEDULERS=1`), job Security scan (pip-audit).
2. **Vigilancia del PR #162**: la sesión quedó suscrita a los eventos del PR
   (fallas de CI y comentarios llegan como eventos y se atienden). Se usaron
   además chequeos programados (~1 hora) para verificar estados que los
   eventos no notifican (CI en verde, mergeabilidad); **el usuario canceló los
   chequeos programados el 22-jul** — la suscripción a eventos sigue activa.
3. **La bitácora** (`BITACORA.md` + instrucción en `CLAUDE.md`): toda sesión
   de Claude Code debe leerla al iniciar y actualizarla al terminar. Es una
   automatización de proceso, no de código.

## 11. ARCHIVOS MODIFICADOS (lista completa, por commit de esta rama)

| Commit | Archivo | Cambio exacto |
|---|---|---|
| `550775e` | `tools/organizar_objeciones_emssanar.py` | **Nuevo.** El bot completo. |
| `550775e` | `tools/README_organizar_objeciones_emssanar.md` | **Nuevo.** Guía de uso. |
| `550775e` | `tests/test_tools/test_organizar_objeciones_emssanar.py` | **Nuevo.** 19 tests. |
| `5cc1a34` | los 3 anteriores | 4 casos límite de la verificación adversarial: `_a_entero` + coma decimal (con test que documenta por qué la validación de suma no detectaría la inflación ×100), ajustes de README (exit code en NO CUADRA), tests 19→23. |
| `a24cc5a` | `tests/test_api/test_import_history.py` | Un solo carácter: newline final que exigía ruff 0.15.21 (falla de CI ajena a la rama, ver §13.2). |
| `21f991a` | `BITACORA.md`, `CLAUDE.md` | **Nuevos** (luego reemplazados/fusionados en el merge, ver §13.3). |
| `5d2d8ab` | `tests/test_api/test_por_dia_semana.py`, `tests/test_api/test_heatmap_actividad.py`, `BITACORA.md` | Desactivación de la "bomba de tiempo": fechas fijas de abril → helper `_ultimo(día_semana)` con fechas relativas (última ocurrencia PASADA del día, 1–7 días atrás). Bitácora actualizada. |
| `454b03c` (merge) | — | Merge de `origin/motor-glosas`: se tomó la versión de la base para `CLAUDE.md` y los 2 tests de estadísticas (otra sesión aplicó el mismo fix con helper `_lunes_reciente()`, commit `0b358d8` de la base); `BITACORA.md` se fusionó (base de la otra sesión + entradas EMSSANAR de esta). |

**Diff neto final del PR #162** (tras el merge): 4 archivos, +1560/−1 — el
bot, su README, sus tests y la BITACORA.md fusionada. `CLAUDE.md` y los tests
de estadísticas quedaron idénticos a la base (salieron del diff).

## 12. DEPENDENCIAS NUEVAS Y CONFIGURACIÓN

**Dependencias nuevas del proyecto: NINGUNA.** `pdfplumber==0.11.5` y openpyxl
ya estaban en `requirements.txt`.

En el entorno de desarrollo de la sesión (efímero, no afecta el repo) se
instalaron para trabajar: openpyxl 3.1.5, pdfplumber 0.11.10 (+ cffi, que
faltaba para pdfminer), pytest, ruff==0.15.21 (la misma del CI), y el grueso
de requirements.txt (dos paquetes no compilaron localmente y se excluyeron
solo del entorno local: http-ece, sgmllib3k).

**Variables de entorno del módulo: ninguna.** Todo se pasa por flags de CLI
(`--pdf, --salida, --consec-inicial, --fecha, --usuario, --tipobj,
--sin-sufijo-h, --estricto`). Sin tokens ni credenciales: el bot no toca
ningún portal.

**Parámetros internos calibrados** (constantes del script):
`BANDAS_X = (140, 180, 272, 320, 395, 588)` (límites de columnas, en puntos
PDF); regex `RE_CODIGO_TEC = ^[A-Z]{0,3}\d[\dA-Z.\-]*$` (acepta 890701,
32606-01, FMQ0923, 129A02), `RE_CODIGO_OBJ = ^[A-Z]{2}\d{4}$`,
`RE_DINERO = ^\$[\d.,]+$`; margen de +13pt bajo el encabezado de tabla;
defaults GENUSUARIO4="999", consecutivo inicial 1.

## 13. RIESGOS E INCIDENTES CONOCIDOS

### 13.1 Riesgos del módulo al integrarlo
1. **Cambio de layout de ripslink.** Si EMSSANAR cambia el diseño del reporte,
   las bandas X pueden dejar de corresponder. **Mitigación ya integrada:** la
   validación de suma contra el encabezado destapa el problema de inmediato
   (NO CUADRA / renglones incompletos en el log); no hay fallas silenciosas.
2. **Supuestos sin confirmar con un cargue real** (§15): tabla de sufijos H y
   semántica de CROTIPOBJ (0/2). Ambos documentados y con escape (`--sin-sufijo-h`,
   `--tipobj`).
3. **Riesgo residual del detector de inicio de registro:** una descripción de
   insumo que envuelva justo como `REF 989803179041 -` al inicio de línea de
   la columna Tecnología podría confundirse con un inicio de registro. Se
   evaluó en diseño y se aceptó porque el checksum lo delataría; no se observó
   en el PDF real.
4. **Coma decimal:** cubierta por `_a_entero` — era el riesgo más peligroso
   porque inflaba renglones y encabezado por igual (indetectable por checksum).

### 13.2 Incidente CI #1 — ruff sin versión fijada (resuelto)
El job Lint instala `pip install ruff` **sin pin**; al salir ruff 0.15.21
empezó a exigir newline final en `tests/test_api/test_import_history.py`
(archivo preexistente) y rompió el lint de TODAS las ramas. Se arregló en
`a24cc5a` (un carácter). **Recomendación al equipo principal: fijar la versión
de ruff en el CI** para que una release nueva no vuelva a frenar el trabajo.

### 13.3 Incidente CI #2 — tests "bomba de tiempo" y desarrollo paralelo (resuelto)
El 22-jul fallaron 3 tests de estadísticas (`test_por_dia_semana`,
`test_heatmap_actividad`): sembraban glosas en fechas fijas de abril-2026 y
los endpoints filtran por ventana móvil de 90 días — el 19/20-jul los datos
caducaron y el CI de cualquier rama quedó rojo (4.102 pasaban, 3 fallaban).
Esta sesión lo arregló (`5d2d8ab`, fechas relativas); **otra sesión de Claude
en paralelo aplicó el mismo arreglo a la base** (`0b358d8`) y además creó su
propia BITACORA.md/CLAUDE.md (PR #179) y mergeó la ronda 31 (PR #180). Eso
volvió el PR #162 conflictivo ("dirty"). Resolución en el merge `454b03c`:
tests y CLAUDE.md → versión de la base; BITACORA.md → la de la base (más
completa: cubre desde abril con las cifras de la operación SIMED) **enriquecida
con el contenido EMSSANAR que solo existía en esta rama** (entrada 15-jul,
entrada 22-jul, PENDIENTE #8, PARA MAÑANA #5). **Lección para la
consolidación:** cuando varios chats trabajan a la vez, los archivos
compartidos (bitácora, tests comunes) chocan; la bitácora única y esta
documentación existen precisamente para eso.

### 13.4 Otros hechos operativos de la sesión
- El reloj del contenedor de la sesión quedó atrasado ~6 días tras una
  dormancia larga (decía 16-jul cuando GitHub registraba 22-jul). Para fechas
  se tomó como autoritativo GitHub/CI. Tenerlo presente al leer fechas de
  commits de la rama (algunos quedaron fechados 15/16-jul).
- El PDF de prueba y el Excel de ejemplo se procesaron desde los archivos
  subidos por el usuario; el Excel generado de la factura HUS0000515948 quedó
  en el scratchpad de la sesión (efímero) — regenerable en segundos con el bot.

## 14. DEPENDENCIAS CON OTROS MÓDULOS

- **No depende de ningún módulo del motor** (`app/`): ni de
  `homologador_cups.py` (ese homologa en la dirección contraria: código
  institucional → CUPS oficial de la Res. 2641/2025; se revisó y se descartó
  reutilizarlo), ni de `exportar_dgh.py` (ese produce OTRO formato: el Excel
  de RESPUESTA de 26 columnas `EstadoCxCObjecion…OBSERVACION`; no confundir
  los dos formatos).
- **Quién lo usa:** el flujo operativo de cartera. El Excel OBJECIONES que
  produce es el insumo del cargue de objeciones al sistema de cartera; aguas
  abajo, las objeciones registradas alimentan el flujo de respuesta
  (motor de dictámenes / bot DGH / COOSALUD según entidad).
- **Relación conceptual con COOSALUD:** el lote OBJECIONES de COOSALUD fue el
  contrato de formato (se replicó columna a columna, formato de celda a
  formato de celda). `tools/responder_glosas_coosalud.py` sirvió como
  referencia de convenciones de código del repo (docstring de cabecera,
  imports perezosos, logging, argparse).

## 15. PENDIENTES (exactos, también registrados en BITACORA.md)

1. **Aprobar y unir el PR #162** (quedó en borrador con CI en verde tras el
   merge `454b03c`; al cierre de esta entrega el CI del commit de merge estaba
   corriendo — verificar verde antes de unir).
2. **Cargue de prueba del Excel en el sistema de cartera** con la factura
   HUS0000515948 para confirmar los DOS supuestos documentados: sufijos H
   (§3.3) y CROTIPOBJ 0/2 (§3.5). Si el sistema rechaza códigos → agregarlos a
   `CUPS_A_DGH` (o correr con `--sin-sufijo-h` y corregir a mano).
3. **Correr el lote completo** de PDFs de EMSSANAR del mes (solo se procesó la
   factura de muestra) y revisar que cada una cuadre con su encabezado.
4. Mejora prevista no implementada: recalibración automática de `BANDAS_X`
   desde el encabezado de la tabla (se descartó por riesgo de recorte de
   palabras largas; ver §16-D3). Si ripslink cambia el layout, recalibrar las
   bandas midiendo el nuevo PDF, como se hizo en esta entrega.
5. No hay errores conocidos sin resolver en el módulo a la fecha de entrega.

## 16. DECISIONES TÉCNICAS Y SOLUCIONES DESCARTADAS

- **D1. Parser por bandas X de palabras, no `extract_tables`.** La detección
  automática de tablas de pdfplumber une "Código Objeción" con "Observación"
  (no ve la línea divisoria) y mezcla filas envueltas. Se descartó y se
  construyó el parser geométrico (palabra → columna por centro X).
- **D2. Asignación por CENTRO de palabra, no por borde izquierdo**, para que
  palabras largas pegadas al límite no se caigan de columna.
- **D3. Bandas X FIJAS calibradas + validación por checksum, en vez de
  derivarlas dinámicamente del encabezado.** Se evaluó calcular los límites
  como puntos medios entre palabras del encabezado; se descartó porque el
  midpoint entre "Tecnología" y "Cantidad" (~113pt) recortaba palabras reales
  de datos (~115pt). La pareja "bandas fijas + suma que debe cuadrar" es más
  robusta: cualquier desvío de layout truena la validación en vez de fallar
  en silencio.
- **D4. Detección de inicio de registro** = primer token de la columna
  Tecnología cumple el patrón de código Y el segundo token es exactamente
  `-`. Necesario porque hay registros cuyos números vienen en la línea
  siguiente (DEXTROSA) — no se puede exigir "línea con números".
- **D5. Fusión de dobles glosas** (§3.4). Alternativa descartada: una fila
  por renglón del PDF sin fusionar — inflaba el total en $68.000 contra lo
  radicado por la EPS y contradecía el estilo multi-código del lote COOSALUD.
- **D6. Homologación H embebida y derivada de datos reales** (lote cargado con
  éxito), en vez de reutilizar `homologador_cups.py` (dirección contraria) o
  de omitirla (los PDFs futuros con servicios tipo 876802 fallarían el cargue).
  Ambigüedades resueltas por mayoría de frecuencia; apagable por flag.
- **D7. Sin IA en runtime** — determinismo y auditabilidad al peso.
- **D8. Tests con página falsa (duck typing)** en vez de PDFs binarios de
  fixture: más rápidos, legibles y no requieren adjuntar PDFs con datos de
  pacientes al repo.
- **D9. Formatos de celda replicados exactamente** del lote real (texto `@`,
  fechas `mm-dd-yy`, miles contables) para minimizar el riesgo de rechazo del
  importador del sistema de cartera.
- **D10. En el conflicto con la base (§13.3)** se prefirió la versión de la
  base para los archivos duplicados (tests, CLAUDE.md, estructura de la
  bitácora) y se conservó SOLO el contenido único de esta rama — criterio:
  minimizar el diff del PR y no duplicar arreglos equivalentes.

## 17. RECOMENDACIONES PARA FUSIONARLO EN EL PROYECTO PRINCIPAL

1. **Verificar CI en verde** del commit de merge `454b03c` en el PR #162
   (Lint + Tests + Security scan).
2. **Sacar el PR de borrador y unirlo** a `motor-glosas`. El diff es acotado
   (4 archivos) y ya está al día con la base — no hay conflictos pendientes.
3. **No renombrar ni mover** `tools/organizar_objeciones_emssanar.py` sin
   actualizar: el test (importa por ruta `tools/`), el README y la BITACORA.
4. Tras el merge, correr el **cargue de prueba** (§15.2) y, según el
   resultado, ajustar `CUPS_A_DGH` (es un dict literal — agregar/quitar
   entradas es trivial y hay test de la homologación).
5. Si el proyecto principal consolida varios repos: este módulo es
   autosuficiente (script + README + tests); llevarse también §3 de este
   documento (el conocimiento de formatos NO vive en el código del sistema de
   cartera, que es de terceros).
6. **Fijar la versión de ruff en el CI** (§13.2) para eliminar esa clase de
   rupturas.
7. Mantener el hábito de la **BITACORA.md** (leerla al abrir sesión,
   actualizarla al cerrar): es el mecanismo anti-pérdida de conocimiento entre
   chats que motivó esta misma entrega, y ya demostró su valor al fusionar el
   trabajo de dos sesiones paralelas.

## 18. RESUMEN EJECUTIVO (para el desarrollador que lo mantenga)

`tools/organizar_objeciones_emssanar.py` convierte los PDFs de objeción de
EMSSANAR (ripslink.app) en el Excel OBJECIONES de 16 columnas que se carga al
sistema de cartera del HUS, replicando al detalle el formato del lote COOSALUD
que ya funciona. Es un script determinista sin IA, sin base de datos y sin
dependencias nuevas (pdfplumber + openpyxl, ya en requirements). Sus tres
piezas de lógica no obvias son: (1) el **parser geométrico** por bandas X con
detección de registros `CÓDIGO -` (las celdas envuelven, cruzan páginas y a
veces los números vienen en la línea siguiente); (2) la **fusión de dobles
glosas** — cuando la EPS objeta el mismo servicio por valor total y por
diferencia tarifaria, solo cuenta la mayor (sin esto el total infla $68.000 en
la factura de prueba); (3) la **homologación de sufijos H** (tabla de 145
códigos derivada del lote real). Su red de seguridad es contable: la suma de
cada factura DEBE cuadrar al peso con el "Valor Objetado" del encabezado del
PDF (verificado: $2.177.341 en la factura HUS0000515948, 40 renglones → 37
filas); si no cuadra, avisa fuerte y sale con código 1. Tiene 23 tests que no
necesitan PDFs binarios (página falsa por duck typing). Antes de darlo por
cerrado falta una sola cosa de fondo: un cargue real que confirme los sufijos
H y el campo CROTIPOBJ (0=Glosa, 2=Devolución — hipótesis derivada de datos,
forzable por flag). Todo lo demás — decisiones, descartes, incidentes de CI y
el conflicto resuelto con la sesión paralela — está en este documento y en
`BITACORA.md`.
