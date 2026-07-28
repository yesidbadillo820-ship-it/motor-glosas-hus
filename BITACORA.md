# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana). Escrito en lenguaje claro
> para el auditor de cartera del HUS.

**Última actualización:** 28-07-2026

---

## 1) Las patas del proyecto

1. **Motor de Glosas (aplicación web con IA):** recibe las glosas y redacta el
   dictamen de defensa del hospital (cita contrato, tarifas, normativa). Vive en
   la carpeta `app/` y se usa desde el navegador. Incluye además el **módulo de
   Pre-auditoría SINAC** (página `/preauditoria`, nuevo 23-07).
2. **Bots de carga (robots que suben respuestas a las plataformas):**
   - `tools/responder_glosas_coosalud.py` — portal de COOSALUD (vco.ctamedicas.com).
   - `tools/responder_glosas_simed.py` y `tools/cargar_soportes_simed.py` — SIMED (Dispensario Médico).
   - `tools/responder_glosas_dgh.py` — Dinámica Gerencial (programa de escritorio del hospital).
   - Otros: Mutual Ser, FOMAG, radicador de facturación.
3. **Plataforma de conciliación del Dispensario** (`tools/`):
   índice de soportes → expediente por factura → motor de evidencia → hechos
   probados → motor de decisión → piloto (`piloto_conciliacion_dispensario.py`).
4. **Herramientas de apoyo:** armar el Word/PDF de evidencias
   (`tools/evidencias_a_word.py`, `evidencias_a_pdf.py`), notas crédito del
   Dispensario (renombrar, organizar, verificar CUV), tablero de cartera
   (`tools/tablero_cartera.py`).

Guías por plataforma en `docs/`: `CONTEXTO_COOSALUD.md`,
`CONTEXTO_DISPENSARIO_GLOSAS.md`, `CONTEXTO_DISPENSARIO_NOTAS.md`.

---

## 2) Resumen de lo ya hecho (por fecha)

### Abril 2026 — Nace el Motor de Glosas
- **08 al 10-04:** primera versión de la aplicación: análisis de glosas con IA,
  dictámenes con normativa colombiana (Res. 3047/2008, Ley 1438/2011, etc.),
  importación masiva desde Excel, exportación a Excel, seguridad de acceso.
- **13 al 25-04:** la aplicación crece: generación masiva en lote, conciliación
  bilateral con acta y PDF institucional, informe ejecutivo mensual para
  gerencia, catálogo de tarifas pactadas por EPS, homologación Res. 2641/2025,
  exportes con el formato exacto del DGH, pre-análisis automático diario y
  dashboard ejecutivo.
- **26 al 30-04:** panel de administración completo (usuarios, equipos,
  notificaciones), sincronización de soportes desde el servidor del hospital
  (jumpbox) y tarifas FOMAG actualizadas al contrato nuevo.

### Mayo 2026 — Estabilización
- Importación masiva con progreso e historial, auditor forense IA, panel de
  diagnóstico del sistema, y correcciones a partir del uso real diario.
- **21 al 29-05:** primer robot del portal **SIMED** (Dispensario), en ese
  momento para el cargue de notas crédito con validación del CUV.

### Junio 2026 — Nacen los robots de carga
- **11-06:** primera versión del **bot de COOSALUD**: entra al portal, busca cada
  factura, responde las glosas en grupo y captura el pantallazo de cierre como
  evidencia. Ese mismo día nace `evidencias_a_word.py` (une los pantallazos en
  un Word, una factura por página).
- **12 al 19-06:** herramientas de **notas crédito del Dispensario**: renombrar
  y organizar PDFs por carpeta, consolidar, verificar el estado del CUV ante
  MinSalud. Auditoría rápida de pendientes COOSALUD (`verificar_glosas_coosalud.py`).
- **22-06:** mejoras grandes del bot COOSALUD: responder también la pertinencia
  médica (`--incluir-calidad`), cerrar glosas residuales que el Excel no traía
  (`--cerrar-residuales`), buscar el PDF de soporte en carpetas alternativas del
  share. Guías escritas de los bots. Bot SIMED: manejo de ventanas emergentes.
  **Respuesta de glosas Dispensario en SIMED:** lote cerrado completo — 8
  facturas / 24 objeciones en 26,9 minutos con el robot.
- **23 y 24-06:** **cargue DIA 3 JUNIO (COOSALUD):** se cerraron las 118 facturas
  pendientes de la hoja BASE y las 26 de la hoja CALIDAD (4.936 glosas). Dos
  facturas fallaron por un detalle del portal al elegir el código de respuesta;
  se corrigió el bot y cerraron en la segunda pasada.
- **25 y 26-06:** Word de evidencias del **lote 69** (46 de 69 facturas tenían
  pantallazo; 23 quedaron identificadas sin evidencia). Nace `evidencias_a_pdf.py`.
  **Diagnóstico de las 12 facturas pendientes del Lote V2 del Dispensario:** se
  descubrió que el registro estaba equivocado en 6 — cinco que figuraban
  "subidas OK" nunca tuvieron validación del Ministerio (el servicio interno
  de validación estaba caído y guardó el error como si fuera el resultado).
  Se armó la carpeta `PENDIENTES_12` con ficha de estado por factura.
  **Primer lote de respuesta de glosas del Dispensario en SIMED**
  (`respuestas_glosa_INICIAL_DSE_26JUN.xlsx`).
- **30-06:** arranca el **bot de Dinámica Gerencial (DGH)** (muchas iteraciones
  para dominar el programa de escritorio; la ventana de respuesta no se deja
  leer por dentro y hay que operarla por coordenadas de pantalla). **Tablero de
  Radicación y Cartera** (informe HTML con alertas de mora +90 días, exportar a
  Excel). Mejoras al motor IA (rondas 19-22) y set de evaluación de calidad de
  los dictámenes: la calidad del motor pasó de **2,5 a ~9 sobre 10**.

### Julio 2026 — Contratos reales, lotes masivos y cierre de pendientes
- **01 al 03-07:** el motor IA aprende los **contratos reales por EPS**
  (COOSALUD SOAT −15%, FOMAG, Dispensario FF.MM., Famisanar, Aurora, Compensar,
  etc.) — fin del falso "sin contrato pactado". Rondas 23-28 de mejoras.
- **07 y 08-07:** ronda 29 de limpieza y corrección (27 hallazgos de auditoría).
- **10-07:** **cargue DIA 3 JULIO (COOSALUD): 100 de 100 facturas cerradas
  (2.436 glosas)** — incluida una recuperación automática tras un corte de luz
  a mitad del cargue, sin duplicar nada. Se corrigió el bot para que las glosas
  extemporáneas (código RE9502) no exijan soporte PDF (5 facturas que estaban
  trabadas cerraron de una). Se definió la estructura de carpetas por
  mes/día para archivar evidencias y Word. **Informe de efectividad para
  gerencia** (página web con el antes/después). También: **informe de gestión
  del Lote V2 de notas crédito** (`INFORME_GERENCIA.md`, 12 facturas por
  $108,5 millones facturados con comparativo manual vs. automatizado).
- **10 al 21-07 (corridas del auditor):** se analizaron y lanzaron los
  **LOTES 02 (300 fact.), 06 (300), 07 (300) y 08 (75)** de COOSALUD.
  El LOTE 7 llegó primero como listado de objeciones sin respuestas
  (OBJECIONES.xlsx) y fue reemplazado por el consolidado correcto.
  En los lotes 06/07/08 quedaron 37 facturas con la pertinencia médica
  sin responder (el médico aún no la tipificaba).
- **17-07:** informe técnico en Word de los **rechazos CUV de 4 facturas
  conciliadas** (`INFORME_RECHAZOS_CUV.docx`, para enviar al área): 3 rechazadas
  por el Ministerio con código RVC086 ("código de diagnóstico repetido", con el
  campo exacto del RIPS a corregir) y 1 cuya validación nunca corrió (servicio
  interno caído). Incluye el argumento clave: lo que al radicar la factura
  salía como *objeción* se convirtió en *error bloqueante* en la nota crédito.
  Dato: SISTEMAS ya reintentó 2 el 25-06 sin corregir el RIPS y volvió a fallar.
- **22-07:** llegaron las respuestas de pertinencia en 3 archivos
  ("PERTINENCIA (1)", "ok" y "15"). Se detectó que **cada archivo estaba
  incompleto pero se complementaban** entre sí → se fusionaron en
  **CONSOLIDADO_PERTINENCIA_6JULIO_FUSIONADO.xlsx** (37 facturas, 5.736
  glosas, cero sin respuesta, todas RE9901). Quedó listo el comando para
  correrlo. Se creó esta bitácora (fusionando el trabajo de dos chats).

### Julio 2026 — Frente Dispensario: respuesta masiva de glosas en SIMED
(trabajo del chat del bot Dispensario, fusionado a esta bitácora el 23-07)
- **01 y 02-07:** el robot DGH aprendió a llenar la ventana de respuesta por
  coordenadas (modo `--calibrar`). Lote del 1 de julio respondido.
- **06-07:** lote respondido y **subido a SIMED** (65 objeciones / 53 facturas)
  con pantallazos de evidencia.
- **09 y 10-07:** lote grande **subido a SIMED completo: 102 facturas, 225
  objeciones**, verificado al 100% (subida en ~22 minutos).
- **14 y 15-07:** lote del 14-07: **28 facturas, 44 objeciones, $46.016.019
  defendidos**. Respuestas revisadas con verificación adversarial; citas
  normativas corregidas (fuera la Res. 3047/2008 derogada; todo anclado en la
  Res. 2284/2023, el contrato 440-DIGSA/DMBUG-2025 y las Res. de tarifas HUS
  054 y 124 de 2026). El PDF de evidencias debe llamarse **GI-33-5182-2026**.
- **17-07:** lote del 17-07: **58 facturas, 115 objeciones, $87.605.050**
  (verificado con 33 agentes; 8 respuestas corregidas). En el motor: validador
  FURIPS endurecido (22 hallazgos) e informe de baja de cartera (Res. 577/2019).
- **22-07:** se detectaron **3 facturas de junio sin respuesta** (HUS0000518186,
  HUS0000515107, HUS0000515773) → generadas sus respuestas: **38 objeciones,
  $20.054.751** (`respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx`). También
  un consolidado de 116 facturas / 238 objeciones / $94.150.626. Y nació la
  **plataforma de conciliación del Dispensario** (todas con README y pruebas):
  - `tools/organizar_objeciones_dispensario.py` — PDF de AUDITOOL → Excel de
    OBJECIONES para DGH, validando totales.
  - `tools/asistente_conciliacion_dispensario.py` — arma la matriz de evidencia
    por glosa desde los soportes (`Y:\`) y redacta el oficio de respuesta.
  - `tools/indexar_soportes_dispensario.py` — indexa `Y:\` una sola vez (el
    servidor tiene ~2,2 millones de archivos; sin índice se colgaba).
  - `tools/expediente_conciliacion.py` — EXPEDIENTE único por factura (contrato
    287/440, radicado, glosas, soportes, cartera). Probado con el lote real
    (147 expedientes).
  - `tools/motor_evidencia_dispensario.py` — localiza la prueba de cada glosa
    página por página (evidencia fuerte/débil, nunca inventa).
  - `tools/motor_verificacion_dispensario.py` — reglas deterministas: fija los
    HECHOS a probar por glosa, motor de contradicciones, marca *defendible*.
  - `tools/motor_decision_dispensario.py` — califica defendibilidad (0-100%),
    riesgos y acción recomendada (levantar / pedir soporte / aceptar parcial /
    escalar / conciliar).
  - `tools/piloto_conciliacion_dispensario.py` — orquesta el piloto de 5 casos
    (HUS0000446262, HUS0000452150, HUS0000426013, HUS0000455554 + 1 del
    auditor) con métricas y umbrales de aceptación (≥95% con soporte, ≥90% con
    evidencia, 0 levantamientos sin hecho probado, 100% trazables).
  - Diagnóstico del lote de conciliación (147 facturas / 444 glosas): 146/147
    cruzan con cartera (falta HUS0000443525); 372 glosas venían mal marcadas
    "SIN CONTRATO" cuando sí tienen contrato por fecha (342 → 287, 30 → 440).
    Base tarifaria: 287 = SOAT −15%, 440 = SOAT −20%.

**Los números de la operación SIMED (respuesta de glosas Dispensario):**

| Lote | Facturas | Objeciones | Valor defendido | Estado |
|---|---|---|---|---|
| 26 de junio | ~30 | ~40 | — | Subido |
| 1 de julio | ~50 | ~70 | — | Subido |
| 6 de julio | 53 | 65 | — | Subido |
| 9 de julio | 102 | 225 | — | Subido y verificado 100% |
| 14 de julio | 28 | 44 | $46.016.019 | Excel listo — confirmar subida |
| 17 de julio | 58 | 115 | $87.605.050 | Excel listo — confirmar subida |
| Pendientes junio | 3 | 38 | $20.054.751 | Excel listo — subir YA (plazos vencidos) |

### 23-07 — Módulo de Pre-auditoría SINAC
- **23-07:** nace el **módulo de Pre-auditoría SINAC** (rama
  `claude/invoice-audit-bot-qa2koy`, PR #186, página `/preauditoria` de la app
  web), a partir de los archivos guía CONSOLIDADO_PRE_AUDITORIA_2026 y
  OFICIOS_DEVOLUCIONES_CONSECUTIVOS. Qué hace:
  - Registrar el **oficio radicado** por Facturación con **fecha y hora** de
    recibido.
  - Importar el Excel del **consecutivo de DGH** y contar **cuántas facturas
    trae cada número de envío**.
  - Auditar cada factura: **Soportes OK (radicar)** o **Devuelta con motivo**.
    Máximo **3 devoluciones** por factura (la 4.ª se bloquea); cuando la
    factura vuelve corregida queda **SUBSANADA** o **NUEVAMENTE DEVUELTA**.
  - Generar el **oficio de devolución en PDF** con consecutivo SINAC
    (DEV-PRE-AUD-####-AAAA), logo y bloque de firmas, igual al formato del
    Excel de oficios.
  - **Semáforo** del plazo de 3 días hábiles (cuentan desde el día siguiente
    al recibo): verde / amarillo (penúltimo día) / rojo (último) / vencido.
  - **Estadísticas**: auditadas, OK, devueltas, subsanadas, por auditor y
    facturas reincidentes; vista masiva con filtros y vista individual con
    el historial completo de cada factura.
  - 29 pruebas automáticas en verde (`tests/test_api/test_preauditoria.py`).
- **23-07 (tarde):** dos entregas más del mismo frente:
  - El **PDF del oficio de devolución** quedó con el formato exacto de la guía
    del equipo (GUIA_DE_PDF): título "ENTREGA DE NO ACEPTACIONES PARA
    CORRECCION...", subtítulo "OBSERVACIONES DE PREAUDITORÍA PARA SUBSANACIÓN",
    consecutivo y fecha arriba a la derecha y columna OFICIO (radicado FHUS)
    en cada fila.
  - **CONSOLIDADO_PRE_AUDITORIA_2026_INTERACTIVO.xlsx** (entregado por chat,
    NO va al repo porque el DGReport trae datos de pacientes): se escribe el
    número de ENVÍO y se llenan solas F_RECIBIDO, FACTURA, F_FACTURA, VALOR,
    NIT, ENTIDAD y CORREO F.E. Las fuentes las alimenta el auditor pegando
    los reportes de DGH en las hojas RADICACION (radicación de cuentas;
    precargada con 36.765 filas) y DGREPORT (correos de factura electrónica;
    7.231 filas). Si el envío trae varias facturas, se repite el número y
    salen en orden ("2 de 5"). Instrucciones en la hoja LEYENDA.

### 24-07 — Pre-auditoría v2: la aplicación web es el consolidado oficial
- **24-07:** el módulo de pre-auditoría deja de depender del Excel: ahora la
  **aplicación web es el consolidado oficial** (misma rama/PR #186). El auditor
  solo hace 4 cosas y el sistema arma todo:
  1. **Sube la Radicación de Cuentas** (reporte de DGH) → el sistema la guarda
     como fuente (upsert por factura, no duplica; excluye radicaciones
     'Anulado'; se probó con las 36.723 facturas reales del reporte).
  2. **Sube el DGReport** → de ahí sale CORREO F.E. (SI/NO).
  3. **Registra el oficio recibido** (FHUS + fecha/hora).
  4. **Escribe el número de envío** → el sistema crea automáticamente una fila
     por cada factura del envío, autocompletando F_RECIBIDO, F_FACTURA, VALOR,
     NIT, ENTIDAD y CORREO F.E. desde las fuentes.
  - **No duplica:** si el envío ya se cargó, avisa "El envío ya fue cargado".
  - **Una factura = una sola fila** (canónica) + un **historial de eventos**
    con toda la trazabilidad. Si una factura devuelta reingresa en un envío
    nuevo, la reconoce y numera **Subsanación 1/2/3** sin crear factura nueva.
  - **Auto-sincroniza:** corregir un dato en el Excel y volver a subirlo se
    refleja solo en el consolidado (los datos descriptivos se leen de la fuente
    más reciente, no se copian).
  - **Auditoría:** el auditor solo decide **Radicar** o **Devolver con motivo**;
    máximo 3 devoluciones (la 4.ª se bloquea).
  - **Oficio de devolución PDF** con consecutivo SINAC (formato de la guía),
    armado desde un **snapshot inmutable**: un reingreso posterior no altera un
    oficio ya emitido.
  - **Consolidado consultable y exportable a Excel** + estadísticas (por
    auditor, reincidentes, semáforo, tasa de devolución).
  - Diseño verificado con un panel de agentes IA (mapeo de columnas contra los
    archivos reales, esquema, flujo) y una **revisión adversarial** que encontró
    y corrigió: corrimiento de fechas de un día, inmutabilidad del PDF ante
    reingreso, bloqueo de doble devolución, y consultas que no escalaban a 36k
    filas. **30 pruebas del módulo + 4.327 de todo el repo en verde.**
  - Pendiente operativo: al sacar el DGReport, ampliar el rango de fechas para
    que cubra el mismo periodo que la Radicación (si no, algunas facturas
    marcan CORREO F.E.=NO por quedar fuera de la ventana del reporte).

### 27-07 — Pre-auditoría: mejoras pedidas tras el primer uso real
- **27-07:** el módulo ya está desplegado y en uso (2 oficios, 22 facturas
  auditadas el primer día). Con el feedback del auditor se agregó:
  - **Firma de Yudy en el PDF**: se extrajo la firma manuscrita de la guía y
    ahora sale automáticamente en cada oficio de devolución
    (`static/firma_preauditoria.png`, con su proporción real).
  - **Regla nueva: sin facturación electrónica NO se radica.** Si la factura
    no está en el Formato Facturación Electrónica (CORREO F.E. = NO), el botón
    "Soportes completos" queda deshabilitado y el servidor también lo bloquea:
    solo se puede devolver.
  - **Eliminar radicados (solo administradores):** individual o masivo, para
    oficios que quedaron mal registrados. Con salvaguardas: no se puede
    eliminar uno con PDF de devolución ya emitido; las subsanaciones se
    revierten sin perder el historial; los envíos quedan libres para
    re-escribirse.
  - **Dos fases con nombre:** cada oficio muestra quién lo RECEPCIONÓ y
    quién(es) lo están AUDITANDO (gestores distintos).
  - **Botón "Ver"** en el consolidado para consultar la respuesta y el
    historial completo de cada factura sin entrar a auditarla.
  - Se renombró DGReport → **"Formato Facturación Electrónica"** en la
    pantalla de fuentes.
  - **Estadísticas interactivas:** dona de resultados con clic-para-filtrar,
    barras por auditor y por entidad (top 10) con tooltips, y semáforo visual.
    Colores verificados para daltonismo.
  - 35 pruebas del módulo en verde; verificado en navegador con los archivos
    reales (36.723 facturas).

### 27-07 (tarde) — Documentación técnica oficial del módulo de Pre-auditoría
- Se generó **`docs/PREAUDITORIA_DOCUMENTACION_TECNICA.md`**: documento de
  entrega al equipo principal que reconstruye TODO el desarrollo del módulo
  (objetivo, arquitectura, funciones, flujo, base de datos, backend, frontend,
  decisiones tomadas y descartadas, riesgos, pendientes y guía de fusión).
  Es la referencia para integrar este módulo al proyecto principal sin perder
  conocimiento. PRs del módulo: #186 (v1→v2), #187 (botón menú), #189
  (mejoras post primer uso).

### 27-07 (tarde) — Documentación técnica oficial del módulo Glosas Dispensario/SIMED
- Se generó **`docs/ENTREGA_MODULO_GLOSAS_DISPENSARIO_SIMED.md`** (PR #191,
  fusionado): entrega al equipo principal del chat "GLOSAS DISPENSARIO —
  SIMED": objetivo, arquitectura, el clasificador de 14 reglas y las 16
  plantillas de respuesta con sus 4 rondas de verificación adversarial
  (qué normas NO citar y por qué), el contrato operativo del robot SIMED
  (numeración por línea de concepto, estados, reintentos, evidencias),
  cifras de los 7 lotes del Dispensario, el bot DGH por coordenadas (PR
  #134), riesgos, pendientes y el plan para fusionar todo sin perder nada.
  Recomendación clave que quedó escrita: mover `glosa_motor.py` y los
  generadores de lotes (hoy en el scratchpad de la sesión) a
  `tools/glosas_dispensario/` en el repo.

### 27-07 (noche) — Pre-auditoría: borrado total (solo admin) y Excel para ADRES
- **Zona de administración** nueva en la pestaña Fuentes (solo la ven
  SUPER_ADMIN/COORDINADOR): botón **"Borrar todos los datos"** para dejar la
  página limpia y que el equipo empiece a trabajar de cero. Borra oficios,
  facturas, historial, envíos y oficios de devolución; las **fuentes se
  conservan** salvo que se marque la casilla para borrarlas también. Pide
  escribir **BORRAR TODO** + una confirmación final, y el servidor exige rol
  de administrador (un auditor recibe "no autorizado"). Ojo: al limpiar, el
  consecutivo DEV-PRE-AUD vuelve a empezar en 0001.
- **Excel especial para ADRES:** cuando un oficio tiene facturas de ADRES
  (se reconoce por NIT 901037916 o por el nombre de la entidad), aparece el
  botón **"⬇ ADRES"** en la lista de oficios y dentro del oficio. Descarga un
  Excel con la **información completa** de esas facturas: envío, oficio FHUS,
  fechas, valor, NIT, entidad, correo F.E., fecha del correo, **CUFE**,
  estado, resultado, ronda, subsanaciones, devoluciones, auditor, motivo,
  oficio de devolución SINAC y quién recepcionó. Solo salen las facturas de
  ADRES (si el oficio trae mezcla de entidades, las otras no van).
- 42 pruebas del módulo en verde (7 nuevas: permisos del borrado, conteos,
  confirmación obligatoria, contenido del Excel ADRES).
- **Para dejar la página limpia:** después de desplegar en la VM, entrar como
  administrador → Fuentes → Zona de administración → "Borrar todos los datos"
  (sin marcar la casilla de fuentes, para no volver a subir los Excel).
- **Ajuste posterior (mismo día):** el auditor pidió que el Excel de ADRES
  salga con el formato del consolidado que se maneja con esa entidad. Quedó
  así: SINAC diligencia de **Item** a **Fecha_Entrega_Fact** (Item,
  Fecha_Recibido, Envío, AUD, HUS, Fecha_Factura, Valor, NIT, Entidad,
  Correo F.E., Observación Preauditoria Radicación SINAC, Radicar_1,
  Observaciones Adicionales, Fecha_Entrega_Fact) y después vienen las
  columnas de las otras áreas **vacías** para que continúen el mismo archivo
  (Observación_FACTURACIÓN, Fecha_Dev_CARTERA, Fecha_Segunda_Revisión,
  Segunda_Observación_SINAC, Fecha_Dev_FACTURACIÓN,
  Segunda_Observación_FACTURACIÓN, Fecha_Dev_CARTERA, Radicar_2,
  Fecha_Radicación, Número_Radicado, INFOPOL). El sistema llena: Radicar_1
  (SI/NO según la auditoría), la Observación (el motivo de devolución con el
  consecutivo DEV-PRE-AUD, o "SOPORTES COMPLETOS" si va a radicar) y deja
  **Fecha_Entrega_Fact en blanco** (esa fecha la escribe a mano quien
  entrega a Facturación). Encabezados azules el tramo SINAC y grises el de
  las otras áreas.

### 28-07 — La página se caía al subir las fuentes: causa y solución
- **Qué pasó:** durante la mañana la página mostró varias veces "Error 524",
  "Failed to fetch" y "Bad gateway 502", y **el cargue del Excel no entraba**
  (los contadores seguían mostrando el cargue anterior).
- **Causa real (medida, no supuesta):** el servidor de Google tiene **1 GB de
  memoria** y la aplicación se quedaba sin aire al procesar el archivo de
  36.723 facturas. El sistema operativo mataba la aplicación a mitad del
  cargue (5 veces en 45 minutos, confirmado en el registro del servidor), y
  al morir la base de datos deshacía todo: por eso no quedaba nada cargado.
  Reparto medido del consumo: aplicación en reposo 140 MB, leer el Excel
  +70 MB, **guardar en la base +154 MB** (todas las filas se guardaban de un
  solo golpe al final), más lo que consume el tablero cuando el equipo entra
  a la vez.
- **Solución en el código:** el cargue ahora **se guarda por bloques de 2.000
  facturas** en vez de todo al final, y los textos que se repiten miles de
  veces (entidad, NIT, envío) se guardan una sola vez y se comparten.
  Resultado medido con el archivo real: **pico de 263 MB → 119 MB** (menos de
  la mitad) y además más rápido (5,3 s → 3,7 s en el guardado). Ventaja
  adicional: si el cargue se interrumpe, **lo ya guardado no se pierde** —
  al volver a subir el mismo archivo el cargue retoma donde quedó (el
  sistema nunca duplica). 47 pruebas del módulo en verde (5 nuevas que fijan
  que trocear el cargue no altera los conteos ni duplica facturas).
- **Paliativo aplicado ese día en el servidor** (mientras se despliega lo
  anterior): se subió el tope de memoria del contenedor de 640 MB a 1.400 MB
  con uso de disco como apoyo, para que la aplicación se ponga lenta en vez
  de morirse.
- **Segundo hallazgo (misma tarde): los archivos crecieron mucho.** Al revisar
  los archivos reales de hoy resultó que ya no son del tamaño de antes:
  - Formato Facturación Electrónica: **203.484 filas** (antes 7.231).
  - Radicación de Cuentas: **191.859 filas → 189.446 facturas** (antes 36.723),
    17,6 MB, con 2.413 radicaciones anuladas.
  Con ese tamaño el cargue tardaba 49 segundos en un equipo rápido, y en el
  servidor del hospital pasaba de los **100 segundos que Cloudflare tolera**
  antes de cortar la conexión: de ahí los errores 524 y 502.
- **Segunda optimización (lectura del Excel):** se encontró que los reportes de
  Dinámica Gerencial **no declaran sus dimensiones** dentro del archivo. Cuando
  ese dato falta, la librería que lee Excel recorre el archivo COMPLETO solo
  para averiguar su tamaño y después lo vuelve a recorrer para leerlo: 12
  segundos perdidos de 36. Como el sistema nunca usa ese dato, ahora se omite
  ese primer barrido. Además se quitó una normalización de texto costosa que
  se ejecutaba 383.740 veces (dos por fila). **Resultado: la lectura pasó de
  45 a 28 segundos**, leyendo exactamente lo mismo.
- **Solución entregada al auditor ese día:** se partió el archivo de Radicación
  en 3 partes (verificando que las 3 suman exactamente lo mismo que el
  original: 191.859 leídas, 189.446 facturas, 2.413 anuladas). Cada parte
  tarda 17 segundos, muy por debajo del límite. Se puede partir sin riesgo
  porque en ese archivo **ninguna factura se repite**.
### 28-07 (tarde) — Tres fallas del uso real y el borrado de envíos
Reportadas por el auditor durante la jornada, con evidencia en pantalla:
- **La misma factura quedó radicada 5 veces.** En el historial aparecían cinco
  eventos RADICADA idénticos, del mismo auditor y a la misma hora. Causa: como
  la página no avisaba que estaba guardando, el gestor volvía a hacer clic, y
  las peticiones llegaban al servidor **al mismo tiempo**; todas veían la
  factura "pendiente" antes de que la primera alcanzara a guardar. Corregido
  por los dos lados: el botón se bloquea y muestra "Guardando…", y el servidor
  toma la factura con una sola operación indivisible, así solo el primer clic
  gana y los demás reciben un aviso claro.
- **Lo que se escribía se perdía.** El único campo del formulario decía "Motivo
  de la devolución" y, al radicar, ese texto se descartaba. Ahora hay un campo
  **Observaciones** aparte que **se guarda siempre** (también al radicar) y
  queda visible en el historial de la factura, con su propia columna.
- **La página no se actualizaba sola.** Había que recargarla a mano para ver si
  algo se había guardado, porque cuando el servidor iba lento los refrescos
  fallaban **en silencio**. Ahora las tablas muestran "Cargando…" mientras
  responden y, si algo falla, lo **dicen** en pantalla con opción de
  reintentar, en vez de quedarse mostrando datos viejos.
- **Nuevo: quitar un envío cargado por error.** En el detalle del oficio, cada
  envío tiene una ✕ (solo administradores) que lo deshace sin tocar el resto
  del oficio: borra las facturas que entraron con ese envío, y las que venían
  de una devolución vuelven a su estado anterior sin perder historial. El
  envío queda libre para volver a escribirlo. No se puede quitar si alguna de
  sus facturas ya salió en un oficio de devolución emitido.
- 58 pruebas del módulo (8 nuevas) y 4.361 de la suite completa en verde, más
  verificación en navegador de los cuatro puntos.

- **PENDIENTE importante (para que no vuelva a pasar):** con archivos de este
  tamaño, la solución de fondo es que **el cargue no haga esperar al
  navegador**: subir el archivo, responder de inmediato "recibido, procesando"
  y que la página muestre el avance. Así el tamaño del archivo deja de
  importar y no hay límite de tiempo que valga. Queda propuesto.
- **PENDIENTE recomendado:** subir la máquina virtual de `e2-micro` (1 GB) a
  **`e2-small`** (2 GB, ~US$13 más al mes). Se hace desde la consola de
  Google: Compute Engine → VM `motor-glosas` → Detener → Editar → Tipo de
  máquina `e2-small` → Guardar → Iniciar (5 minutos de página caída). Ojo:
  esos comandos NO funcionan desde adentro de la VM (la VM no tiene permiso
  para modificarse a sí misma); hay que hacerlo desde la consola web o
  desde Cloud Shell.

### Motor IA — rondas 32 y 33 (viene de la rama principal, PR #183)
- **22 y 23-07 (motor de dictámenes):** dos rondas más de corrección del motor,
  fusionadas desde la rama principal:
  - **Ronda 32:** el número de factura ya no se cuela como código CUPS en el
    dictamen (red determinística nueva); las glosas de $10 millones o más van
    al modelo potente; se corrigieron citas legales. Pasó una revisión
    adversarial (panel de 25 agentes) que confirmó y corrigió 18 detalles.
  - **Ronda 33** (dos dictámenes PPL reales, glosas de $218.145 y $5.800):
    se quitaron normas repetidas y de relleno; 13 pruebas nuevas
    (`test_ronda33_fixes.py`). Pendiente: desplegar la ronda 32 en la VM de
    Google (`cd /opt/motor-glosas && git pull && docker compose build motor &&
    docker compose up -d`) y repetir los 4 casos de prueba.

### 28-07 — SINAC OS: se pasó de "una aplicación" a una plataforma con plan

Día de dos mitades: primero se documentó a dónde vamos, después se empezó a
construir. Todo está en la rama principal.

**Lo que se documentó** (PR #197, cuatro archivos en `docs/`):
- `SINAC_OS.md` — el plano maestro que escribió Yesid: visión, principios,
  agentes, módulos y las siete fases del proyecto. Es el documento rector:
  ningún desarrollo puede contradecirlo sin actualizarlo primero.
- `MANUAL_ARQUITECTURA_SINAC_OS.md` — 19 capítulos que explican **cómo** se
  construye SINAC OS. La idea de fondo: el proceso administrativo deja de ser
  una carpeta de archivos y pasa a ser un objeto vivo que nunca muere, solo
  cambia de estado (Factura → Glosa → Objeción → Respuesta → Radicación →
  Conciliación → Aceptación → Pago → Archivo → Histórico). Cada capítulo cierra
  respondiendo qué existe hoy, qué se reutiliza, qué se elimina, qué se crea y
  cómo se migra sin romper nada.
- `MAPA_CAPACIDADES.md` — la misma plataforma explicada sin tecnicismos, para
  gerencia o para alguien que llega nuevo al área.
- `ANEXO_AUDITORIA.md` — la radiografía del sistema tal como estaba antes,
  guardada como memoria de por qué se decidió cada cosa.

**Lo que se descubrió al revisar el sistema entero** (15 auditorías sobre el
código real): el sistema sabe mucho pero está mal conectado consigo mismo. La
mitad que piensa (la aplicación web) y la mitad que ejecuta (los robots de
portal) **no se hablan**: el puente es un Excel que viaja en el escritorio de
una PC. Y hay **39 archivos de módulos ya terminados** (SAVIA, EMSSANAR, VCO,
FOMAG, Mutual Ser, el organizador de correos) que nunca se fusionaron a la
rama principal: están listos, probados y a un clic de distancia.

**Lo que ya se construyó y está funcionando:**

- **Seguridad y trazabilidad (PR #199).** Siete arreglos:
  1. El sistema decía que ciframos los datos del paciente **y no los ciframos**.
     Ahora dice la verdad; cifrarlos de verdad queda para el siguiente paso.
  2. El nombre del paciente ya no se le muestra a cualquiera: solo al gestor
     asignado, al coordinador y al administrador. Si la glosa **no** tiene
     gestor, sigue visible para todos — es trabajo que cualquiera puede tomar.
  3. Un usuario de solo lectura podía cerrar glosas por una puerta lateral,
     **incluso 500 de un golpe**. Cerrada.
  4. Si faltaba la clave secreta en la configuración, el sistema arrancaba
     igual y firmaba las sesiones con una clave vacía. Ahora no arranca.
  5. La página de "estado del sistema", que es pública, hacía un recorrido
     pesado de 30 días en cada consulta. Ahora es liviana.
  6. El registro de auditoría (quién hizo qué) ya **no se puede borrar**.
  7. Ese registro ahora guarda también desde qué computador se hizo cada cosa.
  - Además: el servidor pasó a hora de Bogotá. Estaba en hora de Londres, así
    que las tareas programadas "de las 3 de la mañana" corrían a las 10 de la
    noche.
- **Un solo lector de valores en pesos (PR #201).** Había cuatro copias del
  mismo código leyendo montos, y dos se equivocaban en plata:
  - El **informe de cartera de gerencia** leía `950.000` como **950 pesos**
    (cualquier monto con un solo punto se dividía por mil). Solo pasaba con
    valores en texto, como los que exporta el DGH. **Conviene revisar un
    informe reciente.**
  - El cargue de tarifas leía como **cero** dos formas de escribir comunes
    (`1'500.000` y `850 millones`). Una tarifa en cero se propaga al dictamen.
  - Al unificar apareció un tercer error: `0.99` se leía como 99 pesos.
  - Ahora hay un solo lector, y una prueba que caza a quien vuelva a escribir
    otro por su cuenta.

**Dos hallazgos que conviene no perder de vista:**
- El robot de SAVIA **multiplica por cien** los valores con decimales
  (`1.365,50` → `136.550`). El módulo de EMSSANAR ya había corregido ese mismo
  error, pero el arreglo nunca llegó porque las ramas nunca se juntaron. Si el
  Excel de SAVIA trae decimales, los archivos generados con ese robot llevan
  valores inflados.
- El sistema **ya tiene construido** un avisador por correo de glosas próximas
  a vencer (ordena por urgencia, arma el correo, todo). Está terminado y
  **desconectado**. Es justo lo que faltó cuando las tres facturas de junio
  ($20.054.751) se descubrieron 45 días tarde.

---

## 3) PENDIENTE

### COOSALUD
1. **Correr el consolidado fusionado de pertinencia** (37 facturas / 5.736
   glosas) con `--hoja CALIDAD --incluir-calidad`. Con eso los LOTES 06, 07 y
   08 quedan cerrados al 100%. El archivo está en Downloads como
   `CONSOLIDADO_PERTINENCIA_6JULIO_FUSIONADO.xlsx`.
2. **Confirmar los resultados de los LOTES 02, 06, 07 y 08:** revisar los
   reportes CSV en `D:\USUARIO CARTERA\Documents\COOSALUD\` (cuántas OK,
   cuántas PENDIENTE_PDX o pendientes) y hacer segunda pasada donde falte.
3. **Words de evidencia de los lotes recientes** (02, 06, 07, 08 y pertinencia),
   cada uno en su carpeta `MES AÑO\DD-MM-AAAA\` con subcarpeta SOPORTES.
4. **Lote 69 — 23 facturas sin pantallazo** (4 nunca estuvieron en bolsa, resto
   por revisar): decidir si se reprocesan o se documentan como están.
5. **HUS504096:** factura mencionada en un cruce de junio que no aparece en
   ningún consolidado. Verificar de qué lote es o si el número está mal escrito.

### Notas crédito Dispensario (Lote V2) — detalle en `docs/diagnostico_lote_v2_pendientes/`
6. **Rechazos CUV:** hacer seguimiento a la respuesta del área sobre las 4
   facturas conciliadas (informe enviado el 17-07). Esperando de SISTEMAS:
   - Corregir el RIPS y revalidar las 3 con **RVC086** (HUS404136, HUS410675,
     HUS435485) — el reintento sin corregir ya se probó el 25-06 y volvió a fallar.
   - Reejecutar la validación que nunca corrió (servicio caído) de las 6:
     HUS411234, HUS420099, HUS421733, HUS418576, HUS420160, HUS422238.
   - Cuando confirmen: revalidar los CUV (comando en el README de la carpeta
     del diagnóstico) y radicar en SIMED con el robot.
7. **Descargar del DIAN los PDF de 2 notas:** HUS413266 (radicado 492346) y
   HUS417459 (radicado 521665). Sin ese PDF no se pueden armar las carpetas.
8. **Dos consultas a FACTURACIÓN:** (a) HUS440328 — ¿la nota vigente es la
   302111 del histórico o emitieron una nueva?; (b) HUS422238 — confirmar que
   la nota 311199 sí le corresponde (no aparece en el histórico de conciliación).
9. **Verificar el resto del Lote V2:** las que estaban "COMPLETA" sin subir
   (HUS409574, 410979, 416671, 428425, 428523, 431722, 432292, 432884, 437357,
   437582) — confirmar si ya quedaron radicadas en SIMED o siguen pendientes.

### Dispensario — respuesta de glosas SIMED y conciliación
10. **Subir a SIMED las 3 facturas de junio** (518186 / 515107 / 515773) con
    `respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx`. **URGENTE: sus fechas
    de vencimiento (6 y 8 de julio) ya pasaron.** Si el portal ya no las deja
    responder, radicar la respuesta por oficio/correo dejando constancia.
11. **Confirmar la subida a SIMED de los lotes del 14 y 17 de julio** (los
    Excel están listos; falta el log de la corrida y la pasada de verificación
    que debe dar 0 pendientes).
12. **Generar los PDF de evidencias:** lote 14-07 → `GI-33-5182-2026.pdf`
    (comando ya entregado); lote 17-07 → falta el consecutivo GI-33 (pedirlo
    al auditor).
13. **Soportes por adjuntar del lote 17-07** (casos puntuales): notas de
    enfermería del 16-jun (529093), renglón tarifario de dispositivos (coils,
    AIRVO, material de osteosíntesis), descripción quirúrgica del vaciamiento
    de cuello (529291), reporte de lactato/piruvato y aclaración de la biopsia
    vs. estereotaxia (CL0301), justificación de la segunda hemoclasificación.
14. **Robot DGH:** correr el modo `--calibrar` en el equipo de la oficina y
    validar el llenado de la ventana de respuesta por coordenadas.
15. **Conciliación:** confirmar el acta de inicio del contrato 287 y el mapeo
    de códigos internos de cartera (U22031/C26001…), y correr el asistente en
    piloto sobre 1-2 facturas reales contra `Y:\`.

### Informes
16. **Informe de gerencia:** falta el dato real del "antes" (cuánto tardaba el
    proceso manual y cuántas personas) para poner el multiplicador exacto.
    Completar también el "valor total objetado defendido" del lote 9-jul
    (sale de `reporte_glosa.csv`).

### Módulo de Pre-auditoría (nuevo, 23-07)
17. **Revisar y aprobar el PR nuevo** (borrado total admin + Excel ADRES) de la
    rama `claude/invoice-audit-bot-qa2koy`; los PRs #186, #187, #189 y #190 ya
    están fusionados. Después de aprobar: desplegar en la VM y **usar el botón
    "Borrar todos los datos"** (como administrador, sin marcar la casilla de
    fuentes) para dejar la página limpia antes del arranque real del equipo.
18. **Definiciones que quedaron con supuesto y hay que confirmar con el
    auditor:** (a) el plazo de 3 días se contó en **días hábiles lunes-viernes**
    (sin festivos colombianos); (b) los nombres/cargos de las firmas del
    oficio PDF se tomaron del Excel de oficios — si cambian, se ajustan en
    `app/services/oficio_devolucion_pdf.py`; (c) si se quiere la firma
    escaneada en el PDF, subir la imagen como
    `static/firma_preauditoria.png` (el módulo la toma solo).
19. **Cargar el histórico** del CONSOLIDADO_PRE_AUDITORIA_2026.xlsx al módulo
    (el importador ya entiende ese formato de columnas, se puede subir por
    oficio) para que las estadísticas y el control de 3 devoluciones
    arranquen con la historia real.

## 4) PARA MAÑANA

1. **Dispensario prioridad 1:** subir a SIMED el Excel de las 3 facturas de
   junio y guardar el pantallazo de evidencia de cada una. Si los lotes del
   14 y 17 aún no están subidos, subirlos (piloto de 1 factura → lote →
   verificación) y generar sus PDF de evidencias.
2. Correr la **pertinencia fusionada** COOSALUD (pendiente #1) y verificar que
   las 37 facturas cierren con evidencia.
3. Con los reportes en mano, **cerrar los flecos de los lotes 02/06/07/08**
   (segunda pasada de las que queden pendientes).
4. Generar los **Words de evidencia** de todo lo cerrado y archivarlos en sus
   carpetas por mes/día.
5. Actualizar el **informe de gerencia** con el acumulado real de julio
   (facturas y glosas cerradas por lote).
6. Si hay tiempo: verificar si SISTEMAS ya corrigió algún CUV (pendiente #6),
   descargar los 2 PDF del DIAN (pendiente #7) y revisar el PR #186 del módulo
   de pre-auditoría.

### SINAC OS — decisiones que dependen de Yesid (28-07)

7. **Revisar un informe de cartera reciente.** El lector de montos leía
   `950.000` como `950` cuando el valor venía en texto. Ya está corregido, pero
   conviene mirar si algún informe salió con cifras bajas.
8. **Revisar un Excel de SAVIA.** Si la columna de valor trae comas decimales,
   los archivos que generó ese robot llevan los montos multiplicados por cien.
   El arreglo existe (lo tiene el módulo de EMSSANAR); falta juntarlos.
9. **Decidir qué hacer con los 39 archivos huérfanos** (SAVIA, EMSSANAR, VCO,
   FOMAG, Mutual Ser, organizador de correos, herramientas de cartera): están
   en ramas de otras sesiones con sus PR en borrador (#162, #164, #167). Se
   fusionan desde acá o se cierran desde esas sesiones — pero conviene no
   dejarlos más tiempo sueltos, que es justo lo que produjo dos robots
   distintos para el mismo pagador.
10. **Decidir si se enciende el avisador de vencimientos por correo.** Está
    construido y desconectado. Para prenderlo hace falta definir: quién recibe
    los avisos, con cuántos días de anticipación, y desde qué cuenta de correo
    salen (hoy no hay servidor de correo configurado).
11. **Comprobar que el enmascarado del nombre del paciente no estorbe** en el
    trabajo diario. Si una glosa tiene gestor asignado, los demás auditores
    ven iniciales en vez del nombre. Si molesta, se ajusta en una línea.
12. **Siguiente paso de construcción**, según el plan: terminar la limpieza de
    módulos sin uso y arrancar la **Fase 2 — modelo real del dominio**
    (Factura → Glosa → Soporte → Conciliación → Acta).

---

## 5) Datos fijos que siempre se necesitan

- **Carpeta de trabajo en Windows:** `C:\temp-notas` (ahí vive el repo).
- **Credenciales:** siempre en variables de entorno (`COOSALUD_USER`,
  `COOSALUD_PASSWORD`). Nunca escritas en archivos ni en comandos.
- **Índice de soportes:** `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt`.
- **Reportes y evidencias:** `D:\USUARIO CARTERA\Documents\COOSALUD\`.
- **Notas crédito Dispensario:** diagnóstico e informes en
  `docs/diagnostico_lote_v2_pendientes/` (repo); carpetas de trabajo en
  `D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\`
  (subcarpeta `PENDIENTES_12` con ficha por factura); fuente oficial XML/CUV en
  `\\172.16.32.83\factura_electronica_net22\<AAAAMM>\FACTURAS_NOTA\<nota>\`.
- **Regla de reanudación:** si un cargue se corta (luz, portal caído), NO se
  pierde nada: se relanza con `--saltar-csv <reporte anterior>` y un nombre de
  reporte nuevo. El bot salta lo ya cerrado y no duplica respuestas.
- **Regla de soportes:** las glosas extemporáneas (RE9502) NO llevan PDF de
  soporte. Las demás (ej. RE9901 en glosas de soportes) sí, y salen del share
  vía el índice.

### Notas de método del flujo Dispensario (para cualquier chat nuevo)

- **Solo se trabaja el Dispensario Médico (DSE Ejército)** en este flujo de
  respuestas; si el Excel trae otras entidades, se omiten.
- Toda respuesta va en **MAYÚSCULAS, un solo párrafo**, empieza con
  *"ESE HUS NO ACEPTA LA GLOSA APLICADA A LA FACTURA…"* y cierra citando la
  mesa de conciliación y los correos de cartera.
- Postura institucional: **NO ACEPTA (RE9901), se defiende el 100% del valor.**
- Normas ancla: Res. 2284/2023 (Manual Único de Glosas — la 3047/2008 está
  DEROGADA, no citarla), contrato 440-DIGSA/DMBUG-2025 (el Dispensario ES
  parte), Resoluciones de tarifas HUS 054 y 124 de 2026 (y 194/2025 para
  material de osteosíntesis), Ley 1751/2015 art. 17 (autonomía médica),
  Decreto 4747/2007 y Ley 1438/2011 art. 57 (conciliación y trámite).
- Los generadores de respuestas de cada lote viven en el scratchpad de las
  sesiones (`glosa_motor.py` es la fuente única de plantillas); los robots de
  portal están en `tools/` de este repo.
