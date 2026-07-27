# Documentación oficial del módulo — Respuesta automatizada de glosas: MUTUAL SER

**Estado:** entrega técnica para consolidación en el proyecto principal.
**Repositorio:** `motor-glosas-hus`
**Rama de desarrollo:** `claude/mutual-ser-glosa-responses-fa4k2g`
**Pull Request:** #154 (borrador). **Rama base:** `motor-glosas`.
**Entidad objetivo:** MUTUAL SER EPS — portal **Zona Ser** (`https://portalzonaser.mutualser.com`).
**Institución:** ESE Hospital Universitario de Santander (HUS), NIT 900006037-4.
**Autoría:** Área de Cartera / Auditoría de Cuentas Médicas del HUS, con asistencia de Claude Code.

> Este documento reconstruye **todo** lo realizado en la conversación de desarrollo de
> este módulo, incluyendo decisiones técnicas, enfoques descartados y hallazgos. No es un
> resumen: es la memoria técnica completa para quien reciba y mantenga el módulo.

---

## Índice

1. Objetivo del desarrollo
2. Arquitectura
3. Funciones implementadas
4. Flujo completo
5. Base de datos
6. Backend
7. Frontend
8. IA
9. Automatizaciones
10. Archivos modificados
11. Dependencias nuevas
12. Configuración
13. Riesgos
14. Dependencias con otros módulos
15. Pendientes
16. Recomendaciones para fusionarlo
17. Resumen ejecutivo

---

## 1. Objetivo del desarrollo

### ¿Por qué se creó este módulo?
El HUS recibe **glosas** (objeciones a la facturación) de las EPS. En MUTUAL SER, cuando
la glosa es **ratificada**, el hospital debe **subsanar** (responder) en el portal Zona
Ser, ítem por ítem. El proceso manual es lento y repetitivo: por **cada objeción** hay que
abrir el portal, expandir el ítem, escribir el valor aceptado, pegar un texto legal de
conciliación de ~831 caracteres en una ventana modal, subir un PDF de soporte, y al final
elegir un código y enviar. Una factura puede tener **decenas o cientos** de objeciones
(hasta 185 en el piloto), multiplicando el tiempo y el riesgo de error humano (texto
inconsistente, soporte omitido, código equivocado).

### ¿Qué problema resolvía?
Automatizar de punta a punta la **subsanación de glosas ratificadas** en MUTUAL SER,
garantizando: exactitud de los datos, texto legal idéntico en todas las glosas, evidencia
de cada envío para auditoría, y velocidad.

### ¿Qué necesidad cubría?
1. **Extraer** de forma exacta los datos de respuesta desde los PDF "Trámite de Objeción".
2. **Cargar y enviar** esas respuestas en el portal sin intervención manual.
3. **Convertir** las objeciones descargadas del portal al formato que ingiere el sistema
   interno de cartera del HUS (formato "CRO*").

### Caso de negocio (glosa ratificada, rechazo total)
La respuesta del HUS es **uniforme**: no se acepta ninguna glosa → **Valor Aceptado = $0**
para todas, **código de respuesta RE9901** ("RE9901 SUBSANADA TOTAL"), y un único **texto
de conciliación** (idéntico en todas las glosas) que solicita conciliación de auditoría y
cita la Ley 1438 de 2011 (art. 57 y 126) y el Decreto 4747 de 2007 (art. 20).

---

## 2. Arquitectura

### Naturaleza del módulo
Es un conjunto de **scripts de línea de comandos (CLI) en Python**, autónomos, que viven
en la carpeta `tools/` del repositorio. **No** es una aplicación web propia: no expone
servidor, ni base de datos, ni interfaz. Su "interfaz" es la terminal; su "backend" es el
**portal de la EPS**, que el módulo **opera** mediante automatización de navegador.

### Estructura de carpetas y archivos (de este módulo)
```
motor-glosas-hus/
├── tools/
│   ├── extraer_respuestas_glosa_mutualser.py   # PDF Trámite de Objeción → Excel de respuestas
│   ├── responder_glosas_mutual_ser.py          # Robot Playwright: llena y envía la subsanación
│   └── objeciones_a_formato_interno.py         # Excel de objeciones del portal → formato interno CRO*
├── docs/
│   ├── CONTEXTO_MUTUAL_SER.md                   # Notas técnicas del flujo/DOM del portal
│   └── MODULO_GLOSAS_MUTUAL_SER.md              # (este documento)
├── BITACORA.md                                 # Memoria común entre sesiones de Claude Code
└── CLAUDE.md                                    # Instrucciones de sesión (leer/actualizar BITÁCORA)
```

### Componentes
- **Extractor de PDF** (`extraer_respuestas_glosa_mutualser.py`): componente de *preparación
  de datos*. Convierte el PDF oficial en un Excel estructurado.
- **Robot de carga** (`responder_glosas_mutual_ser.py`): componente de *automatización de
  navegador*. Es el corazón del módulo.
- **Conversor a formato interno** (`objeciones_a_formato_interno.py`): componente de
  *transformación de datos* hacia el sistema de cartera del HUS.
- **Documentación** (`docs/CONTEXTO_MUTUAL_SER.md`): registro de ingeniería inversa del
  portal (React/MUI), selectores y decisiones.

### Dependencias y librerías
- **Playwright (API síncrona de Python)** + **Chromium**: automatización del navegador. Se
  instala **aparte** (no está en `requirements.txt`): `pip install playwright` +
  `playwright install chromium`.
- **pdfplumber == 0.11.5**: extracción de texto de los PDF (ya presente en `requirements.txt`).
- **openpyxl == 3.1.5**: lectura/escritura de Excel (ya presente en `requirements.txt`).
- **Estándar de Python**: `argparse`, `csv`, `logging`, `re`, `unicodedata`, `contextlib`,
  `datetime`, `pathlib`, `time`, `os`, `sys`.

### "APIs", "modelos", "servicios", "utilidades"
- **APIs**: el módulo no expone ni consume APIs REST propias. Interactúa con el portal de
  MUTUAL SER (aplicación React/MUI) a través del **DOM** y del protocolo **CDP** (Chrome
  DevTools Protocol) para conectarse al Chrome real del usuario.
- **Modelos de datos**: no hay ORM ni tablas. Los "modelos" son **estructuras en memoria**
  (diccionarios) y **contratos de columnas** de los Excel/CSV (ver §5).
- **Servicios**: cada script encapsula su lógica; no hay capa de servicios compartida.
- **Utilidades**: funciones auxiliares internas (`_norm_header`, `normalizar_factura`,
  `_to_int`, `sanitizar`, `factura_larga`, `_dump_tabla`, `_dump_modal`).

---

## 3. Funciones implementadas

### 3.1 `tools/responder_glosas_mutual_ser.py` (robot de carga — núcleo)

- **`_exigir_playwright()`** — Verifica que Playwright esté instalado; si no, imprime la
  instrucción de instalación y sale con código 2. *Existe* para dar un error claro en vez
  de un `ImportError` críptico. *Depende de ella*: `main`.
- **`setup_logging(log_file=None)`** — Configura logging a consola y, opcionalmente, a un
  archivo (`--log`). *Depende de ella*: `main`.
- **`cargar_credenciales() -> (user, password)`** — Lee `MUTUALSER_USER` y
  `MUTUALSER_PASSWORD` de variables de entorno; si faltan, sale con código 2. Sólo se usa
  cuando **no** se pasa `--cdp` (en modo CDP el login lo hace el humano). *Regla de
  seguridad*: nunca hay credenciales en código.
- **`_norm_header(h)`** — Normaliza encabezados de Excel (mayúsculas, sin tildes, espacios
  colapsados) para el emparejamiento tolerante de columnas. *Utilidad* de `leer_excel_respuestas`.
- **`normalizar_factura(f)`** — `'HUS0000510639' → '510639'` (quita prefijo HUS y ceros a
  la izquierda). Se usa para localizar la factura por su texto corto ("HUS510639") en la
  grilla. *Depende de ella*: `_abrir_factura`, `_resolver_soporte`.
- **`_to_int(s)`** — Convierte valores monetarios a entero (formato Colombia). *Utilidad*.
- **`leer_excel_respuestas(ruta) -> {factura: {items, grupos}}`** — Lee el Excel de
  respuestas (salida del extractor). Empareja columnas por alias tolerantes (`COLUMNAS`),
  arma un ítem por fila y **agrupa por `(cod_rta, detalle)` idénticos**; en glosa ratificada
  queda **un solo grupo** por factura. Cierra el workbook (`wb.close()`). *Por qué existe*:
  es el insumo del robot. *Depende de ella*: `main`.
- **`sanitizar(texto)`** — Translitera/limpia texto a `[A-Za-z0-9 ]` (previsto por si el
  portal rechaza caracteres especiales; por defecto **no** se usa, el bot manda el texto
  tal cual). *Decisión*: se dejó disponible pero inactiva.
- **`_login_ok(page)`** — Heurística de sesión activa: no estar en `/auth/login`, ver
  textos de `LOGIN_OK_TEXTOS`, o estar en `/dashboard`. *Depende de ella*: `login_interactivo`,
  `abrir_sesion`.
- **`login_interactivo(page, user, password, timeout_captcha_s=240)`** — Rellena
  credenciales y **espera hasta 240 s a que un humano resuelva el reCAPTCHA** y entre; al
  detectar sesión, retorna (el llamador guarda `storage_state`). *Existe* para el modo sin
  CDP. Ver §13 (reCAPTCHA).
- **`abrir_sesion(p, args, user, password) -> (browser, ctx, page, es_cdp)`** — Abre o
  conecta el navegador. **Modo `--cdp`**: se conecta por CDP a un Chrome real ya abierto por
  el usuario (con sesión iniciada); prueba variantes IPv4 (fallback `localhost`→`127.0.0.1`);
  **elige la pestaña que ya está en el portal** (no secuestra otras) y registra un handler
  de diálogos nativos. **Modo lanzado**: abre Chromium controlado por Playwright, reutiliza
  `storage_state` si existe, o hace login interactivo. *Depende de ella*: `main`.
- **`explorar(page, salida_dir)`** — Modo `--explorar`: vuelca el DOM del módulo
  (botones, inputs, selects, íconos `data-testid` de SVG, cabeceras de tabla, HTML crudo de
  la primera tabla y de cualquier modal) + screenshot. *Por qué existe*: **calibrar los
  selectores** contra el portal real. Fue clave en la ingeniería inversa.
- **`_abrir_factura(page, factura)`** — Va a `PORTAL_MODULO`, hace clic en la factura por su
  texto corto ("HUS"+número), y espera el botón **SUBSANAR GLOSA** como señal de que abrió
  el detalle. *Depende de ella*: `procesar_factura`.
- **`_dump_tabla(page, evidencias, nombre)`** — Diagnóstico: vuelca el `outerHTML` de la
  primera tabla a un archivo (`dbg_*.html`) cuando un selector falla.
- **`_dump_modal(page, evidencias, nombre)`** — Diagnóstico: vuelca el HTML del modal/overlay
  MUI visible.
- **`_item_rows(page)`** — Devuelve las **filas de ÍTEM padre**: `table tbody tr:has(td:nth-child(3)
  button)` (las que tienen el botón "+"). *Por qué existe*: identificar los ítems a expandir.
- **`_detail_rows(page)`** — Devuelve las **sub-filas de glosa**: `table tbody tr:has(input.MuiInputBase-inputAdornedEnd)`
  (las únicas con el input editable de valor). *Por qué existe*: un ítem puede tener **varias
  glosas** (los insumos de tecnología 799 traen 2), y hay que llenarlas **todas**.
- **`_set_valor(detail, valor, timeout=12000)`** — En la sub-fila de detalle, localiza el
  input de VALOR RATIFICADO ACEPTADO IPS por su **clase MUI estable**
  (`input.MuiInputBase-inputAdornedEnd`), hace clic, escribe el valor y presiona Tab (dispara
  la validación). *Depende de ella*: `subsanar_items`.
- **`_set_observacion(page, detail, texto)`** — Abre el modal de OBSERVACIONES de esa
  sub-fila (botón en `COL_OBSERVACION`), toma la **única `textarea:visible`** (hay decenas
  ocultas), escribe el texto y confirma con **ACEPTAR**; espera a que la textarea se oculte.
- **`_subir_soporte(page, detail, pdf, evidencias)`** — Sube el PDF de soporte de esa
  sub-fila: la celda SOPORTE (`COL_SOPORTE`) tiene 3 íconos (`Ver documentos` / **subir
  (nube)** / `Limpiar soporte`); hace clic en el del medio, espera el modal "SOPORTE - Cargar
  archivos", hace `set_input_files`, clic en **GUARDAR** y espera el toast de carga exitosa y
  el cierre del modal. Usa esperas por evento (no tiempos fijos).
- **`subsanar_items(page, valor, texto, evidencias, max_items=0, lento=False, soporte=None) -> int`**
  — Orquesta el llenado: hace clic en **SUBSANAR GLOSA**, espera que la tabla estabilice el
  conteo de ítems, **expande TODOS los ítems padre** (esperando que aparezcan sus sub-filas),
  y luego **llena CADA sub-fila de glosa** (valor + observación + soporte si aplica).
  Devuelve cuántas glosas llenó. Vuelca HTML de diagnóstico ante error. Advierte si hay menos
  glosas que ítems.
- **`_seleccionar_codigo(page, codigo, evidencias)`** — Selecciona el **CÓDIGO SUBSANACIÓN**
  (dropdown inferior) que habilita ENVIAR. Contiene:
  - **`_buscar_opcion()`** — busca la opción por `role=option` / `role=menuitem` / `<li>` con
    el texto del código.
  - **`_elegir(combo)`** — abre un combobox, espera (hasta 4 s) a que rendericen las opciones,
    hace clic en la del código, **lee el valor mostrado y ABORTA si no coincide** (anti código
    equivocado). Prueba varios combobox (paginador, filtros) con salida temprana si el menú
    abierto no matchea; *fallbacks* por placeholder ("seleccione una opción") y por
    `div[role=combobox]` / `.MuiSelect-select`.
- **`finalizar_factura(page, factura, evidencias, codigo="RE9901") -> str`** — (1) elige el
  código; (2) espera hasta ~40 s a que **ENVIAR SUBSANACIÓN** se habilite; (3) toma la foto
  **`<factura>_pre_envio.png`** (prueba de qué se envía); (4) hace clic en ENVIAR; (5) maneja
  un posible modal de confirmación; (6) toma `<factura>_ok.png`. Si el botón no se habilita,
  guarda `<factura>_no_habilita.png` y lanza error explicativo.
- **`_resolver_soporte(soportes_dir, factura) -> Path|None`** — Ubica el PDF de soporte de la
  factura en la carpeta `--soportes` (`<factura>.pdf` o `HUS<numero>.pdf`).
- **`procesar_factura(page, factura, datos, evidencias, max_items, finalizar, lento, soportes_dir,
  codigo, solo_finalizar) -> dict`** — Procesa una factura de punta a punta. **Guarda de
  seguridad**: si el Excel trae **respuestas no uniformes** (>1 grupo o valores aceptados
  distintos), **omite la factura sin enviar** y lo reporta. Trunca la observación a 1000
  caracteres (máximo del modal) con aviso. Soporta `solo_finalizar` (no rellena; entra a
  subsanar y solo elige código + envía). Captura `<factura>_error.png` si falla. Retorna un
  registro con estado (OK / LLENADO_SIN_ENVIAR / ERROR).
- **`_seleccionar_facturas(por_factura, args)`** — Filtra qué facturas procesar según
  `--solo / --facturas / --lista / --todas`.
- **`main()`** — Punto de entrada: parsea flags, valida, abre sesión, ejecuta `--explorar` o
  el bucle de facturas, escribe el reporte CSV (con `flush` por fila y `try/finally`), corta
  el lote si Chrome se cierra, y retorna código de salida ≠0 si hubo ERROR.

### 3.2 `tools/extraer_respuestas_glosa_mutualser.py` (extractor de PDF)

- **`_limpiar_obs(obs)`** — Corta el texto de "Observaciones:" en el primer marcador de
  pie/encabezado de página (`RE_PIE_PAGINA`) y colapsa espacios, para que todos los ítems con
  la misma respuesta queden **idénticos**.
- **`setup_logging()`**, **`_to_int(s)`** — utilidades.
- **`extraer_texto_pdf(ruta)`** — Extrae texto de todas las páginas con pdfplumber.
- **`_completar_codigo(cod5, bloque)`** — Reconstruye el **código de glosa de 6 caracteres**
  que pdfplumber parte por el ancho de columna (`CL010` + `1` = `CL0101`).
- **`_codigo_respuesta(bloque, default)`** — Detecta el código de respuesta (RE9901) del
  bloque; usa el dominante del documento si pdfplumber lo separó.
- **`extraer_objeciones(ruta) -> list[dict]`** — Recorre el texto con `RE_BLOQUE` (una
  objeción por bloque) y arma la lista con factura, número, código de glosa, código de
  respuesta, valores objetado/aceptado, servicio y observaciones.
- **`escribir_excel(filas, salida)`** — Escribe el Excel con 8 columnas: `Factura | # Objeción
  | Código Glosa | Código Respuesta | Servicio | Valor Objetado | Valor Aceptado | Detalle
  Respuesta`. Cabecera con formato, `freeze_panes`, formato numérico.
- **`main()`** — CLI: `--pdf` o `--carpeta`, `--salida`. Verifica los totales contra el PDF.

### 3.3 `tools/objeciones_a_formato_interno.py` (conversor a formato interno CRO*)

- **`setup_logging()`**, **`_norm(s)`**, **`_to_int(v)`** — utilidades (normalización,
  parseo de montos "$ 111.400").
- **`factura_larga(f)`** — `'HUS520567' → 'HUS0000520567'` (HUS + 10 dígitos con ceros).
- **`leer_objeciones(ruta) -> list[dict]`** — Lee el Excel de "Objeciones de glosa" del
  portal; **localiza la fila de encabezados** aunque no sea la primera, por sus nombres
  (`ENTRADA_ALIAS`, tolerante a tildes); devuelve un dict por objeción (factura, código,
  tecnología, valor, observación).
- **`escribir_formato_interno(objeciones, salida, fecha, usuario)`** — Escribe la hoja
  `OBJECIONES` con las 16 columnas CRO* en el **orden exacto** del sistema interno; aplica las
  constantes y el mapeo (ver §5).
- **`main()`** — CLI: `--entrada`, `--salida`, `--fecha` (por defecto hoy), `--usuario` (por
  defecto 999). Reporta objeciones, facturas y suma.

---

## 4. Flujo completo (paso a paso)

### 4.1 Preparación de datos (opcional, según el insumo)
- **Si el insumo es el PDF Trámite de Objeción** → correr `extraer_respuestas_glosa_mutualser.py`
  (`--pdf` o `--carpeta` + `--salida`). Produce `respuestas_mutualser.xlsx`. Se verifican los
  totales contra el PDF oficial.

### 4.2 Envío de la subsanación (robot)
1. **Arranque del navegador (modo `--cdp`, recomendado por el reCAPTCHA):** el usuario abre su
   Chrome con `--remote-debugging-port=9222 --user-data-dir=...`, inicia sesión a mano en el
   portal (resuelve el captcha) y abre el módulo. El robot **se conecta** a ese Chrome
   (`connect_over_cdp`), elige la pestaña del portal y no lo cierra al terminar.
2. **Lectura del Excel** (`leer_excel_respuestas`): agrupa la respuesta (glosa ratificada = 1
   grupo). Se calcula `valor = $0` y `texto = detalle` del grupo.
3. **Guarda de uniformidad** (`procesar_factura`): si hay respuestas no uniformes, se **omite**
   la factura (no se envía). Se trunca el texto a 1000 caracteres si excede.
4. **Abrir factura** (`_abrir_factura`): navega a la grilla, hace clic en la factura, espera
   SUBSANAR GLOSA.
5. **Modo subsanar** (`subsanar_items`): clic en **SUBSANAR GLOSA** → espera estabilización →
   **expande todos los ítems padre** (cada "+" revela 1..N sub-filas; los ítems 799 traen 2).
6. **Llenado por glosa** (para cada sub-fila de detalle):
   - `_set_valor` → escribe **$0** en VALOR RATIFICADO ACEPTADO IPS (clase MUI estable) + Tab.
   - `_set_observacion` → abre el modal, escribe el texto de conciliación, **ACEPTAR**.
   - `_subir_soporte` (si `--soportes`) → nube → modal "SOPORTE - Cargar archivos" →
     `set_input_files` → **GUARDAR** → toast "carga exitosa".
7. **Código de subsanación** (`finalizar_factura` → `_seleccionar_codigo`): abre el dropdown
   inferior, elige **"RE9901 SUBSANADA TOTAL"**, **verifica** que el selector lo muestre y
   **aborta si no coincide**.
8. **Habilitación y evidencia:** espera a que **ENVIAR SUBSANACIÓN** (arriba a la derecha) se
   ponga verde; toma **`<factura>_pre_envio.png`** (prueba del código elegido antes de enviar).
9. **Envío:** clic en ENVIAR SUBSANACIÓN → posible confirmación → toast "Subsanación enviada a
   mutualser" → **`<factura>_ok.png`**.
10. **Reporte:** cada factura queda en `reporte_mutualser.csv` (estado OK / LLENADO_SIN_ENVIAR /
    ERROR). Sin `--finalizar`, el bot **solo llena y no envía**.

### 4.3 Conversión a formato interno (independiente)
- Correr `objeciones_a_formato_interno.py --entrada <Objeciones del portal.xlsx> --salida
  <OBJECIONES_XXXX.xlsx> [--fecha AAAA-MM-DD]`. Produce el Excel CRO* para importar al sistema
  de cartera.

---

## 5. Base de datos

**Este módulo no tiene base de datos propia.** No usa el ORM (SQLAlchemy) ni las migraciones
(Alembic) del proyecto principal, ni crea tablas. El "estado" vive en cuatro lugares:

1. **El portal de MUTUAL SER** (fuente de verdad del estado de cada factura/glosa).
2. **Archivos Excel** (contratos de datos del módulo):
   - **Excel de respuestas** (insumo del robot), 8 columnas: `Factura`, `# Objeción`, `Código
     Glosa`, `Código Respuesta`, `Servicio`, `Valor Objetado`, `Valor Aceptado`, `Detalle
     Respuesta`.
   - **Excel de objeciones del portal** (insumo del conversor): `Número de factura`,
     `Tecnología`, `Cantidad facturada`, `Valor Facturado`, `Valor glosado`, `Código de glosa`,
     `Observacion`.
   - **Excel formato interno CRO*** (salida del conversor), hoja `OBJECIONES`, 16 columnas en
     orden exacto: `CDCONSEC, CDFECDOC, CRNCXC, CROFECOBJ, CROREFERE, CROOBSERV, CROCLAOBJ,
     CRNCLAOBJ, GENUSUARIO4, CRNCONOBJ, SLNSERPRO, IDRIPS, CTNCENCOS, CROVALOBJ, CRDOBSERV,
     CROTIPOBJ`. **Mapeo:** `CRNCXC`=factura larga (HUS+10 dígitos), `CRNCONOBJ`=código de
     glosa, `SLNSERPRO`=tecnología, `CROVALOBJ`=valor glosado (entero), `CRDOBSERV`="código +
     observación", `CDFECDOC`=`CROFECOBJ`=fecha. **Constantes por fila:** `CDCONSEC`=1,
     `CROCLAOBJ`=0, `CROTIPOBJ`=0, `GENUSUARIO4`=999 (configurable), y vacías `CROREFERE`,
     `CROOBSERV`, `CRNCLAOBJ`, `IDRIPS`, `CTNCENCOS`.
3. **Reporte CSV** (`reporte_mutualser.csv`): `factura, grupos, items, estado, detalle`.
4. **Sesión y evidencias**: `mutualser_session.json` (storage_state), y en `EVIDENCIA_MUTUALSER/`
   los `*_pre_envio.png`, `*_ok.png`, `*_error.png`, `*_no_habilita.png` y los volcados de
   diagnóstico `dbg_*.html`.

Índices, migraciones y relaciones: **no aplican** a este módulo.

---

## 6. Backend

**El módulo no tiene backend propio.** Integra con el backend del **portal de MUTUAL SER**
(aplicación React/MUI servida en `portalzonaser.mutualser.com`). Documentación de esa
integración:

- **"Endpoints"/URLs del portal usadas** (constantes):
  - `PORTAL_BASE = https://portalzonaser.mutualser.com`
  - `PORTAL_LOGIN = {BASE}/auth/login`
  - `PORTAL_DASHBOARD = {BASE}/dashboard`
  - `PORTAL_MODULO = {BASE}/dashboard/applications/auditoria-de-cuentas-medicas/GESTION-RESPUESTAS-GLOSAS`
- **Autenticación:** el portal usa **reCAPTCHA** en el login, que **no valida en navegador
  automatizado**. Solución adoptada: modo **CDP** (el humano se autentica en su Chrome; el bot
  opera esa sesión). Alternativa: `storage_state` persistido tras un login interactivo con
  `--con-cabeza`.
- **Validaciones del módulo** (equivalente a validaciones de backend):
  - Uniformidad de la respuesta (aborta si no es uniforme).
  - Verificación del **código** mostrado antes de enviar (aborta si no es RE9901).
  - Longitud de observación ≤ 1000 (trunca con aviso).
  - `MAX_PDF_MB = 10` (tope de tamaño previsto para el soporte).
- **Manejo de errores:** cada factura se procesa en `try/except`; el error queda en el reporte
  y se captura `<factura>_error.png`; los selectores que fallan vuelcan `dbg_*.html`.
- **Permisos:** credenciales sólo por variables de entorno; en modo CDP ni siquiera se
  requieren (login humano).

---

## 7. Frontend

**El módulo no tiene frontend propio.** Su trabajo es **operar el frontend del portal** (React
+ Material-UI). Elementos de esa interfaz que el robot maneja:

- **Pantalla grilla** de facturas glosadas → se hace clic en la factura por su texto corto.
- **Pantalla "Detalle de respuesta de glosa"** con **una tabla ancha de ~24 columnas** (scroll
  horizontal). Índices de columna usados: `COL_TECNOLOGIA=2` (botón "+"), `COL_VALOR_ACEPTADO=19`,
  `COL_OBSERVACION=21`, `COL_SOPORTE=22`.
- **Botón "SUBSANAR GLOSA"** (entra a modo edición).
- **Botón "+"** por ítem: **inserta sub-filas de detalle** (no es acordeón; pueden quedar varias
  abiertas; los ítems de tecnología 799 traen **2 glosas**).
- **Input de valor**: `input.MuiInputBase-inputAdornedEnd` (clase MUI estable).
- **Modal de OBSERVACIONES**: se opera por la **`textarea:visible`** + botón **ACEPTAR** (el
  modal **no** expone `role=dialog` fiable, y hay decenas de textareas ocultas).
- **Celda SOPORTE**: 3 `MuiIconButton` en `<span aria-label>`: `Ver documentos`, **subir
  (nube)** y `Limpiar soporte` → modal "SOPORTE - Cargar archivos" → **GUARDAR** → **toast** de
  carga exitosa.
- **Dropdown CÓDIGO SUBSANACIÓN** (abajo, junto a "ACEPTAR TOTAL RATIFICADO"): opciones
  `RE9602 INJUSTIFICADA` y **`RE9901 SUBSANADA TOTAL`**. **Hallazgo:** el dropdown **por
  defecto muestra RE9602** (primera opción); tras enviar, se **resetea** a ese valor por
  defecto — lo cual causó una falsa alarma (ver §13 y la nota de decisiones).
- **Botón "ENVIAR SUBSANACIÓN"** (arriba a la derecha): arranca deshabilitado (gris) y sólo se
  pone **verde** cuando **todas** las glosas están completas y se eligió el código.
- **Estrategia de selectores:** las clases CSS son **hasheadas/inestables** (`jss48`,
  `css-mfslm7`) y los ids autogenerados (`:r4g:`) → **prohibido** usarlas. Se usan **texto/rol**
  (`get_by_role`, `get_by_text`), **clases utilitarias MUI estables**
  (`MuiInputBase-inputAdornedEnd`, `MuiSelect-select`), **`aria-label`** y **posición de celda**.
- **"Animaciones"/asincronía:** el robot **espera por evento** los modales y toasts (aparición
  del título del modal, visibilidad/ocultamiento de GUARDAR, toast "exitosa", habilitación del
  botón), no por tiempos fijos.

---

## 8. IA

- **En tiempo de ejecución, este módulo NO usa IA.** No llama a ningún modelo de lenguaje; no
  hay prompts, temperatura, proveedores ni fallback de IA en el código del robot/extractor/conversor.
- **Durante el desarrollo** sí se usó IA: la construcción y la **revisión de código** se hicieron
  con **Claude Code**. En la fase de optimización se lanzó un **subagente de revisión de código**
  que produjo **13 hallazgos** (correctitud, robustez y rendimiento); se aplicaron los seguros y
  se **descartó** el hallazgo de "comparar conteo de glosas del portal vs Excel" (ver §13/decisiones).
- **Contexto del proyecto principal (no de este módulo):** la aplicación FastAPI del repositorio
  sí integra proveedores de IA (según los logs de CI: `primary=gemini | anthropic | gemini | groq`),
  pero eso pertenece a otros módulos y **no** es tocado ni usado por esta entrega.

---

## 9. Automatizaciones

- **Subsanación de glosas (automatización principal):** el robot llena y envía la respuesta en el
  portal. **Se ejecuta manualmente** desde la terminal (CLI), conectado al Chrome del usuario.
  Modos: piloto (`--max-items N`, sin `--finalizar`), factura completa (`--solo ... --finalizar`),
  cierre sin re-llenar (`--solo-finalizar`), masivo (`--todas`).
- **Extracción de PDF → Excel:** automatiza la transcripción de los trámites de objeción.
- **Conversión objeciones → formato interno CRO*:** automatiza el armado del archivo de importación.
- **Reporte CSV + evidencias:** se generan automáticamente en cada corrida.
- **CI (calidad):** el flujo `.github/workflows/ci.yml` corre en cada push: **Lint (ruff)**
  (`ruff check . --select F,W6` y `ruff format --check .`), **Tests (pytest)** y **pip-audit**.
  Este módulo mantiene **ruff en verde** en los archivos que toca.
- **Sin schedulers/cron propios:** el módulo no programa tareas; la app principal tiene
  schedulers, pero no forman parte de esta entrega.

---

## 10. Archivos modificados (con detalle de qué cambió)

Cronología por commit en la rama `claude/mutual-ser-glosa-responses-fa4k2g`:

| Commit | Archivos | Qué cambió |
|---|---|---|
| `e225bb0` | `docs/CONTEXTO_MUTUAL_SER.md` (+168), `extraer_respuestas_glosa_mutualser.py` (+307), `responder_glosas_mutual_ser.py` (+570) | Creación: extractor de PDF + andamiaje del robot + doc de contexto. |
| `db4e832` | contexto + responder | Documentar el flujo real de subsanación observado en el portal. |
| `5b85ac4` | responder | Modo `--cdp` para el reCAPTCHA (conectar al Chrome real). |
| `261b257` | responder | `--cdp` robusto a `localhost`→IPv6 (fallback `127.0.0.1`). |
| `e80d7d7` | contexto | Registrar hallazgos del DOM (React/MUI). |
| `074cccd` | responder | `--explorar` captura `data-testid` de los SVG. |
| `648da35` | responder | `--explorar` vuelca el HTML crudo de tabla y modal. |
| `91c18d9` | responder | Implementar el flujo de subsanación v1 (calibrado con el DOM). |
| `cd57efd` | responder | Selector robusto de valor (clase MUI estable) + diagnóstico de tabla. |
| `18d40c4` | responder | Llenar la SUB-FILA de detalle activa (fix selector de observación). |
| `7f2da2d` | responder | Operar el modal por `textarea`+ACEPTAR (no `role=dialog`). |
| `f5fc589` | responder | Tomar la `textarea:visible` (había decenas ocultas) + dump modal. |
| `dbc328b` | responder | Llenar la sub-fila de detalle **propia** de cada ítem (no acordeón). |
| `6e32362` | contexto + responder | **ENVIAR SUBSANACIÓN** (no "ACEPTAR TOTAL RATIFICADO") + subir soporte PDF por ítem (`--soportes`). |
| `17d38b2` | responder | Responder **TODAS** las glosas por ítem (los 799 traen 2): expandir todo + `_detail_rows`. |
| `736874e` | contexto + responder | Elegir **CÓDIGO SUBSANACIÓN (RE9901)** antes de enviar (`--codigo`). |
| `9ecead2` | responder | **Verificar** el código elegido + foto **pre-envío** (anti código equivocado). |
| `2cf7b95` | responder | Selector de código **robusto** + `--solo-finalizar`. |
| `ca4c5e2` | responder | **Robustez + velocidad** (revisión de código): guarda de uniformidad, truncado a 1000, reporte durable, corte si Chrome se cierra, screenshot de error, CDP elige pestaña del portal, esperas por evento en soporte/expansión/código, `wb.close()`, código de salida ≠0. |
| `686f1c8` | `tools/objeciones_a_formato_interno.py` (+240) | **Nuevo** conversor de objeciones a formato interno CRO*. |
| *(posterior)* | `BITACORA.md`, `CLAUDE.md`, este documento | Memoria común, instrucciones de sesión y documentación oficial. |

> Nota: se agregó y luego **se revirtió** una constante de texto (`TEXTO_RATIFICADA_HUS`) en el
> extractor, tras cambiar el enfoque de salida (ver §15 y decisiones); el extractor quedó como
> estaba.

---

## 11. Dependencias nuevas

| Paquete | Versión | ¿Nueva? | Para qué |
|---|---|---|---|
| **playwright** (Python) + **Chromium** | (no fijada; se instala aparte) | **Sí** (solo para este módulo, no en `requirements.txt`) | Automatizar el navegador y conectarse por CDP. Instalar con `pip install playwright` + `playwright install chromium`. |
| **pdfplumber** | 0.11.5 | No (ya en `requirements.txt`) | Extraer texto de los PDF Trámite de Objeción. |
| **openpyxl** | 3.1.5 | No (ya en `requirements.txt`) | Leer/escribir Excel. |

No se agregó ninguna dependencia a `requirements.txt`. **Decisión:** Playwright es una
dependencia **solo de herramientas** (no del servidor web), por eso no se sumó a
`requirements.txt` (que instala la CI). Se documenta su instalación manual.

---

## 12. Configuración

- **Variables de entorno** (solo modo sin CDP; **nunca** en código):
  - `MUTUALSER_USER` — usuario del portal.
  - `MUTUALSER_PASSWORD` — contraseña del portal.
- **Preparación de Chrome para `--cdp`:**
  `chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\temp-notas\zonaser-chrome"`,
  luego iniciar sesión a mano y abrir el módulo.
- **Rutas / archivos:**
  - `--excel` Excel de respuestas (insumo del robot).
  - `--soportes` carpeta con los PDF de soporte (`<factura>.pdf`).
  - `--storage-state` (por defecto `mutualser_session.json`).
  - `--evidencias` (por defecto `EVIDENCIA_MUTUALSER/`).
  - `--reporte` (por defecto `reporte_mutualser.csv`).
  - `--log` archivo de log adicional.
- **Parámetros de comportamiento:** `--cdp URL`, `--canal` (chrome/msedge), `--con-cabeza`,
  `--lento`, `--max-items N`, `--codigo` (por defecto `RE9901`), `--finalizar`,
  `--solo-finalizar`, `--explorar`; selección de facturas `--solo/--facturas/--lista/--todas`.
- **Conversor CRO*:** `--entrada`, `--salida`, `--fecha AAAA-MM-DD` (por defecto hoy),
  `--usuario` (por defecto 999).
- **Tokens:** este módulo **no** usa tokens ni claves de API.
- **Config de calidad:** `pyproject.toml` → ruff `line-length = 100`, `target-version = "py311"`,
  lint selección **F, W6** (más `ruff format`).

---

## 13. Riesgos

1. **Cambios del DOM del portal (riesgo #1):** MUTUAL SER puede reordenar columnas, renombrar
   botones o cambiar el flujo. *Mitigación:* selectores por texto/rol/`aria-label`/clase MUI
   estable + índices de columna documentados; modo `--explorar` para re-calibrar; volcados
   `dbg_*.html` ante fallo.
2. **reCAPTCHA:** bloquea el login automatizado. *Mitigación:* modo `--cdp` (login humano) o
   `storage_state`. No se usan servicios de resolución de captcha.
3. **Paginación de la tabla de detalle (TODO conocido):** el robot procesa la **página actual**;
   si una factura paginara el detalle, faltarían glosas. *Mitigación actual:* si faltan glosas,
   ENVIAR no se habilita y la factura queda en ERROR (no envía incompleto). Pendiente: soportar
   >1 página.
4. **Re-subida de soporte:** en un re-envío, `_subir_soporte` vuelve a cargar el PDF; si el
   portal **agregara** en vez de **reemplazar**, podría duplicar el soporte. *Mitigación:*
   `--solo-finalizar` evita re-llenar; verificar visualmente.
5. **Formato CRO* — supuestos a confirmar:** (a) `CRDOBSERV` se arma como "código + observación"
   (el ejemplo real incluía además el `$valor` y a veces unía dos glosas); (b) la **fecha** se
   parametriza (`--fecha`) y por defecto es hoy. *Mitigación:* revisar con el sistema interno.
6. **Guarda de uniformidad:** si una factura tuviera respuestas distintas por ítem, el robot la
   **omite** (por diseño, para no enviar datos equivocados). *Implicación:* esas facturas
   requieren tratamiento manual o una extensión del módulo.
7. **Credenciales:** deben permanecer solo en variables de entorno. *Riesgo si se ignora:* fuga
   de credenciales en el repo.
8. **Falsa alarma del código (documentada):** el dropdown muestra `RE9602` por defecto tras
   enviar; **no** significa que se envió RE9602. *Mitigación implementada:* lectura+verificación
   del valor antes de enviar y foto `pre_envio` como prueba.

---

## 14. Dependencias con otros módulos

- **Necesita (aguas arriba):**
  - El **portal de MUTUAL SER** (fuente de verdad y destino del envío).
  - El **Chrome del usuario** (para el modo CDP / reCAPTCHA).
  - Los **PDF Trámite de Objeción** y/o los **Excel de objeciones** descargados del portal.
- **Lo utilizan (aguas abajo):**
  - El **sistema interno de cartera del HUS** consume el Excel **CRO*** producido por el conversor.
  - El personal de Cartera/Auditoría opera los scripts.
- **Relación con módulos hermanos:** el repositorio ya tenía automatizaciones para otras EPS
  (**Coosalud**, **Simed**, **Dispensario/DGH**) siguiendo el mismo patrón (extractor + robot).
  Este módulo es **independiente** de ellos (no comparten código, solo el estilo).
- **Relación con la app FastAPI del repositorio:** **ninguna en runtime.** Este módulo son
  scripts CLI en `tools/`, **no** son importados por `motor_glosas` (la app). Por eso los cambios
  de esta entrega **no pueden** afectar el comportamiento ni los tests de la app.

---

## 15. Pendientes

- **Envío final de `HUS0000492542`** (185 objeciones / $37.379.742): ya quedó **llenada** en el
  portal (77 glosas cargadas); falta el **envío** con `--solo-finalizar` y verificar
  `HUS0000492542_pre_envio.png` = "RE9901 SUBSANADA TOTAL".
- **Confirmar el formato CRO*** con el sistema interno: si `CRDOBSERV` requiere el sufijo
  `$valor`, y poner la **fecha real** de la objeción.
- **Lote masivo** de MUTUAL SER con `--todas` (con soportes).
- **Soporte de paginación** en la tabla de detalle (>1 página) — TODO.
- **Formato del bot desde el Excel de objeciones** (no construido): el usuario primero eligió
  "formato del bot", pero luego entregó el ejemplo del formato interno CRO*; se **cambió el
  enfoque** hacia CRO*. Queda disponible construir el conversor objeciones→formato-del-bot si se
  necesita responder facturas cuyo insumo es Excel (no PDF).
- **Errores conocidos / no propios:** 3 tests de la app (`test_por_dia_semana`,
  `test_heatmap_actividad`) fallan en CI por **fechas fijas** fuera de la ventana móvil de 90
  días de la API de estadísticas. **No** pertenecen a este módulo ni fueron causados por él; se
  decidió **no** tocarlos. Se pueden arreglar en un cambio aparte (usar fechas relativas).

---

## 16. Recomendaciones para fusionarlo

1. **Bajo riesgo de integración:** esta entrega **solo agrega/modifica** `tools/*.py`,
   `docs/*.md`, `BITACORA.md` y `CLAUDE.md`. **No** toca código de la app, ni modelos, ni
   migraciones, ni endpoints. Por lo tanto no hay conflictos con la lógica del proyecto principal.
2. **Revisar el PR #154** y hacer merge de `claude/mutual-ser-glosa-responses-fa4k2g` hacia
   `motor-glosas`. La CI en **rojo** es por los 3 tests pre-existentes de fechas (no de este
   módulo); si se requiere CI verde antes del merge, arreglar esos tests en un **cambio separado**
   (fechas relativas) — no mezclar con esta entrega.
3. **Dependencias:** confirmar que `pdfplumber==0.11.5` y `openpyxl==3.1.5` siguen en
   `requirements.txt` (ya están). Documentar en el README que **Playwright + Chromium** se
   instalan aparte para las herramientas (no van a `requirements.txt` del servidor).
4. **Calidad:** mantener `ruff check --select F,W6` y `ruff format` en verde en `tools/`.
5. **Operación:** conservar el modo `--cdp` como estándar (por el reCAPTCHA) y la práctica de
   **piloto** (`--max-items`) antes de un masivo.
6. **Memoria de trabajo:** mantener el flujo de **`CLAUDE.md` → leer/actualizar `BITACORA.md`**
   para que futuras sesiones tengan contexto.
7. **No romper reglas:** credenciales solo en variables de entorno; no incluir el identificador
   del modelo de IA en artefactos del repo.

---

## 17. Resumen ejecutivo (para quien lo mantenga)

- **Qué es:** tres scripts CLI en `tools/` que (1) extraen respuestas desde los PDF de trámite,
  (2) **llenan y envían** la subsanación de glosas ratificadas en el portal de MUTUAL SER, y
  (3) convierten las objeciones del portal al formato interno **CRO\***.
- **Cómo corre:** conectado por **CDP** al Chrome real del usuario (por el reCAPTCHA). Sin
  `--finalizar` solo llena; con `--finalizar` elige el código y envía; `--solo-finalizar` cierra
  una factura ya llena.
- **La respuesta siempre es la misma** (glosa ratificada, rechazo total): **Valor Aceptado $0**,
  **código RE9901 (SUBSANADA TOTAL)**, y un **texto de conciliación fijo** de ~831 caracteres.
- **Gotchas clave que hay que conocer:**
  - Los **ítems de tecnología 799 traen 2 glosas** cada uno; hay que responderlas **todas**
    (se expande todo y se llenan las `_detail_rows`).
  - El botón de envío correcto es **ENVIAR SUBSANACIÓN** (arriba a la derecha), **no** "ACEPTAR
    TOTAL RATIFICADO".
  - Antes de enviar **hay que elegir el código** en el dropdown inferior; el dropdown **muestra
    RE9602 por defecto** (falsa alarma) — por eso el bot **verifica** el valor y toma foto
    **pre-envío**.
  - Los **selectores** deben seguir siendo por **texto/rol/aria-label/clase MUI estable**; nunca
    por clases hasheadas ni ids autogenerados.
  - El modal de observación se opera por **`textarea:visible` + ACEPTAR** (no hay `role=dialog`).
- **Resultados validados:** extracción **exacta al peso** contra los PDF (HUS0000492542 = 185 obj
  / $37.379.742; HUS0000510639 = 18 obj / $2.482.335). **HUS0000510639 fue enviada por el robot**
  de punta a punta (21 glosas, ~5 min, RE9901). **HUS0000492542** quedó llenada (77 glosas),
  pendiente de envío. **OBJECIONES_HUS520567** generada en formato CRO* (84 objeciones).
- **Decisiones y enfoques descartados (memoria de ingeniería):**
  - *Login automatizado* → **descartado** (reCAPTCHA); se adoptó **CDP**.
  - *CDP por `localhost`* → fallaba en IPv6; se agregó **fallback `127.0.0.1`**.
  - *Modal por `role=dialog`* → **descartado**; se usa **`textarea:visible` + ACEPTAR**.
  - *Suponer acordeón / llenar "la primera fila activa"* → **descartado**; se llena la **sub-fila
    propia** de cada ítem y luego **todas** las glosas (por los ítems con 2 glosas).
  - *Botón "ACEPTAR TOTAL RATIFICADO"* → **descartado** como finalizador; el correcto es **ENVIAR
    SUBSANACIÓN**.
  - *Comparar conteo de glosas del portal vs Excel* (hallazgo de la revisión de código) →
    **descartado**: el portal **consolida** (18 obj→21 glosas; 185 obj→77 glosas), la comparación
    daría falsas alarmas.
  - *Tiempos de espera fijos* → reemplazados por **esperas por evento** (más rápido y robusto).
  - *Salida "formato del bot" desde el Excel de objeciones* → se **cambió** al **formato interno
    CRO\*** al recibir el ejemplo real diligenciado.

---

*Fin de la documentación oficial del módulo.*
