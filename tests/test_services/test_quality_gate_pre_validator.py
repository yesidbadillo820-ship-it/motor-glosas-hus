"""Tests del Quality Gate — Pre-validador."""

from __future__ import annotations

import pytest

from app.services.quality_gate.pre_validator import (
    check_codigo_glosa,
    check_eps,
    check_plantilla_disponible,
    check_texto_glosa,
    check_valor_monetario,
    pre_validar_glosa,
)


class TestCodigoGlosa:
    @pytest.mark.parametrize(
        "codigo,esperado_ok,familia_esperada",
        [
            ("TA0201", True, "TA"),
            ("SO0501", True, "SO"),
            ("CO0101", True, "CO"),
            ("FA0501", True, "FA"),
            ("CL0101", True, "CL"),
            ("AU0301", True, "AU"),
            ("ta0201", True, "TA"),  # normaliza minúsculas
            ("  TA0201  ", True, "TA"),  # trim espacios
            ("TA02", True, "TA"),  # 2 dígitos también válido
            ("TA1234", True, "TA"),  # 4 dígitos también válido
        ],
    )
    def test_codigos_validos(self, codigo, esperado_ok, familia_esperada):
        res, cod_norm, familia = check_codigo_glosa(codigo)
        assert res.ok == esperado_ok
        assert familia == familia_esperada

    @pytest.mark.parametrize(
        "codigo_invalido",
        [
            "",
            "XX0201",  # prefijo no oficial
            "TA",  # sin dígitos
            "0201TA",  # invertido
            "TA02XX",  # con letras al final
            "TA-0201",  # con guión
            None,
        ],
    )
    def test_codigos_invalidos(self, codigo_invalido):
        res, _, _ = check_codigo_glosa(codigo_invalido or "")
        assert not res.ok
        assert res.razon  # debe tener razón explicada

    @pytest.mark.parametrize(
        "placeholder", ["N/A", "NA", "-", "—", "?", "SIN CODIGO", "SIN CÓDIGO"]
    )
    def test_placeholders_de_codigo_ausente_dan_mensaje_amigable(self, placeholder):
        # Regresión 10-jun-2026: el gestor pegaba un motivo legítimo sin
        # código ("Se evidencia cobro duplicado mediante fragmentación de
        # procedimientos.") y _extraer_codigos_glosa devolvía []. El caller
        # pasaba "N/A" al pre-validator, que mostraba "Código 'N/A' no
        # tiene formato válido (debe ser AA####)" — mensaje confuso.
        # Ahora cualquier placeholder ("N/A", "-", ...) dispara el mensaje
        # de "Falta el código" con sugerencia accionable.
        res, _, _ = check_codigo_glosa(placeholder)
        assert not res.ok
        assert "no detect" in res.razon.lower() or "falta" in res.razon.lower()
        assert "agrega" in res.sugerencia.lower() or "incluye" in res.sugerencia.lower()
        # NO debe filtrar el placeholder al mensaje
        assert placeholder.upper() not in res.razon


class TestEps:
    def test_eps_conocida(self):
        res, eps_norm = check_eps("FAMISANAR EPS")
        assert res.ok
        assert eps_norm == "FAMISANAR EPS"

    def test_eps_con_tildes(self):
        res, _ = check_eps("POLICÍA NACIONAL")
        assert res.ok

    def test_eps_vacia_falla(self):
        res, _ = check_eps("")
        assert not res.ok
        assert "Falta" in res.razon

    def test_eps_desconocida_no_bloquea(self):
        """EPSs nuevas/raras no deben bloquear — solo whitelist es permisiva."""
        res, _ = check_eps("EPS NUEVA DEL FUTURO XYZ")
        assert res.ok  # NO bloquea


class TestValorMonetario:
    @pytest.mark.parametrize(
        "input_val,esperado",
        [
            ("500000", 500000.0),
            ("$500.000", 500000.0),
            ("$ 500.000", 500000.0),
            ("500,000", 500000.0),
            ("1'500.000", 1500000.0),
            ("%150.000", 150000.0),  # typo % por $
            ("500000 pesos", 500000.0),
            (500000, 500000.0),
            (500000.0, 500000.0),
        ],
    )
    def test_parseo_valores(self, input_val, esperado):
        res, v = check_valor_monetario(input_val)
        assert res.ok, f"Falló parseo de {input_val!r}: {res.razon}"
        assert v == esperado

    @pytest.mark.parametrize("invalido", ["", None, 0, "0", "abc", "$ 0"])
    def test_valor_ausente_o_invalido_no_bloquea(self, invalido):
        """El valor objetado es OPCIONAL — pre_validator ya no bloquea por su
        ausencia. Esto permite glosas de cobertura sin monto definido (ej.
        ratificaciones de etapa previa). El detector de "valores fabricados"
        del post_validator se encarga de impedir que la IA invente cifras."""
        res, v = check_valor_monetario(invalido)
        assert res.ok  # ya no bloquea
        assert v == 0.0  # pero el valor parseado sigue siendo 0
        assert res.sugerencia  # deja una sugerencia opcional


class TestTextoGlosa:
    def test_texto_largo_ok(self):
        res = check_texto_glosa(
            "TA0201 - Mayor valor cobrado en consulta especializada "
            "por valor objetado de $500.000 según factura electrónica"
        )
        assert res.ok

    def test_texto_sin_palabra_dominio_rechazado(self):
        # Sin código presente + sin ningún término del dominio (admin o
        # clínico): posible copy-paste de algo no relacionado con una glosa.
        res = check_texto_glosa(
            "Este es un texto suficientemente largo pero sin sustancia.",
            codigo_presente=False,
        )
        assert not res.ok
        assert "glosa" in (res.razon or "").lower()

    def test_texto_corto_falla(self):
        # Antes el mínimo era 60 — bloqueaba glosas reales de 35-50 chars
        # ("TA0102 - Medicamento fuera del PBS"). Ahora 20 chars.
        res = check_texto_glosa("TA0201", codigo_presente=True)
        assert not res.ok
        assert "corto" in res.razon.lower()

    def test_texto_vacio_falla(self):
        res = check_texto_glosa("")
        assert not res.ok

    def test_glosa_corta_real_con_codigo_pasa(self):
        # Regresión 10-jun-2026: "TA0102 - Medicamento fuera del PBS. No
        # procede reconocimiento." (53 chars) era rechazada por el viejo
        # mínimo de 60. En la vida real las glosas son así de cortas.
        res = check_texto_glosa(
            "TA0102 - Medicamento fuera del PBS. No procede reconocimiento.",
            codigo_presente=True,
        )
        assert res.ok

    def test_glosa_clinica_sin_admin_pasa(self):
        # Regresión 10-jun-2026: "Se reconocen únicamente 8 días de UCI.
        # Los días restantes se consideran injustificados." era rechazada
        # porque ninguna palabra de la lista vieja (factura/CUPS/tarifa...)
        # aparecía. Pero "UCI", "días" y "reconoc" sí son dominio clínico.
        res = check_texto_glosa(
            "Se reconocen únicamente 8 días de UCI. Los días restantes "
            "se consideran injustificados.",
            codigo_presente=False,
        )
        assert res.ok


class TestPlantillaDisponible:
    def test_familias_con_banco_hus(self):
        for familia in ["TA", "SO", "CO", "FA", "CL"]:
            res = check_plantilla_disponible(familia)
            assert res.ok
            assert not res.razon  # familia conocida → sin warnings

    def test_familia_sin_banco_hus_solo_warning(self):
        """AU/PE/SE/IN/ME/EX no tienen plantilla — no bloquea pero advierte."""
        res = check_plantilla_disponible("AU")
        assert res.ok  # NO bloquea
        assert "no tiene plantillas" in res.razon.lower()

    def test_familia_vacia_ok(self):
        res = check_plantilla_disponible("")
        assert res.ok


class TestPreValidarGlosa:
    def test_glosa_completa_aprobada(self):
        r = pre_validar_glosa(
            eps="FAMISANAR EPS",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa="TA0201 - Mayor valor cobrado en consulta especializada por $500.000",
        )
        assert r.aprobado
        assert r.codigo_normalizado == "TA0201"
        assert r.familia_codigo == "TA"
        assert r.valor_parseado == 500000.0
        assert not r.razones_bloqueo

    def test_glosa_sin_codigo_falla(self):
        r = pre_validar_glosa(
            eps="FAMISANAR EPS",
            codigo_glosa="",
            valor_objetado="500000",
            texto_glosa="Mayor valor cobrado en consulta especializada por factura",
        )
        assert not r.aprobado
        assert any("código" in razon.lower() for razon in r.razones_bloqueo)

    def test_glosa_sin_eps_falla(self):
        r = pre_validar_glosa(
            eps="",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa="TA0201 mayor valor cobrado",
        )
        assert not r.aprobado
        assert any("eps" in razon.lower() for razon in r.razones_bloqueo)

    def test_glosa_sin_valor_NO_falla(self):
        """Cambio de comportamiento: el valor objetado ahora es opcional.
        Una glosa sin valor sigue siendo aprobada por el pre-validator
        (texto suficiente + código válido + EPS válida). El detector de
        valores fabricados del post_validator se encarga después de que
        la IA no invente cifras que no estaban en el input."""
        r = pre_validar_glosa(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="",
            texto_glosa=(
                "TA0201 mayor valor cobrado en consulta especializada "
                "por servicio facturado según factura electrónica"
            ),
        )
        assert r.aprobado  # ya no bloquea por falta de valor
        assert r.valor_parseado == 0.0  # pero el valor sigue siendo 0

    def test_mensaje_para_usuario_legible(self):
        r = pre_validar_glosa(
            eps="",
            codigo_glosa="",
            valor_objetado="",
            texto_glosa="",
        )
        msg = r.mensaje_para_usuario
        assert "No puedo generar dictamen" in msg
        assert "Sugerencias" in msg
        # Cada razón debe estar listada
        for razon in r.razones_bloqueo:
            assert razon in msg

    def test_aprobado_sin_mensaje(self):
        r = pre_validar_glosa(
            eps="NUEVA EPS",
            codigo_glosa="CL0101",
            valor_objetado="1500000",
            texto_glosa=(
                "CL0101 - No pertinencia clínica del procedimiento facturado "
                "por valor de $1.500.000 según historia clínica del paciente"
            ),
        )
        assert r.aprobado
        assert r.mensaje_para_usuario == ""

    def test_familia_sin_banco_hus_aprueba_pero_advierte(self):
        """AU0301 (autorización) no tiene plantilla — debe pasar pre-check
        pero el resultado debe incluir la advertencia."""
        r = pre_validar_glosa(
            eps="FAMISANAR",
            codigo_glosa="AU0301",
            valor_objetado="500000",
            texto_glosa=(
                "AU0301 - autorización pendiente del servicio facturado "
                "por valor de $500.000 según factura electrónica"
            ),
        )
        assert r.aprobado  # no bloquea
        # Pero el check de plantilla debe traer razón (warning)
        assert r.checks["plantilla"].razon  # advertencia presente
