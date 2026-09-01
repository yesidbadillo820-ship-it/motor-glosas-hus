# Guía: `organizar_objeciones_adres.py` — Glosas del ADRES → formato OBJECIONES de DGH

Pasa el Excel de glosas del ADRES (el **«ADRES DANIEL»**, el que arma el auditor
con la clasificación y el valor aceptado de cada renglón) al **mismo formato
OBJECIONES de 16 columnas** que se viene cargando en Dinámica Gerencial (DGH)
para COOSALUD.

Bot de doble clic para Windows: **`tools/OBJECIONES_ADRES.cmd`**.

---

## 1) Por qué existe

El ADRES y DGH le ponen **nombres distintos al mismo servicio**:

| Lo que dice el ADRES | Lo que tiene DGH |
|---|---|
| `29117` — Terapia respiratoria (código **SOAT**) | `939403` — TERAPIA RESPIRATORIA INTEGRAL |
| `38134` — Habitación de cuatro ó mas camas | `10A004` — INTERNACION COMPLEJIDAD ALTA CUATRO O MAS CAMAS |
| `2016DM-0000315-R2` — venda de gasa (registro **INVIMA**) | `FMQ0041` — VENDA DE GASA 6 X 5 YARDAS |

Mientras no estén homologados, el archivo no se puede cargar: la columna
`SLNSERPRO` (el código del servicio en DGH) es la que amarra cada objeción con
el renglón que se facturó.

---

## 2) Qué archivos necesita

| Parámetro | Archivo | Para qué |
|---|---|---|
| `--adres` | Excel de glosas del ADRES | Es la fuente: una fila por glosa |
| `--dgh` | `DGReport_*.xlsx` (hoja `DGDATATABLE`) | Trae los servicios que DGH tiene facturados en cada factura |
| `--homologador` | `01._Homologador_Gold_Standard_CUPS_a_SOAT_*.xlsx` | Traduce el código SOAT del ADRES a CUPS |
| `--reporte-reclamaciones` | `ReporteReclamPAQUETE_*.xlsx` | La cifra oficial: cuánto glosó el ADRES en cada factura |
| `--salida` | Carpeta destino | Ahí quedan los lotes y el archivo de control |

El bot **busca solo** la hoja de glosas dentro del Excel del ADRES: es la que
trae a la vez `Cod Elemento`, `CODIGO NUMERICO`, `Valor Glosado` y
`VALOR ACEPTADO`. Las descripciones limpias de cada servicio las saca de la hoja
del reporte crudo (`Descripción Elemento`). Si hiciera falta, se pueden indicar a
mano con `--hoja-glosas` y `--hoja-reporte`.

> **Ojo con la tabla dinámica.** El libro del ADRES suele traer además una hoja
> resumen («Hoja3») con las mismas columnas pero los valores sumados («Suma de
> Valor Glosado»). El bot la descarta: si se quedara con ella, todas las
> objeciones saldrían en cero.

---

## 3) Cómo homologa el código del servicio

Siempre **dentro de la misma factura**, y en este orden. En cuanto uno acierta,
se para:

1. **Código directo** — el código del ADRES ya existe en DGH (igualando los ceros
   de relleno: `19935303-4` y `19935303-04` son el mismo medicamento).
2. **SOAT → CUPS** — con el Homologador Gold Standard.
3. **Descripción igual.**
4. **Descripción que empieza igual** — el ADRES recorta los nombres largos.
5. **Valor exacto + palabras en común** — el valor del renglón coincide al peso
   con un servicio de DGH y comparten al menos la mitad de las palabras. Así se
   resuelve «Habitación de cuatro ó mas camas» ↔ «Internación complejidad alta
   cuatro o mas camas». Si hay **dos** servicios distintos que cumplen, no se
   elige ninguno.
6. **Descripción muy parecida** (85 % o más) — para las tildes rotas y las
   abreviaturas.

**Lo que no se pueda homologar no se inventa.** El renglón igual sale en el
archivo, con `SLNSERPRO` vacío, y además queda listado en la hoja `REVISAR` con
el candidato más parecido, para que el auditor decida.

En el paquete 31068 esto resolvió **2.763 de 3.262 renglones con servicio
(84,7 %)**. Los 499 que quedaron son, casi todos, los códigos SOAT que
descomponen una cirugía (honorarios de cirujano, ayudantía, derechos de sala,
materiales): DGH factura la cirugía en **un solo renglón**, así que no hay un
servicio al cual amarrarlos uno por uno.

---

## 3bis) El cuadre contra el reporte del ADRES (`--reporte-reclamaciones`)

**El detalle del ADRES cuenta la misma plata más de una vez.** Sumado tal cual,
el paquete 31068 daba **$1.032.239.679**, cuando el ADRES reporta **$646.908.552**
glosados. Cargar eso a DGH sería objetar hasta tres veces el mismo dinero.

Son dos formas de repetición:

1. **Renglones que repiten el total de la reclamación.** Cuando el ADRES glosa la
   reclamación entera por el FURIPS, además de listar los servicios mete **una
   fila por cada causal de reclamación** (2102, 2103…) con el valor **completo**.
   La factura `HUS0000311371` aparece por $39.722.100 cuando el ADRES reporta
   $13.240.700: el detalle ($13.240.700) más dos renglones de causal, cada uno
   por el total.
2. **Renglones repetidos:** el mismo servicio, misma cantidad y mismo valor,
   listado otra vez porque le cayó otra causal encima.

Con `--reporte-reclamaciones` el bot deja **cada factura sumando exactamente el
Valor Glosado que reporta el ADRES**, en este orden:

1. Quita los renglones que repiten el total de la reclamación.
2. Quita las repeticiones, **la más grande primero** y **sin bajarse nunca del
   valor reportado** (quitar de más sería objetar menos de lo que el ADRES glosó).
3. Si aún queda diferencia, la carga al renglón **mayor** —el que menos se
   deforma en proporción— y sigue con el siguiente si no cabe. Ningún valor
   queda negativo.

El cuadre se hace **de último**, sobre los valores ya definitivos, porque el
guardián de valores de DGH pudo recortar algún renglón antes.

**Todo lo que se quita y todo lo que se ajusta queda en la hoja `REVISAR`**, con
el antes y el después. En el paquete 31068: 169 renglones quitados y 65 facturas
ajustadas, y las **324 de 324 facturas** quedaron cuadradas.

---

## 3ter) Que ningún renglón quede sin código de servicio (`--completar-servicios`)

Por defecto, lo que no se pudo homologar sale con la casilla vacía. Con
`--completar-servicios` **ningún renglón queda sin código**:

1. Si el cruce encontró un candidato parecido pero no lo suficiente para darlo
   por bueno, se usa ese.
2. Si no hay ninguno, se usa el **servicio de más peso de la factura** en DGH
   (el que más plata suma).

Esto **no es una homologación**: es un destino por defecto para que el archivo
cargue. Por eso **cada uno de esos renglones queda listado en `REVISAR`** con el
motivo `CODIGO DE SERVICIO ASIGNADO (no salio del cruce)` y con de dónde salió el
código. En el paquete 31068 fueron 1.768 renglones ($307.480.311): revíselos
antes de cargar.

---

## 4) Reglas del formato de salida

| Columna | De dónde sale |
|---|---|
| `CDCONSEC` | Consecutivo **por factura** (1 la 1ª, 2 la 2ª…), como **texto** |
| `CDFECDOC` / `CROFECOBJ` | `--fecha` (por defecto, hoy) |
| `CRNCXC` | Número de factura en formato largo: `HUS311371` → `HUS0000311371` |
| `CROCLAOBJ` | `0` (constante de la guía) |
| `GENUSUARIO4` | `999` (constante de la guía), como **texto** |
| `CRNCONOBJ` | Código de glosa del ADRES, o el que diga `--mapa-codigos` |
| `SLNSERPRO` | El código de DGH que salga de la homologación |
| `CROVALOBJ` | Valor glosado, con el guardián de valores aplicado |
| `CRDOBSERV` | `<código> <causal> (<cód. servicio>-<servicio>)$<valor>` |
| `CROTIPOBJ` | Por factura: solo administrativas `0`, solo pertinencia `1`, mezcla `2` |
| `CROREFERE`, `CROOBSERV`, `CRNCLAOBJ`, `IDRIPS`, `CTNCENCOS` | Vacíos |

**Guardián de valores** (la misma guarda del cruce de DGH de la Suite Cartera):
la objeción nunca supera el valor del servicio en DGH ni el saldo de la factura.
Si se pasa, se ajusta al tope y queda anotado en `REVISAR` con el antes y el
después.

**Lotes de 300 facturas.** DGH no recibe más por archivo, así que la salida sale
partida en `OBJECIONES_ADRES_LOTE_01.xlsx`, `_02.xlsx`… Una factura nunca queda
partida entre dos lotes.

---

## 5) El código de glosa (`CRNCONOBJ`) — esto hay que revisarlo a mano

El ADRES usa códigos numéricos de cuatro dígitos (`3106`, `3209`, `4506`…) y DGH
usa los de seis del Manual Único (`SO3401`, `CL0101`…). **No existe una tabla
oficial que los equipare**, así que el bot escribe el código del ADRES tal cual
y le deja la traducción al auditor:

- La hoja **`CODIGOS`** del archivo `REVISAR_*` trae la lista de códigos del
  ADRES con cuántos renglones y cuánta plata mueve cada uno, la clasificación que
  escribió el auditor y el **grupo del Manual Único** que le corresponde
  (`CL`, `SO`, `TA`, `FA`…) como punto de partida.
- Una vez definida la equivalencia, se pasa en un JSON:

```json
{ "3106": "SO3401", "3209": "CL0801", "4506": "FA0602" }
```

```
--mapa-codigos "codigos_adres_dgh.json"
```

---

## 6) Uso

```
py tools\organizar_objeciones_adres.py ^
    --adres                  "ADRES_DANIEL_31068.xlsx" ^
    --dgh                    "DGReport_1.xlsx" ^
    --homologador            "01._Homologador_Gold_Standard_CUPS_a_SOAT__Ano_2026.xlsx" ^
    --reporte-reclamaciones  "ReporteReclamPAQUETE_31068.xlsx" ^
    --completar-servicios ^
    --salida                 "OBJECIONES_ADRES" ^
    --paquete                "31068"
```

Opciones útiles:

| Opción | Para qué |
|---|---|
| `--paquete 31068` | Deja solo las glosas de ese paquete |
| `--reporte-reclamaciones archivo.xlsx` | Cuadra cada factura contra el glosado que reporta el ADRES |
| `--completar-servicios` | Que ningún renglón quede sin código de servicio |
| `--fecha 2026-08-21` | Fecha de la objeción (por defecto, hoy) |
| `--mapa-codigos archivo.json` | Traduce el código del ADRES al de DGH |
| `--excluir-glosa-total` | Deja fuera los renglones sin código de glosa |
| `--max-facturas 300` | Facturas por archivo (el tope de DGH) |
| `--prefijo` | Cambia el nombre de los archivos de salida |

---

## 7) Qué mirar antes de cargar

El archivo `REVISAR_OBJECIONES_ADRES.xlsx` trae tres hojas:

- **`RESUMEN`** — cuántas glosas se leyeron, cuántas objeciones se escribieron,
  por qué camino se homologó cada renglón y cuánto recortó el guardián.
- **`REVISAR`** — un renglón por cada cosa que necesita ojo humano:

  | Motivo | Qué significa |
  |---|---|
  | `SIN CODIGO DE SERVICIO EN DGH` | No se pudo homologar; va el candidato más parecido |
  | `GLOSA DE TODA LA RECLAMACION (sin servicio)` | El ADRES glosó la reclamación entera; no señala un servicio |
  | `SIN CODIGO DE GLOSA (glosa total por FURIPS)` | El renglón no trae causal propia |
  | `VALOR AJUSTADO AL TOPE DE DGH` | La objeción se recortó; va el antes y el después |
  | `GLOSA ACEPTADA COMPLETA` | Se aceptó todo el valor: quizá no haya que objetarla |
  | `LA FACTURA NO ESTA EN EL REPORTE DE DGH` | Falta esa factura en el DGReport |
  | `CODIGO DE SERVICIO ASIGNADO` | El código no salió del cruce; va de dónde se sacó |
  | `RENGLON QUITADO: repetia el glosado de toda la reclamacion` | El ADRES lo contaba dos veces |
  | `RENGLON QUITADO: duplicado del ADRES` | El mismo servicio listado otra vez |
  | `VALOR AJUSTADO PARA CUADRAR CON EL REPORTE DEL ADRES` | Va el antes y el después |
  | `LA FACTURA NO ESTA EN EL REPORTE DE RECLAMACIONES` | No se pudo cuadrar |

- **`CODIGOS`** — la tabla para armar el `--mapa-codigos`.

Y siempre, antes del cargue masivo: **piloto de UNA factura**.

---

## 8) Pruebas

`tests/test_tools/test_organizar_objeciones_adres.py` (65 pruebas). Cubren que no
se pierda ningún renglón, que el código de DGH salga del cruce y no de una
suposición, que no se elija un candidato cuando hay dos igual de posibles, que el
guardián recorte al tope, que los lotes no partan una factura y que el bot no se
quede con la tabla dinámica en vez de la hoja de glosas.

Del cuadre: que se quite el renglón que repite el total de la reclamación, que
las repeticiones se quiten de mayor a menor, que **nunca se baje del valor
reportado**, que el cuadre mande sobre el tope de DGH, que el ajuste se reparta
si no cabe en un solo renglón y que ningún valor quede negativo.
