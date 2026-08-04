# Pre-auditor del paquete ADRES — `preauditar_glosas_adres.py`

Deja la **macro de respuesta a glosa** casi lista: llena solo todo lo que es
mecánico y **propone** —sin decidir— lo que falta.

La macro es el reporte del ADRES (16 columnas) **más 10 que el equipo llena a
mano**. De esas diez, **siete son mecánicas**:

| Columna | ¿Quién la llena ahora? |
|---|---|
| 17 CODIGO NUMERICO | **el bot** — los 4 primeros caracteres de la causal, igual que `=MID(O3,1,4)` |
| 18 CLASIFICACION DE LA GLOSA | **el bot** — tabla de 48 causales sacada del trabajo del equipo |
| 21 RTA GLOSA COMPLETA | **el bot** — réplica exacta de la fórmula de la macro |
| 24 CENTRO DE COSTOS | **el bot** — propone el área por el servicio glosado |
| 25 GESTOR / 26 MEDICO | **el bot** — del reparto, renglón por renglón |
| 19 OBSERVACION (ACEPTA/OBJETA/SUBSANA) | **el auditor** — el bot solo sugiere |
| 20 OBSERVACION TECNICO · 22/23 CANTIDAD y VALOR ACEPTADO | **el auditor** |

> **El bot no decide.** La sugerencia va en columnas aparte (27 en adelante),
> con el motivo escrito. La columna 19 solo se toca si se pide expresamente con
> `--aplicar-sugerencias`.

---

## Uso

```bat
cd C:\temp-notas
git pull

py tools\preauditar_glosas_adres.py ^
    --reporte-glosas "D:\...\ReporteGlosasReclamPAQUETE 31068.xlsx" ^
    --macro          "D:\...\NUEVO MODELO MACRO ... 31068.xlsm" ^
    --bitacora       "D:\...\BITACORA_31068.csv" ^
    --salida         "D:\...\MACRO_31068_PREAUDITADA.xlsx" ^
    --respuestas     "D:\...\RESPUESTAS"
```

| Opción | Para qué sirve |
|---|---|
| `--reporte-glosas` | El reporte del ADRES (obligatorio). |
| `--macro` | El libro de la macro. **Muy recomendado**: de ahí salen los catálogos, el reparto y —sobre todo— **lo que el equipo ya escribió, que se conserva intacto**. |
| `--bitacora` | La bitácora del ajustador de detallados: agrega el estado de cada ítem. |
| `--reparto` | Excel/CSV con FACTURA, GESTOR y MEDICO, si el reparto viene aparte. |
| `--salida` | El libro resultante (.xlsx). |
| `--respuestas` | Carpeta para el **Word de respuesta por factura** (lo que hoy hace la macro con Word). |
| `--aplicar-sugerencias` | `no` (por defecto), `aprendidas` (solo el criterio que el propio equipo ya usó) o `todas`. |
| `--minimo-glosado` | Ignora las glosadas por menos de un peso (redondeos del ADRES). |
| `--reporte-csv` | Resumen por causal de lo que hizo y por qué. |

---

## Cómo propone, y por qué se le puede creer

1. **Del criterio del equipo** (`APRENDIDA`): si en la macro ya hay decisiones
   suficientes para una causal y coinciden entre sí, el bot propone **esa**
   decisión y dice en cuántos casos se basa. Cuantas más glosas resuelvan, más
   aprende: el mismo comando, corrido otra vez, propone mejor.
2. **Por regla** (`REGLA`): glosa de soportes → subsanar anexando el soporte;
   glosa de tarifa → objetar contra el valor pactado; glosa a toda la
   reclamación por FURIPS → subsanar el formulario.
3. **No propone nada** donde hace falta criterio humano: pertinencia (es del
   médico auditor), facturación, CUPS, FACOSTE y habilitación REPS. Ahí escribe
   por qué lo deja abierto.

---

## Verificado contra el trabajo real del equipo

Corrido sobre el paquete 31068 y comparado renglón por renglón contra la macro
que el equipo venía llenando a mano (4.619 filas):

| Columna | Resultado |
|---|---|
| Filas | **4.619 de 4.619**, en el mismo orden |
| CODIGO NUMERICO | 2.989 iguales, **0 distintos** |
| RTA GLOSA COMPLETA | **4.619 iguales, 0 distintos** (carácter por carácter) |
| GESTOR | 4.619 iguales, **0 distintos** |
| MEDICO | 2.595 iguales, **0 distintos** |
| CLASIFICACION | 4.594 iguales, **25 distintos** |

Las 25 diferencias son todas de la causal **4506**, la única que el equipo
clasificó de dos formas distintas (231 veces `FACTURACION` y 24 `PERTINENCIA`).
El bot usa la mayoritaria: conviene unificar el criterio.

Y lo que estaba sin llenar:

- **CENTRO DE COSTOS**: de 0 a **4.248 de 4.619** propuestos. Los 371 que
  quedan en blanco son los que de verdad no se pueden deducir (la habitación no
  dice de qué especialidad es; las glosas a la reclamación no son de un
  servicio).
- **Decisiones**: 3.061 sugerencias con su motivo; **1.558 quedan para el
  auditor**, casi todas de pertinencia.

> **Una segunda corrida no borra nada.** Lo que una persona escribió se copia
> tal cual —incluidos los espacios— y el bot no lo pisa.

---

## El Word de respuesta por factura

Con `--respuestas` se genera un documento por factura, igual que la macro VBA
`GenerarWord_Factura_Ordenada`: encabezado con el total aceptado, las
respuestas aceptadas **agrupadas y ordenadas de mayor a menor valor**, después
las objetadas y subsanadas sin repetir, y el párrafo de glosa extemporánea
(Resolución 1236 de 2023, artículo 8 numeral 8.5).

A diferencia de la macro, **no necesita Word**: se genera con `python-docx`
(`py -m pip install python-docx`). Si falta la librería salen como `.txt` y
avisa.

## Pruebas

```bash
py -m pytest tests/test_tools/test_preauditar_glosas_adres.py -q
```
