# Registro de cambios

## Sesión 11-sep-2026 (5) — `gc.freeze()` sobre el índice: 455 ms de pausa global a cero

Segunda vuelta de la medición, ya con el arreglo del arranque en producción:
**24 de 826 peticiones sobre 2 s (2,9 %, venía de 34,5 %)** y `GET /health`
—`SELECT 1`— en **93 ms de promedio**.

- **Diagnóstico** — 93 ms en `/health` no es lentitud de ese endpoint: es una
  pausa global que le cae encima a ~1 de cada 5 peticiones. El índice son
  **811.598 objetos** que el recolector de ciclos recorre en cada pasada de
  generación 2. Medido con el `SoporteEntry` real: **455 ms por pasada**
  contra 2,2 ms sin el índice; `0,2 × 455 ≈ 91 ms`, que es el promedio
  observado. El cálculo se hizo antes de tocar el código.
- **`app/services/soportes_autodiscovery_service.py`** —
  `_sacar_el_indice_del_camino_del_recolector()`: `gc.collect()` seguido de
  `gc.freeze()`, llamado en las dos puertas por donde el índice entra a
  memoria (`_cargar_de_disco()` y el cambiazo final de `rebuild()`).
  Comprobado sobre el indexador real: **99 ms → 0 ms** con 300.000 archivos,
  y el `lookup()` sigue devolviendo lo mismo.
- **Seguridad** — `freeze()` solo excluye del recolector de CICLOS; el
  refcounting sigue liberando. `SoporteEntry` es un dataclass plano sin
  ciclos, así que el índice viejo muere al ser reemplazado.
  `test_el_indice_viejo_SI_se_libera_al_reconstruir` lo demuestra con
  `weakref`, no lo afirma.
- **Pruebas** — 4 nuevas (19 en el archivo). Suite completa: 12.819 en verde.
- **Pendiente propuesto, NO hecho** — quedan los picos de 13-15 s del
  arranque: los **14,6 s** de abrir 358 MB de JSON y rearmar 811.598 objetos.
  Ya no bloquean el event loop (van en hilo) pero sí compiten por el GIL. El
  arreglo de fondo es mover el índice a SQLite —`lookup()` pasa a ser una
  consulta indexada, sin carga inicial ni 1,5 GB de RAM—. Es un cambio
  grande: queda propuesto, no metido de sorpresa.


## Sesión 11-sep-2026 (4) — Abrir el índice de soportes congelaba el sitio entero

Primer hallazgo del cronómetro instalado una hora antes. Medido en producción,
un minuto después de un reinicio: **47 de 136 peticiones sobre 2 s**, y
`GET /health` —un `SELECT 1`— en **330 ms de promedio y 3,1 s la peor**. Seis
peticiones distintas terminando en el mismo segundo: cola, no lentitud
individual.

- **Causa** — `_ejecutar_safe()` llamaba `get_indexer()` **dentro de la
  corrutina**. Esa llamada construye el singleton, y `__init__` hace
  `_cargar_de_disco()`: hoy **358 MB de JSON y 811.598 `SoporteEntry`** que
  rearmar. Medido en un árbol del tamaño real: `json.load` 10,4 s +
  reconstrucción de objetos 4,2 s = **14,6 s de GIL tomado**, con el event
  loop bloqueado y el sitio sin atender nada. En cada reinicio del
  autodespliegue.
  La ronda 30 ya había movido `rebuild()` a `asyncio.to_thread` con el
  comentario «bloqueaba el event loop —congelando TODO el sitio—», pero dejó
  `get_indexer()` fuera del hilo: `asyncio.to_thread(get_indexer().rebuild)`
  evalúa `get_indexer()` en el loop antes de lanzar el hilo.
- **`app/services/soportes_reindex_scheduler.py`** —
  `indexador = await asyncio.to_thread(get_indexer)` y después
  `await asyncio.to_thread(indexador.rebuild)`.
- **Pruebas** — 4 nuevas en `test_el_indexador_no_machaca_el_servidor.py`
  (15 en total): que abrir y recorrer van los dos al hilo, que no queda
  ningún `get_indexer().algo` suelto en la corrutina, y una que mide el
  **atraso real del event loop** con un indexador lento simulado y exige que
  el sitio siga respondiendo. Verificado reinyectando el defecto.
  Suite completa: 12.815 en verde.
- **Pendiente de medir** — los números vienen del primer minuto tras un
  reinicio, el peor momento posible. Hay que volver a medir en régimen
  normal antes de concluir que no queda nada más.


## Sesión 11-sep-2026 (2) — Cronómetro de peticiones: saber QUÉ está lento

Al diagnosticar «la plataforma está lentísima» se pudo medir RAM (1,1 GB de
16, con 3,5 libres), CPU (9 %), el share (17 ms) y el motor local (13 ms
contra 130 ms por el túnel) — pero no había registro de cuánto tarda cada
endpoint. La pregunta que importaba era la única sin instrumentar.

- **`app/services/tiempos_peticiones.py`** (nuevo) — cronómetro en memoria,
  acotado a propósito: `agrupar_ruta()` normaliza `/glosas/{n}`,
  `/soportes-auto/factura/{factura}` y UUIDs para que mil glosas abiertas no
  sean mil filas; tope de `MAX_RUTAS` (400) y `deque(maxlen=MAX_RECIENTES)`
  (50) para las lentas. Ordena por `promedio × veces` —lo que se lleva el día
  del auditor— y no por el pico. Sobre `SEGUNDOS_PARA_AVISAR` (2 s) escribe
  `[LENTITUD]` en el log. Medido: **1,53 µs por petición** (0,012 % de una
  petición real).
- **`app/main.py`** — `_cronometro_middleware`, declarado **de último** a
  propósito: Starlette monta los middlewares al revés, así que el último
  declarado es el que envuelve a todos y mide lo que de verdad esperó el
  usuario. El `finally` garantiza que también se anoten las que fallan, y el
  `except` interno impide que medir tumbe una petición.
- **`app/api/routers/diagnostico.py`** — `GET /admin/diagnostico/lentitud` y
  `POST /admin/diagnostico/lentitud/reiniciar` (solo admin).
- **`static/index.html`** — botón «⏱️ ¿Qué está lento?» en Diagnóstico,
  `cargarLentitud()` / `renderLentitud()` / `reiniciarLentitud()`. Tabla por
  pantalla + últimas lentas con hora, y la aclaración de que esto NO mide el
  viaje por internet.
- **Pruebas** — `tests/test_services/test_saber_que_esta_lento.py` (20):
  agrupado de rutas, orden por peso real, topes de memoria, tolerancia a
  valores raros, y que el cronómetro siga siendo el **último** middleware
  declarado (si deja de serlo, mide de menos). Suite: 12.781 en verde.


## Sesión 11-sep-2026 — El indexador de soportes deja de machacar el servidor

Diagnóstico de «la plataforma está lentísima» a las 8:35 a.m. El indexador
recorría `\\Prime\radicacion_2026` (101.991 facturas / 426.405 archivos) en
horario laboral, disparado por el reinicio del autodespliegue de las 8:16.

- **`app/services/soportes_reindex_scheduler.py`** — el build de arranque pasa
  a `_ejecutar_safe(solo_si_hace_falta=True)`: si el índice tiene menos de
  `_HORAS_PARA_NO_REPETIR` (20 h) no se recorre nada. El motor se reinicia
  varias veces al día por el autodespliegue y cada reinicio disparaba un walk
  completo que no aportaba nada sobre el de las 2 AM. El turno diario y el
  botón «Reindexar ahora» (que llama sin la bandera) no cambian.
- **`app/services/soportes_autodiscovery_service.py`** — nuevo
  `_recorrer_con_contenido()`: un `scandir` por carpeta que devuelve
  `(carpeta, archivos, firma)`. Antes había 3 `scandir` + 1 `stat` por
  carpeta (os.walk descartaba su propia lista de archivos, `_firma_de`
  relistaba para contar, y el cuerpo del bucle relistaba para leer) más un
  `Path.stat()` por archivo. `_construir_entry()` acepta ahora el
  `os.stat_result` que el listado ya trajo (en Windows viene en la misma
  respuesta del directorio, sin viaje extra), y los compartidos de lote se
  guardan como `(Path, stat)` para que la pasada 2 tampoco re-pregunte.
  Nuevo método público `construido_hace()`. `_recorrer_carpetas()` y
  `_firma_de()` se conservan para compatibilidad.
  - **Cambio de semántica de la huella**: era `(mtime de la carpeta, nº de
    entradas)`; ahora es `(mtime del archivo más nuevo, nº de entradas)`,
    que se arma con el listado que de todos modos hay que pedir. La primera
    corrida tras el despliegue re-lee todo una vez (las firmas viejas no
    casan) y a partir de ahí el diferencial vuelve a saltar carpetas.
- **Medido** con un contador de `scandir`/`stat` sobre un árbol de 3.000
  facturas / 12.000 archivos con la estructura real: **23.712 → 3.910 viajes**
  (6×), indexando idéntico.
- **Pruebas** — `tests/test_services/test_el_indexador_no_machaca_el_servidor.py`
  (11): tope de viajes por carpeta, el diferencial ve archivo nuevo / factura
  nueva / archivo borrado, tamaño y fecha correctos, y las cuatro rutas del
  arranque (fresco no recorre, viejo sí, sin índice sí, botón siempre). El
  tope de viajes falla si se reinyecta el `stat` por archivo (verificado).
  Suite completa: 12.761 en verde.


## Sesión 10-sep-2026 (6) — Naturaleza contradicha, y Gemini con cupo propio

- **`app/services/quality_gate/post_validator.py`** — nuevo
  `check_no_contradice_la_naturaleza_del_servicio()` (ERROR, check 13). El
  dictamen radicado decía «EL MEDICAMENTO IOBITRIDOL NO ES UN MEDIO DE
  CONTRASTE, SINO UN SOLUCIÓN ANTISEPTICA» sobre una glosa que lo objeta
  llamándolo medio de contraste, y sobre una factura que dice «equivalente a
  30%P/V de yodo». El check es estrecho a propósito: salta solo cuando el
  dictamen niega (`NO ES / NO SE TRATA DE / NO CORRESPONDE A / NO CONSTITUYE`)
  una de las 11 naturalezas de `_NATURALEZAS_QUE_NO_SE_REDEFINEN` **y** esa
  misma naturaleza está en lo que la entidad mandó. `_sin_tildes()` normaliza
  los dos lados (en mayúscula sostenida casi nadie pone tildes, y sin eso el
  caso real se escapaba). Las negaciones jurídicas —«no es extemporánea», «no
  procede»— no se tocan.
- **`app/core/config.py`, `app/services/glosa_service.py`, `.env.example`** —
  `GEMINI_API_KEY_DICTAMEN` opcional: con una segunda llave gratis, los
  dictámenes usan `self.gemini_dictamen` y el OCR se queda con `self.gemini`.
  Vacía (lo de hoy) apunta al mismo cliente y no cambia nada.
- **`app/services/glosa_service.py`** — `_es_falta_de_cuota()` y salida
  inmediata del bucle de reintentos de Gemini ante un 429 / quota /
  RESOURCE_EXHAUSTED, como Groq hace desde junio. Antes se quemaban 7 s y dos
  peticiones más contra un cupo agotado.
- **Pruebas** — `test_no_le_lleve_la_contraria_al_papel.py` (13) y
  `test_gemini_con_su_propio_cupo.py` (19). Los 4 dictámenes reales de
  producción pasan los dos checks nuevos. Suite completa: 12.750 en verde.
- **Verificado sobre el papel:** el dictamen que se radicó ese día, pasado
  hoy por el post-validador, queda en score 0 y **no aprobado**, con
  `[medidas_fabricadas]` y `[naturaleza_contradicha]` nombrando las dos
  mentiras.


## Sesión 10-sep-2026 (5) — CI: reparto por duración medida, cuatro máquinas

Las tres máquinas del reparto por nombre tardaban 2m34 / 3m51 / **4m46**: dos
terminaban y esperaban a la tercera, y el reloj lo marca la más lenta. El
reparto era por nombre de archivo (impares/pares) y los archivos no duran lo
mismo — `tests/test_api/test_preauditoria.py` se lleva 96 s él solo.

- **`scripts/repartir_pruebas.py`** (nuevo) — reparto goloso LPT por duración
  medida: el archivo más pesado a la máquina más liviana. Determinista
  (desempate por ruta, y a igual carga gana el grupo de menor número). Los
  archivos sin medir valen la **mediana**, así que una prueba nueva entra
  igual y nunca se queda por fuera. Sin tabla de duraciones reparte por
  cantidad, que es exactamente lo que había antes. Subcomandos: `--grupos/
  --grupo` (lo que consume el CI), `--resumen` y `--medir junit.xml [...]`
  para rehacer las mediciones desde los artefactos del propio CI.
- **`tests/duraciones_pruebas.json`** (nuevo, 60 KB) — 1.071 archivos medidos.
- **`.github/workflows/ci.yml`** — matriz `grupo: [1, 2, 3, 4]`, nombre
  «Tests (pytest · grupo N de 4)», y el paso de pruebas pasó del `case` de
  bash a `mapfile -t OBJETIVO < <(python scripts/repartir_pruebas.py …)`. El
  agregador `test-ok` no cambia: `needs.test.result` resume la matriz entera,
  así que agregar o quitar grupos no toca nada más.
- **Pruebas** — `tests/test_tools/test_repartir_pruebas.py` (19) y
  `test_el_ci_no_deja_pruebas_afuera.py` reescrito sobre el nuevo reparto
  (26): cobertura archivo por archivo, sin repetidos, sin grupos vacíos,
  determinismo, balance ≤1,25×, degradación sin tabla, y avisos de tabla
  vieja (cobertura ≥50 %, fantasmas ≤20 %).
- **Medido en el CI de verdad** (PR #700, corrida 34545040058), job completo
  con instalación incluida: **2m53 / 2m59 / 3m03 / 3m10**, contra los
  2m34 / 3m51 / **4m46** del reparto por nombre. El *spread* pasó de 2m12 a
  **17 s**. En local (2 núcleos, `taskset -c 0,1`): 141 / 133 / 127 / 128 s
  contra 286 s. Suite completa 12.718 pruebas en verde.


## Sesión 10-sep-2026 (4) — La cláusula citada sin retoques, y la rúbrica del comparador con dientes

- **`app/services/glosa_service.py`** — `_neutralizar_valores_inventados()`
  pisaba las cifras de las cláusulas del contrato inyectadas por el propio
  motor (`_clausulas_contrato`, clave `texto_literal`), porque no venían en
  la glosa. Resultado radicado: «TRES MIL DOSCIENTOS TREINTA Y CINCO MILLONES
  CINCUENTA MIL PESOS MCTE (el valor objetado consignado en el expediente)».
  Ahora `_extras_legitimos` incluye `_texto_clausulas`, `_val_fact_str` y
  `_val_pact_str`. Y `_RE_PARENTESIS_NEUTRALIZADO` borra el paréntesis entero
  cuando la cifra sí era inventada, en vez de dejar la frase neutra donde
  debía ir un número; limpieza de dobles espacios y espacio-antes-de-coma.
- **`tools/comparar_proveedores_ia.py`** — la rúbrica dejó de ser word
  matching puro. Nuevos `Veredicto`, `CapturaDeAvisos` (handler sobre el
  logger `motor_glosas`, nivel WARNING) y `_veredicto_del_motor()`, que leen
  `score`, `confianza`, `bloqueado_para_radicar`, `motivos_bloqueo` y las 10
  marcas de `AVISOS_QUE_DESCALIFICAN` (verificadas contra el código del
  motor, no supuestas). `_correr()` devuelve el veredicto, `_tabla()` marca
  LIMPIO / CON PEGAS y lista los reproches. Décima comprobación: el letrero
  rojo de conceptos sin responder.
- **Pruebas** — `tests/test_services/test_clausula_citada_sin_retoques.py`
  (10) y 8 casos nuevos en `tests/test_tools/test_comparar_proveedores_ia.py`,
  incluido uno que falla si alguien renombra una marca del motor y la rúbrica
  se queda escuchando marcas muertas (verificado reinyectando el defecto).
  8.470 pruebas de servicios, tools, utils y frontend en verde.


## Sesión 10-sep-2026 (3) — `check_medidas_no_fabricadas`: dosis, unidades y números de ítem inventados

Mismo caso (objeción 189801, causal FA0701 del IOBITRIDOL). El dictamen
radicado afirmaba «EL ÍTEM 13 DE LA FACTURA INDICA LA ADQUISICIÓN DE CINCO
UNIDADES DE 100 ML CADA UNA, TOTALIZANDO 500 ML» sobre un medicamento de
50 ML. `check_valores_no_fabricados` no lo veía: solo mira cifras con `$` y
separador de miles.

- **`app/services/quality_gate/post_validator.py`** — nuevo
  `check_medidas_no_fabricadas()` (severidad ERROR, check 12 del post-gate).
  Extrae del dictamen y de la fuente todas las parejas *(número, unidad)*
  —`_PAT_MEDIDA` con unidades canonizadas (CC≡ML, GR≡G≡GRS, UG≡MCG)—, los
  `ÍTEM/RENGLÓN/FOLIO n` (`_PAT_ITEM`) y los conteos de envase
  (`_PAT_CONTEO`), y marca lo que está en el dictamen y no en la fuente.
  `_ANTES_QUE_NO_ES_MEDIDA` evita leer «ANEXO 3 G» como gramos;
  `UN`/`UNA`/`UNO` quedan fuera de `_NUMERO_EN_LETRAS` a propósito (en
  español son artículo, no cuenta) porque un ERROR falso cuesta una
  regeneración de IA y una escalada a humano.
- **`post_validar_dictamen()`, `ejecutar_quality_gate()`** — parámetro nuevo
  `fuentes_adicionales: list[str] | None`.
- **`app/services/quality_gate_adapter.py`** — pasa `[user_prompt]`, que es la
  lista fiel de lo que la IA vio (glosa + contexto contractual + texto de los
  soportes leídos). Así el check solo acusa lo que nadie le entregó.
- **Pruebas** — `tests/test_services/test_medidas_que_nadie_conto.py` (18),
  incluida una que corre los 4 dictámenes reales de `tests/benchmark/casos.json`
  y dos que fallan si alguien desconecta el check del gate (verificado
  reinyectando el defecto). 8.754 pruebas de servicios y API en verde.


## Sesión 10-sep-2026 (2) — Cada causal con su valor, y el panel de soportes que dejó de mentir

Los dos defectos salieron de la objeción real N° 189801 (factura
HUS0000541440): ocho renglones, siete SO4201 por $55.882.100 y uno FA0701 por
$103.000.

- **`app/services/multi_codigo.py`** — `valores_por_codigo()` reescrita. Antes
  abortaba (`{}`) al ver cualquier monto antes del primer código, y en la
  objeción real ese monto es el VALOR FACTURA del encabezado: el reparto no se
  intentaba nunca y los dos bloques del dictamen salían con el total global.
  Ahora acumula **todas** las apariciones de cada código (SO4201 aparece
  siete veces) atribuyendo el primer monto de cada tramo, y **cuadra la suma
  contra el `TOTAL OBJETADO` declarado en el propio texto** (±1 peso). Si
  cuadra, el reparto está probado contra el papel de la entidad; si no, se
  devuelve `{}` en vez de adivinar. Sin total declarado se conserva la regla
  estrecha anterior. Helpers `_a_numero()` / `_formatear()` para los formatos
  colombianos (`$ 6.898.700,00`).
- **`app/services/catalogo_glosas.py`** — `SOPORTE_QUE_EL_MOTOR_NO_VE` y
  `soporte_que_el_motor_no_ve()`. SO4201 exige lista de precios pactada,
  factura de compra y cotización avalada — documentos que no están en el
  índice de radicación ni en los PDF del análisis. `soportes_que_pide()`
  devuelve `()` para esos códigos en vez de caer al patrón de la familia SO
  (historia clínica/epicrisis), que es lo que ponía el panel en verde.
- **`app/api/routers/analizar.py`** — `_evidencia_de_los_soportes()` agrega
  `pide_y_no_lo_veo`.
- **`static/index.html`** — `renderEvidenciaSoportes()` nombra esos documentos
  en la columna de exigidos y `hayDuda` impide que el panel se pinte en verde.
- **Pruebas** — `tests/test_services/test_cada_causal_con_su_valor.py` (15) y
  `tests/test_frontend/test_lo_que_el_motor_no_puede_ver.py` (8). Los 12 casos
  de `test_gl206_valor_por_codigo.py` siguen pasando.


## Sesión 09-sep-2026 (tarde, 8) — `evidencia_soportes`: la mitad que faltaba del panel de análisis

El pedido original («que vean qué van a auditar, o también si es por tarifas
que aparezca el Excel de la tarifa pactada») tenía dos partes. Se entregó la
tarifaria en la sesión anterior; esta es la de soportes.

Mismo patrón que `evidencia_tarifa`: los tres datos existían y se
concatenaban como HTML dentro del dictamen (`_soportes_reales`,
`_documentos_adjuntos`, `catalogo_glosas.soportes_que_pide`), fuera del
alcance de la pantalla.

- **`app/models/schemas.py`** — `GlosaResult.evidencia_soportes`.
- **`app/api/routers/analizar.py`** — `_evidencia_de_los_soportes()` cruza las
  tres fuentes: lo que la causal exige (Res. 2284), lo que el índice del
  servidor de radicación reporta, y los PDF de este análisis. Deriva `faltan`
  con la regla de que **basta uno** de los soportes válidos para la causal.
  `None` sin número de factura.
- **`static/index.html`** — `renderEvidenciaSoportes()` en tres columnas, con
  remate accionable según el caso. Se pinta junto a `renderEvidenciaTarifa`,
  antes del riesgo y de la recomendación.

**`no_se_pudo_consultar`**: cuando el índice está reconstruyéndose (o revienta),
`faltan` queda vacío y el panel dice «todavía no se sabe». Es el defecto que
ya se pagó una vez — expedientes completos reportados como ausentes durante
una reindexación, con bloqueo de radicación incluido.

### Pruebas (35, todas comprobadas contra el código anterior)

- `tests/test_api/test_la_evidencia_de_los_soportes.py` (18) — las tres
  fuentes por separado, la regla de «basta uno», y los cuatro estados del
  índice (con datos / vacío al día / reconstruyéndose / caído).
- `tests/test_frontend/test_el_auditor_ve_que_soporte_le_falta.py` (17) —
  ejecuta el pintor con Node contra las tres formas reales.


## Sesión 09-sep-2026 (tarde, 7) — `_detectar_pagador_en_texto` no conocía los regímenes especiales

Detectado en la prueba del auditor. Glosa «DISPENSARIO MEDICO · FA0801
$275.000…» con `eps_dropdown="FAMISANAR EPS"`: `resolver_eps_efectiva`
devolvió `("FAMISANAR EPS", False, "")` y el dictamen salió con el contrato
S-13-1-03-1-04958 y la tarifa SOAT UVB −5 % de FAMISANAR sobre una factura de
sanidad militar.

`_TOKENS_PAGADOR_EN_TEXTO` tenía `DMBUG` y `DISPENSARIO MEDICO BUCARAMANGA`,
pero no la forma corta ni DIGSA / SANIDAD EJÉRCITO / SANIDAD MILITAR, y no
tenía la Policía Nacional ni FIDUPREVISORA.

- **`app/services/glosa_ia_prompts.py`** — entradas nuevas en
  `_TOKENS_PAGADOR_EN_TEXTO`, todas con **el canónico que ya existía**
  (`DMBUG`, `FOMAG`): devolver uno distinto haría que `get_contrato()` buscara
  con un nombre que la malla no conoce. En `_RE_EPS_SOLA`, CAJACOPI, SAVIA
  SALUD, COMFENALCO y SUMIMEDICAL.

### Pruebas (21, con 10 que fallan sin el arreglo)

- `tests/test_services/test_el_dictamen_no_sale_con_el_contrato_de_otra_entidad.py`
  — el caso exacto, las siete formas de nombrar la sanidad militar, y la
  comprobación de que tres regímenes distintos resuelven a **tres contratos
  distintos** y ninguno al de FAMISANAR. Más una clase entera de no-regresión
  para las EPS del contributivo.


## Sesión 09-sep-2026 (tarde, 6) — `_facturado_linea_cups` leía el pactado como facturado

Detectado en la prueba del auditor. Sobre «VALOR FACTURADO $185.000 SUPERIOR AL
PACTADO $157.250» con `cups="890201"`, `_extraer_valores_glosa` devolvía
`facturado: 157250.0`. La recomendación resultante fue aceptar $105.350 en vez
de $133.100 — y se aplicó.

`_facturado_linea_cups` toma `valores[-1]` de la ventana posterior al CUPS,
correcto para una fila de factura (`CANT VR_UNIT VR_PAC VR_ENT`) e incorrecto
para prosa etiquetada. La guarda existente (`len(todos_montos) < 2 → 0.0`) no
lo cubría: aquí hay dos montos.

- **`app/utils/parsers_glosa.py`** — `_las_cifras_vienen_con_nombre(chunk)`
  detecta las etiquetas que asignan significado a un monto (PACTADO,
  CONTRATADO, RECONOCIDO, OBJETADO, GLOSADO, ACEPTA(DO), TARIFA
  PACTADA/CONTRATADA/VIGENTE, DIFERENCIA). Cuando aparecen,
  `_facturado_linea_cups` devuelve `0.0` y `_extraer_valores_glosa` cae a
  `patrones_fact`, que lee por etiqueta. La regla estricta del CUPS (incidente
  27-abr-2026) queda intacta para columnas mudas. Se añadió también
  `\bFACTUR(?:Ó|O)\b` a `patrones_fact` («SE FACTURÓ $90.000»).

### Pruebas (20, con 7 que fallan sin el arreglo)

- `tests/test_services/test_no_confundir_lo_facturado_con_lo_pactado.py` —
  el caso exacto del auditor, cuatro variantes de redacción, y la verificación
  de que las filas de factura no se marcan como prosa. Las 8 de
  `test_parser_facturado_cups.py` (incidente de abril) siguen pasando.


## Sesión 09-sep-2026 (tarde, 5) — La evidencia de la tarifa, como dato y no como texto

Pedido del área: al analizar una glosa de TARIFAS, ver el renglón del catálogo
pactado y las cifras, para poder auditarlo. El cruce contra las 19.051 filas de
`tarifas_contratadas` ya existía (`_pre_lookup_tarifa` → `evaluar_glosa_tarifa`),
pero su salida se **prepend-eaba como HTML al `dictamen`**: no renderizable como
tabla, y contaminando el escrito radicable.

- **`app/models/schemas.py`** — `GlosaResult.evidencia_tarifa: Optional[dict]`.
- **`app/api/routers/analizar.py`** — `_evidencia_de_la_tarifa(info_tarifa)`
  estructura la fila del catálogo (CUPS, `codigo_ips`, descripción,
  `valor_pactado`, `tipo_tarifa`/`factor_ajuste`, modalidad, contrato, vigencia
  y `fuente_archivo`) más las cifras del caso. **La diferencia solo se calcula
  con las dos cifras presentes** — en este motor `0` significa «no se pudo
  leer», y restar contra él produciría un sobrecosto ficticio del tamaño de la
  tarifa; los ceros se entregan como `None` y se enumeran en `no_se_pudo_leer`.
  Devuelve `None` cuando no hay fila que mostrar. Se asigna al resultado tras
  `service.analizar`.
- **`static/index.html`** — `renderEvidenciaTarifa()` pinta las tres cifras, la
  diferencia explicada en castellano (tres desenlaces: por encima, exacta, por
  debajo), el aviso de homologación cuando `aplicada`, y un `<details>` con el
  renglón del contrato. Se invoca **antes** de `renderRiesgoRatificacion` y
  `renderAccionIA`: leído después del veredicto, nadie revisa la evidencia.

### Pruebas (38, todas comprobadas contra el código anterior)

- `tests/test_api/test_la_evidencia_de_la_tarifa.py` (21) — incluye los casos
  de cifra ausente, diferencia cero legítima vs. incalculable, y homologación.
- `tests/test_frontend/test_el_auditor_ve_la_tarifa_pactada.py` (17) — ejecuta
  el pintor con Node contra las formas reales; comprueba sobre el texto plano
  que no aparezca `$0` donde falta el dato, y que el orden en pantalla ponga la
  evidencia antes del veredicto.


## Sesión 09-sep-2026 (tarde, 4) — La Confianza se guarda; el panel dejó de confundir dos métricas

El diagnóstico corrió contra la base real (397 glosas) y devolvió
«Confianza promedio por modelo: 77%» — mientras el auditor ve 51% al pie de
sus dictámenes. Los dos números eran ciertos y medían cosas distintas:

- `historial.score` (77%) = `_calcular_score()`, fórmula fija por tipo de
  glosa (99 extemporánea / 92 ratificación / 90 urgencia / 75 tarifa / 85
  resto, +5 con PDF). No lee el escrito.
- La Confianza (51%) = `confidence_scorer.calcular_confianza()`, siete
  factores ponderados — **y no se persistía en ninguna parte**.

Con lo cual la pregunta que motivó el diagnóstico («¿qué modelo de IA da
mejor Confianza?») era incontestable, no por falta de volumen sino porque el
número nunca se escribía.

### Persistencia de la Confianza

- **`app/models/db.py`** — `GlosaRecord.confianza_score` (Float, 0-100 para
  que se lea igual que en pantalla) y `confianza_nivel` (String(10)). Sin
  default: las 397 filas previas quedan en NULL, que es la verdad.
- **`app/main.py`** — migración en caliente (`ADD COLUMN` para ambas), en el
  patrón de las demás de `historial`.
- **`app/repositories/glosa_repository.py`** — `crear()` las acepta.
- **`app/api/routers/analizar.py`** — `_confianza_para_guardar(resultado)`
  convierte `{score: 0.51}` → `(51.0, "medio")` y devuelve `(None, None)`
  ante cualquier forma inesperada: **nunca 0**, que hundiría el promedio del
  modelo sin explicación. Se escribe en las dos ramas (crear y re-analizar);
  al re-analizar solo pisa si este análisis sí la calculó.

### El panel deja de llamar Confianza a lo que no lo es

- **`app/api/routers/diagnostico_calidad.py`** — `probabilidad_exito_por_modelo`
  (la fórmula vieja, con su nombre) y `confianza_por_modelo` como objeto con
  `glosas_con_confianza_guardada`, `detalle` (promedio + peor + mejor por
  modelo) y `diagnostico`.
- **`static/index.html`** — `_diagTabla()` como helper compartido. «Confianza
  real por modelo» va **primero**; «Probabilidad de éxito (fórmula antigua)»
  después, con la fórmula escrita y la advertencia de que no sirve para
  comparar modelos. Sin datos aún, el recuadro dice qué hacer en vez de
  mostrar un 0% que se leería como «el motor saca cero».

### `TypeError` real en la consola del auditor

`sinac-ux.js:216 Cannot read properties of undefined (reading 'toLowerCase')`,
dos veces al entrar al portal: el gestor de contraseñas del navegador emite
eventos `keydown` sin `e.key` al autocompletar (uno por campo). No tumbaba la
página pero apagaba todos los atajos en ese evento.

- **`static/sinac-ux.js`** — `const tecla = typeof e.key === 'string' ?
  e.key.toLowerCase() : ''` con salida temprana; las dos llamadas (⌘K y el
  `switch`) usan la variable. Las comparaciones `e.key === 'Escape'` se dejan:
  con `undefined` dan `false`, no revientan.

### Pruebas (33, todas comprobadas contra el código anterior)

- `tests/test_api/test_la_confianza_se_guarda.py` (19) — conversión, los seis
  casos que deben quedar en blanco, las columnas, la migración y las dos ramas
  de guardado.
- `tests/test_frontend/test_no_se_confunde_la_confianza_con_la_formula_vieja.py`
  (9) — ejecuta el panel con Node contra la respuesta real de hoy (0 con
  Confianza) y contra una futura con dos modelos. Compara sobre el **texto
  plano**, no el HTML: buscar «0%» en el marcado encuentra `width:100%`.
- `tests/test_frontend/test_el_autocompletado_no_revienta_los_atajos.py` (5) —
  dispara el evento sin `key` contra el manejador real.


## Sesión 09-sep-2026 (tarde, 3) — El diagnóstico en pantalla, y dos afirmaciones sin respaldo

Las tres del mismo tipo: el motor decía algo que no le constaba.

### 1. El diagnóstico de calidad, dentro del motor

`GET /admin/diagnostico-calidad` se publicó por la mañana y resultó
inalcanzable: escrita en la barra del navegador, la ruta responde
`{"detail":"Token de autenticación requerido"}` — correctamente, porque el
navegador no manda el Bearer. La ruta existía y nadie podía usarla.

- **`static/index.html`** — panel `#admin-diagnostico-card` en la pantalla de
  Usuarios, visible solo con rol `SUPER_ADMIN` (nace con `display:none` y lo
  destapa `loadUsuarios()`, igual que los otros dos paneles de administrador).
  `cargarDiagnosticoCalidad()` pide la ruta con `authH()` y `_diagPintar()`
  la renderiza en español —cada cifra con la frase que dice qué significa—
  en vez del JSON crudo. Falla visible en pantalla tanto por red caída como
  por respuesta de error (`r.ok`), nunca solo en consola.

### 2. La ratificación no afirma una respuesta previa que no consta

`TEXTO_RATIFICADA` abre con «SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE LA
GLOSA INICIAL». En el caso 4 de la prueba salió sobre una factura sin
ninguna respuesta anterior en el historial.

- **`app/services/glosa_service.py`** — `_hay_respuesta_inicial_registrada()`
  consulta `historial` por número de factura y devuelve `True` / `False` /
  `None`. `None` («no se sabe»: factura ausente del historial, sin número, o
  base no disponible) **no** dispara nada, igual que el aviso de soportes con
  el índice a medio construir. Solo `False` agrega el aviso `⛔ NO RADICAR
  TODAVÍA: NO HAY RESPUESTA INICIAL REGISTRADA`, y la marca entra en
  `_MARCAS_DE_BLOQUEO` para que `bloqueado_para_radicar` lo impida — un
  hallazgo grave bloquea, no aconseja. La propia ratificación no se cuenta a
  sí misma como la respuesta que mantiene.

### 3. No se le atribuye a la IA lo que la IA no hizo

Con `modelo_ia = "texto_fijo"` la IA nunca corrió y `accion_ia` sale de
`_mapa_accion` (Python), pero el recuadro decía «💡 La IA recomienda
DEFENDER 100%»: una segunda opinión inexistente, con autoridad prestada.

- **`static/index.html`** — `renderAccionIA()` deriva la atribución de
  `d.modelo_ia`: «📋 Regla fija del área» para `texto_fijo`, `plantilla`,
  `abstencion` y `directo_auditor`; «💡 La IA recomienda» solo cuando la IA
  analizó. Las cuatro frases del panel también salen de esa variable.

### 4. Un CUM no se rotula CUPS en la ficha del prompt

La regla 4 del system prompt ya prohibía escribir «CUPS» sobre un CUM. Pero
el BLOQUE 1 —declarado AUTORITATIVO— rotulaba `• CUPS : 20123-1` y remataba
con «USA ESTE CUPS». Entre una regla general y un dato concreto con una orden
al lado, gana el dato: salió «el código homologado del CUPS facturado» sobre
acetaminofén.

- **`app/services/glosa_ia_prompts.py`** — `_es_codigo_cum()` (forma
  `\d{4,9}-\d{1,3}`, la misma de `citation_verifier._FORMA_CUM`, duplicada
  adrede porque este módulo arma el prompt y no puede depender del que revisa
  el resultado). La fila usa la etiqueta real y, con un CUM, `_nota_cups`
  prohíbe explícitamente «CUPS X», «el CUPS facturado» y «código homologado
  del CUPS», más el Manual Tarifario SOAT (no rige precios de medicamentos).
  Un CUPS con anexo (`39147B-18`) sigue siendo CUPS.

### 5. Una corrección automática ya no deja una cita rota

Salió publicado «…LEY 1438 DE 2011 ART. EL DECRETO 780…». Perseguir cuál de
las decenas de redes cortó mal es interminable; se valida el resultado.

- **`app/services/glosa_service.py`** — `_quitar_articulo_huerfano()` exige
  las dos orillas: a la izquierda el final de una cita completa (`(?<=\d)`), a
  la derecha el arranque de otra norma (`EL|DEL|LA|…` + `DECRETO|LEY|
  RESOLUCIÓN|…`). Corre después de todas las redes que reescriben citas y
  registra la corrección en `_correcciones` — el artículo perdido puede
  hacerle falta al gestor. La prosa vaga pero correcta («el artículo del
  decreto») no la dispara.

### 6. El riesgo de ratificación no contradice al sello de bloqueo

Salía «riesgo BAJO — alta probabilidad de levantamiento» junto a «⛔ NO
RADICAR». Ambos los calcula el motor.

- **`app/services/riesgo_ratificacion.py`** — `elevar_por_bloqueo(riesgo,
  motivos)`: con bloqueo, piso en 61 (ALTO), color/icono/etiqueta coherentes y
  cada motivo añadido a `factores`. No muta el dict original y sin bloqueo
  devuelve el mismo objeto — `calcular_riesgo` sigue mandando.
- **`app/services/glosa_service.py`** — se aplica justo después de calcular
  `_motivos_bloqueo`, antes de armar el `GlosaResult`.

No se tocó «DEFENDER 100%» junto a «riesgo ALTO»: no es contradicción — uno
dice qué responde el hospital, el otro qué se espera de la entidad.

### Pruebas (75, todas comprobadas contra el código anterior)

- `tests/test_frontend/test_el_diagnostico_de_calidad_se_ve_en_pantalla.py` (4)
- `tests/test_frontend/test_el_diagnostico_pinta_los_numeros_de_verdad.py` (11),
  que EJECUTA el pintor con Node contra la forma real de la respuesta: las
  otras leen el HTML como texto y no verían un «undefined» en pantalla.
- `tests/test_frontend/test_no_dice_que_la_ia_recomienda_si_la_ia_no_corrio.py` (5)
- `tests/test_services/test_no_se_mantiene_una_respuesta_que_no_existe.py` (15),
  con SQLite en memoria, los tres desenlaces del helper y tres de extremo a
  extremo por `GlosaService.analizar` (probadas contra el cableado desactivado).
- `tests/test_services/test_un_medicamento_no_se_llama_cups.py` (17)
- `tests/test_services/test_una_correccion_no_puede_dejar_una_cita_rota.py` (14)
- `tests/test_services/test_el_riesgo_no_contradice_al_sello.py` (9)

## Sesión 09-sep-2026 (tarde, 2) — `GET /admin/diagnostico-calidad`

Los números detrás de la confianza baja solo se ven en la base real del
hospital. Pedirle al auditor que corriera un script por consola era pasarle
trabajo manual; esto lo vuelve un enlace que abre y copia.

- **`app/api/routers/diagnostico_calidad.py`** (nuevo) — solo lectura, solo
  SUPER_ADMIN. Devuelve: % de glosas con EPS genérica y el detalle de las
  que sí tienen nombre; filas en `tarifas_contratadas` (con el diagnóstico
  escrito cuando está vacía); cobertura de `clausulas_contrato`; % de glosas
  con veredicto final de la EPS —de ahí se alimentan el precedente interno y
  `few_shot_gold`, y por debajo del 30% lo dice explícitamente—; confianza
  promedio **por `modelo_ia`** (la comparación Groq vs. Claude con datos
  propios); y costo real por proveedor leído de `ai_calls`, con proyección
  mensual al volumen actual.

Complementa `scripts/diagnostico_calidad_ia.py` (misma información por
consola, para quien tenga acceso al servidor).

9 pruebas nuevas. Verificado contra un servidor real con datos sembrados.


## Sesión 09-sep-2026 (tarde) — El desplegable de EPS no puede depender de tener contrato

SURA, SALUD TOTAL, EMSSANAR, SAVIA y MUTUAL SER —entidades reales, con bot de
portal propio y lógica propia en el resto del motor desde hace meses—
nunca aparecían en «EPS / Entidad Pagadora» del botón Analizar: el
desplegable se llenaba solo con `GET /contratos/`, o sea con las EPS que
tienen `ContratoRecord`. El auditor solo podía elegir «OTRA / SIN DEFINIR»,
y todo dictamen de esas cinco entidades salía genérico.

- **`app/services/catalogo_eps.py`** (nuevo) — el catálogo fijo de entidades
  reales, y `eps_seleccionables()` para unir varias fuentes sin repetidos.
  Cada entidad agregada ya estaba en uso en otra parte del motor (bot de
  portal, rama de lógica de negocio); no se inventó ninguna.
- **`GET /contratos/eps-seleccionables`** — une tres fuentes: el catálogo
  fijo, las EPS con `ContratoRecord`, y las que ya aparecen en
  `GlosaRecord.eps` sin tenerlo. `/eps-sin-contrato` (ya existía) no bastaba
  sola: solo lista EPS que YA están en el historial, y una EPS que nunca se
  pudo seleccionar tampoco pudo quedar guardada con su nombre real — un
  candado que se cierra solo.
- **`loadContratos()`** — el `<select id="eps-sel">` del botón Analizar ahora
  se llena también desde la ruta nueva. La grilla de la pantalla Contratos
  sigue mostrando solo contratos reales (no se infla con entidades sin
  contrato). El fallo de esa llamada avisa con `avisarNoCargo`, no se traga
  en la consola (regla del `MASTER_IMPROVEMENT_PLAN.md`, 1.3).
- **`extractor_factura.py`** — su lista propia de EPS conocidas (que se había
  quedado atrás, sin MUTUAL SER/EMSSANAR/SAVIA) ahora importa del catálogo
  nuevo: una sola fuente, no dos copias que se desincronizan.
- **`scripts/diagnostico_calidad_ia.py`** (nuevo) — reporte de solo lectura
  para correr en el servidor del hospital: EPS genéricas vs. con nombre,
  filas en `tarifas_contratadas` (tarifa pactada por CUPS), cobertura de
  `clausulas_contrato`, qué fracción de las glosas tiene ya el veredicto
  final de la EPS registrado (de ahí se alimentan el precedente interno y el
  banco de argumentos ganadores), el promedio de confianza real por
  `modelo_ia`, y el **costo real** de Anthropic leído de `ai_calls` —esa
  tabla ya existe y ya calcula el costo en dólares por llamada; no hay que
  estimarlo, solo leerlo.

39 pruebas nuevas. Comprobado en navegador: con la base vacía, las cinco
entidades ya aparecen en el desplegable. El script de diagnóstico se probó
con datos sembrados (65 glosas, dos modelos, EPS mixtas) y se limpiaron
después.


## Sesión 09-sep-2026 — Todo 401 va al manejador de sesión vencida

El auditor abrió el motor a las 8:15 con la sesión de la noche anterior (el
token dura 8 h) y en Usuarios le salió el `detail` crudo de FastAPI:
«Error · Credenciales inválidas o token expirado».

- **El envoltorio global de `fetch`** —el que ya existía para los 403— atrapa
  ahora también el **401** y llama a `manejarSesionExpirada()`, que ya decía
  «Tu sesión venció — vuelve a iniciar sesión» y devuelve al login
  conservando el formulario. Va ahí porque es el único punto por el que pasan
  las 173 llamadas: arreglarlo sitio por sitio dejaría el siguiente afuera.
- **`/token` queda excluido**: el login contesta 401 con la contraseña mala y
  eso no es una sesión vencida; su pantalla ya lo explica. Se compara la ruta
  sin los parámetros.
- `manejarSesionExpirada()` ya traía sus dos guardas y se conservan: no avisa
  si no hay token guardado, y avisa **una sola vez** aunque varios sondeos de
  fondo reciban 401 a la vez.

8 pruebas nuevas. Comprobado en navegador con las rutas interceptadas: un 401
en `/usuarios/`, `/2fa/estado` y `/notificaciones/badge` avisa una vez cada
uno; en `/token`, ninguna.


## Sesión 08-sep-2026 (noche, 4) — Lo que destapó la segunda corrida

Los cinco casos, vueltos a correr tras los arreglos. Lo anterior quedó bien;
salieron cuatro cosas nuevas.

- **Un hallazgo de severidad ALTA bloquea.** `_bloqueos_para_radicar()` ahora
  recibe `verificacion_citas`: una cita ALTA es bloqueo aunque no haya dejado
  marca en el texto. En la pantalla, el pie del recuadro deja de decir «solo
  orientativo» cuando hay graves. Caso 2: el verificador marcó
  AFIRMACION_SIN_SOPORTE en ALTA y el dictamen salió sin sello verde pero sin
  bloquear.
- **`_cifra_del_escrito_no_es_la_de_la_glosa()`** — caso 1: la glosa objetaba
  $19.500 y el texto radicable decía «POR UN VALOR OBJETADO DE $ 19.». Compara
  solo las cifras que el escrito PRESENTA como valor objetado (topes, UVB y
  valores de contrato tienen sus propias redes) con tolerancia del 1 %.
  Bloquea.
- **`_RE_NORMA_DEL_VACIO_TARIFARIO`** — la contradicción con la ficha, en otra
  forma: invocar el art. 87 del Decreto 2423/1996 (servicios SIN tarifa
  asignada) teniendo pacto. Sin pacto esa norma es legítima y no se marca.
- **Telemetría**: `float(re.sub(r"[^\d.]", ...))` leía el punto de miles como
  decimal — «$ 19.500» → 19.5 — y con dos puntos lanzaba `ValueError` y caía al
  `except` con 0.0. Toda glosa ≥ $1M iba al bucket «<100K». Ahora usa
  `parse_valor_cop`, que existe justo para esto.
- **`_MARCAS_DE_BLOQUEO`** += «AFIRMA SIN PROBAR» (el escrito enumera los
  soportes con los que se radicó sin señalar un folio).

32 pruebas nuevas + 4 de pantalla. Comprobado en navegador: con ALTA, sello
rojo y pie «no es opcional»; con MEDIA, sello verde y pie orientativo.


## Sesión 08-sep-2026 (noche, 3) — El escrito no puede contradecir la ficha del motor

Caso 1 de la prueba del botón Analizar (TA0701, COOSALUD). El motor tiene el
contrato cargado y lo imprime en el recuadro del dictamen; la argumentación del
mismo documento decía «EL VALOR LIQUIDADO COINCIDE CON LA TARIFA SOAT PLENO» y
«COOSALUD NO HA APORTADO ELEMENTOS DE PRUEBA QUE DEMUESTREN LA EXISTENCIA DE
UNA TARIFA PACTADA DISTINTA O INFERIOR».

- **`_contradice_la_ficha_contractual(argumento, ficha)`** — cruza el texto del
  argumento contra la ficha de `get_contrato`. Detecta tres cosas: decir «SOAT
  PLENO» con descuento pactado, negar el contrato que el motor tiene, y
  exigirle a la entidad probar una tarifa pactada que el hospital ya tiene.
  Devuelve las frases con ambos valores nombrados, para que el gestor lea qué
  contradice a qué.
- **`_hay_tarifa_pactada_de_verdad(ficha)`** — las tres puertas que evitan el
  falso positivo: sin contrato, con `_vigencia_vencida` o con
  `_tarifa_indeterminada` no se marca, porque ahí decir «SOAT pleno» es
  correcto. Y un pacto A SOAT pleno (factor 1.0) tampoco contradice.
- **Bloquea, no avisa.** Nueva marca en `_MARCAS_DE_BLOQUEO`, así que el sello
  sale rojo por la vía de la PR anterior. El aviso de `[PLATA-INVENTADA]` ya
  existía y solo avisaba: el caso 1 salió sellado en verde encima de la
  contradicción.
- **No reescribe el argumento.** Redactarle la defensa jurídica al modelo es
  peor que marcarlo.

La red anterior (`_vigencia_vencida`) solo cubría el contrato vencido; con uno
vigente nadie cruzaba el texto contra la ficha.

28 pruebas nuevas, incluido el párrafo del caso real palabra por palabra.


## Sesión 08-sep-2026 (noche, 2) — Cuatro señales del dictamen que se contradecían

Prueba de cinco casos desde `/analizar` (TA0701, SO3401, CL0101, FA1605,
CO4601). La IA no fallaba de fondo; fallaba lo que el motor decía de sí mismo.

- **`GlosaResult.bloqueado_para_radicar` + `motivos_bloqueo`** — el motor ya
  escribía «⛔ NO RADICAR TODAVÍA» en el texto pero no se lo decía a la
  pantalla, que estampaba «✓ VALIDADO POR QUALITY GATE» encima.
  `_bloqueos_para_radicar()` lee las marcas que el propio motor deja
  (falta de soporte de la causal, entidad sin identificar, afirmar contenido
  de documentos no aportados). En `renderResult`, si viene bloqueado el sello
  es rojo (`.qg-bloqueado`, «⛔ NO LISTO PARA RADICAR») con los motivos en el
  `title`; el verde solo cuando no. Respuestas sin el campo (caminos de
  salida temprana, historial viejo) se comportan como antes.
- **`_neutralizar_eps_generica_en_dictamen()`** — con la EPS en «OTRA / SIN
  DEFINIR», el escrito radicable decía «INTERPUESTA POR OTRA / SIN DEFINIR» y
  «SE SOLICITA A OTRA / SIN DEFINIR PRECISAR». Se sustituye por «LA ENTIDAD
  RESPONSABLE DE PAGO» **solo la forma suelta**: la del aviso al gestor
  («quedó como «OTRA / SIN DEFINIR»») se conserva. `_parrafo_cobertura_soat`
  deja de usar el marcador como nombre. En los dos impresos (`imprimirDictamen`
  e `imprimirLoteConsolidado`) el marcador sale como «ENTIDAD PAGADORA SIN
  IDENTIFICAR».
- **`_paciente_honesto()`** — el prompt daba por defecto «PACIENTE
  IDENTIFICADO EN EXPEDIENTE» y la cabecera lo mostraba sobre facturas sin
  expediente. Ahora el prompt, `dictamen_directo` y el post-proceso dicen
  «PACIENTE NO IDENTIFICADO EN LOS SOPORTES» cuando no hay nombre.
- **`_avisos_de_soportes_no_leidos()`** — los avisos «no se adjuntó ningún
  soporte» y «sí se adjuntaron, pero ninguno de ese tipo» salían juntos con
  cero PDF: el segundo se calculaba contra un texto vacío y todo le parecía
  faltante. Ahora la decisión se toma una vez: sin soportes va el de cero; con
  soportes, la revisión por tipo.

63 pruebas nuevas (51 de servicio, 10 de pantalla, 2 actualizadas). Chequeo
en navegador de `renderResult` con resultado simulado en los tres estados.


## Sesión 08-sep-2026 (noche) — Los soportes de mesa van a disco, en flujo

El auditor reportó que sus escaneos pesan **25–40 MB**. El tope era de 15 MB
—un número escogido sin dato— y los dejaba a todos afuera. Pero subir el
número a secas habría tumbado el motor.

### Lo que había mal, y no era el tope

- El archivo se guardaba como base64 en SQLite: +33% de tamaño.
- `soportes_subidos()` hacía `query(SoporteMesaRecord).all()`, así que
  SQLAlchemy traía **todas** las columnas, `contenido_b64` incluida. Listar
  diez soportes de 40 MB eran ~500 MB de texto en memoria.
- `docker-compose.yml` fija `mem_limit: 640m` y su propio comentario
  documenta que el OOM killer ya mató procesos al azar antes.

### Cómo queda

- **`guardar_soporte_en_disco()`** — escribe en pedazos de 1 MB. La memoria
  usada no depende del tamaño del archivo. El tope se comprueba **mientras**
  se escribe: 500 MB se cortan a los 50, no se sostienen para después
  rechazarlos. Lo escrito a medias se borra.
- **`carpeta_de_soportes()`** — deriva de `SOPORTES_ROOT`, así que en el
  hospital cae en `/data/soportes_mesa`: el volumen persistente, junto a la
  base. El motor se autoactualiza cada 5 minutos; fuera del volumen, la
  evidencia de una audiencia duraría minutos.
- **Nombre en disco propio** (`AAAAMM/<uuid>.<ext>`) — el nombre que pone el
  usuario puede traer `../` y escribir fuera de la carpeta.
- **`sha256`** por soporte — un archivo alterado no sirve de evidencia.
- **`soportes_subidos()`** pide solo las columnas que muestra.
- **Descarga con `FileResponse`** — por pedazos, no entera en memoria.
- **`MAX_BYTES_SOPORTE = 50 MB`**, y el mismo tope en el frontend.
- Aviso en pantalla cuando el archivo pasa de 8 MB: «puede tardar, no cierre
  la ventana». Sin eso, el auditor cree que se colgó y le da otra vez.

### Compatibilidad

`contenido_b64` pasa a ser opcional y se sigue leyendo: los soportes subidos
esta tarde, antes del cambio, se bajan igual. Migración en `app/main.py` para
`ruta_relativa` y `sha256`.

15 pruebas nuevas, incluidas: que un escaneo de 30 MB entra, que el
contenido NO queda en la base, que listar no lee los archivos, que lo
rechazado no deja basura en disco, que un nombre con `../` no escribe fuera
de la carpeta, y que la carpeta cae en el volumen persistente.


## Sesión 08-sep-2026 — Suite en cero fallas, gates de verdad y subida de soportes

### La suite ya no arrastra doce fallas

- **`office_tools.modulos_libreoffice_faltantes()` / `libreoffice_puede_convertir()`** —
  la causa real de las doce fallas: `libreoffice-core` instalado sin Writer,
  Calc ni Draw. `hay_libreoffice()` solo miraba el ejecutable, así que
  `soffice` «existía» y la conversión moría con «source file could not be
  loaded» — un mensaje que manda a buscar un archivo dañado que no existe.
  Ahora `a_pdf()` comprueba el módulo del tipo de archivo ANTES de intentar y
  nombra el paquete a instalar.
- **`scripts/preparar_entorno_pruebas.sh`** — instala LibreOffice completo y
  `extract-msg` (con `--no-deps`: su dependencia `red-black-tree-mod` ya no
  compila, y solo hace falta para re-escribir `.msg`, no para leerlos). Lo usa
  el CI y sirve igual en un contenedor de desarrollo.
- **`tests/test_tools/_entorno.py`** — en un PC sin las herramientas las
  pruebas se saltan diciendo qué falta; en el CI,
  `EXIGIR_HERRAMIENTAS_DE_PRUEBA=1` hace que la ausencia reviente al importar.
  Un `skipif` ahí dejaría el CI verde con doce pruebas saltadas.

### Gates que de verdad bloquean

- **`scripts/revisar_vulnerabilidades.py`** — el paso de seguridad terminaba
  en `|| true`: encontraba 22 vulnerabilidades y decía que todo estaba bien.
  Ahora falla ante cualquier vulnerabilidad **nueva**; las conocidas están en
  `seguridad/vulnerabilidades_conocidas.txt`, a la vista. Poner el gate en
  cero de una vez dejaría el CI rojo permanentemente y bloquearía los propios
  arreglos.
- **Job `CI OK`** — una sola casilla que exige los tres pasos, para que el día
  que se agregue un cuarto no quede fuera del gate.
- **`.github/rulesets/motor-glosas-protegida.json`** — la protección lista
  para importar. Aplicarla requiere permisos de dueño del repositorio.

### El indexador ya no puede pintar en blanco

- **`app/services/soportes_contrato.py`** — modelos Pydantic
  (`SoporteDeFactura`, `RespuestaSoportes`) y `leer_soportes()`, el único
  camino que deben usar las pantallas. Cinco estados explícitos:
  `CON_SOPORTES`, `SIN_SOPORTES`, `INDEXANDO`, `SIN_INDICE` y
  `DATOS_INVALIDOS`. Un registro malo se descarta y se **cuenta**; no tumba a
  los buenos ni se cuela como fila vacía. Nunca lanza: un índice caído es un
  estado que se pinta, no una excepción que tumba la mesa.
- **`mesaPintarSoportes()`** en el frontend — una sola función pinta los cinco
  estados. Los errores en rojo (`.mesa-sop-err`), lo que aún no se sabe en
  ámbar (`.mesa-sop-duda`). «Dice que hay 3 y no se pudo leer ninguno» ya no
  es una caja vacía.

### Subir soportes en la mesa

- **`SoporteMesaRecord`** — guardado en la base y no en el share: el índice
  del hospital se reconstruye cada tantas horas y un archivo puesto a mano
  desaparecería. Por factura, no por renglón.
- **`validar_soporte()`** — peso (15 MB), tipo (PDF e imágenes) y **firma
  real** del archivo: el `content-type` lo manda el navegador y un ejecutable
  renombrado a `.pdf` llega diciendo «application/pdf».
- **Cuatro rutas** bajo `/conciliaciones/mesa/{id}/soportes-subidos`. Una mesa
  cerrada devuelve 409. La descarga filtra por mesa —cambiar el número en la
  dirección no abre los soportes de otra audiencia— y sanea el nombre para
  que no inyecte cabeceras.
- **Frontend** — el peso se comprueba antes de mandar, el botón se bloquea
  mientras sube (un doble clic no sube dos veces) y se desbloquea en
  `finally`, con spinner que respeta `prefers-reduced-motion`.

93 pruebas nuevas.


## Sesión 07-sep-2026 (noche, 2) — La mesa muestra por qué se glosó y con qué refutar

La tabla cortaba el motivo de la glosa a media línea y no decía si la factura
tenía soportes. Con la EPS al frente, eso obligaba a abrir el Excel aparte.

- **`glosa_del_motor()`** (`mesa_conciliacion.py`) — enlaza el renglón con la
  glosa del historial por factura **y** código. Solo por factura traería la
  primera de doce y se mostraría el dictamen de otra. Se guarda en
  `MesaLineaRecord.glosa_id` al abrir la mesa (migración en `app/main.py`).
- **`detalle_linea()`** — devuelve el dictamen del motor, los soportes y los
  comentarios del equipo. Cuando la glosa no está en el motor (vino solo en el
  archivo de la EPS) lo dice explícitamente en vez de responder vacío.
- **`_soportes_de()`** — **tres** estados, no dos: `CON_SOPORTES`,
  `SIN_SOPORTES` y `INDEXANDO`/`SIN_INDICE`. Decir «no tiene» mientras el
  índice se construye induce a aceptar una glosa soportada.
- **`soportes_de_la_mesa()`** — consulta por factura, no por renglón: doce
  glosas de la misma factura comparten soportes y recorrer el índice doce
  veces daría la misma respuesta.
- **Pantalla** (`static/index.html`) — flecha que despliega el motivo completo
  con `white-space:pre-wrap` (+ `title` para verlo al pasar el mouse), columna
  de soportes con insignia, botón «Gestionar» que abre un cajón lateral con
  cuatro secciones, y limpieza de la tabla (renglones alternados, hover,
  `tabular-nums`).
- **`.mesa-drawer[hidden]{display:none}`** — sin esta regla el `display:flex`
  ganaba sobre `hidden` y el fondo invisible del cajón se comía todos los
  clics de la página.

Corregido en el camino:

- `lookup()` del indexador devuelve **diccionarios**, no objetos: se leían con
  `getattr` y el cajón mostraba «3 soportes» con tres nombres en blanco. Va
  con prueba que falla contra el código anterior.
- El ayudante `_funcion()` de `test_mesa_conciliacion_pantalla.py` cortaba el
  cuerpo a 2.600 caracteres: agregarle una línea a la función dejaba el resto
  fuera y las pruebas de «esto no aparece» (`toLocaleString`) pasaban sin
  haber mirado. Ahora corta en la función siguiente.

30 pruebas nuevas (11 de API, 18 de pantalla, 1 de regresión de soportes).


## Sesión 07-sep-2026 (noche) — La mesa de conciliación vive en el motor

El acta se arma, se guarda y se trabaja en pantalla; el Excel sale al final.

- **`MesaConciliacionRecord` + `MesaLineaRecord`** — el acta en curso y sus
  renglones. Tres dueños por renglón que no se mezclan: lo que trajo la EPS
  (solo lectura), lo que decide la mesa y lo contable.
- **`app/services/mesa_conciliacion.py`** — `abrir()`, `guardar_linea()`,
  `resumen()`, `cerrar()`, `reabrir()` y `a_excel()`. Solo los campos de
  `CAMPOS_EDITABLES` se tocan: el valor objetado y el código son de la EPS.
  Guardar NO impide repartir de más —en una mesa se tantea— pero devuelve el
  pendiente al instante y el `revisar()` lo atrapa al cerrar.
- **`app/services/conceptos_nota_hus.py`** — el catálogo de contabilidad, 234
  combinaciones. El centro de costo sale de `conceptos_glosa` (DGH) y se
  consulta con vía ACTAS. Sin centro en el catálogo devuelve None: no se
  aproxima una cuenta contable.
- **Siete rutas** bajo `/conciliaciones/mesa`. Reabrir exige coordinador.
- **Pantalla**: tabla con encabezado fijo, guardado automático, botones
  «todo A/L/R» por renglón, renglones en ámbar cuando falta decidir, y la
  tabla ancha recorriéndose en su propia caja.
- **58 pruebas nuevas** (20 de ruta, 19 de pantalla, 19 de servicio y
  catálogo).

## Sesión 07-sep-2026 (hotfix) — El acta generada abría «[Reparado]»

- **`_reponer_lo_que_openpyxl_se_lleva()`** — openpyxl no edita el `.xlsm`, lo
  reconstruye, y descarta 3 de los 5 `definedNames` del modelo (los
  `_FilterDatabase` de ACTA, GLOSAS y TRAMITES), dejando el superviviente
  reasignado a `Hoja3`. También pierde `printerSettings` y las rels de una
  hoja. Se repone todo desde el original tras guardar. `calcChain.xml` y
  `sharedStrings.xml` se dejan fuera a propósito: son cachés, y un calcChain
  previo a la escritura es en sí mismo un disparador de reparación.
- **`_borrar_renglones_sobrantes()`** — el modelo trae 260 filas prebordeadas;
  un acta de 3 líneas salía con 257 de cuadrícula vacía. Se les quita borde y
  relleno en vez de borrar las filas: `delete_rows` correría el pie del acta
  (bloque de observaciones y firmas, en celdas combinadas) y lo rompería. El
  fin de la banda de datos se detecta por la primera combinación bajo el
  encabezado, no por un número fijo.
- **11 pruebas nuevas**: los 5 nombres sobreviven y cada autofiltro sigue en
  su hoja, no falta ninguna parte salvo las dos cachés, las líneas reales
  conservan su formato y el pie no se movió.

## Sesión 07-sep-2026 (tarde) — Armar el ACTA SINAC desde la lista y el archivo de la EPS

Faltaba el paso de **aguas arriba** del módulo de conciliación: ya se sabía
leer, revisar y optimizar un acta llena, pero no armarla. Se hacía a mano.

- **`app/services/acta_conciliacion_armar.py`** — cruza la lista de facturas
  con el consolidado de la EPS y produce `Acta` + `LineaActa`, las mismas
  estructuras de `acta_conciliacion_excel`, así que lo generado pasa tal cual
  por el `revisar()` que ya existía: el acta sale llena **y cuadrada**.
  - Llave del cruce tolerante a los tres formatos del número de factura.
  - Encabezados de la EPS buscados **por nombre**, no por posición (cada EPS
    manda el consolidado en otro orden), con emparejado exacto para que
    «VALOR FACTURA» no le robe la columna a «FACTURA».
  - Tipificación deducida del código (CL/FA/SO/TA), verificada contra las 257
    líneas del acta 709 del Dispensario.
  - `escribir_en_modelo()` vuelca sobre el `.xlsm` oficial con `keep_vba`,
    resolviendo las celdas combinadas del encabezado (openpyxl solo deja
    escribir en la superior izquierda del grupo).
- **`ConciliacionTipificacionRecord`** — memoria por factura + código de lo
  que decidió una persona. Lo que el código no puede deducir (pertinencia
  mixta vs. médica) se pregunta una vez y queda guardado.
- **`POST /conciliaciones/acta-excel/armar`** — con `solo_revisar` devuelve el
  parte; si no, el `.xlsm` con el parte en la cabecera `X-Acta-Parte`.
  **`POST /conciliaciones/acta-excel/aprender`** alimenta la memoria desde el
  acta ya trabajada.
- **Pantalla** en Conciliación: dos zonas de arrastre, las casillas del
  encabezado, «Ver qué sale» y «Armar y descargar acta».
- **`plantillas/ACTA_SINAC_modelo.xlsm`** — el formato oficial en blanco.
- **58 pruebas nuevas** (39 de servicio, 19 de ruta y pantalla).

Lo que NO se rellena solo: el tipo de las glosas de pertinencia (decisión
clínica) y los valores de aceptar/levantar/ratificar, que se escriben en la
audiencia.

## Sesión 07-sep-2026 — Pre-Auditoría: tres defectos de producción

Hallados auditando el código, no por una prueba fallida: los tres se
manifiestan solo con volumen o con el paso del tiempo.

- **HTTP 500 en facturas de más de 2.000 renglones.** `traducir()` corría
  fuera del `try/except` del router, así que el tope de `items` del
  `PayloadFactura` salía como `ValidationError` crudo — y el docstring del
  endpoint promete que lo único que devuelve error es un cuerpo ilegible
  (422). Además los modelos del RIPS no tenían tope, de modo que el cuerpo
  entero se convertía en objetos Pydantic antes de que nada lo revisara: un
  RIPS de cápita podía agotar la memoria del proceso, que es uno solo para
  todo el hospital. Se sube `items` a 20.000, se agregan `MAX_POR_FAMILIA` y
  `MAX_USUARIOS` en `preauditoria_rips.py` (cortan antes de construir), y se
  envuelve `traducir()` con un 422 que explica la salida. Verificado: 2.001 y
  5.000 ítems → 200; 20.001 → 422. No se trunca: descartar renglones en
  silencio en una auditoría financiera es peor que rechazar.
- **~265 MB por consulta en el tablero.** `db.query(PreAuditoriaEventoRecord)`
  cargaba la entidad completa, incluido `payload_base` (531 KB en HUS559077),
  para pintar una tabla que no lo muestra. Se pasa a `load_only` con las trece
  columnas que la vista usa; `/eventos/{id}` sigue leyendo el payload entero,
  que es una sola fila.
- **`dinero_salvado` congelado a los 5.000 eventos.** El `limit(5000)` iba
  sobre `order_by(id.asc())`, o sea que conservaba los más viejos: al mes de
  uso la cifra dejaba de crecer, en silencio y a la baja. Se reemplaza por una
  ventana de 90 días (`creado_en >= ahora - 90d`), sin tope de filas, y el
  resumen devuelve `dias`. El orden ascendente se conserva: la lógica de
  «bloqueada y después pasó» solo se lee hacia adelante en el tiempo.
- **12 pruebas nuevas** en `tests/test_api/test_preauditoria_limites_y_metrica.py`,
  cuatro de ellas candados contra el propio arreglo.

## Sesión 04-sep-2026 (hotfix) — Falsos positivos de la Pre-Auditoría

Primera prueba contra una factura real del share (`Rips_HUS559077.json`,
531 KB, $141.720.044): respondió en **32 ms** pero con 63 alertas, dos
fuentes de ruido propias.

- **`regla_topes_tarifarios` calla sin EPS.** El RIPS de la Res. 2275 no trae
  pagador; sin él `tarifa_pactada_de` caía al catálogo oficial del HUS y
  comparaba contra el precio propio del hospital — 48 BLOQUEOS irresolubles,
  mientras `omisiones` afirmaba que la tarifa no se había cruzado. Ahora la
  guarda es `ctx.db is None or not payload.eps.strip()`, y el mensaje de
  omisión dice la verdad. Con EPS la regla opera sin cambios.
- **`regla_cruce_edad` ignora DISPOSITIVO y MEDICAMENTO.** En un artículo,
  «neonatal / pediátrico / adulto» es talla o dosis, no paciente: el insumo
  `FMQ0098` salía BLOQUEADO como servicio pediátrico en adulto. La regla
  sigue firme en estancias, consultas y procedimientos.
- **9 pruebas nuevas** (`tests/test_services/test_preauditoria_falsos_positivos.py`),
  la mitad de ellas comprobando que el arreglo NO debilitó las reglas: UCI
  pediátrica en adulto y procedimiento neonatal en adulto siguen bloqueando,
  y con EPS los topes siguen disparando con el mismo valor en riesgo.

## Sesión 04-sep-2026 — V3 Pilar 2: mapeo RIPS real + tablero

Con el primer archivo real del HIS (`Rips_HUS558039.json`) se ajusta el
endpoint al formato normativo y se construye la pantalla.

- **`app/services/preauditoria_rips.py`** — modelos Pydantic del RIPS
  (Res. 2275/2023) y traductor a `PayloadFactura`. Se traduce en vez de
  reescribir las reglas: las nueve duras y sus 108 pruebas no se tocaron.
  Lee las siete familias de servicios (`consultas`, `procedimientos`,
  `urgencias`, `hospitalizacion`, `recienNacidos`, `medicamentos`,
  `otrosServicios`) con `extra="ignore"` y arreglos en `null` tolerados.
- **`POST /pre-auditoria/evaluar`** acepta el RIPS (se reconoce por
  `usuarios`) o la forma interna; 422 explícito si no es ninguna.
- **Tres huecos del RIPS, dichos en voz alta** en el campo `omisiones` de la
  respuesta, no como alertas: sin EPS (no se cruza tarifa ni contrato), sin
  notas clínicas (nuevo estado `OMITIDO_SIN_NOTAS`, la IA no corre y no
  aborta) y sin total de factura. `eps` deja de ser obligatoria en
  `PayloadFactura`.
- **Con varios usuarios en una factura no se cruzan sexo ni edad**: el RIPS
  no dice de quién es cada servicio cuando se leen juntos. La plata sí se
  suma toda.
- **`GET /pre-auditoria/resumen`** y `preauditoria_concurrente.resumen()` —
  dinero salvado = facturas BLOQUEADAS que después volvieron a pasar; las que
  nunca volvieron van aparte en `riesgo_sin_resolver`. Una sola consulta.
- **Pantalla Pre-Auditoría** en `static/index.html` (panel `p-pre-auditoria`,
  entrada de menú, prefijo `preAud*` porque `pa*` ya estaba tomado):
  tarjetas, tabla con filtros por dictamen y factura, y modal de reparos.
  Verificada en Chromium a 1280/900/480/360 px.
- **70 pruebas nuevas**: 21 del traductor sobre el archivo real, 20 del
  endpoint y el tablero, 29 de la pantalla.

## Sesión 04-sep-2026 (hotfix) — Rescate de filas RECLAMADAS

Tapa una fuga del Pilar 1: `reclamar_una` marcaba la fila `RECLAMADA` y, si el
bot moría en el paso siguiente (playwright ausente, navegador que no arranca,
portal que no abre), la fila quedaba invisible para todos — los demás equipos
solo ven `PENDIENTE` y las personas miran las atoradas.

- **`radicacion_eps.rescatar_reclamada()`** — devuelve la fila a `PENDIENTE`,
  escribe el diagnóstico en `ultimo_error` y limpia el sello del equipo. Solo
  actúa sobre `RECLAMADA`: cualquier otro estado responde `no_rescatable`, y en
  particular `EN_PORTAL_SIN_CONFIRMAR` no se trae de vuelta jamás.
- **Cortacircuito** — a `MAX_INTENTOS_RESCATE` (3) muta a `HUMANO_REQUERIDO` en
  vez de seguir rebotando. El contador NO se incrementa en el rescate:
  `reclamar_una` ya lo sumó al entregar la fila, y volver a sumarlo haría
  saltar el corte a las dos vueltas en vez de a las tres.
- **`POST /radicacion/{id}/rescatar`** — puerta del agente (token de máquina).
- **`radicador_comun`** — `ColaMotor.rescatar()` (se traga los fallos de red:
  se llama cuando el bot ya se está muriendo) y perímetro de rescate en
  `correr()` alrededor del import de playwright, del arranque del navegador y
  de `abrir_sesion`. `SesionNoDisponible` sigue yendo a `humano_requerido`, no
  a la cola: un portal con captcha no es un equipo enfermo.
- **27 pruebas nuevas** (`tests/test_api/test_rescate_fila_reclamada.py`),
  incluida la caída del worker con la fila en la mano y el ciclo completo de
  tres intentos hasta el cortacircuito.
- Máquina de estados actualizada en `docs/ARQUITECTURA_V3_PILAR1_RPA.md`.

## Sesión 04-sep-2026 — V3 Pilar 2: Pre-Auditoría Concurrente (backend)

El HIS del hospital consulta el motor **antes de timbrar** una factura y recibe
un dictamen en menos de 10 segundos. Solo backend y pruebas; la pantalla queda
para después.

- **`POST /pre-auditoria/evaluar`** — sincrónico, dos puertas: el HIS con
  `X-Agente-Token` (comparado con `compare_digest`) y el auditor con su sesión.
  Contrato rígido de salida: `status`, `alertas`, `valor_en_riesgo`,
  `recomendacion_accion`, más trazabilidad.
- **Cadena de validación (Chain of Responsibility)** en
  `app/services/preauditoria_reglas_duras.py`: aritmética, topes tarifarios,
  cruce de género y de edad, vías quirúrgicas excluyentes, coherencia de fechas
  y estancia, doble facturación, contrato vigente y UCI sin criterio escrito.
  Todas deterministas; ninguna inventa (sin tarifa cargada, la regla calla).
- **Cruce clínico con Groq** (`preauditoria_cruce_clinico.py`) al final de la
  cadena, con reloj propio: tope de 6 s y corte por `asyncio.wait_for`. Sus
  hallazgos son siempre ADVERTENCIA — la IA nunca bloquea una factura. Modelo
  dedicado (`preauditoria_modelo`, por defecto `llama-3.3-70b-versatile`): el
  `groq_model` general es un razonador y no cabe en el presupuesto de tiempo.
- **Presupuesto de latencia** en `preauditoria_concurrente.py`: techo duro de
  10 s (reglas + IA + escritura), con degradación elegante si la IA falla.
- **Tabla `pre_auditoria_eventos`** — un evento por evaluación, con el payload
  tal como llegó, el dictamen, la plata en riesgo y los tiempos por tramo.
- **Códigos de glosa oficiales** del Manual Único (`catalogo_glosas.py`)
  proyectados por tipo de servicio; una prueba impide que se cuele un código
  inventado.
- `tarifa_lookup_service.tarifa_pactada_de()` y
  `reglas_casos_fno.sexo_exigido_por_el_procedimiento()`: dos accesos públicos
  a lógica que ya existía, para no duplicarla.
- **108 pruebas nuevas** (64 de reglas, 44 de la ruta), con los casos que pidió
  el auditor: múltiples cirugías por vías excluyentes y estancia en UCI
  injustificada.
- Arquitectura: `docs/ARQUITECTURA_V3_PILAR2_PREAUDITORIA.md`.

## Sesión 04-sep-2026 — «El CSV son solo datos, no dice nada de velas»

Duda razonable del usuario, y merecía una respuesta demostrable en vez de una
explicación: **una vela japonesa ES esos cuatro números**. El cuerpo va de la
apertura al cierre, hueca o llena según cuál quedó arriba, y las mechas hasta
el máximo y el mínimo. TradingView pinta exactamente eso; el gráfico no añade
ni un dato que no esté en el archivo.

- **`mercados/dibujo.py` + `python -m mercados vela`**: dibuja una sesión en la
  consola con cada precio señalado donde le corresponde, las cuentas del libro
  ya hechas («mecha inferior 2,3 veces el cuerpo») y qué patrones encajan ahí.
- Se guarda el **índice** de la sesión, no la vela: dos sesiones con los mismos
  cuatro precios son iguales entre sí, y buscarlas por valor habría devuelto la
  primera en vez de la pedida.
- **11 pruebas nuevas** (130 en `tests/test_mercados`, 599 en total).

## Sesión 31-ago-2026 (cierre) — Análisis de velas japonesas (`mercados/`)

Módulo independiente que detecta los 28 patrones del libro de Luis M. González
sobre un histórico en CSV y **mide si cumplen lo que el libro promete**. No
predice precios ni genera señales de compra o venta: nada en el libro ni en la
evidencia pública lo sostiene, y construirlo habría sido inventar.

### Lo que trae
- **28 detectores** (12 individuales, 16 combinados), cada uno con la
  definición textual del libro y su caso de prueba construido a mano.
- **Catálogo en JSON** con el texto del libro y la página de cada patrón,
  validado contra los detectores por `python -m mercados revisar`.
- **Lector de CSV** tolerante: cabecera ES/EN, separador `,`/`;`/tab, decimales
  con coma o punto, orden ascendente o descendente. Columna faltante = mensaje
  con nombre propio.
- **Medición** con tasa base, intervalo de Wilson y veredicto en una línea.
- **Aplicación web** instalable, sin internet, con cuatro pantallas.

### Los tres cuidados que la hacen creíble
- **Tasa base.** Cuántas veces el precio fue en esa dirección en TODAS las
  sesiones. Sin esa comparación, en un mercado alcista todo patrón alcista
  «funciona».
- **Muestra mínima de 30 casos**, dicha explícitamente en cada veredicto.
- **Corrección por comparaciones múltiples (Bonferroni).** Se hacen 112
  preguntas (28 patrones × 4 horizontes): al 95 % de siempre, ~6 salen
  «significativas» por azar. Comprobado con datos aleatorios: sin corregir
  aparecía un patrón con +19 puntos sobre su base en 37 casos; con la
  corrección, ninguno.

### Accesibilidad de las gráficas
El validador de la guía de visualización da **ΔE 4,1 (deutan)** entre el verde
y el rojo: por debajo del mínimo de 8. El color no lleva significado — la vela
que sube va **hueca** y la que baja **llena** (la forma original japonesa), y
toda etiqueta de dirección lleva ▲/▼ junto a la palabra. Las barras de medición
usan una sola serie con la base como marca de referencia; lo que no llega a 30
casos sale rayado.

### Honestidad de fuente
Las etiquetas de fiabilidad del libro se muestran **atribuidas al autor** y sin
respaldo declarado. La «Cubierta de la Nube Oscura» queda marcada con
`"revisar"`: el libro no exige el cierre bajo la mitad del cuerpo que sí pide
la literatura clásica, y se implementó lo que dice el libro.

Pruebas: **112** (`tests/test_mercados`), 586 con las del ICFES y noruego.
Comprobado además en Chromium a 390 px: cuatro pantallas, 28 fichas, 120 velas,
sin errores de JavaScript ni desbordes.

## Sesión 31-ago-2026 (noche 6) — Todos los botones 🔊 estaban mudos

La causa de fondo de todo el enredo de la voz.

- **El navegador cortaba el manejador a la mitad.** Los botones se armaban con
  `onclick="decir(${JSON.stringify(texto)})"`. `JSON.stringify` devuelve el
  texto entre comillas **dobles**, y el atributo HTML también va entre comillas
  dobles: el navegador leía `onclick="decir("gå")"`, lo cortaba en la primera
  comilla, y el atributo quedaba en `decir(` — con su «Unexpected end of input»
  en la consola. **Los 12 botones de audio de la aplicación no hacían nada**:
  «Toca para oír», «🐢 Más despacio», «🔊 Oír» y «🐢 Despacio» del veredicto, y
  los 🔊 del diccionario, la gramática y las conversaciones.
- **Por qué costó tanto verlo.** Lo único que sí hablaba era lo que no pasa por
  un atributo: el audio al acertar (se llama desde JavaScript) y, desde el
  arreglo anterior, el automático al aparecer (va por un atributo de datos).
- **Una sola puerta: `alPulsarDecir()`.** Escapa el JavaScript para HTML (`esc`
  convierte la comilla en `&quot;`) y todos los botones que hablan salen de
  ahí. De paso, el 🔊 de los errores recientes dejó de borrar los apóstrofos
  del texto, que era lo que hacía para esquivar el problema.
- **3 pruebas nuevas** (208): que ningún `onclick` lleve un `JSON.stringify` sin
  escapar, que todos los botones salgan del ayudante y que el ayudante escape.

Comprobado en Chromium con voz simulada: hablan los cinco sitios probados
—automático, «Toca para oír», «Más despacio», «Oír» del veredicto y el 🔊 del
diccionario— y el `onclick` ya llega entero (`decir("øl")`), sin errores.

## Sesión 31-ago-2026 (noche 5) — «Escucha y elige» no sonaba al aparecer

Fallo real reportado desde el uso: en los ejercicios de escucha la palabra
**no se oía al aparecer el ejercicio**, solo al pulsar «Comprobar».

- **Era código muerto.** `tras()` buscaba un elemento con `data-autoaudio` para
  decirlo al pintar la pantalla… y **ningún ejercicio ponía ese atributo**. Lo
  único que hablaba solo era `comprobar()`, que dice la palabra al acertar.
  Resultado: «escucha y elige» funcionaba como «lee y elige».
- **`audioGrande()` ahora sí lo marca**, y con ello quedan cubiertos los tres
  ejercicios de oído que lo usan: `escuchar_opcion`, `escuchar_escribir` y
  `pronunciar` (este último dice «escúchalo y repítelo», así que también debe
  sonar solo).
- **Dos condiciones para no molestar:**
  - `data-audio-clave` (sesión + número de ejercicio) impide que la palabra se
    repita **en cada toque de opción** — tocar una opción vuelve a pintar la
    pantalla entera.
  - No suena con la respuesta ya revelada: ahí ya habla `comprobar()`, y sonaría
    dos veces encima.
- **4 pruebas nuevas** (205) y comprobación en Chromium con una voz noruega
  simulada: al aparecer el ejercicio dice `['øl']`, tras tocar dos opciones
  sigue en `['øl']`, y al pasar al siguiente ejercicio de oído vuelve a hablar.

## Sesión 31-ago-2026 (noche 4) — Windows no deja instalar la voz en el PC del hospital

El usuario llegó al sitio correcto (Hora e idioma → Voz → Agregar voces) y
Windows respondió **«No se pudo instalar el paquete de voz»**. Los dos paquetes
listados —el noruego y el español— aparecían con **0 MB**: ese equipo no está
descargando contenido de idioma en absoluto.

- **La causa no es la aplicación ni el usuario.** Es un equipo de dominio
  (`esehus.loc`): las actualizaciones pasan por el servidor de Sistemas, que
  normalmente bloquea las *características a petición* (paquetes de voz e
  idioma). Se habilita con la directiva «Especificar la configuración para la
  instalación y la reparación de componentes opcionales», permitiendo bajar de
  Windows Update en vez de WSUS. Eso lo hace Sistemas, no el usuario.
- **El aviso de la app lo dice ahora.** En Windows, después de los pasos,
  advierte del error exacto y ofrece la salida que sí funciona: el celular,
  donde Android e iPhone traen la voz noruega.
- **1 prueba nueva** (201): que el tramo de Windows nombre el error literal y
  ofrezca el celular.

La aplicación sigue siendo usable sin voz: los ejercicios de escuchar muestran
la palabra escrita y la pronunciación aproximada sigue debajo de cada palabra.

## Sesión 31-ago-2026 (noche 3) — La casilla de la voz en Windows no se llama así

Corrección de una instrucción equivocada que se entregó al usuario.

- **El nombre estaba mal.** La app decía «marcando **Voz** entre las funciones
  opcionales». En esa pantalla de Windows la casilla se llama **«Texto a voz»**
  — «Voz» a secas no existe ahí, y «Reconocimiento de voz» es otra cosa
  (dictado).
- **Y ese camino es peligroso.** En la misma pantalla de *Idioma y región →
  Agregar idioma* está **«Establecer como mi idioma de presentación de
  Windows»**: marcarla por error deja **todo el PC del hospital en noruego**.
- **Se cambió al camino corto:** *Configuración → Hora e idioma → **Voz** →
  Administrar voces → Agregar voces → «Noruego (Bokmål)»*. Instala solo la voz
  y no toca el idioma del sistema.
- La guía documenta los dos caminos y advierte del riesgo del primero.

Comprobado en Chromium con user-agent de Windows: el aviso muestra el camino
nuevo y ya no nombra el de «Idioma y región».

## Sesión 31-ago-2026 (noche 2) — La voz noruega: aviso sin salida y voces tardías

En la prueba real la app dijo «este dispositivo no tiene voz noruega» y ahí
quedó: el usuario no tenía cómo saber que eso se instala.

- **Fallo real: las voces llegan tarde y la pantalla no se redibujaba.** Chrome
  entrega `speechSynthesis.getVoices()` de forma asíncrona; la primera llamada
  casi siempre devuelve una lista vacía. Como el aviso se cocina al dibujar,
  un aparato **que sí tiene** la voz veía «no hay voz» hasta cambiar de
  pantalla. Ahora `onvoiceschanged` vuelve a dibujar cuando el resultado
  cambia, y se abstiene si el usuario está escribiendo en un campo.
- **`comoInstalarVoz()`: instrucciones según el aparato.** Los avisos nombraban
  solo Android e iPhone. Se agregaron **Windows** (Configuración → Hora e
  idioma → Agregar idioma → Norsk bokmål, marcando «Voz», y cerrar el navegador
  por completo) y **macOS**, más un texto genérico. Los tres avisos de audio
  apagado —inicio, ejercicio de escucha y perfil— dicen ahora cómo arreglarlo.
- **4 pruebas nuevas** (200): que la búsqueda acepte las tres etiquetas del
  noruego (`nb`, `no`, `nn`), que la pantalla se redibuje al llegar las voces
  sin borrar lo escrito, que estén los cuatro sistemas y que ningún aviso quede
  sin salida.

## Sesión 31-ago-2026 (noche) — La guía hacía copiar una dirección que no era

Segunda vuelta del mismo problema, en la prueba real.

- **Se quitó toda dirección de ejemplo** de la guía y del bot. La guía traía
  `http://192.168.1.15:8000/...` como muestra, con la advertencia de no
  copiarla; se copió igual (la máquina real era `172.17.80.25`). Antes había
  pasado lo mismo con `LA-IP-DE-ARRIBA` y con `ESE-NUMERO`. La conclusión: una
  dirección impresa como ejemplo termina escrita en el navegador, así que no
  puede haber ninguna — la instrucción ahora es «copie **la línea que muestra
  su ventana**».
- **El bot explica el `ERR_CONNECTION_TIMED_OUT`.** Ese error no es del enlace
  sino de la red: firewall de Windows (con el `New-NetFirewallRule` listo para
  pegar), celular en otra red, o wifi y cable separados en el hospital.
- **Salida por el túnel.** Como `app/` monta `/static` desde el disco, el
  servidor que ya se ve desde fuera del hospital sirve también la aplicación:
  la dirección de siempre con `/static/noruego/index.html` al final. Sin
  firewall, sin wifi y sin reiniciar nada.
- **3 pruebas nuevas** (196): un `re` rechaza cualquier `http://n.n.n.n:puerto/`
  en la guía y en el bot, y se exige que el bot traiga la regla de firewall.

## Sesión 31-ago-2026 (tarde) — El bot de noruego no mostraba la dirección

Arreglo de la primera prueba real en el PC de cartera.

- **`tools/NORUEGO.cmd` imprimía la ayuda de `ipconfig` en vez de la IP.** La
  línea era `ipconfig ^| findstr /C:"IPv4"`: el `^|` solo va escapado dentro de
  un `for /f`; suelto, el `|` le llega a `ipconfig` como argumento. Como no
  salía la dirección, el bot igual mostraba el texto de relleno
  `http://LA-IP-DE-ARRIBA:8000/...` — y eso fue literalmente lo que se escribió
  en Chrome (`DNS_PROBE_FINISHED_NXDOMAIN`).
- **Nuevo `noruego/red.py` + `python -m noruego direccion`.** La IP se averigua
  abriendo un socket UDP hacia `8.8.8.8` sin enviar ningún byte (en UDP,
  `connect()` solo fija la ruta local): funciona sin internet, no genera tráfico
  y no depende del idioma de Windows ni de cuántos adaptadores tenga el equipo.
  El comando imprime el **enlace completo**, listo para copiar; sin red no
  imprime nada y devuelve 1.
- **El bot y `exportar` ya no muestran texto de relleno** cuando pueden mostrar
  el enlace real. El relleno que queda (`ESE-NUMERO`) solo aparece si de verdad
  no hubo IP, y va acompañado de cómo conseguirla.
- **Se explica dónde está «Agregar a la pantalla de inicio»:** Android (Chrome)
  en los tres puntos, iPhone (Safari) en el botón de compartir. En el computador
  no aplica — se abre `static\noruego\index.html` con doble clic. Se buscó esa
  opción en el Chrome de escritorio, donde no existe con ese nombre.
- **26 pruebas nuevas** (193 en `tests/test_noruego`): `test_red.py` comprueba
  que no salga tráfico, que sin red no reviente y que nunca se ofrezca una IP de
  loopback; `test_bots_windows.py` rechaza el `^|` fuera de un `for /f`, el
  texto de relleno viejo, los finales de línea LF y los subcomandos inexistentes.

## Sesión 31-ago-2026 — Curso de noruego (`noruego/`)

Aplicación web para aprender noruego bokmål desde cero, para hispanohablantes,
instalable en el celular (PWA) y funcional sin internet. Módulo independiente:
no importa nada de `app/` ni de `tools/` y solo usa la librería estándar.

### Contenido
- **423 elementos de léxico** en JSON: 133 sustantivos con género y las cuatro
  formas, 69 verbos con sus cuatro tiempos y su grupo, 40 adjetivos con las tres
  formas, 85 frases de uso real, 42 números, 13 guías de pronunciación, 29
  reglas de gramática (con ejemplo, error típico y comparación con el español) y
  12 conversaciones de situaciones reales.
- **18 módulos y 73 lecciones**, de nivel cero a B2, con la estructura definida
  hasta C2.

### Motor
- Los ejercicios **se generan a partir de los datos**, no se escriben a mano:
  de «bil es masculino y su definido es bilen» salen solos el ejercicio de
  género, el de forma, el de traducción, el de escucha y el de parejas. 875
  ejercicios por variante, 3 variantes por lección (2.625 en total).
- 15 tipos de ejercicio: opción, completar, ordenar, traducir en las dos
  direcciones, escuchar y elegir, escuchar y escribir, parejas, conjugar,
  género, forma nominal, encontrar el error, diálogo, lectura y pronunciación.

### Aplicación
- Mobile first: barra inferior, botones de 52 px, zona segura del iPhone,
  vibración, atajos de teclado.
- Repetición espaciada que decide sola qué repasar, con detección de palabras
  difíciles.
- XP, niveles de jugador, racha, objetivo diario, corazones, estrellas, 10
  logros y desbloqueo progresivo.
- Audio con la voz del propio dispositivo (`nb-NO`). **Si no hay voz noruega,
  muestra el texto y lo dice**, en vez de leer con acento español.
- Diccionario buscable, gramática explicada, conversaciones, estadísticas con
  calendario de constancia, copia de seguridad y panel para agregar contenido
  sin tocar código.
- PWA: manifest, service worker con caché e iconos generados.

### Correcciones encontradas durante el desarrollo
- `fuentes=("frases")` era una cadena, no una tupla: al recorrerla daba letras
  sueltas y dejaba lecciones sin material.
- El tipo de ejercicio rotaba con los ejercicios ya generados, así que un tipo
  imposible de construir con ese material **bloqueaba el ciclo entero**: 27
  lecciones quedaban casi vacías. Ahora rota con los intentos.
- Sin voz noruega instalada, los ejercicios de escucha eran imposibles de
  responder. Ahora muestran el texto como respaldo.

### Pruebas
167 pruebas en `tests/test_noruego/`; `ruff` limpio. Recorrido completo
verificado en Chromium emulando un celular: alta de usuario, tres lecciones
completas, XP, logros, diccionario, gramática, conversaciones, perfil, panel de
contenido y **persistencia tras recargar**, sin errores de JavaScript y sin
desbordamiento horizontal.

## Sesión 26-ago-2026 (cierre 7) — un solo vocabulario de color

Idea #12, decidida por el área. **Corrige lo que la propuesta afirmaba:** que
`sinac-ds.css` «se carga y nadie usa» y que no había defecto visible. Al medir,
las dos afirmaciones resultaron falsas.

- **16 reglas de color de ese archivo aplican hoy**, todas sobre `#p-analizar`:
  `.res-dictamen-body`, `.pa-cite.verified`, `.pa-cite.unverified`,
  `.sidebar input/select/textarea`, `.sidebar .btn-primary`, `.res-actions button`.
- Las paletas eran **colores distintos**, no alias: `--sds-success` `#16a34a`
  contra `--c-green` `#2E7D32` (distancia RGB 51); `--sds-amber` `#d97706`
  contra `--c-amber` `#E65100` (41); `--sds-rose` `#e11d48` contra `--c-red`
  `#C62828` (43).

**Arreglo: 13 líneas, no 2.072.** Los trece tokens de color de `--sds-*` pasan
a `var(--sinac-*, #hex)`. El nombre que se escribe sigue siendo `--sds-*` —como
pide CLAUDE.md— y el valor que devuelve es el corporativo. Ningún uso se tocó.

**El fallback es obligatorio:** de las 6 páginas que cargan el archivo, 4 no
definen `--sinac-*` (preauditoria, importar-masiva, presentacion-ia,
terapia-fisica). Un alias sin fallback las dejaría con `var()` vacío → elemento
transparente. El fallback es el hex corporativo, no el viejo, para unificarlas
también.

**Pruebas:** `test_un_solo_vocabulario_de_color.py`, 8 casos — ningún token de
color se declara solo, ninguno queda sin fallback, ningún fallback conserva el
hex viejo, y un guardia de ≥10 tokens para que no pase por vacía. 262 en
`tests/test_frontend`.



## Sesión 26-ago-2026 (cierre 6) — la ruta de «Mi día» pisaba una que ya existía

Defecto que entró con el PR #506 y lo cazó el CI.

`GET /mi-dia` ya existía en `health.py` (resumen personal del gestor: tareas,
saludo, alertas). El router del tablero nuevo registró la misma ruta y, como se
incluye antes que el de health, FastAPI se quedó con la nueva y la vieja quedó
muerta en silencio — el modo de falla de «Salud Total».

- El tablero se muda a `GET /mi-dia/tablero`; la pantalla llama la nueva.
- `tests/test_api/test_ninguna_ruta_pisa_a_otra.py`: recorre `app.routes` y
  falla si dos comparten (método, camino), nombrándolas. Más un guardia que
  exige >100 rutas para que la prueba no pase por estar vacía.

Ninguna pantalla del portal consumía la ruta vieja, así que no se rompió nada
de cara al auditor. `tests/test_api/`: 2.783 en verde.



## Sesión 26-ago-2026 (cierre 5) — las once ideas para el motor

Se implementaron once de las doce ideas propuestas. La #12 (unificar los dos
vocabularios de color) queda sin hacer: son 2.072 cambios sobre algo que
funciona y sin defecto visible; está escrita en la bitácora para constancia y
solo se hace si el área lo pide.

**Antes de radicar**

- **No radicar sin el soporte de la causal.** `catalogo_glosas.py` gana el mapa
  `SOPORTE_QUE_PIDE_LA_CAUSAL` y `soportes_que_pide(codigo)`; el dictamen avisa
  cuando falta.
- **`agente_auditor_eps()`** en `multi_agente.py`: seis flancos sacados de
  fallas reales de agosto. Se dispara **cuando `citation_verifier` no encuentra
  nada** — el caso que quemó esta semana. Lee `verif_citas` (la revisión que sí
  llevó evidencia) en vez de volver a revisar; volver a revisar ahí sería sin
  evidencia y un folio inventado pasaría de largo. Tres pruebas fijan ese
  cableado.
- **El sello dice contra qué se verificó** — `_estado_del_corpus()`.
- **`_cups_desde_dgh()`**: cuando el texto no trae CUPS, se lee el que DGH ya
  registró para esa factura en `ConceptoRecord`.

**Aprendizaje**

- Las plantillas gold se escogen por `valor_recuperado` y no por `usos`
  (tres sitios de selección en `plantillas_gold.py`).
- `_notas_de_la_promocion()` guarda con la plantilla lo que el gestor contestó
  a «¿cuál argumento la levantó?». Si no contestó, no se inventa nada.

**Pantallas nuevas**

- `app/services/plata_recuperada.py` + `GET /dashboard-ejecutivo/plata-recuperada`
  + panel `p-plata`. Una sola consulta para todo el periodo. Lo que no tiene
  dato va a `sin_dato` y sale avisado en pantalla; no se rellena con supuestos.
- `app/services/mi_dia.py` + `GET /mi-dia` + panel `p-mi-dia`. Tres columnas,
  cada glosa en una sola. **`dias_restantes` vale 0 por defecto**, así que un 0
  sin `fecha_vencimiento` es ambiguo entre «vencida» y «nadie la calculó»: se
  devuelve `None` y esa glosa va al final, no al principio.

**Pruebas:** 87 nuevas en cinco archivos. `tests/test_services` +
`tests/test_api`: 6.601 en verde. `tests/test_frontend`: 264 en verde — la
prueba de tokens fantasma atajó cuatro colores inexistentes en la pantalla
nueva antes del commit.



## Sesión 26-ago-2026 (cierre 4) — el orden del folio de la factura, y sin índice

Tres cosas que pidió el área al revisar el resultado:

**1. El folio de la FACTURA no lleva índice.** Solo el clínico. Ya está.

**2. El detallado tiene que ir de SEGUNDO, y quedaba de tercero.** El
`..._FACTURA.pdf` que viene con el XML trae la factura y la representación
gráfica **pegadas**; si el detallado llega aparte y solo se le pone detrás,
queda después de las dos. Ahora `partes_de_la_factura()` mira página por página
qué es cada pedazo y el bot **parte** el PDF para meter el detallado en la
mitad:

```
antes:  factura(1-4) → representación gráfica(5-10) → detallado
ahora:  factura(1-4) → detallado(5-8) → representación gráfica(9-14)
```

Si el PDF ya trae todo en orden —como la HUS311736, que trae los cuatro
renglones— **se deja entero**: partirlo y volverlo a pegar no aporta y sí puede
dañar algo.

**3. La basura visual.** `sanar_temporales()` barre ahora los `.tmp` que deja
una corrida caída, y el armado por pedazos limpia los suyos aunque falle.

Comprobado con los dos archivos reales del paquete. 170 pruebas en el archivo,
1784 en `tests/test_tools`.


## Sesión 26-ago-2026 (cierre 3) — el aviso decía un nombre que no existe

Armando el paquete completo (223 folios), CLAUDIA avisó de 11 archivos «que no
se reconocieron», listándolos como «3 OTROS.pdf», «4 OTROS.pdf»… Pero
`3 OTROS.pdf` SÍ se reconoce: ese es el nombre que el bot les acababa de poner.
El nombre de verdad —el único que le diría al auditor qué archivo es— ya no
estaba en el disco.

O sea: los 11 archivos que hay que revisar salían avisados con un nombre
inservible. Ahora el `Soporte` guarda con qué nombre llegó, y el aviso dice
«3 OTROS.pdf (llegó como «FACOSTE.pdf»)». El reporte CSV lleva además una
columna **LLEGO COMO**.

Es el mismo defecto de la pantalla que mostraba dos veces «2 HISTORIA
CLINICA.pdf»: el bot contaba lo que iba a hacer, no lo que hizo.

1778 pruebas en `tests/test_tools`.


## Sesión 26-ago-2026 (cierre 2) — el detallado convertido no se pierde de vista

Al ir a repartir los 317 detallados del paquete —que salen del bot hermano con
el número por todo nombre, `HUS388262.xlsx`— apareció que al pasarlos a PDF
quedaban como `HUS388262.pdf`, y **con ese nombre el bot ya no sabe qué son**:
en la corrida siguiente se iban a OTROS del folio CLÍNICO, cuando su sitio es el
renglón 2 del folio de la FACTURA. (Peor: `HUS<num>.pdf` es también el nombre
con que sale una nota crédito del CRRP, así que el nombre es genuinamente
ambiguo.)

Ahora la conversión los deja como `HUS388262 DETALLADO.pdf`. Si el nombre ya
dice qué es, no se le agrega nada.

Comprobado de punta a punta con un detallado real del paquete: se convierte,
entra al folio de la factura como «2 DETALLADO.pdf», la carátula dice
«2.DETALLADO → 13», y la segunda corrida deja exactamente lo mismo.

1775 pruebas en `tests/test_tools`.


## Sesión 26-ago-2026 (cierre) — la carátula del folio

El área mandó la carátula que necesita: un índice de una página que abre el
folio, con el renglón y la página donde empieza.

```
1.RESPUESTA A GLOSA ______________________________________  2
2.HISTORIA CLINICA _______________________________________ 70
3.AYUDAS DIAGNOSTICAS ___________________________________ 237
```

Una línea por **renglón**, no por archivo — que era lo que quería decir con
«en la carátula solo quedaría 1. RESPUESTA — 2. HISTORIA CLINICA». Las dos
historias clínicas son una sola línea y apunta a donde empieza la primera.

Lo que se cuidó, porque un índice que miente es peor que no tener índice:

- El número es la página **exacta** del folio ya armado, contando la carátula.
- Un soporte que NO entró (un PDF dañado) no figura: si figurara, todas las
  páginas de abajo quedarían corridas. Por eso la carátula se arma con las
  páginas que de verdad escribió `unir_pdfs`, no con las que se esperaban.
- Sin `reportlab` el folio se arma igual, sin índice, y se avisa.
- No quedan archivos temporales en la carpeta.

`unir_pdfs` acepta un parámetro `detalle` opcional que devuelve cuántas páginas
puso cada archivo; los demás bots que lo usan no cambian. `UNIR_PDFS.cmd`
regenerado (su prueba del motor embebido volvió a detectar el desfase).

`--sin-caratula` la desactiva. 158 pruebas en el archivo, 1772 en `tests/test_tools`.


## Sesión 26-ago-2026 (piloto) — el número es del renglón, y las copias de Windows en su sitio

Dos cosas que salieron al correr el piloto sobre la HUS311371 de CAROLINA, que
trae `HC.pdf` y `HC (2).pdf`:

**1. El número es del RENGLÓN, no del archivo.** El área lo dijo claro: dos
historias clínicas son las dos el renglón 2, y en la carátula del folio va un
solo «2. HISTORIA CLINICA». Antes salían «2 HISTORIA CLINICA.pdf» y
«3 HISTORIA CLINICA.pdf», que en la carátula se leían como dos renglones
distintos. Ahora la segunda queda «2 HISTORIA CLINICA (2).pdf».

**2. El original quedaba de último.** Windows nombra los repetidos `HC.pdf`,
`HC (2).pdf`, `HC (3).pdf`, pero con el orden natural a secas «HC (2)» va antes
que «HC.» —el espacio pesa menos que el punto— así que el orden salía
`HC (2) → HC (3) → HC (10) → HC`. `clave_orden()` lo pone en su sitio.

Las dos comprobadas con el caso real y estables en tres corridas seguidas.

**3. La pantalla mentía sobre el nombre repetido.** En el piloto real, las dos
historias clínicas salían listadas las dos como «2 HISTORIA CLINICA.pdf», como
si la segunda hubiera pisado a la primera. En disco quedaban bien —
«2 HISTORIA CLINICA.pdf» y «2 HISTORIA CLINICA (2).pdf»— porque el «(2)» lo
resolvía `nombre_libre` al momento de renombrar, después de imprimir el
listado. Ahora `nombres_en_orden()` calcula el nombre definitivo ANTES, así que
la pantalla y el reporte muestran exactamente lo que va a quedar en la carpeta.

153 pruebas en el archivo.


## Sesión 26-ago-2026 (tarde) — la revisión adversarial: pérdida de datos y cuatro defectos más

Se pasó el bot de folios por una revisión con cinco lentes distintas —colisiones
de nombres, idempotencia, pérdida de archivos, Windows/SMB, contratos—, y cada
hallazgo se puso a dos escépticos que tenían que reproducirlo contra el código
real. Salieron 31; estos son los que se confirmaron y se arreglaron.

**1. PÉRDIDA DE DATOS: el folio pisaba la epicrisis de verdad.** El folio se
llama igual que el archivo del que sale (`..._EPICRIS.pdf`). Para distinguirlos
el bot miraba si la carpeta traía archivos numerados; en una carpeta donde el
auditor ya había numerado algo a mano —que es lo que pide la hoja del área— la
epicrisis DE VERDAD se tomaba por folio viejo, se dejaba fuera del folio y se
pisaba. Comprobado: epicrisis de 5 páginas → tras UNA corrida, esa ruta tenía un
folio de 4 páginas sin la epicrisis y la epicrisis no existía. Sin respaldo.

La heurística se reemplaza por un hecho: el bot **firma** los PDF que escribe
(`/Producer`) y reconoce los suyos por esa firma. Lo que no la lleva es un
soporte y se trata como tal — que era lo correcto: la epicrisis entra al folio y
se renombra, y con eso queda libre el nombre. Se quitan `_RE_NUMERADO`,
`_grupos_ya_numerados` y `folios_dudosos`. Candado extra: si en la ruta del
folio hay algo sin firma, no se arma ese folio y se avisa.

**2. Las notas crédito no se reconocían con el nombre del hospital.** Vienen
como `NC_263272_HUS352904.pdf`; caían en OTROS del folio CLÍNICO y el reporte
seguía diciendo que faltaban. Se agregan `NC` y `NOTA ELECTRONICA`, comprobando
que no disparan falsos positivos (`HC`, `RESONANCIA`, `INCAPACIDAD`, `NTE-C`).

**3. El folio cambiaba de orden entre corridas.** El nombre que escribe el
propio bot, `3 HISTORIA CLINICA - TERAPIAS.pdf`, se releía como HISTORIA a
secas, porque «HISTORIA CLINICA» es más larga que «TERAPIAS» y ganaba. El
soporte cambiaba de grupo y se renumeraba. Ahora HISTORIA CLINICA es un grupo
**genérico**: cualquier grupo más preciso le gana. Igual para curaciones,
evoluciones y procedimientos.

**4. El detallado del bot hermano no se reconocía.**
`dividir_detallado_por_factura.py` lo deja como `HUS352904.xlsx`, el número y
nada más: nunca se pasaba a PDF y no entraba al folio.

**5. Un soporte dañado desaparecía del folio en silencio.** Se omitía, el folio
se armaba sin él y en pantalla decía «armado». Ahora sale avisado: «OJO, N
soporte(s) NO entraron al folio».

Y dos candados más de robustez: una copia fallida de la factura, o un archivo
bloqueado al renombrar con `--renombrar`, ya no tumban las otras 323 facturas.

### Y seis más, de la misma revisión

**6. Una FECHA pasaba por NIT.** `prefijo_del_nombre` solo pedía «números al
principio y esta factura después», así que `20240913_HUS352904 EVOLUCION.pdf`
daba NIT `20240913` y el folio salía llamándose `20240913_HUS352904_EPICRIS.pdf`.
Ahora se exige el nombre completo del ADRES (`<NIT>_<FACTURA>_<TIPO>`) y nada
más; un número de ingreso o una fecha ya no cuelan.

**7. `--mapa-nombres` dependía del orden del JSON.** Con
`{"TAC": …, "TAC DE TORAX": …}` ganaba la primera línea escrita, no la palabra
más larga. Ahora gana la más larga, como en el diccionario de siempre.

**8. El reporte abierto en Excel tumbaba la corrida.** En Windows el CSV no se
deja escribir si está abierto; el traceback llegaba **después** de armar todos
los folios. Ahora se avisa y el trabajo no se pierde.

**9. `--renombrar` dejaba a medias la carpeta.** Numeraba el folio clínico pero
no el de la factura, y el CSV prometía renglones que nadie armaba.

**10. Las banderas que no hacen nada sin `--folio`** (`--carpeta-facturas`,
`--prefijo`, `--convertir-detallado`) se ignoraban en silencio: el auditor creía
que había traído las facturas. Ahora avisan.

**11. Los archivos que no son PDF desaparecían sin avisar.** Una epicrisis en
Word o una radiografía en JPG no entran al folio, pero tampoco pueden
esfumarse: salen listadas en pantalla y en el reporte. La basura de Windows
(`Thumbs.db`, `desktop.ini`) no se reporta.

### Y el último grupo: lo que deja una corrida que se cae a mitad

El renombrado va en dos vueltas —primero a un nombre de paso `~renombrando~…`,
porque el nombre que le toca a un archivo puede ser el que todavía tiene otro—.
Si la corrida se caía en medio, eso dejaba dos destrozos:

**12. Un `~renombrando~HC.pdf` colgado se PERDÍA en la corrida siguiente.** El
nombre de paso se armaba con `ruta.with_name(...)` a secas, así que al renombrar
`HC.pdf` se pisaba el huérfano. Comprobado: un huérfano de 7 páginas
desaparecía y la carpeta quedaba con un `~renombrando~~renombrando~HC.pdf` y sin
folio. Ahora el nombre de paso se pide libre (`nombre_libre`), y
`sanar_temporales()` le devuelve su nombre a lo que quedó colgado antes de
empezar: el huérfano de 7 páginas se recupera y entra al folio.

**13. No había vuelta atrás.** Si la segunda vuelta fallaba, los archivos
quedaban como `~renombrando~…` para siempre y la factura sin folio. Ahora se
deshace: cada uno vuelve al nombre que tenía, y la corrida siguiente arma el
folio sin ayuda.

**14. `--renombrar` borraba el NIT sin decirlo.** Al numerar, el nombre que lo
traía (`680010079201_HUS######_EPICRIS.pdf`) desaparece, y después no hay de
dónde sacarlo: los folios salían como `HUS######_EPICRIS.pdf`. Ahora avisa con
el NIT que encontró, para pasarlo con `--prefijo`.

En simulación los huérfanos no entran al folio pero sí salen en el reporte.

149 pruebas en el archivo. Se comprobó además que quedaron cerrados los otros
dos confirmados: `--renombrar` y después `--folio` ya no destruye el PDF de la
factura (19 páginas intactas), y una carpeta con punto y espacios
(`HUS379477_PEND. CARTA CORONEL`) da el mismo folio en tres corridas seguidas.


## Sesión 26-ago-2026 — los DOS folios de cada factura (`--folio`)

El área aclaró cómo es el folio completo, y son **dos PDF por factura**, no uno:

- **`<NIT>_<FACTURA>_EPICRIS.pdf`** — el nombre que queda **después** de unir
  los soportes numerados (`1 RESPUESTA A GLOSA`, `2 EPICRISIS`,
  `3 HISTORIA CLINICA`, `4 AYUDAS DIAGNOSTICAS`, `5 OTROS`).
- **`<NIT>_<FACTURA>_FACTURA.pdf`** — la factura sí entra al folio, con su
  propio orden adentro: **1 FACTURA · 2 DETALLADO (el Excel pasado a PDF) ·
  3 REPRESENTACIÓN GRÁFICA DIAN · 4 NOTAS CRÉDITO**.

Lo que se agregó a `unir_soportes_adres.py`:

- **`--folio`**: numera los soportes y arma los dos PDF. Numerar primero no es
  adorno — es lo que **deja libre el nombre del folio**, porque ese nombre es
  justo el que traían la epicrisis y la factura antes de renombrarlas.
- **Cuatro renglones nuevos** (`GRUPOS_FACTURA`) con sus palabras: FACTURA,
  DETALLADO, REPRESENTACIÓN GRÁFICA DIAN y NOTAS CRÉDITO. Los trece grupos
  clínicos quedaron igual.
- **`--carpeta-facturas`**: trae a cada carpeta su
  `680010079201_HUS######_FACTURA.pdf` desde `4.FACTURAS CON XML\XML`. No pisa
  la que ya estuviera.
- **`--convertir-detallado`**: pasa a PDF el detallado que esté en Excel,
  reusando el motor de `excel_a_pdf.py`. Si el equipo no tiene ni Excel ni
  LibreOffice, lo deja anotado y sigue.
- **`--prefijo`**: el NIT del nombre. **No se inventa**: sale del nombre de los
  propios archivos; esta opción solo llena las carpetas donde ninguno lo trae.
- **Las notas crédito quedan PENDIENTES a propósito** — todavía no las han
  sacado, así que no se cuentan como falta. Cuando lleguen, se dejan en la
  carpeta y se vuelve a correr: entran solas de cuartas.
- **La simulación muestra el folio como va a quedar de verdad**, con la factura
  y el detallado ya adentro, aunque todavía no los haya copiado ni convertido.

Un defecto que apareció en la prueba de tres corridas seguidas y quedó cerrado:
en una factura **sin epicrisis**, el `..._EPICRIS.pdf` de la primera corrida se
colaba como si fuera una epicrisis y en la segunda el folio crecía metido dentro
de sí mismo (10 → 13 páginas). Ahora el bot mira la carpeta, no el renglón: si
ya hay archivos numerados, lo que quede con el nombre original es el folio
viejo. El caso que no se puede distinguir (un `..._EPICRIS.pdf` suelto en una
carpeta ya armada) no se adivina: se avisa para que el auditor lo mire.

45 pruebas nuevas (104 en el archivo).

### Revisión posterior: dos defectos más, encontrados antes del cargue real

**1. Una factura bloqueada dejaba sin folio a las otras 323.** `aplicar_folios`
llamaba a `renombrar_lista` sin candado, al contrario de `unir()`. Un PDF
abierto en Acrobat —o el share cayéndose un momento— tumbaba la corrida entera.
Ahora esa factura se salta con `ERROR` y su motivo, y las demás siguen.

**2. El folio de la factura habría llevado el detallado dos veces.** Al abrir el
`680010079201_HUS311736_FACTURA.pdf` que viene con el XML, resultó **no ser solo
la factura**: son 19 páginas con los cuatro renglones ya pegados —factura con
CUFE (1–7), detallado (8–9), representación gráfica DIAN (10–18) y nota crédito
(19)—. El bot le habría agregado encima el detallado del Excel. Ahora
`renglones_que_trae()` mira dentro del PDF antes de tocarlo: lo que ya viene
pegado no se duplica ni se cuenta como faltante, y se avisa en pantalla.
Comprobado sobre una sola factura; en las que vengan solo con la factura, el bot
arma el folio con las partes sin configurar nada.

Con esto: 111 pruebas en el archivo.


## Sesión 25-ago-2026 (noche, 2) — `--renombrar`: el folio como lo nombra el área

El PDF unido de la HUS352904 no se parecía a lo que pide la hoja del área. Al
mirarlo con el auditor salieron dos cosas distintas:

- **La hoja no pide un PDF pegado, pide los soportes numerados dentro del
  folio**: `1 RESPUESTA A GLOSA.pdf`, `2 HISTORIA CLINICA.pdf`, `3 OTRO.pdf`.
  Eso es `--renombrar`, nuevo. `nombre_numerado()` arma el nombre y
  `renombrar_en_orden()` lo aplica **en dos vueltas** —primero a un nombre
  temporal—: el nombre que le toca a un archivo puede ser el que todavía tiene
  otro, y renombrando de una uno pisaría al otro. Idempotente.
- **El contenido era corto porque la carpeta solo tenía dos soportes.** No es
  defecto del bot: faltan la epicrisis y los demás.

La unión en un solo PDF sigue como estaba, por defecto. Se pueden usar las dos.

7 pruebas nuevas (59 en el archivo), incluida la del renombrado que se pisaría a
sí mismo y la de correrlo dos veces.


## Sesión 25-ago-2026 (noche) — repartir la respuesta a glosa por carpeta de factura

`organizar_soportes_por_factura.py`:

- **`carpetas_por_factura()`**: mapea el número de factura a la carpeta que ya
  existe, aunque traiga una nota detrás (`HUS379477_PEND. CARTA CORONEL`,
  `HUS367368 ACEPTADO`, `HUS378523_MAOS`). Antes se buscaba `carpeta / factura`
  literal, así que a esas no las encontraba y **creaba una carpeta gemela
  vacía**. Con dos carpetas para la misma factura gana la primera alfabética,
  para que el resultado no dependa del orden del sistema de archivos.
- **`--solo-carpetas-existentes`**: mueve solo lo que ya tiene carpeta, sin
  crear ninguna. Hace falta al repartir un lote que abarca varios gestores: las
  324 respuestas se sueltan en cada carpeta y solo caen las que corresponden;
  las demás quedan listadas con el estado `SIN CARPETA PARA ESA FACTURA`.

`unir_soportes_adres.py`: `_factura_de_carpeta` pasa a delegar en
`factura_del_nombre` — la regla de cómo se saca el número de un nombre queda en
un solo sitio.

8 pruebas nuevas (54 en el archivo), y ensayo de punta a punta con el ZIP real.


## Sesión 25-ago-2026 — `unir_soportes_adres.py` + arreglo del desglose huérfano

### `unir_soportes_adres.py` (nuevo)
Une los soportes de cada carpeta de factura en un solo `<FACTURA>_SOPORTES.pdf`,
en el orden de la lista del área (13 grupos, de RESPUESTA A GLOSA a OTROS). El
detallado queda fuera del PDF: la lista lo pide en Excel.

Clasifica por nombre de archivo con dos reglas que evitan los falsos positivos:
gana la **palabra más larga** («NOTAS DE ENFERMERIA» sobre «NOTAS»), y las
abreviaturas cortas se buscan como **palabra completa** (`INS` no casa dentro de
`INSTITUCIONAL`). Lo no reconocido va a OTROS y sale marcado en el reporte.
`--mapa-nombres` agrega palabras sin tocar el código.

Reusa `unir_pdfs` / `clave_natural` de `unir_pdfs_carpetas.py` — la unión y el
orden natural ya estaban resueltos; aquí solo se agrega la capa de orden.

Simula por defecto (`--aplicar` para escribir), se excluye a sí mismo de la
entrada (idempotente) y un PDF ilegible se omite sin tumbar el lote. Avisa las
facturas sin RESPUESTA A GLOSA o sin EPICRISIS.

Incluye `UNIR_SOPORTES_ADRES.cmd` (CRLF), guía en español y 42 pruebas.

### `ajustar_detallado_glosas.py` — desglose huérfano
**Defecto:** cada ítem se decidía por separado. Cuando la entidad aprobaba el
procedimiento (CUPS, que no aparece en el reporte del ADRES porque este glosa
con códigos SOAT) pero seguía glosando sus componentes, el principal se quitaba
y los componentes quedaban huérfanos: el detallado mostraba honorarios y
derechos de sala sin decir de qué cirugía eran. El auditor tuvo que rehacer a
mano la HUS383283.

**Arreglo:** una pasada previa marca los principales cuyo desglose sobrevive y
los conserva con la acción nueva `ACCION_ENCABEZADO` — se ven, pero no suman al
subtotal, porque su valor ya está en los renglones de desglose. La condición de
"no suma" de los hijos se corrigió en consecuencia (`id(padre) not in
rescatados`), para que el valor no se pierda ni se cuente dos veces.

2 pruebas nuevas: el principal se queda como encabezado y no suma; y si su
desglose también se fue, se va como siempre.

## Sesión 25-ago-2026 (noche) — 2.ª auditoría del lote: el Decreto 4747 tenía tres artículos inventados

Un segundo auditor revisó las mismas 117 respuestas con otro método: contrastó
las citas contra el texto publicado de las leyes y cruzó, código por código, el
motivo real del pagador contra lo contestado. Encontró lo que la primera pasada
no vio.

### 1. `DECRETO 4747 DE 2007` — corpus corregido contra la fuente oficial

Las 28 respuestas de ratificación (100 %) citaban el **Art. 20** como el del
trámite de glosas. Verificado contra el texto de MinSalud: el Art. 20 es el del
**RIPS**; el trámite está en el **23**. Y de los tres artículos que el corpus
tenía cargados, **los tres** estaban mal, con epígrafe y texto fabricados:

| Corpus decía | Texto oficial |
|---|---|
| Art. 11 — «Atención de urgencias» | «Verificación de derechos de los usuarios» |
| Art. 20 — «Trámite de glosas — conciliación» | «Registro Individual de Prestaciones — RIPS» |
| Art. 21 — «Pago durante trámite de glosas» | «Soportes de las facturas» |

**El defecto estructural, no la cita:** `citation_verifier` contrasta contra ese
mismo corpus, así que la cita fabricada **se autocertificaba** — el dictamen
salía «citas verificadas · 0 hallazgos» con una norma que dice otra cosa. Misma
clase de defecto que la jurisprudencia del 24-08.

Se cargaron los cinco artículos con texto literal (11, 20, 21, 22, 23) y se
repasaron las **17 citas** al decreto repartidas por `glosa_ia_prompts`,
`multi_agente`, `conciliador_ia`, `validador_dictamen`, `memoria_gestor`,
`contexto_contractual_enriquecido`, `salud_total_service` y `routers/glosas`.

`TEXTO_RATIFICADA` ahora cita el Art. 23. `_corregir_articulo_mal_citado` es la
malla: corrige «Art. 20 del Decreto 4747» → 23 **solo** cuando el contexto habla
de glosas (el Art. 20 existe y citarlo para RIPS es correcto).

Efecto colateral bueno: el Art. 11 real —verificación de derechos— es
exactamente el fundamento de las glosas FA1605/FA1606. Estaba inutilizable
porque el corpus lo tenía mal.

### 2. Cita literal fabricada — se detecta sola al corregir el corpus

Varias respuestas AU0202 atribuían al Art. 11 un texto entrecomillado sobre
urgencias sin autorización previa. No está en el decreto. Corregido el corpus,
`verificar_citas` la marca `CITA_LITERAL_FALSA` (ALTA) y
`_descomillar_citas_falsas` la desactiva. No hizo falta regla nueva.

### 3. `_avisar_si_contesta_la_forma` — responder la glosa que es

De 79 códigos, **74 abordaban el motivo real**. Los 5 que no ($3.564.600)
fallaban igual: contestaban validez de factura electrónica ante la DIAN cuando
la glosa era de fondo.

- **FA1606** (3, $2.571.800) — el pagador alega régimen del afiliado distinto al
  del contrato. Lo resuelve la BDUA a la fecha de atención, no la DIAN.
- **FA0703** (2, $992.800) — «insumo no facturable» con código del ítem. Lo
  resuelve el anexo del paquete.

`catalogo_glosas` gana la defensa central de ambos códigos (patrón ya usado en
FA0202/FA0802). La red no reescribe el argumento: añade **«⚠ REVISAR ANTES DE
RADICAR»** cuando el dictamen argumenta forma y no entró en el fondo. No dispara
si el texto ya menciona BDUA/régimen/verificación de derechos (FA1606) o
paquete/anexo (FA0703), ni en códigos que sí son de forma.

### 4. Dos defectos de forma

- **Etiqueta contradictoria** (HUS0000538289): «Contrato: SIN CONTRATO PACTADO»
  junto a «Tarifa **pactada**: SOAT PLENO». Sin contrato no hay pacto — el SOAT
  pleno es lo que se aplica *a falta* de pacto. La etiqueta pasa a «Tarifa
  aplicada» cuando no hay contrato.
- **Pseudo-norma en el cuerpo del argumento**:
  `_neutralizar_art_168_fuera_de_contexto` sustituía la cita inaplicable por «LA
  NORMATIVA DE CONTINUIDAD Y COBERTURA DEL SISTEMA GENERAL DE SALUD», que se lee
  como el título de un documento inexistente. Ahora: «las reglas generales del
  Sistema General de Seguridad Social en Salud». `_solo_normas_citables` sigue
  de malla para la lista de FUNDAMENTO.

### Nota de despliegue

El filtro `_solo_normas_citables` (24-08) **sí estaba** en el commit desplegado
y aun así la pseudo-norma salió en el FUNDAMENTO de las 117: se generaron antes
de reiniciar el motor. Lo corregido no tiene efecto hasta el reinicio.

### Lo que no se tocó

Las 21 respuestas de ratificación usan una plantilla que no entra en el motivo
concreto de la ratificación (0/44 códigos). El texto lo pidió el área y se
sostiene jurídicamente; cambiarlo es decisión del auditor. Queda anotado en
BITACORA con la mejora disponible: el Art. 23 prohíbe glosas nuevas sobre la
misma factura salvo por hechos nuevos.

### Pruebas

`test_decreto_4747_articulos_reales.py` (16) ·
`test_contestar_el_tema_de_la_glosa.py` (13). Reescritas para fijar la intención
en vez de la redacción: `test_ronda13_fixes` (pseudo-norma) y `test_multi_agente`
(anclaje de urgencias — tercer anclaje equivocado para lo mismo).

## Sesión 25-ago-2026 (tarde) — Auditoría de las 117 respuestas del primer lote productivo

Se pasaron por el revisor de citas las 117 respuestas que el motor generó con
el archivo de recepción del día. Cinco defectos, cinco correcciones con prueba.

### 1. CUPS que el motor nunca tuvo a la vista (12 respuestas)
El archivo de recepción **no trae columna de CUPS**. La IA rellenaba el hueco
con un número de seis cifras. La prueba de que era invento: el mismo `734101`
nombró «radiografía de maxilar inferior» en un dictamen y «radiografía de
pierna» en otro; el `730102`, «urgencias adultos» e «internación adultos
complejidad alta».

`_neutralizar_cups_sin_respaldo(texto, evidencia)` — misma regla que ya se
aplicaba a los folios: si el código no está en lo que la IA leyó, no lo leyó.
Se exige **además** que no se pueda verificar en el catálogo, para que un
código real nunca se borre (lección de la Res. 2641 de 2024). Se retira solo el
número; la descripción del servicio se conserva.

### 2. El texto fijo del Dispensario declaraba vigente un contrato vencido (14)
`TEXTO_DMBUG_TARIFAS` afirmaba «SE ENCUENTRA SUSCRITO Y **VIGENTE** EL CONTRATO
440-DIGSA/DMBUG-2025 … CON PLAZO HASTA **30/07/2026**» — el 25 de agosto, 26
días después del plazo. Frase autocontradictoria en un documento radicado.

- El texto ancla la vigencia **a la fecha de prestación**, que es lo verificable
  y además defiende mejor.
- `_dmbug_cubierto_por_el_contrato(fecha_hecho)` lee el plazo de
  `malla_contractual` (fuente única) y, si el servicio quedó fuera, el texto
  canónico no se usa: la glosa va por el camino normal. Sin fecha se deja pasar
  — una glosa siempre es de un servicio pasado.

### 3. `LEY 1164 DE 2007` cargada al corpus (3 respuestas)
El revisor la marcaba `NORMA_INEXISTENTE` (ALTA). Existe: Talento Humano en
Salud, 3 de octubre de 2007. Se verificó contra el texto oficial de MinSalud y
se cargaron sus artículos 26 («el acto profesional se caracteriza por la
autonomía profesional») y 35.

### 4. `_corregir_anio_de_norma` — la norma es real, el año no (2 respuestas)
«Resolución 3100 de 2020» → es de **2019**. La resolución ya estaba en el
corpus con el año correcto; faltaba corregir la cita. Tabla estrecha: solo
pares número+año verificados contra la fuente.

### 5. `_reponer_preposicion_comida` — el «de» que se come el modelo (11)
«levantamiento **la** glosa», «artículo 17 **la** ley», y —dentro de comillas
que citan textualmente el Art. 17— «los profesionales **la** salud». Se probó
cada patrón del módulo contra la frase correcta: ninguna malla la toca, lo
escribe así el modelo. Lista de tres fórmulas verificadas, no un corrector
gramatical general.

### Además
- **Amenazas al pagador**: la regla 8.decies las prohibía por instrucción y el
  modelo amenazaba igual (GL-118/GL-119). Ahora hay malla. Lo legítimo se
  conserva: Art. 126 Ley 1438 (SuperSalud), Art. 57 (levantamiento por falta de
  respuesta) y negarle a la EPS la facultad sancionatoria.
- **`_completar_norma_derogada`** (Res. 2275/2023, 21 respuestas): no se
  reemplaza — para un servicio anterior al 14-05-2026 esa ES la norma
  aplicable. Se **completa** con la regla de fecha. `citation_verifier` deja de
  avisar cuando el documento ya nombra la sucesora
  (`_norma_sucesora_ya_nombrada`).

### Resultado sobre el mismo lote de 117

| Hallazgo | Antes | Después |
|---|---|---|
| `CUPS_INEXISTENTE` (ALTA) | 7 | **0** |
| `CODIGO_NO_ES_CUPS` (ALTA) | 5 | **0** |
| `NORMA_INEXISTENTE` (ALTA) | 2 | **0** |
| `NORMA_DEROGADA` (MEDIA) | 21 | **2** |
| Preposición comida | 11 | **0** |

Pruebas nuevas: `test_cups_inventado_no_sale_en_el_dictamen.py` (17),
`test_dmbug_no_dice_vigente_lo_vencido.py` (8),
`test_el_dictamen_no_amenaza_al_pagador.py` (13),
`test_normas_reales_que_faltaban.py` (14),
`test_el_de_que_se_come_el_modelo.py` (11),
`test_norma_derogada_dice_desde_cuando.py` (14).

## Sesión 24-ago-2026 — `organizar_objeciones_adres.py`: cuadre contra el reporte del ADRES

### El defecto que corrige
El detalle del ADRES cuenta la misma plata varias veces, y la conversión la
sumaba tal cual: el paquete 31068 salía en **$1.032.239.679** contra los
**$646.908.552** que el ADRES reporta glosados. Cargado a DGH habría objetado
hasta tres veces el mismo dinero.

Dos fuentes de repetición, ambas del archivo del ADRES:
- Filas de causal de reclamación (2102, 2103…) con el valor **completo** de la
  reclamación, además del detalle por servicio.
- El mismo servicio (mismo código, cantidad y valores) repetido por cada causal.

### `--reporte-reclamaciones`
Lee el `ReporteReclamPAQUETE_*.xlsx` (encabezado en la 2ª fila: encima va la de
totales) y deja cada factura sumando **exactamente** su `Valor Glosado`:
1. `conciliar_factura` quita las filas que repiten el total de la reclamación.
2. Quita las repeticiones, mayor primero, **sin bajarse del valor reportado**.
3. `cuadrar_con_reporte` corre **al final**, sobre los valores ya topados por el
   guardián de DGH, y reparte el residuo desde el renglón mayor hacia abajo sin
   dejar valores negativos. También reescribe el `$<valor>` del `CRDOBSERV`.

Resultado 31068: **324/324 facturas cuadradas**, $646.908.553 (Δ $1 por redondeo
a pesos enteros), 169 renglones quitados, 65 facturas ajustadas.

### `--completar-servicios`
Ningún `SLNSERPRO` queda vacío: se usa el candidato del cruce y, si no hay,
`servicio_principal` (el servicio de más peso de la factura en DGH). No es
homologación — cada fila así queda en `REVISAR` con `CODIGO DE SERVICIO
ASIGNADO` y su procedencia. En el 31068: 1.856 vacíos → **0**, con 1.768 filas
marcadas.

### Otros
- `_hoja_con` acepta `max_filas` para encabezados que no están en la 1ª fila.
- Motivos nuevos en REVISAR: `REV_REPITE_TOTAL`, `REV_DUPLICADO`,
  `REV_AJUSTE_REPORTE`, `REV_FACTURA_SIN_REPORTE`, `REV_SERVICIO_ASIGNADO`.
- El resumen del CLI imprime el cuadre contra el reporte y las facturas que no
  cuadren.

### Pruebas
16 nuevas (65 en total en el archivo): que se quite el renglón que repite el
total, que las repeticiones se quiten de mayor a menor, que **nunca se baje del
valor reportado**, que el cuadre mande sobre el tope de DGH, que el ajuste se
reparta si no cabe en un renglón, que ningún valor quede negativo, y que el
lector tolere el encabezado en la 2ª fila.


## Sesión 21-ago-2026 — `organizar_objeciones_adres.py`: glosas del ADRES → OBJECIONES de DGH

Bot nuevo (`tools/organizar_objeciones_adres.py` + `OBJECIONES_ADRES.cmd` +
`README_organizar_objeciones_adres.md`) que convierte el Excel de glosas del
ADRES al layout de 16 columnas que recibe Dinámica Gerencial.

### Homologación del código de servicio (`SLNSERPRO`)
Seis pasos, siempre dentro de la misma factura, parando en el primero que
acierta: código directo (igualando ceros de relleno), SOAT→CUPS con el
Homologador Gold Standard, descripción igual, descripción por prefijo, valor
exacto + ≥50 % de palabras en común, y similitud ≥0,85. Lo que no se resuelve
sale con la casilla **vacía** y con su mejor candidato listado en `REVISAR` —
nunca se escribe un código deducido.

En el paquete 31068: 2.763 de 3.262 renglones con servicio (84,7 %).

### Reglas del formato
- `CDCONSEC` y `GENUSUARIO4` como TEXTO, `CROCLAOBJ=0`, `GENUSUARIO4=999`.
- `CRNCXC` en formato largo (`HUS311371` → `HUS0000311371`).
- `CROTIPOBJ` por factura: administrativas `0`, pertinencia `1`, mezcla `2`.
- **Guardián de valores** (el mismo de `cruces_dgh.generar_objeciones`): la
  objeción no supera el valor del servicio en DGH ni el saldo de la factura.
- **Lotes de 300 facturas** (tope de DGH), sin partir ninguna factura.

### Detalles que costaron
- El libro del ADRES trae una tabla dinámica con las mismas columnas pero los
  valores sumados (`Suma de Valor Glosado`); detectar la hoja de glosas por dos
  columnas dejaba todas las objeciones en cero. Ahora se exigen cuatro.
- El texto de la causal viene repetido detrás de su código en la misma celda;
  se corta en la última aparición de `<código>-`.
- `CRNCONOBJ`: el ADRES usa códigos numéricos de 4 dígitos y DGH los de 6 del
  Manual Único, y **no existe tabla oficial que los equipare**. Se escribe el
  del ADRES tal cual y se entrega la hoja `CODIGOS` + `--mapa-codigos` para que
  el auditor defina la equivalencia.

### Pruebas
`tests/test_tools/test_organizar_objeciones_adres.py` — 49 pruebas, incluida
una de punta a punta que arma los tres libros de entrada y verifica el archivo
de salida celda por celda.

## Sesión 20-ago-2026 (noche) — Rediseño de la aplicación web del ICFES

De cuatro pantallas planas a un panel con el plan de estudio adentro.

### Funcionalidad nueva
- **El plan de estudio ahora vive en la aplicación**: Inicio abre en «qué te
  toca hoy» con los bloques del día y un botón para empezar cada uno; la
  pantalla **Plan** muestra las cuatro fases y el detalle de cualquier semana.
- **Estudiar** (pantalla nueva): repaso del día, cuaderno de errores, las
  competencias más flojas con botón para practicarlas, y práctica libre con
  filtros de área, competencia, dificultad y procedencia.
- **Progreso**: proyección al día del examen, línea del año, una mini gráfica
  por área, competencias ordenadas, causas de error con su remedio, calendario
  de constancia y preguntas reincidentes.
- **Durante las preguntas**: cronómetro con el ritmo real del examen y semáforo
  de ritmo, atajos de teclado (A-D y Enter), marcar preguntas para revisar y
  lecturas largas en serif.
- Barra lateral en pantallas grandes; barra inferior en celular.

### Una sola fuente de verdad
- La política del plan (fases, mezclas, piso por área, minutos por bloque) y las
  escalas de puntaje se **exportan** desde `icfes/plan.py` y `icfes/puntaje.py`
  en vez de reescribirse en JavaScript.
- **`tests/test_icfes/test_nucleo_web.py`** extrae el núcleo de cálculo de la
  plantilla, lo corre con node y lo compara contra Python: metas por área,
  reparto de horas, puntaje, repaso espaciado y el plan completo **bloque por
  bloque** en tres escenarios. Se salta si node no está instalado.

### Color y accesibilidad
- Paleta de gráficas validada con el script de la guía de visualización: rampa
  secuencial monótona en claro y oscuro, y contraste ≥ 3:1 en las dos
  superficies.
- La primera versión coloreaba cada barra por estado; el validador la rechazó
  (verde y rojo se confunden para daltonismo, ΔE 4,1). Se corrigió por diseño:
  una sola serie, un solo tono, y el estado en una etiqueta con texto.
- Tres estados de tema (claro, oscuro por sistema, oscuro elegido) con una
  prueba que verifica que ningún color viva solo dentro de un bloque de tema.

### Correcciones encontradas probando en navegador
- Dos simulacros el mismo día se superponían en la gráfica de línea y sus zonas
  de hover se tapaban. Ahora la serie deja un punto por día (el último) y el
  ancho de la zona sensible se calcula desde la separación real entre puntos.
- El calendario de constancia solo miraba hacia atrás desde hoy: con avance
  importado decía «199 días con estudio» y salía vacío.
- En práctica el cronómetro estaba congelado y el semáforo de ritmo siempre en
  verde.

### Pruebas
266 en total (27 nuevas). `ruff check` y `ruff format` limpios sobre 1.229
archivos. Recorrido completo verificado en Chromium: escritorio y celular, tema
claro y oscuro, sin errores de JavaScript y sin desbordamiento horizontal.

## Sesión 20-ago-2026 (cierre) — Bot de doble clic del ICFES y guías corregidas

**Falla del primer uso real:** los comandos de la guía se corrieron desde
`C:\Users\cartera` y Python respondió `No module named icfes`. `python -m icfes`
requiere que la consola esté dentro de la carpeta del repositorio, y ninguna de
las tres guías lo decía.

### Cambios
- **`tools/ICFES.cmd`** (nuevo): bot de doble clic con menú completo — hoy,
  practicar, repasar, simulacro, progreso, plan, configurar y exportar la app.
  Hace `cd /d "%~dp0.."` antes de llamar a Python, así que el error no puede
  ocurrir; y verifica que Python esté instalado antes de intentar nada.
- **`docs/GUIA_SISTEMA_ICFES.md`**, **`docs/ESTRATEGIA_ICFES_400.md`** y
  **`README.md`**: el doble clic va primero, el `cd` aparece como paso cero y se
  explica qué significa `No module named icfes`.

### Pruebas (`tests/test_icfes/test_bots_windows.py`, 12 nuevas)
- Los bots del ICFES se paran en la carpeta del repositorio y avisan si falta
  Python.
- El menú no llama a ningún subcomando que no exista en el CLI (se valida
  contra el parser real).
- Los bots no traen credenciales.
- **Todos los `.cmd` del repositorio conservan finales de línea CRLF.** Esta
  regla estaba en `.gitattributes` y en CLAUDE.md pero no tenía prueba; con LF
  la ventana se cierra en Windows sin ejecutar nada.

Total del módulo: 251 pruebas.

## Sesión 20-ago-2026 — Sistema de preparación para el ICFES Saber 11 (`icfes/`)

Módulo **independiente** del Motor de Glosas: no importa nada de `app/` ni de
`tools/`, y solo usa la librería estándar de Python 3.11, así que la carpeta
`icfes/` se puede copiar a cualquier computador y funciona.

### Qué trae
- **`icfes/dominio.py`** — el examen modelado con datos oficiales: 254 preguntas
  calificables (41/50/50/58/55), 24 de pilotaje, pesos 3-3-3-3-1, dos sesiones
  de 4 h 30, y las 17 competencias de las cinco áreas.
- **`icfes/puntaje.py`** — puntaje global 0-500 con la fórmula oficial
  (`(3·LC+3·MAT+3·SOC+3·CN+1·ING)/13 × 5`); estimación de área 0-100 con curva
  declarada y editable (`CURVA_PUNTAJE`), siempre rotulada como estimación;
  reparto de una meta global en metas por área; corrección por azar.
- **`icfes/banco/`** — 110 preguntas de práctica en JSON (una por área), todas
  con explicación y con el distractor principal identificado. Cubre las 17
  competencias. Textos de Lectura Crítica en dominio público.
- **`icfes/plan.py`** — plan de 50 semanas en cuatro fases, con reparto de horas
  por peso oficial × brecha, piso del 8 % por área, día de descanso semanal,
  última semana aliviada y 11 simulacros completos.
- **`icfes/repaso.py`** — SM-2 adaptado; nunca programa un repaso posterior al
  examen; deduce la calidad del repaso de acierto, tiempo y causa del error.
- **`icfes/simulacro.py`** — simulacros con la estructura y los segundos por
  pregunta reales; a escala cuando el banco no alcanza, avisándolo.
- **`icfes/progreso.py`** — dominio ponderado por recencia, cuaderno de errores
  por causa con su remedio, racha y proyección por mínimos cuadrados que declara
  cuándo no es confiable.
- **`icfes/almacen.py`** — SQLite local (`~/.icfes/progreso.db`).
- **`icfes/cli.py`** — `python -m icfes iniciar|hoy|plan|practicar|simulacro|
  repaso|progreso|banco|exportar-web`.
- **`icfes/exportar_web.py`** + **`plantilla_web.html`** — aplicación web de un
  solo archivo, sin red, adaptable a celular, con tema claro/oscuro y avance en
  `localStorage`.
- **`tools/ICFES_APP.cmd`** — bot de doble clic para Windows (CRLF).

### Correcciones hechas durante el desarrollo
- **Simulacro**: reconstruía las respuestas desde la base de datos, así que una
  pregunta acertada en una práctica del mismo día contaba como acertada en el
  simulacro. La ronda ahora devuelve las respuestas reales, traducidas del orden
  barajado al orden original de la pregunta.
- **Exportación web**: la plantilla dejaba su objeto por defecto pegado al JSON
  inyectado (`const DATOS = {…}{…};`) y la página no cargaba. Se detectó abriendo
  la app en Chromium. Corregido con marcas de apertura/cierre y cubierto por
  prueba.
- **Banco**: la primera versión concentraba el 65 % de las respuestas correctas
  en la letra B. Como las opciones se barajan en cada práctica, el validador
  ahora exige que ninguna explicación nombre letras y verifica el reparto.

### Pruebas
239 pruebas en `tests/test_icfes/`; `ruff check` y `ruff format` limpios.
Recorrido completo de la app web verificado en Chromium (práctica, explicación,
cronómetro, resultado, progreso, persistencia tras recargar) sin errores de
JavaScript.

### Documentación
`docs/GUIA_SISTEMA_ICFES.md` y `docs/ESTRATEGIA_ICFES_400.md`.

## Sesión 10-jul-2026 — Suite Cartera HUS: herramienta multifuncional (GUI + CLI)

Integra en `tools/suite_cartera_hus/` la Suite de Cartera/Auditoría (menú
único de radicación, glosas y cruces masivos: reemplaza Power Query +
BUSCARV) con correcciones de fondo, endurecimiento y pruebas.

### Correcciones (verificadas con pruebas)
- **`a_numero`**: `'50.000'` se leía como `50` y no `50000` — corrompía
  TODOS los importes (glosado/servicio/saldo/copago y el guardián de
  valores). Ahora resuelve miles/decimales en formato colombiano, UE y US.
- **`generar_objeciones`**: `KeyError` si el Excel elegido no traía
  `valor_servicio/saldo/copago`; ahora da un error claro o tolera la falta.
- **`consolidar`**: renglones sin factura (celda vacía y sin factura en el
  nombre) se perdían en silencio en el `groupby`; ahora sobreviven visibles.
- **`consolidar`**: si no hay columna propia de código de servicio ya no se
  confunde con la de glosa (evita agrupar/sumar por la clave equivocada);
  además depura renglones byte-idénticos (duplicados de exportación).
- **`extraer_factura`**: reconoce facturas numéricas pegadas a `_` y da
  prioridad al formato HUS aunque una fecha aparezca antes en el nombre.
- **`leer_tabla`**: acepta listas de una sola columna (facturas ya
  objetadas) y CSV en latin-1 (Windows), que antes reventaban.
- **`extraer_zip_recursivo`**: los ZIP anidados ya no se pisan entre sí, y
  una entrada insegura (`../`) se omite sin abortar todo el ZIP.

### Seguridad
- Las contraseñas de los portales salen de `entidades.json` a un archivo
  **local no versionado** (`entidades.credenciales.json`, en `.gitignore`).
  La Suite las vuelve a unir en memoria al abrir. Incluye
  `herramientas/separar_credenciales.py` y una plantilla `.example`.

### Nuevo
- **`suite_cli.py`**: la misma Suite por línea de comandos (`entidades`,
  `organizar`, `consolidar`, `objeciones`, `evidencias`, `todo`) para
  automatizar sin ventana.
- **`tests/test_tools/test_suite_cartera_hus.py`**: 40 pruebas del núcleo
  (las que requieren pandas se saltan si no está, como el resto de tools).

## Sesión 1–2-jul-2026 — El expediente: contratos + soportes + precedentes

Diagnóstico que disparó la sesión (del usuario): *"la IA se rehúsa a
refutar... es como pegar el concepto en una IA normal"*. Causa raíz
confirmada: el motor argumentaba **a ciegas** — tres conexiones de datos
existían como código pero estaban desenchufadas de la generación del
dictamen. Esta sesión las enchufó (rondas 23–25).

### Fase 1 — Contratos (ronda 23)
- `get_contrato` ahora lee la BD (`ContratoRecord` + `ClausulaContrato`),
  no solo el catálogo estático: fin del falso "SIN CONTRATO PACTADO"
  cuando sí hay contrato cargado.
- Emparejamiento flexible de EPS ("AURORA" encuentra "SEGUROS DE VIDA
  AURORA S.A.").
- **26 cláusulas LITERALES de 11 pagadores reales** cargables con
  `scripts/seed_clausulas_contrato.py` (idempotente): AURORA (8),
  COMPENSAR, COOSALUD, SUMIMEDICAL, SALUD MÍA (3), POSITIVA (2), PPL (2),
  FAMISANAR 2026, DISPENSARIO MÉDICO/DMBUG (3), POLICÍA oncología (2),
  FOMAG (2 — incl. Circular 004/2025: sin autorización previa a docentes).
  Tarifas verificadas contra los Excel (SOAT−3/10/15/20%, UVB−5/8%,
  SMDLV−20%).
- Correcciones de catálogo: FOMAG a SOAT SMDLV −20% (Acta 012), POLICÍA
  oncología a UVB−8% + institucionales (Anexo 2 de la minuta), PRECIMED
  eliminado (era contrato de suministro con PRECIMEC SAS, no un pagador).

### Fase 2 — Soportes (ronda 24)
- **Tope de OCR 2000 → 12000 chars** en el caso simple (la IA por fin ve
  la HC adjunta); tunable por env (`GLOSA_SOPORTES_MAX_CHARS_*`).
- **Multimodal automático** (`GLOSA_MULTIMODAL_AUTO=1`): los casos que ya
  escalan a Claude mandan los PDFs nativos completos; los simples siguen
  en Groq con texto (no es "siempre Claude").
- **Gate interactivo de expediente**: el detector determinista avisa en el
  prompt qué soportes faltan y prohíbe inventar evidencia; fallback
  sin-soportes reescrito de "el registro clínico respalda la atención"
  (invitación a alucinar) a reglas anti-invención siempre-verdaderas.
- **Auditor Forense conectado al dictamen** (opt-in,
  `GLOSA_AUDITOR_FORENSE_PREPASS=1`): pre-pass que lee los PDFs y antepone
  un mapa de folios (folio + fecha + hallazgo + faltantes) al contexto.
- Review adversarial del propio diff cazó y corrigió 6 bugs antes de
  mergear (el peor: Opus degradándose a Sonnet en casos ≥$10M por la vía
  multimodal; backstop nuevo en el validador contra fuga del andamiaje
  del prompt al dictamen).

### Fase 3 — RAG/banco (ronda 25)
- **Few-shots por SIMILITUD BM25** (`GLOSA_FEWSHOT_BM25=1`): cuando el
  match exacto (eps+código) no llena los ejemplos, se completa con el
  precedente GANADO más parecido al texto de la glosa (RAGService, antes
  desconectado de la generación). Sin tokens extra.
- Filtro de contrato ajeno sobre los precedentes + instrucción anti-copia
  reforzada (estilo sí, datos del otro expediente no).

Suite: **4069 tests verdes**. Todo reversible por env var sin redeploy.

---

## Sesión 30-jun-2026 — De "a ciegas" a "medido"

Resultado medible de la sesión, con el **tablero de calidad** (0–10) sobre
los 4 casos difíciles reales:

| Caso | Antes | Después |
|---|---|---|
| MEDIMÁS da Vinci $273M | 0.5 | **10** |
| ECOOPSOS coclear $389M | 4.5 | **10** |
| SALUD TOTAL TMS $98M | 5.0 | **10** |
| Hemofilia + sanción $156M | 0.0 | 6 → escala a Claude (subiendo) |
| **Promedio** | **2.5/10** | **~9/10** |

El cambio de fondo: dejamos de parchear a ciegas. Ahora cada cambio se
**mide** contra una rúbrica experta y el que **regresa** se detecta solo.

---

### Operación / producción (incidentes resueltos)
- **Cloudflare Error 1033** (app caída): causa raíz `net.ipv4.ip_forward=0`
  → NAT de Docker rota → los contenedores no salían a internet y el túnel
  no conectaba. Fix: `ip_forward=1` + reinicio de Docker (+ persistencia en
  `/etc/sysctl.d/`).
- **502 Bad Gateway**: contenedor `motor` con referencia stale tras un
  `up --build`. Fix: `docker compose down && up -d`.

### Limpieza de imports (PR #152, mergeado)
- Eliminados **~100 lazy imports redundantes** en `glosas_stats.py` y
  `sistema.py` (símbolos ya disponibles a nivel de módulo).
- Agregado `app/utils/__init__.py` faltante.

### Mejora #3 — Salida estructurada incremental (flag OFF por defecto)
- Flag `GLOSA_CAMPOS_ESTRUCTURADOS` (config + docker-compose + .env.example).
- La IA confirma 6 campos críticos (EPS, servicio, contrato, cláusulas,
  sanción, sub-conceptos) en un bloque JSON que el motor cruza contra los
  valores **deterministas** (verdad = determinista) y registra divergencias.
- Parser tolerante + validación + degradación elegante + tests (31).
- Runbook de activación: `docs/RUNBOOK_CAMPOS_ESTRUCTURADOS.md`.

### Ronda 21 — Auditoría del dictamen MEDIMÁS da Vinci (9 fixes)
- **#1 (crítico)** Contrato negado en el cuerpo ("al no existir contrato
  pactado") pese a que la glosa lo cita → regex ampliado a la forma verbal.
- **#2 (crítico)** Tarifa: ya no afirma "SOAT pleno / sin contrato" cuando
  la glosa cita un contrato; defiende dentro del contrato (Pacta Sunt S.).
- **#5** Pertinencia: rebate la GPC citada con T-121/2015 + evidencia 1A.
- **#6** Rebate por nombre las normas que cita la EPS (+ regex de extracción
  que ahora captura "Res. 0112/2012", "Decreto 4747/2007 Art. 20").
- **#8** Banner + penalización cuando se evade una cláusula citada.
- **#9** Vocabulario de cobertura (evento adverso, liquidación).
- **#10** Defensa de liquidación anclada (Auto 116/2024).
- **#11** Recorte de coda procesal unida por conjunción.
- **#12** "Art. 177 Ley 100" pelado en debate tarifario → fundamento correcto.

### Defensa clínica (PR #151, mergeado + integrado)
- Banco de evidencia nivel 1A (da Vinci, coclear, TMS, hemofilia, etc.) que
  nunca se había integrado a producción. Ahora se inyecta al prompt y se
  audita la literatura citada.

### Ronda 22 — Defectos del tablero (capa de generación)
- Reglas de prompt: sanción → atacar la legalidad (NO "Pacta Sunt Servanda"
  ante una multa); prohibido tono amenazante; prohibido el falso "silencio
  positivo"; prohibido inventar el texto de cláusulas/normas; no confundir
  normas por tema (Ley 1388/2010 es de cáncer, no auditiva).
- Red de seguridad: `_corregir_norma_mal_aplicada` (Ley 1388→1618).

### Tablero de calidad (lo nuevo de fondo)
- `tests/benchmark/scorer.py`: rúbrica experta determinista (0–10, sin LLM).
- `tools/scoreboard.py`: mide el texto guardado + **memoria** (historial) +
  detección de **regresión** + modo `--rescore-live`.
- `tools/scoreboard_live.py`: corre las 4 glosas por el **motor real** y las
  puntúa (mide el efecto real de cada cambio). Progreso visible + timeout.
- `docs/EJEMPLOS_DICTAMENES_ESPERADOS.md`: 4 casos con el dictamen esperado
  y checklist de criterios.
- Regla del proyecto: la IA es BUENA solo si **los 4 casos sacan ≥ 7**.

### Routing
- Hemofilia con inhibidores ("factor VII / eptacog") ahora escala a Claude
  (palabra-clave + valor), no se queda en Groq.

---

_Total sesión: 18 commits en la rama + PR #151 y #152 mergeados._
