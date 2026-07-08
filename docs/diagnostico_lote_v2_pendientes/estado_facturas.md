# Estado detallado por factura (12 pendientes — Lote V2)

> **ACTUALIZADO 2026-06-25** tras correr `diagnosticar_local.ps1` + inspección
> del contenido real de los `CUV_*.json`. Reescribe el agrupamiento previo
> porque el archivo `CUV_*.json` de 6 facturas resultó **no ser un CUV** sino
> un mensaje de error de conexión al servicio interno `dockerrips.hus.gov.co:9443`
> del HUS — el RIPS nunca llegó a validarse contra MinSalud.

Fuentes cruzadas:

- **TSV histórico**: `tools/notas_credito_ejemplo.tsv` (Radicado, Acta, valores).
- **Contexto V2**: `docs/CONTEXTO_DISPENSARIO_NOTAS.md` sección 7.
- **Diagnóstico real**: `reporte_diagnostico.csv` generado por
  `diagnosticar_local.ps1` + inspección de los JSON.

## Hallazgo principal

El contexto V2 marcaba como ✅ Subida a HUS420099, HUS421733, HUS418576,
HUS420160 y HUS422238. **Eso era falso positivo**. En realidad el
`CUV_*.json` de esas 5 + de HUS411234 contiene literalmente:

```
Se ha generado un error en el consumo
Se ha generado un error en el proceso de login
One or more errors occurred. (No connection could be made because the target
machine actively refused it. (dockerrips.hus.gov.co:9443))
```

(con variantes "A connection attempt failed" = timeout para 5 de las 6).

Esto significa que el servicio interno del HUS que envía RIPS a MinSalud no
estaba operativo cuando se generaron esas 6 notas. **Nunca hubo CUV válido**
para esas NCs. El bot las subió igual al SIMED porque el archivo JSON existía
con el nombre correcto, pero el portal terminó dejándolas en limbo (NC sin
CUV válido → no se persiste como completa).

## Agrupamiento real por causa raíz

| Causa | Conteo | Facturas | Quién resuelve |
|---|---|---|---|
| RIPS rechazado MinSalud — RVC086 (diagnóstico repetido) | 3 | HUS404136, HUS410675, HUS435485 | **SISTEMAS/RIPS** — reemitir RIPS con diagnóstico relacionado distinto |
| RIPS nunca validado — servicio `dockerrips.hus.gov.co:9443` caído | 6 | HUS411234, HUS420099, HUS421733, HUS418576, HUS420160, HUS422238 | **SISTEMAS** — reintentar envío cuando el servicio esté UP, regenerar CUV |
| Sin PDF CRRP (descargar DIAN) | 2 | HUS413266, HUS417459 | **Yo (auditor)** — bajar PDFs |
| Sin NE V2 | 1 | HUS440328 | **Facturación** — confirmar NE vigente |
| **TOTAL** | **12** | | |

**9 de las 12** se desbloquean con una sola gestión al área de SISTEMAS.

---

## 1. HUS0000404136

| Campo | Valor |
|---|---|
| HUS corto | HUS404136 |
| NE V2 | 311131 |
| NE histórico (TSV) | 263272 |
| Radicado | 457325 | Acta AC000456 |
| Valores | $ 2.169.054 / $ 61.708 / $ 10.218 |
| Estado en disco | COMPLETA (NC+XML+CUV en V2) |
| **CUV real** | `ResultState:false` — **RVC086** "Código de diagnóstico repetido" |
| Estado contexto (DESACTUALIZADO) | "COMPLETA copiar de DISP_10" |
| Por qué no se subió | El CUV está rechazado por MinSalud. El RIPS tiene un diagnóstico relacionado igual al principal. |
| **Acción** | **NO subir.** Escalar a SISTEMAS para reemitir el RIPS con el diagnóstico corregido. Cuando llegue nuevo CUV con `ResultState:true`, recién subir. |

---

## 2. HUS0000411234

| Campo | Valor |
|---|---|
| HUS corto | HUS411234 |
| NE V2 | 311147 |
| NE histórico (TSV) | 263288 |
| Radicado | 460616 | Acta AC000456 |
| Valores | $ 812.155 / $ 115.942 / $ 12.589 |
| Estado en disco | COMPLETA (NC+XML+CUV en V2) |
| **CUV real** | **JSON inválido** — contiene error: `No connection could be made because the target machine actively refused it. (dockerrips.hus.gov.co:9443)` |
| Estado contexto (DESACTUALIZADO) | "COMPLETA copiar de DISP_9" |
| Por qué no se subió | El archivo `CUV_311147_HUS411234.json` no es un CUV: es el mensaje de error que devolvió el servicio interno del HUS al intentar validar el RIPS contra MinSalud. Nunca hubo CUV. |
| **Acción** | Escalar a SISTEMAS — verificar `dockerrips.hus.gov.co:9443`, reintentar el envío del RIPS y regenerar el `ResultadosDoker_*.json`. Después re-correr `consolidar_carpetas_notas.py` + `verificar_cuv_notas.py` + `cargar_soportes_simed.py --solo 311147`. |

---

## 3. HUS0000410675

| Campo | Valor |
|---|---|
| HUS corto | HUS410675 |
| NE V2 | 311136 |
| NE histórico (TSV) | 263284 |
| Radicado | 462915 | Acta AC000456 |
| Valores | $ 7.390.337 / $ 245.072 / $ 245.072 |
| Estado en disco | COMPLETA (NC+XML+CUV en V2) |
| **CUV real** | `ResultState:false` — **RVC086** "Código de diagnóstico repetido" |
| Estado contexto | COMPLETA con CUV RECHAZADO RVC086 (coincide) |
| Por qué no se subió | RIPS rechazado por MinSalud. |
| **Acción** | Mismo correo a SISTEMAS junto con HUS404136 y HUS435485 — todas tienen RVC086. |

---

## 4. HUS0000413266

| Campo | Valor |
|---|---|
| HUS corto | HUS413266 |
| NE V2 | 311183 |
| NE histórico (TSV) | 263303 |
| Radicado | 492346 | Acta AC000456 |
| Valores | $ 4.237.047 / $ 458.490 / $ 458.490 |
| Estado en disco | **carpeta `311183` no existe en V2** |
| Estado contexto | "sin PDF — descargar del DIAN" (coincide) |
| Por qué no se subió | No hay carpeta ni archivos. |
| **Acción** | Descargar PDF CRRP del DIAN (radicado 492346), correr el pipeline desde `renombrar_y_organizar_notas.py --hus-corto` → `extraer_notas_credito.py` → `consolidar_carpetas_notas.py` → `verificar_cuv_notas.py`. Si el CUV sale OK, subir. |

---

## 5. HUS0000417459

| Campo | Valor |
|---|---|
| HUS corto | HUS417459 |
| NE V2 | 311186 |
| NE histórico (TSV) | 234326 |
| Radicado | 521665 |
| Valores | $ 16.632.959 / $ 4.282.669 / $ 2.728.811 |
| Estado en disco | **carpeta `311186` no existe en V2** |
| Estado contexto | "sin PDF — descargar del DIAN" (coincide) |
| **Acción** | Idem HUS413266 con radicado 521665. |

---

## 6. HUS0000420099

| Campo | Valor |
|---|---|
| HUS corto | HUS420099 |
| NE V2 | 311188 |
| NE histórico (TSV) | 243804 |
| Radicado | 560611 | Acta AC000619 |
| Valores | $ 3.757.260 / $ 161.635 / $ 79.407 |
| Estado en disco | COMPLETA (NC+XML+CUV en V2) |
| **CUV real** | **JSON inválido** — `A connection attempt failed... dockerrips.hus.gov.co:9443` |
| Estado contexto (DESACTUALIZADO) | "✅ Subida al SIMED" |
| Por qué no se subió | El CUV nunca fue válido. La supuesta subida del bot dejó la NC en limbo en el portal — por eso vuelve a aparecer como pendiente. |
| **Acción** | SISTEMAS — regenerar CUV. Luego re-correr `cargar_soportes_simed.py --solo 311188 --con-cabeza`. |

---

## 7. HUS0000421733

| Campo | Valor |
|---|---|
| HUS corto | HUS421733 |
| NE V2 | 311190 |
| NE histórico (TSV) | 243806 |
| Radicado | 560613 |
| Valores | $ 20.627.343 / $ 2.111.169 / $ 108.024 |
| Estado en disco | COMPLETA con CUV inválido (dockerrips) |
| **Acción** | Idem HUS420099 → SISTEMAS regenera CUV, luego re-subir. |

---

## 8. HUS0000418576

| Campo | Valor |
|---|---|
| HUS corto | HUS418576 |
| NE V2 | 311194 |
| NE histórico (TSV) | 243803 |
| Radicado | 562326 |
| Valores | $ 2.518.999 / $ 1.195.740 / $ 1.195.740 |
| Estado en disco | COMPLETA con CUV inválido (dockerrips) |
| **Acción** | Idem HUS420099. |

---

## 9. HUS0000420160

| Campo | Valor |
|---|---|
| HUS corto | HUS420160 |
| NE V2 | 311197 |
| NE histórico (TSV) | 243805 |
| Radicado | 568849 | Acta AC000619 |
| Valores | $ 4.170.179 / $ 42.800 / $ 42.800 |
| Estado en disco | COMPLETA con CUV inválido (dockerrips) |
| **Acción** | Idem HUS420099. |

---

## 10. HUS0000422238

| Campo | Valor |
|---|---|
| HUS corto | HUS422238 |
| NE V2 | 311199 |
| NE histórico (TSV) | (no figura) |
| Estado en disco | COMPLETA con CUV inválido (dockerrips) |
| **Acción** | Idem HUS420099. Confirmar con facturación que el NE 311199 corresponde a HUS422238 (porque no aparece en el TSV histórico). |

---

## 11. HUS0000435485

| Campo | Valor |
|---|---|
| HUS corto | HUS435485 |
| NE V2 | 311222 |
| NE histórico (TSV) | 264792 |
| Radicado | 637718 |
| Valores | $ 27.102.523 / $ 1.662.440 / $ 1.662.440 |
| Estado en disco | COMPLETA (NC+XML+CUV en V2) |
| **CUV real** | `ResultState:false` — **RVC086** "Código de diagnóstico repetido" |
| Estado contexto (DESACTUALIZADO) | "NC subió pero soportes pendientes — re-correr" |
| Por qué no se subió completa | El CUV está rechazado. El bot subió la NC pero el portal no acepta los soportes obligatorios porque el CUV no es válido. **Re-correr el bot no sirve** — el problema es el CUV, no el bot. |
| **Acción** | Mismo correo a SISTEMAS junto con HUS404136 y HUS410675 — RVC086. |

---

## 12. HUS0000440328

| Campo | Valor |
|---|---|
| HUS corto | HUS440328 |
| NE histórico (TSV) | 302111 |
| NE V2 | **vacío** |
| Radicado | 670496 |
| Valores | $ 19.152.692 / $ 13.553.900 / $ 2.168.866 |
| Estado en disco | no aplica (no hay NE V2 para armar carpeta) |
| Estado contexto | "sin NE — pedir al área" |
| **Acción** | Mandar a facturación: "¿Cuál es el NE vigente de HUS0000440328? El TSV histórico tiene 302111, ¿sigue vigente o se reemitió?" |

---

## Orden recomendado de ataque (revisado)

1. **Mandar el correo modelo a SISTEMAS** (`correo_sistemas.md` en esta carpeta)
   — destraba 9 facturas con una sola gestión.
2. **HUS413266 y HUS417459**: descargar PDFs del DIAN (puedo hacerlo en
   paralelo mientras SISTEMAS arregla el resto).
3. **HUS440328**: mensaje corto a facturación.

Mientras esperás respuesta de SISTEMAS, **no perdés tiempo intentando subir
nada de las 9** — todas necesitan CUV nuevo.

## Si SISTEMAS te dice "ya está, regeneré los CUV"

Antes de volver a subir, validá:

```powershell
cd C:\temp-notas
git pull
py tools\verificar_cuv_notas.py `
  --facturas "HUS404136,HUS411234,HUS410675,HUS420099,HUS421733,HUS418576,HUS420160,HUS422238,HUS435485" `
  --reporte  "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\reporte_cuv_pendientes.csv"
```

Si el reporte muestra OK para las 9, ahí sí re-correr el pipeline desde
`extraer_notas_credito.py` para refrescar los JSON, después `consolidar` y
después `cargar_soportes_simed.py`.
