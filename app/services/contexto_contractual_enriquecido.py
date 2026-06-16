"""Contexto contractual enriquecido para el prompt de la IA.

Auditoría 10-jun-2026 — la "otra IA" producía dictámenes radicables
9/10 porque su prompt incluía:
  - CUPS específico detectado en la glosa + tarifa pactada + modalidad
  - NIT de las partes, número de contrato, proceso SECOP, fechas, plazo
  - Cláusulas POR FAMILIA con parágrafo y página
  - Doctrina del régimen especial (DMBUG/sanidad militar, FOMAG, PPL, ARL)
  - Templates de soportes específicos por familia/CUPS
  - Detector de error del auditor (denominación equivocada)

Este módulo construye ese bloque enriquecido a partir de:
  - ContratoRecord (metadatos del contrato — NIT, SECOP, fechas)
  - ClausulaContrato (cláusulas literales con parágrafo y página)
  - TarifaContratadaRecord (CUPS pactado → modalidad + valor)
  - Catálogo de Manual Único (Res. 2284/2023)

El call site (glosa_service.analizar) lo invoca y lo concatena al user
prompt. Si falta cualquier dato, degrada silenciosamente — el dictamen
sale sin ese bloque pero la pipeline sigue.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("motor_glosas.contexto_contractual")

# Patrones CUPS — los códigos institucionales del HUS pueden tener letras
# (ej. 39143A-4) y los CUPS oficiales son 6 dígitos. Aceptamos ambos.
_PAT_CUPS = re.compile(r"\b(\d{6}|\d{2,5}[A-Z]-?\d{1,4}|FMQ\d{3,6}|FMO\d{3,6})\b")

# ── Exclusiones de candidatos CUPS (12-jun-2026, ronda 2) ─────────────
# Evidencia de producción: el dictamen citó "CUPS 2026-04" (era la fecha
# 2026-04-15) y "CUPS HUS0000522871" (era el número de FACTURA). Un CUPS
# falso en el dictamen le regala a la EPS la ratificación por
# inconsistencia. Ningún candidato que parezca fecha, año o factura puede
# pasar como CUPS.
_PAT_FECHA_COMO_CUPS = re.compile(r"^\d{4}-\d{1,2}(?:-\d{1,2})?$")
_PAT_ANIO_COMO_CUPS = re.compile(r"^(?:19|20)\d{2}$")
_PAT_FECHAS_EN_TEXTO = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b")
# Ronda 3 (16-jun-2026): "Verificar radicado 20260511" → la IA lo escribió
# como CUPS. yyyymmdd: año 19xx/20xx + mes 01-12 + día 01-31, 8 dígitos
# pegados sin separadores. NO conflictúa con CUPS reales (6-7 dígitos).
_PAT_FECHA_YYYYMMDD_COMO_CUPS = re.compile(
    r"^(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])$"
)
_PREFIJOS_FACTURA = ("HUS", "FE", "FAC")


def es_cups_descartable(candidato: str, texto: str = "") -> bool:
    """True si el candidato NO debe usarse como CUPS:

    (a) parece fecha (2026-04, 2026-04-15),
    (b) empieza por prefijo de factura (HUS/FE/FAC) seguido de dígitos,
    (c) es un año suelto (19xx/20xx),
    (d) aparece dentro de una fecha del texto (el "2026-04" capturado del
        "2026-04-15" de la glosa), o
    (e) parece fecha yyyymmdd pegada (20260511 = 11/05/2026).

    Helper compartido: lo usan _extraer_cups_del_texto (acá) y el fallback
    de extracción de CUPS en glosa_service.
    """
    cu = (candidato or "").strip().upper()
    if not cu:
        return True
    if _PAT_FECHA_COMO_CUPS.match(cu) or _PAT_ANIO_COMO_CUPS.match(cu):
        return True
    if _PAT_FECHA_YYYYMMDD_COMO_CUPS.match(cu):
        return True
    for pref in _PREFIJOS_FACTURA:
        # "HUS0000522871" sí; "FMQ6296" no (FM* es código institucional válido).
        if cu.startswith(pref) and len(cu) > len(pref) and cu[len(pref)].isdigit():
            return True
    if texto:
        for m in _PAT_FECHAS_EN_TEXTO.finditer(texto):
            if cu in m.group(0):
                return True
    return False


# Denominaciones que la auditoría suele equivocar (variantes con typo o
# confusión por similitud léxica). Al detectar el patrón, el inyector
# agrega una instrucción para que la IA corrija el nombre del servicio.
_DENOMINACIONES_ERRADAS = {
    "BETA 2 MACROGLOBULINA": "BETA 2 GLICOPROTEINA",
    "BETA 2 MICROGLOBULINA": "BETA 2 GLICOPROTEINA",
    "CRITULINA": "PEPTIDO CICLICO CITRULINADO (CCP)",
}


@dataclass
class ContextoContractual:
    """Estructura del bloque enriquecido que se concatena al user prompt."""

    contrato_metadata: dict = field(default_factory=dict)
    clausulas: list = field(default_factory=list)
    cups_detectados: list = field(default_factory=list)
    tarifas_pactadas: list = field(default_factory=list)
    correcciones_denominacion: list = field(default_factory=list)
    regimen_especial: str = ""
    soportes_recomendados: list = field(default_factory=list)

    def es_vacio(self) -> bool:
        return not (
            self.contrato_metadata
            or self.clausulas
            or self.cups_detectados
            or self.tarifas_pactadas
            or self.correcciones_denominacion
            or self.regimen_especial
        )

    def a_bloque_prompt(self) -> str:
        """Renderiza el contexto como bloque listo para concatenar al user prompt.

        Formato: secciones marcadas con encabezados ASCII para que el modelo
        las separe del resto del prompt y las consulte como datos verificables.
        """
        if self.es_vacio():
            return ""

        partes: list[str] = ["\n═══════════ CONTEXTO CONTRACTUAL VERIFICABLE ═══════════"]

        # 1) Metadatos del contrato (NIT, fecha, SECOP, plazo, anexos)
        md = self.contrato_metadata
        if md:
            lineas = ["\n[CONTRATO VIGENTE — DATOS AUDITABLES]"]
            if md.get("numero_contrato"):
                lineas.append(f"  • Número: {md['numero_contrato']}")
            if md.get("razon_social_eps") or md.get("nit_eps"):
                rs = md.get("razon_social_eps") or md.get("eps_nombre", "")
                nit = md.get("nit_eps") or ""
                lineas.append(f"  • Pagador: {rs}{f' (NIT {nit})' if nit else ''}")
            if md.get("razon_social_ips") or md.get("nit_ips"):
                rs = md.get("razon_social_ips") or "ESE HOSPITAL UNIVERSITARIO DE SANTANDER"
                nit = md.get("nit_ips") or ""
                lineas.append(f"  • Prestador: {rs}{f' (NIT {nit})' if nit else ''}")
            if md.get("fecha_suscripcion"):
                lineas.append(f"  • Fecha de suscripción: {md['fecha_suscripcion']}")
            if md.get("fecha_inicio") and md.get("fecha_fin"):
                lineas.append(
                    f"  • Plazo de ejecución: del {md['fecha_inicio']} al {md['fecha_fin']}"
                )
            if md.get("numero_proceso_secop"):
                p = md["numero_proceso_secop"]
                url = md.get("secop_url", "")
                lineas.append(f"  • Proceso SECOP II: {p}" + (f" ({url})" if url else ""))
            if md.get("objeto_contractual"):
                obj = md["objeto_contractual"][:400]
                lineas.append(f"  • Objeto: {obj}")
            if md.get("modalidades_tarifarias"):
                mods = md["modalidades_tarifarias"]
                if isinstance(mods, list) and mods:
                    lineas.append(f"  • Modalidades tarifarias pactadas: {', '.join(mods)}")
            if md.get("anexos_descripcion"):
                anexos = md["anexos_descripcion"]
                if isinstance(anexos, list) and anexos:
                    lineas.append("  • Anexos integrales del contrato:")
                    for a in anexos[:6]:
                        if isinstance(a, dict):
                            lineas.append(
                                f"      - {a.get('nombre', '')}: {a.get('descripcion', '')}"
                            )
                        else:
                            lineas.append(f"      - {a}")
            partes.append("\n".join(lineas))
            partes.append(
                "\n⚠ USO OBLIGATORIO: cita el número de contrato, NITs y proceso SECOP en el primer "
                "párrafo de identificación del vínculo contractual. Cuando refieras un anexo (tarifas, "
                "dispositivos, medicamentos) menciónalo por su nombre exacto."
            )

        # 2) CUPS detectados + tarifa pactada del catálogo del contrato
        if self.tarifas_pactadas:
            lineas = ["\n[CUPS DEL CASO — TARIFAS PACTADAS EN EL CONTRATO]"]
            for t in self.tarifas_pactadas[:10]:
                cups = t.get("codigo_cups", "")
                desc = (t.get("descripcion") or "")[:120]
                mod = t.get("modalidad", "")
                val = t.get("valor_pactado")
                cod_ips = t.get("codigo_ips") or ""
                linea = f"  • CUPS {cups}: {desc}"
                if cod_ips and cod_ips != cups:
                    linea += f" (código institucional {cod_ips})"
                if mod:
                    linea += f" — modalidad {mod}"
                if val and val > 0:
                    linea += f", valor pactado ${int(val):,}".replace(",", ".")
                lineas.append(linea)
            partes.append("\n".join(lineas))
            partes.append(
                "\n⚠ USO OBLIGATORIO: identifica el servicio por CUPS específico (no 'el CUPS de la factura'); "
                "si la modalidad es TARIFA PROPIA ESE, la reliquidación a SOAT UVB NO procede; si es SOAT "
                "UVB, defiende el ajuste anual conforme al art. 89 Ley 2277/2022."
            )
        elif self.cups_detectados:
            lineas = ["\n[CUPS DETECTADOS EN LA GLOSA — sin pacto verificable en BD]"]
            for c in self.cups_detectados[:10]:
                lineas.append(f"  • {c}")
            partes.append("\n".join(lineas))

        # 3) Cláusulas del contrato POR FAMILIA con parágrafo y página
        if self.clausulas:
            lineas = ["\n[CLÁUSULAS DEL CONTRATO PARA CITAR LITERALMENTE]"]
            for cl in self.clausulas[:8]:
                num = (cl.get("numero_clausula") or "—").strip()
                titulo = (cl.get("titulo") or "").strip()
                texto = (cl.get("texto_literal") or "").strip()
                pagina = cl.get("pagina")
                if not texto:
                    continue
                if len(texto) > 1200:
                    texto = texto[:1200].rsplit(" ", 1)[0] + " […]"
                pag = f" (pág. {pagina})" if pagina else ""
                tema = cl.get("tema", "")
                tema_tag = f" [{tema}]" if tema else ""
                lineas.append(f"\n  ◇ Cláusula {num}{tema_tag}{pag} — {titulo}")
                lineas.append(f"      «{texto}»")
            partes.append("\n".join(lineas))
            partes.append(
                "\n⚠ USO OBLIGATORIO: cita LITERALMENTE entre comillas la cláusula y/o parágrafo "
                "aplicable. NO inventes cláusulas que no aparezcan arriba — el Quality Gate las cazará "
                "como CITA_LITERAL_FALSA y la respuesta se regenerará."
            )

        # 4) Régimen especial (DMBUG/sanidad militar, FOMAG, PPL, ARL)
        if self.regimen_especial:
            partes.append(f"\n[RÉGIMEN ESPECIAL APLICABLE]\n{self.regimen_especial}")

        # 5) Corrección de denominación cuando la auditoría confunde servicios
        if self.correcciones_denominacion:
            lineas = ["\n[ERRORES DEL AUDITOR DETECTADOS — corrige el nombre del servicio]"]
            for c in self.correcciones_denominacion:
                lineas.append(
                    f"  • La auditoría dice '{c['equivocado']}' pero el servicio facturado es '{c['correcto']}'. "
                    f"En el primer párrafo aclara que se trata de exámenes diferentes."
                )
            partes.append("\n".join(lineas))

        # 6) Soportes a anexar — específicos por familia
        if self.soportes_recomendados:
            lineas = ["\n[SOPORTES QUE DEBES ANEXAR EXPLÍCITAMENTE EN EL DICTAMEN]"]
            for s in self.soportes_recomendados:
                lineas.append(f"  • {s}")
            partes.append("\n".join(lineas))
            partes.append(
                "\n⚠ Cierra el dictamen con una línea 'SE ANEXAN: ...' listando los soportes anteriores."
            )

        # 7) Doctrina general para casos contractuales con agotamiento
        # presupuestal o glosas masivas por "IPS sin contrato".
        if md and any(
            "IPS SIN CONTRATO" in (s or "").upper() for s in [md.get("__hint_motivo", "")]
        ):
            partes.append(
                "\n[DOCTRINA CONTRACTUAL — agotamiento ≠ extinción]\n"
                "Si la EPS objeta como 'IPS SIN CONTRATO' o pretende reliquidar a SOAT por agotamiento "
                "del valor comprometido, defiende con cadena tripartita: (i) la gestión presupuestal y "
                "las apropiaciones son obligación expresa del CONTRATANTE — no del prestador; (ii) los "
                "actos propios del pagador (autorizaciones emitidas, remisiones, uso de su plataforma "
                "SALUD.SIS o equivalente) reconocen la vigencia del vínculo y activan el art. 83 C.P. + "
                "arts. 1602 y 1603 C.C. + art. 871 C.Co.; (iii) en gracia de discusión, AÚN sin contrato "
                "vigente, las atenciones se reconocen a SOAT pleno (Art. 20 Decreto 4747/2007, "
                "compilado en Decreto 780/2016), NUNCA a valores impuestos unilateralmente — so pena de "
                "enriquecimiento sin justa causa de la entidad que recibió y autorizó el servicio."
            )

        partes.append("\n═════════════════════════════════════════════════════════\n")
        return "\n".join(partes)


def _extraer_cups_del_texto(texto: str) -> list[str]:
    """Extrae CUPS / códigos institucionales del texto de la glosa.

    Devuelve lista deduplicada en orden de aparición. Desde la ronda 2
    (12-jun-2026) descarta candidatos que son fechas, años o números de
    factura — ver `es_cups_descartable`.
    """
    if not texto:
        return []
    vistos: list[str] = []
    for m in _PAT_CUPS.finditer(texto):
        cod = m.group(1).upper()
        if es_cups_descartable(cod, texto):
            continue
        if cod not in vistos:
            vistos.append(cod)
    return vistos[:10]


# ── Datos clínicos del enunciado (12-jun-2026, ronda 2) ───────────────
# Evidencia: glosas con "NYHA III, FE 25%, en lista de trasplante", "47
# días UCI por TCE severo" y "Kellgren IV" produjeron dictámenes que NO
# mencionaban ninguno de esos datos — plantilla pura, fácil de ratificar.
# Extractor determinístico (regex, sin NLP) para inyectarlos al prompt
# como bloque imperativo y para el check suave del post_validator.
_PATRONES_DATOS_CLINICOS: tuple[tuple[str, re.Pattern], ...] = (
    ("NYHA", re.compile(r"\bNYHA\s*(?:CLASE\s*)?(?:IV|III|II|I)\b", re.IGNORECASE)),
    (
        "FE",
        re.compile(
            r"\b(?:FE|FEVI|FRACCI[ÓO]N\s+DE\s+EYECCI[ÓO]N)\s*(?:DEL?\s*)?[:=]?\s*\d{1,2}\s*%",
            re.IGNORECASE,
        ),
    ),
    ("GLASGOW", re.compile(r"\b(?:GLASGOW|GCS)\s*[:=]?\s*\d{1,2}(?:\s*/\s*15)?\b", re.IGNORECASE)),
    (
        "KELLGREN",
        re.compile(
            r"\bKELLGREN(?:\s*[-–]\s*LAWRENCE)?\s*(?:GRADO\s*)?(?:IV|III|II|I)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ESTANCIA",
        re.compile(
            r"\b\d{1,3}\s*D[ÍI]AS?\s+(?:DE\s+|EN\s+)?(?:UCI|ESTANCIA|HOSPITALIZACI[ÓO]N\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "TRASPLANTE",
        re.compile(r"\bLISTA\s+DE\s+(?:ESPERA\s+(?:DE|PARA)\s+)?TRASPLANTE\b", re.IGNORECASE),
    ),
    ("TCE", re.compile(r"\bTCE\s+(?:SEVERO|MODERADO|LEVE)\b", re.IGNORECASE)),
)


def extraer_datos_clinicos(texto: str) -> list[str]:
    """Extrae datos clínicos concretos del texto de la glosa.

    Devuelve frases normalizadas (MAYÚSCULAS, espacios colapsados) en orden
    de aparición, ej. ["NYHA III", "FE 25%", "LISTA DE TRASPLANTE"].
    Solo patrones taxativos — nada de inferencia: si no matchea, no existe.
    """
    if not texto:
        return []
    hallados: list[tuple[int, str]] = []
    vistos: set[str] = set()
    for _nombre, pat in _PATRONES_DATOS_CLINICOS:
        for m in pat.finditer(texto):
            dato = re.sub(r"\s+", " ", m.group(0)).strip().upper()
            if dato not in vistos:
                vistos.add(dato)
                hallados.append((m.start(), dato))
    return [d for _, d in sorted(hallados)]


def bloque_datos_clinicos(texto: str) -> str:
    """Bloque listo para el user prompt con los datos clínicos del caso.

    Cadena vacía si no se detectó ninguno (no perturba el prompt base).
    """
    datos = extraer_datos_clinicos(texto)
    if not datos:
        return ""
    lineas = "\n".join(f"  • {d}" for d in datos)
    return (
        "\n[DATOS CLÍNICOS DEL CASO — ÚSALOS EN LA ARGUMENTACIÓN]\n"
        f"{lineas}\n"
        "⚠ OBLIGATORIO: INCORPORA estos datos LITERALMENTE en la argumentación — "
        "son la prueba de la pertinencia del servicio. Un dictamen que ignora los "
        "datos clínicos del caso es plantilla y será rechazado.\n"
    )


def _detectar_correcciones_denominacion(texto_glosa: str) -> list[dict]:
    """Detecta cuando la auditoría usa una denominación que el sistema sabe
    equivocada (ej. 'BETA 2 MACROGLOBULINA' en vez de 'BETA 2 GLICOPROTEINA').

    Solo dispara para confusiones conocidas — no extrapola.
    """
    correcciones: list[dict] = []
    tu = (texto_glosa or "").upper()
    for equivocado, correcto in _DENOMINACIONES_ERRADAS.items():
        if equivocado in tu and correcto not in tu:
            correcciones.append({"equivocado": equivocado, "correcto": correcto})
    return correcciones


def _soportes_por_familia(familia: str, cups: list[str]) -> list[str]:
    """Lista de soportes específicos a anexar según familia (no genérica).

    Auditoría 10-jun-2026: la "otra IA" pide soportes específicos por caso
    ("informes de cada procedimiento con fecha/hora", "descripción quirúrgica
    + hoja de gastos + sticker del implante"), no la lista genérica
    "RIPS+HC+factura". Esto blinda contra ratificación.
    """
    fam = (familia or "").upper()
    s: list[str] = []
    if fam == "SO":
        s = [
            "Historia clínica institucional con folios completos",
            "RIPS radicados (JSON Res. 2275/2023)",
            "Factura electrónica de venta + CUV MinSalud",
            "Anexo técnico nº 5 Res. 3047/2008 cumplido",
        ]
    elif fam == "TA":
        s = [
            "Anexo tarifario del contrato vigente (cláusula segunda, parágrafos 1 y 4)",
            "Comprobante de tarifa SOAT vigente (Circular 047/2025 MinSalud, UVB 2026)",
            "Resolución tarifaria institucional ESE HUS (054/2026 + 124/2026)",
        ]
    elif fam == "AU":
        s = [
            "Autorización/remisión radicada en plataforma del pagador",
            "Soporte clínico del servicio (criterios de urgencia o pertinencia electiva)",
            "Acuse de recibo de la solicitud (si aplica silencio administrativo positivo)",
        ]
    elif fam in ("CL", "PE"):
        s = [
            "Historia clínica con evolución del médico tratante y CIE-10/CUPS coherentes",
            "Órdenes médicas con justificación clínica del procedimiento",
            "Evidencia de criterio del tratante (lex artis)",
        ]
    elif fam == "FA":
        s = [
            "Descripción operatoria / informe del procedimiento por evento",
            "Hoja de gastos quirúrgicos con sticker / referencia del insumo",
            "Historia clínica con momentos asistenciales diferenciados",
        ]
    elif fam == "IN":
        s = [
            "Hoja de gastos quirúrgicos con referencia/sticker del implante",
            "Descripción quirúrgica con detalle del material utilizado",
            "Cláusula del contrato / Anexo de dispositivos médicos con código pactado",
        ]
    elif fam == "ME":
        s = [
            "Fórmula médica del tratante con CUM",
            "Hoja de administración de medicamentos firmada",
            "Constancia MIPRES si NoPBS / Régimen especial",
        ]
    elif fam == "CO":
        s = [
            "Cláusula primera (objeto) y de cobertura integral del contrato",
            "Historia clínica que acredita la pertinencia clínica",
            "Norma de inclusión PBS / régimen especial aplicable",
        ]
    # CUPS específicos siempre como soporte
    if cups:
        s.append(f"Referencia explícita al CUPS {', '.join(cups[:3])} en el anexo tarifario")
    return s


def _regimen_especial_texto(eps: str, contrato_md: dict) -> str:
    """Construye el bloque de régimen especial según la EPS/entidad."""
    if not eps:
        return ""
    eu = eps.upper()
    if any(
        k in eu
        for k in (
            "DISPENSARIO",
            "DIGSA",
            "DMBUG",
            "SANIDAD",
            "MILITAR",
            "POLICIA",
            "POLICÍA",
            "EJERCITO",
            "EJÉRCITO",
            "ARMADA",
            "FUERZA AEREA",
            "FUERZA AÉREA",
        )
    ):
        return (
            "Régimen especial Subsistema de Salud de las Fuerzas Militares y de la Policía Nacional:\n"
            "  • Decreto 1795 de 2000 (régimen especial SSMP)\n"
            "  • Acuerdo 002 del 27 de abril de 2001 (Consejo Superior de Salud FF.MM. y Policía Nacional)\n"
            "  • Plan de Servicios de Sanidad Militar y Policial (cobertura integral)\n"
            "  • NO cites Ley 100/1993 como fuente principal; tampoco T-760/2008 (no aplica).\n"
            "  • Cuando la entidad sea un Dispensario Médico (DMBUG), refiérete como 'CONTRATANTE'\n"
            "    o 'ENTIDAD PAGADORA del Subsistema de Salud Militar', NO como 'EPS'."
        )
    if "FOMAG" in eu:
        return (
            "Régimen especial Magisterio (FOMAG):\n"
            "  • Decreto 3752 de 2003 y normas concordantes.\n"
            "  • Refiere FOMAG como 'Fondo' y el operador como 'Operador del Magisterio'."
        )
    if "PPL" in eu or "RECLU" in eu:
        return (
            "Régimen especial Población Privada de la Libertad (PPL):\n"
            "  • Resolución 5159 de 2015 y Ley 1709 de 2014 (atención en salud para PPL)."
        )
    if any(k in eu for k in ("POSITIVA", "ARL", "AURORA", "BOLIVAR", "BOLÍVAR", "SURA ARL")):
        return (
            "Régimen Aseguradora — Riesgos Laborales / SOAT:\n"
            "  • Para ARL: Decreto-Ley 1295/1994 + Decreto 1072/2015 + Ley 1562/2012.\n"
            "  • Para SOAT: Manual Tarifario SOAT 2026 (UVB; Circular 047/2025 MinSalud, art. 89 Ley 2277/2022).\n"
            "  • Defensa: tarifa SOAT vigente + obligación de pago por el hecho generador."
        )
    return ""


def construir_contexto(
    *,
    eps: str,
    codigo_glosa: str,
    texto_glosa: str,
    familia: str = "",
) -> ContextoContractual:
    """Punto de entrada — junta CUPS, tarifas, cláusulas y régimen especial.

    Args:
        eps: nombre de la EPS / entidad pagadora (normalizado upper).
        codigo_glosa: AA#### o vacío para texto libre.
        texto_glosa: el texto crudo de la objeción.
        familia: prefijo del código (TA/SO/AU/CO/FA/CL/IN/ME) si ya se conoce.

    Returns:
        ContextoContractual listo para `.a_bloque_prompt()`. Si la BD no
        está disponible, devuelve un contexto parcial pero útil (régimen,
        soportes, correcciones — todo lo que no depende de BD).
    """
    ctx = ContextoContractual()
    eps_norm = (eps or "").strip().upper()

    # 1) Régimen especial (no depende de BD) — siempre disponible
    contrato_md_para_regimen: dict = {}
    ctx.regimen_especial = _regimen_especial_texto(eps_norm, contrato_md_para_regimen)

    # 2) CUPS detectados en el texto (no depende de BD)
    ctx.cups_detectados = _extraer_cups_del_texto(texto_glosa)

    # 3) Correcciones de denominación (no depende de BD)
    ctx.correcciones_denominacion = _detectar_correcciones_denominacion(texto_glosa)

    # 4) Soportes por familia (no depende de BD)
    fam = (familia or (codigo_glosa[:2] if codigo_glosa else "")).upper()
    ctx.soportes_recomendados = _soportes_por_familia(fam, ctx.cups_detectados)

    # 5-7) Metadatos del contrato + cláusulas + tarifas pactadas (BD)
    try:
        from app.database import SessionLocal
        from app.models.db import ClausulaContrato, ContratoRecord, TarifaContratadaRecord

        db = SessionLocal()
        try:
            # 5) Metadatos del contrato
            contrato = db.query(ContratoRecord).filter(ContratoRecord.eps == eps_norm).first()
            if contrato:
                anexos = None
                modalidades = None
                try:
                    anexos = (
                        json.loads(contrato.anexos_descripcion)
                        if contrato.anexos_descripcion
                        else None
                    )
                except Exception:
                    anexos = None
                try:
                    modalidades = (
                        json.loads(contrato.modalidades_tarifarias)
                        if contrato.modalidades_tarifarias
                        else None
                    )
                except Exception:
                    modalidades = None

                def _fecha(d: Optional[datetime]) -> str:
                    return d.strftime("%d/%m/%Y") if isinstance(d, datetime) else ""

                ctx.contrato_metadata = {
                    "eps_nombre": eps_norm,
                    "numero_contrato": contrato.numero_contrato,
                    "nit_eps": contrato.nit_eps,
                    "nit_ips": contrato.nit_ips,
                    "razon_social_eps": contrato.razon_social_eps,
                    "razon_social_ips": contrato.razon_social_ips,
                    "numero_proceso_secop": contrato.numero_proceso_secop,
                    "secop_url": contrato.secop_url,
                    "fecha_suscripcion": _fecha(contrato.fecha_suscripcion),
                    "fecha_inicio": _fecha(contrato.fecha_inicio),
                    "fecha_fin": _fecha(contrato.fecha_fin),
                    "objeto_contractual": contrato.objeto_contractual,
                    "anexos_descripcion": anexos,
                    "modalidades_tarifarias": modalidades,
                    "__hint_motivo": texto_glosa,
                }
                # Re-evaluar régimen especial con los datos del contrato
                if not ctx.regimen_especial:
                    ctx.regimen_especial = _regimen_especial_texto(eps_norm, ctx.contrato_metadata)

            # 6) Cláusulas POR FAMILIA — sin limit, agrupadas por número
            # (la "otra IA" cita Parágrafos 1, 3, 4 y 5 de Cláusula 2ª — el
            # sistema viejo solo traía 5 cláusulas mezcladas).
            temas_relevantes = {
                "TA": ["TA", "NN"],
                "SO": ["SO", "NN"],
                "AU": ["AU", "NN"],
                "CO": ["CO", "NN"],
                "CL": ["CO", "CL", "NN"],
                "PE": ["CO", "CL", "NN"],
                "FA": ["FA", "NN"],
                "IN": ["FA", "TA", "IN", "NN"],
                "ME": ["FA", "CO", "ME", "NN"],
            }.get(fam, ["NN", "TA", "SO", "FA", "CO"])

            q = (
                db.query(ClausulaContrato)
                .filter(ClausulaContrato.eps == eps_norm)
                .filter(ClausulaContrato.tema.in_(temas_relevantes))
                .order_by(ClausulaContrato.numero_clausula, ClausulaContrato.id)
                .limit(8)
            )
            ctx.clausulas = [
                {
                    "numero_clausula": cl.numero_clausula or "",
                    "tema": cl.tema or "",
                    "titulo": cl.titulo or "",
                    "texto_literal": cl.texto_literal or "",
                    "pagina": cl.pagina,
                }
                for cl in q.all()
            ]

            # 7) Tarifas pactadas para los CUPS detectados
            if ctx.cups_detectados:
                tarifas: list[dict] = []
                for cups in ctx.cups_detectados:
                    fila = (
                        db.query(TarifaContratadaRecord)
                        .filter(
                            TarifaContratadaRecord.activa == 1,
                            TarifaContratadaRecord.eps.ilike(f"%{eps_norm}%"),
                        )
                        .filter(
                            (TarifaContratadaRecord.codigo_cups == cups)
                            | (TarifaContratadaRecord.codigo_ips == cups)
                        )
                        .order_by(TarifaContratadaRecord.creado_en.desc())
                        .first()
                    )
                    if fila:
                        tarifas.append(
                            {
                                "codigo_cups": fila.codigo_cups,
                                "codigo_ips": fila.codigo_ips,
                                "descripcion": fila.descripcion,
                                "modalidad": fila.modalidad,
                                "valor_pactado": fila.valor_pactado,
                            }
                        )
                ctx.tarifas_pactadas = tarifas
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[CONTEXTO-CONTRACTUAL] BD no disponible o consulta falló: {e}")

    return ctx
