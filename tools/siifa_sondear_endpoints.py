#!/usr/bin/env python3
"""siifa_sondear_endpoints.py — Averigua POR DÓNDE se responde una devolución
en SIIFA, sin escribir nada en la plataforma.

EL PROBLEMA QUE RESUELVE
El bot manda TODO —glosas y devoluciones— por la misma puerta:
PUT /api/SeguimientoFacturaGlosa/Respuesta. Con las devoluciones que el
hospital aceptó (código RE9701), SIIFA contesta:

    «El código de tipo de respuesta especificado no existe, no está activo o
     no pertenece al grupo RESPUESTA»

El código sí existe —el portal lo ofrece en el desplegable de «Responder
Devolución»—, así que lo que falla es la puerta: se está validando contra los
códigos de GLOSA. Este script prueba las rutas y los grupos de catálogo
candidatos y dice cuáles existen, para dar con la correcta.

NO ESCRIBE NADA: solo toca las rutas con GET. Una ruta que existe contesta
405 (método equivocado) o 400; una que no existe contesta 404.

USO:
    py siifa_sondear_endpoints.py
    py siifa_sondear_endpoints.py --guardar "D:\\...\\SIIFA\\sondeo.txt"

INSTALACIÓN (una vez):
    py -m pip install httpx
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from siifa_client import SiifaApiError, SiifaClient, credenciales_desde_env  # noqa: E402

logger = logging.getLogger("siifa_sondeo")

# Rutas donde podría vivir la respuesta a una devolución. La primera es la que
# usa hoy el bot y sirve de control: se sabe que existe.
RUTAS = [
    "/api/SeguimientoFacturaGlosa/Respuesta",
    "/api/SeguimientoFacturaDevolucion/Respuesta",
    "/api/SeguimientoFacturaDevolucion/List",
    "/api/SeguimientoDevolucion/Respuesta",
    "/api/SeguimientoFactura/Devolucion/Respuesta",
    "/api/SeguimientoFacturaDevolucion",
    "/api/SeguimientoFacturaGlosa/DevolucionRespuesta",
    # Subsanación (etapa 4): la de glosa está confirmada; la de devolución no
    # se conoce. Es el mismo problema que en agosto con las respuestas, y se
    # resuelve igual: preguntando, no adivinando.
    "/api/SeguimientoFacturaGlosa/ReiteracionRespuesta",
    "/api/SeguimientoFacturaGlosa/Reiteracion",
    "/api/SeguimientoFacturaDevolucion/ReiteracionRespuesta",
    "/api/SeguimientoFacturaDevolucion/Reiteracion",
    "/api/SeguimientoFacturaDevolucion/SubsanacionRespuesta",
    "/api/SeguimientoFacturaGlosa/SubsanacionRespuesta",
]

# Nombres de grupo del catálogo de códigos. El portal muestra la frase pero no
# el código, y con «RESPUESTA» a secas el catálogo vino vacío.
GRUPOS = [
    # Nombres que la propia API menciona en sus errores de validación.
    "RESPUESTA_DEV_PTS_PSS",
    "RESPUESTA_GLOSA_PTS_PSS",
    "RESPUESTA",
    "RESPUESTA_GLOSA",
    "RESPUESTAGLOSA",
    "RESPUESTA_DEVOLUCION",
    "RESPUESTADEVOLUCION",
    "DEVOLUCION",
    "RESPUESTA_DEVOLUCIONES",
    "GLOSA",
    # Códigos de la SUBSANACIÓN (lo que el hospital contesta cuando la EPS
    # reitera). El patrón que funcionó fue «..._PTS_PSS», así que se prueban
    # las variantes de ese mismo molde.
    "REITERACION_RESPUESTA_GLOSA_PTS_PSS",
    "RESPUESTA_REITERACION_GLOSA_PTS_PSS",
    "REITERACION_GLOSA_PTS_PSS",
    "REITERACION_RESPUESTA_DEV_PTS_PSS",
    "REITERACION_DEV_PTS_PSS",
    "REITERACION_RESPUESTA",
    "REITERACION",
    "SUBSANACION",
]


def es_falso_positivo(ruta: str, detalle: str) -> bool:
    """¿El 400 vino de otra ruta que se tragó el último trozo como si fuera un id?

    SIIFA tiene rutas del tipo `/api/SeguimientoFacturaGlosa/{id}`. Al sondear
    `/api/SeguimientoFacturaGlosa/LoQueSea`, ESA ruta responde y se queja de
    que «LoQueSea» no es un número válido para IdSeguimientoFacturaGlosa. El
    400 hace creer que la ruta inventada existe, y no existe.

    Pasó de verdad el 13-08-2026: el sondeo dio por buenas seis rutas
    inventadas, tres de ellas para subsanar devoluciones por $14 millones.
    Mandar una escritura ahí habría ido a parar a otro registro.
    """
    ultimo = ruta.rstrip("/").rsplit("/", 1)[-1]
    return f"El valor '{ultimo}' no es válido" in (detalle or "")


def leer_estado(codigo: int) -> str:
    """Qué significa cada código para lo que estamos buscando."""
    if codigo == 0:
        return "sin respuesta de red"
    if codigo == 404:
        return "NO existe"
    if codigo == 405:
        return "EXISTE (hay que llamarla con PUT/POST)"
    if codigo == 401:
        return "existe, pide permisos"
    if 400 <= codigo < 500:
        return "EXISTE (contestó con error de datos, que es lo esperado en un sondeo)"
    if codigo >= 500:
        return "existe, pero el servidor falló"
    return "responde bien"


def sondear(cliente: SiifaClient) -> list[str]:
    lineas = ["RUTAS", "-" * 70]
    for ruta in RUTAS:
        codigo, detalle = cliente.sondear(ruta)
        if es_falso_positivo(ruta, detalle):
            estado = "NO CONCLUYENTE (la tomó como id de otra ruta) - NO ESCRIBIR"
        else:
            estado = leer_estado(codigo)
        lineas.append(f"  {codigo:>3}  {estado:<52} {ruta}")
        if detalle and codigo not in (404, 405):
            lineas.append(f"       {detalle[:120]}")

    lineas += ["", "GRUPOS DEL CATÁLOGO DE CÓDIGOS", "-" * 70]
    for grupo in GRUPOS:
        try:
            codigos = cliente.catalogo_tipo_codigo(grupo)
        except SiifaApiError as exc:
            lineas.append(f"  {grupo:<24} no responde ({exc})")
            continue
        if not codigos:
            lineas.append(f"  {grupo:<24} vacío")
            continue
        lineas.append(f"  {grupo:<24} {len(codigos)} códigos:")
        for c in codigos:
            cod = c.get("idSeguimientoTipoCodigo") or c.get("codigo") or "?"
            desc = c.get("descripcion") or c.get("nombre") or ""
            lineas.append(f"      {cod:<12} {desc}")
    return lineas


def ver_seguimiento_crudo(cliente: SiifaClient, factura: str) -> list[str]:
    """Muestra los campos TAL CUAL los devuelve la API para una factura.

    Es la única forma de saber con qué nombre viene el id de una devolución
    —hay que responderla con ESE id, no con el de la glosa— sin adivinarlo.
    """
    lineas = [f"CAMPOS CRUDOS DE LA FACTURA {factura}", "-" * 70]
    vistos = 0
    for crudo in cliente.listar_seguimientos(numero_factura=factura):
        tipo = str(crudo.get("tipoSeguimiento") or crudo.get("TipoSeguimiento") or "?")
        lineas.append(f"\n  Seguimiento tipo {tipo}:")
        for clave, valor in sorted(crudo.items()):
            if isinstance(valor, (dict, list)):
                valor = f"({type(valor).__name__})"
            texto = str(valor)
            lineas.append(f"    {clave:<48} {texto[:60]}")
        vistos += 1
        if vistos >= 2:  # con uno de cada tipo alcanza
            break
    if not vistos:
        lineas.append("  (esa factura no devolvió seguimientos)")
    return lineas


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--guardar", help="Archivo de texto donde dejar el resultado, para mandarlo.")
    ap.add_argument(
        "--factura",
        help="Muestra además los campos crudos de esa factura (para ver con qué nombre "
        "viene el id de una devolución). Ej: HUS494196",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    usuario, password = credenciales_desde_env()
    with SiifaClient() as cliente:
        try:
            cliente.login(usuario, password)
        except SiifaApiError as exc:
            raise SystemExit(f"\nNo se pudo entrar a SIIFA: {exc}\n")
        lineas = sondear(cliente)
        if args.factura:
            lineas += ["", ""] + ver_seguimiento_crudo(cliente, args.factura)

    texto = (
        "\nSONDEO DE SIIFA — no se escribió nada en la plataforma\n"
        + "=" * 70
        + "\n"
        + "\n".join(lineas)
        + "\n"
    )
    print(texto)
    if args.guardar:
        ruta = Path(args.guardar)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
        print(f"Guardado en: {ruta}\n")


if __name__ == "__main__":
    main()
