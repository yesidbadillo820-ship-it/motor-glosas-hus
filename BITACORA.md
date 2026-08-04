# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana).

**Última actualización:** 04-08-2026

---

## 1) Las tres patas del proyecto

1. **Motor de Glosas (aplicación web con IA):** recibe las glosas y redacta el
   dictamen de defensa del hospital (cita contrato, tarifas, normativa). Vive en
   la carpeta `app/` y se usa desde el navegador.
2. **Bots de carga (robots que suben respuestas a las plataformas):**
   - `tools/responder_glosas_coosalud.py` — portal de COOSALUD (vco.ctamedicas.com).
   - `tools/responder_glosas_simed.py` y `tools/cargar_soportes_simed.py` — SIMED (Dispensario Médico).
   - `tools/responder_glosas_dgh.py` — Dinámica Gerencial (programa de escritorio del hospital).
   - Otros: Mutual Ser, FOMAG, radicador de facturación.
3. **Herramientas de apoyo:** armar el Word/PDF de evidencias
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
- **30-06:** arranca el **bot de Dinámica Gerencial (DGH)** (muchas iteraciones
  para dominar el programa de escritorio). **Tablero de Radicación y Cartera**
  (informe HTML con alertas de mora +90 días, exportar a Excel). Mejoras al
  motor IA (rondas 19-22) y set de evaluación de calidad de los dictámenes:
  la calidad del motor pasó de **2,5 a ~9 sobre 10**.

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
- **22-07 (hoy):** llegaron las respuestas de pertinencia en 3 archivos
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

### Informes
10. **Informe de gerencia:** falta el dato real del "antes" (cuánto tardaba el
    proceso manual y cuántas personas) para poner el multiplicador exacto.

## 4) PARA MAÑANA

1. Correr la **pertinencia fusionada** (pendiente #1) y verificar que las 37
   facturas cierren con evidencia.
2. Con los reportes en mano, **cerrar los flecos de los lotes 02/06/07/08**
   (segunda pasada de las que queden pendientes).
3. Generar los **Words de evidencia** de todo lo cerrado y archivarlos en sus
   carpetas por mes/día.
4. Actualizar el **informe de gerencia** con el acumulado real de julio
   (facturas y glosas cerradas por lote).
5. Si hay tiempo, avanzar el frente Dispensario: verificar si SISTEMAS ya
   corrigió algún CUV (pendiente #6) y descargar los 2 PDF del DIAN
   (pendiente #7).
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
9. **Unificar el criterio de la causal 4506** (hoy 231 FACTURACION vs 24
   PERTINENCIA). Mientras esté dividida, el bot no sugiere nada para ella.
10. **Completar los 371 renglones sin centro de costos**: son los que el nombre
    del servicio no alcanza a identificar. Se pueden llenar desde la misma
    pantalla y el sistema los recuerda para el siguiente paquete.

---

## 5) Datos fijos que siempre se necesitan

- **Carpeta de trabajo en Windows:** `C:\temp-notas` (ahí vive el repo).
- **Rama de trabajo:** `claude/excel-reconciliation-data-9Bnpj`. Antes de correr
  nada: `cd C:\temp-notas` y `git pull`.
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
