# Acta de Línea Base — HOSPIAI v1.0

**ESE Hospital Universitario de Santander · Cuentas Médicas y Cartera**
**Fecha de medición:** 23 de julio de 2026 · **Corrida:** #2 (08:37)
**Motor:** radicador 1.0-fase1 · reglas v1.0 · **Alcance:** lote de facturación electrónica junio 2026

> Este documento fija el **punto de partida medido** de la operación el día en que
> HOSPIAI entró en producción. Todo el impacto futuro (más facturas LISTAS, dinero
> recuperado, reducción de tiempos) se medirá **contra estas cifras**. Son datos
> **agregados**; ningún dato de paciente o factura individual sale de este acta.

---

## 1. Resultado de la primera corrida real

| Indicador | Valor día 0 |
|---|---|
| Facturas auditadas | **12.523** |
| Valor total auditado | **$ 49.293.781.977** |
| **Facturas LISTAS para radicar** | **7.840 (62,6 %)** |
| **Valor LISTO para radicar** | **$ 38.646.727.859** |
| Facturas detenidas (no listas) | 4.683 (37,4 %) |
| Valor detenido | $ 10.647.054.118 |
| Soportes anexados automáticamente por el cruce | **10.823 facturas** |

**Lectura:** el 63 % del lote ya está listo para radicar y el motor cruzó soportes
por su cuenta en 10.823 facturas. La operación arranca con **$38.646 millones
radicables** identificados y verificados.

---

## 2. Por qué está detenido lo que está detenido

| Estado | Facturas | Valor |
|---|---|---|
| REVISAR_TIPIFICACIÓN | 3.697 | $ 9.121.562.836 |
| FALTAN_SOPORTES | 354 | $ 951.732.429 |
| ENTIDAD_NO_RESUELTA | 29 | $ 551.708.853 |
| PARTICULAR (paciente) | 484 | $ 22.050.000 |
| SIN_RIPS | 119 | $ 0 |

---

## 3. La palanca del mes (el hallazgo grande)

**3.275 facturas — $ 1.255.941.607 — están a UN SOLO soporte clínico (la hoja de
evidencia HEV) de quedar LISTAS.** (En el HUS la epicrisis EPI y la hoja de
urgencias HAU se escanean dentro de la HEV, así que una HEV cubre las tres.)

> **Si se resuelve solo ese grupo, las facturas LISTAS suben de 7.840 (62,6 %) a
> 11.115 (88,8 %).** Eso supera de una vez la meta fijada por la dirección
> (7.840 → 9.000+).

**Paso inmediato pendiente de medir:** de esas 3.275, ¿cuántas HEV **ya están
escaneadas** en los servidores (solo hay que asociarlas, costo $0) y cuántas hay
que escanear? Lo responde exactamente:

```
py tools\hospiai.py oportunidades
```

Ese número — cuánto de los $1.256 millones ya está esperando a que el cruce lo
asocie — es el primer objetivo operativo de la V1.0.

---

## 4. Oportunidades de alto valor por folio

- **OPF (descripción/opción quirúrgica):** 84 facturas que solo esperan OPF valen
  **$ 1.648.373.908**. Pocas facturas, mucha plata: las quirúrgicas grandes rinden
  más por folio y conviene priorizarlas.
- **Entidad no resuelta:** 29 facturas por **$ 551.708.853** detenidas solo porque
  falta el pagador en el catálogo. Es agregar entidades a un archivo de
  configuración — cero escaneo. **Quick-win de mayor retorno por esfuerzo.**

---

## 5. Carga por funcionario (balanceada)

| Responsable | Facturas | % Listas | Pendientes |
|---|---|---|---|
| VANESSA | 3.832 | 65 % | 1.347 |
| KARIN | 3.555 | 69 % | 1.090 |
| LILIANA | 2.552 | 69 % | 803 |
| SOFIA | 473 | 81 % | 91 |

La carga está pareja (65–69 % entre los tres grandes). **El cuello no es la gente:
es la HEV.** La acción no es redistribuir personal, es conseguir/asociar HEV en
masa.

---

## 6. Top de pagadores

| Pagador | Facturas | Listas | Valor |
|---|---|---|---|
| NUEVA EPS | 5.390 | 4.157 | $ 25.885.706.461 |
| COOSALUD EPS | 3.353 | 1.969 | $ 11.492.281.736 |
| DISPENSARIO MÉDICO BUCARAMANGA | 1.330 | 595 | $ 2.364.473.948 |
| REGIONAL DE ASEGURAMIENTO N° 5 | 691 | 438 | $ 3.957.570.117 |
| FOMAG (Magisterio) | 335 | 297 | $ 738.139.203 |
| FAMISANAR EPS | 295 | 207 | $ 897.557.430 |

COOSALUD es quien más caja frena en proporción (solo 59 % listas): concentra la
palanca de la HEV.

---

## 7. Objetivo de la Entrega 2 (medición de impacto, 2–4 semanas)

Con esta línea base fija, la Entrega 2 medirá — usando la plataforma todos los
días, sin construir nada nuevo:

| Métrica | Día 0 (esta acta) | Meta a medir |
|---|---|---|
| Facturas LISTAS | 7.840 (62,6 %) | 9.000+ (meta dirección) / 11.115 (techo por HEV) |
| Valor LISTO | $ 38.646 millones | + lo que libere el cierre de la HEV |
| Facturas con entidad sin resolver | 29 ($ 551 M) | 0 |
| Hospital Operational Score (HOS) | *se captura con `iniciar-dia`* | evolución semanal |
| Tiempo hasta LISTA | *se mide al segundo ciclo* | reducción |

---

*Acta generada como parte del cierre del Sprint 5 (Puesta en Producción) de
HOSPIAI. Cifras agregadas de la corrida #2 del 23-jul-2026; el detalle por factura
vive en el Expediente Digital local (`data/hospiai.db`) y en el reporte del área,
nunca en este documento.*
