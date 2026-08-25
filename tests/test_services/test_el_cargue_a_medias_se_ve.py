"""Un cargue que se corta a mitad tiene que decir qué SÍ quedó (20-08-2026).

Las fuentes de Pre-auditoría (Radicación y DGREPORT) se cargan por bloques, y
cada bloque se confirma en la base apenas termina. Eso está bien pensado: si
el proceso se interrumpe, lo ya guardado no se pierde y volver a subir el
mismo archivo retoma donde quedó, porque el upsert nunca duplica.

Lo que faltaba era contarlo. Si reventaba en el bloque 5 de 10, la excepción
salía derecho y el auditor veía un error a secas, **como si no se hubiera
guardado nada** — cuando en realidad los cuatro bloques anteriores ya estaban
confirmados. Eso lleva a rehacer trabajo que no hace falta o, peor, a dudar de
lo que sí quedó.
"""

from __future__ import annotations

from app.services import preauditoria_service as svc


class _DbFalsa:
    """Lo mínimo que usa `_upsert_por_bloques`."""

    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


def _filas(n: int) -> list[dict]:
    return [{"factura": f"HUS{i:07d}"} for i in range(n)]


class TestCuandoTodoSaleBien:
    def test_reporta_completo_y_cuantas_filas(self):
        db = _DbFalsa()
        vistas = []

        def aplicar(bloque):
            vistas.extend(bloque)
            return {"nuevas": len(bloque), "actualizadas": 0, "sin_cambio": 0}

        r = svc._upsert_por_bloques(db, _filas(250), aplicar)
        assert r["completo"] is True
        assert r["filas_procesadas"] == 250
        assert r["nuevas"] == 250
        assert "error" not in r
        assert db.rollbacks == 0

    def test_un_archivo_vacio_no_es_un_error(self):
        r = svc._upsert_por_bloques(_DbFalsa(), [], lambda b: {})
        assert r["completo"] is True
        assert r["filas_procesadas"] == 0


class TestCuandoSeCortaAMitad:
    """El caso que antes se veía como «no se guardó nada»."""

    def _corta_en_el_segundo_bloque(self):
        estado = {"bloques": 0}

        def aplicar(bloque):
            estado["bloques"] += 1
            if estado["bloques"] == 2:
                raise RuntimeError("se cayó la base")
            return {"nuevas": len(bloque), "actualizadas": 0, "sin_cambio": 0}

        return aplicar

    def test_no_revienta_hacia_afuera(self):
        """El auditor no puede quedarse con un error genérico de 500."""
        r = svc._upsert_por_bloques(
            _DbFalsa(), _filas(svc.TAM_BLOQUE_UPSERT * 3), self._corta_en_el_segundo_bloque()
        )
        assert r["completo"] is False

    def test_dice_cuantas_SI_quedaron_guardadas(self):
        r = svc._upsert_por_bloques(
            _DbFalsa(), _filas(svc.TAM_BLOQUE_UPSERT * 3), self._corta_en_el_segundo_bloque()
        )
        assert r["filas_procesadas"] == svc.TAM_BLOQUE_UPSERT
        assert r["nuevas"] == svc.TAM_BLOQUE_UPSERT

    def test_y_le_dice_al_auditor_qué_hacer(self):
        r = svc._upsert_por_bloques(
            _DbFalsa(), _filas(svc.TAM_BLOQUE_UPSERT * 3), self._corta_en_el_segundo_bloque()
        )
        assert "SÍ quedaron guardadas" in r["error"]
        assert "no duplica" in r["error"]

    def test_suelta_la_transaccion_a_medias(self):
        """Sin el rollback, la sesión queda envenenada y todo lo que venga
        después en esa petición falla sin explicación."""
        db = _DbFalsa()
        svc._upsert_por_bloques(
            db, _filas(svc.TAM_BLOQUE_UPSERT * 3), self._corta_en_el_segundo_bloque()
        )
        assert db.rollbacks == 1

    def test_si_revienta_en_el_primer_bloque_lo_dice_igual(self):
        def siempre_falla(bloque):
            raise RuntimeError("nada que hacer")

        r = svc._upsert_por_bloques(_DbFalsa(), _filas(10), siempre_falla)
        assert r["completo"] is False
        assert r["filas_procesadas"] == 0
        assert "fila 1 de 10" in r["error"]
