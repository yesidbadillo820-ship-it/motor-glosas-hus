# Contexto HUS Dispensario — Respuesta de Glosas (SIMED)

> **Cómo usar este archivo:** pegá su contenido completo como primer mensaje en
> un nuevo chat de Claude Code y el asistente va a tener todo el contexto del
> flujo de **RESPUESTA DE GLOSAS** del Dispensario.
>
> **Este archivo NO cubre el cargue de notas crédito.** Para eso usá
> `docs/CONTEXTO_DISPENSARIO_NOTAS.md` en otro chat.

---

## 1) Quién soy y qué hago

- Soy auditor de cartera del **Hospital Universitario de Santander** (HUS,
  NIT 900006037-4), Bucaramanga, Colombia.
- Mi tarea en este flujo: **responder glosas masivas** del Dispensario
  Médico Bucaramanga (DMBUG) en el portal SIMED.
- Trabajo en Windows con PowerShell.

## 2) Plataforma

- DMBUG usa el portal **SIMED** en `auditool25.tool.com.co`.
- **ESTO ES PARA DISPENSARIO MEDICO, NO PARA COOSALUD.** COOSALUD usa
  `vco.ctamedicas.com` (otra guía aparte).
- En este flujo respondemos **objeciones glosa por glosa** (NO subimos
  notas crédito — eso es otro proceso/otra guía).
- La página del portal que usa el bot es **"Respuesta Glosa Rad. WEB"**
  (`glosasfacturaww.aspx`).

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

## 5) Pipeline de respuesta de glosas (2 pasos)

```
PDFs CRRP de Trámite de Objeción (uno por factura)
    │
    ├─ 1. extraer_respuestas_glosa.py
    │       → lee los PDFs y genera Excel con 1 fila por objeción
    │
    └─ 2. responder_glosas_simed.py
            → recorre cada factura, abre cada objeción y carga la respuesta
```

### Paso 1 — `tools/extraer_respuestas_glosa.py`

Lee uno o varios PDFs CRRP de "Trámite de Objeción" del HUS y produce un
Excel con UNA FILA POR OBJECIÓN.

Cada PDF representa una factura con N objeciones. El script extrae:

- N° de factura HUS.
- Para cada objeción: código (TA020, SO070, FA0203, RE9901, etc.), valor
  objetado, valor aceptado, servicio (ej. "734005 - LABORATORIO"), y el
  texto de "Observaciones:" como respuesta del HUS.

Flags:

- `--pdf <archivo>`: un solo PDF.
- `--carpeta <dir>`: carpeta con varios PDFs (uno por factura).
- `--salida <ruta>`: archivo `.xlsx` de salida.

Columnas del Excel generado:

| Columna | Uso |
|---|---|
| `Factura` | HUS0000XXXXXX |
| `# Objeción` | 1, 2, 3, ... |
| `Cód.` | código de la glosa (ej. TA020, FA0203) |
| `Servicio` | descripción del servicio glosado |
| `Valor Objetado` | valor que la EPS objetó |
| `Valor Aceptado` | valor que el HUS acepta (típicamente $0 si rechaza) |
| `Detalle Respuesta` | texto del HUS, sanitizado (sin tildes/ñ) |

Después de generar el Excel, **revisarlo en Excel** y ajustar Aceptado/
Detalle si es necesario antes de pasarlo al responder.

### Paso 2 — `tools/responder_glosas_simed.py`

Bot Playwright que recorre las objeciones una por una en el portal SIMED:

1. **Login** (una sola vez).
2. Por cada factura del Excel:
   - Va a `glosasfacturaww.aspx` (Respuesta Glosa Rad. WEB).
   - Filtra por `# Factura`.
   - Click en el lápiz → abre "Glosas Factura".
   - Para cada objeción 1..N del Excel:
     - Click en el ícono de la fila → abre modal "Respuesta Glosa Ips Web".
     - Tab "Información Glosa": escribe Aceptado, deja NC vacío, escribe el
       Detalle Respuesta sanitizado.
     - Tab "Soportes": sube el PDF de soporte + archivos del share.
     - Click "Confirmar" del modal.
   - Click "Confirmar" del form principal.
   - Click botón verde (Enviar/Finalizar) → espera "Registro completado".
3. Genera reporte CSV con estado por factura.

Flags:

- `--excel <ruta>`: Excel generado por extraer_respuestas_glosa.
- `--soportes-glosa <dir>`: carpeta con `HUS<n>.pdf` (PDF de Trámite que se
  adjunta a cada objeción).
- `--indice <txt>`: TXT con rutas del share por factura (para soportes
  adicionales). Default: `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt`.
- `--solo HUS<n>`: 1 sola factura (piloto).
- `--todas`: todas las facturas del Excel.
- `--rehacer`: re-procesa objeciones marcadas como "ya contestadas".
- `--max-obj N`: piloto rápido — máx N objeciones por factura.
- `--sin-soportes`: solo carga texto + fecha, NO sube PDFs. Mucho más rápido
  y evita que la subida trabe el cierre del modal.
- `--con-cabeza`: browser visible (default headless).
- `--lento`: slow-motion 300ms (debug).
- `--reporte <csv>`: CSV de salida.

### Estados posibles del reporte

| Estado | Significado |
|---|---|
| OK | "X respondidas, Y omitidas" |
| NO_PENDIENTE | "Factura no está en pendientes" (ya finalizada) |
| MENSAJE: <texto> | el portal devolvió un mensaje informativo |
| ERROR | excepción no clasificada |

## 6) Reglas críticas

- El bot detecta automáticamente si una objeción ya está contestada
  (`span FCTOBJEST == "Contestado"`) y la omite (a menos que pases `--rehacer`).
- El bot escanea **hasta 12 páginas** de la grilla buscando cada objeción
  por su número exacto. Si no la encuentra, marca como "no hallada".
- **El portal del DMBUG puede CONSOLIDAR objeciones**: el PDF de Trámite
  puede traer N objeciones pero el portal solo mostrar M (con M < N) si el
  DMBUG agrupó por servicio. Caso real: HUS513270 traía 17 objeciones (4
  TA010 separadas con valores $615k+$184k+$1107k+$123k) y el portal mostró
  14 con la #14 consolidando esos 4 valores en $2,029,500. Las 3 "no
  halladas" no faltaban — estaban sumadas.
- **Verificación matemática para confirmar consolidación:** sumar las
  objeciones "no halladas" y comparar con el valor de la última objeción
  del portal. Si coincide, está OK.
- El modal "Mensajes" tras Confirmar puede demorar; el bot usa retries de 2
  intentos antes de fallar. Si falla, marca como "modal no cerró" y reintenta.
- Si el portal muestra "esta objeción ya tiene soportes cargados", el bot
  salta la re-subida (idempotente).

## 7) Estado actual del último lote (al cerrar el chat anterior)

**Lote del 22/06/2026** (8 facturas, 24 objeciones totales):

| Factura | Objeciones | Estado |
|---|---|---|
| HUS0000512599 | 1 | ✅ OK (piloto) |
| HUS0000512914 | 1 | ✅ OK |
| HUS0000512938 | 1 | ✅ OK |
| HUS0000513090 | 1 | ✅ OK |
| HUS0000513270 | 17 | ✅ OK (14 respondidas — las 3 últimas TA010 las consolidó el portal en la #14) |
| HUS0000513485 | 1 | ✅ OK |
| HUS0000513998 | 1 | ✅ OK |
| HUS0000514285 | 1 | ✅ OK |

**Tiempo total:** 26.9 minutos. **Resultado:** 7 facturas subidas + 1
NO_PENDIENTE (la del piloto ya estaba cerrada).

**Archivos:**

- PDFs Trámite: `D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_22-06\SOPORTES\`
- Excel respuestas: `D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_22-06\respuestas_glosa.xlsx`
- Reporte: `D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_22-06\rep_glosa.csv`

## 8) Próximos pasos pendientes

No hay tareas en curso. Cuando llegue el próximo lote:

### Receta estándar

```powershell
# Variables del lote
$baseGlo  = "D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_<fecha>"
$soportes = "$baseGlo\SOPORTES"
$excelResp = "$baseGlo\respuestas_glosa.xlsx"
$indice   = "D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt"

# 1. Descomprimir el ZIP con los PDFs (verificar el path real del ZIP en Downloads)
New-Item -Force -ItemType Directory $soportes | Out-Null
Expand-Archive -Path "D:\USUARIO CARTERA\Downloads\<NOMBRE>.zip" -DestinationPath $soportes -Force
Get-ChildItem $soportes   # listar los PDFs HUS<n>.pdf

# 2. Generar Excel desde los PDFs de trámite
cd C:\temp-notas
git pull
py tools\extraer_respuestas_glosa.py --carpeta $soportes --salida $excelResp

# 3. Revisar el Excel y guardar (ajustar Valor Aceptado o Detalle si hace falta)
Start-Process $excelResp

# 4. Piloto con la factura más chica
py tools\responder_glosas_simed.py `
  --excel $excelResp --soportes-glosa $soportes --indice $indice `
  --solo HUS<n> --con-cabeza --reporte "$baseGlo\rep_piloto.csv"

# 5. Si el piloto pasa OK, masivo
py tools\responder_glosas_simed.py `
  --excel $excelResp --soportes-glosa $soportes --indice $indice `
  --todas --reporte "$baseGlo\rep_glosa.csv"
```

### Si el lote es solo texto (sin subir PDFs por objeción)

```powershell
py tools\responder_glosas_simed.py --excel $excelResp --todas --sin-soportes `
  --reporte "$baseGlo\rep_glosa_sin_sop.csv"
```

## 9) Comandos de diagnóstico útiles

### Ver cuántas objeciones detectó por factura el extractor

El log del paso 1 muestra una línea por PDF tipo:

```
HUS512599.pdf → factura HUS0000512599: 1 objeciones, total objetado $38,200
HUS513270.pdf → factura HUS0000513270: 17 objeciones, total objetado $2,171,612
```

Si una factura debería tener N objeciones según el PDF y el script reporta
M ≠ N, hay un bug en la regex o el PDF cambió de formato. Pedir al
asistente que revise `RE_BLOQUE` en el código.

### Ver el reporte por estado

```powershell
$rep = "D:\USUARIO CARTERA\Documents\GLOSAS_2026\DISPENSARIO_<fecha>\rep_glosa.csv"
Import-Csv $rep | Group-Object estado | Format-Table Name, Count -AutoSize
Import-Csv $rep | Where-Object { $_.estado -ne "OK" } | Format-Table factura, estado, detalle -AutoSize
```

### Verificar visualmente qué muestra el portal para una factura

Si el bot reporta "X objeciones no halladas en la grilla del portal":

1. Abrí el portal manualmente.
2. Busca la factura en `glosasfacturaww.aspx`.
3. Click en el lápiz.
4. Mirá cuántas filas tiene la grilla "Respuesta Glosa Ips".
5. Si el portal tiene menos objeciones que el PDF, probablemente las consolidó
   (sumar los valores de las "no halladas" y comparar con el valor de la
   última objeción del portal para confirmar).

### Matar python colgado

```powershell
Stop-Process -Name python, py -Force -ErrorAction SilentlyContinue
```

## 10) Reglas que el asistente NO debe romper

1. **NUNCA confundir SIMED con COOSALUD** o este flujo con el de cargue de
   notas crédito (otra guía).
2. **NUNCA commitear passwords ni usuarios.** Solo en env vars.
3. **NUNCA incluir el identificador del modelo en commits, PRs, código
   pusheado.**
4. **Antes de un masivo, SIEMPRE pasar por un piloto** (`--solo HUS<n>
   --con-cabeza --max-obj 1`) para verificar que el portal acepta el formato
   y los selectores siguen vigentes.
5. **No asumir que "no hallada" es error.** Verificar matemáticamente si el
   portal consolidó objeciones (sumar valores).
6. **No matar procesos** sin confirmar (excepto si el usuario lo pidió o
   están colgados >10 min).
7. **Cuando el usuario diga "SUBE LAS RESPUESTAS",** chequear primero si el
   asistente realmente puede hacerlo (no tiene acceso al portal ni al
   Windows) y, si no, dar el comando para que el usuario lo corra.
8. **El portal del DMBUG NO siempre tiene `RE9901`** como código de respuesta
   válido — depende del tipo de glosa. Si el dropdown rechaza el código del
   Excel, mirar qué códigos ofrece el portal y ajustar el Excel.
