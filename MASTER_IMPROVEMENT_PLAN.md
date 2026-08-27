# MASTER_IMPROVEMENT_PLAN.md — Programa de Mejora Integral

> **Qué es este archivo.** El tablero del programa de mejora del Motor de
> Glosas. Cada tarea tiene su casilla, y **la casilla se marca solo cuando el
> trabajo está hecho y probado** — nunca por adelantado.
>
> **Cómo se leyó el proyecto.** Todo lo que dice acá está medido sobre el
> código, no supuesto. Al lado de cada hallazgo va el número que lo sustenta y
> el archivo donde está. Donde no hubo forma de medirlo, dice **PENDIENTE DE
> VALIDAR** en vez de inventar.
>
> **Fecha de la auditoría:** 13-08-2026 · **Rama:** `motor-glosas` en el
> commit `3d0eb87`.

---

## 0) El tamaño real de lo que se audita

| | |
|---|---|
| Pantalla principal | `static/index.html`, **26.059 líneas** en un solo archivo |
| Otras páginas | 5 (`preauditoria`, `importar-recepcion`, `importar-masiva`, `presentacion-ia`, `terapia-fisica`) |
| Llamadas al servidor desde el navegador | **326** en `index.html` |
| Rutas del backend | **595** en 69 routers |
| Servicios | 119 en `app/services/` |
| Pruebas | 6.132 pasando (2 fallan por LibreOffice del contenedor, ajenas) |

**Lo primero que hay que decir:** este sistema ya funciona y sostiene la
operación diaria del hospital. El programa de mejora **no autoriza
reescribirlo**. Cada tarea de acá abajo es un cambio pequeño, reversible y
con prueba.

---

## 1) UI/UX — Diseño y experiencia

### 1.1 El sistema de diseño solo lo usa una de seis páginas

**Medido:** `sinac-ds.css` y `sinac-ux.js` se cargan **únicamente** en
`index.html`. Las otras cinco páginas no los cargan (`ds=0 ux=0`).

- [x] Confirmar qué expone el sistema de diseño: `sinac-ds.css` da tokens `--sds-*` (espaciado, color, sombra, radio, transición); `sinac-ux.js` expone `window.SDS_UX` (paleta de comandos, modo enfocado, toast, atajos).
- [x] `preauditoria.html` carga el sistema de diseño.
- [x] `importar-recepcion.html` íd.
- [x] `importar-masiva.html` íd.
- [x] `presentacion-ia.html` íd.
- [x] `terapia-fisica-paciente-encamado.html` íd.
- [x] Prueba que falla si una página del portal deja de cargar el sistema de diseño (12 casos, uno por página y por archivo).
- [x] Que además **usen** los tokens `--sds-*`. **HECHO el 26-08, y al revés de como estaba planteado.**
  Lo que decía esta casilla era falso en sus dos mitades, y solo se supo al medirlo:
  (a) `sinac-ds.css` **no** era «un segundo vocabulario que nadie usa» — 16 de sus reglas
  de color pintan hoy la pantalla de Analizar (dictamen, fichas de cita, campos, botón
  principal); y (b) **sí** había defecto visible: las dos paletas eran colores distintos,
  así que la ficha de cita VERIFICADA salía verde `#16a34a` en el dictamen y verde
  `#2E7D32` en el resto del motor. Tampoco eran 2.072 cambios: bastaron **13** — los
  tokens de color de `--sds-*` pasaron a apuntar a la paleta corporativa, así que el
  nombre que se escribe sigue siendo `--sds-*` y el color que devuelve es el de la casa.
  Ningún uso se tocó. 8 pruebas en `tests/test_frontend/test_un_solo_vocabulario_de_color.py`.

### 1.2 La moneda se formatea de 74 maneras

**Medido:** existe `fmtCOP()` (una sola definición, `index.html:6918`), pero
hay **73 llamadas sueltas** a `toLocaleString('es-CO')` en el mismo archivo,
más una en `preauditoria.html` y un `Intl.NumberFormat` propio en
`sinac-asistente.js`.

Esto no es cosmética: el mismo valor puede salir `$1.234.567`, `1.234.567` o
`1234567` en pantallas distintas, y el auditor concilia contra DGH mirando
esos números.

- [x] Contar los formateadores y localizarlos.
- [x] Formato único en `sinac-ux.js` → `window.SDS_FMT` con `cop`, `num`, `fecha` y `fechaCorta`, para que lo usen las seis páginas.
- [x] Las llamadas sueltas de `index.html` pasan por `fmtCOP` / `fmtNum` / `fmtFecha`: de **73 quedan 2**, y las dos son formatos de fecha con opciones propias, legítimos.
- [x] `preauditoria.html` y `sinac-asistente.js` delegan en el mismo formateador.
- [x] Corregidos 5 `toLocaleString()` **sin idioma**, que en un equipo en inglés escribían «$1,234,567».
- [x] Prueba que falla si aparece un monto formateado a mano, o uno sin idioma, en cualquier página.
- [x] Prueba de que el respaldo no se llama a sí mismo — al hacer este cambio quedó una recursión en `fmtFecha` que habría tumbado la pantalla si `sinac-ux.js` no cargaba.

### 1.3 Siete pantallas se quedaban mudas si fallaba la red

**Corrección de la primera medición.** El primer conteo dio 14 y **estaba
mal**: el detector miraba solo los primeros 4.000 caracteres de cada función,
y las largas sí tenían su `catch` más abajo. Contadas bien con el cuerpo
completo: de **275** funciones que llaman al motor, **268 ya lo manejaban** y
**7 no**.

Las 7: `_resolverComentario`, `_borrarComentario`, `cambiarRol`,
`registrarDecisionEPS`, `loadConciliaciones`, `registrarResultadoConciliacion`
y `loadAudit`.

Las cuatro que **guardan** eran las graves: si se caía la red, el auditor
creía que su decisión había quedado registrada y no había quedado.

- [x] Listar las funciones afectadas, con el cuerpo completo y no con una ventana.
- [x] Las 7 muestran un mensaje entendible cuando falla la llamada.
- [x] Las que guardan dicen expresamente que **no** se guardó («El rol NO se cambió», «La decisión NO quedó registrada», «El resultado NO quedó registrado»).
- [x] Prueba que falla si una función nueva con `fetch` queda sin manejo de error — y una segunda prueba que verifica que el detector siga detectando, para no repetir el error de conteo.

### 1.4 Estados de carga y estados vacíos, disparejos

**Medido:** `showLoading(` aparece 13 veces, `skeleton` 18, `spinner` 2, para
**326** llamadas al servidor. Estados vacíos: 41 apariciones.

- [x] Medir la cobertura actual.
- [x] **Lo que de verdad dolía no era el skeleton: era el silencio.** Contadas las 278 funciones que llaman al motor, **77** tienen `catch` pero el catch solo escribe en la consola del navegador — que el auditor no abre. Si se cae la red, la tabla vieja se queda en pantalla con cara de estar al día. (Primer conteo: 24, y estaba mal; se caían las que mezclan un catch vacío con uno de consola.)
- [x] `avisarNoCargo()` — un solo aviso, con el nombre de la pantalla en cristiano, que dice que **lo que se ve puede estar desactualizado**. No repite antes de 15 s: con la red caída fallan seis cosas a la vez.
- [x] Enchufado en las **14 pantallas donde el auditor mira plata o decide**: vencimientos, historial, tablero, cobranza, resumen del mes, mando (×4), ADRES, contratos, plata recuperada, analítica predictiva y comentarios del expediente.
- [x] **La tarjeta de vencimientos** era la más grave: además se devolvía callada cuando el servidor respondía con error (`if(!r.ok) return;`). Su silencio se traduce en glosas aceptadas por vencimiento (Art. 57 Ley 1438).
- [x] **La cortina de carga decía algo que no era:** `showLoading()` descartaba el mensaje que le pasaban y rotaba siempre «Identificando tipo de glosa…». Mientras el sistema *borraba datos*, la pantalla decía que analizaba una glosa. Ahora respeta el mensaje.
- [x] Prueba que falla si una de esas 14 vuelve a callarse, o si la cortina vuelve a descartar el mensaje (34 casos).
- [ ] Inventario de las pantallas que tardan (>1s) y no avisan. **PENDIENTE DE VALIDAR** — hay que medirlo con el motor del hospital, no se puede desde acá.
- [ ] *Skeleton* en las tablas mientras cargan. Menos urgente de lo que parecía: lo grave era el silencio, no la espera.
- [ ] Estado vacío ilustrado y con acción sugerida en las tablas principales.
- [ ] Las **63 restantes** que fallan en silencio son adornos (insignias, banners, sugerencias). Que un adorno no cargue no le hace perder plata a nadie; se dejan para cuando alguna moleste.

### 1.5 Badges de estado unificados — **medido el 25-08: no hay tal problema**

El inventario se hizo. **La premisa era falsa:** no hay estados pintados de
colores distintos según la pantalla. El único con más de un tono es
`RATIFICADA`, y son los tres del mismo rojo (fondo `#fee2e2`, borde `#ef4444`,
texto `#991b1b`) — que es como se pinta un badge, no una inconsistencia.

- [x] Inventario de los estados que se pintan hoy y de sus colores actuales. **No hay divergencia que corregir.**
- [ ] Una sola clase de badge por estado, con el mismo color en todas las pantallas.
- [ ] Prueba que falla si un estado se pinta con un color distinto en dos pantallas.

### 1.6 Filtros modernos en tablas

- [ ] Inventario de tablas y de qué filtros tiene cada una. **PENDIENTE DE VALIDAR**.
- [ ] Filtro por texto, por estado y por rango de fechas en las tablas de glosas e historial.
  - [x] **Texto, en «Mis glosas»** (26-08). Busca por factura, EPS y código
    sobre las filas ya cargadas. 13 pruebas en
    `tests/test_frontend/test_buscar_y_densidad.py`.
  - [ ] Por estado y por rango de fechas. Sin hacer.
  - [ ] En la tabla de historial y en la del expediente. Sin hacer.

---

## 2) Rendimiento

### 2.1 Veintidós consultas dentro de bucles (N+1)

**Medido:** 22 bucles con una consulta a la base adentro. Los más cargados:

| Archivo | Línea |
|---|---|
| `app/api/routers/glosas_stats.py` | 1798, 8852, 8908 |
| `app/api/routers/admin.py` | 824, 2989 |
| `app/api/routers/preauditoria.py` | 1101 |
| `app/api/routers/dashboard_ejecutivo.py` | 288 |
| `app/api/routers/plantillas_gold.py` | 474 |
| `app/api/routers/mi_desempeno.py` | 178 |
| `app/api/routers/tarifas_contratadas.py` | 453 |

- [x] Localizar los 22 casos con archivo y línea.
- [x] **Medido con la base real del hospital (13-08-2026).** Conteos de `motorglosas.db`:

| Tabla | Filas |
|---|---|
| `preaud_fuente_dgreport` | 206.365 |
| `preaud_fuente_radicacion` | 193.025 |
| `glosas_adres` | 4.619 |
| `preaud_factura_eventos` | 3.061 |
| `preaud_facturas` | 959 |
| **`historial` (las glosas)** | **74** |
| `audit_log` | 57 |
| `clausulas_contrato` | 29 |
| `tarifas_contratadas` | **0** |

- [x] **VEREDICTO: ninguno de los 22 vale la pena corregir.** Veinte consultan `GlosaRecord` (**74 filas**), `TarifaContratadaRecord` (0) o `FacturaPreauditoriaRecord` (959) — a esa escala un bucle con consulta adentro cuesta milisegundos. Dos tocan `FacturaEventoRecord` (3.061), y son operaciones manuales de una vez (generar un oficio de devolución), no una pantalla que se abre cien veces al día.
- [x] **Y las dos tablas de verdad grandes —206.365 y 193.025 filas— no se consultan dentro de ningún bucle.** Cero coincidencias. Eso ya estaba bien resuelto.
- [ ] ~~Corregir los 22~~ — **no se hace.** Sería reescribir código estable sin defecto que lo justifique, contra la regla 1 del proyecto. Se revisa de nuevo si `historial` pasa de unos miles de filas.

### 2.2 Caché de IA — **ya existe y funciona**

**Medido:** `app/services/glosa_service.py:10322` arma una clave `sha256`,
busca primero en memoria (`_CACHE_IA`) y luego en la base
(`_buscar_cache_ia_db`), y guarda en las dos. Ya trae la corrección de la
Ronda 18 sobre la composición del hash.

- [x] Verificar que existe caché de IA en dos niveles (memoria + base).
- [ ] ~~Refactorizar la capa de caché~~ — **no se hace.** Funciona y no hay defecto que lo justifique. Tocarlo violaría la regla 1 del proyecto. Si aparece una falla concreta, se abre tarea nueva con la evidencia.
- [ ] Medir la tasa de acierto del caché en el motor del hospital. **PENDIENTE DE VALIDAR**.

### 2.3 Índices de base de datos

**Medido:** 152 `index=True` sobre 635 columnas en `app/models/db.py`.

- [x] Contar los índices declarados.
- [ ] Verificar que `num_radicado`, `nit_eps` y `estado` estén indexados. **PENDIENTE DE VALIDAR** — hay que mirar campo por campo.
- [ ] Índice donde falte, con la consulta que lo justifica.

### 2.4 Asincronía

**Medido:** 68 rutas `async def` de 595. La mayoría son síncronas, que con
SQLAlchemy sobre SQLite es lo correcto: marcarlas `async` sin cambiar el
acceso a datos bloquearía el bucle de eventos en vez de ayudar.

- [x] Medir la proporción.
- [ ] ~~Convertir rutas a `async`~~ — **no se hace en bloque.** Solo tiene sentido donde la ruta espera por red (IA, portales), y esas ya lo son.

---

### 2.5 Ocho pantallas rotas desde mayo, no una — la causa raíz de «Salud Total»

**Medido en el historial del repositorio:**

- **09-05-2026** (`8f91087` y siguientes): se borran **ocho routers** que el portal usaba, y `3ccefd9` los reemplaza por cáscaras con prefijo `/_removed/` «para no romper los imports». Desde ese día ocho pantallas responden 404 — pero el código se ve ordenado.
- **07-07-2026** (`0c15a71`): se borran las cáscaras. El mensaje dice *«verificado cero callers, eliminación por AST»*. **La verificación por AST solo miró el código Python. El que llamaba era el JavaScript.**
- **13-08-2026**: Yesid abre «Salud Total» y le sale «Not Found». Tres meses después.

Las ocho: `salud_total`, `comentarios_thread`, `notas_privadas`,
`preset_filtros`, `push`, `auditor_forense`, `autopilot`, `noticias`.

**Los datos del auditor nunca se borraron:** `ComentarioThreadRecord`,
`NotaPrivadaRecord`, `PresetFiltroRecord`, `PushSubscriptionRecord`,
`NoticiaSaludRecord`, `ChatConversacionRecord` siguen en `app/models/db.py`.
Solo se había ido la puerta.

- [x] Rastrear la causa raíz con los commits que lo prueban.
- [x] Verificar que los modelos de la base sobreviven (los comentarios y notas del auditor están ahí).
- [x] **Prueba que compara las llamadas del JavaScript contra las rutas montadas** — la verificación que faltó. Con lista de pendientes que solo puede achicarse.
- [x] Repuesta `salud_total` (OT-033).
- [x] Repuestos `comentarios_thread`, `notas_privadas` y `preset_filtros`, desde su última versión funcional del historial.
- [x] `push` (notificaciones al navegador).
- [x] `auditor_forense` (Q&A sobre soportes) — con su hallazgo aparte: la limpieza lo confundió con `auditoria_forense`, que es otra cosa (busca por IP). Son dos funciones distintas.
- [x] `autopilot` (piloto automático) — hubo que reponer además sus dos servicios, `autopilot_service` y `metricas_autopilot`, borrados en la misma limpieza.
- [x] `noticias` (noticias del sector).
- [x] `chat_history` (historial del chat).
- [x] `eventos/heartbeat` y `eventos/recientes` — el polling que refresca los paneles solos. Se borró y después se creó otro `eventos_live.py` con el mismo prefijo pero con SSE, que es otro mecanismo. Ahora conviven.
- [x] **Cero rutas fantasma.** La lista de pendientes de la prueba quedó vacía.

---

## 3) Código interno y arquitectura

### 3.1 Solo 8 de 69 routers declaran el contrato de su respuesta

**Medido:** `response_model=` aparece en 8 routers de 69. Las otras 587 rutas
devuelven diccionarios sueltos: nada garantiza que el campo que el JavaScript
lee siga existiendo mañana.

Es la misma familia de fallo que dejó la pantalla de Salud Total en «Not
Found» tres meses: el frontend depende de nombres que nadie verifica.

- [x] Contar routers con y sin `response_model`. **Corrección al enunciado inicial:** no son «8 rutas sin contrato», son 8 *routers* que sí lo tienen de 69; sin contrato están **587 de 595 rutas**. Ponerle esquema a 587 de una sentada es el cambio gigante que las reglas prohíben.
- [x] Ocho esquemas Pydantic para las rutas que alimentan las pantallas donde un cambio silencioso duele, descritos sobre lo que devuelven **hoy** (campo por campo, leído del código; ninguno inventado ni renombrado).
- [x] Enchufados en seis rutas: tarifas (lista y stats), conciliaciones, Salud Total y el validador ADRES (estado e inicio).
- [x] **Prueba que compara las llaves que lee el JavaScript contra las del esquema.** Es lo que de verdad importa: un `response_model` **filtra**, y todo campo fuera del esquema se cae de la respuesta. Si la pantalla lee uno que quedó por fuera, se queda en blanco sin dar error — el mismo mal que este trabajo vino a evitar. Comprobado quitando un campo a propósito: la prueba lo caza.
- [x] **`GET /glosas/historial`** — y con él, el caso más peligroso de todos. Declaraba `response_model=list` a secas, que no es un contrato: acepta cualquier cosa. Y existía desde hacía meses un `GlosaHistorialItem` con **diez** campos mientras la ruta devuelve **veintiuno**, sin enchufar. Enchufarlo tal como estaba —que es exactamente lo que pedía esta fase— le habría borrado **once columnas** a la tabla de Historial (la factura, el dictamen, la entidad, el CUPS, el servicio, la observación…) y sin dar error. Reescrito sobre lo que la ruta devuelve de verdad, con las 19 llaves que el JavaScript lee y su prueba.
- [x] **`GET /glosas/{id}`** — el expediente. Devuelve 36 campos y no declaraba ninguno. Contrato completo, con las 26 llaves que la pantalla lee. Incluye `dictamen_stale`, el aviso de que la glosa cambió después de generar el dictamen: si el contrato lo borrara, el auditor radicaría un dictamen viejo creyendo que está al día.
- [ ] El resto de rutas del expediente (soportes, comentarios, historial de versiones). **PENDIENTE**.

### 3.2 Lógica de datos dentro de los routers

**Medido:** `db.query(` dentro de routers: `glosas_stats.py` **203 veces**,
`admin.py` 138, `glosas.py` 116, `usuarios.py` 79, `preauditoria.py` 39.

- [x] Medir cuánta consulta vive fuera de los servicios.
- [ ] Extraer a `app/services/` la lógica de negocio repetida, **empezando por lo que ya esté duplicado entre dos routers** (no por volumen).
- [ ] Prueba por cada extracción, para que el resultado sea idéntico.

### 3.3 `index.html`: 26.059 líneas en un archivo

- [x] Medirlo.
- [ ] Decidir si se parte. **DECISIÓN DEL DUEÑO** — partirlo toca las 326 llamadas y es el tipo de cambio gigante que las reglas del proyecto prohíben. Solo se hace si Yesid lo pide expresamente, y por partes.

### 3.4 `glosa_service.py`: 10.536 líneas

- [x] Medirlo.
- [ ] Igual que arriba: es el corazón del motor y funciona. No se reescribe. Se toca por defecto concreto, en la etapa concreta del pipeline.

---

## 4) Funcionalidad y casos borde

### 4.1 Casos borde de la normativa colombiana

- [x] Glosa extemporánea sin fecha de recepción → no se alega el plazo (OT-033).
- [x] Fecha de recepción posterior a la glosa → se descarta el dato (OT-034).
- [x] Tarifa cargada sin vigencia → se puede escribir contrato y fechas (OT-036).
- [x] CUPS sin homologación SOAT → se dice el hecho, no se inventa un código (OT-037).
- [ ] Factura en cero: qué hace el motor hoy. **PENDIENTE DE VALIDAR**.
- [ ] Glosa que objeta más de lo facturado: ya avisa (OT-002); falta el caso de valor negativo.
- [ ] Archivo de notificación vacío o con encabezado cambiado: cubierto para Salud Total, falta para los demás portales.

### 4.2 Mensajes de error entendibles para el auditor

- [ ] Inventario de los `HTTPException` cuyo texto es técnico y no le dice al auditor qué hacer. **PENDIENTE DE VALIDAR**.
- [ ] Reescribir esos mensajes en español claro, diciendo la acción concreta.
- [ ] Que el frontend los muestre (depende de 1.3).

### 4.3 Cobertura de pruebas de los flujos críticos

- [x] Salud Total: 22 pruebas.
- [x] Validador ADRES y autorizaciones: 29 pruebas.
- [x] Tarifas y homologación: 35 pruebas.
- [ ] Conciliación y devoluciones: **PENDIENTE DE VALIDAR** cuánto está cubierto.

---

## Orden de ejecución propuesto

Por daño evitado, no por facilidad:

1. **1.3** — que ninguna pantalla se quede muda cuando falla la red.
2. **1.2** — un solo formato de moneda: el auditor concilia con esos números.
3. **3.1** — contrato de respuesta en las rutas que alimentan las pantallas.
4. **1.1** — sistema de diseño en las cinco páginas que no lo cargan.
5. **2.1** — los N+1, después de medir cuáles pesan.

## Lo que este plan NO va a hacer

- Reescribir `index.html` ni `glosa_service.py`.
- Refactorizar el caché de IA, que funciona.
- Convertir rutas a `async` en bloque.
- Marcar una casilla sin la prueba que la respalde.
