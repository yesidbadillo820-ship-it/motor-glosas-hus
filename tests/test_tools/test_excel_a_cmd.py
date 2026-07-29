"""Pruebas del motor tools/excel_a_cmd.py (usado por EXCEL_A_CMD.cmd).

No requiere openpyxl: los "Excel" de prueba son archivos con la firma real
(ZIP para .xlsx, OLE2 para .xls), que es lo único que el motor inspecciona.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
_MOTOR = _RAIZ / "tools" / "excel_a_cmd.py"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("excel_a_cmd", _MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hacer_xlsx(ruta: Path, relleno: bytes = b"contenido") -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"PK\x03\x04" + relleno)


def _hacer_xls(ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"\xd0\xcf\x11\xe0" + b"ole2")


def test_convierte_cada_excel_a_cmd(tmp_path):
    _hacer_xlsx(tmp_path / "c" / "INFORME.xlsx")
    _hacer_xls(tmp_path / "c" / "VIEJO.xls")
    _hacer_xlsx(tmp_path / "sub" / "otro" / "RIPS.xlsm")

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0

    for origen in ("c/INFORME.xlsx", "c/VIEJO.xls", "sub/otro/RIPS.xlsm"):
        o = tmp_path / origen
        copia = o.with_suffix(".cmd")
        assert copia.exists(), f"falta {copia}"
        assert copia.read_bytes() == o.read_bytes()
        assert o.exists()  # el original queda intacto


def test_idempotente_y_refresca_la_copia(tmp_path):
    xlsx = tmp_path / "c" / "INFORME.xlsx"
    _hacer_xlsx(xlsx, b"version1")
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    copia = xlsx.with_suffix(".cmd")
    assert copia.read_bytes().endswith(b"version1")

    # El Excel cambia → la copia se refresca en la siguiente corrida.
    _hacer_xlsx(xlsx, b"version2")
    assert mod.main([str(tmp_path)]) == 0
    assert copia.read_bytes().endswith(b"version2")
    assert not list(tmp_path.rglob("*.tmp"))


def test_jamas_pisa_un_cmd_que_no_es_excel(tmp_path):
    _hacer_xlsx(tmp_path / "c" / "UNIR_PDFS.xlsx")
    bot = tmp_path / "c" / "UNIR_PDFS.cmd"
    bot.write_bytes(b"@echo off\r\nrem soy un script real\r\n")

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    # El script real sigue intacto: la conversión se omitió.
    assert bot.read_bytes().startswith(b"@echo off")


def test_ignora_temporales_de_office_y_colisiones(tmp_path):
    _hacer_xlsx(tmp_path / "c" / "~$INFORME.xlsx")  # lock temporal de Office
    _hacer_xlsx(tmp_path / "c" / "DOBLE.xlsx")
    _hacer_xls(tmp_path / "c" / "DOBLE.xls")  # chocaría con DOBLE.cmd

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert not (tmp_path / "c" / "~$INFORME.cmd").exists()
    copia = tmp_path / "c" / "DOBLE.cmd"
    # Solo el primero (orden natural: .xls antes que .xlsx) generó la copia.
    assert copia.exists()
    assert len(list((tmp_path / "c").glob("*.cmd"))) == 1


def test_simulacro_no_escribe(tmp_path):
    _hacer_xlsx(tmp_path / "c" / "INFORME.xlsx")
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--simulacro"]) == 0
    assert not (tmp_path / "c" / "INFORME.cmd").exists()


def test_motor_embebido_en_cmd_identico_al_py():
    """La copia embebida tras #PYSTART# en EXCEL_A_CMD.cmd debe ser el .py exacto."""
    cmd_path = _RAIZ / "tools" / "EXCEL_A_CMD.cmd"
    lineas = cmd_path.read_text(encoding="utf-8").splitlines()
    marcador = "#PY" + "START#"  # partido para no autodetectarse
    idx = next(i for i, ln in enumerate(lineas) if marcador in ln)
    embebido = "\n".join(lineas[idx + 1 :]).strip("\n")
    fuente = _MOTOR.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    assert embebido == fuente, (
        "La copia embebida en tools/EXCEL_A_CMD.cmd difiere de tools/excel_a_cmd.py. "
        "Regenera el .cmd (encabezado batch + contenido del .py en CRLF)."
    )
