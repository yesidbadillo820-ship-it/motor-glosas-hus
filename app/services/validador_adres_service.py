"""Núcleo del validador ADRES/FURIPS, compartido por sus dos entradas.

Hasta el 13-08-2026 este código vivía dentro de `validador-adres/app.py`, la
aplicación aparte que el auditor levanta en el puerto 8010 con un doble clic.
Funciona bien, pero obliga a arrancar un segundo programa y a manejar dos
ventanas: por eso Yesid pidió que la validación viva DENTRO del portal, donde
ya está trabajando y donde ya hay sesión y control de roles.

La orquestación se movió acá para que las dos entradas —la app aparte y el
portal— llamen al MISMO código. Duplicarla habría significado que cada
corrección hay que hacerla dos veces, y que tarde o temprano las dos
versiones digan cosas distintas sobre la misma factura.

Lo que hace, en orden: descubre los FURIPS 1 y 2 y los soportes de lo que se
subió, valida la malla de la Circular 022/2023 factura por factura, cruza
cada soporte contra lo declarado, y deja el resultado listo para el informe
en Excel.

El trabajo corre en segundo plano y se consulta por su identificador: una
validación de un paquete grande tarda minutos y el navegador no puede quedar
esperando.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("motor_glosas")

# ── Límites de lo que se acepta subir ────────────────────────────────────
# El tope de tamaño y la lista de extensiones son la primera defensa: al
# validador llegan paquetes del servidor de facturación y no tiene por qué
# recibir ejecutables ni archivos de cientos de megas.
MAX_MB_ARCHIVO = 500
EXT_PERMITIDAS = frozenset({".txt", ".zip", ".json", ".xml", ".pdf"})
MAX_TRABAJOS_VIVOS = 20

DIR_TRABAJOS = Path(tempfile.gettempdir()) / "validador_adres_web"
DIR_TRABAJOS.mkdir(parents=True, exist_ok=True)

NOMBRE_INFORME = "INFORME_VALIDACION_FURIPS.xlsx"

_trabajos: dict[str, dict] = {}
_lock = threading.Lock()


def _motor():
    """Carga el validador FURIPS, que vive fuera del paquete `app`."""
    raiz = Path(__file__).resolve().parent.parent.parent
    ruta = str(raiz / "tools" / "adres")
    if ruta not in sys.path:
        sys.path.insert(0, ruta)
    import validar_furips as vf

    return vf


# ── Trabajos ─────────────────────────────────────────────────────────────


def crear_trabajo() -> tuple[str, Path]:
    """Reserva un identificador y su carpeta de trabajo."""
    trabajo_id = uuid.uuid4().hex[:12]
    carpeta = DIR_TRABAJOS / trabajo_id
    carpeta.mkdir(parents=True, exist_ok=True)
    with _lock:
        _trabajos[trabajo_id] = {
            "estado": "EN_COLA",
            "progreso": 0,
            "total": 0,
            "mensaje": "Preparando la validación…",
            "resultados": [],
            "obs": [],
            "resumen": [],
            "creado": time.time(),
        }
    # Se barre DESPUÉS de insertar: así el tope se cumple exacto. Barriendo
    # antes siempre quedaba uno de más.
    _limpiar_viejos()
    return trabajo_id, carpeta


def estado(trabajo_id: str) -> dict | None:
    with _lock:
        tr = _trabajos.get(trabajo_id)
        return dict(tr) if tr else None


def carpeta_de(trabajo_id: str) -> Path:
    return DIR_TRABAJOS / trabajo_id


def ruta_informe(trabajo_id: str) -> Path:
    return carpeta_de(trabajo_id) / NOMBRE_INFORME


HORAS_HUERFANO = 24


def _limpiar_viejos(max_trabajos: int = MAX_TRABAJOS_VIVOS) -> None:
    """Conserva solo los últimos trabajos, en memoria y en disco.

    Sin esto, el disco del PC de cartera se llena con los paquetes de cada
    validación: son ZIP de facturación con PDF adentro.

    Barre DOS cosas. Los trabajos de más de esta corrida, y los huérfanos:
    las carpetas que dejó un arranque anterior del motor. El motor del
    hospital se reinicia a diario —hay un vigilante que lo levanta—, y en
    cada arranque la memoria de trabajos vuelve a cero mientras las carpetas
    siguen ahí. Sin este barrido no se borraban nunca.
    """
    import shutil

    with _lock:
        vivos = set(_trabajos)
        viejos = (
            sorted(_trabajos, key=lambda k: _trabajos[k]["creado"])[:-max_trabajos]
            if len(_trabajos) > max_trabajos
            else []
        )
        for k in viejos:
            _trabajos.pop(k, None)
            vivos.discard(k)

    for k in viejos:
        shutil.rmtree(DIR_TRABAJOS / k, ignore_errors=True)

    limite = time.time() - HORAS_HUERFANO * 3600
    try:
        for carpeta in DIR_TRABAJOS.iterdir():
            if not carpeta.is_dir() or carpeta.name in vivos:
                continue
            try:
                if carpeta.stat().st_mtime < limite:
                    shutil.rmtree(carpeta, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


# ── Entrada de archivos ──────────────────────────────────────────────────


def extension_permitida(nombre: str) -> bool:
    return Path(nombre or "").suffix.lower() in EXT_PERMITIDAS


def extraer_zip_seguro(ruta_zip: Path, destino: Path) -> int:
    """Descomprime dentro de `destino` y nunca fuera.

    Un ZIP puede traer rutas como `../../etc/passwd` (zip-slip). Se resuelve
    cada destino y se descarta lo que se salga de la carpeta del trabajo.
    """
    n = 0
    destino_abs = destino.resolve()
    with zipfile.ZipFile(ruta_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            salida = (destino / info.filename).resolve()
            if not str(salida).startswith(str(destino_abs)):
                logger.warning(
                    f"[VALIDADOR-ADRES] entrada de ZIP fuera de la carpeta: {info.filename}"
                )
                continue
            salida.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as origen, open(salida, "wb") as fh:
                fh.write(origen.read())
            n += 1
    return n


# ── Validación ───────────────────────────────────────────────────────────


def correr_validacion(
    trabajo_id: str,
    raiz: Path,
    sin_pdf: bool = False,
    resumen_factura: Callable[[Any], dict] | None = None,
) -> None:
    """Valida todo lo que haya bajo `raiz` y deja el resultado en el trabajo.

    Pensada para correr en segundo plano: cualquier fallo queda dentro del
    trabajo como estado ERROR, nunca se propaga — si revienta la validación
    de un paquete, el servidor tiene que seguir atendiendo a los demás.
    """
    vf = _motor()
    with _lock:
        tr = _trabajos.get(trabajo_id)
    if tr is None:
        return

    def _actualizar(**campos):
        with _lock:
            _trabajos[trabajo_id].update(**campos)

    try:
        rutas_f1, rutas_f2 = vf.descubrir_archivos_furips(raiz)
        if not rutas_f1 and not rutas_f2:
            _actualizar(
                estado="ERROR",
                mensaje=(
                    "No se encontró ningún archivo FURIPS1*.txt / FURIPS2*.txt en lo "
                    "subido. Suba los TXT o inclúyalos dentro del ZIP."
                ),
            )
            return

        registros_f1, obs1 = vf.leer_furips1(rutas_f1)
        lineas_f2, obs2 = vf.leer_furips2(rutas_f2)
        soportes = vf.descubrir_soportes(raiz)
        claves = sorted(set(registros_f1) | set(soportes) | set(lineas_f2))

        _actualizar(
            estado="VALIDANDO", total=len(claves), progreso=0, mensaje="Validando facturas…"
        )

        resultados = []
        for i, clave in enumerate(claves, 1):
            regs = registros_f1.get(clave, [])
            res = vf.ResultadoFactura(factura=clave)
            res.archivos = sorted(soportes.get(clave, []))
            res.carpeta = res.archivos[0].parent if res.archivos else None
            res.lineas_f2 = lineas_f2.get(clave, [])
            if len(regs) > 1:
                res.agregar(
                    "ESTRUCTURA",
                    vf.ADVERTENCIA,
                    "-",
                    "Registros duplicados",
                    f"{len(regs)} registros",
                    "Circular 022/2023",
                    f"La factura aparece {len(regs)} veces en el FURIPS 1; "
                    f"se valida el primer registro.",
                )
            res.registro_f1 = regs[0] if regs else None
            vf.validar_malla_f1(res)
            vf.validar_furips2(res)
            vf.analizar_carpeta(res, sin_pdf=sin_pdf)
            vf.cruzar_soportes(res)
            resultados.append(res)
            _actualizar(progreso=i, mensaje=f"Validando {clave} ({i}/{len(claves)})…")

        _actualizar(
            resultados=resultados,
            obs=obs1 + obs2,
            resumen=[resumen_factura(r) for r in resultados] if resumen_factura else [],
            estado="LISTO",
            mensaje="Validación completada.",
        )
    except Exception as e:  # el trabajo reporta el error; el servidor sigue vivo
        logger.exception(f"[VALIDADOR-ADRES] trabajo {trabajo_id} falló")
        _actualizar(estado="ERROR", mensaje=f"Error inesperado durante la validación: {e}")


def generar_informe(trabajo_id: str) -> Path | None:
    """Escribe el Excel del trabajo y devuelve su ruta. None si no está listo."""
    tr = estado(trabajo_id)
    if not tr or tr["estado"] != "LISTO" or not tr.get("resultados"):
        return None
    salida = ruta_informe(trabajo_id)
    if not salida.exists():
        _motor().generar_excel(tr["resultados"], tr.get("obs") or [], salida)
    return salida if salida.exists() else None
