"""
RecepcionService
================

Procesa el archivo Excel enviado por el equipo de recepción de glosas.

Columnas esperadas (en cualquier orden, por nombre de encabezado):
    GESTOR
    FECHA DE ENTREGA
    FECHA RADICACION          (cuando se radicó la factura a la EPS)
    FECHA DOCUMENTO DGH       (cuando la EPS emitió la glosa)
    FECHA RECEPCION           (cuando HUS recibió la glosa)
    ENTIDAD                   (nombre/código EPS)
    FACTURA
    CONSECUTIVO DGH           (identificador único de la glosa)
    VALOR GLOSA
    VENCE                     (fecha límite para responder)
    DEVOLUCION S/N
    DIAS RADICACION VS RECEPCION
    RADICADO                  (texto libre; si contiene "RATIFICADA", se aplica automáticamente el texto de respuesta para ratificadas)

Para cada fila:
- Si la glosa es RATIFICADA -> estado=RATIFICADA + dictamen con TEXTO_RATIFICADA.
- Si fue glosada extemporáneamente (>20 días hábiles entre radicación y DGH) ->
  estado=EXTEMPORANEA + dictamen con el texto estándar.
- Se calcula el semáforo por días hábiles restantes hasta VENCE.
- Upsert por CONSECUTIVO DGH (o por factura si no viene consecutivo).
"""
from __future__ import annotations

import re
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Optional

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.models.db import GlosaRecord, ConceptoGlosaRecord
from app.services.glosa_service import (
    FERIADOS_CO,
    DIAS_HABILES_LIMITE_EXTEMPORANEA,
    TEXTO_RATIFICADA,
    generar_texto_extemporanea,
)


# ─── Parámetros de semáforo (días hábiles restantes) ─────────────────────────
SEMAFORO_VERDE_MIN = 11   # >10 días
SEMAFORO_AMARILLO_MIN = 5  # 5-10 días
# <5 días → ROJO; <=0 → NEGRO


# ─── Mapeo de columnas del Excel -> campo interno ────────────────────────────
# Soporta dos hojas de cabecera:
#   • INICIAL:    GESTOR | FECHA DE ENTREGA | FECHA RADICACION | FECHA DOCUMENTO
#                  DGH | FECHA RECEPCION | ENTIDAD | FACTURA | ...
#   • RATIFICADA: RESPONSABLE | FECHA ENTREGA | FECHA DE DOCUMENTO (DGH) |
#                  FECHA NOTIFICACION OBJECION | EMPRESA | NUMERO DE FACTURA |
#                  FECHA VENCIMIENTO | OBSERVACION RECEPCION | ...
COLUMN_ALIASES: dict[str, list[str]] = {
    "gestor": ["gestor", "responsable"],
    "fecha_entrega": ["fecha de entrega", "fecha entrega"],
    "fecha_radicacion": ["fecha radicacion", "fecha de radicacion"],
    "fecha_documento_dgh": [
        "fecha documento dgh", "fecha dgh",
        "fecha de documento (dgh)", "fecha de documento dgh",
        "fecha documento (dgh)",
    ],
    "fecha_recepcion": [
        "fecha recepcion", "fecha de recepcion",
        "fecha notificacion objecion", "fecha de notificacion objecion",
    ],
    "entidad": ["entidad", "eps", "empresa"],
    "factura": ["factura", "numero de factura", "numero factura"],
    "consecutivo_dgh": ["consecutivo dgh", "consecutivo"],
    "valor_glosa": ["valor glosa", "valor"],
    "vence": ["vence", "fecha vence", "fecha vencimiento", "fecha de vencimiento"],
    "devolucion": ["devolucion s/n", "devolucion", "devolucion s", "s/n"],
    "dias_rad_rec": ["dias radicacion vs recepcion", "dias radicacion recepcion"],
    "radicado": ["radicado"],
    "referencia": ["referencia"],
    "observacion_tecnico": [
        "observacion tecnico", "observacion", "obs tecnico",
        "observacion recepcion", "observacion de recepcion",
    ],
    "tecnico_recepcion": [
        "tecnico que recepciono", "tecnico recepcion",
        "tecnico recepciono", "tecnico que recepciona",
    ],
    "tipo_glosa": ["tipo glosa", "tipo de glosa"],
    "profesional_medico": ["profesional(medico)", "profesional (medico)", "profesional medico", "profesional", "medico auditor"],
}

# ─── Columnas de las hojas DETALLE (I / R) del DGH ───────────────────────────
# El DGH exporta los conceptos por factura en hojas con nombres literales
# "I" (Glosa_Inicial) y "R" (Glosa_Ratificada). Estas columnas son las que
# usa el parser de conceptos (procesar_hoja_conceptos).
CONCEPTO_COLS: dict[str, list[str]] = {
    "estado_dgh": ["estadocxcobjecion"],
    "tipo_tramite": ["tipoobjeciontramite"],
    "factura": ["facturacartera.factura"],
    "consecutivo": ["consecutivo"],
    "valor_factura": ["facturacartera.valor"],
    "saldo_factura": ["facturacartera.saldo"],
    "fecha_documento": ["fechadocumento"],
    "fecha_objecion": ["fechaobjecion"],
    "eps_plan": ["facturacartera.planbeneficio.codigonombreplanbeneficios"],
    "eps_codigo_entidad": ["facturacartera.planbeneficio.contrato.entidad.codigoentidad"],
    "eps_nombre": ["facturacartera.planbeneficio.contrato.entidad.nombreentidad"],
    "tercero_nit": ["facturacartera.tercero.documento"],
    "concepto_codigo": ["listadoconceptos.conceptoobjecion.codigo"],
    "concepto_oid": ["listadoconceptos.oid"],
    "concepto_nombre": ["listadoconceptos.conceptoobjecion.nombre"],
    "cups_codigo": ["listadoconceptos.servicioproductofactura.codigo"],
    "cups_descripcion": ["listadoconceptos.servicioproductofactura.descripcion"],
    "concepto_valor": ["listadoconceptos.valorobjecion"],
    "centro_costo": ["listadoconceptos.servicioproductofactura.centrocosto.codigonombrecentro"],
    "concepto_observacion": ["listadoconceptos.observaciones"],
}


def _normalizar(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def _fix_mojibake(texto: str) -> str:
    """Arregla texto UTF-8 leído como Latin-1 (mojibake) y limpia artefactos.

    - Mojibake: "OBJECIÃ³N" → "OBJECIÓN".
    - Artefactos Excel: "_x000D_" (Windows CRLF escapado por openpyxl) → " ".
    - Multiples espacios/saltos: colapsados a un solo espacio.
    """
    if not texto or not isinstance(texto, str):
        return texto
    # 1. Fix mojibake latin1/utf8 si aplica
    if "Ã" in texto or "Â" in texto:
        try:
            texto = texto.encode("latin1", errors="strict").decode("utf8", errors="strict")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    # 2. Limpiar artefactos comunes de export desde Excel
    # openpyxl a veces deja literal "_x000D_" donde había \r (retorno de carro).
    texto = texto.replace("_x000D_", " ").replace("_x000A_", " ")
    # Quitar saltos de línea intermedios y espacios redundantes
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _split_entidad(entidad: str) -> tuple[str, str]:
    """Separa 'U220181 - FAMISANAR EPS SUBSIDIADO' en ('U220181', 'FAMISANAR EPS SUBSIDIADO').

    Si no hay guion, el código queda vacío y todo va al nombre.
    """
    if not entidad:
        return "", ""
    m = re.match(r"^\s*([A-Z]\d{5,8})\s*[-–—]\s*(.+)$", entidad.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", entidad.strip()


def _mapear_cabeceras(fila_encabezado: tuple, mapa: dict[str, list[str]] | None = None) -> dict[str, int]:
    """Devuelve {nombre_interno: índice_columna}.

    Por defecto usa COLUMN_ALIASES (hojas INICIAL/RATIFICADA). Pasa
    ``mapa=CONCEPTO_COLS`` para parsear hojas I/R de detalle.
    """
    mapa = mapa if mapa is not None else COLUMN_ALIASES
    indices: dict[str, int] = {}
    for idx, celda in enumerate(fila_encabezado):
        valor = _normalizar(str(celda or ""))
        if not valor:
            continue
        for nombre_interno, aliases in mapa.items():
            if valor in aliases and nombre_interno not in indices:
                indices[nombre_interno] = idx
                break
    return indices


def _buscar_fila_encabezado(
    ws, max_filas: int, mapa: dict[str, list[str]], min_aciertos: int = 3
) -> tuple[int, dict[str, int]]:
    """Busca la primera fila que parezca encabezado.

    Escanea hasta ``max_filas`` filas y devuelve (num_fila_1based, indices).
    Si ninguna fila tiene al menos ``min_aciertos`` columnas mapeadas,
    devuelve (0, {}).
    """
    for num_fila, fila in enumerate(ws.iter_rows(values_only=True), start=1):
        if num_fila > max_filas:
            break
        if all(c is None or str(c).strip() == "" for c in fila):
            continue
        indices = _mapear_cabeceras(fila, mapa)
        if len(indices) >= min_aciertos:
            return num_fila, indices
    return 0, {}


def _a_fecha(valor) -> Optional[datetime]:
    """Acepta datetime, date, o string con varios formatos comunes."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    s = str(valor).strip()
    for fmt in (
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _a_float(valor) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d]", "", str(valor))
    return float(s) if s else 0.0


def _dias_habiles(desde: datetime, hasta: datetime) -> int:
    """Cuenta días hábiles (excluye sábados, domingos y festivos Colombia)."""
    if desde >= hasta:
        return 0
    dias = 0
    curr = desde
    while curr < hasta:
        curr += timedelta(days=1)
        if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in FERIADOS_CO:
            dias += 1
    return dias


def _semaforo(dias_restantes: int) -> str:
    if dias_restantes <= 0:
        return "NEGRO"
    if dias_restantes < SEMAFORO_AMARILLO_MIN:
        return "ROJO"
    if dias_restantes < SEMAFORO_VERDE_MIN:
        return "AMARILLO"
    return "VERDE"


def _es_ratificada(*valores: str) -> bool:
    """True si CUALQUIERA de los valores contiene la palabra RATIFICADA."""
    for v in valores:
        if v and "RATIFICADA" in str(v).upper():
            return True
    return False


def _no_aplicar_extemporaneidad(observacion: str) -> bool:
    """True si la observación del técnico pide no aplicar extemporaneidad."""
    if not observacion:
        return False
    texto = str(observacion).upper()
    return (
        "NO APLICAR EXTEMPORANEIDAD" in texto
        or "NO APLICA EXTEMPORANEIDAD" in texto
        or "NO APLICAR EXTEMPORANEA" in texto
    )


def _dictamen_ratificada(eps: str, factura: str, radicado_info: str) -> str:
    return f"""
    <div style="background:#ede9fe;border-left:4px solid #7c3aed;padding:20px;margin:15px 0;border-radius:8px;">
        <h4 style="color:#5b21b6;margin:0 0 10px 0;">RESPUESTA A GLOSA RATIFICADA</h4>
        <p style="font-size:12px;color:#6d28d9;margin:0 0 10px 0;">
            <b>EPS:</b> {eps} | <b>Factura:</b> {factura} | <b>Observación recepción:</b> {radicado_info}
        </p>
        <p style="font-size:13px;line-height:1.8;color:#4c1d95;white-space:pre-wrap;">{TEXTO_RATIFICADA}</p>
    </div>
    """.strip()


def _dictamen_extemporanea(eps: str, factura: str, dias_transcurridos: int) -> str:
    texto = generar_texto_extemporanea(dias_transcurridos)
    return f"""
    <div style="background:#fee2e2;border-left:4px solid #dc2626;padding:20px;margin:15px 0;border-radius:8px;">
        <h4 style="color:#991b1b;margin:0 0 10px 0;">GLOSA EXTEMPORÁNEA ({dias_transcurridos} DÍAS HÁBILES)</h4>
        <p style="font-size:12px;color:#b91c1c;margin:0 0 10px 0;">
            <b>EPS:</b> {eps} | <b>Factura:</b> {factura}
        </p>
        <p style="font-size:13px;line-height:1.8;color:#7f1d1d;white-space:pre-wrap;">{texto}</p>
    </div>
    """.strip()


class ResumenImportacion:
    def __init__(self):
        self.total = 0
        self.creadas = 0
        self.actualizadas = 0
        self.duplicadas = 0  # mismo (factura+consecutivo+valor+fecha) — se saltan
        self.ratificadas = 0
        self.extemporaneas = 0
        self.errores: list[str] = []
        self.duplicadas_detalle: list[dict] = []
        self.por_gestor: dict[str, list[dict]] = {}
        self.semaforo: dict[str, int] = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0, "NEGRO": 0}
        # Conceptos (hojas I/R)
        self.conceptos_creados = 0
        self.conceptos_actualizados = 0
        self.conceptos_huerfanos: list[dict] = []  # sin GlosaRecord que los ancle

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "creadas": self.creadas,
            "actualizadas": self.actualizadas,
            "duplicadas": self.duplicadas,
            "ratificadas": self.ratificadas,
            "extemporaneas": self.extemporaneas,
            "errores": self.errores,
            "duplicadas_detalle": self.duplicadas_detalle[:50],
            "por_gestor": self.por_gestor,
            "semaforo": self.semaforo,
            "conceptos_creados": self.conceptos_creados,
            "conceptos_actualizados": self.conceptos_actualizados,
            "conceptos_huerfanos": self.conceptos_huerfanos[:50],
        }


class RecepcionService:
    def __init__(self, db: Session):
        self.db = db

    def procesar_excel(self, contenido: bytes) -> ResumenImportacion:
        """Procesa el archivo Excel completo (múltiples hojas).

        Detecta automáticamente el tipo de cada hoja:
          • "RECEPCION"  — hojas INICIAL/RATIFICADA con encabezados de gestor+factura.
          • "CONCEPTOS"  — hojas I/R del DGH con columnas FacturaCartera.* y
                           ListadoConceptos.* (detalle por concepto).
          • "SALTAR"     — hoja vacía o sin columnas reconocibles.

        Orden garantizado: primero RECEPCION (crea/actualiza GlosaRecord),
        después CONCEPTOS (upsert sobre glosas existentes). Así los conceptos
        siempre encuentran su glosa padre. Conceptos huérfanos se reportan.
        """
        resumen = ResumenImportacion()
        try:
            wb = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
        except Exception as e:
            resumen.errores.append(f"Archivo Excel inválido: {e}")
            return resumen

        hojas_disponibles = wb.sheetnames if wb.sheetnames else []
        if not hojas_disponibles:
            resumen.errores.append("El archivo no tiene hojas")
            return resumen

        hoy = datetime.now()

        # Clasificar hojas por tipo antes de procesar
        plan: list[tuple[str, str, int, dict]] = []  # (tipo, nombre, fila_header, indices)
        for nombre_hoja in hojas_disponibles:
            try:
                ws = wb[nombre_hoja]
            except KeyError:
                continue

            # Escaneo rápido de los primeros 5 encabezados para detectar tipo.
            # CONCEPTOS gana si aparecen columnas ListadoConceptos.*;
            # RECEPCION si aparecen factura+vence o factura+fecha_recepcion.
            fila_h_rec, idx_rec = _buscar_fila_encabezado(ws, max_filas=5, mapa=COLUMN_ALIASES, min_aciertos=3)
            fila_h_con, idx_con = _buscar_fila_encabezado(ws, max_filas=5, mapa=CONCEPTO_COLS, min_aciertos=4)

            if idx_con and "concepto_codigo" in idx_con and "factura" in idx_con:
                plan.append(("CONCEPTOS", nombre_hoja, fila_h_con, idx_con))
            elif idx_rec and {"factura", "vence"}.issubset(set(idx_rec.keys())):
                plan.append(("RECEPCION", nombre_hoja, fila_h_rec, idx_rec))
            else:
                logger.warning(
                    f"Hoja '{nombre_hoja}' sin columnas reconocibles — saltando"
                )

        # Procesar RECEPCION primero, CONCEPTOS después
        plan.sort(key=lambda p: 0 if p[0] == "RECEPCION" else 1)

        total_procesadas = 0
        for tipo, nombre_hoja, fila_header, indices in plan:
            ws = wb[nombre_hoja]
            # Re-iterar desde la fila siguiente al encabezado detectado
            filas = ws.iter_rows(values_only=True)
            for _ in range(fila_header):
                try:
                    next(filas)
                except StopIteration:
                    break

            hoja_es_ratificada = (
                "RATIFIC" in (nombre_hoja or "").upper()
                or nombre_hoja.strip().upper() == "R"
            )

            if tipo == "RECEPCION":
                logger.info(
                    f"Procesando hoja '{nombre_hoja}' como RECEPCION "
                    f"{'(RATIFICADAS)' if hoja_es_ratificada else '(INICIALES)'}"
                )
                self._procesar_filas_hoja(
                    filas=filas,
                    indices=indices,
                    resumen=resumen,
                    hoy=hoy,
                    hoja_es_ratificada=hoja_es_ratificada,
                    nombre_hoja=nombre_hoja,
                )
            else:  # CONCEPTOS
                logger.info(
                    f"Procesando hoja '{nombre_hoja}' como CONCEPTOS "
                    f"{'(RATIFICADOS)' if hoja_es_ratificada else '(INICIALES)'}"
                )
                self._procesar_filas_conceptos(
                    filas=filas,
                    indices=indices,
                    resumen=resumen,
                    nombre_hoja=nombre_hoja,
                )
            total_procesadas += 1

        if total_procesadas == 0:
            resumen.errores.append(
                "Ninguna hoja tiene columnas reconocibles. El parser busca hojas "
                "tipo RECEPCION (con FACTURA+VENCE) o CONCEPTOS (con ListadoConceptos.*)."
            )
        return resumen

    def _procesar_filas_hoja(
        self,
        filas,
        indices: dict,
        resumen: "ResumenImportacion",
        hoy: datetime,
        hoja_es_ratificada: bool,
        nombre_hoja: str,
    ):
        """Procesa las filas de una hoja individual."""
        for num_fila, fila in enumerate(filas, start=2):
            if all(c is None or str(c).strip() == "" for c in fila):
                continue

            def _get(key: str):
                i = indices.get(key)
                return fila[i] if i is not None and i < len(fila) else None

            try:
                entidad_raw = _fix_mojibake(str(_get("entidad") or "").strip())
                entidad = entidad_raw.upper()
                factura = str(_get("factura") or "").strip()
                if not entidad or not factura:
                    continue

                # Separar código plan (U220181) del nombre para normalización
                eps_codigo, eps_nombre_limpio = _split_entidad(entidad)

                consecutivo = str(_get("consecutivo_dgh") or "").strip()
                gestor = str(_get("gestor") or "").strip().upper() or "SIN ASIGNAR"
                radicado_info = str(_get("radicado") or "").strip()
                referencia = str(_get("referencia") or "").strip()
                observacion_tecnico = _fix_mojibake(str(_get("observacion_tecnico") or "").strip())
                tipo_glosa_excel = str(_get("tipo_glosa") or "").strip()
                profesional_medico = str(_get("profesional_medico") or "").strip()
                tecnico_recepcion = str(_get("tecnico_recepcion") or "").strip()
                devolucion = str(_get("devolucion") or "").strip().upper()[:1]

                fecha_entrega = _a_fecha(_get("fecha_entrega"))
                fecha_rad = _a_fecha(_get("fecha_radicacion"))
                fecha_dgh = _a_fecha(_get("fecha_documento_dgh"))
                fecha_rec = _a_fecha(_get("fecha_recepcion"))
                fecha_vence = _a_fecha(_get("vence"))
                valor = _a_float(_get("valor_glosa"))

                if fecha_vence is None or fecha_rec is None:
                    resumen.errores.append(f"Fila {num_fila}: fechas VENCE/RECEPCION inválidas")
                    continue

                # Flag del técnico para saltar extemporaneidad (ej. PPL/FOMAG con régimen especial)
                skip_extemporaneidad = _no_aplicar_extemporaneidad(observacion_tecnico)

                # Extemporaneidad: días hábiles entre FECHA RADICACION y FECHA DOCUMENTO DGH
                dias_transcurridos = 0
                es_extemporanea = False
                if fecha_rad and fecha_dgh:
                    dias_transcurridos = _dias_habiles(fecha_rad, fecha_dgh)
                    es_extemporanea = (
                        dias_transcurridos > DIAS_HABILES_LIMITE_EXTEMPORANEA
                        and not skip_extemporaneidad
                    )

                # Semáforo: días hábiles restantes hasta VENCE
                dias_restantes = _dias_habiles(hoy, fecha_vence) if fecha_vence > hoy else 0
                semaforo = _semaforo(dias_restantes)

                # Ratificación: la hoja entera puede ser de ratificaciones (nombre
                # "RATIFICADA") o bien detectarse fila a fila en RADICADO/REFERENCIA.
                ratificada = hoja_es_ratificada or _es_ratificada(radicado_info, referencia)

                # numero_radicado: si RADICADO no es un texto de ratificación, es el radicado real
                if ratificada:
                    numero_radicado_real = None
                else:
                    numero_radicado_real = radicado_info or None

                if ratificada:
                    estado = "RATIFICADA"
                    texto_ref = radicado_info or referencia
                    dictamen = _dictamen_ratificada(entidad, factura, texto_ref)
                    resumen.ratificadas += 1
                elif es_extemporanea:
                    estado = "EXTEMPORANEA"
                    dictamen = _dictamen_extemporanea(entidad, factura, dias_transcurridos)
                    resumen.extemporaneas += 1
                else:
                    estado = "RADICADA"
                    nota_obs = (
                        f'<div style="margin-top:10px;padding:10px;background:#fef3c7;border-left:3px solid #eab308;border-radius:6px;font-size:12px">'
                        f'<b>⚠ Observación técnico:</b> {observacion_tecnico}</div>'
                    ) if observacion_tecnico else ""
                    dictamen = (
                        f'<div style="padding:15px;background:#f8fafc;border-radius:8px;">'
                        f'<b>Glosa importada desde recepción.</b><br>'
                        f'Pendiente de análisis y respuesta por el gestor asignado.'
                        f'{nota_obs}'
                        f'</div>'
                    )

                # Upsert por (factura + consecutivo_dgh) o solo factura si no hay consecutivo
                q = self.db.query(GlosaRecord).filter(GlosaRecord.factura == factura)
                if consecutivo:
                    q = q.filter(GlosaRecord.consecutivo_dgh == consecutivo)
                existente = q.first()

                campos = dict(
                    eps=entidad,
                    eps_codigo=eps_codigo or None,
                    paciente="N/A",
                    factura=factura,
                    numero_radicado=numero_radicado_real,
                    consecutivo_dgh=consecutivo or None,
                    gestor_nombre=gestor,
                    tecnico_recepcion=tecnico_recepcion or None,
                    fecha_radicacion_factura=fecha_rad,
                    fecha_documento_dgh=fecha_dgh,
                    fecha_recepcion=fecha_rec,
                    fecha_entrega=fecha_entrega,
                    fecha_vencimiento=fecha_vence,
                    es_devolucion=devolucion or None,
                    radicado_info=radicado_info or None,
                    referencia=referencia or None,
                    observacion_tecnico=observacion_tecnico or None,
                    tipo_glosa_excel=tipo_glosa_excel or None,
                    profesional_medico=profesional_medico or None,
                    valor_objetado=valor,
                    valor_aceptado=0.0,
                    etapa="RESPUESTA A GLOSA",
                    estado=estado,
                    dictamen=dictamen,
                    dias_restantes=dias_restantes,
                    # Dias habiles FECHA RADICACION -> FECHA DOCUMENTO DGH (excl. findes/festivos).
                    # Es lo que el auditor ve en la columna "Dias" de Mis glosas, usado como
                    # indicador de extemporaneidad (si > 20, EPS gloso fuera de termino).
                    dias_radicacion_dgh=dias_transcurridos,
                    prioridad=semaforo,
                    workflow_state=estado,
                    modelo_ia="importacion_recepcion",
                )

                if existente:
                    # Detectar duplicado exacto (misma factura+consecutivo+valor+fecha)
                    es_duplicado_exacto = (
                        abs(float(existente.valor_objetado or 0) - float(valor)) < 0.01
                        and (existente.fecha_recepcion == fecha_rec)
                        and ((existente.consecutivo_dgh or "") == (consecutivo or ""))
                    )
                    if es_duplicado_exacto:
                        resumen.duplicadas += 1
                        resumen.duplicadas_detalle.append({
                            "fila": num_fila,
                            "factura": factura,
                            "consecutivo_dgh": consecutivo,
                            "valor": valor,
                            "glosa_existente_id": existente.id,
                            "motivo": "Misma factura + consecutivo + valor + fecha recepción",
                        })
                        continue
                    # Distinto en algún campo → actualizar (posible reimportación con correcciones)
                    for k, v in campos.items():
                        setattr(existente, k, v)
                    resumen.actualizadas += 1
                else:
                    self.db.add(GlosaRecord(**campos))
                    resumen.creadas += 1

                resumen.total += 1
                resumen.semaforo[semaforo] = resumen.semaforo.get(semaforo, 0) + 1
                resumen.por_gestor.setdefault(gestor, []).append({
                    "factura": factura,
                    "consecutivo_dgh": consecutivo,
                    "eps": entidad,
                    "valor": valor,
                    "vence": fecha_vence.strftime("%d/%m/%Y"),
                    "fecha_entrega": fecha_entrega.strftime("%d/%m/%Y") if fecha_entrega else "N/A",
                    "semaforo": semaforo,
                    "estado": estado,
                    "tipo_glosa": tipo_glosa_excel or "-",
                    "radicado": numero_radicado_real or "-",
                })

            except Exception as e:
                resumen.errores.append(f"Fila {num_fila}: {e}")
                logger.warning(f"Error procesando fila {num_fila}: {e}")
                continue

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Error guardando importación: {e}")
            self.db.rollback()
            resumen.errores.append(f"Error al guardar: {e}")

        return resumen

    def _procesar_filas_conceptos(
        self,
        filas,
        indices: dict,
        resumen: "ResumenImportacion",
        nombre_hoja: str,
    ):
        """Procesa hoja de conceptos (I/R del DGH).

        Cada fila = 1 concepto asociado a una factura+consecutivo DGH. Se hace
        upsert contra la tabla ``conceptos_glosa`` usando ``ListadoConceptos.Oid``
        como clave de idempotencia. La glosa padre debe existir (cargada antes
        desde INICIAL/RATIFICADA); si no, el concepto se reporta como huérfano.
        """
        for num_fila, fila in enumerate(filas, start=2):
            if all(c is None or str(c).strip() == "" for c in fila):
                continue

            def _get(key: str):
                i = indices.get(key)
                return fila[i] if i is not None and i < len(fila) else None

            try:
                factura = str(_get("factura") or "").strip()
                consecutivo = str(_get("consecutivo") or "").strip()
                codigo_glosa = str(_get("concepto_codigo") or "").strip().upper()
                oid = str(_get("concepto_oid") or "").strip()
                if not factura or not consecutivo or not codigo_glosa:
                    # Sin estos 3 campos mínimos, la fila no es un concepto válido
                    continue

                nombre_glosa = _fix_mojibake(str(_get("concepto_nombre") or "").strip())
                cups_codigo = str(_get("cups_codigo") or "").strip()
                cups_desc = _fix_mojibake(str(_get("cups_descripcion") or "").strip())
                centro_costo = _fix_mojibake(str(_get("centro_costo") or "").strip())
                observacion = _fix_mojibake(str(_get("concepto_observacion") or "").strip())
                valor_obj = _a_float(_get("concepto_valor"))

                # Buscar la glosa padre por factura + consecutivo
                glosa_padre = (
                    self.db.query(GlosaRecord)
                    .filter(
                        GlosaRecord.factura == factura,
                        GlosaRecord.consecutivo_dgh == consecutivo,
                    )
                    .first()
                )
                if not glosa_padre:
                    resumen.conceptos_huerfanos.append({
                        "fila": num_fila,
                        "hoja": nombre_hoja,
                        "factura": factura,
                        "consecutivo_dgh": consecutivo,
                        "codigo_glosa": codigo_glosa,
                        "cups": cups_codigo,
                        "valor": valor_obj,
                        "motivo": "No existe glosa con esa FACTURA+CONSECUTIVO DGH (carga primero INICIAL/RATIFICADA)",
                    })
                    continue

                # Extra: completar metadatos de la glosa padre desde la hoja I/R
                # (saldo, valor factura, NIT) si venían vacíos de INICIAL/RATIFICADA.
                if _get("saldo_factura") is not None and not glosa_padre.saldo_factura:
                    glosa_padre.saldo_factura = _a_float(_get("saldo_factura"))
                if _get("valor_factura") is not None and not glosa_padre.valor_factura:
                    glosa_padre.valor_factura = _a_float(_get("valor_factura"))
                nit = str(_get("tercero_nit") or "").strip()
                if nit and not glosa_padre.tercero_nit:
                    glosa_padre.tercero_nit = nit
                fecha_obj = _a_fecha(_get("fecha_objecion"))
                if fecha_obj and not glosa_padre.fecha_objecion_eps:
                    glosa_padre.fecha_objecion_eps = fecha_obj

                # Upsert del concepto por OID (idempotente)
                concepto_existente = None
                if oid:
                    concepto_existente = (
                        self.db.query(ConceptoGlosaRecord)
                        .filter(ConceptoGlosaRecord.oid_dgh == oid)
                        .first()
                    )

                campos = dict(
                    glosa_id=glosa_padre.id,
                    oid_dgh=oid or None,
                    consecutivo_dgh=consecutivo,
                    factura=factura,
                    codigo_glosa=codigo_glosa,
                    nombre_glosa=nombre_glosa or None,
                    cups_codigo=cups_codigo or None,
                    cups_descripcion=cups_desc or None,
                    centro_costo=centro_costo or None,
                    valor_objetado=valor_obj,
                    observacion_eps=observacion or None,
                )

                if concepto_existente:
                    for k, v in campos.items():
                        setattr(concepto_existente, k, v)
                    resumen.conceptos_actualizados += 1
                else:
                    self.db.add(ConceptoGlosaRecord(**campos))
                    resumen.conceptos_creados += 1

            except Exception as e:
                resumen.errores.append(f"[Conceptos {nombre_hoja}] Fila {num_fila}: {e}")
                logger.warning(f"Error procesando concepto fila {num_fila}: {e}")
                continue

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Error guardando conceptos: {e}")
            self.db.rollback()
            resumen.errores.append(f"Error al guardar conceptos: {e}")
