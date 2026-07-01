# Registro de cambios

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
