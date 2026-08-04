# Glosas ADRES en la página (módulo web)

Este módulo reemplaza en la web el botón que antes decía **Cobranza Live**
(no se usaba) y pone en su lugar el trabajo del paquete de glosas del ADRES.

La idea es simple: **el gestor solo escribe el número de factura** y la
pantalla le trae todo lo que antes tenía que buscar a mano en tres archivos
distintos (el reporte del ADRES, la macro de respuestas y el detallado
impreso de la factura).

---

## 1. Qué hace, en cristiano

Antes el equipo trabajaba así:

1. abría el `ReporteGlosasReclamPAQUETE 31068.xlsx` y buscaba la factura,
2. abría la macro de Excel y llenaba a mano el centro de costos, el gestor,
   la clasificación de la causal y la respuesta,
3. abría el detallado impreso para ver qué ítem le glosaron,
4. armaba el texto de respuesta y lo pegaba en un Word.

Ahora eso es una sola pantalla. El coordinador carga el reporte **una vez**
y el gestor escribe la factura. Le sale:

| Lo que ve el gestor | De dónde sale |
|---|---|
| Cada glosa con su causal y su valor | del reporte del ADRES |
| La clasificación (SOPORTES / PERTINENCIA / TARIFAS / FACTURACION…) | de las 48 causales que ya tenía mapeadas el equipo |
| El centro de costos | de las pistas del nombre del servicio, o de lo que ya escribió el equipo en la macro |
| El gestor y el médico asignado | de la macro que se cargue |
| **La sugerencia de respuesta con su motivo** | de las reglas + de lo que el propio equipo ha venido decidiendo |
| El detallado cruzado (qué pagó ya el ADRES y qué sigue glosado) | de la bitácora del ajustador de detallados |
| El texto de respuesta consolidado | de la misma fórmula que armaba la macro |

**La sugerencia nunca decide sola.** El gestor la confirma o la cambia.
Mientras nadie confirme, la glosa queda como *pendiente*.

---

## 2. Cómo se usa

### Paso 1 — El coordinador carga el paquete (una sola vez)

En la pantalla **📄 Glosas ADRES** → botón **Cargar paquete**:

- **Archivo obligatorio:** el `ReporteGlosasReclamPAQUETE NNNNN.xlsx` que baja
  del ADRES.
- **Archivo opcional:** el Excel de la macro con la que venía trabajando el
  equipo. Si se sube, el sistema **aprende** de él: se trae el gestor, el
  médico, el centro de costos y las respuestas ya escritas, y usa esas
  decisiones para afinar las sugerencias.

Solo pueden cargar los roles **COORDINADOR** y **SUPER_ADMIN**.

### Paso 2 — (Opcional) cargar la bitácora del detallado

Si ya se corrió `tools/ajustar_detallado_glosas.py` sobre los lotes, el CSV
`BITACORA_NNNNN.csv` que deja ese bot se puede subir acá también. Con eso la
pantalla muestra, renglón por renglón, **qué le aprobó ya la entidad y qué
sigue glosado**.

### Paso 3 — El gestor trabaja

**Apenas se carga el archivo salen las facturas a auditar**, con el avance de
cada una. El gestor hace **clic en una** y se le despliega por qué y qué le
glosan. También puede escribir el número directo (con o sin ceros: `352890`,
`HUS352890` y `HUS0000352890` llegan a la misma).

Por cada glosa: confirma o cambia la sugerencia y escribe la observación del
técnico. **Se guarda solo** mientras escribe, y hay un botón **Guardar** para
forzarlo. Cuando termina la factura pulsa **Terminar factura** — si después hay
que corregir algo, **Reabrir factura**, y queda registrado quién la reabrió.

Con **Ver respuesta** saca el texto consolidado para el Word del ADRES, y con
**📄 PDF de evidencia** el reporte de la factura auditada.

La lista se filtra por **Pendientes / En proceso / Cerradas**, para saber en
todo momento qué falta.

---

## 3. Lo que el sistema NO decide solo

- **Pertinencia médica.** Las causales de pertinencia no traen sugerencia:
  dicen «requiere concepto del médico auditor». Eso lo firma un médico, no un
  bot.
- **Las causales que trabajan dos áreas** (hoy la **4506**). Ver el punto 4.
- **Nada queda en firme sin gestor.** El campo `decidido_por` guarda quién
  confirmó cada glosa y cuándo.
- **Recargar el paquete no borra trabajo.** Si el coordinador vuelve a subir
  el mismo reporte (porque el ADRES lo corrigió, por ejemplo), las decisiones,
  observaciones, centros de costo y médicos que el equipo ya había escrito se
  vuelven a pegar sobre las filas nuevas.

---

## 4. La causal 4506: la trabajan dos áreas

La 4506 («el material hace parte de otro servicio») **no está mal clasificada**
en la macro: la ven **dos áreas distintas**.

- Los **gestores** la trabajan por **FACTURACION**.
- Las **médicas** la trabajan por **PERTINENCIA**, cuando lo glosado es
  **material de osteosíntesis o insumos de alto costo** (curación avanzada e
  instrumental de quirófano).

Como quién la toma depende del procedimiento y de lo que se glosó, **el sistema
no la clasifica solo**. La marca como `POR ASIGNAR` y **solo un SUPER ADMIN**
puede repartirla, desde la misma pantalla.

El bot propone el área con su motivo escrito, para ahorrar el 90 % del trabajo:

| Lo glosado | Área que se propone |
|---|---|
| Osteosíntesis, prótesis, stent, injerto, cemento óseo | PERTINENCIA (médicas) |
| Curación avanzada: hidrofibra con plata, hidrocoloide, gasa de parafina, hemostático | PERTINENCIA (médicas) |
| Instrumental de quirófano: fresas, perforador craneal, dermatomo, cuchilla de corte de hueso | PERTINENCIA (médicas) |
| Insumo corriente: gasa, apósito de gasa, aguja, bisturí, sutura corriente | FACTURACION (gestores) |

Los patrones son **específicos a propósito**: el apósito de hidrofibra con
plata es curación avanzada, pero el apósito de gasa no; la cuchilla para corte
de hueso es de quirófano, pero la de bisturí no.

**Qué tan acertada es la propuesta:** se midió contra las 255 filas de causal
4506 que el equipo clasificó a mano en el paquete 31068 — coincide en **249
(97,6 %)**. Las 6 en que no coincide son casos donde el propio equipo repartió
distinto la misma descripción. De todos modos el super admin confirma.

Cuando el super admin asigna el área, **la sugerencia de respuesta se
recalcula**: si queda en PERTINENCIA, el bot deja de proponer, porque esa la
firma un médico auditor.

---

## 5. Los centros de costos salen del catálogo del hospital

No se escriben a mano. La pantalla muestra un **desplegable con los 45 centros
oficiales** (`510204-COSTOS`, `733001-QUIROFANOS`, `510406-DIREC SUBGCIA DE
ALTO COSTO`, …) — la misma lista del botón que tiene la macro.

- El bot propone el centro según el servicio glosado, siempre en la forma
  oficial `código-NOMBRE`.
- Si el hospital cambia el plan de cuentas, **manda el catálogo que traiga la
  macro** que se cargue; el del bot es solo el respaldo.
- Lo que un gestor escoja a mano queda marcado (`centro_costos_por`) y **no se
  vuelve a pisar** cuando se recarga el paquete.
- Los que el bot no puede deducir quedan en blanco a propósito, resaltados en
  la pantalla, para que alguien los complete. En el 31068 son 371 de 4.619.

---

## 6. Las glosas totales no se muestran

En el reporte del ADRES hay filas **con la columna «Descripción Glosa» vacía**.
Son el desglose de una **GLOSA TOTAL**: el ADRES glosó la reclamación entera
por el FURIPS y lista los ítems por debajo, pero sin causal propia. **No se
responden una por una**, así que la pantalla no las muestra — antes ensuciaban
la tabla y hacían parecer que «no salía la descripción de la glosa».

En el paquete 31068 son **1.630 de 4.619 filas ($236.217.091)**. Por ejemplo la
factura 311371 pasa de 150 renglones a **21 que sí hay que trabajar**.

**No desaparecen en silencio:** arriba de la tabla sale un aviso diciendo
cuántas son y cuánto valen, con un enlace para verlas. En la base siguen
guardadas todas (`glosa_total = true`), y el endpoint acepta
`?incluir_totales=true`.

En el PDF de evidencia tampoco van en la tabla, pero sí se dicen al pie.

---

## 7. Facturas sin detallado

Algunas facturas del paquete no tienen detallado (en el 31068 son cuatro:
311371, 367368, 380246 y 394817). **No es un fallo:** esas facturas no venían
en los lotes de detallados que se importaron — se verificó archivo por archivo
en los siete lotes.

La pantalla **no deja al gestor sin nada**: muestra el aviso explicando por qué
no hay detallado y **abajo trae igual todo lo del reporte del ADRES** — las
glosas, sus causales, los valores y las sugerencias. Si después aparece el
detallado, basta volver a cargar la bitácora y el aviso desaparece.

---

## 8. De dónde salen las sugerencias

Hay dos niveles, y la pantalla siempre dice cuál es:

- **REGLA** — sale del criterio general por tipo de causal (por ejemplo:
  «glosa por soporte ausente → se subsana anexando el soporte»).
- **APRENDIDA** — sale de lo que el propio equipo ha venido decidiendo para
  esa causal en la macro. Solo se marca así cuando hay **al menos 5 casos** y
  **el 80 % o más** coincide en la misma respuesta. Si el equipo está dividido,
  el sistema se calla y deja que decida el gestor.

Cada sugerencia trae su **motivo** escrito. Nunca se sugiere sin explicar.

---

## 9. Endpoints

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| POST | `/glosas-adres/importar` | coordinador | carga el reporte (+ la macro) |
| POST | `/glosas-adres/importar-bitacora` | coordinador | carga el detallado cruzado |
| GET | `/glosas-adres/paquetes` | cualquiera | qué paquetes hay cargados |
| GET | `/glosas-adres/facturas` | cualquiera | **la lista de facturas a auditar**, con el avance |
| GET | `/glosas-adres/buscar?q=` | cualquiera | autocompletado de facturas |
| GET | `/glosas-adres/factura/{numero}` | cualquiera | **todo** lo de esa factura |
| GET | `/glosas-adres/factura/{numero}/respuesta` | cualquiera | el texto consolidado |
| POST | `/glosas-adres/factura/{numero}/estado` | cualquiera | cierra la factura o la reabre |
| GET | `/glosas-adres/factura/{numero}/evidencia.pdf` | cualquiera | el PDF de evidencia |
| POST | `/glosas-adres/glosa/{id}` | cualquiera | guarda la decisión del gestor |
| POST | `/glosas-adres/aplicar-sugerencias` | cualquiera | aplica las sugerencias en bloque |
| GET | `/glosas-adres/centros-costos` | cualquiera | el catálogo oficial, para el desplegable |
| GET | `/glosas-adres/por-asignar` | cualquiera | glosas 4506 esperando reparto |
| POST | `/glosas-adres/glosa/{id}/area` | **super admin** | reparte la glosa entre gestores y médicas |

`aplicar-sugerencias` acepta `factura` para limitarlo a una sola, y
`solo_confianza: "APRENDIDA"` para aplicar únicamente lo que salió del
criterio del propio equipo (lo más conservador).

---

## 10. Tablas

Tres tablas nuevas, se crean solas al arrancar:

- `paquetes_adres` — un renglón por cargue (archivo, quién, cuándo, totales) y
  el catálogo de centros de costos que traía esa macro.
- `glosas_adres` — un renglón por glosa del reporte. Acá viven la
  clasificación, el centro de costos (y quién lo puso), la sugerencia con su
  motivo, el reparto de área (`requiere_asignacion`, `area_sugerida`,
  `area_asignada_por`) y la decisión del gestor.
- `facturas_adres` — el estado de cada factura (PENDIENTE / EN PROCESO /
  CERRADA), con quién la cerró y quién la reabrió.
- `items_detallado_adres` — el detallado cruzado, renglón por renglón.

---

## 11. Relación con los bots de `tools/`

El módulo web y los bots de línea de comandos comparten **las mismas reglas**:
el servicio importa las funciones de `tools/preauditar_glosas_adres.py`, no
las copia. Si mañana cambia un criterio de clasificación, cambia en un solo
lado y sirve para los dos.

- `tools/ajustar_detallado_glosas.py` → produce la bitácora que alimenta el
  detallado de esta pantalla.
- `tools/dividir_detallado_por_factura.py` y `tools/excel_a_pdf.py` → producen
  el Excel y el PDF por factura que se adjuntan a la respuesta.
- `tools/preauditar_glosas_adres.py` → las reglas de clasificación,
  sugerencia y el texto de respuesta.

Detalle de cada uno en `tools/README_*.md`.
