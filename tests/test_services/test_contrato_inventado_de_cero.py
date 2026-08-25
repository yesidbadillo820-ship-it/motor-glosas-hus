"""Un número de contrato que no existe en ninguna parte.

OT-027 · 06-08-2026. La red de contratos ajenos —que existe desde junio—
solo caza los números CONOCIDOS que pertenecen a otra entidad: compara
contra el catálogo de contrato→dueña. Un número inventado de cero, que no
está en el catálogo de nadie, pasaba derecho hasta el documento radicado.

Es el mismo riesgo que la cláusula inventada de OT-001, y peor: la entidad
busca ese contrato en su sistema, no lo encuentra, y todo el dictamen queda
bajo sospecha sin haber discutido el fondo.

El Quality Gate tiene `check_contratos_no_fabricados`, pero está apagado por
defecto, así que en el motor del hospital no protege nada.

Se conserva el número cuando está en el catálogo (de quien sea: si es de
otra entidad, esa es tarea de la red anterior, que corre antes), cuando lo
citó la propia entidad en su glosa, o cuando aparece en el contrato
registrado de ese pagador.
"""

from __future__ import annotations

from app.services.glosa_service import _neutralizar_contratos_inventados as _limpiar

GLOSA_CON_CONTRATO = (
    "TA0801 - La tarifa facturada no corresponde a lo pactado en el contrato "
    "CTR-2025-HUS-777 suscrito entre las partes."
)


class TestElContratoInventado:
    def test_un_numero_que_no_existe_se_cae(self):
        d = "SEGUN EL CONTRATO XYZ-9999-2030-ABC LA TARIFA ES SOAT."
        out = _limpiar(d, "COOSALUD")
        assert "XYZ-9999-2030-ABC" not in out
        assert "EL CONTRATO VIGENTE ENTRE LAS PARTES" in out

    def test_tambien_cuando_dice_acta(self):
        d = "SEGUN EL ACTA GI-00-0000-9999 SE ACORDO EL PAGO."
        assert "GI-00-0000-9999" not in _limpiar(d, "COOSALUD")

    def test_tambien_con_la_palabra_numero(self):
        d = "SEGUN EL CONTRATO No. QQQ-8888-7777 LA TARIFA ES SOAT."
        assert "QQQ-8888-7777" not in _limpiar(d, "COOSALUD")

    def test_varios_en_el_mismo_dictamen(self):
        d = "EL CONTRATO AAA-1111-2222 Y EL CONTRATO BBB-3333-4444 LO PACTAN."
        out = _limpiar(d, "COOSALUD")
        assert "AAA-1111-2222" not in out
        assert "BBB-3333-4444" not in out


class TestLoQueSiExisteSeConserva:
    def test_el_contrato_propio_del_catalogo(self):
        d = "SEGUN EL CONTRATO 68001C00060340-24 LA TARIFA ES SOAT -15%."
        assert _limpiar(d, "COOSALUD") == d

    def test_el_contrato_de_otra_entidad_lo_maneja_la_red_anterior(self):
        """No es tarea de esta red: la de contratos ajenos corre antes y lo
        sustituye. Si esta lo tocara, se pisarían."""
        d = "SEGUN EL CONTRATO S-13-1-03-1-04958."
        assert _limpiar(d, "COOSALUD") == d

    def test_el_que_cito_la_propia_entidad(self):
        """Si el número lo puso la entidad en su glosa, no es invención del
        motor: es el dato con el que hay que discutir."""
        d = "SEGUN EL CONTRATO CTR-2025-HUS-777 LA TARIFA ES SOAT."
        assert _limpiar(d, "COOSALUD", texto_glosa=GLOSA_CON_CONTRATO) == d

    def test_sin_ese_texto_el_mismo_numero_se_cae(self):
        d = "SEGUN EL CONTRATO CTR-2025-HUS-777 LA TARIFA ES SOAT."
        assert "CTR-2025-HUS-777" not in _limpiar(d, "COOSALUD")


class TestNoSeLlevaPorDelanteOtrosCodigos:
    def test_las_citas_de_normas(self):
        d = "CONFORME A LA SENTENCIA T-760/2008 Y LA RESOLUCION 2284/2023."
        assert _limpiar(d, "COOSALUD") == d

    def test_los_cups_con_sufijo_del_hus(self):
        d = "EL PROCEDIMIENTO 372301H Y EL 039001H1 FUERON PRESTADOS."
        assert _limpiar(d, "COOSALUD") == d

    def test_las_fechas(self):
        d = "LA FACTURA SE RADICO EL 2026-04-15 EN DEBIDA FORMA."
        assert _limpiar(d, "COOSALUD") == d

    def test_un_dictamen_sin_contratos(self):
        d = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        assert _limpiar(d, "COOSALUD") == d

    def test_texto_generico_sin_digitos(self):
        """ "EL CONTRATO VIGENTE" no es un número: no hay nada que verificar."""
        d = "SEGUN EL CONTRATO VIGENTE ENTRE LAS PARTES LA TARIFA ES SOAT."
        assert _limpiar(d, "COOSALUD") == d

    def test_texto_vacio(self):
        assert _limpiar("", "COOSALUD") == ""
        assert _limpiar(None, "COOSALUD") is None


class TestLaRedEstaEnchufada:
    def test_corre_despues_de_la_de_contratos_ajenos(self):
        """El orden importa: la de ajenos es más específica —sabe de quién
        es el número— y debe tener la primera palabra."""
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_neutralizar_contratos_inventados(" in src
        assert src.index("_neutralizar_contratos_ajenos(") < src.index(
            "_neutralizar_contratos_inventados("
        )

    def test_un_fallo_no_tumba_el_dictamen(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("_neutralizar_contratos_inventados(")
        assert "CONTRATO-INVENTADO" in src[i : i + 700]
