"""Del RIPS del HIS al lenguaje del motor (V3, Pilar 2 — 04-09-2026).

El HIS (SINAC) manda el RIPS de la Resolución 2275/2023. Estas pruebas
trabajan sobre **el archivo real que entregó el hospital**
(`tests/fixtures/rips/Rips_HUS558039.json`, con los documentos del paciente y
del profesional cambiados; la estructura es byte a byte la del original) más
casos armados para las familias de servicios que ese archivo no traía.

Lo que se protege:

  · Que los campos críticos lleguen: `codSexo`, `fechaNacimiento`,
    `numFactura`, los CUPS (`codConsulta` / `codProcedimiento` /
    `codTecnologiaSalud`), el CIE-10 y `vrServicio`.
  · Que lo que el RIPS **no trae** se diga en voz alta en vez de inventarse:
    la EPS y el texto clínico. Sin EPS no se cruza tarifa; sin notas no
    corre la IA. Ninguna de las dos cosas aborta la evaluación.
  · Que con varios usuarios en una factura NO se cruce sexo ni edad: el
    RIPS no dice de quién es cada servicio cuando se leen juntos, y acusar
    al paciente equivocado es peor que callar.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.preauditoria_rips import RipsFactura, es_rips, traducir

RAIZ = Path(__file__).resolve().parents[2]
FIXTURE = RAIZ / "tests" / "fixtures" / "rips" / "Rips_HUS558039.json"


@pytest.fixture(scope="module")
def crudo() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _traducir(cuerpo: dict):
    return traducir(RipsFactura.model_validate(cuerpo))


def _rips(servicios: dict, **kw) -> dict:
    base = {
        "numDocumentoIdObligado": "900006037",
        "numFactura": "HUS900001",
        "usuarios": [
            {
                "tipoDocumentoIdentificacion": "CC",
                "numDocumentoIdentificacion": "10000000001",
                "fechaNacimiento": "1978-08-10",
                "codSexo": "F",
                "consecutivo": 1,
                "servicios": servicios,
            }
        ],
    }
    base.update(kw)
    return base


# ═══════════════════════════════════════════════════════════════════════
class TestElArchivoRealDelHospital:
    def test_se_reconoce_como_rips(self, crudo):
        assert es_rips(crudo) is True
        assert es_rips({"factura": "X", "items": []}) is False

    def test_la_factura_y_el_paciente(self, crudo):
        p, _ = _traducir(crudo)
        assert p.factura == "HUS558039"
        assert p.paciente.sexo_normalizado() == "F"
        # Nació el 10-08-1978 y la atención fue el 24-08-2026.
        assert p.paciente.edad_en_anios(p.atencion.fecha_ingreso) == pytest.approx(48.0, abs=0.1)

    def test_la_consulta_llega_completa(self, crudo):
        p, _ = _traducir(crudo)
        assert len(p.items) == 1
        item = p.items[0]
        assert item.cups == "890264"
        assert item.valor_unitario == 117300
        assert item.total_efectivo() == 117300
        assert item.tipo == "CONSULTA"  # grupoServicios 01
        assert item.fecha.strftime("%Y-%m-%d %H:%M") == "2026-08-24 06:22"

    def test_los_diagnosticos_cie10(self, crudo):
        p, _ = _traducir(crudo)
        assert p.atencion.diagnostico_principal == "M542"
        assert "G560" in p.atencion.diagnosticos  # el relacionado también

    def test_el_total_se_suma_porque_el_rips_no_lo_trae(self, crudo):
        p, _ = _traducir(crudo)
        assert p.total_efectivo() == 117300

    def test_sin_hospitalizacion_ni_urgencias_es_ambulatorio(self, crudo):
        p, _ = _traducir(crudo)
        assert p.atencion.tipo == "AMBULATORIO"
        assert p.atencion.fecha_ingreso is not None

    def test_la_fixture_conserva_la_estructura_del_his(self, crudo):
        """Si alguien 'limpia' la fixture y le quita campos, estas pruebas
        dejarían de probar el formato real. Esto lo impide."""
        assert crudo["numDocumentoIdObligado"] == "900006037"
        consulta = crudo["usuarios"][0]["servicios"]["consultas"][0]
        for campo in (
            "codConsulta",
            "vrServicio",
            "codDiagnosticoPrincipal",
            "grupoServicios",
            "fechaInicioAtencion",
            "numAutorizacion",
        ):
            assert campo in consulta, f"la fixture perdió {campo}"

    def test_no_quedaron_datos_personales_reales_en_la_fixture(self, crudo):
        """El repositorio no guarda datos de pacientes de verdad.

        Se cambiaron los dos documentos, el identificador VIDA y el municipio
        de residencia: fecha de nacimiento + sexo + municipio son, juntos, un
        triple con el que se puede volver a identificar a una persona. La
        fecha de nacimiento se conserva porque de ella salen los cruces de
        edad, y sola no identifica a nadie.
        """
        u = crudo["usuarios"][0]
        assert u["numDocumentoIdentificacion"] == "10000000001"
        assert u["servicios"]["consultas"][0]["numDocumentoIdentificacion"] == "10000000002"
        assert u["codMunicipioResidencia"] == "00000"
        assert set(u["servicios"]["consultas"][0]["codigoVIDA"]) <= set("0-48")


# ═══════════════════════════════════════════════════════════════════════
class TestLoQueElRipsNoTrae:
    def test_sin_eps_se_dice_y_no_se_inventa(self, crudo):
        p, omisiones = _traducir(crudo)
        assert p.eps == ""
        assert any("EPS" in o for o in omisiones)
        # numDocumentoIdObligado es el NIT del hospital: NO es la EPS.
        assert "900006037" not in p.eps

    def test_si_el_his_agrega_la_eps_al_lado_se_usa(self, crudo):
        cuerpo = dict(crudo)
        cuerpo["eps"] = "COOSALUD EPS-S"
        p, omisiones = _traducir(cuerpo)
        assert p.eps == "COOSALUD EPS-S"
        assert not any("EPS" in o for o in omisiones)

    def test_sin_notas_clinicas_se_dice(self, crudo):
        p, omisiones = _traducir(crudo)
        assert p.epicrisis == ""
        assert any("notas clínicas" in o for o in omisiones)

    def test_si_el_his_adjunta_notas_se_usan(self, crudo):
        cuerpo = dict(crudo)
        cuerpo["notasClinicas"] = "Paciente con lumbalgia, examen neurológico normal."
        p, omisiones = _traducir(cuerpo)
        assert "lumbalgia" in p.epicrisis
        assert not any("notas clínicas" in o for o in omisiones)


# ═══════════════════════════════════════════════════════════════════════
class TestLasOtrasFamiliasDeServicios:
    def test_procedimientos(self):
        p, _ = _traducir(
            _rips(
                {
                    "procedimientos": [
                        {
                            "codProcedimiento": "511002",
                            "fechaInicioAtencion": "2026-08-24 09:00",
                            "grupoServicios": "04",
                            "codDiagnosticoPrincipal": "K801",
                            "vrServicio": 2400000,
                        }
                    ]
                }
            )
        )
        assert len(p.items) == 1
        assert p.items[0].cups == "511002"
        assert p.items[0].tipo == "QUIRURGICO"
        assert p.items[0].total_efectivo() == 2400000
        assert p.atencion.diagnostico_principal == "K801"

    def test_hospitalizacion_da_las_fechas_del_episodio(self):
        p, _ = _traducir(
            _rips(
                {
                    "hospitalizacion": [
                        {
                            "viaIngresoServicioSalud": "02",
                            "fechaInicioAtencion": "2026-08-20 14:00",
                            "fechaEgreso": "2026-08-25 10:00",
                            "codDiagnosticoPrincipal": "A419",
                        }
                    ]
                }
            )
        )
        assert p.atencion.tipo == "HOSPITALIZACION"
        assert p.atencion.fecha_ingreso.strftime("%Y-%m-%d") == "2026-08-20"
        assert p.atencion.fecha_egreso.strftime("%Y-%m-%d") == "2026-08-25"
        assert p.atencion.dias_calendario() == 5

    def test_urgencias(self):
        p, _ = _traducir(
            _rips(
                {
                    "urgencias": [
                        {
                            "fechaInicioAtencion": "2026-08-24 06:00",
                            "fechaEgreso": "2026-08-24 11:00",
                            "codDiagnosticoPrincipal": "R104",
                        }
                    ]
                }
            )
        )
        assert p.atencion.tipo == "URGENCIAS"
        assert p.atencion.diagnostico_principal == "R104"

    def test_medicamentos_con_cantidad_y_unitario(self):
        p, _ = _traducir(
            _rips(
                {
                    "medicamentos": [
                        {
                            "codTecnologiaSalud": "M01101",
                            "nomTecnologiaSalud": "OXÍGENO MEDICINAL POR HORA",
                            "cantidadMedicamento": 24,
                            "vrUnitMedicamento": 1500,
                            "vrServicio": 36000,
                            "fechaDispensAdmon": "2026-08-24 08:00",
                        }
                    ]
                }
            )
        )
        item = p.items[0]
        assert item.tipo == "MEDICAMENTO"
        assert item.cantidad == 24
        assert item.valor_unitario == 1500
        assert item.total_efectivo() == 36000

    def test_otros_servicios_de_estancia_alimentan_los_dias(self):
        p, _ = _traducir(
            _rips(
                {
                    "hospitalizacion": [
                        {
                            "fechaInicioAtencion": "2026-08-20 14:00",
                            "fechaEgreso": "2026-08-25 10:00",
                            "codDiagnosticoPrincipal": "A419",
                        }
                    ],
                    "otrosServicios": [
                        {
                            "tipoOS": "03",
                            "codTecnologiaSalud": "S11201",
                            "nomTecnologiaSalud": "ESTANCIA EN UCI ADULTOS",
                            "cantidadOS": 3,
                            "vrUnitOS": 1500000,
                            "vrServicio": 4500000,
                        },
                        {
                            "tipoOS": "03",
                            "codTecnologiaSalud": "S11101",
                            "nomTecnologiaSalud": "ESTANCIA EN HABITACIÓN COMPARTIDA",
                            "cantidadOS": 2,
                            "vrUnitOS": 300000,
                            "vrServicio": 600000,
                        },
                    ],
                }
            )
        )
        assert p.atencion.dias_estancia == 5
        assert p.atencion.dias_uci == 3
        assert p.total_efectivo() == 5100000
        assert [i.tipo for i in p.items] == ["ESTANCIA", "ESTANCIA"]

    def test_un_arreglo_en_null_no_revienta(self):
        """El HIS manda `null` en las familias que no aplican."""
        p, _ = _traducir(
            _rips(
                {
                    "consultas": [
                        {"codConsulta": "890201", "vrServicio": 60000, "grupoServicios": "01"}
                    ],
                    "procedimientos": None,
                    "urgencias": None,
                    "hospitalizacion": None,
                    "medicamentos": None,
                    "otrosServicios": None,
                    "recienNacidos": None,
                }
            )
        )
        assert len(p.items) == 1

    def test_un_campo_que_no_conocemos_se_ignora(self):
        cuerpo = _rips(
            {"consultas": [{"codConsulta": "890201", "vrServicio": 1000, "campoNuevoDelHIS": 42}]}
        )
        cuerpo["otraCosaDelHIS"] = {"lo": "que sea"}
        p, _ = _traducir(cuerpo)
        assert len(p.items) == 1


# ═══════════════════════════════════════════════════════════════════════
class TestVariosUsuariosEnUnaFactura:
    def _dos_usuarios(self) -> dict:
        return {
            "numFactura": "HUS900002",
            "usuarios": [
                {
                    "numDocumentoIdentificacion": "1",
                    "codSexo": "F",
                    "fechaNacimiento": "1990-01-01",
                    "servicios": {"consultas": [{"codConsulta": "890201", "vrServicio": 60000}]},
                },
                {
                    "numDocumentoIdentificacion": "2",
                    "codSexo": "M",
                    "fechaNacimiento": "1950-01-01",
                    "servicios": {"consultas": [{"codConsulta": "890202", "vrServicio": 80000}]},
                },
            ],
        }

    def test_no_se_cruza_sexo_ni_edad_y_se_dice_por_que(self):
        p, omisiones = _traducir(self._dos_usuarios())
        assert p.paciente.sexo_normalizado() == ""
        assert p.paciente.edad_en_dias() is None
        assert any("2 usuarios" in o for o in omisiones)

    def test_pero_la_plata_si_se_suma_toda(self):
        """Aritmética, tarifas y duplicados son de la factura entera."""
        p, _ = _traducir(self._dos_usuarios())
        assert len(p.items) == 2
        assert p.total_efectivo() == 140000
