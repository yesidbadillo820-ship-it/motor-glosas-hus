"""Genera la aplicación web: un archivo que se abre en el celular sin internet.

Todo lo que la pantalla muestra —los patrones encontrados y la medición contra
el histórico— **se calcula aquí, en Python**, y se inyecta como datos. La
aplicación solo dibuja. Así hay una sola implementación de cada regla: si el
detector estuviera además escrito en JavaScript, tarde o temprano las dos
versiones dirían cosas distintas y nadie sabría cuál creer.
"""

from __future__ import annotations

import json
import struct
import zlib
from collections.abc import Sequence
from pathlib import Path

from . import catalogo
from .dominio import Vela
from .medicion import CASOS_MINIMOS, HORIZONTES, medir_todo
from .patrones import PATRONES, buscar

PLANTILLA = Path(__file__).parent / "plantilla_web.html"
MARCA_INICIO = "/*<DATOS>*/"
MARCA_FIN = "/*</DATOS>*/"

#: Cuántas sesiones se llevan al gráfico. Más no cabe en una pantalla de
#: celular y solo hace pesado el archivo.
SESIONES_GRAFICO = 120

#: Cuántas apariciones recientes se listan.
APARICIONES_MOSTRADAS = 120

MANIFEST = {
    "name": "Velas — análisis de patrones",
    "short_name": "Velas",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0f1620",
    "theme_color": "#0f1620",
    "lang": "es",
    "icons": [
        {"src": "./icono-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "./icono-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    ],
}

SERVICE_WORKER = """/* Service worker del análisis de velas.
   Guarda la aplicación entera para que abra sin internet. */
const CACHE = "velas-v1";
const ARCHIVOS = ["./index.html", "./manifest.webmanifest",
                  "./icono-192.png", "./icono-512.png"];
self.addEventListener("install", ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", ev => {
  ev.waitUntil(caches.keys()
    .then(ns => Promise.all(ns.filter(n => n !== CACHE).map(n => caches.delete(n))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", ev => {
  if (ev.request.method !== "GET") return;
  ev.respondWith(caches.match(ev.request).then(r => r || fetch(ev.request)));
});
"""


def _icono_png(lado: int) -> bytes:
    """Un PNG liso del color de la aplicación, sin librerías de imagen."""
    r, g, b = 0x0F, 0x16, 0x20
    fila = b"\x00" + bytes([r, g, b] * lado)
    crudo = fila * lado

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (
            struct.pack(">I", len(datos))
            + tipo
            + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(crudo, 9))
        + trozo(b"IEND", b"")
    )


def _vela_json(v: Vela) -> dict:
    return {
        "f": v.fecha.isoformat(),
        "a": round(v.apertura, 6),
        "h": round(v.maximo, 6),
        "l": round(v.minimo, 6),
        "c": round(v.cierre, 6),
    }


def construir_datos(velas: Sequence[Vela], titulo: str) -> dict:
    """Todo lo que la pantalla necesita, ya calculado."""
    fichas = catalogo.cargar()
    apariciones = buscar(velas)
    resultados = medir_todo(velas, HORIZONTES)

    catalogo_json = []
    for p in PATRONES:
        f = fichas[p.clave]
        catalogo_json.append(
            {
                "clave": p.clave,
                "nombre": p.nombre,
                "velas": p.velas,
                "familia": p.familia.value,
                "familiaEtiqueta": p.familia.etiqueta,
                "sentimiento": p.sentimiento.value,
                "sentimientoEtiqueta": p.sentimiento.etiqueta,
                "fiabilidadLibro": p.fiabilidad_declarada.etiqueta,
                "pagina": f.pagina,
                "identificar": list(f.identificar),
                "significado": f.significado,
                "revisar": f.revisar,
            }
        )

    medicion = [
        {
            "clave": r.patron.clave,
            "sesiones": r.sesiones,
            "casos": r.casos,
            "aciertos": r.aciertos,
            "tasa": round(r.tasa, 4),
            "base": round(r.tasa_base, 4),
            "ventaja": round(r.ventaja, 4),
            "bajo": round(r.intervalo[0], 4),
            "alto": round(r.intervalo[1], 4),
            "rendimiento": round(r.rendimiento_medio, 6),
            "veredicto": r.veredicto,
            "medible": r.medible,
            "contradice": r.contradice_al_libro,
        }
        for r in resultados
    ]

    recientes = apariciones[-APARICIONES_MOSTRADAS:]
    indice_desde = max(0, len(velas) - SESIONES_GRAFICO)
    return {
        "titulo": titulo,
        "fuente": catalogo.fuente(),
        "horizontes": list(HORIZONTES),
        "casosMinimos": CASOS_MINIMOS,
        "resumen": {
            "sesiones": len(velas),
            "desde": velas[0].fecha.isoformat() if velas else None,
            "hasta": velas[-1].fecha.isoformat() if velas else None,
            "apariciones": len(apariciones),
            "primerCierre": round(velas[0].cierre, 6) if velas else 0,
            "ultimoCierre": round(velas[-1].cierre, 6) if velas else 0,
        },
        "catalogo": catalogo_json,
        "medicion": medicion,
        "grafico": [_vela_json(v) for v in velas[indice_desde:]],
        "graficoDesde": indice_desde,
        "apariciones": [
            {"clave": a.patron.clave, "fecha": a.fecha.isoformat(), "indice": a.indice}
            for a in recientes
        ],
    }


def exportar(destino: Path, velas: Sequence[Vela], titulo: str = "Histórico") -> Path:
    """Escribe la aplicación completa en `destino` y devuelve el índice."""
    destino.mkdir(parents=True, exist_ok=True)
    html = PLANTILLA.read_text(encoding="utf-8")

    inicio, fin = html.find(MARCA_INICIO), html.find(MARCA_FIN)
    if inicio < 0 or fin < 0:
        raise ValueError(f"La plantilla debe traer {MARCA_INICIO} … {MARCA_FIN}")

    datos = json.dumps(construir_datos(velas, titulo), ensure_ascii=False, separators=(",", ":"))
    indice = destino / "index.html"
    indice.write_text(html[: inicio + len(MARCA_INICIO)] + datos + html[fin:], encoding="utf-8")
    (destino / "manifest.webmanifest").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (destino / "sw.js").write_text(SERVICE_WORKER, encoding="utf-8")
    for lado in (192, 512):
        (destino / f"icono-{lado}.png").write_bytes(_icono_png(lado))
    return indice
