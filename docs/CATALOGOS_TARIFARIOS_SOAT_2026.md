# Las dos tablas del SOAT 2026 — qué son y cómo comprobar que están bien

Cualquier defensa de tarifa del hospital se apoya en dos tablas. Este
documento explica qué tiene cada una, cómo comprobar que el servidor las
tiene bien instaladas, y qué **no** está cargado (para no dar por hecho lo
que no es).

---

## 1. El homologador CUPS → SOAT

**Archivo:** `app/data/cups_soat_homologacion.json.gz`
**Fuente:** Excel «Gold Standard 2026» de homologación CUPS (Res. 2775) →
Manual Tarifario SOAT, cargado en agosto de 2026.
**Se regenera con:** `python tools/generar_cups_soat_json.py RUTA_DEL_EXCEL.xlsx`

Es el puente entre el código que factura el hospital (CUPS) y el código del
Manual Tarifario SOAT que usa la EPS para objetar.

| Dato | Cantidad |
|---|---|
| Códigos CUPS | 10.024 |
| Con el **artículo** del Manual SOAT | 8.783 |
| Marcados **sin homologación directa** | 2.966 |
| Códigos SOAT distintos | 2.918 |

**El defecto que destapó esta carga.** Para esos 2.966 CUPS el Excel escribe
la frase «NO TIENE HOMOLOGACION DIRECTA». El motor la leía **como si fuera un
código SOAT** y le decía a la IA, textualmente:

> El CUPS 013205 corresponde oficialmente a los siguientes código(s) SOAT del
> Manual Tarifario: • SOAT **NO TIENE HOMOLOGACION DIRECTA**. USA ESTE DATO
> OFICIAL para fundamentar la tarifa.

Un código inventado, metido como base de la defensa tarifaria, en 2.966 casos.
Hoy el motor dice lo cierto, que además favorece al hospital:

> El CUPS 013205 **NO tiene homologación directa** en el Manual Tarifario
> SOAT… luego la entidad **NO puede objetar la tarifa citando un código
> SOAT** para este procedimiento. PROHIBIDO afirmar que corresponde a algún
> código SOAT.

---

## 2. El Manual SOAT 2026 (tarifas en UVB)

**Archivo:** `app/data/soat_uvb_2026.json.gz`
**Fuente:** MinSalud, **Circular Externa 047 del 30 de diciembre de 2025** —
«Indexación de tarifas del Manual de Régimen Tarifario expresadas en UVB que
regirán a partir de la vigencia 2026». 49 páginas.
**Se regenera con:** `python tools/generar_soat_uvb_2026_json.py RUTA_DEL_PDF.pdf`

| Dato | Cantidad |
|---|---|
| Códigos con tarifa oficial | **1.507** |
| Valor de la UVB 2026 | **$12.110** |

**Antes el sistema conocía cuatro.** Cuatro tarifas SOAT transcritas a mano
como «ejemplos representativos». Para las otras 1.503 el liquidador contestaba
«sin tarifa local — consulte el Manual SOAT 2026 oficial», que es justo lo que
uno necesita cuando la EPS objeta la tarifa. Esto pesa sobre todo en los
contratos pactados **contra el SOAT**: FAMISANAR («SOAT UVB vigente −5%») y
Policía Nacional («UVB −8%»).

**Cómo se saca el valor en pesos:** tarifa en UVB × $12.110, ajustado a la
**centena más próxima** (numeral 87 del Anexo técnico 1 del Decreto 780/2016).
Ejemplo: reemplazo protésico total primario de cadera (513014) = 1.223,71 UVB
× $12.110 = $14.819.128 → **$14.819.100**. Con el −5% de FAMISANAR:
**$14.078.200**.

### Por qué se puede confiar en lo que se leyó del PDF

La Circular es un **escaneo**: el computador tuvo que reconocer las cifras.
Por eso se comprobó de tres maneras y las tres dieron lo mismo:

1. **Dos lecturas independientes del mismo PDF** (una leyendo el texto
   corrido, otra leyendo por columnas): **cero diferencias** en las 1.498
   tarifas que ambas encontraron.
2. **Contra los cuatro códigos que un humano había transcrito** antes a mano:
   coinciden exactamente los cuatro.
3. **Contra el Excel Gold Standard**, que trae su propia columna de UVB:
   coinciden 1.048 de 1.250 códigos comunes, y las 202 restantes difieren en
   **una centésima de UVB** (≈$121) y **ninguna** en más. Es diferencia de
   redondeo entre quien armó el Excel y el Ministerio, no error de lectura.
   Manda la Circular, que es la norma.

Una advertencia honesta: en un puñado de renglones la **descripción** quedó
con un pedazo de la nota al pie pegado (por ejemplo el código 38274). La
**tarifa** de esos renglones está bien; solo el texto quedó con ruido.

---

## 3. Cómo comprobarlo usted mismo

En el servidor de cartera, **doble clic** en:

    tools\VERIFICAR_CATALOGOS_SOAT.cmd

Abre una pantalla, revisa las dos tablas y termina diciendo **VERIFICADO** o
**FALLA**. No cambia nada: solo mira. Si dice FALLA, indica qué falta y qué
hacer.

Comprueba, entre otras cosas:

- que el homologador instalado sea la versión `2026-GOLD-STANDARD`;
- que **ningún** CUPS haya vuelto a guardar una frase como si fuera código
  SOAT;
- que el Manual SOAT traiga más de 1.500 códigos;
- cinco tarifas escogidas a mano contra el PDF de la Circular.

También queda cubierto por las pruebas automáticas:
`tests/test_services/test_soat_uvb_2026_circular047.py` y
`tests/test_services/test_homologador_cups_soat_2026.py`.

---

## 4. Lo que NO está cargado

- **«Proyecto Manual SOAT — Tabla de servicios».** Es un **proyecto**, no una
  norma vigente, y sus valores están en **puntos de SMLVD**, la unidad que la
  Ley 2294 de 2023 reemplazó por la UVB. Cargarlo produciría cifras que no
  corresponden a lo que hoy se puede cobrar. Queda como documento de consulta,
  no como tarifa del sistema.
- **`Trazabilidad años anteriores.xlsx`** (13 hojas con las resoluciones de
  años previos). Serviría para responder glosas de **facturas viejas**, donde
  aplica la tarifa vigente el día de la atención y no la de 2026. Pendiente.
