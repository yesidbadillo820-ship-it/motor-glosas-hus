# 🎓 Capacitación de Gestores — IA GLOSAS SINAC SC

**ESE Hospital Universitario de Santander · Área de Cartera**
Sistema: `motor-glosas-hus.onrender.com`

---

## 📋 Agenda (60–75 min)

1. **Contexto** (5 min) — qué es la IA GLOSAS y por qué lo estamos usando.
2. **Flujo del día a día** (10 min) — cómo arranca un gestor la mañana.
3. **Demo en vivo — 6 casos** (30 min) — copia/pega en pantalla.
4. **Herramientas del Centro Premium** (10 min) — reportes, digest, anomalías.
5. **Preguntas y ejercicio libre** (15 min).

---

## 1. Contexto en 3 frases

- El sistema reemplaza la redacción manual de dictámenes repetitivos.
- La IA consulta el **contrato cargado** y el **texto canónico institucional** antes de redactar.
- Las **ratificadas y extemporáneas** se responden solas: el gestor solo revisa.

**Métricas que pueden mostrar al comité** (las ven en el Centro Premium → Impacto):
- Glosas cerradas por la IA solas (hoy / semana / mes)
- USD ahorrados en tokens
- Horas de trabajo ahorradas

---

## 2. Flujo del día a día

### Al entrar (primeros 2 minutos)
1. Login → pantalla de inicio.
2. Click en el botón verde grande **⚡ Preparar el día**.
   - La IA aplica texto fijo a todas las **RATIFICADAS / EXTEMPORÁNEAS** pendientes.
   - Las cierra automáticamente → desaparecen de `Mis glosas`.
3. Ver el 🔔 del header — si hay número rojo, click → panel de notificaciones (vencidas, listas para enviar, menciones).

### Durante el día
- Entrar a **Mis glosas** → responder una por una.
- El chip 🤖 al lado del código dice si la glosa es `LISTA_ENVIAR`, `CASI_LISTA`, `REVISAR` o `INTERVENIR`.
- Priorizar las marcadas **REVISAR** o **INTERVENIR** (las de criterio humano).

### Al final del día
- **Centro Premium → Reportes → Descargar formato DGH** para el archivo que se sube al sistema DGH.
- **Centro Premium → Digest** para enviar el resumen del día al coordinador por WhatsApp o Telegram.

---

## 3. Demo en vivo — 6 casos

Cada caso se hace en el formulario **Analizar glosa**. Pegar textualmente el cuadro marcado.

---

### 🔹 Caso 1 — TARIFA con match perfecto (FAMISANAR)

**Frase para introducir:** *"Voy a analizar una glosa de Famisanar por tarifa. Miren lo rápido que el sistema encuentra el valor pactado."*

**Configuración:**
- EPS: `FAMISANAR EPS`
- Etapa: **INICIAL**
- Tono: **Conciliador**
- Factura: `HUS-DEMO-001`

**Texto de la glosa (copiar y pegar completo):**

```
TA0201 - El cargo por consulta presenta diferencias con los valores pactados - CUPS 890750 - CONSULTA DE URGENCIAS POR ESPECIALISTA EN GINECOLOGIA Y OBSTETRICIA - Valor objetado: $24.900 - SE REALIZA OBJECIÓN POR MAYOR VALOR COBRADO DE ACUERDO A TARIFA CONTRATADA CON EPS FAMISANAR. VALOR FACTURADO $114.900, VALOR RECONOCIDO $90.000
```

**Qué esperar:**
- Banner verde "Tarifa pactada encontrada · Defender".
- CUPS `890750`, contrato `S-13-1-03-1-04958`, modalidad `SOAT -5%`.
- Dictamen cita contrato + Circular 047/2025 MinSalud + UVB 2026 = $12.110.

---

### 🔹 Caso 2 — DMBUG con código viejo (homologación Res. 2641/2025)

**Frase:** *"Ahora una glosa del Dispensario Militar. La EPS dice 'no hay tarifa pactada' — pero nosotros SÍ la tenemos. Miren cómo el sistema homologa el código viejo al CUPS nuevo y lo encuentra."*

**Configuración:**
- EPS: `DISPENSARIO MEDICO DMBUG`
- Etapa: **INICIAL**
- Tono: **Firme**
- Factura: `HUS-DEMO-002`

**Texto de la glosa:**

```
TA0201 - El cargo por consulta, interconsulta o atención (visita) domiciliaria que viene relacionado o justificado en los soportes de cobro, presenta diferencias con los valores pactados o establecidos por la norma - CUPS 39147B-18 - CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA - Valor objetado: $168.563 - SE GLOSA MVC EN CONSULTA ESPECIALIZADA. NO HAY TARIFA PACTADA, NO HAY COTIZACION AVALADA POR SANIDAD MILITAR. SE RECONOCE TARIFA SOAT UVB VIGENTE CODIGO 39143
```

**Qué esperar:**
- Banner verde "Tarifa pactada encontrada · Defender 100% (facturado < pactado)".
- CUPS oficial homologado: `890348`.
- Valor pactado: **$231.556**.
- Valor facturado $168.563 **MENOR** al pactado → glosa injustificada.
- Dictamen cita contrato **440-DIGSA/DMBUG-2025** + Res. 2641/2025 (homologación) + Res. 054/2026 + 124/2026 HUS (tarifa propia).

---

### 🔹 Caso 3 — SOPORTES (historia clínica no adjunta)

**Frase:** *"Esta es la glosa más frecuente: 'falta historia clínica'. Ya no hay que redactar cada vez — la IA cita la normativa."*

**Configuración:**
- EPS: `NUEVA EPS`
- Etapa: **INICIAL**
- Tono: **Conciliador**
- Factura: `HUS-DEMO-003`

**Texto:**

```
SO0101 - Historia clínica no allegada - CUPS 890301 - CONSULTA DE CONTROL POR ESPECIALISTA EN MEDICINA INTERNA - Valor objetado: $58.000 - SE SOLICITA ADJUNTAR EPICRISIS Y REGISTRO DE ATENCIÓN COMPLETO, NO ANEXADO AL COBRO.
```

**Qué esperar:**
- Dictamen cita **Res. 1995/1999** (HC = plena prueba), **Res. 866/2021** (RIPS), **Res. 2275/2023** (Factura Electrónica).
- Argumento: los RIPS ya se radican con la FEV; la HC completa es reserva legal profesional, no exigible por pago ordinario.

---

### 🔹 Caso 4 — FACTURACIÓN (servicio no documentado)

**Frase:** *"Cuando la EPS alega que el servicio 'no tiene constancia' — la respuesta es RIPS + epicrisis."*

**Configuración:**
- EPS: `COOSALUD`
- Etapa: **INICIAL**
- Tono: **Conciliador**
- Factura: `HUS-DEMO-004`

**Texto:**

```
FA0401 - Servicio no documentado en los soportes de cobro - CUPS 890201 - CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN MEDICINA INTERNA - Valor objetado: $72.500 - NO SE EVIDENCIA EN LOS DOCUMENTOS SOPORTES LA PRESTACIÓN EFECTIVA DEL SERVICIO FACTURADO.
```

**Qué esperar:**
- Argumento: el servicio fue prestado y documentado en HC institucional.
- Cita: **Art. 177 Ley 100/1993**, Res. 1995/1999, Res. 2275/2023 (FEV).

---

### 🔹 Caso 5 — RATIFICADA (la IA cerró sola)

**Frase:** *"Las ratificaciones ya no se argumentan una por una. Miren: todas las marcadas como RATIFICADA ya quedaron respondidas con el texto institucional. Solo toca mandar a mesa de conciliación."*

**Pasos en vivo:**
1. Ir al **landing** → click **⚡ Preparar el día**.
2. Esperar el banner verde con el conteo (ej. *"marcadas respondidas: 12"*).
3. Abrir **Mis glosas → tab Respondidas** → mostrar que aparecen las que eran RATIFICADA.
4. Click en una → el dictamen muestra el texto canónico:
   > *"ESE HUS NO ACEPTA LA RATIFICACIÓN DE LA GLOSA Y MANTIENE LA RESPUESTA DADA EN EL TRÁMITE DE LA GLOSA INICIAL... SE SOLICITA A LA ENTIDAD PAGADORA LA PROGRAMACIÓN DE LA MESA DE CONCILIACIÓN..."*

**No se pega nada** — se demuestra que el sistema ya lo hizo automáticamente.

---

### 🔹 Caso 6 — EXTEMPORÁNEA (por plazo)

**Frase:** *"Cuando la EPS glosó pasados los 20 días hábiles — la glosa es improcedente de plano."*

**Configuración:**
- EPS: `SANITAS` (o cualquiera)
- Etapa: **INICIAL**
- **Fecha radicación**: elegir una fecha **30 días hábiles antes de hoy**
- **Fecha recepción**: **hoy**
- Factura: `HUS-DEMO-006`

**Texto:**

```
TA0201 - Diferencia en consulta - CUPS 890202 - CONSULTA DE PRIMERA VEZ POR MEDICINA GENERAL - Valor objetado: $50.000 - MAYOR VALOR COBRADO SOBRE TARIFA CONTRATADA
```

**Qué esperar:**
- Banner ámbar "GLOSA EXTEMPORÁNEA — N DÍAS HÁBILES" (N > 20).
- Dictamen cita **Art. 56 Ley 1438/2011** (plazo 20 días hábiles).
- Solicitud de levantamiento inmediato y total.

---

## 4. Herramientas del Centro Premium

Click en **⭐ Centro Premium** del landing (o sidebar). Modal con 7 pestañas — recorrerlas en orden:

| Pestaña | Qué muestra |
|---|---|
| **📊 Resumen** | KPIs del día, estado general del sistema. |
| **🤖 Autopilot** | Bandeja con cada glosa clasificada (LISTA_ENVIAR verde, INTERVENIR rojo). Botón **⚡ Aprobar en lote** cierra de un click todas las LISTA_ENVIAR con ≥85% confianza. |
| **📨 Digest** | Resumen del día en texto plano — copiar o enviar por WhatsApp/Telegram desde **Reportes**. |
| **🚨 Anomalías** | Duplicados (misma factura + CUPS + EPS) y patrones de EPS sospechosos. |
| **❤️ Salud** | Estado de BD, scheduler, caché, bots, anomalías. |
| **📥 Reportes** | **Formato DGH** (Excel para cargar al sistema DGH) · Reporte gerencial para Comité · Batch texto fijo · Envío digest manual. |
| **💎 Impacto** | *"La IA cerró X glosas hoy · ahorró Y USD · Z horas"* — ideal para mostrar ROI. |

---

## 5. Atajos y tips

### Atajos de teclado
- `Ctrl + N` → Nueva glosa
- `Ctrl + K` → Buscador (command palette)
- `Ctrl + /` → Refrescar KPIs del header
- `Ctrl + Shift + V` → Comandos de voz (Chrome/Edge)

### Tips visuales
- **Chip 🤖 LISTA_ENVIAR** (verde) en una fila = texto fijo aplicado, solo revisar y enviar.
- **Chip 🤖 INTERVENIR** (rojo) = requiere criterio humano, no confíes en la IA.
- **Banner amarillo** al responder una glosa = conflicto en los datos, leer completo.
- **Banner verde al responder** = caso claro, la IA tiene alta confianza.

---

## 6. FAQ / Troubleshooting en vivo

**P: No aparece la tarifa pactada, el banner dice "no encontrada".**
R: Verificá que se haya cargado el Excel del contrato de esa EPS en **Tarifas contratadas** (sidebar → Tarifas). Si el contrato es nuevo, pedí al coordinador que lo cargue.

**P: El dictamen viene con "CUPS INDICADO EN EL EXPEDIENTE".**
R: Quiere decir que el extractor no pudo identificar el CUPS en el texto. Asegurate de escribir `CUPS 890348` en el texto (con la palabra "CUPS" seguida del código).

**P: La IA tarda mucho / sale error "timeout".**
R: Esperá 10 segundos — el sistema tiene 3 reintentos automáticos. Si aún falla, el fallback a Groq se activa solo.

**P: Quiero cambiar el gestor asignado a una glosa (se la cargaron a quien no era).**
R: En `Mis glosas` activá **Ver todas (admin)** → botón **↪ Reasignar** al final de la fila (solo coordinador/super_admin).

**P: La EPS manda Excel sin códigos homologados.**
R: El sistema aplica la **Res. 2641/2025** automáticamente — mapea códigos viejos (39147B-18 → 890348). Si aun así no encuentra, se puede agregar la equivalencia manualmente en el admin.

---

## 7. PDF con el dictamen — para llevar físico a la EPS

Después de que el dictamen se genere en pantalla:

1. **En el panel del análisis** → botón **📄 Descargar PDF** (o `Exportar PDF`).
2. El PDF incluye:
   - Encabezado institucional con logo HUS
   - Datos completos de la glosa (EPS, factura, CUPS, valor objetado)
   - Dictamen formateado en párrafos
   - Marco normativo citado (numerado)
   - Firma electrónica (si aplicaste firma digital — Ronda 10-11)
   - Pie con correos: `CARTERA@HUS.GOV.CO`, `GLOSASYDEVOLUCIONES@HUS.GOV.CO`

Si el flujo es masivo:
- **Centro Premium → 📥 Reportes → Descargar formato DGH** descarga un Excel con 26 columnas exactas + el dictamen limpio en la columna OBSERVACION — listo para cargar al sistema DGH.

---

## 8. Cierre

**Mensaje final para los gestores:**

> *"La IA no los reemplaza — les quita el trabajo mecánico. Cada glosa que el sistema cierra sola es una que ustedes no tienen que redactar. Pero la glosa REVISAR / INTERVENIR es donde ustedes aportan valor: criterio humano, casos atípicos, negociación. Ese es el trabajo que el sistema nunca va a hacer."*

**Pide al final:**
1. Que cada gestor haga un caso de prueba suyo (glosa real de su bandeja).
2. Que reporten cualquier error con screenshot + texto pegado.
3. Que usen el **🎓 Tour guiado** (botón del landing) las primeras veces para recordar el flujo.

---

**Contacto soporte técnico durante la capacitación**: anotar aquí el correo del coordinador / quien responde en vivo.

---

*Documento generado para la capacitación del 24-abr-2026. Sistema IA GLOSAS SINAC SC v1.x · 49 rondas de mejoras desplegadas · 513 tests automatizados.*
