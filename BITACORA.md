# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana).

**Última actualización:** 22-07-2026

---

## 1) Las tres patas del proyecto

1. **Motor de Glosas (aplicación web con IA):** recibe las glosas y redacta el
   dictamen de defensa del hospital (cita contrato, tarifas, normativa). Vive en
   la carpeta `app/` y se usa desde el navegador.
2. **Bots de carga (robots que suben respuestas a las plataformas):**
   - `tools/responder_glosas_coosalud.py` — portal de COOSALUD (vco.ctamedicas.com).
   - `tools/responder_glosas_simed.py` y `tools/cargar_soportes_simed.py` — SIMED (Dispensario Médico).
   - `tools/responder_glosas_dgh.py` — Dinámica Gerencial (programa de escritorio del hospital).
   - Otros: Mutual Ser, FOMAG, radicador de facturación.
3. **Herramientas de apoyo:** armar el Word/PDF de evidencias
   (`tools/evidencias_a_word.py`, `evidencias_a_pdf.py`), notas crédito del
   Dispensario (renombrar, organizar, verificar CUV), tablero de cartera
   (`tools/tablero_cartera.py`).

Guías por plataforma en `docs/`: `CONTEXTO_COOSALUD.md`,
`CONTEXTO_DISPENSARIO_GLOSAS.md`, `CONTEXTO_DISPENSARIO_NOTAS.md`.

---

## 2) Resumen de lo ya hecho (por fecha)

### Abril 2026 — Nace el Motor de Glosas
- **08 al 10-04:** primera versión de la aplicación: análisis de glosas con IA,
  dictámenes con normativa colombiana (Res. 3047/2008, Ley 1438/2011, etc.),
  importación masiva desde Excel, exportación a Excel, seguridad de acceso.

### Junio 2026 — Nacen los robots de carga
- **11-06:** primera versión del **bot de COOSALUD**: entra al portal, busca cada
  factura, responde las glosas en grupo y captura el pantallazo de cierre como
  evidencia. Ese mismo día nace `evidencias_a_word.py` (une los pantallazos en
  un Word, una factura por página).
- **12 al 19-06:** herramientas de **notas crédito del Dispensario**: renombrar
  y organizar PDFs por carpeta, consolidar, verificar el estado del CUV ante
  MinSalud. Auditoría rápida de pendientes COOSALUD (`verificar_glosas_coosalud.py`).
- **22-06:** mejoras grandes del bot COOSALUD: responder también la pertinencia
  médica (`--incluir-calidad`), cerrar glosas residuales que el Excel no traía
  (`--cerrar-residuales`), buscar el PDF de soporte en carpetas alternativas del
  share. Guías escritas de los bots. Bot SIMED: manejo de ventanas emergentes.
- **23 y 24-06:** **cargue DIA 3 JUNIO (COOSALUD):** se cerraron las 118 facturas
  pendientes de la hoja BASE y las 26 de la hoja CALIDAD (4.936 glosas). Dos
  facturas fallaron por un detalle del portal al elegir el código de respuesta;
  se corrigió el bot y cerraron en la segunda pasada.
- **25 y 26-06:** Word de evidencias del **lote 69** (46 de 69 facturas tenían
  pantallazo; 23 quedaron identificadas sin evidencia). Nace `evidencias_a_pdf.py`.
  Diagnóstico de las 12 facturas pendientes del Lote V2 del Dispensario.
- **30-06:** arranca el **bot de Dinámica Gerencial (DGH)** (muchas iteraciones
  para dominar el programa de escritorio). **Tablero de Radicación y Cartera**
  (informe HTML con alertas de mora +90 días, exportar a Excel). Mejoras al
  motor IA (rondas 19-22) y set de evaluación de calidad de los dictámenes.

### Julio 2026 — Contratos reales, lotes masivos y cierre de pendientes
- **01 al 03-07:** el motor IA aprende los **contratos reales por EPS**
  (COOSALUD SOAT −15%, FOMAG, Dispensario FF.MM., Famisanar, Aurora, Compensar,
  etc.) — fin del falso "sin contrato pactado". Rondas 23-28 de mejoras.
- **07 y 08-07:** ronda 29 de limpieza y corrección (27 hallazgos de auditoría).
- **10-07:** **cargue DIA 3 JULIO (COOSALUD): 100 de 100 facturas cerradas
  (2.436 glosas)** — incluida una recuperación automática tras un corte de luz
  a mitad del cargue, sin duplicar nada. Se corrigió el bot para que las glosas
  extemporáneas (código RE9502) no exijan soporte PDF (5 facturas que estaban
  trabadas cerraron de una). Se definió la estructura de carpetas por
  mes/día para archivar evidencias y Word. **Informe de efectividad para
  gerencia** (página web con el antes/después).
- **10 al 21-07 (corridas del auditor):** se analizaron y lanzaron los
  **LOTES 02 (300 fact.), 06 (300), 07 (300) y 08 (75)** de COOSALUD.
  El LOTE 7 llegó primero como listado de objeciones sin respuestas
  (OBJECIONES.xlsx) y fue reemplazado por el consolidado correcto.
  En los lotes 06/07/08 quedaron 37 facturas con la pertinencia médica
  sin responder (el médico aún no la tipificaba).
- **17-07:** informe técnico en Word de los **rechazos CUV de 4 facturas
  conciliadas** (para enviar al área).
- **22-07 (hoy):** llegaron las respuestas de pertinencia en 3 archivos
  ("PERTINENCIA (1)", "ok" y "15"). Se detectó que **cada archivo estaba
  incompleto pero se complementaban** entre sí → se fusionaron en
  **CONSOLIDADO_PERTINENCIA_6JULIO_FUSIONADO.xlsx** (37 facturas, 5.736
  glosas, cero sin respuesta, todas RE9901). Quedó listo el comando para
  correrlo. Se creó esta bitácora.

---

## 3) PENDIENTE

1. **Correr el consolidado fusionado de pertinencia** (37 facturas / 5.736
   glosas) con `--hoja CALIDAD --incluir-calidad`. Con eso los LOTES 06, 07 y
   08 quedan cerrados al 100%. El archivo está en Downloads como
   `CONSOLIDADO_PERTINENCIA_6JULIO_FUSIONADO.xlsx`.
2. **Confirmar los resultados de los LOTES 02, 06, 07 y 08:** revisar los
   reportes CSV en `D:\USUARIO CARTERA\Documents\COOSALUD\` (cuántas OK,
   cuántas PENDIENTE_PDX o pendientes) y hacer segunda pasada donde falte.
3. **Words de evidencia de los lotes recientes** (02, 06, 07, 08 y pertinencia),
   cada uno en su carpeta `MES AÑO\DD-MM-AAAA\` con subcarpeta SOPORTES.
4. **Lote 69 — 23 facturas sin pantallazo** (4 nunca estuvieron en bolsa, resto
   por revisar): decidir si se reprocesan o se documentan como están.
5. **HUS504096:** factura mencionada en un cruce de junio que no aparece en
   ningún consolidado. Verificar de qué lote es o si el número está mal escrito.
6. **Informe de gerencia:** falta el dato real del "antes" (cuánto tardaba el
   proceso manual y cuántas personas) para poner el multiplicador exacto.
7. **Rechazos CUV:** hacer seguimiento a la respuesta del área sobre las 4
   facturas conciliadas (informe enviado el 17-07).

## 4) PARA MAÑANA

1. Correr la **pertinencia fusionada** (punto 1 de pendientes) y verificar que
   las 37 facturas cierren con evidencia.
2. Con los reportes en mano, **cerrar los flecos de los lotes 02/06/07/08**
   (segunda pasada de las que queden pendientes).
3. Generar los **Words de evidencia** de todo lo cerrado y archivarlos en sus
   carpetas por mes/día.
4. Actualizar el **informe de gerencia** con el acumulado real de julio
   (facturas y glosas cerradas por lote).

---

## 5) Datos fijos que siempre se necesitan

- **Carpeta de trabajo en Windows:** `C:\temp-notas` (ahí vive el repo).
- **Rama de trabajo:** `claude/excel-reconciliation-data-9Bnpj`. Antes de correr
  nada: `cd C:\temp-notas` y `git pull`.
- **Credenciales:** siempre en variables de entorno (`COOSALUD_USER`,
  `COOSALUD_PASSWORD`). Nunca escritas en archivos ni en comandos.
- **Índice de soportes:** `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt`.
- **Reportes y evidencias:** `D:\USUARIO CARTERA\Documents\COOSALUD\`.
- **Regla de reanudación:** si un cargue se corta (luz, portal caído), NO se
  pierde nada: se relanza con `--saltar-csv <reporte anterior>` y un nombre de
  reporte nuevo. El bot salta lo ya cerrado y no duplica respuestas.
- **Regla de soportes:** las glosas extemporáneas (RE9502) NO llevan PDF de
  soporte. Las demás (ej. RE9901 en glosas de soportes) sí, y salen del share
  vía el índice.
