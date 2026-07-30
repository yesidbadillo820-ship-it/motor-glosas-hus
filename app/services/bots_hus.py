"""Todos los bots del hospital, administrados desde la plataforma.

Hasta hoy convivían tres mundos: los conversores que corren en la nube
(Centro de Automatización), los bots de portal que corren en el PC del HUS
por la cola de Lotes (COOSALUD, SIMED), y una veintena de robots de doble
clic que cada auditor corría a mano sin que el sistema se enterara.

Este registro los declara TODOS. Cada bot dice dónde corre y cómo se
dispara:

  - "nube"   → es una ficha del Centro de Automatización (archivo entra,
               archivo sale, corre en el servidor).
  - "lotes"  → usa la cola de Lotes existente (COOSALUD / SIMED).
  - "cola"   → se encola como TrabajoBot y el agente del PC del HUS lo
               reclama, lo corre y reporta el resultado.
  - "manual" → todavía es de doble clic en el PC; la plataforma lo muestra
               con su instrucción exacta mientras pasa a la cola.

Agregar un bot es agregar una ficha acá: la pantalla, la API y el agente
del PC lo recogen solos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BotHUS:
    id: str
    nombre: str
    sistema: str  # COOSALUD, SIMED, DGH, ADRES, PDF, XML…
    que_hace: str
    donde_corre: str  # "nube" | "pc_hus"
    disparo: str  # "automatizacion" | "lotes" | "cola" | "manual"
    archivo: str = ""  # módulo/cmd en tools/
    automatizacion_id: str = ""  # si disparo == "automatizacion"
    comando_pc: str = ""  # cómo lo corre el agente del PC (si "cola")
    parametros_ayuda: str = ""  # qué parámetros espera (texto para el auditor)
    riesgo: str = ""  # advertencias (piloto de 1 factura, CUV, etc.)
    grupo: str = "Portales"

    def como_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "sistema": self.sistema,
            "que_hace": self.que_hace,
            "donde_corre": self.donde_corre,
            "disparo": self.disparo,
            "archivo": self.archivo,
            "automatizacion_id": self.automatizacion_id,
            "parametros_ayuda": self.parametros_ayuda,
            "riesgo": self.riesgo,
            "grupo": self.grupo,
        }


def _b(**kw) -> BotHUS:
    return BotHUS(**kw)


CATALOGO_BOTS: tuple[BotHUS, ...] = (
    # ── Portales de EPS (PC del HUS) ─────────────────────────────────────
    _b(
        id="coosalud-responder",
        nombre="Responder glosas en COOSALUD",
        sistema="COOSALUD",
        que_hace="Carga las respuestas del lote al portal VCO de COOSALUD, factura por factura, con evidencia.",
        donde_corre="pc_hus",
        disparo="lotes",
        archivo="tools/responder_glosas_coosalud.py",
        riesgo="Correr piloto de 1 factura antes del masivo.",
    ),
    _b(
        id="coosalud-verificar",
        nombre="Verificar radicación COOSALUD",
        sistema="COOSALUD",
        que_hace="Recorre el portal y confirma qué facturas del lote quedaron radicadas de verdad.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/verificar_glosas_coosalud.py",
        comando_pc="py tools/verificar_glosas_coosalud.py",
    ),
    _b(
        id="simed-responder",
        nombre="Responder glosas en SIMED (Dispensario)",
        sistema="SIMED",
        que_hace="Carga las respuestas del lote al SIMED del Dispensario Médico.",
        donde_corre="pc_hus",
        disparo="lotes",
        archivo="tools/responder_glosas_simed.py",
        riesgo="Piloto de 1 factura antes del masivo.",
    ),
    _b(
        id="simed-soportes",
        nombre="Cargar soportes en SIMED",
        sistema="SIMED",
        que_hace="Sube los PDF de soporte de cada factura al SIMED.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/cargar_soportes_simed.py",
        comando_pc="py tools/cargar_soportes_simed.py",
    ),
    _b(
        id="fomag-responder",
        nombre="Responder glosas FOMAG",
        sistema="FOMAG",
        que_hace="Carga las respuestas al portal del FOMAG.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/responder_glosas_fomag.py",
        comando_pc="py tools/responder_glosas_fomag.py",
        riesgo="Piloto de 1 factura antes del masivo.",
    ),
    _b(
        id="mutual-responder",
        nombre="Responder glosas MUTUAL SER",
        sistema="MUTUAL SER",
        que_hace="Carga las respuestas al portal de MUTUAL SER.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/responder_glosas_mutual_ser.py",
        comando_pc="py tools/responder_glosas_mutual_ser.py",
        riesgo="Piloto de 1 factura antes del masivo.",
    ),
    _b(
        id="mutual-extraer",
        nombre="Extraer respuestas MUTUAL SER",
        sistema="MUTUAL SER",
        que_hace="Baja del portal las respuestas ya radicadas para archivarlas.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/extraer_respuestas_glosa_mutualser.py",
        comando_pc="py tools/extraer_respuestas_glosa_mutualser.py",
    ),
    # ── DGH (programa de escritorio del hospital) ────────────────────────
    _b(
        id="dgh-responder",
        nombre="Responder glosas en DGH",
        sistema="DGH",
        que_hace="Registra las respuestas en Dinámica Gerencial (el ERP de escritorio del hospital).",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/responder_glosas_dgh.py",
        comando_pc="py tools/responder_glosas_dgh.py",
        grupo="DGH",
    ),
    _b(
        id="dgh-tramites",
        nombre="Trámites masivos en DGH",
        sistema="DGH",
        que_hace="Registra el trámite de glosas aceptadas en DGH desde el Excel de cargue.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/respuesta_tramites_dgh.py",
        comando_pc="py tools/respuesta_tramites_dgh.py",
        grupo="DGH",
    ),
    _b(
        id="dgh-corregir",
        nombre="Corregir errores de cargue DGH",
        sistema="DGH",
        que_hace="Repara los registros que DGH rechazó en un cargue anterior.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/corregir_errores_dgh.py",
        comando_pc="py tools/corregir_errores_dgh.py",
        grupo="DGH",
    ),
    # ── Radicación y facturación ─────────────────────────────────────────
    _b(
        id="radicador",
        nombre="Radicador de facturación",
        sistema="FACTURACIÓN",
        que_hace="Radica facturas en el portal de la entidad con sus soportes.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/radicar_facturacion.py",
        comando_pc="py tools/radicar_facturacion.py",
        grupo="Radicación",
    ),
    _b(
        id="explorador-radicacion",
        nombre="Explorador de radicación",
        sistema="FACTURACIÓN",
        que_hace="Recorre el share y arma el tablero de qué está radicado y qué no.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/explorador_radicacion.py",
        comando_pc="py tools/explorador_radicacion.py",
        grupo="Radicación",
    ),
    _b(
        id="verificar-radicacion",
        nombre="Verificar radicación",
        sistema="FACTURACIÓN",
        que_hace="Confirma contra el portal qué facturas quedaron radicadas.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/verificar_radicacion.py",
        comando_pc="py tools/verificar_radicacion.py",
        grupo="Radicación",
    ),
    # ── ADRES / FURIPS ───────────────────────────────────────────────────
    _b(
        id="adres-furips",
        nombre="Validador FURIPS (ADRES)",
        sistema="ADRES",
        que_hace="Valida reclamaciones FURIPS 1/2 contra la Circular 022/2023 y cruza con soportes.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/adres/validar_furips.py",
        comando_pc="py tools/adres/validar_furips.py",
        grupo="ADRES",
    ),
    _b(
        id="adres-baja-cartera",
        nombre="Informe de baja de cartera",
        sistema="ADRES",
        que_hace="Genera el informe Word + Excel de baja de facturas (Res. 577/2019), con OCR.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/generar_informe_baja_cartera.py",
        comando_pc="py tools/generar_informe_baja_cartera.py",
        grupo="ADRES",
    ),
    _b(
        id="nueva-eps-de4401",
        nombre="Informe DE4401 NUEVA EPS (XML DIAN)",
        sistema="NUEVA EPS",
        que_hace="Completa el informe de devoluciones DE4401 leyendo los XML DIAN del repositorio.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/completar_informe_xml_dian.py",
        comando_pc="py tools/completar_informe_xml_dian.py",
        grupo="Radicación",
    ),
    # ── Notas crédito del Dispensario ────────────────────────────────────
    _b(
        id="notas-cuv",
        nombre="Verificar CUV de notas crédito",
        sistema="SIMED",
        que_hace="Valida el CUV de cada nota ANTES de cargarla: el portal acepta CUV inválidos pero quedan mal radicadas.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/verificar_cuv_notas.py",
        comando_pc="py tools/verificar_cuv_notas.py",
        riesgo="OBLIGATORIO antes de cargar notas al SIMED.",
        grupo="Notas crédito",
    ),
    _b(
        id="notas-organizar",
        nombre="Renombrar y organizar notas crédito",
        sistema="SIMED",
        que_hace="Renombra, organiza por acta y deja listas las notas crédito para el cargue.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/renombrar_y_organizar_notas.py",
        comando_pc="py tools/renombrar_y_organizar_notas.py",
        grupo="Notas crédito",
    ),
    # ── Herramientas de PC que eran de doble clic (ahora por la cola) ────
    _b(
        id="unir-pdfs",
        nombre="Unir PDFs por carpeta",
        sistema="PDF",
        que_hace="Une los PDF de cada carpeta en un solo archivo por carpeta.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/unir_pdfs_carpetas.py",
        comando_pc="py tools/unir_pdfs_carpetas.py",
        parametros_ayuda="carpeta: ruta de la carpeta raíz en el PC/share",
        grupo="Archivos",
    ),
    _b(
        id="pdf-a-cmd",
        nombre="PDF → CMD (por carpeta)",
        sistema="PDF",
        que_hace="Convierte los PDF de una carpeta al formato CMD que pide el portal.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/pdf_a_cmd.py",
        comando_pc="py tools/pdf_a_cmd.py",
        grupo="Archivos",
    ),
    _b(
        id="comprimir-zip",
        nombre="Comprimir a ZIP",
        sistema="PDF",
        que_hace="Comprime carpetas de soportes a ZIP listos para subir.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/comprimir_zip.py",
        comando_pc="py tools/comprimir_zip.py",
        grupo="Archivos",
    ),
    _b(
        id="partir-zip",
        nombre="Partir ZIP en partes de 30 MB",
        sistema="PDF",
        que_hace="Parte un ZIP grande en partes que los portales sí aceptan.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/partir_zip.py",
        comando_pc="py tools/partir_zip.py",
        grupo="Archivos",
    ),
    _b(
        id="organizar-correos",
        nombre="Organizar correos de glosas",
        sistema="CORREO",
        que_hace="Clasifica los correos exportados de glosas por pagador y factura.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/organizar_correos_glosas.py",
        comando_pc="py tools/organizar_correos_glosas.py",
        grupo="Archivos",
    ),
    _b(
        id="cruzar-glosas",
        nombre="Cruzar glosas con XML",
        sistema="XML",
        que_hace="Cruza el Excel de glosas contra los XML DIAN y marca diferencias.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/cruzar_glosas_xml.py",
        comando_pc="py tools/cruzar_glosas_xml.py",
        grupo="Informes",
    ),
    _b(
        id="semaforo",
        nombre="Semáforo de vencimientos",
        sistema="CARTERA",
        que_hace="Genera el semáforo de glosas por vencer del área.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/semaforo_vencimientos.py",
        comando_pc="py tools/semaforo_vencimientos.py",
        grupo="Informes",
    ),
    _b(
        id="tablero-cartera",
        nombre="Tablero de cartera",
        sistema="CARTERA",
        que_hace="Arma el tablero HTML de cartera con los cortes del área.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/tablero_cartera.py",
        comando_pc="py tools/tablero_cartera.py",
        grupo="Informes",
    ),
    _b(
        id="informe-gerencia",
        nombre="Informe de gerencia",
        sistema="CARTERA",
        que_hace="Genera el informe ejecutivo mensual para gerencia.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/informe_gerencia.py",
        comando_pc="py tools/informe_gerencia.py",
        grupo="Informes",
    ),
    _b(
        id="auditar-dev-eps",
        nombre="Auditar devoluciones EPS",
        sistema="CARTERA",
        que_hace="Audita el archivo de devoluciones que manda la EPS y señala inconsistencias.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/auditar_devoluciones_eps.py",
        comando_pc="py tools/auditar_devoluciones_eps.py",
        grupo="Informes",
    ),
    _b(
        id="buscar-factura",
        nombre="Buscar factura en el share",
        sistema="FACTURACIÓN",
        que_hace="Encuentra en el share todos los archivos de una factura.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/buscar_facturas.py",
        comando_pc="py tools/buscar_facturas.py",
        parametros_ayuda="factura: número HUS a buscar",
        grupo="Radicación",
    ),
    _b(
        id="glosas-aceptadas",
        nombre="Completar trámite de glosas aceptadas",
        sistema="DGH",
        que_hace="Arma el Excel de trámite de las glosas aceptadas para el cargue en DGH.",
        donde_corre="pc_hus",
        disparo="cola",
        archivo="tools/completar_tramite_glosas_aceptadas.py",
        comando_pc="py tools/completar_tramite_glosas_aceptadas.py",
        grupo="DGH",
    ),
    # ── Conversores que ya corren en la nube ─────────────────────────────
    _b(
        id="savia-erp",
        nombre="Glosas de SAVIA SALUD → ERP",
        sistema="SAVIA",
        que_hace="Convierte el Excel de SAVIA al formato de 16 columnas del ERP.",
        donde_corre="nube",
        disparo="automatizacion",
        automatizacion_id="objeciones-savia",
        grupo="Conversores",
    ),
    _b(
        id="vco-erp",
        nombre="Glosas de VCO → ERP",
        sistema="VCO",
        que_hace="Convierte el consolidado de VCO al formato del ERP.",
        donde_corre="nube",
        disparo="automatizacion",
        automatizacion_id="objeciones-vco",
        grupo="Conversores",
    ),
    _b(
        id="emssanar-erp",
        nombre="Glosas de EMSSANAR (PDF) → ERP",
        sistema="EMSSANAR",
        que_hace="Lee el PDF de EMSSANAR y arma el Excel de cargue.",
        donde_corre="nube",
        disparo="automatizacion",
        automatizacion_id="objeciones-emssanar",
        grupo="Conversores",
    ),
    _b(
        id="xml-facturas",
        nombre="Revisar XML de facturas",
        sistema="XML",
        que_hace="Valida los XML DIAN y arma el Excel con CUFE, NIT, valor y fecha.",
        donde_corre="nube",
        disparo="automatizacion",
        automatizacion_id="revisar-xml",
        grupo="Conversores",
    ),
    _b(
        id="excel-csv",
        nombre="Excel → CSV",
        sistema="CSV",
        que_hace="Convierte a CSV para los portales que lo exigen.",
        donde_corre="nube",
        disparo="automatizacion",
        automatizacion_id="excel-a-csv",
        grupo="Conversores",
    ),
)

_POR_ID = {b.id: b for b in CATALOGO_BOTS}


def obtener(bot_id: str) -> BotHUS | None:
    return _POR_ID.get(bot_id)


def catalogo() -> list[BotHUS]:
    return list(CATALOGO_BOTS)


def grupos() -> dict[str, list[dict[str, Any]]]:
    salida: dict[str, list[dict[str, Any]]] = {}
    for b in CATALOGO_BOTS:
        salida.setdefault(b.grupo, []).append(b.como_dict())
    return salida
