from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
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
    # Timestamp del último guardado del dictamen. Se usa para detectar
    # dictámenes stale tras cargar tarifas/contratos nuevos: si una tarifa
    # relevante se cargó después de `dictamen_generado_en`, la UI marca
    # el dictamen como obsoleto y sugiere re-analizar.
    dictamen_generado_en = Column(DateTime(timezone=True))
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
    texto_glosa_original = Column(Text)  # tabla_excel o input original del formulario
    codigo_respuesta = Column(String(20))  # RE9901, RE9502, RE9801, RE9702, RE9602
    cups_servicio = Column(String(50))  # CUPS extraído del servicio glosado
    servicio_descripcion = Column(String(400))  # Descripción del servicio/procedimiento
    concepto_glosa = Column(Text)  # Descripción oficial del código de glosa

    # Metadatos adicionales del Excel de recepción (hojas INICIAL/RATIFICADA/I/R)
    eps_codigo = Column(String(20), index=True)  # "U220181", "C230051", ...
    tecnico_recepcion = Column(String(200))  # TECNICO QUE RECEPCIONO
    fecha_objecion_eps = Column(DateTime(timezone=True))  # FechaObjecion (hoja I/R)
    saldo_factura = Column(Float, default=0.0)  # FacturaCartera.Saldo (hoja I/R)
    valor_factura = Column(Float, default=0.0)  # FacturaCartera.Valor (hoja I/R)
    tercero_nit = Column(String(30))  # FacturaCartera.Tercero.Documento (hoja I/R)
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

    # Evidencia de radicación ante la entidad (POST /glosas/{id}/marcar-radicada).
    # `numero_radicado` (arriba) guarda el número que asigna la EPS; estos
    # campos registran CUÁNDO y QUIÉN dejó constancia, para auditoría.
    radicado_en = Column(DateTime(timezone=True), nullable=True)
    radicado_por = Column(String(200), nullable=True)
    radicado_observacion = Column(Text, nullable=True)

    # Nota crédito asociada cuando la glosa se acepta (parcial o total).
    # El gestor la captura desde "Mis glosas respondidas".
    numero_nota_credito = Column(String(60), nullable=True, index=True)
    fecha_nota_credito = Column(DateTime(timezone=True), nullable=True)
    valor_nota_credito = Column(Float, default=0.0)
    nota_credito_observacion = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_historial_alertas", "dias_restantes", "estado"),
        Index("ix_historial_auditor", "auditor_email"),
        Index("ix_historial_decision", "decision_eps"),
        # Auditoría jun-2026 P2 #10 — caminos calientes sin índice:
        # /historial ordena por creado_en, "responder por factura" filtra
        # por factura y el tablero de workflow por workflow_state. Para
        # tablas pre-existentes los crea el lifespan (CREATE INDEX IF NOT
        # EXISTS sobre _INDICES_HISTORIAL en app/main.py).
        Index("ix_historial_creado_en", "creado_en"),
        Index("ix_historial_factura", "factura"),
        Index("ix_historial_workflow_state", "workflow_state"),
    )


class ConceptoGlosaRecord(Base):
    """Detalle de concepto-por-concepto de una glosa.

    Una glosa (GlosaRecord) suele agrupar N conceptos (N servicios/CUPS
    glosados). Los importadores del Excel de recepción cargan esta tabla
    desde las hojas 'I' (Glosa_Inicial) y 'R' (Glosa_Ratificada) del DGH.
    """

    __tablename__ = "conceptos_glosa"

    id = Column(Integer, primary_key=True, index=True)
    glosa_id = Column(
        Integer, ForeignKey("historial.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Identificadores del DGH (idempotencia)
    oid_dgh = Column(String(50), index=True)  # ListadoConceptos.Oid (único por concepto)
    consecutivo_dgh = Column(
        String(50), index=True
    )  # mismo CONSECUTIVO DGH que la glosa (denormalizado)
    factura = Column(String(50), index=True)  # denormalizado para joins rápidos

    # Código de glosa + motivo canónico
    codigo_glosa = Column(String(20), index=True)  # TA0801, FA0603, TA0201, ...
    # Ronda 50 (Bug #4): código interno del DGH/Syscafe (ej. "423", "223"
    # cuando Excel del DGH no trae el canónico Res. 2284/2023). Se guarda
    # al importar si viene y se usa al exportar en el campo
    # 'ListadoConceptos.ConceptoObjecion.Codigo' del formato DGH.
    codigo_syscafe = Column(String(20), index=True)
    nombre_glosa = Column(Text)  # ConceptoObjecion.Nombre ("Los cargos por apoyo diagnóstico...")

    # Servicio/CUPS glosado
    cups_codigo = Column(String(50))  # 906625, FMQ0163-1, 39143A-10
    cups_descripcion = Column(Text)  # "GONADOTROPINA CORIONICA SUBUNIDAD BETA..."
    centro_costo = Column(String(200))  # "734005 - LABORATORIO - INMUNOLOGIA"

    # Valor y observaciones de la EPS para ESTE concepto específico
    valor_objetado = Column(Float, default=0.0)  # ListadoConceptos.ValorObjecion
    observacion_eps = Column(Text)  # ListadoConceptos.Observaciones (motivo fino de la EPS)

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

    __table_args__ = (Index("ix_dictamen_ver_glosa", "glosa_id", "creado_en"),)


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
    conciliacion_id = Column(
        Integer, ForeignKey("conciliaciones.id", ondelete="CASCADE"), index=True
    )
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
    mencion = Column(String(200))  # email de quien se menciona con @
    resuelto = Column(Integer, default=0)
    resuelto_por = Column(String(200))
    resuelto_en = Column(DateTime(timezone=True))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_comentarios_glosa", "glosa_id", "creado_en"),)


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

    __table_args__ = (Index("ix_plantilla_gold_lookup", "eps", "codigo_glosa", "activa"),)


class ContratoRecord(Base):
    __tablename__ = "contratos"
    eps = Column(String, primary_key=True, index=True)
    detalles = Column(String)
    # Ruta absoluta al PDF del contrato vigente (en /data/contratos/...).
    # Se sobreescribe cuando se sube uno nuevo — solo guardamos el vigente.
    pdf_path = Column(String(500), nullable=True)
    pdf_subido_en = Column(DateTime(timezone=True), nullable=True)

    # Metadatos enriquecidos para argumentación contractual de alto nivel
    # (auditoría 10-jun-2026: la "otra IA" cita NIT, número de proceso SECOP,
    # fecha exacta, plazo y anexos específicos — el sistema HUS no los tenía
    # disponibles para el prompt y producía dictámenes genéricos).
    # Se llenan al parsear el PDF del contrato o al cargarlo desde el panel
    # admin. Todos opcionales — el inyector degrada elegantemente si faltan.
    numero_contrato = Column(String(120), nullable=True)
    nit_eps = Column(String(40), nullable=True)
    nit_ips = Column(String(40), nullable=True)
    razon_social_eps = Column(String(300), nullable=True)
    razon_social_ips = Column(String(300), nullable=True)
    numero_proceso_secop = Column(String(120), nullable=True)
    secop_url = Column(String(500), nullable=True)
    fecha_suscripcion = Column(DateTime(timezone=True), nullable=True)
    fecha_inicio = Column(DateTime(timezone=True), nullable=True)
    fecha_fin = Column(DateTime(timezone=True), nullable=True)
    objeto_contractual = Column(Text, nullable=True)
    anexos_descripcion = Column(Text, nullable=True)  # JSON: lista de anexos
    modalidades_tarifarias = Column(
        Text, nullable=True
    )  # JSON: ["TARIFA PROPIA ESE", "SOAT UVB", ...]


class ClausulaContrato(Base):
    """Cláusulas extraídas del PDF del contrato de cada EPS.

    El motor de glosas las inyecta como contexto al prompt IA cuando
    analiza una glosa de la EPS correspondiente. Permite que el dictamen
    cite literalmente la cláusula contractual aplicable, lo que hace la
    defensa mucho más fuerte (la EPS firmó el documento del que se cita).

    El campo `tema` matchea con `codigo_glosa[:2]` (ej: TA, SO, AU, CO,
    NN, FA) para filtrar solo cláusulas relevantes al tipo de objeción.
    """

    __tablename__ = "clausulas_contrato"

    id = Column(Integer, primary_key=True, index=True)
    eps = Column(
        String, ForeignKey("contratos.eps", ondelete="CASCADE"), index=True, nullable=False
    )
    numero_clausula = Column(String(80))
    tema = Column(String(20), index=True)
    titulo = Column(String(300))
    texto_literal = Column(Text)
    pagina = Column(Integer, nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())


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
    # RustDesk ID — para acceso remoto a la PC del gestor desde la UI
    # admin. El usuario configura el ID de su instalación RustDesk
    # (ej. "123456789") y un coordinador puede tomar control vía link
    # rustdesk://?id=XXX. Opcional, no afecta nada si está vacío.
    rustdesk_id = Column(String(40), nullable=True)
    # Etiqueta libre para el equipo (ej. "PC HUS oficina 3", "Laptop casa")
    rustdesk_etiqueta = Column(String(120), nullable=True)
    # Delegación temporal (vacaciones / licencia). Si vacaciones_desde
    # <= ahora <= vacaciones_hasta y delega_a_email está seteado, las
    # asignaciones automáticas se redirigen al delegado y la UI marca
    # el badge "Vacaciones" en perfil/cards.
    vacaciones_desde = Column(DateTime(timezone=True), nullable=True)
    vacaciones_hasta = Column(DateTime(timezone=True), nullable=True)
    delega_a_email = Column(String(200), nullable=True)
    vacaciones_motivo = Column(String(200), nullable=True)


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

    __table_args__ = (Index("ix_audit_usuario_fecha", "usuario_email", "timestamp"),)


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
    contra_respuesta_eps = Column(Text)  # Texto de la respuesta de la EPS antes de conciliar
    fecha_contra_respuesta_eps = Column(DateTime(timezone=True))
    postura_hus = Column(Text)  # Posición final de HUS para la audiencia
    fecha_acta = Column(DateTime(timezone=True))  # Fecha en que se firmó el acta
    valor_ratificado_hus = Column(Float, default=0.0)  # Valor que HUS defendió
    estado_bilateral = Column(String(40), default="PROGRAMADA")
    # Estados: PROGRAMADA → EPS_RESPONDIO → AUDIENCIA_REALIZADA → ACTA_FIRMADA → CERRADA

    __table_args__ = (Index("ix_conciliacion_glosa", "glosa_id"),)


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
    eps = Column(String(200), nullable=False, index=True)  # Ej: "FAMISANAR EPS"
    contrato_numero = Column(String(100))  # Ej: "S-13-1-03-1-04958"
    codigo_cups = Column(String(30), nullable=False, index=True)  # Ej: "890202" / "FMQ6296"
    # Ronda 45: código interno IPS (ej. '39147B-18' del HUS) para que cuando
    # la EPS glose con el código viejo podamos homologarlo al CUPS oficial
    # (Res. 2641/2025). El parser Excel llena este campo cuando hay columna
    # 'CODIGO IPS'/'CODIGO PROPIO'.
    codigo_ips = Column(String(30), index=True)
    descripcion = Column(Text)  # "CONSULTA DE PRIMERA VEZ..."
    valor_pactado = Column(Float, nullable=False, default=0.0)  # COP (solo tipo VALOR_FIJO)
    modalidad = Column(
        String(80)
    )  # "SOAT UVB VIGENTE" / "MEDICAMENTOS" / "SUMINISTROS CARDIOVASCULAR"
    # Tipo de tarifa: VALOR_FIJO (medicamentos/suministros) | SOAT_PORCENTAJE (servicios CUPS pactados como % sobre SOAT)
    tipo_tarifa = Column(String(30), nullable=False, default="VALOR_FIJO", index=True)
    # Factor de ajuste sobre SOAT vigente. Solo aplica si tipo_tarifa=SOAT_PORCENTAJE.
    # Ej: -5 → SOAT × 0.95; 0 → SOAT plano; +10 → SOAT × 1.10
    factor_ajuste = Column(Float, default=0.0)
    fuente_archivo = Column(String(300))  # "famisanar_2026.xlsx"
    vigencia_desde = Column(DateTime(timezone=True))
    vigencia_hasta = Column(DateTime(timezone=True))
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    creado_por = Column(String(200))  # email del COORDINADOR/SUPER_ADMIN
    activa = Column(Integer, default=1, nullable=False)  # 1=activa, 0=archivada

    __table_args__ = (Index("ix_tarifa_eps_cups", "eps", "codigo_cups", "activa"),)


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
    modelo = Column(String(80))  # "groq/llama-3.3..." | "anthropic/..."
    respuesta = Column(Text, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    ultimo_hit = Column(DateTime(timezone=True), server_default=func.now())
    hit_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_aicache_clave_creado", "clave", "creado_en"),)


class AICallRecord(Base):
    """Historial de cada llamada a Anthropic / Groq con métricas (R55 P2).

    Permite calcular costo total del día/semana/mes, latencia p50/p95,
    cache hit rate efectivo, identificar glosas que dispararon Opus por
    error, etc. — sin depender de parsear logs externos.

    Granularidad: 1 fila por call al LLM. En una glosa puede haber
    múltiples filas (LLM principal + retry + check riesgo). El campo
    glosa_id (nullable) permite trazar de vuelta cuando aplica.
    """

    __tablename__ = "ai_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    proveedor = Column(String(20), nullable=False)  # 'anthropic' | 'groq'
    modelo = Column(String(80), nullable=False)  # 'claude-sonnet-4-6' | 'llama-3.3-70b'
    latency_ms = Column(Integer, default=0, nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    cache_creation_input_tokens = Column(Integer, default=0, nullable=False)
    cache_read_input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    # Costo USD almacenado pre-calculado (Float es suficiente — los valores
    # típicos están entre $0.0001 y $0.10 por call).
    cost_usd = Column(Float, default=0.0, nullable=False)
    # Trazabilidad opcional
    glosa_id = Column(Integer, nullable=True, index=True)
    user_email = Column(String(200), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_aicalls_proveedor_creado", "proveedor", "creado_en"),)


class TareaDiariaRecord(Base):
    """Checklist de tareas diarias del gestor.

    Independiente del motor de glosas: cada usuario gestiona su
    propia lista (responder glosa X, preparar informe, ir a la
    reunión, etc.). El día al que pertenece la tarea se guarda
    en `fecha_para` para poder filtrar "lo de hoy".
    """

    __tablename__ = "tareas_diarias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_email = Column(String(200), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    # ALTA | MEDIA | BAJA
    prioridad = Column(String(10), default="MEDIA", nullable=False)
    # Fecha lógica (ISO date, el día al que pertenece la tarea).
    # Sin time-zone: es local, lo que importa es "hoy/mañana".
    fecha_para = Column(String(10), nullable=False, index=True)
    completada = Column(Integer, default=0, nullable=False, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    completada_en = Column(DateTime(timezone=True), nullable=True)
    # Vínculo opcional con una glosa (si la tarea es "responder GLS-...")
    glosa_id = Column(Integer, nullable=True)


class SugerenciaRecord(Base):
    """R369: feedback in-app de gestores (bugs, ideas, mejoras).

    Tabla simple para que cualquier usuario reporte fallos o
    sugerencias sin salir del sistema. Admin puede triagear
    desde /admin/sugerencias.
    """

    __tablename__ = "sugerencias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    autor_email = Column(String(200), index=True)
    autor_nombre = Column(String(200), nullable=True)
    autor_rol = Column(String(50), nullable=True)
    # tipo: BUG | IDEA | MEJORA | OTRO
    tipo = Column(String(20), default="OTRO", nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=False)
    # Contexto opcional (página visitada, glosa relacionada)
    pagina = Column(String(120), nullable=True)
    glosa_id = Column(Integer, nullable=True)
    # Estado del triage por admin
    estado = Column(String(20), default="ABIERTA", nullable=False, index=True)
    # ABIERTA | EN_REVISION | RESUELTA | DESCARTADA
    resuelto_en = Column(DateTime(timezone=True), nullable=True)
    resuelto_por = Column(String(200), nullable=True)
    nota_admin = Column(Text, nullable=True)


class EnvioCorreoRecord(Base):
    """Cada intento de envío de correo del motor (20-08-2026).

    POR QUÉ EXISTE. Yesid configuró el correo y preguntó: «¿cómo miro eso
    acá?». Hasta ahora no se podía: cada correo salía y no quedaba ni rastro
    en el portal. Para saber si algo se había enviado había que entrar a la
    bandeja de Gmail de la cuenta que envía, que es justo lo que un auditor
    no debería tener que hacer.

    OJO CON LO QUE ESTO SIGNIFICA, que no es poco: acá queda si el servidor de
    correo ACEPTÓ el mensaje. Que después LLEGUE al buzón del gestor es otra
    cosa — si la dirección no existe, el rebote llega minutos más tarde a la
    cuenta que envía y NO se ve desde acá. Esa distinción se dice en pantalla:
    prometer entrega sería mentir.
    """

    __tablename__ = "envios_correo"

    id = Column(Integer, primary_key=True, index=True)
    destinatario = Column(String(200), index=True, nullable=False)
    asunto = Column(String(300), nullable=True)
    # De dónde salió: "recepcion", "prueba", "alertas", "excel-recepcion"…
    contexto = Column(String(60), index=True, nullable=True)
    aceptado = Column(Boolean, default=False, nullable=False)
    error = Column(Text, nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class LoteImportacionRecord(Base):
    """Histórico de lotes de Importación Masiva (IM Fase 1.3).

    Cada lote del flujo /glosas/importar-masiva genera 1 registro.
    Permite:
      - Tracking en vivo del progreso (polling /lote/{id}/status)
      - Historial paginado /lotes
      - Forensia ("¿quién subió este lote, cuántas glosas creó?")
      - Auditoría SuperSalud (compliance Habeas Data)
    """

    __tablename__ = "lotes_importacion"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(40), index=True, nullable=False, unique=True)
    usuario_email = Column(String(200), index=True, nullable=False)
    total_filas = Column(Integer, default=0, nullable=False)
    procesadas = Column(Integer, default=0, nullable=False)
    exitosas = Column(Integer, default=0, nullable=False)
    fallidas = Column(Integer, default=0, nullable=False)
    costo_estimado_usd = Column(Float, default=0.0)
    costo_real_usd = Column(Float, default=0.0)  # se actualiza por fila
    estado = Column(String(20), default="PROCESANDO", index=True)
    # PROCESANDO | COMPLETO | CANCELADO | ERROR
    iniciado_en = Column(DateTime(timezone=True), server_default=func.now())
    terminado_en = Column(DateTime(timezone=True), nullable=True)
    # JSON serializado: {eps: count}
    eps_detectadas = Column(Text, nullable=True)
    # Lista de IDs de glosas creadas (JSON array)
    glosas_creadas_ids = Column(Text, nullable=True)
    # Hash sha256 del texto_excel — para detectar lotes duplicados
    texto_hash = Column(String(64), index=True, nullable=True)
    # Si gestor_asignado_id != NULL, las glosas se asignan a ese usuario
    gestor_asignado_id = Column(Integer, nullable=True, index=True)
    # Errores por fila (JSON array de {fila, error}) — capped a 100
    errores = Column(Text, nullable=True)


class ImportacionRecepcionRecord(Base):
    """Histórico de importaciones de recepción (Excel subido por el
    equipo de recepción vía /glosas/importar-recepcion).

    Guarda la ruta al Excel original en disco (/data/recepcion) y los
    IDs de glosas creadas/actualizadas, para poder regenerar y descargar
    el Excel-respuesta anotado desde la app en cualquier momento — no
    solo cuando llega por correo. Sirve además de respaldo si el envío
    SMTP falla.
    """

    __tablename__ = "importaciones_recepcion"

    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    usuario_email = Column(String(200), index=True, nullable=False)
    archivo_nombre = Column(String(300), nullable=True)
    ruta_original = Column(String(500), nullable=True)
    total_glosas = Column(Integer, default=0, nullable=False)
    # JSON array con los IDs de glosas creadas/actualizadas del lote
    glosa_ids = Column(Text, nullable=True)
    estado = Column(String(20), default="LISTO", index=True)
    # LISTO | SIN_ARCHIVO | ERROR


class NotaPrivadaRecord(Base):
    """Notas privadas por glosa, una por gestor.

    Cada gestor puede dejar notas asociadas a una glosa que SOLO el
    ve. Util para recordatorios personales: "preguntar a Mario sobre
    esta", "esperar respuesta tecnica del Dr. Lopez", "pendiente
    confirmar dosis con HC".

    Diferente de ComentarioGlosaRecord (publico, todos los
    auditores ven). El indice unico (glosa_id + autor_email)
    asegura una sola nota por par.
    """

    __tablename__ = "notas_privadas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    glosa_id = Column(Integer, index=True, nullable=False)
    autor_email = Column(String(200), index=True, nullable=False)
    contenido = Column(Text, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_nota_privada_unico", "glosa_id", "autor_email", unique=True),)


class PresetFiltroRecord(Base):
    """Presets de filtros guardados por usuario para Mis Glosas /
    Historial. Permite que cada gestor configure sus filtros
    favoritos (EPS X + estado Y + ordenado por valor) y los reutilice
    con un click. Tambien soporta presets compartidos (visibilidad
    EQUIPO o GLOBAL) cuando un coordinador comparte un filtro util.
    """

    __tablename__ = "preset_filtros"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_email = Column(String(200), index=True, nullable=False)
    nombre = Column(String(80), nullable=False)
    # JSON serializado con los filtros: {eps, estado, valor_min,
    # valor_max, orden, etc.}. Sin esquema rigido — el frontend
    # serializa lo que necesita y el backend lo guarda como blob.
    filtros = Column(Text, nullable=False)
    # PRIVADO (solo el dueno) | EQUIPO (todos los del mismo equipo) |
    # GLOBAL (todos los usuarios). Default PRIVADO.
    visibilidad = Column(String(20), default="PRIVADO", nullable=False)
    icono = Column(String(8), nullable=True)  # emoji opcional
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    ultimo_uso = Column(DateTime(timezone=True), nullable=True)
    uso_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_preset_usuario", "usuario_email", "creado_en"),)


class ComentarioThreadRecord(Base):
    """Comentarios threaded por seccion del dictamen.

    Cada comentario asociado a un (glosa_id, seccion). seccion es un
    label libre del frontend ("intro", "argumento", "conclusion") o
    un anchor de un parrafo especifico ("p:5"). parent_id permite
    respuestas anidadas estilo Linear/GitHub.
    """

    __tablename__ = "comentarios_thread"

    id = Column(Integer, primary_key=True, autoincrement=True)
    glosa_id = Column(Integer, index=True, nullable=False)
    seccion = Column(String(50), index=True, nullable=False)
    parent_id = Column(Integer, nullable=True, index=True)
    autor_email = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=False)
    resuelto = Column(Integer, default=0, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now())


class WebhookRecord(Base):
    """Webhooks salientes configurables. Cuando ocurre un evento
    cuyo nombre coincide con `eventos` (CSV), se envia un POST al
    `url` con el payload del evento. Util para integrar con Slack,
    Teams, n8n, Zapier, etc.

    Solo COORDINADOR/SUPER_ADMIN puede crear/borrar.
    """

    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    url = Column(String(800), nullable=False)
    secret = Column(String(64), nullable=True)  # HMAC firma opcional
    eventos = Column(String(500), nullable=False)  # CSV: "DECISION_EPS,CREAR,..."
    activo = Column(Integer, default=1, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    creado_por = Column(String(200))
    ultimo_disparo = Column(DateTime(timezone=True), nullable=True)
    ultimo_status = Column(String(20), nullable=True)
    disparos_total = Column(Integer, default=0, nullable=False)
    disparos_fallidos = Column(Integer, default=0, nullable=False)


class ChatConversacionRecord(Base):
    """Conversacion del Asistente Maestro IA (chat persistente).

    Cada usuario tiene N conversaciones, cada una con M mensajes.
    Sirve para volver a una sesion anterior y continuar el contexto.
    """

    __tablename__ = "chat_conversaciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_email = Column(String(200), index=True, nullable=False)
    titulo = Column(String(200), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    ultimo_mensaje_en = Column(DateTime(timezone=True), server_default=func.now())
    archivado = Column(Integer, default=0, nullable=False)


class ChatMensajeRecord(Base):
    """Mensaje individual de una conversacion. Rol = user|assistant."""

    __tablename__ = "chat_mensajes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversacion_id = Column(Integer, index=True, nullable=False)
    rol = Column(String(20), nullable=False)  # user | assistant | tool_use | tool_result
    contenido = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # tool_use info, tokens, etc
    creado_en = Column(DateTime(timezone=True), server_default=func.now())


class SnippetRecord(Base):
    """Snippets / abreviaciones expandibles del usuario.

    Cada gestor define atajos como '/ratif' -> texto fijo de 200
    palabras. Al escribir el atajo en cualquier textarea grande
    (con clase .snippet-enabled), se expande automaticamente.

    Visibilidad similar a presets: PRIVADO (default) | EQUIPO | GLOBAL.
    Los GLOBAL los crea el coordinador y todos los usan (plantillas
    institucionales).
    """

    __tablename__ = "snippets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_email = Column(String(200), index=True, nullable=False)
    atajo = Column(String(50), nullable=False)
    contenido = Column(Text, nullable=False)
    descripcion = Column(String(200), nullable=True)
    visibilidad = Column(String(20), default="PRIVADO", nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    uso_count = Column(Integer, default=0, nullable=False)
    ultimo_uso = Column(DateTime(timezone=True), nullable=True)


class RutaFacturaRecord(Base):
    """Mapeo factura HUS -> ruta de la carpeta de soportes en el share
    local del HUS (ej. Y:\\FEBRERO 2026 - SOPORTES RADICACION CARPETA
    2\\DISPENSARIO\\VANESSA\\ENV-221979-C\\HUS466775).

    El gestor sube un CSV/XLSX con dos columnas (factura, ruta) y la
    UI consulta esta tabla cuando va a auditar una factura. El
    browser del gestor (que SI tiene visibilidad de Y:) descarga los
    PDFs del servidor HTTP local y los sube al motor para auditarlos
    con Claude.

    El motor en cloud no necesita acceso al share — solo necesita el
    string de la ruta para que el frontend pueda construir la URL.
    """

    __tablename__ = "rutas_factura"

    factura_hus = Column(String(50), primary_key=True)
    ruta_carpeta = Column(String(800), nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now())
    importado_por = Column(String(200), nullable=True)
    # Metadatos extra opcionales (eps, mes, ambiente) deserializados de
    # las columnas de la fuente original. JSON blob.
    meta = Column(Text, nullable=True)


class QualityGateRunRecord(Base):
    """Registro de cada ejecución del Quality Gate.

    Plan de Transformación Ola 1 — observabilidad del pipeline determinístico.
    Cada vez que el orchestrator procesa un dictamen, se guarda una fila aquí
    para que el coordinador pueda ver métricas reales:
      - tasa de aprobación
      - cuántas regeneraciones se necesitan en promedio
      - qué modelo aprueba más
      - razones de rechazo más comunes
    """

    __tablename__ = "quality_gate_runs"

    id = Column(Integer, primary_key=True, index=True)
    # NOTA: GlosaRecord usa __tablename__ "historial" — no agregamos FK para
    # evitar problemas de orden de creación en tests. Soft-link por id.
    glosa_id = Column(Integer, nullable=True, index=True)
    estado = Column(String(30), nullable=False, index=True)
    # APROBADO | RECHAZADO_PRE | ESCALAR_HUMANO | PENDIENTE
    score_final = Column(Integer, default=0)
    modelo_final = Column(String(40), nullable=True)
    n_intentos = Column(Integer, default=1)
    n_regeneraciones = Column(Integer, default=0)
    razones_rechazo = Column(Text, nullable=True)  # JSON blob
    pre_aprobado = Column(Integer, default=1)
    tiempo_ms = Column(Integer, nullable=True)
    eps = Column(String(120), nullable=True)
    codigo_glosa = Column(String(20), nullable=True, index=True)
    familia_codigo = Column(String(5), nullable=True)
    es_ratificacion = Column(Integer, default=0)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    creado_por = Column(String(200), nullable=True)


class EntidadCredencialRecord(Base):
    """Vault de credenciales de plataformas EPS/entidades (jun-2026).

    Importado del Excel maestro "RADICAR FACTURAS ENTIDADES" (hoja
    CONSOLIDADO). Cada entidad genera hasta 3 registros: uno por bloque
    (RADICACION | CARTERA | DEVOLUCIONES). Los campos sensibles
    (usuario, contraseña, teléfono, correo) se guardan SOLO cifrados
    con Fernet (app/services/credenciales_vault.py, clave en env
    CRED_VAULT_KEY) — nunca en claro. El link de la plataforma y los
    datos de contacto institucionales son públicos dentro del equipo
    y van en claro para que /credenciales/buscar funcione sin clave.
    """

    __tablename__ = "entidad_credenciales"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nit = Column(String(30), index=True, nullable=False)
    empresa = Column(String(300), index=True, nullable=False)
    bloque = Column(String(20), nullable=False)  # RADICACION | CARTERA | DEVOLUCIONES
    link_plataforma = Column(Text, nullable=True)  # no secreto
    usuario_cifrado = Column(Text, nullable=True)  # token Fernet
    password_cifrado = Column(Text, nullable=True)  # token Fernet
    telefono_cifrado = Column(Text, nullable=True)  # token Fernet
    correo_cifrado = Column(Text, nullable=True)  # token Fernet
    nombre_contacto = Column(String(300), nullable=True)
    cargo = Column(String(200), nullable=True)
    manual_radicacion = Column(Text, nullable=True)  # instrucciones, no secreto
    medio_contacto = Column(String(300), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    actualizado_por = Column(String(200), nullable=True)

    __table_args__ = (
        # Clave de upsert del importador: una credencial por entidad y bloque.
        Index("ix_entidad_cred_nit_bloque", "nit", "bloque", unique=True),
    )


class CredencialAccesoLog(Base):
    """Auditoría de acceso al vault de credenciales.

    Cada IMPORTAR (carga del Excel) y cada REVELAR (descifrado de
    usuario/contraseña, con motivo obligatorio) deja fila aquí.
    LISTAR queda reservado para consumidores automáticos futuros
    (worker de radicación) — /buscar no lo registra para no inundar.
    """

    __tablename__ = "credencial_acceso_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    credencial_id = Column(Integer, index=True, nullable=True)  # NULL en IMPORTAR
    usuario_email = Column(String(200), index=True, nullable=False)
    accion = Column(String(20), nullable=False)  # REVELAR | IMPORTAR | LISTAR
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    motivo = Column(Text, nullable=True)


# ─── Paquetes de glosas del ADRES ────────────────────────────────────────────
#
# El ADRES glosa por "paquete": un lote de reclamaciones con su reporte de
# glosas ítem por ítem. Antes eso vivía en un Excel con macro que el equipo
# llenaba a mano; estas tres tablas lo traen al sistema para que el gestor
# escriba un número de factura y tenga todo al frente.


class PaqueteAdresRecord(Base):
    """Un cargue del reporte de glosas del ADRES."""

    __tablename__ = "paquetes_adres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_paquete = Column(String(30), index=True)
    archivo = Column(String(300))
    importado_en = Column(DateTime(timezone=True), server_default=func.now())
    importado_por = Column(String(200))
    total_filas = Column(Integer, default=0)
    total_facturas = Column(Integer, default=0)
    valor_glosado = Column(Float, default=0.0)
    nota = Column(Text)
    # Catálogo de centros de costos del hospital (JSON). Sale de la hoja oculta
    # de la macro; si no mandan macro, se guarda el catálogo que trae el bot.
    catalogo_centros = Column(Text)


class GlosaAdresRecord(Base):
    """Una glosa del ADRES sobre un ítem de una factura.

    Las 16 primeras columnas son el reporte tal cual; las que siguen son el
    trabajo: lo que el bot dedujo (clasificación, centro de costos, sugerencia)
    y lo que decide el gestor (aceptar/objetar/subsanar y su valor).
    """

    __tablename__ = "glosas_adres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paquete_id = Column(Integer, index=True, nullable=False)
    # Clave normalizada (sin el HUS ni los ceros) para buscar por factura.
    factura_clave = Column(String(30), index=True, nullable=False)
    factura = Column(String(50), nullable=False)
    radicacion = Column(String(50))
    cod_habilitacion = Column(String(30))
    doc_victima = Column(String(50))
    consecutivo = Column(String(20))
    tipo_elemento = Column(String(60))
    codigo = Column(String(60), index=True)
    descripcion = Column(Text)
    causal_codigo = Column(String(10), index=True)
    causal_texto = Column(Text)
    anotacion = Column(Text)
    cant_reclamada = Column(Float, default=0.0)
    valor_reclamado = Column(Float, default=0.0)
    cant_aprobada = Column(Float, default=0.0)
    valor_aprobado = Column(Float, default=0.0)
    valor_glosado = Column(Float, default=0.0)
    # Lo que dedujo el bot
    clasificacion = Column(String(60), index=True)
    centro_costos = Column(String(80))
    # Quién puso el centro de costos a mano (vacío = lo propuso el bot). Sirve
    # para no volver a pisarlo cuando se recarga el paquete.
    centro_costos_por = Column(String(200))
    gestor = Column(String(120), index=True)
    medico = Column(String(120))
    sugerencia = Column(String(20))
    confianza = Column(String(20))
    motivo = Column(Text)
    estado_detallado = Column(String(30))
    # Renglón de una GLOSA TOTAL: el ADRES glosó la reclamación entera por el
    # FURIPS y el reporte lista los ítems por debajo, pero sin causal propia.
    # No se responden uno por uno, así que la pantalla no los muestra.
    glosa_total = Column(Boolean, default=False, index=True)
    # El reporte del ADRES abre UNA FILA POR CADA CAUSAL del mismo ítem. Las
    # filas se conservan todas (el gestor decide causal por causal), pero solo
    # una de cada ítem cuenta para la plata: si no, la glosa sale al doble o al
    # triple. En el paquete 31078 la suma cruda daba $585M contra $297M reales.
    cuenta_valor = Column(Boolean, default=True, index=True)
    # Causales que trabajan dos áreas (hoy la 4506): los gestores por
    # FACTURACION y las médicas por PERTINENCIA. Quién la toma depende de qué
    # se glosó, así que la reparte un SUPER ADMIN — el bot solo sugiere.
    requiere_asignacion = Column(Boolean, default=False, index=True)
    area_sugerida = Column(String(60))
    motivo_area = Column(Text)
    area_asignada_por = Column(String(200))
    area_asignada_en = Column(DateTime(timezone=True))
    # Lo que decide el gestor
    decision = Column(String(20), index=True)  # SE ACEPTA | SE OBJETA | SE SUBSANA
    observacion_tecnico = Column(Text)
    cantidad_aceptada = Column(String(20))
    valor_aceptado = Column(Float, default=0.0)
    decidido_por = Column(String(200))
    decidido_en = Column(DateTime(timezone=True))

    __table_args__ = (Index("ix_glosas_adres_paq_factura", "paquete_id", "factura_clave"),)


class FacturaAdresRecord(Base):
    """Estado de auditoría de una factura del paquete.

    Sirve para la lista que ve el gestor al abrir la pantalla («qué me falta»)
    y para poder **cerrar** una factura cuando termina y **reabrirla** si
    después hay que corregir algo.
    """

    __tablename__ = "facturas_adres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paquete_id = Column(Integer, index=True, nullable=False)
    factura_clave = Column(String(30), index=True, nullable=False)
    factura = Column(String(50), nullable=False)
    radicacion = Column(String(50))
    doc_victima = Column(String(50))
    gestor = Column(String(120), index=True)
    medico = Column(String(120))
    # PENDIENTE | EN PROCESO | CERRADA
    estado = Column(String(20), default="PENDIENTE", index=True)
    # Lo que el ADRES dice que tiene glosado esta factura, del archivo de
    # facturas del paquete. Es la única cifra oficial: el reporte por ítem
    # repite renglones. Vacío = no se cargó ese archivo.
    valor_glosado_oficial = Column(Float)
    cerrada_por = Column(String(200))
    cerrada_en = Column(DateTime(timezone=True))
    reabierta_por = Column(String(200))
    reabierta_en = Column(DateTime(timezone=True))
    nota = Column(Text)

    __table_args__ = (Index("ix_facturas_adres_paq_clave", "paquete_id", "factura_clave"),)


class ItemDetalladoAdresRecord(Base):
    """Un renglón del detallado de la factura, ya cruzado con el reporte.

    Sale de la bitácora del ajustador: dice de cada servicio si el ADRES lo
    pagó, si sigue glosado o si quedó a medias.
    """

    __tablename__ = "items_detallado_adres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paquete_id = Column(Integer, index=True, nullable=False)
    factura_clave = Column(String(30), index=True, nullable=False)
    factura = Column(String(50))
    grupo = Column(String(120))
    codigo = Column(String(60))
    nombre = Column(Text)
    cantidad = Column(Float, default=0.0)
    valor_facturado = Column(Float, default=0.0)
    valor_reclamado = Column(Float, default=0.0)
    valor_aprobado = Column(Float, default=0.0)
    valor_glosado = Column(Float, default=0.0)
    accion = Column(String(30), index=True)  # QUITADO | AJUSTADO | CONSERVADO | SIN_CRUCE | …
    cantidad_nueva = Column(Float, default=0.0)
    valor_nuevo = Column(Float, default=0.0)
    cruce_por = Column(String(30))
    tipo_renglon = Column(String(20))  # ITEM | DESGLOSE
    causales = Column(Text)
    observacion = Column(Text)

    __table_args__ = (Index("ix_items_det_adres_paq_factura", "paquete_id", "factura_clave"),)


# ============================================================
# PRE-AUDITORÍA SINAC — recepción de oficios de Facturación,
# auditoría de soportes y oficios de devolución (DEV-PRE-AUD).
# ============================================================


class OficioRecepcionRecord(Base):
    """Oficio radicado por Facturación que entrega facturas a pre-auditoría.

    El plazo para auditar es de 3 días hábiles, contados a partir del día
    siguiente al recibo del oficio (semáforo verde/amarillo/rojo/vencido).
    """

    __tablename__ = "preaud_oficios_recepcion"

    id = Column(Integer, primary_key=True, index=True)
    numero_radicado = Column(String(60), nullable=False)  # ej. FHUS-AS-I00768-26
    fecha_recibido = Column(DateTime(timezone=True), nullable=False, index=True)  # con hora
    observaciones = Column(Text, nullable=True)
    archivo_dgh = Column(String(300), nullable=True)  # Excel del consecutivo DGH importado
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    creado_por = Column(String(200), nullable=True)

    __table_args__ = (Index("ix_preaud_oficio_radicado", "numero_radicado", unique=True),)


# ---------- FUENTES: las alimenta el auditor subiendo Excel (upsert) ----------


class RadicacionCuentaRecord(Base):
    """FUENTE 1 — RADICACIÓN DE CUENTAS (reporte de DGH).

    Dice, por factura, en qué ENVÍO (consecutivo de radicación) va, cuándo se
    recibió el documento, el valor, el NIT y la entidad. El auditor la alimenta
    subiendo el Excel; al re-subir se ACTUALIZA fila por fila (upsert por
    factura) y nunca se duplica: la última carga es la verdad vigente. El
    consolidado toma de aquí F_RECIBIDO, F_FACTURA, VALOR, NIT y ENTIDAD.
    """

    __tablename__ = "preaud_fuente_radicacion"

    id = Column(Integer, primary_key=True, index=True)
    factura = Column(String(30), nullable=False)  # identidad de la fuente
    envio = Column(String(30), nullable=False, index=True)
    f_recibido = Column(DateTime(timezone=True), nullable=True)  # Radicacion.FechaDocumento
    f_factura = Column(DateTime(timezone=True), nullable=True)  # CxC.Fecha
    valor = Column(Float, default=0.0, nullable=False)  # CxC.Valor
    nit = Column(String(30), nullable=True, index=True)  # Tercero.Documento
    entidad = Column(String(300), nullable=True)  # Tercero.NombreCompletoNA
    estado_radicacion = Column(String(40), nullable=True)  # Radicado_Entidad, etc.
    fuente_archivo = Column(String(300), nullable=True)
    importado_por = Column(String(200), nullable=True)
    importado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # DEDUP / upsert: una sola fila vigente por factura.
        Index("ix_preaud_rad_factura", "factura", unique=True),
        # Cruce: traer todas las facturas de un envío.
        Index("ix_preaud_rad_envio", "envio"),
    )


class DgReportRecord(Base):
    """FUENTE 2 — DGREPORT (facturas con correo de factura electrónica).

    Dice, por factura, si salió el correo de F.E. Se alimenta subiendo el
    DGReport. Upsert por factura. El consolidado marca CORREO F.E. = SI si la
    factura está aquí, NO si no está.
    """

    __tablename__ = "preaud_fuente_dgreport"

    id = Column(Integer, primary_key=True, index=True)
    factura = Column(String(30), nullable=False)
    correo_fe = Column(String(2), default="SI", nullable=False)  # SI | NO
    fecha_correo = Column(DateTime(timezone=True), nullable=True)
    numero_fe = Column(String(80), nullable=True)  # CUFE / nº de F.E. si viene
    fuente_archivo = Column(String(300), nullable=True)
    importado_por = Column(String(200), nullable=True)
    importado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_preaud_dgreport_factura", "factura", unique=True),)


class EnvioCargadoRecord(Base):
    """Ledger de cada ENVÍO ya volcado al consolidado (dedup del punto 3).

    Al escribir un envío se inserta aquí; si ya existe PARA ESE OFICIO
    (único por envío + oficio), se responde "El envío ya fue cargado" y NO
    se recrean facturas. El mismo envío SÍ puede cargarse en oficios
    posteriores — hasta MAX_OFICIOS_POR_ENVIO en total — porque facturación
    reenvía las subsanaciones con el mismo número de envío (caso real
    30-07-2026); la recarga solo reingresa las facturas devueltas.
    """

    __tablename__ = "preaud_envios_cargados"

    id = Column(Integer, primary_key=True, index=True)
    envio = Column(String(30), nullable=False)
    oficio_id = Column(
        Integer, ForeignKey("preaud_oficios_recepcion.id"), index=True, nullable=True
    )
    total_facturas = Column(Integer, default=0, nullable=False)
    nuevas = Column(Integer, default=0, nullable=False)
    reingresos = Column(Integer, default=0, nullable=False)
    cargado_por = Column(String(200), nullable=True)
    cargado_en = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_preaud_envio_cargado", "envio", "oficio_id", unique=True),)


# ---------- CONSOLIDADO: la factura canónica (una sola fila por factura) ------


class FacturaPreauditoriaRecord(Base):
    """La FACTURA como entidad CANÓNICA: UNA sola fila por número de factura,
    aunque reingrese varias veces (subsanaciones).

    Guarda solo el ESTADO del proceso de pre-auditoría. Los datos descriptivos
    (F_FACTURA, VALOR, NIT, ENTIDAD, CORREO F.E.) NO se copian aquí: se resuelven
    por JOIN a las fuentes al leer, de modo que corregir un Excel se refleja solo
    (auto-sync, punto 5). F_RECIBIDO se toma del oficio actual.

    num_devoluciones / num_subsanacion son un caché del historial de eventos,
    mantenido en la misma transacción del evento.
    """

    __tablename__ = "preaud_facturas"

    id = Column(Integer, primary_key=True, index=True)
    factura = Column(String(30), nullable=False)  # identidad canónica

    # Posición actual dentro del proceso (cambian al reingresar)
    envio_actual = Column(String(30), index=True, nullable=True)
    oficio_actual_id = Column(
        Integer, ForeignKey("preaud_oficios_recepcion.id"), index=True, nullable=True
    )
    oficio_fhus = Column(String(60), index=True, nullable=True)  # radicado FHUS actual
    f_recibido = Column(DateTime(timezone=True), nullable=True)  # del oficio actual

    # Estado del proceso
    estado = Column(String(25), default="NUEVA", nullable=False, index=True)
    # NUEVA | RADICADA | DEVUELTA_PEND_SUBSANACION | EN_SUBSANACION | SUBSANADA
    # | NUEVAMENTE_DEVUELTA | BLOQUEADA_LIMITE
    resultado_actual = Column(
        String(15), default="PENDIENTE", index=True
    )  # PENDIENTE | RADICAR | DEVUELTA
    ronda_actual = Column(Integer, default=1, nullable=False)  # 1=primera; 2+=subsanación
    num_subsanacion = Column(Integer, default=0, nullable=False)  # 0,1,2,3 = ronda_actual-1
    num_devoluciones = Column(Integer, default=0, nullable=False)  # veces devuelta (tope 3)
    pendiente_subsanacion = Column(Integer, default=0, nullable=False)  # 0/1

    # Última auditoría
    auditor = Column(String(120), index=True, nullable=True)
    fecha_auditoria = Column(DateTime(timezone=True), nullable=True)
    motivo_ultima_devolucion = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    oficio_devolucion_id = Column(
        Integer, ForeignKey("preaud_oficios_devolucion.id"), index=True, nullable=True
    )

    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    creado_por = Column(String(200), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # DEDUP canónico (punto 4): una sola factura por número.
        Index("ix_preaud_fact_canonica", "factura", unique=True),
        Index("ix_preaud_fact_envio", "envio_actual"),
        Index("ix_preaud_fact_estado_auditor", "estado", "auditor"),
    )


class FacturaEventoRecord(Base):
    """Historial INMUTABLE de la vida de una factura en pre-auditoría (punto 5).

    Una fila por transición; nunca se actualiza, solo se inserta. Conserva un
    SNAPSHOT de los valores de la fuente EN EL MOMENTO del evento (fidelidad
    legal: el oficio de devolución muestra el valor de ese día).
    """

    __tablename__ = "preaud_factura_eventos"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(
        Integer,
        ForeignKey("preaud_facturas.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    factura = Column(String(30), index=True, nullable=False)  # denormalizado

    tipo_evento = Column(String(30), index=True, nullable=False)
    # ESCRITA | RADICADA | DEVUELTA | REINGRESO | SUBSANADA
    # | NUEVAMENTE_DEVUELTA | REVERTIDA
    subsanacion_num = Column(Integer, default=0, nullable=False)  # ronda del evento
    ronda = Column(Integer, default=1, nullable=False)
    estado_resultante = Column(String(25), nullable=True)

    envio = Column(String(30), nullable=True)
    oficio_id = Column(
        Integer, ForeignKey("preaud_oficios_recepcion.id"), index=True, nullable=True
    )
    oficio_fhus = Column(String(60), nullable=True)
    f_recibido = Column(DateTime(timezone=True), nullable=True)
    resultado = Column(String(15), nullable=True)
    auditor = Column(String(120), index=True, nullable=True)
    motivo = Column(Text, nullable=True)
    # Lo que escribió el auditor al decidir. A diferencia del motivo (que solo
    # aplica a las devoluciones), la observación se guarda también cuando la
    # factura se radica, y queda visible en el historial.
    observaciones = Column(Text, nullable=True)
    oficio_devolucion_id = Column(
        Integer, ForeignKey("preaud_oficios_devolucion.id"), index=True, nullable=True
    )

    # Snapshot de la fuente al momento del evento
    valor_snapshot = Column(Float, default=0.0)
    nit_snapshot = Column(String(30), nullable=True)
    entidad_snapshot = Column(String(300), nullable=True)
    correo_fe_snapshot = Column(String(2), nullable=True)
    fecha_factura_snapshot = Column(DateTime(timezone=True), nullable=True)

    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    creado_por = Column(String(200), nullable=True)

    __table_args__ = (
        Index("ix_preaud_evt_factura_ts", "factura_id", "creado_en"),
        Index("ix_preaud_evt_tipo", "tipo_evento"),
        Index("ix_preaud_evt_oficio_dev", "oficio_devolucion_id"),
    )


class OficioDevolucionRecord(Base):
    """Oficio de devolución con consecutivo SINAC (DEV-PRE-AUD-####-AAAA).

    Agrupa las facturas devueltas de un oficio de recepción; el PDF se
    genera con logo y bloque de firmas para entregar a Facturación.
    """

    __tablename__ = "preaud_oficios_devolucion"

    id = Column(Integer, primary_key=True, index=True)
    consecutivo = Column(String(40), nullable=False)  # DEV-PRE-AUD-0007-2026
    anio = Column(Integer, index=True, nullable=False)
    numero = Column(Integer, nullable=False)  # parte numérica del consecutivo
    oficio_recepcion_id = Column(
        Integer, ForeignKey("preaud_oficios_recepcion.id"), index=True, nullable=True
    )
    fecha_generado = Column(DateTime(timezone=True), server_default=func.now())
    generado_por = Column(String(200), nullable=True)
    total_facturas = Column(Integer, default=0, nullable=False)
    total_valor = Column(Float, default=0.0, nullable=False)

    __table_args__ = (
        Index("ix_preaud_dev_consecutivo", "consecutivo", unique=True),
        Index("ix_preaud_dev_anio_numero", "anio", "numero", unique=True),
    )


# ─── Lotes de portal (Fase 1 de la app unificada, jul-2026) ──────────────────
# Un "lote" es un Excel consolidado de glosas de un pagador (COOSALUD por
# ahora) que el auditor sube a la app. La app lo parsea, crea una fila por
# factura y encola una tarea que el agente local (tools/agente_lotes.py,
# corriendo en el PC del hospital con acceso a los portales) reclama,
# ejecuta con el bot Playwright y reporta de vuelta factura por factura.

LOTE_ESTADO_EN_COLA = "EN_COLA"
LOTE_ESTADO_EN_PROCESO = "EN_PROCESO"
LOTE_ESTADO_COMPLETADO = "COMPLETADO"
LOTE_ESTADO_COMPLETADO_CON_PENDIENTES = "COMPLETADO_CON_PENDIENTES"
LOTE_ESTADO_ERROR = "ERROR"

TAREA_ESTADO_PENDIENTE = "PENDIENTE"
TAREA_ESTADO_RECLAMADA = "RECLAMADA"
TAREA_ESTADO_COMPLETADA = "COMPLETADA"
TAREA_ESTADO_ERROR = "ERROR"

FACTURA_LOTE_ESTADO_PENDIENTE = "PENDIENTE"
# Estados terminales de éxito que reporta el bot COOSALUD en su CSV
# (columna "estado" de --reporte). Cualquier otro valor cuenta como
# pendiente/fallo al calcular el estado final del lote.
FACTURA_LOTE_ESTADOS_EXITO = {
    "OK",
    "OK_CALIDAD_ABIERTA",
    "OK_SIN_DIALOGO",
    "YA_PROCESADA",
    "SOLO_CALIDAD",
    "TERMINADA_SIN_CARTEL",
}


class LoteRecord(Base):
    """Un Excel consolidado subido para respuesta masiva en un portal."""

    __tablename__ = "lotes"

    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    creado_por = Column(String(200), nullable=False)
    pagador = Column(String(50), nullable=False, index=True)  # COOSALUD, SIMED, ...
    nombre_archivo = Column(String(300), nullable=False)
    hoja = Column(String(100), default="BASE")
    incluir_calidad = Column(Integer, default=0)
    estado = Column(String(50), default=LOTE_ESTADO_EN_COLA, index=True)
    total_facturas = Column(Integer, default=0)
    total_glosas = Column(Integer, default=0)
    total_calidad = Column(Integer, default=0)  # glosas CALIDAD excluidas
    # El Excel original tal como se subió: el agente local lo descarga de
    # aquí para correr el bot — el PC del hospital no comparte disco con
    # el servidor de la app.
    excel_archivo = Column(LargeBinary, nullable=False)
    resumen = Column(Text, nullable=True)  # JSON: conteo de estados al cierre
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FacturaLoteRecord(Base):
    """Estado por factura dentro de un lote (el semáforo de la UI)."""

    __tablename__ = "facturas_lote"

    id = Column(Integer, primary_key=True, index=True)
    lote_id = Column(
        Integer, ForeignKey("lotes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    factura = Column(String(50), nullable=False, index=True)
    grupos = Column(Integer, default=0)  # grupos de respuesta (cod+obs)
    glosas = Column(Integer, default=0)  # ids de glosa a responder
    calidad = Column(Integer, default=0)  # glosas CALIDAD excluidas
    requiere_soporte = Column(Integer, default=0)
    estado = Column(String(50), default=FACTURA_LOTE_ESTADO_PENDIENTE, index=True)
    detalle = Column(Text, nullable=True)  # motivo textual del bot (RECHAZADA: ...)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_facturas_lote_lote_factura", "lote_id", "factura", unique=True),)


class TareaLoteRecord(Base):
    """Cola de trabajos para el agente local (una tarea por corrida de bot)."""

    __tablename__ = "tareas_lote"

    id = Column(Integer, primary_key=True, index=True)
    lote_id = Column(
        Integer, ForeignKey("lotes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tipo = Column(String(50), default="RESPONDER_COOSALUD", nullable=False)
    estado = Column(String(50), default=TAREA_ESTADO_PENDIENTE, index=True)
    agente = Column(String(200), nullable=True)  # hostname del PC que la reclamó
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    reclamada_en = Column(DateTime(timezone=True), nullable=True)
    terminada_en = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    resultado = Column(Text, nullable=True)  # JSON: resumen que reportó el agente


class TrabajoBotRecord(Base):
    """Cola universal de trabajos para los bots del PC del HUS.

    La plataforma encola (quién pidió qué bot con qué parámetros); el
    agente del PC reclama, corre y reporta. Es la generalización de
    TareaLoteRecord para TODOS los bots, no solo los de lotes.
    """

    __tablename__ = "trabajos_bot"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String(80), index=True, nullable=False)
    estado = Column(
        String(30), default="PENDIENTE", index=True
    )  # PENDIENTE/RECLAMADO/TERMINADO/ERROR
    parametros = Column(Text)  # JSON con lo que el auditor escribió
    pedido_por = Column(String(200))
    equipo = Column(String(200))  # hostname del PC que lo reclamó
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    reclamado_en = Column(DateTime(timezone=True))
    terminado_en = Column(DateTime(timezone=True))
    error = Column(Text)
    registro = Column(Text)  # salida/resumen que reportó el agente
    progreso = Column(Text)  # último avance reportado ("factura 12 de 40…")
    cancelado_por = Column(String(200))


class AutoPilotBitacoraRecord(Base):
    """Bitácora INMUTABLE del Auto-Pilot (V2, Pilar 2, 03-09-2026).

    Cada decisión de la máquina —y cada liberación humana— es una fila NUEVA.
    Aquí no se edita ni se borra nada: el servicio solo inserta, y así queda
    auditable quién decidió qué, con cuánta confianza y mirando qué soportes.
    """

    __tablename__ = "auto_pilot_bitacora"

    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    glosa_id = Column(Integer, index=True)
    # CANDIDATA / RECHAZADA / LIBERADA_POR_HUMANO
    decision = Column(String(40), index=True)
    # La regla de negocio que produjo la decisión, en palabras.
    regla_aplicada = Column(Text)
    # Confianza matemática del evaluador (0-1). Nula si no se llegó a calcular.
    confianza = Column(Float)
    riesgo = Column(String(20))
    # JSON con los identificadores de lo que la evaluación tuvo a la vista.
    soportes_analizados = Column(Text)
    # "auto-pilot" para la máquina; el correo del gestor cuando libera.
    actor = Column(String(120), index=True)
