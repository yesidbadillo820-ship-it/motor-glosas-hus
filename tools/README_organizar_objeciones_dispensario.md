# Guía: `organizar_objeciones_dispensario.py` — PDF de auditoría del Dispensario → Excel OBJECIONES

Convierte el PDF **"DETALLE DE AUDITORIA Y GLOSAS"** que envía el auditor del
Dispensario Médico Bucaramanga (CONSORCIO AUDITOOL, `tool.com.co`) en el Excel
de **OBJECIONES** que se importa en Dinámica Gerencial — el mismo formato del
ejemplo `OBJECIONES_EMSSANAR_HUS<n>.xlsx` (columnas `CDCONSEC` … `CROTIPOBJ`,
hoja `OBJECIONES`, una fila por objeción).

Reemplaza la digitación manual de:

> *abrir el PDF, leer cada glosa, copiar código, valor y motivo a mano al
> formato de cargue de DGH, factura por factura*

por una corrida que genera un Excel por factura, listo para revisar e importar.

---

## 1) Qué hace

1. Lee el PDF por **coordenadas de carácter** (no por texto corrido): la tabla
   del auditor tiene las columnas CONCEPTO DE GLOSA y MOTIVO DE GLOSA pegadas
   y el texto plano las mezcla. Cada carácter se asigna a su columna por
   posición X, así los textos salen completos y sin mezclarse.
2. Detecta cada factura (prefijo `HUS` + número), su paciente, fecha de
   atención, valor de factura y las N glosas con: código (`CL03 01` →
   `CL0301`), texto del concepto, motivo completo y valor objetado.
3. **Valida contra el propio PDF**: la suma de los valores extraídos de cada
   factura se compara con el "Total Factura" que imprime el auditor. Si no
   cuadra, lo marca como `DESCUADRE` y el script sale con código 1.
4. Genera `OBJECIONES_DISPENSARIO_HUS<n a 10 dígitos>.xlsx` por factura (o un
   único consolidado con `--consolidado`), con los mismos tipos y formatos de
   celda del ejemplo de EMSSANAR.

### Mapeo de columnas

| Columna | Valor |
|---|---|
| `CDCONSEC` | `1` |
| `CDFECDOC` / `CROFECOBJ` | Fecha Impresión del PDF (o `--fecha`) |
| `CRNCXC` | `HUS` + número de factura a 10 dígitos (`HUS0000530265`) |
| `CROCLAOBJ` / `CROTIPOBJ` | `0` |
| `GENUSUARIO4` | `999` |
| `CRNCONOBJ` | código de glosa (`CL0301`, `SO0801`, …) |
| `SLNSERPRO` | código del servicio si el motivo dice "SE GLOSA CODIGO <x>" |
| `CROVALOBJ` | valor objetado (entero, formato contable) |
| `CRDOBSERV` | `<código> <concepto>: <motivo>$<valor>` |
| resto | vacío (igual que el ejemplo) |

---

## 2) Uso

```powershell
cd C:\temp-notas
git pull

# Un PDF → un Excel por factura glosada, en la carpeta del PDF
py tools\organizar_objeciones_dispensario.py --pdf "D:\...\AUDITORIA_GLOSA_...pdf"

# Carpeta con varios PDFs + carpeta de salida propia
py tools\organizar_objeciones_dispensario.py `
  --carpeta "D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_<fecha>" `
  --salida-dir "D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_<fecha>\OBJECIONES"

# Todo en un solo Excel
py tools\organizar_objeciones_dispensario.py --pdf <pdf> --consolidado "D:\...\objeciones.xlsx"
```

### Flags

| Flag | Uso |
|---|---|
| `--pdf <archivo>` | un solo PDF |
| `--carpeta <dir>` | todos los `*.pdf` de la carpeta |
| `--salida-dir <dir>` | dónde dejar los xlsx (default: junto al PDF) |
| `--consolidado <xlsx>` | un único Excel con todas las facturas |
| `--entidad <nombre>` | nombre en el archivo de salida (default `DISPENSARIO`) |
| `--fecha dd/mm/aaaa` | fecha de la objeción (default: Fecha Impresión del PDF) |

### Salida típica

```
HUS0000530265 (JOSE GREGORIO PEREZ AGUAS): 4 objeciones, total $5,763,297 ✓ cuadra con el PDF → OBJECIONES_DISPENSARIO_HUS0000530265.xlsx
HUS0000527448 (DIANA PATRICIA VALBUENA CABALLERO): 2 objeciones, total $4,200 ✓ cuadra con el PDF → OBJECIONES_DISPENSARIO_HUS0000527448.xlsx
HUS0000527761 (JEISON SMITH OYOLA IBARRA): sin glosas — no se genera Excel
```

Las facturas del PDF **sin glosas** (valor objetado $0) se reportan pero no
generan archivo.

---

## 3) Después de generar

1. Abrir cada Excel y **revisarlo** antes de importar a DGH (igual que con el
   flujo de EMSSANAR): verificar códigos `CRNCONOBJ`, completar `SLNSERPRO`
   donde el motivo no traía código de servicio (estancias, insumos sin código).
2. Importar en DGH por el módulo de cartera (mismo procedimiento que con el
   archivo de EMSSANAR).

> **Ojo:** este script solo ORGANIZA las objeciones (registro en DGH). La
> RESPUESTA de las glosas del Dispensario en el portal SIMED es otro flujo:
> `extraer_respuestas_glosa.py` + `responder_glosas_simed.py`
> (ver `docs/CONTEXTO_DISPENSARIO_GLOSAS.md`).

---

## 4) Si el PDF cambia de formato

- El layout está fijado en `COLUMNAS` (rangos X de cada columna, página de
  1029 pt). Si el auditor cambia la plantilla, ajustar esos rangos.
- Los textos truncados tipo "URGENC" o "EN LO SOPORTES" vienen **así en el
  PDF** (el auditor corta el texto del concepto al borde de la columna); no
  es un bug de extracción.
- Diagnóstico rápido: correr con un solo `--pdf` y comparar el log
  (`N objeciones, total $X ✓/✗`) contra el "Total Factura" del PDF.

## 5) Dependencias

```powershell
py -m pip install pdfplumber openpyxl
```

Tests: `pytest tests/test_tools/test_organizar_objeciones_dispensario.py`
