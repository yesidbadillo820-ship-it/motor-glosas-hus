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
- **27/07** — **Documento de entrega técnica** del módulo COOSALUD (`docs/ENTREGA_MODULO_COOSALUD.md`): arquitectura, cada bot, el flujo completo, reglas de negocio y riesgos. Sirve para pasarle el conocimiento a otro equipo.
- **13–14/08** — **Operación** (chat) y tres correcciones de fondo:
  - **CROTIPOBJ arreglado**: el tipo de objeción (0 administrativa / 1 médica / 2 mixta) se calculaba mirando *todas* las glosas del portal, incluso las que solo se mencionan en la observación. DGH lo calcula sobre el concepto que uno **escribe**. Ahora el bot hace lo mismo: si todos los conceptos escritos de la factura son CL → médica; si ninguno → administrativa; si hay de los dos → mixta. Se verificó con las 5 facturas que DGH había clasificado distinto y todas coincidieron; en el masivo de agosto cambiaron 8 de 589.
  - Bot **LISTA FACTURAS YA EN TRÁMITES** (`facturas_ya_en_tramites.py`): revisa la carpeta de masivos ya enviados y arma el TXT de facturas que **no** se deben repetir. Solo cuenta los masivos realmente diligenciados (con CÓDIGO RESPUESTA lleno) y de la EPS que se le pida, para no mezclar Dispensario con COOSALUD.
  - **Lotes procesados**: COOSALUD 7 (23 facturas, $27,9 millones), COOSALUD 1 (29 facturas, $5,4 millones) y el masivo de agosto (589 facturas, $5.612 millones). Cierre del mes: **641 facturas / $5.674.278.862**.
- **19/08** — Bot **FILTRAR BASE DGH** (`filtrar_base_dgh.py`): recorta la base "SERVICIOS FACTURADOS COOSALUD DGH.xlsx" (70 MB) a las facturas del lote, para poder moverla. Se le pasan las facturas por carpeta, por TXT o por lista.
- **25/08** — **Lote nuevo COOSALUD_25082026: 1.573 facturas**:
  - Organizado en 6 lotes y consolidado: **4.533 ítems, 4.691 glosas, $289.077.286**. Todas a tiempo (RE9901); solo 2 con CALIDAD (HUS532676 y HUS532956); 193 con copago.
  - Entregados los consolidados y el paquete del portal (Excel masivo + 4 listas para correr en paralelo: 394/394/394/391).
  - **Tropiezo**: al cruzar con DGH la base solo trajo **9 de las 1.573**. La base que se está usando es del 08/07 y además venía recortada (leyó 1.048.000 filas, prácticamente el tope de Excel). Hay que bajar de DGH un export **nuevo**, por tandas de fechas.
  - Por eso el bot FILTRAR BASE DGH ahora acepta **varias bases a la vez** (las tandas), quita las filas repetidas y avisa dos cosas: si una base llegó al tope de filas de Excel (salió recortada) y hasta qué número de factura llega cada una (para ver de una si está vieja).

---

## PENDIENTE

1. **Base DGH nueva** (lo que bloquea el lote de 1.573): bajar de DGH el export de SERVICIOS FACTURADOS COOSALUD que cubra de HUS533xxx en adelante. Si no cabe en un solo Excel, bajarlo por tandas de fechas y pasarlas todas al bot FILTRAR BASE DGH. Con eso se genera el OBJECIONES del lote.
2. **Portal COOSALUD del lote de 1.573**: correr las 4 listas en paralelo (S1–S4). No depende de la base DGH, se puede hacer ya.
3. **8 facturas de auditoría médica de agosto** (HUS527358, HUS529493, HUS530150, HUS530676, HUS530701, HUS531001, HUS531885, HUS533202): esperar la respuesta de las doctoras para armar sus trámites.
4. **Registrar manualmente en DGH**: HUS530335 y HUS506920; y los ítems sueltos ACETAZOLAMIDA de HUS527199 ($10.200) y BUPIVACAÍNA de HUS529267, HUS531631 y HUS531672 ($30.600 cada una).
5. **Evidencias**: unificar → PDF `GI-33-5300-2026` → carpeta en el servidor Z:.
6. **37 facturas de auditoría médica** del masivo del 14/07: siguen esperando a las doctoras.
7. **Confirmar en DGH** los códigos TA0601, TA2301 y AU2301 para dejar cerrada la homologación 206/207/223/423 en el bot.
8. **Riesgo conocido**: quedan ~14 pruebas del proyecto con fechas fijas que se van a vencer y tumbar el CI. Cambiarlas a fechas relativas cuando haya un rato.

---

## PARA MAÑANA (26/08/2026)

1. Bajar la base DGH nueva (por tandas si toca) y correr FILTRAR BASE DGH con las 1.573 facturas.
2. Generar el OBJECIONES del lote de 1.573 y subirlo a DGH en tandas de 300.
3. Correr el portal COOSALUD con las 4 listas del lote de 1.573.
4. Insistir con auditoría médica por las 8 facturas de CALIDAD de agosto.
5. Registrar a mano en DGH lo que no cruza (HUS530335, HUS506920 y los 4 ítems sueltos).

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
