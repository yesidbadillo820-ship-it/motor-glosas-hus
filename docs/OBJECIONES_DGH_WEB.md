# Objeciones DGH — armar el archivo de cargue desde la aplicación

Pantalla **Objeciones DGH** (barra lateral). El auditor sube dos Excel y baja
los dos archivos de siempre, sin consola y sin pedirle el cruce a nadie.

---

## 1) Qué hace

| Entra | Sale |
|---|---|
| El Excel de glosas que mandó la entidad | `OBJECIONES_<ENTIDAD>_<DDMMAAAA>.xlsx` — el que se sube al DGH |
| El export de servicios facturados del DGH | `CRUCE_<ENTIDAD>_<DDMMAAAA>.xlsx` — el respaldo, con la hoja `REVISAR` |

Antes de descargar nada, la pantalla muestra el resumen: cuántas objeciones
quedaron en ALTA, MEDIA, BAJA y sin cruce, la tabla de lo que hay que revisar y
el detalle por factura.

**Entidades que reconoce solo:**

| Entidad | Qué archivo se sube |
|---|---|
| **FAMISANAR** | Export DEVYGLOSAS de 4 columnas; el servicio va escondido en el texto de la glosa. |
| **Dispensario Médico** | Excel de glosa inicial de 5 columnas, con el servicio objetado en columna propia. |
| **SAVIA SALUD** | Export de 8 columnas, con código y nombre del servicio. |
| **SALUD TOTAL** | Export NotificacionGLS de 6 columnas. No manda código: el servicio se ubica por nombre y valor. |
| **SANITAS** | Hoja «Glosa» de 7 columnas. Ojo: la 2ª dice «NUMERO DE FACTURA» pero trae el código de glosa. |
| **VCO** (COOSALUD, Fiduprevisora, SAVIA…) | Consolidado del acta del portal VCO, 10 columnas, con el acta en la primera. |
| **EMSSANAR** | No manda Excel: son los **PDF** de ripslink («Objeción a Factura N° HUS…»), uno por factura. Se marcan varios de una vez (hasta 300, que es el tope del DGH). |
| **ADRES** | Excel de glosas del ADRES. Tiene motor propio: homologa los códigos SOAT a los CUPS del hospital, aplica el tope de valor de cada servicio y decide el tipo por la columna `CLASIFICACION` (sus causales son de cuatro dígitos y no dicen el grupo). Se le puede agregar el **Homologador Gold Standard CUPS↔SOAT** como segundo archivo. |

Si el formato cambió y no la reconoce, se elige a mano en el selector; si no la
reconoce **no procesa a ciegas**, avisa qué encabezados leyó.

Con esto la pantalla sirve para **todas** las entidades que el motor sabe
trabajar. Si un lote pasa de **300 facturas** —el tope que recibe el DGH en un
archivo— la pantalla lo avisa: ese lote hay que partirlo antes de subirlo (por
consola, el bot del ADRES ya lo parte solo en `_LOTE_01`, `_LOTE_02`…).

## 2) Por qué hacen falta los dos archivos

El archivo de la entidad dice *cuánto* se objeta y *por qué*, pero el código del
servicio o no viene, o viene en el catálogo de la entidad y no en el del
hospital. DGH sólo reconoce el suyo. El export de servicios facturados es lo que
permite traducirlo. Sin él, `SLNSERPRO` saldría vacío en todo el archivo.

El motor **no puede entrar al DGH por su cuenta**: ese export lo sigue sacando
el auditor.

## 3) Las reglas, que no cambian

Son las mismas de siempre (están en `CLAUDE.md`) y las aplica el mismo bot de
`tools/` que se usa por consola, así que **lo que baja de la pantalla es
idéntico a lo que sale por línea de comandos**:

- `CTNCENCOS` vacía siempre;
- `CROTIPOBJ` por factura (0 administrativa, 1 médica, 2 mixta);
- `SLNSERPRO` sin códigos inventados: sin cruce confiable, celda vacía;
- el archivo lleva **el 100% de los renglones**, para que los totales cuadren
  con lo que reportó la entidad.

La pantalla muestra el veredicto de esa verificación en verde o en rojo. Si sale
en rojo, **no se sube**: se avisa qué regla se incumplió.

## 4) Cómo se usa

1. Barra lateral → **Objeciones DGH**.
2. Arrastrar el Excel de la entidad y el export del DGH.
3. Dejar la entidad en «Reconocerla sola» (o elegirla) y confirmar la fecha.
4. **Armar el archivo**. En lotes grandes tarda hasta medio minuto.
5. Mirar el resumen y la tabla de revisión, y descargar.

Lo que quede en la tabla de revisión se completa a mano en el Excel antes de
subirlo: esas filas van con la celda del servicio vacía, nunca con un código
adivinado.

## 5) Cómo está hecho

| Pieza | Dónde |
|---|---|
| Pantalla | `static/index.html`, panel `p-objeciones-dgh` (funciones `obj*`) |
| Rutas | `app/api/routers/objeciones_dgh.py` — acceso AUDITOR o superior |
| Orquestación | `app/services/objeciones_dgh_service.py` |
| El trabajo de verdad | `tools/organizar_objeciones_*.py` sobre `tools/_cruce_dgh.py` |

El servicio **no reimplementa nada**: importa los bots y recoge lo que
producen. Si una regla cambia, cambia en el bot y la pantalla la hereda.

Los archivos armados quedan media hora en memoria esperando la descarga, y
sólo los ve quien los armó. Después se sueltan solos: no quedan datos de
pacientes guardados en el servidor.

Pruebas: `tests/test_services/test_objeciones_dgh_service.py` y
`tests/test_api/test_objeciones_dgh.py`.
