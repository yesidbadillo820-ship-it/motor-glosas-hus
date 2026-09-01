"""El motor no puede ofrecer una norma que él mismo no tiene.

QUÉ PASÓ (25-08-2026). Los prompts del motor le ofrecían a la IA 24 normas que
NO estaban en el corpus con que él mismo revisa las citas. O sea: le pedíamos
que las citara, la IA obedecía, y el revisor las marcaba en rojo como «norma
inexistente» sobre un dictamen que podía estar perfectamente bien. Se comprobó
una por una: las 21 que tenían forma de norma producían alarma de severidad
ALTA, incluidas leyes que existen sin discusión, como el Código General del
Proceso o la Ley 776 de 2002 de riesgos laborales.

Al verificarlas contra fuente oficial aparecieron dos grupos:

  · DOCE eran reales y estaban bien citadas: se cargaron al corpus con su
    contenido verificado.
  · OCHO las nombraba mal el motor, y TRES de esas NO EXISTEN:
      – «Acuerdo 002 de 2010 USPEC» (el modelo de atención de PPL lo fija el
        Decreto 1142 de 2016, que sí es real).
      – «Decreto 1760 de 2022» (hay un Decreto 1760 de 1990, de otro tema).
      – «Resolución 5853 de 2003» del bloque FOMAG.
    Y de las otras cinco: la 5159 de 2015 es RESOLUCIÓN y no decreto; la 506 de
    2021 es de MinSalud y no de la DIAN; la «Resolución 2284 de 2024» es de
    2023; la «Resolución 1604 de 2022» es un DECRETO sobre instituciones
    educativas de las cajas de compensación, no de habilitación; y la
    Resolución 010 de 2018 es de la DIAN y no dice nada del pago de migrantes
    por el ente territorial, que era para lo que se citaba.

QUÉ CUIDA ESTA PRUEBA. Que no vuelva a haber normas ofrecidas y no cargadas. Es
un invariante sencillo y comprobable: si el motor se lo pide a la IA, el
sistema tiene que poder respaldarlo.
"""

import io
import re

import pytest

from app.services.citation_verifier import _buscar_clave_norma
from app.services.normativa_completa import _TODAS_LAS_NORMAS as CORPUS

# Los textos con que el motor arma o defiende un dictamen.
TEXTOS_DEL_MOTOR = [
    "app/services/glosa_ia_prompts.py",
    "app/services/clausulas_anti_rebatimiento.py",
    "app/services/salud_total_service.py",
    "app/services/defensa_clinica.py",
    "app/services/multi_agente.py",
    "app/services/conciliador_ia.py",
    "app/services/analizador_motivo_eps.py",
    "app/services/excel_radicable.py",
]

_CITA = re.compile(
    r"\b(Ley|Decreto|Resoluci[óo]n|Circular|Acuerdo)\s+(?:N[oº°.]?\s*)?(\d{1,5})"
    r"\s*(?:de\s+|/)\s*(\d{4})",
    re.IGNORECASE,
)

# «Decreto-Ley 1295 de 1994» y «Decreto-Ley 1795 de 2000» se nombran bien: la
# expresión de arriba les lee la cola («Ley 1295 de 1994») y cree que falta una
# ley que no existe. El revisor de citas sí las entiende — se comprueba abajo.
COMPUESTAS = {("ley", "1295", "1994"), ("ley", "1795", "2000")}


def _normas_ofrecidas(ruta: str):
    contenido = io.open(ruta, encoding="utf-8").read()
    for i, renglon in enumerate(contenido.split("\n")):
        if renglon.strip().startswith("#"):
            continue  # los comentarios explican, no le ofrecen nada a la IA
        for m in _CITA.finditer(renglon):
            tipo, numero, anio = m.groups()
            clave = (tipo[:3].lower(), numero.lstrip("0") or numero, anio)
            if clave in COMPUESTAS:
                continue
            yield tipo, numero, anio, i + 1, renglon.strip()


class TestTodaNormaOfrecidaEstaEnElCorpus:
    @pytest.mark.parametrize("ruta", TEXTOS_DEL_MOTOR)
    def test_el_motor_puede_respaldar_lo_que_pide_citar(self, ruta):
        faltantes = []
        for tipo, numero, anio, linea, texto in _normas_ofrecidas(ruta):
            if not _buscar_clave_norma(tipo[:3].lower(), numero, anio, CORPUS):
                faltantes.append(f"{tipo} {numero} de {anio} (línea {linea}): {texto[:70]}")
        assert not faltantes, (
            f"{ruta} le ofrece a la IA normas que el corpus no tiene, así que citarlas "
            f"produce una alarma roja sobre un dictamen que puede estar bien: {faltantes}"
        )

    def test_las_compuestas_si_las_entiende_el_revisor(self):
        """Los decretos-leyes se nombran bien; es la prueba la que debe entenderlos."""
        from app.services.citation_verifier import verificar_citas

        for cita in ("DECRETO-LEY 1295 DE 1994", "DECRETO-LEY 1795 DE 2000"):
            assert verificar_citas(f"CONFORME AL {cita} SE RESPONDE.")["issues"] == []


class TestLasTresQueNoExistenNoVuelven:
    @pytest.mark.parametrize(
        "inventada",
        ["Acuerdo 002 de 2010", "Decreto 1760 de 2022", "Resolución 5853 de 2003"],
    )
    def test_ningun_texto_del_motor_las_nombra(self, inventada):
        numero = inventada.split()[1]
        anio = inventada.split()[-1]
        for ruta in TEXTOS_DEL_MOTOR:
            for renglon in io.open(ruta, encoding="utf-8").read().split("\n"):
                if renglon.strip().startswith("#"):
                    continue
                assert not (
                    numero in renglon
                    and anio in renglon
                    and inventada.split()[0][:3].lower() in renglon.lower()
                ), f"{ruta} volvió a nombrar «{inventada}», que no existe: {renglon.strip()[:80]}"


class TestLasDoceQueSiExistenQuedaronCargadas:
    @pytest.mark.parametrize(
        "clave",
        [
            "LEY 1564 DE 2012",
            "LEY 1618 DE 2013",
            "LEY 2277 DE 2022",
            "LEY 776 DE 2002",
            "LEY 789 DE 2002",
            "DECRETO 1477 DE 2014",
            "DECRETO 1352 DE 2013",
            "DECRETO 1142 DE 2016",
            "DECRETO 2462 DE 2013",
            "RESOLUCION 1403 DE 2007",
            "RESOLUCION 3539 DE 2019",
            "ACUERDO 080 DE 2022 CSSMP",
            "RESOLUCION 506 DE 2021",
        ],
    )
    def test_esta_en_el_corpus_y_verificada(self, clave):
        assert clave in CORPUS, f"{clave} no quedó cargada"
        assert CORPUS[clave].get("verificada"), f"{clave} quedó sin marca de verificación"
