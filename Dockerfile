# Motor Glosas HUS — Dockerfile para Fly.io
# Python 3.11 (compatible con todas las dependencias del proyecto y
# probado contra los 800+ tests de la suite). Build slim para minimizar
# tamaño de imagen y tiempo de cold-start.

FROM python:3.11-slim

# Variables de entorno Python para producción
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema requeridas por:
#   • psycopg2-binary (libpq + build essentials por si toca compilar)
#   • pdfplumber / reportlab (libxml2, libfreetype, libjpeg)
#   • bcrypt (build essentials)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libxml2 \
        libfreetype6 \
        libjpeg62-turbo \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar deps Python primero (capa cacheada — no se reconstruye si
# requirements.txt no cambia). Esto acelera deploys futuros.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la app
COPY app/ /app/app/
COPY scripts/ /app/scripts/
COPY static/ /app/static/

# Carpeta de soportes — montada como volumen persistente Fly al
# correr (ver fly.toml). Si no se monta volumen, queda en disco
# efímero del contenedor (igual que Render Free /tmp).
RUN mkdir -p /data/soportes

# Variable que el motor lee para saber dónde guardar/leer soportes.
# El volumen persistente Fly se monta en /data; soportes en subcarpeta.
ENV SOPORTES_ROOT=/data/soportes \
    SOPORTES_LOCAL_ROOT=/data/soportes

# Puerto en el que uvicorn escucha — Fly lo enruta automáticamente a 443/80.
EXPOSE 8080

# Healthcheck básico: que /health devuelva 200 antes de marcarlo "healthy".
# Fly usa esto para zero-downtime deploys.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

# Comando final. 1 worker — la VM shared-cpu-1x con 512MB no soporta 2
# workers (cada Python con todas las deps pesa ~235MB → 2x235 + OS = OOM).
# Usamos 1 worker; los uploads pesados se hacen async (Anthropic con
# await httpx, pdf_service con run_in_executor) por lo que el endpoint
# /health sigue respondiendo entre await points incluso durante una
# extracción Claude de 60s.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
