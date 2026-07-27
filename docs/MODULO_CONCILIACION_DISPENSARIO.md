# MÓDULO: CONCILIACIÓN DE CARTERA — DISPENSARIO MÉDICO BUCARAMANGA

**Documentación técnica oficial de entrega al equipo principal**

| Campo | Valor |
|---|---|
| Módulo | Conciliación de cartera / Expediente de conciliación (Dispensario Médico) |
| Repositorio | `yesidbadillo820-ship-it/motor-glosas-hus` |
| Rama de desarrollo | `claude/dispensario-objections-bot-h8dfcf` |
| Rama base (default) | `motor-glosas` |
| Pull Request | #188 (CI en verde: Tests ✅ · Lint ✅ · Security ✅) |
| Commit principal | `15ebe51` — *DISPENSARIO: Expediente Inteligente de Conciliacion (hoja maestra unica por factura)* |
| Entidad | DIRECCIÓN DE SANIDAD EJÉRCITO (DIGSA) — NIT 901541137 |
| Prestador | DISPENSARIO MÉDICO BUCARAMANGA (MEBUG) |
| IPS | ESE Hospital Universitario de Santander — NIT 900006037-4 |
| Contrato vigente | 440-DIGSA-DMBUG-2025 |
| Fecha de entrega | 27 de julio de 2026 |

---

## 1. OBJETIVO DEL DESARROLLO

### 1.1 Por qué se creó este módulo

El HUS tiene con el Dispensario Médico una cartera de **$13.621.817.613** (corte 30/06/2026) con **$3.338.232.845 en glosas**. El área de cartera necesitaba preparar la **mesa de conciliación** con la entidad, pero la información estaba dispersa en bases que nadie había cruzado nunca:

- **La glosa que puso la EPS** vivía en un export de SIMED (`RECEPCION DE OBJECIONES`).
- **La respuesta que envió el HUS** vivía en OTRO export de SIMED (`TRAMITE DE OBJECION`).
- **El saldo y el estado** vivían en el estado de cartera de DGH (Dinámica Gerencial).
- **El resultado de actas previas** vivía en un tercer archivo (`CRUCE ACTAS`).

Para preparar una sola factura, el auditor tenía que abrir 4 archivos, filtrar en cada uno y transcribir a mano. Con 147 facturas y 444 glosas eso es inviable en el tiempo de una mesa.

### 1.2 Qué problema resolvía

**Problema central:** no existía un documento donde, al abrir una factura, se viera *toda su historia* — qué objetó la EPS, con qué motivo exacto, qué respondimos nosotros, con qué argumento, en qué acta quedó, y dónde están los soportes.

**Problemas derivados que también se resolvieron:**

1. **Duplicación de valores.** Las bases de SIMED repiten el valor de la factura en cada línea de glosa. Sumar esa columna infla la cartera. (Ver §13.1.)
2. **Actas duplicadas.** El acta `AC000639` es la misma que la `SINAC 720`; contarla dos veces inflaba el levantado.
3. **Filas de totales ocultas.** Los archivos de cartera traen filas banner/totales mezcladas con los datos, que al sumarse duplicaban las cifras.
4. **Diferencias no detectadas** entre el valor glosado del lote y el registrado en cartera.
5. **Formato no institucional.** El área no puede llevar a una mesa un Excel improvisado: la conciliación se firma sobre el **formato oficial del acta SINAC**.

### 1.3 Qué necesidad cubría

Preparar de forma **técnica, trazable y auditable** la conciliación, con dos entregables:

- **Entregable A (visión de cartera):** expediente de las 5.571 facturas — *construido y luego reemplazado por decisión del usuario, ver §1.4*.
- **Entregable B (visión de mesa) — EL VIGENTE:** acta de conciliación de las **147 facturas** que van a la mesa, en el formato oficial del acta SINAC, lista para diligenciar en vivo.

### 1.4 Cambio de enfoque durante el desarrollo (decisión documentada)

**Esto es lo más importante que debe saber quien reciba el módulo.**

El desarrollo se construyó primero sobre el universo completo de cartera (5.571 facturas, 18.378 glosas). El resultado fue `EXPEDIENTE_CONCILIACION_DISPENSARIO_24JUL2026.xlsx`, con 5 hojas y 11 cruces de consistencia.

**El usuario lo rechazó explícitamente**, con este argumento textual:

> *"No es el resultado que esperaba. No necesito un expediente de las 5.571 facturas de la cartera. El universo de trabajo son únicamente las 147 facturas que actualmente están pendientes por conciliar. […] El objetivo no es administrar toda la cartera, sino preparar de forma técnica y ordenada la próxima conciliación de esas 147 facturas."*

Además exigió una **compuerta de aprobación**:

> *"No construyas el archivo hasta identificar exactamente cuáles son las 147 facturas objeto de la conciliación. Antes de generar el Excel, muéstrame el listado […] Solo después de mi aprobación construye la herramienta definitiva."*

Y posteriormente fijó el **formato**, adjuntando el acta SINAC 720 real:

> *"ahora necesito que me ayudes hacerlo pero que me quede como este archivo que es como lo necesito"*

**Consecuencia arquitectónica:** el módulo tiene **dos generadores**, no uno. Ambos son código válido y funcional, pero cumplen propósitos distintos:

| Generador | Universo | Estado | Formato de salida |
|---|---|---|---|
| `tools/hoja_maestra_conciliacion.py` | 5.571 facturas (toda la cartera) | En repo, commiteado, PR #188 | Libro nuevo de 5 hojas |
| `generar_acta_147.py` | 147 facturas (la mesa) | **Vigente** — en scratchpad, PENDIENTE de promover a `tools/` | Acta SINAC oficial (.xlsm) |

**No se descartó el primero**: sigue siendo la única herramienta que da visión de la cartera completa y ejecuta los 11 cruces de consistencia sobre todo el universo. Se relegó a herramienta de gestión de cartera, no de mesa.

---

## 2. ARQUITECTURA

### 2.1 Naturaleza del módulo

Este módulo **no es una aplicación web**. Es un conjunto de **herramientas de línea de comandos (CLI) en Python** que ejecutan un proceso **ETL determinista**:

```
Exports de SIMED / DGH (.xlsx)  →  [ETL Python]  →  Libro Excel entregable (.xlsx / .xlsm)
```

Consecuencias directas (desarrolladas en §5, §6, §7, §8):

- **No hay base de datos.** Los archivos Excel *son* la capa de datos.
- **No hay backend HTTP.** No hay endpoints, controladores ni middleware.
- **No hay frontend web.** El libro Excel *es* la interfaz de usuario.
- **No hay llamadas a IA en tiempo de ejecución.** El motor es 100 % determinista.

Esta decisión fue deliberada: el usuario es un **auditor de cartera**, no un programador. El entregable debe abrirse en el Excel de su equipo, funcionar sin conexión, sin instalación y sin servidor, y poder llevarse a una mesa de conciliación donde se diligencia en vivo.

### 2.2 Estructura de carpetas y archivos

```
motor-glosas-hus/
├── tools/                                        # Herramientas CLI (sin __init__.py)
│   ├── hoja_maestra_conciliacion.py              # ★ NUEVO (1.088 líneas) — Generador A
│   ├── exportar_conciliacion_dispensario.py      # preexistente (CONCILIACION.xlsx)
│   ├── preparar_lote_dgh_dispensario.py          # preexistente (export DGH → layout motor)
│   ├── indexar_soportes_dispensario.py           # preexistente (índice de soportes Y:/X:)
│   ├── expediente_conciliacion.py                # preexistente (modelo de datos único)
│   ├── motor_evidencia_dispensario.py            # preexistente (evidencia página a página)
│   ├── motor_verificacion_dispensario.py         # preexistente (hechos probados)
│   ├── motor_decision_dispensario.py             # preexistente (defendibilidad %)
│   ├── piloto_conciliacion_dispensario.py        # preexistente (orquestador)
│   └── asistente_conciliacion_dispensario.py     # preexistente (carga de glosas)
├── tests/test_tools/
│   └── test_hoja_maestra_conciliacion.py         # ★ NUEVO (255 líneas) — 4 tests
├── docs/
│   ├── MODULO_CONCILIACION_DISPENSARIO.md        # ★ ESTE DOCUMENTO
│   ├── CONTEXTO_DISPENSARIO_GLOSAS.md            # preexistente (flujo respuesta SIMED)
│   ├── CONTEXTO_DISPENSARIO_NOTAS.md             # preexistente (notas crédito)
│   └── CONTEXTO_COOSALUD.md                      # preexistente
├── BITACORA.md                                   # ★ MODIFICADO (memoria común de sesiones)
├── CLAUDE.md                                     # instrucciones de repo (preexistente)
├── requirements.txt                              # openpyxl==3.1.5, pdfplumber, reportlab
└── .github/workflows/ci.yml                      # CI: pytest + ruff + pip-audit

FUERA DEL REPO (scratchpad de sesión — PENDIENTE de promover):
└── generar_acta_147.py                           # ★ Generador B VIGENTE (541 líneas)
```

### 2.3 Componentes lógicos

El módulo se divide en **cinco capas**, presentes en ambos generadores:

**Capa 1 — Normalización (utilidades puras).**
Funciones sin efectos secundarios que resuelven las inconsistencias de formato de los exports colombianos: `normalizar_factura`, `_num`/`num`, `_txt`/`txt`, `_fecha`, `_aaaamm`, `cod_corto`, `familia_de`.

**Capa 2 — Carga de fuentes (lectores).**
Una función por archivo de origen, cada una devuelve una estructura Python indexada: `cargar_cartera`, `cargar_recepcion`, `cargar_tramite`, `cargar_cruce_actas`.

**Capa 3 — Cruce y lógica de negocio.**
`construir_glosas` (une glosa ↔ respuesta), `_motivo_eps_para` (desambigua el motivo EPS), `agregar_por_factura`, `resultado_final`, `contrato_por_fecha`, `centro_costo`.

**Capa 4 — Controles de consistencia.**
`calcular_cruces` — los 11 controles automáticos.

**Capa 5 — Presentación (escritura del libro).**
`_escribir_workbook` (Generador A: libro nuevo) / bloque de inserción sobre plantilla (Generador B: acta SINAC).

### 2.4 Modelo de datos (estructuras en memoria)

No hay ORM ni esquema SQL. Las estructuras son diccionarios y listas de Python:

```python
# cargar_cartera → { "HUS0000316347": {...} }
{
    "factura": str,
    "vigencia": str,
    "estado": str,
    "fecha_radicado": datetime,
    "valor_factura": float,
    "saldo_dgh": float,
    "saldo_eps": float,
    "valor_devolucion": float,
    "valor_glosa": float,
    "valor_libre_pago": float,
    "soporte_pago": str,
    "edades": str,
    "levantada_actas": float,
    "aceptada_actas": float,
    "ratificada_actas": float,
    "actas": str,
    "estado_glosa": str,
}

# cargar_recepcion → { "104341": [ {...}, {...} ] }   (indexado por CONSECUTIVO)
{
    "consecutivo": str,
    "factura": str,
    "fecha_glosa": datetime,
    "fecha_factura": datetime,
    "tipo": str,
    "codigo": str,
    "concepto": str,
    "cups": str,
    "servicio": str,
    "valor": float,
    "motivo_eps": str,
}

# cargar_tramite → [ {...}, ... ]  (lista plana, una por línea de respuesta)
{
    "factura": str,
    "rec_consecutivo": str,
    "fecha_glosa": datetime,
    "fecha_factura": datetime,
    "fecha_respuesta": datetime,
    "radicado_respuesta": str,
    "tipo": str,
    "estado_cxc": str,
    "contrato_cod": str,
    "codigo_glosa": str,
    "concepto_glosa": str,
    "servicio": str,
    "glosado": float,
    "aceptado": float,
    "objetado": float,  # DERIVADO = glosado - aceptado
    "argumento": str,
}

# cargar_cruce_actas → [ {...}, ... ]  (una por par FACTURA+ACTA)
{
    "factura": str,
    "acta": str,
    "tipo": str,
    "glosa_inicial": float,
    "aceptada": float,
    "levantada": float,
    "ratificada": float,
    "a_pagar": float,
    "duplicada": bool,  # True si acta == AC000639
}

# construir_glosas → [ {...}, ... ]  (LA ESTRUCTURA CENTRAL: glosa + respuesta juntas)
{
    "factura": str,
    "consecutivo": str,
    "fecha_glosa": datetime,
    "tipo": str,
    "codigo_glosa": str,
    "concepto_glosa": str,
    "servicio": str,
    "cups": str,
    "motivo_eps": str,  # ← lo que objetó la EPS
    "valor_glosado": float,
    "fecha_respuesta": datetime,
    "radicado_respuesta": str,
    "valor_aceptado": float,
    "valor_objetado": float,
    "argumento": str,  # ← lo que respondió el HUS
    "estado_respuesta": "RESPONDIDA" | "SIN RESPUESTA",
    "origen": "TRAMITE" | "RECEPCION",
}
```

### 2.5 Dependencias y librerías

| Librería | Versión | Uso en este módulo | ¿Nueva? |
|---|---|---|---|
| `openpyxl` | 3.1.5 | Lectura/escritura de .xlsx y .xlsm (única dependencia funcional) | **No** — ya estaba en `requirements.txt:13` |
| `pytest` | 9.1.1 | Ejecución de pruebas | No |
| `pytest-asyncio` | 1.4.0 | Requerido por `pytest.ini` (`asyncio_mode = auto`) | No (ver §11.1) |
| `ruff` | — | Lint (`--select F,W6`) y formato | No |
| LibreOffice (`soffice`) | 24.2.7.2 | Recálculo de fórmulas del entregable (**solo desarrollo**) | Ver §11.2 |
| Biblioteca estándar | Python 3.11.15 | `re`, `sys`, `argparse`, `logging`, `pathlib`, `datetime`, `collections.defaultdict`, `copy.copy` | — |

**No se instaló ningún paquete nuevo de Python.** Decisión deliberada: no añadir superficie de dependencias a un repo que ya corre en el equipo del HUS.

### 2.6 APIs

**No se consume ni se expone ninguna API HTTP.** Todas las fuentes son archivos en disco. Las únicas rutas de red que aparecen son **rutas UNC de Windows escritas como texto** en el entregable (no se accede a ellas desde el código):

- `\\172.16.32.83\factura_electronica_net22\AAAAMM` — factura electrónica.
- `Y:\` / `X:\` — soportes documentales (**raíces exactas PENDIENTES de confirmar**, ver §15).

---

## 3. FUNCIONES IMPLEMENTADAS

### 3.A — GENERADOR A: `tools/hoja_maestra_conciliacion.py` (1.088 líneas)

#### 3.A.1 `setup_logging()` — línea 102
- **Qué hace:** configura `logging` a nivel INFO con formato `%(asctime)s [%(levelname)s] %(message)s`.
- **Cómo funciona:** una llamada a `logging.basicConfig`.
- **Por qué existe:** el auditor corre la herramienta en consola y necesita ver el avance y las cifras finales sin abrir el Excel.
- **Modifica:** nada (solo estado del logger).
- **Depende de ella:** `main()`.

#### 3.A.2 `_num(x) -> float` — línea 109
- **Qué hace:** convierte cualquier celda a número tolerando el formato colombiano.
- **Cómo funciona:** si es `int`/`float` lo devuelve; si es texto elimina `$` y espacios, descarta `""`, `"-"`, `"None"`, y aplica tres reglas de separador decimal:
  1. Coma **y** punto (`"1.234,56"`) → el punto es de miles: `1234.56`.
  2. Solo coma (`"1234,56"`) → la coma es decimal: `1234.56`.
  3. **Más de un punto y sin coma** (`"$ 3.211.891"`) → todos son de miles: `3211891.0`.
  Cualquier fallo de conversión devuelve `0.0`, nunca lanza excepción.
- **Por qué existe:** los exports de DGH/SIMED mezclan números reales con texto formateado. Sin esta función, `float("$ 3.211.891")` revienta el proceso.
- **Decisión técnica:** la regla 3 **se añadió durante el desarrollo** porque el test `test_num_formato_colombiano` falló con `assert 0.0 == 3211891.0`. La versión inicial solo contemplaba las reglas 1 y 2.
- **Modifica:** nada (función pura).
- **Depende de ella:** todos los lectores (`cargar_cartera`, `cargar_recepcion`, `cargar_tramite`, `cargar_cruce_actas`).

#### 3.A.3 `_txt(x) -> str` — línea 132
- **Qué hace:** normaliza una celda a texto limpio.
- **Cómo funciona:** `None` → `""`; aplica `.strip()`; convierte los marcadores `"None"` y `"-"` a `""`.
- **Por qué existe:** los exports traen literalmente la cadena `"None"` y guiones como marcador de vacío. Sin normalizar, esos valores se imprimirían en el acta.
- **Depende de ella:** todos los lectores.

#### 3.A.4 `normalizar_factura(x) -> str` — línea 139
- **Qué hace:** lleva cualquier representación de factura a la forma canónica `HUS` + 10 dígitos.
- **Cómo funciona:** extrae el primer grupo de dígitos con `re.search(r"(\d+)", s)` y lo rellena con `zfill(10)`, anteponiendo `HUS`. Acepta `"HUS0000316347"`, `"316347"` y `316347` (entero).
- **Por qué existe:** **es la clave de cruce de todo el módulo.** Cada fuente escribe la factura distinto: CARTERA usa `HUS0000316347`, el lote separa prefijo (`HUS`) y número (`426013`) en dos columnas, y DGH a veces la trae como entero. Sin esta normalización, ningún cruce encuentra nada.
- **Modifica:** nada (función pura).
- **Depende de ella:** absolutamente todos los cruces del módulo.
- **Cubierta por:** `test_normalizar_factura`.

#### 3.A.5 `_fecha(x)` — línea 150
- **Qué hace:** devuelve un `datetime` o `None`.
- **Cómo funciona:** si ya es `datetime` lo devuelve; si es texto prueba tres formatos (`%Y-%m-%d %H:%M:%S`, `%Y-%m-%d`, `%d/%m/%Y`) recortando la cadena al largo del formato + 2; si ninguno casa devuelve `None`.
- **Por qué existe:** las fechas llegan como `datetime` real, como texto ISO con microsegundos (`2025-01-13 08:14:02.850000`) o como texto local. Se necesita un tipo único para escribir en Excel y para derivar el período.
- **Depende de ella:** `_aaaamm`, `contrato_por_fecha`, `_escribir_workbook`.

#### 3.A.6 `_aaaamm(*fechas)` — línea 165
- **Qué hace:** devuelve el período `AAAAMM` de la primera fecha válida de la lista, o `""`.
- **Cómo funciona:** itera los argumentos, aplica `_fecha` a cada uno y con el primero válido formatea `f"{d.year:04d}{d.month:02d}"`.
- **Por qué existe:** las rutas de soportes y de factura electrónica se organizan por carpeta mensual. Se pasa una cadena de respaldo (`fecha_factura`, luego `fecha_radicado`) porque no toda factura tiene fecha de factura.
- **Depende de ella:** construcción de `UBICACION SOPORTES` y `UBICACION FACTURA ELECTRONICA`, y el cruce #4.

#### 3.A.7 `contrato_por_fecha(fecha_fac, codigo_raw) -> str` — línea 174
- **Qué hace:** decide si aplica el contrato **287** o el **440**.
- **Cómo funciona:** regla de vigencia por fecha — hasta el 30-nov-2025 → `287`; desde dic-2025 → `440`. Devuelve el texto con la marca de aproximación y el código interno crudo entre paréntesis (ej. `"287 (aprox; cod U22031)"`). Sin fecha y sin código devuelve `"PENDIENTE"`.
- **Por qué existe:** la base tarifaria depende del contrato (**287 = SOAT −15 %**, **440 = SOAT −20 %**). La bitácora documenta que **372 glosas venían mal marcadas "SIN CONTRATO"** cuando sí tenían contrato.
- **Decisión técnica documentada:** se usa la **fecha de la factura** como aproximación porque **la fecha de atención real vive en los RIPS**, no en los exports. Por eso la salida dice explícitamente `(aprox)` — nunca se presenta como dato duro.
- **Cubierta por:** `test_contrato_por_fecha`.

#### 3.A.8 `cargar_cartera(ruta) -> dict[str, dict]` — línea 195
- **Qué hace:** lee la hoja `CARTERA` y devuelve `{factura: datos}`. Es la **columna vertebral** del Generador A.
- **Cómo funciona:** abre con `read_only=True, data_only=True`; si no existe la hoja `CARTERA` lanza `ValueError` con mensaje claro; **descarta las filas 0 y 1** (fila 0 = banner con totales de entidad, fila 1 = encabezado real) e itera desde la fila 2. Mapea 18 campos por posición usando las constantes `CA_*`.
- **Por qué existe:** CARTERA es la única fuente con **valores a nivel factura** (valor de factura, saldo, estado, edades) sin repetición por línea. Es la única que se puede sumar directamente.
- **Punto crítico:** el descarte de la fila 0 evita un **doble conteo de toda la cartera**, porque ese banner contiene los totales.
- **Depende de ella:** `construir`, `calcular_cruces`.

#### 3.A.9 `cargar_recepcion(ruta) -> dict[str, list[dict]]` — línea 232
- **Qué hace:** lee el export `RECEPCION DE OBJECIONES` (la glosa que puso la EPS) y lo indexa **por consecutivo de recepción**.
- **Cómo funciona:** lee la primera hoja del libro; salta filas con menos columnas de las esperadas (`len(r) <= RE_MOTIVO`); normaliza la factura y agrupa en un `defaultdict(list)` por `RE_CONSECUTIVO` (col 13). Extrae 11 campos, entre ellos el **motivo EPS en texto libre** (col 33).
- **Por qué existe:** **es la única fuente del motivo exacto de la EPS.** Su descubrimiento cambió el diseño del módulo (ver §3.A.9-bis).
- **Por qué se indexa por consecutivo y no por factura:** porque el cruce con la respuesta se hace por consecutivo (`TRAMITE.col20 = RECEPCION.col13`), que es una clave mucho más precisa que la factura.

> **§3.A.9-bis — HALLAZGO CRÍTICO DEL DESARROLLO.**
> Un agente de análisis automático había reportado que este archivo era un *"placeholder de 1 fila con encabezado 'a', sin datos"* y el diseño inicial **lo descartaba como fuente**. Al re-inspeccionarlo manualmente con `openpyxl` se comprobó que el reporte era **falso**: el archivo tiene **18.371 filas de datos, 34 columnas y 3.933 facturas**, y la columna 33 (motivo EPS) está poblada en **18.371 de 18.371 filas (100 %)**.
> **Impacto:** de haber aceptado el reporte, el bloque "motivo exacto de la glosa" — un requisito explícito del usuario — habría quedado vacío en todo el universo. **Lección para el equipo: verificar siempre contra el archivo, nunca contra un resumen.**

#### 3.A.10 `cargar_tramite(ruta) -> list[dict]` — línea 267
- **Qué hace:** lee el export `TRAMITE DE OBJECION` (la respuesta del HUS). Una entrada por línea de respuesta.
- **Cómo funciona:** lee la primera hoja, salta filas cortas, normaliza factura, y **deriva** `objetado = max(glosado - aceptado, 0.0)`.
- **Por qué existe:** contiene el **argumento técnico del ESE HUS** (col 32, textos tipo `"604- ESE HUS ACEPTA OBJECION"` / `"208 ESE HUS NO ACEPTA GLOSA…"`), el valor aceptado (col 24) y el radicado de respuesta (col 11).
- **Decisión técnica:** `objetado` **no existe como columna** en el export; se deriva. Se acota con `max(..., 0.0)` para que un aceptado mayor que el glosado (dato sucio) no produzca un negativo que contamine los totales — esa anomalía se reporta aparte en el cruce #7.
- **Trampa documentada en el código:** las columnas 25/27 traen el **concepto original de la glosa**; las 28/29 traen el código de *"respuesta a glosa"* (997). Usar 28/29 como concepto de glosa sería un error de lectura.

#### 3.A.11 `cargar_cruce_actas(ruta) -> list[dict]` — línea 307
- **Qué hace:** lee la hoja `CRUCE ACTAS` del mismo libro de cartera. Una entrada por par **FACTURA+ACTA**.
- **Cómo funciona:** si la hoja no existe devuelve `[]` (degradación elegante). Descarta fila 0 (título) y fila 1 (encabezado). **Descarta las filas sin factura o sin acta** — así elimina automáticamente la fila de totales del final. Marca `duplicada=True` cuando el acta es `AC000639`.
- **Por qué existe:** una factura puede aparecer en varias actas; el resultado de conciliación solo tiene sentido a grano FACTURA+ACTA (1.710 pares reales).
- **Punto crítico:** el flag `duplicada` implementa el hallazgo de que **`AC000639` es la misma acta que la `SINAC 720`**. Sin excluirla, el levantado se infla.

#### 3.A.12 `_motivo_eps_para(linea_tr, rec_por_cons) -> (motivo, cups, servicio)` — línea 342
- **Qué hace:** encuentra el motivo EPS que corresponde a una línea concreta de respuesta.
- **Cómo funciona:** estrategia en cascada de tres niveles:
  1. **Match exacto:** dentro del consecutivo, líneas con el mismo código de glosa **y** el mismo valor redondeado. Si hay exactamente una → se usa.
  2. **Match por código:** si hay exactamente una línea con ese código → se usa.
  3. **Ambiguo:** se concatenan los motivos *distintos* del consecutivo con `" | "`, recortado a 900 caracteres, y se devuelve `servicio=""`.
- **Por qué existe:** una recepción puede tener varias líneas y el trámite no conserva un identificador de línea. Sin esta cascada, habría que elegir arbitrariamente un motivo — es decir, **inventar**.
- **Decisión técnica clave:** en el caso ambiguo **no se adivina**: se muestran todos los motivos reales del consecutivo. El auditor ve la verdad completa aunque sea menos precisa. El recorte a 900 caracteres evita romper el límite de celda de Excel (32.767 caracteres) y mantener la celda legible.

#### 3.A.13 `construir_glosas(tramite, rec_por_cons) -> list[dict]` — línea 366
- **Qué hace:** **la función central del módulo.** Produce la lista donde cada glosa lleva su respuesta al lado.
- **Cómo funciona:** dos pasadas.
  1. Recorre el trámite; por cada línea llama a `_motivo_eps_para`, marca `estado_respuesta = "RESPONDIDA"` si hay radicado, fecha o argumento, y etiqueta `origen="TRAMITE"`. Acumula los consecutivos respondidos en un `set`.
  2. Recorre la recepción y, para **todo consecutivo que no aparezca en ese set**, emite la glosa con `estado_respuesta="SIN RESPUESTA"`, `valor_aceptado=0.0`, `valor_objetado = valor glosado` y `origen="RECEPCION"`.
- **Por qué existe:** unir ambos mundos en una sola fila es literalmente el requisito del usuario (*"junto a cada una, la respuesta que enviamos, el motivo de la EPS, el estado actual"*).
- **Por qué la segunda pasada:** **sin ella, las glosas sin responder serían invisibles.** Un expediente que solo muestra lo respondido oculta precisamente el riesgo (glosas que vencen sin respuesta). Detectó **179 glosas sin respuesta** en el universo completo.
- **Cubierta por:** `test_construir_expediente_completo` (verifica ambos caminos).

#### 3.A.14 `agregar_por_factura(glosas) -> dict[str, dict]` — línea 425
- **Qué hace:** agrega el detalle a nivel factura.
- **Cómo funciona:** `defaultdict` con `num_glosas`, `glosado`, `aceptado`, `objetado`, `sin_respuesta`, `fecha_factura` (primera no nula) y `tipos` (un `set`).
- **Por qué existe:** la hoja maestra tiene **una fila por factura**; sus valores de glosa deben ser la **suma de las líneas**, nunca el valor repetido a nivel factura.

#### 3.A.15 `fecha_factura_por_factura(tramite, rec_por_cons) -> dict` — línea 454
- **Qué hace:** devuelve `{factura: fecha_de_factura}`.
- **Cómo funciona:** primero recorre el trámite (col 15), luego completa con la recepción (col 17); en ambos casos toma la primera fecha válida por factura.
- **Por qué existe:** **CARTERA no trae fecha de factura, solo fecha de radicado.** Sin este rescate, el período `AAAAMM` de las rutas de soportes saldría del radicado, que puede caer en otro mes.

#### 3.A.16 `contrato_cod_por_factura(tramite) -> dict` — línea 470
- **Qué hace:** `{factura: código interno de contrato}` (ej. `U22031`).
- **Por qué existe:** alimenta la trazabilidad de `contrato_por_fecha`, que muestra el código crudo junto al contrato deducido.

#### 3.A.17 `resultado_final(cart, agg) -> str` — línea 481
- **Qué hace:** deriva el estado de la factura de cara a la conciliación.
- **Cómo funciona:** cascada de reglas por precedencia:
  1. Sin glosas y sin `valor_glosa` → `"SIN GLOSA"`.
  2. Solo levantado (`lev>0`, `rat==0`, `ace==0`) → `"LEVANTADA (a favor HUS)"`.
  3. Solo ratificado → `"RATIFICADA (pdte conciliar)"`.
  4. Mezcla de valores en actas → `"CONCILIADA PARCIAL"`.
  5. Todas las glosas sin respuesta → `"SIN RESPUESTA"`.
  6. Respaldo por texto de `ESTADO GLOSA` de cartera (busca `LEVANTADA`/`RATIFICADA`/`CONCILIADA` como subcadena).
  7. Por defecto → `"EN TRAMITE"`.
- **Por qué existe:** el auditor necesita ver de un vistazo, y a color, en qué punto está cada factura.
- **Decisión técnica:** se combinan **valores** (precisos) y **texto de estado** (respaldo) en ese orden, porque los valores son verificables aritméticamente y el texto es libre.

#### 3.A.18 `calcular_cruces(cartera, agg, glosas, cruce_actas) -> list[dict]` — línea 507
- **Qué hace:** ejecuta los **11 controles de consistencia**. Devuelve `{n, nombre, cantidad, muestra}` por control (muestra = primeras 15 facturas ordenadas).
- **Los 11 controles:**

| # | Control | Lógica |
|---|---|---|
| 1 | Facturas SIN glosa | Anti-join CARTERA vs detalle **y** `valor_glosa == 0` |
| 2 | Facturas con glosa sin respuesta | `estado_respuesta == "SIN RESPUESTA"` |
| 3 | Glosas cuya factura no está en cartera | Anti-join inverso |
| 4 | Facturas sin período para ubicar soportes | `_aaaamm` vacío |
| 5 | Diferencia cartera vs detalle | `abs(valor_glosa − Σ glosado) > 1` |
| 6 | Respuesta que no cubre el 100 % | `abs(glosado − (aceptado + objetado)) > 1` |
| 7 | Aceptado > glosado | Inconsistencia aritmética |
| 8 | Facturas duplicadas en la maestra | Siempre 0 (CARTERA garantiza unicidad) — control testigo |
| 9 | Pagos no aplicados | Levantada/conciliada pero `saldo_dgh > 1` |
| 10 | Facturas en actas que no están en cartera | Fuga entre conciliación y cartera |
| 11 | Aritmética de actas | `glosa_inicial ≠ aceptada+levantada+ratificada` (excluye `AC000639`) |

- **Decisión técnica:** las tolerancias son de **$1**, no de $0, para absorber redondeos de punto flotante sin ocultar diferencias reales.
- **Por qué el control 8 existe si siempre da 0:** es un **testigo**. Si algún día da distinto de 0, significa que la espina dejó de ser única y el modelo está roto.

#### 3.A.19 `_escribir_workbook(salida, maestra, glosas, actas, cruces, dash)` — línea 604
- **Qué hace:** escribe el libro de 5 hojas con toda la presentación.
- **Hojas:** `00_DASHBOARD`, `01_MAESTRA` (32 columnas), `02_GLOSAS` (16 columnas), `03_ACTAS` (9 columnas), `04_CRUCES` (4 columnas).
- **Presentación:** encabezado azul `1F4E78` con texto blanco y ajuste de línea; `freeze_panes` bajo el encabezado; `auto_filter` en todas las hojas; formato de moneda `#,##0`; semáforo por resultado (verde `C6EFCE` levantada, naranja `FCE4D6` ratificada, azul `DDEBF7` conciliada parcial, rojo `FFC7CE` sin respuesta, amarillo `FFF2CC` en trámite, gris `F2F2F2` sin glosa); hipervínculo de navegación maestra → detalle.
- **Dos optimizaciones críticas de rendimiento** (ver §13.2 y §13.3): estilos izados fuera de los bucles y contador propio de fila en lugar de `ws.max_row`.

#### 3.A.20 `construir(cartera_p, recepcion_p, tramite_p, salida) -> dict` — línea 902
- **Qué hace:** orquesta todo el proceso y devuelve el resumen de ejecución.
- **Cómo funciona:** carga las 4 fuentes → `construir_glosas` → `agregar_por_factura` → rescata fechas y contratos → arma las filas de la maestra recorriendo la espina ordenada → `calcular_cruces` → calcula el dashboard → `_escribir_workbook`.
- **Decisión técnica corregida durante el desarrollo:** los totales de conciliación (levantado, ratificado, aceptado en actas, a pagar) se toman del **detalle de `CRUCE ACTAS` excluyendo la duplicada**, **no** de las columnas resumen de CARTERA. Motivo: las columnas resumen de CARTERA **sub-cuentan la ratificada** (daban $691.881.200 / $295.521.200 frente a los valores verificados $707.499.754 / $980.141.374). Está documentado en un comentario dentro del propio código.
- **Devuelve:** `facturas_maestra`, `facturas_con_glosa`, `glosas`, `glosas_sin_respuesta`, `actas_filas`, totales y el diccionario `cruces`.

#### 3.A.21 `main(argv) -> int` — línea 1038
- **Qué hace:** CLI con `argparse`. Argumentos: `--cartera` (obligatorio), `--recepcion`, `--tramite`, `--salida` (obligatorio).
- **Manejo de errores:** captura `OSError` y `ValueError`, registra el error y devuelve código de salida `1`. Éxito → `0`.
- **Registra:** conteos y las 5 cifras económicas formateadas con separador de miles.

### 3.B — GENERADOR B (VIGENTE): `generar_acta_147.py` (541 líneas)

#### 3.B.1 `norm(pref, fac)` — línea 50
- **Qué hace:** igual que `normalizar_factura` pero acepta **prefijo y número por separado**.
- **Por qué existe:** `HUS.xlsx` (el lote) guarda el prefijo en la col 8 y el número en la col 9. Es el único archivo con ese diseño.

#### 3.B.2 `num(x)`, `txt(x)` — líneas 58, 78
- Idénticas en comportamiento a `_num`/`_txt` del Generador A (incluida la regla de puntos múltiples).
- **Nota de deuda técnica:** están duplicadas. Al promover el generador a `tools/`, deben importarse del módulo común (ver §16.3).

#### 3.B.3 `cod_corto(c)` — línea 85
- **Qué hace:** extrae el código corto de glosa de un texto largo.
- **Cómo funciona:** regex `([A-Z]{2}\s?\d{2}\s?\d{2}|[A-Z]{2}\d{2}|[A-Z]{2}\s?\d+)` sobre el texto en mayúsculas; si no casa, devuelve la primera palabra.
- **Por qué existe:** el lote trae el código embebido en la descripción (`"CO46 01 COBERTURA-COBERTURA SIN AG…"`). El acta necesita solo `CO4601`.

#### 3.B.4 `familia_de(cod)` — línea 90
- **Qué hace:** mapea el prefijo de dos letras a `(TIPIFICACIÓN, TIPO DE GLOSA)`.
- **Tabla:** `TA`→(TARIFAS, ADMINISTRATIVA) · `SO`→(SOPORTES, ADMINISTRATIVA) · `AU`→(AUTORIZACION, ADMINISTRATIVA) · `FA`→(FACTURACION, ADMINISTRATIVA) · `CO`→(COBERTURA, ADMINISTRATIVA) · `CL`→(CALIDAD / PERTINENCIA, MEDICA) · `PE`→(PERTINENCIA, MEDICA). Desconocido → `(OTRA, ADMINISTRATIVA)`.
- **Por qué existe:** el acta SINAC exige las columnas `TIPO DE GLOSA (ADM-MIX-MED)` y `TIPIFICACION`, que no vienen en el lote pero se deducen del código.

#### 3.B.5 `centro_costo(f, valor)` — línea 191
- **Qué hace:** devuelve el centro de costo real de la línea glosada.
- **Cómo funciona:** cascada análoga a `_motivo_eps_para`:
  1. Match por `(factura, valor redondeado)` — si hay un único centro, se usa.
  2. Si la factura tiene un solo centro en toda la recepción, se usa ese.
  3. Si es ambiguo, se listan **todos los centros reales** de la factura separados por `" / "`.
  4. Si no hay dato, cadena vacía.
- **Por qué existe:** el acta SINAC pide `CENTRO DE COSTO`, dato que **no está en el lote ni en cartera**, pero **sí** en la columna 32 del export de recepción (`ServicioProductoFactura.CentroCosto.CodigoNombreCentro`).
- **Resultado:** cobertura del **100 % (444 de 444 líneas)**. Ejemplos reales: `733001 - QUIROFANOS` (208 líneas), `732501 - QUEMADOS` (129), `732109 - UCI ADULTOS - MEDICAS` (66).

#### 3.B.6 `rellenar_cruda(nombre, filas, col_factura, header_keep)` — línea 485
- **Qué hace:** vacía una hoja de soporte y la rellena con las filas del export cuya factura pertenezca a las 147.
- **Cómo funciona:** `delete_rows` desde `header_keep+1`, luego `append` de las filas filtradas; devuelve el conteo.
- **Por qué existe:** el acta SINAC lleva sus soportes crudos (hojas `GLOSAS` y `TRAMITES`) como respaldo probatorio, igual que el acta 720 original.
- **Resultado:** 893 filas en cada hoja.

#### 3.B.7 Bloque de inserción sobre plantilla (líneas 240–275) — *no es función, es la maniobra central*
- **Qué hace:** expande la tabla del acta de 11 filas de datos a **444**, conservando todo el formato.
- **Cómo funciona, paso a paso:**
  1. Calcula `extra = 444 − 11 = 433`.
  2. **Guarda y desarma** todos los rangos combinados que estén por debajo del punto de inserción.
  3. **Guarda** las alturas de fila de esa zona.
  4. `ws.insert_rows(INS_AT, 433)`.
  5. **Rehace los merges** desplazados `+433`.
  6. **Restaura las alturas** desplazadas `+433`.
  7. Copia el estilo de la fila 12 (`cell._style = copy(base[c]._style)`) a las 443 filas nuevas, columnas C..AL.
- **Por qué existe:** `openpyxl.insert_rows` **no desplaza los rangos combinados ni las alturas de fila**. Sin los pasos 2/3/5/6, la zona de firmas del acta queda destrozada.
- **Decisión técnica:** se copia `_style` (el objeto de estilo completo) en vez de asignar fuente/borde/relleno uno a uno — es más fiel y mucho más rápido.

### 3.C — FUNCIONES DE PRUEBA: `tests/test_tools/test_hoja_maestra_conciliacion.py`

| Test | Qué verifica |
|---|---|
| `test_normalizar_factura` | Las 4 formas de entrada → `HUS0000316347`; `None` → `""` |
| `test_num_formato_colombiano` | `"$ 3.211.891"`→3211891.0 · `"1605989"`→1605989.0 · `"1.234,56"`→1234.56 · `None`/`"-"`→0.0 |
| `test_contrato_por_fecha` | jun-2025→`287…` · ene-2026→`440…` · sin datos→`PENDIENTE` |
| `test_construir_expediente_completo` | Flujo completo sobre fixtures que **imitan las tres fuentes reales** (incluidos banner, encabezado y fila de totales): maestra con 1 fila/factura, motivo EPS y argumento **en la misma fila**, glosa sin respuesta detectada, factura sin glosa marcada, cruce #1 = 1, orden exacto de las 5 hojas |

Funciones auxiliares de fixture: `_fila(n, pares)` (construye filas dispersas), `_cartera`, `_recepcion`, `_tramite`.

**Decisión de diseño de las pruebas:** los fixtures reproducen las **anomalías reales** de los archivos (fila banner en CARTERA, título + encabezado + fila de totales en CRUCE ACTAS). Si alguien "simplifica" los lectores quitando esos descartes, los tests fallan.

---

## 4. FLUJO COMPLETO

### 4.1 Flujo del Generador B (el vigente) — de la orden al acta firmable

**Paso 0 — Disparador.** No hay clic: el auditor ejecuta en consola:

```bat
py generar_acta_147.py "D:\ruta\ACTA_CONCILIACION_147_DISPENSARIO.xlsm"
```

**Paso 1 — Carga del lote (universo).** Se lee `HUS.xlsx` hoja `Hoja1`, 59 columnas. Por cada fila se normaliza `PREFIJO(col8) + FACTURA(col9)` y se extraen 20 campos. **Aserción dura:**

```python
assert len(facs) == 147 and len(glosas) == 444
```

Si el lote cambia, el proceso **se detiene**. Es deliberado: el universo está aprobado por el usuario y no puede variar en silencio.

**Paso 2 — Rescate de fechas.** Se recorre `TRAMITE` (col 15 fecha factura, col 3 fecha objeción) y luego `RECEPCION` (col 17, col 20) tomando la primera fecha válida por factura. El lote solo trae fecha de atención y de radicación.

**Paso 3 — Carga del estado de cartera JUN 2026.** De `ARCH CON CRUCES JUN`: `VLR ACEPTADO` (col 21) por factura, tomando el máximo, y `ABOGADO ASIGNADOS` (col 25) descartando `#N/A`.

**Paso 4 — Índice de centros de costo.** De `RECEPCION` col 32 se construye un doble índice: `cc_por_fac[factura][valor] = {centros}` y `cc_todos[factura] = {centros}`.

**Paso 5 — Cartera y actas previas.** De la hoja `CARTERA` se toman saldo, valor de glosa y estado. De `CRUCE ACTAS` se arma, por factura, el texto legible del resultado: `"AR002328: RATIFICADA $32.563.634"`.

**Paso 6 — Ordenamiento.** Se suma el valor objetado por factura, se ordenan las facturas **de mayor a menor valor glosado**, y las 444 glosas se ordenan por `(posición de su factura, −valor objetado)`.
**Por qué:** en la mesa se negocia primero lo que más pesa, y las glosas de una misma factura deben quedar **físicamente contiguas** (requisito del usuario).

**Paso 7 — Apertura de la plantilla.** `load_workbook(TPL, keep_vba=True)`. **`keep_vba=True` es obligatorio**: sin él se pierden las macros del acta.

**Paso 8 — Expansión de la tabla.** La maniobra de 7 pasos descrita en §3.B.7. La tabla pasa de las filas 12–22 a **12–455**; la fila TOTAL pasa de 23 a **456**; las firmas se desplazan `+433` (de 38/47 a 471/480).

**Paso 9 — Columnas de apoyo.** Se crean 7 encabezados nuevos en `AM11..AS11`, copiando el estilo del encabezado `I11`: ESTADO RESPUESTA · RESULTADO EN ACTAS PREVIAS · SOPORTE ENTREGA ESM · DIFERENCIA VS CARTERA · RUTA SOPORTES · RUTA FACTURA ELECTRONICA · LISTA PARA CONCILIAR.

**Paso 10 — Volcado de las 444 filas.** Por cada glosa se escribe:

| Col | Contenido | Origen |
|---|---|---|
| C | Consecutivo 1..444 | Generado |
| D | Acta de respuesta / radicado | Lote col 27 / col 7 |
| E | Factura | Normalizada |
| F | Fecha factura | Trámite/recepción, o atención |
| G | Tipo (ADM/MED) | `familia_de` |
| H | Tipificación | `familia_de` |
| I | Código corto | `cod_corto(col18)` |
| J | **Motivo exacto EPS** | Lote col 19 |
| K | Valor factura | Lote col 16 |
| L | **Valor glosa inicial** | Lote col 20 |
| M | **Valor pendiente por conciliar** | Lote col 25 (ratificado) |
| N,O,P,Q | Acepta IPS · Levanta entidad · Ratificado · Descripción | **Vacías: se diligencian EN la mesa** |
| S | Abogado asignado | Estado de cartera col 25 |
| T | Valor aceptado en trámite | Estado de cartera col 21 (primera fila de cada factura) |
| U | Centro de costo | `centro_costo()` |
| V | Cuenta contable | `"PENDIENTE"` (no existe en ninguna fuente) |
| Z | Diferencia | **Fórmula** `=L{r}-N{r}` |
| AA, AB | Fecha radicación · Fecha objeción | Lote col 11 · trámite/recepción |
| AC | **Respuesta del HUS a la glosa** | Lote col 32 |
| AM..AS | Columnas de apoyo | Derivadas |

**Regla anti-duplicación en T, AN, AP y AS:** esos valores son de **nivel factura**. Se escriben **solo en la primera fila de cada factura** (`first_of_fac`). Así la suma de la columna cuadra sin duplicar. Verificado: `T456 = $1.758.956` exacto.

**Paso 11 — Fila TOTAL (456).** Se reescriben las fórmulas al rango nuevo: `=SUM(L12:L455)` en L, M, N, O, T, W, Z; `U456 = "-"`. En K se usa una fórmula especial que suma el valor de factura **una sola vez por factura**:

```excel
=SUMPRODUCT((E12:E455<>E11:E454)*K12:K455)
```

Compara cada factura con la de la fila anterior y solo suma cuando cambia. Funciona porque las facturas están agrupadas (paso 6). Resultado verificado: **$1.267.976.805**.

**Paso 12 — Encabezado del acta.** `K9` cuenta facturas distintas con `=SUMPRODUCT((E12:E455<>E11:E454)*1)` → **147**. `M9/P9/R9/T9/W9` apuntan a la fila TOTAL. `R7` (fecha) y `V7` (número de acta) quedan en `"POR DEFINIR"` / `"POR ASIGNAR"` — los asigna la entidad.

**Paso 13 — DASHBOARD.** Se inserta como **primera hoja** con los 12 indicadores, todos como **fórmulas vivas** sobre la hoja ACTA. Se ocultan las líneas de cuadrícula.

**Paso 14 — Hojas de soporte.** `GLOSAS` y `TRAMITES` se rellenan con los exports filtrados (893 filas cada una) y se les reemplaza el encabezado por el del export real, para que columna y dato coincidan siempre. `NOTAS` queda solo con encabezado.

**Paso 15 — Acotado del formato condicional.** Se reescriben los rangos de formato condicional de columna completa a rangos reales (ver §13.4).

**Paso 16 — Guardado y recálculo.** `wb.save(OUT)` y luego, en desarrollo, `recalc.py` con LibreOffice: **471 fórmulas, 0 errores**.

**Paso 17 — Uso en la mesa (el "clic" del usuario).**
1. Abre el `.xlsm` — ve el **DASHBOARD** primero.
2. Pasa a **ACTA** y filtra por factura o recorre de mayor a menor valor.
3. Al llegar a una factura ve **todas sus glosas contiguas**, cada una con motivo EPS (J), nuestra respuesta (AC), valor glosado (L), pendiente (M), estado (AM), resultado en actas previas (AN) y rutas (AQ/AR, con hipervínculo a la factura electrónica).
4. Negocia y escribe en **N, O, P, Q**.
5. La columna **Z** calcula la diferencia sola; la fila **456** y el **DASHBOARD** se actualizan solos.
6. Firma sobre el bloque original del acta (filas 471 y 480).

### 4.2 Flujo del Generador A (cartera completa)

```bat
py tools\hoja_maestra_conciliacion.py ^
   --cartera "…CORTE_30062026_CRUCE_ACTAS.xlsx" ^
   --recepcion "…RECEPCION_DE_OBJECIONES_DISPENSARIO_MEDICO.xlsx" ^
   --tramite "…TRAMITE_DE_OBJECCION_DISPENSARIO_MEDICO.xlsx" ^
   --salida "EXPEDIENTE_CONCILIACION_DISPENSARIO.xlsx"
```

`main` → `construir` → 4 lectores → `construir_glosas` → `agregar_por_factura` → rescate de fechas/contratos → filas de la maestra → `calcular_cruces` → dashboard → `_escribir_workbook` → resumen por consola. **Tiempo de ejecución medido: ~30 s** para 5.571 facturas / 18.378 glosas / 3,5 MB de salida.

---

## 5. BASE DE DATOS

**Este módulo no utiliza base de datos.** No hay tablas, columnas SQL, relaciones, índices ni migraciones que documentar. La afirmación es categórica y verificable: el módulo no importa ningún cliente de base de datos y su única dependencia funcional es `openpyxl`.

### 5.1 Por qué no hay base de datos (decisión de arquitectura)

1. Las fuentes son **exports que el auditor descarga a mano** de SIMED y DGH; no hay acceso directo a esos motores.
2. El entregable debe **abrirse en Excel sin servidor** y llevarse a una mesa de conciliación.
3. El repositorio ya tiene un `docs/MIGRACION_SQLITE.md` para la plataforma web; este módulo se mantuvo deliberadamente **fuera** de esa capa para no acoplarlo.

### 5.2 Equivalente funcional: la capa de datos son los archivos

| "Tabla" (archivo/hoja) | Grano | Filas reales | Clave |
|---|---|---|---|
| `CARTERA` | 1 por factura | 5.571 | `FACTURA` |
| `CRRPSEGUIMIENTORECEPCIONOBJECIO` | 1 por línea de glosa recibida | 18.371 | `Consecutivo` (col 13) |
| `CRRPSEGUIMIENTOTRAMITEOBJECION` | 1 por línea de respuesta | 18.199 | `RecepcionObjecion.Consecutivo` (col 20) |
| `CRUCE ACTAS` | 1 por FACTURA+ACTA | 1.710 | `FACTURA` + `ACTA` |
| `ACTAS DE GLOSAS` | 1 por acta | 13 | `ACTA` |
| `HUS.xlsx / Hoja1` (lote) | 1 por glosa del lote | 444 | `PREFIJO`+`FACTURA` |
| `ARCH CON CRUCES JUN` | 1 por factura | 5.571+ | `FACTURA` (col 6) |

### 5.3 Relaciones (el modelo relacional implícito)

```
CARTERA (1) ──< RECEPCION (N)          por FACTURA normalizada
RECEPCION (1) ──< TRAMITE (N)          por Consecutivo  ← LA RELACIÓN CLAVE
CARTERA (1) ──< CRUCE ACTAS (N)        por FACTURA (una factura, varias actas)
CARTERA (1) ──── ESTADO CARTERA (1)    por FACTURA
LOTE HUS (147) ⊂ CARTERA (5.571)       146 de 147 (falta HUS0000443525)
```

**Integridad de la relación clave, medida:** `TRAMITE.col20 ∩ RECEPCION.col13` = **4.063 de 4.066** consecutivos (99,93 %). Facturas en recepción sin trámite: **136**. En trámite sin recepción: **2**.

### 5.4 "Índices"

Se construyen en memoria en cada ejecución, todos como `dict`/`defaultdict` de acceso O(1):

- `cargar_cartera` → índice por factura.
- `cargar_recepcion` → índice por consecutivo (`defaultdict(list)`).
- `cc_por_fac` / `cc_todos` → doble índice de centros de costo.
- `acep_cartera` / `abogado` → índices por factura del estado de cartera.

### 5.5 Datos necesarios para operar

Cinco archivos. Sin los tres primeros el proceso no arranca:

1. `DISPENSARIO_MEDICO_CORTE_30062026_CRUCE_ACTAS.xlsx` (hojas `CARTERA`, `ACTAS DE GLOSAS`, `CRUCE ACTAS`).
2. `RECEPCION_DE_OBJECIONES_DISPENSARIO_MEDICO.xlsx`.
3. `TRAMITE_DE_OBJECCION_DISPENSARIO_MEDICO.xlsx`.
4. `HUS.xlsx` — el lote de 147 (**solo Generador B**).
5. `Copia_de_Estado_Cartera_JUN_2026_Con_Cruces.xlsx` (**solo Generador B**).
6. `ACTA_SINAC_N_720__ESE_HUS__DISPENSARIO_MEDICO.xlsm` — plantilla (**solo Generador B**).

---

## 6. BACKEND

**Este módulo no tiene backend HTTP.** No expone endpoints, no tiene controladores, ni middleware, ni sistema de permisos, ni autenticación. Es un proceso batch de línea de comandos.

### 6.1 Equivalente funcional: la interfaz CLI

**Generador A** (`argparse`):

| Argumento | Obligatorio | Tipo | Descripción |
|---|---|---|---|
| `--cartera` | Sí | `Path` | Libro con hojas CARTERA + CRUCE ACTAS |
| `--recepcion` | No (`None`) | `Path` | Export de recepción (glosa/motivo EPS) |
| `--tramite` | No (`None`) | `Path` | Export de trámite (nuestra respuesta) |
| `--salida` | Sí | `Path` | Ruta del `.xlsx` de salida |

**Generador B:** un único argumento posicional opcional (`sys.argv[1]`) con la ruta de salida; si falta usa una ruta por defecto.

### 6.2 "Servicios" (capa lógica)

| Servicio | Función | Responsabilidad |
|---|---|---|
| Normalización | `normalizar_factura`, `_num`, `_txt`, `_fecha` | Sanear datos de entrada |
| Carga | `cargar_*` | Leer y estructurar fuentes |
| Cruce | `construir_glosas`, `_motivo_eps_para` | Unir glosa ↔ respuesta |
| Agregación | `agregar_por_factura` | Bajar de línea a factura |
| Reglas de negocio | `resultado_final`, `contrato_por_fecha`, `familia_de` | Derivar estado y clasificación |
| Auditoría | `calcular_cruces` | 11 controles |
| Presentación | `_escribir_workbook` | Generar el entregable |
| Orquestación | `construir`, `main` | Coordinar y reportar |

### 6.3 Validaciones

**De entrada:**
- Hoja `CARTERA` ausente → `ValueError` con mensaje explícito.
- Hoja `CRUCE ACTAS` ausente → devuelve `[]` (degradación elegante, no falla).
- Filas con menos columnas de las esperadas → se saltan.
- Filas sin factura o sin acta → se descartan (elimina las filas de totales).
- Filas banner/encabezado → descarte posicional explícito.
- **Generador B:** `assert len(facs) == 147 and len(glosas) == 444` — detiene el proceso si el universo cambió.

**De salida (los 11 cruces):** ver §3.A.18. No bloquean la generación; se reportan en la hoja `04_CRUCES` para que el auditor decida.

### 6.4 Manejo de errores

| Situación | Comportamiento | Justificación |
|---|---|---|
| Valor no numérico | `_num` → `0.0` | Un dato sucio no debe tumbar el proceso |
| Fecha ilegible | `_fecha` → `None`; período → `"PENDIENTE"` | Se marca, no se inventa |
| Motivo EPS ambiguo | Se concatenan los reales | Nunca se elige uno arbitrario |
| Dato inexistente en toda fuente | `"PENDIENTE"` / `"PENDIENTE VERIFICAR"` | **Jamás en blanco**, que se confundiría con "no" |
| Factura fuera de cartera | `"NO ESTA EN CARTERA"` visible | Es un hallazgo, no un error |
| `OSError` / `ValueError` en `main` | `logger.error` + `return 1` | Código de salida usable en scripts |

### 6.5 Permisos

No hay modelo de permisos en el módulo. La seguridad es **del sistema de archivos**: quien puede leer los exports y escribir la salida, puede ejecutarlo. El acceso a `Y:\`, `X:\` y `\\172.16.32.83\` depende de las credenciales de red del usuario de Windows.

---

## 7. FRONTEND

**No hay frontend web.** No hay pantallas HTML, componentes, modales ni animaciones. **La interfaz de usuario es el libro Excel**, y fue diseñada con el mismo rigor que una UI.

### 7.1 "Pantallas" (hojas del Generador B — el entregable vigente)

**Pantalla 1 — `DASHBOARD`** (primera hoja, la que se ve al abrir)
- Título `B2`, subtítulo `B3` con el alcance y las advertencias.
- Tabla de 12 indicadores: etiqueta combinada `B:D`, valor en `E`.
- Todos los valores son **fórmulas vivas**; al diligenciar la mesa, el tablero se actualiza solo.
- Cuadrícula oculta (`showGridLines = False`).
- Nota al pie (`B19:B20`) indicando qué columnas se llenan en la mesa.

**Pantalla 2 — `ACTA`** (la pantalla de trabajo)
- Bloque superior institucional intacto (logos, NIT, razón social, fecha, número de acta).
- Fila 9: resumen (cantidad de facturas, valor a conciliar, acepta IPS, levanta EPS, a refacturar).
- Encabezado de tabla en fila 11, alto 128 px, texto blanco sobre azul.
- 444 filas de datos (12–455), alto uniforme 21,75.
- Fila TOTAL (456) con fórmulas.
- Bloque de observaciones legales y zona de firmas.

**Pantalla 3 — `GLOSAS`** · **Pantalla 4 — `TRAMITES`**: soportes crudos (893 filas c/u).
**Pantalla 5 — `NOTAS`**: solo encabezado (no hay notas crédito en este lote).

### 7.2 "Componentes" reutilizables (Generador A)

| Componente | Implementación | Función |
|---|---|---|
| `estilizar_encabezado(ws, ncols, fila)` | Relleno azul + fuente blanca + `wrap_text` + `freeze_panes` + `auto_filter` + alto 30 | Encabezado uniforme en las 4 hojas tabulares |
| `anchos(ws, mapa)` | `column_dimensions[letra].width` | Anchos por hoja |
| Paleta de estados | `dict` de `PatternFill` izados | Semáforo de resultado |

### 7.3 "Formularios" — las celdas de entrada

Las únicas celdas que el usuario diligencia (en la mesa):

| Celda | Campo |
|---|---|
| `N12:N455` | VALOR ACEPTA IPS |
| `O12:O455` | VALOR LEVANTA ENTIDAD |
| `P12:P455` | VALOR RATIFICADO |
| `Q12:Q455` | DESCRIPCIÓN DE CONCILIACIÓN |
| `R7` | Fecha de conciliación |
| `V7` | Número de acta |

Están **declaradas explícitamente en el DASHBOARD** (`B19:B20`) para que nadie escriba sobre una columna calculada.

### 7.4 "Tablas"

Todas las hojas tabulares llevan `auto_filter` en el encabezado y `freeze_panes` debajo, de modo que el auditor puede filtrar por factura, por estado o por acta sin perder los títulos. **En el Generador B no se aplicó `auto_filter` a la hoja ACTA**: el acta es un documento formal que se firma, y un autofiltro alteraría su presentación oficial.

### 7.5 "Botones" y navegación

- **Generador A:** columna `VER GLOSAS` con hipervínculo interno `#'02_GLOSAS'!A1`, texto azul subrayado.
- **Generador B:** columna `AR` (RUTA FACTURA ELECTRONICA) con **hipervínculo real** a la ruta UNC `\\172.16.32.83\factura_electronica_net22\AAAAMM`; un clic abre la carpeta del mes.
- No hay navegación entre hojas en el Generador B **por diseño**: el requisito era *"abrir una factura y ver inmediatamente toda su historia, sin tener que buscar en otras hojas"*. Todo está en la hoja ACTA.

### 7.6 "Animaciones" y formato condicional

No hay animaciones (Excel no las tiene). El equivalente es el **formato condicional y el color**:

- Generador A: semáforo de 6 colores por resultado; rojo en glosas sin respuesta; gris en el acta duplicada; ámbar en cruces con hallazgos.
- Generador B: se **heredan** las 2 reglas de formato condicional de la plantilla original (columnas Z y W), acotadas a los rangos reales.

### 7.7 Requisitos de UI que no se pudieron cumplir con openpyxl

Documentado con honestidad ante el usuario **antes** de construir:

| Solicitado | Estado | Motivo |
|---|---|---|
| Colores / iconos | ✅ Entregado | `PatternFill` |
| Filtros | ✅ Entregado | `auto_filter` |
| Formato condicional | ✅ Entregado | `conditional_formatting` |
| Hipervínculos | ✅ Entregado | `cell.hyperlink` |
| Panel de navegación | ⚠️ Parcial | Se resolvió con hipervínculos y con el diseño "todo en una hoja" |
| **Tablas dinámicas vivas** | ❌ No entregado | `openpyxl` no crea tablas dinámicas. Se sustituyeron por **fórmulas vivas** (`SUMPRODUCT`, `SUMIF`, `COUNTIF`), que se recalculan igual y no requieren refrescar |
| **Listas desplegables** | ❌ No entregado | Se evaluó `DataValidation`; se descartó porque la plantilla original no las usa y habría alterado el formato oficial |

---

## 8. IA

### 8.1 IA en tiempo de ejecución: NINGUNA

**Este módulo no realiza ninguna llamada a un modelo de lenguaje.** No hay prompts, ni proveedores, ni temperatura, ni fallback de modelos en el código entregado. El motor es **100 % determinista**: dadas las mismas entradas produce byte a byte la misma salida.

**Por qué fue una decisión deliberada y no una omisión:**

El requisito operativo permanente del usuario es **"NUNCA inventar evidencia ni datos; si falta, marcar PENDIENTE"**. Un modelo generativo, ante un motivo de glosa ambiguo o un centro de costo faltante, produciría un texto plausible — que en una mesa de conciliación donde se discuten **$317.640.524** es exactamente el fracaso que hay que evitar. Toda la ambigüedad se resuelve con **cascadas deterministas** (`_motivo_eps_para`, `centro_costo`) que, cuando no pueden decidir, **muestran todas las opciones reales** en vez de elegir una.

### 8.2 IA en tiempo de desarrollo: orquestación multiagente

Sí se usó IA **para construir y auditar** el módulo, mediante la herramienta `Workflow` de orquestación multiagente. Quedan dos ejecuciones registradas:

**Ejecución 1 — Diseño del blueprint** (previa, recuperada de `w2lz1w6v4.output`)
- **7 agentes**, ~309.000 tokens, 13,6 minutos.
- **Salida:** `{schemas, blueprint, critica}`. El blueprint definió `joinKey`, `masterColumns`, `granularidad`, 11 `crossChecks`, `soporteRule`, `facturaElectronicaRule`, `dedupStrategy`, 22 `dashboardMetrics` y `pendientes`. La crítica evaluó **64 requisitos, 42 cubiertos**, y listó 14 vacíos.
- **Errores de esta ejecución (documentados en §3.A.9-bis):** un agente reportó falsamente que `RECEPCION` era un placeholder vacío. **La verificación manual lo desmintió.**

**Ejecución 2 — Verificación adversarial del acta** (`wf_48b38c49-84f`)
- **4 agentes en paralelo**, 158.123 tokens, 36 llamadas a herramientas, 415 segundos.
- **Patrón:** *adversarial verify* — cada agente recibió instrucción de **solo leer** y devolver `{ok, hallazgos[], detalles}` con esquema forzado (`StructuredOutput`), con `ok=true` únicamente si no encontraba errores.
- **Las 4 auditorías:**

| Agente | Alcance | Resultado |
|---|---|---|
| `v1:cifras` | Recalcular por su cuenta desde `HUS.xlsx` los 5 totales y comparar contra K9, M9, fila 456 y los 12 valores del DASHBOARD | ✅ `ok:true`, 0 hallazgos |
| `v2:muestreo` | Comparar fila por fila 3 facturas (HUS0000452150 con 62 glosas, HUS0000426013, HUS0000443525) y verificar agrupación en todo el rango | ✅ `ok:true`, 0 hallazgos |
| `v3:formato` | Comparar encabezados, 14 rangos combinados, zona de firmas desplazada, anchos y fórmulas contra la plantilla SINAC | ✅ `ok:true`, 0 hallazgos |
| `v4:crudas` | Verificar encabezados y conteos de GLOSAS/TRAMITES/NOTAS, orden de hojas | ✅ `ok:true`, 0 hallazgos |

- **Dos observaciones menores** que los agentes clasificaron como *no errores* y se aceptan como tales: los anchos difieren en ~0,005 unidades por redondeo a 2 decimales; y se limpió el artefacto `_x000d_` (retorno de carro escapado del export de SIMED) en 676 filas de GLOSAS y 124 de TRAMITES, conservando el texto con saltos de línea normales.

**Manejo de errores de la orquestación:** los agentes que fallan devuelven `null` y se filtran con `.filter(Boolean)`. En la ejecución 2: `agents_error: 0`, `agents_skipped: 0`, `agents_empty_result: 0`.

### 8.3 Relación con la IA del resto de la plataforma

El repositorio **sí tiene** un motor de respuestas con IA (`tests/test_services/`, con degradación Opus→Sonnet, prompts de dictamen, banco de plantillas). **Este módulo no lo toca ni lo invoca.** La única interacción fue de diagnóstico: 85 tests de esa capa aparecían fallando en local por ausencia de `pytest-asyncio`, no por este cambio (ver §11.1).

---

## 9. AUTOMATIZACIONES

### 9.1 Lo que se automatizó (y lo que reemplaza)

| Automatización | Antes (manual) | Ahora |
|---|---|---|
| Identificación del universo | Filtrar y contar a mano | `assert` sobre el lote: 147/444 |
| Cruce glosa ↔ respuesta | Abrir 2 exports y buscar por consecutivo | Índice por consecutivo, 4.063 cruces automáticos |
| Motivo exacto de la EPS | Copiar y pegar por línea | Cascada de 3 niveles sobre 18.371 filas |
| Centro de costo | No se hacía | 444/444 líneas resueltas |
| Detección de duplicados | No se hacía | Exclusión automática de `AC000639` |
| Descarte de filas de totales | Error frecuente al sumar | Descarte posicional automático |
| Contrato 287 vs 440 | Criterio manual | Regla por fecha |
| Clasificación ADM/MED | Manual | `familia_de` sobre el prefijo |
| 11 controles de consistencia | No se hacían | Automáticos |
| Rutas de soportes y FE | Buscar en la red | Derivadas por `AAAAMM` + hipervínculo |
| Totales del acta | Calculadora | Fórmulas vivas que se recalculan solas |
| Expansión del acta a 444 filas | Copiar/pegar destruyendo el formato | Inserción que preserva merges, alturas y estilos |
| Ordenamiento por prioridad | Manual | Mayor valor glosado primero |

### 9.2 Cuándo y cómo se ejecuta

- **Disparo:** manual, bajo demanda del auditor. **No hay cron, ni scheduler, ni trigger.** Fue decisión deliberada: cada corrida depende de exports que el auditor descarga a mano y de un universo que él aprueba.
- **Frecuencia real:** una vez por mesa de conciliación, más las regeneraciones que pidan ajustes.
- **Idempotencia:** total. Reejecutar con las mismas entradas produce el mismo archivo; sobrescribe la salida sin efectos acumulativos.
- **Tiempo:** ~30 s (Generador A, 18.378 glosas) · ~15 s (Generador B, 444 glosas).

### 9.3 Automatización de calidad (CI)

`.github/workflows/ci.yml`, disparado en cada push/PR, con tres jobs:

1. **Lint (ruff)** — ✅ verde en PR #188.
2. **Security scan (pip-audit)** — ✅ verde.
3. **Tests (pytest)** — ✅ verde. Ejecuta `python -m pytest tests/ -v --tb=long --maxfail=5` e instala `pytest pytest-asyncio` explícitamente.

### 9.4 Automatización de verificación del entregable

Dos mecanismos, ambos ejecutados:

1. **`recalc.py` + LibreOffice** — recalcula todas las fórmulas y reporta errores. Resultado final: **471 fórmulas, `status: success`, `total_errors: 0`**, con el `vbaProject.bin` intacto tras el recálculo.
2. **Workflow de verificación adversarial** — §8.2.

---

## 10. ARCHIVOS MODIFICADOS

### 10.1 Archivos NUEVOS en el repositorio

#### `tools/hoja_maestra_conciliacion.py` — 1.088 líneas — **NUEVO**
Generador A completo. Contiene: docstring de módulo (51 líneas documentando fuentes, granularidad y pendientes), 6 constantes de negocio, 26 constantes de índice de columna en 4 bloques, 7 utilidades, 4 lectores, 6 funciones de lógica, `calcular_cruces`, `_escribir_workbook`, `construir`, `main`.

**Cambios aplicados sobre la versión inicial durante el desarrollo:**
1. Izado de los objetos de estilo fuera de los bucles (§13.2).
2. Sustitución de `ws.max_row` por contador propio en los 4 bucles de escritura (§13.3).
3. Regla de puntos múltiples en `_num` (§3.A.2).
4. Totales de conciliación desde `CRUCE ACTAS` en vez de las columnas resumen de CARTERA (§3.A.20).
5. `ruff format` aplicado.

#### `tests/test_tools/test_hoja_maestra_conciliacion.py` — 255 líneas — **NUEVO**
4 tests + 4 funciones de fixture. Sigue la convención del repo: docstring en español, `sys.path.insert` hacia `tools/`, `# noqa: E402` en el import.

#### `docs/MODULO_CONCILIACION_DISPENSARIO.md` — **NUEVO (este documento)**

### 10.2 Archivos MODIFICADOS en el repositorio

#### `BITACORA.md` — **MODIFICADO**
1. Cabecera: *"Última actualización: 22 de julio de 2026"* → **"24 de julio de 2026"**.
2. Nueva sección fechada **"24 de julio de 2026 — Expediente Inteligente de Conciliación (Hoja Maestra)"**, insertada entre la tabla de lotes SIMED y la sección `## 2. PENDIENTE`, con: descripción de la herramienta, las 3 fuentes cruzadas, las 5 hojas, las cifras verificadas y los PENDIENTE marcados. Escrita en español claro para auditor, respetando el formato existente.

### 10.3 Archivos FUERA del repositorio (scratchpad — pendientes de promover)

| Archivo | Líneas | Descripción |
|---|---|---|
| `generar_acta_147.py` | 541 | **Generador B — el vigente.** PENDIENTE de promover a `tools/` |
| `ACTA_CONCILIACION_147_DISPENSARIO.xlsm` | — | Entregable final (629 KB) |
| `EXPEDIENTE_CONCILIACION_DISPENSARIO_24JUL2026.xlsx` | — | Entregable del Generador A (3,5 MB) |
| `LISTADO_147_PARA_APROBAR.xlsx` | — | Listado de aprobación del universo |

### 10.4 Archivos NO modificados (importante para el merge)

**No se tocó ningún archivo preexistente del repositorio salvo `BITACORA.md`.** En particular: ninguna herramienta previa de `tools/`, ningún test previo, ni `requirements.txt`, ni la configuración de CI, ni la plataforma web. **El commit `15ebe51` es puramente aditivo.** Esto se verificó explícitamente moviendo los archivos nuevos fuera del árbol y comprobando que los fallos de `test_services` se reproducían idénticos.

### 10.5 Archivos de entrada (solo lectura — NUNCA modificados)

Regla operativa permanente: **jamás se modifican los archivos originales**. Los 6 archivos de `/root/.claude/uploads/…` se abrieron siempre en modo lectura.

---

## 11. DEPENDENCIAS NUEVAS

### 11.1 Paquetes de Python: NINGUNO NUEVO

**No se añadió ninguna dependencia a `requirements.txt`.** El módulo usa `openpyxl==3.1.5`, que ya estaba en la línea 13.

**Aclaración necesaria sobre `pytest-asyncio` 1.4.0.** Durante el desarrollo se instaló en el entorno local, pero **no es una dependencia nueva del módulo**:
- `pytest.ini` ya declaraba `asyncio_mode = auto` desde antes.
- El CI ya lo instalaba explícitamente (`pip install pytest pytest-asyncio`, `ci.yml:58`).
- **Sin él**, la suite local reportaba **85 fallos** en `tests/test_services/`. **Con él**, la suite completa da **4.224 passed, 1 skipped, 0 failed**.
- Se comprobó que esos fallos eran ajenos al módulo reproduciéndolos con los archivos nuevos retirados del árbol.

**Conclusión:** era una carencia del entorno local, no del código. **No hay que añadir nada a `requirements.txt`.**

### 11.2 Software del sistema: LibreOffice Calc (solo desarrollo)

- **Paquete:** `libreoffice-calc` (LibreOffice 24.2.7.2), instalado con `apt-get install --no-install-recommends libreoffice-calc`.
- **Para qué sirve:** `openpyxl` escribe las fórmulas como texto **sin valor calculado**. Sin recalcular, toda fórmula se lee como `None` desde `pandas`, `data_only=True` y la mayoría de visores. `recalc.py` usa LibreOffice para calcular y reescribir el archivo.
- **Diagnóstico que llevó a instalarlo (§13.5):** el entorno tenía `libreoffice-core` pero **no `libreoffice-calc`**, así que `soffice --version` funcionaba pero cualquier archivo de hoja de cálculo fallaba con `Error: source file could not be loaded`, manifestándose como *timeouts* engañosos. Se aisló probando un archivo trivial de 3 celdas: si un `=SUM(A1:A2)` también expira, el problema no es el tamaño.
- **¿Es necesario en producción?** **No.** Excel recalcula solo al abrir. Solo hace falta si se quiere verificar las fórmulas de forma automatizada.

### 11.3 Herramientas de desarrollo ya presentes

`pytest` 9.1.1 · `ruff` (`check --select F,W6` + `format --check`) · Python 3.11.15.

---

## 12. CONFIGURACIÓN

### 12.1 Variables de entorno

**El módulo no lee ninguna variable de entorno.** No usa `os.environ`, ni `.env`, ni `dotenv`. Toda la parametrización va por argumentos de línea de comandos.

### 12.2 Tokens y credenciales

**El módulo no usa ni almacena ningún token, clave de API ni credencial.** No hay secretos que rotar ni que proteger. El acceso a los recursos de red depende de las credenciales de Windows del usuario.

### 12.3 Archivos de configuración que afectan al módulo

| Archivo | Efecto |
|---|---|
| `pytest.ini` | `testpaths = tests`, `addopts = -v --tb=short`, **`asyncio_mode = auto`** (obliga a `pytest-asyncio`), filtros de warnings |
| `.github/workflows/ci.yml` | 3 jobs; instala `pytest pytest-asyncio`; corre `pytest tests/ -v --tb=long --maxfail=5` |
| `requirements.txt` | `openpyxl==3.1.5` (línea 13) |
| `CLAUDE.md` | Obliga a leer y actualizar `BITACORA.md` en cada sesión |

### 12.4 Parámetros de negocio (constantes en código)

**Generador A** (líneas 68–73):

```python
EPS_NOMBRE = "DIRECCION DE SANIDAD EJERCITO"
NIT_TERCERO = "901541137"
PRESTADOR = "DISPENSARIO MEDICO BUCARAMANGA"
FE_RAIZ = r"\\172.16.32.83\factura_electronica_net22"
SOPORTES_NOTA = "RAIZ Y:/X: PENDIENTE confirmar con auditor; subcarpeta = AAAAMM"
ACTA_DUPLICADA = "AC000639"
```

**Generador B:** `FE_RAIZ` (idéntica) y el diccionario `FAMILIAS` (7 prefijos).

**Constantes estructurales del acta:** `FIRST=12` · `TPL_LAST=22` · `LAST=455` · `TOT=456` · `INS_AT=13` · `extra=433`.

**Regla de vigencia de contrato** (en `contrato_por_fecha`): corte el **30-nov-2025**.

### 12.5 Índices de columna (la configuración más frágil)

Los 26 índices `CA_*`, `RE_*`, `TR_*`, `CR_*` mapean **por posición**, no por nombre. **Si SIMED o DGH cambian el orden de columnas de sus exports, el módulo lee datos equivocados sin dar error.** Ver §13.6 y §16.5.

### 12.6 Rutas

Todas las rutas son **argumentos**, salvo en el Generador B, donde las 6 rutas de entrada están **fijas en el código** (líneas 26–32 y 160) apuntando al directorio de subidas de la sesión. **Debe parametrizarse al promoverlo** (§16.3).

---

## 13. RIESGOS

### 13.1 Riesgo de inflar valores por sumar columnas de nivel factura — **ALTO**

**Qué pasa:** los exports de SIMED repiten `FacturaCartera.Valor` y `FacturaCartera.Saldo` en **cada línea de glosa**. Una factura con 62 glosas repite su valor 62 veces. Sumar esa columna infla la cartera varias veces.

**Cómo se resolvió:** el valor de factura y el saldo se toman **siempre** de CARTERA (nivel factura). Solo se suman las columnas de **nivel línea** (`ValorObjecion`, `ValorAceptado`). En el acta se usa `SUMPRODUCT((E12:E455<>E11:E454)*K12:K455)`, que suma una vez por factura.

**Cómo detectarlo:** si el total facturado se aleja de **$1.267.976.805** (147) o **$20.648.885.150** (universo completo), la regla se rompió.

### 13.2 Riesgo de rendimiento: dedup de estilos de openpyxl — **RESUELTO**

**Qué pasó:** crear `PatternFill(...)` y `Font(...)` dentro de los bucles hacía que openpyxl deduplicara miles de objetos idénticos, con degradación cuadrática.
**Solución:** todos los objetos de estilo se crean **una vez** antes de los bucles (`FILL_RES`, `FILL_ROJO`, `FILL_GRIS`, `FILL_AMBAR`, `FONT_LINK`, `ALIGN_HDR`) y se reutilizan por referencia.

### 13.3 Riesgo de rendimiento: `ws.max_row` es O(n) — **RESUELTO** (el bug más costoso)

**Qué pasó:** el proceso no terminaba ni en 2 minutos. El perfilado con `cProfile` mostró **14,9 s de 25,6 s dentro de `builtins.max` con solo 9.846 llamadas**. La causa: `rid = ws.max_row` después de cada `append`. Cada llamada recorre **todas** las celdas de la hoja → escribir n filas cuesta O(n²). Medición: 1.000 filas → 2,6 s; 4.000 filas → 19,2 s.

**Solución:** llevar un contador propio:

```python
rid = 1
for m in maestra:
    ws.append(m["fila"])
    rid += 1  # contador propio: ws.max_row es O(n) y volveria cuadratico
```

Aplicado en los 4 bucles. **Resultado: de "no termina en 120 s" a ~30 s.**

**Advertencia para el mantenedor:** cualquier `ws.max_row` dentro de un bucle de escritura reintroduce el bug. El comentario explicativo está en el código para impedirlo.

### 13.4 Riesgo: formato condicional sobre columnas completas cuelga el recálculo — **RESUELTO**

**Qué pasó:** la plantilla SINAC traía formato condicional sobre **columnas enteras**: `Z1:Z1048576` en ACTA y `A71:A1048576` en NOTAS. Al recalcular, LibreOffice intentaba evaluar **más de un millón de filas por regla** y expiraba.

**Solución (paso 15 del flujo):** se reconstruye la lista de formato condicional acotando los rangos a los reales (`Z12:Z456`, `W12:W455`) y se elimina el de las hojas crudas. Se descubrió que había **dos** rangos problemáticos, no uno: `A1:A25 A71:A1048576` en NOTAS apareció en la segunda pasada.

**Advertencia:** si se cambia de plantilla, hay que auditar de nuevo sus rangos de formato condicional.

### 13.5 Riesgo: falsos diagnósticos por entorno incompleto — **RESUELTO** (dos casos)

**Caso A — `pytest-asyncio` ausente:** 85 tests de `test_services` fallaban. Parecían regresiones del módulo. **No lo eran.** Se demostró retirando los archivos nuevos del árbol (fallaban igual) e instalando el plugin (4.224 passed, 0 failed).

**Caso B — `libreoffice-calc` ausente:** todos los recálculos expiraban, incluso con timeouts de 300 s. Parecía un problema de tamaño. **No lo era.** Se aisló probando un archivo de 3 celdas: también expiraba. `soffice --version` respondía porque `libreoffice-core` sí estaba; faltaba el módulo de hojas de cálculo. Tras instalarlo, el archivo trivial recalculó en segundos y el acta completa (471 fórmulas) en menos de 270 s.

**Lección:** ante un fallo masivo tras un cambio pequeño y aditivo, **sospechar primero del entorno** y aislar con el caso más simple posible.

### 13.6 Riesgo: los índices de columna son posicionales — **VIGENTE, sin mitigar**

**Qué puede pasar:** si SIMED/DGH reordenan columnas, el módulo lee el campo equivocado y **produce un archivo con datos incorrectos sin lanzar ningún error**.
**Mitigación parcial actual:** los `assert` del Generador B detectan cambios en el número de facturas/glosas, y los cruces #5 y #6 delatarían descuadres grandes.
**Mitigación recomendada:** validar los encabezados por nombre al cargar (§16.5).

### 13.7 Riesgo: pérdida de macros al reguardar el `.xlsm` — **RESUELTO**

**Qué pasa:** `load_workbook` sin `keep_vba=True` **descarta `vbaProject.bin`**.
**Solución:** se usa `keep_vba=True` y se **verifica tras cada guardado y tras cada recálculo** con `unzip -l … | grep -c vbaProject` (siempre `1`).

### 13.8 Riesgo: `insert_rows` no desplaza merges ni alturas — **RESUELTO**

Documentado en §3.B.7. Sin la maniobra de 7 pasos, la zona de firmas del acta queda destruida. Verificado por el agente `v3:formato`.

### 13.9 Riesgo: la columna resumen de CARTERA sub-cuenta — **RESUELTO**

Las columnas `LEVANTADA/ACEPTADA/RATIFICADA EN ACTAS` de CARTERA daban $691.881.200 / $295.521.200, frente a los valores verificados desde el detalle `CRUCE ACTAS`: **$707.499.754 / $980.141.374**. **Regla: los totales de conciliación se toman del detalle, nunca del resumen.**

### 13.10 Riesgo: el universo puede cambiar — **CONTROLADO**

El `assert 147/444` detiene el proceso si el lote cambia. Es intencional: obliga a revalidar el universo con el usuario antes de generar un acta distinta.

### 13.11 Conflictos previstos al integrar

| Conflicto potencial | Probabilidad | Resolución |
|---|---|---|
| `tools/hoja_maestra_conciliacion.py` ya existe en destino | Muy baja | Nombre único; comparar y unificar |
| `BITACORA.md` diverge | **Alta** | Es la memoria común y todos los chats la editan. **Resolver a mano conservando ambas secciones fechadas** — nunca `--theirs`/`--ours` a ciegas |
| `requirements.txt` | Nula | No se tocó |
| CI | Nula | No se tocó |
| Duplicación de utilidades (`num`/`txt`) | Media | Al promover el Generador B, importar del módulo común |

---

## 14. DEPENDENCIAS CON OTROS MÓDULOS

### 14.1 Módulos que este módulo NECESITA

**Ninguno en tiempo de ejecución.** Ambos generadores son **autónomos**: no importan ninguna otra herramienta del repositorio. Solo dependen de `openpyxl` y de la biblioteca estándar. Esto fue deliberado, para que puedan ejecutarse en el equipo del HUS sin arrastrar la plataforma completa.

### 14.2 Módulos con los que se relaciona por DATOS (no por código)

| Módulo | Relación |
|---|---|
| `tools/preparar_lote_dgh_dispensario.py` | Convierte exports DGH al layout `HUS.xlsx` — **produce la entrada del Generador B** |
| `tools/indexar_soportes_dispensario.py` | Construye el índice JSON de soportes de `Y:`/`X:` — **es la pieza que cerraría la ruta de soportes hoy PENDIENTE** (§15.1) |
| `tools/exportar_conciliacion_dispensario.py` | Genera `CONCILIACION.xlsx` desde una carpeta de piloto — mismo lote de 147/444, **fuente alternativa del universo** |
| `tools/expediente_conciliacion.py` | Modelo de expediente por factura con `id_expediente` — **candidato natural a fusionarse** con este módulo |
| `tools/asistente_conciliacion_dispensario.py` | `cargar_glosas`, `codigo_corto`, `familia_de` — **funciones equivalentes duplicadas aquí** (§16.3) |
| `tools/motor_evidencia_dispensario.py` | Localiza evidencia página a página — podría **poblar la columna de soportes** con la página exacta |
| `tools/motor_decision_dispensario.py` | Calcula defendibilidad 0–100 % — podría **alimentar "LISTA PARA CONCILIAR"** con un criterio probatorio |
| `tools/piloto_conciliacion_dispensario.py` | Orquestador extremo a extremo | 
| `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` | Documenta el flujo de **respuesta** de glosas en SIMED, que **produce** los datos que este módulo consume |

### 14.3 Módulos que UTILIZAN este módulo

**Ninguno todavía.** El módulo es hoja terminal: produce archivos para personas, no para otros programas. Sus consumidores son el **auditor de cartera** y la **mesa de conciliación**.

### 14.4 Relación con la plataforma web

**Ninguna.** No comparte código, modelos, base de datos ni configuración con la plataforma (`tests/test_services/`, motor de IA, SQLite). Son subsistemas independientes dentro del mismo repositorio.

### 14.5 Diagrama de relaciones

```
   SIMED ──> RECEPCION_DE_OBJECIONES.xlsx ─┐
   SIMED ──> TRAMITE_DE_OBJECCION.xlsx ────┤
   DGH   ──> CORTE_..._CRUCE_ACTAS.xlsx ───┼──> [hoja_maestra_conciliacion.py]  ──> EXPEDIENTE.xlsx (5.571)
   DGH   ──> Estado_Cartera_JUN_2026.xlsx ─┤
   DGH   ──> HUS.xlsx (lote 147) ──────────┤
   SINAC ──> ACTA_SINAC_720.xlsm ──────────┴──> [generar_acta_147.py]           ──> ACTA_147.xlsm ★
                                                                                        │
   [preparar_lote_dgh] ──> HUS.xlsx ────────────────────────────────────────────────────┘
   [indexar_soportes] ──> indice.json ──> (PENDIENTE: cerrar ruta de soportes)
```

---

## 15. PENDIENTES

### 15.1 PENDIENTES de negocio (requieren respuesta del auditor)

| # | Pendiente | Impacto | Qué se necesita |
|---|---|---|---|
| 1 | **Raíces exactas `Y:` / `X:`** y umbral reciente/histórico | La columna de ruta de soportes trae la ruta derivada por `AAAAMM` con la marca `PENDIENTE`, no una ruta abrible | Que el auditor confirme las cadenas exactas. Luego se cierra contra el índice de `indexar_soportes_dispensario.py` |
| 2 | **CUENTA CONTABLE** | Las 444 filas dicen `"PENDIENTE"` | **No existe en ninguna fuente disponible** (ni lote, ni cartera, ni SIMED; en el acta 720 original la columna `CuentaObjecion` venía vacía). Vive en contabilidad/DGH |
| 3 | **Bandera de factura electrónica (CUFE/CUV)** | Columna `FE` con `"PENDIENTE VERIFICAR"` | Ninguna fuente trae CUFE. Solo derivable comprobando existencia del archivo en la ruta de red |
| 4 | **Normatividad citada por respuesta** | Columna con `"PENDIENTE (inyectar del motor)"` | Construir tabla de mapeo `código_glosa → norma` (Res. 2284/2023, contrato 440-DIGSA/DMBUG-2025, tarifas HUS 054/124-2026) |
| 5 | **Valor pagado real** | Solo hay proxy (`VALOR LIBRE PARA PAGO`, `SOPORTE DE PAGO`) | El pago aplicado real no está en las fuentes |
| 6 | **Acta de inicio del contrato 287** y mapeo de códigos internos (`U22031`/`C26001`) | `contrato_por_fecha` marca `(aprox)` | Confirmar con el auditor para cerrar la regla de vigencia |
| 7 | **`HUS0000443525`** no cruza con cartera | Marcada `"NO ESTA EN CARTERA"` | **El usuario no respondió si incluirla (147) o excluirla (146).** Hoy está **incluida** |
| 8 | **Confirmación del universo de 147** | Se entregó `LISTADO_147_PARA_APROBAR.xlsx` | **El usuario no dio aprobación explícita.** Se procedió porque después pidió el acta con ese universo |

### 15.2 Hallazgos abiertos (para llevar a la mesa)

| Hallazgo | Dato | Significado |
|---|---|---|
| **Soporte de entrega ESM = "NO" en las 444 líneas** | 147/147 facturas | La entidad **no ha confirmado recibo de ninguna respuesta**, aunque las 444 tienen radicado de entrega. Es un punto de negociación, no un defecto nuestro |
| **29 facturas con diferencia** entre el glosado del lote y el de cartera | 29 de 147 | Requiere revisión previa a la mesa |
| **Discrepancia trámite vs cartera en el aceptado** | Lote: $0 · Cartera: **$1.758.956** en 8 facturas | El lote dice que no aceptamos nada (RE9901) pero cartera registra aceptaciones. **Debe aclararse antes de firmar** |
| **Glosas sin respuesta en el universo completo** | 179 | Riesgo de vencimiento de términos |
| **Facturas de cartera sin línea de glosa** | ~1.772 (5.571 − 3.799) | Verificar si son realmente "sin glosa" o fuga de fuente |

### 15.3 PENDIENTES técnicos

| # | Pendiente | Prioridad |
|---|---|---|
| 1 | **Promover `generar_acta_147.py` a `tools/`** con rutas parametrizadas por `argparse`, docstring, README y tests | **ALTA** — es el generador vigente y hoy vive fuera del repo |
| 2 | Eliminar la duplicación de `num`/`txt`/`norm` entre ambos generadores | Media |
| 3 | Validar encabezados por nombre además de por posición (§13.6) | **ALTA** |
| 4 | Parametrizar el universo (hoy `assert` fijo en 147/444) | Media |
| 5 | Escribir `README_hoja_maestra_conciliacion.md` siguiendo la convención de `tools/` | Media |
| 6 | Actualizar `BITACORA.md` con la sesión del 27-jul (acta de las 147) | **ALTA** — lo exige `CLAUDE.md` |
| 7 | Bajar el resultado de acta a nivel de **cada glosa** (hoy es a nivel factura/acta) | Baja |
| 8 | Llave de dedup entre fuentes si se combinan lote + trámite + recepción | Baja |

### 15.4 Errores conocidos

**No hay errores abiertos conocidos en el código entregado.** Estado de verificación:

- Suite completa: **4.224 passed, 1 skipped, 0 failed**.
- `ruff check --select F,W6`: **All checks passed**.
- `ruff format --check`: **2 files already formatted**.
- CI del PR #188: **3 de 3 jobs en verde**.
- Recálculo del acta: **471 fórmulas, 0 errores**.
- Verificación adversarial: **4 de 4 agentes con `ok: true`, 0 hallazgos**.

**Limitaciones conocidas (no son errores):**
1. Sin tablas dinámicas vivas (sustituidas por fórmulas).
2. Sin listas desplegables (se descartaron para no alterar el formato oficial).
3. Los anchos de columna difieren ~0,005 unidades por redondeo — imperceptible.
4. El artefacto `_x000d_` de SIMED se limpia (mejora, no defecto).

### 15.5 Mejoras previstas

1. **Cerrar la ruta de soportes** integrando `indexar_soportes_dispensario.py`: bandera `soporte_encontrado` y ruta real por factura.
2. **Poblar la normatividad** desde el motor de plantillas.
3. **Alimentar "LISTA PARA CONCILIAR"** con la defendibilidad de `motor_decision_dispensario.py` en vez de la regla actual (respondida + sin diferencia + en cartera).
4. **Página exacta del soporte** por glosa usando `motor_evidencia_dispensario.py`.
5. **Generalizar a otras EPS** (hoy las constantes son del Dispensario).
6. **Comparador tarifario** contra el contrato 440 (existe el análisis previo: 75 glosas por **$5.861.318** objetadas como "SIN CONTRATO → SOAT pleno" que **sí están bajo el contrato 440** — defensa sistemática fuerte).

---

## 16. RECOMENDACIONES PARA FUSIONARLO

### 16.1 Paso 1 — Verificar antes de tocar nada

```bash
git fetch origin claude/dispensario-objections-bot-h8dfcf
git log --oneline origin/claude/dispensario-objections-bot-h8dfcf -3
# Debe aparecer 15ebe51 DISPENSARIO: Expediente Inteligente de Conciliacion...
```

**Comprobar que no se pierde nada** (esta es la regla de oro del proyecto, aprendida a la fuerza):

```bash
git merge-base --is-ancestor <commit_local> origin/<rama_destino>; echo "EXIT=$?"
# EXIT=0 => el commit ya está contenido. EXIT=1 => NO está: no continuar.
```

> **Contexto histórico:** en una sesión previa un merge se ejecutó **sobre la rama equivocada** y se detectó justamente porque `git merge-base --is-ancestor` devolvió `EXIT=1`. Se recuperó con `reset --hard` al commit previo. **Verificar siempre `git branch --show-current` antes de un merge.**

### 16.2 Paso 2 — Fusionar el commit del repositorio

`15ebe51` es **puramente aditivo**: 2 archivos nuevos + `BITACORA.md`. El único conflicto probable es `BITACORA.md`.

```bash
git checkout <rama_principal>
git merge --no-commit --no-ff origin/claude/dispensario-objections-bot-h8dfcf   # ENSAYO
git status
```

**Si `BITACORA.md` entra en conflicto: resolverlo a mano conservando AMBAS secciones fechadas.** Nunca `--theirs` ni `--ours`: se perdería la memoria de una de las ramas.

Alternativa más limpia si el destino divergió mucho:

```bash
git cherry-pick 15ebe51
```

### 16.3 Paso 3 — Promover el Generador B al repositorio (**imprescindible**)

**Es el trabajo más importante que queda**, porque el generador vigente vive fuera del repo. Pasos:

1. Copiar `generar_acta_147.py` a `tools/generar_acta_conciliacion_dispensario.py`.
2. **Parametrizar las 6 rutas fijas** (líneas 26–32 y 160) con `argparse`:
   `--lote`, `--tramite`, `--recepcion`, `--cartera`, `--estado-cartera`, `--plantilla`, `--salida`.
3. **Sustituir el `assert` fijo** por un `--esperado-facturas` / `--esperado-glosas` opcional que, si se pasa, valide; si no, solo informe.
4. **Eliminar la duplicación**: importar `num`, `txt`, `normalizar_factura` de `hoja_maestra_conciliacion.py`, o extraer un `tools/_comun_conciliacion.py`.
5. Añadir docstring de módulo con el bloque `USO` (convención del repo).
6. Escribir `tests/test_tools/test_generar_acta_conciliacion_dispensario.py` con fixtures que imiten la plantilla SINAC (mínimo: expansión de filas que preserva merges y alturas, `keep_vba`, regla de "solo primera fila de la factura", fórmula `SUMPRODUCT`).
7. Escribir `tools/README_generar_acta_conciliacion_dispensario.md`.
8. Correr `ruff check --select F,W6` y `ruff format`.

### 16.4 Paso 4 — Verificar la integración

```bash
pip install pytest-asyncio          # OBLIGATORIO: pytest.ini usa asyncio_mode = auto
python -m pytest tests/ -q          # esperado: 4224 passed, 1 skipped, 0 failed
python -m ruff check --select F,W6 tools/ tests/
python -m ruff format --check tools/ tests/
```

**Si aparecen ~85 fallos en `tests/test_services/`: falta `pytest-asyncio`.** No es una regresión (§13.5).

Prueba funcional extremo a extremo con datos reales:

```bat
py tools\hoja_maestra_conciliacion.py --cartera "…CRUCE_ACTAS.xlsx" ^
   --recepcion "…RECEPCION….xlsx" --tramite "…TRAMITE….xlsx" --salida "PRUEBA.xlsx"
```

**Cifras de control que DEBEN salir** (si alguna cambia, algo se rompió):

| Indicador | Valor esperado |
|---|---|
| Facturas maestra | 5.571 |
| Facturas con glosa | 3.935 |
| Glosas | 18.378 |
| Glosas sin respuesta | 179 |
| Filas de actas | 1.710 |
| Glosado | $7.000.506.193 |
| Aceptado | $1.122.029.872 |
| Levantado | $707.499.754 |
| Ratificado | $980.141.374 |
| Saldo DGH | $13.621.817.613 |

Y para el acta de las 147:

| Indicador | Valor esperado |
|---|---|
| Facturas / glosas | 147 / 444 |
| Total facturado (K456) | $1.267.976.805 |
| Glosado (L456) | $317.640.524 |
| Pendiente por conciliar (M456) | $317.640.524 |
| Aceptado en trámite (T456) | $1.758.956 |
| Recuperable (dashboard) | $315.881.568 |
| Fórmulas / errores | 471 / 0 |
| `vbaProject.bin` | presente (1) |

### 16.5 Paso 5 — Endurecer antes de producción

1. **Validar encabezados por nombre** al cargar cada fuente y fallar con mensaje claro si no coinciden (mitiga §13.6).
2. **Añadir un test de regresión de cifras** que corra sobre un extracto reducido de los archivos reales.
3. **Documentar en `CLAUDE.md`** que este módulo existe y qué contexto leer.

### 16.6 Paso 6 — Preservar el conocimiento

1. **No fusionar sin conservar este documento** (`docs/MODULO_CONCILIACION_DISPENSARIO.md`).
2. **Actualizar `BITACORA.md`** con la sesión del 27-jul (acta de las 147, columnas T/U/V/S completadas). Lo exige `CLAUDE.md`.
3. **Conservar los archivos de entrada** en un directorio versionado o documentar su ubicación: sin ellos el módulo no se puede reejecutar ni verificar.
4. **Conservar los entregables** (`ACTA_CONCILIACION_147_DISPENSARIO.xlsm`, `EXPEDIENTE_…xlsx`, `LISTADO_147_PARA_APROBAR.xlsx`): son la evidencia del estado con el que se preparó la mesa.

### 16.7 Orden recomendado

```
1. Verificar (16.1)
2. Merge de 15ebe51 resolviendo BITACORA.md a mano (16.2)
3. Correr suite + lint (16.4) — DEBE dar verde antes de seguir
4. Promover el Generador B (16.3)
5. Correr suite + prueba funcional con cifras de control (16.4)
6. Endurecer (16.5)
7. Documentar y archivar (16.6)
```

---

## 17. RESUMEN EJECUTIVO

### 17.1 Qué es este módulo en una frase

Un **ETL determinista en Python** que cruza cinco exports de SIMED y DGH para producir el **acta de conciliación de las 147 facturas** que el HUS lleva a la mesa con el Dispensario Médico, en el **formato oficial del acta SINAC**, con la glosa de la EPS y la respuesta del HUS enfrentadas glosa por glosa.

### 17.2 Las 10 cosas que un desarrollador nuevo DEBE saber

1. **Hay dos generadores, y el vigente NO está en el repo.** `tools/hoja_maestra_conciliacion.py` (5.571 facturas) está commiteado; `generar_acta_147.py` (147 facturas, formato SINAC) es **el que el usuario usa** y vive en el scratchpad. **Promoverlo es la tarea número uno** (§16.3).

2. **El universo son 147 facturas, no la cartera.** El usuario rechazó explícitamente el enfoque de cartera completa. Cualquier ampliación de alcance debe consultarse antes.

3. **`normalizar_factura` es el corazón.** Cada fuente escribe la factura distinto. Todo cruce pasa por `HUS` + 10 dígitos.

4. **La relación clave es `TRAMITE.col20 = RECEPCION.col13`** (consecutivo), no la factura. 4.063 de 4.066 cruzan.

5. **Nunca sumar columnas de nivel factura de los exports de SIMED**: están repetidas por línea (§13.1). Usar CARTERA o `SUMPRODUCT` con detección de cambio de factura.

6. **Nunca usar `ws.max_row` dentro de un bucle de escritura.** Es O(n) y vuelve el proceso cuadrático (§13.3). Usar contador propio. Igual con los objetos de estilo: crearlos fuera del bucle.

7. **`keep_vba=True` es obligatorio** al abrir el `.xlsm`, y hay que verificar el `vbaProject.bin` después de cada guardado y recálculo.

8. **Los índices de columna son posicionales.** Si SIMED cambia el orden, el módulo lee mal **sin dar error** (§13.6). Es la fragilidad estructural más importante.

9. **La regla de oro del proyecto: nunca inventar.** Lo que no existe se marca `PENDIENTE`, jamás en blanco. Las funciones ambiguas (`_motivo_eps_para`, `centro_costo`) muestran **todas** las opciones reales en vez de elegir una. La cuenta contable dice `PENDIENTE` en las 444 filas porque **no existe en ninguna fuente**, y eso es una respuesta correcta, no un fallo.

10. **Ante fallos masivos tras un cambio pequeño, sospechar del entorno.** Pasó dos veces (§13.5): 85 tests "rotos" por falta de `pytest-asyncio`, y todos los recálculos "colgados" por falta de `libreoffice-calc`. Aislar con el caso más simple posible.

### 17.3 Cómo se mantiene

**Para regenerar el acta con datos nuevos:** conseguir los 6 archivos de entrada actualizados, ajustar rutas, ejecutar, recalcular, verificar contra las cifras de control (§16.4).

**Para cambiar el universo:** ajustar el `assert` (o el parámetro, una vez promovido) y **revalidar el listado con el auditor antes de generar**. El usuario exigió esa compuerta de aprobación explícitamente.

**Para añadir una columna al acta:** añadir el encabezado en `AM11..` copiando el estilo de `I11`, escribir el valor en el bucle de volcado, y decidir si es de **nivel línea** (todas las filas) o de **nivel factura** (solo `first_of_fac`, para que la suma no se duplique).

**Para cambiar de plantilla:** auditar sus rangos de formato condicional (§13.4), recalcular `FIRST`/`TPL_LAST` y verificar la zona de firmas tras la inserción.

### 17.4 Estado de entrega

| Aspecto | Estado |
|---|---|
| Código en repo | ✅ Commit `15ebe51`, PR #188 |
| CI | ✅ 3/3 verde |
| Pruebas | ✅ 4.224 passed, 1 skipped, 0 failed |
| Lint / formato | ✅ Limpio |
| Entregable acta 147 | ✅ Generado, recalculado (471 fórmulas, 0 errores), macros intactas |
| Verificación adversarial | ✅ 4/4 agentes, 0 hallazgos |
| Cifras | ✅ Todas contrastadas contra la fuente |
| Documentación | ✅ Este documento + `BITACORA.md` |
| Generador vigente en repo | ❌ **PENDIENTE** (§16.3) |
| Rutas de soportes | ⚠️ PENDIENTE de confirmación del auditor |
| Cuenta contable | ⚠️ No existe en ninguna fuente |

### 17.5 Valor entregado al negocio

- **Universo preparado:** 147 facturas · 444 glosas · **$317.640.524** en discusión.
- **Tiempo:** de horas de transcripción manual por factura a **~15 segundos** para las 147.
- **Trazabilidad:** cada cifra del acta es rastreable hasta la celda del export de origen.
- **Hallazgos que no se conocían:** 29 facturas con diferencias, discrepancia de $1.758.956 entre trámite y cartera, cero confirmaciones de recibo de la entidad, y una factura fuera de cartera.
- **Formato:** acta institucional firmable, no un Excel improvisado.

---

*Fin del documento. Elaborado como entrega formal del módulo al equipo principal, a partir únicamente de la información generada y verificada durante el desarrollo.*
