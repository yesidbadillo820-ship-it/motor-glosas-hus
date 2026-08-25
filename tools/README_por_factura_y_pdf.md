# Un archivo por factura y conversión masiva a PDF

Dos herramientas que van una detrás de la otra, después de
[`ajustar_detallado_glosas.py`](README_ajustar_detallado_glosas.md):

```
detallado del sistema
   └─ ajustar_detallado_glosas.py   → deja solo lo que sigue glosado
        └─ dividir_detallado_por_factura.py  → un Excel por factura
             └─ excel_a_pdf.py                → un PDF por factura
```

---

## 1) `dividir_detallado_por_factura.py` — un Excel por factura

El detallado trae **todas las facturas apiladas en una sola hoja**. Para
radicar, anexar o mandar a PDF hace falta **un archivo por factura**.

Cada archivo sale con el número de la factura como nombre (`HUS352890.xlsx`),
con el formato intacto —celdas combinadas, anchos, fuentes, bordes, moneda— y
**listo para imprimir**: se le fija el área de impresión y el ajuste a lo ancho
de la página, para que el PDF no salga recortado por la derecha.

```bat
cd C:\temp-notas
git pull

REM Todos los archivos ajustados de una vez:
py tools\dividir_detallado_por_factura.py ^
    --detallado "D:\USUARIO CARTERA\Documents\COOSALUD\*_AJUSTADO.xlsx" ^
    --salida    "D:\USUARIO CARTERA\Documents\COOSALUD\EXCEL_POR_FACTURA" ^
    --reporte-csv "D:\USUARIO CARTERA\Documents\COOSALUD\listado_por_factura.csv"
```

| Opción | Para qué sirve |
|---|---|
| `--detallado` | Uno o varios Excel (acepta `*.xlsx`). |
| `--salida` | Carpeta donde dejar los archivos. |
| `--consolidado` | Separar **solo** las facturas de esa lista. |
| `--carpeta-por-factura` | `salida\HUS352890\HUS352890.xlsx` en vez de todo junto. |
| `--nombre corto\|largo` | `HUS352890` (por defecto) o el número tal cual venga. |
| `--sin-pie` | No copiar el texto legal del final del archivo. |
| `--no-sobrescribir` | Saltar los que ya existan. |
| `--reporte-csv` | Listado de lo generado. |

> El texto legal del final (`AUTORIZACIÓN FACTURA ELECTRÓNICA…`, `LICENCIADO A:`)
> se copia **a cada factura**, porque en el archivo grande aparece una sola vez
> y cada archivo suelto tiene que quedar completo.

---

## 2) `excel_a_pdf.py` — un PDF por cada Excel

```bat
REM Todos los PDF en una sola carpeta:
py tools\excel_a_pdf.py ^
    --origen "D:\USUARIO CARTERA\Documents\COOSALUD\EXCEL_POR_FACTURA" ^
    --salida "D:\USUARIO CARTERA\Documents\COOSALUD\PDF_POR_FACTURA" ^
    --reporte-csv "D:\USUARIO CARTERA\Documents\COOSALUD\listado_pdf.csv"

REM O cada PDF en su propia carpeta (para meterle los soportes al lado):
py tools\excel_a_pdf.py ^
    --origen "D:\...\EXCEL_POR_FACTURA" ^
    --salida "D:\...\PDF_POR_FACTURA" ^
    --carpeta-por-archivo
```

### Los dos motores

| Motor | Cuándo usarlo | Qué necesita |
|---|---|---|
| **Excel** (`--motor excel`) | Cuando el PDF tiene que salir **idéntico** a como imprime el Excel del hospital | Windows con Office y `py -m pip install pywin32` |
| **LibreOffice** (`--motor libreoffice`) | Cuando no hay Office, o para ir más rápido (convierte en tandas) | LibreOffice instalado |

Por defecto (`--motor auto`) usa el Excel del equipo si lo encuentra, y si no
LibreOffice.

| Opción | Para qué sirve |
|---|---|
| `--origen` | Carpeta(s) o archivo(s). Acepta comodines. |
| `--salida` | Carpeta de los PDF (si se omite, quedan junto al Excel). |
| `--carpeta-por-archivo` | `salida\HUS352890\HUS352890.pdf`. |
| `--patron` | Qué tomar de la carpeta (por defecto `*.xlsx`). |
| `--recursivo` | Entrar también en las subcarpetas. |
| `--saltar-existentes` | No rehacer los PDF que ya están (para reanudar). |
| `--lote N` | Archivos por tanda de LibreOffice (por defecto 25). |
| `--dry-run` | Solo mostrar qué haría. |
| `--reporte-csv` | Listado de lo convertido y de lo que falló. |

Ignora solo los temporales de Excel (`~$archivo.xlsx`) y lo que no sea
`.xlsx/.xlsm/.xls`. Devuelve código de salida 1 si algún archivo falló, para
que se note en un `.bat`.

---

## Corrido sobre el paquete 31068

| | |
|---|---|
| Excel generados | **320**, uno por factura |
| PDF generados | **320**, sin errores |
| Tiempo | ~8 min separar + ~35 s convertir |

**Comprobación de punta a punta:** se leyó el texto de los 320 PDF y se
verificó que cada uno traiga su número de factura, el título
`DETALLADO DE FACTURA` y que su `VALOR TOTAL ORDEN DE SERVICIO` coincida con la
bitácora. Los 320 cuadran, y la suma da **$714.332.224** contra los
**$714.332.225** de la bitácora (1 peso de redondeo en 320 facturas).

---

## Si algo no cuadra

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| `No encontré ningún Excel en …` | La carpeta está vacía o el patrón no pega | Revisar `--origen` y `--patron`. |
| `No encontré Excel por COM` | Falta `pywin32` o no hay Office | `py -m pip install pywin32`, o `--motor libreoffice`. |
| `No encontré LibreOffice` | No está instalado ni en el PATH | Indicar la ruta con `--ruta-libreoffice`. |
| `LibreOffice se pasó del tiempo límite` | Tanda muy grande o archivo pesado | Bajar `--lote` (por ejemplo `--lote 10`). |
| El PDF sale recortado | El área de impresión quedó corta | Volver a separar con la versión actual: el área ahora se mide sobre las celdas combinadas. |

## Pruebas

```bash
py -m pytest tests/test_tools/test_dividir_y_pdf.py -q
```
