# ENTREGA TÉCNICA — Módulo "Respuesta de Glosas Dispensario (SIMED)"

**Documento oficial de entrega al equipo principal.**
Reconstruye TODO el trabajo realizado en la conversación/rama de desarrollo
"GLOSAS DISPENSARIO — SIMED (respuestas por lote)" del proyecto Motor de
Glosas HUS, incluidos hallazgos, decisiones, descartes y pendientes.

- **Fecha de entrega:** 27 de julio de 2026.
- **Autor de la sesión:** auditor de cartera HUS (Yesid Pérez) + Claude Code.
- **Repositorio:** `yesidbadillo820-ship-it/motor-glosas-hus` (rama principal `motor-glosas`).
- **PRs producidos por esta conversación:** #134 (bot DGH, fusionado), #179 (bitácora + fix de tests, fusionado).
- **Artefacto publicado:** informe para gerencia — https://claude.ai/code/artifact/5356b11e-6abb-4aea-b9d1-b62044948290

---

## 1. Objetivo del desarrollo

**Problema.** La Dirección de Sanidad del Ejército – Dispensario Médico de
Bucaramanga (DMBUG/MEBUG, entidad U220311, NIT tercero 901541137) glosa
masivamente facturas de la ESE Hospital Universitario de Santander (HUS,
NIT 900006037-4). Cada glosa debe responderse **objeción por objeción** en el
portal **SIMED** (auditool25.tool.com.co, página "Respuesta Glosa Rad. WEB",
`glosasfacturaww.aspx`) dentro de términos legales. Hacerlo a mano implicaba:
redactar cada respuesta (6–8 min/objeción), buscar la factura en el portal,
digitar, fijar fecha, confirmar, capturar evidencia — con riesgo de omisiones,
calidad dispareja y vencimiento de términos.

**Qué resuelve este módulo.** Un flujo de punta a punta que:
1. Lee el **export de DGH** (Excel de glosas con hoja de detalle `ListadoConceptos.*`).
2. **Clasifica cada objeción por su observación real** (no solo por el código).
3. **Redacta la respuesta técnico-normativa** por objeción con un banco de
   plantillas endurecido por verificación adversarial (postura institucional:
   **NO ACEPTA — RE9901 — defensa del 100 % del valor**).
4. Produce el **Excel de carga** en el formato exacto que consume el robot
   `tools/responder_glosas_simed.py`.
5. **Sube el lote al portal** con el robot (salta respondidas, reintenta
   transitorios, evidencia PNG por factura, reporte CSV, reanudable).
6. **Consolida las evidencias** en un PDF `GI-33-XXXX-2026` para el radicado.

**Necesidad cubierta.** Pasar de jornadas a minutos manteniendo defensa
jurídica sólida: en esta conversación se respondieron y/o dejaron listos
**7 lotes** del Dispensario (26-jun, 01-jul, 06-jul, 09-jul, 14-jul, 17-jul y
"pendientes de junio"), más un consolidado de soporte. Cifras verificadas:
lote 09-jul = 102 facturas / 225 objeciones subidas y verificadas al 100 %
(22,5 min la corrida, 6,1 min la pasada de verificación); 14-jul = 28/44/
$46.016.019; 17-jul = 58/115/$87.605.050; pendientes junio = 3/38/$20.054.751.

Secundariamente, la conversación también avanzó el **bot de Dinámica
Gerencial (DGH)** (PR #134) y produjo **infraestructura de memoria común**
(`BITACORA.md` + `CLAUDE.md`, PR #179) y un **informe para gerencia**.

---

## 2. Arquitectura

### 2.1 Estructura (qué vive dónde)

```
motor-glosas-hus/                      # repo (clon Windows en C:\temp-notas)
├── CLAUDE.md                          # instrucción: leer/actualizar BITACORA.md (PR #179; luego fusionado con otro chat)
├── BITACORA.md                        # memoria común de todos los chats (PR #179; luego fusionado)
├── app/                               # Motor de Glosas (FastAPI) — NO tocado aquí salvo lectura
│   └── services/
│       ├── catalogo_glosas.py         # catálogo autoritativo de códigos (AU/SO/CL/TA/FA/CO)
│       ├── normativa.py               # normograma (Res. 2284/2023 = Anexo Técnico No. 3; Res. HUS 054 y 124/2026…)
│       └── rag_service.py             # (fix menor previo: set con duplicados)
├── data/
│   └── plantillas_hus_base.json       # 50 plantillas vetadas HUS (TA-G01..CL-G10) — fuente doctrinal
├── scripts/
│   └── banco_objeciones_glosas_hus.py # citado por la verificación (texto art. 87 D.2423/1996)
├── docs/
│   ├── CONTEXTO_DISPENSARIO_GLOSAS.md # guía operativa de ESTE flujo
│   ├── CONTEXTO_DISPENSARIO_NOTAS.md  # (otro flujo: notas crédito)
│   └── CONTEXTO_COOSALUD.md           # (otro flujo/portal)
├── tests/test_api/
│   ├── test_import_history.py         # fix bomba de tiempo (30-jun)
│   ├── test_por_dia_semana.py         # fix bomba de tiempo (22-jul, PR #179)
│   └── test_heatmap_actividad.py      # fix bomba de tiempo (22-jul, PR #179)
└── tools/
    ├── responder_glosas_simed.py      # ROBOT de carga SIMED (Playwright) — pieza central de ejecución
    ├── responder_glosas_dgh.py        # ROBOT DGH (pywinauto/UIA + coordenadas) — PR #134
    ├── evidencias_a_pdf.py            # consolidador PNG→PDF (GI-33)
    ├── dump_dg.py, login_dg.py        # apoyo DGH
    └── (resto de tools de otros flujos)
```

```
scratchpad de la sesión (fuera del repo; generadores y verificación)
├── glosa_motor.py                     # ★ FUENTE ÚNICA de clasificador+plantillas (extraído de gen_14jul)
├── gen_respuestas.py                  # generador lote 01-jul (histórico)
├── gen_06jul.py                       # generador lote 06-jul (histórico)
├── gen_09jul.py                       # generador lote 09-jul (histórico; clasificador v1)
├── gen_14jul.py                       # generador 14-jul (aquí evolucionaron clasificador y plantillas)
├── gen_lote.py                        # generador GENÉRICO de un lote (usa glosa_motor) — el vigente
├── gen_consolidado.py                 # generador multi-fuente por lista de facturas (usa glosa_motor)
├── gen_junio_pendientes.py            # generador con datos embebidos de 3 recepciones (usa glosa_motor)
├── wf_verify_14jul_v2.js              # workflow verificación adversarial ronda 1 (datos embebidos)
├── wf_reverify_14jul.js               # ronda 2 (regresión)
├── wf_confirm_14jul.js                # ronda 3 (go/no-go)
├── wf_verify_17jul.js                 # verificación lote 17 (clasif por código + plantillas)
├── dump_14jul.json / dump_17jul.json  # volcado por objeción (factura,num,code,cups,serv,valor,obs,tipo,detalle)
├── facturas_consolidado.txt           # lista de 116 facturas pedida por el auditor
├── informe_gerencia_glosas.html       # fuente del artefacto de gerencia
├── venv/                              # Python 3.11 con openpyxl 3.1.5, pytest, fastapi… (+ruff instalado luego)
└── respuestas_glosa_*.xlsx            # productos por lote (ver §10)
```

### 2.2 Componentes y responsabilidades

| Componente | Rol |
|---|---|
| `glosa_motor.py` | Clasificador de observaciones + banco de argumentos + redactor. Puro, sin I/O. |
| `gen_lote.py` | Export DGH → Excel de respuestas de UN lote (filtra Dispensario, numera 1..N). |
| `gen_consolidado.py` | N exports + lista de facturas → un Excel (primera fuente gana; sin duplicar). |
| `gen_junio_pendientes.py` | Datos transcritos de recepciones (sin export) → Excel; valida totales al peso. |
| `responder_glosas_simed.py` | Sube el Excel al portal: busca factura, itera objeciones, llena modal, confirma, finaliza, evidencia. |
| `evidencias_a_pdf.py` | Une los PNG de evidencia en un PDF multipágina (orden por nombre). |
| `responder_glosas_dgh.py` | Homólogo para el aplicativo de escritorio DGH (ver §9.3). |
| Workflows `wf_*.js` | Verificación adversarial multi-agente de clasificación y solidez jurídica. |

### 2.3 Dependencias y librerías

- **Python 3.11** (venv del scratchpad). Paquetes usados aquí: `openpyxl 3.1.5`
  (lectura/escritura Excel), `Pillow` (PDF de evidencias, en el equipo del
  auditor), `pytest` (suite del repo), `ruff` (instalado en el venv el 22-jul
  para replicar los gates del CI). El robot SIMED usa **Playwright** y el DGH
  **pywinauto 0.6.9** (backend UIA) — ambos ya estaban en el repo.
- **Node** (solo `node --check` para validar sintaxis de los workflows).
- **APIs externas:** ninguna nueva. GitHub vía MCP (PRs, checks, logs).

### 2.4 Modelos de datos (en memoria)

- **Fila de detalle (export DGH, hoja `I`/`i`):** columnas usadas →
  `FacturaCartera.PlanBeneficio.Contrato.Entidad.NombreEntidad`,
  `FacturaCartera.Factura`, `Oid`, `Consecutivo`,
  `ListadoConceptos.ConceptoObjecion.Codigo`,
  `ListadoConceptos.ServicioProductoFactura.Codigo`,
  `ListadoConceptos.ServicioProductoFactura.Descripcion`,
  `ListadoConceptos.ValorObjecion` (fallback `ValorObjecion`),
  `ListadoConceptos.Observaciones` (limpia `_x000D_`).
- **Registro de respuesta (Excel de carga):**
  `Factura | # Objeción | Cód. | Servicio | Valor Objetado | Valor Aceptado | Cod Respuesta | Detalle Respuesta`
  → hoja **"Respuestas Glosa"**, encabezado azul `1F4E78` con letra blanca,
  anchos `[16,10,9,44,14,14,13,130]`, detalle con ajuste de texto, panel
  congelado en `A2`. `Valor Aceptado = 0` y `Cod Respuesta = RE9901` SIEMPRE.
- **Dump JSON por objeción:** `{factura, num, code, cups, serv, valor, obs, tipo, detalle}` —
  insumo de los workflows de verificación y de los chequeos deterministas.

---

## 3. Funciones implementadas

### 3.1 `glosa_motor.py` (fuente única)

| Función/objeto | Qué hace / cómo / por qué |
|---|---|
| `norm(s)` | Colapsa espacios y elimina `_x000D_` (artefacto de Excel/DGH). Existe porque las observaciones llegan con saltos codificados. |
| `money(v)` | Formatea `$1.234.567` (punto de miles colombiano) para citar el valor en la respuesta. |
| `disp(e)` | `True` si la entidad contiene DISPENSARIO/EJERCITO/MEBUG. **Regla de negocio: solo se trabaja Dispensario; otras entidades se OMITEN** (instrucción expresa del auditor). |
| `CIERRE` | Párrafo final común: solicita levantamiento total y pago íntegro; disposición a mesa de conciliación (art. 20 D.4747/2007; L.1438/2011 art. 57); correos cartera@hus.gov.co y glosasydevoluciones@hus.gov.co. |
| `clasificar(code, obs)` | Devuelve el TIPO de argumento. **Orden de 14 reglas** (el orden ES semántica): 1) `CL0101/FA0101` → estancia; **sub-regla causación** si la obs es de CONTEO de días (`SOLO SE RECONOCE UN DIA`, `NO ES POSIBLE ACEPTAR COBRO DE ESTANCIA EL DIA`, ingreso+egreso, `INGRESA`+`MADRUG`, `SOLO ES ATENDIDO EL DIA`, `ADMISIONA`+`NO SE ACEPTA COBRO DE ESTANCIA`) → `ESTANCIA_CAUSACION`. 2) Materiales incluidos en derechos de sala/estancia (todas las variantes vistas: `HACE PARTE DE LOS DERECHOS DE SALA`, `HACEPARTE…`, `INCLUIDO EN D. SALA`, `MATERIAL DE SUTURA Y CURACION`…) → `MATERIALES`. 3) Estancia por palabras clave (UCI/nivel/no pertinente, sin MVC) → `CALIDAD_ESTANCIA`. 4) `TA0601` → `TARIFA_DISPOSITIVO`. 5) Pertinencia (remitido con diagnóstico, solicitud de estudios, yeso, `REMITIDA DE PRIMER NIVEL`, no-pertinente no quirúrgico) → `PERTINENCIA`. 6) Inherente/incluido/inmerso/cubierto en honorarios → `PROC_INDEPENDIENTE` (o `TARIFA_SALDO` si además hay agotamiento+diferencia). 7) Agotamiento de saldo/cupo → `TARIFA_SALDO`. 8) Medicamento sin justificar uso/cantidad → `INSUMO_MEDICAMENTO`. 9) Mala clasificación CUPS → `MISCODIFICACION`. 9-bis) `INTERMEDIACION`/`TERMOMETRO DE PRECIOS`/`PRECIO PROMEDIO` → `TARIFA_DISPOSITIVO`. 9-ter) `HASTA TANTO ADJUNTEN (LISTA DE PRECIOS)` → `LISTA_PRECIOS`. 9-quater) `NO FACTURABLE`+`LIQUIDACION DE PROCEDIMIENTOS` → `PROC_INDEPENDIENTE`. 9-quinquies) `DESCRIPCION QUIRURGICA CORRESPONDE A` → `MISCODIFICACION`. 10) factura de compra/venta/casa ortopédica → `INSUMO_FACTURA`. 11) lista/LISTADO de precios (salvo TA con MVC) → `LISTA_PRECIOS`. 12) sin soporte/resultado → `SOPORTE`. 13) MVC/SOAT/diferencia/aval → `TARIFA`. 14) residuales por prefijo (`AU`→AUTORIZACION, `CL0601`→MATERIALES, `CL*`→PERTINENCIA, default `FACTURACION`). |
| `arg(t)` | Devuelve el argumento jurídico del tipo. 16 plantillas (ver §8.2 los textos-tesis). |
| `redactar(factura, code, cups, serv, valor, obs)` | Compone: `ESE HUS NO ACEPTA LA GLOSA APLICADA A LA FACTURA {factura} POR LA DIRECCIÓN DE SANIDAD DEL EJÉRCITO – DISPENSARIO MÉDICO DE BUCARAMANGA. FRENTE AL CARGO POR CÓDIGO {cups} {serv} ({money}), OBJETADO BAJO EL CONCEPTO {code}: {arg} {CIERRE}` → colapsa espacios → **`.upper()`** (mayúsculas, párrafo único). Devuelve `(texto, tipo)`. |

### 3.2 Generadores

| Script | Entrada → Salida | Detalles |
|---|---|---|
| `gen_lote.py` | `fuente.xlsx salida.xlsx [dump.json]` | Detecta la hoja de detalle **por encabezado** (`ListadoConceptos.ConceptoObjecion.Codigo`), no por nombre (los exports alternan `I`/`i`). Filtra Dispensario. Numera `# Objeción` 1..N **en el orden del export** (= orden de la grilla del portal). Chequeos deterministas al final: mayúsculas, sin saltos de línea, apertura exacta, código presente en el texto, cierre presente; imprime distribución por tipo y largos (rango observado 1.095–2.087 caracteres; tope del portal 4.000). |
| `gen_consolidado.py` | `salida.xlsx facturas.txt fuente1.xlsx …` | Normaliza factura (`re.sub(r"\D","")` + strip ceros → `HUS0000522249`≡`522249`). "Primera fuente gana" para no duplicar. Reporta facturas sin fuente. |
| `gen_junio_pendientes.py` | (datos embebidos) → `respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx` | 38 objeciones transcritas de las Recepciones de Objeción Nº 179722/179779/179781. **Valida con `assert` que la suma por factura cuadre al peso con el total de cada recepción** (control de transcripción más fuerte que cualquier revisión). |

### 3.3 Fixes a código del repo hechos en esta conversación

- `tools/responder_glosas_simed.py`: anotación/docstring de
  `leer_excel_respuestas` corregida a `-> dict[str, list[dict]]`; detección de
  éxito de finalización más robusta; `--evidencias-dir` (commits del 24 y
  30-jun); formato ruff en 13 tools.
- `tools/responder_glosas_dgh.py`: ver §9.3 (todo el bot).
- `tools/evidencias_a_pdf.py`: creado el 26-jun (ver §9.2).
- `tests/test_api/test_import_history.py` (30-jun) y
  `test_por_dia_semana.py` + `test_heatmap_actividad.py` (22-jul): fixes de
  "bomba de tiempo" (ver §13.3).
- `tools/login_dg.py`, `tools/motor_glosas_hus.py`,
  `tools/responder_glosas_coosalud.py`, `app/services/rag_service.py`:
  limpieza de errores ruff F preexistentes (30-jun).

---

## 4. Flujo completo (paso a paso)

1. **Llega el export** de DGH (p. ej. `GLOSAS_17_JULIO.xlsx`) con hojas
   `INICIAL` (control) e `I`/`i` (detalle por concepto).
2. **Análisis del lote** (siempre antes de generar): entidades presentes
   (solo Dispensario se procesa), nº de facturas y filas, códigos de glosa y
   sus frecuencias, estructura `Oid` (¿multi-concepto?), valor total, y
   **lectura de las observaciones por código** para detectar patrones nuevos.
3. **Clasificación**: `clasificar()` por observación (el código solo decide
   cuando la observación no discrimina). Si aparece un patrón nuevo, se
   agrega la regla y se re-verifica la distribución (objetivo: 0 respuestas
   genéricas `FACTURACION`).
4. **Generación**: `gen_lote.py` produce el Excel + dump JSON; chequeos
   deterministas en verde.
5. **Verificación adversarial** (lotes con plantillas/patrones nuevos):
   workflow multi-agente (ver §8) → correcciones de texto/clasificación →
   regenerar → repetir hasta veredictos aceptable/sólido.
6. **Entrega al auditor**: Excel + comando PowerShell listo (Claude Code no
   tiene acceso a `D:\`, al share ni a los portales — regla del repo):
   ```powershell
   $base  = "D:\USUARIO CARTERA\Documents\DISPENSARIO MEDICO 17-07-2026"
   $excel = "D:\USUARIO CARTERA\Downloads\respuestas_glosa_DISPENSARIO_17JUL.xlsx"
   cd C:\temp-notas
   # Piloto de 1 factura (regla del repo antes de todo cargue masivo):
   py tools\responder_glosas_simed.py --excel $excel --solo HUS0000527406 --sin-soportes --evidencias-dir "$base\EVIDENCIAS"
   # Lote completo:
   py tools\responder_glosas_simed.py --excel $excel --todas --sin-soportes --evidencias-dir "$base\EVIDENCIAS"
   ```
7. **El robot, por factura**: navega a "Respuesta Glosa Ips Web" → filtra por
   `factura_corta` → abre la factura → por cada objeción del Excel: localiza
   la fila en la grilla por su **# de objeción** (span `FCTOBJSEC`,
   escaneando hasta 12 páginas porque la grilla puede venir ordenada por otra
   columna) → si ya está **Contestada** la omite (salvo `--rehacer`) → abre el
   modal (estrategias `btn_respuesta_id` / `img_inicio`, en iframe) → llena
   `VALOR ACEPTADO=0` y el detalle (recortado a 4.000) → la **Fecha
   Respuesta** se setea sola → Confirmar → espera cierre del modal (25 s; si
   no cierra: dump de botones + screenshot + reintento único; el segundo
   intento recupera casi todos) → al terminar las objeciones: Confirmar del
   formulario principal → **Enviar/Finalizar** → guarda **evidencia PNG**
   (`HUS<numero>_<fecha>_<hora>.png` en `--evidencias-dir`).
8. **Estados por factura** en `reporte_glosa.csv`: `OK`, `NO_PENDIENTE`
   (la factura ya no está en pendientes del portal), `SIN_PENDIENTES` (todas
   las objeciones ya estaban contestadas), `PILOTO_PARCIAL` (con `--max-obj`,
   no finaliza), `ERROR`.
9. **Segunda pasada obligatoria**: re-ejecutar `--todas`; barre cualquier
   objeción que quedó pendiente por el transitorio "modal no cerró". Éxito =
   `OK: 0` y todo `NO_PENDIENTE`/`SIN_PENDIENTES`.
10. **Evidencias → PDF**: `py tools\evidencias_a_pdf.py --carpeta
    "$base\EVIDENCIAS" --salida "$base\GI-33-5182-2026.pdf"` (orden por
    nombre = orden por factura).
11. **Resiliencia probada**: en el lote 09-jul hubo corte de energía en la
    factura 66/102; al relanzar `--todas` el robot saltó lo hecho y terminó
    (`NO_PENDIENTE: 64, OK: 37, SIN_PENDIENTES: 1`; verificación posterior:
    `NO_PENDIENTE: 101, SIN_PENDIENTES: 1`, 6,1 min).

---

## 5. Base de datos

Este módulo **no crea tablas ni migraciones**. Interactúa con datos así:

- **Entrada:** Excel export de DGH (esquema de columnas en §2.4).
- **Salida:** Excel "Respuestas Glosa" (esquema §2.4) + `reporte_glosa.csv`
  (`factura, objeciones, estado, detalle`) + PNG de evidencia por factura +
  PDF consolidado.
- **Del Motor (app) se LEYÓ** (sin modificar): `GlosaRecord` y
  `UsuarioRecord` solo en los tests corregidos (campos usados:
  `eps, paciente, codigo_glosa, valor_objetado, valor_recuperado, etapa,
  estado, creado_en`); los endpoints de estadísticas filtran por **ventana
  default de 90 días** sobre `creado_en` — dato clave del fix de tests.
- **Identificadores del dominio:** `Oid` (trámite de objeción), `Consecutivo`
  (radicado DGH), `FCTOBJSEC` (# de objeción en la grilla SIMED),
  `FCTOBJEST` (estado Contestado), `vGRIDBADGE` (badge verde).

---

## 6. Backend (robot SIMED — contrato operativo)

No hay endpoints HTTP nuevos; el "backend" de este módulo es el robot.

- **CLI:** `--excel` (obligatorio), `--solo <factura>` | `--todas`,
  `--con-cabeza`, `--sin-soportes`, `--soportes-glosa`, `--indice`,
  `--evidencias-dir`, `--rehacer`, `--reporte` (default
  `reporte_glosa.csv`), `--max-obj N` (piloto parcial: no finaliza la
  factura a propósito para no disparar "glosas pendientes").
- **Lectura del Excel** (`leer_excel_respuestas`): encabezados tolerantes —
  factura: por nombre de columna "Factura"; nº: `{# OBJECION, NUM OBJECION,
  OBJECION, NUMERO OBJECION, ITEM}`; aceptado: `{VALOR ACEPTADO, ACEPTADO,
  VI ACEPTADO}`; detalle: `{DETALLE RESPUESTA, RESPUESTA, OBSERVACIONES,
  DETALLE}`. Devuelve `{factura_corta: [{factura, factura_corta, num,
  aceptado, detalle}]}` ordenado por `num`.
- **Validaciones/errores:** `ObjecionNoEnGrilla` (el Excel trae más
  objeciones que el portal → no reintenta), `FacturaNoPendiente` (→ estado
  `NO_PENDIENTE`), `RuntimeError` "El modal no cerró tras Confirmar en 25s —
  la objeción NO se guardó" (+ dump `debug_screenshots/…_botones_modal_no_
  cierra.txt` y screenshot), `_sesion_muerta` → reinicio de sesión.
- **Permisos/credenciales:** variables de entorno (`SIMED_USER=900006037`,
  clave por env var). **Regla del repo: nunca commitear usuarios/contraseñas.**
- **Hallazgo estructural CLAVE (14-jul):** el portal numera las objeciones
  por **línea de concepto** (cada fila `ListadoConceptos` es una fila 1..N de
  la grilla), NO por trámite `Oid`. Se sospechó lo contrario al ver 4 facturas
  con 1 `Oid` y varias filas; se descartó la alarma con evidencia: el lote
  09-jul tenía `HUS0000523846` con 30 filas y 1 `Oid`, y el robot respondió
  #1..#30 en el portal. **Conclusión vinculante: numerar 1..N por fila del
  export, en su orden.**

---

## 7. Frontend

Este módulo no tocó el frontend de la app. Las "pantallas" del flujo son las
del portal SIMED que el robot opera (grilla "Respuesta Glosa Ips", modal
"Respuesta Glosa Ips Web" en iframe `gxp0_ifrm`, botón verde
Enviar/Finalizar) y dos entregables visuales:

1. **Informe para gerencia** (artefacto HTML publicado, tema claro/oscuro,
   paleta teal institucional `#0C6E6B`): KPIs (102 facturas, 225 objeciones,
   100 % cobertura, 97 % reducción de tiempo), comparativo antes/ahora,
   barras a escala real (≈26 h manual vs ≈22 min robot; ~7 min → ~6 s por
   objeción, ≈70×), tabla punto por punto, herramientas construidas, lotes de
   julio, beneficios, nota metodológica y un campo editable "valor total
   objetado defendido" (pendiente de llenar desde `reporte_glosa.csv`).
   Fuente: `informe_gerencia_glosas.html` (scratchpad).
2. **Los Excel de respuestas** con formato corporativo (ver §2.4).

---

## 8. IA

### 8.1 Generación de respuestas
**No usa LLM en runtime**: la redacción es **determinista** (plantillas +
clasificador de reglas). Decisión deliberada: reproducibilidad, cero
alucinación normativa y validación mecánica (chequeos de formato, totales).

### 8.2 Banco de argumentos (tesis por tipo, estado final endurecido)
- **TARIFA** (MVC vs SOAT): el valor ES la tarifa institucional adoptada por
  acto administrativo vigente a la fecha de cada prestación (Res. HUS 054 y
  124 de 2026), reconocida por la **Cláusula Segunda del Contrato
  Interadministrativo 440-DIGSA/DMBUG-2025**; el "no anexan acuerdo de
  tarifas" se rebate porque **el acuerdo es el propio contrato**; la entidad
  glosadora **ES parte** → alegar "IPS sin contrato" contraría sus propios
  actos (*venire contra factum proprium*); se aporta el listado tarifario.
- **TARIFA_DISPOSITIVO** (TA0601, intermediación, termómetro de precios,
  precio promedio): tarifa institucional de dispositivos/insumos (Res. 054 y
  124/2026 y **Res. HUS 194/2025 para material de osteosíntesis — MAOS**);
  la **factura de compra del proveedor NO es exigible** ni para acreditar la
  prestación ni para fijar el valor; el precio no se rige por costo de
  adquisición; soporte de uso: descripción quirúrgica + hoja de gasto (o, en
  no quirúrgicos, orden médica + registros de administración).
- **TARIFA_SALDO**: el agotamiento de saldo/cupo es carga presupuestal del
  contratante y no es causal admisible del Manual (Res. 2284/2023); hubo
  autorización previa (buena fe, art. 1603 C.C. y 871 C.Co.; actos propios);
  si además pretenden subsumir el procedimiento en otro, se afirma su
  autonomía y liquidación separada. Conciliación arts. 20/23 D.4747/2007.
- **PROC_INDEPENDIENTE**: desagregación — cada línea tiene código y soporte
  propios; el pagador no probó una desagregación distinta ni la inclusión
  expresa; autonomía médica (L.1751/2015 art. 17) frente a reproches de
  pertinencia/técnica; el pagador es parte del contrato 440.
- **CALIDAD_ESTANCIA**: necesidad clínica día a día en notas de evolución;
  el nivel se determina por criterios clínicos (monitoreo/soporte/vigilancia)
  con independencia de la hora del registro formal de traslado; demoras de
  autorización del pagador no imputables al HUS; petitum: reconocimiento del
  NIVEL facturado y del valor objetado.
- **ESTANCIA_CAUSACION** (nueva, 17-jul): el día-cama se causa con la
  **ocupación efectiva y el registro de ingreso**, no por pernoctación
  completa ni corte de medianoche; se aportan notas de ingreso/enfermería.
- **INSUMO_MEDICAMENTO** (AU0701 = "número de unidades de forma farmacéutica
  difiere de lo autorizado"): dosificación según técnica del estudio, peso y
  ficha técnica; emitida la autorización del apoyo diagnóstico, no procede
  objetar las unidades empleadas (actos propios); se aportan orden y registro
  de administración.
- **INSUMO_FACTURA** (SO4201 pinza 30 % "en espera de conciliación"): el
  soporte de uso es la descripción quirúrgica + hoja de gasto; el valor por
  tarifa institucional; dispositivo de un solo uso no reprocesado (reúso
  inaplicable); la retención parcial "en espera de conciliación" carece de
  causal presente y taxativa — la conciliación no autoriza retener el pago.
- **MATERIALES**: el insumo no figura en los listados de inclusión de
  derechos de sala/sutura/estancia que invoca el pagador (arts. 55 §5 y 40
  §2 citados por él); la tarifa institucional los codifica por separado.
- **SOPORTE**: prestación real soportada en HC/sistemas del HUS (integralidad
  Res. 1995/1999); se ANEXA el soporte específico según el ítem (reporte con
  fecha y responsable / descripción quirúrgica + hoja de gasto / hoja de
  administración con hora y responsable).
- **LISTA_PRECIOS**: el tarifario institucional es documento contractual
  preexistente en poder de ambas partes y en todo caso se aporta de nuevo,
  con la fila del código glosado.
- **MISCODIFICACION** (AU0802, "descripción quirúrgica corresponde a otro"):
  la causal "mala clasificación de CUPS" no es causal taxativa del Manual
  (que ni adopta la CUPS) → improcedente de origen; prevalencia de lo
  sustancial; el servicio realmente practicado se reconoce íntegro a tarifa
  institucional; se aportan orden y resultado.
- **PERTINENCIA**: indicación del tratante documentada en HC; autonomía
  médica; la remisión a la IPS no excluye el pago.
- **AUTORIZACION**, **RE_ENCUADRE**, **FACTURACION** (residuales).
- **Apertura y cierre** fijos (§3.1). Nota: el 06-jul el auditor pidió la
  apertura "ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE…"; los dos lotes
  aceptados y subidos (06 y 09-jul) usaron "…LA GLOSA APLICADA A LA
  FACTURA…", así que **esa** quedó como estándar probado (decisión
  documentada; el banco del repo `plantillas_hus_base.json` usa la otra
  variante en sus 50 plantillas genéricas).

### 8.3 Verificación adversarial (aquí SÍ hubo LLM, en revisión)
- **Mecánica:** tool `Workflow` con subagentes en paralelo; salidas con
  JSON Schema estricto (`veredicto: correcto|dudoso|incorrecto`;
  `severidad: alta|media|baja`; `clase: norma-incorrecta|sobreafirmacion|
  no-rebate|impreciso|regresion|otro`); fases Clasificación (un agente por
  código, effort medium) → Argumento (un agente por plantilla, effort high,
  rol "abogado adversarial: refutá") → Síntesis (go/no-go + correcciones +
  `pendientes_usuario`).
- **Rondas del lote 14-jul:** R1 = 20 agentes / 359.975 tokens; R2 = 10 /
  253.334; R3 = 10 / 286.216. **Lote 17-jul:** 33 agentes / 668.838 tokens.
- **Lección de plumbing:** pasar los datos por `args` del Workflow falló
  (`args.rows` llegó `undefined` → "undefined is not an object"); patrón
  adoptado: **embeber los datos en el script** (`const A = {...}`) y validar
  con `node --check` antes de lanzar (aun así un `;` dentro de un `.map()`
  rompió el parser del runtime una vez; segundo intento OK).
- **Hallazgos objetivos que cambiaron el texto** (todos verificados contra
  archivos del repo): (a) **Res. 3047/2008 está DEROGADA** por la Res.
  2284/2023 — se citaba en 5 plantillas; (b) la CUPS **no** la adopta la Res.
  2284/2023; (c) citar **D.780/2016 art. 2.6.1.4.2.4** a favor del HUS es un
  **autogol** (es la base del SOAT-UVB del pagador); (d) citar **D.2423/1996
  art. 87** para ítems que SÍ están definidos en SOAT es otro autogol (su
  supuesto es "procedimiento no definido y sin tarifa asignada" —
  `scripts/banco_objeciones_glosas_hus.py:48-52`) → se introdujo en R2 y se
  RETIRÓ en R3; (e) el número de Anexo Técnico se citó mal dos veces (No. 2 y
  No. 1); el repo (`normativa.py:135`) dice que el Manual es el **Anexo
  Técnico No. 3** → decisión: citar la resolución sin numerar el anexo;
  (f) "en subsidio procede la re-liquidación" concedía rebaja → eliminado;
  (g) INSUMO_FACTURA aportaba la factura de compra (revela margen) →
  invertido; (h) frase duplicada por un edit fallido en MATERIALES
  ("…su cobro es procedente por cuanto no se encuentra su cobro es
  procedente…") → detectada por la ronda 17-jul y reparada; (i) meses
  hardcodeados ("autorizado en abril y ejecutado en mayo") → parametrizado;
  (j) "carece de causal taxativa" era insostenible donde la causal SÍ es
  taxativa → reformulado.
- **Reclasificaciones puntuales aceptadas:** 14-jul: `520337 #2`
  (vaciamiento de cuello) TARIFA_SALDO→PROC_INDEPENDIENTE. 17-jul:
  `529741 #1` TARIFA→PROC_INDEPENDIENTE (derechos de sala de la 2ª
  salpingectomía = liquidación de múltiples); `529741 #2`
  INSUMO_FACTURA→TARIFA_DISPOSITIVO (no discutir el tope de intermediación
  del 12 %); `533773 #5` TARIFA→TARIFA_DISPOSITIVO (paracetamol vs
  "termómetro de precios"); `528744 #11` TARIFA→LISTA_PRECIOS (retención del
  50 % "hasta tanto adjunten lista"); `529093 #1` y `522342` →
  ESTANCIA_CAUSACION; `529291 #3` doble tesis saldo+autonomía.
- **Chequeos deterministas** que quedaron como batería estándar tras cada
  regeneración: ausencia de `3047`, `2423`, `ART. 87` (regex que no confunda
  con el art. **871** C.Co.), `RE-LIQUIDACI`, `RECHAZO TOTAL`, `ANEXO
  TÉCNICO No. 2`, `CARECE DE CAUSAL TAXATIVA`; presencia de Cláusula
  Segunda + Res. 054/124, actos propios, L.1751 art. 17 donde corresponde;
  formato íntegro; totales y conteos.

### 8.4 Otros usos de IA en la conversación
- Revisión de código del bot DGH con el modelo **Fable** (halló el bug real
  de `ElementAmbiguousError`, §9.3).
- El informe de gerencia y este documento son redacción asistida.
- El Motor de la app usa IA (Groq/Anthropic/Gemini) pero **no fue tocado** aquí.

---

## 9. Automatizaciones

### 9.1 Robot SIMED (`tools/responder_glosas_simed.py`)
Qué hace: §4 y §6. Cuándo: bajo demanda del auditor por lote. Cómo: comando
PowerShell en el equipo Windows del hospital (`C:\temp-notas`), headless por
defecto (`--con-cabeza` para verlo). Rendimiento observado: ~6-10 s por
objeción; 102 facturas/225 objeciones en 22,5 min. Transitorio conocido:
"modal no cerró tras Confirmar en 25 s" — reintento único integrado + segunda
pasada del lote lo dejan en cero (se ofreció subir 25→40 s; se descartó por
innecesario tras autorrecuperarse).

### 9.2 Consolidador de evidencias (`tools/evidencias_a_pdf.py`)
`--lista lista.txt | --paginas a.png b.png | --carpeta DIR` + `--salida X.pdf`.
Requiere Pillow; solo `.png/.jpg/.jpeg`; con `--carpeta` ordena por nombre
(los PNG `HUS<num>_<fecha>_<hora>.png` quedan por factura); fuerza sufijo
`.pdf`; convierte a RGB; multipágina con `save_all`. Naming institucional:
`GI-33-<consecutivo>-2026.pdf` (lote 14-jul = **GI-33-5182-2026**).

### 9.3 Robot DGH (`tools/responder_glosas_dgh.py`, PR #134 fusionado)
- **Hallazgo raíz:** el modal "Conceptos del trámite de objeción" es WinForms
  que hospeda WPF/DevExpress **opaco a UIA y win32** — probado por 4 vías
  (tree-walk desde `DGFRMPrincipal`, conexión UIA a su HWND, conexión win32,
  y `GetFocusedElement` tabulando: los 28 TAB stops reportan la Window).
  → **Se descartó** el control por árbol de elementos y se pivotó a
  **coordenadas de pantalla**: `_MODAL_OFFSETS` (grabar/concepto/
  observaciones/aplicar/check_fila, referencia 360,166 @1920×1080),
  `_rect_modal(hwnd)`, `_targets_modal(rect)`, `_click_abs(x,y)`,
  `_calibrar_modal(hwnd)` (pasea el mouse SIN clickear para validar
  offsets), `_responder_modal(hwnd, cod_respuesta, detalle, grabar,
  dump_al_fallar)` y flag CLI `--calibrar`.
- **Bug real hallado por la revisión Fable:** `.exists()` de pywinauto 0.6.9
  solo captura `ElementNotFoundError`/`MatchError`/`InvalidWindowHandle`/
  `InvalidElement`; con 2+ coincidencias lanza `ElementAmbiguousError` NO
  capturada → falso "no existe". Fix: sondear con `found_index=0` en
  `_buscar`/`_grid_con_fila`/`_diag_grids` (verificado contra el código
  fuente de pywinauto). Además `.exists()` MUTA los criterios del spec y
  `_buscar` debe devolver `WindowSpecification` (no wrapper) para búsquedas
  anidadas.
- Otras piezas: `_escapar` en una pasada para `{}+^%~()` (send_keys);
  `procesar_factura` dividido en `_abrir_editor`/`_cargar_factura`/
  `_esperar_autocargue`; botón AGREGAR robusto (`set_focus()` + fallback
  Ctrl+N + verificación de la pestaña Editor; el click se lo tragaba un
  tooltip flotante "AGREGAR (Ctrl+N)"); autocargue asincrónico esperado hasta
  **120 s** con progreso (falsos negativos a 60 s en sesiones degradadas).
- **Pendiente:** correr `--calibrar` en el equipo de la oficina y validar el
  llenado real (tarea abierta #4).

### 9.4 CI/CD y suscripción de PRs
GitHub Actions con 3 gates: **Lint (ruff: `check --select F,W6` + `format
--check`)**, **Tests (pytest, `DISABLE_SCHEDULERS=1`, SQLite
`test_ci.db`)**, **Security scan (pip-audit)**. Esta conversación además usó
la suscripción de actividad del PR #179: el webhook de fallo de CI disparó el
diagnóstico y fix automático (§13.3) sin intervención del auditor.

---

## 10. Archivos creados/modificados por esta conversación

**En el repo (commits/PRs):**
| Archivo | Cambio |
|---|---|
| `tools/responder_glosas_dgh.py` | Bot completo por coordenadas + `--calibrar` + fixes Fable (PR #134, ~20 commits del 30-jun al 02-jul). |
| `tools/dump_dg.py` | Volcador del árbol UIA de DGH (30-jun). |
| `tools/responder_glosas_simed.py` | `--evidencias-dir`, detección de éxito robusta, docstring/anotación de `leer_excel_respuestas`. |
| `tools/evidencias_a_pdf.py` | Nuevo (26-jun). |
| `tools/login_dg.py`, `tools/motor_glosas_hus.py`, `tools/responder_glosas_coosalud.py`, `app/services/rag_service.py` | Limpieza ruff F (import/vars muertos, sets duplicados) — 30-jun. |
| 13 archivos de `tools/` | `ruff format` (gate de formato en verde) — 30-jun. |
| `tests/test_api/test_import_history.py` | Fechas relativas (`ahora_utc() - timedelta`) — 30-jun. |
| `BITACORA.md` | Nueva (PR #179, commit `6622cd5`); luego el usuario/otro chat la fusionó con la de COOSALUD. |
| `CLAUDE.md` | Nueva (PR #179); luego fusionada (reglas del repo, rama del otro chat, CUV, piloto de 1 factura, sin acceso a D:). |
| `tests/test_api/test_por_dia_semana.py`, `tests/test_api/test_heatmap_actividad.py` | Helper `_lunes_reciente()` + siembras relativas (PR #179, commit `0b358d8`). |
| `docs/ENTREGA_MODULO_GLOSAS_DISPENSARIO_SIMED.md` | **Este documento.** |

**Productos de datos (scratchpad / Downloads del auditor):**
| Archivo | Contenido |
|---|---|
| `respuestas_glosa_INICIAL_DSE_26JUN.xlsx` | Lote 26-jun (primeras respuestas DSE). |
| `respuestas_glosa_INICIAL_DSE_01JUL.xlsx` | Lote 01-jul (fuente `GLOSAS_1_JULIO.xlsx`, 150 fact. en fuente). |
| `respuestas_glosa_DISPENSARIO_06JUL.xlsx` | 65 obj / 53 fact (fuente `RESPUESTAS_GLOSAS_6_JULIO.xlsx`, hoja `i`, 70 fact. fuente). Subido. |
| `respuestas_glosa_DISPENSARIO_09JUL.xlsx` | 225 obj / 102 fact. Subido y verificado 100 %. |
| `respuestas_glosa_DISPENSARIO_14JUL.xlsx` | 44 obj / 28 fact / $46.016.019 (fuente `GLOSAS_14_JULIO.xlsx`; codes: TA0201×14, TA0301×13, TA0801×5, CL0101×3, AU0701×2, TA2301×2, SO4201×2, AU0802/FA2302/SO0801×1; 4 facturas multi-concepto: 519530×12, 520337×4, 522834×2, 523104×2). |
| `respuestas_glosa_DISPENSARIO_17JUL.xlsx` | 115 obj / 58 fact / $87.605.050 (fuente `GLOSAS_17_JULIO.xlsx`, 22 códigos; distribución final: TARIFA 69, TARIFA_DISPOSITIVO 14, SOPORTE 10, MATERIALES 7, CALIDAD_ESTANCIA 5, LISTA_PRECIOS 2, ESTANCIA_CAUSACION 2, PROC_INDEPENDIENTE 2, MISCODIFICACION 1, PERTINENCIA 1, TARIFA_SALDO 1, INSUMO_FACTURA 1). |
| `respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx` | 3 fact / 38 obj / $20.054.751 (518186: 5 obj/$19.558.220; 515107: 21 obj/$338.773; 515773: 12 obj/$157.758) — totales cuadrados al peso contra las Recepciones 179722/179779/179781. |
| `respuestas_glosa_CONSOLIDADO.xlsx` | 116 fact / 238 obj / $94.150.626 (51 de 06-jul, 63 de 09-jul, 2 de 14-jul; 0 sin fuente; 0 genéricas). |
| `respuestas_glosa_RADICADOS_JUNIO.xlsx` | Extracto de 28 obj de 6 facturas con columna "Lote" (para radicación). |
| `glosa_motor.py`, `gen_lote.py`, `gen_consolidado.py`, `gen_junio_pendientes.py`, `gen_14jul.py`, `gen_09jul.py`, `gen_06jul.py`, `gen_respuestas.py` | Generadores (§3). |
| `wf_verify_14jul_v2.js`, `wf_reverify_14jul.js`, `wf_confirm_14jul.js`, `wf_verify_17jul.js` | Workflows de verificación (§8.3). |
| `dump_14jul.json`, `dump_17jul.json`, `facturas_consolidado.txt`, `log_full.txt` | Datos de trabajo. |
| `informe_gerencia_glosas.html` | Informe de gerencia (artefacto publicado). |

---

## 11. Dependencias nuevas

- **En el repo: ninguna.** (Playwright, pywinauto, openpyxl, Pillow ya estaban.)
- **En el venv del scratchpad:** `ruff` (instalado el 22-jul para replicar los
  gates del CI en local; misma versión que resuelve pip, sin pin). `openpyxl
  3.1.5` ya estaba en el venv.

---

## 12. Configuración

- **Rutas Windows del auditor:** repo en `C:\temp-notas`; exports en
  `D:\USUARIO CARTERA\Downloads\`; evidencias en `D:\USUARIO CARTERA\
  Documents\DISPENSARIO MEDICO <DD-MM-2026>\EVIDENCIAS`; soportes del share
  hospitalario (Claude Code NO accede a D:\ ni al share — entrega comandos).
- **Variables de entorno:** `SIMED_USER=900006037` (+ clave por env var; DGH
  y COOSALUD análogos). CI: `SECRET_KEY`, `DATABASE_URL=sqlite:///./test_ci.db`,
  `DISABLE_SCHEDULERS=1`, `PYTHONPATH`.
- **Parámetros operativos del robot:** timeout cierre de modal 25 s; espera
  grilla 10 s; escaneo hasta 12 páginas; detalle truncado a 4.000; 2 intentos
  por objeción; `--reporte reporte_glosa.csv`.
- **Convenciones:** PDF `GI-33-<consecutivo>-2026`; PNG
  `HUS<numero>_<yyyymmdd>_<hhmmss>.png`; commits sin identificador de modelo
  (regla del repo); español claro para el auditor.
- **Git/PRs de esta sesión:** rama designada `claude/beautiful-cori-8s7raj`
  (se re-crea desde `origin/motor-glosas` cuando su PR ya fue fusionado y la
  remota borrada — pasó dos veces); default branch `motor-glosas`; clones
  remotos vienen *shallow* (hubo que `--unshallow` para reconstruir historia:
  1.674 commits desde 2026-04-08).

---

## 13. Riesgos (y cómo resolverlos)

1. **`--rehacer` pisa respuestas ya aceptadas en el portal.** Solo usarlo
   para re-radicar deliberadamente. El default (omitir contestadas) es lo
   seguro y lo que permite reanudar tras cortes.
2. **Desalineación de numeración Excel↔portal.** La numeración 1..N por fila
   del export en SU orden es la que casa con la grilla (evidencia 09-jul).
   Si un export viniera reordenado respecto del portal, las objeciones no
   coincidirían: el robot lo detecta (`ObjecionNoEnGrilla` / "ya contestada"
   inesperada) — parar y comparar contra la Recepción de Objeción.
3. **Entidades mezcladas en el export.** `disp()` filtra; si un lote trajera
   otra entidad para trabajar, hay que decidirlo explícitamente (regla actual:
   OMITIR — Chicamocha y FOMAG se omitieron por instrucción).
4. **Citas normativas.** NO citar Res. 3047/2008 (derogada), ni D.780/2016
   art. 2.6.1.4.2.4, ni D.2423/1996 art. 87 para ítems tarifados en SOAT, ni
   numerar el Anexo Técnico de la 2284 (es el No. 3 según `normativa.py`,
   pero se decidió citar sin número). La batería determinista (§8.3) protege
   contra regresiones — mantenerla al modificar plantillas.
5. **Tests "bomba de tiempo".** Patrón repetido 2 veces en el repo: siembras
   con fechas fijas + endpoints con ventana móvil (60/90 días) → CI rojo al
   pasar el calendario. Regla: **toda siembra de fechas en tests debe ser
   relativa a `ahora_utc()`** (helper `_lunes_reciente()` cuando el día de
   semana importa).
6. **Bitácora compartida entre chats.** Dos chats la actualizaron el mismo
   día y hubo fusión manual (la versión actual en `motor-glosas` es la
   fusionada). Riesgo de conflicto/pisado: actualizar SIEMPRE sobre la punta
   fresca de `motor-glosas` y con commits pequeños.
7. **Ramas de trabajo distintas por chat.** `CLAUDE.md` (fusionado) fija
   `claude/excel-reconciliation-data-9Bnpj` como rama de trabajo de aquel
   chat; esta conversación operó su rama designada
   `claude/beautiful-cori-8s7raj`. Al consolidar: la fuente de verdad es
   `motor-glosas`; las ramas de chat son efímeras post-merge.
8. **Detalle > 4.000 caracteres se truncaría** en el portal (máximo visto:
   2.087 — margen amplio; vigilar si se alargan plantillas).
9. **Plazos legales.** Las 3 facturas de junio se detectaron VENCIDAS
   (6 y 8-jul). Si el portal ya no permite responder, radicar por oficio
   dejando constancia (y alegar extemporaneidad del pagador si aplica).
10. **Los generadores viven en el scratchpad** (efímero). Este documento los
    describe por completo, pero el riesgo de pérdida se elimina moviéndolos
    al repo (recomendación §16.2).

---

## 14. Dependencias con otros módulos

- **Usa (lee) del Motor:** `data/plantillas_hus_base.json` (doctrina),
  `app/services/normativa.py` (normograma y Res. HUS 054/124/194),
  `app/services/catalogo_glosas.py` (significado autoritativo de cada código
  de glosa — p. ej. AU0701, AU0802, TA0601, CL0101, SO4201).
- **Alimenta:** el flujo de evidencias/radicación (PDF GI-33), el informe de
  gerencia, y la BITÁCORA común.
- **Hermanos (no tocados, no confundir):** bot COOSALUD
  (vco.ctamedicas.com), notas crédito SIMED (con validación CUV
  `tools/verificar_cuv_notas.py` — el portal acepta CUV inválido pero queda
  mal radicado), ADRES/FURIPS, tablero de cartera. Regla del repo: son
  plataformas y bots DISTINTOS.
- **El robot SIMED de este flujo** es compartido con el flujo de notas
  crédito del Dispensario (mismo archivo, páginas distintas del portal).

---

## 15. Pendientes

1. **Subir a SIMED** `respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx`
   (3 facturas, URGENTE por vencimiento) y confirmar con el log.
2. **Confirmar subida** de los lotes 14-jul y 17-jul (no se recibió el log de
   la corrida en esta conversación) + segunda pasada de verificación.
3. **PDF de evidencias**: correr `GI-33-5182-2026.pdf` (14-jul) y obtener el
   consecutivo GI-33 del 17-jul para el suyo.
4. **Soportes por caso del 17-jul** (checklist entregado): notas de
   enfermería 16-jun (529093); renglón tarifario nominal de cada dispositivo
   (coils Target 360/Hydrosoft, circuito AIRVO, MAOS) en Res. 054/124/194 —
   si alguno no figura, defenderlo por otra vía; descripción quirúrgica del
   vaciamiento (529291); reporte de lactato/piruvato y aclaración
   biopsia-vs-estereotaxia (CL0301 — caso más frágil del lote: la HC
   contradice lo facturado); justificación de la 2ª hemoclasificación; ficha
   técnica single-use de la pinza HAR9F; orden del contraste + cálculo
   dosis/peso (AU0701); verificación de la orden médica del examen AU0802.
5. **DGH:** ejecutar `--calibrar` y validar el llenado del modal por
   coordenadas en el equipo real (tarea #4, abierta desde el 02-jul).
6. **Informe de gerencia:** llenar el "valor total objetado defendido" del
   lote 09-jul desde `reporte_glosa.csv`.
7. **Mejora descartada por ahora:** subir timeout de cierre de modal
   25→40 s (reabrir solo si vuelven los transitorios en lotes grandes).
8. **Sugerido:** mover `glosa_motor.py` y `gen_*.py` al repo (§16.2).

---

## 16. Recomendaciones para fusionarlo al proyecto principal

1. **No hay nada de código pendiente de merge:** PR #134 y PR #179 ya están
   en `motor-glosas`. Este documento entra por PR propio.
2. **Persistir los generadores** (hoy en scratchpad): crear
   `tools/glosas_dispensario/` con `glosa_motor.py`, `gen_lote.py`,
   `gen_consolidado.py`, `gen_junio_pendientes.py` + un README con el flujo
   de §4. Con eso cualquier chat/equipo regenera lotes sin depender de una
   sesión. (Los textos completos de plantillas y reglas están en §3.1 y §8.2
   para reconstruirlos si el scratchpad ya no existe.)
3. **Unificar doctrina:** `glosa_motor.py` y `data/plantillas_hus_base.json`
   deben converger (mismo banco). Sugerencia: que `arg()` lea las plantillas
   del JSON del repo y el JSON incorpore las correcciones de §8.3 (derogada
   la 3047, sin art. 87 para ítems SOAT, etc.). Ojo: TA-G01 del JSON aún
   cita el art. 87 — corregirlo allí también.
4. **Respetar los invariantes** al integrar: apertura/cierre exactos,
   MAYÚSCULAS párrafo único, RE9901/aceptado 0, numeración 1..N por fila,
   hoja "Respuestas Glosa", solo Dispensario, piloto de 1 factura antes de
   masivo, segunda pasada de verificación, evidencia por factura, PDF GI-33.
5. **CI:** mantener la batería determinista de §8.3 como test si las
   plantillas entran al repo (es barata y ya cazó 3 regresiones reales).
6. **Bitácora:** conservar el contrato de `CLAUDE.md` (leer al inicio,
   actualizar al cierre con fecha, commit+push) — es lo que mantiene la
   memoria entre chats; actualizar SIEMPRE sobre `motor-glosas` fresco.
7. **Al retomar DGH:** empezar por `--calibrar`; no intentar de nuevo leer el
   interior del modal por UIA/win32 (callejón sin salida probado 4 veces).

## 17. Resumen ejecutivo (para quien lo mantenga)

Este módulo convierte el export de glosas del DGH en respuestas jurídicas por
objeción y las radica solo en SIMED. Sus tres piezas: **`glosa_motor.py`**
(clasificador de 14 reglas ordenadas + 16 plantillas endurecidas por 4 rondas
de verificación adversarial con ~1,5 M tokens de agentes — las correcciones
normativas de §8.3 NO son opcionales), **`gen_lote.py`** (Excel de carga con
formato e invariantes fijos) y **`responder_glosas_simed.py`** (robot
reanudable que salta lo contestado, reintenta transitorios y deja evidencia).
Verdades no negociables aprendidas con evidencia: el portal numera objeciones
por línea de concepto (no por trámite `Oid`); la entidad glosadora ES parte
del contrato 440 (tesis central de tarifa); la Res. 3047/2008 está derogada;
el art. 87 del D.2423/1996 y el art. 2.6.1.4.2.4 del D.780/2016 son
autogoles; toda siembra de fechas en tests debe ser relativa. Operativa
estándar: analizar el lote → clasificar por observación (0 genéricas) →
generar → verificar → piloto de 1 factura → `--todas` → segunda pasada
(`OK: 0`) → PDF GI-33 → actualizar BITÁCORA. En números, esta rama dejó
subidos o listos ~7 lotes del Dispensario (≈245 facturas y ≈550 objeciones
solo en julio, >$150 M defendidos en los lotes valorizados) y dos PRs
fusionados. Lo primero que debe hacer quien reciba esto: subir las 3 facturas
vencidas de junio y confirmar los lotes 14/17-jul.
