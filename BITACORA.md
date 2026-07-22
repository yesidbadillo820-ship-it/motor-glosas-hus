# BITÁCORA — Control central del trabajo en este repositorio

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> **Al iniciar cualquier sesión de trabajo, léelo primero.** Al terminar,
> actualízalo: qué se hizo hoy (con fecha), qué quedó pendiente y qué sigue
> mañana. Escrito en lenguaje claro, para un auditor, no para un programador.
>
> **Última actualización: 22 de julio de 2026.**

---

## De qué se trata este proyecto

Trabajo de auditoría de cartera para la **ESE Hospital Universitario de
Santander (HUS)**, apoyado en herramientas construidas en este repositorio:

1. **El Motor de Glosas** — aplicación web donde los gestores del HUS
   responden las glosas (objeciones) que las EPS le hacen a las facturas del
   hospital. La aplicación redacta la respuesta técnico-jurídica con
   inteligencia artificial, controla plazos legales, lleva el historial y
   produce los reportes. Corre en una máquina del propio hospital.
2. **Los bots de portales** — programas que hacen solos el trabajo repetitivo
   en los portales de cada entidad (COOSALUD, SIMED del Dispensario Médico,
   Dinámica Gerencial del HUS, portal VCO): responder glosas factura por
   factura, subir soportes, radicar, guardar pantallazos de evidencia.
3. **Herramientas de organización** — scripts que ordenan archivos Excel,
   notas crédito, soportes de radicación y arman los formatos que piden las
   entidades o el sistema interno del hospital (ERP).

---

## LO YA HECHO (resumen por fecha)

### Abril 2026 — Nace el Motor de Glosas

- **8 abr** — Primer commit. Versión inicial de la aplicación con respuesta
  automática de glosas, plazos de 20 días hábiles (Ley 1438) y códigos de
  respuesta según la Resolución 3047.
- **9–10 abr** — Corrección de fallas de seguridad (contraseñas, accesos),
  dictámenes de aceptación total/parcial, e **importación masiva de glosas
  desde Excel**.
- **13 abr** — Roles de usuarios (administrador, coordinador, gestor),
  registro de auditoría de cambios, panel de conciliaciones y módulo para
  las respuestas de SALUD TOTAL.
- **16 abr** — Carga de los **13 contratos reales del HUS** con sus tarifas,
  importación del Excel de recepción con semáforo de vencimientos, pestaña
  "Mis Glosas" por gestor y usuarios corporativos con nombres reales.
- **17 abr** — Gran tanda de funciones: alertas de vencimiento por correo,
  aprobación multi-estado, buscador global, exportar a Excel, informe
  mensual para gerencia, biblioteca de "argumentos ganadores", conciliación
  bilateral con acta, y presentación institucional del sistema.
- **20–30 abr** — Semanas de pulido intensivo de la calidad de las
  respuestas: que la IA no invente montos, ni cláusulas, ni normas; tono
  institucional; catálogo completo del Manual Único de Glosas; biblioteca
  normativa consultable; checklist de pre-radicación con puntaje.

### Mayo 2026 — Calidad, auditoría y primeros bots

- **4–8 may** — Migración del servidor a Fly.io, extracción de cláusulas de
  contratos desde PDF, verificación de citas normativas, respaldo con tres
  proveedores de IA, e importación masiva con vista previa y costo estimado.
- **9–12 may** — **Gran limpieza**: se eliminaron 22 módulos que no se
  usaban. La IA dejó de copiar plantillas y empezó a argumentar cada caso.
  Rediseño del panel "Analizar glosa".
- **14–19 may** — Excel-respuesta por correo a cada gestor, importación en
  segundo plano (la app ya no se congelaba), y arreglo del incidente que
  tumbaba la aplicación al importar.
- **20 may** — **Auditoría integral del sistema** (documento AUDITORIA.md):
  2.593 pruebas automáticas en verde, integración continua en GitHub y
  documento de arquitectura.
- **21 may** — Se aprobó el **Plan de Transformación 2.0**. Además: banco de
  50 plantillas HUS de respuesta, y primeros scripts de **notas crédito del
  Dispensario** (extraer, renombrar, organizar por gestor: 368 notas) y el
  **bot de SIMED** para subir soportes con evidencia.
- **22–29 may** — "Control de calidad" (Quality Gate) que revisa cada
  dictamen antes y después de la IA, y mejoras del bot SIMED por lotes.

### Junio 2026 — Los bots toman los portales y la calidad se mide

- **2–4 jun** — Herramientas para radicación ante **ADRES** (inspector de
  soportes, generador FUR desde RIPS). Arreglo de la integración continua.
- **9–10 jun** — **Bot de respuestas masivas de glosas en SIMED** (objeción
  por objeción, con reintentos y reporte CSV). Vault cifrado de credenciales.
  Groq como IA principal con respaldo de Claude.
- **12–16 jun** — Rondas 2 a 7 de corrección de calidad del dictamen,
  evaluadas con casos reales cada vez. Verificador del estado del CUV
  (MinSalud) para notas crédito. Sugeridor de respuestas desde el histórico.
- **17–19 jun** — Rondas 8 a 11: banco de respuestas HUS como ejemplos para
  la IA, auto-detección de la EPS, cambio del modelo de IA (Llama 4 Scout).
  Piloto de **ingreso automático a Dinámica Gerencial** (el sistema del HUS).
- **22–26 jun** — **El servidor se mudó a una máquina del propio HUS**
  (costo $0/mes, con túnel de Cloudflare y auto-actualización desde Git).
  Bot COOSALUD reforzado (soportes de respaldo, cierre de residuales,
  glosas de pertinencia). Guías de uso de los bots. **Radicador maestro
  multi-entidad**. PDF/Word consolidado de pantallazos de evidencia.
  Rondas 12 a 18 de calidad, ya con auditoría humana de dictámenes reales.
- **25 jun** — **Diagnóstico del Lote V2 del Dispensario**: 12 notas crédito
  trabadas; se descubrió que 6 tenían "CUV" que en realidad eran errores de
  conexión (el registro manual estaba equivocado). Cada factura quedó con
  causa raíz, evidencia y responsable (9 dependen de SISTEMAS).
- **30 jun** — Día enorme (62 commits): **tablero de calidad 0–10** que mide
  cada dictamen contra una rúbrica experta (el promedio de los 4 casos
  difíciles pasó de 2,5 a ~9), **Tablero de Radicación y Cartera** (alertas
  de mora +90, comparativos, exportar), homologador CUPS→SOAT para defensa
  tarifaria, banco de evidencia clínica nivel 1A, y muchas iteraciones del
  bot de Dinámica Gerencial.

### Julio 2026 — El expediente completo y el bot de objeciones VCO

- **1–3 jul** — "El expediente": la IA dejó de argumentar a ciegas. Ahora
  (1) **lee el contrato real** cargado en la base (26 cláusulas literales de
  11 pagadores), (2) **lee los soportes/historia clínica** adjuntos (hasta
  6 veces más texto, con mapa de folios), y (3) usa como ejemplo el
  **precedente ganado más parecido** al caso. Rondas 23 a 28 de calidad y
  dos incidentes de producción resueltos (app caída y arranque fallido).
- **7–8 jul** — Ronda 29: limpieza de código muerto y 27 hallazgos de
  auditoría interna corregidos. Se retiró el despliegue viejo de Fly.io.
- **10 jul** — **Informe para gerencia** del diagnóstico del Lote V2
  (12 notas crédito, $8,7 millones por radicar). Bot COOSALUD: mejoras para
  respuestas extemporáneas (RE9502 sin soporte).
- **17 jul** — **Nuevo bot "organizar objeciones VCO"** (pedido para SAVIA
  SALUD): toma el consolidado del acta de objeciones (como el de
  FIDUPREVISORA) y arma el archivo de cargue de 16 columnas para el ERP del
  hospital — o al revés, del archivo del ERP arma el consolidado. Detecta
  solo el formato, tolera variantes de encabezados, e imprime un resumen de
  control (facturas, objeciones y valor glosado por acta) para cuadrar
  contra el acta. Con 30 pruebas automáticas y guía de uso. Se abrió el
  **PR #167** (borrador). Nota: el archivo OBJECIONES.xlsx de SAVIA llegó
  vacío (solo encabezados) — aún se espera el archivo real con datos.
- **21 jul** — Se procesó el **CONSOLIDADO_VCO_FIDUPREVISORA.xlsx** real
  (41 objeciones, 4 facturas, 3 actas, $58,5 millones glosados) y se
  entregó el archivo de cargue generado. El bot aprendió dos variantes de
  encabezado nuevas ("NUMERO RADICADO", "DESCRIPCION GLOSA AUDITOR").
  Además se arregló una falla ajena al bot: 3 pruebas del sistema usaban
  fechas fijas de abril y "explotaban" al pasar 90 días — ya usan fechas
  relativas. **Todo el CI del PR #167 quedó en verde.**
- **22 jul** — Se creó esta bitácora como memoria común de los chats, y el
  archivo CLAUDE.md que ordena leerla al inicio y actualizarla al final de
  cada sesión.

---

## PENDIENTE

1. **SAVIA SALUD — el motivo del último bot.** Falta el archivo real de
   objeciones de SAVIA SALUD (el que se adjuntó llegó vacío, solo
   encabezados). Cuando llegue, correr el bot para armar su consolidado /
   cargue.
2. **Validar el cargue OBJECIONES contra el ERP.** Tres campos del formato
   del ERP no vienen en el consolidado y hoy se llenan por parámetro:
   tipo de objeción, centro de costos y usuario (por defecto "CARTERA").
   Falta cotejarlos contra un cargue que el ERP ya haya aceptado, y ajustar
   los valores por defecto si difieren.
3. **PR #167 en borrador.** El bot de objeciones VCO está terminado y con
   CI en verde, pero el PR sigue como borrador: falta revisarlo, marcarlo
   listo y hacer el merge a la rama principal (`motor-glosas`).
4. **Lote V2 Dispensario (12 notas crédito, $8,7 millones).** El diagnóstico
   y el escalamiento están hechos; la pelota está en otras áreas: 9 facturas
   dependen de SISTEMAS (servicio de validación de RIPS caído / CUV
   rechazado), 2 requieren descargar el PDF del DIAN y 1 confirmación de
   Facturación (NE histórico 302111). Hacer seguimiento y, cuando SISTEMAS
   resuelva, re-validar y radicar con los scripts ya listos.
5. **Tablero de calidad — caso hemofilia.** De los 4 casos difíciles de
   referencia, tres están en 10/10 y el de hemofilia con sanción quedó en 6
   (escala a Claude). Falta subirlo a ≥7 para cumplir la regla del proyecto
   ("la IA es buena solo si los 4 casos sacan ≥7").
6. **Mejora #3 (campos estructurados) apagada.** Está programada y probada
   pero con el interruptor apagado por defecto. Falta activarla en la
   máquina del HUS siguiendo su guía (docs/RUNBOOK_CAMPOS_ESTRUCTURADOS.md)
   y verificar con casos reales.
7. **Bot de Dinámica Gerencial (DGH) en piloto.** El bot que carga
   respuestas directamente en el sistema del hospital sigue en fase de
   piloto/calibración; falta estabilizarlo para uso diario.

## PARA MAÑANA

1. Conseguir con cartera/el ERP el **archivo real de objeciones de SAVIA
   SALUD** (con datos, no solo encabezados) y correrlo por el bot
   `tools/organizar_objeciones_vco.py`.
2. Con un cargue previo aceptado por el ERP a la vista, **confirmar los tres
   campos pendientes** del formato (tipo de objeción, centro de costos,
   usuario) y ajustar el bot si hace falta.
3. **Sacar el PR #167 de borrador y mergearlo** para que el bot quede en la
   rama principal y disponible en la máquina del HUS (que se auto-actualiza
   desde Git).
4. Preguntar a SISTEMAS por el avance de las **9 notas crédito del Lote V2**
   que dependen de ellos y re-validar las que destraben.

---

## Cómo mantener esta bitácora (regla para cada sesión)

1. **Al empezar:** leer esta bitácora completa antes de tocar nada.
2. **Al terminar:** agregar la fecha del día en "LO YA HECHO" con lo que se
   hizo (en lenguaje claro), actualizar "PENDIENTE" (quitar lo resuelto,
   agregar lo nuevo) y reescribir "PARA MAÑANA" con los próximos pasos.
3. Escribir siempre pensando en que **otro chat u otra persona** pueda
   retomar el trabajo sin más contexto que este archivo.
