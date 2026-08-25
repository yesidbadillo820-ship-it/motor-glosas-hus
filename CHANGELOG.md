# Registro de cambios

## Sesión 25-ago-2026 — `unir_soportes_adres.py` + arreglo del desglose huérfano

### `unir_soportes_adres.py` (nuevo)
Une los soportes de cada carpeta de factura en un solo `<FACTURA>_SOPORTES.pdf`,
en el orden de la lista del área (13 grupos, de RESPUESTA A GLOSA a OTROS). El
detallado queda fuera del PDF: la lista lo pide en Excel.

Clasifica por nombre de archivo con dos reglas que evitan los falsos positivos:
gana la **palabra más larga** («NOTAS DE ENFERMERIA» sobre «NOTAS»), y las
abreviaturas cortas se buscan como **palabra completa** (`INS` no casa dentro de
`INSTITUCIONAL`). Lo no reconocido va a OTROS y sale marcado en el reporte.
`--mapa-nombres` agrega palabras sin tocar el código.

Reusa `unir_pdfs` / `clave_natural` de `unir_pdfs_carpetas.py` — la unión y el
orden natural ya estaban resueltos; aquí solo se agrega la capa de orden.

Simula por defecto (`--aplicar` para escribir), se excluye a sí mismo de la
entrada (idempotente) y un PDF ilegible se omite sin tumbar el lote. Avisa las
facturas sin RESPUESTA A GLOSA o sin EPICRISIS.

Incluye `UNIR_SOPORTES_ADRES.cmd` (CRLF), guía en español y 42 pruebas.

### `ajustar_detallado_glosas.py` — desglose huérfano
**Defecto:** cada ítem se decidía por separado. Cuando la entidad aprobaba el
procedimiento (CUPS, que no aparece en el reporte del ADRES porque este glosa
con códigos SOAT) pero seguía glosando sus componentes, el principal se quitaba
y los componentes quedaban huérfanos: el detallado mostraba honorarios y
derechos de sala sin decir de qué cirugía eran. El auditor tuvo que rehacer a
mano la HUS383283.

**Arreglo:** una pasada previa marca los principales cuyo desglose sobrevive y
los conserva con la acción nueva `ACCION_ENCABEZADO` — se ven, pero no suman al
subtotal, porque su valor ya está en los renglones de desglose. La condición de
"no suma" de los hijos se corrigió en consecuencia (`id(padre) not in
rescatados`), para que el valor no se pierda ni se cuente dos veces.

2 pruebas nuevas: el principal se queda como encabezado y no suma; y si su
desglose también se fue, se va como siempre.


## Sesión 24-ago-2026 — `organizar_objeciones_adres.py`: cuadre contra el reporte del ADRES

### El defecto que corrige
El detalle del ADRES cuenta la misma plata varias veces, y la conversión la
sumaba tal cual: el paquete 31068 salía en **$1.032.239.679** contra los
**$646.908.552** que el ADRES reporta glosados. Cargado a DGH habría objetado
hasta tres veces el mismo dinero.

Dos fuentes de repetición, ambas del archivo del ADRES:
- Filas de causal de reclamación (2102, 2103…) con el valor **completo** de la
  reclamación, además del detalle por servicio.
- El mismo servicio (mismo código, cantidad y valores) repetido por cada causal.

### `--reporte-reclamaciones`
Lee el `ReporteReclamPAQUETE_*.xlsx` (encabezado en la 2ª fila: encima va la de
totales) y deja cada factura sumando **exactamente** su `Valor Glosado`:
1. `conciliar_factura` quita las filas que repiten el total de la reclamación.
2. Quita las repeticiones, mayor primero, **sin bajarse del valor reportado**.
3. `cuadrar_con_reporte` corre **al final**, sobre los valores ya topados por el
   guardián de DGH, y reparte el residuo desde el renglón mayor hacia abajo sin
   dejar valores negativos. También reescribe el `$<valor>` del `CRDOBSERV`.

Resultado 31068: **324/324 facturas cuadradas**, $646.908.553 (Δ $1 por redondeo
a pesos enteros), 169 renglones quitados, 65 facturas ajustadas.

### `--completar-servicios`
Ningún `SLNSERPRO` queda vacío: se usa el candidato del cruce y, si no hay,
`servicio_principal` (el servicio de más peso de la factura en DGH). No es
homologación — cada fila así queda en `REVISAR` con `CODIGO DE SERVICIO
ASIGNADO` y su procedencia. En el 31068: 1.856 vacíos → **0**, con 1.768 filas
marcadas.

### Otros
- `_hoja_con` acepta `max_filas` para encabezados que no están en la 1ª fila.
- Motivos nuevos en REVISAR: `REV_REPITE_TOTAL`, `REV_DUPLICADO`,
  `REV_AJUSTE_REPORTE`, `REV_FACTURA_SIN_REPORTE`, `REV_SERVICIO_ASIGNADO`.
- El resumen del CLI imprime el cuadre contra el reporte y las facturas que no
  cuadren.

### Pruebas
16 nuevas (65 en total en el archivo): que se quite el renglón que repite el
total, que las repeticiones se quiten de mayor a menor, que **nunca se baje del
valor reportado**, que el cuadre mande sobre el tope de DGH, que el ajuste se
reparta si no cabe en un renglón, que ningún valor quede negativo, y que el
lector tolere el encabezado en la 2ª fila.


## Sesión 21-ago-2026 — `organizar_objeciones_adres.py`: glosas del ADRES → OBJECIONES de DGH

Bot nuevo (`tools/organizar_objeciones_adres.py` + `OBJECIONES_ADRES.cmd` +
`README_organizar_objeciones_adres.md`) que convierte el Excel de glosas del
ADRES al layout de 16 columnas que recibe Dinámica Gerencial.

### Homologación del código de servicio (`SLNSERPRO`)
Seis pasos, siempre dentro de la misma factura, parando en el primero que
acierta: código directo (igualando ceros de relleno), SOAT→CUPS con el
Homologador Gold Standard, descripción igual, descripción por prefijo, valor
exacto + ≥50 % de palabras en común, y similitud ≥0,85. Lo que no se resuelve
sale con la casilla **vacía** y con su mejor candidato listado en `REVISAR` —
nunca se escribe un código deducido.

En el paquete 31068: 2.763 de 3.262 renglones con servicio (84,7 %).

### Reglas del formato
- `CDCONSEC` y `GENUSUARIO4` como TEXTO, `CROCLAOBJ=0`, `GENUSUARIO4=999`.
- `CRNCXC` en formato largo (`HUS311371` → `HUS0000311371`).
- `CROTIPOBJ` por factura: administrativas `0`, pertinencia `1`, mezcla `2`.
- **Guardián de valores** (el mismo de `cruces_dgh.generar_objeciones`): la
  objeción no supera el valor del servicio en DGH ni el saldo de la factura.
- **Lotes de 300 facturas** (tope de DGH), sin partir ninguna factura.

### Detalles que costaron
- El libro del ADRES trae una tabla dinámica con las mismas columnas pero los
  valores sumados (`Suma de Valor Glosado`); detectar la hoja de glosas por dos
  columnas dejaba todas las objeciones en cero. Ahora se exigen cuatro.
- El texto de la causal viene repetido detrás de su código en la misma celda;
  se corta en la última aparición de `<código>-`.
- `CRNCONOBJ`: el ADRES usa códigos numéricos de 4 dígitos y DGH los de 6 del
  Manual Único, y **no existe tabla oficial que los equipare**. Se escribe el
  del ADRES tal cual y se entrega la hoja `CODIGOS` + `--mapa-codigos` para que
  el auditor defina la equivalencia.

### Pruebas
`tests/test_tools/test_organizar_objeciones_adres.py` — 49 pruebas, incluida
una de punta a punta que arma los tres libros de entrada y verifica el archivo
de salida celda por celda.

## Sesión 20-ago-2026 (noche) — Rediseño de la aplicación web del ICFES

De cuatro pantallas planas a un panel con el plan de estudio adentro.

### Funcionalidad nueva
- **El plan de estudio ahora vive en la aplicación**: Inicio abre en «qué te
  toca hoy» con los bloques del día y un botón para empezar cada uno; la
  pantalla **Plan** muestra las cuatro fases y el detalle de cualquier semana.
- **Estudiar** (pantalla nueva): repaso del día, cuaderno de errores, las
  competencias más flojas con botón para practicarlas, y práctica libre con
  filtros de área, competencia, dificultad y procedencia.
- **Progreso**: proyección al día del examen, línea del año, una mini gráfica
  por área, competencias ordenadas, causas de error con su remedio, calendario
  de constancia y preguntas reincidentes.
- **Durante las preguntas**: cronómetro con el ritmo real del examen y semáforo
  de ritmo, atajos de teclado (A-D y Enter), marcar preguntas para revisar y
  lecturas largas en serif.
- Barra lateral en pantallas grandes; barra inferior en celular.

### Una sola fuente de verdad
- La política del plan (fases, mezclas, piso por área, minutos por bloque) y las
  escalas de puntaje se **exportan** desde `icfes/plan.py` y `icfes/puntaje.py`
  en vez de reescribirse en JavaScript.
- **`tests/test_icfes/test_nucleo_web.py`** extrae el núcleo de cálculo de la
  plantilla, lo corre con node y lo compara contra Python: metas por área,
  reparto de horas, puntaje, repaso espaciado y el plan completo **bloque por
  bloque** en tres escenarios. Se salta si node no está instalado.

### Color y accesibilidad
- Paleta de gráficas validada con el script de la guía de visualización: rampa
  secuencial monótona en claro y oscuro, y contraste ≥ 3:1 en las dos
  superficies.
- La primera versión coloreaba cada barra por estado; el validador la rechazó
  (verde y rojo se confunden para daltonismo, ΔE 4,1). Se corrigió por diseño:
  una sola serie, un solo tono, y el estado en una etiqueta con texto.
- Tres estados de tema (claro, oscuro por sistema, oscuro elegido) con una
  prueba que verifica que ningún color viva solo dentro de un bloque de tema.

### Correcciones encontradas probando en navegador
- Dos simulacros el mismo día se superponían en la gráfica de línea y sus zonas
  de hover se tapaban. Ahora la serie deja un punto por día (el último) y el
  ancho de la zona sensible se calcula desde la separación real entre puntos.
- El calendario de constancia solo miraba hacia atrás desde hoy: con avance
  importado decía «199 días con estudio» y salía vacío.
- En práctica el cronómetro estaba congelado y el semáforo de ritmo siempre en
  verde.

### Pruebas
266 en total (27 nuevas). `ruff check` y `ruff format` limpios sobre 1.229
archivos. Recorrido completo verificado en Chromium: escritorio y celular, tema
claro y oscuro, sin errores de JavaScript y sin desbordamiento horizontal.

## Sesión 20-ago-2026 (cierre) — Bot de doble clic del ICFES y guías corregidas

**Falla del primer uso real:** los comandos de la guía se corrieron desde
`C:\Users\cartera` y Python respondió `No module named icfes`. `python -m icfes`
requiere que la consola esté dentro de la carpeta del repositorio, y ninguna de
las tres guías lo decía.

### Cambios
- **`tools/ICFES.cmd`** (nuevo): bot de doble clic con menú completo — hoy,
  practicar, repasar, simulacro, progreso, plan, configurar y exportar la app.
  Hace `cd /d "%~dp0.."` antes de llamar a Python, así que el error no puede
  ocurrir; y verifica que Python esté instalado antes de intentar nada.
- **`docs/GUIA_SISTEMA_ICFES.md`**, **`docs/ESTRATEGIA_ICFES_400.md`** y
  **`README.md`**: el doble clic va primero, el `cd` aparece como paso cero y se
  explica qué significa `No module named icfes`.

### Pruebas (`tests/test_icfes/test_bots_windows.py`, 12 nuevas)
- Los bots del ICFES se paran en la carpeta del repositorio y avisan si falta
  Python.
- El menú no llama a ningún subcomando que no exista en el CLI (se valida
  contra el parser real).
- Los bots no traen credenciales.
- **Todos los `.cmd` del repositorio conservan finales de línea CRLF.** Esta
  regla estaba en `.gitattributes` y en CLAUDE.md pero no tenía prueba; con LF
  la ventana se cierra en Windows sin ejecutar nada.

Total del módulo: 251 pruebas.

## Sesión 20-ago-2026 — Sistema de preparación para el ICFES Saber 11 (`icfes/`)

Módulo **independiente** del Motor de Glosas: no importa nada de `app/` ni de
`tools/`, y solo usa la librería estándar de Python 3.11, así que la carpeta
`icfes/` se puede copiar a cualquier computador y funciona.

### Qué trae
- **`icfes/dominio.py`** — el examen modelado con datos oficiales: 254 preguntas
  calificables (41/50/50/58/55), 24 de pilotaje, pesos 3-3-3-3-1, dos sesiones
  de 4 h 30, y las 17 competencias de las cinco áreas.
- **`icfes/puntaje.py`** — puntaje global 0-500 con la fórmula oficial
  (`(3·LC+3·MAT+3·SOC+3·CN+1·ING)/13 × 5`); estimación de área 0-100 con curva
  declarada y editable (`CURVA_PUNTAJE`), siempre rotulada como estimación;
  reparto de una meta global en metas por área; corrección por azar.
- **`icfes/banco/`** — 110 preguntas de práctica en JSON (una por área), todas
  con explicación y con el distractor principal identificado. Cubre las 17
  competencias. Textos de Lectura Crítica en dominio público.
- **`icfes/plan.py`** — plan de 50 semanas en cuatro fases, con reparto de horas
  por peso oficial × brecha, piso del 8 % por área, día de descanso semanal,
  última semana aliviada y 11 simulacros completos.
- **`icfes/repaso.py`** — SM-2 adaptado; nunca programa un repaso posterior al
  examen; deduce la calidad del repaso de acierto, tiempo y causa del error.
- **`icfes/simulacro.py`** — simulacros con la estructura y los segundos por
  pregunta reales; a escala cuando el banco no alcanza, avisándolo.
- **`icfes/progreso.py`** — dominio ponderado por recencia, cuaderno de errores
  por causa con su remedio, racha y proyección por mínimos cuadrados que declara
  cuándo no es confiable.
- **`icfes/almacen.py`** — SQLite local (`~/.icfes/progreso.db`).
- **`icfes/cli.py`** — `python -m icfes iniciar|hoy|plan|practicar|simulacro|
  repaso|progreso|banco|exportar-web`.
- **`icfes/exportar_web.py`** + **`plantilla_web.html`** — aplicación web de un
  solo archivo, sin red, adaptable a celular, con tema claro/oscuro y avance en
  `localStorage`.
- **`tools/ICFES_APP.cmd`** — bot de doble clic para Windows (CRLF).

### Correcciones hechas durante el desarrollo
- **Simulacro**: reconstruía las respuestas desde la base de datos, así que una
  pregunta acertada en una práctica del mismo día contaba como acertada en el
  simulacro. La ronda ahora devuelve las respuestas reales, traducidas del orden
  barajado al orden original de la pregunta.
- **Exportación web**: la plantilla dejaba su objeto por defecto pegado al JSON
  inyectado (`const DATOS = {…}{…};`) y la página no cargaba. Se detectó abriendo
  la app en Chromium. Corregido con marcas de apertura/cierre y cubierto por
  prueba.
- **Banco**: la primera versión concentraba el 65 % de las respuestas correctas
  en la letra B. Como las opciones se barajan en cada práctica, el validador
  ahora exige que ninguna explicación nombre letras y verifica el reparto.

### Pruebas
239 pruebas en `tests/test_icfes/`; `ruff check` y `ruff format` limpios.
Recorrido completo de la app web verificado en Chromium (práctica, explicación,
cronómetro, resultado, progreso, persistencia tras recargar) sin errores de
JavaScript.

### Documentación
`docs/GUIA_SISTEMA_ICFES.md` y `docs/ESTRATEGIA_ICFES_400.md`.

## Sesión 10-jul-2026 — Suite Cartera HUS: herramienta multifuncional (GUI + CLI)

Integra en `tools/suite_cartera_hus/` la Suite de Cartera/Auditoría (menú
único de radicación, glosas y cruces masivos: reemplaza Power Query +
BUSCARV) con correcciones de fondo, endurecimiento y pruebas.

### Correcciones (verificadas con pruebas)
- **`a_numero`**: `'50.000'` se leía como `50` y no `50000` — corrompía
  TODOS los importes (glosado/servicio/saldo/copago y el guardián de
  valores). Ahora resuelve miles/decimales en formato colombiano, UE y US.
- **`generar_objeciones`**: `KeyError` si el Excel elegido no traía
  `valor_servicio/saldo/copago`; ahora da un error claro o tolera la falta.
- **`consolidar`**: renglones sin factura (celda vacía y sin factura en el
  nombre) se perdían en silencio en el `groupby`; ahora sobreviven visibles.
- **`consolidar`**: si no hay columna propia de código de servicio ya no se
  confunde con la de glosa (evita agrupar/sumar por la clave equivocada);
  además depura renglones byte-idénticos (duplicados de exportación).
- **`extraer_factura`**: reconoce facturas numéricas pegadas a `_` y da
  prioridad al formato HUS aunque una fecha aparezca antes en el nombre.
- **`leer_tabla`**: acepta listas de una sola columna (facturas ya
  objetadas) y CSV en latin-1 (Windows), que antes reventaban.
- **`extraer_zip_recursivo`**: los ZIP anidados ya no se pisan entre sí, y
  una entrada insegura (`../`) se omite sin abortar todo el ZIP.

### Seguridad
- Las contraseñas de los portales salen de `entidades.json` a un archivo
  **local no versionado** (`entidades.credenciales.json`, en `.gitignore`).
  La Suite las vuelve a unir en memoria al abrir. Incluye
  `herramientas/separar_credenciales.py` y una plantilla `.example`.

### Nuevo
- **`suite_cli.py`**: la misma Suite por línea de comandos (`entidades`,
  `organizar`, `consolidar`, `objeciones`, `evidencias`, `todo`) para
  automatizar sin ventana.
- **`tests/test_tools/test_suite_cartera_hus.py`**: 40 pruebas del núcleo
  (las que requieren pandas se saltan si no está, como el resto de tools).

## Sesión 1–2-jul-2026 — El expediente: contratos + soportes + precedentes

Diagnóstico que disparó la sesión (del usuario): *"la IA se rehúsa a
refutar... es como pegar el concepto en una IA normal"*. Causa raíz
confirmada: el motor argumentaba **a ciegas** — tres conexiones de datos
existían como código pero estaban desenchufadas de la generación del
dictamen. Esta sesión las enchufó (rondas 23–25).

### Fase 1 — Contratos (ronda 23)
- `get_contrato` ahora lee la BD (`ContratoRecord` + `ClausulaContrato`),
  no solo el catálogo estático: fin del falso "SIN CONTRATO PACTADO"
  cuando sí hay contrato cargado.
- Emparejamiento flexible de EPS ("AURORA" encuentra "SEGUROS DE VIDA
  AURORA S.A.").
- **26 cláusulas LITERALES de 11 pagadores reales** cargables con
  `scripts/seed_clausulas_contrato.py` (idempotente): AURORA (8),
  COMPENSAR, COOSALUD, SUMIMEDICAL, SALUD MÍA (3), POSITIVA (2), PPL (2),
  FAMISANAR 2026, DISPENSARIO MÉDICO/DMBUG (3), POLICÍA oncología (2),
  FOMAG (2 — incl. Circular 004/2025: sin autorización previa a docentes).
  Tarifas verificadas contra los Excel (SOAT−3/10/15/20%, UVB−5/8%,
  SMDLV−20%).
- Correcciones de catálogo: FOMAG a SOAT SMDLV −20% (Acta 012), POLICÍA
  oncología a UVB−8% + institucionales (Anexo 2 de la minuta), PRECIMED
  eliminado (era contrato de suministro con PRECIMEC SAS, no un pagador).

### Fase 2 — Soportes (ronda 24)
- **Tope de OCR 2000 → 12000 chars** en el caso simple (la IA por fin ve
  la HC adjunta); tunable por env (`GLOSA_SOPORTES_MAX_CHARS_*`).
- **Multimodal automático** (`GLOSA_MULTIMODAL_AUTO=1`): los casos que ya
  escalan a Claude mandan los PDFs nativos completos; los simples siguen
  en Groq con texto (no es "siempre Claude").
- **Gate interactivo de expediente**: el detector determinista avisa en el
  prompt qué soportes faltan y prohíbe inventar evidencia; fallback
  sin-soportes reescrito de "el registro clínico respalda la atención"
  (invitación a alucinar) a reglas anti-invención siempre-verdaderas.
- **Auditor Forense conectado al dictamen** (opt-in,
  `GLOSA_AUDITOR_FORENSE_PREPASS=1`): pre-pass que lee los PDFs y antepone
  un mapa de folios (folio + fecha + hallazgo + faltantes) al contexto.
- Review adversarial del propio diff cazó y corrigió 6 bugs antes de
  mergear (el peor: Opus degradándose a Sonnet en casos ≥$10M por la vía
  multimodal; backstop nuevo en el validador contra fuga del andamiaje
  del prompt al dictamen).

### Fase 3 — RAG/banco (ronda 25)
- **Few-shots por SIMILITUD BM25** (`GLOSA_FEWSHOT_BM25=1`): cuando el
  match exacto (eps+código) no llena los ejemplos, se completa con el
  precedente GANADO más parecido al texto de la glosa (RAGService, antes
  desconectado de la generación). Sin tokens extra.
- Filtro de contrato ajeno sobre los precedentes + instrucción anti-copia
  reforzada (estilo sí, datos del otro expediente no).

Suite: **4069 tests verdes**. Todo reversible por env var sin redeploy.

---

## Sesión 30-jun-2026 — De "a ciegas" a "medido"

Resultado medible de la sesión, con el **tablero de calidad** (0–10) sobre
los 4 casos difíciles reales:

| Caso | Antes | Después |
|---|---|---|
| MEDIMÁS da Vinci $273M | 0.5 | **10** |
| ECOOPSOS coclear $389M | 4.5 | **10** |
| SALUD TOTAL TMS $98M | 5.0 | **10** |
| Hemofilia + sanción $156M | 0.0 | 6 → escala a Claude (subiendo) |
| **Promedio** | **2.5/10** | **~9/10** |

El cambio de fondo: dejamos de parchear a ciegas. Ahora cada cambio se
**mide** contra una rúbrica experta y el que **regresa** se detecta solo.

---

### Operación / producción (incidentes resueltos)
- **Cloudflare Error 1033** (app caída): causa raíz `net.ipv4.ip_forward=0`
  → NAT de Docker rota → los contenedores no salían a internet y el túnel
  no conectaba. Fix: `ip_forward=1` + reinicio de Docker (+ persistencia en
  `/etc/sysctl.d/`).
- **502 Bad Gateway**: contenedor `motor` con referencia stale tras un
  `up --build`. Fix: `docker compose down && up -d`.

### Limpieza de imports (PR #152, mergeado)
- Eliminados **~100 lazy imports redundantes** en `glosas_stats.py` y
  `sistema.py` (símbolos ya disponibles a nivel de módulo).
- Agregado `app/utils/__init__.py` faltante.

### Mejora #3 — Salida estructurada incremental (flag OFF por defecto)
- Flag `GLOSA_CAMPOS_ESTRUCTURADOS` (config + docker-compose + .env.example).
- La IA confirma 6 campos críticos (EPS, servicio, contrato, cláusulas,
  sanción, sub-conceptos) en un bloque JSON que el motor cruza contra los
  valores **deterministas** (verdad = determinista) y registra divergencias.
- Parser tolerante + validación + degradación elegante + tests (31).
- Runbook de activación: `docs/RUNBOOK_CAMPOS_ESTRUCTURADOS.md`.

### Ronda 21 — Auditoría del dictamen MEDIMÁS da Vinci (9 fixes)
- **#1 (crítico)** Contrato negado en el cuerpo ("al no existir contrato
  pactado") pese a que la glosa lo cita → regex ampliado a la forma verbal.
- **#2 (crítico)** Tarifa: ya no afirma "SOAT pleno / sin contrato" cuando
  la glosa cita un contrato; defiende dentro del contrato (Pacta Sunt S.).
- **#5** Pertinencia: rebate la GPC citada con T-121/2015 + evidencia 1A.
- **#6** Rebate por nombre las normas que cita la EPS (+ regex de extracción
  que ahora captura "Res. 0112/2012", "Decreto 4747/2007 Art. 20").
- **#8** Banner + penalización cuando se evade una cláusula citada.
- **#9** Vocabulario de cobertura (evento adverso, liquidación).
- **#10** Defensa de liquidación anclada (Auto 116/2024).
- **#11** Recorte de coda procesal unida por conjunción.
- **#12** "Art. 177 Ley 100" pelado en debate tarifario → fundamento correcto.

### Defensa clínica (PR #151, mergeado + integrado)
- Banco de evidencia nivel 1A (da Vinci, coclear, TMS, hemofilia, etc.) que
  nunca se había integrado a producción. Ahora se inyecta al prompt y se
  audita la literatura citada.

### Ronda 22 — Defectos del tablero (capa de generación)
- Reglas de prompt: sanción → atacar la legalidad (NO "Pacta Sunt Servanda"
  ante una multa); prohibido tono amenazante; prohibido el falso "silencio
  positivo"; prohibido inventar el texto de cláusulas/normas; no confundir
  normas por tema (Ley 1388/2010 es de cáncer, no auditiva).
- Red de seguridad: `_corregir_norma_mal_aplicada` (Ley 1388→1618).

### Tablero de calidad (lo nuevo de fondo)
- `tests/benchmark/scorer.py`: rúbrica experta determinista (0–10, sin LLM).
- `tools/scoreboard.py`: mide el texto guardado + **memoria** (historial) +
  detección de **regresión** + modo `--rescore-live`.
- `tools/scoreboard_live.py`: corre las 4 glosas por el **motor real** y las
  puntúa (mide el efecto real de cada cambio). Progreso visible + timeout.
- `docs/EJEMPLOS_DICTAMENES_ESPERADOS.md`: 4 casos con el dictamen esperado
  y checklist de criterios.
- Regla del proyecto: la IA es BUENA solo si **los 4 casos sacan ≥ 7**.

### Routing
- Hemofilia con inhibidores ("factor VII / eptacog") ahora escala a Claude
  (palabra-clave + valor), no se queda en Groq.

---

_Total sesión: 18 commits en la rama + PR #151 y #152 mergeados._
