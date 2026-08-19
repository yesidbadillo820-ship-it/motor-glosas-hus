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
   VALOR ACEPTADO mayor que cero. Y descarta —avisando— dos clases de fila que
   no se pueden usar:
   - las que dicen **SE OBJETA** o **SE SUBSANA** en la observación: ese
     servicio se sigue reclamando completo, así que no puede tocar el
     detallado. Si además trae valor aceptado, la macro se está contradiciendo
     y el auditor tiene que verlo;
   - aquellas donde el **valor aceptado es mayor que el valor reclamado** de la
     misma fila. Eso es imposible —no se puede aceptar más de lo que se cobró—
     y pasa cuando la columna del Excel quedó corrida un renglón.
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

## Lo más delicado: los renglones sin número

Una cirugía se imprime así: un renglón **con número de consecutivo** (el
procedimiento, con su valor total) y debajo, **sin número**, el desglose de ese
valor — cirujano, anestesiólogo, ayudantía, derechos de sala, materiales. Ese
desglose **no vuelve a sumar**: ya está dentro del procedimiento.

Pero cuando al paciente le hicieron **varias cirugías**, debajo del mismo
procedimiento se imprimen los honorarios de todas, y **los de la segunda en
adelante sí suman**, porque no están dentro de ningún renglón.

El bot lo resuelve acumulando: los primeros renglones sin número se van sumando
hasta completar exactamente el valor del procedimiento que tienen encima —ese
es su desglose y no cuenta—; **lo que siga después es cirugía aparte y sí
cuenta**. Y el subtotal **nunca se recalcula desde cero**: se toma el que ya
trae el archivo, que es el bueno, y solo se le resta lo descontado.

**La comprobación de cierre.** Antes de guardar, el bot se pregunta: «la suma de
los renglones que doy por buenos, ¿reproduce el subtotal que trae el archivo?».
Si no lo reproduce, es que esa factura no se entendió: entonces solo descuenta
los servicios **numerados** —que siempre suman— y deja el aviso
**REVISAR A MANO** en la bitácora. Nunca escribe un subtotal que no pueda
justificar. En el paquete 31068 el modelo cuadra en **318 de las 320** facturas.

### Los dos errores que enseñaron esta regla

- **Recalcular el subtotal desde cero** daba **$106 millones de menos**, porque
  en 50 facturas los honorarios sí suman aparte.
- **Decidir de una sola vez para toda la factura** dejó la **HUS388262** con el
  subtotal **$1.400.050 por encima** de lo que correspondía: tenía dos
  osteosíntesis, y el bot dio por «informativos» los honorarios de la segunda,
  que sí sumaban. Esa factura alcanzó a entregarse mal antes de detectarse.

El contador de servicios de la fila del subtotal **se conserva tal como venía**:
este bot cambia valores, nunca borra renglones, así que no tiene por qué
moverlo.

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

Y si la macro le acepta plata a una factura que **no tiene detallado** en la
carpeta, esa factura igual sale en la bitácora con estado **SIN_DETALLADO** y
su valor: esa plata se seguiría reclamando sin que nadie se entere.

---

## Resultado del paquete 31068 (18-08-2026)

| | |
|---|---|
| 320 facturas, valor antes | **$714.332.224** |
| Menos lo aceptado | **$88.870.607** |
| **TOTAL FINAL que sigue reclamando el hospital** | **$625.461.617** |

Para mirar antes de radicar: **12 facturas con CUADRA = NO** ($2.747.060),
**2 con REVISAR A MANO** (HUS384132 y HUS392442), **1 con OJO CON LA MACRO**
(HUS396996, la fila corrida) y **2 SIN_DETALLADO** (HUS367368 y HUS394817, por
$12.800).

### La fila corrida de la HUS396996

Una fila de la macro —una sola en 4.619— dice **SE OBJETA** y aun así trae
**$758.700 aceptados** sobre un servicio de **$73.500**. La columna VALOR
ACEPTADO quedó corrida un renglón: ese valor es el del tórax de la fila
siguiente. Sin las dos guardas, el bot borraba del detallado una radiografía de
mano que el hospital **sigue reclamando**. Ahora la salta y avisa. **Esa factura
hay que revisarla completa**: por el mismo corrimiento, al tórax se le descontó
$7.800 cuando el equipo lo aceptó por $758.700.
