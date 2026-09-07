"""Ninguna ruta del motor puede pisar a otra.

Lo que lo hizo necesario, el 26-08-2026: se agregó un router nuevo con la ruta
`GET /mi-dia` sin ver que **esa ruta ya existía** desde antes en `health.py` —
era el resumen personal del gestor. FastAPI se queda con la primera que se
registre, así que la vieja quedó muerta **sin que nada lo dijera**: no hay
error, no hay aviso, la pantalla simplemente empieza a recibir otra cosa.

Es exactamente la forma en que «Salud Total» estuvo tres meses devolviendo
«Not Found». Esta prueba lo convierte en algo que se ve antes de subirlo.
"""

from __future__ import annotations

from collections import defaultdict

from app.main import app

# Métodos que FastAPI agrega solo y no son rutas de verdad.
_IGNORAR = {"HEAD", "OPTIONS"}


def _rutas_por_metodo() -> dict[tuple[str, str], list[str]]:
    vistas: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ruta in app.routes:
        camino = getattr(ruta, "path", None)
        if not camino:
            continue
        metodos = getattr(ruta, "methods", None) or set()
        nombre = getattr(ruta, "name", "") or getattr(ruta, "endpoint", None).__name__
        for metodo in metodos:
            if metodo in _IGNORAR:
                continue
            vistas[(metodo, camino)].append(str(nombre))
    return vistas


class TestNingunaRutaPisaAOtra:
    def test_no_hay_dos_rutas_con_el_mismo_camino_y_metodo(self):
        repetidas = {
            clave: quienes for clave, quienes in _rutas_por_metodo().items() if len(quienes) > 1
        }
        assert not repetidas, (
            "Hay rutas repetidas y solo responde la primera que se registró; la otra "
            "queda muerta sin decirlo:\n"
            + "\n".join(f"  {m} {c} → {', '.join(q)}" for (m, c), q in sorted(repetidas.items()))
        )

    def test_la_ruta_vieja_de_mi_dia_sigue_viva(self):
        """El caso concreto que lo destapó, fijado aparte para que se lea."""
        caminos = {getattr(r, "path", "") for r in app.routes}
        assert "/mi-dia" in caminos, "el resumen personal del gestor de health.py"
        assert "/mi-dia/tablero" in caminos, "el tablero de tres columnas"

    def test_hay_rutas_que_revisar(self):
        """Si el conteo se cae a cero, la prueba estaría pasando por vacía."""
        assert len(_rutas_por_metodo()) > 100
