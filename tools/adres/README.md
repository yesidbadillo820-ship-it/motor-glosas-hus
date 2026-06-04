# Módulo ADRES — Radicación de soportes (Res. 2275/2023 y 2284/2023)

Herramientas para armar la radicación ante la **ADRES** a partir de los
soportes de cada factura (RIPS, CUV, FEV DIAN, PDFs clínicos). Pensado para
correr **desde cualquier PC**: rutas por parámetro, sin nada hardcodeado.

## Estado

| Script | Fase | Qué hace | Dependencia |
|---|---|---|---|
| `inspeccionar_soportes.py` | ✅ | Inventaría una carpeta de factura, clasifica cada soporte al código ADRES y lee el RIPS/CUV/FEV | stdlib |
| `rips_lectura.py` | ✅ | Módulo compartido: parseo y normalización del RIPS | stdlib |
| `generar_fur_servicios.py` | ✅ | Excel **FUR SERVICIOS** pre-rellenado desde el RIPS | openpyxl |
| `fur_lectura.py` | ✅ | Módulo compartido: lee el export del HUS (.xlsx/.csv/.tsv/.txt) y lo mapea a los 62 campos FUR | openpyxl |
| `generar_fur.py` | ✅ | Excel **FUR** (62 campos) por factura o masivo desde el export del HUS, con validación de obligatorios/condicionantes | openpyxl |
| `generar_json_zip.py` | ⬜ | Excel completado → JSON ADRES + ZIP con soportes renombrados | stdlib |
| `cargar_masivo_adres.py` | ⬜ | Procesa muchas facturas + reporte CSV | — |

## Qué se autollena y qué no

**FUR SERVICIOS** (13 campos): **~70% automático** desde el RIPS.
- AUTO: factura, NIT, CUPS, descripción, cantidad, valores facturados, tipo de
  servicio (best-effort), código de tecnología (medicamentos/insumos).
- MANUAL (resaltado naranja): código general quirúrgico, consecutivo
  quirúrgico, valores *reclamados* (vienen = facturado como punto de partida),
  y el código **SOAT** de procedimientos (el RIPS trae CUPS, no SOAT).

**FUR** (62 campos): **~100% automático** desde el export consolidado del HUS
(el `FURIPS1...txt`, una fila por factura). El export ya trae víctima, evento,
vehículo, propietario, conductor y atención; `fur_lectura.py` mapea cada
posición al campo oficial y normaliza formatos (fechas `DD/MM/AAAA`→`AAAA-MM-DD`,
zona `U/R`→`02/01`, municipio depto+muni→DIVIPOLA de 5 dígitos).

La **validación** (no inventa datos) resalta en rojo los campos vacíos que el
diccionario ADRES exige según la naturaleza y el estado de aseguramiento:
- Siempre: NIT, factura, doc. víctima, naturaleza, fecha/zona/municipio/
  dirección de ocurrencia, descripción corta, tipo de atención.
- En tránsito: condición de la víctima; y placa + tipo de vehículo,
  conductor y propietario **sólo si el vehículo está identificado**
  (estado 2/4/6/7). En estado 3 (vehículo fantasma / se da a la fuga) y 8
  (no identificado) esos campos quedan legítimamente vacíos y no se exigen.
- SIRAS: obligatorio si la ocurrencia es posterior al 01/06/2023.

Además resalta en **amarillo** (no es faltante, es "revisar antes de radicar",
el dato está pero conviene confirmarlo):
- Descripción corta con menos de 100 caracteres (relato insuficiente del hecho).
- Número de radicado SIRAS no numérico (p. ej. si el export trae un CUV/hash
  en esa columna en vez del radicado). No se borra ni se inventa: se marca.

> **Bloque de transporte/remisión (13 campos finales)**: el export del HUS no
> trae esas columnas (placa de ambulancia, traslado primario/secundario,
> prestador que remite/recibe, profesional y fecha/hora de aceptación), así que
> quedan **vacías**. Sólo aplican cuando hubo traslado en ambulancia, y ese dato
> normalmente lo radica el operador del transporte. Para confirmar si tu export
> sí los trae escondidos en alguna columna, corré `--diagnostico` sobre una
> factura con remisión: las columnas no mapeadas se marcan `← SIN MAPEAR`.

## Portabilidad — correr en cualquier PC

Los scripts no tienen rutas fijas (todo va por parámetro), así que son
portables de por sí. Para que una PC los corra **sin problemas** sólo hacen
falta Python y `openpyxl`. Hay dos caminos:

### A) PC con Python (recomendado para las PC del hospital)
1. Instalá Python 3 desde <https://www.python.org/downloads/> — en el
   instalador marcá **"Add Python to PATH"**.
2. Doble clic en **`INSTALAR.bat`** (instala `openpyxl` una sola vez).
3. Doble clic en **`GENERAR_FUR.bat`**: arrastrá el archivo del HUS
   (`FURIPS1...txt`) a la ventana y Enter. El Excel queda junto al archivo.

### B) PC sin nada instalado (.exe autónomo)
Para llevarlo a una PC que **no** tiene Python:
1. En una PC con Python, doble clic en **`construir_exe.bat`**.
2. Se crean los ejecutables en la carpeta **`dist\`**.
3. Copiá `dist\generar_fur.exe` (y los demás) a la otra PC. Corren solos, sin
   Python ni librerías:
   ```bat
   generar_fur.exe --fur "FURIPS1....txt" --salida "lote_FUR.xlsx"
   ```

> Requisito mínimo del código: **Python 3.10+** y `openpyxl`. Sin internet del
> lado del usuario final si usás los `.exe`. No hay nada hardcodeado: las rutas
> de entrada/salida siempre se pasan por parámetro.

## Uso rápido

```bat
REM 1) Ver qué hay en la carpeta de una factura
py inspeccionar_soportes.py --carpeta "C:\...\FACTURAS\HUS428139"

REM 2) Generar el FUR SERVICIOS del RIPS
py generar_fur_servicios.py ^
    --carpeta "C:\...\FACTURAS\HUS428139" ^
    --salida  "C:\...\FACTURAS\HUS428139_FURSERVICIOS.xlsx"

REM 2b) Igual, pero resolviendo las descripciones ambiguas con el manual ISS/SOAT
py generar_fur_servicios.py ^
    --carpeta "C:\...\FACTURAS\HUS428139" ^
    --furips2 "C:\...\FACTURAS\FURIPS2....txt" ^
    --soat    "C:\...\manual_soat.csv" ^
    --salida  "C:\...\FACTURAS\HUS428139_FURSERVICIOS.xlsx"

REM 3) Localizar el export del HUS (escanea recursivo y reporta filas/facturas)
py generar_fur.py --buscar "C:\Users\Usuario\Downloads"

REM 4) FUR de UNA factura
py generar_fur.py ^
    --fur     "C:\...\FACTURAS\FURIPS168001....txt" ^
    --factura HUS428139 ^
    --salida  "C:\...\FACTURAS\HUS428139_FUR.xlsx"

REM 4b) Verificar el mapeo posición→campo de una factura (no genera Excel)
py generar_fur.py ^
    --fur     "C:\...\FACTURAS\FURIPS168001....txt" ^
    --factura HUS428139 --diagnostico

REM 5) FUR masivo (TODAS las facturas del export en un solo Excel)
py generar_fur.py ^
    --fur    "C:\...\FACTURAS\FURIPS168001....txt" ^
    --salida "C:\...\FACTURAS\lote_FUR.xlsx"
```

### Descripción del servicio: de dónde sale

Por orden de prioridad (cada fuente sólo llena lo que la anterior dejó vacío):

1. **FURIPS2** (detalle del HUS) — descripción y código SOAT directos.
2. **RIPS por código** — medicamentos (CUM) y servicios con `codTecnologiaSalud`.
3. **PDF DIAN, precio único** — un solo servicio a ese precio → descripción limpia.
4. **Propagación por código SOAT** — copia entre líneas del mismo código.
5. **Manual ISS/SOAT (`--soat`)** — descripción oficial por código del servicio.
   Resuelve los códigos de tarifa que cubren varios procedimientos.
6. **PDF DIAN, precio ambiguo** — si nada anterior resolvió, marca `[ELEGIR]`
   con los candidatos del DIAN para que el coordinador escoja antes de radicar.

El manual `--soat` es un CSV/TSV/XLSX `código→descripción` (ver
`manual_soat_PLANTILLA.csv`). Con él, los renglones que de otro modo quedarían
`[ELEGIR]` (un código SOAT = varios procedimientos al mismo precio) toman el
nombre canónico del manual y quedan radicables.

## Nombramiento ADRES de soportes (para el ZIP final)

`FEV_`, `RIP_`, `CUV_`, `FUR_`, `SER_`, `OPF_`, `HEV_`, `CRC_`, `HAO_`, `PDX_`,
`HAM_`, `LDP_`, `HAU_`, `EPI_`, `TAP_`, `RAN_`, `DQX_`, `FMO_`, `FAT_`, `FAC_`,
`IPO_`, `CVE_`, `FCT_`, `CRA_`, `TIR_`, `ADM_` + `#NIT_#factura`.
ZIP: `NIT_AAAAMMDD_CONSECUTIVO.zip`.
