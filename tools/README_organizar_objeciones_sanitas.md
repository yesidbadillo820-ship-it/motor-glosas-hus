# Guía: `organizar_objeciones_sanitas.py` — Objeciones de SANITAS → OBJECIONES (DGH)

Convierte el Excel de glosas de **SANITAS** (hoja `Glosa`, 7 columnas) al
**formato de trabajo de 16 columnas** (hoja `OBJECIONES`) que se importa en
Dinámica Gerencial — el mismo de FAMISANAR, SAVIA y el Dispensario.

---

## 1) La trampa del archivo de SANITAS (léala antes de tocar nada)

Los encabezados están **mal rotulados**: la **segunda** columna se llama otra
vez «NUMERO DE FACTURA», pero lo que trae es el **código de glosa**.

```
NUMERO DE FACTURA | NUMERO DE FACTURA | VALOR REAL GLOSA | CODIGO PROCEDIMIENTO | …
   HUS0000548650  |      CO2301       |       2350       |        903883        | …
        ↑                  ↑
     factura        código de GLOSA (no es la factura)
```

Un lector que resuelva las columnas **por nombre** se equivoca en silencio:
tomaría «CODIGO PROCEDIMIENTO» como código de glosa y el archivo saldría malo
sin que nadie lo note hasta que DGH lo rechace. Por eso este bot:

1. lee las columnas **por posición**, y
2. **verifica el contenido antes de procesar** (`verificar_columnas`): la
   primera columna debe tener facturas (prefijo + 5 dígitos o más) y la segunda
   códigos de glosa (`CO2301`). Si no cuadra, **se detiene con un mensaje
   claro** en vez de entregar un archivo silenciosamente malo.

## 2) Mapeo de columnas

| Salida | Origen |
|---|---|
| `CRNCXC` | col 0, factura a 10 dígitos |
| `CRNCONOBJ` | col 1, el código de glosa limpio (`TA08 01` → `TA0801`) |
| `CROVALOBJ` | col 2, `VALOR REAL GLOSA` |
| `SLNSERPRO` | del **cruce contra el DGH**, partiendo del código y el nombre de las cols 3 y 4 |
| `CRDOBSERV` | `<código> <nombre procedimiento>: <observaciones>$<valor>` |
| `CDFECDOC` / `CROFECOBJ` | `--fecha` (por defecto hoy) |
| `CDCONSEC` | consecutivo **por factura** (vuelve a 1 en los archivos por factura) |
| `CROTIPOBJ` | **0 = ADMINISTRATIVA**, **1 = MEDICA**, **2 = MIXTA**, por factura |
| `CTNCENCOS` | **siempre vacía** |
| resto | vacías |

SANITAS **sí** manda el código del servicio (a diferencia de FAMISANAR, que lo
esconde en el texto). Aun así se cruza contra el export del DGH: la regla del
área es que en `SLNSERPRO` no puede ir un código que el DGH no reconozca en esa
factura. El motor del cruce es el común, `tools/_cruce_dgh.py`.

## 3) Comando

```powershell
py tools\organizar_objeciones_sanitas.py `
  --entrada       "D:\...\SANITAS_4_SEPTIEMBRE.xlsx" `
  --servicios-dgh "D:\...\SERVICIOS_FACTURADOS_DGH.xlsx" `
  --salida        "D:\...\OBJECIONES_SANITAS_04092026.xlsx" --consolidado `
  --reporte-cruce "D:\...\CRUCE_SANITAS_04092026.xlsx" `
  --fecha 2026-09-04
```

Sin `--consolidado` genera un archivo por factura. `--reporte-cruce` escribe el
respaldo del auditor (hojas `CRUCE`, `REVISAR`, `RESUMEN`) y necesita
`--servicios-dgh`.

## 4) Lo que hay que mirar en los archivos de SANITAS

**SANITAS parte el valor de un mismo servicio en varias objeciones.** En el lote
del 4 de septiembre mandó **50 objeciones de $2.350** para **25 glucometrías**
facturadas: el valor total coincide exacto ($117.500), pero en DGH van a
aparecer dos objeciones sobre el mismo servicio. El texto de esas filas dice
«Glosa Calculada Afiliado», así que parece un reparto entre la porción del
afiliado y la de la entidad. **No es sobre-objeción** —conviene comprobarlo
sumando por código, no contando renglones— pero hay que saberlo antes de subir.

## 5) Verificación

El bot comprueba las reglas fijas sobre el archivo terminado
(`verificar_reglas` de `tools/_cruce_dgh.py`) y lo dice en el log. Pruebas:
`tests/test_tools/test_organizar_objeciones_sanitas.py`.

## 6) Instalación (una vez)

```cmd
py -m pip install openpyxl
```
