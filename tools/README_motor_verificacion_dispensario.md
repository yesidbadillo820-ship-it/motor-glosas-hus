# Guía: `motor_verificacion_dispensario.py` — Verificación de Evidencia (Módulo 3.5)

**Encontrar texto no es probar un hecho.** Que la historia clínica diga
"paciente remitido a cirugía" no demuestra que *este* procedimiento se realizó.
Este motor, con **reglas deterministas (no IA)**, convierte el expediente en un
**expediente probatorio**: por cada glosa fija los **hechos** que hay que
demostrar y verifica —con la evidencia del Módulo 3 y los soportes presentes—
si cada hecho quedó **probado**, con qué **nivel de confianza** y qué **falta**.

Además corre un **Motor de Contradicciones** que cruza factura / paciente /
CUPS / contrato entre los soportes y avisa inconsistencias **antes** de
responder la glosa.

> Filosofía: las **reglas** resuelven los casos claros; la IA (módulos
> posteriores) solo interviene donde hay interpretación. Todo es auditable.

## Qué hechos exige cada tipo de glosa (ejemplos)

| Familia | Hechos a probar | Con qué documento |
|---|---|---|
| **SOPORTES** | La prestación fue **ordenada** · fue **ejecutada/registrada** | Orden médica / HC · Descripción quirúrgica / Epicrisis / HAM / Lab (+ el CUPS presente) |
| **TARIFAS** | El servicio fue **facturado** · hay **contrato** aplicable | Factura/RIPS · Contrato 287/440 por fecha |
| **CALIDAD / PERTINENCIA** | La prestación glosada está **sustentada** en la HC | HC / Epicrisis / Descripción quirúrgica (**el servicio debe aparecer citado**) |
| **COBERTURA / AUTORIZACIÓN** | Existe **autorización** | Autorización / MIPRES |

Cada hecho: `{hecho, probado, nivel_confianza, evidencia[pág], faltantes[]}`.
La confianza sube si el **código CUPS** aparece en el soporte (evidencia fuerte).

### Existencia ≠ pertinencia (calidad)

Para las glosas de **calidad/pertinencia**, que exista la historia clínica **no
prueba** el hecho: el **servicio glosado tiene que aparecer citado**. La confianza
se gradúa según la evidencia:

- código CUPS localizado (fuerte) → **0.90**
- servicio citado por nombre → **0.75**
- historia clínica presente pero el servicio **no aparece** → **no probado (0.40)**,
  con el faltante *"Referencia del servicio glosado en la historia clínica"*.

Así una glosa de calidad ya **no** se defiende sola con *"existe historia clínica"*.

## Contradicciones que detecta

- La factura **no aparece en la cartera** del HUS.
- El **documento del paciente no coincide** con el RIPS.
- El **CUPS del servicio glosado no está en el RIPS**.
- El RIPS trae **otra factura** (cruce equivocado).
- Contrato 287 **por confirmar** (falta acta de inicio).

## Uso

```powershell
# Requiere expedientes_con_evidencia.json (salida del Módulo 3)
py tools\motor_verificacion_dispensario.py `
  --expedientes "D:\...\expedientes_con_evidencia.json" `
  --salida      "D:\...\expedientes_probatorios.json" `
  --reporte     "D:\...\HECHOS_PROBADOS.xlsx"
```

## Qué entrega

- `expedientes_probatorios.json`: cada glosa gana `hechos_probados`; cada
  expediente gana `alertas` y un flag `defendible` (todos los hechos probados y
  sin alertas). Incluye `resumen_verificacion` (hechos probados / totales,
  alertas, expedientes defendibles).
- `HECHOS_PROBADOS.xlsx` (opcional): hoja **Hechos** (probado sí/no + confianza +
  evidencia + qué falta) y hoja **Alertas**.

## Dónde encaja

```
expedientes_con_evidencia.json  (Mod 3)
              │
              ▼
   motor_verificacion  (Mod 3.5, este)  →  expedientes_probatorios.json
              │
              ▼
     Mod 4 (Jurídico) → Mod 5 (Argumentación, ensambla desde hechos probados)
```

El motor de Argumentación ya **no inventará** una defensa: ensamblará la
conclusión a partir de **hechos previamente demostrados y trazables**.

Tests: `pytest tests/test_tools/test_motor_verificacion_dispensario.py`
