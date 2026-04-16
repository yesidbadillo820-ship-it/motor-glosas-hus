from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


ROL_SUPER_ADMIN = "SUPER_ADMIN"
ROL_COORDINADOR = "COORDINADOR"
ROL_AUDITOR = "AUDITOR"
ROL_VIEWER = "VIEWER"


class GlosaRecord(Base):
    __tablename__ = "historial"

    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    eps = Column(String, nullable=False, index=True)
    paciente = Column(String)
    factura = Column(String(50), default="N/A")
    numero_radicado = Column(String(50))
    codigo_glosa = Column(String, index=True)
    valor_objetado = Column(Float, default=0.0)
    valor_aceptado = Column(Float, default=0.0)
    etapa = Column(String)
    estado = Column(String, index=True)
    dictamen = Column(Text)
    dias_restantes = Column(Integer, default=0)
    modelo_ia = Column(String(100))
    workflow_state = Column(String(50), default="RADICADA")
    score = Column(Float, default=0.0)
    prioridad = Column(String(50), default="NORMAL")
    responsable = Column(String(200))
    fecha_vencimiento = Column(DateTime(timezone=True))
    request_id = Column(String(50))
    nota_workflow = Column(String(500))

    auditor_email = Column(String(200))
    decision_eps = Column(String(50))
    fecha_decision_eps = Column(DateTime(timezone=True))
    valor_recuperado = Column(Float, default=0.0)
    observacion_eps = Column(Text)

    # Campos de importación desde recepción
    gestor_nombre = Column(String(200), index=True)
    fecha_radicacion_factura = Column(DateTime(timezone=True))
    fecha_documento_dgh = Column(DateTime(timezone=True))
    fecha_recepcion = Column(DateTime(timezone=True))
    fecha_entrega = Column(DateTime(timezone=True))
    consecutivo_dgh = Column(String(50), index=True)
    es_devolucion = Column(String(1))
    radicado_info = Column(String(200))

    __table_args__ = (
        Index("ix_historial_alertas", "dias_restantes", "estado"),
        Index("ix_historial_auditor", "auditor_email"),
        Index("ix_historial_decision", "decision_eps"),
    )


class PlantillaRecord(Base):
    __tablename__ = "plantillas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    codigo = Column(String(20))
    tipo = Column(String(50))
    eps = Column(String(200))
    plantilla = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    activa = Column(Integer, default=1)


class ContratoRecord(Base):
    __tablename__ = "contratos"
    eps = Column(String, primary_key=True, index=True)
    detalles = Column(String)


class UsuarioRecord(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    rol = Column(String(50), default=ROL_AUDITOR)
    activo = Column(Integer, default=1)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())


class AuditLogRecord(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    usuario_email = Column(String(200), index=True)
    usuario_rol = Column(String(50))
    accion = Column(String(100))
    tabla = Column(String(100))
    registro_id = Column(Integer, nullable=True)
    campo = Column(String(100), nullable=True)
    valor_anterior = Column(Text, nullable=True)
    valor_nuevo = Column(Text, nullable=True)
    detalle = Column(Text, nullable=True)
    ip = Column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_audit_usuario_fecha", "usuario_email", "timestamp"),
    )


class ConciliacionRecord(Base):
    __tablename__ = "conciliaciones"

    id = Column(Integer, primary_key=True, index=True)
    glosa_id = Column(Integer, ForeignKey("historial.id", ondelete="CASCADE"), index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    creado_por = Column(String(200))
    fecha_audiencia = Column(DateTime(timezone=True))
    lugar = Column(String(300))
    participantes_hus = Column(Text)
    participantes_eps = Column(Text)
    resultado = Column(String(50))
    valor_conciliado = Column(Float, default=0.0)
    observaciones = Column(Text)
    siguiente_paso = Column(String(200))
    acta_numero = Column(String(100))

    __table_args__ = (
        Index("ix_conciliacion_glosa", "glosa_id"),
    )
