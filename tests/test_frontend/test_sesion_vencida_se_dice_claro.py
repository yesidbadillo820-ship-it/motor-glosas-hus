"""La sesión vencida se dice como es, no con el texto del servidor.

09-09-2026. El auditor abrió el motor a las 8:15 de la mañana con la sesión
de la noche anterior —el token dura 8 horas— y en la pantalla de Usuarios le
salió un recuadro rojo:

    Error
    Credenciales inválidas o token expirado

Ese es el `detail` que manda FastAPI, escrito para un programador. La
pantalla YA tenía el manejador bueno (`manejarSesionExpirada`, que dice «Tu
sesión venció — vuelve a iniciar sesión» y devuelve al login), pero solo lo
llamaban unas pocas de las llamadas: hay 173 sitios que muestran errores y
cada uno decidía por su cuenta si distinguir un 401.

La red va en el envoltorio global de `fetch` —el mismo que ya existía para
los 403— porque es el único punto por el que pasan todas.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")


def _envoltorio() -> str:
    """El cuerpo del envoltorio global de fetch."""
    i = HTML.index("function envolverFetchPara403(")
    return HTML[i : HTML.index("function _avisar403(", i)]


class TestElEnvoltorioAtrapaEl401:
    def test_mira_el_401(self):
        assert "res.status === 401" in _envoltorio()

    def test_llama_al_manejador_bueno(self):
        cuerpo = _envoltorio()
        i = cuerpo.index("res.status === 401")
        assert "manejarSesionExpirada()" in cuerpo[i : i + 900], (
            "el 401 tiene que ir al manejador que ya existe, no a un mensaje nuevo"
        )

    def test_va_antes_del_403_y_no_lo_pisa(self):
        cuerpo = _envoltorio()
        assert cuerpo.index("res.status === 401") < cuerpo.index("res.status === 403")
        assert "_avisar403" in cuerpo, "el aviso de permisos sigue en su sitio"

    def test_el_manejador_sigue_existiendo(self):
        assert "function manejarSesionExpirada(" in HTML
        i = HTML.index("function manejarSesionExpirada(")
        cuerpo = HTML[i : i + 700]
        assert "Sesión expirada" in cuerpo and "logout()" in cuerpo

    def test_no_avisa_si_ya_no_hay_sesion(self):
        """Sin token guardado no hay nada que haya vencido."""
        i = HTML.index("function manejarSesionExpirada(")
        assert "hus_token" in HTML[i : i + 400]

    def test_avisa_una_sola_vez(self):
        """Con varios sondeos de fondo, un aviso — no diez."""
        i = HTML.index("function manejarSesionExpirada(")
        assert "_sesion401Detectada" in HTML[i : i + 400]


class TestElLoginNoEsUnaSesionVencida:
    def test_el_token_queda_excluido(self):
        """`/token` contesta 401 con la contraseña mala: eso no es una
        sesión vencida y su propia pantalla ya lo explica."""
        cuerpo = _envoltorio()
        i = cuerpo.index("res.status === 401")
        trozo = cuerpo[i : i + 900]
        assert "/token" in trozo, "sin la excepción, equivocarse de clave sacaría al login"

    def test_se_compara_la_ruta_sin_los_parametros(self):
        cuerpo = _envoltorio()
        i = cuerpo.index("res.status === 401")
        assert "split('?')[0]" in cuerpo[i : i + 900]
