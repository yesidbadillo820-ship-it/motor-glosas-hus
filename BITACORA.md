# BITÁCORA DEL PROYECTO — Motor de Glosas (Hospital Universitario de Santander)

Este archivo es la **memoria común** del trabajo. Sirve para que cualquier
persona —o cualquier sesión de trabajo asistido— sepa, sin tener que preguntar,
qué se ha hecho, qué falta y qué sigue.

> **Cómo se usa:** al comenzar una jornada se lee esta bitácora primero. Al
> terminar, se anota lo que se hizo ese día, lo que quedó pendiente y lo que
> sigue mañana, siempre con la fecha.

---

## En qué consiste el proyecto

El área de cartera del hospital maneja las **glosas** (objeciones que hacen las
EPS y aseguradoras a las facturas) y las **devoluciones**. El trabajo reciente
se ha concentrado en dos automatizaciones que le ahorran horas de trabajo manual
al equipo:

1. **Responder glosas en el sistema DGH** (Dinámica Gerencial Hospitalaria):
   una herramienta que carga automáticamente las respuestas a las glosas dentro
   del sistema, en vez de que una persona las digite una por una.
2. **Organizar los correos de glosas**: un asistente ("bot") que lee la bandeja
   de correo institucional, clasifica cada glosa, la archiva ordenadamente en el
   servidor y prepara el archivo de entrega para los gestores.

Todo esto se apoya en el sistema principal del hospital (el "Motor de Glosas"),
que ya existía y que administra la información de las glosas.

---

## LO YA HECHO (por fecha)

### 24 al 26 de junio de 2026 — Herramientas de apoyo para radicación y soportes
- Se crearon utilidades para el sistema SIMED: cargar los soportes de las
  facturas y consolidar los pantallazos de evidencia en un solo archivo PDF.
- Se diagnosticaron 12 facturas que estaban pendientes y se encontró la causa:
  6 tenían un código de validación (CUV) inválido por una caída del servicio de
  validación. Se dejó organizada la carpeta con esas facturas para su gestión.

### 30 de junio al 2 de julio de 2026 — Automatización para responder glosas en DGH
- Se construyó la herramienta que **carga las respuestas a las glosas
  directamente en el sistema Dinámica Gerencial Hospitalaria**, leyendo la
  pantalla y llenando los campos automáticamente.
- Requirió muchos ajustes para que funcionara bien con la interfaz del sistema
  (encontrar la factura correcta, abrir el formulario de respuesta, llenarlo y
  guardarlo de forma confiable). Quedó funcionando como piloto.

### 6 de julio de 2026 — Nace el bot que organiza los correos de glosas
- Se construyó el **bot organizador**: lee la bandeja del correo institucional,
  clasifica cada correo (glosa inicial, ratificada, devolución o conciliación),
  identifica de qué entidad viene, imprime el correo a PDF, guarda los adjuntos y
  lo archiva en el servidor por año, mes, día y entidad.
- Se construyó el **extractor**, que arma el Excel de entrega para los gestores
  con el responsable asignado y las fechas de vencimiento.
- Se creó un **instalador de un clic** para ponerlo en el equipo de cartera.
- Se hizo una **revisión de seguridad** del sistema y se corrigieron 34 puntos
  para que sea robusto (por ejemplo, que no se cuelgue si se cae la red y que
  nunca borre ni dañe correos).

### 7 de julio de 2026 — Modo de pruebas y mejoras al instalador
- Se agregó la opción de archivar primero en una **carpeta local de pruebas**,
  antes de tocar el servidor real, para validar con tranquilidad.
- Se mejoró el instalador para que avise con claridad si se ejecuta sin haber
  descomprimido el paquete.
- Segunda revisión del sistema: 12 correcciones adicionales.

### 8 de julio de 2026 — Afinación con los datos reales del hospital
- Con el registro real de **904 correos**, se afinaron las reglas: la revisión
  manual bajó del **72% al 8%** de los correos (89% menos trabajo manual).
- Se agregaron entidades que faltaban (Sura, HDI, Colmena, ADRES, Aseguradora
  Solidaria y otras); ya se reconocen más de 30 entidades.
- Se eliminaron las carpetas "basura" con nombres raros: ahora lo que no se
  reconoce va a **una sola carpeta "Sin identificar"** para revisión.
- A pedido del área, el bot pasó a **leer el contenido del correo** para decidir
  por sí mismo si es glosa o devolución, en lugar de mandarlo a revisión.

### 22 de julio de 2026 — Documentación y control central
- Se prepararon dos informes: uno para **gerencia** (comparación "antes vs
  ahora") y una **bitácora del proyecto**.
- Se creó **este archivo de control central** (BITACORA.md) como memoria común, y
  se dejó la instrucción de leerlo y actualizarlo en cada jornada.
- Se dejaron **en verde las pruebas automáticas** del proyecto: dos pruebas del
  sistema principal fallaban por usar fechas fijas de abril que quedaron fuera de
  la ventana de 90 días; se corrigieron para que usen fechas recientes. No se
  tocó el funcionamiento del sistema, solo las pruebas.

---

## PENDIENTE (lo que falta por hacer)

- **Rotar la contraseña del correo:** durante las pruebas, la contraseña de
  aplicación de la cuenta quedó visible en el canal de trabajo. Debe crearse una
  nueva, actualizarla en el equipo y eliminar la anterior.
- **Afinar las últimas entidades:** revisar qué correos siguen cayendo en la
  carpeta "Sin identificar" y crear su regla para que se archiven solos.
- **Validar un día completo:** comparar lo que archiva el bot en un día contra
  lo que se hacía a mano, para confirmar que quedó idéntico.
- **Paso a producción:** cuando las pruebas estén conformes, apuntar el bot al
  servidor de glosas definitivo (la unidad Z:).
- **Integrar el trabajo al sistema principal:** el desarrollo está en una rama
  aparte, lista para incorporarse al sistema oficial cuando se apruebe.

---

## PARA MAÑANA (lo próximo a trabajar)

- Instalar la última versión del bot en la carpeta de pruebas y **dejarlo correr
  unas horas**, luego revisar cómo quedó el archivo.
- Abrir el **registro en Excel** que genera el bot y revisar la carpeta "Sin
  identificar"; pasar esa lista para agregar las entidades que falten.
- Preparar el **cambio a producción**: verificar que el equipo tenga acceso al
  servidor Z: y planear el día del paso.

---

*Última actualización: 22 de julio de 2026.*
