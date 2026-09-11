"""El motor tiene que poder decir QUÉ está lento.

11-09-2026. Yesid: «*ayúdame a mirar por qué está tan lenta la plataforma*».
Y no había con qué contestarle: se pudo medir la memoria (1,1 GB), el
procesador (9 %) y el servidor de archivos (17 ms) —todo sano—, pero **el
motor no anotaba en ninguna parte cuánto tardaba en contestar**. O sea que
la única pregunta que de verdad importa era la única sin respuesta, y tocó
salir a suponer.

Ahora cada petición se cronometra, las que pasan del umbral quedan en el
registro, y el resumen por pantalla se ve en «Diagnóstico del sistema».
"""

from __future__ import annotations

import pytest

from app.services.tiempos_peticiones import (
    MAX_RECIENTES,
    MAX_RUTAS,
    SEGUNDOS_PARA_AVISAR,
    agrupar_ruta,
    anotar,
    reiniciar,
    resumen,
)


@pytest.fixture(autouse=True)
def _limpio():
    reiniciar()
    yield
    reiniciar()


class TestAgruparRutas:
    """`/glosas/12345` y `/glosas/99` son la MISMA pantalla."""

    def test_los_numeros_se_agrupan(self):
        assert agrupar_ruta("/glosas/12345") == "/glosas/{n}"
        assert agrupar_ruta("/glosas/12345/comentarios") == "/glosas/{n}/comentarios"

    def test_las_facturas_se_agrupan(self):
        assert agrupar_ruta("/soportes-auto/factura/HUS0000541440") == (
            "/soportes-auto/factura/{factura}"
        )

    def test_los_identificadores_largos_se_agrupan(self):
        r = agrupar_ruta("/x/3f2504e0-4f89-11d3-9a0c-0305e82c3301")
        assert r == "/x/{id}"

    def test_una_ruta_normal_no_se_toca(self):
        assert agrupar_ruta("/admin/diagnostico") == "/admin/diagnostico"

    def test_no_crece_sin_limite(self):
        assert len(agrupar_ruta("/x" * 500)) <= 120

    def test_ruta_vacia(self):
        assert agrupar_ruta("") == "/"


class TestElResumenDiceLaVerdad:
    def test_cuenta_veces_promedio_y_la_peor(self):
        anotar("GET", "/glosas/1", 200, 0.10)
        anotar("GET", "/glosas/2", 200, 0.30)
        fila = next(f for f in resumen()["por_pantalla"] if f["ruta"] == "GET /glosas/{n}")
        assert fila["veces"] == 2
        assert fila["promedio_s"] == pytest.approx(0.20, abs=0.001)
        assert fila["peor_s"] == pytest.approx(0.30, abs=0.01)

    def test_manda_lo_que_mas_tiempo_se_lleva_en_el_dia(self):
        """Una pantalla de 0,4 s que se abre mil veces pesa más que una de 8 s
        que se abre una. El auditor sufre la primera."""
        for _ in range(100):
            anotar("GET", "/muy-usada", 200, 0.4)
        anotar("GET", "/rarisima", 200, 8.0)
        assert resumen()["por_pantalla"][0]["ruta"] == "GET /muy-usada"

    def test_marca_las_que_pasan_del_umbral(self):
        anotar("GET", "/rapida", 200, 0.1)
        anotar("GET", "/pesada", 200, SEGUNDOS_PARA_AVISAR + 1)
        d = resumen()
        assert d["peticiones"] == 2
        assert d["peticiones_lentas"] == 1
        assert [x["ruta"] for x in d["ultimas_lentas"]] == ["/pesada"]

    def test_las_lentas_salen_de_la_mas_nueva_a_la_mas_vieja(self):
        for i in range(3):
            anotar("GET", f"/lenta-{i}", 200, SEGUNDOS_PARA_AVISAR + 1)
        assert [x["ruta"] for x in resumen()["ultimas_lentas"]] == [
            "/lenta-2",
            "/lenta-1",
            "/lenta-0",
        ]

    def test_poner_en_cero_borra_todo(self):
        anotar("GET", "/algo", 200, 5.0)
        reiniciar()
        d = resumen()
        assert d["peticiones"] == 0
        assert d["por_pantalla"] == []
        assert d["ultimas_lentas"] == []


class TestNoSeComeLaMemoria:
    """El motor del hospital ya anda por el gigabyte. Medir no puede sumarle."""

    def test_las_rutas_distintas_tienen_tope(self):
        for i in range(MAX_RUTAS + 200):
            anotar("GET", f"/pantalla-inventada-{i}", 200, 0.01)
        assert len(resumen(limite=10_000)["por_pantalla"]) <= MAX_RUTAS

    def test_de_las_lentas_solo_se_guardan_las_ultimas(self):
        for i in range(MAX_RECIENTES + 50):
            anotar("GET", f"/lenta/{i}", 200, SEGUNDOS_PARA_AVISAR + 1)
        assert len(resumen()["ultimas_lentas"]) == MAX_RECIENTES

    def test_mil_glosas_distintas_son_una_sola_fila(self):
        for i in range(1000):
            anotar("GET", f"/glosas/{i}", 200, 0.02)
        rutas = [f["ruta"] for f in resumen(limite=10_000)["por_pantalla"]]
        assert rutas == ["GET /glosas/{n}"]


class TestMedirNoPuedeTumbarUnaPeticion:
    def test_aguanta_valores_raros(self):
        anotar("", "", 0, 0.0)
        anotar("GET", "/x", 200, -1.0)
        assert resumen()["peticiones"] == 2

    def test_el_cronometro_anota_al_salir(self):
        from app.services.tiempos_peticiones import cronometrar

        with cronometrar("GET", "/con-cronometro") as c:
            c.estado = 200
        fila = resumen()["por_pantalla"][0]
        assert fila["ruta"] == "GET /con-cronometro"
        assert fila["veces"] == 1


class TestEstaEnchufadoDeVerdad:
    """Un medidor que nadie llama no mide nada."""

    def test_el_middleware_existe_y_llama_a_anotar(self):
        import inspect

        from app import main

        fuente = inspect.getsource(main)
        assert "async def _cronometro_middleware" in fuente
        assert "from app.services.tiempos_peticiones import anotar" in fuente

    def test_el_cronometro_envuelve_a_los_demas(self):
        """Starlette monta los middlewares al revés: el último declarado es el
        que envuelve a todos. Si deja de ser el último, mide de menos."""
        import inspect
        import re

        from app import main

        fuente = inspect.getsource(main)
        declarados = re.findall(r'@app\.middleware\("http"\)\s*\nasync def (\w+)', fuente)
        assert declarados, "no se encontró ningún middleware http"
        assert declarados[-1] == "_cronometro_middleware", (
            f"el cronómetro tiene que declararse de último; hoy el último es {declarados[-1]}"
        )

    def test_la_pantalla_de_diagnostico_lo_muestra(self):
        from pathlib import Path

        html = Path("static/index.html").read_text(encoding="utf-8")
        assert "cargarLentitud()" in html
        assert "/admin/diagnostico/lentitud" in html
        assert "diag-lentitud" in html

    def test_las_rutas_existen(self):
        from app.api.routers import diagnostico

        rutas = {r.path for r in diagnostico.router.routes}
        assert "/admin/diagnostico/lentitud" in rutas
        assert "/admin/diagnostico/lentitud/reiniciar" in rutas
