"""El gate de seguridad tiene que bloquear de verdad, y no de mentiras.

Antes, el paso de seguridad del CI terminaba en `|| true`: encontraba las 22
vulnerabilidades de las librerías del motor y decía que todo estaba bien. Un
escáner que nunca falla no protege de nada.

Estas pruebas cuidan las dos formas de romperlo:

  · que deje pasar una vulnerabilidad nueva (volvería a ser un adorno);
  · que se ponga rojo con vulnerabilidades que YA estaban anotadas, solo
    porque pip-audit cambió con cuál de sus nombres las reporta — un gate que
    se pone rojo sin motivo se acaba ignorando, que es la otra forma de
    quedarse sin gate.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUION = os.path.join(RAIZ, "scripts", "revisar_vulnerabilidades.py")


def _cargar():
    spec = importlib.util.spec_from_file_location("revisar_vulnerabilidades", GUION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["revisar_vulnerabilidades"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def gate():
    return _cargar()


def _salida(paquete="jinja2", version="3.1.5", ident="PYSEC-2026-1471", aliases=None):
    return json.dumps(
        {
            "dependencies": [
                {
                    "name": paquete,
                    "version": version,
                    "vulns": [
                        {
                            "id": ident,
                            "aliases": aliases if aliases is not None else ["CVE-2025-27516"],
                            "fix_versions": ["3.1.6"],
                        }
                    ],
                }
            ]
        }
    )


def _con_salida(gate, monkeypatch, texto, codigo=0):
    class _Proc:
        stdout = texto
        stderr = ""
        returncode = codigo

    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: _Proc())


def _con_lista(gate, monkeypatch, tmp_path, contenido):
    archivo = tmp_path / "conocidas.txt"
    archivo.write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(gate, "LISTA", str(archivo))


class TestElGateBloquea:
    def test_una_vulnerabilidad_nueva_tumba_el_ci(self, gate, monkeypatch, tmp_path, capsys):
        _con_salida(gate, monkeypatch, _salida())
        _con_lista(gate, monkeypatch, tmp_path, "# nada anotado\n")
        assert gate.main(["x"]) == 1
        texto = capsys.readouterr().out
        assert "NUEVA" in texto and "jinja2" in texto
        assert "requirements.txt" in texto, "hay que decir qué hacer, no solo que falló"

    def test_una_anotada_no_lo_tumba(self, gate, monkeypatch, tmp_path):
        _con_salida(gate, monkeypatch, _salida())
        _con_lista(gate, monkeypatch, tmp_path, "PYSEC-2026-1471  # revisada el 08-09\n")
        assert gate.main(["x"]) == 0

    def test_da_igual_con_cual_de_sus_nombres_este_anotada(self, gate, monkeypatch, tmp_path):
        """PYSEC, CVE y GHSA son la misma vulnerabilidad."""
        _con_salida(
            gate,
            monkeypatch,
            _salida(aliases=["CVE-2025-27516", "GHSA-cpwx-vrp4-4pq7"]),
        )
        for nombre in ("PYSEC-2026-1471", "CVE-2025-27516", "GHSA-cpwx-vrp4-4pq7"):
            _con_lista(gate, monkeypatch, tmp_path, f"{nombre}\n")
            assert gate.main(["x"]) == 0, f"anotada como {nombre} y aun así falló"

    def test_los_comentarios_de_la_lista_no_cuentan(self, gate, monkeypatch, tmp_path):
        _con_salida(gate, monkeypatch, _salida())
        _con_lista(gate, monkeypatch, tmp_path, "# PYSEC-2026-1471 esto es un comentario\n")
        assert gate.main(["x"]) == 1, "una vulnerabilidad comentada no está perdonada"

    def test_el_texto_despues_del_numeral_se_ignora(self, gate, monkeypatch, tmp_path):
        _con_salida(gate, monkeypatch, _salida())
        _con_lista(gate, monkeypatch, tmp_path, "PYSEC-2026-1471  # jinja2 3.1.5 → 3.1.6\n")
        assert gate.main(["x"]) == 0


class TestElGateNoSePuedeEnganar:
    def test_si_pip_audit_no_corre_NO_pasa(self, gate, monkeypatch, tmp_path):
        """Una herramienta caída no es «todo bien». Eso era el `|| true`."""
        _con_salida(gate, monkeypatch, "")
        _con_lista(gate, monkeypatch, tmp_path, "")
        with pytest.raises(SystemExit) as e:
            gate.main(["x"])
        assert e.value.code == 2

    def test_una_salida_ilegible_tampoco_pasa(self, gate, monkeypatch, tmp_path):
        _con_salida(gate, monkeypatch, "esto no es JSON")
        _con_lista(gate, monkeypatch, tmp_path, "")
        with pytest.raises(SystemExit) as e:
            gate.main(["x"])
        assert e.value.code == 2

    def test_avisa_de_lo_que_ya_se_puede_quitar(self, gate, monkeypatch, tmp_path, capsys):
        """Una lista que crece y nunca se poda termina tapando cosas de verdad."""
        _con_salida(gate, monkeypatch, _salida())
        _con_lista(
            gate, monkeypatch, tmp_path, "PYSEC-2026-1471\nPYSEC-2020-0000  # ya arreglada\n"
        )
        assert gate.main(["x"]) == 0
        assert "PYSEC-2020-0000" in capsys.readouterr().out


class TestLaListaDeVerdadEstaSana:
    def test_no_tiene_renglones_repetidos(self):
        from pathlib import Path

        archivo = Path(RAIZ) / "seguridad" / "vulnerabilidades_conocidas.txt"
        ids = [
            linea.split("#")[0].strip()
            for linea in archivo.read_text(encoding="utf-8").splitlines()
            if linea.split("#")[0].strip()
        ]
        assert len(ids) == len(set(ids)), "hay identificadores repetidos"

    def test_cada_renglon_dice_de_qué_paquete_es(self):
        from pathlib import Path

        archivo = Path(RAIZ) / "seguridad" / "vulnerabilidades_conocidas.txt"
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.split("#")[0].strip():
                assert "#" in linea, (
                    f"«{linea.strip()}» no dice de qué paquete es. Un identificador "
                    "suelto no se puede revisar después."
                )
