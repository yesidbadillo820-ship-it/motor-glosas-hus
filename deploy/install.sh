#!/usr/bin/env bash
# install.sh — instalador one-shot del Motor Glosas HUS en una máquina Linux
#
# Qué hace:
#   1. Instala Docker + docker-compose si no están.
#   2. Instala cloudflared (la CLI de Cloudflare Tunnel).
#   3. Clona/actualiza el repo en /opt/motor-glosas.
#   4. Genera un .env si no existe (con claves aleatorias).
#   5. Crea los directorios de datos con los permisos correctos.
#   6. Te imprime los próximos 3 pasos manuales (los que requieren
#      decisión tuya: auth en Cloudflare, configurar dominio, etc.).
#
# IDEMPOTENTE: podés re-correrlo sin romper nada — solo agrega lo que falta.
#
# Uso (con sudo, desde cualquier carpeta):
#   curl -fsSL https://raw.githubusercontent.com/yesidbadillo820-ship-it/motor-glosas-hus/motor-glosas/deploy/install.sh | sudo bash
#
# O ejecutándolo desde el repo clonado:
#   sudo bash deploy/install.sh

set -euo pipefail

# Colores para logs (solo si el output es un TTY)
if [[ -t 1 ]]; then
    AZUL='\033[0;34m'; VERDE='\033[0;32m'; AMARILLO='\033[0;33m'; ROJO='\033[0;31m'; NC='\033[0m'
else
    AZUL=''; VERDE=''; AMARILLO=''; ROJO=''; NC=''
fi
log() { echo -e "${AZUL}[install]${NC} $*"; }
ok()  { echo -e "${VERDE}[ ✓ ]${NC} $*"; }
warn(){ echo -e "${AMARILLO}[ ! ]${NC} $*"; }
err() { echo -e "${ROJO}[ ✗ ]${NC} $*" >&2; }

REPO_URL="${REPO_URL:-https://github.com/yesidbadillo820-ship-it/motor-glosas-hus.git}"
REPO_DIR="${REPO_DIR:-/opt/motor-glosas}"
BRANCH="${BRANCH:-motor-glosas}"

if [[ $EUID -ne 0 ]]; then
    err "Este script debe correrse como root (sudo bash deploy/install.sh)"
    exit 1
fi

# ─── 1. Docker ────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
    ok "Docker ya instalado ($(docker --version))"
else
    log "Instalando Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    ok "Docker instalado"
fi

# ─── 2. cloudflared ───────────────────────────────────────────────────
if command -v cloudflared >/dev/null 2>&1; then
    ok "cloudflared ya instalado ($(cloudflared --version | head -1))"
else
    log "Instalando cloudflared..."
    ARQ=$(dpkg --print-architecture 2>/dev/null || uname -m)
    case "$ARQ" in
        amd64|x86_64) PKG="cloudflared-linux-amd64.deb" ;;
        arm64|aarch64) PKG="cloudflared-linux-arm64.deb" ;;
        *) err "Arquitectura desconocida: $ARQ"; exit 1 ;;
    esac
    TMP=$(mktemp)
    curl -fsSL -o "$TMP" "https://github.com/cloudflare/cloudflared/releases/latest/download/$PKG"
    dpkg -i "$TMP" && rm -f "$TMP"
    ok "cloudflared instalado"
fi

# ─── 3. Repo ──────────────────────────────────────────────────────────
if [[ -d "$REPO_DIR/.git" ]]; then
    log "Actualizando repo existente en $REPO_DIR..."
    cd "$REPO_DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
    ok "Repo actualizado a la última versión de $BRANCH"
else
    log "Clonando repo en $REPO_DIR..."
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
    cd "$REPO_DIR"
    ok "Repo clonado"
fi

# ─── 4. .env con valores aleatorios seguros ───────────────────────────
if [[ -f "$REPO_DIR/.env" ]]; then
    ok ".env ya existe — no se sobrescribe"
else
    log "Generando .env con claves aleatorias seguras..."
    JWT_SECRET=$(openssl rand -hex 32)
    SECRET_KEY=$(openssl rand -hex 32)
    ADMIN_PASS=$(openssl rand -base64 18 | tr -d '/+' | head -c 16)
    cat > "$REPO_DIR/.env" <<EOF
# Motor Glosas HUS — generado por deploy/install.sh el $(date -Iseconds)
DATABASE_URL=sqlite:////data/motorglosas.db
ENV=production
LOG_LEVEL=INFO
SOPORTES_ROOT=/data/soportes
SOPORTES_LOCAL_ROOT=/data/soportes
ANTHROPIC_MODEL=claude-sonnet-4-5

# Claves IA — COMPLETAR estas líneas con tus valores reales:
GROQ_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

# Secretos del motor (generados aleatoriamente — NO COMPARTIR)
JWT_SECRET=$JWT_SECRET
SECRET_KEY=$SECRET_KEY

# Admin inicial — apuntá este password en algún lado seguro:
ADMIN_PASSWORD=$ADMIN_PASS
FORCE_RESET_ADMIN_PASSWORD=1
EOF
    chmod 600 "$REPO_DIR/.env"
    ok ".env generado en $REPO_DIR/.env"
    warn "Tu password de admin inicial es: $ADMIN_PASS"
    warn "Apuntálo AHORA — al primer login te va a pedir cambiarlo."
fi

# ─── 5. Carpetas de datos ─────────────────────────────────────────────
mkdir -p "$REPO_DIR/data/soportes" "$REPO_DIR/data/backups"
chmod -R 700 "$REPO_DIR/data"
ok "Carpetas /data creadas con permisos 700"

# ─── 6. Próximos pasos ────────────────────────────────────────────────
cat <<'EOF'

╔════════════════════════════════════════════════════════════════════════╗
║  Instalación base completa. Faltan 3 pasos MANUALES (decisión tuya): ║
╠════════════════════════════════════════════════════════════════════════╣
║                                                                        ║
║  1) Pegale tus claves de API al .env:                                ║
║       sudo nano /opt/motor-glosas/.env                                 ║
║     (mínimo GROQ_API_KEY — las demás son opcionales)                 ║
║                                                                        ║
║  2) Autenticate en Cloudflare y crea el túnel:                       ║
║       cloudflared tunnel login            # te abre el browser         ║
║       cloudflared tunnel create motor-glosas                          ║
║       cloudflared tunnel route dns motor-glosas iaglosassinac.help    ║
║                                                                        ║
║     Esto te genera un archivo <UUID>.json en ~/.cloudflared/.        ║
║     Movelo al repo:                                                   ║
║       sudo cp ~/.cloudflared/<UUID>.json /opt/motor-glosas/deploy/cloudflared/ ║
║                                                                        ║
║  3) Configurar el túnel y arrancar el motor:                         ║
║       cd /opt/motor-glosas/deploy/cloudflared                         ║
║       sudo cp config.yml.example config.yml                          ║
║       sudo nano config.yml         # pegar el UUID en los placeholders║
║       cd /opt/motor-glosas                                            ║
║       sudo docker compose up -d                                       ║
║                                                                        ║
║  Verificá que funciona:                                              ║
║       sudo docker compose ps        # ambos services "running"        ║
║       sudo docker compose logs -f motor       # logs del motor        ║
║       curl https://iaglosassinac.help/health  # debe responder OK     ║
║                                                                        ║
║  Doc completa: docs/SELF_HOSTED_HUS.md                               ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝

EOF
ok "Instalación base lista."
