"""El repartidor de pruebas del CI, probado fuera del CI.

Antes esto era un `case` de bash metido en el YAML del CI, y la lógica que
vive en el YAML es la que nadie revisa hasta que falla. Acá se comprueba lo
que de verdad importa: que reparta parejo, que sea siempre igual, que nadie
se quede sin correr, y que aguante que le falten mediciones.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.repartir_pruebas import (  # noqa: E402
    archivos_de_prueba,
    duraciones_medidas,
    main,
    repartir,
)


class TestElReparto:
    def test_el_mas_pesado_va_a_la_maquina_mas_liviana(self):
        pesos = {"a": 10.0, "b": 6.0, "c": 5.0, "d": 4.0}
        grupos = repartir(list(pesos), 2, pesos)
        cargas = sorted(sum(pesos[a] for a in g) for g in grupos)
        # 11 y 14 es el mejor reparto posible de {10, 6, 5, 4}. Partir la
        # lista por la mitad, como se hacía antes, daría 16 contra 9.
        assert cargas == [11.0, 14.0]

    def test_es_determinista(self):
        pesos = {f"t{i}": float(i % 7) for i in range(50)}
        assert repartir(list(pesos), 3, pesos) == repartir(list(pesos), 3, pesos)

    def test_no_depende_del_orden_en_que_lleguen(self):
        pesos = {f"t{i}": float(i % 7) for i in range(50)}
        a = repartir(sorted(pesos), 3, pesos)
        b = repartir(sorted(pesos, reverse=True), 3, pesos)
        assert a == b

    def test_nadie_se_queda_por_fuera_ni_va_dos_veces(self):
        archivos = [f"t{i}" for i in range(37)]
        repartidos = [a for g in repartir(archivos, 5, {}) for a in g]
        assert sorted(repartidos) == sorted(archivos)

    def test_sin_mediciones_reparte_por_cantidad(self):
        tamanos = [len(g) for g in repartir([f"t{i}" for i in range(20)], 4, {})]
        assert tamanos == [5, 5, 5, 5]

    def test_lo_que_no_esta_medido_vale_la_mediana(self):
        """Ni se le teme ni se le ignora: entra con el peso del montón."""
        pesos = {"a": 1.0, "b": 1.0, "c": 100.0}
        grupos = repartir(["a", "b", "c", "nuevo"], 2, pesos)
        # «c» pesa 100 y se lleva una máquina sola; los otros tres, la otra.
        assert ["c"] in grupos
        assert sorted(g for g in grupos if g != ["c"])[0] == ["a", "b", "nuevo"]

    def test_mas_maquinas_que_archivos_no_revienta(self):
        grupos = repartir(["a", "b"], 5, {})
        assert sum(len(g) for g in grupos) == 2

    def test_un_solo_grupo_se_lo_lleva_todo(self):
        assert repartir(["a", "b", "c"], 1, {}) == [["a", "b", "c"]]

    def test_cero_grupos_es_un_error(self):
        import pytest

        with pytest.raises(ValueError):
            repartir(["a"], 0, {})


class TestSobreLaSuiteDeVerdad:
    def test_encuentra_todos_los_archivos_de_prueba(self):
        archivos = archivos_de_prueba()
        assert len(archivos) > 500
        assert all(a.startswith("tests/") and a.endswith(".py") for a in archivos)
        assert not any("__pycache__" in a for a in archivos)

    def test_este_mismo_archivo_esta_en_la_lista(self):
        assert "tests/test_tools/test_repartir_pruebas.py" in archivos_de_prueba()

    def test_las_duraciones_se_leen_como_numeros(self):
        medidas = duraciones_medidas()
        assert medidas
        assert all(isinstance(v, float) and v >= 0 for v in medidas.values())

    def test_un_archivo_de_duraciones_roto_no_tumba_el_ci(self, tmp_path: Path):
        roto = tmp_path / "roto.json"
        roto.write_text("{esto no es json", encoding="utf-8")
        assert duraciones_medidas(roto) == {}
        assert duraciones_medidas(tmp_path / "no_existe.json") == {}

    def test_los_valores_que_no_son_numeros_se_descartan(self, tmp_path: Path):
        mezcla = tmp_path / "mezcla.json"
        mezcla.write_text(json.dumps({"a": 1.5, "b": "rapido", "c": None}), encoding="utf-8")
        assert duraciones_medidas(mezcla) == {"a": 1.5}


class TestLaLineaDeComandos:
    def test_pedir_un_grupo_que_no_existe_falla(self):
        assert main(["--grupos", "4", "--grupo", "9"]) == 2
        assert main(["--grupos", "4", "--grupo", "0"]) == 2

    def test_imprime_los_archivos_del_grupo(self, capsys):
        assert main(["--grupos", "4", "--grupo", "2"]) == 0
        salida = capsys.readouterr().out.split()
        assert salida
        assert all(a.endswith(".py") for a in salida)

    def test_los_cuatro_grupos_suman_la_suite(self, capsys):
        todos: list[str] = []
        for k in (1, 2, 3, 4):
            assert main(["--grupos", "4", "--grupo", str(k)]) == 0
            todos += capsys.readouterr().out.split()
        assert sorted(todos) == archivos_de_prueba()

    def test_el_resumen_no_falla(self, capsys):
        assert main(["--resumen", "--grupos", "4"]) == 0
        assert "grupo 4" in capsys.readouterr().out

    def test_medir_sin_datos_utiles_avisa(self, tmp_path: Path, capsys):
        vacio = tmp_path / "vacio.xml"
        vacio.write_text("<testsuites></testsuites>", encoding="utf-8")
        assert main(["--medir", str(vacio)]) == 1
        assert "No se pudo leer" in capsys.readouterr().err
