"""Parsing canónico de valores monetarios COP (formato colombiano).

Única fuente de verdad para convertir strings de dinero a float. En
Colombia el punto es separador de MILES y la coma es separador DECIMAL:

    "7.700,00"    → 7700.0      (siete mil setecientos pesos)
    "1.500.000"   → 1500000.0
    "$ 500.000"   → 500000.0

El patrón ingenuo ``float(re.sub(r"[^\\d]", "", x))`` que existía en
varios call sites (analizar.py, glosas.py, schemas.py) convertía
"7.700,00" en 770000 — un error de 100× en los valores persistidos.
Bug detectado el 12-may-2026 en auto_pilot_decision y corregido allí;
esta extracción propaga ese parser correcto al resto del sistema
(auditoría jun-2026, hallazgo P0 #1).

NOTA: la corrección aplica solo a valores NUEVOS. El backfill de filas
históricas en BD es una operación separada (dry-run + snapshot previo).
"""

from __future__ import annotations

import re

__all__ = ["parse_valor_cop", "palabras_a_numero"]

# Multiplicadores verbales colombianos: "$850 millones", "120 mil pesos",
# "1,5 mil millones". El parser de mayo-2026 corrigió los separadores
# (7.700,00) pero nadie pensó en los multiplicadores en palabras — el
# 10-jun-2026 una glosa de "$850 millones" entró a BD como $850 (misma
# clase de bug que el 100×, segunda aparición). El orden importa:
# "mil millones" debe evaluarse antes que "millones" y que "mil".
_MULTIPLICADORES = (
    (
        re.compile(r"\bmil(?:es)?\s+de\s+millones\b|\bmil\s+millones\b", re.IGNORECASE),
        1_000_000_000,
    ),
    (re.compile(r"\bmillon(?:es)?\b|\bmillón\b|\bmillones\b", re.IGNORECASE), 1_000_000),
    (re.compile(r"\bmil(?:es)?\b", re.IGNORECASE), 1_000),
)


def _detectar_multiplicador(s: str) -> tuple[str, int]:
    """Devuelve (string sin la palabra multiplicadora, factor).

    "850 millones" → ("850 ", 1_000_000); "1,5 mil" → ("1,5 ", 1_000).
    Si no hay multiplicador, devuelve (s, 1).
    """
    for pat, factor in _MULTIPLICADORES:
        if pat.search(s):
            return pat.sub(" ", s), factor
    return s, 1


# ── Números cardinales deletreados en palabras (12-jun-2026, ronda 2) ──
# Evaluación de estrés ronda-2: "novecientos cincuenta y dos millones de
# pesos" entraba a BD como $0.00 — el parser solo cubría multiplicadores
# verbales junto a DÍGITOS ("850 millones"), no el número completo en
# letras. Cobertura: cardinales españoles estándar 1–999 millones con
# composiciones "centena + decena + y + unidad" + "mil" + "millón/millones".
# Sin acentos (se normalizan) y sin NLP: solo tabla de palabras + acumulador.
_CARDINAL_UNIDADES = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiun": 21,
    "veintiuno": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}
_CARDINAL_DECENAS = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}
_CARDINAL_CENTENAS = {
    "cien": 100,
    "ciento": 100,
    "doscientos": 200,
    "doscientas": 200,
    "trescientos": 300,
    "trescientas": 300,
    "cuatrocientos": 400,
    "cuatrocientas": 400,
    "quinientos": 500,
    "quinientas": 500,
    "seiscientos": 600,
    "seiscientas": 600,
    "setecientos": 700,
    "setecientas": 700,
    "ochocientos": 800,
    "ochocientas": 800,
    "novecientos": 900,
    "novecientas": 900,
}
_ACENTOS_TR = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")


def palabras_a_numero(texto) -> float:
    """Convierte un número cardinal español deletreado en palabras a float.

    "novecientos cincuenta y dos millones" → 952_000_000.0
    "doscientos treinta mil"               → 230_000.0
    "un millón doscientos mil"             → 1_200_000.0

    Conservador por diseño (ronda 2, 12-jun-2026): solo devuelve > 0 si la
    frase trae un cardinal EXPLÍCITO (unidad/decena/centena) seguido de una
    palabra de ESCALA ("mil" / "millón" / "millones"). Un "una" o "tres"
    suelto en prosa jamás se convierte en valor, y "mil millones" sin
    número delante tampoco — coherente con parse_valor_cop("mil millones")
    == 0.0 del fix P0-2 del 10-jun-2026 ("sin número delante no hay cifra").
    """
    if not texto:
        return 0.0
    t = str(texto).translate(_ACENTOS_TR).lower()
    tokens = re.findall(r"[a-zñ]+", t)
    if not tokens:
        return 0.0

    millones = 0  # acumulado en millones ya cerrados
    miles = 0  # acumulado del grupo de miles/unidades actual
    sub = 0  # acumulador 1-999 en construcción
    en_numero = False  # ya arrancó la secuencia cardinal
    vio_escala = False  # apareció mil/millón (gate conservador)
    vio_cardinal = False  # apareció un cardinal explícito (no solo "mil")

    for tok in tokens:
        if tok in _CARDINAL_CENTENAS:
            sub += _CARDINAL_CENTENAS[tok]
            en_numero = True
            vio_cardinal = True
        elif tok in _CARDINAL_DECENAS:
            sub += _CARDINAL_DECENAS[tok]
            en_numero = True
            vio_cardinal = True
        elif tok in _CARDINAL_UNIDADES:
            sub += _CARDINAL_UNIDADES[tok]
            en_numero = True
            vio_cardinal = True
        elif tok == "y" and en_numero:
            continue  # "cincuenta y dos"
        elif tok in ("mil", "miles"):
            if tok == "miles" and not en_numero:
                # "miles de millones" en prosa, sin cardinal previo → no es cifra
                continue
            # "mil" solo = 1.000; "doscientos treinta mil" = 230.000
            sub = (sub or 1) * 1_000
            miles += sub
            sub = 0
            en_numero = True
            vio_escala = True
        elif tok in ("millon", "millones") and en_numero:
            grupo = miles + sub
            if grupo <= 0:
                # "los millones de pesos..." sin cardinal previo → no es cifra
                return 0.0
            millones += grupo * 1_000_000
            miles = 0
            sub = 0
            vio_escala = True
        elif en_numero:
            # Primer token no-cardinal tras la secuencia → fin del número
            # ("...dos millones DE pesos", "...mil PESOS m/cte").
            break

    if not (en_numero and vio_escala and vio_cardinal):
        return 0.0
    valor = millones + miles + sub
    return float(valor) if valor > 0 else 0.0


def parse_valor_cop(valor_raw) -> float:
    """Convierte string "$1.234.567" / "7.700,00" / "850 millones" o número a float COP.

    Reglas (formato colombiano):
      - int/float → float directo; None/vacío/no-numérico → 0.0
      - Prefijos no numéricos ($, COL$, %, espacios) se descartan.
      - Multiplicadores verbales: "850 millones" → 850000000.0,
        "120 mil" → 120000.0, "1,5 mil millones" → 1500000000.0.
      - Si hay coma con 1-2 dígitos al final → es separador decimal
        ("7.700,00" → 7700.0).
      - Si hay coma con 3+ dígitos detrás → se trata como separador de
        miles y se eliminan todos los símbolos ("1,500,000" → 1500000.0).
      - Sin coma: TODOS los puntos se asumen separadores de miles
        ("1.500.000" → 1500000.0, "1'500.000" → 1500000.0).
    """
    if valor_raw is None:
        return 0.0
    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)
    s = str(valor_raw).strip()
    # Para el último intento en palabras (ronda 2, 12-jun-2026) necesitamos
    # el string ORIGINAL: _detectar_multiplicador borra justamente la
    # palabra "millones" que palabras_a_numero usa como escala.
    s_original = s
    # Multiplicador verbal ANTES de limpiar (la limpieza borra letras)
    s, factor = _detectar_multiplicador(s)
    # Quitar prefijos no numéricos al inicio ($, %, espacios, COL$, etc.)
    s = re.sub(r"^[^\d\-]+", "", s)
    if not s:
        # Último intento (ronda 2, 12-jun-2026): cifra deletreada en
        # palabras sin un solo dígito — "novecientos cincuenta y dos
        # millones de pesos" llegaba aquí y se persistía como $0.00.
        return palabras_a_numero(s_original)
    # Formato colombiano: puntos = miles, coma = decimal ("7.700,00" = 7700.00).
    if "," in s:
        partes = s.rsplit(",", 1)
        enteros = re.sub(r"[^\d\-]", "", partes[0])
        decimales = partes[1].strip()
        # Con multiplicador, la coma decimal es lo usual: "2,5 millones".
        decimales = re.sub(r"[^\d]", "", decimales)
        if 1 <= len(decimales) <= 2 and decimales.isdigit():
            try:
                return float(f"{enteros}.{decimales}") * factor
            except Exception:
                return 0.0
        # Coma no era decimal (más de 2 dígitos detrás) → todo a entero
        cleaned = re.sub(r"[^\d]", "", s)
        return float(cleaned) * factor if cleaned else 0.0
    # Con multiplicador y UN punto con 1-2 decimales ("1.5 millones" estilo
    # informal) → punto decimal, no separador de miles.
    if factor > 1:
        m_dec = re.fullmatch(r"(\d+)\.(\d{1,2})\D*", s)
        if m_dec:
            return float(f"{m_dec.group(1)}.{m_dec.group(2)}") * factor
    # Sin coma: los puntos se asumen separadores de miles (Colombia)
    cleaned = re.sub(r"[^\d]", "", s)
    return float(cleaned) * factor if cleaned else 0.0
