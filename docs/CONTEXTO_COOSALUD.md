# Contexto HUS COOSALUD — Guía para iniciar un nuevo chat

> **Cómo usar este archivo:** pegá su contenido completo como primer mensaje en
> un nuevo chat de Claude Code y el asistente va a tener todo el contexto del
> proyecto para retomar el trabajo de COOSALUD desde donde quedó.

---

## 1) Quién soy y qué hago

- Soy auditor de cartera del **Hospital Universitario de Santander** (HUS,
  NIT 900006037-4), Bucaramanga, Colombia.
- Mi tarea acá: **responder glosas masivas** que la EPS COOSALUD impone a las
  facturas del HUS.
- Trabajo en Windows con PowerShell.

## 2) Plataforma

- COOSALUD usa el portal **vco.ctamedicas.com**.
- **NO es lo mismo que SIMED.** SIMED es para Dispensario Médico Bucaramanga
  (otra plataforma, otra guía). Si en alguna respuesta mezclás COOSALUD con
  SIMED es un error: pedíme aclaración antes de tipear comandos.

## 3) Repositorio de scripts

- **Path local en Windows:** `C:\temp-notas`
- **Repo:** `motor-glosas-hus`
- **Branch de trabajo:** `claude/excel-reconciliation-data-9Bnpj`
- Para sincronizar antes de cada corrida: `cd C:\temp-notas; git pull`

## 4) Credenciales

Siempre en **variables de entorno**, nunca hardcodeadas en código ni en
historial de comandos:

```cmd
setx COOSALUD_USER 680010079201
setx COOSALUD_PASSWORD <password>
```

Después cerrar y reabrir PowerShell para que las tome.

## 5) Script principal

`tools/responder_glosas_coosalud.py` — bot Playwright que:

1. Lee un Excel con glosas tipificadas (1 fila por glosa).
2. Por cada factura: filtra en la Bolsa o "En Pausa", agrupa por
   código+observación, marca checkboxes, elige código de respuesta del
   dropdown y envía.
3. Captura screenshot de evidencia al Terminar cada factura.
4. Genera reporte CSV con estado por factura.

### Columnas del Excel que el bot lee

| Columna | Uso |
|---|---|
| `numero_factura` | factura HUS (ej. HUS506047) |
| `id_glosa` | id único de cada glosa en el portal |
| `tipo_glosa` | PERTINENCIA / CALIDAD / TARIFAS / FACTURACION / SOPORTES |
| `codigo_glosa` | código de la glosa (ej. TA2901, CL0801) |
| `COD RESPUESTA GLOSA` | código corto + descripción (ej. "RE9901 - El prestador...") |
| `OBSERVACION RTA GLOSA` | texto de respuesta del HUS (sanitizado, sin tildes/ñ) |

### Flags importantes

- `--excel <ruta>`: Excel consolidado.
- `--hoja BASE` o `--hoja CALIDAD`: hoja a procesar.
- `--incluir-calidad`: responde también las glosas tipo CALIDAD con su texto
  del Excel. Sin este flag las CALIDAD se omiten y la factura queda abierta
  para el equipo médico.
- `--indice <txt>`: TXT con rutas del share UNC para hallar el PDX/HAM/PDE
  cuando un grupo es de tipo SOPORTES. Default:
  `D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt`.
- `--solo HUS<n>`: 1 sola factura.
- `--facturas "HUS<n>,HUS<n>,..."`: lista por coma.
- `--lista <txt>`: archivo TXT con 1 factura por línea.
- `--todas`: todas las facturas de la hoja.
- `--saltar-csv <csv>`: omite facturas con estado terminal en un reporte
  previo. Acepta el flag repetido para combinar varios CSVs.
  Estados terminales: `OK`, `OK_CALIDAD_ABIERTA`, `SOLO_CALIDAD`,
  `NO_EN_BOLSA`, `TERMINADA_SIN_CARTEL`.
- `--cerrar-residuales`: cuando el portal tiene glosas que el Excel no
  cubría (residuales), responderlas con código `RE9901` y un texto genérico
  de pertinencia y Terminar la factura.
- `--con-cabeza`: browser visible (default es headless).
- `--max-grupos N`: piloto rápido — responde como mucho N grupos por factura
  y NO Termina (deja en estado `PILOTO_PARCIAL`).
- `--reporte <csv>`: CSV de salida (modo write, sobrescribe).

### Estados posibles del reporte

| Estado | Significado |
|---|---|
| OK | factura cerrada, evidencia capturada |
| OK_CALIDAD_ABIERTA | calidad no respondida (sin --incluir-calidad), factura abierta para equipo médico |
| SOLO_CALIDAD | factura solo tenía CALIDAD |
| NO_EN_BOLSA | no está ni en Bolsa ni "En Pausa" (ya cerrada o no existe) |
| PENDIENTES | el Excel no cubría todas las glosas que el portal mostraba |
| PENDIENTE_PDX | un grupo SOPORTES sin PDF en el share |
| TERMINADA_SIN_CARTEL | terminó sin el cartel de éxito (verificar manualmente) |
| PILOTO_PARCIAL | --max-grupos cortó antes de Terminar |
| ERROR | excepción no clasificada (ver debug_screenshots\) |

## 6) Convenciones críticas

- **El bot abre `--reporte` en modo `"w"` — sobrescribe.** Para retomar una
  corrida usar nombres distintos (`reporte_pass2.csv`, `pass3.csv`) y pasar
  los anteriores como `--saltar-csv`.
- **PowerShell pierde variables entre ventanas.** Siempre redefinir `$excel`,
  `$indice` al empezar una sesión.
- **Modal de un solo uso:** el bot recarga la página entre grupos
  automáticamente (ya está en el código).
- **Tandas de ≤200:** facturas con >200 glosas se parten automáticamente.
- **Facturas grandes (1000+ glosas):** si el portal se satura, el bot
  reintenta 2 veces — la cuenta queda "En Pausa" y la siguiente corrida la
  encuentra ahí y continua.
- **`--cerrar-residuales` solo aplica para PENDIENTES**, no para `ERROR`.

## 7) Estado actual del lote 69 (al cerrar el chat anterior)

- **Excel:** `D:\USUARIO CARTERA\Downloads\CONSOLIDADO COOSALUD PERTINENCIA DIA 28 PERTINENCIA.xlsx`
- **Hoja:** `CALIDAD` (69 facturas, 31,515 glosas).
- **Reportes generados:**
  - `D:\USUARIO CARTERA\Documents\COOSALUD\reporte_calidad_full.csv` (pass1, 20 OK).
  - `D:\USUARIO CARTERA\Documents\COOSALUD\reporte_calidad_full_pass2.csv` (pass2, 39 OK).
- **Evidencias:** `D:\USUARIO CARTERA\Documents\COOSALUD\EVIDENCIA\HUS<n>_cierre.png`.

### Conteo combinado

| Estado | Cant. | Detalle |
|---|---|---|
| OK | 57 | cerradas con evidencia |
| NO_EN_BOLSA | 4 | HUS506670, HUS498646, HUS502038, HUS496818 (probablemente ya cerradas) |
| PENDIENTES | 7 | HUS502178, HUS501816, HUS500617, HUS503707, HUS500344, HUS498713, HUS502387 |
| ERROR | 1 | HUS506726 (dropdown no ofrecía RE9901 — ya resuelto en re-corrida con --max-grupos 1) |

## 8) Próximos pasos pendientes

### A) Pass3 — cerrar las 7 PENDIENTES con `--cerrar-residuales`

```powershell
$excel  = "D:\USUARIO CARTERA\Downloads\CONSOLIDADO COOSALUD PERTINENCIA DIA 28 PERTINENCIA.xlsx"
$indice = "D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt"

cd C:\temp-notas
git pull

py tools\responder_glosas_coosalud.py `
  --excel $excel `
  --hoja CALIDAD `
  --incluir-calidad `
  --indice $indice `
  --facturas "HUS502178,HUS501816,HUS500617,HUS503707,HUS500344,HUS498713,HUS502387" `
  --cerrar-residuales `
  --reporte "D:\USUARIO CARTERA\Documents\COOSALUD\reporte_residuales_pass3.csv"
```

### B) Cerrar HUS506726 (FACTURACION/TARIFAS, 204 glosas)

Re-correr sin `--max-grupos` para procesar los 3 grupos completos:

```powershell
py tools\responder_glosas_coosalud.py `
  --excel $excel --hoja CALIDAD --incluir-calidad --indice $indice `
  --solo HUS506726 `
  --reporte "D:\USUARIO CARTERA\Documents\COOSALUD\rep_HUS506726_final.csv"
```

### C) Word de evidencias

Una vez cerradas las 7 PENDIENTES, generar el Word con `tools/evidencias_a_word.py`:

```powershell
py tools\evidencias_a_word.py `
  --carpeta "D:\USUARIO CARTERA\Documents\COOSALUD\EVIDENCIA" `
  --salida  "D:\USUARIO CARTERA\Documents\COOSALUD\evidencias_lote69.docx" `
  --patron "*_cierre.png"
```

## 9) Comandos de diagnóstico útiles

### Ver el último comando que corrí

```powershell
Get-History | Where-Object { $_.CommandLine -match "responder_glosas_coosalud" } | Select -Last 3 CommandLine
```

### Filtrar reporte por estado

```powershell
$rep = "D:\USUARIO CARTERA\Documents\COOSALUD\reporte_calidad_full_pass2.csv"
Import-Csv $rep | Where-Object { $_.estado -notin "OK","NO_EN_BOLSA" } |
  Format-Table factura, estado, detalle -AutoSize
```

### Total acumulado de varias corridas

```powershell
$rep1 = "D:\USUARIO CARTERA\Documents\COOSALUD\reporte_calidad_full.csv"
$rep2 = "D:\USUARIO CARTERA\Documents\COOSALUD\reporte_calidad_full_pass2.csv"
$todos = @(Import-Csv $rep1) + @(Import-Csv $rep2)
$todos | Group-Object estado | Sort Count -Descending | Format-Table Name, Count -AutoSize
```

### Matar python colgado

```powershell
Stop-Process -Name python, py -Force -ErrorAction SilentlyContinue
Get-Process python, py -ErrorAction SilentlyContinue   # debe estar vacío
```

## 10) Reglas que el asistente NO debe romper

1. **Nunca confundir COOSALUD con SIMED/Dispensario.** Son plataformas distintas.
2. **Nunca commitear passwords ni usuarios.** Siempre env vars.
3. **Nunca incluir el identificador del modelo en commits, PR titles/bodies,
   o código pusheado.** Solo en chat.
4. **No matar procesos sin avisar** — preguntar antes (excepto cuando el
   usuario lo pidió explícitamente o el proceso está colgado >10 min).
5. **Cuando el usuario diga "ARMAME / RESUELVAME / SUBE",** chequear primero
   si el asistente realmente puede hacerlo (no hay acceso al disco D: ni al
   share UNC del HUS) y si no, dar el comando para que el usuario lo corra.
