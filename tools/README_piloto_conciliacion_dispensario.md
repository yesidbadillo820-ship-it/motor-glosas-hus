# Guía: `piloto_conciliacion_dispensario.py` — Piloto extremo a extremo

Corre **todo el flujo** sobre unos pocos casos representativos y **mide** si el
sistema está listo, **antes** de seguir con el Módulo Jurídico:

```
índice → expediente → evidencia → hechos probados → decisión
```

Deja una **carpeta por expediente** con cada etapa en su archivo, más un
`METRICAS.json` con los indicadores y la evaluación de los **umbrales de
aceptación**. Así se audita y se diagnostica dónde falla el flujo.

## Uso — el piloto en un solo comando

```powershell
# 1) (una vez) Indexar la carpeta del Dispensario dentro del servidor
py tools\indexar_soportes_dispensario.py `
  --raiz "X:\SERVIDOR RADICACION\2. SINAC SC SAS - 2026\...\DISPENSARIO" `
  --salida "D:\...\indice_soportes.json" --con-meta

# 2) Correr el piloto sobre los 5 casos representativos (selección automática)
py tools\piloto_conciliacion_dispensario.py `
  --excel   "D:\USUARIO CARTERA\Downloads\HUS.xlsx" `
  --indice  "D:\...\indice_soportes.json" `
  --cartera "D:\...\Estado_Cartera_JUN_2026.xlsx" `
  --auto  --conocido HUS0000436483 `
  --salida-dir "D:\...\Piloto"
```

- `--auto` elige 5 casos: **mayor valor**, **más glosas**, **contrato 287**,
  **contrato 440**, y el **`--conocido`** (el que ya conocés, para comparar).
- O casos explícitos: `--facturas "HUS0000446262,HUS0000452150,HUS0000426013"`.

## Qué deja

```
Piloto/
├── HUS0000446262/
│   ├── expediente.json   ← núcleo (factura, paciente, contrato, cartera, soportes)
│   ├── evidencia.json    ← evidencias por glosa (documento, página, fragmento)
│   ├── hechos.json       ← hechos probados + alertas/contradicciones
│   ├── decision.json     ← defendibilidad, riesgos, acción recomendada
│   ├── resumen.txt       ← todo lo anterior, legible
│   └── log.txt           ← traza de las etapas
├── ...
├── CONCILIACION.xlsx     ← hoja de trabajo: 1 fila por glosa, lista para conciliar
└── METRICAS.json         ← indicadores + umbrales de aceptación (piloto_ok sí/no)
```

La **`CONCILIACION.xlsx`** consolida todo en una hoja para el auditor: factura,
paciente, contrato, cartera, código y servicio de la glosa, valor objetado,
**defendibilidad %**, **decisión** (coloreada), prioridad, **evidencia citada
(páginas)**, documentos faltantes, riesgo probatorio, alertas y motivo/acción.

## Indicadores que mide (`METRICAS.json`)

> Las glosas **exactamente duplicadas** en el Excel origen (misma factura, código,
> servicio y valor) se descartan al armar el expediente, para no contar dos veces.
> El indicador `pct_hechos_evaluados` es el **% de glosas evaluadas (0–100)**, no
> el promedio de hechos por glosa.

- **Índice:** facturas del piloto, documentos encontrados, con soporte, huérfanos.
- **Evidencia:** localizadas, fuertes, débiles, glosas sin evidencia.
- **Hechos:** probados / no probados, contradicciones.
- **Decisión:** cuántas glosas por cada acción.
- **Aceptación** (umbrales del auditor):
  - ≥ 95 % facturas con soporte
  - ≥ 90 % glosas con evidencia
  - ≥ 90 % hechos evaluados
  - **0** decisiones de levantamiento sin un hecho probado (guardarraíl)
  - 100 % decisiones con trazabilidad
- `piloto_ok`: **true solo si se cumplen todos los umbrales.**

> Si `piloto_ok=false`, la prioridad es **corregir el flujo** (índice, OCR,
> clasificación, reglas, datos), **no** agregar funcionalidades.

## Validación manual (indispensable)

Por cada factura, revisar en el `resumen.txt` / carpeta:
- ¿La evidencia localizada es correcta? ¿La página es la correcta?
- ¿El hecho probado realmente está demostrado?
- ¿La decisión coincide con la de un auditor humano?

Si algo falla, la causa suele estar en: índice · OCR · clasificación documental ·
reglas · datos del expediente. (No se toca el Módulo Jurídico todavía.)

Tests: `pytest tests/test_tools/test_piloto_conciliacion_dispensario.py`
