"""Que una herramienta a medio instalar se note, y que el CI no la deje pasar.

Durante meses doce pruebas fallaron con «source file could not be loaded» y
se aceptaron como «fallas del entorno». La causa real era otra: LibreOffice
instalado A PEDAZOS —el ejecutable sin Writer, sin Calc y sin Draw—, que es
la instalación por defecto de `libreoffice-core` en un contenedor. El
mensaje hacía pensar en un archivo dañado y mandaba a buscar donde no era.
"""

from __future__ import annotations

import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SUITE = os.path.join(RAIZ, "tools", "suite_cartera_hus")
if SUITE not in sys.path:
    sys.path.insert(0, SUITE)

from nucleo import office_tools  # noqa: E402

from . import _entorno  # noqa: E402


class TestLibreOfficeAMedioInstalar:
    def test_el_ejecutable_solo_no_alcanza(self, tmp_path, monkeypatch):
        """Un `soffice` sin módulos no puede convertir, y hay que decirlo."""
        programa = tmp_path / "libreoffice" / "program"
        programa.mkdir(parents=True)
        (programa / "soffice").write_text("#!/bin/sh\n")
        (programa / "services.rdb").write_text("")  # instalación real, pero pelada

        monkeypatch.setattr(office_tools, "buscar_soffice", lambda: str(programa / "soffice"))
        faltan = office_tools.modulos_libreoffice_faltantes()
        assert len(faltan) == 3, f"debería reportar los tres módulos, reportó {faltan}"

        puede, motivo = office_tools.libreoffice_puede_convertir(".html")
        assert not puede
        assert "Writer" in motivo, "el mensaje no dice cuál módulo falta"
        assert "no es que el archivo esté dañado" in motivo.lower(), (
            "sin esta frase, el auditor sale a buscar un archivo corrupto que no existe"
        )
        assert "libreoffice-writer" in motivo, "no dice qué instalar"

    def test_con_los_modulos_puestos_no_se_queja(self, tmp_path, monkeypatch):
        programa = tmp_path / "libreoffice" / "program"
        programa.mkdir(parents=True)
        (programa / "soffice").write_text("#!/bin/sh\n")
        (programa / "services.rdb").write_text("")
        for lib in ("libswlo.so", "libsclo.so", "libsdlo.so"):
            (programa / lib).write_text("")

        monkeypatch.setattr(office_tools, "buscar_soffice", lambda: str(programa / "soffice"))
        assert office_tools.modulos_libreoffice_faltantes() == []
        assert office_tools.libreoffice_puede_convertir(".xlsx")[0]

    def test_cada_tipo_de_archivo_pide_su_modulo(self, tmp_path, monkeypatch):
        """Un Excel necesita Calc; que esté Writer no sirve de nada."""
        programa = tmp_path / "libreoffice" / "program"
        programa.mkdir(parents=True)
        (programa / "soffice").write_text("#!/bin/sh\n")
        (programa / "services.rdb").write_text("")
        (programa / "libswlo.so").write_text("")  # solo Writer

        monkeypatch.setattr(office_tools, "buscar_soffice", lambda: str(programa / "soffice"))
        assert office_tools.libreoffice_puede_convertir(".html")[0], "Writer sí está"
        puede_excel, motivo = office_tools.libreoffice_puede_convertir(".xlsx")
        assert not puede_excel and "Calc" in motivo
        puede_pdf, motivo_pdf = office_tools.libreoffice_puede_convertir(".pdf")
        assert not puede_pdf and "Draw" in motivo_pdf

    def test_no_se_inventa_un_diagnostico_donde_no_puede_mirar(self, monkeypatch):
        """En Windows/macOS no se inspecciona la instalación: no se opina."""
        monkeypatch.setattr(office_tools, "buscar_soffice", lambda: None)
        assert office_tools.modulos_libreoffice_faltantes() == []
        monkeypatch.setattr(office_tools, "_carpeta_programa", lambda _s: None)
        monkeypatch.setattr(office_tools, "buscar_soffice", lambda: "/ruta/rara/soffice")
        assert office_tools.libreoffice_puede_convertir(".docx") == (True, "")

    def test_convertir_avisa_antes_de_intentarlo(self, tmp_path, monkeypatch):
        """El error tiene que ser el bueno, no el de LibreOffice."""
        programa = tmp_path / "libreoffice" / "program"
        programa.mkdir(parents=True)
        (programa / "soffice").write_text("#!/bin/sh\n")
        (programa / "services.rdb").write_text("")
        monkeypatch.setattr(office_tools, "buscar_soffice", lambda: str(programa / "soffice"))

        doc = tmp_path / "carta.html"
        doc.write_text("<html><body>x</body></html>")
        with pytest.raises(RuntimeError, match="Writer"):
            office_tools.a_pdf(str(doc), str(tmp_path), log=lambda _m: None)


class TestElCiNoPuedeSaltarseEstasPruebas:
    """Una prueba saltada en el CI es una prueba que ya no cuida nada."""

    def test_sin_la_variable_se_salta(self, monkeypatch):
        monkeypatch.delenv("EXIGIR_HERRAMIENTAS_DE_PRUEBA", raising=False)
        assert not _entorno.exigido()
        marca = _entorno._marca("no está instalado", "LibreOffice")
        assert marca.mark.args[0] is True, "debería saltarse"
        assert "preparar_entorno_pruebas.sh" in marca.mark.kwargs.get("reason", ""), (
            "el motivo tiene que decir cómo arreglarlo"
        )

    def test_con_la_variable_revienta(self, monkeypatch):
        monkeypatch.setenv("EXIGIR_HERRAMIENTAS_DE_PRUEBA", "1")
        assert _entorno.exigido()
        with pytest.raises(RuntimeError, match="no se puede saltar"):
            _entorno._marca("no está instalado", "LibreOffice")

    def test_si_la_herramienta_esta_no_estorba(self, monkeypatch):
        monkeypatch.setenv("EXIGIR_HERRAMIENTAS_DE_PRUEBA", "1")
        marca = _entorno._marca("", "LibreOffice")
        assert marca.mark.args[0] is False

    def test_este_entorno_tiene_las_herramientas(self):
        """Si esto falla acá, corra `bash scripts/preparar_entorno_pruebas.sh`."""
        assert _entorno.falta_libreoffice() == "", _entorno.falta_libreoffice()
        assert _entorno.falta_extract_msg() == "", _entorno.falta_extract_msg()
