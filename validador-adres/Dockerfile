# Validador ADRES Web — imagen independiente
# Construir DESDE LA RAÍZ del repo (necesita tools/adres para el motor):
#   docker build -f validador-adres/Dockerfile -t validador-adres .
#   docker run -p 8010:8010 validador-adres
FROM python:3.11-slim

WORKDIR /srv

COPY validador-adres/requirements.txt ./validador-adres/requirements.txt
RUN pip install --no-cache-dir -r validador-adres/requirements.txt

COPY tools/adres ./tools/adres
COPY validador-adres ./validador-adres

WORKDIR /srv/validador-adres
EXPOSE 8010
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
