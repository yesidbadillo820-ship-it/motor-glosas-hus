# Mapa de Capacidades de SINAC OS

**ESE Hospital Universitario de Santander** · Versión 1.0 · 28 de julio de 2026

> Vista no técnica de SINAC OS: qué sabe hacer la plataforma, qué puede hacer
> hoy y qué falta construir. Complementa el
> [Manual de Arquitectura](MANUAL_ARQUITECTURA_SINAC_OS.md).

---

## 20. Mapa de Capacidades de SINAC OS

### 20.1 Qué es este mapa y para qué sirve

Este documento es la **vista de negocio de SINAC OS**. No describe archivos, clases ni endpoints: describe **capacidades** — cosas que el hospital sabe hacer, o va a saber hacer, con este sistema. Está escrito para que un gerente, un auditor nuevo o un jefe de área entiendan el sistema completo sin abrir una línea de código, y para que cualquiera pueda responder tres preguntas antes de pedir o construir algo:

1. **¿Esto ya existe?** — y si existe, ¿en qué estado?
2. **¿A qué familia pertenece?** — para no crear un módulo nuevo donde ya hay una capacidad.
3. **¿Quién la usa?** — porque una capacidad sin dueño no se mantiene.

El mapa es la cara legible del **Registro de Capacidades** del núcleo (§18): no se escribe a mano, se **deriva** del registro y del catálogo de pruebas. Una capacidad que pierde su prueba baja de estado sola, y el manual y el sistema no pueden desincronizarse sin que falle el CI.

**Una capacidad no es un módulo, y menos una EPS.** Esta es la regla que ordena todo el mapa: no existe "el módulo FOMAG"; existe la capacidad *conversión de formatos de objeciones*, y FOMAG es un **perfil**. La prueba de que la regla estaba mal aplicada hasta hoy está medida: cuatro programas distintos (SAVIA, VCO, EMSSANAR, DISPENSARIO), **2.581 líneas**, escriben **el mismo archivo** con los mismos 16 encabezados byte a byte, y **14 de esas 16 columnas (87,5 %) admiten una sola implementación**. Eso no son cuatro módulos: es una capacidad construida cuatro veces.

**Los cuatro estados, y su significado exacto.** Este mapa es honesto por diseño: un estado optimista cuesta plata.

| Símbolo | Estado | Qué significa exactamente |
|:--:|---|---|
| ● | **Disponible** | Funciona en producción, tiene usuario real y prueba verde. |
| ◐ | **Parcial** | Existe y sirve, pero le falta el último tramo: sin pantalla, sin conectar, apagado por bandera, o entrega menos de lo que promete. |
| ◇ | **Huérfano** | Está construido, probado y funcionando — **fuera del sistema**: en una rama con PR en borrador, en el escritorio de una PC o en un chat. Se recupera; no se reescribe. |
| ○ | **Por construir** | No existe en ninguna parte. Solo aquí se admite código nuevo, y solo tras pasar el Principio Nº 1. |

**Cómo leer los números.** El sistema actual tiene 100.259 líneas de backend, 193 archivos, 686 endpoints, 37 tablas, 4.266 pruebas y un frontend de un solo archivo de 23.125 líneas. Ese volumen no mide capacidad: **287 de los 686 endpoints tienen alguna referencia desde la interfaz**, un solo archivo de estadísticas suma 11.341 líneas con 167 de sus 171 rutas sin un solo llamador, y hay **39 archivos de módulos terminados que nunca se fusionaron**. Por eso el mapa cuenta capacidades y no líneas: es la única unidad en la que el hospital y el sistema hablan el mismo idioma.

---

### 20.2 El árbol completo de capacidades

Al centro no hay un módulo: hay un **objeto vivo**. Todo lo demás existe para hacerle algo a ese objeto.

```
                    ┌──────────────────────────────────────────────────────┐
                    │            PROCESO ADMINISTRATIVO                    │
                    │  no muere: cambia de estado                          │
                    │  Factura → Glosa → Objeción → Respuesta → Radicación │
                    │  → Conciliación → Aceptación → Pago → Archivo        │
                    └───────────────────────┬──────────────────────────────┘
                                            │ se materializa en un solo objeto
                    ╔═══════════════════════▼══════════════════════════════╗
                    ║                   EXPEDIENTE                         ║
                    ║  UUID · Estado · Eventos · Versiones · Memoria IA    ║
                    ║  Documentos · Historial · Responsables · Contratos   ║
                    ║  Normatividad · Decisiones · Bots · Tareas · Riesgos ║
                    ║  ── una sola verdad sobre una factura, para siempre ─║
                    ╚═══════════════════════╤══════════════════════════════╝
                                            │
    ┌───────────────────────────────────────┴────────────────────────────────────┐
    │                        LAS DIEZ FAMILIAS DE CAPACIDADES                     │
    └─────────────────────────────────────────────────────────────────────────────┘

 1. GESTIÓN DE GLOSAS ─────────── el trabajo del auditor, de punta a punta
    ● Recepción y reparto        ● Respuesta sin IA (texto fijo)   ◐ Respuesta con IA
    ◐ Ratificación (2ª vuelta)   ◐ Control de calidad del dictamen ◐ Radicación en portal
    ○ Seguimiento y plazos reales                                  ○ Devoluciones

 2. GESTIÓN DOCUMENTAL ────────── todo papel que entra, se lee; todo el que sale, se firma
    ◐ Lectura de documentos (PDF · OCR · visión)   ◐ Índice documental del hospital
    ◐ Generación (Word · PDF · Excel)              ◐ Evidencias y expediente probatorio
    ● Versiones y papelera                         ○ Firma con validez jurídica
    ◇ Caja de herramientas documental (18 operaciones PDF · Office · conversión)

 3. AUTOMATIZACIÓN Y AGENTES ─── el sistema trabaja solo, no cuando alguien hace clic
    ◐ Bots de portal (4 vivos)   ◇ Bots de portal (2 más, huérfanos)  ◐ Bots de escritorio
    ◐ Monitor de carpetas        ◇ Correo institucional (Gmail/Outlook/IMAP)
    ● Lectura tolerante de Excel ◐ Capturas de pantalla como prueba
    ◐ Agente local del hospital  ◐ Tareas programadas   ○ Agentes residentes

 4. INTELIGENCIA Y CONOCIMIENTO ─ lo que el sistema sabe, y que nunca debe olvidar
    ◐ Base de conocimiento       ◐ Normatividad con texto literal  ◐ Contratos como reglas
    ◐ Búsqueda (semántica y de precedentes)         ● Copiloto conversacional
    ○ Memoria y aprendizaje que gire de verdad      ◐ Ruteo y costo de la IA

 5. CONCILIACIÓN Y CARTERA ───── donde la glosa se vuelve plata (o se pierde)
    ◐ Preparación de audiencia   ◐ Acta de conciliación   ◇ Acta multi-glosa sobre plantilla
    ◐ Nota crédito y CUV         ◇ Saldo, aging y recaudo ◇ Circularización a reguladores
    ● Baja de cartera (Res. 577) ○ Pago y cierre contable

 6. CONTRATOS Y TARIFAS ──────── la fuente de reglas de cada peso facturado
    ◐ Ficha de contrato por pagador   ● Cláusulas citables con página
    ● Tarifas contratadas             ◐ Manuales tarifarios (SOAT · propias · ISS)
    ● Homologación de códigos         ◐ Liquidación tarifaria
    ○ Vigencia por fecha de atención

 7. AUDITORÍA Y PREVENCIÓN ───── la glosa más barata es la que no ocurre
    ◇ Pre-auditoría de la cuenta ● Auditoría de radicación   ● Validación FURIPS/ADRES
    ● Auditoría EPS-vs-BD        ◐ Predicción de ratificación
    ◇ Auditoría de devoluciones  ◇ Verificación adversarial del lote

 8. ANALÍTICA Y DIRECCIÓN ────── un solo número por pregunta
    ○ Métrica canónica           ● Tablero del coordinador   ● Informe ejecutivo mensual
    ◐ Mi desempeño               ◇ Respuesta a reguladores   ○ Impacto real del área

 9. OBSERVABILIDAD ───────────── si no se mide, no existe
    ◐ Salud del sistema          ◐ Costo de IA por expediente ◐ Trazabilidad de acciones
    ○ Estado de los bots en vivo ○ Linaje del dato            ● Errores y secretos redactados

10. PLATAFORMA Y GOBIERNO ───── lo que sostiene todo lo demás
    ● Identidad (login · 2FA)    ◐ Permisos por rol           ◐ Bóveda de credenciales
    ○ Cifrado de datos de paciente  ◐ Respaldos                ◐ Esquema y migraciones
    ○ Perfil compuesto (canal × pagador × hospital)            ○ Registro de Capacidades
    ○ Constructor de capacidades y agentes

    ● disponible   ◐ parcial   ◇ huérfano (existe fuera del sistema)   ○ por construir
```

**Lectura de un vistazo:** de 68 capacidades del mapa, **14 están disponibles**, **28 parciales**, **11 huérfanas** y **15 por construir**. El dato que manda: **el 57 % de lo que el hospital necesita ya está construido** (disponible + parcial + huérfano) y no llega al usuario. SINAC OS es, en su mayor parte, un trabajo de **conexión y consolidación**, no de invención.

---

### 20.3 Ficha por familia

#### Familia 1 · Gestión de Glosas

**Qué resuelve.** El trabajo diario del área: recibir la objeción del pagador, repartirla, contestarla con argumento jurídico, controlar su calidad, radicarla en el portal dentro del plazo y saber en qué terminó. Es la familia que justifica el presupuesto del área.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Recepción del Excel del pagador y reparto a gestores | ● | `recepcion_service.py` (1.458 l): alias reales de columnas DGH, feriados colombianos, resolución de gestor con delegación por vacaciones |
| Respuesta sin IA (ratificadas, extemporáneas, tarifa-match) | ● | `recepcion_service.py:1049-1080` — decisión de negocio explícita y fechada: dictamen a $0 y ~50 ms |
| Respuesta con IA (dictamen jurídico) | ◐ | Un método de 2.800 líneas (`glosa_service.py:4299-7097`) con 73 `except` silenciosos y 32 "redes finales" cosidas por orden cronológico de bug |
| Ratificación (segunda vuelta) | ◐ | Texto canónico en `glosa_service.py:3835-3848`, **copiado palabra por palabra** en el bot FOMAG (línea 128) y en el de Mutual Ser |
| Control de calidad previo a radicar | ◐ | Quality Gate: 1.748 líneas de código + 1.151 de pruebas, **apagado por bandera** en el flujo principal |
| Radicación en el portal del pagador | ◐ | 4 bots vivos (COOSALUD, SIMED-glosas, SIMED-soportes, DGH) + 2 huérfanos (FOMAG 1.563 l, Mutual Ser 1.143 l). **La interfaz no sabe que existen**: 0 menciones en las 23.125 líneas del frontend |
| Seguimiento, plazos y escalamiento | ○ | El reloj viene escrito en una celda de Excel; el estado NEGRO existe y no dispara nada |
| Devoluciones como proceso propio | ○ | El dato `DEVOLUCION S/N` se guarda, hay un endpoint de resumen y **nadie lo llama**; no hay pantalla |

**Qué puede hacer hoy, sin adornos.** El hospital puede recibir un lote, repartirlo, generar dictámenes (con y sin IA) y radicarlos masivamente con resultados demostrados: **102 facturas y 225 objeciones subidas y verificadas al 100 % en 22 minutos**. Lo que **no** puede hacer es cerrar el círculo: el resultado del bot vive en un CSV del escritorio, alguien tiene que acordarse de pulsar "marcar radicada", y el reloj de vencimiento no es del sistema. Ese hueco tiene precio conocido: **3 facturas de junio, 38 objeciones, $20.054.751**, vencidas los días 6 y 8 de julio y descubiertas 45 días después, revisando a mano.

**Agentes que la sirven.** *Glosas* (clasifica, redacta, ratifica), *Calidad* (verifica antes de radicar), *Radicación* (lanza el lote y trae el resultado), *Vigilante de Plazos* (residente: vigila el semáforo y escala solo), *Auditor* (residente: detecta inconsistencias entre lo que dice el sistema y lo que dice el portal).

**Qué gana el hospital cuando esté completa.** Que la pregunta *"¿esta objeción se radicó, cuándo, con qué evidencia y cómo terminó?"* se responda en una pantalla y no abriendo tres carpetas y un chat. Y que ninguna glosa se venza en silencio: una glosa vencida deja de ser un descubrimiento y pasa a ser una alarma que escala sola al coordinador.

---

#### Familia 2 · Gestión Documental

**Qué resuelve.** Todo el papel del proceso: leer lo que entra (historias clínicas, PDF de objeción, contratos, RIPS), encontrarlo cuando hace falta, y producir lo que sale (respuesta radicable, acta, expediente de evidencia) con una sola identidad visual y un consecutivo de verdad.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Lectura de PDF (texto nativo · OCR · visión) | ◐ | **Cinco caminos independientes** para leer un PDF, cada uno con su política de truncado. El principal corta cualquier documento de más de 4 páginas a ~7.050 caracteres |
| Índice documental del hospital | ◐ | Indexa hasta 144.000 archivos y **no hay un solo endpoint que devuelva el archivo**: la interfaz muestra la ruta absoluta como texto y ofrece "📋 Copiar" para pegarla en el explorador de Windows |
| Extracción de datos de la factura y de folios citables | ● | `extractor_factura.py` (293 l) y `extractor_folios.py` (120 l): folio, fecha, médico firmante — hechos verificados que la IA tiene prohibido inventar |
| Generación de documentos (Word · PDF · Excel) | ◐ | **Cuatro plantillas visuales** para el mismo documento del HUS, y el que se imprime lleva un "Nº OBJECIÓN" generado con `Math.random()` |
| Evidencias y expediente probatorio | ◐ | Los bots capturan el cartel del portal como prueba legal; el expediente se arma con un script y el consecutivo institucional **se pide por chat a una persona** |
| Versiones y papelera | ● | Nunca se pierde un dictamen: snapshot en cada acción, *diff* en texto plano, restaurar reversible, soft-delete con 30 días |
| Firma con validez jurídica | ○ | Lo implementado es HMAC con la clave del servidor: **no prueba autoría** — y el sistema declara "CUMPLIDO" el artículo de firma digital |
| Caja de herramientas documental | ◇ | 18 operaciones PDF, Office headless y conversión, con 39 pruebas y contrato de servicio explícito, en una rama con PR en borrador |

**Qué puede hacer hoy.** Encuentra los soportes y no los abre. Lee los documentos y los trunca. Genera el documento y le pone un número inventado. Es la familia con la mayor distancia entre lo construido y lo entregado: **un dictamen sobre una historia clínica de 200 páginas se redacta con 7 KB de texto**, y el banner verde le dice al gestor "✓ 12 soportes detectados" cuando la IA leyó tres pedazos de 5 KB.

**Agentes que la sirven.** *Documental* (lee cualquier formato), *Evidencias* (captura, rotula, empaqueta y versiona), *Servidor* (residente: vigila carpetas, detecta duplicados, renombra, indexa).

**Qué gana el hospital.** Que el auditor **nunca navegue una carpeta**. Que el dictamen se construya sobre el expediente completo y no sobre su primera página — que es exactamente la diferencia entre una glosa levantada y una ratificada. Y que un documento del HUS se vea igual salga de donde salga, con un consecutivo que exista de verdad en la base.

---

#### Familia 3 · Automatización y Agentes

**Qué resuelve.** Que el sistema trabaje sin que nadie haga clic: que la glosa entre sola por el correo o el portal, que los archivos se organicen solos, que los bots suban las respuestas y devuelvan el resultado al expediente.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Bots de portal (Playwright) | ◐ | 4 vivos, 2 huérfanos. Comparten el mismo esqueleto **cinco veces**: >6.900 líneas para el mismo flujo (login → filtrar → llenar → guardar → evidencia → CSV) |
| Bots de escritorio (ERP DGH, pywinauto) | ◐ | 746 líneas que **nunca respondieron una glosa real**: operan por coordenadas fijas de pantalla |
| Monitor de carpetas / sincronización del share | ◐ | **Dos agentes locales distintos** en la misma PC, con dos tokens, dos configuraciones y dos formas de instalar |
| Correo institucional (entrada real del proceso) | ◇ | Un bot de 63 KB convierte 78.905 correos en un árbol clasificado; bajó la revisión manual **del 72 % al 8 %**. Vive fuera del sistema. En la app hay un esqueleto IMAP que nadie ejecuta |
| Lectura tolerante de Excel | ● | Alias de columnas, detección de encabezado, parser de pesos colombianos — resuelto bien y **reimplementado en cada módulo** |
| Motor Universal de conversión de objeciones | ◇ | 4 conversores, 2.581 líneas, mismo archivo de salida. 14 de 16 columnas admiten una sola implementación |
| Capturas como prueba | ◐ | Se toman y quedan en una carpeta de PNG; no llegan al expediente |
| Tareas programadas | ◐ | 5 tareas declaradas, 3 vivas, **todas corriendo en UTC**: las "3 de la mañana" son las 22:00 de Bogotá |
| Agentes residentes | ○ | No existe ninguno. Todo lo automático hoy es un script que alguien lanza |

**Qué puede hacer hoy.** Ejecuta muy bien la última milla y nada más. Los bots **no clasifican, no analizan, no generan respuestas y no guardan historial**: reciben un Excel que un humano ya resolvió y lo tipean en el portal. **El puente entre la mitad que piensa y la mitad que ejecuta es un archivo Excel que viaja en el escritorio de una PC.** Y el costo de no compartir núcleo está medido: el bot de SAVIA tiene un error contable que **multiplica por 100 los valores con decimales**, y EMSSANAR ya lo había corregido — el arreglo nunca llegó porque las ramas nunca se fusionaron. Tres sesiones arreglaron además los mismos dos problemas de integración continua con cuatro nombres distintos para el mismo helper.

**Agentes que la sirven.** *Vigilante* (carpetas), *Correo* (bandeja institucional, con Gmail y Outlook como simples adaptadores de un mismo canal), *Servidor* (archivos nuevos), *Radicación* (portales), *Constructor* (da de alta un pagador nuevo sin programar).

**Qué gana el hospital.** Que el pagador número 30 cueste lo mismo que el número 15: **una tarde de configuración de la coordinación, no un programa nuevo**. Y que la entrada del proceso deje de ser invisible: hoy, si nadie baja el lote a tiempo, el plazo corre igual.

---

#### Familia 4 · Inteligencia y Conocimiento

**Qué resuelve.** Lo que el sistema sabe: normas con su texto literal, contratos con sus cláusulas, precedentes propios del hospital, el estilo de cada auditor y el resultado real de cada pelea. Es el activo más difícil de reconstruir y hoy el peor guardado.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Base de conocimiento única | ○ | No existe. Hay **cuatro catálogos de normas** paralelos y dos corpus de 131 normas cada uno **que solo comparten 20 nombres** |
| Normatividad con texto literal y citas verificadas | ◐ | El corpus con el texto de los artículos existe y es oro; el validador de citas distingue norma inexistente, artículo fuera de norma y cita literal falsa. Pero **el panel que consulta el auditor devuelve palabras clave, no el texto del artículo** |
| Contratos como fuente de reglas | ◐ | La ficha real de las 14 EPS principales está **escrita en código** y **tiene prioridad sobre la base**: editar un contrato por pantalla es placebo |
| Búsqueda de precedentes propios | ◐ | Un buscador BM25 correcto y sin dependencias, **desperdiciado** detrás de un cortocircuito que devuelve siempre las plantillas de semilla |
| Búsqueda semántica | ◐ | No es semántica: es una búsqueda por coincidencia de texto con un modelo de lenguaje reordenando 80 filas, a costo de una llamada por búsqueda |
| Copiloto conversacional | ● | El Asistente Maestro, con 9 herramientas que consultan datos verdaderos. Es la única IA conversacional real del sistema |
| Memoria y aprendizaje | ○ | **El circuito no gira.** En la base hay 52 plantillas "ganadoras": las 52 son de semilla, 0 aprendidas, todas con `usos = 0` y sin fecha de último uso. Ganar o perder una conciliación no cambia nada en la generación futura |
| Ruteo de modelos y costo | ◐ | Dos enrutadores; el flujo principal no usa el oficial. De 12 puntos que llaman a la IA, **solo 1 registra el gasto** |

**Qué puede hacer hoy.** Redacta dictámenes buenos con conocimiento excelente y frágil: las ~15 reglas de defensa destiladas de 33 rondas de auditoría adversarial, el trío anti contrato-cruzado, la verificación de citas y el banco de respuestas del equipo jurídico. Todo eso vive en cadenas de texto de Python: **cuando cambia una norma, un contrato o el valor de la UVB anual —hoy repetido en más de 10 archivos— solo un programador puede actualizarlo**, tocando cuatro o cinco lugares coherentemente. El coordinador, que es quien sabe, no puede tocar nada.

**Agentes que la sirven.** *Normativo* (residente: vigila legislación y vigencias), *Asistente* (copiloto contextual en cada pantalla), *Glosas* (consume el conocimiento), *Auditor* (detecta contradicciones entre catálogos).

**Qué gana el hospital.** Que el conocimiento jurídico sea **un dato con vigencia, editable por quien sabe, y no un despliegue**. Y que el sistema aprenda de verdad: que un argumento que levantó una glosa vuelva al siguiente dictamen, y que uno que la EPS ratificó deje de usarse.

---

#### Familia 5 · Conciliación y Cartera

**Qué resuelve.** El final del embudo: la mesa con el pagador, el acta que se firma, la nota crédito, el saldo real y la plata que efectivamente entra. Es donde el trabajo del área se convierte en dinero — y hoy es donde el sistema se apaga.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Preparación de la audiencia | ◐ | Calcula contraargumentos probables y valor mínimo aceptable, y el auditor lo usa. Pero informa "N audiencias previas" contando algo que no son audiencias |
| Acta de conciliación | ◐ | El modelo es de lo mejor del sistema: ciclo bilateral y acta con cláusula de mérito ejecutivo. La tabla de conciliaciones tiene **0 filas**: la conciliación real del histórico —226 facturas, 4 actas, **$277.231.324 glosados y $71.901.424 aceptados**— vive en un archivo de texto separado por tabuladores |
| Acta multi-glosa sobre la plantilla oficial | ◇ | El generador del acta de las 147 facturas existe, con verificación dura del universo, en una rama con PR en borrador |
| Nota crédito y validación de CUV | ◐ | 8 scripts encadenados a mano, 2.682 líneas. Diagnóstico real: **6 de 12 facturas tenían como "CUV" el texto del error de conexión**, se subieron al portal y el registro decía "Subidas OK" |
| Saldo, antigüedad y recaudo | ◇ | Un tablero HTML alimentado por una planilla amarilla. **Cuatro definiciones distintas de saldo** y **tres particiones de antigüedad** (4, 6 y 7 rangos) en el mismo hospital |
| Circularización a reguladores | ◇ | Construido para responder un requerimiento de la Supersalud y **nunca ejecutado contra datos reales**; el NIT de la entidad objetivo tiene **tres valores en circulación** |
| Baja de cartera (Res. 577/2019) | ● | Genera el Word y el Excel exigidos, con un diseño honesto que declara qué **no** puede afirmar |
| Pago y cierre contable | ○ | No existe. Mientras la verdad del pago viva en una planilla, nadie puede responder cuánto se recuperó |

**Qué puede hacer hoy.** Prepara la audiencia y guarda el acta; no cierra la glosa ni suma al tablero. El acta firmada no transiciona el expediente ni escribe el valor recuperado: **para que la plata conciliada aparezca, el auditor debe registrar el resultado otra vez por otro camino**. Y la decisión más importante del ciclo —qué dijo la EPS— se captura hoy con un cuadro de texto libre.

**Agentes que la sirven.** *Conciliación* (reemplaza el Excel: analiza diferencias, arma el acta, calcula cartera), *Contabilidad* (nota crédito, CUV, cierre), *Auditor* (cuadra al peso antes de firmar).

**Qué gana el hospital.** Un solo número por pregunta, y el más importante de todos: **cuánto se defendió y cuánto se cobró**. Hoy esa pregunta no se puede responder porque los lotes radicados por bot no vuelven a la base.

---

#### Familia 6 · Contratos y Tarifas

**Qué resuelve.** La regla contra la que se mide cada peso: qué contrato aplica, con qué manual, con qué factor, en qué vigencia. Es el argumento que más glosas levanta y el que más rápido se cae si está mal citado.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Ficha de contrato por pagador | ◐ | **Tres catálogos divergentes** más una tabla que, verificada contra la base real, tiene **15 de sus 17 columnas vacías en las 13 filas existentes** |
| Cláusulas citables con número de página | ● | PDF del contrato → lectura nativa por el modelo → cláusula literal con tema y página → dictamen. Es la capacidad diferencial del producto |
| Tarifas contratadas cargadas por el auditor | ● | La única vía por la que el área carga datos contractuales sin programador, con parsers para los formatos reales del negocio |
| Evaluación determinista de glosas tarifarias | ● | 649 líneas sin costo de IA, endurecidas con casos reales. Es el 20 % que da el 80 % del valor en glosas de tarifa |
| Manuales tarifarios oficiales | ◐ | El liquidador promete el Manual SOAT y el catálogo tiene **4 códigos de ejemplo**; el ISS no existe |
| Homologación de códigos | ● | Tabla oficial de 10.024 CUPS → 2.919 SOAT comprimida, más homologación de CUPS por resolución vigente |
| Vigencia por fecha de atención | ○ | El contrato depende de **cuándo se atendió al paciente**, no de cuándo llegó la glosa. En el Dispensario, **372 de 444 glosas venían marcadas "SIN CONTRATO" teniendo contrato** |
| Alta de un contrato nuevo | ○ | **No existe formulario de creación.** El mensaje de error dice "créalo primero en la pestaña Contratos" y esa pestaña no tiene formulario |

**Qué puede hacer hoy.** Cita una cláusula exacta con su página —lo mejor que tiene el sistema— apoyada en una ficha de contrato que el usuario cree editar y no edita. Un contrato que se renueva exige un despliegue.

**Agentes que la sirven.** *Documental* (lee el PDF del contrato), *Normativo* (vigila vencimientos y prórrogas), *Glosas* (arma el bloque contractual del dictamen), *Auditor* (avisa cuando el contrato citado no corresponde a la fecha de atención).

**Qué gana el hospital.** Que la coordinación renueve un contrato o cambie un factor **desde una pantalla, con historial**, y que el dictamen del día siguiente lo use. Y que nunca más se defienda una factura con el contrato equivocado — un error que la EPS verifica en segundos.

---

#### Familia 7 · Auditoría y Prevención

**Qué resuelve.** La glosa más barata es la que no ocurre. Esta familia se ocupa de lo que pasa **antes**: auditar la cuenta antes de radicarla, validar los soportes, cruzar el XML, y medir si lo que el sistema predice se parece a lo que la EPS decide.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Pre-auditoría de la cuenta antes de radicar | ◇ | Línea base medida sobre **12.523 facturas: 7.840 listas (62,6 %), $38.646 millones**, con una palanca identificada de $1.245–1.256 millones que llevaría al 88,8 %. Huérfano y nunca ejecutado en el equipo del área |
| Auditoría de radicación multi-entidad | ● | 1.192 líneas con **perfiles declarativos en JSON**, librería estándar pura y pruebas. Es la mejor pieza de automatización del repositorio y el contrato de perfil que la 2.0 debe extender |
| Validación FURIPS / ADRES (canal SOAT) | ● | 3.096 líneas contra la circular vigente, con lectores de RIPS y factura electrónica |
| Auditoría de la glosa contra la base (sin IA) | ● | Detecta "sin contrato" cuando el contrato está cargado, "sin tarifa" cuando está en el catálogo, y objeciones mayores al excedente facturado. Único módulo que audita el **fondo** y no la forma |
| Predicción de ratificación | ◐ | **Tres predictores, ninguno validado.** El único que el usuario ve no consulta la base ni una vez: sus números son constantes escritas a mano y una lista de 5 EPS que no son las del HUS |
| Auditoría de devoluciones y cruce de XML | ◇ | Kit completo (verificar radicación, revisar XML, cruzar glosas, semáforo de vencimientos) construido y huérfano en un PR en borrador |
| Verificación adversarial del lote | ◇ | Varios agentes buscando fallas antes de radicar. Es la etapa que más calidad aporta y **la única que no dejó un solo dato estructurado** |

**Qué puede hacer hoy.** Auditar muy bien el canal SOAT-ADRES y la radicación, y muy poco lo demás. La capacidad que más dinero mueve —auditar las cuentas antes de radicarlas— está construida, cuantificada y **fuera del sistema**. Además, hay **16 a 29 facturas bloqueadas por un catálogo de pagadores incompleto, con un impacto declarado de $488 a $551 millones**: eso no es un problema de código, es un problema de configuración que hoy nadie puede resolver sin programador.

**Agentes que la sirven.** *Auditor* (residente: cruza fuentes y abre la tarea solo), *Calidad* (residente: vigila errores y contradicciones), *Documental* (verifica que el soporte exigido exista, en qué archivo y en qué página).

**Qué gana el hospital.** Dejar de pagar dos veces el mismo ciclo. Una devolución cuesta el trámite completo otra vez; prevenirla es el retorno más alto por línea de código de todo el mapa.

---

#### Familia 8 · Analítica y Dirección

**Qué resuelve.** Que el coordinador sepa qué está pasando hoy y que la gerencia sepa cuánto vale el área — con **un solo número por pregunta**, no con seis pantallas que dicen cosas distintas.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Métrica canónica (recuperado, cerrado, cartera) | ○ | No existe. La definición de "recuperado" cambia entre endpoints, y la constante que define qué glosa está cerrada **se redeclara 117 veces** |
| Tablero del coordinador | ● | La única pieza con valor gerencial real y demostrablemente usada, con auto-refresco |
| Informe ejecutivo mensual | ● | El único artefacto que un gerente puede llevar a una reunión |
| Mi desempeño (gestor) | ◐ | La misma información en tres lugares, con 15 llamadas separadas para pintar una sola pantalla |
| Respuesta a reguladores | ◇ | El generador del formato oficial existe, nunca corrió con datos reales, y el NIT objetivo está sin confirmar |
| Impacto real del área | ○ | No se puede calcular: lo que el bot radica no vuelve a la base |
| Almacén de estadísticas | ◐ | 11.341 líneas y 171 rutas, de las cuales **167 no tienen un solo llamador** — una fábrica de números contradictorios |

**Qué puede hacer hoy.** Producir muchos números y ninguna verdad. Hay **cuatro pantallas de reportes que muestran el mismo dato con distinto corte**; el propio código documenta que el usuario ya pidió consolidarlas y que la respuesta fue **agregar una quinta superficie sin eliminar ninguna**. Y de 77 informes construidos para el coordinador, 5 llegaron a tener pantalla: el coordinador no sabe que existen y sigue haciendo esos informes en Excel.

**Agentes que la sirven.** *Director de Operaciones* (el Brain en su rol de mando: qué está pendiente, qué venció, qué se detuvo, qué bot falló), *Supervisor* (vigila desvíos), *Auditor* (avisa cuando dos números del mismo hecho divergen).

**Qué gana el hospital.** Una sola cifra defendible ante la gerencia, la Supersalud y la revisoría fiscal — derivada del expediente, no de una planilla.

---

#### Familia 9 · Observabilidad

**Qué resuelve.** Saber si el sistema está bien, cuánto cuesta operarlo, quién hizo qué y de dónde salió cada número. Sin esto, ninguna decisión de apagar, escalar o confiar es defendible.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Salud del sistema | ◐ | **Seis endpoints de salud** para un sistema que usa uno; el "profundo" está roto por un error de importación y siempre responde "estado no verificable" |
| Costo de IA por expediente | ◐ | De 12 puntos que llaman a la IA, **1 registra**; los otros proveedores nunca registran. El panel de costos muestra un total que cubre un camino de un proveedor |
| Trazabilidad de acciones (auditoría legal) | ◐ | De 134 endpoints que modifican datos, **57 dejan rastro**; la columna de dirección IP existe y está prácticamente siempre vacía |
| Errores y secretos redactados | ● | El filtro de secretos y la redacción del cuerpo de las peticiones "porque puede contener glosas con datos de paciente" nacieron de una fuga real, fechada |
| Estado de los bots en vivo | ○ | Cero observabilidad durante la corrida: si el operador cierra la ventana, pierde el hilo |
| Linaje del dato | ○ | Cada módulo resolvió a mano su propio registro de origen; no hay servicio transversal |
| Panel de observabilidad | ◐ | Reporta números congelados con desviaciones de 3,5×, consulta un componente que siempre responde "removido", y recomienda configurar cosas que no hacen nada. **Peor que no tener panel** |

**Qué puede hacer hoy.** Contar bien los errores y mal todo lo demás. El caso más caro es el tablero de calidad que lee una tabla que **nunca se llena por diseño**: observabilidad ilusoria, que es más peligrosa que la ausencia de observabilidad porque el coordinador la cree.

**Agentes que la sirven.** *Calidad* (residente), *Supervisor*, *Sistemas* (operación).

**Qué gana el hospital.** Poder decir con evidencia qué cuesta cada dictamen, qué proceso está detenido y quién tocó qué — en un dominio donde el hospital debe **probar** que respondió dentro del plazo.

---

#### Familia 10 · Plataforma y Gobierno

**Qué resuelve.** Lo que sostiene todo lo anterior: quién entra, qué puede hacer, dónde viven los secretos, cómo se protege el dato del paciente, cómo se recupera un desastre y —lo más importante para este proyecto— **cómo se impide que la misma capacidad se construya dos veces**.

| Capacidad | Estado | Dónde está hoy |
|---|:--:|---|
| Identidad (login, 2FA) | ● | Sólido: contraseñas correctamente cifradas, validación en cada petición, límite de intentos. El segundo factor funciona y **su adopción es cero**: 0 de 24 usuarios |
| Permisos por rol | ◐ | **460 de 686 endpoints tratan a todos los usuarios igual**, y 67 de ellos escriben o borran. El listado del historial devuelve el nombre de **todos los pacientes** del hospital a cualquier usuario autenticado |
| Bóveda de credenciales de portales | ◐ | El mejor módulo de seguridad del repositorio: cifrado, falla cerrado, motivo obligatorio, auditoría hasta de los intentos fallidos. **No tiene una sola pantalla**, y el área sigue compartiendo las claves de ~122 entidades en un Excel |
| Cifrado de datos de paciente | ○ | El sistema **recomienda configurar la clave de cifrado y configurarla no cifra nada**: nadie llama a la función. Es una declaración de conformidad sin implementación |
| Respaldos | ◐ | Copia consistente diaria con rotación — **al mismo disco de la base**. Si se pierde la máquina, se pierden los dos |
| Esquema y migraciones | ◐ | **Tres mecanismos conviviendo**, incluidas ~500 líneas de migración a mano dentro del arranque que degradan sus errores a advertencia |
| Perfil compuesto (canal × pagador × hospital) | ○ | Hoy hay **tres o cuatro descripciones del mismo pagador** que nadie reconcilia. Y el perfil no es solo la EPS: un canal sirve a tres pagadores, y el ancho del número de factura es del hospital |
| Registro de Capacidades | ○ | No existe, y su ausencia es la causa raíz de todo este mapa: **39 archivos huérfanos**, dos bots para el mismo pagador construidos por dos sesiones que no se veían, y el propio protocolo de memoria común creado **tres veces en paralelo** |
| Constructor de capacidades y agentes | ○ | Dar de alta un pagador cuesta hoy una sesión de chat y un programa nuevo |

**Qué puede hacer hoy.** Autenticar bien y autorizar mal. Guardar secretos con excelencia y no dejar que nadie los use. Y opera sobre **1 vCPU y 1 GB de RAM con 2 GB de intercambio**, con la rama de producción **fuera de la integración continua**: el despliegue automático sube a producción código que nunca pasó las pruebas.

**Agentes que la sirven.** *Constructor* (da de alta capacidades, perfiles y agentes con piloto obligatorio), *Auditor* (detecta ramas huérfanas y capacidades duplicadas antes de la primera línea de código), *Sistemas*.

**Qué gana el hospital.** Cumplir de verdad la Ley 1581 en vez de declararlo. Y detener la hemorragia estructural: **ninguna capacidad se construye dos veces, porque el Registro lo dice antes de empezar.**

---

### 20.4 Tabla de madurez

Estado de cada capacidad y la épica del programa (§19) que la lleva a **disponible**. Las épicas: **E0** cimiento (seguridad, permisos, poda, esquema) · **E1** núcleo compartido y Registro de Capacidades · **E2** expediente y máquina de estados única · **E3** Motor Universal de objeciones · **E4** centro documental · **E5** perfil compuesto y multi-hospital · **E6** conocimiento en datos · **E7** pipeline único del dictamen y aprendizaje · **E8** radicación y agente local unificado · **E9** captura (correo y portales) · **E10** conciliación, acta y nota crédito · **E11** cartera y circularización · **E12** observabilidad y costo · **E13** interfaz y copiloto · **E14** constructor y evolución.

| Capacidad | Estado actual | Épica |
|---|---|:--:|
| **1 · Gestión de Glosas** | | |
| Recepción del lote y reparto a gestores | Disponible | E2 |
| Respuesta sin IA (texto fijo, tarifa-match) | Disponible | E7 |
| Respuesta con IA (dictamen) | Parcial (un método de 2.800 líneas, 32 parches en cascada) | E7 |
| Ratificación / segunda vuelta | Parcial (texto canónico copiado en 4 lugares) | E6, E7 |
| Control de calidad previo a radicar | Parcial (construido y apagado por bandera) | E7 |
| Radicación en portal | Parcial (6 bots, ninguna pantalla) | E8 |
| Seguimiento, plazos y escalamiento | Por construir (el reloj viene en una celda de Excel) | E2 |
| Devoluciones como proceso propio | Por construir | E2, E11 |
| **2 · Gestión Documental** | | |
| Lectura completa de documentos (PDF · OCR · visión) | Parcial (trunca a ~7.050 caracteres; 5 caminos distintos) | E4 |
| Índice documental y apertura del archivo | Parcial (indexa 144k archivos y muestra la ruta como texto) | E4 |
| Extracción de factura y de folios citables | Disponible | E4 |
| Generación única de documentos con consecutivo real | Parcial (4 plantillas; número aleatorio en el documento radicado) | E4 |
| Evidencias y expediente probatorio | Parcial (consecutivo pedido por chat) | E4, E8 |
| Versiones y papelera | Disponible | — |
| Firma con validez jurídica | Por construir (declarada, no implementada) | E0, E4 |
| Caja de herramientas documental (PDF · Office) | Huérfano (PR en borrador, 39 pruebas) | E4 |
| **3 · Automatización y Agentes** | | |
| Bots de portal como perfiles de un motor único | Parcial (4 vivos) + Huérfano (2 más) | E8 |
| Bot de escritorio contra el ERP | Parcial (nunca respondió una glosa real) | E8 |
| Motor Universal de conversión de objeciones | Huérfano (4 programas, 2.581 líneas, mismo archivo) | E3 |
| Correo institucional como entrada del proceso | Huérfano (revisión manual del 72 % al 8 %) | E9 |
| Monitor de carpetas y sincronización del share | Parcial (dos agentes locales distintos) | E8 |
| Lectura tolerante de Excel | Disponible (reimplementada en cada módulo) | E1 |
| Capturas de pantalla pegadas al expediente | Parcial (se toman, no llegan) | E4, E8 |
| Tareas programadas | Parcial (corren en UTC) | E0, E12 |
| Agentes residentes | Por construir | E9, E14 |
| **4 · Inteligencia y Conocimiento** | | |
| Corpus normativo único con texto literal | Parcial (2 corpus de 131 normas, 20 nombres en común) | E6 |
| Verificación de citas contra el corpus | Disponible | E6, E7 |
| Contratos como dato editable con vigencia | Parcial (el código gana a la base) | E6 |
| Búsqueda de precedentes propios | Parcial (motor correcto, cortocircuitado) | E7 |
| Búsqueda semántica | Parcial (no es semántica) | E6 |
| Copiloto conversacional | Disponible | E13 |
| Memoria y aprendizaje que gire | Por construir (52 plantillas, 0 aprendidas, 0 usos) | E7 |
| Ruteo y costo de IA gobernado | Parcial (se loguea, no se gobierna) | E12 |
| **5 · Conciliación y Cartera** | | |
| Preparación de audiencia | Parcial (una cifra mal etiquetada) | E10 |
| Acta que cierra la glosa y alimenta el tablero | Parcial (0 filas; la real vive en un archivo de texto) | E10 |
| Acta multi-glosa sobre plantilla oficial | Huérfano | E10 |
| Nota crédito y validación de CUV | Parcial (8 scripts; 6 de 12 CUV falsos) | E10 |
| Saldo, antigüedad y recaudo | Huérfano (4 definiciones de saldo, 3 de antigüedad) | E11 |
| Circularización a reguladores | Huérfano (nunca corrió con datos reales) | E11 |
| Baja de cartera (Res. 577) | Disponible | — |
| Pago y cierre contable | Por construir | E11 |
| **6 · Contratos y Tarifas** | | |
| Ficha única de contrato editable | Parcial (15 de 17 columnas vacías en la base) | E6 |
| Cláusulas citables con página | Disponible | — |
| Tarifas contratadas cargadas por el auditor | Disponible | — |
| Evaluación determinista de glosas tarifarias | Disponible | — |
| Manuales tarifarios completos (SOAT · ISS) | Parcial (4 códigos de ejemplo) | E6 |
| Homologación de códigos | Disponible | — |
| Vigencia por fecha de atención | Por construir (372 de 444 glosas mal marcadas) | E6 |
| **7 · Auditoría y Prevención** | | |
| Pre-auditoría de la cuenta antes de radicar | Huérfano (12.523 facturas medidas, $38.646 M) | E11 |
| Auditoría de radicación multi-entidad | Disponible (el contrato de perfil a extender) | E5 |
| Validación FURIPS / ADRES | Disponible | — |
| Auditoría de la glosa contra la base | Disponible | E7 |
| Predicción de ratificación validada | Parcial (3 predictores, ninguno validado) | E7 |
| Auditoría de devoluciones y cruce de XML | Huérfano | E11 |
| Verificación adversarial del lote | Huérfano (no deja dato estructurado) | E7 |
| **8 · Analítica y Dirección** | | |
| Métrica canónica del área | Por construir (constante redeclarada 117 veces) | E12 |
| Tablero del coordinador | Disponible | E12 |
| Informe ejecutivo mensual | Disponible | E12 |
| Mi desempeño | Parcial (misma info en tres lugares) | E13 |
| Respuesta a reguladores | Huérfano | E11 |
| Impacto real del área | Por construir | E12 |
| **9 · Observabilidad** | | |
| Salud real del sistema | Parcial (el panel miente) | E12 |
| Costo de IA por expediente | Parcial (1 de 12 puntos registra) | E12 |
| Trazabilidad legal de acciones | Parcial (57 de 134 mutaciones) | E0, E12 |
| Errores y secretos redactados | Disponible | — |
| Estado de los bots en vivo | Por construir | E8, E12 |
| Linaje del dato | Por construir | E12 |
| **10 · Plataforma y Gobierno** | | |
| Identidad y segundo factor | Disponible (adopción cero) | E0 |
| Autorización por permisos | Parcial (460 de 686 sin control) | E0 |
| Bóveda de credenciales con interfaz | Parcial (backend completo, interfaz cero) | E0 |
| Cifrado de datos de paciente | Por construir (declarado, no hecho) | E0 |
| Respaldos fuera del disco | Parcial (al mismo volumen) | E0 |
| Esquema y migraciones con una sola vía | Parcial (tres mecanismos) | E0 |
| Perfil compuesto (canal × pagador × hospital) | Por construir | E5 |
| Registro de Capacidades | Por construir | E1 |
| Constructor de capacidades y agentes | Por construir | E14 |
| Interfaz componentizada | Por construir (1 archivo, 23.125 líneas) | E13 |
| Bandeja priorizada como pantalla de inicio | Parcial (existe, no es el inicio) | E13 |

---

### 20.5 Mapa capacidad → quién la usa

Una capacidad sin dueño no se mantiene. Esta tabla asigna, por capacidad, quién la usa a diario y quién responde por ella.

| Capacidad | Auditor de glosas | Coordinador | Gerencia | Contabilidad | Sistemas |
|---|:--:|:--:|:--:|:--:|:--:|
| Expediente y línea de tiempo | ● uso diario | ● supervisión | ○ consulta | ○ consulta | — |
| Bandeja priorizada y plazos | ● uso diario | ● reparto y alertas | — | — | — |
| Respuesta con IA y sin IA | ● uso diario | ○ revisión | — | — | — |
| Control de calidad del dictamen | ● antes de radicar | ● aprueba el lote | — | — | — |
| Radicación en portal | ● lanza el lote | ● vigila la cola | — | — | ○ soporte |
| Correo institucional (entrada) | ● entrada del día | ● reparto | — | — | ○ buzón |
| Índice documental / abrir el soporte | ● uso diario | ○ | — | ○ sustento | ● share |
| Evidencia y expediente probatorio | ● arma | ● firma | — | ○ | — |
| Contratos y tarifas | ● consulta | ● **edita** | ○ | ○ | — |
| Normatividad con texto literal | ● consulta | ● **cura** | — | — | — |
| Conciliación y acta | ● prepara | ● **audiencia** | ○ | ● cierre | — |
| Nota crédito y CUV | ○ | ● | — | ● **dueña** | ○ desbloqueo |
| Saldo, antigüedad y recaudo | — | ● | ● **decisión** | ● | — |
| Circularización a reguladores | — | ● | ○ | ● **dueña** | — |
| Baja de cartera (Res. 577) | — | ○ | ● | ● **dueña** | — |
| Pre-auditoría de la cuenta | ● | ● | ○ | — | — |
| Auditoría de devoluciones | ● | ● | — | ○ | — |
| Tablero e informe ejecutivo | — | ● | ● **destinatario** | ● | — |
| Impacto real del área | — | ● | ● **decisión** | ● | — |
| Observabilidad y salud | — | ○ | — | — | ● **dueño** |
| Costo de IA | — | ● techo | ● presupuesto | ○ | ● |
| Bóveda de credenciales | ○ con motivo | ● autoriza | — | — | ● **custodia** |
| Roles y permisos | — | ● solicita | — | — | ● **dueño** |
| Cifrado y protección de datos | — | ○ | ○ riesgo legal | — | ● **dueño** |
| Respaldos y recuperación | — | — | ○ riesgo | — | ● **dueño** |
| Alta de pagador (perfil compuesto) | — | ● **la hace** | — | — | ○ apoyo |
| Registro de Capacidades | — | ● consulta | — | — | ● **dueño** |

● responsable o usuario principal · ○ consulta ocasional · — no le corresponde

**Cuatro lecturas que cambian el diseño.**

1. **El auditor vive en cinco capacidades y solo cinco**: expediente, bandeja, respuesta, evidencia y radicación. Todo lo demás que hoy le ocupa pantalla es ruido — y hoy le ocupan **26 paneles**, con pantallas que llevan meses devolviendo error y ítems de menú cuyo backend fue borrado.
2. **El coordinador es el único rol que edita conocimiento** (contratos, normas, perfiles, plantillas). Hoy no puede: ese conocimiento vive en código y cada corrección exige un programador y un despliegue.
3. **Contabilidad es dueña de tres capacidades que hoy no están en ningún sistema** (nota crédito, circularización, cierre). Por eso el cierre contable depende de planillas mantenidas a mano — y por eso 6 de 12 facturas figuraban como "subidas OK" cuando ninguna tenía CUV válido.
4. **Sistemas custodia la única joya de seguridad terminada y sin pantalla.** Mientras la bóveda no tenga interfaz, las claves de ~122 portales seguirán viajando en un Excel: es la mayor ganancia de cumplimiento por línea de código de todo el mapa.

---

### 20.6 El sistema en una página

```
                        ┌───────────────────────┐
                        │      EL AUDITOR       │
                        │   decide · aprueba    │
                        └───────────┬───────────┘
                                    │ pide y confirma
                                    ▼
     ┌──────────────────────────────────────────────────────────────┐
     │                        SINAC BRAIN                           │
     │        entiende lo que hace falta y arma el plan             │
     └──────────────────────────────┬───────────────────────────────┘
                                    │
   ┌──────────────┬─────────────────┼─────────────────┬─────────────┐
   │              │                 │                 │             │
   ▼              ▼                 ▼                 ▼             ▼
┌────────┐  ┌──────────┐  ╔══════════════════╗  ┌──────────┐  ┌──────────┐
│ ENTRA  │  │ SE       │  ║                  ║  │ SE       │  │ SE       │
│        │  │ ANALIZA  │  ║   EXPEDIENTE     ║  │ RADICA   │  │ CONCILIA │
│ correo │  │          │  ║                  ║  │          │  │          │
│ portal │─►│ contrato │─►║  la factura      ║─►│ portal   │─►│ acta     │
│ Excel  │  │ norma    │  ║  como objeto     ║  │ evidencia│  │ nota     │
│ PDF    │  │ tarifa   │  ║  vivo que        ║  │ radicado │  │ crédito  │
│ carpeta│  │ historia │  ║  nunca muere     ║  │          │  │ pago     │
└────────┘  └──────────┘  ║                  ║  └──────────┘  └──────────┘
                          ║  estado · plazos ║
                          ║  eventos         ║
                          ║  documentos      ║
                          ║  decisiones      ║
                          ║  responsables    ║
                          ╚═════════╤════════╝
                                    │ todo queda registrado
                                    ▼
     ┌──────────────────────────────────────────────────────────────┐
     │   MEMORIA — normas · contratos · precedentes · aprendizaje    │
     └──────────────────────────────────────────────────────────────┘

   Los AGENTES trabajan solos alrededor del expediente, día y noche:
   correo · carpetas · servidor · normativa · calidad · auditoría · plazos
```

**En una frase:** el auditor decide, el Brain organiza, los agentes ejecutan y **todo queda pegado al expediente de la factura** — que es lo único que el hospital tiene que poder mostrar cuando alguien pregunte qué pasó con esa plata.

---

### 20.7 Contrato de cierre — Mapa de Capacidades

#### 1. ¿Qué existe actualmente?

**No existe ningún mapa de capacidades.** Lo que existe son cinco sustitutos parciales, y ninguno responde la pregunta *"¿esto ya existe?"*:

- **El menú de la aplicación** (26 paneles en el frontend). Es lo más parecido a un índice de lo que el sistema hace, y miente: hay pantallas visibles cuyo backend fue eliminado, **22 direcciones que el frontend invoca y que no existen en el servidor**, y tres pantallas completas —con estilos y endpoints vivos— a las que **ningún usuario puede llegar** por ningún camino.
- **El blueprint del cliente** (`docs/SINAC_OS.md`), que lista 9 módulos y 8 agentes. Es la intención correcta y no describe lo construido.
- **Los ~20 documentos de entrega de los módulos externos**, cada uno con su propio inventario, sus pendientes y su bitácora. Ninguno sabe de los otros: por eso hay dos bots para el mismo pagador nacidos de la misma petición literal, y un extractor inverso construido dos veces —una de las dos versiones tirada a la basura.
- **`BITACORA.md`**, la única razón por la que este proceso se puede reconstruir con evidencia. Es memoria narrativa, no registro consultable.
- **Los tres `CONTEXTO_*.md`**, que el auditor **copia y pega como primer mensaje de un chat** cada vez que retoma un flujo. La "memoria" del proceso es hoy un ritual de copiar y pegar.

La consecuencia es medible: **39 archivos de módulos terminados, probados y con integración continua en verde**, esperando en ramas con PR en borrador; **142 duplicaciones** identificadas; y el propio protocolo de memoria común creado **tres veces en paralelo**, chocando en vivo el mismo día. El mecanismo diseñado para impedir la dispersión del conocimiento se dispersó él mismo.

#### 2. ¿Qué se reutiliza?

- **Los inventarios ya producidos**: las 15 auditorías sobre el código real (304 módulos, 142 duplicaciones, 166 hallazgos de experiencia de usuario) y las fichas de los 75 módulos externos. Son la línea base del mapa y **están verificados contra archivo y línea**: el mapa no se levanta de cero, se **carga**.
- **El veredicto por módulo ya emitido** (mantener · simplificar · fusionar · eliminar · automatizar · reescribir). Es la semilla del campo *estado* de cada capacidad.
- **El contrato de perfil que ya funciona**: el radicador multi-entidad con sus 12 entidades en un archivo de datos editable sin tocar código. El perfil compuesto **extiende** ese contrato, no lo reinventa.
- **Las cifras de control del área** (universo del Dispensario, acta de las 147 facturas, lotes de COOSALUD, línea base de pre-auditoría): son la red de regresión de toda migración y ya están producidas.
- **La convención de estados de los módulos externos** ("fusionado / parcialmente fusionado / huérfano / muerto pero recuperable"), verificada con Git y no con documentos. Es exactamente la semántica que el mapa necesita.

#### 3. ¿Qué se elimina?

- **El menú como inventario de capacidades.** Deja de ser la respuesta a "qué hace el sistema": el menú se **deriva** de las capacidades disponibles para el rol de quien mira. Una capacidad sin estado *disponible* no puede tener entrada de menú — y eso hace estructuralmente imposible el panel visible con el backend borrado.
- **Los inventarios en prosa por módulo.** Los ~20 documentos de entrega se conservan como memoria histórica y **dejan de ser el registro**: sus filas se cargan al Registro y ahí termina su vida operativa.
- **Las tres bitácoras paralelas como registro de módulos.** Se conserva una sola, en su función correcta: memoria de decisiones fechada, escrita para un auditor de cartera.
- **La costumbre de nombrar capacidades por pagador.** Desaparecen "módulo FOMAG", "módulo SAVIA", "módulo COOSALUD": quedan capacidades con perfiles. La prueba de que la eliminación se cumplió es automática y verificable: **ningún nombre de pagador puede aparecer en el identificador de una capacidad**.
- **La respuesta "agreguemos otra pantalla".** Documentada en el propio repositorio: se pidió consolidar cuatro pantallas de reportes y la respuesta fue añadir una quinta sin eliminar ninguna. El Registro no permite dos capacidades sobre el mismo dominio.

#### 4. ¿Qué se crea?

Todo lo que sigue pasó por el **Principio Nº 1**: se buscó primero como capacidad del núcleo y se demostró que no existe.

- **El Registro de Capacidades.** *Prueba de inexistencia:* se buscó en la aplicación, en las herramientas, en la documentación y en las ramas; lo más parecido son los documentos de entrega y las tres bitácoras, que son prosa y no se consultan antes de escribir código. *Por qué es del núcleo:* no sirve a una capacidad, **sirve a todas**, y es la única defensa estructural contra la duplicación. Se implementa como dato consultable con una pregunta obligatoria antes de crear: *¿esto ya existe?*
- **El estado derivado.** El estado de una capacidad no se escribe: se calcula a partir de si tiene código propietario, prueba verde, usuario real y ruta viva. Una capacidad que pierde su prueba **baja de estado sola**; una cuyo endpoint deja de tener consumidor pasa a *parcial* sin que nadie lo decida.
- **El detector de duplicación por dominio.** Dos capacidades no pueden reclamar el mismo dominio de negocio. Es la regla que habría impedido cuatro conversores del mismo archivo y dos bots para el mismo pagador.
- **La prueba de contrato interfaz↔servidor.** Cada capacidad *disponible* debe demostrar que su entrada de menú resuelve a una ruta registrada. Es la respuesta directa a las 22 direcciones inexistentes y a los dos paneles rotos y visibles.
- **El mapa como artefacto publicado.** Este documento se **genera** desde el Registro. Si el manual y el sistema divergen, **falla la integración continua**: es la única garantía de que la fuente de verdad no envejezca.

#### 5. ¿Cómo se migra sin romper el sistema?

El sistema está **en producción** sobre 1 vCPU y sostiene un área que recupera plata todos los meses. El mapa es la capa menos riesgosa del programa —no toca datos ni flujos— pero su carga sí puede desordenar el trabajo si se hace mal.

1. **El Registro nace en modo lectura.** Primero cataloga, no gobierna. Se cargan las 68 capacidades con su estado derivado y se comparan contra las auditorías; las divergencias se resuelven antes de que el Registro bloquee nada.
2. **Se poda antes de catalogar.** Las ~21.000 líneas muertas se borran primero, con triple prueba de no-uso (sin referencia en la interfaz, sin referencia en la aplicación, sin referencia en las herramientas). Catalogar código muerto es catalogar deuda.
3. **La red de seguridad se audita antes de usarse.** Las 4.266 pruebas existen, y hay pruebas que llevan meses en verde sobre errores reales —una verifica que un diccionario sea un diccionario sobre un diccionario que siempre está vacío. Antes de que el estado de una capacidad dependa de su prueba, se verifica que la prueba comprueba el **valor** y no la forma.
4. **El bloqueo se enciende por familia, no de golpe.** El Registro empieza bloqueando altas duplicadas solo en la familia que se esté trabajando; se extiende a la siguiente cuando la anterior está estable.
5. **Nada se declara *disponible* sin demostración.** El criterio es el que el área ya practica: piloto de un caso con navegador visible → lote completo → segunda pasada de verificación con cero pendientes. Esa disciplina, que ya existe, se convierte en la definición de hecho.
6. **El modo de trabajo actual sobrevive todo el programa.** La línea de comandos de los bots sigue existiendo mientras se construye la interfaz encima. En ningún momento el área se queda sin su herramienta más productiva.
7. **Las ramas quedan gobernadas desde el primer día.** Un PR en borrador con integración en verde y sin dueño durante una semana **se fusiona o se cierra**. Es la causa raíz de los 39 archivos huérfanos y se corta antes de catalogar nada más.

---

### 20.8 Ficha técnica de construcción — Mapa y Registro de Capacidades

**Estructura de carpetas**

```
nucleo/capacidades/
  registro.py            alta, búsqueda, veredicto de duplicación por dominio
  estado.py              cálculo del estado derivado (disponible/parcial/huérfano/por construir)
  dominio.py             taxonomía de familias y dominios; prohíbe nombres de pagador
  mapa.py                render del mapa (árbol, madurez, matriz de uso)
datos/capacidades/
  familias.yaml          las 10 familias, su propósito y su dueño de negocio
  capacidades.yaml       una fila por capacidad: nombre · familia · dominio · dueño ·
                         estado declarado · pruebas · ruta · reemplaza_a · perfil aplicable
  roles.yaml             matriz capacidad → rol (uso principal / consulta / no aplica)
```

**Servicios**

| Servicio | Responsabilidad |
|---|---|
| `RegistroCapacidades` | Responde *¿esto ya existe?* antes de que alguien escriba código. Bloquea el alta de una capacidad cuyo dominio ya esté tomado y exige `reemplaza_a` cuando la nueva sustituye a otra. |
| `EstadoCapacidad` | Deriva el estado real cruzando propietario declarado, resultado de pruebas, existencia de ruta y existencia de consumidor. Nunca acepta un estado escrito a mano. |
| `MapaCapacidades` | Publica el árbol, la tabla de madurez y la matriz capacidad→rol. Es la fuente del menú de la interfaz. |
| `DeteccionDuplicados` | Compara capacidades nuevas contra el registro por dominio, por nombre normalizado y por firma de entradas/salidas. |

**API**

```
GET  /capacidades                     el mapa completo, con estado derivado
GET  /capacidades/buscar?dominio=…    ¿esto ya existe? — obligatorio antes de crear
GET  /capacidades/{id}                ficha: familia · dueño · estado · pruebas · perfiles
POST /capacidades                     alta; rechaza dominio duplicado y nombres de pagador
GET  /capacidades/familias/{f}        ficha de familia con sus capacidades y agentes
GET  /capacidades/por-rol/{rol}       lo que ese rol puede hacer — alimenta el menú
GET  /capacidades/madurez             tabla de madurez con la épica que completa cada una
GET  /capacidades/huerfanas           lo construido y no entregado, con su rama y su PR
```

**Eventos**

*Publica:* `capacidad.registrada` · `capacidad.duplicada.detectada` · `capacidad.estado.cambiado` · `capacidad.degradada` (perdió su prueba o su consumidor) · `capacidad.huerfana.detectada`.

*Consume:* `prueba.fallida` y `prueba.superada` (recalculan estado) · `despliegue.realizado` (revalida rutas vivas) · `rama.actualizada` (detecta huérfanos) · `epica.cerrada` (promueve capacidades a *disponible*).

**Dependencias**

Solo el núcleo: eventos, seguridad y observabilidad. **Cero dependencias nuevas de terceros** — requisito, no casualidad: en un hospital donde instalar una librería requiere permisos de sistemas, cada dependencia es una herramienta que no se usa.

**Interfaz**

Una pantalla, tres vistas: **Mapa** (el árbol con su semáforo, filtrable por familia y por rol), **Ficha** (qué resuelve, quién la usa, qué la sirve, qué prueba la sostiene) y **¿Existe?** (el buscador obligatorio antes de pedir algo nuevo, que devuelve la capacidad más cercana y su dueño). Sin porcentajes de avance: una capacidad está disponible o no lo está.

**Base de datos**

`capacidades` (con `reemplaza_a` como autorreferencia y `dominio` con restricción de unicidad) · `capacidad_familia` · `capacidad_prueba` · `capacidad_rol` · `capacidad_estado_historico` (con `vigencia_desde`, para que el avance del programa sea auditable) · `capacidad_perfil`. Todas cubiertas por migraciones versionadas desde su creación.

**Skills / Workers / Agentes relacionados**

*Skills:* `buscar_referencias`, `contar_lineas`, `leer_repositorio`, `comparar_dominios`. *Workers:* `repositorio` (estado de ramas y PR), `pruebas` (resultado de la suite), `office` (exporta el mapa a Excel para la gerencia). *Agentes:* **Auditor** (detecta capacidades duplicadas, ramas huérfanas y capacidades degradadas, y abre la tarea solo), **Constructor** (consulta el Registro antes de dar de alta cualquier cosa) y **Asistente** (responde en lenguaje natural "¿el sistema puede hacer X?" recorriendo el mapa).

**Pruebas**

`test_dominio_unico` (dos capacidades no pueden reclamar el mismo dominio) · `test_sin_nombre_de_pagador` (ningún identificador de capacidad contiene un nombre de EPS) · `test_estado_no_se_escribe_a_mano` · `test_capacidad_disponible_tiene_ruta_viva` (la prueba que habría evitado los dos paneles rotos y las 22 rutas inexistentes) · `test_menu_deriva_del_registro` · `test_huerfano_genera_tarea` · `test_mapa_y_manual_coinciden` (si el documento y los datos divergen, falla la integración continua).

**Documentación**

Este capítulo es la fuente del formato; **el contenido se genera desde los datos**. El árbol, la tabla de madurez y la matriz capacidad→rol de este documento se publican desde el Registro: no pueden desincronizarse sin romper el CI.

---

### 20.9 Ficha de evolución a 5 años — Mapa de Capacidades

**Cómo se amplía.** El mapa no crece por acumulación: crece por **admisión**. Una necesidad nueva entra por el buscador *¿esto ya existe?*; si existe, se extiende la capacidad y se registra el nuevo perfil; si no existe, pasa por el Procedimiento de Admisión al Núcleo y recién entonces se le busca interfaz, agente o automatización. **El Principio Nº 1 deja de ser una regla escrita y pasa a ser una puerta de software.**

**Nuevos hospitales.** El mapa es el mismo para todos; lo que cambia es el **perfil de hospital** (prefijo y ancho del número de factura, raíces documentales, calendario institucional, consecutivos, textos institucionales, ERP de destino) y su catálogo de pagadores. Una instalación nueva no migra nada: nace con las capacidades ya *disponibles* y con las huérfanas ya integradas. La prueba de que el producto es multi-hospital es concreta y verificable en el código: **cero literales de nombre del hospital, de su NIT, de sus unidades de red y de sus consecutivos dentro de una capacidad.**

**Nuevos procesos.** El mapa tiene diez familias y espacio para más. Un proceso nuevo del hospital —facturación electrónica, respuesta a tutelas, auditoría concurrente, cobro coactivo— entra como **familia nueva sin tocar la arquitectura**: reutiliza expediente, eventos, documentos, reglas y conocimiento, y aporta sus propios agentes y perfiles. La señal de que la arquitectura aguantó es que la familia nueva **no obligue a crear un dominio nuevo del núcleo**. Si lo obliga, apareció una capacidad genuina y debe demostrarlo.

**Nuevos agentes.** Con el Constructor, dar de alta un agente deja de ser un proyecto y pasa a ser una configuración con piloto obligatorio. Proyección razonable: de 7 residentes en el año 1 a 15-20 en el año 5, **sin que el núcleo crezca proporcionalmente**, porque los agentes nuevos consumen Workers y Skills que ya existen. El mapa lo hace visible: cada familia declara qué agentes la sirven, y un agente que no sirve a ninguna capacidad del mapa no se aprueba.

**Nuevos perfiles.** El perfil compuesto (canal × pagador × hospital) ya soporta las cinco operaciones que hoy comparten un solo formulario y son cinco negocios distintos: portal con bot, portal sin bot, correo y conciliación interadministrativa (régimen especial), ARL con régimen propio, y SOAT/ADRES con expediente completo. **Un régimen nuevo se declara; no se programa.**

**Nuevos documentos.** El Centro Documental clasifica por perfil de documento, no por lista cerrada. Un formato nuevo entra como adaptador de lectura de uno de los tres tipos que ya existen (Excel plano por alias, PDF tabular por geometría, registro canónico). Si no encaja en ninguno, esa es la señal de que hace falta un cuarto: decisión de arquitectura, con su prueba de inexistencia.

**Lo que debe seguir siendo verdad en 2031.** Cinco invariantes, cada una con su prueba en la integración continua desde el año 1:

1. **Ninguna capacidad lleva el nombre de un pagador adentro.**
2. **El conocimiento jurídico vive en datos con vigencia, no en código.**
3. **El estado de una objeción lo escribe el sistema, nunca una persona.**
4. **Toda pieza tiene propietario declarado en el Registro.**
5. **Ninguna capacidad se construye dos veces** — y si alguien lo intenta, el Registro se lo dice antes de la primera línea.

**El indicador que resume los cinco años.** Hoy, dar de alta un pagador cuesta una sesión de chat y un programa nuevo: la prueba son cuatro conversores de 2.581 líneas escribiendo el mismo archivo y dos bots construidos para el mismo pagador por dos sesiones que no se veían. En 2031 ese costo debe ser **una tarde de configuración de la coordinación, sin desarrollador**. Y el mapa debe poder demostrarlo solo: cero capacidades huérfanas, cero capacidades disponibles sin prueba, y el número de familias creciendo mientras el número de dominios del núcleo se mantiene estable. Si en cinco años ese indicador no bajó, esta arquitectura no sirvió, por elegante que se vea el diagrama.
