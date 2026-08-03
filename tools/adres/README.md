# Módulo ADRES — Radicación de soportes (Res. 2275/2023 y 2284/2023)

Herramientas para armar la radicación ante la **ADRES** a partir de los
soportes de cada factura (RIPS, CUV, FEV DIAN, PDFs clínicos). Pensado para
correr **desde cualquier PC**: rutas por parámetro, sin nada hardcodeado.

## Estado

| Script | Fase | Qué hace | Dependencia |
|---|---|---|---|
| `inspeccionar_soportes.py` | ✅ | Inventaría una carpeta de factura, clasifica cada soporte al código ADRES y lee el RIPS/CUV/FEV | stdlib |
| `validar_furips.py` | ✅ | **Bot de validación FURIPS**: malla Circular 022/2023 + cruce contra soportes (RIPS, CUV, FEV, factura PDF, epicrisis) + informe Excel masivo. Ver `README_validar_furips.md` | openpyxl, pypdf/pdfplumber |
| `rips_lectura.py` | ✅ | Módulo compartido: parseo y normalización del RIPS | stdlib |
| `generar_fur_servicios.py` | ✅ | Excel **FUR SERVICIOS** pre-rellenado desde el RIPS | openpyxl |
| `generar_fur.py` | ⬜ | Excel **FUR** (autollena víctima desde RIPS+aviso; resto manual/IPAT) | openpyxl |
| `generar_json_zip.py` | ⬜ | Excel completado → JSON ADRES + ZIP con soportes renombrados | stdlib |
| `cargar_masivo_adres.py` | ⬜ | Procesa muchas facturas + reporte CSV | — |

## Qué se autollena y qué no

**FUR SERVICIOS** (13 campos): **~70% automático** desde el RIPS.
- AUTO: factura, NIT, CUPS, descripción, cantidad, valores facturados, tipo de
  servicio (best-effort), código de tecnología (medicamentos/insumos).
- MANUAL (resaltado naranja): código general quirúrgico, consecutivo
  quirúrgico, valores *reclamados* (vienen = facturado como punto de partida),
  y el código **SOAT** de procedimientos (el RIPS trae CUPS, no SOAT).

**FUR** (62 campos, accidente de tránsito):
- AUTO desde RIPS: NIT, factura, tipo/número doc víctima, fecha nac., municipio.
- AUTO desde el aviso (`IPO`): nombres/apellidos, dirección de la víctima.
- MANUAL / desde IPAT-FURIPS: vehículo, conductor, propietario, póliza SOAT,
  SIRAS, zona/dirección de ocurrencia, condición de la víctima (~40 campos).

## Uso rápido

```bat
REM 1) Ver qué hay en la carpeta de una factura
py inspeccionar_soportes.py --carpeta "C:\...\FACTURAS\HUS428139"

REM 2) Generar el FUR SERVICIOS del RIPS
py generar_fur_servicios.py ^
    --carpeta "C:\...\FACTURAS\HUS428139" ^
    --salida  "C:\...\FACTURAS\HUS428139_FURSERVICIOS.xlsx"
```

## Radicación masiva multi-entidad

El procesamiento de **muchas facturas** con reporte (lo que figuraba como
`cargar_masivo_adres.py`) y, además, la radicación ante **cualquier entidad**
(no solo ADRES) vive ahora en `../radicar_facturacion.py`. Reutiliza estos
mismos parsers (`rips_lectura.py`, `factura_lectura.py`), tipifica los soportes,
valida la completitud por entidad y arma carpetas + ZIP. Ver
`../README_radicar_facturacion.md`.

## Nombramiento ADRES de soportes (para el ZIP final)

`FEV_`, `RIP_`, `CUV_`, `FUR_`, `SER_`, `OPF_`, `HEV_`, `CRC_`, `HAO_`, `PDX_`,
`HAM_`, `LDP_`, `HAU_`, `EPI_`, `TAP_`, `RAN_`, `DQX_`, `FMO_`, `FAT_`, `FAC_`,
`IPO_`, `CVE_`, `FCT_`, `CRA_`, `TIR_`, `ADM_` + `#NIT_#factura`.
ZIP: `NIT_AAAAMMDD_CONSECUTIVO.zip`.
