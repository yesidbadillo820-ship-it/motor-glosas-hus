# REVISAR_XML — bot de doble clic para revisar los XML y responder la glosa "factura sin contrato"

Cuando la EPS glosa un lote de facturas diciendo que **"se encuentran sin
contrato"**, este bot abre los XML que se radicaron (los de factura electrónica
en salud) y saca a un **Excel** la información de contrato que el XML **sí trae**,
factura por factura. Ese Excel es el anexo de prueba para responder la glosa.

Por cada XML lee, del `AttachedDocument` de la DIAN y de la factura (`Invoice`)
que va embebida dentro, estos campos del sector salud:

| Campo del XML | Qué demuestra |
|---|---|
| `NUMERO_CONTRATO` | El número de contrato pactado con la EPS (p. ej. `01_VCEVN_900006037`). |
| `FACTURA_SIN_CONTRATO` | La causa de cobertura cuando aplica (p. ej. `ATENCION DE URGENCIAS`). |
| `MODALIDAD_PAGO` | Evento, cápita, etc. |
| `COBERTURA_PLAN_BENEFICIOS` | Plan de beneficios (UPC, etc.). |
| `NUMERO_POLIZA` / `CODIGO_PRESTADOR` | Póliza y código del prestador. |
| Validación DIAN | Código `02` = documento validado por la DIAN. |

…más el número de factura, la fecha, el valor y la EPS adquirente.

## Cómo se usa

1. **Copia** `REVISAR_XML.cmd` a una carpeta (por ejemplo tu Escritorio).
2. *(Opcional pero recomendado)* pon junto a él un archivo **`facturas.txt`**
   con **una factura por línea** (sirve `HUS0000533470`, `HUS533470` o
   `533470`, da igual). Así el bot revisa **solo esas**. Si no lo pones,
   revisa **todos** los XML de la carpeta.
3. **Doble clic**.
4. Te pide la carpeta con los XML. Trae por defecto la ruta de red del HUS
   (`\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD`); dale
   **Enter** para usarla o pega otra.
5. Junto al `.cmd` queda **`INFORME_REVISION_XML.xlsx`**:
   - filas en **verde** = el XML trae contrato o causa de cobertura,
   - filas en **amarillo** = hubo algo que revisar (XML ilegible, etc.),
   - la última columna arma la **frase de argumento** para la glosa.
   Al final avisa **cuántas** facturas de tu lista **no** aparecieron como XML.

## Detalles útiles

- **No hay que instalar nada a mano**: si el PC no tiene Python, el bot lo
  instala solo la primera vez (winget o python.org, sin administrador). También
  asegura el componente de Excel (`openpyxl`). **No cambia ninguna
  configuración del equipo.**
- **Solo lee**: abre los XML en modo lectura; no modifica ni mueve nada en la
  carpeta de facturas.
- **No hace falta que el `.cmd` esté junto al `.py`**: el motor va embebido en
  el propio `.cmd` (después de la marca `#PYSTART#`).

## Opciones avanzadas (línea de comandos)

```powershell
py tools\revisar_xml_facturas.py "\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD"
py tools\revisar_xml_facturas.py CARPETA --lista facturas.txt --salida INFORME.xlsx
py tools\revisar_xml_facturas.py .   # carpeta actual, todos los XML
```
