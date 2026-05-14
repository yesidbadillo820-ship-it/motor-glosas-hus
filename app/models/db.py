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
    # Ronda 50 (Bug #4): código interno del DGH/Syscafe (ej. "423", "223"
    # cuando Excel del DGH no trae el canónico Res. 2284/2023). Se guarda
    # al importar si viene y se usa al exportar en el campo
    # 'ListadoConceptos.ConceptoObjecion.Codigo' del formato DGH.
    codigo_syscafe = Column(String(20), index=True)
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
    # Ruta absoluta al PDF del contrato vigente (en /data/contratos/...).
    # Se sobreescribe cuando se sube uno nuevo — solo guardamos el vigente.
    pdf_path = Column(String(500), nullable=True)
    pdf_subido_en = Column(DateTime(timezone=True), nullable=True)


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
    eps = Column(String, ForeignKey("contratos.eps", ondelete="CASCADE"), index=True, nullable=False)
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
    # Telegram chat_id para notificaciones push. El gestor escribe
    # /start al bot @MotorGlosasHUS_bot (o el nombre que se elija) y
    # el bot guarda aquí su chat_id contra el email del usuario. Si
    # está vacío, el gestor no recibe alertas push (no bloquea nada).
    telegram_chat_id = Column(String(40), nullable=True, index=True)
    # Preferencias de notificación Telegram (bitmask serializado simple):
    #   "rojas,negras,resumen_diario,vence_hoy"  → todo activado
    #   ""  → todo desactivado
    # Default: todo activado cuando vinculan el chat.
    telegram_preferencias = Column(String(200), nullable=True)


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
    # Ronda 45: código interno IPS (ej. '39147B-18' del HUS) para que cuando
    # la EPS glose con el código viejo podamos homologarlo al CUPS oficial
    # (Res. 2641/2025). El parser Excel llena este campo cuando hay columna
    # 'CODIGO IPS'/'CODIGO PROPIO'.
    codigo_ips = Column(String(30), index=True)
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
    proveedor = Column(String(20), nullable=False)        # 'anthropic' | 'groq'
    modelo = Column(String(80), nullable=False)           # 'claude-sonnet-4-6' | 'llama-3.3-70b'
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

    __table_args__ = (
        Index("ix_aicalls_proveedor_creado", "proveedor", "creado_en"),
    )


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


class NoticiaSaludRecord(Base):
    """Noticias del sector salud Colombia traídas vía RSS de fuentes
    oficiales y especializadas (ConsultorSalud, MinSalud, ACHC, etc.).

    Se muestran en el dashboard del auditor al loguearse — directiva
    Yesid mayo 2026: "que cuando el auditor entre salga como un script
    con las noticias mas importantes".

    Fuente -> URL del feed/sitio. Hash sirve para dedupe entre fetches
    (mismo titulo+url pueden venir múltiples veces si el feed se
    actualiza).
    """
    __tablename__ = "noticias_salud"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(500), nullable=False)
    resumen = Column(Text, nullable=True)
    url = Column(String(800), nullable=True)
    fuente = Column(String(80), index=True, nullable=False)
    fecha_publicacion = Column(DateTime(timezone=True), index=True, nullable=True)
    indexada_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    hash_unico = Column(String(64), index=True, nullable=False)
    activa = Column(Integer, default=1, nullable=False, index=True)
    # Categorías típicas: NORMATIVA | NOTICIA | OPINION | ALERTA
    categoria = Column(String(40), default="NOTICIA", index=True)


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

    __table_args__ = (
        Index("ix_nota_privada_unico", "glosa_id", "autor_email", unique=True),
    )


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

    __table_args__ = (
        Index("ix_preset_usuario", "usuario_email", "creado_en"),
    )


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
