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
9. **Directriz del 03-09-2026 — las CL médicas/mixtas NO las responde el bot.**
   Si la glosa es de tipo Médica o Mixta y el servicio tiene causal `CL`, el
   generador (`gen_lote.py`) la omite del cargue y la aísla en la hoja
   **"PARA GESTION MEDICA"** del mismo Excel: esas quedan a gestión manual del
   equipo médico. La razón: cuando el equipo médico revisa y acepta la glosa,
   debe cruzar una nota crédito — y una respuesta genérica ya cargada por el
   bot impide ese cruce y daña la conciliación. Las objeciones excluidas
   conservan su número de la grilla, así el robot responde las demás sin
   correrse de fila.

## El bot RPA del paquete GI (`bot_lote_dispensario.py`, 04-09-2026)

Orquesta el lote completo en un solo comando (pide el GI en pantalla):

    py tools\glosas_dispensario\bot_lote_dispensario.py --excel "D:\...\GLOSAS_X.xlsx"

1. Crea `D:\USUARIO CARTERA\Documents\<GI>\soportes`.
2. Genera las respuestas con `gen_lote.py` (hereda la directriz CL).
3. Recorre **una sola vez** las carpetas de radicación de `Y:` y arma el
   índice de soportes por factura, para copiar el PDF de cada una a
   `soportes`. Las carpetas vienen así:

       Y:\9.SEPTIEMBRE - SOPORTES RADICACION\DISPENSARIO\LILIANA\
           ENV-233972-OK\HUS552002\FEV_900006037_HUS552002.pdf

   o sea, una carpeta por factura con varios soportes adentro. El bot escoge
   el archivo `FEV_...` (la factura electrónica, que es la que trae el detalle
   del cobro) y, si no está, cualquier otro soporte de esa carpeta. Entre
   meses manda el más reciente.
4. Lee cada PDF con la cascada pdfplumber → PyPDF2 → OCR
   (`extraer_factura_pdf.py`) y ancla a la respuesta SOLO lo que se leyó
   (paciente y valor total). Nada leído = nada agregado.
5. Cruza cada glosa de tarifas con el tarifario del contrato 440
   (`tarifario_440.py`: anexo 6.2 de servicios por CUPS/código IPS y anexos
   de medicamentos por CUM) y cita la tarifa pactada exacta; sin
   coincidencia no cita nada.
6. **COTEJO DE COBRO** (ver abajo): compara lo que de verdad se facturó
   contra lo pactado y escribe el veredicto y la respuesta sugerida.
7. Corre el robot del portal (`--piloto HUS...` primero, siempre) y deja las
   evidencias de la corrida en `<GI>\<GI>_EVIDENCIAS.pdf`.

Con `--sin-cargue` prepara todo (carpeta, soportes, Excel enriquecido) sin
tocar el portal. Los tarifarios se pasan con `--tarifario-servicios` y
`--tarifario-medicamentos` (por defecto busca en
`D:\USUARIO CARTERA\Documents\TARIFARIO_440\`).

## El COTEJO DE COBRO (`cotejo_tarifa.py`, 04-09-2026)

Responde la pregunta que importa cuando la EPS glosa por mayor valor cobrado:
**¿de verdad estamos cobrando de más, y de cuánto?** El bot compara el valor
que leyó en el PDF de la factura contra la tarifa pactada en el anexo del
contrato 440 y escribe al lado de cada respuesta siete columnas nuevas:
VALOR FACTURADO (PDF), TARIFA PACTADA (440), DIFERENCIA, ¿SOBRECOBRO?,
VALOR SUGERIDO A ACEPTAR, RESPUESTA SUGERIDA y FUENTE DEL COTEJO. Lo que hay
que decidir queda además en la hoja **"COTEJO DE COBRO"**, que es el paquete
de trabajo del auditor, y en el archivo `cotejo_cobro_<GI>.json`.

Los veredictos:

| Veredicto | Qué significa | Qué sugiere |
|---|---|---|
| `SIN COTEJO` | no se leyó el PDF, el código no está pactado, o la línea trae varios valores y no se sabe cuál es el unitario | nada: revisar a mano |
| `COBRO A TARIFA` | lo facturado es exactamente lo pactado (± $2 de redondeo) | no aceptar, la glosa es infundada |
| `COBRO POR DEBAJO DE LO PACTADO` | se facturó menos que la tarifa | no aceptar |
| `MAYOR VALOR VERIFICADO` | se cobró de más y es un caso aislado | aceptar la diferencia (o lo objetado, lo que sea menor) |
| `MAYOR VALOR POR VIGENCIA` | se cobró de más, pero la misma diferencia porcentual se repite en el lote | no aceptar: sustentar con la resolución de tarifas del año |

Ese último veredicto es el que evita el error caro. En el lote del 04-09-2026,
24 facturas venían al 7% sobre el anexo y 19 al 31,25%: eso no es un error de
cobro, es la actualización de tarifas de la vigencia 2026 que los **parágrafos
3 y 4 del contrato 440** prevén (SOAT 2026 menos 20%, y para las tarifas
propias de la ESE un modificatorio que reconoce el incremento del año). Un
cotejo ingenuo habría sugerido aceptar glosas en todo el lote.

**El bot nunca acepta solo.** El Excel del cargue conserva `Valor Aceptado` en
0 y `RE9901`: la columna es una sugerencia para que el auditor decida y, si
acepta, la escriba él. Aceptar una glosa es decisión del hospital, y además
tiene que poder cruzar la nota crédito (misma razón de la directriz CL).
