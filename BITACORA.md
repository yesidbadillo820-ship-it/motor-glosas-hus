# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana). Escrito en lenguaje claro
> para el auditor de cartera del HUS.

**Última actualización:** 19-08-2026

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
   - `tools/responder_glosas_siifa.py` — **SIIFA** (Ministerio de Salud, plataforma
     nacional, no es un portal de una EPS): a diferencia de los otros, no es un
     bot de navegador, habla directo con la API oficial de interoperabilidad.
   - Otros: Mutual Ser, FOMAG, radicador de facturación.
3. **Plataforma de conciliación del Dispensario** (`tools/`):
   índice de soportes → expediente por factura → motor de evidencia → hechos
   probados → motor de decisión → piloto (`piloto_conciliacion_dispensario.py`).
4. **Herramientas de apoyo:** armar el Word/PDF de evidencias
   (`tools/evidencias_a_word.py`, `evidencias_a_pdf.py`), notas crédito del
   Dispensario (renombrar, organizar, verificar CUV), tablero de cartera
   (`tools/tablero_cartera.py`), informe masivo de seguimientos SIIFA
   (`tools/siifa_reporte_seguimientos.py`).
5. **Módulo ADRES/FURIPS** (chat "VALIDADOR ADRES"):
   - `tools/adres/validar_furips.py` + `VALIDAR_FURIPS.cmd` — validador masivo
     FURIPS 1/2 contra la Circular 022/2023 + cruce con soportes (RIPS, CUV,
     XML DIAN, factura PDF, epicrisis) con OCR para PDF escaneados.
   - `validador-adres/` — la misma validación como APP WEB (navegador,
     puerto 8010, `VALIDADOR_ADRES_WEB.cmd`).
   - `tools/generar_informe_baja_cartera.py` + `INFORME_BAJA_CARTERA.cmd` —
     informe Word + Excel de baja de facturas (Res. 577/2019), también con OCR.
   - `tools/completar_informe_xml_dian.py` + `COMPLETAR_INFORME_XML.cmd` —
     completa el informe de devoluciones DE4401 de NUEVA EPS leyendo los XML
     DIAN del repositorio de facturación (v2.1: subcarpetas, ZIP, DIAGNOSTICO).
   - Bots PDF de doble clic: `UNIR_PDFS.cmd`, `PDF_A_CMD.cmd`,
     `PDF_A_CMD_EN_CARPETA.cmd`.

Guías por plataforma en `docs/`: `CONTEXTO_COOSALUD.md`,
`CONTEXTO_DISPENSARIO_GLOSAS.md`, `CONTEXTO_DISPENSARIO_NOTAS.md`,
`CONTEXTO_SIIFA.md`,
`ENTREGA_MODULO_ADRES_FURIPS.md` (entrega técnica del módulo ADRES).

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
  Además se escribió la **documentación técnica de entrega del módulo de
  diagnóstico del Lote V2** (`docs/diagnostico_lote_v2_pendientes/DOCUMENTACION_MODULO.md`)
  para consolidarlo en el proyecto principal sin perder conocimiento.
- **27-07:** se generó el **informe técnico completo** de todo el trabajo
  realizado (bot + evidencias + mejoras + lotes): 1.075 facturas procesadas,
  45.134+ glosas respondidas, 7 mejoras al bot, 8 lotes cerrados o en proceso.
  Publicado como artifact para socializar ante gerencia. Se generó también el
  cruce de **2.215 facturas vs. GI-33-5181-2026** (975 encontradas en los
  consolidados de este chat, 1.240 NA pendientes de lotes 03/04/05).
- **28-07 (hoy):** nace el **ajustador de detallados de factura**
  (`tools/ajustar_detallado_glosas.py` + README + 36 tests). Automatiza el
  trabajo manual de dejar el detallado **solo con lo que la entidad sigue
  glosando**: quita duplicados del consolidado, borra del Excel las hojas de las
  facturas que no se van a trabajar, quita el encabezado institucional (logo,
  NIT, QR, CUFE), cambia el título a **"DETALLADO DE FACTURA"**, cruza cada ítem
  contra el `ReporteGlosasReclamPAQUETE` (quita lo aprobado, ajusta lo aprobado
  a medias, deja lo glosado), borra los grupos que quedan vacíos y recalcula
  subtotal, total y **total en letras**. Deja bitácora CSV ítem por ítem y tiene
  modo `--diagnostico` para ver qué haría antes de escribir nada.
  **Hallazgo:** el reporte de glosas trae **el mismo ítem repartido en varias
  filas** (la venda de gasa de la HUS352890 viene en dos: 4 y 2 unidades). El
  bot las suma → siguen glosados **$47.000**, no $9.400 como quedó en el ejemplo
  hecho a mano. Falta que el auditor confirme ese criterio (ver PENDIENTE #11).
  **Validado contra el reporte real del paquete 31068** (19.256 filas, 581
  facturas): las **324 facturas del lote están todas** en el reporte y se
  reconocen sin ajustes. Del total reclamado **$2.870.214.655**, el ADRES aprobó
  **$1.835.864.089 (64%)** y **sigue glosado $1.034.350.566 (36%)**. De 9.616
  ítems: 6.805 se quitan, 472 se ajustan y 2.712 se dejan. El **32% de los ítems
  viene repartido en más de una fila** del reporte (el peor: 38 filas para la
  terapia respiratoria de HUS311371) y en el 1,1% de las filas la columna
  "Cantidad Aprobada" no cuadra con el valor — por eso el bot suma y calcula la
  cantidad desde el valor glosado.
  **Llegaron los 7 archivos de detallados y se corrió el paquete 31068 completo.**
  El formato real resultó distinto del supuesto: **una sola hoja con todas las
  facturas apiladas** (no una hoja por factura) y cada dato dentro de una celda
  combinada cuyos límites NO coinciden con los del encabezado. Se reescribió el
  núcleo del bot: segmentación de facturas dentro de la hoja, mapeo de columnas
  por solapamiento de rangos, borrado masivo de filas re-indexando en sitio
  (0,3 s en vez de minutos) y emparejamiento por rondas con unicidad mutua.
  **Resultado: 320 de las 324 facturas procesadas** (150.919 filas de entrada),
  $2.464.092.099 facturados de los cuales **siguen glosados $714.332.225 (29,0%)**.
  Se generaron 5 Excel ajustados + bitácora ítem por ítem + resumen por factura.
  Un análisis en paralelo sobre los 4 primeros archivos (1.306 facturas) destapó
  que **los procedimientos quirúrgicos traen renglones de DESGLOSE sin
  consecutivo** cuyo valor ya está incluido en el renglón de arriba: son 3.794
  renglones en 302 facturas y sumarlos inflaba el valor de la factura en
  $628.947.541. Ya se descuentan. Nace también
  `tools/verificar_detallado_ajustado.py`, que relee el Excel ajustado y lo
  contrasta contra el original, el consolidado y el reporte del ADRES: los 5
  archivos pasan sin fallas.
  Además nacen dos herramientas más, encadenadas con el ajustador:
  **`tools/dividir_detallado_por_factura.py`** (separa el detallado en un Excel
  por factura, con el formato intacto y el área de impresión ya fijada) y
  **`tools/excel_a_pdf.py`** (convierte en masa a PDF con el Excel del equipo o
  con LibreOffice, uno por archivo, con opción de carpeta por factura).
  Se generaron los **320 Excel y los 320 PDF** del paquete 31068 y se
  comprobó, leyendo el texto de cada PDF, que traiga su número de factura y que
  su total cuadre con la bitácora: los 320 cuadran ($714.332.224 contra
  $714.332.225, 1 peso de redondeo).

### Agosto 2026 — Pre-auditoría del paquete ADRES
- **03-08:** llegó la macro `NUEVO MODELO MACRO PARA DAR RESPUESTA A GLOSA ADRES
  31068`. Es el reporte del ADRES (16 columnas) **más 10 que el equipo llena a
  mano** sobre 4.619 filas glosadas. Se analizó y se descubrió que **siete de esas
  diez son mecánicas**: el código numérico sale de la causal (verificado contra
  las 2.989 que llenaron a mano: **cero discrepancias**) y la clasificación
  también (determinística en 47 de 48 causales).
  Nace **`tools/preauditar_glosas_adres.py`**: llena lo mecánico, propone el
  resto con el motivo escrito y **respeta lo que el equipo ya escribió**.
  Reproduce la macro renglón por renglón: 4.619 de 4.619 filas, y la columna
  RTA GLOSA COMPLETA sale **carácter por carácter idéntica**. El centro de
  costos pasó de 0 a 4.248 de 4.619 propuestos. Replica también el Word de
  respuesta por factura del VBA, sin depender de Word.
  El bot **no decide**: las 4.604 decisiones de aceptar/objetar/subsanar siguen
  siendo del auditor; la sugerencia va en columnas aparte (27 en adelante) para
  no correr nada de lo que usan las macros. A medida que el equipo decida, el
  bot aprende **su** criterio por causal y lo propone citando en cuántos casos
  se basa.
  **Hallazgo:** la causal **4506** está clasificada de dos formas distintas
  (231 veces FACTURACION y 24 PERTINENCIA) — hay que unificar el criterio.
- **04-08:** todo ese trabajo **se llevó a la página**. En el menú se quitó
  **Cobranza Live** (no se usaba) y en su lugar quedó **📄 Glosas ADRES**.
  Ahora el coordinador carga el `ReporteGlosasReclamPAQUETE` una sola vez
  (opcionalmente también el Excel de la macro y la bitácora del ajustador de
  detallados) y **el gestor solo escribe el número de factura**: la pantalla le
  trae las glosas clasificadas, el centro de costos, el gestor y el médico, la
  sugerencia de respuesta **con su motivo escrito**, el detallado cruzado
  (qué le pagó ya el ADRES y qué sigue glosado) y el texto consolidado para el
  Word.
  Se agregaron 3 tablas (`paquetes_adres`, `glosas_adres`,
  `items_detallado_adres`), el servicio `app/services/preauditoria_adres.py`
  y el router `app/api/routers/glosas_adres.py` con 8 rutas.
  El módulo web **no copia** las reglas: importa las mismas de
  `tools/preauditar_glosas_adres.py`, así un cambio de criterio sirve para los
  dos lados.
  Probado de punta a punta con el paquete real: **4.619 glosas, 324 facturas,
  $1.034.350.562 glosado** y 9.982 renglones de detallado, entrando por los
  endpoints de verdad. Se verificó lo que más duele si falla: **volver a cargar
  el paquete no borra las decisiones ya tomadas**, y aplicar las sugerencias en
  bloque tampoco pisa lo que un gestor escribió a mano.
  La pertinencia médica **sigue sin sugerencia**: la firma un médico auditor.
  Guía para el equipo en `docs/GLOSAS_ADRES_WEB.md`.
- **30-07:** **nace el proyecto SIIFA** (plataforma del Ministerio de Salud,
  distinta de COOSALUD/SIMED/DGH — la portalidad nacional de seguimiento de
  facturas). El auditor mostró la pantalla `Listar seguimientos` (2.579
  registros, sin botón de exportar) y subió los manuales oficiales y la
  documentación técnica de la API (swagger, colección Postman, manual de
  interoperabilidad). Hallazgo clave: **SIIFA sí tiene API REST oficial** de
  interoperabilidad (a diferencia de COOSALUD/SIMED), documentada y con
  endpoints específicos para listar y responder glosas — así que las dos
  herramientas nuevas hablan HTTP directo, sin navegador:
  - `docs/CONTEXTO_SIIFA.md`: plataforma, roles (IPS/ERP/FITS), autenticación
    JWT, catálogo de endpoints usados, y los plazos del trámite de glosa
    (Res. 1962/2025, Ley 1438/2011 Art. 57: 15 días hábiles para responder,
    7 para subsanar una glosa reiterada).
  - `tools/siifa_client.py`: cliente compartido (login, paginación automática,
    respuesta de glosas).
  - `tools/siifa_reporte_seguimientos.py`: trae TODOS los seguimientos del HUS
    (paginando solo) y arma el Excel masivo que pedía el auditor, con hoja de
    resumen por EPS.
  - `tools/responder_glosas_siifa.py`: el "bot tipo COOSALUD" pedido — lee un
    Excel tipificado y carga cada respuesta por API, con el mismo patrón de
    piloto/reporte CSV/`--saltar-csv` que el bot de COOSALUD.
  - Las tres piezas se probaron de punta a punta contra un servidor SIIFA de
    prueba (simulado, no el real) para validar el flujo completo: login →
    paginación → export a Excel → piloto de 1 glosa → cargue masivo con un
    error simulado → reintento sin duplicar. Todo funcionó como se diseñó.

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

### 24 de julio de 2026 — Expediente Inteligente de Conciliación (Hoja Maestra)
- **Nueva herramienta `tools/hoja_maestra_conciliacion.py`:** arma en un solo
  Excel el **expediente de conciliación** del Dispensario con **un único
  registro maestro por factura** (nada duplicado). Cruza las tres bases que ya
  existen (no transcribe ni inventa):
  - **CARTERA** (corte 30/06/2026) como columna vertebral: 5.571 facturas, con
    su valor, saldo, estado de glosa, edades y lo levantado/aceptado/ratificado
    en actas.
  - **RECEPCIÓN DE OBJECIONES** (la glosa que puso la EPS): trae el **motivo
    exacto de la EPS** en texto (ej. *"SE RECONOCE A TARIFA SOAT... SIN
    CONTRATO"*), el concepto, el CUPS y el servicio.
  - **TRÁMITE DE OBJECIÓN** (nuestra respuesta): el valor objetado, el valor
    aceptado y el **argumento del ESE HUS** (ej. *"ESE HUS NO ACEPTA GLOSA..."*).
    Se une a la recepción por el consecutivo (4.063 de 4.066 cruzan).
- **El libro entregado tiene 5 hojas:** `00_DASHBOARD` (tablero con 15
  indicadores + cartera por vigencia/estado/edades), `01_MAESTRA` (una fila por
  factura, con resultado final a color), `02_GLOSAS` (una fila por glosa con el
  **motivo de la EPS y nuestra respuesta lado a lado**), `03_ACTAS` (una fila
  por factura+acta) y `04_CRUCES` (los 11 controles de consistencia).
- **Cifras que cuadran con lo ya verificado:** glosado $7.000.506.193; aceptado
  por IPS $1.122.029.872; **levantado a favor del HUS $707.499.754**;
  **ratificado (pdte. conciliar) $980.141.374**; saldo pendiente DGH
  $13.621.817.613. Total: 5.571 facturas (3.935 con glosa), 18.378 glosas (179
  aún sin respuesta). Se excluye el acta AC000639 por ser **duplicada** de la
  SINAC 720.
- **Lo que ninguna base trae queda marcado PENDIENTE** (no en blanco): la
  bandera de factura electrónica (CUFE), la normatividad citada por respuesta,
  el valor pagado real, y las **raíces exactas Y:/X:** de los soportes (por
  ahora se deja la ruta derivada por mes AAAAMM + la de factura electrónica
  `\\172.16.32.83\factura_electronica_net22\AAAAMM`). Con pruebas.

### 27 de julio de 2026 — Acta de conciliación de las 147 facturas (formato SINAC)
- **Cambio de enfoque pedido por el auditor.** El expediente del 24-jul cubría
  las 5.571 facturas de toda la cartera. El auditor lo devolvió: *"el universo
  de trabajo son únicamente las 147 facturas que actualmente están pendientes
  por conciliar"*. Ahora todo gira alrededor de esas 147.
- **Identificación del universo (antes de construir nada).** Las 147 salen del
  `HUS.xlsx` que envió el Dispensario (el mismo lote del `CONCILIACION.xlsx`):
  **147 facturas / 444 glosas**. Se cruzaron contra el estado de cartera: **146
  de 147 cruzan**; la única que no aparece en cartera es **HUS0000443525**. El
  estado de glosa de las 147 confirma que todas están pendientes (98
  ratificadas pdte. conciliar, 25 parte levantada/parte ratificada, 23 en
  trámite DGH). Se entregó el listado `LISTADO_147_PARA_APROBAR.xlsx` para
  revisión previa.
- **Nueva herramienta `tools/generar_acta_conciliacion_dispensario.py`:** arma
  el acta **sobre el archivo real del ACTA SINAC N.º 720** (no una imitación):
  conserva logos, encabezado oficial, celdas combinadas, zona de firmas y
  macros. Solo cambia el contenido. La tabla se expande de 11 a **444 filas**
  sin romper el formato.
- **Lo que quedó en el acta:** una fila por glosa, **agrupadas por factura** y
  ordenadas de mayor a menor valor glosado (al abrir una factura se ven todas
  sus glosas seguidas — la HUS0000452150 con sus 62). Cada fila trae el
  **motivo exacto de la EPS** y, al lado, **nuestra respuesta completa**, más
  código, tipificación, valores, fechas, radicados, resultado en actas
  previas, rutas de soportes y de factura electrónica (con hipervínculo).
- **Hoja DASHBOARD** (la primera del libro) con los 12 indicadores pedidos,
  todos como **fórmulas vivas**: al diligenciar la mesa el tablero se
  actualiza solo.
- **Cifras verificadas:** 147 facturas · 444 glosas · facturado
  **$1.267.976.805** (sin duplicar por factura) · glosado y pendiente por
  conciliar **$317.640.524** · aceptado en trámite **$1.758.956** ·
  recuperable **$315.881.568**. 471 fórmulas, **0 errores**.
- **Columnas completadas con el estado de cartera** (a solicitud del auditor):
  *VALOR ACEPTADO EN TRÁMITE* (8 facturas, $1.758.956), *CENTRO DE COSTO*
  (444 de 444 líneas, del export de recepción) y *ABOGADO ASIGNADO* (115
  facturas). La *CUENTA CONTABLE* quedó en **PENDIENTE**: no existe en
  ninguna base disponible (ni en el acta 720 original).
- **Tres hallazgos para llevar a la mesa:** (1) la entidad **no ha confirmado
  el recibo de ninguna de las 444 respuestas**, aunque todas tienen radicado
  de entrega; (2) **29 facturas** tienen diferencia entre el valor glosado del
  lote y el de la cartera; (3) el lote dice que **no aceptamos nada** (RE9901)
  pero la cartera registra **$1.758.956 aceptados** en 8 facturas — hay que
  aclararlo antes de firmar.
- **Documentación de entrega:** `docs/MODULO_CONCILIACION_DISPENSARIO.md`, con
  todo el módulo (objetivo, arquitectura, funciones, flujo, riesgos,
  pendientes y cómo fusionarlo al proyecto principal).

---
### Julio 2026 — Frente ADRES/FURIPS (chat "VALIDADOR ADRES", PR #173-#176)
- **17-07:** nace el **bot validador FURIPS**: valida masivamente los TXT
  FURIPS 1 y 2 contra la Circular 022 de 2023 de la ADRES (102 + 9 campos,
  obligatoriedad condicional) y cruza cada factura con sus soportes (RIPS,
  CUV, factura XML DIAN, factura PDF, epicrisis). Informe Excel de 7 hojas
  con semáforo. Revisión adversarial de 28 agentes: 22 correcciones el mismo
  día. También el **informe de baja de cartera** (Res. 577/2019): Word para
  presentar + Excel de relación, leyendo el PDF unido de cada factura.
- **21-07:** afinación con datos reales: direcciones con nomenclatura
  completa (campos 15/50/60), PDF escaneados sin falsos errores,
  representación gráfica DIAN cruzada contra la epicrisis, informe de baja
  en carpeta plana con progreso. **APP WEB "Validador ADRES"**
  (`validador-adres/`): validación desde el navegador con tablero, semáforo,
  gráficas y descarga del Excel. Bot `PDF_A_CMD_EN_CARPETA` (carpeta
  `CMD_CONVERTIDOS`) y blindaje CRLF de todos los `.cmd`. Corrida real de
  las 50 facturas ADRES: 27 con errores, 18 por revisar, 5 cumplen.
- **22-07:** **bot del informe XML DE4401 de NUEVA EPS** (411 facturas
  devueltas): busca el XML DIAN de cada factura y completa valor, contrato,
  cobertura, validación DIAN (CUFE, firma, acuse 02), conclusión con norma
  (Res. 506/2021 y 2275/2023) y respuesta para el portal DGH.
- **23-07:** el servidor guarda cada factura en su subcarpeta con nombres
  genéricos (`ad0901….xml`) → el bot busca también por el nombre de la
  subcarpeta, dentro de los **.zip** DIAN, verifica el número POR DENTRO del
  XML, y deja una hoja **DIAGNOSTICO** en el Excel (versión 2.1) para
  diagnosticar corridas a distancia.
- **27-07:** **documentación técnica de entrega del módulo**
  (`docs/ENTREGA_MODULO_ADRES_FURIPS.md`). **OCR automático** para PDF
  escaneados en el validador y el informe de baja (Tesseract o RapidOCR,
  se instala solo desde el .cmd; el soporte queda "SI (OCR)"). Soportes
  reconocidos a cualquier profundidad (subcarpetas internas, sueltos en la
  raíz) y con nombres genéricos (epicrisis.pdf, fe.xml, ResultadosMSPS.json).
  Se entregó el **PAQUETE COMPLETO** en ZIP (5 frentes + documentación).
- **29-07:** el **PR #176 quedó FUSIONADO** en la rama principal (se
  resolvieron dos rondas de conflictos con los otros chats — bitácora,
  CLAUDE.md y dos archivos de pruebas que ambos frentes habían corregido
  igual). Los lanzadores `.cmd` ahora muestran el avance de la descarga del
  OCR (~200 MB la primera vez) para que no parezcan congelados; el auditor
  ya corrió el validador con OCR en su PC ("YA ARRANCO TODO BIEN").

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
- **Faltaba un caso (corregido enseguida):** cuando el auditor audita **desde
  la ventana del oficio** (que es como se trabaja normalmente), esa ventana
  no se refrescaba. Seguía mostrando los contadores viejos "Pend · OK · Dev"
  y, como el botón del oficio de devolución se habilita según ese dato, se
  quedaba bloqueado aunque ya hubiera facturas devueltas: por eso "no dejaba
  generar el PDF" y tocaba recargar. Ahora esa ventana se actualiza sola al
  guardar. Además, cuando el botón está bloqueado **dice por qué**: el oficio
  de devolución solo se puede generar si hay al menos una factura devuelta,
  porque es la carta con la que se le regresan las facturas a la entidad.

### 28-07 (tarde) — Pre-auditoría: el consecutivo del oficio lo escribe el auditor
- El auditor recordó un pedido anterior: **la numeración de los oficios de
  devolución la lleva SINAC internamente**, así que el sistema no debe
  asignarla sola. Ahora, al oprimir **"Generar oficio de devolución"**, se
  abre una ventana para **escribir el consecutivo que corresponde**.
- Viene precargado con el que seguiría según lo registrado en la página (solo
  como sugerencia) y se puede cambiar. Se acepta escribir **solo el número**
  (`89` → se completa como DEV-PRE-AUD-0089-2026) o el **consecutivo
  completo**. Si se escribe uno ya usado, el sistema lo rechaza diciendo en
  cuál oficio está. Si se deja vacío, usa el sugerido.
- La sugerencia siguiente continúa desde el que se escribió (si usó el 89, la
  próxima vez sugiere el 90).
- 3 pruebas nuevas + prueba en navegador de la ventana completa.
- **Ya quedó desplegado en la VM** (PR #208 fusionado). No hubo que hacer nada
  a mano: el auto-despliegue que corre cada 5 minutos lo aplicó solo y el
  motor quedó corriendo el commit `5ba3a3f`, sano. Para verlo en pantalla hay
  que refrescar el navegador con **Ctrl+F5** (si no, muestra la versión vieja
  que tiene guardada).
- **Nota para no perder tiempo la próxima vez:** en la VM el repositorio está
  en `/opt/motor-glosas` y el motor corre en **Docker**, no como servicio de
  systemd. El comando para mirar cómo está, desde Cloud Shell y en un solo
  paso (entra a la VM y ejecuta allá adentro):

  ```bash
  gcloud compute ssh motor-glosas --zone=us-west1-a --tunnel-through-iap --command '
  cd /opt/motor-glosas && git log --oneline -1
  sudo docker compose ps
  free -m | head -2
  '
  ```

  Cuidado con confundir las dos máquinas: si el prompt dice `@cloudshell`
  estás **fuera** de la VM y los comandos no encuentran nada; dentro de la VM
  el prompt dice `@motor-glosas`.

- **PENDIENTE importante (para que no vuelva a pasar):** con archivos de este
  tamaño, la solución de fondo es que **el cargue no haga esperar al
  navegador**: subir el archivo, responder de inmediato "recibido, procesando"
  y que la página muestre el avance. Así el tamaño del archivo deja de
  importar y no hay límite de tiempo que valga. Queda propuesto.
- **~~PENDIENTE recomendado~~ — YA HECHO:** subir la máquina virtual a
  **`e2-small`**. Al revisar la VM el 28-07 la memoria total salió en 1.971 MB
  (~2 GB): la `e2-micro` tiene 1 GB y la `e2-small` tiene 2 GB. Se confirmó
  además preguntándole directamente a Google, que respondió `e2-small`:
  `gcloud compute instances describe motor-glosas --zone=us-west1-a --format="value(machineType)"`
  No hay que detener ni editar nada.

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

### 28-07 (noche) — Verificación adversarial del lote de glosas Dispensario del 28-jul
- Lote de **97 objeciones**. Solo se atacaron las **6 decisiones nuevas** (el
  resto del banco de plantillas ya pasó 4 rondas adversariales y no se re-evalúa).
- Resultado: **3 calzan con reserva** (FA0201 equipo interdisciplinario,
  FA2303 transfusión, TA listado→tarifa) y **3 NO calzan** (FA0801 segundo
  rastreo de anticuerpos, SO5801 biopsia endometrio/AMEU, FA0101 conteo de
  días de estancia).
- **Veredicto: el lote NO está listo para subir.** Hay correcciones de texto
  obligatorias antes del cargue:
  - Quitar frases que refutan reclamos que el pagador no hizo ("no se anexa
    acuerdo de tarifas", "paquete", "procedimiento principal", SOAT UVB):
    delatan respuesta enlatada y permiten descalificarla por no pertinente
    (la Res. 2284/2023 exige coherencia entre glosa y respuesta).
  - Responder los prongs reales de cada observación: identificación del
    equipo interdisciplinario y defensa de la cantidad 29 (FA0201); la tesis
    "enfermería está incluida en la estancia" (FA2303: la estancia cubre el
    cuidado básico, no procedimientos con renglón propio); la regla de 72
    horas del banco de sangre (FA0801: voltearla — la muestra pretransfusional
    VENCE a las 72 h en paciente transfundido, Decreto 1571/1993, o sea el
    nuevo evento OBLIGA al nuevo rastreo); la homologación AMEU→legrado
    (SO5801); y el conteo aritmético 32 vs 34 días (FA0101).
  - Quitar frases autolesivas: la remisión genérica a la nota operatoria en
    SO5801 (si la nota no describe biopsia aparte, confirma la glosa) y la
    prueba de "permanencia del día objetado" en FA0101 (34 días no caben
    entre el 17-may y el 18-jun); en TA, afirmar la vigencia 2026 del
    contrato 440 (prórroga/adiciones), no solo que el pagador "es parte".
- Verificaciones del auditor antes de cargar esos grupos: leer la nota
  operatoria del caso AMEU (¿hubo toma de biopsia como acto aparte?);
  reconstruir día a día los 34 días de estancia (si solo se prueban 32-33,
  procede aceptar parcial el excedente, no forzar el 100%); fechas y horas de
  los 2 rastreos de anticuerpos con su orden médica; otrosí o prórroga que
  acredite la vigencia 2026 del contrato 440-DIGSA/DMBUG-2025.

### 28-07 (noche) — Contrato de Construcción de SINAC OS: el plano se volvió obra

Hasta hoy teníamos el **plano** (el Manual de Arquitectura: qué queremos que
sea SINAC OS). Faltaba el **contrato de obra**: qué se construye, en qué orden,
quién lo aprueba y cómo se comprueba que quedó bien. Eso es lo que quedó hecho.

Está en `docs/CONTRATO_CONSTRUCCION_SINAC_OS.md`: **veinte capítulos y un
anexo**, unas 323.000 palabras. Cada capítulo termina con una tabla donde toda
fila tiene **criterio de aceptación** y **el comando exacto que lo comprueba**,
para que nadie tenga que preguntar si algo quedó hecho. En total **730 tareas**.

**Lo importante para el área, en una frase:** de las 730 tareas, **69 producen
los siete resultados que usted puede ver funcionando**, y cuestan 163,5 jornadas
—el 10 % del esfuerzo total—. Las otras 661 el Contrato nunca las amarró a un
resultado visible.

Los siete resultados, en el orden en que llegarían:

1. **La plata deja de contarse mal.** Un solo lector de valores en pesos: se
   acaba el error del ×100 que hacía leer `950.000` como `950`.
2. **Lo vencido deja de esconderse.** Encabeza la lista en vez de desaparecer
   de ella, y escala solo al coordinador. Es el caso de las tres facturas de
   junio por $20.054.751 que se descubrieron 45 días tarde.
3. **Una entidad nueva se activa sin programar.** SIMED encolable desde una
   ficha, sin esperar semanas de desarrollo.
4. **Un expediente por factura y una sola cifra por concepto.** Se acaba que
   "recuperado" dé cuatro números distintos según la pestaña.
5. **Un solo documento radicable**, generado en un solo lugar.
6. **El robot corre solo y se ve mientras corre**, con la plata en juego a la
   vista.
7. **Una institución nueva queda instalada en una jornada.**

**Cuatro problemas se encontraron al juntar los capítulos** y quedaron
corregidos o registrados:

- **El plan eran diecinueve planes que no se miraban.** De 773 dependencias
  declaradas, 742 apuntaban a una tarea del mismo capítulo: casi ninguna decía
  que el trabajo de un capítulo necesita el cimiento que vive en otro. Se
  agregaron 563 dependencias derivadas de nueve cimientos escritos, con la
  regla a la vista para que se pueda discutir.
- **La columna que separa los datos de una institución de los de otra tenía
  tres nombres** (`institucion_id`, `hospital_id`, `tenant_id`). Construido así
  quedaban tres columnas para lo mismo, y la protección de datos se activa
  sobre una sola: las tablas con las otras dos quedaban abiertas. Se unificó en
  `institucion_id` (287 reemplazos y 8 líneas a mano). Se eligió ese nombre
  porque SINAC OS también debe poder instalarse en una clínica o en una IPS.
- **Más de la mitad del plan estaba marcada como urgente** (380 de 730). Una
  urgencia que le toca a la mitad no prioriza nada. Se volvió a priorizar con
  una regla verificable: P0 es lo que hace falta para los tres primeros
  resultados y nada más. Quedaron 37.
- **El Contrato completo compromete casi siete años de una persona**
  (1.625,5 jornadas). Se dice sin adornos: **no es ejecutable de punta a punta**
  con el equipo de hoy. Por eso el anexo separa lo que sí cabe.

También se cerraron defectos que habrían costado retrabajo: ocho dependencias
apuntaban a tareas inexistentes, el capítulo 14 numeraba 40 tareas con códigos
que ya significaban otra cosa en otros capítulos (`GOB-09` era "parser
monetario" en uno y "política de vida de rama" en otro), y dos tareas se
declaraban prerrequisito de sí mismas. Todo eso quedó arreglado y explicado en
el **Anexo I**.

**Las cifras del Contrato se comprueban solas.** La portada trae una tabla que
vuelve a medir contra el repositorio lo que el documento afirma. Hoy: 43 tablas,
4.530 pruebas, 59 ramas sin fusionar, 44 llamadas a `prompt()` y 1 sola
migración formal **coinciden**; las rutas de la API subieron de 686 a 712
porque el sistema siguió creciendo mientras se escribía.

**La Regla 11 quedó cumplida en los veintiuno.** Todo capítulo cierra
respondiendo qué habría que cambiar para soportar 100 hospitales, 10 millones
de expedientes y 10.000 usuarios a la vez. De esas respuestas salió un defecto
que ningún capítulo podía ver solo: **la escala de referencia tiene tres cifras
distintas para la misma cosa** —2.350.000, 4.000.000 y 6.000.000 de objeciones
para los mismos 500.000 expedientes— y dos para el almacenamiento (2,4 TB
contra 8 TB). La medida es la primera: sale del acervo real del hospital,
18.371 objeciones para 3.933 facturas. No se corrigió porque elegir la cifra
buena decide el tamaño de medio Contrato, y esa decisión es del área.

Todo esto es **documentación y plan**. No se tocó una línea del código que
corre en producción: la suite de 4.533 pruebas pasa igual que antes.

### 29-07 — Pre-auditoría: lo que escribía el auditor se perdía

Día de uso real con cuatro auditores trabajando (Vanessa, Camilo, Edgar y
Yesid) y tres arreglos que salieron de lo que ellos vieron en pantalla.

**1. Las observaciones no se guardaban (PR #220, ya en producción).**
El auditor reportó que escribían "OKAY SOPORTES" al radicar y la columna
Observaciones del historial salía vacía en todas las facturas. La causa no
era el historial: **el texto se descartaba en silencio**. La ventana de
auditar tiene dos recuadros —"Motivo de la devolución" arriba y
"Observaciones" abajo— y escribían en el de arriba, que es el que más se ve.
Al radicar, ese motivo no se guardaba en ninguna parte.

Cómo se confirmó, contra la base de producción: **0 de 55** facturas y
**0 de 79** eventos tenían observación guardada, mientras que 4 eventos sí
tenían motivo (todos de devoluciones). Ese contraste fue la prueba.

Ahora nada de lo que escribe el auditor se descarta: si escribió solo en
Motivo, ese texto queda como la observación; si escribió en los dos, se
conservan ambos. Además se pueden **anotar las facturas ya radicadas** sin
revertir la decisión (botón "✎ Guardar observación" en el historial), y los
dos recuadros quedaron rotulados sin ambigüedad, con Observaciones primero.

**2. Se pueden borrar los oficios de devolución (PR #225, ya en producción).**
Cuando el PDF salía con el consecutivo equivocado no había forma de
deshacerlo: el número quedaba quemado y las facturas atrapadas (con el oficio
emitido, revertirlas está bloqueado). Ahora hay un botón 🗑 en la pestaña de
oficios de devolución, **solo para administradores y coordinación**. Las
facturas no cambian de decisión —siguen devueltas— y solo quedan libres para
salir en un oficio nuevo; el consecutivo vuelve a estar disponible y el
historial no se borra. Avisa antes: si el PDF ya se entregó a la entidad, no
hay que eliminarlo.

**3. El PDF del oficio muestra los días transcurridos (PR #228).**
El documento solo traía la fecha de generación. Ahora el encabezado dice
cuándo se recibió el oficio (con hora), cuándo se generó el PDF y cuántos
días completos pasaron. **Un día solo cuenta pasadas 24 horas enteras:** del
22 a las 2:35 p.m. al 24 a las 11:23 a.m. hay 1 día, no 2, aunque el
calendario haya cambiado dos veces. Así el número no depende de la hora a la
que se registró el oficio. Las fechas salen de lo guardado, no del momento de
imprimir: reimprimir el mismo oficio meses después da el mismo documento.

**4. La lentitud: eran las búsquedas (PR #230).** El auditor dijo que la
página "se demora para sacar los datos". Se midió contra la base de
producción antes de tocar nada, y **todo el sistema estaba sano** menos una
cosa: las consultas del consolidado tardan entre 0 y 27 milisegundos, la red
responde en 70, el procesador va al 0,2% y sobra memoria — pero **buscar por
entidad tardaba 1.031 milisegundos**.

La razón: la entidad y el NIT no están en el consolidado (que son 55
facturas), sino en la tabla de la fuente, que tiene **189.452 filas**. Cada
búsqueda las recorría todas, y lo hacía **dos veces** (una para contar y otra
para traer la página): unos **2 segundos cada vez que alguien escribía en el
buscador**.

El arreglo: la fuente solo importa para las facturas que ya están en el
consolidado, así que ahora se buscan primero esas —por el número de factura,
que sí tiene índice— y el filtro de texto cae sobre ese puñado. Comprobado
reproduciendo la tabla real: **de 73 ms a 0,1 ms**, con resultados idénticos
en 7 patrones distintos. No cambia lo que se ve, solo cómo se llega.

**Lo aprendido sobre la VM, para no volver a perder tiempo.** Los comandos
que se intentaron primero fallaron porque en la VM el repositorio está en
`/opt/motor-glosas` (no en la carpeta personal) y el motor corre en **Docker**,
no como servicio de systemd. Además, **el despliegue es automático**: un
proceso revisa cada 5 minutos si hay código nuevo y lo aplica solo. Cuidado
con confundir las dos máquinas: si el prompt dice `@cloudshell` se está fuera
de la VM y nada se encuentra; dentro dice `@motor-glosas`. Comando para mirar
cómo está, desde Cloud Shell y en un solo paso:

```bash
gcloud compute ssh motor-glosas --zone=us-west1-a --tunnel-through-iap --command '
cd /opt/motor-glosas && git log --oneline -1
sudo docker compose ps
free -m | head -2
'
```

### 29-07 (segunda parte) — El contrato correcto, en todas las pantallas

Sprint de construcción del día (varios PR fusionados en cadena):

- **Al analizar una glosa, manda la fecha del hecho.** El dictamen cita el
  contrato que regía el día de la atención, no el de hoy. Si ese día no regía
  ninguno (ej.: COMPENSAR después del 3 de abril de 2026), la IA recibe la
  alerta y defiende a tarifa SOAT plena en vez de citar un contrato muerto.
- **Cada análisis deja constancia en el expediente.** En la línea de tiempo de
  la glosa queda escrito qué contrato se usó, si estaba vigente ese día y con
  qué factor, en una frase clara y con color según el veredicto: verde
  (vigente), ámbar (sin contrato ese día), rojo (pagador fuera de la malla).
  Cuando la EPS discuta la tarifa meses después, la respuesta está escrita en
  el expediente, no en la memoria de nadie.
- **El asistente del chat ya consulta la malla.** Preguntas como «¿qué
  contrato de COMPENSAR regía en septiembre?» se responden con la malla
  oficial, y el asistente tiene prohibido citar un contrato sin verificar
  primero que regía el día del hecho.
- Pantallas nuevas de los días previos, ya fusionadas y desplegadas:
  **Contratos** (malla completa con buscador, filtros de un clic y semáforo de
  vencimientos, más el buscador de material de osteosíntesis con la defensa
  lista para pegar) y **Automatización** (robots de cartera desde el
  navegador, arrastrando el archivo).

### 29-07 (tercera parte) — Épica: el Expediente Inteligente

- **Pantalla nueva «Expediente»** en el menú: se busca por ID de glosa o por
  factura y aparece TODO en un solo lugar — la ficha, el contrato que rige
  con su color (verde/ámbar/rojo), las conciliaciones, los soportes y la
  línea de tiempo completa con filtros de un clic. El popup viejo de
  timeline (ventana aparte) se eliminó: el botón 📜 ahora entra acá.
- **El acta de la mesa se cuadra sola.** En la pantalla Conciliación se sube
  el mismo Excel que se diligencia en la audiencia (el de las 147 del
  Dispensario, por ejemplo) y el sistema: dice qué no cuadra (fila por
  fila), devuelve el libro optimizado con el resultado de cada línea y una
  hoja REVISION, y arma el acta lista para imprimir y firmar con la cláusula
  de mérito ejecutivo y las firmas leídas del propio libro. Probado con el
  acta real: 444 líneas, 147 facturas, $317.640.524 glosados y los
  $11.836.399 levantados, cuadre exacto.
- **La IA ya consulta expedientes**: en el chat se puede preguntar «¿qué ha
  pasado con la factura HUS…?» y responde con la misma información de la
  pantalla. Cada uso del acta queda registrado en la auditoría del sistema.
- Guía corta en `docs/EXPEDIENTE_INTELIGENTE.md`.

### 29-07 (cuarta parte) — Épica: el Centro de Inteligencia + arreglo de producción

- **El sistema ahora dice qué hacer hoy.** Nueva primera opción del menú:
  **Inteligencia**. Barre toda la operación —glosas vencidas y por vencer
  con su plata, contratos caídos o por caer, análisis defendidos sin
  contrato, audiencias encima sin acta, actas a medio cuadrar— y entrega
  la lista de acciones ordenada por urgencia y valor, cada una con el
  botón que lleva a la pantalla donde se resuelve. El número rojo del
  menú (frentes urgentes) se actualiza solo.
- **La IA pasó de asistente a directora**: al preguntarle «¿qué hago
  hoy?» corre el mismo barrido y dirige — empieza por lo rojo, dice la
  plata en juego y qué abrir primero.
- **Se arregló la causa raíz del «Error 500» de Automatización en el
  servidor**: la imagen de producción no llevaba la carpeta de
  herramientas (regla vieja del empaque). Quedó la lista blanca, una
  guardia en la suite para que no vuelva a pasar, y además ningún robot
  vuelve a contestar «Error 500» pelado: ahora explican qué pasó.
- Guía corta en `docs/CENTRO_INTELIGENCIA.md`.

### 29-07 (quinta parte) — Épica: el Centro Documental

- **La carpeta de cada expediente se arma sola.** Dentro de la pantalla
  Expediente aparece «📁 Centro Documental»: el PDF radicable del
  dictamen, el dictamen en texto, el historial de versiones, el acta de
  cada mesa de conciliación, el paquete de evidencia para jurídica y los
  soportes de la factura que el indexador encontró en el share — cada
  uno con su botón de descarga o su ruta. Se acabó buscar «todo lo de
  esta factura» a mano.
- Los soportes del share NO se sirven por la web (son historia clínica):
  se muestra la ruta para abrirlos desde el equipo del hospital, como
  siempre.
- La misma carpeta la entrega la API y el chat IA («¿qué documentos hay
  de la factura…?»). Guía corta en `docs/CENTRO_DOCUMENTAL.md`.

### 29-07 (sexta parte) — Épica: el Motor Universal

- **Un perfil único por pagador.** En la pantalla Contratos, al expandir
  cualquier pagador aparece «El sistema con este pagador»: si el análisis
  cita su contrato por fecha, si hay respuesta masiva por lotes y con qué
  bot, qué conversores de Automatización le aplican y si hay contacto de
  radicación. Lo mismo responde el chat («¿qué se puede hacer con
  COOSALUD?») y la API.
- **La regla que queda sellada**: agregar un pagador o una capacidad
  nunca vuelve a ser tocar código repartido — es agregar una ficha en el
  registro que corresponde (malla, perfil de lote o catálogo de
  automatización) y el perfil la muestra solo en las tres superficies.
- Guía corta en `docs/MOTOR_UNIVERSAL.md`.

### 03-08 (tercera parte) — El Centro de Inteligencia vigila los bots y los lotes

- El barrido del día ganó dos ojos nuevos: **los trabajos de bots que
  fallaron** esta semana (con qué bot y a dónde ir a reintentarlos) y los
  que llevan **más de una hora en cola sin que ningún PC los reclame**
  (señal de que el agente de bots no está abierto), y **los lotes de
  respuesta masiva que quedaron a medias** (completados con facturas
  pendientes o en error). Todo aparece en la pantalla Inteligencia y en
  el chat, con su botón directo a Automatización.

### 03-08 (segunda parte) — Ronda 35: el formato de respuesta que aprobó Yesid

- La respuesta del caso de la citología quedó como **modelo oficial del
  motor**: primera línea de referencia («RESPUESTA GLOSA … – FACTURA … –
  CUPS …»), postura seca, y **un punto numerado por cada reclamo de la
  glosa** — si la entidad reclama tres cosas, se contestan las tres, cada
  una con su norma. Ni reclamos sin contestar (eso es conceder), ni
  puntos de relleno.
- La respuesta completa entró además al banco de plantillas del motor
  (TA-G11) para el patrón «SOAT UVB sin contrato»: la próxima glosa así
  sale con esa misma factura de estilo.

### 03-08 — Ronda 34: dos reglas del caso TA0801/citología

- Del caso real que trajo Yesid (factura 1344527, citología 898015H,
  ajuste de $1.700 «SOAT UVB»): el motor aprendió que **«se reconoce SOAT
  UVB» + «sin acuerdo de voluntades» NO significa accidente de tránsito**
  — significa que la entidad liquida a SOAT por falta de contrato. La
  defensa correcta: SOAT PLENO sin descuentos, UVB vigente a la fecha de
  atención (2026 = $12.110), y exigir el desglose del ajuste (los ajustes
  chicos suelen ser UVB del año anterior o descuentos que nadie pactó).
- Y que **«ayuda diagnóstica no interpretada» no existe en patología**:
  en citologías y estudios anatomopatológicos la interpretación ES el
  servicio — el producto es el informe del patólogo, que se anexa.

### 03-08 — El expediente entiende de facturas y lleva al trabajo

- **Buscar una factura en Expediente ahora muestra EL CASO completo**: una
  cabecera con el pagador, cuántas glosas tiene (y cuántas siguen
  abiertas), el total objetado y el aceptado — y cada glosa como una
  ficha de un clic para saltar entre ellas sin volver a buscar.
- **Del expediente al trabajo en un clic**: la ficha trae «Abrir en
  Analizar» (directo a trabajar la glosa) y «Ver toda la factura».

### 30-07 (segunda parte) — Las tarjetas de COOSALUD y SIMED cuentan su lote

- Los dos bots que trabajan por Lotes ya muestran **su cola real en la
  propia tarjeta**: qué lote va (archivo, cuántas facturas, quién lo
  subió), en qué equipo corre, y si terminó con facturas pendientes la
  tarjeta queda en ámbar «CON PENDIENTES» — nunca más un verde engañoso.
  El botón lleva directo a la pantalla de Lotes.
- Una revisión automática con verificadores independientes encontró
  cuatro defectos antes de publicar (botones que no aplicaban a lotes,
  el estado «completado con pendientes» invisible, y una consulta que
  cargaba el Excel completo de cada lote a la memoria del servidor —
  el mismo error que ya había tumbado la instancia una vez). Los cuatro
  quedaron corregidos y sellados con pruebas.

### 30-07 — Todos los bots del hospital, administrados desde la plataforma

- **Se acabó el doble clic a ciegas.** El Centro de Automatización ahora
  muestra los **35 bots del hospital** (COOSALUD, SIMED, FOMAG, MUTUAL SER,
  DGH, ADRES, NUEVA EPS, radicador, notas crédito, PDFs, informes…) con su
  estado en vivo: disponible, en cola, corriendo (con avance y en qué
  equipo), o en error (con el motivo). Cada tarjeta trae Ejecutar,
  Cancelar, Reintentar, Historial, Ver registros y Configurar.
- **Cola universal**: «Ejecutar» encola el trabajo; el **agente de bots**
  del PC del HUS (doble clic en `AGENTE_BOTS.cmd`, usa la misma URL y
  token del agente de lotes) lo reclama, lo corre y reporta — la tarjeta
  se actualiza sola. El agente no conoce ningún bot por nombre: el
  comando viaja desde el catálogo.
- Quién pidió qué bot, en qué equipo corrió, cuánto tardó y por qué falló:
  todo queda en la auditoría y en el historial de cada tarjeta.

### 29-07 (séptima parte) — Épica: el Constructor de Agentes

- **El sistema ya arma sus propios agentes.** Menú → Herramientas →
  **Agentes**: se escribe la misión, las instrucciones y se marcan las
  herramientas permitidas — y el agente queda corriendo con todo lo que
  el sistema sabe (expediente, malla, diagnóstico, soportes), pero SOLO
  dentro de su misión y sus herramientas. Sin programar nada.
- Dos plantillas de fábrica para arrancar con un clic: **Vigilante de
  vencimientos** y **Preparador de mesa**.
- Cada construcción, corrida y retiro queda en la auditoría (quién, qué
  agente, qué preguntó, qué herramientas usó).
- Guía corta en `docs/CONSTRUCTOR_AGENTES.md`.

### 30-07 — Pre-auditoría: una sola observación, corregible aunque el oficio ya exista

**1. La pantalla explica qué pasa con cada devuelta (PR #232).** El caso de las
3 facturas que "no salieron" en el oficio DEV-PRE-AUD-0099: sí habían salido,
pero en el oficio anterior (0097), y la pantalla no lo decía. Ahora el contador
de la ventana del oficio distingue cuántas devueltas **ya salieron** en un
oficio y cuántas **faltan por incluir**, el botón dice cuántas facturas saldrán
en el oficio nuevo, y cada factura muestra en cuál oficio salió. (Una factura
no se repite en dos oficios: la entidad recibiría el mismo cobro dos veces.)

**2. Un solo recuadro de observación (mismo PR #232).** La ventana de auditar
tenía dos recuadros —"Observaciones" y "Motivo de la devolución"— y seguían
prestándose a confusión: un texto de devolución del FURIPS quedó escrito en el
recuadro que NO sale en el oficio. A pedido del auditor quedaron en **uno
solo**: lo que se escriba ahí se guarda siempre y, si la factura se devuelve,
ese mismo texto es el que imprime el oficio de devolución.

**3. La observación se corrige aunque el oficio ya se haya generado.** Si el
oficio salió con un error en el texto, el auditor abre la factura con el botón
"👁 Ver", corrige la observación y la guarda. Si la factura ya salió en un
oficio de devolución, la corrección **también corrige el oficio**: el PDF se
arma cada vez que se abre, así que basta volver a abrirlo para verlo al día.
Los oficios de rondas anteriores no se tocan (esos ya se entregaron tal como
estaban) y cada corrección queda en el historial con quién la hizo y cuándo.

### 03-08 — Pre-auditoría: el registro de envíos "borrado" y la regla de los 3 oficios

**Qué se vio en pantalla.** La columna Envíos de casi todos los oficios
apareció vacía ("se borró toda la información") y al cargar un envío repetido
seguía saliendo "El envío ya fue cargado", aunque el viernes se había subido
un cambio para permitir el mismo envío en hasta 3 oficios.

**Qué pasó de verdad (nada de las decisiones se perdió).** El cambio del
viernes 31-07 modificó la regla en el código pero **no cambió el candado
dentro de la base de datos** que ya estaba en producción: la base seguía
exigiendo "un envío una sola vez en todo el sistema". Por eso siguió
bloqueando, y en el afán de destrabarlo el REGISTRO de envíos (qué envío
entró en qué oficio, quién y cuándo) quedó vacío. Importante: ese registro
es solo la "tabla de contenido" — los oficios, las facturas, las decisiones
de los auditores y el historial completo quedaron intactos (por eso las
columnas Facturas/Pend/OK/Dev siguen con sus números).

**Qué se hizo hoy:**
1. **La migración que faltaba**: al arrancar, el sistema ahora corrige solo
   el candado de la base — pasa de "un envío una sola vez" a "un envío una
   sola vez POR OFICIO". Con eso la regla de los 3 oficios funciona de
   verdad, sin tocar nada a mano.
2. **La regla completa de recarga**: el mismo envío se acepta en hasta
   **3 oficios distintos** (el original + las subsanaciones que facturación
   reenvía con el mismo número). Al recargar solo se mueven las facturas
   devueltas; las radicadas y pendientes se quedan donde están, con su
   aviso. El 4.º intento se bloquea nombrando los radicados. "Ver antes"
   avisa en qué oficios ya salió el envío y qué va a pasar si se carga.
3. **Recuperación del registro borrado**: el historial de cada factura es
   inmutable y guarda envío + oficio + auditor + fecha, así que se armó un
   comando (3 pasos: mirar → aplicar → aplicar todo) que reconstruye el
   registro de envíos desde ese historial, sin borrar ni modificar nada de
   lo existente. Probado contra una réplica local con el mismo escenario.
4. De paso se confirmó que el sistema **hace una copia de seguridad
   automática todos los días a las 3:00 a. m.** (guarda las últimas 14, en
   `/data/backups` de la VM).

**Lección para todos los chats:** cambiar un candado/índice en el código
SIN su migración deja producción con la regla vieja; y destrabar borrando
registros a mano borra la trazabilidad. Siempre: migración en el código +
piloto + PR, nunca DELETE a mano contra la base de producción.

**Endurecimiento posterior (mismo día, revisión adversarial):** se detectó
y corrigió que (1) eliminar el oficio original después de recargar su envío
en otro daba error 500 — ahora explica que las facturas ya subsanaron y no
se puede; (2) quitar el envío del oficio original tras la recarga devolvía
un cupo del tope de 3 en silencio — ahora se bloquea con su porqué; (3) dos
cargas simultáneas del mismo envío podían pasarse del tope o terminar en
error 500 — ahora la segunda recibe un aviso claro; y (4) la migración del
candado se auto-repara si un arranque muere a mitad de camino.

### 03-08 (segunda parte) — Solo administración corrige auditorías decididas + informe de gestión

A pedido del auditor:

1. **Las auditorías ya decididas quedan protegidas.** Revertir una factura
   radicada o devuelta, o corregir su observación (que también corrige el
   PDF del oficio de devolución, porque el PDF se arma al abrirlo), ahora
   es SOLO de coordinación o administración. El auditor sigue escribiendo
   su observación con normalidad al decidir, y mientras la factura esté
   pendiente. En la pantalla, quien no es administrador ve el botón
   bloqueado con la explicación, y el servidor lo exige de todos modos.
2. **Informe de gestión descargable.** En la pestaña Estadísticas quedó el
   botón "⬇ Informe de gestión (Excel)": un libro con 5 hojas — RESUMEN
   (totales y valores), POR AUDITOR, POR OFICIO, DEVOLUCIONES e HISTORIAL
   (el registro completo de eventos: qué se hizo, quién, cuándo, con motivo
   y observación de cada movimiento).

105 pruebas del módulo en verde.

---

### 03-08 (SIIFA) — el informe masivo por fin se baja completo

Día de corridas reales contra SIIFA con las credenciales del auditor. Cada
falla que apareció en pantalla quedó corregida el mismo día:

1. **El bot se colgaba a mitad de camino** (PR #249). Dos causas: el permiso
   de entrada (token) se vencía durante una descarga larga y nadie lo
   renovaba, y ante un error definitivo del servidor el bot volvía a
   intentar lo mismo una y otra vez. Ahora renueva el permiso solo y deja de
   insistir cuando el error no tiene remedio.
2. **No entraba con el usuario del auditor** (PR #252). El script pedía la
   variable con un nombre y el auditor tenía otro: ahora acepta
   `SIIFA_USERNAME` además del nombre anterior, y la prueba de conexión dice
   con claridad si el problema es de usuario, de clave o de red.
3. **El servidor del Ministerio no aguantaba la consulta completa**
   (PR #254). Cuando la consulta de todo el período se cae, el bot ya no se
   rinde: baja el informe **mes por mes** y lo une, sin registros repetidos.
4. **Dos remates** (PR #255): se recuperó un ajuste que se había perdido al
   rehacer la rama (tandas de 50 registros en vez de 200, que bajan solas si
   el servidor se queja) y se cubrió el caso real en que la consulta **no
   responde nunca** (se queda esperando) — antes ese camino terminaba sin
   informe; ahora también dispara el rescate mes por mes.

Todo probado con un servidor de prueba que imita las fallas reales.

**OJO — la segunda corrida borró el informe bueno.** Después de actualizar
la carpeta, el auditor volvió a correr el informe y el servidor del
Ministerio estaba sobrecargado: alcanzó a bajar 50 registros y se cayó. El
bot, en vez de completar el informe mes por mes, se conformó con esas 50
filas **y las guardó encima del Excel bueno de 2.597**, que se perdió. Se
corrigieron las dos cosas el mismo día:

- Si la consulta completa se corta a medias, ahora **sigue mes por mes**
  igual (antes solo lo hacía si no había bajado nada). Los repetidos se
  quitan al final por número de seguimiento.
- **Un informe incompleto ya no puede pisar a uno bueno.** Se guarda al lado
  con `_PARCIAL` en el nombre y el anterior queda intacto. Vale para las
  tres formas de quedar incompleto: cancelado con Ctrl-C, consulta cortada,
  o algún mes que no se pudo traer.
- Seis pruebas nuevas que reproducen exactamente lo que pasó (se verificó
  que fallan con el código anterior).

**Lo que salió del informe, ya cruzado con lo que el hospital respondió.**
Con el informe en la mano se armó el camino completo para cargar las
respuestas, y aparecieron tres cosas que importan más que el bot:

- **El valor de las devoluciones que muestra el informe está inflado.** La
  hoja RESUMEN dice $24.921 millones, pero SIIFA registra cada devolución
  repitiendo el valor completo de la factura: HUS475438 aparece 340 veces,
  cada una por sus $51 millones. **El valor real de las 10 facturas
  devueltas es $115.051.312.** Ese es el número que va a un informe.
- **El trabajo es mucho menor de lo que parece.** Las 2.579 líneas
  pendientes se responden con **272 textos distintos**, y son apenas 58
  facturas con glosa y 10 con devolución.
- **Casi todo está vencido:** 85 glosas con más de 90 días y 685 entre 61 y
  90, contra un plazo de ley de 15 días hábiles.

Y el hallazgo que ahorra el trabajo: **1.082 de las 2.579 líneas YA fueron
respondidas por el hospital**, con la respuesta escrita en la base de
trámites de Dinámica Gerencial, sólo que nunca se cargó al portal del
Ministerio. Se hicieron dos herramientas nuevas:
`tools/siifa_preparar_respuestas.py` (agrupa las líneas repetidas y después
reparte la respuesta a cada una) y `tools/siifa_cruzar_tramites_dgh.py`
(busca en DGH la respuesta ya dada y deja la hoja de trabajo pre-llenada,
marcando de dónde salió cada una). De las 272 respuestas, 162 salieron de
DGH y 110 hay que escribirlas.

**Y la corrida real salió bien: el Excel maestro ya está bajado.** El
informe quedó en `D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx`
con **2.597 seguimientos, 2.579 sin respuesta del HUS** — el mismo 2.579 que
se ve en la pantalla de SIIFA, así que cuadra con el portal. Duró 16 minutos.
Por meses: enero 487, febrero 559 (partido en dos quincenas porque el servidor
no aguantó el mes entero), marzo 600, abril 432, mayo 181, junio 224 (también
partido), julio 114. De 2025 no hay nada. Sin registros repetidos y sin
períodos perdidos.

---

### 04-08 (décima parte) — La causa de fondo: el vigilante entregaba claves viejas

Aquí terminó el misterio del día. La página por internet seguía diciendo
«su clave está inválida (la que usó: gsk_5CxaRq…)» a las 3 de la tarde,
con el archivo de claves correcto desde el mediodía y el otro motor
mostrando la clave nueva sin problema.

**El porqué.** `tools/servidor_motor_local.cmd` es la ventana que mantiene
vivo el servidor de la página pública: si se cae, lo vuelve a levantar a
los 5 segundos. Pero **cargaba el archivo de claves una sola vez, antes de
entrar a ese bucle**. Cada vez que revivía el servidor le entregaba el
ambiente de cuando se abrió la ventana — y las variables de ambiente le
ganan al archivo. Resultado: **ese motor se queda con las claves del día
en que se abrió la ventana, para siempre**, por más que se cambie el
archivo y por más veces que se reinicie solo.

Por eso todo lo de hoy se veía contradictorio: el motor de pruebas (8000)
mostraba la clave nueva y decía la verdad; el de la página (8080) usaba la
vieja y también decía la verdad. Cada mitad tenía razón por separado.

Lo que quedó hecho:

- **El vigilante relee el archivo de claves en cada vuelta.** Un reinicio
  ahora sí toma las claves de hoy.
- **El motor avisa cuando no está usando las claves del archivo**: la
  tarjeta «Motor» del Diagnóstico se pone en ROJO y dice, sin revelar las
  claves, *«está usando gsk_5CxaRq… pero el archivo dice gsk_vn06EE…»* y
  qué ventana hay que cerrar. Es lo que hoy no se podía ver de ninguna
  manera.
- **La tarea automática cada 5 minutos** cerraba cualquier motor de la
  aplicación: ahora solo reinicia el de producción (puerto 8080), así que
  ya no le apaga el de pruebas al auditor sin explicación.
- **El bot de reinicio** pasó a un archivo aparte (`tools/reiniciar_motor.ps1`)
  con cinco correcciones que salieron de una revisión adversarial: no cierra
  motores de otro puerto, comprueba que de verdad murieron (antes se tragaba
  el «acceso denegado» y decía «cerrado»), no mata al dueño del puerto si no
  es el motor, avisa de los programas que Windows no lo deja ver, y consulta
  el puerto sin depender del idioma —el filtro anterior buscaba «LISTENING»
  y **en un Windows en español nunca encontraba nada**, por eso decía «no
  había ningún motor encendido» cuando sí lo había—.

**Cierre del día, con la máquina de Yesid como banco de pruebas.** Cada
corrida real destapó algo más:

- El bot mostró **dos motores en el puerto 8080** y parecía haber un
  intruso. No lo había: en Windows el Python del proyecto es un lanzador
  que arranca el intérprete de verdad como **proceso hijo**, y es el hijo
  el que se queda con el puerto. Un solo motor. El bot ahora los cuenta
  como uno —pero al cerrar se lleva padre e hijo, porque matar solo al
  padre dejaría vivo justo al que tiene el puerto—.
- **La página por internet no revivía sola si había un motor de pruebas
  abierto.** El vigilante se negaba a arrancar cuando veía cualquier motor
  de la aplicación, sin mirar el puerto. Con el 8000 encendido —que es lo
  que el propio bot invita a hacer— la página pública se habría quedado
  caída en el próximo corte. Corregido: mira el puerto.
- Si algún día se arranca con la opción de recarga automática, el proceso
  que de verdad atiende **se llama distinto** y el bot no lo veía: cerraba
  al padre y dejaba al hijo con el puerto tomado. Ahora cierra el árbol
  completo.
- Y un detalle de presentación: un guion largo salía en la consola como
  `â€`. Los mensajes del bot ahora usan solo caracteres que Windows
  muestra bien, con una prueba que lo impide a futuro.

**Dos bots nuevos en el menú (`MOTOR_HUS.cmd`, opciones 16 y 17):**

- **`ESTADO_MOTOR.cmd` — «¿está bien la página?»**. Doble clic y en una
  pantalla sale todo: quién atiende la página por internet, con qué clave
  de IA, si el túnel publica, si el vigilante está encendido, si arranca
  solo al iniciar sesión, y las tareas automáticas. Al final una lista de
  avisos con qué hacer si algo falta. **Solo mira: no cierra ni arranca
  nada.** Antes eso eran cinco órdenes de PowerShell pegadas a mano y
  había que saber interpretarlas.
- **`REINICIAR_MOTOR.cmd`** — el de reiniciar el motor de pruebas, ahora
  también desde el menú.

### 04-08 (novena parte) — Quién puede tocar qué: las 51 puertas abiertas

El 28 de julio se encontraron cuatro «puertas de al lado»: rutas del
sistema por las que se podía cambiar una glosa **sin comprobar el cargo**
de quien lo pedía. Se cerraron una por una, pero quedaban **51 rutas** que
solo pedían haber entrado con usuario y contraseña, sin que nadie hubiera
decidido si eso estaba bien o era otro descuido esperando.

Quedaron todas decididas y escritas:

- **39 pasaron a exigir cargo de auditor o superior**: analizar una glosa,
  importar en masa, comentar en el expediente, validar, restaurar una
  versión del dictamen, decidir glosas ADRES, crear plantillas del equipo,
  preguntarle a la IA, generar el PDF del acta.
- **2 pasaron a coordinación**: subir el PDF de un contrato y mandar
  alertas por correo a todo el equipo.
- **12 se quedan como estaban** porque son del propio usuario: entrar y
  salir, cambiar su contraseña, su segundo factor, sus tareas, sus
  vacaciones y el buzón de sugerencias.
- **9 ya comprobaban el cargo por dentro** (las que dependen del dato:
  «esta glosa es de otro auditor»), y ahora una prueba verifica que ese
  chequeo exista de verdad.

El único que pierde algo es el perfil **VIEWER** (el que solo mira), que
es exactamente para lo que existe. El auditor no perdió nada: hay pruebas
que lo comprueban en las dos direcciones.

Lo importante para el futuro: **una ruta nueva que modifique datos y no
tenga decisión de permisos rompe las pruebas**. Ya no depende de que
alguien se acuerde de revisarlo.

### 04-08 (octava parte) — Una librería ajena tapó la carpeta de los bots

A las 18:20 (hora universal) se publicó **Mako 1.4.0**, una librería que
viene incluida con otra que usa el sistema. Esa versión salió con un error
de empaquetado: trae **una carpeta llamada `tools/` propia** que se instala
junto a las librerías y **tapa la carpeta `tools/` del proyecto** —donde
viven todos los bots—. Cuarenta y cinco minutos después, las pruebas
automáticas del repositorio empezaron a morir con «No module named
'tools._dinero'». No fue nada que hubiéramos hecho: le pasa a cualquier
proyecto que tenga su propia carpeta con ese nombre.

Lo grave es lo que habría pasado en producción: es exactamente el mismo
síntoma del incidente del 31 de julio (todas las tarjetas del Centro de
Automatización contestando «ModuleNotFoundError»). Bastaba con reinstalar
las librerías en el PC o volver a armar la imagen del servidor.

Quedó blindado por partida doble:

- La carpeta `tools/` del proyecto ahora es un **paquete de verdad**
  (`tools/__init__.py`): con eso gana siempre la del repositorio, sin
  importar qué librería se llame igual mañana. Y viaja a la imagen del
  servidor (línea nueva en `.dockerignore`).
- Se le puso **tope a esa librería** (`Mako` por debajo de 1.4) para no
  traer esa basura mientras el error siga arriba.
- Dos pruebas nuevas lo vigilan: que el paquete exista y que sea el del
  repositorio el que se carga, y que viaje en la imagen.

### 04-08 (séptima parte) — Había DOS motores prendidos al mismo tiempo

Este fue el verdadero culpable de toda la tarde. Yesid cambió la clave de
Groq, reinició y el arranque escribió **`groq=OK gsk_vn06EE…`**; pero la
pantalla de Diagnóstico —que lee exactamente el mismo dato— mostraba
**`gsk_5CxaRq…`** (la clave vieja) y el análisis seguía fallando con «clave
inválida». Dos respuestas distintas para el mismo dato solo tienen una
explicación: **no era un solo programa contestando, eran dos**.

**La explicación de verdad (y no era la primera que se pensó).** En el PC
del hospital corren **dos motores al mismo tiempo, en puertos distintos**:

- el del **puerto 8080**, que lo mantiene vivo `tools/servidor_motor_local.cmd`
  y es **el que alimenta la página por internet** (el túnel de Cloudflare);
- el del **puerto 8000**, que es el que Yesid levanta a mano para probar.

El del 8080 llevaba horas arriba, así que conservaba la clave vieja y el
programa viejo — y **el navegador estaba hablando con ese**. Por eso el
arranque del 8000 mostraba una clave y la pantalla mostraba la otra: no era
una pantalla mintiendo, eran dos sistemas distintos.

(La primera sospecha fue que los dos se peleaban el mismo puerto. Quedó
descartada en vivo: al intentar levantar un segundo motor en el 8080,
Windows respondió «solo se permite un uso de cada dirección de socket».)

**La lección, que quedó escrita en el sistema:** si se cambia el archivo de
claves, hay que **reiniciar los dos motores**. Reiniciar solo el de pruebas
no toca la página por internet.

Lo que se construyó para que no vuelva a pasar:

- **`tools/REINICIAR_MOTOR.cmd`** (doble clic): cierra los motores **de su
  propio puerto** —incluido el que quedó vivo sin estar atendiendo— y deja
  uno solo recién arrancado. De los de otro puerto **avisa y no los toca**:
  la primera versión los cerraba a todos y así se tumbó la página pública
  por error.
- **El Diagnóstico avisa primero**: la primera tarjeta del panel ahora es
  **«Motor (quién está atendiendo)»**, con el puerto de cada uno. Si dos se
  pelean el mismo puerto se pone en ROJO («cerrá el sobrante»); si están en
  puertos distintos avisa en amarillo que son **dos instalaciones separadas**
  y que hay que reiniciar las dos — sin mandar a cerrar ninguna.
- **El arranque también lo dice**: junto a `[IA-PROVIDERS]` aparece
  `[MOTOR] Un solo motor atendiendo…` o `[MOTOR-DUPLICADO] …`.
- **El aviso de error dice CUÁL clave usó**: «GROQ: su clave está inválida o
  vencida (la que usó: gsk_5CxaRq…)». Con eso se compara de un vistazo
  contra la del arranque y se sabe si contestó el motor viejo.
- **El botón «Probar proveedores de IA»** muestra la clave que probó y
  advierte si hay más de un motor encendido (si no, uno ve verde y el
  análisis igual falla).

De paso apareció otro defecto real: cuando la clave estaba vencida, el motor
**apagaba el «razonador» de uno de los modelos de Groq para el resto del
día** (confundía el error de clave con un rechazo de ese ajuste). Los
dictámenes salían más pobres y nada lo decía. Corregido: solo se apaga si el
error nombra de verdad a ese ajuste.

### 04-08 (sexta parte) — Botón para probar la clave de IA

- En **Gobierno IA** hay un botón **«Probar proveedores de IA»**: hace una
  llamada mínima a cada proveedor y dice en un renglón si la clave sirve
  («✓ GROQ (principal) — respondió con llama-3.3-70b») o por qué no. Nació
  del día de hoy: la única forma de saber si una clave nueva funcionaba
  era analizar una glosa de verdad y ver si fallaba.
- Y el aviso ya no deja causas en blanco: si un proveedor falla sin
  explicar, dice «no respondió» en vez de dejar el renglón vacío.

### 04-08 (quinta parte) — El .env correcto que el sistema no veía

- Yesid montó el sistema en su equipo (ya no en el servidor de Google) y
  el arranque decía **«groq=AUSENTE»** aunque el archivo de claves
  estuviera bien puesto. No era su configuración: **el sistema leía las
  claves en dos sitios distintos**. El motor de dictámenes las recibía
  bien, pero el asistente, el auditor forense, el lector de cláusulas y
  el propio mensaje de arranque las buscaban en otro lado y no las
  encontraban nunca.
- Quedó el puente: lo que está en el archivo de claves ahora también
  queda disponible para todo el sistema. Si el arranque dice AUSENTE, de
  verdad falta la clave — ya no es una falsa alarma. Lo que venga por
  Docker o el servicio de Windows sigue mandando sobre el archivo.

### 04-08 (cuarta parte) — El mensaje dice QUÉ proveedor falló y por qué

- Con Groq como IA principal y Anthropic de respaldo, cuando fallaban
  los dos el aviso solo nombraba al último: el auditor veía «clave
  inválida» de Anthropic —que ni siquiera es su proveedor principal— y
  no sabía qué había pasado con Groq.
- Ahora el mensaje los nombra a todos con su causa en cristiano:
  «GROQ: está en límite de uso · ANTHROPIC: su clave está inválida o
  vencida». Las causas se traducen solas (sin saldo, saturado, no
  respondió a tiempo, no se pudo conectar…).

### 04-08 (tercera parte) — Una carátula vacía tampoco es un dictamen

- Segundo hallazgo del mismo día: ya no salía el error de la IA en el
  cuerpo, pero el dictamen salía **con la argumentación jurídica VACÍA**
  y aun así con el sello «validado». Eso es peor que el error visible,
  porque parece bueno.
- Ahora el motor **se niega a armar la carátula** si la IA no devolvió
  argumentación (tabla, sello y cierre no se generan), y el guardado la
  rechaza también aunque llegara armada por otro camino. En pantalla:
  mensaje claro de que no se guardó y que hay que reintentar.
- Recordatorio: la causa de fondo sigue siendo la **clave de IA
  inválida** en el servidor. Mientras no se renueve, el sistema no va a
  inventar dictámenes — va a decir que no puede.

### 04-08 (segunda parte) — Panel operacional y arreglo del CI

- **El Mando ejecutivo ya muestra dónde se atasca el trabajo**: las
  glosas abiertas agrupadas por estado, con cuánta plata hay parada en
  cada uno y hace cuántos días no se mueve la más vieja (en rojo si pasa
  de 30). Y al lado, **la carga real de cada auditor**: cuántas lleva
  abiertas, cuántas ya vencidas y por qué valor — quien tiene vencidas
  aparece de primero. Se decidió ampliar el Mando en vez de crear otra
  pantalla, para no tener dos tableros que digan cosas parecidas.
- **Arreglo del CI**: el cambio del incidente dejó tres pruebas viejas en
  rojo porque validaban justamente el texto de error como si fuera
  dictamen. Se corrigieron para probar lo que siempre quisieron probar,
  con un dictamen de verdad.

### 04-08 — Incidente: un error de la IA quedó guardado como dictamen

- Iván analizó una glosa de PPL y el «dictamen» salió con el error crudo
  del proveedor («Invalid API Key») como argumentación jurídica, con
  sello de calidad y todo. Dos causas, dos arreglos:
  1. **La clave de Anthropic del servidor está inválida** — hay que
     renovarla (instrucción abajo en el chat). Eso es configuración, no
     código.
  2. **El motor jamás debió guardar eso.** Ahora, si la IA se cae, el
     análisis falla LIMPIO: mensaje claro de qué pasó y qué hacer («la
     clave está vencida, avisá a administración» / «saturada, reintentá
     en 2-3 minutos») y NO se guarda nada. Y aunque un texto con firma
     de error llegara por cualquier otro camino, la persistencia lo
     rechaza: no puede volver a existir un dictamen que diga «Invalid
     API Key».

### 03-08 (cuarta parte) — Gobierno de IA: el gasto se ve

- Pantalla nueva **Gobierno IA** (Reportes, solo coordinación y
  administración): cuánto va gastado en IA hoy, en la semana y en el mes;
  qué modelos consumen y con qué demora; qué usuarios la usan; **cuánto
  ahorra el caché** de instrucciones; y las **glosas más caras de
  defender**, con enlace directo a su expediente.
- El chat también lo responde («¿cuánto hemos gastado en IA este mes?»).
  Los datos existían llamada por llamada desde hace meses — faltaba la
  vista que los cuenta.

### 03-08 (tercera parte) — Google apagó el servidor: mudanza al PC del hospital

**Qué pasó.** La página <https://iaglosassinac.help> dejó de cargar (error
1033). La causa no fue el sistema: la **cuenta de facturación de Google Cloud
quedó cerrada** (saldo pendiente ~$11.278 COP) y Google apaga la máquina
virtual cuando eso pasa. **Los datos NO se perdieron**: siguen en el disco de
la máquina apagada, junto con las copias diarias de las 3 a. m.

**Decisión (Yesid):** en vez de seguir pagando servidor, el sistema se muda al
**PC de cartera del hospital**, que permanece siempre encendido. Misma página,
mismos usuarios, mismos datos, y los cambios de código se siguen aplicando
solos cada 5 minutos, igual que en la VM.

**Lo que quedó construido hoy (el paquete de mudanza):**

1. `docs/MIGRACION_PC_HOSPITAL.md` — la guía completa en 4 fases: (0) reabrir
   la cuenta de facturación, (1) rescatar de la VM la base de datos, las
   llaves y la llave del túnel con comandos listos para pegar en Cloud Shell,
   (2) preparar el PC (Docker Desktop + Git), (3) instalar con doble clic,
   (4) apagar la VM cuando todo funcione.
2. `tools/MONTAR_SERVIDOR_MOTOR_GLOSAS.cmd` — el instalador de doble clic:
   verifica requisitos, trae el código, restaura el rescate, levanta el
   sistema y deja programadas las dos tareas de Windows. Se puede correr las
   veces que sea sin dañar nada.
3. `tools/autodeploy_motor_glosas.cmd` — el deploy automático cada 5 minutos
   (igual al de la VM), con su registro en `data\autodeploy.log`.
4. `tools/copiar_backup_motor_glosas.cmd` — la copia de seguridad diaria
   (9:00 a. m.) hacia el share del hospital o una carpeta de Drive/OneDrive,
   para que la base y su copia no vivan en el mismo disco.

**El paso que sigue depende de Yesid (fase 0 y 1):** reabrir "Mi cuenta de
facturación 2" pagando el saldo (~$11 mil pesos, una sola vez) y correr los
comandos de rescate de la guía. Sin ese rescate el PC arrancaría vacío.

### 03-08 (quinta parte) — SIIFA: el motor redactó las respuestas que faltaban

- Se construyó `tools/siifa_redactar_respuestas.py`: para los seguimientos de
  SIIFA que **no tenían respuesta escrita en DGH**, el motor la redacta solo,
  y separa el trabajo en dos archivos, **glosas** y **devoluciones**, porque
  no se contestan igual. Quedaron `respuestas_GLOSAS.xlsx` (1.238 filas) y
  `respuestas_DEVOLUCIONES.xlsx` (1.341), todas con texto y con una columna
  REVISAR que dice qué verificar antes de subirla (PR #268).
- **Corrección del mismo día (PR #269):** el redactor traía su propia forma de
  leer los pesos, y esa es la copia número once de algo que ya existe una sola
  vez en el repositorio. Se le puso el lector único (`tools/_dinero.py`). Antes,
  un valor que viniera del Excel con puntos de miles o con `$` (por ejemplo
  `$ 1.479.360`) hacía que la respuesta dijera "SIN VALOR REGISTRADO" en una
  glosa que sí tiene valor; ahora se lee bien. Con esto vuelve a quedar en
  verde la prueba que vigila que haya **un solo lector de pesos** en todo el
  repositorio (esa prueba existe porque llegaron a convivir diez copias y
  cuatro estaban malas: una multiplicaba por cien y tres dividían por mil).

### 03-08 (sexta parte) — SIIFA: cargar primero solo lo que el hospital ya respondió

- **La duda de Yesid:** la factura HUS532384 no aparece en el Excel de lotes
  de DGH, ¿de dónde salió entonces su respuesta? De la base de SIIFA, no de
  la de DGH. El informe de seguimientos de SIIFA es la lista de trabajo (trae
  factura, código, causal, valor y lo que escribió la EPS); el Excel de DGH es
  solo un atajo para no volver a escribir lo que el hospital ya contestó. Si
  la factura no está en DGH, la respuesta la redactó el motor y la fila queda
  marcada **REDACTADA** (amarilla); las que sí estaban salen **EXACTO** o
  **POR_CODIGO** (verdes).
- **Decisión:** cargar primero solo las verdes. El redactor tiene ahora la
  opción `--solo-lo-ya-respondido`: los dos archivos de cargue quedan
  únicamente con las respuestas reales del hospital, y las redactadas **no se
  botan** — salen en archivos aparte terminados en `_REDACTADAS`, para
  revisarlas y subirlas después.
- **Advertencia que quedó anotada:** la glosa que no se contesta dentro del
  término se entiende ACEPTADA (art. 57 Ley 1438/2011). Las redactadas no
  pueden quedarse guardadas indefinidamente: hay que revisarlas por tandas
  (empezando por las de mayor valor) y subirlas.

### 03-08 (séptima parte) — La fecha de la respuesta: el detalle que salvaba o hundía el cargue

- Yesid pasó la **guía de cargue manual de SIIFA** (con pantallazos del piloto
  de la factura HUS497119). Ahí quedó claro que el portal pide **tres** datos
  para responder: código, observación y **fecha de respuesta** — y que la
  fecha que se digita es **la del día en que el hospital respondió de verdad**
  (la de DGH: 11/05/2026), no la de hoy.
- **El problema que eso destapó:** los archivos de cargue no llevaban esa
  fecha. El bot, sin fecha, pone la de hoy. Es decir: las 1.082 respuestas que
  el hospital dio en su momento se habrían subido fechadas hoy, y en el
  histórico de SIIFA aparecerían contestadas **meses después de la glosa, o
  sea fuera del término** (art. 57 Ley 1438/2011). Es lo primero que mira la
  EPS en una conciliación: habría sido regalarle el argumento.
- **Corregido:** la fecha de DGH ahora viaja desde el cruce hasta el archivo
  que lee el bot, en la columna `FECHA_RESPUESTA` (normalizada a AAAA-MM-DD
  venga como venga del export). Las redactadas van sin fecha —se están
  respondiendo hoy, y hoy es la fecha correcta para ellas—. Si DGH no trae la
  fecha, la fila queda marcada en REVISAR.
- El paso a paso manual del portal quedó escrito en `docs/CONTEXTO_SIIFA.md`
  (sección 5.ter), incluido el pantallazo de **Ver Histórico** como evidencia
  para el PDF de soportes.

### 03-08 (CUV) — Cuentas médicas: el CUV que no salía

- Cuentas médicas reportó que el validador del Ministerio no le generaba el
  **CUV** de la factura **MED737** (Medical Center Especialistas, NIT
  900299334). El validador mostraba un solo rechazo: `RVG01 | Dato requerido`
  en `usuarios[0].servicios.consultas[0].modalidadGrupoServicioTecSal`.
- **Al revisar el paquete completo (XML + JSON) aparecieron cuatro problemas,
  no uno.** Los otros tres no los ve la pre-validación de escritorio: se
  descubren cuando el paquete ya se envió y el CUV no llega.
  1. `modalidadGrupoServicioTecSal` en `null` → va `01` (Intramural), porque
     fue consulta presencial en la sede.
  2. `numFactura` sin el prefijo: decía `737` y en la DIAN esa factura quedó
     radicada como **`MED737`**. Si no coincide, el Ministerio no la encuentra.
  3. `numNota: "2"` con `tipoNota: null` → en una factura de venta los dos
     campos van en `null`. Lo está exportando mal el software de facturación.
  4. **La atención quedó fechada el 27-07 y la factura cubre el período del
     31-07.** Esa la decide facturación: o la fecha del servicio está mal, o
     hay que reexpedir la factura. No se cambia una fecha clínica para que el
     validador pase.
- **Se creó `tools/validar_json_rips.py`** para no repetir el ida y vuelta
  factura por factura. Revisa las dos cosas antes de subir nada: la estructura
  del JSON (campos obligatorios en `null` por tipo de servicio, formato de
  fechas, tablas de referencia de la Res. 2275/2023, coherencia
  `tipoNota`/`numNota`) **y el cruce contra el XML** (número con prefijo, NIT,
  fecha de atención dentro del período de facturación, suma de valores).
  Desempaqueta la factura tanto si el XML es un `Invoice` suelto como si es el
  `AttachedDocument` que la trae en CDATA, que es como la entrega el
  facturador. Corre sobre una carpeta o sobre un mes con `--recursivo`, deja
  reporte CSV y separa ERROR (bloquea el CUV) de AVISO (no bloquea, pero suele
  terminar en glosa). 29 pruebas automáticas.
- Guía para el auditor en `docs/CONTEXTO_FEV_RIPS_CUV.md`: qué revisa cada
  pasada del validador, la tabla de modalidades, los errores más frecuentes y
  la plantilla de PowerShell para corregir el JSON sin dañarlo.

### 03-08 (CUV, parte 2) — El enredo del código de prestador

Con las cuatro correcciones puestas, el Ministerio dejó de reclamar y salió un
rechazo nuevo, **RVC011**, que costó tres intentos entender. Vale la pena
dejarlo escrito porque le va a pasar a más facturas:

- El mensaje dice que el código informado (`680010393301`) "no coincide con los
  datos de autenticación" y muestra como habilitado `6800103933`. Parece que
  sobraran dos dígitos en el RIPS. **No es así.**
- **El mismo prestador se escribe con dos largos distintos según el archivo:**
  en el **XML** de la factura va a **10 dígitos** (código del prestador) y en el
  **JSON** de RIPS va a **12** (código de habilitación de la sede). Está en los
  Documentos Técnicos 1 y 2 del Ministerio.
- Se probó bajar el JSON a 10 y el validador contestó de una: *"El campo de
  codPrestador debe tener 12 caracteres"*. Confirmado por descarte.
- Se consultó el REPS (datos abiertos, dataset `c36g-9fc2`) con el NIT
  900299334: prestador **6800103933**, sede **680010393301**. O sea que **el
  JSON siempre estuvo bien** y la sede 01 es la correcta.
- **Lo que está mal es el XML**, que lleva los 12 donde van 10. Y el XML está
  firmado: no se toca. Le toca a **facturación reexpedir** la factura, y al
  proveedor del software separar los dos parámetros — si usa uno solo para los
  dos archivos, el error se repite en todas.
- Las 3 notificaciones amarillas (RVC017/019/059) **no bloquean el CUV**: la
  norma dice que son transitorias. Pero son cruces de CUPS contra diagnóstico,
  cobertura y finalidad, o sea materia prima de glosa. Ojo con una: la factura
  describe "CONSULTA ESPECIALIZADA POR PRIMERA VEZ" pero el RIPS reporta el
  CUPS **890201**, que es consulta de primera vez **por medicina general**. Hay
  que confirmar quién atendió antes de aprovechar la reexpedición.
- **Cambio de norma importante:** la Resolución 2275 de 2023 fue **derogada por
  la Resolución 948 de 2026**. Los anexos ya no van dentro de la resolución:
  ahora son "Documento Técnico 1 y 2" y el Ministerio los actualiza en el
  micrositio de SISPRO **sin expedir norma nueva**. Hay que mirarlos antes de
  cada cargue grande.
- `tools/validar_json_rips.py` ahora detecta este caso solo: lee el
  `CODIGO_PRESTADOR` del bloque de interoperabilidad del XML, compara los largos
  y dice cuál de los dos archivos tiene el error y quién lo corrige. 35 pruebas.
### 03-08 (octava parte) — Todo listo para empezar a subir a SIIFA

- **`tools\CARGAR_SIIFA.cmd`** — bot de doble clic con menú, para no escribir
  comandos: [1] baja el informe de SIIFA, [2] arma los archivos de respuestas
  (solo lo que el hospital ya había respondido), [3] piloto de UNA glosa,
  [4] y [5] cargue de glosas y de devoluciones, [6] reintento de lo que falló,
  [7] catálogo de códigos. Instala solo lo que falte y guarda el usuario y la
  clave del portal la primera vez (nunca quedan escritos en un archivo). El
  menú **no deja hacer el cargue masivo sin haber corrido el piloto**.
- **`docs/CARGUE_SIIFA_PASO_A_PASO.md`** — la misma secuencia escrita, con los
  comandos sueltos por si hay que correr uno aparte, qué verificar en el
  portal después del piloto (Ver Histórico + pantallazo) y el orden sugerido
  para revisar después las redactadas: primero las de mayor valor, luego
  tarifas/facturación/pertinencia (se sostienen con el contrato), y de últimas
  soportes y DE5601 (esas exigen el papel y el acuse).

### 03-08 (novena parte) — Primera corrida real del bot de SIIFA: dos correcciones

- Yesid corrió `CARGAR_SIIFA.cmd` por primera vez. En la pregunta de la
  carpeta de trabajo quedó pegado un comando en vez de una ruta; el bot lo
  aceptó, bajó los **2.598 seguimientos** (7 minutos, con el servidor del
  Ministerio en mal día) y **todo se perdió al momento de guardar**.
- **Corregido en dos partes**, para que no vuelva a pasar por ningún camino:
  1. El bot valida la carpeta ANTES de empezar: si la ruta no sirve o no deja
     guardar (unidad de red desconectada, por ejemplo), lo dice de una y
     vuelve a preguntar. Se agregó la opción **[8] Cambiar la carpeta**.
  2. El propio informe (`siifa_reporte_seguimientos.py`) revisa que va a
     poder guardar antes de bajar nada — así también queda protegido quien
     corra el comando a mano.
- De la misma corrida quedó confirmado que el modo **mes por mes** funciona:
  la consulta completa se cayó (el servidor respondió 500 y hubo que bajar de
  50 a 10 registros por tanda), el bot cambió solo de estrategia y completó
  el informe.

### 03-08 (décima parte) — El Enter que dejaba el bot inservible

- Segunda corrida del bot de SIIFA: al dar **Enter** para aceptar la carpeta
  por defecto, el menú quedó mostrando `Carpeta: "=` y ninguna opción sirvió.
- **La causa:** el bot le quitaba las comillas a lo escrito ANTES de aplicar
  la carpeta por defecto. Con Enter no se escribe nada, y quitarle las
  comillas a algo vacío dejaba de carpeta la basura `"=`. Corregido el orden
  (primero la de por defecto, después limpiar), y lo mismo en la ruta del
  export de DGH. Queda una prueba que vigila ese orden.
- De paso, el menú ahora **muestra por dónde va el trabajo**: al lado de cada
  opción dice si el informe ya está bajado, si los archivos de respuestas ya
  están armados y si el piloto ya se hizo.
- **Pendiente relacionado:** otros bots de doble clic (`CRUZAR_GLOSAS`,
  `SEMAFORO_GLOSAS`, `AUDITAR_DEV_EPS`, `BUSCAR_FACTURA`, `EXCEL_A_CSV`,
  `TXT_A_EXCEL`, `VERIFICAR_RADICACION`, `VIGILANTE_NOCTURNO`) tienen el
  mismo patrón. Ahí sólo falla cuando la ruta queda vacía, pero conviene
  corregirlo antes de que le pase a alguien en mitad de un trabajo.

### 03-08 (undécima parte) — La prueba de que sí quedó subido

- **Piloto de SIIFA hecho y bueno:** la glosa 15110544 de la factura
  HUS454747 se subió por el bot, con OK, y el reporte quedó en
  `piloto_siifa.csv`.
- La pregunta de Yesid fue la correcta: *«¿y cómo sé que efectivamente se
  subió, si necesito un pantallazo?»*. Con 1.082 respuestas, tomar 1.082
  pantallazos no es viable.
- **`tools/siifa_verificar_cargue.py`** (opción **[9]** del bot): le pregunta
  a SIIFA, factura por factura, qué quedó registrado de verdad y lo compara
  con lo que se mandó. Saca dos cosas:
  1. La **hoja de verificación**: verde lo que quedó igual; amarillo lo que
     quedó con el código o **la fecha** distintos; rojo lo que sigue sin
     respuesta y hay que volver a subir.
  2. Una **constancia en PDF por factura** (carpeta `EVIDENCIAS`), con
     membrete del hospital, fecha y hora de la consulta, y por cada glosa su
     código, valor, respuesta registrada y fecha. Eso es lo que se anexa a
     soportes: reemplaza al pantallazo y sale de la API oficial del
     Ministerio.
- Se consulta **por factura y no por glosa**: 17 consultas en vez de 1.082.

### 04-08 — La deuda quedó paga, Google se demora, y nace el arranque exprés

**El pago.** Se descubrió que la deuda era en **pesos** (once mil, no once
mil dólares). Google no dejó pagar menos de $30.000: se pagaron con la
Visa nueva y el perfil quedó **sin saldo pendiente** y con $18.080 a favor.
La Mastercard vieja (la que rebotó y causó todo) debe dejar de ser la
principal.

**El nuevo tranque.** Aun con la deuda paga, el botón "Reabrir cuenta de
facturación" quedó bloqueado: Google exige que lo haga su equipo de
soporte. Se abrió el **caso #74044918** (chat con soporte, escalado al
equipo especializado) y prometieron respuesta **en 24-48 horas por correo**.
Crear cuentas nuevas no sirve: mientras el perfil estuvo en deuda, Google
las cerraba al nacer (pasó con la cuenta 3).

**La decisión para no parar al equipo:** revivir la página YA desde el PC
de cartera con una **base nueva provisional**, sin esperar el rescate:

1. `tools/REVIVIR_EXPRESS_SIN_RESCATE.cmd` — instalador de doble clic:
   crea las llaves nuevas del sistema, configura el túnel de Cloudflare
   por **token** (sin necesitar la llave vieja encerrada en la VM),
   levanta todo y deja las mismas dos tareas programadas.
2. La guía `docs/MIGRACION_PC_HOSPITAL.md` ganó la sección **"Arranque
   exprés SIN rescate"**: cómo sacar el token del túnel en Cloudflare
   (5 minutos), cómo entra el equipo (los 25 usuarios se siembran solos;
   contraseña inicial = la parte del correo antes del arroba, y el
   sistema obliga a cambiarla), y qué hacer cuando Google reabra.
3. **ELIAS CARVAJAL quedó en el sembrado como administrador** (antes solo
   existía en la base de la VM; en una base nueva no aparecía).

**OJO — cuando Google reabra la cuenta:** hacer el rescate de la fase 1 y
**avisar al chat ANTES de restaurar la base vieja**, para sacar copia de la
provisional y fusionar lo trabajado en estos días.

**Segunda parte del mismo día — modo SIN Docker.** Yesid preguntó si se
podía sin Docker Desktop (los PC del hospital no siempre lo permiten). Se
construyó el camino alterno: `tools/REVIVIR_EXPRESS_SIN_DOCKER.cmd` corre
el sistema directo con Python (el mismo de los otros bots) y publica la
página con el programa oficial de Cloudflare descargado solo. Deja
vigilantes que reviven el servidor y el túnel si se caen, arranque
automático al iniciar sesión, el mismo autodeploy cada 5 minutos y la
misma copia diaria. Ojo al único detalle distinto: en Cloudflare la URL
del Public hostname es `localhost:8080` en este modo (con Docker es
`motor:8080`). Guía: sección "B-bis" de `docs/MIGRACION_PC_HOSPITAL.md`.

**Tercera parte — ¡LA PÁGINA REVIVIÓ desde el PC de cartera!** La
instalación real dejó tres tropiezos, corregidos el mismo día:

1. El PC tenía Python 3.14 (demasiado nuevo) → el instalador ahora exige
   3.11-3.13 y guía a instalar el 3.13 con `winget` (PR #279).
2. `psycopg2` (conector de PostgreSQL, innecesario con SQLite) intentaba
   compilarse y tumbaba la instalación → se salta en este modo (PR #279).
3. Windows no trae la base de zonas horarias y `America/Bogota` reventaba
   el arranque → paquete `tzdata` fijado en requirements (PR #280) — y el
   **autodeploy de 5 minutos lo aplicó solo**, señal de que la maquinaria
   automática quedó viva igual que en la VM.

Con eso el sistema quedó arriba en el PC: túnel nuevo de Cloudflare por
token (`motorglosas`), usuarios sembrados (27), 13 contratos, y las tres
llaves de IA repuestas (Groq nueva, Gemini recuperada de AI Studio,
Anthropic creada de nuevo — las viejas siguen en el `.env` de la VM).
Último ajuste del día: en Docker las llaves llegaban como variables de
entorno y varias partes del código las leen así (`os.getenv`); el
vigilante del servidor ahora carga TODO el `.env` como variables de
verdad antes de arrancar, para que el modo sin Docker sea idéntico al
de Docker.
- **04-08 (tarde):** se cerraron los tres pendientes que había dejado abiertos
  el módulo web, con lo que explicó el auditor:
  - **La causal 4506 no estaba mal clasificada.** La trabajan **dos áreas**:
    los gestores por FACTURACION y las médicas por PERTINENCIA, y esta última
    cuando lo glosado es material de osteosíntesis o insumos de alto costo.
    Ahora el sistema **no la clasifica solo**: la marca `POR ASIGNAR` y **solo
    un SUPER ADMIN** la reparte desde la pantalla. El bot propone el área con
    su motivo escrito; se midió contra las 255 filas de 4506 que el equipo
    clasificó a mano y **coincide en 249 (97,6 %)**. Al asignar el área se
    recalcula la sugerencia: si queda en PERTINENCIA, el bot se calla.
  - **Los centros de costos ya no se adivinan.** La macro tenía el catálogo
    oficial en una **hoja oculta** (el botón que usa el equipo): **45 centros
    con su código** (`733001-QUIROFANOS`, `510406-DIREC SUBGCIA DE ALTO
    COSTO`, …). Se metió al bot y a la pantalla como **desplegable**, para que
    no queden variantes escritas a mano. Los 4.248 propuestos ahora salen en
    la forma oficial `código-NOMBRE`. Si el hospital cambia el plan de
    cuentas, manda el catálogo de la macro que se cargue.
  - **Las 4 facturas sin detallado** (311371, 367368, 380246, 394817): se
    revisaron **los siete lotes archivo por archivo** y no están en ninguno —
    el detallado nunca se exportó, no es un fallo del bot. La pantalla ahora
    **avisa por qué** y **trae igual todo lo del reporte del ADRES** (150, 1,
    2 y 12 glosas respectivamente, $43.518.600 en total). Si aparece el
    detallado, basta recargar la bitácora.
  200 tests pasando.
- **04-08 (noche):** el auditor mandó la guía de cargue y un PDF de ejemplo
  (`RTA_ADRES_HUS311371.pdf`), y con eso la pantalla quedó como él la quiere:
  - **Las glosas totales ya no se muestran.** En el reporte del ADRES hay
    filas con la columna «Descripción Glosa» **vacía**: son el desglose de una
    reclamación glosada entera por el FURIPS y **no se responden una por una**.
    Son **1.630 de 4.619 ($236.217.091)**. Ocultarlas resolvió de paso lo de
    «no sale la descripción de la glosa»: era eso, esas filas venían en blanco.
    La factura 311371 pasa de 150 renglones a **21 que sí hay que trabajar**.
    No desaparecen en silencio: sale un aviso con cuántas son y cuánto valen,
    y un enlace para verlas.
  - **La descripción de la glosa es ahora una columna propia** en la tabla,
    completa (antes iba cortada debajo del código de la causal).
  - **Al cargar el archivo salen de una vez las facturas a auditar**, con el
    avance de cada una y filtros por Pendientes / En proceso / Cerradas. Se
    hace **clic en una** y se despliega por qué y qué le glosan.
  - **Se guarda solo** mientras el gestor escribe la observación, y también
    con un botón **Guardar**. Al terminar, **Terminar factura**; si hay que
    corregir, **Reabrir factura**, y queda registrado quién la reabrió. Una
    factura cerrada **no se reabre sola** al editar una glosa.
  - **Botón de PDF de evidencia por factura**, con el mismo formato del
    ejemplo: encabezado con factura, radicación y documento del paciente, y la
    tabla de seis columnas (incluida RTA GLOSA COMPLETA con la fórmula de la
    macro). Los renglones de glosa total no van en la tabla pero sí se dicen
    al pie, junto con las glosas que quedaron sin decidir.
  Tabla nueva `facturas_adres` para el estado. 50 tests del módulo web.
  **Nota sobre Cobranza Live:** otra sesión, al fusionar, había vuelto a
  dejarla en el menú por prudencia ("quitarle una pantalla al equipo no es
  decisión de una fusión"). El auditor lo pidió de nuevo de forma explícita,
  así que **se retiró del menú**. Se quitó solo el botón, el panel, la pestaña
  y el alias: `loadDashCobranza()` y el endpoint
  `/glosas/stats/dashboard-cobranza` **siguen vivos**, de modo que devolver la
  pantalla es volver a poner el botón (un minuto de trabajo). Si el equipo la
  estaba usando de verdad, se avisa y se devuelve.
- **04-08 (cierre del día):** el módulo **quedó andando en el servidor del
  hospital**. Costó tres pasos que vale la pena dejar escritos:
  - El PR #209 se había fusionado con la **primera versión** del módulo, así
    que el servidor mostraba la pantalla vieja. Se abrió el PR #295 con lo que
    faltaba.
  - Al preparar el despliegue se descubrió que **eso solo habría roto la
    pantalla**: las tablas `glosas_adres` y `paquetes_adres` ya existían con el
    paquete cargado, y el sistema crea tablas nuevas pero **no agrega columnas
    a las que ya están**. Además `facturas_adres` nacía vacía, así que la lista
    habría salido en blanco otra vez. Se agregó la migración al arranque
    (PR #298) y en el servidor corrió limpia: **1.630 glosas totales marcadas
    y 324 facturas creadas para la lista**, sin borrar nada.
  - Probando, el auditor encontró que al marcar **SE ACEPTA** el valor quedaba
    en **$0**: la tabla no tenía dónde escribir cuánto se acepta. Se agregó la
    columna **Aceptado** (valor y cantidad). Al escoger SE ACEPTA se propone
    **todo lo glosado**, que es el caso normal, y el gestor lo baja si fue
    parcial; si cambia de decisión, vuelve a cero para no reconocer plata por
    descuido. Es lo que alimenta el «CANTIDAD ACEPTADA n . POR VALOR $x» de la
    respuesta al ADRES y del PDF de evidencia.

  **Para desplegar de aquí en adelante:** el autodeploy baja de `motor-glosas`
  cada 5 minutos. Para forzarlo: `schtasks /Run /TN "MotorGlosas_Autodeploy"`,
  y se verifica en `data\autodeploy.log` y `data\servidor.log`.

### 05-08 — Dispensario: se ubicó cada evidencia y quedó listo el cargue de las 23 que faltan

- **¿Dónde y cuándo quedó lo subido? (base de 124 facturas).** Con un comando
  de búsqueda en el PC se encontró que **116 de las 124 se subieron el jueves
  23 de julio** (piloto 3:04 p. m., corrida completa 3:53–5:05 p. m., dos
  sueltas 5:11 y 5:22 p. m.) y sus pantallazos quedaron en
  `C:\temp-notas\evidencias_glosa` (esa corrida no indicó carpeta de
  evidencias, así que el robot usó la suya por defecto). Se entregó el comando
  del paquete **GI-33-5285-2026**: carpeta con las 116 evidencias + inventario
  + PDF unificado.
- **El pantallazo de "pendientes por cargar" del portal aclaró el resto:** en
  SIMED solo quedan **23 facturas pendientes** (glosas fechadas entre enero y
  agosto, **$21.083.565**). Eso confirma que los lotes del 14, 17, 28 y 31 de
  julio **ya están subidos**, aunque a cada uno se le escaparon casos: la
  522160 (17-jul), la 530112 (28-jul) y la 534953 (31-jul) figuran pendientes
  y entran ahora. Las 3 de junio ya no aparecen en pendientes (verificar cómo
  quedaron radicadas).
- **Excel de cargue de las 23**
  (`respuestas_glosa_DISPENSARIO_PENDIENTES_05AGO.xlsx`): usa el texto de
  TARIFAS que definió el auditor (contrato 440-DIGSA/DMBUG-2025) con dos
  ajustes: la cita de la **Resolución 3047 de 2008 (derogada)** se reemplazó
  por la **Resolución 2284 de 2023**, y se agregó el cierre de conciliación
  con los correos de cartera. Como no se conoce cuántas líneas tiene cada
  glosa en el portal, el Excel trae filas de sobra por factura —el robot salta
  sin problema los números que no existen y omite lo ya contestado—: 298 filas
  en total. Antes de entregar se corrió verificación adversarial en 3 frentes
  (jurídico, operativo del robot y técnico del script de paquete).
- **Consecutivos confirmados por el auditor:** los lotes 17-jul, 28-jul y
  31-jul (más esta corrida de pendientes) van juntos en el paquete
  **GI-33-5251-2026**; el cargue del 23 de julio va aparte como
  **GI-33-5285-2026**. Los comandos de carpeta + PDF de ambos quedaron
  entregados en el chat.
- **Verificación adversarial del texto (3 frentes: jurídico, operativo,
  técnico) — correcciones aplicadas antes de entregar el Excel:** se quitó la
  frase "vigente ... con plazo hasta 30/07/2026" (contradictoria al radicar en
  agosto; ahora dice "vigente a la fecha de prestación de los servicios"); el
  artículo de conciliación del cierre quedó bien citado (art. 23 del Decreto
  4747, no el 20); se citaron las Resoluciones HUS 054 y 124 de 2026 como
  respaldo de los servicios por fuera del Anexo No. 1; y la frase del
  presupuesto (art. 71 del Decreto 111/1996) se redactó de forma que no se
  pueda voltear en contra del hospital.
- **Robot SIMED mejorado (mismo día):** (1) si el Excel trae más filas que
  objeciones tiene la grilla, el robot corta en la primera que no exista (ya
  no escanea página por página cada fila sobrante); (2) lee siempre la hoja
  "Respuestas Glosa" aunque el archivo se haya guardado con otra pestaña
  activa; (3) el cierre estándar del motor de glosas ahora cita el art. 23
  del Decreto 4747 (antes decía art. 20, que no es el de conciliación).
- **OJO jurídico para el auditor:** confirmar si existe **prórroga 2026 del
  contrato 440**; con ella se refuerzan los próximos textos (el de hoy ya
  quedó blindado sin necesitarla).
- **Las 8 "sin evidencia" quedaron identificadas** con la tabla de
  vencimientos que mandó el auditor: 6 están pendientes en SIMED y entran en
  el cargue de hoy (519423 vencida el 23-07, 522160 vencida el 29-07, 533934
  y 534507 vencen el 06-08, 524188 el 10-08 y 530112 el 13-08); las otras 2
  (527406, vencía 03-08, y 525763, vence 10-08) NO figuran pendientes en el
  portal: verificar que estén contestadas buscándolas una a una en SIMED.

### 05-08 — Por qué SIIFA rechazó 1.422 respuestas (y cómo se arregló)

- **Lo que se subió el 4 y 5 de agosto:** de 2.579 respuestas quedaron
  **1.157 registradas** (985 glosas por $227.803.973 y 172 líneas de
  devolución) y **1.422 rechazadas**. Informe completo por factura en el
  Excel que se le entregó a Yesid.
- **Causa 1 — el texto pasaba de 1.500 caracteres (927 casos).** SIIFA no lo
  dice: contesta «HTTP 500: error saving the entity changes», que parece una
  falla del servidor. Los números no dejaron duda: entraron TODAS las de
  hasta 1.499 caracteres y ninguna de 1.501 en adelante. El redactor estaba
  recortando a 1.900, que era el límite equivocado. Corregido a **1.500**
  (`LIMITE_OBSERVACION`).
- **Causa 2 — el código RE9701 (495 casos).** Se usa en DGH pero SIIFA no lo
  acepta: «el código no existe, no está activo o no pertenece al grupo
  RESPUESTA». Son las devoluciones que el hospital ACEPTÓ con nota crédito.
- **`tools/siifa_corregir_rechazadas.py`** (nuevo): lee el archivo que se
  cargó y el reporte del cargue, se queda solo con lo que quedó en ERROR y lo
  corrige: a lo que escribió el motor **se lo vuelve a redactar** para que
  quepa (así el recorte se lo lleva la cita de la EPS y no el cierre del
  hospital), a lo que vino de DGH se le recorta el final en un punto, y los
  códigos que SIIFA no acepta se cambian por el que se indique. Todo queda
  marcado en la columna CORRECCION.
- **Ojo con dos cosas que quedaron pendientes de revisar:**
  1. Lo ya subido quedó con **la fecha del día del cargue**, no con la de
     DGH: los archivos se generaron el 03-08, antes de que existiera la
     columna FECHA_RESPUESTA. Para la EPS, esas respuestas figuran dadas en
     agosto.
  2. El desplegable de SIIFA para devoluciones ofrece tres respuestas
     («no procede por fuera de términos», «es injustificada al 100%»,
     «ha sido aceptada al 100%»), pero el portal no muestra el código. Para
     las 495 aceptadas con nota crédito hay que averiguar el código de «ha
     sido aceptada al 100%»: se responde UNA a mano en el portal y se mira
     el código en Ver Histórico.

### 05-08 (segunda parte) — La homologación de códigos DGH → SIIFA

- El portal muestra la **frase** de cada respuesta pero no el código, y el
  catálogo de la API vino vacío. Se armó la homologación por SIGNIFICADO con
  la evidencia que hay:
  - **RE9901** = «la glosa siendo justificable ha podido ser subsanada
    totalmente» — así lo devuelve el propio informe de SIIFA. NO es
    «no acepto».
  - **RE9702** = «la glosa/devolución ha sido **aceptada al 100%**» — en el
    piloto de la HUS497119 se escogió esa frase y en Ver Histórico quedó
    RE9702.
  - **RE9701** (DGH) = las devoluciones que el hospital **aceptó** con nota
    crédito. SIIFA no lo acepta → se homologa a **RE9702**.
- `siifa_corregir_rechazadas.py --homologar` aplica ese cambio y lo deja
  marcado en la columna CORRECCION.
- La opción **[7]** del bot ahora prueba todos los nombres de grupo conocidos
  del catálogo y, si ninguno responde, explica cómo sacar el código a mano:
  responder una a mano en el portal y mirarlo en Ver Histórico.
- El desplegable de **devoluciones** ofrece tres respuestas: «no procede por
  fuera de términos (aceptación tácita de la factura)», «la devolución es
  injustificada al 100%» y «la devolución ha sido aceptada al 100%».

### 05-08 (tercera parte) — No era el código: es la puerta

- **Corrección de lo anterior:** se había homologado RE9701 → RE9702 pensando
  que RE9701 no existía. **Yesid lo verificó contra el portal: RE9701 SÍ es el
  código de la devolución que el hospital acepta** —el desplegable de
  «Responder Devolución» ofrece esa respuesta—. La homologación quedó
  deshecha: el código de esas 495 no se toca.
- **Lo que en realidad falla:** el bot manda glosas Y devoluciones por la
  misma puerta, `PUT /api/SeguimientoFacturaGlosa/Respuesta`, que valida
  contra los códigos del grupo de GLOSA. Por eso el mensaje decía «no
  pertenece al grupo RESPUESTA»: el código es de devolución y se está
  entrando por la puerta de las glosas.
- **`tools/siifa_sondear_endpoints.py`** (nuevo): prueba las rutas y los
  grupos de catálogo candidatos y dice cuáles existen, **sin escribir nada**
  en la plataforma (solo consulta; una ruta que existe contesta 405 y una que
  no, 404). Con eso se sabe por dónde se responde una devolución.
- Lección para el chat: cuando el auditor tiene el portal delante, su dato
  manda sobre cualquier deducción hecha desde los datos.

### 05-08 (cuarta parte) — Resuelto: las devoluciones tienen su propia puerta

- **Piloto en verde:** `Devolución 17876242 (factura HUS481923): OK`. Con esa
  sola respuesta quedó confirmado todo: la puerta correcta, el id correcto y
  que **RE9701 siempre fue el código bueno** —lo dijo Yesid mirando el portal,
  contra la deducción del chat, y tenía razón—.
- **Lo que estaba mal:** el bot mandaba glosas y devoluciones por la misma
  puerta (`/api/SeguimientoFacturaGlosa/Respuesta`). Una devolución se
  responde por `/api/SeguimientoFacturaDevolucion/Respuesta`, que valida
  contra los códigos de devolución. Por eso SIIFA decía que RE9701 «no
  pertenece al grupo RESPUESTA»: el código estaba bien, la puerta no.
- **El id es el mismo** para los dos casos (`idSeguimientoFactura`): lo mostró
  el volcado crudo de la API. Por eso los archivos de cargue ya generados
  sirven tal cual, con solo actualizar el bot.
- **Cómo se llegó:** `tools/siifa_sondear_endpoints.py`, que prueba rutas y
  grupos del catálogo **sin escribir nada** en la plataforma, y el volcado de
  los campos crudos de una factura (`--factura HUS494196`).

### 05-08 (quinta parte) — SIIFA quedó al día: 2.579 de 2.579

| | Subidas | Pendientes |
|---|---|---|
| Glosas | **1.238 de 1.238** — $310.614.081 defendidos | 0 |
| Devoluciones | **1.341 de 1.341** líneas — 10 facturas por $115.051.312 | 0 |

- **Todas las glosas y devoluciones que SIIFA tenía sin responder quedaron
  respondidas.** El cargue de hoy fue en cuatro tandas y ninguna dejó errores.
- **La tabla de códigos de respuesta a devolución** (grupo
  `RESPUESTA_DEV_PTS_PSS`), que era lo que faltaba saber:
  - `RE9501` — la devolución no procede, se generó fuera de términos →
    aceptación tácita de la factura;
  - `RE9601` — el hospital aporta evidencia de que es injustificada al 100%;
  - `RE9701` — el hospital acepta la devolución al 100%.
- Se usó `RE9701` en las 495 que el hospital había aceptado con nota crédito y
  `RE9601` en las 674 que no acepta.

**Lo que queda por revisar (no urgente, pero conviene):**

1. **170 líneas de la factura HUS475438** se subieron el 4 y 5 de agosto por
   la puerta de las glosas, con el código RE9901, antes de que se descubriera
   el problema. Hay que mirar su histórico en el portal y decidir si se
   vuelven a responder por la puerta correcta.
2. **Las 674 devoluciones DE5601 podrían ganarse con `RE9501`.** Se subieron
   con RE9601 («es injustificada»), que es lo que decía el texto. Pero si al
   comparar fechas resulta que la EPS devolvió fuera de SU propio plazo,
   RE9501 es más fuerte: implica aceptación tácita de la factura. Requiere
   cruzar fecha de radicación contra fecha de devolución, caso por caso.
3. **La fecha de las respuestas subidas el 4 y 5 de agosto** quedó con el día
   del cargue y no con la de DGH (los archivos se generaron antes de que
   existiera la columna FECHA_RESPUESTA).

### 06-08 — Informe por entidad en Word, y cómo ver qué llega nuevo a SIIFA

**1. Informe para gerencia (`INFORME_SIIFA_POR_ENTIDAD.docx`).** Entrega en
Word con las cuatro entidades que glosaron o devolvieron, sus facturas,
valores y causales; el detalle de las 15 facturas de mayor valor; y una
sección que muestra lo que se ganó automatizando: **1.419 respuestas en 4
minutos y 58 segundos** (286 por minuto) frente a las ~86 horas —11 jornadas—
que habría tomado a mano. Incluye los tres hallazgos que destrabaron el
cargue y los tres puntos que quedan por revisar.

**2. El portal ya marca 2.620 registros** (antes 2.597): llegaron 23 nuevos.
El portal dice el total pero **no cuál es nuevo**, y buscarlos a mano son 175
páginas de a 10. Se creó **`tools/siifa_novedades.py`**, que compara el
informe de hoy contra el de la revisión pasada y responde, para cada novedad:
qué entidad, qué factura, si es glosa o devolución, por cuánto y con qué
causal. Queda como **opción [N]** del bot `CARGAR_SIIFA.cmd`: guarda el
informe anterior, baja el de hoy y compara solo. Si la bajada falla, devuelve
el informe anterior intacto.

**3. Un error de cuentas que se corrigió a tiempo.** Al probar el resumen, las
devoluciones daban **$24.917 millones**. La causa: SIIFA **repite el valor de
la factura en cada línea** de la devolución, y sumarlas multiplica la plata
(1.340 líneas de una factura de $111 millones). El valor real de esas 9
facturas es **$111.420.812** —224 veces menos—. Ahora el valor de una
devolución se cuenta **una sola vez por factura**, hay tres pruebas que lo
vigilan y quedó anotado en `docs/CONTEXTO_SIIFA.md`. Es la clase de cifra que
en un informe a gerencia no se puede sostener.

### 13-08 — 68 glosas nuevas respondidas, y el semáforo del trámite

**1. Llegaron 68 glosas nuevas y quedaron todas respondidas.** El portal pasó
de 2.597 a 2.665 seguimientos. Casi todas de **FAMISANAR** (67 de 68;
$30.013.228), más una de SANITAS. Total defendido: **$30.038.128** sobre 34
facturas. De esas, 27 salieron con la respuesta real que el hospital ya había
dado en Dinámica Gerencial y 41 las redactó el motor.

**28 de las 68 ya estaban vencidas** ($15.345.553). Se respondieron igual: una
respuesta tardía se discute, una glosa sin respuesta se pierde.

El cargue tomó **58 segundos de máquina** (17 de escritura efectiva, unas 240
respuestas por minuto) contra las 2 horas y media que habría tomado a mano.
Seis rebotaron por el límite de 1.500 caracteres —el mismo error de siempre— y
entraron a la primera después de recortarlas. Entre ellas la más grande del
lote, HUS521868 por $3.399.053.

**2. FAMISANAR reformula glosas — y eso puede dañar un cargue.** Al comparar
los informes del 6 y el 13 de agosto, una glosa desapareció: la de HUS517950
(CL0801, $665.200, del 30 de junio). No se perdió: la EPS la borró y la volvió
a crear el 9 de julio con otra causal (SO0801) y **número de seguimiento
nuevo**. Lección: **las respuestas se arman contra el informe bajado el mismo
día del cargue**, nunca contra uno de días atrás, porque el id viejo puede ya
no existir. El comparador avisa cuando algo desaparece; así se detectó.

**3. Nueva herramienta: `siifa_estado_tramite.py` (opción [E] del bot).** El
panel «Avance de auditoría» del portal muestra las cinco etapas del trámite
para UNA factura; esto lo hace para las 2.600 de una vez y dice **a quién le
toca mover**. Lo primero que muestra es lo que le toca al hospital, con su
fecha de vencimiento.

Con esa herramienta aparecieron cosas que nadie estaba mirando:

- **3 glosas LEVANTADAS: $1.418.479 que SANITAS le dio la razón al hospital.**
  Nadie lo sabía porque hay que entrar factura por factura a verlo.
- **5 reiteradas ($15.445.892) con el plazo de subsanación corriendo.** Cuando
  la EPS reitera, al hospital le quedan **7 días hábiles** —menos de la mitad
  que los 15 de la primera respuesta— y **nadie avisa**. Cuatro son
  devoluciones de SANITAS por $14 millones.
- **16 glosas donde la EPS está en mora**: respondimos y no ha decidido dentro
  de sus 10 días hábiles.

**4. Otro error de cuentas atajado a tiempo.** El semáforo repetía el error de
sumar las devoluciones línea por línea: mostraba $25.221 millones donde hay
$428 millones. La regla quedó ahora en **una sola función** (`valor_total()`
en `siifa_novedades.py`) que usan las dos herramientas, en vez de copiada en
cada una — igual que el lector de pesos. Es el mismo error, cometido dos veces
en dos semanas: por eso ahora vive en un solo sitio y con pruebas.

### 13-08 (segunda parte) — La subsanación: la etapa que nadie estaba mirando

Con el semáforo del trámite apareció lo que seguía: **la EPS ya respondió**
algunas glosas, y eso abre la etapa 4.

**Lo que se encontró (informe del 6 de agosto):**

- **3 glosas LEVANTADAS — $1.418.479 recuperados.** SANITAS le dio la razón al
  hospital en HUS467326 ($1.396.804), HUS464765 y HUS463797. Nadie lo sabía
  porque hay que entrar factura por factura al portal a verlo.
- **1 glosa REITERADA** (HUS465198, $1.396.804): hay que subsanar.
- **4 DEVOLUCIONES REITERADAS** ($14.049.088), todas de SANITAS.

**Nueva herramienta: `siifa_armar_subsanacion.py` (opción [S] del bot).** Arma
el archivo para insistir ante lo reiterado. El escrito **no repite** la
primera respuesta —la EPS ya la leyó y no la aceptó—: deja constancia de que
el hospital contestó y en qué fecha, señala que la reiteración no aporta
elemento nuevo, y conserva el argumento de fondo de la causal.

**Las 4 devoluciones reiteradas NO se cargan todavía, y es a propósito.** La
puerta de subsanación está confirmada sólo para glosas
(`PUT /api/SeguimientoFacturaGlosa/ReiteracionRespuesta`); para devoluciones
no se conoce. Mandarlas por la de glosas escribiría sobre otro registro y el
reporte diría OK — el mismo daño que costó descubrir en agosto. Salen en una
hoja aparte, sin código ni texto, y el bot las bloquea. Se amplió
`siifa_sondear_endpoints.py` con las rutas y grupos candidatos para
averiguarlo **sin escribir nada** (sólo consulta).

**La primera subsanación quedó cargada** (HUS465198, $1.396.804) — el
trámite llegó por primera vez a la etapa 4.

**El sondeo mintió, y por poco cuesta caro.** Dijo que existían seis rutas,
entre ellas tres para subsanar devoluciones. Era falso: SIIFA tiene rutas del
tipo `/api/SeguimientoFacturaGlosa/{id}`, así que al preguntar por
`/api/SeguimientoFacturaDevolucion/ReiteracionRespuesta` responde ESA otra
ruta, quejándose de que «ReiteracionRespuesta» no es un número válido para el
id. El 400 se leía como «la ruta existe». Mandar una escritura ahí habría ido
a parar a otro registro, con OK falso en el reporte —exactamente el daño que
la hoja aparte quería evitar—.

Ya está corregido: cuando el error menciona el último trozo de la ruta como
si fuera un id, el sondeo lo marca **NO CONCLUYENTE - NO ESCRIBIR** en vez de
«existe». Tres pruebas lo vigilan.

**Los grupos de códigos de la subsanación salieron todos vacíos**
(`REITERACION_*`, `SUBSANACION`, `RESPUESTA_GLOSA_PTS_PSS`). La subsanación de
glosa funcionó igual con RE9901, así que para glosas no hace falta.

**Las 4 devoluciones reiteradas ($14.049.088) siguen sin vía por API.** Lo que
falta es mirar en el portal qué ofrece el menú de una devolución reiterada: el
nombre que aparezca ahí es la pista del endpoint, igual que en agosto el
propio mensaje de error reveló el grupo `RESPUESTA_DEV_PTS_PSS`. Mientras
tanto, se pueden subsanar **a mano** en el portal: son cuatro.

### 13-08 (tercera parte) — SIIFA al día: 2.665 de 2.665, y la EPS en mora

Verificado contra la plataforma después del cargue:

| Etapa | Le toca a | Ítems | Valor |
|---|---|---|---|
| 2. Respondida, esperando decisión | EPS | 2.657 | $458.717.238 |
| 3. **Levantada — ganada** | — | **3** | **$1.418.479** |
| 4. Reiterada — falta subsanar | HOSPITAL | 4 | $14.049.088 |
| 5. Subsanada, esperando decisión final | EPS | 1 | $1.396.804 |

**No queda ni un seguimiento sin responder.** Lo único pendiente del hospital
son las 4 devoluciones reiteradas de SANITAS, que hay que hacer a mano.

**Dato nuevo y aprovechable: las EPS están en mora.** Tienen 10 días hábiles
para decidir si levantan o reiteran una glosa ya respondida, y **43 se
pasaron**: FAMISANAR 27 por $14.680.353 y SANITAS 16 por $1.030.100. Es
incumplimiento de ellas y sirve para la mesa de trabajo.

**Otro cálculo corregido.** El semáforo marcaba «VENCIDA» la subsanación
cargada esa misma mañana. La causa: los 5 días de la decisión final corren
desde la SUBSANACIÓN, y esa fecha no viene en el informe; se estaba contando
desde la respuesta original del 5 de agosto. Una mora inventada de la EPS es
un reclamo que no se puede sostener, así que ahora esa etapa no calcula
vencimiento y lo dice. (Con eso SANITAS pasó de 17 a 16 en mora.)

Entregado el informe en Word `INFORME_CARGUE_SIIFA_13AGO.docx` con las ocho
secciones, incluida la del estado verificado contra la API.

### 13-08 (cuarta parte) — De un hospital a cuatro IPS

El auditor ahora administra **cuatro prestadores** y quiere trabajarlos a la
vez: HUS (900006037), Clínica Socorro (900190045), Clínica Girón (890203242)
y Clínica Guane (804006936).

**Cada IPS tiene lo suyo:** su carpeta (`...\SIIFA\HUS`, `...\SIIFA\SOCORRO`,
etc.), sus credenciales (`SIIFA_USER_HUS`, `SIIFA_USER_SOCORRO`…) y su nombre
en el título de la ventana. Todas las herramientas reciben `--ips`, y el bot
de doble clic pregunta con cuál se trabaja **antes que nada**.

**La guarda que evita el error caro.** Antes de bajar o escribir, la
herramienta le pregunta al token de SIIFA a qué NIT pertenece y lo compara
con la IPS elegida. Si no coinciden, se detiene **sin tocar la plataforma** y
dice de quién son las credenciales que encontró. Con cuatro ventanas
abiertas, confundirse es cuestión de tiempo, y una respuesta cargada en la
entidad equivocada no se puede deshacer. Una prueba recorre los scripts que
entran a SIIFA y falla si alguno se salta la comprobación.

**Un problema que apareció al revisar, y era grave.** El texto de las
respuestas decía «ESE HOSPITAL UNIVERSITARIO DE SANTANDER NO ACEPTA…» escrito
a mano, con el correo `CARTERA@HUS.GOV.CO` y la dirección de la Carrera 30.
Las respuestas de la Clínica Socorro habrían salido **firmadas por el HUS y
con los datos del HUS** — en un escrito con efectos jurídicos ante la EPS. Ya
está parametrizado: cada IPS pone su nombre, y **si no tiene correo y
dirección cargados, la frase se omite** en vez de poner los de otra.

**Falta:** el correo y la dirección de Socorro, Girón y Guane, para que sus
respuestas cierren con sus propios datos de contacto.

**Cuatro huecos más, encontrados revisando a fondo** (tres los halló una
revisión adversarial del diseño; el cuarto salió en la primera corrida real):

1. **La guarda del ARCHIVO, no sólo de las credenciales.** Comprobar el token
   protege lo que se escribe; faltaba proteger lo que se lee. Con cuatro
   carpetas parecidas y archivos que se llaman igual en todas, pasarle el
   informe de otra IPS era facilísimo —y de ahí salen las respuestas—.
   Comparar el informe de una contra el de otra, además, habría reportado
   todos sus registros como «novedades». Ahora se compara el NIT del emisor.
2. **Las constancias PDF salían a nombre del HUS.** Se anexan a la EPS como
   evidencia: una constancia de la Clínica Girón encabezada «Hospital
   Universitario de Santander» no prueba nada. Y el nombre del archivo no
   distinguía la IPS, así que una pisaba a la otra.
3. **Dos IPS bajando a la vez se borraban el archivo de prueba de escritura**
   (se llamaba igual en las dos), y una concluía «no puedo guardar acá»
   cuando sí podía. Pasó de verdad con tres corridas en paralelo.
4. **Al pasar a «mes por mes» seguía pidiendo tandas de 1.000.** Si la
   consulta completa falló por peso, partirla en meses pero conservar la
   tanda gigante es repetir el error a pedazos. Girón y Guane se atoraron
   así, mes tras mes. Ahora la tanda baja a 200 al pasar a meses.

**Lo que se aprendió del primer día con las cuatro:** Socorro tiene **60.568
seguimientos** (23 veces el HUS). Y el servidor del Ministerio **no aguanta
tres consultas pesadas a la vez**: con las tres corriendo, Socorro degradó de
1.000 a 62 registros por página. Conviene bajarlas de a una.

### 18 y 19-08-2026 — Los cargues masivos de las cuatro IPS en SIIFA

**Socorro: 48.766 respuestas cargadas** (unas 3 horas y media de robot).
El revisor previo (`siifa_revisar_antes_de_cargar.py`, nuevo) apartó antes
del cargue lo que iba a fallar: ya respondidas, textos pasados de 1.500
caracteres, códigos de devolución en glosas, 16 sin texto. De la corrida,
48.009 entraron a la primera y 756 dieron «error» de tiempo de espera —
pero al verificar contra la plataforma **la escritura sí había entrado**:
SIIFA las tenía todas. De ahí salió una regla nueva del informe:
un error de «ya tiene un registro previo» cuenta como REGISTRADA.

**El informe final ahora funciona sin los CSV del robot (modo censo).**
Una corrida interrumpida pisó el reporte del cargue grande y el informe
solo veía 1.271 filas. Ahora `siifa_informe_del_cargue.py` puede partir
del informe masivo solo: dice cuánto de lo que SIIFA tiene está respondido
(lo del robot y lo cargado antes) y qué falta. Con eso salió el informe de
Socorro completo: **59.732 de 60.567 respondidas ($2.224 millones
defendidos)**; quedan ~835 nuevas que llegaron después del corte.

**Las 16 de Socorro que faltaban por texto: alguien ya las había respondido
a mano.** Al cargarlas, las 16 rechazaron con «ya tiene un registro previo».
No hubo daño, pero conviene **coordinar con quien responde manualmente en la
clínica** para no duplicar trabajo.

**Girón: 1.085 respuestas cargadas.** Falta correr su informe final (censo).

**Guane: 1.530 respuestas** (522 glosas y 1.008 devoluciones con RE9701 =
aceptar la devolución al 100%, confirmado con el archivo del auditor);
el cargue y su informe final quedaron corriendo en el equipo de cartera.

**HUS: la subsanación con el texto institucional.** El auditor entregó la
plantilla oficial del HUS para glosas ratificadas (RE9901: se mantiene la
respuesta, se pide conciliación, art. 57 Ley 1438/2011). Quedó en
`tools/plantillas/subsanacion_HUS.txt` y el armador de subsanación la usa
con `--texto`. La única glosa ratificada pendiente ya estaba subsanada.
**Ojo:** el botón «Crear decisión» del portal es una etapa del PAGADOR;
el hospital no debe usarlo.

**Herramienta nueva: el BALANCE de un corte** (`siifa_balance.py`, opción
[B] del bot). Después de un cargue responde las cuatro preguntas de una vez,
por IPS: qué estaba glosado al corte, qué de eso quedó respondido (separando
lo que ya venía respondido de antes), qué **sigue sin responder** y qué
**nuevo** ha glosado la EPS desde entonces. Deja un Excel con lo pendiente
de primero y avisa si algo del corte desapareció del informe (posible
reformulación de la EPS). Con pruebas que cuidan las dos confusiones caras:
contar como logro lo que ya venía respondido, e inflar el valor de las
devoluciones.

---

## 3) PENDIENTE

### Conciliación Dispensario (147 facturas objeto de mesa)

1. **Revisar y aprobar el listado de las 147** (`LISTADO_147_PARA_APROBAR.xlsx`)
   y decidir qué se hace con **HUS0000443525**, que está en el lote de glosas
   pero **no aparece en el estado de cartera**: ¿se incluye (147) o se excluye
   (146)? Hoy está incluida.
2. **Aclarar la discrepancia del aceptado:** el lote dice $0 (RE9901) pero la
   cartera registra **$1.758.956** aceptados en 8 facturas. Debe resolverse
   antes de firmar el acta.
3. **Revisar las 29 facturas con diferencia** entre el valor glosado del lote y
   el de la cartera.
4. **Confirmar las raíces exactas `Y:` / `X:`** de los soportes para cerrar la
   columna de ubicación (hoy queda la ruta derivada por mes + PENDIENTE).
5. **Conseguir la CUENTA CONTABLE** con contabilidad/DGH: es el único campo del
   acta que no existe en ninguna base disponible.
6. Plantear en la mesa que la entidad **no ha confirmado el recibo de ninguna
   de las 444 respuestas**, pese a que todas tienen radicado de entrega.

### Pre-auditoría
0. **~~La lentitud de la página~~ — DIAGNOSTICADA Y ARREGLADA el 29-07**
   (ver la entrada del día). Queda una sola cosa por decidir: **el buscador de
   la pestaña Fuentes sigue lento** (recorre las 189.452 filas de la fuente, y
   ahí es a propósito: esa pantalla existe para buscar entre TODAS las
   facturas, no solo las del consolidado). Hacerlo rápido necesita búsqueda de
   texto completo, que es un cambio mayor. **Preguntar al auditor si esa
   pantalla le molesta en el día a día** antes de meterle mano.

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

### Pre-auditoría ADRES (`tools/preauditar_glosas_adres.py`)
16. **Unificar el criterio de la causal 4506**: hoy está clasificada como
    FACTURACION en 231 filas y como PERTINENCIA en 24.
17. **Revisar las 371 filas sin centro de costos propuesto** (habitación, sala
    especial, atención diaria: no se puede saber el área sin más contexto).
18. **Fase 2 — llevarlo al motor web como preauditoría.** El patrón ya existe
    en `app/services/ia_auditora_proactiva.py` (pre-análisis nocturno que deja
    el dictamen listo antes de que el gestor abra la glosa). Las 10 columnas de
    la macro mapean a campos que ya tiene `GlosaRecord` (`codigo_respuesta`,
    `tipo_glosa_excel`, `observacion_tecnico`, `dictamen`, `valor_aceptado`,
    `gestor_nombre`, `profesional_medico`); falta agregar centro de costos.

### Ajustador de detallados (`tools/ajustar_detallado_glosas.py`)
11. **Las 4 facturas que no aparecen en ningún detallado:** HUS0000311371,
    HUS0000367368, HUS0000380246 y HUS0000394817. Pedir su impresión para
    poder cerrarlas.
12. **Revisar los 100 ítems marcados `SIN_CRUCE`** (73 facturas) y los 24
    `GLOSA_SIN_ITEM` ($11.220.692): son renglones que no cruzaron entre la
    factura impresa y el reporte del ADRES.
13. **Glosas a toda la reclamación:** 46 filas por $335.585.041 con causales
    como "2102- formulario de reclamación incompleto" y "3122- debe anexar el
    informe de ambulancia". No corresponden a ningún ítem: se responden aparte.
14. **Confirmar el criterio de los ítems aprobados a medias.** En el ejemplo
    `HUS352890` la venda de gasa quedó a mano en **1 unidad / $9.400**, pero
    sumando las **dos** filas del reporte siguen glosadas **5 unidades /
    $47.000** (subtotal $132.800 en vez de $95.200). El bot hace la suma. Si el
    criterio del auditor es otro, se cambia con `--modo-parcial`.
15. **Definir qué hacer con los ítems `SIN_CRUCE`** (los de la factura que no
    aparecen en el reporte): hoy se conservan y se marcan.
### Dispensario — respuesta de glosas SIMED y conciliación
10. **Las 3 facturas de junio** (518186 / 515107 / 515773): en el pantallazo
    de pendientes del 05-08 **ya no figuran por cargar**. Verificar en el
    portal cómo quedaron radicadas (¿respuesta cargada o cerradas por
    vencimiento?); si el portal las cerró sin respuesta, radicar por
    oficio/correo dejando constancia.
11. **(05-08) Correr el cargue de las 23 pendientes** con
    `respuestas_glosa_DISPENSARIO_PENDIENTES_05AGO.xlsx`: piloto con
    HUS0000513796 → corrida completa → pegar el reporte al chat. En las de
    valor alto (500031, 510793, 454563, 512742, 518923, 522160) revisar en el
    reporte que ninguna quede "sin finalizar" por tener más líneas en el
    portal que filas en el Excel (si pasa, avisar al chat y se amplía).
12. **Generar los PDF de evidencias:** lote 14-07 → `GI-33-5182-2026.pdf`
    (comando ya entregado); lotes 17/28/31-jul + corrida de pendientes →
    `GI-33-5251-2026.pdf`; cargue del 23-jul → `GI-33-5285-2026.pdf`
    (los tres comandos quedaron entregados en el chat el 05-08).
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
- ~~(28-07) Lote del 28-jul: NO subir todavía~~ — **Superado el 05-08:** el
  portal muestra el lote ya subido (solo se escapó la 530112, que entra en el
  cargue de las 23 pendientes). Sigue vigente de esa nota únicamente la
  pregunta de la **prórroga 2026 del contrato 440** (ver "OJO jurídico" del
  05-08).

### Informes
16. **Informe de gerencia:** falta el dato real del "antes" (cuánto tardaba el
    proceso manual y cuántas personas) para poner el multiplicador exacto.
    Completar también el "valor total objetado defendido" del lote 9-jul
    (sale de `reporte_glosa.csv`).

### Módulo ADRES/FURIPS (chat "VALIDADOR ADRES")
20. ~~Fusionar el PR #176~~ — **HECHO el 29-07**: todo el módulo (validador
    con OCR, app web, bot DE4401 v2.1, documentación de entrega) ya está en
    la rama principal.
21. **Bot DE4401:** correr la versión 2.1 con los archivos reenviados y, si
    algo sale "SIN XML", enviar el Excel `_COMPLETO` (la hoja DIAGNOSTICO
    dice la causa exacta).
22. **Confirmar en el servidor** que `PDF_A_CMD_EN_CARPETA.cmd` genera la
    carpeta `CMD_CONVERTIDOS`.
23. **Corregir las 27 facturas ADRES con errores** de la corrida de 50 (usar
    el Excel o la app web, priorizando las de mayor valor) y completar los
    soportes de HUS410606 y HUS472103 (les faltan RIPS y CUV).
24. **Facturas de baja:** completar el informe de trabajo social donde el
    Word quedó con "NOTA DE REVISIÓN".

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

### SIIFA (actualizado 19-08, ver `docs/CONTEXTO_SIIFA.md`)
11. **HUS — 4 devoluciones ratificadas de SANITAS ($14.049.088), trámite
    MANUAL en el portal y ya vencidas o al borde** (HUS482639, HUS479521,
    HUS479457, HUS481923). La puerta de subsanación de devoluciones por API
    no está confirmada; el texto sirve el de la plantilla del HUS ajustando
    factura y valor. **Es lo más urgente de SIIFA.**
12. **Cerrar el ciclo con el BALANCE de las cuatro IPS** (opción [B] o
    `siifa_balance.py`): corte contra informe fresco de HUS, Socorro, Girón
    y Guane — qué se respondió, qué falta y qué hay nuevo. Con eso salen
    también las ~835 nuevas de Socorro y las 2 nuevas del HUS.
13. **Girón y Guane:** correr el informe final del cargue (censo) de Girón;
    recibir la salida del cargue de Guane (1.530) y su informe.
14. **Datos de contacto de Socorro, Girón y Guane** (correo y dirección de
    ventanilla) para que sus respuestas cierren con sus propios datos; hoy
    la frase se omite. Y **coordinar con quien responde a mano en Socorro**
    para no duplicar trabajo. Queda también por definir RE9501 vs RE9601 en
    las 674 devoluciones DE5601 del HUS (~$111 millones).

### Cuentas médicas — CUV de facturas nuevas (nuevo, 03-08)
15. **Factura MED737 — la pelota está en facturación.** El JSON ya quedó bien
    (las 4 correcciones + `codPrestador` de 12 dígitos, que era el correcto).
    Falta que **reexpidan la factura** con el `CODIGO_PRESTADOR` a **10 dígitos
    (6800103933)** en el XML. Enviarles el pedido por escrito con los dos
    valores explícitos: XML = `6800103933`, JSON = `680010393301`.
16. **Avisar al proveedor del software de facturación** (el rastro apunta a
    Siigo): si usa un solo parámetro para el XML y el RIPS, hay que separarlos.
    Si no, el RVC011 se repite en todas las facturas.
17. **Antes de reexpedir, confirmar quién atendió:** la factura dice "consulta
    especializada" y el RIPS reporta CUPS 890201 (medicina general). Si atendió
    un especialista, el CUPS y el `codServicio` también deben corregirse en la
    misma reexpedición. Pedir el soporte de quién atendió.
18. **Preguntar al Ministerio la vía correcta** (mesa de ayuda,
    Soporte-fev-rips@minsalud.gov.co): si para corregir el `CODIGO_PRESTADOR` de
    una FEV ya validada por la DIAN toca nota crédito de anulación total y
    reexpedición, o si basta retransmitir. Ningún texto oficial lo ordena; la
    vía de la anulación viene de mesas de ayuda de proveedores. Cuesta cero
    preguntar y evita anular una factura sin necesidad.
19. **Revisar el resto de facturas de agosto** con `validar_json_rips.py
    --recursivo` antes de subirlas.
20. **Revisar el número de factura si la reexpiden:** si sale con número nuevo,
    el JSON debe llevar el número nuevo, no `MED737`.

## 4) PARA MAÑANA

**SIIFA (lo primero, 19-08):** (a) tramitar a mano en el portal las 4
devoluciones ratificadas de SANITAS del HUS ($14.049.088, pendiente #11);
(b) cerrar Guane (salida del cargue + informe); (c) correr el **balance**
de las cuatro IPS con la opción [B] del bot — de ahí sale qué quedó sin
responder y qué nuevo hay que trabajar.

00. **Antes de cualquier prueba de IA: reiniciar con
    `tools\REINICIAR_MOTOR.cmd`** (doble clic). Cierra los motores viejos
    que quedaron prendidos y deja uno solo. Después, en **Gobierno IA →
    «Probar proveedores de IA»**, verificar que la clave que aparece ahí sea
    la misma que muestra el arranque. Si el Diagnóstico marca en rojo la
    tarjeta «Motor (quién está atendiendo)», hay más de uno: cerrar y
    repetir. Con eso queda lista la prueba de fuego pendiente: **pasar la
    glosa de PPL por Analizar** y confirmar que sale con el formato
    aprobado.
0. **PRIORIDAD CERO — revivir la página YA (arranque exprés) y luego
   restaurar la historia.** Actualizado 04-08: la deuda ya se pagó; Google
   reabre la cuenta por soporte (caso #74044918, 24-48 h). Mientras tanto:
   (a) en el PC de cartera instalar Docker Desktop y Git; (b) sacar el token
   del túnel en Cloudflare y doble clic a
   `tools\REVIVIR_EXPRESS_SIN_RESCATE.cmd` (guía: sección "Arranque exprés"
   de `docs/MIGRACION_PC_HOSPITAL.md`) — con eso el equipo trabaja hoy con
   base provisional. (c) Cuando llegue el correo de Google: rescate de la
   fase 1 (`rescate-motor-glosas.tgz`) y **avisar al chat antes de restaurar**
   la base histórica; (d) verificar y apagar la VM (fase 4).
1. **Dispensario prioridad 1 (actualizado 05-08):** correr el cargue de las
   **23 pendientes** (piloto con HUS0000513796 → corrida completa → pegar el
   reporte al chat) y después armar los dos paquetes de evidencias:
   **GI-33-5251-2026** (lotes 17/28/31-jul + pendientes) y
   **GI-33-5285-2026** (cargue del 23-jul). Verificar cómo quedaron radicadas
   las 3 de junio (ya no figuran pendientes) y averiguar si hay **prórroga
   2026 del contrato 440** para blindar los próximos textos.
2. Correr la **pertinencia fusionada** COOSALUD (pendiente #1) y verificar que
   las 37 facturas cierren con evidencia.
3. Con los reportes en mano, **cerrar los flecos de los lotes 02/06/07/08**
   (segunda pasada de las que queden pendientes).
4. Generar los **Words de evidencia** de todo lo cerrado y archivarlos en sus
   carpetas por mes/día.
5. Actualizar el **informe de gerencia** con el acumulado real de julio
   (facturas y glosas cerradas por lote).
6. **Revisar los Excel ajustados del paquete 31068** que quedaron generados y
   los pendientes #11 a #15. Guías en `tools/README_ajustar_detallado_glosas.md`
   y `tools/README_por_factura_y_pdf.md`.
7. **Repetir el PDF con el Excel del equipo** (`--motor excel`): los PDF que se
   entregaron salieron con LibreOffice, que puede tener mínimas diferencias de
   maquetación frente al Excel del hospital.
8. **Estrenar en la página el módulo 📄 Glosas ADRES** con un gestor real:
   cargar el paquete 31068 (reporte + macro + `BITACORA_31068.csv`) y que el
   gestor pruebe con 5 facturas antes de soltarlo a todo el equipo.
   Guía: `docs/GLOSAS_ADRES_WEB.md`.
9. **Repartir las 255 glosas de causal 4506** desde la pantalla (lo hace un
   super admin). El bot ya propone: 229 para los gestores y 26 para las
   médicas, cada una con su motivo. Solo hay que confirmar o corregir.
10. **Completar los 371 renglones sin centro de costos**: son los que el nombre
    del servicio no alcanza a identificar. Se pueden llenar desde la misma
    pantalla y el sistema los recuerda para el siguiente paquete.
6. Si hay tiempo: verificar si SISTEMAS ya corrigió algún CUV (pendiente #6),
   descargar los 2 PDF del DIAN (pendiente #7) y revisar el PR #186 del módulo
   de pre-auditoría.
7. **ADRES:** (PR #176 ya fusionado el 29-07) copiar al servidor el PAQUETE
   COMPLETO (ZIP del 27-07) y correr la v2.1 del bot DE4401 (pendiente #21).
8. **SIIFA — revisar los dos archivos de respuestas y hacer el piloto.**
   Ya están generados `respuestas_GLOSAS.xlsx` (1.238) y
   `respuestas_DEVOLUCIONES.xlsx` (1.341), con respuesta en TODAS las filas:
   1.082 son la respuesta real que el hospital ya había dado en DGH y 1.497
   las redactó el motor nuevo (`tools/siifa_redactar_respuestas.py`). Cada
   fila dice en la columna REVISAR qué hay que verificar antes de subirla.
   Lo urgente de revisar: las de soportes (SO*), que no se sostienen sin
   anexar el papel, y las 674 devoluciones DE5601, donde hay que confirmar
   el acuse de radicación. Después, piloto de 1 glosa y cargue.

   **Decisión del 03-08:** primero se cargan SOLO las 1.082 respuestas reales
   del hospital. Volver a generar los archivos agregando al final del comando
   `--solo-lo-ya-respondido`: los de cargue quedan con las verdes y las
   redactadas se van a los archivos `_REDACTADAS`. Esas 1.497 quedan
   pendientes de revisar por tandas (empezando por las de mayor valor) —
   no se pueden dejar vencer: sin respuesta a tiempo, la glosa se entiende
   aceptada.

9. **SIIFA — lo que quedó del trabajo anterior.** El informe
   maestro ya está rebajado (2.597) y la hoja de trabajo ya salió cruzada
   con DGH: de las 272 respuestas, **162 vienen puestas** y **110 hay que
   escribirlas**. El orden del trabajo es:
   (a) mirar las **93 filas marcadas en REVISAR** (las de origen POR_CODIGO
   y las que en DGH tenían más de una respuesta);
   (b) escribir las 110 que dicen ESCRIBIR — ahí están las 482 glosas de
   HUS454747 y las devoluciones, que no tienen trámite en DGH;
   (c) **decidir qué se hace con las 1.169 devoluciones DE5601**, que es un
   trámite distinto al de una glosa;
   (d) expandir con `siifa_preparar_respuestas.py --expandir` y hacer el
   **piloto de 1 glosa** antes del cargue masivo (pendiente #13).

10. **Cerrar la MED737 (cuentas médicas):** corregir el JSON con el comando de
    PowerShell de `docs/CONTEXTO_FEV_RIPS_CUV.md`, resolver con facturación el
    conflicto de fechas y confirmar que el Ministerio entregue el CUV
    (pendiente #15). Después pasar `validar_json_rips.py --recursivo` a todas
    las facturas de agosto (pendiente #16).

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
13. **Preguntar a contratación por las prórrogas.** Según la malla del 28-07,
    los contratos de COMPENSAR y COOSALUD subsidiado ya vencieron y los de
    NUEVA EPS y SALUD MIA están al límite. Si hay prórroga u otrosí firmado,
    avisar para actualizar la malla del sistema; mientras tanto, el sistema
    defiende esas atenciones a tarifa SOAT plena, que es lo correcto sin
    contrato vigente.

### Contrato de Construcción — decisiones que dependen de Yesid (28-07 noche)

13. **Leer el Anexo I del Contrato** (`docs/CONTRATO_CONSTRUCCION_SINAC_OS.md`,
    al final). Son diez páginas y responden lo único que importa ahora: qué se
    construye primero, qué se ve funcionando y cuánto cuesta. Con eso basta
    para decidir; los veinte capítulos son el detalle.
14. **Aprobar o cambiar los siete resultados comprometidos.** Están escritos
    como cosas que usted ve en pantalla, no como tareas técnicas. Si alguno no
    le sirve o falta uno, se cambia ahí y el plan se recalcula solo.
15. **Decidir qué pasa con las 661 tareas que quedaron fuera de todo
    resultado** (1.462 jornadas, el 90 % del esfuerzo). Dos salidas honestas
    por cada una: o se le escribe el resultado que justifica su existencia, o
    se acepta que va después. Lo que no sirve es dejarlas marcadas urgentes
    sin destinatario, que es como estaban.
16. **Decidir el tamaño del equipo.** El Contrato completo son 1.625,5 jornadas
    ≈ siete años de una persona. La primera entrega —los tres resultados que
    recuperan plata ya— son 79,5 jornadas ≈ cuatro meses de una persona, o un
    mes de cuatro. De esa decisión sale todo lo demás.
17. **Tres tareas están escritas dos veces** en capítulos distintos (migrar los
    perfiles de pagador a YAML, la pantalla de Perfiles, y las pruebas de
    arquitectura bloqueantes). Hay que decidir cuál capítulo conserva cada una
    antes de que dos personas las construyan por separado.
    del servicio no alcanza a identificar. Se escogen del desplegable oficial
    (45 centros) y el sistema los recuerda para el siguiente paquete.
11. **Preguntar a facturación por las 4 facturas sin detallado** (311371,
    367368, 380246, 394817 — $43.518.600 glosados): no vinieron en ninguno de
    los siete lotes. Hay que pedir esa impresión y volver a correr el
    ajustador.

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
- **ADRES/FURIPS:** repositorio de XML de facturación
  `\\172.16.32.83\factura_electronica_net22\<AAAAMM>\FACTURAS_SALUD\` (una
  subcarpeta por factura; la ruta se edita en la línea RUTA_FACTURAS de
  `COMPLETAR_INFORME_XML.cmd` cuando cambia el período). Los `.cmd` de
  `tools/` DEBEN conservar finales de línea CRLF (regla en `.gitattributes`);
  con LF la ventana se cierra sin ejecutar nada.

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
