"""Unidades tarifarias 2026 — UVB (SOAT) y FACTOR SMDLV (tarifas propias HUS).

Marco normativo completo:

1) MANUAL SOAT 2026 — expresado en UVB
   - Circular Externa 047 de 2025 del Ministerio de Salud y Protección Social
   - Resolución MinHacienda 31/12/2025: UVB 2026 = $12.110
   - Decreto 780/2016 (marco general sector salud) — Anexo Técnico No. 1
   - Fórmula: valor_pesos = Tarifa_UVB × $12.110 → centena más próxima
   - Aplica a: accidentes de tránsito (SOAT), desastres, atentados, eventos
     catastróficos, y atención inicial de urgencias sin acuerdo tarifario

2) TARIFAS PROPIAS ESE HUS — expresadas en FACTOR SMDLV
   - Resolución 054 de enero 30 de 2026 (ESE HUS): unifica el listado maestro
     de tarifas propias del hospital. Cada CUPS trae un "FACTOR SMDLV" que,
     multiplicado por el SMDLV vigente, da el valor en pesos.
   - Resolución 124 de marzo 25 de 2026 (ESE HUS): crea nuevos códigos
     institucionales (lab clínico, quirúrgicos, electrofisiología, etc.) y
     modifica algunas tarifas de la Res. 054.
   - SMDLV 2026 ≈ $58.375 (derivado del SMLMV 2026, ajustable por Res. Junta
     Directiva HUS). Ejemplos oficiales de la Res. 124/2026:
       · 3,94 SMDLV = $230.000 (Potenciales evocados miogénicos)
       · 14,32 SMDLV = $836.200 (Cardioversión eléctrica a tórax cerrado)
       · 44,56 SMDLV = $2.601.000 (Estudio electrofisiológico cardíaco)
   - Las tarifas se ajustan anualmente con el incremento del SMLMV
     (Acuerdo Junta Directiva HUS No. 003 de 2018).

Fuera de los casos obligatorios del SOAT, el tarifario SOAT puede usarse
como REFERENTE para otros contratos (ej. FAMISANAR pacta "SOAT -5%"; otros
contratos pactan "TARIFAS PROPIAS" que aluden a la Res. 054/2026 HUS).
"""
from __future__ import annotations


# ─── UVB (Manual SOAT 2026) ─────────────────────────────────────────────────

UVB_2026: int = 12_110
UVB_POR_VIGENCIA: dict[int, int] = {2026: UVB_2026}


# ─── SMDLV (tarifas propias HUS) ────────────────────────────────────────────
# Valor aproximado derivado de los ejemplos oficiales de la Res. 124/2026:
#  3.94 × X = 230.000 → X ≈ 58.376; 14.32 × X = 836.200 → X ≈ 58.394;
#  44.56 × X = 2.601.000 → X ≈ 58.371. Promedio ≈ 58.380.
SMDLV_2026: int = 58_375
SMDLV_POR_VIGENCIA: dict[int, int] = {2026: SMDLV_2026}


# ─── Referencias textuales normativas ───────────────────────────────────────

MARCO_SOAT_2026 = (
    "Manual Tarifario SOAT 2026 — Circular Externa 047 de 2025 del "
    "Ministerio de Salud y Protección Social, en concordancia con el "
    "Decreto 780 de 2016 (Anexo Técnico No. 1) y la Resolución del "
    "Ministerio de Hacienda que fija la UVB 2026 en $12.110. Fórmula: "
    "valor_pesos = Tarifa_UVB × $12.110, ajustado a la centena más próxima."
)

MARCO_SOAT_2026_COMPACTO = "Circular 047/2025 MinSalud + UVB 2026 $12.110"

MARCO_TARIFAS_PROPIAS_HUS = (
    "Tarifas propias de la ESE Hospital Universitario de Santander — "
    "Resolución 054 de enero 30 de 2026 (listado unificado) y Resolución "
    "124 de marzo 25 de 2026 (nuevos códigos institucionales y "
    f"modificaciones). Expresadas en FACTOR SMDLV (SMDLV 2026 ≈ ${SMDLV_2026:,}); "
    "valor_pesos = FACTOR × SMDLV vigente."
)

MARCO_PROPIAS_HUS_COMPACTO = f"Res. 054/2026 + Res. 124/2026 HUS · SMDLV ${SMDLV_2026:,}"


def valor_uvb_vigente(anio: int = 2026) -> int:
    """UVB vigente para el año dado; fallback al último conocido."""
    if anio in UVB_POR_VIGENCIA:
        return UVB_POR_VIGENCIA[anio]
    return UVB_POR_VIGENCIA[max(UVB_POR_VIGENCIA.keys())]


def valor_smdlv_vigente(anio: int = 2026) -> int:
    """SMDLV vigente para el año dado; fallback al último conocido."""
    if anio in SMDLV_POR_VIGENCIA:
        return SMDLV_POR_VIGENCIA[anio]
    return SMDLV_POR_VIGENCIA[max(SMDLV_POR_VIGENCIA.keys())]


def _redondear_a_centena(v: float) -> int:
    return int(round(v / 100.0) * 100)


def calcular_valor_pesos(tarifa_uvb: float, anio: int = 2026) -> int:
    """SOAT: UVB × valor UVB vigente → centena más próxima.
    Ejemplos: 5.93 UVB × 12.110 = 71.812,3 → 71.800;
              0.567 UVB × 12.110 = 6.866,37 → 6.900."""
    if tarifa_uvb is None or tarifa_uvb <= 0:
        return 0
    return _redondear_a_centena(float(tarifa_uvb) * valor_uvb_vigente(anio))


def calcular_soat_con_factor(
    tarifa_uvb: float, factor_pct: float = 0.0, anio: int = 2026
) -> int:
    """Contrato 'SOAT ± X%': UVB × valor_UVB × (1+pct/100) → centena."""
    if tarifa_uvb is None or tarifa_uvb <= 0:
        return 0
    uvb = valor_uvb_vigente(anio)
    return _redondear_a_centena(float(tarifa_uvb) * uvb * (1 + factor_pct / 100.0))


def calcular_propia_hus(factor_smdlv: float, anio: int = 2026) -> int:
    """Tarifa propia HUS: FACTOR × SMDLV vigente → centena.
    Ejemplos (Res. 124/2026):
      3.94 × 58.375 = 229.997 → 230.000
      14.32 × 58.375 = 835.930 → 835.900 (cercano al $836.200 oficial)
    Nota: el SMDLV que usa HUS puede variar levemente por redondeos internos;
    la fórmula oficial está en la Res. 124/2026 y el Acuerdo Junta No. 003/2018."""
    if factor_smdlv is None or factor_smdlv <= 0:
        return 0
    return _redondear_a_centena(float(factor_smdlv) * valor_smdlv_vigente(anio))


def inferir_uvb_desde_pesos(valor_pesos: float, anio: int = 2026) -> float:
    """Inverso: valor en pesos → UVB implícita (para explicar discrepancias)."""
    if valor_pesos <= 0:
        return 0.0
    return round(valor_pesos / valor_uvb_vigente(anio), 3)


def marco_normativo_segun_modalidad(modalidad: str) -> str:
    """Devuelve la cita normativa correcta según la modalidad tarifaria.

    - 'SOAT UVB VIGENTE', 'SOAT -5%', 'SOAT' → Circular 047/2025 + UVB 2026
    - 'PROPIAS', 'TARIFA PROPIA', 'MANUAL HUS' → Res. 054/2026 + 124/2026 HUS (SMDLV)
    - Otros (MEDICAMENTOS, SUMINISTROS…) → valor fijo pactado en contrato
    """
    if not modalidad:
        return MARCO_SOAT_2026
    m = modalidad.upper()
    if "PROPIA" in m or "MANUAL HUS" in m or "INSTITUCIONAL" in m:
        return MARCO_TARIFAS_PROPIAS_HUS
    if "SOAT" in m or "UVB" in m:
        return MARCO_SOAT_2026
    return "Valor pactado en el contrato vigente entre las partes."


def valor_uvb_vigente(anio: int = 2026) -> int:
    """Devuelve el valor de la UVB vigente para el año solicitado.
    Si no hay dato, cae al último conocido."""
    if anio in UVB_POR_VIGENCIA:
        return UVB_POR_VIGENCIA[anio]
    # Fallback al mayor año conocido
    return UVB_POR_VIGENCIA[max(UVB_POR_VIGENCIA.keys())]


def _redondear_a_centena(v: float) -> int:
    """Redondea a la centena más próxima (reglas Anexo Técnico 1, Dec. 780/2016).

    Ejemplos:
      71_812.3 → 71_800
      71_850.0 → 71_900 (punto medio sube — regla bancaria estándar)
      6_866.37 → 6_900
    """
    return int(round(v / 100.0) * 100)


def calcular_valor_pesos(tarifa_uvb: float, anio: int = 2026) -> int:
    """Convierte una tarifa en UVB a pesos con la fórmula oficial.

    Ejemplos (con UVB 2026 = $12.110):
      acetaminofén   5,93 UVB × 12.110 = 71.812,3 → 71.800
      hematocrito    0,567 UVB × 12.110 = 6.866,37 → 6.900
      histocompat.   305,70 UVB × 12.110 = 3.702.027 → 3.702.000
    """
    if tarifa_uvb is None or tarifa_uvb <= 0:
        return 0
    uvb = valor_uvb_vigente(anio)
    return _redondear_a_centena(float(tarifa_uvb) * uvb)


def calcular_soat_con_factor(
    tarifa_uvb: float, factor_pct: float = 0.0, anio: int = 2026
) -> int:
    """Calcula la tarifa pactada cuando el contrato dice 'SOAT ± X%'.

    Ejemplo: Famisanar CUPS 890750 = 5,93 UVB con factor -5% →
    5,93 × 12.110 × 0.95 = 68.221,68 → 68.200
    """
    if tarifa_uvb is None or tarifa_uvb <= 0:
        return 0
    uvb = valor_uvb_vigente(anio)
    valor_pesos_bruto = float(tarifa_uvb) * uvb * (1 + factor_pct / 100.0)
    return _redondear_a_centena(valor_pesos_bruto)


def inferir_uvb_desde_pesos(valor_pesos: float, anio: int = 2026) -> float:
    """Inverso de calcular_valor_pesos: dado un valor en pesos, infiere la UVB.
    Útil para explicar en el banner qué UVB asume HUS vs EPS cuando hay
    discrepancia. El resultado puede no ser entero si la tarifa no está
    redondeada exactamente a centena."""
    if valor_pesos <= 0:
        return 0.0
    uvb = valor_uvb_vigente(anio)
    return round(valor_pesos / uvb, 3)
