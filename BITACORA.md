# BITÁCORA — Motor de Glosas HUS

> **Memoria común de todo el trabajo.** Este archivo es el "cuaderno central"
> del proyecto. Sirve para que, en cualquier chat nuevo de Claude Code, se
> pueda retomar el trabajo sin empezar de cero: qué se ha hecho, qué falta y
> qué sigue.
>
> **Cómo se usa (regla fija):**
> - Al **empezar** una sesión: leer primero esta bitácora.
> - Al **terminar** una sesión: actualizarla con lo que se hizo ese día, lo que
>   quedó pendiente y lo que sigue mañana, **poniendo la fecha**.
>
> Escrito en lenguaje sencillo, pensado para el área de cartera/glosas (no para
> programadores).

---

## ¿Qué es este proyecto?

Un conjunto de "robots" (programas que manejan solos el navegador y el
computador) para **responder glosas médicas de forma automática** en las
plataformas de las EPS, y para **organizar los soportes y las evidencias** del
cargue. El objetivo es hacer en minutos lo que antes se hacía factura por
factura, a mano, durante horas.

Todo esto es para la **ESE Hospital Universitario de Santander (HUS)**.

---

## Mapa rápido: qué robot sirve para qué

| Herramienta (archivo) | ¿Para qué sirve? |
|---|---|
| `tools/responder_glosas_fomag.py` | **Robot de FOMAG (Horus).** Responde glosas **RATIFICADAS**: entra, va a Auditoría, abre el cuadro naranja, filtra la factura, le da RESPUESTA, elige el código **RE9901**, pega el texto de respuesta, sube el PDF de soporte, confirma (chulito) y da GUARDAR RESPUESTA. Toma pantallazo de evidencia de cada una. |
| `tools/responder_glosas_coosalud.py` | **Robot de COOSALUD.** Responde glosas en el portal de COOSALUD (busca la factura, responde por lotes, confirma el guardado, retoma las que quedaron "En Pausa"). |
| `tools/responder_glosas_simed.py` | **Robot de SIMED.** Responde glosas en la plataforma SIMED. |
| `tools/cargar_soportes_simed.py` | Sube los soportes (PDF) a SIMED. |
| `tools/evidencias_a_pdf.py` | **Junta los pantallazos de evidencia en un solo PDF** (una factura por página), para radicar. Ej.: archivo `GR-33-XXXX-2026.pdf`. |
| `tools/evidencias_a_word.py` | Igual que el anterior, pero arma un **Word** en vez de PDF (se usó primero con COOSALUD). |
| `tools/motor_glosas_hus.py` | **Sugiere respuestas** aprendiendo del histórico de glosas ya contestadas (formato TRÁMITE). |
| `tools/verificar_glosas_coosalud.py` | Revisión rápida de qué glosas quedan pendientes en COOSALUD. |
| `tools/verificar_cuv_notas.py` | Revisa el estado del **CUV** (MinSalud) de las notas crédito. |
| `tools/login_dg.py` | Entra solo a **Dinámica Gerencial .NET** (el sistema de escritorio del hospital). |
| `tools/renombrar_y_organizar_notas.py`, `consolidar_carpetas_notas.py`, `extraer_notas_credito.py`, `dividir_notas_por_acta.py`, `organizar_por_gestor.py`, etc. | **Organización de notas crédito**: renombrar, ordenar y armar las carpetas de soportes. |

> Cada robot importante tiene su guía de uso en un archivo `README_...md` dentro
> de `tools/`.

---

## Resumen de lo trabajado (por fecha)

### 11 de junio de 2026 — Arranca el robot de COOSALUD
- Se creó el **primer robot** para responder glosas: **COOSALUD**.
- Ese día se afinó mucho para que aguantara la lentitud del portal: buscar la
  factura exacta, esperar a que cargue la grilla, **confirmar** que la respuesta
  quedó guardada, y **retomar** las facturas que quedaban a medias ("En Pausa").
- Se agregaron opciones para hacer **pilotos controlados** (responder solo unas
  pocas facturas, o una lista específica).
- Se creó `evidencias_a_word.py` para **juntar los pantallazos** de cierre en un
  solo Word (una factura por página).

### 12 al 19 de junio de 2026 — Notas crédito y herramientas de apoyo
- **12/06:** revisión rápida de pendientes de COOSALUD; organización de notas
  crédito (renombrar en sitio, cruzar nota ↔ factura).
- **16/06:** herramienta para revisar el **CUV** de las notas crédito;
  `motor_glosas_hus.py`, que **propone respuestas** a partir del histórico ya
  contestado.
- **17/06:** `login_dg.py`, para entrar automáticamente a **Dinámica Gerencial**.
- **19/06:** ajuste del renombrado de notas para **SIDME (Dispensario)**.

### 22 al 23 de junio de 2026 — Mejoras a COOSALUD/SIMED y documentación
- COOSALUD más completo: usar soportes alternos cuando falta el principal,
  responder también glosas de **pertinencia/calidad** y las **residuales** del
  portal que no venían en el Excel.
- Robot de **SIMED** (cerrar avisos antes de subir soportes).
- Se escribieron **guías** separadas por EPS para poder retomar en chats nuevos.

### 24 de junio de 2026 — Nace el robot de FOMAG (Horus)
- Se creó `responder_glosas_fomag.py` para responder glosas **RATIFICADAS** en
  la plataforma de FOMAG (Horus).
- Se dejó todo el "camino" funcionando y a prueba de tropiezos: detectar bien
  cuándo ya entró (login real), **darle clic al cuadro naranja**, filtrar la
  factura, encontrar la fila correcta por el botón **RESPUESTA**, y leer la
  tabla correcta del formulario.
- Se dejó el control de calidad del código (CI) en **verde**.

### 25 de junio de 2026 — Se completa el paso a paso de FOMAG
- El robot ya hace la secuencia completa: elegir el código **RE9901**, esperar a
  que abra el cuadro de texto del **Detalle Rta 2 prestador**, pegar el texto,
  **subir el PDF** de soporte sin que se atore, y **no guardar** si algo no
  cargó (para no dejar respuestas incompletas).

### 26 de junio de 2026 — Evidencias en un solo PDF
- Se creó `evidencias_a_pdf.py`: junta todos los pantallazos de un cargue en un
  **único PDF** (una factura por página, con su número arriba), listo para
  radicar con el nombre `GR-33-XXXX-2026.pdf`.

### 1 de julio de 2026 — Facturas con ceros a la izquierda
- El robot de FOMAG ahora **reconoce las facturas aunque el PDF venga con ceros
  adelante** (ej.: el soporte se llama `HUS0000505761.pdf` y en la plataforma
  aparece como `HUS505761`). Antes no las emparejaba.

### 2 de julio de 2026 — Limpieza del robot de FOMAG
- Repaso final del robot de FOMAG: se corrigió un detalle, se quitó código que
  ya no se usaba y se ordenó, **sin cambiar la forma de operarlo**.

### 22 de julio de 2026 — Cargues reales, informe a gerencia y esta bitácora
- Se procesaron **lotes reales** de glosas ratificadas de FOMAG (alrededor de 20
  facturas por corrida, cerca de un minuto cada una) y se consolidaron sus
  evidencias en PDF (`GR-33-XXXX-2026`).
- Se preparó un **informe para gerencia** que compara el trabajo automatizado
  con el proceso anterior (manual), para mostrar la efectividad.
- Se creó **este archivo (`BITACORA.md`)** como memoria común, y el archivo
  `CLAUDE.md` con la instrucción de leer y actualizar la bitácora en cada
  sesión.

---

## PENDIENTE

- **FOMAG — listar facturas de la pestaña RATIFICADAS:** el modo que "lista"
  todas las facturas de esa pantalla todavía **no funciona** (la grilla de esa
  pestaña no es una tabla común y el robot no la lee de corrido). Por ahora se
  trabaja factura por factura o por lista.
- **FOMAG — solo está lista la pestaña RATIFICADAS.** Faltan las otras
  (PENDIENTES, RADICADAS, CONCILIACIÓN) si en algún momento se quieren
  automatizar.
- **FOMAG — pestaña "HISTÓRICO CONCILIACIÓN":** el robot aún no la reconoce bien
  por el nombre.
- **Informe a gerencia — dato de tiempo manual:** falta medir cuánto tomaba
  responder una glosa **a mano** para poder calcular el ahorro exacto (el
  "antes vs. ahora") con números firmes.

---

## PARA MAÑANA

- **Seguir cargando los lotes de ratificadas de FOMAG** que vayan llegando, con
  el mismo procedimiento (RE9901 + texto + PDF + chulito + pantallazo + GUARDAR
  RESPUESTA) y consolidar las evidencias en su PDF `GR-33-XXXX-2026`.
- **Tomar el tiempo del proceso manual** de una o dos glosas para cerrar el
  número del ahorro en el informe de gerencia.
- (Opcional, si se necesita) empezar a mirar las otras pestañas de FOMAG o
  arreglar el "listar" de la grilla de ratificadas.

---

*Última actualización: 22 de julio de 2026.*
