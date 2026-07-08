"""Asignación automática del GESTOR del Excel de recepción al usuario.

Cada fila de la hoja INICIAL trae la columna GESTOR ("GESTOR PRUEBA").
La importación debe resolver ese nombre contra UsuarioRecord (tolerante a
mayúsculas, tildes, nombre parcial y local-part del email) y setear
auditor_email para que la glosa aparezca en "Mis glosas" del usuario.
Si nadie matchea: la glosa queda sin asignar y el resumen registra la
advertencia para el coordinador (gestores_sin_usuario + advertencias).
"""

from datetime import datetime, timedelta
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.models.db import GlosaRecord, UsuarioRecord
from app.services.recepcion_service import (
    RecepcionService,
    construir_indice_usuarios,
    resolver_gestor_a_email,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

_HEADERS_INICIAL = [
    "GESTOR",
    "FECHA DE ENTREGA",
    "FECHA RADICACION",
    "FECHA DOCUMENTO DGH",
    "FECHA RECEPCION",
    "ENTIDAD",
    "FACTURA",
    "CONSECUTIVO DGH",
    "VALOR GLOSA",
    "VENCE",
    "DEVOLUCION \nS/N",
    "DIAS \nRADICACION VS RECEPCION",
]


def _fila_inicial(gestor: str, factura: str, consecutivo: str = "100001"):
    return [
        gestor,
        "10/06/2026",
        "21/05/2026",
        "05/06/2026",
        "05/06/2026",
        "U999999 - EPS DE PRUEBA",
        factura,
        consecutivo,
        "36402",
        "26/06/2026",
        "S",
        "11",
    ]


def _excel_inicial(filas) -> bytes:
    """Estructura real: fila 1 título, fila 2 headers, fila 3+ datos."""
    wb = Workbook()
    ws = wb.active
    ws.title = "INICIAL"
    ws.append(["ENTREGA GLOSA INICIAL"] + [""] * (len(_HEADERS_INICIAL) - 1))
    ws.append(_HEADERS_INICIAL)
    for f in filas:
        ws.append(f)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def _crear_usuario(db, nombre, email, **extra):
    u = UsuarioRecord(
        nombre=nombre,
        email=email,
        rol="AUDITOR",
        activo=1,
        password_hash="x",
        **extra,
    )
    db.add(u)
    db.commit()
    return u


# ─── Resolución pura (sin Excel) ─────────────────────────────────────────────


class TestResolverGestor:
    def test_match_exacto_insensible_a_tildes_y_mayusculas(self, db):
        _crear_usuario(db, "Gestor Préba", "gestor.preba@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("GESTOR PREBA", indice)
        assert email == "gestor.preba@hus.gov.co"
        assert motivo == "exacto"

    def test_match_parcial_nombre_mas_largo_en_bd(self, db):
        # Excel trae 2 nombres; el usuario registró nombre completo
        _crear_usuario(db, "Gestor Prueba Cárdenas", "gp@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("GESTOR PRUEBA", indice)
        assert email == "gp@hus.gov.co"
        assert motivo == "parcial"

    def test_match_tokens_desordenados(self, db):
        _crear_usuario(db, "Prueba Gestor", "pg@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, _ = resolver_gestor_a_email("GESTOR PRUEBA", indice)
        assert email == "pg@hus.gov.co"

    def test_match_por_local_part_del_email(self, db):
        # Usuario sin campo nombre — solo el email lo identifica
        _crear_usuario(db, "", "gestor.prueba@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("GESTOR PRUEBA", indice)
        assert email == "gestor.prueba@hus.gov.co"
        assert motivo == "email"

    def test_sin_match(self, db):
        _crear_usuario(db, "Otra Persona", "otra@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("GESTOR INEXISTENTE", indice)
        assert email is None
        assert motivo == "sin_match"

    def test_vacio_y_sin_asignar_no_warn(self, db):
        indice = construir_indice_usuarios(db)
        assert resolver_gestor_a_email("", indice) == (None, "vacio")
        assert resolver_gestor_a_email("SIN ASIGNAR", indice) == (None, "vacio")

    def test_ambiguo_equipo_no_asigna_a_uno_al_azar(self, db):
        # Dos usuarios distintos con el mismo nombre de equipo
        _crear_usuario(db, "Equipo Aseguradoras", "a1@hus.gov.co")
        _crear_usuario(db, "Equipo Aseguradoras", "a2@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("EQUIPO ASEGURADORAS", indice)
        assert email is None
        assert motivo == "ambiguo"

    def test_desempate_exacto_gana_sobre_parcial(self, db):
        _crear_usuario(db, "Gestor Prueba", "exacto@hus.gov.co")
        _crear_usuario(db, "Gestor Prueba Cárdenas", "parcial@hus.gov.co")
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("GESTOR PRUEBA", indice)
        assert email == "exacto@hus.gov.co"
        assert motivo == "exacto"

    def test_usuario_inactivo_no_matchea(self, db):
        u = _crear_usuario(db, "Gestor Prueba", "inactivo@hus.gov.co")
        u.activo = 0
        db.commit()
        indice = construir_indice_usuarios(db)
        email, motivo = resolver_gestor_a_email("GESTOR PRUEBA", indice)
        assert email is None
        assert motivo == "sin_match"

    def test_vacaciones_redirige_al_delegado(self, db):
        ahora = datetime.now()
        _crear_usuario(
            db,
            "Gestor Prueba",
            "titular@hus.gov.co",
            vacaciones_desde=ahora - timedelta(days=1),
            vacaciones_hasta=ahora + timedelta(days=10),
            delega_a_email="delegado@hus.gov.co",
        )
        indice = construir_indice_usuarios(db)
        email, _ = resolver_gestor_a_email("GESTOR PRUEBA", indice)
        assert email == "delegado@hus.gov.co"


# ─── End-to-end vía Excel ────────────────────────────────────────────────────


class TestAsignacionEnImportacion:
    def test_happy_path_asigna_auditor_email(self, db):
        _crear_usuario(db, "Gestor Prueba", "gestor.prueba@hus.gov.co")
        contenido = _excel_inicial([_fila_inicial("GESTOR PRUEBA", "HUS0000000001")])
        resumen = RecepcionService(db).procesar_excel(contenido)

        assert resumen.creadas == 1
        assert resumen.gestores_asignados == {"GESTOR PRUEBA": "gestor.prueba@hus.gov.co"}
        assert resumen.gestores_sin_usuario == []
        g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000001").one()
        assert g.auditor_email == "gestor.prueba@hus.gov.co"
        assert g.gestor_nombre == "GESTOR PRUEBA"

    def test_sin_match_deja_sin_asignar_y_advierte(self, db):
        contenido = _excel_inicial(
            [
                _fila_inicial("GESTOR FANTASMA", "HUS0000000002", "100002"),
                _fila_inicial("GESTOR FANTASMA", "HUS0000000003", "100003"),
            ]
        )
        resumen = RecepcionService(db).procesar_excel(contenido)

        assert resumen.creadas == 2
        # auditor_email queda vacío
        for g in db.query(GlosaRecord).all():
            assert g.auditor_email is None
        # Una sola advertencia por gestor (no por fila) y visible en to_dict
        assert resumen.gestores_sin_usuario == ["GESTOR FANTASMA"]
        assert len(resumen.advertencias) == 1
        assert "GESTOR FANTASMA" in resumen.advertencias[0]
        d = resumen.to_dict()
        assert d["gestores_sin_usuario"] == ["GESTOR FANTASMA"]
        assert d["advertencias"] == resumen.advertencias
        # No es un error de importación (las filas SÍ entraron)
        assert resumen.errores == []

    def test_reimportacion_sin_match_no_pisa_asignacion_manual(self, db):
        contenido = _excel_inicial([_fila_inicial("GESTOR FANTASMA", "HUS0000000004")])
        RecepcionService(db).procesar_excel(contenido)
        g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000004").one()
        assert g.auditor_email is None

        # El coordinador asigna a mano
        g.auditor_email = "manual@hus.gov.co"
        db.commit()

        # Reimporta el mismo Excel con el valor cambiado (fuerza UPDATE,
        # no duplicado exacto): la asignación manual debe sobrevivir.
        fila = _fila_inicial("GESTOR FANTASMA", "HUS0000000004")
        fila[8] = "99999"  # VALOR GLOSA distinto
        RecepcionService(db).procesar_excel(_excel_inicial([fila]))
        db.expire_all()
        g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000004").one()
        assert g.auditor_email == "manual@hus.gov.co"

    def test_reimportacion_con_match_actualiza_asignacion(self, db):
        _crear_usuario(db, "Gestor Prueba", "gestor.prueba@hus.gov.co")
        contenido = _excel_inicial([_fila_inicial("GESTOR PRUEBA", "HUS0000000005")])
        RecepcionService(db).procesar_excel(contenido)

        fila = _fila_inicial("GESTOR PRUEBA", "HUS0000000005")
        fila[8] = "77777"  # fuerza UPDATE
        resumen = RecepcionService(db).procesar_excel(_excel_inicial([fila]))
        assert resumen.actualizadas == 1
        g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000005").one()
        assert g.auditor_email == "gestor.prueba@hus.gov.co"
