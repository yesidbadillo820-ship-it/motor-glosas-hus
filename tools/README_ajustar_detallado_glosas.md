# Ajustador de detallados de factura — `ajustar_detallado_glosas.py`

Deja el **detallado de factura** con **solo lo que la entidad sigue glosando**.
Es el trabajo que hoy se hace a mano, hoja por hoja: borrar el encabezado,
cambiar el título, buscar en el reporte de glosas qué ya pagaron, borrar esos
renglones y volver a sumar.

---

## Qué hace, paso a paso

1. **Lee el consolidado** de facturas que se van a trabajar y le **quita los
   duplicados** (`HUS352890`, `HUS0000352890` y `hus352890` cuentan como una).
2. **Abre el Excel del detallado** (el que baja el sistema con **una hoja por
   factura**, que siempre trae más facturas de las que se necesitan) y
   **elimina las hojas de las facturas que no están en el consolidado**.
3. En cada hoja que queda:
   - **quita el encabezado institucional** (logo, `Carrera 33 # 28-126`, NIT,
     Bucaramanga, el QR, la línea `CUFE:` y `Página 1/1`);
   - cambia el título **`FACTURA ELECTRONICA DE` → `DETALLADO DE FACTURA`**.
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
6. **Recalcula** el `VALOR SUBTOTAL DE SERVICIOS PRESTADOS`, el
   `VALOR TOTAL ORDEN DE SERVICIO` y escribe el **total en letras**
   (`CIENTO TREINTA Y DOS MIL OCHOCIENTOS PESOS M/CTE`).
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
| `--detallado` | El Excel del detallado. Se pueden pasar **varios**; en ese caso `--salida` es una **carpeta**. |
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
VR_ENT_NUEVO · CRUCE_POR · FILAS_REPORTE · OBSERVACION`

- **ACCION**: `QUITADO`, `AJUSTADO`, `CONSERVADO`, `SIN_CRUCE`, o el estado de
  la hoja (`ELIMINADA`, `SIN_GLOSAS`, `SIN_ESTRUCTURA`).
- **CRUCE_POR**: `codigo`, `descripcion` o `unitario` — cómo se emparejó el
  ítem con el reporte.

**Revisar siempre las filas `SIN_CRUCE`**: son ítems de la factura que no
aparecieron en el reporte de glosas. El bot los deja puestos (no borra nada por
las dudas) y los marca para que el auditor decida.

---

## Cómo cruza los ítems

Los códigos **no siempre coinciden** entre los dos archivos: en la factura la
venda de gasa es `FMQ0046` y en el reporte es `2016DM-0000315-R2` (código
INVIMA). Por eso el bot intenta en este orden:

1. **por código** (procedimientos y medicamentos: `39145`, `19992190-3`, …);
2. **por descripción** (dispositivos médicos: `VENDA DE GASA 6 X 5 YARDAS`),
   sin tildes ni signos;
3. **por valor unitario**.

Una fila del reporte se usa **una sola vez**, para que dos ítems distintos no
se lleven la misma glosa.

---

## Si algo no cuadra

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| `Hojas sin glosas` | La factura no tiene filas en el reporte | ¿Es de otro paquete? La hoja queda sin tocar. |
| `Hojas sin estructura` | No encontró la tabla `CÓDIGO / NOMBRE / CANT` ni la fila `VALOR SUBTOTAL…` | El formato del detallado cambió: pasar el archivo para ajustar el bot. |
| `REVISAR: N ítem(s) no cruzaron` | Ítems de la factura ausentes del reporte | Mirar la bitácora, columna `OBSERVACION`. |
| `X factura(s) del consolidado no están en el reporte de glosas` | El consolidado y el paquete no corresponden | Verificar que sean del mismo paquete. |

---

## Pruebas

```bash
py -m pytest tests/test_tools/test_ajustar_detallado_glosas.py -q
```

Los tests reconstruyen la factura `HUS352890` del ejemplo (el "ANTES") y
verifican que quede exactamente el "DESPUÉS": encabezado fuera, título
cambiado, los 6 ítems pagados quitados, la venda de gasa ajustada y los totales
recalculados.
