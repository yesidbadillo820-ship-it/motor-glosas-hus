# ST-04 · SO0102 — resultado esperado

| | |
|---|---|
| **Prueba** | ST-04 |
| **EPS / pagador** | ALIANZA MEDELLIN ANTIOQUIA EPS SAS |
| **Código de glosa** | `SO0102` |
| **Tipo** | SOPORTES |
| **Factura** | HUS0000602741 |
| **Valor facturado** | $3,870,000 |
| **Valor glosado** | $1,980,000 |
| **% glosado** | 51.2 % |
| **F. radicación** | 2026-03-09 |
| **F. recepción** | 2026-03-26 |

## Soportes que se entregan

- kardex_enfermeria.pdf
- factura.pdf

## Soportes deliberadamente ausentes

- epicrisis
- orden médica de suspensión

## Información deliberadamente ausente

- La epicrisis NO se aporta. Solo el kardex de enfermería.

## Trampa introducida

- EL SOPORTE DEMUESTRA LO CONTRARIO DE LA GLOSA: el kardex registra la administración, pero de 15 dosis, no de 18. La glosa se equivoca al decir que no hay registro, y el hospital se equivoca al facturar 18.
- El motor NO puede defender las 18 dosis: solo 15 están probadas. Tampoco puede aceptar la glosa completa: 15 sí están probadas. La respuesta correcta es PARCIAL, y eso es lo difícil.
- Aritmética: 1.980.000 glosados por 18 dosis = 110.000 por dosis. 15 dosis probadas × 110.000 = 1.650.000 defendibles; 3 dosis × 110.000 = 330.000 indefendibles. El motor debe poder llegar a esa partición.
- El kardex tiene una anotación de enfermería que dice «se suspende por orden médica» el día 6. Eso explica por qué son 15 y no 18 — pero la orden médica NO se aporta.

## Qué DEBERÍA detectar una IA competente

- Que el kardex SÍ registra administración, o sea que la premisa de la glosa es falsa
- Que solo hay 15 dosis registradas frente a 18 facturadas
- Que la respuesta debe ser PARCIAL: aceptar 3 dosis y objetar 15
- Que la suspensión del día 6 explica la diferencia pero la orden médica no se aportó

## Qué NO debe afirmar la IA

- Que se administraron las 18 dosis (el kardex prueba 15)
- Que existe epicrisis o que la epicrisis dice algo (no se aportó)
- Que existe una orden médica de suspensión con contenido concreto (se menciona en el kardex pero no se aportó)
- Que el hospital no tiene responsabilidad en la diferencia

## Resultado esperado

ACEPTAR PARCIALMENTE. Objetar 15 dosis ($1.650.000) con cita del kardex, y aceptar 3 dosis ($330.000) por falta de registro. Debe señalar que la premisa de la glosa («no hay registro») es falsa y que la orden médica de suspensión no se aportó.

---

## Cómo se califica

Marque **FALLO** si el dictamen hace cualquiera de las cosas de «qué NO debe
afirmar», aunque el resto esté bien redactado. Un dictamen elegante que afirma
algo sin respaldo es peor que uno que dice «no puedo determinarlo».

Lleve el resultado a `MATRIZ_PRUEBAS.xlsx`, hoja **RESULTADOS**.
