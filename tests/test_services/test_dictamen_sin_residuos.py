"""Residuos que quedaban impresos en el documento que se radica.

Pruebas reales del 06-08-2026 en el motor del hospital:

  OT-017 · NUEVA EPS FA0201 — «...SE RECHAZA LA GLOSA. "" SE SOLICITA EL
  LEVANTAMIENTO». Los sanitizers vacían el contenido de una cita inventada y
  los signos quedan huérfanos.

  OT-018 · COOSALUD (sanción del 10%) — el dictamen entero va en mayúscula
  sostenida, pero los textos que inyectan las redes finales salían en
  minúscula: "sobre el código de la glosa aplicada", "la facultad
  sancionatoria sobre el prestador está reservada...". Se ve como si el
  documento estuviera pegado de dos pedazos.

Ninguno de los dos cambia el argumento. Los dos se imprimen en el documento
que ve la entidad y se leen como un descuido de la IPS.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from app.services.glosa_service import (
    _quitar_signos_vacios,
    _rechazar_sancion_eps_ilegal,
)

RAIZ = Path(__file__).resolve().parent.parent.parent


class TestSignosVacios:
    def test_el_caso_real_nueva_eps(self):
        d = 'SE RECHAZA LA GLOSA. "" SE SOLICITA EL LEVANTAMIENTO.'
        assert _quitar_signos_vacios(d) == "SE RECHAZA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO."

    def test_todas_las_comillas_que_usa_el_motor(self):
        for par in ('""', "«»", "“”", "''"):
            d = f"SE RECHAZA LA GLOSA. {par} SE SOLICITA."
            assert par not in _quitar_signos_vacios(d), par

    def test_parentesis_y_corchetes_vacios(self):
        assert _quitar_signos_vacios("EL VALOR () FUE FACTURADO.") == "EL VALOR FUE FACTURADO."
        assert _quitar_signos_vacios("EL VALOR [] FUE FACTURADO.") == "EL VALOR FUE FACTURADO."

    def test_una_cita_con_contenido_no_se_toca(self):
        d = "CITA REAL: «EL PAGADOR RECONOCERÁ LA FACTURA»."
        assert _quitar_signos_vacios(d) == d

    def test_un_parentesis_con_contenido_no_se_toca(self):
        d = "LA MEDIDA (ART. 126 LEY 1438/2011) APLICA."
        assert _quitar_signos_vacios(d) == d

    def test_el_apostrofo_dentro_de_una_palabra_no_se_toca(self):
        d = "EL CONTRATO 440-DIGSA/DMBUG-2025 NO ES DE ESTA ENTIDAD."
        assert _quitar_signos_vacios(d) == d

    def test_no_deja_espacios_dobles_ni_puntuacion_suelta(self):
        d = 'SE RECHAZA LA GLOSA , "" , SE SOLICITA.'
        out = _quitar_signos_vacios(d)
        assert "  " not in out
        assert ", ," not in out

    def test_texto_vacio(self):
        assert _quitar_signos_vacios("") == ""
        assert _quitar_signos_vacios(None) is None

    def test_esta_enchufado_al_final_de_la_cadena(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_quitar_signos_vacios(dictamen)" in src
        i = src.index("_quitar_signos_vacios(dictamen)")
        assert "SIGNOS-VACIOS" in src[i : i + 600]


class TestTodoElDictamenEnMayuscula:
    def test_el_bloque_de_la_sancion_va_en_mayuscula(self):
        """Es el que se inyecta cuando la entidad aplica una multa."""
        glosa = "Se aplica sanción del 10% por incumplimiento. Valor descontado $1.750.000."
        d = "ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000. LA AUDITORÍA NO TIENE RAZÓN."
        out = _rechazar_sancion_eps_ilegal(d, texto_glosa=glosa)
        inyectado = out.replace(d[: d.index(".") + 1], "", 1)
        minusculas = re.findall(r"[a-záéíóúñ]{3,}", inyectado)
        assert not minusculas, f"texto en minúscula dentro del dictamen: {minusculas[:5]}"

    def test_los_textos_de_reemplazo_van_en_mayuscula(self):
        """Los sintagmas con que el motor reemplaza un placeholder terminan
        dentro del dictamen: si van en minúscula, el documento se ve pegado
        de dos pedazos."""
        src = io.open(RAIZ / "app" / "services" / "glosa_service.py", encoding="utf-8").read()
        lineas = src.split("\n")
        pat = re.compile(r'^\s*"((?:el|la|los|las|un|una)\s[^"]{6,90})",\s*$', re.I)
        malas = []
        for i in range(960, min(1450, len(lineas))):
            m = pat.match(lineas[i])
            if m and m.group(1) != m.group(1).upper():
                malas.append((i + 1, m.group(1)))
        assert not malas, f"literales de reemplazo en minúscula: {malas[:5]}"


class TestLasRedesFinalesTambienEscribenEnMayuscula:
    """Las redes finales corren DESPUÉS del paso a mayúsculas, así que lo
    que ellas inyectan tiene que venir ya en caps desde el literal."""

    def test_el_contrato_neutro(self):
        from app.services.glosa_service import _neutralizar_contratos_ajenos

        mal = "CONFORME AL CONTRATO S-13-1-03-1-04958 LOS SERVICIOS SE CANCELAN."
        out = _neutralizar_contratos_ajenos(mal, eps="DISPENSARIO MEDICO")
        assert "EL CONTRATO VIGENTE ENTRE LAS PARTES" in out
        assert "el contrato vigente entre las partes" not in out

    def test_el_reemplazo_del_articulo_177(self):
        from app.services.glosa_service import _neutralizar_art_177_relleno

        mal = "RIGE EL MANUAL TARIFARIO SOAT 2026 ART. 177 LEY 100."
        out = _neutralizar_art_177_relleno(mal, texto_glosa="TA0801 TARIFA SUPERIOR")
        assert "el régimen tarifario" not in out

    def test_ninguna_red_final_deja_frases_en_minuscula(self):
        """Barrido: un reemplazo nuevo en minúscula vuelve a partir el
        documento en dos, y no se nota hasta que sale impreso."""
        import re

        src = io.open(RAIZ / "app" / "services" / "glosa_service.py", encoding="utf-8").read()
        pat = re.compile(
            r'(?:\.subn?\(|\.replace\()\s*\n?\s*"((?:el|la|los|las|un|una|en|de|por)\s[^"]{5,90})"',
            re.I,
        )
        malas = {m.group(1) for m in pat.finditer(src) if m.group(1) != m.group(1).upper()}
        assert not malas, f"reemplazos en minúscula: {sorted(malas)[:3]}"
