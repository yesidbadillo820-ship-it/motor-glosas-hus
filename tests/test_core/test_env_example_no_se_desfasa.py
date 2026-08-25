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


# ─── Una sola fuente de verdad ───────────────────────────────────────────────


class TestNadieRepiteLaCadenaPorSuCuenta:
    """19-08-2026. Yesid vio en el panel «Primario: meta-llama/llama-4-scout»
    cuando `config.py` decía `openai/gpt-oss-120b` desde el 05-08.

    La causa: la cadena estaba escrita a mano en CUATRO sitios. El arreglo del
    05-08 tocó `config.py` y dejó los otros tres:

      · `.env.example`                  → los PC nuevos nacían mal
      · `GlosaService.__init__`         → construirlo sin pasar modelo
                                          resucitaba el muerto
      · `ia_status.PROVEEDORES_INFO`    → el panel mostraba la cadena vieja

    Un panel de diagnóstico que miente sobre la configuración es peor que no
    tener panel: mandó a buscar el problema donde no estaba.
    """

    def _fuentes(self):
        return {
            "app/services/glosa_service.py": RAIZ / "app" / "services" / "glosa_service.py",
            "app/api/routers/ia_status.py": RAIZ / "app" / "api" / "routers" / "ia_status.py",
        }

    def test_ningun_archivo_escribe_un_modelo_retirado_como_valor(self):
        """Nombrarlo en un comentario está bien; usarlo como valor, no."""
        import ast

        for nombre, ruta in self._fuentes().items():
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            textos = {
                n.value
                for n in ast.walk(arbol)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
            malos = textos & RETIRADOS
            assert not malos, f"{nombre} usa como valor un modelo retirado: {malos}"

    def test_el_servicio_toma_el_modelo_de_la_configuracion(self):
        from app.core.config import get_settings
        from app.services.glosa_service import GlosaService

        servicio = GlosaService(groq_api_key="x")
        cfg = get_settings()
        assert servicio.groq_model == cfg.groq_model
        assert servicio.groq_model_fallback_1 == cfg.groq_model_fallback_1
        assert servicio.gemini_model == cfg.gemini_model

    def test_el_panel_reporta_la_cadena_de_la_configuracion(self):
        from app.api.routers.ia_status import _cadena_groq
        from app.core.config import get_settings

        cfg = get_settings()
        assert _cadena_groq()[0] == cfg.groq_model, "el panel no muestra el primario real"
        assert not set(_cadena_groq()) & RETIRADOS

    def test_el_panel_no_repite_modelos(self):
        from app.api.routers.ia_status import _cadena_groq

        cadena = _cadena_groq()
        assert len(cadena) == len(set(cadena)), cadena


def test_ningun_archivo_usa_un_modelo_retirado_como_valor_de_respaldo():
    """19-08-2026. El panel de Diagnóstico tenía
    `os.getenv("GEMINI_MODEL", "gemini-2.0-flash")`. Como el .env del hospital
    no define esa variable, usaba el respaldo —un modelo retirado— e ignoraba
    la configuración. Cuarto valor copiado a mano que se desfasa el mismo día.
    """
    import ast

    for ruta in (
        RAIZ / "app" / "api" / "routers" / "diagnostico.py",
        RAIZ / "app" / "api" / "routers" / "ia_status.py",
        RAIZ / "app" / "api" / "routers" / "sistema.py",
        RAIZ / "app" / "services" / "glosa_service.py",
    ):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        textos = {
            n.value
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        malos = textos & RETIRADOS
        assert not malos, f"{ruta.name} usa como valor un modelo retirado: {malos}"
