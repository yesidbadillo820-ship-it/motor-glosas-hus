# Registro de cambios

## Sesión 26-ago-2026 (piloto) — el número es del renglón, y las copias de Windows en su sitio

Dos cosas que salieron al correr el piloto sobre la HUS311371 de CAROLINA, que
trae `HC.pdf` y `HC (2).pdf`:

**1. El número es del RENGLÓN, no del archivo.** El área lo dijo claro: dos
historias clínicas son las dos el renglón 2, y en la carátula del folio va un
solo «2. HISTORIA CLINICA». Antes salían «2 HISTORIA CLINICA.pdf» y
«3 HISTORIA CLINICA.pdf», que en la carátula se leían como dos renglones
distintos. Ahora la segunda queda «2 HISTORIA CLINICA (2).pdf».

**2. El original quedaba de último.** Windows nombra los repetidos `HC.pdf`,
`HC (2).pdf`, `HC (3).pdf`, pero con el orden natural a secas «HC (2)» va antes
que «HC.» —el espacio pesa menos que el punto— así que el orden salía
`HC (2) → HC (3) → HC (10) → HC`. `clave_orden()` lo pone en su sitio.

Las dos comprobadas con el caso real y estables en tres corridas seguidas.

**3. La pantalla mentía sobre el nombre repetido.** En el piloto real, las dos
historias clínicas salían listadas las dos como «2 HISTORIA CLINICA.pdf», como
si la segunda hubiera pisado a la primera. En disco quedaban bien —
«2 HISTORIA CLINICA.pdf» y «2 HISTORIA CLINICA (2).pdf»— porque el «(2)» lo
resolvía `nombre_libre` al momento de renombrar, después de imprimir el
listado. Ahora `nombres_en_orden()` calcula el nombre definitivo ANTES, así que
la pantalla y el reporte muestran exactamente lo que va a quedar en la carpeta.

153 pruebas en el archivo.


## Sesión 26-ago-2026 (tarde) — la revisión adversarial: pérdida de datos y cuatro defectos más

Se pasó el bot de folios por una revisión con cinco lentes distintas —colisiones
de nombres, idempotencia, pérdida de archivos, Windows/SMB, contratos—, y cada
hallazgo se puso a dos escépticos que tenían que reproducirlo contra el código
real. Salieron 31; estos son los que se confirmaron y se arreglaron.

**1. PÉRDIDA DE DATOS: el folio pisaba la epicrisis de verdad.** El folio se
llama igual que el archivo del que sale (`..._EPICRIS.pdf`). Para distinguirlos
el bot miraba si la carpeta traía archivos numerados; en una carpeta donde el
auditor ya había numerado algo a mano —que es lo que pide la hoja del área— la
epicrisis DE VERDAD se tomaba por folio viejo, se dejaba fuera del folio y se
pisaba. Comprobado: epicrisis de 5 páginas → tras UNA corrida, esa ruta tenía un
folio de 4 páginas sin la epicrisis y la epicrisis no existía. Sin respaldo.

La heurística se reemplaza por un hecho: el bot **firma** los PDF que escribe
(`/Producer`) y reconoce los suyos por esa firma. Lo que no la lleva es un
soporte y se trata como tal — que era lo correcto: la epicrisis entra al folio y
se renombra, y con eso queda libre el nombre. Se quitan `_RE_NUMERADO`,
`_grupos_ya_numerados` y `folios_dudosos`. Candado extra: si en la ruta del
folio hay algo sin firma, no se arma ese folio y se avisa.

**2. Las notas crédito no se reconocían con el nombre del hospital.** Vienen
como `NC_263272_HUS352904.pdf`; caían en OTROS del folio CLÍNICO y el reporte
seguía diciendo que faltaban. Se agregan `NC` y `NOTA ELECTRONICA`, comprobando
que no disparan falsos positivos (`HC`, `RESONANCIA`, `INCAPACIDAD`, `NTE-C`).

**3. El folio cambiaba de orden entre corridas.** El nombre que escribe el
propio bot, `3 HISTORIA CLINICA - TERAPIAS.pdf`, se releía como HISTORIA a
secas, porque «HISTORIA CLINICA» es más larga que «TERAPIAS» y ganaba. El
soporte cambiaba de grupo y se renumeraba. Ahora HISTORIA CLINICA es un grupo
**genérico**: cualquier grupo más preciso le gana. Igual para curaciones,
evoluciones y procedimientos.

**4. El detallado del bot hermano no se reconocía.**
`dividir_detallado_por_factura.py` lo deja como `HUS352904.xlsx`, el número y
nada más: nunca se pasaba a PDF y no entraba al folio.

**5. Un soporte dañado desaparecía del folio en silencio.** Se omitía, el folio
se armaba sin él y en pantalla decía «armado». Ahora sale avisado: «OJO, N
soporte(s) NO entraron al folio».

Y dos candados más de robustez: una copia fallida de la factura, o un archivo
bloqueado al renombrar con `--renombrar`, ya no tumban las otras 323 facturas.

### Y seis más, de la misma revisión

**6. Una FECHA pasaba por NIT.** `prefijo_del_nombre` solo pedía «números al
principio y esta factura después», así que `20240913_HUS352904 EVOLUCION.pdf`
daba NIT `20240913` y el folio salía llamándose `20240913_HUS352904_EPICRIS.pdf`.
Ahora se exige el nombre completo del ADRES (`<NIT>_<FACTURA>_<TIPO>`) y nada
más; un número de ingreso o una fecha ya no cuelan.

**7. `--mapa-nombres` dependía del orden del JSON.** Con
`{"TAC": …, "TAC DE TORAX": …}` ganaba la primera línea escrita, no la palabra
más larga. Ahora gana la más larga, como en el diccionario de siempre.

**8. El reporte abierto en Excel tumbaba la corrida.** En Windows el CSV no se
deja escribir si está abierto; el traceback llegaba **después** de armar todos
los folios. Ahora se avisa y el trabajo no se pierde.

**9. `--renombrar` dejaba a medias la carpeta.** Numeraba el folio clínico pero
no el de la factura, y el CSV prometía renglones que nadie armaba.

**10. Las banderas que no hacen nada sin `--folio`** (`--carpeta-facturas`,
`--prefijo`, `--convertir-detallado`) se ignoraban en silencio: el auditor creía
que había traído las facturas. Ahora avisan.

**11. Los archivos que no son PDF desaparecían sin avisar.** Una epicrisis en
Word o una radiografía en JPG no entran al folio, pero tampoco pueden
esfumarse: salen listadas en pantalla y en el reporte. La basura de Windows
(`Thumbs.db`, `desktop.ini`) no se reporta.

### Y el último grupo: lo que deja una corrida que se cae a mitad

El renombrado va en dos vueltas —primero a un nombre de paso `~renombrando~…`,
porque el nombre que le toca a un archivo puede ser el que todavía tiene otro—.
Si la corrida se caía en medio, eso dejaba dos destrozos:

**12. Un `~renombrando~HC.pdf` colgado se PERDÍA en la corrida siguiente.** El
nombre de paso se armaba con `ruta.with_name(...)` a secas, así que al renombrar
`HC.pdf` se pisaba el huérfano. Comprobado: un huérfano de 7 páginas
desaparecía y la carpeta quedaba con un `~renombrando~~renombrando~HC.pdf` y sin
folio. Ahora el nombre de paso se pide libre (`nombre_libre`), y
`sanar_temporales()` le devuelve su nombre a lo que quedó colgado antes de
empezar: el huérfano de 7 páginas se recupera y entra al folio.

**13. No había vuelta atrás.** Si la segunda vuelta fallaba, los archivos
quedaban como `~renombrando~…` para siempre y la factura sin folio. Ahora se
deshace: cada uno vuelve al nombre que tenía, y la corrida siguiente arma el
folio sin ayuda.

**14. `--renombrar` borraba el NIT sin decirlo.** Al numerar, el nombre que lo
traía (`680010079201_HUS######_EPICRIS.pdf`) desaparece, y después no hay de
dónde sacarlo: los folios salían como `HUS######_EPICRIS.pdf`. Ahora avisa con
el NIT que encontró, para pasarlo con `--prefijo`.

En simulación los huérfanos no entran al folio pero sí salen en el reporte.

149 pruebas en el archivo. Se comprobó además que quedaron cerrados los otros
dos confirmados: `--renombrar` y después `--folio` ya no destruye el PDF de la
factura (19 páginas intactas), y una carpeta con punto y espacios
(`HUS379477_PEND. CARTA CORONEL`) da el mismo folio en tres corridas seguidas.


## Sesión 26-ago-2026 — los DOS folios de cada factura (`--folio`)

El área aclaró cómo es el folio completo, y son **dos PDF por factura**, no uno:

- **`<NIT>_<FACTURA>_EPICRIS.pdf`** — el nombre que queda **después** de unir
  los soportes numerados (`1 RESPUESTA A GLOSA`, `2 EPICRISIS`,
  `3 HISTORIA CLINICA`, `4 AYUDAS DIAGNOSTICAS`, `5 OTROS`).
- **`<NIT>_<FACTURA>_FACTURA.pdf`** — la factura sí entra al folio, con su
  propio orden adentro: **1 FACTURA · 2 DETALLADO (el Excel pasado a PDF) ·
  3 REPRESENTACIÓN GRÁFICA DIAN · 4 NOTAS CRÉDITO**.

Lo que se agregó a `unir_soportes_adres.py`:

- **`--folio`**: numera los soportes y arma los dos PDF. Numerar primero no es
  adorno — es lo que **deja libre el nombre del folio**, porque ese nombre es
  justo el que traían la epicrisis y la factura antes de renombrarlas.
- **Cuatro renglones nuevos** (`GRUPOS_FACTURA`) con sus palabras: FACTURA,
  DETALLADO, REPRESENTACIÓN GRÁFICA DIAN y NOTAS CRÉDITO. Los trece grupos
  clínicos quedaron igual.
- **`--carpeta-facturas`**: trae a cada carpeta su
  `680010079201_HUS######_FACTURA.pdf` desde `4.FACTURAS CON XML\XML`. No pisa
  la que ya estuviera.
- **`--convertir-detallado`**: pasa a PDF el detallado que esté en Excel,
  reusando el motor de `excel_a_pdf.py`. Si el equipo no tiene ni Excel ni
  LibreOffice, lo deja anotado y sigue.
- **`--prefijo`**: el NIT del nombre. **No se inventa**: sale del nombre de los
  propios archivos; esta opción solo llena las carpetas donde ninguno lo trae.
- **Las notas crédito quedan PENDIENTES a propósito** — todavía no las han
  sacado, así que no se cuentan como falta. Cuando lleguen, se dejan en la
  carpeta y se vuelve a correr: entran solas de cuartas.
- **La simulación muestra el folio como va a quedar de verdad**, con la factura
  y el detallado ya adentro, aunque todavía no los haya copiado ni convertido.

Un defecto que apareció en la prueba de tres corridas seguidas y quedó cerrado:
en una factura **sin epicrisis**, el `..._EPICRIS.pdf` de la primera corrida se
colaba como si fuera una epicrisis y en la segunda el folio crecía metido dentro
de sí mismo (10 → 13 páginas). Ahora el bot mira la carpeta, no el renglón: si
ya hay archivos numerados, lo que quede con el nombre original es el folio
viejo. El caso que no se puede distinguir (un `..._EPICRIS.pdf` suelto en una
carpeta ya armada) no se adivina: se avisa para que el auditor lo mire.

45 pruebas nuevas (104 en el archivo).

### Revisión posterior: dos defectos más, encontrados antes del cargue real

**1. Una factura bloqueada dejaba sin folio a las otras 323.** `aplicar_folios`
llamaba a `renombrar_lista` sin candado, al contrario de `unir()`. Un PDF
abierto en Acrobat —o el share cayéndose un momento— tumbaba la corrida entera.
Ahora esa factura se salta con `ERROR` y su motivo, y las demás siguen.

**2. El folio de la factura habría llevado el detallado dos veces.** Al abrir el
`680010079201_HUS311736_FACTURA.pdf` que viene con el XML, resultó **no ser solo
la factura**: son 19 páginas con los cuatro renglones ya pegados —factura con
CUFE (1–7), detallado (8–9), representación gráfica DIAN (10–18) y nota crédito
(19)—. El bot le habría agregado encima el detallado del Excel. Ahora
`renglones_que_trae()` mira dentro del PDF antes de tocarlo: lo que ya viene
pegado no se duplica ni se cuenta como faltante, y se avisa en pantalla.
Comprobado sobre una sola factura; en las que vengan solo con la factura, el bot
arma el folio con las partes sin configurar nada.

Con esto: 111 pruebas en el archivo.


## Sesión 25-ago-2026 (noche, 2) — `--renombrar`: el folio como lo nombra el área

El PDF unido de la HUS352904 no se parecía a lo que pide la hoja del área. Al
mirarlo con el auditor salieron dos cosas distintas:

- **La hoja no pide un PDF pegado, pide los soportes numerados dentro del
  folio**: `1 RESPUESTA A GLOSA.pdf`, `2 HISTORIA CLINICA.pdf`, `3 OTRO.pdf`.
  Eso es `--renombrar`, nuevo. `nombre_numerado()` arma el nombre y
  `renombrar_en_orden()` lo aplica **en dos vueltas** —primero a un nombre
  temporal—: el nombre que le toca a un archivo puede ser el que todavía tiene
  otro, y renombrando de una uno pisaría al otro. Idempotente.
- **El contenido era corto porque la carpeta solo tenía dos soportes.** No es
  defecto del bot: faltan la epicrisis y los demás.

La unión en un solo PDF sigue como estaba, por defecto. Se pueden usar las dos.

7 pruebas nuevas (59 en el archivo), incluida la del renombrado que se pisaría a
sí mismo y la de correrlo dos veces.


## Sesión 25-ago-2026 (noche) — repartir la respuesta a glosa por carpeta de factura

`organizar_soportes_por_factura.py`:

- **`carpetas_por_factura()`**: mapea el número de factura a la carpeta que ya
  existe, aunque traiga una nota detrás (`HUS379477_PEND. CARTA CORONEL`,
  `HUS367368 ACEPTADO`, `HUS378523_MAOS`). Antes se buscaba `carpeta / factura`
  literal, así que a esas no las encontraba y **creaba una carpeta gemela
  vacía**. Con dos carpetas para la misma factura gana la primera alfabética,
  para que el resultado no dependa del orden del sistema de archivos.
- **`--solo-carpetas-existentes`**: mueve solo lo que ya tiene carpeta, sin
  crear ninguna. Hace falta al repartir un lote que abarca varios gestores: las
  324 respuestas se sueltan en cada carpeta y solo caen las que corresponden;
  las demás quedan listadas con el estado `SIN CARPETA PARA ESA FACTURA`.

`unir_soportes_adres.py`: `_factura_de_carpeta` pasa a delegar en
`factura_del_nombre` — la regla de cómo se saca el número de un nombre queda en
un solo sitio.

8 pruebas nuevas (54 en el archivo), y ensayo de punta a punta con el ZIP real.


## Sesión 25-ago-2026 — `unir_soportes_adres.py` + arreglo del desglose huérfano

### `unir_soportes_adres.py` (nuevo)
Une los soportes de cada carpeta de factura en un solo `<FACTURA>_SOPORTES.pdf`,
en el orden de la lista del área (13 grupos, de RESPUESTA A GLOSA a OTROS). El
detallado queda fuera del PDF: la lista lo pide en Excel.

Clasifica por nombre de archivo con dos reglas que evitan los falsos positivos:
gana la **palabra más larga** («NOTAS DE ENFERMERIA» sobre «NOTAS»), y las
abreviaturas cortas se buscan como **palabra completa** (`INS` no casa dentro de
`INSTITUCIONAL`). Lo no reconocido va a OTROS y sale marcado en el reporte.
`--mapa-nombres` agrega palabras sin tocar el código.

Reusa `unir_pdfs` / `clave_natural` de `unir_pdfs_carpetas.py` — la unión y el
orden natural ya estaban resueltos; aquí solo se agrega la capa de orden.

Simula por defecto (`--aplicar` para escribir), se excluye a sí mismo de la
entrada (idempotente) y un PDF ilegible se omite sin tumbar el lote. Avisa las
facturas sin RESPUESTA A GLOSA o sin EPICRISIS.

Incluye `UNIR_SOPORTES_ADRES.cmd` (CRLF), guía en español y 42 pruebas.

### `ajustar_detallado_glosas.py` — desglose huérfano
**Defecto:** cada ítem se decidía por separado. Cuando la entidad aprobaba el
procedimiento (CUPS, que no aparece en el reporte del ADRES porque este glosa
con códigos SOAT) pero seguía glosando sus componentes, el principal se quitaba
y los componentes quedaban huérfanos: el detallado mostraba honorarios y
derechos de sala sin decir de qué cirugía eran. El auditor tuvo que rehacer a
mano la HUS383283.

**Arreglo:** una pasada previa marca los principales cuyo desglose sobrevive y
los conserva con la acción nueva `ACCION_ENCABEZADO` — se ven, pero no suman al
subtotal, porque su valor ya está en los renglones de desglose. La condición de
"no suma" de los hijos se corrigió en consecuencia (`id(padre) not in
rescatados`), para que el valor no se pierda ni se cuente dos veces.

2 pruebas nuevas: el principal se queda como encabezado y no suma; y si su
desglose también se fue, se va como siempre.

## Sesión 25-ago-2026 (noche) — 2.ª auditoría del lote: el Decreto 4747 tenía tres artículos inventados

Un segundo auditor revisó las mismas 117 respuestas con otro método: contrastó
las citas contra el texto publicado de las leyes y cruzó, código por código, el
motivo real del pagador contra lo contestado. Encontró lo que la primera pasada
no vio.

### 1. `DECRETO 4747 DE 2007` — corpus corregido contra la fuente oficial

Las 28 respuestas de ratificación (100 %) citaban el **Art. 20** como el del
trámite de glosas. Verificado contra el texto de MinSalud: el Art. 20 es el del
**RIPS**; el trámite está en el **23**. Y de los tres artículos que el corpus
tenía cargados, **los tres** estaban mal, con epígrafe y texto fabricados:

| Corpus decía | Texto oficial |
|---|---|
| Art. 11 — «Atención de urgencias» | «Verificación de derechos de los usuarios» |
| Art. 20 — «Trámite de glosas — conciliación» | «Registro Individual de Prestaciones — RIPS» |
| Art. 21 — «Pago durante trámite de glosas» | «Soportes de las facturas» |

**El defecto estructural, no la cita:** `citation_verifier` contrasta contra ese
mismo corpus, así que la cita fabricada **se autocertificaba** — el dictamen
salía «citas verificadas · 0 hallazgos» con una norma que dice otra cosa. Misma
clase de defecto que la jurisprudencia del 24-08.

Se cargaron los cinco artículos con texto literal (11, 20, 21, 22, 23) y se
repasaron las **17 citas** al decreto repartidas por `glosa_ia_prompts`,
`multi_agente`, `conciliador_ia`, `validador_dictamen`, `memoria_gestor`,
`contexto_contractual_enriquecido`, `salud_total_service` y `routers/glosas`.

`TEXTO_RATIFICADA` ahora cita el Art. 23. `_corregir_articulo_mal_citado` es la
malla: corrige «Art. 20 del Decreto 4747» → 23 **solo** cuando el contexto habla
de glosas (el Art. 20 existe y citarlo para RIPS es correcto).

Efecto colateral bueno: el Art. 11 real —verificación de derechos— es
exactamente el fundamento de las glosas FA1605/FA1606. Estaba inutilizable
porque el corpus lo tenía mal.

### 2. Cita literal fabricada — se detecta sola al corregir el corpus

Varias respuestas AU0202 atribuían al Art. 11 un texto entrecomillado sobre
urgencias sin autorización previa. No está en el decreto. Corregido el corpus,
`verificar_citas` la marca `CITA_LITERAL_FALSA` (ALTA) y
`_descomillar_citas_falsas` la desactiva. No hizo falta regla nueva.

### 3. `_avisar_si_contesta_la_forma` — responder la glosa que es

De 79 códigos, **74 abordaban el motivo real**. Los 5 que no ($3.564.600)
fallaban igual: contestaban validez de factura electrónica ante la DIAN cuando
la glosa era de fondo.

- **FA1606** (3, $2.571.800) — el pagador alega régimen del afiliado distinto al
  del contrato. Lo resuelve la BDUA a la fecha de atención, no la DIAN.
- **FA0703** (2, $992.800) — «insumo no facturable» con código del ítem. Lo
  resuelve el anexo del paquete.

`catalogo_glosas` gana la defensa central de ambos códigos (patrón ya usado en
FA0202/FA0802). La red no reescribe el argumento: añade **«⚠ REVISAR ANTES DE
RADICAR»** cuando el dictamen argumenta forma y no entró en el fondo. No dispara
si el texto ya menciona BDUA/régimen/verificación de derechos (FA1606) o
paquete/anexo (FA0703), ni en códigos que sí son de forma.

### 4. Dos defectos de forma

- **Etiqueta contradictoria** (HUS0000538289): «Contrato: SIN CONTRATO PACTADO»
  junto a «Tarifa **pactada**: SOAT PLENO». Sin contrato no hay pacto — el SOAT
  pleno es lo que se aplica *a falta* de pacto. La etiqueta pasa a «Tarifa
  aplicada» cuando no hay contrato.
- **Pseudo-norma en el cuerpo del argumento**:
  `_neutralizar_art_168_fuera_de_contexto` sustituía la cita inaplicable por «LA
  NORMATIVA DE CONTINUIDAD Y COBERTURA DEL SISTEMA GENERAL DE SALUD», que se lee
  como el título de un documento inexistente. Ahora: «las reglas generales del
  Sistema General de Seguridad Social en Salud». `_solo_normas_citables` sigue
  de malla para la lista de FUNDAMENTO.

### Nota de despliegue

El filtro `_solo_normas_citables` (24-08) **sí estaba** en el commit desplegado
y aun así la pseudo-norma salió en el FUNDAMENTO de las 117: se generaron antes
de reiniciar el motor. Lo corregido no tiene efecto hasta el reinicio.

### Lo que no se tocó

Las 21 respuestas de ratificación usan una plantilla que no entra en el motivo
concreto de la ratificación (0/44 códigos). El texto lo pidió el área y se
sostiene jurídicamente; cambiarlo es decisión del auditor. Queda anotado en
BITACORA con la mejora disponible: el Art. 23 prohíbe glosas nuevas sobre la
misma factura salvo por hechos nuevos.

### Pruebas

`test_decreto_4747_articulos_reales.py` (16) ·
`test_contestar_el_tema_de_la_glosa.py` (13). Reescritas para fijar la intención
en vez de la redacción: `test_ronda13_fixes` (pseudo-norma) y `test_multi_agente`
(anclaje de urgencias — tercer anclaje equivocado para lo mismo).

## Sesión 25-ago-2026 (tarde) — Auditoría de las 117 respuestas del primer lote productivo

Se pasaron por el revisor de citas las 117 respuestas que el motor generó con
el archivo de recepción del día. Cinco defectos, cinco correcciones con prueba.

### 1. CUPS que el motor nunca tuvo a la vista (12 respuestas)
El archivo de recepción **no trae columna de CUPS**. La IA rellenaba el hueco
con un número de seis cifras. La prueba de que era invento: el mismo `734101`
nombró «radiografía de maxilar inferior» en un dictamen y «radiografía de
pierna» en otro; el `730102`, «urgencias adultos» e «internación adultos
complejidad alta».

`_neutralizar_cups_sin_respaldo(texto, evidencia)` — misma regla que ya se
aplicaba a los folios: si el código no está en lo que la IA leyó, no lo leyó.
Se exige **además** que no se pueda verificar en el catálogo, para que un
código real nunca se borre (lección de la Res. 2641 de 2024). Se retira solo el
número; la descripción del servicio se conserva.

### 2. El texto fijo del Dispensario declaraba vigente un contrato vencido (14)
`TEXTO_DMBUG_TARIFAS` afirmaba «SE ENCUENTRA SUSCRITO Y **VIGENTE** EL CONTRATO
440-DIGSA/DMBUG-2025 … CON PLAZO HASTA **30/07/2026**» — el 25 de agosto, 26
días después del plazo. Frase autocontradictoria en un documento radicado.

- El texto ancla la vigencia **a la fecha de prestación**, que es lo verificable
  y además defiende mejor.
- `_dmbug_cubierto_por_el_contrato(fecha_hecho)` lee el plazo de
  `malla_contractual` (fuente única) y, si el servicio quedó fuera, el texto
  canónico no se usa: la glosa va por el camino normal. Sin fecha se deja pasar
  — una glosa siempre es de un servicio pasado.

### 3. `LEY 1164 DE 2007` cargada al corpus (3 respuestas)
El revisor la marcaba `NORMA_INEXISTENTE` (ALTA). Existe: Talento Humano en
Salud, 3 de octubre de 2007. Se verificó contra el texto oficial de MinSalud y
se cargaron sus artículos 26 («el acto profesional se caracteriza por la
autonomía profesional») y 35.

### 4. `_corregir_anio_de_norma` — la norma es real, el año no (2 respuestas)
«Resolución 3100 de 2020» → es de **2019**. La resolución ya estaba en el
corpus con el año correcto; faltaba corregir la cita. Tabla estrecha: solo
pares número+año verificados contra la fuente.

### 5. `_reponer_preposicion_comida` — el «de» que se come el modelo (11)
«levantamiento **la** glosa», «artículo 17 **la** ley», y —dentro de comillas
que citan textualmente el Art. 17— «los profesionales **la** salud». Se probó
cada patrón del módulo contra la frase correcta: ninguna malla la toca, lo
escribe así el modelo. Lista de tres fórmulas verificadas, no un corrector
gramatical general.

### Además
- **Amenazas al pagador**: la regla 8.decies las prohibía por instrucción y el
  modelo amenazaba igual (GL-118/GL-119). Ahora hay malla. Lo legítimo se
  conserva: Art. 126 Ley 1438 (SuperSalud), Art. 57 (levantamiento por falta de
  respuesta) y negarle a la EPS la facultad sancionatoria.
- **`_completar_norma_derogada`** (Res. 2275/2023, 21 respuestas): no se
  reemplaza — para un servicio anterior al 14-05-2026 esa ES la norma
  aplicable. Se **completa** con la regla de fecha. `citation_verifier` deja de
  avisar cuando el documento ya nombra la sucesora
  (`_norma_sucesora_ya_nombrada`).

### Resultado sobre el mismo lote de 117

| Hallazgo | Antes | Después |
|---|---|---|
| `CUPS_INEXISTENTE` (ALTA) | 7 | **0** |
| `CODIGO_NO_ES_CUPS` (ALTA) | 5 | **0** |
| `NORMA_INEXISTENTE` (ALTA) | 2 | **0** |
| `NORMA_DEROGADA` (MEDIA) | 21 | **2** |
| Preposición comida | 11 | **0** |

Pruebas nuevas: `test_cups_inventado_no_sale_en_el_dictamen.py` (17),
`test_dmbug_no_dice_vigente_lo_vencido.py` (8),
`test_el_dictamen_no_amenaza_al_pagador.py` (13),
`test_normas_reales_que_faltaban.py` (14),
`test_el_de_que_se_come_el_modelo.py` (11),
`test_norma_derogada_dice_desde_cuando.py` (14).

## Sesión 24-ago-2026 — `organizar_objeciones_adres.py`: cuadre contra el reporte del ADRES

### El defecto que corrige
El detalle del ADRES cuenta la misma plata varias veces, y la conversión la
sumaba tal cual: el paquete 31068 salía en **$1.032.239.679** contra los
**$646.908.552** que el ADRES reporta glosados. Cargado a DGH habría objetado
hasta tres veces el mismo dinero.

Dos fuentes de repetición, ambas del archivo del ADRES:
- Filas de causal de reclamación (2102, 2103…) con el valor **completo** de la
  reclamación, además del detalle por servicio.
- El mismo servicio (mismo código, cantidad y valores) repetido por cada causal.

### `--reporte-reclamaciones`
Lee el `ReporteReclamPAQUETE_*.xlsx` (encabezado en la 2ª fila: encima va la de
totales) y deja cada factura sumando **exactamente** su `Valor Glosado`:
1. `conciliar_factura` quita las filas que repiten el total de la reclamación.
2. Quita las repeticiones, mayor primero, **sin bajarse del valor reportado**.
3. `cuadrar_con_reporte` corre **al final**, sobre los valores ya topados por el
   guardián de DGH, y reparte el residuo desde el renglón mayor hacia abajo sin
   dejar valores negativos. También reescribe el `$<valor>` del `CRDOBSERV`.

Resultado 31068: **324/324 facturas cuadradas**, $646.908.553 (Δ $1 por redondeo
a pesos enteros), 169 renglones quitados, 65 facturas ajustadas.

### `--completar-servicios`
Ningún `SLNSERPRO` queda vacío: se usa el candidato del cruce y, si no hay,
`servicio_principal` (el servicio de más peso de la factura en DGH). No es
homologación — cada fila así queda en `REVISAR` con `CODIGO DE SERVICIO
ASIGNADO` y su procedencia. En el 31068: 1.856 vacíos → **0**, con 1.768 filas
marcadas.

### Otros
- `_hoja_con` acepta `max_filas` para encabezados que no están en la 1ª fila.
- Motivos nuevos en REVISAR: `REV_REPITE_TOTAL`, `REV_DUPLICADO`,
  `REV_AJUSTE_REPORTE`, `REV_FACTURA_SIN_REPORTE`, `REV_SERVICIO_ASIGNADO`.
- El resumen del CLI imprime el cuadre contra el reporte y las facturas que no
  cuadren.

### Pruebas
16 nuevas (65 en total en el archivo): que se quite el renglón que repite el
total, que las repeticiones se quiten de mayor a menor, que **nunca se baje del
valor reportado**, que el cuadre mande sobre el tope de DGH, que el ajuste se
reparta si no cabe en un renglón, que ningún valor quede negativo, y que el
lector tolere el encabezado en la 2ª fila.


## Sesión 21-ago-2026 — `organizar_objeciones_adres.py`: glosas del ADRES → OBJECIONES de DGH

Bot nuevo (`tools/organizar_objeciones_adres.py` + `OBJECIONES_ADRES.cmd` +
`README_organizar_objeciones_adres.md`) que convierte el Excel de glosas del
ADRES al layout de 16 columnas que recibe Dinámica Gerencial.

### Homologación del código de servicio (`SLNSERPRO`)
Seis pasos, siempre dentro de la misma factura, parando en el primero que
acierta: código directo (igualando ceros de relleno), SOAT→CUPS con el
Homologador Gold Standard, descripción igual, descripción por prefijo, valor
exacto + ≥50 % de palabras en común, y similitud ≥0,85. Lo que no se resuelve
sale con la casilla **vacía** y con su mejor candidato listado en `REVISAR` —
nunca se escribe un código deducido.

En el paquete 31068: 2.763 de 3.262 renglones con servicio (84,7 %).

### Reglas del formato
- `CDCONSEC` y `GENUSUARIO4` como TEXTO, `CROCLAOBJ=0`, `GENUSUARIO4=999`.
- `CRNCXC` en formato largo (`HUS311371` → `HUS0000311371`).
- `CROTIPOBJ` por factura: administrativas `0`, pertinencia `1`, mezcla `2`.
- **Guardián de valores** (el mismo de `cruces_dgh.generar_objeciones`): la
  objeción no supera el valor del servicio en DGH ni el saldo de la factura.
- **Lotes de 300 facturas** (tope de DGH), sin partir ninguna factura.

### Detalles que costaron
- El libro del ADRES trae una tabla dinámica con las mismas columnas pero los
  valores sumados (`Suma de Valor Glosado`); detectar la hoja de glosas por dos
  columnas dejaba todas las objeciones en cero. Ahora se exigen cuatro.
- El texto de la causal viene repetido detrás de su código en la misma celda;
  se corta en la última aparición de `<código>-`.
- `CRNCONOBJ`: el ADRES usa códigos numéricos de 4 dígitos y DGH los de 6 del
  Manual Único, y **no existe tabla oficial que los equipare**. Se escribe el
  del ADRES tal cual y se entrega la hoja `CODIGOS` + `--mapa-codigos` para que
  el auditor defina la equivalencia.

### Pruebas
`tests/test_tools/test_organizar_objeciones_adres.py` — 49 pruebas, incluida
una de punta a punta que arma los tres libros de entrada y verifica el archivo
de salida celda por celda.

## Sesión 20-ago-2026 (noche) — Rediseño de la aplicación web del ICFES

De cuatro pantallas planas a un panel con el plan de estudio adentro.

### Funcionalidad nueva
- **El plan de estudio ahora vive en la aplicación**: Inicio abre en «qué te
  toca hoy» con los bloques del día y un botón para empezar cada uno; la
  pantalla **Plan** muestra las cuatro fases y el detalle de cualquier semana.
- **Estudiar** (pantalla nueva): repaso del día, cuaderno de errores, las
  competencias más flojas con botón para practicarlas, y práctica libre con
  filtros de área, competencia, dificultad y procedencia.
- **Progreso**: proyección al día del examen, línea del año, una mini gráfica
  por área, competencias ordenadas, causas de error con su remedio, calendario
  de constancia y preguntas reincidentes.
- **Durante las preguntas**: cronómetro con el ritmo real del examen y semáforo
  de ritmo, atajos de teclado (A-D y Enter), marcar preguntas para revisar y
  lecturas largas en serif.
- Barra lateral en pantallas grandes; barra inferior en celular.

### Una sola fuente de verdad
- La política del plan (fases, mezclas, piso por área, minutos por bloque) y las
  escalas de puntaje se **exportan** desde `icfes/plan.py` y `icfes/puntaje.py`
  en vez de reescribirse en JavaScript.
- **`tests/test_icfes/test_nucleo_web.py`** extrae el núcleo de cálculo de la
  plantilla, lo corre con node y lo compara contra Python: metas por área,
  reparto de horas, puntaje, repaso espaciado y el plan completo **bloque por
  bloque** en tres escenarios. Se salta si node no está instalado.

### Color y accesibilidad
- Paleta de gráficas validada con el script de la guía de visualización: rampa
  secuencial monótona en claro y oscuro, y contraste ≥ 3:1 en las dos
  superficies.
- La primera versión coloreaba cada barra por estado; el validador la rechazó
  (verde y rojo se confunden para daltonismo, ΔE 4,1). Se corrigió por diseño:
  una sola serie, un solo tono, y el estado en una etiqueta con texto.
- Tres estados de tema (claro, oscuro por sistema, oscuro elegido) con una
  prueba que verifica que ningún color viva solo dentro de un bloque de tema.

### Correcciones encontradas probando en navegador
- Dos simulacros el mismo día se superponían en la gráfica de línea y sus zonas
  de hover se tapaban. Ahora la serie deja un punto por día (el último) y el
  ancho de la zona sensible se calcula desde la separación real entre puntos.
- El calendario de constancia solo miraba hacia atrás desde hoy: con avance
  importado decía «199 días con estudio» y salía vacío.
- En práctica el cronómetro estaba congelado y el semáforo de ritmo siempre en
  verde.

### Pruebas
266 en total (27 nuevas). `ruff check` y `ruff format` limpios sobre 1.229
archivos. Recorrido completo verificado en Chromium: escritorio y celular, tema
claro y oscuro, sin errores de JavaScript y sin desbordamiento horizontal.

## Sesión 20-ago-2026 (cierre) — Bot de doble clic del ICFES y guías corregidas

**Falla del primer uso real:** los comandos de la guía se corrieron desde
`C:\Users\cartera` y Python respondió `No module named icfes`. `python -m icfes`
requiere que la consola esté dentro de la carpeta del repositorio, y ninguna de
las tres guías lo decía.

### Cambios
- **`tools/ICFES.cmd`** (nuevo): bot de doble clic con menú completo — hoy,
  practicar, repasar, simulacro, progreso, plan, configurar y exportar la app.
  Hace `cd /d "%~dp0.."` antes de llamar a Python, así que el error no puede
  ocurrir; y verifica que Python esté instalado antes de intentar nada.
- **`docs/GUIA_SISTEMA_ICFES.md`**, **`docs/ESTRATEGIA_ICFES_400.md`** y
  **`README.md`**: el doble clic va primero, el `cd` aparece como paso cero y se
  explica qué significa `No module named icfes`.

### Pruebas (`tests/test_icfes/test_bots_windows.py`, 12 nuevas)
- Los bots del ICFES se paran en la carpeta del repositorio y avisan si falta
  Python.
- El menú no llama a ningún subcomando que no exista en el CLI (se valida
  contra el parser real).
- Los bots no traen credenciales.
- **Todos los `.cmd` del repositorio conservan finales de línea CRLF.** Esta
  regla estaba en `.gitattributes` y en CLAUDE.md pero no tenía prueba; con LF
  la ventana se cierra en Windows sin ejecutar nada.

Total del módulo: 251 pruebas.

## Sesión 20-ago-2026 — Sistema de preparación para el ICFES Saber 11 (`icfes/`)

Módulo **independiente** del Motor de Glosas: no importa nada de `app/` ni de
`tools/`, y solo usa la librería estándar de Python 3.11, así que la carpeta
`icfes/` se puede copiar a cualquier computador y funciona.

### Qué trae
- **`icfes/dominio.py`** — el examen modelado con datos oficiales: 254 preguntas
  calificables (41/50/50/58/55), 24 de pilotaje, pesos 3-3-3-3-1, dos sesiones
  de 4 h 30, y las 17 competencias de las cinco áreas.
- **`icfes/puntaje.py`** — puntaje global 0-500 con la fórmula oficial
  (`(3·LC+3·MAT+3·SOC+3·CN+1·ING)/13 × 5`); estimación de área 0-100 con curva
  declarada y editable (`CURVA_PUNTAJE`), siempre rotulada como estimación;
  reparto de una meta global en metas por área; corrección por azar.
- **`icfes/banco/`** — 110 preguntas de práctica en JSON (una por área), todas
  con explicación y con el distractor principal identificado. Cubre las 17
  competencias. Textos de Lectura Crítica en dominio público.
- **`icfes/plan.py`** — plan de 50 semanas en cuatro fases, con reparto de horas
  por peso oficial × brecha, piso del 8 % por área, día de descanso semanal,
  última semana aliviada y 11 simulacros completos.
- **`icfes/repaso.py`** — SM-2 adaptado; nunca programa un repaso posterior al
  examen; deduce la calidad del repaso de acierto, tiempo y causa del error.
- **`icfes/simulacro.py`** — simulacros con la estructura y los segundos por
  pregunta reales; a escala cuando el banco no alcanza, avisándolo.
- **`icfes/progreso.py`** — dominio ponderado por recencia, cuaderno de errores
  por causa con su remedio, racha y proyección por mínimos cuadrados que declara
  cuándo no es confiable.
- **`icfes/almacen.py`** — SQLite local (`~/.icfes/progreso.db`).
- **`icfes/cli.py`** — `python -m icfes iniciar|hoy|plan|practicar|simulacro|
  repaso|progreso|banco|exportar-web`.
- **`icfes/exportar_web.py`** + **`plantilla_web.html`** — aplicación web de un
  solo archivo, sin red, adaptable a celular, con tema claro/oscuro y avance en
  `localStorage`.
- **`tools/ICFES_APP.cmd`** — bot de doble clic para Windows (CRLF).

### Correcciones hechas durante el desarrollo
- **Simulacro**: reconstruía las respuestas desde la base de datos, así que una
  pregunta acertada en una práctica del mismo día contaba como acertada en el
  simulacro. La ronda ahora devuelve las respuestas reales, traducidas del orden
  barajado al orden original de la pregunta.
- **Exportación web**: la plantilla dejaba su objeto por defecto pegado al JSON
  inyectado (`const DATOS = {…}{…};`) y la página no cargaba. Se detectó abriendo
  la app en Chromium. Corregido con marcas de apertura/cierre y cubierto por
  prueba.
- **Banco**: la primera versión concentraba el 65 % de las respuestas correctas
  en la letra B. Como las opciones se barajan en cada práctica, el validador
  ahora exige que ninguna explicación nombre letras y verifica el reparto.

### Pruebas
239 pruebas en `tests/test_icfes/`; `ruff check` y `ruff format` limpios.
Recorrido completo de la app web verificado en Chromium (práctica, explicación,
cronómetro, resultado, progreso, persistencia tras recargar) sin errores de
JavaScript.

### Documentación
`docs/GUIA_SISTEMA_ICFES.md` y `docs/ESTRATEGIA_ICFES_400.md`.

## Sesión 10-jul-2026 — Suite Cartera HUS: herramienta multifuncional (GUI + CLI)

Integra en `tools/suite_cartera_hus/` la Suite de Cartera/Auditoría (menú
único de radicación, glosas y cruces masivos: reemplaza Power Query +
BUSCARV) con correcciones de fondo, endurecimiento y pruebas.

### Correcciones (verificadas con pruebas)
- **`a_numero`**: `'50.000'` se leía como `50` y no `50000` — corrompía
  TODOS los importes (glosado/servicio/saldo/copago y el guardián de
  valores). Ahora resuelve miles/decimales en formato colombiano, UE y US.
- **`generar_objeciones`**: `KeyError` si el Excel elegido no traía
  `valor_servicio/saldo/copago`; ahora da un error claro o tolera la falta.
- **`consolidar`**: renglones sin factura (celda vacía y sin factura en el
  nombre) se perdían en silencio en el `groupby`; ahora sobreviven visibles.
- **`consolidar`**: si no hay columna propia de código de servicio ya no se
  confunde con la de glosa (evita agrupar/sumar por la clave equivocada);
  además depura renglones byte-idénticos (duplicados de exportación).
- **`extraer_factura`**: reconoce facturas numéricas pegadas a `_` y da
  prioridad al formato HUS aunque una fecha aparezca antes en el nombre.
- **`leer_tabla`**: acepta listas de una sola columna (facturas ya
  objetadas) y CSV en latin-1 (Windows), que antes reventaban.
- **`extraer_zip_recursivo`**: los ZIP anidados ya no se pisan entre sí, y
  una entrada insegura (`../`) se omite sin abortar todo el ZIP.

### Seguridad
- Las contraseñas de los portales salen de `entidades.json` a un archivo
  **local no versionado** (`entidades.credenciales.json`, en `.gitignore`).
  La Suite las vuelve a unir en memoria al abrir. Incluye
  `herramientas/separar_credenciales.py` y una plantilla `.example`.

### Nuevo
- **`suite_cli.py`**: la misma Suite por línea de comandos (`entidades`,
  `organizar`, `consolidar`, `objeciones`, `evidencias`, `todo`) para
  automatizar sin ventana.
- **`tests/test_tools/test_suite_cartera_hus.py`**: 40 pruebas del núcleo
  (las que requieren pandas se saltan si no está, como el resto de tools).

## Sesión 1–2-jul-2026 — El expediente: contratos + soportes + precedentes

Diagnóstico que disparó la sesión (del usuario): *"la IA se rehúsa a
refutar... es como pegar el concepto en una IA normal"*. Causa raíz
confirmada: el motor argumentaba **a ciegas** — tres conexiones de datos
existían como código pero estaban desenchufadas de la generación del
dictamen. Esta sesión las enchufó (rondas 23–25).

### Fase 1 — Contratos (ronda 23)
- `get_contrato` ahora lee la BD (`ContratoRecord` + `ClausulaContrato`),
  no solo el catálogo estático: fin del falso "SIN CONTRATO PACTADO"
  cuando sí hay contrato cargado.
- Emparejamiento flexible de EPS ("AURORA" encuentra "SEGUROS DE VIDA
  AURORA S.A.").
- **26 cláusulas LITERALES de 11 pagadores reales** cargables con
  `scripts/seed_clausulas_contrato.py` (idempotente): AURORA (8),
  COMPENSAR, COOSALUD, SUMIMEDICAL, SALUD MÍA (3), POSITIVA (2), PPL (2),
  FAMISANAR 2026, DISPENSARIO MÉDICO/DMBUG (3), POLICÍA oncología (2),
  FOMAG (2 — incl. Circular 004/2025: sin autorización previa a docentes).
  Tarifas verificadas contra los Excel (SOAT−3/10/15/20%, UVB−5/8%,
  SMDLV−20%).
- Correcciones de catálogo: FOMAG a SOAT SMDLV −20% (Acta 012), POLICÍA
  oncología a UVB−8% + institucionales (Anexo 2 de la minuta), PRECIMED
  eliminado (era contrato de suministro con PRECIMEC SAS, no un pagador).

### Fase 2 — Soportes (ronda 24)
- **Tope de OCR 2000 → 12000 chars** en el caso simple (la IA por fin ve
  la HC adjunta); tunable por env (`GLOSA_SOPORTES_MAX_CHARS_*`).
- **Multimodal automático** (`GLOSA_MULTIMODAL_AUTO=1`): los casos que ya
  escalan a Claude mandan los PDFs nativos completos; los simples siguen
  en Groq con texto (no es "siempre Claude").
- **Gate interactivo de expediente**: el detector determinista avisa en el
  prompt qué soportes faltan y prohíbe inventar evidencia; fallback
  sin-soportes reescrito de "el registro clínico respalda la atención"
  (invitación a alucinar) a reglas anti-invención siempre-verdaderas.
- **Auditor Forense conectado al dictamen** (opt-in,
  `GLOSA_AUDITOR_FORENSE_PREPASS=1`): pre-pass que lee los PDFs y antepone
  un mapa de folios (folio + fecha + hallazgo + faltantes) al contexto.
- Review adversarial del propio diff cazó y corrigió 6 bugs antes de
  mergear (el peor: Opus degradándose a Sonnet en casos ≥$10M por la vía
  multimodal; backstop nuevo en el validador contra fuga del andamiaje
  del prompt al dictamen).

### Fase 3 — RAG/banco (ronda 25)
- **Few-shots por SIMILITUD BM25** (`GLOSA_FEWSHOT_BM25=1`): cuando el
  match exacto (eps+código) no llena los ejemplos, se completa con el
  precedente GANADO más parecido al texto de la glosa (RAGService, antes
  desconectado de la generación). Sin tokens extra.
- Filtro de contrato ajeno sobre los precedentes + instrucción anti-copia
  reforzada (estilo sí, datos del otro expediente no).

Suite: **4069 tests verdes**. Todo reversible por env var sin redeploy.

---

## Sesión 30-jun-2026 — De "a ciegas" a "medido"

Resultado medible de la sesión, con el **tablero de calidad** (0–10) sobre
los 4 casos difíciles reales:

| Caso | Antes | Después |
|---|---|---|
| MEDIMÁS da Vinci $273M | 0.5 | **10** |
| ECOOPSOS coclear $389M | 4.5 | **10** |
| SALUD TOTAL TMS $98M | 5.0 | **10** |
| Hemofilia + sanción $156M | 0.0 | 6 → escala a Claude (subiendo) |
| **Promedio** | **2.5/10** | **~9/10** |

El cambio de fondo: dejamos de parchear a ciegas. Ahora cada cambio se
**mide** contra una rúbrica experta y el que **regresa** se detecta solo.

---

### Operación / producción (incidentes resueltos)
- **Cloudflare Error 1033** (app caída): causa raíz `net.ipv4.ip_forward=0`
  → NAT de Docker rota → los contenedores no salían a internet y el túnel
  no conectaba. Fix: `ip_forward=1` + reinicio de Docker (+ persistencia en
  `/etc/sysctl.d/`).
- **502 Bad Gateway**: contenedor `motor` con referencia stale tras un
  `up --build`. Fix: `docker compose down && up -d`.

### Limpieza de imports (PR #152, mergeado)
- Eliminados **~100 lazy imports redundantes** en `glosas_stats.py` y
  `sistema.py` (símbolos ya disponibles a nivel de módulo).
- Agregado `app/utils/__init__.py` faltante.

### Mejora #3 — Salida estructurada incremental (flag OFF por defecto)
- Flag `GLOSA_CAMPOS_ESTRUCTURADOS` (config + docker-compose + .env.example).
- La IA confirma 6 campos críticos (EPS, servicio, contrato, cláusulas,
  sanción, sub-conceptos) en un bloque JSON que el motor cruza contra los
  valores **deterministas** (verdad = determinista) y registra divergencias.
- Parser tolerante + validación + degradación elegante + tests (31).
- Runbook de activación: `docs/RUNBOOK_CAMPOS_ESTRUCTURADOS.md`.

### Ronda 21 — Auditoría del dictamen MEDIMÁS da Vinci (9 fixes)
- **#1 (crítico)** Contrato negado en el cuerpo ("al no existir contrato
  pactado") pese a que la glosa lo cita → regex ampliado a la forma verbal.
- **#2 (crítico)** Tarifa: ya no afirma "SOAT pleno / sin contrato" cuando
  la glosa cita un contrato; defiende dentro del contrato (Pacta Sunt S.).
- **#5** Pertinencia: rebate la GPC citada con T-121/2015 + evidencia 1A.
- **#6** Rebate por nombre las normas que cita la EPS (+ regex de extracción
  que ahora captura "Res. 0112/2012", "Decreto 4747/2007 Art. 20").
- **#8** Banner + penalización cuando se evade una cláusula citada.
- **#9** Vocabulario de cobertura (evento adverso, liquidación).
- **#10** Defensa de liquidación anclada (Auto 116/2024).
- **#11** Recorte de coda procesal unida por conjunción.
- **#12** "Art. 177 Ley 100" pelado en debate tarifario → fundamento correcto.

### Defensa clínica (PR #151, mergeado + integrado)
- Banco de evidencia nivel 1A (da Vinci, coclear, TMS, hemofilia, etc.) que
  nunca se había integrado a producción. Ahora se inyecta al prompt y se
  audita la literatura citada.

### Ronda 22 — Defectos del tablero (capa de generación)
- Reglas de prompt: sanción → atacar la legalidad (NO "Pacta Sunt Servanda"
  ante una multa); prohibido tono amenazante; prohibido el falso "silencio
  positivo"; prohibido inventar el texto de cláusulas/normas; no confundir
  normas por tema (Ley 1388/2010 es de cáncer, no auditiva).
- Red de seguridad: `_corregir_norma_mal_aplicada` (Ley 1388→1618).

### Tablero de calidad (lo nuevo de fondo)
- `tests/benchmark/scorer.py`: rúbrica experta determinista (0–10, sin LLM).
- `tools/scoreboard.py`: mide el texto guardado + **memoria** (historial) +
  detección de **regresión** + modo `--rescore-live`.
- `tools/scoreboard_live.py`: corre las 4 glosas por el **motor real** y las
  puntúa (mide el efecto real de cada cambio). Progreso visible + timeout.
- `docs/EJEMPLOS_DICTAMENES_ESPERADOS.md`: 4 casos con el dictamen esperado
  y checklist de criterios.
- Regla del proyecto: la IA es BUENA solo si **los 4 casos sacan ≥ 7**.

### Routing
- Hemofilia con inhibidores ("factor VII / eptacog") ahora escala a Claude
  (palabra-clave + valor), no se queda en Groq.

---

_Total sesión: 18 commits en la rama + PR #151 y #152 mergeados._
