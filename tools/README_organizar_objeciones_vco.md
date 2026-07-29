# Guía: `organizar_objeciones_vco.py` — Organizador de objeciones VCO por entidad

Bot que organiza las objeciones (glosas) que llegan por el portal VCO
(`vco.ctamedicas.com`) de **SAVIA SALUD**, COOSALUD, FIDUPREVISORA y demás
entidades. Convierte entre los dos formatos que maneja cartera del HUS y
**autodetecta** cuál le pasaste como entrada:

| Entrada | Salida |
|---|---|
| CONSOLIDADO VCO (acta, 10 columnas) | Plantilla **OBJECIONES** de cargue al ERP (16 columnas) |
| Plantilla OBJECIONES / export ERP (16 columnas) | **CONSOLIDADO VCO** (10 columnas, como el de las demás entidades) |

---

## 1) Los dos formatos

### CONSOLIDADO VCO (una fila por servicio objetado)

```
CROOBSERV | NUMERO FACTURA | VALOR GLOSA | CODIGO GLOSA ESPECIFICA |
OBSERVACION | CODIGO SERVICIO | DESCRIPCION SERVICIO | CANTIDAD |
VALOR UNITARIO SERVICIO | VALOR TOTAL SERVICIO
```

- `CROOBSERV` trae la referencia del acta (ej. `VCO-FIDUPREVISORA-2024-R1-14920`,
  para Savia sería `VCO-SAVIA...`).
- Los encabezados se matchean con tolerancia (tildes, mayúsculas, espacios) y
  aceptan alias: `ACTA`, `Nro Factura`, `Vlr Glosa`, `Cód Glosa`,
  `Observaciones`, `CUPS`, `Cant`, etc.

### Plantilla OBJECIONES (cargue masivo al ERP)

```
CDCONSEC | CDFECDOC | CRNCXC | CROFECOBJ | CROREFERE | CROOBSERV |
CROCLAOBJ | CRNCLAOBJ | GENUSUARIO4 | CRNCONOBJ | SLNSERPRO | IDRIPS |
CTNCENCOS | CROVALOBJ | CRDOBSERV | CROTIPOBJ
```

Los encabezados de salida son **exactamente** los de la plantilla
`OBJECIONES.xlsx` (misma hoja `OBJECIONES`, fila 1 congelada).

---

## 2) Uso típico con SAVIA SALUD

### A) Del consolidado del acta → cargue OBJECIONES para el ERP

```cmd
py tools\organizar_objeciones_vco.py ^
    --entrada "D:\GLOSAS 2026\CONSOLIDADO_VCO_SAVIA.xlsx" ^
    --entidad "SAVIA SALUD" ^
    --fecha-documento 17/07/2026
```

Genera `OBJECIONES_SAVIA_SALUD.xlsx` junto a la entrada (o donde diga
`--salida`) e imprime un **resumen de control** por acta (facturas,
número de objeciones y valor glosado) para cuadrar contra el acta antes
de cargar al ERP.

### B) Del export/plantilla OBJECIONES → CONSOLIDADO VCO

```cmd
py tools\organizar_objeciones_vco.py ^
    --entrada "D:\GLOSAS 2026\OBJECIONES_SAVIA.xlsx" ^
    --entidad "SAVIA SALUD"
```

Genera `CONSOLIDADO_VCO_SAVIA_SALUD.xlsx` con el mismo formato (y formato
contable en los valores) del consolidado de las demás entidades.

> Si el archivo OBJECIONES viene **solo con encabezados** (sin datos), el bot
> lo dice claro y sale con error — hay que exportar/pegar primero las
> objeciones de la entidad.

---

## 3) Mapeo consolidado → cargue (supuestos ajustables)

| Campo ERP | De dónde sale | Flag |
|---|---|---|
| `CDCONSEC` | Consecutivo **por factura** (todas las filas de una misma factura comparten el número) | `--consecutivo-inicial` (default 1) |
| `CDFECDOC` | Fecha del documento | `--fecha-documento` (default hoy) |
| `CRNCXC` | `NUMERO FACTURA` (con `--sin-prefijo`: `HUS521454` → `521454`) | `--sin-prefijo` |
| `CROFECOBJ` | Fecha de la objeción | `--fecha-objecion` (default = fecha documento) |
| `CROREFERE` / `CROOBSERV` | Referencia del acta (columna `CROOBSERV`/`ACTA` del consolidado) | `--referencia` si no hay columna |
| `CROCLAOBJ` | Letras del código de glosa (`TA2901` → `TA`) | — |
| `CRNCLAOBJ` | Concepto general Res. 3047 (`TA2901` → `29`) | — |
| `GENUSUARIO4` | Usuario que registra | `--usuario` (default `CARTERA`) |
| `CRNCONOBJ` | Código de glosa específico completo (`TA2901`) | — |
| `SLNSERPRO` | `CODIGO SERVICIO` | — |
| `IDRIPS` | Vacío (no viene en el consolidado) | — |
| `CTNCENCOS` | Centro de costos | `--centro-costos` (default vacío) |
| `CROVALOBJ` | `VALOR GLOSA` (numérico, tolera `$ 1.234.567`) | — |
| `CRDOBSERV` | `OBSERVACION` tal cual; con `--detalle-servicio` anexa servicio/cantidad/valores | `--detalle-servicio` |
| `CROTIPOBJ` | Tipo de objeción | `--tipo-objecion` (default vacío) |

> **Validar contra un cargue previo del ERP**: si el ERP espera otros valores
> en `CROCLAOBJ`/`CRNCLAOBJ`/`CRNCONOBJ`/`CROTIPOBJ` (catálogos propios), se
> ajustan con los flags o pedime el cambio con un ejemplo de cargue exitoso.

En el sentido inverso (cargue → consolidado), `DESCRIPCION SERVICIO` y
`CANTIDAD` se rescatan (mejor esfuerzo) del patrón `(DESCRIPCION CANTIDAD n)`
al final de la observación; los valores unitario/total quedan vacíos porque
el layout del ERP no los trae.

---

## 4) Otros flags

- `--hoja <nombre>`: hoja a leer (match tolerante; default: la primera).
- `--salida <ruta>`: ruta exacta del Excel de salida.
- `--entidad "<nombre>"`: solo afecta el nombre del archivo de salida
  (`OBJECIONES_<ENTIDAD>.xlsx` / `CONSOLIDADO_VCO_<ENTIDAD>.xlsx`).

## 5) Tests

```bash
python3 -m pytest tests/test_tools/test_organizar_objeciones_vco.py -q
```

30 tests: autodetección, alias de encabezados, consecutivos, partición del
código de glosa, montos es-CO, ambos sentidos del mapeo y CLI end-to-end.
