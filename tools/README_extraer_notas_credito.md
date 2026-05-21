# Extraer documentos de Notas Crédito

Utilidad para descargar todos los archivos asociados a un listado de Notas
Crédito desde el share de facturación electrónica del HUS.

## Qué hace

A partir de un Excel/TSV/CSV con una columna `NOTA CREDITO`, el script:

1. Indexa todas las carpetas disponibles bajo el share, esperando la estructura

       <base>\<PERIODO>\<subcarpeta>\<nota>

   p. ej. `\\172.16.32.83\factura_electronica_net22\202605\FACTURAS_NOTA\309306`.

2. Para cada nota del listado, ubica la carpeta correspondiente y copia
   **todos** los archivos contenidos a `<salida>\<nota>\`.

3. Genera un reporte CSV (`reporte_extraccion_notas.csv` por defecto) con el
   estado de cada nota: `OK`, `PARCIAL`, `VACIA`, `NO_ENCONTRADA`, `ERROR`.

## Requisitos

- Python 3.9 o superior.
- Para leer `.xlsx`: `pip install openpyxl` (ya está en `requirements.txt`).
- Para `.tsv` / `.csv`: nada extra, solo stdlib.
- En Windows, conexión válida al share (`\\172.16.32.83\factura_electronica_net22`).
- En Linux/Mac, el share debe estar montado y se pasa el path con `--base`.

## Uso rápido

Desde la carpeta `tools/`:

```bash
# Con el TSV de ejemplo que viene en el repo
python extraer_notas_credito.py --tsv notas_credito_ejemplo.tsv

# Con tu Excel real
python extraer_notas_credito.py --excel "C:\ruta\a\notas.xlsx"

# Cambiar base / destino / reporte
python extraer_notas_credito.py ^
    --excel "C:\ruta\a\notas.xlsx" ^
    --base "\\172.16.32.83\factura_electronica_net22" ^
    --subcarpeta FACTURAS_NOTA ^
    --salida "C:\descargas\documentos" ^
    --reporte "C:\descargas\reporte.csv"

# Ver qué encontraría sin copiar nada
python extraer_notas_credito.py --excel notas.xlsx --dry-run
```

> En PowerShell usá `` ` `` en vez de `^` para continuar línea, y en Bash `\`.

## Argumentos

| Argumento | Default | Descripción |
|---|---|---|
| `--excel <ruta>` | — | Archivo `.xlsx` con la columna `NOTA CREDITO`. |
| `--csv <ruta>` | — | Archivo separado por comas. |
| `--tsv <ruta>` | — | Archivo separado por tabs (lo que sale al pegar de Excel). |
| `--base <ruta>` | `\\172.16.32.83\factura_electronica_net22` | Raíz del share. |
| `--subcarpeta <nombre>` | `FACTURAS_NOTA` | Carpeta dentro de cada periodo donde están las notas. |
| `--salida <ruta>` | `documentos` | Carpeta destino local. Se crea si no existe. |
| `--reporte <ruta>` | `reporte_extraccion_notas.csv` | CSV con el resumen por nota. |
| `--log <ruta>` | — | Archivo opcional para guardar el log. |
| `--no-fallback-recursivo` | off | Si la nota no está en el índice, no intenta `rglob` (más rápido pero menos tolerante). |
| `--dry-run` | off | No copia nada; solo informa qué encontraría. |

> El input es excluyente: usá uno de `--excel`, `--csv` o `--tsv`.

## Formato esperado del Excel/TSV

La única columna obligatoria es `NOTA CREDITO`. Si están presentes, también se
copian al reporte estas columnas (útiles para auditar):

- `Radicado`
- `Acta Conciliacion`
- `Prefijo Factura`
- `# Factura`
- `CONCATENAR`

Ejemplo mínimo (TSV):

```
Radicado	Acta Conciliacion	Prefijo Factura	# Factura	CONCATENAR	NOTA CREDITO
868448	AC000862	HUS	481072	HUS481072	309306
```

## Reporte CSV de salida

Una fila por nota única. Columnas:

| Columna | Significado |
|---|---|
| `nota` | Número de nota crédito (carpeta buscada). |
| `Radicado`, `Acta Conciliacion`, `Prefijo Factura`, `# Factura`, `CONCATENAR` | Tomados del Excel original, si existen. |
| `estado` | `OK`, `PARCIAL`, `VACIA`, `NO_ENCONTRADA`, `ERROR`. |
| `ruta_origen` | Ruta exacta de la carpeta encontrada (o vacío si NO_ENCONTRADA). |
| `archivos_copiados` | Archivos nuevos copiados al destino. |
| `archivos_omitidos` | Archivos que ya existían en destino con el mismo tamaño. |
| `errores` | Cantidad de errores de I/O durante la copia. |

Se puede abrir directamente en Excel (UTF-8 con BOM).

## Re-ejecución segura

Si se interrumpe el proceso o se quiere reintentar:

- Los archivos que ya existen en el destino con el mismo tamaño se **omiten**.
- Las notas que ya están completas no se recopian.
- Es seguro lanzar el script varias veces con el mismo destino.

## Diagnóstico de problemas comunes

| Síntoma | Causa probable | Fix |
|---|---|---|
| `La base no es accesible: \\172.16.32.83\...` | Falta autenticarse contra el share. | Abrí el Explorer, andá a la ruta, mete tu usuario/clave y reintentá. |
| `No encontré ninguna subcarpeta 'FACTURAS_NOTA'` | El share tiene otra estructura o nombre. | Usá `--subcarpeta` con el nombre correcto, o `--no-fallback-recursivo` apagado para que igual busque. |
| `NO_ENCONTRADA` en muchas notas | El share no tiene esos periodos visibles o las notas están en otra ruta. | Mirá el log: indica qué periodos indexó. Ajustá `--base` o pedile a Infra que monte el periodo faltante. |
| `errores` > 0 en el reporte | Archivos bloqueados, permisos, conexión inestable. | Re-ejecutá; los archivos OK se omiten y solo se reintentan los faltantes. |
| `openpyxl` no instalado | El Excel no se puede leer. | `pip install openpyxl` o exportá a TSV/CSV. |
