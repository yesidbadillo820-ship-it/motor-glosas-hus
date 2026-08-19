#!/usr/bin/env python3
"""siifa_perfiles.py — Quién es quién cuando se trabajan varias IPS en SIIFA.

El auditor administra la facturación de CUATRO prestadores distintos, cada uno
con su propio usuario en el portal del Ministerio. Este archivo dice, para
cada uno: cómo se llama, cuál es su NIT, en qué carpeta trabaja y en qué
variables de entorno están sus credenciales.

ACÁ NO HAY NI UN USUARIO NI UNA CONTRASEÑA, y no puede haberlos: este archivo
va al repositorio. Lo único que guarda son los NOMBRES de las variables de
entorno donde el auditor tiene sus claves en su propio equipo.

EL PELIGRO QUE ESTO RESUELVE. Con cuatro ventanas de PowerShell abiertas, es
cuestión de tiempo cargar en una IPS las respuestas preparadas para otra. Por
eso, además de separar carpetas, existe `verificar_identidad()`: antes de
escribir nada, se le pregunta al token de SIIFA a qué NIT pertenece y se
compara con el de la IPS elegida. Si no coinciden, el trabajo se detiene.

CÓMO SE AGREGA UNA IPS NUEVA: se añade una entrada a IPS acá abajo, y en el
equipo del auditor se definen sus dos variables de entorno:

    setx SIIFA_USER_<CLAVE> "usuario"
    setx SIIFA_PASSWORD_<CLAVE> "contraseña"
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Carpeta de trabajo. Cada IPS tiene la suya adentro, para que el informe de
# una nunca pise el de otra: todos los archivos se llaman igual.
CARPETA_BASE = Path(r"D:\USUARIO CARTERA\Documents\SIIFA")


@dataclass(frozen=True)
class Ips:
    clave: str
    # `nombre` es el legible, para la pantalla y los informes. `nombre_legal`
    # es el que va DENTRO de la respuesta a la EPS, y va en mayúsculas porque
    # así se escriben esos textos en el trámite.
    nombre: str
    nombre_legal: str
    nit: str
    # Para el cierre de las respuestas. Va vacío mientras el auditor no dé el
    # correo y la dirección de esa IPS: es preferible una respuesta sin datos
    # de contacto que una con los de OTRA entidad.
    contacto: str = ""

    @property
    def var_usuario(self) -> str:
        return f"SIIFA_USER_{self.clave}"

    @property
    def var_password(self) -> str:
        return f"SIIFA_PASSWORD_{self.clave}"

    @property
    def carpeta(self) -> Path:
        return CARPETA_BASE / self.clave


IPS: dict[str, Ips] = {
    "HUS": Ips(
        "HUS",
        "E.S.E. Hospital Universitario de Santander",
        "ESE HOSPITAL UNIVERSITARIO DE SANTANDER",
        "900006037",
        "CORREO ELECTRÓNICO INSTITUCIONAL CARTERA@HUS.GOV.CO, VENTANILLA ÚNICA DE LA "
        "ESE HUS, CARRERA 30 NO. 31-10, BUCARAMANGA, SANTANDER",
    ),
    # `nombre_legal` es la razón social EXACTA con la que cada una está
    # registrada en SIIFA, tomada de la columna razon_social_emisor de su
    # propio informe (13-08-2026). No se inventa: es la que la EPS ve.
    # Ojo con Socorro: el auditor la llama «Clínica Socorro», pero ante el
    # Ministerio es el Hospital Regional Manuela Beltrán.
    #
    # Falta el correo y la dirección de estas tres: hasta tenerlos, sus
    # respuestas salen sin la frase de contacto (ver `contacto` arriba).
    "SOCORRO": Ips(
        "SOCORRO",
        "Clínica Socorro (Hospital Regional Manuela Beltrán)",
        "E.S.E. HOSPITAL REGIONAL MANUELA BELTRAN",
        "900190045",
    ),
    "GIRON": Ips("GIRON", "Clínica Girón", "CLINICA GIRON E.S.E", "890203242"),
    "GUANE": Ips(
        "GUANE",
        "Clínica Guane",
        "ESE CLINICA GUANE Y SU RED INTEGRAL DE SALUD",
        "804006936",
    ),
}


def listar() -> str:
    return ", ".join(sorted(IPS))


def buscar(clave: str) -> Ips:
    """La IPS que corresponde a ese nombre corto."""
    ips = IPS.get(str(clave or "").strip().upper())
    if ips is None:
        raise SystemExit(
            f"\nNo conozco la IPS '{clave}'.\n\nLas que están configuradas son: {listar()}\n"
            "Para agregar otra, se añade en tools/siifa_perfiles.py.\n"
        )
    return ips


def por_nit(nit: str) -> Ips | None:
    """Para poder decir en el error CUÁL es la entidad del token equivocado."""
    limpio = solo_digitos(nit)
    return next((i for i in IPS.values() if solo_digitos(i.nit) == limpio), None)


def solo_digitos(nit: object) -> str:
    """El NIT sin puntos, guiones ni dígito de verificación.

    SIIFA lo devuelve de varias formas —`900006037`, `900006037-4`,
    `900.006.037`— y compararlas como texto daría «no coincide» sobre la misma
    entidad, que es peor que no comparar: haría desconfiar de la guarda.
    """
    digitos = "".join(c for c in str(nit or "") if c.isdigit())
    # El dígito de verificación va después del guion; si vino pegado, sobra.
    return digitos[:9] if len(digitos) == 10 else digitos


def credenciales(ips: Ips) -> tuple[str, str]:
    """Usuario y clave de esa IPS, desde las variables de entorno."""
    usuario = os.environ.get(ips.var_usuario)
    password = os.environ.get(ips.var_password)
    if not usuario or not password:
        raise SystemExit(
            f"\nFaltan las credenciales de {ips.nombre} ({ips.clave}).\n\n"
            "Definilas una sola vez en PowerShell, y después cerrá y volvé a\n"
            "abrir la ventana para que las tome:\n\n"
            f'    setx {ips.var_usuario} "usuario_de_esa_ips"\n'
            f'    setx {ips.var_password} "contraseña_de_esa_ips"\n\n'
            "Nunca se escriben dentro del código ni se suben al repositorio.\n"
        )
    return usuario, password


class IdentidadEquivocada(SystemExit):
    """El token no es de la IPS con la que se dijo estar trabajando."""


def verificar_identidad(ips: Ips, nit_del_token: str | None) -> None:
    """Frena todo si el token no es de la IPS elegida.

    ESTA ES LA GUARDA QUE IMPORTA. El auditor trabaja cuatro IPS a la vez, en
    cuatro ventanas; equivocarse de ventana es cuestión de tiempo. Sin esto,
    el error se descubre después de haber escrito en la plataforma —y una
    respuesta cargada en la entidad equivocada no se puede deshacer—.

    Si el token no dice a qué entidad pertenece, NO se bloquea: se avisa. Un
    bloqueo por un campo que la API dejó de mandar dejaría al auditor sin
    herramienta y sin saber por qué.
    """
    if not solo_digitos(nit_del_token):
        print(
            f"\n  [!] AVISO: el token de SIIFA no dice a qué entidad pertenece, así que no\n"
            f"      se pudo confirmar que estas credenciales sean las de {ips.nombre}.\n"
            f"      Revisá que la ventana sea la correcta antes de cargar nada.\n"
        )
        return

    if solo_digitos(nit_del_token) == solo_digitos(ips.nit):
        return

    otra = por_nit(nit_del_token)
    quien = f"{otra.nombre} ({otra.clave})" if otra else f"NIT {nit_del_token}"
    raise IdentidadEquivocada(
        f"\n{'=' * 70}\n"
        f"  ALTO: LAS CREDENCIALES NO SON DE LA IPS QUE PEDISTE\n"
        f"{'=' * 70}\n\n"
        f"  Pediste trabajar con : {ips.nombre} (NIT {ips.nit})\n"
        f"  Pero SIIFA respondió : {quien}\n\n"
        f"  No se hizo nada. Si se hubiera seguido, el trabajo de una entidad\n"
        f"  habría quedado cargado en la otra.\n\n"
        f"  Qué revisar:\n"
        f"    1. Que {ips.var_usuario} tenga el usuario de {ips.nombre}.\n"
        f"    2. Que esta ventana de PowerShell sea la de esa IPS (si cambiaste\n"
        f"       las variables con setx, hay que abrir una ventana nueva).\n"
    )


def verificar_informe(ips: Ips, filas: list[dict], de_donde: str = "el informe") -> None:
    """Frena si el archivo no es de la IPS con la que se está trabajando.

    LA OTRA MITAD DE LA GUARDA. Comprobar el token protege lo que se ESCRIBE;
    esto protege lo que se LEE. Con cuatro carpetas de nombres parecidos y
    archivos que se llaman igual en todas, pasarle a la herramienta el informe
    de otra IPS es fácil — y lo que sale de ahí son las respuestas que después
    se cargan. Comparar el informe de una contra el de otra, además, reportaría
    todos sus registros como «novedades».

    El informe trae el NIT del emisor de cada factura, que es la IPS. Si no
    trae la columna (informes viejos), se sigue sin bloquear.
    """
    nits = {solo_digitos(f.get("nit_emisor")) for f in filas if f.get("nit_emisor")}
    nits.discard("")
    if not nits:
        return
    ajenos = nits - {solo_digitos(ips.nit)}
    if not ajenos:
        return

    de_quien = [f"{o.nombre} (NIT {o.nit})" if (o := por_nit(n)) else f"NIT {n}" for n in ajenos]
    raise IdentidadEquivocada(
        f"\n{'=' * 70}\n"
        f"  ALTO: {de_donde.upper()} NO ES DE LA IPS QUE PEDISTE\n"
        f"{'=' * 70}\n\n"
        f"  Estás trabajando con : {ips.nombre} (NIT {ips.nit})\n"
        f"  Pero el archivo es de: {', '.join(de_quien)}\n\n"
        f"  No se hizo nada. Revisá que la ruta sea la de la carpeta de\n"
        f"  {ips.clave}: los archivos se llaman igual en las cuatro.\n"
    )


def carpeta_de(ips: Ips, ruta_pedida: str | None) -> Path:
    """La carpeta donde trabaja esa IPS. Lo que pida el auditor manda."""
    return Path(ruta_pedida) if ruta_pedida else ips.carpeta


def agregar_argumento(ap) -> None:
    """La opción --ips, igual en todas las herramientas."""
    ap.add_argument(
        "--ips",
        default=os.environ.get("SIIFA_IPS", "HUS"),
        help=f"Con qué IPS se trabaja: {listar()} (default: HUS, o lo que diga SIIFA_IPS).",
    )


def anunciar(ips: Ips) -> None:
    """Deja dicho en pantalla con quién se está trabajando.

    Cuatro ventanas iguales son cuatro oportunidades de equivocarse; esta
    línea es lo primero que se ve en cada una.
    """
    print(f"\n  IPS: {ips.nombre} — NIT {ips.nit}\n")
