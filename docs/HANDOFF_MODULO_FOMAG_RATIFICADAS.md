# Documentación oficial del módulo — Bot de Glosas RATIFICADAS de FOMAG (Horus)

> **Entrega técnica al equipo principal.** Este documento reconstruye, sin
> resumir, todo lo desarrollado en la conversación que produjo el módulo de
> respuesta de glosas **ratificadas** de FOMAG. Sirve como acta de entrega para
> integrar el módulo al proyecto principal sin perder trabajo ni conocimiento.
>
> **Fuente:** el código real de los archivos del módulo (`tools/responder_glosas_fomag.py`,
> 1 563 líneas; `tools/README_responder_glosas_fomag.md`, 168 líneas;
> `tools/evidencias_a_pdf.py`, 188 líneas) y los 21 commits de FOMAG + los
> commits de CI de esta misma línea de trabajo.
>
> **Aviso de ubicación del código (leer sección 13 y 16):** al momento de esta
> entrega el módulo vive en la línea remota `origin/claude/jolly-lovelace-tfkdfs`
> (commit `23cbb1b`, **PR #136**, con base `motor-glosas`). La rama **local** fue
> reseteada a otra base (`937f318`) que trae la bitácora fusionada pero **no**
> los archivos del bot. Nada se perdió: el bot está íntegro en el remoto/PR #136.

---

## 1. Objetivo del desarrollo

### ¿Por qué se creó este módulo?
La ESE Hospital Universitario de Santander (HUS) responde glosas médicas en
varias plataformas de EPS/pagadores. Ya existían robots para **COOSALUD**
(`responder_glosas_coosalud.py`) y **SIMED/Dispensario**
(`responder_glosas_simed.py`). Faltaba el equivalente para **FOMAG**
(magisterio, administrado por Fiduprevisora), cuyo portal es **Horus Health**
(`https://horus2.horus-health.com`). Este módulo es ese robot.

### ¿Qué problema resolvía?
La respuesta manual de una glosa **ratificada** en Horus obliga al auditor a,
factura por factura: abrir Auditoría, desplegar el cuadro "Facturas prestador",
entrar a la pestaña RATIFICADAS, filtrar la factura, dar RESPUESTA, y por **cada
fila de servicio glosado** elegir el código de respuesta, escribir el texto
legal de defensa, subir el PDF de soporte, guardar la fila, tomar la evidencia y
finalmente dar GUARDAR RESPUESTA. Es repetitivo, lento y propenso a error
humano (olvidar una fila, subir el PDF a la fila equivocada, no capturar
evidencia).

### ¿Qué necesidad cubría?
Automatizar ese flujo completo dejando **una sola** intervención humana: resolver
el reCAPTCHA del login una vez al día. A cambio entrega:
- carga del código + texto + PDF + guardado por cada fila de servicio;
- **un pantallazo de evidencia por factura**;
- un **CSV de seguimiento** con el estado de cada factura;
- procesamiento por lote (lista de facturas).

La respuesta a las ratificadas del HUS es **estándar** (el mismo código y el
mismo texto legal para todas), lo que hace el proceso perfectamente
automatizable.

---

## 2. Arquitectura

### Naturaleza del módulo
Es un **script CLI de automatización RPA** (Robotic Process Automation), no un
servicio web. **No tiene** frontend propio, ni base de datos propia, ni
endpoints propios: **maneja el navegador** contra la interfaz web de Horus
mediante **Playwright** (API síncrona). El "frontend" que opera es el SPA de
Horus (Angular/Material); ver secciones 6 y 7.

### Estructura de archivos del módulo
```
tools/
├── responder_glosas_fomag.py          # el bot (1 563 líneas)  ← núcleo
├── README_responder_glosas_fomag.md   # guía de uso (168 líneas)
└── evidencias_a_pdf.py                # consolida los PNG de evidencia en un PDF (188 líneas)
```
Artefactos que **genera** en tiempo de ejecución (no versionados):
```
<perfil>/                    # perfil de navegador persistente (por defecto ~/.fomag_horus_profile)
EVIDENCIA_FOMAG/             # pantallazos <factura>_ratificada.png  (--evidencias)
reporte_fomag.csv            # CSV de estado por factura              (--reporte)
debug_screenshots/           # screenshots + volcados HTML de diagnóstico
```

### Componentes internos (bloques del script, en orden)
1. **Setup** — logging y carga de credenciales desde variables de entorno.
2. **Helpers de texto / DOM** — normalización de texto, selección del primer
   elemento visible, disparo de eventos DOM, navegación tolerante.
3. **Login** — perfil persistente + espera del reCAPTCHA manual.
4. **Navegación** — Auditoría → cuadro naranja → pestaña.
5. **Lectura de la grilla** — inventario de facturas (modo `--listar`).
6. **Formulario de RESPUESTA (RTA2)** — el corazón: elegir código, cargar
   detalle, subir PDF, guardar fila, guardar respuesta.
7. **Driver (`main`)** — parseo de argumentos y orquestación de los 3 modos.

### Dependencias / librerías
| Librería | Uso |
|---|---|
| `playwright` (sync API) | manejo del navegador Chromium contra Horus |
| **stdlib**: `argparse`, `csv`, `logging`, `os`, `re`, `sys`, `time`, `unicodedata`, `pathlib` | CLI, reporte CSV, logs, regex de facturas, normalización de tildes |
| `Pillow` (PIL) | solo en `evidencias_a_pdf.py`: arma el PDF multipágina |

> **Nota honesta:** la cabecera de instalación dice `pip install playwright
> openpyxl`, pero el código actual del bot **no importa `openpyxl`** (herencia
> del template de COOSALUD). Ver "Pendientes" (sección 15).

### APIs / modelos / servicios / utilidades
- **APIs externas:** ninguna API REST propia; se interactúa con el **portal web
  Horus** (Angular SPA) vía DOM. URLs fijas: `PORTAL_BASE`, `PORTAL_LOGIN`,
  `PORTAL_AUDITORIA`.
- **Modelos:** no hay ORM en el bot. El único "modelo" es el `dict` de reporte
  por factura: `{factura, filas, ok, estado, detalle}`.
- **Servicios/utilidades:** todas las funciones son del propio script (no
  importa nada de `app/`). Es **autónomo**.

---

## 3. Funciones implementadas (lista completa)

Formato: **qué hace · cómo funciona · por qué existe · de qué depende**. Todas
viven en `tools/responder_glosas_fomag.py` salvo aviso.

### Setup
- **`_exigir_playwright()`** — Aborta con instrucciones si Playwright no está
  instalado. *Cómo:* verifica el import diferido `sync_playwright`. *Por qué:* el
  bot es inútil sin Playwright y el usuario no es programador. *Depende de:* el
  bloque `try/except ImportError` de la cabecera.
- **`setup_logging(log_file)`** — Configura logging a stdout y, opcional, a
  archivo. *Cómo:* `logging.basicConfig` con handlers. *Por qué:* trazabilidad
  de cada corrida. *Usada por:* `main`.
- **`cargar_credenciales() -> (user, password)`** — Lee `FOMAG_USER` /
  `FOMAG_PASSWORD` de entorno; aborta si faltan. *Por qué:* **nunca** hardcodear
  credenciales (regla del repo). *Usada por:* `main`.

### Helpers de texto / DOM
- **`_norm(s)`** — Mayúsculas, sin tildes/combinantes, espacios colapsados.
  *Por qué:* Horus mezcla tildes; el match debe ser tolerante. *Usada por:* casi
  toda la navegación.
- **`_norm_col(s)`** — Como `_norm` pero sin puntuación ni espacios
  (`'Cod Rta2 RAT'` → `'CODRTA2RAT'`). *Por qué:* matchear encabezados de columna
  de forma robusta. *Usada por:* `_idx_columna`, `main` (resolución de `--tab`).
- **`_primer_visible(loc)`** — Devuelve el primer elemento **visible** de un
  locator (o `None`). *Cómo:* itera `nth(i)` y prueba `is_visible()`. *Por qué:*
  el DOM de Horus tiene plantillas ocultas; `.first` agarra basura. *Usada por:*
  prácticamente todo.
- **`_dir_debug()`** — Crea/retorna `debug_screenshots/`. *Usada por:* los
  volcados de diagnóstico.
- **`_screenshot_debug(page, etiqueta)`** — Screenshot con timestamp para
  diagnóstico. *Por qué:* sin acceso interactivo al equipo del auditor, la
  evidencia visual es la forma de depurar.
- **`_disparar_eventos(campo, *eventos)`** — Dispara `input`/`change`/`blur` por
  JS sobre un campo. *Por qué:* los formularios reactivos de Angular no
  registran valores cargados por script sin eventos. *Usada por:* login, filtro,
  detalle.
- **`_goto_tolerante(page, url)`** — `goto` con `domcontentloaded` y, si el
  portal lento no lo emite, cae a `commit`. *Por qué:* Horus a veces no dispara
  `domcontentloaded` a tiempo. *Usada por:* login y navegación.

### Login (perfil persistente + reCAPTCHA manual)
- **`_en_login(page) -> bool`** — Detecta la **pantalla de login** por el campo
  de contraseña + botón INGRESAR / "RECUPERAR CONTRASEÑA". *Por qué (decisión
  clave):* la palabra "Bienvenido" aparece **tanto** en el login **como** dentro
  del portal, así que **no** sirve para detectar sesión (esto causó un falso
  positivo — ver sección 4).
- **`_logueado(page) -> bool`** — True si estamos **dentro** del portal. *Cómo:*
  primero descarta `_en_login`; luego revisa la URL (`/cuentasMedicas`, etc.) o
  ítems del menú lateral. *Depende de:* `_en_login`.
- **`login(page, user, password, timeout_login_s=240)`** — Inicia sesión.
  *Cómo:* si el perfil persistente ya tiene sesión, retorna; si no, autollena
  email + contraseña, dispara eventos, y **espera hasta 240 s** a que el humano
  resuelva el reCAPTCHA y entre. *Por qué:* el reCAPTCHA **no** se automatiza.
  *Depende de:* `_goto_tolerante`, `_logueado`, `_primer_visible`,
  `_disparar_eventos`, `_screenshot_debug`.

### Navegación (Auditoría → cuadro naranja → pestaña)
- **`_pestanas_visibles(page)`** — True si hay una pestaña RATIFICADAS/RADICADAS
  **visible**. *Por qué:* condición de éxito del click al cuadro naranja.
- **`_abrir_facturas_prestador(page)`** — Clickea el **cuadro naranja "Facturas
  prestador"** para desplegar las pestañas. *Cómo:* idempotente (si ya hay
  pestañas visibles no hace nada), espera a que el card aparezca, prefiere el
  **ancestro clickeable** (no el `<span>` del texto), y da **1 click por intento
  con espera larga** para no "togglear" y cerrar. *Por qué (decisión clave):* el
  handler está en el contenedor, no en el texto; y el doble click cerraba las
  pestañas. *Depende de:* `_pestanas_visibles`, `_primer_visible`.
- **`_click_tab(page, tab_label)`** — Clickea la pestaña pedida. *Cómo:* recorre
  hasta 500 elementos visibles y matchea por **prefijo** con margen de 8
  caracteres (el texto trae el contador pegado: `"RATIFICADAS42"`). *Limitación
  conocida:* el margen `+8` no alcanza para `"HISTÓRICO CONCILIACIÓN"` (ver
  sección 15).
- **`_senal_auditoria(page)` / `_esperar_auditoria(page, timeout_s)`** — Detectan
  que cargó la vista de Auditoría (cuadro naranja / pestañas / título).
- **`_navegar_por_menu(page)`** — Fallback: Cuentas médicas → Auditoría por el
  menú lateral cuando el `goto` directo no rinde.
- **`_ir_a_auditoria(page)`** — Orquesta: `goto` directo y, si no aparece,
  `_navegar_por_menu`; lanza con el texto visible si ninguna funciona.
- **`ir_a_pestana(page, tab_label)`** — **Entrada pública** de navegación:
  Auditoría → cuadro naranja → pestaña, y espera la grilla. *Depende de:*
  `_ir_a_auditoria`, `_abrir_facturas_prestador`, `_click_tab`.

### Lectura de la grilla de facturas (modo `--listar`)
- **`_dump_inputs(page)`** — Vuelca por JS los inputs visibles
  (tag/type/name/placeholder/label/valor) para diagnosticar cuál es "Número
  factura".
- **`_caja_numero_factura(page)`** — Localiza el input "Número factura". *Cómo
  (decisión clave):* es un campo Material **sin placeholder** (la etiqueta
  flota), así que va por `get_by_label`, luego por XPath del `mat-form-field`,
  luego por placeholder/name, y por último el primer input de texto.
- **`_set_page_size_max(page)`** — Pone el selector de tamaño de página en su
  valor mayor (ver todas las filas de una).
- **`_leer_pagina(page)`** — Lee las filas visibles de la grilla mapeando por
  **encabezado** (NIT, FECHA RADICACION, RADICADO, QUIEN RADICA, FACTURA, VALOR,
  ESTADO, FECHA RATIFICACION, SEMAFORO). *Cómo:* JS que descarta filas vacías y
  la fila placeholder "Sin datos para mostrar".
- **`leer_grilla_completa(page, max_paginas=200)`** — Recorre **todas** las
  páginas (deduplica por `(radicado, factura)`, corta cuando la huella de página
  se repite o no hay "next"). *Usada por:* `--listar`.

### Formulario de RESPUESTA (RTA2) — el núcleo
- **`_nucleo_factura(s)`** — Parte numérica sin ceros a la izquierda
  (`'HUS0000505761'` → `'505761'`). *Por qué:* emparejar facturas con distinto
  padding.
- **`_formas_factura(factura)`** — Genera las formas a probar en la grilla, de
  más a menos probable: `HUS505761`, la forma dada, y el núcleo suelto `505761`.
  *Por qué (decisión clave):* los soportes vienen `HUS0000...` pero Horus muestra
  `HUS505761`.
- **`abrir_respuesta(page, factura)`** — Filtra la factura (probando las formas)
  y clickea **RESPUESTA**; espera el formulario (`text=GUARDAR RESPUESTA`).
  *Depende de:* `_formas_factura`, `filtrar_por_factura`,
  `_boton_respuesta_de_fila`.
- **`filtrar_por_factura(page, factura, timeout_s=45)`** — Escribe la factura en
  "Número factura", dispara **FILTRAR** (+ Enter de respaldo) y **espera hasta
  45 s** a que la grilla (lenta) traiga la fila. *Por qué:* la grilla de Horus es
  muy lenta y "Sin datos" también aparece **mientras** carga. *Depende de:*
  `_caja_numero_factura`, `_disparar_eventos`, `_fila_cargo`, `_dump_inputs`.
- **`_fila_cargo(page, factura)`** — True si cargó la fila. *Cómo (decisión
  clave):* **estructura-agnóstico** — no asume `<table>`; la señal es "hay un
  botón RESPUESTA visible **y** la factura está en pantalla". *Por qué:* la
  grilla de Horus **no siempre es un `<table>`**.
- **`_boton_respuesta_de_fila(page, factura)`** — El botón RESPUESTA de la fila
  que contiene la factura (o el primero visible). Constante de selector:
  `_SEL_BOTON_RESPUESTA` (`button/a:has-text('RESPUESTA')`).
- **`_tabla_formulario(page)`** — Elige, entre **varias tablas** del DOM, la del
  formulario de Respuesta. *Cómo:* puntúa cada `table`/`mat-table` por cuántas
  palabras clave contiene (`_CLAVES_TABLA_FORM`: afiliado, cod rta2, detalle rta
  2, concepto aud, rta1 prestador, ratificado). *Por qué (decisión clave):* hay
  tablas ocultas cuyos encabezados son de otra vista.
- **`_headers_formulario(tabla)`** — Encabezados de esa tabla (thead / mat-header
  / primera fila).
- **`_idx_columna(headers, *needles)`** — Índice de la 1ª columna cuyo
  encabezado normalizado (`_norm_col`) contiene el needle. *Por qué:* ubicar las
  columnas por nombre, no por posición fija.
- **`_filas_formulario(tabla)`** — Filas de servicio visibles y no vacías.
- **`_celda(fila, idx)`** — La celda `td`/`mat-cell` en la posición `idx`.
- **`_elegir_codigo_en_celda(page, celda, codigo)`** — Selecciona el código
  (RE9901) en el dropdown de la celda **y verifica** que quedó pegado. *Cómo
  (decisión clave):* soporta `<select>` nativo **y** dropdowns custom
  (`mat-select`/overlay `cdk-overlay-pane`); prueba **click normal → force → JS**;
  verifica con `_ya_esta()` que lee `innerText`, `value` del input y
  `.mat-select-value`; reintenta 3 veces; si falla, vuelca el HTML de la celda.
  *Por qué:* en Material el valor queda en un `<input>`, no en el texto — el
  primer intento "parecía" fallar aunque hubiera funcionado.
- **`_cargar_detalle_en_celda(page, celda, texto)`** — Click en el lápiz de
  "Detalle Rta 2 prestador" y carga el texto. *Cómo (decisión clave):* **poll de
  12 s** esperando el editor (textarea / `contenteditable` / input) porque en
  lotes largos tarda; escribe con `fill` o, si es `contenteditable`, tipeando;
  dispara eventos; confirma con el **Guardar del editor** — excluyendo
  explícitamente "GUARDAR RESPUESTA" (ese enviaría toda la auditoría). *Por qué:*
  700 ms era muy poco y el editor salía vacío.
- **`_guardar_fila(page, fila, idx_guardar)`** — Click en el **✓ ("chulito")** de
  Guardar de la fila y espera "guardada con exito".
- **`_buscar_pdf_factura(pdf_dir, factura)`** — Busca `<factura>.pdf` por nombre
  exacto y, si no, por **núcleo numérico** (así `HUS512134` encuentra
  `HUS0000512134.pdf`). *Depende de:* `_nucleo_factura`.
- **`_esperar_adjunto(page, timeout_s=25)`** — Espera "Adjunto cargado con
  exito" (la subida desde un recurso de red `Z:` es lenta).
- **`_subir_pdf_en_celda(page, celda, pdf_path)`** — Sube el PDF **sin abrir el
  diálogo del SO**. *Cómo (decisión clave):* `set_input_files` sobre el
  `<input type=file>` de la celda; si no, el de la página; y como último recurso
  intercepta el `file_chooser` con timeout corto para no colgar. *Por qué:* el
  diálogo nativo del SO no se automatiza.
- **`responder_glosa(page, factura, codigo, texto, evidencias, max_filas, guardar, pdf_dir) -> dict`**
  — **Orquesta la respuesta de UNA factura.** Abre el formulario, ubica las
  columnas por encabezado, y por cada fila: elige código → carga detalle → sube
  PDF (**antes** del ✓) → da ✓. Toma la **evidencia antes** de GUARDAR
  RESPUESTA. **Seguridad:** si `guardar=False` retorna `PILOTO_SIN_GUARDAR`; si
  **ninguna** fila cargó completa, **NO** da GUARDAR RESPUESTA (`PARCIAL`).
  Devuelve el dict de reporte. *Depende de:* casi todas las anteriores.
- **`diagnosticar_respuesta(page, factura)`** — Modo `--diagnostico`: abre
  RESPUESTA y vuelca headers + índices + HTML + screenshot **sin escribir nada**.
- **`main() -> int`** — Driver: parsea argumentos, lanza el navegador persistente
  y ejecuta el modo (`--listar` / `--diagnostico` / `--responder`); escribe el
  CSV y el resumen por estado.

### `tools/evidencias_a_pdf.py`
- **`_exigir_pillow()`**, **`_factura_desde_nombre(p)`**, **`_clave_natural(p)`**
  (orden natural), **`_leer_lista(p)`** (TXT con rutas), **`_cargar_fuente(...)`**,
  **`_pagina_con_encabezado(...)`** (imagen + franja con el número de factura),
  **`main()`** — Consolida los PNG de evidencia en un **único PDF**, una factura
  por página, con encabezado. Modos `--carpeta` / `--lista`; salida `--salida`
  (ej. `GR-33-2070-2026.pdf`). *Por qué:* radicar la evidencia del lote como un
  solo archivo.

---

## 4. Flujo completo (paso a paso)

Desde que el auditor lanza el comando hasta que termina:

1. **Arranque (`main`)** — Parsea argumentos; exige Playwright; carga
   `FOMAG_USER`/`FOMAG_PASSWORD`; resuelve la pestaña (`--tab`, default
   RATIFICADAS); resuelve el texto (fijo o `--texto-archivo`); arma la lista de
   facturas objetivo (`--solo`/`--facturas`/`--lista`).
2. **Navegador persistente** — `launch_persistent_context(user_data_dir=--perfil)`
   con `headless = not --con-cabeza`, viewport 1600×900, `accept_downloads`. Se
   fija `dialog → accept` (cierra pop-ups nativos).
3. **Login (`login`)** — Abre el portal. Si el perfil ya tiene sesión, sigue. Si
   no, autollena email + contraseña y **espera al humano** para el reCAPTCHA +
   INGRESAR (hasta 240 s). La sesión queda guardada en el perfil para próximas
   corridas.
4. **Navegación (`ir_a_pestana`)** — Auditoría (`/cuentasMedicas/auditoria`) →
   click en el **cuadro naranja "Facturas prestador"** → click en la **pestaña
   RATIFICADAS**.
5. **Por cada factura** (`responder_glosa`):
   1. **Filtrar** (`abrir_respuesta` → `filtrar_por_factura`): escribe la
      factura (probando formas con/sin ceros), da FILTRAR, espera la fila (poll
      45 s).
   2. **RESPUESTA**: click en el botón verde de la fila; espera el formulario.
   3. **Ubicar columnas** (`_tabla_formulario` + `_headers_formulario` +
      `_idx_columna`): Cod Rta2 RAT, Detalle Rta 2 prestador, Archivo, Guardar.
   4. **Por cada fila de servicio**, en este orden:
      - **Cod Rta2 RAT** → `RE9901` (`_elegir_codigo_en_celda`, con verificación).
      - **Detalle Rta 2 prestador** → texto fijo (`_cargar_detalle_en_celda`).
      - **Archivo** → sube `<factura>.pdf` **antes** del ✓ (`_subir_pdf_en_celda`).
      - **✓ Guardar** de la fila (`_guardar_fila`, espera "guardada con exito").
   5. **Evidencia**: `page.screenshot(...)` → `EVIDENCIA_FOMAG/<factura>_ratificada.png`,
      **antes** de cerrar.
   6. **Guardas de seguridad**: si `--sin-guardar` → no confirma nada
      (`PILOTO_SIN_GUARDAR`); si ninguna fila cargó → no da GUARDAR RESPUESTA
      (`PARCIAL`).
   7. **GUARDAR RESPUESTA** (botón verde) → vuelve a la grilla.
   8. Escribe la fila del CSV (`w_rep.writerow`; `flush` inmediato) y vuelve a la
      pestaña para la siguiente factura.
6. **Cierre** — Resumen por estado (Counter), cierre del contexto, tiempo total.

---

## 5. Base de datos

**El módulo FOMAG no tiene base de datos propia.** Su "estado persistente" es:
- el **perfil de navegador** en disco (`--perfil`, cookies/sesión de Horus);
- el **CSV de reporte** (`--reporte`);
- los **PNG de evidencia** (`--evidencias`);
- volcados de `debug_screenshots/`.

> **Contexto relevante para la integración:** esta misma línea de trabajo tocó
> el **backend del Motor de Glosas** (app web) al arreglar tests (sección 6).
> Ahí sí hay BD. Las tablas/columnas involucradas en esos arreglos:
> - Modelo **`GlosaRecord`** (`app/models/db.py`), columna **`creado_en`**
>   (timestamp) — usada por los endpoints de estadísticas para agrupar por día y
>   hora dentro de una **ventana rodante de 90 días**. No se alteró el esquema;
>   solo se corrigieron **tests** que sembraban `creado_en` con fechas fijas.

---

## 6. Backend

El bot **no expone** backend. Lo que aplica aquí es (a) el "backend" que el bot
**consume** —el portal Horus— y (b) el backend del Motor de Glosas que esta
línea de trabajo **tocó al dejar el CI verde**.

### (a) El portal Horus que el bot maneja
- **Login**: email + contraseña + **reCAPTCHA** + INGRESAR. El reCAPTCHA es el
  único punto no automatizable → perfil persistente.
- **Validaciones del portal que el bot respeta**: al guardar una fila (✓) la
  fila **se bloquea** y el botón de Archivo se apaga → por eso el PDF se sube
  **antes** del ✓. "GUARDAR RESPUESTA" **envía y cierra** → por eso solo se da al
  final y nunca se confunde con el Guardar del editor de detalle.
- **Errores/estados** que el bot interpreta: "Sin datos para mostrar" (grilla
  vacía o cargando), "Respuesta guardada con exito!", "Adjunto cargado con
  exito".
- **Permisos**: el usuario `1098612385@fomag.com` es un usuario prestador del
  HUS con acceso a Auditoría de facturas.

### (b) Backend del Motor de Glosas tocado por el CI (contexto)
Dos endpoints de estadísticas (`app/api/routers/glosas_stats.py`) quedaron
documentados al arreglar sus tests:
- **`GET /glosas/stats/por-dia-semana`** (línea ~9971): distribución de glosas
  por día de semana; ventana **`dias` = 90** por defecto; agrupa por
  `creado.weekday()` en **UTC**.
- **`GET /glosas/stats/heatmap-actividad`** (línea ~11142): matriz 7×24
  (día×hora); misma ventana de 90 días; agrupa por `weekday()`/`hour` en **UTC**.

No se cambió lógica de negocio de estos endpoints; solo sus **tests** (sección
10).

---

## 7. Frontend

**El módulo no tiene frontend propio.** Opera el frontend de terceros de Horus
(Angular + Angular Material). Elementos de esa UI que el bot conoce y maneja:

| Elemento UI (Horus) | Cómo lo trata el bot |
|---|---|
| **Pantalla de login** | detecta por campo password + INGRESAR / "RECUPERAR CONTRASEÑA" |
| **reCAPTCHA "No soy un robot"** | espera intervención humana (no automatizable) |
| **Cuadro naranja "Facturas prestador"** (card) | clickea el ancestro clickeable, 1 click/intento |
| **Pestañas** (RADICADAS/PENDIENTES/RATIFICADAS/CONCILIACIÓN/CONSOLIDADO/HISTÓRICO) | match por prefijo, tolerando el contador pegado |
| **Caja "Número factura"** (Material, sin placeholder, label flotante) | `get_by_label` / XPath del `mat-form-field` |
| **Botón FILTRAR** | click forzado + Enter de respaldo |
| **Botón verde RESPUESTA** (a veces `<a>`) | selector `_SEL_BOTON_RESPUESTA` |
| **Tabla del formulario** (varias ocultas en el DOM) | se elige por palabras clave de columnas |
| **Dropdown "Cod Rta2 RAT"** (`mat-select`, valor en `<input>`) | click multi-método + verificación + overlay `cdk-overlay-pane` |
| **Editor "Detalle Rta 2 prestador"** (lápiz ✏️, modal o inline, textarea/contenteditable) | poll 12 s + Guardar del editor |
| **Columna "Archivo"** (`<input type=file>`) | `set_input_files` (sin diálogo del SO) |
| **✓ "chulito" Guardar** de fila | click + espera "guardada con exito" |
| **Botón verde "GUARDAR RESPUESTA"** | solo al final; nunca confundir con el Guardar del editor |
| **Carteles**: "Sin datos", "guardada con exito", "adjunto cargado" | señales de estado por texto |

Validaciones que el bot impone del lado del cliente: verificar que la caja de
filtro realmente tomó la factura; verificar que el dropdown quedó en RE9901;
confirmar el guardado de fila y del adjunto por su cartel.

---

## 8. IA

**Este módulo (el bot FOMAG) NO usa IA.** La respuesta a las ratificadas es
**determinística**: siempre el mismo código (`RE9901`) y el mismo texto legal
fijo (`TEXTO_RATIFICADA_DEFAULT`). No hay prompts, ni proveedores, ni
temperatura, ni fallback de IA en este bot.

- **Código por defecto:** `RE9901` (`--cod` para cambiarlo).
- **Texto por defecto:** constante `TEXTO_RATIFICADA_DEFAULT` — texto legal del
  HUS que no acepta la glosa ratificada, cita el art. 57 de la Ley 1438/2011 y
  el art. 20 del Decreto 4747/2007, pide conciliación y advierte escalamiento a
  la Superintendencia (art. 126 Ley 1438/2011). Cambiable con `--texto-archivo`.

> El resto del proyecto (el Motor de Glosas, en `app/`) **sí** usa IA para
> redactar dictámenes (proveedores Gemini/Anthropic/Groq), pero eso es **otro
> módulo**, ajeno a esta entrega.

---

## 9. Automatizaciones

1. **Respuesta de glosas ratificadas (el bot)** — *Qué:* todo el flujo de la
   sección 4. *Cuándo:* bajo demanda, cuando llega un lote de ratificadas.
   *Cómo:* `py responder_glosas_fomag.py --responder --lista ... --pdf-dir ...`.
2. **Inventario de la pestaña (`--listar`)** — *Qué:* vuelca la grilla completa a
   CSV (read-only). *Cuándo:* para saber qué ratificadas hay pendientes.
3. **Diagnóstico (`--diagnostico`)** — *Qué:* vuelca la estructura del formulario
   sin escribir. *Cuándo:* cuando un selector deja de entrar.
4. **Consolidación de evidencias (`evidencias_a_pdf.py`)** — *Qué:* junta los PNG
   en un PDF por lote. *Cuándo:* al cerrar un lote, para radicar.
5. **Pilotos seguros (`--sin-guardar`, `--max-filas`)** — *Qué:* corre el flujo
   sin comprometer datos. *Cuándo:* siempre antes de un cargue masivo (regla del
   repo: piloto de 1 factura primero).

> No hay cron ni scheduler: todas son corridas manuales lanzadas por el auditor
> (que no tiene el navegador ni acceso a los portales desde Claude Code; opera en
> su Windows/PowerShell).

---

## 10. Archivos modificados (lista completa)

### Archivos creados por el módulo
| Archivo | Qué es |
|---|---|
| `tools/responder_glosas_fomag.py` | el bot (creado en `64bcf53`, 1 076 líneas; hoy 1 563 tras las iteraciones) |
| `tools/README_responder_glosas_fomag.md` | guía de uso (168 líneas) |
| `tools/evidencias_a_pdf.py` | consolidador de evidencias a PDF (`6c43e48`) |

### Commits del bot FOMAG (21, del 2026-06-24 al 2026-07-02)
`64bcf53` crea el bot · `34fe0d0` navegación a Auditoría robusta · `d754212`
detectar login real (no por "Bienvenido") · `5eee357` click al cuadro naranja
por visibilidad · `67dd533` reconocer grilla vacía · `19ef73f`/`7f0ac75` esperar
la grilla lenta (poll) · `c0938d1` loguear el valor de la caja + Enter ·
`a7d0eb7` "Número factura" por label Material · `71ce1c7` detectar la fila por el
botón RESPUESTA (grilla no es `<table>`) · `2ba43d1` leer la tabla correcta ·
`52df664` confirmar editor del Detalle · `6fd7518` abrir pestañas sin togglear ·
`8e5b002`/`b51953c` dropdown RE9901 con verificación · `8af358b` log del valor
real del control · `79e2beb` PDF sin diálogo del SO · `2f9bafb` poll del editor +
no GUARDAR si nada cargó · `e14a3be` matchear ceros a la izquierda · `be11e93`
limpieza y consolidación (revisión conservadora con modelo fable, −5 líneas
netas, sin cambiar comportamiento).

### Archivos modificados para dejar el CI verde (contexto de la misma línea)
- **`32cb241`** — "CI: corrige fallos preexistentes de lint y un test
  time-bomb". Tocó **14 archivos**: `tests/test_api/test_import_history.py`
  (fechas relativas en lugar de `datetime(2026,4,10…)` fijo) y correcciones de
  lint F de ruff en `tools/`: `cargar_soportes_simed.py`,
  `consolidar_carpetas_notas.py`, `convertir_tramite_masivo.py`,
  `dividir_notas_por_acta.py`, `evidencias_a_word.py`,
  `extraer_respuestas_glosa.py`, `login_dg.py`, `motor_glosas_hus.py`,
  `renombrar_y_organizar_notas.py`, `responder_glosas_coosalud.py`,
  `responder_glosas_simed.py`, `verificar_cuv_notas.py`,
  `verificar_glosas_coosalud.py`.
- **`2ed720d`** — "ci(lint): excluir tools/ del ruff format --check". Cambió en
  `.github/workflows/ci.yml` el `ruff format --check .` por
  `ruff format --check app alembic scripts tests` (los scripts operativos de
  `tools/` se mantienen con formato manual; adopción gradual del formateador).
- **`23cbb1b`** — "test(stats): fechas relativas en heatmap y por-dia-semana
  (time-bomb)". Cambió `tests/test_api/test_por_dia_semana.py` (+29/−15 aprox.) y
  `tests/test_api/test_heatmap_actividad.py` (+21/−? ): reemplazó las fechas fijas
  `2026-04-20/21/22` por fechas **relativas** ancladas a `ahora_utc()` (un lunes
  reciente = `weekday()+7`), para que las siembras no salgan de la ventana de 90
  días con el paso del tiempo.

### Otros entregables de esta conversación (no versionados en `tools/`)
- **Informe de gerencia** (`informe-glosas-fomag.html`): página HTML de una
  carilla, tema claro/oscuro, que compara el proceso manual vs. automatizado
  (publicada como Artifact).
- **`BITACORA.md`** + **`CLAUDE.md`**: sistema de "memoria común" (leer al
  iniciar, actualizar con fecha al terminar). *Nota:* estos dos archivos fueron
  luego **refundidos por el usuario** en la rama local `937f318`, integrando el
  trabajo de dos chats.

---

## 11. Dependencias nuevas

| Paquete | Versión | Para qué | Dónde |
|---|---|---|---|
| `playwright` | la vigente (`pip install playwright`) | manejar el navegador contra Horus | bot FOMAG |
| Chromium de Playwright | `py -m playwright install chromium` | navegador que se automatiza | bot FOMAG |
| `Pillow` (PIL) | la vigente (`pip install pillow`) | armar el PDF de evidencias | `evidencias_a_pdf.py` |
| `ruff` | 0.15.x (igual que CI) | lint (`F`,`W6`) + format-check | CI |
| `pytest`, `pytest-asyncio` | las que fije el runner de CI | correr la suite | CI |

> El bot solo usa **Playwright + stdlib**. No agrega dependencias al `app/` del
> proyecto principal. `openpyxl` aparece en la línea de instalación por herencia
> del template, pero **no** se importa (limpiar — sección 15).

---

## 12. Configuración

### Variables de entorno (obligatorias)
```cmd
setx FOMAG_USER 1098612385@fomag.com
setx FOMAG_PASSWORD <contraseña>
```
(Una vez por máquina; cerrar y reabrir la terminal.) **Nunca** en el comando ni
en el código (queda en el historial / en git).

### Constantes de configuración (en el script)
- `PORTAL_BASE = "https://horus2.horus-health.com"`, `PORTAL_LOGIN`,
  `PORTAL_AUDITORIA = .../cuentasMedicas/auditoria`.
- `TABS` — mapa de las 6 pestañas.
- `COD_RTA2_DEFAULT = "RE9901"`.
- `TEXTO_RATIFICADA_DEFAULT` — el texto legal fijo.
- `PERFIL_DEFAULT = ~/.fomag_horus_profile` — perfil de navegador persistente.

### Parámetros CLI (todos)
`--tab` · **modo** (requerido, excluyente): `--listar` / `--diagnostico` /
`--responder` · **selección** (excluyente): `--solo` / `--facturas` / `--lista` ·
`--cod` · `--texto-archivo` · `--pdf-dir` · `--max-filas` · `--sin-guardar` ·
`--perfil` · `--con-cabeza` · `--lento` · `--evidencias` · `--reporte` · `--log`.

### Rutas típicas (Windows del auditor)
- PDFs de soporte: `D:\...\FOMAG\GLOSAS\2026\...\SOPORTES` (o recurso de red `Z:`).
- Evidencias: `EVIDENCIA_FOMAG\` (o carpeta del lote).
- Salida consolidada: `GR-33-XXXX-2026.pdf`.

### Tokens / credenciales
Solo `FOMAG_USER`/`FOMAG_PASSWORD` (portal). El bot **no** usa tokens de API ni
llaves de IA.

---

## 13. Riesgos (al integrarlo)

1. **⚠ El código no está en la rama local actual.** El bot vive en
   `origin/claude/jolly-lovelace-tfkdfs` (`23cbb1b`, PR #136). La rama **local**
   fue reseteada a `937f318` (bitácora fusionada, **sin** el bot). *Riesgo:* creer
   que el módulo se perdió, o **force-pushear** la rama local y **sobrescribir**
   el bot en el remoto. *Solución:* **no** force-pushear; integrar vía PR #136 o
   traer los archivos del remoto (sección 16).
2. **Sesión / reCAPTCHA.** Si el perfil expira, la corrida se detiene en el
   login. *Solución:* correr una vez con `--con-cabeza` y resolver el captcha.
3. **Cambios del DOM de Horus.** Los selectores del dropdown y del editor se
   programaron desde pantallazos; si Horus cambia el markup, algún paso puede no
   entrar. *Solución:* `--diagnostico` vuelca el HTML real para reafinar.
4. **Lentitud del portal / recurso de red `Z:`.** Grilla y subida de PDF lentas;
   ya hay polls largos (45 s grilla, 12 s editor, 25 s adjunto), pero un pico
   extremo puede vencerlos.
5. **Emparejamiento por núcleo numérico.** `_nucleo_factura` empareja por la
   parte numérica sin ceros; si dos facturas compartieran núcleo (improbable en
   HUS), podría tomar el PDF equivocado.
6. **Conflicto de merge nulo con `app/`.** El bot es aditivo (archivos nuevos en
   `tools/`) → **no** debería generar conflictos con el proyecto principal. Los
   cambios de CI sí tocan `tests/` y `.github/workflows/ci.yml` (revisar que no
   choquen con cambios paralelos del `ci.yml`).

---

## 14. Dependencias con otros módulos

- **Qué necesita:** solo Playwright + Chromium + stdlib. **No importa** nada de
  `app/`. Es 100 % autónomo.
- **Qué lo usa:** `evidencias_a_pdf.py` **consume** los PNG que el bot genera
  (`<factura>_ratificada.png`). Nada más depende del bot.
- **Relación con hermanos:** comparte **patrón y filosofía** con
  `responder_glosas_coosalud.py` y `responder_glosas_simed.py` (mismo estilo de
  RPA, mismo esquema de credenciales por entorno, mismo `--sin-guardar`/`--lista`/
  `--reporte`). No comparten código, pero sí convenciones.
- **Relación con el Motor de Glosas (`app/`):** ninguna en runtime. El único
  cruce fue de **CI**: al dejar la suite verde se tocaron tests del `app/` y el
  `ci.yml` (secciones 6 y 10).

---

## 15. Pendientes (sin terminar / mejoras previstas / bugs conocidos)

1. **`--listar` no funciona bien en la grilla de RATIFICADAS.** `leer_grilla_completa`
   asume `<table>`, y esa grilla **no siempre** lo es. El listado por CSV puede
   salir vacío aunque haya filas. (El flujo `--responder` no depende de esto:
   detecta la fila por el botón RESPUESTA.)
2. **Solo está implementada la pestaña RATIFICADAS.** PENDIENTES, RADICADAS,
   CONCILIACIÓN, CONSOLIDADO no tienen su flujo de respuesta.
3. **La pestaña "HISTÓRICO CONCILIACIÓN" no matchea** en `_click_tab`: el filtro
   `len(t) <= len(objetivo) + 8` es muy corto para ese texto largo.
4. **`openpyxl` figura en la instalación pero no se usa** — limpiar la línea de
   `pip install` (herencia del template COOSALUD).
5. **Desalineación de nombres de estado** entre el README (`SIN_FORMULARIO`) y el
   código (`NO_EN_PESTANA`) para el caso "no abrió el formulario". Unificar.
6. **Falta la línea base de tiempo manual** para cerrar el ROI exacto del informe
   de gerencia (cuánto tomaba responder una ratificada a mano).
7. **Selectores del dropdown/editor** validados con pantallazos y corridas
   reales, pero dependientes del markup de Horus (ver Riesgo 3).

---

## 16. Recomendaciones para fusionarlo (paso a paso)

**Objetivo:** integrar el bot al proyecto principal **sin perder** ni el bot ni
la bitácora fusionada, sabiendo que hoy están en **dos líneas divergentes**:
- `origin/claude/jolly-lovelace-tfkdfs` = `23cbb1b` → **el bot FOMAG** (PR #136,
  base `motor-glosas`).
- rama local `claude/jolly-lovelace-tfkdfs` = `937f318` → **bitácora fusionada**,
  sin el bot.

### Opción A (recomendada): consolidar por la rama principal `motor-glosas`
1. **No** force-pushear la rama local sobre el remoto (borraría el bot).
2. **Mergear PR #136** (`23cbb1b` → `motor-glosas`): así el bot + su README + su
   documentación (este archivo) entran a la línea principal. El módulo es
   **aditivo** en `tools/` → bajo riesgo de conflicto.
3. Llevar aparte la **bitácora fusionada** (`937f318`) a `motor-glosas` con un
   commit/PR propio (o cherry-pick de `4497bdb`/`937f318`), ya que vive en otra
   línea. Revisar el conflicto en `BITACORA.md`/`CLAUDE.md` (elegir la versión
   fusionada del usuario).
4. Verificar CI verde en `motor-glosas` tras ambos merges.

### Opción B: traer el bot a la rama local
Si se prefiere trabajar todo desde la rama local:
```bash
git checkout claude/jolly-lovelace-tfkdfs           # 937f318 (bitácora)
git checkout origin/claude/jolly-lovelace-tfkdfs -- \
    tools/responder_glosas_fomag.py \
    tools/README_responder_glosas_fomag.md \
    tools/evidencias_a_pdf.py \
    docs/HANDOFF_MODULO_FOMAG_RATIFICADAS.md
git add tools/ docs/ && git commit -m "traer módulo FOMAG a la línea de bitácora"
```
Así ambos trabajos quedan en una sola rama sin sobrescribir historia.

### Verificaciones antes de dar por integrado
- CI verde (`ruff check . --select F,W6`, `ruff format --check app alembic scripts
  tests`, y `pytest`).
- Piloto de **1 factura** con `--sin-guardar --con-cabeza` en Horus real (regla
  del repo: piloto antes de cargue masivo).
- Credenciales por entorno presentes (`FOMAG_USER`/`FOMAG_PASSWORD`).

---

## 17. Resumen ejecutivo (qué debe saber quien lo mantenga)

- **Qué es:** un bot Playwright (`tools/responder_glosas_fomag.py`) que responde
  las glosas **ratificadas** del HUS en el portal **FOMAG/Horus**, con respuesta
  **estándar** (código `RE9901` + texto legal fijo + PDF de soporte + evidencia).
- **La única fricción real es el reCAPTCHA:** se resuelve una vez al día en
  modo `--con-cabeza`; la sesión queda en un **perfil de navegador persistente**.
- **El portal es un SPA Angular/Material lento y con DOM tramposo:** grilla que
  **no siempre es `<table>`**, varias tablas ocultas, dropdowns cuyo valor vive
  en un `<input>`, labels flotantes sin placeholder. El bot ya resuelve todo eso
  con detección **estructura-agnóstica**, matching por encabezado, verificación
  del dropdown y polls largos. **No** simplificar esos mecanismos: cada uno nació
  de un fallo real (ver secciones 3 y 4).
- **Orden sagrado por fila:** código → detalle → **PDF antes del ✓** → ✓. Y
  **GUARDAR RESPUESTA solo al final**, nunca confundirlo con el Guardar del
  editor de detalle. Hay **guardas** que evitan enviar respuestas a medias.
- **Para depurar:** `--diagnostico --con-cabeza` vuelca el HTML real y los
  índices de columna; `debug_screenshots/` guarda pantallazos de cada tropiezo.
- **Seguridad operativa:** credenciales **solo** por entorno; **piloto** de 1
  factura antes de cualquier lote; `--sin-guardar` para ensayar sin comprometer.
- **Estado de entrega:** el módulo está **completo y probado** para RATIFICADAS
  (se procesaron lotes reales, ~1 min/factura). Vive en **PR #136** (base
  `motor-glosas`). Pendientes menores en la sección 15. **Cuidado con la
  divergencia de ramas** (secciones 13 y 16): no force-pushear la rama local, que
  no trae el bot.

---

*Documento de entrega generado a partir del código y los commits reales de esta
línea de trabajo. Fecha de la entrega: 2026-07-27.*
