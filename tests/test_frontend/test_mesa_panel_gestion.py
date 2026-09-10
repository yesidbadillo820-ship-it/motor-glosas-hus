"""El panel de gestión y la lectura del motivo en la mesa (07-09-2026).

En una audiencia, cuando la EPS sostiene una glosa, la pregunta es siempre
la misma: **¿qué tenemos para refutar esto?** Antes había que salir a otra
pantalla a buscarlo, con la EPS esperando.

Lo que estas pruebas cuidan:

  · que el panel arranque OCULTO — el defecto que se atrapó probándolo en
    Chromium: `.mesa-drawer{display:flex}` le gana al atributo `hidden`, y el
    panel quedaba siempre presente con su fondo invisible tapando la página
    entera. Ningún clic funcionaba en toda la pantalla;
  · que el motivo largo se pueda leer completo sin romper la tabla;
  · y que la insignia de soportes distinga «no tiene» de «todavía no sé».
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parents[2] / "static" / "index.html").read_text(encoding="utf-8")


def _regla(sel: str) -> str:
    m = re.search(re.escape(sel) + r"\{([^}]*)\}", HTML)
    return m.group(1) if m else ""


def _funcion(nombre: str) -> str:
    """El cuerpo COMPLETO de una función, hasta la siguiente declaración.

    Cortar por un número fijo de caracteres deja fuera el final de las
    funciones largas y la prueba falla por el recorte, no por el código.
    """
    i = HTML.index(f"function {nombre}(")
    siguiente = HTML.find("\nfunction ", i + 1)
    fin = siguiente if siguiente > 0 else i + 6000
    return HTML[i:fin]


class TestElPanelArrancaOculto:
    def test_el_hidden_le_gana_al_display_flex(self):
        """El defecto real: sin esta regla el panel está SIEMPRE presente y su
        fondo invisible intercepta todos los clics de la página."""
        assert _regla(".mesa-drawer[hidden]"), "falta la regla que respeta el atributo hidden"
        assert "display:none" in _regla(".mesa-drawer[hidden]")

    def test_el_marcado_nace_con_hidden(self):
        assert 'id="mesa-drawer" class="mesa-drawer" hidden' in HTML

    def test_se_puede_cerrar_de_dos_maneras(self):
        """Por el botón y tocando fuera: en una mesa se cierra rápido."""
        assert 'onclick="mesaCerrarPanel()"' in HTML
        assert HTML.count('onclick="mesaCerrarPanel()"') >= 2


class TestLeerElMotivoCompleto:
    def test_hay_una_fila_que_se_despliega(self):
        """500 caracteres en un globo del navegador no se leen; en una fila sí."""
        assert "function mesaDesplegar" in HTML
        assert 'class="mesa-detalle"' in HTML
        assert "white-space:pre-wrap" in _regla(".mesa-detalle td")

    def test_la_fila_de_detalle_nace_plegada(self):
        assert 'class="mesa-detalle" id="mesa-det-' in HTML
        bloque = HTML[HTML.index('class="mesa-detalle" id="mesa-det-') :][:200]
        assert "hidden" in bloque

    def test_el_aviso_de_lo_que_falta_decidir_va_ahi_tambien(self):
        assert "l.aviso ?" in _funcion("mesaPintar")


class TestLaInsigniaDeSoportes:
    def test_distingue_no_tiene_de_no_se_sabe(self):
        """Decir «no tiene soportes» mientras el índice se arma manda a
        aceptar una glosa que sí estaba soportada."""
        cuerpo = _funcion("mesaInsigniaSoportes")
        assert "CON_SOPORTES" in cuerpo and "SIN_SOPORTES" in cuerpo
        assert "mesa-sop duda" in cuerpo, "falta el estado «todavía no sé»"
        # Los tres estados tienen color propio.
        for clase in (".mesa-sop.si", ".mesa-sop.no", ".mesa-sop.duda"):
            assert _regla(clase), f"falta el color de {clase}"

    def test_las_insignias_llegan_aparte_para_no_frenar_la_tabla(self):
        """Consultar el índice puede tardar; la tabla tiene que pintarse ya."""
        assert "function mesaTraerSoportes" in HTML
        assert "'/conciliaciones/mesa/' + MESA.id + '/soportes'" in HTML

    def test_al_llegar_no_repinta_la_tabla_entera(self):
        """El auditor puede estar escribiendo en un renglón cuando llegan."""
        cuerpo = _funcion("mesaTraerSoportes")
        assert "cells[5].innerHTML" in cuerpo
        assert "mesaPintar()" not in cuerpo


class TestElPanelTraeLoQueSirveParaRefutar:
    @pytest.mark.parametrize(
        "seccion",
        [
            "Lo que objeta la EPS",
            "Nuestro dictamen",
            "Soportes de la factura",
            "Comentarios del equipo",
        ],
    )
    def test_las_cuatro_secciones(self, seccion):
        assert seccion in _funcion("mesaPintarPanel")

    def test_un_renglon_sin_glosa_del_motor_lo_dice_en_vez_de_fallar(self):
        """Hay facturas que la EPS glosa y que el motor nunca recibió."""
        cuerpo = _funcion("mesaPintarPanel")
        assert "d.glosa_id" in cuerpo
        assert "no está enlazado a una glosa del motor" in cuerpo

    def test_la_plata_del_panel_usa_el_formato_unico(self):
        cuerpo = _funcion("mesaPintarPanel")
        assert "fmtCOP(" in cuerpo and "toLocaleString" not in cuerpo


class TestLaTablaQuedoMasLimpia:
    def test_filas_alternas_y_resaltado_al_pasar(self):
        """Con 146 renglones la cuadrícula completa cansa y se pierde la fila."""
        assert _regla(".mesa-tabla tbody tr:nth-child(even)")
        assert _regla(".mesa-tabla tbody tr:hover")

    def test_las_cifras_se_alinean_por_digito(self):
        """Sin `tabular-nums` las columnas de plata bailan y no se comparan."""
        assert "tabular-nums" in _regla(".mesa-tabla .num,.mesa-tabla input.num")

    def test_el_encabezado_sigue_fijo_y_la_tabla_en_su_caja(self):
        assert "position:sticky" in _regla(".mesa-tabla th")
        assert "overflow:auto" in _regla(".mesa-tabla-wrap")


# ═══════════════════════════════════════════════════════════════════════
#  Subir soportes desde la mesa, y no pintar nunca una caja en blanco
# ═══════════════════════════════════════════════════════════════════════


class TestNingunComponenteEnBlanco:
    """El caso que lo enseñó: «3 soportes» y tres renglones vacíos.

    No falló nada; simplemente no se veía nada. En una audiencia eso se lee
    como «esta factura no tiene con qué defenderse», y no era verdad.
    """

    def test_hay_una_sola_funcion_que_pinta_los_soportes(self):
        assert "function mesaPintarSoportes(" in HTML, (
            "si cada sitio lo pinta a su manera, el estado de error se olvida en uno"
        )

    def test_los_cinco_estados_estan_contemplados(self):
        cuerpo = _funcion("mesaPintarSoportes")
        for estado in ("CON_SOPORTES", "SIN_SOPORTES", "DATOS_INVALIDOS", "SIN_INDICE"):
            assert estado in cuerpo, f"falta el estado {estado}"

    def test_una_lista_vacia_con_cuantos_mayor_que_cero_es_error(self):
        """Decía que había 3 y no llegó ninguno legible: eso es un error."""
        cuerpo = _funcion("mesaPintarSoportes")
        assert "filter(" in cuerpo and "a.nombre" in cuerpo, (
            "hay que descartar los archivos sin nombre, que son los renglones en blanco"
        )
        assert "no se pudo leer ninguno" in cuerpo, (
            "sin este aviso, la caja queda vacía y parece que no hay soportes"
        )

    def test_un_error_no_se_pinta_como_ausencia(self):
        cuerpo = _funcion("mesaPintarSoportes")
        i_err = cuerpo.index("DATOS_INVALIDOS")
        assert "mesa-sop-err" in cuerpo[i_err : i_err + 300], (
            "un fallo del buscador tiene que verse como fallo, no como un dato"
        )
        assert ".mesa-sop-err{" in HTML, "sin el estilo, el error se lee igual que el texto normal"

    def test_indexando_nunca_dice_que_no_hay(self):
        cuerpo = _funcion("mesaPintarSoportes")
        final = cuerpo[cuerpo.index("INDEXANDO") if "INDEXANDO" in cuerpo else -400 :]
        assert "Todavía no se puede saber" in cuerpo
        assert "mesa-sop-duda" in final or "mesa-sop-duda" in cuerpo


class TestSubirSoportesEnLaMesa:
    def test_la_caja_de_subida_existe(self):
        assert "function mesaCajaDeSubida(" in HTML
        assert "function mesaSubirSoporte(" in HTML

    def test_solo_deja_elegir_pdf_e_imagenes(self):
        cuerpo = _funcion("mesaCajaDeSubida")
        assert "accept=" in cuerpo
        assert ".pdf" in cuerpo and "image/png" in cuerpo
        assert ".xlsx" not in cuerpo, "un Excel hay que pasarlo antes a PDF"

    def test_el_peso_se_revisa_antes_de_mandarlo(self):
        """En la red del hospital, subir 40 MB para que los rechacen son minutos."""
        cuerpo = _funcion("mesaSubirSoporte")
        assert "50*1024*1024" in cuerpo.replace(" ", ""), (
            "el tope tiene que ser el mismo que el del servidor"
        )
        assert "f.size" in cuerpo
        i = cuerpo.index("f.size")
        assert "return" in cuerpo[i : i + 400], "si pesa de más, no debe llegar a mandarse"

    def test_hay_estado_de_carga_y_el_boton_se_bloquea(self):
        """Un doble clic no puede subir el mismo soporte dos veces."""
        cuerpo = _funcion("mesaSubirSoporte")
        assert "btn.disabled = true" in cuerpo
        assert "Subiendo…" in cuerpo
        assert "mesa-spinner" in cuerpo
        assert ".mesa-spinner{" in HTML, "sin el estilo no se ve que está trabajando"

    def test_el_boton_se_desbloquea_pase_lo_que_pase(self):
        cuerpo = _funcion("mesaSubirSoporte")
        assert "finally" in cuerpo, "si falla la red, el botón quedaría muerto para siempre"
        i = cuerpo.index("finally")
        assert "btn.disabled = false" in cuerpo[i:]

    def test_el_error_del_servidor_se_muestra_tal_cual(self):
        cuerpo = _funcion("mesaSubirSoporte")
        assert "e.detail" in cuerpo, (
            "el motivo del rechazo lo escribe el motor en español; hay que mostrarlo"
        )

    def test_la_animacion_respeta_a_quien_la_desactiva(self):
        assert "prefers-reduced-motion" in HTML

    def test_al_subir_se_refresca_la_insignia_de_la_tabla(self):
        cuerpo = _funcion("mesaSubirSoporte")
        assert "mesaCargarSubidos" in cuerpo
