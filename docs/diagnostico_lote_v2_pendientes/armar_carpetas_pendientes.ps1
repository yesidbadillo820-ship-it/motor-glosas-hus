# Arma D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\PENDIENTES_12\
# con una subcarpeta por cada una de las 12 facturas pendientes del Lote V2.
#
# Cada subcarpeta lleva:
#   - los archivos NC_/XML_/CUV_ que se tengan (copiados desde V2\NOTAS\<NE>\,
#     o desde NOTAS_DISP_9/NOTAS_DISP_10 cuando aplique).
#   - _ESTADO.txt con la ficha completa: factura, NE, radicado, valores,
#     causa por la que no se subio y proxima accion.
#
# El nombre de cada subcarpeta lleva un prefijo por causa raiz, asi un
# `dir` agrupa visualmente:
#   RVC086_HUS<n>_NE<ne>\
#   DOCKERRIPS_HUS<n>_NE<ne>\
#   SIN_PDF_HUS<n>_NE<ne>\
#   SIN_NE_HUS<n>\
#
# El script NO toca V2\NOTAS\ original — solo copia hacia PENDIENTES_12\.
# Es idempotente: si la subcarpeta existe, sobreescribe el _ESTADO.txt y
# vuelve a copiar los archivos con -Force.
#
# Uso:
#   cd C:\temp-notas
#   powershell -ExecutionPolicy Bypass -File `
#     docs\diagnostico_lote_v2_pendientes\armar_carpetas_pendientes.ps1

$ErrorActionPreference = "Stop"

$baseLote      = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2"
$baseV2        = Join-Path $baseLote "NOTAS"
$destPendientes= Join-Path $baseLote "PENDIENTES_12"
$origenDisp9   = "D:\USUARIO CARTERA\Documents\NOTAS_DISP_9\NOTAS"
$origenDisp10  = "D:\USUARIO CARTERA\Documents\NOTAS_DISP_10\NOTAS"

# Las 12 facturas con toda su metadata. Mantener este array sincronizado con
# docs\diagnostico_lote_v2_pendientes\estado_facturas.md
$facturas = @(
  [PSCustomObject]@{
    Causa="RVC086"; HUS="HUS404136"; FacturaFull="HUS0000404136"; NE="311131"; NE_TSV="263272"
    Radicado="457325"; Acta="AC000456"
    ValorFactura="$ 2.169.054"; TotalGlosas="$ 61.708"; ValorAceptado="$ 10.218"
    OrigenAlt=(Join-Path $origenDisp10 "311131")
    EstadoCausa="RIPS rechazado por MinSalud - RVC086 (Codigo de diagnostico repetido)"
    Detalle="El RIPS tiene un diagnostico relacionado igual al principal en el primer procedimiento. MinSalud lo rechaza automaticamente. El CUV en disco (CUV_311131_HUS404136.json) trae ResultState:false."
    QueFalta="CUV valido con ResultState:true."
    Accion="Escalar a SISTEMAS/RIPS para reemitir el RIPS con diagnostico relacionado distinto al principal. Cuando llegue nuevo CUV con ResultState:true, recien subir al SIMED."
  }
  [PSCustomObject]@{
    Causa="DOCKERRIPS"; HUS="HUS411234"; FacturaFull="HUS0000411234"; NE="311147"; NE_TSV="263288"
    Radicado="460616"; Acta="AC000456"
    ValorFactura="$ 812.155"; TotalGlosas="$ 115.942"; ValorAceptado="$ 12.589"
    OrigenAlt=(Join-Path $origenDisp9 "311147")
    EstadoCausa="CUV invalido - servicio dockerrips.hus.gov.co:9443 caido al validar (connection refused)"
    Detalle="El archivo CUV_311147_HUS411234.json no es un CUV: contiene el mensaje de error que devolvio el servicio interno del HUS al intentar validar el RIPS contra MinSalud."
    QueFalta="CUV valido (regenerar el RIPS contra MinSalud cuando dockerrips este UP)."
    Accion="Escalar a SISTEMAS para reintentar el envio del RIPS y regenerar el ResultadosDoker_<NE>.json. Despues re-correr consolidar_carpetas_notas + verificar_cuv_notas + cargar_soportes_simed --solo 311147."
  }
  [PSCustomObject]@{
    Causa="RVC086"; HUS="HUS410675"; FacturaFull="HUS0000410675"; NE="311136"; NE_TSV="263284"
    Radicado="462915"; Acta="AC000456"
    ValorFactura="$ 7.390.337"; TotalGlosas="$ 245.072"; ValorAceptado="$ 245.072"
    OrigenAlt=$null
    EstadoCausa="RIPS rechazado por MinSalud - RVC086 (Codigo de diagnostico repetido)"
    Detalle="Periodo de atencion 2025-08-08 a 2025-08-21. Diagnostico relacionado igual al principal en el primer procedimiento."
    QueFalta="CUV valido con ResultState:true."
    Accion="Mismo correo a SISTEMAS junto con HUS404136 y HUS435485 - RVC086."
  }
  [PSCustomObject]@{
    Causa="SIN_PDF"; HUS="HUS413266"; FacturaFull="HUS0000413266"; NE="311183"; NE_TSV="263303"
    Radicado="492346"; Acta="AC000456"
    ValorFactura="$ 4.237.047"; TotalGlosas="$ 458.490"; ValorAceptado="$ 458.490"
    OrigenAlt=$null
    EstadoCausa="Carpeta no existe en V2 - falta el PDF CRRP de la NC"
    Detalle="Sin el PDF la carpeta no se puede completar (consolidar_carpetas_notas exige la triada NC+XML+CUV)."
    QueFalta="PDF CRRP de la NC (NC_311183_HUS413266.pdf)."
    Accion="Descargar PDF CRRP del DIAN usando radicado 492346. Renombrar a NC_311183_HUS413266.pdf, ponerlo en la carpeta y correr el pipeline desde extraer_notas_credito."
  }
  [PSCustomObject]@{
    Causa="SIN_PDF"; HUS="HUS417459"; FacturaFull="HUS0000417459"; NE="311186"; NE_TSV="234326"
    Radicado="521665"; Acta=""
    ValorFactura="$ 16.632.959"; TotalGlosas="$ 4.282.669"; ValorAceptado="$ 2.728.811"
    OrigenAlt=$null
    EstadoCausa="Carpeta no existe en V2 - falta el PDF CRRP de la NC"
    Detalle="Igual que HUS413266: sin PDF no se puede completar la triada."
    QueFalta="PDF CRRP de la NC (NC_311186_HUS417459.pdf)."
    Accion="Descargar PDF CRRP del DIAN usando radicado 521665 y armar carpeta NE 311186."
  }
  [PSCustomObject]@{
    Causa="DOCKERRIPS"; HUS="HUS420099"; FacturaFull="HUS0000420099"; NE="311188"; NE_TSV="243804"
    Radicado="560611"; Acta="AC000619"
    ValorFactura="$ 3.757.260"; TotalGlosas="$ 161.635"; ValorAceptado="$ 79.407"
    OrigenAlt=$null
    EstadoCausa="CUV invalido - servicio dockerrips.hus.gov.co:9443 caido al validar (timeout)"
    Detalle="El contexto V2 la marcaba como Subida OK, pero el CUV en disco no es valido - es el mensaje de error de conexion. El bot subio al SIMED y el portal la dejo en limbo (NC sin CUV valido)."
    QueFalta="CUV valido (regenerar contra MinSalud)."
    Accion="SISTEMAS regenera CUV. Despues re-correr cargar_soportes_simed --solo 311188 --con-cabeza."
  }
  [PSCustomObject]@{
    Causa="DOCKERRIPS"; HUS="HUS421733"; FacturaFull="HUS0000421733"; NE="311190"; NE_TSV="243806"
    Radicado="560613"; Acta=""
    ValorFactura="$ 20.627.343"; TotalGlosas="$ 2.111.169"; ValorAceptado="$ 108.024"
    OrigenAlt=$null
    EstadoCausa="CUV invalido - servicio dockerrips.hus.gov.co:9443 caido al validar (timeout)"
    Detalle="Mismo caso que HUS420099."
    QueFalta="CUV valido."
    Accion="SISTEMAS regenera CUV. Despues re-correr cargar_soportes_simed --solo 311190."
  }
  [PSCustomObject]@{
    Causa="DOCKERRIPS"; HUS="HUS418576"; FacturaFull="HUS0000418576"; NE="311194"; NE_TSV="243803"
    Radicado="562326"; Acta=""
    ValorFactura="$ 2.518.999"; TotalGlosas="$ 1.195.740"; ValorAceptado="$ 1.195.740"
    OrigenAlt=$null
    EstadoCausa="CUV invalido - servicio dockerrips.hus.gov.co:9443 caido al validar (timeout)"
    Detalle="Mismo caso que HUS420099."
    QueFalta="CUV valido."
    Accion="SISTEMAS regenera CUV. Despues re-correr cargar_soportes_simed --solo 311194."
  }
  [PSCustomObject]@{
    Causa="DOCKERRIPS"; HUS="HUS420160"; FacturaFull="HUS0000420160"; NE="311197"; NE_TSV="243805"
    Radicado="568849"; Acta="AC000619"
    ValorFactura="$ 4.170.179"; TotalGlosas="$ 42.800"; ValorAceptado="$ 42.800"
    OrigenAlt=$null
    EstadoCausa="CUV invalido - servicio dockerrips.hus.gov.co:9443 caido al validar (timeout)"
    Detalle="Mismo caso que HUS420099."
    QueFalta="CUV valido."
    Accion="SISTEMAS regenera CUV. Despues re-correr cargar_soportes_simed --solo 311197."
  }
  [PSCustomObject]@{
    Causa="DOCKERRIPS"; HUS="HUS422238"; FacturaFull="HUS0000422238"; NE="311199"; NE_TSV=""
    Radicado=""; Acta=""
    ValorFactura=""; TotalGlosas=""; ValorAceptado=""
    OrigenAlt=$null
    EstadoCausa="CUV invalido - servicio dockerrips.hus.gov.co:9443 caido al validar (timeout). NE no figura en TSV historico."
    Detalle="Mismo caso que HUS420099. Confirmar tambien con facturacion que el NE 311199 corresponde efectivamente a HUS422238 (no esta en el TSV)."
    QueFalta="CUV valido + confirmacion del NE."
    Accion="SISTEMAS regenera CUV. Facturacion confirma 311199 <-> HUS422238. Despues re-correr cargar_soportes_simed --solo 311199."
  }
  [PSCustomObject]@{
    Causa="RVC086"; HUS="HUS435485"; FacturaFull="HUS0000435485"; NE="311222"; NE_TSV="264792"
    Radicado="637718"; Acta=""
    ValorFactura="$ 27.102.523"; TotalGlosas="$ 1.662.440"; ValorAceptado="$ 1.662.440"
    OrigenAlt=$null
    EstadoCausa="RIPS rechazado por MinSalud - RVC086 (Codigo de diagnostico repetido)"
    Detalle="El contexto V2 la marcaba como 'NC subio pero soportes pendientes - re-correr'. La causa real es RVC086: el portal acepto la NC pero los soportes obligatorios quedaron en limbo porque el CUV es invalido. Re-correr el bot NO sirve - hay que arreglar el RIPS."
    QueFalta="CUV valido con ResultState:true."
    Accion="Mismo correo a SISTEMAS junto con HUS404136 y HUS410675 - RVC086."
  }
  [PSCustomObject]@{
    Causa="SIN_NE"; HUS="HUS440328"; FacturaFull="HUS0000440328"; NE=""; NE_TSV="302111"
    Radicado="670496"; Acta=""
    ValorFactura="$ 19.152.692"; TotalGlosas="$ 13.553.900"; ValorAceptado="$ 2.168.866"
    OrigenAlt=$null
    EstadoCausa="Sin NE V2 asignado"
    Detalle="El TSV historico tiene NE 302111 pero el contexto V2 dice 'sin NE'. Hay discrepancia: o el NE 302111 fue anulado y nadie lo notifico, o sigue vigente y el contexto V2 quedo desactualizado."
    QueFalta="Confirmacion del NE vigente."
    Accion="Preguntar al area de facturacion: '?La factura HUS0000440328 tiene NC vigente 302111 o se emitio una nueva NC con NE distinto?' Si la respuesta es 302111, armar la carpeta y correr el pipeline."
  }
)

# --- Funciones auxiliares ---

function Copiar-Archivos-NC($origen, $destino) {
  if (-not (Test-Path $origen)) { return @() }
  $copiados = @()
  $patrones = @("NC_*.pdf", "XML_*.xml", "CUV_*.json")
  foreach ($pat in $patrones) {
    $items = Get-ChildItem -Path $origen -Filter $pat -File -ErrorAction SilentlyContinue
    foreach ($it in $items) {
      Copy-Item -Path $it.FullName -Destination (Join-Path $destino $it.Name) -Force
      $copiados += $it.Name
    }
  }
  return $copiados
}

function Generar-EstadoTxt($f, $destinoCarpeta, $archivosCopiados, $origenesUsados) {
  $hoy = (Get-Date).ToString("yyyy-MM-dd HH:mm")
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.AppendLine("=== ESTADO DE LA NOTA CREDITO ===")
  [void]$sb.AppendLine("Generado: $hoy")
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("Factura HUS    : $($f.FacturaFull)")
  [void]$sb.AppendLine("HUS corto      : $($f.HUS)")
  [void]$sb.AppendLine("NE V2 (vigente): $(if ($f.NE) { $f.NE } else { '(sin asignar)' })")
  [void]$sb.AppendLine("NE TSV historico: $(if ($f.NE_TSV) { $f.NE_TSV } else { '(no figura)' })")
  [void]$sb.AppendLine("Radicado       : $(if ($f.Radicado) { $f.Radicado } else { '(s/d)' })")
  [void]$sb.AppendLine("Acta           : $(if ($f.Acta) { $f.Acta } else { '(s/d)' })")
  [void]$sb.AppendLine("Valor Factura  : $(if ($f.ValorFactura) { $f.ValorFactura } else { '(s/d)' })")
  [void]$sb.AppendLine("Total Glosas   : $(if ($f.TotalGlosas) { $f.TotalGlosas } else { '(s/d)' })")
  [void]$sb.AppendLine("Valor Aceptado : $(if ($f.ValorAceptado) { $f.ValorAceptado } else { '(s/d)' })")
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("--- Causa por la que no se subio ---")
  [void]$sb.AppendLine($f.EstadoCausa)
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("Detalle: $($f.Detalle)")
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("--- Que falta ---")
  [void]$sb.AppendLine($f.QueFalta)
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("--- Proxima accion ---")
  [void]$sb.AppendLine($f.Accion)
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("--- Archivos en esta carpeta ---")
  if ($archivosCopiados.Count -eq 0) {
    [void]$sb.AppendLine("(ninguno - la carpeta esta vacia porque no hay archivos en disco para esta factura)")
  } else {
    foreach ($a in $archivosCopiados) { [void]$sb.AppendLine("  - $a") }
  }
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("--- Origen de los archivos ---")
  if ($origenesUsados.Count -eq 0) {
    [void]$sb.AppendLine("(sin archivos para copiar)")
  } else {
    foreach ($o in $origenesUsados) { [void]$sb.AppendLine("  - $o") }
  }
  Set-Content -Path (Join-Path $destinoCarpeta "_ESTADO.txt") -Value $sb.ToString() -Encoding UTF8
}

# --- Ejecucion ---

Write-Host ""
Write-Host "=== ARMADO DE PENDIENTES_12 ===" -ForegroundColor Cyan
Write-Host "Destino: $destPendientes"
Write-Host ""

if (-not (Test-Path $baseLote)) {
  Write-Error "No existe el lote V2: $baseLote"
  exit 1
}

if (-not (Test-Path $destPendientes)) {
  New-Item -Path $destPendientes -ItemType Directory | Out-Null
  Write-Host "Creada raiz: $destPendientes" -ForegroundColor Green
}

$resumen = @()

foreach ($f in $facturas) {
  $sufijo = if ($f.NE) { "$($f.HUS)_NE$($f.NE)" } else { "$($f.HUS)" }
  $nombreCarpeta = "$($f.Causa)_$sufijo"
  $destCarpeta = Join-Path $destPendientes $nombreCarpeta

  if (-not (Test-Path $destCarpeta)) {
    New-Item -Path $destCarpeta -ItemType Directory | Out-Null
  }

  $archivos = @()
  $origenes = @()

  # 1) Si existe la carpeta NE en V2, copiar de ahi.
  if ($f.NE) {
    $rutaV2 = Join-Path $baseV2 $f.NE
    if (Test-Path $rutaV2) {
      $copiados = Copiar-Archivos-NC $rutaV2 $destCarpeta
      if ($copiados.Count -gt 0) {
        $archivos += $copiados
        $origenes += "$rutaV2  (V2\NOTAS)"
      }
    }
  }

  # 2) Si tiene origen alterno (DISP_9 / DISP_10), copiar lo que no haya quedado.
  if ($f.OrigenAlt -and (Test-Path $f.OrigenAlt)) {
    $copiados = Copiar-Archivos-NC $f.OrigenAlt $destCarpeta
    if ($copiados.Count -gt 0) {
      foreach ($c in $copiados) { if ($archivos -notcontains $c) { $archivos += $c } }
      $origenes += "$($f.OrigenAlt)  (lote anterior)"
    }
  }

  Generar-EstadoTxt $f $destCarpeta $archivos $origenes

  $estadoTxtPath = (Join-Path $destCarpeta "_ESTADO.txt")
  $color = switch ($f.Causa) {
    "RVC086"     { "Red" }
    "DOCKERRIPS" { "Magenta" }
    "SIN_PDF"    { "Yellow" }
    "SIN_NE"     { "Yellow" }
    default      { "White" }
  }
  Write-Host ("[{0}]  archivos={1}  -> {2}" -f $f.HUS, $archivos.Count, $nombreCarpeta) -ForegroundColor $color

  $resumen += [PSCustomObject]@{
    Carpeta        = $nombreCarpeta
    Factura        = $f.FacturaFull
    NE_V2          = $f.NE
    Causa          = $f.Causa
    ArchivosCopiados = $archivos.Count
    Origenes       = ($origenes -join " | ")
  }
}

# Resumen.csv dentro de PENDIENTES_12 para que tambien quede ahi.
$resumenPath = Join-Path $destPendientes "_INDICE_PENDIENTES.csv"
$resumen | Export-Csv -Path $resumenPath -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "Indice: $resumenPath" -ForegroundColor Cyan
Write-Host "Listo. $($resumen.Count) carpetas armadas en $destPendientes" -ForegroundColor Green
