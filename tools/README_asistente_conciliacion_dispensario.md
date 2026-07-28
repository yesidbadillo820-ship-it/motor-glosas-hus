# Guía: `asistente_conciliacion_dispensario.py` — Asistente de conciliación de glosas

Construye, **por cada glosa**, la defensa técnica/jurídica/documental a partir de
**todos los soportes de la factura**. Recorre la carpeta de soportes, lee cada
documento (RIPS, XML/CUFE, CUV, PDF de historia clínica/epicrisis/orden/etc., con
OCR opcional para escaneados), arma la **matriz de evidencia**, cruza coherencia y
redacta la **respuesta técnica** lista para el pagador.

> **Regla principal:** nunca inventa evidencia. Si un soporte no existe, lo dice;
> si la evidencia es insuficiente, marca **"Información insuficiente"** e indica
> qué documento falta. Toda conclusión indica documento, ruta, página y norma.

> **Dónde corre:** en **tu máquina Windows**, donde está montada la unidad de red
> de soportes (`Y:\...`). El asistente no puede leer `Y:\` desde la nube.

---

## 1. Qué hace (los "motores")

1. **Documental** — indexa toda la carpeta y agrupa los archivos por factura
   (busca `HUS<número>` en el nombre o la ruta).
2. **OCR** (opcional) — si un PDF está escaneado y no tiene texto, lo pasa por OCR
   (requiere `pytesseract` + `pdf2image` + Tesseract). Si no, lo marca "requiere OCR".
3. **Cruces / coherencia** — verifica que el RIPS corresponda a la factura y al
   paciente, y que el código del servicio glosado aparezca en el RIPS.
4. **Jurídico** — asocia cada familia de glosa con su norma vigente
   (Res. 2284/2023, Res. 2335/2023, Ley 1438/2011 Art. 57, contrato aplicable…).
5. **Auditoría / confianza** — concluye **Procede / No procede / Parcial /
   Información insuficiente** con un **% de confianza** según la evidencia hallada.
6. **Redacción** — genera el oficio de respuesta con la estructura completa
   (identificación, hallazgo, evidencia, cruces, análisis, conclusión, acción).
7. **Base de conocimiento** — guarda los casos resueltos con alta confianza y los
   reutiliza como **precedente** en glosas análogas (mismo código + servicio).

## 2. Estructura de carpetas que espera

```
<raíz>\DISPENSARIO\<GESTOR>\ENV-<n>-OKDGH\HUS<factura>\<TIPO>_900006037_HUS<factura>.<ext>
```

Tipos reconocidos por el token inicial del nombre: `RIPS`, `XML`, `FEV`, `CUV`,
`CRC`, `HEV` (historia/evolución), `EPICRISIS`, `OPF` (orden/fórmula), `HAM`,
`PDE`/`PDX`, `AUT`/`AUTORIZACION`, `MIPRES`, `LAB`, `IMG`, `NC`/`ND`, `PAGO`.
Si tu convención usa otros nombres, se amplía el mapa `TIPOS_DOC` del script.

## 3. Uso

```powershell
cd C:\temp-notas
git pull

# Piloto de UNA factura (recomendado antes del masivo)
py tools\asistente_conciliacion_dispensario.py `
  --excel "D:\...\HUS.xlsx" `
  --soportes-raiz "Y:\7. JULIO 2026 - SOPORTES RADICACION\DISPENSARIO" `
  --salida "D:\...\MATRIZ_EVIDENCIA_Y_RESPUESTAS.xlsx" `
  --solo HUS436483 --con-oficios "D:\...\OFICIOS"

# Masivo (todas las glosas del Excel)
py tools\asistente_conciliacion_dispensario.py `
  --excel "D:\...\HUS.xlsx" `
  --soportes-raiz "Y:\7. JULIO 2026 - SOPORTES RADICACION\DISPENSARIO" `
  --salida "D:\...\MATRIZ_EVIDENCIA_Y_RESPUESTAS.xlsx" `
  --con-oficios "D:\...\OFICIOS" --kb "D:\...\precedentes.json" --ocr
```

### Flags

| Flag | Uso |
|---|---|
| `--excel` | Excel de glosas (layout HUS.xlsx del Dispensario) |
| `--soportes-raiz` | Carpeta raíz de soportes (la unidad `Y:\...`) |
| `--salida` | Excel de salida (hojas `Respuestas` + `Matriz_Evidencia`) |
| `--solo HUS<n>` | Procesa una sola factura (piloto) |
| `--con-oficios <dir>` | Escribe un oficio `.txt` por glosa |
| `--kb <json>` | Base de conocimiento de precedentes (se lee y actualiza) |
| `--ocr` | Activa OCR para PDFs escaneados (requiere libs + Tesseract) |

## 4. Qué entrega

- **Excel** con dos hojas:
  - `Respuestas`: una fila por glosa con conclusión, % de confianza, contrato,
    norma, documentos hallados/faltantes y alertas de coherencia.
  - `Matriz_Evidencia`: una fila por documento (encontrado/no, páginas, ruta).
- **Oficios** `.txt` por glosa (si `--con-oficios`), con la respuesta técnica.
- **Base de conocimiento** JSON con los precedentes (si `--kb`).

## 5. Reglas de conclusión (deterministas, auditable)

- **No procede** (alta confianza): están los soportes requeridos de la familia y
  los cruces de coherencia pasan.
- **Procede parcialmente**: falta algún soporte o hay una alerta de coherencia.
- **Información insuficiente**: no hay soportes suficientes; se indica cuál falta.
- **TARIFAS**: se defiende con la factura/RIPS + la tarifa pactada del contrato
  vigente a la fecha de atención (287 hasta 30‑nov‑2025; 440 desde diciembre).

> **El asistente propone; el auditor decide.** Cada oficio debe revisarse y
> avalarse antes de enviarlo. Los documentos marcados "NO" hay que conseguirlos.

## 6. Dependencias

```powershell
py -m pip install openpyxl pdfplumber
# OCR opcional:
py -m pip install pytesseract pdf2image   # + instalar Tesseract-OCR
```

Tests: `pytest tests/test_tools/test_asistente_conciliacion_dispensario.py`
