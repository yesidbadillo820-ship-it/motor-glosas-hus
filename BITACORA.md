# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana).

**Última actualización:** 03-08-2026

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

### Agosto 2026 — Validación de RIPS para el CUV
- **03-08:** cuentas médicas reportó que el validador del Ministerio no le
  generaba el **CUV** de la factura **MED737** (Medical Center Especialistas,
  NIT 900299334): salía `RVG01 | Dato requerido` en
  `usuarios[0].servicios.consultas[0].modalidadGrupoServicioTecSal`.
  Al revisar el paquete completo (XML + JSON) aparecieron **4 problemas**, no
  uno: el campo de modalidad en `null`, el `numFactura` sin el prefijo (`737`
  en vez de `MED737`), un `numNota` diligenciado con el `tipoNota` vacío, y la
  atención fechada el **27-07** cuando la factura cubre el período **31-07**
  (esa última la tiene que decidir facturación: o la fecha del servicio está
  mal, o hay que reexpedir la factura).
  Para no repetir el ida y vuelta se creó **`tools/validar_json_rips.py`**:
  revisa estructura del JSON (campos obligatorios, formatos de fecha, tablas
  de referencia) **y** el cruce contra el XML de la factura (número con
  prefijo, NIT, período de facturación, valores). Corre sobre una carpeta o
  sobre todo un mes con `--recursivo` y deja reporte CSV. 29 pruebas
  automáticas. Guía para el auditor en `docs/CONTEXTO_FEV_RIPS_CUV.md`.

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

### Cuentas médicas — CUV de facturas nuevas
11. **Factura MED737:** aplicar las tres correcciones del JSON (modalidad `01`,
    `numFactura` = `MED737`, `numNota` en `null`) y **preguntar a facturación**
    por el conflicto de fechas: la atención es del 27-07 y la factura cubre el
    período del 31-07. Sin resolver eso el Ministerio no entrega el CUV.
12. **Revisar el resto de facturas de agosto** con `validar_json_rips.py
    --recursivo` antes de subirlas: si el facturador viene exportando el
    `numFactura` sin prefijo y la modalidad en `null`, el problema es de todas,
    no solo de la 737. Si se confirma, pedir el ajuste al proveedor del software.

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
6. **Cerrar la MED737:** corregir el JSON, resolver el tema de las fechas con
   facturación y confirmar que el Ministerio entregue el CUV (pendiente #11).
   Luego pasar el revisor a todo agosto (pendiente #12).

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
