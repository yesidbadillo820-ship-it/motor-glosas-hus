# BITÁCORA DEL PROYECTO — Glosas y Cartera ESE HUS

> **Qué es este archivo:** la memoria común de todo el trabajo hecho en este
> proyecto. Cualquier sesión de Claude Code debe **leerlo al empezar** (para
> saber en qué vamos) y **actualizarlo al terminar** (qué se hizo hoy, qué
> quedó pendiente y qué sigue mañana, con la fecha).
>
> Está escrito en lenguaje claro, pensado para auditoría — no hace falta ser
> programador para entenderlo.

---

## ¿De qué se trata este proyecto?

Es el conjunto de herramientas que apoya la **gestión de glosas y cartera del
Hospital Universitario de Santander (ESE HUS)**, operado por SINAC SC. Tiene
tres frentes:

1. **El Motor de Glosas**: una página web interna donde el equipo pega la glosa
   que envía la EPS y el sistema redacta la respuesta de defensa del hospital
   (con inteligencia artificial + banco de argumentos jurídicos y tarifarios).
2. **Los bots de portales**: programas que hacen solos el trabajo repetitivo en
   los portales de cada entidad (COOSALUD, SIMED/Dispensario, Dinámica
   Gerencial, SAVIA SALUD): responder glosas, cargar soportes, dejar evidencia.
3. **Herramientas de apoyo**: organización de notas crédito, consolidación de
   evidencias en Word/PDF, tablero de radicación y cartera, verificación de CUV.

---

## LO YA HECHO (resumen por fecha)

### Junio de 2026

**12–16 de junio — Arranque de las rondas de calidad del Motor de Glosas**
- Se detectaron y corrigieron decenas de errores en las respuestas que
  generaba el sistema (rondas 2 a 7): respuestas incompletas, datos inventados,
  contratos que no correspondían, fechas mal leídas.
- Se cargó el catálogo real de **15 contratos** del hospital con sus EPS.
- Se creó el verificador de **CUV** de notas crédito (valida contra MinSalud) y
  la primera versión del **motor histórico** (sugiere respuestas basadas en lo
  que el hospital ya respondió antes en casos iguales).

**17 de junio — Mejor redacción y nuevas pantallas**
- El sistema empezó a usar el **banco de respuestas reales del HUS** como
  ejemplos para redactar mejor (ronda 8) y a detectar solo la EPS del texto pegado.
- Se arreglaron paneles rotos (notas crédito, consulta de normativa), se creó el
  **acta de conciliación SINAC** multi-glosa y la barra unificada de reportes.
- Se preparó la migración de la base de datos a un esquema más simple y barato.

**18–19 de junio — Estabilidad**
- Corrección de errores críticos de arranque y de los modelos de IA
  disponibles; el sistema dejó de copiar ejemplos prohibidos en las respuestas
  (ronda 11).

**22–23 de junio — Bots de COOSALUD y SIMED + servidor propio**
- El **bot de COOSALUD** (responde glosas masivamente en su portal) aprendió a:
  encontrar los PDF de soporte aunque estén en carpetas hermanas, responder
  también pertinencia cuando viene tipificada, y cerrar glosas residuales.
- El **bot de SIMED (Dispensario)** quedó operativo para cargar soportes.
- La aplicación pasó de un servicio pagado a un **servidor propio con túnel
  seguro (costo $0/mes)**, con actualización automática desde el repositorio.
- Se escribieron guías de uso de ambos bots y contextos para nuevos chats.

**24–26 de junio — Radicador, calidad argumentativa y evidencias**
- Se creó el **radicador maestro multi-entidad** (clasifica los soportes de cada
  factura y arma el paquete de radicación con nombres oficiales).
- Rondas 13 a 18 de calidad: se eliminaron muletillas, valores inventados,
  citas normativas falsas y errores con medicamentos (CUM/INVIMA).
- Se creó la herramienta que junta los pantallazos de evidencia en un solo
  PDF, y el diagnóstico de las 12 facturas pendientes del Lote V2.

**30 de junio — El día grande (62 avances)**
- **Tablero de Radicación y Cartera** con alertas de mora +90 días, exportación
  a Excel y comparativos.
- **Homologador oficial CUPS→SOAT** para la defensa tarifaria.
- **Defensa concepto por concepto**: la respuesta ahora refuta cada punto de la
  glosa, sin dejar ninguno sin contestar.
- **Tablero de calificación 0–10**: mide en vivo la calidad de los dictámenes
  que produce el motor (la nota subió de 2.5 a ~9).
- Avanzó el **bot de Dinámica Gerencial (DGH)** para cargar respuestas
  directamente en el sistema del hospital.

### Julio de 2026

**1 de julio — Contratos reales completos**
- Ronda 23: el motor dejó de decir "sin contrato pactado" en falso — ahora lee
  las **cláusulas reales** de AURORA, COMPENSAR, COOSALUD, DISPENSARIO (FF.MM.),
  FAMISANAR, FOMAG, SUMIMEDICAL, SALUD MÍA, POSITIVA, PPL y POLICÍA.

**2–3 de julio — El motor deja de argumentar a ciegas**
- Fases 2 y 3: antes de redactar, el sistema **revisa los soportes reales** de
  la factura (Auditor Forense) y elige ejemplos por similitud del caso.
- Auditoría integral con 20 correcciones y un arreglo urgente de producción.

**7–10 de julio — Limpieza y cierre de pendientes**
- Ronda 29: limpieza general del código y 27 hallazgos corregidos.
- Bot COOSALUD: ya no exige soporte cuando la respuesta es "glosa extemporánea".
- Informe para gerencia del diagnóstico del Lote V2 (12 notas crédito).

**16–17 de julio — Bot de SAVIA SALUD (sesión actual)**
- Se creó el **bot que organiza las objeciones de SAVIA SALUD**
  (`tools/organizar_objeciones_savia.py`): toma el Excel que entrega SAVIA
  (8 columnas) y lo convierte al **formato de trabajo de 16 columnas** (hoja
  OBJECIONES), un archivo por factura o todo unificado.
- Reglas incorporadas y verificadas contra archivos reales (guía del
  Dispensario y EMSSANAR):
  - Factura en formato largo (HUS0000443697).
  - **CDCONSEC**: consecutivo por factura (la 1ª factura toda en 1, la 2ª en 2…).
  - **CROTIPOBJ** según los conceptos de la factura: solo administrativos
    (TA/FA/SO/AU) = 0, solo calidad (CL) = 1, mezclada = 2.
  - **CRDOBSERV** = código + texto + $valor (como los archivos reales).
  - Fechas en **fecha corta** (sin horas) y los 16 formatos de celda idénticos
    a los archivos reales.
- Se procesó el archivo real `SAVIA_SALUD_8.03` (2 facturas, 161 objeciones,
  $4.177.858 glosados) y se entregaron los Excel organizados.
- Todo quedó guardado en el repositorio con 36 pruebas automáticas en verde
  (Pull Request #164, verificación automática aprobada).

---

## PENDIENTE

1. **Códigos CRNCONOBJ de SAVIA**: el bot completa el código de 4 a 6 dígitos
   con "01" (TA08 → TA0801). Falta que la auditora confirme si algún concepto
   de SAVIA lleva otro subíndice (en EMSSANAR se ven FA0205, SO0603, etc.).
   Si hay lista oficial, se fija en el bot con `--mapa-codigos`.
2. **Aprobar y fusionar el Pull Request #164** (el bot de SAVIA) a la rama
   principal `motor-glosas`.
3. **Instalar el bot en el computador de cartera** (quedó la guía y el
   archivo; la corrida local aún no se ha logrado en ese equipo — mientras
   tanto, los Excel se convierten aquí en el chat).
4. Del diagnóstico del Lote V2: 12 notas crédito documentadas en el informe a
   gerencia — seguimiento a su radicación.

## PARA MAÑANA

1. Confirmar con la auditora la tabla de equivalencias de códigos de SAVIA
   (CRNCONOBJ) y dejarla fija en el bot.
2. Probar el archivo unificado de SAVIA en el proceso real de cargue y anotar
   cualquier ajuste que pida el sistema receptor.
3. Si llega un nuevo Excel de SAVIA, convertirlo con el bot (o aquí en el chat)
   y archivar los resultados por factura.
4. Fusionar el Pull Request #164 si la revisión está conforme.

---

*Última actualización: 17 de julio de 2026 — sesión del bot de SAVIA SALUD.*
