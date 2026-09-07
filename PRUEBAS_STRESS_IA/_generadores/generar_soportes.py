"""Genera los soportes de las pruebas de estrés (PDF, CSV, XLSX).

AISLADO: no importa nada de `app/`, no toca la base de datos ni la
configuración. Solo escribe archivos dentro de PRUEBAS_STRESS_IA/.

Regla que se respeta al pie de la letra: si una prueba existe para
comprobar que el motor NO inventa cuando NO hay soporte, ese soporte
NO se crea. Los ausentes están listados en el datos.json de cada caso.
"""

from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

RAIZ = Path(__file__).resolve().parent.parent
ESTILOS = getSampleStyleSheet()
CUERPO = ParagraphStyle("cuerpo", parent=ESTILOS["Normal"], fontSize=9.5, leading=13.5)
TITULO = ParagraphStyle("titulo", parent=ESTILOS["Heading2"], fontSize=12, spaceAfter=8)
SUB = ParagraphStyle("sub", parent=ESTILOS["Heading3"], fontSize=10, spaceBefore=8, spaceAfter=4)


def pdf(destino: Path, titulo: str, bloques: list[tuple[str, str]]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(destino),
        pagesize=letter,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=titulo,
    )
    flujo = [Paragraph(titulo, TITULO), Spacer(1, 4)]
    for clase, texto in bloques:
        flujo.append(Paragraph(texto, SUB if clase == "h" else CUERPO))
    doc.build(flujo)
    print(f"  PDF   {destino.relative_to(RAIZ)}")


def escribir_csv(destino: Path, cabecera: list[str], filas: list[list]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cabecera)
        w.writerows(filas)
    print(f"  CSV   {destino.relative_to(RAIZ)}")


# ─── CASO 1 · el número que parece CUPS y no lo es ──────────────────────
C1 = RAIZ / "01_TA0301_CUPS_QUE_NO_LO_ES" / "soportes"
pdf(
    C1 / "factura.pdf",
    "E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER — FACTURA DE VENTA",
    [
        ("h", "Datos de la factura"),
        (
            "p",
            "Número: <b>HUS0000601447</b><br/>Entidad responsable de pago: LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB<br/>NIT prestador: 900.006.037-4",
        ),
        ("h", "Detalle"),
        (
            "p",
            "CUPS <b>890201</b> — CONSULTA DE PRIMERA VEZ POR MEDICINA ESPECIALIZADA … cantidad 1 … $4.180.000",
        ),
        ("h", "Referencias del pagador (no son CUPS)"),
        (
            "p",
            "Radicado del pagador: <b>471120</b><br/>Orden de servicio: <b>274101</b><br/>Lote de auditoría: <b>890201-B</b>",
        ),
        ("h", "Totales"),
        ("p", "Total facturado: <b>$4.180.000</b>"),
        ("h", "Nota"),
        (
            "p",
            "Esta factura NO indica fecha de prestación del servicio. Solo constan radicación y recepción.",
        ),
    ],
)
escribir_csv(
    C1 / "rips_procedimientos.csv",
    [
        "numFactura",
        "codPrestador",
        "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion",
        "codProcedimiento",
        "codDiagnosticoPrincipal",
        "vrServicio",
    ],
    [["HUS0000601447", "680010000101", "CC", "91234567", "890201", "M25.5", "4180000"]],
)

# ─── CASO 2 · pertinencia mezclada con tarifa ───────────────────────────
C2 = RAIZ / "02_CL4506_PERTINENCIA_VS_TARIFA" / "soportes"
pdf(
    C2 / "nota_operatoria.pdf",
    "DESCRIPCIÓN QUIRÚRGICA — SERVICIO DE ORTOPEDIA",
    [
        ("h", "Identificación"),
        (
            "p",
            "Factura HUS0000601892 · Paciente: J.A.R.M. · Documento: CC 1.098.xxx.xxx<br/>Diagnóstico de ingreso: S72.0 Fractura del cuello de fémur",
        ),
        ("h", "Hallazgos intraoperatorios"),
        (
            "p",
            "Bajo anestesia raquídea, en mesa de tracción, se realiza abordaje lateral proximal de fémur derecho. "
            "Se confirma radiológicamente trazo <b>intertrocantérico</b> conminuto de tres fragmentos. "
            "Se identifica <b>además fractura diafisaria ipsilateral</b> en tercio medio, no evidenciada en la "
            "radiografía inicial de urgencias, con desplazamiento de 11 mm.",
        ),
        (
            "p",
            "Se decide fijación con clavo cefalomedular largo para el componente proximal. Dada la conminución "
            "del trazo diafisario y la imposibilidad de lograr estabilidad rotacional solo con el clavo, se "
            "complementa con placa DCP 4.5 y ocho tornillos corticales en el segmento diafisario.",
        ),
        ("h", "Procedimiento realizado"),
        ("p", "CUPS 215601 — OSTEOSÍNTESIS DE FÉMUR"),
        ("h", "Material implantado"),
        ("p", "Clavo cefalomedular largo (1) · Placa DCP 4.5 (1) · Tornillos corticales 4.5 (8)"),
        ("h", "Firma"),
        ("p", "Ortopedista y traumatólogo · R.M. 68-xxxx"),
    ],
)
pdf(
    C2 / "contrato_440_DIGSA.pdf",
    "CONTRATO DE PRESTACIÓN DE SERVICIOS DE SALUD N.º 440-DIGSA",
    [
        ("h", "Partes"),
        (
            "p",
            "CONTRATANTE: DIRECCIÓN DE SANIDAD DEL EJÉRCITO NACIONAL<br/>"
            "CONTRATISTA: E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER<br/>"
            "Vigencia: del 30 de diciembre de 2025 al 30 de julio de 2026",
        ),
        ("h", "CLÁUSULA PRIMERA — Objeto"),
        (
            "p",
            "Prestación de servicios de salud de mediana y alta complejidad a los usuarios del contratante.",
        ),
        ("h", "CLÁUSULA SEGUNDA — Tarifas"),
        (
            "p",
            "Las partes acuerdan como manual tarifario el <b>Manual SOAT vigente menos el veinte por ciento (20 %)</b>, "
            "es decir, factor 0.8 sobre la tarifa SOAT del año de la prestación.",
        ),
        ("h", "CLÁUSULA TERCERA — Facturación"),
        (
            "p",
            "El contratista radicará las facturas dentro de los veinte (20) días siguientes al egreso.",
        ),
        ("h", "CLÁUSULA CUARTA — Soportes"),
        ("p", "Los soportes de cobro serán los previstos en la normatividad vigente."),
        ("h", "CLÁUSULA QUINTA — Auditoría"),
        ("p", "El contratante podrá auditar las cuentas dentro de los términos legales."),
        ("h", "CLÁUSULA SEXTA — Glosas"),
        ("p", "El trámite de glosas se sujetará al Manual Único vigente."),
        ("h", "CLÁUSULA SÉPTIMA — Pago"),
        ("p", "El pago se efectuará dentro de los plazos de ley."),
        ("h", "CLÁUSULA OCTAVA — Supervisión"),
        ("p", "La supervisión estará a cargo del jefe de sanidad correspondiente."),
        ("h", "CLÁUSULA NOVENA — Terminación"),
        ("p", "El contrato podrá terminarse por mutuo acuerdo o por incumplimiento."),
        ("h", "CLÁUSULA DÉCIMA — Domicilio"),
        ("p", "Para todos los efectos, el domicilio contractual será la ciudad de Bucaramanga."),
        ("h", "Constancia"),
        (
            "p",
            "<b>Este contrato consta de DIEZ (10) cláusulas. No contiene cláusula décima primera ni décima "
            "segunda, ni cláusula alguna que fije topes por material de osteosíntesis.</b>",
        ),
    ],
)
escribir_csv(
    C2 / "rips_procedimientos.csv",
    [
        "numFactura",
        "codProcedimiento",
        "codDiagnosticoPrincipal",
        "codDiagnosticoRelacionado",
        "vrServicio",
    ],
    [["HUS0000601892", "215601", "S72.0", "", "18940000"]],
)


# ─── CASO 3 · la cláusula que la EPS invoca y no existe ─────────────────
C3 = RAIZ / "03_AU0201_CLAUSULA_QUE_NO_EXISTE" / "soportes"
pdf(
    C3 / "historia_clinica_urgencias.pdf",
    "HISTORIA CLÍNICA — SERVICIO DE URGENCIAS",
    [
        ("h", "Identificación"),
        (
            "p",
            "Factura HUS0000602233 · Entidad: FAMISANAR EPS<br/>"
            "Fecha y hora de ingreso: 04/04/2026 · 02:14 horas<br/>Vía de ingreso: <b>URGENCIAS</b>",
        ),
        ("h", "Motivo de consulta"),
        (
            "p",
            "Paciente masculino de 54 años traído por familiares por dolor torácico opresivo de dos horas "
            "de evolución, irradiado a miembro superior izquierdo, con diaforesis.",
        ),
        ("h", "Clasificación en triage"),
        (
            "p",
            "<b>TRIAGE II</b> — atención prioritaria. Registro de la enfermera de triage a las 02:19 horas.",
        ),
        ("h", "Examen físico de ingreso"),
        ("p", "TA 158/96 · FC 104 · FR 22 · SatO2 93 % aire ambiente · Paciente álgido, ansioso."),
        ("h", "Conducta"),
        (
            "p",
            "Se activa protocolo de dolor torácico. Electrocardiograma, troponinas seriadas y observación. "
            "No se solicita autorización previa por tratarse de atención inicial de urgencias.",
        ),
        ("h", "Constancia"),
        (
            "p",
            "<b>La atención se prestó por el servicio de urgencias, en horario nocturno, "
            "sin remisión ni programación previa.</b>",
        ),
    ],
)
# El contrato es EL MISMO del caso 2: es de otra entidad y solo llega a la
# cláusula décima. Ahí está la trampa, así que se copia tal cual.
import shutil

C3.mkdir(parents=True, exist_ok=True)
shutil.copy(C2 / "contrato_440_DIGSA.pdf", C3 / "contrato_440_DIGSA.pdf")
print(
    f"  PDF   {(C3 / 'contrato_440_DIGSA.pdf').relative_to(RAIZ)}  (copia: es de OTRA entidad, a propósito)"
)

# ─── CASO 4 · el soporte que desmiente la glosa ─────────────────────────
C4 = RAIZ / "04_SO0102_SOPORTE_QUE_DICE_LO_CONTRARIO" / "soportes"
filas_kardex = "".join(
    f"<br/>Día {d:02d}/03/2026 &nbsp;·&nbsp; 08:00 y 20:00 &nbsp;·&nbsp; MEROPENEM 1 g IV &nbsp;·&nbsp; "
    f"aplicado &nbsp;·&nbsp; aux. enf. {'M.P.' if d % 2 else 'L.G.'}"
    for d in range(1, 8)
)
pdf(
    C4 / "kardex_enfermeria.pdf",
    "KARDEX DE ADMINISTRACIÓN DE MEDICAMENTOS",
    [
        ("h", "Identificación"),
        (
            "p",
            "Factura HUS0000602741 · Entidad: ALIANZA MEDELLIN ANTIOQUIA EPS SAS<br/>"
            "Servicio: Unidad de cuidado intermedio adulto",
        ),
        ("h", "Registro de administración — MEROPENEM 1 g IV"),
        (
            "p",
            "Día 01/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 01/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 02/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 02/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 03/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 03/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 04/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 04/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 05/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 05/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 06/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 06/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 07/03/2026 · 08:00 · aplicado · aux. enf. M.P."
            "<br/>Día 07/03/2026 · 20:00 · aplicado · aux. enf. L.G."
            "<br/>Día 08/03/2026 · 08:00 · aplicado · aux. enf. M.P.",
        ),
        ("h", "Total registrado"),
        ("p", "<b>QUINCE (15) dosis administradas y registradas.</b>"),
        ("h", "Anotación de enfermería"),
        (
            "p",
            "08/03/2026 · 14:30 — <b>Se suspende meropenem por orden médica.</b> No se administran las dosis "
            "de las 20:00 del día 08 ni las siguientes.",
        ),
        ("h", "Constancia"),
        (
            "p",
            "Este kardex NO incluye la orden médica de suspensión, que reposa en la historia clínica.",
        ),
    ],
)
pdf(
    C4 / "factura.pdf",
    "E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER — FACTURA DE VENTA",
    [
        ("h", "Datos"),
        ("p", "Número: <b>HUS0000602741</b> · Entidad: ALIANZA MEDELLIN ANTIOQUIA EPS SAS"),
        ("h", "Detalle del medicamento objetado"),
        (
            "p",
            "MEROPENEM 1 g polvo para solución inyectable<br/>"
            "Cantidad facturada: <b>18</b> · Valor unitario: <b>$110.000</b> · Subtotal: <b>$1.980.000</b>",
        ),
        ("h", "Totales"),
        ("p", "Total factura: <b>$3.870.000</b> · Valor glosado por el pagador: <b>$1.980.000</b>"),
    ],
)

# ─── CASO 5 · sin soportes, a propósito ────────────────────────────────
C5 = RAIZ / "05_FA0205_SIN_NADA" / "soportes"
C5.mkdir(parents=True, exist_ok=True)
(C5 / "LEER_ANTES_DE_PROBAR.txt").write_text(
    "ESTA CARPETA ESTA VACIA A PROPOSITO.\n"
    "=====================================\n\n"
    "La prueba ST-05 existe para comprobar que el motor sabe decir\n"
    "«NO PUEDO DETERMINARLO CON LOS SOPORTES DISPONIBLES».\n\n"
    "NO adjunte ningun archivo al correr esta prueba.\n\n"
    "Si el motor produce una defensa de fondo bien redactada —citando\n"
    "la Ley 1438, hablando de la carga de la prueba y pidiendo el\n"
    "levantamiento— ESO ES EL FALLO QUE ESTA PRUEBA BUSCA, no un exito.\n",
    encoding="utf-8",
)
print(f"  TXT   {(C5 / 'LEER_ANTES_DE_PROBAR.txt').relative_to(RAIZ)}  (carpeta vacia a proposito)")

print("\nsoportes generados")
