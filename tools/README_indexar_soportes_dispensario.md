# Guía: `indexar_soportes_dispensario.py` — Índice de soportes (Módulo 1 + 2)

Recorre **una sola vez** las carpetas de soportes (la unidad de red `Y:\...`) y
construye un **índice** (JSON) con una fila por documento: factura, tipo, ruta,
tamaño, fecha y —para los RIPS— paciente y número de factura. Después, el
asistente de conciliación consulta el índice y abre **solo** los archivos de la
factura que se está trabajando, **sin volver a recorrer `Y:\`** (que es lo que
se colgaba).

> **Por qué existe:** recorrer toda la unidad `Y:\` en cada corrida es lentísimo
> (se queda "pensando" minutos). Con el índice, escaneás una vez y todas las
> consultas posteriores son instantáneas.

## Flujo recomendado (2 pasos)

```powershell
cd C:\temp-notas
git pull

# PASO 1 — Indexar una vez (podés pasar varias carpetas de meses distintos).
#          El lote actual se radicó entre nov-2025 y mar-2026, así que incluí
#          esas carpetas, no solo la de julio.
py tools\indexar_soportes_dispensario.py `
  --raiz "Y:\11. NOVIEMBRE 2025 - SOPORTES RADICACION" `
  --raiz "Y:\12. DICIEMBRE 2025 - SOPORTES RADICACION" `
  --raiz "Y:\1. ENERO 2026 - SOPORTES RADICACION" `
  --raiz "Y:\2. FEBRERO 2026 - SOPORTES RADICACION" `
  --raiz "Y:\3. MARZO 2026 - SOPORTES RADICACION" `
  --salida "D:\USUARIO CARTERA\Desktop\indice_soportes.json" --con-meta

# PASO 2 — El asistente ya NO recorre Y:\ ; lee del índice.
py tools\asistente_conciliacion_dispensario.py `
  --excel "D:\USUARIO CARTERA\Downloads\HUS.xlsx" `
  --indice "D:\USUARIO CARTERA\Desktop\indice_soportes.json" `
  --salida "C:\Users\cartera\Desktop\MATRIZ_EVIDENCIA.xlsx" `
  --solo HUS436483 --con-oficios "C:\Users\cartera\Desktop\OFICIOS"
```

## Actualizar el índice más tarde (rápido)

Cuando lleguen soportes nuevos, no reindexes todo: usá `--actualizar` (reusa lo
ya indexado y solo escanea lo nuevo o modificado).

```powershell
py tools\indexar_soportes_dispensario.py `
  --raiz "Y:\3. MARZO 2026 - SOPORTES RADICACION" `
  --salida "D:\USUARIO CARTERA\Desktop\indice_soportes.json" --actualizar
```

## Buscar una factura (sin tocar `Y:\`)

```powershell
py tools\indexar_soportes_dispensario.py `
  --salida "D:\USUARIO CARTERA\Desktop\indice_soportes.json" --buscar HUS436483
```

Devuelve la lista de documentos de esa factura con su tipo y ruta. También busca
por documento del paciente o por nombre de archivo.

## Flags

| Flag | Uso |
|---|---|
| `--raiz <carpeta>` | Carpeta a indexar. **Se puede repetir** (varios meses). |
| `--salida <json>` | Archivo del índice (se lee y se escribe). |
| `--actualizar` | Incremental: reusa lo ya indexado, solo escanea lo nuevo. |
| `--con-meta` | Lee los RIPS para guardar paciente y número de factura. |
| `--buscar <texto>` | Solo busca en el índice (no reindexa). |

## Qué NO hace

- No decide procedencia de glosas (eso es el asistente).
- No mueve ni modifica los soportes: solo los lista.

Tests: `pytest tests/test_tools/test_indexar_soportes_dispensario.py`
