# Jump-box agent — instalación y uso

Plan B cuando Infra **no puede** montar el share `\\Prime\radicacion_2026`
en el server Linux del motor. Una PC Windows que ya ve `Y:\` corre este
agente y empuja los archivos vía HTTP al motor.

> **Importante**: esto es solución de **emergencia / puente**, no de
> producción. Apenas Infra entregue la cuenta de servicio y se monte
> el share en el server, este agente se apaga y el motor lee directo.

## Requisitos en la PC Windows

- Windows 10/11 con `Y:\` mapeado a `\\Prime\radicacion_2026` (o como esté).
- Python 3.9+ instalado y en PATH.
- Acceso de red al motor (puerto 443 hacia `motor.hus.gov.co` o el que sea).
- La PC tiene que estar **prendida** en horario laboral mínimo. Para 24/7,
  configurá Windows: `Configuración → Sistema → Inicio/apagado → Suspensión: Nunca`.

## Instalación (5 min)

```powershell
# 1) Bajá jumpbox_sync.py a una carpeta dedicada, ej C:\motor-glosas\
mkdir C:\motor-glosas
# Copiá tools\jumpbox_sync.py del repo a C:\motor-glosas\

# 2) Dependencias
pip install requests

# 3) Probá que tenés acceso al share
dir Y:\
```

## Configuración (variables de entorno)

Abrí PowerShell **como administrador** y configurá variables persistentes
para tu usuario:

```powershell
[Environment]::SetEnvironmentVariable("MOTOR_URL", "https://motor.hus.gov.co", "User")
[Environment]::SetEnvironmentVariable("MOTOR_TOKEN", "PEGAR_TU_TOKEN_DE_AUDITOR", "User")
[Environment]::SetEnvironmentVariable("SHARE_ROOT", "Y:\", "User")
```

> El **token** lo sacás del motor: login con tu usuario → DevTools del
> navegador → Network → cualquier request → header `Authorization: Bearer ...`.
> El usuario debe tener rol `auditor` o superior (Plan B requiere ese permiso
> para subir archivos).

Cerrá y volvé a abrir la PowerShell para que tome las variables.

## Probar (modo `--once`)

```powershell
cd C:\motor-glosas
python jumpbox_sync.py --once
```

Esperás algo como:

```
2026-04-29 09:15:01 [INFO] Iniciando sync. SHARE_ROOT=Y:\ → https://motor.hus.gov.co
2026-04-29 09:15:03 [INFO] Local: 12450 archivos | Remoto: 0 | A subir: 12450
2026-04-29 09:15:04 [INFO] Pasada terminada: {'duracion_s': 0.0, 'subidos': 0, 'reindexado': False}
...
2026-04-29 09:42:12 [INFO] Sync hecho: {'guardados': 12450, ...}
2026-04-29 09:42:15 [INFO] Reindex OK: 12450 archivos / 4321 facturas
```

Logs y estado quedan en `%APPDATA%\motor-glosas\`:
- `jumpbox.log` — log rotativo
- `jumpbox_state.json` — último run, último reindex, conteos

Validá en el motor:

```
https://motor.hus.gov.co/soportes-auto/healthz
```

Tiene que decir `"status":"ok"` y `archivos_indexados: 12450` (o lo que corresponda).

## Modo loop (producción)

```powershell
python jumpbox_sync.py --loop --interval-min 30
```

Pasada cada 30 minutos. La consola queda abierta.

## Hacerlo permanente (Tarea Programada)

Para que arranque solo y sobreviva reinicios:

```powershell
# Crear tarea programada (Administrador)
schtasks /Create /TN "MotorGlosas-JumpBox" `
  /TR "python C:\motor-glosas\jumpbox_sync.py --loop --interval-min 30" `
  /SC ONLOGON /RL HIGHEST /F
```

Para verla / pararla:

```powershell
schtasks /Query /TN "MotorGlosas-JumpBox"
schtasks /End /TN "MotorGlosas-JumpBox"
schtasks /Delete /TN "MotorGlosas-JumpBox" /F
```

## Diagnóstico de problemas comunes

| Síntoma | Causa | Fix |
|---|---|---|
| `SHARE_ROOT no existe: Y:\` | Y: no está mapeado o caducó la sesión | Abrí Explorer, andá a `\\Prime\radicacion_2026`, mete tu password. Reintentá. |
| `401 Unauthorized` | Token expirado | Generá uno nuevo del motor y actualizá `MOTOR_TOKEN`. |
| `403 Forbidden` | Tu usuario no es auditor+ | Pedile a un admin del motor que te suba el rol. |
| `Connection refused / timeout` | Firewall hacia el motor | Abrí 443 hacia el host del motor con tu equipo de red. |
| `413 Payload Too Large` | Algún PDF supera 50 MB (rara historia clínica gigante) | Subir el límite en el motor (`_MAX_BYTES_POR_ARCHIVO` en `app/api/routers/soportes.py`) o saltarlo. |
| Subió mucho la primera vez, después casi nada | Esperado. Una vez que el manifest del motor coincide con el share, solo se suben archivos nuevos o cambiados. | — |

## Cuándo apagar este agente

Apenas se cumplan **las dos** condiciones:

1. El server motor tiene mount CIFS funcionando (`/soportes-auto/healthz` devuelve `"status":"ok"` mostrando `raiz: /mnt/radicacion_2026`).
2. Probaste un `GET /soportes-auto/factura/HUS......` y devuelve los archivos correctamente sin que el agente esté corriendo.

En ese momento:

```powershell
schtasks /Delete /TN "MotorGlosas-JumpBox" /F
```

Y sugerencia: **NO borres el archivo de Python** todavía. Dejalo guardado
en la PC un par de meses como respaldo, por si el mount tiene un problema
y hay que reactivar el Plan B mientras se resuelve.
