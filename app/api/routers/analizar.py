"""Endpoint /analizar — entrada principal del motor de glosas (R53 P1).

Extraído de app/main.py (era ~365 LOC). Maneja:
  - Validación de input (GlosaInput)
  - Extracción de PDFs adjuntos (con OCR opcional vía Claude Vision)
  - Pre-lookup de tarifa pactada (TA*) para evitar tokens innecesarios
  - Llamada al GlosaService (IA + few-shots de plantillas Gold)
  - Generación de banner de tarifa + dictamen de aceptación si aplica
  - Persistencia (GlosaRecord) + snapshot de versión inicial
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.core.logging_utils import logger, set_request_id
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.db import UsuarioRecord
from app.models.schemas import GlosaInput, GlosaResult
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.glosa_repository import GlosaRepository
from app.services.glosa_ia_prompts import get_contrato
from app.services.glosa_service import GlosaService
from app.utils.parsers_glosa import (
    _concepto_glosa,
    _descripcion_servicio,
    _extraer_cups_servicio,
    _extraer_valores_glosa,
    _generar_banner_tarifa_html,
)

router = APIRouter(tags=["analizar"])

cfg = get_settings()

MAX_ARCHIVOS = 10  # Límite de soportes PDF por glosa
MAX_BYTES_PDF = 15_000_000  # 15 MB por archivo
# Cuántos soportes auto-detectados del servidor inyectar al prompt.
# Limitamos a 3 PDFs y 5000 chars c/u para no romper memoria de Render Free.
MAX_SOPORTES_AUTO = 3
MAX_CHARS_POR_SOPORTE = 5_000
# Tipos prioritarios de soportes (orden de preferencia):
# HEV (historia clínica) > RIPS > FEV (factura electrónica) > el resto.
PRIORIDAD_TIPOS_SOPORTE = ["HEV", "RIPS", "FEV", "OPF", "PDE", "PDX", "CRC", "AD"]


async def _extraer_soportes_del_servidor(
    numero_factura: Optional[str],
    contexto_pdf_existente: str,
    req_id: str,
) -> str:
    """Lee PDFs del servidor de archivos (soportes auto-detectados) y los
    inyecta al contexto IA. Solo se usan si el gestor NO subió archivos
    manualmente — para no duplicar contenido.

    Idempotente: si no hay factura o el indexador no encuentra nada,
    devuelve string vacío sin tirar error.
    """
    if not numero_factura:
        return ""
    if contexto_pdf_existente and len(contexto_pdf_existente) > 1000:
        # El gestor ya subió PDFs manualmente — esos pesan más que los
        # auto-detectados, mejor no duplicar contexto.
        logger.info(
            f"[{req_id}] Soportes auto-detectados: omitidos (gestor subió "
            f"{len(contexto_pdf_existente)} chars manualmente)"
        )
        return ""
    try:
        from app.services.soportes_autodiscovery_service import get_indexer
        soportes = get_indexer().lookup(numero_factura) or []
    except Exception as e:
        logger.warning(f"[{req_id}] Indexador soportes no disponible: {e}")
        return ""
    if not soportes:
        return ""

    # Ordenar por prioridad de tipo
    def _prioridad(s: dict) -> int:
        try:
            return PRIORIDAD_TIPOS_SOPORTE.index(s.get("tipo_codigo") or "")
        except ValueError:
            return len(PRIORIDAD_TIPOS_SOPORTE)
    soportes_ordenados = sorted(soportes, key=_prioridad)

    contexto = ""
    leidos = 0
    from app.services.pdf_service import PdfService
    pdf_svc = PdfService()
    for s in soportes_ordenados:
        if leidos >= MAX_SOPORTES_AUTO:
            break
        ruta = s.get("ruta")
        nombre = s.get("nombre_archivo") or "soporte.pdf"
        tipo = s.get("tipo_codigo") or "OTRO"
        if not ruta:
            continue
        if not nombre.lower().endswith(".pdf"):
            # Para JSON/XML/TXT (RIPS, etc.), inyectamos directo como texto plano
            try:
                from pathlib import Path as _P
                p = _P(ruta)
                if p.exists() and p.stat().st_size < 500_000:
                    contenido_txt = p.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS_POR_SOPORTE]
                    contexto += (
                        f"\n\n═══ SOPORTE AUTO ({tipo}): {nombre} ═══\n\n"
                        + contenido_txt
                    )
                    leidos += 1
                    logger.info(f"[{req_id}] Soporte texto auto: {nombre} ({len(contenido_txt)} chars)")
            except Exception as e:
                logger.warning(f"[{req_id}] No pude leer soporte {nombre}: {e}")
            continue
        # PDF — extraer texto
        try:
            from pathlib import Path as _P
            p = _P(ruta)
            if not p.exists():
                continue
            tam = p.stat().st_size
            if tam > MAX_BYTES_PDF:
                logger.info(f"[{req_id}] Soporte auto omitido por tamaño: {nombre} ({tam} bytes)")
                continue
            if tam < 100:
                # Archivo vacío o corrupto (los hay con 0 KB)
                continue
            contenido_bytes = p.read_bytes()
            texto, metodo = await pdf_svc.extraer_con_ocr(
                contenido_bytes,
                anthropic_api_key=cfg.anthropic_api_key,
                anthropic_model=cfg.anthropic_model,
            )
            texto_recortado = (texto or "")[:MAX_CHARS_POR_SOPORTE]
            if not texto_recortado.strip():
                continue
            contexto += (
                f"\n\n═══ SOPORTE AUTO ({tipo}): {nombre} ═══\n\n"
                + texto_recortado
            )
            leidos += 1
            logger.info(
                f"[{req_id}] Soporte auto inyectado: {nombre} "
                f"({metodo}, {len(texto_recortado)} chars)"
            )
        except Exception as e:
            logger.warning(f"[{req_id}] Error procesando soporte auto {nombre}: {e}")

    if contexto:
        logger.info(
            f"[{req_id}] Soportes auto-detectados inyectados: {leidos}/{len(soportes)} "
            f"| total {len(contexto)} chars"
        )
    return contexto


async def _extraer_pdfs(
    archivos: Optional[list[UploadFile]],
    req_id: str,
    capturar_raw: bool = False,
) -> tuple[str, int, Optional[list[tuple[str, bytes]]]]:
    """Extrae texto de los PDFs adjuntos (con OCR Claude opcional).

    Retorna (texto_concatenado, archivos_procesados, pdfs_raw_o_None).
    Los PDFs se separan con un marker '═══ DOCUMENTO: <filename> ═══'
    para que la IA distinga entre ellos. Errores por archivo se loguean
    pero no abortan el batch.

    Si capturar_raw=True, además del texto extraído devuelve los bytes
    crudos para que el caller los pueda enviar al modo multi-modal.
    """
    if not archivos:
        return "", 0, None

    from app.services.pdf_service import PdfService
    pdf_svc = PdfService()
    contexto_pdf = ""
    procesados = 0
    raw_acumulado: list[tuple[str, bytes]] = [] if capturar_raw else None

    for archivo in archivos:
        if procesados >= MAX_ARCHIVOS:
            logger.warning(
                f"[{req_id}] Máximo {MAX_ARCHIVOS} archivos alcanzado, "
                "ignorando restantes"
            )
            break
        if not archivo.filename:
            continue
        try:
            contenido = await archivo.read()
            if contenido[:4] != b"%PDF":
                logger.warning(f"[{req_id}] Archivo ignorado (no es PDF): {archivo.filename}")
                continue
            if len(contenido) > MAX_BYTES_PDF:
                logger.warning(f"[{req_id}] PDF muy grande: {archivo.filename}")
                continue
            if raw_acumulado is not None:
                raw_acumulado.append((archivo.filename, contenido))
            texto, metodo = await pdf_svc.extraer_con_ocr(
                contenido,
                anthropic_api_key=cfg.anthropic_api_key,
                anthropic_model=cfg.anthropic_model,
                gemini_api_key=cfg.gemini_api_key,
                gemini_model=cfg.gemini_model,
            )
            sep = (
                f"\n\n═══ DOCUMENTO: {archivo.filename} ═══\n\n"
                if contexto_pdf
                else f"═══ DOCUMENTO: {archivo.filename} ═══\n\n"
            )
            contexto_pdf += sep + texto
            procesados += 1
            logger.info(f"[{req_id}] PDF {archivo.filename}: {metodo} ({len(texto)} chars)")
        except Exception as e:
            logger.warning(f"[{req_id}] Error extrayendo PDF {archivo.filename}: {e}")

    if procesados:
        logger.info(
            f"[{req_id}] Total PDFs procesados: {procesados}/{MAX_ARCHIVOS} "
            f"| {len(contexto_pdf)} chars | raw_capturado={raw_acumulado is not None}"
        )
    return contexto_pdf, procesados, raw_acumulado


def _obtener_few_shots(
    db: Session, eps: str, tabla_excel: str,
) -> tuple[list[str], list, str]:
    """Pre-fetch de Plantillas Gold para inyectar como few-shot al LLM.

    Devuelve (lista_argumentos, lista_records, codigo_prefijo). El prefijo
    se usa también para el pre-lookup de tarifa.
    """
    from app.api.routers.plantillas_gold import obtener_few_shot
    codigo_match = re.search(
        r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b",
        tabla_excel.upper(),
    )
    cod_pref = codigo_match.group(0) if codigo_match else ""
    plantillas_gold = (
        obtener_few_shot(db, eps=eps, codigo_glosa=cod_pref, limite=2)
        if cod_pref else []
    )
    few_shots = [p.argumento for p in plantillas_gold]
    return few_shots, plantillas_gold, cod_pref


def _pre_lookup_tarifa(
    db: Session, cod_pref: str, eps: str,
    tabla_excel: str, contexto_pdf: str, req_id: str,
) -> Optional[dict]:
    """Wrapper local sobre tarifa_lookup_service.pre_lookup_tarifa.
    Mantenido para no romper el call site original (línea 573 de este módulo).
    """
    from app.services.tarifa_lookup_service import pre_lookup_tarifa
    return pre_lookup_tarifa(
        db=db, cod_pref=cod_pref, eps=eps,
        tabla_excel=tabla_excel, contexto_pdf=contexto_pdf, req_id=req_id,
    )


def _agregar_banner_tarifa_post(
    db: Session, resultado, eps: str, tabla_excel: str,
    contexto_pdf: str, val_obj: float, val_ac: float, req_id: str,
) -> None:
    """Si es glosa TA con CUPS extraíble, busca la tarifa y prefija el
    banner HTML al dictamen para que el auditor vea los datos duros."""
    es_ta = (resultado.codigo_glosa or "").upper().startswith("TA")
    if not es_ta:
        return
    cups_ext, _ = _extraer_cups_servicio(tabla_excel or "", contexto_pdf)
    if not cups_ext:
        return
    try:
        from app.services.tarifa_lookup_service import evaluar_glosa_tarifa
        # Buscar valores en la glosa Y en el PDF (la factura electrónica
        # HUS trae "VALOR TOTAL ORDEN DE SERVICIO $X" — fuente confiable
        # del facturado real, distinto del valor objetado por la EPS).
        vals_txt = _extraer_valores_glosa(tabla_excel or "", cups=cups_ext)
        val_fact = vals_txt["facturado"]
        val_rec = vals_txt["reconocido"]
        if val_fact <= 0 and contexto_pdf:
            vals_pdf = _extraer_valores_glosa(contexto_pdf, cups=cups_ext)
            if vals_pdf["facturado"] > 0:
                val_fact = vals_pdf["facturado"]
        info_tarifa = evaluar_glosa_tarifa(
            db, eps=eps, cups=cups_ext,
            valor_facturado=val_fact, valor_objetado=val_obj,
            valor_reconocido=val_rec,
        )
        if not info_tarifa.get("encontrada"):
            from app.services.tarifas_oficiales import tarifa_a_banner_dict
            oficial = tarifa_a_banner_dict(cups_ext)
            if oficial:
                info_tarifa = {
                    "encontrada": True, "tarifa": oficial,
                    "valor_facturado": val_fact, "valor_objetado": val_obj,
                    "valor_reconocido": val_rec,
                    "valor_pactado_calc": oficial["valor_pactado"],
                    "recomendacion": {
                        "accion": "DEFENDER_TOTAL" if val_fact <= oficial["valor_pactado"] + 1 else "REVISAR",
                        "titulo": "✅ Valor oficial HUS/SOAT conocido — defender",
                        "razon": (
                            f"El valor oficial publicado para este CUPS es "
                            f"${oficial['valor_pactado']:,.0f} según {oficial['contrato_numero']}. "
                            "Defender este valor citando la norma institucional."
                        ),
                        "valor_a_defender": val_obj,
                        "valor_a_aceptar": 0.0,
                        "diferencia": 0.0,
                    },
                }
        if info_tarifa.get("encontrada"):
            banner = _generar_banner_tarifa_html(info_tarifa)
            if banner:
                resultado.dictamen = banner + (resultado.dictamen or "")
                rec = info_tarifa.get("recomendacion") or {}
                logger.info(
                    f"[{req_id}] Tarifa pactada: cups={cups_ext} "
                    f"fact=${val_fact:,.0f} rec=${val_rec:,.0f} "
                    f"obj=${val_obj:,.0f} accion={rec.get('accion')}"
                )
    except Exception as e:
        logger.warning(f"[{req_id}] No se pudo agregar banner de tarifa: {e}")


def _decidir_estado_y_codigo(val_obj: float, val_ac: float) -> tuple[float, str, Optional[str], Optional[str]]:
    """Determina (val_obj_corregido, estado, cod_respuesta, descripcion).

    BUG fix preservado: si val_obj=0 y hay aceptación, val_ac es la base
    del cálculo (caso de aceptación total con cifra ausente del texto).
    """
    if val_obj == 0 and val_ac > 0:
        return val_ac, "ACEPTADA", "RE9702", "GLOSA ACEPTADA AL 100%"
    if val_ac >= val_obj and val_obj > 0:
        return val_obj, "ACEPTADA", "RE9702", "GLOSA ACEPTADA AL 100%"
    if val_ac > 0:
        return val_obj, "PARCIALMENTE_ACEPTADA", "RE9801", "GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE"
    return val_obj, "RADICADA", None, None


def _construir_dictamen_aceptacion(
    eps: str, codigo_glosa: str, val_obj: float, val_ac: float,
    estado: str, cod_resp: str, desc_resp: str,
    tabla_excel: str, contexto_pdf: str,
) -> str:
    """Genera el HTML completo cuando hay aceptación (total/parcial).

    Estructura: tabla códigos + bloque de argumento (verde/ámbar) +
    tabla resumen de valores. Cita el contrato vigente con la EPS.
    """
    val_rechazado = val_obj - val_ac
    contrato_info = get_contrato(eps)
    num_contrato = contrato_info.get("numero") or "CONTRATO VIGENTE ENTRE LAS PARTES"
    servicio_descr = _descripcion_servicio(
        codigo_glosa, texto_glosa=tabla_excel, contexto_pdf=contexto_pdf,
    )

    if estado == "ACEPTADA":
        argumento = f"""
        <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:20px;margin:15px 0;border-radius:8px;">
            <h4 style="color:#15803d;margin:0 0 10px 0;">RESPUESTA A GLOSA</h4>
            <p style="font-size:13px;line-height:1.8;color:#166534;">
                ESE HUS ACEPTA GLOSA TOTAL POR VALOR DE <strong>${val_ac:,.0f}</strong>,
                CORRESPONDIENTE {servicio_descr}. ESTO CORRESPONDE A UN MAYOR VALOR COBRADO
                SEGÚN <strong>{num_contrato}</strong> PACTADO ENTRE LAS PARTES. SE AJUSTAN LOS VALORES
                DANDO CUMPLIMIENTO A ESTAS TARIFAS.
            </p>
        </div>"""
        val_en_disputa = 0.0
    else:
        val_en_disputa = abs(val_rechazado)
        argumento = f"""
        <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:20px;margin:15px 0;border-radius:8px;">
            <h4 style="color:#92400e;margin:0 0 10px 0;">RESPUESTA A GLOSA</h4>
            <p style="font-size:13px;line-height:1.8;color:#78350f;">
                ESE HUS ACEPTA GLOSA PARCIAL POR VALOR DE <strong>${val_ac:,.0f}</strong>,
                CORRESPONDIENTE {servicio_descr}. ESTO CORRESPONDE A UN MAYOR VALOR COBRADO
                SEGÚN <strong>{num_contrato}</strong> PACTADO ENTRE LAS PARTES. SE AJUSTAN LOS VALORES
                DANDO CUMPLIMIENTO A ESTAS TARIFAS.
            </p>
            <p style="font-size:13px;line-height:1.8;color:#78350f;">
                EL VALOR RESTANTE DE <strong>${val_en_disputa:,.0f}</strong> NO SE ACEPTA POR LA ESE HUS
                YA QUE SE EVIDENCIA QUE ESTE VALOR CORRESPONDE AL VALOR PACTADO ENTRE LAS PARTES.
            </p>
        </div>"""

    tabla_codigos = f"""
    <table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:15px;background:white;border:1px solid #cbd5e1;">
        <thead>
            <tr style="background:#0f172a;color:white;">
                <th style="padding:10px;text-align:center;font-weight:700;letter-spacing:.3px;">CÓDIGO GLOSA</th>
                <th style="padding:10px;text-align:center;font-weight:700;letter-spacing:.3px;">VALOR OBJETADO</th>
                <th style="padding:10px;text-align:center;font-weight:700;letter-spacing:.3px;">CÓDIGO RESPUESTA</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="padding:10px;text-align:center;font-weight:700;border-bottom:1px solid #e2e8f0;">{codigo_glosa}</td>
                <td style="padding:10px;text-align:center;font-weight:700;color:#0f172a;border-bottom:1px solid #e2e8f0;">$ {val_obj:,.0f}</td>
                <td style="padding:10px;text-align:center;border-bottom:1px solid #e2e8f0;">
                    <b>{cod_resp}</b><br>
                    <span style="font-size:10px;color:#64748b;">{desc_resp}</span>
                </td>
            </tr>
        </tbody>
    </table>"""

    tabla_valores = f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;margin-top:15px;">
        <div style="font-weight:700;color:#334155;margin-bottom:10px;font-size:11px;letter-spacing:.4px;text-transform:uppercase;">Resumen de valores</div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <tr>
                <td style="padding:6px 8px;color:#475569;">Valor objetado</td>
                <td style="padding:6px 8px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums;">$ {val_obj:,.0f}</td>
            </tr>
            <tr>
                <td style="padding:6px 8px;color:#047857;">Valor aceptado</td>
                <td style="padding:6px 8px;text-align:right;font-weight:700;color:#047857;font-variant-numeric:tabular-nums;">$ {val_ac:,.0f}</td>
            </tr>"""
    if estado == "PARCIALMENTE_ACEPTADA":
        tabla_valores += f"""
            <tr>
                <td style="padding:6px 8px;color:#b91c1c;">Valor en disputa</td>
                <td style="padding:6px 8px;text-align:right;font-weight:700;color:#b91c1c;font-variant-numeric:tabular-nums;">$ {val_en_disputa:,.0f}</td>
            </tr>"""
    tabla_valores += """
        </table>
    </div>"""

    return tabla_codigos + argumento + tabla_valores


async def _persistir_y_responder(
    db: Session, resultado, eps: str, etapa: str,
    valor_aceptado: str, tabla_excel: str, contexto_pdf: str,
    numero_factura: Optional[str], numero_radicado: Optional[str],
    data, current_user, req_id: str,
):
    """Cierra el flujo: aplica banner de tarifa, decide estado, construye
    dictamen final, persiste GlosaRecord, guarda snapshot de versión."""
    glosa_repo = GlosaRepository(db)
    val_obj = float(re.sub(r"[^\d]", "", resultado.valor_objetado) or 0)
    val_ac = float(re.sub(r"[^\d]", "", valor_aceptado) or 0)

    _agregar_banner_tarifa_post(
        db, resultado, eps, tabla_excel, contexto_pdf, val_obj, val_ac, req_id,
    )

    val_obj, estado, cod_resp_acept, desc_resp_acept = _decidir_estado_y_codigo(
        val_obj, val_ac,
    )

    dictamen_final = resultado.dictamen
    if estado in ("ACEPTADA", "PARCIALMENTE_ACEPTADA"):
        dictamen_final = _construir_dictamen_aceptacion(
            eps=eps, codigo_glosa=resultado.codigo_glosa,
            val_obj=val_obj, val_ac=val_ac,
            estado=estado, cod_resp=cod_resp_acept,
            desc_resp=desc_resp_acept,
            tabla_excel=tabla_excel, contexto_pdf=contexto_pdf,
        )

    tipo_final = (
        f"RESPUESTA {cod_resp_acept}" if cod_resp_acept else resultado.tipo
    )
    cup_ext, servicio_ext = _extraer_cups_servicio(tabla_excel or "", contexto_pdf)
    cod_resp_m = re.search(r"\bRE\d{4}\b", tipo_final or "")
    cod_resp = cod_resp_m.group(0) if cod_resp_m else (cod_resp_acept or "")

    # R-backend 27-abr-2026: anti-duplicación.
    # Si ya existe una glosa para el par (factura, codigo_glosa, cups,
    # etapa) hacemos UPDATE en vez de INSERT. Esto evita los duplicados
    # que ocurrían cuando el frontend llamaba /analizar dos veces para
    # la misma glosa (ej. el gestor abre una respondida y vuelve a
    # darle Analizar). El frontend ya redirige a /reanalizar cuando
    # sabe el ID, pero esto es la doble salvaguarda en el server.
    existente = None
    try:
        if numero_factura and resultado.codigo_glosa:
            from app.models.db import GlosaRecord as _GR
            q = (
                db.query(_GR)
                .filter(_GR.factura == numero_factura)
                .filter(_GR.codigo_glosa == resultado.codigo_glosa)
                .filter(_GR.etapa == etapa)
            )
            if cup_ext:
                q = q.filter(_GR.cups_servicio == cup_ext)
            existente = q.order_by(_GR.creado_en.desc()).first()
    except Exception as _e_dup:
        logger.debug(f"[ANTI-DUP] Lookup falló: {_e_dup}")

    if existente:
        # UPDATE de la fila existente — sobreescribe dictamen y campos.
        from datetime import datetime, timezone as _tz
        existente.valor_objetado = val_obj
        existente.valor_aceptado = val_ac
        existente.estado = estado
        existente.dictamen = dictamen_final
        existente.dictamen_generado_en = datetime.now(_tz.utc)
        existente.dias_restantes = resultado.dias_restantes
        existente.modelo_ia = resultado.modelo_ia
        existente.score = resultado.score
        existente.numero_radicado = (
            numero_radicado or existente.numero_radicado
        )
        existente.texto_glosa_original = (
            tabla_excel or existente.texto_glosa_original
        )
        existente.codigo_respuesta = cod_resp or existente.codigo_respuesta
        existente.cups_servicio = (
            cup_ext or existente.cups_servicio
        )
        existente.servicio_descripcion = (
            servicio_ext or existente.servicio_descripcion
        )
        existente.paciente = resultado.paciente or existente.paciente
        if data and getattr(data, "fecha_recepcion", None):
            existente.fecha_recepcion = data.fecha_recepcion
        db.commit()
        db.refresh(existente)
        glosa = existente
        logger.info(
            f"[{req_id}] [ANTI-DUP] Glosa existente actualizada "
            f"ID={glosa.id} factura={numero_factura} "
            f"codigo={resultado.codigo_glosa} cups={cup_ext} (no se duplicó)"
        )
    else:
        glosa = glosa_repo.crear(
            eps=eps,
            paciente=resultado.paciente,
            codigo_glosa=resultado.codigo_glosa,
            valor_objetado=val_obj,
            valor_aceptado=val_ac,
            etapa=etapa,
            estado=estado,
            dictamen=dictamen_final,
            dias_restantes=resultado.dias_restantes,
            modelo_ia=resultado.modelo_ia,
            score=resultado.score,
            numero_radicado=numero_radicado,
            factura=numero_factura,
            texto_glosa_original=tabla_excel,
            codigo_respuesta=cod_resp,
            cups_servicio=cup_ext or None,
            servicio_descripcion=servicio_ext or None,
            concepto_glosa=_concepto_glosa(resultado.codigo_glosa),
            fecha_recepcion=data.fecha_recepcion,
        )

    if estado == "RADICADA":
        glosa_repo.actualizar_estado(
            glosa.id, "RESPONDIDA", responsable=current_user.email,
        )

    logger.info(f"[{req_id}] Glosa guardada ID={glosa.id} | estado={estado}")
    # R56 P1: ahora que la glosa existe en BD, los siguientes calls IA
    # de este request quedan trazados a su id (caso de glosas que disparen
    # un análisis adicional, ej. evaluación de riesgo).
    from app.core.logging_utils import glosa_id_var
    glosa_id_var.set(glosa.id)

    resultado.tipo = tipo_final
    resultado.dictamen = dictamen_final
    resultado.glosa_id = glosa.id
    try:
        from app.api.routers.versiones import guardar_version
        guardar_version(
            db=db, glosa_id=glosa.id, dictamen_html=dictamen_final,
            accion="CREAR", autor_email=current_user.email,
        )
    except Exception as e:
        logger.warning(f"No se pudo guardar version: {e}")
    return resultado


def get_glosa_service() -> GlosaService:
    """Factory del GlosaService (inyectado vía Depends en el endpoint)."""
    return GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
        gemini_api_key=cfg.gemini_api_key,
        gemini_model=cfg.gemini_model,
    )


@router.post(
    "/analizar",
    response_model=GlosaResult,
    summary="Analizar Glosa",
    description="Analiza una glosa y genera respuesta técnico-jurídica automática.",
)
@limiter.limit("60/minute")
async def analizar(
    request: Request,
    eps: str = Form(...),
    etapa: str = Form(...),
    fecha_radicacion: Optional[str] = Form(None),
    fecha_recepcion: Optional[str] = Form(None),
    valor_aceptado: str = Form("0"),
    tabla_excel: str = Form(...),
    numero_factura: Optional[str] = Form(None),
    numero_radicado: Optional[str] = Form(None),
    tono: Optional[str] = Form("conciliador"),
    modo_respuesta: Optional[str] = Form("defender"),
    valor_aceptado_parcial: Optional[float] = Form(0.0),
    usar_pdf_nativo_soportes: Optional[bool] = Form(False),
    archivos: Optional[list[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    service: GlosaService = Depends(get_glosa_service),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    req_id = set_request_id()
    # R56 P1: trazar el call IA al usuario via ContextVar.
    # glosa_id se setea más tarde, en _persistir_y_responder cuando ya
    # existe la fila en BD.
    from app.core.logging_utils import user_email_var
    user_email_var.set(current_user.email or "")
    logger.info(
        f"[{req_id}] Análisis solicitado por: {current_user.email} | "
        f"eps={eps} | tono={tono} | modo={modo_respuesta}"
    )

    try:
        data = GlosaInput(
            eps=eps, etapa=etapa,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
            valor_aceptado=valor_aceptado,
            tabla_excel=tabla_excel,
            numero_factura=numero_factura,
            numero_radicado=numero_radicado,
            tono=tono,
            modo_respuesta=modo_respuesta or "defender",
            valor_aceptado_parcial=valor_aceptado_parcial or 0.0,
            usar_pdf_nativo_soportes=bool(usar_pdf_nativo_soportes),
        )
    except Exception as e:
        logger.error(f"[{req_id}] Validación fallida: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    contexto_pdf, archivos_procesados, pdfs_raw = await _extraer_pdfs(
        archivos, req_id, capturar_raw=bool(usar_pdf_nativo_soportes),
    )

    # Soportes auto-detectados del servidor (\\Prime\radicacion_2026):
    # si el gestor NO subió PDFs manualmente, leemos directo del indexador
    # los soportes asociados a esta factura (HEV, RIPS, FEV, etc.) y los
    # inyectamos como contexto IA. Esto permite que el dictamen mencione
    # paciente, servicios y fechas reales sin que el gestor tenga que
    # buscar y subir cada PDF a mano.
    contexto_soportes_auto = await _extraer_soportes_del_servidor(
        numero_factura=numero_factura,
        contexto_pdf_existente=contexto_pdf,
        req_id=req_id,
    )
    if contexto_soportes_auto:
        contexto_pdf = (contexto_pdf + "\n\n" + contexto_soportes_auto) if contexto_pdf else contexto_soportes_auto
        # Contar como "archivos procesados" para que el motor IA detecte
        # que hay soportes disponibles y referencie en el dictamen.
        archivos_procesados += contexto_soportes_auto.count("═══ SOPORTE AUTO")

    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()

    few_shots, plantillas_gold, cod_pref = _obtener_few_shots(db, eps, tabla_excel)

    info_tarifa_pre = _pre_lookup_tarifa(
        db, cod_pref, eps, tabla_excel, contexto_pdf, req_id
    )

    resultado = await service.analizar(
        data, contexto_pdf, contratos,
        few_shots=few_shots, info_tarifa=info_tarifa_pre,
        pdfs_raw_para_multimodal=pdfs_raw,
    )
    if plantillas_gold:
        from app.api.routers.plantillas_gold import marcar_usos
        marcar_usos(db, [p.id for p in plantillas_gold])
    logger.info(
        f"[{req_id}] Análisis completado | modelo={resultado.modelo_ia} "
        f"| few_shots={len(few_shots)} | tarifa_match={bool(info_tarifa_pre and info_tarifa_pre.get('encontrada'))}"
    )

    return await _persistir_y_responder(
        db, resultado, eps, etapa, valor_aceptado, tabla_excel, contexto_pdf,
        numero_factura, numero_radicado, data, current_user, req_id,
    )


# ════════════════════════════════════════════════════════════════════
# Endpoints de soporte para el rediseno del panel "Analizar glosa"
# ════════════════════════════════════════════════════════════════════

@router.post("/analizar/preview")
async def preview_glosa(
    request: Request,
    payload: dict,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Detecta automaticamente desde el texto crudo de la glosa:
      - codigo (TA0201, FA0101, etc)
      - valor objetado / facturado / reconocido
      - EPS si aparece mencionada
      - CUPS y descripcion del servicio
      - tipo de glosa (TA, FA, SO, etc)
      - probable patron determinista (RATIFICADA, EXTEMPORANEA, etc)

    Sirve para alimentar el panel preview EN VIVO del frontend mientras
    el usuario escribe. NO invoca IA — solo regex y heuristicas.
    """
    texto = (payload or {}).get("texto", "")
    eps_form = (payload or {}).get("eps", "")
    if not texto or len(texto) < 5:
        return {"detectado": False}

    texto_upper = texto.upper()

    codigo_match = re.search(
        r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\s*\d{2,4}\b",
        texto_upper,
    )
    codigo = re.sub(r"\s+", "", codigo_match.group(0)) if codigo_match else ""

    prefijo = codigo[:2] if len(codigo) >= 2 else ""
    concepto = _concepto_glosa(codigo) if codigo else ""

    valores = _extraer_valores_glosa(texto)

    if (valores.get("objetado", 0) or 0) <= 0:
        m_simple = re.search(r"\$\s*([\d][\d\.,]{2,})", texto)
        if m_simple:
            raw = re.sub(r"[^\d]", "", m_simple.group(1))
            if raw:
                try:
                    v = float(raw)
                    if 0 < v < 1_000_000_000:
                        valores["objetado"] = v
                except ValueError:
                    pass

    eps_detectada = ""
    if not eps_form or eps_form.upper() in ("OTRA / SIN DEFINIR", "OTRA/SIN DEFINIR", ""):
        eps_lista = [
            "NUEVA EPS", "COMPENSAR", "COOSALUD", "POSITIVA", "FOMAG",
            "POLICIA NACIONAL", "AURORA", "SUMIMEDICAL", "PRECIMED",
            "SALUD MIA", "SANITAS", "SURA", "MEDIMAS", "FAMISANAR",
            "MUTUAL SER", "EPS SURA", "SAVIA SALUD",
        ]
        for eps_nombre in eps_lista:
            if eps_nombre in texto_upper:
                eps_detectada = eps_nombre
                break

    cups, descripcion = _extraer_cups_servicio(texto, "")

    contrato_info = None
    eps_para_contrato = eps_form or eps_detectada
    if eps_para_contrato:
        try:
            contrato = get_contrato(eps_para_contrato)
            contrato_info = {
                "numero": contrato.get("numero", ""),
                "tarifa": contrato.get("tarifa", ""),
                "tipo": contrato.get("tipo", ""),
            }
        except Exception:
            pass

    patron_auto = None
    if "RATIFICA" in texto_upper or "INSISTE" in texto_upper:
        patron_auto = "RATIFICACION"
    elif "EXTEMPORANE" in texto_upper or "FUERA DE TERMINO" in texto_upper:
        patron_auto = "EXTEMPORANEA"
    elif "ACEPTADA" in texto_upper or "CONCILIADA" in texto_upper:
        patron_auto = "ACEPTADA"

    return {
        "detectado": True,
        "codigo": codigo,
        "prefijo": prefijo,
        "concepto": concepto,
        "valor_objetado": valores.get("objetado", 0) or 0,
        "valor_facturado": valores.get("facturado", 0) or 0,
        "valor_reconocido": valores.get("reconocido", 0) or 0,
        "eps_detectada": eps_detectada,
        "cups": cups,
        "descripcion_servicio": descripcion,
        "contrato": contrato_info,
        "patron_auto": patron_auto,
        "longitud_texto": len(texto),
    }


@router.post("/analizar/extraer-correo")
async def extraer_de_correo(
    request: Request,
    payload: dict,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Recibe el texto crudo de un correo de EPS y extrae los campos
    estructurados (EPS, codigo, valor, factura, radicado, motivo).

    Usa solo regex y heuristica. Si el correo es muy desestructurado y
    no detecta lo basico, devuelve {"detectado": false}.
    """
    raw = (payload or {}).get("texto_correo", "")
    if not raw or len(raw) < 20:
        return {"detectado": False, "razon": "texto vacio o muy corto"}

    texto_upper = raw.upper()

    factura_match = re.search(r"(?:FACTURA|FACT|FV[-\s]?)\s*[:\-]?\s*([A-Z0-9\-]{4,20})", texto_upper)
    radicado_match = re.search(r"(?:RADIC|GLS[-\s]?)\s*[:\-]?\s*([A-Z0-9\-]{4,20})", texto_upper)
    fecha_match = re.search(r"\b(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})\b", raw)

    eps_detectada = ""
    eps_lista = [
        "NUEVA EPS", "COMPENSAR", "COOSALUD", "POSITIVA", "FOMAG",
        "POLICIA NACIONAL", "AURORA", "SUMIMEDICAL", "PRECIMED",
        "SALUD MIA", "SANITAS", "SURA", "MEDIMAS", "FAMISANAR",
    ]
    for eps_nombre in eps_lista:
        if eps_nombre in texto_upper:
            eps_detectada = eps_nombre
            break

    codigo_match = re.search(
        r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\s*\d{2,4}\b",
        texto_upper,
    )
    codigo = re.sub(r"\s+", "", codigo_match.group(0)) if codigo_match else ""

    valores = _extraer_valores_glosa(raw)

    motivo = ""
    lineas = [l.strip() for l in raw.split("\n") if l.strip()]
    palabras_clave = ["motivo", "razon", "concepto", "observacion", "se glosa", "se objeta"]
    for l in lineas:
        if any(k in l.lower() for k in palabras_clave):
            motivo = l[:300]
            break
    if not motivo and lineas:
        motivo = max(lineas, key=len)[:300]

    return {
        "detectado": bool(eps_detectada or codigo or factura_match),
        "eps": eps_detectada,
        "codigo": codigo,
        "numero_factura": factura_match.group(1) if factura_match else "",
        "numero_radicado": radicado_match.group(1) if radicado_match else "",
        "fecha_detectada": fecha_match.group(1) if fecha_match else "",
        "valor_objetado": valores.get("objetado", 0) or 0,
        "valor_facturado": valores.get("facturado", 0) or 0,
        "motivo": motivo,
        "texto_glosa_sugerido": _construir_texto_glosa(codigo, valores, motivo),
    }


def _construir_texto_glosa(codigo: str, valores: dict, motivo: str) -> str:
    """Construye un texto-glosa estandar a partir de los campos detectados."""
    partes = []
    if codigo:
        partes.append(codigo)
    obj = valores.get("objetado", 0)
    if obj:
        partes.append(f"- se glosa valor de ${int(obj):,}".replace(",", "."))
    if motivo:
        partes.append(f"por {motivo.lower().lstrip('por ').strip()}")
    return " ".join(partes) if partes else ""


@router.get("/analizar/score-breakdown/{glosa_id}")
async def score_breakdown(
    glosa_id: int,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Devuelve el desglose explicable del score de una glosa ya analizada.

    Factores que componen el score:
      - datos_completos:      todos los campos del caso estan llenos
      - normativa_relevante:  se encontraron articulos/sentencias
      - tarifa_pactada:       el contrato pactado tiene la tarifa
      - precedente_interno:   existe glosa similar ya ganada
      - soportes_adjuntos:    se subieron PDFs / OCR
      - auditor_ok:           el agente auditor no encontro discrepancias
    """
    from app.models.db import GlosaRecord
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="glosa no encontrada")

    factores = []

    datos_completos = bool(g.eps and g.codigo_glosa and (g.valor_objetado or 0) > 0)
    factores.append({
        "id": "datos_completos",
        "etiqueta": "Datos del caso completos",
        "peso": 15,
        "score": 100 if datos_completos else 40,
        "ok": datos_completos,
        "sugerencia": "" if datos_completos else "Faltan datos basicos (EPS, codigo o valor)",
    })

    tarifa_ok = bool(
        getattr(g, "tarifa_pactada", None)
        or getattr(g, "tarifa_match", None)
        or (g.dictamen and "tarifa" in (g.dictamen or "").lower())
    )
    factores.append({
        "id": "tarifa_pactada",
        "etiqueta": "Tarifa pactada conocida",
        "peso": 20,
        "score": 100 if tarifa_ok else 30,
        "ok": tarifa_ok,
        "sugerencia": "" if tarifa_ok else "Subir el contrato firmado al modulo de Contratos",
    })

    soportes_ok = bool(
        getattr(g, "tiene_soportes", False)
        or (g.dictamen and "soporte" in (g.dictamen or "").lower())
    )
    factores.append({
        "id": "soportes_adjuntos",
        "etiqueta": "Soportes documentales",
        "peso": 25,
        "score": 100 if soportes_ok else 0,
        "ok": soportes_ok,
        "sugerencia": "" if soportes_ok else "Adjuntar historia clinica, RIPS o evolutivas",
    })

    precedente_ok = False
    try:
        from sqlalchemy import and_
        prev = db.query(GlosaRecord).filter(
            and_(
                GlosaRecord.codigo_glosa == g.codigo_glosa,
                GlosaRecord.eps == g.eps,
                GlosaRecord.estado == "GANADA",
                GlosaRecord.id != glosa_id,
            )
        ).limit(1).first()
        precedente_ok = prev is not None
    except Exception:
        pass
    factores.append({
        "id": "precedente_interno",
        "etiqueta": "Precedente interno (glosa ganada similar)",
        "peso": 15,
        "score": 100 if precedente_ok else 0,
        "ok": precedente_ok,
        "sugerencia": "" if precedente_ok else "Sin precedente interno; el dictamen igual procede via normativa",
    })

    normativa_ok = bool(g.dictamen and any(k in (g.dictamen or "").upper() for k in ["ART.", "ARTICULO", "RES.", "LEY", "DECRETO", "SENT."]))
    factores.append({
        "id": "normativa_relevante",
        "etiqueta": "Normativa citada en el dictamen",
        "peso": 15,
        "score": 100 if normativa_ok else 50,
        "ok": normativa_ok,
        "sugerencia": "" if normativa_ok else "El dictamen no cita normativa explicita",
    })

    auditor_ok = bool(getattr(g, "auditor_ok", True))
    factores.append({
        "id": "auditor_ok",
        "etiqueta": "Auditor forense sin discrepancias",
        "peso": 10,
        "score": 100 if auditor_ok else 40,
        "ok": auditor_ok,
        "sugerencia": "" if auditor_ok else "El agente auditor detecto inconsistencias en el caso",
    })

    total_peso = sum(f["peso"] for f in factores)
    total_score = sum(f["score"] * f["peso"] for f in factores) / total_peso

    return {
        "glosa_id": glosa_id,
        "score_total": round(total_score, 1),
        "factores": factores,
        "sugerencias_priorizadas": [
            f["sugerencia"] for f in sorted(factores, key=lambda x: -x["peso"])
            if f["sugerencia"]
        ][:3],
    }
