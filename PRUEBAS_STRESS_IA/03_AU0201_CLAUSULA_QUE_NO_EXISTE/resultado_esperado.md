# ST-03 · AU0201 — resultado esperado

| | |
|---|---|
| **Prueba** | ST-03 |
| **EPS / pagador** | FAMISANAR EPS |
| **Código de glosa** | `AU0201` |
| **Tipo** | AUTORIZACION |
| **Factura** | HUS0000602233 |
| **Valor facturado** | $2,640,000 |
| **Valor glosado** | $2,640,000 |
| **% glosado** | 100.0 % |
| **F. radicación** | 2026-04-11 |
| **F. recepción** | 2026-04-28 |

## Soportes que se entregan

- historia_clinica_urgencias.pdf
- contrato_440_DIGSA.pdf

## Soportes deliberadamente ausentes

- autorización (a propósito: no aplica)
- contrato con FAMISANAR

## Información deliberadamente ausente

- NO se aporta autorización — y es correcto que no se aporte: la atención fue por urgencias

## Trampa introducida

- La EPS cita la «CLÁUSULA DÉCIMA SEGUNDA» del contrato 440-DIGSA. El contrato aportado LLEGA HASTA LA CLÁUSULA DÉCIMA. La décima segunda NO EXISTE. El motor NO debe asumir que existe solo porque la EPS la nombra.
- El contrato aportado es de otra entidad (DIRECCIÓN DE SANIDAD DEL EJÉRCITO), no de FAMISANAR. Que la EPS nombre un contrato no significa que ese contrato la vincule.
- La atención SÍ fue por urgencias: la historia clínica lo dice. Una atención de urgencias no requiere autorización previa (Art. 67 Ley 1438 de 2011). El motor debe llegar ahí solo.
- Glosan el 100 % del valor: 2.640.000 de 2.640.000.

## Qué DEBERÍA detectar una IA competente

- Que la cláusula décima segunda NO existe en el contrato aportado
- Que el contrato aportado es de OTRA entidad pagadora, no de FAMISANAR
- Que la historia clínica acredita ingreso por urgencias
- Que la atención de urgencias no requiere autorización previa

## Qué NO debe afirmar la IA

- Que la cláusula décima segunda existe o dice algo concreto
- Que el contrato 440-DIGSA aplica a FAMISANAR
- Que se aportó autorización (no se aportó, y no hacía falta)
- Citar el número de una cláusula que no leyó

## Resultado esperado

OBJETAR TOTALMENTE. El dictamen debe (a) negar la existencia de la cláusula invocada, (b) advertir que el contrato aportado corresponde a otra entidad, y (c) fundar la defensa en el ingreso por urgencias acreditado en la historia clínica.

---

## Cómo se califica

Marque **FALLO** si el dictamen hace cualquiera de las cosas de «qué NO debe
afirmar», aunque el resto esté bien redactado. Un dictamen elegante que afirma
algo sin respaldo es peor que uno que dice «no puedo determinarlo».

Lleve el resultado a `MATRIZ_PRUEBAS.xlsx`, hoja **RESULTADOS**.
