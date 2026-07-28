# Anexo — Auditoría del sistema de partida

**ESE Hospital Universitario de Santander** · 27 de julio de 2026

> **Documentación histórica.** Este anexo describe el sistema tal como estaba
> ANTES de SINAC OS. Se conserva porque es la evidencia sobre la que se tomaron
> las decisiones del [Manual de Arquitectura](MANUAL_ARQUITECTURA_SINAC_OS.md),
> no como plan de trabajo: el plan vigente es el roadmap por épicas del manual.
>
> Método: 15 auditorías técnicas independientes sobre el código real
> (304 módulos revisados, 142 duplicaciones, 166 hallazgos de uso), más una
> revisión adversarial de completitud que corrigió cifras y contradicciones.

---

## 1. Radiografía del sistema actual (Fase 1)

El sistema que hoy usa el área de glosas del HUS es grande y funciona: 100.259 líneas de backend en 193 archivos, 686 endpoints, 37 tablas y una suite de 4.266 pruebas automatizadas (verificado sobre el repositorio, 27-jul-2026). No es un prototipo ni un experimento: responde glosas reales, genera el Excel radicable que se entrega ante la EPS, calcula extemporaneidad con festivos colombianos, verifica que la IA no invente normas y tiene bots que trabajan contra los portales de verdad. En SIMED —el flujo de mayor volumen— **los bots procesaron 324 facturas y 597 objeciones en siete lotes; de los tres últimos, por $153.675.820, el Excel está listo y la subida sin confirmar** (`BITACORA.md:173-181`). Dentro de esos tres lotes hay 3 facturas de junio con 38 objeciones por **$20.054.751 cuyos plazos (6 y 8 de julio) ya estaban vencidos cuando se detectaron, el 22 de julio**: eso es **plata en riesgo, no plata defendida ni recuperada**, y es la mejor prueba de que el problema del sistema no es la calidad del dictamen sino el trecho entre generarlo y radicarlo.

Lo que el sistema resuelve bien es la parte más difícil de construir: el **conocimiento jurídico y operativo destilado de 33 rondas de corrección contra casos reales**. Lo que no resuelve es la parte más fácil de imaginar: que ese conocimiento llegue completo, una sola vez y sin retrabajo, desde el correo de la EPS hasta el portal donde se radica la respuesta. El sistema sabe muchísimo y está mal conectado consigo mismo. De las **15 auditorías técnicas independientes** salieron **304 módulos revisados, 142 duplicaciones estructurales y 166 hallazgos de experiencia de uso**; de esos, un número sorprendente no son defectos de programación sino **el mismo dato de negocio escrito en cuatro lugares distintos que ya no coinciden**. Esa es la enfermedad; todo lo demás es síntoma.

### El sistema en números

| Zona | Tamaño verificado | El dato que importa |
|---|---|---|
| Backend completo (`app/`) | 193 archivos, 100.259 líneas | Es un sistema mediano de verdad, no un script grande |
| Routers (la API) | 59 archivos, 50.174 líneas, **686 endpoints** | 686 puertas para un equipo que usa unas 60 |
| Servicios (la lógica de negocio) | 103 archivos, 44.478 líneas | Aquí vive el activo real del hospital |
| Frontend | **1 solo archivo**: `static/index.html`, **23.125 líneas** (toda la carpeta `static/`, html+js+css: **26.728**) | 26 pantallas, 276 llamadas al backend, **0 formularios HTML** (`grep -c '<form'` = 0) |
| Base de datos | **37 tablas** (`grep -c "__tablename__" app/models/db.py`) | **8 tablas (8 de 37 = 22%) sin una sola referencia en el código** |
| Migraciones de base de datos | 1 sola migración formal (`alembic/versions/`) + ~460 líneas de `ALTER TABLE` ejecutadas al arrancar (`app/main.py:144-660`) | El esquema se modifica al prender la aplicación, y si falla, arranca igual |
| Bots y utilitarios (`tools/`) | 33 scripts = 16.100 líneas · `tools/adres/` 5 scripts = 3.998 · 3 bots `.cmd` = 1.010 | Solo **7 de los 33 son RPA** (6.040 líneas = 37%); los otros 26 mueven archivos, Excel y PDF |
| Tecnología de los bots | **Cuatro bots de portal en producción**: 3 en Playwright contra 2 portales web (COOSALUD, SIMED-glosas, SIMED-soportes) + 1 en pywinauto contra la aplicación de escritorio del DGH. Los otros 3 scripts RPA son auxiliares (verificador, agente de lotes, login) | **No hay Selenium** en el repositorio (`grep -rli selenium` = 0 archivos) |
| Pruebas automatizadas | **626 archivos `.py` en `tests/`**, de los cuales **616 empiezan por `test_`** (142 en `tests/test_services/`). La suite **ejecuta 4.266 pruebas** (corrida real del 23-jul). Por otra medición distinta, esos archivos suman 78.865 líneas de código de prueba | Es la red de seguridad que permite migrar sin romper |
| Los 3 archivos más grandes | `glosas_stats.py` 11.341 l · `glosas.py` 10.241 l · `glosa_service.py` 8.981 l | Tres archivos concentran 30.563 líneas: el 30% del backend |
| Endpoints sin un solo botón en la interfaz | 62 de 127 en `glosas.py` · **167 de 171** en `glosas_stats.py` · 34 de 42 en `sistema.py` | Se construyó, se probó y nunca se entregó |
| Deuda visual del frontend | 2.216 estilos escritos dentro del HTML, 288 `!important`, 44 `prompt()`, 44 `confirm()`, 12 `alert()` | Ningún cambio de diseño es seguro, y el módulo de conciliación se opera con ventanitas del navegador |
| Resultado de las **15 auditorías** | **304 módulos revisados, 142 duplicaciones, 166 hallazgos de uso** | Cada afirmación de este documento tiene archivo y línea detrás |

### Qué hace cada gran bloque y qué problema resuelve

| Bloque (tamaño) | Qué problema real resuelve | Salud | El hecho que lo define |
|---|---|---|---|
| **1. Conocimiento jurídico y prompts** (16 archivos, 10.216 l) | Es el cerebro jurídico: contratos por EPS, reglas de defensa, normas con texto literal, banco de respuestas del equipo. Es lo que hace que el dictamen se sostenga ante la EPS. | **Con deuda** | El contenido es oro y está preso en Python: 4 catálogos de normas paralelos, y la UVB 2026 ($12.110) repetida en más de 10 archivos pese a existir `uvb.py` con el valor canónico. Cambiar una norma exige un programador. |
| **2. Núcleo de análisis IA** (19 archivos, ~15.050 l) | Convierte el texto de una glosa en un dictamen defendible: clasifica, enriquece con contrato y tarifa, llama al modelo, sanea y guarda. | **Con deuda grave** | El método `analizar()` tiene ~2.800 líneas en un solo bloque (`glosa_service.py:4299-7097`), con **73 `except Exception` silenciosos dentro del propio método** (84 en el archivo completo) y 32 "redes finales" cosidas por orden cronológico de bug, no por diseño. Y hay **dos orquestadores** distintos: el manual y el de lote. |
| **3. Calidad y verificación** (13 archivos, ~4.220 l) | Impide que la IA invente valores, contratos, CUPS o sentencias. Es lo que separa este producto de pegarle la glosa a un chatbot. | **Con deuda** | La mejor ingeniería del sistema (Quality Gate: 1.748 líneas + 1.151 de tests) **está apagada por defecto**: `QUALITY_GATE_ENABLED` ni figura en `.env.example`. Y hay 6 escalas de puntaje sobre el mismo dictamen, ninguna reconciliada. |
| **4. Ciclo de vida de la glosa** (routers, ~12.726 l) | Modela el proceso colombiano completo: radicada → objetada → respondida → ratificada → conciliación → acta con mérito ejecutivo. | **Con deuda + roto a la vista** | **Tres máquinas de estado** escriben el mismo campo, una de ellas sin validar transiciones (`glosas.py:2580`). El botón "Simular conciliación" (`index.html:20509`) llama a una ruta que no existe: 404 siempre. |
| **5. Contratos y tarifas** (~7.450 l) | Sostiene el argumento con el número de contrato, el factor tarifario y la cláusula exacta con página. Es lo que gana las glosas TA. | **Roto en su promesa central** | Editar el contrato de una de las 14 EPS principales desde la pantalla **no cambia nada**: `get_contrato` prioriza el catálogo escrito en Python (`glosa_ia_prompts.py:383-384`, textual: "El catálogo estático sigue teniendo prioridad"). Y no existe formulario para crear un contrato nuevo. |
| **6. Frontend — navegación** (26 pantallas en 1 archivo) | Es la puerta de entrada al trabajo diario: sidebar, buscador, atajos. | **Roto** | Ctrl+K abre **tres paletas de comandos superpuestas**; la tecla `/` deja un overlay que no se puede cerrar (hay que recargar y se pierde la glosa); el menú tiene un ítem "Salud Total" cuyo backend fue borrado en mayo de 2026. |
| **7. Bots / RPA** (7 scripts, 6.040 l; **cuatro bots de portal**) | Tipean la respuesta en el portal de la EPS: COOSALUD, SIMED-glosas, SIMED-soportes, DGH. Es donde se ahorran las horas. | **Sano por dentro, desconectado por fuera** | El conocimiento de portal está pagado con meses de producción (el modal de un solo uso, el filtro que requiere teclas reales). Pero **el frontend no sabe que los bots existen**: 0 menciones de RPA, Playwright o de cualquier script de `tools/` en las 23.125 líneas de la interfaz. |
| **8. Plataforma / base de datos** (37 tablas) | Guarda glosas, conceptos, contratos, tarifas, versiones, auditoría, credenciales. | **Con deuda grave** | Enviar una glosa a la papelera **borra físicamente** conceptos, todas las versiones del dictamen, comentarios y conciliaciones por CASCADE (`glosas.py:3483`); al restaurar solo vuelve la cabecera. Y el sistema **reporta que cifra los datos del paciente** (`sistema.py:147`) mientras `cifrado.py` no tiene ni un solo importador. |
| **9. Frontend — flujo del auditor** (mismo archivo) | Es donde el auditor realmente trabaja: pegar la glosa, analizar, revisar, marcar respondida. | **Con deuda grave** | Una vez que el auditor marca un concepto como "Aceptar 100%", la variable nunca se limpia (`index.html:9791` vs `:15039`): **todas las glosas siguientes de la sesión salen como aceptación en vez de defensa**, sin aviso. Y el PDF que se radica lleva un Nº OBJECIÓN generado con `Math.random()` (`index.html:18095`). |
| **10. Soportes y documental** (indexador + PDF) | Encuentra la historia clínica, los RIPS y la factura en el disco de red por número de factura, y produce el documento radicable. | **Roto en el último clic** | Indexa hasta **144.000 archivos** para terminar mostrando la ruta como texto y ofrecer "Copiar" para pegarla en el explorador de Windows: no existe **ni un solo endpoint que devuelva el archivo**. Y todo PDF de más de 4 páginas llega a la IA recortado a ~7.050 caracteres (`pdf_service.py:77-91`): una historia clínica de 200 páginas entra como 7 KB. |
| **11. Lotes y procesamiento masivo** | Resuelve el volumen: importar el Excel del DGH, generar respuestas en masa, devolver el Excel anotado. Es donde está la productividad. | **Con deuda grave** | **Cuatro caminos distintos** para generar dictámenes en masa, con cuatro niveles de concurrencia y cuatro sets de enriquecimiento: la misma glosa sale con calidad distinta según por qué puerta entró. Solo uno tiene las defensas anti-gasto que nacieron de un incidente real de $14,50 en 251 llamadas. |
| **12. IA avanzada / copiloto** (~25 servicios) | Es la promesa de que el sistema aprende: precedentes, plantillas ganadoras, estilo del auditor, predicción de ratificación. | **Con deuda: hoy no aprende** | Verificado en la base de datos: **52 plantillas Gold, las 52 sembradas automáticamente, 0 aprendidas de un caso real, todas con usos = 0**. El circuito está cortado por tres lados a la vez. Y el "chat sobre la glosa" no hace una sola llamada a IA: son 8 respuestas fijas por palabra clave. |
| **13. Analítica e indicadores** (~15.000 l) | Debería responder las cinco preguntas de un gerente de cartera: cuánto recuperamos, contra quién, por qué causal, quién rinde, qué se proyecta. | **Roto como fuente de verdad** | **"Valor recuperado" tiene cinco fórmulas incompatibles y cuatro conviven en la misma barra de pestañas del coordinador.** Ningún tablero es firmable por un auditor porque el mismo número cambia al cambiar de pestaña, sin explicación. 167 de 171 estadísticas no tienen puerta en la interfaz. |

Tres bloques están **rotos a la vista del usuario** y deben repararse antes que nada, porque cada uno erosiona la confianza en todo lo demás: contratos (editar es placebo), navegación (menús que llevan a 404 y overlays que bloquean la aplicación) y analítica (números que no cuadran entre sí). Dos bloques están **sanos y desperdiciados**: los bots y el indexador de soportes — funcionan bien, y nadie puede usarlos desde la aplicación.

### EL HALLAZGO CENTRAL: el sistema está partido en dos mitades

La hipótesis con la que empezó la auditoría era que todos los bots hacen lo mismo (recibir → extraer → clasificar → analizar → generar respuesta → exportar → historial) y que por eso hay que unificarlos en un motor con perfiles. Esa hipótesis es **parcialmente cierta, y por una razón más grave que la supuesta**.

Los bots no hacen ese pipeline. Hacen **solo el último tramo**. Ningún bot clasifica, ninguno analiza, ninguno genera respuestas y ninguno guarda historial. La prueba es directa y la verifiqué de nuevo sobre el código: en `responder_glosas_coosalud.py`, `responder_glosas_simed.py`, `cargar_soportes_simed.py` y `responder_glosas_dgh.py` **no existe una sola llamada HTTP que no sea al portal de la EPS** (`grep -nE "requests\.|urlopen|httpx"` sobre los cuatro archivos devuelve cero resultados). Las etapas de clasificar, analizar y generar **sí existen** —y están bien hechas— pero viven en `app/` y no están conectadas con los bots.

**El puente entre las dos mitades es hoy un archivo Excel que viaja en el escritorio de una PC.** Un humano exporta el resultado del motor, lo guarda, y otro proceso lo levanta y lo tipea en el portal. Para SIMED —el flujo con más volumen real del hospital— el resultado de la corrida ni siquiera vuelve al sistema: **queda en un CSV en el escritorio** (el único bot que reporta a la API es COOSALUD, y solo a través del agente de lotes). Ese puente es exactamente el punto donde se perdieron los plazos de las 3 facturas de junio: el dictamen estaba hecho y el sistema no tenía cómo saber que nadie lo había subido.

Por qué esto es la raíz de casi todo lo demás:

- **Explica las duplicaciones.** Como las dos mitades no se hablan, cada una se construyó su propia versión de las mismas cosas: su catálogo de códigos de soporte, su taxonomía de familias de glosa, su normalizador de EPS, su generador de Excel. No son descuidos: son consecuencias inevitables de la desconexión. Existen dos scripts (`asistente_conciliacion_dispensario.py`, 727 l, y `motor_glosas_hus.py`, 399 l) que reimplementan **fuera de la API, peor y sin IA**, exactamente lo que el motor ya hace.
- **Explica el retrabajo.** Los scripts `extraer_respuestas_glosa.py` y `convertir_tramite_masivo.py` existen **únicamente** porque el bot no habla con el motor: son el pegamento manual entre "el sistema ya sabe la respuesta" y "el bot la escribe en el portal".
- **Explica que no haya trazabilidad.** El bot cierra la factura en el portal, saca el pantallazo que prueba el cumplimiento del plazo… y nadie actualiza el estado en el sistema. La evidencia legal queda en una carpeta local con nombre relativo al directorio desde donde se corrió el script.
- **Explica la ausencia de interfaz.** El procedimiento operativo del hospital está escrito en un `.md` cuya primera instrucción es *"pegá su contenido completo como primer mensaje en un nuevo chat"* (`docs/CONTEXTO_COOSALUD.md:2-5`). El runbook de producción de una ESE pública depende de que alguien copie un archivo a un chat. Eso no es una interfaz: es la ausencia de una.

**El Orquestador de SINAC OS (§6 del blueprint) es exactamente la pieza faltante — no una función nueva, sino el cable que nunca se puso.** El ejemplo que el blueprint plantea (*Leer PDF → Extraer datos → Buscar contrato → Buscar normas → Consultar historial → Construir respuesta → Generar Word → Exportar PDF → Guardar expediente → Actualizar historial*) describe con precisión lo que hoy ocurre partido en dos, con un Excel y una persona en el medio. Las dos mitades **ya existen y ya funcionan**: lo que falta es que el bot le pida la respuesta a la API en vez de leerla de una planilla, y que le devuelva el resultado y el pantallazo al expediente. Ese solo cambio elimina de un golpe el Excel intermedio, los dos scripts de pegamento, los dos motores de glosa paralelos y el CSV en el escritorio.

Y hay una razón de calendario para hacerlo ahora: **hoy existen cuatro bots de portal** (COOSALUD, SIMED-glosas, SIMED-soportes, DGH). El cliente ya nombró cinco pagadores más —**SAVIA, EMSSANAR, VCO, MUTUAL SER y FOMAG**— que todavía no tienen bot; escritos con el patrón actual, serían **nueve**. Unificar con cuatro cuesta una fracción de lo que costará con nueve.

### Una sola fuente de verdad: la regla que el sistema viola

El principio del blueprint (§3) dice: *"Nunca existirán dos lugares con la misma información."* Hoy hay conceptos centrales del negocio —catálogo de normas, ficha de contratos por EPS, perfil de pagador, códigos de soporte ADRES, taxonomía de familia de glosa, escala de confianza del dictamen, máquina de estados, enrutador de modelo de IA, capa de sanitización y la definición de "valor recuperado"— que existen **entre dos y seis veces cada uno**, y en varios de ellos las copias **ya se contradicen entre sí**: dos verdades sobre los plazos del Art. 57, dos significados clínicos del código `PDX`, dos lecturas del código de familia `CL`. Esa contradicción no se queda en el código: llega al dictamen que se radica y a los tableros que el coordinador lee mientras redacta.

**El inventario completo, concepto por concepto, con el número de copias, el ganador declarado y qué se borra, está en §5.5. No se repite acá.**

### Qué está sano y no hay que tocar

Esta es la **única lista de este tipo en todo el documento** (§3.1 remite acá y no repite su tabla). Es lo que costó meses de bugs reales, lo que ninguna reescritura debe perder y lo que debe migrar **intacto** a la 2.0. La regla de migración es siempre la misma: **cambiar el contenedor, jamás el contenido.**

| Joya | Dónde vive | Por qué costó y qué protege | Cómo migra |
|---|---|---|---|
| **Las reglas 8.x del prompt maestro** | `glosa_ia_prompts.py:698-749` | ~15 reglas de defensa destiladas de fallas reales, cada una con fecha y caso: sanciones = vicio de competencia, nunca negar un contrato citado, atacar la legalidad de las multas, cada norma una sola vez. Es la experiencia de 33 rondas de auditoría adversarial. **El activo más difícil de reconstruir del repositorio.** | A datos versionados, editables por el auditor jurídico, con historial. Jamás perderse. |
| **El trío anti contrato-cruzado** | `glosa_ia_prompts.py:372-547` | Nació de 3 casos reales donde el dictamen citó el contrato de OTRA EPS — error que "la EPS verifica en segundos y destruye el dictamen completo". | La lógica de matching sobrevive tal cual, aunque el catálogo se mude a la base de datos. |
| **Corpus normativo con texto literal + verificador de citas** | `normativa_completa.py` + `citation_verifier.py` | El mecanismo anti-alucinación jurídica más sólido del sistema: detecta norma inexistente, artículo fuera de norma y cita literal falsa. Sus expresiones traen cicatrices con nombre propio (la sentencia fantasma "C-4747/2007", el guion Unicode del caso FOMAG). | Único corpus, único validador. Se conserva entero. |
| **El conocimiento de las 32 "redes finales"** | `glosa_service.py` | Cada una tapa un bug de alucinación pagado con dolor: EPS inventada, CUPS falsos, CUPS confundido con número de factura, valores inventados, citas descomilladas, sanción ilegal a la EPS. **La forma es deuda; el contenido es el activo.** | Se migran **una por una, cada una con su test** (ya existen), como transformaciones registradas y ordenadas. |
| **Los caminos sin IA** | `texto_fijo`, plantilla por código, `dictamen_directo.py` | Dictámenes a **$0 y ~50 ms** con retorno seguro al modelo si no aplican. Es el mayor retorno económico del sistema. | Ramas de primera clase del pipeline, no `try/except` incrustados. |
| **Las defensas anti-gasto de IA** | `auto_responder_service.py:242-366` | Reuso de dictámenes gemelos por hash, corte por complejidad, semáforo de concurrencia. Nacieron de un incidente real de $14,50 en 251 llamadas. Hoy protegen **un** flujo de cuatro. | Camino obligatorio de **toda** generación de dictamen. |
| **La puerta de entrada del DGH** | `recepcion_service.py` (1.458 l) | Alias reales de las columnas del DGH, extemporaneidad por días hábiles con festivos colombianos, resolución difusa de gestor con delegación por vacaciones, textos fijos jurídicos que evitan quemar tokens. **Conocimiento de dominio irrecuperable si se pierde.** | Se protege tal cual; solo se separan sus 8 responsabilidades. |
| **El motor tarifario determinista** | `tarifa_lookup_service.py` (649 l) + `contexto_contractual_enriquecido.py` (920 l) + `extractor_clausulas_contrato.py` | Evalúa el mérito de una glosa de tarifas **sin gastar IA**, con heurísticas ganadas en producción, y hace que el dictamen cite la cláusula exacta con número de página. Es la capacidad diferencial del producto. | Se conserva; solo el catálogo pasa a la base de datos. |
| **Los entregables reales** | `excel_radicable.py` + `exportar_dgh.py` (26 columnas canónicas) + `services/dictamen_pdf.py` | Son los documentos que efectivamente se radican y que el DGH exige. El Excel radicable tiene la regla de oro escrita: **si falta un metadato, degrada a texto genérico en vez de inventar un número.** | Único generador, en el servidor, con consecutivo real persistido. Se eliminan los tres generadores del navegador. |
| **El conocimiento de portal de los bots** | `responder_glosas_coosalud.py`, `responder_glosas_simed.py` | El modal del portal es de un solo uso por carga de página; el filtro solo reacciona a eventos de teclado reales; el modal se rompe con más de 200 glosas marcadas. Y la política de integridad: **si no aparece el soporte, el grupo se salta y la factura queda pendiente, "para no prometer un soporte que no se adjuntó".** | Se conserva textual dentro del adaptador de cada portal. |
| **El contrato de Perfil de entidad, ya probado** | `tools/radicar_facturacion.py:266-344` + `data/perfiles_radicacion.json` | Ya implementa el patrón que la 2.0 necesita: **perfil declarativo en JSON + motor genérico**, **12 entidades** cargadas, editable sin tocar código, con librería estándar pura (corre en cualquier PC del hospital sin permisos de sistemas). | El Perfil de pagador 2.0 **extiende este**, no inventa otro. |
| **El patrón "núcleo como librería"** | `verificar_glosas_coosalud.py` | 234 líneas que reutilizan el bot grande como librería sin copiar una sola función. Es la **demostración empírica, dentro de este mismo repositorio, de que la unificación de bots funciona.** | Se generaliza: hoy es la excepción, debe ser la regla. |
| **Lo mejor del esquema de datos** | `conceptos_glosa` · el trío `lotes`/`facturas_lote`/`tareas_lote` · `credenciales_vault` · los PRAGMAs de `app/database.py` | `conceptos_glosa` es el único modelo que representa bien el negocio (una glosa agrupa N conceptos, con idempotencia real por el identificador del DGH). El trío de lotes es el único lugar del repositorio con estados centralizados y llaves foráneas reales. El vault es **el único cifrado que de verdad cifra**, con motivo obligatorio y registro de cada acceso. | `conceptos_glosa` pasa a ser el centro del esquema. El vault es el patrón que debe aplicarse a los datos del paciente. |
| **Lo mejor de la interfaz** | La bandeja "Mis glosas" con priorización · el aviso de vencimiento a 24 h con valor en riesgo · el aviso de factura duplicada · la narración en vivo del análisis · **el diseño de "Preparar el día" (`index.html:7112`), hoy ROTO** | Un botón, una acción, resultado explicado en español, idempotente. La bandeja resuelve hasta 100 glosas en 5 clics — es el camino más barato del sistema y hoy está a dos niveles de profundidad, mientras el camino más caro (12-14 clics por glosa) es el que abre por defecto. **Aclaración obligatoria: "Preparar el día" NO funciona.** El botón llama a `POST /autopilot/preparar-dia` y ese router fue borrado (`app/main.py:1207`: *"autopilot: removido en la limpieza de ronda 29"*): hoy devuelve 404. Su frecuencia de uso real es **nula (roto)**. Lo valioso es el diseño, no el estado actual. | **Resucitar "Preparar el día"** —reponer el endpoint sobre el motor actual— dentro del paquete A0 de §10.3, por ser la automatización de mayor retorno del producto; y ascender la bandeja y ese botón a primera pantalla. El vocabulario de las vistas guardadas ("TA sin contrato", "alta cuantía", "dictamen obsoleto") se conserva aunque el filtrado se rehaga entero. |
| **Los entregables de gerencia** | `informes.py` (informe ejecutivo mensual imprimible) · `dashboard_ejecutivo.py:241-421` (detector de gestores inactivos con carga) · `analytics.py:276-405` (win-rate por par EPS+código) | El informe mensual es el único artefacto que un gerente puede llevar impreso a un Comité de Cartera, y su estructura es la correcta. El detector de actividad es la única analítica que responde "¿qué hago ahora?" en vez de "¿cuánto llevo?". | Se conservan, recalculando sobre una **única** definición de cada palabra del negocio. |
| **La red de seguridad** | **626 archivos en `tests/` (616 `test_*.py`), 4.266 pruebas ejecutadas**; 142 archivos cubren servicios | Es lo que permite migrar red final por red final sin romper lo que hoy funciona. Sin esto, la 2.0 sería una apuesta; con esto, es una obra. | Se mantiene y se extiende con una prueba nueva y obligatoria: **que cada botón de la interfaz resuelva a una ruta que existe** — el defecto que hoy produce menús que llevan a 404 y que dejó "Preparar el día" roto sin que nadie se enterara. |

---

## 2. Auditoría de experiencia de usuario (Fase 2)

Esta sección responde una sola pregunta: **¿cuánto le cuesta hoy al auditor usar el sistema, y cuánto de ese costo es evitable?** Todo lo que sigue está medido sobre el código real de la interfaz (`static/index.html`, 23.125 líneas, 276 llamadas al servidor, cero elementos `<form>`) y sobre los endpoints que esa interfaz llama. Los **166 hallazgos** de experiencia de usuario de la auditoría se resumen aquí en lo que cambia el trabajo diario.

El diagnóstico de fondo no es que falten funciones. Es que **el sistema ya sabe hacer casi todo lo que el auditor hace a mano, y no se lo entrega** — y en algunos casos ya lo sabía hacer y se lo quitaron sin avisarle.

---

### 2.1 El costo real de responder una glosa hoy

Existen tres caminos para responder glosas. El más barato ya está construido y funcionando; está enterrado a dos niveles de profundidad. El más caro es el que abre por defecto al entrar.

| Camino | Cómo se llega | Clics medidos | Rendimiento real | Evidencia |
|---|---|---|---|---|
| **Una glosa a mano (el que abre por defecto)** | Pantalla "Analizar", formulario en blanco | **4 clics mínimos + 1 pegado**; **12-14 clics** en el camino realista con factura, radicado, fechas, PDF radicable y cierre | 1 glosa | `index.html:2132, 2155-2176, 2204, 2238, 16407, 16430` |
| **Lote por factura (43 conceptos)** | Escribir el N° de factura dentro del acordeón "Facturación · opcional" | **6 clics** para las 43; **+43 clics y 43 valores tecleados** si se decide concepto por concepto | 43 conceptos de una factura | `index.html:9548-9556, 9841-9998` |
| **Lote por bandeja (hasta 100 glosas)** | Sidebar → "Mis glosas" → seleccionar todas | **5 clics** para generar las 100 respuestas; **8 clics** si además se cierran todas | Hasta 100 glosas | `index.html:2665, 2760, 2729, 2732, 13705, 13441` |

**La paradoja, en números:** responder 100 glosas por la bandeja cuesta 5 clics. Responder esas mismas 100 glosas de a una cuesta entre 1.200 y 1.400 clics. Es una diferencia de **entre 240 y 280 veces** —más de 200 veces bajo cualquier supuesto—, y el camino caro es el que la aplicación ofrece al abrir.

**Campos que el auditor escribe a mano en el camino feliz — hasta 6**, más el pegado del texto de la glosa: EPS (desplegable), N° de factura, N° de radicado, valor aceptado, fecha de radicación y fecha de recepción. **De esos 6, al menos 4 ya están en la base de datos** cuando la glosa entró por el Excel de recepción: `responderGlosa()` los precarga (`index.html:14338-14345`); si el auditor arranca de cero, los vuelve a escribir uno por uno.

Dos costos ocultos que agravan el cuadro:

- **El lote por factura impone 1,8 segundos de espera artificial por concepto** (`index.html:9878` + `:9903`): 43 conceptos = ~77 segundos de reloj *sin contar el tiempo de la IA*, sin barra de progreso y sin botón de cancelar. Ese bucle corre en el navegador: cerrar la pestaña pierde el lote.
- **El botón "Marcar factura como RESPONDIDA" solo cierra una glosa.** Opera sobre `window._factura_conceptos[0].id`, el primer concepto (`index.html:9921-9925` y `:9958`). Si la factura tenía 43 objeciones, **42 quedan abiertas y el auditor cree que cerró todo** — con el reloj del Art. 57 corriendo sobre las 42.

---

### 2.2 Lo que el sistema ya sabe y te hace escribir igual

Esta es la lista de redigitación evitable. En todos los casos el dato ya existe en el sistema, en el mismo momento en que el auditor lo está tecleando.

| Dato | El sistema ya lo tiene en | Qué pasa hoy |
|---|---|---|
| **Valor objetado, valor facturado, valor reconocido, código de glosa, CUPS y descripción del servicio** | `POST /analizar/preview` los extrae del texto pegado sin gastar un token de IA (`analizar.py:1032-1046`) y el panel "Detección automática" **se los muestra en pantalla** (`index.html:21875-21891`) | **Ninguno se escribe en un campo ni viaja en el envío del análisis.** El auditor lee "$24.900 detectado" y no puede hacer nada con ese dato. Peor: desde la segunda glosa el panel ni siquiera aparece, porque `renderResult()` borra el contenedor (`:16440`) y `nuevaGlosa()` no lo reconstruye (`:16886-16893`) |
| **Factura, radicado, fecha de radicación y fecha de recepción** | Precargados desde la base cuando la glosa vino del Excel de recepción (`index.html:14338-14345`) | Si el auditor arranca desde el formulario en blanco, los vuelve a escribir. El campo factura, además, vive dentro de un acordeón **cerrado y rotulado "opcional"** (`:2160-2164`) |
| **Historia clínica, RIPS y factura electrónica del disco de red** | El servidor los lee solo con el número de factura: *"si el gestor NO subió PDFs manualmente, leemos directo del indexador"* (`analizar.py:806-824`) | El banner verde anuncia "✓ N soporte(s) detectado(s) en el servidor" y **su único botón es "Ver detalle", que salta a otro panel** (`index.html:18621-18633`). No hay ninguna acción "usar estos soportes". El sistema le dice al auditor *sé dónde están tus papeles* y acto seguido le pide que los busque él |
| **NIT y razón social de la EPS (obligatorios en el acta SINAC)** | Persistidos en el editor de metadatos de contratos, campos `nit_eps` y `razon_social_eps` (`index.html:3129-3133`, `14314-14317`) | `abrirActaSinac()` **no los consulta** (`:20608-20620`). Son campos marcados con asterisco en el acta (`:3539-3540`): se escriben a mano en cada acta |
| **Nombre y correo del firmante del HUS** | El usuario logueado, en la variable global `USER_NAME` (`index.html:6242`) | **Autocompletado roto:** el acta lee `window.USUARIO_EMAIL` y `window.USUARIO_NOMBRE` (`:20615-20616`), dos variables que **no se asignan en ninguna parte del archivo** (verificado: única aparición de cada una, y es de lectura). Los dos campos del firmante salen siempre en blanco |
| **La EPS de la glosa** | Detectada automáticamente del texto en dos lugares distintos (`index.html:7449` en el navegador, `analizar.py:986` en el servidor) | Se pide igual en el desplegable, y **el desplegable no valida nada**: la primera opción es "OTRA / SIN DEFINIR" con valor no vacío (`:14588`), así que la comprobación `if(!eps)` (`:14971`) nunca puede fallar. **Se puede analizar una glosa sin decir de qué EPS es** |

**Traducción a plata y riesgo:** el número de factura es el dato que dispara tres automatizaciones ya construidas y pagadas — la lista completa de conceptos objetados de esa factura, el aviso de factura duplicada (que evita gastar IA dos veces y radicar dos veces), y la lectura automática de soportes del disco de red. Está escondido en un acordeón que la propia interfaz rotula "opcional". **Mover esas 20 líneas de HTML elimina la mayor parte del trabajo manual de adjuntar soportes.**

---

### 2.3 Pantallas y botones que mienten

Hay dos clases de mentira en la interfaz, y la segunda es peor que la primera.

**A. Funciones que el auditor ve, usa, y están rotas de forma permanente.** Sus routers fueron borrados del backend en mayo de 2026 y la interfaz nunca se actualizó. Los errores se tragan con `catch` vacío o `console.warn`, así que el usuario no ve un mensaje: **ve que el botón no hace nada.**

| Qué promete | Qué hace de verdad | Evidencia |
|---|---|---|
| **Guardar preset de filtros** en Mis Glosas | Llama a `/presets-filtros`, ruta que **no existe en ningún router**. Falla siempre, en silencio | `index.html:13009, 13060, 13084`; error tragado en `:13036` |
| **Nota privada por glosa** (botón flotante amarillo, siempre visible) | El botón aparece *antes* de comprobar nada (`fab.style.display='flex'` en `:21012`, la carga falla en silencio en `:21031`). El auditor escribe su nota, pulsa Guardar y **recibe un toast rojo "No se pudo guardar": se pierde lo escrito** | `index.html:5993, 21015, 21061, 21089`; router eliminado en `main.py:1214` |
| **Comentarios por sección del dictamen** | Router eliminado; además ninguna de las dos implementaciones tiene un botón que la dispare | `index.html:17290, 17318, 17328`; `main.py:1221` |
| **Historial del chat del asistente** | Router eliminado. El chat funciona, la conversación no se guarda | `index.html:17347, 17360, 17377`; `main.py:1218` |
| **"Preparar el día"** (el botón de mayor retorno de toda la interfaz) | Llama a `POST /autopilot/preparar-dia`; el router fue borrado en la ronda 29. **Devuelve 404 y un toast rojo: hoy su frecuencia de uso es nula porque está roto** | `index.html:7112`; `main.py:1207` (*"autopilot: removido en la limpieza de ronda 29"*) |
| **Crear y borrar snippets** ("Gestionar mis snippets") | El backend expone **únicamente GET y devuelve lista vacía**. Su propio docstring lo dice: *"Endpoint mínimo que evita 404 en el frontend. Devuelve lista vacía hasta que se implemente"* (16 líneas en total, verificado). Mientras tanto, el panel **enseña a usar la función**: "/ratif → tu plantilla de ratificación" | `index.html:3378` (botón), `:17820` (panel que instruye), `:17849, 17867` (POST/DELETE inexistentes); `app/api/routers/snippets.py` completo |

A esa lista hay que sumar **una pantalla entera de primer nivel del menú**: "Salud Total" (`index.html:2091`), explícitamente habilitada para el rol AUDITOR (`:19735`), cuyos dos únicos botones devuelven 404 desde mayo de 2026 (`main.py:1177`). El auditor entra, sube un archivo, pulsa, y no pasa nada.

**B. Botones que dan acuse de recibo de un trabajo que no hicieron, e indicadores que informan algo falso.** Esta clase es más grave porque el auditor *no tiene forma de saber* que algo salió mal.

| Qué promete | Qué hace de verdad | Evidencia |
|---|---|---|
| **"Aplicar recomendación"** del banner de acción de la IA (aceptar parcialmente un valor) | Busca tres identificadores de campo — `valor-aceptado`, `valorAceptado`, `input[name=valor_aceptado]` — y **ninguno de los tres existe** (verificado: 0 coincidencias de los dos primeros). El campo real se llama `f-valacp`. **Aun así muestra el toast verde "Recomendación aplicada · valor a aceptar: $X".** El auditor cree que aceptó parcialmente y no aceptó nada | `index.html:15167-15181` contra `:2176` |
| **El sistema informa que cifra los datos sensibles del paciente** | El endpoint de estado publica `"cifrado_fernet": true` con solo tener puesta una variable de entorno, y lo lista como capacidad del sistema. **`app/services/cifrado.py` no tiene un solo importador en todo el repositorio** (verificado). El nombre del paciente, el dictamen clínico y el texto crudo de la glosa se guardan en claro | `sistema.py:147` y `:2839`; `app/services/cifrado.py` sin llamadores |
| **"Firma digital" del dictamen** | Es HMAC con la clave del propio servidor: con esa misma clave el servidor puede firmar cualquier texto. **No prueba autoría, no es no-repudiable y no cumple la Ley 527/1999 ni el Decreto 2364/2012**, que exigen certificado de entidad de certificación | `app/services/firma_digital.py:43, 51` |
| **El PDF que se radica ante la EPS trae un "Nº OBJECIÓN"** | `var tramite = Math.floor(100000 + Math.random()*900000); // consecutivo ficticio para el doc`. **Cada reimpresión de la misma glosa produce un número distinto.** Y el bloque de control imprime "Elaboró: X · Confirmó: X" con la misma persona, simulando un doble control que no ocurrió | `index.html:18095` (impreso en `:18192`), `:18186-18187` |
| **"🧠 Simular conciliación"** (botón morado en la lista de conciliaciones) | Llama a `POST /conciliaciones/{id}/simulador/`, ruta que no existe en ningún router. Devuelve 404 siempre y muestra "No se pudo simular" | `index.html:20424, 20509`; `conciliacion.py` |
| **"Costo aproximado"** del lote de importación | Siempre "$0.00": la columna `costo_real_usd` **solo se lee, nunca se escribe**, pese a que el comentario del modelo dice "se actualiza por fila" | `index.html:8368`; `glosas.py:5058, 5099`; `db.py:627` |
| **"🤖 IA: N/N listas"** en el historial de recepción | Marca 100 % desde el segundo cero: cuenta glosas con dictamen no vacío, pero el servicio de recepción **siempre escribe un dictamen provisional al crear la glosa**. El gestor no tiene cómo saber si la IA ya trabajó | `glosas.py:5713-5723` contra `recepcion_service.py:1081-1087` |
| **"Cancelar lote"** | No cancela: el propio código explica que las filas ya encoladas se siguen procesando y que lo único que cambia es la visibilidad. **La IA se sigue gastando** | `glosas.py:5109-5116`; botón en `index.html:8104` |
| **La barra de progreso del lote** | Animación simulada. El propio código lo declara: *"Barra de progreso determinística simulada (el endpoint no hace streaming...)"* | `index.html:13741` |
| **"N audiencias previas"** en Preparar conciliación | Cuenta glosas cerradas del par EPS+familia. **Nunca mira la tabla de conciliaciones** | `conciliador_ia.py:143-152`; UI en `index.html:11984` |

Y una fuga silenciosa que puede costar plata directa: **al hacer clic una vez en un concepto marcado "Aceptar 100%", todas las glosas individuales del resto de la sesión se analizan en modo aceptación** — es decir, salen cartas de aceptación en lugar de defensas — porque la variable de modo se fija (`index.html:9791`) y **nadie la limpia nunca**: ni "Nueva glosa" (`:16874-16904`), ni "Limpiar formulario" (`:22034-22046`), ni el final del lote. El formulario no muestra ningún indicio del modo en que está.

---

### 2.4 Pantallas confusas y sobrecargadas

**El inventario, verificado:** 26 pantallas en la aplicación (26 identificadores `p-*` únicos), 23 destinos en el menú lateral. La diferencia son **3 pantallas huérfanas**.

| Problema | Detalle medido | Evidencia |
|---|---|---|
| **3 pantallas inalcanzables** | Multi-concepto, Detector en masa y Simulador existen completas, con CSS propio y endpoints vivos, y **no tienen ítem de menú**. Sus tres entradas en el buscador de comandos buscan un botón de menú que no existe y **no hacen absolutamente nada al pulsar Enter: fallo silencioso, sin mensaje** | `index.html:3767, 3797, 3832`; entradas fantasma en `:10840-10842`, lógica en `:10973-10974` |
| **4 pantallas de reportes sobre el mismo dato, y una quinta superficie encima** | Mando, Dashboard, Cobranza Live y Resumen del mes. El propio código documenta el pedido del cliente: *«Feedback Yesid: "4 botones que sacan la misma info → consolidar en uno"»*. La respuesta fue **agregar una barra de pestañas sin eliminar ninguna de las cuatro**. Hoy hay 8 caminos para llegar a 4 vistas del mismo dato — y las 4 pestañas llaman a 4 endpoints con **4 fórmulas distintas de "recuperado"** | `index.html:2879, 2382, 2814, 2847`; comentario en `:12386-12390`; barra en `:12404-12419` |
| **7 superficies responden "¿qué se vence?"** | Pantalla de Alertas, badge del sidebar, KPI del encabezado, banner en Mis Glosas, chip de vista, panel Mando y cajón del asistente — todas sobre los mismos dos endpoints. La pantalla de Alertas son **literalmente dos líneas de markup: sin título, sin filtros, cero botones**, y ocupa un ítem del menú principal | `index.html:3088-3090, 19681, 7091, 2754, 2745, 10439, 12350-12374` |
| **"Analizar": 24 controles antes de poder empezar** | 13 campos + 6 chips de etapa/tono + 5 botones de barra, cuando **solo 2 campos son obligatorios**. Y los atributos "obligatorio" son decorativos: **no existe un solo elemento `<form>` en las 23.125 líneas**, así que el navegador nunca los aplica | `index.html:2125-2381`; obligatorios en `:2131` y `:2184` |
| **"Analizar": 13 acciones después del dictamen** | Hasta 11 sub-paneles apilados + 7 botones en fila + 5 chips de refinado. **"Marcar como RESPONDIDA" —la acción que cierra el ciclo de negocio— queda ÚLTIMA, al final de todo el scroll, con el mismo peso visual que "Copiar texto"** | `index.html:16333-16442`, botón en `:16434` |
| **"Mis glosas": 23 controles, 3 taxonomías de filtro que no se explican entre sí** | 3 pestañas + 8 chips de vista + presets del servidor (que siempre fallan porque el endpoint no existe) + 8 acciones en lote + toggle Lista/Kanban. El auditor debe elegir entre **19 combinaciones** para encontrar el trabajo del día. Además la pestaña, el chip "⏰ Vencen ≤24h" y el banner rojo pueden estar activos a la vez **mostrando tres conteos distintos de lo mismo** | `index.html:2665-2813, 2694-2702, 2743-2750, 13005-13009` |
| **"Usuarios" es un cajón de sastre** | Conviven ajustes personales del usuario logueado (snippets, vacaciones, 2FA) con administración de terceros (crear usuario, token de integración) **y un botón "Borrar todo" a un clic del sitio donde un auditor entra a marcar sus vacaciones** | `index.html:3335-3473`; `resetDatos()` en `:3449` |

**Menús que se solapan o se contradicen:**

- El **liquidador de tarifas SOAT vive dentro de "Consulta Normativa"** mientras existe una pantalla llamada "Tarifas". Quien busca liquidar una tarifa entra a Tarifas y no lo encuentra (`index.html:3725-3728` contra `:3195`).
- **"Importación masiva" aparece dos veces en la navegación con destinos técnicos distintos**: el menú abre un panel interno, el buscador de comandos recarga la página entera (`:2113` contra `:10846`).
- **Ctrl+K abre tres buscadores superpuestos a la vez** (tres escuchadores independientes, ninguno detiene la propagación) y la tecla "?" abre dos modales de ayuda (`:10992`, `:21689`, `:22263`). Hay 12 escuchadores globales de teclado.
- **La tecla "/" deja la aplicación bloqueada**: un manejador abre la capa con estilo en línea y la función de cierre solo quita una clase CSS — el estilo en línea gana. **Ni Esc, ni clic fuera, ni ejecutar un comando la cierran: hay que recargar la página y se pierde la glosa que se estaba redactando** (`:7178` contra `:10869`).
- **Atajos de una sola tecla que destruyen trabajo**: pulsar "n" fuera de un campo borra el dictamen en pantalla y limpia el formulario, **sin confirmación** (`:7183-7184`).
- **5 botones de exportación repartidos en 3 pantallas**; tres de ellos consecutivos en la misma fila del Historial, y el usuario solo puede distinguirlos leyendo el texto emergente (`:3020, 3021, 3022, 2736, 2478`).
- **El control de acceso por rol es cosmético**: el menú se recorta leyendo el rol de `localStorage`. Cualquiera puede reescribirlo y recuperar los 24 ítems, incluida la zona con "Borrar todo" (`:19740` y `:12844`). **La restricción real tiene que estar en el servidor**, y no es un problema estético: hay dos fugas concretas de datos del paciente que dependen de eso. (1) `GET /glosas/historial` exige estar logueado pero **no filtra por rol ni por asignación**: devuelve el nombre del paciente de todas las glosas del hospital a cualquier usuario (`glosas.py:188-236`, campo `"paciente"`). (2) El service worker cachea `/usuarios/yo` sin `Vary: Authorization` y la regla de cacheo gana sobre la que debía excluirlo (`sw.js:14` contra `:110`, resuelto en `:89-102`): en un PC compartido de cartera, el segundo gestor puede recibir el nombre, correo y rol del primero.
- **La aplicación no se puede usar en un teléfono**: el panel de trabajo es horizontal con el formulario fijo en 320 px, que solo baja a 280 px; **no existe ninguna regla que apile formulario y resultado**. En un teléfono de 390 px al dictamen le quedan ~110 px de ancho — y el instalador de la aplicación ofrece un acceso directo "Analizar nueva" que lleva justo a esa pantalla (`:840` y `:1432`).

---

### 2.5 Procesos demasiado largos que deberían ser un clic

En orden de retorno. Los cinco primeros son movimientos de horas o días, no de meses, y se pueden hacer **antes** de escribir una línea de la 2.0.

1. **Abrir la aplicación en la bandeja de trabajo, no en un formulario en blanco.** El camino de 5 clics para 100 glosas está a dos niveles de profundidad; el de 12-14 clics por glosa es el que abre por defecto (`index.html:2125` contra `:13705`). Arriba de todo debe ir el aviso de vencimientos a 24 h con valor en riesgo (`:13548`) y el botón **"Preparar el día"**.

   Sobre ese botón hay que ser exactos, porque el resto del plan lo da por vivo: **hoy no funciona.** El botón sigue en la interfaz, enterrado en el estado vacío de "Analizar" (`:2365`) —donde además desaparece para siempre en cuanto se analiza la primera glosa, porque el resultado borra ese bloque (`:16440`)—, pero al pulsarlo llama a `POST /autopilot/preparar-dia` (`:7112`) y ese router fue eliminado: `main.py:1207` dice literalmente *"autopilot: removido en la limpieza de ronda 29 (módulo sin uso real)"*. Devuelve **404** y un toast rojo. Su frecuencia de uso real es **nula, porque está roto**.

   **Decisión tomada: se resucita.** El código del navegador está intacto y describe exactamente la rutina que el coordinador hace a mano todos los días —aplicar el texto fijo a las RATIFICADAS y EXTEMPORÁNEAS pendientes, marcarlas como RESPONDIDAS y refrescar la bandeja, de forma idempotente—; falta únicamente reponer el endpoint. Es la automatización de mayor retorno por hora de trabajo de todo el producto, así que **entra en el primer paquete (A0), junto con moverla al encabezado de la bandeja**, y no espera a la 2.0.

2. **Que lo detectado se escriba solo.** El servidor ya extrae código, valores, EPS, CUPS y servicio sin gastar IA; la interfaz los pinta y los tira (`analizar.py:1032-1046` contra `index.html:21875-21891`). Rellenar los campos con eso **elimina de un golpe la mayor parte de la redigitación de la sección 2.2**.

3. **Sacar el N° de factura del acordeón "opcional" y ponerlo primero.** Un solo dato desbloquea tres automatizaciones ya construidas: conceptos de la factura, aviso de duplicado y lectura automática de soportes del disco de red (`index.html:2160-2164` contra `analizar.py:806-824`).

4. **Que el acta de conciliación cierre la glosa.** Hoy "cerrar acta" **no transiciona la glosa ni escribe el valor recuperado**: para que la plata conciliada aparezca en el tablero, el auditor debe registrar el mismo resultado **otra vez** por un camino distinto (`conciliacion.py:290-324`). Doble digitación en el punto exacto donde se mide el éxito del área.

5. **Que la ratificación de la EPS cree la conciliación sola.** El sistema tiene todos los datos y **nadie crea la conciliación automáticamente**: la transición RATIFICADA → conciliación es 100 % manual.

6. **Matar los cuadros de diálogo del navegador.** Verificado: **44 `prompt()`, 44 `confirm()` y 12 `alert()`**. Los peores están en el módulo donde se negocian millones: cerrar un acta encadena **cinco prompts** —número, fecha escrita a mano en formato `YYYY-MM-DD`, valor, resultado tecleando literalmente `ACUERDO_PARCIAL` con guion bajo, y observaciones— y **si el último no coincide exactamente, se pierde todo lo anterior** (`index.html:20480-20498`). La decisión de la EPS, dato del que dependen todas las estadísticas de recuperación, se captura escribiendo "LEVANTADA" o "RATIFICADA" a mano (`:20390`). Y "Pegar correo de EPS" pide pegar un correo completo **dentro de un cuadro de una sola línea** (`:21934`).

7. **Un solo generador de documentos, en el servidor.** Hay cuatro generadores del mismo PDF radicable; tres corren en el navegador y uno de ellos estampa un número de objeción aleatorio (ver 2.3). Solo el del servidor puede asignar un consecutivo real, trazable y repetible.

8. **Dar tablero a los bots.** Los bots de SIMED **procesaron 324 facturas y 597 objeciones en siete lotes; de los tres últimos, por $153.675.820, el Excel está listo y la subida sigue sin confirmar** (`BITACORA.md:173-181`). Ese es exactamente el problema de interfaz: el estado de esos lotes —listo, subido, vencido— **vive en un CSV en el escritorio de una PC**, y la aplicación ni siquiera sabe que los bots existen (barrido completo sobre `index.html`: 0 ocurrencias de "RPA", "Playwright" o "robot"). Nadie puede ver desde el sistema qué falta subir ni desde cuándo. La cola de trabajo del agente ya existe, tiene 6 endpoints, 3 tablas y 403 líneas de pruebas — **y ninguna pantalla**.

9. **Un botón "Exportar" con selector de formato y de alcance**, en lugar de cinco botones repartidos en tres pantallas.

---

### 2.6 Qué información falta en pantalla

Lo llamativo es que casi todo esto **ya está calculado en el servidor**. El problema no es que falte la inteligencia: es que no llega al ojo del auditor en el momento en que decide.

| Lo que el auditor necesita ver | Estado real | Evidencia |
|---|---|---|
| **Plazo restante de esta glosa** | El cálculo existe y es bueno: días hábiles con festivos colombianos, y un banner que dice "N glosa(s) vencen en 24h · Valor en riesgo: $X" con la aclaración jurídica de que el Art. 57 protege a la EPS, no al prestador. **Pero solo se pinta dentro de "Mis glosas", y la pantalla que abre por defecto es "Analizar".** Peor aún: **la pantalla de Alertas y el contador rojo del encabezado ESCONDEN las glosas ya vencidas**, porque la consulta filtra "días restantes > 0" — lo más urgente es exactamente lo que no se muestra | `recepcion_service.py:609-629`; banner en `index.html:13548-13573`; filtro en `glosa_repository.py:445`, consumido en `index.html:19681, 19693` |
| **Probabilidad real de éxito** | El número grande y más visible de la interfaz ("% de éxito") **no mide calidad**: es una tabla estática por tipo de glosa (extemporánea=99, ratificación=92, urgencia=90, tarifa=75, resto=85) más bonificaciones por longitud y por tener PDF. El propio código lo admite: *"heurística estática… las citas FABRICADAS subían el score"*. Y el indicador de "riesgo de ratificación" que se muestra al lado **no consulta la base de datos ni una sola vez**: sale de constantes "según histórico nacional" y una lista fija de 5 EPS difíciles que no son las del HUS. Encima hay **hasta 6 semáforos simultáneos** sobre el mismo dictamen, con escalas distintas | `glosa_service.py:7098`, comentario en `:3551-3554`; `riesgo_ratificacion.py:17, 38-44`; seis escalas listadas en la auditoría del subsistema de calidad |
| **Historial de esta EPS con este código** | **Existe y está bien pensado**: la ficha de EPS muestra tasa histórica, tono recomendado y códigos top mientras el auditor redacta, y hay win-rate por par (EPS, código) con tendencia contra el periodo anterior. Defecto a corregir: la cifra "Recuperado" de esa ficha está **inflada** por una fórmula que suma el valor objetado completo de toda glosa levantada sin valor registrado | ficha en `glosas_stats.py:4057+` pintada en `index.html:11927-11960`; win-rate en `analytics.py:276-405` usado en `:18302`; fórmula inflada en `glosas_stats.py:4103` |
| **¿Hay una respuesta ganadora anterior para este caso?** | **El sistema sabe calcularla y el auditor nunca la ve.** El buscador de precedentes propios (BM25 sobre casos reales del hospital) funciona, pero `GET /glosas/casos-similares/{id}` **no tiene una sola referencia en la interfaz**. Y las 52 plantillas que sí se le presentan a la IA rotuladas como *"respuesta que logró levantar la glosa"* son **semillas: 0 aprendidas, todas con 0 usos** (verificado en la base) | `rag_service.py`; endpoint huérfano en `glosas.py:4414`; rótulo en `glosa_service.py:4770` |
| **¿Este dictamen pasó el control de calidad?** | El Quality Gate es la mayor inversión de ingeniería del sistema (1.748 líneas de código + 1.151 de pruebas) y **su resultado es invisible: 0 menciones en la interfaz**. Cuando escala a revisión humana, el aviso llega como texto plano metido dentro del borrador | barrido de "quality-gate" sobre `index.html` = 0 |
| **¿Qué le falta a este dictamen para ser más fuerte?** | **Sí existe y es lo mejor del producto**: el panel de confianza con desglose accionable ("subí el PDF del contrato en Tarifas → Subir PDF") y la verificación de citas legales que marca las normas inexistentes con severidad ALTA. Es lo que separa este producto de pegarle la glosa a un chatbot. Solo hay que dejarlo como **la única** señal, en vez de una entre seis | `index.html:16220-16290`; `citation_verifier.py` |

Falta señalar tres capacidades más que están construidas y **solo existen en el camino de lote**, invisibles para quien responde una glosa suelta: "Conversar con la IA sobre este dictamen", "Escuchar el dictamen" y el semáforo de confianza (`index.html:9971, 9972, 9986`).

---

### 2.7 Veredicto

**La aplicación no es difícil de usar porque le falten funciones: es difícil de usar porque el camino barato está enterrado, el camino caro abre por defecto, y una parte visible de los botones da acuse de éxito sin haber hecho nada —lo que convierte cada acierto real del sistema en algo que el auditor tampoco puede creerle.** El caso extremo es "Preparar el día": la automatización de mayor retorno del producto sigue dibujada en la pantalla y lleva meses devolviendo 404.

---

Now I have everything I need. Here is the corrected section.

## 3. Rearquitectura: cómo se construye SINAC OS sobre lo que ya existe (Fase 3)

### 3.1 Principio de la migración: no se reescribe, se reorganiza

El sistema actual tiene 100.259 líneas en `app/`, 20.098 en `tools/` y **26.728** en `static/` (medido en el repositorio). La tentación natural, después de leer una auditoría con **142 duplicaciones y 166 hallazgos de UX**, es tirar todo y empezar de nuevo. **Esa sería la decisión más cara del proyecto**, y la auditoría explica por qué: lo que está mal es el *orden*, no el *conocimiento*.

El inventario de lo que ya funciona y no se puede reconstruir con dinero ni con tiempo —las reglas de defensa 8.x, las 32 redes finales anti-alucinación, el corpus normativo con texto literal, la puerta de entrada del DGH, los entregables que efectivamente se radican, la ficha contractual de las EPS, la red de pruebas y el conocimiento de portal de los bots— está en **§1, «Qué está sano y no hay que tocar»**. Aquí se da por leído: esta sección parte de que ese activo se conserva.

**La decisión: se reescriben tres cosas y solo tres.** (1) La interfaz — `static/index.html` con 23.125 líneas, 554 funciones en un único ámbito global y 0 componentes no es modularizable, es reemplazable. (2) El esquema de datos — hay que crear el Expediente, sacar los contratos del código y unificar los estados. (3) El hilo que une las piezas — el Orquestador, que hoy no existe. **Todo lo demás se mueve de lugar, se fusiona o se borra.**

El volumen exacto de lo que desaparece —bloque por bloque, con el total de líneas y el porcentaje del sistema— está en **§5.7**, y lo que **no** se borra aunque lo parezca (empezando por la cola `/lotes`, que no se elimina: se le da pantalla) está en **§5.8**. Ninguna de las dos cuentas se repite aquí.

### 3.2 Mapa del sistema nuevo: de dónde sale cada pieza

Este es el punto que hay que ver antes de aprobar meses de trabajo: **casi todo el SINAC OS ya está construido y disperso.** De los 8 agentes del blueprint, 7 tienen su núcleo escrito hoy. De los 9 módulos, 8 tienen pantallas que absorber. Lo que falta es el pegamento y el registro.

```
╔═ CAPA 1 · LOS 9 MÓDULOS — lo único que el auditor ve
║   Inicio · Bandeja Inteligente · Expedientes · Conciliaciones · Contratos
║   Biblioteca · Automatización · Herramientas · Administración
║
║   SALE DE: static/index.html (23.125 l, 26 pantallas) + sinac-ux.js (331 l)
║            + sinac-analizar-pro.js (332 l) + sinac-asistente.js (227 l)
║   ESTADO:  única pieza que se reescribe ENTERA — 554 funciones en un solo
║            ámbito global, 2.216 estilos en línea, 288 !important
╚══════════════════════ ▼ una sola API tipada (hoy: 276 fetch sueltos, y 5
                          apuntando a routers borrados en mayo de 2026)

╔═ CAPA 2 · IA CENTRAL + ORQUESTADOR
║   intención + contexto → plan de pasos → invoca agentes → registra → explica
║
║   SALE DE: asistente_maestro.py — loop de tool-use VIVO, 9 herramientas que
║            consultan datos reales, 6 turnos, errores escritos para un humano
║            ia_tools._exec_* — cláusula de contrato, glosa similar, tarifa,
║            norma (ya funcionan, hoy solo los usa el chat)
║            routing_complejidad.py — la elección de modelo YA unificada
║            progreso_analisis.py — narración SSE de lo que de verdad pasa
║   FALTA:   el planificador de pasos y el registro del plan en el expediente
╚══════════════════════ ▼

╔═ CAPA 3 · LOS 8 AGENTES — uno por función, nunca un agente gigante
║   Glosas ········ glosa_service · glosa_ia_prompts · quality_gate ·
║                   citation_verifier · texto_fijo · dictamen_directo
║   Radicación ···· radicar_facturacion (perfil JSON + 12 entidades) ·
║                   excel_radicable · exportar_dgh · marcar-radicada
║   Expedientes ··· conceptos_glosa · dictamen_versiones · audit_log ·
║                   soportes_autodiscovery · rutas_factura · papelera
║   Conciliación ·· conciliacion.py (ciclo bilateral + acta con mérito
║                   ejecutivo) · conciliador_ia (contraargumentos EPS)
║   Documental ···· pdf_service · pdf_to_images · extractor_factura ·
║                   extractor_folios · tarifas_excel_parser · gemini (OCR)
║   Evidencias ···· pantallazos de los bots · evidencias_a_word ·
║                   dictamen_versiones · papelera con snapshot
║   Servidor ······ jumpbox_sync · agente_lotes · AgenteLotes.pyw (doble
║                   clic) · indexador de soportes · _safe_join
║   Constructor ··· NO EXISTE una sola línea
╚══════════════════════ ▼

╔═ CAPA 4 · BASE DE CONOCIMIENTO — lo que lee la IA y lo que lee el auditor
║   son el MISMO texto (hoy no lo son)
║
║   SALE DE: normativa_completa.py (131 normas con texto literal) ·
║            catalogo_glosas.py (Res. 2284/2023 con "Defensa central" por
║            código) · clausulas_contrato (PDF → Claude → cláusula con
║            página) · plantillas_gold (52 filas) · rag_service (BM25 sobre
║            dictámenes propios) · banco_respuestas_hus (24 del equipo)
║   FALTA:   fusionar los 4 catálogos de normas que hoy se contradicen
╚══════════════════════ ▼

╔═ CAPA 5 · DATOS — EL EXPEDIENTE ÚNICO POR FACTURA
║   SALE DE: historial · conceptos_glosa · dictamen_versiones · audit_log ·
║            comentarios_glosa · conciliaciones · rutas_factura · índice de
║            soportes · lotes/facturas_lote/tareas_lote
║   FALTA:   la entidad que los une. Hoy NO EXISTE (ver 3.6)
╚═══════════════════════════════════════════════════════════════════════════
```

### 3.3 De qué está hecho cada agente de SINAC OS

| Agente | Servicios actuales que lo componen | Qué falta construir | Esfuerzo |
|---|---|---|---|
| **Glosas** | `glosa_service.py` (8.981 l) · `glosa_ia_prompts.py` (3.050 l) · `quality_gate/` (1.748 l + 1.151 de tests) · `citation_verifier.py` · `routing_complejidad.py` · `multi_codigo.py` · `few_shot_gold.py` · `auditor_glosa.py` · `confidence_scorer.py` · los caminos sin IA (texto fijo, plantilla, `dictamen_directo.py`) | Partir `analizar()` — un método de 2.800 líneas (`:4299-7097`) con **73 `except` silenciosos dentro de ese método** — en 9 etapas explícitas y testeables. **Un** motor de checks (hoy placeholders, cifras y longitud están implementados 3 y 4 veces con criterios incompatibles). **Un** score (hoy 6 escalas sin reconciliar; la más visible, el "% de éxito", es la única que no mide calidad). Que los 4 caminos de lote usen el mismo pipeline (hoy la misma glosa da distinta calidad según por qué puerta entró) | **Alto** — es el más grande del plan, pero con red: 142 archivos en `tests/test_services/` permiten migrar red final por red final |
| **Radicación** | `tools/radicar_facturacion.py` (1.192 l, **ya implementa el patrón perfil-declarativo + motor genérico**, con `data/perfiles_radicacion.json` de **12 entidades**) · `excel_radicable.py` · `exportar_dgh.py` (26 columnas canónicas) · `marcar-radicada` con evidencia auditable (`glosas.py:3617-3702`) | Consecutivo **real** persistido en base de datos: hoy el documento que se radica ante la EPS lleva un "Nº OBJECIÓN" generado con `Math.random()` (`static/index.html:18097`, impreso en `:18192`) y cada reimpresión da un número distinto. Rutas parametrizables (hoy los artefactos se escriben en rutas relativas al directorio desde el que se corrió el bot). **Generación de Word: no existe en el backend** (solo `tools/evidencias_a_word.py`, para pantallazos). **Y el DGH tiene dueño aquí**: el bot DGH que §5.4 retira no deja hueco, porque su reemplazo —un adaptador de dos direcciones que exporte al DGH y lea de vuelta el estado contable de la glosa— queda asignado a este agente, no a un script suelto | **Medio** — el contrato de perfil ya existe y funciona; hay que extenderlo, no inventarlo |
| **Expedientes** | `conceptos_glosa` (el único modelo que representa bien el dominio, con idempotencia real por `oid_dgh`) · `dictamen_versiones` con diff en texto plano · `comentarios_glosa` · `audit_log` · `soportes_autodiscovery_service.py` (indexa hasta 144k archivos) · `rutas_factura.py` · `papelera.py` | La entidad Expediente (ver 3.6). Servir el archivo: **no hay un solo `FileResponse` en `soportes.py`** — se indexan 144k archivos para terminar mostrando la ruta como texto y un botón "📋 Copiar" para pegarla en el explorador de Windows. Versionar el dictamen en los 19 puntos donde se escribe, no en 3 | **Alto** — es el cambio estructural de la fase |
| **Conciliación** | `conciliacion.py` (609 l) + `ConciliacionRecord` con ciclo bilateral (contra-respuesta EPS → postura HUS → acta) · acta SINAC multi-glosa con cláusula de mérito ejecutivo (Art. 422 CGP) · `conciliador_ia.preparar_audiencia` (contraargumentos probables y valor mínimo aceptable, **sí usado** por la UI) | Que cerrar el acta **cierre la glosa y sume a la plata recuperada en una sola acción**: hoy `cerrar-acta` (`conciliacion.py:290-324`) no transiciona nada, y el auditor tiene que registrar el resultado otra vez. Reemplazar los 5 `prompt()` encadenados de `panelCerrarActa` (si escribe "ACUERDO PARCIAL" con espacio en vez de guion bajo, pierde los cinco). Participantes como filas, no como texto (un acta legal cita personas). Traer adentro el CLI del Dispensario (727 l corriendo en el PC del auditor) | **Medio** — el modelo de datos ya es de lo mejor del sistema |
| **Documental** | `pdf_service.py` · `pdf_to_images.py` · `extractor_factura.py` (293 l, determinístico) · `extractor_folios.py` (120 l — extrae folio, fecha y médico firmante: **ataca directamente el mecanismo por el que las EPS ratifican, que es la vaguedad**) · `extractor_clausulas_contrato.py` (PDF → Claude → cláusula literal con página) · `tarifas_excel_parser.py` (905 l, formatos reales del negocio) · `gemini_service` (OCR de foto de glosa) | **Dejar de truncar el expediente**: hoy cualquier PDF de más de 4 páginas llega a la IA como ~7.050 caracteres (3.000 del inicio, 2.000 del medio, 2.000 del final) — una historia clínica de 200 páginas entra como 7 KB, y el camino automático limita además a 3 archivos × 5.000 caracteres. Un solo `DocumentReader` (hoy hay **5 caminos** para leer un PDF con 5 políticas distintas, uno de ellos un *monkey patch* aplicado en producción porque el archivo era "demasiado grande para editarse"). Correo y ZIP (el ingestor IMAP quedó en esqueleto) | **Medio-alto** — el truncado es, según la auditoría, el 40 % del valor de este subsistema |
| **Evidencias** | Captura del cartel de cierre en los bots (`responder_glosas_coosalud.py:1196-1204`; SIMED captura con el diálogo del portal visible, `:342-350`) · `evidencias_a_word.py` (232 l, rotula cada página con el número de factura) · `dictamen_versiones` · snapshot de papelera | Que la evidencia **suba sola al expediente**: hoy queda en una carpeta del escritorio de una PC y el consecutivo se pide por chat. Numeración automática. Un solo generador con `--formato pdf/docx` (hoy son dos scripts y el de PDF no rotula la factura, que es justo lo que lo haría radicable) | **Bajo-medio** — hay poco por escribir, mucho por conectar |
| **Servidor** | `jumpbox_sync.py` (566 l, integrado con la autenticación del backend) · `agente_lotes.py` (345 l: cola reclamable, reporte incremental, validación anti *path-traversal*, manejo del WAF) · `AgenteLotes.pyw` (**doble clic, cero PowerShell** — la única concesión de usabilidad del repositorio) · indexador de soportes · `_safe_join` con tests | **Un solo Agente HUS**: hoy son dos procesos distintos, con dos tokens, dos configuraciones y dos formas de instalar, en la misma máquina. Pantalla de control: barrido completo de la interfaz → **0 menciones de bots, RPA, Playwright o cualquier script de `tools/`**. El auditor no puede lanzar, ver, detener ni auditar un bot desde la aplicación. Detectar duplicados / renombrar / respaldar como acciones del agente | **Medio** — el mecanismo está probado; falta unificarlo y darle tablero |
| **Constructor** | Nada. No existe una sola línea | Registro de plugins, contrato de agente, generador de código, documentación automática | **Decisión: no se construye en Fase 3.** En Fase 3 se define **solo el contrato de plugin** —cómo se declara un agente, qué recibe, qué devuelve, cómo registra trazabilidad— y se obliga a los otros 7 agentes a cumplirlo. Construir un generador de agentes antes de que exista un solo agente bien formado es construir sobre una forma que todavía no se conoce. El Constructor es Fase 6-7 del roadmap |

**Orden de ejecución recomendado:** Expedientes → Glosas → Documental → Conciliación → Radicación/Evidencias/Servidor → (Constructor, fuera de fase). El Expediente va primero porque es el suelo: sin él, la evidencia del bot, la versión del dictamen, el acta y la trazabilidad no tienen dónde aterrizar, y cualquier trabajo hecho antes hay que rehacerlo.

### 3.4 El Orquestador: qué es exactamente y qué NO es

**Qué NO es** (cuatro confusiones que hay que cerrar antes de escribir una línea):

1. **No es un chat.** El chat ya existe (`asistente_maestro.py`) y seguirá existiendo como *una* de las entradas al Orquestador, no como el Orquestador.
2. **No ejecuta.** El blueprint es explícito (§5) y la auditoría explica por qué importa: hoy hay 12 puntos del código que llaman directo a la API de Anthropic y **solo uno registra el costo** (`glosa_service.py:8456`). El Orquestador es el único autorizado a invocar un modelo, y por eso es el único lugar donde hay que medir el gasto.
3. **No decide jurídicamente.** Arma el plan; el dictamen lo produce el Agente Glosas y lo firma el auditor.
4. **No puede nacer detrás de un interruptor.** El Quality Gate (1.748 líneas de código + 1.151 de tests) está apagado por defecto en el flujo principal; `TOOL_USE_HABILITADO` viene en `'0'`; `MULTI_AGENT_HABILITADO` también, y quedó con 1 de 3 agentes implementados. **Regla: el Orquestador nace encendido y sin bandera, o no se construye.** Tres inversiones grandes del sistema actual murieron esperando que alguien encendiera el interruptor.

**Su contrato, en cinco partes:**

| # | Parte | Qué significa en la práctica |
|---|---|---|
| 1 | **Entrada** | Una intención en español ("responder esta glosa", "preparar la conciliación de la factura HUS123456") + el contexto de trabajo: quién lo pide, qué expediente está abierto, qué documento está mirando |
| 2 | **Plan** | Una lista ordenada de pasos, cada uno con agente, acción, insumos y criterio de éxito. Si el plan tiene costo de IA o efecto irreversible (radicar, enviar correo, borrar), **se muestra antes de ejecutar** y el auditor aprueba |
| 3 | **Ejecución** | Invoca agentes uno por uno. Cada agente devuelve resultado + evidencia + costo. Si un paso falla, el plan se detiene con el motivo en español, no con una traza de Python (hoy el gestor lee literalmente el texto de la excepción: `recepcion_service.py:1203`) |
| 4 | **Registro** | Cada paso entra en la trazabilidad del expediente: quién pidió, qué plan, qué agente corrió, qué devolvió, qué modelo, cuánto costó. Esto es lo que hoy no ocurre: `ia_auditora_proactiva.py:183` sobrescribe el dictamen —el documento legal que el hospital le opone a la EPS— **sin crear versión ni registro de auditoría** |
| 5 | **Salida** | Resultado + explicación en español + los pasos ejecutados. El auditor puede ver por qué el sistema hizo lo que hizo |

**El ejemplo del blueprint (§6), mapeado a lo que ya corre hoy:**

| Paso del blueprint | Agente | Qué lo hace HOY | Estado real |
|---|---|---|---|
| Leer PDF | Documental | `pdf_service.extraer` + `pdf_to_images` | Existe — pero trunca a ~7.050 caracteres |
| Extraer datos | Documental | `extractor_factura.extraer_de_texto` + `POST /analizar/preview` | Existe — el frontend **muestra** valor objetado, código, CUPS y servicio, y **los tira**: no rellena ningún campo (`static/index.html:21875-21891`) |
| Buscar contrato | Glosas | `get_contrato` + `contexto_contractual_enriquecido` (920 l) | Existe — pero lee un diccionario de Python que tiene prioridad sobre la base de datos (`glosa_ia_prompts.py:383-384`) |
| Buscar normas | Base de Conocimiento | `normativa_completa.py` (131 normas con texto literal) | Existe — pero el auditor consulta **otro** catálogo, que comparte solo 20 nombres con este |
| Consultar historial | Glosas | `calibracion_dificultad` (tasa real del par EPS+código) | Existe y es gratis |
| Consultar respuestas similares | Glosas | `rag_service` (BM25 sobre dictámenes propios) + `few_shot_gold` | Existe — pero un `return` prematuro deja fuera de juego a los precedentes propios para las 5 familias de glosa más comunes |
| Construir respuesta | Glosas | `glosa_service.analizar()` | Existe (2.800 líneas en un método) |
| Generar Word | Documental | — | **No existe.** Es el único paso del ejemplo sin código |
| Exportar PDF | Documental | `services/dictamen_pdf.py` (membrete, sello, línea de firma) | Existe — hay que borrar los 3 generadores del navegador que compiten con él |
| Guardar expediente | Expedientes | `GlosaRecord` + `dictamen_versiones` | Parcial: versiona 3 de los 19 puntos donde se escribe el dictamen |
| Actualizar historial | Glosas | `aprendizaje_feedback.aprender_de_decision_eps` | Existe pero el lazo **no gira**: en la base hay 52 plantillas Gold, las 52 de semilla, 0 aprendidas, todas con `usos=0` |

**Diez de los once pasos ya tienen código escrito.** Lo que falta no es capacidad: es el hilo que los une, la garantía de que se ejecutaron y el registro de qué hizo cada uno. Eso es exactamente el Orquestador, y por eso es la pieza de mayor retorno de toda la rearquitectura.

### 3.5 Nueva navegación: de 26 pantallas sueltas a 9 módulos

**Antes de leer la tabla: 9 módulos no son 9 pantallas.** Los 9 módulos son las **entradas del menú**; adentro contienen **unas 14 pantallas**, porque varios módulos tienen dos o tres vistas (Expedientes: lista, expediente y análisis; Automatización: importación, bots y cola de lotes; Contratos: contratos y tarifas). Cuando otras secciones de este documento hablan de "de 26 a 14" se refieren a las pantallas; cuando esta habla de 9, se refiere al menú. Es la misma reforma contada por sus dos extremos: **el auditor pasa de 26 destinos sueltos a 9 puertas con 14 vistas ordenadas detrás.**

| Módulo nuevo | Pantallas actuales que absorbe | Pantallas que desaparecen |
|---|---|---|
| **1. Inicio** (Centro de Operaciones) | `p-mando` (2879) · `p-dashboard` (2382) · **"Preparar el día" resucitado**: hoy el botón (`static/index.html:7108`) llama a `POST /autopilot/preparar-dia` en `:7112`, y ese router fue borrado (`app/main.py:1207`: *"autopilot: removido en la limpieza de ronda 29"*), así que **devuelve 404** — a lo que se suma que está enterrado en el estado vacío de Analizar y **desaparece para siempre en cuanto se analiza la primera glosa**. Su uso hoy es **nulo, porque está roto**. Es la automatización de mayor retorno del producto —un clic aplica texto fijo a RATIFICADAS y EXTEMPORÁNEAS y las saca de la bandeja— y se **reconstruye** como acción principal y permanente de Inicio | `p-cobranza-live` (2814: 33 líneas, 1 botón) · `p-resumen-mes` (2847: 32 líneas, 1 botón) · la barra de pestañas `pintarRepTabbars` (12404) que se agregó **en vez** de consolidar, cuando el propio código documenta el pedido: *"Feedback Yesid: 4 botones que sacan la misma info → consolidar en uno"* (12386-12390) |
| **2. Bandeja Inteligente** | `p-mis-glosas` (2665) con sus 8 vistas guardadas y sus acciones sobre 500 glosas — **el mejor trabajo del frontend** · el banner de vencimientos con valor en riesgo (13548) | `p-alertas` (3088: dos líneas de markup, sin título, sin filtros, **cero botones**, ocupando un ítem del menú principal) · 6 de las 7 superficies que hoy responden "¿qué se vence?" |
| **3. Expedientes** | `p-analizar` (2125) pasa a ser una vista **dentro** del expediente · `p-historial` · la caja de conceptos por factura (9461) · el panel de soportes (18449) · versiones · comentarios | El formulario en blanco como pantalla de entrada por defecto: hoy la aplicación abre en el camino **más caro** (12-14 clics por glosa) mientras el barato (bandeja → seleccionar todas → generar en lote, 5 clics para 100 glosas) está a dos niveles de profundidad |
| **4. Conciliaciones** | `p-conciliacion` (3474) · acta SINAC (3527) · el CLI del Dispensario (`tools/asistente_conciliacion_dispensario.py`, 727 l) entra a la plataforma | El botón "🧠 Simular" (20424) que llama a una ruta inexistente y **siempre** devuelve 404 · el tab de Conciliación oculto con `display:none` (1979) — el final del embudo escondido |
| **5. Contratos** | `p-contratos` + metadatos (3129) · `p-tarifas` (3195) · el liquidador SOAT, que hoy vive dentro de "Consulta Normativa" (3725) mientras existe una pantalla llamada "Tarifas" | La edición placebo: hoy editar el contrato de una de las 14 EPS principales desde la pantalla **no cambia lo que la IA cita**, porque el catálogo en código tiene prioridad. El auditor cree que actualizó y el dictamen sigue citando lo viejo |
| **6. Biblioteca** | `p-consulta-normativa` (3673), ahora leyendo el corpus con **texto literal** | Las ~950 líneas de `CATALOGO_NORMAS` dentro del router, que devuelven como "texto" de cada norma la concatenación de sus palabras clave: **hoy el auditor recibe menos información que la IA** |
| **7. Automatización** | `p-importacion-masiva` (4153) · `importar-recepcion.html` (539 l, hoy una página aparte) · y **por primera vez**: los bots (0 menciones en toda la interfaz) y la cola de lotes (6 endpoints, 3 tablas, 403 líneas de tests, **ninguna pantalla**), que **no se borra: se le da tablero**, según decide §5.8 | `static/importar-masiva.html` (336 l) · la doble puerta de importación con el mismo nombre y distinto destino (sidebar 2113 vs. paleta 10846) |
| **8. Herramientas** | Multi-concepto (3767), Detector en masa (3797) y Simulador (3832) — **existen completos, con endpoints vivos, y ningún usuario puede llegar a ellos** · los 5 botones de exportación repartidos en 3 pantallas se vuelven uno con selector de formato y alcance | `p-salud-total` (3984): ítem de primer nivel del menú, habilitado explícitamente para el rol AUDITOR, cuyos dos únicos botones devuelven 404 desde mayo de 2026 · los 4 archivos `.cmd` de doble clic (1.010 líneas de batch de Windows, uno de ellos renombra PDFs a extensión `.cmd`) |
| **9. Administración** | `p-usuarios` (3335) partido en dos: los ajustes personales (snippets 3378, vacaciones 3396, segundo factor 3408) se van a "Mi cuenta", dentro de Inicio · **aparece por primera vez el vault de credenciales de portales**, que está bien construido y cifrado y no tiene pantalla — por eso el equipo sigue guardando esas claves en un Excel | El botón "Borrar todo" (`resetDatos`, 3449) a un clic de distancia de donde un auditor entra a marcar sus vacaciones |

**Decisión sobre el segundo factor (2FA): se conserva, y pasa a ser obligatorio para el rol SUPER_ADMIN.** En un sistema que guarda nombre de paciente y dictámenes con historia clínica adentro, quitar el segundo factor no simplifica el menú: baja el piso de cumplimiento frente a la Ley 1581/2012 justo en las dos cuentas que pueden borrar la base. Se mueve de sitio (a "Mi cuenta"), no se elimina.

**Se van sin que nada las absorba, porque están rotas a la vista del usuario:** el botón flotante de nota privada (5993, el router fue borrado: el auditor escribe su nota, pulsa Guardar y **pierde lo escrito**), los dos sistemas de comentarios (ambos inalcanzables), `sinac-asistente.js` (227 líneas que se descargan en cada visita y **nunca hicieron una sola petición** porque leen la clave del token equivocada), la barra de navegación legacy (10 botones invisibles que `tab()` sigue recorriendo en cada cambio de pantalla) y los archivos huérfanos, incluido uno sobre terapia física de paciente encamado sin ninguna relación con el dominio.

### 3.6 El Expediente único por factura: el cambio estructural más grande

**Por qué hoy no existe.** La historia de una glosa está partida en tres sitios que no se cruzan, y ninguno de los tres está completo:

- **`audit_log`** — la misma tabla se audita con **dos nombres distintos**: `tabla="historial"` en 19 puntos de escritura y `tabla="glosas"` en 11. De los doce lectores del registro, **uno solo** contempla ambos. Los otros once informes de auditoría están incompletos y nadie lo sabe. Además no existe índice por `(tabla, registro_id)`, que es exactamente el filtro de todos ellos.
- **`dictamen_versiones`** — cubre 3 de los 19 puntos donde el código escribe el dictamen. Los que **no** versionan incluyen los automáticos, que son los peligrosos: `ia_auditora_proactiva.py:183` y `auto_responder_service.py` (líneas 227, 301, 341, 460) sobrescriben el documento de defensa legal sin dejar rastro del texto anterior.
- **`comentarios_glosa`** — la única de tres tablas de comentarios que sigue viva.

Y hay un cuarto problema, más profundo: **la factura no es una entidad**. `historial.factura` es un campo de texto con valor por defecto `"N/A"`; `saldo_factura` y `valor_factura` son datos **de la factura** guardados repetidos en cada glosa. La consecuencia se paga en pesos: dos endpoints de cartera suman el saldo una vez por glosa, así que una factura con 5 glosas abiertas **reporta 5 veces su saldo**. El único que lo hace bien lo hace por un parche puntual. Y el modelo conceptualmente correcto —razonar por factura, con saldo, mora y tramos 0-30/31-60/61-90/+90— existe, pero **fuera de la aplicación**, en `tools/tablero_cartera.py`.

A eso se suma que borrar una glosa a la papelera es un `DELETE` **físico** con cuatro claves foráneas en CASCADE: se van los conceptos, todas las versiones del dictamen, los comentarios del equipo y las conciliaciones. Al restaurar vuelve solo la cabecera. El usuario cree que tiene 30 días para arrepentirse y en realidad ya perdió el trabajo.

**Qué se unifica.** El Expediente se identifica por la clave natural **NIT del pagador + número de factura**, y de él cuelgan:

| Cuelga del expediente | Viene de | Qué cambia |
|---|---|---|
| Conceptos objetados | `conceptos_glosa` | Pasa a ser la **única** fuente del detalle; se borran las 9 columnas que `historial` duplica y la rama "Fallback legacy" del endpoint por factura |
| Dictámenes y sus versiones | `historial.dictamen` + `dictamen_versiones` | Un dictamen por concepto (mata `dictamen_secciones.py`, que hoy des-concatena con expresiones regulares un HTML que el propio sistema generó) y versión obligatoria en los 19 puntos |
| Soportes | índice en memoria + `rutas_factura` | Índice persistido y **archivo servible**: el último clic que hoy falta |
| Radicación | `marcar-radicada` | Número de radicado, fecha, quién y acuse, con consecutivo real |
| Evidencia de los bots | pantallazos en el escritorio de una PC | Suben solos al expediente al cerrar el lote |
| Conciliación y acta | `conciliaciones` + participantes como filas | El acta cierra las N glosas de la factura y alimenta el tablero en una sola acción |
| Trazabilidad | `audit_log` con un solo nombre de entidad | Se puede reconstruir la historia completa |
| Cartera | saldo y valor de la factura, **una sola vez** | La cartera se calcula por factura, nunca por glosa |

**Qué habilita, en lenguaje de trabajo real:**

1. Responder *"¿qué pasó con la factura HUS123456?"* en una pantalla. Hoy hace falta cruzar a mano tres consultas que no cuadran entre sí, y el resultado no es defendible ante la SuperSalud.
2. Cerrar una factura de verdad. Hoy el botón "Marcar factura como RESPONDIDA" opera sobre el **primer** concepto: si la factura tenía 43 objeciones, quedan 42 abiertas y el auditor cree que cerró todo.
3. Que los indicadores cuadren. La cartera deja de multiplicarse por el número de glosas.
4. Que el bot devuelva el resultado al sistema. Hoy, para SIMED —el flujo de más volumen— los bots procesaron **324 facturas y 597 objeciones en siete lotes** y ese resultado vive en un CSV en el escritorio de una PC: la aplicación no sabe nada. De los tres últimos lotes, por **$153.675.820**, el Excel está listo y **la subida sigue sin confirmar** — y ese estado tampoco está en ninguna pantalla, sino en la bitácora y en la cabeza de quien corrió el bot. Con el Expediente, "Excel generado" y "radicado con acuse" son dos estados distintos del mismo expediente, visibles sin preguntarle a nadie.
5. Un expediente exportable, con todo dentro, el día que llegue una auditoría externa o una acción de la SuperSalud.

### 3.7 Nueva estructura de datos: las siete decisiones que exige SINAC OS

| # | Decisión | Situación hoy | Qué cambia para el auditor |
|---|---|---|---|
| 1 | **Contratos fuera del código y con vigencia histórica** | El diccionario `CONTRATOS_HUS` (`glosa_ia_prompts.py:59-299`) tiene prioridad declarada sobre la base de datos (`:383-384`); de las 17 columnas de la tabla `contratos`, **15 están vacías en las 13 filas existentes**; y la clave primaria es el nombre de la EPS, así que **no cabe un otrosí** | Renegociar una tarifa deja de ser un despliegue de software. Y el motor puede preguntar *"¿qué contrato regía el día de la prestación?"*, que es la pregunta jurídica correcta y hoy no tiene respuesta |
| 2 | **Un concepto por fila** | `historial` duplica 9 columnas de `conceptos_glosa` y el endpoint por factura tiene dos ramas para el mismo dato, una rotulada por el propio código como *"Fallback legacy"* | Exportar al DGH, responder por factura y analizar por CUPS se simplifican solos |
| 3 | **Un catálogo de estados, una máquina** | Dos columnas de estado (`estado`, `workflow_state`) escritas por **tres** máquinas, una de ellas sin validar ninguna transición. Y la constante que define "glosa cerrada" está **copiada 117 veces** en tres versiones incompatibles: una glosa RATIFICADA cuenta como cerrada en 13 pantallas y como abierta en las otras | Los totales de dos pantallas dejan de contradecirse. **Decisión tomada, no delegada: RATIFICADA cierra el caso y cuenta como derrota.** Sale de la cartera defendible (deja de sumar como recuperable), resta en la tasa de éxito y desaparece de la bandeja; si el hospital insiste, eso abre una **conciliación**, que es otro estado con su propio expediente. Una sola definición, escrita una sola vez, porque hoy la respuesta depende del endpoint que se consulte |
| 4 | **Pagador como entidad, con NIT** | La identidad de la EPS se resuelve en 4 implementaciones distintas, y 4 tablas de normalización devuelven claves diferentes para la misma entidad ("FAMISANAR" vs "FAMISANAR EPS"). La búsqueda de tarifa usa `ILIKE '%eps%'`, que anula el índice y puede cruzar tarifas entre EPS de nombre parecido | Se acaba el riesgo de aplicar la tarifa de una EPS a otra — que en un dictamen es munición gratis para la contraparte |
| 5 | **Trazabilidad completa** | Un solo nombre de entidad en el registro de auditoría + el índice `(tabla, registro_id)` que hoy no existe + versión obligatoria del dictamen + borrado lógico real (`eliminado_en`) en vez del `DELETE` físico con CASCADE | El auditor deja de poder abrir mañana una glosa y encontrar un texto que él no escribió, sin poder recuperar el suyo |
| 6 | **Protección del dato del paciente (PHI): en reposo y en el acceso** | El sistema **declara que cifra** (`sistema.py:147` publica `"cifrado_fernet"` y lo lista como capacidad) y `cifrado.py` **no tiene un solo importador en todo el repositorio**: nombre del paciente, texto crudo de la glosa, dictamen y observación de la EPS se guardan en claro. Y el cifrado en reposo no es el único agujero: `GET /glosas/historial` (`glosas.py:188-236`) devuelve el nombre del paciente de **todas** las glosas del hospital sin filtro por rol ni por asignación, mientras el endpoint vecino (`glosas.py:1633`) sí filtra; y el service worker cachea `/usuarios/yo` sin `Vary: Authorization` (`sw.js:14` contra `:110`), de modo que en un PC compartido de cartera el segundo gestor puede recibir los datos del primero | Ante la Ley 1581/2012, una afirmación falsa de cumplimiento es **peor** que no cifrar. **Decisión: se cifran esos cuatro campos con el patrón que ya funciona en el sistema** — `credenciales_vault.py`: Fernet obligatorio que no degrada a texto plano, motivo obligatorio para revelar, registro de cada acceso. No hay tercera vía. Y los otros dos agujeros se cierran **en la misma fase, no después**: filtro por propietario y por rol en todo listado que devuelva `paciente`, empezando por `/glosas/historial`, y ninguna respuesta autenticada en la caché del service worker |
| 7 | **Migraciones de verdad** | El esquema se modifica **al arrancar la aplicación**, con 460 líneas de `ALTER TABLE` envueltas en `try/except` que hacen rollback y siguen. Si un ALTER falla en producción, la app arranca igual con un esquema distinto al que el código espera, y el fallo aparece más tarde como un error de consulta sin relación visible con la causa | Un despliegue que falla se entera en el despliegue, no tres días después en una pantalla del auditor |

Además, el esquema baja **de 37 tablas a unas 25** sin perder una sola función que alguien use: **8 tablas —el 22 % del esquema— no tienen ninguna referencia en el código** y se materializan igual en cada arranque, y hay tres pares redundantes (`plantillas` con 0 filas contra `plantillas_gold` con 52; dos tablas que registran lo mismo sobre importaciones; tres modelos de comentarios de los cuales dos están muertos).

### 3.8 Base de Conocimiento: un solo corpus, consultable por la IA y por el auditor

**Qué se indexa y de dónde sale:**

| Qué | Sale de | Qué se elimina o fusiona |
|---|---|---|
| **Normas** | `normativa_completa.py` — 131 normas **con el texto literal de cada artículo**, que es lo que permite citas verificables | Los otros tres catálogos: `normativa.py` (~35 normas con resúmenes), `CATALOGO_NORMAS` (~950 líneas dentro de un router, con solo 20 nombres en común con el corpus real), el índice TF-IDF de `rag_normativa` y el grafo detrás de una bandera apagada. **Un solo validador**: `citation_verifier`, el único que distingue norma inexistente / artículo fuera de norma / cita literal falsa |
| **Contratos y cláusulas** | `ClausulaContrato` (extraída del PDF por Claude, con tema y **número de página**) + contratos + `tarifas_contratadas` + tarifas oficiales y UVB | El diccionario en Python, el segundo diccionario que siembra la base y el tercer catálogo por EPS (`perfil_eps.py`) se funden en **una** ficha de pagador |
| **Respuestas y precedentes** | `plantillas_gold` (52 filas) + `banco_respuestas_hus` (24 respuestas del equipo jurídico) + `rag_service` (BM25 sobre los dictámenes propios del hospital) | Una sola tabla con columna de origen (SEMILLA / MANUAL / GANADA) y **un solo selector con orden explícito**: precedente propio ganado → Gold aprendida → banco del HUS. Hoy el orden está exactamente invertido, y hay **tres** sistemas inyectando ejemplos en el mismo prompt con instrucciones contradictorias ("COPIA VERBATIM" contra "no copies literalmente") |
| **Reglas de defensa** | Las reglas 8.x del prompt maestro · `clausulas_anti_rebatimiento.py` · `defensa_clinica.py` · las anotaciones "Defensa central" por código de `catalogo_glosas.py` · las listas de "qué evitar" por familia (*"T-1025/2002 NO aplica a controversia tarifaria"*) | Nada se pierde: **todo migra a datos versionados y editables**. Hoy corregir una regla exige programador y despliegue, y la prueba son las 33 rondas de parches documentadas en los comentarios del código |
| **Documentos del expediente** | Índice de soportes (hasta 144k archivos, hoy en memoria con caducidad de 6 horas y reconstrucción diaria a las 2 AM que no cuadran entre sí) | Índice persistido con búsqueda por texto, actualización incremental al subir y reconstrucción como trabajo nocturno |
| **Correos, actas, conciliaciones** | Hoy fuera del sistema | Entran con el Expediente (3.6) |

**Las tres reglas que unifican todo esto:**

1. **Ningún dato de conocimiento vive en un archivo `.py`.** Vive en la base de datos o en un JSON versionado, editable por la coordinación sin despliegue. La única excepción justificada es la transcripción taxativa de una resolución, que no cambia. El modelo a seguir ya existe dentro del sistema: `few_shot_gold` es el único módulo cuyo conocimiento **crece solo**, aprendiendo de resultados reales de la base sin tocar código.
2. **Un solo índice y un solo validador de citas.** Hoy hay tres validadores con tres criterios y, por tanto, con puntajes potencialmente contradictorios sobre el mismo dictamen.
3. **Lo que lee la IA es lo mismo que lee el auditor.** Criterio de aceptación de la fase: cualquier norma, cláusula o plantilla que el motor cite debe poder abrirse en un clic, con su texto literal y su página; y el sistema nunca cita algo que el auditor no pueda ver. Hoy pasa lo contrario — el auditor puede encontrar en la biblioteca una norma que el validador de citas marcará como inexistente en el dictamen.

---

## 4. Matriz de funciones (Fase 4)

Esta matriz convierte los 304 módulos técnicos del digest en **90 funciones de nivel usuario**: cosas que usted puede decidir mantener, cambiar o borrar sin saber programar. Están agrupadas en los 9 módulos del blueprint (§8) más dos transversales que el propio blueprint define como piezas separadas: **IA Central / Orquestador** (§5-§6) y **Motor de Glosas** (el agente Glosas, §7).

**Resumen ejecutivo.** De las 90 funciones: **21 se mantienen** (son el capital del hospital: reglas de defensa, parsers de Excel del DGH, verificador de citas, bandeja priorizada), **30 se modifican**, **19 se fusionan** (versiones duplicadas de lo mismo), **15 se eliminan** y **5 se automatizan**. **23 son P0**: se hacen antes de escribir una línea de la 2.0, porque hoy cuestan plata, plazos o riesgo jurídico. **20 de las 90 tienen frecuencia de uso nula o rota**: 17 marcadas "nula" —código pagado que nunca llegó al auditor— y 3 que fallan siempre, botones visibles que devuelven 404 desde mayo de 2026. De esas 20, **14 se borran** (es la parte más barata y más rápida de todo el proyecto) y **6 se rescatan**, porque no les falta diseño sino pantalla o un router: la bóveda de credenciales, la cola de automatización, el detector de doble radicación, "Preparar el día", el segundo factor y la ingesta del correo. Ninguna de las 15 eliminaciones quita una capacidad que alguien esté usando: todas están verificadas contra archivo:línea. La única que retira una pieza con vocación de servicio —el bot de escritorio DGH— sale con reemplazo declarado (un adaptador DGH de dos vías), no al vacío.

**Cómo leer la matriz.** *Frecuencia*: alta = se usa todos los días; nula (código muerto) = verificado sin llamador; nula (roto) = el botón existe y la llamada muere en 404. *Impacto*: qué se pierde si no se hace (plata, tiempo, riesgo jurídico). *Decisión*: mantener, modificar (incluye **resucitar** lo que está roto pero vale), fusionar, eliminar, automatizar. *Prioridad*: **P0** = ya, bloquea o está sangrando; **P1** = versión 2.0; **P2** = 2.1; **P3** = después.

| Función | Módulo | Utilidad | Frecuencia | Impacto | Complejidad | Decisión | Prior. |
|---|---|---|---|---|---|---|---|
| Tope de gasto de IA por usuario | IA Central | Impide quemar créditos: `/analizar` no aplica `rate_limit_ia` pese a prometerlo en su docstring, solo 60 req/min genéricos (analizar.py:672). Un lote ya costó $14.50 en 251 llamadas (auto_responder_service.py:27-38) | alta | Alto (plata) | Baja | modificar | P0 |
| Costo real de IA por glosa | IA Central | Solo 1 de los 12 puntos que llaman a Anthropic registra el gasto (glosa_service.py:8456); Gemini y Groq nunca registran; 24 filas en `ai_calls`, 0 con glosa_id. Sin esto no se puede decidir qué apagar | media | Alto (plata) | Media | modificar | P0 |
| Pipeline multi-agente LLM | IA Central | Apagado desde siempre, 1 de 3 agentes escrito, 3× costo por diseño (multi_agent.py:32-34, 60-61). Su nombre choca con multi_agente.py, que es lo contrario | nula (código muerto) | Bajo | Baja | eliminar | P0 |
| Asistente Predictivo "Ola 4" | IA Central | Router montado (main.py:1226) sin un solo llamador; sinac-asistente.js se descarga en cada visita y nunca hizo una petición por leer `token` en vez de `hus_token` | nula (código muerto) | Bajo | Baja | eliminar | P0 |
| Ruteo del modelo de IA (cuándo escalar a Claude) | IA Central | Decide el costo de cada dictamen. Hoy hay dos cerebros y el flujo principal NO usa el oficial: `ia_router.py` vs el R-CEREBRO #5 inline de glosa_service (~5293) | alta | Alto (plata) | Media | fusionar | P1 |
| Caché de IA de dos niveles (RAM + BD 30 días) | IA Central | Evita pagar dos veces el mismo dictamen; clave sha256 que incluye proveedor+modelo+prompt (fix del caché cruzado entre EPS distintas) | alta | Alto (plata) | Baja | mantener | P1 |
| Copiloto conversacional con datos reales | IA Central | Único chat que consulta de verdad soportes, contratos, tarifas, normas y precedentes (asistente_maestro.py:72-187). Es el esqueleto del Copilot contextual del blueprint §15 | media | Alto | Media | mantener | P1 |
| Chat sobre la glosa | IA Central | No llama a IA: 8 respuestas fijas por palabra clave; el ejemplo que la propia pantalla sugiere ("citá la cláusula octava") nunca coincide (chat_glosa.py:56-138) y aun así consume cupo de IA | baja | Bajo | Baja | fusionar (en el copiloto) | P1 |
| Aprendizaje del resultado de la EPS | IA Central | El lazo está cortado: en la BD hay 52 plantillas Gold, las 52 son semilla, 0 aprendidas, todas con usos=0. La reinyección exige usos≥3 (few_shot_gold.py:131) y además corta en el paso 1 (:116-117) | media | Alto (plata) | Media | modificar | P1 |
| Definición de "valor recuperado" | Inicio | Cinco fórmulas incompatibles y cuatro conviven en la misma barra de pestañas del coordinador (glosa_repository.py:474 vs dashboard_ejecutivo.py:62-67 vs glosas_stats.py:4103, que suma el objetado completo cuando no hay valor registrado) | alta | Alto (plata) | Media | modificar (métrica única) | P0 |
| Biblioteca de 171 estadísticas `/stats/*` | Inicio | 167 de 171 endpoints sin un solo llamador; 11.341 líneas. Es donde vive la constante `ESTADOS_CERRADOS` copiada 117 veces: cambiar un criterio de negocio exige editar 117 sitios | nula (código muerto) | Alto (mantenimiento) | Baja | eliminar | P0 |
| Pantalla "Alertas" | Inicio | Dos líneas de markup, cero botones, y esconde lo más urgente: filtra `dias_restantes > 0`, así que lo ya vencido no aparece (glosa_repository.py:445) | baja | Medio (plazos) | Baja | fusionar (en la bandeja) | P1 |
| Cuatro tableros del mismo dato (Mando, Dashboard, Cobranza Live, Resumen del mes) | Inicio | El propio código registra su pedido de consolidar y la respuesta fue agregar una quinta superficie en vez de quitar tres pantallas (index.html:12386-12419) | alta | Alto (confianza) | Media | fusionar | P1 |
| Cartera y aging | Inicio | Se calcula por glosa, no por factura: una factura con 5 glosas abiertas reporta 5 veces su saldo (glosas_stats.py:6890-6902 y :6954-6968). Solo un endpoint tiene el parche | media | Alto (plata) | Alta | modificar (modelar la factura) | P1 |
| Informe ejecutivo mensual imprimible | Inicio | Único entregable que un gerente lleva impreso a un Comité de Cartera (informes.py:222-302). Hoy se pide con dos `prompt()` y se pierde si el navegador bloquea la ventana emergente | media | Alto | Baja | mantener (+ periodo y PDF) | P1 |
| Tasa de éxito por gestor | Inicio | Existe seis veces con seis denominadores; una versión divide levantadas entre TODAS las glosas del mes del gestor, incluidas las que aún no tienen decisión (dashboard_ejecutivo.py:128-137) | media | Medio | Media | fusionar | P2 |
| Detección de doble radicación (factura+CUPS+EPS) | Inicio | Bien construido y agregando en SQL (detector_anomalias.py:46-229). Ataca plata real y no tiene ninguna pantalla | nula (sin pantalla) | Alto (plata) | Media | automatizar (aviso en Inicio) | P2 |
| Badge de glosas críticas y vencidas | Bandeja | Siempre marca 0: filtra `estado=='PENDIENTE'`, valor que ningún código escribe (notificaciones_usuario.py:40,52). El aviso de vencimientos nunca avisa | alta | Medio (plazos) | Baja | modificar | P0 |
| Filtros guardados en el servidor | Bandeja | El frontend llama `/presets-filtros`, endpoint que no existe en el backend; el error se traga en silencio (index.html:13009) | nula (roto) | Bajo | Baja | eliminar | P0 |
| "Preparar el día" (un clic cierra ratificadas y extemporáneas) | Bandeja | Una acción, resultado en español, idempotente… y **hoy no funciona**: index.html:7112 llama a `POST /autopilot/preparar-dia` y ese router se borró ("autopilot: removido en la limpieza de ronda 29", main.py:1207). Devuelve 404. Es la automatización de mayor retorno del producto, apagada por un descuido de limpieza, no por decisión | nula (roto) | Alto (tiempo) | Baja | resucitar (modificar): rehacer el endpoint en el servidor y ponerla en la primera pantalla; entra en el primer paquete de la 2.0 (§10.3-A0) | P1 |
| Aviso de vencimientos ≤24h con valor en riesgo | Bandeja | Dice cuántas vencen y cuánta plata está en juego, y explica que el Art. 57 protege a la EPS (index.html:13548-13573). Solo se pinta en "Mis glosas" y la app abre en "Analizar" | alta | Alto (plazos) | Baja | mantener (moverlo a Inicio) | P1 |
| Bandeja priorizada con semáforo por días hábiles | Bandeja | Lo mejor construido del frontend: urgencia calculada en el servidor con su motivo, y tasa histórica del par (EPS, código) en cada fila (index.html:13091-13410) | alta | Alto | Media | mantener | P1 |
| Vistas guardadas de negocio | Bandeja | "Aprobadas por radicar", "TA sin contrato", "alta cuantía ≥$5M", "dictamen obsoleto", "requieren soportes": cada una es una pregunta real de cartera (index.html:2743-2750) | alta | Alto (tiempo) | Baja | mantener | P1 |
| Acciones en lote sobre hasta 500 glosas | Bandeja | Único punto del sistema donde el volumen se trata como volumen: generar, marcar respondidas, decisión EPS, reasignar (index.html:2728-2737) | alta | Alto (tiempo) | Media | mantener | P1 |
| Sugeridor automático de gestor | Bandeja | Router muerto con N+1 severo: por cada usuario carga TODAS sus glosas históricas a memoria (asignacion.py:95-103). El frontend usa los endpoints de glosas.py | nula (código muerto) | Bajo | Baja | eliminar | P1 |
| Generar dictamen con IA (unitario) | Motor de glosas | Es el producto. Hoy `analizar()` es un método de ~2.800 líneas con 73 `except` silenciosos dentro del método y 32 "redes finales" cosidas por orden cronológico de bug (glosa_service.py:4299-7097) | alta | Alto | Alta | modificar (pipeline por etapas) | P0 |
| Generar dictámenes en masa | Motor de glosas | Cuatro caminos con cuatro concurrencias y cuatro sets de enriquecimiento; solo uno tiene defensas anti-gasto. La misma glosa da distinta calidad según por qué puerta entró | alta | Alto (plata) | Alta | fusionar (un solo cerebro) | P0 |
| Estado del formulario de análisis | Motor de glosas | Dos fugas verificadas: `_concepto_modo_actual` nunca se limpia (index.html:9791 vs :15039) y toda la sesión sale como aceptación en vez de defensa; y "Re-analizar" descarta el tono elegido por leer un campo inexistente (:14491) | alta | Alto (plata) | Baja | modificar | P0 |
| Detección automática en vivo mientras se pega la glosa | Motor de glosas | Extrae sin gastar IA código, valor objetado, valor facturado, EPS, CUPS, contrato y tarifa (analizar.py:1032-1046)… y solo los muestra: no rellena ningún campo ni se envían | alta | Alto (tiempo) | Baja | modificar (que rellene) | P1 |
| Caminos sin IA: texto fijo, plantilla por código, dictamen directo | Motor de glosas | Dictámenes a $0 y ~50 ms para ratificadas, extemporáneas y tarifa-match, con fallback seguro (recepcion_service.py:1052-1057). Hoy la clasificación está triplicada y nadie adoptó el módulo unificador | alta | Alto (plata) | Media | fusionar | P1 |
| Reuso de dictamen gemelo por huella | Motor de glosas | Defensa anti-costo nacida de un incidente real; hoy solo protege el flujo de recepción (auto_responder_service.py:242-366) | media | Alto (plata) | Baja | mantener (extender a todos) | P1 |
| Respuesta por concepto dentro de una misma factura | Motor de glosas | Evita mezclar familias (lo que facilita la ratificación), pero concatena todo en un campo y obliga a des-concatenar con regex después (multi_codigo + dictamen_secciones + multi_concepto: tres detectores) | alta | Alto | Media | modificar (persistir por concepto) | P1 |
| Verificación de citas normativas contra el texto literal | Motor de glosas | Distingue norma inexistente, artículo fuera de norma y cita literal falsa (citation_verifier.py:24-50, 270), con cicatrices reales documentadas (la sentencia fantasma "C-4747/2007") | alta | Alto (jurídico) | Baja | mantener | P1 |
| Checks anti-fabricación y reintento dirigido | Motor de glosas | Cazan valores inventados, contratos de otra EPS, CUPS fantasma. Hoy cada check está implementado 3 veces con criterios distintos y hay una contradicción activa: una capa exige el correo institucional que otra penaliza (validador_dictamen.py:561-577) | alta | Alto (jurídico) | Alta | fusionar | P1 |
| Quality Gate como control único | Motor de glosas | 1.748 líneas + 1.151 de tests apagadas por un flag que ni figura en `.env.example`; conviven dos pipelines de regeneración | baja | Alto | Media | modificar (encender de fábrica) | P1 |
| Semáforos de calidad y autopiloto | Motor de glosas | Seis escalas sobre el mismo dictamen; la más visible ("% de éxito") es una heurística estática por tipo de glosa que no mide calidad, y el propio código lo admite (glosa_service.py:3551-3554) | alta | Alto (confianza) | Media | fusionar (score único) | P1 |
| Auditoría de la glosa contra la BD antes de gastar IA | Motor de glosas | Detecta "sin contrato" cuando el contrato está cargado, SOAT indebido y objeción mayor al excedente facturado-pactado (auditor_glosa.py). Único módulo que audita el fondo, no la forma | alta | Alto (plata) | Baja | mantener (ejecutar 1 vez) | P1 |
| Corrección automática de EPS: el texto le gana al desplegable | Motor de glosas | Anti-error humano con aviso legible al gestor (glosa_ia_prompts.py:1603). Hoy el aviso se inyecta DENTRO del dictamen jurídico que se radica | alta | Alto (jurídico) | Baja | mantener (aviso fuera del documento) | P1 |
| Detector de soportes faltantes antes de gastar IA | Motor de glosas | Dice qué falta y por qué, sin consumir tokens ni producir dictámenes inservibles (detector_requiere_soportes.py) | alta | Alto (plata) | Baja | mantener | P1 |
| Captura de la glosa por correo, voz, foto y Excel | Motor de glosas | Entiende el trabajo de campo: la glosa llega en correo, papel o Excel. Pero "pegar correo de EPS" abre un `prompt()` de una sola línea sin scroll (index.html:21934) | media | Alto (tiempo) | Media | modificar | P1 |
| Refinar el dictamen con instrucciones | Motor de glosas | Cuatro interfaces contra el mismo endpoint, con el "guardar al aplicar" en cuatro estados distintos (index.html:4295, 16423, 9968, 14535): el mismo gesto guarda o no según por dónde se entre | media | Medio | Baja | fusionar | P2 |
| Lectura del expediente por la IA | Expedientes | Hoy cualquier PDF de más de 4 páginas llega a la IA como ~7.050 caracteres (pdf_service.py:77-91) y el expediente auto-descubierto como 3 archivos × 5 KB. Una historia clínica de 200 páginas se analiza a ciegas | alta | Alto (plata) | Alta | modificar | P0 |
| Consulta de un soporte del expediente | Expedientes | Se indexan hasta 144k archivos para terminar mostrando la ruta como texto y un botón "Copiar" para pegarla en el explorador de Windows: no hay un solo `FileResponse` en soportes.py | alta | Alto (tiempo) | Media | modificar (servir el archivo) | P0 |
| Documento radicable de respuesta (PDF) | Expedientes | Cuatro generadores distintos; el del navegador estampa un "Nº OBJECIÓN" con `Math.random()` (index.html:18097→18191) y firma "Elaboró X · Confirmó X" con la misma persona | alta | Alto (jurídico) | Media | fusionar (solo el del servidor) | P0 |
| Firma digital del dictamen | Expedientes | Es HMAC con la clave del servidor: no prueba autoría ni cumple Ley 527/1999. Y el sistema declara CUMPLIDO el artículo de firma digital con evidencia "RSA-PSS-SHA256-v1", que no existe en el repositorio (sistema.py:1301) | nula (sin uso verificado) | Alto (jurídico) | Baja | eliminar | P0 |
| Papelera / borrado de glosas | Expedientes | No es borrado lógico: es `db.delete()` físico (glosas.py:3483) y las FK en CASCADE arrastran conceptos, versiones, comentarios y conciliaciones. Al restaurar solo vuelve la cabecera | media | Alto (pérdida) | Media | modificar | P0 |
| Protección del dato del paciente | Expedientes | El sistema publica `"cifrado_fernet": true` (sistema.py:147) y `cifrado.py` no tiene un solo importador: paciente, dictamen y texto de la glosa se guardan en claro. Y hay una segunda fuga, más silenciosa: el service worker cachea `/usuarios/yo` sin `Vary: Authorization`, así que en un PC compartido del hospital el usuario B puede recibir la sesión del usuario A. Ante Ley 1581/2012 es peor que no cifrar | n/a | Alto (jurídico) | Media | modificar (cifrar de verdad y no cachear lo autenticado) | P0 |
| Descubrimiento de soportes por número de factura | Expedientes | Un dato desbloquea historia clínica, RIPS y factura desde el disco de red (analizar.py:805-824). El índice se reconstruye dentro del request y congela el servidor (analizar.py:80, sin `to_thread`) | alta | Alto (tiempo) | Alta | modificar (índice persistente) | P1 |
| Trazabilidad del dictamen (versiones + bitácora) | Expedientes | Solo 3 de los 19 puntos que escriben el dictamen guardan versión, y los automáticos no la guardan (ia_auditora_proactiva.py:183). En la bitácora la misma tabla se audita como "historial" (19 sitios) y "glosas" (11) | alta | Alto (jurídico) | Media | modificar | P1 |
| Excel radicable institucional | Expedientes | Único generador del documento que se radica ante la EPS, con hoja de fundamento jurídico y la regla de no inventar datos cuando falta un metadato (excel_radicable.py:20-23) | alta | Alto | Media | mantener (agrupar por pagador) | P1 |
| Exportación en formato DGH (26 columnas) | Expedientes | Obligación externa no negociable, ya conectada al botón (exportar.py:39 ← index.html:19553) | alta | Alto | Baja | mantener | P1 |
| Excel-respuesta anotado que vuelve al gestor | Expedientes | Le devuelve al gestor SU planilla con las respuestas. Es el único generador de Excel del repo que NO sanea celdas: un carácter de control en un dictamen tumba el archivo de todos los gestores | alta | Alto | Baja | modificar | P1 |
| Botón "Simular conciliación" | Conciliaciones | Llama a `/conciliaciones/{id}/simulador/`, ruta que no existe en ningún router: devuelve 404 siempre y el auditor cree que la función falla (index.html:20509) | baja (siempre falla) | Bajo | Baja | eliminar | P0 |
| Ciclo bilateral y acta SINAC multi-glosa | Conciliaciones | Contra-respuesta EPS → postura HUS → acta con mérito ejecutivo (Art. 422 CGP): es el formato real que firma el hospital | media | Alto | Media | mantener | P1 |
| Preparar la audiencia con IA | Conciliaciones | Contraargumentos probables de la EPS y valor mínimo aceptable, ya usado por la pantalla (index.html:11971). La IA acompaña la negociación, no solo el dictamen | media | Alto (plata) | Baja | mantener | P1 |
| Cerrar acta → cerrar la glosa y sumar la plata | Conciliaciones | `cerrar-acta` no transiciona la glosa ni escribe valor_recuperado (conciliacion.py:290-324): para que la plata conciliada aparezca en el tablero hay que registrarla otra vez por otro camino | media | Alto (plata) | Media | automatizar | P2 |
| Captura de la decisión y del cierre | Conciliaciones | `panelCerrarActa` encadena CINCO `prompt()` (número, fecha a mano, valor, resultado escrito literal "ACUERDO_PARCIAL" con guion bajo) y pierde todo si el último no coincide (index.html:20480-20498) | media | Alto (dato) | Baja | modificar | P2 |
| Crear la conciliación cuando la EPS ratifica | Conciliaciones | Hoy la transición RATIFICADA → conciliación es 100% manual aunque el sistema tiene todos los datos | media | Alto (plata) | Media | automatizar | P2 |
| Ficha de contrato por EPS | Contratos y tarifas | Riesgo estructural nº1: número, NIT, vigencia y factor tarifario viven en un diccionario Python con PRIORIDAD sobre la BD (glosa_ia_prompts.py:59-299, get_contrato:372). Las 15 columnas de la tabla `contratos` están vacías en las 13 filas reales | alta | Alto (plata) | Alta | fusionar (una ficha en BD) | P0 |
| Módulo "Salud Total" | Contratos y tarifas | Ítem de primer nivel del menú, habilitado al rol AUDITOR, cuyos dos botones devuelven 404 desde mayo de 2026 (index.html:2091; main.py:1177). El usuario entra, sube un archivo y no pasa nada | baja (siempre 404) | Bajo | Baja | eliminar | P0 |
| Crear y editar un contrato desde la pantalla | Contratos y tarifas | No existe forma de crear un contrato: `POST /contratos/upsert` tiene 0 llamadas. Y editar uno de las 14 EPS principales es placebo: el dictamen sigue citando el catálogo del código (index.html:14820) | media | Alto (plata) | Media | modificar | P1 |
| Extracción de cláusulas del PDF del contrato con IA | Contratos y tarifas | Capacidad diferencial: el dictamen cita la cláusula exacta con su página. Protegida contra pérdida (no borra las viejas si la IA devuelve 0), pero sin revisión humana antes de inyectarlas | media | Alto (jurídico) | Media | mantener (+ revisión humana) | P1 |
| Carga de tarifarios por Excel (multi-formato) | Contratos y tarifas | Única vía por la que un auditor carga datos contractuales sin programador; parsers para los formatos reales (Famisanar 3 anexos, DMBUG, FOMAG por paquetes) | media | Alto (plata) | Media | mantener | P1 |
| Mérito de glosas tarifarias sin gastar IA | Contratos y tarifas | Evaluación determinista con heurísticas ganadas en producción (facturado >50× objetado = parser roto; si la EPS niega el contrato, defender íntegro). Consumida por 4 flujos | alta | Alto (plata) | Media | mantener | P1 |
| Perfil argumental por EPS | Contratos y tarifas | Estilo, táctica y cierre preferido por pagador; es un cuarto catálogo por-EPS paralelo, con EPS que no existen en los otros tres (perfil_eps.py) | media | Medio | Baja | fusionar (en la ficha de pagador) | P2 |
| Liquidador de tarifas SOAT | Contratos y tarifas | Promete liquidar el Manual SOAT y el catálogo tiene 4 códigos de ejemplo: casi toda búsqueda cae en "SIN_TARIFA_LOCAL" y el auditor va al manual oficial | baja | Alto (plata) | Media | automatizar (cargar el manual) | P2 |
| Corpus normativo y reglas de defensa | Biblioteca | Las ~15 reglas 8.x destiladas de 33 rondas con caso y fecha (glosa_ia_prompts.py:698-749) y el corpus con texto literal son el activo más difícil de reconstruir, y viven en Python: cada corrección exige un programador | alta | Alto (jurídico) | Alta | modificar (a datos versionados) | P1 |
| Consulta de normas por el auditor | Biblioteca | Dos corpus de 131 normas con solo 20 nombres en común: lo que el auditor lee no es lo que la IA cita ni lo que el validador verifica. Y devuelve como "texto" la concatenación de palabras clave | media | Alto (jurídico) | Media | fusionar | P1 |
| Banco de respuestas modelo del equipo | Biblioteca | Existe dos veces: 24 textos en Python y 50 filas en la BD sembradas del mismo material. El contenido es capital jurídico; el contenedor duplicado no | alta | Alto | Baja | fusionar (tabla editable) | P1 |
| Búsqueda TF-IDF de normativa | Biblioteca | Sus dos endpoints no aparecen en ninguna línea de las 23.125 del frontend; su validación de citas da por buena cualquier cita cuyo número aparezca en el corpus concatenado | nula (código muerto) | Bajo | Baja | eliminar | P1 |
| Grafo de relaciones entre normas | Biblioteca | Único consumidor detrás de `TOOL_USE_HABILITADO`, que por defecto es '0' (ia_tools.py:28). Su propio docstring se declara "foundation" | nula (flag apagado) | Bajo | Baja | eliminar | P2 |
| Bot de escritorio DGH | Automatización | 746 líneas que nunca respondieron una glosa real: no graban por defecto, procesan solo la primera objeción y hacen clic por coordenadas fijas de pantalla sobre un sistema contable. Pero el DGH es el único lugar donde la glosa existe contablemente, y hoy se alimenta a mano en las dos direcciones: borrar el bot sin sustituto deja el cuello de botella intacto | nula (nunca cerró una glosa) | Alto (el hueco que deja) | Media | eliminar el bot de coordenadas **y** reemplazarlo por un adaptador DGH de dos vías (exportar respuesta / importar estado) | P1 |
| Motores de glosa fuera de la aplicación | Automatización | Dos motores paralelos, sin IA y peores, que además contradicen al backend: "CL" = calidad allí y pertinencia clínica acá; "PDX" con dos significados clínicos distintos (asistente_conciliacion_dispensario.py:69 vs radicar_facturacion.py:131) | baja | Alto (jurídico) | Media | eliminar (rescatando la matriz de evidencia) | P1 |
| Bots de portal COOSALUD y SIMED | Automatización | Es donde se cierra la plata: los bots procesaron 324 facturas y 597 objeciones en siete lotes; de los tres últimos, por $153.675.820, el Excel está listo y la subida sin confirmar. Pero ningún bot habla con el motor: el puente es un Excel que viaja en el escritorio de una PC, y por eso nadie sabe desde el sistema qué quedó radicado. Son cuatro bots hoy y serán nueve con los cinco pagadores ya nombrados por el cliente | alta | Alto (plata) | Alta | modificar (núcleo + perfil + adaptador) | P2 |
| Bot de notas crédito SIMED | Automatización | Mismo portal, mismo login, mismas credenciales que el bot de glosas, en dos implementaciones separadas; el propio código lo admite (responder_glosas_simed.py:423) | media | Medio (tiempo) | Media | fusionar (una acción del adaptador) | P2 |
| Agente local instalado en el hospital | Automatización | Hoy son dos procesos en la misma PC con dos tokens, dos configuraciones y dos formas de instalar (jumpbox_sync.py y agente_lotes.py) | media | Medio | Media | fusionar (un solo agente) | P2 |
| Centro de Automatización (lanzar y ver los bots) | Automatización | La cola tiene 6 endpoints, 3 tablas y 403 líneas de tests, y ninguna pantalla: 0 ocurrencias de "RPA", "robot" o "Playwright" en el frontend. La interfaz real es PowerShell con rutas de 120 caracteres. No le falta diseño: le falta pantalla, por eso no se borra | nula (sin pantalla) | Alto (tiempo) | Alta | modificar (darle tablero) | P2 |
| Radicación multi-entidad por perfiles | Automatización | Ya implementa el patrón correcto: perfil declarativo en JSON + motor genérico, con 12 entidades en `data/perfiles_radicacion.json` y stdlib pura (radicar_facturacion.py:266-344). El Perfil 2.0 debe extender este | media | Alto | Media | mantener | P2 |
| Ingesta del correo de la EPS | Automatización | El paso correo → Excel → importación sigue siendo manual: el router IMAP quedó en esqueleto, sin pantalla ni tarea programada (bandeja.py) | nula (esqueleto) | Medio (tiempo) | Media | automatizar | P3 |
| Tres pantallas huérfanas (multi-concepto, detector en masa, simulador) | Herramientas | Existen completas y con CSS propio, y no hay forma de llegar a ellas: ni sidebar, ni paleta (falla en silencio), ni atajo. El detector en masa además rompe con 500 por consultar campos inexistentes | nula (inalcanzables) | Bajo | Baja | eliminar | P1 |
| Buscador global de datos y acciones | Herramientas | Ctrl+K abre TRES paletas superpuestas y la tecla "/" deja un overlay imposible de cerrar: hay que recargar y se pierde la glosa que se estaba redactando (index.html:7178 vs :10869) | alta | Medio (tiempo) | Media | fusionar (una sola) | P1 |
| Foto de la glosa con OCR | Herramientas | Única entrada multimodal barata; resuelve el caso real de la glosa que llega en papel (vida.py:189-233) | media | Medio (tiempo) | Baja | mantener | P1 |
| Utilidades de doble clic (unir PDF, informes) | Herramientas | La idea —doble clic, cero consola— es el único gesto de usabilidad del repositorio; la implementación son 1.010 líneas de batch de Windows inauditables, y una renombra PDFs a `.cmd` | media | Medio | Media | fusionar (acciones del agente) | P3 |
| Control de acceso por rol | Administración | Es cosmético: `aplicarRestriccionesRol` oculta menús según una variable de localStorage (index.html:12844, 19740). Cualquiera escribe `hus_rol='SUPER_ADMIN'` y recupera los 24 ítems, incluido "Borrar todo". Y detrás hay una exposición concreta, no teórica: `GET /glosas/historial` devuelve el nombre del paciente de todas las glosas del hospital sin filtro por rol ni por asignación (glosas.py:188-236), mientras el endpoint vecino sí filtra | alta | Alto (seguridad) | Media | modificar (autorización en el servidor, endpoint por endpoint) | P0 |
| Funciones rotas a la vista del usuario | Administración | Notas privadas (el usuario escribe y pierde lo escrito), snippets (la pantalla enseña a usar algo que devuelve lista vacía) y dos sistemas de comentarios, con sus routers borrados en mayo de 2026 | baja (fallan siempre) | Alto (confianza) | Baja | eliminar | P0 |
| Aislamiento multi-entidad (multi-tenant) | Administración | Un middleware que lee un header y no filtra nada, y que acepta el tenant por query param sin validar (tenancy.py:82). Para un solo hospital, es peor que no tenerlo | nula (código muerto) | Bajo | Baja | eliminar | P0 |
| Manejo de sesión expirada | Administración | Solo 11 de las 276 llamadas comprueban el 401, y lo hacen de cuatro maneras distintas; en las otras ~265 el usuario ve un error incomprensible o nada | alta | Medio (tiempo) | Media | modificar | P1 |
| Actualización del esquema al arrancar | Administración | 460 líneas de `ALTER TABLE` en el arranque, cada una en try/except que registra y sigue: si falla en producción la app arranca con un esquema distinto al que el código espera | n/a | Alto (pérdida) | Alta | modificar (migraciones reales) | P1 |
| Bóveda de credenciales de los portales EPS | Administración | Es el único cifrado que de verdad cifra, con motivo obligatorio y log de cada acceso (credenciales_vault.py) — y no tiene pantalla, así que el equipo sigue guardando las claves en un Excel | nula (sin pantalla) | Alto (seguridad) | Baja | modificar (darle pantalla) | P1 |
| Segundo factor (2FA) y escritorio remoto (RustDesk) | Administración | Verificado contra los datos: `totp_activo` en 0 de 24 usuarios y `rustdesk_id` en 0 de 24, pese al comentario del código que dice que el 2FA es obligatorio para SUPER_ADMIN. Son dos piezas distintas metidas en la misma pantalla: el escritorio remoto no lo usa nadie y no es función de un motor de glosas; el segundo factor no se usa porque está enterrado en Administración, donde el gestor nunca entra. En un sistema que guarda nombre de paciente, historia clínica y dictámenes no se quita el segundo factor: se pone donde el usuario pueda activarlo y se exige a quien puede borrar todo | nula (0 de 24 usuarios) | Alto (seguridad) | Baja | modificar: el 2FA se conserva, se mueve a "Mi cuenta" y se vuelve obligatorio para SUPER_ADMIN; RustDesk se elimina | P1 |

### Las 10 decisiones que más plata mueven

1. **Sacar los contratos del código y meterlos en la base de datos.** Hoy renegociar una tarifa o renovar un contrato exige un despliegue de software, y editar el contrato de las 14 EPS principales desde la pantalla no cambia lo que la IA cita, porque el catálogo en Python tiene prioridad sobre la BD (glosa_ia_prompts.py:372-432). Es el cambio de mayor impacto y de los más baratos.
2. **Dejar de truncar el expediente.** Cualquier PDF de más de 4 páginas llega a la IA como ~7.050 caracteres (pdf_service.py:77-91). Un dictamen construido sobre 7 KB de una historia clínica de 200 páginas es un dictamen a ciegas, y eso se traduce en glosas ratificadas. El propio equipo ya lo comprobó por otro lado con los contratos (contratos.py:527-531).
3. **Un solo cerebro de respuesta, con las defensas anti-gasto en todos los caminos.** Hay cuatro formas de generar dictámenes en masa y solo una tiene texto fijo, reuso de gemelos y corte por complejidad; nacieron de un incidente real de $14.50 en 251 llamadas (auto_responder_service.py:27-38).
4. **Aplicar el tope de gasto de IA al endpoint más caro.** `POST /analizar` no lo aplica pese a que el módulo lo promete en su docstring: un usuario puede disparar 60 análisis por minuto (analizar.py:672).
5. **Una sola definición de "valor recuperado" y modelar la factura.** Cinco fórmulas incompatibles, cuatro a un clic de distancia en la misma barra de pestañas, y la cartera multiplicada por el número de glosas de cada factura (glosas_stats.py:6890-6902). Mientras siga así, ningún tablero es firmable por un auditor de cartera.
6. **Que el acta de conciliación cierre la glosa y sume la plata en una sola acción.** Hoy `cerrar-acta` no transiciona nada (conciliacion.py:290-324): el auditor digita el resultado dos veces, y lo conciliado no aparece en el tablero hasta que lo haga.
7. **Reparar el circuito de aprendizaje.** En la base hay 52 plantillas Gold: las 52 son semilla, 0 aprendidas, todas con usos=0. El sistema aprende solo si se invierte el orden de selección de ejemplos y se quita el filtro `usos>=3` (few_shot_gold.py:116-131).
8. **Conectar los bots al motor.** Ningún bot clasifica, analiza ni guarda historial: hacen solo el último tramo, y el puente entre las dos mitades es un Excel en el escritorio de una PC. En SIMED los bots procesaron 324 facturas y 597 objeciones en siete lotes; de los tres últimos, por $153.675.820, el Excel está listo y la subida sin confirmar — y el sistema no lo sabe, porque el resultado del trabajo queda en un CSV local y la confirmación depende de que alguien se acuerde de mirar el portal.
9. **Arreglar la fuga de "aceptar 100%".** Un solo clic en un concepto marcado para aceptar contamina toda la sesión: las glosas siguientes salen como cartas de aceptación en vez de defensas, sin ninguna señal en el formulario (index.html:9791 vs :15039).
10. **Quitar del documento radicable lo que no es verdad.** El PDF que se le entrega a la EPS lleva un "Nº OBJECIÓN" generado con `Math.random()` (index.html:18097→18191) y un "Elaboró / Confirmó" con la misma persona; y el sistema declara ante una auditoría que firma digitalmente con RSA cuando implementa un HMAC que no prueba autoría (sistema.py:1301). Eso no es un problema estético: es lo primero que un abogado de la EPS usa para tumbar el trámite.

---

```markdown
## 5. Lo que desaparece (Fase 6 del encargo)

Esta es la fase más barata del proyecto y la de menor riesgo, y por eso va primero: **no se toca nada que alguien use**. Todo lo que aparece abajo cumple al menos uno de estos tres criterios verificables, y en la tabla se dice cuál:

| Criterio | Cómo se comprueba | Riesgo de borrar |
|---|---|---|
| **Muerto verificado** | Cero llamadas desde `static/index.html` (23.125 líneas), `tools/` y `scripts/` | Casi nulo |
| **Roto a la vista** | La pantalla existe y llama a un backend que fue borrado → 404 en cada clic | Negativo: hoy hace daño |
| **Duplicado con ganador claro** | Dos o más implementaciones del mismo concepto; una está en el camino real y las otras no | Bajo, si primero se migra el contenido |

> **Regla operativa para toda la fase:** antes de borrar una ruta se corre un barrido automático (`grep` de la ruta contra `static/`, `tools/`, `scripts/`) **y** se revisan 30 días de log de acceso por ruta. Lo que no aparece en ninguno de los dos, se va. Esto es lo que el propio blueprint exige en §9 ("Antes de eliminar, verificar dependencias") y lo que ya falló una vez: el router `exportar` se perdió en una limpieza anterior y el botón del DGH devolvió 404 con un servicio de 580 líneas huérfano detrás (`app/api/routers/exportar.py`, docstring líneas 3-7). En la 2.0 esto se previene con **un test de contrato que verifique que cada botón del frontend resuelve a una ruta registrada**.

> **Excepción declarada:** "Preparar el día" (`static/index.html:7112` → `POST /autopilot/preparar-dia`) parece muerto y **no se borra**. El router se removió en la limpieza de ronda 29 (`app/main.py:1207`) y hoy el botón devuelve 404 en cada clic. Es la automatización de mayor retorno del producto y hay que **resucitarla**, no eliminarla. Va en el primer paquete del roadmap.

---

### 5.1 Módulos muertos del backend

Conteos de líneas verificados con `wc -l` sobre el repositorio actual. Las tres decisiones que este plan dejaba abiertas (Quality Gate, Salud Total, snippets) quedan cerradas en la propia tabla.

| Qué se borra | Líneas | Evidencia de que no se usa | Riesgo de borrarlo | Qué verificar antes |
|---|---|---|---|---|
| `app/api/routers/asignacion.py` | 158 | Cero llamadas en el frontend; la UI usa los endpoints de asignación de `glosas.py` (`/{id}/asignar`, `/bulk/asignar`, `/bulk/auto-asignar`) | Se pierde la heurística de sugerencia de gestor | Portar el score a `/glosas/bulk/auto-asignar` si la coordinación lo quiere. Bonus: tiene un N+1 severo (carga todas las glosas históricas de cada usuario, `asignacion.py:95-103`) |
| `app/api/routers/bandeja.py` | 123 | Su propio docstring lo llama "skeleton"; requiere un cron externo que no existe | Se pierde la idea de ingesta por correo IMAP | Nada: la idea revive mejor en la propuesta N12 (captura automática) |
| `alertas.py` + `alerta_service.py` | 323 | `/alertas/proximas` es idéntico a `/glosas/alertas` (ambos llaman `GlosaRepository.alertas_proximas`) y el frontend solo usa el segundo; el correo nunca se envía porque no hay programador | Se pierde el correo de vencimientos | Es urgente borrarlo por otro motivo: `POST /alertas/enviar` (`alertas.py:45`) está abierto a **cualquier usuario autenticado**. El correo de vencimientos se repone en la propuesta N1 |
| `salud_total_service.py` + panel | 502 | Router removido en mayo 2026 (`app/main.py:1177`, "stub removido"); cero imports en `app/` | Si Salud Total vuelve a ser pagador, hay que rehacerlo | **Decisión: se borra.** Salud Total no aparece entre las 12 entidades de `data/perfiles_radicacion.json` ni en `CONTRATOS_HUS`, es decir, hoy no es pagador con el que el HUS radique. Si volviera a serlo, entra como una fila del Perfil de Pagador (N4) en horas, no como un servicio propio de 502 líneas |
| `texto_fijo_batch.py` | 134 | Cero importadores fuera de su propio test; era una migración puntual de la Ronda 22 | Nulo | Una consulta SQL de una línea que confirme que el backlog al que apuntaba ya está migrado |
| `multi_agent.py` (inglés) | 314 | Flag `MULTI_AGENT_HABILITADO` por defecto `"0"` (`multi_agent.py:61`), 1 de 3 agentes implementado, 3× costo por diseño | Se pierde la idea de multi-agente LLM | Que la variable no esté puesta en el `.env` del hospital. Ojo: **no confundir con `multi_agente.py` (español), que sí corre en cada análisis y hay que conservar** |
| `rag_normativa.py` | 312 | Sus dos endpoints (`/herramientas/normativa/buscar` y `/validar-citas`) no aparecen ni una vez en el frontend; su validación de citas es más pobre que `citation_verifier` | Se pierde su diccionario de sinónimos jurídicos | Rescatar ese diccionario **antes** de borrar el archivo |
| `normativa_grafo.py` | 290 | Único consumidor `ia_tools.py:331`, y todo `ia_tools` está detrás de `TOOL_USE_HABILITADO` que por defecto es `"0"` (`ia_tools.py:28`) | Se pierden ~30 aristas normativas escritas a mano | Migrar las aristas al corpus único como campo `relaciones` |
| `snippets.py` + tabla + pantalla | 15 | Es un stub de 15 líneas que devuelve `[]`; la pantalla promete "Gestionar mis snippets" (`index.html:3378`) y `POST`/`DELETE` no existen | Nulo | **Decisión: se borra todo, incluida la pantalla.** El texto reutilizable ya está resuelto dos veces y bien: `plantillas_gold` (52 filas, con aprendizaje) y los textos fijos jurídicos de `recepcion_service`. Un tercer mecanismo de texto reutilizable violaría el §3 del blueprint el día uno |
| `plantillas.py` + repositorio + tabla `plantillas` | 168 | Tabla con 0 filas; el motor usa `PlantillaGoldRecord` (52 filas), no `PlantillaRecord` | Nulo | Nada |
| `tenancy.py` + su middleware | 109 | Nadie lee el `ContextVar` que setea en cada request; acepta el tenant por query param sin validar | Si algún día se vende como SaaS hay que rehacerlo bien | Nada. Hoy es peor que no tenerlo: induce a creer que hay separación de datos |
| `cifrado.py` | 73 | Cero importadores en todo el repositorio | **Jurídico, si se borra sin más**: `/sistema` publica `"cifrado_fernet": true` (`sistema.py:147`) con solo tener la variable puesta | Se borra **en el mismo commit** en que se corrige esa declaración (ver la decisión de PHI en 5.7). No se puede seguir declarando ante una auditoría de Habeas Data algo que no ocurre |
| `bot_mensajeria.py` (WhatsApp/Telegram) | 215 | Nunca envía un mensaje; su único efecto es que un healthcheck responda `providers_configurados: []` | Nulo | Nada |
| `quality_gate_stats.py` (router) | 188 | 0 menciones de "quality-gate" en el frontend; sus consultas leen una tabla que hoy está vacía | Se pierde el router de estadísticas de calidad, no la medición | **Decisión tomada: el Quality Gate se enciende de fábrica en la 2.0** (§3.3, §4 y §8.1), así que `quality_gate_recorder.py` (170 l) **se conserva**, se conecta con la línea que hoy le falta (`registrar_run` no tiene llamadores) y se le da pantalla. Lo que se borra es solo este router: sus cuatro consultas vivas se mudan al `MetricasService` único (propuesta **N8**), para no volver a tener dos lugares donde se calculan métricas |
| `auditoria_forense.py` (router) | 111 | Cero llamadores + colisión de nombre con `auditor_forense.py`, que es el que sí funciona | Nulo | Si hace falta forense de accesos, va dentro de `audit.py` |
| `routers/dictamen_pdf.py` + `/glosas/{id}/resumen-pdf` | 288 | `grep "dictamen-pdf"` en `static/` = 0 resultados | Se pierde un hash SHA-256 que **ningún endpoint verifica** | Nada. Sobrevive `services/dictamen_pdf.py`, que es el generador real |
| `adjuntos.py` | 139 | Cero llamadores, cero filas | Nulo | Rescatar el patrón de saneo de `Content-Disposition` contra CRLF injection (`adjuntos.py:104-117`): debe aplicarse a **toda** descarga de la 2.0 |
| `routers/pdf.py` (`/pdf/ocr`) | 44 | Cero llamadores en 13 meses | Nulo, y quita superficie de ataque: no tiene rate limit y cuesta tokens de Anthropic por llamada | Nada |
| `firma_digital.py` + router `/firma` | 100 | Cero uso real | **Alto si se deja como está**: es HMAC con la `SECRET_KEY` del servidor — no prueba autoría ni cumple Ley 527/1999. Y `sistema.py:1301` declara CUMPLIDO el artículo de firma digital con evidencia "RSA-PSS-SHA256-v1", que no existe en el repositorio | Corregir las tres afirmaciones falsas del sistema **en el mismo commit** en que se borra el módulo |
| `predictor_glosas.py` | 234 | Su endpoint (`/herramientas/predecir-riesgo`) no se llama nunca | Se pierde una función madura con 7 tests | Es **otro producto**: predice si una factura será glosada *antes* de radicar. El motor responde glosas ya recibidas. Fuera de alcance (ver 6.3) |
| `asistente_predictivo.py` + `inteligencia_ambiental.py` | 402 | Router montado en `main.py:1226` y nunca invocado; su frontend (`sinac-asistente.js`) jamás hizo una petición porque lee `localStorage.token` cuando la app guarda `hus_token` (`index.html:6387`) | Nulo | Nada |
| `multi_concepto.py` + `dictamen_secciones.py` | 315 | Tercer detector de multi-código (duplica `multi_codigo.py` y `_extraer_codigos_glosa`); `dictamen_secciones` existe solo para des-concatenar con regex un HTML que el propio sistema generó | Nulo | `dictamen_secciones` desaparece **automáticamente** al persistir el dictamen por concepto (ver 5.3) |
| Stubs vacíos: `digest_ejecutivo`, `digest_scheduler`, `exportar_gerencial`, `noticias_scheduler`, `noticias_salud_co` | 56 | Archivos de 5 a 18 líneas que hacen `pass`, aún conectados al arranque | Nulo, y quita una mentira: `/sistema/jobs-programados` le reporta al admin un trabajo programado que no existe | Quitar los bloques del ciclo de vida en `main.py` y sacar `feedparser` de la imagen |
| `_exportar_xlsx_legacy_22_columnas` (`glosas.py:480`) | ~220 | El propio docstring dice: "NO se invoca desde el endpoint público" | Nulo | Nada. Su reemplazo (`excel_radicable`) está en producción |
| **Subtotal (24 filas)** | **4.833** | | | |

---

### 5.2 Endpoints construidos que nunca llegaron a un botón

Aquí está el grueso del peso muerto. La API tiene rutas que se escribieron, se probaron y **nunca se cablearon a la interfaz**: consumen mantenimiento y no llegan al auditor.

| Router | Endpoints muertos | Líneas fuera (aprox.) | Ejemplos concretos | Qué verificar antes |
|---|---|---|---|---|
| `glosas.py` (10.241 l, **127 rutas verificadas**) | **62 de 127** | ~4.500 | `score-defensa`, `whatsapp-mensaje`, `checklist-pre-envio`, `probabilidad-levantamiento`, `dialogo-bilateral`, `eps-comportamiento`, `versiones-resumen`, `conciliaciones-resumen`, `historial-workflow`, `validar-rapido` | Cuatro de ellos duplican endpoints vivos: borrar el duplicado, no el original |
| `glosas_stats.py` (11.341 l) | **167 de 171** | ~11.000 | Es el archivo donde vive el bug replicado: `ESTADOS_CERRADOS` redeclarado 117 veces en `app/` con tres definiciones incompatibles | Antes de borrar, extraer las 4 estadísticas vivas a la API de métricas única (propuesta **N8**) |
| `admin.py` (5.344 l) | **72 de 77** | ~4.900 | `/admin/equipo-pulse`, `/admin/insight-financiero`, `/admin/cierre-del-dia`, `/admin/alertas-inteligentes` | `/admin/backup-db.json` carga en memoria todas las glosas + tarifas + 90 días de audit_log: borrarlo es además una mejora de estabilidad |
| `sistema.py` (3.053 l) | **34 de 42** | ~2.000 | 6 endpoints de "salud" que nadie llama; `/sistema/observabilidad` reporta números congelados en "Ronda 50" con desviaciones de 3,5× | Dejar `/health` (público, 3 campos, sin consultar la BD) y `/admin/diagnostico` (el único con pantalla) |
| `usuarios.py` (3.902 l) | **20 de 36** rutas `/yo/*` | ~1.200 | `/yo/resumen`, `/yo/super-resumen`, `/yo/inicio`, `/yo/dashboard`, `/yo/insights`, `/yo/quick-wins` — todas responden variantes de la misma pregunta | Consolidar las 16 vivas en un solo `GET /mi-dia`: hoy la pantalla personal se arma con ~15 peticiones separadas |
| `analytics.py`, `contratos.py`, `cups.py`, `papelera.py`, `herramientas_avanzadas.py`, `analizar.py` | 6/10, 9/16, 3/4, 2/5, 2/6, 1 = **23** | ~800 | `/analizar/score-breakdown`, `/herramientas/extraer-factura` (duplicado exacto de `/analizar/extraer-soportes`), `/papelera/buscar`, `/papelera/stats` | En `contratos.py` hay que **agregar** lo que falta (formulario de creación) mientras se podan 9 endpoints muertos |
| **Subtotal** | **378 endpoints** | **~24.400** | | |

**Tres de estos endpoints no están muertos: están rotos y visibles.** `/herramientas/detector-masa` consulta `GlosaRecord.created_at` y `g.texto_glosa`, atributos que no existen en el modelo (son `creado_en` y `texto_glosa_original`) → error 500 en cada clic. `/conciliaciones/{id}/simulador/` no existe en ningún router, pero el botón morado "🧠 Simular" está en la pantalla de conciliaciones. Esos se arreglan o se borran **el primer día**, no al final.

---

### 5.3 Ocho tablas de la base de datos sin una sola referencia

La base tiene **37 tablas** (`grep -c "__tablename__" app/models/db.py`). Ocho de ellas —el **22 %**— no son leídas ni escritas por ninguna línea de código vivo. Se materializan igual en cada arranque vía `Base.metadata.create_all` (`app/main.py:158`), y sus routers fueron borrados en mayo de 2026 (`main.py:1213-1222`) mientras el frontend los sigue llamando.

| Tabla (`app/models/db.py`) | Qué prometía | Estado real | Decisión |
|---|---|---|---|
| `push_subscriptions` (l. 228) | Notificaciones push | Service worker preparado, `pywebpush` en la imagen Docker, **cero backend** | Borrar tabla + handler del SW + dependencia |
| `notas_privadas` (l. 710) | Nota privada por glosa | El botón flotante amarillo **siempre aparece**, el usuario escribe y al guardar recibe "No se pudo guardar" y pierde el texto | Borrar tabla y FAB. La función revive como columna `visibilidad` en `comentarios_glosa` |
| `preset_filtros` (l. 730) | Filtros guardados | `/presets-filtros` no existe; el error se traga con `console.warn` | Borrar |
| `comentarios_thread` (l. 759) | Comentarios por sección | Router borrado; **dos** sistemas de comentarios en el frontend, ambos inalcanzables | Borrar los dos; sobrevive `comentarios_glosa` |
| `webhooks` (l. 781) | Integraciones | Sin router | Borrar |
| `chat_conversaciones` / `chat_mensajes` (l. 804, 817) | Historial del chat | Router borrado; 5 llamadas huérfanas en el frontend | Borrar |
| `snippets` (l. 839) | Atajos de texto del gestor | Router = stub que devuelve `[]` | Borrar (ver la decisión en 5.1) |

**Riesgo de borrarlas: nulo en datos, positivo en confianza.** Hoy son **cinco funciones que el usuario ve en pantalla y que fallan en silencio**; eso se percibe como "el sistema es inestable" y erosiona la confianza en el resto, que sí funciona.

Además se fusionan tres pares redundantes: `plantillas` → `plantillas_gold`; `lotes_importacion` + `importaciones_recepcion` → una sola tabla `importaciones`; y las nueve columnas de `historial` que duplican `conceptos_glosa` (`codigo_glosa`, `valor_objetado`, `observacion_eps`, `cups_servicio`, `servicio_descripcion`, `concepto_glosa`, `dictamen`, `score`, `auditor_email`). El propio código admite el problema: `glosas.py:2192` está rotulado `# Fallback legacy: 1 GlosaRecord por concepto`. La cuenta: **37 − 8 muertas − `plantillas` − una de las dos tablas de importación = 27 tablas**, sin perder una sola función que alguien use.

---

### 5.4 Los dos motores de glosa que viven fuera de la API, y el resto de `tools/`

| Qué se borra | Líneas | Evidencia | Riesgo | Qué rescatar antes |
|---|---|---|---|---|
| `tools/asistente_conciliacion_dispensario.py` | 727 | Motor de glosas paralelo, determinista y sin IA, que **contradice al backend**: mapea `CL` → CALIDAD mientras `glosa_service.py:281` mapea `CL` → PERTINENCIA CLÍNICA; define `PDX` como "Descripción quirúrgica" mientras otros cinco catálogos lo definen como apoyo diagnóstico | Alto si se borra a ciegas | **La matriz de evidencia** (`construir_matriz`, línea 488): por cada soporte que la familia de glosa exige, si está o no, en qué archivo y en qué página. Eso el backend hoy **no lo tiene** y es genuinamente útil → propuesta N2 |
| `tools/motor_glosas_hus.py` | 399 | Cero llamadores. Prototipo pre-API que hace por conteo de frecuencias lo que hoy hacen `glosa_service` + `few_shot_gold` + `excel_radicable` | Nulo | Nada. Además comparte nombre con el proyecto entero, lo que garantiza confusión permanente |
| `responder_glosas_dgh.py` (746) + `login_dg.py` (457) + `dump_dg.py` (180) | 1.383 | **Nunca respondió una glosa real**: no graba por defecto, solo procesa la primera objeción de cada factura, y funciona por coordenadas de pantalla fijas ("modal en 360,166 @ 1920x1080"). Pendiente de `--calibrar` desde el 30-jun | Medio: el DGH es el único lugar donde la glosa existe contablemente | El camino correcto no es un bot que clickea a ciegas sobre un sistema contable, sino el **adaptador DGH de dos direcciones** (leer objeciones / escribir respuestas) con un test de contrato por dirección. Ese adaptador **no es una función suelta: es parte del entregable de N3**. **Regla dura: estas 1.383 líneas no se borran hasta que el adaptador esté en producción** — el DGH es la etapa E3 y no puede quedarse sin ninguna automatización |
| `tools/evidencias_a_pdf.py` | 115 | Duplicado de `evidencias_a_word.py`, y le falta justo lo que lo haría útil: el número de factura como encabezado de cada página | Nulo | Nada |
| Los 4 lanzadores `.cmd` de doble clic (`UNIR_PDFS`, `INFORME_BAJA_CARTERA`, `PDF_A_CMD`, `adres/VALIDAR_FURIPS`) | 1.096 | Batch de Windows inauditable e inteseable. `PDF_A_CMD.cmd` renombra PDFs a extensión `.cmd`, que Windows trata como ejecutable. **No son los bots RPA** (esos son cuatro y se conservan): son envoltorios de doble clic | Se pierde la única concesión de usabilidad del repositorio | **Conservar la idea** (doble clic, cero consola) y matar la implementación: pasa a ser una acción del Agente HUS (propuesta N7) |
| **Subtotal** | **3.720** | | | |

Dos aclaraciones que evitan un error caro. **Primera:** la cadena de 8 scripts de notas crédito (2.682 líneas que el operador encadena a mano) **no se borra, se colapsa** en un solo comando con etapas — estimación conservadora: 2.682 → ~700 líneas. **Segunda:** `scoreboard.py`, `scoreboard_live.py` y `correr_golden_set.py` **no se borran, se mudan** de `tools/` a `scripts/dev/`, para que `tools/` signifique una sola cosa ("automatización de la operación") y no un cajón de sastre.

---

### 5.5 Catálogos duplicados: una sola fuente de verdad

Esto es el principio §3 del blueprint ("Nunca existirán dos lugares con la misma información") aplicado con nombres y apellidos. En cada fila hay un ganador y el resto desaparece **después** de migrar el contenido. La columna de líneas cuenta **solo lo que no está contado en otra subsección**, para que el total de 5.7 no infle nada dos veces.

| Concepto | Cuántas veces existe hoy | Consecuencia real y verificada | Quién gana | Qué desaparece | Líneas (netas) |
|---|---|---|---|---|---|
| **Catálogo de normas** | 4 + un grafo | Dos corpus de 131 normas cada uno con **solo 20 nombres en común**: el auditor puede encontrar en la biblioteca una norma que el validador de citas marcará como inexistente en el dictamen. Y los plazos del Art. 57 se contradicen entre `normativa.py:30` y `glosa_ia_prompts.py:749` | `normativa_completa.py` (único con texto literal), migrado a datos editables | `CATALOGO_NORMAS` (955 líneas, `consulta_normativa.py:133-1087`), `normativa.py` (339 l), el índice TF-IDF, el grafo | **~1.290** (el grafo y el índice ya se contaron en 5.1) |
| **Ficha de contrato por EPS** | 3 | **Editar un contrato por pantalla es placebo**: `get_contrato` prioriza el diccionario `CONTRATOS_HUS` (`glosa_ia_prompts.py:59-299`) sobre la BD. Verificado contra la base real: 15 de las 17 columnas de `contratos` están vacías en las 13 filas existentes | La tabla `contratos`, con vigencia real | `CONTRATOS_HUS` (241 l) y `CONTRATOS_DEFAULT` (`main.py:82-96`, 15 l) — **el contenido se migra, no se tira** | **~255** |
| **Perfil de pagador** | 3 | El mismo pagador descrito de tres maneras que nadie reconcilia (`data/perfiles_radicacion.json` con 12 entidades, `perfil_eps.py`, constantes dentro de cada bot) | Un **Perfil de Pagador** único (propuesta N4), extendiendo el contrato que ya funciona en `radicar_facturacion.py:266-281` | `perfil_eps.py` y las constantes de los bots | **~175** |
| **Códigos de soporte ADRES** | 6 | `PDX` significa dos cosas clínicas distintas según el archivo: el asistente puede concluir que hay descripción quirúrgica cuando lo que hay es un resultado de apoyo diagnóstico | Un catálogo versionado en `data/` con los 24 códigos de la Res. 2284/2023 y los alias reales del HUS | Los otros cinco | **~130** |
| **Familia de glosa** | 3 taxonomías | `CL` = "pertinencia clínica" en el backend y "calidad" en un asistente; un código `PT` que el backend no conoce | `catalogo_glosas.py` (Anexo Técnico 3) | Las otras dos. El Perfil declara cómo se llama cada familia **en la planilla de ese pagador**, y el motor traduce | **~110** |
| **Estados de la glosa** | 3 máquinas + 1 bypass | `PATCH /glosas/{id}/estado` (`glosas.py:2580`) acepta 11 estados **sin validar una sola transición**; `POST /workflow/{id}/transicionar` no comprueba rol ni propiedad mientras el otro camino sí | Una máquina con dos ejes (estado interno / estado frente a la EPS) | El bypass y una de las dos máquinas | **~140** |
| **"Glosa cerrada"** | 117 redeclaraciones | Una glosa RATIFICADA cuenta como cerrada en 13 pantallas y como abierta en las otras. **Los KPIs de dos pantallas del mismo sistema no pueden cuadrar** | Un enum en el modelo con `es_cerrada()` / `es_decidida()` | Las 117 constantes literales | ya contadas en 5.2 (115 viven en `glosas_stats.py`) |
| **"Valor recuperado"** | 5 fórmulas | Cuatro conviven **en la misma barra de pestañas del coordinador**. Una de ellas (`glosas_stats.py:4103`) hace `valor_recuperado or valor_objetado`: como 0 es falso en Python, toda glosa levantada sin valor registrado suma su objetado completo — y ese es justo el número que el auditor lee mientras redacta | Un `MetricasService` único (propuesta **N8**) | Las otras cuatro | ya contadas en 5.2 |
| **Score de confianza** | 6 escalas | El número más grande y prominente de la pantalla (`_calcular_score`) es el único que **no mide calidad**: es una heurística estática por tipo de glosa (extemporánea=99, ratificación=92, tarifa=75) | `confidence_scorer` (el único con desglose accionable) | Las otras cinco, derivadas por umbrales | **~180** |
| **Generador de PDF radicable** | 4 | Tres generadores de cliente estampan un **"Nº OBJECIÓN" generado con `Math.random()`** en el documento que se radica ante la EPS (`index.html:18095`, impreso en `:18192`), e imprimen "Elaboró: X · Confirmó: X" con la misma persona | `services/dictamen_pdf.py`, con consecutivo persistido en BD | Los tres de cliente | ya contadas en 5.6 (~330, frontend) |
| **Motores de generación en lote** | 4 | Cuatro concurrencias distintas (secuencial / 2 / 5 / n-a) y cuatro sets de enriquecimiento: **la misma glosa produce un dictamen de calidad distinta según por qué puerta entró**. Solo uno tiene las defensas anti-gasto que nacieron del incidente de $14,50 en 251 llamadas | Un `ResponderGlosa.ejecutar()` + un ejecutor de lotes | Los otros tres, reducidos a adaptadores de 20 líneas | ya contadas en 5.1 y 5.2 |
| **Sistemas de few-shot** | 3 | En una sola petición el modelo recibe hasta 6 ejemplos y **tres órdenes incompatibles**: "no copies literal" / "COPIA EL ENCABEZADO VERBATIM… ANULA cualquier REGLA DURA del system prompt" / "úsalas como patrón, no las copies" | Un selector único con prioridad: precedente propio ganado → Gold aprendida → banco HUS | Los otros dos (hoy el orden está exactamente invertido) | **~120** |
| **Subtotal neto** | | | | | **~2.400** |

---

### 5.6 Pantallas rotas y superficies muertas del frontend

`static/index.html` son 23.125 líneas con 554 declaraciones de función, 51 variables globales, 428 asignaciones a `.innerHTML`, 2.216 estilos inline y 288 `!important`. Toda la carpeta `static/` (html + js + css) son 26.728 líneas. No todo se borra en la Fase 6 (la reescritura componentizada es otra fase), pero **esto sí**:

| Qué se borra | Líneas | Por qué |
|---|---|---|
| Ítem de menú "Salud Total" + su pantalla | ~60 | Ítem de primer nivel, **habilitado explícitamente para el rol AUDITOR**, cuyos dos botones dan 404 desde mayo de 2026. El usuario entra, sube un archivo, pulsa y no pasa nada. Coherente con la decisión de 5.1: Salud Total se borra |
| Botón flotante de nota privada + panel | ~90 | Siempre visible; el usuario escribe y **pierde lo escrito** al guardar |
| 3 paneles inalcanzables (multi-concepto, detector en masa, simulador) | ~1.500 | Existen completos, con CSS dedicado y endpoints vivos, y **no tienen ítem de menú**; sus entradas en la paleta de comandos fallan en silencio |
| Barra de navegación legacy (10 botones `display:none`) | ~30 | Invisible desde hace meses, y `tab()` la recorre en **cada cambio de pantalla** |
| 2 de las 3 paletas de comandos + 1 de los 2 modales de atajos + 2 de los 3 modos focus | ~500 | **Ctrl+K abre tres overlays apilados**; la tecla `/` deja la aplicación tapada por una capa imposible de cerrar (hay que recargar y se pierde la glosa que se estaba redactando) |
| `sinac-asistente.js` completo | 227 | Se descarga en cada visita, deja un `setInterval` corriendo para siempre y **jamás hizo una petición** por leer la clave de token equivocada |
| Paleta de `sinac-ux.js` (o el archivo entero) | 331 | Sus 14 acciones emiten un evento `sds-nav` que **nadie escucha**; su acción "Cerrar sesión" hace GET a una ruta declarada POST → 405 |
| Los 2 sistemas de comentarios | ~150 | Ambos completos, ambos inalcanzables |
| 12 funciones sin ningún llamador | ~400 | Entre ellas `registrarResultadoConciliacion`, que es **el cierre contable del proceso** |
| 3 generadores de PDF de cliente | ~330 | Ver 5.5: número de objeción inventado en un documento oficial |
| Motor de lote de cliente + 2 indicadores de progreso falsos | ~270 | Un `setInterval` cada 200 ms **apaga a propósito** el indicador que el propio análisis acaba de encender |
| Archivos huérfanos: `terapia-fisica-paciente-encamado.html` (316) e `importar-masiva.html` (336) | ~652 | Cero referencias en todo el repositorio. El primero **ni siquiera pertenece al dominio de glosas**. Sale también `docs/presentacion-ia.html`, duplicado byte a byte de `static/presentacion-ia.html` (653 líneas más, que no suman aquí porque `docs/` no es código de producción) |
| Las ~22 llamadas del frontend a rutas que no existen en el backend: **21 se borran, 1 se resucita** | ~190 | Se borran `/push/*`, `/noticias/*`, `/notas-privadas/*`, `/presets-filtros`, `/chat-history/*`, `/comentarios-thread/*`, `/api/salud-total/*`, `/auditor-forense/*`. **No se borra `/autopilot/preparar-dia`** (`index.html:7112`): el router se removió en la ronda 29 (`app/main.py:1207`) y hoy el botón devuelve 404, pero "Preparar el día" es la automatización de mayor retorno del producto. Frecuencia de uso hoy: **nula, porque está roto**. Se resucita en el primer paquete del roadmap |
| **Subtotal** | **~4.730** | |

Y una consolidación que no es borrado pero cuenta como desaparición para el usuario: **de 26 pantallas a ~14, agrupadas en los 9 módulos de §3.5** (los 9 módulos no son 9 pantallas: son 9 entradas de menú que contienen esas ~14 superficies). Cuatro paneles de reportes (Mando, Dashboard, Cobranza Live, Resumen del mes) muestran el mismo dato con distinto corte; el propio código documenta el pedido del cliente — *"4 botones que sacan la misma info → consolidar en uno"* (`index.html:12386-12390`) — y la respuesta del equipo fue **añadir una quinta superficie sin quitar ninguna de las cuatro**. En la 2.0 se quitan tres. Igual: siete superficies distintas responden "¿qué se vence?" consultando los mismos dos endpoints; queda una, ubicada donde se actúa.

---

### 5.7 Cuánto desaparece y qué se gana

| Bloque | Líneas fuera (aprox.) |
|---|---|
| Módulos muertos del backend (5.1) | 4.833 |
| Endpoints sin interfaz dentro de routers vivos (5.2) | 24.400 |
| `tools/` muerto y lanzadores de Windows (5.4) | 3.720 |
| Catálogos duplicados que pasan a datos (5.5, neto) | 2.400 |
| Frontend muerto y roto (5.6) | 4.730 |
| **Total código de producción** | **≈ 40.100 líneas** |

Sobre un total verificado de **147.085 líneas** de producción (`app/` 100.259 + `tools/` 20.098 + `static/` 26.728), eso es **algo más del 27 % del sistema**. A eso se suman varios miles de líneas de pruebas que hoy existen para probar código que nadie ejecuta.

**El corte que necesita el roadmap.** El borrado se ejecuta en dos paquetes distintos, y estas son las dos cifras que deben usarse aguas abajo, no otras:

| Paquete | Alcance | Líneas |
|---|---|---|
| **Backend** (5.1 + 5.2 + 5.4 + 5.5) | No toca ni un píxel de la interfaz; se puede hacer con la aplicación en producción | **≈ 35.350** |
| **Frontend** (5.6) | Requiere una ventana de despliegue y aviso a los gestores | **≈ 4.730** |

**Qué se gana, en términos que se notan:**

1. **Menos superficie de bugs, y no de cualquier tipo.** Los bugs replicados viven justamente en el código muerto: `ESTADOS_CERRADOS` copiado 117 veces significa que corregir un criterio de negocio hoy exige editar 117 sitios coherentemente. Borrando `glosas_stats.py` desaparecen 115 de esas copias de un golpe.

2. **Menos RAM, que aquí es literal.** El contenedor de la aplicación corre con `mem_limit: 640m` (`docker-compose.yml:34`) en una VM de 1 GB (`fly.toml:62`), y el propio compose documenta por qué: *"con mem_limit el cgroup mata al uvicorn (exit 137)"*. Hay **45 lugares del backend que hacen `db.query(GlosaRecord).all()` sin filtro ni límite**; medido con el modelo real y 50.000 glosas, eso son +507 MB en **una sola petición**. Es decir: hoy dos usuarios pueden tumbar el servidor pulsando dos informes que nadie usa. Borrarlos es la mejora de estabilidad más barata disponible.

3. **Arranque más rápido y más seguro.** Ocho tablas menos que materializar en cada arranque, ~460 líneas de `ALTER TABLE` manuales (23 sentencias, `main.py:144-660`) fuera del arranque —`main.py` baja de 1.322 a ~400 líneas— y ~60 introspecciones de esquema menos por arranque. Y desaparece un riesgo real: hoy un `ALTER` puede fallar en silencio (`logger.warning`) y la aplicación arranca igual con un esquema distinto al que el código espera.

4. **Imagen más liviana:** salen `pywebpush` y `feedparser`, que solo estaban ahí para funciones fantasma.

5. **Menos superficie de ataque:** fuera `/pdf/ocr` (sin rate limit y con costo de tokens), `/alertas/enviar` (abierto a cualquiera), `/sistema/salud/publico` (ejecuta detección de anomalías sobre 30 días **sin autenticación**) y el middleware de multi-tenancy que finge un aislamiento que no existe.

6. **Cinco funciones que hoy fallan a la vista del usuario dejan de fallar** — porque dejan de estar. Eso es lo que devuelve la confianza en el resto del sistema, que sí funciona.

**Dos decisiones tomadas en esta fase (ya no quedan abiertas):**

- **El PHI: se borra `cifrado.py` y se dice la verdad en el reporte de cumplimiento.** Hoy el sistema declara que cifra los datos sensibles del paciente (`sistema.py:147`, y lo lista como capacidad "cifrado_simetrico") y **no cifra ni un byte**, porque `cifrado.py` no tiene un solo importador. Ante la Ley 1581/2012 eso es peor que no cifrar: es una afirmación falsa. La alternativa —cifrar de verdad `paciente`, `texto_glosa_original`, `dictamen` y `observacion_eps`— se descarta por dos razones concretas: haría imposible buscar y filtrar por esos campos, que es el 80 % de lo que el auditor hace todos los días; y el cifrado de columna sobre una base que vive en la misma VM que la clave no protege contra el único escenario realista (que alguien acceda al disco). **La protección del PHI en la 2.0 es control de acceso + auditoría de lectura**, y así se declara. El cifrado real se reserva para lo que sí lo necesita y donde ya está bien resuelto: las credenciales de portales de `credenciales_vault.py`. La corrección de las declaraciones de `/sistema` va en el mismo commit del borrado.
- **La firma: se elimina el módulo.** No se implementa firma con validez jurídica en esta fase porque exige un certificado de entidad de certificación, que es un proceso de contratación y no de desarrollo (ver 6.3). Lo que sí entra ahora es **dejar de declarar que existe**: se corrigen las tres afirmaciones falsas de `sistema.py` en el mismo commit en que sale `firma_digital.py`.

---

### 5.8 Lo que NO hay que borrar aunque lo parezca

Esta subsección existe porque el criterio "cero llamadores = borrar" produce un desastre si se aplica sin leer. Hay código feo, código dormido y código sin pantalla que es exactamente lo que **no** se puede reconstruir.

| Qué parece muerto o desechable | Por qué lo parece | Por qué NO se borra | Qué se hace en su lugar |
|---|---|---|---|
| **Las 32 "redes finales" de `glosa_service.py`** | Son parches en cascada cosidos por orden cronológico de bug (Rondas 2→49), dentro de un método de ~2.800 líneas con **73 `except` silenciosos en el propio método `analizar()`** (`glosa_service.py:4299-7097`; 84 en el archivo completo). Leídas de corrido parecen basura | **Cada una codifica un bug real de alucinación pagado con dolor**, fechado y con caso: EPS inventada, CUPS falsos, CUPS = número de factura, valores inventados, citas falsas descomilladas, contratos de OTRA EPS, sanción a la EPS por vicio de competencia. La **forma** es deuda; el **contenido** es el activo jurídico-técnico más valioso del repositorio | Migrar **una a una** a un registro ordenado de transformaciones, cada una con su test. La red de seguridad ya existe: **142 archivos en `tests/test_services/`**, de los cuales **41 ejercitan `glosa_service`** (48 en toda la suite de 626 archivos). **Regla dura: ninguna red final se borra si su test no sigue en verde en el pipeline nuevo** |
| **Las reglas 8.x del SYSTEM_BASE** (`glosa_ia_prompts.py:698-749`) | Son ~15 párrafos de texto dentro de un string de Python | Son la experiencia de 33 rondas de auditoría adversarial destilada de fallas reales: sanciones = vicio de competencia, nunca negar un contrato citado, no invocar falso silencio positivo, atacar la legalidad de la multa y no *Pacta Sunt Servanda*, cada norma citada una sola vez | Migran a **datos versionados**, editables sin deploy. Jamás se pierden |
| **`CONTRATOS_HUS`** (`glosa_ia_prompts.py:59-299`) | Es un diccionario hardcodeado, en el lugar equivocado, con prioridad indebida sobre la BD | El **contenido** es oro: números de contrato, NITs, factores tarifarios, vigencias, contactos nominales y matices normativos por EPS (el mecanismo causal laboral de Positiva, las exclusiones de Compensar). Lo construyó alguien que conoce el negocio | Se **migra** a las columnas estructuradas de `contratos`, junto con la lógica de matching endurecida de `get_contrato` (palabra completa para "ARL", candidato más específico para "POLICÍA NACIONAL ONCOLOGÍA", normalización de tildes) — que también nació de bugs reales |
| **La cola `/lotes` + `agente_lotes.py`** | Cero llamadas desde el frontend, el token viene vacío por defecto, y una de las auditorías propone eliminarla entera | **Aquí las auditorías se contradicen y hay que decidir.** Otras dos la señalan como lo mejor construido del repositorio: el trío `lotes` / `facturas_lote` / `tareas_lote` es el único lugar del esquema con responsabilidad única por tabla, FKs reales, índice único que garantiza idempotencia y estados como constantes centralizadas; y el agente tiene cola reclamable, reporte incremental, validación anti path-traversal y manejo del WAF de Cloudflare | **Decisión: no se borra, y sus ~1.100 líneas no cuentan en el total de 5.7.** No le falta diseño, le falta **pantalla** — y esa pantalla es la propuesta N7. Lo que sí se borra es el segundo agente paralelo: `jumpbox_sync` y `agente_lotes` se funden en **un solo Agente HUS** con una sola credencial |
| **`credenciales_vault.py` + `credenciales.py`** | Cero llamadas desde la UI; el equipo sigue usando un Excel con las claves | Es **el mejor módulo de seguridad del repositorio**: Fernet que falla cerrado (503 sin clave, no degrada a texto plano), separación buscar/revelar, motivo obligatorio, auditoría hasta de los intentos fallidos de descifrado | No se borra: **se termina**. Es la mayor ganancia de valor por línea escrita de todo el sistema (propuesta **N5**) |
| **`ml_ratificacion.py`** | 241 líneas, cero llamadores en producción | Es el **único** predictor que mira la base de datos del propio hospital para calibrar por EPS. El que el usuario sí ve (`riesgo_ratificacion`) no consulta la BD ni una vez: sus números son constantes escritas a mano y una lista de 5 "EPS difíciles" que ni siquiera son las del HUS | Sobrevive como base de la propuesta N10 |
| **El 40 % de cada bot que es DOM del portal** | Parece código repetitivo y sucio | Es conocimiento pagado con meses de producción: *"el datatable filtra con eventos de teclado — `fill()` nunca dispara el filtro"*, *"el modal es de UN SOLO USO por carga de página"*, *"partimos en tandas de 200 porque el modal se rompe"*, la sanitización sin tildes que el portal exige, las tres pasadas de SIMED porque GeneXus no persiste. **Eso no se reescribe: se hereda** | Se parte en núcleo compartido + perfil declarativo + **adaptador de portal**, y el adaptador se conserva casi textual. Son cuatro bots hoy (COOSALUD, SIMED-glosas, SIMED-soportes, DGH) y serán nueve cuando entren los cinco pagadores que el cliente ya nombró: por eso el núcleo compartido no es un lujo |
| **`recepcion_service.py`** (1.458 l) | Archivo enorme que mezcla 8 responsabilidades | Encapsula conocimiento de dominio irrecuperable: aliases reales de columnas del DGH, días hábiles con festivos colombianos, resolución difusa de gestor→email con delegación por vacaciones, y los textos fijos jurídicos que evitan quemar tokens | Se separa por responsabilidades, **sin tocar el contenido de las reglas** |
| **`excel_radicable.py`, `exportar_dgh.py` (26 columnas), `services/dictamen_pdf.py`** | Parecen tres generadores redundantes más | Son los **entregables reales**: lo que se radica ante la EPS y el formato obligatorio del DGH. La regla de oro de `excel_radicable` — si falta un metadato, degrada a texto genérico en vez de inventar un número — es política de casa | Se conservan; se les corrige la agrupación por pagador (hoy un lote multi-EPS sale titulado con el contrato de una sola) |
| **`quality_gate_recorder.py`** (170 l) | `registrar_run` no tiene un solo llamador y su tabla está vacía | La tabla está vacía **por una línea que falta**, no por un diseño equivocado. Como el Quality Gate se enciende de fábrica en la 2.0, el recorder es lo que convierte esa decisión en un número auditable | Se conecta (1 línea) y se le da pantalla dentro del panel de calidad. Lo que se borra es su router de estadísticas (ver 5.1) |
| **`plantillas_gold` (52 filas), `few_shot_gold`, `calibracion_dificultad`, `citation_verifier`, `detector_copia`, `detector_requiere_soportes`, los caminos sin LLM** | Módulos chicos, algunos sin pantalla | Son el 20 % que produce el 80 %: el único aprendizaje acumulativo, el anti-alucinación que sí corre, y los dictámenes a $0 y ~50 ms de las ratificadas y extemporáneas | Se conservan tal cual y se convierten en ramas de primera clase del pipeline |
| **Los comentarios con fecha e incidente** | "Comentarios viejos que se pueden limpiar" | *"incidente 3-jul-2026: compose inyectó SMTP_PORT vacío"*, *"C-4747/2007: sentencia fantasma por regex sin `\b`"*, *"antes el CSV se escribía entero recién al final"*. Esa memoria operativa vale más que la documentación | Migra al 2.0 con el código que explica |

---

## 6. Funciones nuevas que sí valen la pena (Fase 5 del encargo)

El filtro es la **regla suprema del blueprint (§20)**: las siete preguntas. Se evaluaron 21 candidatas; **12 pasaron**. La columna "Regla suprema" indica cuántas de las siete responde SÍ; nada por debajo de 5/7 entró. Las semanas son **semanas-persona** de desarrollo, no calendario.

### 6.1 Tabla maestra, ordenada por retorno

| # | Función | Problema real que resuelve | Beneficio medible | Impacto | Complejidad | Semanas | Regla suprema | Prioridad |
|---|---|---|---|---|---|---|---|---|
| **N1** | **Reloj de vencimientos del sistema, con escalamiento automático** | Hoy el vencimiento **viene escrito en una celda del Excel** de recepción y, si falta, la fila se descarta y la glosa nunca existe. Existe un estado NEGRO para lo vencido y **no dispara nada** | 3 facturas de junio (38 objeciones, **$20.054.751**) tenían plazo el 6 y el 8 de julio; nadie lo notó hasta el 22 de julio. Esa es **plata en riesgo por vencimiento**, no plata defendida | Plata directa | Baja | **2** | 7/7 | **1** |
| **N2** | **Expediente leído de verdad: fin del truncado + matriz de evidencia + abrir el soporte con un clic** | `PdfService` devuelve **como máximo ~7.050 caracteres** de cualquier PDF de más de 4 páginas, con el medio reemplazado por `...[PÁGINAS INTERMEDIAS OMITIDAS]...`; el camino automático limita a 3 archivos × 5.000 chars. Y el sistema indexa hasta 144.000 archivos para terminar mostrando **la ruta como texto** para copiar y pegar en el explorador | Un dictamen construido sobre 7 KB de una historia clínica de 200 páginas es un dictamen a ciegas, y eso se traduce en glosas ratificadas. El equipo ya lo comprobó por otro lado: pdfplumber devolvía "solo 7k chars de un PDF de 4MB → 0 cláusulas" | Tasa de levantamiento | Media | **4** | 7/7 | **2** |
| **N3** | **Puente Orquestador: el bot le pide la respuesta al motor y le devuelve el resultado — incluido el adaptador DGH de dos direcciones** | Ningún bot clasifica, analiza, genera ni guarda historial: **no hay una sola llamada HTTP que no sea al portal**. El puente entre las dos mitades es un Excel que viaja en el escritorio de una PC. Y el DGH —el único sistema donde la glosa existe contablemente— se alimenta a mano en las dos direcciones | En SIMED, el flujo con más volumen real, los bots procesaron **324 facturas y 597 objeciones en siete lotes**; de los tres últimos, por **$153.675.820**, el Excel está listo y la subida sin confirmar. El resultado vive hoy en un CSV en un escritorio, y el registro manual ya demostró estar **equivocado en 6 de 12 facturas** | Cierra el ciclo | Media-alta | **6** | 7/7 | **3** |
| **N4** | **Perfil de Pagador único y editable por la coordinación** | El mismo pagador está descrito en tres lugares que no se hablan, y los plazos legales aparecen de cinco formas distintas **incluida la documentación con la que se capacitó a los gestores** | Renovar un contrato o cambiar un factor tarifario deja de ser un despliegue de software y pasa a ser un formulario. Y editar por pantalla deja de ser placebo | Elimina la deuda raíz | Media | **4** | 7/7 | **4** |
| **N5** | **Panel del vault de credenciales de portales** | El backend está **completo, cifrado y auditado** y no tiene una sola pantalla; el equipo sigue pasándose en un Excel las claves de los portales de las entidades con las que radica (12 perfiles registrados hoy en `data/perfiles_radicacion.json`, y creciendo con cada pagador nuevo) | Mayor ganancia de valor y de cumplimiento por línea de código escrita en todo el sistema | Riesgo/cumplimiento | Baja | **1,5** | 6/7 | **5** |
| **N6** | **Conciliación sin Excel: acta que cierra la glosa y suma la plata** | El módulo entero se opera con `prompt()` del navegador: `panelCerrarActa` encadena **cinco**, y si el último trae un espacio en vez de un guion bajo **se pierde todo lo anterior**. Y `cerrar-acta` no transiciona la glosa ni escribe `valor_recuperado`: hay que registrar el resultado **otra vez** | La conciliación real del histórico (226 facturas, 4 actas, $277.231.324 glosados, $71.901.424 aceptados) **está en un TSV**; la tabla `conciliaciones` tiene 0 filas | Cierre del embudo | Media | **4** | 7/7 | **6** |
| **N7** | **Centro de Automatización: un solo Agente HUS y un tablero de bots** | El frontend **no sabe que los bots existen** (0 ocurrencias de "RPA", "robot" o "Playwright" en 23.125 líneas). La interfaz real de los bots es PowerShell con rutas de 120 caracteres, y el runbook de producción es un `.md` que alguien copia y pega en un chat | Motor de orquestación ya construido (6 endpoints, 3 tablas, agente de escritorio, 403 líneas de tests) al que **solo le falta el tablero**. Hoy hay dos agentes distintos en la misma PC, con dos tokens y dos configuraciones, para cuatro bots; serán nueve | Operación diaria | Media | **5** | 7/7 | **7** |
| **N8** | **Un solo número: definición única de recuperado/cartera + informe mensual firmable** | "Valor recuperado" tiene **cinco fórmulas**, cuatro visibles a un clic de distancia en la misma barra de pestañas. La cartera se suma por glosa y no por factura: una factura con 5 glosas abiertas reporta **5 veces su saldo** | Ningún tablero es hoy firmable por un auditor de cartera. El modelo correcto ya está escrito, pero **fuera** de la aplicación (`tools/tablero_cartera.py`, que razona por factura) | Credibilidad gerencial | Media | **3** | 6/7 | **8** |
| **N9** | **Expediente único de la factura, con línea de tiempo defendible** | La historia está partida en tres sitios que no se cruzan, la misma tabla se audita con **dos nombres distintos** (19 sitios "historial", 11 "glosas") y el dictamen se versiona en **3 de 19** puntos de escritura. Borrar una glosa es un DELETE físico que arrastra por CASCADE conceptos, versiones, comentarios y conciliaciones, mientras la papelera solo fotocopia la cabecera | Para una glosa que llegue a conciliación o a la SuperSalud, **hoy el expediente no es defendible**. Y un proceso automático puede sobrescribir el documento de defensa legal sin dejar rastro (`ia_auditora_proactiva.py:183`) | Riesgo jurídico | Alta | **7** | 7/7 | **9** |
| **N10** | **Probabilidad de ganar calibrada contra los resultados del HUS + reporte de acierto** | El único indicador que el usuario ve **no consulta la base de datos ni una vez**: constantes "según histórico nacional" y una lista fija de 5 EPS difíciles que no son las del HUS. El que sí mira `decision_eps` tiene cero llamadores | Y hoy **nadie mide la predicción contra el resultado real**. Sin eso, el número no sirve para decidir contra quién pelear | Decisión del auditor | Media | **3** | 6/7 | **10** |
| **N11** | **Copiloto contextual por pantalla** (blueprint §15) | El chat de glosa promete *"preguntá lo que quieras… ej: citá la cláusula octava"* y detrás hay **8 respuestas fijas por palabra clave**: ese ejemplo exacto cae siempre en "No pude responder eso con certeza" — y encima consume cupo de IA sin gastar un token | El esqueleto real ya existe y funciona: el Asistente Maestro, con 9 herramientas que consultan datos verdaderos (soportes, contratos, tarifas, normas, precedentes) y loop de 6 turnos | Adopción | Media-alta | **5** | 6/7 | **11** |
| **N12** | **Captura automática del lote de glosas en el portal del pagador** | Es el hueco más caro del proceso: **si nadie baja el lote a tiempo, el plazo corre igual**. Hoy es bajar un ZIP a Descargas y descomprimirlo | Convierte un evento invisible en una entrada auditable con sello de fecha — que es justo lo que activa el reloj de N1 | Previene pérdida total | Alta | **6** | 6/7 | **12** |

**Total: 50,5 semanas-persona.** Es **contenido de trabajo, no calendario**, y **está dentro** del esfuerzo que el roadmap de §10 reparte entre las versiones: las semanas de §10 deben contener estas doce funciones, nunca sumarse a ellas. Si un paquete de §10 sale por debajo de la suma de las funciones que contiene, el que está mal es el paquete. N1, N5 y N8 son independientes y pueden ir en paralelo desde la primera semana; N2 y N3 son las que más plata mueven y deben arrancar en cuanto N4 tenga el Perfil de Pagador en pie.

---

### 6.2 Por qué cada una pasa el filtro (y qué la haría fracasar)

**N1 — Reloj de vencimientos.** El sistema calcula el vencimiento desde el **perfil del pagador** y la fecha de notificación, no desde una celda; y una glosa que entra en rojo escala sola **al coordinador, no al gestor** (si el gestor pudiera resolverlo, ya lo habría hecho). Reemplaza además las siete superficies que hoy responden "¿qué se vence?" por una sola, ubicada donde se actúa. El caso que la justifica es de este mes: tres facturas de junio con plazo el 6 y el 8 de julio que nadie vio hasta el 22 — **$20.054.751 en riesgo por vencimiento**, con el Excel de respuesta listo y sin subir. **Lo que la haría fracasar:** dejar el criterio de "cerrada" sin unificar — hoy una glosa RATIFICADA cuenta como abierta en 117 sitios y como cerrada en 13, y el reloj heredaría esa contradicción. Por eso el enum de estados (5.5) es prerrequisito.

**N2 — Expediente leído de verdad.** Tres piezas en una sola historia de usuario: (a) lectura completa con troceo y selección **por relevancia, no por posición en el documento**, con un único presupuesto de tokens configurable en un solo lugar en vez de cinco caminos independientes de lectura de PDF; (b) la **matriz de evidencia** rescatada del script suelto — por cada soporte que la familia de glosa exige: si está, en qué archivo y en qué página; (c) un endpoint que **devuelva el archivo** (hoy no hay un solo `FileResponse` en el router de soportes) con visor en línea y auditoría de acceso. Hoy el banner dice "✓ 12 soportes detectados" y la IA leyó 3 pedazos de 5 KB: el gestor firma un dictamen creyendo que se analizó el expediente completo. **Lo que la haría fracasar:** no arreglar antes que el indexador se ejecuta dentro del event loop sin `asyncio.to_thread` — con el índice frío, un `rglob` sobre el share congela todo el servidor.

**N3 — Puente Orquestador.** Es literalmente el §6 del blueprint. El bot deja de recibir un Excel que un humano ya resolvió y pasa a pedirle las respuestas a la API, y al terminar **escribe él el estado** y sube el pantallazo al expediente. Dos scripts (`extraer_respuestas_glosa.py`, `convertir_tramite_masivo.py`) existen únicamente como pegamento manual entre "el sistema sabe la respuesta" y "el bot la escribe": desaparecen. **El adaptador DGH de dos direcciones es parte de este entregable, no una función aparte**: leer objeciones y escribir respuestas contra el sistema contable, con un test de contrato por dirección. Se le asignó explícitamente porque el DGH es la etapa E3 —el cuello de botella estructural del proceso— y el plan borra el bot actual: **la regla es que ese bot no se borra hasta que el adaptador esté en producción**, para no quedarse sin ninguna automatización en el único lugar donde la glosa existe contablemente. **Lo que la haría fracasar:** traducir mal los estados. El CSV devuelve hoy `OK_CALIDAD_ABIERTA`, `TERMINADA_SIN_CARTEL`, `PENDIENTE_PDX`, `NO_EN_BOLSA`; un auditor de cartera necesita leer *"esta factura quedó cerrada / le falta un soporte / la EPS ya la había cerrado"*. El vocabulario es parte del entregable.

**N4 — Perfil de Pagador.** Un solo registro por entidad con **todo lo que cambia entre pagadores**: canal (portal con bot / portal sin bot / correo / ADRES), identidad del portal, formato de factura (largo `HUS0000487523` vs corto `HUS487523` — hoy eso se recuerda con un flag en cada corrida), nomenclatura de soportes, CUV obligatorio sí/no, régimen (para saber si aplica extemporaneidad, **en vez del texto mágico "NO APLICAR EXTEMPORANEIDAD" que hoy alguien escribe a mano en una celda**), plazos, estilo de respuesta, mapeo de columnas de su planilla, y **contrato y base tarifaria vigentes por FECHA DE ATENCIÓN**. Esto último ya costó plata: en el Dispensario, contrato 287 hasta el 30-nov-2025 (SOAT −15 %) y 440 desde diciembre (SOAT −20 %), y **372 de 444 glosas venían mal marcadas "SIN CONTRATO"**. El contrato de perfil ya existe y funciona (`radicar_facturacion.py:266-281`, con 12 entidades en JSON): se **extiende**, no se reinventa. **Lo que la haría fracasar:** que el catálogo hardcodeado siga teniendo prioridad sobre la BD.

**N5 — Panel del vault.** Es la única función de esta lista donde el trabajo ya está hecho: falta una pantalla de listar / buscar / revelar con motivo. Con eso el Excel de claves sale del hospital. **No pasa 7/7** porque no automatiza una tarea repetitiva (pregunta 1): resuelve un riesgo. Entra igual porque las otras seis son SÍ rotundos.

**N6 — Conciliación sin Excel.** El acta del sistema debe tener **exactamente los campos del TSV que hoy se firma** (radicado, acta, factura, nota crédito, valor factura, total glosas, valor aceptado), imprimirse desde el sistema y, al cerrarse, **transicionar la glosa y alimentar el dashboard en una sola acción**. Se acaban los cinco `prompt()` encadenados y la doble digitación. Además la transición "la EPS ratificó → crear la conciliación" pasa a ser automática: el sistema ya tiene todos los datos. Y el resultado de la audiencia debe alimentar el aprendizaje —hoy es un callejón sin salida: ganar o perder una conciliación **no cambia nada** en la generación futura. **Lo que la haría fracasar:** dejar los participantes como texto libre. Un acta legal cita a las personas con nombre y cargo; eso es una tabla, no una celda.

**N7 — Centro de Automatización.** Lanzar, ver, detener y auditar un bot desde la aplicación, con el perfil del pagador resolviendo qué bot corre (hoy es un diccionario hardcodeado que solo conoce uno). Un solo Agente HUS instalado una vez, con una sola credencial, que sincroniza el share **y** ejecuta bots. Aquí está la aritmética que decide la prioridad: unificar hoy, con **cuatro bots**, cuesta una fracción de lo que costará con **nueve** (los cinco pagadores que el cliente ya nombró: SAVIA, EMSSANAR, VCO, MUTUAL SER, FOMAG). Se conserva el principio que el propio equipo ya acertó: *"cero PowerShell, cero setx"*. **Lo que la haría fracasar:** volver a construir el motor sin la pantalla. Ya pasó una vez.

**N8 — Un solo número.** Un `MetricasService` que defina en un solo lugar las cuatro palabras del negocio (DECIDIDA, LEVANTADA, RECUPERADO, CARTERA), con la definición **escrita en la propia pantalla** ("Recuperado = suma de `valor_recuperado` de glosas con decisión de la EPS registrada entre el 1 y hoy"), la factura modelada como entidad de primera clase, y un informe mensual con tres salidas (pantalla, PDF, Excel) que reemplace los cuatro actuales. **Decisión tomada: el sistema mide con la columna `valor_recuperado` registrada, no con la derivada objetado − aceptado.** La derivada es automática pero mide "lo que no aceptamos", no "lo que nos pagaron"; la registrada exige disciplina de captura y es la única que un auditor puede defender ante un Comité de Cartera. La derivada queda como control de consistencia, nunca como el número que se publica. **No pasa 7/7** porque no reduce clics: reduce discusiones.

**N9 — Expediente único.** Un solo nombre de entidad en el log, versionado del dictamen en los 19 puntos de escritura y no en 3, borrado lógico real (columna `eliminado_en` + filtro global) en vez del DELETE físico actual, y una línea de tiempo por **objeción**: recibida → asignada → respondida → radicada → ratificada → conciliada → nota crédito → pagada, donde el estado **lo escribe el bot al terminar**, no una persona que se acuerde de apretar un botón. Es la fase más cara de la lista y la que más protege al hospital.

**N10 — Probabilidad calibrada.** Se fusionan los tres predictores en uno: la estructura del que aprende de la BD, con la presentación del que ya tiene interfaz (0-100 con factores legibles). Y se agrega lo que hoy no existe en ninguno: **medir lo predicho contra `decision_eps` real y publicar el acierto**. Un número que no se contrasta no es una predicción, es un adorno.

**N11 — Copiloto contextual.** Sobre el Asistente Maestro, no sobre el chat de glosa (que se elimina). Viendo un PDF: *"falta la firma del auditor"*. Viendo una conciliación: *"existe una idéntica de 2025"*. En contratos: *"la cláusula 18 respalda esta respuesta"*. Reutiliza los cuatro *lookups* a datos reales que ya funcionan (cláusula de contrato, glosa similar, tarifa pactada, norma). Requisito previo no negociable: **un cliente de IA compartido que registre siempre el costo** — hoy 11 de 12 puntos que llaman a Anthropic no registran nada, y Groq y Gemini nunca registran, así que el panel de "costos de IA del mes" muestra una fracción del gasto real.

**N12 — Captura automática.** Un agente por pagador que hace login, descarga el lote y lo registra con sello de fecha. Es la etapa E2 del proceso y hoy es 100 % manual. Va última porque depende de N4 (el perfil que dice cómo entrar a cada portal) y N7 (el agente que lo ejecuta), y porque es la más frágil: cada portal cambia por su cuenta.

---

### 6.3 Lo que NO pasó el filtro (y por qué)

Decisiones tomadas, no dejadas a evaluación posterior:

| Candidata | Veredicto | Razón |
|---|---|---|
| Predicción de glosa **antes** de radicar (`predictor_glosas.py`, 234 l, ya escrita) | **No** | Es otro producto: audita facturación previa a la radicación. El motor responde glosas ya recibidas (pregunta 7: no aporta valor al auditor de glosas hoy) |
| Notificaciones push web | **No** | Infraestructura completa sin backend, y el canal correcto ya existe: correo + badge. Añadir un tercer canal a los tres que ya se solapan empeora el problema (pregunta 3: no reutiliza, duplica) |
| Digest por WhatsApp / Telegram | **No** | 215 líneas que nunca enviaron un mensaje. El correo por gestor con su Excel-respuesta ya funciona y es el canal que el equipo usa |
| Pipeline multi-agente LLM (`multi_agent.py`) | **No** | 3× costo por diseño, 1 de 3 agentes implementado, apagado desde siempre. Los "agentes" que el blueprint pide (§7) se resuelven con enriquecimiento determinista a costo $0, que ya existe y funciona |
| Búsqueda semántica con re-ranking por LLM | **No** | No es semántica: es `LIKE` + un modelo ordenando 80 filas, a un call de Sonnet por búsqueda. BM25 local ya está implementado y da resultados equivalentes a costo cero |
| Grafo de conocimiento normativo | **No como módulo** | Idea ambiciosa, ~30 aristas a mano, detrás de un flag apagado. Las aristas caben como un campo `relaciones` dentro del corpus único |
| Multi-tenancy / venta como SaaS | **No ahora** | El HUS es un hospital. Un middleware que lee un header y no filtra nada es peor que no tener nada. Si algún día se vende, se diseña con `tenant_id` en el modelo, no con un ContextVar |
| Firma digital con validez jurídica | **No en esta fase** | Exige certificado de entidad de certificación: es un proyecto de contratación, no de desarrollo. Lo que sí entra en la Fase 6 es **dejar de declarar que existe** (ver 5.7) |
| Cifrado en reposo del PHI en la base de datos | **No** | Rompería la búsqueda y el filtrado sobre los cuatro campos que el auditor usa todos los días, y la clave viviría en la misma VM que la base: protege contra un escenario que no es el real. La protección del PHI es control de acceso + auditoría de lectura, y así se declara (ver 5.7) |
| Aplicación móvil / PWA usable en teléfono | **No como función nueva** | El diagnóstico es correcto (en un teléfono de 390 px al dictamen le quedan ~110 px), pero la solución es **una media query** en la fase de limpieza, no un desarrollo |
```

---

## 7. El flujo ideal del auditor (Fase 7)

Esta sección no propone pantallas nuevas: propone **borrar pasos**. La Fase 7 del roadmap (`docs/SINAC_OS.md:191`) se llama "optimización continua", y la única forma honesta de optimizar es medir primero cuántos clics, cuántas ventanas y cuántas re-digitaciones cuesta hoy defender una glosa. Todo lo que sigue está medido sobre el código real y sobre la bitácora de operación del hospital.

---

### 7.1 Cómo trabaja hoy: un día real, paso a paso

**07:50 — El auditor abre el sistema y el sistema no le dice qué es urgente.**
La aplicación arranca en el panel **Analizar**, con un formulario en blanco de 13 campos (`static/index.html:2125`). Al mismo tiempo dispara doce peticiones de golpe —dashboard, historial completo, alertas, analítica y hasta un ticker de noticias RSS del sector— para cinco paneles que el auditor no ha abierto (`static/index.html:6711-6750`).

El aviso que sí importa —**"N glosa(s) vencen en las próximas 24h · Valor en riesgo: $X"**, con la aclaración jurídica de que el Art. 57 de la Ley 1438 protege a la EPS y no al prestador— existe, está bien escrito y **sólo se pinta dentro del panel "Mis glosas"** (`static/index.html:13546-13573`). Es decir: el mejor aviso del sistema vive en una pantalla que no es la que abre.

**07:52 — El botón que resolvería la mitad del día está enterrado y, además, está roto.**
Existe un botón **"⚡ Preparar el día"** cuyo código de pantalla aplica el texto fijo a las glosas RATIFICADAS y EXTEMPORÁNEAS pendientes, las marca como RESPONDIDAS, es idempotente y explica el resultado en español (`static/index.html:7108-7149`). Tres problemas verificados:

1. Vive en el **estado vacío** del panel Analizar (`static/index.html:2370`), o sea que sólo se ve si no hay un dictamen en pantalla; en cuanto se analiza la primera glosa, `renderResult` borra ese bloque y el botón desaparece hasta recargar (`static/index.html:16440`).
2. Llama a `POST /autopilot/preparar-dia` (`static/index.html:7112`), ruta cuyo router **fue eliminado en la ronda 29** (`app/main.py:1207`: "autopilot: removido en la limpieza de ronda 29").
3. Resultado: hoy el botón **devuelve 404 y un toast rojo**. Su frecuencia de uso real es **nula**, porque no funciona.

**Esto no es una automatización que haya que mudar de sitio: es una automatización que hay que resucitar.** El frontend está escrito y sirve; lo que falta es el endpoint del servidor. Es la pieza de mayor retorno por línea de código de todo el producto —cierra en un clic el 20-30 % del lote sin gastar un peso de IA— y hay que reconstruirla en el paquete **A0** de la versión 2.0 (§10.3), antes de que el Centro de Operaciones (7.5) pueda apoyarse en ella. Nadie notó que estaba caída precisamente porque estaba escondida.

**08:00 — Responder una glosa suelta: 12 a 14 clics y hasta 6 campos tecleados.**
El camino realista con exportación mide **12-14 clics**: desplegar EPS, elegir EPS, clic en el textarea, pegar, abrir el acordeón "Facturación", tipear factura, tipear radicado, dos fechas con calendario, "Analizar con IA", "Imprimir / PDF radicable", el diálogo del navegador y "Marcar como RESPONDIDA" con su confirmación (referencias: `static/index.html:2132, 2155-2156, 2160-2176, 2204, 2238, 16407, 16430`). El mínimo absoluto teórico es 4 clics, pero exige renunciar a factura, radicado, fechas y PDF.

De los 6 campos que teclea, **al menos 4 ya los tiene el sistema**: si la glosa entró por el Excel de recepción, `responderGlosa()` precarga factura, radicado y ambas fechas desde la base (`static/index.html:14338-14345`). Si arranca de cero, los vuelve a escribir.

**El campo más valioso está rotulado "opcional" y escondido.** El número de factura es el único dato que dispara tres automatizaciones ya construidas: trae de la base los N conceptos objetados de esa factura (`static/index.html:9461`), avisa si la factura ya fue cargada (`:9578`) y —lo más caro— hace que el servidor **lea solo** la historia clínica, los RIPS y la factura electrónica desde el disco de red (`app/api/routers/analizar.py:805-824`). Ese campo vive dentro de un acordeón cerrado por defecto rotulado *"Facturación · opcional"* (`static/index.html:2160-2164`). Consecuencia práctica: el auditor no lo llena, y termina buscando y subiendo los PDF a mano.

**Y lo que el sistema detecta, lo tira a la basura.** El endpoint `/analizar/preview` extrae del texto pegado el valor objetado, el valor facturado, el código de glosa, el CUPS y la descripción del servicio sin gastar un solo token de IA (`app/api/routers/analizar.py:1032-1046`); el panel "Detección automática" se los **muestra** al auditor y no los escribe en ningún campo ni los envía al backend (`static/index.html:21875-21891`). El auditor lee "$24.900 detectado" en pantalla y lo vuelve a teclear.

**08:15 — El dictamen sale, y la acción que cierra el caso queda última.**
Después del análisis se apilan hasta once sub-paneles (medallas, riesgo de ratificación, confianza, autopilot, ganadores históricos, auditor forense…) y luego 13 acciones. **"Marcar como RESPONDIDA"** —la que cierra el ciclo de negocio— queda al final de todo el scroll, con el mismo peso visual que "Copiar texto" (`static/index.html:16434`). Y el PDF que se imprime para radicar lleva un **número de objeción inventado con `Math.random()`** (`static/index.html:18095`, impreso como "Nº OBJECIÓN" en `:18192`) y firma "Elaboró: X · Confirmó: X" con la misma persona (`:18186-18187`).

**08:30 en adelante — La parte que de verdad mueve la plata ocurre FUERA del sistema.**
La operación SIMED del Dispensario son **siete lotes: 324 facturas y 597 objeciones** procesadas por los bots (`BITACORA.md:173-181`). De esos siete, los cuatro primeros (26-jun, 1-jul, 6-jul y 9-jul) figuran como subidos —el del 9 de julio, verificado al 100 %— y no traen valor registrado. De los **tres últimos, por $153.675.820, el Excel está listo y la subida sigue sin confirmar**: dos con estado literal *"Excel listo — confirmar subida"* (14 y 17 de julio) y uno con estado *"Excel listo — subir YA (plazos vencidos)"* (las tres facturas de junio). Nada de esto se produjo con la aplicación. El recorrido real, según la guía operativa y la bitácora:

| Paso real | Dónde ocurre | Evidencia |
|---|---|---|
| Bajar el ZIP con los PDF CRRP de Trámite de Objeción | Carpeta `Downloads` de una PC | `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` (receta estándar: `Expand-Archive … Downloads\<NOMBRE>.zip`) |
| Descomprimir a `D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_<fecha>\SOPORTES` | Explorador de Windows | ídem |
| `git pull` en `C:\temp-notas` | PowerShell | `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` §3 |
| Generar el Excel de respuestas | `tools/extraer_respuestas_glosa.py` (225 líneas) | digest S7 |
| Redactar las respuestas | **`glosa_motor.py`, que no está en el repositorio** — vive en el scratchpad de una sesión de chat | `BITACORA.md:254-256`; `find . -name 'glosa_motor*'` → vacío |
| Correr el piloto de 1 factura con navegador visible | PowerShell, ruta absoluta de ~120 caracteres | `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` §10 regla 4 |
| Correr el lote completo | `tools/responder_glosas_simed.py` (1.711 líneas) | digest S7 |
| Segunda pasada de verificación (debe dar 0 pendientes) | PowerShell otra vez | `BITACORA.md:227-229` |
| Leer el resultado | Un CSV en el escritorio, con estados tipo `TERMINADA_SIN_CARTEL`, `PENDIENTE_PDX`, `NO_EN_BOLSA` | digest S7 ("los estados que ve el usuario son jerga de programador") |
| Marcar radicada en la app | Botón manual que alguien debe acordarse de apretar | digest S14 ("el sistema no sabe si la respuesta se radicó") |
| Armar el PDF de evidencias | `tools/evidencias_a_pdf.py` | digest S7 |
| Conseguir el consecutivo institucional GI-33 | **Se le pide por chat a una persona, lote por lote** | `BITACORA.md:196-197` |
| Anotar el resultado del lote | A mano, en la bitácora | `BITACORA.md:174-182` |

El contexto para poder siquiera empezar tampoco está en el sistema: son tres archivos Markdown que el auditor **copia y pega como primer mensaje de un chat** cada vez que retoma un flujo (`docs/CONTEXTO_DISPENSARIO_GLOSAS.md`, `docs/CONTEXTO_DISPENSARIO_NOTAS.md`, `docs/CONTEXTO_COOSALUD.md`). La memoria del proceso es un ritual de copiar y pegar.

**Lo que este circuito ya costó, en plata y en riesgo:**

- **Tres facturas de junio con la respuesta lista y el plazo vencido** (HUS0000518186, HUS0000515107, HUS0000515773 — 38 objeciones, **$20.054.751**). Sus vencimientos eran el 6 y el 8 de julio; se descubrieron el **22 de julio revisando a mano** (`BITACORA.md:86-91`). Esa cifra es **plata en riesgo por vencimiento**, no plata defendida ni recuperada: el Excel de respuestas existe, la radicación en plazo no. El semáforo tiene un estado NEGRO para lo vencido (`app/services/recepcion_service.py:52-56`) pero **nada ocurre cuando una glosa entra en él**.
- Peor: la lista de alertas que la interfaz consulta **esconde justamente las vencidas**, porque filtra `dias_restantes > 0` (`app/repositories/glosa_repository.py:440-450`, consumido por `/glosas/alertas` en `app/api/routers/glosas.py:1587-1606`). La pantalla que existe para avisar de lo urgente oculta lo más urgente.
- **El registro manual estaba equivocado en 6 de 12 facturas**: cinco figuraban como "subidas OK" y ninguna tenía CUV válido (`docs/diagnostico_lote_v2_pendientes/INFORME_GERENCIA.md:39-47`). Por eso "Excel listo — confirmar subida" no se puede leer como "radicado".
- La conciliación real del histórico —226 facturas, 4 actas (AC000456/AC000618/AC000619/AC000862), $277.231.324 glosados de los que se aceptaron $71.901.424— **vive en un TSV**. La tabla `conciliaciones` de la base tiene **0 filas** (digest S14).
- El módulo de conciliación de la app, donde se negocian millones, se opera con **cuadros de diálogo del navegador**: `panelCerrarActa` encadena **cinco `prompt()`** —número de acta, fecha escrita a mano en formato YYYY-MM-DD, valor conciliado, resultado tecleando literalmente `ACUERDO_PARCIAL` con guion bajo, y observaciones— y si el último no coincide exacto, **se pierde todo lo anterior** (`static/index.html:20480-20498`). La decisión de la EPS, dato del que dependen todos los indicadores de recuperación, se captura escribiendo "LEVANTADA" a mano en un `prompt()` (`:20390`). En total: 44 `prompt()`, 44 `confirm()` y 12 `alert()`.
- Y aunque el acta se cierre, **no cierra nada**: `cerrar-acta` no transiciona la glosa ni escribe `valor_recuperado`, así que para que la plata conciliada aparezca en el tablero **el auditor debe registrar el resultado otra vez** por otra vía (`app/api/routers/conciliacion.py:290-324`).

**El diagnóstico en una frase:** el sistema tiene la mitad que piensa (`app/`) y la mitad que ejecuta (`tools/`), y **el puente entre las dos es un Excel que viaja en el escritorio de una PC** (`docs/SINAC_OS.md:225-230`). Ningún bot llama al motor: en los cuatro bots que existen hoy no hay una sola petición HTTP que no sea al portal (digest S7).

---

### 7.2 Cómo debería trabajar en SINAC OS

El recorrido nuevo, de la llegada de la glosa a la firma del acta. **El sistema propone; el auditor confirma.** Cada paso indica quién actúa.

**1. La glosa entra sola. (Sistema)**
Un agente de captura por pagador entra al portal, descarga el lote y lo registra con sello de fecha. Hoy este es el hueco más caro del proceso: si nadie baja el lote, el plazo corre igual, y ahí quedaron atrapadas las tres facturas de junio (digest S14, etapa E2). Para los pagadores sin portal (PPL, FOMAG, Policía) la puerta es el correo, no un adjunto que alguien recuerda bajar.

**2. El reloj lo pone el sistema, no una celda. (Sistema)**
El vencimiento se calcula desde el **perfil del pagador** y la fecha de notificación, no desde la columna VENCE del Excel —que hoy, si viene vacía, **descarta la fila y la glosa nunca existe** (`app/services/recepcion_service.py:1021-1023`). Una glosa que entra en rojo escala sola al coordinador, no al gestor.

**3. Triage a costo cero. (Sistema)**
Las RATIFICADAS y EXTEMPORÁNEAS se cierran con texto fijo, sin llamar a la IA: es una decisión de negocio ya tomada, fechada y justificada por costo (`app/services/recepcion_service.py:1073-1080`). Las glosas de tarifa se resuelven con el evaluador determinista que ya existe (`app/services/tarifa_lookup_service.py`, 649 líneas). Esto es "Preparar el día" corriendo solo y sobre todo el lote — **con el endpoint reconstruido**, porque hoy la ruta que ese botón invoca no existe (7.1).

**4. El expediente se arma solo. (Sistema)**
Con el número de factura —que deja de ser "opcional" y pasa a ser la llave— el sistema trae los conceptos objetados de la base, la historia clínica, los RIPS y la factura electrónica del disco de red (`app/api/routers/analizar.py:805-824`), el contrato **vigente por fecha de atención** (287 hasta 30-nov-2025 = SOAT −15 %; 440 desde diciembre = SOAT −20 %, `BITACORA.md:105-111`) y la tarifa pactada. Y **abre el archivo**, no muestra la ruta para copiarla y pegarla en el explorador de Windows, como hace hoy (`static/index.html:21606`; no existe un solo `FileResponse` en `app/api/routers/soportes.py`).

**5. El dictamen se redacta con las defensas ya probadas. (Sistema)**
Un solo motor —no cuatro, como hoy (digest S11: importar-masiva secuencial, auto_responder con 2, generar-lote con 5, y /analizar unitario)— con las tres capas anti-gasto que nacieron de un incidente real de $14,50 en 251 llamadas, los precedentes ganadores (`few_shot_gold.py`), el verificador de citas contra el corpus con texto literal (`citation_verifier.py`) y los checks anti-fabricación del `post_validator`.

**6. El auditor ve una bandeja de excepciones, no una lista. (Humano)**
El sistema no le muestra 225 objeciones: le muestra las que necesitan su criterio —confianza baja, contrato ausente, alta cuantía, contradicción entre lo que dice la EPS y lo que dice la base. El resto viene marcado "listo". **Aquí ocurre la decisión 1** (ver 7.4).

**7. Aprobación del lote con firma. (Humano)**
Un botón: "Apruebo este lote para radicar". Queda registrado quién aprobó, cuándo y sobre qué versión. Hoy esta etapa —la verificación adversarial que corrigió 8 respuestas que no atacaban el punto real de la glosa en el lote del 17 de julio (`BITACORA.md:78-84`)— es la que más calidad aporta y **la única que no deja un solo dato estructurado** (digest S14, etapa E7). **Aquí ocurre la decisión 2.**

**8. El despacho al portal es del sistema. (Sistema)**
El bot recibe las respuestas por API, no por un Excel en el escritorio. Piloto de una factura → lote → segunda pasada de verificación, todo dentro del producto, con la disciplina que el equipo ya practica (`BITACORA.md:227-229`). El resultado del portal **vuelve al expediente**: estado, pantallazo del cartel de confirmación y motivo en español, no `TERMINADA_SIN_CARTEL`. Y con eso desaparece la categoría "Excel listo — subida sin confirmar", que es la que hoy tiene $153.675.820 en el limbo.

**9. La evidencia y el consecutivo se generan solos. (Sistema)**
Los pantallazos se consolidan en el PDF numerado con un **consecutivo real, persistido en base de datos** —no un `Math.random()` en un documento oficial (`static/index.html:18095`), ni un número que se pide por chat lote por lote (`BITACORA.md:196-197`). El blueprint ya lo describe: "Solicitar consecutivo → Leer Excel → Obtener número" (`docs/SINAC_OS.md:132-136`).

**10. La decisión de la EPS entra por selector. (Humano, 1 clic)**
LEVANTADA / ACEPTADA / RATIFICADA, no texto libre en un `prompt()`. Cuando la EPS levanta, el argumento ganador se promueve solo a plantilla gold; cuando ratifica, se desactiva — ese aprendizaje ya está implementado (`app/api/routers/glosas.py:3728-3746`) y sólo necesita un dato limpio de entrada.

**11. Ratificada → conciliación automática. (Sistema)**
Hoy esa transición es 100 % manual aunque el sistema tiene todos los datos (digest S4). En 2.0, registrar una ratificación **crea la conciliación** con su expediente, su matriz de evidencia por soporte (concepto rescatado de `tools/asistente_conciliacion_dispensario.py:488-506`) y los contraargumentos probables de la EPS.

**12. El acta se firma desde el sistema y cierra el ciclo. (Humano)**
El acta trae precargados NIT y razón social del pagador —que hoy el auditor re-escribe a mano aunque estén guardados (`static/index.html:3539-3540` vs `:3129-3133`)— y el firmante del HUS, que hoy sale siempre en blanco porque el código lee dos variables que no existen (`static/index.html:20615-20616`). Al firmar: la glosa se cierra, el valor conciliado alimenta el tablero y la nota crédito queda encolada. **Una acción, no tres. Aquí ocurre la decisión 3.**

**Un ramal que hoy no tiene flujo: la devolución.** El Excel de recepción trae la marca `DEVOLUCION S/N` y el sistema la guarda (`app/models/db.py:65`), hay un endpoint de resumen que nadie llama (`app/api/routers/glosas_stats.py:4753`) y ninguna pantalla la trabaja. Una devolución **no es una glosa**: no se contesta, obliga a corregir y **re-radicar la factura**, con su propio reloj. **Decisión: la devolución abre su propio expediente desde el paso 1 y termina en la re-radicación, ejecutada con `tools/radicar_facturacion.py` desde el servidor y con su reporte guardado en el expediente** (digest S15 y etapa E1). Se decide así porque la herramienta ya existe y es madura: lo único que falta es que el producto la dispare y registre el resultado, en vez de dejar la devolución sin dueño.

---

### 7.3 Antes vs. Después

| Etapa | Clics hoy | Clics en 2.0 | Qué automatiza el sistema |
|---|---|---|---|
| Saber qué es urgente al llegar | 2-3 (abre en Analizar; el aviso de vencimientos sólo vive en Mis Glosas, `static/index.html:13546`) | **0** — es la pantalla de inicio | Ordena por urgencia con el score que ya existe y **muestra primero las vencidas**, que hoy el endpoint esconde (`glosa_repository.py:440-450`) |
| Cerrar ratificadas y extemporáneas del día | Hoy se hacen una por una (12-14 clics c/u): el botón de un clic existe en pantalla pero llama a una ruta eliminada y **devuelve 404** (`static/index.html:7112` vs `app/main.py:1207`) | **1** (confirmar la propuesta) | Texto fijo determinístico, sin gastar IA (`recepcion_service.py:1073-1080`). Exige **reconstruir el endpoint**, no sólo mover el botón |
| Responder una glosa individual | **12-14 clics + 6 campos tecleados** (digest S9) | **2** (abrir la ficha, confirmar postura) + **0 campos** | Escribe lo que ya detecta en vez de sólo mostrarlo (`analizar.py:1032-1046`); precarga factura, radicado y fechas |
| Traer los soportes de la factura | Salir de la app, copiar la ruta, pegarla en el explorador (`static/index.html:21606`) | **0** | Abre el archivo desde el expediente; el número de factura deja de ser "opcional" (`static/index.html:2160-2164`) |
| Factura con 43 conceptos | 6 clics mínimos, **hasta 43 clics + 43 valores** si decide uno por uno, con 1,8 s de espera artificial por concepto ≈ 77 s (`static/index.html:9878, 9903, 9548-9556`) | **1** para aceptar el bloque + 1 por excepción real | Agrupa por criterio y sólo pide decisión donde el criterio cambia |
| Generar el lote para el portal | 0 clics en la app: **ocurre fuera** (ZIP → PowerShell → 2 scripts → Excel) | **1** ("Aprobar y radicar") | El generador de lotes entra al producto; hoy `glosa_motor.py` no está en el repositorio (`BITACORA.md:254-256`) |
| Radicar en el portal | 3 corridas de consola (piloto, lote, verificación) con rutas absolutas de ~120 caracteres | **0** | El bot recibe por API y reporta progreso en pantalla |
| Registrar que se radicó | 1 botón que alguien debe recordar apretar (digest S14) | **0** | Lo escribe el bot con el pantallazo del portal como evidencia — se acaba el estado "Excel listo, subida sin confirmar" |
| PDF de evidencias + consecutivo | 1 script + **pedir el GI-33 por chat** (`BITACORA.md:196-197`) | **0** | Consecutivo persistido y PDF armado al cerrar el lote |
| Registrar la decisión de la EPS | 1 `prompt()` de texto libre (`static/index.html:20390`) | **1** (selector) | Promueve o desactiva la plantilla gold sola (`glosas.py:3728-3746`) |
| Abrir la conciliación tras una ratificación | Manual, sin ayuda | **0** | La crea con expediente y matriz de evidencia |
| Cerrar el acta | **5 `prompt()` encadenados** + registrar el resultado otra vez para que sume al tablero (`static/index.html:20480-20498`; `conciliacion.py:290-324`) | **1** (firmar) | Precarga NIT, razón social y firmante; cierra la glosa y alimenta el tablero en la misma acción |

**Lectura de negocio:** el camino más barato que hoy existe —"Mis glosas" → seleccionar todas → "Generar respuestas en lote", que resuelve hasta 100 glosas en 5 clics (`static/index.html:13705`)— **está a dos niveles de profundidad**, mientras el camino más caro es el que abre por defecto. Dar vuelta esa relación es el cambio de mayor retorno de toda la 2.0 y no requiere inventar nada.

---

### 7.4 Los 3 momentos donde el humano DEBE decidir

El blueprint es explícito: *"El auditor toma decisiones. La IA ejecuta"* (`docs/SINAC_OS.md:26-31`). Traducido a este proceso, eso son exactamente **tres momentos**, y ninguno más.

**Decisión 1 — La postura frente a la objeción: defender, aceptar total o aceptar parcial.**
Es la decisión que mueve plata y compromete a la institución ante un tercero. La postura por defecto del HUS está escrita y es estable —NO ACEPTA, RE9901, se defiende el 100 % del valor (`BITACORA.md:245-248`)— pero apartarse de ella es un acto de auditoría, no de software.
*Por qué debe ser explícita y por glosa:* hoy no lo es, y eso ya es un riesgo verificado. La variable `window._concepto_modo_actual` se fija al hacer clic una vez en "Aceptar 100 %" (`static/index.html:9791`), se lee en cada análisis posterior (`:15039-15043`) y **nadie la limpia nunca** — ni "Nueva glosa", ni el botón de limpiar formulario, ni el final del lote. Después de tocar ese botón una vez, **todas las glosas de la sesión salen como cartas de aceptación en lugar de defensas**, sin ningún indicio en el formulario. Una decisión de plata tomada por una variable global huérfana.

**Decisión 2 — Aprobar el lote para radicar.**
Es la firma de calidad antes de que un documento salga a nombre del hospital. La evidencia de que este paso es irreemplazable está en la bitácora: en el lote del 17 de julio (58 facturas, 115 objeciones, $87.605.050 en juego) se corrigieron **8 casos donde la respuesta no atacaba el punto real de la glosa** —dispositivos, día-cama, lista de precios, desagregación de procedimientos (`BITACORA.md:78-84`)—; en el del 14 de julio se eliminaron citas de la Resolución 3047/2008, derogada (`BITACORA.md:71-77`). Ninguna verificación automática habría detectado los ocho.
*Lo que cambia:* hoy esa revisión no deja rastro estructurado; en 2.0 produce un estado "lote aprobado para radicar" con firma, fecha y versión — y **es lo único que habilita el despacho al portal**.

**Decisión 3 — El cierre de la conciliación: valor conciliado y firma del acta.**
El acta lleva cláusula de mérito ejecutivo (Art. 422 CGP) y es el documento que fija cuánto cobra y cuánto castiga el hospital: en el histórico, $71.901.424 aceptados sobre $277.231.324 glosados. Esa cifra la firma una persona con nombre, cargo y responsabilidad. La IA puede traer la matriz de evidencia, los contraargumentos probables de la EPS y el valor mínimo aceptable —`preparar-conciliacion` ya lo hace (`static/index.html:11971`)—, pero **no firma**.

**Por qué todo lo demás puede ser automático.** Porque ya es determinístico y ya está escrito: el texto fijo de ratificadas y extemporáneas, el cálculo del vencimiento por días hábiles, la evaluación de tarifa contra el contrato, el reparto al gestor, la detección del pagador real, la verificación de citas contra el corpus, los checks anti-fabricación y el estado de la radicación que devuelve el portal. **El detalle de cada una, con su archivo, su prioridad y qué le falta, está en la tabla de §9.1; no se repite aquí.**

Y porque el volumen ya demostró que funciona sin intervención humana pieza por pieza: **102 facturas y 225 objeciones subidas y verificadas al 100 % en ~22 minutos** (`BITACORA.md:67-70`), 8 facturas y 24 objeciones en 26,9 minutos, una ratificación FOMAG respondida con evidencia en 0,7 minutos.

---

### 7.5 El día del auditor en 2.0: el Centro de Operaciones

El módulo 1 del blueprint se llama "Inicio — Centro de Operaciones" (`docs/SINAC_OS.md:98`). Hoy ese lugar lo ocupa un formulario en blanco. **Decisión: la aplicación abre en el Centro de Operaciones y el formulario en blanco pasa a ser la excepción, alcanzable desde un botón, no la pantalla de entrada.**

Lo que el auditor ve al abrir, **en este orden y sin scroll**:

**Bloque 1 — "Lo que se vence" (rojo, arriba de todo).**
"**N glosas vencidas** · **M vencen hoy** · Valor en riesgo: $X". Es el banner que hoy ya existe y está bien escrito (`static/index.html:13546-13573`), movido al sitio donde el auditor entra, y **corregido para incluir las vencidas** — hoy la consulta que alimenta el contador del encabezado filtra `dias_restantes > 0` y las esconde (`glosa_repository.py:440-450`). Un botón: "Ver y resolver ahora".
*Regla nueva:* una glosa que entra en negro escala sola al coordinador. Las tres facturas de junio, con $20.054.751 en riesgo, se descubrieron 45 días tarde revisando a mano (`BITACORA.md:86-91`).

**Bloque 2 — "Preparar el día" (la acción principal, y hoy no existe).**
Este bloque **se apoya en una automatización que hay que reconstruir, no en una que funcione**: el botón actual devuelve 404 porque su router fue borrado en la ronda 29 (7.1). Por eso el arreglo es parte del paquete **A0** de la versión 2.0 (§10.3) y es condición previa de todo este Centro de Operaciones. Lo que se rescata es el trabajo de pantalla ya escrito: el resumen en español del resultado (`static/index.html:7120-7126`) y la idempotencia. Lo que cambia: en vez de un `confirm()` genérico, **muestra la propuesta antes de ejecutar** — "Voy a cerrar 34 glosas: 21 ratificadas, 13 extemporáneas. Ninguna requiere IA. ¿Confirmás?" — y deja registrado qué cerró y con qué texto.

**Bloque 3 — "Lo que necesita tu criterio".**
La bandeja priorizada, que ya existe y es **el mejor trabajo del frontend actual**: semáforo por días hábiles, motivo de urgencia en español, tasa histórica de éxito del par (EPS, código) en cada fila y vistas guardadas que son preguntas reales de un auditor de cartera — "Aprobadas (radicar)", "TA sin contrato", "Alta cuantía ≥ $5.000.000", "Requieren soportes", "Dictamen obsoleto" (`static/index.html:2743-2750, 13091-13410`). El orden lo da el score de urgencia que ya está implementado (`app/api/routers/glosas.py:2394-2427`): **VENCIDA = 100**, vence ≤3 días con ≥$1.000.000 = 95, **aprobada pero sin radicar = 88**, vence ≤3 días = 85, requiere soportes = 75, alta cuantía ≥$5.000.000 = 70.

**Bloque 4 — "Lo que está esperando del otro lado".**
Lotes en curso en el portal con su progreso real, respuestas radicadas sin decisión de la EPS, conciliaciones programadas, notas crédito trabadas por CUV. Aquí es donde deja de ser posible que $153.675.820 queden con el Excel listo y la subida sin confirmar sin que nadie lo vea. Hoy nada de esto tiene pantalla: la API de lotes tiene 6 endpoints, 3 tablas, un agente de escritorio y 403 líneas de tests, y **cero llamadas desde la interfaz** (digest S7: `grep "fetch('/lotes"` en `static/index.html` → 0 resultados).

**Bloque 5 — Un solo número de resultado.**
"Este mes: defendido $X · recuperado $Y · pendiente $Z", con **fecha de corte y fórmula visibles**, y con una regla de vocabulario: *defendido* es lo que se radicó en plazo, no lo que se generó. Hoy hay cuatro pantallas de reportes sobre el mismo dato con cuatro fórmulas distintas de "recuperado", y el propio código documenta que el cliente ya pidió consolidarlas y que la respuesta fue agregar una quinta superficie en lugar de quitar tres pantallas (`static/index.html:12386-12394`). **Decisión: una sola pantalla de reportes con selector de corte; se eliminan Mando, Cobranza Live y Resumen del mes.**

**Tres reglas de diseño del Centro de Operaciones:**

1. **Un solo indicador de confianza.** Hoy conviven seis escalas sobre el mismo dictamen (score 0-100, post_validator, evaluar_dictamen, confidence_scorer 0-1, auditor_dictamen, alta/media/baja) y **el número más grande y prominente de la interfaz es el único que no mide calidad**: `_calcular_score` es una heurística estática por tipo de glosa (extemporánea=99, ratificación=92, tarifa=75) que el propio código admite que subía con citas fabricadas (`glosa_service.py:3551-3554`). Se queda `confidence_scorer`, que es el único con desglose accionable.
2. **Cero `prompt()`.** Los 44 cuadros nativos del navegador se reemplazan por formularios con selectores. Es trabajo mecánico, de bajo riesgo, y elimina la clase de error donde escribir "ACUERDO PARCIAL" con espacio en vez de guion bajo borra cinco datos ya tecleados.
3. **Debe funcionar en un teléfono.** La mesa de conciliación no ocurre en el escritorio. Hoy el panel de trabajo es un flex horizontal con el formulario fijo en 280 px, sin ninguna regla que apile: en un teléfono de 390 px al dictamen le quedan ~110 px de ancho (`static/index.html:840, 1432`).

---

### 7.6 El flujo de LOTE: donde está el volumen real

Un lote de 102 facturas y 225 objeciones no es "muchas glosas individuales": es **otra unidad de trabajo**, y hoy el producto no la modela. El auditor la opera desde PowerShell y la anota a mano en la bitácora. Así debe verse en SINAC OS:

**1. El lote entra y se anuncia solo.**
El agente de captura descarga el paquete del pagador y crea el lote con su origen, su fecha de notificación y su vencimiento calculado. El auditor recibe un aviso: "Lote DMBUG · 102 facturas · 225 objeciones · vence el 12". No hay ZIP en `Downloads`.

**2. Ingesta única, con perfil declarativo.**
Un solo lector de tablas —hoy hay **tres detectores de encabezado incompatibles** y uno de ellos importa la fila de encabezado como si fuera una glosa (digest S11)— que detecta hoja, fila de encabezado y columnas por alias según el **perfil del pagador**. Agregar un pagador nuevo deja de exigir tocar cuatro archivos de código. Esto es lo que hace que pasar de los **cuatro bots de hoy** a los **nueve** que ya se nombraron (con SAVIA, EMSSANAR, VCO, MUTUAL SER y FOMAG) sea agregar fichas y no escribir cinco robots más.

**3. Pantalla de composición ANTES de gastar un peso.**
"De 225 objeciones: 61 ratificadas y extemporáneas → texto fijo, $0. 48 de tarifa → resolución determinista, $0. 92 gemelas de dictámenes ya emitidos → reuso, $0. **24 requieren IA.**" Esta pantalla no existe hoy y es la que convierte el gasto en una decisión informada: las tres capas anti-gasto nacieron de un incidente real de $14,50 en 251 llamadas y **hoy sólo protegen uno de los cuatro caminos de generación masiva** (digest S11).

**4. Ejecución con progreso real y reanudable.**
Barra de progreso verdadera, no la animación que el propio código declara simulada (`static/index.html:13741`); costo real acumulado, no el "$0.00" fijo que se muestra hoy porque la columna nunca se escribe (`app/models/db.py:627`); "Cancelar" que cancela de verdad, no el botón que el código admite que sólo cambia la visibilidad mientras la IA se sigue gastando (`app/api/routers/glosas.py:5109-5116`). Y reanudación desde donde se cortó, para los dos portales: hoy COOSALUD tiene `--saltar-csv` y SIMED no tiene nada equivalente (digest S7).

**5. Tablero de excepciones — el único punto donde el auditor trabaja.**
De 225 objeciones, el sistema le presenta 15: las de confianza baja, sin contrato, de alta cuantía o con contradicción entre la EPS y la base. Las demás quedan marcadas "listas". Aquí ocurre la **decisión 1**, y ocurre 15 veces, no 225.

**6. Aprobación del lote (decisión 2).**
Un botón con firma. Sin esa firma, el lote no sale.

**7. Despacho y verificación automáticos.**
Piloto de una factura → lote completo → segunda pasada que debe dar cero pendientes. Es la disciplina que el equipo ya ejecuta a mano (`BITACORA.md:227-229`), convertida en un flujo del producto. Cada objeción vuelve con su estado en español y su pantallazo del portal pegado al expediente — no `PENDIENTE_PDX` en un CSV del escritorio. El lote no puede quedar en "Excel listo": o está radicado con evidencia, o está en rojo en el bloque 4 del Centro de Operaciones.

**8. Cierre del lote.**
Se genera el PDF de evidencias con **consecutivo real**, se actualiza el expediente de cada factura, y el tablero de gerencia se mueve solo. La bitácora deja de ser un registro de estado —donde ya se demostró que estaba equivocada en 6 de 12 facturas— y vuelve a ser lo que sí hace bien: memoria de decisiones.

**El objetivo medible de la Fase 7:** hoy un lote de 102 facturas cuesta **~22 minutos de bot más una jornada de preparación manual repartida entre carpetas, PowerShell, un script que no está en el repositorio y un chat para pedir un consecutivo**. En 2.0 debe costar **una revisión de excepciones y dos clics** — y dejar, por primera vez, un rastro auditable de punta a punta que responda sin abrir tres carpetas la única pregunta que importa: *¿esta objeción se radicó, cuándo, con qué evidencia, y cómo terminó?*

---

## 8. La IA como copiloto, no como botón (Fase 8)

El blueprint es explícito: *"No habrá un botón llamado IA. Toda la plataforma estará impulsada por IA"* (§3, `docs/SINAC_OS.md:44`). Hoy pasa lo contrario: hay mucha IA construida, poca conectada, y varias piezas que se anuncian en pantalla sin existir por detrás. Esta fase no agrega inteligencia: **conecta la que ya está pagada y apaga la que miente**.

### 8.1 Qué tiene hoy el sistema de IA y qué de eso está realmente conectado

| Capacidad | Estado real | Evidencia | Decisión 2.0 |
|---|---|---|---|
| Generación del dictamen con LLM | **Viva. Es el producto.** Un método de ~2.800 líneas con **73 `except` silenciosos dentro del método** (84 en el archivo completo) y 32 "redes finales" cosidas por orden cronológico de bug | `glosa_service.py:4299-7097` | Mantener el conocimiento, partir en pipeline de 9 etapas (Fase 1) |
| Verificación anti-alucinación de citas | **Viva y es lo mejor que tiene el sistema.** Distingue norma inexistente / artículo fuera de norma / cita literal falsa contra el texto real | `citation_verifier.py`, corre en `glosa_service.py:6484` y `quality_gate/post_validator.py:98` | Mantener intacto. Absorbe los otros 2 validadores de citas |
| Enriquecimiento determinista del prompt (jurídico, clínico, tarifario) | **Vivo, gratis, en el camino caliente.** No llama a ningún LLM pese al nombre | `multi_agente.py:34-380`, llamado desde `glosa_service.py:5165` | Mantener. **Renombrar a `enriquecedor_prompt_dominio`**: no son agentes |
| Caminos sin LLM (texto fijo, plantilla, dictamen directo) | **Vivos. El mayor retorno del sistema:** ratificadas y extemporáneas se cierran a $0 y ~50 ms | `recepcion_service.py:1073-1080`, `dictamen_directo.py` | Ascender a ramas de primera clase del pipeline |
| Quality Gate (pre/post validación + regeneración) | **Construido y apagado.** 1.748 líneas de código + 1.151 de tests; el flag no figura en `.env.example` ni en `docker-compose.yml` | `quality_gate/`, `quality_gate_adapter.py` | Encender de fábrica y **eliminar el retry legacy** que lo duplica |
| Asistente conversacional con herramientas reales (9 tools que consultan soportes, contratos, tarifas, normas, precedentes) | **Vivo y cableado al usuario** | `asistente_maestro.py:72-187`; FAB en `static/index.html:15311` | **Es el esqueleto del copiloto 2.0** |
| "Chat sobre esta glosa" | **Cero llamadas a IA.** Ocho respuestas fijas por palabra clave; el ejemplo que la propia UI sugiere ("citá la cláusula octava") no coincide con ninguna y siempre cae en "No pude responder eso" — y encima consume cupo de IA | `chat_glosa.py:56-138`, `:147`; UI en `index.html:6595` | **Eliminar.** Se absorbe dando contexto de glosa al Asistente Maestro |
| "Asistente Predictivo · Ola 4" / inteligencia ambiental | **Nunca hizo una sola petición.** El JS lee el token en `localStorage.token` cuando la app lo guarda en `hus_token`, y se engancha a un textarea de una pantalla inalcanzable | `sinac-asistente.js:1-227` vs `index.html:6387`; router en `main.py:1226` sin llamadores | **Eliminar** (router + servicio + 227 líneas de JS + 18 tests) |
| Multi-agente LLM real | **Apagado desde siempre.** 1 de 3 agentes implementado, 3× costo por diseño | `multi_agent.py:60-61` (flag por defecto `'0'`), call site `glosa_service.py:5054` | **Eliminar** |
| Tool-use dentro de la generación del dictamen | **Apagado.** Su loop está triplicado | `ia_tools.py:28` (`TOOL_USE_HABILITADO='0'`); loops en `glosa_service.py:8530-8700`, `asistente_maestro.py:409-520`, `multi_agent.py:148-216` | Conservar las funciones `_exec_*` (consultan datos reales); borrar el andamiaje y dejar **un solo cliente LLM compartido** |
| Recuperación de precedentes propios (BM25) | **Viva pero neutralizada:** un cortocircuito la deja fuera de juego (ver 8.2) | `rag_service.py` vía `few_shot_gold.py:218`; corte en `few_shot_gold.py:116-117` | Mantener y **ponerla primera** en el orden de ejemplos |
| RAG normativo TF-IDF | **Muerto de cara al usuario.** Sus dos endpoints no se llaman desde ninguna de las **23.125 líneas de `static/index.html`** | `rag_normativa.py`; `herramientas_avanzadas.py:343,357` | **Eliminar.** Su validación de citas da por buena cualquier cita cuyo número aparezca en el corpus concatenado (`rag_normativa.py:291-302`) |
| "Búsqueda semántica" | **No es semántica.** Es `LIKE` en base de datos más un LLM reordenando 80 filas: paga un modelo para ordenar | `busqueda_semantica.py:25-161` | Reemplazar por BM25 local (ya existe, costo $0) |
| Grafo de normas | **Dormido detrás de un flag apagado**; solo asoma si alguien pregunta una norma en el chat | `normativa_grafo.py`, único consumidor `ia_tools.py:331` | No sobrevive como módulo: sus ~30 aristas pasan a ser un campo `relaciones` del corpus normativo único |
| Aprendizaje del resultado de la EPS | **Cableado pero sin circuito de vuelta.** Verificado en la base: 52 plantillas Gold, las 52 sembradas, 0 aprendidas, todas con `usos=0` | `glosas.db`: `creado_por='auto_seed_lifespan'` en 52/52 | **Reparar (8.2). Es el punto más importante de todo el plan** |
| Aprendizaje del estilo del auditor | **No llega al flujo principal.** El panel "tu estilo aprendido" existe, pero `/analizar` no lo pasa | `analizar.py:880-887` (sin `hint_gestor`); panel en `index.html:11898` | Fusionar `memoria_gestor` + `aprendizaje_diff` en `estilo_gestor` y cablearlo a `/analizar` |
| Predicción de ratificación | **La que el usuario ve no consulta la base de datos ni una vez** | `riesgo_ratificacion.py:17` ("según histórico nacional"), `:38-44` | Reemplazar (8.3) |
| Lectura de foto de glosa (OCR/visión) | **Viva y barata.** Única entrada multimodal | `vida.py:189-233` + `gemini_service.py` | Mantener |
| Auditoría pre-IA de la glosa contra la base (sin LLM) | **Viva.** Detecta "sin contrato" cuando sí hay contrato, "sin tarifa" cuando está en el catálogo, objeción mayor al excedente | `auditor_glosa.py` | Mantener. Corregir la doble ejecución (`glosa_service.py:5387` y `:6798`) |
| Medición del costo de IA por glosa | **No existe.** De 12 puntos que llaman al modelo, solo 1 registra; en la tabla hay 24 llamadas y **ninguna** con `glosa_id` | `glosa_service.py:8456` es el único con métricas | Un cliente único con registro obligatorio. Sin esto no se puede decidir qué apagar |

**Los pares casi idénticos: quién sobrevive y por qué**

| Par | Sobrevive | Se elimina | Razón de la decisión |
|---|---|---|---|
| `multi_agent.py` (inglés) vs `multi_agente.py` (español) | `multi_agente.py`, renombrado **`enriquecedor_prompt_dominio`** | `multi_agent.py` (314 l) | Nombres a una letra de distancia para cosas opuestas. El que se queda es determinista, gratis y corre en cada análisis; el que se va está apagado desde siempre, con 2 de 3 agentes sin escribir y 3× costo declarado (`multi_agent.py:32-34`) |
| `rag_service` vs `rag_normativa` | `rag_service` (BM25 sobre precedentes propios del HUS) | `rag_normativa` (312 l) | Uno recupera lo que el HUS ya ganó; el otro busca normas que el corpus ya tiene con texto literal, y su validador es más débil que `citation_verifier`, que sí corre en producción |
| `predictor_glosas` vs `ml_ratificacion` vs `riesgo_ratificacion` | **La estructura de `ml_ratificacion`** (aprende de `decision_eps` del propio hospital) **con la presentación de `riesgo_ratificacion`** (0-100 y factores legibles, ya tiene interfaz en `index.html:16249`) | `predictor_glosas` (234 l) y la heurística de constantes de `riesgo_ratificacion` | `predictor_glosas` predice si una factura *será* glosada: eso es prevención de facturación, otro producto. Y de los otros dos, el único que mira la base tiene 0 llamadores |
| `asistente_maestro` vs `asistente_predictivo` | `asistente_maestro` | `asistente_predictivo` + `inteligencia_ambiental` + `sinac-asistente.js` | El primero es la única IA conversacional real del sistema y está enchufada al usuario; el segundo nunca ejecutó una petición |
| `aprendizaje_diff` vs `aprendizaje_feedback` | **Los dos, porque no son el mismo par** | — | Corrección al enunciado: `aprendizaje_feedback` aprende del **resultado de la EPS**; `aprendizaje_diff` aprende del **estilo del auditor**. El duplicado verdadero es `aprendizaje_diff` vs `memoria_gestor` (misma finalidad, dos señales, dos suites de test, un único consumidor: `memoria_gestor.py:244`). Se fusionan en **`estilo_gestor`** y `aprendizaje_feedback` se renombra **`aprendizaje_resultado_eps`** para que nadie los vuelva a confundir |

---

### 8.2 ¿El sistema aprende de verdad?

**No. El circuito existe, está cableado, y está cortado en cuatro puntos.** Esta es la respuesta más importante de todo el informe, así que va rastreada paso a paso.

**Dónde se guarda el resultado real de la EPS**

Solo en dos columnas de la glosa: `decision_eps` y `valor_recuperado`. Y solo si **una persona lo escribe a mano**, en `PATCH /glosas/{id}/decision-eps` (`glosas.py:3705-3726`) o en el lote (`glosas.py:3947-3952`). No hay ingesta automática desde el portal: los bots cierran la factura, sacan el pantallazo y el resultado se queda en un CSV del escritorio (verificado: ninguno de los cuatro bots hace una llamada HTTP que no sea al portal). Peor: la captura de ese dato — el más importante del negocio — se hace escribiendo texto libre en un `prompt()` del navegador (`index.html:20390`). Si el auditor escribe "levantada" en minúscula, se pierde.

**Qué dispara ese registro**

`aprendizaje_feedback.aprender_de_decision_eps` (`glosas.py:3734`), que crea una Plantilla Gold con el argumento ganador y `usos=0` (`aprendizaje_feedback.py:155`). Hasta acá, correcto.

**Los cuatro cortes**

1. **Cortocircuito en la selección de ejemplos.** `few_shot_gold.obtener_ejemplos_gold` hace `return ejemplos` apenas junta 2 ejemplos del banco de plantillas sembradas (`few_shot_gold.py:116-117`). Como el banco cubre exactamente las cinco familias más comunes — CL, CO, FA, SO y TA, con 10 plantillas cada una — **para la enorme mayoría de las glosas los pasos 2 (Gold aprendida), 3 (histórico levantado) y 4 (precedentes BM25) nunca se ejecutan.**
2. **Filtro imposible de superar.** Ese mismo paso 2 exige `usos >= 3` (`few_shot_gold.py:131`), pero toda Gold aprendida nace con `usos=0` y ese camino no incrementa el contador. Nunca llega a 3.
3. **Desajuste de mayúsculas.** El otro camino (`plantillas_gold.obtener_few_shot`, `analizar.py:867`) sí puede leer Gold aprendidas y sí incrementa `usos`, pero busca con la EPS en mayúsculas (`plantillas_gold.py:252`) mientras el aprendizaje guarda `glosa.eps.strip()` sin normalizar.
4. **El desaprendizaje no ocurre.** Cuando la EPS ratifica, `_desactivar_gold` solo apaga la plantilla si los primeros 200 caracteres coinciden **exactamente** con el dictamen ratificado (`aprendizaje_feedback.py:192`). Con texto generado por un modelo de lenguaje esa igualdad prácticamente nunca se da: **los argumentos que pierden siguen activos.**

**Y la conciliación es un callejón sin salida.** `PATCH /conciliaciones/{id}/resultado` (`conciliacion.py:159-192`) escribe el resultado y el valor conciliado, y no llama a ningún aprendizaje, no toca `decision_eps` y ni siquiera importa el módulo. Ganar o perder una audiencia — donde se negocian los montos más grandes — no cambia absolutamente nada en la generación futura.

**La prueba definitiva está en los datos, no en la lectura del código:** la tabla `plantillas_gold` tiene 52 filas, las 52 con `creado_por='auto_seed_lifespan'`, todas con `usos=0` y `ultima_uso_en` en nulo (verificado ejecutando la consulta sobre `glosas.db`). En toda la operación registrada hasta hoy **el lazo nunca giró ni una vez**. Y hay una consecuencia adicional que sí hace daño: al modelo se le presentan esas 52 semillas rotuladas como *"EJEMPLO #N (respuesta que logró levantar la glosa)"* (`glosa_service.py:4770`). Ninguna ganó nunca nada. El sistema le está mintiendo a su propio modelo.

**Cómo se cierra el circuito (diseño)**

```
Bot cierra en el portal ──┐
Correo/acta de la EPS  ───┼──> INGESTA DEL RESULTADO (automática, no un prompt)
Conciliación cerrada   ───┘            │
                                       v
                        Resultado por OBJECIÓN (no por factura):
                        LEVANTADA / ACEPTADA / RATIFICADA / CONCILIADA
                        + valor recuperado + fecha + evidencia
                                       │
                    ┌──────────────────┼──────────────────┐
                    v                  v                  v
            Promueve a Gold     Desactiva la Gold    Recalibra el par
            (ganó, con valor)   (perdió, por         (EPS, código):
                                 similitud, no        tasa real de éxito
                                 por igualdad)
                                       │
                                       v
                    UN SOLO SELECTOR DE EJEMPLOS, con este orden:
                    1) precedente propio ganado (BM25 sobre casos reales)
                    2) Gold aprendida del par (EPS, código)
                    3) banco HUS como último recurso, rotulado como lo que es
```

Seis cambios concretos, todos de bajo riesgo:

1. Quitar el `return` anticipado (`few_shot_gold.py:116-117`) e **invertir el orden**: precedente propio primero, banco sembrado al final.
2. Eliminar el filtro `usos >= 3` y unificar los dos caminos de few-shot en uno solo con **una sola instrucción** al modelo (hoy conviven tres instrucciones contradictorias: "COPIA VERBATIM", "no copies literal" y "úsalas como patrón").
3. Normalizar la EPS al escribir y al leer la Gold (una sola función de identidad de pagador, ver 9.3).
4. Cambiar la igualdad exacta del desaprendizaje por **similitud** (el sistema ya tiene el mecanismo: `detector_copia.py` calcula Jaccard sobre 5-gramas en 76 líneas).
5. Propagar el resultado de la conciliación a `decision_eps` y `valor_recuperado` en la misma acción que cierra el acta.
6. Rotular honestamente: una plantilla sembrada es "modelo aprobado por el equipo jurídico", no "respuesta que ganó".

**Impacto en el trabajo real:** hoy cada glosa se responde con el mismo conocimiento del día uno. Con el circuito cerrado, cada factura que la EPS levanta mejora la siguiente respuesta contra esa misma EPS y ese mismo código — y cada ratificación retira de circulación el argumento que falló. Es la diferencia entre un motor y un formulario.

---

### 8.3 Predicción de éxito

**Qué existe hoy.** Tres predictores, ninguno validado contra un resultado real.

| Módulo | Qué calcula | Con qué datos | ¿Lo ve el usuario? | ¿Validado? |
|---|---|---|---|---|
| `riesgo_ratificacion.py` | Riesgo 0-100 de que la EPS ratifique | **Constantes escritas a mano.** Una tabla por familia de glosa rotulada "según histórico nacional" (`:17-36`) y un conjunto de 5 "EPS históricamente difíciles" — NUEVA EPS, SALUD TOTAL, MEDIMÁS, SURA, SANITAS (`:38-44`) — que **no son los pagadores donde el HUS concentra la operación** (Dispensario Médico, COOSALUD, PPL, FOMAG), y dos de las cinco (MEDIMÁS y SURA) ni siquiera figuran entre las **12 entidades** del catálogo de radicación. Cero consultas SQL | **Sí, es el único visible** (`glosa_service.py:6463`, panel en `index.html:16249`) | No |
| `ml_ratificacion.py` | Probabilidad por regresión logística, 14 coeficientes | **Sí consulta la base**: calibra por EPS con `decision_eps` | No: 0 llamadores en producción | No. Su propio comentario (`:11-12`) dice "reentrenar cuando haya >500 decisiones EPS" — nunca se conectó |
| `predictor_glosas.py` | Probabilidad de que una factura *sea* glosada antes de radicar | Histórico de facturación | No: su endpoint no se llama desde ninguna pantalla | No |

**Decisión.** Sobrevive **uno solo**: la estructura de `ml_ratificacion` (aprende del hospital) con la presentación de `riesgo_ratificacion` (0-100 con factores en español, que ya tiene interfaz). `predictor_glosas` se elimina: predecir glosas antes de facturar es prevención de facturación, un producto distinto que no debe consumir presupuesto de esta versión.

**Con qué datos se construye.** Todos ya están en la base o entran con la Fase 9:

- Par (pagador, código de glosa) y su tasa real de levantamiento — el sistema ya calcula algo parecido en `calibracion_dificultad.py` y lo usa para el tono.
- Valor objetado y relación objetado/facturado.
- Si hay contrato vigente **por fecha de atención** y si hay tarifa pactada cargada.
- Si hay soportes en el expediente y de qué tipo (la matriz de evidencia).
- Antigüedad de la glosa y si es primera vuelta o ratificación.
- Familia normativa y si el argumento se apoya en cláusula literal o solo en norma general.
- Quién respondió y con qué versión del motor (para no confundir mejora del modelo con mejora del auditor).

**Cómo se mide que la predicción sirve — esto es lo que hoy no existe en ninguno de los tres.** Un número de probabilidad sin medición de acierto es decoración. La calibración se mide así, y se publica en pantalla:

1. **Tabla de calibración por deciles.** Se agrupan todas las glosas cuyo pronóstico fue "70-80 % de éxito" y se mira qué porcentaje efectivamente se levantó. Si el sistema dice 75 y la realidad es 74, está calibrado. Si dice 75 y la realidad es 40, el número es un adorno peligroso — el auditor radica confiado y pierde.
2. **Una sola cifra de resumen** (error cuadrático medio de la probabilidad, el llamado *Brier score*), reportada mensualmente contra la línea base "predecir siempre la tasa promedio". Si el modelo no le gana a esa línea base, se apaga.
3. **Ventana móvil de 90 días y recalibración automática** por pagador: los pagadores cambian de criterio de auditoría, y un modelo entrenado con 2025 no sirve para el contrato 440.
4. **Regla dura de producto: la predicción no se muestra hasta que haya al menos 30 decisiones reales registradas para ese par (pagador, familia).** Antes de eso se muestra "sin datos suficientes", que es información honesta. Hoy el sistema muestra un número inventado desde la primera glosa.

---

### 8.4 El copiloto contextual (blueprint §15)

El blueprint pide un copiloto en cada pantalla. La regla de diseño que proponemos, para que no se convierta en un chat decorativo: **el copiloto no conversa, avisa y ofrece una acción de un clic.** Si lo que detecta no se puede resolver con un botón, no se muestra.

| Pantalla (§8 del blueprint) | Qué detecta el copiloto | Qué propone, en concreto |
|---|---|---|
| **1. Inicio — Centro de Operaciones** | Glosas en semáforo negro que hoy no disparan nada: el estado existe (`recepcion_service.py:52-56`) pero ninguna acción se activa. Así quedaron sin radicar 3 facturas del Dispensario con vencimiento 6 y 8 de julio, descubiertas el 22 por revisión manual (`BITACORA.md:86-91`) | *"3 facturas vencen hoy por $X. Las respuestas ya están generadas pero no radicadas. Radicar ahora"* — y si el plazo ya pasó, *"generar el oficio de radicación por correo con constancia"*. **Acá revive "Preparar el día":** hoy el botón (`static/index.html:7112`) llama a `POST /autopilot/preparar-dia`, ruta borrada en la ronda 29 (`app/main.py:1207`), y **devuelve 404**. No es una automatización que solo haya que mover de sitio: hay que **resucitarla**, y entra en el primer paquete de arreglos por ser la acción de un clic con mejor retorno del producto |
| **2. Bandeja Inteligente** | Composición del día antes de tocar nada: cuántas son ratificadas/extemporáneas de texto fijo, cuántas tienen gemela ya respondida por hash, cuántas exigen modelo caro | *"De las 120 glosas de hoy, 43 se cierran sin IA (ratificadas y extemporáneas), 12 tienen una respuesta gemela reutilizable y 9 superan $10.000.000 y van a modelo alto. Costo estimado del lote: $X. Procesar"*. Las tres capas anti-gasto existen pero hoy solo protegen un flujo de cuatro (`auto_responder_service.py:242-366`) |
| **3. Expedientes** | Que el banner verde miente: dice "12 soportes detectados" pero la IA solo leyó 3 archivos recortados a 5.000 caracteres (`analizar.py:48-49`), y cualquier PDF de más de 4 páginas llega truncado a ~7.050 caracteres (`pdf_service.py:77-91`) | *"El expediente tiene la historia clínica de 180 páginas, pero el dictamen se construyó con 7 KB de ella. Leer completo (2 min, $X)"*. Y la matriz de evidencia por familia: *"La glosa SO0101 exige descripción quirúrgica (DQX); no está en el expediente. Sin ella el argumento queda genérico y la EPS lo ratifica"* |
| **4. Conciliaciones** | Contraargumentos probables del pagador y valor mínimo aceptable — ya calculados por `conciliador_ia.preparar_audiencia` y usados en `index.html:11971`. Y el hueco: cerrar el acta no transiciona la glosa ni suma a la plata recuperada (`conciliacion.py:290-324`) | *"En las últimas 4 mesas con este pagador, el 60 % de las glosas TA se conciliaron al 70 % del valor. Su piso sugerido para esta mesa es $X"*. Al cerrar: *"El acta AC000862 cierra 47 glosas por $18.400.000. Aplicar y actualizar cartera"* — una sola acción, no dos digitaciones |
| **5. Contratos** | Que el contrato aplicable depende de la **fecha de atención**, no de la fecha de la glosa: 372 de 444 glosas venían marcadas "SIN CONTRATO" cuando sí lo tenían (`BITACORA.md:105-111`). Y que editar el contrato por pantalla no cambia el dictamen, porque el catálogo en código tiene prioridad sobre la base (`glosa_ia_prompts.py:372-432`) | *"Esta atención es del 12-nov-2025: aplica el contrato 287 (SOAT −15 %), no el 440 (SOAT −20 %). Recalcular la diferencia tarifaria"*. Y en el editor: *"La cláusula octava, página 14, respalda esta respuesta. Citarla textualmente"* — el sistema ya extrae cláusulas literales con página desde el PDF (`extractor_clausulas_contrato.py`) |
| **6. Biblioteca (normatividad)** | Citas peligrosas antes de radicar: normas derogadas, artículos que no existen en la norma citada, sentencias fantasma. El verificador ya distingue los tres casos y trae cicatrices reales (`citation_verifier.py:24-50`, caso "C-4747/2007") | *"El dictamen cita la Res. 3047/2008, derogada por la Res. 2284/2023. Reemplazar la cita"*. Y en la biblioteca: *"Esta norma existe en el catálogo de consulta pero no en el corpus con texto literal"* — hoy los dos catálogos de 131 normas comparten solo 20 nombres, así que el auditor puede citar algo que el propio validador marcará como inexistente |
| **7. Automatización (bots)** | Estados del bot traducidos al idioma del negocio y con causa raíz. Hoy el CSV devuelve `PENDIENTE_PDX`, `TERMINADA_SIN_CARTEL`, `NO_EN_BOLSA` (`docs/CONTEXTO_COOSALUD.md:100-104`) | *"7 facturas quedaron sin cerrar porque falta el soporte PDX en el share. Están acá: [lista]. Buscar en carpeta ENV alternativa / marcar para el equipo de soportes"*. Y antes de lanzar: *"Este lote tiene 3 facturas con más de 200 glosas; el portal se rompe por encima de ese número, se partirán en tandas"* — conocimiento que hoy vive en un comentario del bot (`responder_glosas_coosalud.py:1252-1254`) |
| **8. Herramientas** | Códigos homologados y tarifarios incompletos | *"El CUPS 995201 fue homologado por la Res. 2641/2025 a 995200; el pagador está glosando por el código viejo. Citar la resolución"* (`homologador_cups.py`). Y honestidad donde falta dato: *"El Manual SOAT cargado tiene 4 códigos de ejemplo; esta liquidación no se puede verificar contra tarifa oficial"* (`tarifa_liquidador.py`) |
| **9. Administración** | Riesgos de cumplimiento y de acceso, en lenguaje de auditoría, no de sistemas | *"0 de 24 usuarios tienen segundo factor activo, incluidos los 2 administradores"* (verificado sobre la tabla `usuarios`); *"el rol Solo Lectura puede borrar contratos y plantillas: la restricción solo se verifica en 1 de 67 endpoints de escritura"*; *"el sistema reporta que cifra datos del paciente y no cifra ninguno"* (`sistema.py:147` vs `cifrado.py`, sin un solo importador). Cada aviso con su acción: activar 2FA, corregir el rol, o retirar la afirmación falsa. **Decisión: el segundo factor se conserva y se vuelve obligatorio para los perfiles administradores** — quitarlo de un sistema que guarda datos de paciente no es defendible ante una auditoría, y el módulo ya está construido |

Tres reglas transversales para que el copiloto no se vuelva ruido: **(a)** máximo un aviso primario por pantalla, ordenado por plata en riesgo; **(b)** todo aviso trae la evidencia que lo sustenta (el dato, el archivo, la cláusula) — el sistema ya hace esto bien en el mensaje de "sin soportes", que enumera las tres causas probables (`index.html:18665-18672`); **(c)** ningún aviso se inyecta **dentro** del documento jurídico. Hoy la corrección automática de EPS se comunica con un banner metido en el HTML del dictamen (`glosa_ia_prompts.py:1603`): es un aviso de interfaz, no un párrafo del oficio que se radica.

---

### 8.5 Explicabilidad: una sola escala, y que se pueda defender

Hoy el mismo dictamen recibe **seis puntuaciones distintas, ninguna reconciliada con las otras**:

| # | Escala | Origen | Problema |
|---|---|---|---|
| 1 | "% de éxito" 0-100 (el número grande de la pantalla) | `glosa_service.py:7098` | **Es el más visible y el único que no mide calidad**: es una tabla estática por tipo de glosa (extemporánea 99, ratificación 92, urgencia 90, tarifa 75, resto 85) más bonos por citar normas y por tener PDF. El propio código admite que las citas *fabricadas* subían el puntaje (`glosa_service.py:3551-3554`) |
| 2 | Puntaje 0-100 del Quality Gate | `quality_gate/post_validator.py` | Apagado por flag en el flujo principal |
| 3 | Puntaje 0-100 del validador pre-radicación | `validador_dictamen.evaluar_dictamen` | Solapa con el anterior con otros umbrales |
| 4 | Confianza 0,0-1,0 con desglose | `confidence_scorer.py` | **Es el único honesto y el único accionable** |
| 5 | Puntaje 0-100 del auditor forense | `auditor_dictamen.py` | Cuarta re-verificación de longitud y citas |
| 6 | Alta / media / baja (badge de "Capa de Vida") + medalla A/B/C de citas | `confianza_dictamen.py` | Tiene un error de escala: recibe un valor 0-100 y lo compara contra umbrales 7 y 6, de una escala 0-10 (`confianza_dictamen.py:78-80` vs `vida.py:172`), así que el umbral nunca filtra |

Y hay contradicciones activas entre capas: una exige el correo institucional en todo dictamen y otra lo penaliza como "coda procesal" (`validador_dictamen.py:561-577` vs `post_validator.check_sin_coda_procesal`).

**Decisión: una sola escala, la de `confidence_scorer`, expresada de 0 a 100 y con desglose obligatorio.** Es la única que ya tiene siete factores ponderados y documentados (`confidence_scorer.py:1-22`), la única que le dice al auditor qué le falta ("subí el PDF del contrato en Tarifas"), y la que el propio equipo usó para corregir el gauge inflado (`glosa_service.py:6871-6878`). Las demás no desaparecen como *lógica*: se convierten en **filas de evidencia** dentro de la misma tarjeta.

La tarjeta única de explicabilidad, tal como debe verse:

```
CONFIANZA DE ESTE DICTAMEN: 72 / 100  ·  Revisar antes de radicar

  +20  Cláusula contractual literal aplicable   Contrato 440-DIGSA, cláusula 8, pág. 14
  +20  Citas verificadas contra el corpus       3 de 3 normas existen; 0 citas literales falsas
  +10  Auditoría contra la base sin hallazgos   Contrato y tarifa pactada confirmados
  +10  Cálculo numérico verificable             Objetado $1.240.500 = facturado − pactado
  +12  Calidad argumentativa                    Ataca la causal, cita textual, sin relleno
   +0  Precedente propio ganado                 SIN DATOS: aún no hay decisión registrada
                                                para (Dispensario, TA0201)
   +0  Soportes en el expediente                Falta la descripción quirúrgica (DQX)

  PARA SUBIR A 92:  adjuntar el DQX de la factura HUS529291  [Buscar en el share]
  DECISIÓN SUGERIDA: revisar y radicar         (auto-radicar desde 90)
```

Cuatro consecuencias de diseño, todas obligatorias:

1. **El nivel de autopiloto se deriva del score, no se calcula aparte.** Hoy hay dos clasificadores con umbrales distintos (0,90 contra 0,98/0,85) llegando ambos a la pantalla con taxonomías distintas (`auto_pilot_decision.py` y `autopiloto_nivel.py`). Uno solo, con umbrales configurables por la coordinación.
2. **Los checks se unifican en un solo motor con dos salidas**: "regenerar" (el modelo se corrige solo) e "informar al auditor". Hoy el mismo control está implementado tres veces con criterios distintos — placeholders entre corchetes, cifras inventadas, longitud verificada cuatro veces con cuatro umbrales incompatibles.
3. **Cada punto del score debe poder señalar el dato que lo justifica.** Un puntaje sin evidencia no es explicabilidad, es otro número.
4. **Cuando falta información, se dice "sin datos", no se rellena con un supuesto.** Es la misma regla de oro que ya cumple el Excel radicable: si un metadato no está poblado, degrada a texto genérico en vez de inventar (`excel_radicable.py`, docstring líneas 20-23).

---

## 9. Automatización: qué deja de hacer el humano (Fase 9)

### 9.1 El ciclo completo: qué se automatiza y qué no

Recorrido de punta a punta, desde que el pagador formula la glosa hasta que la plata entra. La columna "Hoy" describe lo que verificamos en el código y en la bitácora, no lo que dicen los manuales.

| # | Proceso | Hoy | ¿Automatizable? | Cómo | Qué se necesita | Prio |
|---|---|---|---|---|---|---|
| 1 | **Recepción / captura de la glosa** | Una persona entra al portal o al correo, baja un ZIP a Descargas y lo descomprime. El ingestor por correo quedó en esqueleto: su propio docstring lo admite y requiere un cron que no existe (`bandeja.py`, 123 l, sin llamadores) | **Sí, completa** | Agente de captura por pagador: entra, descarga el lote, sella fecha y hora de notificación y crea el lote en el sistema. Para los pagadores sin portal (PPL, FOMAG, Policía), lectura del buzón por IMAP | Que el reloj de vencimiento lo calcule el sistema desde la fecha de notificación y el perfil, **no una celda de Excel** — hoy si la columna VENCE viene vacía la fila se descarta y la glosa nunca existe (`recepcion_service.py:1021-1023`) | **P1** |
| 2 | **Clasificación y triaje** | Ya funciona y es lo mejor construido: detecta hojas, resuelve alias de columnas, calcula extemporaneidad por días hábiles con festivos colombianos, asigna gestor con delegación por vacaciones (`recepcion_service.py`) | **Ya lo está.** Solo hay que sacarlo del Excel | Mismo motor, disparado por el lote que trae el agente de captura | Que "no aplicar extemporaneidad" sea un atributo del perfil del pagador y no una frase que alguien escribe a mano en una celda (`recepcion_service.py:676-685`) | **P1** |
| 3 | **Respuesta de las repetitivas (ratificadas, extemporáneas, aceptadas, tarifa que coincide)** | Automático y a costo cero — decisión de negocio explícita y fechada (`recepcion_service.py:1073-1080`) | **Ya lo está** | Extenderlo a los otros tres caminos de generación masiva, que hoy no tienen esas defensas | Un solo motor de respuesta (hoy hay cuatro con cuatro niveles de concurrencia y cuatro conjuntos de enriquecimiento: la misma glosa sale con calidad distinta según por qué puerta entró) | **P1** |
| 4 | **Respuesta de las que exigen argumento** | El auditor decide; la IA redacta. Correcto que siga así | **No, y no debe.** La IA propone, el auditor decide (§2 del blueprint) | — | Cerrar el circuito de aprendizaje (8.2) para que cada mes redacte mejor | **P1** |
| 5 | **Control de calidad del lote antes de radicar** | Se hace, y muy bien — verificación adversarial con varios modelos buscando fallas, que en el lote del 17-jul encontró 8 respuestas que no atacaban el punto real (`BITACORA.md:78-85`) — pero **no deja ni un dato estructurado**. Es un ritual de chat | **Sí** | Checklist por familia + verificación de citas contra el corpus + estado "lote aprobado para radicar" con firma de quién aprobó | Encender el Quality Gate de fábrica (ya está construido y probado, y apagado por flag) | **P1** |
| 6 | **Radicación en el portal** | Los bots hacen esto y lo hacen bien: el lote del 9 de julio subió 102 facturas y 225 objeciones, verificadas al 100 %, en ~22 minutos (`BITACORA.md:67-70`). Pero se lanzan desde PowerShell con rutas de 120 caracteres | **Sí, el lanzamiento y el gobierno; no el bot** | Motor universal de bots (9.2), lanzado desde la pantalla de Automatización | Que el frontend sepa que los bots existen: hoy hay **0 ocurrencias** de "RPA", "robot" o "Playwright" en las 23.125 líneas de `static/index.html` | **P1** |
| 7 | **Volcado del resultado a la aplicación** | Manual y poco confiable. El resultado del bot vive en un CSV del escritorio; alguien debe acordarse de marcar "radicada" en la app. El registro manual ya estuvo equivocado (`docs/diagnostico_lote_v2_pendientes/INFORME_GERENCIA.md:39-47`) | **Sí, completa** | El bot escribe el estado y el pantallazo en el expediente al terminar cada factura, no una persona después | Un solo agente local (hoy son dos procesos, dos tokens y dos configuraciones en la misma PC: `jumpbox_sync.py` y `agente_lotes.py`) | **P1** |
| 8 | **Soportes** | El sistema indexa hasta 144.000 archivos y termina mostrando **la ruta como texto** con un botón "Copiar" para pegarla en el explorador de Windows. No hay un solo `FileResponse` en el router de soportes | **Sí** | Endpoint que devuelva el archivo, visor en línea y adjuntar-al-expediente en un clic. Y la búsqueda tolerante que el bot ya sabe hacer (PDX > HAM > PDE, carpetas ENV alternativas) subida al servidor | Registro de acceso a datos del paciente en cada apertura | **P1** |
| 9 | **Evidencia de radicación** | Semi-manual: el bot captura el pantallazo; después una persona pide el consecutivo institucional GI-33 **por chat** y corre un script para armar el Word (`BITACORA.md:196-197`) | **Sí, completa** | El consecutivo es un contador: lo asigna el sistema. El PDF de evidencias se arma solo al cerrar el lote y queda pegado al expediente | Contador institucional persistido. Elimina de paso el "N.º OBJECIÓN" generado con `Math.random()` que hoy se imprime en el documento que se radica (`index.html:18095`, impreso en `:18192`) | **P1** |
| 10 | **Seguimiento y vencimientos** | El semáforo tiene estado negro y **no dispara nada**. Además la consulta de alertas filtra `dias_restantes > 0`, o sea que **esconde justamente las ya vencidas** (`glosa_repository.py:445`) | **Sí** | Una sola consulta de vencimientos que ponga primero lo vencido, y escalamiento automático al coordinador (no al gestor) cuando entra en negro | Corregir el filtro y unificar las siete superficies que hoy responden la misma pregunta | **P1** |
| 11 | **Decisión de la EPS** | Se escribe a mano en un `prompt()` del navegador. De ese dato dependen todas las estadísticas de recuperación y todo el aprendizaje | **Parcialmente**: lo que llega por portal o correo estructurado, sí; lo que llega en PDF, con lectura asistida y confirmación humana | Ingesta desde el portal (el verificador de estado de COOSALUD ya lo hace en 234 líneas) + selector con opciones, nunca texto libre | Modelo de objeción con línea de tiempo propia | **P1** |
| 12 | **Conciliación** | La transición "la EPS ratificó → crear la conciliación" es totalmente manual, aunque el sistema tiene todos los datos. Y la conciliación real se hace con un CLI en el PC del auditor y un TSV: 226 facturas, 4 actas, $277.231.324 glosados de los que se aceptaron $71.901.424 | **Sí la preparación y el papeleo; no la negociación** | Al registrar RATIFICADA, el sistema crea la mesa con las glosas agrupadas, los contraargumentos probables y el piso sugerido | Que el módulo web tenga los campos del TSV que de verdad se firma (radicado, acta, valor factura, total glosas, valor aceptado) | **P2** |
| 13 | **Acta** | Se cierra en el sistema pero **no cierra nada**: no transiciona la glosa ni escribe el valor recuperado, así que hay que registrarlo otra vez por otro camino para que aparezca en el tablero | **Sí, completa** | Cerrar acta = transicionar las N glosas + escribir valor recuperado + generar el PDF + alimentar cartera y aprendizaje, en una sola acción | Participantes como filas, no como texto libre: un acta legal cita a cada persona con nombre y cargo | **P1** (es un arreglo chico con impacto grande) |
| 14 | **Nota crédito y CUV** | Ocho scripts encadenados a mano, 2.682 líneas, para mover y renombrar archivos. Y el proceso miente sobre sí mismo: el registro previo daba 5 facturas como "subida OK al SIMED" y ninguna tenía CUV válido | **Sí** | Un solo comando con etapas (extraer → renombrar → agrupar → verificar) sobre la nomenclatura declarada en el perfil, y **validación del CUV antes de intentar el cargue** | Que la nomenclatura sea un campo del perfil y no una convención en la cabeza del operador | **P2** |
| 15 | **Cartera** | Un tablero HTML de escritorio alimentado por una planilla manual. Y dentro de la aplicación, dos de los tres endpoints de cartera **suman el saldo una vez por glosa**: una factura con 5 glosas abiertas reporta 5 veces su saldo | **Sí** | Modelar la **factura** como entidad (número, valor, saldo, radicación, estado de cobro) y colgar las glosas de ella. El modelo correcto ya existe, pero fuera de la aplicación: `tools/tablero_cartera.py:139-195` | Traer ese modelo adentro. Es la mejor decisión de rediseño disponible en todo el sistema de datos | **P1** |
| 16 | **Informes** | El único informe para gerencia se pide con dos ventanas emergentes (`prompt('Año')`, `prompt('Mes')`) y se abre con `window.open`: si el navegador bloquea emergentes, no pasa nada y el usuario no se entera | **Sí, completa** | Un informe mensual, una sola fuente de datos, tres salidas (pantalla, PDF, Excel), generado y enviado por correo automáticamente el día 1 | **Una sola definición de "recuperado"**: hoy hay cinco fórmulas incompatibles y cuatro conviven en la misma barra de pestañas del coordinador. Sin esto ningún informe es firmable | **P1** |

---

### 9.2 El Motor Universal de bots

**Primero, el hallazgo, porque cambia el diseño.** La hipótesis de partida era que los bots hacen todos el mismo recorrido (recibir → clasificar → analizar → generar → exportar → historial) y que por eso conviene un motor único con perfiles. **La conclusión es parcialmente cierta, y por una razón más grave que la supuesta:**

- **Los bots no hacen ese recorrido. Hacen solo el último tramo.** Ninguno clasifica, ninguno analiza, ninguno genera respuestas, ninguno guarda historial. Prueba: en los cuatro bots no hay **una sola llamada HTTP que no sea al portal**. Reciben un Excel que un humano ya resolvió y lo tipean.
- **Las etapas de clasificar, analizar y generar sí existen** — pero viven en `app/` y no están conectadas con los bots. **El puente entre las dos mitades es un archivo Excel que viaja en el escritorio de una PC.**
- **Corrección factual al encargo:** no hay Selenium en el repositorio (`grep -rln selenium tools/ app/` → 0 resultados, verificado). Son **4 bots con Playwright contra 2 portales web** y **3 scripts con pywinauto contra una aplicación de escritorio**. Los pagadores con bot son **cuatro hoy**: COOSALUD, SIMED-glosas, SIMED-soportes y DGH. Los cinco que el cliente ya nombró — **SAVIA, EMSSANAR, VCO, MUTUAL SER y FOMAG** — no existen todavía: escritos con el patrón actual, el parque llegaría a **nueve bots**. Ese es el mejor argumento económico de esta fase: **consolidar hoy con cuatro cuesta una fracción de lo que costará con nueve.**
- Y de los 33 scripts de `tools/` (16.100 líneas), **solo 7 son RPA** (37 % de las líneas). Los otros 26 son procesamiento de archivos, Excel y PDF.

**Lo que la hipótesis subestima: cuánto de un bot es genuinamente el portal.** El 40-50 % de cada bot grande es manipulación del navegador específica de esa plataforma, y ese conocimiento está pagado con meses de producción. Ejemplos textuales que ningún rediseño debe tirar: *"el datatable filtra con eventos de teclado; `fill()` setea el valor sin teclas y la grilla nunca filtra"* (`responder_glosas_coosalud.py:636-638`); *"el modal del portal es de un solo uso por carga de página: el primer Responder Glosa funciona, el segundo queda deshabilitado para siempre"* (`:1257-1261`); *"el modal con cientos de glosas marcadas se rompe; partimos en tandas de 200"* (`:1252-1254`). Eso no se reescribe: **se hereda**.

**Y ya hay una prueba empírica de que la arquitectura propuesta funciona:** `verificar_glosas_coosalud.py` hace `import responder_glosas_coosalud as core` y construye una herramienta completa en 234 líneas reutilizando login, navegación, lectura de Excel, credenciales y logging **sin copiar una sola función** (`:36`). Hoy es la excepción; la Fase 9 la convierte en la regla.

**La duplicación, medida (no estimada).** Comparando el cuerpo de cada función entre bots: `setup_logging` idéntica al 100 % (3 copias), `_screenshot_debug` 92 % entre los dos de SIMED y 86 % contra COOSALUD, `cargar_credenciales` 85 % (4 copias, solo cambia el nombre de la variable de entorno), `login` 51 % **entre los dos bots del mismo portal**. Y `cargar_indice` al 52 %: dos copias que leen el **mismo** archivo TXT con **dos expresiones regulares distintas** — una devuelve la factura larga y la otra la normaliza a corta. El ahorro literal son ~150 líneas; el valor real es que hoy un arreglo en el índice hay que aplicarlo dos veces, de dos maneras.

Caso extremo: `responder_glosas_simed.py` y `cargar_soportes_simed.py` atacan **el mismo portal, con las mismas credenciales, el mismo login y el mismo filtro**, en dos implementaciones paralelas. El código lo admite y no lo resuelve: *"Idéntica lógica a cargar_soportes_simed.py — el portal es el mismo"* (`responder_glosas_simed.py:423`).

**Arquitectura propuesta: tres capas**

```
        ┌──────────────────────────────────────────────────────────┐
        │  PERFIL DE PAGADOR  (datos, editables sin programador)   │
        │  identidad · contrato · portal · columnas · reglas ·      │
        │  estilo · plazos · entregable · rutas                     │
        └──────────────────────────────────────────────────────────┘
                                   │  alimenta a
        ┌──────────────────────────────────────────────────────────┐
        │  NÚCLEO COMÚN  (uno solo, con tests, nunca se duplica)    │
        │  sesión · credenciales (vault) · runner con reintentos    │
        │  y relogin · reporte incremental · evidencia · índice     │
        │  del share · normalización de factura · sanitización      │
        └──────────────────────────────────────────────────────────┘
                                   │  usa
        ┌──────────────────────────────────────────────────────────┐
        │  ADAPTADOR POR PORTAL  (lo único que se escribe nuevo)    │
        │  hoy:  COOSALUD · SIMED · DGH                             │
        │  luego: SAVIA · EMSSANAR · VCO · MUTUAL SER · FOMAG       │
        │  acciones: responder_glosa · cargar_nota_credito ·        │
        │            verificar_estado · descargar_lote              │
        └──────────────────────────────────────────────────────────┘
```

| Pieza del núcleo | Qué resuelve | De dónde sale (ya existe, hay que consolidarlo) |
|---|---|---|
| **Sesión** | Abrir navegador, contexto, diálogos, relogin | Los 3 bots Playwright, hoy con 3 implementaciones |
| **Credenciales** | Resolver por perfil, desde el vault cifrado con motivo y registro de acceso | `credenciales_vault.py` — el mejor módulo de seguridad del repositorio, **sin pantalla**, por eso el equipo sigue guardando las claves en un Excel |
| **Runner** | Interfaz de línea de comandos, tandas, reintentos, relogin (máximo 5), resumen por estado, reanudación | Hoy `main()` está reescrito en cada bot: 310 líneas en COOSALUD y 245 en SIMED que son la misma máquina con 10 % de texto en común. **Y la reanudación solo existe en un bot** (`--saltar-csv`); si SIMED se corta en la factura 60 de 102, hay que volver a pasar por todas |
| **Reporte** | Escritura incremental a prueba de cortes, con estados **en español de negocio** | El mecanismo ya existe (vuelca cada 5 facturas, nacido de perder 4 horas de trabajo). Falta traducir `TERMINADA_SIN_CARTEL` a *"cerrada, pero el portal no mostró la confirmación: verificar"* |
| **Evidencia** | Pantallazo de cierre + subida automática al expediente | Los bots ya capturan el cartel de éxito con el diálogo visible (`:1196-1204`). Hoy la imagen se queda en una carpeta local |
| **Índice del share** | Una sola implementación, con la normalización de factura como parámetro del perfil | Hoy dos copias con dos expresiones regulares distintas + un TXT de 133.000 líneas en el escritorio de una PC |

**Tres reglas de gobierno que evitan que la duplicación vuelva:**

1. **`tools/` solo extrae y ejecuta. Todo entregable se genera en el servidor.** Hoy hay tres generadores de Excel de respuesta, uno de ellos en `tools/`, y un tablero de cartera de escritorio que se desincroniza con la base por diseño.
2. **Nada de dos motores de glosa fuera de la API.** `asistente_conciliacion_dispensario.py` (727 l) y `motor_glosas_hus.py` (399 l) reimplementan peor y sin IA lo que ya hace `app/`, y además **contradicen al backend**: para uno `CL` es "calidad" y para el otro "pertinencia clínica"; `PDX` significa dos cosas clínicas distintas según el archivo. Se eliminan los dos. Se rescata **una sola cosa** del primero, que el backend hoy no tiene y es genuinamente valiosa: la **matriz de evidencia** (por cada soporte que la familia de glosa exige: si está, en qué archivo y en qué página).
3. **El adaptador DGH sobrevive, y va en las dos direcciones.** El bot DGH desaparece como script suelto, no como capacidad: DGH es el único lugar donde la glosa existe contablemente, y hoy se alimenta a mano en ambos sentidos. El adaptador `dgh` nace con dos acciones obligatorias — *registrar la respuesta/objeción* y *traer el estado contable de la factura* — y se construye en el mismo paquete que el motor de bots. Borrar la única automatización que existe sin poner nada en su lugar no es una opción, y por eso queda con dueño y fecha dentro de esta fase.

**Un solo agente local instalado en el hospital**, con una credencial, que sincronice el share y ejecute los bots, y que se vea desde la aplicación. La ventana de escritorio con doble clic ya existe y es el único punto del repositorio donde alguien pensó en el auditor y no en el desarrollador (*"cero PowerShell, cero setx"*) — está enterrada en una carpeta de scripts, sin instalador y sin mención en la app.

---

### 9.3 El contrato del Perfil de pagador

Hoy el mismo pagador está descrito en **tres lugares que nadie reconcilia**: `data/perfiles_radicacion.json` (**12 entidades**, con canal, portal, nomenclatura y CUV), `app/services/perfil_eps.py` (estilo argumental, táctica, qué evitar) y **constantes dentro de cada bot** (URLs, nombres de columna, códigos por defecto, prefijos de soporte, límites). A eso se suman los contratos por triplicado (`CONTRATOS_HUS` en código, `CONTRATOS_DEFAULT` en el arranque y la tabla `contratos`, cuyas 15 columnas estructuradas están **vacías en las 13 filas reales**).

**El tamaño real del problema, para dimensionar el trabajo:** son **12 entidades** en el catálogo de radicación y **cuatro portales con bot** (nueve cuando entren los cinco pagadores ya nombrados). No hay un parque de cientos de perfiles. Eso cambia dos cosas: la migración de perfiles se hace en días, no en meses, y **el panel de credenciales del vault es una pantalla de listado, revelar-con-motivo y bitácora de acceso para una docena de entradas** — no un proyecto de gestión de secretos a escala. Cualquier estimación que asuma cientos de entidades está inflada.

El contrato del perfil unificado **extiende** el que ya funciona (`radicar_facturacion.py:266-281`, con `cargar_perfiles` y resolución tolerante de nombres sucios del mundo real) — no inventa uno nuevo. Ficha completa de ejemplo, en el formato en que el auditor la editará desde la pantalla:

```yaml
# ═══════════════════════════════════════════════════════════════════════════
# PERFIL DE PAGADOR — absorbe perfiles_radicacion.json (12 entidades)
# + perfil_eps.py + las constantes que hoy viven dentro de cada bot.
# Editable por la coordinación desde la pantalla. Cada cambio queda versionado.
# ═══════════════════════════════════════════════════════════════════════════

identidad:
  id: COOSALUD                          # clave única, nunca cambia
  nombre_legal: "COOSALUD EPS S.A."
  nombre_corto: "COOSALUD"
  alias: ["COOSALUD", "COOSALUD EPS", "COOSALUD E.P.S.", "COOSALUD EPS-S"]
  # Los alias resuelven los nombres sucios del mundo real. Se elige SIEMPRE
  # el alias más largo que coincida, para no confundir "SALUD TOTAL" con "SALUD".
  nit: "900226715"                      # HOY VACÍO en el JSON: completar desde el RUT.
                                        # Un NIT errado causa devolución de la radicación.
  codigo_pagador: ""                    # código interno de cartera (DGH), si aplica
  regimen: SUBSIDIADO                   # CONTRIBUTIVO | SUBSIDIADO | ESPECIAL_FFMM |
                                        # ARL | SOAT_ADRES | PPL | MAGISTERIO
  tipo: EPS                             # EPS | ENTIDAD_ESTATAL | ARL | FONDO

# ───────────────────────────────────────────────────────────────────────────
# CONTRATO Y TARIFA — vigencias POR FECHA DE ATENCIÓN, no por fecha de glosa.
# Esto no es un detalle: 372 de 444 glosas de un lote venían marcadas
# "SIN CONTRATO" cuando por fecha de atención sí lo tenían (BITACORA.md:105-111).
# ───────────────────────────────────────────────────────────────────────────
contrato_y_tarifa:
  vigencias:
    - numero: "CTO-COOSALUD-2025"
      desde: 2025-01-01
      hasta: 2025-12-31
      base_tarifaria: "SOAT"
      factor: -0.15                     # SOAT menos 15 %
      modalidad: "EVENTO"
      documento: "contratos/coosalud-2025.pdf"   # el PDF del que se extraen
                                                 # las cláusulas literales con página
    - numero: "CTO-COOSALUD-2026"
      desde: 2026-01-01
      hasta: 2026-12-31
      base_tarifaria: "SOAT"
      factor: -0.20
      modalidad: "EVENTO"
      documento: "contratos/coosalud-2026.pdf"
  tarifas_propias_aplicables: ["RES-HUS-054-2026", "RES-HUS-124-2026"]
  notas_contractuales: >
    Exclusiones y anexos que el dictamen debe conocer. Texto libre corto,
    citable por la IA. NO reemplaza a las cláusulas extraídas del PDF.

# ───────────────────────────────────────────────────────────────────────────
# PORTAL Y CREDENCIALES — reemplaza las constantes hardcodeadas del bot
# (responder_glosas_coosalud.py:86-89 y :124-135) y las variables de entorno.
# ───────────────────────────────────────────────────────────────────────────
portal:
  canal: PORTAL_BOT                     # PORTAL_BOT | PORTAL_MANUAL | CORREO | ADRES
  motor: PLAYWRIGHT                     # PLAYWRIGHT | PYWINAUTO | API | NINGUNO
  adaptador: "coosalud"                 # nombre del adaptador, no ruta de script
  base: "https://vco.ctamedicas.com"
  rutas:
    login:  "/app/login"
    inicio: "/app/inicio"
    bolsa:  "/app/respuestaGlosaSearch"
    pausa:  "/app/respuestaGlosaPause"
  acciones_soportadas: [responder_glosa, verificar_estado, descargar_lote]
  particularidades:                     # conocimiento pagado con meses de producción.
                                        # Cada línea evita una jornada perdida.
    - "El buscador filtra por eventos de teclado: escribir carácter a carácter."
    - "El modal es de un solo uso por carga de página: recargar entre grupos."
    - "Partir en tandas de 200 glosas: por encima, el modal se rompe."
    - "Facturas de 1.000+ glosas: reintentar 2 veces; la cuenta queda En Pausa
       y la siguiente corrida la retoma desde ahí."
  sanitizacion_texto: NINGUNA           # SIMED exige NINGUNA_TILDE (solo [A-Za-z0-9]
                                        # y espacios), COOSALUD acepta texto normal
  max_pdf_mb: 10

credenciales:
  origen: VAULT                         # nunca variables de entorno ni texto en claro
  referencia: "vault://pagador/COOSALUD"
  usuario_visible: "6800100792**"       # enmascarado en pantalla y en logs
  # Revelar el secreto exige motivo de al menos 5 caracteres y queda registrado
  # con usuario, fecha y motivo. El mecanismo YA existe (credenciales_vault.py);
  # lo que falta es la pantalla, y esa pantalla administra 12 entidades
  # (cuatro con bot hoy, nueve proyectadas): es una tabla, no un proyecto.

# ───────────────────────────────────────────────────────────────────────────
# FORMATO DE FACTURA — el Dispensario exige HUS corto (HUS487523); el portal
# rechaza el largo. Hoy eso se recuerda con un flag en cada corrida (--hus-corto).
# ───────────────────────────────────────────────────────────────────────────
formato_factura:
  patron_interno: "HUS\\d{4,12}"
  formato_para_portal: LARGO            # LARGO (HUS0000487523) | CORTO (HUS487523)

# ───────────────────────────────────────────────────────────────────────────
# MAPEO DE COLUMNAS — entrada (lo que manda el pagador) y salida (lo que
# consume el bot). Hoy vive dentro de cada bot y difiere entre ellos.
# ───────────────────────────────────────────────────────────────────────────
mapeo_columnas:
  hoja_por_defecto: "BASE"
  hojas_alternas: ["CALIDAD"]
  entrada:
    id_glosa:        ["ID_GLOSA", "ID GLOSA"]
    numero_factura:  ["NUMERO_FACTURA", "NUMERO FACTURA"]
    familia:         ["TIPO_GLOSA", "TIPO GLOSA"]
    codigo_glosa:    ["CODIGO_GLOSA", "COD GLOSA"]
    valor_objetado:  ["VALOR GLOSA", "VALOR OBJETADO"]
    observacion_eps: ["OBSERVACION GLOSA", "MOTIVO"]
  salida:
    codigo_respuesta: "COD RESPUESTA GLOSA"
    texto_respuesta:  "OBSERVACION RTA GLOSA"
    valor_aceptado:   "VALOR ACEPTADO"
  # El mapeo de familias traduce el vocabulario del pagador al catálogo oficial
  # (Res. 2284/2023). NO redefine conceptos: hoy 'CL' significa "pertinencia
  # clínica" en el backend y "calidad" en un script, y eso ya produjo errores.
  traduccion_familias:
    "CALIDAD":     "CL"     # en la planilla de COOSALUD, CALIDAD = pertinencia
    "PERTINENCIA": "CL"
    "TARIFAS":     "TA"
    "SOPORTES":    "SO"
    "FACTURACION": "FA"

# ───────────────────────────────────────────────────────────────────────────
# REGLAS DE RESPUESTA — postura institucional y automatismos por familia.
# ───────────────────────────────────────────────────────────────────────────
reglas_respuesta:
  postura_por_defecto: NO_ACEPTA        # se defiende el 100 % del valor
  codigo_respuesta_por_defecto: "RE9901"
  codigos_sin_soporte: ["RE9502"]       # extemporánea: se rechaza por vencimiento
                                        # del plazo legal, no por falta de soporte
                                        # clínico. Sin esta regla, esas glosas
                                        # quedaban esperando un PDF que no existe.
  familias_que_no_responde_el_bot: ["CL"]   # pertinencia la trabaja el equipo médico;
                                            # la factura queda abierta a propósito
  exige_soporte_si:
    - "familia == SO"
    - "la justificación de la EPS contiene 'ANEXA SOPORTE'"
  politica_si_falta_el_soporte: SALTAR_Y_MARCAR_PENDIENTE
    # Nunca prometer un soporte que no se adjuntó. Esta honestidad operativa
    # ya está en el bot y debe sobrevivir textualmente.
  texto_residuales: >
    ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE PERTINENCIA INTERPUESTA POR
    COOSALUD SOBRE LOS SERVICIOS EN MENCION...

# ───────────────────────────────────────────────────────────────────────────
# ESTILO ARGUMENTAL — absorbe perfil_eps.py, hoy un cuarto catálogo por EPS.
# ───────────────────────────────────────────────────────────────────────────
estilo:
  registro: "administrativo"
  formato: "MAYUSCULAS_UN_PARRAFO"
  apertura: "ESE HUS NO ACEPTA LA GLOSA APLICADA A LA FACTURA"
  caracteristicas: >
    Auditoría de alto volumen, revisan rápido. Responden bien a cifras exactas,
    cálculo tarifario visible y estructura clara.
  tactica: "Cifras exactas + contrato vigente + tarifario pactado."
  evitar: "Argumentación extensa sin cifras concretas."
  cierre: "Solicitud directa de reconocimiento con monto específico + mesa de conciliación."
  jurisprudencia_prohibida: []          # p. ej. el Dispensario NO admite T-760/2008

# ───────────────────────────────────────────────────────────────────────────
# PLAZOS LEGALES — hoy hay CINCO versiones distintas de los plazos del trámite
# dentro del mismo repositorio, incluida la documentación con la que se capacitó
# a los gestores. Citar mal el artículo en un dictamen radicado es munición
# para el pagador.
# ───────────────────────────────────────────────────────────────────────────
plazos:
  norma_marco: "Ley 1438/2011 art. 57"
  dias_formulacion_pagador: 20          # hábiles
  dias_respuesta_prestador: 15
  dias_subsanacion: 7
  dias_decision: 10
  dias_pago: 5
  aplica_extemporaneidad: true          # PPL / FOMAG / FF.MM. van en false, POR RÉGIMEN.
                                        # Hoy esto se logra escribiendo a mano
                                        # "NO APLICAR EXTEMPORANEIDAD" en una celda:
                                        # un error de tipeo cambia la defensa jurídica.
  umbrales_semaforo_dias: { verde: 11, amarillo: 5, rojo: 1 }
  calendario: "FESTIVOS_COLOMBIA"

# ───────────────────────────────────────────────────────────────────────────
# ENTREGABLE Y RADICACIÓN
# ───────────────────────────────────────────────────────────────────────────
entregable:
  nomenclatura_soportes: "ADRES"        # ADRES | DISPENSARIO_HUS_CORTO | LIBRE
  cuv_obligatorio: true
  soportes_base_obligatorios: ["FEV", "RIP", "CUV"]
  soportes_extra: []
  formato_paquete: "ZIP_FACTURA"        # ZIP_FACTURA | CARPETA
  evidencia_requerida: ["PANTALLAZO_CIERRE"]
  consecutivo_institucional: "GI-33"    # lo asigna el sistema, no se pide por chat

rutas:
  # Rutas lógicas: el agente local las resuelve contra el share del hospital.
  # Nunca rutas relativas: correr el mismo bot desde dos carpetas distintas
  # deja la evidencia legal repartida en dos sitios sin que nadie avise.
  indice_soportes: "share://BUSCADOR_HUS/indice_facturas_HUS.txt"
  soportes_por_factura: "share://SOPORTES/{factura}"
  prefijos_soporte_preferidos: ["PDX", "HAM", "PDE"]
  carpetas_alternas: ["ENV-{numero_envio}-*"]
  evidencia: "expediente://{factura}/evidencia"     # al expediente, no a una carpeta
  reportes: "expediente://lote/{lote_id}"
```

**Quién lee este perfil:** el motor de IA (contrato, estilo, plazos), el radicador, el bot (portal, columnas, reglas, rutas), el calculador de vencimientos, el generador del entregable y el tablero de cartera. **Un solo archivo, seis consumidores.** Agregar SAVIA o MUTUAL SER pasa a ser llenar una ficha y escribir un adaptador de portal, no clonar 1.700 líneas.

---

### 9.4 Qué gana el hospital

**Supuestos explícitos, declarados porque de ellos depende todo lo que sigue:**

- **Volumen mensual de respuesta.** Los bots **procesaron 324 facturas y 597 objeciones en siete lotes** del Dispensario/SIMED entre el 26 de junio y el 17 de julio (`BITACORA.md:173-181`). De esos siete, **cuatro están confirmados como subidos** (26-jun, 1-jul, 6-jul y 9-jul: ~235 facturas y ~400 objeciones, sin valor registrado en la bitácora). De **los tres últimos, por $153.675.820, el Excel está listo y la subida no está confirmada** ("confirmar subida" y "subir YA — plazos vencidos"). **Las filas de la tabla que dependen de trabajo efectivamente radicado se calculan sobre 235 facturas, no sobre 324.** Si esos tres lotes se confirman, el volumen sube a 324 facturas y el ahorro a ~47 h/mes; hasta que se confirmen, no se cuentan.
- Un lote COOSALUD de **69 facturas y 31.515 glosas** (`docs/CONTEXTO_COOSALUD.md:120-122`).
- Conciliación: histórico de 226 facturas y 4 actas; se asume **2 mesas al mes**.
- Notas crédito: **12 facturas** por lote (lote V2).
- **Se toma como "mes tipo" el ritmo observado en julio de 2026.** No hay serie de doce meses: si el volumen cae a la mitad, el ahorro cae en la misma proporción.
- **Los minutos por unidad son supuestos declarados, no mediciones: el sistema no registra tiempo por tarea.** Lo que sí está medido y sirve de ancla: el bot sube 102 facturas y 225 objeciones en **~22 minutos**, y una ratificación con evidencia se responde en **0,7 minutos**.
- No se cuenta la redacción del dictamen: ya está automatizada y contarla sería inflar el resultado.

| Tarea que hoy hace una persona | Evidencia de que hoy es manual | Vol./mes | min/u | h/mes hoy | h/mes después | **Libera** |
|---|---|---|---|---|---|---|
| Bajar el lote del portal/correo y ordenarlo | Ingestor por correo en esqueleto sin cron (`bandeja.py`) | 7 lotes | 25 | 2,9 | 0,2 | **2,7** |
| Armar el Excel intermedio para el bot | `extraer_respuestas_glosa.py` + `convertir_tramite_masivo.py` existen solo porque el bot no habla con el motor | 7 lotes | 45 | 5,3 | 0,0 | **5,3** |
| Operar el bot desde PowerShell (rutas, pases 1/2/3, `--saltar-csv`) | `docs/CONTEXTO_COOSALUD.md:106-120`; el frontend no sabe que los bots existen | 10 corridas | 35 | 5,8 | 1,0 | **4,8** |
| Volcar el resultado del bot a la aplicación factura por factura | El resultado vive en un CSV del escritorio; `marcar-radicada` es un botón que alguien debe recordar | 235 fact. (confirmadas) | 1 | 3,9 | 0,0 | **3,9** |
| Buscar y abrir soportes en el explorador de Windows | El sistema muestra la ruta como texto con botón "Copiar" (`index.html:21606`); no hay endpoint que devuelva el archivo | ~235 | 2 | 7,8 | 2,0 | **5,8** |
| Registrar la decisión de la EPS | Se escribe a mano en un `prompt()` (`index.html:20390`) | ~235 | 1,5 | 5,9 | 2,0 | **3,9** |
| Crear la conciliación y cerrar el acta con doble digitación | `cerrar-acta` no transiciona la glosa ni escribe el valor recuperado (`conciliacion.py:290-324`) | 2 mesas | 90 | 3,0 | 1,0 | **2,0** |
| Pedir el consecutivo por chat y armar el Word/PDF de evidencias | `BITACORA.md:196-197` | 7 lotes | 30 | 3,5 | 0,3 | **3,2** |
| Encadenar a mano los 8 scripts de notas crédito y verificar el CUV | 2.682 líneas en 8 ejecutables que el operador encadena | 12 fact. | 20 | 4,0 | 1,0 | **3,0** |
| Mantener la cartera en planilla y correr el tablero de escritorio | `tools/tablero_cartera.py` se alimenta de una planilla manual | 4 sem. | 120 | 8,0 | 1,0 | **7,0** |
| Armar el informe de gerencia | Se pide con dos `prompt()` y se abre con `window.open` | 1 | 180 | 3,0 | 0,5 | **2,5** |
| | | | **Total** | **53,1** | **9,0** | **≈ 44 h/mes** |

**44 horas al mes son cinco jornadas y media completas de un auditor**, liberadas del trámite y devueltas a lo único que no se puede automatizar: decidir qué se defiende, con qué argumento y hasta qué monto se concilia. La cifra es deliberadamente conservadora: cuenta solo el trabajo que consta como radicado.

**Y hay dos ganancias que no caben en la tabla de horas, y que valen más:**

1. **La plata que hoy queda expuesta por vencimiento.** Tres facturas del Dispensario con vencimiento el 6 y el 8 de julio se descubrieron el **22 de julio**, dos semanas después del primer vencimiento y por revisión manual, no por el sistema: **38 objeciones, $20.054.751** (`BITACORA.md:86-91` y `173-181`). Ese monto no está defendido ni recuperado: es **plata en riesgo**, cuya suerte depende de que el portal todavía acepte la respuesta o de radicarla por oficio con constancia. El semáforo negro ya existe en el código y no dispara nada; el aviso de la pantalla de Inicio (8.4) y el arreglo del filtro que esconde lo vencido (`glosa_repository.py:445`) son lo que convierte ese hallazgo casual en una alerta del sistema.
2. **Lo que se deja de creer sin evidencia.** En el lote de notas crédito V2, **5 facturas figuraban como "Subida OK al SIMED" y ninguna tenía CUV válido**; en total, 8 de 12 estados registrados a mano no coincidían con el estado real verificado (`docs/diagnostico_lote_v2_pendientes/INFORME_GERENCIA.md:39-47`). Cuando el estado lo escribe el sistema a partir de lo que devuelve el portal, la pregunta "¿esta objeción se radicó, cuándo, con qué evidencia y cómo terminó?" se responde en un clic y no en tres carpetas y un chat.

**Cómo se valida esta estimación en lugar de discutirla:** la Fase 9 introduce el modelo `Lote` / `LoteItem` con marca de tiempo por etapa. A las dos semanas de operación, el hospital deja de estimar horas y las mide — y esa medición reemplaza a los supuestos de esta tabla, sin excepciones.

---

## 10. Roadmap por versiones (Fase 10)

Las 7 fases del blueprint (`docs/SINAC_OS.md` §19) describen **qué** hay que construir. Esta sección define **en qué orden se entrega, cuánto cuesta y por qué**, agrupando esas fases en cuatro versiones que se pueden instalar, usar y medir de forma independiente. Ninguna versión termina en "quedó a medias": cada una cierra un ciclo completo de trabajo del auditor.

### 10.1 Una sola contabilidad de esfuerzo (sin esto, los tiempos no significan nada)

**Regla de este documento: todo el esfuerzo del proyecto se cuenta aquí, en §10, y en una sola unidad — la semana-persona.** Las 49,5 semanas-persona de las doce funciones nuevas de §6 (N1–N12) **están dentro** de los paquetes de esta sección, no encima. Ningún trabajo se cuenta dos veces y ningún paquete queda sin dueño de versión.

Este es el mapa completo de las doce propuestas de §6 dentro del roadmap. Si el cliente aprueba §6, está aprobando estos paquetes:

| Propuesta de §6 | Semanas | Paquete de §10 | Versión |
|---|---|---|---|
| N1 · Reloj de vencimientos con escalamiento | 2 | C1 | **2.0** |
| N4 · Perfil de Pagador único y editable | 4 | A2 | **2.0** |
| N8 · Un solo número (definición única + informe firmable) | 3 | C2 (2) + R7 (1) | **2.0** / 2.2 |
| N9 · Expediente único de la factura | 7 | E1 | 2.1 |
| N2 · Expediente leído de verdad (fin del truncado) | 4 | E2 | 2.1 |
| N11 · Copiloto contextual | 5 | E4 | 2.1 |
| N5 · Panel del vault de credenciales | 1,5 | E5 | 2.1 |
| N7 · Centro de Automatización (tablero de bots) | 5 | R2 | 2.2 |
| N3 · Puente Orquestador (el bot le pide al motor) | 5 | R3 | 2.2 |
| N6 · Conciliación sin Excel | 4 | R6 | 2.2 |
| N12 · Captura automática del lote en el portal | 6 | R8 | 2.2 |
| N10 · Probabilidad calibrada y medida | 3 | L2 | 3.0 |
| **Subtotal §6** | **49,5** | | |

El resto del esfuerzo del programa (47,5 semanas) es de dos clases: **36 semanas de refactorización, borrado y arreglo de la interfaz** —que no son "funciones nuevas" pero son lo que hace posible construir las nuevas sin multiplicar el costo— y **11,5 semanas de siete piezas que faltaban en el plan** y que se incorporan en esta versión del roadmap: el adaptador DGH de dos direcciones, el subproceso de devoluciones, el respaldo fuera de la VM, el cierre de las dos fugas de datos de paciente, el cliente único de IA que registra el costo y la capacitación de cada versión.

#### Supuesto de capacidad: quién trabaja

| Recurso | Dedicación | Evidencia de que el ritmo es real |
|---|---|---|
| **1 desarrollador senior asistido por IA** (el mismo esquema de trabajo actual) | Tiempo completo | En ~4 meses (abril–julio 2026) se construyó el sistema completo: **626 archivos `.py` en `tests/`** (616 de ellos empiezan por `test_`), una suite que ejecuta **4.266 pruebas** (corrida real del 23 de julio), 33 rondas de auditoría del motor y 4 bots de portal (BITACORA.md) |
| **Yesid Pérez como dueño del producto** | 1–2 h/día para validar dictámenes reales y decidir reglas de negocio | Las 32 "redes finales" y las reglas 8.x del prompt nacieron de casos reales validados por el área, no de diseño teórico (`app/services/glosa_ia_prompts.py:698-749`) |
| **Un responsable de TI del hospital** | 2 h/semana, para la ventana de despliegue y el respaldo fuera de la VM | La VM del hospital es de 1 vCPU / 1 GB y hoy **construye la imagen en la misma máquina que atiende a los gestores** (`docker-compose.yml`, `deploy/auto_update.sh:60-70`) |

**Conversión de semanas-persona a calendario:** se cuentan **45 semanas efectivas por año** (descontando vacaciones, festivos y el soporte de la operación diaria, que no se detiene). Con un solo desarrollador, una semana-persona es una semana de calendario efectivo.

#### Qué pasa si entra un segundo desarrollador

La reducción no se estima con un porcentaje: se deriva de los propios paquetes, porque la regla de trabajo de §10.8 prohíbe que dos sesiones toquen el mismo archivo central (`glosa_service.py`, `index.html`, `db.py`) en la misma semana. Se reparte por subsistema y el calendario lo marca la rama más larga:

| Versión | Esfuerzo (semanas-persona) | Calendario con 1 desarrollador | Calendario con 2 | Qué se paraleliza |
|---|---|---|---|---|
| **2.0** | **29,5** | 29,5 sem (~8 meses) | 24,5 sem (~6,5 meses) | Casi nada: A0–A3, A5, A6, B1–B7, C1 y C2 tocan los mismos tres archivos centrales. Solo A4, A7, C3, C4, C5 y C6 (5 semanas) son separables |
| **2.1** | **22,5** | 22,5 sem (~6 meses) | 13,5 sem (~3,5 meses) | Núcleo/datos (E1, E2, E3 = 13) contra interfaz y herramientas (E4, E5, E6, E7 = 9,5) |
| **2.2** | **31,5** | 31,5 sem (~8,5 meses) | 19,5 sem (~5,5 meses) | Bots y adaptadores (R1, R2, R4, R8 = 19) contra aplicación (R3, R5, R6, R7, R9 = 12,5) |
| **3.0** | **13,5** | 13,5 sem (~3,5 meses) | 7,5 sem (~2 meses) | Aprendizaje y predicción (L1, L2, L4 = 7) contra plugins y validadores (L3, L5, L6 = 6,5) |
| **Total** | **97** | **~26 meses** | **~17 meses** | |

El segundo desarrollador **no reduce el costo, reduce el calendario**: las 97 semanas-persona se pagan igual (ver §10.11). Y la 2.0 se paraleliza mal a propósito: es la versión donde todo converge sobre los mismos archivos, y partirla en dos manos es exactamente cómo nacieron los pares `multi_agent.py` / `multi_agente.py`.

### 10.2 De las 7 fases del blueprint a 4 versiones entregables

| Fase del blueprint (§19) | Versión que la entrega | Por qué ahí |
|---|---|---|
| **1 · Refactorización del núcleo** | **2.0** (completa) | Es el prerrequisito físico de todo lo demás: no se puede poner un Orquestador encima de tres máquinas de estados, cuatro catálogos de normas y **142 duplicaciones** estructurales |
| **2 · IA Central y Orquestador** | **2.0** (el pipeline único) + **2.1** (la memoria y el copiloto) | El "pipeline único de respuesta" es refactorización, no IA nueva: hoy hay 4 caminos distintos para generar el mismo dictamen |
| **3 · Expedientes inteligentes** | **2.1** | Depende de que exista una sola tabla de conceptos y trazabilidad real (2.0) |
| **4 · Automatización (radicación, evidencias)** | **2.2** | Depende del perfil de pagador único (2.0) y del expediente (2.1) |
| **5 · Conciliación inteligente** | **2.2** | Depende de que el acta cierre la glosa y alimente la cartera, que hoy no ocurre (`app/api/routers/conciliacion.py:290-324`) |
| **6 · Ecosistema de agentes / plugins** | **2.2** (bots unificados + adaptador DGH) + **3.0** (plugins) | Consolidar **cuatro bots** (COOSALUD, SIMED-glosas, SIMED-soportes, DGH) cuesta una fracción de lo que costará con **nueve**: SAVIA, EMSSANAR, VCO, MUTUAL SER y FOMAG ya están nombrados por el cliente y todavía no existen |
| **7 · Optimización continua / aprendizaje** | **3.0** | Hoy el circuito de aprendizaje **no gira**: las 52 plantillas Gold de la base son todas semilla, 0 aprendidas, todas con `usos=0` (verificado en `glosas.db`) |

---

### 10.3 Versión 2.0 — "Cimientos invisibles y tres victorias que se ven el primer día"

> **Objetivo en una frase:** que el sistema sea legalmente defendible, que un cambio de contrato o de norma no requiera un programador, que ninguna glosa se venza sin que nadie se entere, y que responder una glosa cueste la mitad de clics que hoy.

**Esfuerzo: 29,5 semanas-persona** (≈ 8 meses con un desarrollador; 6,5 con dos). Prioridad global: **P0**.

#### Bloque A — Lo que no se ve, pero desbloquea todo (14 semanas)

| Paquete | Qué incluye | Cambio técnico | Prio. | Impacto en el trabajo real | Sem. |
|---|---|---|---|---|---|
| **A0 · Barrido de lo que falla a la vista, y resucitar "Preparar el día"** | **Primero: reconstruir `POST /autopilot/preparar-dia`**, la ruta que el botón `static/index.html:7112` sigue llamando y cuyo router fue eliminado (`app/main.py:1207`: "autopilot: removido en la limpieza de ronda 29"). Hoy devuelve **404** y un toast rojo: la automatización de mayor retorno del producto no funciona y nadie lo notó porque estaba escondida. Después: quitar del menú "Salud Total" (`2091`, backend borrado en `main.py:1177`) y el botón flotante de nota privada (`5993`, router borrado en `main.py:1214`); arreglar el enlace "Ver glosa" del aviso de factura duplicada (`9591`, llama a `abrirGlosa()` que no existe); quitar el segundo manejador de la tecla `/` que deja un overlay imposible de cerrar (`7178` vs `10869`); dejar un solo Ctrl+K de tres | La lógica de texto fijo para RATIFICADAS y EXTEMPORÁNEAS sigue viva en `texto_fijo_detector`: el endpoint se reconstruye sobre ella, idempotente, con reporte en español. Más un barrido del frontend contra las 686 rutas reales y un test de contrato "cada botón resuelve a una ruta registrada" | P0 | Devuelve la acción que cierra sola la mitad de la cola del día, y elimina 5 fallos que el auditor encuentra en su primera hora de uso | **1,5** |
| **A1 · Borrar lo muerto** | 62 de 127 endpoints de `glosas.py` sin un botón en la UI; 167 de 171 endpoints de `glosas_stats.py` (11.341 líneas); 72 de 77 de `admin.py` (5.344 líneas); routers `asignacion.py`, `bandeja.py`, `alertas.py`, `plantillas.py`, `pdf.py`, `adjuntos.py`, `dictamen_pdf.py`, `auditoria_forense.py`; `tenancy.py`, `bot_mensajeria.py`, `multi_agent.py`, `rag_normativa.py`, `normativa_grafo.py`, `salud_total_service.py`, `texto_fijo_batch.py`; las **8 tablas sin un solo importador (8 de 37, el 22 % del esquema)**; los dos motores de glosa fuera de la API (`tools/motor_glosas_hus.py`, `tools/asistente_conciliacion_dispensario.py`) | Borrado con barrido previo de referencias en `app/`, `tools/`, `scripts/`, `static/` y `tests/` | P0 | **~34.000 líneas menos de servidor y herramientas** (las ~4.700 de frontend las quita el bloque B; el total de ~39.000 está desglosado en §5.7). No es estética: es donde viven los bugs replicados — la constante de "glosa cerrada" está copiada 117 veces y por eso dos pantallas dan cifras distintas | 2 |
| **A2 · Perfil de Pagador y contratos a la base de datos** *(= N4)* | Una sola ficha de pagador (identidad + NIT + alias + contrato + factor tarifario + vigencia por **fecha de atención** + régimen + plazos + canal de radicación + formato de factura + mapeo de columnas + estilo), editable desde la pantalla, con historial de otrosíes | Migrar `CONTRATOS_HUS` (`glosa_ia_prompts.py:59-299`), `CONTRATOS_DEFAULT` (`main.py:82-96`), `perfil_eps.py` y las **12 entidades** de `data/perfiles_radicacion.json` a tabla; `get_contrato()` lee de BD; agregar el formulario de creación que hoy **no existe** (`POST /contratos/upsert` tiene 0 llamadas en la UI); doble lectura de verificación durante 2 semanas | P0 | Hoy renovar un contrato exige un despliegue, y editar por pantalla el contrato de las 14 EPS principales **es placebo**: el diccionario de Python le gana a la base (`get_contrato`, línea 383). Es un dictamen citando un contrato vencido, firmado por el hospital | **4** |
| **A3 · Trazabilidad del dictamen** | Versionar el dictamen **siempre** (hoy 3 de 19 puntos de escritura); un solo nombre de entidad en el registro de auditoría (hoy la misma tabla se audita como `historial` en 19 sitios y como `glosas` en 11, y solo 1 de 12 lectores contempla ambos); borrado lógico real (hoy `db.delete()` físico + CASCADE destruye conceptos, versiones, comentarios y conciliaciones, y la papelera solo fotocopia la cabecera) | Columna `eliminado_en` + filtro global; índice `audit_log(tabla, registro_id)`; IP obligatoria en las 68 llamadas a `registrar()` | P0 | Hoy un proceso automático puede sobrescribir el documento legal que el hospital le opone a la EPS sin dejar rastro (`ia_auditora_proactiva.py:183`, `auto_responder_service.py:227,301,341,460`). Ante SuperSalud, ese expediente **no es defendible** | 1,5 |
| **A4 · Cifrado de los datos del paciente** | Cifrar en reposo `paciente`, `texto_glosa_original`, `dictamen` y `observacion_eps` con la política estricta que **ya funciona** en el vault de credenciales (Fernet obligatorio, falla cerrado, log de acceso con motivo) | Borrar `cifrado.py` (0 importadores reales, verificado) y replicar `credenciales_vault.py`; corregir el indicador `"cifrado_fernet": true` de `sistema.py:147` | P0 | Hoy el sistema **declara que cifra y no cifra un solo byte**. Ante Ley 1581/2012 una afirmación falsa en un reporte de cumplimiento es peor que no tener el control | 1,5 |
| **A5 · Un solo vocabulario de estados y una sola máquina** | Catálogo de estados con transiciones válidas y dos ejes explícitos (interno del dictamen / frente a la EPS); eliminar el bypass `PATCH /glosas/{id}/estado` que acepta 11 estados sin validar nada (`glosas.py:2580`) y el bypass de autorización de `POST /workflow/{id}/transicionar` (no verifica rol ni propiedad) | Enum en el modelo + `es_terminal()`; borrar las 117 declaraciones locales | P0 | Hoy una glosa RATIFICADA cuenta como cerrada en 13 pantallas y como abierta en las otras 117. Ningún tablero es firmable mientras eso siga así, y el reloj de vencimientos (C1) heredaría la contradicción | 1 |
| **A6 · Un solo motor de respuesta** | `ResponderGlosa.ejecutar()` con todas las capas en orden declarado (pre-validación → texto fijo/plantilla/dictamen directo a $0 → enriquecimiento → routing único → generación con caché → verificación de citas → sanitización registrada → persistencia por concepto → un solo score) | Los 4 caminos actuales (unitario, importación masiva, auto-responder, generar-lote) pasan a ser adaptadores de entrada; migrar las 32 "redes finales" **una a una, cada una con su test** | P0 | Hoy la misma glosa produce un dictamen de calidad distinta según por qué puerta entró, y solo uno de los cuatro caminos tiene las defensas anti-gasto nacidas del incidente de $14,50 en 251 llamadas | 2,5 |
| **A7 · Migraciones y arranque** | Alembic como única vía; sacar las ~500 líneas de `ALTER TABLE` del arranque (`main.py:144-650`), donde un fallo se degrada a `logger.warning` y la aplicación arranca con un esquema distinto al que el código espera | `alembic upgrade head` como paso del despliegue | P1 | `main.py` baja de 1.322 a ~400 líneas y desaparece la clase de fallo "funcionaba ayer y hoy no, sin causa visible" | 0,5 |

#### Bloque B — Las victorias visibles (8 semanas, en paralelo al cierre del bloque A)

| Paquete | Qué incluye | Prio. | Impacto medible | Sem. |
|---|---|---|---|---|
| **B1 · Dar vuelta la pantalla de entrada** | La aplicación abre en la **bandeja de trabajo**, no en un formulario en blanco de 13 campos. Arriba: el aviso de vencimientos a 24 h con valor en riesgo (`static/index.html:13548`) y el botón "Preparar el día", **ya reparado en A0**, que hoy vive enterrado en el estado vacío del panel Analizar (`7108`) y desaparece para siempre en cuanto se analiza la primera glosa | P0 | El camino barato (bandeja → seleccionar todas → generar en lote) resuelve hasta 100 glosas en **5 clics** y está a dos niveles de profundidad; el camino caro (12–14 clics por glosa) es el que abre por defecto | 1 |
| **B2 · Subir el número de factura y borrar la palabra "opcional"** | Ese campo vive hoy dentro de un acordeón cerrado rotulado "Facturación · opcional" (`2160-2164`). Un solo dato desbloquea tres automatizaciones **ya construidas**: los N conceptos objetados desde la base (`9461`), el aviso de factura duplicada (`9578`) y la lectura automática de historia clínica, RIPS y factura electrónica desde el disco de red (`analizar.py:805-824`) | P0 | Elimina la mayor parte del trabajo manual de buscar y adjuntar soportes. Son ~20 líneas de HTML | 0,5 |
| **B3 · Que lo detectado se escriba, no solo se muestre** | `POST /analizar/preview` ya extrae código de glosa, valor objetado, valor facturado, EPS, CUPS y servicio sin gastar un token (`analizar.py:1032-1046`) y el frontend los pinta y los tira (`21875-21891`) | P0 | De los 6 campos que el auditor teclea a mano en el camino feliz, al menos 4 los tiene el sistema. Información capturada, mostrada y tirada a la basura | 1 |
| **B4 · Matar los 44 `prompt()` y los 12 `alert()`** | El módulo de conciliación entero —donde se negocian millones— se opera con cuadros del navegador: `panelCerrarActa` encadena **cinco** y pierde todo si el último trae un espacio en vez de un guion bajo (`20480-20498`). La decisión de la EPS, dato del que dependen todas las estadísticas de recuperación, se escribe a mano (`20390`) | P0 | Trabajo mecánico, riesgo bajo, y protege el dato más importante del negocio | 1,5 |
| **B5 · Un solo documento radicable** | Borrar los tres generadores de PDF del navegador y dejar el del servidor, con consecutivo persistido en base de datos | P0 | Hoy el documento que se radica ante la EPS lleva un "Nº OBJECIÓN" generado con `Math.random()` (`18095`, impreso en `18192`) y firma "Elaboró X · Confirmó X" con la misma persona (`18186-18187`). Es un identificador fabricado en un documento oficial | 1 |
| **B6 · Un solo semáforo de calidad** | `confidence_scorer` como métrica única y explicable; el autopiloto y el badge se derivan de ella por umbrales | P1 | Hoy el auditor ve hasta 6 indicadores simultáneos y el más grande y prominente (`_calcular_score`) es una heurística estática por tipo de glosa —el único que **no mide calidad** | 1 |
| **B7 · De 26 pantallas a 14 y de 5 botones de exportar a 1** | Fusionar Mando + Dashboard + Cobranza Live + Resumen del mes; absorber "Alertas" (2 líneas de markup, 0 botones) dentro de Mis Glosas; partir "Usuarios" en Mi cuenta / Administración; mover el liquidador SOAT a Tarifas. Esas 14 pantallas son las que agrupan los **9 módulos de navegación de §3.5**: 9 módulos, 14 pantallas, no son dos promesas distintas | P1 | El propio código documenta que el usuario ya pidió esta consolidación y que la respuesta fue **agregar una quinta superficie** en vez de quitar tres pantallas (`static/index.html:12386-12390`) | 2 |

#### Bloque C — Lo que faltaba y no puede esperar a la 2.1 (7 semanas)

| Paquete | Qué incluye | Prio. | Por qué va en la 2.0 y no después | Sem. |
|---|---|---|---|---|
| **C1 · Reloj de vencimientos del sistema, con escalamiento automático** *(= N1)* | El vencimiento se calcula desde el **perfil del pagador** (A2) y la fecha de notificación, no desde una celda del Excel de recepción; una objeción que entra en rojo escala sola **al coordinador**, no al gestor; una sola bandeja de vencimientos que muestra **primero lo ya vencido** (hoy el repositorio filtra `dias_restantes > 0`, así que lo más urgente desaparece de la pantalla que existe para eso) | **P0** | Es la propuesta de mayor retorno de §6 (7/7 en la regla suprema, "plata directa") y estaba fuera del roadmap. Hoy el vencimiento **viene escrito en una celda**: si falta, la fila se descarta y la glosa nunca existe. Existe un estado NEGRO para lo vencido y **no dispara nada**. Ese hueco es el que dejó 3 facturas de junio (38 objeciones, **$20.054.751**) con los plazos del 6 y el 8 de julio vencidos, descubiertas el 22 de julio | 2 |
| **C2 · Un solo número: `MetricasService` + informe mensual firmable** *(= N8, primera mitad)* | Un servicio único que define DECIDIDA, LEVANTADA, RECUPERADO y CARTERA, **con la definición escrita en la propia pantalla**; un informe mensual con tres salidas (pantalla, PDF, Excel) que reemplaza los cuatro actuales. **Decisión tomada:** el sistema mide con la **columna registrada** (`valor_recuperado`), no con la derivada objetado−aceptado, porque es la única cifra que un auditor puede defender ante un Comité de Cartera; la derivada queda como control de consistencia, no como número publicado | **P0** | "Valor recuperado" tiene **cinco fórmulas**, cuatro de ellas visibles a un clic de distancia en la misma barra de pestañas. Sin esto, ninguna meta de §10.9 es medible y ninguna versión posterior se puede evaluar | 2 |
| **C3 · Un solo cliente de IA que registre siempre** | Todas las llamadas a Anthropic, Groq y Gemini pasan por un cliente único que escribe modelo, tokens, costo, camino de entrada e **identificador de glosa** | **P0** | Hoy 11 de 12 puntos que llaman a Anthropic no registran gasto y Groq/Gemini no registran nunca: hay 24 filas en `ai_calls` y **ninguna** con identificador de glosa. Es prerrequisito del copiloto (E4) y la única forma de que el presupuesto de §10.11 deje de ser una estimación | 1 |
| **C4 · Respaldos fuera de la VM** | Copia diaria cifrada a almacenamiento externo al servidor, con **prueba de restauración mensual** documentada y retención de 30 días | **P0** | Hoy `backup_sqlite.py:54` escribe los respaldos en `dirname(ruta)/backups`, es decir, dentro del mismo volumen que `docker-compose.yml:51` monta como `./data:/data`. **Si se pierde el disco o la VM, se pierden la base y todos sus respaldos juntos.** Para una ESE pública esto es más grave que varias cosas que sí estaban priorizadas, y cuesta media semana | 0,5 |
| **C5 · Cerrar las dos fugas de datos de paciente** | (a) El service worker deja de cachear respuestas de usuario: `/usuarios/yo` y `/notificaciones/badge` están a la vez en la lista cacheable (`sw.js:14,20`) y en la de exclusión (`:110`), y como el bloque cacheable se evalúa primero (`:89`) gana el cacheo — sin `Vary: Authorization`, en un PC compartido de cartera el segundo gestor ve nombre, correo, rol y contadores del primero. (b) `GET /glosas/historial` (`glosas.py:188-236`) devuelve el **nombre del paciente de todas las glosas del hospital** a cualquier usuario autenticado, sin filtro por rol ni por asignación, mientras `glosas.py:1633` sí filtra ("Auditor solo ve las suyas") | **P0** | El plan trataba el dato de paciente solo como cifrado en reposo (A4). Cifrar la columna no sirve de nada si la API la entrega completa y el navegador la guarda en un equipo compartido. Son dos arreglos concretos, con archivo y línea | 1 |
| **C6 · Puesta en marcha y capacitación de la 2.0** | Ver §10.10 | P0 | Una versión no está entregada hasta que dos gestores distintos completan el flujo nuevo sin ayuda | 0,5 |

#### Por qué este orden y no el contrario

1. **Porque lo invisible es lo que cuesta plata cuando falla.** Una pantalla fea hace perder minutos; un dictamen sobrescrito sin rastro, un contrato citado desde un diccionario de Python vencido, un reporte de cumplimiento que dice que se cifra el nombre del paciente cuando está en texto plano, o un respaldo que se pierde con la misma VM que la base, hacen perder **glosas, datos y credibilidad jurídica**. Y el daño aparece meses después, cuando ya no se puede reconstruir.
2. **Porque construir encima de lo duplicado multiplica el costo.** Poner el Orquestador (fase 2 del blueprint) sobre tres máquinas de estados, cuatro catálogos de normas y cinco fórmulas de "valor recuperado" significa que el Orquestador tendrá que aprender las cinco. Cada semana que se posterga, la deuda se cobra intereses: hoy son **cuatro bots** contra dos portales; con los cinco pagadores que el cliente ya nombró serían **nueve**.
3. **Porque borrar es la actividad de mayor retorno y menor riesgo del proyecto.** Los cuatro movimientos de mayor impacto del frontend son **todos de borrado, ninguno de construcción**. Nada de eso se puede romper, porque nada de eso se usa.
4. **Porque las victorias visibles compran el permiso para seguir.** A0, B1, B2 y B3 se notan el primer día y no dependen del resto del bloque A: se pueden entregar en la semana 8 mientras el bloque A sigue en curso. Un proyecto de cimientos que tarda ocho meses en mostrar algo pierde el apoyo del área.

---

### 10.4 Versión 2.1 — "El expediente único y el copiloto que sabe dónde está todo"

> **Objetivo en una frase:** que cada factura tenga un expediente completo y defendible, que el auditor deje de buscar papeles, y que una devolución deje de ser un agujero.

**Esfuerzo: 22,5 semanas-persona** (≈ 6 meses con un desarrollador; 3,5 con dos). Prioridad: **P1**. Cubre las fases 2 (memoria y copiloto) y 3 (expedientes) del blueprint.

| Paquete | Qué incluye | Cambio técnico | Impacto | Sem. |
|---|---|---|---|---|
| **E1 · Expediente único de la factura** *(= N9)* | Una entidad Factura de primera clase (número, valor, saldo, radicación, estado de cobro) con las objeciones colgando de ella y su línea de tiempo: recibida → asignada → respondida → radicada → ratificada → conciliada → nota crédito → pagada | `conceptos_glosa` pasa a ser el centro del esquema; se borran las 9 columnas duplicadas de `historial` y la rama de "fallback legacy" del endpoint por factura (`glosas.py:2156` vs `2192`) | Hoy nadie puede responder "¿esta objeción se radicó, cuándo, con qué evidencia y cómo terminó?" sin abrir tres carpetas y un chat | 7 |
| **E2 · Expediente leído de verdad: fin del truncado, matriz de evidencia y visor de soportes** *(= N2)* | Lectura completa del PDF con troceo y selección **por relevancia**, con un único presupuesto de tokens configurable; matriz de evidencia (por cada soporte que la familia de glosa exige: si está, en qué archivo y en qué página); `GET /soportes/{id}/archivo` con visor en línea, validación de ruta y auditoría de acceso a PHI | Hoy `pdf_service._procesar_pdf_sync:77-91` devuelve como máximo ~7.050 caracteres de cualquier PDF de más de 4 páginas y el camino auto-descubierto limita a 3 archivos × 5.000 caracteres (`analizar.py:48-49`); y **no existe un solo `FileResponse`** en `app/api/routers/soportes.py` | Una historia clínica de 200 páginas llega a la IA como 7 KB, con el medio literalmente reemplazado por `...[PÁGINAS INTERMEDIAS OMITIDAS]...`, mientras el banner dice "✓ 12 soportes detectados". Y el sistema indexa hasta 144.000 archivos para terminar mostrando la ruta absoluta como texto para copiar y pegar en el explorador de Windows (`21606`) | 4 |
| **E3 · Un solo corpus normativo y una sola biblioteca** | Corpus con texto literal en datos versionados, editable por el auditor, con vigencias; `citation_verifier` como único validador | Hoy hay **dos corpus de 131 normas con solo 20 nombres en común**: uno alimenta lo que la IA cita, otro lo que el gestor lee. Y los plazos del Art. 57 tienen 5 versiones distintas en el repositorio, incluida la documentación de capacitación | El auditor puede encontrar hoy en la biblioteca una norma que el validador marcará como inexistente en el dictamen | 2 |
| **E4 · Copiloto contextual único (blueprint §15)** *(= N11)* | Un solo asistente, construido sobre el Asistente Maestro (la única IA conversacional real, con 9 herramientas que consultan datos verdaderos), con contexto de la pantalla activa | Se elimina el "chat de glosa", que promete conversación y tiene 8 respuestas fijas por palabra clave y **cero llamadas a IA** (`chat_glosa.py:56-138`). Requisito previo ya entregado en C3 | Un copiloto que responde "la cláusula 18 respalda esta respuesta" con la cláusula real y su página, en vez de tres asistentes que no responden | 5 |
| **E5 · Panel del vault de credenciales** *(= N5)* | Terminar la única joya sin entregar: el backend está completo, cifrado y auditado, y no tiene interfaz. Listar, buscar y revelar con motivo registrado | Pantalla sobre `credenciales_vault.py`, sin tocar el backend | El equipo sigue compartiendo en un Excel fuera del sistema las claves de los portales — hoy **12 entidades** registradas en `data/perfiles_radicacion.json`, y crecerán a nueve pagadores con bot | 1,5 |
| **E6 · Devoluciones: el subproceso que no existe** | La devolución deja de ser una columna guardada y sin dueño: bandeja propia, causal, responsable de la corrección, **re-radicación de la factura** con nuevo consecutivo, y reloj propio (el plazo de una devolución no es el de una glosa) | El Excel de recepción ya trae `DEVOLUCION S/N` y se guarda (`db.py:65`, columna `es_devolucion`); existe `/stats/devoluciones-resumen` (`glosas_stats.py:4753`) **sin un solo llamador** en `static/` ni en `tools/`; y no hay pantalla en ninguna parte | Es un **flujo de negocio completo ausente del sistema**. Una devolución no es una glosa: obliga a corregir y volver a radicar la factura entera, y hoy eso se hace fuera, sin reloj y sin rastro. Va en la 2.1 porque necesita la entidad Factura de E1 | 2,5 |
| **E7 · Puesta en marcha y capacitación 2.1** | Ver §10.10 | | | 0,5 |

---

### 10.5 Versión 2.2 — "Del dictamen al portal, del portal al DGH y del acta a la cartera, sin Excel intermedio"

> **Objetivo en una frase:** cerrar el círculo completo — que el sistema capture, radique, registre la evidencia, alimente la contabilidad, concilie y sepa cuánta plata entró.

**Esfuerzo: 31,5 semanas-persona** (≈ 8,5 meses con un desarrollador; 5,5 con dos). Prioridad: **P1**. Cubre las fases 4, 5 y la primera mitad de la 6.

| Paquete | Qué incluye | Impacto | Sem. |
|---|---|---|---|
| **R1 · Unificar los bots sin tocar su conocimiento de portal** | Un núcleo compartido (sesión, credenciales, reporte, evidencia, índice) + un perfil declarativo por pagador + un adaptador de portal por sitio. Fusionar los dos bots del portal SIMED en uno con dos acciones (el propio código admite que son el mismo portal y las mismas credenciales: `responder_glosas_simed.py:423`) | ~800 líneas menos y, sobre todo, **una sola política de reintentos que auditar**. Hoy `setup_logging` está copiada idéntica 3 veces, `cargar_credenciales` 4 veces con 85 % de similitud, y el índice de facturas se parsea con dos expresiones regulares distintas que hay que arreglar por separado | 4 |
| **R2 · Centro de Automatización: un solo Agente HUS y un tablero de bots** *(= N7)* | Lanzar, ver, detener y auditar un bot desde la aplicación, con el perfil del pagador resolviendo qué bot corre. Un solo agente instalado una vez, con una sola credencial, que sincroniza el share **y** ejecuta bots | La cola de lotes existe con 6 endpoints, 3 tablas, un agente de escritorio y 403 líneas de tests — y **cero pantalla**: `grep "fetch('/lotes"` en el frontend devuelve 0. El frontend no sabe que los bots existen (0 ocurrencias de "RPA", "Robot" o "Playwright" en **23.125 líneas**). Hoy la interfaz real de los bots es PowerShell con rutas de 120 caracteres, para un auditor de cartera | 5 |
| **R3 · Puente Orquestador: el resultado del portal vuelve al expediente** *(= N3)* | El bot le pide la respuesta al motor por API en vez de recibir un Excel, y al terminar escribe el estado, sube el pantallazo del cartel de cierre y marca la objeción como radicada. Los estados dejan de ser jerga (`TERMINADA_SIN_CARTEL`, `PENDIENTE_PDX`, `NO_EN_BOLSA`) y pasan a ser frases de auditor | Ningún bot clasifica, analiza ni guarda historial: **no hay una sola llamada HTTP que no sea al portal**. Para SIMED —el flujo con más volumen real— el resultado vive hoy en un CSV en el escritorio de una PC, y el registro manual ya demostró estar equivocado en **6 de 12 facturas** | 5 |
| **R4 · Adaptador DGH de dos direcciones** | Un único adaptador dentro del sistema con las dos direcciones —**leer** las objeciones que el DGH registra y **escribir** las respuestas y notas crédito— con un test de contrato por cada dirección y el mapeo de columnas viviendo en el perfil del pagador (A2), no en un script | **El plan borraba el bot DGH sin poner nada en su lugar, y el DGH es el único sitio donde la glosa existe contablemente.** Hoy la etapa E3 se alimenta con Excel a mano en ambos sentidos y el bot que la atacaría (`tools/responder_glosas_dgh.py`) sigue en piloto, operando por coordenadas de pantalla y pendiente de `--calibrar` desde el 30 de junio. **Decisión: el bot de escritorio no se borra en la 2.0 — se congela**, y solo se retira cuando este adaptador esté en producción. El adaptador es además la especificación de la integración directa que lo hará innecesario | 4 |
| **R5 · Radicación automática y evidencia (blueprint §12)** | Consecutivo institucional desde el sistema (hoy se pide por chat, lote por lote), carpetas parametrizables, evidencia consolidada automática al cerrar el lote | Convierte un trámite de chat en un contador | 2 |
| **R6 · Conciliación que cierra el ciclo (blueprint §13)** *(= N6)* | El acta del sistema es la que se firma, con los campos reales del TSV que hoy se usa (radicado, acta, valor factura, total glosas, valor aceptado) y los participantes como personas con nombre y cargo, no como texto libre; cerrar el acta transiciona la glosa y suma a la plata recuperada **en una sola acción** | Hoy `cerrar-acta` no transiciona la glosa ni escribe el valor recuperado: el auditor registra el resultado dos veces. Y la tabla `conciliaciones` tiene 0 filas mientras la conciliación real (226 facturas, 4 actas, $277.231.324 glosados) vive en un TSV | 4 |
| **R7 · La cartera se calcula por factura, no por glosa** *(= N8, segunda mitad)* | Traer adentro el modelo de `tools/tablero_cartera.py`, que razona correctamente por factura (saldo, mora, % recaudo), ahora que la entidad Factura existe (E1) | Hoy dos endpoints suman el saldo **una vez por glosa**: una factura con 5 glosas abiertas reporta 5 veces su saldo. El bug se detectó y se arregló solo en el endpoint que la interfaz usaba | 1 |
| **R8 · Captura automática de la glosa en el portal** *(= N12)* | Agente de captura por pagador: login, descarga del lote, registro con sello de fecha — que es justo lo que arranca el reloj de C1 | Es el hueco más caro del proceso: si nadie baja el lote, el plazo corre igual. Las 3 facturas de junio (38 objeciones, **$20.054.751**) quedaron en riesgo **aquí**, no en la redacción: sus plazos vencieron el 6 y el 8 de julio y el hallazgo llegó el 22 | 6 |
| **R9 · Puesta en marcha y capacitación 2.2** | Ver §10.10 | | 0,5 |

**Nota sobre los bots y el volumen real.** En julio los bots procesaron **324 facturas y 597 objeciones en siete lotes**; de los tres últimos, por **$153.675.820**, el Excel está listo y la subida sin confirmar (BITACORA.md:173-181). Ese es exactamente el problema que R3 cierra: hoy nadie puede saber desde el sistema si un lote se radicó o no.

---

### 10.6 Versión 3.0 — "El sistema operativo que aprende"

> **Objetivo en una frase:** que cada glosa ganada o perdida mejore la siguiente, sin que nadie lo programe.

**Esfuerzo: 13,5 semanas-persona** (≈ 3,5 meses con un desarrollador; 2 con dos). Prioridad: **P2**. Cubre las fases 6 (plugins) y 7 (optimización continua).

| Paquete | Qué incluye | Por qué es 3.0 y no antes | Sem. |
|---|---|---|---|
| **L1 · Reparar el circuito de aprendizaje** | Un solo selector de ejemplos con la prioridad invertida: precedente propio ganado → plantilla Gold aprendida → banco del HUS. Quitar el cortocircuito que retorna en el paso 1 (`few_shot_gold.py:116-117`) y el filtro `usos>=3` (`:131`); normalizar la EPS al guardar la Gold; propagar el resultado de la conciliación a la decisión de la EPS | Requiere que primero exista **un solo** pipeline (2.0) y que la conciliación cierre la glosa (2.2). Hoy el lazo nunca giró: 52 plantillas Gold, las 52 de semilla, 0 aprendidas, todas con `usos=0` | 3 |
| **L2 · Un solo predictor, validado** *(= N10)* | Fusionar los tres predictores en uno que se alimente del histórico del propio hospital, y publicar el acierto (predicho vs. decisión real de la EPS) | El único predictor que el usuario ve hoy **no consulta la base ni una vez**: sus números son constantes "según histórico nacional" y una lista de 5 EPS difíciles que no son las del HUS. Sin histórico limpio (2.0–2.2) no hay contra qué calibrar | 3 |
| **L3 · Centro de Automatización abierto y plugins (§10, §17)** | Nuevos agentes sin modificar el núcleo; el catálogo de bots deja de ser un diccionario en código y se resuelve por el perfil del pagador | Solo tiene sentido cuando el perfil de pagador es único (2.0) y el núcleo de bots está extraído (2.2). Es el paquete que hace que SAVIA, EMSSANAR, VCO, MUTUAL SER y FOMAG cuesten un perfil y no un bot | 3 |
| **L4 · Costo por glosa publicado y optimizado** | El dato ya se registra desde C3: aquí se publica por glosa, por pagador y por camino de generación, y se optimiza el routing con evidencia | En 2.0 se construye el medidor; en 3.0 se usa para decidir. Antes de C3, "costo por glosa" **no existía** como dato | 1 |
| **L5 · Herramientas (§11) y validadores** | Manual SOAT completo cargado como datos (hoy hay 4 códigos de ejemplo), validadores RIPS/CUPS/CIE10/PBS | Es valor real pero no bloquea nada; entra cuando el motor ya es estable | 3 |
| **L6 · Puesta en marcha y capacitación 3.0** | Ver §10.10 | | 0,5 |

### 10.7 Lo que NO se hace

Las ocho candidatas descartadas —predicción pre-radicación, notificaciones push, WhatsApp/Telegram, pipeline multi-agente, búsqueda semántica con re-ranking, grafo normativo, multi-tenant/SaaS y firma digital con validez jurídica— **están decididas y justificadas una por una en §6.3**; no se repiten aquí. La decisión de no rehacer el frontend con React y hacerlo con componentes web nativos está en §11.11.

Queda una sola decisión que no vive en otra sección: **el informe de baja de cartera (Res. 577/2019) se queda como herramienta de escritorio y no se porta a la web**, porque su insumo son carpetas y PDFs del share interno y portarlo obligaría a subir gigabytes a una VM de 1 vCPU para un informe que se genera una vez al año.

### 10.8 Riesgos del proyecto y cómo se mitigan

| Riesgo | Por qué es real aquí | Mitigación concreta | Señal temprana de que se está materializando |
|---|---|---|---|
| **El sistema está en producción y el hospital depende de él todos los días** | Julio fue el mes más productivo del área: los bots procesaron 324 facturas y 597 objeciones en siete lotes, y el del 9 de julio (102 facturas, 225 objeciones) se subió y verificó al 100 % en ~22 minutos (BITACORA.md) | Regla dura: **la operación diaria nunca depende de la rama de desarrollo**. Los bots no se tocan por dentro hasta 2.2; hasta entonces solo se les agrega tablero. Despliegue semanal fuera de horario de radicación, con la imagen construida **fuera** de la VM del hospital (hoy se construye en la misma máquina de 1 vCPU que atiende a los gestores) | Un lote se cae o tarda el doble después de un despliegue |
| **Los respaldos se pierden junto con la base** | `backup_sqlite.py:54` escribe en `dirname(ruta)/backups` y `docker-compose.yml:51` monta `./data:/data`: base y respaldos comparten disco y VM. No es hipotético: es el estado actual de una ESE pública con datos de paciente | Paquete **C4**, semana 1 de la 2.0: copia diaria cifrada fuera del servidor, retención de 30 días y **prueba de restauración mensual documentada**. Un respaldo que no se ha restaurado nunca no es un respaldo | El listado de respaldos y el archivo `.db` siguen apareciendo bajo la misma ruta después de la semana 2 |
| **Borrar el bot DGH sin reemplazo deja la contabilidad sin puente** | El DGH es el único lugar donde la glosa existe contablemente y hoy se alimenta a mano en las dos direcciones. El plan lo mandaba a borrar en la fase de limpieza | El bot de escritorio **se congela, no se borra**, en la 2.0. Su retiro es la última tarea de la 2.2, y solo después de que el adaptador **R4** pase sus dos tests de contrato en producción | Alguien propone borrar `responder_glosas_dgh.py` antes de que R4 esté desplegado |
| **Datos de paciente expuestos antes de que llegue el cifrado** | `GET /glosas/historial` devuelve el nombre del paciente de todas las glosas a cualquier usuario autenticado (`glosas.py:188-236`), y el service worker cachea `/usuarios/yo` sin `Vary: Authorization` en PCs compartidos (`sw.js:14,20` vs `:110`) | Paquete **C5**, en las primeras cuatro semanas: filtro por rol y asignación en todo listado con datos de paciente, y exclusión real de las rutas de usuario en el cache del navegador. Cifrar (A4) sin esto es cerrar la puerta y dejar la ventana abierta | Un endpoint nuevo devuelve `paciente` sin pasar por la dependencia de autorización |
| **Borrar algo que sí se usa** | Ya pasó: `exportar.py` documenta que el router se perdió en una limpieza anterior y el botón devolvía 404 con un servicio de 580 líneas huérfano. Y "Preparar el día" lleva desde la ronda 29 devolviendo 404 sin que nadie lo notara | Ningún borrado sin barrido previo de referencias en `app/`, `tools/`, `scripts/`, `static/` y `tests/`. **Test de contrato obligatorio: cada botón del frontend resuelve a una ruta registrada.** Borrado en dos tiempos: se deshabilita una semana, se borra a la siguiente | Un 404 en el log que antes no estaba |
| **Las pruebas son la red de seguridad… y a veces dan falsa seguridad** | Verificado: **626 archivos `.py` en `tests/`** (616 empiezan por `test_`) y una suite que ejecuta **4.266 pruebas** (corrida real del 23 de julio). Pero `test_notificaciones_contadores` comprueba `isinstance(d['por_tipo'], dict)` sobre un diccionario que **siempre está vacío**, y `test_healthcheck_profundo` valida una clave de un chequeo que nunca se ejecuta. Ambos bugs llevan meses en verde | La suite se corre completa en cada paso (es la red real para migrar las 32 redes finales una a una). Se agrega un **golden set de dictámenes reales** que compara contenido, no forma: `tools/scoreboard.py` ya guarda cada corrida con fecha y commit y avisa si un caso retrocedió. Regla: ninguna red final se borra sin un test que reproduzca el bug original | Un cambio grande pasa en verde a la primera |
| **Sesiones de trabajo en paralelo tocando el mismo repositorio** | Es el modo de trabajo actual y ya produjo pares como `multi_agent.py` / `multi_agente.py` (nombres a una letra, cosas opuestas, ambos importados desde el mismo archivo) y funciones redefinidas en silencio (`escHtml` en dos líneas distintas, gana la segunda) | `BITACORA.md` sigue siendo obligatoria al abrir y cerrar sesión (`CLAUDE.md`). Además: **una rama por versión y un subsistema por sesión** — prohibido tocar dos subsistemas en la misma sesión. Los archivos centrales (`glosa_service.py`, `index.html`, `db.py`) se tocan en ventanas exclusivas anunciadas en la bitácora. Esta regla es la que fija el reparto de trabajo de §10.1 cuando hay dos desarrolladores | Dos ramas modifican el mismo archivo central en la misma semana |
| **El CI no cubre la rama que se despliega** | `ci.yml` dispara en `main/develop/claude/**` y el despliegue sigue la rama `motor-glosas`: el cron **despliega a producción código que nunca pasó ruff ni los tests** | Primera tarea de la semana 1 de la 2.0. No es refactor, es una línea de configuración | Cualquier fallo en producción que la suite habría atrapado |
| **Migrar los contratos del código a la base y que el dictamen cite mal** | El diccionario de Python tiene hoy **prioridad** sobre la base; invertir esa relación cambia lo que la IA cita en cada dictamen | Doble lectura durante 2 semanas (incluida en las 4 de A2): se lee de la base y se compara contra el diccionario, registrando cada diferencia sin cambiar el dictamen. Solo cuando el registro de diferencias esté en cero se apaga el diccionario | Una diferencia en número de contrato o factor tarifario que nadie explica |
| **Perder el conocimiento que costó meses** | Las reglas 8.x del prompt (~15 reglas destiladas de fallas reales fechadas), las 32 redes finales, el conocimiento de portal de los bots ("el modal es de un solo uso por carga de página"; "tandas de 200 porque el dropdown se rompe") y el catálogo contractual con NITs, factores y matices por EPS | Regla suprema del proyecto para esta migración: **el contenido se muda, el contenedor se cambia**. Cada bloque de conocimiento se migra a datos versionados con su test y su comentario de origen (fecha + caso real) intactos | Un comentario con fecha y caso desaparece en un diff |
| **Quemar créditos de IA durante las pruebas de lote** | Ya pasó: $14,50 en 251 llamadas, documentado en `auto_responder_service`. Y `POST /analizar` —el endpoint más caro— **no aplica** el límite de IA que su propio docstring promete: solo tiene 60 req/min genéricos | Aplicar `rate_limit_ia` a `/analizar` en la semana 1; reuso de gemelos por hash activado por defecto en todos los caminos; presupuesto mensual con corte automático y aviso al 70 % (§10.11), medible gracias a C3 | Un salto de costo diario sin un lote que lo explique |
| **Dependencia de una sola persona** | Todo el contexto operativo vive hoy en tres archivos Markdown que hay que **pegar a mano en un chat** cada vez que se retoma un flujo | Los runbooks pasan al sistema como parte del expediente y del perfil de pagador (2.1–2.2), y la capacitación deja material dentro del producto (§10.10). La bitácora se mantiene como memoria de decisiones, no de estados | Alguien pregunta "¿cómo era el flujo de COOSALUD?" y la respuesta es "abrí el .md" |

### 10.9 Cómo se mide el éxito

Advertencia previa, y es una tarea de la 2.0: **hoy varios de estos indicadores no se pueden medir**. No existe medición de tiempo por glosa, el costo por glosa no existe como dato (11 de 12 puntos de llamada a IA no registran; hay 24 filas en `ai_calls` y **ninguna** con identificador de glosa), y "valor recuperado" tiene **cinco fórmulas incompatibles**, cuatro de ellas visibles a un clic de distancia en la misma barra de pestañas del coordinador. Por eso los paquetes **C2** (un solo número) y **C3** (un solo cliente de IA que registre) son P0 de la 2.0: primero se construye el medidor.

| Indicador | Definición exacta (la que va escrita en pantalla) | Línea base hoy | Meta 2.0 | Meta 2.1 | Meta 2.2 | Meta 3.0 |
|---|---|---|---|---|---|---|
| **Minutos por glosa respondida** | Del primer clic sobre la glosa hasta marcarla RESPONDIDA, medido por el sistema | No instrumentado. Proxy verificado: **12–14 clics + 6 campos tecleados** en el camino realista de una glosa suelta | Instrumentado + ≤ 6 clics y ≤ 2 campos | −30 % sobre 2.0 (soportes se abren dentro) | −50 % sobre 2.0 | Estable, con el 80 % del volumen fuera de este camino |
| **% de glosas respondidas sin intervención humana** | Glosas cerradas por texto fijo, plantilla o dictamen aprobado sin una sola edición / total de glosas recibidas en el mes | No medido. Existe el triaje sin IA de ratificadas y extemporáneas, pero solo protege 1 de los 4 caminos de generación | ≥ 35 % (el triaje aplicado a los 4 caminos, más "Preparar el día" reparado) | ≥ 45 % | ≥ 60 % | ≥ 70 % |
| **Tasa de levantamiento** | Glosas LEVANTADAS / glosas con decisión de la EPS registrada, en la ventana elegida | **No es un número, son seis**: existe con seis denominadores distintos y algunas versiones ni identifican al mismo gestor | Una sola cifra, auditable, con su fórmula visible | +5 puntos sobre la línea base real de 2.0 | +8 puntos | +12 puntos y medida contra la predicción |
| **Plata recuperada por mes** | Suma de `valor_recuperado` **registrado** de glosas con decisión de la EPS en el periodo (decisión de C2: se mide con la columna registrada, no con la derivada) | Cinco fórmulas conviviendo; una de ellas suma el valor objetado **completo** de toda glosa levantada sin valor registrado, y es la que el auditor lee mientras redacta | Una sola cifra, cuadrable con contabilidad | +10 % | +25 % (el acta cierra la glosa y alimenta la cartera en una acción) | +35 % |
| **Glosas vencidas por mes** | Objeciones que superaron el plazo sin respuesta radicada | **3 facturas / 38 objeciones / $20.054.751 en un solo mes (junio)**: plazos vencidos el 6 y el 8 de julio, descubiertos a mano el 22 de julio. Es **plata en riesgo por vencimiento**, no plata perdida ni recuperada | **0**, con escalamiento automático al coordinador (el reloj pasa a ser del sistema, no de una celda de Excel) | 0 | 0, con alerta desde la captura del lote en el portal | 0 |
| **Devoluciones re-radicadas dentro del plazo** | Facturas devueltas que se vuelven a radicar dentro del plazo del pagador / facturas devueltas en el periodo | **No medible**: el dato se guarda (`db.py:65`) y no lo trabaja nadie; `/stats/devoluciones-resumen` (`glosas_stats.py:4753`) no tiene un solo llamador | Medido y visible | ≥ 90 % (el subproceso existe, E6) | ≥ 98 % | 100 %, con aviso automático al responsable de la corrección |
| **Costo de IA por glosa** | Gasto registrado / glosas con dictamen generado por IA | No existe: 24 filas en `ai_calls`, 0 con identificador de glosa | Medido y publicado (C3) | −20 % (los caminos sin LLM como primera clase) | −35 % | −50 % |
| **% de objeciones con expediente completo** | Objeciones con radicado + evidencia + decisión registrada / total radicadas | No medible. El estado real del portal solo vuelve a la base si se pasó por el agente de lotes, que solo soporta un pagador | 40 % | 75 % | **≥ 95 %** (lo escribe el bot, no una persona) | ≥ 98 % |
| **Respaldo restaurable fuera de la VM** | Días desde la última restauración probada con éxito | **No existe**: respaldos y base comparten disco (`backup_sqlite.py:54` / `docker-compose.yml:51`) | ≤ 30 días, con prueba mensual documentada | ≤ 30 | ≤ 30 | ≤ 30 |
| **Reproceso** | Dictámenes editados a mano antes de radicar / dictámenes generados | No medido | Instrumentado | ≤ 30 % | ≤ 20 % | ≤ 10 % |

### 10.10 Despliegue y capacitación: quién, cuándo y con qué material

Esto no es un anexo: es la diferencia entre entregar software y entregar una capacidad al hospital. Hoy `docs/CAPACITACION_GESTORES.md` describe un producto que el proceso real nunca usó, y los runbooks de operación se pegan a mano en un chat cada vez que se retoma un flujo. **Decisión: ese documento se declara obsoleto y no se actualiza — se reemplaza por material que vive dentro del sistema.**

| Qué | Decisión tomada |
|---|---|
| **Quién construye la imagen** | GitHub Actions, **fuera** de la VM del hospital. Hoy `deploy/auto_update.sh:60-70` la construye en la misma máquina de 1 vCPU que atiende a los gestores, y esa máquina se queda sin aire mientras compila. La VM solo hace `pull` y `up`. Tarea de la semana 1 de la 2.0, junto con hacer que el CI cubra la rama que se despliega |
| **Cuándo se despliega** | Una ventana semanal fija, **jueves 18:00**, fuera del horario de radicación. Nunca el día en que hay lote programado. La imagen anterior queda etiquetada para volver atrás en un comando, y el despliegue solo procede si el respaldo del día verificó bien (C4) |
| **Quién capacita a los gestores** | **Yesid Pérez**, como dueño del producto. Es quien valida los dictámenes reales y quien conoce el proceso; un desarrollador explicando pantallas no transfiere criterio. El desarrollador capacita a Yesid y al responsable de TI, no al equipo |
| **Cuándo** | Media jornada por versión, en la semana siguiente al despliegue de esa versión, y **un piloto con un solo gestor antes** — la misma disciplina que el equipo ya aplica a los lotes (piloto → lote → segunda pasada con cero pendientes) |
| **Con qué material** | Tres piezas, todas dentro del producto y ninguna en un `.md` suelto: (1) un **recorrido guiado en la aplicación** por cada pantalla nueva, que se dispara la primera vez que el gestor entra; (2) una **guía de una página por flujo** (W1–W7 de §11.12), generada desde el propio sistema para que no pueda quedar desactualizada; (3) el **runbook de cada bot dentro del perfil de su pagador** (A2), donde ya vive el resto de lo que cambia entre pagadores |
| **Criterio de aceptación de cada versión** | Una versión **no se declara entregada** hasta que dos gestores distintos completan el flujo nuevo de punta a punta sin ayuda y sin abrir un `.md`. Si no ocurre, el tiempo de corregir la interfaz se cuenta dentro del paquete de capacitación, no como trabajo extra |
| **Qué pasa con la bitácora** | `BITACORA.md` sigue siendo obligatoria (`CLAUDE.md`), pero cambia de función: deja de ser el manual de operación y pasa a ser la **memoria de decisiones** — por qué se hizo algo, no cómo se hace |

### 10.11 Presupuesto: cuánto cuesta y cuánto cuesta mantenerlo

Ninguna de estas cifras sale del repositorio: son **estimaciones con supuestos declarados**, y el hospital debe reemplazar el valor-semana por su propio costo real antes de llevarlas a un comité.

**Supuesto de costo del desarrollo:** un desarrollador senior asistido por IA en Colombia, **cargado** (salario + prestaciones + parafiscales ≈ 1,5 × el salario base), cuesta entre **$14 y $22 millones de pesos al mes**, es decir **$3,2–5,1 millones por semana** (4,33 semanas/mes).

| Versión | Semanas-persona | Costo estimado del desarrollo | Qué compra |
|---|---|---|---|
| **2.0** | 29,5 | **$94 – 150 millones** | Defendibilidad jurídica, contratos editables sin programador, reloj de vencimientos, un solo número, respaldo fuera de la VM y la mitad de los clics |
| **2.1** | 22,5 | **$72 – 115 millones** | Expediente único, expediente leído completo, copiloto, vault con pantalla, devoluciones |
| **2.2** | 31,5 | **$101 – 161 millones** | El círculo cerrado: captura, radicación, DGH, conciliación y cartera por factura |
| **3.0** | 13,5 | **$43 – 69 millones** | Aprendizaje real, predicción calibrada, plugins |
| **Total del programa** | **97** | **$310 – 495 millones** | ~26 meses con un desarrollador, ~17 con dos |

El segundo desarrollador **no cambia esta tabla**: cambia el calendario. Las 97 semanas-persona se pagan igual; lo que se compra con la segunda persona es llegar nueve meses antes.

**Gasto mensual de IA después de la 2.0.** Supuestos, todos declarados: (a) volumen de **600 a 1.000 objeciones al mes** —el orden de magnitud de la operación real: 597 objeciones en siete lotes de SIMED entre junio y julio, más el resto de pagadores—; (b) la meta de la 2.0 de que **al menos el 35 %** se resuelva por caminos sin LLM (texto fijo, plantilla, dictamen directo), que cuestan **$0** y ~50 ms; (c) el costo observado por llamada en el único incidente medido, **$14,50 en 251 llamadas ≈ $0,058 USD por llamada** de Sonnet; (d) el reuso de gemelos por hash y el corte por complejidad activos en los cuatro caminos, no en uno solo.

| Concepto | Estimación mensual | Nota |
|---|---|---|
| Generación de dictámenes con LLM | **$25 – 70 USD** | 390–650 dictámenes con IA sobre el volumen supuesto |
| Copiloto contextual, verificación de citas y OCR de glosa desde el celular | **$15 – 50 USD** | El copiloto es conversacional y consume más por interacción, pero se usa decenas, no miles, de veces al mes |
| **Total IA** | **$40 – 120 USD/mes ≈ $170.000 – $500.000 COP** | A $4.200 COP/USD |
| Almacenamiento del respaldo fuera de la VM (C4) | **$5 – 15 USD/mes** | Bucket de objetos con retención de 30 días |
| Servidor | **$0 adicional** | Se mantiene la VM actual; la construcción de imagen se muda a GitHub Actions, que en el plan gratuito cubre este volumen |

**Control duro, no confianza:** tope mensual de **$200 USD** con corte automático de las llamadas a IA y aviso al coordinador al 70 % del tope. Ese control solo es posible después de C3, porque hoy el panel de "costos de IA del mes" muestra una fracción del gasto real: 11 de 12 puntos de llamada a Anthropic no registran nada y Groq y Gemini nunca registran.

---

## 11. Documento Maestro de Consolidación

Esta sección responde, una por una, las doce preguntas del encargo, y puede leerse sola. Todo lo que se afirma está verificado contra el código: las **15 auditorías independientes** cubrieron **304 módulos, 142 duplicaciones y 166 hallazgos de UX** (`scratchpad/AUDITORIA_DIGEST.md`). Cuando una respuesta ya está desarrollada con más detalle en otra sección, aquí va la respuesta corta y la remisión: en un documento de este tamaño, repetir una tabla es la forma más rápida de que las dos versiones se contradigan.

### 11.1 ¿Qué módulos existen?

**Quince subsistemas**, agrupados en tres mitades que hoy no se hablan entre sí: la aplicación (`app/`, motor de IA y API), la página web (`static/index.html`, un solo archivo de 23.125 líneas) y las herramientas de escritorio (`tools/`, bots y procesamiento de archivos). El puente entre la mitad que piensa y la mitad que ejecuta **es un archivo Excel que viaja en el escritorio de una PC**.

El inventario completo —tamaño verificado, archivo, línea y veredicto dominante de cada subsistema— está en **§1, "El sistema en números"**. No se repite aquí.

### 11.2 ¿Qué hace cada uno?

En una frase: el motor convierte el texto de una glosa en un dictamen jurídico con citas verificadas; la web es donde el auditor trabaja; los bots escriben esas respuestas en el portal de la EPS. Todo lo demás (contratos, tarifas, soportes, lotes, analítica) existe para alimentar esos tres.

La descripción funcional bloque por bloque, con **el valor irreemplazable de cada uno** —las ~15 reglas 8.x destiladas de fallas reales fechadas, los caminos sin IA a $0, los parsers de Excel del DGH, el conocimiento de los defectos de cada portal pagado con meses de producción—, está en **§1, "Qué hace cada gran bloque"**.

### 11.3 ¿Cuáles son duplicados?

Este es el corazón del problema: la regla del blueprint "una sola fuente de verdad" (§3) está violada en **al menos 24 conceptos centrales**. Las tres peores, porque son las que le cuestan plata o credibilidad al hospital todos los días:

- **"Glosa cerrada"**: 117 declaraciones locales con 3 variantes incompatibles. Por eso una glosa RATIFICADA cuenta como cerrada en 13 pantallas y como abierta en las otras 117.
- **"Valor recuperado"**: 5 fórmulas, cuatro visibles a un clic de distancia en la misma barra de pestañas.
- **Ficha de contrato por EPS**: 4 fuentes, y el diccionario de Python le gana a la base de datos — por eso editar un contrato por pantalla es placebo.

La tabla única, con las 24 filas, su ubicación exacta y **cuál sobrevive** en cada caso, es **§5.5**. Es la tabla de referencia del proyecto para esta pregunta.

### 11.4 ¿Qué funcionalidades se pueden fusionar?

| Fusión | Qué se une | Se ahorra | Riesgo |
|---|---|---|---|
| **Un solo motor de respuesta** | `/analizar` + importación masiva + auto-responder + generar-lote | La inconsistencia de calidad entre puertas; el gasto descontrolado del importador; el bloqueo de 10 minutos del request de lote (que Cloudflare corta a los 100 s) | Alto — es el corazón; se hace con la suite completa y migración red por red |
| **Un motor de checks con dos salidas** (regenerar / informar) | Quality Gate + `validador_dictamen` + `auditor_dictamen` + `dictamen_postprocesor` | ~2.800 líneas y la contradicción activa: una capa **exige** el correo institucional en el dictamen y otra lo **penaliza** como coda procesal | Medio |
| **Un ingestor de Excel** | Los 3 detectores de encabezado incompatibles | Que la fila de encabezado se importe como una glosa (verificado) y que la plantilla oficial que la propia UI ofrece descargar cree 4 glosas basura y gaste 4 llamadas de IA | Bajo |
| **Un adaptador SIMED con dos acciones** | `responder_glosas_simed.py` + `cargar_soportes_simed.py` | ~250 líneas y la clase de bug "se arregla el selector en un archivo y el otro sigue roto" | Bajo — no se toca la lógica de portal |
| **Un solo adaptador DGH, de dos direcciones** | `tools/organizar_objeciones_dispensario.py` (entrada) + `tools/responder_glosas_dgh.py` (salida, en piloto por coordenadas de pantalla) + los Excel manuales de ida y vuelta | Que el único punto donde la glosa existe contablemente dependa de dos scripts y una persona copiando celdas | Medio — es el paquete R4 de la 2.2 |
| **Un solo panel de refinado** | Las 4 interfaces contra el mismo endpoint, hoy con el checkbox "Guardar" en 4 estados distintos | Que el mismo gesto guarde o no según desde dónde se hizo | Bajo |
| **Una sola bandeja de vencimientos** | Las **7 superficies** que responden "¿qué se vence?" consultando los mismos dos endpoints | Que lo ya vencido esté oculto: el repositorio filtra `dias_restantes > 0`, así que **lo más urgente desaparece de la pantalla que existe para eso** | Bajo |
| **Un solo aprendizaje de estilo del gestor** | `memoria_gestor.py` + `aprendizaje_diff.py` | Dos módulos, dos suites de tests y un solo consumidor | Bajo |
| **Un solo predictor** | `riesgo_ratificacion` + `ml_ratificacion` + `predictor_glosas` | Que el único visible no consulte la base ni una vez | Medio |
| **Un solo lector de documentos** | Los 5 caminos de lectura de PDF, cada uno con su política de truncado | Que cambiar el presupuesto de tokens exija tocar 5 lugares; y elimina el monkey patch en producción que el propio código confiesa | Medio |
| **Un solo modelo de lote** | `LoteImportacionRecord` + `LoteRecord`/`TareaLote`/`FacturaLote` + `ImportacionRecepcionRecord` | La barra de progreso simulada, el costo que siempre muestra $0.00, el "IA: N/N listas" que cuenta el marcador de posición como dictamen, y el "Cancelar" que no cancela | Medio |

### 11.5 ¿Qué pantallas sobran?

De **26 paneles se pasa a 14**, y ninguna función que alguien use desaparece. Esas 14 pantallas son las que agrupan los **9 módulos de navegación** del sistema nuevo: 9 módulos y 14 pantallas no son dos promesas distintas, son el mismo mapa visto desde el menú y desde el contenido.

Las que se van sin que nada las absorba, porque están rotas a la vista del usuario: **Salud Total** (ítem de primer nivel del menú, habilitado para el rol AUDITOR, con los dos botones devolviendo 404 desde mayo de 2026), **Alertas** (dos líneas de markup, sin título, sin filtros, cero botones), **Multi-concepto, Detector en masa y Simulador** (completas, con endpoints vivos y sin un solo ítem de menú que lleve a ellas), **Cobranza Live** y **Resumen del mes** (cascarones de ~33 líneas con un botón cada uno) y la **barra de navegación antigua** (10 botones invisibles que `tab()` sigue recorriendo en cada cambio de pantalla).

El detalle pantalla por pantalla, con línea de código, módulo que la absorbe y decisión, está en **§3.5**.

### 11.6 ¿Qué botones desaparecen?

Desaparecen los que mienten: los que devuelven 404 desde mayo, los que muestran un mensaje verde sin haber hecho nada ("Aplicar recomendación" busca tres identificadores de campo que no existen), el "Cancelar lote" que solo oculta la fila mientras la IA se sigue gastando, el "Deshacer" que el propio código admite que no deshace, y los duplicados (3 paletas con Ctrl+K, 3 modales de atajos, 5 botones de exportar en 3 pantallas, 2 botones de limpiar formulario en la misma pantalla que limpian cosas distintas). El listado completo, con línea y decisión, está en **§3.5** y en la auditoría de experiencia de **§2.4**.

Dos decisiones sobre botones que solo se toman aquí, porque no son borrados:

- **"Marcar como RESPONDIDA" no desaparece: asciende.** Hoy es el último elemento tras todo el scroll, con el mismo peso visual que "Copiar texto" (`16434`). Pasa a ser acción primaria fija.
- **De las 12 funciones sin ningún botón que las llame, una no se borra: `registrarResultadoConciliacion`** (`20593`). Es el cierre contable del proceso: en vez de eliminar el código, se crea el botón que le falta.

### 11.7 ¿Qué servicios usan exactamente la misma lógica?

Medido con comparación textual de cuerpos de función (`difflib.SequenceMatcher`), no a ojo:

| Función / lógica | Copias | Similitud medida | Dónde |
|---|---|---|---|
| `setup_logging` | 3 | **100 % idéntica** | `responder_glosas_coosalud.py:115`, `responder_glosas_simed.py:94`, `cargar_soportes_simed.py:88` |
| `_screenshot_debug` | 3 | 92 % entre los de SIMED, 86 % contra COOSALUD | mismos archivos |
| `cargar_credenciales` | 4 | 85 % (solo cambia el nombre de la variable de entorno) | + `login_dg.py:60` |
| `login` del **mismo** portal SIMED | 2 | 51 % | dos bots contra el mismo sitio con las mismas claves |
| `cargar_indice` | 2 | 52 %, y **dos expresiones regulares distintas** sobre el mismo archivo | un arreglo hay que aplicarlo dos veces |
| `main()` / `procesar_factura()` | 2–3 | 6–10 % textual, pero **es la misma máquina**: mismos flags, mismo CSV incremental con vaciado cada 5, misma detección de sesión caída, mismo `MAX_RELOGINS = 5` | ~550 líneas duplicadas |
| `normalizar_factura` / `factura_corta` | 5 | Comportamientos distintos: una devuelve nulo si no coincide, otra devuelve la entrada | 5 archivos de `tools/` |
| `sanitizar` | 3 | Mismo nombre, **tres contratos distintos** (portal, nombre de archivo, nombre de carpeta) | `tools/` |
| `_normalizar_valor` (moneda) | 2 | Parsers de pesos ligeramente distintos | `tarifas_contratadas.py:34`, `tarifas_excel_parser.py:44` |
| Parser de moneda | 2 | `app/utils/moneda.parse_valor_cop` vs `auto_pilot_decision._parse_valor` (privada, **importada por 5 módulos**) | `app/` |
| Bucle multi-turno de herramientas contra Anthropic | 3 | El mismo saneo de bloques vacíos, uno importándolo del otro | `asistente_maestro.py:409`, `multi_agent.py:148`, `glosa_service.py:8530` |
| Check de placeholders entre corchetes | 3 | Tres expresiones regulares distintas | `post_validator:379`, `validador_dictamen:286`, `detectar_defectos_criticos:744` |
| Check de cifras inventadas | 3 | **Tres criterios incompatibles** | `post_validator:245`, `validador_dictamen:94`, `:773` |
| Verificación de longitud del dictamen | 4 | 200–5000 caracteres / 130–320 palabras / >340 palabras / <200 caracteres | cuatro umbrales que se contradicen |
| Resolución de identidad de EPS | 4 | `pagador_normalizer`, `resolver_entidad`, `dictamen_stale._matchea_eps`, el emparejamiento por tokens de `get_contrato` | `app/services/` |
| Endpoints gemelos | 4 pares | `/glosas/alertas` ≡ `/alertas/proximas`; `/validador/pre-radicacion` ≡ `/glosas/{id}/validar-rapido`; `/analizar/extraer-soportes` ≡ `/herramientas/extraer-factura`; `/glosas/{id}/conciliaciones-resumen` ≡ `/conciliaciones/glosa/{id}` | en todos los casos el frontend usa uno solo |

### 11.8 ¿Qué IA se puede reutilizar?

La respuesta corta: **casi toda la IA que hoy funciona hay que conservarla; lo que sobra es el andamiaje apagado alrededor.**

**Se reutiliza tal cual (es el núcleo de la IA Central del blueprint §5):**

| Pieza | Por qué es irremplazable |
|---|---|
| `citation_verifier.py` | Distingue norma inexistente / artículo fuera de norma / cita literal falsa contra el texto real, con cicatrices documentadas caso por caso (la sentencia fantasma "C-4747/2007", el guion Unicode del caso FOMAG). Es el anti-alucinación que sí corre en producción |
| Las reglas 8.x del prompt base | ~15 reglas de defensa destiladas de 33 rondas de auditoría adversarial, cada una con fecha y caso real. Es el activo de negocio más difícil de reconstruir |
| Los caminos **sin LLM** | Texto fijo (ratificadas, extemporáneas), plantilla por código y dictamen directo: dictámenes a $0 y ~50 ms con respaldo seguro. Son el mayor retorno del sistema y la base del presupuesto de IA de §10.11 |
| `confidence_scorer.py` | El único score con desglose accionable ("subí el PDF del contrato en Tarifas") |
| `rag_service.py` (BM25) | El único recuperador de precedentes reales del hospital, hoy desperdiciado detrás de un cortocircuito |
| `few_shot_gold.py` | El único módulo cuyo conocimiento **crece solo**, con filtro anti contrato-cruzado nacido de un caso real |
| `detector_copia.py` | 76 líneas que impiden que el modelo copie una plantilla con datos de otro expediente |
| `calibracion_dificultad.py` | El único módulo que cierra el lazo histórico → prompt en el camino principal, gratis |
| Asistente Maestro (9 herramientas) | El esqueleto natural del copiloto único (§15) |
| `/vida/ocr-imagen` (Gemini) | Foto de la glosa desde el celular → texto. La única entrada multimodal barata, y resuelve un problema real de campo |
| `contexto_contractual_enriquecido` + extractor de cláusulas | La capacidad diferencial: el dictamen cita la cláusula exacta con su página |
| `tarifa_lookup_service` | Evaluación determinista de glosas tarifarias **sin gastar IA**, endurecida con casos de producción |
| Defensas anti-costo del auto-responder | Reuso de gemelos por hash, caché de 2 niveles con clave versionada, semáforo de concurrencia. Nacidas del incidente real de $14,50 en 251 llamadas |

**Se borra (IA que no llega a nadie o que miente):**

`multi_agent.py` (apagado desde siempre, 1 de 3 agentes implementado, 3× costo por diseño) · `asistente_predictivo` + `inteligencia_ambiental` (router registrado y nunca invocado) · `rag_normativa` (sus dos endpoints no se llaman desde ninguna parte, y su validación da por buena cualquier cita cuyo número aparezca en cualquier lugar del corpus) · `normativa_grafo` (detrás de un interruptor apagado por defecto) · `chat_glosa` (promete conversación y tiene 8 respuestas fijas por palabra clave; el ejemplo que la propia pantalla sugiere no coincide con ninguna) · `predictor_glosas` y `ml_ratificacion` (0 llamadores) · `busqueda_semantica` (no es semántica: es un `LIKE` más un modelo reordenando 80 filas, a costo de una llamada por búsqueda) · el bucle de herramientas del generador de dictámenes (apagado, duplicado tres veces).

### 11.9 ¿Qué tablas se deben unificar?

De **37 tablas a ~24**, sin perder ninguna función que alguien use.

| Movimiento | Tablas | Justificación |
|---|---|---|
| **Borrar** | `push_subscriptions`, `notas_privadas`, `preset_filtros`, `comentarios_thread`, `webhooks`, `chat_conversaciones`, `chat_mensajes`, `snippets` | **8 tablas de 37 (el 22 % del esquema)** sin una sola referencia en Python, materializadas en cada arranque. Sus routers se borraron en mayo de 2026 y **el frontend las sigue llamando en cinco funciones visibles** que fallan en silencio |
| **Borrar** | `plantillas` | 0 filas; es un subconjunto estricto de `plantillas_gold` (52 filas), que además guarda la evidencia de resultado |
| **Fusionar** | `lotes_importacion` + `importaciones_recepcion` → `importaciones` (columna `origen`) | Duplicado casi literal: mismo usuario, total, estado, marca de tiempo y lista de IDs serializada en JSON |
| **Fusionar** | `comentarios_glosa` absorbe la idea de nota privada con una columna `visibilidad` | Es la única de las tres tablas de comentarios que sigue viva |
| **Reescribir** | `historial` pierde 9 columnas que duplican `conceptos_glosa` | El propio código tiene dos ramas para leer el mismo dato, una rotulada "Fallback legacy" |
| **Reescribir** | `contratos` recibe los datos reales | 15 de sus 17 columnas están **100 % vacías** en las 13 filas existentes: los datos viven en un diccionario de Python |
| **Crear** | `pagador` (NIT como clave natural, nombre comercial, nombre de plan, alias) | Hoy la entidad pagadora se identifica con **cinco campos de texto sin normalizar** y el emparejamiento se hace con `ILIKE '%eps%'`, que anula el índice y puede cruzar tarifas entre EPS de nombre parecido |
| **Crear** | `factura` como entidad de primera clase, con `es_devolucion` colgando de ella | La cartera se calcula por factura; hoy se calcula por glosa y **se duplica la plata**. Y la devolución es un atributo de la factura, no de la glosa: obliga a re-radicar (§10.4, E6) |
| **Crear** | `estado_glosa` (catálogo con `es_terminal`) | Elimina las 117 declaraciones locales |
| **Convertir JSON en filas** | `importacion↔glosa`, `conciliacion↔participante`, `contrato↔modalidad_tarifaria` | Los participantes de un acta son personas con nombre y cargo que un documento legal necesita citar individualmente; hoy son un campo de texto |
| **Corregir** | `lotes.excel_archivo` (hasta 20 MB de binario en la fila) y `adjuntos` (Base64 en columna de texto, +33 % de tamaño, va a todos los respaldos) | Almacenamiento fuera de la base — y respaldos que caben en el destino externo de C4 |

Y dos correcciones de índices que hoy cuestan minutos al día: `audit_log(tabla, registro_id)` **no existe** y es exactamente el filtro de todos los lectores del registro; `historial` tiene 14 índices y **ninguno** cubre `fecha_decision_eps` ni `fecha_vencimiento`, que son las dos fechas que filtran casi toda la analítica.

### 11.10 ¿Qué APIs pueden convertirse en una sola?

De **686 rutas** se baja a ~180 sin perder una sola función usada.

| Familia | Hoy | Queda | Evidencia |
|---|---|---|---|
| Estadísticas | **171** endpoints en `glosas_stats.py` (11.341 líneas) | **6** en un servicio de métricas con una definición por palabra | 167 de 171 no tienen llamador. Es donde vive el bug replicado 117 veces |
| Administración | **77** en `admin.py` (5.344 líneas) | **5** | 72 sin llamadores en frontend, herramientas ni scripts |
| Analítica personal | ~33 (`/usuarios/yo/*`) + 3 (`/mi-desempeno`) + `/mi-dia` | **1–2** ("mi trabajo hoy" + "mi desempeño") | La pantalla personal del gestor hoy se arma con ~15 peticiones separadas — y `/usuarios/yo` es, además, la que el service worker cachea entre usuarios distintos (§10.3, C5) |
| Notificaciones y alertas | 3 familias solapadas + `/glosas/alertas` + `/glosas/vencen-24h` + `/alertas/*` | **1** consulta de vencimientos que siempre incluye lo vencido primero | Siete superficies distintas responden la misma pregunta |
| Salud del sistema | **6** endpoints (`/health`, `/health/detail`, `/sistema/salud`, `/salud/publico`, `/healthcheck-profundo`, `/soportes-auto/healthz`) | **2**: `/health` público de 3 campos + `/admin/salud` autenticado | `/sistema/salud/publico` corre detección de anomalías sobre 30 días **sin autenticación ni límite de tasa** en una VM de 1 vCPU |
| Informes ejecutivos | **4 "informes del mes"** con cifras distintas | **1**, con tres formatos de salida | Es el paquete C2 de la 2.0 |
| Generación de dictamen | 4 puertas | **1** motor + 4 adaptadores de 20 líneas | |
| PDF del dictamen | 3 endpoints (2 muertos) + 3 generadores de navegador | **1** | ~450 líneas de `reportlab` muertas |
| Validación del dictamen | 2 endpoints al mismo servicio + 3 validadores | **1** | |
| Búsqueda de códigos y tarifas | 3 buscadores expuestos | **1** | El frontend usa uno solo |
| Devoluciones | 1 endpoint de resumen (`glosas_stats.py:4753`) **sin un solo llamador** | **3** (bandeja, corrección, re-radicación) | Es el único caso de esta tabla donde la consolidación **agrega** endpoints: hoy el subproceso no existe en ninguna pantalla |
| Anomalías | 4 detectores, ninguno visible | **1**, con tarjeta en el panel Mando | Solo uno agrega en SQL; los otros cargan la tabla en memoria |
| Proyección de recuperación | 3 implementaciones, **0 en pantalla** | **1**, visible, con su base explicada en una línea | Es una de las cinco preguntas que hace un gerente y hoy no tiene respuesta |

Regla nueva que acompaña la consolidación: **ningún endpoint puede volver a agregar por su cuenta.** Toda cifra sale del servicio de métricas, y toda pantalla muestra la definición de lo que está mostrando. Y 31 endpoints que hoy hacen `db.query(GlosaRecord).all()` sin filtro pasan a agregar en SQL: medido con 50.000 glosas, cargarlas todas cuesta 2,4–6,7 s y +507 MB en **una** petición; la misma cifra con `GROUP BY` tarda 110 ms. Regla de autorización que va con ella: **todo endpoint que devuelva datos de paciente filtra por rol y asignación**, empezando por `GET /glosas/historial` (§10.3, C5).

### 11.11 ¿Qué componentes React son iguales? (pregunta reformulada, con honestidad)

**No hay React, ni Vue, ni ningún framework.** El frontend es un único archivo `static/index.html` de **23.125 líneas** (verificado; la carpeta `static/` completa, con html, js y css, suma 26.728) en JavaScript de navegador, con:

- **554 declaraciones `function`** (521 en el ámbito global), 51 variables globales y 47 asignaciones a `window`;
- **428 asignaciones a `.innerHTML`**, **2.216** atributos `style=` en línea y **288** `!important`;
- **0 elementos `<form>`** (verificado con `grep -c '<form'`), así que los atributos "obligatorio" de los campos son decorativos;
- **276 llamadas `fetch`**, de las cuales solo 11 comprueban sesión expirada, y de **cuatro maneras distintas**;
- dos funciones redefinidas en silencio con el mismo nombre en el mismo ámbito (`escHtml`, `paFmtCOP`): gana la segunda y nadie se entera.

No existe encapsulación: cualquier función puede pisar el estado de cualquier otra. La consecuencia más cara ya se midió: **cinco variables distintas guardan "la glosa abierta"**, y "Nueva glosa" limpia dos de las cinco, así que el panel de nota privada sigue apuntando a la glosa anterior.

**Lo que sí está repetido y se componentiza** (respuesta a la pregunta reformulada):

| Bloque repetido hoy | Copias | Componente propuesto |
|---|---|---|
| Documento institucional del HUS (membrete, NIT, consecutivo, firma, sello) | 4 plantillas visuales con tipografías y colores distintos, en 3 archivos | **Uno**, en el servidor. El frontend pide la URL y la abre |
| Tabla de glosas con semáforo, badges y selección múltiple | Historial, Mis glosas, resultados de lote | `<hus-tabla-glosas>` |
| Tarjeta de indicador (KPI) | Dashboard, Mando, Mi desempeño, Resumen del mes, encabezado | `<hus-kpi>` con etiqueta, fórmula y fecha de corte visibles |
| Modal / cuadro de diálogo | 44 `prompt()` + 44 `confirm()` + 12 `alert()` nativos (verificado) | `<hus-dialogo>` con campos tipados y desplegables |
| Paleta de comandos / buscador | 3 paletas + 1 spotlight + 1 buscador de sidebar | `<hus-paleta>` única, que busque datos y acciones |
| Panel de refinado con chips | 4 copias, con los mismos 5 chips copiados literalmente | `<hus-refinar>` |
| Barra de exportación | 5 botones en 3 pantallas | `<hus-exportar>` con selector de formato y alcance |
| Semáforo de confianza | 4–6 indicadores simultáneos | `<hus-confianza>` alimentado por un solo score |
| Subida de archivo con progreso | El subidor de ZIP es **lo mejor hecho de la interfaz** (progreso real, resumen de guardados/rechazados con motivo por archivo) y no se reutiliza en ningún otro lado | `<hus-subida>` — ese componente pasa a ser el estándar de toda operación larga |
| Formulario de glosa | 24 controles antes de poder pulsar "Analizar", cuando solo 2 son obligatorios | `<hus-form-glosa>` con "Datos adicionales" plegado |
| Navegación | Una cadena de 21 condicionales encadenados en `tab()` | Mapa declarativo `{panel: cargador}` |
| Cliente HTTP | 276 llamadas sueltas, con manejo de sesión de 4 sabores | Un solo cliente con reintento, renovación de sesión y un único mensaje de sesión expirada |

**Decisión técnica: componentes web nativos (`customElements`), no React.** Tres razones: (1) no agrega dependencias ni proceso de compilación a un despliegue que hoy es un contenedor en una VM de 1 GB; (2) se puede hacer **incremental**, componente por componente, sobre el archivo actual, sin un "gran día del cambio" que ponga en riesgo la operación diaria; (3) el equipo es de una persona — un framework nuevo es una deuda de aprendizaje, no un ahorro. La componentización se aborda en la 2.1; la 2.0 se hace sobre el archivo actual, donde los cuatro movimientos de mayor impacto son borrados.

Tres cosas se arreglan sí o sí durante la componentización, porque son riesgo y no estética: el dictamen se inserta hoy con `innerHTML` **sin escapar** sobre texto que originó el usuario (`16351`, `16377`) en un sistema que guarda el token de sesión en el navegador; el control de acceso del menú se lee de `localStorage` (`12844`), así que cualquiera puede escribir `hus_rol='SUPER_ADMIN'` y recuperar los 24 ítems, incluida la zona con "Borrar todo"; y el service worker deja de cachear respuestas de usuario (`sw.js:14,20`), que es lo que hoy permite que en un PC compartido el segundo gestor vea los datos del primero. **La restricción real tiene que estar en el servidor; la del navegador solo ordena la vista.**

### 11.12 ¿Qué workflows deben quedar como estándar?

Siete flujos. Todo lo demás es una variante de estos, y cualquier funcionalidad nueva tiene que caber en uno (regla suprema del blueprint §20).

| # | Workflow | Pasos estándar | Dueño | Dónde vive hoy | Qué cambia |
|---|---|---|---|---|---|
| **W1** | **El día del auditor** | Abrir → ver la bandeja priorizada con vencimientos y valor en riesgo → "Preparar el día" (cierra ratificadas y extemporáneas con texto fijo) → trabajar la cola | Gestor | **Está roto.** El botón existe, es idempotente y explica el resultado en español, pero llama a `POST /autopilot/preparar-dia` (`static/index.html:7112`), ruta cuyo router fue eliminado (`app/main.py:1207`): **devuelve 404**. Y además vive en el estado vacío del panel Analizar, así que **desaparece en cuanto se analiza la primera glosa**. Frecuencia de uso real: nula | Se reconstruye el endpoint sobre la lógica de texto fijo que sigue viva (paquete A0) y pasa a ser la pantalla de inicio (B1). Es la automatización de mayor retorno del producto y hoy no funciona |
| **W2** | **Entrada de glosas** | Captura en el portal → importación con perfil de pagador → detección de hoja y encabezado → semáforo por días hábiles con feriados → reparto por identidad de gestor → triaje sin IA → **separar devoluciones de glosas** | Recepción | Es la joya del sistema (aliases reales del DGH, extemporaneidad por días hábiles, delegación por vacaciones), pero el reloj llega **escrito en una celda de Excel** y si falta, la fila se descarta y la glosa nunca existe. Y la marca `DEVOLUCION S/N` se guarda y no la trabaja nadie | El reloj lo calcula el sistema desde el perfil del pagador (C1); el régimen especial es un atributo, no la frase mágica "NO APLICAR EXTEMPORANEIDAD" escrita a mano; y la devolución entra a su propio subproceso (E6) en vez de perderse |
| **W3** | **Responder una glosa** | Número de factura → trae los N conceptos, avisa de duplicado y lee los soportes del disco → decidir por concepto (defender / aceptar 100 % / parcial) → generar → verificar citas → marcar RESPONDIDA | Gestor | La caja "Conceptos vinculados a esta factura" es la pieza que convierte 43 objeciones en un flujo manejable, y vive dentro de un acordeón cerrado rotulado "opcional" | Se pone en el centro; el bucle secuencial del navegador (1,8 s de espera artificial por concepto) se reemplaza por el ejecutor del servidor |
| **W4** | **Radicar en el portal** | Seleccionar el lote → el bot ejecuta → estado, pantallazo y radicado vuelven **a la glosa** | Sistema | El bot cierra la factura y saca el pantallazo, y nadie actualiza el estado: para SIMED —el flujo de más volumen— el resultado vive en un CSV en un escritorio. Los bots procesaron 324 facturas y 597 objeciones en siete lotes; de los tres últimos, por $153.675.820, el Excel está listo y la subida sin confirmar | El estado de una objeción lo escribe el sistema a partir de lo que devuelve el portal, no una persona (R3) |
| **W5** | **Registrar la decisión de la EPS** | Levantada / Aceptada / Ratificada + valor → aprendizaje automático (el argumento ganador se promueve, el perdedor se desactiva) → indicadores | Gestor | El mecanismo de aprendizaje **existe y está cableado**, pero la reinyección está cortada por dos lados y la desactivación exige coincidencia exacta de 200 caracteres con texto generado por IA — que prácticamente nunca ocurre | Se captura con desplegable, no escribiendo "LEVANTADA" a mano en un cuadro del navegador |
| **W6** | **Cierre del ciclo** | Ratificada → se crea la conciliación sola → audiencia con contraargumentos probables → acta → nota crédito con CUV validado → **registro en el DGH** → cartera actualizada | Coordinación | Tres implementaciones para una etapa, y la que se firma es un TSV. El acta del sistema no cierra la glosa ni suma a la plata recuperada, y el asiento contable en el DGH se hace a mano | Una sola acción: cerrar el acta transiciona la glosa, escribe el valor recuperado, actualiza la cartera y deja el registro listo para el adaptador DGH (R4) |
| **W7** | **Cargar conocimiento** | Subir contrato en PDF → cláusulas extraídas con página → **revisión humana** → vigente desde/hasta → disponible para la IA y para el auditor | Coordinación | Hoy no hay forma en la interfaz de **crear** un contrato, y el mensaje de error del sistema remite a una pestaña que no tiene formulario de creación: callejón sin salida con una EPS nueva. Además, subir el PDF no ofrece revisión humana de las cláusulas antes de que empiecen a inyectarse en dictámenes | Formulario de creación, revisión obligatoria y vigencias por fecha de atención (el caso real: contrato 287 hasta el 30-nov-2025 con SOAT −15 %, contrato 440 desde diciembre con SOAT −20 %; **372 de 444 glosas venían marcadas "SIN CONTRATO" teniéndolo**) |

**Un principio que ordena los siete:** ninguno de estos flujos puede depender de que alguien se acuerde de pulsar un botón después de que la máquina terminó. Hoy tres de ellos sí dependen de eso (marcar radicada, registrar la decisión de la EPS, registrar el resultado de la conciliación), y el histórico ya demostró el costo: el registro manual estaba equivocado en **6 de 12 facturas**.
