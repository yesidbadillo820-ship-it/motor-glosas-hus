# SINAC OS — Sistema Operativo Inteligente para Auditoría, Glosas y Conciliación

**Versión:** 2.0
**Estado:** Arquitectura Base (Blueprint Maestro)
**Autor:** Yesid Pérez — ESE Hospital Universitario de Santander
**Fecha de adopción:** 27 de julio de 2026

> **Documento rector del proyecto. Ningún desarrollo podrá realizarse sin
> respetar esta arquitectura.**

---

## 1. Visión del proyecto

### Misión

Construir un ecosistema inteligente para la gestión integral de glosas,
auditoría, conciliación, radicación, documentación y automatización
hospitalaria, donde la Inteligencia Artificial no sea una herramienta aislada,
sino el **núcleo operativo** del sistema.

El sistema debe convertirse en el asistente principal del auditor. No será
únicamente un software para responder glosas: será el **sistema operativo del
área de glosas**.

## 2. Filosofía

- La IA no reemplaza al auditor.
- La IA elimina el trabajo repetitivo.
- El auditor toma decisiones.
- La IA ejecuta.

## 3. Principios

Todo desarrollo debe cumplir estos principios.

| Principio | Definición |
|---|---|
| **Automatización primero** | Si una tarea puede automatizarse, debe automatizarse. |
| **Una sola fuente de verdad** | Nunca existirán dos lugares con la misma información. |
| **Modularidad** | Cada módulo debe poder existir de manera independiente. |
| **Escalabilidad** | Cada componente debe soportar crecimiento sin ser reescrito. |
| **Trazabilidad** | Toda acción debe quedar registrada. |
| **IA en toda la plataforma** | No habrá un botón llamado "IA". Toda la plataforma estará impulsada por IA. |

## 4. Arquitectura general

```
                          SINAC OS
                             │
   ┌─────────────────────────────────────────────────────┐
   │              IA CENTRAL (ORQUESTADOR)               │
   └─────────────────────────────────────────────────────┘
        │         │           │            │           │
     Glosas     Bots    Expedientes   Biblioteca   Automatización
        │         │           │            │           │
        └──────────────  BASE DE CONOCIMIENTO  ────────────┘
```

## 5. IA Central

La IA Central será el cerebro del sistema. **Nunca ejecutará directamente
tareas**: su función será coordinar agentes especializados.

Debe conocer: contratos · normatividad · glosas · conciliaciones · RIPS ·
CUPS · CIE10 · PBS · manuales tarifarios · PDF · Word · Excel · servidor ·
expedientes · historial · respuestas anteriores · aprendizaje del usuario.

## 6. Orquestador

Toda petición del usuario pasa primero por el Orquestador.

**Ejemplo.** Usuario: *"Necesito responder esta glosa."* El Orquestador decide:

```
Leer PDF → Extraer datos → Buscar contrato → Buscar normas →
Consultar historial → Consultar respuestas similares → Construir respuesta →
Generar Word → Exportar PDF → Guardar expediente → Actualizar historial
```

## 7. Ecosistema de agentes IA

Cada agente realiza **una sola función**. Nunca existirá un agente gigante.

| Agente | Responsabilidad |
|---|---|
| **Glosas** | Análisis, clasificación, respuesta, ratificación, conciliación. |
| **Radicación** | Crear carpetas, nombrar archivos, capturar evidencias, generar Word, convertir a PDF, guardar, actualizar Excel, registrar radicación. |
| **Expedientes** | Administrar factura, historia clínica, RIPS, soportes, respuesta, conciliación, actas, correos, pagos. |
| **Conciliación** | Reemplaza completamente el Excel: analizar diferencias, construir conciliación, generar acta y PDF, calcular cartera, actualizar indicadores. |
| **Documental** | Leer PDF, Word, Excel, TXT, correo, ZIP, OCR, escáner. |
| **Evidencias** | Capturas automáticas, inserción en Word, generación de PDF, control de versiones. |
| **Servidor** | Leer carpetas, mover archivos, detectar duplicados, renombrar, crear estructura, monitorear, respaldar. |
| **Constructor** | Ante *"crea un bot"*: analizar, diseñar, programar, documentar, integrar, registrar. |

## 8. Módulos principales

1. **Inicio** — Centro de Operaciones.
2. **Bandeja Inteligente** — todas las glosas, priorizadas automáticamente.
3. **Expedientes** — cada factura tendrá un expediente único.
4. **Conciliaciones** — sistema inteligente, no Excel.
5. **Contratos** — motor documental.
6. **Biblioteca** — normatividad, tarifarios, resoluciones, circulares, sentencias.
7. **Automatización** — todos los bots.
8. **Herramientas** — centro de herramientas.
9. **Administración** — usuarios, permisos, configuración.

## 9. Eliminación de módulos

Eliminar módulos sin uso comprobado: Mando Ejecutivo, Cobranza Live, cualquier
módulo redundante, dashboards duplicados, reportes repetidos.

**Antes de eliminar, verificar dependencias.**

## 10. Centro de Automatización

Aquí vivirán todos los bots: monitor de carpetas · OCR · captura web ·
renombrador · buscador · correo · Excel · Word · PDF · conciliación ·
facturación · RIPS · historia clínica · contratos · backups · programador de
tareas.

## 11. Herramientas

Inspirado en iLovePDF, pero orientado a auditoría hospitalaria:

- **Documentos:** PDF, OCR, firmas, convertidores, compresores, extractor de
  tablas, comparador, editor.
- **Validadores:** RIPS, CUPS, CIE10, PBS, SOAT, ISS, tarifarios.

## 12. Radicación automática

```
Seleccionar factura → Solicitar consecutivo → Leer Excel → Obtener número →
Crear carpeta → Generar Word → Insertar evidencias → Exportar PDF →
Guardar → Actualizar historial → Registrar radicación
```

Las rutas deberán ser **parametrizables** (no codificadas), permitiendo
configurar estructuras como:

```
Año → Mes → Entidad → Tipo → Consecutivo → PDF → Word → Soportes
```

## 13. Conciliación

**Eliminar Excel.** Nuevo flujo:

```
Factura → Glosa → Respuesta → Valor aceptado → Valor rechazado → Norma →
Contrato → Observaciones → Acta → PDF → Firmas → Guardar expediente
```

## 14. Base de conocimiento

Todo debe indexarse: contratos, respuestas, glosas, PDF, normas, correos,
conciliaciones, resoluciones, sentencias, RIPS, manuales.

## 15. IA en toda la interfaz

Cada pantalla tendrá un **Copilot contextual**:

- Viendo un PDF → *"Falta la firma del auditor."*
- Viendo una conciliación → *"Existe una conciliación idéntica de 2025."*
- En contratos → *"La cláusula 18 respalda esta respuesta."*

## 16. Aprendizaje

La IA debe aprender de conciliaciones, respuestas exitosas, errores, el estilo
del usuario y los contratos. **Nunca olvidar.**

## 17. Plugins internos

El sistema deberá permitir agregar nuevos agentes **sin modificar el núcleo**.
Cada agente será un plugin.

## 18. Seguridad

Roles · permisos · auditoría · historial · versionado · backups · trazabilidad.

## 19. Roadmap

| Fase | Objetivo | Contenido |
|---|---|---|
| **1** | Refactorización del núcleo | Auditoría completa del sistema actual, eliminación de módulos obsoletos, unificación de componentes repetidos, reorganización de la navegación, definición de arquitectura modular. |
| **2** | IA Central y Orquestador | Implementación del orquestador, integración de la base de conocimiento, memoria operativa, copilot contextual. |
| **3** | Expedientes inteligentes | Expediente único por factura, gestión documental integrada, control de versiones. |
| **4** | Automatización | Radicación automática, gestión de carpetas, evidencias, generación documental. |
| **5** | Conciliación inteligente | Sustitución completa del Excel, actas automáticas, PDF, indicadores. |
| **6** | Ecosistema de agentes | Integración progresiva de los bots existentes, Centro de Automatización, plugins de agentes especializados. |
| **7** | Optimización continua | Aprendizaje basado en casos reales, métricas de productividad, recomendaciones inteligentes, nuevos agentes desarrollados desde la propia plataforma. |

## 20. Regla suprema del proyecto

> SINAC OS no es una aplicación de respuesta de glosas. Es un ecosistema
> inteligente que centraliza todos los procesos del área de auditoría, glosas,
> conciliación, documentación y automatización hospitalaria.

Toda nueva funcionalidad deberá responder estas preguntas **antes** de
desarrollarse:

1. ¿Automatiza una tarea repetitiva?
2. ¿Reduce el número de clics o el tiempo de trabajo?
3. ¿Puede reutilizar componentes existentes?
4. ¿Se integra con el Orquestador y la Base de Conocimiento?
5. ¿Genera trazabilidad y evidencia?
6. ¿Es escalable como un agente o plugin independiente?
7. ¿Aporta valor operativo real al auditor?

**Si la respuesta a la mayoría de estas preguntas es NO, la funcionalidad no
debe implementarse.**

---

## Anexo A — Hallazgos de la auditoría que condicionan esta arquitectura

Auditoría técnica del 27-jul-2026 sobre el sistema actual (motor-glosas-hus).
Estos hallazgos no modifican el blueprint: explican **desde dónde se parte**.

### A.1 El sistema está partido en dos mitades que no se hablan

Verificado sobre el código: los bots (`tools/`) **no ejecutan** el pipeline
completo — solo el último tramo (tipear en el portal). Ningún bot clasifica,
analiza, genera respuestas ni guarda historial: no hay una sola llamada HTTP
que no sea al portal. Las etapas de clasificar / analizar / generar sí existen,
pero viven en `app/` y **no están conectadas con los bots**.

**El puente entre las dos mitades es hoy un archivo Excel que viaja en el
escritorio de una PC.** Esto es exactamente lo que el Orquestador (§6) debe
eliminar.

### A.2 Inventario real de automatización

- 33 scripts en `tools/` = 16.100 líneas. Solo **7 son RPA** (37 % de las
  líneas); los otros 26 son procesamiento de archivos, Excel y PDF.
- Tecnología: **Playwright** (4 bots contra 2 portales web) y **pywinauto**
  (3 scripts contra 1 aplicación de escritorio). No hay Selenium.
- Bots existentes: COOSALUD, SIMED-glosas, SIMED-soportes, DGH.
  **SAVIA, EMSSANAR, VCO y MUTUAL SER no existen todavía** — consolidar ahora
  cuesta una fracción de lo que costará con siete.

### A.3 Violaciones del principio "una sola fuente de verdad"

| Concepto | Implementaciones hoy | Consecuencia |
|---|---|---|
| Catálogo de normas | 4 | Se contradicen sobre los plazos del Art. 57. |
| Ficha de contratos por EPS | 4 | La versión en código le gana a la base de datos: editar un contrato por pantalla es placebo. |
| Perfil de pagador | 3 (radicación, IA, constantes en bots) | El mismo pagador descrito de tres maneras que nadie reconcilia. |
| Catálogo de códigos de soporte ADRES | 6 | `PDX` significa dos cosas clínicas distintas según el archivo. |
| Taxonomía de familia de glosa | 3 | `CL` = "pertinencia clínica" en el backend y "calidad" en un asistente. |
| Escala de confianza del dictamen | 6 | Ninguna reconciliada entre sí. |
| Máquina de estados de la glosa | 3 | Las tres escriben el mismo campo. |
| Enrutador de modelo de IA | 2 | El flujo principal no usa el que dice ser el oficial. |
| Capa de sanitización post-IA | 3 (32 "redes finales") | Cosidas por orden cronológico de bug, no por diseño. |

### A.4 Módulos sin uso comprobado (§9)

- **62 de 127 endpoints** del router principal de glosas no tienen un solo
  botón en la interfaz.
- Módulos muertos verificados: `asignacion.py`, `bandeja.py`, `alertas.py`,
  `alerta_service.py`, `salud_total_service.py`, `texto_fijo_batch.py`,
  `multi_agent.py`, `rag_normativa.py`, `normativa_grafo.py`.
- Dos motores de glosa **fuera de la API** (`asistente_conciliacion_dispensario.py`,
  `motor_glosas_hus.py`) que reimplementan peor y sin IA lo que ya hace `app/`.

### A.5 Frontend

No existen componentes React: el frontend es **un único `static/index.html` de
23.125 líneas** con JavaScript vanilla. La modularidad exigida en §3 requiere
componentizar esa página.
