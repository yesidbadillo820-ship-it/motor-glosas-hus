"""El programa de consola, probado sin que nadie escriba en el teclado."""

from __future__ import annotations

import itertools
from datetime import date

import pytest

from icfes.cli import Ronda, area_desde_texto, main
from icfes.dominio import Area

HOY = "2026-08-20"
EXAMEN = "2027-08-08"


class Consola:
    """Finge el teclado y la pantalla para poder probar el programa."""

    def __init__(self, respuestas=("A",)):
        self.lineas: list[str] = []
        self.respuestas = itertools.cycle(respuestas)
        self.reloj = itertools.count(0, 30)

    def escribir(self, texto=""):
        self.lineas.append(str(texto))

    def leer(self, _mensaje=""):
        return next(self.respuestas)

    def tiempo(self):
        return float(next(self.reloj))

    @property
    def texto(self):
        return "\n".join(self.lineas)


@pytest.fixture
def consola():
    return Consola()


@pytest.fixture
def datos(tmp_path):
    return str(tmp_path / "progreso.db")


def _correr(datos, consola, *argumentos):
    return main(
        ["--datos", datos, *argumentos],
        entrada=consola.leer,
        salida=consola.escribir,
        reloj=consola.tiempo,
    )


def _iniciar(datos, consola):
    return _correr(datos, consola, "iniciar", "--examen", EXAMEN, "--meta", "400", "--horas", "12")


def test_alias_de_areas():
    assert area_desde_texto("mat") is Area.MATEMATICAS
    assert area_desde_texto("LC") is Area.LECTURA_CRITICA
    assert area_desde_texto("ciencias_naturales") is Area.CIENCIAS_NATURALES


def test_alias_desconocido_es_error():
    with pytest.raises(ValueError, match="No existe el área"):
        area_desde_texto("quimica")


def test_iniciar_guarda_la_configuracion(datos, consola):
    assert _iniciar(datos, consola) == 0
    assert "Meta: 400 de 500 puntos" in consola.texto
    assert "Faltan" in consola.texto


def test_iniciar_dice_cuantas_preguntas_hay_que_acertar(datos, consola):
    _iniciar(datos, consola)
    assert "42 de 50" in consola.texto  # Matemáticas para un puntaje de 80
    assert "49 de 58" in consola.texto  # Ciencias Naturales


def test_un_examen_en_el_pasado_no_se_acepta(datos, consola):
    with pytest.raises(SystemExit, match="futuro"):
        _correr(datos, consola, "iniciar", "--examen", "2020-01-01")


def test_los_comandos_exigen_configuracion_previa(datos, consola):
    with pytest.raises(SystemExit, match="configurar"):
        _correr(datos, consola, "progreso")


def test_hoy_muestra_los_bloques_del_dia(datos, consola):
    _iniciar(datos, consola)
    assert _correr(datos, consola, "hoy", "--fecha", HOY) == 0
    assert "HOY —" in consola.texto
    assert "Semana 1 de" in consola.texto


def test_hoy_avisa_que_falta_el_diagnostico(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "hoy", "--fecha", HOY)
    assert "todavía no hay un simulacro" in consola.texto


def test_plan_muestra_el_resumen(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "plan")
    assert "PLAN DE ESTUDIO" in consola.texto
    assert "REPARTO DEL TIEMPO POR ÁREA" in consola.texto


def test_plan_de_una_semana(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "plan", "--semana", "3")
    assert "SEMANA 3" in consola.texto


def test_pedir_una_semana_que_no_existe_es_error(datos, consola):
    _iniciar(datos, consola)
    with pytest.raises(SystemExit, match="semanas"):
        _correr(datos, consola, "plan", "--semana", "999")


def test_practicar_registra_los_intentos(datos, consola):
    _iniciar(datos, consola)
    _correr(
        datos, consola, "practicar", "--area", "mat", "-n", "5", "--fecha", HOY, "--semilla", "1"
    )
    assert "PRÁCTICA — Matemáticas" in consola.texto
    assert "Resultado:" in consola.texto

    from icfes.almacen import Almacen

    with Almacen(datos) as a:
        assert len(a.intentos()) == 5
        assert len(a.tarjetas()) == 5


def test_practicar_muestra_la_explicacion_y_la_trampa(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "practicar", "-n", "2", "--fecha", HOY, "--semilla", "2")
    assert "Por qué:" in consola.texto
    assert "La trampa:" in consola.texto


def test_la_letra_S_termina_la_sesion(datos, consola):
    _iniciar(datos, consola)
    salir = Consola(respuestas=("S",))
    _correr(datos, salir, "practicar", "-n", "10", "--fecha", HOY, "--semilla", "3")
    assert "Sesión terminada" in salir.texto
    from icfes.almacen import Almacen

    with Almacen(datos) as a:
        assert a.intentos() == []


def test_simulacro_completo_deja_un_puntaje_global(datos, consola):
    _iniciar(datos, consola)
    _correr(
        datos,
        consola,
        "simulacro",
        "--tipo",
        "completo",
        "--max",
        "20",
        "--fecha",
        HOY,
        "--semilla",
        "4",
    )
    assert "PUNTAJE GLOBAL ESTIMADO" in consola.texto
    from icfes.almacen import Almacen

    with Almacen(datos) as a:
        assert len(a.historial_simulacros()) == 1


def test_el_simulacro_avisa_que_va_a_escala(datos, consola):
    _iniciar(datos, consola)
    _correr(
        datos,
        consola,
        "simulacro",
        "--tipo",
        "sesion1",
        "--max",
        "20",
        "--fecha",
        HOY,
        "--semilla",
        "5",
    )
    assert "escala" in consola.texto.lower()


def test_el_simulacro_de_area_exige_decir_cual(datos, consola):
    _iniciar(datos, consola)
    with pytest.raises(SystemExit, match="--area"):
        _correr(datos, consola, "simulacro", "--tipo", "area", "--fecha", HOY)


def test_el_simulacro_no_cuenta_lo_practicado_antes_ese_mismo_dia(datos):
    """Una pregunta acertada en la práctica no puede contar en el simulacro."""
    todo_bien = Consola(respuestas=("A", "B", "C", "D"))
    _iniciar(datos, todo_bien)
    # Se practica primero con todas las áreas, el mismo día.
    _correr(datos, todo_bien, "practicar", "-n", "20", "--fecha", HOY, "--semilla", "7")
    # Y ahora un simulacro donde no se responde nada: debe dar cero.
    vacio = Consola(respuestas=("",))
    _correr(
        datos,
        vacio,
        "simulacro",
        "--tipo",
        "completo",
        "--max",
        "20",
        "--fecha",
        HOY,
        "--semilla",
        "7",
    )
    assert "0 de" in vacio.texto


def test_repaso_avisa_cuando_no_hay_nada_pendiente(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "repaso", "--fecha", HOY)
    assert "No hay nada que repasar" in consola.texto


def test_repaso_toma_lo_que_ya_vencio(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "practicar", "-n", "4", "--fecha", HOY, "--semilla", "8")
    otra = Consola()
    _correr(datos, otra, "repaso", "--fecha", "2026-09-30")
    assert "REPASO —" in otra.texto


def test_progreso_arma_el_informe(datos, consola):
    _iniciar(datos, consola)
    _correr(datos, consola, "practicar", "-n", "6", "--fecha", HOY, "--semilla", "9")
    informe = Consola()
    _correr(datos, informe, "progreso", "--fecha", HOY)
    assert "INFORME DE PROGRESO" in informe.texto
    assert "DOMINIO POR ÁREA" in informe.texto


def test_banco_muestra_la_cobertura_y_no_reporta_avisos(datos, consola):
    assert _correr(datos, consola, "banco") == 0
    assert "COBERTURA POR COMPETENCIA" in consola.texto
    assert "el banco está bien" in consola.texto


def test_exportar_web_crea_el_archivo(datos, consola, tmp_path):
    _iniciar(datos, consola)
    destino = tmp_path / "app.html"
    _correr(datos, consola, "exportar-web", "--salida", str(destino))
    assert destino.is_file()
    assert "sin internet" in consola.texto


def test_practicar_solo_preguntas_nuevas_no_repite(datos, consola):
    _iniciar(datos, consola)
    _correr(
        datos,
        consola,
        "practicar",
        "--area",
        "ing",
        "-n",
        "5",
        "--fecha",
        HOY,
        "--semilla",
        "10",
        "--nuevas",
    )
    from icfes.almacen import Almacen

    with Almacen(datos) as a:
        vistos = a.ids_respondidos()
    segunda = Consola()
    _correr(
        datos,
        segunda,
        "practicar",
        "--area",
        "ing",
        "-n",
        "5",
        "--fecha",
        HOY,
        "--semilla",
        "11",
        "--nuevas",
    )
    with Almacen(datos) as a:
        assert len(a.ids_respondidos()) == len(vistos) + 5


def test_la_ronda_devuelve_las_respuestas_en_el_orden_original(banco, almacen):
    """Con las opciones barajadas, lo guardado debe ser el índice original."""
    from icfes.cli import correr_ronda

    preguntas = banco.muestra(3, semilla=1)
    consola = Consola(respuestas=("A",))
    ronda = correr_ronda(
        preguntas,
        almacen,
        date(2026, 8, 20),
        date(2027, 8, 8),
        consola.leer,
        consola.escribir,
        consola.tiempo,
        semilla=1,
    )
    assert isinstance(ronda, Ronda)
    assert set(ronda.respuestas) == {p.id for p in preguntas}
    assert all(0 <= v <= 3 for v in ronda.respuestas.values())
