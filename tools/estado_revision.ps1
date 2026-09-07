<#
  ESTADO DE LA REVISION AUTOMATICA de un commit — 27-08-2026.

  Le pregunta a GitHub como quedo la revision automatica (el "CI") del
  codigo que el autodespliegue esta a punto de bajarle al PC de cartera.

  Escribe UNA sola palabra por pantalla, y nada mas:

    VERDE      la revision termino y paso.  -> se puede aplicar
    ROJO       la revision termino y fallo. -> NO aplicar
    CORRIENDO  todavia esta revisando.      -> esperar
    NOSESABE   no se pudo preguntar.        -> decide quien llama

  POR QUE "NOSESABE" Y NO "ROJO" CUANDO FALLA LA CONSULTA:
  no saber no es lo mismo que saber que esta mal. Si esto devolviera
  ROJO cada vez que se cae internet, el hospital se quedaria sin
  desplegar por una consulta fallida — peor que el problema que
  resuelve. Quien llama decide, y lo deja anotado en su registro.

  LA LLAVE, si el repositorio es privado: se busca primero en la
  variable GITHUB_TOKEN y despues en data\github_token.txt (ese
  archivo NO va al repositorio). Si el repositorio es publico, no
  hace falta ninguna.

  Para probarlo a mano:
     powershell -ExecutionPolicy Bypass -File tools\estado_revision.ps1 `
        -Sha (git rev-parse origin/motor-glosas) -Repo C:\motor-glosas\repo
#>

param(
  [Parameter(Mandatory=$true)][string]$Sha,
  [string]$Repo = "",
  [string]$Proyecto = "yesidbadillo820-ship-it/motor-glosas-hus",
  [int]$Segundos = 20
)

$ErrorActionPreference = "Stop"

function Responder([string]$palabra) {
  Write-Output $palabra
  exit 0
}

# ── La llave, si hace falta ────────────────────────────────────────
$llave = $env:GITHUB_TOKEN
if ([string]::IsNullOrWhiteSpace($llave) -and $Repo) {
  $archivo = Join-Path $Repo "data\github_token.txt"
  if (Test-Path $archivo) {
    try { $llave = (Get-Content $archivo -Raw).Trim() } catch { $llave = "" }
  }
}

$cabeceras = @{
  "Accept"               = "application/vnd.github+json"
  "User-Agent"           = "motor-glosas-autodeploy"
  "X-GitHub-Api-Version" = "2022-11-28"
}
if (-not [string]::IsNullOrWhiteSpace($llave)) {
  $cabeceras["Authorization"] = "Bearer $llave"
}

# TLS 1.2: los Windows viejos no lo traen puesto y GitHub ya no acepta menos.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

# ── La consulta ────────────────────────────────────────────────────
$url = "https://api.github.com/repos/$Proyecto/commits/$Sha/check-runs?per_page=50"
try {
  $r = Invoke-RestMethod -Uri $url -Headers $cabeceras -TimeoutSec $Segundos -Method Get
} catch {
  Responder "NOSESABE"
}

if ($null -eq $r -or $null -eq $r.check_runs) { Responder "NOSESABE" }

$revisiones = @($r.check_runs)

# Ninguna revision registrada todavia: para GitHub el commit acaba de
# llegar. No es verde ni rojo — es que aun no empieza.
if ($revisiones.Count -eq 0) { Responder "CORRIENDO" }

# Una sola en rojo basta para no bajar el codigo.
$malas = @("failure", "timed_out", "startup_failure", "action_required")
foreach ($c in $revisiones) {
  if ($c.status -eq "completed" -and $malas -contains $c.conclusion) {
    Responder "ROJO"
  }
}

# Si alguna sigue trabajando, todavia no se sabe como termina.
foreach ($c in $revisiones) {
  if ($c.status -ne "completed") { Responder "CORRIENDO" }
}

# Todas terminaron y ninguna fallo. "cancelled" y "skipped" no son
# fallas: son revisiones que no llegaron a dar veredicto — y fue
# justamente una CANCELADA la que dejo pasar el defecto del ADRES el
# 26 de agosto, asi que tampoco cuentan como verde.
$buenas = @("success", "neutral")
$hayVeredicto = $false
foreach ($c in $revisiones) {
  if ($buenas -contains $c.conclusion) { $hayVeredicto = $true }
}
if (-not $hayVeredicto) { Responder "NOSESABE" }

Responder "VERDE"
