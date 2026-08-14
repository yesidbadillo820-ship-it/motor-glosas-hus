# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Este archivo es la memoria común de todos los chats de Claude Code.**
> Al iniciar cualquier sesión de trabajo, léase primero este archivo para saber
> en qué va todo. Al terminar cada sesión, debe actualizarse con: lo que se hizo
> hoy, lo que quedó pendiente y lo que sigue mañana, siempre con la fecha.

**Última actualización:** 27 de julio de 2026 (segunda sesión del día)

---

## Qué es este proyecto (para ubicarse en 1 minuto)

Herramientas de trabajo del área de **Auditoría de Cartera / Glosas** del
Hospital Universitario de Santander (ESE HUS, operado con SINAC SC SAS):

1. **La aplicación web "Motor de Glosas"**: recibe las glosas (objeciones de
   las EPS a las facturas del hospital) y redacta con inteligencia artificial
   la respuesta técnico-jurídica de defensa, usando los contratos, tarifas,
   normas y soportes reales de cada caso. Corre en un servidor propio del HUS.
2. **Robots de portales**: programas que hacen el trabajo repetitivo de
   cargar respuestas y soportes en los portales de cada pagador
   (SIMED del Dispensario Médico, portal de COOSALUD, y el sistema interno
   Dinámica Gerencial - DGH), dejando pantallazos como evidencia.
3. **Utilitarios de Excel y notas crédito**: programas pequeños que organizan
   carpetas de notas crédito, verifican validaciones del Ministerio (CUV),
   cruzan archivos de conciliación y diligencian consolidados mensuales.

---

## RESUMEN DE LO YA HECHO (agrupado por fecha)

### Abril 2026 — Nacimiento del sistema y construcción acelerada

- **8–9 abril:** Primer día del proyecto. Se creó la aplicación web con su
  base de respuestas por tipo de glosa, la normativa colombiana de salud
  (Ley 1438, Resolución 3047, etc.), el control de usuarios con contraseña y
  las primeras correcciones de seguridad. Se agregó exportación a Excel y
  alertas de vencimiento por correo.
- **10 abril:** La respuesta generada empezó a citar el servicio y el contrato
  específico de cada caso. Se creó la **importación masiva de glosas desde
  Excel**.
- **13 abril:** Roles de usuario (administrador, coordinador, gestor, auditor),
  registro de auditoría de acciones, módulo de conciliaciones y módulo para
  los archivos de respuesta de Salud Total.
- **16–17 abril:** Se cargaron los **13 contratos reales del HUS** y se creó la
  importación del Excel de recepción (el que sale del DGH) con semáforo de
  vencimientos y asignación a cada gestor con su correo corporativo. Además:
  bandeja "Mis Glosas" por gestor, presentación institucional, rediseño
  visual, búsqueda rápida, doble factor de seguridad (2FA) y mejoras grandes
  de calidad en la redacción.
- **20–21 abril:** Catálogo completo del **Manual Único de Glosas** (200
  códigos), biblioteca normativa de consulta para auditores, y una campaña
  fuerte contra los errores de la IA: que no invente montos, cláusulas ni
  datos de pacientes, tono institucional conciliador, respuestas más
  concisas. Se activó el monitoreo de errores (Sentry) y protecciones de
  seguridad adicionales.
- **22 abril:** Marca **SINAC SC SAS** en la aplicación (logo y branding).
  Botones por concepto para **Defender / Aceptar 100% / Aceptar parcial**,
  columna de días hábiles transcurridos, y corrección definitiva del panel de
  Salud Total.
- **23 abril:** **Catálogo de tarifas pactadas por EPS** cargable desde Excel
  (Famisanar, Dispensario) con aviso de tarifa al analizar glosas de tarifa.
  Optimización del gasto de IA (~80% menos). Arrancaron las "rondas" de
  mejoras: pre-análisis automático a las 6 AM, aprendizaje por
  retroalimentación, predictor de glosas, extracción automática de PDFs,
  consulta normativa con verificación anti-invenciones y detector de
  anomalías.
- **24 abril:** Autopilot (el sistema recomienda qué hacer con cada glosa y
  aplica textos fijos a las ratificadas/extemporáneas), resumen ejecutivo
  diario, exportación gerencial en Excel, **exportación con el formato exacto
  para cargar al DGH**, homologador de la Resolución 2641/2025, manual de
  capacitación para gestores.
- **25–27 abril:** Se agregaron **cientos de consultas y reportes
  estadísticos** (por EPS, por gestor, por código, cartera, semáforos,
  proyecciones, tablero de cobranza) y un asistente que sugiere el orden del
  día. En el "cerebro" de respuestas: distinción correcta entre valor
  facturado / pactado / objetado, respuesta MIXTA cuando corresponde,
  **registro de nota crédito al aceptar glosas**, pre-auditoría sin costo que
  detecta errores de la EPS antes de gastar IA, y recorte del costo por glosa.
- **28 abril:** Detector de soportes requeridos antes de responder,
  auto-respuesta masiva, textos institucionales fijos, tarifas FOMAG, y
  corrección masiva de códigos de respuesta mal asignados.
- **29–30 abril:** Conexión con el **share de archivos del hospital** para
  encontrar automáticamente los PDF de soportes de cada factura (agente
  "jump-box"), y liquidador de tarifas SOAT/UVB en línea.

### Mayo 2026 — Calidad, portales y orden

- **4 mayo:** Migración del servidor (de Render a Fly.io por memoria
  insuficiente). Subir el **PDF del contrato** y extraer sus cláusulas con IA
  para usarlas en los dictámenes.
- **5–8 mayo:** Verificador de citas normativas (que lo citado exista de
  verdad), calificación de confianza de cada dictamen, importación masiva
  mejorada (avance en vivo, costo estimado, historial), tercera IA de
  respaldo y comparador de IAs, Auditor Forense de PDFs y panel de mando para
  el coordinador.
- **9 mayo:** **Gran limpieza**: se eliminaron más de 22 módulos que no se
  usaban en el día a día del HUS, para enfocar el sistema en lo que sí sirve.
- **10–12 mayo:** La IA dejó de copiar plantillas y empezó a argumentar cada
  caso (esqueleto en vez de ejemplo literal). Se inyectan las **cláusulas
  literales del contrato** al dictamen. Rediseño del panel Analizar. Subió la
  calidad de los modelos económicos para reducir costo sin perder nivel.
- **14–19 mayo:** **Excel de respuesta por correo a cada gestor** al importar
  la recepción, importación en segundo plano (se resolvió un incidente que
  tumbó la aplicación), y limpieza general de código.
- **20–22 mayo:** Semana de infraestructura y calidad: pruebas automáticas en
  cada cambio (CI), documento de arquitectura, **auditoría completa del
  sistema con checklist priorizado** (`AUDITORIA.md`, `AUDIT_CHECKLIST.md`),
  **banco HUS de 50 plantillas institucionales** que la IA usa de forma
  literal, y el **Quality Gate**: un control de calidad automático que revisa
  cada dictamen antes de mostrarlo. Se aprobó el **Plan de Transformación
  2026**. Nacieron las herramientas de **notas crédito** (extraer, renombrar,
  organizar 368 notas por gestor) y el **robot de SIMED** que carga soportes
  de notas crédito al portal del Dispensario con evidencia en pantallazos.
- **23–29 mayo:** Corrección definitiva de citas inventadas, arreglos de
  pantalla del dictamen, y mejoras del robot SIMED para procesar lotes
  específicos.

### Junio 2026 — Robots de portales y pruebas de estrés

- **2–4 junio:** Herramientas para radicación **ADRES** (inspector de
  soportes RIPS/CUV/FEV y generador del FUR de servicios).
- **9–10 junio:** **Robot de respuestas masivas de glosas en SIMED** (responde
  objeción por objeción con fecha y soportes). Quality Gate conectado al
  flujo en vivo. Bóveda cifrada de credenciales de portales. PDF radicable de
  cada respuesta y registro auditable de radicación. **Divisor de notas por
  ACTA** (decide cuáles van por correo y cuáles por SIMED).
- **11–12 junio:** **Robot de COOSALUD** (responde glosas en su portal, con
  manejo de las lentitudes del portal y evidencias en Word). Verificador
  rápido de pendientes de COOSALUD. **Excel radicable con el formato exacto
  del Dispensario (DMBUG)**. Rediseño visual de identidad SINAC.
- **16–19 junio:** Rondas 3 a 11 de **pruebas de estrés con casos reales**:
  cada día se evaluaban dictámenes de verdad, se detectaban errores y se
  corregían el mismo día (calificaciones subieron de ~4/10 a 8+/10).
  Herramienta de **respuestas sugeridas desde el histórico**
  (`motor_glosas_hus.py`), verificador del **CUV** (validación MinSalud) de
  notas crédito, contratos de 15 pagadores catalogados, migración de la base
  de datos a SQLite en el servidor propio, endpoints de nota crédito, acta de
  conciliación SINAC, y piloto de conexión con **Dinámica Gerencial**
  (`login_dg.py`).
- **22–26 junio:** **Servidor propio en máquina del HUS** con túnel de
  Cloudflare (costo $0/mes) y auto-actualización desde Git. Guías detalladas
  de los robots COOSALUD y SIMED, y documentos de contexto para abrir chats
  nuevos sin perder el hilo. Mejoras a ambos robots (cerrar residuales,
  glosas de calidad/pertinencia, fallbacks de soportes). **Radicador maestro
  multi-entidad**. Rondas 12 a 18 de calidad con auditoría humana de
  dictámenes reales. **Diagnóstico de las 12 facturas pendientes del Lote V2
  del Dispensario** (25-jun): se descubrió que el registro manual estaba
  equivocado en 6 de 12 — la mitad "subidas OK" en realidad nunca validaron el
  RIPS ante MinSalud porque un servicio interno del hospital estaba caído;
  se armó el escalamiento a SISTEMAS con evidencia técnica.
- **30 junio:** **Tablero de Radicación y Cartera** para Cuentas Médicas
  (alertas de mora +90 días, exportar Excel, comparativos). **Homologador
  oficial CUPS → SOAT** para defensa tarifaria. **Tablero de calidad 0–10**
  que califica los dictámenes contra una rúbrica experta y detecta
  retrocesos (benchmark en vivo del motor real). Refutación obligatoria
  **concepto por concepto**. Banco de evidencia clínica nivel 1A para
  tecnología costosa. Piloto del robot que **carga respuestas directamente en
  Dinámica Gerencial** (`responder_glosas_dgh.py`). Rondas 19 a 22.

### Julio 2026 — El expediente completo y trabajo de campo

- **1–2 julio:** Sesión "el expediente": la IA dejó de argumentar a ciegas y
  ahora usa (1) **el contrato real** — se cargaron 26 cláusulas literales de
  11 pagadores reales (AURORA, COMPENSAR, COOSALUD, SUMIMEDICAL, SALUD MÍA,
  POSITIVA, PPL, FAMISANAR, DISPENSARIO/DMBUG, POLICÍA, FOMAG) con tarifas
  verificadas contra los Excel; (2) **los soportes** — lee la historia
  clínica adjunta completa y un mapa de folios; y (3) **los precedentes
  ganados** más parecidos a cada glosa. Resultado medido en el tablero: de
  2.5/10 a ~9/10 en los casos difíciles. 4.069 pruebas automáticas en verde.
- **3 julio:** Auditoría integral (rondas 27–28): 20 correcciones seguras +
  un arreglo urgente de caída en producción (error 502 por una variable de
  correo vacía) + se retiró una clave de API real que estaba expuesta en un
  archivo de ejemplo.
- **7–8 julio:** Ronda 29 de limpieza (27 hallazgos: errores silenciosos,
  código muerto). Se eliminó el despliegue en Fly.io (ya todo corre en el
  servidor propio del HUS).
- **10 julio:** Robot COOSALUD: las respuestas extemporáneas (RE9502) ya no
  exigen soporte. **Informe para gerencia del diagnóstico del Lote V2**
  (12 notas crédito del Dispensario, $8,7 millones por radicar): documento
  formal con causa raíz por factura, comparativo antes/después y
  responsables.
- **17 julio:** Nueva herramienta
  `tools/completar_tramite_glosas_aceptadas.py`: **diligencia automáticamente
  el consolidado mensual de glosas aceptadas** (columnas RESPUESTA, N° y
  FECHA DE TRÁMITE Y/O ACTA) cruzando cada factura contra la CIRCULARIZACIÓN
  DE GLOSAS, validando que el valor aceptado cuadre con el acta. Se corrió
  para **junio 2026: 76 filas diligenciadas** y un reporte de 54
  observaciones para revisar (actas citadas con otro número, valores
  parciales). Quedó en el PR #166 (borrador) y el Excel diligenciado se
  entregó al auditor.
- **22 julio:** Se creó esta **BITÁCORA** como memoria común de todos los
  chats, reconstruyendo el historial completo del proyecto (1.647 cambios
  registrados en Git desde el 8 de abril), y se dejó la instrucción
  permanente en `CLAUDE.md` de leerla al inicio y actualizarla al final de
  cada sesión. Ese mismo día se corrigieron **dos pruebas automáticas que
  se dañaron solas con el paso del calendario**: sembraban datos con fechas
  fijas de abril y los reportes que revisan solo miran los últimos 90 días,
  así que al pasar los 90 días empezaron a fallar sin que nadie hubiera
  tocado nada. Ahora usan fechas relativas al día en que se ejecutan.
- **27 julio:** Se completaron dos archivos de nota crédito que traían la
  casilla de respuesta con el error **#N/D** (facturas HUS0000340948 del
  acta 509 y HUS0000384193 del acta 604, ambas de vigencia 2025): se
  verificó que no están en la circularización 2026 y se llenaron con el
  texto del acta que trae la propia observación de la nota. Se advirtió que
  en la segunda el acta suma $113.700 y la nota crédito es por $52.100.
  Además se redactó el **documento técnico de entrega del módulo**
  (`docs/HANDOVER_TRAMITE_GLOSAS_ACEPTADAS.md`) para poder consolidar este
  desarrollo dentro del proyecto principal sin perder nada: explica el
  objetivo, cómo funciona por dentro, cada decisión que se tomó y por qué,
  los datos del cruce de junio, los riesgos al integrarlo y el paso a paso
  para fusionarlo. Al subirlo, el revisor automático de código (que el
  proyecto instala siempre en su versión más reciente) acababa de cambiar
  de versión y empezó a revisar también los documentos: rechazó el nuevo
  documento por detalles de espaciado en sus ejemplos de código. Se
  corrigió el formato y quedó anotado el pendiente de fijar la versión de
  esa herramienta para que no vuelva a pasar.

- **27 julio (tarde):** Se diligenció el **consolidado de julio 2026**. El
  archivo venía con otro formato (la hoja se llama distinto, los encabezados
  están una fila más arriba y las columnas están corridas una posición), y
  además el trabajo del mes era otro: las 229 filas de tipo Acta ya traían el
  número y la fecha del acta, **solo faltaba el texto de la respuesta**. En
  vez de arreglar la herramienta a la medida de este mes, se la hizo
  **capaz de reconocer el formato sola**: ahora busca la hoja, la fila de
  encabezados y cada columna por su nombre, así que sirve para cualquier mes
  aunque cambien de sitio. También se le enseñó a **no pisar** un número o
  una fecha que ya haya escrito el auditor. Resultado: **229 respuestas
  diligenciadas**, ninguna otra celda del archivo tocada, y **228 de 229
  cuadran al peso** con el valor de la nota crédito. La única excepción es la
  factura HUS0000470403 (acta 825, Seguros del Estado), donde el acta detalla
  $4.557.800 y la nota es por $4.557.805: **5 pesos de diferencia**. Se
  comprobó además que la herramienta sigue produciendo exactamente el mismo
  resultado de junio que ya se había entregado.
  Después se sometió el resultado a una **revisión independiente** (seis
  revisiones automáticas mirando el archivo desde ángulos distintos), y
  apareció un defecto serio que la comprobación de valores **no podía
  detectar**: en las actas hay glosas que la entidad levantó o que la ESE no
  aceptó, y que valen $0. Como sumar cero no cambia el total, esos párrafos se
  colaban en la respuesta sin que la validación se diera cuenta: había notas
  crédito cuyo texto empezaba diciendo "ESE HUS NO ACEPTA GLOSA", justo lo
  contrario de lo que la nota documenta. Se corrigió (ahora solo entran los
  conceptos con valor acreditado) y se rehicieron los archivos de julio **y de
  junio**, que tenía el mismo defecto en 7 celdas. La misma revisión encontró
  además que en la factura **HUS0000470388 (acta 832) el acta reconoce
  $491.700 aceptados pero la nota crédito solo acredita $479.700: quedan
  $12.000 aceptados en acta firmada sin nota crédito**. Y confirmó dos cosas
  tranquilizadoras que nadie había comprobado: no falta ninguna factura por
  acreditar de esas 9 actas, y las 98 filas de trámite ya venían correctas.

---

## PENDIENTE

1. **Lote V2 Dispensario (12 notas crédito, ~$8,7 millones):** en manos de
   terceros desde el escalamiento del 25-jun / informe del 10-jul:
   - 9 facturas dependen de **SISTEMAS** (RIPS sin validar por servicio
     interno caído, o rechazado por MinSalud con código RVC086).
   - 2 facturas requieren descargar el **PDF del DIAN** (Cartera).
   - 1 factura requiere confirmar el número de nota con **Facturación**
     (HUS440328, NE histórico 302111).
   - Falta: hacer seguimiento a SISTEMAS y, cuando validen, re-correr la
     verificación (`diagnosticar_local.ps1`) y radicar en SIMED.
2. **Excel de glosas aceptadas de junio 2026:** el archivo diligenciado ya se
   entregó, pero el reporte de revisión dejó casos por confirmar con el
   auditor:
   - 11 notas crédito citan el **acta 786 del 07/05/2026**, que no existe en
     la circularización; allí esas facturas figuran bajo el **acta 879 (o
     862) del 20/05/2026**. Confirmar cuál número es el oficial.
   - 17 filas donde el valor de la nota crédito es **menor** al valor
     aceptado en el acta (posibles saldos acreditados en otras notas).
   - 21 facturas del **acta 599 de 2025** (vigencia anterior) que no están en
     la circularización 2026 — se diligenciaron con la observación de la
     propia nota crédito; validar si así se deja.
3. **PR #166 (borrador):** aprobar y fusionar la herramienta de glosas
   aceptadas para que quede oficial y reutilizable cada mes.
4. **Checklist técnico de la auditoría de mayo** (`AUDIT_CHECKLIST.md`):
   siguen abiertos los puntos de seguridad de nivel medio (endurecer dos
   funciones administrativas, exigir contraseña actual al cambiarla,
   límites de intentos en accesos sensibles) y de consistencia de datos.
   Nota: los puntos de Fly.io ya **no aplican** (se migró a servidor propio).
5. **Robot de Dinámica Gerencial** (`responder_glosas_dgh.py`): quedó en
   piloto (junio 30 – julio 1) con el modo de calibración; falta la puesta en
   marcha completa en la máquina del HUS.
6. **Revisar las demás pruebas automáticas con fechas fijas.** Se arreglaron
   las dos que fallaron, pero seguramente quedan más esperando su turno: es
   un problema que ya se repitió cuatro veces (9 y 24 de junio, 30 de junio
   y 22 de julio). Vale la pena hacer una revisión de una sola vez.
7. **La herramienta de glosas aceptadas no tiene pruebas automáticas
   propias.** Funciona y se verificó a mano, pero conviene agregarlas para
   que nadie la dañe sin darse cuenta.
8. **Instalar el entorno de desarrollo falla en máquinas limpias** por dos
   paquetes (`http-ece` y `sgmllib3k`) que quedaron en la lista pero
   pertenecen a funciones ya retiradas del sistema en mayo. Conviene
   sacarlos de la lista.
9. **Consolidación del proyecto:** este desarrollo debe integrarse al
   proyecto principal siguiendo el paso a paso del documento
   `docs/HANDOVER_TRAMITE_GLOSAS_ACEPTADAS.md` (ojo: la rama principal del
   repositorio se llama `motor-glosas`, no `main`).

---

## PARA MAÑANA (28 de julio de 2026)

0. **Julio 2026 — cuatro casos que necesitan decisión del auditor:**
   (a) **HUS0000470388, acta 832: faltan $12.000.** El acta acepta $491.700 y
   la nota crédito solo acredita $479.700. Definir si falta emitir nota por la
   diferencia o si se acreditó en otro periodo.
   (b) **HUS0000470403, acta 825: 5 pesos.** El acta detalla $4.557.800 y la
   nota es por $4.557.805.
   (c) **HUS0000508277, acta 828: 100 pesos.** El texto del acta dice $198.100
   pero su propio valor registrado y la nota dicen $198.200. El error viene de
   la circularización, no de la nota.
   (d) **HUS0000467123 y HUS0000420585:** dos renglones del acta comparten el
   mismo texto de concepto, así que se escribió una sola vez y el lector no
   alcanza a ver que fueron dos glosas.
1. Revisar con el auditor los **casos marcados del Excel de junio**
   (acta 786 vs 879/862 y los 19 valores parciales) y, si hay correcciones,
   re-generar el archivo con la herramienta (es un solo comando).
2. **Aprobar/fusionar el PR #166** para dejar la herramienta disponible, y
   luego consolidarlo en el proyecto principal con la guía del documento de
   entrega.
3. Retomar el **seguimiento a SISTEMAS** por las 9 notas del Lote V2
   bloqueadas por RIPS/CUV.
4. Validar contra el acta física el caso de **HUS0000384193 (acta 604)**,
   donde el acta suma $113.700 y la nota crédito es por $52.100.
5. Si llega el consolidado de otro mes (julio), correr la misma herramienta
   de glosas aceptadas.

---

## Historial de actualizaciones de esta bitácora

| Fecha | Quién | Qué se actualizó |
|---|---|---|
| 22-jul-2026 | Claude Code | Creación de la bitácora con la reconstrucción completa del historial (abril–julio 2026). |
| 27-jul-2026 (tarde) | Claude Code | Diligenciamiento del consolidado de julio 2026 (229 respuestas) y herramienta capaz de reconocer sola el formato de cada mes. |
| 27-jul-2026 | Claude Code | Se agregó el arreglo de las pruebas caducas (22-jul), el llenado de los dos archivos con #N/D y el documento técnico de entrega del módulo. Se ampliaron los pendientes (revisión de pruebas con fechas fijas, pruebas de la herramienta, entorno de desarrollo, consolidación) y se reescribió "Para mañana". |
