# Ajustador de detallados de factura — `ajustar_detallado_glosas.py`

Deja el **detallado de factura** con **solo lo que la entidad sigue glosando**.
Es el trabajo que hoy se hace a mano, hoja por hoja: borrar el encabezado,
cambiar el título, buscar en el reporte de glosas qué ya pagaron, borrar esos
renglones y volver a sumar.

---

## Qué hace, paso a paso

1. **Lee el consolidado** de facturas que se van a trabajar y le **quita los
   duplicados** (`HUS352890`, `HUS0000352890` y `hus352890` cuentan como una).
2. **Abre el Excel del detallado** (el que baja el sistema: **una sola hoja con
   todas las facturas del lote apiladas**, siempre muchas más de las que se
   necesitan) y **elimina las facturas que no están en el consolidado**.
3. En cada factura que queda:
   - **quita el encabezado institucional** (logo, `Carrera 33 # 28-126`, NIT,
     Bucaramanga, el QR, la línea `CUFE:` y `Página 1/1`);
   - cambia el título **`FACTURA ELECTRONICA DE VENTA` → `DETALLADO DE FACTURA`**.
4. **Cruza cada ítem contra el `ReporteGlosasReclamPAQUETE NNNNN.xlsx`** y:

   | Situación en el reporte | Qué hace el bot |
   |---|---|
   | Valor glosado = 0 (la entidad ya lo aprobó) | **Quita** el renglón |
   | Valor glosado = valor de la factura | **Deja** el renglón igual |
   | Aprobado a medias (glosado parcial) | **Ajusta** cantidad y valor a lo que sigue sin pagar |
   | El ítem no aparece en el reporte | **Lo deja y lo marca `SIN_CRUCE`** para revisión |

5. **Borra los títulos de grupo que quedaron vacíos** (`MEDICAMENTOS POS`,
   `DERECHOS DE SALA`, `IMAGENOLOGIA`, …) con su renglón en blanco, igual que
   se hace a mano.
6. **Recalcula** el `VALOR SUBTOTAL DE SERVICIOS PRESTADOS` (importe **y**
   cantidad de ítems), el `VALOR TOTAL ORDEN DE SERVICIO` y escribe el **total
   en letras** con el mismo formato del sistema
   (`CIENTO TREINTA Y DOS MIL OCHOCIENTOS PESOS CON CERO CTVS M/Cte.`).
7. Escribe el **Excel corregido** y una **bitácora CSV** ítem por ítem.

> **Seguro por defecto:** NO toca los archivos originales. Solo los **lee** y
> **escribe** el Excel de salida y la bitácora.

---

## Lo más importante: el reporte repite el mismo ítem

El `ReporteGlosasReclamPAQUETE` trae **el mismo ítem repartido en varias filas**.
En la factura de ejemplo `HUS352890`, la venda de gasa (6 unidades, $56.400)
aparece en **dos** filas:

| Cod Elemento | Cant Reclamado | Valor Reclamado | Valor Aprobado | Valor Glosado |
|---|---|---|---|---|
| 2016DM-0000315-R2 | 4 | 37.600 | 0 | **37.600** |
| 2016DM-0000315-R2 | 2 | 18.800 | 9.400 | **9.400** |

El bot **suma las dos** → siguen glosados **$47.000 (5 unidades)**, no $9.400.
Mirar una sola fila subestima la glosa, que es el error típico del proceso
manual. En la bitácora CSV la columna `FILAS_REPORTE` dice cuántas filas se
sumaron para cada ítem.

**No es un caso raro.** Sobre el reporte real del paquete 31068 (19.256 filas,
581 facturas), en las 324 facturas del lote:

- **el 32 % de los ítems (3.068 de 9.616) viene repartido en más de una fila**;
- el peor caso es la terapia respiratoria de `HUS311371`: **38 filas** del mismo
  ítem;
- en el **1,1 %** de las filas la columna `Cantidad Aprobada` **no cuadra** con
  `Valor Aprobado ÷ valor unitario` (como en la venda de gasa: dice 2 pero el
  valor corresponde a 1). Por eso el bot calcula la cantidad desde el **valor
  glosado**, no desde la columna de cantidad.

---

## Corrido sobre el paquete 31068 completo

| | |
|---|---|
| Reporte de glosas | `ReporteGlosasReclamPJ_RADICACIO`, encabezados en la fila 7, 19.256 filas, 581 facturas |
| Detallados | 7 archivos, 150.919 filas, 2.137 facturas |
| Facturas del lote | 324 — **320 encontradas**; faltan 311371, 367368, 380246 y 394817 |
| Resultado | 5 archivos ajustados, 1.817 facturas borradas por no ir en el lote |

| Concepto | Valor |
|---|---|
| Valor facturado de las 320 | $2.464.092.099 |
| Ya pagado (renglones que se quitan) | $1.749.759.874 |
| **Sigue glosado** | **$714.332.225 — 29,0 %** |

De 9.912 renglones: **7.052 se quitan**, **501 se ajustan**, **2.259 se dejan**
y **100 quedan marcados para revisión**.

---

## Los procedimientos quirúrgicos traen renglones de desglose

Debajo de un procedimiento quirúrgico el sistema imprime su **desglose**
(honorarios del cirujano, del anestesiólogo, ayudantía, derechos de sala,
materiales y suturas). Esos renglones **no llevan número consecutivo** y su
valor **ya está incluido** en el renglón que los encabeza: la factura suma solo
los renglones numerados.

En los 4 primeros archivos son **3.794 renglones en 302 facturas**, y sumarlos
como si fueran ítems **inflaba el valor de la factura en $628.947.541** sobre el
paquete 31068. El bot los marca `DESGLOSE` en la bitácora y los descuenta del
total cuando el renglón que los encabeza sigue en la factura.

> El reporte del ADRES lo modela al revés: el procedimiento va en $0 y son los
> componentes los que llevan el valor. Por eso el procedimiento se quita
> (`reclamado 0`) y son sus componentes los que quedan glosados.

---

## Dos cosas del reporte que NO son ítems

1. **Glosas a toda la reclamación.** 46 filas del reporte vienen con
   `Tipo Elemento = Reclamacion`, sin código ni descripción, y su valor **repite
   el total de la factura** (causales tipo "2102- La reclamación presenta
   formulario incompleto"). Si se cruzaran como ítems **duplicarían la glosa**:
   en el paquete 31068 son **$335.585.041** que aparecerían dos veces. El bot las
   separa y las anota en la bitácora como `GLOSA_RECLAMACION`.
2. **Glosas sin ítem en el detallado.** 24 ítems que el reporte glosa
   ($11.220.692) no existen en la factura impresa. Se anotan como
   `GLOSA_SIN_ITEM` para que el auditor los revise.

---

## Instalación

```bash
py -m pip install openpyxl
```

Opcional: `py -m pip install Pillow` — solo si el detallado trae imágenes
**fuera** del encabezado que se quieran conservar. Las del encabezado (logo y
QR) se eliminan de todas formas.

---

## Uso

### 1) Primero, ver qué haría (sin escribir nada)

```bat
cd C:\temp-notas
git pull

py tools\ajustar_detallado_glosas.py ^
    --consolidado    "D:\USUARIO CARTERA\Downloads\CONSOLIDADO.xlsx" ^
    --detallado      "D:\USUARIO CARTERA\Downloads\DETALLADOS PAQUETE 31068.xlsx" ^
    --reporte-glosas "D:\USUARIO CARTERA\Downloads\ReporteGlosasReclamPAQUETE 31068.xlsx" ^
    --diagnostico
```

Muestra, factura por factura y renglón por renglón, qué va a quitar, qué va a
ajustar y qué va a dejar. **Correr siempre esto primero.**

### 2) Generar el Excel corregido

```bat
py tools\ajustar_detallado_glosas.py ^
    --consolidado    "D:\USUARIO CARTERA\Downloads\CONSOLIDADO.xlsx" ^
    --detallado      "D:\USUARIO CARTERA\Downloads\DETALLADOS PAQUETE 31068.xlsx" ^
    --reporte-glosas "D:\USUARIO CARTERA\Downloads\ReporteGlosasReclamPAQUETE 31068.xlsx" ^
    --salida         "D:\USUARIO CARTERA\Documents\COOSALUD\DETALLADOS_31068_AJUSTADO.xlsx" ^
    --reporte-csv    "D:\USUARIO CARTERA\Documents\COOSALUD\bitacora_31068.csv"
```

---

## Opciones

| Opción | Para qué sirve |
|---|---|
| `--consolidado` | Excel/CSV con las facturas a trabajar. Si se omite, se trabajan **todas** las hojas del detallado. |
| `--detallado` | El/los Excel del detallado (una sola hoja con las facturas apiladas). Se pueden pasar **varios**; en ese caso `--salida` es una **carpeta**. |
| `--reporte-glosas` | El `ReporteGlosasReclamPAQUETE NNNNN.xlsx`. |
| `--salida` | Excel corregido (o carpeta, si son varios detallados). |
| `--reporte-csv` | Bitácora ítem por ítem (recomendado siempre). |
| `--paquete 31068` | Si el reporte trae varios paquetes, filtra solo ese. |
| `--modo-parcial` | `ajustar` (por defecto) deja solo la parte glosada; `conservar` deja el ítem completo; `quitar` lo elimina. |
| `--sin-cruce` | `conservar` (por defecto) deja los ítems que no aparecen en el reporte y los marca; `quitar` los elimina. |
| `--diagnostico` | Solo analiza y muestra; no escribe el Excel. |
| `--verbose` | Log detallado. |

---

## La bitácora CSV

Una fila por ítem, separada por `;` (se abre en Excel con doble clic):

`FACTURA · HOJA · GRUPO · CODIGO · NOMBRE · CANT_ORIGINAL · VR_ENT_ORIGINAL ·
VALOR_RECLAMADO · VALOR_APROBADO · VALOR_GLOSADO · ACCION · CANT_NUEVA ·
VR_ENT_NUEVO · CRUCE_POR · FILAS_REPORTE · CAUSALES_GLOSA · OBSERVACION`

- **ACCION**: `QUITADO`, `AJUSTADO`, `CONSERVADO`, `SIN_CRUCE`,
  `GLOSA_SIN_ITEM`, `GLOSA_RECLAMACION`, o el estado de la factura
  (`ELIMINADA`, `SIN_GLOSAS`, `SIN_ESTRUCTURA`).
- **CRUCE_POR**: cómo se emparejó el ítem — `codigo`, `descripcion`,
  `descripcion~` (por prefijo), `cantidad+valor` o `varios-a-uno`.

**Revisar siempre las filas `SIN_CRUCE`**: son ítems de la factura que no
aparecieron en el reporte de glosas. El bot los deja puestos (no borra nada por
las dudas) y los marca para que el auditor decida.

---

## Cómo cruza los ítems

Los dos archivos no hablan el mismo idioma:

- los códigos llevan distinto relleno de ceros (`19935303-4` / `19935303-04`);
- a los materiales el reporte les agrega un sufijo
  (`… MATERIAL DE OSTEOSINTESIS UNIDAD 01`);
- los dispositivos traen código INVIMA en el reporte (`2016DM-0000315-R2`) y
  código interno en la factura (`FMQ0046`);
- un mismo ítem puede estar partido en varias filas del reporte, o al revés:
  dos renglones de la factura ser uno solo del reporte.

El emparejamiento se hace **por rondas**, de la evidencia más fuerte a la más
débil, y en cada ronda **solo se acepta un par cuando es mutuamente único**:

1. por **código** (normalizando los ceros);
2. por **descripción** exacta;
3. por **descripción con sufijo** (prefijo);
4. por **cantidad + valor** exactos;
5. por **valor** exacto;
6. **varios renglones de la factura ↔ un ítem del reporte**, solo si cantidades
   y valores cuadran exacto (la glosa se reparte proporcionalmente).

Si un ítem empata con dos del reporte, **no se adivina**: pasa a la ronda
siguiente y, si nada lo resuelve, queda `SIN_CRUCE` para revisión. Emparejar
"al primero que aparezca" es lo que hacía que la PIPERACILINA se llevara la
glosa del NITRÓGENO URÉICO por compartir el valor unitario.

---

## Si algo no cuadra

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| `Hojas sin glosas` | La factura no tiene filas en el reporte | ¿Es de otro paquete? La factura queda sin tocar. |
| `Hojas sin estructura` | No encontró la tabla `CÓDIGO / NOMBRE / CANT` ni la fila `VALOR SUBTOTAL…` | El formato del detallado cambió: pasar el archivo para ajustar el bot. |
| `ninguna de sus N facturas está en el consolidado` | Ese archivo es de otro lote | No se escribe salida (quedaría vacía). |
| `REVISAR: N ítem(s) no cruzaron` | Ítems de la factura ausentes del reporte | Mirar la bitácora, columna `OBSERVACION`. |
| `X factura(s) del consolidado no están en el reporte de glosas` | El consolidado y el paquete no corresponden | Verificar que sean del mismo paquete. |

---

## Segunda opinión: `verificar_detallado_ajustado.py`

Antes de mandar nada, conviene que **otro programa revise el resultado**. Este
vuelve a leer el Excel ajustado y lo contrasta contra el original, el
consolidado y el reporte del ADRES —sin confiar en lo que el bot dijo que hizo:

```bat
py tools\verificar_detallado_ajustado.py ^
    --ajustado       "D:\...\DETALLADOS_31068_AJUSTADO.xlsx" ^
    --original       "D:\...\DETALLADOS PAQUETE 31068.xlsx" ^
    --consolidado    "D:\...\CONSOLIDADO.xlsx" ^
    --reporte-glosas "D:\...\ReporteGlosasReclamPAQUETE 31068.xlsx" ^
    --bitacora       "D:\...\bitacora_31068.csv"
```

Comprueba que no quede membrete ni el título viejo, que las facturas sean
exactamente las del consolidado, que suma de renglones = subtotal = total, que
ese total cuadre con lo que el ADRES dice que sigue glosado, y que el total en
letras corresponda al número. Devuelve `SIN FALLAS` o la lista de diferencias.

---

## Pruebas

```bash
py -m pytest tests/test_tools/test_ajustar_detallado_glosas.py -q
```

Los tests reconstruyen el formato real (facturas apiladas en una hoja, celdas
combinadas desalineadas, membrete al principio y pie legal al final) con la
factura `HUS352890` del ejemplo, y verifican que quede exactamente el "DESPUÉS":
membrete fuera, título cambiado, los 6 ítems pagados quitados, la venda de gasa
ajustada a 5 unidades y los totales recalculados.
