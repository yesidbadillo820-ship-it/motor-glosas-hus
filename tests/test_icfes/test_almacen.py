"""Lo guardado tiene que volver igual: si no, se pierde un año de trabajo."""

from __future__ import annotations

from datetime import date

from icfes.almacen import Almacen, Configuracion
from icfes.dominio import Area, CausaError
from icfes.progreso import Intento
from icfes.repaso import Tarjeta, calificar
from icfes.simulacro import TipoSimulacro, armar_simulacro, calificar_simulacro

HOY = date(2026, 8, 20)
EXAMEN = date(2027, 8, 8)


def test_un_almacen_nuevo_no_tiene_configuracion(almacen):
    assert almacen.config() is None


def test_la_configuracion_vuelve_igual(almacen, config):
    almacen.guardar_config(config)
    assert almacen.config() == config


def test_guardar_la_configuracion_dos_veces_la_reemplaza(almacen, config):
    almacen.guardar_config(config)
    nueva = Configuracion("otro", date(2027, 6, 1), 320, 6, dias_por_semana=5)
    almacen.guardar_config(nueva)
    assert almacen.config() == nueva


def test_el_archivo_se_crea_solo(tmp_path):
    ruta = tmp_path / "carpeta" / "nueva" / "progreso.db"
    with Almacen(ruta):
        pass
    assert ruta.is_file()


def test_los_intentos_vuelven_completos(almacen):
    intento = Intento(
        fecha=HOY,
        pregunta_id="MAT-001",
        area=Area.MATEMATICAS,
        competencia="Argumentación",
        tema="Porcentajes",
        acerto=False,
        segundos=95.5,
        causa=CausaError.CONCEPTO,
    )
    almacen.guardar_intento(intento)
    assert almacen.intentos() == [intento]


def test_un_intento_sin_causa_vuelve_sin_causa(almacen):
    intento = Intento(HOY, "X-1", Area.INGLES, "Uso del idioma en contexto", "t", True, 12.0)
    almacen.guardar_intento(intento)
    assert almacen.intentos()[0].causa is None


def test_los_intentos_se_pueden_filtrar_por_fecha(almacen):
    almacen.guardar_intento(
        Intento(date(2026, 1, 1), "A", Area.MATEMATICAS, "Argumentación", "t", True)
    )
    almacen.guardar_intento(Intento(HOY, "B", Area.MATEMATICAS, "Argumentación", "t", True))
    assert [i.pregunta_id for i in almacen.intentos(desde=HOY)] == ["B"]


def test_los_ids_respondidos_no_se_repiten(almacen):
    for _ in range(3):
        almacen.guardar_intento(
            Intento(HOY, "MAT-001", Area.MATEMATICAS, "Argumentación", "t", True)
        )
    assert almacen.ids_respondidos() == {"MAT-001"}


def test_una_tarjeta_que_no_existe_sale_nueva(almacen):
    t = almacen.tarjeta("NO-EXISTE")
    assert t.es_nueva and t.clave == "NO-EXISTE"


def test_la_tarjeta_vuelve_igual(almacen):
    t = calificar(Tarjeta("MAT-001"), 5, HOY, EXAMEN)
    almacen.guardar_tarjeta(t)
    assert almacen.tarjeta("MAT-001") == t


def test_guardar_la_misma_tarjeta_la_actualiza(almacen):
    primera = calificar(Tarjeta("X"), 5, HOY, EXAMEN)
    almacen.guardar_tarjeta(primera)
    segunda = calificar(primera, 5, primera.proxima_fecha, EXAMEN)
    almacen.guardar_tarjeta(segunda)
    assert len(almacen.tarjetas()) == 1
    assert almacen.tarjeta("X").repeticiones == 2


def test_el_simulacro_queda_guardado_con_su_puntaje(almacen, banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=1, maximo=40)
    r = calificar_simulacro(s, {p.id: p.correcta for p in s.preguntas}, HOY)
    almacen.guardar_simulacro(r)
    assert almacen.historial_simulacros() == [(HOY, 500)]


def test_los_simulacros_sin_todas_las_areas_no_entran_al_historial(almacen, banco):
    s = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=1)
    almacen.guardar_simulacro(calificar_simulacro(s, {}, HOY))
    assert almacen.historial_simulacros() == []


def test_el_ultimo_diagnostico_trae_las_cinco_areas(almacen, banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=2, maximo=40)
    r = calificar_simulacro(s, {p.id: p.correcta for p in s.preguntas}, HOY)
    almacen.guardar_simulacro(r)
    diag = almacen.ultimo_diagnostico()
    assert diag is not None and len(diag) == 5
    assert all(v == 100 for v in diag.values())


def test_sin_simulacros_no_hay_diagnostico(almacen):
    assert almacen.ultimo_diagnostico() is None


def test_los_datos_sobreviven_a_cerrar_y_volver_a_abrir(tmp_path, config):
    ruta = tmp_path / "p.db"
    with Almacen(ruta) as a:
        a.guardar_config(config)
        a.guardar_intento(Intento(HOY, "A", Area.INGLES, "Uso del idioma en contexto", "t", True))
    with Almacen(ruta) as a:
        assert a.config() == config
        assert len(a.intentos()) == 1
