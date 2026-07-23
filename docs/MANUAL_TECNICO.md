# Manual Técnico — HOSPIAI v1.0

**ESE HUS · Cuentas Médicas y Cartera**
Documento para quien mantenga o extienda la plataforma. La visión y la hoja de
ruta completas están en [`ARQUITECTURA_HOSPIAI.md`](ARQUITECTURA_HOSPIAI.md);
este manual es la referencia operativa del código.

---

## 1. Qué es HOSPIAI

Una plataforma de agentes especializados sobre un **Expediente Digital** (SQLite)
que audita las facturas del hospital antes de radicarlas, explica cada dictamen
con su norma, recomienda acciones por retorno económico y llega cada mañana con
las decisiones del día. **Todo es solo lectura sobre los servidores del hospital.**

- **Lenguaje:** Python 3.11+ (probado hasta 3.14), **solo librería estándar**
  (`openpyxl` es opcional, únicamente para el XLSX). Sin servidores, sin nube.
- **Datos:** una base local `data/hospiai.db` (SQLite, modo WAL). Cero
  infraestructura: corre en el equipo del área.
- **Código y comentarios:** en español, siguiendo el estilo del archivo.

---

## 2. Instalación

```powershell
# 1. Clonar (una vez)
git clone <url-del-repo> C:\Users\cartera\motor-glosas-hus
cd C:\Users\cartera\motor-glosas-hus

# 2. Python 3.11+ (la 3.14 del equipo sirve). Opcional para XLSX:
py -m pip install openpyxl

# 3. Verificar
py tools\hospiai.py init          # crea la base vacía
py -m pytest tests/test_tools/ -q # 251 pruebas en verde
```

No hay más dependencias. El resto es librería estándar.

---

## 3. Mapa de módulos (`tools/`)

| Módulo | Responsabilidad |
|---|---|
| `radicar_facturacion.py` | El **motor**: recorre los shares, clasifica soportes, cruza, dicta LISTA / REVISAR / FALTAN, persiste cada corrida en el Expediente. |
| `hospiai_db.py` | Esquema y apertura del Expediente Digital; migraciones suaves; vistas; `persistir_corrida()`. |
| `hospiai_sdk.py` | Contrato único de agente (`Agente`, `ResultadoAgente`), cola de misiones, `RegistroAgentes`. |
| `hospiai_agentes.py` | Agentes de referencia (AG002/003/011) y `registro_con_implementaciones()` que enlaza TODAS las clases. |
| `hospiai_indexador.py` | **AG001 / DIS**: índice permanente por servidor (`data/indices/indice_*.db`), incremental, búsqueda en ms. |
| `hospiai_documento.py` | DIS: fingerprint de PDF, calidad A–D/X, duplicados, `document_profile`; AG016–AG018. |
| `hospiai_semantica.py` | Motor semántico sobre ontologías (`data/ontologias/`); AG011. |
| `hospiai_supervisor.py` | **AG010**: Scheduler + Dispatcher + RetryManager + PolicyEngine + MissionLogger. |
| `hospiai_directores.py` | AG012–AG015: informe gerencial, tareas del día, respuestas de caja, aprendizaje. |
| `hospiai_conocimiento.py` | **Fase 2.2**: Memoria Institucional + AG019–AG023 + `recomendar` / `simular`. |
| `hospiai_operacion.py` | **Fase 3**: AG024–AG028 + tabla `indicadores` (`plan`, `oportunidades`, ficha, gemelo, mejora). |
| `hospiai_comando.py` | **Fase 4**: HOS + AG029–AG033 (`iniciar-dia`, `preguntar`, carga, alertas, proyección). |
| `hospiai_gobernanza.py` | Registro de artefactos con huella (deriva), golden dataset, compatibilidad, salud. |
| `hospiai_api.py` | Capa de servicios + servidor HTTP local de solo lectura (contrato para HIS/ERP/BI). |
| `hospiai_dsl.py` | Compilador del lenguaje de reglas (`.hospiai` → JSON del motor). |
| `hospiai.py` | Consola principal (init/resumen/panel/recomendar/simular/plan/oportunidades/iniciar-dia/preguntar…). |
| `hospiai_panel_ejecutivo.py` | Panel HTML que consume **solo la API** (abre con la "situación del día" y el HOS). |
| `corrida_diaria.ps1` | Orquesta el día: índice → radicador → directores → curaduría → indicadores → paneles → "buenos días" (+ mejora los viernes). |

---

## 4. El Expediente Digital (esquema en `hospiai_db.py`)

Tablas centrales: `corridas`, `pagadores`, `contratos`, `reglas` (+vigencias),
`expedientes`, `documentos`, `hallazgos` (evidencia + confianza), `eventos`,
`radicaciones`, `glosas`, `pagos`, `decisiones` (Decision Records),
`conocimiento` (Memoria Institucional), `indicadores`, `misiones`.

Principios:
- **Migración suave:** al abrir la base se aplican `CREATE TABLE IF NOT EXISTS` +
  migraciones de columnas. Abrir una base vieja con código nuevo **agrega solas**
  las tablas/columnas que falten, sin perder datos.
- **Toda corrida queda registrada** con las versiones exactas de motor y reglas
  (reproducibilidad y auditoría).

---

## 5. Los 33 agentes (Registro Central `data/agentes.json`)

El Supervisor y la consola consumen **este registro**, nunca clases concretas.

| Dominio | Agentes |
|---|---|
| Documental (D1 / DIS) | AG001 Indexador, AG002 AnalizadorRuta, AG003 Clasificador, AG016 DocumentCurator, AG017 StorageOptimizer, AG018 Ingesta |
| Clínico (D2) | AG004 OCR *(planeado, Fase 3 de la hoja de ruta)* |
| Administrativo/Auditoría (D3) | AG005 ResolutorEntidad, AG006 AuditorCompletitud, AG007 CruceSoportes, AG008 Persistencia |
| Conocimiento | AG011 Semántico, AG019 KnowledgeCurator, AG020 PatternDiscovery, AG021 Recommendation, AG022 RootCause, AG023 ProcessMiner |
| Operación (Fase 3) | AG024 PlanRecuperación, AG025 CorrecciónMasiva, AG026 Contratos, AG027 GemeloEPS, AG028 MejoraContinua |
| Comando (Fase 4) | AG029 DailyOrchestrator, AG030 WorkloadBalancer, AG031 EarlyWarning, AG032 KpiForecaster, AG033 ExecutiveCopilot |
| Orquestación / Gerencia | AG009 PanelDirector, AG010 Supervisor, AG012–AG015 Directores |

---

## 6. Reglas de integridad (no negociables)

Se cumplen en el código y se verifican con pruebas automáticas:

1. **Solo lectura** sobre los shares. Nunca `--armar`/`--mover` salvo pedido
   explícito. La radicación en portales (RPA) está retenida por política hasta
   autorización de gerencia/TI.
2. **Nada de números inventados.** Toda probabilidad se calcula (regla vigente o
   frecuencia histórica con casos). Lo que no se puede medir queda en NULL con su
   razón (p. ej. `dpi`/legibilidad hasta el OCR; devoluciones/recaudo hasta cargar
   historial). El HOS excluye los componentes sin datos y se re-pondera.
3. **Ningún agente aprende solo.** Todo aprendizaje entra como CANDIDATO a la
   Memoria Institucional y lo valida el Knowledge Curator (AG019) antes de que
   otro agente lo use.
4. **Ningún agente lee un PDF directamente.** La única fuente documental es el
   Document Profile (DIS).
5. **Regla de oro (Fase 3+):** ningún agente nuevo sin responder por escrito las 5
   preguntas (problema, dinero, horas, indicador, medición) en su ficha
   (`justificacion_operativa`). Hay una prueba que lo exige.
6. **Datos reales nunca al repositorio.** Solo casos sintéticos en el golden
   dataset; las bases reales viven local (`data/` está en `.gitignore`).

---

## 7. Pruebas y calidad

```powershell
py -m pytest tests/test_tools/ -q      # 251 pruebas de las herramientas
ruff check --select F,W6               # linter
ruff format --check                    # formato
```

- El golden dataset (`data/golden/casos.json`, 10 casos sintéticos) corre el motor
  real y compara resultados: red de regresión funcional.
- Cada agente se valida en vivo contra el contrato del SDK (compatibilidad).
- **Correr las pruebas y el linter antes de dar por terminado cualquier cambio.**

---

## 8. Cómo extender (sin romper la integridad)

1. ¿El cambio es un agente nuevo? Respondé primero las 5 preguntas de la regla de
   oro; si no aportan indicador medible, no se construye.
2. Implementá sobre el SDK: subclase de `Agente`, solo `_trabajar()`; devolvé el
   `ResultadoAgente` estándar.
3. Registralo en `data/agentes.json` **y** en `registro_con_implementaciones()`.
4. Si añade reglas de negocio, van a `data/*.json` con su fuente/vigencia —
   nunca "hardcodeadas".
5. Escribí pruebas en `tests/test_tools/`; corré pytest + ruff.
6. Actualizá `BITACORA.md` (en español, para el auditor) y, si cambia la
   arquitectura, `ARQUITECTURA_HOSPIAI.md`.

---

## 9. API interna (contrato estable, solo lectura, local)

```powershell
py tools\hospiai_api.py servir --puerto 8765
```

Rutas: `/salud /agentes /capacidades /misiones /expedientes/{f} /decisiones/{f}
/evidencias/{f} /ontologia/{c} /informe /caja /tareas /recomendaciones/{f}
/simulaciones /conocimiento /plan/{f} /oportunidades /indicadores /fichas
/gemelo/{eps} /mejora /hos /situacion /iniciar-dia /carga /alertas /proyeccion
/preguntar?q=`. Es el contrato para integrar HIS/ERP/BI el día que se necesite.
