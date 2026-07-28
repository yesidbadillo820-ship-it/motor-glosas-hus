# Respuesta de glosas del Dispensario (SIMED) — generadores

Convierte el **export de glosas de DGH** (Excel con hoja de detalle
`ListadoConceptos.*`) en el **Excel de respuestas** que consume el robot
`tools/responder_glosas_simed.py`, con la argumentación técnico-normativa del
HUS (postura **NO ACEPTA — RE9901 — defensa del 100 %**).

Documentación completa del módulo (arquitectura, decisiones, doctrina,
verificaciones): `docs/ENTREGA_MODULO_GLOSAS_DISPENSARIO_SIMED.md`.
Guía operativa del flujo: `docs/CONTEXTO_DISPENSARIO_GLOSAS.md`.

## Archivos

- **`glosa_motor.py`** — fuente única: clasificador de la observación
  (reglas ordenadas) + banco de plantillas endurecido por verificación
  adversarial + `redactar()` (apertura y cierre institucionales, MAYÚSCULAS,
  párrafo único). Las prohibiciones normativas del encabezado del archivo
  NO son opcionales.
- **`gen_lote.py`** — genera el Excel de un lote:

  ```powershell
  py tools\glosas_dispensario\gen_lote.py GLOSAS_DD_MES.xlsx respuestas_glosa_DISPENSARIO_DDMES.xlsx [dump.json]
  ```

## Flujo estándar de un lote

1. Analizar el export (entidades → solo Dispensario; códigos; observaciones).
2. `gen_lote.py` → Excel + chequeos automáticos (formato, 0 genéricas).
3. Piloto de 1 factura con el robot; luego `--todas`; luego **segunda pasada**
   (`OK: 0` = lote cerrado).
4. Evidencias → `tools/evidencias_a_pdf.py --carpeta ... --salida GI-33-XXXX-2026.pdf`.
5. Actualizar `BITACORA.md`.

## Invariantes (no cambiar sin re-verificar)

- Columnas: `Factura | # Objeción | Cód. | Servicio | Valor Objetado |
  Valor Aceptado (0) | Cod Respuesta (RE9901) | Detalle Respuesta`; hoja
  "Respuestas Glosa".
- La numeración `# Objeción` es **1..N por factura en el orden del export**
  (el portal numera por línea de concepto, no por trámite `Oid`).
- Apertura exacta: `ESE HUS NO ACEPTA LA GLOSA APLICADA A LA FACTURA …`.
- Solo entidad Dispensario/DSE Ejército; las demás se omiten.
