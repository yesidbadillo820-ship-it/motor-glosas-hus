"""El modelo escribe el argumento; el motor arma el dictamen.

01-09-2026 — refactor pedido por el auditor tras GL-149: «quítale el control
del ensamblaje». El renglón «Servicio objetado» y el bloque económico no son
redacción: son datos verificables. Ahora salen del catálogo CUPS y de la malla
contractual, no de lo que el modelo quiera escribir.
"""

import pytest

from app.services.glosa_service import _linea_servicio_determinista
from app.services.respuesta_ia_estructurada import (
    RespuestaIA,
    esquema_para_el_prompt,
    parsear_respuesta_ia,
)


class TestElRenglonDelServicioSaleDeLaBase:
    def test_cups_del_catalogo_trae_su_descripcion_oficial(self):
        r = _linea_servicio_determinista("902210", "lo que el modelo quiera", "", "CL4506")
        assert "HEMOGRAMA" in r
        assert "(CUPS 902210)" in r

    def test_cups_fuera_del_catalogo_no_se_imprime(self):
        """215601 sale de los PDF y NO figura en el catálogo oficial.

        Poner un código que la entidad no encuentra al cruzarlo es justo lo
        que le sirve para ratificar. El aviso de «revise el código» va aparte.
        """
        r = _linea_servicio_determinista("215601", "OSTEOSÍNTESIS DE FÉMUR", "", "CL4506")
        assert r == "OSTEOSÍNTESIS DE FÉMUR"
        assert "215601" not in r

    @pytest.mark.parametrize(
        "sufijo",
        ["- código CL4506", "(CL4506)", "[CL4506]", "ref. CL4506", "CL4506", "código CL4506"],
    )
    def test_la_causal_nunca_llega_al_renglon(self, sufijo: str):
        r = _linea_servicio_determinista("", f"OSTEOSÍNTESIS DE FÉMUR {sufijo}", "", "CL4506")
        assert r == "OSTEOSÍNTESIS DE FÉMUR"

    def test_sin_datos_no_inventa_un_servicio(self):
        assert _linea_servicio_determinista("", "", "", "CL4506") == ""

    def test_si_solo_queda_el_codigo_devuelve_vacio(self):
        """Mejor sin renglón que con un rótulo huérfano."""
        assert _linea_servicio_determinista("", "CL4506", "", "CL4506") == ""

    def test_codigo_de_glosa_raro_no_rompe(self):
        for basura in ("", "   ", "N/A", "902210"):
            r = _linea_servicio_determinista("", "OSTEOSÍNTESIS DE FÉMUR", "", basura)
            assert r == "OSTEOSÍNTESIS DE FÉMUR"


class TestElContratoDeSalidaDelModelo:
    def test_dos_campos_y_nada_mas(self):
        assert set(RespuestaIA.model_fields) == {"justificacion_clinica", "fundamentos_ley"}

    def test_el_hecho_clinico_va_antes_que_la_ley(self):
        r = RespuestaIA(
            justificacion_clinica="La nota operatoria del folio 1 registra conminución.",
            fundamentos_ley="Art. 17 Ley 1751/2015.",
        )
        arg = r.argumento()
        assert arg.index("nota operatoria") < arg.index("Ley 1751")

    def test_lee_el_json_limpio(self):
        r = parsear_respuesta_ia(
            '{"justificacion_clinica":"Folio 1: conminución.","fundamentos_ley":"Art. 17."}'
        )
        assert r and "Folio 1" in r.argumento()

    def test_lee_el_json_envuelto_en_comillas_de_bloque(self):
        r = parsear_respuesta_ia(
            'Aquí tienes:\n```json\n{"justificacion_clinica":"X","fundamentos_ley":"Y"}\n```'
        )
        assert r and r.argumento() == "X Y"

    def test_aplana_una_lista_de_parrafos(self):
        r = parsear_respuesta_ia('{"justificacion_clinica":["uno","dos"],"fundamentos_ley":"tres"}')
        assert r and r.argumento() == "uno dos tres"

    @pytest.mark.parametrize(
        "basura",
        [
            "",
            "   ",
            "esto no es json",
            '{"otra_cosa":1}',
            "[1,2,3]",
            '{"justificacion_clinica":""}',
        ],
    )
    def test_lo_que_no_sirve_devuelve_none(self, basura: str):
        """None NO es fatal: el motor sigue por el camino XML de siempre.

        Un modelo que un día devuelva mal el JSON no puede dejar sin dictamen
        al hospital.
        """
        assert parsear_respuesta_ia(basura) is None


class TestElEsquemaLeCierraLasPuertas:
    def test_le_prohibe_las_cifras_y_el_codigo(self):
        e = esquema_para_el_prompt()
        for prohibido in ("cifras", "tarifas", "UVB", "topes", "código de la glosa"):
            assert prohibido in e, prohibido

    def test_le_dice_quien_arma_lo_que_el_no_escribe(self):
        assert "los arma el motor con los datos de la base" in esquema_para_el_prompt()

    def test_le_prohibe_agregar_claves(self):
        assert "PROHIBIDO agregar claves" in esquema_para_el_prompt()


class TestLasRedesSIGUENHaciendoFalta:
    """El JSON restringe el sobre, no el contenido de un campo de texto.

    El auditor pidió borrar las redes de limpieza «porque el modelo no tendrá
    la capacidad física de imprimir el código». No es así: dentro de
    `justificacion_clinica` puede escribirlo igual — en GL-149 lo escribió en
    el cuerpo del argumento, no solo en el campo del servicio.
    """

    def test_el_codigo_puede_venir_dentro_del_campo_libre(self):
        r = parsear_respuesta_ia(
            '{"justificacion_clinica":"El procedimiento código CL4506 fue pertinente.",'
            '"fundamentos_ley":"Art. 17."}'
        )
        assert r is not None
        assert "CL4506" in r.argumento(), (
            "si esto falla, el contrato empezó a filtrar contenido y habría que "
            "revisar si las redes siguen haciendo falta"
        )

    def test_por_eso_la_red_del_cuerpo_sigue_viva(self):
        from app.services.glosa_service import _quitar_causal_propia_del_cuerpo

        assert (
            _quitar_causal_propia_del_cuerpo(
                "El procedimiento código CL4506 fue pertinente.", "CL4506"
            )
            == "El procedimiento fue pertinente."
        )


class TestLaBanderaYLaCaidaSuave:
    """La salida JSON es una mejora, no un punto único de falla.

    01-09-2026. Si un día el modelo devuelve mal las llaves, el hospital NO
    puede quedarse sin dictamen: se sigue por el camino XML de siempre.
    """

    def test_la_bandera_nace_apagada(self):
        from app.core.config import Settings

        assert Settings.model_fields["glosa_salida_json"].default is False, (
            "la bandera no puede nacer encendida: cambiaría el comportamiento "
            "de producción sin que nadie lo decida"
        )

    def test_el_motor_lee_la_bandera_una_sola_vez(self):
        import io as _io

        motor = _io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert motor.count("_flag_json = bool(") == 1

    def test_el_motor_cae_al_xml_cuando_el_json_no_sirve(self):
        import io as _io

        motor = _io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "if not arg_ia:" in motor
        i = motor.index("if not arg_ia:")
        assert 'self._xml("argumento", res_ia, "")' in motor[i : i + 200]

    def test_deja_rastro_en_el_log_cuando_cae(self):
        import io as _io

        motor = _io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "no devolvió JSON utilizable" in motor


class TestElValidadorEntiendeLasDosFormas:
    """Si solo entendiera XML, rechazaría un dictamen bueno por un defecto
    que no existe, y mandaría al gestor a buscar un fantasma."""

    def test_sigue_leyendo_el_xml_de_siempre(self):
        from app.services.validador_dictamen import _extraer_argumento_xml

        assert _extraer_argumento_xml("<argumento>texto viejo</argumento>") == "texto viejo"

    def test_ahora_tambien_lee_el_json(self):
        from app.services.validador_dictamen import _extraer_argumento_xml

        r = _extraer_argumento_xml(
            '{"justificacion_clinica":"Folio 1: conminución.","fundamentos_ley":"Art. 17."}'
        )
        assert r == "Folio 1: conminución. Art. 17."

    def test_lo_que_no_es_ninguna_de_las_dos_sigue_siendo_none(self):
        from app.services.validador_dictamen import _extraer_argumento_xml

        assert _extraer_argumento_xml("cualquier cosa") is None
        assert _extraer_argumento_xml("") is None

    def test_el_xml_manda_cuando_vienen_los_dos(self):
        """dictamen_directo produce XML: ese camino no puede cambiar."""
        from app.services.validador_dictamen import _extraer_argumento_xml

        mixto = '<argumento>el del XML</argumento> {"justificacion_clinica":"el del JSON"}'
        assert _extraer_argumento_xml(mixto) == "el del XML"
