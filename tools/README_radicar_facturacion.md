# Radicador maestro multi-entidad — `radicar_facturacion.py`

Orquestador de **radicación de facturas** de la ESE Hospital Universitario de
Santander. Es el paso **aguas arriba** de los bots de glosas (COOSALUD, SIMED):
toma el lote que entrega el **área de facturación** y lo deja listo para radicar
ante cada entidad (EPS, regímenes especiales, SOAT/ADRES), revisando la **debida
tipificación de los soportes** según la **Resolución 2284 de 2023**.

En una sola corrida, por cada factura:

1. **Inventaría y tipifica** cada soporte al código ADRES (`FEV`, `RIP`, `CUV`,
   `HEV`, `EPI`, `HAU`, `PDX`, `OPF`, `DQX`, `RAN`, `CRC`, `HAM`, `TAP`, `FMO`,
   `FUR`, `SER`, `IPO`, …) y detecta los que están mal nombrados o sin reconocer.
2. **Lee el RIPS y la factura electrónica (FEV)** —reutiliza `tools/adres/`—
   para sacar número de factura, NIT del prestador, usuarios, servicios y el
   valor total facturado.
3. **Resuelve la entidad/pagador** (desde el manifiesto de facturación, la
   carpeta padre de EPS o el nombre) y la cruza con su **perfil de radicación**.
4. **Valida la completitud**: soportes base (`FEV`+`RIP`+`CUV`), soportes
   esperados según los servicios, consistencia del número de factura entre
   RIPS/FEV, y CUV cuando la entidad lo exige.
5. **Arma el paquete** (`--armar`): crea `<destino>/<ENTIDAD>/<factura>/`,
   renombra los soportes a la nomenclatura de la entidad, escribe un manifiesto
   por factura y, con `--zip`, genera el ZIP `<NIT>_<AAAAMMDD>_<consecutivo>.zip`.
6. **Reporta**: CSV por factura, resumen por entidad y resumen global.

> **Seguro por defecto**: sin `--armar` el script **no toca archivos**, solo
> diagnostica y reporta (modo auditoría). Ideal para "revisar la debida
> tipificación" antes de mover nada.

---

## Instalación

Núcleo: **solo librería estándar** de Python 3.11+ (corre en cualquier PC).
Para `--xlsx` o leer un manifiesto `.xlsx`:

```bash
py -m pip install openpyxl
```

El script importa los parsers de RIPS/FEV de `tools/adres/`, así que dejalo
dentro de `tools/` (junto a la carpeta `adres/`).

---

## Uso rápido

```bat
REM 1) Auditar el lote (no arma nada): tipificación + completitud + reporte
py radicar_facturacion.py --origen "D:\LOTE_FACTURACION_2026-06" ^
    --reporte "D:\salida\radicacion_2026-06.csv" ^
    --xlsx    "D:\salida\radicacion_2026-06.xlsx"

REM 2) Armar los paquetes por entidad (carpetas + renombrado ADRES)
py radicar_facturacion.py --origen "D:\LOTE" --destino "D:\RADICAR" --armar

REM 3) Armar + comprimir en ZIP, solo una entidad
py radicar_facturacion.py --origen "D:\LOTE" --destino "D:\RADICAR" ^
    --armar --zip --entidad COOSALUD

REM 4) El lote viene del share (muchas facturas por carpeta): --layout lote
py radicar_facturacion.py --origen "\\Prime\radicacion_2026\...\ESCANEO" --layout lote

REM 5) Mapear factura -> entidad con un Excel de facturación
py radicar_facturacion.py --origen "D:\LOTE" --manifiesto "D:\facturacion.xlsx"
```

---

## Layouts de entrada

| `--layout` | Estructura | Cómo agrupa | De dónde sale la entidad |
|---|---|---|---|
| `carpeta-factura` *(def.)* | Una **subcarpeta por factura** (`…/HUS469401/`), aunque esté anidada | Todos los archivos de la carpeta = una factura. Si la **misma** factura aparece en árboles paralelos (`RIPS/` y `SOPORTES/`) como dos carpetas con el mismo nombre, **se fusionan** | Manifiesto o un componente de la ruta con nombre de EPS |
| `lote` | Una carpeta con archivos de **muchas** facturas (el share) | Por el token `_<factura>_` del nombre, **sin importar la subcarpeta**; los compartidos (FURIPS) se reparten a todas las facturas de su carpeta | Manifiesto o un componente de la ruta con nombre de EPS |

> **El RIPS desnudo**: en el share real el RIPS suele venir nombrado **solo con
> el número de factura** —`HUS469401.json`, sin el token `RIP_`/`Rips_`—. El
> radicador lo reconoce igual (un `.json` cuyo nombre es una factura y que no es
> el `CUV_…`). Por eso ya **no** salen como `SIN_RIPS`.

### El share real de SINAC

La estructura típica del escaneo (febrero 2026) es:

```
…\2. SINAC SC SAS - 2026\02. FEBRERO\1. DD FACTURACION\ESCANEO\
  COOSALUD\                         ← EPS (de aquí sale la entidad)
    RIPS\
      ENV-222467-OK\                ← envío/lote
        HUS469401\
          HUS469401.json            ← RIPS (¡nombrado solo con la factura!)
          CUV_HUS469401.json        ← resultado de validación MSPS
        HUS470871\
          ...
    SOPORTES\                       ← árbol hermano: FEV + PDFs (si aplica)
      ENV-222467-OK\
        HUS469401\
          FEV_900006037_HUS469401.xml
          HEV_900006037_HUS469401.pdf
```

Recomendado para este share:

```bat
REM Auditar todo el mes (no toca nada). Apuntá --origen a la carpeta ESCANEO.
py radicar_facturacion.py ^
    --origen "X:\SERVIDOR RADICACION\2. SINAC SC SAS - 2026\02. FEBRERO\1. DD FACTURACION\ESCANEO" ^
    --layout lote ^
    --reporte "X:\salida\radicacion_febrero.csv" ^
    --xlsx    "X:\salida\radicacion_febrero.xlsx"
```

- `--layout lote` es el más robusto: agrupa por factura aunque el FEV/PDF estén
  en un árbol distinto (`SOPORTES/`) del RIPS (`RIPS/`).
- El layout por defecto (`carpeta-factura`) también sirve y **fusiona**
  automáticamente las dos carpetas `HUS469401\` (la de `RIPS/` y la de
  `SOPORTES/`) en una sola factura.

---

## Estados de cada factura

| Estado | Significado | ¿Se arma? |
|---|---|---|
| `LISTA` | Todos los soportes obligatorios presentes y bien tipificados | ✅ |
| `REVISAR_TIPIFICACION` | Hay archivos sin tipificar o faltan soportes *esperados* (no obligatorios) | Solo con `--forzar` |
| `FALTAN_SOPORTES` | Falta algún soporte **obligatorio** de la entidad | ❌ |
| `SIN_CUV` | Falta el resultado de validación RIPS (CUV) y la entidad lo exige | ❌ |
| `SIN_RIPS` / `SIN_FEV` | Falta el RIPS o la factura electrónica | ❌ |
| `FACTURA_INCONSISTENTE` | El número de factura no coincide entre RIPS y FEV | ❌ |
| `ENTIDAD_NO_RESUELTA` | No se pudo identificar el pagador | ❌ |

El código de salida es `0` si **todas** las facturas quedaron `LISTA`, `1` si
hay alguna con problemas (útil para encadenar en scripts/CI).

---

## Opciones del CLI

| Flag | Descripción |
|---|---|
| `--origen` | Carpeta raíz del lote *(requerido)*. |
| `--destino` | Dónde armar los paquetes *(requerido con `--armar`)*. |
| `--perfiles` | JSON de perfiles (def.: `data/perfiles_radicacion.json`). |
| `--manifiesto` | CSV/XLSX que mapea `factura → entidad`. |
| `--layout` | `carpeta-factura` (def.) o `lote`. |
| `--entidad` | Filtra solo una entidad (substring). |
| `--reporte` | CSV de salida (def.: `radicacion_reporte.csv`). |
| `--xlsx` | Reporte XLSX con formato y hoja de resumen. |
| `--armar` | Construye los paquetes (carpetas + renombrado). |
| `--zip` | Comprime cada paquete a ZIP. |
| `--mover` | Mueve los archivos en vez de copiarlos. |
| `--forzar` | Arma también los `REVISAR_TIPIFICACION`. |
| `--fecha` | `AAAAMMDD` para el nombre del ZIP (def.: hoy). |
| `--consecutivo-inicial` | Consecutivo inicial de los ZIP (def. 1). |
| `--dry-run` | No toca archivos; reporta qué haría. |
| `--log` | Archivo de log opcional. |

---

## Perfiles de entidad — `data/perfiles_radicacion.json`

El catálogo de entidades es **editable sin tocar código**. Cada entidad define:

```jsonc
{
  "id": "COOSALUD",
  "nombre": "COOSALUD EPS",
  "alias": ["COOSALUD", "COOSALUD EPS", "COOSALUD EPS-S"],
  "nit": "",                       // del pagador: completar desde el contrato
  "eps_codigo": "U220311",         // código DGH si aplica
  "regimen": "SUBSIDIADO",
  "canal": "PORTAL_BOT",           // ADRES | PORTAL | PORTAL_BOT | CORREO | FISICO
  "portal": "https://vco.ctamedicas.com",
  "nomenclatura": "ADRES",         // ADRES | DISPENSARIO_HUS_CORTO
  "cuv_obligatorio": true,
  "soportes_extra": [],            // códigos extra obligatorios (ej. SOAT: FUR, SER)
  "formato_paquete": "ZIP_FACTURA",// CARPETA | ZIP_FACTURA
  "bot": "tools/responder_glosas_coosalud.py",
  "observaciones": "..."
}
```

A nivel global, el bloque `soportes` define los **obligatorios base**
(`FEV`+`RIP`+`CUV`) y los **esperados por tipo de servicio** del RIPS
(hospitalización → `EPI`, urgencias → `HAU`, etc.). Estos defaults siguen la
Res. 2284/2023 y se pueden ajustar por operación.

> **Nota sobre NIT de pagadores**: vienen vacíos a propósito. Un NIT errado
> causa devoluciones; complételos desde el contrato/RUT de cada entidad. La
> resolución de entidad funciona por **nombre/alias**, y el NIT que se usa en la
> nomenclatura de soportes y en el ZIP es el del **prestador** (HUS).

---

## Nomenclatura de soportes (ADRES)

```
<TOKEN>_<NIT_prestador>_<factura>.<ext>     ej. FEV_900006037_HUS487523.pdf
ZIP por factura:  <NIT_prestador>_<AAAAMMDD>_<consecutivo>.zip
```

Para el **Dispensario (SIMED)** se usa `DISPENSARIO_HUS_CORTO`: la factura va en
formato corto (`HUS487523`, sin ceros de relleno) porque el portal rechaza el
formato largo.

---

## Cómo encaja con el resto del motor

```
FACTURACIÓN  →  [ radicar_facturacion.py ]  →  RADICACIÓN ante la entidad
   (lote)         tipifica, valida, arma           │
                                                    ▼
                                        (la EPS responde glosas)
                                                    │
                                                    ▼
                          responder_glosas_coosalud.py / responder_glosas_simed.py
                                        motor_glosas_hus.py (aprende y propone)
```

- Reutiliza los parsers de `tools/adres/` (`rips_lectura.py`, `factura_lectura.py`).
- Para radicación ante **ADRES/SOAT** (FUR, FUR SERVICIOS), ver `tools/adres/`.
- Las credenciales de portales se manejan por variables de entorno en cada bot
  (`COOSALUD_USER`, `SIMED_USER`, …); este radicador **no** sube nada a portales,
  solo deja el paquete armado y verificado.
