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

Escribe la factura (con o sin ceros: `352890`, `HUS352890` y `HUS0000352890`
llegan a la misma). Revisa cada glosa, confirma o cambia la sugerencia,
escribe la observación del técnico y listo. Con **Ver respuesta** saca el
texto consolidado para pegarlo en el Word del ADRES.

---

## 3. Lo que el sistema NO decide solo

- **Pertinencia médica.** Las causales de pertinencia no traen sugerencia:
  dicen «requiere concepto del médico auditor». Eso lo firma un médico, no un
  bot.
- **Nada queda en firme sin gestor.** El campo `decidido_por` guarda quién
  confirmó cada glosa y cuándo.
- **Recargar el paquete no borra trabajo.** Si el coordinador vuelve a subir
  el mismo reporte (porque el ADRES lo corrigió, por ejemplo), las decisiones,
  observaciones, centros de costo y médicos que el equipo ya había escrito se
  vuelven a pegar sobre las filas nuevas.

---

## 4. De dónde salen las sugerencias

Hay dos niveles, y la pantalla siempre dice cuál es:

- **REGLA** — sale del criterio general por tipo de causal (por ejemplo:
  «glosa por soporte ausente → se subsana anexando el soporte»).
- **APRENDIDA** — sale de lo que el propio equipo ha venido decidiendo para
  esa causal en la macro. Solo se marca así cuando hay **al menos 5 casos** y
  **el 80 % o más** coincide en la misma respuesta. Si el equipo está dividido,
  el sistema se calla y deja que decida el gestor.

Cada sugerencia trae su **motivo** escrito. Nunca se sugiere sin explicar.

---

## 5. Endpoints

| Método | Ruta | Quién | Para qué |
|---|---|---|---|
| POST | `/glosas-adres/importar` | coordinador | carga el reporte (+ la macro) |
| POST | `/glosas-adres/importar-bitacora` | coordinador | carga el detallado cruzado |
| GET | `/glosas-adres/paquetes` | cualquiera | qué paquetes hay cargados |
| GET | `/glosas-adres/buscar?q=` | cualquiera | autocompletado de facturas |
| GET | `/glosas-adres/factura/{numero}` | cualquiera | **todo** lo de esa factura |
| GET | `/glosas-adres/factura/{numero}/respuesta` | cualquiera | el texto consolidado |
| POST | `/glosas-adres/glosa/{id}` | cualquiera | guarda la decisión del gestor |
| POST | `/glosas-adres/aplicar-sugerencias` | cualquiera | aplica las sugerencias en bloque |

`aplicar-sugerencias` acepta `factura` para limitarlo a una sola, y
`solo_confianza: "APRENDIDA"` para aplicar únicamente lo que salió del
criterio del propio equipo (lo más conservador).

---

## 6. Tablas

Tres tablas nuevas, se crean solas al arrancar:

- `paquetes_adres` — un renglón por cargue (archivo, quién, cuándo, totales).
- `glosas_adres` — un renglón por glosa del reporte. Acá viven la
  clasificación, el centro de costos, la sugerencia con su motivo y la
  decisión del gestor.
- `items_detallado_adres` — el detallado cruzado, renglón por renglón.

---

## 7. Relación con los bots de `tools/`

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
