"""Tests del organizador de correos de glosas (tools/organizar_correos_glosas.py).

Cubren la lógica pura (clasificación, entidad, rutas, nombres, consecutivos)
y el procesamiento completo de un mensaje construido en memoria — sin IMAP.
Los casos de clasificación vienen de correos reales de la bandeja
glosasydevoluciones@hus.gov.co (AUDITOOL/DISPENSARIO, AXA, Salud Mía, ...).
"""

from __future__ import annotations

import json
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import pytest

from tools import organizar_correos_glosas as org

CONFIG = org.cargar_config(None)


# ─── Utilidades ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ('Devolución: Radicado <No> "100570"', "Devolución_ Radicado _No_ _100570_"),
        ("  espacios   dobles  ", "espacios dobles"),
        ("termina en punto...", "termina en punto"),
        ("con\x00control", "con_control"),
    ],
)
def test_sanitizar_windows(entrada, esperado):
    assert org.sanitizar(entrada) == esperado


def test_decodificar_encabezado_mime():
    codificado = "=?UTF-8?Q?Devoluci=C3=B3n_de_Factura?="
    assert org.decodificar_encabezado(codificado) == "Devolución de Factura"
    assert org.decodificar_encabezado(None) == ""


def test_extraer_radicado():
    assert org.extraer_radicado("Devolución de Factura del Radicado No 100881") == "100881"
    assert org.extraer_radicado("Proceso en revisión Radicado No. 102666") == "102666"
    assert org.extraer_radicado("sin radicado") == ""


def test_extraer_texto_html():
    html = "<html><style>p{color:red}</style><body><p>Hola</p><p>Mundo</p></body></html>"
    assert org.extraer_texto_html(html) == "Hola\n\nMundo"


# ─── Clasificación de categoría (asuntos reales de la bandeja) ───────────────


@pytest.mark.parametrize(
    "asunto,categoria",
    [
        ("GLOSA DEL DIA 02/07/26 07:35 DE EMPRESA SOCIAL DEL ESTADO", "INICIAL"),
        ("53 Notificación de objeciones diarias 01 de julio.", "INICIAL"),
        ("Devolución de Factura del Radicado No 100881", "DEVOLUCIONES"),
        ("Solicitud cita de conciliación glosas ratificadas", "CONCILIACIONES"),
        ("Resultado glosas RATIFICADAS radicado 998", "RATIFICADA"),
        ("Envió Documentos a Terceros", "0-REVISAR"),
    ],
)
def test_clasificar_categoria(asunto, categoria):
    assert org.clasificar_categoria(asunto, [], CONFIG)[0] == categoria


def test_clasificar_mixto_glosas_y_devueltas_va_a_revision():
    """Un correo que mezcla glosas Y devoluciones lo decide un humano."""
    asunto = "NOTIFICACIÓN: FACTURAS GLOSADAS Y DEVUELTAS 30 JUNIO 2026"
    categoria, motivo = org.clasificar_categoria(asunto, [], CONFIG)
    assert categoria == "0-REVISAR"
    assert "GLOSA+DEVOLUCION" in motivo


def test_clasificar_usa_nombres_de_adjuntos():
    categoria, _ = org.clasificar_categoria(
        "Notificación", ["AUDITORIA_GLOSA_HUS_68001.pdf"], CONFIG
    )
    assert categoria == "INICIAL"


def test_ignorar_notificaciones_de_radicacion():
    assert org.debe_ignorarse("Cargue exitoso: 14 facturas procesadas", CONFIG)
    assert org.debe_ignorarse("Errores en el procesamiento del ZIP: 178.zip", CONFIG)
    assert not org.debe_ignorarse("GLOSA DEL DIA", CONFIG)


# ─── Detección de entidad ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "remitente,asunto,carpeta",
    [
        ("CONSORCIO AUDITOOL 25 <radicacion.auditool@tool.com.co>", "Devolución", "DISPENSARIO"),
        ("Archivo Colpatria <archivo.colpatria@grupomok.com>", "objeciones", "AXA"),
        ("x <notificaciones@segurosbolivar.com>", "glosa", "SEGUROS BOLIVAR"),
        ("noreply <glosas@saludmia.com.co>", "FACTURAS GLOSADAS", "SALUD MIA"),
    ],
)
def test_detectar_entidad_conocida(remitente, asunto, carpeta):
    entidad, identificada = org.detectar_entidad(remitente, asunto, [], CONFIG)
    assert (entidad, identificada) == (carpeta, True)


def test_entidad_desconocida_usa_dominio():
    entidad, identificada = org.detectar_entidad(
        "Karin <radicacionhus04@sinacsc.com>", "Envió Documentos a Terceros", [], CONFIG
    )
    assert entidad == "SINACSC.COM"
    assert not identificada


# ─── Rutas, nombres y estado ─────────────────────────────────────────────────


def test_construir_carpeta_destino_estructura_servidor(tmp_path):
    fecha = datetime(2026, 7, 2, 8, 11, tzinfo=org.TZ_COLOMBIA)
    carpeta = org.construir_carpeta_destino(tmp_path, fecha, "DEVOLUCIONES", "DISPENSARIO", CONFIG)
    assert carpeta == tmp_path / "2026" / "07 JULIO" / "02" / "DEVOLUCIONES" / "DISPENSARIO OK"


def test_construir_carpeta_reutiliza_marcas_manuales(tmp_path):
    """El personal renombra carpetas a mano; el script debe reutilizarlas,
    no crear duplicadas: 07.JULIO, '01 OK SOLO NUEVA', 'DEVOLUCIONES OK',
    'DISPENSARIO SOFIA OK' (estructura real del servidor)."""
    existente = tmp_path / "2026" / "07.JULIO" / "01 OK SOLO NUEVA" / "DEVOLUCIONES OK"
    (existente / "DISPENSARIO SOFIA OK").mkdir(parents=True)
    fecha = datetime(2026, 7, 1, 8, 11, tzinfo=org.TZ_COLOMBIA)
    carpeta = org.construir_carpeta_destino(tmp_path, fecha, "DEVOLUCIONES", "DISPENSARIO", CONFIG)
    assert carpeta == existente / "DISPENSARIO SOFIA OK"


def test_carpeta_equivalente_acepta_plural_y_prefiere_la_mas_corta(tmp_path):
    (tmp_path / "RATIFICADAS").mkdir()
    assert org.carpeta_equivalente(tmp_path, "RATIFICADA").name == "RATIFICADAS"
    # '02' no debe confundirse con '021' ni con otra carpeta numérica
    (tmp_path / "021").mkdir()
    assert org.carpeta_equivalente(tmp_path, "02").name == "02"
    (tmp_path / "02 OK").mkdir()
    (tmp_path / "02 OK REVISADA COMPLETA").mkdir()
    assert org.carpeta_equivalente(tmp_path, "02").name == "02 OK"


def test_hora_correo_formato_manual():
    assert org.hora_correo(datetime(2026, 7, 2, 7, 21)) == "7.21"
    assert org.hora_correo(datetime(2026, 7, 2, 13, 30)) == "1.30"
    assert org.hora_correo(datetime(2026, 7, 2, 0, 5)) == "12.05"
    assert org.hora_correo(datetime(2026, 7, 2, 12, 0)) == "12.00"


def test_nombre_disponible_no_sobreescribe(tmp_path):
    (tmp_path / "DEV028158_324.pdf").write_bytes(b"x")
    assert org.nombre_disponible(tmp_path, "DEV028158_324.pdf").name == "DEV028158_324 (2).pdf"
    (tmp_path / "DEV028158_324 (2).pdf").write_bytes(b"x")
    assert org.nombre_disponible(tmp_path, "DEV028158_324.pdf").name == "DEV028158_324 (3).pdf"


def test_nombre_pdf_devolucion_usa_asunto():
    estado = org.Estado(None)
    fecha = datetime(2026, 7, 2, 8, 11, tzinfo=org.TZ_COLOMBIA)
    nombre = org.nombre_pdf_correo(
        "DEVOLUCIONES",
        "DISPENSARIO",
        "Devolución de Factura del Radicado No 100881",
        fecha,
        lambda: estado.siguiente_consecutivo(fecha, "DISPENSARIO"),
        CONFIG,
    )
    assert nombre == "Devolución de Factura del Radicado No 100881 OK.pdf"
    # la plantilla de devoluciones no usa consecutivo: no debe gastarlo
    assert estado.datos["consecutivos"] == {}


def test_nombre_pdf_glosa_usa_hora_de_llegada():
    fecha = datetime(2026, 7, 2, 7, 21, tzinfo=org.TZ_COLOMBIA)
    nombre = org.nombre_pdf_correo("INICIAL", "AXA", "objeciones", fecha, lambda: 1, CONFIG)
    assert nombre == "AXA 7.21 OK.pdf"


def test_consecutivo_por_dia_y_entidad():
    estado = org.Estado(None)
    dia = datetime(2026, 7, 2, tzinfo=org.TZ_COLOMBIA)
    otro_dia = datetime(2026, 7, 3, tzinfo=org.TZ_COLOMBIA)
    assert estado.siguiente_consecutivo(dia, "AXA") == 1
    assert estado.siguiente_consecutivo(dia, "AXA") == 2
    assert estado.siguiente_consecutivo(dia, "DISPENSARIO") == 1
    assert estado.siguiente_consecutivo(otro_dia, "AXA") == 1


def test_estado_persistencia_y_dedup(tmp_path):
    ruta = tmp_path / "estado.json"
    estado = org.Estado.cargar(ruta)
    estado.marcar("<msg-1@x>")
    estado.guardar()
    recargado = org.Estado.cargar(ruta)
    assert recargado.ya_procesado("<msg-1@x>")
    assert not recargado.ya_procesado("<msg-2@x>")


def test_estado_corrupto_respalda_y_sigue(tmp_path):
    ruta = tmp_path / "estado.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    estado = org.Estado.cargar(ruta)
    assert estado.datos["procesados"] == {}
    assert (tmp_path / "estado.corrupto.json").exists()


def test_config_ejemplo_sincronizado_con_defaults():
    """El JSON de ejemplo que edita el usuario debe ser idéntico a los defaults."""
    ruta = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "organizar_correos_glosas_config.ejemplo.json"
    )
    assert json.loads(ruta.read_text(encoding="utf-8")) == org.CONFIG_DEFECTO


# ─── Procesamiento completo de un mensaje (sin IMAP) ─────────────────────────


def _correo_devolucion() -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Devolución de Factura del Radicado No 100881"
    msg["From"] = "CONSORCIO AUDITOOL 25 <radicacion.auditool@tool.com.co>"
    msg["To"] = "glosasydevoluciones@hus.gov.co"
    msg["Date"] = "Thu, 2 Jul 2026 08:11:00 -0500"
    msg["Message-ID"] = "<devolucion-100881@tool.com.co>"
    msg.set_content("Estimada IPS, se presentaron devoluciones a facturas.")
    msg.add_alternative(
        "<html><body><p>Estimada IPS,</p><p>se presentaron devoluciones.</p></body></html>",
        subtype="html",
    )
    msg.add_attachment(
        b"%PDF-1.4 contenido de prueba",
        maintype="application",
        subtype="pdf",
        filename="DEV028158_324.pdf",
    )
    return msg


def test_procesar_mensaje_archiva_pdf_y_adjuntos(tmp_path):
    pytest.importorskip("reportlab")
    fila = org.procesar_mensaje(
        _correo_devolucion(),
        base=tmp_path,
        config=CONFIG,
        estado=org.Estado(None),
        dry_run=False,
        sin_pdf_correo=False,
        navegador=None,  # forzar la vía reportlab, determinista en CI
    )
    carpeta = tmp_path / "2026" / "07 JULIO" / "02" / "DEVOLUCIONES" / "DISPENSARIO OK"
    assert fila["estado"] == "ARCHIVADO"
    assert Path(fila["carpeta"]) == carpeta
    pdf_correo = carpeta / "Devolución de Factura del Radicado No 100881 OK.pdf"
    assert pdf_correo.exists() and pdf_correo.stat().st_size > 0
    assert pdf_correo.read_bytes()[:5] == b"%PDF-"
    # el adjunto se renombra con la convención manual y queda ' (2)' por el choque
    adjunto = carpeta / "Devolución de Factura del Radicado No 100881 OK (2).pdf"
    assert adjunto.read_bytes() == b"%PDF-1.4 contenido de prueba"
    assert "DEV028158_324.pdf" in fila["archivos"]  # el original queda en el registro


def test_procesar_mensaje_dry_run_no_escribe(tmp_path):
    fila = org.procesar_mensaje(
        _correo_devolucion(),
        base=tmp_path,
        config=CONFIG,
        estado=org.Estado(None),
        dry_run=True,
        sin_pdf_correo=False,
        navegador=None,
    )
    assert fila["estado"] == "DRY_RUN"
    assert "DEV028158_324.pdf" in fila["archivos"]
    assert list(tmp_path.iterdir()) == []  # nada escrito


def test_procesar_mensaje_ignorado_no_clasifica(tmp_path):
    msg = EmailMessage()
    msg["Subject"] = "Cargue exitoso: 14 facturas procesadas"
    msg["From"] = "Notificaciones <notificaciones@simed.com.co>"
    msg["Date"] = "Mon, 6 Jul 2026 15:27:00 -0500"
    msg.set_content("Se cargaron las facturas con exito.")
    fila = org.procesar_mensaje(
        msg,
        base=tmp_path,
        config=CONFIG,
        estado=org.Estado(None),
        dry_run=False,
        sin_pdf_correo=False,
        navegador=None,
    )
    assert fila["estado"] == "IGNORADO"
    assert list(tmp_path.iterdir()) == []


def test_procesar_glosa_inicial_nombra_por_hora(tmp_path):
    """Dos correos AXA el mismo minuto: 'AXA 7.35 OK.pdf' y 'AXA 7.35 OK (2).pdf'."""
    pytest.importorskip("reportlab")
    estado = org.Estado(None)
    esperados = ("AXA 7.35 OK.pdf", "AXA 7.35 OK (2).pdf")
    for numero, esperado in enumerate(esperados, start=1):
        msg = EmailMessage()
        msg["Subject"] = f"{52 + numero} Notificación de objeciones diarias 01 de julio."
        msg["From"] = "Archivo Colpatria <archivo.colpatria@grupomok.com>"
        msg["Date"] = "Thu, 2 Jul 2026 07:35:00 -0500"
        msg["Message-ID"] = f"<objeciones-{numero}@grupomok.com>"
        msg.set_content("Objeciones parciales o totales.")
        fila = org.procesar_mensaje(
            msg,
            base=tmp_path,
            config=CONFIG,
            estado=estado,
            dry_run=False,
            sin_pdf_correo=False,
            navegador=None,
        )
        assert fila["categoria"] == "INICIAL"
        carpeta = tmp_path / "2026" / "07 JULIO" / "02" / "INICIAL" / "AXA OK"
        assert (carpeta / esperado).exists()


def test_extraer_partes_omite_logo_inline_pequeno():
    msg = EmailMessage()
    msg["Subject"] = "x"
    msg.set_content("hola")
    msg.add_attachment(
        b"\x89PNG logo chiquito",
        maintype="image",
        subtype="png",
        filename="logo.png",
        disposition="inline",
        cid="<logo@firma>",
    )
    msg.add_attachment(
        b"%PDF-1.4 real",
        maintype="application",
        subtype="pdf",
        filename="soporte.pdf",
    )
    _, _, inlines, adjuntos = org.extraer_partes(msg, CONFIG)
    assert [n for n, _ in adjuntos] == ["soporte.pdf"]
    assert "logo@firma" in inlines  # sí disponible para incrustar en el PDF del correo
