# Guía: `motor_evidencia_dispensario.py` — Motor de Evidencia (Módulo 3)

No basta con decir *"existe historia clínica"*. Este motor **lee los soportes
clínicos página por página** y localiza, para cada glosa, **en qué página** está
la prueba, con el fragmento textual exacto:

> Historia clínica, **página 18**: *"…se ordena procedimiento 890201 consulta
> control por especialista…"*

Trabaja sobre el **expediente único** (`expedientes.json`): ya sabe las rutas de
los soportes de cada factura, así que abre **solo** esos archivos (no recorre `Y:\`).

> **Nunca inventa.** Si el término no aparece en ningún soporte, la evidencia
> queda vacía y la glosa se marca **"sin evidencia localizada"**.

## Cómo decide qué buscar

Por cada glosa arma términos de búsqueda a partir del servicio y el motivo:
- **Códigos** CUPS/CUM/servicio (ej. `890201`, `21519H`) → evidencia **fuerte**.
- **Palabras significativas** del servicio (ej. `CONSULTA`, `CONTROL`) → evidencia
  **débil** (apoya, pero no prueba sola). Las palabras demasiado genéricas
  (`PROCEDIMIENTO`, `ATENCION`, `PACIENTE`…) se ignoran para no dar falsos positivos.

Cada evidencia queda marcada como **fuerte** o **débil** para no exagerar.

### Cita acotada (no "disparo de escopeta")

Antes, una glosa de calidad podía citar **las 300 páginas** de la historia
clínica (cualquier página con una palabra genérica). Eso no es una prueba usable
en un oficio. Ahora el motor **puntúa cada página** (cada código CUPS pesa 10,
cada palabra 1), ordena por **evidencia fuerte primero** y cita como máximo
`MAX_EVIDENCIAS_POR_GLOSA` (6) páginas — las más relevantes. La cita pasa de
*"páginas 1 a 300"* a *"páginas 9-11"*, que sí ahorra trabajo al auditor.

## Uso

```powershell
# Requiere el expedientes.json (lo genera expediente_conciliacion.py)
py tools\motor_evidencia_dispensario.py `
  --expedientes "D:\...\expedientes.json" `
  --salida      "D:\...\expedientes_con_evidencia.json" `
  --reporte     "D:\...\EVIDENCIA.xlsx" `
  --ocr    # si los soportes son escaneados (requiere Tesseract)
```

## Qué entrega

- `expedientes_con_evidencia.json`: cada glosa gana una lista `evidencias` con
  `{tipo, nombre, ruta, pagina, termino, fuerza, fragmento}`.
- `EVIDENCIA.xlsx` (opcional): una fila por evidencia — Factura · Glosa · Soporte
  · **Página** · Término · **Fragmento**. Las glosas sin evidencia salen marcadas.

## Dónde encaja

```
expediente_conciliacion.py  →  expedientes.json
                                     │
                                     ▼
              motor_evidencia_dispensario.py  (este)   ← Módulo 3
                                     │
                                     ▼
        expedientes_con_evidencia.json  →  Módulo 5 (Argumentación)
```

El siguiente motor (Argumentación) toma estas evidencias con página y arma el
oficio con las razones numeradas.

## Dependencias

```powershell
py -m pip install openpyxl pdfplumber
# OCR opcional: py -m pip install pytesseract pdf2image  + Tesseract-OCR
```

Tests: `pytest tests/test_tools/test_motor_evidencia_dispensario.py`
