"""Tests del detector de copia textual Gold (R-cerebro #7)."""
from __future__ import annotations

from app.services.detector_copia import (
    _ngramas,
    _normalizar,
    detectar_copia_gold,
    instruccion_anti_copia,
    similitud_jaccard,
)


class TestNormalizar:
    def test_vacio(self):
        assert _normalizar("") == ""

    def test_minusculas_a_mayusculas(self):
        assert _normalizar("hola mundo") == "HOLA MUNDO"

    def test_colapsa_espacios(self):
        assert _normalizar("  hola   \n\t mundo  ") == "HOLA MUNDO"

    def test_quita_puntuacion(self):
        # los signos se vuelven espacios y luego se colapsan
        out = _normalizar("¡hola, mundo!")
        assert out == "HOLA MUNDO"

    def test_preserva_tildes_y_n(self):
        assert _normalizar("camión año") == "CAMIÓN AÑO"


class TestNgramas:
    def test_texto_corto_devuelve_vacio(self):
        # Con n=5 y solo 3 palabras → set vacío
        assert _ngramas("una dos tres", n=5) == set()

    def test_genera_5gramas(self):
        t = "uno dos tres cuatro cinco seis siete"
        ngs = _ngramas(t, n=5)
        # 7 palabras, n=5 → 3 ngramas: [0..4], [1..5], [2..6]
        assert len(ngs) == 3
        assert "UNO DOS TRES CUATRO CINCO" in ngs

    def test_n_pequeno(self):
        ngs = _ngramas("uno dos tres", n=2)
        assert "UNO DOS" in ngs
        assert "DOS TRES" in ngs


class TestSimilitudJaccard:
    def test_textos_vacios(self):
        assert similitud_jaccard("", "") == 0.0
        assert similitud_jaccard("hola", "") == 0.0

    def test_identicos(self):
        t = "uno dos tres cuatro cinco seis siete ocho nueve diez"
        assert similitud_jaccard(t, t, n=5) == 1.0

    def test_distintos(self):
        a = "uno dos tres cuatro cinco seis siete"
        b = "perro gato pajaro ratón vaca caballo cerdo"
        assert similitud_jaccard(a, b, n=5) == 0.0

    def test_parcial(self):
        # Comparten un buen tramo común
        a = "uno dos tres cuatro cinco seis siete ocho"
        b = "uno dos tres cuatro cinco nueve diez once"
        s = similitud_jaccard(a, b, n=5)
        assert 0.0 < s < 1.0

    def test_textos_demasiado_cortos_para_n(self):
        # Con n=5 y palabras < 5 → 0.0
        assert similitud_jaccard("uno dos", "uno dos", n=5) == 0.0


class TestDetectarCopia:
    def _ejemplo(self, texto, id_=1, fuente="GOLD"):
        return {"argumento": texto, "id": id_, "fuente": fuente}

    def test_sin_dictamen_o_ejemplos(self):
        assert detectar_copia_gold("", []) is None
        assert detectar_copia_gold("texto", []) is None
        assert detectar_copia_gold("", [self._ejemplo("x")]) is None

    def test_dictamen_distinto(self):
        d = "uno dos tres cuatro cinco seis siete ocho nueve"
        ej = self._ejemplo(
            "perro gato pajaro raton vaca caballo cerdo oveja gallina"
        )
        assert detectar_copia_gold(d, [ej], umbral=0.55) is None

    def test_dictamen_copiado_supera_umbral(self):
        comun = (
            "ESE HUS NO ACEPTA LA GLOSA POR TARIFA APLICADA "
            "DE CONFORMIDAD CON EL CONTRATO VIGENTE Y LA "
            "RESOLUCION 2284 DE 2023 QUE REGULA EL MANUAL "
            "UNICO DE GLOSAS DEVOLUCIONES Y RESPUESTAS"
        )
        ej = self._ejemplo(comun, id_=42, fuente="GOLD")
        det = detectar_copia_gold(comun, [ej], umbral=0.55)
        assert det is not None
        assert det["similitud"] >= 0.55
        assert det["ejemplo_id"] == 42
        assert det["fuente"] == "GOLD"

    def test_devuelve_peor_caso(self):
        # Dos ejemplos: uno con coincidencia alta, otro baja
        comun = (
            "ESE HUS NO ACEPTA LA GLOSA POR TARIFA APLICADA "
            "DE CONFORMIDAD CON EL CONTRATO VIGENTE Y LA "
            "RESOLUCION 2284 DE 2023 QUE REGULA EL MANUAL"
        )
        ej_alto = self._ejemplo(comun, id_=1, fuente="GOLD")
        ej_bajo = self._ejemplo(
            "perro gato pajaro raton vaca caballo cerdo oveja",
            id_=2,
            fuente="HISTORICO",
        )
        det = detectar_copia_gold(
            comun, [ej_bajo, ej_alto], umbral=0.55,
        )
        assert det is not None
        assert det["ejemplo_id"] == 1


class TestInstruccionAntiCopia:
    def test_sin_deteccion_devuelve_vacio(self):
        assert instruccion_anti_copia({}) == ""
        assert instruccion_anti_copia(None) == ""  # type: ignore[arg-type]

    def test_con_deteccion_genera_bloque(self):
        det = {"similitud": 0.78, "ejemplo_id": 7, "fuente": "GOLD"}
        b = instruccion_anti_copia(det)
        assert "DETECCIÓN DE COPIA TEXTUAL" in b
        assert "78%" in b
        assert "GOLD" in b
        assert "id=7" in b
        assert "REGENERA" in b
