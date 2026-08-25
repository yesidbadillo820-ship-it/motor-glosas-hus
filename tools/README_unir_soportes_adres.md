# Guía: `unir_soportes_adres.py` — un solo PDF de soportes por factura, en orden

Une los soportes sueltos de cada carpeta de factura en **un solo PDF**, puestos
en el **orden exacto** que pide el área de Cuentas Médicas.

Bot de doble clic para Windows: **`tools/UNIR_SOPORTES_ADRES.cmd`**.

---

## 1) El orden

| # | Grupo | Cómo lo reconoce en el nombre del archivo |
|---|---|---|
| 1 | RESPUESTA A GLOSA | `RESPUESTA A GLOSA`, `RTA GLOSA`, `RESPUESTA` |
| 2 | EPICRISIS | `EPICRISIS`, `EPICRIS`, `EPI` |
| 3 | HISTORIA CLÍNICA — consulta de urgencias | `CONSULTA DE URGENCIAS`, `URGENCIAS`, `TRIAGE` |
| 4 | HISTORIA CLÍNICA — terapias | `TERAPIAS`, `FISIOTERAPIA`, `RESPIRATORIA` |
| 5 | HISTORIA CLÍNICA — curaciones | `CURACIONES` |
| 6 | HISTORIA CLÍNICA — evoluciones | `EVOLUCIONES`, `INTERCONSULTA` |
| 7 | HISTORIA CLÍNICA — procedimientos | `PROCEDIMIENTOS`, `DESCRIPCION QUIRURGICA` |
| 8 | HISTORIA CLÍNICA (el resto) | `HISTORIA CLINICA`, `HC` |
| 9 | AYUDAS DIAGNÓSTICAS | `AYUDAS DIAGNOSTICAS`, `LABORATORIO`, `RADIOGRAFIA`, `TOMOGRAFIA`, `ECOGRAFIA`, `DX`… |
| 10 | MEDICAMENTOS | `MEDICAMENTOS`, `INGESTA`, `PLAN DE MANEJO`, `MED` |
| 11 | NOTAS DE ENFERMERÍA | `NOTAS DE ENFERMERIA`, `ENFERMERIA`, `NTE` |
| 12 | INSUMOS | `INSUMOS`, `GASTOS QUIROFANO`, `INS` |
| 13 | OTROS | todo lo que no reconoció |

**El DETALLADO no entra al PDF**: la lista lo pide en Excel, así que se queda
como archivo aparte en la carpeta de la factura.

Dentro de un mismo grupo los archivos van en **orden natural** de nombre
(`2` antes que `10`).

---

## 2) Cómo decide de qué es cada PDF

Por el **nombre del archivo**. Dos reglas que evitan los errores típicos:

- **Gana la palabra más larga**, no la primera que aparezca. Así
  «NOTAS DE ENFERMERÍA» no se lo lleva `NOTAS`, y «CONSULTA DE URGENCIAS» no se
  confunde con una consulta cualquiera.
- **Las abreviaturas van sueltas.** `INS` no puede casar dentro de
  `INSTITUCIONAL`, ni `HC` dentro de `HCG12`.

**Lo que no reconoce no se pierde**: va al grupo OTROS y sale listado aparte en
el reporte, para que el auditor lo mire.

Si el equipo usa una palabra que el bot no conoce, se agrega sin tocar el
código con `--mapa-nombres`:

```json
{ "ANGIOTAC": "AYUDAS", "SOAT": "OTROS", "GASTOS DE CIRUGIA": "INSUMOS" }
```

---

## 3) Uso

```
REM 1) PRIMERO en simulación: muestra el orden y no toca nada.
py tools\unir_soportes_adres.py --carpeta "Z:\...\TECNICOS\CAROLINA" ^
    --reporte-csv "Z:\...\TECNICOS\CAROLINA\SOPORTES_UNIDOS.csv"

REM 2) Si el listado se ve bien, con --aplicar sí une.
py tools\unir_soportes_adres.py --carpeta "Z:\...\TECNICOS\CAROLINA" --aplicar ^
    --reporte-csv "Z:\...\TECNICOS\CAROLINA\SOPORTES_UNIDOS.csv"
```

| Opción | Para qué |
|---|---|
| `--carpeta` | La carpeta del gestor (CAROLINA, CLAUDIA, OSCAR…) |
| `--facturas archivo.xlsx` | Solo las facturas de esa lista. Sin esto, todas las carpetas |
| `--aplicar` | Unir de verdad (sin esto solo simula) |
| `--reporte-csv` | Listado de qué archivo quedó en qué grupo y en qué orden |
| `--mapa-nombres` | JSON para agregar palabras propias |

El resultado queda en la carpeta de cada factura como
`<FACTURA>_SOPORTES.pdf`.

---

## 4) Los tres candados

Unir soportes no se deshace de un clic, así que:

1. **Simula por defecto.** Muestra el orden completo y no escribe nada mientras
   no se le pase `--aplicar` (el botón lo pide escribiendo «SI»).
2. **Nunca se come su propio consolidado.** El `<FACTURA>_SOPORTES.pdf` de una
   corrida anterior se excluye de la entrada: se puede correr las veces que
   haga falta sin que se anide.
3. **Un PDF dañado no tumba el lote.** Se omite, se sigue con los demás y queda
   anotado en el reporte.

---

## 5) Qué mirar antes de dar por buena la corrida

En el reporte CSV:

- **`RECONOCIDO = NO - revisar`** — el bot no supo de qué era y lo mandó a
  OTROS. Si es un grupo que sí existe, renombre el archivo o agregue la palabra
  con `--mapa-nombres` y vuelva a correr.
- **`FALTA este soporte`** — la factura no tiene RESPUESTA A GLOSA o no tiene
  EPICRISIS, que son los dos obligatorios.
- **`SIN PDF QUE UNIR`** — la carpeta está vacía.

---

## 6) Pruebas

`tests/test_tools/test_unir_soportes_adres.py` (42 pruebas). Cubren el orden
completo de los trece grupos, que gane la palabra más larga, que las
abreviaturas no casen dentro de otras palabras, que el detallado no se cuele en
el PDF, que ningún archivo se pierda, que sin `--aplicar` no se escriba nada,
que la segunda corrida no anide el consolidado y que un PDF dañado no tumbe el
lote.
