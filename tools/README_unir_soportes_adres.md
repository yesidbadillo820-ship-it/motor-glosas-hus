# Guía: `unir_soportes_adres.py` — los dos folios de cada factura del ADRES

Deja cada carpeta de factura con **sus dos folios**, numerados por dentro y con
el nombre con que se suben al ADRES:

```
📁 HUS352904
    1 RESPUESTA A GLOSA.pdf   (era RTA_ADRES_HUS352904.pdf)
    2 EPICRISIS.pdf           (era 680010079201_HUS352904_EPICRIS.pdf)
    3 HISTORIA CLINICA.pdf    (era HC.pdf)
    4 AYUDAS DIAGNOSTICAS.pdf (era DX.pdf)
    5 OTROS.pdf
    ───────────────────────►  680010079201_HUS352904_EPICRIS.pdf

    1 FACTURA.pdf             (era 680010079201_HUS352904_FACTURA.pdf)
    2 DETALLADO.pdf           (el detallado en Excel, pasado a PDF)
    3 REPRESENTACION GRAFICA DIAN.pdf
    4 NOTAS CREDITO.pdf       (PENDIENTE: todavía no las han sacado)
    ───────────────────────►  680010079201_HUS352904_FACTURA.pdf
```

**Numerar primero no es adorno**: es lo que deja libre el nombre del folio,
porque ese nombre es justo el que traían la epicrisis y la factura antes de
renombrarlas.

### El orden dentro del folio de la FACTURA

El `..._FACTURA.pdf` que viene con el XML **no es solo la factura**: trae varios
renglones pegados. `partes_de_la_factura()` mira página por página cuál es cuál:

```
HUS311736 -> {'FACTURA': (1, 7), 'DETALLADO': (8, 9), 'DIAN': (10, 18), 'NOTAS': (19, 19)}
HUS311371 -> {'FACTURA': (1, 4), 'DIAN': (5, 10)}
```

Cuando el detallado llega **aparte** (en Excel), no basta con ponerlo detrás:
quedaría de tercero, después de la representación gráfica. Por eso el bot
**parte** el PDF y mete cada pedazo en su puesto: factura, detallado,
representación gráfica, nota crédito.

Si el PDF ya trae los renglones en su orden y no hay nada que intercalar, **se
deja entero**: partirlo y volverlo a pegar no aporta y sí puede dañar algo.

### La carátula

**Solo el folio clínico la lleva.** El de la factura no, porque el área lo pidió
así. Cada folio clínico abre con una página de índice:

```
1.RESPUESTA A GLOSA ______________________________________  2
2.HISTORIA CLINICA _______________________________________ 70
3.AYUDAS DIAGNOSTICAS ___________________________________ 237
4.MEDICAMENTOS __________________________________________ 251
5.INSUMOS _______________________________________________ 269
```

Una línea por **renglón**, no por archivo: las dos historias clínicas son un
solo «2.HISTORIA CLINICA», y apunta a donde empieza la primera. El número es la
página exacta del folio ya armado (la 1 es la carátula misma). Un soporte que
no entró —un PDF dañado— **no figura**: si figurara, todas las páginas de abajo
quedarían corridas.

Con `--sin-caratula` no se pone. Si al equipo le falta `reportlab`, el folio se
arma igual sin índice y se avisa en el reporte.

Bot de doble clic para Windows: **`tools/UNIR_SOPORTES_ADRES.cmd`**.

---

## 1) El orden del folio clínico

| # | Grupo | Cómo lo reconoce en el nombre del archivo |
|---|---|---|
| 1 | RESPUESTA A GLOSA | `RESPUESTA A GLOSA`, `RTA GLOSA`, `RESPUESTA`, y `RTA ADRES` (así se llama el PDF que arma `respuestas_adres_por_factura.py`) |
| 2 | EPICRISIS | `EPICRISIS`, `EPICRIS`, `EPI` |
| 3 | HISTORIA CLÍNICA — consulta de urgencias | `CONSULTA DE URGENCIAS`, `URGENCIAS`, `TRIAGE` |
| 4 | HISTORIA CLÍNICA — terapias | `TERAPIAS`, `FISIOTERAPIA`, `RESPIRATORIA` |
| 5 | HISTORIA CLÍNICA — curaciones | `CURACIONES` |
| 6 | HISTORIA CLÍNICA — evoluciones | `EVOLUCIONES`, `INTERCONSULTA` |
| 7 | HISTORIA CLÍNICA — procedimientos | `PROCEDIMIENTOS`, `DESCRIPCION QUIRURGICA` |
| 8 | HISTORIA CLÍNICA (el resto) | `HISTORIA CLINICA`, `HC` |
| 9 | AYUDAS DIAGNÓSTICAS | `AYUDAS DIAGNOSTICAS`, `LABORATORIO`, `RADIOGRAFIA`, `TOMOGRAFIA`, `ECOGRAFIA`, `DX`, y los nombres con que salen los exámenes en el detallado: `GLUCOMETRIA`, `GASES ARTERIALES`, `LACTATO`, `HEMOGRAMA`… |
| 10 | MEDICAMENTOS | `MEDICAMENTOS`, `INGESTA`, `PLAN DE MANEJO`, `MED` |
| 11 | NOTAS DE ENFERMERÍA | `NOTAS DE ENFERMERIA`, `ENFERMERIA`, `NTE` |
| 12 | INSUMOS | `INSUMOS`, `GASTOS QUIROFANO`, `INS` |
| 13 | OTROS | `OTROS`, `SOAT`, `CERTIFICACION`, `REPS` — y todo lo que no reconoció |

Dentro de un mismo grupo los archivos van en **orden natural** de nombre
(`2` antes que `10`).

---

## 1bis) El orden del folio de la FACTURA

| # | Renglón | Cómo lo reconoce en el nombre del archivo | De dónde sale |
|---|---|---|---|
| 1 | FACTURA | `FACTURA`, `FACTURA DE VENTA` | De la carpeta `4.FACTURAS CON XML\XML`, como `680010079201_HUS######_FACTURA.pdf`. El bot la trae solo con `--carpeta-facturas` |
| 2 | DETALLADO | `DETALLADO`, `DETALLE DE FACTURA` | Del detallado en Excel. Con `--convertir-detallado` el bot lo pasa a PDF |
| 3 | REPRESENTACIÓN GRÁFICA DIAN | `REPRESENTACION GRAFICA`, `DIAN` | La que sale de la DIAN |
| 4 | NOTAS CRÉDITO | `NOTAS CREDITO`, `NOTA DE CREDITO`, `NOTA ELECTRONICA` y `NC` —así las nombra el hospital: `NC_263272_HUS352904.pdf` | Las de los valores aceptados |

**Las NOTAS CRÉDITO quedan pendientes a propósito.** Todavía no las han sacado,
así que el bot **no las cuenta como falta**: avisa cuántas faltan y sigue. El
día que estén, se dejan en la carpeta de la factura, se vuelve a correr el bot
y entran solas de cuartas, sin rehacer nada.

**El DETALLADO ya no queda por fuera**: antes se dejaba en Excel aparte; ahora
es el renglón 2 de este folio, en PDF.

### Ojo: la factura del XML a veces YA es el folio completo

En el paquete 31068, el `680010079201_HUS311736_FACTURA.pdf` que viene con el
XML **no es solo la factura**. Son 19 páginas con los cuatro renglones ya
pegados:

| Páginas | Qué es | Renglón |
|---|---|---|
| 1–7 | FACTURA ELECTRÓNICA DE VENTA, con su CUFE | 1. FACTURA |
| 8–9 | DETALLADO FACTURA ELECTRONICA | 2. DETALLADO |
| 10–18 | «Representación Gráfica» + Código Único de Factura (CUFE), Datos Totales | 3. REPRESENTACIÓN GRÁFICA DIAN |
| 19 | NOTA CRÉDITO, con el trámite de objeción que la originó | 4. NOTAS CRÉDITO |

Por eso el bot **mira dentro** del PDF de la factura antes de agregarle nada
(`renglones_que_trae()`): si el renglón ya viene pegado, no le pone otro encima
—el folio subiría al ADRES con el detallado dos veces— y tampoco lo cuenta como
faltante. Lo dice en pantalla y en el reporte.

Esto se comprobó sobre **una sola factura** (la HUS311736). Si en otras el
`..._FACTURA.pdf` viene solo con la factura, el bot lo detecta igual y arma el
folio con las partes: no hace falta configurar nada.

---

## 2) Cómo decide de qué es cada PDF

Por el **nombre del archivo**. Dos reglas que evitan los errores típicos:

- **Gana la palabra más larga**, no la primera que aparezca. Así
  «NOTAS DE ENFERMERÍA» no se lo lleva `NOTAS`, y «CONSULTA DE URGENCIAS» no se
  confunde con una consulta cualquiera.
- **Las abreviaturas van sueltas.** `INS` no puede casar dentro de
  `INSTITUCIONAL`, ni `HC` dentro de `HCG12`. Esto importa porque el equipo
  nombra los archivos **con la abreviatura sola**: `EPI.pdf`, `HC.pdf`,
  `DX.pdf`, `MED.pdf`, `NTE.pdf`, `INS.pdf`, `OTROS.pdf`.
- **`OTROS` es un grupo con nombre propio, no solo el cajón.** Un `OTROS.pdf`
  está bien clasificado y **no** sale en la lista de «revisar»; un
  `papel suelto.pdf` sí.

**Lo que no reconoce no se pierde**: va al grupo OTROS y sale listado aparte en
el reporte, para que el auditor lo mire.

Si el equipo usa una palabra que el bot no conoce, se agrega sin tocar el
código con `--mapa-nombres`:

```json
{ "ANGIOTAC": "AYUDAS", "SOAT": "OTROS", "GASTOS DE CIRUGIA": "INSUMOS" }
```

---

## 2bis) Tres formas de dejar la carpeta

**a) Los dos folios (`--folio`)** — es lo que pidió el área y lo que hace el
botón: numera los soportes y los une en `<NIT>_<FACTURA>_EPICRIS.pdf` y
`<NIT>_<FACTURA>_FACTURA.pdf`.

**b) Solo numerar (`--renombrar`)** — deja los soportes como
`1 RESPUESTA A GLOSA.pdf`, `2 EPICRISIS.pdf`… y no une nada. El número dice en
qué orden van y el nombre dice de qué es cada uno, sin tener que abrirlos. Si
hay dos del mismo grupo, siguen la numeración (`3 HISTORIA CLINICA.pdf`,
`4 HISTORIA CLINICA.pdf`).

**c) El consolidado viejo (por defecto)** — deja `<FACTURA>_SOPORTES.pdf` con
todo adentro, en el mismo orden, y no toca los originales.

Las tres se pueden correr las veces que haga falta: la segunda corrida deja lo
mismo.

### El NIT del nombre

El `680010079201` **no se inventa**: sale del nombre de los propios archivos de
la carpeta (la epicrisis y la factura vienen así, `<NIT>_<FACTURA>_<TIPO>.pdf`).
Si en una carpeta ningún archivo lo trae, el folio queda como
`HUS######_EPICRIS.pdf` y el bot lo avisa; con `--prefijo 680010079201` se le
puede dar.

**Ojo con el flujo de dos pasos.** Si primero corre `--renombrar` y después
`--folio`, al numerar desaparece el nombre que traía el NIT y ya no hay de dónde
sacarlo. El bot lo avisa al terminar el renombrado, con el NIT que encontró:
guárdelo y páselo con `--prefijo`. Corriendo `--folio` de una sola vez no hace
falta.

---

## 3) Uso

```
REM 1) PRIMERO en simulación: muestra los dos folios y no toca nada.
py tools\unir_soportes_adres.py --folio ^
    --carpeta "Z:\...\TECNICOS\CAROLINA" ^
    --carpeta-facturas "Z:\...\4.FACTURAS CON XML\XML" ^
    --convertir-detallado ^
    --reporte-csv "Z:\...\TECNICOS\CAROLINA\FOLIOS_ADRES.csv"

REM 2) Si el listado se ve bien, con --aplicar sí los arma.
py tools\unir_soportes_adres.py --folio ^
    --carpeta "Z:\...\TECNICOS\CAROLINA" ^
    --carpeta-facturas "Z:\...\4.FACTURAS CON XML\XML" ^
    --convertir-detallado --aplicar ^
    --reporte-csv "Z:\...\TECNICOS\CAROLINA\FOLIOS_ADRES.csv"
```

| Opción | Para qué |
|---|---|
| `--carpeta` | La carpeta del gestor (CAROLINA, CLAUDIA, OSCAR…) |
| `--folio` | El trabajo completo: numerar y armar los DOS folios |
| `--carpeta-facturas` | Carpeta `4.FACTURAS CON XML\XML`, de donde se trae el PDF de cada factura |
| `--convertir-detallado` | Pasar a PDF el detallado que esté en Excel |
| `--prefijo` | NIT para nombrar los folios, si los archivos no lo traen |
| `--facturas archivo.xlsx` | Solo las facturas de esa lista. Sin esto, todas las carpetas |
| `--renombrar` | Solo numerar los soportes, sin unir nada |
| `--aplicar` | Hacerlo de verdad (sin esto solo simula) |
| `--reporte-csv` | Listado de qué archivo quedó en qué renglón y de qué folio |
| `--mapa-nombres` | JSON para agregar palabras propias |

El resultado queda en la carpeta de cada factura como
`<NIT>_<FACTURA>_EPICRIS.pdf` y `<NIT>_<FACTURA>_FACTURA.pdf`.

---

## 4) Los ocho candados

Armar folios no se deshace de un clic, así que:

1. **Simula por defecto.** Muestra los dos folios completos —con la factura y
   el detallado ya adentro, como van a quedar— y no escribe nada mientras no se
   le pase `--aplicar` (el botón lo pide escribiendo «SI»).
2. **Nunca se come su propio folio.** El `..._EPICRIS.pdf` y el
   `..._FACTURA.pdf` de una corrida anterior se excluyen de la entrada: se
   puede correr las veces que haga falta sin que el folio se anide dentro de sí
   mismo. Lo distingue porque, después de una corrida, todos los soportes
   quedaron numerados y con el nombre original ya no queda ninguno.
3. **Nunca pisa un archivo que no escribió él.** El folio se llama igual que el
   archivo del que sale, así que el bot **firma por dentro** los PDF que
   escribe (`/Producer`) y en la corrida siguiente reconoce los suyos por esa
   firma, no por el nombre. Lo que no lleva la firma es un soporte de verdad.
   Si en la ruta del folio hay algo sin firmar, no arma ese folio y avisa:
   perder un soporte no se deshace, no armar un folio sí.
4. **No pisa la factura que ya estaba.** Si la carpeta ya tiene su factura, no
   la reemplaza con la del XML.
5. **Un PDF dañado no tumba el lote.** Se omite, se sigue con los demás, y sale
   avisado en pantalla («NO entraron al folio») además del reporte: un folio al
   que le falta una hoja no se sube sin que el auditor lo sepa.
6. **Sin Excel ni LibreOffice no revienta.** Si no hay con qué pasar el
   detallado a PDF, lo deja anotado y sigue con lo demás.
7. **Una corrida que se cae no deja destrozos.** El renombrado va en dos
   vueltas (primero a un nombre de paso `~renombrando~…`, porque el nombre que
   le toca a un archivo puede ser el que todavía tiene otro). Si algo falla a
   mitad, **se deshace**: cada archivo vuelve al nombre que tenía. Y si de una
   corrida anterior quedó algo colgado, la siguiente **le devuelve su nombre**
   antes de empezar — un `~renombrando~HC.pdf` es la historia clínica del
   paciente, no basura.
8. **El reporte abierto en Excel no tumba la corrida.** En Windows el CSV no se
   deja escribir si está abierto; el trabajo ya está hecho y no se pierde por
   no poder dejar el listado.

---

## 5) Qué mirar antes de dar por buena la corrida

En el reporte CSV:

- **`RECONOCIDO = NO - revisar`** — el bot no supo de qué era y lo mandó a
  OTROS. Si es un grupo que sí existe, renombre el archivo o agregue la palabra
  con `--mapa-nombres` y vuelva a correr.
- **`FALTA este soporte`** — al folio le falta un renglón que hoy debería
  estar: RESPUESTA A GLOSA o EPICRISIS en el clínico; FACTURA, DETALLADO o
  REPRESENTACIÓN GRÁFICA DIAN en el de la factura.
- **`PENDIENTE: las notas crédito…`** — normal, todavía no existen. No hay que
  hacer nada hasta que salgan.
- **`está en Excel: hay que pasarlo a PDF`** — el detallado no entró al folio.
  Corra otra vez con `--convertir-detallado`.
- **`REVISAR: se tomó como el folio de la corrida anterior`** — hay un
  `..._EPICRIS.pdf` (o `..._FACTURA.pdf`) en una carpeta ya armada, pero sin su
  archivo numerado al lado. El bot no adivina: lo trata como el folio viejo. Si
  en realidad es un soporte nuevo, renómbrelo con su número y vuelva a correr.
- **`no es un PDF: no entra al folio`** — una epicrisis en Word, una radiografía
  en JPG. Páselas a PDF y vuelva a correr.
- **`quedó a medio renombrar por una corrida caída`** — con `--aplicar` el bot
  le devuelve su nombre solo.
- **`NO se armó el folio: … no lo escribió este bot`** — en la ruta del folio
  hay un archivo que podría ser un soporte de verdad. No se pisó nada. Si es un
  soporte, renómbrelo con su número; si es un folio viejo, bórrelo.
- **`SIN PDF QUE UNIR`** — la carpeta está vacía.

---

## 6) Pruebas

`tests/test_tools/test_unir_soportes_adres.py` (149 pruebas). Cubren el orden
completo de los trece grupos del folio clínico y los cuatro del de la factura,
que gane la palabra más larga, que las abreviaturas no casen dentro de otras
palabras, que ningún archivo se pierda, que sin `--aplicar` no se escriba nada,
que la simulación muestre el folio como va a quedar de verdad, y que la segunda
corrida deje exactamente lo mismo.

Las regresiones que dejó la revisión a fondo del 26-08 —cada una falla sin su
arreglo y pasa con él—:

| Prueba | Lo que evita |
|---|---|
| `test_una_epicrisis_sin_firma_es_un_soporte_no_un_folio` | Que el bot borre la epicrisis y suba el folio sin ella |
| `test_un_huerfano_a_medio_renombrar_no_se_pierde` | Que un archivo de una corrida caída se pierda en la siguiente |
| `test_si_el_renombrado_revienta_a_mitad_se_deshace` | Que queden archivos `~renombrando~…` para siempre |
| `test_el_orden_del_folio_no_cambia_entre_corridas` | Que las páginas del folio salgan en otro orden |
| `test_una_fecha_no_puede_pasar_por_NIT` | Que el folio salga con el nombre equivocado |
| `test_las_notas_credito_con_el_nombre_del_hospital` | Que la nota crédito acabe en el folio clínico |
| `test_avisa_el_soporte_que_no_entro_al_folio` | Que un soporte dañado se caiga en silencio |
| `test_una_factura_bloqueada_no_tumba_las_demas` | Que un PDF abierto en Acrobat deje sin folio a las otras 323 |
| `test_el_reporte_abierto_en_excel_no_tumba_la_corrida` | Perder el trabajo ya hecho por no poder escribir el CSV |