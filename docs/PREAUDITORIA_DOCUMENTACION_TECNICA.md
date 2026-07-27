# MÓDULO DE PRE-AUDITORÍA SINAC — DOCUMENTACIÓN TÉCNICA OFICIAL

> **Documento de entrega al equipo principal.** Reconstruye de forma completa el
> desarrollo del módulo de Pre-auditoría realizado en la rama
> `claude/invoice-audit-bot-qa2koy` del repositorio
> `yesidbadillo820-ship-it/motor-glosas-hus`, fusionado a la rama principal
> `motor-glosas` en los PR **#186** (módulo completo v1→v2), **#187** (botón de
> menú) y **#189** (mejoras post primer uso). Fechas de desarrollo:
> **23 al 27 de julio de 2026**. Estado: **desplegado y en uso en producción**
> (VM de Google Cloud, `iaglosassinac.help/preauditoria`).

---

## 1. OBJETIVO DEL DESARROLLO

### Por qué se creó

El equipo de pre-auditoría de SINAC SC SAS (proceso de Cartera de la ESE
Hospital Universitario de Santander) recibe de Facturación **oficios radicados**
(consecutivo tipo `FHUS-AS-I00877-26`) que entregan facturas para revisión de
soportes antes de radicarlas ante las aseguradoras (SOAT-ADRES, Previsora, AXA,
Suramericana, Bolívar, Mundial, etc.). Ese control se llevaba **a mano en un
Excel** (`CONSOLIDADO_PRE_AUDITORIA_2026.xlsx`: 1.220 filas, 690 envíos, 322
facturas repetidas por devoluciones — hasta 4 veces la misma) y los oficios de
devolución se armaban a mano en otro Excel
(`OFICIOS_DEVOLUCIONES_CONSECUTIVOS.xlsx`, 101 consecutivos `DEV-PRE-AUD`).

### Qué problema resolvía

1. **Digitación repetitiva**: por cada envío había que copiar a mano factura,
   fecha, valor, NIT y entidad desde los reportes de Dinámica Gerencial (DGH).
2. **Sin control de duplicados**: el mismo envío podía digitarse dos veces.
3. **Trazabilidad frágil**: las devoluciones y subsanaciones de una misma
   factura quedaban en filas sueltas sin amarre entre sí.
4. **Plazo sin control**: solo hay **3 días** para auditar cada oficio (cuentan
   desde el día siguiente al recibo) y no había alarma.
5. **Oficios de devolución manuales**: consecutivo, formato, totales y firmas
   se armaban a mano con riesgo de error.
6. **Sin estadísticas**: no había forma rápida de saber cuántas facturas se
   auditan, cuántas OK, cuántas devueltas, reincidencias ni desempeño por
   auditor.

### Qué necesidad cubría (requerimiento del usuario, 10 puntos + ampliación)

**Fase 1 (23-07):** (1) registrar el número de radicado del oficio; (2) fecha de
recibido **con hora**; (3) número de envío; (4) informar cuántas facturas lleva
cada envío; (5) facturas cargadas desde el archivo DGH del consecutivo;
(6) máximo **3 devoluciones** por factura; (7) tras la primera devolución,
subsanación: **subsanada o nuevamente devuelta**; (8) oficio de devoluciones en
**PDF con consecutivo SINAC, logo y firma**; (9) **semáforo** del plazo de 3
días; (10) **estadísticas** con vista masiva, individual y filtros.

**Fase 2 (24-07, cambio de enfoque solicitado):** que la aplicación web **sea el
consolidado oficial** (no un registro): el usuario solo sube dos reportes
fuente, registra el oficio y **escribe el número de envío**; el sistema crea
todas las filas, autocompleta, deduplica, reconoce subsanaciones, se
auto-sincroniza al corregir las fuentes y genera PDF y estadísticas.

**Fase 3 (27-07, mejoras tras primer uso real):** eliminar radicados mal
registrados (solo admin), botón "Ver" en consolidado, renombrar
DGReport→"Formato Facturación Electrónica", firma manuscrita en el PDF, regla
"sin facturación electrónica no se radica", fases visibles de
recepción/auditoría, estadísticas interactivas tipo Power BI.

---

## 2. ARQUITECTURA

### Contexto del sistema anfitrión

El módulo vive dentro del **Motor de Glosas HUS**: aplicación FastAPI + SQLAlchemy
(SQLite en desarrollo/pruebas, PostgreSQL/SQLite en producción), frontend de
páginas estáticas servidas por FastAPI, autenticación JWT (OAuth2 Bearer,
`POST /token`), roles `SUPER_ADMIN | COORDINADOR | AUDITOR | VIEWER`.
Producción: contenedor Docker en VM Google Cloud (`e2-micro`, 1 GB RAM, proyecto
`motor-glosas-hus`, zona `us-west1-a`, instancia `motor-glosas`, repo en
`/opt/motor-glosas`), expuesto por túnel Cloudflare (`iaglosassinac.help`), con
`mem_limit: 640m` y rotación de logs en el `docker-compose.yml` **personalizado
de la VM** (no está en git; ver §12 y §13).

### Estructura del módulo (archivos propios)

```
app/
  models/db.py                      ← 7 modelos del módulo (sección PRE-AUDITORÍA)
  services/preauditoria_service.py  ← toda la lógica de negocio (~900 líneas)
  services/oficio_devolucion_pdf.py ← generador del PDF del oficio (reportlab)
  api/routers/preauditoria.py       ← 20 endpoints REST (prefix /preauditoria)
  api/routers/pwa.py                ← ruta GET /preauditoria (sirve la página)
  main.py                           ← registro del router + migración v1→v2 en lifespan
static/
  preauditoria.html                 ← frontend completo (SPA de 5 pestañas, vanilla JS)
  firma_preauditoria.png            ← firma manuscrita (859×127, PNG transparente)
  LOGO SINAC.png                    ← logo usado en el PDF (ya existía)
  index.html                        ← botón "Pre-auditoría" en menú lateral y ⌘K
tests/
  test_api/test_preauditoria.py     ← 35 pruebas del módulo
docs/
  PREAUDITORIA_DOCUMENTACION_TECNICA.md  ← este documento
```

### Dependencias y librerías

No se agregó **ninguna dependencia nueva** al proyecto. Se usan las ya
existentes en `requirements.txt`: `fastapi`, `sqlalchemy==2.0.37`,
`pydantic` v2, `openpyxl==3.1.5` (lectura/escritura Excel, import perezoso),
`reportlab==4.2.5` (PDF, API platypus, import perezoso). El frontend es HTML/CSS/
JS puro y los gráficos son **SVG vanilla sin librerías** (decisión deliberada:
la app corre en red hospitalaria, sin CDNs).

### Principios de diseño (decisiones de arquitectura)

1. **Modelo B — factura canónica + historial de eventos** (event-sourcing
   "lite"). Cada factura es UNA sola fila (`preaud_facturas`, índice único por
   número) con su estado ACTUAL, más una bitácora append-only
   (`preaud_factura_eventos`) con cada transición. *Cambio de enfoque
   documentado:* la v1 usaba "Modelo A" (una fila por par oficio-factura, campo
   `ronda`); se migró a Modelo B porque el requisito de la fase 2 exige
   explícitamente "cuando la misma factura vuelva a ingresar el sistema **no
   debe crear una factura nueva**" y una línea por factura como el Excel.
2. **Auto-sync por JOIN en lectura, no por snapshot re-sincronizado.** Los
   datos descriptivos (F_FACTURA, VALOR, NIT, ENTIDAD, CORREO F.E.) **no se
   copian** a la factura canónica: se resuelven leyendo la fila vigente de la
   fuente. Re-subir un Excel corregido se refleja solo, sin jobs. *Alternativa
   descartada:* snapshot con re-sync en cada cargue — más escrituras y riesgo
   de deriva si el sync falla a medias (patrón que ya causó un incidente real
   en el proyecto: el caso Lote V2 donde un servicio caído "guardó el error
   como si fuera el resultado").
3. **Snapshot SOLO donde importa legalmente:** cada evento guarda
   `valor/nit/entidad/correo_fe/fecha_factura` del momento
   (`*_snapshot`), y el PDF del oficio de devolución se arma desde los
   **eventos sellados**, no desde la fila viva → un oficio emitido es
   **inmutable** aunque la factura reingrese o la fuente cambie.
4. **Los contadores de la canónica son caché del log** (se actualizan en la
   misma transacción del evento; reconstruibles con COUNT/MAX sobre eventos).
5. **Página standalone**, no panel del SPA `index.html` (22.800 líneas):
   `static/preauditoria.html` + `FileResponse` con cabeceras
   `no-store` en `pwa.py`. Patrón ya usado por `importar-recepcion.html`.

---

## 3. FUNCIONES IMPLEMENTADAS

### `app/services/preauditoria_service.py`

Constantes: `MAX_DEVOLUCIONES=3`, `PLAZO_DIAS_HABILES=3`,
`PREFIJO_CONSECUTIVO="DEV-PRE-AUD"`, resultados
`PENDIENTE|RADICAR|DEVUELTA`, estados `NUEVA|RADICADA|
DEVUELTA_PEND_SUBSANACION|EN_SUBSANACION|SUBSANADA|NUEVAMENTE_DEVUELTA|
BLOQUEADA_LIMITE`.

| Función | Qué hace / cómo / por qué |
|---|---|
| `_es_habil(d)` | `weekday()<5` (lunes–viernes). Base del plazo. **Supuesto documentado: no descuenta festivos colombianos** (pendiente §15). |
| `_sumar_dias_habiles(desde,n)` | n-ésimo día hábil DESPUÉS de `desde`. Calcula la fecha límite. |
| `_dias_habiles_entre(a,b)` | Días hábiles inclusive. Calcula restantes. |
| `calcular_semaforo(fecha_recibido, hoy=None, completado=False)` | Devuelve `{estado, fecha_limite, dias_habiles_restantes, dias_vencido}`. Estados: `COMPLETADO` (todo auditado), `VENCIDO` (hoy>límite), `VERDE` (≥3 restantes), `AMARILLO` (2, penúltimo día), `ROJO` (1, último). Convierte el recibido a fecha LOCAL Bogotá antes de contar. Verificado con casos: recibido lunes 20-jul → límite jueves 23; recibido viernes 24-jul → límite miércoles 29 (el fin de semana no cuenta). |
| `siguiente_consecutivo(db, anio=None)` | `MAX(numero)+1` filtrado por año → `DEV-PRE-AUD-####-AAAA`. **Reinicia cada año.** Protegido por índice único `(anio, numero)`. |
| `_normalizar_encabezado(v)` | Mayúsculas, sin tildes (NFKD), sin signos → permite mapear encabezados con variantes. |
| `_ALIAS_RADICACION` / `_ALIAS_DGREPORT` | Diccionarios de alias de columnas (nombre normalizado → campo). Aceptan tanto los encabezados REALES del reporte DGH (`Radicacion.Consecutivo`, `CxC.Factura`, …) como variantes genéricas (`ENVIO`, `FACTURA`, …) para poder cargar también el consolidado histórico. |
| `_mapear_columnas(fila, alias)` | Devuelve `{campo: índice}` de la fila de encabezados. |
| `_como_fecha(v)` | datetime/date/str en varios formatos → `datetime` o None. |
| `_como_valor(v)` | Números y texto **en formato colombiano** (punto de miles, coma decimal: `"1.234.567,89"` → `1234567.89`). |
| `_texto(v)` | `.strip()` → None si queda vacío (la ENTIDAD real trae espacios al final). |
| `_misma_fecha(a,b)` | Compara solo la parte DÍA. Evita que el upsert marque "actualizada" toda la fuente por diferencias de zona horaria naive/aware (hallazgo de la revisión adversarial). |
| `_hallar_encabezado(ws, alias, requeridos)` | Busca la fila de encabezados en las primeras 15 filas de cada hoja. |
| `parsear_excel_radicacion(bytes)` | Lee RADICACIÓN DE CUENTAS. Devuelve **una fila por factura**: descarta estados `Anulado*` (42 en el archivo real); si una factura tiene varias radicaciones válidas (re-radicación, 12 casos reales) conserva la de **mayor F_RECIBIDO**; recorta ENTIDAD; reporta `advertencias` y `leidas`. |
| `parsear_excel_dgreport(bytes)` | Lee el Formato Facturación Electrónica (DGReport): una fila por factura (`correo_fe="SI"`, fecha de correo, CUFE). Deduplica dentro del archivo. |
| `upsert_radicacion(db, filas, archivo, usuario)` | Upsert por factura contra `preaud_fuente_radicacion`. **En bloque**: pre-carga las existentes con `IN` troceado de a 900 (36k filas pasaron de 19s a 3,4s). Detecta cambio campo a campo (fechas con `_misma_fecha`) → reporta `{nuevas, actualizadas, sin_cambio}`. Blindado contra factura repetida en el mismo lote (agrega al índice tras `db.add`). |
| `upsert_dgreport(...)` | Igual, por factura, contra `preaud_fuente_dgreport`. |
| `datos_fuente(db, factura)` | Resuelve `{envio,f_recibido,f_factura,valor,nit,entidad,correo_fe}` desde las fuentes (correo = SI si está en dgreport, NO si no). Es el corazón del **auto-sync**. |
| `facturas_de_envio(db, envio)` | Todas las filas de la fuente con ese envío (`str(envio).strip()` normaliza int/str). |
| `_nuevo_evento(...)` | Construye un `FacturaEventoRecord` con ronda/subsanación/oficio/auditor/motivo y el **snapshot** de la fuente en ese momento. |
| `preview_envio(db, oficio, envio)` | Simula el cargue SIN escribir: clasifica cada factura (`NUEVA`, `REINGRESO`, `YA_RADICADA`, `YA_ABIERTA`), avisa `ya_cargado` y alertas de límite. |
| `escribir_envio(db, oficio, envio, usuario)` | **El corazón del automatismo.** (a) si el envío está en el ledger → `{ya_cargado, "El envío ya fue cargado."}`; (b) si no existe en la fuente → mensaje "no existe… suba la fuente"; (c) por cada factura del envío: si no existe → crea canónica (ronda 1, `NUEVA`, `PENDIENTE`) + evento `ESCRITA`; si existe y está `DEVUELTA` → **REINGRESO/SUBSANACIÓN**: `ronda+1`, `num_subsanacion=ronda-1`, actualiza envío/oficio/f_recibido actuales, vuelve a `PENDIENTE`/`EN_SUBSANACION`, limpia auditor y `oficio_devolucion_id` (abre ciclo nuevo) + evento `REINGRESO` — **sin crear factura nueva**; alerta si ya lleva 3 devoluciones; si está `RADICAR` o `PENDIENTE` en otro oficio → omite con advertencia; (d) registra el envío en el ledger; (e) `commit` con manejo de `IntegrityError` (carrera de doble clic → responde "ya fue cargado" limpio). |
| `auditar_factura(db, canon, resultado, usuario, motivo, observaciones)` | Aplica `RADICAR`/`DEVUELTA`/`PENDIENTE`(revertir). **Guardas:** solo se audita una factura `PENDIENTE` (evita inflar el contador con doble clic; para cambiar una decisión hay que revertir primero); RADICAR exige `correo_fe == "SI"` (**regla: sin facturación electrónica solo se devuelve**, 409); DEVOLVER exige motivo (400) y contador < 3 (la 4.ª → 409 con mensaje "máximo 3… radicar o escalar"); revertir está bloqueado si ya salió en PDF (409) y decrementa el contador si venía de DEVUELTA. Estados resultantes: RADICAR→`RADICADA` (r1) o `SUBSANADA` (r≥2); DEVOLVER→`DEVUELTA_PEND_SUBSANACION` (r1), `NUEVAMENTE_DEVUELTA` (r≥2) o `BLOQUEADA_LIMITE` (al llegar a 3). Cada acción inserta su evento con snapshot. |
| `eliminar_oficio(db, oficio)` | Elimina un oficio mal registrado con **salvaguardas**: 409 si alguna factura (fila o evento) está amarrada a un oficio de devolución emitido; facturas de ronda 1 → se borran con sus eventos; facturas en subsanación (r≥2) → **se revierte el reingreso** (ronda-1, vuelve a `DEVUELTA` con el envío/oficio/auditor/motivo del evento de devolución anterior) sin perder historial; libera los envíos del ledger; devuelve `{radicado, facturas_borradas, subsanaciones_revertidas, envios_liberados}`. |

### `app/services/oficio_devolucion_pdf.py`

`generar_pdf_oficio_devolucion(consecutivo, fecha_generado, numero_radicado,
facturas, generado_por) -> bytes`. Reportlab platypus, **carta apaisada**,
import perezoso. Formato replicado 1:1 del documento guía (`GUIA_DE_PDF.pdf`):

- Cabecera en caja: logo `static/LOGO SINAC.png` (5,2×0,92 cm) · título
  "ENTREGA DE NO ACEPTACIONES PARA CORRECCION POR PARTE DE FACTURACION HUS" ·
  subtítulo "OBSERVACIONES DE PREAUDITORÍA PARA SUBSANACIÓN" · a la derecha
  `Consecutivo:` y `Fecha:`.
- Tabla (repite encabezado por página): `No. | ENVIO | FACTURA | F_FACTURA |
  VALOR | NIT | ENTIDAD | OFICIO | MOTIVO` — la columna OFICIO lleva el
  radicado FHUS de cada fila. Zebra, fila `TOTAL — N factura(s)` con SPAN y el
  total bajo VALOR (formato `$ 1.234.567`, helper `_formatear_cop`).
- NOTA institucional y **bloque de firmas**: izquierda YUDY ALEXANDRA AMAYA
  GUTIERREZ / Directora del proceso - Cartera / Sinac Sc Sas - ESE HUS, con la
  **firma manuscrita** `static/firma_preauditoria.png` (si existe) dibujada
  sobre la línea **conservando su proporción real** (`ImageReader.getSize()`,
  ancho 6 cm); derecha "RECIBIDO:" ANGELICA LORENA POVEDA / Coordinadora de
  Facturacion - Encargada / Administracion en Salud CTA - ESE HUS. Los nombres
  y cargos son constantes del archivo (`FIRMANTE_*`, `RECIBE_*`) y se editan
  ahí si cambian.
- Pie: "Documento generado por el módulo de Pre-auditoría SINAC el dd/mm/aaaa
  HH:MM · Elaborado por: X".

La firma se **extrajo del PDF guía** (imagen embebida de la página 2, 859×127)
con PyMuPDF y se le quitó el fondo (blanco→transparente, umbral RGB>230).

### `static/preauditoria.html` — funciones JS principales

`api()` (fetch con Bearer + logout en 401) · `esc()` (escape HTML) · `cop()`
(formato pesos es-CO) · `fBog()/fDia()` (fechas) · `debounce()` ·
`verTab()` · `subirFuente()` · `cargarResumenFuentes()` · `crearOficio()` ·
`cargarOficios()` · `abrirOficio()` (modal con paso 4) · `previewEnvio()` ·
`commitEnvio()` · `selTodos()` · `eliminarOficio()` · `eliminarSeleccionados()`
· `generarDev()` · `verPdf()` (blob con Bearer; también descarga el Excel) ·
`cargarConsolidado()` · `abrirAuditar()` · `auditar()` · `verHist()` ·
`cargarDevoluciones()` · `tipMostrar()/tipOcultar()` (tooltip) ·
`irConsolidado(resultado)` (clic-para-filtrar) · `renderDona()` ·
`renderBarras()` · `cargarStats()`. Variables de sesión:
`TOKEN=localStorage.hus_token`, `USER_ROL=localStorage.hus_rol`,
`ES_ADMIN = SUPER_ADMIN||COORDINADOR` (solo muestra/oculta botones — **la
autorización real la impone el servidor**).

---

## 4. FLUJO COMPLETO (paso a paso)

**Paso 0 — Login.** El usuario inicia sesión en la app principal (`/`), que
guarda `hus_token`, `hus_user`, `hus_rol` en localStorage. Entra a
`/preauditoria` (botón "Pre-auditoría" del menú lateral, ⌘K, o URL directa).
Sin token → redirige a `/`.

**Paso 1 — Subir Radicación de Cuentas (pestaña Fuentes).** Selecciona el
`.xlsx` del reporte DGH y pulsa "Subir Radicación" → `POST
/preauditoria/fuentes/radicacion` (multipart, máx. 30 MB) →
`parsear_excel_radicacion` (descarta Anulado, dedup por factura, strip) →
`upsert_radicacion` (en bloque) → respuesta con leídas/nuevas/actualizadas/sin
cambio + advertencias; la UI refresca los contadores
(`GET /fuentes/resumen`). Con el archivo real: 36.765 leídas → 36.723 válidas,
42 Anulado descartadas, 5.198 envíos distintos, en ~9 s.

**Paso 2 — Subir Formato Facturación Electrónica.** Igual con
`POST /fuentes/dgreport` (7.231 facturas reales). Define CORREO F.E.

**Paso 3 — Registrar oficio (pestaña Oficios y envíos).** Número FHUS + fecha y
hora (input `datetime-local`, precargado con ahora) → `POST /oficios`.
El backend normaliza a mayúsculas, rechaza duplicado (409, índice único), parsea
la fecha como **hora local Bogotá → UTC** y guarda `creado_por` = usuario
logueado (= **quién RECEPCIONÓ**, fase 1). La tabla muestra el semáforo,
"Recepcionó" y "Auditor(es)".

**Paso 4 — Escribir el envío.** En el modal del oficio escribe el número (ej.
`229304`) → opcional "Ver antes" (`GET .../envios/{envio}/preview`, no escribe)
→ "Cargar envío" (`POST .../envios`). El sistema trae TODAS las facturas del
envío desde la fuente y crea/reingresa según §3 `escribir_envio`. Respuestas
posibles: `nuevas/reingresos/omitidas` + alertas; "El envío ya fue cargado."
(dedup); 404 "no existe en la Radicación… suba la fuente". Se pueden escribir
varios envíos al mismo oficio (se acumulan en el ledger con su conteo).

**Paso 5 — Auditar (pestaña Consolidado).** Una fila por factura con
Factura·Envío·Entidad·Valor·Correo F.E.·Estado·Ronda·Subs.·Dev.·Auditor y
botones **Auditar** y **👁 Ver**. "Auditar" abre el modal
(`GET /facturas/{id}`): si `correo_fe != SI` el botón verde queda
**deshabilitado** con aviso 🚫 (y el backend lo bloquea igual);
"✔ Soportes completos — radicar" / "✖ Devolver" (motivo obligatorio) /
"Dejar pendiente" (revertir) → `PATCH /facturas/{id}/auditar`. El auditor
que decide queda registrado (fase 2 — puede ser distinto del que recepcionó).

**Paso 6 — Oficio de devolución (modal del oficio → botón rojo).**
`POST /oficios/{id}/oficio-devolucion`: toma las facturas `DEVUELTA` sin
oficio, asigna el consecutivo SINAC, crea el registro, marca las facturas y
**sella el evento de devolución** de cada una con el `oficio_devolucion_id`.
`GET /oficios-devolucion/{id}/pdf` arma el PDF **desde los eventos sellados**
(inmutable) y lo abre en otra pestaña. La pestaña "Oficios de devolución" lista
todos con su PDF.

**Paso 7 — Subsanación.** Cuando Facturación reenvía la factura corregida en un
envío nuevo, al escribir ese envío el sistema la **reconoce** (estaba
DEVUELTA) y la numera Subsanación 1/2/3 sin duplicarla (§3). Si se radica →
`SUBSANADA`; si se devuelve otra vez → `NUEVAMENTE_DEVUELTA`; al acumular 3
devoluciones → `BLOQUEADA_LIMITE` (solo radicar o escalar).

**Paso 8 — Seguimiento.** Pestaña Estadísticas (tablero interactivo §7) y
"Exportar Excel" del consolidado. El botón 👁 Ver muestra el historial
completo (`GET /facturas/{numero}/historial`): cada evento con ronda, envío,
oficio, auditor, motivo, valor del momento y fecha.

---

## 5. BASE DE DATOS

7 tablas (todas del módulo, prefijo `preaud_`). Tipos según convención del
repo: `Integer/String/Float/DateTime(timezone=True)/Text/ForeignKey/Index`.
**Creación:** `Base.metadata.create_all` en el lifespan (sin Alembic para
tablas nuevas — convención del proyecto).

### `preaud_oficios_recepcion` — `OficioRecepcionRecord`
| Columna | Tipo | Nota |
|---|---|---|
| id | Integer PK | |
| numero_radicado | String(60) NOT NULL | ej. FHUS-AS-I00877-26; **único** (`ix_preaud_oficio_radicado`) |
| fecha_recibido | DateTime(tz) NOT NULL idx | **con hora**; guardada en UTC (entrada = hora Bogotá) |
| observaciones | Text | |
| archivo_dgh | String(300) | legado v1 (import directo); sin uso en v2 |
| creado_en / creado_por | server_default now() / String(200) | `creado_por` = **quién recepcionó** |

### `preaud_fuente_radicacion` — `RadicacionCuentaRecord` (FUENTE 1)
| Columna | Tipo | Nota |
|---|---|---|
| id | Integer PK | |
| factura | String(30) NOT NULL | **única** (`ix_preaud_rad_factura`) — upsert |
| envio | String(30) NOT NULL idx | `ix_preaud_rad_envio` — cruce envío→facturas |
| f_recibido | DateTime(tz) | `Radicacion.FechaDocumento` |
| f_factura | DateTime(tz) | `CxC.Fecha` |
| valor | Float NOT NULL | `CxC.Valor` (NO `ValorRadicado`: vale 0 en estado Registrado) |
| nit | String(30) idx | `Radicacion.Tercero.Documento` |
| entidad | String(300) | `Tercero.NombreCompletoNA` (con strip) |
| estado_radicacion | String(40) | Radicado_Entidad / Registrado / … |
| fuente_archivo / importado_por / importado_en / actualizado_en | — | trazabilidad del cargue |

### `preaud_fuente_dgreport` — `DgReportRecord` (FUENTE 2)
factura String(30) **única** (`ix_preaud_dgreport_factura`) · correo_fe
String(2) default "SI" · fecha_correo DateTime(tz) · numero_fe String(80)
(CUFE) · fuente_archivo/importado_por/importado_en/actualizado_en.

### `preaud_envios_cargados` — `EnvioCargadoRecord` (ledger/dedup)
envio String(30) **único** (`ix_preaud_envio_cargado`) · oficio_id FK
recepción idx · total_facturas/nuevas/reingresos Integer · cargado_por /
cargado_en. Insertar aquí es lo que hace atómico el "El envío ya fue cargado".

### `preaud_facturas` — `FacturaPreauditoriaRecord` (LA CANÓNICA, redefinida en v2)
| Columna | Tipo | Nota |
|---|---|---|
| id | Integer PK | |
| factura | String(30) NOT NULL | **única** (`ix_preaud_fact_canonica`) — nunca se duplica |
| envio_actual | String(30) idx | cambia al reingresar |
| oficio_actual_id | FK recepción idx | |
| oficio_fhus | String(60) idx | denormalizado del oficio actual |
| f_recibido | DateTime(tz) | del oficio actual |
| estado | String(25) idx default NUEVA | máquina de estados §3 |
| resultado_actual | String(15) idx default PENDIENTE | PENDIENTE/RADICAR/DEVUELTA |
| ronda_actual | Integer default 1 | 1=primera, 2+=subsanación |
| num_subsanacion | Integer default 0 | = ronda_actual − 1 (Subsanación 1/2/3) |
| num_devoluciones | Integer default 0 | contador histórico, tope 3, −1 al revertir, **nunca se reinicia por reingreso** |
| pendiente_subsanacion | Integer 0/1 | 1 al devolver; 0 al reingresar o radicar |
| auditor / fecha_auditoria | String(120) idx / DateTime(tz) | **quién audita** (fase 2) |
| motivo_ultima_devolucion / observaciones | Text | |
| oficio_devolucion_id | FK devolución idx | del ciclo vigente; se limpia al reingresar |
| creado_en/creado_por/actualizado_en | — | |
Índices extra: `ix_preaud_fact_envio(envio_actual)`,
`ix_preaud_fact_estado_auditor(estado,auditor)`.

### `preaud_factura_eventos` — `FacturaEventoRecord` (historial inmutable)
factura_id FK CASCADE idx · factura String(30) idx (denorm.) · tipo_evento
String(30) idx (`ESCRITA|RADICADA|DEVUELTA|REINGRESO|SUBSANADA|
NUEVAMENTE_DEVUELTA|REVERTIDA`) · subsanacion_num · ronda ·
estado_resultante · envio · oficio_id FK · oficio_fhus · f_recibido ·
resultado · auditor idx · motivo · oficio_devolucion_id FK idx (**sellado al
emitir el PDF**) · **snapshots**: valor_snapshot Float, nit_snapshot,
entidad_snapshot, correo_fe_snapshot, fecha_factura_snapshot ·
creado_en idx / creado_por. Índices: `ix_preaud_evt_factura_ts(factura_id,
creado_en)`, `ix_preaud_evt_tipo`, `ix_preaud_evt_oficio_dev`.

### `preaud_oficios_devolucion` — `OficioDevolucionRecord`
consecutivo String(40) **único** · anio Integer idx · numero Integer ·
**único compuesto** `(anio,numero)` (consecutivo sin choques, reinicia por
año) · oficio_recepcion_id FK · fecha_generado · generado_por ·
total_facturas · total_valor.

### Migración v1 → v2 (en `app/main.py`, lifespan)

`create_all` no altera tablas existentes, así que el arranque detecta el
esquema viejo de `preaud_facturas` (tiene `oficio_id` y no tiene
`num_subsanacion`): si la tabla está **vacía** → `DROP TABLE` + recrear con la
forma v2; si tuviera datos → NO destruye, deja warning "requiere migración
manual a v2". Idempotente, con try/rollback como el resto de migraciones del
lifespan. En producción corrió limpio (el módulo se desplegó v2 antes de
cargar datos).

### Datos necesarios para operar
Los dos Excel fuente (se suben por la UI). Opcionalmente el histórico del
CONSOLIDADO (los alias del parser ya entienden sus encabezados) — pendiente
§15.

---

## 6. BACKEND

Router: `app/api/routers/preauditoria.py`, `APIRouter(prefix="/preauditoria",
tags=["preauditoria"])`, registrado en `app/main.py` junto al resto.

**Permisos:** todos los endpoints exigen JWT (`Depends(get_usuario_actual)`).
Los de eliminación exigen `Depends(get_coordinador_o_admin)` →
SUPER_ADMIN/COORDINADOR (un AUDITOR recibe **403**; hay prueba de ello).

| Método y ruta | Qué hace / validaciones / errores |
|---|---|
| POST `/fuentes/radicacion` | Sube Excel Radicación. Valida extensión `.xlsx/.xlsm`, tamaño ≤30 MB (400), parseable (400), ≥1 factura válida (422). Devuelve `{tipo, filas_leidas, facturas_validas, nuevas, actualizadas, sin_cambio, advertencias[≤50]}`. |
| POST `/fuentes/dgreport` | Igual para el Formato F.E. |
| GET `/fuentes/resumen` | `{radicacion_facturas, radicacion_envios, dgreport_facturas}`. |
| GET `/fuentes/radicacion` | Consulta paginada de la fuente (filtros `q` factura/entidad/NIT, `envio`; `page/per_page≤200`). |
| POST `/oficios` | Crea oficio. Radicado a mayúsculas; duplicado → 409; fecha "AAAA-MM-DDTHH:MM" hora Bogotá → UTC (400 si inválida). |
| GET `/oficios` | Lista con semáforo, conteos, `envios_escritos`, `recepcionado_por`, `auditores[]`. Filtros `q`, `estado` (del semáforo, filtrado en memoria), paginación. |
| GET `/oficios/{id}` | Detalle + facturas (404). |
| DELETE `/oficios/{id}` | **Solo admin/coordinador.** Elimina con salvaguardas (§3); 404/409. |
| POST `/oficios/eliminar-masivo` | **Solo admin/coordinador.** `{ids:[1..100]}` → `{eliminados[], rechazados[{id,motivo}]}` — los bloqueados no frenan al resto. |
| GET `/oficios/{id}/envios/{envio}/preview` | Simulación sin escribir. |
| POST `/oficios/{id}/envios` | Escribe el envío (§4 paso 4). `{envio}`; 404 oficio o envío inexistente en fuente; dedup devuelve 200 con `ya_cargado`. |
| PATCH `/facturas/{id}/auditar` | `{resultado: RADICAR\|DEVUELTA\|PENDIENTE, motivo_devolucion?, observaciones?}` (Pydantic pattern). Errores: 400 sin motivo; 409 doble decisión / sin F.E. / 4.ª devolución / revertir con PDF. |
| GET `/consolidado` | Una fila por factura con datos de fuente **en batch** (2 queries por página). Filtros: `q` (factura directo + subquery correlacionada a entidad/NIT — sin materializar listas), `oficio_id`, `envio`, `auditor`, `resultado`, `estado`, `solo_reincidentes`, paginación ≤500. |
| GET `/consolidado/export.xlsx` | Excel del consolidado (openpyxl, **un solo JOIN**, sin N+1): ENVIO, F_RECIBIDO, OFICIO FHUS, FACTURA, F_FACTURA, VALOR, NIT, ENTIDAD, CORREO F.E., ESTADO, RESULTADO, N SUBSANACION, DEVOLUCIONES, AUDITOR, MOTIVO. |
| GET `/facturas/{id}` | Ficha por id (para el modal de auditar). |
| GET `/facturas/{numero}/historial` | Ficha actual + TODOS los eventos (timeline). 404 si no está. |
| POST `/oficios/{id}/oficio-devolucion` | Genera consecutivo + registro + **sella eventos**. 400 si no hay devueltas sin oficio. |
| GET `/oficios-devolucion` | Lista paginada con radicado origen y `pdf_url`. |
| GET `/oficios-devolucion/{id}/pdf` | `StreamingResponse application/pdf` armado desde eventos sellados. |
| GET `/estadisticas` | KPIs (total/auditadas/pendientes/radicar/devueltas/subsanadas/nuevamente_devueltas/tasa_devolucion/valor_total), `por_auditor[]`, `por_entidad[]` (top 10), `reincidentes[≤50]` (≥2 dev.), `en_limite_devoluciones`, `semaforo_oficios` (conteo agrupado en 2 queries, sin N+1), `max_devoluciones`. |
| GET `/preauditoria` (en `pwa.py`) | Sirve `static/preauditoria.html` con cabeceras **no-store** (nunca se cachea la página). |

**Manejo de fechas (2 helpers, hallazgo de revisión):**
`_fecha_iso` (fechas del PROCESO guardadas UTC → ISO Bogotá) vs
`_fecha_fuente_iso` (fechas de CALENDARIO de las fuentes → ISO **sin**
corrimiento de zona; antes se corrían un día: 2026-05-20 salía 2026-05-19 en
el consolidado pero 20/05 en el PDF).

**Middleware/infra heredada del anfitrión:** CORS, GZip, correlación de
request-id, rate limit (slowapi), Sentry/PostHog opcionales — no se tocó nada
de eso.

---

## 7. FRONTEND (`static/preauditoria.html`)

Página standalone (~800 líneas), español, paleta institucional
(azul `#0b3d91`), responsive básico, sin dependencias.

**Pantallas (5 pestañas):**
1. **📤 Fuentes** — dos tarjetas de subida ("1 Radicación de Cuentas",
   "2 Formato Facturación Electrónica") con input file + botón + mensajes
   (verde/amarillo/rojo) y 3 KPI de resumen.
2. **📥 Oficios y envíos** — formulario "3 Registrar oficio" (radicado +
   `datetime-local` precargado) con leyenda del semáforo; barra admin "🗑
   Eliminar seleccionados" (oculta para no-admin); tabla: checkbox (admin) ·
   Radicado · Recibido · **Recepcionó** · **Auditor(es)** · Plazo (chip
   semáforo con días restantes/vencidos) · Envíos escritos `envio(n)` ·
   Facturas · Pend. · OK · Dev. · Abrir/🗑.
3. **🧾 Consolidado** — filtros (buscar, resultado, envío, auditor, "solo con
   devoluciones") + Exportar Excel; tabla una-fila-por-factura con chips de
   estado por color (`RADICADA/SUBSANADA` verde, `DEVUELTA_*` rojo,
   `BLOQUEADA_LIMITE` rojo sólido, resto gris), contador `dev/3`; botones
   **Auditar** y **👁 Ver**.
4. **📄 Oficios de devolución** — tabla consecutivo/fecha/origen/facturas/
   valor/generado por/📄 PDF.
5. **📊 Estadísticas** — tablero interactivo (abajo).

**Modales (3):** detalle de oficio (con "4 Escribir un número de envío": input
+ "Ver antes" + "Cargar envío" + resultados/alertas + lista de facturas +
botón "Generar oficio de devolución", deshabilitado sin devueltas) · auditar
(ficha, avisos de límite y de sin-F.E., textarea motivo, 3 botones — el verde
**deshabilitado** si `correo_fe != SI`) · historial (timeline de eventos).

**Tablero de estadísticas** (construido siguiendo la guía interna de
visualización, paleta **validada por script** contra daltonismo):
- Colores de estado: OK `#0f6a33`, Devuelta `#ea5f45`, Pendiente `#4d68c8` —
  todas las verificaciones PASS (banda de luminosidad, croma, separación CVD
  protan ΔE 8.6 ≥ 8, piso visión normal, contraste ≥3:1). *Decisión
  documentada:* el par verde/rojo institucional original (`#1e8e3e/#d93025`)
  **falló** la validación (ΔE 5.0 deutan) y se reemplazó por pares separados
  por luminosidad.
- **Dona de resultados**: SVG con número total en el centro, separadores
  angulares entre segmentos, tooltip al pasar el mouse, **clic en un segmento
  o en su leyenda → abre el Consolidado filtrado por ese resultado**; leyenda
  con conteos y tasa de devolución.
- **Barras apiladas horizontales** por **auditor** y por **entidad (top 10)**:
  segmentos OK/Devueltas/Pendientes con 2px de aire, nombre truncado con
  `<title>`, total al final, tooltip por segmento (incluye valor $), leyenda
  fija.
- KPI tiles (8) + semáforo de oficios (5 tiles con emoji+texto, nunca color
  solo) + tabla de reincidentes.
- Tooltip compartido `#gtooltip` (div fijo, sigue el cursor, se voltea cerca
  del borde).

**Validaciones de UI:** campos obligatorios con mensajes en español; confirm()
antes de eliminar y de generar oficio; todos los textos pasan por `esc()`;
errores del backend se muestran tal cual (`detail`).

---

## 8. IA

**El módulo NO usa IA en tiempo de ejecución.** Es lógica determinista
(reglas de negocio + SQL). No consume Groq/Anthropic/Gemini ni comparte nada
con el motor de dictámenes del anfitrión.

**IA usada durante el DESARROLLO** (metodología, para reproducibilidad):
- **Panel de diseño (4 agentes en paralelo)** antes de programar la v2:
  (1) *mapeo de fuentes* — analizó los archivos reales y produjo el mapeo
  exacto de columnas con edge cases medidos (42 Anulado; 12 facturas con
  re-radicación, patrón Anulado→re-radicada; envío int de 6 dígitos sin ceros
  a la izquierda; 0 nulos en NIT/entidad; entidad con espacios al final;
  FechaDocumento constante por consecutivo y mejor candidata a F_RECIBIDO;
  `ValorRadicado`=0 en Registrado → usar `CxC.Valor`; ventana temporal del
  DGReport 1–23 jul con su caveat de CORREO F.E.); (2) *esquema de BD*
  (canónica+eventos, join-en-lectura); (3) *flujo y API* (máquina de estados,
  endpoints, algoritmo de escribir-envío); (4) *plan de integración* (qué se
  reutiliza/modifica del código v1).
- **Revisión adversarial (2 agentes)** sobre la v2 ya implementada, con
  verificación paso a paso. Hallazgos CONFIRMADOS y corregidos: (a) el
  reingreso borraba el vínculo con el oficio de devolución emitido → el PDF
  regenerado perdía la factura → solución: sellar eventos y armar el PDF desde
  ellos; (b) doble devolución sin reingreso inflaba el contador → guard de
  estado PENDIENTE; (c) corrimiento de fechas de un día (naive→UTC→Bogotá) →
  `_fecha_fuente_iso` + `_misma_fecha`; (d) búsqueda `q` materializaba un IN
  con 36k binds (rompería SQLite) → subquery; (e) N+1 en export/estadísticas →
  JOIN/agrupadas; (f) índice del upsert no se actualizaba en inserciones
  (defensa en profundidad); (g) carrera TOCTOU del dedup de envío →
  IntegrityError manejado. Cada hallazgo quedó cubierto con prueba de
  regresión.
- Nota operativa ajena al módulo detectada en logs de producción: el motor de
  dictámenes intenta el modelo Groq `meta-llama/llama-4-scout-17b-16e-instruct`
  que responde 404 `model_not_found` y cae al fallback
  `openai/gpt-oss-120b` (funciona, pero desperdicia 2 llamadas por análisis).
  Pendiente §15.

---

## 9. AUTOMATIZACIONES

| Automatización | Qué hace | Cuándo/cómo |
|---|---|---|
| Creación de tablas + migración v1→v2 | `create_all` + drop-if-empty del esquema viejo de `preaud_facturas` | Al arrancar la app (lifespan), idempotente |
| Autocompletado por envío | Crea una fila por factura con todos sus datos | Al `POST /oficios/{id}/envios` |
| Dedup de envíos | "El envío ya fue cargado", sin duplicar | Ledger + índice único + IntegrityError |
| Reconocimiento de subsanaciones | Numera Subsanación 1/2/3 sin crear factura | Dentro de escribir-envío |
| Auto-sync de las fuentes | Corregir el Excel y re-subirlo se refleja solo | JOIN en lectura (sin job) |
| Semáforo del plazo | VERDE→AMARILLO→ROJO→VENCIDO/COMPLETADO | Calculado en cada consulta |
| Consecutivo SINAC | DEV-PRE-AUD-####-AAAA, reinicia por año | Al generar el oficio |
| Sellado del PDF | El oficio emitido queda inmutable | Eventos sellados al generarlo |
| Contadores/estado | num_devoluciones, num_subsanacion, estado | Misma transacción de cada evento |
| CI del repo | ruff (`--select F,W6` + format) + pytest + pip-audit | GitHub Actions en cada push/PR |
| **NO hay** tareas programadas (cron) propias del módulo | — | — |

---

## 10. ARCHIVOS MODIFICADOS (lista completa y qué cambió)

**Nuevos:**
- `app/services/preauditoria_service.py` — todo §3.
- `app/services/oficio_devolucion_pdf.py` — todo el generador PDF.
- `app/api/routers/preauditoria.py` — los 20 endpoints.
- `static/preauditoria.html` — el frontend completo.
- `static/firma_preauditoria.png` — firma manuscrita (859×127, transparente).
- `tests/test_api/test_preauditoria.py` — 35 pruebas.
- `docs/PREAUDITORIA_DOCUMENTACION_TECNICA.md` — este documento.

**Modificados:**
- `app/models/db.py` — sección "PRE-AUDITORÍA SINAC": 7 modelos (en v2 se
  **redefinió** `FacturaPreauditoriaRecord` de oficio-céntrica a canónica y se
  añadieron las 4 tablas de fuentes/ledger/eventos).
- `app/main.py` — import + `include_router(preauditoria_router)` y bloque de
  migración v1→v2 en el lifespan (tras los índices de historial).
- `app/api/routers/pwa.py` — `GET /preauditoria` → FileResponse no-store.
- `static/index.html` — botón "Pre-auditoría" en el sidebar (patrón
  `window.location.href='/preauditoria'`, junto a Importar recepción), entrada
  en el Command Palette (⌘K) y exclusión en `aplicarRestriccionesRol` para que
  los AUDITOR también lo vean.
- `BITACORA.md` — entradas 23-07, 23-07 tarde, 24-07 y 27-07 (además se
  **fusionaron las bitácoras** de dos líneas de chat paralelas que habían
  divergido, dos veces, conservando el contenido de ambas).
- `CLAUDE.md` — fusión de reglas de ambas líneas (leer/actualizar bitácora,
  reglas del repo).

**Entregables fuera del repo (a propósito, por datos sensibles):**
- `CONSOLIDADO_PRE_AUDITORIA_2026_INTERACTIVO.xlsx` — Excel interactivo
  entregado por chat (ver §15 "contexto"): hojas LEYENDA / PREAUDITORIA
  (400 filas de fórmulas: se escribe el envío y INDEX/MATCH sobre una clave
  `envío-ocurrencia` llena factura/fechas/valor/NIT/entidad, con "n de N" y
  "YA NO TRAE MAS FACTURAS") / RADICACION (36.765 filas precargadas + columnas
  W-X de ocurrencia/clave encadenadas para pegar datos nuevos) / DGREPORT
  (7.231 filas; CORREO F.E. por COUNTIF). **No va al repo porque el DGReport
  contiene nombres y cédulas de pacientes.** Quedó como referencia; la app web
  lo reemplaza. *Soluciones descartadas en él:* XLOOKUP/FILTER/SORT (LibreOffice
  no las evalúa) y COUNTIF acumulativo columna completa (O(n²), inviable) →
  se cambió por ocurrencia encadenada por fila.

---

## 11. DEPENDENCIAS NUEVAS

**Ninguna en el proyecto.** (`requirements.txt` intacto.)
Solo tooling del entorno de desarrollo/CI, no del runtime: `ruff` (lint/format
del CI), `pillow` y `PyMuPDF` (extraer y limpiar la firma del PDF guía — uso
puntual, no requerido por la app), `playwright`+Chromium (pruebas de UI),
LibreOffice `libreoffice-calc` (validar el Excel interactivo; **hallazgo**: el
entorno tenía solo libreoffice-core y por eso todo recálculo se colgaba).

---

## 12. CONFIGURACIÓN

- **Variables de entorno** (las generales de la app; el módulo no añade
  ninguna): `SECRET_KEY`, `DATABASE_URL` (SQLite o Postgres), `ADMIN_PASSWORD`
  (seed), `DISABLE_SCHEDULERS=1` (tests/CI), opcionales `SENTRY_DSN`,
  `POSTHOG_API_KEY`, claves IA del motor (no usadas por este módulo). En la VM
  viven en `/opt/motor-glosas/.env` (git lo ignora; **nunca** se toca en
  despliegues).
- **Rutas**: página `/preauditoria`; API `/preauditoria/*`; estáticos
  `/static/*`.
- **Archivos de configuración especiales**: el `docker-compose.yml` de la VM
  está **personalizado** (`mem_limit: 640m`, `memswap_limit: 640m`, logging
  json-file 10m×3) y difiere del del repo → en cada despliegue se respalda y
  restaura (§16).
- **Recursos del PDF**: `static/LOGO SINAC.png` (obligatorio para el logo) y
  `static/firma_preauditoria.png` (opcional: si falta, queda la línea para
  firma manuscrita). Nombres/cargos de firmas: constantes en
  `oficio_devolucion_pdf.py`.
- **Parámetros de negocio** (constantes en `preauditoria_service.py`):
  `MAX_DEVOLUCIONES=3`, `PLAZO_DIAS_HABILES=3`, prefijo `DEV-PRE-AUD`.
- **Tokens**: JWT de la app en `localStorage.hus_token` (+ `hus_user`,
  `hus_rol`).

---

## 13. RIESGOS (qué puede romperse al integrarlo y cómo resolverlo)

1. **Esquema v1 vs v2 de `preaud_facturas`.** Si otra copia de la BD tiene la
   tabla vieja CON datos, el arranque NO la migra (solo avisa). Resolución:
   vaciarla si es de prueba, o migrar a mano: por factura distinta → 1 fila
   canónica (la de mayor ronda) + reconstruir eventos desde las filas/rondas.
2. **`docker-compose.yml` divergente en la VM.** Un `git reset --hard` lo pisa
   y se pierde el `mem_limit` (→ riesgo real de OOM matando procesos al azar
   en la VM de 1 GB). Mitigación aplicada: respaldar/restaurar en cada
   despliegue (§16). Solución de fondo sugerida: mover esos overrides a un
   `docker-compose.override.yml` ignorado por git.
3. **Archivos con dueño root en la VM** (`docs/diagnostico_lote_v2_pendientes/*`,
   `tests/benchmark/*`): hacían fallar `git reset` con *Permission denied*
   dejando el árbol a medias (la VM quedó días clavada en un commit viejo con
   archivos mixtos — causa real del "me sigue saliendo todo igual").
   Resolución aplicada: `sudo chown -R usuario:usuario /opt/motor-glosas` y
   re-reset.
4. **Zonas horarias.** Regla del proyecto: TIMESTAMPTZ en Postgres, helpers
   `app/core/tz.py`, nunca `datetime.now()` naive. El módulo distingue fechas
   de proceso (UTC↔Bogotá) de fechas de calendario de las fuentes (sin
   conversión). Si se replica lógica nueva, respetar esa distinción o
   reaparece el corrimiento de un día.
5. **CORREO F.E. depende de la ventana del reporte.** El DGReport se exporta
   por rango de fechas (el real cubría solo 1–23 jul): una factura radicada
   fuera de la ventana marca NO aunque el correo exista → con la regla
   "sin F.E. no se radica" puede bloquear indebidamente. Mitigación operativa:
   exportar el DGReport cubriendo el mismo periodo que la Radicación (está
   avisado en BITACORA y en el PR).
6. **SQLite y límites de binds**: ya mitigado (IN troceado a 900, subqueries);
   si se agregan consultas nuevas sobre las fuentes, seguir ese patrón.
7. **Conflictos de fusión recurrentes en `BITACORA.md`/`CLAUDE.md`** entre
   líneas de chat paralelas: resolver **fusionando contenido**, nunca
   escogiendo un lado (ya ocurrió dos veces; ambas se fusionaron a mano).
8. **CI**: ruff exige `--select F,W6` + `format --check` — imports/variables
   sin uso o formato distinto rompen el build (pasó y se corrigió).
9. **Flaky conocido del CI (ajeno al módulo):** `test_heatmap_actividad` /
   `test_por_dia_semana` fallaron una vez en CI ("assert 0 == 2") y pasan en
   local y en re-runs; sospecha de interferencia entre tests. Vigilar.

---

## 14. DEPENDENCIAS CON OTROS MÓDULOS

**Necesita (del anfitrión):** `app/database.py` (`Base`, `get_db`, engine) ·
`app/api/deps.py` (`get_usuario_actual`, `get_coordinador_o_admin`) ·
`app/core/tz.py` (`TZ_BOGOTA`, `a_utc`, `ahora_utc`, `ahora_bogota`) · modelo
`UsuarioRecord` (nombre/rol del auditor) · login `/token` y localStorage del
frontend · registro en `app/main.py` · `pwa.py` para servir la página.

**Lo utilizan:** `static/index.html` (botón del menú y ⌘K). Nadie más consume
sus tablas ni endpoints hoy.

**Relaciones de datos:** las tablas `preaud_*` son autocontenidas (FKs solo
entre ellas). NO tocan `historial` (glosas) ni ninguna tabla del motor. Los
Excel fuente provienen de **Dinámica Gerencial (DGH)** — sistema externo, sin
integración directa: el usuario exporta y sube.

---

## 15. PENDIENTES / MEJORAS PREVISTAS / ERRORES CONOCIDOS

1. **Festivos colombianos en el semáforo**: hoy solo excluye sábado/domingo.
   Mejora prevista: tabla/set de festivos inyectable en `_es_habil`.
2. **Ventana del DGReport** (§13.5): riesgo operativo documentado; mejora
   posible: guardar fecha del último correo y avisar cobertura de la ventana.
3. **Cargar el histórico** del CONSOLIDADO_PRE_AUDITORIA_2026.xlsx para que
   estadísticas y contador de devoluciones arranquen con la historia real
   (el parser ya entiende sus encabezados; falta decidir el mapeo de rondas
   históricas a eventos).
4. **Oficio de devolución multi-oficio** (agrupar devueltas de varios FHUS en
   un solo PDF): diseñado en la fase de diseño, no implementado.
5. **Caso borde del ledger**: si una factura queda PENDIENTE en el oficio A y
   su envío se intenta escribir en el oficio B, se omite con advertencia, pero
   el envío queda registrado como cargado; si luego se resuelve en A, ese
   envío no puede reescribirse en B sin que un admin elimine/libere. Señalado
   por la revisión (prioridad baja-media).
6. **`archivo_dgh`** en `preaud_oficios_recepcion`: columna legado v1 sin uso.
7. **Favicon**: la página lanza un 404 benigno de favicon en consola.
8. **Groq del motor de dictámenes** (ajeno al módulo): reemplazar el modelo
   `meta-llama/llama-4-scout-17b-16e-instruct` (404) por uno vigente para
   ahorrar 2 llamadas fallidas por análisis.
9. **Eliminación masiva**: hace commit por oficio (vía `eliminar_oficio`); si
   se quisiera atomicidad total del lote habría que refactorizar a una sola
   transacción.
10. **Depuración del despliegue**: mover los overrides de la VM a
    `docker-compose.override.yml` (§13.2) y dejar un usuario/propietario único
    en `/opt/motor-glosas` (§13.3).

---

## 16. RECOMENDACIONES PARA FUSIONARLO EN EL PROYECTO PRINCIPAL

1. **Traer la rama principal ya fusionada** (`motor-glosas` contiene PR #186,
   #187 y #189 en orden). Si se integra a otro repo, copiar los archivos de
   §10 y registrar el router + migración en el `main.py` destino.
2. **No tocar** `docker-compose.yml` productivo: respaldarlo antes de
   cualquier `reset` y restaurarlo después (o adoptar el override de §15.10).
3. **Orden de despliegue probado** (VM Google):
   `gcloud compute ssh motor-glosas --zone=us-west1-a --tunnel-through-iap` →
   `cd /opt/motor-glosas && cp docker-compose.yml ~/dc-backup.yml && git fetch
   origin && git reset --hard origin/motor-glosas && cp ~/dc-backup.yml
   docker-compose.yml && docker compose build motor && docker compose up -d`
   (≈30 s de 502 mientras arranca; el lifespan crea/migra tablas solo).
   Verificación rápida: `grep -c "gr-dona" static/preauditoria.html` y el
   mismo grep dentro del contenedor (`docker exec motor-glosas-hus grep -c
   "gr-dona" /app/static/preauditoria.html`) deben dar >0; `git log --oneline
   -1` debe coincidir con `origin/motor-glosas`.
4. **Si el destino ya tiene datos v1** en `preaud_facturas`: migrar antes de
   arrancar (§13.1); el arranque no destruye datos.
5. **Verificación funcional mínima post-integración** (checklist): subir las
   dos fuentes reales → registrar oficio → escribir un envío conocido (ej.
   221181, trae 3 facturas) → verlas autocompletadas en Consolidado →
   devolver una con motivo → generar oficio de devolución → abrir el PDF
   (logo + firma + formato guía) → reescribir el mismo envío ("ya fue
   cargado") → Estadísticas con dona y barras.
6. **Correr la suite**: `pytest tests/test_api/test_preauditoria.py` (35) y la
   suite completa (4.338 verdes al momento de la entrega). CI: ruff F,W6 +
   format + pytest + pip-audit.
7. **Roles**: asegurar que los usuarios de administración tengan
   SUPER_ADMIN/COORDINADOR para ver la eliminación (los botones se pintan por
   `hus_rol` del localStorage → tras cambiar roles, cerrar sesión y volver a
   entrar).
8. **Conservar este documento** junto al módulo y mantener la **BITÁCORA**
   (regla del repo: leerla al iniciar sesión de trabajo y actualizarla al
   terminar, con fecha, en español claro para el auditor).

---

## 17. RESUMEN EJECUTIVO (para el desarrollador que lo mantenga)

El módulo convierte la pre-auditoría de facturas en una base de datos web con
**cero digitación**: dos Excel fuente (Radicación de Cuentas y Formato
Facturación Electrónica) alimentan un consolidado donde **una factura = una
fila canónica** y cada acción queda en un **historial de eventos inmutable con
snapshot**. El auditor registra el oficio FHUS, **escribe solo el número de
envío** y decide radicar/devolver; el sistema deduplica envíos, numera
subsanaciones (1/2/3) sin duplicar facturas, bloquea la 4.ª devolución y la
radicación sin facturación electrónica, controla el plazo de 3 días hábiles
con semáforo, genera el oficio de devolución en PDF (consecutivo
DEV-PRE-AUD-####-AAAA, logo, firma manuscrita, formato oficial, **inmutable**
tras emitirse) y entrega estadísticas interactivas y export a Excel.

**Claves de mantenimiento:** (1) los datos descriptivos NUNCA se copian a la
canónica — se leen de la fuente (auto-sync); si necesitas fijarlos, usa los
snapshots de los eventos; (2) toda transición pasa por
`svc.auditar_factura`/`svc.escribir_envio` — no mutar `preaud_facturas` por
fuera o los contadores/eventos quedan inconsistentes; (3) el PDF se arma desde
eventos sellados — no lo cambies a leer la fila viva; (4) fechas: proceso en
UTC (helpers tz), fuentes como calendario sin conversión; (5) consultas sobre
36k+ filas: JOIN o IN troceado, jamás listas materializadas; (6) reglas de
negocio en constantes del servicio; nombres de firmas en el servicio del PDF;
(7) la seguridad de la eliminación vive en el backend
(`get_coordinador_o_admin`) — el frontend solo esconde botones; (8) el
despliegue tiene dos trampas conocidas (compose personalizado y permisos en la
VM) descritas en §13 con su solución. Pruebas: 35 del módulo cubren cada regla
(inclúyelas en cualquier refactor); las 4 nuevas de la fase 3 son la mejor
especificación ejecutable de las reglas sin-F.E. y de eliminación.
