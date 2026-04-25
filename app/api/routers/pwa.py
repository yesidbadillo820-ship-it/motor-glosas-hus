"""Endpoints PWA y assets estáticos del shell de la app (Ronda 51 Paso 6).

Originalmente vivían dentro de app/main.py. Se extraen acá para:
  1. Reducir el tamaño de main.py (objetivo < 800 líneas)
  2. Consolidar el manejo del service worker (antes había dos handlers
     @app.get("/sw.js") duplicados — el segundo quedaba como dead code)
  3. Aislar la lógica de PWA (iconos generados dinámicamente, cache
     headers agresivos) de la lógica de negocio

Endpoints servidos aquí:
  - GET /                           → shell React (static/index.html)
  - GET /manifest.webmanifest       → manifiesto PWA
  - GET /sw.js                      → service worker (SIEMPRE no-store)
  - GET /icon-192.png / icon-512.png → iconos PWA generados con Pillow
  - GET /importar-masiva            → HTML importación masiva
  - GET /importar-recepcion         → HTML importación recepción
  - GET /reset-sw.html              → limpiador de SW colgado
  - GET /presentacion               → demo institucional

Notas:
  - El endpoint / NO incluye router.prefix porque FastAPI no soporta
    prefijos vacíos de forma limpia; por eso este router usa prefix="".
  - _NO_STORE_HEADERS fuerza no-store para evitar que navegadores o SW
    viejos sirvan HTML/JS cacheado tras un deploy.
"""
from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response


router = APIRouter(tags=["pwa"])


_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.get("/")
def root():
    return FileResponse("static/index.html", headers=_NO_STORE_HEADERS)


@router.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(
        "static/manifest.webmanifest",
        media_type="application/manifest+json",
    )


@router.get("/sw.js")
def pwa_service_worker():
    """Siempre no-store: si el navegador cachea sw.js viejo, los clientes
    quedan pegados en una versión anterior tras un deploy."""
    return FileResponse(
        "static/sw.js",
        media_type="application/javascript",
        headers=_NO_STORE_HEADERS,
    )


def _generar_icono_pwa(size: int) -> bytes:
    """Genera un icono PWA cuadrado con el azul institucional y 'HUS'."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (size, size), "#0b5d8a")
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.08)
    draw.ellipse(
        [pad, pad, size - pad, size - pad],
        outline="#ffffff", width=max(2, size // 80),
    )
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.42))
    except Exception:
        font = ImageFont.load_default()
    texto = "HUS"
    bbox = draw.textbbox((0, 0), texto, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((size - tw) // 2, (size - th) // 2 - int(size * 0.03)),
        texto, fill="#ffffff", font=font,
    )
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/icon-192.png")
def icon_192():
    return Response(
        content=_generar_icono_pwa(192), media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/icon-512.png")
def icon_512():
    return Response(
        content=_generar_icono_pwa(512), media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/importar-masiva")
def importar_masiva():
    return FileResponse("static/importar-masiva.html", headers=_NO_STORE_HEADERS)


@router.get("/importar-recepcion")
def importar_recepcion_page():
    return FileResponse("static/importar-recepcion.html", headers=_NO_STORE_HEADERS)


@router.get("/reset-sw.html")
def reset_sw():
    """Página de emergencia que desregistra cualquier service worker viejo y
    limpia el cache del navegador. Útil cuando un usuario queda pegado con
    una UI vieja. Uso: abrir https://.../reset-sw.html y esperar 3 seg."""
    html = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Limpiando cache…</title>
<style>body{font-family:sans-serif;max-width:600px;margin:80px auto;padding:20px;
text-align:center;color:#1f2937}h1{color:#059669}.ok{color:#059669;font-size:48px}</style>
</head><body>
<h1>🧹 Limpiando caché del navegador…</h1>
<p id="status">Procesando…</p>
<script>
(async () => {
  const log = (msg) => document.getElementById('status').innerHTML += '<br>' + msg;
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      for (const r of regs) { await r.unregister(); log('✓ SW desregistrado'); }
    }
    if ('caches' in window) {
      const keys = await caches.keys();
      for (const k of keys) { await caches.delete(k); log('✓ Cache borrado: ' + k); }
    }
    log('<br><span class="ok">✅ Listo</span>');
    log('<p>Redirigiendo a la aplicación en 2 segundos…</p>');
    setTimeout(() => { location.href = '/'; }, 2000);
  } catch (e) {
    log('⚠ Error: ' + e.message);
  }
})();
</script></body></html>"""
    return HTMLResponse(content=html, headers=_NO_STORE_HEADERS)


@router.get("/presentacion")
def presentacion_ia():
    """Presentación institucional del sistema IA (pública, sin login)."""
    return FileResponse("static/presentacion-ia.html")
