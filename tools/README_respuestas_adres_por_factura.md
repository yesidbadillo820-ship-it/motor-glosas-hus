# El PDF y el Word de respuesta, uno por factura (`respuestas_adres_por_factura.py`)

De la **macro de respuesta** del paquete saca, para cada factura, los dos
documentos que se radican:

- **`RTA_ADRES_<FACTURA>.pdf`** — el *REPORTE RTA ADRES*: encabezado con la
  factura, la radicación y el documento del paciente, y la tabla de seis
  columnas con lo que se le respondió a cada glosa.
- **`Reporte_Factura_<FACTURA>_<GESTOR>.docx`** — el *Word de respuesta*:
  primero lo que se aceptó y después lo demás, una respuesta por párrafo.

El texto de cada respuesta sale **tal cual** de la columna «RTA GLOSA COMPLETA»
de la macro: es lo que redactó el auditor y el bot no lo vuelve a armar ni lo
corrige.

---

## Cómo se usa

```
py tools\respuestas_adres_por_factura.py ^
    --macro  "D:\...\RTA GLOSA ADRES PAQ 31068.xlsx" ^
    --salida "D:\...\RESPUESTAS_31068" ^
    --reporte-csv "D:\...\RESPUESTAS_31068\REPORTE.csv"
```

Requiere una sola vez: `py -m pip install openpyxl python-docx reportlab`

| Opción | Para qué |
|---|---|
| `--macro` | El Excel de la macro de respuesta. |
| `--salida` | Carpeta donde deja los documentos. |
| `--gestor` | Solo las facturas de un gestor (CAROLINA, CLAUDIA, OSCAR…). |
| `--paquete` | Filtrar por número de paquete, si la macro trae varios. |
| `--consecutivo` | El consecutivo del oficio, si lleva. Va al comienzo del Word. |
| `--extemporanea` | Cerrar el Word con el aviso de glosa extemporánea. |
| `--incluir-glosas-totales` | Meter también las filas sin causal propia. |
| `--carpeta-por-factura` | Cada factura en su propia carpeta. |
| `--reporte-csv` | Listado de lo generado, con las cifras de cada factura. |

---

## Cómo queda el Word

1. Si la factura tiene valor aceptado, encabeza con
   `<consecutivo> SE IDENTIFICAN HALLAZGOS Y SE REALIZAN LOS AJUSTES
   CORRESPONDIENTES POR GLOSA ACEPTADA PARCIAL POR VALOR DE $X`.
   Si no aceptó nada, esa línea no va.
2. Una respuesta por párrafo, **con las aceptadas de primeras**.
3. Al final, si se pidió, el aviso de extemporaneidad; y las notas de lo que
   quedó por fuera.

---

## Dos cosas que el bot NO decide solo

**El aviso de extemporaneidad** (`--extemporanea`) es una afirmación jurídica
sobre el paquete —que la EPS glosó fuera de los términos del numeral 8.5 del
artículo 8 de la Resolución 1236 de 2023— y la macro no trae las fechas para
comprobarlo. Por eso **no se pone solo**: lo decide el auditor.

**Las glosas totales no se responden una por una.** En el reporte del ADRES hay
filas con la «Descripción Glosa» vacía: son el desglose de una reclamación que
el ADRES glosó entera por el FURIPS. No entran en los documentos, pero **sí se
dicen al pie**, con cuántas son y cuánto valen, para no esconder nada. Con
`--incluir-glosas-totales` se meten igual.

El bot tampoco calla lo que falta: si una glosa quedó **sin decidir** en la
macro (la columna OBSERVACION vacía), lo dice al pie del PDF y del Word.

---

## Corrida del paquete 31068 (21-08-2026)

324 facturas → **324 PDF y 324 Word**, sin un solo error. $798.133.471 glosados
y $91.617.467 aceptados. 108 facturas por gestor (CAROLINA, CLAUDIA y OSCAR).

Se omitieron 1.630 renglones de glosa total, avisados factura por factura, y
quedó **una** glosa sin decidir en toda la macro (HUS380112).
