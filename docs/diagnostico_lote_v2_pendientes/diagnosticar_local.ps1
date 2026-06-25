# Diagnostico local de las 12 facturas pendientes del Lote V2
#
# Que hace:
#   - Para cada factura/NE V2, verifica si existe la carpeta en el V2 y si tiene
#     los 3 archivos finales (NC_/XML_/CUV_).
#   - Para las facturas que se esperan en lotes anteriores (DISP_9/DISP_10),
#     reporta si la carpeta origen existe.
#   - Si el CUV JSON existe, lo parsea y muestra ResultState + Codigo de
#     rechazo.
#   - Exporta todo a reporte_diagnostico.csv en esta misma carpeta.
#
# Uso:
#   cd C:\temp-notas
#   powershell -ExecutionPolicy Bypass -File `
#     docs\diagnostico_lote_v2_pendientes\diagnosticar_local.ps1
#
# Ajustar $baseV2 si tu disco no coincide.

$ErrorActionPreference = "Stop"

$baseV2     = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\NOTAS"
$origenDisp9  = "D:\USUARIO CARTERA\Documents\NOTAS_DISP_9\NOTAS"
$origenDisp10 = "D:\USUARIO CARTERA\Documents\NOTAS_DISP_10\NOTAS"

$reporteSalida = Join-Path $PSScriptRoot "reporte_diagnostico.csv"

# Listado de las 12 facturas con su NE V2 (segun docs/CONTEXTO_DISPENSARIO_NOTAS.md)
$facturas = @(
  [PSCustomObject]@{ Factura="HUS0000404136"; HUS="HUS404136"; NE_V2="311131"; NE_TSV="263272"; OrigenAlt=Join-Path $origenDisp10 "311131"; Motivo="Copiar de NOTAS_DISP_10" }
  [PSCustomObject]@{ Factura="HUS0000411234"; HUS="HUS411234"; NE_V2="311147"; NE_TSV="263288"; OrigenAlt=Join-Path $origenDisp9  "311147"; Motivo="Copiar de NOTAS_DISP_9"  }
  [PSCustomObject]@{ Factura="HUS0000410675"; HUS="HUS410675"; NE_V2="311136"; NE_TSV="263284"; OrigenAlt=$null; Motivo="CUV RECHAZADO RVC086 - NO subir" }
  [PSCustomObject]@{ Factura="HUS0000413266"; HUS="HUS413266"; NE_V2="311183"; NE_TSV="263303"; OrigenAlt=$null; Motivo="Sin PDF - descargar DIAN" }
  [PSCustomObject]@{ Factura="HUS0000417459"; HUS="HUS417459"; NE_V2="311186"; NE_TSV="234326"; OrigenAlt=$null; Motivo="Sin PDF - descargar DIAN" }
  [PSCustomObject]@{ Factura="HUS0000420099"; HUS="HUS420099"; NE_V2="311188"; NE_TSV="243804"; OrigenAlt=$null; Motivo="Contexto: Subida OK - revisar SIMED" }
  [PSCustomObject]@{ Factura="HUS0000421733"; HUS="HUS421733"; NE_V2="311190"; NE_TSV="243806"; OrigenAlt=$null; Motivo="Contexto: Subida OK - revisar SIMED" }
  [PSCustomObject]@{ Factura="HUS0000418576"; HUS="HUS418576"; NE_V2="311194"; NE_TSV="243803"; OrigenAlt=$null; Motivo="Contexto: Subida OK - revisar SIMED" }
  [PSCustomObject]@{ Factura="HUS0000420160"; HUS="HUS420160"; NE_V2="311197"; NE_TSV="243805"; OrigenAlt=$null; Motivo="Contexto: Subida OK - revisar SIMED" }
  [PSCustomObject]@{ Factura="HUS0000422238"; HUS="HUS422238"; NE_V2="311199"; NE_TSV="";       OrigenAlt=$null; Motivo="Contexto: Subida OK - revisar SIMED + confirmar NE con facturacion" }
  [PSCustomObject]@{ Factura="HUS0000435485"; HUS="HUS435485"; NE_V2="311222"; NE_TSV="264792"; OrigenAlt=$null; Motivo="NC subio sin soportes - re-correr" }
  [PSCustomObject]@{ Factura="HUS0000440328"; HUS="HUS440328"; NE_V2="";       NE_TSV="302111"; OrigenAlt=$null; Motivo="Sin NE V2 - confirmar con facturacion (TSV historico: 302111)" }
)

function Inspeccionar-Carpeta($path) {
  $info = [ordered]@{
    Existe       = $false
    TienePDF     = $false
    TieneXML     = $false
    TieneCUV     = $false
    NombrePDF    = ""
    NombreXML    = ""
    NombreCUV    = ""
    CUV_State    = ""
    CUV_CodigoError = ""
    CUV_Observacion = ""
    CUV_NumRechazos = 0
    CUV_FechaValidacion = ""
    Archivos     = @()
  }
  if (-not (Test-Path $path)) { return [PSCustomObject]$info }
  $info.Existe = $true
  $archivos = Get-ChildItem -Path $path -File -ErrorAction SilentlyContinue
  $info.Archivos = $archivos.Name
  foreach ($a in $archivos) {
    if ($a.Name -match "^NC_.*\.pdf$")  { $info.TienePDF = $true;  $info.NombrePDF = $a.Name }
    if ($a.Name -match "^XML_.*\.xml$") { $info.TieneXML = $true;  $info.NombreXML = $a.Name }
    if ($a.Name -match "^CUV_.*\.json$") {
      $info.TieneCUV  = $true
      $info.NombreCUV = $a.Name
      try {
        $j = Get-Content $a.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        # ResultState es booleano nativo en el JSON; PowerShell lo deserializa
        # como [bool] real, asi que normalizamos a "True"/"False".
        if ($null -ne $j.ResultState) {
          if ($j.ResultState) { $info.CUV_State = "True" } else { $info.CUV_State = "False" }
        }
        if ($j.FechaRadicacion) {
          $info.CUV_FechaValidacion = ([string]$j.FechaRadicacion).Substring(0, [Math]::Min(19, ([string]$j.FechaRadicacion).Length))
        }
        # El codigo de rechazo (RVC086, RVC063, TOT003, etc.) vive en
        # ResultadosValidacion[].Codigo donde Clase == "RECHAZADO".
        if ($j.ResultadosValidacion) {
          $rechazos = @($j.ResultadosValidacion | Where-Object { $_.Clase -and $_.Clase.ToUpper() -eq "RECHAZADO" })
          $info.CUV_NumRechazos = $rechazos.Count
          if ($rechazos.Count -gt 0) {
            $r0 = $rechazos[0]
            $info.CUV_CodigoError = [string]$r0.Codigo
            $obs = [string]$r0.Observaciones
            # Recortar a 200 chars para que entre en el CSV sin romper Excel.
            if ($obs.Length -gt 200) { $obs = $obs.Substring(0, 200) + "..." }
            $info.CUV_Observacion = $obs
          }
        }
      } catch {
        $info.CUV_State = "JSON_ILEGIBLE"
      }
    }
  }
  return [PSCustomObject]$info
}

Write-Host ""
Write-Host "=== DIAGNOSTICO LOTE V2 - 12 FACTURAS PENDIENTES ===" -ForegroundColor Cyan
Write-Host "Base V2: $baseV2"
Write-Host "Reporte: $reporteSalida"
Write-Host ""

if (-not (Test-Path $baseV2)) {
  Write-Warning "No existe la carpeta V2: $baseV2"
  Write-Warning "Editar `$baseV2 al principio del script."
}

$resultados = @()
foreach ($f in $facturas) {
  $rutaV2 = if ($f.NE_V2) { Join-Path $baseV2 $f.NE_V2 } else { "" }

  $infoV2 = if ($rutaV2) { Inspeccionar-Carpeta $rutaV2 } else { [PSCustomObject]@{ Existe=$false; TienePDF=$false; TieneXML=$false; TieneCUV=$false; NombrePDF=""; NombreXML=""; NombreCUV=""; CUV_State=""; CUV_CodigoError=""; Archivos=@() } }

  $infoOrigen = if ($f.OrigenAlt) { Inspeccionar-Carpeta $f.OrigenAlt } else { $null }

  if (-not $f.NE_V2) {
    $estadoCalculado = "SIN_NE_V2"
  } elseif (-not $infoV2.Existe) {
    $estadoCalculado = "CARPETA_NO_EXISTE_EN_V2"
  } elseif ($infoV2.TienePDF -and $infoV2.TieneXML -and $infoV2.TieneCUV) {
    if ($infoV2.CUV_State -eq "True") {
      $estadoCalculado = "COMPLETA_CUV_OK"
    } elseif ($infoV2.CUV_State -eq "False") {
      $estadoCalculado = "COMPLETA_CUV_RECHAZADO_$($infoV2.CUV_CodigoError)"
    } else {
      $estadoCalculado = "COMPLETA_CUV_DESCONOCIDO"
    }
  } else {
    $faltan = @()
    if (-not $infoV2.TienePDF) { $faltan += "PDF" }
    if (-not $infoV2.TieneXML) { $faltan += "XML" }
    if (-not $infoV2.TieneCUV) { $faltan += "CUV" }
    $estadoCalculado = "FALTAN_" + ($faltan -join "+")
  }

  $color = switch -Regex ($estadoCalculado) {
    "^COMPLETA_CUV_OK$"          { "Green" }
    "^COMPLETA_CUV_RECHAZADO"    { "Red" }
    "^FALTAN_"                   { "Yellow" }
    "^CARPETA_NO_EXISTE_EN_V2$"  { "Yellow" }
    "^SIN_NE_V2$"                { "Red" }
    default                       { "White" }
  }

  Write-Host ("[{0}]  NE_V2={1}  Estado={2}" -f $f.HUS, $f.NE_V2, $estadoCalculado) -ForegroundColor $color

  if ($infoV2.CUV_CodigoError -or $infoV2.CUV_Observacion) {
    $obsCorta = $infoV2.CUV_Observacion
    if ($obsCorta.Length -gt 120) { $obsCorta = $obsCorta.Substring(0, 120) + "..." }
    Write-Host ("    CUV rechazo: [{0}] {1}" -f $infoV2.CUV_CodigoError, $obsCorta) -ForegroundColor DarkRed
  }

  if ($infoOrigen) {
    $origenEstado = if ($infoOrigen.Existe) {
      if ($infoOrigen.TienePDF -and $infoOrigen.TieneXML -and $infoOrigen.TieneCUV) { "COMPLETA" } else { "INCOMPLETA" }
    } else { "NO_EXISTE" }
    Write-Host ("    Origen alterno ({0}): {1}" -f $f.OrigenAlt, $origenEstado) -ForegroundColor DarkGray
  }

  $resultados += [PSCustomObject]@{
    Factura            = $f.Factura
    HUS_corto          = $f.HUS
    NE_V2              = $f.NE_V2
    NE_TSV_historico   = $f.NE_TSV
    Motivo_contexto    = $f.Motivo
    V2_existe          = $infoV2.Existe
    V2_PDF             = $infoV2.NombrePDF
    V2_XML             = $infoV2.NombreXML
    V2_CUV             = $infoV2.NombreCUV
    CUV_ResultState    = $infoV2.CUV_State
    CUV_CodigoError    = $infoV2.CUV_CodigoError
    CUV_NumRechazos    = $infoV2.CUV_NumRechazos
    CUV_FechaValidacion= $infoV2.CUV_FechaValidacion
    CUV_Observacion    = $infoV2.CUV_Observacion
    Estado_real        = $estadoCalculado
    Origen_alterno     = if ($f.OrigenAlt) { $f.OrigenAlt } else { "" }
    Origen_existe      = if ($infoOrigen) { $infoOrigen.Existe } else { "" }
    Archivos_V2        = ($infoV2.Archivos -join "; ")
  }
}

$resultados | Export-Csv -Path $reporteSalida -NoTypeInformation -Encoding UTF8
Write-Host ""
Write-Host "Reporte escrito en: $reporteSalida" -ForegroundColor Cyan
Write-Host ""
Write-Host "Resumen por Estado_real:" -ForegroundColor Cyan
$resultados | Group-Object Estado_real | Sort-Object Count -Descending | Format-Table Count, Name -AutoSize
