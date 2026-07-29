# Explorador de Radicación — `explorador_radicacion.py`

Buscador **interactivo** de las facturas del radicador, para el día a día de los
radicadores y el área de cartera. Toma el reporte del radicador
(`radicar_facturacion.py`) y genera un HTML donde, de un vistazo y con un clic,
se ve:

- **cuáles** facturas están LISTAS y cuáles tienen problemas,
- **qué le falta** a cada una (RIPS, CUV, FEV, soportes, tipificación…),
- **dónde está** cada una (la carpeta del share), con botón para **copiar la ruta**.

> Seguro: solo **lee** el reporte y **escribe** el HTML. No toca las carpetas de
> soportes.

---

## Uso

```powershell
# 1) Generá el reporte con el radicador (si no lo tenés ya)
py tools\radicar_facturacion.py --origen "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD" --reporte "$env:USERPROFILE\Desktop\radicacion_fe.csv"

# 2) Generá el explorador a partir de ese reporte
py tools\explorador_radicacion.py --reporte "$env:USERPROFILE\Desktop\radicacion_fe.csv" --salida "$env:USERPROFILE\Desktop\explorador_radicacion.html"
```

Abrí `explorador_radicacion.html` con doble clic (Edge/Chrome, sin internet).

También lee el `.xlsx` del radicador: `--reporte "...\radicacion_fe.xlsx"`.

---

## Qué se puede hacer en el explorador

- **Chips por estado** (arriba): muestran el conteo de cada estado
  (SIN_RIPS, FALTAN_SOPORTES, REVISAR_TIPIFICACION, LISTA…). **Clic** en uno
  filtra la tabla a ese estado. Ej.: clic en **SIN RIPS** → solo las que les
  falta el RIPS, con su carpeta.
- **Búsqueda**: por número de factura, entidad o ruta de carpeta.
- **Filtro por entidad**.
- **Columna "¿Qué le falta?"**: la causa concreta por factura.
- **Columna "Carpeta (dónde está)"**: la ruta del share + botón **📋 Copiar**
  para pegarla en el Explorador de Windows y ir directo a la factura.
- **Clic en una fila**: abre el detalle completo (soportes presentes/faltantes,
  archivos sin tipificar, detalle y las rutas con botón de copiar).
- **Exportar lista**: baja la vista filtrada a CSV (lo abre Excel) — útil para
  pasarle a facturación/archivo "estas 134 facturas necesitan el RIPS".

---

## Cómo encaja

```
FACTURACIÓN → [ radicar_facturacion.py ] → reporte CSV/XLSX → [ explorador_radicacion.py ] → buscador HTML
                  diagnostica cada factura                        encuentra y prioriza qué arreglar
```

- El **tablero de cartera** (`tablero_cartera.py`) usa el mismo reporte para el
  control de plata (pagos, glosas, saldo). El **explorador** es la vista
  operativa: encontrar y arreglar las facturas con problemas de radicación.
