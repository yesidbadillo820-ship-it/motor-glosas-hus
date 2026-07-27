# Entrega Técnica Oficial — Módulo HOSPIAI

**Proyecto:** Suite de Cuentas Médicas y Cartera · ESE Hospital Universitario de Santander
**Módulo:** HOSPIAI (Sistema Operativo Inteligente de Cuentas Médicas)
**Rama de desarrollo:** `claude/radicador-share-real`
**Versión:** 1.0.0 · **Estado:** en producción (primera corrida real 23-jul-2026)
**Documento para:** el equipo del proyecto principal (consolidación de repositorios)

> Este documento reconstruye **todo** lo desarrollado en esta línea de trabajo, para
> que el módulo pueda integrarse y mantenerse sin pérdida de conocimiento. Es la
> documentación oficial del módulo. Donde el módulo no implementa algo que la
> plantilla pide (p. ej. frontend web SPA o modelos de lenguaje), se declara
> explícitamente en lugar de inventarlo.

---

## 1. Objetivo del desarrollo

### ¿Por qué se creó?
El área de Cuentas Médicas y Cartera del HUS radica **más de 12.000 facturas al mes**
ante las EPS. Cada factura debe llevar sus soportes completos (factura electrónica,
RIPS, CUV, y los soportes clínicos según el tipo de atención: epicrisis, hoja de
evidencia, descripción quirúrgica, etc.). Si falta un soporte, la EPS **devuelve o
glosa** la factura y se congela la cartera. La revisión se hacía **manualmente,
factura por factura**, lo que era lento, incompleto y no dejaba trazabilidad.

### ¿Qué problema resuelve?
1. **Auditoría automática** de las 12.523 facturas del lote: clasifica cada una en
   LISTA / REVISAR_TIPIFICACION / FALTAN_SOPORTES / SIN_RIPS / ENTIDAD_NO_RESUELTA /
   PARTICULAR, identificando qué le falta y dónde está.
2. **Cruce de soportes clínicos** que viven en servidores separados (Y:/Z:/X:),
   completando automáticamente las facturas incompletas.
3. **Trazabilidad auditable**: cada dictamen queda con la regla que lo sustenta, la
   norma y la evidencia — defendible ante una auditoría.
4. **Inteligencia operativa**: no solo dice "qué falta", sino "qué hacer hoy para
   liberar más dinero", con impacto económico calculado.

### ¿Qué necesidad cubría?
Convertir una tarea manual, no medible y sin memoria, en una **plataforma que audita,
explica, recomienda y mide** — y que llega cada mañana con las decisiones del día
(copiloto operacional). El éxito se mide en indicadores reales: % de facturas LISTAS,
dinero recuperable, tiempo de radicación.

---

## 2. Arquitectura

### Estructura del módulo
HOSPIAI es una **plataforma multi-agente** sobre un **Expediente Digital** (base
SQLite local). Principios de diseño:
- **Agentes con contrato único** (SDK): todos tienen identidad (AGxxx), versión,
  dominio, capacidades y devuelven el mismo formato de resultado.
- **Los agentes nunca se llaman entre sí**: publican misiones en una cola persistente.
- **El Supervisor consume un Registro Central** (`data/agentes.json`), nunca clases
  concretas.
- **Las reglas y políticas son datos**, no código (`data/*.json`).
- **Todo es solo lectura** sobre los servidores del hospital; solo escribe la base
  local, los paneles HTML y los reportes CSV/XLSX.

### Componentes (6 dominios + orquestación)
- **D1 Documental**: indexación, clasificación, perfilado de PDFs (DIS).
- **D2 Clínico**: OCR (planeado, no implementado).
- **D3 Administrativo/Auditoría**: resolución de entidad, completitud, cruce.
- **D4 Financiero/Conocimiento**: memoria institucional, patrones, causa raíz.
- **D5 Operacional**: plan de recuperación, corrección masiva, balance de carga.
- **D6 Gerencial/Comando**: directores, HOS, copiloto ejecutivo.
- **Orquestación**: Supervisor (Scheduler/Dispatcher/RetryManager/PolicyEngine).

### Carpetas
```
motor-glosas-hus/
├── tools/                 # todo el código HOSPIAI (Python stdlib) + PowerShell
├── data/                  # configuración (JSON), ontologías, golden, base local
│   ├── ontologias/        # 5 ontologías (documental, clínica, cups, normativa, contractual)
│   ├── golden/            # casos.json (10 casos sintéticos de regresión)
│   ├── indices/           # índices SQLite por servidor (NO en git; se generan)
│   └── hospiai.db         # Expediente Digital (NO en git; datos reales)
├── tests/test_tools/      # 251 pruebas de las herramientas HOSPIAI
└── docs/                  # arquitectura, manuales, acta, guiones, esta entrega
```

### Archivos de código (tools/)
| Archivo | Rol |
|---|---|
| `radicar_facturacion.py` | Motor de auditoría y cruce; persiste cada corrida. |
| `hospiai_db.py` | Esquema del Expediente Digital, migraciones, vistas, `persistir_corrida()`. |
| `hospiai_sdk.py` | Contrato `Agente`/`ResultadoAgente`, `ColaMisiones`, `RegistroAgentes`. |
| `hospiai_agentes.py` | AG002/AG003/AG011 + `registro_con_implementaciones()`. |
| `hospiai_indexador.py` | AG001/DIS: índice permanente por servidor. |
| `hospiai_documento.py` | DIS: fingerprint PDF, calidad, duplicados, `document_profile`; AG016–AG018. |
| `hospiai_semantica.py` | Motor semántico sobre ontologías; AG011. |
| `hospiai_supervisor.py` | AG010: orquestación. |
| `hospiai_directores.py` | AG012–AG015. |
| `hospiai_conocimiento.py` | Memoria Institucional + AG019–AG023 + `recomendar`/`simular`. |
| `hospiai_operacion.py` | AG024–AG028 + `indicadores` + `plan`/`oportunidades`. |
| `hospiai_comando.py` | HOS + AG029–AG033 + `iniciar-dia`/`preguntar`. |
| `hospiai_gobernanza.py` | Registro de artefactos, golden, compatibilidad, salud. |
| `hospiai_api.py` | Capa de servicios + servidor HTTP local (solo lectura). |
| `hospiai_dsl.py` | Compilador del DSL de reglas. |
| `hospiai.py` | Consola principal (CLI). |
| `hospiai_panel_ejecutivo.py` | Panel HTML alimentado solo por la API. |
| `hospiai_rpa.py` | Interfaz RPA (contrato; sin adaptador real, retenido por política). |
| `corrida_diaria.ps1` | Orquestador PowerShell del día. |

### Dependencias / librerías
- **Python 3.11+** (probado hasta 3.14). **Solo librería estándar**: `sqlite3`,
  `argparse`, `pathlib`, `datetime`, `json`, `hashlib`, `unicodedata`, `http.server`,
  `os`, `re`, `time`, `html`.
- **`openpyxl`** — opcional, únicamente para exportar el XLSX. Si no está, el CSV sale igual.
- **Cero dependencias externas nuevas.** No usa frameworks web, ni ORM, ni servicios cloud.

### APIs
API interna HTTP de **solo lectura** (`hospiai_api.py`), pensada como contrato estable
para integrar HIS/ERP/BI en el futuro. Corre en `127.0.0.1` (local). Rutas en §6.

### Modelos
No hay ORM ni modelos de clases-tabla. El "modelo de datos" es el **esquema SQLite**
(§5). Los objetos de dominio son diccionarios serializables devueltos por la capa de
servicios.

### Servicios
La clase `Servicios` (`hospiai_api.py`) es la **única puerta** a la plataforma:
cada método es un endpoint estable que devuelve dicts, sin exponer el esquema interno.

### Utilidades
`hospiai_gobernanza.py` (artefactos/deriva/golden/salud), `hospiai_dsl.py` (compilar
reglas), `diag_soportes.py` (diagnóstico del cruce, de la etapa temprana).

---

## 3. Funciones y componentes implementados

> Se documentan las funciones y clases principales por módulo (nivel de mantenimiento).

### `radicar_facturacion.py` — el motor
- **`analizar_ruta(ruta)`**: de una ruta del share extrae año, mes, entidad,
  responsable (funcionario) y lote. Determinístico. *Existe para poblar los
  indicadores por funcionario (D5).* Lo usa AG002.
- **`clasificar_soporte(nombre)`**: nombre de archivo → código ADRES (FEV, RIP, CUV,
  HEV, EPI, DQX…). Diccionario oficial + alias HUS. Lo usa AG003 y el indexador.
- **`resolver_entidad(...)`**: identifica el pagador por catálogo + razón social del
  FEV (25+ entidades). Legacy AG005.
- **`procesar_factura(...)`**: cruza inventario vs. reglas vigentes → dictamen con
  hallazgos y evidencia. Corazón del AG006.
- **`indexar_soportes_desde_db(...)` / `_desde_indice(...)`**: carga los soportes
  clínicos desde el índice SQLite o el txt. AG007.
- **`cargar_reglas(ruta, cfg, fecha_referencia)`**: aplica la regla correcta según la
  fecha (vigencias). *Existe para que convivan versiones de la norma.*
- **`normalizar_factura(fac)`**: normaliza el número (quita "HUS" y ceros). Clave de
  cruce usada por todo el sistema.
- **`_clave_factura_en(texto, rx)`**: extrae el número de factura de un nombre o de la
  **carpeta contenedora** (decisión clave; ver §15/§decisiones).
- **`EQUIVALENCIAS_SOPORTE_DEFAULT`**: `{EPI:[EPI,HEV], HAU:[HAU,HEV]}` — en el HUS la
  epicrisis y urgencias se escanean dentro de la HEV, así que una HEV las cubre.
- Persiste cada corrida en el Expediente vía hook a `hospiai_db.persistir_corrida`.

### `hospiai_db.py` — Expediente Digital
- **`abrir(db_path)`**: abre/crea la base, aplica el esquema (`CREATE TABLE IF NOT
  EXISTS`) y las migraciones suaves. *Clave para la integración: abrir una base vieja
  con código nuevo agrega solas las tablas/columnas faltantes, sin perder datos.*
- **`persistir_corrida(...)`**: escribe expedientes, documentos, hallazgos (con
  evidencia y confianza), eventos y Decision Records; sincroniza reglas y catálogo.
  Es el AG008.
- **`VISTAS_SQL`**: `vw_evidencias`, `vw_productividad`, `vw_memoria_glosas`.

### `hospiai_sdk.py` — contrato de agente
- **`Agente`** (clase base): atributos id/nombre/dominio/version/entradas/salidas/
  depende_de/herramientas/capacidades/estado; método plantilla `ejecutar()` que valida,
  cronometra y llama a `_trabajar()` (lo único que implementan las subclases); devuelve
  `ResultadoAgente`.
- **`ResultadoAgente`**: dict fijo (agente, version, expediente, resultado
  OK/ERROR/OMITIDO, confianza, hallazgos, evidencias, salida, detalle, duracion_ms,
  versiones). *Formato único para que un agente que falla no tumbe la plataforma.*
- **`ColaMisiones`**: crear/tomar/completar/fallar/estado + primitivas del Supervisor
  (pendientes/estados_de/asignar/reprogramar).
- **`RegistroAgentes`**: `registrar_clase`, `listar`, `disponibles`, `por_capacidad`,
  `instanciar`, `explicar`. La ficha JSON manda sobre la clase.
- `VERSION_SDK = "1.0"`.

### `hospiai_indexador.py` — AG001 / DIS (índice permanente)
- **`indexar_raiz(raiz, ...)`**: indexa un servidor en su base SQLite propia
  (`indice_<alias>.db`), en lotes de 5.000 con **guardado inmediato**, incremental
  (compara mtime/size), marca AUSENTE lo borrado, con progreso (rate/ETA).
- **`alias_de(raiz)`**: letra de unidad o slug+sha1[:6] (dos raíces jamás comparten base).
- **`buscar(factura)`**: búsqueda instantánea uniendo todas las bases.
- **`estado()`**: resumen por base. **`vigilar(cada)`**: rescan incremental en bucle.
- **`AgenteIndexador`**: INDEXAR, BUSCAR_ARCHIVO.

### `hospiai_documento.py` — DIS objeto documental
- **`fingerprint_pdf(ruta)`**: lee la estructura del PDF sin librerías (regex sobre
  bytes: /Count, /Type/Page, /Author, /ByteRange, /Font, /Encrypt, /Rotate, %PDF,
  %%EOF) → hash, páginas, autor, firma, texto, cifrado, rotación, problema.
- **`calificar(fp)`**: calidad A/B/C/D/X por señales verificables.
- **`clasificar_con_confianza(nombre, carpeta)`**: 0.98 token / 0.9 alias / 0.5 carpeta
  / 0.3 sin evidencia.
- **`perfilar_base(db)`**: llena `document_profile`; dup exacto (canónico = MIN(ruta)
  alfabético) y dup funcional (misma factura+código, hash distinto).
- **`perfil_factura(...)`**: el objeto documental completo (criterio de aceptación DIS).
- **AG016 DocumentCurator, AG017 StorageOptimizer, AG018 IngestaInteligente.**
- *dpi/legibilidad quedan NULL hasta el OCR — no se inventan medidas.*

### `hospiai_semantica.py` — AG011
- **`MotorSemantico.explicar(codigo)`**: cadena código → significado → implicación
  (documento/CIE-10/CUPS). **`importar-cups`** (extracción AST de 158 CUPS oficiales),
  **`cargar-cie10`**. *Los códigos clínicos jamás se inventan: solo semilla verificada
  + tablas oficiales.*

### `hospiai_supervisor.py` — AG010
- **`PolicyEngine`**: `permitida()` (aprobación humana / tope por tipo / horario),
  `backoff(intento)`, `cadena(tipo)`. *Las políticas viven en `data/politicas.json`,
  nunca en código.*
- **`Scheduler`** (elegibles respetando depende_de + no_antes), **`Dispatcher`** (elige
  por Registro + compatibilidad, jamás importa clases), **`RetryManager`** (backoff →
  PENDIENTE; agotado → ERROR + Decision Record), **`MissionLogger`**, **`Supervisor`**.

### `hospiai_directores.py` — AG012–AG015
- **`analizar_corrida(db)`**: la analítica central (resumen, riesgo por causa,
  responsables, entidades con causa principal, hallazgos valorizados con norma,
  predicción = único faltante, recomendaciones por impacto). Fuente única de los tres
  directores.
- **AG012** informe gerencial (JSON en `data/informes/`), **AG013** tareas del día
  (misiones TAREA_HUMANA retenidas), **AG014** 5 respuestas de caja, **AG015**
  aprendizaje entre corridas → eventos APRENDIZAJE **y** entradas LECCION en la Memoria
  Institucional (regla de arquitectura Fase 2.2).

### `hospiai_conocimiento.py` — Memoria + AG019–AG023
- **`MemoriaInstitucional`**: `registrar(tipo, enunciado, contexto, evidencia, ...)`
  (upsert por clave sha1(tipo+contexto); acumula ocurrencias/éxitos; asigna CON-xxxxxx);
  `consultar(tipo, contexto_como, solo_validado=True)`. *Única puerta del aprendizaje.*
- **`_confianza_laplace(exitos, ocurrencias) = (exitos+1)/(ocurrencias+2)`**. *Con 1
  caso NO reporta 100%.*
- **AG019 KnowledgeCurator**: promueve CANDIDATO→VALIDADO (n≥3, conf≥0.6, con
  evidencia), retira VALIDADO→RETIRADO (conf<0.4), versiona cada cambio.
- **AG020 PatternDiscovery** (patrones por eps/responsable/mes → candidatos),
  **`recomendar_expediente(db, factura)`** (POR REGLA VIGENTE prob 1.0 si es el único
  faltante, o histórica VALIDADA con casos) + **AG021**, **AG022 RootCauseEngine**
  (concentración ≥60% + mapa `data/causas_raiz.json`), **AG023 ProcessMiner**
  (transiciones entre eventos → cuello de botella en horas).
- **`simular(db, escenario, codigo)`**: motor de hipótesis; `_liberadas_si(cods)`
  cuenta expedientes cuyas faltas ⊆ cods (EXACTO por reglas); redistribución etiquetada
  como ESTIMACIÓN.

### `hospiai_operacion.py` — AG024–AG028 + indicadores
- **`plan_expediente(db, factura, dir_indices)`**: convierte hallazgos en pasos con
  responsable (de `data/esfuerzos.json`), tiempo (curado, jamás inventado),
  probabilidad e impacto; **ASOCIAR** si el soporte ya existe en el índice, si no
  **CONSEGUIR**. AG024.
- **`oportunidades(db, dir_indices)`**: soluciones masivas con dinero EXACTO por reglas;
  distingue asociar (ya en el índice) de conseguir; solo propone. AG025.
- **`ficha_pagador(db, pagador)`** AG026, **`gemelo_eps(db, eps)`** AG027,
  **`mejora_semanal(db, dir_indices)`** AG028.
- **`calcular_indicadores(db, guardar)`**: 4 bloques (financieros/operativos/calidad/
  aprendizaje); lo no medible → None con su razón; persiste en tabla `indicadores`.

### `hospiai_comando.py` — HOS + AG029–AG033
- **`hospital_operational_score(db)`**: combina 6 componentes (calidad, tiempo,
  devoluciones, recuperación, productividad, aprendizaje) **solo con los que tienen
  datos**; excluye el resto con su razón y **re-pondera** (nunca inventa). Escala
  92-100/80-91/60-79/<60.
- **`situacion_del_dia(db)`** (HOS + decisiones), **`iniciar_dia(db, tope=15)`** AG029,
  **`balancear_carga(db)`** AG030 (reparto exacto, ganancia etiquetada),
  **`alertas_tempranas(db)`** AG031 (señales de `document_profile` + memoria; sin %
  inventado), **`proyectar_mes(db)`** AG032 (lineal con supuesto, o "insuficiente"),
  **`preguntar(db, pregunta)`** AG033 (intención por palabras clave → respuesta con
  evidencia/indicadores/confianza/recomendaciones; nunca opiniones).

### `hospiai_api.py`, `hospiai.py`, `hospiai_panel_ejecutivo.py`, `hospiai_gobernanza.py`, `hospiai_dsl.py`
Ver §2 y §6.

---

## 4. Flujo completo

> HOSPIAI no tiene "clic": es CLI + tarea programada. El flujo diario y el bajo demanda:

### Flujo diario (automático, `corrida_diaria.ps1`)
1. **Índice permanente**: `hospiai_indexador.py indexar Y: Z: X:` (incremental).
2. **Auditoría**: `radicar_facturacion.py` recorre el share de FE, clasifica cada
   soporte, **resuelve la entidad**, **cruza** los soportes clínicos desde el índice,
   aplica las **reglas vigentes** por tipo de atención y **dicta** cada factura. Escribe
   el CSV/XLSX y **persiste la corrida** en `hospiai.db` (expedientes, documentos,
   hallazgos con evidencia, eventos, Decision Records).
3. **Directores**: informe gerencial + aprendizaje entre corridas → Memoria.
4. **Conocimiento**: `curar` (promueve/retira) + `patrones`.
5. **Indicadores**: `calcular_indicadores` persiste los 4 bloques.
6. **Paneles**: `hospiai.py panel` + `hospiai_panel_ejecutivo.py` (abre con HOS y
   "situación del día").
7. **"Buenos días"**: `hospiai.py iniciar-dia` (acciones por retorno + objetivo del día).
8. **Viernes**: `hospiai_operacion.py mejora`.

### Flujo bajo demanda (un comando)
Ej. `hospiai.py oportunidades`: la consola lee `hospiai.db` + el índice → calcula las
oportunidades masivas con dinero exacto → imprime. Ej. `preguntar "…"`: normaliza el
texto → detecta intención → llama a la analítica correspondiente → responde con
evidencia y confianza.

### Lógica interna del dictamen (por factura)
inventario de soportes presentes → tipo de atención (del RIPS/servicios) → soportes
esperados (reglas vigentes) → faltantes = esperados − (presentes ∪ equivalencias ∪
cruce) → si faltan bloqueantes → REVISAR/FALTAN; si entidad no resuelta →
ENTIDAD_NO_RESUELTA; si completo → LISTA. Cada faltante genera un **hallazgo** con
criticidad, regla, norma, evidencia y confianza.

---

## 5. Base de datos (`data/hospiai.db`, SQLite, WAL)

### Tablas principales
| Tabla | Columnas clave |
|---|---|
| `corridas` | id, iniciada, terminada, origen, version_reglas, version_motor, total_expedientes/documentos/hallazgos |
| `pagadores` | id, nombre, nit, regimen, canal |
| `contratos` | id, pagador_id→, nombre, modalidad, manual_tarifario, plazo_dias, periodicidad, vigencia_desde/hasta |
| `reglas` | (declarativas, con vigencia_desde/hasta, fuente normativa) |
| `expedientes` | factura_norm (PK), factura, pagador_id/nombre, responsable, lote, anio, mes, carpeta, valor_total, usuarios, servicios, estado, dictamen, creado, actualizado, ultima_corrida |
| `documentos` | id, factura_norm, nombre, ruta, codigo, origen, visto_primera/ultima, corrida_id, UNIQUE(factura_norm, ruta) |
| `hallazgos` | id, factura_norm, corrida_id, agente, tipo, codigo, criticidad, detalle, regla_id, evidencia, confianza, fecha, resuelto |
| `eventos` | id, factura_norm, fecha, agente, tipo, resultado, version_reglas, corrida_id, detalle |
| `radicaciones` | id, factura_norm, fecha, plataforma, numero_radicado, comprobante, estado, detalle |
| `glosas` | id, factura_norm, fecha, causa, codigo_glosa, valor, estado, detalle, solucion, aprendizaje, tiempo_dias |
| `pagos` | id, factura_norm, fecha, valor, fuente, detalle |
| `conocimiento` | id, codigo (CON-xxxxxx), clave UNIQUE, tipo, enunciado, contexto, evidencia, ocurrencias, exitos, confianza, vigente_desde, version, estado (CANDIDATO/VALIDADO/RETIRADO), fuente_agente, actualizado |
| `indicadores` | id, corrida_id, categoria, nombre, valor, texto, calculado, UNIQUE(corrida_id, nombre) |
| `decisiones` | id, codigo (DEC-xxxxxx), factura_norm, corrida_id, dictamen, motivo, regla_id, agente, version_motor, version_reglas, confianza, fecha |
| `misiones` | id, codigo, expediente, tipo, prioridad, estado, creada, actualizada, creada_por, agente_asignado, intentos, max_intentos, datos, resultado, no_antes |

### Bases secundarias (índice DIS, `data/indices/indice_<alias>.db`)
- `archivos` (ruta UNIQUE, nombre, factura, tipo, reconocido, tamano, hash,
  ultima_modificacion, visto_primera/ultima, servidor, estado ACTIVO/AUSENTE)
- `corridas_indexacion` (iniciada, terminada, raiz, total, nuevos, actualizados,
  ausentes, modo)
- `document_profile` (ruta PK, hash, paginas, autor, productor, fechas, firma, texto,
  cifrado, rotacion, dpi, legibilidad, calidad, clase, codigo, confianza, dup_exacto_de,
  dup_funcional, problema, perfilado_en)

### Relaciones
`expedientes` es el eje (por `factura_norm`). `documentos`, `hallazgos`, `eventos`,
`radicaciones`, `glosas`, `pagos`, `decisiones` referencian la factura. `contratos`→
`pagadores`. `indicadores`→`corridas`.

### Índices
`ix_perfil_hash`, `ix_perfil_calidad` en `document_profile`; PK/UNIQUE en las tablas
listadas. WAL activado (`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`).

### Migraciones
`_MIGRACIONES` en `hospiai_db.py`: migración suave de columnas al abrir. **No hay
Alembic ni migraciones versionadas**: el patrón es idempotente (`CREATE TABLE IF NOT
EXISTS` + añadir columnas faltantes).

### Datos necesarios (semilla)
`data/agentes.json` (registro), `data/reglas_radicacion.json`,
`data/perfiles_radicacion.json`, `data/causas_raiz.json`, `data/esfuerzos.json`,
`data/politicas.json`, `data/ontologias/*`, `data/golden/casos.json`.

---

## 6. Backend

### Endpoints (API interna, solo lectura, `127.0.0.1`)
`/salud`, `/agentes`, `/capacidades`, `/misiones`, `/expedientes/{f}`,
`/decisiones/{f}`, `/evidencias/{f}`, `/ontologia/{c}`, `/informe`, `/caja`, `/tareas`,
`/recomendaciones/{f}`, `/simulaciones[/{codigo}]`, `/conocimiento`, `/plan/{f}`,
`/oportunidades`, `/indicadores`, `/fichas[/{pagador}]`, `/gemelo/{eps}`, `/mejora`,
`/hos`, `/situacion`, `/iniciar-dia`, `/carga`, `/alertas`, `/proyeccion`,
`/preguntar?q=`.

### Servicios / controladores
La clase `Servicios` es el controlador único; `_Manejador(BaseHTTPRequestHandler)`
enruta GET a los métodos de `Servicios`. No hay POST/escritura (por diseño; la
escritura llegará con el Supervisor y siempre con aprobación humana).

### Middleware / validaciones / errores
- Sin framework: el manejador captura excepciones → JSON `{"error": ...}` con 500;
  ruta no encontrada → 404; falta `?q=` en `/preguntar` → mensaje explícito.
- Validación de agentes: el SDK valida entradas y el contrato en vivo (compatibilidad).
- El Supervisor valida `requiere_sdk` (chequeo de major) y `existe_capacidad`.

### Permisos
No hay autenticación (corre en `127.0.0.1`, un solo equipo). La **política** de
`data/politicas.json` retiene por defecto RPA/RADICAR/SUBIR_PORTAL/TAREA_HUMANA hasta
aprobación humana (`requiere_aprobacion_humana`).

---

## 7. Frontend

> **HOSPIAI NO tiene frontend web (SPA).** No hay React/Vue, ni componentes, ni
> modales, ni animaciones, ni formularios web. Se declara explícitamente para no
> inventar.

La interfaz es de **dos tipos**:
1. **CLI** (PowerShell): la consola `hospiai.py` y los módulos `hospiai_*.py` con sus
   subcomandos. Es la superficie de uso diario.
2. **Paneles HTML autocontenidos** (generados por `hospiai.py panel` y
   `hospiai_panel_ejecutivo.py`): un solo archivo `.html` con CSS embebido, sin JS ni
   dependencias externas, que se abre con doble clic.
   - **Panel ejecutivo**: abre con la banda **"SITUACIÓN DEL DÍA"** (HOS grande +
     tarjetas de decisión), luego 6 preguntas de aceptación, luego 6 vistas (Estado
     General, Riesgo Financiero, Responsables, EPS, Hallazgos, Predicción) +
     Oportunidades + "¿Qué pasaría si…?" + memoria validada + tareas + respuestas de
     caja. **Se alimenta 100% de la API** (hay una prueba que verifica que el módulo no
     consulta SQLite directamente).
   - **Tablas** renderizadas con un helper `_tabla(headers, filas)`; **"pills"** de
     color por dictamen. Sin interactividad JS (es un reporte para leer/imprimir).

---

## 8. IA

> **Aclaración crítica y honesta:** el módulo HOSPIAI **NO utiliza modelos de lenguaje
> (LLM) ni IA generativa.** No hay prompts, no hay contexto de modelo, no hay proveedor
> (OpenAI/Groq/Anthropic), no hay temperatura, no hay respuestas generadas, no hay
> cadena de fallback de modelos. Se declara explícitamente para no inventar.

La "inteligencia" de HOSPIAI es **determinística + estadística descriptiva**, por
decisión de arquitectura (integridad ante auditoría):
- **Reglas vigentes** (con `vigencia_desde/hasta`): dictámenes reproducibles y
  citables.
- **Estadística**: frecuencias reales con **suavizado de Laplace**
  `(exitos+1)/(ocurrencias+2)` — nunca reporta 100% con 1 caso.
- **Probabilidades siempre calculadas**: "POR REGLA VIGENTE" (1.0 si es el único
  faltante) o "histórica VALIDADA" (frecuencia con casos). Jamás inventadas.
- **El copiloto (`preguntar`)** hace **detección de intención por palabras clave** (con
  normalización de acentos), no comprensión de lenguaje por modelo. Devuelve respuestas
  **plantilladas con datos reales**, siempre con evidencia/indicadores/confianza/
  recomendaciones. "Nunca opiniones."
- **OCR (AG004)**: PLANEADO, no implementado (Fase 3 de la hoja de ruta). Requiere una
  decisión pendiente: Tesseract local vs. reutilizar la lectura de documentos del
  producto hermano "Motor de Glosas".

**Nota de alcance:** el producto hermano **Motor de Glosas** (`app/`, en el mismo
repositorio, otro módulo) **sí** usa un LLM (Groq) para redactar respuestas a glosas.
Eso **no forma parte de HOSPIAI** ni de este desarrollo; se menciona solo para evitar
confusión al consolidar el repositorio.

---

## 9. Automatizaciones

- **`corrida_diaria.ps1`**: automatiza el día completo (índice → radicador → directores
  → conocimiento → indicadores → paneles → "buenos días"; + `mejora` los viernes con
  `if (Get-Date).DayOfWeek -eq 'Friday'`). Genera CSV/XLSX/HTML en el Escritorio y logs
  en `data/logs/`.
- **Programación**: `schtasks /Create /TN "HOSPIAI corrida diaria" /SC DAILY /ST 06:00
  /TR "powershell -ExecutionPolicy Bypass -File ...\corrida_diaria.ps1"` — el panel
  amanece actualizado sin intervención.
- **Índice incremental / vigilante**: `hospiai_indexador.py vigilar --cada 300` (rescan
  en bucle; "watcher" correcto para discos de red donde los eventos de Windows no son
  confiables).
- **Cola de misiones + Supervisor**: automatiza la ejecución de agentes respetando
  dependencias, reintentos con backoff y políticas. Las misiones de escritura/RPA
  quedan retenidas hasta aprobación humana.

---

## 10. Archivos creados/modificados en esta línea de trabajo

> Lista consolidada. "N" = creado nuevo, "M" = modificado.

**Código (tools/)**
- N `hospiai_db.py`, `hospiai_sdk.py`, `hospiai_agentes.py`, `hospiai_indexador.py`,
  `hospiai_documento.py`, `hospiai_semantica.py`, `hospiai_supervisor.py`,
  `hospiai_directores.py`, `hospiai_conocimiento.py`, `hospiai_operacion.py`,
  `hospiai_comando.py`, `hospiai_gobernanza.py`, `hospiai_api.py`, `hospiai_dsl.py`,
  `hospiai.py`, `hospiai_panel_ejecutivo.py`, `hospiai_rpa.py`, `corrida_diaria.ps1`.
- M `radicar_facturacion.py`: `analizar_ruta` + `_es_responsable` (+stoplist);
  `cargar_reglas` con vigencias; `indexar_soportes_desde_db` + `--soportes-db` +
  autodetección de `data/indices/*.db`; hook de persistencia con catálogo; columnas
  `responsable`/`lote`/`soportes_clinicos` en el reporte; `_clave_factura_en` con
  fallback por carpeta; `EQUIVALENCIAS_SOPORTE_DEFAULT`.

**Datos (data/)**
- N `agentes.json` (33 agentes con `justificacion_operativa` en los de Fase 3+),
  `reglas_radicacion.json`, `causas_raiz.json`, `esfuerzos.json`, `politicas.json`,
  `artefactos_huellas.json`, `ejemplo_reglas.hospiai`, `ontologias/*` (5),
  `golden/casos.json`.
- M `perfiles_radicacion.json` (campos plazo/periodicidad).

**Pruebas (tests/test_tools/)**
- N `test_hospiai.py`, `test_hospiai_sdk.py`, `test_hospiai_semantica.py`,
  `test_hospiai_gobernanza.py`, `test_hospiai_supervisor.py`, `test_hospiai_directores.py`,
  `test_hospiai_indexador.py`, `test_hospiai_documento.py`, `test_hospiai_conocimiento.py`,
  `test_hospiai_operacion.py`, `test_hospiai_comando.py`.
- M `test_radicar_facturacion.py` (89 casos; parcheados con `--sin-db`).

**Documentación (docs/ + raíz)**
- N `ARQUITECTURA_HOSPIAI.md`, `ACTA_LINEA_BASE.md`, `MANUAL_USUARIO.md`,
  `MANUAL_TECNICO.md`, `GUION_VIDEO_DEMO.md`, `SEGUIMIENTO_SEMANAL.md`, este documento.
- N/M `BITACORA.md` (memoria común), `CLAUDE.md` (instrucciones del repo).

---

## 11. Dependencias nuevas

**Ninguna en tiempo de ejecución.** HOSPIAI corre con Python 3.11+ y **solo librería
estándar**. `openpyxl` es opcional (solo XLSX) y ya existía en el repo.

*(Contexto: en el sandbox de desarrollo se instalaron `fastapi`, `httpx`, `sqlalchemy`,
etc. para poder correr la suite de pruebas del producto hermano Motor de Glosas —
`tests/test_api/`, `tests/test_services/` —, pero eso **no** es dependencia de HOSPIAI.)*

---

## 12. Configuración

- **Variables de entorno**: HOSPIAI no requiere ninguna propia. `corrida_diaria.ps1`
  usa `$env:USERPROFILE` (Escritorio) y acepta `$Origen` / `$Raices` como parámetros;
  `$SOPORTES_ROOT` opcional para el radicador.
- **Archivos de configuración** (`data/`): `agentes.json`, `politicas.json`,
  `reglas_radicacion.json`, `perfiles_radicacion.json`, `causas_raiz.json`,
  `esfuerzos.json`, ontologías. **Editables por el área sin programar.**
- **Parámetros de umbral (en código)**: `UMBRAL_VALIDACION_N=3`,
  `UMBRAL_VALIDACION_CONF=0.6` (Curator); pesos y escala del HOS (`_PESOS_HOS`,
  `_ESCALA_HOS`); LOTE=5000 (indexador); umbral concentración 60% (RootCause).
- **Tokens / credenciales**: **ninguno**. HOSPIAI no accede a portales ni a APIs
  externas. (La radicación en portales — RPA — está retenida por política y requiere
  autorización de gerencia/TI.)
- **Rutas del entorno de producción**: repo en `C:\Users\cartera\motor-glosas-hus`;
  servidores `Y:\` (soportes clínicos), `Z:\SERVIDOR GLOSAS`, `X:\SERVIDOR RADICACION\
  2. SINAC SC SAS - 2026`; origen FE `\\172.16.32.83\factura_electronica_net22\
  202606\FACTURAS_SALUD` (el segmento `202606` = mes; cambiar por mes a radicar).

---

## 13. Riesgos al integrar

| Riesgo | Cómo se manifiesta | Mitigación |
|---|---|---|
| **`data/` está en `.gitignore`** | Los JSON de configuración no se versionan por defecto | Se agregan con `git add -f`; verificar que `agentes.json`, `causas_raiz.json`, `esfuerzos.json`, `politicas.json`, ontologías y golden queden en el repo principal. |
| **Colisión de `hospiai.db`** | La base real del área NO debe subirse ni sobrescribirse | Mantener `data/hospiai.db` y `data/indices/` fuera de git; nunca incluirlos en paquetes. |
| **Migración de esquema** | Una base vieja con código nuevo | Es segura: `abrir()` aplica `CREATE TABLE IF NOT EXISTS` + migraciones al abrir. |
| **Conflicto con el Motor de Glosas** | Ambos módulos en el mismo repo | HOSPIAI vive **solo en `tools/` + `data/` + `tests/test_tools/`**; no toca `app/`. Fronteras limpias. |
| **CI** | Push a `claude/**` corre ruff + pytest (app + tools) + pip-audit | Las pruebas de la app requieren sus dependencias; las de HOSPIAI son stdlib. Mantener ambos suites verdes. |
| **Rama local desactualizada** | Comandos "no existen" tras un pull incompleto | Verificar `git log` = tip esperado; el go-live real falló por esto (rama 18 commits atrás). |
| **Índice no construido** | `oportunidades` no distingue "asociar" de "conseguir" | Correr `hospiai_indexador.py indexar` antes de confiar en el split (ver §15). |

---

## 14. Dependencias con otros módulos

### Qué necesita HOSPIAI
- **`radicar_facturacion.py`** (el motor): HOSPIAI lo envuelve como agentes (AG005–AG007)
  y reutiliza `clasificar_soporte`, `normalizar_factura`, `analizar_ruta`,
  `EQUIVALENCIAS_SOPORTE_DEFAULT`. Es la dependencia interna más fuerte.
- **Los shares del hospital** (Y:/Z:/X: y el origen FE): solo lectura.

### Qué usa a HOSPIAI
- La **corrida diaria** y el área (CLI + paneles).
- La **API** es el punto de integración para futuros HIS/ERP/BI.

### Relaciones internas (orden de dependencia)
`hospiai_comando` → `hospiai_operacion` → `hospiai_conocimiento` → `hospiai_directores`
→ `hospiai_db` (+ `hospiai_indexador`/`hospiai_documento` para el índice). Todos sobre
`hospiai_sdk`. Regla: **Analytics/Intelligence dependen de Core+Knowledge+Rules; nunca
al revés.** El producto hermano **Motor de Glosas (`app/`) es independiente**;
comparten repositorio y la posible futura reutilización de su lectura de documentos
para el OCR.

---

## 15. Pendientes, mejoras previstas y errores conocidos

### Sin terminar / bloqueado en producción
- **Índice permanente no construido** en el equipo del área (`indexador estado` → "Sin
  bases todavía"). Consecuencia: `oportunidades` marca todo como "Conseguir" porque no
  tiene índice contra el cual detectar "Asociar". **Acción decisiva pendiente**: correr
  `indexar` sobre los 3 servidores y re-correr `oportunidades` para saber si hay HEV ya
  escaneadas (recuperación gratis) o si es trabajo de escaneo.
- **Etiqueta `v1.0.0` sin subir**: el proxy de la sesión no empuja tags; queda para
  crearla desde el equipo del área (apunta al commit `268af2f`).
- **Merge a la rama principal no hecho**: HOSPIAI vive en `claude/radicador-share-real`;
  el PR #135 (draft) está abierto. La integración "permanente" a `main` quedó pendiente
  (hubo un intento de merge con conflictos que se abortó con backup
  `backup-motor-glosas-local`).

### Mejoras previstas (hoja de ruta)
- **OCR (AG004)** — leer el contenido de los PDFs (paciente, fechas, firmas): habilita
  dpi/legibilidad y coherencia clínica. Requiere decidir Tesseract vs. Motor de Glosas.
- **Historial de glosas/pagos**: al cargarlo se activan los componentes del HOS hoy
  excluidos (tiempo de radicación, devoluciones, recuperación), la demora del gemelo
  EPS y el "valor perdido".
- **Memoria Institucional real**: se llena con varias corridas; hoy arranca vacía.
- **"Doctor" de arranque** (Sprint 5 propuesto, no construido): un preflight que valida
  entorno (shares montados, disco, rutas) antes de correr. Justificado por el go-live:
  el 100% de la fricción fue de entorno, no de código.
- **Migración de agentes legacy** (AG005–AG007) al SDK.

### Errores/limitaciones conocidas
- **SOAT/FURIPS** no cruzan (el nombre no trae el número de factura).
- **Catálogo incompleto**: ~16–29 facturas quedan ENTIDAD_NO_RESUELTA (pagador sin
  ficha) — es configuración, quick-win de alto retorno ($488–551 M).
- **Diccionario de siglas**: los significados oficiales ADRES están; falta validar los
  usos internos del HUS con el área.

---

## 16. Recomendaciones para fusionarlo al proyecto principal

**Paso a paso, sin perder funcionalidades:**
1. **Traer la rama completa**: integrar `claude/radicador-share-real` (tip `268af2f`+;
   ver PR #135). Si se hace por merge, para los archivos de HOSPIAI (`tools/`,
   `tests/test_tools/`, `data/*.json`, `docs/`, `BITACORA.md`) quedarse con **la versión
   de esta rama** (es la nueva y probada); para `app/` y `tests/test_api/`, con la del
   `main` — **salvo** dos tests del calendario (`test_heatmap_actividad.py`,
   `test_por_dia_semana.py`) donde esta rama trae la corrección de fechas fijas.
2. **Versionar la configuración**: `git add -f data/agentes.json data/causas_raiz.json
   data/esfuerzos.json data/politicas.json data/reglas_radicacion.json
   data/perfiles_radicacion.json data/ejemplo_reglas.hospiai data/artefactos_huellas.json
   data/ontologias data/golden`.
3. **Excluir datos reales**: confirmar que `data/hospiai.db`, `data/indices/`,
   `data/logs/`, `data/informes/` NO entran (siguen en `.gitignore`).
4. **Verificar**: `py -m pytest tests/test_tools/ -q` (251 verdes) + `ruff check
   --select F,W6` + `ruff format --check`. Y la suite de la app aparte.
5. **Etiquetar** `v1.0.0` en el commit integrado.
6. **Fronteras**: mantener HOSPIAI confinado a `tools/`+`data/`+`tests/test_tools/`+
   `docs/`. No mezclar con `app/`.
7. **Despliegue offline** (documentado por el go-live real): si el equipo del área no
   llega a GitHub (firewall bloquea el 443), se entrega un ZIP con `tools/` + `data/*.json`
   (sin `hospiai.db`/`indices`) y se extrae con `Expand-Archive -Force` sobre la carpeta
   del proyecto. La base y el índice del área quedan intactos (no van en el ZIP).

---

## 17. Resumen ejecutivo (para el próximo desarrollador)

**Qué es:** una plataforma multi-agente en **Python puro (stdlib)**, sin frontend web ni
LLM, que audita las facturas del hospital, cruza sus soportes, explica cada dictamen con
su norma y actúa como copiloto operacional (llega cada mañana con las decisiones del
día). Corre en el equipo del área, cero infraestructura, **solo lectura** sobre los
servidores.

**Lo esencial para mantenerlo:**
- **Todo gira alrededor de `data/hospiai.db`** (Expediente Digital). `hospiai_db.abrir()`
  migra la base sola al abrir.
- **33 agentes (AG001–AG033)** bajo un contrato único (`hospiai_sdk.Agente`); se registran
  en `data/agentes.json` **y** en `registro_con_implementaciones()`. Nunca se llaman entre
  sí (cola de misiones). El Supervisor consume el Registro, no las clases.
- **Reglas y políticas son datos** (`data/*.json`), editables sin programar.
- **Cinco reglas de integridad no negociables** (con pruebas que las exigen): solo
  lectura; nada de números inventados (Laplace, NULL con razón, EXACTO vs ESTIMACIÓN);
  ningún agente aprende solo (todo por la Memoria + Curator); ningún agente lee PDFs
  (solo el Document Profile); ningún agente nuevo sin las 5 preguntas de la "regla de
  oro" en su ficha.
- **La prioridad del proyecto es impacto operativo, no más agentes.** El desarrollo está
  **congelado**: la etapa actual es medir (Entrega 2) contra la **línea base** del
  23-jul-2026: **12.523 facturas, 7.840 LISTAS (62,6%), $38.646 M listos**, con la
  palanca de los HEV ($1.245–1.256 M → llevaría a 88,8%).
- **Calidad**: `py -m pytest tests/test_tools/ -q` (251) + `ruff`. Golden dataset como
  red de regresión.
- **Memoria del proyecto**: leer `BITACORA.md` (qué se hizo/pendiente) y
  `docs/ARQUITECTURA_HOSPIAI.md` (visión y hoja de ruta) antes de tocar nada.

**Decisiones y descartes clave (contexto histórico):**
- Se **descartó** el índice en `.txt` (`idx_soportes_2026.txt`) por no servir en
  producción (se colgaba, sin incremental) → **índice permanente SQLite por servidor**.
- El cruce pasó a tomar el número de factura de la **carpeta contenedora** (antes solo
  del nombre del archivo, y se perdían soportes).
- El "grafo de conocimiento" se implementó como **vistas + export JSON** (no un motor de
  grafos dedicado) y el "bus de eventos" como la tabla `eventos`+`corridas` — para
  **evitar sobreingeniería** con un solo nodo/equipo.
- Se **difirieron** el agente conversacional y la predicción ML por decisión explícita:
  "primero datos, después modelos".
- El "ranking de EPS a llamar" se cambió de ordenar por número de folios a **ordenar por
  dinero detenido** (corrección hecha durante las pruebas de la Fase 4).
- La radicación automática en portales (RPA) existe como **interfaz sin adaptador**,
  retenida por política hasta autorización de gerencia/TI.

*Documento de entrega técnica — HOSPIAI v1.0. Reconstruido a partir del desarrollo
completo de esta línea de trabajo. ESE Hospital Universitario de Santander.*
