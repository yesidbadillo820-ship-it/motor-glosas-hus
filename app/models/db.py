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
    referencia = Column(String(300))
    observacion_tecnico = Column(Text)
    tipo_glosa_excel = Column(String(50))
    profesional_medico = Column(String(200))

    # Campos para historial detallado (vista IPS estilo Excel)
    texto_glosa_original = Column(Text)   # tabla_excel o input original del formulario
    codigo_respuesta = Column(String(20)) # RE9901, RE9502, RE9801, RE9702, RE9602
    cups_servicio = Column(String(50))    # CUPS extraído del servicio glosado
    servicio_descripcion = Column(String(400))  # Descripción del servicio/procedimiento
    concepto_glosa = Column(Text)         # Descripción oficial del código de glosa

    # Metadatos adicionales del Excel de recepción (hojas INICIAL/RATIFICADA/I/R)
    eps_codigo = Column(String(20), index=True)   # "U220181", "C230051", ...
    tecnico_recepcion = Column(String(200))        # TECNICO QUE RECEPCIONO
    fecha_objecion_eps = Column(DateTime(timezone=True))  # FechaObjecion (hoja I/R)
    saldo_factura = Column(Float, default=0.0)     # FacturaCartera.Saldo (hoja I/R)
    valor_factura = Column(Float, default=0.0)     # FacturaCartera.Valor (hoja I/R)
    tercero_nit = Column(String(30))               # FacturaCartera.Tercero.Documento (hoja I/R)
    # Nombre comercial corto de la entidad pagadora (FacturaCartera.Tercero.
    # NombreCompletoNA). Mas corto y limpio que el plan EPS, ej.
    # "DISPENSARIO MEDICO BUCARAMANGA" vs el plan
    # "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG".
    # Se usa en la UI de conceptos y en el texto del dictamen.
    tercero_nombre = Column(String(300))
    # Días hábiles entre FECHA RADICACION y FECHA DOCUMENTO DGH (excluye
    # sábados, domingos y festivos). Clave para detectar extemporaneidad:
    # si > 20 días hábiles, la EPS glosó fuera de término (Art. 57 Ley 1438/2011).
    dias_radicacion_dgh = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_historial_alertas", "dias_restantes", "estado"),
        Index("ix_historial_auditor", "auditor_email"),
        Index("ix_historial_decision", "decision_eps"),
    )


class ConceptoGlosaRecord(Base):
    """Detalle de concepto-por-concepto de una glosa.

    Una glosa (GlosaRecord) suele agrupar N conceptos (N servicios/CUPS
    glosados). Los importadores del Excel de recepción cargan esta tabla
    desde las hojas 'I' (Glosa_Inicial) y 'R' (Glosa_Ratificada) del DGH.
    """
    __tablename__ = "conceptos_glosa"

    id = Column(Integer, primary_key=True, index=True)
    glosa_id = Column(Integer, ForeignKey("historial.id", ondelete="CASCADE"), index=True, nullable=False)

    # Identificadores del DGH (idempotencia)
    oid_dgh = Column(String(50), index=True)       # ListadoConceptos.Oid (único por concepto)
    consecutivo_dgh = Column(String(50), index=True)  # mismo CONSECUTIVO DGH que la glosa (denormalizado)
    factura = Column(String(50), index=True)       # denormalizado para joins rápidos

    # Código de glosa + motivo canónico
    codigo_glosa = Column(String(20), index=True)  # TA0801, FA0603, TA0201, ...
    nombre_glosa = Column(Text)                     # ConceptoObjecion.Nombre ("Los cargos por apoyo diagnóstico...")

    # Servicio/CUPS glosado
    cups_codigo = Column(String(50))               # 906625, FMQ0163-1, 39143A-10
    cups_descripcion = Column(Text)                 # "GONADOTROPINA CORIONICA SUBUNIDAD BETA..."
    centro_costo = Column(String(200))              # "734005 - LABORATORIO - INMUNOLOGIA"

    # Valor y observaciones de la EPS para ESTE concepto específico
    valor_objetado = Column(Float, default=0.0)    # ListadoConceptos.ValorObjecion
    observacion_eps = Column(Text)                  # ListadoConceptos.Observaciones (motivo fino de la EPS)

    # Respuesta del auditor (se llena cuando analiza el concepto)
    dictamen_html = Column(Text)
    score = Column(Float)
    respondido_en = Column(DateTime(timezone=True))
    respondido_por = Column(String(200))

    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_concepto_glosa", "glosa_id", "codigo_glosa"),
        Index("ix_concepto_oid", "oid_dgh"),
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


class DictamenVersionRecord(Base):
    """Snapshot del dictamen cada vez que se refina/regenera.
    Permite ver el historial y restaurar una versión anterior."""
    __tablename__ = "dictamen_versiones"

    id = Column(Integer, primary_key=True, index=True)
    glosa_id = Column(Integer, ForeignKey("historial.id", ondelete="CASCADE"), index=True)
    dictamen_html = Column(Text, nullable=False)
    accion = Column(String(50))  # CREAR | REFINAR | REGENERAR | RESTAURAR
    mensaje_refinar = Column(Text)  # instrucción cuando fue REFINAR
    autor_email = Column(String(200))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_dictamen_ver_glosa", "glosa_id", "creado_en"),
    )


class GlosaEliminadaRecord(Base):
    """Papelera: glosas eliminadas con soft-delete. Se pueden restaurar
    dentro de 30 días. Después se purgan permanentemente."""
    __tablename__ = "glosas_eliminadas"

    id = Column(Integer, primary_key=True, index=True)
    glosa_id_original = Column(Integer, index=True)
    snapshot_json = Column(Text, nullable=False)  # dump JSON del GlosaRecord
    eliminado_por = Column(String(200))
    eliminado_en = Column(DateTime(timezone=True), server_default=func.now())
    motivo = Column(String(300))


class PushSubscriptionRecord(Base):
    """Suscripciones Web Push por usuario (para notificaciones al navegador)."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    usuario_email = Column(String(200), index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    user_agent = Column(String(500))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    ultima_usada_en = Column(DateTime(timezone=True))


class AdjuntoConciliacionRecord(Base):
    """Screenshots/evidencia adjunta a una conciliación."""
    __tablename__ = "adjuntos_conciliacion"

    id = Column(Integer, primary_key=True, index=True)
    conciliacion_id = Column(Integer, ForeignKey("conciliaciones.id", ondelete="CASCADE"), index=True)
    nombre = Column(String(300))
    mime_type = Column(String(100))
    tamano_bytes = Column(Integer)
    contenido_b64 = Column(Text, nullable=False)  # base64 del archivo
    subido_por = Column(String(200))
    subido_en = Column(DateTime(timezone=True), server_default=func.now())


class ComentarioGlosaRecord(Base):
    """Hilo de comentarios por glosa para discusión interna del equipo."""
    __tablename__ = "comentarios_glosa"

    id = Column(Integer, primary_key=True, index=True)
    glosa_id = Column(Integer, ForeignKey("historial.id", ondelete="CASCADE"), index=True)
    autor_email = Column(String(200), index=True)
    autor_nombre = Column(String(200))
    autor_rol = Column(String(50))
    texto = Column(Text, nullable=False)
    mencion = Column(String(200))   # email de quien se menciona con @
    resuelto = Column(Integer, default=0)
    resuelto_por = Column(String(200))
    resuelto_en = Column(DateTime(timezone=True))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_comentarios_glosa", "glosa_id", "creado_en"),
    )


class PlantillaGoldRecord(Base):
    """Argumentos técnico-jurídicos que ganaron (EPS levantó la glosa).

    Se usan como few-shot examples al llamar a la IA para nuevas glosas
    del mismo (EPS, código) — mejoran calidad con el tiempo.
    """
    __tablename__ = "plantillas_gold"

    id = Column(Integer, primary_key=True, index=True)
    eps = Column(String(200), index=True)
    codigo_glosa = Column(String(20), index=True)
    tipo = Column(String(50))
    titulo = Column(String(200))
    argumento = Column(Text, nullable=False)
    glosa_origen_id = Column(Integer)  # ID de GlosaRecord que ganó
    valor_recuperado = Column(Float, default=0.0)
    usos = Column(Integer, default=0)
    creado_por = Column(String(200))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    ultima_uso_en = Column(DateTime(timezone=True))
    notas = Column(Text)
    activa = Column(Integer, default=1)

    __table_args__ = (
        Index("ix_plantilla_gold_lookup", "eps", "codigo_glosa", "activa"),
    )


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
    # 2FA TOTP (obligatorio para SUPER_ADMIN cuando está configurado)
    totp_secret = Column(String(64))
    totp_activo = Column(Integer, default=0)
    # Forzar cambio de password en primer login (1=debe cambiar, 0=ok)
    must_change_password = Column(Integer, default=0, nullable=False, server_default="0")
    # Timestamp del último cambio de password (para auditoría)
    password_changed_at = Column(DateTime(timezone=True))
    # Equipo al que pertenece el usuario (para compartir bandeja entre varios
    # correos del mismo equipo, ej. EQUIPO_ASEGURADORAS con 4 emails). Si
    # está seteado, las vistas "Mis glosas" e "Historial" agrupan por equipo.
    equipo = Column(String(50), index=True, nullable=True)


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

    # Trazabilidad bilateral (ciclo completo con EPS)
    contra_respuesta_eps = Column(Text)            # Texto de la respuesta de la EPS antes de conciliar
    fecha_contra_respuesta_eps = Column(DateTime(timezone=True))
    postura_hus = Column(Text)                      # Posición final de HUS para la audiencia
    fecha_acta = Column(DateTime(timezone=True))    # Fecha en que se firmó el acta
    valor_ratificado_hus = Column(Float, default=0.0)  # Valor que HUS defendió
    estado_bilateral = Column(String(40), default="PROGRAMADA")
    # Estados: PROGRAMADA → EPS_RESPONDIO → AUDIENCIA_REALIZADA → ACTA_FIRMADA → CERRADA

    __table_args__ = (
        Index("ix_conciliacion_glosa", "glosa_id"),
    )


class TarifaContratadaRecord(Base):
    """Catálogo de tarifas pactadas por contrato con cada EPS.

    Carga masiva por CSV desde el panel admin /tarifas. El motor de glosas
    consulta esta tabla cuando una glosa es por TARIFAS (TA*) para decidir
    si el valor facturado coincide con lo pactado. Si coincide → glosa
    no procede. Si hay diferencia → evaluar.

    No aplica a aseguradoras SOAT (Mundial, Bolívar, etc) ni a EPS sin
    contrato (Sanitas, etc); esas siguen con lógica actual.
    """
    __tablename__ = "tarifas_contratadas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eps = Column(String(200), nullable=False, index=True)    # Ej: "FAMISANAR EPS"
    contrato_numero = Column(String(100))                     # Ej: "S-13-1-03-1-04958"
    codigo_cups = Column(String(30), nullable=False, index=True)  # Ej: "890202" / "FMQ6296"
    descripcion = Column(Text)                                # "CONSULTA DE PRIMERA VEZ..."
    valor_pactado = Column(Float, nullable=False, default=0.0)    # COP (solo tipo VALOR_FIJO)
    modalidad = Column(String(80))                            # "SOAT UVB VIGENTE" / "MEDICAMENTOS" / "SUMINISTROS CARDIOVASCULAR"
    # Tipo de tarifa: VALOR_FIJO (medicamentos/suministros) | SOAT_PORCENTAJE (servicios CUPS pactados como % sobre SOAT)
    tipo_tarifa = Column(String(30), nullable=False, default="VALOR_FIJO", index=True)
    # Factor de ajuste sobre SOAT vigente. Solo aplica si tipo_tarifa=SOAT_PORCENTAJE.
    # Ej: -5 → SOAT × 0.95; 0 → SOAT plano; +10 → SOAT × 1.10
    factor_ajuste = Column(Float, default=0.0)
    fuente_archivo = Column(String(300))                      # "famisanar_2026.xlsx"
    vigencia_desde = Column(DateTime(timezone=True))
    vigencia_hasta = Column(DateTime(timezone=True))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    creado_por = Column(String(200))                          # email del COORDINADOR/SUPER_ADMIN
    activa = Column(Integer, default=1, nullable=False)       # 1=activa, 0=archivada

    __table_args__ = (
        Index("ix_tarifa_eps_cups", "eps", "codigo_cups", "activa"),
    )


class AICacheRecord(Base):
    """Caché persistente de respuestas de IA (Groq / Anthropic).

    Evita pagar tokens dos veces por el mismo análisis (mismo EPS + código +
    system + user prompt). Sobrevive a reinicios/deploys de Render.

    Estrategia:
      - Clave SHA256 calculada sobre (primary_ai|modelo|eps|codigo|system|user)
      - TTL por defecto 30 días (se purga al acceder si creado_en + 30d < now)
      - hit_count: cuántas veces se reutilizó esta respuesta (métrica ahorro)
    """
    __tablename__ = "ai_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clave = Column(String(64), unique=True, nullable=False, index=True)  # SHA256 hex
    modelo = Column(String(80))                                           # "groq/llama-3.3..." | "anthropic/..."
    respuesta = Column(Text, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    ultimo_hit = Column(DateTime(timezone=True), server_default=func.now())
    hit_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_aicache_clave_creado", "clave", "creado_en"),
    )
