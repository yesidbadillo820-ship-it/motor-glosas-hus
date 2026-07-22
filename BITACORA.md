# BITÁCORA DEL PROYECTO — Motor de Glosas HUS

**Qué es este proyecto:** el conjunto de herramientas que apoya a Cuentas Médicas /
Cartera del Hospital Universitario de Santander (ESE HUS) para gestionar las glosas
y objeciones de las EPS: un sistema web con inteligencia artificial que redacta las
respuestas (dictámenes), y una serie de "bots" (programas automáticos) que hacen el
trabajo repetitivo en los portales de cada entidad (COOSALUD, SIMED, Dinámica
Gerencial, EMSSANAR, etc.).

**Cómo usar este archivo:** es la memoria común de todos los chats de Claude Code.
Al iniciar una sesión de trabajo se lee primero; al terminar, se anota lo hecho,
lo pendiente y lo que sigue, con la fecha.

**Última actualización:** 22 de julio de 2026.

---

## RESUMEN DE LO YA HECHO (por fecha)

### 12 de junio de 2026
- Primeros ajustes registrados del motor de respuestas (correcciones de la
  "ronda 2" de revisión de calidad) y relanzamiento del servicio en la nube.

### 16 de junio de 2026
- Cuatro rondas de corrección de calidad de los dictámenes (rondas 3 a 7), a
  partir de evaluaciones con casos reales: se corrigieron respuestas con textos
  incompletos, datos inventados y contratos que no correspondían.
- Se cargaron al sistema **15 contratos reales** del hospital con sus EPS.
- Herramienta nueva para **verificar el estado del CUV** (validación del
  Ministerio de Salud) de las notas crédito.
- Herramienta nueva que sugiere respuestas de glosas a partir del **histórico**
  de respuestas del hospital.

### 17 de junio de 2026
- El banco de respuestas históricas del HUS se conectó como ejemplos para la IA
  (mejora la calidad y la coherencia de los dictámenes).
- Rondas 8 a 10 de corrección tras corridas con glosas reales del 17 de junio.
- El sistema ahora **detecta automáticamente la EPS** desde el texto pegado.
- Panel de **notas crédito** y **acta de conciliación SINAC** en la página web.
- La base de datos se migró a un esquema más simple y económico, con copias de
  seguridad automáticas.
- Primer piloto de **ingreso automático a Dinámica Gerencial** (el sistema de
  cartera del hospital) para preparar el cargue automático de respuestas.

### 18–19 de junio de 2026
- Ajustes de configuración y ronda 11 de calidad.
- Corrección de errores críticos de estabilidad del servidor (memoria, límites
  de acceso, proveedores de IA que ya no se usan).

### 22 de junio de 2026
- El sistema quedó **instalado en una máquina del propio hospital** con un túnel
  seguro de acceso (costo mensual $0, antes se pagaba nube externa).
- Mejoras al **bot de COOSALUD** (responde glosas en el portal de esa EPS):
  ahora puede usar soportes alternativos cuando falta el principal, cerrar
  glosas del portal que no están en el Excel y responder también las de
  pertinencia médica cuando la planilla trae la respuesta.
- Guías escritas de los bots de COOSALUD y SIMED para quien los opere.

### 23 de junio de 2026
- Ronda 12: tres errores críticos del dictamen corregidos.
- El servidor del hospital ahora **se actualiza solo** cuando hay versión nueva.
- Corrección en la recepción de planillas de la entidad DMBUG (se descartaban
  conceptos por una columna vacía).
- Documentos de contexto separados por entidad (COOSALUD, Dispensario) para que
  cualquier chat nuevo entienda el trabajo sin volver a explicar todo.

### 24 de junio de 2026
- Ronda 13: mejoras de calidad argumentativa (evitar frases repetidas y valores
  inventados en los dictámenes).
- **Radicador maestro multi-entidad**: herramienta que clasifica los soportes de
  cada factura y arma el paquete de radicación completo.
- El bot de SIMED ahora guarda un **pantallazo de evidencia** por cada factura
  cargada.

### 25 de junio de 2026
- Rondas 14 y 15 tras pruebas en producción (códigos de medicamentos, citas de
  normas inventadas, instrucciones del usuario que no se respetaban).
- **Diagnóstico de las 12 facturas pendientes del Lote V2 del Dispensario**:
  se encontró que 6 facturas tenían el CUV inválido por una falla del validador
  local; quedó documentado con el detalle por factura.

### 26 de junio de 2026
- Rondas 16 a 18: errores detectados en auditoría humana de dictámenes reales;
  los casos complejos ahora **escalan automáticamente a un modelo de IA superior**.
- Herramienta para consolidar los pantallazos de evidencia en un solo PDF.

### 30 de junio de 2026
- **Tablero de calidad de dictámenes** (califica de 0 a 10 cada respuesta) con
  medición en vivo del motor real; la calidad pasó de ~2.5 a ~9 sobre 10 en los
  casos de referencia.
- **Bot de Dinámica Gerencial (DGH)** primera versión: carga las respuestas de
  glosas directamente en el sistema de cartera del hospital (muchas iteraciones
  para dominar las pantallas del programa).
- **Tablero de Radicación y Cartera** para Cuentas Médicas, con alertas de mora
  a más de 90 días, exportación a Excel y comparativos.
- Homologador oficial de códigos CUPS → tarifa SOAT para la defensa tarifaria.
- Refutación obligatoria **concepto por concepto** de cada glosa y banco de
  evidencia científica para tecnología costosa.

### 1 de julio de 2026
- **Contratos con cláusulas literales de 11 pagadores reales** cargadas al
  sistema (AURORA, COMPENSAR, COOSALUD, FOMAG, FAMISANAR, POSITIVA, PPL,
  POLICÍA, SALUD MÍA, SUMIMEDICAL, DISPENSARIO): se acabó el falso
  "sin contrato pactado" en los dictámenes, con tarifas verificadas contra los
  Excel de los contratos.

### 2 de julio de 2026
- La IA por fin **lee la historia clínica adjunta completa** (antes solo veía un
  fragmento) y los casos complejos envían los PDF originales al modelo superior.
- **Auditor forense** conectado: antes de redactar, se hace un mapa de folios de
  los soportes (qué hay, en qué folio, qué falta) y se prohíbe inventar evidencia.
- Los ejemplos que ve la IA ahora se eligen por **similitud con la glosa** (se
  buscan los precedentes ganados más parecidos).

### 3 de julio de 2026
- Auditoría integral del sistema: 20 correcciones seguras aplicadas (ronda 28).
- Arreglo urgente de una caída del servidor en producción por una variable de
  correo mal configurada.
- Seguridad: se retiró una clave de acceso real que estaba expuesta en un
  archivo de ejemplo.

### 7–8 de julio de 2026
- Ronda 29: 27 hallazgos corregidos y limpieza general de código en desuso.
- Se consolidó todo en la rama principal y se retiró el despliegue en la nube
  externa (ya todo corre en la máquina del hospital).

### 10 de julio de 2026
- Bot COOSALUD: las glosas extemporáneas (respuesta RE9502) ya no exigen
  adjuntar soporte clínico (no corresponde), y la lectura del Excel tolera
  nombres de hoja con espacios o mayúsculas distintas.
- **Informe para gerencia** del diagnóstico del Lote V2 (12 notas crédito).

### 15 de julio de 2026
- **Bot organizador de objeciones EMSSANAR** (nuevo): toma los PDF de objeción
  que radica EMSSANAR (los "Objeción a Factura N° HUS…") y arma automáticamente
  el Excel de cargue OBJECIONES para el sistema de cartera, con el mismo formato
  del lote que ya se usa con COOSALUD.
  - Probado con la factura real HUS0000515948: 37 filas que suman exactamente
    los $2.177.341 que dice el encabezado del PDF.
  - Detecta y fusiona la "doble glosa" (cuando la EPS objeta el mismo servicio
    dos veces, cuenta solo la mayor, igual que hace la EPS en su total).
  - Traduce los códigos de servicio al código interno del sistema de cartera
    (tabla de 145 equivalencias derivada del lote real ya cargado).
  - Con guía de uso (`tools/README_organizar_objeciones_emssanar.md`) y 23
    pruebas automáticas; pasó una verificación independiente fila por fila.
- Quedó en el **PR #162** (propuesta de cambio en revisión, en borrador).

### 22 de julio de 2026
- Verificación del PR #162: revisión automática en verde (las tres
  comprobaciones pasan), sin conflictos, listo para aprobar y unir.
- Se creó esta bitácora y la instrucción para que todos los chats la usen como
  memoria común.
- Se arreglaron 3 pruebas automáticas "bomba de tiempo" que no tenían que ver
  con el bot: usaban fechas fijas de abril y, al pasar los 90 días de la
  ventana de estadísticas, empezaron a fallar y bloqueaban la revisión
  automática de cualquier cambio. Ahora usan fechas relativas al día actual y
  no volverán a caducar.

---

## PENDIENTE

1. **Aprobar y unir el PR #162** (bot de objeciones EMSSANAR): está en borrador,
   con la revisión automática en verde y sin conflictos. Falta la decisión de
   pasarlo a definitivo y unirlo a la rama principal.
2. **Probar el cargue real del Excel de EMSSANAR** en el sistema de cartera
   (Dinámica Gerencial) con la factura HUS0000515948. Dos datos quedaron con
   supuestos razonables que solo el cargue real confirma:
   - los códigos de servicio con sufijo "H" (tabla de equivalencias), y
   - el campo "tipo de objeción" (0 = glosa, 2 = devolución).
   Si el sistema rechaza algún código, se agrega a la tabla y listo.
3. **Correr el bot EMSSANAR con el lote completo** de PDFs (hasta hoy solo se
   procesó una factura de muestra) y revisar que todas cuadren con su encabezado.
4. **Lote V2 del Dispensario**: según el informe entregado a gerencia el 10 de
   julio, había 12 notas crédito con problemas (6 por CUV inválido). Verificar
   si ya se re-radicaron o siguen pendientes.

## PARA MAÑANA

1. Sacar el PR #162 de borrador, aprobarlo y unirlo a la rama principal.
2. Reunir todos los PDF de objeciones de EMSSANAR del mes en una carpeta y
   correr el bot para generar el Excel del lote completo.
3. Hacer un cargue de prueba de ese Excel en el sistema de cartera y anotar en
   esta bitácora si aceptó todos los códigos (o cuáles corrigió).

---

*Recordatorio para los chats de Claude Code: al cerrar la sesión, actualizar las
tres secciones de arriba (lo hecho hoy con su fecha, lo pendiente y lo de mañana).*
