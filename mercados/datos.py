"""Leer el histórico de precios que usted exporta del bróker.

Cada plataforma exporta el CSV a su manera: unas encabezan «Date», otras
«Fecha»; unas separan los decimales con punto y otras con coma; unas ordenan
de más viejo a más nuevo y otras al revés. Aquí se acepta todo eso, y lo que
no se entienda se dice con nombre propio en vez de fallar en silencio.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from .dominio import Vela

#: Cómo se llama cada columna en las plataformas que el auditor usa.
#: Todo en minúsculas y sin acentos: la comparación se hace normalizada.
NOMBRES = {
    "fecha": ("fecha", "date", "time", "datetime", "dia", "day", "timestamp"),
    "apertura": ("apertura", "open", "abertura", "primero"),
    "maximo": ("maximo", "high", "alto", "max", "mayor"),
    "minimo": ("minimo", "low", "bajo", "min", "menor"),
    "cierre": ("cierre", "close", "ultimo", "last", "adj close", "precio", "price"),
    "volumen": ("volumen", "volume", "vol"),
}

#: Formatos de fecha, en orden de preferencia. El ISO primero porque no es
#: ambiguo; dd/mm antes que mm/dd porque el bróker es colombiano.
FORMATOS_FECHA = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%b %d, %Y",
    "%d %b %Y",
)


class ArchivoIlegible(Exception):
    """El CSV no se pudo entender, y el mensaje dice exactamente por qué."""


def _normalizar(texto: str) -> str:
    tabla = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
    return texto.strip().lower().translate(tabla).replace('"', "").replace("﻿", "")


def _columna(cabecera: list[str], campo: str) -> int | None:
    limpias = [_normalizar(c) for c in cabecera]
    for alias in NOMBRES[campo]:
        if alias in limpias:
            return limpias.index(alias)
    # Segunda pasada: algunos exportan «Close/Last» o «Precio de cierre».
    for alias in NOMBRES[campo]:
        for i, c in enumerate(limpias):
            if alias in c:
                return i
    return None


def leer_numero(bruto: str) -> float:
    """Convierte «1.234,56», «1,234.56» y «1234.56» al mismo número.

    Sin esto, un histórico exportado en formato colombiano entra con los
    precios multiplicados por mil y todos los patrones salen mal.
    """
    t = bruto.strip().replace('"', "").replace(" ", "").replace("%", "")
    if not t or t in {"-", "N/A", "n/a", "null"}:
        raise ValueError("celda vacía")
    t = t.replace(" ", "")
    if "," in t and "." in t:
        # El separador decimal es el que aparece más a la derecha.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        entero, _, decimales = t.rpartition(",")
        # «1,234» son mil doscientos treinta y cuatro si hay 3 cifras detrás
        # y el número no lleva más comas; con 1 o 2, es decimal.
        t = (
            (entero + decimales)
            if len(decimales) == 3 and entero.count(",") == 0 and entero
            else (entero + "." + decimales)
        )
        t = t.replace(",", "")
    return float(t)


def leer_fecha(bruto: str) -> date:
    t = bruto.strip().replace('"', "")
    if " " in t and len(t) > 10:
        t = t.split(" ")[0]
    if "T" in t:
        t = t.split("T")[0]
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(t, formato).date()
        except ValueError:
            continue
    raise ValueError(f"no reconozco la fecha «{bruto}»")


def leer_csv(ruta: str | Path) -> list[Vela]:
    """El histórico de un CSV, siempre de la sesión más vieja a la más nueva."""
    texto = Path(ruta).read_text(encoding="utf-8-sig", errors="replace")
    return leer_texto(texto, origen=str(ruta))


def leer_texto(texto: str, origen: str = "el archivo") -> list[Vela]:
    filas = list(csv.reader(io.StringIO(texto), delimiter=_separador(texto)))
    filas = [f for f in filas if any(c.strip() for c in f)]
    if len(filas) < 2:
        raise ArchivoIlegible(f"{origen}: no tiene ni cabecera ni datos.")

    cabecera = filas[0]
    indices = {campo: _columna(cabecera, campo) for campo in NOMBRES}
    faltan = [c for c in ("fecha", "apertura", "maximo", "minimo", "cierre") if indices[c] is None]
    if faltan:
        raise ArchivoIlegible(
            f"{origen}: no encuentro la columna de {', '.join(faltan)}.\n"
            f"La cabecera dice: {', '.join(cabecera)}.\n"
            "Se aceptan nombres en español o en inglés (Fecha/Date, "
            "Apertura/Open, Máximo/High, Mínimo/Low, Cierre/Close)."
        )

    velas: list[Vela] = []
    problemas: list[str] = []
    for numero, fila in enumerate(filas[1:], start=2):
        try:
            vela = Vela(
                fecha=leer_fecha(fila[indices["fecha"]]),
                apertura=leer_numero(fila[indices["apertura"]]),
                maximo=leer_numero(fila[indices["maximo"]]),
                minimo=leer_numero(fila[indices["minimo"]]),
                cierre=leer_numero(fila[indices["cierre"]]),
                volumen=_volumen(fila, indices["volumen"]),
            )
        except (ValueError, IndexError) as error:
            problemas.append(f"  línea {numero}: {error}")
            continue
        velas.append(vela)

    if not velas:
        detalle = "\n".join(problemas[:5])
        raise ArchivoIlegible(f"{origen}: ninguna fila se pudo leer.\n{detalle}")

    velas.sort(key=lambda v: v.fecha)
    return velas


def _volumen(fila: list[str], indice: int | None) -> float | None:
    if indice is None or indice >= len(fila):
        return None
    try:
        return leer_numero(fila[indice])
    except ValueError:
        return None


def _separador(texto: str) -> str:
    """Coma, punto y coma o tabulador: Excel en español exporta con «;»."""
    primera = texto.splitlines()[0] if texto.splitlines() else ""
    for sep in (";", "\t"):
        if primera.count(sep) >= 3:
            return sep
    return ","


def decimales(precio: float) -> int:
    """Cuántos decimales tiene sentido mostrar para un precio de este tamaño.

    Dos decimales fijos servían para una acción de 4.200, pero borran toda la
    información de un par de divisas: EUR/USD a 1,1593 salía como «1,16» y el
    movimiento entero desaparecía de la pantalla. Pasó con el primer archivo
    real que se probó.
    """
    magnitud = abs(precio)
    if magnitud >= 100:
        return 2
    if magnitud >= 1:
        return 5
    return 6


def formato(precio: float) -> str:
    return f"{precio:,.{decimales(precio)}f}"


def resumen(velas: Iterable[Vela]) -> str:
    lista = list(velas)
    if not lista:
        return "Sin datos."
    return (
        f"{len(lista)} sesiones · del {lista[0].fecha} al {lista[-1].fecha} · "
        f"cierre {formato(lista[0].cierre)} → {formato(lista[-1].cierre)}"
    )
