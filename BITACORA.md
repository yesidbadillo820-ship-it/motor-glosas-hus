# BITÁCORA DE TRABAJO — GESTIÓN DE GLOSAS ESE HUS

> **Memoria común de todos los chats de Claude Code.**
> Al iniciar cualquier sesión: leer este archivo primero.
> Al terminar: actualizarlo con lo hecho, lo pendiente y lo que sigue, con la fecha.

**Última actualización: 22/07/2026 (tarde — cierre del lote 1.600)**

---

## GLOSARIO RÁPIDO (para quien llega nuevo)

| Término | Qué es |
|---|---|
| **Glosa** | Objeción de la EPS a un cobro de la factura (no quiere pagar una parte) |
| **DGH** | Dinámica Gerencial Hospitalaria — el sistema contable del hospital; ahí se registran las objeciones y las respuestas de trámites |
| **Portal VCO** | Portal web de COOSALUD (vco.ctamedicas.com) donde se responden las glosas ante la EPS |
| **OBJECIONES** | Archivo Excel que se carga a DGH para registrar las glosas objetadas |
| **RE9502 / RE9901** | Códigos de respuesta: 9502 = glosa extemporánea (la EPS glosó tarde, art. 57 Ley 1438/2011) · 9901 = glosa a tiempo, se responde con el texto del área |
| **CALIDAD (CL)** | Glosas de pertinencia médica: las responden las doctoras de auditoría médica, no cartera |
| **Copago** | Cuota moderadora que paga el paciente; DGH no permite objetar esa parte |
| **SIMED / Dispensario** | Otra EPS y otro frente de trabajo (notas crédito), independiente de COOSALUD |

---

## LO YA HECHO (por fecha)

### Junio 2026 — Preparación y primeros bots

- **17/06** — Herramienta para conectarse automáticamente a Dinámica Gerencial (DG).
- **19/06** — Dispensario (SIDME): organización de notas crédito con nombre corto.
- **22/06** — Mejoras al bot que responde glosas en el portal COOSALUD: adjuntar soportes con respaldo (PDX→HAM→PDE), opción para incluir glosas de calidad, cierre de glosas residuales, evidencias en Word.
- **23/06** — Se separó la documentación por frentes: COOSALUD, Dispensario-notas y Dispensario-glosas (docs/CONTEXTO_*.md).
- **24/06** — SIMED: pantallazo de evidencia por cada factura cargada.
- **25/06** — Diagnóstico de 12 facturas pendientes del Lote V2 Dispensario: 6 tenían CUV inválido porque un servicio interno estaba caído.
- **26/06** — Herramienta para unir todas las evidencias en un solo PDF.
- **30/06 a 02/07** — Bot para responder glosas DENTRO de DGH (maneja las ventanas del programa): se construyó y se estabilizó tras muchas pruebas.

### Julio 2026 — Cargue masivo COOSALUD (el grueso del trabajo)

- **08/07** — Nacen los bots del masivo COOSALUD:
  - **Organizador**: toma el ZIP del portal (miles de Excel sueltos) y lo ordena en carpetas FACTURAS/DETALLES/GLOSAS por lotes de 300 (límite de DGH).
  - **Consolidador**: une todo, arma la observación final de cada glosa, cruza con la base de DGH y genera el archivo OBJECIONES listo para cargar.
  - **HACER TODO COOSALUD.bat**: los dos pasos con doble clic.
- **09/07** — Ajustes claves tras errores reales de DGH:
  - Cruce de códigos en 4 niveles + por nombre de medicamento (arregló el caso KETAMINA vs SALBUTAMOL).
  - Una glosa de CALIDAD (CL) manda sobre las administrativas en el archivo.
  - Un archivo OBJECIONES por cada lote de 300.
  - Bot **CORREGIR ERRORES DGH**: si DGH rechaza el cargue, arma el reintento completo (DGH no guarda nada cuando hay error).
- **10/07** — Aviso automático de facturas con copago (causa de errores de valor en DGH).
- **14/07** — Día grande:
  - **CONSOLIDADO RESPUESTAS GLOSAS**: por cada lote, el Excel con la respuesta de cada glosa (RE9502 si extemporánea / RE9901 con el texto del área). Las de CALIDAD quedan en blanco para las doctoras.
  - Bot **RESPUESTA TRÁMITES DGH**: llena el export de trámites de DGH con las 4 columnas de respuesta, en lotes de máximo 499 facturas, quitando las ya subidas.
  - **Operación**: se objetaron **2.170 facturas** en DGH (~$4.741 millones) y se subieron los 5 archivos de trámites (2.133 facturas; 37 quedaron para auditoría médica).
- **16/07** — **Operación**: lote de **41 facturas** objetado en DGH (8.801 ítems, ~$754 millones).
- **17/07** — Corrección definitiva del **copago** en el bot: ahora cada objeción se recorta automáticamente a (valor del servicio − copago), que es lo que DGH acepta. Se corrigió el archivo del lote 41 (factura HUS517650) y quedó cargado sin errores.
- **21/07** — **Operación** (chat):
  - Trámites del lote 41: archivo parcial con 6 facturas generado (el export de DGH salió incompleto; faltan 35).
  - **Lote nuevo de 1.600 facturas** recibido (16 remesas) y procesado completo el mismo día: organizado en 6 lotes, consolidado, cruzado con DGH. Total: **4.257 ítems glosados, $230.736.952**. Solo TARIFAS y AUTORIZACIÓN — sin CALIDAD (no se necesitan las doctoras) y sin SOPORTES.
  - Todas a tiempo (RE9901): el consolidado de respuestas salió con los textos oficiales del área.
  - Homologación de códigos de glosa vieja→nueva resolución: 206→TA0601 · 207→TA0701 (confirmado) · 223→TA2301 · 423→AU2301.
  - **CONSOLIDADO RESPUESTAS GLOSAS MASIVO 1600.xlsx**: un solo Excel con las 4.395 respuestas de los 6 lotes.
- **22/07** — **Operación** (chat) — día de cierre del lote 1.600:
  - **Portal COOSALUD en paralelo**: 4 ventanas a la vez (listas de 400). En 2,5 horas se cerraron **1.425 facturas** (+84 de la corrida de la mañana = 1.509); quedaron 90 "no en bolsa" y 1 error.
  - La plataforma reportó **137 facturas pendientes** (las 41 del lote del 16/07 + 96 del 1.600). Se les armó su Excel de respuestas (`CONSOLIDADO RESPUESTAS PENDIENTES 137.xlsx`) y su lista para el bot, con `--incluir-calidad` porque las extemporáneas responden TODO con RE9502.
  - **Objeciones del lote 1.600 confirmadas en DGH** (el export de seguimiento las trae con fecha 17/07).
  - **Trámites DGH generados y entregados**: 4 lotes de máximo 499 (1.599 facturas, RE9901) + el archivo de las **35 restantes del lote del 16/07** (RE9502). Listos para que los suban los de DGH.
  - **HUS530335** no se pudo objetar ("no está en DGH", igual que las 5 famosas) → registro manual.
  - Sorpresa: 4 de las 5 que no cruzaban (513595, 515251, 516765, 520580) **ya aparecen registradas en DGH** (06/07) — alguien las metió a mano.
  - **Excel GI-33-5181-2026**: control de 2.215 facturas contra todo lo trabajado en el chat — las 2.215 están, 0 NA.
  - Se dejaron los comandos para unificar las evidencias (Word + PDF `GI-33-5181-2026`) y armar la carpeta en el servidor Z: (RESPUESTA GLOSA INICIAL\GI-33-5181-2026 + EVIDENCIAS SUBIDAS).
  - Se creó esta **bitácora** y la instrucción en CLAUDE.md; se arregló el CI (3 pruebas con fechas vencidas) y quedó en verde.

---

## PENDIENTE

1. **Correr el comando de las 137 pendientes** en el portal (Excel y lista ya entregados) y cuadrar con su reporte.
2. **Que los de DGH suban los 5 archivos de trámites** entregados el 22/07 (4 lotes del 1.600 + 35 restantes). Si el parcial de 6 facturas del 21/07 no se ha subido, subirlo también.
3. **Evidencias**: correr los 4 pasos (lista → Word → PDF `GI-33-5181-2026` → carpeta en Z:) cuando estén cerradas las 137.
4. **Registrar manualmente en DGH**: HUS530335 y HUS506920 (sus servicios no están en la base DGH).
5. **4 de las 5 no-cruzadas ya registradas en DGH** (513595, 515251, 516765, 520580): definir su respuesta y generar su mini-trámite.
6. **37 facturas de auditoría médica** (masivo del 14/07): subir sus trámites cuando las doctoras respondan (sus conceptos ya vienen en el export del 22/07).
7. **Casos sueltos**: HUS531067 (trámite del 14/07, verificar si ya tiene respuesta) y HUS520206 (está entre las 37 de doctoras).
8. **Confirmar en DGH** los códigos TA0601, TA2301 y AU2301 para dejar la homologación 206/207/223/423 en el bot.

---

## PARA MAÑANA (23/07/2026)

1. Verificar que los de DGH hayan subido los 5 archivos de trámites; si devuelven errores, corregir y reintentar.
2. Correr (si no se corrió hoy) el comando de las 137 pendientes y confirmar que el portal quede en cero.
3. Evidencias → PDF GI-33-5181-2026 → carpeta en el servidor Z:.
4. Registrar a mano HUS530335 y HUS506920 en DGH.
5. Preguntar a auditoría médica por las 37 de CALIDAD.

---

## DÓNDE ESTÁ CADA COSA

| Qué | Dónde |
|---|---|
| Bots de COOSALUD (organizar, consolidar, corregir errores, trámites) | `tools/` (y en el equipo de trabajo, carpeta BOTS COOSALUD) |
| Bot que responde en el portal COOSALUD | `tools/responder_glosas_coosalud.py` (en el equipo: `C:\temp-notas\tools\`) |
| Contexto y reglas del proceso COOSALUD | `docs/CONTEXTO_COOSALUD.md` |
| Contextos de Dispensario | `docs/CONTEXTO_DISPENSARIO_*.md` |
| Facturas del piloto ya objetadas (no repetir) | `tools/FACTURAS YA OBJETADAS.txt` |
| Trabajo en el equipo del usuario | `D:\USUARIO CARTERA\Desktop\RESPUESTA COOSALUD 1600\` (R1–R4, evidencias y reportes) |
