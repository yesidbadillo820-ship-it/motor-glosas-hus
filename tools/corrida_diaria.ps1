# HOSPIAI — corrida diaria (solo lectura sobre los shares).
# 1) Actualiza el ÍNDICE PERMANENTE (incremental: segundos si nada cambió).
# 2) Corre el radicador (usa el índice permanente automáticamente).
# 3) Directores + aprendizaje + curaduría del conocimiento + indicadores + paneles.
# 4) Los VIERNES: informe de mejora continua (AG028).
#
# Programarla (una vez):
#   schtasks /Create /TN "HOSPIAI corrida diaria" /SC DAILY /ST 06:00 `
#     /TR "powershell -ExecutionPolicy Bypass -File C:\Users\cartera\motor-glosas-hus\tools\corrida_diaria.ps1"
param(
    [string]$Origen = "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD",
    [string[]]$Raices = @("Y:\", "Z:\SERVIDOR GLOSAS", "X:\SERVIDOR RADICACION\2. SINAC SC SAS - 2026")
)

Set-Location (Split-Path $PSScriptRoot -Parent)   # raíz del repo
New-Item -ItemType Directory -Force -Path "data\logs" | Out-Null
$fecha = Get-Date -Format "yyyyMMdd"

# 1) Índice permanente (AG001) — incremental, con progreso.
py tools\hospiai_indexador.py indexar @Raices

# 2) Auditoría del lote + Expediente Digital (autodetecta data\indices\*.db).
py tools\radicar_facturacion.py --origen $Origen `
    --reporte "$env:USERPROFILE\Desktop\radicacion_fe.csv" `
    --xlsx    "$env:USERPROFILE\Desktop\radicacion_fe.xlsx" `
    --db      "data\hospiai.db" `
    --log     "data\logs\corrida_$fecha.log"

# 3) Directores + aprendizaje → memoria → curaduría → indicadores + paneles.
py tools\hospiai_directores.py informe
py tools\hospiai_directores.py aprendizaje
py tools\hospiai_conocimiento.py curar
py tools\hospiai_conocimiento.py patrones
py tools\hospiai_operacion.py indicadores
py tools\hospiai.py --db "data\hospiai.db" panel --salida "$env:USERPROFILE\Desktop\panel_hospiai.html"
py tools\hospiai_panel_ejecutivo.py --salida "$env:USERPROFILE\Desktop\panel_ejecutivo.html"

# 4) EL "BUENOS DÍAS": el copiloto llega con las decisiones del día (AG029).
py tools\hospiai.py iniciar-dia | Tee-Object "data\logs\dia_$fecha.txt"

# 5) Ritual del viernes: ¿qué mejoró, qué empeoró, qué aprendimos, qué cambiamos el lunes?
if ((Get-Date).DayOfWeek -eq 'Friday') {
    py tools\hospiai_operacion.py mejora | Tee-Object "data\logs\mejora_$fecha.txt"
}
