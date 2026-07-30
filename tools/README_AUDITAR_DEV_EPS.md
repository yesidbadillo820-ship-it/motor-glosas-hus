# AUDITAR_DEV_EPS — audita las devoluciones de Nueva EPS (DGH vs RIPS vs soportes)

Automatiza la guía de auditoría del HUS: por cada factura del Excel de
devoluciones, cruza **tres fuentes** y deja el hallazgo por escrito.

```
FACTURA DGH            RIPS - JSON              SOPORTES AUTORIZACION
(factura/soportes)     (Rips_<FAC>.json)        (OPF_*.pdf / PDE_*.pdf)
  TIPO, DOCUMENTO        TIPO, DOCUMENTO          Nº AUTORIZACION
  NOMBRE, SERVICIO       Nº AUTORIZACION          TIPO, DOCUMENTO
                                     -> OBSERVACION (diferencias)
```

El hallazgo típico es el de **recién nacidos**: el JSON trae un documento
provisional (RC largo, p. ej. `26066910192188`) distinto al de la factura y
los soportes (`1244781967`). El bot lo marca:
`OK - DIFERENCIA DEL NUMERO DE DOCUMENTO DGH VS JSON`.

## Cómo se usa

1. Copia **`AUDITAR_DEV_EPS.cmd`** a una carpeta y pon **junto a él el Excel**
   de devoluciones (`NUEVA_EPS_DEV.xlsx`, con el bloque FACTURA DGH ya lleno).
2. **Doble clic**.
3. Te pide, con valores por defecto:
   - el **Excel** (lo detecta solo si dice "DEV"),
   - la **carpeta de facturas/JSON** (por defecto la red del HUS
     `\\172.16.32.83\factura_electronica_net22`),
   - la **carpeta de soportes** (por defecto `Y:\`).

   > ⚡ **Para que sea más rápido**: en la carpeta de soportes, en vez de `Y:\`
   > (todo el disco), puedes poner la carpeta del mes, p. ej.
   > `Y:\7. JULIO 2026 - SOPORTES RADICACION`. El bot ya va **directo** a la
   > carpeta de cada factura y **poda** los envíos/facturas que no son del lote,
   > así que no recorre todo el disco; darle la carpeta del mes lo hace aún más
   > veloz. Va mostrando el progreso, así que **nunca se queda "colgado"**.
4. Queda **`NUEVA_EPS_DEV_AUDITADO.xlsx`** junto al original:
   - los bloques RIPS-JSON y SOPORTES llenos y la **OBSERVACIÓN** en color
     (verde = OK, rojo = diferencia, amarillo = revisar / sin datos),
   - dos columnas al final con la **RUTA DEL JSON** y la **RUTA DE LOS
     SOPORTES** de cada factura, para ir directo a los archivos,
   - una hoja **DETALLE** con TODOS los usuarios y servicios de cada factura.

Al terminar, en la ventana negra muestra **cuántos JSON y cuántos soportes**
encontró; si no halla soportes, imprime un **diagnóstico** con ejemplos de los
PDF que sí vio en esa ruta (para saber si la carpeta es la correcta).

## Qué compara y de dónde

- **RIPS - JSON**: del `Rips_<FAC>.json` — tipo y documento del usuario y el
  número de autorización de cada servicio **tal cual viene**; si el campo
  `numAutorizacion` está en **`null`**, se reporta `null` (no se oculta).
- **SOPORTES AUTORIZACIÓN**: de los PDF `OPF_*` y `PDE_*` — se extraen **TODAS**
  las autorizaciones (un PDE puede traer varias, una por servicio), cada una
  reducida a sus **últimos 9 dígitos** (`(POS) 5251-313608762` → `313608762`),
  más el tipo y documento del paciente (ignora NIT del hospital y prestador).
- **OBSERVACIÓN**: `OK` cuando las autorizaciones del JSON coinciden con las del
  soporte (por sus últimos 9 dígitos); avisa si el JSON trae alguna en `null`,
  y marca las que están en uno y no en el otro.
- **VALIDACIÓN SAT (PDE)**: en el PDE (el soporte que siempre se revisa), si la
  autorización se tramitó en **SAT / Mi Seguridad Social**, mira dentro y
  confirma que el proceso quedó **"Proceso exitoso"**, con su número de
  novedad. Si no aparece esa confirmación, lo marca para revisar.
- **OCR automático**: los PDF que son **solo imagen** (escaneados, sin texto)
  se leen con OCR (Tesseract) para poder sacar de ellos la autorización, el
  documento y la validación SAT. El motor de OCR se instala solo la primera
  vez; si no se puede, los PDF con texto se leen igual.
- **FACTURA DGH**: nombre, documento y servicio del paciente tomados de los
  soportes (lista de chequeo / autorización).
- **OBSERVACIÓN**: `OK` cuando la autorización coincide; marca la diferencia
  de documento DGH vs JSON, autorización distinta, o falta de datos.

## Detalles útiles

- **Solo lee**: no modifica el Excel original (escribe una copia `_AUDITADO`),
  ni los JSON ni los soportes.
- **Tolerante**: una factura sin JSON o sin soportes no detiene el resto; se
  marca en la observación.
- **Empareja bien**: busca por número de factura sin confundir `HUS532392`
  con `HUS5323921`.
- **Instala solo** Python, `openpyxl` y el lector de PDF (`pymupdf`) la primera
  vez, sin administrador.

## Opciones avanzadas (línea de comandos)

```powershell
py tools\auditar_devoluciones_eps.py NUEVA_EPS_DEV.xlsx
py tools\auditar_devoluciones_eps.py DEV.xlsx --facturas-base "\\172.16.32.83\factura_electronica_net22" --soportes-base "Y:\" --salida DEV_AUDITADO.xlsx
```
