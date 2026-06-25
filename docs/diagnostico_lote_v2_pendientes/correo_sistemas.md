# Plantilla — correo a SISTEMAS/RIPS para destrabar 9 notas crédito

Pegá el texto siguiente en un correo a SISTEMAS (CC al jefe de cartera).
Reemplazá `<NOMBRES DESTINATARIOS>` por los contactos reales.

---

**Asunto:** Solicitud de regeneración de CUV para 9 notas crédito Dispensario Médico (Lote V2 — junio 2026)

**Para:** `<EQUIPO SISTEMAS / RIPS HUS>`
**CC:** `<JEFE CARTERA / AUDITORÍA>`

Buenos días,

En el **Lote V2 del Dispensario Médico Bucaramanga (DMBUG) — junio 2026**
tenemos **9 notas crédito que no se pueden subir al portal SIMED** porque sus
CUVs vienen inválidos o rechazados desde el lado del HUS. Necesito apoyo del
área para destrabarlas en dos grupos:

## Grupo A — 6 notas crédito con CUV inválido (servicio `dockerrips.hus.gov.co:9443` caído al validar)

El archivo de resultado de validación que quedó en el share contiene
literalmente el mensaje:

```
Se ha generado un error en el consumo
Se ha generado un error en el proceso de login
One or more errors occurred. (No connection could be made because the target
machine actively refused it. / A connection attempt failed.
 - dockerrips.hus.gov.co:9443)
```

| # | Factura | NE (Nota Electrónica) | Periodo en share |
|---|---|---|---|
| 1 | HUS0000411234 | 311147 | (a confirmar — el JSON dice "connection refused") |
| 2 | HUS0000420099 | 311188 | (timeout) |
| 3 | HUS0000421733 | 311190 | (timeout) |
| 4 | HUS0000418576 | 311194 | (timeout) |
| 5 | HUS0000420160 | 311197 | (timeout) |
| 6 | HUS0000422238 | 311199 | (timeout) |

**Acción solicitada:** verificar disponibilidad del servicio
`dockerrips.hus.gov.co:9443` y reintentar el envío del RIPS de cada una de
estas 6 NEs a MinSalud. Cuando el `ResultadosDoker_<NE>.json` quede grabado
con `ResultState: true` en el share
`\\172.16.32.83\factura_electronica_net22\<periodo>\FACTURAS_NOTA\<NE>\RIPS\`,
notificarme para que yo re-corra el cargue al SIMED.

## Grupo B — 3 notas crédito con RIPS rechazado por MinSalud (RVC086 — Código de diagnóstico repetido)

| # | Factura | NE | Periodo de atención | Glosa MinSalud |
|---|---|---|---|---|
| 1 | HUS0000404136 | 311131 | (revisar RIPS) | RVC086 |
| 2 | HUS0000410675 | 311136 | 2025-08-08 a 2025-08-21 | RVC086 |
| 3 | HUS0000435485 | 311222 | (revisar RIPS) | RVC086 |

**RVC086** = "Código de diagnóstico repetido". El RIPS tiene un diagnóstico
relacionado igual al diagnóstico principal en el primer procedimiento,
lo cual MinSalud rechaza automáticamente.

**Acción solicitada:** reemitir el RIPS de las 3 NEs corrigiendo el
diagnóstico relacionado (distinto del principal), revalidarlo y obtener un
CUV nuevo con `ResultState: true`.

## Cómo verifico que esté listo

Cuando me confirmen "ya regeneré", yo voy a correr:

```
py tools\verificar_cuv_notas.py --facturas "HUS404136,HUS411234,HUS410675,HUS420099,HUS421733,HUS418576,HUS420160,HUS422238,HUS435485" --reporte reporte_cuv_pendientes.csv
```

Si las 9 salen con estado `OK` voy a re-correr el bot que carga al SIMED.
Si alguna sigue `RECHAZADO` les paso el código y la observación para iterar.

Quedo atento a su respuesta.

Saludos,

`<NOMBRE>`
Auditor de cartera — Hospital Universitario de Santander
NIT 900006037-4

---

## Anexo — qué pasa si no se regeneran

Las NCs ya están emitidas y publicadas en el DIAN. Sin CUV válido **no se
pueden radicar en el SIMED del Dispensario** y por tanto la cartera no se
cierra. Cada día sin cerrar va contra los indicadores de auditoría de cartera
del HUS frente al Subsistema de Salud FF.MM. (DMBUG).

El bloqueo no es del lado del Dispensario ni del SIMED — es interno del HUS
(el servicio `dockerrips` está down) o del propio RIPS (diagnóstico mal
codificado). Por eso necesito que SISTEMAS lo arregle: del lado del auditor
no hay nada más que hacer.
