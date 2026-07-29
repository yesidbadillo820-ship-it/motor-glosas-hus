"""Habilitar un pagador para el robot es agregar una ficha, no tocar código.

Antes había tres sitios que había que acordarse de mantener iguales:

    lotes_service.PAGADORES_SOPORTADOS = {"COOSALUD"}
    lotes_service.parsear_excel_coosalud(...)      llamado por su nombre
    agente_lotes.BOTS_POR_TIPO = {"RESPONDER_COOSALUD": ...}

Los bots de SIMED, SAVIA, EMSSANAR, VCO, FOMAG y MUTUAL SER ya vivían en
`tools/`. Funcionaban. Ninguno se podía encolar sin editar esos tres sitios y
desplegar.
"""

from __future__ import annotations

import pytest

from app.services import lotes_service, perfiles_lote


class TestRegistro:
    def test_coosalud_y_simed_estan_habilitados(self):
        assert set(perfiles_lote.pagadores()) >= {"COOSALUD", "SIMED"}

    def test_cada_perfil_dice_que_archivo_subir(self):
        """Un pagador sin ayuda obliga al auditor a preguntarle a alguien."""
        for p in perfiles_lote.PERFILES:
            assert p.ayuda.strip(), p.pagador
            assert p.nombre.strip()
            assert p.leer is not None

    def test_el_tipo_de_tarea_sale_del_pagador(self):
        assert perfiles_lote.obtener("SIMED").tarea == "RESPONDER_SIMED"
        assert perfiles_lote.obtener("COOSALUD").tarea == "RESPONDER_COOSALUD"

    def test_obtener_es_tolerante(self):
        assert perfiles_lote.obtener(" simed ") is not None
        assert perfiles_lote.obtener("SANITAS") is None


class TestUnaSolaFuente:
    """Los tres sitios leen del mismo registro."""

    def test_el_servicio_ofrece_lo_mismo_que_el_registro(self):
        assert lotes_service.PAGADORES_SOPORTADOS() == set(perfiles_lote.pagadores())

    def test_el_agente_atiende_todo_lo_que_la_app_ofrece(self):
        """El fallo que esto impide: la aplicación ofrece un pagador, el
        auditor encola el lote, y el agente no sabe qué bot correr — la tarea
        se queda en la cola sin que nadie entienda por qué."""
        ofrecidas = {p.tarea for p in perfiles_lote.PERFILES}
        atendidas = set(perfiles_lote.bots_por_tarea())
        assert ofrecidas == atendidas

    def test_cada_bot_declarado_existe_en_el_repositorio(self):
        from pathlib import Path

        tools = Path(__file__).resolve().parent.parent.parent / "tools"
        for tarea, bot in perfiles_lote.bots_por_tarea().items():
            assert (tools / bot).exists(), f"{tarea} apunta a {bot}, que no existe"


class TestNormalizacion:
    """Cada bot lee su Excel a su manera; el lote necesita una sola forma."""

    def test_la_forma_normalizada_tiene_los_cuatro_datos(self):
        f = perfiles_lote.FacturaLote(grupos=2, glosas=5, calidad=1, requiere_soporte=True)
        assert (f.grupos, f.glosas, f.calidad, f.requiere_soporte) == (2, 5, 1, True)

    def test_simed_no_separa_calidad(self):
        """SIMED entrega la respuesta ya redactada: una fila por objeción, sin
        distinguir pertinencia. Declararlo evita que la pantalla ofrezca una
        casilla que no hace nada."""
        assert perfiles_lote.obtener("SIMED").soporta_calidad is False
        assert perfiles_lote.obtener("COOSALUD").soporta_calidad is True


class TestElCatalogoLlegaALaPantalla:
    def test_el_catalogo_trae_lo_que_la_pantalla_necesita(self):
        for ficha in perfiles_lote.catalogo():
            assert {"pagador", "nombre", "ayuda", "soporta_calidad", "tarea"} <= set(ficha)

    def test_agregar_un_pagador_no_toca_el_servicio(self):
        """La prueba de la forma: si mañana se agrega MUTUAL SER al registro,
        el servicio lo ofrece sin que nadie lo edite."""
        antes = lotes_service.PAGADORES_SOPORTADOS()
        extra = perfiles_lote.PerfilLote(
            pagador="PRUEBA",
            nombre="Pagador de prueba",
            bot="responder_glosas_simed.py",
            modulo="responder_glosas_simed",
            ayuda="x",
            leer=lambda r, h, c: {},
        )
        original = perfiles_lote.PERFILES
        try:
            perfiles_lote.PERFILES = original + (extra,)
            perfiles_lote._POR_PAGADOR["PRUEBA"] = extra
            assert "PRUEBA" in lotes_service.PAGADORES_SOPORTADOS()
        finally:
            perfiles_lote.PERFILES = original
            perfiles_lote._POR_PAGADOR.pop("PRUEBA", None)
        assert lotes_service.PAGADORES_SOPORTADOS() == antes


@pytest.mark.parametrize("pagador", ["COOSALUD", "SIMED"])
def test_el_perfil_apunta_al_lector_de_su_propio_bot(pagador):
    """Que la aplicación lea el Excel distinto de como lo lee el bot sería peor
    que no leerlo: la pantalla mostraría un conteo y el bot trabajaría sobre
    otro."""
    perfil = perfiles_lote.obtener(pagador)
    assert perfil.modulo in perfil.bot.replace(".py", "")
