# 📓 Bitácora del proyecto — Cuentas Médicas y Cartera · ESE HUS

> **Memoria común de trabajo.** Este archivo es el control central de todo lo que
> se ha hecho, lo que falta y lo que sigue. Sirve para que cualquier sesión de
> trabajo (cualquier chat de Claude Code) retome el hilo sin perder nada.

**Cómo se usa:**
- **Al empezar el día / una sesión:** leer esta bitácora para saber en qué punto vamos.
- **Al terminar:** anotar abajo, con la fecha, lo que se hizo, lo que quedó pendiente y lo que sigue mañana.

**Última actualización:** 22 de julio de 2026

---

## 🎯 Qué es este proyecto

Son dos herramientas al servicio del área de **Cuentas Médicas y Cartera** del Hospital Universitario de Santander:

1. **Motor de Glosas** — una aplicación que redacta automáticamente las respuestas a las glosas que ponen las EPS, con base en la normativa colombiana de salud. Es la base del proyecto (se viene construyendo desde abril de 2026).

2. **Suite de Radicación y Cartera** — el trabajo más reciente (junio–julio de 2026): un conjunto de herramientas que revisan las facturas antes de radicarlas ante las EPS, verifican que tengan todos sus soportes, dicen qué le falta a cada una y dónde está, y permiten controlar el estado de la cartera (radicado, glosado, pagado y saldo).

> ⚠️ **Garantía de seguridad (importante para auditoría):** todas las herramientas
> de radicación funcionan en modo **solo lectura**. No modifican, mueven ni borran
> ningún archivo o carpeta del sistema. Únicamente leen la información y generan
> reportes nuevos. Cero riesgo para los soportes originales.

---

## 🗓️ Lo que se ha hecho (por fecha)

### Abril – junio de 2026 · Motor de Glosas (la base)
Se construyó la aplicación que responde glosas médicas de forma automática: detección de glosas fuera de plazo, plantillas por tipo de glosa (tarifa, soportes, autorización, cobertura, pertinencia), cálculo de días hábiles con el calendario de festivos, gestión de contratos y tarifas de las EPS, exportación a Excel institucional y un marco normativo completo. Durante junio se hicieron numerosas rondas de mejora y corrección para elevar la calidad de las respuestas y afinar la detección de la EPS y de los códigos (CUPS, SOAT, medicamentos).

### 24 de junio de 2026 · Nace el motor de radicación de facturas
Se creó la herramienta que revisa automáticamente las facturas electrónicas y sus soportes, las clasifica (lista para radicar / le falta algo / hay que revisar) e identifica la EPS que debe pagar. Se le enseñó a leer las carpetas reales del hospital (factura electrónica de la DIAN y el escaneo), a reconocer los RIPS, el CUV y los documentos de la DIAN, y a reconocer más de una docena de pagadores por su razón social (NUEVA EPS y otros).

### 25 de junio de 2026 · Más entidades y el cruce de soportes
Se agregó la Regional de Aseguramiento N°5 y el estado "Particular" (pacientes que no son de ninguna EPS). Lo más importante: se creó el **cruce con los soportes clínicos** (epicrisis, evolución, urgencias, órdenes) que viven en discos aparte, para completar automáticamente las facturas que quedaban "en revisión".

### 30 de junio de 2026 · Cobertura ampliada, tablero y explorador
- **Radicador:** el cruce pasó a aceptar varias carpetas de soportes a la vez (están repartidos por mes) y a poder leer un listado pre-armado para no recorrer la red cada vez. Se agregó la Unión Temporal Salud Integral MAISFEN.
- **Tablero de Radicación y Cartera:** una página que muestra el radicado, glosado, pagado y saldo por EPS, con alertas de vencimiento, comparativo mensual y detalle por factura.
- **Explorador de Radicación:** un buscador para encontrar cada factura, ver qué le falta y en qué carpeta está, con una ficha de verificación factura por factura y el nombre del pagador cuando la EPS no se reconoce.

### 1 de julio de 2026 · Cruce por carpeta y diagnóstico
Se corrigió el cruce para tomar el número de factura de la **carpeta que la contiene** (antes solo miraba el nombre del archivo, y muchos soportes se perdían). El resumen ahora informa cuántas facturas recibieron soportes de verdad. Se creó además una herramienta de **diagnóstico** que verifica en segundos si el cruce está funcionando y por qué una factura no queda lista.

### 2 de julio de 2026 · Robustez y optimización
Se hizo la herramienta tolerante a los distintos formatos de archivo de Windows. Con apoyo de un segundo modelo de revisión (todo verificado y probado), se corrigieron varios errores finos y se optimizó el motor para procesar decenas de miles de archivos mucho más rápido. **89 pruebas automáticas** respaldan cada cálculo.

### 22 de julio de 2026 · Medición de impacto e informe para gerencia
- Se midió el resultado sobre el lote real de junio (**12.523 facturas**): al cruzar los soportes de todos los meses, las facturas listas para radicar pasaron de **42% a 49% (+961 facturas)**, y el cruce completó automáticamente **6.328 facturas** con 32.866 soportes.
- Se preparó un **informe ejecutivo** para socializar ante gerencia, comparando el proceso anterior (revisión manual) con el actual (motor automatizado).
- Se creó **esta bitácora** como memoria común del proyecto.

---

## ⏳ PENDIENTE (lo que falta)

- [ ] **Terminar la corrida con los soportes de todos los meses.** Armar el listado único de soportes (los 7 meses del disco) y volver a correr el motor, para medir cuánto más baja el grupo "revisar".
- [ ] **Cargar el tablero con datos reales.** Hoy la plantilla de seguimiento está vacía (muestra $0 pagado). Falta ingresar los pagos y glosas reales de al menos las EPS grandes (NUEVA EPS, COOSALUD).
- [ ] **Completar el catálogo de entidades.** Quedan alrededor de 24 facturas cuya EPS pagadora el sistema aún no reconoce ("entidad por resolver"). Falta exportar esa lista desde el explorador y agregar esas entidades.
- [ ] **Soportes de SOAT / tránsito.** Los formularios FURIPS de los accidentes de tránsito no traen el número de factura en el nombre, por lo que no cruzan automáticamente. Es un grupo pequeño que requiere una solución aparte.
- [ ] **Escanear los soportes que faltan.** Parte de las facturas "en revisión" simplemente todavía no tienen sus soportes clínicos escaneados. Esa es una tarea operativa del área; el explorador ya dice cuáles son y qué les falta.
- [ ] **Dejar las mejoras disponibles en forma permanente.** Integrar el trabajo a la versión principal del proyecto para que esté en todas las sesiones, sin importar en qué rama se trabaje.

---

## 📌 PARA MAÑANA (lo próximo a trabajar)

1. **Correr el motor con el índice completo de soportes** (los 3 pasos: armar el índice una vez → actualizar → correr leyendo el índice) y anotar aquí el nuevo porcentaje de facturas listas.
2. **Regenerar el explorador y el tablero** con el reporte actualizado, para ver el resultado nuevo factura por factura.
3. **Empezar a cargar el tablero** con los pagos y glosas reales de una EPS grande, para que el saldo de cartera deje de estar en cero.
4. **Revisar la lista de EPS no reconocidas** y agregarlas al catálogo, para bajar el grupo "entidad por resolver".

---

*Bitácora del proyecto de Cuentas Médicas y Cartera — ESE Hospital Universitario de Santander.*
