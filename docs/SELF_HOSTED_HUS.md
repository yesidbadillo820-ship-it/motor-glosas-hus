# Motor Glosas HUS — Self-hosted en una máquina del hospital

**Costo: $0 USD/mes para siempre.** El motor vive en una máquina del HUS
y se expone a internet con HTTPS automático vía Cloudflare Tunnel — sin
abrir puertos en el firewall del hospital, sin VPS de pago, sin Fly,
sin Railway, sin Neon.

## Resumen visual

```
┌────────────────────────────────┐         ┌───────────────────────┐
│  iaglosassinac.help (público)  │  HTTPS  │  Cloudflare Edge      │
│  navegadores de los gestores   │ ─────▶  │  (validación + cache) │
└────────────────────────────────┘         └──────────┬────────────┘
                                                      │ Túnel saliente
                                                      │ (conexión iniciada
                                                      │  desde adentro)
                                                      ▼
                              ┌───────────────────────────────────┐
                              │  Máquina del HUS (Linux + Docker) │
                              │  ┌─────────────┐  ┌────────────┐ │
                              │  │ cloudflared │──│   motor    │ │
                              │  │ (contenedor)│  │ (FastAPI)  │ │
                              │  └─────────────┘  │ + SQLite   │ │
                              │                   │ /data      │ │
                              │                   └────────────┘ │
                              └───────────────────────────────────┘
```

## Requisitos

- **Una máquina Linux del HUS** prendida 24/7 (Ubuntu 22.04+ recomendado).
  - Mínimo: 2 vCPU, 2 GB RAM, 20 GB disco.
  - Acceso a internet saliente (NO se necesita IP pública ni abrir puertos).
- **Acceso root** (sudo) a esa máquina.
- **Una cuenta Cloudflare** (gratis) con el dominio `iaglosassinac.help`
  agregado.
- **Tus claves de IA**: mínimo `GROQ_API_KEY` (gratis en
  [console.groq.com](https://console.groq.com/keys)).

> Si tu dominio no está en Cloudflare, primero hay que mudarlo allá:
> Cloudflare → "Add a Site" → seguir el wizard. Es gratis y tarda ~10 min.

## Setup en 3 fases

### Fase 1 — Preparar la máquina (5 min, automatizado)

Conectate por SSH a la máquina del HUS y corré el instalador:

```bash
curl -fsSL https://raw.githubusercontent.com/yesidbadillo820-ship-it/motor-glosas-hus/motor-glosas/deploy/install.sh | sudo bash
```

Eso:
- Instala Docker + cloudflared automáticamente.
- Clona el repo en `/opt/motor-glosas`.
- Genera un `.env` con secrets aleatorios fuertes (incluyendo password
  admin inicial — anotalo cuando aparezca).
- Crea las carpetas `/data/soportes` y `/data/backups`.

### Fase 2 — Configurar Cloudflare Tunnel (5 min, manual)

```bash
# 1. Autenticate (te abre el browser, login con tu cuenta Cloudflare)
cloudflared tunnel login

# 2. Crear el túnel (genera un UUID + archivo .json)
cloudflared tunnel create motor-glosas
# Output: "Created tunnel motor-glosas with id <UUID>"
# Anotá ese UUID — lo vas a necesitar.

# 3. Apuntar tu dominio al túnel
cloudflared tunnel route dns motor-glosas iaglosassinac.help

# 4. Copiar las credentials del túnel al repo
sudo cp ~/.cloudflared/<UUID>.json /opt/motor-glosas/deploy/cloudflared/

# 5. Crear la config del túnel desde el ejemplo
cd /opt/motor-glosas/deploy/cloudflared
sudo cp config.yml.example config.yml
sudo nano config.yml
# Reemplazá <REEMPLAZAR_CON_UUID_DEL_TUNEL> con el UUID real (2 lugares).
```

### Fase 3 — Pegale tus claves de API y arrancá (3 min)

```bash
# 1. Editar el .env y pegar GROQ_API_KEY (mínimo)
sudo nano /opt/motor-glosas/.env

# 2. Arrancar todo
cd /opt/motor-glosas
sudo docker compose up -d

# 3. Verificar (debe responder 200 OK)
curl https://iaglosassinac.help/health
```

¡Listo! La web responde en `https://iaglosassinac.help`.

---

## Operación diaria

### Ver el estado

```bash
sudo docker compose ps                # ambos servicios "running"
sudo docker compose logs -f motor     # logs del motor en vivo
sudo docker compose logs -f cloudflared # logs del túnel
```

### Aplicar la última versión del código

```bash
cd /opt/motor-glosas
sudo git pull origin motor-glosas
sudo docker compose up -d --build     # rebuild + redeploy
```

### Apagar el motor

```bash
sudo docker compose down              # los datos SQLite + soportes se conservan
```

### Backup manual de la base de datos

El motor hace backup automático diario a las 3 AM en `/opt/motor-glosas/data/backups/`
(rotación 14 días). Para hacer un backup manual:

```bash
sudo docker compose exec motor python -c \
  "from app.services.backup_sqlite import crear_backup; print(crear_backup())"
```

Para descargar un backup a tu PC:

```bash
scp usuario@maquina-hus:/opt/motor-glosas/data/backups/motorglosas-YYYYMMDD-HHMMSS.db ./
```

---

## Auto-arranque al reiniciar la máquina

Para que el motor levante solo si la máquina se reinicia (cortes de luz,
updates de Ubuntu, etc.):

```bash
sudo cp /opt/motor-glosas/deploy/systemd/motor-glosas.service.example \
        /etc/systemd/system/motor-glosas.service
sudo systemctl daemon-reload
sudo systemctl enable motor-glosas.service
sudo systemctl start motor-glosas.service
```

Ya queda activo. Para verificar:

```bash
sudo systemctl status motor-glosas.service
```

---

## Backup automático fuera de la máquina (opcional pero recomendado)

Si la máquina del HUS muere, los backups internos se pierden con ella.
Para conservarlos en otro lado (Google Drive, otra PC, GitHub repo privado),
configurá un cron diario que copie el último backup:

```bash
# Editar crontab del root
sudo crontab -e

# Agregar (4 AM, después del backup interno del motor que es a las 3 AM):
0 4 * * * /usr/bin/rsync -avz --remove-source-files \
  /opt/motor-glosas/data/backups/ usuario@otra-maquina:/ruta/destino/ \
  >> /var/log/motor-backup-externo.log 2>&1
```

---

## Resolución de problemas

### "La web da 502 Bad Gateway"

El túnel está vivo pero el motor no responde. Veo logs del motor:
```bash
sudo docker compose logs --tail 100 motor
```
Usualmente es un secret mal puesto en `.env` o la DB no inicializa.

### "El sitio no carga (DNS)"

Cloudflared no se conectó. Veo:
```bash
sudo docker compose logs cloudflared
```
Verificá que el UUID del túnel en `config.yml` coincida con el del archivo
`<UUID>.json` en `deploy/cloudflared/`.

### "Error 1033 Cloudflare Tunnel error" en el navegador

El túnel está registrado pero cloudflared no puede leer las credenciales.
Pasa cuando el archivo `<UUID>.json` quedó con permisos 400/600 (solo root),
pero el contenedor cloudflared corre como user `nonroot` y no puede leerlo.

```bash
# Ver permisos actuales
ls -l /opt/motor-glosas/deploy/cloudflared/*.json

# Arreglarlo
sudo chmod 644 /opt/motor-glosas/deploy/cloudflared/*.json
sudo docker compose restart cloudflared

# Verificar que el túnel registre las 4 conexiones (sea01, sea07, sea09, ...)
sudo docker compose logs cloudflared | grep "Registered tunnel connection"
```

### "Quedó sin espacio en disco"

```bash
df -h /opt/motor-glosas
# Si /data > 80% lleno, archivá soportes viejos o aumentá el disco.
sudo docker compose exec motor du -sh /data/*
```

### "Cómo cancelar Fly/Railway sin perder datos"

1. Llevá unos días corriendo en self-hosted en paralelo para confirmar.
2. Una vez confirmado, en el panel de Fly: Settings → Delete app.
   En Railway: Settings → Delete service.
3. Los datos viejos (cuando arregles Neon o desde un backup) los importás
   con `scripts/migrar_neon_a_sqlite.py` apuntando al SQLite del HUS.

---

## Costo total

| Componente | Costo |
|---|---|
| Máquina del HUS (ya existente) | $0 |
| Docker + cloudflared | $0 (open source) |
| Cloudflare Tunnel | $0 (free tier sin límite) |
| Dominio iaglosassinac.help | (ya lo tenés) |
| Groq (Llama 4 Scout) | $0 (gratis) |
| Anthropic / Gemini | opcionales |
| **TOTAL** | **$0/mes para siempre** |

---

## Ventajas vs los hostings de pago

| | Self-hosted HUS | Fly Hobby | Railway Hobby |
|---|---|---|---|
| Costo/mes | $0 | $5 | $5 |
| Datos en tu infra | ✅ | ❌ EE.UU. | ❌ EE.UU. |
| HTTPS automático | ✅ | ✅ | ✅ |
| Sin abrir puertos | ✅ (Cloudflare Tunnel) | n/a | n/a |
| Disco persistente | ✅ ilimitado | ✅ 3GB | ✅ 5GB |
| Mantenés tu IP | ✅ | n/a | n/a |
| Auto-deploy desde Git | ❌ (manual git pull) | ✅ | ✅ |
| Si la máquina muere | manual recovery | Fly recovery | Railway recovery |

## Desventajas (sé honesto con ellos)

- **Dependes de que la máquina del HUS esté viva**. Si se apaga, se cae.
- **Updates manuales**: hay que correr `git pull && docker compose up -d`
  para aplicar nuevos cambios del repo (vs auto-deploy de Fly/Railway).
- **Vos sos el sysadmin**. Backups, monitoring, actualizaciones del OS.

Para mitigarlo:
1. Pedile a Infraestructura HUS que la máquina esté en un UPS.
2. Configurá el cron de backup externo (sección arriba).
3. Una vez al mes, `sudo apt update && sudo apt upgrade -y` en la máquina.
