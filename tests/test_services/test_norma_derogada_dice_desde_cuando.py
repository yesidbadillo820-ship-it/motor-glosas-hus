"""Una norma derogada citada sin decir desde cuando.

Lote de recepcion del 25-08-2026: 21 de los 117 dictamenes citaron la
Resolucion 2275 de 2023 como si siguiera vigente. La derogo la Resolucion
948 de 2026 el 14 de mayo.

PERO citarla no siempre esta mal: para un servicio prestado ANTES del
14-05-2026 la norma aplicable ES la 2275, y cambiarla por la 948 seria
meterle al dictamen una norma que no regia ese dia — el error contrario, y
mas grave.

Ademas la fecha del servicio no se sabe con certeza: el formulario trae la
de RADICACION de la factura, que es posterior a la atencion.

Por eso la red NO reemplaza: COMPLETA. El dictamen dice cual rige hoy y
desde cuando, asi la cita es correcta cualquiera que sea la fecha del
servicio y la entidad no puede rebatirla con «esa resolucion esta derogada».
"""

from app.services.citation_verifier import _norma_sucesora_ya_nombrada, verificar_citas
from app.services.glosa_service import _completar_norma_derogada


class TestCompletaLaCita:
    def test_agrega_la_regla_de_fecha(self):
        texto = "LA FACTURA CUMPLE LA RESOLUCIÓN 2275 DE 2023 (FEV EN EL SECTOR SALUD)."
        salida = _completar_norma_derogada(texto)
        assert "14 DE MAYO DE 2026" in salida
        assert "RESOLUCIÓN 948 DE 2026" in salida

    def test_no_borra_la_cita_original(self):
        texto = "LA FACTURA CUMPLE LA RESOLUCIÓN 2275 DE 2023."
        salida = _completar_norma_derogada(texto)
        assert "RESOLUCIÓN 2275 DE 2023" in salida, (
            "para un servicio anterior a la derogatoria esa ES la norma aplicable"
        )

    def test_reconoce_la_cita_con_barra(self):
        texto = "CONFORME A LA RESOLUCION 2275/2023 LA FACTURA ES VÁLIDA."
        assert "948 DE 2026" in _completar_norma_derogada(texto).upper()

    def test_la_aclaracion_va_despues_del_parentesis_propio_de_la_cita(self):
        """Asi salio en el lote: «RESOLUCION 2275 DE 2023 (FEV EN EL SECTOR
        SALUD)». Dos parentesis pegados se leen mal."""
        texto = "CUMPLE (III) RESOLUCIÓN 2275 DE 2023 (FEV EN EL SECTOR SALUD); (IV) RIPS."
        salida = _completar_norma_derogada(texto)
        assert "(FEV EN EL SECTOR SALUD) (VIGENTE PARA SERVICIOS" in salida
        assert ") (" in salida and ")(" not in salida

    def test_solo_aclara_la_primera_mencion(self):
        texto = (
            "LA RESOLUCIÓN 2275 DE 2023 EXIGE EL CUV. LA MISMA RESOLUCIÓN 2275 DE 2023 "
            "REGULA EL ANEXO TÉCNICO."
        )
        salida = _completar_norma_derogada(texto)
        assert salida.count("14 DE MAYO DE 2026") == 1, (
            "repetir la aclaración en cada mención vuelve el dictamen ilegible"
        )


class TestNoMolestaCuandoNoHaceFalta:
    def test_si_el_dictamen_ya_nombra_la_948_no_toca_nada(self):
        texto = "CONFORME A LA RESOLUCIÓN 948 DE 2026 Y A LA RESOLUCIÓN 2275 DE 2023."
        assert _completar_norma_derogada(texto) == texto

    def test_no_toca_otras_resoluciones_de_2023(self):
        texto = "SEGÚN LA RESOLUCIÓN 2284 DE 2023 Y LA RESOLUCIÓN 2335 DE 2023."
        assert _completar_norma_derogada(texto) == texto

    def test_dictamen_sin_la_norma_sale_identico(self):
        texto = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        assert _completar_norma_derogada(texto) == texto

    def test_texto_vacio_no_rompe(self):
        assert _completar_norma_derogada("") == ""
        assert _completar_norma_derogada(None) is None


class TestElAvisoDejaDeSonarCuandoYaNoHaceFalta:
    """21 avisos por lo mismo en un solo lote y el gestor deja de leerlos.

    Si el dictamen ya dice cual norma reemplazo a la derogada y desde
    cuando, el aviso solo hace ruido.
    """

    NOTA = (
        "la derogó la Resolución 948 del 14 de mayo de 2026, que rige desde su "
        "expedición (junto con las Resoluciones 558 y 1884 de 2024)"
    )

    def test_reconoce_la_sucesora_nombrada(self):
        assert _norma_sucesora_ya_nombrada(self.NOTA, "RIGE LA RESOLUCIÓN 948 DE 2026")

    def test_no_se_conforma_con_otra_norma_de_la_misma_frase(self):
        """En la nota tambien aparecen «558 y 1884 de 2024». Nombrarlas NO
        es nombrar la sucesora: el aviso debe seguir sonando."""
        assert not _norma_sucesora_ya_nombrada(self.NOTA, "SEGÚN LA RESOLUCIÓN 1884 DE 2024")

    def test_sin_nota_de_derogatoria_no_calla_el_aviso(self):
        assert not _norma_sucesora_ya_nombrada("", "RESOLUCIÓN 948 DE 2026")
        assert not _norma_sucesora_ya_nombrada(self.NOTA, "")

    def test_el_dictamen_completado_ya_no_dispara_el_aviso(self):
        crudo = (
            "ESE HUS NO ACEPTA GLOSA, DADO QUE LA FACTURA CUMPLE LA "
            "RESOLUCIÓN 2275 DE 2023 (FEV EN EL SECTOR SALUD)."
        )
        antes = [i["tipo"] for i in verificar_citas(crudo).get("issues", [])]
        assert "NORMA_DEROGADA" in antes
        despues = [
            i["tipo"] for i in verificar_citas(_completar_norma_derogada(crudo)).get("issues", [])
        ]
        assert "NORMA_DEROGADA" not in despues

    def test_el_dictamen_sin_completar_si_dispara_el_aviso(self):
        """La red no puede tapar el problema: si el dictamen NO dice desde
        cuando, el gestor tiene que enterarse."""
        crudo = "LA FACTURA CUMPLE LA RESOLUCIÓN 2275 DE 2023."
        assert "NORMA_DEROGADA" in [i["tipo"] for i in verificar_citas(crudo).get("issues", [])]
