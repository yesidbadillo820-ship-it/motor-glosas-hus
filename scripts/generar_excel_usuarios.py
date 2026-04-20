"""Genera el Excel de usuarios y contraseñas para entrega.

Ejecutar:
    python scripts/generar_excel_usuarios.py

Genera: docs/usuarios_motor_glosas.xlsx
"""
import sys
from pathlib import Path

# Añade raíz del proyecto al path
PROY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROY))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# Lista canónica de usuarios (debe coincidir con app/main.py USUARIOS_CORPORATIVOS).
# Cada password = prefijo del email.
USUARIOS = [
    ("Auditor Principal",                     "admin@hus.gov.co",                "SUPER_ADMIN"),
    ("YESID PEREZ",                           "glosashus09@sinacsc.com",         "SUPER_ADMIN"),
    ("DIANEYDA QUINTERO",                     "glosashus11@sinacsc.com",         "AUDITOR"),
    ("CAROLINA CIFUENTES",                    "glosashus02@sinacsc.com",         "AUDITOR"),
    ("JHON JAIMES",                           "glosashus04@sinacsc.com",         "AUDITOR"),
    ("MARICELA ROJAS",                        "glosashus05@sinacsc.com",         "AUDITOR"),
    ("IRMA RIOS",                             "carterahus01@sinacsc.com",        "AUDITOR"),
    ("RUBY MILENA",                           "carterahus04@sinacsc.com",        "AUDITOR"),
    ("PATRICIA QUIÑONES",                     "carterahus05@sinacsc.com",        "AUDITOR"),
    ("KAREN ORTIZ",                           "radicadevoluciones@sinacsc.com",  "AUDITOR"),
    ("SEBASTIAN SANCHES",                     "devoluciones01@sinacsc.com",      "AUDITOR"),
    ("YUDY AMAYA",                            "coordinacioncartera@hus.gov.co",  "AUDITOR"),
    ("CLAUDIA SUAREZ",                        "glosashus08@sinacsc.com",         "AUDITOR"),
    ("YENFERSON ORTEGA",                      "glosashus07@sinacsc.com",         "AUDITOR"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)",         "glosashus12@sinacsc.com",         "AUDITOR"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)",         "devoluciones02@sinacsc.com",      "AUDITOR"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)",         "glosashus10@sinacsc.com",         "AUDITOR"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)",         "glosashus16@sinacsc.com",         "AUDITOR"),
    ("LAURA DIAZ",                            "auditorhus01@sinacsc.com",        "AUDITOR"),
    ("LEIDY JHOANA SANGUINO",                 "auditorhus02@sinacsc.com",        "AUDITOR"),
    ("LEYDI ZULAY GONZALEZ",                  "auditorhus03@sinacsc.com",        "AUDITOR"),
    ("JOHANNA MORENO",                        "devoluciones03@sinacsc.com",      "AUDITOR"),
    ("EDGAR SILVA",                           "devoluciones1@sinacsc.com",       "AUDITOR"),
    ("OSCAR VILLAMIZAR",                      "glosashus03@sinacsc.com",         "AUDITOR"),
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Credenciales de Acceso"

    # ---- Encabezado institucional ----
    ws.merge_cells("A1:E1")
    c = ws["A1"]
    c.value = "ESE HOSPITAL UNIVERSITARIO DE SANTANDER"
    c.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor="0B1220")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:E2")
    c = ws["A2"]
    c.value = "Motor de Glosas — Credenciales de Acceso"
    c.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor="0369A1")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    ws.merge_cells("A3:E3")
    c = ws["A3"]
    c.value = (
        "INSTRUCCIONES: La contraseña inicial de cada usuario corresponde al PREFIJO de su correo "
        "(parte antes del @). Por ejemplo, para glosashus04@sinacsc.com, la contraseña es 'glosashus04'. "
        "Cambie su contraseña inmediatamente después del primer ingreso."
    )
    c.font = Font(name="Calibri", size=9, italic=True, color="475569")
    c.fill = PatternFill("solid", fgColor="F0F9FF")
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[3].height = 38

    # ---- Encabezado de tabla ----
    headers = ["#", "Nombre completo", "Correo institucional", "Contraseña inicial", "Rol"]
    header_fill = PatternFill("solid", fgColor="0369A1")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_thin
    ws.row_dimensions[5].height = 26

    # ---- Filas de usuarios ----
    rol_colors = {
        "SUPER_ADMIN": ("FEF3C7", "92400E"),  # ambar
        "AUDITOR":     ("DBEAFE", "1E40AF"),  # azul
    }
    fill_alt = PatternFill("solid", fgColor="F8FAFC")
    for i, (nombre, email, rol) in enumerate(USUARIOS, start=1):
        row = 5 + i
        password = email.split("@")[0]
        rol_bg, rol_fg = rol_colors.get(rol, ("E2E8F0", "334155"))
        # # (ID)
        c = ws.cell(row=row, column=1, value=i)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.font = Font(name="Calibri", size=10, bold=True, color="64748B")
        # Nombre
        c = ws.cell(row=row, column=2, value=nombre)
        c.font = Font(name="Calibri", size=10, color="0F172A")
        c.alignment = Alignment(vertical="center", indent=1)
        # Email
        c = ws.cell(row=row, column=3, value=email)
        c.font = Font(name="Calibri", size=10, color="334155")
        c.alignment = Alignment(vertical="center", indent=1)
        # Password (en mono bold)
        c = ws.cell(row=row, column=4, value=password)
        c.font = Font(name="Consolas", size=10, bold=True, color="0369A1")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.fill = PatternFill("solid", fgColor="EFF6FF")
        # Rol con badge
        c = ws.cell(row=row, column=5, value=rol)
        c.font = Font(name="Calibri", size=9, bold=True, color=rol_fg)
        c.fill = PatternFill("solid", fgColor=rol_bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
        # Bordes a toda la fila
        for col in range(1, 6):
            ws.cell(row=row, column=col).border = border_thin
        # Alternar bg de filas (excepto password que ya tiene)
        if i % 2 == 0:
            for col in [1, 2, 3, 5]:
                cur = ws.cell(row=row, column=col)
                if not cur.fill or cur.fill.fgColor.rgb == "00000000":
                    cur.fill = fill_alt
        ws.row_dimensions[row].height = 22

    # ---- Anchos de columna ----
    widths = {1: 5, 2: 36, 3: 36, 4: 24, 5: 14}
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w

    # ---- Pie de página ----
    last_row = 5 + len(USUARIOS) + 2
    ws.merge_cells(start_row=last_row, start_column=1, end_row=last_row, end_column=5)
    c = ws.cell(row=last_row, column=1)
    c.value = (
        f"Total de usuarios: {len(USUARIOS)}  ·  "
        "URL: https://motor-glosas-hus.onrender.com  ·  "
        "Soporte: cartera@hus.gov.co"
    )
    c.font = Font(name="Calibri", size=9, italic=True, color="64748B")
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.fill = PatternFill("solid", fgColor="F8FAFC")
    ws.row_dimensions[last_row].height = 22

    # Notas de seguridad
    notas_row = last_row + 2
    ws.merge_cells(start_row=notas_row, start_column=1, end_row=notas_row, end_column=5)
    c = ws.cell(row=notas_row, column=1)
    c.value = (
        "🔒 SEGURIDAD: (1) La contraseña inicial debe cambiarse en el primer login.  "
        "(2) Activar autenticación de dos factores (2FA) desde el menú de usuario.  "
        "(3) No compartir credenciales — cada usuario tiene un registro de auditoría individual."
    )
    c.font = Font(name="Calibri", size=9, color="991B1B")
    c.fill = PatternFill("solid", fgColor="FEF2F2")
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[notas_row].height = 38

    # Freeze panes para mantener encabezado al hacer scroll
    ws.freeze_panes = "A6"

    # Guardar
    output = PROY / "docs" / "usuarios_motor_glosas.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    print(f"✓ Excel generado: {output}")
    print(f"  Total usuarios: {len(USUARIOS)}")


if __name__ == "__main__":
    main()
