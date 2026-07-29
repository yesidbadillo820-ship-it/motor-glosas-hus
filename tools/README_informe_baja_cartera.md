# Informe Word de baja de facturas para cartera (Resolución 577/2019)

`generar_informe_baja_cartera.py` genera el documento Word que elabora el
**área de facturación** para presentar las facturas que **no cumplen los
parámetros de la Resolución No. 577 del 16 de octubre de 2019** (manual de
cartera del HUS) para su entrega al área de cartera para el cobro, y que por
lo tanto se presentan para trámite de **depuración / baja**.

## Qué hace

- Lee el **PDF unido** de cada carpeta de factura (el `_UNIDO_<carpeta>.pdf`
  o su copia `.cmd` que deja el bot `UNIR_PDFS.cmd`; si no existe, lee los
  PDF sueltos de la carpeta).
- Extrae número de factura, paciente, documento, fecha de atención y el
  **valor de la factura** (etiquetas estrictas de total; ignora los
  certificados con acumulados de la cuenta y los topes SOAT/UVT).
- Localiza las páginas del **informe de trabajo social**, transcribe el
  concepto y **ajusta la justificación de cada factura a lo que trabajo
  social dejó escrito** (sin capacidad de pago, no localizable, sin red de
  apoyo, habitante de calle, paciente fallecido, sin identificación,
  población migrante sin aseguramiento…).
- Ordena las facturas **de la más cara a la más económica**.
- Entrega **DOS informes en la misma corrida**:
  - **Word**: introducción del área de facturación, marco normativo
    (Resolución 577/2019), relación de facturas en tabla, **análisis
    individual con conclusión de baja para cada factura** y conclusión
    general con firmas.
  - **Excel**: hoja `RELACION DE FACTURAS` (con semáforo del informe de
    trabajo social, valores con formato y total), hoja `EXTRACTOS TRABAJO
    SOCIAL` (el concepto transcrito por factura) y `LEYENDA`.

**Importante:** el documento deja constancia de que **no fue posible remitir
las facturas al área de cartera** conforme a la Resolución 577/2019 y por eso
**NO incluye** la fórmula de "agotadas las acciones administrativas de cobro
persuasivo (Art. 15) sin resultado positivo" — no hubo gestión de cobro
porque los documentos nunca llegaron a cartera.

Las facturas cuyo PDF unido **no contiene** informe de trabajo social (o está
escaneado sin texto) quedan marcadas con **NOTA DE REVISIÓN** dentro del Word
y se listan en consola: hay que completarlas a mano antes de presentar.

## Uso

```bat
REM 1) Primero unir los PDF de cada carpeta:
REM    UNIR_PDFS.cmd (deja _UNIDO_<carpeta>.pdf + copia .cmd)

REM 2) Generar el informe:
py generar_informe_baja_cartera.py --raiz "C:\FACTURAS\BAJAS" ^
    --elaborado "NOMBRE APELLIDO - Facturación" --ciudad Bucaramanga

REM Salida con nombre propio:
py generar_informe_baja_cartera.py --raiz "C:\FACTURAS\BAJAS" ^
    --salida "C:\FACTURAS\BAJAS\INFORME_BAJA_MAYO.docx"
```

**Doble clic:** copie `INFORME_BAJA_CARTERA.cmd` +
`generar_informe_baja_cartera.py` a la raíz de las facturas y dele doble
clic (o arrastre una carpeta encima del `.cmd`).

## Dependencias

- `python-docx` (obligatoria, para el Word).
- `openpyxl` (obligatoria, para el Excel).
- `pypdf` **o** `pdfplumber` (para leer los PDF unidos).

El `.cmd` las instala solo si faltan.

## Revisión antes de presentar

El Word es un **borrador estructurado**: revise nombre/cargo de quien firma,
los extractos citados de trabajo social y las facturas con NOTA DE REVISIÓN.
El área de facturación es responsable del contenido final que presenta.

## OCR para páginas escaneadas (nuevo)

Las páginas del PDF unido que no traen texto (escaneadas) ahora se leen por
**OCR** (máximo 15 páginas por factura, para no alargar la corrida). El
motor se detecta solo: Tesseract si está instalado, o RapidOCR
(`pip install pypdfium2 rapidocr-onnxruntime` — el .cmd lo intenta solo).
