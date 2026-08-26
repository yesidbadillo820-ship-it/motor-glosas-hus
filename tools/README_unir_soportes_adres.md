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
| 4 | NOTAS CRÉDITO | `NOTAS CREDITO`, `NOTA DE CREDITO` | Las de los valores aceptados |

**Las NOTAS CRÉDITO quedan pendientes a propósito.** Todavía no las han sacado,
así que el bot **no las cuenta como falta**: avisa cuántas faltan y sigue. El
día que estén, se dejan en la carpeta de la factura, se vuelve a correr el bot
y entran solas de cuartas, sin rehacer nada.

**El DETALLADO ya no queda por fuera**: antes se dejaba en Excel aparte; ahora
es el renglón 2 de este folio, en PDF.

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
la carpeta (la epicrisis y la factura vienen así). Si en una carpeta ningún
archivo lo trae, el folio queda como `HUS######_EPICRIS.pdf` y el bot lo avisa;
con `--prefijo 680010079201` se le puede dar.

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

## 4) Los cinco candados

Armar folios no se deshace de un clic, así que:

1. **Simula por defecto.** Muestra los dos folios completos —con la factura y
   el detallado ya adentro, como van a quedar— y no escribe nada mientras no se
   le pase `--aplicar` (el botón lo pide escribiendo «SI»).
2. **Nunca se come su propio folio.** El `..._EPICRIS.pdf` y el
   `..._FACTURA.pdf` de una corrida anterior se excluyen de la entrada: se
   puede correr las veces que haga falta sin que el folio se anide dentro de sí
   mismo. Lo distingue porque, después de una corrida, todos los soportes
   quedaron numerados y con el nombre original ya no queda ninguno.
3. **No pisa la factura que ya estaba.** Si la carpeta ya tiene su factura, no
   la reemplaza con la del XML.
4. **Un PDF dañado no tumba el lote.** Se omite, se sigue con los demás y queda
   anotado en el reporte.
5. **Sin Excel ni LibreOffice no revienta.** Si no hay con qué pasar el
   detallado a PDF, lo deja anotado y sigue con lo demás.

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
- **`SIN PDF QUE UNIR`** — la carpeta está vacía.

---

## 6) Pruebas

`tests/test_tools/test_unir_soportes_adres.py` (104 pruebas). Cubren el orden
completo de los trece grupos del folio clínico y los cuatro del de la factura,
que gane la palabra más larga, que las abreviaturas no casen dentro de otras
palabras, que ningún archivo se pierda, que sin `--aplicar` no se escriba nada,
que la simulación muestre el folio como va a quedar de verdad, que la segunda
corrida deje exactamente lo mismo —incluso cuando a la factura le falta la
epicrisis, que fue el caso que se escapó en la prueba real—, que las notas
crédito queden pendientes sin contarse como falta y que entren de cuartas
cuando lleguen, que el NIT no se invente, y que ni un PDF dañado ni la falta de
Excel/LibreOffice tumben el lote.
