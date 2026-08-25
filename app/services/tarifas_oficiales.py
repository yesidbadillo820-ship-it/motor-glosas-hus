"""Catálogo oficial de tarifas ESE HUS (Res. 054/2026 + Res. 124/2026) y
ejemplos representativos del Manual SOAT 2026 (Circular 047/2025 UVB).

Sirve como **base de conocimiento local** para que la IA sepa con certeza
los valores en pesos cuando la EPS objeta una tarifa. Se consulta como
fallback cuando la tarifa_contratada cargada por el coordinador no
contiene el CUPS.

Datos extraídos directamente del texto oficial de la Resolución 124 de
marzo 25 de 2026 de la ESE Hospital Universitario de Santander.

Estructura de los dicts:
    { "codigo_ips": (factor_smdlv, valor_pesos, descripcion, norma) }

Donde:
  - codigo_ips: el código con sufijo H/H1/… que el HUS factura
  - factor_smdlv: FACTOR establecido en la resolución
  - valor_pesos: valor en pesos 2026 ya calculado por el HUS
  - norma: "RES_124_2026" | "RES_054_2026" | "CIRCULAR_047_2025"
"""

from __future__ import annotations

import gzip
import json
import os


# ─── TARIFAS PROPIAS HUS — Resolución 124 de marzo 25 de 2026 ───────────────
# Datos textuales extraídos directamente del documento oficial.

TARIFAS_PROPIAS_HUS: dict[str, tuple[float, int, str, str]] = {
    # ─── Laboratorio Clínico ────────────────────────────────────────────────
    "908859H2": (
        21.46,
        1_252_500,
        "Identificación simultánea de múltiples patógenos por pruebas moleculares (panel BCID2)",
        "RES_124_2026",
    ),
    "908859H3": (
        21.46,
        1_252_500,
        "Identificación simultánea de múltiples patógenos (panel respiratorio RP 2.1)",
        "RES_124_2026",
    ),
    "908859H4": (
        21.46,
        1_252_500,
        "Identificación simultánea de múltiples patógenos (panel gastrointestinal)",
        "RES_124_2026",
    ),
    "908859H5": (
        22.34,
        1_303_800,
        "Identificación simultánea de múltiples patógenos por pruebas moleculares",
        "RES_124_2026",
    ),
    "903101H": (1.38, 81_000, "Ácidos biliares totales en sangre", "RES_124_2026"),
    "906497H": (10.03, 585_900, "Anticuerpos anti-fosfolipasa A2", "RES_124_2026"),
    "906470H": (8.55, 499_500, "Aquaporina 4 IgG en suero por EIA", "RES_124_2026"),
    "906470H1": (8.82, 514_800, "Aquaporina 4 IgG en LCR", "RES_124_2026"),
    "906470H2": (8.55, 499_500, "Aquaporina 4 IgG en suero por técnica IFI", "RES_124_2026"),
    "908862H": (6.37, 371_800, "Citomegalovirus DNA detector (PCR)", "RES_124_2026"),
    "904720H": (3.54, 207_100, "Elastasa pancreática en materia fecal", "RES_124_2026"),
    "906811H": (
        4.57,
        267_300,
        "Electroforesis de proteínas en LCR (bandas oligoclonales)",
        "RES_124_2026",
    ),
    "902109H": (1.05, 61_300, "Glucosa 6 fosfato deshidrogenasa cuantitativa", "RES_124_2026"),
    "903021H": (0.70, 41_300, "Haptoglobina automatizada", "RES_124_2026"),
    "908872H": (6.69, 390_900, "Herpes simple I y II DNA detector por PCR", "RES_124_2026"),
    "904706H": (1.22, 71_700, "Péptido C en suero", "RES_124_2026"),
    "904706H1": (1.22, 71_700, "Péptido C en orina", "RES_124_2026"),
    "906303H": (2.41, 141_100, "Detección de antígeno LAM (lipoarabinomanano)", "RES_124_2026"),
    "903065H": (4.36, 255_000, "Pro péptido atrial natriurético [Pro-BNP]", "RES_124_2026"),
    "898807H": (
        35.29,
        2_060_000,
        "Estudio anatomopatológico de marcación inmunohistoquímica básica",
        "RES_124_2026",
    ),
    # Hematología
    "898803H": (
        46.55,
        2_717_000,
        "Citometría de flujo en biopsia (leucemias agudas)",
        "RES_124_2026",
    ),
    "898803H1": (
        40.23,
        2_348_000,
        "Citometría de flujo (leucemias linfocíticas agudas)",
        "RES_124_2026",
    ),
    "898803H2": (
        38.91,
        2_271_000,
        "Citometría de flujo (síndrome linfoproliferativo)",
        "RES_124_2026",
    ),
    "898803H3": (
        49.84,
        2_909_000,
        "Citometría de flujo (síndrome mieloproliferativo)",
        "RES_124_2026",
    ),
    "898803H4": (
        26.35,
        1_538_000,
        "Citometría de flujo (discrasias de células plasmáticas)",
        "RES_124_2026",
    ),
    "898803H5": (
        29.04,
        1_695_000,
        "Citometría de flujo (infiltración LCR por células neoplásicas)",
        "RES_124_2026",
    ),
    "898803H6": (
        34.72,
        2_026_700,
        "Citometría de flujo (enfermedad mínima residual)",
        "RES_124_2026",
    ),
    "898803H7": (
        7.77,
        454_000,
        "Citometría de flujo (hemoglobinuria paroxística nocturna)",
        "RES_124_2026",
    ),
    # ─── Consulta externa especializada ─────────────────────────────────────
    "890202H1": (1.86, 109_000, "Consulta primera vez por electrofisiología", "RES_124_2026"),
    "890302H1": (
        1.86,
        109_000,
        "Consulta control y seguimiento por electrofisiología",
        "RES_124_2026",
    ),
    "890253H": (
        4.36,
        254_500,
        "Consulta primera vez por hepatología — cirujano hepatobiliar",
        "RES_124_2026",
    ),
    "890405H": (0.65, 38_000, "Interconsulta por enfermería", "RES_124_2026"),
    "890405H1": (
        0.65,
        38_000,
        "Interconsulta enfermería — clínica de heridas y cuidado de la piel",
        "RES_124_2026",
    ),
    "890405H2": (
        0.65,
        38_000,
        "Interconsulta enfermería — programa terapia de infusión",
        "RES_124_2026",
    ),
    "890405H3": (
        0.65,
        38_000,
        "Interconsulta enfermería — programa recursos energía y terapia de la piel",
        "RES_124_2026",
    ),
    "890402H1": (1.86, 109_000, "Interconsulta hospitalaria por electrofisiología", "RES_124_2026"),
    "890410H": (1.03, 60_500, "Interconsulta por audiología", "RES_124_2026"),
    "890453": (3.38, 197_300, "Consulta por hepatología — cirujano hepatobiliar", "RES_124_2026"),
    # ─── Electrofisiología / Cardiología ────────────────────────────────────
    "954624H": (
        3.94,
        230_000,
        "Potenciales auditivos evocados miogénicos oculares",
        "RES_124_2026",
    ),
    "954625H": (
        3.94,
        230_000,
        "Potenciales auditivos evocados miogénicos cervicales",
        "RES_124_2026",
    ),
    "996101H": (14.32, 836_200, "Cardioversión eléctrica a tórax cerrado electiva", "RES_124_2026"),
    "378501H": (4.11, 240_000, "Revisión (reprogramación) de marcapasos", "RES_124_2026"),
    "378502H": (
        5.14,
        300_000,
        "Revisión (reprogramación) de resincronizador cardíaco",
        "RES_124_2026",
    ),
    "378503H": (
        4.96,
        290_000,
        "Revisión (reprogramación) de cardioversor (desfibrilador)",
        "RES_124_2026",
    ),
    "378504H": (4.96, 290_000, "Revisión cardioversor con resincronizador", "RES_124_2026"),
    "378401H": (
        95.87,
        5_595_794,
        "Inserción [implantación] de resincronizador cardíaco",
        "RES_124_2026",
    ),
    "378607H": (
        68.73,
        4_011_800,
        "Inserción de cardioversor (desfibrilador) vía subcutánea",
        "RES_124_2026",
    ),
    "378301H": (35.56, 2_075_800, "Inserción de marcapasos bicameral", "RES_124_2026"),
    "378201H": (32.55, 1_899_800, "Inserción de marcapasos unicameral", "RES_124_2026"),
    "378102H": (19.82, 1_157_300, "Inserción marcapaso temporal vía percutánea", "RES_124_2026"),
    "372301H": (
        44.56,
        2_601_000,
        "Estudio electrofisiológico + cateterismo derecho e izquierdo",
        "RES_124_2026",
    ),
    "373406H": (
        85.79,
        5_007_300,
        "Ablación de lesión o tejido cardíaco focal percutánea",
        "RES_124_2026",
    ),
    "373409H": (
        85.79,
        5_007_300,
        "Ablación de lesión o tejido cardíaco multifocal percutánea",
        "RES_124_2026",
    ),
    "373412H": (174.84, 10_204_800, "Aislamiento de venas pulmonares (FARAPULSE)", "RES_124_2026"),
    "372802H": (151.76, 8_857_300, "Mapeo electroanatómico tridimensional", "RES_124_2026"),
    "373414H": (184.74, 10_782_300, "Modulación de sustrato arrítmico epicárdica", "RES_124_2026"),
    "373413H": (165.55, 9_662_500, "Modulación de sustrato arrítmico endocárdica", "RES_124_2026"),
    "376401H": (
        28.07,
        1_638_500,
        "Retiro o eliminación de marcapasos/cardiodesfibriladores",
        "RES_124_2026",
    ),
    "895001H": (8.56, 500_000, "Monitoreo electrocardiográfico continuo (Holter)", "RES_124_2026"),
    "378001H": (21.99, 1_283_800, "Inserción [implantación] de monitor de eventos", "RES_124_2026"),
    # ─── Procedimientos guiados por ecografía ───────────────────────────────
    "881411H": (6.42, 375_000, "Ecografía dinámica de piso pélvico", "RES_124_2026"),
    "881412H": (6.42, 375_000, "Ecografía de mapeo pélvico", "RES_124_2026"),
    "881701H": (2.39, 140_000, "Ecografía como guía para procedimientos", "RES_124_2026"),
    "881702H": (
        2.91,
        170_000,
        "Ecografía como guía para procedimientos con marcación",
        "RES_124_2026",
    ),
    "881214H": (
        20.56,
        1_200_000,
        "Ecocardiograma transtorácico con análisis deformidad miocárdica",
        "RES_124_2026",
    ),
    # ─── Cardiología ambulatoria ────────────────────────────────────────────
    "881205AMB": (13.36, 780_000, "Ecocardiograma transesofágico", "RES_124_2026"),
    "881210AMB": (
        20.56,
        1_200_000,
        "Ecocardiograma de stress (esfuerzo o farmacológica)",
        "RES_124_2026",
    ),
    "881202AMB": (9.93, 580_000, "Ecocardiograma transtorácico", "RES_124_2026"),
    "894102AMB": (5.48, 320_000, "Prueba de esfuerzo cardiovascular", "RES_124_2026"),
    "895004AMB": (
        7.71,
        450_000,
        "Monitoreo ambulatorio de presión arterial sistémica (MAPA)",
        "RES_124_2026",
    ),
    "881214AMB": (
        13.36,
        780_000,
        "Ecocardiograma transtorácico con deformidad miocárdica",
        "RES_124_2026",
    ),
    # ─── Gineco-oncológicos ─────────────────────────────────────────────────
    "671201": (11.13, 650_000, "Biopsia en sacabocado de cuello uterino", "RES_124_2026"),
    "671202": (14.56, 850_000, "Biopsia de cuello uterino circunferencial", "RES_124_2026"),
    "673101": (14.56, 850_000, "Escisión de pólipo en cuello uterino [cérvix]", "RES_124_2026"),
    "681105": (12.85, 750_000, "Biopsia de endometrio", "RES_124_2026"),
    "690103": (14.56, 850_000, "Legrado uterino ginecológico", "RES_124_2026"),
    "711110": (14.56, 850_000, "Biopsia de labio mayor vulva", "RES_124_2026"),
    "673102": (
        11.13,
        650_000,
        "Resección de lesión cuello uterino (modificada Res. 124)",
        "RES_124_2026",
    ),
    # ─── Cirugías mayores (ejemplo representativo, Res. 124) ────────────────
    "054204H": (600.19, 35_029_200, "Reconstrucción de plejo braquial", "RES_124_2026"),
    "849501H": (
        216.15,
        12_615_200,
        "Cirugía reconstructiva múltiple en fémur, tibia y peroné",
        "RES_124_2026",
    ),
    "849701H": (
        216.15,
        12_615_200,
        "Cirugía reconstructiva múltiple en húmero, cúbito o radio",
        "RES_124_2026",
    ),
    "841501": (148.13, 8_645_900, "Amputación o desarticulación de pierna", "RES_124_2026"),
    # ─── Modificación Res. 124: Capítulo VI (procedimientos quirúrgicos) ───
    "017202H": (
        216.15,
        12_615_200,
        "Resección tumor supratentorial hemisférico por craneotomía osteoplástica",
        "RES_124_2026",
    ),
    "395080H": (
        86.05,
        5_022_200,
        "Angioplastia o aterectomía de vasos miembros inferiores con balón",
        "RES_124_2026",
    ),
}


# ─── EJEMPLOS TARIFA SOAT 2026 — Circular 047/2025 (UVB × $12.110) ──────────
# Valores oficiales del texto de la Circular. Se usan como referencia
# cuando la glosa es SOAT y no conocemos el factor_uvb completo del CUPS.

TARIFAS_SOAT_2026: dict[str, tuple[float, int, str, str]] = {
    # (factor_uvb, valor_pesos_2026, descripcion, norma)
    "19001": (5.93, 71_800, "Acetaminofén", "CIRCULAR_047_2025"),
    "19007": (
        63.74,
        # 63,74 UVB × $12.110 = $771.891,40 → centena más próxima = $771.900.
        # Estaba escrito $771.800: se redondeó hacia abajo en vez de a la
        # centena más próxima, como manda el numeral 87 del Anexo técnico 1
        # del Decreto 780/2016. Cien pesos, pero era una cifra que el sistema
        # le entregaba a la IA como «valor oficial».
        771_900,
        "Ácidos grasos de cadena muy larga cuantificación",
        "CIRCULAR_047_2025",
    ),
    "19505": (0.567, 6_900, "Hematocrito", "CIRCULAR_047_2025"),
    "19575": (305.70, 3_702_000, "Histocompatibilidad, estudio completo HLA", "CIRCULAR_047_2025"),
}


def tarifas_propias_hus_completas() -> dict[str, dict]:
    """Catálogo institucional completo del HUS (TARIFAS_HUS.xlsx): ~1.900
    procedimientos, paquetes, exámenes ambulatorios y órtesis con su valor
    propio en pesos 2026, indexados por CUPS.

    Se lee una sola vez. Si el archivo no está, devuelve {} y el sistema sigue
    con las 84 tarifas transcritas a mano — nunca inventa una tarifa.
    """
    global _CACHE_PROPIAS
    if _CACHE_PROPIAS is not None:
        return _CACHE_PROPIAS
    catalogo: dict[str, dict] = {}
    try:
        with gzip.open(_RUTA_PROPIAS, "rt", encoding="utf-8") as f:
            catalogo = json.load(f).get("tarifas", {}) or {}
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        catalogo = {}
    _CACHE_PROPIAS = catalogo
    return catalogo


def _cups_base(codigo: str) -> str:
    """De un código IPS a su CUPS: '512101H' → '512101'. Los alfanuméricos
    (órtesis 'AGMO102T') se dejan igual."""
    k = str(codigo or "").strip().upper()
    if k[:6].isdigit() and len(k) > 6:
        return k[:6]
    return k


def buscar_tarifa_propia_hus(cups_o_codigo_ips: str) -> dict | None:
    """Busca en el catálogo de tarifas propias HUS (Res. 054/2026 + 124/2026).

    Acepta códigos IPS (con sufijo H/H1/…) y CUPS raw. Si el CUPS viene
    sin sufijo pero existe la variante "H" básica, la devuelve."""
    if not cups_o_codigo_ips:
        return None
    k = cups_o_codigo_ips.strip().upper()
    if k in TARIFAS_PROPIAS_HUS:
        f, v, d, n = TARIFAS_PROPIAS_HUS[k]
        return {
            "codigo_ips": k,
            "factor_smdlv": f,
            "valor_pesos_2026": v,
            "descripcion": d,
            "norma": n,
        }
    # Fallback: intentar con sufijo H
    variantes = [k + "H", k + "H1", k + "H2", k + "H3"]
    for var in variantes:
        if var in TARIFAS_PROPIAS_HUS:
            f, v, d, n = TARIFAS_PROPIAS_HUS[var]
            return {
                "codigo_ips": var,
                "factor_smdlv": f,
                "valor_pesos_2026": v,
                "descripcion": d,
                "norma": n,
            }
    # Catálogo institucional completo (TARIFAS_HUS.xlsx). Se busca por CUPS.
    catalogo = tarifas_propias_hus_completas()
    fila = catalogo.get(k) or catalogo.get(_cups_base(k))
    if fila:
        # 20-08-2026: el catálogo pasó a tener tarifas de varias resoluciones.
        # La ficha dice de cuál sale cada una para que el dictamen cite la que
        # corresponde y no una derogada — la EPS verifica la norma citada.
        return {
            "codigo_ips": fila.get("codigo_ips") or k,
            "factor_smdlv": None,
            "valor_pesos_2026": int(fila["valor"]),
            "descripcion": fila.get("descripcion", ""),
            "norma": f"Tarifa propia HUS 2026 ({fila.get('tipo', 'PROPIA')})",
            "resolucion": _RESOLUCIONES.get(
                fila.get("norma", ""), "Resolución 054 de 2026 + Resolución 124 de 2026 ESE HUS"
            ),
        }
    return None


# Cómo se cita cada resolución en el dictamen. La clave es lo que el generador
# graba en el catálogo; sin clave, la cita histórica (054 + 124 de 2026).
_RESOLUCIONES: dict[str, str] = {
    "RES_283_2026": "Resolución 283 de 2026 ESE HUS",
}


def tarifa_por_niveles(cups: str) -> list[int] | None:
    """Los valores de un CUPS que la resolución publica por NIVELES.

    20-08-2026. La Res. 283/2026 trae cuatro códigos repetidos con valores
    distintos —399802 HEMOFILTRACIÓN VENOVENOSA a $5.450.000, $7.260.000 y
    $9.075.000— sin decir cuál aplica a cada caso. Quedaron FUERA del catálogo
    a propósito: elegir uno sería inventarle al dictamen una cifra que puede no
    ser la del paciente.

    Devolverlos acá permite que el motor AVISE («esta tarifa tiene tres
    niveles, verifíquela») en vez de callar o de afirmar la que no es.
    """
    if not cups:
        return None
    meta = _meta_propias()
    niveles = (meta.get("res_283_2026") or {}).get("por_niveles_excluidos") or {}
    k = str(cups).strip().upper()
    return niveles.get(k) or niveles.get(_cups_base(k))


def _meta_propias() -> dict:
    """El bloque `_meta` del catálogo comprimido (leído una sola vez)."""
    global _CACHE_META_PROPIAS
    if _CACHE_META_PROPIAS is not None:
        return _CACHE_META_PROPIAS
    meta: dict = {}
    try:
        with gzip.open(_RUTA_PROPIAS, "rt", encoding="utf-8") as f:
            meta = json.load(f).get("_meta", {}) or {}
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        meta = {}
    _CACHE_META_PROPIAS = meta
    return meta


# ─── Manual SOAT 2026 completo — Circular Externa 047 de 2025 ───────────────
#
# Los cuatro códigos de TARIFAS_SOAT_2026 se transcribieron a mano del PDF
# oficial. La tabla completa —1.507 códigos— se lee del catálogo comprimido
# que genera tools/generar_soat_uvb_2026_json.py leyendo ese mismo PDF. Los
# dos coinciden exactamente en los cuatro: esa es la prueba de que la lectura
# automática del escaneo no inventó cifras.
#
# Sin esta tabla el sistema respondía «sin tarifa local — consulte el Manual
# SOAT 2026 oficial» para 1.503 de los 1.507 códigos, justo cuando la EPS
# objeta la tarifa. Importa especialmente en los contratos pactados contra
# el SOAT (FAMISANAR: «SOAT UVB vigente −5%»; Policía Nacional: «UVB −8%»).

_RUTA_SOAT_2026 = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "soat_uvb_2026.json.gz"
)
_CACHE_SOAT_2026: dict[str, tuple[float, int, str, str]] | None = None
_CACHE_INTEGRALES: set[str] | None = None

_RUTA_PROPIAS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "tarifas_propias_hus.json.gz"
)
_CACHE_PROPIAS: dict[str, dict] | None = None
_CACHE_META_PROPIAS: dict | None = None


def tarifas_soat_2026_completas() -> dict[str, tuple[float, int, str, str]]:
    """Catálogo completo de la Circular 047/2025, con la misma forma que
    TARIFAS_SOAT_2026: {codigo: (factor_uvb, valor_pesos, descripcion, norma)}.

    Se lee una sola vez y se deja en memoria. Si el archivo no está, devuelve
    los cuatro códigos transcritos a mano y el sistema sigue funcionando.
    """
    global _CACHE_SOAT_2026, _CACHE_INTEGRALES
    if _CACHE_SOAT_2026 is not None:
        return _CACHE_SOAT_2026

    from app.services.uvb import calcular_valor_pesos

    catalogo: dict[str, tuple[float, int, str, str]] = {}
    integrales: set[str] = set()
    try:
        with gzip.open(_RUTA_SOAT_2026, "rt", encoding="utf-8") as f:
            datos = json.load(f)
        for codigo, fila in (datos.get("tarifas") or {}).items():
            cod = str(codigo).strip().upper()
            uvb = float(fila["uvb"])
            catalogo[cod] = (
                uvb,
                calcular_valor_pesos(uvb, 2026),
                str(fila.get("descripcion") or "").strip(),
                "CIRCULAR_047_2025",
            )
            if fila.get("integral"):
                integrales.add(cod)
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        # Catálogo ausente o dañado: se sigue con lo transcrito a mano. Nunca
        # se inventa una tarifa para rellenar.
        catalogo = {}

    # Lo transcrito a mano manda sobre lo leído del escaneo.
    catalogo.update(TARIFAS_SOAT_2026)
    _CACHE_SOAT_2026 = catalogo
    _CACHE_INTEGRALES = integrales
    return catalogo


def es_atencion_integral(codigo: str) -> bool:
    """True si el código SOAT es un PAQUETE quirúrgico todo-incluido (sala,
    honorarios, anestesia, materiales y estancia en un solo valor), bajo el
    título 'Atención integral... de intervenciones quirúrgicas' de la Circular
    047/2025. Es otra modalidad, distinta del pago por grupo quirúrgico."""
    if _CACHE_INTEGRALES is None:
        tarifas_soat_2026_completas()
    return str(codigo).strip().upper() in (_CACHE_INTEGRALES or set())


def buscar_tarifa_soat_2026(cups: str) -> dict | None:
    """Busca en el catálogo de tarifas SOAT 2026 (Circular 047/2025)."""
    if not cups:
        return None
    k = cups.strip().upper()
    fila = tarifas_soat_2026_completas().get(k)
    if fila:
        f, v, d, n = fila
        return {
            "codigo_cups": k,
            "factor_uvb": f,
            "valor_pesos_2026": v,
            "descripcion": d,
            "norma": n,
        }
    return None


def _pesos(valor: float) -> str:
    """$14.819.100 — punto de miles, como se escribe en Colombia.

    El bloque de abajo va al prompt de la IA: si le llega '$14,819,100'
    la IA lo copia así al dictamen y el auditor recibe una cifra escrita
    a la gringa en un documento que va radicado a la EPS."""
    return "$" + f"{int(round(valor)):,}".replace(",", ".")


def contexto_tarifa_oficial(cups: str) -> str:
    """Construye un bloque de texto para inyectar al prompt IA con los
    valores oficiales conocidos del CUPS. Devuelve cadena vacía si no hay match.
    """
    bloques: list[str] = []

    hus = buscar_tarifa_propia_hus(cups)
    if hus:
        _res = hus.get("resolucion") or "Res. 054/2026 + Res. 124/2026 ESE HUS"
        bloques.append(
            f"[TARIFA PROPIA HUS - {_res} · código IPS {hus['codigo_ips']}]\n"
            f"Descripción: {hus['descripcion']}\n"
            f"Factor: {hus['factor_smdlv']} SMDLV → Valor oficial 2026: "
            f"${hus['valor_pesos_2026']:,.0f}\n"
            "Este es el valor exacto publicado en la resolución institucional. "
            "Si la EPS reconoce un valor menor sin soporte contractual, defender "
            f"la tarifa oficial citando la {_res}."
        )

    # Tarifa publicada por niveles: se avisa, no se elige.
    niveles = tarifa_por_niveles(cups)
    if niveles:
        _lista = ", ".join(_pesos(v) for v in niveles)
        bloques.append(
            f"[TARIFA PROPIA HUS POR NIVELES - CUPS {cups}]\n"
            f"La Resolución 283 de 2026 publica este código con {len(niveles)} "
            f"valores distintos: {_lista}.\n"
            "NO afirmes ninguno de esos valores como la tarifa del caso: la "
            "resolución no dice cuál aplica. Indica que la tarifa institucional "
            "de este procedimiento está publicada por niveles y debe verificarse "
            "contra el nivel efectivamente prestado."
        )

    soat = buscar_tarifa_soat_2026(cups)
    if soat:
        bloques.append(
            f"[TARIFA SOAT 2026 - Circular 047/2025 · CUPS {soat['codigo_cups']}]\n"
            f"Descripción: {soat['descripcion']}\n"
            f"Factor: {soat['factor_uvb']} UVB × $12.110 = {_pesos(soat['valor_pesos_2026'])}\n"
            "Este es el valor SOAT pleno vigente 2026. Si el contrato pactó "
            f"'SOAT -X%', aplicar: {_pesos(soat['valor_pesos_2026'])} × (1 - X/100)."
        )

    return "\n\n".join(bloques)


def tarifa_a_banner_dict(cups: str) -> dict | None:
    """Devuelve un dict compatible con el banner de tarifa pactada cuando
    el lookup de tarifas_contratadas (EPS + CUPS) NO encuentra nada pero
    sí hay info oficial del CUPS. Útil para fallback."""
    hus = buscar_tarifa_propia_hus(cups)
    if hus:
        return {
            "codigo_cups": hus["codigo_ips"],
            "descripcion": hus["descripcion"],
            "valor_pactado": float(hus["valor_pesos_2026"]),
            "tipo_tarifa": "VALOR_FIJO",
            "factor_ajuste": 0.0,
            "modalidad": f"TARIFA PROPIA HUS ({hus.get('resolucion') or 'Res. 124/2026'})",
            "contrato_numero": (
                hus.get("resolucion") or "Resolución 054 de 2026 + Resolución 124 de 2026 ESE HUS"
            ),
            "fuente_archivo": "Catálogo oficial HUS",
            "eps": None,
            "vigencia_desde": None,
            "vigencia_hasta": None,
        }
    soat = buscar_tarifa_soat_2026(cups)
    if soat:
        return {
            "codigo_cups": soat["codigo_cups"],
            "descripcion": soat["descripcion"],
            "valor_pactado": float(soat["valor_pesos_2026"]),
            "tipo_tarifa": "VALOR_FIJO",
            "factor_ajuste": 0.0,
            "modalidad": "SOAT PLENO 2026",
            "contrato_numero": "Circular Externa 047 de 2025 MinSalud",
            "fuente_archivo": "Catálogo oficial SOAT 2026",
            "eps": None,
            "vigencia_desde": None,
            "vigencia_hasta": None,
        }
    return None
