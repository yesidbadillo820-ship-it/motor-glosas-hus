"""Liquidador de cirugías por grupo quirúrgico — Manual SOAT 2026.

18-08-2026. El liquidador de tarifas daba el valor de un examen o una
consulta, pero no el de una cirugía. Y una cirugía no tiene "un" valor: el
Manual Tarifario la cobra por **grupo quirúrgico** (02 al 13, y especiales
20 al 23), sumando cinco cosas distintas, cada una con su propio código y su
propia tarifa:

    derechos de sala + honorarios del cirujano + ayudantía quirúrgica
    + servicios del anestesiólogo + materiales, medicamentos y gases

Eso es lo que hace la página "liquidación de cirugías SOAT" de
miscuentasmedicas. La diferencia es que aquí sale del catálogo oficial ya
cargado (Circular Externa 047 de 2025), y el grupo de cada CUPS lo sabe la
tabla de homologación — no hay que buscarlo a mano.

Se comprobó contra los valores REALES pactados con FAMISANAR (base del PC de
cartera): cesárea (grupo 08) da $2.072.200 exacto; apendicectomía (grupo 07)
da $1.885.200 contra $1.885.300 del contrato — cien pesos de diferencia por
el orden del redondeo. El "UVB POR GRUPOS" del contrato ES este paquete con
el −5% aplicado.

Lo que este liquidador NO inventa:
  • Grupos especiales 20 al 23: la Circular no publica un código de
    materiales para ellos. Esa línea sale marcada "no tarifado en la
    Circular", nunca con un valor supuesto.
  • Grupos 02 al 05: el Manual no reconoce ayudantía quirúrgica (empieza en
    el grupo 06). Esa línea no aparece.
  • Los procedimientos con TARIFA PROPIA del HUS (p. ej. la colecistectomía)
    no se liquidan por grupo: el contrato manda pagarlos a la tarifa
    institucional, que es otra cosa y vive en las tarifas contratadas.
"""

from __future__ import annotations

from app.services.cups_soat_service import _crudos, descripcion_cups
from app.services.tarifas_oficiales import tarifas_soat_2026_completas
from app.services.uvb import calcular_soat_con_factor, valor_uvb_vigente

# Grupos quirúrgicos tal como los guarda la tabla de homologación: 2 al 13 y
# los especiales 20 al 23 (sin ceros a la izquierda, sin la "e").
_GRUPOS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "20", "21", "22", "23"]

# Las cinco series de la Circular 047/2025, verificadas código por código
# contra el texto oficial. Cada serie va en orden de grupo.
_CIRUJANO = {g: str(39000 + i) for i, g in enumerate(_GRUPOS)}  # 39000–39015
_ANESTESIOLOGO = {g: str(39100 + i) for i, g in enumerate(_GRUPOS)}  # 39100–39115
_SALA = {g: str(39204 + i) for i, g in enumerate(_GRUPOS)}  # 39204–39219
# La ayudantía quirúrgica solo existe desde el grupo 06 (39117).
_AYUDANTIA = {g: str(39117 + j) for j, g in enumerate(_GRUPOS[4:])}  # 39117–39128
# Materiales, medicamentos, oxígeno y gases: la Circular los agrupa por rangos
# y NO publica código para los grupos especiales 20 al 23.
_MATERIALES = {
    "2": "39301",
    "3": "39301",  # grupos 02-03
    "4": "39302",
    "5": "39302",
    "6": "39302",  # grupos 04-05-06
    "7": "39303",
    "8": "39303",
    "9": "39303",  # grupos 07-08-09
    "10": "39304",
    "11": "39304",
    "12": "39304",
    "13": "39304",  # grupos 10-11-12-13
}

# Orden en que se muestran las líneas del paquete.
_COMPONENTES = (
    ("Derechos de sala de cirugía", _SALA),
    ("Honorarios del cirujano/ginecoobstetra", _CIRUJANO),
    ("Ayudantía quirúrgica", _AYUDANTIA),
    ("Servicios del anestesiólogo", _ANESTESIOLOGO),
    ("Materiales, medicamentos, oxígeno y gases", _MATERIALES),
)


def _grupo_de_cirugia(cups: str | None) -> str | None:
    """Devuelve el grupo quirúrgico ('2'..'13','20'..'23') de un CUPS, o None
    si ese CUPS no es una cirugía tarifada por grupo."""
    for m in _crudos(cups):
        if str(m.get("clase") or "").strip().upper() == "GRUPO":
            grupo = str(m.get("uvb") or "").strip()
            if grupo in _CIRUJANO:
                return grupo
    return None


def es_cirugia_por_grupo(cups: str | None) -> bool:
    """True si el CUPS se liquida por grupo quirúrgico (tiene desglose)."""
    return _grupo_de_cirugia(cups) is not None


def liquidar_cirugia(cups: str | None, pct: float = 0.0, anio: int = 2026) -> dict | None:
    """Desglosa el valor de una cirugía por sus cinco componentes SOAT.

    `pct` es el ajuste contractual sobre la UVB (FAMISANAR −5%, Policía −8%…).
    Devuelve None si el CUPS no es una cirugía por grupo.

    Cada componente trae su código SOAT, su tarifa en UVB y su valor en pesos
    ya con el ajuste. Los componentes que el Manual no reconoce para ese grupo
    salen con `disponible=False` y valor None — nunca con una cifra supuesta.
    """
    grupo = _grupo_de_cirugia(cups)
    if grupo is None:
        return None

    catalogo = tarifas_soat_2026_completas()
    lineas: list[dict] = []
    total_uvb = 0.0
    faltan: list[str] = []

    for nombre, tabla in _COMPONENTES:
        codigo = tabla.get(grupo)
        fila = catalogo.get(codigo) if codigo else None
        if fila is None:
            lineas.append(
                {
                    "concepto": nombre,
                    "codigo_soat": codigo,
                    "uvb": None,
                    "valor_pesos": None,
                    "disponible": False,
                }
            )
            faltan.append(nombre)
            continue
        uvb = float(fila[0])
        total_uvb += uvb
        lineas.append(
            {
                "concepto": nombre,
                "codigo_soat": codigo,
                "uvb": uvb,
                "valor_pesos": calcular_soat_con_factor(uvb, pct, anio),
                "disponible": True,
            }
        )

    total_pesos = calcular_soat_con_factor(total_uvb, pct, anio)
    es_especial = grupo in ("20", "21", "22", "23")

    nota = (
        "El valor total es la suma de los cinco componentes del grupo "
        f"quirúrgico {grupo} del Manual Tarifario SOAT 2026 (Circular 047/2025). "
    )
    if es_especial:
        nota += (
            "Para los grupos especiales (20 al 23) el Manual no publica código "
            "de materiales: esa línea queda por fuera y debe soportarse aparte. "
        )
    if pct:
        signo = "más" if pct > 0 else "menos"
        nota += f"Se aplicó el ajuste contractual de {signo} {abs(pct)}% sobre la UVB."

    return {
        "cups": str(cups).strip(),
        "descripcion_cups": descripcion_cups(cups),
        "grupo": grupo,
        "grupo_especial": es_especial,
        "porcentaje_aplicado": pct,
        "anio": anio,
        "uvb_vigente": valor_uvb_vigente(anio),
        "lineas": lineas,
        "total_uvb": round(total_uvb, 2),
        "total_pesos": total_pesos,
        "componentes_faltantes": faltan,
        "nota": nota,
    }
