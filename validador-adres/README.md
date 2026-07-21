# Validador ADRES Web — FURIPS · Circular 022/2023

Aplicación web **independiente** (misma familia del Motor Glosas HUS) para
validar reclamaciones FURIPS desde el navegador, con el mismo motor de la
herramienta de línea de comandos (`tools/adres/validar_furips.py`).

## Qué hace

1. **Subir** los TXT `FURIPS1*`/`FURIPS2*` y un **ZIP con los soportes**
   (RIPS/CUV `.json`, factura `.xml`/`.pdf`, epicrisis `.pdf`). Sirven las
   dos organizaciones: carpetas por factura o carpeta plana (`SOPORTES`),
   asociando por el número de factura del nombre de cada archivo. Los TXT
   pueden ir dentro del mismo ZIP.
2. **Validar** en el servidor con progreso en vivo: malla de los 102
   campos del FURIPS 1 y 9 del FURIPS 2 (Circular 022/2023), coherencia
   FURIPS1↔FURIPS2 y cruce contra los soportes.
3. **Ver** el tablero: KPIs, distribución por estado, tabla de facturas
   con semáforo y soportes, y detalle por factura (hallazgos, 102 campos,
   líneas FURIPS 2, cruce de soportes, archivos).
4. **Descargar** el informe Excel completo de 7 hojas.

Los datos se procesan en el servidor donde corra la app (PC local o
servidor del hospital): **no salen de su red**.

## Cómo correrla

**Windows (doble clic):** `VALIDADOR_ADRES_WEB.cmd` — instala las
dependencias si faltan, levanta el servidor y abre
<http://localhost:8010>. Otros PC de la red pueden entrar a
`http://NOMBRE-DEL-PC:8010`.

**Manual:**

```bash
pip install -r validador-adres/requirements.txt
cd validador-adres
uvicorn app:app --host 0.0.0.0 --port 8010
```

**Docker (desde la raíz del repo):**

```bash
docker build -f validador-adres/Dockerfile -t validador-adres .
docker run -p 8010:8010 validador-adres
```

> La app importa el motor desde `tools/adres/validar_furips.py`: la
> carpeta `validador-adres/` debe vivir junto a `tools/` (estructura del
> repositorio). No hay código duplicado: un solo motor para el bot de
> línea de comandos y la web.

## API

| Método y ruta | Qué hace |
|---|---|
| `POST /api/validar` | multipart `archivos[]` (TXT/ZIP) + `?sin_pdf=true` opcional → `{id}` |
| `GET /api/validaciones/{id}/estado` | progreso: `{estado, progreso, total, mensaje}` |
| `GET /api/validaciones/{id}` | resultado: KPIs + resumen por factura |
| `GET /api/validaciones/{id}/facturas/{factura}` | detalle completo de una factura |
| `GET /api/validaciones/{id}/excel` | descarga el informe Excel de 7 hojas |
| `GET /api/salud` | estado del servicio y motores PDF disponibles |

## Seguridad y alcance (v1)

- Pensada para red interna/PC del auditor. **No trae login**: si se
  publica fuera de la red del hospital, póngala detrás de un proxy con
  autenticación (o pida la integración al Motor Glosas, que ya tiene
  login con 2FA).
- Archivos aceptados: `.txt`, `.zip` (y dentro del ZIP: `.json`, `.xml`,
  `.pdf`, `.txt`). Límite 500 MB por archivo. El ZIP se extrae con
  protección contra rutas maliciosas.
- Los trabajos viven en memoria/carpeta temporal y se limpian solos
  (se conservan los últimos 20).

## Normativa aplicada

Circular 022 de 2023 ADRES · Resolución 2284 de 2023 · Decreto 780/2016
(mod. 2466/2022) · Resolución 762 de 2023 ADRES.
