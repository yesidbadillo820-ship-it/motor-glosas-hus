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

REM 6) Cruzar el share de soportes CLÍNICOS (epicrisis, evolución, órdenes…)
REM     para completar las facturas con procedimientos/hospitalización/urgencias
py radicar_facturacion.py --origen "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD" ^
    --soportes "\\Prime\soportes_radicacion\2026\06 JUNIO - SOPORTES RADICACION" ^
    --reporte "%USERPROFILE%\Desktop\radicacion_fe.csv" --xlsx "%USERPROFILE%\Desktop\radicacion_fe.xlsx"
```

---

## Layouts de entrada

| `--layout` | Estructura | Cómo agrupa | De dónde sale la entidad |
|---|---|---|---|
| `auto` *(def.)* | Carpetas con nombre de factura (`…/HUS520760/`), aunque estén anidadas y tengan subcarpetas | Ancla en la carpeta `HUS<factura>` y le asigna **todo lo que cuelga debajo** (subcarpeta `RIPS/`, documentos DIAN); lo demás, por token. Fusiona por número de factura | Manifiesto, carpeta EPS de la ruta, **o el adquiriente del propio FEV** |
| `carpeta-factura` | Una **subcarpeta por factura** | Todos los archivos de la carpeta = una factura; fusiona árboles paralelos con el mismo nombre | Manifiesto o carpeta EPS de la ruta |
| `lote` | Una carpeta con **muchas** facturas | Por el token `_<factura>_` del nombre, sin importar la subcarpeta | Manifiesto o carpeta EPS de la ruta |

> **Reconoce los nombres reales**: el RIPS desnudo (`HUS520760.json`), el del
> validador (`Rips_…`, CUV `ResultadosDoker_…`, envío `EnvioDoker_…`) y los
> documentos DIAN de la factura electrónica (`fv…`=FEV, `ad…`=AttachedDocument,
> `ar…`=acuse, `<factura>.zip`). Por eso ya **no** salen `SIN_RIPS`/`SIN_FEV`.

### Los dos shares reales del HUS

**1) ESCANEO** (RIPS + CUV, organizado por EPS):

```
…\02. FEBRERO\1. DD FACTURACION\ESCANEO\
  COOSALUD\                         ← EPS (de aquí sale la entidad)
    RIPS\ENV-222467-OK\HUS469401\
      HUS469401.json                ← RIPS (solo el número de factura)
      CUV_HUS469401.json
```

```bat
py radicar_facturacion.py --origen "X:\...\02. FEBRERO\1. DD FACTURACION\ESCANEO" --reporte "X:\salida\radicacion_feb.csv" --xlsx "X:\salida\radicacion_feb.xlsx"
```

**2) factura electrónica** (FEV DIAN, organizado por factura):

```
\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD\HUS520760\
  RIPS\                             ← subcarpeta
    Rips_HUS520760.json             ← RIPS
    ResultadosDoker_HUS520760_…json ← CUV (resultado de validación)
    EnvioDoker_HUS520760_…json      ← envío al validador (auxiliar)
  ad09…xml / fv09…xml / fv09…pdf    ← factura electrónica DIAN
  HUS520760.zip
```

```bat
py radicar_facturacion.py --origen "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD" --reporte "%USERPROFILE%\Desktop\radicacion_fe.csv" --xlsx "%USERPROFILE%\Desktop\radicacion_fe.xlsx"
```

- No hace falta `--layout`: `auto` (por defecto) cubre los dos shares.
- En el share de FE la EPS **no está en la ruta**: el radicador la lee del
  adquiriente (`AccountingCustomerParty`) de la propia factura electrónica. Si
  alguna EPS no resuelve, pasá `--manifiesto` (Excel/CSV con `FACTURA` y `EPS`)
  para forzar el mapeo.

### `--soportes`: cruzar el share de soportes clínicos

El share de FE trae lo **obligatorio** (`FEV`+`RIP`+`CUV`), pero la
**epicrisis, hoja de evolución, atención de urgencias y órdenes médicas** viven
en **otro share** (el de escaneo de soportes). Por eso, sin cruzar nada, toda
factura con `procedimientos`/`urgencias`/`hospitalización`/`medicamentos` queda
en `REVISAR_TIPIFICACION` (solo las de **consulta** llegan a `LISTA`).

Con `--soportes <raíz>` el radicador **indexa ese share por número de factura**
y rellena los huecos de cada factura (anexando `HEV`, `OPF`, `PDE`, `PDX`, `CRC`…
al paquete cuando se arma). Mismo criterio de cruce que el indexador de la app
(`HUS\d{4,12}` + normalización quitando ceros), así que **no requiere
configuración extra**.

```
<raíz>\…\ESCANEO\<EPS>\ENV-<lote>\
  HEV_900006037_HUS487523.pdf   ← historia clínica / epicrisis / evolución
  OPF_900006037_HUS487523.pdf   ← orden o prescripción facultativa
  PDX_900006037_HUS487523.pdf   ← resultado de apoyo diagnóstico
```

- Si se omite `--soportes`, se usa la variable de entorno **`SOPORTES_ROOT`**
  cuando está definida (la misma que ya usa el motor de glosas).
- Los soportes clínicos **siempre se copian** (nunca se mueven, aun con
  `--mover`): el share clínico es fuente y lo comparten otras facturas.
- Solo rellena **huecos**: no duplica `FEV`/`RIP`/`CUV` que el share de FE ya
  trae. La columna `soportes_clinicos` del reporte lista lo que se anexó.

> **Epicrisis ≡ historia clínica (HEV)**: en el HUS la epicrisis (`EPI`) y la
> atención de urgencias (`HAU`) se escanean **dentro** de la historia clínica
> (`HEV`), así que un `HEV` presente satisface esas exigencias. Es una
> *equivalencia* configurable (ver más abajo); con `"equivalencias": {}` en el
> JSON se vuelve a exigir el código exacto.

---

## Estados de cada factura

| Estado | Significado | ¿Se arma? |
|---|---|---|
| `LISTA` | Todos los soportes obligatorios presentes y bien tipificados | ✅ |
| `REVISAR_TIPIFICACION` | Hay archivos sin tipificar o faltan soportes *esperados* según los servicios (p.ej. epicrisis de una hospitalización). Crúzalo con **`--soportes`** para completarlos | Solo con `--forzar` |
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
| `--soportes` | Raíz del share de soportes **clínicos** a cruzar por factura (def.: `$SOPORTES_ROOT`). |
| `--layout` | `auto` (def.), `carpeta-factura` o `lote`. |
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
(`FEV`+`RIP`+`CUV`), los **esperados por tipo de servicio** del RIPS
(hospitalización → `EPI`, urgencias → `HAU`, etc.) y las **equivalencias** entre
códigos. Estos defaults siguen la Res. 2284/2023 y se pueden ajustar por operación:

```jsonc
"soportes": {
  "base_obligatorios": ["FEV", "RIP", "CUV"],
  "por_servicio": {
    "procedimientos": ["HEV"], "urgencias": ["HAU"],
    "hospitalizacion": ["EPI"], "medicamentos": ["OPF"]
  },
  "equivalencias": {           // un documento "paraguas" cubre uno específico
    "EPI": ["EPI", "HEV"],     // la epicrisis la cubre la historia clínica (HEV)
    "HAU": ["HAU", "HEV"]      // la atención de urgencias, igual
  }
}
```

Con `"equivalencias": {}` se exige el **código exacto** (sin paraguas).

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
