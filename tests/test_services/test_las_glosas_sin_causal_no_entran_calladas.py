"""59 de 135 glosas entraron sin código de causal, y nadie se enteró.

31-08-2026, quinta idea del repaso de diseño.

En el export real de la base del hospital, **59 de las 135 glosas** salieron
**sin código de causal** — el 44 %. Entraron en silencio: la importación decía
«135 importadas» y nada más.

Sin causal el motor **redacta a ciegas**. No sabe contra qué está defendiendo,
así que puede contestar la forma cuando la glosa era de fondo, o alegar
soportes cuando lo que objetaron fue la tarifa. El escrito sale bien redactado
y contesta otra cosa.

**Esto no se arregla desde el código: el dato no viene en el archivo.** La
columna de causal no está, y ningún cambio de programa la inventa —inventarla
sería justo lo que este motor no puede hacer—.

Lo que sí se puede hacer, y es lo que se hizo: **dejar de importarlas en
silencio**. La pantalla ahora dice cuántas son, qué porcentaje del lote, unos
ejemplos con factura y entidad, y que el arreglo es pedirle la columna a quien
manda el archivo. Con eso el reclamo sale con evidencia y no con una impresión.

Se cuenta en el punto exacto donde el dato se pierde: cuando se completa el
plan de cada glosa con su causal y no hay ninguna que asignarle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.recepcion_service import ResumenImportacion

RAIZ = Path(__file__).resolve().parents[2]
SERVICIO = (RAIZ / "app" / "services" / "recepcion_service.py").read_text(encoding="utf-8")
PANTALLA = (RAIZ / "static" / "importar-recepcion.html").read_text(encoding="utf-8")


class TestElResumenLasCuenta:
    def test_arranca_en_cero(self):
        assert ResumenImportacion().sin_causal == 0

    def test_cuenta_cada_una(self):
        r = ResumenImportacion()
        r.registrar_sin_causal("HUS0000497616", "NUEVA EPS")
        r.registrar_sin_causal("HUS0000543138", "NUEVA EPS")
        assert r.sin_causal == 2

    def test_guarda_factura_y_entidad_para_poder_reclamar(self):
        """Un número suelto no sirve para reclamar: hay que poder decir cuáles."""
        r = ResumenImportacion()
        r.registrar_sin_causal("HUS0000497616", "NUEVA EPS")
        assert r.sin_causal_detalle == [{"factura": "HUS0000497616", "entidad": "NUEVA EPS"}]

    def test_sin_numero_no_inventa_uno(self):
        r = ResumenImportacion()
        r.registrar_sin_causal("", "")
        assert r.sin_causal_detalle[0]["factura"] == "(sin número)"

    def test_la_muestra_no_crece_sin_limite(self):
        """Un lote entero sin causal no puede reventar la respuesta."""
        r = ResumenImportacion()
        for i in range(80):
            r.registrar_sin_causal(f"HUS{i}", "X")
        assert r.sin_causal == 80
        assert len(r.sin_causal_detalle) == 50

    @pytest.mark.parametrize("campo", ["sin_causal", "sin_causal_detalle"])
    def test_viaja_al_frontend(self, campo: str):
        assert campo in ResumenImportacion().to_dict()


class TestSeCuentaDondeElDatoSePierde:
    def test_en_el_punto_donde_no_hay_causal_que_asignar(self):
        i = SERVICIO.index("cod = por_factura.get(clave_fac)")
        bloque = SERVICIO[i : i + 900]
        assert "if not cod:" in bloque
        assert "registrar_sin_causal" in bloque

    def test_sigue_procesando_las_demas(self):
        """Contar no puede convertirse en detener la importación."""
        i = SERVICIO.index("resumen.registrar_sin_causal(")
        assert "continue" in SERVICIO[i : i + 300]


class TestLaPantallaLoDiceYExplicaQueHacer:
    def test_muestra_el_numero_y_el_porcentaje(self):
        assert "d.sin_causal" in PANTALLA
        assert "pct" in PANTALLA

    def test_explica_por_que_importa(self):
        """Un aviso que no dice qué se pierde no cambia nada."""
        assert "no sabe contra qué está defendiendo" in PANTALLA

    def test_dice_que_no_lo_arregla_el_programa(self):
        """Es lo que evita que el auditor espere un arreglo que no va a venir."""
        assert "no se arregla desde el programa" in PANTALLA

    def test_dice_a_quien_pedirle_el_dato(self):
        assert "quien lo envía" in PANTALLA

    def test_muestra_ejemplos_concretos(self):
        assert "sin_causal_detalle" in PANTALLA
        assert "Ejemplos:" in PANTALLA

    def test_no_sale_si_no_falta_ninguna(self):
        i = PANTALLA.index("const nSc = d.sin_causal")
        assert "if(nSc > 0)" in PANTALLA[i : i + 200]

    def test_usa_el_ambar_nuevo_no_el_rojo_de_error(self):
        """Falta un dato: es «revisar», no «la evidencia lo contradice»."""
        i = PANTALLA.index("const nSc = d.sin_causal")
        assert "#A67500" in PANTALLA[i : i + 1400]
