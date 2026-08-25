"""Material de osteosíntesis: el precio institucional y la norma que lo respalda.

LA GLOSA QUE ESTO CONTESTA. La EPS objeta el valor del material de
osteosíntesis diciendo que «no está pactado» o que «excede tarifas». Hasta
ahora el auditor tenía que abrir el Anexo 09 en PDF —dieciocho páginas y
1.216 códigos— buscar la fila a ojo, y redactar la respuesta a mano.

Acá el código FMO devuelve su precio oficial y la cita de la resolución que
lo creó, lista para pegar en el dictamen.

LA NORMA. Resolución 194 del 15 de mayo de 2025 del Gerente de la E.S.E. HUS,
«Por medio de la cual se crean Códigos y Tarifas Institucionales para MATERIAL
DE OSTEOSINTESIS». Deroga el artículo noveno de la Resolución 171 del 30 de
abril de 2024 y deja sin efecto su anexo 9.

EL SUSTENTO JURÍDICO, que es lo que la EPS tiene que reconocer: el Decreto
2423 de 1996 en su artículo 87 habilita a la institución a fijar el precio
cuando presta un servicio no previsto en el manual tarifario, y el Decreto 887
de 2001 hace obligatorias esas tarifas en los eventos que regula. Por eso un
código FMO con precio en el Anexo 09 **sí está pactado**: lo pactó un acto
administrativo, no una cotización suelta.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATOS = Path(__file__).resolve().parent.parent / "data" / "maos_res194.json"

# ─── La resolución, para citarla ──────────────────────────────────────────

RESOLUCION = {
    "numero": "Resolución No. 194 de 2025",
    "fecha": "15 de mayo de 2025",
    "expide": "Gerencia de la E.S.E. Hospital Universitario de Santander",
    "objeto": (
        "Por medio de la cual se crean Códigos y Tarifas Institucionales para "
        "MATERIAL DE OSTEOSINTESIS, en la Empresa Social del Estado Hospital "
        "Universitario de Santander"
    ),
    "anexo": "ANEXO No. 9 — Material de osteosíntesis (parte integral de la resolución)",
    "deroga": (
        "El artículo noveno de la Resolución No. 171 del 30 de abril de 2024, "
        "dejando sin efecto su anexo 9"
    ),
    "vigencia": ("En firme desde el día siguiente a su publicación, comunicación o notificación"),
}

# Los considerandos que dan el sustento. Se citan tal cual: una EPS que
# objeta «tarifa no pactada» sobre material de osteosíntesis tiene que
# responder a estos dos decretos, no a una cotización del hospital.
SUSTENTO: tuple[dict[str, str], ...] = (
    {
        "norma": "Decreto 2423 de 1996, artículo 87",
        "texto": (
            "Por las circunstancias de orden tecnológico, cuando alguna Institución "
            "Prestadora de Servicios de Salud realice un procedimiento no previsto en "
            "el presente manual tarifario, podrá fijar el valor correspondiente."
        ),
        "para_que": (
            "Es la habilitación legal para que el HUS fije por acto administrativo el "
            "precio del material de osteosíntesis."
        ),
    },
    {
        "norma": "Decreto 887 de 2001, artículo 1",
        "texto": (
            "Las tarifas dispuestas por el Decreto 2423 de 1996 serán de obligatorio "
            "cumplimiento en los casos originados por accidentes de tránsito, "
            "desastres naturales, atentados terroristas y los demás eventos "
            "catastróficos."
        ),
        "para_que": "Hace obligatorias esas tarifas en los eventos que regula.",
    },
)

_RE_FMO = re.compile(r"\bFMO\s*-?\s*(\d{3,6})\b", re.I)


@lru_cache(maxsize=1)
def _catalogo() -> dict[str, dict[str, Any]]:
    """El Anexo 09, leído una sola vez.

    Si el archivo no está, se devuelve vacío en vez de reventar: un dictamen
    no puede caerse porque falte un catálogo de consulta.
    """
    try:
        return json.loads(_DATOS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalizar_codigo(codigo: str) -> str:
    """`fmo 482`, `FMO-00482`, `FMO00482` → `FMO00482`.

    La EPS y el ERP escriben el código de formas distintas, y un guion de más
    hacía que no se encontrara la tarifa que sí existe.
    """
    m = _RE_FMO.search(codigo or "")
    if not m:
        return (codigo or "").strip().upper()
    return "FMO" + m.group(1).zfill(5)


def buscar(codigo: str) -> dict[str, Any] | None:
    """El precio institucional de un código FMO, con su respaldo normativo."""
    cod = normalizar_codigo(codigo)
    ficha = _catalogo().get(cod)
    if ficha is None:
        return None
    return {
        "codigo": cod,
        "descripcion": ficha["descripcion"],
        "precio": ficha["precio"],
        "cantidad": ficha["cantidad"],
        "grupo": ficha["grupo"],
        "resolucion": RESOLUCION,
    }


def buscar_por_texto(texto: str, limite: int = 20) -> list[dict[str, Any]]:
    """Busca por descripción cuando el auditor no tiene el código a mano.

    Es lo normal: la glosa de la EPS dice «tornillo cortical 3.5», no
    «FMO00482».
    """
    palabras = [p for p in (texto or "").upper().split() if len(p) > 2]
    if not palabras:
        return []
    salida = []
    for cod, f in _catalogo().items():
        desc = f["descripcion"].upper()
        if all(p in desc for p in palabras):
            salida.append({"codigo": cod, **f})
    salida.sort(key=lambda x: x["precio"])
    return salida[:limite]


def codigos_en(texto: str) -> list[str]:
    """Todos los códigos FMO que aparecen en un texto de glosa."""
    vistos, salida = set(), []
    for m in _RE_FMO.finditer(texto or ""):
        cod = "FMO" + m.group(1).zfill(5)
        if cod not in vistos:
            vistos.add(cod)
            salida.append(cod)
    return salida


def defensa_para(codigo: str) -> str | None:
    """El párrafo listo para el dictamen, con el precio y la norma.

    Se escribe en el estilo de las respuestas del hospital: mayúsculas, un
    solo párrafo, citando el acto administrativo y su sustento legal.
    """
    ficha = buscar(codigo)
    if ficha is None:
        return None
    # El separador de miles va aparte: aplicar el reemplazo sobre todo el
    # párrafo convertía en punto cualquier coma del texto.
    pesos = f"{ficha['precio']:,.0f}".replace(",", ".")
    return (
        f"EL MATERIAL DE OSTEOSÍNTESIS OBJETADO CORRESPONDE AL CÓDIGO "
        f"INSTITUCIONAL {ficha['codigo']} — {ficha['descripcion']}, CUYO PRECIO "
        f"DE VENTA UNITARIO ES DE ${pesos}"
        + f", ESTABLECIDO EN EL ANEXO No. 9 DE LA {RESOLUCION['numero'].upper()} "
        f"DEL {RESOLUCION['fecha'].upper()}, EXPEDIDA POR LA GERENCIA DE LA E.S.E. "
        "HOSPITAL UNIVERSITARIO DE SANTANDER. DICHA TARIFA NO ES UNA COTIZACIÓN "
        "UNILATERAL SINO UN ACTO ADMINISTRATIVO EN FIRME, PROFERIDO CON FUNDAMENTO "
        "EN EL ARTÍCULO 87 DEL DECRETO 2423 DE 1996, QUE FACULTA A LA INSTITUCIÓN "
        "PRESTADORA PARA FIJAR EL VALOR DE LO NO PREVISTO EN EL MANUAL TARIFARIO, "
        "EN CONCORDANCIA CON EL ARTÍCULO 1 DEL DECRETO 887 DE 2001. POR LO "
        "ANTERIOR, EL VALOR FACTURADO SÍ SE ENCUENTRA DEBIDAMENTE SOPORTADO Y SE "
        "SOLICITA EL LEVANTAMIENTO TOTAL DE LA GLOSA."
    )


def resumen() -> dict[str, Any]:
    cat = _catalogo()
    grupos: dict[str, int] = {}
    for f in cat.values():
        grupos[f["grupo"] or "sin grupo"] = grupos.get(f["grupo"] or "sin grupo", 0) + 1
    return {
        "total_codigos": len(cat),
        "resolucion": RESOLUCION,
        "sustento": list(SUSTENTO),
        "grupos": [{"nombre": g, "codigos": n} for g, n in sorted(grupos.items())],
    }
