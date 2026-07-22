# Guía: `motor_decision_dispensario.py` — Motor de Decisión (el cerebro)

No es jurídico ni IA: son **reglas de negocio**. Toma el expediente probatorio
(hechos probados + contradicciones + contrato + cartera) y, por cada glosa,
**decide**. Así el Módulo Jurídico solo **fundamenta** la decisión con la norma,
y el de Argumentación solo la **redacta** — separación de responsabilidades
limpia, transparente y auditable.

## Qué calcula por cada glosa

- **Defendibilidad (0–100 %)** — qué tan sostenible es el cobro con lo que hay
  (promedio de la confianza de los hechos probados).
- **Riesgos multidimensionales** — `probatorio`, `documental`, `contractual`,
  `tarifario`, `financiero`, `jurídico` (cada uno ALTO/MEDIO/BAJO **con su razón**).
  Ej.: *Probatorio ALTO → "No se probó: la prestación fue ejecutada"*.
- **Documentos requeridos** (matriz de precedencia) y los que **faltan** — el
  sistema sabe QUÉ buscar, no busca todo.
- **Acción recomendada** — una de:
  `SOLICITAR_LEVANTAMIENTO` · `ACEPTAR_PARCIAL` · `SOLICITAR_SOPORTE` ·
  `ESCALAR` · `CONCILIAR` (+ `COBRO_JURIDICO` a futuro).
- **Prioridad** — por el valor objetado.

## Cómo decide (regla de negocio, resumida)

| Situación | Acción |
|---|---|
| Contradicción grave (paciente ≠ RIPS, factura no en cartera) | **ESCALAR** |
| Defendibilidad ≥ 85 % | **SOLICITAR_LEVANTAMIENTO** |
| 60–85 % con documento faltante | **SOLICITAR_SOPORTE** |
| 60–85 % completo | **ACEPTAR_PARCIAL** |
| 40–60 % | **SOLICITAR_SOPORTE** |
| < 40 % | **CONCILIAR** |

## Uso

```powershell
# Requiere expedientes_probatorios.json (salida del Módulo 3.5)
py tools\motor_decision_dispensario.py `
  --expedientes "D:\...\expedientes_probatorios.json" `
  --salida      "D:\...\expedientes_decision.json" `
  --reporte     "D:\...\DECISION.xlsx"
```

## Qué entrega

- `expedientes_decision.json`: cada glosa gana el bloque `decision`
  (defendibilidad, riesgos, documentos_faltantes, decision, prioridad, motivo);
  cada expediente gana `defendibilidad_promedio` y `decision_dominante`. Incluye
  `resumen_decision` (cuántas glosas por cada acción).
- `DECISION.xlsx` (opcional): una fila por glosa con defendibilidad %, decisión
  (coloreada), prioridad, riesgos y qué falta.

## Dónde encaja

```
expedientes_probatorios.json  (Mod 3.5)
              │
              ▼
   motor_decision  (el cerebro, este)  →  expedientes_decision.json
              │
              ▼
   Mod 4 (Jurídico: fundamenta) → Mod 5 (Argumentación: redacta) → Oficios → Dashboard
```

Tests: `pytest tests/test_tools/test_motor_decision_dispensario.py`
