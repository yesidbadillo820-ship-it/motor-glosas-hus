# Guía: `organizar_objeciones_savia.py` — Organizador de objeciones de SAVIA SALUD

Herramienta que toma el/los export(s) **crudos del Dispensario**
(`OBJECIONES_DISPENSARIO_HUS*.xlsx`) y arma un Excel **limpio y organizado** con
el formato exacto que usa el equipo para trabajar las glosas de **SAVIA SALUD**
(tomado como plantilla del archivo `SAVIA_SALUD_8.03.xlsx`).

Es el mismo patrón que `convertir_tramite_masivo.py` (que convierte el export del
CRRP al formato de SIMED), pero apuntando al formato de SAVIA SALUD.

---

## 1) Por qué existe

El Dispensario exporta las objeciones en un Excel **técnico y difícil de leer**:
16 columnas con nombres de sistema (`CRNCXC`, `CRNCONOBJ`, `SLNSERPRO`,
`CROVALOBJ`, `CRDOBSERV`, …), una fila por objeción, con el número de factura en
formato largo (`HUS0000530265`) y el nombre del servicio, la cantidad y el valor
unitario **embebidos dentro del texto** de la objeción.

Para trabajar las glosas de SAVIA el equipo necesita, en cambio, una tabla de
**8 columnas limpias**:

| Columna | Contenido |
|---|---|
| `Numero_factura` | Factura corta (`HUS530265`) |
| `Cod_Servicio` | Código del servicio/insumo glosado |
| `Servicio` | Nombre del servicio |
| `Cantidad_Servicio` | Cantidad facturada |
| `Valor_Unitario` | Valor unitario facturado |
| `Valor_Glosa` | Valor objetado |
| `Motivo_Esp_Glosa_Valor_A` | Código de objeción (p.ej. `CL08`, `TA08`, `SO61`) |
| `Observacion_Glosa_A` | Texto de la objeción |

Este bot hace esa transformación de forma automática y **consolida muchas
facturas** (una carpeta llena de `OBJECIONES_DISPENSARIO_*.xlsx`) en un solo
Excel ordenado por factura.

---

## 2) Insumos que necesita

### A) Export(es) del Dispensario (`--entrada`)

Uno o más `OBJECIONES_DISPENSARIO_HUS*.xlsx`, **o una carpeta** que los contenga
(los toma todos con `*.xlsx`, ignorando los temporales `~$…`). Las columnas se
detectan **por nombre de encabezado** (tolerante a tildes/mayúsculas); si el
export viniera con encabezados distintos, cae a los índices fijos observados:

| Concepto | Columna del Dispensario | Índice de respaldo |
|---|---|---|
| Factura | `CRNCXC` | 2 |
| Código de objeción | `CRNCONOBJ` | 9 |
| Código de servicio | `SLNSERPRO` | 10 |
| Valor objetado | `CROVALOBJ` | 13 |
| Texto de la objeción | `CRDOBSERV` | 14 |

### B) Excel de salida (`--salida`)

Ruta del Excel organizado que se va a generar (se crea la carpeta si no existe).

---

## 3) Mapeo de campos (crudo → SAVIA)

| Salida (SAVIA) | Origen (Dispensario) | Cómo se obtiene |
|---|---|---|
| `Numero_factura` | `CRNCXC` | Se acorta: `HUS0000530265` → `HUS530265` (mismo criterio que `radicar_facturacion.factura_corta`). Se puede desactivar con `--sin-normalizar-factura`. |
| `Cod_Servicio` | `SLNSERPRO` | Directo. |
| `Servicio` | `CRDOBSERV` | Se extrae del texto: lo que sigue a `SE GLOSA CODIGO <cod>` hasta el primer punto / `SE FACTURA`. Si no hay código de servicio (p.ej. estancias), usa el nombre del concepto del encabezado. Si no se puede, queda vacío. |
| `Cantidad_Servicio` | `CRDOBSERV` | Del texto: `SE FACTURA UNA UNIDAD` → 1, `SE FACTURAN DOS UNIDADES` → 2. Default 1. |
| `Valor_Unitario` | `CRDOBSERV` / `CROVALOBJ` | Del texto: `POR VALOR DE N PESOS` (valor facturado) ÷ cantidad. Si no está, asume objeción de línea completa (`Valor_Glosa` ÷ cantidad). |
| `Valor_Glosa` | `CROVALOBJ` | Directo (valor objetado). |
| `Motivo_Esp_Glosa_Valor_A` | `CRNCONOBJ` | Ver **§4**. |
| `Observacion_Glosa_A` | `CRDOBSERV` | Texto de la objeción, quitándole el `$NNNNN` que el Dispensario pega al final. |

> **Nota sobre la extracción de `Servicio`, `Cantidad_Servicio` y
> `Valor_Unitario`:** estos tres campos **no existen como columna** en el export
> del Dispensario — van embebidos en la redacción de la objeción. La herramienta
> los extrae con reglas de texto (best-effort) y siempre deja un valor de
> respaldo razonable (cantidad 1, unitario = valor glosado, servicio vacío). Es
> recomendable una revisión rápida de estas columnas cuando la redacción del
> Dispensario sea atípica.

---

## 4) Código de objeción (`--codigo`)

El Dispensario usa códigos de **6 caracteres**: `<GG><CC><SS>` (grupo + concepto
+ consecutivo), p.ej. `CL0801`, `TA0801`, `SO0801`. La plantilla de SAVIA usa los
**4 primeros** (grupo + concepto): `CL08`, `TA08`, `SO08`.

Esto se verificó contra la plantilla `SAVIA_SALUD_8.03.xlsx`:
`TA0801 → TA08` y `CL0801 → CL08` (ambos "apoyo diagnóstico").

| `--codigo` | Efecto | Ejemplo |
|---|---|---|
| `corto` (default) | Los 4 primeros caracteres (grupo + concepto). Coincide con la plantilla de SAVIA. | `CL0801` → `CL08` |
| `completo` | El código tal cual del Dispensario (trazable). | `CL0801` → `CL0801` |

### Mapeo puntual (`--mapa-codigos`)

Si SAVIA espera un código distinto para algún concepto, se puede pasar un JSON
que **fuerza** el mapeo de esos códigos (se aplica antes que `--codigo`):

```json
{
  "CL0801": "CL06",
  "SO0801": "SO61"
}
```

```
--mapa-codigos "mapa_savia.json"
```

Los códigos que no estén en el JSON siguen la regla de `--codigo`.

---

## 5) Argumentos del CLI

| Flag | Default | Uso |
|---|---|---|
| `--entrada` | — (requerido) | Uno o más Excel del Dispensario, o carpeta(s) con `OBJECIONES_DISPENSARIO_*.xlsx`. |
| `--salida` | — (requerido) | Excel destino con el formato organizado de SAVIA. |
| `--codigo` | `corto` | `corto` (CL0801→CL08) o `completo` (CL0801 tal cual). |
| `--mapa-codigos` | — | JSON opcional para forzar códigos puntuales. |
| `--limpiar-encabezado` | off | Quita el código del inicio del texto (`CL0801 …`), que ya va en su columna. |
| `--sin-normalizar-factura` | off | Deja la factura larga (`HUS0000530265`) en vez de acortarla. |
| `--log` | — | Guarda un log adicional a archivo. |

---

## 6) Comandos típicos

### Un solo Excel del Dispensario

```cmd
py tools\organizar_objeciones_savia.py ^
  --entrada "D:\...\OBJECIONES_DISPENSARIO_HUS0000530265.xlsx" ^
  --salida  "D:\...\SAVIA_SALUD_organizado.xlsx"
```

### Muchas facturas (una carpeta con todos los exports)

```cmd
py tools\organizar_objeciones_savia.py ^
  --entrada "D:\...\OBJECIONES SAVIA" ^
  --salida  "D:\...\SAVIA_SALUD_organizado.xlsx"
```

### Conservando el código completo del Dispensario

```cmd
py tools\organizar_objeciones_savia.py ^
  --entrada "D:\...\OBJECIONES SAVIA" ^
  --salida  "D:\...\SAVIA_SALUD_organizado.xlsx" ^
  --codigo completo
```

---

## 7) Qué imprime

Al terminar, además del Excel, muestra un resumen:

```
Excel organizado: ...\SAVIA_SALUD_organizado.xlsx
  Facturas: 1  |  Objeciones: 4
  Valor glosado total: $5,763,297
  Códigos de objeción:
    CL01: 1
    CL03: 1
    CL08: 1
    SO08: 1
```

---

## 8) Instalación (una vez)

```cmd
py -m pip install openpyxl
```

---

## 9) Limitaciones conocidas

- **Extracción por texto**: `Servicio`, `Cantidad_Servicio` y `Valor_Unitario`
  se derivan de la redacción de la objeción. Si el Dispensario cambia el estilo
  de redacción, esos tres campos pueden requerir revisión manual (los demás —
  factura, código de servicio, valor glosado, código de objeción, observación —
  vienen de columnas y son exactos).
- **Mapeo de código**: la regla `corto` (4 primeros caracteres) coincide con la
  plantilla de SAVIA para los casos verificados. Si SAVIA usa un catálogo de
  códigos propio para algún concepto, usar `--mapa-codigos` para forzarlo.
