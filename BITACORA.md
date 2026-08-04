# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana). Escrito en lenguaje claro
> para el auditor de cartera del HUS.

**Última actualización:** 04-08-2026

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

### 03-08 (octava parte) — Cuentas médicas: el CUV que no salía

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
- **(28-07) Lote del 28-jul (97 objeciones): NO subir todavía.** Aplicar las
  correcciones de texto de la verificación (3 grupos no calzan: FA0801,
  SO5801, FA0101; y ajustes obligatorios en FA0201, FA2303 y TA) y completar
  las verificaciones del auditor: nota operatoria del caso AMEU, desglose día
  a día de los 34 días de estancia, horas/órdenes de los 2 rastreos de
  anticuerpos y prórroga 2026 del contrato 440. Detalle en la sección
  "28-07 (noche)".

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

### SIIFA (nuevo, ver `docs/CONTEXTO_SIIFA.md`)
11. **Confirmar la URL del servicio de Auth** (`SIIFA_AUTH_URL`) — no está en
    los manuales que tenemos, el script trae una hipótesis
    (`https://siifa.sispro.gov.co/siifa-seguridad`) sin confirmar. Preguntar a
    mesa de ayuda SIIFA / soporte MinSalud.
12. **Primera corrida real — salió bien, pero hay que repetirla.** El
    03-08 bajó completo (2.597 seguimientos, 2.579 sin respuesta), pero una
    segunda corrida fallida pisó el archivo y se perdió. Ya está corregido
    el bot para que un informe a medias no vuelva a pisar uno bueno; falta
    **volver a bajarlo** y **revisar con el auditor que las columnas sean
    las que necesita** para tipificar las respuestas.
13. **Piloto real** de `tools/responder_glosas_siifa.py --solo-id <id>` con
    una sola glosa antes de cualquier cargue masivo (regla del repo).
14. Definir con el auditor si además de responder glosas (`Respuesta`) hace
    falta automatizar también la subsanación (`ReiteracionRespuesta`) desde
    el arranque, o si eso se deja para cuando llegue el primer lote real.

### Cuentas médicas — CUV de facturas nuevas (nuevo, 03-08)
15. **Factura MED737:** aplicar las tres correcciones del JSON (modalidad `01`,
    `numFactura` = `MED737`, `numNota` en `null`) y **preguntar a facturación**
    por el conflicto de fechas: la atención es del 27-07 y la factura cubre el
    período del 31-07. Sin resolver eso el Ministerio no entrega el CUV.
16. **Revisar el resto de facturas de agosto** con `validar_json_rips.py
    --recursivo` antes de subirlas. Si el facturador viene exportando el
    `numFactura` sin prefijo y la modalidad en `null`, el problema es de todas,
    no solo de la 737: ahí lo que toca es pedirle el ajuste al proveedor del
    software, no corregir a mano cada archivo.

## 4) PARA MAÑANA

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
1. **Dispensario prioridad 1:** subir a SIMED el Excel de las 3 facturas de
   junio y guardar el pantallazo de evidencia de cada una. Si los lotes del
   14 y 17 aún no están subidos, subirlos (piloto de 1 factura → lote →
   verificación) y generar sus PDF de evidencias.
   **Lote del 28-jul: NO subir hasta corregir los textos** señalados por la
   verificación (3 grupos no calzan) y resolver las verificaciones del
   auditor (nota operatoria AMEU, desglose de los 34 días, horas de los 2
   rastreos, prórroga 2026 del contrato 440).
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
