"""Pruebas del trabajo con varias IPS en SIIFA.

El auditor administra cuatro prestadores distintos, cada uno con su usuario
del portal, y los trabaja al mismo tiempo en cuatro ventanas iguales.
Equivocarse de ventana es cuestión de tiempo, y una respuesta cargada en la
entidad equivocada no se puede deshacer.

Lo que se cuida acá:
  1. Que las credenciales de cada IPS salgan de SU variable de entorno.
  2. Que ANTES de escribir se compruebe que el token es de esa IPS.
  3. Que ningún script que entra a SIIFA se salte esa comprobación.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TOOLS = RAIZ / "tools"
sys.path.insert(0, str(TOOLS))

import siifa_perfiles as perfiles  # noqa: E402
from siifa_client import _nit_del_jwt  # noqa: E402

# Los scripts que se conectan a SIIFA. Cualquiera de ellos puede escribir, o
# bajar datos con los que después se escribe.
SCRIPTS_QUE_ENTRAN = [
    "siifa_reporte_seguimientos.py",
    "responder_glosas_siifa.py",
    "siifa_verificar_cargue.py",
    "siifa_sondear_endpoints.py",
]


def _jwt(payload: dict) -> str:
    cuerpo = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"encabezado.{cuerpo}.firma"


# --------------------------------------------------------- las cuatro IPS


def test_estan_las_cuatro_ips_con_su_nit():
    assert set(perfiles.IPS) == {"HUS", "SOCORRO", "GIRON", "GUANE"}
    assert perfiles.IPS["HUS"].nit == "900006037"
    assert perfiles.IPS["SOCORRO"].nit == "900190045"
    assert perfiles.IPS["GIRON"].nit == "890203242"
    assert perfiles.IPS["GUANE"].nit == "804006936"


def test_cada_ips_tiene_su_carpeta_y_sus_variables():
    """Si dos IPS compartieran carpeta, el informe de una pisaría al de otra:
    todos los archivos se llaman igual (informe_seguimientos.xlsx)."""
    carpetas = {i.carpeta for i in perfiles.IPS.values()}
    usuarios = {i.var_usuario for i in perfiles.IPS.values()}
    claves = {i.var_password for i in perfiles.IPS.values()}

    assert len(carpetas) == len(perfiles.IPS), "hay IPS compartiendo carpeta"
    assert len(usuarios) == len(perfiles.IPS), "hay IPS compartiendo variable de usuario"
    assert len(claves) == len(perfiles.IPS), "hay IPS compartiendo variable de contraseña"


def test_en_el_archivo_de_perfiles_no_hay_ni_una_credencial():
    """Regla del repo: nunca un usuario ni una clave en algo versionado."""
    fuente = (TOOLS / "siifa_perfiles.py").read_text(encoding="utf-8")

    for ips in perfiles.IPS.values():
        # Los NOMBRES de las variables sí van; los valores, jamás.
        assert f'os.environ.get("{ips.var_usuario}")' not in fuente
    assert not re.search(r'(password|clave|contrase\w+)\s*=\s*["\'][^"\']{3,}["\']', fuente, re.I)


def test_una_ips_que_no_existe_se_rechaza_con_la_lista():
    with pytest.raises(SystemExit, match="GIRON"):
        perfiles.buscar("CLINICA_INVENTADA")


def test_el_nombre_de_la_ips_no_distingue_mayusculas():
    assert perfiles.buscar("socorro").clave == "SOCORRO"
    assert perfiles.buscar("  Giron  ").clave == "GIRON"


def test_faltando_las_credenciales_se_dice_cual_variable_definir(monkeypatch):
    monkeypatch.delenv("SIIFA_USER_GUANE", raising=False)
    monkeypatch.delenv("SIIFA_PASSWORD_GUANE", raising=False)

    with pytest.raises(SystemExit, match="SIIFA_USER_GUANE"):
        perfiles.credenciales(perfiles.buscar("GUANE"))


def test_cada_ips_lee_su_propia_variable(monkeypatch):
    monkeypatch.setenv("SIIFA_USER_SOCORRO", "usuario_socorro")
    monkeypatch.setenv("SIIFA_PASSWORD_SOCORRO", "clave_socorro")
    monkeypatch.setenv("SIIFA_USER_GIRON", "usuario_giron")
    monkeypatch.setenv("SIIFA_PASSWORD_GIRON", "clave_giron")

    assert perfiles.credenciales(perfiles.buscar("SOCORRO")) == ("usuario_socorro", "clave_socorro")
    assert perfiles.credenciales(perfiles.buscar("GIRON")) == ("usuario_giron", "clave_giron")


# ------------------------------------------------- la guarda que importa


def test_el_token_de_otra_ips_detiene_todo():
    """EL CASO QUE ESTO EXISTE PARA EVITAR.

    El auditor pide trabajar con SOCORRO pero la ventana tiene cargadas las
    credenciales del HUS. Sin esta guarda, las respuestas de SOCORRO se
    cargarían contra las facturas del HUS.
    """
    with pytest.raises(SystemExit) as exc:
        perfiles.verificar_identidad(perfiles.buscar("SOCORRO"), "900006037")

    mensaje = str(exc.value)
    assert "ALTO" in mensaje
    assert "Clínica Socorro" in mensaje
    assert "Hospital Universitario" in mensaje, "debe decir de quién SÍ son las credenciales"
    assert "No se hizo nada" in mensaje


def test_el_token_correcto_deja_seguir():
    perfiles.verificar_identidad(perfiles.buscar("GUANE"), "804006936")


def test_el_nit_con_digito_de_verificacion_es_el_mismo():
    """SIIFA devuelve el NIT de varias formas. Un falso «no coincide» sobre la
    misma entidad es peor que no comparar: haría desconfiar de la guarda."""
    ips = perfiles.buscar("HUS")

    perfiles.verificar_identidad(ips, "900006037-4")
    perfiles.verificar_identidad(ips, "9000060374")
    perfiles.verificar_identidad(ips, "900.006.037")
    perfiles.verificar_identidad(ips, " 900006037 ")


def test_un_token_sin_nit_avisa_pero_no_bloquea(capsys):
    """Si la API deja de mandar el campo, bloquear dejaría al auditor sin
    herramienta y sin entender por qué. Se avisa y se sigue."""
    perfiles.verificar_identidad(perfiles.buscar("HUS"), None)

    assert "AVISO" in capsys.readouterr().out


def test_el_aviso_de_ips_se_ve_antes_de_trabajar(capsys):
    perfiles.anunciar(perfiles.buscar("GIRON"))

    salida = capsys.readouterr().out
    assert "Clínica Girón" in salida and "890203242" in salida


# ------------------------------------------------- leer el NIT del token


def test_se_lee_el_nit_que_viene_en_el_token():
    assert _nit_del_jwt(_jwt({"NitEntidad": "900190045", "role": "SIIFA_IPS"})) == "900190045"


def test_se_lee_aunque_el_claim_venga_con_url_delante():
    """Los claims de .NET llegan como http://schemas.../nitentidad."""
    token = _jwt({"http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nitentidad": "890203242"})

    assert _nit_del_jwt(token) == "890203242"


def test_un_token_ilegible_no_revienta():
    """Esto es una comprobación de seguridad: si falla, avisa, no tumba."""
    assert _nit_del_jwt("no-es-un-token") is None
    assert _nit_del_jwt("") is None
    assert _nit_del_jwt("a.###.c") is None
    assert _nit_del_jwt(_jwt({"role": "SIIFA_IPS"})) is None


def test_el_padding_del_base64_no_estorba():
    """base64url viene sin relleno y decodificarlo así falla en silencio."""
    for nit in ("900006037", "8042", "90019004512345"):
        assert _nit_del_jwt(_jwt({"nit": nit})) == nit


# --------------------------------------- que nadie se salte la guarda


@pytest.mark.parametrize("script", SCRIPTS_QUE_ENTRAN)
def test_todo_script_que_entra_a_siifa_comprueba_la_identidad(script):
    """EL GUARDIÁN. Un script nuevo que copie el patrón de login y se olvide
    de verificar la identidad deja el hueco abierto otra vez, y en verde.

    No basta con que la función exista: hay que llamarla en cada entrada.
    """
    fuente = (TOOLS / script).read_text(encoding="utf-8")

    assert "cliente.login(" in fuente, f"{script} ya no entra a SIIFA: sacalo de la lista"
    assert "perfiles.verificar_identidad(" in fuente, (
        f"{script} entra a SIIFA sin comprobar de qué IPS es el token"
    )
    assert "perfiles.credenciales(" in fuente, f"{script} no lee las credenciales de la IPS elegida"


@pytest.mark.parametrize("script", SCRIPTS_QUE_ENTRAN)
def test_la_verificacion_va_despues_del_login_y_antes_de_trabajar(script):
    """El orden es lo que da la garantía: comprobar después de trabajar sería
    enterarse cuando ya está escrito."""
    fuente = (TOOLS / script).read_text(encoding="utf-8")

    assert fuente.index("cliente.login(") < fuente.index("perfiles.verificar_identidad(")


@pytest.mark.parametrize("script", SCRIPTS_QUE_ENTRAN)
def test_ningun_script_lee_ya_las_credenciales_de_una_sola_ips(script):
    """SIIFA_USER a secas era el mundo de una sola IPS. Si un script lo
    siguiera usando, trabajaría con la entidad equivocada sin avisar."""
    fuente = (TOOLS / script).read_text(encoding="utf-8")
    codigo = fuente[fuente.index('"""', fuente.index('"""') + 3) :]  # sin el encabezado de ayuda

    assert "credenciales_desde_env()" not in codigo, (
        f"{script} sigue leyendo las credenciales viejas, iguales para todas las IPS"
    )


# ------------------- que la respuesta no salga a nombre de otra entidad


def _glosa():
    return {
        "numero_factura": "HUS521868",
        "tipo_seguimiento": "GLOSA",
        "valor_glosa": 3_399_053,
        "codigo_glosa": "TA0801",
        "descripcion_glosa": "Diferencia con los valores pactados.",
        "observacion_glosa": "No corresponde a la tarifa.",
        "fecha_respuesta": "2026-08-05T14:07:00",
        "descripcion_reiteracion": "Glosa Reiterada",
    }


@pytest.mark.parametrize("clave", ["SOCORRO", "GIRON", "GUANE"])
def test_la_respuesta_de_otra_ips_no_dice_que_es_el_hus(clave):
    """El texto de la respuesta tiene efectos jurídicos ante la EPS.

    Estaba escrito «ESE HOSPITAL UNIVERSITARIO DE SANTANDER NO ACEPTA...» a
    mano. Con cuatro IPS, la respuesta de la Clínica Socorro habría salido
    diciendo que la firma el HUS —y con el correo y la dirección del HUS—.
    """
    import siifa_redactar_respuestas as redactor

    ips = perfiles.buscar(clave)
    texto = redactor.redactar(_glosa(), ips=ips)["OBSERVACION_RESPUESTA"]

    assert ips.nombre_legal in texto
    assert "HOSPITAL UNIVERSITARIO" not in texto
    assert "HUS.GOV.CO" not in texto, "no puede llevar el correo de otra entidad"
    assert "CARRERA 30" not in texto, "no puede llevar la dirección de otra entidad"


@pytest.mark.parametrize("clave", ["SOCORRO", "GIRON", "GUANE"])
def test_la_subsanacion_de_otra_ips_tampoco(clave):
    import siifa_armar_subsanacion as sub

    ips = perfiles.buscar(clave)
    texto = sub.redactar_subsanacion(_glosa(), ips=ips)["OBSERVACION_RESPUESTA"]

    assert ips.nombre_legal in texto
    assert "HOSPITAL UNIVERSITARIO" not in texto


def test_la_del_hus_sigue_saliendo_igual_que_siempre():
    """Lo ya cargado no puede cambiar de forma por este trabajo."""
    import siifa_redactar_respuestas as redactor

    texto = redactor.redactar(_glosa(), ips=perfiles.buscar("HUS"))["OBSERVACION_RESPUESTA"]

    assert texto.startswith("ESE HOSPITAL UNIVERSITARIO DE SANTANDER NO ACEPTA")
    assert "CARTERA@HUS.GOV.CO" in texto


def test_sin_ips_se_comporta_como_antes():
    """Compatibilidad: el código viejo llama redactar(linea) sin IPS."""
    import siifa_redactar_respuestas as redactor

    assert redactor.redactar(_glosa())["OBSERVACION_RESPUESTA"].startswith(
        "ESE HOSPITAL UNIVERSITARIO DE SANTANDER"
    )


def test_una_ips_sin_contacto_omite_la_frase_en_vez_de_inventarla():
    """Mejor una respuesta sin datos de contacto que con los de otra entidad."""
    import siifa_redactar_respuestas as redactor

    cierre = redactor.cierre_de(perfiles.buscar("SOCORRO"))

    assert "CUALQUIER INFORMACIÓN AL" not in cierre
    assert "ARTÍCULO 57 DE LA LEY 1438" in cierre, "el sustento normativo no se pierde"


# ------------------- la otra mitad: que el ARCHIVO sea de esa IPS


def _fila_informe(nit_emisor="900006037"):
    return {"nit_emisor": nit_emisor, "id_seguimiento_factura_glosa": 1}


def test_un_informe_de_otra_ips_se_rechaza():
    """La guarda del token protege lo que se ESCRIBE; esta, lo que se LEE.

    Con cuatro carpetas parecidas y archivos que se llaman igual en todas,
    pasarle el informe de otra IPS es facilísimo — y de ahí salen las
    respuestas que después se cargan.
    """
    with pytest.raises(SystemExit) as exc:
        perfiles.verificar_informe(perfiles.buscar("SOCORRO"), [_fila_informe("900006037")])

    mensaje = str(exc.value)
    assert "ALTO" in mensaje
    assert "Hospital Universitario" in mensaje, "debe decir de quién ES el archivo"
    assert "se llaman igual en las cuatro" in mensaje


def test_el_informe_de_la_ips_correcta_pasa():
    perfiles.verificar_informe(perfiles.buscar("GUANE"), [_fila_informe("804006936")] * 50)


def test_un_informe_viejo_sin_la_columna_no_bloquea():
    """Los informes bajados antes de este cambio no traen nit_emisor."""
    perfiles.verificar_informe(perfiles.buscar("GIRON"), [{"id_seguimiento_factura_glosa": 1}])
    perfiles.verificar_informe(perfiles.buscar("GIRON"), [])


def test_el_nit_del_informe_tambien_admite_digito_de_verificacion():
    perfiles.verificar_informe(perfiles.buscar("HUS"), [_fila_informe("900006037-4")])


def test_un_informe_mezclado_se_rechaza_por_la_fila_ajena():
    """Basta una fila de otra entidad: el archivo no es confiable."""
    filas = [_fila_informe("890203242")] * 99 + [_fila_informe("804006936")]

    with pytest.raises(SystemExit, match="Guane"):
        perfiles.verificar_informe(perfiles.buscar("GIRON"), filas)


@pytest.mark.parametrize(
    "script",
    ["siifa_novedades.py", "siifa_estado_tramite.py", "siifa_armar_subsanacion.py"],
)
def test_las_herramientas_que_leen_informes_comprueban_de_quien_son(script):
    fuente = (TOOLS / script).read_text(encoding="utf-8")

    assert "perfiles.verificar_informe(" in fuente, (
        f"{script} lee un informe sin comprobar que sea de la IPS elegida"
    )


def test_la_constancia_pdf_no_sale_a_nombre_del_hus():
    """Se anexa a la EPS como evidencia: una constancia de la Clínica Girón
    encabezada «Hospital Universitario de Santander» no prueba nada."""
    fuente = (TOOLS / "siifa_verificar_cargue.py").read_text(encoding="utf-8")

    assert 'Paragraph("E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER"' not in fuente
    assert "ips.nombre_legal" in fuente
    assert "CONSTANCIA_SIIFA_{ips.clave}_{factura}.pdf" in fuente, (
        "el nombre del PDF debe distinguir la IPS: si no, una pisa a la otra"
    )


def test_dos_ips_bajando_a_la_vez_no_se_borran_el_archivo_de_prueba():
    """Pasó de verdad con tres corridas en paralelo: el nombre era fijo, una
    borraba el de la otra y la otra concluía «no puedo guardar acá»."""
    fuente = (TOOLS / "siifa_reporte_seguimientos.py").read_text(encoding="utf-8")

    assert ".prueba_escritura_hus.tmp" not in fuente
    assert "os.getpid()" in fuente
