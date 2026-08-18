# Quitarle al detallado lo que ya se aceptó (`descontar_aceptado_detallado.py`)

Cuando el equipo termina de responder las glosas en la macro, algunos ítems
quedan como **SE ACEPTA** con un **VALOR ACEPTADO**: esa plata el hospital ya
no la está reclamando. Este bot **se la quita al detallado de cada factura** y
vuelve a cuadrar los totales, para que lo que se radica sea exactamente lo que
se sigue reclamando.

Trabaja sobre los Excel **por factura** (los que salen del ajustador o de
`glosas_adres_por_factura.py`) y sobre la **macro de respuesta** del paquete.

---

## Cómo se usa

```
py tools\descontar_aceptado_detallado.py ^
    --detallados "D:\...\EXCEL_POR_FACTURA_31068" ^
    --macro      "D:\...\RTA GLOSA ADRES PAQ 31068 - ok ok.xlsx" ^
    --salida     "D:\...\POR_FACTURA_31068_SIN_ACEPTADO" ^
    --bitacora   "D:\...\DESCUENTOS_31068.csv"
```

Requiere una sola vez: `py -m pip install openpyxl`

| Opción | Para qué |
|---|---|
| `--detallados` | La carpeta (o el patrón) con un Excel por factura. |
| `--macro` | El Excel de la macro, con la columna **VALOR ACEPTADO**. |
| `--salida` | Carpeta donde deja los archivos ya descontados. Los originales **no se tocan**. |
| `--bitacora` | CSV con una línea por servicio descontado. Muy recomendado. |

---

## Qué hace exactamente

1. **De la macro se queda solo con lo aceptado.** Únicamente las filas con
   VALOR ACEPTADO mayor que cero. Las **SE OBJETA** y las **SE SUBSANA** se
   siguen reclamando completas, así que no tocan el detallado.
2. **Cruza contra el detallado.** No por código a secas: el detallado usa el
   código del hospital (`FMQ0046`) y la macro el del ADRES
   (`2016DM-0000315-R2`). Se usa el mismo motor de rondas del ajustador —
   código → descripción → cantidad y valor → valor — con emparejamiento único,
   para que dos servicios no se roben el mismo descuento.
3. **Le baja la plata al renglón** y recalcula el VR UNIT para que cuadre con
   la cantidad.
4. **Recalcula el subtotal, el total de la orden y el total en letras.**
5. **Lo que no cruza se informa, no se adivina.** Queda en la bitácora.

El formato del detallado no se toca: celdas combinadas, anchos, bordes y
formato de moneda quedan igual.

### Ejemplo (factura HUS352890 del paquete 31068)

```
ANTES    39145 CONSULTA DE URGENCIAS   1,00   $85.800  →  VR ENT  $85.800
         FMQ0046 VENDA DE GASA         5,00    $9.400  →  VR ENT  $47.000
         SUBTOTAL $132.800

En la macro, la consulta quedó SE ACEPTA con VALOR ACEPTADO $2.400.

DESPUÉS  39145 CONSULTA DE URGENCIAS   1,00   $83.400  →  VR ENT  $83.400
         FMQ0046 VENDA DE GASA         5,00    $9.400  →  VR ENT  $47.000
         SUBTOTAL $130.400
```

---

## El detalle que casi hace perder $106 millones

Algunos procedimientos quirúrgicos abren renglones **sin número de
consecutivo** (honorarios de cirujano, ayudantía, derechos de sala). En la
mayoría de las facturas ese desglose **ya está incluido** en el renglón que lo
encabeza y no vuelve a sumar. Pero en **50 de las 320 facturas del paquete
31068 sí suma aparte**.

Si el bot recalculara el subtotal desde cero, en esas 50 facturas descontaría
de más: la primera corrida daba **$607 millones** en vez de **$714 millones**.

Por eso el bot **nunca recalcula el subtotal desde cero**. Toma el que ya trae
el archivo —que es el bueno— y solo le resta lo que descontó. Cuando hay
renglones sin consecutivo, mira cuál de las dos sumas se parece al subtotal del
archivo y decide **factura por factura**.

---

## La bitácora (lo que hay que revisar)

Una línea por servicio descontado, con separador `;` para que Excel la abra
directo:

| Columna | Qué dice |
|---|---|
| FACTURA / ESTADO | El número y si quedó AJUSTADA, SIN_ACEPTADO o ERROR. |
| SUBTOTAL_ANTES / SUBTOTAL_DESPUES | El valor de la factura antes y después. |
| DESCONTADO | Lo que se le quitó en total. |
| ACEPTADO_EN_LA_MACRO | Lo que dice la macro que se aceptó. |
| **CUADRA** | **SI** o **NO**: compara las dos anteriores. |
| CODIGO / SERVICIO | El renglón tocado. |
| VR_ENT_ANTES / ACEPTADO / VR_ENT_DESPUES | La cuenta del renglón. |
| CRUCE_POR | Por dónde cruzó (código, descripción, valor…). |
| CAUSALES | Las causales de glosa de ese ítem. |
| AVISOS | Lo que no cruzó o lo que hay que revisar. |

**Filtre por CUADRA = NO.** Son las facturas donde el descuento no coincide con
la macro: o el servicio aceptado no está en el detallado, o el aceptado es
mayor que el valor del servicio (ahí el bot descuenta hasta cero, nunca deja
valores negativos, y lo avisa).

Un Excel dañado no tumba el lote: esa factura queda en ERROR y las demás siguen.

---

## Resultado del paquete 31068 (18-08-2026)

| | |
|---|---|
| 320 facturas, valor antes | **$714.332.224** |
| Menos lo aceptado | **$86.889.982** |
| **TOTAL FINAL que sigue reclamando el hospital** | **$627.442.242** |

Quedaron **14 facturas con CUADRA = NO** ($4.727.685) para revisar a mano.
