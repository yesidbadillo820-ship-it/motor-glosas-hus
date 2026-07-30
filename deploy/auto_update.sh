#!/usr/bin/env bash
# auto_update.sh — chequea si hay cambios nuevos en origin/motor-glosas y
# rebuild + redeploy el motor si los hay. Idempotente: si no hay commits
# nuevos, sale silenciosamente sin tocar el container.
#
# Pensado para correr cada N minutos vía cron como root. Ejemplos:
#   # Cada 5 minutos
#   */5 * * * * /opt/motor-glosas/deploy/auto_update.sh >> /var/log/motor-auto-deploy.log 2>&1
#   # Cada 30 minutos
#   */30 * * * * /opt/motor-glosas/deploy/auto_update.sh >> /var/log/motor-auto-deploy.log 2>&1
#
# Variables de entorno opcionales:
#   REPO_DIR  — ruta al repo (default: /opt/motor-glosas)
#   BRANCH    — rama a seguir (default: motor-glosas)

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/motor-glosas}"
BRANCH="${BRANCH:-motor-glosas}"
LOCK_FILE="/var/run/motor-auto-deploy.lock"

ts() { date -Iseconds; }
log() { echo "[$(ts)] $*"; }

# Lock para evitar dos corridas en paralelo (si una build tarda > intervalo
# de cron, el segundo job se sale sin hacer nada en vez de chocar).
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "otra corrida en curso — salgo"
    exit 0
fi

cd "$REPO_DIR"

# Fetch silencioso. Si falla la red, salimos sin actualizar.
if ! git fetch origin "$BRANCH" --quiet 2>/dev/null; then
    log "git fetch falló (red?) — salgo sin actualizar"
    exit 0
fi

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse "origin/$BRANCH")

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
    # Sin cambios — exit silencioso para no spammear el log
    exit 0
fi

log "nuevos commits detectados ($LOCAL_SHA → $REMOTE_SHA), aplicando..."

# Pull fast-forward only — si hubo un commit local manual no documentado,
# no lo pisamos automáticamente: fallamos y queda en el log para revisar.
if ! git pull --ff-only origin "$BRANCH"; then
    log "ERROR: git pull --ff-only falló — hay divergencia local, revisar manualmente"
    exit 1
fi

# Ronda 30: guarda de memoria. Este script corre por cron en la e2-micro
# (1GB) y `up -d --build` rebuildea la imagen CON el motor corriendo — si
# hay poca RAM libre, el build estrangula la VM (colapso observado 8-jul).
# Si no hay al menos 500MB libres, posponemos: el próximo cron reintenta.
MEM_LIBRE=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
if (( MEM_LIBRE < 500 )); then
    log "SKIP: solo ${MEM_LIBRE}MB libres — build pospuesto al próximo ciclo"
    exit 0
fi

# Rebuild + redeploy. up -d --build hace el rebuild de la imagen Y reinicia
# el contenedor solo si la imagen cambió (no toca el motor si solo cambió
# un archivo .md, por ejemplo).
if ! docker compose up -d --build 2>&1; then
    log "ERROR: docker compose up -d --build falló"
    exit 1
fi

log "redeploy OK — motor corriendo en $(git rev-parse --short HEAD)"

# Limpieza post-deploy: cada rebuild deja la imagen anterior dangling y el
# cache de BuildKit crece sin límite — en el disco de la e2-micro termina
# llenando el filesystem. Solo toca imágenes SIN tag y cache de build; nunca
# la imagen corriendo, la de cloudflared, ni volúmenes/datos.
docker image prune -f >/dev/null || log "WARN: docker image prune falló (no fatal)"
docker builder prune -f --keep-storage 1GB >/dev/null || log "WARN: docker builder prune falló (no fatal)"
