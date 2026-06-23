# Contexto HUS Dispensario — Cargue de Notas Crédito (SIMED)

> **Cómo usar este archivo:** pegá su contenido completo como primer mensaje en
> un nuevo chat de Claude Code y el asistente va a tener todo el contexto del
> flujo de **CARGUE DE NOTAS CRÉDITO** del Dispensario.
>
> **Este archivo NO cubre la respuesta de glosas.** Para eso usá
> `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` en otro chat.

---

## 1) Quién soy y qué hago

- Soy auditor de cartera del **Hospital Universitario de Santander** (HUS,
  NIT 900006037-4), Bucaramanga, Colombia.
- Mi tarea en este flujo: **armar carpetas de soportes de notas crédito y
  subirlas al portal SIMED** del Dispensario Médico Bucaramanga (DMBUG, del
  Subsistema de Salud FF.MM.).
- Trabajo en Windows con PowerShell.

## 2) Plataforma

- DMBUG usa el portal **SIMED** en `auditool25.tool.com.co`.
- **ESTO ES PARA DISPENSARIO MEDICO, NO PARA COOSALUD.** COOSALUD usa
  `vco.ctamedicas.com` (otra guía aparte).
- En este flujo subimos **notas crédito** (NC) con sus 3 archivos:
  PDF + XML + CUV (JSON del MinSalud).

## 3) Repositorio

- **Path local en Windows:** `C:\temp-notas`
- **Repo:** `motor-glosas-hus`
- **Branch:** `claude/excel-reconciliation-data-9Bnpj`
- Antes de cada corrida: `cd C:\temp-notas; git pull`

## 4) Credenciales (env vars)

```cmd
setx SIMED_USER 900006037
setx SIMED_PASSWORD <password>
```

Cerrar y reabrir PowerShell para que las tome.

## 5) Pipeline completo (5 pasos)

El flujo va del **PDF CRRP del DIAN** al **portal SIMED**:

```
PDFs CRRP (Nueva carpeta)
    │
    ├─ 1. renombrar_y_organizar_notas.py
    │       → crea <NE>\NC_<NE>_HUS<n>.pdf
    │
    ├─ 2. extraer_notas_credito.py
    │       → trae XML + JSON CUV del share UNC
    │
    ├─ 3. consolidar_carpetas_notas.py
    │       → renombra a XML_/CUV_, manda extras a _papelera
    │
    ├─ 4. verificar_cuv_notas.py
    │       → reporta CUV OK / RECHAZADO
    │
    └─ 5. cargar_soportes_simed.py
            → sube las 3 pasadas al portal SIMED
```

### Paso 1 — `tools/renombrar_y_organizar_notas.py`

Lee PDFs CRRP con nombre `HUS<n>.pdf`, extrae el **NE** (Nota Electrónica) y
la factura HUS del contenido con `pdfplumber`, y los renombra a
`NC_<NE>_HUS<n>.pdf` dentro de la carpeta `<NE>\`.

Flags clave:

- `--origen <dir>`: carpeta con los PDFs CRRP.
- `--destino <dir>`: raíz donde se crean las subcarpetas `<NE>\`.
- `--crear-carpetas`: crea `<NE>\` si no existe.
- `--mover`: mueve los PDFs (no copia).
- **`--hus-corto`**: SIDME/SIMED requiere `HUS<n>` sin ceros
  (`HUS0000409621` → `HUS409621`). **SIEMPRE pasar esto.**
- `--mapa <csv>`: si el PDF no trae la factura legible, completar desde un
  CSV NE→factura.
- `--en-sitio`: PDF ya está dentro de `<NE>\` (no usa --origen).

### Paso 2 — `tools/extraer_notas_credito.py`

Indexa el share UNC
`\\172.16.32.83\factura_electronica_net22\<periodo>\FACTURAS_NOTA\<NE>\` y
copia el contenido completo (RIPS/, .zip, XMLs, PDFs) por NE.

Flags:

- `--csv <ruta>` (o `--excel`/`--tsv`): archivo con columna `NOTA CREDITO`
  (acepta también `FACTURA HUS` como opcional).
- `--salida <dir>`: raíz local destino.
- `--no-fallback-recursivo`: no usar `rglob` cuando una nota no está en el
  índice (más rápido si confiás que está en un periodo conocido).

> **⚠️ WORKAROUND DOCUMENTADO**: el script puede colgarse con el `.zip`
> pesado de cada NE sobre red SMB lenta. **En ese caso usar PowerShell
> directo** para copiar SOLO `ad*.xml` y `RIPS\ResultadosDoker_*.json`:
>
> ```powershell
> $share = "\\172.16.32.83\factura_electronica_net22"
> $periodos = "202606","202605","202604","202603"
> foreach ($m in $mapeo) {  # mapeo = lista de @{ne; hus}
>   $destNE = "$destNotas\$($m.ne)"
>   foreach ($p in $periodos) {
>     $orig = "$share\$p\FACTURAS_NOTA\$($m.ne)"
>     if (Test-Path $orig) {
>       $xml = Get-ChildItem $orig -Filter "ad*.xml" -File | Select -First 1
>       $json = Get-ChildItem "$orig\RIPS" -Filter "ResultadosDoker_*.json" -File | Select -First 1
>       if ($xml)  { Copy-Item $xml.FullName  "$destNE\XML_$($m.ne)_HUS$($m.hus).xml"  -Force }
>       if ($json) { Copy-Item $json.FullName "$destNE\CUV_$($m.ne)_HUS$($m.hus).json" -Force }
>       break
>     }
>   }
> }
> ```

### Paso 3 — `tools/consolidar_carpetas_notas.py`

Por cada carpeta `<NE>\` deja solo 3 archivos finales:

- `NC_<NE>_HUS<n>.pdf`
- `XML_<NE>_HUS<n>.xml` (renombrado del `ad*.xml`)
- `CUV_<NE>_HUS<n>.json` (movido desde `RIPS\ResultadosDoker_*.json`)

Lo demás (`ar*.xml`, `nc*.xml` originales, .zip, carpeta RIPS) va a
`_papelera\<NE>\` (reversible).

Flags:

- `--destino <dir>`: raíz con `<NE>\`.
- `--aceptar-sin-json`: también consolida notas sin CUV (estado `OK_SIN_JSON`).
- `--borrar`: elimina extras en vez de mover a papelera.
- `--solo <NE>`: procesar solo esa carpeta.

### Paso 4 — `tools/verificar_cuv_notas.py`

Recorre el share por cada factura HUS y reporta el estado del CUV:

- `OK` — `ResultState:true`, CUV asignado por MinSalud.
- `RECHAZADO` — códigos típicos:
  - `RVC086` — diagnóstico relacionado igual al principal.
  - `RVC063` — medicamento inválido.
  - `TOT003` — timeout API SISPRO.
- `SIN_NOTA` — no aparece en ningún periodo del share.

Flags:

- `--lista <txt>`: TXT con 1 factura HUS por línea.
- `--facturas`: lista separada por comas.
- `--periodos`: YYYYMM por coma (default: todos los del share).
- `--reporte <csv>`: CSV de salida.

### Paso 5 — `tools/cargar_soportes_simed.py`

Bot Playwright que sube las **3 pasadas por factura** al portal SIMED:

1. **Pasada 1**: filtrar → editor (lápiz) → escribir NC → "Soportes NC" →
   subir los 3 archivos → Confirmar (modal de soportes).
2. **Pasada 2**: re-entrar al editor → re-escribir NC → Confirmar (form
   principal) para **PERSISTIR** la NC.
3. **Pasada 3**: click botón verde de la fila → confirmar popup
   "Registro completado".

Las 3 pasadas son necesarias porque GeneXus no persiste la NC junto con los
soportes en una sola pasada (workaround verificado en producción).

Flags:

- `--destino <dir>`: raíz con `<NE>\NC_/XML_/CUV_`.
- `--solo <NE>`: 1 sola nota.
- `--lista <csv>`: CSV con columna `NOTA CREDITO`.
- `--todas`: procesa todas las carpetas encontradas.
- `--con-cabeza`: browser visible (default headless).
- `--reporte <csv>`: salida.

### Estados posibles del cargue

| Estado | Significado |
|---|---|
| OK | las 3 pasadas se ejecutaron, "Registro completado" |
| YA_PROCESADA | el portal dice que ya tiene NC + soportes; se salta limpio |
| FALTAN_ARCHIVOS | falta PDF, XML o JSON en la carpeta |
| NO_EN_GRILLA | el filtro no devolvió la factura (ya procesada o no existe) |
| AMBIGUO | filtro devolvió >1 fila |
| RECHAZADA: <motivo> | el portal rechazó la NC (típico: "no corresponde con el CUV") |
| TIMEOUT | algún paso superó el límite |
| ERROR | excepción no clasificada (ver debug_screenshots\) |

## 6) Reglas críticas

- **HUS CORTO siempre** en `renombrar_y_organizar_notas` (`--hus-corto`).
  El portal rechaza el formato largo HUS0000XXXXXX.
- El bot escribe la NC con `page.keyboard.type()` (NO `fill()`) porque
  GeneXus valida la NC contra el CUV mediante eventos `keyup` reales.
- El modal "Mensajes" del portal con texto **"pendiente por cargar soportes
  obligatorios correspondientes a la NC. CUV, NC, XML,"** es INFORMATIVO,
  no error — el bot lo cierra automáticamente con Confirmar (fix del commit
  `1c590b4`).
- **Validar CUV ANTES de cargar.** Si `ResultState:false`, el portal acepta
  el upload pero la NC queda inválida. Hay que esperar a que SISTEMAS arregle
  el RIPS y MinSalud emita un nuevo CUV con `ResultState:true`.
- **Síntoma "Subida lista (después de 1s)"** en el log de la pasada 1: si
  aparece tan rápido es sospechoso, puede indicar que los archivos no se
  subieron y solo se detectó texto residual del iframe. Verificar manualmente
  o re-correr `--solo <NE>` con `--con-cabeza`.

## 7) Estado actual del lote V2 (al cerrar el chat anterior)

**Lote:** `D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\NOTAS\`

| Factura | NE | Estado |
|---|---|---|
| HUS404136 | 311131 | COMPLETA (copiar de `NOTAS_DISP_10\NOTAS\311131`) |
| HUS409574 | 311179 | COMPLETA |
| HUS410675 | 311136 | COMPLETA pero **CUV RECHAZADO RVC086** — no subir |
| HUS410979 | 311181 | COMPLETA |
| HUS411234 | 311147 | COMPLETA (copiar de `NOTAS_DISP_9\NOTAS\311147`) |
| HUS413266 | 311183 | sin PDF — descargar del DIAN |
| HUS416671 | 301906 | COMPLETA (periodo 202602, NE atípico fuera del rango 311xxx) |
| HUS417459 | 311186 | sin PDF — descargar del DIAN |
| HUS420099 | 311188 | ✅ Subida al SIMED |
| HUS421733 | 311190 | ✅ Subida |
| HUS418576 | 311194 | ✅ Subida |
| HUS420160 | 311197 | ✅ Subida |
| HUS422238 | 311199 | ✅ Subida |
| HUS428425 | 311203 | COMPLETA |
| HUS428523 | 311211 | COMPLETA |
| HUS431722 | 311213 | COMPLETA |
| HUS432292 | 311215 | COMPLETA |
| HUS432884 | 311219 | COMPLETA |
| HUS435485 | 311222 | ⚠ NC subió pero soportes pendientes — re-correr |
| HUS437357 | 311224 | COMPLETA |
| HUS437582 | 311228 | COMPLETA |
| HUS440328 | — | sin NE — pedir al área |

## 8) Próximos pasos pendientes

### A) Copiar HUS404136 y HUS411234 al lote V2

```powershell
$destNotas = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\NOTAS"
Copy-Item "D:\USUARIO CARTERA\Documents\NOTAS_DISP_10\NOTAS\311131" $destNotas -Recurse -Force
Copy-Item "D:\USUARIO CARTERA\Documents\NOTAS_DISP_9\NOTAS\311147"  $destNotas -Recurse -Force
```

### B) Re-correr HUS435485 + subir las 2 nuevas (HUS404136, HUS411234)

```powershell
$d = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2"
$lista3 = "$d\notas_3_pendientes.csv"

@(
  [PSCustomObject]@{"NOTA CREDITO"="311222"; "FACTURA HUS"="HUS435485"}
  [PSCustomObject]@{"NOTA CREDITO"="311131"; "FACTURA HUS"="HUS404136"}
  [PSCustomObject]@{"NOTA CREDITO"="311147"; "FACTURA HUS"="HUS411234"}
) | Export-Csv $lista3 -NoTypeInformation -Encoding UTF8

cd C:\temp-notas
git pull

py tools\cargar_soportes_simed.py `
  --destino "$d\NOTAS" `
  --lista $lista3 `
  --reporte "$d\rep_3_extras.csv"
```

### C) Resolver bloqueos pendientes

- **HUS410675 (NE 311136)**: escalar al área de SISTEMAS/RIPS por **RVC086**
  (diagnóstico relacionado igual al principal en el primer procedimiento del
  RIPS, periodo de atención 2025-08-08 a 2025-08-21). Cuando reemitan el
  RIPS y MinSalud lo apruebe, llega un nuevo CUV con `ResultState:true` y
  se puede subir.
- **HUS413266 y HUS417459**: descargar PDF CRRP del DIAN o buscar en otra
  carpeta del disco.
- **HUS440328**: pedir al área de facturación el número de NC asignado para
  esa factura.

## 9) Comandos de diagnóstico útiles

### Listar carpetas del lote y su estado

```powershell
$destNotas = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\NOTAS"
Get-ChildItem $destNotas -Directory | Sort-Object Name | ForEach-Object {
  $f = Get-ChildItem $_.FullName -File | Where-Object { $_.Name -match "^(NC|XML|CUV)_" }
  $tiene = ($f.Name | ForEach-Object { ($_ -split "_")[0] } | Sort-Object -Unique) -join "+"
  $estado = if ($tiene -eq "CUV+NC+XML") { "COMPLETA" } else { "FALTA: $tiene" }
  "[$($_.Name)] $estado"
}
```

### Verificar acceso al share

```powershell
Test-Path "\\172.16.32.83\factura_electronica_net22"
Get-ChildItem "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_NOTA\311136" |
  Select Name -First 5
```

### Buscar archivos de una factura específica en el disco

```powershell
Get-ChildItem "D:\USUARIO CARTERA\Documents" -Recurse -Include "*HUS<n>*" `
  -ErrorAction SilentlyContinue | Select Name, FullName | Format-Table -AutoSize
```

### Matar python colgado (UNC slow)

```powershell
Stop-Process -Name python, py -Force -ErrorAction SilentlyContinue
```

## 10) Reglas que el asistente NO debe romper

1. **NUNCA confundir SIMED con COOSALUD** o mezclar este flujo con el de
   respuesta de glosas (otra guía).
2. **NUNCA commitear passwords ni usuarios.** Solo en env vars.
3. **NUNCA incluir el identificador del modelo en commits, PRs, código
   pusheado.**
4. **Antes de cargar al SIMED, SIEMPRE validar CUV** con
   `verificar_cuv_notas.py`. Una NC con CUV rechazado se acepta en el portal
   pero queda inválida.
5. **No matar procesos** sin confirmar (excepto si el usuario lo pidió o
   están colgados >10 min).
6. **Cuando el usuario diga "ARMAME / SUBE",** chequear primero si el
   asistente realmente puede hacerlo (no tiene acceso al disco D: ni al
   share UNC) y, si no, dar el comando para que el usuario lo corra.
7. **`--hus-corto` siempre** en renombrar_y_organizar_notas.
8. **Modal "Mensajes"** del portal SIMED tras escribir la NC es informativo
   — el bot ya lo cierra automáticamente.
