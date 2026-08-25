# Extrae el detalle COMPLETO del rechazo del CUV (MinSalud) de las 4 facturas
# conciliadas del Dispensario y genera el informe tecnico para el area
# encargada (SISTEMAS/RIPS):
#
#   - INFORME_RECHAZOS_CUV.md : informe listo para enviar/pegar en Word.
#   - rechazos_cuv.csv        : una fila por rechazo (para Excel).
#
# A diferencia de diagnosticar_local.ps1 (que resume y trunca), aca se vuelca
# TODO: cada rechazo con su codigo, la observacion completa sin recortar y el
# PathFuente que indica en que parte exacta del RIPS esta el error.
#
# Fuente de datos: el ResultadosDoker_*.json MAS RECIENTE del share
# (\\172.16.32.83\...\FACTURAS_NOTA\<NE>\RIPS\) - asi se captura el estado
# VIGENTE por si SISTEMAS ya regenero algo. Si el share no responde, cae a la
# copia local del lote V2.
#
# Uso:
#   cd C:\temp-notas
#   powershell -ExecutionPolicy Bypass -File `
#     docs\diagnostico_lote_v2_pendientes\extraer_rechazos_cuv.ps1

$ErrorActionPreference = "Stop"

$share  = "\\172.16.32.83\factura_electronica_net22"
$baseV2 = "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\LOTE_DISPENSARIO_2026-06_V2\NOTAS"

$salidaMd  = Join-Path $PSScriptRoot "INFORME_RECHAZOS_CUV.md"
$salidaCsv = Join-Path $PSScriptRoot "rechazos_cuv.csv"

# Las 4 facturas conciliadas del pantallazo "Facturas Conciliadas" del SIMED.
# Periodos confirmados con la busqueda en el share del 10/07.
$facturas = @(
  [PSCustomObject]@{ HUS="HUS404136"; FacturaFull="HUS0000404136"; NE="311131"; Periodo="202606"
                     Radicado="457325"; Acta="AC000456"
                     ValorFactura="2.169.054"; TotalGlosas="61.708"; ValorAceptado="10.218" }
  [PSCustomObject]@{ HUS="HUS410675"; FacturaFull="HUS0000410675"; NE="311136"; Periodo="202606"
                     Radicado="462915"; Acta="AC000456"
                     ValorFactura="7.390.337"; TotalGlosas="245.072"; ValorAceptado="245.072" }
  [PSCustomObject]@{ HUS="HUS420099"; FacturaFull="HUS0000420099"; NE="311188"; Periodo="202606"
                     Radicado="560611"; Acta="AC000619"
                     ValorFactura="3.757.260"; TotalGlosas="161.635"; ValorAceptado="79.407" }
  [PSCustomObject]@{ HUS="HUS435485"; FacturaFull="HUS0000435485"; NE="311222"; Periodo="202606"
                     Radicado="637718"; Acta="AC000619"
                     ValorFactura="27.102.523"; TotalGlosas="1.662.440"; ValorAceptado="1.662.440" }
)

function Buscar-JsonCuv($f) {
  # Devuelve @{ Path=<ruta>; Origen="share"|"local" } del JSON mas reciente,
  # o $null si no hay ninguno.
  $carpetaShare = "$share\$($f.Periodo)\FACTURAS_NOTA\$($f.NE)"
  foreach ($sub in @("$carpetaShare\RIPS", $carpetaShare)) {
    try {
      if (Test-Path $sub) {
        $cand = @(Get-ChildItem $sub -Filter "ResultadosDoker_*.json" -File -ErrorAction SilentlyContinue |
                  Sort-Object Name -Descending)
        if ($cand.Count -gt 0) { return @{ Path=$cand[0].FullName; Origen="share" } }
      }
    } catch {}
  }
  # Fallback: copia local del V2 (CUV_<NE>_HUS<n>.json renombrado por consolidar)
  $local = @(Get-ChildItem (Join-Path $baseV2 $f.NE) -Filter "CUV_*.json" -File -ErrorAction SilentlyContinue)
  if ($local.Count -gt 0) { return @{ Path=$local[0].FullName; Origen="local (V2)" } }
  return $null
}

function Analizar-Cuv($rutaJson) {
  # Devuelve un objeto con el analisis completo del JSON del CUV.
  $r = [ordered]@{
    Tipo = "SIN_ARCHIVO"; ResultState=""; CUV=""; Fecha=""; Rechazos=@(); NumNotifs=0; TextoError=""
  }
  if (-not $rutaJson) { return [PSCustomObject]$r }
  $raw = Get-Content $rutaJson -Raw -Encoding UTF8
  if ($raw -match "Se ha generado un error en el consumo" -or $raw -match "dockerrips\.hus\.gov\.co" -or
      $raw -match "No connection could be made" -or $raw -match "A connection attempt failed") {
    $r.Tipo = "ERROR_SERVICIO_INTERNO"
    $r.TextoError = ($raw.Substring(0, [Math]::Min(600, $raw.Length))).Replace("`r"," ").Replace("`n"," ")
    return [PSCustomObject]$r
  }
  try { $j = $raw | ConvertFrom-Json } catch {
    $r.Tipo = "JSON_ILEGIBLE"
    $r.TextoError = ($raw.Substring(0, [Math]::Min(600, $raw.Length))).Replace("`r"," ").Replace("`n"," ")
    return [PSCustomObject]$r
  }
  $r.Tipo = "CUV"
  if ($null -ne $j.ResultState) { $r.ResultState = if ($j.ResultState) { "true (APROBADO)" } else { "false (RECHAZADO)" } }
  if ($j.CodigoUnicoValidacion) { $r.CUV = ([string]$j.CodigoUnicoValidacion).Trim() }
  if ($j.FechaRadicacion)       { $r.Fecha = ([string]$j.FechaRadicacion).Substring(0, [Math]::Min(19, ([string]$j.FechaRadicacion).Length)) }
  $vals = @($j.ResultadosValidacion)
  $r.Rechazos  = @($vals | Where-Object { $_.Clase -and $_.Clase.ToUpper() -eq "RECHAZADO" })
  $r.NumNotifs = @($vals | Where-Object { $_.Clase -and $_.Clase.ToUpper() -eq "NOTIFICACION" }).Count
  return [PSCustomObject]$r
}

Write-Host ""
Write-Host "=== EXTRACCION DE RECHAZOS CUV - 4 FACTURAS CONCILIADAS ===" -ForegroundColor Cyan
Write-Host ""

$filasCsv = @()
$detalles = @()   # bloques de texto MD por factura

foreach ($f in $facturas) {
  $fuente = Buscar-JsonCuv $f
  $a = Analizar-Cuv $(if ($fuente) { $fuente.Path } else { $null })

  $etiqueta = switch ($a.Tipo) {
    "CUV"                    { if ($a.ResultState -like "true*") { "CUV APROBADO (ya destrabada)" } else { "CUV RECHAZADO por MinSalud" } }
    "ERROR_SERVICIO_INTERNO" { "VALIDACION NUNCA EJECUTADA (servicio interno dockerrips caido)" }
    "JSON_ILEGIBLE"          { "ARCHIVO ILEGIBLE (revisar manualmente)" }
    default                  { "SIN ARCHIVO DE VALIDACION" }
  }
  $colorCons = if ($a.ResultState -like "true*") { "Green" } elseif ($a.Tipo -eq "CUV") { "Red" } else { "Magenta" }
  Write-Host ("[{0}] NE {1}: {2}" -f $f.HUS, $f.NE, $etiqueta) -ForegroundColor $colorCons
  if ($fuente) { Write-Host ("    Fuente: {0} ({1})" -f $fuente.Path, $fuente.Origen) -ForegroundColor DarkGray }

  # ---- bloque MD de esta factura ----
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.AppendLine("### $($f.FacturaFull) - NC (NE) $($f.NE)")
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("| Campo | Valor |")
  [void]$sb.AppendLine("|---|---|")
  [void]$sb.AppendLine("| Radicado / Acta | $($f.Radicado) / $($f.Acta) |")
  [void]$sb.AppendLine("| Valor factura | `$ $($f.ValorFactura) |")
  [void]$sb.AppendLine("| Total glosas | `$ $($f.TotalGlosas) |")
  [void]$sb.AppendLine("| Valor aceptado en conciliacion (valor de la NC) | `$ $($f.ValorAceptado) |")
  [void]$sb.AppendLine("| Estado de la validacion | **$etiqueta** |")
  if ($a.Fecha) { [void]$sb.AppendLine("| Fecha de la validacion | $($a.Fecha) |") }
  if ($fuente)  { [void]$sb.AppendLine("| Archivo analizado | ``$($fuente.Path)`` |") }
  [void]$sb.AppendLine("")

  if ($a.Tipo -eq "CUV" -and $a.Rechazos.Count -gt 0) {
    [void]$sb.AppendLine("**Rechazos reportados por MinSalud ($($a.Rechazos.Count)):**")
    [void]$sb.AppendLine("")
    $i = 0
    foreach ($rz in $a.Rechazos) {
      $i++
      $obs  = ([string]$rz.Observaciones).Trim()
      $path = ([string]$rz.PathFuente).Trim()
      [void]$sb.AppendLine("$i. **[$($rz.Codigo)]** $obs")
      if ($path) { [void]$sb.AppendLine("   - Ubicacion en el RIPS (PathFuente): ``$path``") }
      [void]$sb.AppendLine("")
      $filasCsv += [PSCustomObject]@{
        Factura=$f.FacturaFull; NE=$f.NE; Radicado=$f.Radicado; Acta=$f.Acta
        Estado=$etiqueta; Codigo=[string]$rz.Codigo
        Observacion=($obs -replace "[`r`n]+", " / "); PathFuente=$path
        FechaValidacion=$a.Fecha; ArchivoAnalizado=$(if ($fuente) { $fuente.Path } else { "" })
      }
    }
    if ($a.NumNotifs -gt 0) {
      [void]$sb.AppendLine("(Ademas trae $($a.NumNotifs) notificaciones informativas, no bloqueantes.)")
      [void]$sb.AppendLine("")
    }
  } elseif ($a.Tipo -eq "CUV" -and $a.ResultState -like "true*") {
    [void]$sb.AppendLine("**Esta nota YA tiene CUV aprobado** (``$($a.CUV)``). No requiere gestion del area - se puede radicar en SIMED.")
    [void]$sb.AppendLine("")
    $filasCsv += [PSCustomObject]@{
      Factura=$f.FacturaFull; NE=$f.NE; Radicado=$f.Radicado; Acta=$f.Acta
      Estado=$etiqueta; Codigo=""; Observacion="CUV aprobado: $($a.CUV)"; PathFuente=""
      FechaValidacion=$a.Fecha; ArchivoAnalizado=$(if ($fuente) { $fuente.Path } else { "" })
    }
  } else {
    [void]$sb.AppendLine("**No hay resultado de validacion de MinSalud para esta nota.** El archivo de resultado contiene el error del servicio interno del hospital:")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine('```')
    [void]$sb.AppendLine($(if ($a.TextoError) { $a.TextoError } else { "(sin archivo ResultadosDoker en el share ni copia local)" }))
    [void]$sb.AppendLine('```')
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("La validacion ante MinSalud **nunca se ejecuto** - no es un rechazo del Ministerio sino una falla del servicio interno ``dockerrips.hus.gov.co:9443`` al momento de generar la nota.")
    [void]$sb.AppendLine("")
    $filasCsv += [PSCustomObject]@{
      Factura=$f.FacturaFull; NE=$f.NE; Radicado=$f.Radicado; Acta=$f.Acta
      Estado=$etiqueta; Codigo="DOCKERRIPS_DOWN"
      Observacion=$(if ($a.TextoError) { $a.TextoError } else { "sin archivo" }); PathFuente=""
      FechaValidacion=""; ArchivoAnalizado=$(if ($fuente) { $fuente.Path } else { "" })
    }
  }
  $detalles += $sb.ToString()
}

# ---------------- Informe MD ----------------
$hoy = (Get-Date).ToString("yyyy-MM-dd")
$md = New-Object System.Text.StringBuilder
[void]$md.AppendLine("# Informe tecnico - Rechazo de CUV en notas credito de facturas conciliadas (Dispensario DMBUG)")
[void]$md.AppendLine("")
[void]$md.AppendLine("**De:** Auditoria de Cartera - Hospital Universitario de Santander (NIT 900006037-4)")
[void]$md.AppendLine("**Para:** Area encargada de RIPS / Facturacion electronica (SISTEMAS)")
[void]$md.AppendLine("**Fecha:** $hoy")
[void]$md.AppendLine("")
[void]$md.AppendLine("## 1. Resumen")
[void]$md.AppendLine("")
[void]$md.AppendLine("Cuatro facturas del Dispensario Medico Bucaramanga, **ya conciliadas** en actas AC000456 y AC000619, tienen su nota credito generada pero **no se pueden radicar en el portal SIMED** porque la validacion del RIPS de la nota ante MinSalud no fue exitosa. Este informe detalla el error exacto de cada una, con el texto completo devuelto por el validador y la ubicacion del problema dentro del RIPS, para que el area brinde la solucion.")
[void]$md.AppendLine("")
[void]$md.AppendLine("## 2. Antecedente importante: de objecion a error bloqueante")
[void]$md.AppendLine("")
[void]$md.AppendLine("Al momento de **radicar las facturas originales**, estas mismas inconsistencias del RIPS se presentaron como **objeciones** (observaciones/glosas) - no impedian la radicacion de la factura y siguieron su tramite normal hasta la conciliacion.")
[void]$md.AppendLine("")
[void]$md.AppendLine("Sin embargo, al **generar la nota credito** producto de la conciliacion, el RIPS de la nota debe validarse nuevamente ante MinSalud (SISPRO). En esa validacion, la misma inconsistencia que antes era una objecion subsanable **se convierte en un error bloqueante**: el Ministerio no asigna el CUV (``ResultState: false``) y sin CUV valido el portal SIMED del Dispensario no acepta la radicacion de la nota credito. Es decir: **la objecion de la radicacion se transformo en error en la nota credito**, y por eso estas notas quedaron atascadas.")
[void]$md.AppendLine("")
[void]$md.AppendLine("## 3. Facturas afectadas")
[void]$md.AppendLine("")
[void]$md.AppendLine("| Factura | Radicado | Acta | NC (NE) | Valor NC (aceptado) |")
[void]$md.AppendLine("|---|---|---|---|---|")
foreach ($f in $facturas) {
  [void]$md.AppendLine("| $($f.FacturaFull) | $($f.Radicado) | $($f.Acta) | $($f.NE) | `$ $($f.ValorAceptado) |")
}
[void]$md.AppendLine("")
[void]$md.AppendLine("## 4. Detalle del error por factura (texto completo del validador)")
[void]$md.AppendLine("")
foreach ($d in $detalles) { [void]$md.AppendLine($d) }
[void]$md.AppendLine("## 5. Solicitud al area")
[void]$md.AppendLine("")
[void]$md.AppendLine('1. **Para las notas con rechazo de MinSalud** (codigos RVCxxx detallados arriba): corregir en el RIPS de cada nota la inconsistencia indicada en el PathFuente (tipicamente el diagnostico relacionado igual al principal), reenviar la validacion y confirmar que el nuevo `ResultadosDoker_<NE>.json` quede con `ResultState: true` en el share (`\\172.16.32.83\factura_electronica_net22\<periodo>\FACTURAS_NOTA\<NE>\RIPS\`).')
[void]$md.AppendLine('2. **Para las notas cuya validacion nunca se ejecuto** (error del servicio interno `dockerrips.hus.gov.co:9443`): verificar el servicio y reintentar el envio del RIPS ante MinSalud para generar el CUV.')
[void]$md.AppendLine("3. Notificar a Auditoria de Cartera al completar cada una, para radicar de inmediato la nota credito en el SIMED y cerrar la conciliacion.")
[void]$md.AppendLine("")
[void]$md.AppendLine("## 6. Verificacion de cierre (la corre Cartera)")
[void]$md.AppendLine("")
[void]$md.AppendLine('```')
[void]$md.AppendLine('py tools\verificar_cuv_notas.py --facturas "HUS404136,HUS410675,HUS420099,HUS435485" --reporte reporte_cuv_conciliadas.csv')
[void]$md.AppendLine('```')
[void]$md.AppendLine("")
[void]$md.AppendLine("---")
[void]$md.AppendLine("*Generado automaticamente el $hoy desde los archivos de validacion vigentes (share de facturacion electronica). Anexo: ``rechazos_cuv.csv`` con una fila por rechazo.*")

Set-Content -Path $salidaMd -Value $md.ToString() -Encoding UTF8
$filasCsv | Export-Csv -Path $salidaCsv -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "Informe : $salidaMd" -ForegroundColor Cyan
Write-Host "CSV     : $salidaCsv" -ForegroundColor Cyan
Write-Host "Listo. Abrir el informe, revisar, y enviar al area." -ForegroundColor Green
