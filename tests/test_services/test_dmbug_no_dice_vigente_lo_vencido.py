"""El texto canonico del Dispensario no puede contradecirse a si mismo.

Caso real 25-08-2026. En el lote de recepcion del dia salieron 14 respuestas
al Dispensario Medico Bucaramanga que decian, en la misma frase:

    "ENTRE LAS PARTES SE ENCUENTRA SUSCRITO Y VIGENTE EL CONTRATO
     INTERADMINISTRATIVO No. 440-DIGSA/DMBUG-2025, CON PLAZO HASTA
     30/07/2026"

Ese dia era 25 de agosto de 2026: el plazo se habia cumplido 26 dias antes.
La entidad lee las dos mitades de la frase y tumba la respuesta sin discutir
el fondo. Lo que era cierto —que el contrato regia CUANDO SE PRESTO EL
SERVICIO— hay que decirlo asi.
"""

from datetime import date

from app.services.glosa_service import (
    TEXTO_DMBUG_TARIFAS,
    _dmbug_cubierto_por_el_contrato,
    _item_del_anexo_dmbug,
)


class TestElTextoNoSeContradice:
    def test_no_afirma_vigencia_en_presente(self):
        assert "SE ENCUENTRA SUSCRITO Y VIGENTE" not in TEXTO_DMBUG_TARIFAS, (
            "afirmar vigencia HOY junto a un plazo ya cumplido tumba la respuesta"
        )

    def test_ancla_la_vigencia_a_la_fecha_de_la_prestacion(self):
        assert "VIGENTE A LA FECHA DE PRESTACIÓN DE LOS SERVICIOS FACTURADOS" in (
            TEXTO_DMBUG_TARIFAS
        )

    def test_el_argumento_del_decreto_2423_tambien_queda_anclado(self):
        assert "HABIENDO CONTRATO VIGENTE A LA FECHA DE LA PRESTACIÓN" in TEXTO_DMBUG_TARIFAS
        assert "HABIENDO CONTRATO VIGENTE, NO PROCEDE" not in TEXTO_DMBUG_TARIFAS

    def test_conserva_lo_que_el_auditor_pidio(self):
        """Lo pedido por el area en abr-2026 sigue intacto: numero, proceso,
        plazo, anexo y el argumento de agotamiento presupuestal."""
        for pedazo in (
            "440-DIGSA/DMBUG-2025",
            "PROCESO CD477",
            "30/07/2026",
            "7.141 ÍTEMS TARIFADOS",
            "AGOTAMIENTO PRESUPUESTAL",
            "ART. 71 DEL DECRETO 111/1996",
        ):
            assert pedazo in TEXTO_DMBUG_TARIFAS, pedazo


class TestLaCompuertaPorFecha:
    def test_servicio_dentro_del_plazo_usa_el_texto(self):
        assert _dmbug_cubierto_por_el_contrato(date(2026, 4, 15))
        assert _dmbug_cubierto_por_el_contrato(date(2026, 7, 30)), "el ultimo dia cuenta"

    def test_servicio_despues_del_plazo_no_usa_el_texto(self):
        assert not _dmbug_cubierto_por_el_contrato(date(2026, 8, 25)), (
            "fuera del plazo el argumento central del texto seria falso"
        )
        assert not _dmbug_cubierto_por_el_contrato(date(2026, 12, 1))

    def test_servicio_anterior_al_contrato_tampoco(self):
        assert not _dmbug_cubierto_por_el_contrato(date(2025, 6, 1))

    def test_sin_fecha_se_deja_pasar(self):
        """Una glosa siempre es de un servicio pasado y el contrato rigio casi
        todo el periodo. Bloquear por no saber la fecha le quitaria al
        hospital su mejor defensa."""
        assert _dmbug_cubierto_por_el_contrato(None)


class TestElAnexoSeProbaConElItem:
    """26-08-2026, decision del area.

    La tercera auditoria senalo que el texto canonico afirmaba que el servicio
    facturado «se encuentra» entre los 7.141 items del Anexo 1 — sin decir cual
    y sin verificarlo caso por caso. Puede ser cierta en general y falsa en un
    caso puntual, y nadie se entera hasta que la entidad lo revisa.

    Yesid pidio cambiarlo y que «trae los servicios». Asi quedo: la afirmacion
    en bloque sale del texto fijo, y el motor busca el codigo en el catalogo
    del contrato que cargo el coordinador. Si lo encuentra, lo nombra con su
    descripcion y su valor — eso es una prueba. Si no, no afirma nada.
    """

    def test_el_texto_ya_no_afirma_que_el_servicio_esta_en_el_anexo(self):
        assert "ENTRE LOS CUALES SE ENCUENTRA" not in TEXTO_DMBUG_TARIFAS

    def test_pero_conserva_el_dato_del_anexo_que_si_es_cierto(self):
        assert "7.141 ÍTEMS TARIFADOS" in TEXTO_DMBUG_TARIFAS

    def test_sin_codigo_no_se_afirma_nada(self):
        assert _item_del_anexo_dmbug(None) == ""
        assert _item_del_anexo_dmbug("") == ""

    def test_un_codigo_que_no_esta_en_el_catalogo_no_inventa_el_item(self):
        assert _item_del_anexo_dmbug("999999") == ""

    def test_el_hueco_donde_se_inserta_sigue_existiendo(self):
        """El motor inserta el ítem justo después de esta frase; si alguien la
        cambia, la inserción deja de funcionar en silencio."""
        assert "7.141 ÍTEMS TARIFADOS." in TEXTO_DMBUG_TARIFAS
