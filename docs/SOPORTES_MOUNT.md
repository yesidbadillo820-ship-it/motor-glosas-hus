# Mount del share de soportes — runbook

El motor lee historias clínicas, RIPS, FEV y demás soportes del share
Windows `\\Prime\radicacion_2026` para alimentar a la IA sin que el
gestor los suba manualmente. Este documento es el procedimiento
oficial de instalación, monitoreo y recuperación.

## Contexto

- **Share origen**: `\\Prime\radicacion_2026` (servidor Windows del HUS)
- **Server motor**: Linux (Ubuntu/Debian asumido)
- **Mount point**: `/mnt/radicacion_2026` (read-only)
- **Variable de entorno**: `SOPORTES_ROOT=/mnt/radicacion_2026`
- **Indexador**: `app/services/soportes_autodiscovery_service.py`
- **Scheduler**: rebuild diario a las 2:00 AM hora local del server

## 1. Requisitos previos (pedirlos a Infra antes de empezar)

- [ ] **Conectividad**: el server motor debe ver `Prime` por SMB. Validar con
      `nc -vz Prime 445` desde el server. Si falla, abrir firewall.
- [ ] **Usuario de servicio**: cuenta de dominio `svc_motor_radicacion`
      con permiso **read-only** sobre el share. **No usar la cuenta
      personal de un gestor** — cuando esa persona se va del hospital
      el motor se cae silencioso.
- [ ] **DNS o IP fija**: confirmar que `Prime` resuelve estable desde el
      server, o usar IP en el fstab.

## 2. Instalación del mount

```bash
# Paquetes
sudo apt update
sudo apt install -y cifs-utils

# Punto de montaje
sudo mkdir -p /mnt/radicacion_2026
sudo chown root:root /mnt/radicacion_2026

# Archivo de credenciales (NO en fstab plano)
sudo tee /etc/cifs-radicacion.cred >/dev/null <<'EOF'
username=svc_motor_radicacion
password=PEGAR_AQUI
domain=HUS
EOF
sudo chmod 600 /etc/cifs-radicacion.cred
sudo chown root:root /etc/cifs-radicacion.cred
```

Identificar UID/GID del usuario que corre el motor (probablemente
`motor` o `www-data`):

```bash
id -u motor   # → 1001 por ejemplo
id -g motor   # → 1001
```

Agregar al `/etc/fstab`:

```
//Prime/radicacion_2026 /mnt/radicacion_2026 cifs credentials=/etc/cifs-radicacion.cred,ro,uid=1001,gid=1001,iocharset=utf8,vers=3.0,cache=strict,actimeo=120,_netdev,x-systemd.automount,x-systemd.idle-timeout=600,nofail 0 0
```

**Flags clave:**
- `ro` — read-only. **No negociable**. Impide que un bug del motor borre soportes.
- `cache=strict,actimeo=120` — cachea metadata 2 min para que `rglob` no se vuelva loco.
- `_netdev,x-systemd.automount` — lazy mount; si la red no está al boot, no impide arranque.
- `nofail` — el sistema arranca aunque el mount falle.
- `vers=3.0` — SMB3 (encriptado en tránsito).

Aplicar:

```bash
sudo systemctl daemon-reload
sudo mount /mnt/radicacion_2026
ls /mnt/radicacion_2026   # debería listar "ABRIL 2026 - SOPORTES RADICACION", etc.
```

## 3. Configurar el motor

En el archivo `.env` del motor:

```
SOPORTES_ROOT=/mnt/radicacion_2026
```

Reiniciar el servicio. En los logs verás:

```
[SOPORTES-REINDEX] Scheduler iniciado (2 AM diario + build inicial)
[SOPORTES-REINDEX] OK: 12345 archivos / 4321 facturas
```

## 4. Validación

```bash
# Healthz público (sin auth)
curl http://localhost:8000/soportes-auto/healthz

# Esperado:
# {"status":"ok","facturas_indexadas":4321,"archivos_indexados":12345,...}

# Lookup de una factura real (requiere token de un usuario)
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/soportes-auto/factura/HUS487523
```

## 5. Monitoreo

Apuntar el monitor (Datadog / Grafana / cron + alerta) a:

```
GET /soportes-auto/healthz
```

Comportamiento:
- **200** → todo OK
- **503** → degradado, con `razones_degradacion` en el body. Casos:
  - `raiz_no_accesible` → mount caído
  - `indice_nunca_construido` → motor recién arrancó pero rebuild falló
  - `build_obsoleto:Xh` → último build hace > 25h (scheduler colgado)
  - `error:...` → error reportado por el indexador

Configurar alerta: **503 por más de 10 minutos = page al on-call**.

## 6. Auditoría PHI

Cada lookup queda registrado en `audit_log` con acción
`LISTAR_SOPORTES_FACTURA`. Cada reindex manual queda como
`REINDEX_SOPORTES`. Para reportes de protección de datos:

```sql
SELECT timestamp, usuario_email, detalle
FROM audit_log
WHERE accion IN ('LISTAR_SOPORTES_FACTURA', 'REINDEX_SOPORTES')
ORDER BY timestamp DESC;
```

## 7. Runbook: el mount se cae

### Síntoma
Healthz devuelve 503 con `raiz_no_accesible`. Los gestores reportan
"no aparecen los soportes".

### Diagnóstico
```bash
# ¿Está montado?
mountpoint /mnt/radicacion_2026

# ¿Llego al server SMB?
nc -vz Prime 445

# ¿Qué dijo el último intento de mount?
sudo journalctl -u systemd-automount --since "1 hour ago"
sudo dmesg | grep -i cifs | tail -20
```

### Causas comunes y fix
| Síntoma en logs | Causa | Acción |
|---|---|---|
| `Connection refused` | Firewall cerró 445 | Hablar con Infra |
| `Permission denied` o `STATUS_LOGON_FAILURE` | Password de svc_motor_radicacion expiró/cambió | Actualizar `/etc/cifs-radicacion.cred`, `sudo umount /mnt/radicacion_2026 && sudo mount /mnt/radicacion_2026` |
| `Host is down` | Server `Prime` reiniciando | Esperar; el automount lo recupera solo cuando vuelva |
| `Stale file handle` | Reconexión sucia tras blip de red | `sudo umount -f /mnt/radicacion_2026 && sudo mount /mnt/radicacion_2026` |

### Re-indexar después de recuperar
```bash
# Como auditor o superior
curl -X POST -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/soportes-auto/reindex
```

## 8. Política de credenciales

- **Rotación**: cada 90 días, coordinar con Infra para rotar password
  de `svc_motor_radicacion`. Actualizar `/etc/cifs-radicacion.cred` y
  remontar.
- **Backup del archivo**: NO copiarlo a repos / S3 / chats. Solo en el
  vault corporativo.
- **Acceso al archivo**: solo `root` (chmod 600). Cualquier otro
  acceso es incidente de seguridad.

## 9. Qué NO hacer

- ❌ Montar el share como `rw` "por si acaso". El motor solo lee.
- ❌ Usar la cuenta personal de un gestor.
- ❌ Hardcodear el password en `fstab` o en variables de entorno.
- ❌ Sincronizar el contenido a un disco local "para ir más rápido".
  Eso duplica PHI y es un dolor de cabeza de auditoría.
- ❌ Saltarse el healthz en el monitor. Un mount caído silencioso
  hace que la IA responda peor sin que nadie se entere.
