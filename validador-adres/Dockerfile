# Validador ADRES Web — imagen independiente
# Construir DESDE LA RAÍZ del repo (necesita tools/adres para el motor):
#   docker build -f validador-adres/Dockerfile -t validador-adres .
#   docker run -p 8010:8010 validador-adres
FROM python:3.11-slim

WORKDIR /srv

COPY validador-adres/requirements.txt ./validador-adres/requirements.txt
# El OCR (pypdfium2 + rapidocr) es opcional: si su plataforma no tiene rueda
# disponible, la imagen se construye igual sin OCR.
RUN pip install --no-cache-dir -r validador-adres/requirements.txt || \
    (grep -vE "pypdfium2|rapidocr" validador-adres/requirements.txt > /tmp/req.txt && \
     pip install --no-cache-dir -r /tmp/req.txt)

COPY tools/adres ./tools/adres
COPY validador-adres ./validador-adres

WORKDIR /srv/validador-adres
EXPOSE 8010
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
