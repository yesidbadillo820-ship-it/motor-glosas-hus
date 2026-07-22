# HOSPIAI — corrida diaria (solo lectura sobre los shares).
# Corre el radicador con el índice de soportes, actualiza el Expediente Digital
# (data\hospiai.db), y regenera el reporte y el panel en el Escritorio.
#
# Programarla (una vez, en PowerShell como el usuario del área):
#   schtasks /Create /TN "HOSPIAI corrida diaria" /SC DAILY /ST 06:00 `
#     /TR "powershell -ExecutionPolicy Bypass -File C:\Users\cartera\motor-glosas-hus\tools\corrida_diaria.ps1"
#
# Parámetros editables:
param(
    [string]$Origen = "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD",
    [string]$Indice = "data\idx_soportes_2026.txt"
)

Set-Location (Split-Path $PSScriptRoot -Parent)   # raíz del repo
New-Item -ItemType Directory -Force -Path "data\logs" | Out-Null
$fecha = Get-Date -Format "yyyyMMdd"

# 1) Auditoría del lote + Expediente Digital (el CSV/XLSX de siempre siguen saliendo).
py tools\radicar_facturacion.py --origen $Origen `
    --soportes-indice $Indice `
    --reporte "$env:USERPROFILE\Desktop\radicacion_fe.csv" `
    --xlsx    "$env:USERPROFILE\Desktop\radicacion_fe.xlsx" `
    --db      "data\hospiai.db" `
    --log     "data\logs\corrida_$fecha.log"

# 2) Panel del Expediente Digital, listo para abrir con doble clic.
py tools\hospiai.py --db "data\hospiai.db" panel --salida "$env:USERPROFILE\Desktop\panel_hospiai.html"
