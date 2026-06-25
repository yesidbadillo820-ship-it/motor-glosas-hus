# Estado detallado por factura (12 pendientes — Lote V2)

Fuentes cruzadas:

- **TSV histórico**: `tools/notas_credito_ejemplo.tsv` (Radicado, Acta, Valor
  Factura, Total Glosas, Valor Aceptado, NE histórico).
- **Contexto V2**: `docs/CONTEXTO_DISPENSARIO_NOTAS.md` sección 7 (estado actual
  del lote, NE V2, motivo de bloqueo).

> **Ojo**: estado conocido al cierre del chat anterior. El estado **real en
> SIMED hoy** se valida con `diagnosticar_local.ps1` + revisión visual del
> portal.

---

## 1. HUS0000404136

| Campo | Valor |
|---|---|
| HUS corto | HUS404136 |
| NE histórico (TSV) | 263272 |
| **NE V2 (vigente)** | **311131** |
| Radicado | 457325 |
| Acta | AC000456 |
| Valor Factura | $ 2.169.054 |
| Total Glosas | $ 61.708 |
| Valor Aceptado | $ 10.218 |
| Estado contexto V2 | COMPLETA en `NOTAS_DISP_10\NOTAS\311131` |
| Por qué no se subió | la carpeta `311131` quedó en el lote anterior (DISP_10) y nunca se copió al `V2\NOTAS`. El bot no la ve porque no existe en el path del V2. |
| **Acción** | Copiar `NOTAS_DISP_10\NOTAS\311131` → `LOTE_DISPENSARIO_2026-06_V2\NOTAS` y subir con `--solo 311131`. |

---

## 2. HUS0000411234

| Campo | Valor |
|---|---|
| HUS corto | HUS411234 |
| NE histórico (TSV) | 263288 |
| **NE V2 (vigente)** | **311147** |
| Radicado | 460616 |
| Acta | AC000456 |
| Valor Factura | $ 812.155 |
| Total Glosas | $ 115.942 |
| Valor Aceptado | $ 12.589 |
| Estado contexto V2 | COMPLETA en `NOTAS_DISP_9\NOTAS\311147` |
| Por qué no se subió | mismo caso que HUS404136 — la carpeta quedó en el lote anterior (DISP_9). |
| **Acción** | Copiar `NOTAS_DISP_9\NOTAS\311147` → `V2\NOTAS` y subir con `--solo 311147`. |

---

## 3. HUS0000410675

| Campo | Valor |
|---|---|
| HUS corto | HUS410675 |
| NE histórico (TSV) | 263284 |
| **NE V2 (vigente)** | **311136** |
| Radicado | 462915 |
| Acta | AC000456 |
| Valor Factura | $ 7.390.337 |
| Total Glosas | $ 245.072 |
| Valor Aceptado | $ 245.072 |
| Estado contexto V2 | COMPLETA pero **CUV RECHAZADO — RVC086** |
| Por qué no se subió | El CUV viene con `ResultState:false`. Motivo: "diagnóstico relacionado igual al principal" en el primer procedimiento del RIPS (periodo de atención 2025-08-08 a 2025-08-21). El portal aceptaría el upload pero la NC quedaría inválida. |
| **Acción** | **NO subir.** Escalar al área de **SISTEMAS / RIPS** para que reemita el RIPS corrigiendo el diagnóstico relacionado. Cuando MinSalud emita el nuevo CUV con `ResultState:true`, recién ahí subir. |

---

## 4. HUS0000413266

| Campo | Valor |
|---|---|
| HUS corto | HUS413266 |
| NE histórico (TSV) | 263303 |
| **NE V2 (vigente)** | **311183** |
| Radicado | 492346 |
| Acta | AC000456 |
| Valor Factura | $ 4.237.047 |
| Total Glosas | $ 458.490 |
| Valor Aceptado | $ 458.490 |
| Estado contexto V2 | **sin PDF** — descargar del DIAN |
| Por qué no se subió | falta el PDF CRRP de la NC en la carpeta `311183`. Sin el PDF, `consolidar_carpetas_notas.py` no completa la triada `NC_/XML_/CUV_` y el bot da `FALTAN_ARCHIVOS`. |
| **Acción** | Descargar el PDF CRRP de la NC desde el DIAN usando radicado **492346**. Renombrar a `NC_311183_HUS413266.pdf` dentro de `V2\NOTAS\311183\`. Verificar que el XML y JSON ya estén ahí; si no, correr `extraer_notas_credito.py` o el workaround PowerShell del share UNC. Después subir con `--solo 311183`. |

---

## 5. HUS0000417459

| Campo | Valor |
|---|---|
| HUS corto | HUS417459 |
| NE histórico (TSV) | 234326 |
| **NE V2 (vigente)** | **311186** |
| Radicado | 521665 |
| Acta | (sin Acta en TSV) |
| Valor Factura | $ 16.632.959 |
| Total Glosas | $ 4.282.669 |
| Valor Aceptado | $ 2.728.811 |
| Estado contexto V2 | **sin PDF** — descargar del DIAN |
| Por qué no se subió | mismo caso que HUS413266: falta el PDF CRRP. |
| **Acción** | Descargar PDF CRRP del DIAN (radicado 521665), renombrar a `NC_311186_HUS417459.pdf` dentro de `V2\NOTAS\311186\` y subir con `--solo 311186`. |

---

## 6. HUS0000420099

| Campo | Valor |
|---|---|
| HUS corto | HUS420099 |
| NE histórico (TSV) | 243804 |
| **NE V2 (vigente)** | **311188** |
| Radicado | 560611 |
| Acta | AC000619 |
| Valor Factura | $ 3.757.260 |
| Total Glosas | $ 161.635 |
| Valor Aceptado | $ 79.407 |
| Estado contexto V2 | ✅ Subida al SIMED |
| Por qué figuraría como pendiente | discrepancia. El contexto dice subida con las 3 pasadas OK ("Registro completado"). Si volvió a aparecer pendiente, las hipótesis son: (a) el portal rebotó la NC después (CUV inválido detectado tarde); (b) la subida marcó solo NC sin soportes (síntoma "Subida lista (después de 1s)"); (c) el reporte previo fue falso positivo. |
| **Acción** | Validar en el portal SIMED filtrando por HUS420099 si la columna "Estado" muestra NC cargada con soportes. Si NO está, re-correr `cargar_soportes_simed.py --solo 311188 --con-cabeza` y mirar las 3 pasadas. |

---

## 7. HUS0000421733

| Campo | Valor |
|---|---|
| HUS corto | HUS421733 |
| NE histórico (TSV) | 243806 |
| **NE V2 (vigente)** | **311190** |
| Radicado | 560613 |
| Acta | (sin Acta en TSV) |
| Valor Factura | $ 20.627.343 |
| Total Glosas | $ 2.111.169 |
| Valor Aceptado | $ 108.024 |
| Estado contexto V2 | ✅ Subida |
| Por qué figuraría como pendiente | mismo análisis que HUS420099. |
| **Acción** | Validar visualmente en SIMED. Si está pendiente, `--solo 311190 --con-cabeza`. |

---

## 8. HUS0000418576

| Campo | Valor |
|---|---|
| HUS corto | HUS418576 |
| NE histórico (TSV) | 243803 |
| **NE V2 (vigente)** | **311194** |
| Radicado | 562326 |
| Acta | (sin Acta en TSV) |
| Valor Factura | $ 2.518.999 |
| Total Glosas | $ 1.195.740 |
| Valor Aceptado | $ 1.195.740 |
| Estado contexto V2 | ✅ Subida |
| Por qué figuraría como pendiente | idem HUS420099. |
| **Acción** | Validar SIMED. Si pendiente, `--solo 311194 --con-cabeza`. |

---

## 9. HUS0000420160

| Campo | Valor |
|---|---|
| HUS corto | HUS420160 |
| NE histórico (TSV) | 243805 |
| **NE V2 (vigente)** | **311197** |
| Radicado | 568849 |
| Acta | AC000619 |
| Valor Factura | $ 4.170.179 |
| Total Glosas | $ 42.800 |
| Valor Aceptado | $ 42.800 |
| Estado contexto V2 | ✅ Subida |
| Por qué figuraría como pendiente | idem. |
| **Acción** | Validar SIMED. Si pendiente, `--solo 311197 --con-cabeza`. |

---

## 10. HUS0000422238

| Campo | Valor |
|---|---|
| HUS corto | HUS422238 |
| NE histórico (TSV) | **no figura** en el TSV |
| **NE V2 (vigente)** | **311199** |
| Radicado | (no en TSV — pedir a facturación) |
| Acta | (no en TSV) |
| Valor Factura | (no en TSV) |
| Total Glosas | (no en TSV) |
| Valor Aceptado | (no en TSV) |
| Estado contexto V2 | ✅ Subida |
| Por qué figuraría como pendiente | idem. Pero también: como no está en el TSV histórico, vale la pena confirmar con facturación que la NC 311199 efectivamente corresponde a HUS422238. |
| **Acción** | Validar SIMED. Si pendiente, `--solo 311199 --con-cabeza`. Confirmar con facturación que 311199 ↔ HUS422238. |

---

## 11. HUS0000435485

| Campo | Valor |
|---|---|
| HUS corto | HUS435485 |
| NE histórico (TSV) | 264792 |
| **NE V2 (vigente)** | **311222** |
| Radicado | 637718 |
| Acta | (sin Acta en TSV) |
| Valor Factura | $ 27.102.523 |
| Total Glosas | $ 1.662.440 |
| Valor Aceptado | $ 1.662.440 |
| Estado contexto V2 | ⚠ NC subió pero soportes pendientes |
| Por qué no se subió completa | la pasada 1 del bot grabó la NC en el form principal pero los 3 archivos (PDF/XML/JSON) no quedaron persistidos. El portal muestra la NC sin soportes obligatorios. |
| **Acción** | Re-correr `cargar_soportes_simed.py --solo 311222 --con-cabeza --destino "...\V2\NOTAS"`. Si vuelve a aparecer el síntoma "Subida lista (después de 1s)", revisar manualmente. |

---

## 12. HUS0000440328

| Campo | Valor |
|---|---|
| HUS corto | HUS440328 |
| NE histórico (TSV) | **302111** |
| NE V2 (contexto) | **sin NE** — pedir al área |
| Radicado | 670496 |
| Acta | (sin Acta en TSV) |
| Valor Factura | $ 19.152.692 |
| Total Glosas | $ 13.553.900 |
| Valor Aceptado | $ 2.168.866 |
| Estado contexto V2 | sin NE — bloqueado |
| Por qué no se subió | el contexto V2 dice "sin NE", pero el TSV tiene NE histórico **302111**. Hay discrepancia: o (a) el NE 302111 fue anulado y nadie lo notificó, o (b) está vigente y el contexto V2 quedó desactualizado. Sin NE confirmado no se puede armar la carpeta NC/XML/CUV. |
| **Acción** | Preguntar al **área de facturación**: "¿La factura HUS0000440328 tiene NC vigente 302111, o se emitió una nueva NC con NE distinto?" Si la respuesta es 302111, armar carpeta `302111` siguiendo el pipeline (renombrar → extraer share → consolidar → verificar CUV → subir). |

---

## Patrón general — agrupamiento por motivo de bloqueo

| Motivo | Facturas | Conteo |
|---|---|---|
| Carpeta en lote anterior, falta copiar al V2 | HUS404136, HUS411234 | 2 |
| CUV RECHAZADO (bloqueo MinSalud) | HUS410675 | 1 |
| Sin PDF CRRP (descargar DIAN) | HUS413266, HUS417459 | 2 |
| Subida marcada OK pero "vuelve a pendientes" | HUS420099, HUS421733, HUS418576, HUS420160, HUS422238 | 5 |
| NC subió, soportes pendientes (re-correr) | HUS435485 | 1 |
| Sin NE confirmado | HUS440328 | 1 |
| **TOTAL** | | **12** |

## Orden recomendado de ataque

1. **Las 5 "ya subidas que vuelven"** (420099, 421733, 418576, 420160, 422238):
   revisar en SIMED de un saque para entender si fue rebote masivo o caso a
   caso. Esto puede limpiar 5 de las 12 sin tocar archivos.
2. **HUS435485** (re-correr soportes): 1 comando, tarda 1-2 min.
3. **HUS404136 y HUS411234** (copiar carpetas de DISP_10/DISP_9 y subir): 2
   `Copy-Item` + un bot run para los 2 NEs.
4. **HUS413266 y HUS417459** (descargar PDF DIAN): el cuello de botella es el
   DIAN — abrir el portal, login, buscar por radicado, descargar.
5. **HUS440328** (consultar facturación): mandar correo / mensaje. Esperar
   respuesta y después armar carpeta.
6. **HUS410675** (CUV RVC086): escalar a SISTEMAS. Largo plazo, no bloquea las
   otras 11.

## Verificar primero el estado real

Antes de tomar acción, correr `diagnosticar_local.ps1` (en esta misma carpeta)
para confirmar archivos en disco y estado de CUV. El reporte sale en
`docs\diagnostico_lote_v2_pendientes\reporte_diagnostico.csv`.
