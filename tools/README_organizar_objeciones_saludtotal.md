# Guía: `organizar_objeciones_saludtotal.py` — Objeciones de SALUD TOTAL → cargue masivo (16 columnas)

Toma el Excel de **notificación de glosas de SALUD TOTAL** (export
"NotificacionGLS_…", 6 columnas) y lo convierte al **formato de trabajo de 16
columnas** (hoja `OBJECIONES`) para el **cargue masivo de recepción** — el
mismo layout que usan los bots de SAVIA y FAMISANAR.

## 1) Qué recibe y qué entrega

**Entrada (SALUD TOTAL):**

```
NumeroFac_ | NombreServicio | CantidadFac | ValorGlosaTotalxServ | Observaciones | CodMotvGlosaEspc
464306     | FOSFORO EN ... | 13          | 95082                | se objeta ... | CL0801
```

**Salida:** las 16 columnas del formato (un `.xlsx` por factura, o todo
unificado con `--consolidado`), con las reglas de siempre:

| Columna | Cómo queda |
|---|---|
| `CRNCXC` | La factura pelada se completa: `464306` → `HUS0000464306` (`--prefijo-factura`). |
| `CRNCONOBJ` | `CodMotvGlosaEspc` tal cual (ya viene de 6: `CL0801`, `TA0601`…). |
| `SLNSERPRO` | **Vacío** (Salud Total no manda código de servicio, solo el nombre) — u homologado por NOMBRE si se pasa `--maestro` (ver §2). |
| `CROVALOBJ` | `ValorGlosaTotalxServ` con el lector único de pesos (`tools/_dinero.py`). |
| `CRDOBSERV` | `"<código> <observación>$<valor>"`, con el encoding dañado reparado («Ã“» → «Ó»). |
| `CDCONSEC` | Consecutivo por factura, como texto (1-1-1…, 2-2-2…); standalone reinicia en 1. |
| `CROTIPOBJ` | Por factura: solo TA/FA/SO/AU/CO → 0; solo CL → 1; mezcla → 2. |
| Fechas / tipos / formatos | Fecha corta sin horas; `GENUSUARIO4='999'` texto; los 16 `number_format` del archivo real. |

## 2) El código de servicio (`--maestro`)

Salud Total **no** envía el código del servicio — solo el nombre (180
distintos en el archivo de agosto/2026: apósitos, medicamentos, derechos de
sala…). El bot NO inventa códigos:

- **Sin `--maestro`**: `SLNSERPRO` queda vacío (igual que las estancias en los
  archivos del Dispensario).
- **Con `--maestro archivo.xlsx`**: homologa por **nombre normalizado, match
  exacto**. El maestro puede ser:
  1. un **OBJECIONES ya trabajado** (tipo `OBJECIONES_LOTE_02…`): saca los
     pares código-nombre de los textos `(FMQ0159-BOLSA RECOLECTORA…)`;
  2. un **listado simple** con columnas código | nombre.
  Lo que no matchea queda vacío y se lista en el log.
- `--mapa-servicios equivalencias.json` (`{"NOMBRE": "CODIGO"}`) se suma al
  maestro y le gana en caso de choque.

## 3) Comandos típicos

```cmd
:: Un archivo por factura (lo normal)
py tools\organizar_objeciones_saludtotal.py ^
  --entrada "PARA_MASIVO.xlsx" --salida "OBJECIONES_SALUDTOTAL"

:: Todo junto en un solo Excel
py tools\organizar_objeciones_saludtotal.py ^
  --entrada "PARA_MASIVO.xlsx" --salida "OBJECIONES_SALUDTOTAL_UNIFICADO.xlsx" --consolidado

:: Con maestro para llenar los códigos de servicio por nombre
py tools\organizar_objeciones_saludtotal.py ^
  --entrada "PARA_MASIVO.xlsx" --salida "SALIDA" --maestro "OBJECIONES_LOTE_02.xlsx"
```

## 4) Verificación de referencia

Probado contra `PARA_MASIVO.xlsx` real (agosto/2026): 227 objeciones, 2
facturas (`HUS0000464306`: 197, CROTIPOBJ=2; `HUS0000464511`: 30, CROTIPOBJ=0),
**$67.110.206** glosados; 227/227 filas fieles a la fuente y 3 textos con
encoding dañado reparados. Tests:
`tests/test_tools/test_organizar_objeciones_saludtotal.py`.
