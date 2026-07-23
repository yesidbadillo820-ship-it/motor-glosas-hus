# BITÁCORA DE TRABAJO — Motor Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code
> sobre este repositorio. Aquí queda lo ya hecho, lo pendiente y lo que sigue.
> **Toda sesión de Claude debe leerlo al empezar y actualizarlo al terminar**
> (ver CLAUDE.md). Escrito para un auditor, sin tecnicismos.

_Última actualización: 22 de julio de 2026 (tarde)._

---

## LO YA HECHO (por fecha)

### 16–19 de junio de 2026 — Nace el Motor de Glosas
- Se construyó la plataforma web **Motor Glosas HUS**: recibe las glosas de
  las EPS y redacta la respuesta técnico-jurídica usando inteligencia
  artificial, con el marco normativo colombiano.
- Se cargaron los contratos reales del hospital y un banco de respuestas
  históricas para que la IA aprenda del estilo propio del HUS.
- Se hicieron varias rondas de ajuste de calidad (evaluando dictámenes
  reales y corrigiendo errores uno a uno).
- Primer piloto de automatización del portal DG.NET (ingreso automático).

### 22–26 de junio de 2026 — Bots de portales y despliegue propio
- **Bots que responden glosas directamente en los portales** de COOSALUD y
  SIMED (suben soportes, cierran facturas, dejan pantallazo de evidencia).
- Radicador maestro multi-entidad: clasifica los soportes de cada factura y
  arma la radicación según lo que exige cada pagador.
- La plataforma quedó instalada en una máquina del propio HUS (costo $0/mes).
- Diagnóstico del Lote V2 del Dispensario (facturas con CUV inválido) y más
  rondas de calidad sobre dictámenes reales.

### 30 de junio – 3 de julio de 2026 — Calidad medible y contratos reales
- **Tablero de calificación 0–10** que mide en vivo la calidad de los
  dictámenes que produce el motor (pasó de ~2.5 a ~9 en el tablero).
- Se cargaron las **cláusulas tarifarias reales** de los pagadores:
  COOSALUD (SOAT −15%), FOMAG, AURORA, COMPENSAR, FAMISANAR, Dispensario
  FF.MM., SUMIMEDICAL, POSITIVA, PPL, Policía, entre otros.
- La IA dejó de "argumentar a ciegas": ahora revisa los soportes de la
  factura antes de redactar (Auditor Forense conectado al dictamen).
- Se atendió y corrigió una caída de la plataforma en producción.

### 7–15 de julio de 2026 — Mantenimiento y endurecimiento
- Tres rondas grandes de revisión: seguridad, exactitud de tarifas y
  cartera, exportes a Excel más seguros y limpieza general.
- Informes para gerencia del diagnóstico del Lote V2 (12 notas crédito).
- Ajuste COOSALUD: no exigir soporte cuando la respuesta es extemporánea.

### 17 de julio de 2026 — Arranca el módulo ADRES (FURIPS)
- **Bot validador FURIPS** (`tools/adres/`): valida de forma masiva los
  archivos FURIPS 1 y 2 contra la **Circular 022 de 2023 de la ADRES**
  (los 102 campos del FURIPS 1 y los 9 del FURIPS 2) y **cruza cada factura
  contra sus soportes**: RIPS, CUV, factura electrónica DIAN, factura PDF y
  epicrisis. Entrega un **informe Excel de 7 hojas** con semáforo.
- Con la muestra real detectó de una vez errores verdaderos: egreso anterior
  al ingreso, paciente con TI siendo mayor de edad, dispositivos médicos sin
  registro INVIMA, líneas repetidas sin agrupar.
- **Revisión de calidad automática** del bot (28 revisores independientes):
  22 correcciones confirmadas y aplicadas el mismo día.
- **Informe de baja de cartera** (Resolución 577 de 2019): bot que lee el
  PDF unido de cada factura, extrae el valor y el informe de trabajo social,
  y arma el documento **Word** para presentar + **Excel** de relación.
- Bots de apoyo de doble clic: UNIR_PDFS y PDF_A_CMD.
- Arreglo clave: los soportes del servidor de cartera están **todos juntos
  en una carpeta** (no en carpeta por factura); el validador aprendió a
  asociarlos por el número de factura del nombre de cada archivo.
- App de lotes con agente local (subir Excel de glosas y repartir tareas).

### 21 de julio de 2026 — Afinación con datos reales + App web
- **Direcciones (campos 15, 50 y 60):** el validador ahora marca ERROR si la
  dirección es solo un código (68780) o solo un municipio (SURATA) — debe ir
  la nomenclatura completa (CALLE 51 # 15-20, MANZANA X CASA Y). En la
  muestra real encontró 33 direcciones inválidas.
- **PDFs escaneados:** ya no generan errores falsos; quedan marcados
  "SIN TEXTO" con sugerencia de OCR. Y si la factura PDF es la
  "Representación Gráfica DIAN" (que no trae datos del paciente), esos
  cruces se hacen contra la epicrisis.
- El informe de baja también funciona con la carpeta plana de soportes y
  muestra el avance mientras lee (antes parecía congelado).
- **APP WEB "Validador ADRES"** (`validador-adres/`): subir los TXT y un ZIP
  de soportes desde el navegador, ver el avance en vivo, tablero con
  gráficas interactivas, tabla con semáforo, vista de hallazgos filtrable,
  detalle por factura, modo claro/oscuro y descarga del Excel. Corre en el
  PC del auditor o en un servidor del hospital; los datos no salen de la red.
- Nuevo bot **PDF_A_CMD_EN_CARPETA**: convierte todos los PDF a .cmd y deja
  las copias juntas dentro de una carpeta nueva `CMD_CONVERTIDOS`.
- Se corrigió un defecto de formato que hacía que algunos bots de doble clic
  se cerraran sin ejecutar nada en Windows (quedó blindado para el futuro).
- Corrida real sobre las 50 facturas ADRES del servidor: 27 con errores,
  18 para revisar, 5 cumplen; a HUS410606 y HUS472103 les faltan RIPS y CUV.

### 22 de julio de 2026 — Memoria común + informe XML NUEVA EPS
- Se creó esta **BITÁCORA** y la instrucción (CLAUDE.md) para que todos los
  chats de Claude la lean al empezar y la actualicen al terminar.
- **Bot del informe de revisión XML (devoluciones DE4401 de NUEVA EPS)**
  (`tools/completar_informe_xml_dian.py` + `COMPLETAR_INFORME_XML.cmd`):
  toma el Excel del informe (411 facturas devueltas), busca el XML DIAN de
  cada factura en el repositorio de facturación, y completa VALOR (XML),
  NUMERO_CONTRATO, COBERTURA_PLAN_BENEFICIOS, VALIDACIÓN DIAN (CUFE, firma,
  acuse), la CONCLUSIÓN (si la devolución procede o no, con norma) y la
  RESPUESTA para el portal DGH — con semáforo y hoja RESUMEN.

---

## DÓNDE ESTÁ CADA COSA (mapa rápido)

| Qué | Dónde |
|---|---|
| Plataforma Motor Glosas (respuestas a glosas con IA) | `app/` + `static/` |
| Bot validador FURIPS + informe Excel | `tools/adres/validar_furips.py` + `VALIDAR_FURIPS.cmd` |
| App web Validador ADRES (navegador) | `validador-adres/` (`VALIDADOR_ADRES_WEB.cmd`) |
| Informe de baja de cartera (Word + Excel) | `tools/generar_informe_baja_cartera.py` + `INFORME_BAJA_CARTERA.cmd` |
| Bots de PDF (unir / convertir a .cmd / a carpeta) | `tools/UNIR_PDFS.cmd`, `tools/PDF_A_CMD.cmd`, `tools/PDF_A_CMD_EN_CARPETA.cmd` |
| Bots de portales (COOSALUD, SIMED, DGH) | `tools/responder_glosas_*.py` |
| Guías de uso de cada herramienta | los `README_*.md` dentro de `tools/` |

---

## PENDIENTE

1. **Fusionar el PR #176** en GitHub: contiene TODO el trabajo del 21 de
   julio (direcciones, PDFs escaneados/DIAN, app web, bot de carpeta,
   arreglos de formato). Mientras no se fusione, la rama principal no lo
   tiene.
2. **Confirmar** que el bot `PDF_A_CMD_EN_CARPETA.cmd` corregido ya genera
   la carpeta `CMD_CONVERTIDOS` en el servidor (el usuario reportó que la
   primera versión no generaba nada; se corrigió el formato y se reenvió).
3. **Corregir los datos de las 50 facturas ADRES** que el validador marcó:
   27 facturas con errores (sobre todo direcciones sin nomenclatura, y los
   hallazgos de la hoja HALLAZGOS del Excel) antes de radicar ante ADRES.
4. **Completar soportes faltantes**: a HUS410606 y HUS472103 les faltan el
   RIPS y el CUV.
5. **Facturas de baja**: completar el informe de trabajo social en las que
   el Word marcó "NOTA DE REVISIÓN" antes de presentar el documento.
6. Facturas con PDF escaneado: aplicarles OCR si se quiere el cruce
   automático completo (hoy quedan "SIN TEXTO" para revisión manual).
7. Mejoras futuras de la app web (cuando se pidan): usuarios y contraseñas,
   historial de validaciones guardadas, exportar hallazgos filtrados.

## PARA MAÑANA

1. Verificar en el servidor el bot de carpeta `CMD_CONVERTIDOS` (pendiente 2).
2. Fusionar el PR #176 y actualizar los archivos del servidor con el último
   paquete (ZIP de bots + app web).
3. Empezar la corrección de las facturas ADRES con errores usando el informe
   Excel / la app web, priorizando las de mayor valor.

---

> **Nota para Claude (cualquier sesión):** al terminar tu trabajo del día,
> agrega la fecha en "LO YA HECHO" con lo realizado, actualiza "PENDIENTE"
> (quita lo resuelto, agrega lo nuevo) y reescribe "PARA MAÑANA". Mantén el
> lenguaje simple, pensado para un auditor.
