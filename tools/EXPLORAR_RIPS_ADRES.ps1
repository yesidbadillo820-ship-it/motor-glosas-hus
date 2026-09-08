# EXPLORAR_RIPS_ADRES.ps1 — solo LECTURA. No modifica ni copia nada.
#
# Para que Claude sepa como esta organizado el servidor de facturacion
# electronica y con que nombre exacto vienen las fechas en los RIPS.
#
# NO muestra datos del paciente: solo nombres de carpetas, nombres de
# campos del archivo y las fechas de atencion. Ningun documento, ningun
# nombre de persona.
#
# Como se corre: clic derecho > "Ejecutar con PowerShell" (sesion normal,
# NO necesita administrador). Copie TODO lo que salga y peguelo en el chat.

$ErrorActionPreference = "Continue"
$RUTA = "\\172.16.32.83\factura_electronica_net22"

Write-Host "=== 1. LA RUTA RESPONDE? ===" -ForegroundColor Cyan
if (-not (Test-Path $RUTA)) {
    Write-Host "NO se puede llegar a $RUTA" -ForegroundColor Red
    Write-Host "Revise que el equipo tenga permiso a esa carpeta compartida."
    Read-Host "`nEnter para cerrar"
    exit
}
Write-Host "SI responde: $RUTA" -ForegroundColor Green

Write-Host "`n=== 2. QUE HAY EN EL PRIMER NIVEL (max 25) ===" -ForegroundColor Cyan
Get-ChildItem -LiteralPath $RUTA -ErrorAction SilentlyContinue |
    Select-Object -First 25 |
    ForEach-Object { "{0}  {1}" -f $(if ($_.PSIsContainer) {"[carpeta]"} else {"[archivo] "}), $_.Name }

Write-Host "`n=== 3. UN EJEMPLO DE SUBCARPETA (max 15) ===" -ForegroundColor Cyan
$sub = Get-ChildItem -LiteralPath $RUTA -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
if ($sub) {
    Write-Host "Dentro de: $($sub.Name)"
    Get-ChildItem -LiteralPath $sub.FullName -ErrorAction SilentlyContinue |
        Select-Object -First 15 |
        ForEach-Object { "   {0}  {1}" -f $(if ($_.PSIsContainer) {"[carpeta]"} else {"[archivo] "}), $_.Name }
}

Write-Host "`n=== 4. CUANTOS RIPS HAY Y COMO SE LLAMAN (max 10 nombres) ===" -ForegroundColor Cyan
Write-Host "Buscando archivos .json ... (puede tardar un par de minutos)"
$rips = Get-ChildItem -LiteralPath $RUTA -Filter "*.json" -Recurse -File -ErrorAction SilentlyContinue |
    Select-Object -First 400
Write-Host ("Encontrados (tope 400): {0}" -f $rips.Count)
$rips | Select-Object -First 10 | ForEach-Object {
    "   {0}   [{1} KB]   {2}" -f $_.Name, [int]($_.Length/1KB), $_.DirectoryName.Replace($RUTA, "...")
}

Write-Host "`n=== 5. QUE CAMPOS TRAE UN RIPS (SIN datos del paciente) ===" -ForegroundColor Cyan
$uno = $rips | Where-Object { $_.Length -gt 100 } | Select-Object -First 1
if (-not $uno) {
    Write-Host "No se encontro ningun .json para revisar." -ForegroundColor Yellow
} else {
    Write-Host "Archivo revisado: $($uno.Name)"
    try {
        $j = Get-Content -LiteralPath $uno.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "`n  Campos del primer nivel:" -ForegroundColor Yellow
        $j.PSObject.Properties.Name | ForEach-Object { "     - $_" }

        if ($j.usuarios -and $j.usuarios.Count -gt 0) {
            Write-Host "`n  Campos de 'usuarios':" -ForegroundColor Yellow
            $j.usuarios[0].PSObject.Properties.Name | ForEach-Object { "     - $_" }

            if ($j.usuarios[0].servicios) {
                Write-Host "`n  Grupos de servicios que trae:" -ForegroundColor Yellow
                $j.usuarios[0].servicios.PSObject.Properties |
                    ForEach-Object {
                        $n = if ($_.Value -is [array]) { $_.Value.Count } else { "?" }
                        "     - {0}  ({1} registros)" -f $_.Name, $n
                    }

                Write-Host "`n  *** LOS CAMPOS DE FECHA (esto es lo clave) ***" -ForegroundColor Green
                foreach ($grupo in $j.usuarios[0].servicios.PSObject.Properties) {
                    if ($grupo.Value -is [array] -and $grupo.Value.Count -gt 0) {
                        $campos = $grupo.Value[0].PSObject.Properties |
                                  Where-Object { $_.Name -match "fecha|Fecha" }
                        foreach ($c in $campos) {
                            "     {0}.{1} = {2}" -f $grupo.Name, $c.Name, $c.Value
                        }
                    }
                }
            }
        } else {
            Write-Host "  Este archivo no trae 'usuarios': puede no ser un RIPS." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  No se pudo leer como JSON: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`n=== FIN — copie todo lo anterior y peguelo en el chat ===" -ForegroundColor Cyan
Read-Host "`nEnter para cerrar"
