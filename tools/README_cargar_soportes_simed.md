# Guía: `cargar_soportes_simed.py` — Carga masiva de notas crédito en SIMED (Dispensario)

Bot Playwright que recorre el portal SIMED (`auditool25.tool.com.co`) y carga
las notas crédito del HUS al Dispensario Médico Bucaramanga, junto con sus
3 archivos finales (PDF + XML + JSON CUV). Reemplaza el flujo manual de:

> *abrir cada factura conciliada, editar, escribir el N° de nota crédito,
> subir los 3 soportes, confirmar, re-entrar a persistir la NC, y dar Enviar
> al final*

por una corrida desatendida que procesa decenas/cientos de notas con
reporte CSV y manejo automático de las idiosincrasias del portal (3 pasadas
por factura porque GeneXus no persiste la NC en una sola).

---

## 1) Por qué existe

El portal SIMED del Dispensario tiene un comportamiento documentado: si subís
los soportes y le das Confirmar **en una sola pasada**, la nota crédito que
escribiste se pierde — el portal guarda los archivos pero no el número de NC,
y la factura queda con `NC vacía`. La conciliación termina rota.

La operación manual correcta es de 3 pasadas por factura:

1. **Pasada 1**: filtrar la factura → lápiz (editor) → escribir NC →
   abrir "Soportes NC" → subir PDF + XML + JSON → Confirmar (del modal).
2. **Pasada 2**: volver a la grilla → re-filtrar → lápiz → reescribir la NC →
   Confirmar (del form principal). Recién acá la NC queda persistida.
3. **Pasada 3**: volver a la grilla → re-filtrar → click en el botón verde
   (Enviar/Finalizar) de la fila → confirmar el popup "Registro completado".

Para 25-100 notas por acta, hacerlo a mano es jornada completa. El bot
automatiza las 3 pasadas con manejo de:

- **Idempotencia**: si volvés a correrlo, las facturas ya cargadas detectan
  el mensaje "YA_PROCESADA" y se saltan.
- **Validación de la NC contra el CUV**: si tipea con `fill()` el portal
  rechaza con "el código digitado no corresponde con el CUV" — el bot usa
  `page.keyboard.type()` para disparar la validación nativa.
- **Detección de rechazos del portal**: si el portal contesta algún error de
  validación, el bot lo captura y registra como `RECHAZADA: <motivo>` en el
  reporte sin abortar el lote completo.

---

## 2) Insumos que necesita

### A) Carpeta destino con los soportes consolidados (`--destino`)

Una raíz con sub-carpetas por nota crédito (con o sin gestor intermedio):

```
D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_AC000456_25\NOTAS\
├── 302478\
│   ├── NC_302478_HUS0000403288.pdf  ← obligatorio
│   ├── XML_302478_HUS0000403288.xml ← obligatorio
│   └── CUV_302478_HUS0000403288.json ← opcional (depende del lote)
├── 263272\
│   ├── NC_263272_HUS0000404136.pdf
│   ├── XML_263272_HUS0000404136.xml
│   └── (sin CUV — el validador DIAN no generó CUV en su momento)
└── ...
```

El bot busca los archivos por patrón `NC_<NE>_HUS<num>.pdf` con su `XML_…`
y `CUV_…` hermanos. Si falta alguno, la factura queda como `FALTAN_ARCHIVOS`
en el reporte (no la procesa).

Para llegar a esta estructura, hay un pipeline previo de 3 scripts:

1. `extraer_notas_credito.py` — copia carpetas desde el share `\\172.16.32.83\factura_electronica_net22\…\FACTURAS_NOTA\<NE>\`.
2. `renombrar_y_organizar_notas.py` — lee el contenido de los PDFs del CRRP, identifica NE + factura, los renombra al patrón `NC_<NE>_HUS<num>.pdf`.
3. `consolidar_carpetas_notas.py` — renombra los XMLs (`ad*.xml → XML_…`) y los JSONs (`RIPS/ResultadosDoker_*.json → CUV_…`), manda los archivos sobrantes a `_papelera\`.

### B) Lista opcional (`--lista`) — Excel/CSV/TSV

TXT con una nota crédito por línea, o Excel con la columna `NOTA CREDITO`.
Útil cuando la carpeta destino reúne notas de varios actas pero solo querés
cargar las del acta de hoy.

```
302478
263272
263278
...
```

### C) Credenciales SIMED (variables de entorno)

```cmd
setx SIMED_USER 900006037
setx SIMED_PASSWORD <password>
```

Una sola vez por máquina. **Nunca pongas la contraseña en el comando** — queda
en el historial.

---

## 3) Flujo paso a paso por factura (las 3 pasadas)

### 3.0 Login (una sola vez)

`GET` a `https://auditool25.tool.com.co/gamexamplelogin.aspx` →
escribe usuario y password → Enter (si no submitea, click en el botón;
si sigue disabled, fuerza submit por JS).

Espera el menú lateral con `Procesos` como señal de éxito. La sesión queda
abierta para todas las facturas del lote.

### 3.1 PASADA 1 — Filtrar + Editor + NC + Subir soportes

#### Filtro
Va a `glosasfacturaconww.aspx` (Facturas Conciliadas), busca la caja de
filtro por factura, escribe el número (sin prefijo "HUS" y sin ceros, ej.
`403288`), presiona Enter o click en Filtrar.

Espera a que la grilla muestre 1 fila exactamente. Si muestra 0 → la nota ya
no está en estado conciliado (ya procesada o no existe) → estado
`NO_EN_GRILLA`. Si muestra >1 → estado `AMBIGUO`.

#### Editor
Click en el ícono **lápiz** (✏️) de la fila → se abre el editor de la
factura.

#### Escribir NC
Localiza el campo "Nota Crédito" y escribe el N° usando
**`page.keyboard.type()`** (NO `fill()`).

Esto es **crítico**: el portal de GeneXus valida la NC contra el CUV
contraparte sólo cuando recibe eventos `keyup` reales. Con `fill()` el portal
acepta el valor pero después al Confirmar dispara la regla *"el código
digitado no corresponde con el CUV"*. Tipearlo simula la entrada nativa del
operador humano y dispara la validación correcta.

#### Soportes NC
Click en el botón "Soportes NC" → modal con tres campos `<input type=file>`.

#### Subir archivos
- `NC_<NE>_HUS<num>.pdf` → input PDF
- `XML_<NE>_HUS<num>.xml` → input XML
- `CUV_<NE>_HUS<num>.json` → input JSON (si existe)

Usa `set_input_files()` de Playwright para cada uno. Espera 1-2s entre
cargas para que el portal procese asincrónicamente.

#### Confirmar (del modal)
Click en el botón verde "Confirmar" **del modal de Soportes NC** (no del
form principal — son dos confirmaciones distintas). El portal vuelve a la
grilla.

### 3.2 PASADA 2 — Re-entrar y persistir la NC

#### Re-filtrar
Vuelve a `glosasfacturaconww.aspx`, filtra por factura otra vez.

#### Editor
Click en lápiz → editor.

#### Reescribir NC
**Importante**: aunque la NC quedó visible en la pasada 1, **se reescribe**.
GeneXus no persiste el campo NC junto con los soportes; necesita un segundo
"toque" del editor + Confirmar.

Usa `page.keyboard.type()` de nuevo (mismo motivo de la validación).

#### Confirmar (form principal)
Click en el "Confirmar" verde **del form principal** (no del modal de
soportes — este se cierra cuando hay archivos ya cargados; el bot detecta
ese caso y salta la subida).

A partir de aquí la factura tiene NC persistida + soportes subidos.

### 3.3 PASADA 3 — Enviar / Finalizar

#### Re-filtrar
Vuelve a la grilla y filtra otra vez.

#### Click en botón verde de la fila
La grilla tiene una columna OPCIONES con un ícono verde
(`ActionExportFile2.png` según el manifest del portal). Click en ese ícono.

#### Confirmar popup
El portal muestra un popup pidiendo confirmación del envío. Click en Aceptar.

#### Verificar mensaje
Espera el toast/cartel **"Registro completado"** como confirmación final.
Estado del reporte: `OK`.

---

## 4) Estados posibles del reporte

| Estado | Significado |
|---|---|
| `OK` | Las 3 pasadas se ejecutaron y el portal devolvió "Registro completado". |
| `YA_PROCESADA` | El portal dice que esta factura ya tiene NC + soportes cargados. El bot la salta limpio. |
| `FALTAN_ARCHIVOS` | Falta el PDF, el XML o (si lo requiere) el JSON CUV en la carpeta. |
| `NO_EN_GRILLA` | El filtro no devolvió ninguna fila — la factura no está en estado conciliado en el portal (puede que ya esté procesada por otra ruta o no exista). |
| `AMBIGUO` | El filtro devolvió más de una fila — necesita revisión manual. |
| `RECHAZADA: <motivo>` | El portal rechazó la NC (típico: "el código digitado no corresponde con el CUV"). El bot capturó el texto del error para diagnóstico. |
| `TIMEOUT` | Algún paso superó el límite de espera (portal lento o cuelgue). |
| `ERROR` | Excepción no clasificada. Mirar el screenshot de `debug_screenshots\`. |

---

## 5) Argumentos del CLI

### Selección (uno requerido)

| Flag | Para qué |
|---|---|
| `--solo NOTA` | Una sola nota (piloto). |
| `--lista archivo` | Excel/CSV/TSV con columna `NOTA CREDITO` — procesa solo las que aparecen ahí. |
| `--todas` | Procesa todas las carpetas encontradas bajo `--destino`. |

### Obligatorio

| Flag | Uso |
|---|---|
| `--destino <dir>` | Carpeta base con subcarpetas `<NE>\` o `<GESTOR>\<NE>\`. |

### Modificadores

| Flag | Para qué |
|---|---|
| `--con-cabeza` | Browser visible (default headless). Usalo en pilotos. |
| `--lento` | `slow_mo=500ms` entre acciones (debug visual). |
| `--reporte <csv>` | Ruta del CSV de salida. Default `reporte_carga_simed.csv`. |
| `--log <ruta>` | Guarda log adicional a archivo. |

---

## 6) Comandos típicos

### Piloto con una nota (browser visible)

```cmd
py tools\cargar_soportes_simed.py ^
  --destino "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_AC000456_25\NOTAS" ^
  --solo 302478 ^
  --con-cabeza
```

Mirá el browser durante el flujo: vas a ver el filtro, el editor abrir,
la NC tipearse, los archivos subir, el confirm de soportes, la re-entrada,
el confirm principal, y finalmente el verde de la fila + "Registro completado".

### Lote acotado con TXT de NEs

```cmd
py tools\cargar_soportes_simed.py ^
  --destino "D:\...\LOTE_AC000456_25\NOTAS" ^
  --lista "D:\...\LOTE_AC000456_25\notas_correo.csv" ^
  --reporte "D:\...\LOTE_AC000456_25\rep_carga_simed.csv"
```

El CSV de `--lista` solo necesita una columna `NOTA CREDITO` (acepta el mismo
formato que ya usa `extraer_notas_credito.py`).

### Lote completo (todas las carpetas del destino)

```cmd
py tools\cargar_soportes_simed.py ^
  --destino "D:\...\NOTAS" ^
  --todas ^
  --reporte "D:\...\reporte_carga.csv"
```

Sin `--con-cabeza` corre headless = más rápido.

---

## 7) Soportes y evidencia de cada decisión

| Decisión de diseño | Por qué — caso real que la motivó |
|---|---|
| **3 pasadas** por factura (filtro→editor→NC→soportes; re-entrar; enviar) | El portal no persiste la NC junto con los soportes en una sola pasada. Verificado por horas perdidas trabajando lotes que después aparecían con NC vacía. |
| **`page.keyboard.type()`** en lugar de `fill()` para la NC | GeneXus valida la NC contra el CUV solo cuando recibe `keyup` reales. Con `fill()` el portal devolvía "el código digitado no corresponde con el CUV" siempre. |
| **Detección de "Soportes ya subidos"** | En la pasada 2, el modal de soportes se cierra solo si los archivos ya están — el bot detecta ese caso y salta la subida en vez de fallar. |
| **`YA_PROCESADA` como estado válido** (no error) | Una corrida interrumpida puede dejar algunas notas a medias y otras ya completas. Al re-correr, el bot las salta sin contar como error. |
| **Reporte CSV con flush cada N** | Si la red cae o el portal expira la sesión, querés saber hasta dónde llegó la corrida. |
| **Ícono verde por imagen `ActionExportFile2.png`** | El portal usa imágenes sin texto en la columna de acciones — el bot busca por nombre del recurso para evitar romperse si cambia el alt-text. |

---

## 8) Pipeline completo (de notas crédito a SIMED)

```
1) extraer_notas_credito.py
       Lee Excel/CSV con NOTA CREDITO →
       Copia carpetas desde \\172.16.32.83\factura_electronica_net22\
                            <PERIODO>\FACTURAS_NOTA\<NE>\
       a <destino>\<NE>\ con todo su contenido (RIPS, XMLs, PDFs, ZIP).

2) renombrar_y_organizar_notas.py [--en-sitio | --origen X]
       Lee el contenido de los PDFs CRRP →
       Extrae Nota Electrónica + Factura HUS →
       Renombra a NC_<NE>_HUS<num>.pdf.
       Con --hus-corto saca los ceros (HUS0000409621 → HUS409621).
       Con --mapa CSV completa la factura cuando el PDF no la trae.

3) consolidar_carpetas_notas.py [--aceptar-sin-json]
       En cada subcarpeta <NE>\ deja sólo 3 archivos finales:
         NC_<NE>_HUS<num>.pdf
         XML_<NE>_HUS<num>.xml  (renombrado del ad*.xml original)
         CUV_<NE>_HUS<num>.json (movido desde RIPS\ResultadosDoker_*.json)
       Lo demás (ar*.xml, nc*.xml originales, .zip, carpeta RIPS) va a
       _papelera\<NE>\ (reversible).

4) verificar_cuv_notas.py [--lista NEs.txt]
       Recorre el share y para cada NE/factura busca su
       ResultadosDoker_*.json → reporta:
         OK            (ResultState:true, CUV asignado)
         RECHAZADO     (RVC063, RVC086, etc. — RIPS con problema en
                        catálogo SISPRO)
         SIN_NOTA      (la nota no aparece en ningún periodo del share)

5) cargar_soportes_simed.py
       Las que pasaron CUV se cargan al portal SIMED.
```

---

## 9) Carpeta `debug_screenshots\` (diagnóstico)

Cada error genera un PNG con timestamp en el directorio de trabajo:

```
debug_screenshots\
├── 095025_filtro_sin_resultado_302478.png
├── 100330_modal_soportes_no_abre_263272.png
├── 132821_confirm_sin_responder_302478.png
└── ...
```

Sirven para investigar después qué pasó si una factura quedó como
`ERROR` o `TIMEOUT` sin contexto.

---

## 10) Limitaciones conocidas

- **Cambios del portal GeneXus**: si SYAC actualiza la app y cambia los
  selectores (botones por id, modal classes), hay que actualizar
  `filtrar_por_factura`, `abrir_factura` o
  `enviar_y_confirmar`. El bot tiene fallbacks pero limitados.
- **Concurrencia**: una sola instancia por usuario — dos bots con la misma
  cuenta pelean por la sesión.
- **Validación contra CUV inválido**: si el `CUV_*.json` que adjuntás dice
  `ResultState:false` (RIPS rechazado por SISPRO), el portal va a aceptar
  el upload pero la NC queda con CUV inválido. Hay que validar **antes**
  con `verificar_cuv_notas.py` y solo cargar las que pasaron.
- **Paths largos en Windows**: si la carpeta `--destino` está en una ruta
  >260 caracteres, los uploads pueden fallar silenciosamente. Trabajar en
  rutas cortas o activar `LongPathsEnabled` en el registro.
- **Sin reintento automático**: a diferencia del bot de COOSALUD, este
  no reintenta facturas que fallan. Hay que correr el bot otra vez con el
  reporte anterior como referencia para identificar qué quedó pendiente.
