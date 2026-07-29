"""Centro de Automatización: correr las herramientas desde la aplicación.

EL PROBLEMA QUE RESUELVE. El repositorio tiene 34 herramientas que convierten
el archivo de un pagador al formato del ERP, consolidan ZIP, arman informes.
Todas funcionan. Ninguna se podía usar desde la aplicación: el auditor tenía
que copiar el guion a un PC con Python, abrir una consola y escribir la orden
con sus parámetros. En la práctica eso significa que las usa una persona.

Aquí cada herramienta se declara **como datos** —qué archivo pide, qué
devuelve, qué parámetros acepta— y el ejecutor la corre en un directorio
temporal, sin que nadie toque una consola.

POR QUÉ COMO DATOS Y NO COMO CÓDIGO. Agregar la herramienta número 35 no
puede exigir tocar el router ni la pantalla: se agrega una ficha a
`CATALOGO` y aparece sola en el catálogo, en la pantalla y en la API. Es la
misma idea del perfil por pagador: lo que cambia por cliente es dato, no
código.

LO QUE NO HACE. No corre nada que abra un navegador ni toque un portal —esos
bots necesitan credenciales y una sesión con la EPS, y van por el camino de
las corridas con evidencia—. Aquí solo entran las que reciben un archivo y
devuelven otro.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"

# Tamaño máximo del archivo de entrada. Los Excel de glosas del HUS más
# grandes rondan los 6 MB (18.378 filas del Dispensario); 25 MB deja margen
# sobrado sin permitir que alguien suba un volcado de la base.
MAX_BYTES = 25 * 1024 * 1024

# Tiempo máximo de una corrida. La producción es una máquina pequeña y estas
# conversiones son de segundos; si una se cuelga, no puede dejar sin CPU a los
# gestores que están respondiendo glosas.
LIMITE_SEGUNDOS = 120


@dataclass(frozen=True)
class Parametro:
    """Un dato que la herramienta pide además del archivo."""

    nombre: str
    etiqueta: str
    ayuda: str = ""
    obligatorio: bool = False
    valor_defecto: str = ""
    tipo: str = "texto"  # texto | fecha | numero | si_no

    def como_dict(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre,
            "etiqueta": self.etiqueta,
            "ayuda": self.ayuda,
            "obligatorio": self.obligatorio,
            "valor_defecto": self.valor_defecto,
            "tipo": self.tipo,
        }


@dataclass(frozen=True)
class Automatizacion:
    """Una herramienta que el auditor puede correr desde la aplicación."""

    id: str
    nombre: str
    # Qué hace, dicho para el auditor: sin nombres de archivo ni de función.
    que_hace: str
    # Cuándo la usa. Es lo que más se pregunta al ver un catálogo.
    cuando_usarla: str
    modulo: str  # módulo de `tools/` que la implementa
    extensiones: tuple[str, ...] = (".xlsx",)
    salida: str = "carpeta"  # carpeta (varios archivos → zip) | archivo
    parametros: tuple[Parametro, ...] = ()
    grupo: str = "Conversión"
    # Cómo se arma la orden. Recibe (entrada, salida, opciones) y devuelve la
    # lista de argumentos que la herramienta espera.
    argumentos: Callable[[Path, Path, dict[str, str]], list[str]] = field(repr=False, default=None)

    def como_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "que_hace": self.que_hace,
            "cuando_usarla": self.cuando_usarla,
            "grupo": self.grupo,
            "extensiones": list(self.extensiones),
            "salida": self.salida,
            "parametros": [p.como_dict() for p in self.parametros],
        }


def _opt(opciones: dict[str, str], clave: str, bandera: str) -> list[str]:
    """`--bandera valor` solo si el auditor escribió algo."""
    valor = (opciones.get(clave) or "").strip()
    return [bandera, valor] if valor else []


# ─── El catálogo ──────────────────────────────────────────────────────────
# Agregar una herramienta es agregar una ficha acá. No hay que tocar el
# router ni la pantalla.

CATALOGO: tuple[Automatizacion, ...] = (
    Automatizacion(
        id="objeciones-savia",
        nombre="Glosas de SAVIA SALUD → formato del ERP",
        que_hace=(
            "Toma el Excel de glosas que manda SAVIA SALUD y lo convierte al "
            "formato de 16 columnas que acepta el ERP, con un archivo por factura."
        ),
        cuando_usarla="Cuando llega el archivo de glosas de SAVIA y hay que subirlo al ERP.",
        modulo="organizar_objeciones_savia",
        parametros=(
            Parametro(
                "fecha",
                "Fecha del documento",
                "Si se deja vacía, se usa la de hoy.",
                tipo="fecha",
            ),
            Parametro(
                "codigo_sufijo",
                "Sufijo del código de glosa",
                "SAVIA manda códigos de 4 caracteres (TA08) y el ERP pide 6 (TA0801).",
                valor_defecto="01",
            ),
        ),
        argumentos=lambda e, s, o: (
            ["--entrada", str(e), "--salida", str(s)]
            + _opt(o, "fecha", "--fecha")
            + _opt(o, "codigo_sufijo", "--codigo-sufijo")
        ),
    ),
    Automatizacion(
        id="objeciones-vco",
        nombre="Glosas de VCO → formato del ERP",
        que_hace=(
            "Convierte el consolidado de objeciones de VCO al formato de 16 columnas del ERP."
        ),
        cuando_usarla="Cuando llega el consolidado de VCO y hay que armar el cargue.",
        modulo="organizar_objeciones_vco",
        parametros=(
            Parametro("fecha_documento", "Fecha del documento", tipo="fecha"),
            Parametro("hoja", "Hoja del Excel", "Si el archivo trae varias hojas."),
        ),
        argumentos=lambda e, s, o: (
            ["--entrada", str(e), "--salida", str(s)]
            + _opt(o, "fecha_documento", "--fecha-documento")
            + _opt(o, "hoja", "--hoja")
        ),
    ),
    Automatizacion(
        id="objeciones-emssanar",
        nombre="Glosas de EMSSANAR (PDF) → formato del ERP",
        que_hace=(
            "Lee el PDF de objeciones de EMSSANAR, saca las glosas y arma el "
            "Excel de cargue del ERP."
        ),
        cuando_usarla="Cuando EMSSANAR manda las glosas en PDF en vez de Excel.",
        modulo="organizar_objeciones_emssanar",
        extensiones=(".pdf",),
        salida="archivo",
        parametros=(
            Parametro("fecha", "Fecha del documento", tipo="fecha"),
            Parametro("usuario", "Usuario del ERP", valor_defecto="999"),
        ),
        argumentos=lambda e, s, o: (
            ["--pdf", str(e), "--salida", str(s / "OBJECIONES_EMSSANAR.xlsx")]
            + _opt(o, "fecha", "--fecha")
            + _opt(o, "usuario", "--usuario")
        ),
    ),
    Automatizacion(
        id="tramite-masivo",
        nombre="Trámite masivo → Excel de cargue",
        que_hace="Convierte el archivo de trámites al Excel que acepta el ERP.",
        cuando_usarla="Cuando hay que cargar muchos trámites de una vez.",
        modulo="convertir_tramite_masivo",
        salida="archivo",
        grupo="Cargue",
        argumentos=lambda e, s, o: [str(e), str(s / "TRAMITE_MASIVO.xlsx")],
    ),
)

_POR_ID = {a.id: a for a in CATALOGO}


def catalogo() -> list[dict[str, Any]]:
    return [a.como_dict() for a in CATALOGO]


def obtener(id_automatizacion: str) -> Automatizacion | None:
    return _POR_ID.get(id_automatizacion)


class ErrorAutomatizacion(RuntimeError):
    """Falla previsible que se le puede explicar al auditor."""


@dataclass
class Resultado:
    """Lo que produjo una corrida, ya en memoria.

    Los archivos van como `(nombre, bytes)` y no como rutas: el directorio
    temporal se borra al terminar, así que devolver rutas sería devolver
    caminos a archivos que ya no existen.
    """

    ok: bool
    mensaje: str
    archivos: list[tuple[str, bytes]]
    salida_texto: str
    segundos: float

    @property
    def nombres(self) -> list[str]:
        return [n for n, _ in self.archivos]

    @property
    def bytes_totales(self) -> int:
        return sum(len(b) for _, b in self.archivos)


def _cargar(modulo: str):
    """Importa la herramienta de `tools/` sin dejar `sys.path` sucio."""
    ruta = str(_TOOLS)
    agregado = ruta not in sys.path
    if agregado:
        sys.path.insert(0, ruta)
    try:
        return importlib.import_module(modulo)
    finally:
        if agregado and ruta in sys.path:
            sys.path.remove(ruta)


def ejecutar(
    id_automatizacion: str,
    contenido: bytes,
    nombre_archivo: str,
    opciones: dict[str, str] | None = None,
) -> Resultado:
    """Corre una automatización sobre el archivo que subió el auditor.

    Todo pasa en un directorio temporal que se borra al terminar: la
    herramienta nunca ve el disco de la aplicación ni deja restos.
    """
    auto = obtener(id_automatizacion)
    if auto is None:
        raise ErrorAutomatizacion(f"No existe la automatización '{id_automatizacion}'")

    if not contenido:
        raise ErrorAutomatizacion("El archivo llegó vacío")
    if len(contenido) > MAX_BYTES:
        raise ErrorAutomatizacion(
            f"El archivo pesa {len(contenido) / 1048576:.1f} MB y el máximo son "
            f"{MAX_BYTES // 1048576} MB"
        )

    sufijo = Path(nombre_archivo or "").suffix.lower()
    if sufijo not in auto.extensiones:
        esperadas = " o ".join(auto.extensiones)
        raise ErrorAutomatizacion(
            f"Esta automatización espera un archivo {esperadas} y llegó '{sufijo or 'sin extensión'}'"
        )

    faltan = [
        p.etiqueta for p in auto.parametros if p.obligatorio and not (opciones or {}).get(p.nombre)
    ]
    if faltan:
        raise ErrorAutomatizacion("Faltan datos obligatorios: " + ", ".join(faltan))

    modulo = _cargar(auto.modulo)
    if not hasattr(modulo, "main"):
        raise ErrorAutomatizacion(f"La herramienta '{auto.modulo}' no se puede correr desde aquí")

    inicio = time.monotonic()
    trabajo = Path(tempfile.mkdtemp(prefix="sinac_auto_"))
    try:
        entrada = trabajo / (Path(nombre_archivo).name or "entrada")
        entrada.write_bytes(contenido)
        salida = trabajo / "salida"
        salida.mkdir()

        argv = auto.argumentos(entrada, salida, opciones or {})
        import contextlib
        import io

        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                codigo = modulo.main(argv)
        except SystemExit as e:  # las CLI salen con sys.exit
            codigo = e.code if isinstance(e.code, int) else 1
        except Exception as e:
            raise ErrorAutomatizacion(f"La herramienta falló: {type(e).__name__}: {e}") from e

        segundos = time.monotonic() - inicio
        if segundos > LIMITE_SEGUNDOS:
            raise ErrorAutomatizacion(
                f"La corrida tardó {segundos:.0f} s, más del límite de {LIMITE_SEGUNDOS} s"
            )

        generados = sorted(p for p in salida.rglob("*") if p.is_file())
        if codigo not in (0, None) and not generados:
            raise ErrorAutomatizacion(
                buffer.getvalue().strip()[-500:] or "La herramienta terminó con error"
            )
        if not generados:
            raise ErrorAutomatizacion(
                "La herramienta no produjo ningún archivo. "
                + (buffer.getvalue().strip()[-300:] or "Revise que el archivo sea el correcto.")
            )

        # Se leen a memoria antes de borrar el temporal.
        leidos = [(p.name, p.read_bytes()) for p in generados]
        return Resultado(
            ok=True,
            mensaje=f"{len(leidos)} archivo(s) generado(s)",
            archivos=leidos,
            salida_texto=buffer.getvalue().strip()[-2000:],
            segundos=segundos,
        )
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
