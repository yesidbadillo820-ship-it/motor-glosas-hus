# Guía: `organizar_objeciones_savia.py` — Objeciones de SAVIA SALUD → formato Dispensario

Herramienta que toma el Excel de **glosas de SAVIA SALUD** (las 8 columnas de
`SAVIA_SALUD_8.03.xlsx`) y lo reordena en la **estructura de 16 columnas** de la
guía `OBJECIONES_DISPENSARIO_HUS*.xlsx` (ese archivo del Dispensario se usa solo
como **plantilla de columnas**). Genera **un archivo por factura**, identificado
como de SAVIA (`OBJECIONES_SAVIA_<factura>.xlsx` por defecto; se cambia con
`--prefijo`).

---

## 1) Por qué existe

SAVIA SALUD entrega sus glosas en una tabla limpia de 8 columnas:

```
Numero_factura | Cod_Servicio | Servicio | Cantidad_Servicio |
Valor_Unitario | Valor_Glosa | Motivo_Esp_Glosa_Valor_A | Observacion_Glosa_A
```

Pero para trabajarlas/cargarlas en el **Dispensario** hacen falta en el layout de
16 columnas que ese sistema usa (hoja `OBJECIONES`):

```
CDCONSEC | CDFECDOC | CRNCXC | CROFECOBJ | CROREFERE | CROOBSERV | CROCLAOBJ |
CRNCLAOBJ | GENUSUARIO4 | CRNCONOBJ | SLNSERPRO | IDRIPS | CTNCENCOS |
CROVALOBJ | CRDOBSERV | CROTIPOBJ
```

Este bot hace esa conversión automáticamente y saca **un archivo por factura**,
con el mismo nombre y estructura que traían los originales del Dispensario.

---

## 2) Insumos

### Entrada (`--entrada`)

El Excel de SAVIA SALUD (8 columnas, como `SAVIA_SALUD_8.03.xlsx`). Las columnas
se detectan **por nombre de encabezado** (tolerante a tildes/mayúsculas); si el
archivo trajera otros nombres, cae a los índices fijos (0..7 en el orden de
arriba).

### Salida (`--salida`)

- **Por defecto:** una **carpeta**. El bot escribe ahí un
  `OBJECIONES_SAVIA_<factura>.xlsx` por cada factura (el prefijo se cambia con
  `--prefijo`).
- **Con `--consolidado`:** `--salida` es un `.xlsx` único con todas las facturas
  juntas.

---

## 3) Mapeo de campos (SAVIA → Dispensario)

| Salida (Dispensario) | Origen (SAVIA) | Cómo se obtiene |
|---|---|---|
| `CRNCXC` | `Numero_factura` | Se pasa a formato largo: `HUS443697` → `HUS0000443697` (10 dígitos). |
| `CRNCONOBJ` | `Motivo_Esp_Glosa_Valor_A` | Se completa a 6 caracteres: `TA08` → `TA0801` (ver **§4**). |
| `SLNSERPRO` | `Cod_Servicio` | Directo. |
| `CROVALOBJ` | `Valor_Glosa` | Directo (valor objetado). |
| `CRDOBSERV` | `Observacion_Glosa_A` | Directo (texto de la objeción). |
| `CDFECDOC`, `CROFECOBJ` | — | Fecha de `--fecha` (default: hoy). |
| `CDCONSEC` | — | Constante `1` (como la guía). Se cambia con `--consecutivo`. |
| `CROCLAOBJ`, `GENUSUARIO4`, `CROTIPOBJ` | — | Constantes `0`, `999`, `0` (de la guía). |
| `CROREFERE`, `CROOBSERV`, `CRNCLAOBJ`, `IDRIPS`, `CTNCENCOS` | — | Vacíos. |

---

## 4) Código de objeción (`--codigo-sufijo` / `--mapa-codigos`)

SAVIA usa códigos de **4 caracteres** (grupo + concepto): `TA08`, `CL07`, `SO61`.
El Dispensario usa **6** (grupo + concepto + consecutivo): `TA0801`, `CL0701`,
`SO6101`. Por defecto el bot **completa con el sufijo `01`** (el que traía la
guía original).

| Flag | Efecto |
|---|---|
| `--codigo-sufijo 05` | Usa otro consecutivo: `TA08` → `TA0805`. |
| `--mapa-codigos mapa.json` | Fuerza el código exacto por concepto (tiene prioridad). |

Ejemplo de `mapa.json`:

```json
{
  "TA08": "TA0805",
  "SO61": "SO6102"
}
```

> Si SAVIA/el Dispensario ya trae un mapeo oficial de estos códigos, cargalo por
> `--mapa-codigos` y esos ganan; el resto sigue la regla del sufijo.

---

## 5) Argumentos del CLI

| Flag | Default | Uso |
|---|---|---|
| `--entrada` | — (requerido) | Excel de SAVIA SALUD (8 columnas). |
| `--salida` | — (requerido) | Carpeta destino (o `.xlsx` si `--consolidado`). |
| `--prefijo` | `OBJECIONES_SAVIA` | Prefijo del nombre de cada archivo por factura. |
| `--consolidado` | off | Un solo Excel con todas las facturas en vez de uno por factura. |
| `--fecha` | hoy | Fecha `YYYY-MM-DD` para `CDFECDOC`/`CROFECOBJ`. |
| `--codigo-sufijo` | `01` | Consecutivo con que se completa el código (4→6). |
| `--mapa-codigos` | — | JSON para forzar códigos puntuales. |
| `--consecutivo` | `1` | Valor de `CDCONSEC`. |
| `--log` | — | Guarda un log adicional a archivo. |

---

## 6) Comandos típicos

### Un archivo por factura (lo normal)

```cmd
py tools\organizar_objeciones_savia.py ^
  --entrada "D:\...\SAVIA_SALUD_8.03.xlsx" ^
  --salida  "D:\...\OBJECIONES_SAVIA"
```

Deja en `OBJECIONES_SAVIA\` un `OBJECIONES_SAVIA_HUS0000443697.xlsx`,
`OBJECIONES_SAVIA_HUS0000503425.xlsx`, etc. (para otro prefijo, usá `--prefijo`).

### Con fecha específica de radicación

```cmd
py tools\organizar_objeciones_savia.py ^
  --entrada "D:\...\SAVIA_SALUD_8.03.xlsx" ^
  --salida  "D:\...\OBJECIONES_SAVIA" ^
  --fecha 2026-07-10
```

### Todo junto en un solo Excel

```cmd
py tools\organizar_objeciones_savia.py ^
  --entrada "D:\...\SAVIA_SALUD_8.03.xlsx" ^
  --salida  "D:\...\SAVIA_consolidado.xlsx" ^
  --consolidado
```

---

## 7) Qué imprime

```
2 archivo(s) del Dispensario en: ...\OBJECIONES_SAVIA
  Facturas: 2  |  Objeciones: 161
  Valor glosado total: $4,177,858
  Códigos de objeción (CRNCONOBJ):
    TA0801: 142
    CL0701: 6
    TA0201: 6
    ...
```

---

## 8) Instalación (una vez)

```cmd
py -m pip install openpyxl
```

---

## 9) Cosas para revisar

- **Código `CRNCONOBJ`**: la regla por defecto completa con `01`. Si algún
  concepto necesita otro consecutivo, usá `--mapa-codigos`.
- **Fecha**: `CDFECDOC`/`CROFECOBJ` toman `--fecha` (o el día de hoy). Poné la
  fecha de radicación/objeción que corresponda.
- **`CDCONSEC` / `GENUSUARIO4` / constantes**: se replican de la guía
  (`1` / `999` / `0`). Si tu Dispensario espera otros valores, avisá y se ajustan.
