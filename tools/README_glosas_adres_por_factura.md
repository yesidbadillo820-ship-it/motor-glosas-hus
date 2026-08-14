# Un Excel por factura con lo que sigue glosado (`glosas_adres_por_factura.py`)

Saca **un archivo de Excel por cada factura** del paquete del ADRES, dejando
únicamente lo que **sigue glosado**. Lo que el ADRES ya aprobó no aparece: eso
ya está pago y no hay nada que responder.

A diferencia de `ajustar_detallado_glosas.py`, este **no necesita el detallado
impreso del hospital**. Trabaja directo del reporte del ADRES, que ya trae por
ítem cuánto se reclamó, cuánto aprobaron y cuánto quedó glosado.

---

## Cómo se usa

```
py tools\glosas_adres_por_factura.py ^
    --reporte  "D:\...\ReporteGlosasReclamPAQUETE 31078.xlsx" ^
    --facturas "D:\...\FACTURAS PAQUETE 31078_81 FACTURAS.xlsx" ^
    --salida   "D:\...\POR_FACTURA_31078"
```

Después, para pasarlos a PDF:

```
py tools\excel_a_pdf.py --entrada "D:\...\POR_FACTURA_31078" --motor excel
```

### Opciones

| Opción | Para qué |
|---|---|
| `--facturas` | El archivo de facturas del paquete. **Úselo siempre**: es lo que permite verificar contra la cifra oficial del ADRES. |
| `--carpeta-por-factura` | Cada factura en su propia carpeta, para meterle los soportes al lado. |
| `--solo-descuadradas` | Escribe únicamente las facturas que **no** cuadran, para revisarlas aparte. |
| `--paquete` | El número de paquete, si el reporte trae varios. |

---

## Lo más importante: la verificación

**El reporte del ADRES repite renglones.** Abre una fila por cada causal del
mismo ítem, así que un ítem con tres causales sale tres veces. Si uno suma esa
columna en bruto, la glosa sale inflada al doble o al triple.

El bot junta esos renglones en uno solo, con las causales pegadas. Pero eso no
alcanza siempre: hay facturas donde el reporte repite sin que haya causales
distintas que lo expliquen.

Por eso **cada archivo sale sellado** al pie con una de estas tres cosas:

- ✅ **«VERIFICADO: cuadra con la cifra oficial del ADRES»** — se puede trabajar.
- ⚠️ **«OJO — NO CUADRA»**, con la diferencia exacta en pesos. Hay que bajar el
  detalle del portal antes de responder esa factura.
- **«Sin verificar»** — no se pasó `--facturas`.

Y si el reporte no dice por qué glosaron un renglón, también queda escrito:
sin la causal no se puede objetar ítem por ítem como exige el numeral 8.5.1 de
la Resolución 1236 de 2023.

### Lo que pasó en el paquete 31078

| | Facturas | Plata |
|---|---|---|
| Cuadran con el ADRES | 54 | $49.499.660 |
| **No cuadran** | **27** | **$247.617.689** |

Las 54 suman **exactamente** la cifra oficial, peso a peso. Las 27 concentran el
**83 %** de la plata del paquete y además traen **1.174 renglones sin causal**.
Ejemplo: la HUS411355 tiene $104.828.886 en el detalle cuando el ADRES dice que
son $34.942.962 — el triple.

**El bot no inventa una regla para taparlo.** Esas facturas se responden con el
detalle bajado del portal del ADRES:

> https://servicios.adres.gov.co/login.aspx → usuario/contraseña de
> **Radicación** → Reclamaciones → **Reportes Lupa al giro**

Cuando baje ese detalle, vuelva a correr el bot y las 27 deben pasar a verde.

---

## Qué trae cada archivo

Encabezado con **factura, paquete, radicación y documento del paciente**, y la
tabla con:

`CONSECUTIVO · TIPO · CÓDIGO · DESCRIPCIÓN DEL SERVICIO · CANT. RECLAMADA ·
VR. RECLAMADO · CANT. APROBADA · VR. APROBADO · VR. GLOSADO · CAUSAL(ES) ·
OBSERVACIÓN DEL ADRES`

Con el total glosado al pie y el sello de verificación. Sale en horizontal y
ajustado a lo ancho, para que el PDF no quede partido.

## El resumen

Además deja un `RESUMEN_NNNNN.csv` (separado por punto y coma, se abre directo
en Excel) con una fila por factura:

`FACTURA · FILAS_REPORTE · ITEMS_GLOSADOS · SUMA_DETALLE · OFICIAL_ADRES ·
DIFERENCIA · CUADRA · RENGLONES_SIN_CAUSAL`

Filtre por `CUADRA = NO` para saber cuáles hay que bajar del portal.

---

## Cuándo usar este bot y cuándo el otro

| Situación | Bot |
|---|---|
| Solo tengo el reporte del ADRES | **`glosas_adres_por_factura.py`** (éste) |
| Tengo el detallado impreso del hospital y quiero conservar su formato | `ajustar_detallado_glosas.py` + `dividir_detallado_por_factura.py` |

El primero es más rápido y no depende de que facturación exporte nada. El
segundo produce el documento con el formato propio del hospital.
