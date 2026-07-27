# Documentación oficial del módulo — Kit de Bots de Auditoría HUS

> **Documento de entrega al equipo principal.**
> Autor de la entrega: desarrollador líder del módulo.
> Rama de desarrollo: `claude/powershell-pdf-cmd-bot-3iaihn` · Pull Request **#156**.
> Repositorio: `yesidbadillo820-ship-it/motor-glosas-hus`.
> Alcance temporal reconstruido en este documento: **15 → 22 de julio de 2026**
> (la conversación de desarrollo de esta rama paralela).
> Fecha de emisión: 2026-07-22.

Este documento reconstruye **todo** lo trabajado en esta línea de desarrollo, sin
resumir ni omitir. Cuando una sección del índice no aplica al módulo (por
ejemplo *Frontend* o *IA en tiempo de ejecución*), se dice explícitamente **por
qué** no aplica, en vez de inventar contenido.

---

## 0. Nota de encuadre: qué es este módulo dentro del proyecto grande

El proyecto principal `motor-glosas-hus` es una aplicación web (backend FastAPI +
base de datos SQLAlchemy) para la gestión de glosas del Hospital Universitario de
Santander (HUS). **Este módulo NO es esa aplicación web.**

Este módulo es el **Kit de Bots de Auditoría HUS**: un conjunto de programas de
**doble clic** (`tools/*.cmd`) que el auditor ejecuta en su propio PC con Windows,
sin instalar nada ni saber programar. Viven en la carpeta `tools/` del mismo
repositorio y son **autónomos**: no dependen del servidor web, no consultan la
base de datos, no exponen ni consumen HTTP. Su “interfaz” es la ventana negra de
la consola de Windows y su “salida” son archivos (Excel, CSV, PDF, TXT) que quedan
junto al `.cmd`.

La única intersección con la app web ocurrió el 22 de julio, cuando esta rama
tuvo que **corregir dos pruebas del backend** (`tests/test_api/`) que hacían fallar
el CI del PR. Ese arreglo se documenta en las secciones 5 y 6.

---

## 1. Objetivo del desarrollo

### ¿Por qué se creó este módulo?

El área de **auditoría de cuentas del HUS** pelea a diario las **glosas** (objeciones
de pago) y **devoluciones** de las EPS, sobre todo **Nueva EPS**. El personal es
**auditor, no de sistemas**: no puede usar herramientas que exijan instalar
dependencias, abrir terminales o escribir comandos. Al mismo tiempo, el trabajo
manual (buscar soportes en carpetas de red enormes, cruzar RIPS contra soportes
factura por factura, controlar plazos legales) es **lento, repetitivo y propenso a
errores** que se traducen en dinero perdido (glosas aceptadas por vencimiento o por
no encontrar la evidencia a tiempo).

### ¿Qué problema resolvía?

- **Prevenir la glosa antes de radicar** (revisar contratos, FURIPS y soportes).
- **Responder la glosa con evidencia** cuando ya llegó (cruzar el Excel de la EPS
  con los XML radicados y generar borradores por causal).
- **No perder glosas por extemporaneidad** (control de plazos en días hábiles).
- **Armar el paquete de soportes en minutos** en vez de horas.
- **Auditar las devoluciones de Nueva EPS** cruzando tres fuentes (factura DGH,
  RIPS-JSON y soportes OPF/PDE) y dejando el hallazgo por escrito.
- **Preparar/convertir archivos** para las plataformas (TXT↔Excel↔CSV, unir/partir
  /comprimir PDF y ZIP).
- **Dejar trazabilidad de gestión** (bitácora de uso e informe para gerencia).

### ¿Qué necesidad cubría?

Convertir tareas de auditor experto (pero manuales) en **un doble clic reproducible**,
respetando dos reglas de oro del negocio:
1. **Nunca tocar el archivo original** del usuario (siempre se escribe una copia).
2. **Un archivo dañado no detiene el resto**: se reporta y se continúa.

---

## 2. Arquitectura

### 2.1 Estructura del módulo

Todo vive en dos carpetas del repo:

```
tools/                      # los bots y sus motores
  MOTOR_HUS.cmd             # menú central (1 doble clic → lista numerada)
  <NOMBRE>.cmd             # cada bot: lanzador batch + motor Python EMBEBIDO
  <nombre>.py              # el motor Python “fuente” de cada bot
  README_<NOMBRE>.md       # guía para el usuario final (auditor)
  README_KIT_AUDITORIA.md  # guía global del kit
  REGISTRO_BOTS.csv        # bitácora de uso (la genera el menú al ejecutarse)
tests/test_tools/          # pruebas automáticas de los bots (pytest)
docs/                      # documentación (incluye este archivo)
BITACORA.md                # memoria común entre chats (creada 22-jul)
CLAUDE.md                  # instrucciones que todo chat lee al iniciar
```

### 2.2 Componente clave: el “polyglot” `.cmd`

Cada bot es **un solo archivo `.cmd`** que Windows puede ejecutar con doble clic y
que a la vez contiene el motor Python **embebido**. Estructura interna:

```
@echo off                       ┐
REM ... cabecera batch 100% ASCII │  Sección BATCH (lanzador):
chcp 65001 ...                    │   - busca/instala Python
... detecta Python ...            │   - instala dependencias (pip --user)
... instala dependencias ...      │   - pide rutas al usuario
... pide rutas ...                │   - extrae el motor a %TEMP% y lo ejecuta
%PYEXE% "%MOTOR%" ...             ┘
#PYSTART#                        ← MARCADOR (aparece EXACTAMENTE una vez)
"""motor Python...               ┐  Sección MOTOR (Python):
def ...                           │   - copia byte a byte de tools/<nombre>.py
...                               ┘
```

- El batch localiza el marcador con PowerShell y vuelca todo lo que hay **después**
  a un archivo temporal (`%TEMP%\..._hus.py`) que ejecuta. Si el `.py` viaja
  suelto junto al `.cmd`, lo usa directo (fallback).
- **Regla de ensamblado** (la verifican las pruebas):
  `full = (cabecera + motor)` con normalización de saltos de línea
  `.replace("\r\n","\n").replace("\n","\r\n")` → **todo CRLF**. La sección batch
  debe ser **100 % ASCII** (Windows batch no tolera UTF‑8 en la parte de comandos).
  El motor embebido debe quedar **byte a byte idéntico** al `.py` fuente.

### 2.3 Carpetas / archivos por bot (de esta conversación)

| Bot (.cmd) | Motor (.py) | README | Fecha |
|---|---|---|---|
| `REVISAR_XML.cmd` | `revisar_xml_facturas.py` | `README_REVISAR_XML.md` | 15-jul |
| `TXT_A_EXCEL.cmd` | `txt_a_excel.py` | `README_TXT_A_EXCEL.md` | 16-jul |
| `VERIFICAR_RADICACION.cmd` | `verificar_radicacion.py` | (en README_KIT) | 16-jul |
| `CRUZAR_GLOSAS.cmd` | `cruzar_glosas_xml.py` | (en README_KIT) | 16-jul |
| `SEMAFORO_GLOSAS.cmd` | `semaforo_vencimientos.py` | (en README_KIT) | 16-jul |
| `BUSCAR_FACTURA.cmd` | `buscar_facturas.py` | (en README_KIT) | 16-jul |
| `EXCEL_A_CSV.cmd` | `excel_a_csv.py` | (en README_KIT) | 16-jul |
| `INFORME_GERENCIA.cmd` | `informe_gerencia.py` | (en README_KIT) | 16-jul |
| `VIGILANTE_NOCTURNO.cmd` | (batch puro, tarea programada) | (en README_KIT) | 16-jul |
| `AUDITAR_DEV_EPS.cmd` | `auditar_devoluciones_eps.py` | `README_AUDITAR_DEV_EPS.md` | 16–17-jul |
| `MOTOR_HUS.cmd` | (menú batch) | `README_KIT_AUDITORIA.md` | 16-jul |

> Bots preexistentes (sesiones anteriores, no de esta conversación pero integrados
> en el mismo menú): `UNIR_PDFS`, `PDF_A_CMD`, `EXCEL_A_CMD`, `COMPRIMIR_ZIP`,
> `PARTIR_ZIP_30MB`.

### 2.4 Dependencias / librerías (runtime de los bots)

Las instala el propio `.cmd` la primera vez, con `pip install --user` (sin admin):

| Librería | Para qué | Bots que la usan |
|---|---|---|
| **openpyxl** (`==3.1.5` en requirements) | leer/escribir `.xlsx` | TXT_A_EXCEL, EXCEL_A_CSV, REVISAR_XML, VERIFICAR_RADICACION, CRUZAR_GLOSAS, SEMAFORO_GLOSAS, INFORME_GERENCIA, AUDITAR_DEV_EPS |
| **pymupdf** (`fitz`) | leer texto de PDF y renderizar páginas a imagen | AUDITAR_DEV_EPS, UNIR_PDFS |
| **pytesseract** | puente Python → motor OCR Tesseract | AUDITAR_DEV_EPS |
| **pillow** (`PIL`) | imagen intermedia para el OCR | AUDITAR_DEV_EPS |
| **PyPDF2** (`==3.0.1`) / `pypdf` | unir/partir PDF | UNIR_PDFS, PARTIR_ZIP (auxiliar) |
| **Tesseract-OCR** (motor externo, no pip) | reconocimiento óptico de caracteres | AUDITAR_DEV_EPS |

Módulos de librería estándar usados intensivamente: `re`, `pathlib`, `os`, `sys`,
`json`, `csv`, `zipfile`, `datetime`, `shutil`, `contextlib`.

### 2.5 APIs / modelos / servicios

- **APIs:** el módulo de bots **no expone ni consume APIs HTTP**. Es 100 % local.
- **Modelos / servicios:** no hay capa de modelos ni servicios de aplicación; cada
  bot es un script funcional (funciones puras + un `main()` / `procesar()`).
- La **única** referencia a modelos/endpoints del proyecto grande aparece en la
  corrección de CI (sección 5 y 6): modelos `GlosaRecord` y `UsuarioRecord`, y los
  endpoints `/glosas/stats/por-dia-semana` y `/glosas/stats/heatmap-actividad`.

### 2.6 Utilidades transversales (patrones repetidos en todos los bots)

- **Detección de Python “por ejecución”**: prueba `py -3`, `python`, `python3`
  ejecutando `import sys` (inmune al alias falso de la Microsoft Store).
- **Autoinstalación de Python** si falta: `winget` → si no, descarga desde
  `python.org` con `curl`/`Invoke-WebRequest`, instalación por usuario.
- **Saneo de rutas de Windows** (ver riesgo del backslash en §13).
- **Datos de facturación como TEXTO** (ceros a la izquierda, NIT largos, fechas).
- **Tolerancia a fallos**: `try/except` por archivo; se reporta y se sigue.

---

## 3. Funciones implementadas

Se listan primero las funciones **del motor central `auditar_devoluciones_eps.py`**
(el componente más complejo, 39 KB, ~1030 líneas) y luego el resto de bots.

### 3.1 `tools/auditar_devoluciones_eps.py` — funciones (por número de línea real)

| Línea | Función | Qué hace | Por qué existe / de qué depende |
|---|---|---|---|
| 61 | `normalizar_factura(valor)` | Deja solo dígitos y quita ceros a la izquierda (`HUS0000532392`→`532392`). | Base del emparejamiento factura↔archivo. |
| 66 | `_patron_factura(norm)` | Compila `HUS0*<norm>(?![0-9])` (regex, `re.I`). | **Corrige** el bug de concatenar todos los dígitos de un nombre como `OPF_900006037_HUS532392` (antes daba `900006037532392`, nunca casaba). Ahora empareja el *token* `HUS…`. |
| 75 | `_configurar_tesseract()` | Si Tesseract no está en el PATH, apunta `pytesseract` a rutas típicas (`%ProgramFiles%`, `%LOCALAPPDATA%\Programs\…`). | Que el OCR funcione aunque el instalador no toque el PATH. |
| 98 | `_lang_ocr()` | Devuelve `"spa+eng"`/`"spa"`/`"eng"`/`""` según los idiomas instalados. | OCR de soportes en español. |
| 121 | `_ocr_pagina(pg)` | Renderiza la página (pixmap dpi≈200) → PIL → `image_to_string`. | Leer PDF que son **solo imagen**. |
| 139 | `_texto_pdf(ruta, ocr=True, max_ocr_pag=20)` | Extrae texto con `fitz`; si una página trae <20 chars y tiene imágenes, cae a OCR. | Fuente única de texto de cualquier PDF (con o sin capa de texto). |
| 189 | `_autoriz_json_bruto(s)` | Devuelve `"null"` si `numAutorizacion` es `None` (clave presente), `""` si falta. | El usuario pidió **reportar el `null` tal cual** del JSON. |
| 200 | `leer_rips(ruta)` | Lee el JSON RIPS probando `utf-8-sig`/`cp1252`/`latin-1`; guardas contra no-dict. | Los RIPS reales llegan en codificaciones distintas y a veces corruptos. |
| 265 | `autorizaciones_del_json(rips)` | Recolecta **todas** las autorizaciones (incluidas `null`). | Comparar contra las del soporte. |
| 291 | `_ultimos9(token)` | Últimos 9 dígitos de un token. | El usuario audita por los **últimos 9 dígitos** (`(POS) 5251-313608762`→`313608762`). |
| 298 | `extraer_autorizaciones(texto)` | Regex `_RE_AUT` (mayúsc./saltos de línea, `re.I`) → lista de autorizaciones. | Un PDE puede traer **varias** autorizaciones (una por servicio). |
| 310 | `extraer_documento(texto)` | Tipo+documento del paciente puntuando por el contexto previo; ignora institucionales. | Evita falsos positivos (preposición “DE”, teléfonos, radicados, NIT). |
| 351 | `_limpiar_nombre(bruto)` | Normaliza el nombre. | Salida legible. |
| 361 | `extraer_nombre(texto)` | Nombre del paciente sin cruzar líneas. | FACTURA DGH. |
| 380 | `extraer_servicio(texto)` | Servicio/procedimiento. | FACTURA DGH. |
| 412 | `validacion_sat(texto)` | Detecta si el trámite es SAT/Mi Seguridad Social y si dice **“Proceso exitoso”**, con su número. | Requisito de la GUÍA: confirmar que el SAT pasó. |
| 430 | `texto_validacion_sat(sat)` | Traduce el dict a texto para el Excel (“SAT: PROCESO EXITOSO - N° …” / “SAT: NO se evidencia…”). | Columna VALIDACIÓN SAT (PDE). |
| 440 | `leer_soportes(pdfs)` | Ordena **PDE primero**, junta el texto y saca autorizaciones/tipo/doc/nombre/servicio/SAT. | El PDE es “el que siempre se revisa”. |
| 483 | `_es_dir(p)` | Chequeo seguro de carpeta. | Recorridos robustos. |
| 490 | `_slot_vacio()` | Estructura vacía por factura. | Índice uniforme. |
| 494 | `_clasificar_archivo(slot, p)` | Mete cada archivo en `json`/`opf`/`pde`/`otros`. | Clasificar soportes. |
| 509 | `_recolectar_carpeta(carpeta, patron, slot)` | Recorre una carpeta y asigna por patrón de factura. | Reúso directo/árbol. |
| 534 | `indexar_directo(base, facturas)` | Va **directo** a `<base>/<AAAAMM>/FACTURAS_SALUD/<HUS>/` (+ meses adyacentes). | Rapidez: evita recorrer toda la red. Devuelve `(indice, faltan)`. |
| 560 | `indexar_arbol(base, facturas_norm, etiqueta)` | `os.walk` que **poda solo** carpetas `HUS…` ajenas; imprime progreso cada 400 carpetas. | Fallback cuando la ruta directa no existe; **sin colgarse**. |
| 601 | `diagnostico_soportes(base)` | Cuando halla 0 soportes, imprime cuántas carpetas/PDF vio y ejemplos de rutas. | Ayudar al usuario a saber si la carpeta es la correcta. |
| 631 | `_fundir(dst, extra)` | Funde dos índices. | Combinar JSON (red) + soportes (Y:). |
| 649 | `observacion(rips_doc, autoriz_json, sop)` | Compara conjuntos de últimos-9; marca `OK`, `JSON CON AUTORIZACION EN NULL`, `DIFERENCIA DEL NUMERO DE DOCUMENTO DGH VS JSON`, etc. | Corazón del hallazgo de auditoría (caso recién nacidos). |
| 707 | `_detectar_cabecera(ws)` | Busca en filas 1–7 una fila con celdas `FACTURA` **y** `FAC`. | Ubicar el encabezado del Excel de devoluciones. |
| 717 | `_mes_yyyymm(valor)` | `AAAAMM` de la fecha (datetime o texto dd/mm/aaaa). | Ruta directa por mes. |
| 733 | `_mes_adyacente(yyyymm, delta)` | Mes ±1. | Buscar en meses vecinos. |
| 745 | `_es_factura(valor)` | La celda parece factura (no TOTAL/SUBTOTAL). | Saltar filas de totales. |
| 757 | `procesar(excel, facturas_base, soportes_base, salida)` | Orquesta todo: carga Excel, indexa JSON + soportes, escribe columnas 7–20 y hoja DETALLE, guarda `_AUDITADO.xlsx`. | Función de aplicación del bot. |
| 995 | `main(argv)` | CLI: parsea `--facturas-base`, `--soportes-base`, `--salida`; sanea rutas. | Punto de entrada. |
| 1016 | `_limpiar_base(v)` (interna) | `strip().strip('"')` + `os.path.normpath`. | Corrige el backslash-comilla de Windows (§13). |

Constantes/regex de apoyo: `TIPOS_DOC` (línea 44, excluye `DE`/`SI` para no confundir),
`_RE_DOC_TIPADO`, `_RE_NUM`, `_RE_NO_DOC` (institucionales), `_RE_AUT`, `_RE_SAT`,
`_RE_SAT_EXITO`, `_RE_SAT_NUM`, `_RE_SAT_NUM2` (`\b(\d{3}[A-Z]{2}\d{10,})\b`),
`_RE_HUS_DIR` (`^HUS\d+$`).

### 3.2 Resto de bots (una línea cada uno)

- **`revisar_xml_facturas.py` (REVISAR_XML):** abre los XML radicados (FEV /
  AttachedDocument con `Invoice` embebido en CDATA), extrae `NUMERO_CONTRATO`,
  `FACTURA_SIN_CONTRATO`, `ValidationResultCode` (02 = validado DIAN) y lo vuelca a
  Excel. Prueba documental de la glosa “factura sin contrato”.
- **`txt_a_excel.py` (TXT_A_EXCEL):** convierte `.txt` (FURIPS, de ancho fijo o
  “normales”) a `.csv` delimitado por comas + `.xlsx`; una sola carpeta o
  recursivo. Datos como texto.
- **`excel_a_csv.py` (EXCEL_A_CSV):** el reverso: cada Excel a `.csv` por comas para
  las plataformas.
- **`verificar_radicacion.py` (VERIFICAR_RADICACION):** antes de radicar, revisa que
  cada XML traiga contrato y validación DIAN, que los FURIPS tengan líneas completas
  y que cada factura tenga soportes. Previene la glosa.
- **`cruzar_glosas_xml.py` (CRUZAR_GLOSAS):** cruza el Excel de glosas de la EPS con
  los XML radicados → `CRUCE_GLOSAS.xlsx` + `BORRADORES_RESPUESTA.txt` por causal,
  citando la evidencia real del XML. Los `[COMPLETAR: …]` los pone el auditor.
- **`semaforo_vencimientos.py` (SEMAFORO_GLOSAS):** plazos en **días hábiles**
  (festivos de Colombia): NEGRO vencida, ROJO 1–4, AMARILLO 5–10, VERDE 11+.
- **`buscar_facturas.py` (BUSCAR_FACTURA):** con `facturas.txt` al lado, rastrea la
  carpeta compartida y copia todos los archivos de esas facturas a
  `SOPORTES_ENCONTRADOS\<factura>\`.
- **`informe_gerencia.py` (INFORME_GERENCIA):** desde `REGISTRO_BOTS.csv` genera un
  informe HTML (usos por bot / persona / semana) listo para imprimir.
- **`VIGILANTE_NOCTURNO.cmd`:** deja programada una tarea de Windows que cada noche
  convierte los `.txt` nuevos de una carpeta (menú instalar/probar/desinstalar;
  log en `VIGILANTE_LOG.txt`).
- **`MOTOR_HUS.cmd`:** menú de 15 opciones; registra cada uso en
  `REGISTRO_BOTS.csv` (`fecha;hora;usuario;equipo;bot`).

---

## 4. Flujo completo (paso a paso)

### 4.1 Flujo genérico de cualquier bot (doble clic)

1. El auditor copia el `.cmd` a una carpeta (o abre `MOTOR_HUS.cmd` y elige número).
2. `@echo off` + `chcp 65001` + `setlocal EnableExtensions DisableDelayedExpansion`.
3. **Detecta Python** ejecutando candidatos; si no hay, lo **instala** (winget →
   python.org). 
4. **Asegura dependencias** con `pip --user` (openpyxl/pymupdf/…); si algo no queda,
   avisa pero continúa lo que pueda.
5. **Pide rutas** con valores por defecto (Enter = usar el detectado).
6. **Extrae el motor** embebido (tras `#PYSTART#`) a `%TEMP%` y lo ejecuta con las
   rutas dadas.
7. El motor **solo lee** las fuentes y **escribe una copia** de salida junto al
   `.cmd`. Muestra progreso y un resumen final. `pause` para que el usuario lea.

### 4.2 Flujo detallado de AUDITAR_DEV_EPS (el más complejo)

1. Detecta el Excel de devoluciones junto al `.cmd` (lo reconoce si el nombre dice
   `DEV`; si no, toma el primero que no sea `_AUDITADO`).
2. Pide **base de facturas/JSON** (por defecto la red del HUS
   `\\172.16.32.83\factura_electronica_net22`) y **base de soportes** (por defecto
   `Y:\`). Sanea el backslash final (§13).
3. `procesar()`:
   - `load_workbook`; `_detectar_cabecera` (filas 1–7 con `FACTURA`+`FAC`). Si no la
     halla → error código 2 (**caso del Excel de GLOSAS ACEPTADAS**, §15).
   - Recorre filas: por cada `_es_factura`, guarda `(fila, factura, envío, mes)`.
   - **[1/2] JSON:** `indexar_directo` a `<base>/<AAAAMM>/FACTURAS_SALUD/<HUS>/`; lo
     que falte, `indexar_arbol` (con poda y progreso).
   - **[2/2] Soportes:** `indexar_arbol(soportes_base)` (poda solo carpetas `HUS`
     ajenas). Funde con lo hallado en la base de facturas.
   - Por cada factura: `leer_rips` (JSON) y `leer_soportes` (PDE primero + OPF +
     otros, con OCR si hace falta) → `observacion()` + `validacion_sat()`.
   - Escribe columnas: FACTURA DGH (7–10), RIPS‑JSON (11–13), SOPORTES (14–16),
     OBSERVACIÓN (17), **VALIDACIÓN SAT (PDE)** (18), **RUTA DEL JSON** (19),
     **RUTA DE LOS SOPORTES** (20), con estilos (colores: verde OK, rojo
     diferencia, amarillo revisar) y una hoja **DETALLE** con todos los usuarios y
     servicios.
   - `wb.save(_AUDITADO.xlsx)` (maneja `PermissionError` si está abierto).
4. Consola: cuántos JSON y cuántos soportes halló; si 0 soportes →
   `diagnostico_soportes`.

---

## 5. Base de datos

**Para el módulo de bots: NO APLICA.** Los bots no usan base de datos; operan sobre
archivos (Excel/CSV/PDF/TXT/JSON) en disco/red. El único “almacén” propio es el CSV
plano `REGISTRO_BOTS.csv` (columnas `fecha;hora;usuario;equipo;bot`), que genera el
menú y consume INFORME_GERENCIA.

**Contexto tocado por la corrección de CI (22-jul), pertenece a la app grande:**

- Modelo **`GlosaRecord`** (SQLAlchemy). Campos usados/observados en las pruebas y
  endpoints: `id`, `eps`, `paciente`, `codigo_glosa`, `valor_objetado`,
  `valor_aceptado`, `etapa`, `estado` (p.ej. `RADICADA`), `creado_en` (datetime),
  y campos derivados como `dias_restantes`.
- Modelo **`UsuarioRecord`**: `id`, `email`, `rol` (p.ej. `AUDITOR`), `activo`.
- Tablas creadas en las pruebas con `Base.metadata.create_all(engine)` sobre SQLite
  en memoria (`StaticPool`). En CI la base es `sqlite:///./test_ci.db`.
- Índices/migraciones/relaciones: **no se modificaron en esta conversación**; el
  arreglo fue exclusivamente en los **tests**, no en el esquema.

---

## 6. Backend

**Para el módulo de bots: NO APLICA** (no hay servidor, endpoints, controladores ni
middleware; la “lógica de servidor” es cada script Python local).

**Backend tocado por la corrección de CI (contexto de la app grande):**

- Endpoints observados en `app/api/routers/glosas_stats.py`:
  - `GET /glosas/stats/por-dia-semana` — `dias: int = Query(90, ge=7, le=365)`;
    filtra `creado_en >= ahora_utc() - timedelta(days=dias)`; agrupa por
    `creado.weekday()` (Lunes=0…Domingo=6); devuelve `items[]` con
    `dia/count/valor_total/pct_del_total`, `total_glosas`, `ventana_dias`.
  - `GET /glosas/stats/heatmap-actividad` — misma ventana de 90 días; construye
    matriz 7×24 con `creado.weekday()` × `creado.hour`.
  - Ambos leen el `datetime` **en UTC directamente** (sin convertir a hora de
    Colombia), dato que fue clave para el arreglo.
- Validaciones/permisos: los endpoints usan `Depends(get_db)` y
  `Depends(get_usuario_actual)`; en pruebas se sobreescriben con `dependency_overrides`.
- **Errores corregidos:** no eran de código de producción sino de **pruebas
  caducadas** (ver §10 y §15).

---

## 7. Frontend

**NO APLICA en el sentido web.** Este módulo no tiene pantallas, componentes,
formularios, modales ni animaciones de interfaz gráfica. La “interfaz” es:

- La **ventana de consola** de Windows (menú de texto de `MOTOR_HUS.cmd`, prompts
  con valores por defecto, barras de progreso textuales, mensajes `[OK]`/`[ATENCION]`).
- Las **salidas visuales** son archivos: los **Excel con formato** (colores por
  estado en la OBSERVACIÓN, anchos de columna, `wrap_text`, hoja DETALLE) y el
  **HTML imprimible** que genera `INFORME_GERENCIA` (tablas de uso por
  bot/persona/semana). No hay JavaScript ni framework de UI.

---

## 8. IA

### 8.1 IA en tiempo de ejecución del módulo

**NO APLICA.** Ningún bot llama a modelos de IA en ejecución. Todo es
determinístico (regex, parsing, OCR). El OCR (Tesseract) es visión por computador
clásica, no un LLM.

### 8.2 IA en el **proceso de desarrollo** (metodología, sí aplica)

- Se usó una **revisión adversarial multi-agente** (herramienta de orquestación
  Workflow) para endurecer dos motores:
  - **TXT_A_EXCEL:** revisión con ~**31 agentes** (finders → verificadores). Todos
    los defectos confirmados se corrigieron y se cubrieron con pruebas.
  - **AUDITAR_DEV_EPS:** revisión con ~**30 agentes**; **22 defectos confirmados**,
    todos corregidos y con test.
  - Patrón: *pipeline* de agentes que **buscan** hallazgos → agentes que
    **verifican de forma adversarial** con esquema (schema) para descartar falsos
    positivos.
- **Proveedores/modelos/temperatura/fallback:** no aplican a este módulo (no hay
  llamadas a IA en el producto). *Como contexto del proyecto grande*, en los logs
  de CI se observó la línea `[IA-PROVIDERS] primary=gemini | anthropic=AUSENTE |
  gemini=AUSENTE | groq=AUSENTE` — esa configuración es de la **app web**, no de
  este módulo, y **no se creó ni modificó** en esta conversación.

---

## 9. Automatizaciones

1. **VIGILANTE_NOCTURNO** — crea una **tarea programada de Windows** que **cada
   noche** convierte los `.txt` nuevos de una carpeta elegida (sin que nadie dé
   doble clic). Menú para instalar / probar / desinstalar; deja `VIGILANTE_LOG.txt`.
2. **Autoinstalación de dependencias** — cada `.cmd`, la primera vez, instala Python
   (winget → python.org) y las librerías pip necesarias. Sin admin.
3. **Autoinstalación del motor OCR** (AUDITAR_DEV_EPS) — intenta `winget UB-Mannheim.
   TesseractOCR`; si falla, **descarga el instalador oficial** (`curl`/PowerShell) y
   lo instala por usuario en `%LOCALAPPDATA%\Programs\Tesseract-OCR`.
4. **Bitácora de uso automática** — `MOTOR_HUS.cmd` registra cada ejecución en
   `REGISTRO_BOTS.csv`, del que sale el informe de gerencia sin trabajo manual.
5. **CI (GitHub Actions)** — en cada push corre `pytest` (2777+ pruebas del repo) y
   ruff; sube artefactos (`junit.xml`, `pytest-output.log`).

---

## 10. Archivos modificados (por esta conversación)

Commits de la rama (más nuevo primero) y qué cambió en cada uno:

| Commit | Fecha | Archivos | Qué cambió |
|---|---|---|---|
| `904569e` | 22-jul | `tests/test_api/test_por_dia_semana.py`, `tests/test_api/test_heatmap_actividad.py` | Reemplaza fechas fijas de abril por un **lunes reciente** calculado desde `ahora_utc()` (helper `_lunes_reciente`), para que las pruebas no caduquen. Ajusta imports. |
| `6abe244` | 22-jul | `BITACORA.md` (nuevo), `CLAUDE.md` | Crea la memoria común entre chats y la instrucción de leerla/actualizarla. |
| `4c9c3ca` | 17-jul | `tools/AUDITAR_DEV_EPS.cmd` | Añade **descarga directa** del instalador de Tesseract si `winget` falla. |
| `ec84989` | 17-jul | `tools/auditar_devoluciones_eps.py`, `tools/AUDITAR_DEV_EPS.cmd`, tests, README | **Validación SAT (Proceso exitoso)** en el PDE + **OCR** de PDF-imagen. |
| `77d00b8` | 17-jul | idem motor + cmd + tests + README | Columnas **RUTA DEL JSON** y **RUTA DE LOS SOPORTES**. |
| `838519c` | 17-jul | idem | Usa **cualquier PDF** de la carpeta como soporte + `diagnostico_soportes`. |
| `5c8b5c0` | 16-jul | idem | **Fix**: no hallaba soportes por podar por envío (se quitó esa poda). |
| `24a8958` | 16-jul | idem | Extrae **todas** las autorizaciones (últimos 9) y reporta el `null` del JSON tal cual. |
| `c68a91b` | 16-jul | idem | **Fix**: dejaba de colgarse recorriendo toda la red (ruta directa + poda + progreso). |
| `f6f901d` | 16-jul | motor + cmd + tests + README + menú | **Alta** del bot AUDITAR_DEV_EPS. |
| `6f1d6aa` | 16-jul | `informe_gerencia.py`+cmd, `VIGILANTE_NOCTURNO.cmd`, menú, tests | INFORME_GERENCIA + VIGILANTE_NOCTURNO. |
| `01e64b6` | 16-jul | `MOTOR_HUS.cmd`, `verificar_radicacion.py`, `cruzar_glosas_xml.py`, `semaforo_vencimientos.py`, `buscar_facturas.py`, `excel_a_csv.py` (+ cmd + tests + README_KIT) | Menú central + **5 bots** del ciclo de glosas. |
| `27ae47d` | 16-jul | `txt_a_excel.py` + cmd + tests | Correcciones de la revisión adversarial (31 agentes). |
| `3e4aef3` | 16-jul | `txt_a_excel.py` + cmd + tests + README | **Alta** de TXT_A_EXCEL. |
| `d78c0be` | 15-jul | `revisar_xml_facturas.py` + cmd + tests + README | **Alta** de REVISAR_XML. |

> Cada “motor + cmd” significa que se editó el `.py` y **se regeneró** el `.cmd` para
> que el motor embebido quedara idéntico (invariante `test_motor_embebido_en_cmd_
> identico_al_py`).

---

## 11. Dependencias nuevas

Ninguna se agregó al `requirements.txt` del servidor (los bots las instalan en el PC
del auditor en runtime). Paquetes que los bots instalan/usan:

| Paquete | Versión | Para qué |
|---|---|---|
| openpyxl | 3.1.5 (pin del repo) | Excel `.xlsx` |
| pymupdf (`fitz`) | la que resuelva pip (sin pin) | leer/renderizar PDF |
| pytesseract | sin pin | puente al OCR |
| pillow (`PIL`) | sin pin | imagen intermedia del OCR |
| PyPDF2 | 3.0.1 (pin del repo) | unir/partir PDF |
| Tesseract-OCR (UB-Mannheim) | 5.3.3.20231005 (instalador que descarga el bot) | motor OCR externo |

En **CI** las pruebas usan `pytest.importorskip("fitz")` para no fallar donde no
está `pymupdf`.

---

## 12. Configuración

- **Rutas por defecto (parámetros del bot AUDITAR_DEV_EPS):**
  - Base de facturas/JSON: `\\172.16.32.83\factura_electronica_net22`
  - Base de soportes: `Y:\`
  - Estructura de red esperada: `<base>\<AAAAMM>\FACTURAS_SALUD\<HUS…>\(RIPS\)`
- **Flags CLI de AUDITAR_DEV_EPS:** `--facturas-base`, `--soportes-base`, `--salida`.
- **Variables de entorno del módulo de bots:** **ninguna** (no requieren env).
- **Variables de entorno del CI (contexto app):** `SECRET_KEY`, `DATABASE_URL`
  (`sqlite:///./test_ci.db`), `PYTHONPATH`, `DISABLE_SCHEDULERS=1`.
- **Tokens / credenciales:** el módulo **no maneja** tokens ni secretos. (Nada que
  reportar; no incluir credenciales en esta doc.)
- **Archivos de configuración del repo:** `pyproject.toml`, `requirements.txt`,
  `pytest.ini`, `.gitattributes` (`*.cmd text eol=crlf`), reglas ruff (`--select
  F,W6` en CI; select completo en pre-commit).

---

## 13. Riesgos (qué puede romperse al integrar) y cómo resolverlos

1. **Codificación del `.cmd`:** si alguien mete un carácter no-ASCII en la sección
   batch, Windows lo rompe. → La parte batch debe ser 100 % ASCII; el motor va tras
   `#PYSTART#`. Lo verifica la prueba de ensamblado.
2. **Saltos de línea:** un LF suelto rompe el polyglot. → Regenerar siempre con el
   ensamblador (normaliza a CRLF); `.gitattributes` fuerza `eol=crlf` en `.cmd`.
3. **Motor embebido divergente del `.py`:** si se edita el `.py` y no se regenera el
   `.cmd`, quedan distintos. → Invariante de test
   `test_motor_embebido_en_cmd_identico_al_py`; regenerar tras cada cambio.
4. **Backslash + comilla en Windows:** `"Y:\"` llega a cmd como `Y:"` (la barra
   escapa la comilla). → El batch strippea la barra final y, si queda `:`, agrega
   `\.` (`Y:\.`); el Python hace `strip().strip('"')` + `os.path.normpath`.
5. **Colgarse en la red:** recorrer `Y:\` entero es lento. → Ruta directa por mes +
   poda de carpetas `HUS` ajenas + progreso cada 400 carpetas.
6. **Emparejar factura por substring:** `HUS532392` vs `HUS5323921`. → `_patron_
   factura` con `(?![0-9])`.
7. **Pruebas que caducan por fechas fijas:** ya ocurrió 3 veces en el repo. → Anclar
   siempre a fechas relativas a “ahora” dentro de la ventana (patrón `_lunes_
   reciente`). **Al integrar, revisar cualquier test con fechas literales.**
8. **OCR ausente:** si Tesseract no se instala, los PDF **solo-imagen** quedan sin
   leer. → Los PDF con texto se auditan igual; el bot avisa y continúa.
9. **Conflicto de merge del `.cmd`:** son archivos grandes con CRLF; un merge textual
   puede corromper el marcador. → Ante conflicto, **regenerar** el `.cmd` desde el
   `.py`, no resolver a mano.

---

## 14. Dependencias con otros módulos

- **Qué módulos necesita este módulo:** en runtime, **ninguno** del proyecto grande.
  Solo Python + librerías pip (que instala solo). No depende del backend, la base de
  datos ni el frontend.
- **Qué módulos lo utilizan:** **ninguno** consume a los bots por código; el consumo
  es humano (el auditor). El backend web y el kit de bots comparten repositorio pero
  **no** se importan entre sí.
- **Relación con la app web:** conviven en el mismo repo y **comparten el CI**. Por
  eso una prueba rota del backend (aunque no sea del módulo) **bloquea el PR del
  módulo** — como pasó el 22-jul. Es un acoplamiento de *pipeline*, no de código.
- **Relación con la bitácora:** `MOTOR_HUS` escribe `REGISTRO_BOTS.csv`;
  `INFORME_GERENCIA` lo lee. `BITACORA.md`/`CLAUDE.md` son memoria entre chats.

---

## 15. Pendientes / errores conocidos / mejoras previstas

- 🟡 **PENDIENTE PRINCIPAL — Excel de GLOSAS ACEPTADAS:** `AUDITAR_DEV_EPS` solo
  reconoce el formato de devoluciones (cabecera con celdas `FACTURA`+`FAC` y columnas
  fijas). Con `ARCHIVO JUNIO 2026-GLOSAS ACEPTADAS.xlsx` se detiene con *“no encontré
  la cabecera (FACTURA / FAC)”* (código 2). **Mejora prevista y ya diseñada:** hacer
  la detección flexible (reconocer la columna de factura aunque se llame distinto:
  `No. FACTURA`, `NUMERO FACTURA`, etc.) y **agregar las columnas de auditoría al
  final** de la hoja **sin pisar** las columnas existentes del usuario. Falta ver la
  estructura real del archivo para no adivinar la columna equivocada.
- 🟡 **OCR condicionado al PC:** en algún equipo del hospital `winget` no instaló
  Tesseract; se agregó la descarga directa, pero **queda por confirmar** que instala
  bien en ese PC concreto.
- 🟢 **Cobertura de pruebas del módulo:** 117 pruebas recolectadas entre
  `tests/test_tools/` (109) y las 8 del backend corregidas. Verde tras el arreglo.
- **Mejoras futuras sugeridas:** unificar READMEs por bot; permitir a
  `AUDITAR_DEV_EPS` recibir la ruta del Excel por parámetro desde el menú;
  parametrizar la ventana de días de los stats del backend en las pruebas.

---

## 16. Recomendaciones para fusionarlo en el proyecto principal

1. **Base del PR:** actualmente la rama `claude/powershell-pdf-cmd-bot-3iaihn`
   (PR #156, *draft*) apunta a `claude/excel-reconciliation-data-9Bnpj`. Para
   integrar al tronco, **recambiar la base a la rama principal** (`motor-glosas`) y
   resolver el PR contra ella.
2. **No mezclar a mano los `.cmd`:** si aparecen conflictos en archivos `.cmd`,
   **regenerarlos** desde su `.py` con el ensamblador correspondiente en vez de
   resolver el conflicto textual (evita romper el marcador/CRLF).
3. **Correr la suite completa antes de fusionar:**
   `python3 -m pytest tests/test_tools/ tests/test_api/ -q` y
   `python3 -m ruff check . --select F,W6 && python3 -m ruff format --check`.
4. **Revisar tests con fechas literales** en todo lo que se traiga (patrón de
   caducidad); anclar a fechas relativas.
5. **Traer también la documentación**: `README_KIT_AUDITORIA.md`, los `README_*`
   por bot, `BITACORA.md`, `CLAUDE.md` y este documento. El conocimiento va con el
   código.
6. **Verificar `.gitattributes`** (`*.cmd text eol=crlf`) en el destino, para que
   los `.cmd` conserven CRLF tras el merge.
7. **Preservar la regla de negocio** en cualquier refactor: los bots **solo leen** y
   **escriben copias**; nunca tocan el original ni pisan archivos ajenos.

---

## 17. Resumen ejecutivo — lo que otro desarrollador debe saber para mantenerlo

- **Qué es:** un kit de **16 bots de doble clic** (`tools/*.cmd`) para auditoría de
  glosas del HUS, pensado para usuarios **no técnicos**. Cada `.cmd` es un
  **polyglot batch+Python**: la sección batch (ASCII, CRLF) instala Python y
  dependencias y extrae el motor Python que viene **embebido** tras el marcador
  `#PYSTART#`.
- **Regla número uno de mantenimiento:** si tocas un `<nombre>.py`, **regenera su
  `.cmd`** para que el motor embebido quede **byte a byte idéntico** (hay un test que
  lo exige). Los ensambladores viven en la carpeta de trabajo temporal (scratchpad).
- **Invariantes que no debes romper:** marcador `#PYSTART#` exactamente una vez, 0
  LF sueltos, batch 100 % ASCII, paréntesis balanceados, `goto`/labels resueltos.
- **Reglas de negocio:** nunca modificar el archivo original (escribir copia); un
  archivo dañado no detiene el lote (reportar y seguir); datos de facturación como
  **texto**.
- **La joya:** `AUDITAR_DEV_EPS` — cruza factura DGH ↔ RIPS(JSON) ↔ soportes
  (OPF/PDE), empareja por el token `HUS…`, extrae **todas** las autorizaciones por
  sus **últimos 9 dígitos**, reporta el `null` del JSON tal cual, valida el trámite
  **SAT “Proceso exitoso”** en el PDE y usa **OCR** para los PDF que son solo imagen.
  Va **directo** por carpeta/mes y **poda** el árbol para no colgarse en la red.
- **Trampa recurrente del repo:** pruebas con **fechas fijas** que caducan al pasar
  el tiempo (ventanas de 90 días). Si un test de `test_api` de repente da `0 == 2`,
  casi seguro es eso: ancla la fecha a `ahora_utc()`.
- **Dónde mirar primero:** `BITACORA.md` (qué se hizo / qué falta), `CLAUDE.md`
  (reglas del repo), `README_KIT_AUDITORIA.md` (visión de usuario) y este documento
  (visión técnica). El **pendiente inmediato** es adaptar `AUDITAR_DEV_EPS` al Excel
  de **GLOSAS ACEPTADAS**.
- **Calidad:** `pytest tests/test_tools/` + ruff en verde es el criterio de “listo”.

---

*Fin del documento — entrega del módulo Kit de Bots de Auditoría HUS.*
