# Bot de validación FURIPS vs soportes (Circular 022/2023 ADRES)

`validar_furips.py` valida de forma **masiva** las reclamaciones FURIPS del
HUS y deja un **informe Excel detallado**. Cruza tres fuentes:

1. **Malla de la Circular 022 de 2023 ADRES** — los 102 campos del FURIPS 1
   y los 9 del FURIPS 2: obligatoriedad, formatos de fecha/hora, valores
   permitidos, longitudes máximas y condicionales (estado de aseguramiento,
   remisión, transporte primario, UCI, procedimientos quirúrgicos…).
2. **Coherencia FURIPS 1 ↔ FURIPS 2** — sumatorias de amparos (campos
   97-100), consecutivo de la reclamación, reclamado ≤ facturado, cantidad ×
   valor unitario = valor facturado, agrupación de servicios idénticos.
3. **Soportes de cada carpeta de factura** — RIPS JSON, CUV JSON, factura
   electrónica DIAN (XML), factura PDF y epicrisis PDF: paciente, documento,
   fechas de ingreso/egreso, fecha del accidente, diagnósticos CIE-10,
   número de factura, NIT, código de habilitación y valores.

Además detecta cruces que suelen terminar en glosa: egreso anterior al
ingreso, TI en mayores de edad, víctima "conductor" con documento distinto en
la sección VIII, evento fuera de la vigencia de la póliza, días de UCI
mayores que la estancia, dispositivos médicos sin registro INVIMA, líneas
duplicadas sin agrupar, PDF escaneados sin capa de texto, soportes faltantes.

## Uso

```bat
REM Masivo: raíz con carpetas por factura. Los TXT FURIPS1*/FURIPS2* se
REM detectan solos en la raíz o en cualquier subcarpeta.
py validar_furips.py --raiz "C:\FACTURAS\ADRES MAYO"

REM Una sola factura
py validar_furips.py --carpeta "C:\FACTURAS\HUS374152"

REM Rutas explícitas y salida con nombre propio
py validar_furips.py --raiz "C:\FACTURAS" ^
    --furips1 "C:\FACTURAS\FURIPS168001007920116102025.txt" ^
    --furips2 "C:\FACTURAS\FURIPS268001007920116102025.txt" ^
    --salida  "C:\FACTURAS\INFORME_FURIPS.xlsx"

REM Sin leer PDFs (más rápido, solo malla + RIPS/CUV/XML)
py validar_furips.py --raiz "C:\FACTURAS" --sin-pdf
```

**Doble clic:** copie `VALIDAR_FURIPS.cmd` + los `.py` de esta carpeta a la
raíz de las facturas y dele doble clic (o arrastre una carpeta encima del
`.cmd`). Instala solo `openpyxl`/`pypdf` si faltan.

## Cómo asocia facturas con soportes

- Cada registro del FURIPS 1 se identifica por el **número de factura**
  (campo 3), normalizado (`HUS0000374152` = `HUS374152`).
- Los soportes se agrupan por el **número de factura en el nombre de cada
  archivo** (`680010079201_HUS374152_EPICRIS.pdf` → `HUS374152`), por lo
  que funcionan las **dos organizaciones** reales:
  - una **carpeta por factura** (`HUS374152\…`), o
  - una **carpeta plana** (p. ej. `SOPORTES\`) con los archivos de muchas
    facturas mezclados.
- Si un archivo no trae el número en el nombre, se intenta con el nombre
  de su carpeta.
- Se reportan también las facturas **sin soportes** y los soportes **sin
  registro** FURIPS.

## El informe Excel (7 hojas)

| Hoja | Contenido |
|---|---|
| **RESUMEN** | Una fila por factura: paciente, fechas, valores, qué soportes hay, número de errores/advertencias y estado (CUMPLE / REVISAR / CON ERRORES) con semáforo. |
| **HALLAZGOS** | Todos los hallazgos: origen (malla, FURIPS2, cruce RIPS/CUV/XML/PDF/epicrisis, soportes), campo de la Circular, valor FURIPS vs valor del soporte, severidad y regla de referencia. |
| **FURIPS1 CAMPOS** | Los 102 campos de cada factura, con su valor, la obligatoriedad de la Circular, estado y observación (auditoría campo a campo). |
| **FURIPS2 LINEAS** | Cada línea del FURIPS 2 con su validación (tipos, códigos, cantidades, valores). |
| **CRUCE SOPORTES** | Matriz dato × fuente: qué dice el FURIPS, el RIPS, el CUV, el XML, la factura PDF y la epicrisis, y si coincide. |
| **SOPORTES** | Inventario de archivos por carpeta, tipo de soporte y si el PDF tiene texto legible. |
| **LEYENDA** | Qué significa cada severidad y la normativa aplicada. |

Severidades: **ERROR** (rojo — incumple la Circular o hay diferencia
comprobada con un soporte; la ADRES normalmente devuelve o glosa),
**ADVERTENCIA** (amarillo — no se pudo confirmar el dato o situación
atípica; revisar), **INFO** (azul — contexto, no impide radicar).

## Dependencias

- `openpyxl` (obligatoria, para el Excel).
- `pdfplumber` **o** `pypdf` (opcional, para leer los PDF; sin ellas el bot
  corre y marca los PDF como no legibles).
- Los PDF **escaneados** (sin capa de texto) no se pueden cruzar
  automáticamente: quedan marcados `SIN TEXTO` para revisión manual.

## Normativa aplicada

- **Circular 022 de 2023 ADRES** — estructura y anexos técnicos FURIPS 1 y 2.
- **Resolución 2284 de 2023** — soportes de la reclamación.
- **Decreto 780/2016** (mod. Decreto 2466/2022) — manual tarifario SOAT.
- **Resolución 762 de 2023 ADRES** — identificación AS/MS.

## OCR para PDF escaneados (nuevo)

Si un PDF no tiene capa de texto (escaneado), el bot le aplica **OCR
automáticamente** a las primeras 8 páginas y hace los cruces sobre el texto
reconocido; en la hoja SOPORTES queda "SI (OCR)" y en HALLAZGOS un aviso
INFO. Motores soportados (se detectan solos): **Tesseract** (si está
instalado en el PC, el más preciso) o **RapidOCR** (`pip install pypdfium2
rapidocr-onnxruntime`, sin programas externos; el .cmd lo instala solo la
primera vez). Si ninguno está disponible, el PDF queda "SIN TEXTO" como
antes y el cruce se omite.
