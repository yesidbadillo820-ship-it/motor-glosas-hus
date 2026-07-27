# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Todo chat debe leerlo al empezar y actualizarlo al terminar** (así lo ordena
> `CLAUDE.md`). Escrito en lenguaje claro para el auditor de cartera del HUS.

**Última actualización:** 27 de julio de 2026.

---

## 1. RESUMEN DE LO YA HECHO (por fecha)

### Abril 2026 — Se construyó la plataforma "Motor de Glosas HUS"
- **8 de abril:** nace el proyecto (primer commit). Motor de respuestas a glosas
  con inteligencia artificial, códigos de respuesta según normativa (RE9901
  "no acepta", RE9502 extemporánea, etc.) y plazos de la Ley (20 días hábiles).
- **9 al 17 de abril:** correcciones de normativa (Resolución 3047/2008),
  mejores respuestas de la IA, usuarios y claves para los gestores de cartera,
  tarifas del Dispensario Médico.
- **20 al 27 de abril:** la página web del motor quedó de nivel profesional:
  inicio de sesión, panel "Mis Glosas", importación masiva desde Excel,
  exportes, dashboards de desempeño, asistente inteligente y seguridad
  (firma digital de dictámenes). El 26 de abril fue la jornada más grande
  (más de 400 cambios en un día).

### Mayo 2026 — El motor en producción y primer bot de portal
- **4 al 12 de mayo:** importación masiva de glosas mejorada, lectura de PDF
  con respaldo cuando una IA falla, panel de análisis renovado, contratos y
  vigencias reales del HUS cargados.
- **20 de mayo:** pruebas automáticas y banco de plantillas de respuesta del
  HUS cargado de fábrica.
- **21 al 29 de mayo:** primer robot del portal **SIMED** (Dispensario), en ese
  momento para el **cargue de notas crédito** con sus soportes y validación
  del CUV de MinSalud.

### Junio 2026 — Los robots de portales y la operación diaria
- **2 de junio:** arranca el módulo **ADRES/FURIPS** (armar formularios FUR
  desde los RIPS).
- **9 y 10 de junio:** auditoría profunda del motor (7 fallas corregidas, 76
  pruebas nuevas), control de calidad automático de los dictámenes y divisor
  de notas por acta (correo vs. SIMED).
- **11 y 12 de junio:** robot de **COOSALUD** (portal vco.ctamedicas.com) para
  responder glosas masivamente, con verificador de pendientes.
- **16 y 17 de junio:** herramienta de respuestas sugeridas desde el histórico
  y primer piloto de ingreso automático a **Dinámica Gerencial (DGH)**.
- **19 al 26 de junio:** mejoras al robot COOSALUD (residuales, glosas de
  calidad), guías de contexto para los chats, evidencias en Word y PDF,
  pantallazo de evidencia por factura en SIMED, y diagnóstico del Lote V2 de
  notas crédito (12 facturas pendientes: 6 con CUV inválido).
- **26 de junio:** **primer lote de RESPUESTA DE GLOSAS del Dispensario en
  SIMED** (archivo `respuestas_glosa_INICIAL_DSE_26JUN.xlsx`).
- **30 de junio:** día intensivo del robot **DGH**: se logró abrir el editor,
  cargar la factura y abrir la ventana de respuesta; quedó pendiente el llenado
  final (la ventana no se deja leer por dentro y hay que operarla por
  coordenadas de pantalla).

### Julio 2026 — Respuesta masiva de glosas del Dispensario (lo fuerte del mes)
- **1 y 2 de julio:** robot DGH aprendió a llenar la ventana de respuesta por
  coordenadas (modo `--calibrar`); revisión de código con el modelo Fable
  (se corrigió una falla real de búsqueda de ventanas). Lote del 1 de julio
  respondido (`respuestas_glosa_INICIAL_DSE_01JUL.xlsx`).
- **3, 7 y 15 de julio:** rondas de auditoría del motor (27 a 30): se
  corrigieron errores de producción, tarifas, números de cartera y exportes.
- **6 de julio:** lote del Dispensario respondido y **subido a SIMED**
  (65 objeciones en 53 facturas), con pantallazos de evidencia.
- **9 y 10 de julio:** lote grande respondido y **subido a SIMED completo:
  102 facturas, 225 objeciones**, verificado al 100 % (ninguna quedó sin
  responder). La subida tomó ~22 minutos. Se hizo también el **informe para
  gerencia** comparando el antes (manual, días) y el ahora (minutos).
- **14 y 15 de julio:** lote del 14 de julio: **28 facturas, 44 objeciones,
  $46.016.019 defendidos**. Las respuestas se revisaron con verificación
  adversarial (varios agentes de IA buscando fallas) y se corrigieron citas
  normativas (se eliminó la Res. 3047/2008 derogada, se ancló todo en la
  Res. 2284/2023, el contrato 440-DIGSA/DMBUG-2025 y las Resoluciones de
  tarifas HUS 054 y 124 de 2026). El PDF de evidencias debe llamarse
  **GI-33-5182-2026**.
- **17 de julio:** dos frentes:
  - Lote del 17 de julio: **58 facturas, 115 objeciones, $87.605.050**.
    Verificado con 33 agentes; se corrigieron 8 casos donde la respuesta no
    atacaba el punto real de la glosa (dispositivos, día-cama, lista de
    precios, desagregación de procedimientos).
  - En el motor: validador de FURIPS endurecido (22 hallazgos) e **informe de
    baja de cartera en Excel + Word** (Res. 577/2019).
- **21 de julio:** merge del último trabajo del validador ADRES (PR #175).
- **22 de julio:** 
  - Se detectaron **3 facturas de junio sin respuesta** (HUS0000518186,
    HUS0000515107, HUS0000515773). Con las recepciones de objeción se
    generaron sus respuestas: **38 objeciones, $20.054.751**
    (`respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx`). Los totales cuadran
    al peso con cada recepción.
  - Se armó también un **consolidado de 116 facturas / 238 objeciones /
    $94.150.626** con las respuestas dadas (para radicación/soporte).
  - Se creó esta bitácora y la instrucción en `CLAUDE.md`.
  - **Nueva herramienta `tools/organizar_objeciones_dispensario.py`:** convierte
    el PDF de auditoría del Dispensario (AUDITOOL) al Excel de OBJECIONES que se
    importa en Dinámica Gerencial (mismo formato del ejemplo de EMSSANAR), y
    valida que las cuentas cuadren contra el "Total Factura" del PDF.
  - **Nueva herramienta `tools/asistente_conciliacion_dispensario.py`:** para la
    **conciliación de cartera con el Dispensario**. Recorre la carpeta de
    soportes (`Y:\...`), lee RIPS/XML/CUV/PDF (OCR opcional), arma la matriz de
    evidencia por glosa, cruza coherencia, concluye procede/improcede/parcial
    con % de confianza y redacta el oficio de respuesta. Corre en el equipo del
    HUS (donde está montada `Y:\`). Nunca inventa evidencia.
  - **Nueva herramienta `tools/indexar_soportes_dispensario.py`:** indexa la
    carpeta de soportes (`Y:\`) **una sola vez** y crea un índice (JSON); así el
    asistente ya no recorre toda la unidad de red (que se colgaba) — con
    `--indice` abre solo los archivos de la factura. Soporta actualización
    incremental y búsqueda por factura/paciente. Con README y pruebas.
  - **Nueva base `tools/expediente_conciliacion.py` (modelo de datos ÚNICO):**
    arma un EXPEDIENTE por factura con un `id_expediente` que amarra todo —
    factura, paciente, contrato (287/440 + base tarifaria + código interno de
    cartera), radicado, glosas, soportes (del índice), cartera (saldo/edad/
    deterioro) y estado. Es la "fuente de la verdad" que consultarán los demás
    módulos (evidencia, jurídico, argumentación, dashboard) en vez de repetir
    búsquedas. Genera `expedientes.json`. Probado con el lote real (147
    expedientes). Con pruebas.
  - **Nuevo `tools/motor_evidencia_dispensario.py` (Motor de Evidencia, Mod 3):**
    lee los soportes clínicos **página por página** y localiza, por glosa, **en
    qué página** está la prueba, con el fragmento textual. Marca cada evidencia
    como *fuerte* (código CUPS/CUM) o *débil* (palabra) e ignora palabras
    genéricas para no dar falsos positivos. Trabaja sobre el expediente (abre
    solo los archivos de cada factura, no recorre `Y:\`). Nunca inventa. Con
    README y pruebas.
  - **Nuevo `tools/motor_verificacion_dispensario.py` (Verificación, Mod 3.5):**
    con **reglas deterministas** (no IA) convierte el expediente en
    **probatorio**: por cada glosa fija los HECHOS a demostrar (ej. la prestación
    fue *ordenada* y *ejecutada*) y verifica si quedaron **probados**, con nivel
    de confianza y qué documento falta. Corre un **motor de contradicciones**
    (factura no en cartera, paciente que no coincide con el RIPS, CUPS ausente
    en RIPS). Marca cada expediente como *defendible* o no. Así el motor de
    argumentación no inventará: ensamblará la defensa desde hechos ya probados y
    trazables. Con README y pruebas.
  - **Nuevo `tools/motor_decision_dispensario.py` (Motor de Decisión — el
    cerebro):** con reglas de negocio (no IA) califica por glosa la
    **defendibilidad (0–100 %)**, evalúa **riesgos** (probatorio, documental,
    contractual, tarifario, financiero, jurídico) con su razón, aplica la
    **matriz de precedencia** (qué documentos necesita cada tipo de glosa) y
    emite la **acción recomendada** (solicitar levantamiento / soporte / aceptar
    parcial / escalar / conciliar). El jurídico y la argumentación luego solo
    fundamentan y redactan esa decisión. Con README y pruebas. La plataforma va:
    índice → expediente → evidencia → hechos probados → **decisión**.
  - **Nuevo `tools/piloto_conciliacion_dispensario.py` (orquestador del piloto):**
    corre todo el flujo extremo a extremo sobre 5 casos representativos
    (mayor valor, más glosas, contrato 287, contrato 440, y uno conocido) y deja
    **una carpeta por expediente** (expediente/evidencia/hechos/decision.json +
    resumen.txt + log.txt) más un `METRICAS.json` con indicadores y los
    **umbrales de aceptación** (≥95 % facturas con soporte, ≥90 % glosas con
    evidencia, 0 levantamientos sin hecho probado, 100 % trazables). Marca
    `piloto_ok`. Si no cumple, la prioridad es corregir el flujo, no agregar
    funciones. Con README y pruebas.
  - **Casos del piloto (elegidos con datos reales):** 1) HUS0000446262 ($46,7 M,
    287, mixto); 2) HUS0000452150 (62 glosas, 287); 3) HUS0000426013 (COBERTURA
    SOAT $32,5 M, 287); 4) HUS0000455554 ($14,4 M, 440); 5) el que elija el
    auditor (sugerido HUS0000436483).
  - Nota de escala: el servidor de radicación tiene ~2,2 millones de archivos —
    por eso el índice (una sola pasada, filtrando `HUS<n>`) es indispensable;
    conviene apuntar la indexación a la subcarpeta del Dispensario, no a todo `X:\`.
  - Diagnóstico de conciliación del lote que envió el Dispensario (147 facturas
    / 444 glosas): 146/147 cruzan con la cartera (falta HUS0000443525); 372
    glosas venían mal marcadas "SIN CONTRATO" cuando por fecha de atención sí
    tienen contrato (342 → 287, 30 → 440). Base tarifaria: 287 = SOAT −15 %,
    440 = SOAT −20 %. **Pendiente:** confirmar acta de inicio del 287 y el mapeo
    de códigos internos de cartera (U22031/C26001…), y correr el asistente en
    piloto sobre 1–2 facturas reales contra `Y:\`.

### Los números de la operación SIMED (respuesta de glosas Dispensario)
| Lote | Facturas | Objeciones | Valor defendido | Estado |
|---|---|---|---|---|
| 26 de junio | ~30 | ~40 | — | Subido |
| 1 de julio | ~50 | ~70 | — | Subido |
| 6 de julio | 53 | 65 | — | Subido |
| 9 de julio | 102 | 225 | — | Subido y verificado 100 % |
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

## 2. PENDIENTE

1. **Subir a SIMED las 3 facturas de junio** (518186 / 515107 / 515773) con
   `respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx`. **URGENTE: sus fechas
   de vencimiento (6 y 8 de julio) ya pasaron.** Si el portal ya no las deja
   responder, radicar la respuesta por oficio/correo dejando constancia.
2. **Confirmar la subida a SIMED de los lotes del 14 y 17 de julio** (los
   Excel están listos; falta ver el log de la corrida y la pasada de
   verificación que debe dar 0 pendientes).
3. **Generar los PDF de evidencias**:
   - Lote 14 de julio → `GI-33-5182-2026.pdf` (comando ya entregado).
   - Lote 17 de julio → falta el consecutivo GI-33 (pedirlo al auditor).
4. **Soportes por adjuntar del lote 17 de julio** (casos puntuales): notas de
   enfermería del 16-jun (529093), renglón tarifario de dispositivos (coils,
   AIRVO, material de osteosíntesis), descripción quirúrgica del vaciamiento
   de cuello (529291), reporte de lactato/piruvato y aclaración de la biopsia
   vs. estereotaxia (CL0301), justificación de la segunda hemoclasificación.
5. **Robot DGH (Dinámica Gerencial):** correr el modo `--calibrar` en el
   equipo de la oficina y validar el llenado de la ventana de respuesta por
   coordenadas. Es lo único que falta para cargar respuestas también en DGH.
6. **Informe para gerencia:** completar el campo "valor total objetado
   defendido" del lote 9-jul (sale de `reporte_glosa.csv`).
7. **Notas crédito Lote V2:** siguen 6 facturas con CUV inválido (diagnóstico
   del 25 de junio) — decidir si se reprocesan o se radican por otra vía.

---

## 3. PARA MAÑANA (28 de julio de 2026)

**De la conciliación de las 147 facturas:**

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

**De la respuesta de glosas en SIMED (sigue pendiente de antes):**

7. Subir a SIMED el Excel de las **3 facturas de junio** (prioridad 1) y
   guardar el pantallazo de evidencia de cada una.
8. Si los lotes del **14 y 17 de julio** aún no están subidos, subirlos
   (piloto de 1 factura → lote completo → segunda pasada de verificación).
9. Correr la consolidación de evidencias del lote 14 → **GI-33-5182-2026.pdf**
   y conseguir el consecutivo GI-33 del lote 17 para su PDF.
10. Cuando llegue el próximo Excel de glosas del Dispensario, generarlo con el
    motor de plantillas ya verificado (mismo flujo de los lotes anteriores).

---

## Notas de método (para cualquier chat nuevo)

- **Solo se trabaja el Dispensario Médico (DSE Ejército)** en este flujo de
  respuestas; si el Excel trae otras entidades, se omiten.
- Toda respuesta va en **MAYÚSCULAS, un solo párrafo**, empieza con
  *"ESE HUS NO ACEPTA LA GLOSA APLICADA A LA FACTURA…"* y cierra citando la
  mesa de conciliación y los correos de cartera.
- Postura institucional: **NO ACEPTA (RE9901), se defiende el 100 % del valor.**
- Normas ancla: Res. 2284/2023 (Manual Único de Glosas — la 3047/2008 está
  DEROGADA, no citarla), contrato 440-DIGSA/DMBUG-2025 (el Dispensario ES
  parte), Resoluciones de tarifas HUS 054 y 124 de 2026 (y 194/2025 para
  material de osteosíntesis), Ley 1751/2015 art. 17 (autonomía médica),
  Decreto 4747/2007 y Ley 1438/2011 art. 57 (conciliación y trámite).
- Los generadores de respuestas de cada lote viven en el scratchpad de las
  sesiones (`glosa_motor.py` es la fuente única de plantillas); los robots de
  portal están en `tools/` de este repo.
- Guías detalladas por flujo: `docs/CONTEXTO_DISPENSARIO_GLOSAS.md`,
  `docs/CONTEXTO_DISPENSARIO_NOTAS.md`, `docs/CONTEXTO_COOSALUD.md`.
