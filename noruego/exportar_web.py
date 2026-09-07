"""Genera la aplicación web instalable en el celular (PWA).

Escribe tres archivos en la carpeta de destino:

- ``index.html``  — la aplicación entera, con el curso adentro.
- ``manifest.webmanifest`` — para que el celular la pueda instalar.
- ``sw.js``       — el service worker que la deja funcionar sin internet.

Si la carpeta de destino se sirve por HTTP (por ejemplo desde ``static/``), el
celular ofrece «Agregar a la pantalla de inicio» y a partir de ahí abre como
una aplicación. Abierta con doble clic (file://) también funciona, solo que
sin instalación ni caché: el navegador no permite service workers ahí.

Los ejercicios se generan aquí, en Python, con varias semillas por lección, y
viajan ya hechos dentro del archivo. Así el motor de generación vive en un solo
sitio y la aplicación no tiene que repetirlo en JavaScript.
"""

from __future__ import annotations

import json
from pathlib import Path

from .curso import MODULOS, todas_las_lecciones
from .dominio import (
    IDIOMA_VOZ,
    TEMAS,
    VIDAS_POR_LECCION,
    XP_ACIERTO,
    XP_LECCION,
    XP_LECCION_PERFECTA,
    Nivel,
)
from .ejercicios import Ejercicio, generar
from .lexico import Lexico, cargar

PLANTILLA: Path = Path(__file__).parent / "plantilla_web.html"
MARCA_INICIO = "/*<DATOS>*/"
MARCA_FIN = "/*</DATOS>*/"

#: Cuántas versiones distintas de cada lección se generan. La aplicación rota
#: entre ellas, para que repetir una lección no sea repetir las mismas
#: preguntas palabra por palabra.
VARIANTES: int = 3


def _ejercicio_a_dict(e: Ejercicio) -> dict:
    salida = {
        "id": e.id,
        "tipo": e.tipo.value,
        "enunciado": e.enunciado,
        "fuente": e.fuente,
        "audio": e.audio,
    }
    if e.opciones:
        salida["opciones"] = list(e.opciones)
        salida["correcta"] = e.correcta
    for campo in ("respuesta", "contexto", "pista", "explicacion"):
        valor = getattr(e, campo)
        if valor:
            salida[campo] = valor
    if e.alternativas:
        salida["alternativas"] = list(e.alternativas)
    if e.orden:
        salida["orden"] = list(e.orden)
    if e.datos:
        salida["datos"] = e.datos
    return salida


def construir_datos(lexico: Lexico | None = None) -> dict:
    """Arma el diccionario completo que la aplicación lleva adentro."""
    lx = lexico or cargar()
    lecciones = []
    for modulo, leccion, indice in todas_las_lecciones():
        variantes = []
        for semilla in range(VARIANTES):
            hechos = generar(lx, leccion, semilla=semilla)
            if hechos:
                variantes.append([_ejercicio_a_dict(e) for e in hechos])
        lecciones.append(
            {
                "clave": leccion.clave,
                "modulo": modulo.clave,
                "titulo": leccion.titulo,
                "objetivo": leccion.objetivo,
                "indice": indice,
                "gramatica": list(leccion.gramatica),
                "sonidos": list(leccion.sonidos),
                "dialogo": leccion.dialogo,
                "variantes": variantes,
                "tipos": [t.value for t in leccion.tipos],
            }
        )
    return {
        "version": 1,
        "idiomaVoz": IDIOMA_VOZ,
        "niveles": [
            {"clave": n.value, "titulo": n.titulo, "descripcion": n.descripcion, "orden": n.orden}
            for n in Nivel
        ],
        "temas": [{"clave": t.clave, "nombre": t.nombre, "icono": t.icono} for t in TEMAS],
        "modulos": [
            {
                "clave": m.clave,
                "titulo": m.titulo,
                "icono": m.icono,
                "nivel": m.nivel.value,
                "descripcion": m.descripcion,
                "lecciones": [le.clave for le in m.lecciones],
            }
            for m in MODULOS
        ],
        "lecciones": lecciones,
        "lexico": {tipo: list(grupo) for tipo, grupo in lx.todo.items()},
        "notas": lx.notas,
        "juego": {
            "xpAcierto": XP_ACIERTO,
            "xpLeccion": XP_LECCION,
            "xpPerfecta": XP_LECCION_PERFECTA,
            "vidas": VIDAS_POR_LECCION,
        },
    }


MANIFEST = {
    "name": "Norsk — curso de noruego",
    "short_name": "Norsk",
    "description": "Curso de noruego para hispanohablantes, de cero a nivel avanzado.",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0E1420",
    "theme_color": "#0E1420",
    "lang": "es",
    "categories": ["education"],
    "icons": [
        {
            "src": "./icono-192.png",
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any maskable",
        },
        {
            "src": "./icono-512.png",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any maskable",
        },
    ],
}

SERVICE_WORKER = """/* Service worker del curso de noruego.
   Guarda la aplicación en el celular la primera vez que se abre, y a partir de
   ahí la sirve desde el propio teléfono: funciona sin internet y arranca al
   instante. Cuando hay conexión, busca una versión nueva por detrás. */
const CACHE = "norsk-v__VERSION__";
const ARCHIVOS = ["./", "./index.html", "./manifest.webmanifest"];

self.addEventListener("install", ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", ev => {
  ev.waitUntil(caches.keys().then(nombres =>
    Promise.all(nombres.filter(n => n !== CACHE).map(n => caches.delete(n)))
  ).then(() => self.clients.claim()));
});
self.addEventListener("fetch", ev => {
  if (ev.request.method !== "GET") return;
  ev.respondWith(
    caches.match(ev.request).then(guardado => {
      const red = fetch(ev.request).then(resp => {
        if (resp && resp.status === 200 && resp.type === "basic") {
          const copia = resp.clone();
          caches.open(CACHE).then(c => c.put(ev.request, copia));
        }
        return resp;
      }).catch(() => guardado);
      return guardado || red;
    })
  );
});
"""


#: Icono mínimo en PNG (un cuadro del color de la marca). Se genera aquí para
#: no depender de un archivo binario en el repositorio.
def _icono_png(lado: int) -> bytes:
    import struct
    import zlib

    r, g, b = 0x2E, 0x7D, 0xF6
    fila = b"\x00" + bytes([r, g, b] * lado)
    crudo = fila * lado

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (
            struct.pack(">I", len(datos))
            + tipo
            + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
        )

    cabecera = struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", cabecera)
        + trozo(b"IDAT", zlib.compress(crudo, 9))
        + trozo(b"IEND", b"")
    )


def exportar(
    destino: Path,
    lexico: Lexico | None = None,
    plantilla: Path | None = None,
) -> Path:
    """Escribe la aplicación completa en ``destino`` y devuelve el index.html."""
    origen = plantilla or PLANTILLA
    if not origen.is_file():
        raise FileNotFoundError(f"No se encuentra la plantilla: {origen}")
    html = origen.read_text(encoding="utf-8")
    inicio, fin = html.find(MARCA_INICIO), html.find(MARCA_FIN)
    if inicio < 0 or fin < 0 or fin < inicio:
        raise ValueError(f"La plantilla debe traer {MARCA_INICIO} … {MARCA_FIN}")

    datos = construir_datos(lexico)
    # «</script>» dentro de una cadena JSON cerraría la etiqueta antes de tiempo.
    serializado = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    carpeta = Path(destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    indice = carpeta / "index.html"
    indice.write_text(
        html[: inicio + len(MARCA_INICIO)] + serializado + html[fin:], encoding="utf-8"
    )
    (carpeta / "manifest.webmanifest").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (carpeta / "sw.js").write_text(
        SERVICE_WORKER.replace("__VERSION__", str(datos["version"])), encoding="utf-8"
    )
    for lado in (192, 512):
        (carpeta / f"icono-{lado}.png").write_bytes(_icono_png(lado))
    return indice
