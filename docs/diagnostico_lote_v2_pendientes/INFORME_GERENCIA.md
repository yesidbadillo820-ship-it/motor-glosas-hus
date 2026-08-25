# Informe de gestión — Diagnóstico y destrabe del Lote V2 de Notas Crédito (Dispensario Médico DMBUG)

**Área:** Auditoría de Cartera — Hospital Universitario de Santander (NIT 900006037-4)
**Fecha del trabajo:** 25 de junio de 2026
**Alcance:** 12 facturas con nota crédito pendiente de radicar en el portal SIMED del Dispensario Médico Bucaramanga (Subsistema de Salud FF.MM.)
**Herramientas:** scripts propios del repositorio `motor-glosas-hus` + asistente de IA (Claude Code)

---

## 1. Resumen ejecutivo

- Se diagnosticaron **12 facturas pendientes** que suman **$108,5 millones en valor facturado**, con **$23,9 millones en glosas** y **$8,7 millones en notas crédito por radicar** (11 de 12 con valores en el histórico de conciliación).
- El diagnóstico automatizado reveló que **el registro previo estaba equivocado en 6 de las 12 facturas**: 5 figuraban como "subidas OK" al SIMED y 1 como "re-intentar cargue", cuando en realidad **ninguna tenía CUV válido del Ministerio de Salud** — nunca pudieron haberse radicado correctamente.
- Se identificó la **causa raíz exacta de cada factura**, con evidencia técnica textual: 9 de las 12 dependen del área de SISTEMAS (no de Cartera), 2 requieren descarga de PDF del DIAN y 1 confirmación de facturación.
- La verificación completa de las 12 facturas (archivos en disco + validación del CUV) corre ahora en **segundos, con un solo comando**, y deja reporte CSV con evidencia. Antes exigía revisión manual carpeta por carpeta en el share de red y factura por factura en el portal (estimado: 20–30 min por factura, entre 4 y 6 horas para un lote como este) y aún así el estado registrado resultó incorrecto.
- Se entregó a SISTEMAS un **escalamiento con soporte técnico preciso** (servicio caído, puerto, mensaje de error textual, códigos de rechazo MinSalud por nota), en lugar del reporte genérico "la nota no sube" que antes obligaba a SISTEMAS a re-diagnosticar desde cero.

## 2. El problema

Al cierre del lote anterior quedaron 12 facturas del Dispensario sin radicar su nota crédito en SIMED, sin claridad de por qué. El registro que se llevaba (manual) indicaba:

- 5 supuestamente ya subidas ✅ — pero volvían a aparecer pendientes.
- 1 supuestamente lista para "re-correr el cargue".
- Las demás con motivos varios (sin PDF, CUV rechazado, sin número de nota).

Cada intento de avance implicaba volver a revisar a mano el share de facturación electrónica, las carpetas locales y el portal, sin poder explicar la diferencia entre lo registrado y lo real.

## 3. Qué se hizo (todo el mismo día)

1. **Script de diagnóstico automatizado** (`diagnosticar_local.ps1`): recorre las 12 carpetas de notas, verifica la triada de soportes (PDF + XML + CUV), parsea el JSON del CUV y clasifica cada factura por estado real. Genera reporte CSV con evidencia.
2. **Inspección del contenido real de los CUV**: se descubrió que 6 archivos "CUV" no eran validaciones del Ministerio sino **mensajes de error de conexión** al servicio interno del hospital (`dockerrips.hus.gov.co:9443`), guardados como si fueran el resultado. Ese servicio estaba caído cuando se generaron esas notas: el RIPS nunca llegó a validarse.
3. **Carpeta de trabajo `PENDIENTES_12`** armada automáticamente: 12 subcarpetas nombradas por causa raíz (`RVC086_`, `DOCKERRIPS_`, `SIN_PDF_`, `SIN_NE_`), cada una con los soportes disponibles y una ficha `_ESTADO.txt` (factura, NE, radicado, acta, valores, causa, qué falta, próxima acción), más un índice CSV.
4. **Plantilla de escalamiento a SISTEMAS** (`correo_sistemas.md`) con las 9 notas afectadas separadas en dos grupos técnicos, evidencia textual y el procedimiento de verificación posterior.
5. **Documentación versionada en Git**: ficha por factura, resumen CSV y procedimiento de re-validación quedaron en el repositorio — cualquier auditor puede retomar el caso sin depender de la memoria de una persona.
6. **Control de calidad del propio tooling**: en revisión posterior se detectaron y corrigieron 2 defectos de los scripts antes de que produjeran reportes erróneos en corridas futuras.

## 4. Hallazgo principal — el estado registrado vs. el estado real

| Estado según registro previo | Estado real verificado | Facturas |
|---|---|---|
| "Subida OK al SIMED" (5) | **CUV inválido** — el servicio de validación del hospital estaba caído; el RIPS nunca se validó ante MinSalud | HUS420099, HUS421733, HUS418576, HUS420160, HUS422238 |
| "Re-correr el cargue" (1) | **CUV rechazado por MinSalud (RVC086)** — re-correr el bot no servía de nada | HUS435485 |
| "Completa, lista para subir" (2) | 1 con CUV rechazado RVC086 y 1 con CUV inválido | HUS404136, HUS411234 |
| "CUV rechazado" (1) | Confirmado — RVC086 | HUS410675 |
| "Sin PDF" (2) | Confirmado | HUS413266, HUS417459 |
| "Sin NE" (1) | Confirmado, con NE histórico 302111 hallado en el archivo de conciliación para verificar con Facturación | HUS440328 |

**Sin este diagnóstico**, el camino natural habría sido re-intentar cargues al portal (que el portal acepta pero deja inválidos), revisar el SIMED factura por factura y reportar a SISTEMAS "no funciona" sin evidencia — semanas de ida y vuelta. **Con el diagnóstico**, cada factura tiene dueño y acción concreta desde el día uno.

## 5. Distribución por causa raíz y responsable

| Causa raíz | Facturas | Responsable de resolver |
|---|---|---|
| RIPS rechazado por MinSalud (RVC086 — diagnóstico repetido) | 3 | SISTEMAS/RIPS |
| RIPS nunca validado (servicio `dockerrips` caído) | 6 | SISTEMAS |
| Falta PDF CRRP (descargar del DIAN) | 2 | Auditoría de Cartera |
| NE por confirmar | 1 | Facturación |

**9 de 12 (75%) no eran destrabables desde Cartera** — la gestión efectiva era escalar con evidencia, no seguir intentando cargues.

## 6. Comparativo: proceso anterior vs. proceso actual

| Actividad | Antes (manual) | Ahora (automatizado) |
|---|---|---|
| Verificar estado de un lote de 12 notas | Revisión carpeta por carpeta en el share + factura por factura en el portal; 20–30 min c/u (est. 4–6 horas el lote) | **Un comando, segundos**, con reporte CSV de evidencia |
| Confiabilidad del estado | Registro manual: en este lote, **6 de 12 con estado equivocado** | Estado calculado desde los archivos y el contenido real del CUV |
| Diagnóstico de por qué no sube | "No sube, revisar" — sin causa | Causa raíz por factura con mensaje de error textual y código MinSalud |
| Escalamiento a SISTEMAS | Reporte genérico; SISTEMAS re-diagnostica desde cero | Correo con servicio, puerto, error textual y NEs agrupadas por tipo de falla |
| Armado de carpetas de trabajo | Copiar/pegar manual, sin ficha de estado | Script idempotente: 12 carpetas + ficha por factura + índice, en segundos |
| Continuidad del conocimiento | En la memoria del auditor / notas sueltas | Documentado y versionado en Git, reproducible por cualquiera |

Como referencia de la misma línea de trabajo ya en producción: el lote de respuesta de glosas del 22/06/2026 (8 facturas, 24 objeciones) se respondió completo en el portal en **26,9 minutos** con el bot, y en esta misma sesión se respondió una glosa ratificada FOMAG en **0,7 minutos** con evidencia de pantalla automática — actividades que manualmente tomaban horas por lote.

## 7. Estado y próximos pasos

| Acción | Responsable | Estado |
|---|---|---|
| Escalar a SISTEMAS los 2 grupos (correo con evidencia listo) | Auditoría | Plantilla entregada |
| Regenerar CUV de 6 notas (servicio dockerrips) | SISTEMAS | Pendiente |
| Reemitir RIPS de 3 notas (RVC086) | SISTEMAS/RIPS | Pendiente |
| Descargar 2 PDF CRRP del DIAN (radicados 492346 y 521665) | Auditoría | Pendiente |
| Confirmar NE de HUS440328 | Facturación | Pendiente |
| Re-validar los 9 CUV y radicar en SIMED cuando SISTEMAS confirme | Auditoría | Procedimiento documentado (1 comando) |

## 8. Soportes

Todo el trabajo queda auditable en el repositorio `motor-glosas-hus`, carpeta `docs/diagnostico_lote_v2_pendientes/`:

- `estado_facturas.md` — ficha detallada de las 12 facturas.
- `resumen.csv` — tabla con causa raíz, responsable y acción por factura.
- `correo_sistemas.md` — escalamiento técnico listo para enviar.
- `diagnosticar_local.ps1` / `armar_carpetas_pendientes.ps1` — herramientas reutilizables para futuros lotes.
- Carpeta local `PENDIENTES_12` con los soportes organizados por causa y ficha `_ESTADO.txt` por factura.
