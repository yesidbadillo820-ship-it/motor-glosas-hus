# 📓 Bitácora del proyecto — Cuentas Médicas y Cartera · ESE HUS

> **Memoria común de trabajo.** Este archivo es el control central de todo lo que
> se ha hecho, lo que falta y lo que sigue. Sirve para que cualquier sesión de
> trabajo (cualquier chat de Claude Code) retome el hilo sin perder nada.

**Cómo se usa:**
- **Al empezar el día / una sesión:** leer esta bitácora para saber en qué punto vamos.
- **Al terminar:** anotar abajo, con la fecha, lo que se hizo, lo que quedó pendiente y lo que sigue mañana.

**Última actualización:** 22 de julio de 2026

---

## 🎯 Qué es este proyecto

Son dos herramientas al servicio del área de **Cuentas Médicas y Cartera** del Hospital Universitario de Santander:

1. **Motor de Glosas** — una aplicación que redacta automáticamente las respuestas a las glosas que ponen las EPS, con base en la normativa colombiana de salud. Es la base del proyecto (se viene construyendo desde abril de 2026).

2. **Suite de Radicación y Cartera** — el trabajo más reciente (junio–julio de 2026): un conjunto de herramientas que revisan las facturas antes de radicarlas ante las EPS, verifican que tengan todos sus soportes, dicen qué le falta a cada una y dónde está, y permiten controlar el estado de la cartera (radicado, glosado, pagado y saldo).

> ⚠️ **Garantía de seguridad (importante para auditoría):** todas las herramientas
> de radicación funcionan en modo **solo lectura**. No modifican, mueven ni borran
> ningún archivo o carpeta del sistema. Únicamente leen la información y generan
> reportes nuevos. Cero riesgo para los soportes originales.

---

## 🗓️ Lo que se ha hecho (por fecha)

### Abril – junio de 2026 · Motor de Glosas (la base)
Se construyó la aplicación que responde glosas médicas de forma automática: detección de glosas fuera de plazo, plantillas por tipo de glosa (tarifa, soportes, autorización, cobertura, pertinencia), cálculo de días hábiles con el calendario de festivos, gestión de contratos y tarifas de las EPS, exportación a Excel institucional y un marco normativo completo. Durante junio se hicieron numerosas rondas de mejora y corrección para elevar la calidad de las respuestas y afinar la detección de la EPS y de los códigos (CUPS, SOAT, medicamentos).

### 24 de junio de 2026 · Nace el motor de radicación de facturas
Se creó la herramienta que revisa automáticamente las facturas electrónicas y sus soportes, las clasifica (lista para radicar / le falta algo / hay que revisar) e identifica la EPS que debe pagar. Se le enseñó a leer las carpetas reales del hospital (factura electrónica de la DIAN y el escaneo), a reconocer los RIPS, el CUV y los documentos de la DIAN, y a reconocer más de una docena de pagadores por su razón social (NUEVA EPS y otros).

### 25 de junio de 2026 · Más entidades y el cruce de soportes
Se agregó la Regional de Aseguramiento N°5 y el estado "Particular" (pacientes que no son de ninguna EPS). Lo más importante: se creó el **cruce con los soportes clínicos** (epicrisis, evolución, urgencias, órdenes) que viven en discos aparte, para completar automáticamente las facturas que quedaban "en revisión".

### 30 de junio de 2026 · Cobertura ampliada, tablero y explorador
- **Radicador:** el cruce pasó a aceptar varias carpetas de soportes a la vez (están repartidos por mes) y a poder leer un listado pre-armado para no recorrer la red cada vez. Se agregó la Unión Temporal Salud Integral MAISFEN.
- **Tablero de Radicación y Cartera:** una página que muestra el radicado, glosado, pagado y saldo por EPS, con alertas de vencimiento, comparativo mensual y detalle por factura.
- **Explorador de Radicación:** un buscador para encontrar cada factura, ver qué le falta y en qué carpeta está, con una ficha de verificación factura por factura y el nombre del pagador cuando la EPS no se reconoce.

### 1 de julio de 2026 · Cruce por carpeta y diagnóstico
Se corrigió el cruce para tomar el número de factura de la **carpeta que la contiene** (antes solo miraba el nombre del archivo, y muchos soportes se perdían). El resumen ahora informa cuántas facturas recibieron soportes de verdad. Se creó además una herramienta de **diagnóstico** que verifica en segundos si el cruce está funcionando y por qué una factura no queda lista.

### 2 de julio de 2026 · Robustez y optimización
Se hizo la herramienta tolerante a los distintos formatos de archivo de Windows. Con apoyo de un segundo modelo de revisión (todo verificado y probado), se corrigieron varios errores finos y se optimizó el motor para procesar decenas de miles de archivos mucho más rápido. **89 pruebas automáticas** respaldan cada cálculo.

### 22 de julio de 2026 · Medición de impacto, informe para gerencia y hoja de ruta
- Se midió el resultado sobre el lote real de junio (**12.523 facturas**): al cruzar los soportes de todos los meses, las facturas listas para radicar pasaron de **42% a 49% (+961 facturas)**, y el cruce completó automáticamente **6.328 facturas** con 32.866 soportes.
- Se preparó un **informe ejecutivo** para socializar ante gerencia, comparando el proceso anterior (revisión manual) con el actual (motor automatizado).
- Se creó **esta bitácora** como memoria común del proyecto.
- Se corrigieron **2 pruebas automáticas del Motor de Glosas** que fallaban solas por el paso del calendario (usaban fechas fijas de abril que quedaron fuera de la ventana de 90 días). No era un error del trabajo de radicación.
- Se recibió y adoptó la **especificación del sistema completo** (ver "Norte del proyecto" abajo): la visión de un auditor inteligente de cuentas médicas de punta a punta. Se hizo el mapa de qué partes ya existen y cuáles siguen.
- Se definió la **arquitectura definitiva de la plataforma: HOSPIAI** (Sistema Operativo Inteligente de Cuentas Médicas). El proyecto deja de ser una herramienta y pasa a ser una plataforma de agentes organizados en 6 dominios, con expediente digital, catálogo institucional, motor de reglas, grafo de conocimiento y orquestador. Documento completo: `docs/ARQUITECTURA_HOSPIAI.md`. Todo lo ya construido se convierte en los primeros agentes (no se bota nada).
- **Se construyó la FASE 1 — FUNDACIÓN de HOSPIAI** (aprobada y entregada el mismo día):
  - **Expediente Digital** (`data/hospiai.db`): cada corrida del motor queda guardada — expedientes, documentos vistos, hallazgos con la regla que los sustenta, y eventos con fecha y versión. Aunque cambie el código, el historial no se pierde. El CSV/XLSX de siempre siguen saliendo igual.
  - **Reglas como datos** (`data/reglas_radicacion.json`): qué soporte exige cada tipo de atención, con su fuente normativa (Res. 2284/2023). El área puede editarlas sin programar y cada corrida registra qué versión usó.
  - **Analizador de ruta completo**: ahora el motor lee de la ruta del share el **responsable** (funcionario) y el **lote de envío**, y los muestra en el reporte, el resumen y el panel — primeros indicadores por funcionario (Dominio 5).
  - **Consola y panel de HOSPIAI** (`tools/hospiai.py`): resumen del expediente en pantalla y panel HTML que lee de la base.
  - **Corrida diaria** (`tools/corrida_diaria.ps1`) lista para programar en Windows + **guía de instalación y operación** (`tools/README_hospiai.md`).
  - Todo **solo lectura** sobre los shares; **100 pruebas automáticas** en verde.
- **Revisión de arquitectura y FASE 1.5 — Arquitectura Cognitiva (entrega 1):** tras una revisión formal se decidió construir la capa de conocimiento ANTES del OCR. Se entregó el mismo día:
  - **Vigencias normativas:** cada regla puede tener "desde/hasta"; el motor aplica la regla correcta según la fecha (si cambia la norma, conviven las dos versiones).
  - **Catálogo institucional:** la ficha de cada pagador (NIT, régimen, plataforma, plazo de radicación, periodicidad) ahora vive en la base (`pagadores` + `contratos`) y se consulta con `py tools\hospiai.py catalogo`. Los plazos los debe suministrar el área.
  - **Motor de Evidencias:** cada hallazgo guarda su evidencia observada y su nivel de confianza, y se consulta la cadena completa (hallazgo → regla → norma → evidencia) con `py tools\hospiai.py evidencia HUS528043` — la vista con la que un auditor defiende un dictamen.
  - **Grafo de conocimiento consultable:** vistas en la base + exportación a JSON (`py tools\hospiai.py grafo`) con pagadores, expedientes, responsables, lotes y reglas incumplidas.
  - **Memoria institucional:** la tabla de glosas ahora guarda solución aplicada, aprendizaje y tiempo — el insumo del aprendizaje continuo.
  - **105 pruebas automáticas** en verde. La base de la Fase 1 se migra sola (sin perder datos).
- **FASE 1.6 — Plataforma de Agentes (entrega 1):** HOSPIAI dejó de ser módulos y pasó a ser un sistema multiagente:
  - **Contrato único de agente** (el "SDK"): todos los agentes tienen identidad (AG001, AG002…), versión, dominio, capacidades, y devuelven exactamente el mismo formato de resultado (con confianza, evidencias y duración). Un agente que falla no tumba la plataforma.
  - **Registro Central de Agentes** (`data/agentes.json` + `py tools\hospiai.py agentes`): la plataforma sabe qué agentes existen, cuáles están activos, en mantenimiento o planeados, y qué sabe hacer cada uno. El futuro Supervisor consultará este registro, nunca el código.
  - **Misiones:** los agentes no se llaman entre sí — publican misiones en una cola guardada en la base (con prioridad y reintentos). `py tools\hospiai.py misiones` muestra la cola.
  - **Primeros agentes reales:** el Analizador de Ruta (AG002) y el Clasificador Documental (AG003) ya corren con el contrato nuevo.
  - **Lenguaje propio de reglas (DSL):** un auditor puede escribir "REGLA … SI SERVICIO = CIRUGIA … REQUIERE DQX RAN EPI … SI FALTA BLOQUEAR … FUENTE Resolución 2284" en un archivo de texto y compilarlo al motor con un comando — sin programar. Con verificación que señala línea y motivo de cualquier error. Ejemplo listo en `data/ejemplo_reglas.hospiai` (paridad probada con las reglas vigentes).
  - **124 pruebas automáticas** en verde.
- **HOSPIAI KNOWLEDGE LAYER (entrega 1) — la capa de conocimiento:** la plataforma dejó de leer códigos y empezó a entenderlos:
  - **Motor Semántico** (`py tools\hospiai_semantica.py explicar K35`): responde "K35 = apendicitis aguda → atención quirúrgica → se esperan descripción quirúrgica, registro anestésico y epicrisis". Lo mismo para documentos: "DQX = descripción quirúrgica, documento clínico, acompañada del registro anestésico, debe llevar paciente, fecha y firma (Res. 1995/1999)".
  - **Cinco ontologías** en `data/ontologias/`: documental (27 soportes con clase, relaciones y atributos), clínica (tipos de atención → soportes; semilla verificada), CUPS (**158 procedimientos oficiales Res. 2641/2025 reutilizados del Motor de Glosas** — no se inventó ni un código), normativa (norma → exigencia → documento) y contractual (esquema para que el área cargue autorizaciones por contrato).
  - **Cargadores de tablas oficiales:** `cargar-cie10` (para la tabla CIE-10 completa del hospital) e `importar-cups`. Principio: los códigos clínicos jamás se inventan — solo se cargan de fuente oficial.
  - **Nuevo agente AG011 (MotorSemantico)** registrado y probado en el SDK.
  - **Mapa de productos** definido en la arquitectura (Core / Knowledge / Rules / Intelligence / RPA / Analytics) con fronteras trazadas desde ya, para que otro hospital pueda adoptar módulos sueltos en el futuro.
  - **136 pruebas automáticas** en verde.
- **FASE 1.7 — ARCHITECTURE GOVERNANCE (entrega 1):** el sistema que gobierna la propia plataforma, para evolucionar años sin perder trazabilidad ni calidad:
  - **Registro único de artefactos** (`py tools\hospiai_gobernanza.py artefactos`): todo es un artefacto versionado (motor, reglas, catálogo, ontologías, agentes, SDK) con huella digital que **detecta cambios sin subir de versión** (deriva silenciosa).
  - **Contratos de compatibilidad** (`compatibilidad`): se verifica en vivo que cada agente cumpla el contrato del SDK — si un cambio del núcleo rompiera un agente, se detecta solo (y corre en las pruebas automáticas).
  - **Banco de casos de referencia** (`golden`): 10 expedientes sintéticos representativos (cirugía, urgencias, hospitalización, sin RIPS, sin CUV…); en cada cambio se corre el motor real sobre ellos y se compara el resultado — la red que evita regresiones funcionales. *Al repo solo entran casos sintéticos; los reales anonimizados se agregan en copias locales.*
  - **Registros de Decisión** (`py tools\hospiai.py decision HUS…`): cada dictamen queda como objeto auditable DEC-xxxxxx con motivo, regla, norma y las versiones exactas del motor y las reglas que lo produjeron.
  - **API interna estable** (`py tools\hospiai_api.py servir`): el contrato de consulta (expedientes, decisiones, evidencias, agentes, ontología, salud) con el que mañana se integrarán HIS/ERP/BI — solo lectura, solo en el equipo local.
  - **Observabilidad** (`salud`): misiones pendientes/fallidas, reintentos, tiempos y corridas — para ver cuándo algo se degrada.
  - **146 pruebas automáticas** en verde.
- **FASE 2 — IMPLEMENTACIÓN FUNCIONAL · Sprint 1 (AG010 Supervisor) ENTREGADO:** por directiva, se terminó la etapa de arquitectura y empezó la de agentes trabajando. El Supervisor quedó **funcionando**:
  - **Seis piezas separadas** (`tools/hospiai_supervisor.py`): *Scheduler* (prioridad ALTA primero, dependencias entre misiones, backoff), *Dispatcher* (elige el agente SOLO por el Registro Central y compatibilidad — jamás conoce clases), *Retry Manager* (error → reintento con espera creciente → error definitivo con Registro de Decisión; **nada queda bloqueado**), *Policy Engine* (las políticas viven en `data/politicas.json`, no en código: topes de concurrencia, horario laboral, y RPA/radicación **retenidas hasta aprobación humana**), *Mission Logger* (cada transición PENDIENTE→ASIGNADA→EJECUTANDO→FINALIZADA/REINTENTO/ERROR queda persistida) y el ciclo que las une.
  - Probado **end-to-end con agentes reales**: `py tools\hospiai_supervisor.py correr` drena la cola; `estado` muestra el log de transiciones.
  - **Interfaz RPA lista sin adaptadores** (`tools/hospiai_rpa.py`, Prioridad 5): el contrato login/subir/confirmar/descargar/cerrar existe; registrar un adaptador real será un acto deliberado de la Fase 5 con autorización de gerencia/TI.
  - AG010 pasó a **ACTIVO** en el registro. **159 pruebas automáticas** en verde.
  - Sprints siguientes de la fase: 2) migrar los agentes legacy al SDK, 3) semántica→dictamen, 4) OCR clínico, 5) OCR→expediente, 6) **primera corrida real de los 12.523 expedientes** (requiere el índice de soportes en el equipo del área).
- **FASE 2 · Sprint 2A+2B — LOS DIRECTORES Y EL PANEL EJECUTIVO (entregados):** la plataforma ya convierte los datos en decisiones:
  - **AG012 Director de Auditoría** (`py tools\hospiai_directores.py informe`): al final de cada corrida genera el informe gerencial completo — resumen ejecutivo, **riesgo financiero explicado por causa**, ranking por responsable, riesgo por entidad con su **causa principal** (ASMET → HEV), hallazgos **valorizados en pesos con su norma**, **predicción estadística** ("si se corrige HEV suben N facturas por $X" — cuenta las facturas donde eso es lo ÚNICO que falta) y **recomendaciones priorizadas por impacto económico**. Queda guardado en `data/informes/`.
  - **AG013 Director Operativo** (`tareas`): convierte el informe en las tareas del día por funcionario, como misiones TAREA_HUMANA **retenidas por política** hasta que una persona las tome — con el valor en juego de cada una.
  - **AG014 Director Gerencial** (`caja`): responde en dinero las 5 preguntas de gerencia (radicable hoy, detenido, recuperable por causa, funcionario con mayor retorno, EPS que frena caja).
  - **AG015 Aprendizaje Institucional** (`aprendizaje`): registra cada transición entre corridas (REVISAR → LISTA): qué cambió, por qué, qué aprendimos — la memoria del hospital, sin duplicados.
  - **Panel Ejecutivo** (`py tools\hospiai_panel_ejecutivo.py`): 6 vistas (Estado General, Riesgo Financiero, Responsables, EPS, Hallazgos, Predicción) + las **6 preguntas de aceptación respondidas de frente**, alimentado **exclusivamente desde la API** (el módulo no toca la base — hay una prueba que lo verifica).
  - Nuevos endpoints de la API: `/informe`, `/caja`, `/tareas`. **165 pruebas automáticas** en verde.
  - ⚠ Los números del panel serán los reales de los 12.523 en cuanto se corra la primera corrida (índice de soportes pendiente en el equipo del área).
- **AG001 — SERVICIO DE INDEXACIÓN PERMANENTE (reemplaza el archivo de texto):** por directiva, el índice dejó de ser un `.txt` gigante y pasó a ser un servicio:
  - **Bases SQLite por servidor** (`data\indices\indice_y.db`, `indice_z.db`, `indice_x.db`): si un servidor falla, los demás siguen sirviendo. La búsqueda une todas (vista global).
  - **Guardado inmediato**: cada archivo encontrado se inserta al momento (lotes de 5.000) — nunca se espera al final. **Progreso en tiempo real**: conteo, velocidad, minutos y % con tiempo restante en las pasadas siguientes.
  - **Indexación incremental**: después de la primera vez solo se revisa qué cambió (fechas/tamaños) — segundos si no hay novedades. Lo borrado queda marcado AUSENTE (no se pierde el historial).
  - **Búsqueda instantánea**: `py tools\hospiai_indexador.py buscar HUS528043` → milisegundos, con tipo de soporte, servidor y estado.
  - **Vigilante** (`vigilar --cada 300`): rescan incremental en bucle — el "watcher" correcto para discos de red, donde los eventos de Windows no son confiables.
  - **El radicador ya lo usa solo**: si existen bases en `data\indices\`, las autodetecta (o `--soportes-db`); el cruce se carga desde SQLite en milisegundos. El `.txt` queda como respaldo de compatibilidad, fuera del flujo diario.
  - `corrida_diaria.ps1` actualizada: 1) índice incremental → 2) radicador → 3) directores → 4) paneles. **174 pruebas automáticas** en verde.
- **FASE 2.1 — DOCUMENT INTELLIGENCE SERVICE (DIS):** AG001 dejó de ser un indexador: es el servicio documental de la plataforma. **El documento dejó de ser un archivo: es un objeto inteligente.**
  - **Fingerprint real** de cada PDF (leyendo su estructura, sin librerías): hash, páginas, autor, productor, fechas del documento, firma digital, texto extraíble, cifrado, rotación. *Honestidad: dpi y % de legibilidad existen en el perfil pero quedan vacíos hasta el OCR (Fase 3) — no se inventan medidas.*
  - **Clasificación con confianza**: token en el nombre 98% · alias reconocido 90% · solo carpeta 50% · sin evidencia 30%.
  - **Calidad A–D/X** por señales verificables: A = válido+texto+firmado · B = con texto · C = escaneo puro (necesitará OCR) · D = sospechoso · X = corrupto/vacío.
  - **Duplicados inteligentes**: exactos (mismo hash → apuntan al canónico) y funcionales (mismo tipo de soporte repetido en la misma factura). El nivel paciente+fecha llega con el OCR.
  - **Timeline** por documento: creado → indexado → perfilado + la historia del expediente (decisiones, hallazgos, eventos).
  - **AG016 Document Curator** (`curar`): corruptos, vacíos, incompletos, duplicados, sin texto, cifrados — detectados ANTES del OCR, con hallazgos en el Expediente.
  - **AG017 Storage Optimizer** (`almacenamiento`): GB por servidor, duplicados recuperables, ausentes, candidatos a archivar (>2 años). Solo informa: mover/borrar es decisión humana.
  - **AG018 Ingesta Inteligente** (`ingesta`): incremental + perfilado inmediato de lo nuevo + evento DOCUMENTO_NUEVO en el Expediente — sin esperar la corrida nocturna.
  - **Criterio de aceptación cumplido**: `py tools\hospiai_documento.py perfil HUS528043` responde el objeto documental completo (clase, calidad, confianza, hash, páginas, texto, firma, duplicado, timeline, expediente). **187 pruebas automáticas** en verde. 18 agentes registrados.

---

## 🧭 NORTE DEL PROYECTO — HOSPIAI

El 22 de julio se definió la **especificación del sistema final** y su
**arquitectura de plataforma: HOSPIAI** (Sistema Operativo Inteligente de
Cuentas Médicas) — un sistema de agentes especializados en 6 dominios (gestión
documental, inteligencia clínica, administrativa, financiera, operacional y
gerencial), sobre un expediente digital, un catálogo institucional, un motor de
reglas con fuente normativa y un grafo de conocimiento. **La arquitectura
completa y su hoja de ruta por fases están en `docs/ARQUITECTURA_HOSPIAI.md`.**
Estado actual de cada parte de la visión:

| Parte de la visión | Estado hoy |
|---|---|
| Explorar el servidor y detectar facturas (Agente 1–2: ruta = año/mes/entidad/lote/factura) | ✅ Construido (motor de radicación); falta solo la vigilancia automática permanente |
| Inventario documental por factura (Agente 3) | ✅ Construido (soportes presentes/faltantes por factura) |
| Diccionario de siglas institucional (Agente 4) | ✅ Construido con el diccionario oficial ADRES; ⚠ falta validar significados con el área |
| Auditor por tipo de servicio: cirugía exige sus soportes, urgencias los suyos… (Agente 6) | ✅ Construido (reglas por servicio del RIPS, configurables por entidad) |
| Calidad de archivos: dañados, vacíos, duplicados, ilegibles (Agente 7) | 🔶 Parcial (duplicados sí; dañados/vacíos/firmas: siguiente paso) |
| Leer el CONTENIDO de los PDF: paciente, fechas, firmas, médico (Agente 5, OCR) | 🔜 Proyecto aparte (el Motor de Glosas ya tiene una base de lectura de documentos) |
| Ficha de cada entidad: NIT, régimen, plataforma, plazos (catálogo de pagadores) | ✅ Construido (25+ entidades); falta plazos y periodicidad por contrato |
| Verificar el cargue y RADICAR automáticamente en las plataformas de las EPS (Capa 4) | 🔴 Requiere decisión de gerencia y TI (credenciales, acceso a portales, marco legal) |
| Tableros e indicadores (Capa 5) | ✅ Construido (tablero de cartera + explorador + informe ejecutivo) |
| Aprendizaje continuo de glosas/devoluciones | 🔜 Futuro (necesita historial de devoluciones cargado) |

> ⚠️ **Regla vigente:** todo lo construido es **solo lectura**. El único punto de
> la visión que rompe esa regla es la radicación automática en portales (Capa 4):
> eso NO se hará sin autorización expresa de gerencia y TI.

---

## ⏳ PENDIENTE (lo que falta)

- [ ] **Terminar la corrida con los soportes de todos los meses.** Armar el listado único de soportes (los 7 meses del disco) y volver a correr el motor, para medir cuánto más baja el grupo "revisar".
- [ ] **Cargar el tablero con datos reales.** Hoy la plantilla de seguimiento está vacía (muestra $0 pagado). Falta ingresar los pagos y glosas reales de al menos las EPS grandes (NUEVA EPS, COOSALUD).
- [ ] **Completar el catálogo de entidades.** Quedan alrededor de 24 facturas cuya EPS pagadora el sistema aún no reconoce ("entidad por resolver"). Falta exportar esa lista desde el explorador y agregar esas entidades.
- [ ] **Soportes de SOAT / tránsito.** Los formularios FURIPS de los accidentes de tránsito no traen el número de factura en el nombre, por lo que no cruzan automáticamente. Es un grupo pequeño que requiere una solución aparte.
- [ ] **Escanear los soportes que faltan.** Parte de las facturas "en revisión" simplemente todavía no tienen sus soportes clínicos escaneados. Esa es una tarea operativa del área; el explorador ya dice cuáles son y qué les falta.
- [ ] **Dejar las mejoras disponibles en forma permanente.** Integrar el trabajo a la versión principal del proyecto para que esté en todas las sesiones, sin importar en qué rama se trabaje.
- [x] ~~HOSPIAI Fase 1 — Fundación~~ **HECHA (22 de julio):** Expediente Digital, reglas declarativas, responsable+lote, consola/panel, corrida diaria y guía.
- [ ] **Estrenar la Fase 1 con datos reales:** correr el motor sobre el lote real (con el índice de soportes) para poblar `data/hospiai.db` por primera vez, y **programar la corrida diaria** en el equipo del área (una línea de `schtasks`; está en `tools/README_hospiai.md`).
- [ ] **Mostrar responsable y lote también en el explorador** (la herramienta del buscador vive en otra rama; el reporte ya trae las columnas).
- [ ] **HOSPIAI Fase 2 (D1/D5):** auditor de calidad de archivos (PDF dañados, vacíos, duplicados de contenido) y tiempos de proceso por expediente.
- [ ] **Validar el diccionario de siglas** con el área (los significados oficiales ADRES ya están en el motor; confirmar los usos internos del HUS).
- [ ] Completar la **ficha de cada pagador**: plazos de radicación, periodicidad y plataforma donde se radica (la tabla `contratos` ya está lista en la base).

---

## 📌 PARA MAÑANA (lo próximo a trabajar)

1. **Estrenar HOSPIAI con el lote real:** `git pull`, armar el índice de soportes (si no está), correr el motor (ya escribe el Expediente Digital solo) y ver `py tools\hospiai.py resumen` + el panel. Anotar aquí el nuevo porcentaje de listas y los primeros indicadores por responsable.
2. **Programar la corrida diaria** con la línea de `schtasks` de la guía (`tools/README_hospiai.md`), para que el panel amanezca actualizado.
3. **Regenerar el explorador y el tablero** con el reporte actualizado.
4. **Revisar la lista de EPS no reconocidas** y agregarlas al catálogo, para bajar el grupo "entidad por resolver".

---

*Bitácora del proyecto de Cuentas Médicas y Cartera — ESE Hospital Universitario de Santander.*
