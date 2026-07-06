# Tablero de Radicación y Cartera — `tablero_cartera.py`

Tablero de control para el área de **Cuentas Médicas y Cartera** de la ESE
Hospital Universitario de Santander. Es el paso **aguas abajo** del radicador
(`tools/radicar_facturacion.py`): una vez que las facturas están radicadas ante
las entidades, este módulo **analiza cuánto se radicó, cuánto se glosó/devolvió,
cuánto se pagó y cuánto queda debiendo**, y lo muestra en un tablero HTML
profesional para todo el equipo.

En una sola corrida:

1. **Consolida la radicación** — lee uno o varios reportes del radicador
   (CSV/XLSX) y arma el inventario de facturas radicadas por entidad y mes.
2. **Cruza el seguimiento de cartera** — una planilla Excel que el equipo
   alimenta a mano (valor glosado, devuelto, pagado, fechas, notas crédito),
   unida por **número de factura**.
3. **Calcula los indicadores**: radicado, glosado/devuelto, pagado, **saldo (lo
   que queda debiendo)**, % de recaudo, % de glosa y la **mora por tramos**
   (aging 0-30 / 31-60 / 61-90 / +90 días).
4. **Genera el tablero HTML** autocontenido (se abre con doble clic, funciona
   sin internet): KPIs, gráficos y una tabla filtrable por factura.

> **Seguro por defecto**: NO toca las carpetas de soportes ni el share. Solo
> **lee** los reportes y la planilla, y **escribe** el HTML (y, con
> `--crear-plantilla`, la planilla inicial pre-cargada con lo radicado).

---

## Instalación

Núcleo: **solo librería estándar** de Python 3.11+. Para leer/escribir Excel
(`.xlsx`):

```bash
py -m pip install openpyxl
```

Dejá el script dentro de `tools/` (junto a `radicar_facturacion.py` y
`_tablero_html.py`): reutiliza el catálogo de entidades y la normalización de
factura del radicador.

---

## Flujo de trabajo (3 pasos)

### 1) Generar la planilla de seguimiento (una vez por periodo)

Pre-carga una fila por factura radicada con `FACTURA`, `ENTIDAD` y
`VALOR_RADICADO` ya rellenos; el resto en blanco para que cartera complete.

```powershell
py tools\tablero_cartera.py --radicacion "$env:USERPROFILE\Desktop\radicacion_fe.csv" `
    --crear-plantilla "$env:USERPROFILE\Desktop\seguimiento_cartera.xlsx"
```

### 2) Cartera completa la planilla

En `seguimiento_cartera.xlsx` (columnas resaltadas en amarillo) el equipo va
diligenciando, factura por factura: la **fecha de radicación**, el **valor
glosado/devuelto**, el **valor pagado** y su fecha, el **motivo** de la glosa y
el número de **nota crédito**.

### 3) Generar el tablero

```powershell
py tools\tablero_cartera.py --radicacion "$env:USERPROFILE\Desktop\radicacion_fe.csv" `
    --seguimiento "$env:USERPROFILE\Desktop\seguimiento_cartera.xlsx" `
    --salida "$env:USERPROFILE\Desktop\tablero_cartera.html"
```

Abrí `tablero_cartera.html` con doble clic. Cada vez que cartera actualice la
planilla, volvé a correr el paso 3 para refrescar el tablero.

> Podés pasar **varios** reportes de radicación a `--radicacion` (un mes o el
> acumulado), separados por espacio.

---

## El tablero (4 módulos)

| Módulo | Qué muestra |
|---|---|
| **Radicación** | KPIs (facturas y valor radicado), barras de radicado/pagado/saldo por entidad y tendencia mensual radicado vs pagado. |
| **Glosas y devoluciones** | Valor glosado/devuelto, % de glosa y top motivos por valor. |
| **Cartera (aging)** | Saldo por tramos de mora (0-30 / 31-60 / 61-90 / +90 días) y estado de cartera por factura. |
| **Ayuda a radicar** | Distribución de estados del radicador (LISTA / REVISAR / FALTAN_SOPORTES…) para saber qué falta. |

Más una **tabla por factura** con búsqueda, filtros por entidad y estado, y
columnas ordenables (clic en el encabezado).

### Estados de cartera

| Estado | Significado |
|---|---|
| `PAGADA` | El pago cubre el valor radicado. |
| `PAGO_PARCIAL` | Hay pago, pero queda saldo. |
| `GLOSADA_DEVUELTA` | Tiene glosa/devolución y aún sin pago. |
| `RADICADA_TRAMITE` | Radicada, en trámite normal (sin glosa ni pago aún). |
| `PENDIENTE_RADICAR` | Sin fecha de radicación cargada en el seguimiento. |

El **saldo** = `radicado − pagado` (lo que la entidad queda debiendo). La parte
**objetada** del saldo es `glosado + devuelto`; el resto es trámite por pagar.

---

## La planilla de seguimiento

Encabezados que reconoce (tolerante a variantes/mayúsculas):

| Columna | Qué va |
|---|---|
| `FACTURA` | Número de factura (llave de cruce). **Requerida.** |
| `FECHA_RADICACION` | Fecha real de radicación ante la entidad (`AAAA-MM-DD` o `DD/MM/AAAA`). |
| `VALOR_GLOSADO` | Valor objetado por la entidad. |
| `VALOR_DEVUELTO` | Valor devuelto (no admitido). |
| `VALOR_PAGADO` | Valor efectivamente pagado. |
| `FECHA_PAGO` | Fecha del pago. |
| `MOTIVO_GLOSA` | Causal/motivo de la glosa o devolución. |
| `NOTA_CREDITO` | Número de la nota crédito. |
| `ESTADO` | Opcional: fuerza el estado de cartera (si se deja vacío se calcula solo). |
| `OBSERVACIONES` | Notas libres. |

Los valores aceptan número o texto en formato colombiano (`$ 1.234.567,89`).

---

## Opciones del CLI

| Flag | Descripción |
|---|---|
| `--radicacion` | Uno o varios reportes del radicador (CSV/XLSX). *Requerido.* |
| `--seguimiento` | Planilla Excel de cartera (glosas/pagos). Opcional. |
| `--salida` | HTML del tablero (def.: `tablero_cartera.html`). |
| `--crear-plantilla` | Genera la planilla pre-cargada con lo radicado y termina. |
| `--perfiles` | Catálogo de entidades (def.: `data/perfiles_radicacion.json`). |
| `--fecha-corte` | `AAAA-MM-DD` para calcular la mora (def.: hoy). |
| `--titulo` | Título que se muestra en el tablero. |
| `--log` | Archivo de log opcional. |

---

## Cómo encaja con el resto del motor

```
FACTURACIÓN → [ radicar_facturacion.py ] → RADICACIÓN → [ tablero_cartera.py ] → CONTROL DE CARTERA
   (lote)       tipifica, valida, arma       (portal)       analiza pagos,           (HTML para el
                                                              glosas y saldo            área y dirección)
```

- Reutiliza el catálogo de entidades (`data/perfiles_radicacion.json`) y la
  normalización de factura del radicador: el cruce radicado→pagado es idéntico.
- El tablero es **autocontenido** (un solo `.html` con todo embebido), pensado
  para compartirse por red o correo y abrirse sin internet.
- Las respuestas a glosas las trabaja el motor de glosas
  (`responder_glosas_*.py`, `motor_glosas_hus.py`); este tablero lleva el
  **control de cartera** de lo radicado.
