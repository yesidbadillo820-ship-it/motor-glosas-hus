# BITÁCORA DE TRABAJO — GESTIÓN DE GLOSAS ESE HUS

> **Memoria común de todos los chats de Claude Code.**
> Al iniciar cualquier sesión: leer este archivo primero.
> Al terminar: actualizarlo con lo hecho, lo pendiente y lo que sigue, con la fecha.

**Última actualización: 22/07/2026**

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
- **22/07** — **Operación** (chat):
  - Arrancó la respuesta masiva de las 1.600 en el portal COOSALUD con el bot.
  - Se dividió el trabajo en **4 ventanas en paralelo** (listas de 400 facturas cada una) para acelerar: PARALELO_1 a 4, cada una con su reporte y su carpeta de evidencias.

---

## PENDIENTE

1. **Terminar la respuesta de las 1.600 en el portal COOSALUD** (4 ventanas en paralelo corriendo). Al final: cuadrar los 4 reportes (reporte_R1..R4.csv) contra las 1.600 y revisar las que salgan NO_EN_BOLSA.
2. **Confirmar el cargue a DGH de los 6 OBJECIONES del lote 1.600** (ya generados con la base DGH).
3. **Trámites del lote 41**: re-exportar el seguimiento en DGH (bajando el scroll hasta el final para que salgan todas) y generar el archivo de las **35 facturas restantes**. Las 6 primeras ya tienen archivo (MASIVO COOSALUD 21072026 PARCIAL).
4. **37 facturas de auditoría médica** (36 En Pausa + 1 En Bolsa del masivo del 14/07): subir sus trámites cuando las doctoras respondan.
5. **5 facturas que no cruzan en DGH** (HUS506920, HUS513595, HUS515251, HUS516765, HUS520580): registrarlas manualmente en DGH o esperar base actualizada.
6. **Casos sueltos por verificar**: HUS531067 (trámite del 14/07 que apareció en un export) y HUS520206 (quedó sin responder en el portal).
7. **Confirmar en DGH** que existen los códigos TA0601, TA2301 y AU2301; si se confirman, agregar la tabla de homologación al bot consolidador.
8. **Evidencias del lote 1.600**: cuando termine el portal, unificar los pantallazos en Word/PDF y armar la carpeta GI-33-XXXX-2026.

---

## PARA MAÑANA (23/07/2026)

1. Revisar cómo amanecieron las 4 ventanas del paralelo; reanudar las que falten con `--saltar-csv` y cerrar las 1.600.
2. Hacer el cuadre final: 4 reportes CSV vs las 1.600 (cerradas / no en bolsa / pendientes) e informe del día.
3. Re-export de seguimiento DGH del lote 41 → generar y subir el archivo de trámites de las 35 restantes.
4. Confirmar (o hacer) el cargue de los 6 OBJECIONES del lote 1.600 en DGH; si DGH devuelve errores, usar el bot CORREGIR ERRORES DGH.
5. Preguntar a auditoría médica por las 37 facturas de CALIDAD pendientes.

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
