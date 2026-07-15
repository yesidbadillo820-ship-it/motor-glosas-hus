# Organizador de objeciones EMSSANAR → Excel OBJECIONES (cargue DGH)

`tools/organizar_objeciones_emssanar.py` toma los PDFs de objeción que radica
EMSSANAR (los "Objeción a Factura N° HUS..." generados por **ripslink.app**, con
nombre `DETALLES_DE_SERVICIOS_FACTURA_HUS*.pdf`) y arma el Excel de cargue con la
hoja **OBJECIONES** — el mismo formato de 16 columnas del lote que ya se usa para
COOSALUD (`OBJECIONES_LOTE_*.xlsx`) y que se sube al sistema de cartera del HUS.

## Uso

```bat
REM Un solo PDF
py tools\organizar_objeciones_emssanar.py ^
    --pdf "DETALLES_DE_SERVICIOS_FACTURA_HUS0000515948.pdf" ^
    --salida "OBJECIONES_EMSSANAR_HUS515948.xlsx"

REM Carpeta completa (recursivo) — un lote con N facturas
py tools\organizar_objeciones_emssanar.py ^
    --pdf "D:\OBJECIONES\EMSSANAR\JULIO" ^
    --salida "OBJECIONES_EMSSANAR_LOTE_01.xlsx" ^
    --consec-inicial 1
```

Instalación (una vez): `py -m pip install pdfplumber openpyxl`

### Opciones

| Opción | Default | Para qué |
|---|---|---|
| `--pdf` | (requerido) | PDF(s) y/o carpeta(s). En carpetas busca `DETALLES_DE_SERVICIOS_FACTURA_*.pdf` recursivo |
| `--salida` | `OBJECIONES_EMSSANAR.xlsx` | Ruta del Excel a generar |
| `--consec-inicial` | `1` | `CDCONSEC` de la primera factura (para continuar numeración entre lotes) |
| `--fecha` | fecha de objeción del PDF | Forzar `CDFECDOC`/`CROFECOBJ` (formato `DD-MM-AAAA`) |
| `--usuario` | `999` | `GENUSUARIO4` |
| `--tipobj` | según el PDF | Forzar `CROTIPOBJ` (0 = Glosa, 2 = Devolución) |
| `--sin-sufijo-h` | apagado | No homologar CUPS al código DGH con sufijo `H` |
| `--estricto` | apagado | Rechazar PDFs cuya suma no cuadre con el encabezado |

## Qué produce

Una hoja `OBJECIONES` con exactamente las columnas del lote de ejemplo:

`CDCONSEC · CDFECDOC · CRNCXC · CROFECOBJ · CROREFERE · CROOBSERV · CROCLAOBJ ·
CRNCLAOBJ · GENUSUARIO4 · CRNCONOBJ · SLNSERPRO · IDRIPS · CTNCENCOS · CROVALOBJ ·
CRDOBSERV · CROTIPOBJ`

- **Una fila por renglón** de la tabla "Detalle glosas" del PDF (tecnología × código
  de objeción), con `CRDOBSERV` en el estilo del lote:
  `TA0801 TEXTO ESTÁNDAR (902045-TIEMPO DE PROTROMBINA TP): NOTA DE LA AUDITORA$15400`
- `CRNCXC` normalizada a `HUS` + 10 dígitos (`HUS515948` → `HUS0000515948`).
- `CDCONSEC`: un consecutivo por factura, en orden de número de factura.
- Facturas repetidas (el mismo PDF en dos carpetas) se cargan una sola vez.

## Reglas importantes (verificadas contra el PDF real)

1. **Fusión de doble glosa.** Cuando la EPS objeta el mismo servicio con una glosa
   de **valor total** (Cantidad Objetada numérica) y además una de **diferencia
   tarifaria** (Cantidad Objetada `--`), su "Valor Objetado" del encabezado solo
   cuenta la mayor. El bot fusiona esas parejas en una sola fila (código y valor de
   la mayor; ambos códigos quedan detallados en `CRDOBSERV`, cada uno con su
   `$valor`), igual que las filas multi-código del lote COOSALUD. Sin esto la suma
   daría $68.000 de más en la factura HUS515948, por ejemplo.

2. **Códigos apilados.** Un renglón del PDF puede traer un segundo código sin valor
   propio (p. ej. `SO0601` + `FA0603` sobre la misma cánula): van en la misma fila,
   concatenados en `CRDOBSERV`.

3. **Homologación CUPS → DGH (sufijo `H`).** Algunos servicios existen en DGH con
   sufijo `H` (`876802` → `876802H`). La tabla `CUPS_A_DGH` del script se derivó del
   lote real `OBJECIONES_LOTE_03_LISTO` (7.869 filas ya cargadas): 145 códigos.
   Lo que no está en la tabla se emite tal cual viene en el PDF. Si el cargue
   rechaza un código, agregarlo a la tabla (o usar `--sin-sufijo-h` y corregir a mano).

4. **Validación por PDF.** La suma de `CROVALOBJ` se compara contra el
   "Valor Objetado" del encabezado del PDF. Si no cuadra, se avisa en consola con
   `⚠ ... NO CUADRA` (y con `--estricto` esa factura se excluye del Excel).

5. **`CROTIPOBJ`**: 0 si el PDF dice `Tipo objeción: Glosa`, 2 si dice `Devolución`
   (forzable con `--tipobj`).

## Cómo parsea el PDF

La tabla se reconstruye desde las **palabras** del PDF asignándolas a columnas por
posición X (bandas calibradas del reporte de ripslink), porque las celdas envuelven
en varias líneas, los renglones cruzan páginas y la detección automática de tablas
no separa "Código Objeción" de "Observación". Un renglón nuevo arranca donde la
columna Tecnología trae `CÓDIGO -`; el pie de página, el encabezado y el bloque de
firmas del auditor se descartan.

Si EMSSANAR cambia el layout del reporte, la validación del punto 4 lo detecta de
inmediato (la suma deja de cuadrar o aparecen renglones incompletos en el log).

## Tests

```bash
pytest tests/test_tools/test_organizar_objeciones_emssanar.py
```
