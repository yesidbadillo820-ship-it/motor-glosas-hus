"""`.env.example` y `config.py` no pueden decir modelos distintos.

19-08-2026. Yesid vio en el panel: «Primario: meta-llama/llama-4-scout-17b-16e
-instruct» pero la respuesta la sacó «Fallback 1: openai/gpt-oss-120b».

Ese modelo salió del catálogo de Groq el 05-08-2026 y devuelve «404 — the model
does not exist». Ese día se corrigió `config.py`… pero no `.env.example`. Los PC
que se montaron copiando el ejemplo quedaron con el modelo muerto de primario:

  · cada dictamen gasta una llamada fallida antes de caer al respaldo;
  · el panel muestra como «primario» un modelo que nunca responde;
  · y el diagnóstico decía «ningún proveedor responde» aunque el motor sí
    funcionaba.

Es el caso de manual del trabajo aislado: se arregló un sitio y no el otro.
Esta prueba obliga a que los dos vayan juntos.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
EJEMPLO = RAIZ / ".env.example"

# Modelos que YA NO existen en su proveedor: devuelven 404 y el motor gasta la
# llamada. Cada vez que uno se muera, se agrega acá y la prueba impide que
# vuelva a quedar configurado.
#
# El patrón se repite: el proveedor retira el modelo, el motor sigue pidiéndolo,
# y nadie se entera porque el fallback tapa el hueco. Con Gemini es peor: no hay
# fallback, así que el OCR de los PDF escaneados deja de funcionar en silencio.
RETIRADOS = {
    "meta-llama/llama-4-scout-17b-16e-instruct",  # Groq, retirado 05-08-2026
    "gemini-2.0-flash",  # «is no longer available», 19-08-2026
    "gemini-2.0-flash-exp",  # deprecado antes que el anterior
}

CLAVES = (
    ("GROQ_MODEL", "groq_model"),
    ("GROQ_MODEL_FALLBACK_1", "groq_model_fallback_1"),
    ("GROQ_MODEL_FALLBACK_2", "groq_model_fallback_2"),
    ("GROQ_MODEL_FALLBACK_3", "groq_model_fallback_3"),
    ("GEMINI_MODEL", "gemini_model"),
)


def _del_ejemplo(clave: str) -> str | None:
    if not EJEMPLO.exists():  # pragma: no cover
        pytest.skip(".env.example no está en este entorno")
    m = re.search(rf"^{clave}=(.*)$", EJEMPLO.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else None


def _defecto(campo: str) -> str:
    from app.core.config import Settings

    return Settings.model_fields[campo].default


@pytest.mark.parametrize("clave,campo", CLAVES)
def test_el_ejemplo_dice_lo_mismo_que_el_codigo(clave, campo):
    assert _del_ejemplo(clave) == _defecto(campo), (
        f"{clave} en .env.example no coincide con {campo} en config.py. "
        "Los dos se cambian juntos, o los PC nuevos nacen mal configurados."
    )


@pytest.mark.parametrize("clave,_campo", CLAVES)
def test_el_ejemplo_no_ofrece_modelos_muertos(clave, _campo):
    valor = _del_ejemplo(clave)
    assert valor not in RETIRADOS, f"{clave}={valor} ya no existe en el proveedor"


@pytest.mark.parametrize("_clave,campo", CLAVES)
def test_el_codigo_no_usa_modelos_muertos(_clave, campo):
    assert _defecto(campo) not in RETIRADOS


def test_la_cadena_de_groq_no_repite_modelos():
    """Un fallback igual al primario no es respaldo: es el mismo error dos veces."""
    groq = [_defecto(campo) for _clave, campo in CLAVES if _clave.startswith("GROQ")]
    assert len(groq) == len(set(groq)), groq
