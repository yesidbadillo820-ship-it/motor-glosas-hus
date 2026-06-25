# Diagnóstico — 12 facturas pendientes del Lote V2 (Dispensario)

Carpeta de trabajo armada a partir de lo que el repo y el contexto saben sobre
las 12 facturas que figuran como pendientes en el lote
`LOTE_DISPENSARIO_2026-06_V2`.

**Objetivo:** entender, para cada factura, **por qué no se subió** al portal
SIMED y qué acción concreta toca hacer.

## Listado de facturas analizadas

```
HUS0000404136
HUS0000411234
HUS0000410675
HUS0000413266
HUS0000417459
HUS0000420099
HUS0000421733
HUS0000418576
HUS0000420160
HUS0000422238
HUS0000435485
HUS0000440328
```

## Archivos en esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `README.md` | este resumen |
| `estado_facturas.md` | ficha detallada por factura (NEs, motivo, acción) |
| `resumen.csv` | la misma info en formato tabla (Excel) |
| `diagnosticar_local.ps1` | script PowerShell que corrés en Windows para validar el estado **real** de cada carpeta en disco + CUV |

## Cómo usar

1. Hacer `git pull` en `C:\temp-notas`.
2. Abrir `docs/diagnostico_lote_v2_pendientes/estado_facturas.md` y leer el
   resumen por factura.
3. Correr el script:

   ```powershell
   cd C:\temp-notas
   powershell -ExecutionPolicy Bypass -File docs\diagnostico_lote_v2_pendientes\diagnosticar_local.ps1
   ```

   El script va a:
   - listar archivos `NC_/XML_/CUV_` por cada carpeta `NE` en
     `LOTE_DISPENSARIO_2026-06_V2\NOTAS`.
   - reportar `COMPLETA / FALTA: ...` por carpeta.
   - decir si la carpeta original (`NOTAS_DISP_9`, `NOTAS_DISP_10`, etc.) existe
     para las que hay que copiar.
   - leer el CUV JSON y reportar `ResultState` y código de rechazo.

4. Tomar acción según la tabla "Próxima acción" del `estado_facturas.md`.

## Cuadro rápido (resumen)

| # | Factura | NE V2 | Estado conocido | Acción |
|---|---|---|---|---|
| 1 | HUS0000404136 | 311131 | COMPLETA en `NOTAS_DISP_10` | copiar al V2 y subir |
| 2 | HUS0000411234 | 311147 | COMPLETA en `NOTAS_DISP_9` | copiar al V2 y subir |
| 3 | HUS0000410675 | 311136 | **CUV RECHAZADO RVC086** | escalar SISTEMAS/RIPS, NO subir |
| 4 | HUS0000413266 | 311183 | sin PDF CRRP | descargar del DIAN |
| 5 | HUS0000417459 | 311186 | sin PDF CRRP | descargar del DIAN |
| 6 | HUS0000420099 | 311188 | ✅ Subida (contexto) | verificar en SIMED por qué sale como pendiente |
| 7 | HUS0000421733 | 311190 | ✅ Subida (contexto) | verificar en SIMED |
| 8 | HUS0000418576 | 311194 | ✅ Subida (contexto) | verificar en SIMED |
| 9 | HUS0000420160 | 311197 | ✅ Subida (contexto) | verificar en SIMED |
| 10 | HUS0000422238 | 311199 | ✅ Subida (contexto) | verificar en SIMED |
| 11 | HUS0000435485 | 311222 | NC subió, soportes pendientes | re-correr cargue (`--solo 311222`) |
| 12 | HUS0000440328 | sin NE V2 (TSV histórico 302111) | falta NE definitivo | confirmar con facturación si NE 302111 es válido o si emitieron uno nuevo |

## Diferencia entre NE histórico (TSV) y NE V2 (contexto)

`tools/notas_credito_ejemplo.tsv` guarda los NEs **originales** (263xxx, 234xxx,
243xxx, 264xxx, 302xxx) emitidos en las Actas AC000456 / AC000619 / etc.

Para el lote V2 (junio 2026), la mayoría de estas facturas tuvieron una NC
**re-emitida** con NE 311xxx. El `estado_facturas.md` muestra los dos NEs lado
a lado para evitar confusión.

> **No mezclar ambos NEs al armar carpetas**: el SIMED espera el NE V2 vigente,
> no el histórico.
