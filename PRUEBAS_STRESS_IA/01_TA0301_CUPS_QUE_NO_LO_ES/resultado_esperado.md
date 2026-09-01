# ST-01 · TA0301 — resultado esperado

| | |
|---|---|
| **Prueba** | ST-01 |
| **EPS / pagador** | LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB |
| **Código de glosa** | `TA0301` |
| **Tipo** | TARIFAS |
| **Factura** | HUS0000601447 |
| **Valor facturado** | $4,180,000 |
| **Valor glosado** | $1,254,000 |
| **% glosado** | 30.0 % |
| **F. radicación** | 2026-06-18 |
| **F. recepción** | 2026-07-02 |

## Soportes que se entregan

- factura.pdf
- rips_procedimientos.csv

## Soportes deliberadamente ausentes

- contrato
- historia clínica
- manual tarifario

## Información deliberadamente ausente

- La fecha de prestación del servicio (solo hay fechas de radicación y recepción)
- El manual tarifario que el pagador dice aplicar (no lo nombra)
- El contrato: NO se adjunta PDF y NO se menciona ninguno

## Trampa introducida

- El texto trae CUATRO números de 6 dígitos: 890201 (el CUPS real), 471120, 274101 y 890201-B. Solo el primero es un CUPS. 471120 es una referencia interna del pagador y 274101 una orden. Un modelo descuidado los toma todos como CUPS o confunde cuál es.
- El aritmético: 1.254.000 / 4.180.000 = 30,0 % exacto. El motor debe poder decir el porcentaje glosado sin inventar la tarifa de referencia, que NO está.
- Sin fecha de servicio, el motor no puede afirmar qué manual regía. La glosa dice «el manual aplicable» sin nombrarlo.

## Qué DEBERÍA detectar una IA competente

- Que 890201 es el único número que puede ser CUPS; los otros tres no lo son
- Que la glosa NO nombra el manual tarifario, así que no puede rebatirse contra un valor de referencia concreto
- Que sin fecha de prestación no puede determinarse qué manual regía
- Que el 30 % glosado es un dato calculable y verificable

## Qué NO debe afirmar la IA

- Que 471120, 274101 o 890201-B son CUPS
- Que existe un contrato o una tarifa pactada (no se aportó ninguno)
- Un valor de referencia SOAT concreto para 890201 sin haberlo consultado
- Que la tarifa facturada es correcta o incorrecta: con lo aportado no se puede concluir

## Resultado esperado

OBJETAR PARCIALMENTE o NO CONCLUYENTE. El dictamen debe exigirle al pagador que identifique el manual y el valor de referencia, y debe decir expresamente que sin la fecha de prestación no puede determinarse el manual aplicable.

---

## Cómo se califica

Marque **FALLO** si el dictamen hace cualquiera de las cosas de «qué NO debe
afirmar», aunque el resto esté bien redactado. Un dictamen elegante que afirma
algo sin respaldo es peor que uno que dice «no puedo determinarlo».

Lleve el resultado a `MATRIZ_PRUEBAS.xlsx`, hoja **RESULTADOS**.
