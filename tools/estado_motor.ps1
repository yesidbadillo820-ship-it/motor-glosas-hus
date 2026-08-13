# =====================================================================
#  estado_motor.ps1 - el estado del sistema en una pantalla.
#
#  Lo llama tools\ESTADO_MOTOR.cmd (doble clic). Nacio el 04-08-2026:
#  para saber si la pagina estaba bien habia que pegar cinco ordenes
#  distintas en PowerShell y saber interpretarlas. Aca sale todo junto y
#  en cristiano: quien atiende, con que clave, si el tunel publica, si el
#  arranque automatico esta puesto y que falta.
#
#  Solo mira. No cierra ni arranca nada.
#  Todo lo que imprime va en ASCII: Windows PowerShell lee este archivo
#  como ANSI y las tildes salen rotas.
# =====================================================================
param(
    [string]$Repo = "C:\motor-glosas\repo"
)

$ErrorActionPreference = "SilentlyContinue"
$avisos = @()

function Motores {
    @(Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app\.main'
        })
}

function Puerto-De($proc) {
    if ($proc.CommandLine -match '--port[=\s]+(\d+)') { return $matches[1] }
    return '8000'
}

$todos = Motores
$pids = @($todos | ForEach-Object { $_.ProcessId })
$raices = @($todos | Where-Object { $pids -notcontains $_.ParentProcessId })

Write-Host ""
Write-Host " ============================================================"
Write-Host "   ESTADO DEL MOTOR DE GLOSAS"
Write-Host " ============================================================"
Write-Host ""

# --- La pagina por internet (puerto 8080) ----------------------------
Write-Host " PAGINA POR INTERNET (puerto 8080)"
$publico = @($raices | Where-Object { (Puerto-De $_) -eq '8080' })
if ($publico.Count -eq 1) {
    Write-Host ("   [OK] servidor atendiendo - PID " + $publico[0].ProcessId)
}
elseif ($publico.Count -eq 0) {
    Write-Host "   [FALTA] no hay servidor de la pagina publica"
    $avisos += "La pagina por internet NO esta arriba. Doble clic en C:\motor-glosas\arrancar_motor_glosas.cmd"
}
else {
    Write-Host ("   [OJO] hay " + $publico.Count + " servidores en el mismo puerto")
    $avisos += "Hay mas de un servidor en el puerto 8080: uno sobra."
}

$dueno = Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique
if ($dueno) { Write-Host ("   [OK] el puerto 8080 lo atiende el proceso " + ($dueno -join ", ")) }
else {
    Write-Host "   [FALTA] nadie esta escuchando el puerto 8080"
    $avisos += "Nadie escucha el puerto 8080: la pagina no responde."
}

# La clave de IA que cargo el servidor al arrancar, del propio registro.
$log = Join-Path $Repo "data\servidor.log"
if (Test-Path $log) {
    $linea = Select-String -Path $log -Pattern 'IA-PROVIDERS' | Select-Object -Last 1
    if ($linea -and $linea.Line -match 'groq=OK (\S+)\.\.\.') {
        Write-Host ("   [OK] clave de IA en uso: " + $matches[1] + "...")
    }
    elseif ($linea -and $linea.Line -match 'groq=AUSENTE') {
        Write-Host "   [FALTA] el servidor arranco SIN clave de Groq"
        $avisos += "El servidor de la pagina no tiene clave de Groq: ningun analisis va a funcionar."
    }
}

$vigilantes = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'servidor_motor_local' })
if ($vigilantes.Count -ge 1) {
    Write-Host ("   [OK] vigilante encendido (" + $vigilantes.Count + ")")
}
else {
    Write-Host "   [FALTA] no hay vigilante: si el servidor se cae, no vuelve solo"
    $avisos += "Sin vigilante del servidor. Doble clic en C:\motor-glosas\arrancar_motor_glosas.cmd"
}

$cf = @(Get-Process cloudflared)
if ($cf.Count -ge 1) { Write-Host ("   [OK] tunel de Cloudflare publicando - PID " + $cf[0].Id) }
else {
    Write-Host "   [FALTA] el tunel de Cloudflare no esta corriendo"
    $avisos += "Sin tunel: la direccion de internet no responde aunque el servidor este bien."
}

# --- El motor de pruebas (puerto 8000) -------------------------------
Write-Host ""
Write-Host " MOTOR DE PRUEBAS (puerto 8000)"
$pruebas = @($raices | Where-Object { (Puerto-De $_) -eq '8000' })
if ($pruebas.Count -ge 1) {
    Write-Host ("   [OK] encendido - PID " + $pruebas[0].ProcessId + " (es normal; no lo cierres si lo estas usando)")
}
else {
    Write-Host "   [--] apagado (normal si hoy no lo usaste)"
}

# --- Automatismos ----------------------------------------------------
Write-Host ""
Write-Host " AUTOMATISMOS"
$inicio = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\MotorGlosas.cmd"
if (Test-Path $inicio) { Write-Host "   [OK] arranca solo al iniciar sesion" }
else {
    Write-Host "   [FALTA] no arranca solo al iniciar sesion"
    $avisos += "Si el PC se reinicia, la pagina no vuelve sola: falta el arranque automatico."
}

foreach ($t in @("MotorGlosas_Autodeploy", "MotorGlosas_Backup")) {
    $tarea = Get-ScheduledTask -TaskName $t
    if ($tarea) { Write-Host ("   [OK] tarea " + $t + ": " + $tarea.State) }
    else {
        Write-Host ("   [FALTA] tarea " + $t)
        $avisos += ("Falta la tarea programada " + $t)
    }
}

# --- Resumen ---------------------------------------------------------
Write-Host ""
Write-Host " AVISOS"
if ($avisos.Count -eq 0) {
    Write-Host "   Ninguno. Todo lo que tiene que estar prendido, esta prendido."
}
else {
    foreach ($a in $avisos) { Write-Host ("   - " + $a) }
}
Write-Host ""
