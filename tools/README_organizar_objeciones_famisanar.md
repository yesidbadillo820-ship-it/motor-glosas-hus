# Guía: `organizar_objeciones_famisanar.py` — Objeciones de FAMISANAR → formato de trabajo (16 columnas)

Herramienta que toma el Excel de devoluciones/glosas que entrega **FAMISANAR**
(export "DEVYGLOSAS…", 4 columnas) y lo convierte al **formato de trabajo de 16
columnas** (hoja `OBJECIONES`) — el mismo que se usa para SAVIA y el
Dispensario. Es el bot hermano de `organizar_objeciones_savia.py`, con las
mismas 7 reglas del formato.

---

## 1) Por qué existe

FAMISANAR entrega muy poca información en columnas:

```
NRO_FACTURA | CODIGO_DEVOLUCION | VALOR DEVOLUCION | OBSERVACION
```

**No trae columna de código de servicio.** El código viene EMBEBIDO dentro del
texto de la observación:

> "…SERVICIO SIN COBERTURA  LOSARTAN (WIN) TABLETA POR 50 MG **CÓDIGO
> U19965499-11** VALOR UNITARIO FACTURADO POR IPS $200"

Este bot **extrae el código del texto** para llenar `SLNSERPRO` y arma el
archivo completo de 16 columnas, un .xlsx por factura (o consolidado).

## 2) Qué extrae y qué no

- ✅ Filas de **cobertura** ("SERVICIO SIN COBERTURA … CÓDIGO X") → código del
  insumo/medicamento (`91017235`, `U19965499-11`, `P32606-02`, …).
- ✅ Filas de **tarifas** ("SE REALIZA OBJECIÓN POR MAYOR VALOR … CÓDIGO X") →
  código CUPS (`903867`, `735301`, `890202`, …).
- ⚠️ Filas cortas tipo **"AUD EXTRA - …"** no traen código en el texto →
  `SLNSERPRO` queda **vacío** (igual que las estancias en los archivos del
  Dispensario). El bot avisa cuántas quedaron así en el log.

### Homologación FAMISANAR → HUS (automática)

Los códigos que FAMISANAR escribe NO son (todos) los del HUS. El bot los
homologa solo (se desactiva con `--sin-homologar`):

| Tipo | Regla | Ejemplo |
|---|---|---|
| CUPS (6 dígitos) | Tal cual — estándar nacional | `903867` → `903867` |
| Medicamentos con letra U/P | Se quita la letra de FAMISANAR | `U20162259-04` → `20162259-04` (METOCLOPRAMIDA, verificado contra EMSSANAR) |
| Dispositivos 9101xxxx | Equivalencia FMQ fija, confirmada contra el archivo de trabajo LOTE_02 | `91017235` → `FMQ0112` (catéter IV 18, $5.800 idéntico); `91012136` → `FMQ0182-1` (llave 3 vías); `91017424` → `FMQ0952` (electrodo ECG adulto, 3×$800); `91017278` → `FMQ0159` (bolsa recolectora orina, $18.100 idéntico) |
| Dispositivos NUEVOS sin equivalencia | Quedan tal cual + WARNING en el log | agregarlos con `--mapa-servicios equivalencias.json` (`{"9101XXXX": "FMQNNNN", ...}`) — pisa/extiende las fijas |

## 3) Mapeo de campos (FAMISANAR → 16 columnas)

| Salida | Origen | Cómo |
|---|---|---|
| `CRNCXC` | `NRO_FACTURA` | Formato largo: `HUS532670` → `HUS0000532670`. |
| `CRNCONOBJ` | `CODIGO_DEVOLUCION` | Ya viene de 6 caracteres (`CL0801`, `CO0701`…): tal cual. Red de seguridad: si viniera de 4 se completa con `--codigo-sufijo`. |
| `SLNSERPRO` | texto de `OBSERVACION` | Regex sobre "CÓDIGO &lt;x&gt;" (acepta dígitos, letras y guiones; con o sin tilde). Vacío si no hay. |
| `CROVALOBJ` | `VALOR DEVOLUCION` | Directo (número). |
| `CRDOBSERV` | `OBSERVACION` | `"<código> <texto>$<valor>"`. Colapsa las corridas largas de espacios del export. Anti-duplicado con cuidado: quita un `$monto` final SOLO si es el mismo valor de la objeción; si es otro monto (p. ej. el valor unitario facturado), se conserva. |
| `CDFECDOC`, `CROFECOBJ` | — | `--fecha` (default hoy), FECHA CORTA sin horas. |
| `CDCONSEC` | — | Consecutivo POR FACTURA (1-1-1, 2-2-2…), como texto; standalone reinicia en 1. |
| `CROTIPOBJ` | — | Por factura: solo TA/FA/SO/AU/CO → 0; solo CL → 1; mezcla con CL → 2. |
| `CROCLAOBJ`, `GENUSUARIO4` | — | `0` (número) y `'999'` (texto). |
| resto | — | Vacíos. Formatos de celda 1:1 con los archivos reales. |

## 4) Comandos típicos

```cmd
:: Un archivo por factura (lo normal)
py tools\organizar_objeciones_famisanar.py ^
  --entrada "FAMISANAR_11.35.1.xlsx" ^
  --salida  "OBJECIONES_FAMISANAR"

:: Todo junto en un solo Excel
py tools\organizar_objeciones_famisanar.py ^
  --entrada "FAMISANAR_11.35.1.xlsx" ^
  --salida  "OBJECIONES_FAMISANAR_UNIFICADO.xlsx" --consolidado
```

## 5) Argumentos del CLI

| Flag | Default | Uso |
|---|---|---|
| `--entrada` | — (requerido) | Excel de FAMISANAR (4 columnas). |
| `--salida` | — (requerido) | Carpeta destino (o `.xlsx` si `--consolidado`). |
| `--prefijo` | `OBJECIONES_FAMISANAR` | Prefijo de los archivos por factura. |
| `--consolidado` | off | Un solo Excel con todas las facturas. |
| `--fecha` | hoy | `YYYY-MM-DD` para `CDFECDOC`/`CROFECOBJ`. |
| `--codigo-sufijo` | `01` | Solo red de seguridad para códigos de 4 chars. |
| `--mapa-codigos` | — | JSON para forzar códigos de objeción puntuales. |
| `--consecutivo` | `1` | Número inicial del consecutivo por factura. |
| `--log` | — | Log adicional a archivo. |

## 6) Instalación (una vez)

```cmd
py -m pip install openpyxl
```

## 7) Verificación de referencia

Probado contra `FAMISANAR_11.35.1.xlsx` real: 37 objeciones, 2 facturas
(`HUS0000532670`: 19, `HUS0000525618`: 18), $4.256.442 glosados, 30 códigos de
servicio extraídos del texto y 7 filas "AUD EXTRA" sin código (esperado).
Fila a fila contra la fuente: 37/37 coherentes; formatos de celda 16/16
idénticos a los archivos reales. Tests: `tests/test_tools/test_organizar_objeciones_famisanar.py`.
