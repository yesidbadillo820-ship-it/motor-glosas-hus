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
  Dispensario). El bot avisa cuántas quedaron así en el log. Con
  `--servicios-dgh` la mayoría se resuelve igual: el nombre del insumo sí está
  en el texto y el valor termina de identificarlo (sección 3).

### Homologación FAMISANAR → HUS (automática)

Los códigos que FAMISANAR escribe NO son (todos) los del HUS. El bot los
homologa solo (se desactiva con `--sin-homologar`):

| Tipo | Regla | Ejemplo |
|---|---|---|
| CUPS (6 dígitos) | Tal cual — estándar nacional | `903867` → `903867` |
| Medicamentos con letra U/P | Se quita la letra de FAMISANAR | `U20162259-04` → `20162259-04` (METOCLOPRAMIDA, verificado contra EMSSANAR) |
| Dispositivos 9101xxxx | Equivalencia FMQ fija, confirmada contra el archivo de trabajo LOTE_02 | `91017235` → `FMQ0112` (catéter IV 18, $5.800 idéntico); `91012136` → `FMQ0182-1` (llave 3 vías); `91017424` → `FMQ0952` (electrodo ECG adulto, 3×$800); `91017278` → `FMQ0159` (bolsa recolectora orina, $18.100 idéntico) |
| Dispositivos NUEVOS sin equivalencia | Quedan tal cual + WARNING en el log | lo mejor es pasar `--servicios-dgh` (sección 3, resuelve el código solo); si no, agregarlos con `--mapa-servicios equivalencias.json` (`{"9101XXXX": "FMQNNNN", ...}`) — pisa/extiende las fijas |

> **Ojo:** la homologación por reglas sólo alcanza para los CUPS y los
> medicamentos. Los dispositivos que FAMISANAR nombra con su catálogo IUM
> (`91022534`, `91018425`…) **no existen en el DGH**: si se cargan así, el
> renglón no se reconoce. Para eso está el cruce contra el export de servicios
> facturados — sección 3.

## 3) El cruce contra los servicios facturados del DGH (`--servicios-dgh`)

Con el **export de servicios facturados del DGH** (el DGReport: `SERVICIOS DGH`,
`DESCRIPCION INSTITUCIONAL`, `SLNSERPRO_CUPS`, `CODIGO_MEDICAMENTO`,
`NOM_CENTRO_COSTO`, `FACTURA`, `CAT_SERVICIOS`, `Vr_SERVICIO`) el bot busca,
**dentro de esa misma factura**, de qué servicio habla cada objeción. Cuando lo
encuentra:

- `SLNSERPRO` queda con el **código real del hospital** (el que DGH reconoce),
  no con el que escribió FAMISANAR.

> **`CTNCENCOS` va SIEMPRE vacía**, con cruce o sin él — es la regla del área
> para el archivo de FAMISANAR. El export del DGH sólo trae el **nombre** del
> centro de costo («URGENCIAS ADULTOS») y esa columna es de código, así que
> llenarla con el nombre sería escribir un dato que no corresponde. El nombre
> sí aparece en el reporte de cruce, como pista para ubicar el renglón.

### Cómo lo busca

Puntúa cada renglón del DGH por tres cosas:

- **código** — contra las tres columnas de código del DGH, tolerando las formas
  en que FAMISANAR los escribe (`P32606-02` = `32606-2`, `U41072-10` =
  `41072-10`, `903437H` = `903437`);
- **nombre** — palabra por palabra, separando número y unidad (`1ML` = `1 ML`) y
  probando también lo que va después del guion, porque FAMISANAR antepone la
  categoría (`LINEA INFUSION E INYECCION - JERINGA 1 ML…`);
- **valor** — unitario y del renglón. Si en toda la factura ese valor lo tiene
  un solo servicio, identifica la línea aunque el código y el nombre sean de
  otro catálogo. Si lo comparten varios, desempata el nombre.

Cada renglón queda con su **nivel de confianza**:

| Confianza | Qué significa |
|---|---|
| **ALTA** | coincide el código (o el nombre exacto) **y** el valor |
| **MEDIA** | coincide una cosa fuerte y el valor la respalda |
| **BAJA** | se ubicó por valor o por parecido flojo — **verificar antes de subir** |
| **SIN CRUCE** | el texto no nombra ningún servicio; se completa a mano |

**Nunca se inventa un servicio.** Sin cruce confiable queda lo que se sabía por
el texto y el renglón se reporta.

### El reporte de trabajo (`--reporte-cruce`)

Un Excel aparte —no es el que se sube— con tres hojas:

| Hoja | Contenido |
|---|---|
| `CRUCE` | fila por fila: qué se leyó del texto, con qué renglón del DGH cruzó y por qué |
| `REVISAR` | sólo lo que hay que confirmar a mano (BAJA, sin cruce o con aviso) |
| `RESUMEN` | por factura: objeciones, valor objetado y cuántas quedan por revisar |

Un aviso que vale la pena mirar: **"el nombre del servicio en el archivo de
FAMISANAR no coincide con el del DGH"**. Pasa cuando FAMISANAR buscó el código
en el catálogo CUPS y no en el del hospital (ej. `150101`, que en el DGH es una
fórmula enteral y en CUPS una biopsia). El cruce por valor suele ser el
correcto, pero hay que confirmarlo.

### Qué cambia en la práctica

Corrida real del 1 de septiembre (398 objeciones, 14 facturas, $31.439.029):

| | Sin `--servicios-dgh` | Con `--servicios-dgh` |
|---|---|---|
| `SLNSERPRO` que el DGH reconoce | 184 (46 %) | **395 (99 %)** |
| `SLNSERPRO` con un código que no existe en el DGH | 191 | **0** |
| `SLNSERPRO` vacío | 23 | 3 |

---

## 4) Mapeo de campos (FAMISANAR → 16 columnas)

| Salida | Origen | Cómo |
|---|---|---|
| `CRNCXC` | `NRO_FACTURA` | Formato largo: `HUS532670` → `HUS0000532670`. |
| `CRNCONOBJ` | `CODIGO_DEVOLUCION` | Ya viene de 6 caracteres (`CL0801`, `CO0701`…): tal cual. Red de seguridad: si viniera de 4 se completa con `--codigo-sufijo`. |
| `SLNSERPRO` | texto de `OBSERVACION` (+ export del DGH) | Regex sobre "CÓDIGO &lt;x&gt;" (acepta dígitos, letras y guiones; con o sin tilde) o, si la etiqueta viene vacía, el código pegado adelante del nombre. Con `--servicios-dgh` se reemplaza por el código real del hospital. Vacío si no hay nada. |
| `CROVALOBJ` | `VALOR DEVOLUCION` | Directo (número). |
| `CRDOBSERV` | `OBSERVACION` | `"<código> <texto>$<valor>"`. Colapsa las corridas largas de espacios del export. Anti-duplicado con cuidado: quita un `$monto` final SOLO si es el mismo valor de la objeción; si es otro monto (p. ej. el valor unitario facturado), se conserva. |
| `CDFECDOC`, `CROFECOBJ` | — | `--fecha` (default hoy), FECHA CORTA sin horas. |
| `CDCONSEC` | — | Consecutivo POR FACTURA (1-1-1, 2-2-2…), como texto; standalone reinicia en 1. |
| `CROTIPOBJ` | — | **0 = ADMINISTRATIVA** (solo TA/FA/SO/AU/CO…), **1 = MEDICA** (solo CL), **2 = MIXTA** (CL junto con administrativas). Se decide **por factura**: todas sus objeciones salen con el mismo valor. |
| `CTNCENCOS` | — | **Siempre vacía** (regla del área), aunque el cruce sepa el centro de costo. |
| `CROCLAOBJ`, `GENUSUARIO4` | — | `0` (número) y `'999'` (texto). |
| resto | — | Vacíos. Formatos de celda 1:1 con los archivos reales. |

## 5) Comandos típicos

```cmd
:: Con el export del DGH (lo recomendado: SLNSERPRO y centro de costo reales)
py tools\organizar_objeciones_famisanar.py ^
  --entrada       "FAMISANAR_1_SEPTIEMBRE.xlsx" ^
  --servicios-dgh "SERVICIOS_FACTURADOS_DGH.xlsx" ^
  --salida        "OBJECIONES_FAMISANAR_01-09-2026.xlsx" --consolidado ^
  --reporte-cruce "CRUCE_FAMISANAR_01-09-2026.xlsx" ^
  --fecha 2026-09-01

:: Un archivo por factura (lo normal)
py tools\organizar_objeciones_famisanar.py ^
  --entrada "FAMISANAR_11.35.1.xlsx" ^
  --salida  "OBJECIONES_FAMISANAR"

:: Todo junto en un solo Excel
py tools\organizar_objeciones_famisanar.py ^
  --entrada "FAMISANAR_11.35.1.xlsx" ^
  --salida  "OBJECIONES_FAMISANAR_UNIFICADO.xlsx" --consolidado
```

## 6) Argumentos del CLI

| Flag | Default | Uso |
|---|---|---|
| `--entrada` | — (requerido) | Excel de FAMISANAR (4 columnas). |
| `--salida` | — (requerido) | Carpeta destino (o `.xlsx` si `--consolidado`). |
| `--prefijo` | `OBJECIONES_FAMISANAR` | Prefijo de los archivos por factura. |
| `--consolidado` | off | Un solo Excel con todas las facturas. |
| `--fecha` | hoy | `YYYY-MM-DD` para `CDFECDOC`/`CROFECOBJ`. |
| `--codigo-sufijo` | `01` | Solo red de seguridad para códigos de 4 chars. |
| `--servicios-dgh` | — | Export de servicios facturados del DGH: resuelve `SLNSERPRO` y llena `CTNCENCOS` (sección 3). |
| `--reporte-cruce` | — | Excel de trabajo con el detalle del cruce (necesita `--servicios-dgh`). |
| `--mapa-codigos` | — | JSON para forzar códigos de objeción puntuales. |
| `--consecutivo` | `1` | Número inicial del consecutivo por factura. |
| `--log` | — | Log adicional a archivo. |

## 7) Instalación (una vez)

```cmd
py -m pip install openpyxl
```

## 8) Verificación de referencia

Probado contra `FAMISANAR_11.35.1.xlsx` real: 37 objeciones, 2 facturas
(`HUS0000532670`: 19, `HUS0000525618`: 18), $4.256.442 glosados, 30 códigos de
servicio extraídos del texto y 7 filas "AUD EXTRA" sin código (esperado).
Fila a fila contra la fuente: 37/37 coherentes; formatos de celda 16/16
idénticos a los archivos reales. Tests: `tests/test_tools/test_organizar_objeciones_famisanar.py`.
