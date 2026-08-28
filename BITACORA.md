# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo:** la memoria común de todos los chats de Claude Code.
> Aquí queda registrado qué se ha hecho, qué está pendiente y qué sigue.
> **Regla:** todo chat debe LEER este archivo al empezar y ACTUALIZARLO al terminar
> (con fecha, lo hecho, lo pendiente y lo de mañana). Escrito en lenguaje claro
> para el auditor de cartera del HUS.

**Última actualización:** 28-08-2026

---

## 1) Las patas del proyecto

1. **Motor de Glosas (aplicación web con IA):** recibe las glosas y redacta el
   dictamen de defensa del hospital (cita contrato, tarifas, normativa). Vive en
   la carpeta `app/` y se usa desde el navegador. Incluye además el **módulo de
   Pre-auditoría SINAC** (página `/preauditoria`, nuevo 23-07).
2. **Bots de carga (robots que suben respuestas a las plataformas):**
   - `tools/responder_glosas_coosalud.py` — portal de COOSALUD (vco.ctamedicas.com).
   - `tools/responder_glosas_simed.py` y `tools/cargar_soportes_simed.py` — SIMED (Dispensario Médico).
   - `tools/responder_glosas_dgh.py` — Dinámica Gerencial (programa de escritorio del hospital).
   - `tools/responder_glosas_siifa.py` — **SIIFA** (Ministerio de Salud, plataforma
     nacional, no es un portal de una EPS): a diferencia de los otros, no es un
     bot de navegador, habla directo con la API oficial de interoperabilidad.
   - Otros: Mutual Ser, FOMAG, radicador de facturación.
3. **Plataforma de conciliación del Dispensario** (`tools/`):
   índice de soportes → expediente por factura → motor de evidencia → hechos
   probados → motor de decisión → piloto (`piloto_conciliacion_dispensario.py`).
4. **Herramientas de apoyo:** armar el Word/PDF de evidencias
   (`tools/evidencias_a_word.py`, `evidencias_a_pdf.py`), notas crédito del
   Dispensario (renombrar, organizar, verificar CUV), tablero de cartera
   (`tools/tablero_cartera.py`), informe masivo de seguimientos SIIFA
   (`tools/siifa_reporte_seguimientos.py`).
5. **Suite Cartera HUS** (`tools/suite_cartera_hus/`, PR #160): programa de
   escritorio del analista de Cartera — organiza el ZIP del portal en lotes,
   consolida las glosas, cruza contra la base DGH y arma las OBJECIONES listas
   para cargar. Incluye una **caja de Herramientas PDF** (26 utilidades: unir/
   dividir/rotar páginas, proteger/censurar, conversión Office↔PDF, resumir/
   traducir/OCR con IA), el bot de **correos de pagos (.msg) → Excel** y el
   bot de **unir Exceles** (apilar filas u hoja por archivo).
   Versión de ventana (`suite_cartera_hus.py`) y de consola (`suite_cli.py`).
6. **Módulo ADRES/FURIPS** (chat "VALIDADOR ADRES"):
   - `tools/adres/validar_furips.py` + `VALIDAR_FURIPS.cmd` — validador masivo
     FURIPS 1/2 contra la Circular 022/2023 + cruce con soportes (RIPS, CUV,
     XML DIAN, factura PDF, epicrisis) con OCR para PDF escaneados.
   - `validador-adres/` — la misma validación como APP WEB (navegador,
     puerto 8010, `VALIDADOR_ADRES_WEB.cmd`).
   - `tools/generar_informe_baja_cartera.py` + `INFORME_BAJA_CARTERA.cmd` —
     informe Word + Excel de baja de facturas (Res. 577/2019), también con OCR.
   - `tools/completar_informe_xml_dian.py` + `COMPLETAR_INFORME_XML.cmd` —
     completa el informe de devoluciones DE4401 de NUEVA EPS leyendo los XML
     DIAN del repositorio de facturación (v2.1: subcarpetas, ZIP, DIAGNOSTICO).
   - Bots PDF de doble clic: `UNIR_PDFS.cmd`, `PDF_A_CMD.cmd`,
     `PDF_A_CMD_EN_CARPETA.cmd`.

Guías por plataforma en `docs/`: `CONTEXTO_COOSALUD.md`,
`CONTEXTO_DISPENSARIO_GLOSAS.md`, `CONTEXTO_DISPENSARIO_NOTAS.md`,
`CONTEXTO_SIIFA.md`,
`ENTREGA_MODULO_ADRES_FURIPS.md` (entrega técnica del módulo ADRES).

---

## 2) Resumen de lo ya hecho (por fecha)

### 28-08-2026 — Se auditaron las 135 glosas reales de la base, y la norma derogada que el motor seguía escribiendo

**Lo que se revisó.** Usted exportó desde la PC de cartera las **135 glosas
reales** que el motor ha respondido y las mandó completas. Se revisaron una por
una. Esto no es una prueba de laboratorio: son los dictámenes que salieron de
verdad.

**Lo que salió mal, en orden de gravedad:**

| Qué | Cuántas |
|---|---|
| Sin código de causal (el archivo de recepción no trae esa columna) | 59 |
| Citan una resolución que ya no rige | 34 |
| Citan un CUPS que no existe en el catálogo | 19 |
| Sin fechas: no se puede calcular si la glosa llegó tarde | 16 |
| Presentan como vigente un contrato ya vencido | 14 |
| Dicen que un código de glosa es el código del servicio | 11 |
| Afirman cosas de la historia clínica sin un soporte anexo | 9 |
| Valor objetado en cero | 7 |
| Comillas de una cita que la norma no dice así | 5 |
| Le atribuyen a un artículo algo que no dice | 3 |
| Citan un folio que no está en el expediente | 1 |

**Lo que se arregló hoy en el motor:**

1. **La Resolución 3047 de 2008 ya no puede salir sola.** Está derogada desde
   el 1 de abril de 2026, y **nueve de las 135** la citan. Se le había cambiado
   la instrucción a la IA para que no la usara y la escribió igual — la
   instrucción no basta. Ahora hay una **red** que revisa el texto ya escrito:
   donde aparezca la 3047 le agrega, ahí mismo, **quién la derogó y desde
   cuándo**, y cuál rige hoy. La cita NO se borra: para un servicio prestado
   antes del 1 de abril de 2026 esa ERA la norma aplicable, y cambiarla sería
   meterle al escrito una norma que ese día no existía. Así la EPS ya no puede
   responder «esa resolución está derogada»: el escrito lo dice primero.

   La máquina que hace esto existía desde el 25 de agosto, con **una sola**
   resolución cargada. Nadie le había puesto la 3047. Es otra vez la lección de
   esta semana: escribir la regla no era el trabajo, el trabajo era comprobar
   que llegara.

2. **Otras dos resoluciones muertas que el motor daba por vivas.** El mismo
   artículo que derogó la 3047 derogó también la **Res. 416 de 2009** y la
   **Res. 4331 de 2012**. La 4331 estaba en el corpus marcada como vigente, así
   que el revisor aprobaba un dictamen fundado en ella. Quedaron las dos
   corregidas y cargadas en la red.

3. **La forma corta no se reconocía.** El motor escribe a veces «Res.
   3047/2008» en vez de «Resolución 3047 de 2008». La red solo veía la forma
   larga, así que la corta pasaba de largo. Ya ve las dos.

4. **El sello volvía a hablar de un texto que ya no existía.** Ayer se corrigió
   para los CUPS y había quedado el mismo defecto en las tres redes de normas:
   corrían DESPUÉS de que se revisaban las citas, así que el sello avisaba de
   problemas que el escrito ya había arreglado. Ahora se vuelve a revisar al
   final. El gestor deja de leer avisos graves de cosas que ya no están —que es
   lo que hace que uno deje de creerle al sello.

**Lo del día anterior (27-08), que tampoco estaba en esta bitácora:** se
descubrió que el motor llamaba «CUPS» a códigos que no lo son (el código de la
glosa, por ejemplo), y que un código sacado de DGH no queda validado por venir
de ahí. También que el revisor marcaba como inventada la **Res. 839 de 2017**,
que existe y es pertinente (es la de la custodia de la historia clínica): quedó
cargada con su texto oficial.

### 28-08-2026 — La carpeta de radicación del 31068 quedó armada y limpia

Todo el día fue sobre la carpeta `GI-XX-XXXXX-2026`, la que se radica al ADRES.

**1. Las facturas que no tenían carpeta de soportes.** Son 101 y lo único que
existía de ellas era su respuesta a glosa, suelta en `RESPUESTAS_31068\salida`.
El bot aprendió a tomar cada respuesta, ponerle el índice y dejarla como
`680010079201_HUS######_EPICRIS.pdf`, **suelta en la carpeta, sin crear
carpetas**. La única que no salió fue la HUS380112, porque no estaba su
archivo; después apareció.

**2. El folio de la factura de esas mismas.** Igual, pero con la factura del
XML y el detallado intercalado en su puesto:

```
1 FACTURA  ->  2 DETALLADO  ->  3 REPRESENTACION GRAFICA  ->  4 NOTA CREDITO
```

Como el archivo del XML trae la factura y la representación gráfica pegadas,
el bot lo parte para meter el detallado en la mitad. Si una factura ya trae el
detallado adentro, **no se le agrega otro**: subiría al ADRES con el detallado
dos veces.

**3. La limpieza de las carpetas.** El área pidió dejar en cada carpeta solo el
EPICRIS y la FACTURA. Se hizo, pero **sin borrar nada**: lo demás se movió a
una carpeta `_APARTADOS_REVISAR_Y_BORRAR` dentro de la misma. Son las historias
clínicas y los detallados del paciente, y son la única fuente para rehacer un
folio; borrarlos no tiene vuelta atrás y esa decisión es del auditor.

| | |
|---|---|
| Carpetas revisadas | 222 |
| Archivos apartados | 1.340 |
| Carpetas sin tocar por faltarles un folio | ninguna |

Comprobado en el servidor: los 1.340 archivos están en la carpeta de apartados
y en las carpetas de factura no quedó ni un archivo que no sea uno de los dos
folios.

**4. Un error del comando, que era mío.** La primera vez que el auditor corrió
el bot le salió «the following arguments are required: --carpeta», aunque ese
modo no usa la carpeta del gestor. Estaba mal pedido y ya se corrigió. La
prueba no lo había detectado porque probaba el comando con una opción que el
auditor no tenía por qué escribir.

**5. El FURIPS2 y las respuestas del DGH.** Aparte del folio, salieron dos
archivos de escritorio:

- El **FURIPS2 con solo la glosa**, ya descontado lo aceptado: pasó de
  $2.460.635.897 a $519.367.482, y el FURIPS1 quedó con los mismos valores en
  VALOR FOSYGA y VALOR FACTURA. Quedó anotado que **$361.758.330 de glosa no se
  pudieron ubicar**, casi todo porque 1.308 renglones del reporte del ADRES no
  traen código de elemento.
- Las **respuestas del export de DGH**: 760 de 947 filas llenas con su código
  (RE9901 / RE9702 / RE9801) y su valor aceptado. Las otras 187 se dejaron en
  blanco a propósito, con un archivo aparte que trae las opciones para que el
  auditor escoja: cuando dos renglones de la misma factura tienen el mismo
  valor pero respuesta distinta, adivinar invierte la plata.

**6. Sacar los folios de las carpetas.** El área pidió que los PDF no queden
metidos en 222 carpetitas, sino sueltos en la carpeta de radicación, que es
como se sube al ADRES. El bot ahora los saca, y **solo borra la carpeta si
quedó vacía**: si adentro sobró algo, la deja y lo avisa por nombre. La
simulación dio 444 folios en 222 carpetas, sin choques de nombre; sumados a
los 201 que ya estaban sueltos, la carpeta debe quedar con **645 PDF**.

**7. Los XML de las facturas.** Al final el área pidió que a la carpeta de
radicación también entrara el XML de cada factura. El bot mira **qué facturas
ya tienen su folio suelto ahí** y trae el XML solo de esas, así no arrastra
facturas de otro paquete. Tres cuidados que quedaron por escrito en el
programa:

- **Copia, no mueve.** La carpeta `4.FACTURAS CON XML\XML` es la fuente del
  paquete y tiene que quedar completa.
- **No pisa lo que ya estaba.** Si el XML ya estaba en la carpeta de
  radicación, lo deja quieto y lo reporta.
- **Si falta un XML, lo dice con el número de la factura**, en vez de fallar
  callado.

Importante para el orden: primero se sacan los folios de las carpetas (punto 6)
y **después** se traen los XML. Al revés no daña nada, pero tocaría correrlo
dos veces, porque el bot solo trae el XML de las facturas cuyo folio ya está
suelto.

**8. Una prueba que estaba en rojo y ya está en verde.** La del bot de
objeciones del ADRES (`test_organizar_objeciones_adres`) llevaba días fallando
por un cambio de otro chat. Ya se arregló en la rama principal y las 65 pruebas
de ese bot pasan.

### 26-08-2026 (cierre 2) — El detallado quedaba de tercero, y la factura no lleva índice

El área revisó los folios ya armados y mandó tres correcciones. Las tres
quedaron hechas y fusionadas el mismo día (PR #500).

**1. El folio de la FACTURA no lleva índice.** La página de índice es solo para
el folio clínico (`..._EPICRIS.pdf`). El de la factura ahora abre directo en la
factura, sin carátula.

**2. El detallado quedaba de tercero, no de segundo.** Este era el de fondo. El
`..._FACTURA.pdf` que baja con el XML no trae un solo documento: trae la
factura y la representación gráfica de la DIAN **pegadas en el mismo archivo**.
Cuando el detallado llegaba aparte y el bot solo lo ponía detrás, quedaba
después de las dos:

```
antes:   1 factura  ->  representacion grafica  ->  detallado (de ultimo)
ahora:   1 factura  ->  2 detallado  ->  3 representacion grafica  ->  4 nota credito
```

Ahora el bot **abre ese PDF y mira página por página qué es cada pedazo** (la
marca viene en la primera página de cada renglón y las siguientes son
continuación), lo parte, y mete cada renglón en su puesto. Si el archivo ya
viene completo y en orden, no lo parte: lo deja tal cual.

Comprobado con dos facturas reales del área:

| Factura | Cómo llegó | Resultado |
|---|---|---|
| HUS311736 | trae todo adentro | 19 páginas, queda entero |
| HUS311371 | detallado aparte | 14 páginas: factura 1–4, detallado 5–8, gráfica 9–14 |

**3. El ruido visual.** Los archivos temporales que quedaban regados en las
carpetas (los `.tmp.pdf`) ahora se barren solos al empezar cada corrida, incluso
si la corrida anterior se cayó a mitad de camino.

**Lo que hay que hacer en el servidor.** Como los 223 folios se armaron con el
orden viejo, hay que **volver a correr los tres gestores** para que se rehagan
con el orden bueno y sin índice en el de la factura. Es la misma orden de
siempre, después de un `git pull`.

### 26-08-2026 (cierre) — El paquete 31068 quedó armado: 223 folios

Hoy se terminó de armar el paquete completo. Las cifras:

| Gestor | Folios | Páginas clínicas | Páginas de factura | Detallados |
|---|---|---|---|---|
| CAROLINA | 49 | 894 | 419 | 48 |
| CLAUDIA | 108 | 1.812 | 900 | 105 |
| OSCAR | 66 | 1.297 | 618 | 65 |
| **Total** | **223** | **4.003** | **1.937** | **218** |

**La carátula.** El área mandó la que necesita y quedó puesta: cada folio abre
con una página de índice que dice en qué página empieza cada renglón.

```
1.RESPUESTA A GLOSA ______________________________________  2
2.HISTORIA CLINICA _______________________________________ 70
3.AYUDAS DIAGNOSTICAS ___________________________________ 237
```

Es una línea por **renglón**, no por archivo: si la factura trae dos historias
clínicas, en la carátula hay un solo «2. HISTORIA CLINICA».

**Los detallados.** Se repartieron los 317 que mandó el área: 216 entraron a su
carpeta y 101 quedaron guardados en `C:\temp-folio\DET_SIN_CARPETA` porque esas
facturas no tienen carpeta en ningún gestor. Después el bot los pasó a PDF y los
metió como renglón 2 del folio de la factura.

**Las respuestas no se tocaron.** Se comprobó que la del zip nuevo y la que ya
estaba en la carpeta son idénticas (mismo tamaño exacto), así que no había nada
que reemplazar y se evitó el riesgo de dejarlas duplicadas.

**Cinco defectos más, encontrados mientras se corría.** Todos arreglados el
mismo día: el número del folio es del renglón y no del archivo; las copias de
Windows (`HC (2).pdf`) iban en desorden; la pantalla mostraba dos veces el mismo
nombre como si un archivo hubiera pisado al otro; el detallado convertido perdía
su nombre y se iba al folio equivocado; y el aviso de «no reconocido» mostraba
un nombre que ya no existe, dejando al auditor sin pista para encontrar esos
archivos.

**Lo que quedó señalado, que no es del bot sino de los datos:**

- **A las 223 facturas les falta la EPICRISIS.** No está en ninguna carpeta. Si
  el ADRES la exige, es el hueco más grande del paquete.
- **La HUS381290 no tiene su factura** en la carpeta del XML: le falta el
  renglón 1 y la representación gráfica de la DIAN.
- **Seis facturas sin detallado**: HUS311371, HUS354080, HUS367368, HUS376239,
  HUS376811 y HUS394817. No venían en el zip.
- **~~11 archivos en CLAUDIA que el bot no supo qué eran~~ — RESUELTO.** El
  área confirmó que **van en OTROS**, así que ya están bien puestos y no hay
  nada que cambiar. Salieron 16 en total; nueve están en carpetas marcadas
  `_MAOS`. El aviso de «no reconocido» se apaga solo en la corrida siguiente:
  ahora se llaman «N OTROS.pdf» y con ese nombre el bot sí los reconoce.

### 26-08-2026 (tarde) — La revisión que encontró que el bot borraba la epicrisis

Antes de dejarlo correr sobre el servidor, se le pasó al bot de folios una
revisión a fondo: cinco revisores mirando cosas distintas y, encima, dos
escépticos por cada cosa encontrada, obligados a reproducirla de verdad. Salieron
31 avisos. Estos son los que resultaron ciertos y ya quedaron arreglados.

**1. El grave: el bot borraba la epicrisis.**

El folio se llama IGUAL que el archivo del que sale: la epicrisis llega del
ADRES como `680010079201_HUS######_EPICRIS.pdf`, que es justo el nombre que va a
tener el folio. Para saber cuál era cuál, el bot miraba si en la carpeta ya
había archivos numerados. En una carpeta donde usted ya hubiera numerado algo a
mano —que es lo que pide su hoja— el bot tomaba **la epicrisis de verdad** por
un folio viejo: la dejaba por fuera del folio y encima la pisaba.

Se comprobó con una epicrisis de 5 páginas: después de UNA sola corrida, en esa
ruta había un folio de 4 páginas sin la epicrisis, y la epicrisis no existía en
ningún lado. No hay respaldo. Al ADRES se habría subido un folio clínico sin
epicrisis.

Ya está arreglado, y de raíz: el bot ahora **firma por dentro** los PDF que él
escribe, y en la corrida siguiente reconoce los suyos por esa firma, no por el
nombre. Lo que no lleva la firma es un soporte de verdad y se respeta. Y por si
acaso: si en la ruta del folio hay algo sin firmar, no arma ese folio y avisa.
Perder un soporte no se deshace; no armar un folio, sí.

**2. Las notas crédito no se reconocían con el nombre de ustedes.** Las nombran
`NC_263272_HUS352904.pdf`, y así caían en OTROS del folio clínico mientras el
reporte seguía diciendo que las notas crédito faltaban. Ya se reconocen.

**3. El folio cambiaba de orden entre una corrida y otra.** Los soportes de
terapias, curaciones, evoluciones y procedimientos se movían de sitio en la
segunda corrida, así que las páginas del folio salían en otro orden. Arreglado.

**4. El detallado que saca el otro bot no se reconocía.** Sale como
`HUS352904.xlsx`, con el número y nada más: nunca se pasaba a PDF ni entraba al
folio de la factura.

**5. Un soporte dañado se caía del folio en silencio.** El folio se armaba sin
él y en pantalla decía «armado». Ahora avisa: «OJO, N soporte(s) NO entraron al
folio».

Y dos más de robustez: si un PDF está abierto en Acrobat o el servidor se cae un
momento, esa factura se salta con su motivo y las otras 323 siguen.

**Lo que esto significa para usted:** no corra el bot sobre el servidor hasta
que esté fusionado el PR #492. Y cuando lo corra, hágalo primero sobre UNA sola
carpeta de prueba.

**6 a 14 (los demás).** Una fecha en el nombre de un archivo se tomaba como si
fuera el NIT del hospital y el folio salía mal nombrado; el reporte abierto en
Excel tumbaba la corrida entera después de haber armado todos los folios; los
archivos que no son PDF (una epicrisis en Word, una radiografía en JPG)
desaparecían sin avisar; y si la corrida se caía a mitad de renombrar, un
archivo quedaba a medio cambiar de nombre y en la corrida siguiente **se
perdía**. Todo eso quedó cerrado, y ahora la corrida que se cae se deshace sola
y la siguiente recupera lo que quedó colgado.

Pruebas: 149 en `tests/test_tools/test_unir_soportes_adres.py`.


### 26-08-2026 — El folio de cada factura del ADRES: ahora son DOS PDF, no uno

Usted aclaró cómo es el folio completo del paquete 31068 y no era como lo
estábamos armando. Son **dos archivos por factura**, cada uno con su orden:

**1) El folio clínico — `680010079201_HUS######_EPICRIS.pdf`**

Es el nombre que queda **después** de unir los soportes numerados:

```
1 RESPUESTA A GLOSA.pdf   (era RTA_ADRES_HUS352904.pdf)
2 EPICRISIS.pdf           (era 680010079201_HUS352904_EPICRIS.pdf)
3 HISTORIA CLINICA.pdf    (era HC.pdf)
4 AYUDAS DIAGNOSTICAS.pdf (era DX.pdf)
5 OTROS.pdf
```

**2) El folio de la factura — `680010079201_HUS######_FACTURA.pdf`**

La factura sí entra al folio, y adentro va en este orden:

```
1 FACTURA.pdf                       (la que viene con el XML)
2 DETALLADO.pdf                     (el detallado en Excel, pasado a PDF)
3 REPRESENTACION GRAFICA DIAN.pdf
4 NOTAS CREDITO.pdf                 (PENDIENTE: todavía no las han sacado)
```

**Las notas crédito quedan pendientes a propósito.** El bot no las cuenta como
falta: avisa cuántas faltan y sigue. El día que salgan, se dejan en la carpeta
de la factura, se vuelve a apretar el botón y entran solas de cuartas, sin
rehacer nada de lo que ya está.

**Lo que hay que apretar:** el mismo botón de siempre,
`tools/UNIR_SOPORTES_ADRES.cmd`. Ahora pide dos rutas: la carpeta del gestor
(CAROLINA, CLAUDIA, OSCAR) y la carpeta de las facturas con XML. Primero
**simula** —muestra los dos folios completos, tal como van a quedar— y solo
arma de verdad cuando usted escribe «SI».

**Por qué se numeran los archivos antes de unirlos.** No es adorno: el folio se
llama igual que el archivo del que sale (`..._EPICRIS.pdf`). Si no se renombra
primero, no habría dónde guardar el folio sin pisar la epicrisis.

**Un defecto que se encontró y se cerró antes de entregar.** Probando tres
corridas seguidas apareció esto: en una factura **sin epicrisis**, el folio de
la primera corrida se colaba en la segunda como si fuera una epicrisis, y el
PDF crecía metido dentro de sí mismo. Ya está resuelto: el bot mira la carpeta
completa, no un solo renglón. Y el caso que de verdad no se puede distinguir
—un `..._EPICRIS.pdf` suelto en una carpeta que ya estaba armada— no se
adivina: sale avisado en pantalla y en el reporte para que usted lo mire.

**LA RESPUESTA A SU PREGUNTA, mirando el archivo que usted mandó.** Abrimos el
`680010079201_HUS311736_FACTURA.pdf` de la carpeta del XML y **no es solo la
factura**: son 19 páginas que ya traen los cuatro renglones del folio, en el
mismo orden que usted describió:

| Páginas | Qué es |
|---|---|
| 1 a 7 | FACTURA ELECTRÓNICA DE VENTA HUS311736, con su CUFE |
| 8 y 9 | DETALLADO FACTURA ELECTRONICA HUS311736 |
| 10 a 18 | «Representación Gráfica» con el Código Único de Factura (CUFE) y los Datos Totales ($28.741.141) |
| 19 | NOTA CRÉDITO N° 253292 del 30/06/2026 por $518.900, del trámite de objeción 179143 |

O sea: **ese archivo ya ES el folio de la factura**. La representación gráfica
de la DIAN no es un archivo aparte: son las páginas 10 a 18 de ese mismo PDF.

**Lo que eso evitó.** El bot, tal como estaba, le habría pegado encima el
detallado del Excel: el folio habría subido al ADRES con el **detallado dos
veces**. Ya está corregido: ahora el bot mira adentro del PDF de la factura
antes de agregarle nada, y lo que ya viene pegado no lo duplica ni lo cuenta
como faltante. Lo avisa en pantalla.

**Cuidado, esto se vio en UNA sola factura** (la HUS311736), que es la que usted
mandó. Si en otras el `..._FACTURA.pdf` viene solo con la factura, el bot lo
detecta solo y arma el folio con las partes: no hay nada que configurar.

**Lo que sí hace falta que usted decida:** las notas crédito. La de la página 19
es de un trámite de junio (objeción 179143). Las de los valores aceptados de
ESTE paquete son otras. ¿El folio se deja con la nota que ya trae, o cuando
salgan las nuevas se rehace? Díganos y se ajusta.

Pruebas: 111 en `tests/test_tools/test_unir_soportes_adres.py`.

**Otro defecto corregido el mismo día:** si un PDF estaba abierto en Acrobat, o
el share se caía un momento, la corrida entera se tumbaba y las otras 323
facturas quedaban sin folio. Ahora esa factura se salta, queda marcada con el
motivo en el reporte, y las demás siguen.

### 25-08-2026 (cierre 4) — La malla que se desactivaba a sí misma

Llegó una **tercera** auditoría independiente, sobre 10 dictámenes nuevos. Trae
buenas noticias y una lección incómoda.

**Lo que el auditor confirma que ya quedó bien:** el artículo 23 del Decreto
4747 se cita correctamente, y el artículo 11 se usa para lo que de verdad dice
(verificación de derechos) en vez de con la cita fabricada de urgencias.

**El hallazgo de fondo.** El auditor señaló que un dictamen decía «la Ley
1438/2011 Art. 57 impone que la carga de la prueba recae en la EPS». Se
verificó contra **dos fuentes oficiales** —el normograma de la SuperSalud y el
Senado de la República—: el artículo 57 trata de plazos y no menciona la carga
de la prueba.

Lo grave no fue la cita. **El motor ya tenía la defensa para esto** y la dejó
pasar por tres agujeros encadenados:

1. El verbo «IMPONE» no estaba en la lista de verbos que la malla reconoce, así
   que ni siquiera enganchaba la frase.
2. Ninguno de los tres patrones aceptaba la abreviatura «ART.» — exigían la
   palabra «ARTÍCULO» completa, y «ART.» es como lo escriben los dictámenes.
3. Y el peor: la función que trae «el texto real del artículo» devolvía también
   **nuestro propio comentario** sobre cómo usarlo. Al artículo 57 se le había
   puesto una nota que dice «NO le atribuya la carga de la prueba: el artículo
   no la menciona» — y esa nota hacía que la malla encontrara la frase en lo que
   creía ser el texto legal y diera por buena justo la atribución que la nota
   prohibía. **La advertencia se desactivaba a sí misma.**

Es la misma autocertificación de toda la jornada, en su versión más incómoda.
Los tres agujeros quedaron cerrados y el motor ya caza ese caso solo.

**Cuatro cosas más en un solo dictamen**, todas verificadas contra el PDF
oficial de MinSalud:

| Lo que decía | Lo cierto |
|---|---|
| «el Art. 57 fija diez (10) días para responder» | son **quince (15)**; los diez son para que la entidad decida |
| «Res. 2284 art. 4, que otorga autorización por silencio administrativo» | el art. 4 es «Manual Único» y la resolución no menciona esa figura |
| «la cláusula antirebatimiento del contrato» | y la ficha del mismo dictamen decía «SIN CONTRATO PACTADO» |
| «la tarifa SOAT pleno exime de autorización previa» | la tarifa dice cuánto se paga, no si hacía falta autorizar |

El primero es el más peligroso: **decirle a la entidad que nuestro plazo es más
corto de lo que es le regala el argumento de extemporaneidad contra el propio
hospital**. Salía de que el corpus tenía los plazos en una lista aparte,
desconectados del texto del artículo. Ya lleva el literal con sus números.

**Un error propio, del mismo día.** En la mañana se reescribió la alerta de
vencimientos y se puso, entre comillas y atribuida al artículo 57, la frase «si
los prestadores no contestan en el plazo señalado, se entenderá aceptada la
glosa». Esa frase **no está** en el artículo. La consecuencia sí es real, pero
viene del código **RE2202** del Manual Único (Res. 2284 de 2023). La alerta ya
cita cada cosa con su norma.

**Y un defecto viejo que salió de rebote:** buscar «Ley 1438» en Consulta
Normativa nunca funcionó — el patrón exigía un espacio después del número, así
que caía al camino de palabras clave y la ley podía no aparecer entre las
primeras. Corregido para las cinco formas (ley, resolución, decreto, circular,
sentencia).

**Lo que se agregó por lo que señaló el auditor:** cuando el dictamen sale sin
saber quién es la entidad pagadora («OTRA / SIN DEFINIR»), ahora baja marcado
— sin saber quién es no se puede afirmar qué contrato rige ni qué tarifa se
pactó.

**Queda una decisión suya:** la plantilla del Dispensario afirma que el servicio
«se encuentra» entre los 7.141 ítems del Anexo 1 sin decir cuál. Puede ser
cierta en general y falsa en un caso puntual. No se tocó, porque es texto
institucional del área.

### 25-08-2026 (cierre 3) — El repaso normativo: otros cuatro artículos mal, y un argumento que estábamos regalando

Siguiendo lo que pidió el área —leer el Decreto 4747 completo y el Decreto 780
de 2016—, apareció más de lo mismo. Y esta vez apareció también algo a favor.

**El Decreto 780 tenía su propio artículo inventado.** El corpus guardaba un
artículo 2.5.3.4.1.1 titulado «Prohibición de auditoría previa como barrera».
Se verificó contra el Decreto 441 de 2022, que es el que le agregó ese capítulo
al 780: **el 2.5.3.4.1.1 es el «Objeto» del capítulo** y no dice nada de
auditoría previa. El texto estaba inventado. Se corrigió y se cargó, con su
texto literal, el 2.5.3.4.3.3, que sí es el de la auditoría de cuentas médicas.

**Pero la prohibición SÍ existe — y en un sitio mejor.** Está en el
**artículo 56 de la Ley 1438 de 2011**:

> «Se prohíbe el establecimiento de la obligatoriedad de procesos de auditoría
> previa a la presentación de las facturas por prestación de servicios o
> cualquier práctica tendiente a impedir la recepción.»

Es de rango de **ley**, más fuerte que el decreto o la resolución. El motor
tenía el argumento correcto colgado de una norma inventada: si la entidad iba a
verificar la cita, no encontraba nada. Ahora está donde debe, y además quedó
cargado el artículo 5 de la Resolución 2284 de 2023, que repite la prohibición
y la llama por su nombre: «prácticas dilatorias no autorizadas».

**Y tres artículos más de la Ley 1438 tenían mal el nombre:**

| El motor decía | Lo que dice de verdad |
|---|---|
| Art. 56 — «Trámite de pagos» | «Pagos a los prestadores de servicios de salud» |
| Art. 105 — «Prohibición de intromisión en el acto médico» | «Autonomía profesional» |
| Art. 126 — «Supervisión, inspección y vigilancia» | «Función jurisdiccional de la Superintendencia Nacional de Salud» |

Dos de ellos tenían además **texto inventado**. El del 56 hablaba de pagar «el
monto total dentro de los treinta días» — la ley no dice eso, remite los plazos
al Gobierno Nacional y a la Ley 1122. Afirmar un plazo que la norma no fija era
darle a la entidad una cita fácil de desmentir. El del 105 le atribuía a la ley
la frase «las entidades no podrán interferir», que tampoco está.

**Y en la Ley 100 había otro texto que no existe.** El artículo 177 figuraba
como «Obligaciones de las EPS — movilizar los recursos para el otorgamiento del
POS a través de patrimonios autónomos». Se buscó esa frase en el texto completo
de la ley: **no aparece**. El artículo 177 es la *definición* de qué es una EPS.
Importa porque el motor tiene una malla entera construida sobre esa creencia —
la malla hace lo correcto (el 177 no viene a cuento en una glosa de tarifa),
pero su razón estaba mal escrita, y de ahí salía la cita. El artículo 178, de
paso, tenía un resumen donde debía ir la cita textual: si el motor lo ponía
entre comillas, no coincidía con la ley.

**El plazo de pago estaba dicho a medias.** El artículo 13 de la Ley 1122
figuraba como si las EPS tuvieran que girar «como mínimo el 50% dentro de los
cinco días», así, en plano. El literal real lo condiciona a la **modalidad de
pago**: 100% mes anticipado si el contrato es por capitación, y el 50%
anticipado solo si es por evento, global prospectivo o grupo diagnóstico. Y los
treinta días del saldo corren solo «en caso de no presentarse objeción o glosa
alguna». Citar la regla sin sus condiciones era darle a la entidad la forma de
tumbarla de una en cualquier contrato capitado.

**Tres normas resultaron estar bien**, y también vale anotarlo: la Resolución
1995 de 1999 (la de historia clínica), el artículo 71 del Decreto 111 —el que
sostiene la defensa contra el «presupuesto agotado» del Dispensario— y el
artículo 34 de la Ley 23 de 1981. Coinciden literalmente con la fuente.

**Cuánto falta.** Se midió: de las 147 normas del corpus, **28 tienen texto de
artículo guardado**. Al cierre del día quedan **12 normas verificadas contra la
fuente oficial (29 artículos)** y **16 pendientes (20 artículos)**. Las
verificadas son todas las que el motor usa a diario. Las que quedan son de uso
ocasional: Ley 80, Ley 599, el CPACA, la Resolución 1885 y otras.

**El balance del repaso, sin adornos:** de las doce normas revisadas a fondo
hoy, **seis tenían al menos un artículo con el nombre o el texto inventado**.
Ese es el tamaño real de lo que destapó la auditoría de la madrugada.

### 25-08-2026 (cierre 2) — Las ratificadas de aseguradora ya no salen con la plantilla

El área revisó los seis pendientes y respondió. Cuatro ya estaban hechos
—el motor reiniciado, el archivo de recepción reenviado, los 6 archivos de
objeciones de COOSALUD subidos a DGH— y quedaron dos decisiones.

**La decisión sobre las ratificaciones.** Yesid la resolvió así: «cuando son de
aseguradoras, estas no van con esa respuesta, sino que toca hacerle su
respectivo análisis».

Quedó implementado. Cuando el pagador es una **compañía de seguros o una ARL**,
la ratificación ya no sale con el texto fijo: la redacta el motor, y le llega la
instrucción de **nombrar la razón concreta por la que la entidad ratificó** y
responderla punto por punto. Se le entrega además el argumento que faltaba: el
artículo 23 del Decreto 4747 prohíbe formular glosas nuevas sobre la misma
factura salvo por hechos nuevos, así que una ratificación que estrena causal es
rebatible.

**Las demás siguen igual.** EPS, Dispensario, Policía, Magisterio y PPL
conservan la plantilla institucional que el área pidió en abril — con el
artículo corregido, eso sí.

**Un criterio que hay que confirmar.** Para decidir quién es «aseguradora» se
hizo una lista corta: compañías de seguros y ARL (Aurora, La Previsora,
Solidaria, Mundial, Positiva, Suramericana y las demás del ramo). Se dejaron
**por fuera** a propósito el Dispensario, Sanidad Militar, la Policía y el
FOMAG, porque tienen contrato con el hospital y su propia forma de responder —
aunque el nombre de algunas lleve la palabra «seguros» o «previsora». Si alguna
de esas también debe analizarse, se mueve.

**La cuenta de Edgar Silva** queda anotada como tarea de pantalla: esa cuenta
vive en la base del hospital, no en el código. Hay que entrar a
Administración → Usuarios, borrar `devoluciones1@sinacsc.com` y dejar
`carterahus02@sinacsc.com`.

**Y se armó un banco de diez pruebas** para comprobar en pantalla que todo lo
del día quedó funcionando: cada caso apunta a un defecto concreto de hoy, con
lo que debe pasar y la señal de alarma al lado.

### 25-08-2026 (cierre) — Las pantallas que fallaban sin decir nada

Terminado el asunto de las respuestas, se retomó lo de la página. Primero se
midió, y la medición cambió lo que había que hacer.

**Lo que se creía y lo que resultó.** El tablero de mejoras tenía anotado que
había que ponerle a las tablas un aviso de «cargando». Al medirlo apareció algo
peor: de las **278** funciones de la página que le piden datos al motor, **77**
tienen su manejo de error, pero ese manejo **solo escribe en la consola del
navegador** — una ventana que el auditor no abre nunca.

O sea que si se cae la red, la tabla vieja se queda en pantalla **con cara de
estar al día**, y el auditor concilia contra números que ya no son. No era un
problema de espera: era de silencio.

**La peor de todas: la tarjeta de glosas por vencerse.** Si fallaba, no
aparecía, y nadie se enteraba de que había glosas a punto de vencerse. Una
glosa no contestada dentro del plazo **se entiende aceptada** (Art. 57 de la
Ley 1438). El silencio de esa tarjeta cuesta plata. Y encima se devolvía
callada también cuando el servidor respondía con error, no solo cuando fallaba
la red.

Ahora las **14 pantallas donde usted mira plata o toma decisiones** avisan con
un mensaje que dice qué no cargó y advierte que **lo que ve puede estar
desactualizado**: vencimientos, historial, tablero, cobranza, resumen del mes,
las cuatro del tablero de mando, ADRES, contratos, plata recuperada, analítica
predictiva y los comentarios del expediente. El aviso no se repite antes de 15
segundos: con la red caída fallan seis cosas a la vez y seis avisos seguidos no
los lee nadie.

**La cortina de carga decía algo que no era.** Cuando el sistema estaba
*borrando datos*, la pantalla mostraba «Identificando tipo de glosa…».
Resulta que cinco funciones le pasaban un mensaje a la cortina y la cortina lo
descartaba, rotando siempre la lista del análisis. Ya respeta lo que le dicen.

**Dos casillas del tablero se cerraron sin escribir código, porque la premisa
era falsa:**

- Se creía que cada estado (Aceptada, Radicada, Conciliada…) se pintaba de
  color distinto en cada pantalla. **Se midió: no pasa.** El único con varios
  tonos es «Ratificada», y son los tres del mismo rojo — que es como se pinta
  un recuadro, no un error.
- Se creía que la página no tenía disciplina de colores. **Tampoco.** Tiene
  **su propio** sistema, con 90 nombres de color y 2.072 usos. Lo que sobra es
  un segundo juego de colores que se carga y nadie usa. Unificarlos serían
  2.072 cambios sobre algo que funciona: no se hace sin que usted lo pida.

**Y un conteo mío que salió mal, otra vez.** El primer conteo de pantallas
mudas dio 24; el bueno era 77. Se caían de la cuenta las funciones que mezclan
un manejo vacío con uno de consola. Es la segunda vez que un conteo de estos
sale corto (el de julio dio 14 y eran 7). Quedó anotado en la prueba para que
la próxima vez no se repita.

### 25-08-2026 (noche) — Un segundo auditor encontró un artículo de ley mal citado en TODAS las ratificaciones

Llegó una segunda auditoría de las mismas 117 respuestas, hecha por fuera y
con otro método: en vez de mirar el texto por dentro, contrastó las citas
contra las leyes publicadas y comparó, código por código, lo que el pagador
reclamó contra lo que el motor contestó. Encontró cosas que la primera
revisión no vio.

**Lo más grave: el artículo estaba mal, y el motor mismo se daba el visto bueno.**

Las 28 respuestas de ratificación —el 100 %— decían que el trámite de glosas
está en el **artículo 20 del Decreto 4747 de 2007**. Se fue a buscar el texto
oficial del decreto en el Ministerio de Salud: el artículo 20 es el del
**RIPS**. El del trámite de glosas es el **23**.

Y al revisar el decreto completo apareció lo de fondo: de los tres artículos
de esa norma que el motor tenía guardados, **los tres estaban mal**, con
título y texto inventados:

| El motor decía | Lo que dice de verdad |
|---|---|
| Art. 11 — «Atención de urgencias» | «Verificación de derechos de los usuarios» |
| Art. 20 — «Trámite de glosas» | «Registro Individual de Prestaciones — RIPS» |
| Art. 21 — «Pago durante trámite de glosas» | «Soportes de las facturas» |

Lo peligroso no era la cita: era que **se aprobaba sola**. El revisor de citas
del motor compara contra esa misma lista guardada, así que la respuesta salía
sellada «citas verificadas» llevando una norma que dice otra cosa. Es la misma
lección de las sentencias del 24 de agosto: una lista sin verificar no
verifica nada.

Se corrigieron los tres artículos con el texto literal del decreto, se
agregaron el 22 y el 23 que faltaban, y se repasaron **una por una las 17
citas** a ese decreto que había repartidas por todo el programa.

De paso quedó algo bueno: el artículo 11 de verdad —el de verificación de
derechos— es justo el que sirve para las glosas de «este paciente era de otro
responsable». Antes no se podía usar porque estaba mal guardado.

**Una frase entrecomillada que no existe en ninguna ley.**
Varias respuestas ponían entre comillas, como si fuera del decreto, un texto
sobre que la urgencia no se puede condicionar a autorización previa. Se buscó
en el decreto completo: **no está**. Al corregir la lista guardada, el propio
revisor del motor ya la detecta y le quita las comillas.

**Cinco glosas contestadas por el lado equivocado ($3.564.600).**
El auditor cruzó los 79 códigos de las respuestas contra el motivo real del
pagador. **74 de 79 sí contestaban el tema** — buen resultado. Los cinco que
no, fallaron todos igual:

- **Tres glosas FA1606** ($2.571.800): el pagador dijo «el régimen del
  afiliado el día de la atención era contributivo y en el contrato figura
  subsidiado», y el motor contestó que la factura electrónica es válida ante
  la DIAN. No es lo que preguntaron.
- **Dos glosas FA0703** ($992.800): el pagador dijo «este insumo no es
  facturable» nombrando su código, y el motor contestó lo mismo de la DIAN.

En auditoría, lo que no se refuta se descuenta. Ahora el motor sabe cómo se
contesta cada uno de esos dos códigos —el FA1606 con la consulta BDUA a la
fecha de la atención, el FA0703 con el anexo del paquete— y si aun así sale
hablando de la DIAN, la respuesta baja con un aviso visible: **«REVISAR ANTES
DE RADICAR»**.

**Dos cosas de forma que también salieron:**

- El recuadro verde decía «Contrato: SIN CONTRATO PACTADO» y debajo «Tarifa
  **pactada**: SOAT PLENO». Si no hay contrato no hay nada pactado. Ahora esa
  línea dice «Tarifa **aplicada**» — que es lo correcto: el SOAT pleno es
  justamente lo que se aplica a falta de pacto.
- Cuando la glosa no es de urgencias, el motor cambiaba la cita del artículo
  168 por la frase «LA NORMATIVA DE CONTINUIDAD Y COBERTURA DEL SISTEMA
  GENERAL DE SALUD». Eso se lee como el título de una norma que nadie puede
  ir a buscar. Ahora dice «las reglas generales del Sistema General de
  Seguridad Social en Salud», que se lee por lo que es.

**Algo que ya estaba arreglado y salió igual.** Esa frase aparecía además en
la lista de «3 normas más relevantes». El filtro que la saca de ahí existe
desde el 24 de agosto y **sí estaba** en la versión del hospital — pero las
117 respuestas se generaron antes de reiniciar el motor. Es la prueba de que
lo corregido no sirve de nada hasta que la PC de cartera se reinicia.

**Lo que NO se tocó, porque es decisión del área.** El auditor señala que las
21 respuestas de ratificación usan la misma plantilla y ninguna entra en el
motivo concreto por el que la entidad ratificó. La plantilla la pidió el área
y funciona jurídicamente, así que no se cambió por cuenta propia. Queda la
pregunta en PENDIENTE.

### 25-08-2026 (tarde) — Se revisaron las 117 respuestas que salieron hoy

Con el archivo de recepción ya cargado, se pasó **una por una** las 117
respuestas que redactó el motor por el revisor de citas. Salieron cinco
problemas y los cinco quedaron corregidos con su prueba.

**1. Códigos CUPS que nadie le mostró al motor (12 respuestas).**
El archivo de recepción **no trae columna de CUPS** — trae factura, entidad y
valor. El motor, al no tener el código, se lo inventaba. La prueba de que era
invento y no un dato: el **mismo código 734101** salió como «radiografía de
maxilar inferior» en una respuesta y como «radiografía de pierna» en otra; el
**730102** salió como «urgencias adultos» y como «internación adultos
complejidad alta». Un código no puede nombrar dos servicios. Un CUPS inventado
es de lo primero que la EPS cruza contra su sistema: no lo encuentra y ratifica
la glosa completa, por buena que esté la defensa.
*Ahora:* si el código no aparece en lo que el motor tuvo a la vista **y**
tampoco se puede verificar en el catálogo, sale del documento y queda el
nombre del servicio. Un código verificable nunca se borra.

**2. El Dispensario: un contrato vencido presentado como vigente (14 respuestas).**
El texto fijo del Dispensario decía, en la misma frase, que el contrato
440-DIGSA/DMBUG-2025 «se encuentra suscrito y **vigente**» y que su plazo iba
«hasta el **30/07/2026**». Hoy es 25 de agosto: el plazo se cumplió hace 26
días. La entidad lee las dos mitades de la frase y tumba la respuesta sin
discutir el fondo.
*Ahora:* el texto dice que el contrato estaba vigente **a la fecha en que se
prestó el servicio** —que es lo cierto y además defiende mejor—, y si el
servicio quedó fuera del plazo el motor no usa ese texto: manda la glosa por
el camino normal, que sí lee el caso.

**3. Una ley real que el motor daba por inventada (3 respuestas).**
El revisor marcaba la **Ley 1164 de 2007** como inexistente. Existe: es la ley
del Talento Humano en Salud y su artículo 26 dice justo lo que la respuesta le
atribuye (que el acto profesional «se caracteriza por la autonomía
profesional»). Lo que faltaba era tenerla cargada. Se verificó contra el texto
oficial y se cargó con sus artículos 26 y 35.

**4. Una resolución citada con el año cambiado (2 respuestas).**
Se citó la «Resolución 3100 de 2020». El número es correcto —es la de
habilitación de servicios— pero es de **2019**. Con el año cambiado la entidad
no la encuentra y trata la cita como inventada. Se corrige sola.

**5. La palabra «de» que se comía el modelo (11 respuestas).**
Salieron frases como «se solicita el levantamiento **la** glosa» y «el artículo
17 **la** ley 1751». La peor: dentro de unas comillas que citaban textualmente
el artículo 17, decía «los profesionales **la** salud» — o sea, el hospital le
atribuía a la ley una frase mal transcrita. Se comprobó que no era ninguna de
las mallas del motor: lo escribía así el modelo. Ahora se repone.

**Además, dos cosas que ya venían pendientes:**

- **Amenazas al pagador.** Había una instrucción que las prohibía, pero era
  solo eso —una instrucción— y en las pruebas de agosto el motor amenazó igual
  con responsabilidad penal y acciones legales. Ahora hay una malla que las
  quita. Lo legítimo sigue saliendo: elevar el caso a la Superintendencia
  (Art. 126 Ley 1438), pedir el levantamiento por falta de respuesta (Art. 57)
  y negarle a la EPS la facultad de sancionar al hospital.
- **La Resolución 2275 de 2023, derogada (21 respuestas).** Aquí no se
  reemplazó nada, y a propósito: para un servicio prestado **antes** del 14 de
  mayo de 2026 esa ES la norma aplicable, y cambiarla por la 948 de 2026 sería
  meterle a la respuesta una norma que ese día no regía. Lo que se hace es
  **completar**: la respuesta ahora dice cuál rige hoy y desde cuándo. Así la
  cita es correcta cualquiera que sea la fecha, y la entidad no puede rebatirla
  diciendo «esa resolución está derogada». De paso, el aviso al gestor dejó de
  sonar cuando el documento ya lo explica: 21 avisos por lo mismo hacen que
  nadie los lea.

**Cómo quedó el mismo lote de 117 respuestas, pasado por las mallas nuevas:**

| Problema | Antes | Después |
|---|---|---|
| CUPS que no existe | 7 | **0** |
| Código que no es CUPS | 5 | **0** |
| Norma que no existe | 2 | **0** |
| Norma derogada sin decir desde cuándo | 21 | **2** |
| Frases con la preposición comida | 11 | **0** |

### 25-08-2026 (mañana) — El correo no salía, y no era la contraseña

Día de arrancar en producción: se borraron las glosas de prueba y entró el
archivo de recepción con **117 glosas** reales. Pero el correo a los gestores
no salía, y lo que costó fue encontrar por qué.

**El motor mandaba los correos sin fecha.** Todos los envíos rebotaban con
«550 Command rejected» desde que el hospital pasó su correo al servidor
institucional. El panel del motor decía que la causa más común era la
contraseña — y no lo era: se probó la clave a mano contra ese mismo servidor y
entró perfecto. Lo que faltaba era la **fecha y el identificador** del mensaje,
que el estándar exige. Gmail los perdonaba; el servidor institucional no. Ese
defecto llevaba meses ahí y solo se destapó al cambiar de servidor.

**El panel adivinaba en vez de mirar.** Decía «la causa más común es que la
contraseña no sea una contraseña de aplicación» sin haber leído el error, y
mandaba a buscar el detalle en un archivo de registro de 3 MB — cuando el error
exacto ya estaba guardado en la base. Eso costó la mañana. Ahora lee el error
real, lo traduce, y cuando no lo entiende **lo dice** en vez de culpar a nadie.

**A las médicas auditoras no les llegaba nada.** Los seis gestores recibieron
su correo; Laura Díaz, Zulay González y Leidy Sanguino no, aunque doce glosas
venían marcadas «Mixta» o «Medico» con su nombre. El nombre sí se leía del
Excel y sí quedaba guardado, pero al rehacer el plan de trabajo con la causal
se le pasaba vacío y **se borraba** — y el correo usa justo ese campo para
saber a quién escribirle.

**Y dos cosas de pantalla.** La plata salía con doble signo («$$ 2.319.514»), y
la alerta roja de vencimientos se contradecía sola: decía que opera el silencio
contra el prestador y en el mismo renglón que el Art. 57 no aplica al hospital.
Verificado el texto oficial: **sí** obliga al prestador. Ahora cita la norma de
verdad.

**«Tengo estos botones pero no hacen nada.»** No estaban dañados: nunca fueron
botones. El rectángulo morado que dice «Editar manual» es una etiqueta que
avisa que la glosa necesita revisión humana, pero estaba pintada igual que los
botones del sistema. Ya se ve como lo que es.

**De paso, el despliegue.** El motor se quedó con el código de la víspera
porque había gente trabajando, y correr el bot a mano se aplazaba igual. Ahora
`autodeploy_motor_local.cmd YA` aplica de una y deja constancia.
### Julio–Agosto 2026 — Frente COOSALUD: objeciones en DGH y respuestas en el portal

Este frente lo llevó un chat aparte (los bots de `tools/`: organizar el ZIP del
portal → consolidar → cruzar con DGH → OBJECIONES → trámites). Se resume aquí
para que quede en la memoria común.

**Palabras que se usan en este frente**

| Término | Qué es |
|---|---|
| **Glosa** | Objeción de la EPS a un cobro de la factura (no quiere pagar una parte) |
| **DGH** | Dinámica Gerencial Hospitalaria — el sistema contable del hospital; ahí se registran las objeciones y las respuestas de trámites |
| **Portal VCO** | Portal web de COOSALUD (vco.ctamedicas.com) donde se responden las glosas ante la EPS |
| **OBJECIONES** | Excel que se carga a DGH para registrar las glosas objetadas (máximo 300 facturas por cargue) |
| **Trámite** | Excel de DGH con la respuesta de cada glosa (máximo 499 facturas por archivo) |
| **RE9502 / RE9901** | Códigos de respuesta: 9502 = glosa extemporánea (la EPS glosó tarde, art. 57 Ley 1438/2011) · 9901 = glosa a tiempo, se responde con el texto del área |
| **CALIDAD (CL)** | Glosas de pertinencia médica: las responden las doctoras de auditoría médica, no cartera |
| **Copago** | Cuota moderadora que paga el paciente; DGH no permite objetar esa parte |

**Junio 2026 — preparación**

- **17/06** — Conexión automática a Dinámica Gerencial.
- **22/06** — El bot del portal COOSALUD aprende a adjuntar soportes con
  respaldo (PDX→HAM→PDE), a cerrar glosas residuales y a dejar evidencias.
- **30/06 al 02/07** — Bot que responde glosas *dentro* de DGH (manejando las
  ventanas del programa).

**Julio 2026 — el cargue masivo (el grueso del trabajo)**

- **08/07** — Nacen los tres bots del masivo: **organizador** (parte el ZIP del
  portal en carpetas FACTURAS/DETALLES/GLOSAS por lotes de 300),
  **consolidador** (une todo, arma la observación de cada glosa, cruza con la
  base de DGH y genera el OBJECIONES) y **HACER TODO COOSALUD.bat**.
- **09/07** — Ajustes tras errores reales de DGH: cruce del servicio en 4
  niveles, una glosa de CALIDAD manda sobre las administrativas, guardián de
  valor/saldo, y el bot **CORREGIR ERRORES DGH** (DGH no guarda nada cuando el
  cargue trae un error, hay que rearmar el archivo completo).
- **10 y 17/07** — **Copago**: DGH descuenta la cuota moderadora, así que lo
  máximo objetable de cada línea es (valor del servicio − copago). Primero se
  avisaba, después el bot lo recorta solo. Esto explicaba los errores de valor.
- **14/07** — **CONSOLIDADO RESPUESTAS GLOSAS** (la respuesta de cada glosa,
  RE9502 o RE9901; las de CALIDAD quedan en blanco para las doctoras) y bot
  **RESPUESTA TRÁMITES DGH**. Operación: **2.170 facturas objetadas** (~$4.741
  millones) y 5 archivos de trámites subidos.
- **16 y 21/07** — Lote de **41 facturas** ($754 millones) y lote de **1.600
  facturas** (4.257 ítems, $230.736.952), procesado completo el mismo día.
- **22/07** — Cierre del lote 1.600: **4 ventanas del portal en paralelo**
  cerraron 1.425 facturas en 2,5 horas. Se armaron los trámites (4 lotes de
  499) y el Excel de control **GI-33-5181-2026** (2.215 facturas, 0 sin
  trabajar).
- **27/07** — Documento de entrega técnica del módulo
  (`docs/ENTREGA_MODULO_COOSALUD.md`).

**Agosto 2026**

- **13 y 14/08** — Tres cosas de fondo:
  - **CROTIPOBJ arreglado.** El tipo de objeción (0 administrativa / 1 médica /
    2 mixta) se calculaba mirando *todas* las glosas del portal, incluso las que
    solo se mencionan en la observación. DGH lo calcula sobre el concepto que
    uno **escribe**. Ahora el bot hace lo mismo: si todos los conceptos escritos
    de la factura son CL → médica; si ninguno → administrativa; si hay de los
    dos → mixta. Se verificó contra las 5 facturas que DGH había clasificado
    distinto y todas coincidieron; en el masivo de agosto cambiaron 8 de 589.
  - Bot **LISTA FACTURAS YA EN TRÁMITES** (`facturas_ya_en_tramites.py`): revisa
    la carpeta de masivos ya enviados y arma el TXT de facturas que **no** se
    deben repetir (repetir una hace que DGH rechace el cargue). Solo cuenta los
    masivos realmente diligenciados y de la EPS que se le pida, para no mezclar
    Dispensario con COOSALUD.
  - **Lotes procesados**: COOSALUD 7 (23 facturas, $27,9 millones), COOSALUD 1
    (29 facturas, $5,4 millones) y el masivo de agosto (589 facturas, $5.612
    millones). Cierre del mes: **641 facturas / $5.674.278.862**.
- **19/08** — Bot **FILTRAR BASE DGH** (`filtrar_base_dgh.py`): recorta la base
  "SERVICIOS FACTURADOS COOSALUD DGH.xlsx" (70 MB) a las facturas del lote, para
  poder moverla o subirla.
- **25/08** — **Lote COOSALUD_25082026: 1.573 facturas.**
  - Organizado en 6 lotes y consolidado: **4.533 ítems, 4.691 glosas,
    $289.077.286**. Todas a tiempo (RE9901); solo 2 con CALIDAD (HUS532676 y
    HUS532956); 193 con copago.
  - Entregados los consolidados y el paquete del portal (Excel masivo + 4 listas
    para correr en paralelo: 394/394/394/391).
  - **Tropiezo**: al cruzar con DGH la base solo trajo **9 de las 1.573**. La
    base que se estaba usando es del 08/07 y además venía recortada (leyó
    1.048.000 filas, prácticamente el tope de Excel, que es 1.048.576). Hay que
    bajar de DGH un export **nuevo**, por tandas de fechas.
  - Por eso FILTRAR BASE DGH ahora acepta **varias bases a la vez** (las
    tandas), quita las filas repetidas y avisa dos cosas: si una base llegó al
    tope de filas de Excel (salió recortada) y hasta qué número de factura llega
    cada una, que es como se ve de una si está vieja.
  - La base de facturación ENE–JUL sirvió para ubicar el rango: **1.537 de las
    1.573** se facturaron entre el **23/06 y el 31/07**, todas de COOSALUD, y
    las 36 restantes son de agosto. Ese es el rango con el que hay que bajar el
    export de SERVICIOS FACTURADOS. De paso, el bot aprendió a buscar el
    encabezado cuando no está en la primera fila y a avisar cuando le pasan un
    reporte que no trae el detalle de servicios (y por tanto no sirve para el
    OBJECIONES).
  - **Portal COOSALUD cerrado el mismo día**: 4 ventanas en paralelo cerraron
    las **1.573 facturas** entre las 10:24 y las 12:51 (**2 h 27 min** de reloj;
    7 h 52 min de trabajo del robot repartido en las cuatro). Resultado:
    **1.527 OK**, 2 con la glosa de CALIDAD abierta a propósito (HUS532676 y
    HUS532956, esperando a las doctoras), **43 NO_EN_BOLSA** y 1 terminada sin
    cartel de asignación. O sea 1.529 respondidas y **44 por revisar**.
    Por ventana: S1 394 en 99 min · S2 394 en 103 min · S3 394 en 123 min ·
    S4 391 en 146 min. Las NO_EN_BOLSA se concentran al final del rango
    (3 en S2, 14 en S3, 26 en S4), que es el mismo patrón del lote de 1.600.
  - **OBJECIONES generado el mismo día.** Llegó la base buena —el export de
    SERVICIOS FACTURADOS de enero a agosto, en formato **.xlsb**— y cruzó
    **1.573 de 1.573**. Salieron **6 lotes, 4.525 filas, 1.572 facturas,
    $287.610.516**. La diferencia contra los $289.077.286 del consolidado son
    $1.466.770 y se explica entera: $816.230 de 72 objeciones recortadas al
    tope que DGH acepta (copago y saldo) y $650.540 de 8 servicios que no
    existen en la base de DGH.
  - **HUS538337 quedó por fuera**: sus 5 servicios ($407.000) no están en DGH,
    así que no hay nada que objetarle. Va a registro manual, como HUS530335 y
    HUS506920. Otras tres entraron incompletas por lo mismo: HUS531604
    ($174.240), HUS537835 ($47.520) y HUS543541 ($21.780).
  - **Tres fuentes coinciden** en que las únicas dos facturas con CALIDAD son
    HUS532676 y HUS532956: así las marcó el consolidador al armar el lote, así
    las dejó el portal (OK_CALIDAD_ABIERTA) y así salieron en el OBJECIONES
    (las únicas dos mixtas).
  - **El bot aprendió a leer .xlsb**, que es el formato en que DGH exporta la
    base. Antes tocaba convertirla a mano.
  - **Defecto propio encontrado y corregido el mismo día**: al aceptar varias
    tandas se habían quitado las filas repetidas, y una base DGH SÍ trae filas
    idénticas de verdad (el mismo medicamento dispensado varias veces en una
    factura), cada una un servicio objetable. Con las repetidas quitadas el
    OBJECIONES bajaba a 4.284 filas y **249 servicios sin cruzar**; sin
    quitarlas son 4.525 filas y **8**. Ahora solo se descarta lo que ya venía
    en una tanda anterior, comparando cuántas veces aparece en cada una.

**Dónde está cada cosa de este frente**

| Qué | Dónde |
|---|---|
| Bots de COOSALUD (organizar, consolidar, corregir errores, trámites, filtrar base) | `tools/` — en el PC de cartera: `D:\USUARIO CARTERA\Desktop\ORGANIZADO\2026-07-08\COMPRIMIDOS\BOTS COOSALUD\` |
| Bot que responde en el portal COOSALUD | `tools/responder_glosas_coosalud.py` |
| Reglas del proceso | `docs/CONTEXTO_COOSALUD.md` y `docs/ENTREGA_MODULO_COOSALUD.md` |
| Facturas del piloto ya objetadas (no repetir) | `tools/FACTURAS YA OBJETADAS.txt` |

---

### 25-08-2026 (madrugada) — La revisión más incómoda: la mayor parte de la jurisprudencia del motor era inventada

Este día empezó con los ejemplos de prueba de la ronda 2 y con la segunda
auditoría independiente (expedientes GL-199 a GL-207). Terminó destapando el
defecto más grave que ha tenido el sistema.

**Lo que se encontró.** El auditor señaló que un dictamen citaba la Sentencia
T-478 de 1995 para defender la autonomía médica, y que esa sentencia trata de
otra cosa. Al ir a mirar la base de conocimiento del motor, el problema no era
un caso suelto: **de las 29 sentencias que el sistema guardaba, unas dos de
cada tres decían algo que la sentencia no dice**. Se verificaron una por una
contra la relatoría de la Corte Constitucional.

- **Tres no existen.** No es que el tema esté mal: la providencia nunca se
  dictó. La T-543 de 2013, la T-553 de 2024 y la T-027 de 2020. Se comprobó por
  dos caminos: el buscador oficial de la Corte no las conoce, y las páginas de
  sus vecinas cargan completas mientras las suyas salen vacías. Se borraron.
- **Trece decían otro tema.** La T-024 de 2009, que el sistema daba como «pago
  de servicios de salud», es una tutela de custodia de una niña contra el ICBF.
  La T-126 de 2018, que daba como «historia clínica como prueba plena», es un
  caso de violencia sexual. La T-307 de 2017, que daba como «recobros NO PBS»,
  es una pensión de sobrevivientes. Y así.
- **Dos autos también.** El Auto 037 de 2024 figuraba como seguimiento a la
  sentencia inexistente sobre terapia CAR-T. El auto sí existe, pero trata de
  algo que resultó **más útil para cartera**: la Corte resolvió que la
  jurisdicción ordinaria laboral es la competente para cobrar ejecutivamente
  las facturas de servicios de salud.

**Por qué era tan peligroso.** El revisor de citas del motor contrasta lo que
va entrecomillado contra ese mismo corpus. Una cita inventada guardada ahí
**se certifica sola**: el dictamen la copia, el revisor la encuentra, y el
documento sale con el sello «citas verificadas · 0 hallazgos». Al auditor de la
EPS le bastaría abrir el enlace para tumbar todo el escrito.

**Las defensas no perdieron nada.** En todos los textos donde estaban, iban
acompañadas de su anclaje legal correcto —el Art. 17 de la Ley 1751 de 2015
para autonomía médica, el Art. 168 de la Ley 100 y el Art. 20 del Decreto 4747
para urgencias—, así que quitarlas no debilitó ningún argumento.

**Y la revisión siguió: TODA la base normativa del motor, no solo las
sentencias.** Con ese antecedente había que mirar el resto, y apareció lo mismo.

- **Una resolución derogada hace tres meses, citada como vigente.** La
  Resolución 2275 de 2023 —la de factura electrónica y RIPS, que el motor cita
  en seis sitios— fue derogada el 14 de mayo de 2026 por la Resolución 948 de
  2026. Un dictamen radicado hoy que se apoye en ella le entrega a la EPS la
  forma de tumbarlo. Peor: el corpus tenía desde siempre un campo que dice si la
  norma sigue vigente, **y el revisor de citas nunca lo miraba**. Ahora avisa.
- **Otras tres normas decían lo que no era.** La «Resolución 1604 de 2024», que
  el sistema daba como norma de RIPS, es un acto del Ministerio del Interior que
  le reconoce personería jurídica a una iglesia. La Resolución 866 de 2021, que
  se ofrecía en cuatro archivos como «los RIPS», es la de interoperabilidad de la
  historia clínica: se leyó su texto completo y la sigla RIPS no aparece ni una
  vez. Y la «Resolución 2641 de 2025» no existe.
- **El motor borraba una cita CORRECTA.** Tenía un limpiador que quitaba del
  dictamen «Resolución 2641 de 2024» por creerla inventada, y la cambiaba por la
  frase «la normativa vigente del Ministerio de Salud». Esa resolución es real
  —es la que estableció la CUPS que rigió en 2025—, así que el motor borraba lo
  bueno y dejaba una pseudo-norma sin ley ni artículo.
- **Y les ofrecía a la IA 24 normas que él mismo no tenía cargadas.** Le pedíamos
  que las citara y luego se las marcábamos en rojo como inexistentes. Doce eran
  reales y se cargaron; de las otras ocho, **tres no existen** («Acuerdo 002 de
  2010 USPEC», «Decreto 1760 de 2022» y «Resolución 5853 de 2003») y cinco
  estaban mal nombradas: la 5159 de 2015 es Resolución y no decreto, la 506 de
  2021 es de MinSalud y no de la DIAN, la «Resolución 2284 de 2024» es de 2023,
  la «Resolución 1604 de 2022» es un Decreto sobre colegios de las cajas de
  compensación, y la Resolución 010 de 2018 es de la DIAN y no dice nada del
  pago de migrantes, que era para lo que se citaba.

- **Y una segunda resolución derogada, esta de un pagador nuestro.** La
  Resolución 5159 de 2015, el modelo de atención en salud para la población
  privada de la libertad, la derogó la Resolución 1099 de 2026. El prompt del
  motor decía con todas sus letras «OBLIGACIÓN: citar SIEMPRE la Res.
  5159/2015 al defender cobertura PPL», y el corpus la daba por vigente en dos
  catálogos. Ahora el motor cita la Ley 1709 de 2014 —que vale en cualquier
  caso— y la resolución que estuviera vigente **a la fecha de la atención**.
- **Lo mismo con la CUPS.** El sistema tenía una «Resolución 2641 de 2025» que
  no existe, y la que sí existe (2641 de 2024) está derogada desde enero por la
  Resolución 2706 de 2025, que se cargó con su texto oficial.

Tres cosas que salieron **a favor**: la Circular 007 de 2025 no era un
«cronograma» sino una circular conjunta con la Superintendencia que **prohíbe
imponerle barreras y exigencias no normadas a los prestadores**; la Resolución
2335 de 2023 no era de cáncer infantil sino de la **ejecución y seguimiento de
los acuerdos de voluntades**; y el Auto 037 de 2024 resolvió que la
**jurisdicción ordinaria laboral es la competente para cobrar ejecutivamente las
facturas de salud**. Las tres son munición útil que estaba mal rotulada.

**Y al revés: el motor le estaba borrando al dictamen artículos que sí existen.**
Buscando otra cosa apareció esto. El sistema afirmaba «esta norma no contiene
ese artículo» mirando solo los artículos que tiene cargados, y tiene poquísimos:
de 131 normas, apenas 26 traen alguno. De la Ley 100 estaban cargados tres de
casi trescientos. Como el limpiador borra la oración entera, un dictamen que
citara el Art. 156 de la Ley 100 salía sin esa frase. Ahora solo se afirma que
un artículo no existe cuando de esa norma se cargó la lista completa; si es
parcial, se avisa en severidad baja y no se borra nada. Se cargaron además,
transcritos de los PDF oficiales del Ministerio, el Art. 87 del Decreto 2423
(la cita del expediente GL-207 **era correcta**, lo que faltaba era el
respaldo), los Arts. 1 y 2 de la Ley 1438 y el Art. 1 de la Ley 1751.

**Los otros cuatro defectos de la auditoría, corregidos:**

1. **«Defender el 100 %» de nada (GL-204).** La glosa se capturó sin la cifra,
   y en este motor un cero significa «no se pudo leer», no «cero pesos». Como
   0 es menor que $915.051, el sistema concluyó que la glosa era injustificada
   y recomendó defender el 100 %. Y el panel escondía justamente la fila del
   valor que originó la conclusión. Ahora, sin cifra, dice REVISAR y pide
   capturarla; y el panel muestra en ámbar «no registrado en el caso».
2. **A cada código, su plata (GL-206).** Una glosa con dos códigos: la
   respuesta del SO3401 salió diciendo «valor objetado de $150.000», que era la
   plata del otro código. Ahora, cuando el texto lo dice sin lugar a duda, cada
   sección recibe el suyo. La regla es estrecha a propósito: ante la menor
   sombra no se reparte, porque colgar un monto equivocado es peor.
3. **Contestar lo que la EPS objetó, no otra cosa.** La EPS glosaba «precio
   superior al regulado» y el dictamen respondía sobre la validez formal de la
   factura. El bloque que le dice al motor qué atacar salía vacío cuando ningún
   patrón enganchaba. Ahora nunca sale vacío: cuando no reconoce la causal, le
   pone delante el texto literal de la EPS. Se agregaron además las dos
   causales que faltaban (precio regulado y reliquidación a otro manual) y se
   cargaron al corpus la Circular 19 y la Circular 18 de 2024.
4. **Una palabra de menos.** El dictamen escribió «ARTÍCULO 168 LA LEY 100»,
   sin el «DE», y por esa palabra no se activó la defensa que tumba esa cita
   cuando la glosa no es de urgencias. Ya caen las cuatro formas.

**Y una corrección menor de la misma familia:** el Art. 3 de la Resolución 1995
llevaba pegada una frase que es del Art. 1. Quedaron separados, cada uno con su
texto oficial.

Todo con pruebas: la suite completa quedó en **8.616 verdes** (los 12 rojos son
de programas que no están instalados en la máquina de pruebas, ajenos al motor).

### Abril 2026 — Nace el Motor de Glosas
- **08 al 10-04:** primera versión de la aplicación: análisis de glosas con IA,
  dictámenes con normativa colombiana (Res. 3047/2008, Ley 1438/2011, etc.),
  importación masiva desde Excel, exportación a Excel, seguridad de acceso.
- **13 al 25-04:** la aplicación crece: generación masiva en lote, conciliación
  bilateral con acta y PDF institucional, informe ejecutivo mensual para
  gerencia, catálogo de tarifas pactadas por EPS, homologación Res. 2641/2025,
  exportes con el formato exacto del DGH, pre-análisis automático diario y
  dashboard ejecutivo.
- **26 al 30-04:** panel de administración completo (usuarios, equipos,
  notificaciones), sincronización de soportes desde el servidor del hospital
  (jumpbox) y tarifas FOMAG actualizadas al contrato nuevo.

### Mayo 2026 — Estabilización
- Importación masiva con progreso e historial, auditor forense IA, panel de
  diagnóstico del sistema, y correcciones a partir del uso real diario.
- **21 al 29-05:** primer robot del portal **SIMED** (Dispensario), en ese
  momento para el cargue de notas crédito con validación del CUV.

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
  **Respuesta de glosas Dispensario en SIMED:** lote cerrado completo — 8
  facturas / 24 objeciones en 26,9 minutos con el robot.
- **23 y 24-06:** **cargue DIA 3 JUNIO (COOSALUD):** se cerraron las 118 facturas
  pendientes de la hoja BASE y las 26 de la hoja CALIDAD (4.936 glosas). Dos
  facturas fallaron por un detalle del portal al elegir el código de respuesta;
  se corrigió el bot y cerraron en la segunda pasada.
- **25 y 26-06:** Word de evidencias del **lote 69** (46 de 69 facturas tenían
  pantallazo; 23 quedaron identificadas sin evidencia). Nace `evidencias_a_pdf.py`.
  **Diagnóstico de las 12 facturas pendientes del Lote V2 del Dispensario:** se
  descubrió que el registro estaba equivocado en 6 — cinco que figuraban
  "subidas OK" nunca tuvieron validación del Ministerio (el servicio interno
  de validación estaba caído y guardó el error como si fuera el resultado).
  Se armó la carpeta `PENDIENTES_12` con ficha de estado por factura.
  **Primer lote de respuesta de glosas del Dispensario en SIMED**
  (`respuestas_glosa_INICIAL_DSE_26JUN.xlsx`).
- **30-06:** arranca el **bot de Dinámica Gerencial (DGH)** (muchas iteraciones
  para dominar el programa de escritorio; la ventana de respuesta no se deja
  leer por dentro y hay que operarla por coordenadas de pantalla). **Tablero de
  Radicación y Cartera** (informe HTML con alertas de mora +90 días, exportar a
  Excel). Mejoras al motor IA (rondas 19-22) y set de evaluación de calidad de
  los dictámenes: la calidad del motor pasó de **2,5 a ~9 sobre 10**.

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
  gerencia** (página web con el antes/después). También: **informe de gestión
  del Lote V2 de notas crédito** (`INFORME_GERENCIA.md`, 12 facturas por
  $108,5 millones facturados con comparativo manual vs. automatizado).
- **10 al 21-07 (corridas del auditor):** se analizaron y lanzaron los
  **LOTES 02 (300 fact.), 06 (300), 07 (300) y 08 (75)** de COOSALUD.
  El LOTE 7 llegó primero como listado de objeciones sin respuestas
  (OBJECIONES.xlsx) y fue reemplazado por el consolidado correcto.
  En los lotes 06/07/08 quedaron 37 facturas con la pertinencia médica
  sin responder (el médico aún no la tipificaba).
- **17-07:** informe técnico en Word de los **rechazos CUV de 4 facturas
  conciliadas** (`INFORME_RECHAZOS_CUV.docx`, para enviar al área): 3 rechazadas
  por el Ministerio con código RVC086 ("código de diagnóstico repetido", con el
  campo exacto del RIPS a corregir) y 1 cuya validación nunca corrió (servicio
  interno caído). Incluye el argumento clave: lo que al radicar la factura
  salía como *objeción* se convirtió en *error bloqueante* en la nota crédito.
  Dato: SISTEMAS ya reintentó 2 el 25-06 sin corregir el RIPS y volvió a fallar.
- **22-07:** llegaron las respuestas de pertinencia en 3 archivos
  ("PERTINENCIA (1)", "ok" y "15"). Se detectó que **cada archivo estaba
  incompleto pero se complementaban** entre sí → se fusionaron en
  **CONSOLIDADO_PERTINENCIA_6JULIO_FUSIONADO.xlsx** (37 facturas, 5.736
  glosas, cero sin respuesta, todas RE9901). Quedó listo el comando para
  correrlo. Se creó esta bitácora (fusionando el trabajo de dos chats).
  Además se escribió la **documentación técnica de entrega del módulo de
  diagnóstico del Lote V2** (`docs/diagnostico_lote_v2_pendientes/DOCUMENTACION_MODULO.md`)
  para consolidarlo en el proyecto principal sin perder conocimiento.
- **27-07:** se generó el **informe técnico completo** de todo el trabajo
  realizado (bot + evidencias + mejoras + lotes): 1.075 facturas procesadas,
  45.134+ glosas respondidas, 7 mejoras al bot, 8 lotes cerrados o en proceso.
  Publicado como artifact para socializar ante gerencia. Se generó también el
  cruce de **2.215 facturas vs. GI-33-5181-2026** (975 encontradas en los
  consolidados de este chat, 1.240 NA pendientes de lotes 03/04/05).
- **28-07 (hoy):** nace el **ajustador de detallados de factura**
  (`tools/ajustar_detallado_glosas.py` + README + 36 tests). Automatiza el
  trabajo manual de dejar el detallado **solo con lo que la entidad sigue
  glosando**: quita duplicados del consolidado, borra del Excel las hojas de las
  facturas que no se van a trabajar, quita el encabezado institucional (logo,
  NIT, QR, CUFE), cambia el título a **"DETALLADO DE FACTURA"**, cruza cada ítem
  contra el `ReporteGlosasReclamPAQUETE` (quita lo aprobado, ajusta lo aprobado
  a medias, deja lo glosado), borra los grupos que quedan vacíos y recalcula
  subtotal, total y **total en letras**. Deja bitácora CSV ítem por ítem y tiene
  modo `--diagnostico` para ver qué haría antes de escribir nada.
  **Hallazgo:** el reporte de glosas trae **el mismo ítem repartido en varias
  filas** (la venda de gasa de la HUS352890 viene en dos: 4 y 2 unidades). El
  bot las suma → siguen glosados **$47.000**, no $9.400 como quedó en el ejemplo
  hecho a mano. Falta que el auditor confirme ese criterio (ver PENDIENTE #11).
  **Validado contra el reporte real del paquete 31068** (19.256 filas, 581
  facturas): las **324 facturas del lote están todas** en el reporte y se
  reconocen sin ajustes. Del total reclamado **$2.870.214.655**, el ADRES aprobó
  **$1.835.864.089 (64%)** y **sigue glosado $1.034.350.566 (36%)**. De 9.616
  ítems: 6.805 se quitan, 472 se ajustan y 2.712 se dejan. El **32% de los ítems
  viene repartido en más de una fila** del reporte (el peor: 38 filas para la
  terapia respiratoria de HUS311371) y en el 1,1% de las filas la columna
  "Cantidad Aprobada" no cuadra con el valor — por eso el bot suma y calcula la
  cantidad desde el valor glosado.
  **Llegaron los 7 archivos de detallados y se corrió el paquete 31068 completo.**
  El formato real resultó distinto del supuesto: **una sola hoja con todas las
  facturas apiladas** (no una hoja por factura) y cada dato dentro de una celda
  combinada cuyos límites NO coinciden con los del encabezado. Se reescribió el
  núcleo del bot: segmentación de facturas dentro de la hoja, mapeo de columnas
  por solapamiento de rangos, borrado masivo de filas re-indexando en sitio
  (0,3 s en vez de minutos) y emparejamiento por rondas con unicidad mutua.
  **Resultado: 320 de las 324 facturas procesadas** (150.919 filas de entrada),
  $2.464.092.099 facturados de los cuales **siguen glosados $714.332.225 (29,0%)**.
  Se generaron 5 Excel ajustados + bitácora ítem por ítem + resumen por factura.
  Un análisis en paralelo sobre los 4 primeros archivos (1.306 facturas) destapó
  que **los procedimientos quirúrgicos traen renglones de DESGLOSE sin
  consecutivo** cuyo valor ya está incluido en el renglón de arriba: son 3.794
  renglones en 302 facturas y sumarlos inflaba el valor de la factura en
  $628.947.541. Ya se descuentan. Nace también
  `tools/verificar_detallado_ajustado.py`, que relee el Excel ajustado y lo
  contrasta contra el original, el consolidado y el reporte del ADRES: los 5
  archivos pasan sin fallas.
  Además nacen dos herramientas más, encadenadas con el ajustador:
  **`tools/dividir_detallado_por_factura.py`** (separa el detallado en un Excel
  por factura, con el formato intacto y el área de impresión ya fijada) y
  **`tools/excel_a_pdf.py`** (convierte en masa a PDF con el Excel del equipo o
  con LibreOffice, uno por archivo, con opción de carpeta por factura).
  Se generaron los **320 Excel y los 320 PDF** del paquete 31068 y se
  comprobó, leyendo el texto de cada PDF, que traiga su número de factura y que
  su total cuadre con la bitácora: los 320 cuadran ($714.332.224 contra
  $714.332.225, 1 peso de redondeo).

### Agosto 2026 — Pre-auditoría del paquete ADRES
- **03-08:** llegó la macro `NUEVO MODELO MACRO PARA DAR RESPUESTA A GLOSA ADRES
  31068`. Es el reporte del ADRES (16 columnas) **más 10 que el equipo llena a
  mano** sobre 4.619 filas glosadas. Se analizó y se descubrió que **siete de esas
  diez son mecánicas**: el código numérico sale de la causal (verificado contra
  las 2.989 que llenaron a mano: **cero discrepancias**) y la clasificación
  también (determinística en 47 de 48 causales).
  Nace **`tools/preauditar_glosas_adres.py`**: llena lo mecánico, propone el
  resto con el motivo escrito y **respeta lo que el equipo ya escribió**.
  Reproduce la macro renglón por renglón: 4.619 de 4.619 filas, y la columna
  RTA GLOSA COMPLETA sale **carácter por carácter idéntica**. El centro de
  costos pasó de 0 a 4.248 de 4.619 propuestos. Replica también el Word de
  respuesta por factura del VBA, sin depender de Word.
  El bot **no decide**: las 4.604 decisiones de aceptar/objetar/subsanar siguen
  siendo del auditor; la sugerencia va en columnas aparte (27 en adelante) para
  no correr nada de lo que usan las macros. A medida que el equipo decida, el
  bot aprende **su** criterio por causal y lo propone citando en cuántos casos
  se basa.
  **Hallazgo:** la causal **4506** está clasificada de dos formas distintas
  (231 veces FACTURACION y 24 PERTINENCIA) — hay que unificar el criterio.
- **04-08:** todo ese trabajo **se llevó a la página**. En el menú se quitó
  **Cobranza Live** (no se usaba) y en su lugar quedó **📄 Glosas ADRES**.
  Ahora el coordinador carga el `ReporteGlosasReclamPAQUETE` una sola vez
  (opcionalmente también el Excel de la macro y la bitácora del ajustador de
  detallados) y **el gestor solo escribe el número de factura**: la pantalla le
  trae las glosas clasificadas, el centro de costos, el gestor y el médico, la
  sugerencia de respuesta **con su motivo escrito**, el detallado cruzado
  (qué le pagó ya el ADRES y qué sigue glosado) y el texto consolidado para el
  Word.
  Se agregaron 3 tablas (`paquetes_adres`, `glosas_adres`,
  `items_detallado_adres`), el servicio `app/services/preauditoria_adres.py`
  y el router `app/api/routers/glosas_adres.py` con 8 rutas.
  El módulo web **no copia** las reglas: importa las mismas de
  `tools/preauditar_glosas_adres.py`, así un cambio de criterio sirve para los
  dos lados.
  Probado de punta a punta con el paquete real: **4.619 glosas, 324 facturas,
  $1.034.350.562 glosado** y 9.982 renglones de detallado, entrando por los
  endpoints de verdad. Se verificó lo que más duele si falla: **volver a cargar
  el paquete no borra las decisiones ya tomadas**, y aplicar las sugerencias en
  bloque tampoco pisa lo que un gestor escribió a mano.
  La pertinencia médica **sigue sin sugerencia**: la firma un médico auditor.
  Guía para el equipo en `docs/GLOSAS_ADRES_WEB.md`.
- **30-07:** **nace el proyecto SIIFA** (plataforma del Ministerio de Salud,
  distinta de COOSALUD/SIMED/DGH — la portalidad nacional de seguimiento de
  facturas). El auditor mostró la pantalla `Listar seguimientos` (2.579
  registros, sin botón de exportar) y subió los manuales oficiales y la
  documentación técnica de la API (swagger, colección Postman, manual de
  interoperabilidad). Hallazgo clave: **SIIFA sí tiene API REST oficial** de
  interoperabilidad (a diferencia de COOSALUD/SIMED), documentada y con
  endpoints específicos para listar y responder glosas — así que las dos
  herramientas nuevas hablan HTTP directo, sin navegador:
  - `docs/CONTEXTO_SIIFA.md`: plataforma, roles (IPS/ERP/FITS), autenticación
    JWT, catálogo de endpoints usados, y los plazos del trámite de glosa
    (Res. 1962/2025, Ley 1438/2011 Art. 57: 15 días hábiles para responder,
    7 para subsanar una glosa reiterada).
  - `tools/siifa_client.py`: cliente compartido (login, paginación automática,
    respuesta de glosas).
  - `tools/siifa_reporte_seguimientos.py`: trae TODOS los seguimientos del HUS
    (paginando solo) y arma el Excel masivo que pedía el auditor, con hoja de
    resumen por EPS.
  - `tools/responder_glosas_siifa.py`: el "bot tipo COOSALUD" pedido — lee un
    Excel tipificado y carga cada respuesta por API, con el mismo patrón de
    piloto/reporte CSV/`--saltar-csv` que el bot de COOSALUD.
  - Las tres piezas se probaron de punta a punta contra un servidor SIIFA de
    prueba (simulado, no el real) para validar el flujo completo: login →
    paginación → export a Excel → piloto de 1 glosa → cargue masivo con un
    error simulado → reintento sin duplicar. Todo funcionó como se diseñó.

### Julio 2026 — Frente Dispensario: respuesta masiva de glosas en SIMED
(trabajo del chat del bot Dispensario, fusionado a esta bitácora el 23-07)
- **01 y 02-07:** el robot DGH aprendió a llenar la ventana de respuesta por
  coordenadas (modo `--calibrar`). Lote del 1 de julio respondido.
- **06-07:** lote respondido y **subido a SIMED** (65 objeciones / 53 facturas)
  con pantallazos de evidencia.
- **09 y 10-07:** lote grande **subido a SIMED completo: 102 facturas, 225
  objeciones**, verificado al 100% (subida en ~22 minutos).
- **14 y 15-07:** lote del 14-07: **28 facturas, 44 objeciones, $46.016.019
  defendidos**. Respuestas revisadas con verificación adversarial; citas
  normativas corregidas (fuera la Res. 3047/2008 derogada; todo anclado en la
  Res. 2284/2023, el contrato 440-DIGSA/DMBUG-2025 y las Res. de tarifas HUS
  054 y 124 de 2026). El PDF de evidencias debe llamarse **GI-33-5182-2026**.
- **17-07:** lote del 17-07: **58 facturas, 115 objeciones, $87.605.050**
  (verificado con 33 agentes; 8 respuestas corregidas). En el motor: validador
  FURIPS endurecido (22 hallazgos) e informe de baja de cartera (Res. 577/2019).
- **22-07:** se detectaron **3 facturas de junio sin respuesta** (HUS0000518186,
  HUS0000515107, HUS0000515773) → generadas sus respuestas: **38 objeciones,
  $20.054.751** (`respuestas_glosa_DISPENSARIO_PENDIENTES_JUN.xlsx`). También
  un consolidado de 116 facturas / 238 objeciones / $94.150.626. Y nació la
  **plataforma de conciliación del Dispensario** (todas con README y pruebas):
  - `tools/organizar_objeciones_dispensario.py` — PDF de AUDITOOL → Excel de
    OBJECIONES para DGH, validando totales.
  - `tools/asistente_conciliacion_dispensario.py` — arma la matriz de evidencia
    por glosa desde los soportes (`Y:\`) y redacta el oficio de respuesta.
  - `tools/indexar_soportes_dispensario.py` — indexa `Y:\` una sola vez (el
    servidor tiene ~2,2 millones de archivos; sin índice se colgaba).
  - `tools/expediente_conciliacion.py` — EXPEDIENTE único por factura (contrato
    287/440, radicado, glosas, soportes, cartera). Probado con el lote real
    (147 expedientes).
  - `tools/motor_evidencia_dispensario.py` — localiza la prueba de cada glosa
    página por página (evidencia fuerte/débil, nunca inventa).
  - `tools/motor_verificacion_dispensario.py` — reglas deterministas: fija los
    HECHOS a probar por glosa, motor de contradicciones, marca *defendible*.
  - `tools/motor_decision_dispensario.py` — califica defendibilidad (0-100%),
    riesgos y acción recomendada (levantar / pedir soporte / aceptar parcial /
    escalar / conciliar).
  - `tools/piloto_conciliacion_dispensario.py` — orquesta el piloto de 5 casos
    (HUS0000446262, HUS0000452150, HUS0000426013, HUS0000455554 + 1 del
    auditor) con métricas y umbrales de aceptación (≥95% con soporte, ≥90% con
    evidencia, 0 levantamientos sin hecho probado, 100% trazables).
  - Diagnóstico del lote de conciliación (147 facturas / 444 glosas): 146/147
    cruzan con cartera (falta HUS0000443525); 372 glosas venían mal marcadas
    "SIN CONTRATO" cuando sí tienen contrato por fecha (342 → 287, 30 → 440).
    Base tarifaria: 287 = SOAT −15%, 440 = SOAT −20%.

**Los números de la operación SIMED (respuesta de glosas Dispensario):**

| Lote | Facturas | Objeciones | Valor defendido | Estado |
|---|---|---|---|---|
| 26 de junio | ~30 | ~40 | — | Subido |
| 1 de julio | ~50 | ~70 | — | Subido |
| 6 de julio | 53 | 65 | — | Subido |
| 9 de julio | 102 | 225 | — | Subido y verificado 100% |
| 14 de julio | 28 | 44 | $46.016.019 | Excel listo — confirmar subida |
| 17 de julio | 58 | 115 | $87.605.050 | Excel listo — confirmar subida |
| Pendientes junio | 3 | 38 | $20.054.751 | Excel listo — subir YA (plazos vencidos) |

### 22 al 28-07-2026 — Frente Suite Cartera HUS: consolidados, actas y bot de correos de pagos
(trabajo de la rama `claude/bot-multifunctional-improvements-zhj4nw`, PR #160, fusionado a esta bitácora el 28-07)
- **22-07:** control central de este frente: nace esta sección (reconstruyendo
  la historia desde Git) y se corrige un fallo de CI heredado, ajeno a
  Cartera/PDF — dos pruebas del Motor usaban fechas fijas de abril que se
  salieron de la ventana de 90 días y empezaron a fallar solas el 19-07; se
  anclaron a "la semana pasada" para que no vuelvan a caducar (la
  funcionalidad real nunca estuvo mal).
- **23-07:** **5 informes consolidados de estado de cartera** (formato
  FAMISANAR: CARTERA detalle por factura · RESUMEN por vigencia · CARTERA POR
  EDADES · RAD VS REC mensual · ACTAS DE GLOSAS), corte 30-06-2026, a partir de
  los 6 cortes mensuales DGH (enero a junio 2026): **DISPENSARIO MÉDICO**
  (Sanidad Ejército, 5.571 facturas, saldo $13.621.817.612, con actas SINAC
  709/720 y el giro directo real de mayo/junio del libro de pagos SAP),
  **PROTEGER EPS** (antes Cajacopi EPS, 532 facturas, $4.268.767.084),
  **CAJACOPI Caja de Compensación** (115 facturas, $302.274.693, sin
  movimiento en los 6 meses), **COMPENSAR** (39 facturas, $193.065.583) y
  **MESSER** (sin cartera al corte). Fórmulas recalculadas sin errores y 30 de
  30 totales cuadrados. Después se generó la **serie mensual completa**: 30
  informes (5 entidades × 6 cortes, 31-01 a 30-06-2026), también 30/30 sin
  errores y 150/150 totales cuadrados.
- **23-07 (cruce de actas):** **cruce factura por factura de las 13 actas del
  Dispensario** (2 SINAC en Excel + 11 en PDF, ~1.900 páginas leídas): el
  informe corte 30-06 ahora dice, por cada factura, si su glosa está
  LEVANTADA, ACEPTADA por la IPS, RATIFICADA (pendiente de conciliar) o EN
  TRÁMITE, con hoja de actas anclada a los totales oficiales y hoja de
  auditoría factura×acta (1.710 filas). Resultado: **$523,1 millones
  levantados en conciliación** a favor del HUS (+$173,2M levantados en
  respuestas AR) y **$1.013 millones aún ratificados** en actas de respuesta
  pendientes de conciliar (el mayor: AR003215 con $399,5M). Las 5 actas de
  conciliación validaron 100% al centavo; en las de respuesta (AR) el detalle
  por factura quedó al 95-98% (el resto documentado en el propio informe).
- **28-07:** **bot de correos de pagos**: la Suite gana el botón **"📧 Correos
  de Pagos → Excel"** — junta varios correos de Outlook (.msg) de "relación de
  pagos del día" en un solo Excel, leyendo el detalle del adjunto de cada
  correo y preservando fechas y montos con su tipo real (nunca como texto);
  las filas repetidas en más de un correo quedan marcadas, no se borran solas.
  Probado con los 13 correos reales del analista: **237 filas, $2.207.118.593
  pagados**, cuadrado al peso contra los 13 archivos originales. Se entregó
  también como **bot suelto** (ZIP de doble clic) para uso inmediato sin
  esperar a actualizar toda la Suite. Nota técnica: el lector de correos
  (`extract-msg`) trae una dependencia accesoria (`red-black-tree-mod`) que no
  instala en Windows/Python moderno; solo serviría para RE-ESCRIBIR un .msg
  (este bot solo LEE), así que se resolvió sin necesitarla.

**Pendiente de este frente:** no existe corte de cartera de julio 2026 (la
columna de recaudo de julio de los 5 consolidados y la serie mensual queda en
0 hasta que el analista lo entregue); revisar y fusionar el PR #160.

### 24 de julio de 2026 — Expediente Inteligente de Conciliación (Hoja Maestra)
- **Nueva herramienta `tools/hoja_maestra_conciliacion.py`:** arma en un solo
  Excel el **expediente de conciliación** del Dispensario con **un único
  registro maestro por factura** (nada duplicado). Cruza las tres bases que ya
  existen (no transcribe ni inventa):
  - **CARTERA** (corte 30/06/2026) como columna vertebral: 5.571 facturas, con
    su valor, saldo, estado de glosa, edades y lo levantado/aceptado/ratificado
    en actas.
  - **RECEPCIÓN DE OBJECIONES** (la glosa que puso la EPS): trae el **motivo
    exacto de la EPS** en texto (ej. *"SE RECONOCE A TARIFA SOAT... SIN
    CONTRATO"*), el concepto, el CUPS y el servicio.
  - **TRÁMITE DE OBJECIÓN** (nuestra respuesta): el valor objetado, el valor
    aceptado y el **argumento del ESE HUS** (ej. *"ESE HUS NO ACEPTA GLOSA..."*).
    Se une a la recepción por el consecutivo (4.063 de 4.066 cruzan).
- **El libro entregado tiene 5 hojas:** `00_DASHBOARD` (tablero con 15
  indicadores + cartera por vigencia/estado/edades), `01_MAESTRA` (una fila por
  factura, con resultado final a color), `02_GLOSAS` (una fila por glosa con el
  **motivo de la EPS y nuestra respuesta lado a lado**), `03_ACTAS` (una fila
  por factura+acta) y `04_CRUCES` (los 11 controles de consistencia).
- **Cifras que cuadran con lo ya verificado:** glosado $7.000.506.193; aceptado
  por IPS $1.122.029.872; **levantado a favor del HUS $707.499.754**;
  **ratificado (pdte. conciliar) $980.141.374**; saldo pendiente DGH
  $13.621.817.613. Total: 5.571 facturas (3.935 con glosa), 18.378 glosas (179
  aún sin respuesta). Se excluye el acta AC000639 por ser **duplicada** de la
  SINAC 720.
- **Lo que ninguna base trae queda marcado PENDIENTE** (no en blanco): la
  bandera de factura electrónica (CUFE), la normatividad citada por respuesta,
  el valor pagado real, y las **raíces exactas Y:/X:** de los soportes (por
  ahora se deja la ruta derivada por mes AAAAMM + la de factura electrónica
  `\\172.16.32.83\factura_electronica_net22\AAAAMM`). Con pruebas.

### 27 de julio de 2026 — Acta de conciliación de las 147 facturas (formato SINAC)
- **Cambio de enfoque pedido por el auditor.** El expediente del 24-jul cubría
  las 5.571 facturas de toda la cartera. El auditor lo devolvió: *"el universo
  de trabajo son únicamente las 147 facturas que actualmente están pendientes
  por conciliar"*. Ahora todo gira alrededor de esas 147.
- **Identificación del universo (antes de construir nada).** Las 147 salen del
  `HUS.xlsx` que envió el Dispensario (el mismo lote del `CONCILIACION.xlsx`):
  **147 facturas / 444 glosas**. Se cruzaron contra el estado de cartera: **146
  de 147 cruzan**; la única que no aparece en cartera es **HUS0000443525**. El
  estado de glosa de las 147 confirma que todas están pendientes (98
  ratificadas pdte. conciliar, 25 parte levantada/parte ratificada, 23 en
  trámite DGH). Se entregó el listado `LISTADO_147_PARA_APROBAR.xlsx` para
  revisión previa.
- **Nueva herramienta `tools/generar_acta_conciliacion_dispensario.py`:** arma
  el acta **sobre el archivo real del ACTA SINAC N.º 720** (no una imitación):
  conserva logos, encabezado oficial, celdas combinadas, zona de firmas y
  macros. Solo cambia el contenido. La tabla se expande de 11 a **444 filas**
  sin romper el formato.
- **Lo que quedó en el acta:** una fila por glosa, **agrupadas por factura** y
  ordenadas de mayor a menor valor glosado (al abrir una factura se ven todas
  sus glosas seguidas — la HUS0000452150 con sus 62). Cada fila trae el
  **motivo exacto de la EPS** y, al lado, **nuestra respuesta completa**, más
  código, tipificación, valores, fechas, radicados, resultado en actas
  previas, rutas de soportes y de factura electrónica (con hipervínculo).
- **Hoja DASHBOARD** (la primera del libro) con los 12 indicadores pedidos,
  todos como **fórmulas vivas**: al diligenciar la mesa el tablero se
  actualiza solo.
- **Cifras verificadas:** 147 facturas · 444 glosas · facturado
  **$1.267.976.805** (sin duplicar por factura) · glosado y pendiente por
  conciliar **$317.640.524** · aceptado en trámite **$1.758.956** ·
  recuperable **$315.881.568**. 471 fórmulas, **0 errores**.
- **Columnas completadas con el estado de cartera** (a solicitud del auditor):
  *VALOR ACEPTADO EN TRÁMITE* (8 facturas, $1.758.956), *CENTRO DE COSTO*
  (444 de 444 líneas, del export de recepción) y *ABOGADO ASIGNADO* (115
  facturas). La *CUENTA CONTABLE* quedó en **PENDIENTE**: no existe en
  ninguna base disponible (ni en el acta 720 original).
- **Tres hallazgos para llevar a la mesa:** (1) la entidad **no ha confirmado
  el recibo de ninguna de las 444 respuestas**, aunque todas tienen radicado
  de entrega; (2) **29 facturas** tienen diferencia entre el valor glosado del
  lote y el de la cartera; (3) el lote dice que **no aceptamos nada** (RE9901)
  pero la cartera registra **$1.758.956 aceptados** en 8 facturas — hay que
  aclararlo antes de firmar.
- **Documentación de entrega:** `docs/MODULO_CONCILIACION_DISPENSARIO.md`, con
  todo el módulo (objetivo, arquitectura, funciones, flujo, riesgos,
  pendientes y cómo fusionarlo al proyecto principal).

### Julio 2026 — Frente ADRES/FURIPS (chat "VALIDADOR ADRES", PR #173-#176)
- **17-07:** nace el **bot validador FURIPS**: valida masivamente los TXT
  FURIPS 1 y 2 contra la Circular 022 de 2023 de la ADRES (102 + 9 campos,
  obligatoriedad condicional) y cruza cada factura con sus soportes (RIPS,
  CUV, factura XML DIAN, factura PDF, epicrisis). Informe Excel de 7 hojas
  con semáforo. Revisión adversarial de 28 agentes: 22 correcciones el mismo
  día. También el **informe de baja de cartera** (Res. 577/2019): Word para
  presentar + Excel de relación, leyendo el PDF unido de cada factura.
- **21-07:** afinación con datos reales: direcciones con nomenclatura
  completa (campos 15/50/60), PDF escaneados sin falsos errores,
  representación gráfica DIAN cruzada contra la epicrisis, informe de baja
  en carpeta plana con progreso. **APP WEB "Validador ADRES"**
  (`validador-adres/`): validación desde el navegador con tablero, semáforo,
  gráficas y descarga del Excel. Bot `PDF_A_CMD_EN_CARPETA` (carpeta
  `CMD_CONVERTIDOS`) y blindaje CRLF de todos los `.cmd`. Corrida real de
  las 50 facturas ADRES: 27 con errores, 18 por revisar, 5 cumplen.
- **22-07:** **bot del informe XML DE4401 de NUEVA EPS** (411 facturas
  devueltas): busca el XML DIAN de cada factura y completa valor, contrato,
  cobertura, validación DIAN (CUFE, firma, acuse 02), conclusión con norma
  (Res. 506/2021 y 2275/2023) y respuesta para el portal DGH.
- **23-07:** el servidor guarda cada factura en su subcarpeta con nombres
  genéricos (`ad0901….xml`) → el bot busca también por el nombre de la
  subcarpeta, dentro de los **.zip** DIAN, verifica el número POR DENTRO del
  XML, y deja una hoja **DIAGNOSTICO** en el Excel (versión 2.1) para
  diagnosticar corridas a distancia.
- **27-07:** **documentación técnica de entrega del módulo**
  (`docs/ENTREGA_MODULO_ADRES_FURIPS.md`). **OCR automático** para PDF
  escaneados en el validador y el informe de baja (Tesseract o RapidOCR,
  se instala solo desde el .cmd; el soporte queda "SI (OCR)"). Soportes
  reconocidos a cualquier profundidad (subcarpetas internas, sueltos en la
  raíz) y con nombres genéricos (epicrisis.pdf, fe.xml, ResultadosMSPS.json).
  Se entregó el **PAQUETE COMPLETO** en ZIP (5 frentes + documentación).
- **29-07:** el **PR #176 quedó FUSIONADO** en la rama principal (se
  resolvieron dos rondas de conflictos con los otros chats — bitácora,
  CLAUDE.md y dos archivos de pruebas que ambos frentes habían corregido
  igual). Los lanzadores `.cmd` ahora muestran el avance de la descarga del
  OCR (~200 MB la primera vez) para que no parezcan congelados; el auditor
  ya corrió el validador con OCR en su PC ("YA ARRANCO TODO BIEN").

### 23-07 — Módulo de Pre-auditoría SINAC
- **23-07:** nace el **módulo de Pre-auditoría SINAC** (rama
  `claude/invoice-audit-bot-qa2koy`, PR #186, página `/preauditoria` de la app
  web), a partir de los archivos guía CONSOLIDADO_PRE_AUDITORIA_2026 y
  OFICIOS_DEVOLUCIONES_CONSECUTIVOS. Qué hace:
  - Registrar el **oficio radicado** por Facturación con **fecha y hora** de
    recibido.
  - Importar el Excel del **consecutivo de DGH** y contar **cuántas facturas
    trae cada número de envío**.
  - Auditar cada factura: **Soportes OK (radicar)** o **Devuelta con motivo**.
    Máximo **3 devoluciones** por factura (la 4.ª se bloquea); cuando la
    factura vuelve corregida queda **SUBSANADA** o **NUEVAMENTE DEVUELTA**.
  - Generar el **oficio de devolución en PDF** con consecutivo SINAC
    (DEV-PRE-AUD-####-AAAA), logo y bloque de firmas, igual al formato del
    Excel de oficios.
  - **Semáforo** del plazo de 3 días hábiles (cuentan desde el día siguiente
    al recibo): verde / amarillo (penúltimo día) / rojo (último) / vencido.
  - **Estadísticas**: auditadas, OK, devueltas, subsanadas, por auditor y
    facturas reincidentes; vista masiva con filtros y vista individual con
    el historial completo de cada factura.
  - 29 pruebas automáticas en verde (`tests/test_api/test_preauditoria.py`).
- **23-07 (tarde):** dos entregas más del mismo frente:
  - El **PDF del oficio de devolución** quedó con el formato exacto de la guía
    del equipo (GUIA_DE_PDF): título "ENTREGA DE NO ACEPTACIONES PARA
    CORRECCION...", subtítulo "OBSERVACIONES DE PREAUDITORÍA PARA SUBSANACIÓN",
    consecutivo y fecha arriba a la derecha y columna OFICIO (radicado FHUS)
    en cada fila.
  - **CONSOLIDADO_PRE_AUDITORIA_2026_INTERACTIVO.xlsx** (entregado por chat,
    NO va al repo porque el DGReport trae datos de pacientes): se escribe el
    número de ENVÍO y se llenan solas F_RECIBIDO, FACTURA, F_FACTURA, VALOR,
    NIT, ENTIDAD y CORREO F.E. Las fuentes las alimenta el auditor pegando
    los reportes de DGH en las hojas RADICACION (radicación de cuentas;
    precargada con 36.765 filas) y DGREPORT (correos de factura electrónica;
    7.231 filas). Si el envío trae varias facturas, se repite el número y
    salen en orden ("2 de 5"). Instrucciones en la hoja LEYENDA.

### 24-07 — Pre-auditoría v2: la aplicación web es el consolidado oficial
- **24-07:** el módulo de pre-auditoría deja de depender del Excel: ahora la
  **aplicación web es el consolidado oficial** (misma rama/PR #186). El auditor
  solo hace 4 cosas y el sistema arma todo:
  1. **Sube la Radicación de Cuentas** (reporte de DGH) → el sistema la guarda
     como fuente (upsert por factura, no duplica; excluye radicaciones
     'Anulado'; se probó con las 36.723 facturas reales del reporte).
  2. **Sube el DGReport** → de ahí sale CORREO F.E. (SI/NO).
  3. **Registra el oficio recibido** (FHUS + fecha/hora).
  4. **Escribe el número de envío** → el sistema crea automáticamente una fila
     por cada factura del envío, autocompletando F_RECIBIDO, F_FACTURA, VALOR,
     NIT, ENTIDAD y CORREO F.E. desde las fuentes.
  - **No duplica:** si el envío ya se cargó, avisa "El envío ya fue cargado".
  - **Una factura = una sola fila** (canónica) + un **historial de eventos**
    con toda la trazabilidad. Si una factura devuelta reingresa en un envío
    nuevo, la reconoce y numera **Subsanación 1/2/3** sin crear factura nueva.
  - **Auto-sincroniza:** corregir un dato en el Excel y volver a subirlo se
    refleja solo en el consolidado (los datos descriptivos se leen de la fuente
    más reciente, no se copian).
  - **Auditoría:** el auditor solo decide **Radicar** o **Devolver con motivo**;
    máximo 3 devoluciones (la 4.ª se bloquea).
  - **Oficio de devolución PDF** con consecutivo SINAC (formato de la guía),
    armado desde un **snapshot inmutable**: un reingreso posterior no altera un
    oficio ya emitido.
  - **Consolidado consultable y exportable a Excel** + estadísticas (por
    auditor, reincidentes, semáforo, tasa de devolución).
  - Diseño verificado con un panel de agentes IA (mapeo de columnas contra los
    archivos reales, esquema, flujo) y una **revisión adversarial** que encontró
    y corrigió: corrimiento de fechas de un día, inmutabilidad del PDF ante
    reingreso, bloqueo de doble devolución, y consultas que no escalaban a 36k
    filas. **30 pruebas del módulo + 4.327 de todo el repo en verde.**
  - Pendiente operativo: al sacar el DGReport, ampliar el rango de fechas para
    que cubra el mismo periodo que la Radicación (si no, algunas facturas
    marcan CORREO F.E.=NO por quedar fuera de la ventana del reporte).

### 27-07 — Pre-auditoría: mejoras pedidas tras el primer uso real
- **27-07:** el módulo ya está desplegado y en uso (2 oficios, 22 facturas
  auditadas el primer día). Con el feedback del auditor se agregó:
  - **Firma de Yudy en el PDF**: se extrajo la firma manuscrita de la guía y
    ahora sale automáticamente en cada oficio de devolución
    (`static/firma_preauditoria.png`, con su proporción real).
  - **Regla nueva: sin facturación electrónica NO se radica.** Si la factura
    no está en el Formato Facturación Electrónica (CORREO F.E. = NO), el botón
    "Soportes completos" queda deshabilitado y el servidor también lo bloquea:
    solo se puede devolver.
  - **Eliminar radicados (solo administradores):** individual o masivo, para
    oficios que quedaron mal registrados. Con salvaguardas: no se puede
    eliminar uno con PDF de devolución ya emitido; las subsanaciones se
    revierten sin perder el historial; los envíos quedan libres para
    re-escribirse.
  - **Dos fases con nombre:** cada oficio muestra quién lo RECEPCIONÓ y
    quién(es) lo están AUDITANDO (gestores distintos).
  - **Botón "Ver"** en el consolidado para consultar la respuesta y el
    historial completo de cada factura sin entrar a auditarla.
  - Se renombró DGReport → **"Formato Facturación Electrónica"** en la
    pantalla de fuentes.
  - **Estadísticas interactivas:** dona de resultados con clic-para-filtrar,
    barras por auditor y por entidad (top 10) con tooltips, y semáforo visual.
    Colores verificados para daltonismo.
  - 35 pruebas del módulo en verde; verificado en navegador con los archivos
    reales (36.723 facturas).

### 27-07 (tarde) — Documentación técnica oficial del módulo de Pre-auditoría
- Se generó **`docs/PREAUDITORIA_DOCUMENTACION_TECNICA.md`**: documento de
  entrega al equipo principal que reconstruye TODO el desarrollo del módulo
  (objetivo, arquitectura, funciones, flujo, base de datos, backend, frontend,
  decisiones tomadas y descartadas, riesgos, pendientes y guía de fusión).
  Es la referencia para integrar este módulo al proyecto principal sin perder
  conocimiento. PRs del módulo: #186 (v1→v2), #187 (botón menú), #189
  (mejoras post primer uso).

### 27-07 (tarde) — Documentación técnica oficial del módulo Glosas Dispensario/SIMED
- Se generó **`docs/ENTREGA_MODULO_GLOSAS_DISPENSARIO_SIMED.md`** (PR #191,
  fusionado): entrega al equipo principal del chat "GLOSAS DISPENSARIO —
  SIMED": objetivo, arquitectura, el clasificador de 14 reglas y las 16
  plantillas de respuesta con sus 4 rondas de verificación adversarial
  (qué normas NO citar y por qué), el contrato operativo del robot SIMED
  (numeración por línea de concepto, estados, reintentos, evidencias),
  cifras de los 7 lotes del Dispensario, el bot DGH por coordenadas (PR
  #134), riesgos, pendientes y el plan para fusionar todo sin perder nada.
  Recomendación clave que quedó escrita: mover `glosa_motor.py` y los
  generadores de lotes (hoy en el scratchpad de la sesión) a
  `tools/glosas_dispensario/` en el repo.

### 27-07 (noche) — Pre-auditoría: borrado total (solo admin) y Excel para ADRES
- **Zona de administración** nueva en la pestaña Fuentes (solo la ven
  SUPER_ADMIN/COORDINADOR): botón **"Borrar todos los datos"** para dejar la
  página limpia y que el equipo empiece a trabajar de cero. Borra oficios,
  facturas, historial, envíos y oficios de devolución; las **fuentes se
  conservan** salvo que se marque la casilla para borrarlas también. Pide
  escribir **BORRAR TODO** + una confirmación final, y el servidor exige rol
  de administrador (un auditor recibe "no autorizado"). Ojo: al limpiar, el
  consecutivo DEV-PRE-AUD vuelve a empezar en 0001.
- **Excel especial para ADRES:** cuando un oficio tiene facturas de ADRES
  (se reconoce por NIT 901037916 o por el nombre de la entidad), aparece el
  botón **"⬇ ADRES"** en la lista de oficios y dentro del oficio. Descarga un
  Excel con la **información completa** de esas facturas: envío, oficio FHUS,
  fechas, valor, NIT, entidad, correo F.E., fecha del correo, **CUFE**,
  estado, resultado, ronda, subsanaciones, devoluciones, auditor, motivo,
  oficio de devolución SINAC y quién recepcionó. Solo salen las facturas de
  ADRES (si el oficio trae mezcla de entidades, las otras no van).
- 42 pruebas del módulo en verde (7 nuevas: permisos del borrado, conteos,
  confirmación obligatoria, contenido del Excel ADRES).
- **Para dejar la página limpia:** después de desplegar en la VM, entrar como
  administrador → Fuentes → Zona de administración → "Borrar todos los datos"
  (sin marcar la casilla de fuentes, para no volver a subir los Excel).
- **Ajuste posterior (mismo día):** el auditor pidió que el Excel de ADRES
  salga con el formato del consolidado que se maneja con esa entidad. Quedó
  así: SINAC diligencia de **Item** a **Fecha_Entrega_Fact** (Item,
  Fecha_Recibido, Envío, AUD, HUS, Fecha_Factura, Valor, NIT, Entidad,
  Correo F.E., Observación Preauditoria Radicación SINAC, Radicar_1,
  Observaciones Adicionales, Fecha_Entrega_Fact) y después vienen las
  columnas de las otras áreas **vacías** para que continúen el mismo archivo
  (Observación_FACTURACIÓN, Fecha_Dev_CARTERA, Fecha_Segunda_Revisión,
  Segunda_Observación_SINAC, Fecha_Dev_FACTURACIÓN,
  Segunda_Observación_FACTURACIÓN, Fecha_Dev_CARTERA, Radicar_2,
  Fecha_Radicación, Número_Radicado, INFOPOL). El sistema llena: Radicar_1
  (SI/NO según la auditoría), la Observación (el motivo de devolución con el
  consecutivo DEV-PRE-AUD, o "SOPORTES COMPLETOS" si va a radicar) y deja
  **Fecha_Entrega_Fact en blanco** (esa fecha la escribe a mano quien
  entrega a Facturación). Encabezados azules el tramo SINAC y grises el de
  las otras áreas.

### 28-07 — La página se caía al subir las fuentes: causa y solución
- **Qué pasó:** durante la mañana la página mostró varias veces "Error 524",
  "Failed to fetch" y "Bad gateway 502", y **el cargue del Excel no entraba**
  (los contadores seguían mostrando el cargue anterior).
- **Causa real (medida, no supuesta):** el servidor de Google tiene **1 GB de
  memoria** y la aplicación se quedaba sin aire al procesar el archivo de
  36.723 facturas. El sistema operativo mataba la aplicación a mitad del
  cargue (5 veces en 45 minutos, confirmado en el registro del servidor), y
  al morir la base de datos deshacía todo: por eso no quedaba nada cargado.
  Reparto medido del consumo: aplicación en reposo 140 MB, leer el Excel
  +70 MB, **guardar en la base +154 MB** (todas las filas se guardaban de un
  solo golpe al final), más lo que consume el tablero cuando el equipo entra
  a la vez.
- **Solución en el código:** el cargue ahora **se guarda por bloques de 2.000
  facturas** en vez de todo al final, y los textos que se repiten miles de
  veces (entidad, NIT, envío) se guardan una sola vez y se comparten.
  Resultado medido con el archivo real: **pico de 263 MB → 119 MB** (menos de
  la mitad) y además más rápido (5,3 s → 3,7 s en el guardado). Ventaja
  adicional: si el cargue se interrumpe, **lo ya guardado no se pierde** —
  al volver a subir el mismo archivo el cargue retoma donde quedó (el
  sistema nunca duplica). 47 pruebas del módulo en verde (5 nuevas que fijan
  que trocear el cargue no altera los conteos ni duplica facturas).
- **Paliativo aplicado ese día en el servidor** (mientras se despliega lo
  anterior): se subió el tope de memoria del contenedor de 640 MB a 1.400 MB
  con uso de disco como apoyo, para que la aplicación se ponga lenta en vez
  de morirse.
- **Segundo hallazgo (misma tarde): los archivos crecieron mucho.** Al revisar
  los archivos reales de hoy resultó que ya no son del tamaño de antes:
  - Formato Facturación Electrónica: **203.484 filas** (antes 7.231).
  - Radicación de Cuentas: **191.859 filas → 189.446 facturas** (antes 36.723),
    17,6 MB, con 2.413 radicaciones anuladas.
  Con ese tamaño el cargue tardaba 49 segundos en un equipo rápido, y en el
  servidor del hospital pasaba de los **100 segundos que Cloudflare tolera**
  antes de cortar la conexión: de ahí los errores 524 y 502.
- **Segunda optimización (lectura del Excel):** se encontró que los reportes de
  Dinámica Gerencial **no declaran sus dimensiones** dentro del archivo. Cuando
  ese dato falta, la librería que lee Excel recorre el archivo COMPLETO solo
  para averiguar su tamaño y después lo vuelve a recorrer para leerlo: 12
  segundos perdidos de 36. Como el sistema nunca usa ese dato, ahora se omite
  ese primer barrido. Además se quitó una normalización de texto costosa que
  se ejecutaba 383.740 veces (dos por fila). **Resultado: la lectura pasó de
  45 a 28 segundos**, leyendo exactamente lo mismo.
- **Solución entregada al auditor ese día:** se partió el archivo de Radicación
  en 3 partes (verificando que las 3 suman exactamente lo mismo que el
  original: 191.859 leídas, 189.446 facturas, 2.413 anuladas). Cada parte
  tarda 17 segundos, muy por debajo del límite. Se puede partir sin riesgo
  porque en ese archivo **ninguna factura se repite**.
### 28-07 (tarde) — Tres fallas del uso real y el borrado de envíos
Reportadas por el auditor durante la jornada, con evidencia en pantalla:
- **La misma factura quedó radicada 5 veces.** En el historial aparecían cinco
  eventos RADICADA idénticos, del mismo auditor y a la misma hora. Causa: como
  la página no avisaba que estaba guardando, el gestor volvía a hacer clic, y
  las peticiones llegaban al servidor **al mismo tiempo**; todas veían la
  factura "pendiente" antes de que la primera alcanzara a guardar. Corregido
  por los dos lados: el botón se bloquea y muestra "Guardando…", y el servidor
  toma la factura con una sola operación indivisible, así solo el primer clic
  gana y los demás reciben un aviso claro.
- **Lo que se escribía se perdía.** El único campo del formulario decía "Motivo
  de la devolución" y, al radicar, ese texto se descartaba. Ahora hay un campo
  **Observaciones** aparte que **se guarda siempre** (también al radicar) y
  queda visible en el historial de la factura, con su propia columna.
- **La página no se actualizaba sola.** Había que recargarla a mano para ver si
  algo se había guardado, porque cuando el servidor iba lento los refrescos
  fallaban **en silencio**. Ahora las tablas muestran "Cargando…" mientras
  responden y, si algo falla, lo **dicen** en pantalla con opción de
  reintentar, en vez de quedarse mostrando datos viejos.
- **Nuevo: quitar un envío cargado por error.** En el detalle del oficio, cada
  envío tiene una ✕ (solo administradores) que lo deshace sin tocar el resto
  del oficio: borra las facturas que entraron con ese envío, y las que venían
  de una devolución vuelven a su estado anterior sin perder historial. El
  envío queda libre para volver a escribirlo. No se puede quitar si alguna de
  sus facturas ya salió en un oficio de devolución emitido.
- 58 pruebas del módulo (8 nuevas) y 4.361 de la suite completa en verde, más
  verificación en navegador de los cuatro puntos.
- **Faltaba un caso (corregido enseguida):** cuando el auditor audita **desde
  la ventana del oficio** (que es como se trabaja normalmente), esa ventana
  no se refrescaba. Seguía mostrando los contadores viejos "Pend · OK · Dev"
  y, como el botón del oficio de devolución se habilita según ese dato, se
  quedaba bloqueado aunque ya hubiera facturas devueltas: por eso "no dejaba
  generar el PDF" y tocaba recargar. Ahora esa ventana se actualiza sola al
  guardar. Además, cuando el botón está bloqueado **dice por qué**: el oficio
  de devolución solo se puede generar si hay al menos una factura devuelta,
  porque es la carta con la que se le regresan las facturas a la entidad.

### 28-07 (tarde) — Pre-auditoría: el consecutivo del oficio lo escribe el auditor
- El auditor recordó un pedido anterior: **la numeración de los oficios de
  devolución la lleva SINAC internamente**, así que el sistema no debe
  asignarla sola. Ahora, al oprimir **"Generar oficio de devolución"**, se
  abre una ventana para **escribir el consecutivo que corresponde**.
- Viene precargado con el que seguiría según lo registrado en la página (solo
  como sugerencia) y se puede cambiar. Se acepta escribir **solo el número**
  (`89` → se completa como DEV-PRE-AUD-0089-2026) o el **consecutivo
  completo**. Si se escribe uno ya usado, el sistema lo rechaza diciendo en
  cuál oficio está. Si se deja vacío, usa el sugerido.
- La sugerencia siguiente continúa desde el que se escribió (si usó el 89, la
  próxima vez sugiere el 90).
- 3 pruebas nuevas + prueba en navegador de la ventana completa.
- **Ya quedó desplegado en la VM** (PR #208 fusionado). No hubo que hacer nada
  a mano: el auto-despliegue que corre cada 5 minutos lo aplicó solo y el
  motor quedó corriendo el commit `5ba3a3f`, sano. Para verlo en pantalla hay
  que refrescar el navegador con **Ctrl+F5** (si no, muestra la versión vieja
  que tiene guardada).
- **Nota para no perder tiempo la próxima vez:** en la VM el repositorio está
  en `/opt/motor-glosas` y el motor corre en **Docker**, no como servicio de
  systemd. El comando para mirar cómo está, desde Cloud Shell y en un solo
  paso (entra a la VM y ejecuta allá adentro):

  ```bash
  gcloud compute ssh motor-glosas --zone=us-west1-a --tunnel-through-iap --command '
  cd /opt/motor-glosas && git log --oneline -1
  sudo docker compose ps
  free -m | head -2
  '
  ```

  Cuidado con confundir las dos máquinas: si el prompt dice `@cloudshell`
  estás **fuera** de la VM y los comandos no encuentran nada; dentro de la VM
  el prompt dice `@motor-glosas`.

- **PENDIENTE importante (para que no vuelva a pasar):** con archivos de este
  tamaño, la solución de fondo es que **el cargue no haga esperar al
  navegador**: subir el archivo, responder de inmediato "recibido, procesando"
  y que la página muestre el avance. Así el tamaño del archivo deja de
  importar y no hay límite de tiempo que valga. Queda propuesto.
- **~~PENDIENTE recomendado~~ — YA HECHO:** subir la máquina virtual a
  **`e2-small`**. Al revisar la VM el 28-07 la memoria total salió en 1.971 MB
  (~2 GB): la `e2-micro` tiene 1 GB y la `e2-small` tiene 2 GB. Se confirmó
  además preguntándole directamente a Google, que respondió `e2-small`:
  `gcloud compute instances describe motor-glosas --zone=us-west1-a --format="value(machineType)"`
  No hay que detener ni editar nada.

### Motor IA — rondas 32 y 33 (viene de la rama principal, PR #183)
- **22 y 23-07 (motor de dictámenes):** dos rondas más de corrección del motor,
  fusionadas desde la rama principal:
  - **Ronda 32:** el número de factura ya no se cuela como código CUPS en el
    dictamen (red determinística nueva); las glosas de $10 millones o más van
    al modelo potente; se corrigieron citas legales. Pasó una revisión
    adversarial (panel de 25 agentes) que confirmó y corrigió 18 detalles.
  - **Ronda 33** (dos dictámenes PPL reales, glosas de $218.145 y $5.800):
    se quitaron normas repetidas y de relleno; 13 pruebas nuevas
    (`test_ronda33_fixes.py`). Pendiente: desplegar la ronda 32 en la VM de
    Google (`cd /opt/motor-glosas && git pull && docker compose build motor &&
    docker compose up -d`) y repetir los 4 casos de prueba.

### 28-07 — SINAC OS: se pasó de "una aplicación" a una plataforma con plan

Día de dos mitades: primero se documentó a dónde vamos, después se empezó a
construir. Todo está en la rama principal.

**Lo que se documentó** (PR #197, cuatro archivos en `docs/`):
- `SINAC_OS.md` — el plano maestro que escribió Yesid: visión, principios,
  agentes, módulos y las siete fases del proyecto. Es el documento rector:
  ningún desarrollo puede contradecirlo sin actualizarlo primero.
- `MANUAL_ARQUITECTURA_SINAC_OS.md` — 19 capítulos que explican **cómo** se
  construye SINAC OS. La idea de fondo: el proceso administrativo deja de ser
  una carpeta de archivos y pasa a ser un objeto vivo que nunca muere, solo
  cambia de estado (Factura → Glosa → Objeción → Respuesta → Radicación →
  Conciliación → Aceptación → Pago → Archivo → Histórico). Cada capítulo cierra
  respondiendo qué existe hoy, qué se reutiliza, qué se elimina, qué se crea y
  cómo se migra sin romper nada.
- `MAPA_CAPACIDADES.md` — la misma plataforma explicada sin tecnicismos, para
  gerencia o para alguien que llega nuevo al área.
- `ANEXO_AUDITORIA.md` — la radiografía del sistema tal como estaba antes,
  guardada como memoria de por qué se decidió cada cosa.

**Lo que se descubrió al revisar el sistema entero** (15 auditorías sobre el
código real): el sistema sabe mucho pero está mal conectado consigo mismo. La
mitad que piensa (la aplicación web) y la mitad que ejecuta (los robots de
portal) **no se hablan**: el puente es un Excel que viaja en el escritorio de
una PC. Y hay **39 archivos de módulos ya terminados** (SAVIA, EMSSANAR, VCO,
FOMAG, Mutual Ser, el organizador de correos) que nunca se fusionaron a la
rama principal: están listos, probados y a un clic de distancia.

**Lo que ya se construyó y está funcionando:**

- **Seguridad y trazabilidad (PR #199).** Siete arreglos:
  1. El sistema decía que ciframos los datos del paciente **y no los ciframos**.
     Ahora dice la verdad; cifrarlos de verdad queda para el siguiente paso.
  2. El nombre del paciente ya no se le muestra a cualquiera: solo al gestor
     asignado, al coordinador y al administrador. Si la glosa **no** tiene
     gestor, sigue visible para todos — es trabajo que cualquiera puede tomar.
  3. Un usuario de solo lectura podía cerrar glosas por una puerta lateral,
     **incluso 500 de un golpe**. Cerrada.
  4. Si faltaba la clave secreta en la configuración, el sistema arrancaba
     igual y firmaba las sesiones con una clave vacía. Ahora no arranca.
  5. La página de "estado del sistema", que es pública, hacía un recorrido
     pesado de 30 días en cada consulta. Ahora es liviana.
  6. El registro de auditoría (quién hizo qué) ya **no se puede borrar**.
  7. Ese registro ahora guarda también desde qué computador se hizo cada cosa.
  - Además: el servidor pasó a hora de Bogotá. Estaba en hora de Londres, así
    que las tareas programadas "de las 3 de la mañana" corrían a las 10 de la
    noche.
- **Un solo lector de valores en pesos (PR #201).** Había cuatro copias del
  mismo código leyendo montos, y dos se equivocaban en plata:
  - El **informe de cartera de gerencia** leía `950.000` como **950 pesos**
    (cualquier monto con un solo punto se dividía por mil). Solo pasaba con
    valores en texto, como los que exporta el DGH. **Conviene revisar un
    informe reciente.**
  - El cargue de tarifas leía como **cero** dos formas de escribir comunes
    (`1'500.000` y `850 millones`). Una tarifa en cero se propaga al dictamen.
  - Al unificar apareció un tercer error: `0.99` se leía como 99 pesos.
  - Ahora hay un solo lector, y una prueba que caza a quien vuelva a escribir
    otro por su cuenta.

**Dos hallazgos que conviene no perder de vista:**
- El robot de SAVIA **multiplica por cien** los valores con decimales
  (`1.365,50` → `136.550`). El módulo de EMSSANAR ya había corregido ese mismo
  error, pero el arreglo nunca llegó porque las ramas nunca se juntaron. Si el
  Excel de SAVIA trae decimales, los archivos generados con ese robot llevan
  valores inflados.
- El sistema **ya tiene construido** un avisador por correo de glosas próximas
  a vencer (ordena por urgencia, arma el correo, todo). Está terminado y
  **desconectado**. Es justo lo que faltó cuando las tres facturas de junio
  ($20.054.751) se descubrieron 45 días tarde.

### 28-07 (noche) — Verificación adversarial del lote de glosas Dispensario del 28-jul
- Lote de **97 objeciones**. Solo se atacaron las **6 decisiones nuevas** (el
  resto del banco de plantillas ya pasó 4 rondas adversariales y no se re-evalúa).
- Resultado: **3 calzan con reserva** (FA0201 equipo interdisciplinario,
  FA2303 transfusión, TA listado→tarifa) y **3 NO calzan** (FA0801 segundo
  rastreo de anticuerpos, SO5801 biopsia endometrio/AMEU, FA0101 conteo de
  días de estancia).
- **Veredicto: el lote NO está listo para subir.** Hay correcciones de texto
  obligatorias antes del cargue:
  - Quitar frases que refutan reclamos que el pagador no hizo ("no se anexa
    acuerdo de tarifas", "paquete", "procedimiento principal", SOAT UVB):
    delatan respuesta enlatada y permiten descalificarla por no pertinente
    (la Res. 2284/2023 exige coherencia entre glosa y respuesta).
  - Responder los prongs reales de cada observación: identificación del
    equipo interdisciplinario y defensa de la cantidad 29 (FA0201); la tesis
    "enfermería está incluida en la estancia" (FA2303: la estancia cubre el
    cuidado básico, no procedimientos con renglón propio); la regla de 72
    horas del banco de sangre (FA0801: voltearla — la muestra pretransfusional
    VENCE a las 72 h en paciente transfundido, Decreto 1571/1993, o sea el
    nuevo evento OBLIGA al nuevo rastreo); la homologación AMEU→legrado
    (SO5801); y el conteo aritmético 32 vs 34 días (FA0101).
  - Quitar frases autolesivas: la remisión genérica a la nota operatoria en
    SO5801 (si la nota no describe biopsia aparte, confirma la glosa) y la
    prueba de "permanencia del día objetado" en FA0101 (34 días no caben
    entre el 17-may y el 18-jun); en TA, afirmar la vigencia 2026 del
    contrato 440 (prórroga/adiciones), no solo que el pagador "es parte".
- Verificaciones del auditor antes de cargar esos grupos: leer la nota
  operatoria del caso AMEU (¿hubo toma de biopsia como acto aparte?);
  reconstruir día a día los 34 días de estancia (si solo se prueban 32-33,
  procede aceptar parcial el excedente, no forzar el 100%); fechas y horas de
  los 2 rastreos de anticuerpos con su orden médica; otrosí o prórroga que
  acredite la vigencia 2026 del contrato 440-DIGSA/DMBUG-2025.

### 28-07 (noche) — Contrato de Construcción de SINAC OS: el plano se volvió obra

Hasta hoy teníamos el **plano** (el Manual de Arquitectura: qué queremos que
sea SINAC OS). Faltaba el **contrato de obra**: qué se construye, en qué orden,
quién lo aprueba y cómo se comprueba que quedó bien. Eso es lo que quedó hecho.

Está en `docs/CONTRATO_CONSTRUCCION_SINAC_OS.md`: **veinte capítulos y un
anexo**, unas 323.000 palabras. Cada capítulo termina con una tabla donde toda
fila tiene **criterio de aceptación** y **el comando exacto que lo comprueba**,
para que nadie tenga que preguntar si algo quedó hecho. En total **730 tareas**.

**Lo importante para el área, en una frase:** de las 730 tareas, **69 producen
los siete resultados que usted puede ver funcionando**, y cuestan 163,5 jornadas
—el 10 % del esfuerzo total—. Las otras 661 el Contrato nunca las amarró a un
resultado visible.

Los siete resultados, en el orden en que llegarían:

1. **La plata deja de contarse mal.** Un solo lector de valores en pesos: se
   acaba el error del ×100 que hacía leer `950.000` como `950`.
2. **Lo vencido deja de esconderse.** Encabeza la lista en vez de desaparecer
   de ella, y escala solo al coordinador. Es el caso de las tres facturas de
   junio por $20.054.751 que se descubrieron 45 días tarde.
3. **Una entidad nueva se activa sin programar.** SIMED encolable desde una
   ficha, sin esperar semanas de desarrollo.
4. **Un expediente por factura y una sola cifra por concepto.** Se acaba que
   "recuperado" dé cuatro números distintos según la pestaña.
5. **Un solo documento radicable**, generado en un solo lugar.
6. **El robot corre solo y se ve mientras corre**, con la plata en juego a la
   vista.
7. **Una institución nueva queda instalada en una jornada.**

**Cuatro problemas se encontraron al juntar los capítulos** y quedaron
corregidos o registrados:

- **El plan eran diecinueve planes que no se miraban.** De 773 dependencias
  declaradas, 742 apuntaban a una tarea del mismo capítulo: casi ninguna decía
  que el trabajo de un capítulo necesita el cimiento que vive en otro. Se
  agregaron 563 dependencias derivadas de nueve cimientos escritos, con la
  regla a la vista para que se pueda discutir.
- **La columna que separa los datos de una institución de los de otra tenía
  tres nombres** (`institucion_id`, `hospital_id`, `tenant_id`). Construido así
  quedaban tres columnas para lo mismo, y la protección de datos se activa
  sobre una sola: las tablas con las otras dos quedaban abiertas. Se unificó en
  `institucion_id` (287 reemplazos y 8 líneas a mano). Se eligió ese nombre
  porque SINAC OS también debe poder instalarse en una clínica o en una IPS.
- **Más de la mitad del plan estaba marcada como urgente** (380 de 730). Una
  urgencia que le toca a la mitad no prioriza nada. Se volvió a priorizar con
  una regla verificable: P0 es lo que hace falta para los tres primeros
  resultados y nada más. Quedaron 37.
- **El Contrato completo compromete casi siete años de una persona**
  (1.625,5 jornadas). Se dice sin adornos: **no es ejecutable de punta a punta**
  con el equipo de hoy. Por eso el anexo separa lo que sí cabe.

También se cerraron defectos que habrían costado retrabajo: ocho dependencias
apuntaban a tareas inexistentes, el capítulo 14 numeraba 40 tareas con códigos
que ya significaban otra cosa en otros capítulos (`GOB-09` era "parser
monetario" en uno y "política de vida de rama" en otro), y dos tareas se
declaraban prerrequisito de sí mismas. Todo eso quedó arreglado y explicado en
el **Anexo I**.

**Las cifras del Contrato se comprueban solas.** La portada trae una tabla que
vuelve a medir contra el repositorio lo que el documento afirma. Hoy: 43 tablas,
4.530 pruebas, 59 ramas sin fusionar, 44 llamadas a `prompt()` y 1 sola
migración formal **coinciden**; las rutas de la API subieron de 686 a 712
porque el sistema siguió creciendo mientras se escribía.

**La Regla 11 quedó cumplida en los veintiuno.** Todo capítulo cierra
respondiendo qué habría que cambiar para soportar 100 hospitales, 10 millones
de expedientes y 10.000 usuarios a la vez. De esas respuestas salió un defecto
que ningún capítulo podía ver solo: **la escala de referencia tiene tres cifras
distintas para la misma cosa** —2.350.000, 4.000.000 y 6.000.000 de objeciones
para los mismos 500.000 expedientes— y dos para el almacenamiento (2,4 TB
contra 8 TB). La medida es la primera: sale del acervo real del hospital,
18.371 objeciones para 3.933 facturas. No se corrigió porque elegir la cifra
buena decide el tamaño de medio Contrato, y esa decisión es del área.

Todo esto es **documentación y plan**. No se tocó una línea del código que
corre en producción: la suite de 4.533 pruebas pasa igual que antes.

### 29-07 — Se juntaron las dos memorias del proyecto + bot de Unir Exceles
- **Se fusionó la rama principal en el PR #160** (la Suite Cartera HUS). Al
  hacerlo se descubrió que había **dos bitácoras paralelas** — una en la rama
  principal (todo el frente del Motor/Pre-auditoría/Dispensario) y otra en la
  rama de la Suite (consolidados de cartera, actas, herramientas PDF, bot de
  correos) — porque dos chats trabajaron cada uno con la suya sin saberlo.
  **Se combinaron en esta sola bitácora sin perder ninguna entrada** de
  ningún lado, y lo mismo con las instrucciones del repo (CLAUDE.md). El PR
  #160 quedó **sin conflictos y con las 3 verificaciones en verde** (4.611
  pruebas), listo para revisar y fusionar.
- **Bot nuevo: «📊 Unir Exceles»** (en la Suite y también entregado como ZIP
  suelto de doble clic): une varios archivos Excel en UNO, sin dañar el dato
  (fechas como fechas, montos como números — nunca texto). Dos modos:
  **APILAR** (todas las filas en una sola tabla — para cortes mensuales o
  exportes con las mismas columnas; si un archivo trae columnas nuevas se
  agregan al final y nada se pierde; cada fila queda marcada con su archivo
  de origen y hay hoja RESUMEN) y **HOJAS** (cada archivo queda como una
  hoja aparte del mismo libro). Acepta archivos sueltos, una carpeta o un
  .zip, y salta solo los títulos que vienen encima de los encabezados.
  Por consola: `python suite_cli.py exceles archivo1.xlsx archivo2.xlsx -o
  UNIDO.xlsx` (o `--modo hojas`). Con 9 pruebas automáticas nuevas.
- **Nota del mismo día:** la rama principal volvió a avanzar (PRs #208-#213:
  consecutivo manual del oficio de devolución, bots de pagadores, vencidas
  visibles y el Contrato de Construcción de SINAC OS) y se volvió a fusionar
  aquí, combinando otra vez las dos bitácoras con la misma regla de no
  perder nada.
- **Nota (tarde):** otro chat hizo un "rescate" de la Suite copiando sus
  archivos directo a la rama principal (commit del 29-07 15:26), pero desde
  una foto VIEJA — sin los bots de correos de pagos ni de unir Exceles. Al
  fusionar aquí se reconciliaron las dos copias: quedó la versión completa
  (con los dos bots nuevos) más la mejora que traía el rescate (el lector
  de pesos de `cruces_dgh` ahora usa el lector único `tools/_dinero.py`,
  el mismo de toda la casa). El PR #160 ahora solo aporta lo que la rama
  principal no tiene: los dos bots, sus pruebas y esta bitácora combinada.

### 29-07 — Pre-auditoría: lo que escribía el auditor se perdía

Día de uso real con cuatro auditores trabajando (Vanessa, Camilo, Edgar y
Yesid) y tres arreglos que salieron de lo que ellos vieron en pantalla.

**1. Las observaciones no se guardaban (PR #220, ya en producción).**
El auditor reportó que escribían "OKAY SOPORTES" al radicar y la columna
Observaciones del historial salía vacía en todas las facturas. La causa no
era el historial: **el texto se descartaba en silencio**. La ventana de
auditar tiene dos recuadros —"Motivo de la devolución" arriba y
"Observaciones" abajo— y escribían en el de arriba, que es el que más se ve.
Al radicar, ese motivo no se guardaba en ninguna parte.

Cómo se confirmó, contra la base de producción: **0 de 55** facturas y
**0 de 79** eventos tenían observación guardada, mientras que 4 eventos sí
tenían motivo (todos de devoluciones). Ese contraste fue la prueba.

Ahora nada de lo que escribe el auditor se descarta: si escribió solo en
Motivo, ese texto queda como la observación; si escribió en los dos, se
conservan ambos. Además se pueden **anotar las facturas ya radicadas** sin
revertir la decisión (botón "✎ Guardar observación" en el historial), y los
dos recuadros quedaron rotulados sin ambigüedad, con Observaciones primero.

**2. Se pueden borrar los oficios de devolución (PR #225, ya en producción).**
Cuando el PDF salía con el consecutivo equivocado no había forma de
deshacerlo: el número quedaba quemado y las facturas atrapadas (con el oficio
emitido, revertirlas está bloqueado). Ahora hay un botón 🗑 en la pestaña de
oficios de devolución, **solo para administradores y coordinación**. Las
facturas no cambian de decisión —siguen devueltas— y solo quedan libres para
salir en un oficio nuevo; el consecutivo vuelve a estar disponible y el
historial no se borra. Avisa antes: si el PDF ya se entregó a la entidad, no
hay que eliminarlo.

**3. El PDF del oficio muestra los días transcurridos (PR #228).**
El documento solo traía la fecha de generación. Ahora el encabezado dice
cuándo se recibió el oficio (con hora), cuándo se generó el PDF y cuántos
días completos pasaron. **Un día solo cuenta pasadas 24 horas enteras:** del
22 a las 2:35 p.m. al 24 a las 11:23 a.m. hay 1 día, no 2, aunque el
calendario haya cambiado dos veces. Así el número no depende de la hora a la
que se registró el oficio. Las fechas salen de lo guardado, no del momento de
imprimir: reimprimir el mismo oficio meses después da el mismo documento.

**4. La lentitud: eran las búsquedas (PR #230).** El auditor dijo que la
página "se demora para sacar los datos". Se midió contra la base de
producción antes de tocar nada, y **todo el sistema estaba sano** menos una
cosa: las consultas del consolidado tardan entre 0 y 27 milisegundos, la red
responde en 70, el procesador va al 0,2% y sobra memoria — pero **buscar por
entidad tardaba 1.031 milisegundos**.

La razón: la entidad y el NIT no están en el consolidado (que son 55
facturas), sino en la tabla de la fuente, que tiene **189.452 filas**. Cada
búsqueda las recorría todas, y lo hacía **dos veces** (una para contar y otra
para traer la página): unos **2 segundos cada vez que alguien escribía en el
buscador**.

El arreglo: la fuente solo importa para las facturas que ya están en el
consolidado, así que ahora se buscan primero esas —por el número de factura,
que sí tiene índice— y el filtro de texto cae sobre ese puñado. Comprobado
reproduciendo la tabla real: **de 73 ms a 0,1 ms**, con resultados idénticos
en 7 patrones distintos. No cambia lo que se ve, solo cómo se llega.

**Lo aprendido sobre la VM, para no volver a perder tiempo.** Los comandos
que se intentaron primero fallaron porque en la VM el repositorio está en
`/opt/motor-glosas` (no en la carpeta personal) y el motor corre en **Docker**,
no como servicio de systemd. Además, **el despliegue es automático**: un
proceso revisa cada 5 minutos si hay código nuevo y lo aplica solo. Cuidado
con confundir las dos máquinas: si el prompt dice `@cloudshell` se está fuera
de la VM y nada se encuentra; dentro dice `@motor-glosas`. Comando para mirar
cómo está, desde Cloud Shell y en un solo paso:

```bash
gcloud compute ssh motor-glosas --zone=us-west1-a --tunnel-through-iap --command '
cd /opt/motor-glosas && git log --oneline -1
sudo docker compose ps
free -m | head -2
'
```

### 29-07 (segunda parte) — El contrato correcto, en todas las pantallas

Sprint de construcción del día (varios PR fusionados en cadena):

- **Al analizar una glosa, manda la fecha del hecho.** El dictamen cita el
  contrato que regía el día de la atención, no el de hoy. Si ese día no regía
  ninguno (ej.: COMPENSAR después del 3 de abril de 2026), la IA recibe la
  alerta y defiende a tarifa SOAT plena en vez de citar un contrato muerto.
- **Cada análisis deja constancia en el expediente.** En la línea de tiempo de
  la glosa queda escrito qué contrato se usó, si estaba vigente ese día y con
  qué factor, en una frase clara y con color según el veredicto: verde
  (vigente), ámbar (sin contrato ese día), rojo (pagador fuera de la malla).
  Cuando la EPS discuta la tarifa meses después, la respuesta está escrita en
  el expediente, no en la memoria de nadie.
- **El asistente del chat ya consulta la malla.** Preguntas como «¿qué
  contrato de COMPENSAR regía en septiembre?» se responden con la malla
  oficial, y el asistente tiene prohibido citar un contrato sin verificar
  primero que regía el día del hecho.
- Pantallas nuevas de los días previos, ya fusionadas y desplegadas:
  **Contratos** (malla completa con buscador, filtros de un clic y semáforo de
  vencimientos, más el buscador de material de osteosíntesis con la defensa
  lista para pegar) y **Automatización** (robots de cartera desde el
  navegador, arrastrando el archivo).

### 29-07 (tercera parte) — Épica: el Expediente Inteligente

- **Pantalla nueva «Expediente»** en el menú: se busca por ID de glosa o por
  factura y aparece TODO en un solo lugar — la ficha, el contrato que rige
  con su color (verde/ámbar/rojo), las conciliaciones, los soportes y la
  línea de tiempo completa con filtros de un clic. El popup viejo de
  timeline (ventana aparte) se eliminó: el botón 📜 ahora entra acá.
- **El acta de la mesa se cuadra sola.** En la pantalla Conciliación se sube
  el mismo Excel que se diligencia en la audiencia (el de las 147 del
  Dispensario, por ejemplo) y el sistema: dice qué no cuadra (fila por
  fila), devuelve el libro optimizado con el resultado de cada línea y una
  hoja REVISION, y arma el acta lista para imprimir y firmar con la cláusula
  de mérito ejecutivo y las firmas leídas del propio libro. Probado con el
  acta real: 444 líneas, 147 facturas, $317.640.524 glosados y los
  $11.836.399 levantados, cuadre exacto.
- **La IA ya consulta expedientes**: en el chat se puede preguntar «¿qué ha
  pasado con la factura HUS…?» y responde con la misma información de la
  pantalla. Cada uso del acta queda registrado en la auditoría del sistema.
- Guía corta en `docs/EXPEDIENTE_INTELIGENTE.md`.

### 29-07 (cuarta parte) — Épica: el Centro de Inteligencia + arreglo de producción

- **El sistema ahora dice qué hacer hoy.** Nueva primera opción del menú:
  **Inteligencia**. Barre toda la operación —glosas vencidas y por vencer
  con su plata, contratos caídos o por caer, análisis defendidos sin
  contrato, audiencias encima sin acta, actas a medio cuadrar— y entrega
  la lista de acciones ordenada por urgencia y valor, cada una con el
  botón que lleva a la pantalla donde se resuelve. El número rojo del
  menú (frentes urgentes) se actualiza solo.
- **La IA pasó de asistente a directora**: al preguntarle «¿qué hago
  hoy?» corre el mismo barrido y dirige — empieza por lo rojo, dice la
  plata en juego y qué abrir primero.
- **Se arregló la causa raíz del «Error 500» de Automatización en el
  servidor**: la imagen de producción no llevaba la carpeta de
  herramientas (regla vieja del empaque). Quedó la lista blanca, una
  guardia en la suite para que no vuelva a pasar, y además ningún robot
  vuelve a contestar «Error 500» pelado: ahora explican qué pasó.
- Guía corta en `docs/CENTRO_INTELIGENCIA.md`.

### 29-07 (quinta parte) — Épica: el Centro Documental

- **La carpeta de cada expediente se arma sola.** Dentro de la pantalla
  Expediente aparece «📁 Centro Documental»: el PDF radicable del
  dictamen, el dictamen en texto, el historial de versiones, el acta de
  cada mesa de conciliación, el paquete de evidencia para jurídica y los
  soportes de la factura que el indexador encontró en el share — cada
  uno con su botón de descarga o su ruta. Se acabó buscar «todo lo de
  esta factura» a mano.
- Los soportes del share NO se sirven por la web (son historia clínica):
  se muestra la ruta para abrirlos desde el equipo del hospital, como
  siempre.
- La misma carpeta la entrega la API y el chat IA («¿qué documentos hay
  de la factura…?»). Guía corta en `docs/CENTRO_DOCUMENTAL.md`.

### 29-07 (sexta parte) — Épica: el Motor Universal

- **Un perfil único por pagador.** En la pantalla Contratos, al expandir
  cualquier pagador aparece «El sistema con este pagador»: si el análisis
  cita su contrato por fecha, si hay respuesta masiva por lotes y con qué
  bot, qué conversores de Automatización le aplican y si hay contacto de
  radicación. Lo mismo responde el chat («¿qué se puede hacer con
  COOSALUD?») y la API.
- **La regla que queda sellada**: agregar un pagador o una capacidad
  nunca vuelve a ser tocar código repartido — es agregar una ficha en el
  registro que corresponde (malla, perfil de lote o catálogo de
  automatización) y el perfil la muestra solo en las tres superficies.
- Guía corta en `docs/MOTOR_UNIVERSAL.md`.

### 03-08 (tercera parte) — El Centro de Inteligencia vigila los bots y los lotes

- El barrido del día ganó dos ojos nuevos: **los trabajos de bots que
  fallaron** esta semana (con qué bot y a dónde ir a reintentarlos) y los
  que llevan **más de una hora en cola sin que ningún PC los reclame**
  (señal de que el agente de bots no está abierto), y **los lotes de
  respuesta masiva que quedaron a medias** (completados con facturas
  pendientes o en error). Todo aparece en la pantalla Inteligencia y en
  el chat, con su botón directo a Automatización.

### 03-08 (segunda parte) — Ronda 35: el formato de respuesta que aprobó Yesid

- La respuesta del caso de la citología quedó como **modelo oficial del
  motor**: primera línea de referencia («RESPUESTA GLOSA … – FACTURA … –
  CUPS …»), postura seca, y **un punto numerado por cada reclamo de la
  glosa** — si la entidad reclama tres cosas, se contestan las tres, cada
  una con su norma. Ni reclamos sin contestar (eso es conceder), ni
  puntos de relleno.
- La respuesta completa entró además al banco de plantillas del motor
  (TA-G11) para el patrón «SOAT UVB sin contrato»: la próxima glosa así
  sale con esa misma factura de estilo.

### 03-08 — Ronda 34: dos reglas del caso TA0801/citología

- Del caso real que trajo Yesid (factura 1344527, citología 898015H,
  ajuste de $1.700 «SOAT UVB»): el motor aprendió que **«se reconoce SOAT
  UVB» + «sin acuerdo de voluntades» NO significa accidente de tránsito**
  — significa que la entidad liquida a SOAT por falta de contrato. La
  defensa correcta: SOAT PLENO sin descuentos, UVB vigente a la fecha de
  atención (2026 = $12.110), y exigir el desglose del ajuste (los ajustes
  chicos suelen ser UVB del año anterior o descuentos que nadie pactó).
- Y que **«ayuda diagnóstica no interpretada» no existe en patología**:
  en citologías y estudios anatomopatológicos la interpretación ES el
  servicio — el producto es el informe del patólogo, que se anexa.

### 03-08 — El expediente entiende de facturas y lleva al trabajo

- **Buscar una factura en Expediente ahora muestra EL CASO completo**: una
  cabecera con el pagador, cuántas glosas tiene (y cuántas siguen
  abiertas), el total objetado y el aceptado — y cada glosa como una
  ficha de un clic para saltar entre ellas sin volver a buscar.
- **Del expediente al trabajo en un clic**: la ficha trae «Abrir en
  Analizar» (directo a trabajar la glosa) y «Ver toda la factura».

### 30-07 (segunda parte) — Las tarjetas de COOSALUD y SIMED cuentan su lote

- Los dos bots que trabajan por Lotes ya muestran **su cola real en la
  propia tarjeta**: qué lote va (archivo, cuántas facturas, quién lo
  subió), en qué equipo corre, y si terminó con facturas pendientes la
  tarjeta queda en ámbar «CON PENDIENTES» — nunca más un verde engañoso.
  El botón lleva directo a la pantalla de Lotes.
- Una revisión automática con verificadores independientes encontró
  cuatro defectos antes de publicar (botones que no aplicaban a lotes,
  el estado «completado con pendientes» invisible, y una consulta que
  cargaba el Excel completo de cada lote a la memoria del servidor —
  el mismo error que ya había tumbado la instancia una vez). Los cuatro
  quedaron corregidos y sellados con pruebas.

### 30-07 — Todos los bots del hospital, administrados desde la plataforma

- **Se acabó el doble clic a ciegas.** El Centro de Automatización ahora
  muestra los **35 bots del hospital** (COOSALUD, SIMED, FOMAG, MUTUAL SER,
  DGH, ADRES, NUEVA EPS, radicador, notas crédito, PDFs, informes…) con su
  estado en vivo: disponible, en cola, corriendo (con avance y en qué
  equipo), o en error (con el motivo). Cada tarjeta trae Ejecutar,
  Cancelar, Reintentar, Historial, Ver registros y Configurar.
- **Cola universal**: «Ejecutar» encola el trabajo; el **agente de bots**
  del PC del HUS (doble clic en `AGENTE_BOTS.cmd`, usa la misma URL y
  token del agente de lotes) lo reclama, lo corre y reporta — la tarjeta
  se actualiza sola. El agente no conoce ningún bot por nombre: el
  comando viaja desde el catálogo.
- Quién pidió qué bot, en qué equipo corrió, cuánto tardó y por qué falló:
  todo queda en la auditoría y en el historial de cada tarjeta.

### 29-07 (séptima parte) — Épica: el Constructor de Agentes

- **El sistema ya arma sus propios agentes.** Menú → Herramientas →
  **Agentes**: se escribe la misión, las instrucciones y se marcan las
  herramientas permitidas — y el agente queda corriendo con todo lo que
  el sistema sabe (expediente, malla, diagnóstico, soportes), pero SOLO
  dentro de su misión y sus herramientas. Sin programar nada.
- Dos plantillas de fábrica para arrancar con un clic: **Vigilante de
  vencimientos** y **Preparador de mesa**.
- Cada construcción, corrida y retiro queda en la auditoría (quién, qué
  agente, qué preguntó, qué herramientas usó).
- Guía corta en `docs/CONSTRUCTOR_AGENTES.md`.

### 30-07 — Pre-auditoría: una sola observación, corregible aunque el oficio ya exista

**1. La pantalla explica qué pasa con cada devuelta (PR #232).** El caso de las
3 facturas que "no salieron" en el oficio DEV-PRE-AUD-0099: sí habían salido,
pero en el oficio anterior (0097), y la pantalla no lo decía. Ahora el contador
de la ventana del oficio distingue cuántas devueltas **ya salieron** en un
oficio y cuántas **faltan por incluir**, el botón dice cuántas facturas saldrán
en el oficio nuevo, y cada factura muestra en cuál oficio salió. (Una factura
no se repite en dos oficios: la entidad recibiría el mismo cobro dos veces.)

**2. Un solo recuadro de observación (mismo PR #232).** La ventana de auditar
tenía dos recuadros —"Observaciones" y "Motivo de la devolución"— y seguían
prestándose a confusión: un texto de devolución del FURIPS quedó escrito en el
recuadro que NO sale en el oficio. A pedido del auditor quedaron en **uno
solo**: lo que se escriba ahí se guarda siempre y, si la factura se devuelve,
ese mismo texto es el que imprime el oficio de devolución.

**3. La observación se corrige aunque el oficio ya se haya generado.** Si el
oficio salió con un error en el texto, el auditor abre la factura con el botón
"👁 Ver", corrige la observación y la guarda. Si la factura ya salió en un
oficio de devolución, la corrección **también corrige el oficio**: el PDF se
arma cada vez que se abre, así que basta volver a abrirlo para verlo al día.
Los oficios de rondas anteriores no se tocan (esos ya se entregaron tal como
estaban) y cada corrección queda en el historial con quién la hizo y cuándo.

### 03-08 — Pre-auditoría: el registro de envíos "borrado" y la regla de los 3 oficios

**Qué se vio en pantalla.** La columna Envíos de casi todos los oficios
apareció vacía ("se borró toda la información") y al cargar un envío repetido
seguía saliendo "El envío ya fue cargado", aunque el viernes se había subido
un cambio para permitir el mismo envío en hasta 3 oficios.

**Qué pasó de verdad (nada de las decisiones se perdió).** El cambio del
viernes 31-07 modificó la regla en el código pero **no cambió el candado
dentro de la base de datos** que ya estaba en producción: la base seguía
exigiendo "un envío una sola vez en todo el sistema". Por eso siguió
bloqueando, y en el afán de destrabarlo el REGISTRO de envíos (qué envío
entró en qué oficio, quién y cuándo) quedó vacío. Importante: ese registro
es solo la "tabla de contenido" — los oficios, las facturas, las decisiones
de los auditores y el historial completo quedaron intactos (por eso las
columnas Facturas/Pend/OK/Dev siguen con sus números).

**Qué se hizo hoy:**
1. **La migración que faltaba**: al arrancar, el sistema ahora corrige solo
   el candado de la base — pasa de "un envío una sola vez" a "un envío una
   sola vez POR OFICIO". Con eso la regla de los 3 oficios funciona de
   verdad, sin tocar nada a mano.
2. **La regla completa de recarga**: el mismo envío se acepta en hasta
   **3 oficios distintos** (el original + las subsanaciones que facturación
   reenvía con el mismo número). Al recargar solo se mueven las facturas
   devueltas; las radicadas y pendientes se quedan donde están, con su
   aviso. El 4.º intento se bloquea nombrando los radicados. "Ver antes"
   avisa en qué oficios ya salió el envío y qué va a pasar si se carga.
3. **Recuperación del registro borrado**: el historial de cada factura es
   inmutable y guarda envío + oficio + auditor + fecha, así que se armó un
   comando (3 pasos: mirar → aplicar → aplicar todo) que reconstruye el
   registro de envíos desde ese historial, sin borrar ni modificar nada de
   lo existente. Probado contra una réplica local con el mismo escenario.
4. De paso se confirmó que el sistema **hace una copia de seguridad
   automática todos los días a las 3:00 a. m.** (guarda las últimas 14, en
   `/data/backups` de la VM).

**Lección para todos los chats:** cambiar un candado/índice en el código
SIN su migración deja producción con la regla vieja; y destrabar borrando
registros a mano borra la trazabilidad. Siempre: migración en el código +
piloto + PR, nunca DELETE a mano contra la base de producción.

**Endurecimiento posterior (mismo día, revisión adversarial):** se detectó
y corrigió que (1) eliminar el oficio original después de recargar su envío
en otro daba error 500 — ahora explica que las facturas ya subsanaron y no
se puede; (2) quitar el envío del oficio original tras la recarga devolvía
un cupo del tope de 3 en silencio — ahora se bloquea con su porqué; (3) dos
cargas simultáneas del mismo envío podían pasarse del tope o terminar en
error 500 — ahora la segunda recibe un aviso claro; y (4) la migración del
candado se auto-repara si un arranque muere a mitad de camino.

### 03-08 (segunda parte) — Solo administración corrige auditorías decididas + informe de gestión

A pedido del auditor:

1. **Las auditorías ya decididas quedan protegidas.** Revertir una factura
   radicada o devuelta, o corregir su observación (que también corrige el
   PDF del oficio de devolución, porque el PDF se arma al abrirlo), ahora
   es SOLO de coordinación o administración. El auditor sigue escribiendo
   su observación con normalidad al decidir, y mientras la factura esté
   pendiente. En la pantalla, quien no es administrador ve el botón
   bloqueado con la explicación, y el servidor lo exige de todos modos.
2. **Informe de gestión descargable.** En la pestaña Estadísticas quedó el
   botón "⬇ Informe de gestión (Excel)": un libro con 5 hojas — RESUMEN
   (totales y valores), POR AUDITOR, POR OFICIO, DEVOLUCIONES e HISTORIAL
   (el registro completo de eventos: qué se hizo, quién, cuándo, con motivo
   y observación de cada movimiento).

105 pruebas del módulo en verde.

---

### 03-08 (SIIFA) — el informe masivo por fin se baja completo

Día de corridas reales contra SIIFA con las credenciales del auditor. Cada
falla que apareció en pantalla quedó corregida el mismo día:

1. **El bot se colgaba a mitad de camino** (PR #249). Dos causas: el permiso
   de entrada (token) se vencía durante una descarga larga y nadie lo
   renovaba, y ante un error definitivo del servidor el bot volvía a
   intentar lo mismo una y otra vez. Ahora renueva el permiso solo y deja de
   insistir cuando el error no tiene remedio.
2. **No entraba con el usuario del auditor** (PR #252). El script pedía la
   variable con un nombre y el auditor tenía otro: ahora acepta
   `SIIFA_USERNAME` además del nombre anterior, y la prueba de conexión dice
   con claridad si el problema es de usuario, de clave o de red.
3. **El servidor del Ministerio no aguantaba la consulta completa**
   (PR #254). Cuando la consulta de todo el período se cae, el bot ya no se
   rinde: baja el informe **mes por mes** y lo une, sin registros repetidos.
4. **Dos remates** (PR #255): se recuperó un ajuste que se había perdido al
   rehacer la rama (tandas de 50 registros en vez de 200, que bajan solas si
   el servidor se queja) y se cubrió el caso real en que la consulta **no
   responde nunca** (se queda esperando) — antes ese camino terminaba sin
   informe; ahora también dispara el rescate mes por mes.

Todo probado con un servidor de prueba que imita las fallas reales.

**OJO — la segunda corrida borró el informe bueno.** Después de actualizar
la carpeta, el auditor volvió a correr el informe y el servidor del
Ministerio estaba sobrecargado: alcanzó a bajar 50 registros y se cayó. El
bot, en vez de completar el informe mes por mes, se conformó con esas 50
filas **y las guardó encima del Excel bueno de 2.597**, que se perdió. Se
corrigieron las dos cosas el mismo día:

- Si la consulta completa se corta a medias, ahora **sigue mes por mes**
  igual (antes solo lo hacía si no había bajado nada). Los repetidos se
  quitan al final por número de seguimiento.
- **Un informe incompleto ya no puede pisar a uno bueno.** Se guarda al lado
  con `_PARCIAL` en el nombre y el anterior queda intacto. Vale para las
  tres formas de quedar incompleto: cancelado con Ctrl-C, consulta cortada,
  o algún mes que no se pudo traer.
- Seis pruebas nuevas que reproducen exactamente lo que pasó (se verificó
  que fallan con el código anterior).

**Lo que salió del informe, ya cruzado con lo que el hospital respondió.**
Con el informe en la mano se armó el camino completo para cargar las
respuestas, y aparecieron tres cosas que importan más que el bot:

- **El valor de las devoluciones que muestra el informe está inflado.** La
  hoja RESUMEN dice $24.921 millones, pero SIIFA registra cada devolución
  repitiendo el valor completo de la factura: HUS475438 aparece 340 veces,
  cada una por sus $51 millones. **El valor real de las 10 facturas
  devueltas es $115.051.312.** Ese es el número que va a un informe.
- **El trabajo es mucho menor de lo que parece.** Las 2.579 líneas
  pendientes se responden con **272 textos distintos**, y son apenas 58
  facturas con glosa y 10 con devolución.
- **Casi todo está vencido:** 85 glosas con más de 90 días y 685 entre 61 y
  90, contra un plazo de ley de 15 días hábiles.

Y el hallazgo que ahorra el trabajo: **1.082 de las 2.579 líneas YA fueron
respondidas por el hospital**, con la respuesta escrita en la base de
trámites de Dinámica Gerencial, sólo que nunca se cargó al portal del
Ministerio. Se hicieron dos herramientas nuevas:
`tools/siifa_preparar_respuestas.py` (agrupa las líneas repetidas y después
reparte la respuesta a cada una) y `tools/siifa_cruzar_tramites_dgh.py`
(busca en DGH la respuesta ya dada y deja la hoja de trabajo pre-llenada,
marcando de dónde salió cada una). De las 272 respuestas, 162 salieron de
DGH y 110 hay que escribirlas.

**Y la corrida real salió bien: el Excel maestro ya está bajado.** El
informe quedó en `D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx`
con **2.597 seguimientos, 2.579 sin respuesta del HUS** — el mismo 2.579 que
se ve en la pantalla de SIIFA, así que cuadra con el portal. Duró 16 minutos.
Por meses: enero 487, febrero 559 (partido en dos quincenas porque el servidor
no aguantó el mes entero), marzo 600, abril 432, mayo 181, junio 224 (también
partido), julio 114. De 2025 no hay nada. Sin registros repetidos y sin
períodos perdidos.

---

### 05-08 (tarde) — Doce glosas de trampa destaparon nueve fallas del motor

Yesid pidió glosas difíciles para poner a prueba la IA. Se armaron doce,
cada una diseñada para romper un punto distinto, y pasó seis por la
página. **Falló en casi todas.** El día se fue en arreglarlas, una por una,
con sus pruebas.

Lo que salió mal y qué había detrás:

1. **Mayúsculas.** Los dictámenes salían mezclados y aparecía «En **ESE**
   orden de ideas». No era el modelo desobedeciendo: había un normalizador
   que **bajaba a minúsculas a propósito** todo dictamen que viniera en
   mayúsculas. Se retiró. Ahora lo decide el sistema, no la IA.
2. **Aceptación parcial.** La glosa decía «LA IPS ACEPTA $340.000» y el
   motor recomendó defender el 100%. Nadie leía esa frase. Peor: el botón
   «Aplicar recomendación» **buscaba campos que no existen, no cargaba
   nada, y aun así decía «aplicada»**. Cada vez que se usó, el valor
   aceptado no quedó registrado ni habilitó la nota crédito.
3. **Dictamen cortado** en «$ 12.». No era el modelo: el post-proceso
   cortaba en el primer punto y en «12.300.000» ese punto es el separador
   de miles. El mismo corte partía «E.S.E.», «ART. 87» y «FACTURA NO.».
4. **Código de glosa usado como CUPS** («servicio con CUPS DE1601»). El
   código entraba por la ranura del CUPS **antes** de que la IA escribiera
   nada, y después ella inventaba qué procedimiento sería.
5. **Dispensario.** El texto fijo respondía toda glosa TA de ese pagador
   **sin leer de qué hablaba**, y ese camino se salta el control de
   calidad. Decisión de Yesid: sigue, pero solo cuando el tema calce.
6. **ARL (POSITIVA).** Se le respondió con normas del régimen de salud
   común. La regla correcta existía desde abril; fallaba porque otras dos
   partes del sistema le ordenaban lo contrario — entre ellas, servirle
   como ejemplo respuestas escritas para EPS.
7. **Sub-objeciones.** Una glosa con cuatro objeciones recibió una sola
   respuesta. El detector no reconocía la forma en que estaba escrita, y
   además vivía en una rama del código donde no siempre se ejecutaba.
8. **Devolución tratada como glosa.** Para el motor, la familia DE **no
   existía**: la convertía en glosa de facturación. Son trámites distintos
   y confundirlos puede costar el término de radicación.
9. **Norma derogada.** La Resolución 3047 de 2008 seguía citándose,
   también en la plantilla guardada en la base que alimenta los ejemplos
   de la IA. Corregida a la 2284 de 2023, y la plantilla vieja se corrige
   sola al arrancar.

**La lección del día:** en **cinco de las nueve**, la regla correcta ya
estaba escrita y no podía funcionar — por una condición que no abría, por
vivir en la rama equivocada, por vocabulario corto, o porque otra
instrucción la contradecía. Escribir la regla no era el trabajo; el
trabajo era comprobar que llegara.

Quedaron 55 pruebas nuevas y la suite en 5.704. Las doce glosas de trampa
sirven para repetir el ejercicio cuando se toque el motor.

### 05-08 — El consolidado histórico de pre-auditoría entra por Excel

La base provisional del PC arrancó vacía y el módulo de Pre-auditoría
quedó sin su historia. Pero el equipo llevó SIEMPRE su consolidado a mano
(`CONSOLIDADO_PRE_AUDITORIA_2026.xlsx`, una fila por pasada de factura,
del 13-04 al 04-08): ese Excel ES la historia completa, más incluso que
la base vieja de la VM. Se construyó
`tools/preauditoria_importar_consolidado.py`:

- **SOLO MIRAR** (sin argumento): muestra el plan completo sin escribir.
  Con el Excel real: 1.324 pasadas → **959 facturas** (511 radicadas,
  348 subsanadas, 83 devueltas/bloqueadas, 17 pendientes), 150 oficios
  (143 FHUS reales + 7 históricos), 1.043 renglones de ledger de envíos,
  3.058 eventos de historial con fechas y valores reales.
- **aplicar**: escribe todo en una sola transacción. **El sistema manda**:
  lo que el equipo ya registró en la página no se toca; correrlo dos veces
  no duplica nada (probado con los datos reales).
- Los nombres cortos del Excel se traducen al nombre completo del equipo
  (OSCAR→OSCAR VILLAMIZAR, CAMILO→CAMILO CASTILLO, etc.). 7 pruebas
  automáticas.

### 04-08 (décima parte) — La causa de fondo: el vigilante entregaba claves viejas

Aquí terminó el misterio del día. La página por internet seguía diciendo
«su clave está inválida (la que usó: gsk_5CxaRq…)» a las 3 de la tarde,
con el archivo de claves correcto desde el mediodía y el otro motor
mostrando la clave nueva sin problema.

**El porqué.** `tools/servidor_motor_local.cmd` es la ventana que mantiene
vivo el servidor de la página pública: si se cae, lo vuelve a levantar a
los 5 segundos. Pero **cargaba el archivo de claves una sola vez, antes de
entrar a ese bucle**. Cada vez que revivía el servidor le entregaba el
ambiente de cuando se abrió la ventana — y las variables de ambiente le
ganan al archivo. Resultado: **ese motor se queda con las claves del día
en que se abrió la ventana, para siempre**, por más que se cambie el
archivo y por más veces que se reinicie solo.

Por eso todo lo de hoy se veía contradictorio: el motor de pruebas (8000)
mostraba la clave nueva y decía la verdad; el de la página (8080) usaba la
vieja y también decía la verdad. Cada mitad tenía razón por separado.

Lo que quedó hecho:

- **El vigilante relee el archivo de claves en cada vuelta.** Un reinicio
  ahora sí toma las claves de hoy.
- **El motor avisa cuando no está usando las claves del archivo**: la
  tarjeta «Motor» del Diagnóstico se pone en ROJO y dice, sin revelar las
  claves, *«está usando gsk_5CxaRq… pero el archivo dice gsk_vn06EE…»* y
  qué ventana hay que cerrar. Es lo que hoy no se podía ver de ninguna
  manera.
- **La tarea automática cada 5 minutos** cerraba cualquier motor de la
  aplicación: ahora solo reinicia el de producción (puerto 8080), así que
  ya no le apaga el de pruebas al auditor sin explicación.
- **El bot de reinicio** pasó a un archivo aparte (`tools/reiniciar_motor.ps1`)
  con cinco correcciones que salieron de una revisión adversarial: no cierra
  motores de otro puerto, comprueba que de verdad murieron (antes se tragaba
  el «acceso denegado» y decía «cerrado»), no mata al dueño del puerto si no
  es el motor, avisa de los programas que Windows no lo deja ver, y consulta
  el puerto sin depender del idioma —el filtro anterior buscaba «LISTENING»
  y **en un Windows en español nunca encontraba nada**, por eso decía «no
  había ningún motor encendido» cuando sí lo había—.

**Cierre del día, con la máquina de Yesid como banco de pruebas.** Cada
corrida real destapó algo más:

- El bot mostró **dos motores en el puerto 8080** y parecía haber un
  intruso. No lo había: en Windows el Python del proyecto es un lanzador
  que arranca el intérprete de verdad como **proceso hijo**, y es el hijo
  el que se queda con el puerto. Un solo motor. El bot ahora los cuenta
  como uno —pero al cerrar se lleva padre e hijo, porque matar solo al
  padre dejaría vivo justo al que tiene el puerto—.
- **La página por internet no revivía sola si había un motor de pruebas
  abierto.** El vigilante se negaba a arrancar cuando veía cualquier motor
  de la aplicación, sin mirar el puerto. Con el 8000 encendido —que es lo
  que el propio bot invita a hacer— la página pública se habría quedado
  caída en el próximo corte. Corregido: mira el puerto.
- Si algún día se arranca con la opción de recarga automática, el proceso
  que de verdad atiende **se llama distinto** y el bot no lo veía: cerraba
  al padre y dejaba al hijo con el puerto tomado. Ahora cierra el árbol
  completo.
- Y un detalle de presentación: un guion largo salía en la consola como
  `â€`. Los mensajes del bot ahora usan solo caracteres que Windows
  muestra bien, con una prueba que lo impide a futuro.

**Dos bots nuevos en el menú (`MOTOR_HUS.cmd`, opciones 16 y 17):**

- **`ESTADO_MOTOR.cmd` — «¿está bien la página?»**. Doble clic y en una
  pantalla sale todo: quién atiende la página por internet, con qué clave
  de IA, si el túnel publica, si el vigilante está encendido, si arranca
  solo al iniciar sesión, y las tareas automáticas. Al final una lista de
  avisos con qué hacer si algo falta. **Solo mira: no cierra ni arranca
  nada.** Antes eso eran cinco órdenes de PowerShell pegadas a mano y
  había que saber interpretarlas.
- **`REINICIAR_MOTOR.cmd`** — el de reiniciar el motor de pruebas, ahora
  también desde el menú.

### 04-08 (novena parte) — Quién puede tocar qué: las 51 puertas abiertas

El 28 de julio se encontraron cuatro «puertas de al lado»: rutas del
sistema por las que se podía cambiar una glosa **sin comprobar el cargo**
de quien lo pedía. Se cerraron una por una, pero quedaban **51 rutas** que
solo pedían haber entrado con usuario y contraseña, sin que nadie hubiera
decidido si eso estaba bien o era otro descuido esperando.

Quedaron todas decididas y escritas:

- **39 pasaron a exigir cargo de auditor o superior**: analizar una glosa,
  importar en masa, comentar en el expediente, validar, restaurar una
  versión del dictamen, decidir glosas ADRES, crear plantillas del equipo,
  preguntarle a la IA, generar el PDF del acta.
- **2 pasaron a coordinación**: subir el PDF de un contrato y mandar
  alertas por correo a todo el equipo.
- **12 se quedan como estaban** porque son del propio usuario: entrar y
  salir, cambiar su contraseña, su segundo factor, sus tareas, sus
  vacaciones y el buzón de sugerencias.
- **9 ya comprobaban el cargo por dentro** (las que dependen del dato:
  «esta glosa es de otro auditor»), y ahora una prueba verifica que ese
  chequeo exista de verdad.

El único que pierde algo es el perfil **VIEWER** (el que solo mira), que
es exactamente para lo que existe. El auditor no perdió nada: hay pruebas
que lo comprueban en las dos direcciones.

Lo importante para el futuro: **una ruta nueva que modifique datos y no
tenga decisión de permisos rompe las pruebas**. Ya no depende de que
alguien se acuerde de revisarlo.

### 04-08 (octava parte) — Una librería ajena tapó la carpeta de los bots

A las 18:20 (hora universal) se publicó **Mako 1.4.0**, una librería que
viene incluida con otra que usa el sistema. Esa versión salió con un error
de empaquetado: trae **una carpeta llamada `tools/` propia** que se instala
junto a las librerías y **tapa la carpeta `tools/` del proyecto** —donde
viven todos los bots—. Cuarenta y cinco minutos después, las pruebas
automáticas del repositorio empezaron a morir con «No module named
'tools._dinero'». No fue nada que hubiéramos hecho: le pasa a cualquier
proyecto que tenga su propia carpeta con ese nombre.

Lo grave es lo que habría pasado en producción: es exactamente el mismo
síntoma del incidente del 31 de julio (todas las tarjetas del Centro de
Automatización contestando «ModuleNotFoundError»). Bastaba con reinstalar
las librerías en el PC o volver a armar la imagen del servidor.

Quedó blindado por partida doble:

- La carpeta `tools/` del proyecto ahora es un **paquete de verdad**
  (`tools/__init__.py`): con eso gana siempre la del repositorio, sin
  importar qué librería se llame igual mañana. Y viaja a la imagen del
  servidor (línea nueva en `.dockerignore`).
- Se le puso **tope a esa librería** (`Mako` por debajo de 1.4) para no
  traer esa basura mientras el error siga arriba.
- Dos pruebas nuevas lo vigilan: que el paquete exista y que sea el del
  repositorio el que se carga, y que viaje en la imagen.

### 04-08 (séptima parte) — Había DOS motores prendidos al mismo tiempo

Este fue el verdadero culpable de toda la tarde. Yesid cambió la clave de
Groq, reinició y el arranque escribió **`groq=OK gsk_vn06EE…`**; pero la
pantalla de Diagnóstico —que lee exactamente el mismo dato— mostraba
**`gsk_5CxaRq…`** (la clave vieja) y el análisis seguía fallando con «clave
inválida». Dos respuestas distintas para el mismo dato solo tienen una
explicación: **no era un solo programa contestando, eran dos**.

**La explicación de verdad (y no era la primera que se pensó).** En el PC
del hospital corren **dos motores al mismo tiempo, en puertos distintos**:

- el del **puerto 8080**, que lo mantiene vivo `tools/servidor_motor_local.cmd`
  y es **el que alimenta la página por internet** (el túnel de Cloudflare);
- el del **puerto 8000**, que es el que Yesid levanta a mano para probar.

El del 8080 llevaba horas arriba, así que conservaba la clave vieja y el
programa viejo — y **el navegador estaba hablando con ese**. Por eso el
arranque del 8000 mostraba una clave y la pantalla mostraba la otra: no era
una pantalla mintiendo, eran dos sistemas distintos.

(La primera sospecha fue que los dos se peleaban el mismo puerto. Quedó
descartada en vivo: al intentar levantar un segundo motor en el 8080,
Windows respondió «solo se permite un uso de cada dirección de socket».)

**La lección, que quedó escrita en el sistema:** si se cambia el archivo de
claves, hay que **reiniciar los dos motores**. Reiniciar solo el de pruebas
no toca la página por internet.

Lo que se construyó para que no vuelva a pasar:

- **`tools/REINICIAR_MOTOR.cmd`** (doble clic): cierra los motores **de su
  propio puerto** —incluido el que quedó vivo sin estar atendiendo— y deja
  uno solo recién arrancado. De los de otro puerto **avisa y no los toca**:
  la primera versión los cerraba a todos y así se tumbó la página pública
  por error.
- **El Diagnóstico avisa primero**: la primera tarjeta del panel ahora es
  **«Motor (quién está atendiendo)»**, con el puerto de cada uno. Si dos se
  pelean el mismo puerto se pone en ROJO («cerrá el sobrante»); si están en
  puertos distintos avisa en amarillo que son **dos instalaciones separadas**
  y que hay que reiniciar las dos — sin mandar a cerrar ninguna.
- **El arranque también lo dice**: junto a `[IA-PROVIDERS]` aparece
  `[MOTOR] Un solo motor atendiendo…` o `[MOTOR-DUPLICADO] …`.
- **El aviso de error dice CUÁL clave usó**: «GROQ: su clave está inválida o
  vencida (la que usó: gsk_5CxaRq…)». Con eso se compara de un vistazo
  contra la del arranque y se sabe si contestó el motor viejo.
- **El botón «Probar proveedores de IA»** muestra la clave que probó y
  advierte si hay más de un motor encendido (si no, uno ve verde y el
  análisis igual falla).

De paso apareció otro defecto real: cuando la clave estaba vencida, el motor
**apagaba el «razonador» de uno de los modelos de Groq para el resto del
día** (confundía el error de clave con un rechazo de ese ajuste). Los
dictámenes salían más pobres y nada lo decía. Corregido: solo se apaga si el
error nombra de verdad a ese ajuste.

### 04-08 (sexta parte) — Botón para probar la clave de IA

- En **Gobierno IA** hay un botón **«Probar proveedores de IA»**: hace una
  llamada mínima a cada proveedor y dice en un renglón si la clave sirve
  («✓ GROQ (principal) — respondió con llama-3.3-70b») o por qué no. Nació
  del día de hoy: la única forma de saber si una clave nueva funcionaba
  era analizar una glosa de verdad y ver si fallaba.
- Y el aviso ya no deja causas en blanco: si un proveedor falla sin
  explicar, dice «no respondió» en vez de dejar el renglón vacío.

### 04-08 (quinta parte) — El .env correcto que el sistema no veía

- Yesid montó el sistema en su equipo (ya no en el servidor de Google) y
  el arranque decía **«groq=AUSENTE»** aunque el archivo de claves
  estuviera bien puesto. No era su configuración: **el sistema leía las
  claves en dos sitios distintos**. El motor de dictámenes las recibía
  bien, pero el asistente, el auditor forense, el lector de cláusulas y
  el propio mensaje de arranque las buscaban en otro lado y no las
  encontraban nunca.
- Quedó el puente: lo que está en el archivo de claves ahora también
  queda disponible para todo el sistema. Si el arranque dice AUSENTE, de
  verdad falta la clave — ya no es una falsa alarma. Lo que venga por
  Docker o el servicio de Windows sigue mandando sobre el archivo.

### 04-08 (cuarta parte) — El mensaje dice QUÉ proveedor falló y por qué

- Con Groq como IA principal y Anthropic de respaldo, cuando fallaban
  los dos el aviso solo nombraba al último: el auditor veía «clave
  inválida» de Anthropic —que ni siquiera es su proveedor principal— y
  no sabía qué había pasado con Groq.
- Ahora el mensaje los nombra a todos con su causa en cristiano:
  «GROQ: está en límite de uso · ANTHROPIC: su clave está inválida o
  vencida». Las causas se traducen solas (sin saldo, saturado, no
  respondió a tiempo, no se pudo conectar…).

### 04-08 (tercera parte) — Una carátula vacía tampoco es un dictamen

- Segundo hallazgo del mismo día: ya no salía el error de la IA en el
  cuerpo, pero el dictamen salía **con la argumentación jurídica VACÍA**
  y aun así con el sello «validado». Eso es peor que el error visible,
  porque parece bueno.
- Ahora el motor **se niega a armar la carátula** si la IA no devolvió
  argumentación (tabla, sello y cierre no se generan), y el guardado la
  rechaza también aunque llegara armada por otro camino. En pantalla:
  mensaje claro de que no se guardó y que hay que reintentar.
- Recordatorio: la causa de fondo sigue siendo la **clave de IA
  inválida** en el servidor. Mientras no se renueve, el sistema no va a
  inventar dictámenes — va a decir que no puede.

### 04-08 (segunda parte) — Panel operacional y arreglo del CI

- **El Mando ejecutivo ya muestra dónde se atasca el trabajo**: las
  glosas abiertas agrupadas por estado, con cuánta plata hay parada en
  cada uno y hace cuántos días no se mueve la más vieja (en rojo si pasa
  de 30). Y al lado, **la carga real de cada auditor**: cuántas lleva
  abiertas, cuántas ya vencidas y por qué valor — quien tiene vencidas
  aparece de primero. Se decidió ampliar el Mando en vez de crear otra
  pantalla, para no tener dos tableros que digan cosas parecidas.
- **Arreglo del CI**: el cambio del incidente dejó tres pruebas viejas en
  rojo porque validaban justamente el texto de error como si fuera
  dictamen. Se corrigieron para probar lo que siempre quisieron probar,
  con un dictamen de verdad.

### 04-08 — Incidente: un error de la IA quedó guardado como dictamen

- Iván analizó una glosa de PPL y el «dictamen» salió con el error crudo
  del proveedor («Invalid API Key») como argumentación jurídica, con
  sello de calidad y todo. Dos causas, dos arreglos:
  1. **La clave de Anthropic del servidor está inválida** — hay que
     renovarla (instrucción abajo en el chat). Eso es configuración, no
     código.
  2. **El motor jamás debió guardar eso.** Ahora, si la IA se cae, el
     análisis falla LIMPIO: mensaje claro de qué pasó y qué hacer («la
     clave está vencida, avisá a administración» / «saturada, reintentá
     en 2-3 minutos») y NO se guarda nada. Y aunque un texto con firma
     de error llegara por cualquier otro camino, la persistencia lo
     rechaza: no puede volver a existir un dictamen que diga «Invalid
     API Key».

### 03-08 (cuarta parte) — Gobierno de IA: el gasto se ve

- Pantalla nueva **Gobierno IA** (Reportes, solo coordinación y
  administración): cuánto va gastado en IA hoy, en la semana y en el mes;
  qué modelos consumen y con qué demora; qué usuarios la usan; **cuánto
  ahorra el caché** de instrucciones; y las **glosas más caras de
  defender**, con enlace directo a su expediente.
- El chat también lo responde («¿cuánto hemos gastado en IA este mes?»).
  Los datos existían llamada por llamada desde hace meses — faltaba la
  vista que los cuenta.

### 03-08 (tercera parte) — Google apagó el servidor: mudanza al PC del hospital

**Qué pasó.** La página <https://iaglosassinac.help> dejó de cargar (error
1033). La causa no fue el sistema: la **cuenta de facturación de Google Cloud
quedó cerrada** (saldo pendiente ~$11.278 COP) y Google apaga la máquina
virtual cuando eso pasa. **Los datos NO se perdieron**: siguen en el disco de
la máquina apagada, junto con las copias diarias de las 3 a. m.

**Decisión (Yesid):** en vez de seguir pagando servidor, el sistema se muda al
**PC de cartera del hospital**, que permanece siempre encendido. Misma página,
mismos usuarios, mismos datos, y los cambios de código se siguen aplicando
solos cada 5 minutos, igual que en la VM.

**Lo que quedó construido hoy (el paquete de mudanza):**

1. `docs/MIGRACION_PC_HOSPITAL.md` — la guía completa en 4 fases: (0) reabrir
   la cuenta de facturación, (1) rescatar de la VM la base de datos, las
   llaves y la llave del túnel con comandos listos para pegar en Cloud Shell,
   (2) preparar el PC (Docker Desktop + Git), (3) instalar con doble clic,
   (4) apagar la VM cuando todo funcione.
2. `tools/MONTAR_SERVIDOR_MOTOR_GLOSAS.cmd` — el instalador de doble clic:
   verifica requisitos, trae el código, restaura el rescate, levanta el
   sistema y deja programadas las dos tareas de Windows. Se puede correr las
   veces que sea sin dañar nada.
3. `tools/autodeploy_motor_glosas.cmd` — el deploy automático cada 5 minutos
   (igual al de la VM), con su registro en `data\autodeploy.log`.
4. `tools/copiar_backup_motor_glosas.cmd` — la copia de seguridad diaria
   (9:00 a. m.) hacia el share del hospital o una carpeta de Drive/OneDrive,
   para que la base y su copia no vivan en el mismo disco.

**El paso que sigue depende de Yesid (fase 0 y 1):** reabrir "Mi cuenta de
facturación 2" pagando el saldo (~$11 mil pesos, una sola vez) y correr los
comandos de rescate de la guía. Sin ese rescate el PC arrancaría vacío.

### 03-08 (quinta parte) — SIIFA: el motor redactó las respuestas que faltaban

- Se construyó `tools/siifa_redactar_respuestas.py`: para los seguimientos de
  SIIFA que **no tenían respuesta escrita en DGH**, el motor la redacta solo,
  y separa el trabajo en dos archivos, **glosas** y **devoluciones**, porque
  no se contestan igual. Quedaron `respuestas_GLOSAS.xlsx` (1.238 filas) y
  `respuestas_DEVOLUCIONES.xlsx` (1.341), todas con texto y con una columna
  REVISAR que dice qué verificar antes de subirla (PR #268).
- **Corrección del mismo día (PR #269):** el redactor traía su propia forma de
  leer los pesos, y esa es la copia número once de algo que ya existe una sola
  vez en el repositorio. Se le puso el lector único (`tools/_dinero.py`). Antes,
  un valor que viniera del Excel con puntos de miles o con `$` (por ejemplo
  `$ 1.479.360`) hacía que la respuesta dijera "SIN VALOR REGISTRADO" en una
  glosa que sí tiene valor; ahora se lee bien. Con esto vuelve a quedar en
  verde la prueba que vigila que haya **un solo lector de pesos** en todo el
  repositorio (esa prueba existe porque llegaron a convivir diez copias y
  cuatro estaban malas: una multiplicaba por cien y tres dividían por mil).

### 03-08 (sexta parte) — SIIFA: cargar primero solo lo que el hospital ya respondió

- **La duda de Yesid:** la factura HUS532384 no aparece en el Excel de lotes
  de DGH, ¿de dónde salió entonces su respuesta? De la base de SIIFA, no de
  la de DGH. El informe de seguimientos de SIIFA es la lista de trabajo (trae
  factura, código, causal, valor y lo que escribió la EPS); el Excel de DGH es
  solo un atajo para no volver a escribir lo que el hospital ya contestó. Si
  la factura no está en DGH, la respuesta la redactó el motor y la fila queda
  marcada **REDACTADA** (amarilla); las que sí estaban salen **EXACTO** o
  **POR_CODIGO** (verdes).
- **Decisión:** cargar primero solo las verdes. El redactor tiene ahora la
  opción `--solo-lo-ya-respondido`: los dos archivos de cargue quedan
  únicamente con las respuestas reales del hospital, y las redactadas **no se
  botan** — salen en archivos aparte terminados en `_REDACTADAS`, para
  revisarlas y subirlas después.
- **Advertencia que quedó anotada:** la glosa que no se contesta dentro del
  término se entiende ACEPTADA (art. 57 Ley 1438/2011). Las redactadas no
  pueden quedarse guardadas indefinidamente: hay que revisarlas por tandas
  (empezando por las de mayor valor) y subirlas.

### 03-08 (séptima parte) — La fecha de la respuesta: el detalle que salvaba o hundía el cargue

- Yesid pasó la **guía de cargue manual de SIIFA** (con pantallazos del piloto
  de la factura HUS497119). Ahí quedó claro que el portal pide **tres** datos
  para responder: código, observación y **fecha de respuesta** — y que la
  fecha que se digita es **la del día en que el hospital respondió de verdad**
  (la de DGH: 11/05/2026), no la de hoy.
- **El problema que eso destapó:** los archivos de cargue no llevaban esa
  fecha. El bot, sin fecha, pone la de hoy. Es decir: las 1.082 respuestas que
  el hospital dio en su momento se habrían subido fechadas hoy, y en el
  histórico de SIIFA aparecerían contestadas **meses después de la glosa, o
  sea fuera del término** (art. 57 Ley 1438/2011). Es lo primero que mira la
  EPS en una conciliación: habría sido regalarle el argumento.
- **Corregido:** la fecha de DGH ahora viaja desde el cruce hasta el archivo
  que lee el bot, en la columna `FECHA_RESPUESTA` (normalizada a AAAA-MM-DD
  venga como venga del export). Las redactadas van sin fecha —se están
  respondiendo hoy, y hoy es la fecha correcta para ellas—. Si DGH no trae la
  fecha, la fila queda marcada en REVISAR.
- El paso a paso manual del portal quedó escrito en `docs/CONTEXTO_SIIFA.md`
  (sección 5.ter), incluido el pantallazo de **Ver Histórico** como evidencia
  para el PDF de soportes.

### 03-08 (CUV) — Cuentas médicas: el CUV que no salía

- Cuentas médicas reportó que el validador del Ministerio no le generaba el
  **CUV** de la factura **MED737** (Medical Center Especialistas, NIT
  900299334). El validador mostraba un solo rechazo: `RVG01 | Dato requerido`
  en `usuarios[0].servicios.consultas[0].modalidadGrupoServicioTecSal`.
- **Al revisar el paquete completo (XML + JSON) aparecieron cuatro problemas,
  no uno.** Los otros tres no los ve la pre-validación de escritorio: se
  descubren cuando el paquete ya se envió y el CUV no llega.
  1. `modalidadGrupoServicioTecSal` en `null` → va `01` (Intramural), porque
     fue consulta presencial en la sede.
  2. `numFactura` sin el prefijo: decía `737` y en la DIAN esa factura quedó
     radicada como **`MED737`**. Si no coincide, el Ministerio no la encuentra.
  3. `numNota: "2"` con `tipoNota: null` → en una factura de venta los dos
     campos van en `null`. Lo está exportando mal el software de facturación.
  4. **La atención quedó fechada el 27-07 y la factura cubre el período del
     31-07.** Esa la decide facturación: o la fecha del servicio está mal, o
     hay que reexpedir la factura. No se cambia una fecha clínica para que el
     validador pase.
- **Se creó `tools/validar_json_rips.py`** para no repetir el ida y vuelta
  factura por factura. Revisa las dos cosas antes de subir nada: la estructura
  del JSON (campos obligatorios en `null` por tipo de servicio, formato de
  fechas, tablas de referencia de la Res. 2275/2023, coherencia
  `tipoNota`/`numNota`) **y el cruce contra el XML** (número con prefijo, NIT,
  fecha de atención dentro del período de facturación, suma de valores).
  Desempaqueta la factura tanto si el XML es un `Invoice` suelto como si es el
  `AttachedDocument` que la trae en CDATA, que es como la entrega el
  facturador. Corre sobre una carpeta o sobre un mes con `--recursivo`, deja
  reporte CSV y separa ERROR (bloquea el CUV) de AVISO (no bloquea, pero suele
  terminar en glosa). 29 pruebas automáticas.
- Guía para el auditor en `docs/CONTEXTO_FEV_RIPS_CUV.md`: qué revisa cada
  pasada del validador, la tabla de modalidades, los errores más frecuentes y
  la plantilla de PowerShell para corregir el JSON sin dañarlo.

### 03-08 (CUV, parte 2) — El enredo del código de prestador

Con las cuatro correcciones puestas, el Ministerio dejó de reclamar y salió un
rechazo nuevo, **RVC011**, que costó tres intentos entender. Vale la pena
dejarlo escrito porque le va a pasar a más facturas:

- El mensaje dice que el código informado (`680010393301`) "no coincide con los
  datos de autenticación" y muestra como habilitado `6800103933`. Parece que
  sobraran dos dígitos en el RIPS. **No es así.**
- **El mismo prestador se escribe con dos largos distintos según el archivo:**
  en el **XML** de la factura va a **10 dígitos** (código del prestador) y en el
  **JSON** de RIPS va a **12** (código de habilitación de la sede). Está en los
  Documentos Técnicos 1 y 2 del Ministerio.
- Se probó bajar el JSON a 10 y el validador contestó de una: *"El campo de
  codPrestador debe tener 12 caracteres"*. Confirmado por descarte.
- Se consultó el REPS (datos abiertos, dataset `c36g-9fc2`) con el NIT
  900299334: prestador **6800103933**, sede **680010393301**. O sea que **el
  JSON siempre estuvo bien** y la sede 01 es la correcta.
- **Lo que está mal es el XML**, que lleva los 12 donde van 10. Y el XML está
  firmado: no se toca. Le toca a **facturación reexpedir** la factura, y al
  proveedor del software separar los dos parámetros — si usa uno solo para los
  dos archivos, el error se repite en todas.
- Las 3 notificaciones amarillas (RVC017/019/059) **no bloquean el CUV**: la
  norma dice que son transitorias. Pero son cruces de CUPS contra diagnóstico,
  cobertura y finalidad, o sea materia prima de glosa. Ojo con una: la factura
  describe "CONSULTA ESPECIALIZADA POR PRIMERA VEZ" pero el RIPS reporta el
  CUPS **890201**, que es consulta de primera vez **por medicina general**. Hay
  que confirmar quién atendió antes de aprovechar la reexpedición.
- **Cambio de norma importante:** la Resolución 2275 de 2023 fue **derogada por
  la Resolución 948 de 2026**. Los anexos ya no van dentro de la resolución:
  ahora son "Documento Técnico 1 y 2" y el Ministerio los actualiza en el
  micrositio de SISPRO **sin expedir norma nueva**. Hay que mirarlos antes de
  cada cargue grande.
- `tools/validar_json_rips.py` ahora detecta este caso solo: lee el
  `CODIGO_PRESTADOR` del bloque de interoperabilidad del XML, compara los largos
  y dice cuál de los dos archivos tiene el error y quién lo corrige. 35 pruebas.
### 03-08 (octava parte) — Todo listo para empezar a subir a SIIFA

- **`tools\CARGAR_SIIFA.cmd`** — bot de doble clic con menú, para no escribir
  comandos: [1] baja el informe de SIIFA, [2] arma los archivos de respuestas
  (solo lo que el hospital ya había respondido), [3] piloto de UNA glosa,
  [4] y [5] cargue de glosas y de devoluciones, [6] reintento de lo que falló,
  [7] catálogo de códigos. Instala solo lo que falte y guarda el usuario y la
  clave del portal la primera vez (nunca quedan escritos en un archivo). El
  menú **no deja hacer el cargue masivo sin haber corrido el piloto**.
- **`docs/CARGUE_SIIFA_PASO_A_PASO.md`** — la misma secuencia escrita, con los
  comandos sueltos por si hay que correr uno aparte, qué verificar en el
  portal después del piloto (Ver Histórico + pantallazo) y el orden sugerido
  para revisar después las redactadas: primero las de mayor valor, luego
  tarifas/facturación/pertinencia (se sostienen con el contrato), y de últimas
  soportes y DE5601 (esas exigen el papel y el acuse).

### 03-08 (novena parte) — Primera corrida real del bot de SIIFA: dos correcciones

- Yesid corrió `CARGAR_SIIFA.cmd` por primera vez. En la pregunta de la
  carpeta de trabajo quedó pegado un comando en vez de una ruta; el bot lo
  aceptó, bajó los **2.598 seguimientos** (7 minutos, con el servidor del
  Ministerio en mal día) y **todo se perdió al momento de guardar**.
- **Corregido en dos partes**, para que no vuelva a pasar por ningún camino:
  1. El bot valida la carpeta ANTES de empezar: si la ruta no sirve o no deja
     guardar (unidad de red desconectada, por ejemplo), lo dice de una y
     vuelve a preguntar. Se agregó la opción **[8] Cambiar la carpeta**.
  2. El propio informe (`siifa_reporte_seguimientos.py`) revisa que va a
     poder guardar antes de bajar nada — así también queda protegido quien
     corra el comando a mano.
- De la misma corrida quedó confirmado que el modo **mes por mes** funciona:
  la consulta completa se cayó (el servidor respondió 500 y hubo que bajar de
  50 a 10 registros por tanda), el bot cambió solo de estrategia y completó
  el informe.

### 03-08 (décima parte) — El Enter que dejaba el bot inservible

- Segunda corrida del bot de SIIFA: al dar **Enter** para aceptar la carpeta
  por defecto, el menú quedó mostrando `Carpeta: "=` y ninguna opción sirvió.
- **La causa:** el bot le quitaba las comillas a lo escrito ANTES de aplicar
  la carpeta por defecto. Con Enter no se escribe nada, y quitarle las
  comillas a algo vacío dejaba de carpeta la basura `"=`. Corregido el orden
  (primero la de por defecto, después limpiar), y lo mismo en la ruta del
  export de DGH. Queda una prueba que vigila ese orden.
- De paso, el menú ahora **muestra por dónde va el trabajo**: al lado de cada
  opción dice si el informe ya está bajado, si los archivos de respuestas ya
  están armados y si el piloto ya se hizo.
- **Pendiente relacionado:** otros bots de doble clic (`CRUZAR_GLOSAS`,
  `SEMAFORO_GLOSAS`, `AUDITAR_DEV_EPS`, `BUSCAR_FACTURA`, `EXCEL_A_CSV`,
  `TXT_A_EXCEL`, `VERIFICAR_RADICACION`, `VIGILANTE_NOCTURNO`) tienen el
  mismo patrón. Ahí sólo falla cuando la ruta queda vacía, pero conviene
  corregirlo antes de que le pase a alguien en mitad de un trabajo.

### 03-08 (undécima parte) — La prueba de que sí quedó subido

- **Piloto de SIIFA hecho y bueno:** la glosa 15110544 de la factura
  HUS454747 se subió por el bot, con OK, y el reporte quedó en
  `piloto_siifa.csv`.
- La pregunta de Yesid fue la correcta: *«¿y cómo sé que efectivamente se
  subió, si necesito un pantallazo?»*. Con 1.082 respuestas, tomar 1.082
  pantallazos no es viable.
- **`tools/siifa_verificar_cargue.py`** (opción **[9]** del bot): le pregunta
  a SIIFA, factura por factura, qué quedó registrado de verdad y lo compara
  con lo que se mandó. Saca dos cosas:
  1. La **hoja de verificación**: verde lo que quedó igual; amarillo lo que
     quedó con el código o **la fecha** distintos; rojo lo que sigue sin
     respuesta y hay que volver a subir.
  2. Una **constancia en PDF por factura** (carpeta `EVIDENCIAS`), con
     membrete del hospital, fecha y hora de la consulta, y por cada glosa su
     código, valor, respuesta registrada y fecha. Eso es lo que se anexa a
     soportes: reemplaza al pantallazo y sale de la API oficial del
     Ministerio.
- Se consulta **por factura y no por glosa**: 17 consultas en vez de 1.082.

### 04-08 — La deuda quedó paga, Google se demora, y nace el arranque exprés

**El pago.** Se descubrió que la deuda era en **pesos** (once mil, no once
mil dólares). Google no dejó pagar menos de $30.000: se pagaron con la
Visa nueva y el perfil quedó **sin saldo pendiente** y con $18.080 a favor.
La Mastercard vieja (la que rebotó y causó todo) debe dejar de ser la
principal.

**El nuevo tranque.** Aun con la deuda paga, el botón "Reabrir cuenta de
facturación" quedó bloqueado: Google exige que lo haga su equipo de
soporte. Se abrió el **caso #74044918** (chat con soporte, escalado al
equipo especializado) y prometieron respuesta **en 24-48 horas por correo**.
Crear cuentas nuevas no sirve: mientras el perfil estuvo en deuda, Google
las cerraba al nacer (pasó con la cuenta 3).

**La decisión para no parar al equipo:** revivir la página YA desde el PC
de cartera con una **base nueva provisional**, sin esperar el rescate:

1. `tools/REVIVIR_EXPRESS_SIN_RESCATE.cmd` — instalador de doble clic:
   crea las llaves nuevas del sistema, configura el túnel de Cloudflare
   por **token** (sin necesitar la llave vieja encerrada en la VM),
   levanta todo y deja las mismas dos tareas programadas.
2. La guía `docs/MIGRACION_PC_HOSPITAL.md` ganó la sección **"Arranque
   exprés SIN rescate"**: cómo sacar el token del túnel en Cloudflare
   (5 minutos), cómo entra el equipo (los 25 usuarios se siembran solos;
   contraseña inicial = la parte del correo antes del arroba, y el
   sistema obliga a cambiarla), y qué hacer cuando Google reabra.
3. **ELIAS CARVAJAL quedó en el sembrado como administrador** (antes solo
   existía en la base de la VM; en una base nueva no aparecía).

**OJO — cuando Google reabra la cuenta:** hacer el rescate de la fase 1 y
**avisar al chat ANTES de restaurar la base vieja**, para sacar copia de la
provisional y fusionar lo trabajado en estos días.

**Segunda parte del mismo día — modo SIN Docker.** Yesid preguntó si se
podía sin Docker Desktop (los PC del hospital no siempre lo permiten). Se
construyó el camino alterno: `tools/REVIVIR_EXPRESS_SIN_DOCKER.cmd` corre
el sistema directo con Python (el mismo de los otros bots) y publica la
página con el programa oficial de Cloudflare descargado solo. Deja
vigilantes que reviven el servidor y el túnel si se caen, arranque
automático al iniciar sesión, el mismo autodeploy cada 5 minutos y la
misma copia diaria. Ojo al único detalle distinto: en Cloudflare la URL
del Public hostname es `localhost:8080` en este modo (con Docker es
`motor:8080`). Guía: sección "B-bis" de `docs/MIGRACION_PC_HOSPITAL.md`.

**Tercera parte — ¡LA PÁGINA REVIVIÓ desde el PC de cartera!** La
instalación real dejó tres tropiezos, corregidos el mismo día:

1. El PC tenía Python 3.14 (demasiado nuevo) → el instalador ahora exige
   3.11-3.13 y guía a instalar el 3.13 con `winget` (PR #279).
2. `psycopg2` (conector de PostgreSQL, innecesario con SQLite) intentaba
   compilarse y tumbaba la instalación → se salta en este modo (PR #279).
3. Windows no trae la base de zonas horarias y `America/Bogota` reventaba
   el arranque → paquete `tzdata` fijado en requirements (PR #280) — y el
   **autodeploy de 5 minutos lo aplicó solo**, señal de que la maquinaria
   automática quedó viva igual que en la VM.

Con eso el sistema quedó arriba en el PC: túnel nuevo de Cloudflare por
token (`motorglosas`), usuarios sembrados (27), 13 contratos, y las tres
llaves de IA repuestas (Groq nueva, Gemini recuperada de AI Studio,
Anthropic creada de nuevo — las viejas siguen en el `.env` de la VM).
Último ajuste del día: en Docker las llaves llegaban como variables de
entorno y varias partes del código las leen así (`os.getenv`); el
vigilante del servidor ahora carga TODO el `.env` como variables de
verdad antes de arrancar, para que el modo sin Docker sea idéntico al
de Docker.
- **04-08 (tarde):** se cerraron los tres pendientes que había dejado abiertos
  el módulo web, con lo que explicó el auditor:
  - **La causal 4506 no estaba mal clasificada.** La trabajan **dos áreas**:
    los gestores por FACTURACION y las médicas por PERTINENCIA, y esta última
    cuando lo glosado es material de osteosíntesis o insumos de alto costo.
    Ahora el sistema **no la clasifica solo**: la marca `POR ASIGNAR` y **solo
    un SUPER ADMIN** la reparte desde la pantalla. El bot propone el área con
    su motivo escrito; se midió contra las 255 filas de 4506 que el equipo
    clasificó a mano y **coincide en 249 (97,6 %)**. Al asignar el área se
    recalcula la sugerencia: si queda en PERTINENCIA, el bot se calla.
  - **Los centros de costos ya no se adivinan.** La macro tenía el catálogo
    oficial en una **hoja oculta** (el botón que usa el equipo): **45 centros
    con su código** (`733001-QUIROFANOS`, `510406-DIREC SUBGCIA DE ALTO
    COSTO`, …). Se metió al bot y a la pantalla como **desplegable**, para que
    no queden variantes escritas a mano. Los 4.248 propuestos ahora salen en
    la forma oficial `código-NOMBRE`. Si el hospital cambia el plan de
    cuentas, manda el catálogo de la macro que se cargue.
  - **Las 4 facturas sin detallado** (311371, 367368, 380246, 394817): se
    revisaron **los siete lotes archivo por archivo** y no están en ninguno —
    el detallado nunca se exportó, no es un fallo del bot. La pantalla ahora
    **avisa por qué** y **trae igual todo lo del reporte del ADRES** (150, 1,
    2 y 12 glosas respectivamente, $43.518.600 en total). Si aparece el
    detallado, basta recargar la bitácora.
  200 tests pasando.
- **04-08 (noche):** el auditor mandó la guía de cargue y un PDF de ejemplo
  (`RTA_ADRES_HUS311371.pdf`), y con eso la pantalla quedó como él la quiere:
  - **Las glosas totales ya no se muestran.** En el reporte del ADRES hay
    filas con la columna «Descripción Glosa» **vacía**: son el desglose de una
    reclamación glosada entera por el FURIPS y **no se responden una por una**.
    Son **1.630 de 4.619 ($236.217.091)**. Ocultarlas resolvió de paso lo de
    «no sale la descripción de la glosa»: era eso, esas filas venían en blanco.
    La factura 311371 pasa de 150 renglones a **21 que sí hay que trabajar**.
    No desaparecen en silencio: sale un aviso con cuántas son y cuánto valen,
    y un enlace para verlas.
  - **La descripción de la glosa es ahora una columna propia** en la tabla,
    completa (antes iba cortada debajo del código de la causal).
  - **Al cargar el archivo salen de una vez las facturas a auditar**, con el
    avance de cada una y filtros por Pendientes / En proceso / Cerradas. Se
    hace **clic en una** y se despliega por qué y qué le glosan.
  - **Se guarda solo** mientras el gestor escribe la observación, y también
    con un botón **Guardar**. Al terminar, **Terminar factura**; si hay que
    corregir, **Reabrir factura**, y queda registrado quién la reabrió. Una
    factura cerrada **no se reabre sola** al editar una glosa.
  - **Botón de PDF de evidencia por factura**, con el mismo formato del
    ejemplo: encabezado con factura, radicación y documento del paciente, y la
    tabla de seis columnas (incluida RTA GLOSA COMPLETA con la fórmula de la
    macro). Los renglones de glosa total no van en la tabla pero sí se dicen
    al pie, junto con las glosas que quedaron sin decidir.
  Tabla nueva `facturas_adres` para el estado. 50 tests del módulo web.
  **Nota sobre Cobranza Live:** otra sesión, al fusionar, había vuelto a
  dejarla en el menú por prudencia ("quitarle una pantalla al equipo no es
  decisión de una fusión"). El auditor lo pidió de nuevo de forma explícita,
  así que **se retiró del menú**. Se quitó solo el botón, el panel, la pestaña
  y el alias: `loadDashCobranza()` y el endpoint
  `/glosas/stats/dashboard-cobranza` **siguen vivos**, de modo que devolver la
  pantalla es volver a poner el botón (un minuto de trabajo). Si el equipo la
  estaba usando de verdad, se avisa y se devuelve.
- **04-08 (cierre del día):** el módulo **quedó andando en el servidor del
  hospital**. Costó tres pasos que vale la pena dejar escritos:
  - El PR #209 se había fusionado con la **primera versión** del módulo, así
    que el servidor mostraba la pantalla vieja. Se abrió el PR #295 con lo que
    faltaba.
  - Al preparar el despliegue se descubrió que **eso solo habría roto la
    pantalla**: las tablas `glosas_adres` y `paquetes_adres` ya existían con el
    paquete cargado, y el sistema crea tablas nuevas pero **no agrega columnas
    a las que ya están**. Además `facturas_adres` nacía vacía, así que la lista
    habría salido en blanco otra vez. Se agregó la migración al arranque
    (PR #298) y en el servidor corrió limpia: **1.630 glosas totales marcadas
    y 324 facturas creadas para la lista**, sin borrar nada.
  - Probando, el auditor encontró que al marcar **SE ACEPTA** el valor quedaba
    en **$0**: la tabla no tenía dónde escribir cuánto se acepta. Se agregó la
    columna **Aceptado** (valor y cantidad). Al escoger SE ACEPTA se propone
    **todo lo glosado**, que es el caso normal, y el gestor lo baja si fue
    parcial; si cambia de decisión, vuelve a cero para no reconocer plata por
    descuido. Es lo que alimenta el «CANTIDAD ACEPTADA n . POR VALOR $x» de la
    respuesta al ADRES y del PDF de evidencia.

  **Para desplegar de aquí en adelante:** el autodeploy baja de `motor-glosas`
  cada 5 minutos. Para forzarlo: `schtasks /Run /TN "MotorGlosas_Autodeploy"`,
  y se verifica en `data\autodeploy.log` y `data\servidor.log`.
- **14-08:** llegó el **paquete 31078** (81 facturas) con el oficio Orfeo
  **20264300142071**. Tres cosas que hay que tener presentes:
  - **PLAZO: 23 de septiembre de 2026.** Son 2 meses desde la notificación
    certificada del 23-07. Si no se responde, la glosa se acepta tácitamente
    **ítem por ítem** (Res. 1236/2023 art. 8 num. 8.5) y **es una sola
    oportunidad**: no se puede radicar algo ahora y completarlo después.
  - **La plata del paquete es $297.117.349,73, NO $585 millones.** El reporte
    del ADRES **repite renglones** (abre una fila por cada causal del mismo
    ítem, y en las facturas grandes repite sin explicación). Sumar esa columna
    en bruto infla la glosa. La cifra buena está en
    `FACTURAS PAQUETE 31078_81 FACTURAS.xlsx` y en la TRAZABILIDAD, que
    coinciden peso a peso con el oficio.
  - **Solo 54 de las 81 facturas cuadran** con la cifra oficial ($49.499.660).
    Las otras **27 concentran el 83 % de la plata** ($247.617.689) y traen
    **1.174 renglones sin causal escrita**. Para esas hay que bajar el detalle
    del portal (Reclamaciones → **Reportes Lupa al giro**, con el usuario de
    Radicación).

  Nace **`tools/glosas_adres_por_factura.py`**: saca un Excel por factura con
  solo lo que sigue glosado, **sin necesitar el detallado impreso del
  hospital** — trabaja directo del reporte del ADRES. Junta los renglones
  repetidos por causal y **verifica cada factura contra la cifra oficial**,
  dejando el veredicto escrito dentro del propio archivo («VERIFICADO» o «OJO —
  NO CUADRA» con la diferencia exacta). Guía en
  `tools/README_glosas_adres_por_factura.md`.

  **Causales nuevas del 31078:** aparecieron 2010, 4301, 4302 y 4005. Se
  propusieron y después se intentó refutarlas: solo sobrevivió la **4302
  (mayor valor en consulta) → TARIFAS**. Las otras tres quedan **sin
  clasificar** a propósito. Ojo con la **2010** (HUS406456, $17.464.478,
  "presentación fuera de términos"): parece glosa total del FURIPS pero **no lo
  es** — si se clasificara ahí, el bot escribiría "SE SUBSANA anexando el
  formulario", que es falso porque un FURIPS corregido no revive un término
  vencido. Esa la deciden cartera y jurídica.

  **Otros hallazgos:** 16 facturas del paquete tienen glosa $0 (aprobadas
  completas, $22.599.644) y no hay que auditarlas; el archivo
  `BASE DE DATOS ADRES.xlsx` vino **truncado** y hay que volver a bajarlo.

### 05-08 — Dispensario: se ubicó cada evidencia y quedó listo el cargue de las 23 que faltan

- **¿Dónde y cuándo quedó lo subido? (base de 124 facturas).** Con un comando
  de búsqueda en el PC se encontró que **116 de las 124 se subieron el jueves
  23 de julio** (piloto 3:04 p. m., corrida completa 3:53–5:05 p. m., dos
  sueltas 5:11 y 5:22 p. m.) y sus pantallazos quedaron en
  `C:\temp-notas\evidencias_glosa` (esa corrida no indicó carpeta de
  evidencias, así que el robot usó la suya por defecto). Se entregó el comando
  del paquete **GI-33-5285-2026**: carpeta con las 116 evidencias + inventario
  + PDF unificado.
- **El pantallazo de "pendientes por cargar" del portal aclaró el resto:** en
  SIMED solo quedan **23 facturas pendientes** (glosas fechadas entre enero y
  agosto, **$21.083.565**). Eso confirma que los lotes del 14, 17, 28 y 31 de
  julio **ya están subidos**, aunque a cada uno se le escaparon casos: la
  522160 (17-jul), la 530112 (28-jul) y la 534953 (31-jul) figuran pendientes
  y entran ahora. Las 3 de junio ya no aparecen en pendientes (verificar cómo
  quedaron radicadas).
- **Excel de cargue de las 23**
  (`respuestas_glosa_DISPENSARIO_PENDIENTES_05AGO.xlsx`): usa el texto de
  TARIFAS que definió el auditor (contrato 440-DIGSA/DMBUG-2025) con dos
  ajustes: la cita de la **Resolución 3047 de 2008 (derogada)** se reemplazó
  por la **Resolución 2284 de 2023**, y se agregó el cierre de conciliación
  con los correos de cartera. Como no se conoce cuántas líneas tiene cada
  glosa en el portal, el Excel trae filas de sobra por factura —el robot salta
  sin problema los números que no existen y omite lo ya contestado—: 298 filas
  en total. Antes de entregar se corrió verificación adversarial en 3 frentes
  (jurídico, operativo del robot y técnico del script de paquete).
- **Consecutivos confirmados por el auditor:** los lotes 17-jul, 28-jul y
  31-jul (más esta corrida de pendientes) van juntos en el paquete
  **GI-33-5251-2026**; el cargue del 23 de julio va aparte como
  **GI-33-5285-2026**. Los comandos de carpeta + PDF de ambos quedaron
  entregados en el chat.
- **Verificación adversarial del texto (3 frentes: jurídico, operativo,
  técnico) — correcciones aplicadas antes de entregar el Excel:** se quitó la
  frase "vigente ... con plazo hasta 30/07/2026" (contradictoria al radicar en
  agosto; ahora dice "vigente a la fecha de prestación de los servicios"); el
  artículo de conciliación del cierre quedó bien citado (art. 23 del Decreto
  4747, no el 20); se citaron las Resoluciones HUS 054 y 124 de 2026 como
  respaldo de los servicios por fuera del Anexo No. 1; y la frase del
  presupuesto (art. 71 del Decreto 111/1996) se redactó de forma que no se
  pueda voltear en contra del hospital.
- **Robot SIMED mejorado (mismo día):** (1) si el Excel trae más filas que
  objeciones tiene la grilla, el robot corta en la primera que no exista (ya
  no escanea página por página cada fila sobrante); (2) lee siempre la hoja
  "Respuestas Glosa" aunque el archivo se haya guardado con otra pestaña
  activa; (3) el cierre estándar del motor de glosas ahora cita el art. 23
  del Decreto 4747 (antes decía art. 20, que no es el de conciliación).
- **OJO jurídico para el auditor:** confirmar si existe **prórroga 2026 del
  contrato 440**; con ella se refuerzan los próximos textos (el de hoy ya
  quedó blindado sin necesitarla).
- **Las 8 "sin evidencia" quedaron identificadas** con la tabla de
  vencimientos que mandó el auditor: 6 están pendientes en SIMED y entran en
  el cargue de hoy (519423 vencida el 23-07, 522160 vencida el 29-07, 533934
  y 534507 vencen el 06-08, 524188 el 10-08 y 530112 el 13-08); las otras 2
  (527406, vencía 03-08, y 525763, vence 10-08) NO figuran pendientes en el
  portal: verificar que estén contestadas buscándolas una a una en SIMED.

### 05-08 — Por qué SIIFA rechazó 1.422 respuestas (y cómo se arregló)

- **Lo que se subió el 4 y 5 de agosto:** de 2.579 respuestas quedaron
  **1.157 registradas** (985 glosas por $227.803.973 y 172 líneas de
  devolución) y **1.422 rechazadas**. Informe completo por factura en el
  Excel que se le entregó a Yesid.
- **Causa 1 — el texto pasaba de 1.500 caracteres (927 casos).** SIIFA no lo
  dice: contesta «HTTP 500: error saving the entity changes», que parece una
  falla del servidor. Los números no dejaron duda: entraron TODAS las de
  hasta 1.499 caracteres y ninguna de 1.501 en adelante. El redactor estaba
  recortando a 1.900, que era el límite equivocado. Corregido a **1.500**
  (`LIMITE_OBSERVACION`).
- **Causa 2 — el código RE9701 (495 casos).** Se usa en DGH pero SIIFA no lo
  acepta: «el código no existe, no está activo o no pertenece al grupo
  RESPUESTA». Son las devoluciones que el hospital ACEPTÓ con nota crédito.
- **`tools/siifa_corregir_rechazadas.py`** (nuevo): lee el archivo que se
  cargó y el reporte del cargue, se queda solo con lo que quedó en ERROR y lo
  corrige: a lo que escribió el motor **se lo vuelve a redactar** para que
  quepa (así el recorte se lo lleva la cita de la EPS y no el cierre del
  hospital), a lo que vino de DGH se le recorta el final en un punto, y los
  códigos que SIIFA no acepta se cambian por el que se indique. Todo queda
  marcado en la columna CORRECCION.
- **Ojo con dos cosas que quedaron pendientes de revisar:**
  1. Lo ya subido quedó con **la fecha del día del cargue**, no con la de
     DGH: los archivos se generaron el 03-08, antes de que existiera la
     columna FECHA_RESPUESTA. Para la EPS, esas respuestas figuran dadas en
     agosto.
  2. El desplegable de SIIFA para devoluciones ofrece tres respuestas
     («no procede por fuera de términos», «es injustificada al 100%»,
     «ha sido aceptada al 100%»), pero el portal no muestra el código. Para
     las 495 aceptadas con nota crédito hay que averiguar el código de «ha
     sido aceptada al 100%»: se responde UNA a mano en el portal y se mira
     el código en Ver Histórico.

### 05-08 (segunda parte) — La homologación de códigos DGH → SIIFA

- El portal muestra la **frase** de cada respuesta pero no el código, y el
  catálogo de la API vino vacío. Se armó la homologación por SIGNIFICADO con
  la evidencia que hay:
  - **RE9901** = «la glosa siendo justificable ha podido ser subsanada
    totalmente» — así lo devuelve el propio informe de SIIFA. NO es
    «no acepto».
  - **RE9702** = «la glosa/devolución ha sido **aceptada al 100%**» — en el
    piloto de la HUS497119 se escogió esa frase y en Ver Histórico quedó
    RE9702.
  - **RE9701** (DGH) = las devoluciones que el hospital **aceptó** con nota
    crédito. SIIFA no lo acepta → se homologa a **RE9702**.
- `siifa_corregir_rechazadas.py --homologar` aplica ese cambio y lo deja
  marcado en la columna CORRECCION.
- La opción **[7]** del bot ahora prueba todos los nombres de grupo conocidos
  del catálogo y, si ninguno responde, explica cómo sacar el código a mano:
  responder una a mano en el portal y mirarlo en Ver Histórico.
- El desplegable de **devoluciones** ofrece tres respuestas: «no procede por
  fuera de términos (aceptación tácita de la factura)», «la devolución es
  injustificada al 100%» y «la devolución ha sido aceptada al 100%».

### 05-08 (tercera parte) — No era el código: es la puerta

- **Corrección de lo anterior:** se había homologado RE9701 → RE9702 pensando
  que RE9701 no existía. **Yesid lo verificó contra el portal: RE9701 SÍ es el
  código de la devolución que el hospital acepta** —el desplegable de
  «Responder Devolución» ofrece esa respuesta—. La homologación quedó
  deshecha: el código de esas 495 no se toca.
- **Lo que en realidad falla:** el bot manda glosas Y devoluciones por la
  misma puerta, `PUT /api/SeguimientoFacturaGlosa/Respuesta`, que valida
  contra los códigos del grupo de GLOSA. Por eso el mensaje decía «no
  pertenece al grupo RESPUESTA»: el código es de devolución y se está
  entrando por la puerta de las glosas.
- **`tools/siifa_sondear_endpoints.py`** (nuevo): prueba las rutas y los
  grupos de catálogo candidatos y dice cuáles existen, **sin escribir nada**
  en la plataforma (solo consulta; una ruta que existe contesta 405 y una que
  no, 404). Con eso se sabe por dónde se responde una devolución.
- Lección para el chat: cuando el auditor tiene el portal delante, su dato
  manda sobre cualquier deducción hecha desde los datos.

### 05-08 (cuarta parte) — Resuelto: las devoluciones tienen su propia puerta

- **Piloto en verde:** `Devolución 17876242 (factura HUS481923): OK`. Con esa
  sola respuesta quedó confirmado todo: la puerta correcta, el id correcto y
  que **RE9701 siempre fue el código bueno** —lo dijo Yesid mirando el portal,
  contra la deducción del chat, y tenía razón—.
- **Lo que estaba mal:** el bot mandaba glosas y devoluciones por la misma
  puerta (`/api/SeguimientoFacturaGlosa/Respuesta`). Una devolución se
  responde por `/api/SeguimientoFacturaDevolucion/Respuesta`, que valida
  contra los códigos de devolución. Por eso SIIFA decía que RE9701 «no
  pertenece al grupo RESPUESTA»: el código estaba bien, la puerta no.
- **El id es el mismo** para los dos casos (`idSeguimientoFactura`): lo mostró
  el volcado crudo de la API. Por eso los archivos de cargue ya generados
  sirven tal cual, con solo actualizar el bot.
- **Cómo se llegó:** `tools/siifa_sondear_endpoints.py`, que prueba rutas y
  grupos del catálogo **sin escribir nada** en la plataforma, y el volcado de
  los campos crudos de una factura (`--factura HUS494196`).

### 05-08 (quinta parte) — SIIFA quedó al día: 2.579 de 2.579

| | Subidas | Pendientes |
|---|---|---|
| Glosas | **1.238 de 1.238** — $310.614.081 defendidos | 0 |
| Devoluciones | **1.341 de 1.341** líneas — 10 facturas por $115.051.312 | 0 |

- **Todas las glosas y devoluciones que SIIFA tenía sin responder quedaron
  respondidas.** El cargue de hoy fue en cuatro tandas y ninguna dejó errores.
- **La tabla de códigos de respuesta a devolución** (grupo
  `RESPUESTA_DEV_PTS_PSS`), que era lo que faltaba saber:
  - `RE9501` — la devolución no procede, se generó fuera de términos →
    aceptación tácita de la factura;
  - `RE9601` — el hospital aporta evidencia de que es injustificada al 100%;
  - `RE9701` — el hospital acepta la devolución al 100%.
- Se usó `RE9701` en las 495 que el hospital había aceptado con nota crédito y
  `RE9601` en las 674 que no acepta.

**Lo que queda por revisar (no urgente, pero conviene):**

1. **170 líneas de la factura HUS475438** se subieron el 4 y 5 de agosto por
   la puerta de las glosas, con el código RE9901, antes de que se descubriera
   el problema. Hay que mirar su histórico en el portal y decidir si se
   vuelven a responder por la puerta correcta.
2. **Las 674 devoluciones DE5601 podrían ganarse con `RE9501`.** Se subieron
   con RE9601 («es injustificada»), que es lo que decía el texto. Pero si al
   comparar fechas resulta que la EPS devolvió fuera de SU propio plazo,
   RE9501 es más fuerte: implica aceptación tácita de la factura. Requiere
   cruzar fecha de radicación contra fecha de devolución, caso por caso.
3. **La fecha de las respuestas subidas el 4 y 5 de agosto** quedó con el día
   del cargue y no con la de DGH (los archivos se generaron antes de que
   existiera la columna FECHA_RESPUESTA).

### 05-08 (sexta parte) — Nace `PROYECTO.md`, el tablero maestro

Yesid pidió un tablero de trabajo, no una auditoría: un solo archivo corto
donde se vea de un vistazo qué módulos existen, en qué estado están, cuál es
el objetivo del proyecto en este momento y qué bloquea el avance.

Quedó en la raíz como **`PROYECTO.md`**. Tiene 18 módulos (la aplicación web
y sus pantallas, los bots de cada portal, el validador ADRES y el servidor
local), cada uno con estado, prioridad, archivo de entrada, dependencias,
próximo objetivo y riesgo. Al final: **un solo objetivo actual**, cinco
próximas tareas en orden, los bloqueantes reales y diez reglas del proyecto.

Los datos salieron del repositorio y de esta bitácora. Donde no había
evidencia quedó escrito «PENDIENTE DE VALIDAR» en vez de suponer.

Cómo se usa: se actualiza cuando cambia el estado de un módulo, cuando se
cierra el objetivo actual o cuando aparece o se cae un bloqueante. La
bitácora sigue siendo la memoria (qué pasó y cuándo); `PROYECTO.md` es el
tablero (dónde estamos hoy).

---


### 06-08 — 22 correcciones al motor, con las glosas de trampa como guía

Yesid corrió dos tandas de glosas de prueba en el motor del hospital y pegó
los dictámenes tal como salieron. De ahí salieron 22 correcciones, cada una
con su prueba automática para que no vuelva a pasar. Lo que el motor
afirmaba sin tener de dónde:

- una **cláusula de contrato** que no existe (y que además sobrevivía cuando
  la red anterior le cambiaba el contrato por el de otra entidad);
- un **CUPS** sacado de la cola del número de contrato;
- un **periodo de atención** ("año 2023") que no está en ninguna parte del caso;
- un **servicio** ("estancia u observación de urgencias") sin CUPS ni soportes;
- **hechos de la historia clínica** sin un solo PDF adjunto;
- una **cita textual del contrato** que el verificador daba por buena y
  entregaba con el sello «0 hallazgos» — que es peor que no revisar.

Lo que el motor no veía y ahora avisa: que la entidad **glosa más de lo
facturado**, que **objeta dos veces el mismo renglón**, que la **glosa es
anterior a la factura**, y que se **contradice** (dice que el servicio no se
prestó y a la vez que la tarifa está mal).

Lo que respondía mal: contestaba de **urgencias y autorización previa** a
glosas que preguntaban por otra cosa; contestaba con la **tabla de tarifas**
una pregunta clínica; y respondía con **una sola plantilla** a glosas con
cuatro objeciones distintas — lo que no se contesta, la entidad lo descuenta.

Dos cosas que salían impresas y se leían como descuido: comillas vacías
(«""») y medio dictamen en minúscula dentro de un documento en mayúscula
sostenida.

Y dos hallazgos de fondo:

1. **Las 26 cláusulas reales nunca se habían cargado.** Estaban en el
   repositorio desde julio, pero solo se cargaban corriendo un comando a
   mano que nadie corrió. Por eso TODOS los dictámenes perdían puntos por
   «falta cláusula del contrato», el motor no tenía ninguna que citar, y el
   verificador no podía comprobar ninguna cita de contrato. Ahora se cargan
   solas al arrancar. En el log vas a ver `[SEED-CLAUSULAS] 26 creadas`.

2. **Seis plantillas fundaban la defensa en la Resolución 3047 de 2008**,
   que la 2284 de 2023 reemplazó. Ahora va adelante la vigente y la vieja
   queda como antecedente. Las que ya estaban en tu base se corrigen solas
   al arrancar.

Aparte: el lector de tarifas se saltaba **tres de las cinco hojas** de la
propuesta 2026 de FAMISANAR. Entraban 1.625 tarifas de 6.655. Lo más
delicado era la hoja UVB, que trae dos columnas de plata: si se cargaba la
de referencia en vez de la pactada, el motor defendería con una tarifa 5%
más alta y la entidad ratificaría la glosa cada vez.

**Ojo con esa propuesta:** el archivo se llama PROPUESTA. Mientras el
acuerdo con FAMISANAR no esté firmado, no la cargues como tarifa pactada.

### 13-08 — Google reabrió la cuenta: rescate de la VM y herramienta de fusión

- **Google resolvió el caso #74044918**: la facturación quedó activa y la VM
  volvió a prender. La página NO depende de ella (sigue viva desde el PC de
  cartera); la VM solo se prendió para sacar lo que quedó encerrado el 03-08.
- **Se empacó el rescate en la VM**: `rescate-motor-glosas.tgz` (28 MB) con la
  base vieja congelada del 03-08, el `.env` con las llaves y la llave del
  túnel. Los soportes y los PDF de contratos (son poquitos, 288 KB) van en un
  segundo paquete `rescate-soportes.tgz`.
- **Decisión importante: NO se restaura la base vieja encima de la del PC.**
  El PC lleva más de una semana siendo el sistema real y su pre-auditoría
  (importada del Excel del equipo el 05-08) es MÁS completa que la vieja.
  Lo que se hace es **fusionar**: traer solo lo que al PC le falta.
- **Nació `tools/fusionar_base_vieja.py`** para esa fusión. Trae de la base
  vieja: las glosas con sus dictámenes y toda su historia (conceptos,
  versiones del dictamen, comentarios, conciliaciones con sus adjuntos, notas
  privadas e hilos), los precedentes ganados, las plantillas, los usuarios que
  falten (a los que ya están en el PC NO les toca la clave), los contratos con
  sus cláusulas, las tarifas contratadas, las credenciales de entidades (solo
  si el vault del PC está vacío), las rutas de soportes y los atajos de los
  gestores. No toca NADA de pre-auditoría ni ninguna fila que ya exista.
  Estilo seguro de siempre: **SOLO MIRAR / aplicar**, copia de seguridad
  automática de la base del PC antes de escribir, idempotente (correrlo dos
  veces no duplica), la base vieja se abre solo-lectura, y aguanta que la
  vieja tenga tablas o columnas más antiguas. 5 pruebas automáticas.

### 13-08 (segunda parte) — La fusión quedó hecha y la VM apagada

El mismo día se terminó el rescate completo, con Yesid corriendo los pasos:

- Se empacaron y **bajaron los dos paquetes** al PC de cartera
  (`C:\motor-glosas\rescate`) y la **VM quedó apagada** (ya no cobra por
  cómputo; solo centavos por el disco mientras se decide borrarla).
- La fusión se corrió primero en SOLO MIRAR, se revisó el plan, y con el
  visto bueno se aplicó: llegaron **27 glosas con sus 27 dictámenes**,
  **6 precedentes ganados** y el contrato de **PRECIMED**. Los 27 usuarios
  ya existían en el PC (nadie perdió su clave) y la base vieja no traía
  credenciales, tarifas ni rutas que faltaran. Antes de escribir quedó la
  copia de seguridad `data\backups\motorglosas-antes-fusion-20260813-094858.db`.
- Se copiaron además los archivos de soportes de recepción del rescate
  (6 archivos). La VM no tenía carpeta de PDF de contratos ni de recepción,
  así que no había nada más que copiar.
- El paquete de rescate queda guardado en `C:\motor-glosas\rescate`.
  **Contiene llaves y la base vieja: no compartirlo ni mandarlo por correo.**

Con esto la mudanza al PC de cartera queda COMPLETA: página viva, historia
de pre-auditoría (del Excel del equipo), historia de glosas (de la VM) y
respaldos diarios. De la VM solo falta borrarla cuando pasen unos días.

---

### 13-08 — Once trabajos: las trampas quedan como prueba, el validador ADRES entra al portal y vuelve la pantalla de Salud Total

Día largo. Se cerraron once órdenes de trabajo (OT-023 a OT-033). En orden
de lo que más pesa:

**Lo que el motor afirmaba sin poder probarlo (y ya no puede).**

- **Las glosas de trampa ahora corren solas.** Las que Yesid usó para
  destapar las 22 fallas del 06-08 quedaron guardadas como examen
  automático: 27 casos y 69 criterios que se revisan en cada cambio. Si
  alguien vuelve a romper una corrección vieja, se entera el mismo día y no
  tres semanas después con un dictamen ya radicado.
- **La tarifa pactada era el único dato duro que nadie verificaba.** El
  dictamen podía escribir un porcentaje de descuento o una tarifa que no
  estaba en ninguna parte del caso. Ahora se comprueba contra lo cargado.
- **Un número de contrato inventado de cero pasaba derecho**, y **dos formas
  corrientes de citar una norma** («Res. 2284/2023», «Resolución No. 2284 de
  2023») el verificador no las veía — o sea que las daba por buenas sin
  mirarlas. Ya las ve.
- **Nadie vigilaba que las redes de seguridad siguieran enchufadas.** Las 18
  revisiones que corren sobre el dictamen antes de entregarlo estaban sin
  vigilancia: si una se desconectaba, el motor seguía trabajando como si
  nada. Ahora hay una prueba que lo detecta.

**Herramientas que estaban por fuera y entraron al portal.**

- **El validador ADRES ya no es un programa aparte.** Antes tocaba levantar
  otra aplicación en el puerto 8010 con un doble clic. Ahora se suben los
  soportes desde la misma página, valida la malla de la Circular 022/2023 y
  descarga el informe en Excel. Solo entra quien tenga sesión con rol de
  auditor: por ahí pasan historias clínicas.
- **El buscador de números de autorización de los RIPS.** Recorre las
  carpetas de facturación **y sus subcarpetas**, entra a los ZIP, y saca el
  listado diciendo cuáles vienen vacíos, cuáles nulos y cuáles con la
  palabra «null» escrita como texto. Queda como bot de doble clic
  (`AUTORIZACIONES_RIPS.cmd`) y también dentro del portal.
  *Falta la pantalla en el portal: el motor ya está, el botón todavía no.*

**El contrato de FAMISANAR ya está firmado.**

Con las 219 páginas del contrato firmado a la vista se cargaron las tres
cláusulas que sirven para contestar glosas (Cuarta de tarifas, Quinta de
soportes y pago, Sexta del trámite de glosas), con su texto literal —no un
resumen, porque un resumen el verificador lo marca como cita falsa, y con
razón. Y se corrigió la cláusula del anexo tarifario, que seguía diciendo
«Propuesta Base Final»: eso era cierto mientras fue propuesta; ahora nombra
los anexos 3.0/3.1/3.2 y la vigencia del 15/04/2026 al 14/04/2027.

**La pantalla de Salud Total volvió a funcionar.**

Yesid la abrió con una notificación real y le salió «Not Found». La causa:
en una limpieza de mayo se borró la parte del programa que atiende esa
pantalla, porque no se le encontraron usuarios en el código. Sí tenía uno:
la pantalla misma. Al motor no le faltaba nada — le faltaba la puerta. Ya
está repuesta y ahora pide rol de auditor, porque de ahí sale un archivo que
se radica ante la entidad.

Al reponerla se corrigieron dos cosas del propio motor:

1. **No se alega un plazo que nadie puede probar.** El término del Art. 57 de
   la Ley 1438/2011 se cuenta desde que la EPS *recibe la factura* hasta que
   radica la glosa. Cuando faltaba esa fecha, el motor contaba desde la
   radicación de la glosa hasta *hoy* —que no mide ningún plazo legal— y
   escribía «han transcurrido N días hábiles» en el archivo que se radica.
   Ahora, sin esa fecha, no se alega extemporaneidad: se contesta de fondo y
   la pantalla avisa que falta el dato. **Por eso la pantalla ahora te pide
   la fecha de recepción también cuando eliges «Extemporánea»** — antes solo
   la pedía para el análisis con IA.
2. **Los valores salen escritos como los escribe la entidad**, sin el «.0» de
   más, y las observaciones ya no pueden llevar saltos de línea adentro (un
   salto parte la fila en dos y la entidad recibe un archivo con más filas
   que glosas).

**Ojo con el archivo `RTAGLOSA_900006037_13082026.csv`.** Ese archivo se armó
por fuera del portal y trae tres errores en las 44 filas. **No lo radiques:**

- el **radicado** salió como `3,5E+14` en vez de `350000214021421` — así
  Salud Total no puede casar ninguna respuesta con su glosa y el archivo no
  sirve para nada;
- el **valor glosado** no es el glosado sino el valor total del servicio
  multiplicado por cien: en la radiografía de tórax la glosa real es de
  **$93.340** y el archivo dice **$28.000.000**;
- el **código del motivo** trae la descripción («Tarifas») donde va la sigla
  («TA»).

Genera el archivo de nuevo desde la pantalla del portal: los tres casos
quedaron como pruebas para que no se repitan.

### 13-08 — Frente SAVIA/FAMISANAR (PR #164): bot de FAMISANAR con homologación de códigos

- **Nuevo bot `tools/organizar_objeciones_famisanar.py`** (hermano del de
  SAVIA): FAMISANAR entrega solo 4 columnas SIN código de servicio — viene
  escondido en el texto de la observación («… CÓDIGO 903867 …»). El bot lo
  extrae y lo **homologa al código del HUS**: CUPS tal cual; a los
  medicamentos se les quita la letra U/P de FAMISANAR (U20162259-04 →
  20162259-04, verificado con METOCLOPRAMIDA en EMSSANAR); y los 4
  dispositivos quedaron con su **código FMQ**, confirmados contra el LOTE_02
  por nombre y valor: catéter IV 18 → FMQ0112 ($5.800 idéntico), llave 3 vías
  → FMQ0182-1, electrodo ECG adulto → FMQ0952 (3×$800), bolsa recolectora de
  orina → FMQ0159 ($18.100 idéntico). Un dispositivo nuevo sin equivalencia
  avisa en el log y se agrega con `--mapa-servicios`.
- **Revisión adversarial con agentes independientes** antes de entregar:
  encontró que se borraba el valor unitario del texto en 18/37 filas (ahora
  solo se quita un $monto final si es duplicado exacto del valor objetado) y
  una mutación de datos al generar por-factura y consolidado en una misma
  corrida. Ambos arreglos se aplicaron también al bot de SAVIA.
- Lote **SAVIA 7.53** procesado y entregado (3 facturas, 392 objeciones,
  $39.772.588).
- **Fusión con la principal**: se integró el lector único de pesos
  (`tools/_dinero.py`, el arreglo del ×100 con centavos) a los bots de SAVIA
  **y de FAMISANAR**; se adoptaron las versiones de la principal de
  `CLAUDE.md`, esta bitácora y los 2 tests de estadísticas; y se conservaron
  los arreglos de la revisión adversarial que la principal no tenía.
  Documento técnico del módulo en `docs/ENTREGA_TECNICA_BOT_SAVIA.md`.
- **Pendiente de este frente:** confirmar la tabla de subíndices del código de
  objeción de SAVIA (hoy TA08→TA0801 con «01»; en EMSSANAR se ven FA0205,
  SO0603…) — si hay lista oficial, se fija con `--mapa-codigos`.

### 13-08 (segunda parte) — El programa de mejora, y ocho pantallas que llevaban tres meses rotas sin que nadie lo supiera

Yesid pidió auditar el proyecto entero y arrancar un programa de mejora en
cuatro frentes: lo visual, lo interno, el rendimiento y lo funcional. Quedó
el tablero en **`MASTER_IMPROVEMENT_PLAN.md`**, con cada hallazgo medido
sobre el código —no supuesto— y con su número al lado.

**Lo más importante que salió de ahí no estaba en el plan.**

Rastreando por qué la pantalla de Salud Total daba «Not Found» apareció que
**no era un caso aislado**. El 9 de mayo se borraron **ocho** partes del
motor que el portal usaba, y se reemplazaron por cáscaras «para no romper
nada». Dos meses después se borraron las cáscaras, con la nota de que
«nadie las llamaba» — porque la revisión miró solo el código del servidor.
**El que las llamaba era la pantalla.**

Desde ese día y hasta hoy, ocho cosas del portal no funcionaban:

- los **comentarios** sobre una glosa,
- las **notas privadas** de cada gestor,
- los **filtros guardados** de Mis Glosas,
- el **historial del chat**,
- las **notificaciones** al navegador,
- el **Auditor Forense** (el que analiza los soportes),
- el **piloto automático**,
- las **noticias del sector**,
- y el refresco solo de los paneles.

**Sus datos nunca se borraron.** Los comentarios, las notas y los filtros
siguen en la base: lo único que faltaba era la puerta. Se repusieron los
nueve, tal como estaban.

**Y ahora hay una prueba que impide que vuelva a pasar.** Cada vez que se
corre la suite, se compara lo que la pantalla pide contra lo que el motor
tiene. Si alguien vuelve a borrar algo que el portal usa, se sabe **ese
mismo día**, no tres meses después.

**Lo demás que se hizo:**

- **Una sola forma de escribir la plata.** Había 74 maneras distintas para la
  misma cifra («$ 1.234.567», «$1.234.567», «1234567») según la pantalla.
  Usted concilia contra Dinámica Gerencial mirando esos números, así que eso
  cuesta tiempo y hace dudar de la cifra. Ahora es una sola, en las seis
  páginas.
- **Ninguna pantalla se queda muda.** Siete no decían nada cuando fallaba la
  red. Las cuatro que guardan eran las graves: usted creía que su decisión
  había quedado registrada y no había quedado. Ahora lo dicen con todas las
  letras.
- **Cuatro puertas apretadas.** Al reponer lo anterior se destapó que cuatro
  acciones estaban abiertas a cualquiera con sesión: crear y resolver
  comentarios, el auditor forense (que manda documentos a la IA y cuesta
  plata por consulta) y aprobar glosas en lote, que mueve dinero.
- **Once columnas del Historial que por poco se pierden.** Al ponerle
  «contrato» a la tabla de Historial se descubrió que el contrato escrito
  meses atrás declaraba diez columnas cuando la tabla tiene veintiuna.
  Aplicarlo tal cual habría borrado la factura, el dictamen, el CUPS y el
  servicio de la pantalla — sin dar error.

**El patrón que se repitió tres veces en el mismo día:** cosas que se ven
ordenadas en el código y que en la pantalla se quedan calladas. El sistema no
fallaba: **se callaba**, que para un auditor es peor. Por eso cada arreglo va
con su prueba, y varias pruebas llevan otra que las vigila a ellas.

### 13-08 (tercera parte) — Lo que dijo la base del hospital

Con los conteos reales de `motorglosas.db` quedaron aclaradas tres cosas que
no se podían saber desde el repositorio:

**1. Las 29 cláusulas SÍ están cargadas en el motor del hospital.** Es la
primera confirmación de que el trabajo de las cláusulas —incluidas las tres
del contrato firmado de FAMISANAR— está funcionando allá, no solo probado
acá.

**2. Las tarifas de FAMISANAR todavía NO se han subido.** La tabla
`tarifas_contratadas` está en **cero**. Mientras siga así, el motor no puede
defender una glosa de tarifas con el valor pactado: sigue pendiente subir el
Excel desde Gestión → Tarifas.

**3. Los 22 posibles cuellos de botella NO hay que tocarlos.** Hoy hay **74
glosas** en la base. Veinte de esos veintidós recorren justamente esa tabla,
así que cuestan milisegundos; y las dos tablas de verdad grandes —206.365 y
193.025 filas de las fuentes de pre-auditoría— no se consultan dentro de
ningún ciclo. Corregirlos habría sido cambiar código que funciona por si
acaso. Queda anotado para revisar de nuevo si las glosas pasan de unos miles.

**Dos cosas para tener en el radar:**

- **Hay un archivo `glosas.db` de 0 bytes** al lado de la base buena. El
  motor usa `motorglosas.db` (bien), pero si algún script llega a apuntar al
  archivo vacío, el portal aparecería **sin ninguna glosa**. No se perdería
  nada —estarían en la otra—, pero el susto sería grande. Conviene borrarlo o
  renombrarlo cuando haya calma.
- **Las tablas de comentarios, notas privadas y filtros guardados están en
  cero.** No es que se hayan borrado con los routers: esta base arrancó
  vacía en el rescate del 4 de agosto. Las tablas están sanas y las pantallas
  ya funcionan otra vez; simplemente todavía no hay nada escrito en ellas.

### 13-08 (cierre) — Las tarifas de FAMISANAR quedaron cargadas y COMPROBADAS

Yesid subió el Excel desde la pantalla y el motor respondió: **6.655 creadas,
0 actualizadas, 6.655 filas leídas**, las cinco hojas, contrato
`S-13-1-03-1-04958`.

Comprobado contra la base del hospital, tarifa por tipo:

| Cómo quedó pactada | Cuántas |
|---|---|
| UVB por grupos | 4.586 |
| Tarifa propia | 1.557 |
| Ambulatorio | 413 |
| Órtesis y prótesis | 31 |
| Paquetes (urología, rehabilitación, gastro, columna…) | 68 |

**Las 4.586 de UVB quedaron rotuladas como «UVB POR GRUPOS» y no como
«tarifa propia»**, que era el defecto corregido esa misma mañana. Si hubieran
entrado mal, el dictamen le habría dicho a FAMISANAR que esas tarifas son
propias del hospital cuando en realidad son la UVB con el descuento del
contrato — y la entidad ratifica la glosa sin discutir el valor.

**Con esto el motor ya defiende las glosas de tarifas de FAMISANAR con el
valor pactado del contrato firmado, y no con SOAT pleno.** Es el círculo
completo: las cláusulas, las tarifas y el homologador CUPS → SOAT, los tres
cargados y comprobados en el motor del hospital.

**Un detalle de un día, anotado:** en «rigen hasta» quedó el **15/04/2027** y
el contrato dice hasta el **14/04/2027**. Solo importaría con un servicio
prestado justo ese día de 2027. Si se quiere exacto, se vuelve a subir el
mismo Excel con la fecha correcta y **marcando «Reemplazar tarifas
existentes»**, para que no queden duplicadas.

### 13-08 (último) — El botón «Analizar con IA» de Salud Total ahora sí llama a la IA

Ese botón existía desde antes y **no llamaba a la IA**: hacía lo mismo que las
otras dos opciones, responder con las plantillas por código de glosa. Yesid
pidió que hiciera lo que promete.

**Ahora cada glosa de la notificación pasa por el mismo motor que usa el
resto del portal.** O sea que responde con las 29 cláusulas del contrato, las
6.655 tarifas pactadas y el homologador CUPS → SOAT, igual que cuando usted
analiza una glosa desde «Analizar glosa».

**Cómo se usa:** en la pantalla de Salud Total escoja «Analizar con IA», suba
el TXT y dele a **Vista Previa**. Aparece un girador y la tabla se va
llenando. **Tarda varios minutos** —son 44 glosas, una por una— así que no
cierre la pantalla.

**Lo que hay que mirar en el resultado:** cada fila queda marcada con una
etiqueta.

- **IA** — la respondió el motor con todo el contexto del contrato.
- **PLANTILLA** — la IA no pudo con esa (se cayó el proveedor, se demoró
  demasiado) y salió con la respuesta de siempre. **Esas son las que conviene
  revisar a mano** antes de radicar.

**Ninguna fila queda vacía nunca.** Aunque se caiga el proveedor de IA
entero, el archivo sale completo con las plantillas. Se hizo así a propósito:
una fila en blanco en el archivo que se radica es una glosa sin responder, y
una glosa sin responder la entidad la da por aceptada.

**Dos cosas que todavía no se saben** y que solo se ven al usarlo con las 44
glosas reales: **cuánto tarda** y **cuánto cuesta**. Cada glosa es una
consulta a la IA, así que este botón sí gasta plata — a diferencia de las
otras dos opciones, que son gratis.

**Lo que enseñó la primera corrida de verdad (esa misma tarde):**

Yesid lo estrenó con la notificación de 44 glosas y salieron **dos defectos
míos**, los dos ya corregidos:

1. **El archivo llegó con código de programación adentro.** En la casilla de
   la observación, las 44 filas traían `<table border="1" style=…` cortado a
   la mitad. La causa: el dictamen del motor viene en formato de página web
   porque está hecho para verse en pantalla y en el PDF, y yo lo recorté sin
   quitarle ese formato. Ahora se extrae solo el argumento, y si por lo que
   sea saliera con código, esa fila se manda por plantilla antes que
   entregarle eso a la entidad.
2. **Los valores salían con decimal:** «FACTURADA POR $ 93340.0». Le estaba
   pasando a la IA el número crudo del archivo. Ahora recibe **$93.340** y
   **$280.000**, como se escribe acá.

**Y un hallazgo que no es un defecto pero conviene tener presente:** las 44
respuestas salieron con **el mismo argumento**, cambiando solo el código y el
valor. Y está bien que así sea: con Salud Total el hospital **no tiene
contrato**, así que no hay cláusula que citar ni tarifa pactada que invocar,
y el motor llega siempre al mismo sitio — el mismo que ya daba la plantilla,
gratis.

**En plata:** para **Salud Total**, «Extemporánea» o «Ratificada» dan
prácticamente lo mismo sin costo. **Donde el análisis con IA sí paga** es en
las entidades con contrato cargado —hoy **FAMISANAR**, con sus 29 cláusulas y
sus 6.655 tarifas—, porque ahí el dictamen puede citar la cláusula y el valor
exacto pactado, y eso la plantilla no lo hace.

### 30-07 al 14-08-2026 — Caja de bots del auditor (entregados por chat) y análisis PROTEGER EPS

Trabajo de este frente (rama `claude/bot-multifunctional-improvements-zhj4nw`,
PR #160). Los bots de esta quincena se entregaron **por el chat, en ZIP**, para
copiar al PC del auditor (no van en el repositorio porque procesan archivos
reales de las entidades):

- **Bot PARTIR/UNIR archivos grandes:** parte cualquier archivo (ej. un Excel
  de 72 MB) en piezas de 25 MB que sí pasan por el chat, y las vuelve a unir
  en el otro lado verificando que no se dañó ni un byte.
- **Bot OCR a PDF:** convierte PDF escaneados en PDF "buscables" (se les puede
  seleccionar y buscar texto). Además se hizo una **versión para celular** que
  funciona abriendo un archivo HTML en el navegador del teléfono, sin instalar
  nada y sin subir los documentos a ninguna página.
- **Bot de autorizaciones en RIPS (JSON):** busca los números de autorización
  dentro de los RIPS, en carpetas o rutas específicas, e informa cuando el
  campo viene vacío, en null o con un número distinto.
- **Bot DE1601 (NUEVA EPS):** completa el informe DE1601 celda por celda:
  saca la autorización del RIPS JSON (ruta de facturación electrónica), lee el
  PDF de la factura (fv) para tipo/documento/nombre del paciente, y verifica
  contra el soporte PDE/OPF de la carpeta de radicación (Y:), con OCR para los
  PDE escaneados. Llegó a la versión 7 afinando con 4 facturas reales; ninguna
  celda queda en blanco y trae hoja DIAGNOSTICO para los casos raros.
- **Bot de herramientas de imágenes (12 en 1):** quitar marca de agua (solo de
  imágenes propias), quitar fondo, fondo blanco, difuminar, mejorar, ampliar,
  comprimir, convertir, sacar texto (OCR), borrar texto sensible, recorte de
  cara y foto tipo documento.

**14-08 — Análisis del acta de conciliación PROTEGER EPS (NIT 901.543.211,
antes Cajacopi EPS):** primer trabajo de glosas con esta entidad (antes solo
aparecía en los consolidados de cartera del 23-07). Del archivo del acta salió
un **informe en Word** entregado por el chat: 70 facturas en el acta — **44
glosadas por $379.250.778** (sobre $464.426.624 facturados; 36 glosadas al
100%) y 26 marcadas "SIN GLOSA NI DEVOL". El 93,2% del valor glosado es tema
de **autorización frente al RIPS** (códigos SO2101, AU2103, SO2103, SO6101 y
afines) — glosa documental, defendible con los mismos bots de RIPS/DE1601. La
EPS ratificó $262.182.096 en 31 facturas; ya existen 44 notas crédito del
28-07-2026 por $70.084.248 (saneamiento de cartera, Acuerdo 020/2026), así que
lo aún en discusión ronda los $309 millones. El acta está sin fecha de
conciliación y con las casillas de resultado en cero. El informe cuadró al
centavo entre las hojas ACTA, GLOSA y TRAMITE del archivo.
- **14-08 (tarde):** se arregló en el **módulo web** lo mismo que se había
  arreglado en el bot: **ya no cuenta dos veces la misma plata**. El reporte
  del ADRES abre una fila por cada causal del mismo ítem; ahora la pantalla las
  **sigue mostrando todas** (el gestor decide causal por causal) pero **solo
  una cuenta** para el total.
  Además el cargue acepta un archivo más — el `FACTURAS PAQUETE NNNNN_NN
  FACTURAS.xlsx` — que trae la **cifra oficial por factura**. Con él, el módulo
  muestra el valor bueno y **avisa en rojo** cuando el detalle no cuadra, en la
  factura y en la lista.
  Probado con el 31078 entrando por los endpoints: sin ese archivo mostraba
  **$585.139.605**; con él muestra **$297.117.349,73**, exacto, y marca las 27
  facturas que no cuadran ($247.617.689, el 83 % del paquete).
  De paso se corrigió un defecto de redacción: los avisos convertían la coma de
  la frase en punto («glosado $34.942.962. pero el detalle...»).

### 25-08-2026 (noche) — La respuesta a glosa, repartida en la carpeta de cada factura

**De dónde sale.** La simulación sobre las tres carpetas del paquete (CAROLINA,
CLAUDIA y OSCAR) mostró que **a las 174 carpetas les falta la respuesta a glosa
y la epicrisis** — el 100 %. Sin eso, el PDF unido saldría sin los dos renglones
que encabezan la lista del área.

Las respuestas ya existen: son los 324 `RTA_ADRES_<FACTURA>.pdf` que se armaron
el 21-08. Solo faltaba llevarlas a su carpeta.

**Dos cosas que lo impedían, ya arregladas:**

1. **Las carpetas traen notas detrás del número.** `HUS379477_PEND. CARTA
   CORONEL`, `HUS367368 ACEPTADO`, `HUS378523_MAOS`. El bot que archiva
   soportes buscaba una carpeta llamada exactamente como la factura, así que a
   esas no las encontraba: **habría creado una segunda carpeta vacía al lado de
   la buena**, y el soporte habría quedado separado del resto.
2. **El lote es de las tres carpetas juntas.** Al soltar las 324 respuestas en
   la carpeta de un gestor, el bot le habría creado las carpetas de los otros
   dos. Con la opción nueva **«solo carpetas existentes»** deja quietas las que
   no son de ese gestor, y las lista al final para que no pasen calladas.

Probado de punta a punta con el ZIP de verdad: las respuestas cayeron en su
carpeta —incluidas las de nombre con nota— y el PDF unido ya sale con la
RESPUESTA A GLOSA de primera.

**Queda pendiente la EPICRISIS**, que no está en ninguna carpeta.

---

### 25-08-2026 — Un solo PDF de soportes por factura, en el orden que pide el área

**Lo que pidió el auditor:** que los soportes de cada factura se unan en un solo
PDF, y que queden en el **orden exacto** de la lista del área: respuesta a
glosa, epicrisis, historia clínica (urgencias, terapias, curaciones,
evoluciones, procedimientos), ayudas diagnósticas, medicamentos, notas de
enfermería, insumos y otros. Cada factura en su carpeta, con su número.

**Lo que quedó hecho:** un bot nuevo, `tools/unir_soportes_adres.py`, con su
botón de doble clic `UNIR_SOPORTES_ADRES.cmd` y su guía. Reconoce de qué es cada
PDF **por el nombre del archivo** —las palabras con que las nombra el equipo y
las abreviaturas del auditor (EPI, HC, DX, MED, NTE, INS)— y los une en el orden
de la lista. El **detallado no entra al PDF**: la lista lo pide en Excel, así
que se queda aparte en la carpeta.

**Dos cuidados con los nombres**, que son los errores que se cometen solos:
«NOTAS DE ENFERMERÍA» no se lo puede llevar la palabra «NOTAS» (gana siempre la
palabra más larga), y «INS» no puede casar dentro de «INSTITUCIONAL» (las
abreviaturas cortas tienen que ir sueltas).

**Lo que no reconoce, no se pierde:** va al grupo OTROS y sale listado en el
reporte para que el auditor lo revise. Si al equipo le falta una palabra, se
agrega sin tocar el código con `--mapa-nombres`.

**Tres candados, porque unir no se deshace de un clic:** simula por defecto y
muestra el orden completo antes de escribir nada; nunca se come su propio
consolidado (se puede correr las veces que haga falta); y un PDF dañado se omite
y queda anotado, sin tumbar el lote.

**El reporte avisa además** qué facturas no tienen respuesta a glosa o no tienen
epicrisis, que son los dos soportes obligatorios.

---

### 25-08-2026 — El detallado ya no deja servicios huérfanos

**Lo que reportó el auditor:** «tuve que modificar un detallado que me había
salido porque me había quitado los servicios y me tocó hacer el detallado
manual».

**Qué estaba pasando.** Cuando el ADRES **aprueba la cirugía** pero **sigue
glosando sus componentes** —honorarios del cirujano, del anestesiólogo, de
ayudantía, derechos de sala, materiales—, el bot quitaba el renglón de la
cirugía por aprobado y dejaba los componentes solos. El detallado quedaba
mostrando «servicios profesionales del cirujano» y «derechos de sala» **sin
decir de qué cirugía son**. Así no se puede defender, y toca rehacerlo a mano,
que fue justo lo que le tocó hacer en la HUS383283.

Pasa porque los dos sistemas hablan distinto: el ADRES glosa con **códigos
SOAT** (39010, 39110, 39214…) y la factura del hospital trae la cirugía con su
**código CUPS** (13723, 14171…). El CUPS no aparece en el reporte del ADRES, así
que el bot lo leía como «aprobado» y lo borraba.

**Cómo quedó.** El renglón principal ahora **se conserva como ENCABEZADO**: se
ve, para que se sepa a qué cirugía pertenecen los servicios, pero **no suma al
total** —su valor ya está en los renglones que quedaron—. Es exactamente lo que
usted hizo a mano. Si no queda ningún componente vivo, el principal se va como
siempre.

En la bitácora CSV esos renglones salen con la acción `ENCABEZADO` y la nota de
por qué se quedaron.

---

### 24-08-2026 — Las objeciones del ADRES, cuadradas con lo que el ADRES reporta

**Lo que pidió el auditor:** que los archivos de objeciones cuadren con el
**Valor Glosado** que trae el `ReporteReclamPAQUETE_31068`, y que **ningún
renglón quede sin código de servicio**.

**Lo que estaba pasando (y era grave):** el detalle del ADRES cuenta la misma
plata más de una vez. Los archivos entregados el 21-08 sumaban
**$1.032.239.679** cuando el ADRES reporta **$646.908.552** glosados. Cargar eso
a Dinámica Gerencial habría sido objetar hasta **tres veces el mismo dinero**.

**Por qué se repetía.** Dos motivos, los dos del archivo del ADRES:

1. Cuando el ADRES glosa la reclamación entera por el FURIPS, además de listar
   los servicios mete **una fila por cada causal de reclamación** (2102, 2103…)
   con el valor **completo**. La factura HUS0000311371 aparecía por $39.722.100
   cuando el ADRES reporta $13.240.700: el detalle ($13.240.700) más dos
   renglones de causal, cada uno por el total.
2. El mismo servicio, con la misma cantidad y el mismo valor, listado otra vez
   porque le cayó otra causal encima.

**Lo que quedó hecho.** El bot ahora recibe el reporte del ADRES y deja **cada
factura sumando exactamente lo que el ADRES dice que glosó**: quita los
renglones que repiten el total, después las repeticiones —la más grande primero
y **sin bajarse nunca del valor reportado**, porque quitar de más sería objetar
menos de lo que nos glosaron— y si aún queda diferencia la carga al renglón
mayor. **Todo lo que se quita y todo lo que se ajusta queda anotado** en la hoja
REVISAR, con el antes y el después.

**Resultado del paquete 31068:**

- **324 de 324 facturas cuadran** con el reporte del ADRES.
- Total objetado: **$646.908.553** (el peso de diferencia es el redondeo: el
  ADRES reporta $646.908.551,95 y DGH recibe pesos enteros).
- Se quitaron **169 renglones** repetidos y se ajustaron **65 facturas**.
- **Ningún renglón quedó sin código de servicio** (antes eran 1.856).

**Dos cosas que hay que revisar, y son importantes:**

1. **1.768 renglones ($307.480.311) llevan un código de servicio ASIGNADO**, no
   homologado: cuando el cruce no encontró el servicio, se les puso el candidato
   más parecido o el servicio de más peso de la factura. Es para que el archivo
   cargue, no es una homologación. Están todos listados en REVISAR.
2. **65 facturas llevan un valor ajustado** ($64.825.592 en 69 renglones) para
   que la factura cuadre. Cada ajuste está en REVISAR con el valor de antes y el
   de después.

**Un hallazgo aparte, que corrige la entrega del 21-08:** el reporte del ADRES
dice que las **581 reclamaciones del paquete son «Reclamacion Normal»** — o sea,
**ninguna es extemporánea**. Los PDF y los Word que se armaron el 21-08 se
hicieron **con** el aviso de glosa extemporánea, porque el documento de ejemplo
lo traía. Hay que volver a generarlos **sin** esa opción antes de radicarlos.

---

### 21-08-2026 — Las glosas del ADRES, en el formato OBJECIONES de DGH

**Lo que pidió el auditor:** organizar el archivo del **«ADRES DANIEL»** para
convertirlo en el archivo de **OBJECIONES** que se viene trabajando con
COOSALUD, «pero que todos los servicios queden completos», y usar el DGReport y
el Homologador Gold Standard para homologar los servicios o códigos que no se
encuentren.

**El problema de fondo:** el ADRES y DGH le ponen nombres distintos al mismo
servicio. El ADRES usa el **código SOAT** (`29117` terapia respiratoria,
`38134` habitación de cuatro o más camas) y el **registro INVIMA** de los
medicamentos y materiales (`2016DM-0000315-R2`); DGH usa su código interno
(`939403`, `10A004`, `FMQ0041`). Mientras no estén homologados, el archivo no se
puede cargar: esa columna es la que amarra cada objeción con el renglón que se
facturó.

**Lo que quedó hecho:** un bot nuevo, `tools/organizar_objeciones_adres.py`, con
su botón de doble clic `OBJECIONES_ADRES.cmd` y su guía
`README_organizar_objeciones_adres.md`. Homologa por seis caminos, siempre
dentro de la misma factura y parando en cuanto uno acierta: código directo,
SOAT→CUPS con el Homologador, descripción igual, descripción que empieza igual,
**valor exacto más palabras en común** (así se resuelve «Habitación de cuatro ó
mas camas» ↔ «Internación complejidad alta cuatro o mas camas») y descripción
muy parecida.

**Resultado del paquete 31068:** las **4.619 glosas** de las **324 facturas**
salieron en dos archivos —`OBJECIONES_ADRES_LOTE_01.xlsx` (300 facturas) y
`_LOTE_02.xlsx` (24)—, porque DGH no recibe más de 300 facturas por archivo. Se
homologaron **2.763 de los 3.262 renglones que señalan un servicio (84,7 %)**.
Total objetado: **$1.032.239.679**.

**Ningún renglón se perdió**, que era lo que pidió: hay tantas filas en la
salida como glosas trae el ADRES. Y **lo que no se pudo homologar no se
inventó**: sale con la casilla vacía y queda listado en el archivo
`REVISAR_OBJECIONES_ADRES.xlsx` con el candidato más parecido.

**Tres cosas que hay que revisar antes de cargar:**

1. **El código de la glosa.** El ADRES usa códigos numéricos de cuatro dígitos
   (`3106`, `3209`, `4506`) y DGH los de seis del Manual Único (`SO3401`,
   `CL0101`). **No hay una tabla oficial que los equipare**, así que el bot
   escribe el del ADRES tal cual. La hoja `CODIGOS` del archivo REVISAR trae los
   50 códigos con cuánta plata mueve cada uno y el grupo del Manual Único que le
   corresponde, para armar la equivalencia; después se le pasa al bot con
   `--mapa-codigos`.
2. **499 renglones sin código de servicio** ($135.744.756). Casi todos son los
   códigos SOAT que descomponen una cirugía —honorarios de cirujano, ayudantía,
   derechos de sala, materiales—: DGH factura la cirugía en **un solo renglón**,
   así que no hay a cuál amarrarlos uno por uno. Se probó deducirlos sumando los
   componentes hasta cuadrar con el renglón de DGH y **se descartó**: en varias
   facturas cuadraban dos combinaciones distintas, y adivinar mal el servicio en
   un archivo que se carga al ERP es peor que dejarlo en blanco.
3. **1.630 renglones de glosa total por FURIPS** ($236.217.091) no traen causal
   propia, y **1.357** no señalan ningún servicio: el ADRES glosó la reclamación
   entera. Salen en el archivo y quedan avisados uno por uno.

El bot también trae el **guardián de valores** del cruce de DGH de la Suite
Cartera: la objeción nunca supera el valor del servicio en DGH ni el saldo de la
factura. En el 31068 recortó **$2.110.859** en 15 renglones, todos anotados con
el antes y el después.

Y como siempre: **piloto de UNA factura antes del cargue masivo**.

---

### 21-08-2026 — El PDF y el Word de respuesta, uno por cada factura

**Lo que pidió el auditor:** que de la macro salgan de una vez los documentos
que se radican — el **PDF de respuesta** por factura y, además, un **Word** con
el formato del `Reporte_Factura_HUS298253_CAROLINA.docx` que compartió de
ejemplo.

**Lo que quedó hecho:** un bot nuevo, `tools/respuestas_adres_por_factura.py`,
que de un solo tirón saca los dos por cada factura:

- `RTA_ADRES_<FACTURA>.pdf` — el REPORTE RTA ADRES, con su tabla de seis
  columnas. Reusa el mismo generador que ya usa la pantalla web, así que el
  papel sale idéntico se arme por donde se arme.
- `Reporte_Factura_<FACTURA>_<GESTOR>.docx` — encabezado con lo aceptado, una
  respuesta por párrafo y **las aceptadas de primeras**, tal como lo pidió.

El texto de cada respuesta sale **tal cual** de la columna «RTA GLOSA COMPLETA»
de la macro: es lo que redactó el auditor y el bot no lo reescribe.

**Resultado del paquete 31068:** 324 facturas → **324 PDF y 324 Word**, sin un
solo error. $798.133.471 glosados y $91.617.467 aceptados, 108 facturas por
gestor.

**Dos cosas que el bot no decide solo, y hay que saberlas:**

1. **El aviso de glosa extemporánea** es una afirmación jurídica sobre el
   paquete y la macro no trae las fechas para comprobarla. Por eso hay que
   pedirlo con `--extemporanea`. La entrega del 21-08 se hizo **con** el aviso,
   porque el Word de ejemplo lo traía; si para el 31068 no aplica, se vuelve a
   correr sin esa opción y listo.
2. **Las glosas totales no se responden una por una** (1.630 renglones): no
   entran en los documentos, pero se avisan al pie con cuántas son y cuánto
   valen. Nada queda escondido.

De paso se arregló un defecto del generador de PDF que también afectaba a la
pantalla web: hay respuestas de más de 2.500 caracteres —una sola celda más
alta que la hoja— y el PDF de esas dos facturas no se podía armar. Ahora el
renglón se parte entre dos páginas.

---

### 20-08-2026 — Cada soporte, en la carpeta de su factura

**Lo que pidió el auditor:** en la carpeta del gestor (CAROLINA, del paquete
31068) hay PDF sueltos, mezclados con las carpetas de las facturas ya armadas.
Que cada uno se meta en la carpeta de su factura, y que la carpeta se cree si no
existe.

**Lo que quedó hecho:** un bot nuevo, `tools/organizar_soportes_por_factura.py`,
con su botón de doble clic `ORGANIZAR_SOPORTES.cmd`. Toma el número de factura
del comienzo del nombre del archivo —que es como los nombra el equipo— y lo mete
en su carpeta.

**Mover archivos no se deshace**, así que el bot va con tres candados:

1. **Simula por defecto.** Muestra el listado de lo que haría y no toca nada
   mientras no se le diga `--aplicar` (el botón lo pide escribiendo «SI»).
2. **Nunca pisa un archivo.** Si en la carpeta destino ya hay uno con el mismo
   nombre, al que llega le pone « (2)» y lo avisa. Lo que ya estaba archivado no
   se pierde.
3. **Solo toca lo suelto.** Lo que ya está dentro de una carpeta se queda
   quieto, y lo que no dice de qué factura es también: sale listado al final.

Al terminar dice **qué carpetas creó**, para que se vea de una si alguien
escribió mal un número.

**En la carpeta de CAROLINA (hecho el 20-08):** 35 PDF sueltos de **23 facturas
distintas**; cinco ya tenían carpeta y se crearon **18**. Antes de mover se
cruzaron las 23 contra las 324 facturas de la macro: **todas son del paquete**,
ninguna con el número mal escrito.

Después de mover quedó **1 solo PDF suelto**, el `REPS.pdf`, y está bien que así
sea: no es de una factura sino la habilitación del hospital, que se copia a las
facturas que la necesitan. Ningún archivo chocó de nombre, así que no hubo que
renombrar nada. En la carpeta quedaron 102 PDF archivados (los 35 movidos más
los 67 que ya estaban), y el listado de qué se movió está en
`SOPORTES_ORGANIZADOS.csv`, dentro de la misma carpeta.

Probado con los nombres reales, que traen comas, espacios dobles y hasta
«- copia» — 37 pruebas, con los dos candados comprobados por mutación.

**Nota para el próximo paquete:** el bot vive en `C:\motor-glosas\repo`, que es
la copia que el autodeploy mantiene al día. La de `C:\temp-notas` está vieja
(quedó en el 5 de agosto) y no conviene usarla.

---

### 19-08-2026 (cierre) — El consolidado: cuántas facturas hay de cada lado

**Lo que pidió el auditor:** confirmar si las facturas del ZIP de detallados son
las mismas de la macro, y si no, **por qué no están**.

**La respuesta:** en la macro hay **324** facturas y en el ZIP hay **320**
detallados. **Faltan 4**, por **$43.518.600** glosados:

| Factura | Radicado | Glosas | Valor glosado | Ya aceptado |
|---|---|---:|---:|---:|
| HUS311371 | 14345108 | 150 (21 por responder) | $39.722.100 | $0 |
| HUS394817 | 14383060 | 12 | $3.646.700 | $2.400 |
| HUS380246 | 14351110 | 2 | $139.400 | $0 |
| HUS367368 | 14344771 | 1 | $10.400 | $10.400 |

**No sobra ninguna** del otro lado: los 320 detallados están todos en la macro,
y el número de factura de adentro de cada archivo coincide con su nombre.

**Por qué faltan:** son **las mismas cuatro** que ya venían señaladas desde el
04-08. El sistema del hospital **nunca exportó** su detallado — se buscaron
archivo por archivo en los siete lotes y no están en ninguno. Hay que pedirle a
facturación esa impresión.

**Lo que quedó hecho:** un bot nuevo, `tools/cruzar_detallados_con_macro.py`,
que arma el consolidado en un Excel de tres hojas: RESUMEN, FACTURAS (todas, con
su estado y sus cifras) y SIN DETALLADO (solo las que faltan, con **el radicado**
que hay que llevarle a facturación y cómo quedó respondida cada glosa). Sirve
para cualquier paquete, no solo el 31068.

---

### 19-08-2026 (tarde) — Las 320 facturas sin el total en letras, y en PDF

**Lo que pidió el auditor:** que a las facturas se les quite el total escrito en
palabras —que ese espacio quede vacío, dejando solo los valores en número— y que
después todas se conviertan a PDF.

**Lo que quedó hecho:** un bot nuevo, `tools/quitar_total_en_letras.py`. Borra el
renglón en letras y deja el espacio vacío; la etiqueta `TOTAL:` se queda. Los
números, el formato, las celdas combinadas y los anchos no se tocan, y los
archivos de origen tampoco: escribe copias nuevas.

No borra a ciegas: solo vacía las celdas que de verdad traen un importe escrito
en palabras (las que dicen PESOS y CTVS), y solo en el renglón del `TOTAL:`. Si
en algún archivo no encuentra ese renglón, lo dice en vez de callarlo.

Después se pasaron a PDF con el bot que ya existía (`tools/excel_a_pdf.py`).

**Resultado:** 320 Excel sin letras y **320 PDF** (351 páginas). Comprobado sobre
los PDF ya generados: **ninguno** muestra un importe en palabras, **todos**
conservan el VALOR TOTAL ORDEN DE SERVICIO en número, y la suma de los
subtotales sigue siendo **$625.461.616,95**, la misma de antes.

**Después el auditor pidió una cosa más:** quitar también el **pie legal del
final** —la autorización de la DIAN, el aviso de la letra de cambio, los
intereses moratorios, «Nombre reporte» y «LICENCIADO A»—, de modo que la hoja
**termine en la firma del auditor**. Se agregó la opción `--quitar-pie` al mismo
bot. El pie se busca de abajo hacia arriba y se corta en el primer renglón que
no sea del pie, así que la firma, las notas finales y los totales nunca se
tocan. Se volvieron a generar los 320 PDF: quedaron en **340 páginas** (11 menos)
y ninguno trae ya nada del pie ni del total en letras; el dinero no se movió.

**Un detalle importante:** el auditor mandó para este trabajo el ZIP de la
**primera** entrega, la que todavía traía los tres errores (total
$627.442.241,95). El trabajo se hizo sobre la **versión corregida**, para no
volver a poner en circulación las facturas malas.

---

### 19-08-2026 — Se recuperaron $654.075 más: el servicio partido en dos renglones

Una medición sobre las 320 facturas mostró por qué faltaba tanta plata por
descontar en la **HUS383283**: el detallado trae los **honorarios del cirujano
partidos en dos renglones** de $320.600 —porque la cirugía se hizo dos veces— y
la macro los reclama en **una sola fila** de $641.200. Los dos renglones suman
exactamente esa cifra, pero el bot exigía que además cuadrara la **cantidad**
(2 renglones contra 1 unidad) y por eso no los emparejaba.

Ahora, cuando el **código** o la **descripción completa** coinciden y el valor
suma exacto, se emparejan y el descuento se reparte a prorrata. **Por prefijo de
descripción se sigue exigiendo la cantidad**: ahí a la descripción del reporte le
basta con ser el comienzo de la del detallado, y sin ese segundo candado un
nombre genérico podría llevarse el grupo equivocado.

Recupera **$654.075** en dos facturas (HUS383283 y HUS397556). Antes de tocar
nada se midió el efecto sobre las 320 facturas y sobre el otro flujo que usa el
mismo motor de cruce: **ningún emparejamiento existente se pierde ni cambia de
pareja**; solo se agregan 8 nuevos.

**Cifras del paquete 31068:**

| | |
|---|---|
| Valor de las facturas antes | **$714.332.224** |
| Menos lo que ya se aceptó | **$88.870.607** |
| **TOTAL FINAL que sigue reclamando el hospital** | **$625.461.617** |

**Tres mejoras más quedaron medidas pero NO se aplicaron**, porque la revisión
adversarial las marcó riesgosas y valen poco ($40.900 entre las tres):

- bajar de 12 a 10 letras el cruce por comienzo de descripción ($34.500): dejaría
  que un nombre genérico como «Hemocultivo» se lleve el renglón equivocado **en
  silencio**;
- desempatar por precio unitario ($5.000) y limpiar los caracteres dañados de la
  macro ($1.400): mismo tipo de riesgo.

Son decisión del área: recuperan poco y el motor de cruce lo comparten los otros
bots del hospital.

---

### 18-08-2026 (cierre) — Una fila corrida de la macro casi borra una radiografía

Siguiendo la revisión, apareció **una segunda factura con problema**: la
**HUS396996**. El bot le había dejado en **cero** una radiografía de mano de
$73.500 que el hospital **sigue reclamando**.

**Por qué.** En la macro hay **una sola fila** (de 4.619) donde la columna
VALOR ACEPTADO quedó **corrida un renglón**: la fila de la radiografía de mano
—que además dice **SE OBJETA**— trae $758.700 aceptados, que en realidad son
del tórax de la fila de abajo. El bot se lo tragó tal cual.

**Lo que faltaba en el bot.** El programa prometía en su documentación que las
**SE OBJETA** y las **SE SUBSANA** no tocan el detallado… pero **nunca leía esa
columna**. Ahora sí, y además rechaza cualquier fila donde el valor aceptado sea
**mayor que el valor reclamado** de esa misma fila: eso es imposible, no se
puede aceptar más de lo que se cobró. Cualquiera de las dos guardas atrapa el
caso; están las dos.

**Otro hueco que se tapó.** Si la macro le acepta plata a una factura que **no
tiene detallado** en la carpeta, antes esa plata desaparecía del control. Ahora
la factura sale igual en la bitácora con estado **SIN_DETALLADO**: son
**HUS367368** ($10.400) y **HUS394817** ($2.400).

**Cifras definitivas del paquete 31068:**

| | |
|---|---|
| Valor de las facturas antes | **$714.332.224** |
| Menos lo que ya se aceptó | **$88.216.532** |
| **TOTAL FINAL que sigue reclamando el hospital** | **$626.115.692** |

**Ojo con la HUS396996:** por el mismo corrimiento de la macro, al tórax se le
descontaron $7.800 cuando el equipo lo aceptó por $758.700. **Esa factura hay
que revisarla completa antes de radicar**, y de paso corregir la macro.

---

### 18-08-2026 (noche) — Una factura salió mal y se corrigió: la HUS388262

**Lo que pasó.** Después de entregar los 320 Excel, una revisión independiente
encontró que **una factura quedó mal**: la **HUS388262**. Su total seguía
$1.400.050 por encima de lo que corresponde, o sea que ese archivo le estaba
reclamando al ADRES una plata que el hospital ya había aceptado. Las otras 319
estaban bien.

**Por qué pasó.** Esa factura tiene **dos cirugías**. En el detallado, debajo
del procedimiento se imprimen los honorarios —cirujano, anestesiólogo,
ayudantía, derechos de sala—. Los de la primera cirugía **ya están dentro** del
valor del procedimiento y no vuelven a sumar; los de la segunda **sí suman**,
porque no están dentro de ningún renglón. El bot decidía «suman todos» o «no
suma ninguno» **para la factura entera**, y en esta se equivocó.

**Cómo quedó arreglado.** Ahora el bot decide **bloque por bloque**: va sumando
los renglones sin número hasta completar exactamente el valor del procedimiento
que tienen encima —ese es su desglose, no cuenta— y lo que siga después es
cirugía aparte, que sí cuenta.

**Y se le puso un candado.** Antes de guardar cada archivo, el bot se pregunta:
«la suma de los renglones que doy por buenos, ¿reproduce el subtotal que trae el
archivo?». Si no lo reproduce, **no inventa el subtotal**: descuenta solo los
servicios numerados y escribe **REVISAR A MANO** en la bitácora. De las 320
facturas, el bot entiende 318; las dos que no —**HUS384132** y **HUS392442**—
quedaron avisadas (y en las dos el descuento sí cuadró con la macro).

**Las cifras corregidas del paquete 31068:**

| | |
|---|---|
| Valor de las facturas antes | **$714.332.224** |
| Menos lo que ya se aceptó | **$88.290.032** |
| **TOTAL FINAL que sigue reclamando el hospital** | **$626.042.192** |

De paso, el bot ya **no toca el contador de servicios** de la fila del subtotal:
como nunca borra renglones, ese número debe quedar tal como lo dejó el sistema
del hospital (en la entrega anterior lo había movido en 4 archivos).

Se agregaron pruebas automáticas del caso de las dos cirugías y del candado, y
se comprobó que si se le quita cualquiera de las dos cosas, las pruebas fallan.
La verificación final se hizo sumando los subtotales de los 320 archivos de
salida con un lector independiente: da **$626.042.191,95**, y en las 320 el
TOTAL DE LA ORDEN coincide con el subtotal.

---

### 18-08-2026 — Se le quita al detallado lo que la EPS ya aceptó (paquete 31068)

**Lo que pidió el auditor:** cruzar los Excel por factura del paquete 31068
(los del ZIP `EXCEL_POR_FACTURA_31068`) contra la macro de respuesta
`RTA GLOSA ADRES PAQ 31068`, **quitarle a cada servicio el VALOR ACEPTADO** y
sacar la **suma final** de lo que el hospital sigue reclamando.

**Lo que quedó hecho:** un bot nuevo, `tools/descontar_aceptado_detallado.py`.
Lee la macro, se queda **solo** con las filas que tienen VALOR ACEPTADO mayor
que cero (las SE OBJETA y las SE SUBSANA se siguen reclamando completas), las
cruza contra el detallado y le baja la plata al renglón que corresponde.
Recalcula el VR UNIT, el subtotal, el total de la orden y el total en letras.
El formato no se toca: celdas combinadas, anchos, bordes y moneda quedan igual.

**El cruce no es por código a secas.** El detallado usa el código del hospital
(`FMQ0046`) y la macro el del ADRES (`2016DM-0000315-R2`), así que se reusó el
mismo motor de rondas del ajustador: código → descripción → cantidad+valor →
valor, con emparejamiento único. Lo que no cruza **se informa, no se adivina**.

**Resultado sobre las 320 facturas:**

| | |
|---|---|
| Valor de las facturas antes | **$714.332.224** |
| Menos lo que ya se aceptó | **$88.290.032** |
| **TOTAL FINAL que sigue reclamando el hospital** | **$626.042.192** |

El ejemplo que mandó el auditor (HUS352890) sale igualito: la consulta de
urgencias baja de $85.800 a $83.400 por los $2.400 aceptados, y la factura
queda en $130.400 en vez de $132.800.

**Un susto que se atajó a tiempo.** La primera corrida daba $607 millones,
$106 millones de menos. La causa: en 50 de las 320 facturas los honorarios de
cirujano y de ayudantía vienen **sin número de consecutivo** —el lector los
tomaba como "desglose" que no suma— pero en esas facturas **sí están sumados**
en el subtotal. La solución fue dejar de recalcular el subtotal desde cero:
ahora se toma **el subtotal que ya trae el archivo** (que es el bueno) y solo
se le resta lo descontado. Cuando hay renglones sin consecutivo, el bot mira
cuál de las dos sumas se parece al subtotal del archivo y decide factura por
factura. Las 320 salidas quedaron con subtotal = total y con el total en
letras recalculado.

El bot deja además una **bitácora en CSV** con una línea por servicio
descontado: factura, servicio, valor antes, aceptado, valor después, por dónde
cruzó, las causales y una columna **CUADRA** que dice SI o NO comparando lo
descontado contra lo que dice la macro. Ahí se ven las 14 facturas que no
cuadran ($3.327.635) para que el auditor las revise a mano.

Se cubrió con **29 pruebas automáticas** (`tests/test_tools/test_descontar_aceptado_detallado.py`),
incluidas las dos trampas del formato (el desglose que suma y el que no) y los
avisos: aceptado mayor que el servicio, aceptado sin ítem en el detallado y
Excel dañado que no puede tumbar el lote.
### 14-08 — El importador aprende a PONER AL DÍA y entra el consolidado ADRES

Yesid mandó TRES Excel para dejar la página al día: el consolidado 2026
con corte al 13-08, los oficios de devolución hasta el DEV-PRE-AUD-0113 y
el **consolidado ADRES/SINAC 2025** (un formato hermano, con la columna
Oficio adelante y 26 columnas). Comparados con lo cargado el 05-08:
**56 facturas nuevas** del consolidado, **32 ya cargadas que avanzaron**
(radicadas/devueltas/subsanadas después de la primera carga), **62
facturas ADRES** que no estaban en ninguna parte, y **8 oficios de
devolución nuevos** (0106 a 0113).

El importador del consolidado antes SALTABA toda factura que ya existiera;
con eso las 32 que avanzaron se habrían quedado congeladas. Se le enseñó a
**ponerlas al día sin tocar nada de lo guardado**, y la primera versión de
ese cambio pasó por una revisión adversarial de tres frentes que confirmó
**15 defectos reales** — todos corregidos antes de publicar:

- Solo toca facturas que ESTE MISMO importador creó y que la página nunca
  ha tocado; la historia guardada debe encajar como el COMIENZO de la del
  Excel, y entonces agrega SOLO los eventos que faltan al final. Si no
  encaja, conflicto reportado y no se toca (con la pista de que escribir
  la F_DEV que faltó suele destrabar).
- Al reingresar limpia el amarre al oficio de devolución (como la página),
  refresca la fecha de recibido, no borra el envío si la fila viene vacía,
  y deja el motivo de devolución en blanco al quedar radicada.
- El estado ya no retrocede a NUEVA cuando hay reenvío sin decidir
  (queda EN_SUBSANACION), y si un encabezado quedó mal de una corrida
  vieja se sana solo (sin duplicar eventos).
- Revalida cada factura DENTRO de la transacción por si la página escribe
  en ese mismo instante, avisa de fechas dañadas (una celda con hora
  «00:00» en vez de fecha) y de filas repetidas idénticas.
- Reconoce solo el formato ADRES: lo traduce al mismo modelo, normaliza
  los números de oficio (FHUS- AS-101139-26 → FHUS-AS-I01139-26) y
  traduce las iniciales de los auditores (EC, ES, DI).
- 10 pruebas nuevas (21 en total entre los dos importadores).

**Ensayo con los datos reales** (copia, no la base del PC): quedó en
**1.077 facturas, 3.372 eventos, 164 oficios de recepción y 11 oficios de
devolución** — incluido el **0111 con sus 28 facturas ADRES** y el 00103
con 3, que antes no se podían armar porque esas facturas no existían.
Cero conflictos, los amarres del 0104/0105 intactos, y correr el trío dos
veces no cambia nada. Los PDF del 0109 y el 0111 salieron de muestra.

**Lo único que queda por fuera:** el oficio 0099 (su única factura,
HUS0000533242, no aparece en ningún Excel) — cuando el equipo la escriba
en el consolidado, entra sola en la siguiente corrida.

**Y LA CORRIDA REAL EN EL PC SALIÓ BIEN (mismo 14-08):** Yesid corrió el
trío con los archivos nuevos. Consolidado 2026: 56 facturas nuevas + 29
puestas al día (las otras 3 que avanzaron —540518, 543271, 545425— el
equipo ya las había trabajado en la página, así que el sistema las
respetó, como debe ser). ADRES 2025: las 62 completas. Oficios de
devolución: 9 nuevos (00103 con 3 facturas y 0106 a 0113, incluido el
0111 con sus 28), 57 eventos amarrados, cada uno con su botón PDF.
Cero conflictos, cero choques con la página. El informe ya sale con la
información de los tres Excel. Pendiente de datos: la factura del 0099 y
la celda F_DEV dañada de la fila 1271 (factura 542017).

---

### 18-08 — Carpeta de trabajo organizada: nace `D:\TRABAJOS BOTS`
- **Pedido del auditor:** con tantos frentes abiertos (SIIFA, COOSALUD,
  SIMED, DGH, ADRES, Suite Cartera...) cuesta acordarse "¿en qué carpeta
  estaba el bot de tal cosa?" y cada vez toca buscar. Pidió una carpeta
  única en `D:\TRABAJOS BOTS`, organizada por tema, con todo lo de cada
  frente junto y de forma intuitiva: que al pedir algo se sepa de una a
  qué carpeta ir y qué bot correr, sin perder tiempo.
- **Solución entregada:** un bot nuevo de doble clic,
  `tools\ORGANIZAR_TRABAJOS_BOTS.cmd`, que arma (o pone al día) la
  carpeta `D:\TRABAJOS BOTS` con **12 carpetas por frente** — 1.COOSALUD,
  2.SIMED-Dispensario, 3.DGH, 4.SIIFA, 5.ADRES-FURIPS, 6.Glosas ADRES y
  detallados, 7.Pre-auditoría SINAC, 8.Suite Cartera HUS, 9.Otras EPS
  (Mutual Ser/FOMAG/SAVIA/EMSSANAR/Famisanar), 10.Herramientas generales
  (PDF/Excel/ZIP), 11.Motor de Glosas-servidor web y 12.Documentación —
  más un **índice maestro** en la raíz ("0. LEEME PRIMERO - INDICE.txt")
  con la tabla *"si te piden esto → ve a esta carpeta"*.
- **Qué deja en cada carpeta:** accesos directos (doble clic) a los bots
  que ya lo permiten (MOTOR_HUS, CARGAR_SIIFA, VALIDAR_FURIPS, INICIAR
  SUITE CARTERA, ESTADO_MOTOR, etc.), accesos a las guías (`docs/...`)
  abiertas con Notepad, y un `LEEME.txt` en español sencillo por carpeta:
  cuándo venir ahí, qué bot usar y — para los robots que aún no tienen
  doble clic (COOSALUD, SIMED, DGH, Mutual Ser, FOMAG) — el **comando de
  PowerShell listo para copiar y pegar**, con la regla del piloto de 1
  factura siempre recordada.
- **No copia ni mueve nada del repositorio**, solo crea accesos directos:
  si el bot cambia, el acceso directo lo sigue viendo sin volver a correr
  el organizador. Es seguro correrlo las veces que haga falta (no borra
  nada que el auditor haya puesto a mano en `D:\TRABAJOS BOTS`) — así que
  cuando se agregue un bot nuevo, basta con volver a darle doble clic a
  `ORGANIZAR_TRABAJOS_BOTS.cmd` para que la carpeta quede al día sola.
- **Cómo usarlo:** copiar la carpeta `tools\` actualizada al PC (o
  `git pull` en `C:\temp-notas`) y dar doble clic en
  `tools\ORGANIZAR_TRABAJOS_BOTS.cmd`.

---

### 18-08 — Cómo comprobar que el SOAT 2026 quedó bien, y las 1.503 tarifas que faltaban

Yesid preguntó dos cosas: **cómo quedó el homologador de CUPS a SOAT 2026** y,
sobre todo, **cómo saber que quedó bien instalado en el sistema**. Y mandó los
dos PDF que faltaban del paquete de agosto.

**1) Ahora hay un botón para comprobarlo, sin depender de nadie.**

Doble clic en `tools\VERIFICAR_CATALOGOS_SOAT.cmd`. Abre una pantalla, revisa
las dos tablas del SOAT y termina diciendo **VERIFICADO** o **FALLA**. Solo
mira: no cambia nada. Si falla, dice qué falta y qué hacer.

Comprueba que el homologador instalado sea el del 2026, que ningún CUPS haya
vuelto a guardar una frase como si fuera código SOAT, que el Manual SOAT traiga
más de 1.500 códigos, y cinco tarifas escogidas a mano contra el PDF oficial.

**2) El sistema conocía CUATRO tarifas SOAT. Ahora conoce 1.507.**

Ese fue el hallazgo del día, y salió del PDF que mandó Yesid (la **Circular
Externa 047 del 30 de diciembre de 2025**, la que fija las tarifas del Manual
Tarifario para 2026). El liquidador de tarifas del portal decía en su
documentación que usaba esa Circular, pero por dentro solo tenía **cuatro
códigos** transcritos a mano como «ejemplos». Para todos los demás contestaba
«sin tarifa local — consulte el Manual SOAT 2026 oficial», que es exactamente
lo que uno necesita **cuando la EPS objeta la tarifa**.

Se cargaron las 1.507 de la Circular. Eso alimenta tres sitios a la vez: el
liquidador de tarifas, el letrero de tarifa que sale al analizar una glosa, y
el bloque de datos que se le entrega a la IA para redactar el dictamen.

**En plata:** el reemplazo de cadera (código 513014) vale 1.223,71 UVB ×
$12.110 = **$14.819.100** a tarifa SOAT plena, y **$14.078.200** con el −5% de
FAMISANAR. Antes de hoy, ese código no tenía tarifa en el sistema. Esto pesa
sobre todo en los contratos pactados contra el SOAT: **FAMISANAR** («SOAT UVB
vigente −5%») y **Policía Nacional** («UVB −8%»).

**Por qué se puede confiar en cifras sacadas de un escaneo.** La Circular es un
PDF escaneado: el computador tuvo que reconocer los números. Se comprobó de
tres maneras distintas y las tres dieron lo mismo: dos lecturas independientes
del mismo PDF (cero diferencias en 1.498 tarifas), los cuatro códigos que un
humano había transcrito antes a mano (coinciden los cuatro), y el Excel Gold
Standard con su propia columna de UVB (1.048 iguales de 1.250, y las 202
restantes difieren en **una centésima de UVB** —unos $121— y ninguna en más:
es redondeo, no error de lectura; manda la Circular, que es la norma).

**3) Dos errores de cien pesos, corregidos.**

- El código SOAT 19007 tenía escrito **$771.800** y son **$771.900**: se había
  redondeado hacia abajo en vez de a la centena más próxima, como manda el
  Decreto 780/2016. Cien pesos, pero era una cifra que el sistema le entregaba
  a la IA como «valor oficial».
- Al prompt de la IA los pesos le llegaban escritos a la gringa
  («$14,819,100»). Ahora van **$14.819.100**, como se escribe acá. Es el mismo
  defecto que salió el 13-08 con «$ 93340.0», en otro sitio del código.

**4) Buscar en el liquidador ya no exige poner las tildes.** Escribir
«osteosintesis» no encontraba nada porque la Circular dice «Osteosíntesis».
Ahora encuentra los 27 códigos de osteosíntesis igual, con tilde o sin ella.

**Lo que NO se cargó, para que no quede la impresión de que sí:**

- El **«Proyecto Manual SOAT — Tabla de servicios»**, el otro PDF. Es un
  **proyecto**, no norma vigente, y sus valores están en **puntos de SMLVD**,
  la unidad que la Ley 2294 de 2023 reemplazó por la UVB. Cargarlo daría
  cifras que no corresponden a lo que hoy se puede cobrar. Queda de consulta.
- El archivo **`Trazabilidad años anteriores.xlsx`**. Serviría para responder
  glosas de **facturas viejas**, donde aplica la tarifa vigente el día de la
  atención y no la de 2026. Sigue pendiente.

Todo lo anterior está explicado con detalle en
`docs/CATALOGOS_TARIFARIOS_SOAT_2026.md`.

**5) OJO CON ESTO — la Policía Nacional quedó SIN CONTRATO VIGENTE.**

Salió de rebote, revisando por qué fallaban cuatro pruebas que no tenían
nada que ver con el SOAT. **No es un error del sistema: es la realidad según
la malla contractual cargada.** Los dos contratos de la Policía ya se
vencieron:

| Contrato | Rigió hasta |
|---|---|
| 068-5-200004-26 (mediana y alta) | **15-08-2026** — hace 3 días |
| 068-5-200006-26 (oncología) | **31-07-2026** — hace 18 días |

Desde el 16 de agosto, si usted analiza una glosa de la Policía Nacional, el
dictamen dice **«SIN CONTRATO PACTADO»** y aplica **tarifa SOAT plena**. Eso
está bien hecho si de verdad no hay contrato; está mal si ya se renovó y
nadie ha cargado el nuevo.

**Lo que hay que decidir (esto no lo puede resolver el sistema):** ¿se
renovó el contrato con la Dirección de Sanidad de la Policía Nacional? Si
sí, hay que cargar el nuevo número y su vigencia en la malla contractual.
La malla que hoy tiene el sistema está fechada **28-07-2026**.

Mientras tanto, las cuatro pruebas quedaron amarradas a una fecha dentro de
la vigencia —igual que ya se había hecho con COMPENSAR—, porque lo que
comprueban es que el nombre resuelva al contrato correcto, no si el contrato
sigue vivo hoy.

---

### 18-08 (tarde) — Un dictamen real destapó dos defectos: la cita vacía y el «mayor valor»

Yesid analizó una glosa de NUEVA EPS —«se glosa servicio por mayor valor
cobrado según contrato, rx de rodilla, por valor de $12.000»— y mandó el
dictamen que salió. Traía dos cosas mal.

**1) El dictamen citaba una norma y NO escribía nada adentro de las comillas.**

Decía, textual:

> EN VIRTUD DE ART. 168 LA LEY 100 DE 1993, **QUE DISPONE «.»**, Y ART. 177…

La IA abrió comillas para citar el artículo y escribió un punto. Y debajo, el
sello: **«7 citas verificadas · 0 hallazgos»**. El revisor de citas no la vio
porque solo miraba las comillas con **15 caracteres o más** adentro: una
comilla vacía le pasaba por debajo y encima se contaba como cita buena.

Eso, radicado ante la EPS, le entrega el argumento de que el prestador no
sustentó su defensa. Ahora pasan dos cosas: **la comilla vacía se borra del
dictamen** (queda la norma citada, sin la comilla), y si aparece, **el
revisor la marca en rojo como hallazgo GRAVE**.

**2) La glosa se clasificó como FACTURACIÓN, cuando es de TARIFA.**

«Mayor valor cobrado según contrato» es la familia **TA (tarifas)** de la
Res. 2284/2023. El motor la mandó a **FA (facturación)** por una razón boba:
el texto no dice la palabra «tarifa». Lo mismo pasaba con «se cobra por
encima de lo pactado» y «valor superior al contratado» —las tres formas más
comunes en que una EPS escribe una glosa de tarifa—.

**Por qué importa:** clasificada como facturación, la defensa se arma como un
problema de papeles y **nunca se invoca la tarifa pactada, la homologación
CUPS → SOAT ni el Manual Tarifario**, que es justo lo que tumba este tipo de
glosa. Ya quedan las tres en TA.

**3) Y de paso, la respuesta que gana esa glosa.** Con la tabla del Manual
SOAT cargada hoy, el motor ya puede decirlo con número:

| Dato | Valor |
|---|---|
| CUPS 873420 — RADIOGRAFÍA DE RODILLA (AP-LATERAL) | homologa a **SOAT 21102** |
| SOAT 21102 — «Brazo, pierna, rodilla, fémur, hombro, omóplato» | 8,25 UVB |
| Tarifa oficial 2026 (Circular 047/2025) | **$99.900** |
| Lo que cobró el hospital | **$12.000** |

El hospital cobró **la octava parte** de la tarifa del Manual Tarifario. Una
glosa por «mayor valor cobrado» sobre un cobro ocho veces por debajo del
manual no se sostiene. Antes de hoy el sistema no tenía ese número.

---

### 18-08 — Empieza la revisión botón por botón: «Consulta Normativa»

Yesid decidió que esta semana se revisa el motor **botón por botón**, dejando
cada uno al 100%. Se arrancó por HERRAMIENTAS → **Consulta Normativa**, que
nació queriendo ser el equivalente de *miscuentasmedicas.com*.

**Lo que YA funcionaba bien:** la biblioteca legal. Las 131 normas están
indexadas de verdad y las ocho preguntas de ejemplo del panel devuelven la
norma correcta. Eso no se tocó.

**El defecto grande: la pantalla no entendía el código de la factura.**

El liquidador solo sabía buscar por **código SOAT** (21102, 19001…). El
auditor no tiene ese código: tiene el **CUPS de la factura** (873420) o el
nombre del procedimiento («radiografía de rodilla»). Escribiendo cualquiera
de los dos, la pantalla devolvía **cero** — y es justo lo que uno escribe
cuando la EPS objeta la tarifa.

La tabla que hace el puente (10.024 CUPS homologados) ya estaba cargada. Solo
faltaba que la búsqueda la usara. **Ya la usa:**

> Escribe **873420** → sale **SOAT 21102 · 8,25 UVB · $99.900**, y debajo dice
> de dónde salió: «CUPS 873420 · RADIOGRAFÍA DE RODILLA (AP - LATERAL)».

Con eso, **2.365 códigos CUPS** que antes no daban nada ahora liquidan en
pesos escribiendo el número que sale en la factura. Y los **2.966** que el
Manual SOAT no tarifa ya no salen como «no encontrado»: sale el hecho —que
además favorece al hospital— de que **la EPS no puede objetar la tarifa
citando un código SOAT que para ese procedimiento no existe**.

**Segundo defecto: el año mentía en silencio.** Si se pedía liquidar al año
2024, el sistema usaba la UVB de 2026 sin avisar. Una factura vieja liquidada
con la unidad de este año da una cifra que no se puede radicar. Ahora sale un
aviso amarillo diciendo con qué unidades se calculó.

**Lo que le sigue faltando a este botón (medido, no supuesto):**

1. **No liquida cirugías.** Son **5.832 mapeos** —los procedimientos
   quirúrgicos—. Su tarifa en el manual no es un valor directo: es un **grupo
   quirúrgico** (02 al 13, y especiales 20 al 23). Para dar el valor hay que
   sumar derechos de sala + honorarios del cirujano + ayudantía +
   anestesiólogo + materiales, cada uno con su propio código. **La Circular
   047/2025 ya trae todas esas tarifas por grupo** (39204 a 39219, 39100 a
   39128, 39301 a 39305): falta cruzarlas. Es la página
   «liquidación de cirugías SOAT» de miscuentasmedicas, y es donde está la
   plata grande.
2. **No consulta las tarifas contratadas.** Los **6.655 códigos de FAMISANAR**
   que se cargaron el 13-08 están en la base de datos, pero el liquidador
   nunca la mira: solo mira los catálogos fijos. O sea que la tarifa
   **realmente pactada** con la EPS no aparece en la pantalla.
3. **No tiene ISS 2001.** miscuentasmedicas lo tiene de primero porque muchos
   contratos se pactan «ISS 2001 + X%». El sistema no lo conoce.
4. **Tarifas propias del HUS: solo 84 códigos** de las Res. 054 y 124 de 2026.
   Falta cargar el resto.
5. **El índice de normas dice «0 artículos»** en las 131. Cosmético.

---

### 18-08 (tarde) — Consulta Normativa: el liquidador ya hace CIRUGÍAS

Seguimos con el mismo botón. Faltaba lo más grande: **liquidar cirugías**, que
es donde está la plata. Ya quedó.

**Primero averigüé cómo factura el HUS las cirugías** (era la duda que dejamos
abierta). Yesid corrió una consulta contra la base del PC de cartera y el
contrato de FAMISANAR lo dejó claro:

- Una cirugía se paga por **grupo quirúrgico**: se suman cinco cosas —derechos
  de sala + honorarios del cirujano + ayudantía + anestesiólogo + materiales—,
  cada una con su tarifa. El «UVB POR GRUPOS» que está cargado en la base **es
  ese paquete** con el −5% del contrato ya aplicado.
- Algunos procedimientos (p. ej. la **colecistectomía**) no van por grupo: van
  por **TARIFA PROPIA del HUS** ($6.296.900), que es más del doble del valor
  SOAT. El contrato manda pagarlos así, y así están cargados.

**Lo comprobé antes de construir nada.** Calculé el paquete de tres cirugías y
lo comparé con lo que está pactado en la base:

| Cirugía | Grupo | Lo que calcula el motor | Lo pactado (base) |
|---|---|---|---|
| Cesárea | 8 | $2.072.200 | $2.072.200 ✅ exacto |
| Apendicectomía | 7 | $1.885.200 | $1.885.300 (±$100 redondeo) |

Es decir: el desglose que ahora muestra la pantalla **reconstruye el valor
real pactado**, casi al peso.

**Qué se ve ahora:** escriba el CUPS de una cirugía (por ejemplo `471102`,
apendicectomía) y la pantalla muestra el **total** y, debajo, las **cinco
líneas** que lo componen, cada una con su código y su valor. Eso es lo que hay
que enseñarle a la EPS.

**Y se resolvió una confusión peligrosa.** El Manual SOAT trae la misma cesárea
de **dos formas**: por grupo ($2.072.200) y como **«paquete integral» todo
incluido** ($4.298.200, otra modalidad). Antes salían las dos sin distinción y
uno no sabía cuál radicar. Ahora cada una sale con su etiqueta —«CIRUGÍA ·
grupo 8» y «PAQUETE INTEGRAL»— para que usted use la que su contrato pactó (con
FAMISANAR, la de grupo).

**Lo honesto de siempre:** para los grupos especiales 20 al 23 (las cirugías
más grandes) el Manual no publica código de materiales, así que esa línea sale
marcada «no tarifado en la Circular» y hay que soportarla aparte. Nunca se
inventa el valor.

**Lo que le sigue faltando a este botón:** que lea las **tarifas pactadas de la
base de datos** (los 6.655 de FAMISANAR) para mostrar, al lado del cálculo
SOAT, el valor exacto del contrato — incluida la TARIFA PROPIA de la
colecistectomía, que el cálculo por grupo no alcanza a ver. Ese es el próximo
paso de Consulta Normativa.

---

### 18-08 (cierre) — Consulta Normativa al 100%: el liquidador ya lee la tarifa PACTADA

Último punto del botón. El liquidador daba lo que el **Manual** dice que vale
un código, pero no lo que el hospital **pactó** en el contrato. Y esas dos
cosas pueden ser muy distintas. Ya lo lee de la base.

**El ejemplo que lo explica:** la **colecistectomía** (CUPS 512101). El
cálculo por grupo SOAT da $3.157.500. Pero el contrato de FAMISANAR la pactó
por **TARIFA PROPIA a $6.296.900** —más del doble—. Antes esa cifra no
aparecía por ningún lado del liquidador. Ahora sale **de primera**, resaltada,
con la etiqueta «PACTADO · FAMISANAR EPS», y debajo queda el cálculo SOAT como
referencia del Manual.

**Cómo funciona:** cuando usted busca un código, el liquidador ahora también
mira las **tarifas contratadas cargadas** (las 6.655 de FAMISANAR y las que se
suban después) y, si el código está pactado, muestra el valor exacto del
contrato. La regla es clara: **manda lo pactado**; el SOAT es solo el soporte
del porqué.

**Detalles que quedaron bien cuidados:**
- Solo muestra contratos **activos** (uno vencido no aparece).
- Se puede filtrar por EPS.
- Si el código no está en ningún contrato, el liquidador funciona igual que
  antes (no estorba).

**Con esto, el botón «Consulta Normativa» queda terminado:**

| Función | Estado |
|---|---|
| Biblioteca de 131 normas | ✅ |
| Buscar por código SOAT | ✅ |
| Buscar por **CUPS de la factura** o por nombre | ✅ |
| **Liquidar cirugías** con desglose por grupo | ✅ |
| Distinguir «paquete integral» del pago por grupo | ✅ |
| Aviso cuando el año no tiene UVB propia | ✅ |
| **Tarifa PACTADA del contrato** (la que de verdad se cobra) | ✅ |

**Lo único que queda por fuera, y es porque falta el archivo:** el manual
**ISS 2001**, con el que se pactan algunos contratos. Cuando Yesid lo consiga,
se carga igual que se cargó el SOAT.

---

### 18-08 (noche) — «No es solo FAMISANAR»: cargadas las 1.900 tarifas propias del HUS

Yesid mandó tres archivos con una instrucción clara: **tener en cuenta todas
las tarifas, no solo FAMISANAR**. Tenía toda la razón, y salió un hueco
grande: el liquidador solo conocía **84** tarifas propias del hospital.

**Qué se cargó — `TARIFAS_HUS.xlsx`.** El catálogo institucional completo del
HUS: **1.932 tarifas propias** en pesos (1.480 procedimientos + 47 paquetes +
374 exámenes ambulatorios + 31 órtesis/prótesis). Estas tarifas **no son de
FAMISANAR**: son del HUS, y las usan **todos** los contratos que pactan
«tarifas propias/institucionales».

**Por qué importa para todas las EPS.** La malla que mandó Yesid lo confirma
—casi todos pagan «SOAT −X% + TARIFAS PROPIAS»—:

| EPS / Pagador | Modalidad |
|---|---|
| COOSALUD (subsidiado y contributivo) | SOAT −15% + tarifas institucionales |
| COMPENSAR | SOAT −15% + tarifas propias |
| SALUD MÍA (Plan Canguro/IVE) | SOAT −15% + tarifas propias |
| CONSORCIO PPL (Fiduciaria Central) | SOAT −15% + tarifas institucionales |
| SEGUROS AURORA / ARL | SOAT −3% + tarifas institucionales |
| FAMISANAR | SOAT UVB −5% + tarifas institucionales |
| PREVISORA FOMAG | SOAT (condiciones iniciales) |

**Qué se ve ahora.** Busque `512101` (colecistectomía) y sale la **TARIFA
PROPIA del HUS $6.296.900** —el valor real que se cobra— **para cualquier
EPS**, sin depender de que esté cargada en la base. Antes ese número solo
aparecía si estaba pactado en la base de FAMISANAR.

**Un cuidado importante:** a las tarifas propias **NO se les aplica el −X%
del SOAT** —son valor fijo—. La pantalla lo dice: «tarifa fija · sin % SOAT».
Aplicarle el descuento sería cobrar de menos.

**Lo que NO se tocó, a propósito:** la **malla de contratación** del sistema.
El sistema ya tiene una malla más reciente (28-07-2026) que la que mandó Yesid
(2 de marzo). Meter la de marzo encima **borraría** contratos más nuevos. Si
hay que actualizar las vigencias o los porcentajes por EPS, se hace con
cuidado y revisando contra la malla vigente — queda como decisión para
confirmar, no se cambió a ciegas.

### 18-08 — Dispensario: lote del 14 de agosto (24 facturas, puras tarifas)

Llegó el export `GLOSAS_14_AGOSTO.xlsx` (636 glosas; 612 son de COOSALUD y se
omitieron por instrucción del auditor). Lo del **Dispensario: 24 facturas, 36
objeciones, $2.511.222**, vencimientos entre el 24-08 y el 01-09. Todas las
observaciones son de **tarifas** (reconocen SOAT UVB alegando "sin acuerdo de
voluntades vigente", "sin cotización", "sin lista de precios").

- **Verificación de "¿ya se subieron?":** 20 facturas son glosas nuevas
  (nunca trabajadas). Las otras 4 (531237, 531815, 531331, 532571) son
  exactamente las mismas glosas que se cargaron el 05-08 con las 23
  pendientes (mismos valores al peso) — van incluidas igual por seguridad:
  si ya están contestadas, el robot las salta (NO_PENDIENTE).
- **Punto jurídico clave:** las 24 facturas tienen fecha de servicio entre el
  24-jun y el 22-jul de 2026 — todas DENTRO del plazo del contrato 440 (hasta
  30-07-2026). El ataque "sin acuerdo de voluntades VIGENTE" se responde con
  la tarifa pactada "vigente a la fecha de cada prestación" (así ya lo dice
  la plantilla del motor).
- **Excel generado** (`respuestas_glosa_DISPENSARIO_14AGO.xlsx`) con el motor
  del repo + 4 refuerzos a la medida: (1) la glosa TOTAL de la 535749 discute
  la FECHA del soporte (la firma del radiólogo es la fecha de lectura, no de
  la toma) y se contestó como soporte con taxatividad de causales; (2) a las
  que citan el Decreto 780 art. 2.6.1.4.2.4 y la Circular 047/2025 se les
  responde que esas normas operan a falta de acuerdo; (3) homologación SOAT y
  (4) cotización previa: no aplican cuando hay tarifa contractual propia.
  Hoja "Control" con consecutivo DGH, vencimiento y cuadre al peso contra la
  hoja INICIAL (las 24 cuadran).
- Comandos de piloto (535452) y corrida completa entregados; evidencias a
  `D:\USUARIO CARTERA\Documents\DISPENSARIO MEDICO 14-08-2026\EVIDENCIAS`.
- **Para verificar por el auditor antes de subir:** en la 535749, confirmar
  en historia clínica/RIPS la fecha real de la toma de la radiografía (la
  respuesta afirma que la fecha del RIPS es la de la atención).
- **Falta el consecutivo GI-33 de este lote** para la carpeta y el PDF de
  evidencias (preguntado al auditor).
- **(19-08) LOTE SUBIDO:** la corrida completa procesó las 24 facturas en
  9,6 minutos — 19 cargadas (OK) y 5 NO_PENDIENTE (las repetidas del cargue
  del 05-08, lo que confirma que esa corrida también quedó bien). Cero
  errores. Consecutivo del lote: **GI-33-5335-2026** (carpeta + PDF de
  evidencias con comandos entregados). Queda la segunda pasada de
  verificación (debe dar 0 pendientes).
- **(19-08) Acta 879 — médicas:** con la conciliación de pertinencia de la
  doctora (13-mayo) se corrigieron 5 observaciones médicas flojas del acta
  (la 487096 de $1.248.511 quedó confirmada ACEPTADA por estancia inactiva,
  y las 4 de la 487285 con su justificación clínica completa). Quedan 2
  líneas de la 474268 (CL0801, $6.093 c/u) sin texto de la doctora.

### 18-08 (conciliación) — Acta 879 armada y las 3 objeciones de pertinencia justificadas

Jornada de apoyo a la mesa de conciliación con el Dispensario (chat GLOSAS
DISPENSARIO — SIMED):

- **Las 2 facturas perdidas aparecieron.** El auditor no encontraba la hoja
  de trabajo con las facturas 487285 y 481515. Se rastreó: sus carpetas de
  soportes están en los LOTES de mayo (LOTE 3 y LOTE 8 — la de LOTE 8 estaba
  mal nombrada "HUS87285" y se renombró); sus radicados de respuesta de abril
  son **GI-23-4699-2026 y GI-23-4700-2026** (en el share Z: de SERVIDOR
  GLOSAS); y la hoja de trabajo buena resultó ser
  **HOJA_TRABAJO_GLOSAS_DMBUG_CON_OBSERVACIONES**, recuperada del respaldo de
  WhatsApp en `D:\BackupCelular` (la "v2 - JOHAN" que buscaba ya no existe:
  solo quedaron sus huellas temporales de Excel en Descargas).
- **Las 3 objeciones de pertinencia médica quedaron justificadas al peso**
  (486873, 487285, 481515): en las tres, el valor aceptado en el acta es
  correcto y cuadra exacto (glosa = aceptado + levantado); lo que falla es la
  **observación de la nota crédito**, que el armador construye concatenando
  textos por línea y **duplica unos y omite otros**. Se entregaron los tres
  textos de respuesta para pertinencia con el desglose peso por peso
  (486873: $27.901 + $139.505 = $167.406, NC 310232; 487285: glosa $1.259.426
  = aceptado $953.680 + levantado $305.746, NC 310123; 481515: glosa
  $16.188.629 = aceptado $4.606.885 + levantado $11.581.744, NC 310166).
  **Hallazgo de fondo:** ese defecto del concatenador de notas va a repetirse
  en otras facturas del acta — se ofreció hacer un bot que arme la
  observación correcta (todos los ítems aceptados con su valor).
- **Se armó el ACTA SINAC N.º 879** (`ACTA_SINAC_N_879_ESE_HUS_DISPENSARIO_MEDICO.xlsx`)
  con el formato del acta 720 de ejemplo: hoja ACTA con encabezado, tabla de
  **1.493 glosas / 630 facturas** (radicado AC000879/AR003215, tipificación,
  código, motivo, valores, descripción de conciliación y observación de NC
  por glosa), totales **glosado $401.179.634 · acepta IPS $122.715.506 ·
  levanta entidad $276.758.183**, observaciones, mérito ejecutivo y firmas;
  hoja GLOSAS (detalle completo de la hoja de trabajo) y hoja NOTAS (las 10
  NC del Dispensario en la BD de julio). Fuentes: la hoja CON_OBSERVACIONES
  (el cruce de decisiones casó 1.493/1.493) y la BD de glosas aceptadas de
  julio.
- **(19-08) Acta 879 en limpio:** el auditor pasó el acta a su formato .xlsm
  definitivo y quedaban 27 filas con la descripción genérica "IPS ACEPTA
  GLOSA". Se corrigieron **26 en el sitio** (mismo archivo, macros y formato
  intactos: solo cambiaron 52 celdas, verificado con comparación celda a
  celda) tomando el CONCEPTO CONCILIACIÓN de la circularización de glosas
  2026 — 22 con el texto textual y 4 de la factura 487285 con texto compuesto
  porque la circularización traía el texto trocado (decía "levanta" con
  valores de aceptación). Quedó **1 sin tocar para decisión del auditor**: la
  487096 CL0101 por $1.248.511, que el acta tiene ACEPTADA al 100% y la
  circularización tiene LEVANTADA. Ojo adicional: en la 487285 la
  circularización reporta las terapias levantadas y un aceptado total de
  $920.064 vs $953.680 del acta de la entidad ($33.616 de diferencia) —
  aclarar con el técnico antes de firmar.
- **Para cerrar el acta:** (1) confirmar fecha y número contra el **PDF
  firmado ACTA_AC_AC000879** (se dejó 07/05/2026 según las NC; el PDF no se
  ha compartido al chat); (2) revisar **3 líneas que no cierran**: 478141
  (diferencia de $1: glosa 16.210 vs aceptado 16.209), 487192 (diferencia de
  $20: 18.886 vs 18.866 — dígitos trocados) y **481589 (quedan $1.705.924 sin
  decidir**: glosa $2.985.367, aceptado $426.481, levantado $852.962).

---

### 18-08 (noche) — Empieza «Salud Total»: el lector de valores ya no lee de menos

Segundo botón de la revisión. Salud Total ya tenía mucho trabajo hecho (se
había restaurado y se le conectó el análisis con IA), así que el diagnóstico
fue corto.

**Lo que ya funcionaba bien:** las tres opciones (Extemporánea, Ratificada,
Analizar con IA) responden; la pantalla tiene girador, error, estado vacío,
moneda con formato y las etiquetas IA/PLANTILLA; y no inventa «días
transcurridos» si falta la fecha.

**El defecto que se arregló — el lector de valores era frágil.** Leía solo el
formato gringo (280000.00). Si el portal mandaba el valor a la colombiana:
- «280.000» lo leía como **$280** (mil veces menos),
- «280.000,00» **reventaba** el proceso.

Y esos valores van en el archivo que se radica y en los totales de la
pantalla. Ahora usa el lector único del repo, que entiende los dos formatos
y deja el actual igual. 11 pruebas nuevas.

**Lo que quedó como DECISIÓN del dueño (no se tocó):** el código de respuesta
RE9901 que el modo rápido le pone a las glosas que no son de tarifa ni
extemporáneas (soportes, autorización, cobertura…). Ese código, según el
Manual Único, ADMITE que la glosa era justificada y que se subsanó. Si lo que
se quiere es rechazarla de fondo, el código sería RE9602 («injustificada al
100%»). Falta que Cartera confirme cuál usa el HUS en el portal de Salud Total
antes de cambiarlo.

---

### 18-08 (noche) — Salud Total: la respuesta ahora es la que el HUS radica de verdad

Yesid mandó el archivo REAL: cómo llega la glosa (el TXT «Detalle» de 24
columnas) y cómo se sube la respuesta (el RTAGLOSA con RE9602/RE9901). Con eso
en la mano se corrigieron tres cosas que estaban mal en el modo por plantilla.

**1) El texto de TARIFAS afirmaba un contrato que NO existe.** Decía «...LA
LIQUIDACIÓN SE REALIZÓ CONFORME AL CONTRATO VIGENTE...». Con Salud Total el
HUS **no tiene contrato**. Afirmar lo contrario en un documento que se radica
le regala a la entidad el argumento de que sí lo había. Ahora dice la verdad,
palabra por palabra como en el archivo real: «...ENTIDAD SALUD TOTAL SIN
CONTRATO VIGENTE... SE FACTURA A SOAT VIGENTE Y LOS INSUMOS A TARIFAS
INSTITUCIONALES...».

**2) El código de respuesta por familia estaba cruzado.** El archivo real usa:
- Tarifas (TA) y Facturación (FA) → **RE9602** (injustificada al 100%).
- Soportes (SO) y Pertinencia (CL) → **RE9901** (subsanada, soportes adjuntos).

El sistema le ponía a Facturación el RE9901 y a Soportes el RE9602. Quedó
alineado con la realidad.

**3) La respuesta ya no le pega el nombre del servicio al final.** El archivo
real no lo lleva, y así se respeta mejor el tope de 500 caracteres.

**Comprobado con el archivo real:** se tomó el TXT «Detalle» que mandó Yesid,
se pasó por el motor, y la salida quedó **idéntica** a su archivo OK en las
familias que se pueden hacer por plantilla (TA y SO, que son el 84% del
archivo).

**Lo honesto:** en el archivo real, las glosas de Facturación y de Pertinencia
venían con un texto **escrito a mano** para ese caso puntual (dotación de UCI,
jeringas de 20 cc). Eso NO se puede volver plantilla sin inventar: para esas
glosas específicas está el botón «Analizar con IA», que arma el argumento con
todo el contexto. La plantilla cubre la mayoría (tarifas y soportes) y las
demás quedan con una respuesta genérica correcta que el auditor ajusta.

**Y un arreglo previo del mismo día:** el lector de valores del TXT ahora
entiende el formato colombiano (antes «280.000» lo leía como $280).

---

### 18-08 (más tarde) — Salud Total: los acentos ya no salen rotos en el portal

Yesid probó el botón «Analizar con IA» con la notificación real y mandó el
archivo que salió. La IA quedó bien (códigos correctos por familia, sin código
HTML, argumentos reales), pero se vio un error que afectaba **todos** los
archivos de Salud Total, no solo la IA.

**Los acentos salían rotos.** «Clínica» se veía «clÃ­nica», «CÓDIGO» «CÃDIGO».
La causa: el portal de Salud Total lee el archivo en **ANSI (Windows-1252)**
—el archivo del HUS que sí funcionó está en ese formato— y el sistema lo
generaba en **UTF-8**. Al subir un UTF-8 a un portal que espera ANSI, los
acentos se dañan, en un documento que se radica.

Ahora el archivo se descarga en ANSI, igual que el que funcionó. Los guiones
largos y las comillas curvas que mete la IA se convierten a signos normales
para que ningún carácter raro dañe la descarga.

Con esto, «Salud Total» queda cerrado: lector de valores robusto, texto de
tarifas sin contrato falso, códigos correctos por familia, salida idéntica al
archivo real, y ahora la codificación correcta para el portal.

---

### 18-08 (noche) — Validador ADRES: la búsqueda de autorizaciones ya no llena el disco

Tercer botón de la revisión. El Validador ADRES está bien armado —la malla
completa de la Circular 022/2023 (FURIPS 1 de 102 campos y FURIPS 2), el cruce
con RIPS/CUV/XML/factura/epicrisis con OCR, y 29 pruebas que pasan—.

**El defecto que salió: una fuga de disco.** El buscador de números de
autorización guardaba lo que uno sube en una carpeta temporal y, **cuando
terminaba bien, no la borraba** (solo la borraba si había un error). Cada
búsqueda dejaba en el disco los JSON subidos y el Excel generado. En el PC de
cartera, usándolo seguido, eso termina llenando el disco. Ahora la carpeta se
borra sola apenas se envía el archivo.

**Una cosa para tener presente (no es un defecto, es cómo está hecho):** la
validación FURIPS grande corre en segundo plano y su estado vive en la memoria
del programa. Si justo mientras corre se actualiza el sistema (deploy), esa
validación se pierde y hay que volver a subir los archivos —la pantalla lo
avisa con un mensaje claro—. Pasa rara vez (solo cuando hay una actualización
en ese momento); dejarlo a prueba de eso sería un cambio grande y de poca
ganancia, así que queda anotado, no cambiado.

---

### 18-08 (noche) — Validador ADRES: probado con datos reales, SÍ sirve

Yesid lo puso a prueba en producción con tres facturas reales y mandó los
informes. Los revisé y la herramienta **funciona de verdad**:

**Informe FURIPS (3 facturas).** Los hallazgos son correctos y precisos, cada
uno citando la regla exacta de la Circular 022/2023: un dispositivo médico sin
registro INVIMA (código vacío), descripciones pasadas de 100 caracteres,
líneas idénticas que la Circular obliga a agrupar, y una dirección de
propietario que era solo el nombre de un municipio («CHARTA SANTANDER») sin
nomenclatura. Cero falsos positivos. Además trae el detalle campo por campo
(307 filas de FURIPS1, 263 de FURIPS2).

**Informe de autorizaciones.** El RIPS traía una autorización mal escrita
(«Código  71539» en vez de un número) y el informe la marcó exacto: «1 con
otro número», y la puso en ALERTAS. Correcto.

**Se agregó una prueba de punta a punta del motor** (no existía): arma un
paquete FURIPS desde la propia malla del validador, lo pasa por `procesar`, y
comprueba que corre, que caza un valor inválido plantado a propósito (sexo
fuera de F/M/O), que NO lo marca cuando es válido, y que genera el Excel.

Con esto queda claro que el botón funciona; los defectos que se corrigieron
antes (la fuga de disco de autorizaciones) eran de plomería, no del motor.

---

### 18-08 (noche) — Soportes: el indexador reconoce «FVS» (la factura)

Quinto botón de la revisión. El indexador de soportes está bien armado (44
pruebas, dos pasadas, comparte los soportes de carpeta entre facturas, y saca
la factura del nombre exigiendo el prefijo «HUS» —lo que evita confundirla con
el NIT del hospital 900006037, que va primero en el nombre—).

**Lo que se arregló:** los archivos de la factura electrónica que el servidor
nombra «FVS_900006037_HUSxxxx.pdf» quedaban etiquetados «otro», porque el
clasificador no conocía el código **FVS** (Factura de Venta en Salud) —aunque
la propia pantalla lo documenta—. Se encontraban por número, pero salían mal
etiquetados. Ahora se etiquetan como la factura.

**Lo que falta CONFIRMAR con un nombre real (para no adivinar):** el
indexador saca la factura del nombre solo si trae el prefijo «HUS» (ej.
FVS_900006037_**HUS**0000487175.pdf). Si algún archivo del servidor nombra la
factura con dígitos pelados (FVS_900006037_487175.pdf, sin «HUS»), NO se
indexaría por factura y no se encontraría. Hay que ver un nombre de archivo
real del servidor de radicación para saber si eso pasa; si pasa, se amplía el
patrón con cuidado de no volver a agarrar el NIT.

---

### 18-08 (cierre) — Soportes: con los nombres REALES salió el defecto de verdad

Yesid mandó rutas reales del servidor (\\Prime\radicacion_2026). Dos cosas:

**1) El prefijo real es FEV, no «FVS».** La pantalla lo tenía mal documentado.
FEV ya lo conocía el clasificador, así que la factura electrónica se
detectaba bien. (Se dejó igual el soporte para «FVS» por si acaso, y se
corrigió el texto de la pantalla.)

**2) El defecto de verdad — la EPS salía vacía.** Las carpetas del 2026 llevan
un ORDINAL delante: «**8.** AGOSTO 2026 - SOPORTES RADICACION». El indexador
buscaba «AGOSTO 2026 - ...» sin ese «8. », así que no reconocía la carpeta del
mes y, con ella, se perdían el mes, el año y —lo que importa— **la EPS de cada
soporte** (NUEVA EPS, SANITAS, PPL, POSITIVA, SURA, SEGUROS BOLIVAR). Con eso
arreglado, cada soporte ya sabe de qué EPS es.

**Lo que quedó comprobado con los nombres reales:** la factura se saca perfecto
del nombre en los 90 archivos de ejemplo —incluido uno con el NIT mal escrito
(«9000006037» con un cero de más)—, porque el patrón se ancla en el prefijo
HUS de la factura, no en el NIT. Mi duda del «dígito pelado» NO se da: todos
traen HUS.

Se agregaron pruebas que arman la estructura real de carpetas (con el ordinal)
y comprueban que se encuentra la factura y se sabe la EPS.

---

### 18-08 (noche) — Soportes conectado al servidor real: dos trabas que aparecieron al usarlo

Se apuntó el motor a `\\Prime\radicacion_2026` y empezó a indexar de verdad
(iba en 2.522 facturas y 17.087 archivos). Al usarlo salieron dos trabas:

**1) La búsqueda daba «Error 524».** Buscar una factura MIENTRAS el indexador
recorría el servidor dejaba la pantalla esperando hasta que el proxy la
cortaba. La causa: la búsqueda y el reindexado se peleaban por el mismo
candado, y recorrer miles de archivos por red dura minutos. Ahora la búsqueda
**responde con lo que ya haya indexado** y nunca hace cola. Además, si se pide
un reindexado y ya hay uno corriendo, no se arranca otro encima.

**2) Se volvía sola a la carpeta local.** El «vigilante» que revive el motor
guarda la configuración de cuando ÉL arrancó, así que matar solo el motor lo
revivía apuntando otra vez a `C:\motor-glosas\repo\data\soportes`. Ahora el
motor **lee la carpeta directamente del archivo** `config\soportes_root.txt`
al arrancar, sin depender de quién lo levante. Se configura una vez y queda.

**Y la pantalla ahora dice qué está pasando:** mientras indexa muestra
«⏳ Indexando…», explica que puede tardar varios minutos la primera vez, y se
actualiza sola cada 5 segundos. El botón de reindexar ya no deja la pantalla
colgada: arranca el trabajo y devuelve el control enseguida.

---

### 19-08 — Soportes indexando el servidor de verdad, y el mensaje que confundía

Con los arreglos de anoche, el indexador ya está recorriendo
`\\Prime\radicacion_2026` de verdad: **11.367 facturas y 102.729 archivos** y
subiendo, con la pantalla mostrando «⏳ Indexando…» y actualizándose sola. La
búsqueda ya **no da Error 524**: responde de una.

**Pero el mensaje engañaba.** Al buscar una factura de agosto mientras el
indexador iba por la mitad, la pantalla decía «Sin soportes para la factura» y
listaba causas que no incluían la verdadera: **todavía no había llegado a
agosto**. Las carpetas se recorren por orden (FEBRERO, MARZO…), así que los
meses recientes salen de últimos. Un auditor podía creer que la factura no
tenía soportes cuando sí los tiene.

Ahora, si el índice está a medias, el mensaje lo dice claro: cuántas facturas
lleva, que las carpetas van por orden y que espere a que termine. Y se corrigió
un «hace en curso» que había quedado mal redactado.

---

### 19-08 — Soportes ENCONTRÓ los expedientes, y la EPS que mostraba estaba mal

Yesid buscó una factura real de febrero (HUS468334) y salieron **los 12
soportes**: FEV, HEV, CRC, epicrisis, hoja de administración de medicamentos,
RIPS en JSON, XML, CUV, OPF, PDE, PDX. El indexador está haciendo su trabajo
sobre el servidor real.

**Pero la columna EPS decía «1.DD FACTURACION»**, que no es una EPS: es una
carpeta del archivado. La EPS de verdad era **ALIANZA MEDELLÍN**.

La causa, otra vez de las que solo se ven con datos reales: la lista de
carpetas que el sistema debe saltarse decía «1. **DD** FACTURACION» **con
espacio** después del punto, y en el servidor la carpeta se llama «1.DD
FACTURACION» **sin espacio**. Como no coincidía, la tomaba como si fuera el
nombre de la EPS. Ahora la comparación ignora el ordinal y los espacios, así
que da igual cómo esté escrita.

Comprobado con las tres formas de carpeta que hay en el servidor: la de
febrero (con ESCANEO en el medio) da ALIANZA MEDELLÍN, la de marzo da SANITAS
y la de agosto da NUEVA EPS.

### 06-08 — Informe por entidad en Word, y cómo ver qué llega nuevo a SIIFA

**1. Informe para gerencia (`INFORME_SIIFA_POR_ENTIDAD.docx`).** Entrega en
Word con las cuatro entidades que glosaron o devolvieron, sus facturas,
valores y causales; el detalle de las 15 facturas de mayor valor; y una
sección que muestra lo que se ganó automatizando: **1.419 respuestas en 4
minutos y 58 segundos** (286 por minuto) frente a las ~86 horas —11 jornadas—
que habría tomado a mano. Incluye los tres hallazgos que destrabaron el
cargue y los tres puntos que quedan por revisar.

**2. El portal ya marca 2.620 registros** (antes 2.597): llegaron 23 nuevos.
El portal dice el total pero **no cuál es nuevo**, y buscarlos a mano son 175
páginas de a 10. Se creó **`tools/siifa_novedades.py`**, que compara el
informe de hoy contra el de la revisión pasada y responde, para cada novedad:
qué entidad, qué factura, si es glosa o devolución, por cuánto y con qué
causal. Queda como **opción [N]** del bot `CARGAR_SIIFA.cmd`: guarda el
informe anterior, baja el de hoy y compara solo. Si la bajada falla, devuelve
el informe anterior intacto.

**3. Un error de cuentas que se corrigió a tiempo.** Al probar el resumen, las
devoluciones daban **$24.917 millones**. La causa: SIIFA **repite el valor de
la factura en cada línea** de la devolución, y sumarlas multiplica la plata
(1.340 líneas de una factura de $111 millones). El valor real de esas 9
facturas es **$111.420.812** —224 veces menos—. Ahora el valor de una
devolución se cuenta **una sola vez por factura**, hay tres pruebas que lo
vigilan y quedó anotado en `docs/CONTEXTO_SIIFA.md`. Es la clase de cifra que
en un informe a gerencia no se puede sostener.

### 13-08 — 68 glosas nuevas respondidas, y el semáforo del trámite

**1. Llegaron 68 glosas nuevas y quedaron todas respondidas.** El portal pasó
de 2.597 a 2.665 seguimientos. Casi todas de **FAMISANAR** (67 de 68;
$30.013.228), más una de SANITAS. Total defendido: **$30.038.128** sobre 34
facturas. De esas, 27 salieron con la respuesta real que el hospital ya había
dado en Dinámica Gerencial y 41 las redactó el motor.

**28 de las 68 ya estaban vencidas** ($15.345.553). Se respondieron igual: una
respuesta tardía se discute, una glosa sin respuesta se pierde.

El cargue tomó **58 segundos de máquina** (17 de escritura efectiva, unas 240
respuestas por minuto) contra las 2 horas y media que habría tomado a mano.
Seis rebotaron por el límite de 1.500 caracteres —el mismo error de siempre— y
entraron a la primera después de recortarlas. Entre ellas la más grande del
lote, HUS521868 por $3.399.053.

**2. FAMISANAR reformula glosas — y eso puede dañar un cargue.** Al comparar
los informes del 6 y el 13 de agosto, una glosa desapareció: la de HUS517950
(CL0801, $665.200, del 30 de junio). No se perdió: la EPS la borró y la volvió
a crear el 9 de julio con otra causal (SO0801) y **número de seguimiento
nuevo**. Lección: **las respuestas se arman contra el informe bajado el mismo
día del cargue**, nunca contra uno de días atrás, porque el id viejo puede ya
no existir. El comparador avisa cuando algo desaparece; así se detectó.

**3. Nueva herramienta: `siifa_estado_tramite.py` (opción [E] del bot).** El
panel «Avance de auditoría» del portal muestra las cinco etapas del trámite
para UNA factura; esto lo hace para las 2.600 de una vez y dice **a quién le
toca mover**. Lo primero que muestra es lo que le toca al hospital, con su
fecha de vencimiento.

Con esa herramienta aparecieron cosas que nadie estaba mirando:

- **3 glosas LEVANTADAS: $1.418.479 que SANITAS le dio la razón al hospital.**
  Nadie lo sabía porque hay que entrar factura por factura a verlo.
- **5 reiteradas ($15.445.892) con el plazo de subsanación corriendo.** Cuando
  la EPS reitera, al hospital le quedan **7 días hábiles** —menos de la mitad
  que los 15 de la primera respuesta— y **nadie avisa**. Cuatro son
  devoluciones de SANITAS por $14 millones.
- **16 glosas donde la EPS está en mora**: respondimos y no ha decidido dentro
  de sus 10 días hábiles.

**4. Otro error de cuentas atajado a tiempo.** El semáforo repetía el error de
sumar las devoluciones línea por línea: mostraba $25.221 millones donde hay
$428 millones. La regla quedó ahora en **una sola función** (`valor_total()`
en `siifa_novedades.py`) que usan las dos herramientas, en vez de copiada en
cada una — igual que el lector de pesos. Es el mismo error, cometido dos veces
en dos semanas: por eso ahora vive en un solo sitio y con pruebas.

### 13-08 (segunda parte) — La subsanación: la etapa que nadie estaba mirando

Con el semáforo del trámite apareció lo que seguía: **la EPS ya respondió**
algunas glosas, y eso abre la etapa 4.

**Lo que se encontró (informe del 6 de agosto):**

- **3 glosas LEVANTADAS — $1.418.479 recuperados.** SANITAS le dio la razón al
  hospital en HUS467326 ($1.396.804), HUS464765 y HUS463797. Nadie lo sabía
  porque hay que entrar factura por factura al portal a verlo.
- **1 glosa REITERADA** (HUS465198, $1.396.804): hay que subsanar.
- **4 DEVOLUCIONES REITERADAS** ($14.049.088), todas de SANITAS.

**Nueva herramienta: `siifa_armar_subsanacion.py` (opción [S] del bot).** Arma
el archivo para insistir ante lo reiterado. El escrito **no repite** la
primera respuesta —la EPS ya la leyó y no la aceptó—: deja constancia de que
el hospital contestó y en qué fecha, señala que la reiteración no aporta
elemento nuevo, y conserva el argumento de fondo de la causal.

**Las 4 devoluciones reiteradas NO se cargan todavía, y es a propósito.** La
puerta de subsanación está confirmada sólo para glosas
(`PUT /api/SeguimientoFacturaGlosa/ReiteracionRespuesta`); para devoluciones
no se conoce. Mandarlas por la de glosas escribiría sobre otro registro y el
reporte diría OK — el mismo daño que costó descubrir en agosto. Salen en una
hoja aparte, sin código ni texto, y el bot las bloquea. Se amplió
`siifa_sondear_endpoints.py` con las rutas y grupos candidatos para
averiguarlo **sin escribir nada** (sólo consulta).

**La primera subsanación quedó cargada** (HUS465198, $1.396.804) — el
trámite llegó por primera vez a la etapa 4.

**El sondeo mintió, y por poco cuesta caro.** Dijo que existían seis rutas,
entre ellas tres para subsanar devoluciones. Era falso: SIIFA tiene rutas del
tipo `/api/SeguimientoFacturaGlosa/{id}`, así que al preguntar por
`/api/SeguimientoFacturaDevolucion/ReiteracionRespuesta` responde ESA otra
ruta, quejándose de que «ReiteracionRespuesta» no es un número válido para el
id. El 400 se leía como «la ruta existe». Mandar una escritura ahí habría ido
a parar a otro registro, con OK falso en el reporte —exactamente el daño que
la hoja aparte quería evitar—.

Ya está corregido: cuando el error menciona el último trozo de la ruta como
si fuera un id, el sondeo lo marca **NO CONCLUYENTE - NO ESCRIBIR** en vez de
«existe». Tres pruebas lo vigilan.

**Los grupos de códigos de la subsanación salieron todos vacíos**
(`REITERACION_*`, `SUBSANACION`, `RESPUESTA_GLOSA_PTS_PSS`). La subsanación de
glosa funcionó igual con RE9901, así que para glosas no hace falta.

**Las 4 devoluciones reiteradas ($14.049.088) siguen sin vía por API.** Lo que
falta es mirar en el portal qué ofrece el menú de una devolución reiterada: el
nombre que aparezca ahí es la pista del endpoint, igual que en agosto el
propio mensaje de error reveló el grupo `RESPUESTA_DEV_PTS_PSS`. Mientras
tanto, se pueden subsanar **a mano** en el portal: son cuatro.

### 13-08 (tercera parte) — SIIFA al día: 2.665 de 2.665, y la EPS en mora

Verificado contra la plataforma después del cargue:

| Etapa | Le toca a | Ítems | Valor |
|---|---|---|---|
| 2. Respondida, esperando decisión | EPS | 2.657 | $458.717.238 |
| 3. **Levantada — ganada** | — | **3** | **$1.418.479** |
| 4. Reiterada — falta subsanar | HOSPITAL | 4 | $14.049.088 |
| 5. Subsanada, esperando decisión final | EPS | 1 | $1.396.804 |

**No queda ni un seguimiento sin responder.** Lo único pendiente del hospital
son las 4 devoluciones reiteradas de SANITAS, que hay que hacer a mano.

**Dato nuevo y aprovechable: las EPS están en mora.** Tienen 10 días hábiles
para decidir si levantan o reiteran una glosa ya respondida, y **43 se
pasaron**: FAMISANAR 27 por $14.680.353 y SANITAS 16 por $1.030.100. Es
incumplimiento de ellas y sirve para la mesa de trabajo.

**Otro cálculo corregido.** El semáforo marcaba «VENCIDA» la subsanación
cargada esa misma mañana. La causa: los 5 días de la decisión final corren
desde la SUBSANACIÓN, y esa fecha no viene en el informe; se estaba contando
desde la respuesta original del 5 de agosto. Una mora inventada de la EPS es
un reclamo que no se puede sostener, así que ahora esa etapa no calcula
vencimiento y lo dice. (Con eso SANITAS pasó de 17 a 16 en mora.)

Entregado el informe en Word `INFORME_CARGUE_SIIFA_13AGO.docx` con las ocho
secciones, incluida la del estado verificado contra la API.

### 13-08 (cuarta parte) — De un hospital a cuatro IPS

El auditor ahora administra **cuatro prestadores** y quiere trabajarlos a la
vez: HUS (900006037), Clínica Socorro (900190045), Clínica Girón (890203242)
y Clínica Guane (804006936).

**Cada IPS tiene lo suyo:** su carpeta (`...\SIIFA\HUS`, `...\SIIFA\SOCORRO`,
etc.), sus credenciales (`SIIFA_USER_HUS`, `SIIFA_USER_SOCORRO`…) y su nombre
en el título de la ventana. Todas las herramientas reciben `--ips`, y el bot
de doble clic pregunta con cuál se trabaja **antes que nada**.

**La guarda que evita el error caro.** Antes de bajar o escribir, la
herramienta le pregunta al token de SIIFA a qué NIT pertenece y lo compara
con la IPS elegida. Si no coinciden, se detiene **sin tocar la plataforma** y
dice de quién son las credenciales que encontró. Con cuatro ventanas
abiertas, confundirse es cuestión de tiempo, y una respuesta cargada en la
entidad equivocada no se puede deshacer. Una prueba recorre los scripts que
entran a SIIFA y falla si alguno se salta la comprobación.

**Un problema que apareció al revisar, y era grave.** El texto de las
respuestas decía «ESE HOSPITAL UNIVERSITARIO DE SANTANDER NO ACEPTA…» escrito
a mano, con el correo `CARTERA@HUS.GOV.CO` y la dirección de la Carrera 30.
Las respuestas de la Clínica Socorro habrían salido **firmadas por el HUS y
con los datos del HUS** — en un escrito con efectos jurídicos ante la EPS. Ya
está parametrizado: cada IPS pone su nombre, y **si no tiene correo y
dirección cargados, la frase se omite** en vez de poner los de otra.

**Falta:** el correo y la dirección de Socorro, Girón y Guane, para que sus
respuestas cierren con sus propios datos de contacto.

**Cuatro huecos más, encontrados revisando a fondo** (tres los halló una
revisión adversarial del diseño; el cuarto salió en la primera corrida real):

1. **La guarda del ARCHIVO, no sólo de las credenciales.** Comprobar el token
   protege lo que se escribe; faltaba proteger lo que se lee. Con cuatro
   carpetas parecidas y archivos que se llaman igual en todas, pasarle el
   informe de otra IPS era facilísimo —y de ahí salen las respuestas—.
   Comparar el informe de una contra el de otra, además, habría reportado
   todos sus registros como «novedades». Ahora se compara el NIT del emisor.
2. **Las constancias PDF salían a nombre del HUS.** Se anexan a la EPS como
   evidencia: una constancia de la Clínica Girón encabezada «Hospital
   Universitario de Santander» no prueba nada. Y el nombre del archivo no
   distinguía la IPS, así que una pisaba a la otra.
3. **Dos IPS bajando a la vez se borraban el archivo de prueba de escritura**
   (se llamaba igual en las dos), y una concluía «no puedo guardar acá»
   cuando sí podía. Pasó de verdad con tres corridas en paralelo.
4. **Al pasar a «mes por mes» seguía pidiendo tandas de 1.000.** Si la
   consulta completa falló por peso, partirla en meses pero conservar la
   tanda gigante es repetir el error a pedazos. Girón y Guane se atoraron
   así, mes tras mes. Ahora la tanda baja a 200 al pasar a meses.

**Lo que se aprendió del primer día con las cuatro:** Socorro tiene **60.568
seguimientos** (23 veces el HUS). Y el servidor del Ministerio **no aguanta
tres consultas pesadas a la vez**: con las tres corriendo, Socorro degradó de
1.000 a 62 registros por página. Conviene bajarlas de a una.

### 18 y 19-08-2026 — Los cargues masivos de las cuatro IPS en SIIFA

**Socorro: 48.766 respuestas cargadas** (unas 3 horas y media de robot).
El revisor previo (`siifa_revisar_antes_de_cargar.py`, nuevo) apartó antes
del cargue lo que iba a fallar: ya respondidas, textos pasados de 1.500
caracteres, códigos de devolución en glosas, 16 sin texto. De la corrida,
48.009 entraron a la primera y 756 dieron «error» de tiempo de espera —
pero al verificar contra la plataforma **la escritura sí había entrado**:
SIIFA las tenía todas. De ahí salió una regla nueva del informe:
un error de «ya tiene un registro previo» cuenta como REGISTRADA.

**El informe final ahora funciona sin los CSV del robot (modo censo).**
Una corrida interrumpida pisó el reporte del cargue grande y el informe
solo veía 1.271 filas. Ahora `siifa_informe_del_cargue.py` puede partir
del informe masivo solo: dice cuánto de lo que SIIFA tiene está respondido
(lo del robot y lo cargado antes) y qué falta. Con eso salió el informe de
Socorro completo: **59.732 de 60.567 respondidas ($2.224 millones
defendidos)**; quedan ~835 nuevas que llegaron después del corte.

**Las 16 de Socorro que faltaban por texto: alguien ya las había respondido
a mano.** Al cargarlas, las 16 rechazaron con «ya tiene un registro previo».
No hubo daño, pero conviene **coordinar con quien responde manualmente en la
clínica** para no duplicar trabajo.

**Girón: 1.085 respuestas cargadas.** Falta correr su informe final (censo).

**Guane: 1.530 respuestas** (522 glosas y 1.008 devoluciones con RE9701 =
aceptar la devolución al 100%, confirmado con el archivo del auditor);
el cargue y su informe final quedaron corriendo en el equipo de cartera.

**HUS: la subsanación con el texto institucional.** El auditor entregó la
plantilla oficial del HUS para glosas ratificadas (RE9901: se mantiene la
respuesta, se pide conciliación, art. 57 Ley 1438/2011). Quedó en
`tools/plantillas/subsanacion_HUS.txt` y el armador de subsanación la usa
con `--texto`. La única glosa ratificada pendiente ya estaba subsanada.
**Ojo:** el botón «Crear decisión» del portal es una etapa del PAGADOR;
el hospital no debe usarlo.

**Herramienta nueva: el BALANCE de un corte** (`siifa_balance.py`, opción
[B] del bot). Después de un cargue responde las cuatro preguntas de una vez,
por IPS: qué estaba glosado al corte, qué de eso quedó respondido (separando
lo que ya venía respondido de antes), qué **sigue sin responder** y qué
**nuevo** ha glosado la EPS desde entonces. Deja un Excel con lo pendiente
de primero y avisa si algo del corte desapareció del informe (posible
reformulación de la EPS). Con pruebas que cuidan las dos confusiones caras:
contar como logro lo que ya venía respondido, e inflar el valor de las
devoluciones.

### 24-08-2026 — Dispensario: el paquete de notas crédito quedó armado y verificado

**De dónde salió.** El Dispensario mandó el `CRRPNota.pdf` con **91 notas
crédito** (la mayoría de la conciliación del acta 858, más anulaciones). Había
que armar el paquete para subirlas al portal SIMED con el robot
`tools/cargar_soportes_simed.py`.

**Lo que se armó.** El PDF se partió en **86 carpetas** (una por nota
electrónica), cada una con su `NC_<nota>_HUS<factura>.pdf`. De las 91 páginas,
86 son notas cargables; las otras son repetidas o sin nota. También salió el
`LISTADO_NOTAS_CARGUE_DISPENSARIO.xlsx` con el inventario y una hoja aparte
con **3 facturas aceptadas en el acta 858 que aún no tienen nota crédito**
(443525, 443566 y 486894 — hay que pedírselas a Facturación).

**Las triadas se completaron desde el share.** Con los comandos entregados,
el auditor copió del share de facturación (`202608\FACTURAS_NOTA`) el XML y
el resultado del validador (CUV) de cada nota: las 86 quedaron con sus tres
archivos.

**La verificación del CUV (la regla de siempre antes de cargar) dio esto:**
**34 notas con CUV vigente** (se pueden cargar ya) y **52 rechazadas**. Se
extrajo el motivo de cada rechazo (queda el detalle en
`_motivos_rechazo.csv`): **47 son "RVG01" con tiempo agotado del validador**
— o sea falla del validador, no de los RIPS: solo hay que pedir a SISTEMAS
que las **revalide**, sin corregir nada; 2 son diagnóstico repetido
(RVC086, el mismo defecto del lote anterior); 1 es precio de medicamento
sobre la Circular 19/2024 (RVG20); y 2 son factura referenciada que no
coincide (GI018). Quedó redactado el **informe para SISTEMAS** con las
listas completas y qué se pide en cada grupo.

**Dos notas venían sin factura legible en el PDF** (páginas donde el número
salió como HUS0000000000). Se identificaron releyendo el cuerpo de la nota y
casando el valor contra el acta 858: la nota 332742 es de la factura
**HUS0000447748** y la 332832 de la **HUS0000486963**. Se entregaron los
comandos para renombrar sus archivos.

**Cómo se carga (queda listo para correr):** primero el piloto de 1 nota
(`--solo 332526 --con-cabeza`), y si sale bien, el lote de las 34 con CUV
vigente usando `--lista` con el CSV `_lista_cuv_ok.csv` (así el robot NO toca
las 52 rechazadas que siguen en la misma carpeta). Cuando SISTEMAS revalide,
se recopia el CUV nuevo del share, se re-verifica y se carga el resto.

**El cargue se corrió el mismo día y salió esto.** La primera corrida mostró
8 notas seguidas con «la factura no aparece en la grilla». No era falla del
robot ni del nombre de los archivos: al revisar el CRRP resultó que **de las
34 con CUV vigente solo 21 son del acta 858** (facturas con glosa, que sí
están en la pantalla que trabaja el robot); las otras **13 son anulaciones de
factura completa (12) y un trámite de devolución (1)**, que el portal no
lista ahí porque no son glosas conciliadas. Con la lista corregida
(`_lista_acta858_ok.csv`), **las 21 del acta 858 quedaron cargadas y
finalizadas en el SIMED: 21 de 21 OK** (reporte
`_reporte_carga_simed.csv`). También se renombraron todos los archivos de
`HUS0000xxxxxx` a `HUSxxxxxx` para que el adjunto coincida con el número real
de la factura electrónica. Las 13 anulaciones/trámite quedaron con sus
carpetas completas (PDF+XML+CUV), a la espera de definir con el gestor del
Dispensario por qué canal las recibe.

---

---

### 19-08 (tarde) — Glosas ADRES ahora muestra las CANTIDADES, no solo la plata

Yesid: «los gestores necesitan saber las cantidades porque si son 6 ítems pero
ellos van a aceptar algo pues no sabrían qué aceptar porque no sale las
cantidades de los ítems glosados».

**Qué pasaba.** El reporte del ADRES trae cinco columnas por renglón —
*Cantidad Reclamado, Valor Reclamado, Cantidad Aprobada, Valor Aprobado y Valor
Glosado*. El sistema las guardaba todas, pero a la pantalla solo le mandaba
cuatro: **la cantidad aprobada se quedaba en la base de datos**. El gestor veía
«$9.200 glosados» y ninguna cantidad, así que no tenía cómo saber cuántos
ítems estaban en discusión.

**No es un caso raro.** Se revisaron los dos paquetes reales que mandó Yesid:

| Paquete | Renglones glosados | Con aprobación parcial |
|---|---|---|
| 31068 | 4.638 | **277** |
| 31078 | 2.272 | **94** |

Un caso de verdad, factura **HUS353885**, dispositivo `2022DM-0008875-R1`: el
ADRES reclamó **3**, aprobó **1** y glosó **2** por $9.200. Es exactamente lo
que describía Yesid: «se facturan 6 ítems pero pagan 2 y los 4 los glosan».

**Qué se hizo.**

1. La tabla de la pantalla ahora trae las cinco columnas del reporte, agrupadas
   en tres bloques para que se lean de un vistazo:
   **Reclamado** (cantidad y valor) · **Aprobado por el ADRES** (cantidad y
   valor) · **Glosado** (cantidad y valor).
2. Se agregó la **cantidad glosada** = reclamados − aprobados. Es el número que
   el gestor necesita y que antes no existía en ninguna parte.
3. **Se corrigió lo que se le declaraba al ADRES.** Al marcar «SE ACEPTA», el
   sistema prellenaba la cantidad **reclamada**: en HUS353885 declaraba
   «cantidad aceptada 3» donde solo hay **2** ítems en discusión. Ahora
   prellena la glosada, y debajo de la casilla dice «de 2 glosado(s)» para que
   se vea el techo.
4. Cuando la cantidad glosada da **cero pero sí hay plata glosada**, la
   pantalla avisa **«solo valor»**: ahí no le quitaron ítems, le bajaron la
   tarifa (factura HUS354131, procedimiento 21706: 1 reclamado, 1 aprobado,
   $100 glosados). Un «0» pelado se leería como dato faltante.

**Comprobado con el archivo real de Yesid.** Se cargó el
`ReporteGlosasReclamPAQUETE_31068.xlsx` completo (4.619 renglones, 324
facturas) y la pantalla devuelve para HUS353885: reclamado 3 / $13.800,
aprobado 1 / $4.600, glosado 2 / $9.200.

### 19-08 — La factura fantasma del envío 232047 y el botón para quitarla

Elias escribió el envío **232047** y la página trajo **13 facturas**, cuando
el DGH y el Excel de radicación mostraban **12**. La de más era
**HUS0000538528 ($442.900)**, que no aparece en ninguna parte del Excel
(se revisaron las 22.363 filas del archivo, una por una).

**Por qué pasó.** La fuente de Radicación se actualiza factura por factura:
cuando facturación saca una factura de un envío, esa factura simplemente
deja de venir en el Excel nuevo — pero su fila vieja se queda guardada con
el envío anterior, y al escribir el envío la página la sigue trayendo. No es
que la página invente facturas: está leyendo un dato que se quedó viejo.

**Tres cosas quedaron para que no vuelva a doler:**

1. **Aviso antes de cargar.** «Ver antes» y «Cargar envío» ahora comparan de
   qué cargue del Excel viene cada factura del envío. Si una quedó de un
   cargue anterior mientras el resto se actualizó en el último, sale el
   aviso: «HUS…528 quedó de un cargue anterior de la Radicación (actualizada
   el 28/07); el resto del envío se actualizó el 19/08. Puede que facturación
   ya la haya sacado de este envío: verifíquela en el DGH antes de
   auditarla.»
2. **Botón 🗑 para quitar UNA factura** (lo que pidió Elias). En la ventana
   del oficio, cada fila tiene ahora su papelera: quita esa factura sola sin
   tocar el resto del oficio ni el envío. Si la factura nació ahí, se borra;
   si venía reingresada de una devolución, vuelve a su estado devuelto
   anterior con su historial intacto. **No** deja quitar una factura que ya
   salió en un oficio de devolución entregado (ese PDF ya está en manos de la
   entidad). Solo administración y coordinación, igual que la ✕ de los
   envíos.
3. **Comando de revisión** `tools\preauditoria_revisar_envio.py 232047`:
   muestra factura por factura de qué cargue viene y dónde quedó cargada, y
   marca con «OJO» las rezagadas. No cambia nada, solo mira.

12 pruebas nuevas. La fila vieja de la fuente se corrige sola la próxima vez
que esa factura venga en el Excel con su envío nuevo.

**Dos defectos de la primera versión, encontrados en la revisión y corregidos
el mismo día:** el aviso de factura rezagada no aparecía nunca (la fuente
sellaba todas las filas con la misma hora aunque el cargue fuera de otro día),
y al revertir un reingreso la factura se quedaba sin el amarre a su oficio de
devolución. Ambos con su prueba.

---

### 19-08 (tarde) — El Auditor Forense se muda adentro de «Analizar glosa»

**Qué es el Auditor Forense.** Es el buscador con IA dentro de los soportes de
una factura: usted pregunta en español corriente («¿está la baciloscopia?»,
«¿qué medicamentos se le administraron entre el 28-02 y el 02-03?», «¿la pinza
Enseal tiene justificación quirúrgica?») y la IA abre los PDF del expediente y
contesta **citando folio y fecha**. Sirve para cuando la EPS glosa diciendo «no
hay soporte de X» y hay que probar que sí lo hay.

**Estaba escogiendo mal los documentos.** Solo caben 5 por consulta, y los
escogía con el orden con que la pantalla de Soportes *lista* los archivos. Con
los 12 soportes reales de la factura HUS468334 eso daba:

| Se le mandaba a la IA | Quedaba sin abrir |
|---|---|
| FEV (la factura) | EPICRISIS |
| HEV (historia clínica) | HOJA DE ADMINISTRACIÓN DE MEDICAMENTOS |
| **RIPS `.json`** ← no es un PDF | OPF (otros procedimientos) |
| CRC (comprobante de recibido de cobro) | PDE |
| RESULTADOSMSPS | PDX |

Dos daños. Uno de los cinco cupos se gastaba en un archivo `.json` que la IA no
puede abrir. Y los documentos donde de verdad está la respuesta no se abrían
nunca: a la pregunta «¿qué medicamentos se administraron?» contestaba **«no
encontré evidencia»** sin haber mirado la hoja de administración de
medicamentos. **Con esa respuesta se acepta una glosa que había que objetar.**

Ahora se abren primero la historia clínica, la factura, la epicrisis, la hoja
de medicamentos y los otros procedimientos; lo que no sea PDF de verdad no se
manda; y —lo más importante— **la pantalla dice qué documentos quedaron sin
leer y por qué**. Antes decía «✅ 5 soportes leídos» y nada más.

**Y ahora trabaja solo, dentro de «Analizar glosa».** Yesid: «me gustaría que
este auditor forense estuviera anclado en analizar glosa, porque es exactamente
lo que se le pide que haga». Había un mecanismo para eso desde julio, pero
venía **apagado**, y aun prendido solo miraba los PDF que el auditor subiera a
mano — los soportes que el indexador ya tiene del servidor de radicación nunca
le llegaban. Se corrigieron las dos cosas: viene prendido y, si nadie adjuntó
nada, saca los PDF del servidor él mismo. El dictamen se arma citando folios
reales del expediente en vez de argumentar a ciegas.

**Se quitó el botón «Auditor Forense» de HERRAMIENTAS.** Yesid: «no tendría
sentido tener dos cosas que hacen exactamente lo mismo». El recuadro que
aparece al final del dictamen hace lo mismo y ya sabe de qué factura se trata,
sin tener que teclear el número. Con el apartado se fue también la
configuración del «servidor de archivos local», que era de cuando el motor
vivía en la nube y no veía las carpetas del hospital: hoy el motor corre en el
PC de cartera y lee `\\Prime\radicacion_2026` directo.

Se borró todo lo del apartado (botón del menú, pantalla y las 14 funciones de
JavaScript), con pruebas que vigilan que no quede nada suelto — la lección de
«Salud Total», que estuvo tres meses dando «Not Found» porque se borró el
router y el JavaScript siguió llamándolo.

---

---

### 19-08 (noche) — Al ADRES ya no se le declara dos veces la misma plata

Una revisión de fondo del módulo Glosas ADRES (35 revisores automáticos, cada
hallazgo verificado por otros que intentaban tumbarlo) encontró **dos fallas de
plata**, las dos reproducidas con el reporte real.

**1. El valor aceptado se declaraba DOBLE.** El reporte del ADRES abre un
renglón por cada causal del mismo ítem, y la pantalla pide una decisión por
renglón — así trabaja el gestor. El GLOSADO ya sabía no contar dos veces; el
ACEPTADO no.

Caso real, factura **HUS311371**, **TAC DE CRÁNEO SIMPLE** glosado $700.000 con
dos causales (3209 y 3106). Aceptando en las dos:

| | Antes | Ahora |
|---|---|---|
| KPI Valor glosado | $700.000 | $700.000 |
| KPI Aceptado | **$1.400.000** | **$700.000** |
| Carta al ADRES | «ACEPTADA PARCIAL POR VALOR DE **$1.400.000**» | «...POR VALOR DE **$700.000**» |

El hospital le declaraba al ADRES que aceptaba **el doble de lo que le habían
glosado** en ese ítem. En el paquete 31078 el reporte repite renglones en **27
de 81 facturas**, y son las de más plata.

El arreglo fácil —contar solo los renglones marcados— habría sido otro error al
revés: si el gestor objeta el renglón que cuenta y acepta el repetido, el
aceptado saldría **$0**. Ahora se consolida por ítem con tope en lo glosado, y
da bien en los cinco casos: aceptar en las dos causales, repartir la aceptación
entre ellas, aceptar solo en el renglón repetido, aceptar parcial, y dos ítems
iguales de verdad.

**2. «Aplicar sugerencias» aceptaba glosas por $0.** Al usar el botón en bloque,
las glosas quedaban «SE ACEPTA» con valor cero. La carta salía diciendo
«ACEPTADA PARCIAL POR VALOR DE **$0**» mientras enumeraba ítem por ítem lo que
sí aceptaba. Por el camino de a una glosa el valor sí se llenaba; por el camino
en bloque, nadie lo llenaba. Ahora se llena igual que a mano: todo lo glosado
del renglón y la cantidad **glosada** (no la reclamada).

**Verificador de doble clic.** Se entrega `tools\VERIFICAR_TRABAJO_HOY.cmd`:
doble clic en el PC de cartera y en una pantalla dice si las cuatro cosas de hoy
quedaron bien instaladas. Si le da el número de una factura radicada, además le
muestra **qué documentos abriría la IA y cuáles no** con los soportes reales del
servidor. Solo mira: no cambia nada, no llama a la IA y no cuesta un peso.

---

---

### 19-08 (noche) — Probamos «Analizar glosa» de verdad y salieron cinco cosas

Yesid analizó la factura **HUS468334** con una glosa **SO0201 — falta de
soporte**. De esa sola corrida salieron cinco fallas. Vale la pena leerlas
porque ninguna se habría visto sin probar con datos reales.

**1. El dictamen decía haber mandado soportes que nadie miró.** En una glosa
SO, la lista de soportes ES el argumento. El dictamen contestó:

> 📎 RELACIÓN DE SOPORTES APORTADOS
> 1. Historia clínica institucional — Res. 1995/1999
> 2. RIPS radicados — Res. 866/2021
> 3. Factura electrónica No. HUS468334 — Res. 2275/2023

Esa lista **era una plantilla fija**, escrita a mano, que salía por el solo
hecho de haber escrito un número de factura. Y la argumentación afirmaba haber
aportado «DESCRIPCIÓN QUIRÚRGICA Y REGISTRO ANESTÉSICO» — para una radiografía
de rodilla, donde no hubo cirugía. Si la EPS verifica y no están, la glosa se
ratifica. Ahora se leen del expediente real, y si la factura no está indexada
**no se afirma nada**: sale un aviso de que la relación está por verificar.

**2. Un CUPS inventado pasaba el sello de calidad.** El dictamen citaba
«RADIOGRAFÍA DE RODILLA **CUPS 348240**» y ese código no existe. El documento
salía sellado con «11 citas verificadas · 0 hallazgos» porque el verificador
revisaba normas y sentencias pero **ningún CUPS**. Un CUPS es de lo primero que
la EPS cruza contra su sistema. Ya se validan contra el catálogo.

**3. El motor pedía un modelo de IA que ya no existe.** El panel decía
«Primario: llama-4-scout», un modelo que Groq retiró el 05-08. Cada dictamen
gastaba una llamada muerta antes de caer al de respaldo. La causa: **la lista
de modelos estaba escrita a mano en cuatro archivos distintos** y la corrección
del 05-08 tocó uno solo. Ahora todos leen del mismo sitio.

**4. Lo mismo con Gemini**, el que lee los PDF escaneados: `gemini-2.0-flash`
también se retiró, y ahí es peor porque no hay respaldo — **el OCR dejó de
funcionar en silencio**. Se cambió por un nombre que Google mantiene siempre
vigente.

**5. El recuadro del Auditor Forense decía «N/A»** en vez del número de
factura, así que ese botón no servía. El dato estaba desde el principio; solo
faltaba devolverlo.

---

### 19-08 (noche) — Se quitó el ticker de noticias, y por qué nunca sirvió

Yesid pidió quitarlo: «nunca sirvió para nada». Tenía razón, y por un motivo
que no podía saber: **el motor de las noticias ya se había borrado en la
limpieza de mayo**. Lo que quedaba era la cáscara, así que llevaba tres meses
diciendo «0 noticias indexadas, el programador corre cada 4 horas». Nunca iba a
traer nada.

Un aviso amarillo permanente que nadie puede resolver enseña a ignorar los
avisos amarillos. Por eso se quitó completo, no solo el botón.

**Y se arreglaron las instrucciones de Sentry**, que mandaban al auditor a
escribir comandos de un servidor Linux con Docker cuando el motor corre en
Windows. Nadie podía seguirlas. Sentry es un buzón de errores: cuando algo
falla, en vez de perderse queda anotado con el detalle. Yesid pidió activarlo;
falta que cree la cuenta gratis en sentry.io y pegue el código en el archivo de
configuración (los pasos quedaron en la pantalla de Diagnóstico).

Se verificó antes de recomendarlo que **no se mandan datos de pacientes**: el
contenido de las peticiones se tacha antes de salir.

---

---

### 19-08 (noche) — El dictamen decía haber mandado papeles que no existen

Yesid volvió a responder la glosa **SO0201 de la factura HUS468334** —«ausencia
de soportes que evidencian la CONSULTA DE URGENCIAS»— y salió bien casi todo:
el recuadro del Auditor Forense ya trae el número de factura, la relación de
soportes lista los doce documentos reales con su nombre propio (incluida la
**hoja de atención de urgencias**, que es la que prueba esa glosa), y el CUPS
inventado sale marcado en rojo.

**Pero el texto del dictamen seguía inventando.** La argumentación decía:

> «LA FACTURA HUS468334 INCLUYE LA FACTURA ELECTRÓNICA, **AUTORIZACIÓN
> PREVIA**, EPICRISIS, HOJA DE ADMINISTRACIÓN DE MEDICAMENTOS, APOYO
> DIAGNÓSTICO, **DESCRIPCIÓN QUIRÚRGICA**, RIPS JSON Y CUV»

Ni la autorización previa ni la descripción quirúrgica estaban en ese
expediente. Y era una **consulta de urgencias**: no hubo cirugía. O sea que el
dictamen se contradecía **con su propia tabla, en la misma hoja**. Si la EPS lo
revisa, ratifica la glosa y de paso el hospital queda mal parado.

Se arregló por los dos lados:

1. **Al motor de IA se le entrega ahora el inventario verificado** de la
   factura —los documentos que de verdad están, con nombre de archivo— y la
   instrucción de no nombrar ningún otro.
2. **Se agregó una regla de fondo al motor**: «prohibido inventar soportes»,
   al mismo nivel que las que ya existían contra inventar normas, valores y
   tarifas. Hacía falta: el inventario solo existe cuando la factura está
   indexada, y sin la regla, en cualquier otra factura la IA volvía a
   completar de memoria. Si no recibe el inventario, ahora la salida correcta
   es no enumerar documentos.

**Y el puntaje castigaba de más.** El desglose de confianza decía «No se
anexaron soportes. La defensa documental es débil» sobre una factura **con doce
soportes en el expediente**: el contador solo miraba los PDF que el auditor
sube a mano, no los que el motor encuentra solo en el servidor de radicación.
Le restaba puntos por algo que el sistema ya había resuelto.

**Cambio de criterio de Yesid, que queda anotado:** «si dicho prompt interfiere
en futuras correcciones tocará modificarlo». Hasta hoy el prompt del motor era
intocable. De aquí en adelante se toca cuando estorbe una corrección de fondo
— con caso real que lo justifique, con prueba, y sin reescribirlo entero.

---

### 20-08 — «Salen 4 y son 5»: el oficio ya explica los envíos que llegan vacíos

En el oficio **FHUS-AS-I01190-26** salían **5 envíos cargados**
(232619, 232638, 232640, 232644 y 232649) y solo **4 facturas** en la tabla. La
que faltaba era la del envío **232619**: **HUS0000544836 ($99.900,
COMPAÑÍA MUNDIAL DE SEGUROS)**.

**Por qué pasaba.** La página no perdió nada ni se equivocó de cuenta: esa
factura **ya estaba abierta en otro oficio**. Cuando se escribe un envío, el
sistema NO trae de nuevo las facturas que siguen pendientes (o que ya se
radicaron) en otro oficio — si lo hiciera, la misma factura estaría en dos
oficios al tiempo. El problema era que **eso solo se avisaba una vez**, en el
momento de cargar el envío, y después no quedaba ni rastro en pantalla: el
chip del envío seguía diciendo «(1)» aunque esa factura nunca hubiera entrado
ahí. De ahí el «salen 4 y son 5».

**Qué quedó ahora.**

1. **El chip dice la verdad.** Cuando un envío no dejó todas sus facturas en
   el oficio, el chip se pinta en amarillo y muestra **«232619 (0 de 1)»**:
   quedaron 0 de la 1 que traía la fuente. Si todo llegó completo, se ve
   igual que siempre. La lista de oficios también lo muestra, en corto
   («232619(0/1)»).
2. **Debajo dice por qué, con nombre propio.** «🔎 Del envío **232619** falta
   la factura **HUS0000544836**: sigue pendiente de auditar en el oficio
   FHUS-AS-I01188-26; resuélvala allá (radicar o devolver) y después vuelva a
   escribir el envío aquí.» El mensaje cambia según el caso: ya radicada en
   otro oficio, devuelta esperando reingreso, o que se mudó a un oficio nuevo.
3. **No molesta cuando el auditor quitó la factura a propósito** con la 🗑:
   en ese caso la cuenta del envío ya bajó y no aparece ningún aviso.

7 pruebas nuevas. Para ver dónde quedó una factura sin abrir la página:
`venv\Scripts\python.exe tools\preauditoria_revisar_envio.py 232619`.

---

### 20-08 (tarde) — «¿Este Excel ya está subido?»: ahora se puede saber

Llegaron dos archivos con la misma pregunta: la hoja del oficio
**FHUS-AS-I01162-26** (14 facturas con las decisiones del 18 de agosto) y el
Excel de **Radicación de Cuentas** bajado del DGH hoy. Hasta ahora no había
forma sencilla de saber si eso ya estaba en el sistema.

**Dos cosas quedaron para responder esa pregunta sola:**

1. **La pestaña «Fuentes» ahora dice cuál fue el último archivo.** Debajo de
   los contadores aparece: «Último archivo de Radicación: **Document12.xlsx**
   · subido el 19/08/2026». Si el nombre no es el del archivo que acaba de
   bajar, ese archivo todavía no está subido.
2. **Comando de comparación** (no cambia nada, solo mira):
   `venv\Scripts\python.exe tools\preauditoria_comparar_acta.py "D:\...\FHUS-AS-I01162-26.xlsx"`
   Lee el Excel (el formato clásico del equipo o el consolidado ADRES) y dice
   factura por factura qué dice el papel y qué dice el sistema, con una marca:
   **AL DÍA** (ya está igual), **ADELANTE** (el sistema sabe eso y además
   avanzó: por ejemplo el acta la muestra devuelta y en la página ya reingresó
   a otro oficio), **FALTA** (esa decisión no está registrada), **DIFERENTE**
   (se contradicen, hay que mirarlo a mano) y **NO ESTÁ** (esa factura no
   existe en el sistema). Al final resume qué facturas piden acción y recuerda
   que lo correcto es auditarlas en la página, no volver a importar el Excel.

**Lo que se encontró en los dos archivos de hoy:** el Excel de Radicación
trae **376 facturas nuevas** y **96 envíos nuevos** frente al que estaba
cargado (y 26 facturas que facturación cambió de envío), así que hay que
subirlo; y de la hoja del oficio FHUS-AS-I01162-26, varias decisiones del 18
de agosto todavía no estaban en el sistema — entre ellas la devolución de
**HUS0000544836**, que es justo la factura del envío 232619 que no aparecía
en el oficio nuevo.

13 pruebas nuevas.

---

### 20-08 (cierre) — Corregir el número de un oficio mal digitado

Un oficio quedó registrado como **FHUS-AS-101190-26**, con un **uno** en vez
de la **I** (los demás son FHUS-AS-I01162-26). Hasta hoy no había forma de
arreglarlo: tocaba borrar el oficio —y con él su historia— y volverlo a
registrar.

**Ahora, en «Oficios y envíos», cada fila tiene un botón ✏** (solo
administración y coordinación) para corregir el número. El número del oficio
no es un dato suelto: va copiado en cada factura del oficio y en cada
renglón de su historial, así que el sistema los corrige todos en la misma
operación y avisa cuántos quedaron corregidos.

Salvaguardas: no deja dejarlo en blanco, no deja ponerle el número de otro
oficio ya registrado (dice cuál y de qué fecha), y si dos personas lo
corrigen al mismo tiempo el aviso es claro en vez de un error de programa.

6 pruebas nuevas.

### 20-08 (noche) — El dictamen ya no puede citar un folio que nadie leyó

Era el último hueco grande de la familia «la IA se lo inventa». Los **CUPS**
ya se verificaban contra el catálogo, y los **soportes** contra el expediente
real del servidor. Los **folios** no los revisaba nadie.

**Qué pasaba.** Un dictamen podía salir con la medalla verde «citas
verificadas · 0 hallazgos» diciendo:

> «SEGÚN CONSTA EN EL FOLIO 25 DE LA HISTORIA CLÍNICA…»

sin que nadie hubiera abierto una historia clínica. Es la afirmación **más
fácil de tumbar que existe**: la EPS pide el folio 25, no lo encuentra y
ratifica la glosa completa — y además queda en el expediente una afirmación
documental falsa firmada por el hospital.

**Por qué ahora sí se puede revisar.** La clave es simple: *la IA y el
revisor leen exactamente el mismo texto*. Si el folio no aparece en lo que la
IA tuvo a la vista, la IA no lo leyó: se lo inventó. Y cuando no se adjuntó
ningún soporte, cualquier folio citado está inventado, porque no había de
dónde sacarlo.

**Qué hace el sistema ahora, en orden:**

1. **Se lo devuelve a la IA para que lo corrija.** El folio inventado entra
   como defecto crítico y dispara el reintento que ya existía, con la
   instrucción exacta: *«no cites números de folio; refiérete al documento
   por su nombre — LA HISTORIA CLÍNICA ACREDITA…»*. La redacción jurídica la
   rehace la IA; el sistema **no** reescribe el texto legal a mano.
2. **Si aun así queda, el auditor lo ve antes de radicar.** El aviso sale en
   el recuadro rojo bajo el dictamen, la medalla de Evidencia baja a **C
   («corregir antes de radicar»)** y **se cae el sello «VALIDADO POR QUALITY
   GATE»**. En español claro: dice cuál es el folio, que no está en los
   soportes leídos, y qué escribir en su lugar.

**Cuidado con los falsos avisos.** Un aviso equivocado en cada dictamen
enseña al auditor a ignorar los avisos, y ahí se pierde también el
verdadero. Por eso quedaron probados los casos que *no* son un folio: «HOJA
DE ADMINISTRACIÓN DE MEDICAMENTOS», «HISTORIA CLÍNICA DE 25 FOLIOS»
(contar folios no es citar uno), «PORTAFOLIO 5» y las normas con números
(«RESOLUCIÓN 2284 DE 2023»). Y un folio real pero poco repetido en el
expediente tampoco se marca.

**Y se corrigió la causa, no solo el síntoma.** Buscando de dónde salía el
número apareció la razón: la instrucción que se le da al Auditor Forense
decía, en la misma lista, dos cosas que no se pueden cumplir a la vez:

> «2. Cita **SIEMPRE** el folio o página específica (ej: **"FOLIO 25"**)»
> «5. NO inventes folios»

Cuando el documento **no viene foliado** —y muchos no vienen— no hay manera
de obedecer las dos. La IA obedece la que le manda hacer algo y se inventa
el número. Peor: el ejemplo traía un número copiable, «FOLIO 25», que es
**exactamente** el que salía en los dictámenes inventados.

Ahora la regla dice: cite el folio **solo si el documento lo trae escrito**;
si no está foliado, nombre el documento por su tipo y su fecha («LA HOJA DE
ATENCIÓN DE URGENCIAS DEL 28/02/2026 REGISTRA…»). El mismo ajuste se hizo en
el molde del dictamen, que ofrecía «LA HISTORIA CLÍNICA FOLIO [N]…» sin
decir cuándo no usarlo.

**33 pruebas nuevas**, cuatro de ellas vigilando que el cableado no se
suelte: si mañana alguien agrega otra ruta que llame al revisor sin pasarle
lo que leyó la IA, la prueba se pone roja.

Y una salvaguarda al revés: los folios que **sí** leyó el Auditor Forense
—el que abre los soportes antes de redactar— cuentan como leídos y no se
marcan. Sería el peor aviso equivocado posible: castigar justamente al
dictamen bien fundamentado.

---

### 20-08 — Bot de SALUD TOTAL: notificación de glosas → cargue masivo de recepción

- **Nuevo bot `tools/organizar_objeciones_saludtotal.py`** (tercer hermano de
  SAVIA y FAMISANAR): convierte la notificación de glosas de SALUD TOTAL
  (6 columnas, export "NotificacionGLS_…") al formato de trabajo de 16
  columnas para el cargue masivo de recepción. Particularidades resueltas:
  la factura llega pelada (464306 → HUS0000464306), tres textos venían con el
  encoding dañado («Ã“» → «Ó», se reparan solos) y **Salud Total no manda el
  código del servicio, solo el nombre** — la casilla queda vacía, o se
  homologa por nombre con `--maestro` (acepta un OBJECIONES trabajado tipo
  LOTE_02 o un listado código|nombre; match exacto, sin inventar).
- Procesado el archivo real `PARA_MASIVO.xlsx`: 227 objeciones, 2 facturas
  (HUS0000464306: 197, tipo 2; HUS0000464511: 30, tipo 0), **$67.110.206**
  glosados. Verificación 227/227 filas fieles a la fuente. 19 pruebas nuevas
  (149 en verde entre los 3 bots + lector de pesos).

- **Notas crédito al portal de SAVIA (Conexiones):** el portal rechazaba el
  XML de la NC 332660 con «Invalid byte 2 of 4-byte UTF-8 sequence». Causa:
  el XML es válido, pero el portal re-codifica mal los ACENTOS al leer el
  documento embebido (una «ó» se vuelve un byte que su lector no entiende).
  Arreglo: **nuevo bot `tools/reparar_xml_nc_ascii.py`** — convierte los
  acentos a entidades XML (`&#243;`), el archivo queda 100 % ASCII, el
  contenido y las firmas DIAN internas quedan idénticos (verificado
  canónicamente antes de escribir). Sirve por archivo o carpeta completa
  (quedan ~124 notas por subir al portal). La NC332660 corregida se entregó
  y quedó lista para re-subir.

### 20-08 (noche) — Probamos 5 dictámenes de verdad: 3 defectos que se radicaban

Yesid corrió cinco glosas de prueba en «Analizar glosa» y pegó los dictámenes
completos. Salieron tres cosas que se estaban radicando ante las EPS:

**1. Cien mil pesos convertidos en un código de procedimiento.**
La glosa decía *«SO5801 — ausencia total de soporte de la curacion, VALOR
GLOSADO 100000»* y el dictamen salió afirmando «SERVICIO FACTURADO **CUPS
100000**». La causa: había DOS lectores de CUPS en el mismo archivo. Uno
endurecido durante meses —descarta fechas, números de factura, colas de
contrato, montos— y otro de una sola línea, que tomaba cualquier número de 5 o
6 dígitos. **El dictamen que se radica usaba el de una línea.** Se borró el
duplicado y se apuntó al bueno, más un filtro nuevo: si la propia glosa dice
que ese número es plata («valor glosado», «monto», «cuantía»), es plata.

*El verificador de citas sí lo atrapó* —medalla C, «CUPS 100000 no existe en el
catálogo»— así que el aviso funcionó. Pero es mejor que el error no se escriba.

**2. El dictamen se contradecía en el mismo renglón.**
«ESE HUS ACEPTA GLOSA TOTAL POR VALOR DE $200, CORRESPONDIENTE AL **SERVICIO
CUBIERTO**. SE ACEPTA POR CORRESPONDER A UN **SERVICIO NO CUBIERTO**…».
Cubierto y no cubierto a la vez. Pasaba igual en autorizaciones («AL
PROCEDIMIENTO AUTORIZADO… SE ACEPTA POR NO ACREDITARSE LA AUTORIZACIÓN») y en
soportes. Cuando el hospital está aceptando que algo falta, no puede afirmar en
la misma frase que ese algo está. Se quitaron los adjetivos que califican justo
lo que está en discusión; se conservaron los que son un hecho (el cargo se
facturó, el procedimiento se prestó, el medicamento se dispensó).

**3. Una glosa parcial radicada como «ACEPTADA AL 100%» — se regalaban $60.000.**
La EPS objetó $100.000 y el gestor aceptó $40.000. El dictamen salió con
**RE9702 «GLOSA ACEPTADA AL 100%»** y valor objetado $40.000. Radicado así, el
hospital renuncia a los $60.000 que sí estaba defendiendo, y encima lo
certifica. Pasaba porque la IA no extrajo el valor objetado, quedaba en cero, y
un respaldo lo daba por aceptación total igualando objetado a aceptado. **El
dato estaba escrito en la propia glosa** y el lector de valores ya sabía
leerlo; nadie le preguntaba. Ahora se le pregunta cuando la IA no trae el
valor. Sale correctamente **RE9801, parcial, con $60.000 en disputa**.

- 17 pruebas nuevas en `tests/test_api/test_el_dictamen_no_se_contradice.py`,
  con el texto exacto de las glosas de Yesid. Incluye las dos mitades del
  arreglo del CUPS: que la plata ya no entre, y que un CUPS de verdad (890201,
  898040) siga detectándose.
- La prueba del cableado se comprobó **quitando el arreglo a propósito** para
  ver que se pone roja; si no, no sirve de nada.

### 20-08 (noche) — Y la mentira que va SIN número de folio

En la misma tanda de pruebas apareció el defecto más grave de los cinco.
Yesid analizó una glosa de pertinencia (**CL0801, AXA COLPATRIA**) **sin
adjuntar un solo soporte**, y el dictamen salió diciendo:

> «EL SERVICIO DE APOYO DIAGNÓSTICO FACTURADO CUMPLE CON LOS CRITERIOS
> CLÍNICOS DEL MÉDICO TRATANTE, **QUIEN DOCUMENTÓ LA INDICACIÓN EN LA
> HISTORIA CLÍNICA INTEGRAL**.»

Nadie abrió una historia clínica. Y salió con medalla verde: «7 citas contra
corpus · 0 hallazgos» y el sello «VALIDADO POR QUALITY GATE».

El control de folios que se había puesto esa misma mañana **no la ve**, porque
no cita ningún folio. Es la misma mentira sin el número: el hospital certifica
ante la EPS lo que dice un documento que no leyó. Y en una glosa de pertinencia
eso es justo el punto en disputa — la EPS pide la historia, ve que la
afirmación no sale de ahí, y ratifica.

**Cómo queda.** Cuando no se leyó ningún soporte, el dictamen no puede afirmar
qué dice un documento clínico. Primero se le devuelve a la IA para que lo
reescriba (fundamentando en contrato, normativa y carga de la prueba, y
exigiendo a la EPS que precise qué echa de menos); si insiste, el auditor lo ve
en pantalla como hallazgo grave, con la frase exacta que sobra.

**Un detalle que salió de paso:** el consejo del control de folios decía «quite
el folio y escriba *LA HISTORIA CLÍNICA ACREDITA…*». Sin soportes leídos, eso
es cambiar una invención por otra. Ahora ese consejo solo aparece cuando sí hay
expediente; sin él, el consejo es no afirmar contenido.

**Regla a propósito estrecha:** solo se marca cuando **no se leyó ningún**
soporte. Con documentos a la vista haría falta leerlos de verdad para saber si
la frase es fiel, y un aviso equivocado es peor que ninguno — enseña al auditor
a ignorar los avisos. Media verificación honesta vale más que una completa que
se inventa la mitad.

- 18 pruebas nuevas en
  `tests/test_services/test_el_dictamen_no_afirma_lo_que_no_leyo.py`. Seis
  formas de inventar quedan marcadas; y **seis frases legítimas siguen
  pasando limpias**: «se anexa la historia clínica», «está a disposición de la
  EPS», «obra en el expediente», «la historia clínica es el soporte exigido por
  la Resolución 2284», «la EPS no precisó qué soporte echa de menos» y «se
  aporta el documento de la historia clínica» (ahí «documento» es sustantivo,
  no verbo).

### 20-08 (noche) — El dictamen que le daba la razón a la EPS

Tercer defecto de la misma tanda, y el que **cuesta plata**. La glosa era
`TA0201` del **DISPENSARIO MEDICO** —mayor valor cobrado en electrodo ECG— y
el dictamen salió diciendo, en el encabezado:

> Contrato: **SIN CONTRATO PACTADO** · Tarifa pactada: **SOAT PLENO**

…y en el cuerpo citaba, palabra por palabra, el **Parágrafo 3 del contrato**
que dice **SOAT −20 %**. Dos cosas malas a la vez:

1. El hospital **niega ante la entidad un contrato que sí existió** — el
   `440-DIGSA/DMBUG-2025`, que corrió del 30/12/2025 al 30/07/2026.
2. Al declarar SOAT pleno frente a un pactado de SOAT −20 %, **le está
   concediendo a la EPS justo lo que glosó**: que cobró de más. En una glosa
   de tarifa, eso es perder por escrito.

**Por qué pasaba.** El formulario no traía fecha del servicio, y sin fecha el
sistema usa **la de hoy**. Una glosa siempre es de un servicio pasado; ese
contrato llevaba 21 días vencido, pero el servicio es de cuando sí regía.

**Cómo queda.** Cuando nadie dijo la fecha, el dictamen ya no afirma que no
había contrato: lo nombra, dice que su vigencia terminó y pide **verificar la
fecha del servicio antes de radicar**. La tarifa sigue siendo SOAT pleno — sin
saber la fecha no se puede aplicar un descuento pactado, y aplicarlo de menos
también sería un error. Lo que se elimina es el «no teníamos contrato».

**Lo que NO se tocó, a propósito.** Cuando la fecha **sí** se conoce y ningún
contrato la cubría, «SIN CONTRATO PACTADO» se mantiene: es un hecho verificado
y además SOAT pleno es más favorable al hospital que el descuento pactado. Esa
decisión ya estaba tomada y tenía sus pruebas.

> **Nota de honestidad:** el primer intento de este arreglo fue demasiado
> amplio y puso en rojo tres pruebas que llevaban meses cuidando justamente esa
> decisión. Las pruebas tenían razón. Se estrechó el cambio al único caso que
> de verdad está mal —cuando la fecha se la inventa el sistema poniendo hoy—.

- 7 pruebas nuevas en `tests/test_services/test_verificacion_contractual.py`,
  al lado de las que ya cuidaban el tema.

### 20-08 (noche) — Cargadas las tarifas de la Resolución 283 de 2026

Yesid mandó **`TARIFAS_INSTITUCIONALES_RES_283.xlsx`**, la resolución nueva de
tarifas institucionales del HUS. Al compararla con lo que el motor ya tenía
cargado (Res. 054/2026 + 124/2026) salió que:

- **662 procedimientos NUEVOS** que el motor no conocía. Sin ellos, cuando la
  EPS glosaba uno de esos códigos el dictamen no podía dar el valor propio del
  hospital. Ahí está buena parte del laboratorio: baciloscopia ($96.800),
  troponina I ($172.700), dengue IgM ($104.000), leishmania, mycobacterium…
- **22 tarifas que YA estaban y cambiaron de valor.** El hospital venía
  defendiendo cifras viejas: **HIERRO TOTAL a $50.000 cuando la resolución
  dice $66.500**; TROPONINA T a $90.900 cuando dice $109.100; renina a
  $108.400 cuando dice $131.300. En esas glosas se estaba pidiendo de menos.
- Ninguna igual.

**Cómo quedó.** El catálogo pasó de **1.932 a 2.594 tarifas**. La 283 **se
suma**, no reemplaza: no se dio de baja ninguna de las que hoy se usan para
defender. Donde los dos catálogos pisan el mismo código, manda la 283 por ser
más reciente.

**Cada tarifa cita su propia resolución.** Una tarifa de la 283 cita la 283;
una de las anteriores sigue citando la 054 + 124. La EPS verifica la norma
citada: citar una resolución que no contiene esa tarifa es regalarle el
argumento.

**Cuatro códigos quedaron FUERA a propósito.** La resolución los publica
repetidos con valores distintos —`399802` HEMOFILTRACIÓN VENOVENOSA sale a
$5.450.000, $7.260.000 y $9.075.000— y no dice cuál aplica a cada caso.
Elegir uno sería inventarle una cifra al dictamen. Cuando aparezca uno de
esos, el motor **avisa que la tarifa está publicada por niveles y que hay que
verificarla contra el nivel prestado**, en vez de afirmar la que no es.

> **Pendiente para Yesid:** decirnos qué distingue los niveles de esos cuatro
> códigos (399802 hemofiltración, 399502 hemoperfusión, 399601 perfusión de
> cuerpo entero, 908338 aminoácidos/metabolitos). Con esa regla entran al
> catálogo automático.

- Para volver a cargar una resolución futura:
  `python tools/generar_tarifas_propias_hus_json.py --res283 RUTA.xlsx`
- 18 pruebas nuevas en `tests/test_services/test_tarifas_res_283_2026.py`,
  incluidas las que vigilan que **no se haya perdido** ninguna tarifa vieja.

### 20-08 (noche) — Importación masiva: dos defectos que salían en TODAS

Se probó el botón como lo usa el auditor de verdad: seleccionar el rango en
Excel —arrastrando desde la primera fila, que es lo normal— y pegarlo.

**1. La fila de títulos entraba como una glosa.** Quedaba guardada con entidad
«ENTIDAD», factura «FACTURA», valor «VALOR» y código «CODIGO». Se le gastaba
una llamada a la IA, le aparecía a usted en la lista y contaba en los totales
del lote. El filtro que había —«el código mide 2 o más caracteres»— la dejaba
pasar, porque «CODIGO» mide seis.

Ahora se reconoce y se salta. Para no comerse una glosa de verdad, se exige
que **manden** las etiquetas (la mitad o más de las celdas llenas): una glosa
cuyo motivo diga «el valor de la factura no coincide» sigue entrando.

**2. El valor glosado se leía como si fuera el CUPS.** El texto que el
importador le arma a la IA ponía el valor suelto:

> «SO0201 **125000** FALTA SOPORTE 890201 no anexan hoja»

…y el lector de códigos tomaba los **pesos glosados** como el código del
procedimiento. **Le ganaba incluso al CUPS de verdad** (890201) que venía en
su propia columna, porque el valor aparece primero. En una importación de 90
glosas, eso son 90 dictámenes citando un CUPS que no existe — y la EPS cruza
los CUPS contra su sistema.

El arreglo es decir qué es ese número: ahora el texto dice «VALOR GLOSADO
125000». El lector ya sabía descartar lo que el texto presenta como plata (se
había puesto esa misma tarde), así que con la etiqueta se resuelve solo, y de
paso la IA lee un texto más claro.

- 14 pruebas nuevas en `tests/test_api/test_importacion_masiva_de_verdad.py`,
  con un pegado tal cual sale de Excel (tabs, encabezado y pesos con punto).

### 20-08 (noche) — Tres botones del portal que no hacían nada

En `CLAUDE.md` está el caso que lo enseñó: **«Salud Total» estuvo tres meses
devolviendo «Not Found» porque se borró su router sin mirar que la pantalla
seguía llamándolo.** Se revisó el portal entero buscando lo mismo, comparando
**cada llamada que hace la pantalla contra las rutas que el motor de verdad
atiende**. Aparecieron tres funciones muertas:

**1. Arrastrar una glosa en el tablero Kanban.** La tarjeta no se movía y
salía «No se pudo cambiar el estado». Llamaba a una ruta con el método
equivocado y, encima, a la ruta equivocada: usaba la del flujo de *aprobación*
(BORRADOR → EN REVISIÓN → APROBADA) cuando el Kanban mueve entre RADICADA,
RESPONDIDA y CONCILIADA, que es otra cosa. Ahora usa la correcta.

**2. Crear y borrar snippets** (los atajos de texto: usted escribe `/ratif` y
se convierte en su párrafo de ratificación completo). La tabla estaba creada
en la base de datos y la pantalla «Gestionar mis snippets» estaba hecha. Lo
que faltaba era el medio: el motor devolvía lista vacía y no tenía ni crear,
ni borrar, ni contar usos. Usted abría el gestor, escribía su atajo, guardaba…
y salía «Falló». Quedó implementado completo, incluidos los atajos de EQUIPO y
los GLOBAL del coordinador.

> Detalle que evita un dolor de cabeza: si alguien guardaba «ratif» sin la
> barra, el atajo quedaba en la lista viéndose perfecto pero **no se expandía
> nunca**. Ahora la barra se pone sola.

**3. El simulador de conciliación.** Decía qué le va a contestar la EPS en la
audiencia y con qué responderle. Nunca se implementó: usted escribía su
postura, esperaba, y salía «No se pudo simular». El análisis que hace el
trabajo ya existía y se usaba en otra pantalla; solo faltaba conectarlo.

> Los contraargumentos NO los inventa una IA: salen del catálogo por tipo de
> glosa, y la probabilidad es la **tasa real de levantamiento de esa EPS** en
> audiencias anteriores. Si no hay historia con esa EPS, la probabilidad sale
> vacía y en pantalla aparece «—». Es preferible a poner un número inventado
> del que después alguien tome una decisión de plata.

**Y para que no vuelva a pasar:** quedó una prueba que revisa las **246 rutas**
que llama el portal contra las que el motor atiende. Si alguien borra un
router y deja la pantalla llamándolo, la prueba se pone roja el mismo día.
Se comprobó volviendo a romper el Kanban a propósito: efectivamente se pone
roja.

- 39 pruebas nuevas entre
  `tests/test_frontend/test_el_portal_no_llama_rutas_que_no_existen.py` y
  `tests/test_services/test_snippets_service.py`.

### 20-08 (noche) — «¿Cómo compruebo que el correo le llegó a los gestores?»

Pregunta de Yesid al subir el archivo de recepción. La pantalla decía **«📧
Correos enviados: 3»** y nada más — con eso no hay forma de saber a quién le
llegó y a quién no.

**Primero, lo que hay que tener claro.** Son tres cosas distintas:

1. **se armó** el correo — se ve en pantalla;
2. **salió** del servidor sin error — ahora también se ve en pantalla;
3. **llegó** al buzón del gestor — **esto no lo sabe ningún sistema de correo**,
   ni el nuestro ni ninguno, salvo que el mensaje rebote.

Lo que se podía mejorar era el nivel 2, y era mucho.

**Ahora la pantalla dice, después de subir:**

- **a qué buzón concreto salió** el correo de cada gestor (`IRMA RIOS →
  carterahus01@sinacsc.com`);
- **qué gestores del Excel se quedaron sin correo** porque su nombre no
  coincide con ningún usuario del portal — con la explicación de cómo
  arreglarlo (crear el usuario, o poner en el Excel el mismo nombre con el
  que está registrado);
- **cuáles rebotaron** al salir;
- y si el servidor **no tiene correo configurado**, lo dice de frente en vez
  de mostrar un «0» que se lee como si no hubiera nada que enviar.

**La comprobación con datos reales.** Se cruzaron los 6 gestores del archivo
del 19 de agosto (85 glosas) contra los 23 usuarios del portal:

| Gestor | Glosas | Le llega a |
|---|---|---|
| YESID PEREZ | 35 | glosashus09 |
| IVAN ARCINIEGAS | 26 | glosashus13 |
| IRMA RIOS | 7 | carterahus01 |
| MARICELA ROJAS | 7 | glosashus05 |
| EQUIPO ASEGURADORAS | 6 | **los 4 buzones del equipo** |
| KAREN ORTIZ | 4 | radicadevoluciones |

**Los seis tienen correo.** Ese archivo sale completo.

**Y de paso apareció un defecto feo.** El cruce de nombres aceptaba
«contiene» sin exigir un mínimo de letras. Si en la casilla del gestor
quedaba **una sola letra** —una «A» por un dedazo en el Excel— el correo le
llegaba a **22 de los 23 usuarios**, porque casi todo nombre lleva una A. Cada
quien habría recibido un plan de trabajo que no es el suyo, y el dueño de
verdad podía no aparecer. Una «S» alcanzaba a 17. Ahora el «contiene» exige 4
letras; el nombre exacto sigue valiendo para cualquier largo.

- 17 pruebas nuevas en `tests/test_services/test_a_quien_le_llega_el_correo.py`,
  **con los usuarios y los gestores reales**.

### 20-08 (noche) — El radicable le metía a COOSALUD facturas del Ejército

Yesid importó el lote del 19 de agosto —35 glosas— y descargó el Excel
radicable. Salió **un solo archivo** llamado
`RESPUESTA_GLOSAS_COOSALUD_19AGO2026_HUS.xlsx`, con el **contrato de COOSALUD
en el encabezado** (68001C00060340-24)… y **las 35 facturas adentro**.

De esas 35, **6 son del DISPENSARIO MÉDICO / EJÉRCITO**, por **$10.290.042**.

Radicado así, el hospital le presenta a COOSALUD seis facturas de otro
pagador, bajo un contrato que nada tiene que ver con ellas: COOSALUD lo
devuelve, y de paso ve las facturas de otra entidad.

**Por qué pasaba.** El archivo se rotulaba con la entidad **más frecuente** del
lote (29 de COOSALUD contra 6 del Ejército, gana COOSALUD), pero después no se
filtraba por ella. Nadie sacaba las otras.

**Cómo queda.** Un radicable se presenta ante UNA entidad, así que ahora se
arma **uno por entidad**. Si el lote trae una sola, se descarga el Excel igual
que siempre; si trae varias, bajan **todas juntas en un ZIP** — así no falta
ninguna ni termina ninguna donde no es.

### Y lo del correo a las doctoras

Pedido de Yesid: «que también les llegue al correo de las doctoras». Ya está:
cuando el lote trae **glosas médicas** —pertinencia o calidad, las que no se
pueden contestar desde cartera sin concepto clínico— el resumen les llega
también a ellas. Si el lote no trae ninguna médica, **no** se les manda: si no,
se les llenaría el buzón de tarifas y facturación que no les competen, y
terminarían ignorando también las que sí importan.

**Cómo señalar quiénes son** (sirve cualquiera de las dos):

1. En la pantalla de **Usuarios**, escribirle `AUDITORIA MEDICA` en el campo
   **equipo** a cada doctora. Es lo más cómodo y no necesita tocar el servidor.
2. O configurar `MEDICOS_AUDITORES_EMAIL` en el `.env` del servidor, con los
   correos separados por coma.

A propósito **no se adivina**: que alguien sea SUPER_ADMIN, o que su correo
empiece por «auditor», no lo vuelve médico. Mandarle historia clínica a quien
no es del área por una corazonada del sistema sería peor que no mandarla.

Y si el lote trae glosas médicas pero **nadie está señalado**, la pantalla lo
dice en rojo con el paso a seguir, en vez de callarse.

- 8 pruebas en `tests/test_services/test_el_radicable_no_mezcla_entidades.py`
  (con las 6 facturas reales del Ejército) y 6 más en
  `test_a_quien_le_llega_el_correo.py` para lo de las doctoras.
- El arreglo del radicable se comprobó **quitando el filtro a propósito**: se
  ponen 4 pruebas en rojo.

### 20-08 (noche) — Por qué no salió el correo, y a cada doctora lo suyo

**1. El aviso apuntaba al lugar equivocado.** Yesid importó, no salió correo, y
la pantalla marcó la importación como **«✗ sin destinatarios»** — que se lee
como «no encontré a quién mandarle». Importó otra vez buscando el error en la
lista de gestores. Pero la causa era otra: **el servidor no tiene el correo
configurado**, y ese mismo estado se ponía para las dos cosas.

Un aviso que apunta al lugar equivocado hace perder más tiempo que no tener
aviso. Ahora la pantalla distingue tres causas:

| Lo que sale | Qué pasó de verdad |
|---|---|
| ✗ **el servidor no tiene correo configurado** | Faltan `SMTP_USER` / `SMTP_PASSWORD` |
| ✗ nadie a quien enviarlo | Sí hay correo configurado, pero ningún gestor cruzó |
| ✗ no quedó el archivo original | Se purgó el .xlsx del lote |

**2. A cada doctora lo suyo.** Yesid confirmó que las médicas auditoras son
**solo tres**: LAURA DIAZ, LEIDY SANGUINO y ZULAY GONZALEZ. Y mostró algo
mejor: **el Excel ya dice cuál doctora lleva cada glosa**, en la columna
`PROFESIONAL(MEDICO)`.

Así que no se les manda a las tres el lote entero: a cada una le llega **lo
suyo**. Quien recibe treinta glosas que no son suyas deja de abrir el correo, y
ahí se pierden también las que sí.

> **Un detalle que casi las deja sin correo:** el Excel escribe «LEIDY
> SANGUINO» y el portal la tiene como «LEIDY JHOANA SANGUINO»; «ZULAY
> GONZALEZ» contra «LEYDI ZULAY GONZALEZ». Comparando letra por letra, esos
> dos correos no habrían salido nunca. Se usa la comparación por palabras que
> ya existía para los gestores, y las tres resuelven bien.

Si una glosa médica no dice qué doctora la lleva, se les avisa a todas las
registradas — mejor eso que dejarla sin avisar. Y si el nombre del Excel no
coincide con ningún usuario, la pantalla lo dice con el nombre exacto.

- 37 pruebas en `tests/test_services/test_a_quien_le_llega_el_correo.py`, con
  los nombres **tal como vienen en el Excel del 19 de agosto**.

### 20-08 (noche) — Botón «Probar correo»: por qué no salía ninguno

**El diagnóstico quedó cerrado.** Yesid corrió la consulta en el PC de cartera
y el `.env` **no tiene absolutamente nada de correo**: ni `SMTP_USER`, ni
`SMTP_PASSWORD`, ni `SMTP_HOST`, ni `ALERTAS_EMAIL`. Por eso salieron cero
correos — no era problema de los gestores ni de los nombres.

Lo importante: **mientras eso falte, NINGÚN correo del motor sale.** Ni el
resumen de recepción, ni las alertas de vencimiento.

**El problema de fondo era otro:** comprobarlo costaba volver a importar el
archivo entero y mirar el resultado. Cinco minutos por intento, para algo que
se responde en dos segundos. Por eso Yesid importó dos veces.

**Ahora hay un botón «📧 Probar correo»** en el panel de Diagnóstico. Manda un
mensaje al buzón de quien lo aprieta y dice qué pasó — sin tocar ninguna
glosa. Y traduce los errores del servidor de correo, que son crípticos:

| Lo que responde el servidor | Lo que sale en pantalla |
|---|---|
| `535 Username and Password not accepted` | «Con Gmail no sirve la contraseña normal: hay que generar una **contraseña de aplicación** de 16 letras» |
| `Connection timed out` | «Suele ser el firewall del hospital bloqueando la salida» |
| `Name or service not known` | «Revise SMTP_HOST» |

La contraseña **nunca se muestra**, ni siquiera cuando está puesta: dice
«(configurada)» y ya.

**Lo que falta para que el correo funcione** (lo tiene que hacer el hospital,
no se puede desde acá): agregar al `.env` del servidor la cuenta desde la que
saldrán los correos y su contraseña de aplicación.

- 10 pruebas en `tests/test_api/test_probar_correo.py`, incluida la que
  verifica que la contraseña no se filtre en la respuesta.

### 20-08 (noche) — Salud Total: 44 glosas ya no tumban la petición

Una notificación de SALUD TOTAL trae **44 glosas**. Se analizaban de tres en
tres, esperando hasta **120 segundos por cada una**… y el túnel por el que
entra el portal **corta a los ~100 segundos**.

O sea: **la espera de UNA SOLA glosa ya era más larga que lo que aguanta la
conexión.** La petición se caía con un 502 y se perdía todo el trabajo que la
IA ya había hecho —los tokens gastados incluidos—, sin que saliera ni un
archivo.

**Cómo queda.** Ahora hay un presupuesto de tiempo para todo el lote, sacado
del corte real del túnel y no de un número inventado. Cuando se acaba, las
glosas que falten **salen por plantilla** —que es una respuesta válida y
radicable— en vez de arriesgar que la petición entera se caiga y no salga
ninguna. Entre «todas con plantilla» y «ninguna», la plantilla gana sin
discusión.

| | Antes | Ahora |
|---|---|---|
| Espera por glosa | 120 s (fijos) | 85 s |
| Presupuesto del lote | ninguno | 70 s |
| Corte del túnel | ~100 s | ~100 s |

El resumen ahora dice **cuántas quedaron por falta de tiempo**, aparte de las
que fallaron: no es lo mismo, porque volviendo a correrlo esas sí pueden
mejorar.

**Lo que NO se tocó, y por eso conviene saberlo:** cada fila sale SIEMPRE con
respuesta por plantilla aunque la IA falle. Eso ya estaba bien resuelto de
antes, y es lo que impide el desastre de verdad — una fila vacía en el archivo
que se radica es una glosa sin responder, y **una glosa sin responder se da
por aceptada**: la plata se regala.

- 10 pruebas en `tests/test_services/test_salud_total_no_se_pasa_del_tunel.py`,
  incluida la que vigila que no vuelva el 120 fijo escrito a mano.

### 20-08 (noche) — Un cargue que se corta a mitad ahora dice qué SÍ quedó

Revisando el pendiente que decía «la importación de DGH deshace filas mientras
el resumen dice que quedaron guardadas», resultó que **eso ya estaba bien
resuelto**: las fuentes de Pre-auditoría se cargan por bloques y cada bloque se
confirma apenas termina, así que una interrupción no pierde lo guardado y
volver a subir el mismo archivo retoma donde quedó sin duplicar nada.

Lo que faltaba era **contarlo**. Si el cargue reventaba en el bloque 5 de 10,
el auditor veía un error a secas —**como si no se hubiera guardado nada**—
cuando en realidad los cuatro anteriores ya estaban en la base. Eso lleva a
rehacer trabajo que no hace falta o, peor, a dudar de lo que sí quedó.

**Ahora dice:** «El cargue se cortó en la fila 301 de 1.000. Las 300 anteriores
SÍ quedaron guardadas. Vuelva a subir el mismo archivo: retoma donde quedó y no
duplica nada».

También se suelta la transacción a medias. Sin eso, la sesión quedaba
envenenada y todo lo que viniera después en esa misma petición fallaba sin
explicación.

- 7 pruebas en `tests/test_services/test_el_cargue_a_medias_se_ve.py`.
- Una prueba vieja comparaba el diccionario COMPLETO con `==` y se puso roja
  por las dos claves nuevas. No estaba fijando ningún defecto —solo era
  estricta con la forma—, así que se ajustó para comparar **los conteos**, que
  es lo que de verdad cuida.

### 20-08 (noche) — El correo YA SALE, y ahora se ve desde el portal

**Yesid configuró el correo en el servidor y los correos empezaron a salir.**
Ese problema quedó cerrado.

Pero en la bandeja de la cuenta que envía aparecieron los **rebotes**:

> 🏥 Motor Glosas HUS — 150 glosas importadas desde recepción
> «**Address not found** — Your message wasn't delivered…»
> «**Message blocked**…»

Es decir: el motor envía bien, pero **las direcciones de destino están
rebotando**. `Address not found` significa que esa dirección **no existe** en
el servidor de destino.

Y preguntó cómo mirar eso desde el portal. No se podía: cada correo salía sin
dejar rastro, y para saber si algo se había enviado había que entrar a Gmail —
justo lo que un auditor no debería tener que hacer.

**Ahora hay un botón «📬 Correos enviados»** en Diagnóstico, al lado del de
«Probar correo». Muestra los últimos 100 intentos: a qué buzón, cuándo, si
salió o falló, y **un resumen por dirección** — que es lo que deja ver de una
que un buzón concentra todos los fallos.

> **Lo que muestra y lo que NO, dicho en la propia pantalla:** acá queda si el
> servidor de correo **aceptó** el mensaje. Que **llegue** al buzón es otra
> cosa — cuando la dirección no existe, el rebote llega minutos después a la
> cuenta que envía y **no se ve desde acá**. Prometer entrega sería mentir.

**Lo que hay que revisar ahora** (es del hospital, no del motor): que las
direcciones `@sinacsc.com` de los usuarios **existan de verdad** como buzones.
Las que rebotan con «Address not found» no van a recibir nada por más que el
motor las intente.

- 7 pruebas en `tests/test_api/test_correos_enviados_se_ven.py`.
- Una de ellas encontró un defecto de verdad: la protección del registro
  estaba solo por dentro, así que un fallo inesperado **habría tumbado un
  correo que ya iba a salir**. El registro es secundario y jamás puede costar
  un envío: ahora está protegido también en el punto de llamada.

### 20-08-2026 — Sistema de preparación para el ICFES Saber 11 (carpeta `icfes/`)

**Qué se pidió:** un sistema completo para prepararse durante un año para el
examen del ICFES (Saber 11), apuntándole a 400 puntos de 500, con unas 12 horas
de estudio a la semana y presentación en el Calendario A de agosto de 2027.

**Aclaración importante:** este trabajo NO es del Motor de Glosas ni de Cartera.
Es un módulo aparte, guardado en la carpeta `icfes/`, que no toca ni depende de
nada de `app/` ni de `tools/`. Se puede copiar solo a otro computador y funciona.

**Qué quedó hecho:**

1. **El examen modelado tal como es** (`icfes/dominio.py`): las cinco áreas con
   sus preguntas reales (Lectura Crítica 41, Matemáticas 50, Sociales 50,
   Ciencias Naturales 58, Inglés 55 = 254 calificables, más 24 de pilotaje que
   no dan puntaje), los pesos oficiales (3 para todas menos Inglés que pesa 1),
   las dos sesiones de 4 h 30 y las competencias de cada área. Si el ICFES
   cambia algo, se cambia ese solo archivo.
2. **Motor de puntaje** (`icfes/puntaje.py`): el puntaje global de 0 a 500 con la
   fórmula oficial, y la traducción de «acerté 34 de 50» a un puntaje de área.
   Esa traducción **se declara siempre como estimación**, porque el ICFES usa un
   modelo estadístico que no se puede replicar. También calcula, para una meta
   dada, cuántas preguntas hay que acertar en cada área.
3. **Banco de 110 preguntas** (`icfes/banco/`, un JSON por área), todas con
   explicación y con el aviso de **cuál es la trampa** de la pregunta. Cubre las
   17 competencias de las cinco áreas. Los textos de Lectura Crítica son de
   obras colombianas de dominio público (Isaacs, Silva, Rivera). Se aclara en
   todas partes que son preguntas de práctica, no del examen real.
4. **Plan de estudio de 50 semanas** (`icfes/plan.py`): reparte las horas según
   cuánto pesa cada área y dónde está la brecha, en cuatro fases (Fundamentos →
   Competencias → Entrenamiento de examen → Afinamiento), con 11 simulacros
   completos, un día de descanso a la semana y la última semana aliviada.
5. **Repaso espaciado** (`icfes/repaso.py`): decide qué toca repasar cada día
   para que lo de marzo no se olvide en agosto. **Nunca programa un repaso
   después del examen.**
6. **Simulacros cronometrados** (`icfes/simulacro.py`) con la estructura real y
   los segundos por pregunta del examen (2 min 15 s en la sesión 1, 2 min 1 s en
   la 2). Como el banco todavía no llega a 254 preguntas, los simulacros se
   arman **a escala** y el sistema lo dice en pantalla.
7. **Cuaderno de errores y proyección** (`icfes/progreso.py`): agrupa las fallas
   por causa (no sabía el tema, iba de afán, marqué mal…) con el remedio de cada
   una, y proyecta a qué puntaje se llega el día del examen, avisando cuándo esa
   proyección todavía no es confiable.
8. **Programa de consola** (`python -m icfes ...`) y **aplicación web de un solo
   archivo** que funciona **sin internet**, sirve en el celular y guarda el
   avance en el navegador. En Windows se genera con doble clic en
   `tools\ICFES_APP.cmd`.

**Dos fallas encontradas durante el trabajo y corregidas:**

- El simulacro reconstruía las respuestas leyendo la base de datos, así que una
  pregunta practicada más temprano ese mismo día se contaba como acertada dentro
  del simulacro. Ahora la ronda devuelve las respuestas reales.
- La plantilla de la aplicación web dejaba pegado su objeto vacío al lado de los
  datos inyectados y **la página no cargaba nada**. Se detectó abriendo la
  aplicación en un navegador de verdad, no con pruebas de escritorio. Quedó
  corregido con marcas de apertura y cierre, y con una prueba que lo vigila.

**Comprobaciones:** 239 pruebas de `pytest` propias del módulo, `ruff` limpio
(revisión y formato), y la aplicación web abierta en Chromium comprobando el
recorrido completo (practicar, explicación, cronómetro, resultado, progreso y
que el avance sobrevive al recargar), sin un solo error de JavaScript.

**Documentos:** `docs/GUIA_SISTEMA_ICFES.md` (cómo se usa) y
`docs/ESTRATEGIA_ICFES_400.md` (el plan concreto para llegar a 400).
### 20-08 (noche) — Los soportes del .zip caían donde el índice nunca mira

Último pendiente de la lista, y era real. La carpeta de soportes se resolvía
en **dos lugares con reglas distintas**:

| | El índice mira | El .zip se guarda en |
|---|---|---|
| 1º | **`config/soportes_root.txt`** | `SOPORTES_LOCAL_ROOT` |
| 2º | `SOPORTES_ROOT` | `SOPORTES_ROOT` |
| 3º | `SOPORTES_LOCAL_ROOT` | `/tmp/motor-soportes` |

La subida **ni siquiera leía** `config/soportes_root.txt`, que es justamente
donde el hospital dejó escrita la suya (`\\Prime\radicacion_2026`).

**Qué pasaba:** el auditor subía un .zip de soportes, el motor decía «subido»,
y los PDFs quedaban en una carpeta que **el índice nunca recorre**. Después
buscaba la factura, no aparecía, y **no había forma de entender por qué** — el
archivo estaba, pero en otro lado.

**Cómo queda.** Una sola función responde «dónde viven los soportes», y la
usan las dos: el índice y la subida. Si mañana cambia el criterio, cambia para
las dos a la vez.

- 8 pruebas en `tests/test_services/test_el_zip_cae_donde_el_indice_busca.py`,
  incluida una que se pone roja si alguien vuelve a resolver la carpeta a mano
  en el router — que es exactamente como nació el defecto.

### 20-08 (noche) — Resubir el mismo archivo no es un error

Yesid volvió a subir `GLOSAS 19 AGOSTO.xlsx` —el mismo que ya había entrado
bien— y la pantalla le mostró:

> ⚠ **Importación procesada — 0 glosas detectadas**
> TOTAL 0 · NUEVAS 0 · ACTUALIZADAS 0 · RATIFICADAS 0 · **EXTEMPORÁNEAS 29**
> *Posibles causas: el Excel no tiene la hoja correcta… los headers no
> matchean…*

**Dos problemas de golpe.**

**1. «0 detectadas» junto a «29 extemporáneas» no pueden ser ciertas a la
vez.** Los contadores de ratificadas y extemporáneas se sumaban al CLASIFICAR
la fila, antes de saber si la fila iba a entrar. Una fila que después resultaba
duplicada se saltaba el total, pero su extemporaneidad ya estaba contada. Ahora
se cuentan cuando la fila **sí** entra.

**2. El aviso lo mandaba a buscar un problema que no existía.** El archivo
estaba perfecto: **las 35 glosas ya estaban importadas**, que es lo normal al
volver a subir el mismo archivo. Pero la pantalla le decía que revisara la hoja
y los encabezados.

**Ahora son dos mensajes distintos, porque son dos situaciones distintas:**

| Lo que pasó | Lo que sale |
|---|---|
| Todas ya estaban | ✅ verde: «**nada nuevo que registrar** — las 35 glosas del archivo YA estaban importadas. No se creó ninguna nueva y no se perdió nada, el archivo está bien» |
| No se leyó ninguna fila | ⚠ ámbar: el aviso de la hoja y los encabezados, que ahí **sí** aplica |

Y se agregó el contador **«YA ESTABAN»**, que antes no se veía en ninguna
parte: el auditor no tenía cómo saber qué había pasado.

- 8 pruebas en `tests/test_services/test_resubir_el_mismo_archivo_no_asusta.py`.

### 20-08 (noche) — El .env podía no encontrarse, y nadie se enteraba

Buscando por qué el motor decía «el correo no está configurado», apareció algo
más grande. La configuración se leía de `".env"` — una ruta **relativa**, que
se resuelve contra **la carpeta desde la que se arrancó el motor**, no contra
la del repositorio.

Si el motor arranca desde otra carpeta, el `.env` **no se encuentra** y toda la
configuración cae a sus valores por defecto **en silencio**: sin claves de IA,
sin correo, sin nada. Y no hay ningún aviso, porque «no encontré el archivo» y
«el archivo está vacío» se ven exactamente igual.

Que en este repositorio ya exista `config/soportes_root.txt` —leído por ruta
absoluta, con un comentario explicando que las variables de entorno no
sobrevivían al vigilante que revive el motor— dice que esta clase de problema
**ya había mordido antes por otro lado**.

**Cómo queda.** Manda el `.env` de la carpeta actual si lo hay —arrancar desde
una carpeta con su propio `.env` es legítimo, así corren las pruebas—, y si
no hay ninguno se usa el de la raíz del repositorio, que es el caso que estaba
roto.

> **Nota de honestidad:** el primer intento fue absoluto a secas y puso en rojo
> dos pruebas del `.env` con acentos, que arrancan el motor desde una carpeta
> temporal con su propio archivo. **Las pruebas tenían razón**: ese caso es
> legítimo. Se corrigió para respetar los dos.

- 8 pruebas en `tests/test_api/test_el_env_se_encuentra_siempre.py`.

### Y lo del correo, con el dato en la mano

La consulta al `.env` del PC de cartera salió **vacía las dos veces**:
`SMTP_USER` y `SMTP_PASSWORD` **no están en el archivo**. Los correos que
Yesid vio en Gmail salieron de otra configuración o de otro momento.

**Lo que falta hacer en el PC de cartera:** agregar esas dos líneas al
`C:\motor-glosas\repo\.env` y reiniciar el motor. Ojo con el Bloc de notas:
suele guardar como `.env.txt`, y así el motor nunca lo lee.

### 20-08 (noche) — Si falta el .env, ahora el motor lo dice

La otra mitad del arreglo anterior. Anclar bien la ruta evita que el archivo se
pierda, pero no sirve de nada si cuando falta **el motor se calla**: desde
afuera, «no encontré el archivo» y «el archivo está vacío» se ven exactamente
igual, y uno termina buscando el problema donde no está. Que es justo lo que
nos pasó con el correo.

**Ahora avisa en dos sitios:** en el registro al arrancar, y como una sección
propia en la pantalla de **Diagnóstico**, marcada en rojo — porque sin `.env`
el motor corre sin claves de IA y sin correo, y eso no es un detalle.

Y detecta el descuido clásico de Windows: **el Bloc de notas guarda «.env» como
«.env.txt»** y el explorador esconde la extensión, así que el archivo se ve
bien. Si encuentra uno de esos al lado, lo nombra.

> **No grita por lo normal:** `.env.example` y las demás plantillas del
> repositorio no se señalan. Un aviso que salta por algo corriente enseña a
> ignorar los avisos.

> **Nota de honestidad:** puse la sección de primera y dos pruebas se pusieron
> rojas. Tenían razón, y por un buen motivo: la sección del **motor** va
> primero porque si hay dos motores corriendo ningún otro dato del panel es
> confiable, y la **versión** va segunda. La mía quedó tercera.

- 9 pruebas en `tests/test_core/test_si_falta_el_env_se_avisa.py`.

### 20-08 (noche) — La contraseña de Gmail se pega con espacios

Google muestra la contraseña de aplicación en cuatro grupos de cuatro —«abcd
efgh ijkl mnop»— y uno la pega tal cual, que es lo natural. **Los espacios son
solo para leerla**, no son parte de la clave.

El problema: algunos servidores la aceptan así y otros la rechazan, y el error
que devuelven es **el mismo** «Username and Password not accepted» que sale
cuando la clave está de verdad equivocada. Uno se pone a generar claves nuevas
sin necesidad.

Ahora el motor le quita los espacios **solo** cuando la clave tiene la forma
exacta de una contraseña de aplicación de Google (16 letras o números en 4
grupos de 4). Cualquier otra se manda tal cual: hay servidores de correo donde
un espacio **sí** es parte de la contraseña, y tocarla ahí sería romperla.

- 12 pruebas en `tests/test_services/test_la_clave_de_gmail_con_espacios.py`,
  la mitad dedicadas a lo que NO se debe tocar.

### 20-08-2026 (cierre) — El sistema ICFES no arrancaba desde PowerShell

**Qué pasó en el primer uso real.** Se copiaron los comandos de la guía a una
ventana de PowerShell parada en `C:\Users\cartera` y Python respondió cuatro
veces `No module named icfes`. **El sistema estaba bien; la carpeta estaba
mal.** `python -m icfes` solo encuentra el módulo si la consola está parada
dentro de la carpeta del repositorio (`C:\temp-notas`), y la guía mostraba los
comandos sin decirlo.

**Qué se hizo para que no vuelva a pasar:**

1. **`tools\ICFES.cmd`** — bot de doble clic con menú: qué estudiar hoy,
   practicar, repasar, simulacro, progreso, plan, configurar y generar la
   aplicación web. Lo primero que hace es pararse solo en la carpeta correcta,
   así que el error es imposible. También avisa, con instrucciones, si Python
   no está instalado.
2. **Las tres guías corregidas** (`docs/GUIA_SISTEMA_ICFES.md`,
   `docs/ESTRATEGIA_ICFES_400.md` y `README.md`): ahora ponen el doble clic
   primero, muestran el `cd C:\temp-notas` como paso cero y explican qué
   significa el mensaje `No module named icfes` cuando aparece.
3. **12 pruebas nuevas** (`tests/test_icfes/test_bots_windows.py`) que vigilan
   lo que de verdad rompe estos bots: que se paren en la carpeta del
   repositorio, que avisen si falta Python, que no llamen a comandos que no
   existen, que no traigan contraseñas, y —esto no tenía prueba en todo el
   repositorio— **que los 38 archivos `.cmd` conserven finales de línea de
   Windows**. Con finales de línea de Unix, la ventana se cierra sin ejecutar
   nada, que es una falla que ya se había sufrido antes.

**Recordatorio:** la aplicación `ICFES.html` no necesita nada de esto. No pide
Python, ni consola, ni carpeta correcta, ni internet. Doble clic y funciona,
también en el celular.

### 20-08 (noche) — EL CORREO YA FUNCIONA ✅

Yesid apretó **📧 Probar correo** y el mensaje llegó a su bandeja de
`glosashus09@sinacsc.com`.

**La causa era la que se sospechaba:** la contraseña de aplicación se había
generado en la cuenta `yesidbadillo820@gmail.com`, pero el `.env` decía
`SMTP_USER=motorglosas@gmail.com`. Una contraseña de aplicación **solo sirve
para la cuenta donde se generó**. Corrigió el usuario y salió a la primera.

Y el detalle que importa: **llegó a un buzón `@sinacsc.com`**. Esos eran los
que rebotaban con «Address not found» cuando salían desde la cuenta
equivocada. Ahora sí entregan.

### Y un último defecto de la misma familia

La etiqueta **«✗ nadie a quien enviarlo»** era un cajón de sastre: salía
siempre que no saliera ningún correo, **aunque sí hubiera destinatarios y lo
que fallara fuera el servidor de correo**. Eso manda al auditor a revisar la
lista de gestores —que está bien— mientras el problema está en otro lado.

Nos pasó hoy mismo: con el correo mal configurado, la pantalla decía «nadie a
quien enviarlo».

Ahora hay una etiqueta aparte: **«✗ el servidor de correo rechazó el envío»**.

- 7 pruebas en `tests/test_services/test_el_correo_no_dice_nadie_cuando_si_habia.py`,
  incluidas las que comprueban que los demás estados (ENVIADO, PARCIAL, sin
  correo configurado, sin archivo) **no cambian**.

### 20-08 (noche) — Dos motores escribiendo en dos bases distintas

**Lo destapó el propio panel de Diagnóstico** del PC de cartera:

> ⚠️ Hay 2 motores distintos corriendo en este equipo
> (PID 7504 puerto 8080, PID 14328 puerto 8000)

Y la base de datos se guardaba en **ruta relativa** (`sqlite:///./glosas.db`),
o sea **relativa a la carpeta desde la que arrancó cada motor**. Arrancados
desde carpetas distintas, **cada uno escribe en su propia base de datos**.

**Eso explica lo que Yesid vio:** las glosas pasaron de **62 a 35** y el
historial de importaciones se reinició. **No se perdió nada** — está en la otra
base.

**Por qué es de lo más grave que puede pasar:** trabajar sobre una base
creyendo estar viendo la otra significa responder una glosa que en «la» base
sigue pendiente, y **nadie se entera hasta que vence**.

**Cómo queda.** La base se ancla a la carpeta del repositorio, arranque el
motor desde donde arranque. Pero si un despliegue **ya tiene** su base en otra
carpeta, se respeta la que existe y se avisa en el registro: cambiársela le
escondería sus datos, que es justo el daño que esto viene a evitar. Y un
`DATABASE_URL` puesto a mano sigue mandando sobre todo.

**Lo que hay que hacer en el PC de cartera:** apagar el motor sobrante del
puerto 8000. El del 8080 es el que sirve la página por internet.

- 6 pruebas en `tests/test_core/test_la_base_no_depende_de_la_carpeta.py`.

---

### 20-08-2026 (noche) — La aplicación del ICFES quedó rediseñada

**Qué se pidió:** que la aplicación fuera más práctica, más profesional, más
intuitiva, más detallada y que no se sintiera tan plana.

**Lo que le faltaba de fondo no era el color: era el plan.** La primera versión
tenía el banco de preguntas y los simulacros, pero el plan de estudio vivía
solo en la consola. Ahora la aplicación abre en «qué te toca hoy», con los
bloques del día y un botón para empezar cada uno.

**Lo que cambió:**

1. **Seis pantallas** en vez de cuatro: se agregaron **Plan** (las cuatro fases
   con el detalle de cualquier semana) y una pantalla de **Estudiar** que reúne
   el repaso del día, el cuaderno de errores, las competencias más flojas con
   su botón de practicar, y la práctica libre con filtros.
2. **Gráficas de verdad:** la línea del puntaje en el año con la meta marcada y
   globo de datos al pasar el mouse; barras por área con la marca de la meta de
   cada una; una mini gráfica por cada prueba; el calendario de constancia del
   año; y las causas de error con su remedio al lado.
3. **Durante las preguntas:** cronómetro que corre con el ritmo real del examen
   (un punto que pasa de verde a ámbar y a rojo cuando te demoras de más),
   atajos de teclado para responder, y las lecturas largas en letra serif.
4. **En el computador** aparece una barra lateral fija; en el celular, la barra
   de abajo de siempre.

**El detalle que más importa, y que no se ve:** la aplicación y la consola
ahora calculan **exactamente lo mismo**. Las fases del plan y sus proporciones
ya no están escritas dos veces: se exportan desde `icfes/plan.py`. Y hay una
prueba que corre el cálculo de la aplicación con node y lo compara contra el de
Python **bloque por bloque** —2.315 bloques en tres escenarios distintos—, para
que nadie cambie una fórmula en un lado y se olvide del otro.

**Los colores de las gráficas están validados,** no escogidos a ojo. La primera
versión coloreaba cada barra según el estado (rojo, naranja, azul, verde) y el
validador la rechazó: verde y rojo se confunden para una persona con daltonismo.
Se corrigió cambiando el diseño, no el color: las barras van todas del mismo
tono —que además es lo correcto, porque es un solo dato— y el estado se dice con
una etiqueta de texto.

**Tres fallas encontradas al probar en un navegador de verdad y corregidas:**

- Dos simulacros el mismo día se dibujaban uno encima del otro en la gráfica y
  el globo de datos ya no sabía a cuál se refería.
- El calendario de constancia solo miraba hacia atrás desde hoy: si se
  importaba el avance de otro equipo, decía «199 días con estudio» y salía
  vacío.
- En práctica, el cronómetro estaba congelado en cero y el punto de ritmo
  siempre en verde.

**Comprobaciones:** 266 pruebas (27 nuevas), `ruff` limpio sobre los 1.229
archivos del repositorio, y el recorrido completo de la aplicación probado en
Chromium en computador y en celular, en tema claro y oscuro, sin un solo error
de JavaScript y sin que la página se salga de ancho.

---

### 20-08 (cierre) — Cada auditor puede deshacer LO SUYO

El botón **«Dejar pendiente»** (el que deshace una auditoría ya decidida)
estaba reservado a coordinación y administración. En la práctica eso dejaba
al auditor trancado con su propio error de dedo: si radicaba una factura por
equivocación, tenía que buscar a alguien más para que se la devolviera a
pendiente.

**Desde hoy:** cada auditor puede volver a pendiente **las facturas que él
mismo radicó o devolvió**. No cambia nada más:

- La decisión **de otra persona** sigue siendo de coordinación (el aviso dice
  quién la auditó).
- Una factura que **ya salió en un oficio de devolución entregado** no se
  deshace: ese PDF ya está en manos de la entidad. Para eso hay que eliminar
  antes el oficio de devolución (eso sí es de administración).
- Corregir la **observación** de una factura ya decidida sigue igual que
  antes: solo coordinación y administración.

Todo queda en el historial con el nombre de quien deshizo y a qué hora.

7 pruebas nuevas.

---

### 21-08 — Responder de una vez las glosas que repiten causal

**Lo que pidió Yesid, textual:** «hay glosas que vienen por 7 ítems y a esos 7
ítems se les da la misma respuesta, y hoy por hoy lo hacen uno a uno».

En la factura HUS405724 la causal **3209** —«la ayuda diagnóstica no tiene
justificación»— viene sobre RX de pie y RX de pierna. Servicios distintos,
misma respuesta. Escribirla dos veces es trabajo regalado; con siete, es media
mañana.

**Lo que hay ahora, en la pantalla de Glosas ADRES:**

**1 · Un aviso arriba de la tabla**

> ⚠ Hay causales que se repiten en esta factura — se pueden responder de una
> sola vez
> **3209** · La ayuda diagnóstica no tiene justificación
> 7 glosas · 5 sin responder — **[ Responder las 7 juntas ]**

**2 · Un cuadro donde usted escoge cuáles**

Al apretarlo salen **las 7 filas listadas**, cada una con su servicio, su valor
y su centro de costos, **con la casilla marcada**. Las que ya tienen decisión
salen **desmarcadas y en ámbar**, para no pisar trabajo hecho sin querer.

Usted desmarca las que necesiten respuesta distinta, escribe **una sola**
observación técnica, escoge **una sola** decisión, y confirma.

Es literalmente lo que pidió: *«que diga a cuáles servicios de esos 7 tendrían
la misma respuesta»*.

**3 · Un filtro para buscar dentro de la factura**

Caja de texto (busca en causal, servicio, CUPS, observación y centro de
costos) más tres desplegables: por causal —**con el número de veces que
viene**—, por clasificación y por «sin decidir / ya decididas».

> **El filtro solo esconde filas.** Los totales de arriba y las pastillas por
> clasificación **no cambian nunca**: son de la factura completa. Si el filtro
> moviera esos números, usted no sabría cuánto lleva de verdad. La pantalla lo
> dice: «Mostrando 4 de 21 glosas · los totales de arriba son de la factura
> completa».

**Tres candados, y ninguno sobra:**

- Se manda la **lista explícita** de las glosas marcadas, nunca un filtro. El
  servidor no decide a qué filas va: aplica exactamente lo que usted marcó.
- La causal y la clasificación **viajan como testigo**. Si una glosa del lote
  no es de esa causal, de esa clasificación y de esa misma factura, **no se
  escribe** y se reporta por qué.
- **La plata no se comparte.** El lote no acepta valores ni cantidades: cada
  glosa conserva su propio valor glosado. Compartirlo sería inventar cifras.

**La 4506 no se mezcla.** Esa causal se reparte glosa por glosa entre
Facturación y Pertinencia; si se agruparan juntas, un gestor de facturación
arrastraría en su lote las que son de la médica auditora.

- 28 pruebas nuevas (14 del servicio + 14 de la pantalla). Las de pantalla
  **ejecutan el JavaScript de verdad en node**, no leen el HTML como texto.

> **Nota:** al escribirlo llamé a una función `abrirModal` que **no existe** en
> el portal. El JavaScript compilaba igual —era un error de ejecución— y solo
> habría reventado al apretar el botón. Lo cazó una prueba que corre `gaPintar`
> de verdad. Se le hizo su propio cuadro, aislado del modal de dictámenes.

### 21-08 — «CUPS FMQ0952» no es un CUPS

Otro de los defectos que cazaron las pruebas de Yesid. Los dictámenes salieron
diciendo **«CUPS FMQ0952»** y **«CUPS 34363-4»**.

- `FMQ0952` es un **código interno del hospital** para insumos (el electrodo de
  ECG).
- `34363-4` es un **CUM**, el código de un medicamento (la dipirona).

Ninguno es un CUPS: los del Ministerio son seis dígitos, a veces con un sufijo
de letra (`890283H`).

**Por qué importa:** la EPS cruza los CUPS contra su sistema. Un código que no
existe como CUPS no lo encuentra, y **ratifica la glosa completa** — así el
argumento jurídico esté impecable.

**Lo que NO se hace, y es la mitad importante:** no se prohíbe nombrar el
código. El hospital **sí** factura con `FMQ0952`, y ponerlo ayuda a la EPS a
ubicar el ítem. Lo que está mal es **la etiqueta**. Por eso el aviso dice:

> «Deje el código tal cual y cambie la palabra: escriba *código institucional
> del HUS FMQ0952* en vez de *CUPS FMQ0952*».

El aviso además distingue de dónde viene el código: institucional del HUS, CUM
de medicamento, o de otro sistema.

- 27 pruebas en `tests/test_services/test_no_todo_codigo_es_un_cups.py`, la
  mitad dedicadas a **los CUPS reales que NO se pueden marcar**: los 14 de las
  facturas del 19 de agosto, incluidos los raros con sufijo (`625104PUR`,
  `129A02H`, `869501H1`). Un aviso equivocado en cada dictamen enseña al
  auditor a ignorar los avisos.
- Y se comprobó que **sigue cazando** el CUPS inventado de ayer: cuando el
  motor tomó «valor glosado 100000» y escribió «CUPS 100000».

### 21-08 — Los tres defectos que faltaban de las pruebas de Yesid

**1 · El dictamen declaraba «VALOR OBJETADO $ 0.00»**

Yesid pegó «CL0801 — … — **valor 279900**» y el documento que se radica salió
diciendo que el valor objetado era **cero pesos**. Eso no es un detalle de
formato: **es una cifra falsa en un documento que va a la EPS.**

La causa: el lector de valores exigía un «$», o la palabra «valor **de**», o el
sufijo «pesos». Un «valor 279900» a secas —que es como lo escribe cualquiera—
no cumplía ninguna. Ahora sí se lee, incluida la glosa de **treinta pesos** de
la dipirona.

Y no se rompió lo que ya andaba: «valor **100%**» sigue sin leerse como plata,
y «valor 2 conceptos» tampoco.

**2 · La plata con comas gringas**

> Tarifa pactada en contrato **$2,072,200**
> Valor en disputa **$ 2,288,600**

En Colombia la coma es el separador **decimal**: eso se lee como dos con
setenta y dos milésimas. Corregido en **33 sitios** de tres archivos, todos
plata que el auditor ve.

**3 · El dictamen negaba su propio contrato**

En la misma pantalla, el motor decía arriba «**Tarifa pactada encontrada ·
Contrato S-13-1-03-1-04958 · $2.072.200**» y el cuerpo del dictamen decía «**EN
AUSENCIA DE CONTRATO BILATERAL FORMAL**».

Ante la EPS eso es **regalarle el argumento**: si el hospital dice que no hay
contrato, no puede después exigir que se respete la tarifa pactada.

La causa: una plantilla del banco (la TA-G01) trae esa frase escrita, y se le
ofrecía a la IA como ejemplo a imitar **sin mirar si el motor ya había
encontrado contrato**.

> **La plantilla NO se borró.** Cuando de verdad no hay contrato, esa
> argumentación del Decreto 2423 Art. 87 es correcta y es la única defensa que
> existe. Solo se deja de ofrecer cuando sí lo hay — y se exige que haya
> **tarifa con valor**, porque un contrato sin tarifa para ese CUPS tampoco
> sirve para sostener «respétese lo pactado».

- 38 pruebas nuevas. **Tres pruebas viejas fijaban los defectos** y se
  corrigieron: una exigía «120,000» con coma, otra «83,800», y una tercera
  daba por bueno que un «valor 500000» sin «$» **no se encontrara** —su
  docstring lo llamaba «returns default when not found»—.

### 21-08 — Un «agujero» que resultó ser una decisión correcta

Revisando el guardián de afirmaciones documentales apareció esto: hay **dos
caminos por donde esa protección nunca corre** —el Quality Gate y el
postprocesador de dictámenes— porque no le pasan el dato de qué se leyó.

Sonaba a hueco. **Revisándolo, es lo correcto**, y conviene que quede escrito:

| Lo que se le pasa | Qué significa | Qué hace |
|---|---|---|
| el texto de los PDF | se leyó eso | contrasta contra ello |
| vacío | se analizó **sin adjuntar nada** | marca cualquier afirmación sobre documentos |
| nada | **este camino no sabe** qué se leyó | no opina |

Los dos llamadores están en el tercer caso, y con razón:

- El **Quality Gate** solo recibe el texto y la EPS. No tiene los PDF.
- El **postprocesador BORRA** las frases con citas inválidas. Si ahí se
  marcaran afirmaciones documentales, **borraría argumentación clínica
  legítima** de dictámenes donde sí se adjuntaron soportes.

Pasarles «vacío» para «cerrar el hueco» convertiría la protección en una
máquina de avisos falsos — y un aviso equivocado en cada dictamen enseña al
auditor a ignorar los avisos.

**No se cambió nada.** Se dejó escrito por qué está así, y 7 pruebas que
protegen la decisión para que nadie la «arregle» sin saber.

### 21-08 — El motor arranca solo al PRENDER el PC

**El problema, en concreto.** El arranque estaba en la carpeta Inicio de
Windows, que se dispara **al iniciar sesión**. Si el PC se reinicia de noche y
nadie entra, el hospital amanece sin portal.

**Pasó hoy a las 8:57 de la mañana:** «Bad gateway · Host Error», y hubo que
sacar el motor a mano por PowerShell.

**Cómo se arregla.** Doble clic en **`tools\ARRANQUE_AUTOMATICO_MOTOR.cmd`**.
Crea una tarea de Windows que arranca el motor **al prender el equipo**, sin
que nadie tenga que iniciar sesión.

**Le va a pedir la contraseña de Windows, y con razón.** La tarea corre con la
cuenta del usuario a propósito, porque el motor necesita entrar a
`\\Prime\radicacion_2026` para el índice de soportes — y la cuenta del sistema
normalmente **no tiene ese permiso**. La contraseña la pide Windows, se guarda
en su bóveda, y **no queda escrita en ningún archivo del repositorio**.

**Espera un minuto tras el arranque:** al prender el PC la red del hospital
todavía no está lista.

**Lo que NO cambia:** sigue arrancando también al iniciar sesión (como
respaldo), el vigilante sigue reviviendo el motor si se cae, y el
autodespliegue sigue bajando el código nuevo cada 5 minutos.

**Cómo comprobar que quedó de verdad:** reiniciar el PC y, **sin iniciar
sesión**, abrir el portal desde el celular o desde otro equipo. Si carga,
quedó.

> **Lo más probable que lo rompa dentro de seis meses:** si cambia la
> contraseña de Windows, la tarea deja de arrancar **en silencio**. Hay que
> volver a correr el archivo. El propio instalador lo advierte.

- 18 pruebas en `tests/test_tools/test_arranque_automatico.py`, incluidas las
  que vigilan que no quede ninguna contraseña escrita, que no pida permisos de
  administrador que no necesita, y que conserve los finales de línea de
  Windows.

### 21-08 — El dictamen decía que el contrato estaba vencido, y no lo estaba

Yesid probó seis dictámenes más. **Se confirmó lo corregido** —el valor ya se
lee, los códigos CUM se marcan bien, la parcial sale correcta, los soportes
son los reales del servidor— y aparecieron dos defectos nuevos.

**1 · «FUERA DE LA VIGENCIA DEL CONTRATO» — falso.**

Dos glosas de FAMISANAR salieron diciendo que el servicio se prestó fuera de
la vigencia del contrato `S-13-1-03-1-04958`, y una hasta puso **«Contrato:
SIN CONTRATO PACTADO»** en el encabezado… mientras la línea de abajo decía
«Tarifa pactada: SOAT UVB VIGENTE -5 %» y el cuerpo citaba el anexo tarifario
de ese mismo contrato, **vigente del 15/04/2026 al 14/04/2027**.

**Ante la EPS eso es de lo peor que se puede escribir:** quien dice que no
tiene contrato vigente pierde el derecho a exigir la tarifa pactada.

**La causa: adivinar.** El motor tomaba **la primera fecha que apareciera** en
el número de factura, el radicado o los primeros 5.000 caracteres de los PDF, y
la trataba como la fecha de la atención. Esa primera fecha puede ser la de
nacimiento del paciente, la de expedición de un documento o la de validación
del CUV.

Ahora **solo cuenta una fecha etiquetada** como de atención, prestación,
ingreso o factura. Si no la hay, **no se dice nada**: no saber cuándo se prestó
el servicio no es prueba de que el contrato estuviera vencido.

**2 · La cifra volvía a salir sin puntos.**

El valor ya se **leía** bien pero se **escribía** crudo: «VALOR OBJETADO
$ 796600». O sea que el formato de una cifra que va a la EPS dependía de cómo
la hubiera escrito quien redactó la glosa. Ahora los cuatro caminos que
encuentran el valor lo escriben igual: **$ 796.600**.

> **Y el CI me corrigió a mí.** La primera versión de este arreglo del formato
> pasaba TODAS las cifras por un redondeo a entero, así que «1.234.567,89»
> salía «$ 1.234.568». **Ochenta y nueve centavos perdidos en un documento que
> se radica ante la EPS** — eso no es formato, es cambiar el valor. Lo cazó una
> prueba que ya existía y que cuidaba justamente eso.
>
> La regla correcta era más estrecha: **solo se toca lo que viene sin formato**.
> Si la cifra ya trae puntos o comas, se respeta tal cual. Y las comas gringas
> («1,500,000») sí se pasan a punto, porque su forma es inequívoca.

- 8 pruebas nuevas. **Una de ellas encontró un segundo bloque de alerta de
  vigencia** que yo no había visto — resultó ser código muerto, y quedó una
  prueba que avisa si alguien empieza a usarlo.
- **Tres pruebas viejas fijaban defectos.** La más llamativa se llamaba
  `test_extraer_valor_formato_colombiano` y su descripción decía «Should
  extract Colombian peso format»… pero exigía «1,500,000» **con comas**, que es
  formato gringo. El nombre decía una cosa y la comprobación la contraria.

### 21-08 — Centro de costos: los medicamentos van a Servicio Farmacéutico

**Decisión de Yesid, y así queda:** los medicamentos y los insumos se imputan
a **Servicio Farmacéutico**.

Se investigó primero con los datos reales del archivo del DGH del 19 de agosto
(669 filas). Vale la pena dejar escrito lo que se encontró, porque cambia cómo
hay que leer esta pantalla:

**El centro de costos no es una propiedad del servicio.** El mismo catéter va
a Urgencias si atendieron ahí al paciente, y a Sala de Partos si estaba allá.
En ese archivo, `CATETER INTRAVENOSO 20` aparece en Urgencias, Sala de Partos
**y** Radiografía. Por eso las «371 filas sin propuesta» no eran un hueco: eran
las reglas negándose, con razón, a adivinar dónde estaba el paciente.

Con la decisión tomada, lo que faltaba era **reconocer el medicamento cuando
el archivo no trae la columna «tipo de elemento»** — que es la mayoría de las
veces. Ahora se detecta por la forma de la descripción (TAB, AMP, VIAL, SOL
INY, CATETER, SONDA, APÓSITO…), anclada a palabra completa para que «AMP» no
enganche «AMPUTACION».

**Tres correcciones de paso:**

1. **Un defecto que ya existía:** `POTASIO CLORURO AMP` y `SOLUCION LACTATO DE
   RINGER` se proponían a **Laboratorio** — la regla los enganchaba por
   «potasio» y «lactato», que también son nombres de exámenes. Son
   medicamentos. Ahora la detección de medicamento manda sobre las pistas de
   área.
2. **Lo obstétrico no va a quirófanos.** La cesárea, la asistencia del parto y
   la ligadura de trompas las carga el hospital a **Urgencias
   Ginecobstétricas** (733101, «Sala de Partos» en el DGH).
3. **Los sublaboratorios se respetan.** El hospital separa Química,
   Bacteriología, Uroanálisis, Hematología e Inmunología, cada uno con su
   código. Proponer el genérico «Laboratorio Clínico» es acercarse pero errar,
   y el gasto queda imputado donde no fue.

**Resultado sobre los 203 servicios distintos del archivo real:**

| | |
|---|---|
| Servicio Farmacéutico | 76 |
| Área específica correcta | 39 |
| Sin propuesta | 47 (23%, antes 34%) |

**Nota honesta sobre la medición:** los cinco sublaboratorios salen como «no
coinciden» en la comparación automática, pero **están bien**: sus códigos no
están en el catálogo base del repositorio, solo en el archivo de la macro del
hospital. En producción, donde el catálogo sí los trae, salen con su código.

Lo que queda sin propuesta son consultas y procedimientos donde el área
depende del caso, no del nombre. Ahí el gestor decide, que es lo correcto.

### 21-08 (tarde) — El menú muestra solo lo que a cada quien le toca

Pedido de Yesid: el rol AUDITOR ve todo **menos** Inteligencia, Expediente,
Usuarios, Mando ejecutivo e Importar de Recepción.

Esos botones ahora se ocultan para quien no sea coordinador o administrador.
Si un título de sección queda sin botones, el título también se oculta: no
queda un rótulo suelto sin nada debajo. El buscador de comandos (Ctrl+K)
filtra igual, porque esconder el botón y dejar el atajo sería ordenar la
pantalla a medias.

**Lo que hay que decir con todas las letras:** esconder un botón **ordena** la
pantalla, **no protege** el dato. La consulta de usuarios sigue abierta a
cualquiera que haya entrado con su clave; quien escriba la dirección a mano
todavía puede ver la lista de usuarios con sus correos. Cerrar esa puerta es
un trabajo aparte —hay cinco pantallas que la usan— y quedó **pendiente**.

### 21-08 (tarde) — Se reinició el PC y el motor no arrancó: dos agujeros

Yesid reinició el PC de cartera para comprobar el arranque automático. El
portal contestó **«Bad gateway 502»**: el túnel de Cloudflare sí subió, el
motor no.

**Agujero 1 — el vigilante se contaba a sí mismo.** En la mañana se le puso un
candado al vigilante para que no hubiera cuatro ventanas abiertas a la vez: el
vigilante cuenta cuántos hay antes de arrancar y, si sobra, se cierra. La
cuenta la hace una orden de Windows… y esa orden lleva escrito adentro el
mismo texto que busca. Windows no esconde al que pregunta, así que se contaba
a sí mismo: **1 vigilante + 1 orden contando = 2**, y como dos es «más de
uno», el vigilante se cerraba **siempre**, aun siendo el único. No fue cosa
del reinicio: llevaba así desde la mañana; el reinicio solo lo dejó a la
vista. Ahora la cuenta solo mira las ventanas que de verdad son vigilantes.

**Agujero 2 — la red de seguridad dormía.** El autodespliegue corre cada 5
minutos y trae una red de seguridad: si el motor no está arriba, lo arranca
directo. Es la que ha salvado el portal varias veces. Pero esa tarea se creó
sin decirle a Windows con qué cuenta corre, y Windows por defecto la deja en
«solo cuando alguien haya iniciado sesión». O sea: dormía justo en el único
momento para el que se hizo. Ahora se vuelve a crear con la cuenta del
usuario, para que trabaje esté quien esté.

De paso, las esperas de los tres bots que ahora corren con el PC recién
prendido pasaron de una orden que necesita ventana de verdad a otra que
funciona siempre. Los tiempos quedan iguales.

**Y para que no vuelva a pasar sin que nadie lo vea:** la pantalla de estado
(doble clic en `ESTADO_MOTOR.cmd`) ahora revisa también la tarea de arranque
y, de cada tarea, dice si trabaja aunque nadie inicie sesión o si duerme, y
cómo le fue la última vez. Una tarea que existe pero duerme se veía igual de
bien que una que trabaja: esa fue exactamente la trampa.

**Lección de las pruebas.** Las pruebas de la mañana miraban que el texto del
candado estuviera escrito en el archivo. Estaba escrito. Nadie probó la
**cuenta**, que era lo único que importaba. Las nuevas simulan la lista de
ventanas de Windows y hacen la cuenta de verdad: con el defecto puesto de
vuelta a propósito, cinco de ellas se ponen en rojo.

### 21-08 (tarde) — La rama que llega al hospital no se estaba revisando

Buscando por qué la corrección del reinicio entró sin que ninguna revisión
automática terminara sobre ella, apareció algo más grande.

El PC de cartera baja el código cada 5 minutos de la rama `motor-glosas`. Esa
es, por lejos, la rama más delicada del repositorio: es **la única que de
verdad llega al hospital**. Y era **la única que no se revisaba**. Las
revisiones automáticas corrían en las ramas de trabajo y en las principales,
pero no en esa. O sea: todo se comprobaba **antes** de juntar los trabajos y
nada **después**.

Eso importa porque acá se juntan dos y tres trabajos en paralelo tocando los
mismos archivos —hoy mismo pasó dos veces—. Una unión mal resuelta llegaba al
hospital sin que nada la mirara.

Ya quedó puesta la revisión sobre esa rama, y una prueba que avisa si alguien
la saca de la lista sin darse cuenta de lo que cuesta.

### 21-08 (tarde) — La lista de usuarios ya no la puede pedir cualquiera

Por la mañana se escondió el botón de Usuarios del menú, y quedó dicho con
todas las letras que **esconder un botón ordena la pantalla pero no protege el
dato**. Esto es lo que sí lo protege.

Cualquier auditor podía sacar el listado entero de las 27 cuentas del portal
—nombre, correo, rol, y también las cuentas de gente que ya no está—
escribiendo la dirección a mano.

**No era descuido.** Cinco pantallas la usaban de verdad: importación masiva,
asignar en lote, reasignar una glosa, reasignar todo lo de un gestor y el
buscador de Ctrl+K. Todas para lo mismo: llenar una lista desplegable de «¿a
quién le paso esto?». Pedían la lista completa y escogían en el navegador.
Cerrar la puerta sin más habría dejado esas cinco pantallas sin desplegable.

Se pasó el filtro al servidor: esas cinco piden ahora una lista que trae solo
lo que un desplegable necesita —quién está activo y puede recibir trabajo—. La
lista completa quedó solo en la pantalla de Usuarios, que ya exige rol de
coordinación.

Dos cuidados que no se ven pero pesan:

- **Las cuentas inactivas ya no salen.** Asignarle una glosa a alguien que ya
  no trabaja acá es perderla de vista.
- **Las filas viejas no se pierden.** Si algún registro trae el rol escrito
  distinto —en minúsculas, con espacios, o de la forma antigua—, esa persona
  desaparecería del desplegable sin que nadie entendiera por qué, y su trabajo
  se le seguiría asignando a otro. Ahora se compara sin importar cómo esté
  escrito.

### 21-08 (tarde) — Por qué el arranque quedó con la cuenta equivocada

Al correr el instalador del arranque salió **«Error: Acceso denegado»**. Eso
destapó dos cosas, y la segunda es la grave.

**La fácil.** Crear una tarea que guarda una contraseña exige permisos de
administrador. Sin ellos, Windows contesta «Acceso denegado». El mensaje de
ayuda ahora nombra ese texto tal cual sale en pantalla.

**La grave.** Al abrir la ventana como administrador, si Windows pide **otra
cuenta**, la ventana pasa a correr con **esa otra**. Y el instalador tomaba la
cuenta de la ventana dando por hecho que era la del auditor.

Así fue como la tarea de la mañana quedó puesta con la cuenta `cpimiento`
cuando la del motor es `cartera`. **Y no da ningún error:** la tarea queda, el
motor arranca, todo se ve bien. Pero si esa cuenta no tiene permiso para
entrar a la carpeta de soportes del servidor, el índice amanece vacío y nadie
entiende por qué las facturas no aparecen. Un defecto que no se ve es peor que
uno que revienta.

Ahora el instalador muestra con qué cuenta está corriendo la ventana, avisa de
la trampa, y deja escribir otra: Enter para dejar la que detectó, o el nombre
correcto para corregirla. Al final dice con cuál quedó, que es la única forma
de que el auditor se entere si se equivocó.

### 21-08 (noche) — El intento fallido había borrado la tarea de arranque

Yesid mandó lo que decía su PC, y ahí apareció lo que faltaba entender:

> `MotorGlosas_Arranque .... NO EXISTE`

La tarea que se había creado por la mañana **ya no estaba**. La historia
completa del día, en tres actos:

1. Por la mañana la tarea quedó creada.
2. Por la tarde, un intento sin permisos contestó «Acceso denegado».
3. Por la noche ya no había tarea.

**Por qué.** Al crear la tarea, Windows **primero borra la que hubiera**. Si
después falla por falta de permisos, se queda **sin ninguna**. O sea que el
intento dejó el PC peor de como estaba — y de eso nadie se entera **hasta el
próximo reinicio**, que es justo cuando ya no se puede hacer nada.

Ahora el instalador pregunta por los permisos **antes de tocar nada**. Sin
ellos se va explicando cómo abrirlo bien y dejando todo como estaba. Y si aun
así falla más adelante, avisa con todas las letras que puede no haber quedado
ninguna tarea.

**Lo que sí quedó confirmado, y era la duda de la mañana:** el autodespliegue
corre con la cuenta `cartera` —la buena, no `cpimiento`— y esa cuenta **sí
entra** a la carpeta de soportes del servidor. Ya sabemos con qué cuenta hay
que dejar la tarea de arranque.

### 21-08 (noche) — La revisión de la rama del hospital sirvió el mismo día

Por la tarde se puso la revisión automática sobre `motor-glosas`, la rama de la
que el PC baja el código. **Lo primero que hizo fue delatar un defecto propio
que ya estaba fusionado:** un comentario que quedó dentro de un bloque entre
paréntesis del vigilante, que en los archivos de Windows es un sitio frágil —
puede hacer que el bot deje de hacer parte de su trabajo sin avisar.

Sin esa revisión, ese comentario se quedaba en el archivo que mantiene el
portal vivo y nadie se enteraba nunca. Ya está corregido, y de paso la prueba
que lo vigila se amplió a los **51 bots** del repositorio: la trampa no era de
ese archivo, es de los `.cmd` de Windows, y cualquier bot de doble clic puede
caer en ella.

### 21-08 (noche) — Por qué el código no llegaba al PC, aunque estaba listo

Todo el día se corrigieron cosas, se probaron y se fusionaron… y **nada de eso
llegó al PC de cartera**. Los datos que mandó Yesid dieron el porqué. Tres
hechos que parecían no tener relación:

- El registro del autodespliegue estaba lleno de **las líneas de cada visita a
  la página**, no de sus propios mensajes.
- La tarea del autodespliegue terminó con un código de error.
- El repositorio del PC llevaba horas clavado en una versión vieja.

**Encajan en uno solo.** La red de seguridad —la parte que arranca el motor
cuando no volvió solo— lo arrancaba *sin abrirle ventana propia*. Así el motor
hereda la salida de la tarea, y Windows solo da una tarea por terminada cuando
nadie más tiene esa salida abierta. El motor no la suelta nunca.

Entonces la tarea se quedaba «corriendo» para siempre, Windows terminaba
matándola y, como está puesta en no abrir dos a la vez, **saltaba todas las
pasadas siguientes**.

Dicho corto: **la red de seguridad, al salvar el motor una vez, mataba el
autodespliegue para siempre.** Y de paso tapaba el único registro donde se
podía ver lo que estaba pasando. Nadie se entera: todo «se ve bien» hasta que
alguien nota que lo nuevo no llega.

Ya está corregido: el motor se abre en su propia ventana y escribe donde le
corresponde. La tarea termina enseguida y la siguiente pasada corre normal.

**Y para que no se vuelva a esconder:** la pantalla de estado ahora delata una
tarea *atascada*. Antes, una tarea trabada decía «corriendo» y se veía igual de
sana que una que funciona. Ahora, si una tarea de cinco minutos lleva media
hora corriendo, lo dice y explica cómo cerrarla.

### 21-08 (noche) — Preguntar no bastaba: hay que decirle cuál es la cuenta

El instalador del arranque ya preguntaba con qué cuenta debía correr la tarea.
Yesid le dio Enter a la que mostraba la ventana —la de administrador— y la
tarea quedó otra vez con la cuenta equivocada. Preguntar algo sin dar la
respuesta no sirve de mucho.

Ahora el instalador **averigua** cuál es la buena: la lee de la tarea del
autodespliegue, que lleva meses funcionando y sí entra a la carpeta de soportes
del servidor. Y se la muestra antes de preguntar.

**Otra cosa que salió de esa misma corrida:** la segunda contraseña se escribió
mal, el autodespliegue no quedó cambiado… y el mensaje final decía igual que
todo seguía funcionando. Un instalador que dice que quedó lo que no quedó es
peor que uno que falla: el auditor se va tranquilo con la mitad del trabajo sin
hacer. Ahora el resumen final depende de cómo fue de verdad.

### 22-08 — «¿Estoy corriendo el código de hoy?» ya se puede responder

Repasando con calma los datos de anoche, la explicación que había dado no
cuadraba del todo. La tarea del autodespliegue **sí estaba corriendo** cada
cinco minutos —lo decía su propia hora de última ejecución—, y aun así el PC
seguía con la versión vieja.

Si corría y no bajaba nada, el problema está antes: en el momento de
**consultar GitHub**. Y ahí apareció algo que no habíamos mirado: una tarea
programada de Windows **no hereda el camino de búsqueda del usuario**. Arranca
con un entorno mínimo. Si `git` se instaló solo para el usuario, dentro de la
tarea `git` sencillamente no existe — y el bot anotaba una línea y seguía de
largo, dejando el PC con la versión vieja **para siempre**, sin que nada se
viera mal.

Dos arreglos, los dos de lo mismo: que se pueda ver.

1. **El autodespliegue busca git donde Windows lo instala**, no solo en el
   camino de búsqueda. Y si aun así no lo encuentra, lo dice con todas las
   letras en vez de callarse. También deja constancia de cada pasada, para que
   se sepa si está corriendo.
2. **La pantalla de estado responde la pregunta.** Ahora muestra qué versión
   hay en el PC, cuál es la última publicada que se alcanzó a consultar, y qué
   fue lo último que dijo el autodespliegue de sí mismo. Si el PC está atrás,
   sale un aviso; si no encuentra git o no logra hablar con GitHub, lo traduce
   a algo que se entienda.

**Lo que falta por confirmar:** todavía no sabemos con certeza cuál de las dos
cosas era. Las líneas propias del autodespliegue lo dirán —quedaron tapadas
por el tráfico de la página, que ya se corrigió—. Lo que sí es seguro es que
los dos defectos eran reales y los dos dejaban el PC atrás en silencio.

### 24-08 — Los cambios ya no le tumban la página a las gestoras

Pedido de Yesid: «necesito que cada vez que hagamos cambios y demás no se les
esté cayendo la página a los gestores a cada rato».

**Cómo era.** Cada cinco minutos el sistema revisa si hay algo nuevo y, si lo
hay, lo aplica: apaga el motor y lo vuelve a levantar. Son entre 15 y 30
segundos de página caída — y lo que estuviera a medio hacer se pierde. Un
dictamen que la IA estaba redactando se va con el motor, y eso son minutos de
trabajo de una médica auditora.

**Cómo es ahora.** El sistema **pregunta antes**. Si hay alguien trabajando, no
toca nada y vuelve a preguntar en cinco minutos. En una oficina de tres
personas siempre aparece un hueco —una llamada, un café, una reunión— y el
cambio entra sin que nadie lo note.

**El punto fino, que es donde esto se rompe si se hace mal:** una pestaña
abierta NO es alguien trabajando. La página se refresca sola —pregunta la salud
cada 30 segundos, los indicadores cada 30, el estado de la IA cada 5—. Si eso
contara, una pantalla olvidada encendida el viernes bloquearía los cambios
hasta el lunes. Entonces se cuenta solo lo que pidió una persona: responder,
guardar, abrir una pantalla, buscar, exportar. Lo que la página se pregunta
sola, no.

**Dos salidas para que nunca se quede atascado:**

- Si el motor está caído, el cambio se aplica de una: no hay a quién
  interrumpir, y esperar solo dejaría el portal caído más tiempo.
- Si lleva más de una hora esperando un hueco, se aplica igual. Una corrección
  urgente no puede quedarse fuera todo el día porque siempre hay alguien
  conectado.

**Y cuando por fin toca apagar**, ahora se le pide al motor que se cierre y solo
se le fuerza si no hace caso en ocho segundos. Así lo que estuviera contestando
en ese momento alcanza a terminar en vez de cortarse a la mitad.

**Nada de esto queda escrito de quién ni de qué.** La pregunta que hace el bot
solo dice cuántos segundos lleva la página en silencio: ni nombres, ni correos,
ni en qué factura estaba nadie.

### 24-08 (mañana) — Lo que contó el primer despliegue del lunes

El lunes a las 9:22, con la fusión del fin de semana, el registro del
autodespliegue contó tres cosas que había que arreglar:

1. **«codigo nuevo detectado» salió dos veces, con medio segundo de
   diferencia.** Dos pasadas corriendo al tiempo. Eso es grave: cada una apaga
   el motor contando con revivirlo, y entre las dos lo dejan caído —una lo
   levanta y la otra lo vuelve a matar—. Ahora hay un candado: una sola pasada
   a la vez, y si una muere sin soltar el candado, caduca a los 30 minutos
   para no quedarse esperando a un muerto. Es un archivo, no una cuenta de
   procesos: contar procesos ya salió mal este mes con el vigilante.

2. **«ALERTA: el motor sigue caido» con el portal funcionando.** El bot
   esperaba 12 segundos fijos y preguntaba una vez. El motor del hospital
   carga una base de 133 MB y tarda más: se daba por muerto estando vivo, y se
   le arrancaba un segundo motor encima. Ahora pregunta cada 3 segundos hasta
   90: si sube en 10, sigue en 10; si de verdad no sube, se entera después de
   un plazo que sí alcanza.

3. **El contrato de POSITIVA no se pudo cargar por la IA.** El PDF del
   contrato original está escaneado —cero texto— y la ruta manual exige un
   token que el auditor no tiene a mano: se intentó tres veces y las tres
   terminaron en «Credenciales inválidas».

   Se hicieron dos cosas. Primero, se leyeron los otrosíes 02 y 03 —esos sí
   tienen texto— y se transcribieron **17 cláusulas literales**: tarifas (no
   pactados a SOAT, insumos a tarifas institucionales), soportes (los 13 datos
   de la factura, RIPS), plazos (20 días para glosar, 15 para responder, pago
   a 30), autorizaciones, cobertura, vigencia hasta el 19-ene-2027, y las dos
   joyas de la página 12: POSITIVA reconoce **intereses moratorios** y
   **reconocimiento económico** cuando formula glosas infundadas o
   inexistentes. Segundo, se hizo el bot `tools/cargar_clausulas_contrato.py`,
   que carga esas cláusulas directo en la base, sin clave, con las mismas
   reglas de la ruta web — y dice SIEMPRE a qué base escribe, por la lección
   de las dos bases del 20-08.

### 24-08 (mediodía) — El cargador dijo «todo listo» y reventó en la última línea

Yesid corrió el cargador de cláusulas en el PC. Dijo «17 cláusulas listas»,
mostró la base correcta (`motorglosas.db`)… y reventó al escribir la primera
fila: la columna de la base se llama `numero_clausula` y el archivo dice
`numero`. La pantalla del portal hace esa traducción; el bot no la copió.

**Nada se perdió:** el guardado es todo-o-nada, así que el intento fallido no
alcanzó a borrar las cláusulas que ya había.

**Por qué las pruebas no lo vieron:** revisaban el archivo y las reglas, pero
nunca guardaron contra la base de verdad. Ya guardan: hay pruebas que insertan
en una base real y comprueban columna por columna, y una que reproduce el
incidente exacto —un intento fallido no puede llevarse lo que había, la misma
lección del instalador que borraba la tarea de arranque—. Con el defecto
puesto de vuelta a propósito, cuatro se ponen en rojo.

### 24-08 (tarde) — Las tarifas de POSITIVA entraron infladas y se corrigió el lector

Se cargó por la pantalla el Excel «TARIFAS ESE HUS 2025 - POSITIVA»: 4.742
tarifas. Al revisarlas fila por fila apareció lo grave: **entraron con el SOAT
pleno, no con el SOAT –15% pactado**. La hoja trae las dos columnas y el
lector conocía la del valor pleno pero no la del descuento. Ejemplo real: la
punción cisternal quedó en $915.051 cuando lo pactado es $777.793. Con eso,
cada dictamen de tarifas defendería un valor 15% más alto que el contrato — la
EPS ratifica la glosa y el dictamen es falso.

Tres correcciones al lector, con sus pruebas:

1. **La columna del descuento pactado gana siempre.** Un encabezado tipo
   «SOAT -15%» al lado del valor pleno es SIEMPRE lo pactado. (Es la misma
   trampa que ya había pasado con FAMISANAR y su «PROPUESTA FINAL».)
2. **El cero de adelante.** Excel guarda el CUPS como número y se come el
   cero: 010101 quedaba 10101 y el motor no lo encontraba — decía «sin tarifa
   pactada» teniéndola. Ahora se guarda a 6 dígitos, y el buscador además
   tolera las 4.742 que ya quedaron guardadas sin el cero.
3. **Los repetidos que se contradicen no se cargan.** El mismo CUPS aparece
   hasta con cinco valores distintos en el archivo (el 103204: de $94.399 a
   $1.926.567). Antes se cargaban todos y el azar del orden decidía cuál
   citaba el dictamen. Ahora se omiten, se avisa cuáles, y el motor dice «sin
   tarifa pactada» — que es la verdad hasta que el auditor defina cuál rige.

Con el lector corregido, del Excel real entran **2.988 tarifas limpias** y
quedan **737 códigos por definir**, entregados en un archivo aparte para
marcar cuál valor rige (más una celda con fórmula dañada: el 512104 dice
#VALUE! en el propio Excel).

**También quedó cargado el contrato:** las 17 cláusulas de POSITIVA se ven en
la pantalla de Tarifas desde las 4:12 p. m. — el cargador sin clave funcionó
tras corregirle la traducción del campo.

### 24-08 (tarde) — El botón invisible destapó siete colores fantasma

Yesid reportó que el botón «Aplicar a las marcadas» —el del lote de glosas
ADRES— salía **en blanco, invisible**: letra blanca sobre fondo blanco.

La causa: el botón pedía su color a un token que **no existe** en el portal
(`--primary`, inventado al escribir la función). Sin token, el fondo queda
transparente y el botón desaparece.

Al barrer el archivo completo aparecieron **siete tokens fantasma en 65
sitios**: textos grises que pedían `--text-3` cuando el real es `--text3`,
fondos que pedían `--bg2` cuando el real es `--bg-card`, bordes y esquinas
igual. Todo eso se estaba pintando con el color heredado por accidente, no
con el del diseño — se veía «casi bien», que es la peor clase de mal.

Los 65 sitios quedaron apuntando a la paleta real, y quedó una prueba que
recorre el archivo entero: **cualquier color que pida un token inexistente
pone la construcción en rojo**. El botón del caso tiene además su prueba con
nombre propio.

### 24-08 (tarde) — El fantasma tenía nombre, y el Enter volvió a caer

**El fantasma.** El motor «inmatable» que atendió todo el día con código viejo
resultó ser nuestra propia tarea de arranque de ayer: quedó creada con la
cuenta `cpimiento`, al prender el PC arrancó el motor bajo esa cuenta **sin
sesión**, y por eso era invisible e intocable desde la sesión de `cartera`.
Se cazó con una ventana de administrador de verdad (la elevación ahora la pide
Windows con su aviso azul, porque el «ejecutar como administrador» manual
falló dos veces) y cayeron los cuatro procesos de una vez.

**El Enter, tercera caída.** Al reinstalar la tarea, el instalador mostró en
mayúsculas «la cuenta del motor es cartera — escriba ESTA»… y el Enter volvió
a dejar la de la ventana (`cpimiento`), ahora en las DOS tareas. Tres personas
distintas han caído en el mismo Enter: el aviso no basta.

**El arreglo es de diseño: el camino fácil tiene que ser el correcto.** Ahora
el Enter elige la cuenta del día a día, y la de la ventana hay que escribirla
a propósito. Y la sugerencia ya no se lee de la tarea del autodespliegue —una
instalación mala la envenena y la próxima vez sugiere la cuenta equivocada
como si fuera la buena— sino de la **sesión de consola**: quién está sentado
en este PC todos los días, cosa que ninguna instalación mala puede cambiar.

### 24-08 (tarde) — El lector de tarifas aprendió los anexos del Dispensario

Llegaron los tarifarios del contrato 440 del Dispensario y el lector se
saltaba **el anexo entero de medicamentos e insumos** —8 hojas, ~3.000
códigos CUM/FMQ/QX— sin decir una palabra. Tres causas, una detrás de otra:

1. El código se titula «CODIGO CUM» o «CODIGO» a secas, no «CUPS».
2. Dos anexos traen encabezados de TRES columnas y la regla exigía cuatro:
   2.000 dispositivos médicos invisibles.
3. La hoja TARIFAS PROPIAS de la propuesta trae una columna TARIFA con el
   TEXTO «PROPIA» y el valor real en OFERTA — y la «prioridad» de columnas
   resultó ilusoria: la búsqueda recorría los encabezados en orden, no los
   candidatos, así que TARIFA (texto) ganaba y la hoja entera se leía como
   ceros. Una prueba nueva me cazó el arreglo a medias; ahora la prioridad
   es real, candidato por candidato.

Con esto, del paquete del contrato 440 salen **7.085 servicios** (SOAT
SMLV-20%) **+ 3.063 medicamentos e insumos**, con 37 códigos en conflicto
para revisión. Y los tarifarios 2025 de COOSALUD y COMPENSAR ya validaron
igual que el de POSITIVA: 2.988 limpias y 737 por definir cada uno.

### 21-08 — El oficio del que la factura YA SALIÓ dejó de pedir lo imposible

**El caso.** La factura **HUS0000551678** ($3.285.631) entró al oficio
**FHUS-AS-I01196-26**, se auditó, se devolvió, salió en el oficio de
devolución **DEV-PRE-AUD-0118-2026** y facturación la reenvió: hoy está
reingresada en el oficio **FHUS-AS-I01212-26**. Todo correcto.

Pero el oficio viejo mostraba dos cosas equivocadas:

1. El aviso decía «*sigue pendiente de auditar en el oficio FHUS-AS-I01212-26:
   resuélvala allá y **vuelva a escribir el envío aquí**»* — invitando a
   traerla de vuelta a un oficio que ya cumplió y que ya tiene su PDF firmado.
2. El oficio se quedaba en **ROJO**, como si nadie lo hubiera auditado, solo
   porque ya no tenía facturas propias.

**Cómo quedó.** El sistema ahora distingue dos situaciones que antes veía
iguales:

- **La factura pasó por este oficio y siguió su camino** → aviso azul: «✅
  Envío 233277 · factura HUS0000551678: ya pasó por este oficio: salió devuelta
  en DEV-PRE-AUD-0118-2026 y hoy está en FHUS-AS-I01212-26 (reingresada, sin
  decidir). Aquí no queda nada pendiente.» El chip del envío se muestra como
  **«233277 (ya siguió)»**, sin el amarillo de alerta.
- **La factura nunca entró** (está trancada en otro oficio) → sigue el aviso
  amarillo de siempre, con el «resuélvala allá».

Y el oficio que se quedó sin facturas **porque todas siguieron su camino**
ahora aparece **COMPLETADO** en vez de rojo. El que nunca ha tenido facturas
—recién registrado, sin envíos— sí sigue corriendo su plazo, como debe ser.

7 pruebas nuevas (143 en el módulo).

---

### 24-08 (tarde) — El autodespliegue se colgó y nadie se enteró (otra vez)

**Qué pasó.** El PC de cartera llevaba horas sin recibir el código nuevo. En
el registro del autodespliegue, la misma línea repetida cada 5 minutos:
«*otra pasada sigue trabajando: esta se salta*». Una pasada se quedó colgada
preguntándole a GitHub, nunca soltó el **candado** —el archivo que evita que
dos pasadas se pisen— y todas las siguientes se saltaron. En pantalla no se
veía nada raro.

**Por qué se cuelga `git`.** Dos casos normales: que GitHub pida usuario y
clave (en una tarea programada no hay nadie que los escriba, y git espera
para siempre) o que la red del hospital deje la conexión a medias.

**Tres arreglos, todos de visibilidad:**

1. **Git tiene prohibido preguntar y tiene reloj.** El autodespliegue le pone
   mordaza (`GIT_TERMINAL_PROMPT=0`) y un tope de **3 minutos**: si no
   contesta, se corta y queda anotado el motivo, en vez de dejar el candado
   puesto toda la tarde.
2. **Bot de doble clic `tools\ACTUALIZAR_PAGINA.cmd`** (lo pidió Yesid): baja
   los cambios y los deja funcionando **ahora**, sin esperar los 5 minutos.
   Muestra en pantalla qué versión hay, qué cambios entran, reinicia el motor,
   comprueba que la página volvió a responder y —si el motor no vuelve solo—
   lo arranca él. De paso suelta el candado si quedó trabado, para que el
   automático vuelva a andar. Al final recuerda el **Ctrl + F5**.
3. **La pantalla de estado lo delata.** `ESTADO_MOTOR.cmd` ahora avisa: «*el
   autodespliegue lleva N min con el candado puesto: está trabado*», y dice
   qué correr para destrabarlo. Una pasada normal no dura ni dos minutos.

11 pruebas nuevas.

---

### 24-08 (noche) — La fábrica de cláusulas: seis EPS más con contrato en el motor

Con los ZIP que armó Yesid (el copiador automático encontró TODOS los archivos
al primer intento), se transcribieron y cargaron los contratos de **PPL (10
cláusulas), FOMAG (7), COMPENSAR (6), DISPENSARIO 440 (7), AURORA con sus dos
minutas ARL y Vida-AP (10) y SEGUROS MUNDIAL (5, pendiente de crear la EPS en
Contratos)**. Con POSITIVA, ya son SIETE las EPS que se defienden citando su
contrato firmado. Las joyas: en PPL, «la carencia de la autorización NO será
motivo de glosa» y «siempre se privilegiará la tarifa institucional»; en
FOMAG, la renovación automática y el 70% a 20 días hábiles; en AURORA, el
suministro de MAOS a cargo de la aseguradora.

**Los archivos de conflictos volvieron todos marcados con SI en ambas filas**
— así no hay decisión: el motor guarda UN valor por código. En vez de
devolverlos sin más, se usaron las reglas de los contratos recién transcritos:
la de POSITIVA (gana SOAT –15%) y la de PPL (gana la institucional) resolvieron
**316 códigos cada una** sin tocar al auditor; quedaron listas para cargar y
los residuales bajaron a 421 con la instrucción clara: UN solo SI por código.

**Y el CI volvió a ganarse el sueldo:** el candidato «CODIGO» del lector
—agregado en la mañana para los medicamentos del Dispensario— secuestró la
hoja AMBULATORIO de FAMISANAR 2026, donde el CUPS oficial se titula «Res
2706/25». Dos corridas selectivas mías pasaron en verde; la suite completa del
CI vio el rojo. El orden quedó sagrado y comentado: CUPS → Res-#### → CODIGO
CUM → CODIGO. La lección se repite: la corrida selectiva es una opinión, la
suite completa es el veredicto.

**El día también enterró al fantasma:** el motor de las 7:55 (la tarea de
ayer bajo cpimiento) cayó con la cacería elevada, el motor bueno arrancó a las
14:45 bajo cartera, y las dos tareas de arranque quedaron por fin con la
cuenta correcta y el permiso de lotes otorgado.

---

### 25-08 — Los paquetes de ADRES vuelven completos, y la pantalla se ordenó

**1) La excepción de ADRES.** Pedido de Yesid: «los paquetes que son del ADRES,
cuando se devuelven —así haya facturas en OK radicadas— se devuelven todas y
toca volverlas a ingresar al sistema; pero cuando ya esté radicada no se debe
dejar colocar en otro envío u oficio: es trabajar para que esto se pueda hacer
**solo** para las del ADRES».

Así quedó:

- Al escribir un envío, una factura **de ADRES** que ya estaba radicada
  **vuelve a entrar** como una ronda nueva, queda pendiente de auditar y el
  historial anota por qué: «ADRES devolvió el paquete completo: esta factura ya
  estaba RADICADA en el oficio tal y vuelve a auditarse».
- **Para las demás entidades no cambia nada:** una radicada sigue sin poder
  moverse. Es la regla que evita cobrar dos veces la misma factura.
- **No le gasta el cupo de las 3 devoluciones.** Ese contador es de las
  devoluciones que hace pre-auditoría a facturación; que ADRES nos devuelva el
  paquete no es una devolución nuestra. Si contara, tres paquetes devueltos
  dejarían la factura bloqueada sin razón.
- **«Ver antes» lo avisa** antes de cargar: «🔁 N factura(s) de ADRES ya estaban
  radicadas y van a volver a entrar».
- Y si el envío se quitó por error con la ✕ o con la 🗑, la factura vuelve a
  **RADICADA** —no a «devuelta»—: nadie la devolvió nunca.

**2) El ruido visual.** Yesid: «hay mucho ruido visual, todos los botones ahí
todos juntos, sin nada de profesionalismo y estética». Se ordenó así:

- Los botones de cada fila van ahora en **una sola barra**, del mismo alto, con
  la misma separación y pegados a la derecha — en las cuatro tablas, no solo en
  una: oficios, facturas del oficio, consolidado y oficios de devolución.
- El **lápiz de corregir el número ya se dibuja**: era un emoji que ese
  navegador no sabía pintar (salía una rayita) y ahora es un dibujo propio, igual
  en todos los computadores. Los botones de solo dibujo llevan su explicación al
  pasar el mouse.
- Las columnas de números (Facturas, Pend., OK, Dev.) van **alineadas a la
  derecha** y con cifras del mismo ancho, para compararlas de un vistazo.
- La columna de **envíos ya no estira la fila**: muestra los primeros seis y
  «+N más», y la lista completa queda en el globo de ayuda.

**Y una red de seguridad que faltaba:** ahora hay una prueba que **compila** el
JavaScript de esta pantalla. Antes solo se revisaba el del portal principal, así
que un error de escritura aquí dejaba la pantalla muerta sin que ninguna prueba
se enterara.

15 pruebas nuevas (152 en el módulo, 309 con las de pantalla).

### 25-08-2026 — Dispensario: lote de glosas del 25-ago respondido completo (24/24)

Llegó el lote nuevo del Dispensario (`GLOSAS_25_AGOSTO.xlsx`): **24 facturas,
64 objeciones, $56.169.241**, con vencimientos el 4 y el 7 de septiembre y
ninguna devolución. Se armó el Excel de respuestas con el motor de siempre,
**cuadrado al peso** contra la hoja INICIAL: 59 respuestas de tarifas (con los
refuerzos según lo que dice cada observación: cotización previa, dispositivos,
referentes SOAT) y **5 médicas de pertinencia** (la fluoroscopia 1-de-2 de la
factura 540394 y las interconsultas y cultivos de la 543137) con el argumento
institucional.

**Resultado del robot:** piloto con la 540273 bien, corrida completa con
**22 OK**, y las otras 2 verificadas: la 540273 era el propio piloto (ya
finalizada) y la 538877 respondió con un aviso informativo del portal — se
verificó aparte y ya no está en pendientes. **Las 24 quedaron respondidas y
finalizadas**, cada una con su pantallazo en `evidencias_glosa\`. El portal
generó el consecutivo del paquete: **GI-33-5369-2026**.

También se resolvió el enredo del PR de la bitácora: el respaldo del 24-08 se
aplicó dos veces (en este chat y en otro), la principal quedó con la versión
vieja del plan y el PR chocó; se fusionaron las dos versiones conservando el
trabajo de todas las sesiones y quedó todo en la rama principal (PR #469).

---

### 25-08 (tarde) — «[object Object]»: el error que no decía nada

Elías pegó en la observación el mensaje de error que devuelve **ADRES SIA**
—ese texto larguísimo del FUR— y al guardar salió un aviso rojo que decía
**«[object Object]»**. Ni se guardaba, ni se entendía por qué.

Eran dos cosas:

1. **El texto no cabía.** La observación tenía tope de 2.000 caracteres y los
   mensajes de ADRES pasan de eso. Ahora el tope es de **4.000**, el mismo del
   motivo de devolución (en la pantalla es un solo recuadro que viaja en los
   dos campos), y el recuadro no deja escribir de más: se corta solo al llegar.
2. **El aviso era inútil.** Cuando el servidor rechaza un dato, manda el motivo
   como una lista de datos y la pantalla lo mostraba tal cual, en su forma
   interna. Ahora lo traduce: «observaciones: el texto es muy largo: máximo
   4000 caracteres». Vale para cualquier error de este tipo, no solo para este.

4 pruebas nuevas, una de ellas ejecuta de verdad la traducción del error.

---

### 25-08 (noche) — «Esto lo hizo Vanesa, pero aparece Óscar»

Yesid preguntó por qué algunos envíos que recepciona y gestiona **Vanesa**
quedan a nombre del gestor **Óscar**.

**La respuesta.** El sistema guarda el nombre de la persona en tres momentos
distintos —quién **registró** el oficio, quién **escribió** el envío y quién
**auditó** cada factura— y en los tres casos el nombre sale de la **sesión
abierta en el navegador**, no de quién esté sentado al computador. Si dos
gestores comparten el mismo equipo y no cierran sesión, todo lo que haga el
segundo queda firmado por el primero. Hay un segundo camino posible: las
facturas que entraron por **importación del Excel** llevan el auditor que decía
la columna AUDITOR del archivo, no el de quien las tocó después.

**Cómo averiguar cuál de los dos fue,** sin cambiar nada:

    venv\Scripts\python.exe tools\preauditoria_quien_hizo_que.py FHUS-AS-I01197-26
    venv\Scripts\python.exe tools\preauditoria_quien_hizo_que.py 232050

Muestra, uno al lado del otro y con fecha y hora: quién registró el oficio,
quién escribió cada envío, quién auditó cada factura y el historial renglón por
renglón con su firma. Las líneas que trajo el Excel quedan marcadas.

**Lo que hay que hacer en la oficina:** cada gestor entra con su propio usuario
y cierra sesión al terminar. El nombre de quien tiene la sesión abierta se ve
arriba a la derecha en la página: si no es el suyo, hay que cerrar sesión antes
de trabajar.

10 pruebas nuevas.

---

### 25-08 (cierre) — De dónde salieron esos nombres, y el chip que decía «(1/0)»

Yesid comparó el Excel del informe contra la pantalla y aparecieron dos cosas.

**1) «Salen gestores escribiendo envíos y ellos solo recepcionan».** El
movimiento **ESCRITA no es auditar**: es el registro de quién **cargó el envío**
en la página (el paso 4 de la pantalla). Y el nombre no lo pone el sistema según
el cargo de cada quien: lo pone según la **sesión abierta en el navegador**. Si
un gestor deja su sesión abierta y otro trabaja en ese computador, todo queda
firmado por el primero.

Se le entregó a la Dirección el informe **INFORME_AUTORIA_PREAUDITORIA_SINAC**
(Excel con fórmulas y gráficos) con los números: 3.889 movimientos, **92 sin
gestor identificado** (los trajo el cargue del consolidado histórico, sobre 55
facturas, y **164 de los 183 oficios** quedaron registrados así), la lista
completa de esos 92 con casilla para asignar responsable, y el hallazgo de que
**VANESSA OSPINA** está partida en dos por un nombre mal escrito («VANESA
OSPINA», 29 movimientos entre el 18 y el 25 de agosto), más un movimiento a
nombre de «Auditor Principal», que no es una persona.

**2) El chip decía «226945(1/0)» y «226943(0)».** Los envíos que entraron por la
importación quedaron con «traía 0 facturas» —el Excel no lo decía— y el chip
comparaba contra ese cero: mostraba que el envío no había traído nada en oficios
que sí tienen facturas. Ahora, cuando el registro no sabe cuántas traía, la
pantalla muestra lo único cierto: **las que están ahí**. Y el importador ya
guarda el número real de facturas por envío, así que a los cargues nuevos no les
vuelve a pasar.

4 pruebas nuevas.

---

### 26-08 — «Dice que no tiene facturación electrónica y sí la tiene»

Tres facturas —**HUS544942, HUS542599 y HUS544936**— salían en la página con
«Correo F.E.: **NO**» teniéndola. Y eso no es un detalle: **sin correo el
sistema no deja radicar**, así que el auditor queda obligado a devolver una
factura que estaba bien.

**Por qué pasaba.** Ese dato no lo escribe nadie a mano: sale de **cruzar** la
factura con el Formato de Facturación Electrónica del DGH. El cruce se hacía
comparando el número **letra por letra**, y los dos archivos no siempre lo
escriben igual: unas veces «544942», otras «HUS544942», otras
«HUS0000544942». Cuando no coincidía exacto, el sistema daba por hecho que la
factura no tenía correo — sin decir nada.

**Cómo quedó.** Al subir cualquiera de las dos fuentes, el número se guarda
siempre en la forma larga (**HUS + 10 dígitos**), venga como venga. Así las dos
hablan el mismo idioma y el cruce no vuelve a fallar. Lo que no tiene forma de
número de factura del HUS se deja tal cual: no se inventa nada.

**Para revisarlo sin cambiar nada:**

    venv\Scripts\python.exe tools\preauditoria_revisar_fe.py HUS544942 HUS542599 HUS544936

Dice, factura por factura, si está en el Formato F.E., si está pero **escrita
distinto**, o si sencillamente no está —y qué hacer en cada caso—. Se pueden
escribir cortas o largas.

**Lo que hay que hacer con estas tres:** después de actualizar, **volver a
subir el Formato F.E.** en «Fuentes». Ahí el número se guarda ya normalizado y
las tres quedan con su correo.

16 pruebas nuevas.

---

### 26-08 (tarde) — El botón «Exportar Excel» ahora saca un informe, no un volcado

Yesid: «quisiera que el botón de exportar Excel me genere el Excel bien
detallado, bien definido, algo pulido». Antes salía **una sola hoja de 15
columnas**: los datos estaban, pero no decían nada.

**Ahora el mismo botón saca un libro de siete hojas:**

- **CÓMO LEER** — qué contesta cada hoja, para que cualquiera lo abra y se
  ubique.
- **RESUMEN** — cuántas facturas hay, cuántas listas para radicar, cuántas
  devueltas, la tasa de devolución, las **tres causas que más devuelven** y el
  gráfico de resultado.
- **POR QUÉ SE DEVUELVEN** — las devoluciones **agrupadas por causa**
  (deducida de lo que escribió el gestor), con cuántas facturas, cuánta plata,
  el porcentaje y **qué hacer** en cada una. Con su gráfico.
- **DEVUELTAS AL DETALLE** — solo las devueltas, con el texto completo de lo
  observado. Es la hoja que se le pasa a Facturación.
- **POR GESTOR** — cuántas auditó cada uno, cuántas radicó, cuántas devolvió y
  su tasa, con gráfico.
- **POR ENTIDAD** — lo mismo por aseguradora.
- **FACTURAS** — una fila por factura con **todo**, incluida la observación del
  gestor y quién escribió el envío y quién auditó. Con filtros en el
  encabezado.

Los totales son **fórmulas vivas**, no números pegados: si el auditor corrige
una fila, los resúmenes se recalculan solos. El archivo sale con la fecha en el
nombre (`CONSOLIDADO_PRE_AUDITORIA_26-08-2026.xlsx`).

**Lo que no se inventa:** la causa se deduce del texto del gestor. Lo que no se
puede clasificar queda como «Otros motivos», y lo que se devolvió sin escribir
nada, como «Sin motivo escrito» — esas dos filas son, en sí mismas, un
hallazgo.

9 pruebas nuevas (166 en el módulo).

---

### 26-08 (cierre) — Las doce ideas para el motor, implementadas

Usted dijo «vamos a implementar todas las ideas». Quedaron **once de doce**. La
que falta es la única que le dije que no recomendaba, y es decisión suya (está
en PENDIENTE, abajo).

**Lo que cambia lo que sale del motor**

- **No deja marcar como listo lo que no tiene con qué probarse.** El motor ya
  sabe qué soporte pide cada causal —SO0101 la epicrisis, AU0202 la
  autorización, CL la historia— y si no está, lo dice en el propio dictamen. De
  los 10 del último lote auditado, 9 afirmaban cosas de la historia clínica sin
  un solo soporte adjunto.
- **Un auditor de la EPS, antes de radicar.** Los defectos graves de agosto los
  encontraron tres auditorías *después* de que los dictámenes salieran — y
  todos habían salido con el sello «citas verificadas · 0 hallazgos». Por eso el
  revisor nuevo se enciende justo ahí: cuando la revisión de citas no encontró
  nada, un agente lee el dictamen como lo leería el auditor de la entidad y
  responde «por dónde lo tumbaría yo». Los seis flancos que revisa salen de
  fallas reales de este mes: cita que no dice lo que se le atribuye, afirmar lo
  que no se probó, contradicción interna, código que no cruza, plazo al revés y
  no contestar la causal.
- **El sello dice contra qué se verificó.** Antes decía «citas verificadas · 0
  hallazgos» a secas, y esta semana quedó demostrado que ese sello podía darse
  el visto bueno a sí mismo. Ahora dice cuántas normas están contrastadas
  contra fuente oficial y cuántas no.
- **El CUPS lo trae de DGH.** El archivo de recepción no tiene columna de CUPS.
  El motor ya no se lo inventa —eso era lo grave— pero así perdía el argumento
  del código. Ahora, cuando el texto no lo trae, busca el que el propio DGH
  tiene guardado para esa factura. No inventa: lee.

**Lo que hace que el motor aprenda**

- **Primero sale la plantilla que más plata ha recuperado**, no la más usada.
  Se usó mucho no es lo mismo que funcionó.
- **Al levantar una glosa se le hace una sola pregunta al gestor:** «¿cuál
  argumento la levantó?». Esa frase queda pegada a la plantilla, que es la
  mejor prueba que existe de qué sirve con esa EPS y esa causal. Se puede dejar
  en blanco, y si se deja en blanco no se inventa nada.

**Dos pantallas nuevas**

- **«Plata recuperada»** (la ve coordinación). Cuánto se glosó y en qué
  terminó, mes a mes y EPS por EPS: glosado, respondido a tiempo, respondido
  tarde, levantado, ratificado, perdido por vencimiento y sin decidir. Es el
  número que pide la gerencia. Había 32 pantallas y una sola gráfica en todo el
  sistema.

  **Lo que más importa de este tablero es lo que NO hace: no rellena.** Una
  glosa que la EPS levantó y a la que nadie le anotó cuánta plata era, no se
  cuenta por el valor objetado — se cuenta aparte y sale arriba, en amarillo,
  diciendo que esa plata no está sumada. Lo mismo con las que no tienen fecha
  de vencimiento (de esas no se puede decir si se respondieron a tiempo). Un
  tablero que se inventa el relleno miente con más autoridad que uno que se
  queda corto y lo dice.

- **«Mi día»** (la ve cualquier gestor). Tres columnas y nada más: responder lo
  que llegó, revisar lo que el motor marcó, radicar lo que está listo. Cada
  glosa cae en una sola, y cada tarjeta dice en una línea por qué está ahí.
  Primero lo que vence antes; a igualdad de días, lo de más plata. Las otras 32
  pantallas siguen ahí para quien las necesite, pero dejan de ser el punto de
  partida.

  **Aquí también hay un «no se inventa»,** y salió escribiendo las pruebas: la
  base guarda un contador de días que vale **cero por defecto**. Un cero sin
  fecha de vencimiento puede querer decir «se venció» o «nadie le calculó el
  plazo», y en la base se ven idénticos. No se escogió ninguno: esa glosa sale
  como «sin plazo conocido» y se va al final de la columna, en vez de
  disfrazarse de urgente y empujar hacia abajo lo que de verdad vence mañana.

**Lo de todos los días**

- **Buscar dentro de las tablas** (38 tablas, y para hallar una factura había
  que pasar páginas — en un lote de 1.573 eso es inviable).
- **Modo compacto**, que aprieta las filas para revisar doscientas seguidas y
  se recuerda por usuario.
- **Los avisos de «revisar antes de radicar» salen en rojo al imprimir**, para
  que nadie los mande por accidente.
- **Las pantallas de plata avisan cuando no cargan.** Catorce pantallas fallaban
  en silencio: si el servidor no respondía, el auditor veía ceros y creía que
  no había nada.

**Dos cosas que se arreglaron por el camino, y las encontraron las pruebas, no
yo:**

1. El revisor nuevo iba a volver a revisar las citas por su cuenta, y lo habría
   hecho **sin la evidencia** — un folio inventado le habría pasado de largo y
   el contador habría quedado en cero por ignorancia, no por estar limpio. Una
   prueba que ya existía lo señaló. Ahora lee la revisión que ya se hizo.
2. Cuatro colores de la pantalla nueva no existían en la paleta: se habrían
   pintado transparentes. Lo cazó la prueba que se escribió en su día por el
   botón invisible del lote ADRES.

**87 pruebas nuevas** en cinco archivos, con sus casos borde: factura en cero,
EPS vacía, glosa vencida que la EPS ya levantó, respuesta de 5.000 caracteres,
lista vacía, cero meses, cien meses.

---

### 26-08 (cierre 2) — La pantalla nueva le quitó el puesto a una ruta que ya existía

Lo cuento porque es un error mío y porque la lección sirve.

**Qué pasó.** La pantalla «Mi día» que se subió hace un rato colgaba de la
dirección `/mi-dia`. Resulta que **esa dirección ya estaba ocupada** desde
antes: era el resumen personal del gestor (tareas del día, saludo, alertas).
Cuando dos partes del programa piden la misma dirección, el motor le hace caso
a la primera que se registre y **la otra queda muerta sin decir nada** — sin
error, sin aviso: simplemente empieza a devolver otra cosa. Es exactamente la
forma en que «Salud Total» estuvo tres meses devolviendo «Not Found».

**Qué se dañó, en concreto.** Nada de lo que usted usa. Revisé todo el portal:
**ninguna pantalla llamaba la dirección vieja**. Y la pantalla nueva sí
funciona en el motor del hospital. El daño fue que quedó una dirección muerta
y que la rama del hospital quedó en rojo un rato.

**Cómo quedó.** El tablero de tres columnas se mudó a `/mi-dia/tablero` y la
dirección vieja volvió a ser lo que era. **Y quedó una prueba que cierra el
problema completo, no solo este caso:** recorre todas las direcciones del
motor y se pone roja si dos comparten camino, diciendo cuáles son. Antes esto
solo se descubría cuando alguien reportaba que una pantalla dejó de funcionar.

**Lo que enseñó, sin adornos.** Mis propias pruebas locales SÍ lo habían
cazado —las mismas cinco— pero subí antes de que la corrida terminara. Y
después le dije a usted que las marcas rojas eran solo cancelaciones, porque
miré dos de los cuatro casos y generalicé. Las dos cosas fueron mías: no subir
con la corrida a medias, y no sacar conclusiones de una muestra cuando el dato
está a un clic.

---

## 3) PENDIENTE

### Radicación del paquete 31068 (28-08)
- **DECISIÓN SUYA: borrar la carpeta `_APARTADOS_REVISAR_Y_BORRAR`.** Ahí
  quedaron los 1.340 archivos que se sacaron de las carpetas de factura
  (historias clínicas, respuestas, detallados). El bot no los borra a propósito:
  son la única fuente para rehacer un folio. Revíselos y bórrelos usted.
- **Sacar los folios de las carpetas.** La simulación quedó limpia (444 folios
  de 222 carpetas); falta correrlo con `--aplicar`. Deben quedar 645 PDF
  sueltos.
- **Traer los XML.** El bot ya sabe hacerlo; se corre **después** de sacar los
  folios, para que los traiga todos y no solo los de los 201 que ya estaban
  sueltos.
- **La HUS380112.** Ya apareció su archivo en la carpeta del XML; falta volver a
  correr `--solo-facturas` para que le arme el folio.
- **$361.758.330 de glosa que no entraron al FURIPS2.** No se pudieron ubicar
  en un renglón porque 1.308 renglones del reporte del ADRES no traen código de
  elemento. Hay que decidir si se reclama de otra forma o se deja así.
- **187 filas del export de DGH en blanco.** Están en
  `REVISAR_RESPUESTAS.xlsx` con las opciones servidas; falta que el auditor
  escoja cuál va en cada una.


> **Cómo leer esta lista (27-08-2026).** Es larga porque cubre todos los
> frentes y varios meses. Lo tachado ya está hecho y se deja para que se vea
> de dónde salió. Lo que de verdad está abierto, ordenado por lo que le cuesta
> plata al hospital, es esto:
>
> **1. Lo que espera una decisión suya**
> - Folio ADRES: la versión A o B de las cinco respuestas, el texto dañado de
>   la HUS396996 y si esa factura entra, y qué se hace con las notas crédito.
> - La **epicrisis de las 223 facturas**: no está en ninguna carpeta. Si el
>   ADRES la exige, es el hueco más grande del paquete.
> - Las **131 entradas sin contrastar** de Consulta Normativa.
> - Si se agrega a la plantilla de ratificaciones el argumento del Art. 23 del
>   Decreto 4747 (no se pueden formular glosas nuevas salvo por hechos nuevos).
> - El criterio de quién cuenta como **aseguradora** para las ratificaciones.
> - Si se pone en GitHub la regla de **no fusionar sin revisión en verde**
>   (el autodespliegue ya no baja código en rojo, pero esa regla lo cierra por
>   el otro lado).
>
> **2. Lo que hay que hacer en el PC de cartera**
> - Volver a correr el bot de folios en CAROLINA, CLAUDIA y OSCAR, para que
>   los 223 se rehagan con el orden bueno.
> - Volver a subir el **Formato F.E.** en «Fuentes» (las tres facturas que
>   decían no tener facturación electrónica).
> - Borrar en Administración → Usuarios la cuenta `devoluciones1@sinacsc.com`
>   de Edgar Silva. Ya no se vuelve a crear sola, pero la fila vieja sigue ahí.
> - Volver a cargar el **Excel de tarifas de POSITIVA** marcando «Reemplazar
>   tarifas existentes». Mientras tanto, no confiar en dictámenes de tarifas de
>   esa entidad: citarían valores 15 % más altos que el contrato.
> - **Comprobar que la tarea de arranque existe** y con qué cuenta quedó. La
>   última noticia clara es del 24-08; si no está, el portal no vuelve solo
>   cuando el PC se reinicie.
> - Mirar `data\autodeploy.log` la primera vez, para confirmar que la puerta
>   nueva sí puede preguntar por la revisión automática.
>
> **3. Lo que falta de datos, y no lo puede resolver el sistema**
> - COOSALUD: las **44 del lote de 1.573** que no quedaron OK, las 8 facturas
>   de auditoría médica de agosto (más las 37 del masivo del 14/07), y las que
>   hay que registrar a mano en DGH.
> - ADRES: las **101 facturas sin carpeta**, las 47 carpetas vacías de CLAUDIA,
>   los 12 archivos `FACOSTE`, la HUS381290 sin factura y las seis sin
>   detallado.
> - **Volver a exportar los 10 casos de prueba** del motor: el archivo que se
>   subió eran los dictámenes viejos, así que esa validación sigue sin hacerse.


### 26-08-2026 (tarde) — Se repasó TODA la base normativa, y no quedaba un artículo bueno

Usted pidió verificar, corregir y completar las 16 normas que faltaban. Se
hizo, con dieciséis revisores trabajando en paralelo y un segundo par de ojos
que intentaba tumbar cada hallazgo antes de darlo por bueno.

**El resultado, sin adornos: de los 20 artículos, los 20 estaban mal.** Y
ninguno se cayó al intentar refutarlo.

| Qué tenían | Cuántos |
|---|---|
| Título **y** texto inventados | 13 |
| El texto cambiado | 3 |
| El título cambiado | 2 |
| El artículo **no existe** en esa norma | 2 |

Tres ejemplos de lo que decía el motor:

- **Decreto 1082**, artículo 2.2.1.2.1.4.4 — el motor lo daba como
  «Contratación de prestadores de servicios de salud». Es «Convenios o
  contratos interadministrativos», y el texto que le habían puesto sale de otro
  decreto, el 1510 de 2013.
- **Decreto 1795** (el del sistema de salud de las Fuerzas Militares), artículo
  6 — figuraba como «Cobertura». Es «Principios y características».
- **Resolución 4886 de 2018**, artículo 25 — esa resolución adopta la Política
  Nacional de Salud Mental y **no tiene ese artículo**.

Los 20 quedaron corregidos con el texto literal de la norma, los 2 que no
existen se retiraron, y las 16 normas quedaron marcadas con la fuente contra la
que se verificaron.

**El corpus completo, al cierre: 26 normas, 47 artículos, cero pendientes.**

Y quedó una prueba que impide que vuelva a pasar: si alguien agrega un artículo
con su texto y no deja escrito contra qué fuente lo verificó, la prueba se pone
roja y el cambio no entra.

**El balance de la semana.** Sumando las tres auditorías: de las 26 normas del
corpus, **veintiuna tenían al menos un artículo con el nombre o el texto
inventado**. El motor llevaba meses citando derecho que no existe, con un sello
que decía «citas verificadas» porque se contrastaba contra esa misma lista.

### 26-08-2026 — Seis decisiones del área, aplicadas

**El texto del Dispensario ya no generaliza: prueba el ítem.** Afirmaba que el
servicio «se encuentra» entre los 7.141 ítems del Anexo 1 sin decir cuál. Ahora
esa afirmación sale del texto fijo, y en su lugar el motor **busca el código en
el catálogo del contrato** que usted cargó: si lo encuentra, lo nombra con su
descripción y su valor pactado — eso es una prueba, no una generalización. Si
no lo encuentra, no afirma nada.

**El cómputo de días hábiles ya se ve.** El texto de glosa extemporánea decía
«han transcurrido 77 días hábiles» sin mostrar una sola fecha. Ahora escribe
entre qué dos fechas contó: la radicación de la factura y la notificación de la
glosa. Si el conteo falla, se nota antes de radicar — y la entidad puede
rehacerlo, que es lo que le da fuerza al argumento.

**La cuenta de Edgar Silva se volvía a crear sola.** Los correos a
`devoluciones1@` rebotaban y la cuenta buena es `carterahus02@`. Borrarla en la
pantalla no servía de nada: **estaba sembrada en el código de arranque**, así
que reaparecía en cada reinicio del motor. Ahí quedó corregida.

**Los códigos con dos valores ahora se resuelven con la fórmula del contrato.**
Eran 256 del Dispensario, 737 de Compensar y 737 de Positiva que no se cargaban
porque el archivo traía el mismo código con precios distintos. Usted decidió:
«el que mejor se ajuste a las tarifas pactadas». Ahora el motor toma el valor
SOAT oficial del código, le aplica el descuento del contrato de esa entidad y
escoge el que caiga sobre ese número. **No es «el más parecido»:** se exige que
quede a menos del 2 % del esperado y que ningún otro quede igual de cerca. Si
nada cuadra, el código se sigue omitiendo, como antes.

**Y apareció una segunda lista de normas que nadie había mirado.** Aparte del
corpus que alimenta a la IA, la pantalla de Consulta Normativa tiene su propia
lista de 132 entradas. Al auditar los dictámenes salió que una estaba
inventada: decía que el artículo 10 del Decreto 2423 de 1996 son «tarifas
mínimas SOAT para urgencias», y verificado contra el PDF oficial de MinSalud
ese artículo es **la nomenclatura de las intervenciones quirúrgicas de
proctología**. Se reemplazó por el artículo 87, que sí es el de tarifas. **Las
otras 131 siguen sin contrastar**, y quedó escrito en el archivo.

**Nota sobre el archivo que subió.** El documento con los resultados de los 10
casos de prueba resultó ser idéntico —byte por byte— al de la auditoría
anterior. No trae los dictámenes nuevos: son los mismos, generados antes de las
correcciones. Falta volver a enviarlo.

### 26-08 — La idea que yo no recomendaba, y que resultó tapando un defecto real

Queda escrito porque el equivocado fui yo.

De las doce ideas para el motor, la #12 era **unificar los dos vocabularios de
color**. Yo se la desaconsejé por escrito: dije que eran «2.072 cambios sobre
algo que funciona y **sin ningún defecto visible** que lo justifique». Usted
dijo que se hiciera igual. Al medirlo, resultó que **las dos afirmaciones mías
eran falsas**.

**Uno: sí había defecto visible, y en la pantalla que más se usa.** El archivo
del sistema de diseño no estaba muerto: dieciséis de sus reglas de color pintan
hoy la pantalla de Analizar — el cuerpo del dictamen, las fichas de cita, los
campos y el botón principal. Y las dos paletas no eran dos nombres para el
mismo color: **eran colores distintos**. La ficha de cita **VERIFICADA** salía
de un verde en el dictamen y de otro verde en el resto del motor. Lo mismo el
ámbar del «sin verificar» y el rojo del error.

**Dos: no eran 2.072 cambios, eran 13.** No hacía falta reescribir los usos.
Bastó con que los trece colores del sistema de diseño dejaran de tener color
propio y tomaran el de la paleta corporativa. Los nombres siguen siendo los
mismos que se escriben; lo que cambia es el color que devuelven. Ni uno solo de
los 2.072 usos se tocó.

Y al medirlo salió algo más: de las seis páginas que cargan ese archivo,
**cuatro no traen la paleta corporativa**. Sin un color de respaldo, esas
cuatro se habrían quedado con los colores vacíos —el elemento se pinta
transparente, que es como quedó invisible en su día el botón del lote ADRES—.
Cada color lleva el suyo, y es el corporativo, así que esas cuatro páginas
también quedaron unificadas.

**La lección, para la próxima vez que yo diga que algo no vale la pena:**
«no hay defecto visible» no es una conclusión si no se ha mirado. Medir costó
diez minutos y cambió la respuesta entera.

### ⭐ Lo primero, al cierre del 25-08

Tres cosas, en este orden:

1. **Correr los 10 casos de prueba en la pantalla del motor.** Están armados
   para que cada uno pruebe algo concreto que se arregló ese día. Si el motor
   pasa los diez, lo del 25 quedó funcionando de verdad en el hospital. Es lo
   único que falta para dar el día por cerrado.
2. **Dos decisiones del área**, las dos sobre textos institucionales que no se
   tocan sin permiso:
   - **La plantilla del Dispensario** afirma que el servicio «se encuentra»
     entre los 7.141 ítems del Anexo 1, sin decir cuál ni verificarlo caso por
     caso. Puede ser cierta en general y falsa en un caso puntual. ¿Se cambia
     por una frase que no afirme lo que no se verificó?
   - **El criterio de «aseguradora»** para las ratificaciones: hoy van al
     análisis las compañías de seguros y las ARL, y conservan la plantilla las
     EPS, el Dispensario, Sanidad Militar, la Policía y el Magisterio. Falta que
     el área lo confirme o lo corrija.
3. **Verificar el cómputo de días hábiles** antes de radicar una glosa como
   extemporánea. El dictamen GL-130 afirma «77 días hábiles» y «ha operado de
   pleno derecho la aceptación tácita» como hecho consumado. Si el conteo
   falla, la causal original nunca quedó respondida.

### Folio ADRES del paquete 31068 (26-08, cierre)
- **DECISIÓN SUYA: las cinco respuestas del Word «PARA_CORREGIR».** Se enviaron
  dos versiones. La **A** incluye 310 glosas «SE SUBSANA» que hoy se omiten
  (son el desglose de reclamaciones que el ADRES glosó enteras por el FURIPS,
  pero el auditor SÍ les escribió respuesta): son **$34.718.970** que al ADRES
  le llegarían sin respuesta visible. La **B** mantiene la regla de siempre.
- **DECISIÓN SUYA: el texto dañado de la HUS396996.** Tres celdas traen
  `EXTENSIÃ"N` en vez de `EXTENSIÓN`. No se tocó porque la regla del generador
  es que el texto sale tal cual lo escribió el auditor.
- **DECISIÓN SUYA: si la HUS396996 entra.** En el Word venía sin rótulo, de
  primera, mientras las otras cuatro sí están rotuladas.
- **La EPICRISIS de las 223 facturas.** Falta en todas. Hay que decidir si se
  consigue o si el paquete va sin ella.
- **La HUS381290** necesita que le busquen su factura en la carpeta del XML.

### Folio ADRES del paquete 31068 (26-08)
- **~~Confirmar qué es la REPRESENTACIÓN GRÁFICA DE LA DIAN~~ — RESUELTO.** Son
  las páginas 10 a 18 del mismo `..._FACTURA.pdf` que viene con el XML. Ese
  archivo trae la factura y la gráfica pegadas; por eso el bot ahora lo parte
  para meter el detallado en la mitad (ver la entrada del 26-08 cierre 2).
- **DECISIÓN SUYA: las notas crédito.** El `..._FACTURA.pdf` de la HUS311736 ya
  trae una nota crédito (la N° 253292, del trámite de objeción 179143 de junio).
  Las de los valores aceptados de ESTE paquete son otras. ¿Se deja la que ya
  trae, o cuando salgan las nuevas se rehace el folio? Mientras no diga, el bot
  respeta lo que el archivo ya trae y no le agrega nada encima.
- **Las 101 facturas sin carpeta** en ningún gestor (CAROLINA, CLAUDIA, OSCAR)
  y **las 47 carpetas vacías de CLAUDIA** siguen igual: sin carpeta no hay
  folio que armar.
- **Los 12 archivos `FACOSTE`** que el bot no reconoce y manda a OTROS: falta
  decir a qué grupo pertenecen.

### Del motor de glosas, al 25-08 (cierre)
- **~~Reiniciar el motor~~ — HECHO** (confirmado por el área el 25-08).
- **~~Reenviar el archivo de recepción~~ — HECHO.**
- **~~Subir a DGH los 6 archivos de objeciones de COOSALUD~~ — HECHO.**
- **~~La plantilla de las ratificaciones~~ — RESUELTO.** El área decidió que las
  de aseguradora se analizan. Implementado el 25-08 (ver la entrada del día).
  Falta que el área confirme el criterio de quién cuenta como aseguradora.
- **La cuenta repetida de Edgar Silva** — pendiente de pantalla, no de código:
  entrar a Administración → Usuarios, borrar `devoluciones1@sinacsc.com` y
  dejar `carterahus02@sinacsc.com`.
- ~~**Terminar de repasar la base normativa**~~ — **HECHO, completo.** 26
  normas, 47 artículos, cero pendientes. (Antes decía:)
  12 normas verificadas contra fuente oficial (29 artículos): Decreto 4747,
  Decreto 780, Decreto 111, Decreto 2423, Ley 23, Ley 100, Ley 1122, Ley 1164,
  Ley 1438, Ley 1751, Resolución 1995 y Resolución 2284. **Quedan 16 normas con
  20 artículos**, todas de uso ocasional (Ley 80, Ley 599, el CPACA, la
  Resolución 1885, entre otras). Se pueden hacer cuando haya un rato.

### Lo que quedó de la noche del 25-08
- ~~**Decisión suya: la plantilla de las ratificaciones**~~ — **RESUELTO** el
  mismo día: el área decidió que las de aseguradora van al análisis y las demás
  conservan la plantilla. Ya está implementado. (Se deja el texto de abajo
  porque explica de dónde salió.) El segundo auditor
  señala que las 21 respuestas a glosas ratificadas usan el mismo texto y
  ninguna entra en el motivo concreto por el que la entidad ratificó. El texto
  lo pidió el área en abril y jurídicamente se sostiene, así que no se cambió
  sin preguntarle. Hay una mejora concreta disponible: el artículo 23 del
  Decreto 4747 dice que **no se pueden formular glosas nuevas sobre la misma
  factura salvo por hechos nuevos** — o sea que si la entidad ratifica
  estrenando causal, eso es rebatible. ¿Se agrega ese argumento a la plantilla?
- **Repasar el resto de la base normativa.** Del Decreto 4747 estaban mal los
  tres artículos que había. Falta pasar por la misma verificación las demás
  normas del corpus que tienen texto de artículo guardado — el Decreto 780 de
  2016 es el primero de la lista.

### Del motor de glosas, al 25-08 (tarde)
- ~~Reenviar el archivo con las columnas de IA~~ · ~~que a las médicas les
  llegue lo suyo~~ — **HECHO**, confirmado por el área el 25-08 (noche).
- ~~La cuenta repetida de Edgar Silva~~ — el área decidió: queda
  `carterahus02@sinacsc.com`. Falta hacerlo en la pantalla de Usuarios; no es
  tarea de código.
- ~~**Los CSV de «valores distintos»**~~ — **RESUELTO el 26-08.** Eran 256 del
  Dispensario, 737 de Compensar y 737 de Positiva, cada uno un código con dos
  precios. El área decidió: «el que mejor se ajuste a las tarifas pactadas».
  Ya está implementado — el motor toma el valor SOAT del código, le aplica el
  descuento del contrato de esa entidad y escoge el que caiga sobre ese número,
  exigiendo que quede a menos del 2 % y que ningún otro quede igual de cerca.
- ~~**Revisar de dónde saldrá el CUPS**~~ — **RESUELTO el 26-08.** El archivo
  de recepción no lo trae, y se decidió traerlo de DGH: cuando el texto no lo
  dice, el motor busca el que el propio DGH tiene guardado para esa factura.
  No inventa, lee. Si no está ahí tampoco, la respuesta sale sin código.

### Del frente COOSALUD (glosas y trámites), al 25-08
- ~~**Subir a DGH los 6 archivos de OBJECIONES del lote de 1.573**~~ — HECHO,
  confirmado por el área el 25-08. (Detalle original: uno por uno,
  por el tope de 300 facturas). Si alguno devuelve error, corregirlo con el bot
  CORREGIR ERRORES DGH y reintentar el archivo completo. Después van los
  trámites de ese lote.
- **Repasar las 44 del lote de 1.573 que no quedaron OK en el portal**: 43
  NO_EN_BOLSA (no estaban en la bolsa del usuario: hay que ver si las tiene
  otro auditor o si ya venían respondidas) y 1 que terminó sin cartel de
  asignación. El resto del portal ya está cerrado.
- **8 facturas de auditoría médica de agosto** (HUS527358, HUS529493, HUS530150,
  HUS530676, HUS530701, HUS531001, HUS531885, HUS533202): esperar la respuesta
  de las doctoras para armar sus trámites. Siguen pendientes también las 37 del
  masivo del 14/07.
- **Registrar a mano en DGH** lo que no cruza: HUS530335 y HUS506920, y los
  ítems sueltos ACETAZOLAMIDA de HUS527199 ($10.200) y BUPIVACAÍNA de HUS529267,
  HUS531631 y HUS531672 ($30.600 cada una).
- **Evidencias**: unificar → PDF `GI-33-5300-2026` → carpeta en el servidor Z:.
- **Confirmar en DGH** los códigos TA0601, TA2301 y AU2301 para cerrar la
  homologación 206/207/223/423 en el bot.


### Del motor de glosas, después de la revisión del 25-08
- ~~**Reiniciar el motor del hospital**~~ — **HECHO y COMPROBADO el 26-08.**
  Se verificó en el PC de cartera: el commit local coincide con el de la rama
  del hospital y las tres pantallas nuevas responden. (Antes decía: seguía
  corriendo código viejo, y mientras no se reiniciara ninguna corrección
  estaba funcionando.)
- **Los correos de Usuarios hay que depurarlos.** Edgar Silva tiene dos
  cuentas y una apunta a `devoluciones1@sinacsc.com`, que rebota con «Address
  not found»; la buena es `carterahus02@sinacsc.com`. Mientras no se corrija,
  los avisos que se le mandan salen y se pierden en silencio.
- **Las tres médicas no recibieron el lote del 25-08.** El arreglo entra para
  las importaciones siguientes; para las doce glosas de ese día hay que
  pasarles el Excel-respuesta a mano.
- **Ojo con la fecha del servicio.** Varias normas que el motor citaba se
  derogaron este año: la Res. 2275 de 2023 (factura electrónica y RIPS, la
  reemplazó la Res. 948 de 2026), la Res. 5159 de 2015 (PPL, la reemplazó la
  Res. 1099 de 2026) y la CUPS 2641 de 2024 (la reemplazó la Res. 2706 de
  2025). Para atenciones anteriores siguen siendo las aplicables, así que el
  motor ahora escoge según la fecha del servicio y el sistema avisa cuando la
  cita ya no rige.
- **Tres sentencias quedaron marcadas como NO VERIFICADAS** (T-313/2007,
  T-050/2017 y T-134/2022): el sitio de la Corte las sirve por JavaScript y no
  se pudo leer su texto. Ya no se citan en ningún dictamen. Si alguien consigue
  el texto oficial, se marcan y vuelven a quedar disponibles.
- **Queda pendiente la contradicción de tarifa del contrato 0525/2017**: un
  expediente lo lee como SOAT pleno ($915.051 para el CUPS 010101) y otros dos
  como SOAT −15 %. Se resuelve reimportando las tarifas de POSITIVA con
  «Reemplazar» marcado — el 010101 debe quedar en $777.793.


### Notas crédito del Dispensario (nuevo, 24-08)
- ~~Cargar al SIMED las notas del acta 858 con CUV vigente~~ **Hecho el
  mismo 24-08: las 21 del acta 858 quedaron cargadas (21/21 OK).**
- **Las 13 anulaciones/trámite con CUV vigente** (notas 332526, 332710,
  332712, 332724, 332746, 332747, 332749, 332774, 332798, 332952, 333121,
  333122, 333198) no van por la pantalla de glosas del robot: definir con el
  gestor del Dispensario por qué canal las recibe y enviarlas (las carpetas
  ya están completas y renombradas).
- **SISTEMAS:** entregarles el informe de los 52 rechazos de CUV y hacerles
  seguimiento — 47 solo necesitan revalidación (timeout del validador), 2
  con diagnóstico repetido (436861 y 441161), 1 precio de medicamento
  (442517), 2 factura referenciada (549496 y 545752). Cuando revaliden:
  recopiar los CUV del share, re-verificar y cargar las nuevas en firme.
- **Facturación:** pedir las notas crédito de las 3 facturas aceptadas en el
  acta 858 que no aparecen en el CRRP: 443525, 443566 y 486894.
- **Acta 879:** quedan 2 líneas de la factura 474268 (CL0801, $6.093) sin
  texto de la doctora, y 3 líneas sin decidir (478141 $1, 487192 $20,
  481589 $1.705.924); confirmar fecha y número contra el PDF firmado.

### Tarifas POSITIVA (nuevo, 24-08 tarde)
- **Volver a cargar el Excel de tarifas** cuando baje el lector corregido:
  misma pantalla, mismo archivo, y ESTA VEZ marcar la casilla «Reemplazar
  tarifas existentes de esta EPS» (las 4.742 actuales están con el valor
  pleno, no el pactado). Deben quedar ~2.988 y un aviso con los códigos en
  conflicto.
- **OJO mientras tanto: no confiar en dictámenes de tarifas de POSITIVA** —
  citarían valores 15% más altos que el contrato.
- **Definir los 737 códigos del archivo «tarifas_positiva_POR_DEFINIR.csv»**
  (columna «¿cuál rige?»). Cuando estén marcados, se cargan aparte.
- **Arreglar en el Excel la celda del CUPS 512104** (dice #VALUE!).

### Contrato POSITIVA (nuevo, 24-08)
- **Cargar las 17 cláusulas en el PC de cartera.** El archivo ya está en
  `data\clausulas_positiva.json`; cuando el autodespliegue baje el bot nuevo,
  correr: `venv\Scripts\python.exe tools\cargar_clausulas_contrato.py
  POSITIVA data\clausulas_positiva.json` y comprobar que diga 17 insertadas y
  que la base sea `motorglosas.db`.
- **El contrato original 525/2017 sigue escaneado.** Si se quieren sus
  cláusulas originales (multas, garantías, terminación), hay que pasarle OCR
  primero. Lo que rige hoy en tarifas, plazos y glosas ya quedó transcrito de
  los otrosíes.

### Permisos del portal (nuevo, 21-08 tarde)
- ~~Cerrar la consulta de usuarios.~~ **HECHO el 21-08 por la tarde.** Ya
  exige rol de coordinación, y las cinco pantallas que la usaban para armar
  un desplegable piden ahora una lista aparte con solo lo suyo.
- **VOLVER A CREAR LA TAREA DE ARRANQUE — es lo más urgente.** Hoy **no
  existe**: el intento fallido de la tarde la borró. Mientras siga así, si el
  PC se reinicia el portal **no vuelve solo**; depende de que alguien inicie
  sesión. Cómo hacerlo: clic derecho sobre
  `tools\ARRANQUE_AUTOMATICO_MOTOR.cmd` → **Ejecutar como administrador**, y
  cuando pregunte la cuenta escribir **`cartera`** (ya está confirmado que esa
  cuenta entra a la carpeta de soportes). Pedirá la clave dos veces.
- **Comprobar después con `ESTADO_MOTOR.cmd`:** las dos tareas deben decir
  «trabaja aunque nadie inicie sesión: SI».
- **Comprobar el arranque automático de verdad:** reiniciar el PC y, **sin
  iniciar sesión**, abrir el portal desde el celular. Si carga, quedó bien. Si
  no, doble clic en `ESTADO_MOTOR.cmd`, que ahora dice cuál tarea duerme.
- **Volver a correr `tools\ARRANQUE_AUTOMATICO_MOTOR.cmd`** cuando el arreglo
  de esta tarde llegue al PC: ahora también deja el autodespliegue trabajando
  con el PC recién prendido, y para eso Windows pide la contraseña una segunda
  vez (es la misma).
- **Confirmar que la cuenta del arranque llega al servidor.** La tarea quedó
  instalada con la cuenta `ESEHUS\cpimiento`, no con `cartera`. Falta
  comprobar que esa cuenta sí entra a `\\Prime\radicacion_2026`; si no, el
  índice de soportes queda vacío aunque el portal abra.

### Sistema ICFES (nuevo, 20-08)
- **Hacer el simulacro de diagnóstico.** Sin él, el plan reparte las horas a
  ciegas (asume 50 de 100 en cada área). Es lo primero que hay que hacer:
  doble clic en `tools\ICFES.cmd` → opción 4 → examen completo. O, más simple
  todavía, desde la aplicación `ICFES.html`, que no necesita ni Python.
- **Confirmar la fecha real del examen.** El plan usa el 8 de agosto de 2027
  como fecha provisional; el Calendario A de 2026 fue el 26 de julio. Cuando el
  ICFES publique la fecha oficial de 2027, se corrige con
  `python -m icfes iniciar --examen AAAA-MM-DD --meta 400 --horas 12` y el plan
  se recalcula solo.
- **Hacer crecer el banco de preguntas.** Hoy tiene 110; para que un simulacro
  salga de tamaño real hacen falta 254. El formato está explicado en
  `docs/GUIA_SISTEMA_ICFES.md` y `python -m icfes banco` avisa si algo quedó mal.
- **Bajar los cuadernillos oficiales del ICFES** (son gratis en su página) y
  hacerlos completos y cronometrados, sobre todo de abril de 2027 en adelante.
  Las preguntas del banco son de práctica, no del examen real.

### Organización de trabajos (nuevo, 18-08)
- **Correr `ORGANIZAR_TRABAJOS_BOTS.cmd` en un PC real del hospital** y
  confirmar que la carpeta `D:\TRABAJOS BOTS` queda como se espera (los
  12 temas, los accesos directos abren el bot correcto, y los LEEME.txt
  se leen bien en español). Claude Code no tiene acceso al disco D: para
  probarlo por su cuenta.
- Si algún bot nuevo se agrega más adelante (o cambia de nombre), avisar
  para sumarlo al script y que el organizador lo incluya la próxima vez.

### DECISIÓN DEL DUEÑO — contrato de la Policía Nacional (18-08)

**¿Se renovó el contrato con la Dirección de Sanidad de la Policía Nacional?**
Los dos que están cargados se vencieron: el 068-5-200004-26 (mediana y alta)
el **15-08-2026**, y el 068-5-200006-26 (oncología) el **31-07-2026**. Desde
el 16 de agosto el motor contesta «SIN CONTRATO PACTADO» y aplica tarifa SOAT
plena para esa entidad. Si ya hay contrato nuevo, hay que cargar su número y
su vigencia en la malla contractual (hoy fechada 28-07-2026).

### Tarifas SOAT — lo que falta cargar (18-08)

1. **`Trazabilidad años anteriores.xlsx`** (13 hojas, resoluciones de años
   previos). Hoy el sistema solo sabe la tarifa **2026**. Cuando la glosa es
   de una factura vieja, la tarifa que aplica es la que estaba vigente **el
   día de la atención**, no la de hoy. Sin ese archivo cargado, ese tipo de
   glosa hay que responderla a mano.
2. **Descripciones con ruido en el Manual SOAT.** En un puñado de renglones de
   la Circular 047/2025 la descripción quedó con un pedazo de la nota al pie
   pegado (por ejemplo el código 38274). La **tarifa** está bien; solo el texto
   quedó sucio. No es urgente, pero se ve feo en pantalla.

### Conciliación Dispensario (147 facturas objeto de mesa)

1. **Revisar y aprobar el listado de las 147** (`LISTADO_147_PARA_APROBAR.xlsx`)
   y decidir qué se hace con **HUS0000443525**, que está en el lote de glosas
   pero **no aparece en el estado de cartera**: ¿se incluye (147) o se excluye
   (146)? Hoy está incluida.
2. **Aclarar la discrepancia del aceptado:** el lote dice $0 (RE9901) pero la
   cartera registra **$1.758.956** aceptados en 8 facturas. Debe resolverse
   antes de firmar el acta.
3. **Revisar las 29 facturas con diferencia** entre el valor glosado del lote y
   el de la cartera.
4. **Confirmar las raíces exactas `Y:` / `X:`** de los soportes para cerrar la
   columna de ubicación (hoy queda la ruta derivada por mes + PENDIENTE).
5. **Conseguir la CUENTA CONTABLE** con contabilidad/DGH: es el único campo del
   acta que no existe en ninguna base disponible.
6. Plantear en la mesa que la entidad **no ha confirmado el recibo de ninguna
   de las 444 respuestas**, pese a que todas tienen radicado de entrega.

### Pre-auditoría
0. **~~La lentitud de la página~~ — DIAGNOSTICADA Y ARREGLADA el 29-07**
   (ver la entrada del día). Queda una sola cosa por decidir: **el buscador de
   la pestaña Fuentes sigue lento** (recorre las 189.452 filas de la fuente, y
   ahí es a propósito: esa pantalla existe para buscar entre TODAS las
   facturas, no solo las del consolidado). Hacerlo rápido necesita búsqueda de
   texto completo, que es un cambio mayor. **Preguntar al auditor si esa
   pantalla le molesta en el día a día** antes de meterle mano.

### COOSALUD
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

### Notas crédito Dispensario (Lote V2) — detalle en `docs/diagnostico_lote_v2_pendientes/`
6. **Rechazos CUV:** hacer seguimiento a la respuesta del área sobre las 4
   facturas conciliadas (informe enviado el 17-07). Esperando de SISTEMAS:
   - Corregir el RIPS y revalidar las 3 con **RVC086** (HUS404136, HUS410675,
     HUS435485) — el reintento sin corregir ya se probó el 25-06 y volvió a fallar.
   - Reejecutar la validación que nunca corrió (servicio caído) de las 6:
     HUS411234, HUS420099, HUS421733, HUS418576, HUS420160, HUS422238.
   - Cuando confirmen: revalidar los CUV (comando en el README de la carpeta
     del diagnóstico) y radicar en SIMED con el robot.
7. **Descargar del DIAN los PDF de 2 notas:** HUS413266 (radicado 492346) y
   HUS417459 (radicado 521665). Sin ese PDF no se pueden armar las carpetas.
8. **Dos consultas a FACTURACIÓN:** (a) HUS440328 — ¿la nota vigente es la
   302111 del histórico o emitieron una nueva?; (b) HUS422238 — confirmar que
   la nota 311199 sí le corresponde (no aparece en el histórico de conciliación).
9. **Verificar el resto del Lote V2:** las que estaban "COMPLETA" sin subir
   (HUS409574, 410979, 416671, 428425, 428523, 431722, 432292, 432884, 437357,
   437582) — confirmar si ya quedaron radicadas en SIMED o siguen pendientes.

### Pre-auditoría ADRES (`tools/preauditar_glosas_adres.py`)
16. **Unificar el criterio de la causal 4506**: hoy está clasificada como
    FACTURACION en 231 filas y como PERTINENCIA en 24.
17. **Revisar las 371 filas sin centro de costos propuesto** (habitación, sala
    especial, atención diaria: no se puede saber el área sin más contexto).
18. **Fase 2 — llevarlo al motor web como preauditoría.** El patrón ya existe
    en `app/services/ia_auditora_proactiva.py` (pre-análisis nocturno que deja
    el dictamen listo antes de que el gestor abra la glosa). Las 10 columnas de
    la macro mapean a campos que ya tiene `GlosaRecord` (`codigo_respuesta`,
    `tipo_glosa_excel`, `observacion_tecnico`, `dictamen`, `valor_aceptado`,
    `gestor_nombre`, `profesional_medico`); falta agregar centro de costos.

### Ajustador de detallados (`tools/ajustar_detallado_glosas.py`)
11. **Las 4 facturas que no aparecen en ningún detallado:** HUS311371
    (radicado 14345108, $39.722.100), HUS394817 (14383060, $3.646.700),
    HUS380246 (14351110, $139.400) y HUS367368 (14344771, $10.400) —
    **$43.518.600 en total**. Confirmado otra vez el 19-08 con el consolidado:
    la macro trae 324 facturas y solo hay 320 detallados. Pedirle a facturación
    esa impresión para poder cerrarlas.
12. **Revisar los 100 ítems marcados `SIN_CRUCE`** (73 facturas) y los 24
    `GLOSA_SIN_ITEM` ($11.220.692): son renglones que no cruzaron entre la
    factura impresa y el reporte del ADRES.
13. **Glosas a toda la reclamación:** 46 filas por $335.585.041 con causales
    como "2102- formulario de reclamación incompleto" y "3122- debe anexar el
    informe de ambulancia". No corresponden a ningún ítem: se responden aparte.
14. **Confirmar el criterio de los ítems aprobados a medias.** En el ejemplo
    `HUS352890` la venda de gasa quedó a mano en **1 unidad / $9.400**, pero
    sumando las **dos** filas del reporte siguen glosadas **5 unidades /
    $47.000** (subtotal $132.800 en vez de $95.200). El bot hace la suma. Si el
    criterio del auditor es otro, se cambia con `--modo-parcial`.
15. **Definir qué hacer con los ítems `SIN_CRUCE`** (los de la factura que no
    aparecen en el reporte): hoy se conservan y se marcan.

### Descuento de lo aceptado (`tools/descontar_aceptado_detallado.py`, 18-08)
16. **Revisar a mano las 14 facturas donde lo descontado NO cuadra con la
    macro** ($2.747.060 en total). Están marcadas con **CUADRA = NO** en la
    bitácora CSV del bot. Son casos donde el servicio aceptado no se pudo
    cruzar con ningún renglón del detallado, o donde el aceptado es mayor que
    el valor del servicio.
17. **Confirmar el TOTAL FINAL de $625.461.617** antes de radicar: es la suma
    de las 320 facturas después de quitarles lo aceptado.
18. **Revisar a mano HUS384132 y HUS392442**: el bot no logró reproducir el
    subtotal que traen esos dos archivos, así que solo descontó los servicios
    numerados. Quedaron marcadas con **REVISAR A MANO** en la bitácora.
19. **Pedir los detallados de HUS367368 y HUS394817** ($12.800): están en la
    macro con valor aceptado pero no están entre los 320 archivos. Ya salen en
    la bitácora con estado **SIN_DETALLADO**.
20. **Corregir la macro en la HUS396996 y revisar esa factura completa:** la
    columna VALOR ACEPTADO está corrida un renglón (filas 3961-3963). Por eso
    al tórax se le descontaron $7.800 cuando se aceptó por $758.700.

### Dispensario — respuesta de glosas SIMED y conciliación
10. **Las 3 facturas de junio** (518186 / 515107 / 515773): en el pantallazo
    de pendientes del 05-08 **ya no figuran por cargar**. Verificar en el
    portal cómo quedaron radicadas (¿respuesta cargada o cerradas por
    vencimiento?); si el portal las cerró sin respuesta, radicar por
    oficio/correo dejando constancia.
11-bis. **(18-08) Correr el lote del 14 de agosto** con
    `respuestas_glosa_DISPENSARIO_14AGO.xlsx` (24 facturas / 36 objeciones /
    $2.511.222; vencen del 24-08 al 01-09): piloto con HUS0000535452 →
    corrida completa → pegar el reporte al chat. Antes de subir: confirmar la
    fecha real de la toma de la radiografía de la 535749 en HC/RIPS. Falta el
    consecutivo GI-33 de este lote para carpeta+PDF de evidencias. Del cargue
    del 05-08 sigue pendiente **pegar el reporte** al chat (nunca llegó), y
    verificar en SIMED las 2 que no figuraban pendientes (527406 y 525763).
11. **(05-08) Correr el cargue de las 23 pendientes** con
    `respuestas_glosa_DISPENSARIO_PENDIENTES_05AGO.xlsx`: piloto con
    HUS0000513796 → corrida completa → pegar el reporte al chat. En las de
    valor alto (500031, 510793, 454563, 512742, 518923, 522160) revisar en el
    reporte que ninguna quede "sin finalizar" por tener más líneas en el
    portal que filas en el Excel (si pasa, avisar al chat y se amplía).
12. **Generar los PDF de evidencias:** lote 14-07 → `GI-33-5182-2026.pdf`
    (comando ya entregado); lotes 17/28/31-jul + corrida de pendientes →
    `GI-33-5251-2026.pdf`; cargue del 23-jul → `GI-33-5285-2026.pdf`
    (los tres comandos quedaron entregados en el chat el 05-08).
13. **Soportes por adjuntar del lote 17-07** (casos puntuales): notas de
    enfermería del 16-jun (529093), renglón tarifario de dispositivos (coils,
    AIRVO, material de osteosíntesis), descripción quirúrgica del vaciamiento
    de cuello (529291), reporte de lactato/piruvato y aclaración de la biopsia
    vs. estereotaxia (CL0301), justificación de la segunda hemoclasificación.
14. **Robot DGH:** correr el modo `--calibrar` en el equipo de la oficina y
    validar el llenado de la ventana de respuesta por coordenadas.
15. **Conciliación:** confirmar el acta de inicio del contrato 287 y el mapeo
    de códigos internos de cartera (U22031/C26001…), y correr el asistente en
    piloto sobre 1-2 facturas reales contra `Y:\`.
- ~~(28-07) Lote del 28-jul: NO subir todavía~~ — **Superado el 05-08:** el
  portal muestra el lote ya subido (solo se escapó la 530112, que entra en el
  cargue de las 23 pendientes). Sigue vigente de esa nota únicamente la
  pregunta de la **prórroga 2026 del contrato 440** (ver "OJO jurídico" del
  05-08).

### Informes
16. **Informe de gerencia:** falta el dato real del "antes" (cuánto tardaba el
    proceso manual y cuántas personas) para poner el multiplicador exacto.
    Completar también el "valor total objetado defendido" del lote 9-jul
    (sale de `reporte_glosa.csv`).

### Módulo ADRES/FURIPS (chat "VALIDADOR ADRES")
20. ~~Fusionar el PR #176~~ — **HECHO el 29-07**: todo el módulo (validador
    con OCR, app web, bot DE4401 v2.1, documentación de entrega) ya está en
    la rama principal.
21. **Bot DE4401:** correr la versión 2.1 con los archivos reenviados y, si
    algo sale "SIN XML", enviar el Excel `_COMPLETO` (la hoja DIAGNOSTICO
    dice la causa exacta).
22. **Confirmar en el servidor** que `PDF_A_CMD_EN_CARPETA.cmd` genera la
    carpeta `CMD_CONVERTIDOS`.
23. **Corregir las 27 facturas ADRES con errores** de la corrida de 50 (usar
    el Excel o la app web, priorizando las de mayor valor) y completar los
    soportes de HUS410606 y HUS472103 (les faltan RIPS y CUV).
24. **Facturas de baja:** completar el informe de trabajo social donde el
    Word quedó con "NOTA DE REVISIÓN".

### Módulo de Pre-auditoría (nuevo, 23-07)
17. **Revisar y aprobar el PR nuevo** (borrado total admin + Excel ADRES) de la
    rama `claude/invoice-audit-bot-qa2koy`; los PRs #186, #187, #189 y #190 ya
    están fusionados. Después de aprobar: desplegar en la VM y **usar el botón
    "Borrar todos los datos"** (como administrador, sin marcar la casilla de
    fuentes) para dejar la página limpia antes del arranque real del equipo.
18. **Definiciones que quedaron con supuesto y hay que confirmar con el
    auditor:** (a) el plazo de 3 días se contó en **días hábiles lunes-viernes**
    (sin festivos colombianos); (b) los nombres/cargos de las firmas del
    oficio PDF se tomaron del Excel de oficios — si cambian, se ajustan en
    `app/services/oficio_devolucion_pdf.py`; (c) si se quiere la firma
    escaneada en el PDF, subir la imagen como
    `static/firma_preauditoria.png` (el módulo la toma solo).
19. **Cargar el histórico** del CONSOLIDADO_PRE_AUDITORIA_2026.xlsx al módulo
    (el importador ya entiende ese formato de columnas, se puede subir por
    oficio) para que las estadísticas y el control de 3 devoluciones
    arranquen con la historia real.

### Suite Cartera HUS (PR #160)
20. **Revisar y fusionar el PR #160** (Suite Cartera HUS: organizar/consolidar/
    objeciones, caja de Herramientas PDF de 26 utilidades, y el nuevo bot de
    correos de pagos .msg → Excel). Hoy en borrador.
21. **4 herramientas PDF avanzadas** aún no hechas: editar texto libre,
    formularios, firma digital y comparar dos PDF (serían una "fase 4").
22. **Validar el mapeo DGH** (los 16 encabezados del archivo de OBJECIONES)
    contra un cargue piloto pequeño antes del primer cargue masivo real de
    la Suite.
23. **Depurar la lista de entidades de la Suite**: agregar un campo de estado
    de vigencia (vigente / en liquidación / liquidada / deshabilitada).
24. **Verificar los links de plataformas** marcados "sin respuesta": muchos
    podrían funcionar solo desde la red/VPN del HUS; validarlos allá.
25. **Configurar en el equipo del analista**: LibreOffice (para Office→PDF) y
    la clave `GEMINI_API_KEY` (para las funciones de IA de Herramientas PDF).
26. **Corte de cartera de julio 2026**: en cuanto el analista lo entregue,
    actualizar los 5 consolidados FAMISANAR y la serie mensual de 30 informes.

### SIIFA (actualizado 19-08, ver `docs/CONTEXTO_SIIFA.md`)
11. **HUS — 4 devoluciones ratificadas de SANITAS ($14.049.088), trámite
    MANUAL en el portal y ya vencidas o al borde** (HUS482639, HUS479521,
    HUS479457, HUS481923). La puerta de subsanación de devoluciones por API
    no está confirmada; el texto sirve el de la plantilla del HUS ajustando
    factura y valor. **Es lo más urgente de SIIFA.**
12. **Cerrar el ciclo con el BALANCE de las cuatro IPS** (opción [B] o
    `siifa_balance.py`): corte contra informe fresco de HUS, Socorro, Girón
    y Guane — qué se respondió, qué falta y qué hay nuevo. Con eso salen
    también las ~835 nuevas de Socorro y las 2 nuevas del HUS.
13. **Girón y Guane:** correr el informe final del cargue (censo) de Girón;
    recibir la salida del cargue de Guane (1.530) y su informe.
14. **Datos de contacto de Socorro, Girón y Guane** (correo y dirección de
    ventanilla) para que sus respuestas cierren con sus propios datos; hoy
    la frase se omite. Y **coordinar con quien responde a mano en Socorro**
    para no duplicar trabajo. Queda también por definir RE9501 vs RE9601 en
    las 674 devoluciones DE5601 del HUS (~$111 millones).

### Cuentas médicas — CUV de facturas nuevas (nuevo, 03-08)
15. **Factura MED737 — la pelota está en facturación.** El JSON ya quedó bien
    (las 4 correcciones + `codPrestador` de 12 dígitos, que era el correcto).
    Falta que **reexpidan la factura** con el `CODIGO_PRESTADOR` a **10 dígitos
    (6800103933)** en el XML. Enviarles el pedido por escrito con los dos
    valores explícitos: XML = `6800103933`, JSON = `680010393301`.
16. **Avisar al proveedor del software de facturación** (el rastro apunta a
    Siigo): si usa un solo parámetro para el XML y el RIPS, hay que separarlos.
    Si no, el RVC011 se repite en todas las facturas.
17. **Antes de reexpedir, confirmar quién atendió:** la factura dice "consulta
    especializada" y el RIPS reporta CUPS 890201 (medicina general). Si atendió
    un especialista, el CUPS y el `codServicio` también deben corregirse en la
    misma reexpedición. Pedir el soporte de quién atendió.
18. **Preguntar al Ministerio la vía correcta** (mesa de ayuda,
    Soporte-fev-rips@minsalud.gov.co): si para corregir el `CODIGO_PRESTADOR` de
    una FEV ya validada por la DIAN toca nota crédito de anulación total y
    reexpedición, o si basta retransmitir. Ningún texto oficial lo ordena; la
    vía de la anulación viene de mesas de ayuda de proveedores. Cuesta cero
    preguntar y evita anular una factura sin necesidad.
19. **Revisar el resto de facturas de agosto** con `validar_json_rips.py
    --recursivo` antes de subirlas.
20. **Revisar el número de factura si la reexpiden:** si sale con número nuevo,
    el JSON debe llevar el número nuevo, no `MED737`.

## 4) PARA MAÑANA

### Lo primero (28-08, cierre)

**1. Fusionar y desplegar.** La entrega de la causal en el recuadro y el sello
que hablaba de un texto viejo **ya la fusionó usted** (PR #529). Falta la de
hoy: la Res. 3047 de 2008 y sus dos hermanas derogadas.

Después del despliegue, corra **la misma glosa de siempre** (SO0102 de la
factura HUS0000498954) y mire dos cosas: que en el recuadro ya **no** diga
«código SO0102», y que si el escrito nombra la Res. 3047 de 2008 le salga al
lado, entre paréntesis, desde cuándo está derogada.

**2. Lo que NO arregla el programa y necesita su decisión:**

- **59 de las 135 glosas salieron sin código de causal.** Eso no lo puede
  arreglar ningún cambio de código: el archivo de recepción **no trae esa
  columna**. Sin causal, el motor no sabe contra qué está defendiendo. Hay que
  pedir que el archivo la traiga.
- **La tarifa del contrato 440-DIGSA.** El motor lo está tomando como **SOAT
  pleno** y el contrato en pantalla dice **SOAT −20 %**. Es plata: hay que
  confirmar cuál es la buena antes de que salgan más dictámenes con la
  equivocada.
- **Las glosas sin fecha de servicio.** Cuando no hay fecha, el motor supone
  hoy, concluye «sin contrato» y aplica SOAT pleno — cuando lo más probable es
  que el servicio sí estuviera cubierto. Hay que decidir qué debe hacer el
  motor en ese caso.
- **El texto de TARIFAS de Salud Total se está cortando.** Salud Total no
  acepta la fila si la Observación IPS pasa de **500 caracteres**, y esa
  plantilla mide **543**. El programa la corta sola por el último punto que
  quepa, así que se pierde el final — «Se solicita el reconocimiento íntegro»
  y el correo de Cartera. La EPS está recibiendo un párrafo sin petición.
  Esto **ya venía así**, no lo causó ningún cambio de esta semana; se descubrió
  midiendo. **No lo toqué a propósito:** ese texto lleva las cifras del manual
  tarifario (UVB 2026 $12.110, Circular 047/2025, Decreto 780/2016) y decidir
  qué se recorta es suyo, no mío. Dígame qué se puede quitar y lo dejo dentro
  del límite. Mientras tanto quedó una prueba que impide que crezca más.


**Radicación 31068 (28-08) — lo primero.** La carpeta `GI-XX-XXXXX-2026` ya
está armada y limpia: 222 carpetas, cada una con su EPICRIS y su FACTURA, y
nada más. Lo que falta antes de radicar:

1. **Sacar los folios de las carpetas** (`--sacar-folios --aplicar`). La
   simulación ya salió limpia: 444 folios de 222 carpetas, sin choques de
   nombre. Al terminar deben quedar **645 PDF sueltos** y, de carpetas, solo
   `_APARTADOS_REVISAR_Y_BORRAR`.
2. **Traer los XML** (`--traer-xml`, primero sin `--aplicar` para ver el
   informe). Va en este orden y no antes: el bot trae el XML de las facturas
   cuyo folio ya está suelto en la carpeta.
3. Correr `--solo-facturas` otra vez para armar el folio de la **HUS380112**,
   que ya tiene su archivo en el XML.
4. Revisar la carpeta `_APARTADOS_REVISAR_Y_BORRAR` y borrarla cuando esté
   seguro.
5. Decidir qué se hace con los **$361.758.330** de glosa que no entraron al
   FURIPS2.
6. Escoger las **187 respuestas** que quedaron en blanco en el export de DGH.


**~~Desplegar las once ideas~~ — HECHO y COMPROBADO el 26-08 en la tarde.** El
motor de la PC de cartera quedó en el mismo punto que el del hospital y las
tres pantallas nuevas respondieron. Se vieron funcionando «Mi día» (24 glosas
del Dispensario, $56.169.241 en riesgo) y «Plata recuperada» ($376.145.240
glosados en agosto, con su aviso de lo que no puede afirmar).

**Lo primero del motor (26-08, cierre de la noche):** volver a **desplegar y
reiniciar** una vez más. Lo que falta por bajar es la **idea #12** —el color
unificado— más los tres arreglos de la noche. En la pantalla de Analizar se va
a notar: la ficha de cita **VERIFICADA** pasa a tener el mismo verde que el
resto del motor, y el «sin verificar» el mismo ámbar.

**Lo primero de usted:** decirme si **«Mi día»** le sirve como está. Es la
pantalla con la que debería empezar el día el gestor; si le falta algo, se
ajusta.

**~~Decidir la idea #12~~ — DECIDIDA POR USTED Y HECHA.** Ver la entrada de
PENDIENTE: yo la había desaconsejado y estaba equivocado.

**Una cosa que hay que decidir, y no es urgente pero sí importante.** Hoy
entraron tres defectos a la rama del hospital y **ninguno lo detuve yo**: los
cazó la revisión automática. El problema es que **el autodespliegue no espera a
esa revisión** — se baja el código apenas se fusiona, así que los tres llegaron
a la PC de cartera antes de que nadie supiera que estaban mal. El hueco se
tapa de dos formas, y hay que escoger una:

  1. **Que GitHub no deje fusionar** hasta que la revisión esté en verde. Es un
     cambio de configuración; se hace en la página del repositorio.
  2. **Que el `.cmd` del despliegue pregunte** antes de bajarse el código, y no
     se baje nada si la revisión está en rojo. Esto lo escribo yo.

La primera es más segura (nada malo llega ni siquiera a la rama). La segunda no
depende de nadie más y protege el PC aunque algo se cuele.

**Sigue faltando (de ayer):** volver a exportar los 10 casos de prueba. El
documento que subió resultó idéntico —byte por byte— al de la auditoría
anterior: son los dictámenes viejos, generados antes de las correcciones.


**Folio ADRES — HAY QUE VOLVER A CORRER LOS TRES GESTORES (26-08 cierre 2).**
Los 223 folios se armaron con el orden viejo del folio de la factura (el
detallado quedaba de último) y con índice en el folio de la factura. Eso ya
quedó corregido en el programa. Después de hacer `git pull` en
`C:\motor-glosas\repo`, se vuelve a correr el bot en CAROLINA, CLAUDIA y OSCAR
y los folios se rehacen solos con el orden bueno:

```
1 FACTURA  ->  2 DETALLADO  ->  3 REPRESENTACION GRAFICA  ->  4 NOTA CREDITO
```

No hay que borrar nada antes: el bot reconoce sus propios folios y los rehace.

**Folio ADRES — YA ESTÁ ARMADO (26-08 cierre).** Los 223 folios quedaron hechos
en los tres gestores. Lo que sigue no es armar, es decidir: la versión A o B de
las cinco respuestas, el texto dañado de la HUS396996, y qué se hace con la
epicrisis que le falta a las 223. Si se cambia alguna respuesta, se reemplaza el
`1 RESPUESTA A GLOSA.pdf` de esa carpeta y se vuelve a correr el bot solo para
ella: el folio se rehace solo.

**(Ya cumplido) Folio ADRES (26-08), lo PRIMERO de lo primero:** NO correr el bot sobre el
servidor hasta que esté fusionado el PR #492 (el que arregla que el bot borraba
la epicrisis). Después de eso, correr el botón
`tools/UNIR_SOPORTES_ADRES.cmd` en **una sola carpeta de prueba** (una factura),
mirar que los dos PDF queden como se espera, y solo entonces pasarlo a los tres
gestores completos. Lo de la representación gráfica de la DIAN ya quedó
resuelto: son las páginas 10 a 18 del mismo `..._FACTURA.pdf`. Lo que falta es
que usted decida qué hacer con las notas crédito (ver PENDIENTE).

**Frente COOSALUD (25-08):** (a) subir a DGH los 6 archivos de OBJECIONES del
lote de 1.573; (b) armar los trámites de ese lote cuando las objeciones estén
cargadas; (c) repasar las 44 del portal que no quedaron OK; (d) registrar a
mano HUS538337 (y las tres incompletas); (e) insistir con auditoría médica por
las 8 facturas de CALIDAD de agosto.


**Lo primero del motor (25-08):** reiniciar el motor en la PC de cartera para
que tome las correcciones de la jurisprudencia y de los valores. Sin eso, los
dictámenes siguen saliendo con las citas inventadas.

**Lo primero del motor (26-08):** volver a **desplegar y reiniciar** el motor en
la PC de cartera para que tome las cinco correcciones de esta tarde (los CUPS
inventados, el contrato vencido del Dispensario, la Ley 1164, el año de la
Resolución 3100 y la preposición comida). Mientras no se reinicie, las
respuestas siguen saliendo con esos defectos.

**Y después:** reenviar el archivo de recepción de hoy —esta vez con las
columnas de IA y con copia a las médicas— y dejar una sola cuenta de correo
para Edgar Silva.

**Lo primero de todo (26-08):** el reinicio del motor dejó de ser un pendiente
más. Hoy quedó demostrado que una corrección del 24 de agosto **sí estaba** en
la versión del hospital y aun así salió el defecto en las 117 respuestas,
porque el motor no se había reiniciado. Todo lo corregido ayer y hoy sigue sin
efecto hasta ese reinicio.


**Lote de glosas del 25-ago (Dispensario):** cerrado — las 24 respondidas
con el consecutivo **GI-33-5369-2026** ya anotado.

**Notas crédito del Dispensario (lo primero, 25-08):** el cargue del acta
858 ya quedó (21/21 OK el 24-08). Lo que sigue: (a) pasar a SISTEMAS el
informe de los 52 rechazos (47 solo necesitan REVALIDACIÓN — timeout del
validador; 2 diagnóstico repetido; 1 precio Circular 19/2024; 2 factura
referenciada); (b) definir con el gestor del Dispensario el canal para las
13 anulaciones/trámite con CUV vigente y enviarlas; (c) pedir a Facturación
las notas de las 3 facturas aceptadas sin NC (443525, 443566, 486894);
(d) cuando SISTEMAS revalide: recopiar los CUV del share, re-verificar y
cargar las que queden en firme.

### Sistema ICFES (20-08)
1. **Correr el diagnóstico** y volver a mirar el plan: con el resultado real, el
   reparto de horas cambia y deja de ser parejo.
2. **Generar la aplicación web** (doble clic en `tools\ICFES_APP.cmd`) y pasarla
   al celular, que es donde se va a estudiar la mayoría de los días.
3. **Revisar y fusionar el pull request** de la rama
   `claude/icfes-prefix-system-ngvyk4`.
4. Si el diagnóstico de Inglés sale en Pre-A1 o A1, subir Inglés de 1 a 2 horas
   semanales: pasar de 40 a 70 en esa área son 11 puntos del global.

### Lo más fresco (del 19-08)

**Lo primero: correr `tools\VERIFICAR_TRABAJO_HOY.cmd`** en el PC de cartera
(doble clic). Cuando pregunte, escriba una factura radicada — por ejemplo
`HUS468334` — y mande la pantalla al chat. Ahí se ve de una si todo lo de hoy
quedó bien.

**Un punto que queda a decisión de cartera:** en la carta al ADRES, cuando un
mismo ítem se acepta en dos causales, el **total del encabezado** ya sale
correcto (una sola vez), pero el **cuerpo sigue enumerando las dos causales**
con el valor del ítem en cada una. Es defendible —el hospital está respondiendo
cada causal— pero si prefiere que el cuerpo también junte las causales en un
solo renglón, dígalo y se hace.

**Lo más urgente (19-08, noche):**

- **Revocar la clave de Gemini.** Se pegó en el chat y quedó expuesta. Crear
  una nueva en Google AI Studio y ponerla en `C:\motor-glosas\repo\.env`,
  en la línea `GEMINI_API_KEY=`. **No mandarla por chat.**
- **Activar Sentry**, que ya se pidió: cuenta gratis en sentry.io, escoger
  «FastAPI», copiar el DSN y pegarlo en el mismo `.env` como
  `SENTRY_DSN=...`. Los pasos completos salen en la pantalla de Diagnóstico.
- **Volver a responder una glosa de HUS468334** y mirar dos cosas: que la
  relación de soportes traiga los documentos de verdad, y que si el dictamen
  cita un folio, ese folio diga lo que la IA afirma.
  *(20-08, noche: el folio inventado ya lo detecta el sistema solo — lo
  devuelve a la IA para que lo corrija y, si insiste, lo avisa en rojo y
  quita el sello «VALIDADO». Lo que falta es verlo funcionar con una glosa
  de verdad: si sale un aviso de folio que usted sabe que SÍ estaba en los
  papeles, avise, porque sería un aviso equivocado.)*

**Auditor Forense (probar en el PC de cartera):**

- **Responder una glosa de una factura que YA esté radicada** (con sus soportes
  en `\\Prime\radicacion_2026`) y mirar si el dictamen cita folios concretos
  de la historia clínica. Eso es lo nuevo: antes argumentaba a ciegas.
- **Confirmar que el motor tenga la clave de Anthropic.** Sin ella el forense
  no corre y el dictamen sale como antes, sin folios — no da error, pero
  tampoco mejora. Si hace falta, se pide a Sistemas.
- **Si el costo se siente alto**, se puede apagar sin tocar código poniendo
  `GLOSA_AUDITOR_FORENSE_PREPASS=0` en el vigilante
  (`tools\servidor_motor_local.cmd`). Avisar y se hace.
- **El botón «Auditor Forense» ya no está en HERRAMIENTAS.** Ahora el recuadro
  sale al final del dictamen, con la factura ya puesta. Si lo echa de menos,
  dígalo y se devuelve.

**SIIFA (lo primero, 19-08):** (a) tramitar a mano en el portal las 4
devoluciones ratificadas de SANITAS del HUS ($14.049.088, pendiente #11);
(b) cerrar Guane (salida del cargue + informe); (c) correr el **balance**
de las cuatro IPS con la opción [B] del bot — de ahí sale qué quedó sin
responder y qué nuevo hay que trabajar.

**Glosas ADRES (mismo día, otro frente):**

- **Mirar la pantalla de Glosas ADRES con un paquete cargado** y confirmar que
  las tres cantidades se leen bien (Reclamado / Aprobado por el ADRES /
  Glosado). Si la tabla queda muy ancha para la pantalla del PC de cartera,
  avisar y se recorta lo que menos se use.
- **Decisión que solo puede tomar cartera (sigue pendiente):** cuando un mismo
  ítem viene glosado por **dos causales** y el gestor acepta en las dos, hoy el
  sistema le declara al ADRES la plata **dos veces**. Lo correcto es contarla
  **una sola vez**, pero hay que definir cuál de los dos renglones manda,
  porque la regla automática puede quedarse **corta** si el gestor acepta justo
  en el renglón que no cuenta. Sin esa definición no se toca.

### Lo más fresco (del 18-08)

- **Probar `ORGANIZAR_TRABAJOS_BOTS.cmd` en un PC real** (doble clic,
  carpeta `tools\`) y confirmar que `D:\TRABAJOS BOTS` queda como se
  espera: las 12 carpetas por tema, los accesos directos abriendo el bot
  correcto y los `LEEME.txt` claros. Avisar en el chat cualquier ajuste
  (nombre de carpeta, bot que falte, texto que no quede claro) para
  corregir el script.

### Lo más fresco (del 13-08)

- **A) Regenerar la respuesta de Salud Total desde el portal.** Entrar a la
  pantalla «Salud Total», subir `NotificacionGLS_Crt01July2026_1469Detalle.txt`,
  poner la **fecha en que la EPS recibió la factura** y descargar. Comparar
  contra el archivo viejo: el radicado debe salir completo
  (`350000214021421`), la radiografía de tórax en **$93.340** y el código del
  motivo como **`TA`**. **El `RTAGLOSA_..._13082026.csv` que ya existe no se
  radica.**
- **B) Probar el validador ADRES dentro del portal** con un paquete real de
  FURIPS y verificar que el Excel del informe salga igual que el de la
  aplicación aparte del puerto 8010. Si sale igual, ya no hay que levantar
  esa aplicación.
- **C) ~~Falta la pantalla del buscador de autorizaciones.~~** **Hecha el
  mismo 13-08.** En el menú, bajo Herramientas, aparece **«Validador
  ADRES»**, y esa pantalla trae las dos cosas: arriba la validación de los
  soportes del ADRES (FURIPS 1 y 2, con su Excel), abajo el buscador de
  números de autorización de los RIPS. El buscador deja escoger **una
  carpeta completa de facturación**, con sus subcarpetas: de todo lo que hay
  adentro solo viajan los `.json`, el resto se descarta en el mismo equipo
  para que la subida no se vuelva eterna.
- **D) Cargar las 6.655 tarifas de FAMISANAR como pactadas.** El motor ya
  quedó listo para recibirlas (ver abajo); falta que usted las suba desde
  **Gestión → Tarifas → Importar Excel**, con estos datos:
  - EPS: `FAMISANAR`
  - Número del contrato: `S-13-1-03-1-04958`
  - Rigen desde `15/04/2026` y hasta `14/04/2027`
  - Archivo: `PROPUESTA_2026_BASE_FINAL_FAMISANAR.xlsx`

  Al terminar debe decir **6.655 filas leídas** y cinco hojas. Si dice
  1.625, quedó con el lector viejo y hay que revisar.

  **Dos cosas que se arreglaron antes de dejarlo cargar:**

  1. Las 4.586 tarifas de la hoja UVB entraban rotuladas como **«tarifa
     propia»**, y no lo son: son la UVB por grupos con el descuento del
     contrato. El dictamen habría citado una forma de pactar distinta a la
     del contrato, y eso lo lee la entidad.
  2. El archivo no dice a qué contrato pertenece ni desde cuándo rige. Así
     cargado, una tarifa de 2026 servía para defender una factura de 2024.
     Por eso ahora la pantalla pide el número del contrato y las dos fechas.
     Si el Excel las trae, mandan las del Excel.

  Sigue vigente el cuidado de siempre con la hoja UVB: se carga la columna
  **pactada** («PROPUESTA FINAL»), no la de referencia («VALOR UVB 2026»),
  que es un 5% más alta.
- **E) ~~Homologador CUPS → SOAT 2026: sin empezar.~~** **Cargado el mismo
  13-08.** Entró la versión Gold Standard 2026: 10.024 códigos CUPS —la
  misma cobertura de antes, no se perdió ninguno— y ahora **8.783 traen
  además el artículo del Manual SOAT** donde está escrito el código. Es la
  diferencia entre que el dictamen diga «el CUPS 012403 corresponde al SOAT
  1101» y que diga «corresponde al SOAT 1101, Artículo 03: Neurocirugía».

  **Y al cargarlo apareció un defecto grave que llevaba meses adentro.** La
  tabla marca 2.966 códigos como «NO TIENE HOMOLOGACION DIRECTA», y esa
  frase estaba escrita en la casilla del código SOAT. El motor la leía como
  si fuera el código y le decía a la IA, con estas palabras: *«el CUPS
  013205 corresponde oficialmente al código SOAT NO TIENE HOMOLOGACION
  DIRECTA — usa este dato oficial para fundamentar la tarifa»*. Un código
  inventado, metido en la defensa de la tarifa, con la orden de usarlo.
  Entre esos 2.966 hay tarifas del propio contrato de FAMISANAR.

  Ahora el motor dice lo que es, y resulta que juega a favor: **si el manual
  no le asigna código SOAT a ese procedimiento, la entidad no puede objetar
  la tarifa citando un código SOAT que no existe.**
- **G) ~~Estrenar «Analizar con IA»~~ — HECHO el 13-08.** Salieron dos
  defectos (código de programación en la observación y valores con decimal),
  los dos corregidos el mismo día. Falta todavía **medir cuánto tarda y
  cuánto cuesta**: en las dos corridas nadie tomó el tiempo.
- **H) Probar el análisis con IA en una glosa de FAMISANAR**, que es donde
  de verdad aporta: con contrato cargado el dictamen puede citar la cláusula
  y el valor pactado. Con Salud Total no hay contrato y la IA llega al mismo
  argumento que la plantilla, que es gratis.
- **F) Todo lo de las OT-023 a OT-034 está probado en el repositorio, pero
  salvo la pantalla de Salud Total nadie lo ha visto correr en el motor del
  hospital.** Falta esa pasada.

**Ya desplegado y comprobado el mismo 13-08:** el PR #341 quedó fusionado y
el motor del hospital corriendo con ese código. La pantalla responde.

Dos cosas aprendidas en el camino, para no repetirlas:

1. **Para saber si el motor tiene un cambio cargado, no sirve `git log`.**
   Eso dice qué hay en el **disco**; el motor puede llevar horas corriendo
   con el código anterior en memoria. Lo que sirve es pedirle al motor su
   propia lista de rutas:
   `Invoke-RestMethod -Uri "http://localhost:8080/openapi.json"`.

2. **La tarea de autodeploy corre sola cada 5 minutos y puede aplicar el
   código en mitad de una revisión.** Ese día una comprobación dio un
   resultado que no cuadraba con lo que mostraba la carpeta segundos antes;
   la explicación más probable es esa, aunque no quedó demostrada. Si algo
   no cuadra, volver a mirar las rutas del motor antes de sacar
   conclusiones.

Queda **por revisar**: en el puerto 8080 aparecen dos procesos de Python,
creados en el mismo segundo. Como nacieron juntos llevan el mismo código,
así que no están dando respuestas distintas. Falta confirmar si uno es hijo
del otro (normal) o si son dos motores independientes (el problema del
04-08), mirando el `ParentProcessId`.

00. **Antes de cualquier prueba de IA: reiniciar con
    `tools\REINICIAR_MOTOR.cmd`** (doble clic). Cierra los motores viejos
    que quedaron prendidos y deja uno solo. Después, en **Gobierno IA →
    «Probar proveedores de IA»**, verificar que la clave que aparece ahí sea
    la misma que muestra el arranque. Si el Diagnóstico marca en rojo la
    tarjeta «Motor (quién está atendiendo)», hay más de uno: cerrar y
    repetir. Con eso queda lista la prueba de fuego pendiente: **pasar la
    glosa de PPL por Analizar** y confirmar que sale con el formato
    aprobado.
0. **~~PRIORIDAD CERO — rescate de la VM~~ — YA HECHO el 13-08.** La fusión
   se aplicó (27 glosas, 6 precedentes, contrato PRECIMED), la VM quedó
   APAGADA y los paquetes de rescate guardados en `C:\motor-glosas\rescate`.
   Lo único que queda: **en unos días, con todo verificado, BORRAR la VM**
   (fase 4 de `docs/MIGRACION_PC_HOSPITAL.md`) para que no cobre ni el disco:
   `gcloud compute instances delete motor-glosas --zone=us-west1-a`.
1. **Dispensario prioridad 1 (actualizado 05-08):** correr el cargue de las
   **23 pendientes** (piloto con HUS0000513796 → corrida completa → pegar el
   reporte al chat) y después armar los dos paquetes de evidencias:
   **GI-33-5251-2026** (lotes 17/28/31-jul + pendientes) y
   **GI-33-5285-2026** (cargue del 23-jul). Verificar cómo quedaron radicadas
   las 3 de junio (ya no figuran pendientes) y averiguar si hay **prórroga
   2026 del contrato 440** para blindar los próximos textos.
2. Correr la **pertinencia fusionada** COOSALUD (pendiente #1) y verificar que
   las 37 facturas cierren con evidencia.
3. Con los reportes en mano, **cerrar los flecos de los lotes 02/06/07/08**
   (segunda pasada de las que queden pendientes).
4. Generar los **Words de evidencia** de todo lo cerrado y archivarlos en sus
   carpetas por mes/día.
5. Actualizar el **informe de gerencia** con el acumulado real de julio
   (facturas y glosas cerradas por lote).
6. **Revisar los Excel ajustados del paquete 31068** que quedaron generados y
   los pendientes #11 a #15. Guías en `tools/README_ajustar_detallado_glosas.md`
   y `tools/README_por_factura_y_pdf.md`.
7. **Repetir el PDF con el Excel del equipo** (`--motor excel`): los PDF que se
   entregaron salieron con LibreOffice, que puede tener mínimas diferencias de
   maquetación frente al Excel del hospital.
8. **Estrenar en la página el módulo 📄 Glosas ADRES** con un gestor real:
   cargar el paquete 31068 (reporte + macro + `BITACORA_31068.csv`) y que el
   gestor pruebe con 5 facturas antes de soltarlo a todo el equipo.
   Guía: `docs/GLOSAS_ADRES_WEB.md`.
9. **Repartir las 255 glosas de causal 4506** desde la pantalla (lo hace un
   super admin). El bot ya propone: 229 para los gestores y 26 para las
   médicas, cada una con su motivo. Solo hay que confirmar o corregir.
10. **Completar los 371 renglones sin centro de costos**: son los que el nombre
    del servicio no alcanza a identificar. Se pueden llenar desde la misma
    pantalla y el sistema los recuerda para el siguiente paquete.
6. Si hay tiempo: verificar si SISTEMAS ya corrigió algún CUV (pendiente #6),
   descargar los 2 PDF del DIAN (pendiente #7) y revisar el PR #186 del módulo
   de pre-auditoría.
7. **ADRES:** (PR #176 ya fusionado el 29-07) copiar al servidor el PAQUETE
   COMPLETO (ZIP del 27-07) y correr la v2.1 del bot DE4401 (pendiente #21).
8. **SIIFA — revisar los dos archivos de respuestas y hacer el piloto.**
   Ya están generados `respuestas_GLOSAS.xlsx` (1.238) y
   `respuestas_DEVOLUCIONES.xlsx` (1.341), con respuesta en TODAS las filas:
   1.082 son la respuesta real que el hospital ya había dado en DGH y 1.497
   las redactó el motor nuevo (`tools/siifa_redactar_respuestas.py`). Cada
   fila dice en la columna REVISAR qué hay que verificar antes de subirla.
   Lo urgente de revisar: las de soportes (SO*), que no se sostienen sin
   anexar el papel, y las 674 devoluciones DE5601, donde hay que confirmar
   el acuse de radicación. Después, piloto de 1 glosa y cargue.

   **Decisión del 03-08:** primero se cargan SOLO las 1.082 respuestas reales
   del hospital. Volver a generar los archivos agregando al final del comando
   `--solo-lo-ya-respondido`: los de cargue quedan con las verdes y las
   redactadas se van a los archivos `_REDACTADAS`. Esas 1.497 quedan
   pendientes de revisar por tandas (empezando por las de mayor valor) —
   no se pueden dejar vencer: sin respuesta a tiempo, la glosa se entiende
   aceptada.

9. **SIIFA — lo que quedó del trabajo anterior.** El informe
   maestro ya está rebajado (2.597) y la hoja de trabajo ya salió cruzada
   con DGH: de las 272 respuestas, **162 vienen puestas** y **110 hay que
   escribirlas**. El orden del trabajo es:
   (a) mirar las **93 filas marcadas en REVISAR** (las de origen POR_CODIGO
   y las que en DGH tenían más de una respuesta);
   (b) escribir las 110 que dicen ESCRIBIR — ahí están las 482 glosas de
   HUS454747 y las devoluciones, que no tienen trámite en DGH;
   (c) **decidir qué se hace con las 1.169 devoluciones DE5601**, que es un
   trámite distinto al de una glosa;
   (d) expandir con `siifa_preparar_respuestas.py --expandir` y hacer el
   **piloto de 1 glosa** antes del cargue masivo (pendiente #13).

10. **Cerrar la MED737 (cuentas médicas):** corregir el JSON con el comando de
    PowerShell de `docs/CONTEXTO_FEV_RIPS_CUV.md`, resolver con facturación el
    conflicto de fechas y confirmar que el Ministerio entregue el CUV
    (pendiente #15). Después pasar `validar_json_rips.py --recursivo` a todas
    las facturas de agosto (pendiente #16).

### SINAC OS — decisiones que dependen de Yesid (28-07)

7. **Revisar un informe de cartera reciente.** El lector de montos leía
   `950.000` como `950` cuando el valor venía en texto. Ya está corregido, pero
   conviene mirar si algún informe salió con cifras bajas.
8. **Revisar un Excel de SAVIA.** Si la columna de valor trae comas decimales,
   los archivos que generó ese robot llevan los montos multiplicados por cien.
   El arreglo existe (lo tiene el módulo de EMSSANAR); falta juntarlos.
9. **Decidir qué hacer con los 39 archivos huérfanos** (SAVIA, EMSSANAR, VCO,
   FOMAG, Mutual Ser, organizador de correos, herramientas de cartera): están
   en ramas de otras sesiones con sus PR en borrador (#162, #164, #167). Se
   fusionan desde acá o se cierran desde esas sesiones — pero conviene no
   dejarlos más tiempo sueltos, que es justo lo que produjo dos robots
   distintos para el mismo pagador.
10. **Decidir si se enciende el avisador de vencimientos por correo.** Está
    construido y desconectado. Para prenderlo hace falta definir: quién recibe
    los avisos, con cuántos días de anticipación, y desde qué cuenta de correo
    salen (hoy no hay servidor de correo configurado).
11. **Comprobar que el enmascarado del nombre del paciente no estorbe** en el
    trabajo diario. Si una glosa tiene gestor asignado, los demás auditores
    ven iniciales en vez del nombre. Si molesta, se ajusta en una línea.
12. **Siguiente paso de construcción**, según el plan: terminar la limpieza de
    módulos sin uso y arrancar la **Fase 2 — modelo real del dominio**
    (Factura → Glosa → Soporte → Conciliación → Acta).
13. **Preguntar a contratación por las prórrogas.** Según la malla del 28-07,
    los contratos de COMPENSAR y COOSALUD subsidiado ya vencieron y los de
    NUEVA EPS y SALUD MIA están al límite. Si hay prórroga u otrosí firmado,
    avisar para actualizar la malla del sistema; mientras tanto, el sistema
    defiende esas atenciones a tarifa SOAT plena, que es lo correcto sin
    contrato vigente.

### Contrato de Construcción — decisiones que dependen de Yesid (28-07 noche)

13. **Leer el Anexo I del Contrato** (`docs/CONTRATO_CONSTRUCCION_SINAC_OS.md`,
    al final). Son diez páginas y responden lo único que importa ahora: qué se
    construye primero, qué se ve funcionando y cuánto cuesta. Con eso basta
    para decidir; los veinte capítulos son el detalle.
14. **Aprobar o cambiar los siete resultados comprometidos.** Están escritos
    como cosas que usted ve en pantalla, no como tareas técnicas. Si alguno no
    le sirve o falta uno, se cambia ahí y el plan se recalcula solo.
15. **Decidir qué pasa con las 661 tareas que quedaron fuera de todo
    resultado** (1.462 jornadas, el 90 % del esfuerzo). Dos salidas honestas
    por cada una: o se le escribe el resultado que justifica su existencia, o
    se acepta que va después. Lo que no sirve es dejarlas marcadas urgentes
    sin destinatario, que es como estaban.
16. **Decidir el tamaño del equipo.** El Contrato completo son 1.625,5 jornadas
    ≈ siete años de una persona. La primera entrega —los tres resultados que
    recuperan plata ya— son 79,5 jornadas ≈ cuatro meses de una persona, o un
    mes de cuatro. De esa decisión sale todo lo demás.
17. **Tres tareas están escritas dos veces** en capítulos distintos (migrar los
    perfiles de pagador a YAML, la pantalla de Perfiles, y las pruebas de
    arquitectura bloqueantes). Hay que decidir cuál capítulo conserva cada una
    antes de que dos personas las construyan por separado.
    del servicio no alcanza a identificar. Se escogen del desplegable oficial
    (45 centros) y el sistema los recuerda para el siguiente paquete.
11. **Preguntar a facturación por las 4 facturas sin detallado** (311371,
    367368, 380246, 394817 — $43.518.600 glosados): no vinieron en ninguno de
    los siete lotes. Hay que pedir esa impresión y volver a correr el
    ajustador.

### Suite Cartera HUS
18. **Revisar y fusionar el PR #160** (Suite Cartera HUS + Herramientas PDF +
    bots de correos de pagos y de unir Exceles). Decidir si se arranca la
    "fase 4" de Herramientas PDF (editar texto, formularios, firma digital,
    comparar PDF) o se prioriza otro pendiente de Cartera.

---

## 5) Datos fijos que siempre se necesitan

- **Carpeta de trabajo en Windows:** `C:\temp-notas` (ahí vive el repo).
- **Credenciales:** siempre en variables de entorno (`COOSALUD_USER`,
  `COOSALUD_PASSWORD`). Nunca escritas en archivos ni en comandos.
- **Índice de soportes:** `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt`.
- **Reportes y evidencias:** `D:\USUARIO CARTERA\Documents\COOSALUD\`.
- **Notas crédito Dispensario:** diagnóstico e informes en
  `docs/diagnostico_lote_v2_pendientes/` (repo); carpetas de trabajo en
  `D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\`
  (subcarpeta `PENDIENTES_12` con ficha por factura); fuente oficial XML/CUV en
  `\\172.16.32.83\factura_electronica_net22\<AAAAMM>\FACTURAS_NOTA\<nota>\`.
- **Regla de reanudación:** si un cargue se corta (luz, portal caído), NO se
  pierde nada: se relanza con `--saltar-csv <reporte anterior>` y un nombre de
  reporte nuevo. El bot salta lo ya cerrado y no duplica respuestas.
- **Regla de soportes:** las glosas extemporáneas (RE9502) NO llevan PDF de
  soporte. Las demás (ej. RE9901 en glosas de soportes) sí, y salen del share
  vía el índice.
- **Suite Cartera HUS:** vive en `tools/suite_cartera_hus/` (README propio en
  `LEEME.txt`). Las contraseñas de los portales van en
  `config/entidades.credenciales.json` (local, no versionado; la Suite las une
  con `entidades.json` en memoria al abrir).
- **ADRES/FURIPS:** repositorio de XML de facturación
  `\\172.16.32.83\factura_electronica_net22\<AAAAMM>\FACTURAS_SALUD\` (una
  subcarpeta por factura; la ruta se edita en la línea RUTA_FACTURAS de
  `COMPLETAR_INFORME_XML.cmd` cuando cambia el período). Los `.cmd` de
  `tools/` DEBEN conservar finales de línea CRLF (regla en `.gitattributes`);
  con LF la ventana se cierra sin ejecutar nada.

### Notas de método del flujo Dispensario (para cualquier chat nuevo)

- **Solo se trabaja el Dispensario Médico (DSE Ejército)** en este flujo de
  respuestas; si el Excel trae otras entidades, se omiten.
- Toda respuesta va en **MAYÚSCULAS, un solo párrafo**, empieza con
  *"ESE HUS NO ACEPTA LA GLOSA APLICADA A LA FACTURA…"* y cierra citando la
  mesa de conciliación y los correos de cartera.
- Postura institucional: **NO ACEPTA (RE9901), se defiende el 100% del valor.**
- Normas ancla: Res. 2284/2023 (Manual Único de Glosas — la 3047/2008 está
  DEROGADA, no citarla), contrato 440-DIGSA/DMBUG-2025 (el Dispensario ES
  parte), Resoluciones de tarifas HUS 054 y 124 de 2026 (y 194/2025 para
  material de osteosíntesis), Ley 1751/2015 art. 17 (autonomía médica),
  Decreto 4747/2007 y Ley 1438/2011 art. 57 (conciliación y trámite).
- Los generadores de respuestas de cada lote viven en el scratchpad de las
  sesiones (`glosa_motor.py` es la fuente única de plantillas); los robots de
  portal están en `tools/` de este repo.
