"""Un solo lector de pesos colombianos para todos los bots de `tools/`.

Existía tres veces, y una de las tres estaba mal:

    savia    `_num`      borraba todo lo no-dígito → "1.365,50" daba 136.550  (×100)
    emssanar `_a_entero` recortaba los centavos → 1.365                       (bien)
    vco      `_numero`   parser es-CO completo → 1.365,50                     (bien)

El bot de SAVIA producía el Excel que se carga al ERP con **todos los valores
con centavos multiplicados por cien**. La validación de suma no lo detectaba
porque encabezado y renglones se inflaban por igual.

Este módulo apunta al parser del núcleo (`app/utils/moneda.py`), que es el
mismo que usa la aplicación web. Si el bot corre suelto en el PC del hospital
—sin el paquete `app/` al alcance— cae a una copia local con la misma regla,
que está probada contra la del núcleo en `tests/test_tools/test_dinero.py`.

**La regla, en una línea:** un separador de miles siempre lleva tres dígitos
detrás; si el último grupo tiene una o dos cifras, es decimal.
"""

from __future__ import annotations

import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from app.utils.moneda import parse_valor_cop as _CORE
except Exception:  # pragma: no cover - el bot corre sin el paquete `app`
    _CORE = None


def _es_negativo_contable(texto: str) -> bool:
    """`(1.234)` es −1.234: así escriben los negativos los informes de cartera.

    Sin esto el signo se voltea, que en un consolidado de cartera convierte una
    nota crédito en un cargo.
    """
    t = texto.strip()
    return t.startswith("(") and t.endswith(")")


def _respaldo(texto: str) -> float:
    """Misma regla que el núcleo, para cuando `app/` no está disponible."""
    neg_contable = _es_negativo_contable(texto)
    s = re.sub(r"[^\d,.\-]", "", texto)
    if not s or s in {"-", ".", ","}:
        return 0.0
    neg = s.startswith("-") or neg_contable
    s = s.lstrip("-")
    # Con los dos separadores presentes, el último que aparece manda.
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        s = s.replace(mil, "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        entero, _, ultimo = s.rpartition(sep)
        # Tres dígitos detrás = separador de miles. Una o dos = decimales.
        if len(ultimo) == 3 and entero.replace(sep, "").isdigit():
            s = s.replace(sep, "")
        else:
            s = entero.replace(sep, "") + "." + ultimo
    try:
        n = float(s)
    except ValueError:
        return 0.0
    return -n if neg else n


def a_numero(valor: object) -> float:
    """Cualquier cosa → pesos como número. Lo ilegible vale 0."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, bool):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0.0
    if _CORE is not None:
        try:
            n = float(_CORE(texto))
            # El núcleo lee informes de la EPS, donde el paréntesis no se usa;
            # los consolidados de cartera sí lo traen, así que el signo se
            # aplica aquí en vez de tocar el parser de la aplicación web.
            return -abs(n) if _es_negativo_contable(texto) else n
        except Exception:
            pass
    return _respaldo(texto)


def a_entero(valor: object) -> int:
    """Pesos enteros: es lo que aceptan los formatos de cargue del ERP.

    Trunca, no redondea: `1.365,90` es 1.365. El ERP nunca recibió centavos y
    redondear hacia arriba cambiaría el total declarado del lote.
    """
    return int(a_numero(valor))


def a_texto(valor: object) -> str:
    """El camino de vuelta: un número se muestra como `$1.234.567`.

    Mismo resultado que el `TEXT(valor,"$#.##0")` de las macros del auditor:
    punto de miles y sin centavos. Los medios pesos se redondean **hacia
    arriba** —igual que Excel—, no con el redondeo bancario de Python, que
    dejaría `1.364,50` en 1.364 y el total del lote no cuadraría con la macro.

    Vive acá por la misma razón que el lector: para que no vuelva a haber diez
    copias, cada una escribiendo el total del lote de una manera distinta.
    """
    pesos = Decimal(str(a_numero(valor))).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return "$" + f"{int(pesos):,}".replace(",", ".")
