"""Ninguna sentencia puede decir en el sistema algo que la sentencia no dice.

QUÉ PASÓ (24-08-2026). La segunda auditoría independiente encontró que el
dictamen GL-205 invocaba la Sentencia T-478 de 1995 para defender la autonomía
médica, y que esa sentencia trata de otra cosa. Al revisar la base de
conocimiento del sistema apareció algo peor que un caso suelto: de las doce
sentencias que el sistema guardaba con CITA LITERAL —el texto entrecomillado
que se copia tal cual al dictamen que se radica—, siete decían un tema que no
es el suyo. Verificadas una por una contra la relatoría de la Corte
Constitucional ese mismo día:

  · T-478/1995  — el sistema decía «autonomía médica»; es seguridad social y
    tratamiento asilar de personas con discapacidad psíquica.
  · T-1025/2002 — decía «urgencias sin autorización previa»; es consentimiento
    informado en cirugía de asignación de sexo en menores intersexuales.
  · T-121/2015  — decía «las Guías de Práctica Clínica son recomendativas»; es
    la autorización de dos cirugías a un menor con epispadias.
  · T-235/1998  — decía «historia clínica como prueba»; es participación
    política en elecciones universitarias. Ni siquiera es de salud.
  · SU-480/1997 — decía «atención inicial de urgencias»; es el suministro de
    medicamentos fuera del POS a pacientes con VIH.
  · T-642/2008  — decía «flujo de recursos y pago oportuno a las IPS»; es el
    transporte y alojamiento de un menor para su tratamiento.
  · T-053/2009  — decía «inadmisibilidad de glosas injustificadas»; es el
    tratamiento integral de una persona con parálisis cerebral.

POR QUÉ ERA TAN GRAVE. El revisor de citas del motor contrasta lo que va
entrecomillado contra este mismo corpus. Una cita inventada guardada aquí se
certifica sola: el dictamen la copia, el revisor la encuentra, y el documento
sale con el sello «citas verificadas · 0 hallazgos». Así salió GL-205.

QUÉ SE HIZO. A esas siete se les puso el tema real y se les quitó la cita
literal inventada, y se las sacó de los textos que las ofrecían como munición.
Las defensas no perdieron nada: el anclaje correcto —Art. 17 de la Ley 1751 de
2015 para autonomía médica y Art. 168 de la Ley 100 para urgencias— ya iba al
lado en todos esos textos.

QUÉ CUIDA ESTA PRUEBA. Que ninguna sentencia vuelva a llevar cita literal sin
estar verificada, y que estas siete no reaparezcan diciendo lo que no dicen.
"""

import pytest

from app.services.normativa_completa import _TODAS_LAS_NORMAS

CAMPOS_DE_CITA_LITERAL = ("ratio_literal", "extracto_judicial")

SENTENCIAS = {
    clave: datos
    for clave, datos in _TODAS_LAS_NORMAS.items()
    if clave.upper().startswith(("SENTENCIA T-", "SENTENCIA SU-", "SENTENCIA C-"))
}


def _texto_completo(datos: dict) -> str:
    return " ".join(
        str(datos.get(campo) or "")
        for campo in ("titulo", "ratio", "aplica_a", "keywords", *CAMPOS_DE_CITA_LITERAL)
    ).lower()


class TestNingunaCitaLiteralSinVerificar:
    def test_hay_sentencias_que_revisar(self):
        assert len(SENTENCIAS) >= 25, "el corpus de jurisprudencia se encogió"

    @pytest.mark.parametrize("clave", sorted(SENTENCIAS))
    def test_si_lleva_cita_literal_esta_verificada(self, clave):
        """Una cita entrecomillada se copia tal cual al documento que se radica
        ante la EPS. Si nadie la contrastó contra el texto oficial, no puede
        estar aquí: el revisor de citas la daría por buena solo porque está."""
        datos = SENTENCIAS[clave]
        lleva_cita = any(datos.get(campo) for campo in CAMPOS_DE_CITA_LITERAL)
        if not lleva_cita:
            return
        assert datos.get("verificada"), (
            f"{clave} guarda una cita literal sin marca de verificación. "
            "Contrástela contra la relatoría de la Corte Constitucional y "
            "escriba la fecha en «verificada», o quite la cita literal."
        )


class TestLasSieteQueDecianOtraCosa:
    """Cada una con el tema que el sistema le atribuía y que NO es suyo."""

    @pytest.mark.parametrize(
        "clave,tema_que_no_es_suyo",
        [
            ("SENTENCIA T-478 DE 1995", "autonom"),
            ("SENTENCIA T-1025 DE 2002", "urgencia"),
            ("SENTENCIA T-121 DE 2015", "guías de práctica"),
            ("SENTENCIA T-235 DE 1998", "historia clínica"),
            ("SENTENCIA SU-480 DE 1997", "urgencia"),
            ("SENTENCIA T-642 DE 2008", "flujo de recursos"),
            ("SENTENCIA T-053 DE 2009", "glosas injustificadas"),
        ],
    )
    def test_ya_no_se_le_atribuye_el_tema_ajeno(self, clave, tema_que_no_es_suyo):
        datos = SENTENCIAS[clave]
        titulo = str(datos.get("titulo") or "").lower()
        assert tema_que_no_es_suyo not in titulo, (
            f"{clave} volvió a titularse con un tema que no es suyo"
        )

    @pytest.mark.parametrize(
        "clave",
        [
            "SENTENCIA T-478 DE 1995",
            "SENTENCIA T-1025 DE 2002",
            "SENTENCIA T-121 DE 2015",
            "SENTENCIA T-235 DE 1998",
            "SENTENCIA SU-480 DE 1997",
            "SENTENCIA T-642 DE 2008",
            "SENTENCIA T-053 DE 2009",
        ],
    )
    def test_ya_no_llevan_la_cita_literal_inventada(self, clave):
        datos = SENTENCIAS[clave]
        for campo in CAMPOS_DE_CITA_LITERAL:
            assert not datos.get(campo), f"{clave} volvió a traer {campo} inventado"


class TestElMotorYaNoLasOfreceComoMunicion:
    """Estaban tejidas en los textos que el motor usa para argumentar."""

    RUTAS = [
        "app/services/glosa_ia_prompts.py",
        "app/services/clausulas_anti_rebatimiento.py",
        "app/services/salud_total_service.py",
        "app/services/multi_agente.py",
        "app/services/conciliador_ia.py",
        "app/services/analizador_motivo_eps.py",
        "app/services/predictor_glosas.py",
    ]

    @pytest.mark.parametrize("ruta", RUTAS)
    def test_ningun_texto_del_motor_cita_las_dos_mas_usadas(self, ruta):
        import io

        contenido = io.open(ruta, encoding="utf-8").read()
        # La lista de DESCARTE sí puede nombrarlas: ahí no se ofrecen, se
        # tiran. Es un filtro que sigue en pie por si alguna volviera a
        # colarse en el contexto por otro camino.
        dentro_del_filtro = False
        renglones_malos = []
        for renglon in contenido.split("\n"):
            if renglon.startswith("_NORMAS_DE_AUTORIZACION"):
                dentro_del_filtro = True
            elif dentro_del_filtro and renglon.startswith("}"):
                dentro_del_filtro = False
            if dentro_del_filtro or renglon.strip().startswith("#"):
                continue
            if "T-478" in renglon or "T-1025" in renglon:
                renglones_malos.append(renglon.strip())
        assert not renglones_malos, (
            f"{ruta} volvió a citar T-478/1995 o T-1025/2002: {renglones_malos[:2]}"
        )

    def test_el_anclaje_correcto_sigue_en_pie(self):
        """Quitarlas no podía dejar las defensas sin fundamento."""
        import io

        prompts = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()
        assert "Art. 17 Ley 1751/2015" in prompts, "se perdió el anclaje de autonomía médica"
        assert "Art. 168 Ley 100/1993" in prompts, "se perdió el anclaje de urgencias"


class TestNoSeCitaJurisprudenciaSinVerificar:
    """Regla general, más allá de las siete de aquel día.

    Tres sentencias (T-313/2007, T-050/2017 y T-134/2022) no se pudieron abrir
    en el sitio de la Corte: la página las sirve por JavaScript y devuelve solo
    el encabezado. Quedaron marcadas como NO verificadas y sin cita literal.

    Mientras no estén verificadas no pueden ir en el texto que se radica ante la
    EPS. Con siete de diez verificadas resultando equivocadas, dar por buena una
    que nadie contrastó sería repetir el error a propósito. La T-313/2007 sí
    estaba en una cláusula armada y en el prompt: se le quitó el número y quedó
    la doctrina con su anclaje verificable, la Resolución 2284 de 2023.
    """

    TEXTOS_QUE_ARGUMENTAN = [
        "app/services/glosa_ia_prompts.py",
        "app/services/clausulas_anti_rebatimiento.py",
        "app/services/salud_total_service.py",
        "app/services/multi_agente.py",
        "app/services/conciliador_ia.py",
        "app/services/analizador_motivo_eps.py",
        "app/services/predictor_glosas.py",
        "app/services/normativa_grafo.py",
    ]

    @staticmethod
    def _numeros_sin_verificar() -> set:
        """Ej. {'T-313/2007'} → cómo se escriben en el texto del motor."""
        sin_verificar = set()
        for clave, datos in SENTENCIAS.items():
            # Solo las que SE REVISARON y no se pudieron confirmar. Una entrada
            # sin la marca todavía no se ha mirado, que es distinto: acusarla
            # aquí sería tratar «no revisada» como «falsa», y eso no es lo que
            # se sabe. A medida que se verifiquen, cada una queda con su fecha
            # (si se confirma) o con False (si no se pudo abrir el texto).
            if datos.get("verificada") is not False:
                continue
            # "SENTENCIA T-313 DE 2007" → "T-313/2007" y "T-313"
            partes = clave.replace("SENTENCIA ", "").split(" DE ")
            if len(partes) == 2:
                sin_verificar.add(partes[0].strip())
        return sin_verificar

    def test_hay_tres_sin_verificar_y_estan_marcadas(self):
        assert self._numeros_sin_verificar() >= {"T-313", "T-050", "T-134"}

    @pytest.mark.parametrize("ruta", TEXTOS_QUE_ARGUMENTAN)
    def test_ningun_texto_del_motor_cita_una_sin_verificar(self, ruta):
        import io

        contenido = io.open(ruta, encoding="utf-8").read()
        malos = []
        for numero in self._numeros_sin_verificar():
            for renglon in contenido.split("\n"):
                if renglon.strip().startswith("#"):
                    continue
                if numero in renglon:
                    malos.append(f"{numero}: {renglon.strip()[:90]}")
        assert not malos, (
            f"{ruta} cita jurisprudencia que nadie verificó contra el texto "
            f"oficial: {malos[:3]}. Verifíquela y marque «verificada» en el "
            "corpus, o quite el número y deje la doctrina con su norma."
        )
