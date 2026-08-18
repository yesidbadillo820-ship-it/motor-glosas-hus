"""Prueba de que el validador FURIPS de verdad valida — 18-08-2026.

Las pruebas que había cubrían el router y la plomería (subir, estado, roles).
Esta corre el MOTOR de verdad de punta a punta: arma un paquete FURIPS con el
formato real de la Circular 022/2023 —a partir de la propia malla del
validador—, lo pasa por `procesar`, y comprueba que:

  1. corre sin caerse y devuelve un resultado por factura,
  2. caza un valor inválido plantado a propósito (sexo fuera de F/M/O),
  3. NO marca ese campo cuando el valor es correcto (no es un detector que
     grita por todo),
  4. genera el Excel del informe.

El paquete de prueba deja en blanco los campos de accidente (vehículo, póliza,
propietario), así que el validador los exige con razón: eso confirma que la
malla condicional funciona, no que el archivo esté «mal».
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ADRES = str(Path(__file__).resolve().parent.parent.parent / "tools" / "adres")
if _ADRES not in sys.path:
    sys.path.insert(0, _ADRES)

import validar_furips as vf  # noqa: E402

FACTURA = "HUS999001"


def _valor_f1(campo, sexo="M"):
    nro, _sec, _concepto, longmax, fmt, permitidos, oblig = campo
    if nro == 3:
        return FACTURA
    if nro == 14:
        return sexo  # el que vamos a variar en las pruebas
    if permitidos:
        return sorted(permitidos)[0]
    if fmt == "fecha":
        return "15/05/2025"
    if fmt == "num":
        return "1"
    if fmt == "dir":
        return "CALLE 10 # 20 30"
    if fmt == "depto":
        return "68"
    if fmt == "mun":
        return "001"
    if oblig == "SI":
        return "DATO"[: (longmax or 4)]
    return ""


def _valor_f2(campo):
    nro, _concepto, _longmax, fmt, oblig = campo
    if nro == 1:
        return FACTURA
    if nro in (2, 3):
        return "1"
    if fmt == "num":
        return "1000"
    return "1" if oblig == "SI" else ""


def _paquete(tmp_path: Path, sexo="M") -> Path:
    f1 = ",".join(_valor_f1(c, sexo=sexo) for c in vf.E1)
    f2 = ",".join(_valor_f2(c) for c in vf.E2)
    (tmp_path / f"FURIPS1{FACTURA}.txt").write_text(f1 + "\n", encoding="latin-1")
    (tmp_path / f"FURIPS2{FACTURA}.txt").write_text(f2 + "\n", encoding="latin-1")
    return tmp_path


def _procesar(carpeta: Path):
    return vf.procesar(raiz=None, carpeta=carpeta, furips1=None, furips2=None, sin_pdf=True)


class TestElMotorValidaDeVerdad:
    def test_corre_y_devuelve_una_factura(self, tmp_path):
        resultados, _obs = _procesar(_paquete(tmp_path))
        assert len(resultados) == 1
        assert resultados[0].factura == vf.norm_factura(FACTURA)

    def test_caza_un_sexo_invalido(self, tmp_path):
        resultados, _obs = _procesar(_paquete(tmp_path, sexo="X"))
        errores_sexo = [
            h for h in resultados[0].hallazgos if h.campo == "14" and h.severidad == vf.ERROR
        ]
        assert errores_sexo, "el validador no marcó el sexo inválido"

    def test_no_marca_el_sexo_cuando_es_valido(self, tmp_path):
        """No es un detector que grita por todo: con 'M' no hay error de sexo."""
        resultados, _obs = _procesar(_paquete(tmp_path, sexo="M"))
        errores_sexo = [
            h for h in resultados[0].hallazgos if h.campo == "14" and h.severidad == vf.ERROR
        ]
        assert errores_sexo == []

    def test_exige_los_campos_de_accidente_que_quedaron_en_blanco(self, tmp_path):
        """La malla condicional funciona: al declarar vehículo/póliza y dejar
        esos campos vacíos, el validador los exige."""
        resultados, _obs = _procesar(_paquete(tmp_path))
        campos_con_error = {h.campo for h in resultados[0].hallazgos if h.severidad == vf.ERROR}
        # 33 = número de póliza SOAT, uno de los condicionales.
        assert "33" in campos_con_error

    def test_genera_el_excel(self, tmp_path):
        resultados, obs = _procesar(_paquete(tmp_path))
        salida = tmp_path / "informe.xlsx"
        vf.generar_excel(resultados, obs, salida)
        assert salida.exists() and salida.stat().st_size > 0
