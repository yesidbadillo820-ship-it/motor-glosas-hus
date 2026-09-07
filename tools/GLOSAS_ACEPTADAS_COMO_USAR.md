# Cómo completar el consolidado de glosas aceptadas

Herramienta para llenar, en el consolidado mensual de glosas aceptadas, las
columnas de **respuesta**, **número** y **fecha** de trámite o acta, cruzando
cada factura contra la CIRCULARIZACIÓN DE GLOSAS.

## Uso normal (doble clic)

1. Doble clic en **`GLOSAS ACEPTADAS.bat`**.
2. Le pide los dos archivos de Excel, uno por uno:
   - el **consolidado de glosas aceptadas** del mes,
   - la **CIRCULARIZACIÓN DE GLOSAS** del año.
3. Le pregunta si quiere **rehacer** las filas de tipo ACTA que ya estaban
   diligenciadas. Responda:
   - **N** si es la primera vez que procesa ese archivo,
   - **S** si ya lo había procesado y quiere volver a generarlo.
4. Al terminar deja, en la misma carpeta del consolidado, dos archivos:
   - `... - DILIGENCIADO.xlsx` — el consolidado con las columnas llenas,
   - `... - REVISAR.csv` — la lista de casos que necesitan su revisión.

También puede **arrastrar los dos Excel** encima del `.bat`: no importa en qué
orden, la herramienta reconoce sola cuál es cuál.

## Qué escribe

En la columna de respuesta va **un párrafo por cada glosa aceptada** del acta,
separados por una línea en blanco. Solo entran las que dicen que la ESE HUS
acepta: las que la entidad levantó, las ratificadas y las no aceptadas se
quedan por fuera, porque una nota crédito documenta lo aceptado.

Los renglones que repiten el mismo texto **no se agrupan**: dos renglones
iguales son dos glosas distintas, y agruparlos escondería la plata de uno.

El número y la fecha del acta solo se escriben si la celda venía vacía. Nunca
se pisa un dato que usted ya haya puesto. Las filas de tipo TRÁMITE no se
tocan nunca.

## La columna de novedades

Al final del archivo se agrega la columna **NOVEDAD ACEPTADO VS NOTA CREDITO**,
que solo se llena cuando hay algo que mirar. Avisa dos cosas distintas:

- **Diferencias de plata**: cuando lo aceptado en el acta no coincide con lo
  que acreditó la nota crédito. Dice por cuánto y para qué lado.
- **Errores de redacción en el acta**: cuando el texto de un renglón anuncia
  una cifra distinta a su propio valor aceptado. El valor registrado puede
  estar bien y el texto mal; esto lo detecta.

Cuando el primer renglón de un acta encabeza con el total de la nota y después
lo desglosa servicio por servicio, la herramienta lo reconoce y **no** lo
reporta como diferencia: no lo es.

## Si algo falla

- **"No se encontró Python"**: instálelo desde python.org y marque la casilla
  *Add Python to PATH* durante la instalación.
- **"No se hallaron las columnas"**: el formato del consolidado cambió. La
  herramienta ubica las columnas por el texto del encabezado; si un mes viene
  con otros nombres, hay que agregarlos en `COLUMNAS_BD` dentro del script.

## Desde la línea de comandos

```
python completar_tramite_glosas_aceptadas.py ACEPTADAS.xlsx CIRCULARIZACION.xlsx SALIDA.xlsx REPORTE.csv [--rehacer]
```
