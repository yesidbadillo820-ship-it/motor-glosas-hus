# Registro de cambios

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
