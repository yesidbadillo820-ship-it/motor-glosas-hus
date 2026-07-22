# HOSPIAI — Arquitectura de la plataforma

**Sistema Operativo Inteligente de Cuentas Médicas · ESE Hospital Universitario de Santander**

> Documento fundacional. Define los dominios, el modelo de datos, el catálogo
> institucional, el motor de reglas, el grafo de conocimiento y el orquestador
> de agentes. Toda funcionalidad nueva se implementa como un **agente**
> independiente, desacoplado y reutilizable que se conecta a esta arquitectura.
>
> Estado: v1 — 22 de julio de 2026.

---

## 1. Visión y principios

HOSPIAI no es un script que recorre carpetas: es una **plataforma de agentes
especializados** que cubre el ciclo completo de la cuenta médica — desde que
nace el expediente hasta que se paga, se glosa o se concilia — y que aprende de
cada resultado.

**Principios no negociables:**

1. **Solo lectura por defecto.** Ningún agente modifica, mueve, renombra ni
   borra archivos de los shares del hospital. Los agentes *proponen* (por
   ejemplo, un renombre o un armado de paquete); *aplicar* requiere orden
   expresa del humano responsable. La única excepción futura (radicación
   automática en portales, Dominio 4) exige autorización formal de gerencia y TI.
2. **Todo pasa por el expediente.** Los agentes no se hablan entre sí por
   archivos sueltos: leen y escriben el **Expediente Digital** (base de datos).
   Eso los desacopla: cualquier agente se puede reescribir sin tocar los demás.
3. **Toda afirmación es trazable.** Cada hallazgo lleva: qué agente lo produjo,
   cuándo, sobre qué evidencia (ruta/archivo) y qué regla lo sustenta (con su
   fuente normativa o contractual).
4. **Human-in-the-loop.** La IA prepara, verifica y recomienda; las decisiones
   con efecto externo (radicar, responder, conciliar) las aprueba una persona.
5. **Evolución sin demolición.** Lo ya construido y probado (motor de
   radicación, explorador, tablero, diagnóstico) no se bota: se **envuelve**
   como los primeros agentes de la plataforma.

---

## 2. Arquitectura general

```
                              HOSPIAI
                 Director General (interfaz de mando)
                                │
        ┌───────────────────────┴───────────────────────┐
        │        ORQUESTADOR DE AGENTES (misiones)      │
        │  agenda · ejecuta · registra · reintenta      │
        └───────────────────────┬───────────────────────┘
                                │
   ┌─────────┬─────────┬────────┴────────┬─────────┬─────────┐
   │ D1      │ D2      │ D3              │ D4      │ D5–D6   │
   │ Gestión │ Intelig.│ Inteligencia    │ Intelig.│ Intelig.│
   │ Docum.  │ Clínica │ Administrativa  │ Financ. │ Oper/Ger│
   └────┬────┴────┬────┴────────┬────────┴────┬────┴────┬────┘
        │         │             │             │         │
        └─────────┴──────┬──────┴─────────────┴─────────┘
                         │
        ┌────────────────┴─────────────────┐
        │   EXPEDIENTE DIGITAL (data/…db)  │  ← modelo de datos + grafo
        │   CATÁLOGO INSTITUCIONAL (JSON)  │  ← entidades, contratos, siglas
        │   MOTOR DE REGLAS (JSON)         │  ← requisitos con fuente normativa
        └──────────────────────────────────┘
```

Tres piezas transversales sostienen a todos los dominios: el **Expediente
Digital** (§4), el **Catálogo Institucional** (§5) y el **Motor de Reglas**
(§6). El **Orquestador** (§8) ejecuta agentes sobre esas piezas. El **Grafo de
Conocimiento** (§7) es la vista relacionada del expediente que permite
preguntas gerenciales.

---

## 3. Los seis dominios y sus agentes

Cada dominio agrupa agentes con un mismo tipo de inteligencia. Un agente = un
módulo con contrato claro (§8.2). Se listan los agentes fundacionales; la
plataforma admite añadir más sin tocar los existentes.

### D1 · Gestión Documental Inteligente
*"Que ningún documento se pierda, se dañe o se duplique sin que lo sepamos."*

| Agente | Función | Estado |
|---|---|---|
| `explorador-servidor` | Recorre los shares, detecta expedientes nuevos/cambiados | ✅ existe (descubrimiento del radicador) — falta vigilancia programada |
| `analizador-ruta` | Ruta → año, mes, entidad, **responsable**, lote, factura | ✅ existe parcial — falta responsable/lote |
| `inventario-documental` | Tipifica cada archivo (diccionario ADRES + institucional) | ✅ existe |
| `calidad-archivos` | PDF dañados, 0 bytes, duplicados por contenido, páginas | 🔶 parcial |
| `foliacion-metadatos` | Orden documental, versiones, huérfanos, metadatos | 🔜 |
| `propuesta-renombre` | *Propone* nombres estándar (no aplica: solo lectura) | 🔜 |

### D2 · Inteligencia Clínica
*"Entender la atención, no solo el archivo."*

| Agente | Función | Estado |
|---|---|---|
| `lector-rips` | Servicios de la atención (consulta, urgencias, cirugía…) | ✅ existe |
| `lector-fev` | Factura electrónica: pagador, valores, CUFE | ✅ existe |
| `lector-ocr` | Contenido de PDFs: paciente, fechas, firmas, médico | 🔜 (el Motor de Glosas ya lee documentos con IA — se reutiliza) |
| `coherencia-clinica` | ¿La historia soporta lo facturado? (cirugía ⇒ DQX+RAN+consentimiento…) | 🔶 parcial (reglas por servicio) — falta contenido |
| `identidad-paciente` | Mismo paciente en todos los soportes | 🔜 (necesita OCR) |

### D3 · Inteligencia Administrativa
*"Responder POR QUÉ una factura no puede radicarse, con norma y contrato."*

| Agente | Función | Estado |
|---|---|---|
| `resolutor-entidad` | Identifica el pagador (catálogo + razón social del FEV) | ✅ existe (25+ entidades) |
| `auditor-completitud` | Cruza inventario vs. reglas del pagador/servicio → falta X | ✅ existe |
| `cruce-soportes` | Busca en los shares clínicos lo que falta y lo anexa al diagnóstico | ✅ existe (6.328 facturas completadas en el lote real) |
| `dictamen-radicabilidad` | Veredicto por factura: LISTA / qué falta / norma que aplica | ✅ existe (estados + ficha del explorador) — falta citar norma por regla |
| `clasificador-radicacion` | Tipo: inicial, corrección, respuesta a devolución/glosa, re-radicación | 🔜 |

### D4 · Inteligencia Financiera
*"La plata: cuánto hay listo, radicado, glosado, pagado y en riesgo."*

| Agente | Función | Estado |
|---|---|---|
| `tablero-cartera` | Radicado/glosado/pagado/saldo por EPS, aging, alertas +90 | ✅ existe |
| `proyector-recaudo` | Proyección de recaudo y riesgo de no pago por pagador | 🔜 (necesita histórico en el expediente) |
| `radicador-portales` | Cargue y verificación en plataformas de las EPS | 🔴 requiere decisión gerencia/TI (credenciales, marco legal) |
| `gestor-devoluciones` | Registro y seguimiento de devoluciones/glosas por causa | 🔜 |

### D5 · Inteligencia Operacional
*"Medir el proceso: personas, tiempos, cuellos de botella."*

| Agente | Función | Estado |
|---|---|---|
| `productividad` | Facturas y valor por responsable (Karin, Liliana…) | 🔜 (sale del `analizador-ruta`) |
| `tiempos-proceso` | Días entre atención → escaneo → completa → radicada | 🔜 (necesita expediente con fechas) |
| `errores-repetitivos` | Patrones: qué documento falta más, por EPS y por equipo | 🔶 (el resumen ya cuenta códigos faltantes; falta persistirlo) |

### D6 · Inteligencia Gerencial
*"De asistente a asesor: recomendaciones con evidencia."*

| Agente | Función | Estado |
|---|---|---|
| `informes-ejecutivos` | Informes de impacto para gerencia | ✅ existe (informe 42%→49%) |
| `recomendador` | "El 37% de devoluciones de ASMET son por RAN incompleto ⇒ reforzar revisión" | 🔜 (consulta el grafo, §7) |
| `alertas-preventivas` | Vencimientos de plazos de radicación por contrato | 🔜 (necesita plazos en el catálogo) |

---

## 4. El Expediente Digital (modelo de datos)

Corazón de la plataforma: una base de datos local (`data/hospiai.db`, SQLite —
cero instalación, un solo archivo, respaldable) donde cada factura es un
**expediente** que acumula la historia completa. Los reportes CSV/XLSX no
desaparecen: pasan a ser *vistas exportadas* del expediente.

**Entidades y relaciones (este modelo ES el esquema del grafo):**

```
PAGADOR ──1:N── CONTRATO ──1:N── REGLA
   │
   └──1:N── EXPEDIENTE (factura) ──N:1── RESPONSABLE (funcionario)
                │ │ │
                │ │ └──N:1── LOTE (envío ENV-…)
                │ │
                │ └──1:N── DOCUMENTO (cada soporte: tipo, ruta, hash, estado)
                │
                ├──1:1── ATENCION (paciente, servicios del RIPS, fechas)
                ├──1:N── HALLAZGO (agente, regla, criticidad, evidencia, fecha)
                ├──1:N── EVENTO (creado, completado, radicado, devuelto,
                │                glosado, pagado — con fecha y fuente)
                └──1:N── RADICACION (nº radicado, plataforma, comprobante)
                              └──1:N── GLOSA / DEVOLUCION (causa, valor, estado)
                                            └──1:N── PAGO (fecha, valor)
```

**Tablas mínimas v1:** `pagadores`, `contratos`, `reglas`, `expedientes`,
`documentos`, `atenciones`, `hallazgos`, `eventos`, `radicaciones`,
`glosas_devoluciones`, `pagos`, `responsables`, `lotes`, `corridas` (misiones
del orquestador).

Claves de diseño:
- `expedientes.factura_norm` es la clave de cruce universal (misma
  normalización que hoy: HUS0000487523 ≡ 487523).
- `documentos.hash` (SHA-256) detecta duplicados de contenido y da integridad.
- `hallazgos` nunca se borran: se marcan resueltos (auditoría trazable).
- `eventos` es la línea de tiempo que alimenta D5 (tiempos de proceso).

---

## 5. El Catálogo Institucional

Todo el conocimiento **configurable** vive en archivos versionados en `data/`
(hoy ya existe `perfiles_radicacion.json` con 25+ entidades — se extiende, no
se reemplaza):

1. **`perfiles_radicacion.json` → ficha por pagador:** nombre, NIT, alias,
   código EPS, régimen, canal/plataforma de radicación, y ahora también:
   **plazos** (días para radicar), **periodicidad** (diaria/semanal/mensual),
   **responsable del hospital**, modalidad de contratación y manual tarifario.
2. **Diccionario institucional de siglas:** el oficial ADRES (Res. 2284/2023)
   ya está en el motor (`CODIGOS_SOPORTE`). Se añade la capa institucional
   *validada por el área* (⚠ pendiente: confirmar usos internos — p. ej. CRC,
   HAM tienen significado distinto en el borrador interno vs. el oficial).
3. **Estructura documental estándar:** convenciones de carpetas y nombres del
   hospital (año/mes/entidad/funcionario/lote/factura) — ya aprendida por el
   `analizador-ruta`; se documenta aquí para que sea contrato, no costumbre.

---

## 6. El Motor de Reglas

Las exigencias dejan de estar en el código y pasan a ser **datos declarativos**
(`data/reglas_radicacion.json`), para que el área pueda mantenerlas sin
programar. El motor actual (soportes por servicio + equivalencias + extras por
entidad) ya funciona así en embrión; se formaliza el esquema:

```json
{
  "id": "R-HOSP-EPI-001",
  "ambito": {"servicio": "hospitalizacion"},
  "exige": ["EPI"],
  "equivalentes": {"EPI": ["EPI", "HEV"]},
  "criticidad": "BLOQUEA_RADICACION",
  "fuente": "Res. 2284/2023, art. …",
  "vigencia_desde": "2023-01-01",
  "nota": "La epicrisis puede venir dentro de la historia clínica (HEV)."
}
```

- **Ámbitos:** por servicio (consulta/urgencias/cirugía…), por pagador, por
  contrato, o combinados. Gana la regla más específica.
- **Criticidad:** `BLOQUEA_RADICACION` (falta obligatoria) · `REVISAR`
  (esperado según servicio) · `ADVERTENCIA` (calidad).
- **Fuente:** norma o cláusula contractual — es lo que permite al
  `dictamen-radicabilidad` responder "¿qué norma aplica?" y al hallazgo citar
  su sustento.
- Cada corrida registra qué **versión** de reglas usó (reproducibilidad).

---

## 7. El Grafo de Conocimiento

No es una base aparte: es **el mismo Expediente Digital consultado por sus
relaciones**, más las agregaciones que aprenden del histórico. Con las tablas
del §4, estas preguntas son consultas directas:

- *"Devoluciones de ASMET por falta de registro anestésico, últimos 6 meses"* →
  `glosas_devoluciones` × `expedientes` × `hallazgos` (causa=RAN).
- *"¿Qué funcionario tiene menos devoluciones?"* → `responsables` × `eventos`.
- *"¿Qué documento genera más rechazos por EPS?"* → `hallazgos` × `pagadores`.
- *"¿Qué contratos tienen mayor riesgo de glosa?"* → tasa histórica de glosa
  por `contrato`.

El **aprendizaje continuo** (punto 14 de la especificación) se materializa así:
cada devolución/glosa registrada se clasifica por causa; el `recomendador` (D6)
detecta patrones (frecuencia × valor × tendencia) y propone acciones; si un
patrón se confirma, se convierte en **regla nueva** del §6 (con fuente "lección
aprendida + referencia del caso"). Así el sistema se endurece con cada golpe,
sin reentrenar nada opaco: el conocimiento queda legible y auditable.

Si el volumen lo exige más adelante, el mismo esquema se migra a un motor de
grafos dedicado sin cambiar a los agentes (ellos hablan con el expediente, no
con el almacenamiento).

---

## 8. El Orquestador de Agentes

### 8.1 Qué hace
Ejecuta **misiones**: secuencias de agentes con un objetivo (p. ej. *"auditoría
diaria del lote de junio"*). Por cada misión registra en `corridas`: qué
agentes corrieron, con qué versión de reglas/catálogo, cuánto tardaron, qué
hallazgos produjeron y qué quedó pendiente. Reintenta lo transitorio (red),
reporta lo permanente.

**v1 pragmática:** un orquestador de procesos local (`tools/hospiai.py`) con
misiones definidas en JSON, agendado con el Programador de tareas de Windows
(corrida nocturna). Sin servidores nuevos ni dependencias de infraestructura.
La arquitectura no cambia si mañana se muda a un servidor del hospital: cambia
solo *dónde* corre.

### 8.2 Contrato de agente (lo que hace a la plataforma extensible)
Todo agente cumple el mismo contrato:

- **Entrada:** el Expediente Digital + catálogo + reglas (nunca estado oculto).
- **Salida:** hallazgos/eventos/documentos escritos al expediente, con su firma
  (`agente`, `version`, `fecha`, `evidencia`).
- **Idempotente:** correrlo dos veces no duplica nada (como hoy: el cruce
  deduplica por ruta).
- **Solo lectura sobre los shares.** Escribe únicamente en `data/` y reportes.
- **Aislado:** falla sin tumbar la misión; el orquestador registra y sigue.
- **Declarado:** se registra en `data/agentes.json` (nombre, dominio, qué lee,
  qué produce) — el Director General lista ahí qué sabe hacer la plataforma.

### 8.3 El Director General
La interfaz de mando (evolución del explorador + tablero): un panel donde se ve
el estado de las misiones, los expedientes por estado, los hallazgos por
criticidad, y desde donde el humano aprueba las acciones con efecto externo.
v1: los HTML actuales leyendo del expediente. Futuro: panel unificado.

---

## 9. Hoja de ruta evolutiva

> **Revisión de arquitectura (22-jul-2026).** Tras la entrega de la Fase 1 se
> hizo una revisión formal que reordenó la hoja de ruta: antes del OCR se
> construye la **capa cognitiva** (catálogo, vigencias, evidencias, grafo,
> supervisor), porque el OCR debe escribir SOBRE esa capa, no antes que ella.
> Veredictos: **adoptado** → catálogo institucional ampliado, versionamiento con
> vigencias, motor de evidencias (evidencia + confianza por hallazgo), vistas
> del grafo + export, memoria institucional en glosas (solución/aprendizaje).
> **Adaptado** → el grafo vive como vistas/export del expediente; un motor de
> grafos dedicado solo si el volumen lo exige (los agentes no cambiarían).
> El "bus de eventos" v1 ES la tabla `eventos` + `corridas` (un solo equipo, un
> solo nodo: un bus real sería sobre-ingeniería hoy). **Diferido con criterio**
> → agente conversacional (requiere decidir integración con la IA del Motor de
> Glosas), predicción ML de glosas (requiere ≥1 ciclo de glosas históricas
> cargadas en la base — primero datos, después modelos).

| Fase | Entrega | Contenido |
|---|---|---|
| **0 · Hecha** | Motor probado con lote real | Radicador + cruce (42%→49%), explorador, tablero, diagnóstico |
| **1 · Hecha** | El Expediente Digital | `hospiai.db` + esquema §4; el radicador persiste cada corrida (CSV intacto); reglas declarativas §6; `analizador-ruta` completo (responsable + lote); consola/panel; corrida diaria + guía |
| **1.5 · Arquitectura Cognitiva** | **Entrega 1 (hecha):** vigencias normativas (la regla correcta según la fecha), catálogo institucional (NIT/régimen/plazo/periodicidad → `pagadores`+`contratos`), Motor de Evidencias v1 (evidencia + confianza por hallazgo, vista `vw_evidencias`, comando `evidencia`), grafo consultable (vistas + `grafo` export JSON), memoria de glosas (solución/aprendizaje/tiempo). **Entrega 2:** orquestador-supervisor (misiones, quién corrió/falló/reintenta), diccionario documental institucional validado |
| **2 · Dominios D1/D5** | Calidad y operación | `calidad-archivos` (dañados/vacíos/duplicados), `tiempos-proceso` |
| **3 · Dominio D2** | Inteligencia clínica | `lector-ocr` (reutilizando la lectura de documentos del Motor de Glosas) escribiendo hallazgos con confianza < 1.0 sobre el Motor de Evidencias, `coherencia-clinica`, `identidad-paciente` |
| **4 · Dominios D4/D6** | Cartera y gerencia | `gestor-devoluciones` + histórico → grafo activo → `recomendador`, `alertas-preventivas` (plazos del catálogo) y agente conversacional; con histórico suficiente, predicción de glosas |
| **5 · Portales** | Radicación automática | `radicador-portales` con human-in-the-loop — **solo** tras autorización de gerencia/TI y análisis legal |

Regla de oro de la hoja de ruta: **cada fase entrega valor usable por sí sola**
(como hasta ahora: cada semana salió algo que el área ya usa).

---

## 10. Decisiones que corresponden al hospital (no al código)

1. **Radicación automática en portales** (Fase 5): credenciales, responsabilidad
   legal, políticas de TI. Sin esto, HOSPIAI llega hasta "todo listo y
   verificado para radicar en un clic humano".
2. **Diccionario institucional**: validar los significados internos de las
   siglas con el área (vs. el oficial ADRES).
3. **Plazos y periodicidad por contrato**: el área debe suministrar los
   contratos o sus fichas para cargar el catálogo.
4. **Dónde corre**: v1 en el equipo del área (cero infraestructura); si TI
   asigna un servidor, la plataforma se muda sin rediseño.

---

*Documento vivo: se actualiza al ritmo de la BITACORA.md. Cambios de
arquitectura se registran aquí con fecha.*
