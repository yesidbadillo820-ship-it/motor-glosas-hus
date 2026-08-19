"""Se quitó el ticker de noticias del sector salud — 19-08-2026.

Yesid: «quitar eso de noticias que nunca sirvió para nada».

Tenía razón, y por una razón que él no podía saber: **el motor ya se había
removido en la limpieza de mayo de 2026**. Lo que quedó fue la carcasa —
`fetch_noticias()` devolvía lista vacía y el programador de las 4 horas no
hacía nada—, así que el diagnóstico decía «0 noticias indexadas. El scheduler
corre cada 4h» y el botón «Refrescar noticias» no traía nunca nada.

Un aviso ámbar permanente que nadie puede resolver enseña a ignorar los avisos
ámbar. Eso es peor que no tenerlo.

Se borró todo: los dos servicios de mentira, el router con sus 3 rutas, la
tabla, la sección del diagnóstico, el ticker del tablero y el botón. Estas
pruebas existen por la lección de «Salud Total»: aquella pantalla estuvo tres
meses dando «Not Found» porque se borró el router y el JavaScript siguió
llamándolo. Acá se borra de los dos lados a la vez.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _index() -> str:
    return (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")


class TestNoQuedaNadaEnElBackend:
    def test_no_estan_los_archivos(self):
        for ruta in (
            "app/services/noticias_salud_co.py",
            "app/services/noticias_scheduler.py",
            "app/api/routers/noticias.py",
        ):
            assert not (RAIZ / ruta).exists(), f"{ruta} sigue ahí"

    def test_el_motor_no_lo_arranca_ni_lo_importa(self):
        fuente = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
        assert "noticias" not in fuente.lower()

    def test_no_queda_el_modelo_de_la_tabla(self):
        fuente = (RAIZ / "app" / "models" / "db.py").read_text(encoding="utf-8")
        assert "NoticiaSaludRecord" not in fuente

    def test_el_diagnostico_ya_no_lo_revisa(self):
        """Se mira el CÓDIGO, no los comentarios: explicar por qué se quitó una
        cosa no puede hacer fallar la prueba de que se quitó."""
        fuente = (RAIZ / "app" / "api" / "routers" / "diagnostico.py").read_text(encoding="utf-8")
        vivas = [
            ln
            for ln in fuente.splitlines()
            if "oticia" in ln.lower() and not ln.strip().startswith("#")
        ]
        assert not vivas, vivas

    def test_la_aplicacion_arranca_sin_ello(self):
        """La prueba de fondo: importar la app entera no puede reventar."""
        from app.main import app

        rutas = {getattr(r, "path", "") for r in app.routes}
        assert not [r for r in rutas if "noticias" in r], rutas


class TestNoQuedaNadaEnLaPantalla:
    def test_no_queda_javascript_llamando_a_rutas_borradas(self):
        """El error de «Salud Total»: el JS llamando a un router que ya no existe."""
        texto = _index()
        for llamada in ("/noticias/recientes", "/noticias/refrescar", "/noticias/stats"):
            assert llamada not in texto, f"el JavaScript sigue llamando a {llamada}"

    def test_no_quedan_funciones_huerfanas(self):
        texto = _index()
        for fn in ("cargarTickerNoticias", "diagRefrescarNoticias"):
            assert fn not in texto, f"{fn} quedó suelta"

    def test_no_queda_el_ticker_del_tablero(self):
        assert 'id="noticias-ticker"' not in _index()

    def test_no_queda_el_boton_del_diagnostico(self):
        assert "Refrescar noticias" not in _index()

    def test_el_resto_del_diagnostico_sigue_en_pie(self):
        """Se quitó un botón, no la pantalla."""
        texto = _index()
        for sigue in ("diagReindexarSoportes()", "cargarIAStatus()", "cargarDiagnostico()"):
            assert sigue in texto, f"se llevó por delante {sigue}"
