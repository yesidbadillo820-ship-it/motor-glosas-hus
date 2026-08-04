# =====================================================================
#  reiniciar_motor.ps1 — deja libre el puerto del motor, sin daños.
#
#  Lo llama tools\REINICIAR_MOTOR.cmd. Vive aparte porque lo que hace es
#  delicado: CIERRA PROGRAMAS en el PC del auditor. Todo lo de aquí salió
#  de una revisión adversarial del 04-08-2026 sobre la primera versión,
#  que hacía este mismo trabajo apretujado dentro del .cmd y tenía cinco
#  agujeros, cada uno con su historia:
#
#   1. Cerraba TODO uvicorn de la aplicación, sin mirar el puerto → se
#      llevaba por delante el motor del 8080, que es el que sirve la
#      página por internet. Ya pasó una vez.
#   2. `netstat | findstr "LISTENING"` no encuentra nada en un Windows en
#      español, que dice ESCUCHANDO: la red de seguridad del puerto era
#      letra muerta justo en el PC del hospital.
#   3. Mataba al dueño del puerto sin mirar quién era: si el 8000 lo usa
#      otro programa del hospital, se cerraba sin aviso ni registro.
#   4. `-ErrorAction SilentlyContinue` se tragaba el «Acceso denegado»:
#      decía «cerrado» de algo que seguía vivo, y arrancaba encima.
#   5. Los procesos que no deja ver Windows (de otro usuario o elevados)
#      se descartaban en silencio y el bot informaba «no había ninguno».
#
#  Códigos de salida:  0 = el puerto quedó libre, se puede arrancar.
#                      1 = NO arrancar: quedó algo vivo y hay que mirarlo.
# =====================================================================
param(
    [string]$Puerto = "8000"
)

$ErrorActionPreference = "Continue"
$mios = @()
$otros = @()
$invisibles = 0

foreach ($p in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
    if ($p.ProcessId -eq $PID) { continue }   # nunca cerrarse a sí mismo
    if (-not $p.CommandLine) {
        # Windows oculta la línea de comando de lo que no es nuestro.
        if ($p.Name -match 'python|uvicorn') { $invisibles++ }
        continue
    }
    if ($p.CommandLine -notmatch 'uvicorn') { continue }
    if ($p.CommandLine -notmatch 'app\.main') { continue }
    $suyo = if ($p.CommandLine -match '--port[=\s]+(\d+)') { $matches[1] } else { '8000' }
    if ($suyo -eq $Puerto) { $mios += $p } else { $otros += , @($p.ProcessId, $suyo) }
}

# --- Los de OTRO puerto: se nombran y NO se tocan ---------------------
foreach ($o in $otros) {
    $extra = if ($o[1] -eq '8080') { ' — es el que sirve la pagina por internet' } else { '' }
    Write-Host ("       - dejo VIVO el motor PID " + $o[0] + " del puerto " + $o[1] + $extra)
}

# --- Los del MISMO puerto: se cierran y se comprueba que murieron -----
$sobrevivientes = @()
foreach ($m in $mios) {
    Write-Host ("       - cerrando motor PID " + $m.ProcessId + " (puerto " + $Puerto + ")")
    try { Stop-Process -Id $m.ProcessId -Force -ErrorAction Stop } catch { }
    Start-Sleep -Milliseconds 400
    if (Get-Process -Id $m.ProcessId -ErrorAction SilentlyContinue) {
        $sobrevivientes += $m.ProcessId
    }
}

# --- ¿Quién se quedó con el puerto? (sin depender del idioma) ---------
# Get-NetTCPConnection devuelve el PID dueño del puerto sin leer texto
# traducido, que es donde fallaba netstat+findstr en Windows en español.
$duenos = @()
try {
    $duenos = @(Get-NetTCPConnection -LocalPort ([int]$Puerto) -State Listen -ErrorAction Stop |
        Select-Object -ExpandProperty OwningProcess -Unique)
} catch { $duenos = @() }

$ajenos = @()
foreach ($pid_ in $duenos) {
    if ($pid_ -eq 0) { continue }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid_" -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    $es_motor = $proc.CommandLine -and $proc.CommandLine -match 'uvicorn' -and $proc.CommandLine -match 'app\.main'
    if ($es_motor) {
        Write-Host ("       - cerrando motor PID " + $pid_ + " que seguia con el puerto " + $Puerto)
        try { Stop-Process -Id $pid_ -Force -ErrorAction Stop } catch { }
        Start-Sleep -Milliseconds 400
        if (Get-Process -Id $pid_ -ErrorAction SilentlyContinue) { $sobrevivientes += $pid_ }
    }
    else {
        # NO es el motor: no se mata nada. Un puerto ocupado por otro
        # programa del hospital no es asunto de este bot.
        $ajenos += ("" + $proc.Name + " (PID " + $pid_ + ")")
    }
}

if ($invisibles -gt 0) {
    Write-Host ("       [!] Hay " + $invisibles + " programas que esta ventana no puede revisar")
    Write-Host "           (de otro usuario o abiertos como administrador). Si el enredo"
    Write-Host "           sigue, corre este bot con boton derecho > Ejecutar como administrador."
}

if ($ajenos.Count -gt 0) {
    Write-Host ""
    Write-Host ("  [!] El puerto " + $Puerto + " lo esta usando: " + ($ajenos -join ", "))
    Write-Host "      NO es el motor de glosas, asi que no lo voy a cerrar."
    Write-Host "      Cierra ese programa, o arranca el motor en otro puerto asi:"
    Write-Host ("          set MOTOR_GLOSAS_PUERTO=8010  y volve a dar doble clic")
    exit 1
}

if ($sobrevivientes.Count -gt 0) {
    Write-Host ""
    Write-Host ("  [!] No pude cerrar: PID " + ($sobrevivientes -join ", ") + ".")
    Write-Host "      Suele ser porque se abrio como administrador. Corre este bot con"
    Write-Host "      boton derecho > Ejecutar como administrador, o cierra esa ventana"
    Write-Host "      a mano. NO arranco otro motor encima para no repetir el enredo."
    exit 1
}

if ($mios.Count -eq 0 -and $otros.Count -eq 0) {
    Write-Host "       No habia ningun motor de glosas encendido. Bien."
}
exit 0
