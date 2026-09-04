"""Reglas deterministas para las contradicciones que un modelo de lenguaje no
puede "razonar" solo (casos F–O, 02-09-2026).

Principio del proyecto: **la IA redacta, Python decide**. Acá viven las reglas
que leen el texto de la glosa y deciden —sin llamar al modelo— qué NO se puede
afirmar y qué debe responderse, para que el dictamen no se cegue con el código
inicial, no invente leyes, no capture mal los números y no defienda imposibles.

Cada función es pura (texto → dato) para poder probarla con `pytest` sin montar
el motor. El motor (`glosa_service.analizar`) las llama en los puntos de
enganche y arma el dictamen con lo que devuelven.

Casos que cubre:
  F  Contradicción ciega (código de tarifa, texto que reclama soportes).
  G  Ley inventada por la entidad (no se legitima; se argumenta con normas reales).
  H  Cálculo por porcentajes ("el 25 % del valor total"): Python calcula.
  I  Paradoja biológica (procedimiento incompatible con el sexo registrado).
  J  Ratificación camuflada (el texto dice "se ratifica"/"respuesta a conciliación").
  K  Texto basura (&&& /// _ ::: $$$): se limpia antes de extraer.
  L  Fechas invertidas (alta anterior al ingreso).
  M  Doble pagador: tope SOAT no agotado con matemática correcta en el texto.
  N  Alto costo sin MIPRES: se exige el formato como anexo obligatorio.
  O  Falso positivo financiero: glosado $0 → informativa, sin defensa.
"""

from __future__ import annotations

import datetime
import re
import unicodedata


# ─────────────────────────── utilidades ───────────────────────────
def _sin_tildes_mayus(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def _num_cop(s: str) -> float:
    """Convierte un número colombiano ('34.600.000', '$10.000.000') a float."""
    try:
        from app.utils.moneda import parse_valor_cop

        return float(parse_valor_cop(s) or 0.0)
    except Exception:
        try:
            return float(re.sub(r"[^\d]", "", s or "0") or 0)
        except Exception:
            return 0.0


def _fmt_cop(n: float) -> str:
    return "$" + f"{int(round(n)):,}".replace(",", ".")


# ─────────────────────────── Caso K: texto basura ───────────────────────────
_RE_RUIDO_JUNK = re.compile(r"[#&*=~^]+")


def limpiar_ruido_glosa(texto: str) -> str:
    """Quita separadores basura sin tocar lo que sí significa algo.

    Conserva: '|' (encabezado), '$', '%', '.', ',', '-', letras, dígitos,
    un '/' suelto (fechas dd/mm/aaaa) y un ':' suelto (rótulos «VALOR:»).
    Colapsa: corridas de # & * = ~ ^, '//', ':::', '_' (unen campos), '$$$'.

    El caso que lo pidió (Caso K): `&&&GLOSA///FA0301_FACTURA#HUS...` extraía
    «N/A» como código porque `_` es carácter de palabra y rompía el `\\b` del
    regex del código. Tras limpiar queda «GLOSA FA0301 FACTURA HUS...».
    """
    if not texto:
        return texto
    t = _RE_RUIDO_JUNK.sub(" ", texto)
    t = re.sub(r"/{2,}", " ", t)
    t = re.sub(r":{2,}", " ", t)
    t = re.sub(r"_+", " ", t)
    t = re.sub(r"\${2,}", "$", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t


# ─────────────────────────── Caso O: glosado $0 (informativa) ───────────────────────────
_RE_GLOSA_CERO = re.compile(
    r"\b(?:GLOSAD[OA]|OBJETAD[OA]|SE\s+GLOSA|VALOR\s+GLOSAD[OA]|VALOR\s+OBJETAD[OA])\b"
    r"\s*[:=]?\s*\$?\s*0(?:[.,]0+)?\b(?!\s*[.,]?\d)",
    re.IGNORECASE,
)


def glosa_es_informativa_cero(texto: str) -> bool:
    """True cuando el valor glosado/objetado es explícitamente $0.

    Caso O: «GLOSADO $0. ACEPTADO $500.000». El valor en disputa es $0: la
    glosa es informativa y no lleva defensa jurídica ni devolución.
    """
    return bool(_RE_GLOSA_CERO.search(texto or ""))


def parrafo_informativa(codigo: str) -> str:
    cod = codigo if codigo and codigo != "N/A" else "INDICADA EN EL EXPEDIENTE"
    return (
        f"LA OBJECIÓN {cod} ES DE CARÁCTER INFORMATIVO: EL VALOR GLOSADO ES $0 Y EL "
        "VALOR RECONOCIDO SE AUTORIZA PARA PAGO. NO EXISTE SUMA EN DISCUSIÓN NI HECHO "
        "QUE DEBA CONTROVERTIRSE, POR LO QUE ESTA RESPUESTA SE LIMITA A DEJAR "
        "CONSTANCIA DE SU RECIBO. ESE HUS QUEDA ATENTO AL PAGO DEL VALOR RECONOCIDO Y "
        "NO PRESENTA DEFENSA JURÍDICA POR NO HABER GLOSA ECONÓMICA. CUALQUIER "
        "INFORMACIÓN AL CORREO INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


# ─────────────────────────── Caso H: cálculo por porcentaje ───────────────────────────
_RE_PORCENTAJE_DE_TOTAL = re.compile(
    r"(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:DEL?|DE\s+LA|DE\s+EL)?\s*(?:VALOR\s+)?(?:TOTAL|FACTURA)",
    re.IGNORECASE,
)
_RE_BASE_TOTAL = re.compile(
    r"(?:VALOR\s+TOTAL|TOTAL\s+DE\s+LA\s+FACTURA|AUDITA\s+LA\s+FACTURA|FACTURA)"
    r"[^$%]{0,40}?\$\s*([\d][\d.,]{4,})",
    re.IGNORECASE,
)


def valor_glosa_por_porcentaje(texto: str) -> float | None:
    """Si la glosa dice «se glosa el N % del valor total», calcula N % de la base.

    Caso H: «SE AUDITA LA FACTURA POR $10.000.000 … SE GLOSA … EL 25 % DEL VALOR
    TOTAL» → 2.500.000, no 10.000.000. Solo dispara si hay porcentaje asociado
    al total Y una base monetaria; en otro caso devuelve None.
    """
    if not texto:
        return None
    u = texto
    if "GLOSA" not in u.upper():
        return None
    mp = _RE_PORCENTAJE_DE_TOTAL.search(u)
    mb = _RE_BASE_TOTAL.search(u)
    if not (mp and mb):
        return None
    try:
        pct = (
            float(mp.group(1).replace(".", "").replace(",", "."))
            if "," in mp.group(1)
            else float(mp.group(1).replace(".", ""))
        )
    except Exception:
        return None
    if not (0 < pct <= 100):
        return None
    base = _num_cop(mb.group(1))
    if base <= 0:
        return None
    return round(base * pct / 100.0)


# ─────────────────────────── Caso I: incoherencia biológica ───────────────────────────
_RE_PROC_FEMENINO = re.compile(
    r"\bPARTO\b|CES[ÁA]REA|OBST[ÉE]TRIC|GESTACI[ÓO]N|EMBARAZ|PRENATAL|LEGRADO|"
    r"HISTERECTOM[ÍI]A|[ÚU]TERO|OV[ÁA]RIC|C[ÉE]RVIX|CERVICOUTERIN",
    re.IGNORECASE,
)
_RE_PROC_MASCULINO = re.compile(
    r"PR[ÓO]STAT|PROSTATECTOM|VASECTOM[ÍI]A|TESTICUL|ESCROT|HIDROCELE|VARICOCELE",
    re.IGNORECASE,
)
_RE_SEXO_M = re.compile(
    r"\bMASCULINO\b|\bHOMBRE\b|\bSEXO\s*[:=]?\s*M\b|\bG[ÉE]NERO\s*[:=]?\s*M\b|\bVAR[ÓO]N\b",
    re.IGNORECASE,
)
_RE_SEXO_F = re.compile(
    r"\bFEMENINO\b|\bMUJER\b|\bSEXO\s*[:=]?\s*F\b|\bG[ÉE]NERO\s*[:=]?\s*F\b",
    re.IGNORECASE,
)


def sexo_exigido_por_el_procedimiento(descripcion: str) -> str | None:
    """«F», «M» o None: el sexo que exige un procedimiento por su nombre.

    Los mismos patrones del Caso I, expuestos para quien YA tiene el sexo del
    paciente como dato y no necesita leerlo del texto. Lo usa la
    pre-auditoría concurrente (V3, Pilar 2), donde el HIS manda el sexo en el
    payload y solo falta saber qué exige el procedimiento facturado.
    """
    d = descripcion or ""
    if _RE_PROC_FEMENINO.search(d):
        return "F"
    if _RE_PROC_MASCULINO.search(d):
        return "M"
    return None


def incoherencia_biologica(texto: str) -> str | None:
    """Devuelve el motivo si la glosa evidencia un procedimiento incompatible
    con el sexo registrado del paciente; None si no.

    Caso I: parto (CUPS 735930) en paciente MASCULINO. Solo dispara cuando la
    glosa nombra a la vez el procedimiento exclusivo de un sexo y el sexo
    contrario declarado explícitamente — no se infiere el sexo.
    """
    u = texto or ""
    if _RE_PROC_FEMENINO.search(u) and _RE_SEXO_M.search(u):
        return "un procedimiento propio del sexo femenino en un paciente registrado como masculino"
    if _RE_PROC_MASCULINO.search(u) and _RE_SEXO_F.search(u):
        return "un procedimiento propio del sexo masculino en una paciente registrada como femenino"
    return None


def texto_aceptacion_error_factura(codigo: str, valor_raw: str, motivo: str) -> str:
    cod = codigo if codigo and codigo != "N/A" else "INDICADA EN EL EXPEDIENTE"
    val = (
        valor_raw
        if valor_raw and str(valor_raw).strip() not in ("$ 0.00", "$0.00", "$ 0", "")
        else "EL VALOR INDICADO EN EL EXPEDIENTE"
    )
    return (
        f"REVISADA LA OBJECIÓN {cod} POR {val}, ESE HUS LA ACEPTA. LA ENTIDAD ADVIERTE "
        f"{motivo.upper()}, LO QUE CORRESPONDE A UN ERROR EN LA FACTURACIÓN Y NO A UNA "
        "CONTROVERSIA DE FONDO. NO ES ADMISIBLE SOSTENER LA PRESTACIÓN AMPARÁNDOSE EN "
        "LA AUTONOMÍA DEL MÉDICO TRATANTE CUANDO EL PROPIO REGISTRO MUESTRA LA "
        "INCONSISTENCIA. SE VERIFICARÁ LA HISTORIA CLÍNICA Y SE PROCEDERÁ CON LA NOTA "
        "CRÉDITO Y LA CORRECCIÓN DE LA FACTURA. CUALQUIER INFORMACIÓN AL CORREO "
        "INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


# ─────────────────────────── Caso L: fechas invertidas ───────────────────────────
def _fecha_junto_a(texto: str, etiqueta: str) -> datetime.date | None:
    m = re.search(
        r"(?:" + etiqueta + r")[^0-9]{0,40}?(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
        texto or "",
        re.IGNORECASE,
    )
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def fechas_ingreso_alta_invertidas(texto: str) -> tuple | None:
    """Devuelve (ingreso, alta) si la de alta es ANTERIOR a la de ingreso.

    Caso L: ingresó 25/08/2026 y alta 20/08/2026. Es un imposible temporal:
    no se defiende inventando un «cierre administrativo».
    """
    ing = _fecha_junto_a(texto, r"INGRES\w*|ADMISI[ÓO]N")
    alta = _fecha_junto_a(texto, r"\bALTA\b|EGRESO|SALIDA")
    if ing and alta and alta < ing:
        return (ing, alta)
    return None


def texto_aceptacion_fecha_invertida(codigo: str, valor_raw: str, fechas: tuple) -> str:
    cod = codigo if codigo and codigo != "N/A" else "INDICADA EN EL EXPEDIENTE"
    ing, alta = fechas
    f = lambda x: x.strftime("%d/%m/%Y")  # noqa: E731
    return (
        f"REVISADA LA OBJECIÓN {cod}, ESE HUS RECONOCE LA INCONSISTENCIA: LA FECHA DE "
        f"EGRESO REGISTRADA ({f(alta)}) ES ANTERIOR A LA FECHA DE INGRESO ({f(ing)}), "
        "LO QUE ES MATERIALMENTE IMPOSIBLE Y CONFIGURA UN ERROR DE FACTURACIÓN. NO SE "
        "SOSTENDRÁ LA PRESTACIÓN CON UNA JUSTIFICACIÓN DE LAS FECHAS INVERTIDAS. SE "
        "REVISARÁ Y CORREGIRÁ LA FACTURA CONTRA LA HISTORIA CLÍNICA Y, CONFIRMADO EL "
        "ERROR, SE APLICARÁ EL AJUSTE MEDIANTE NOTA CRÉDITO. CUALQUIER INFORMACIÓN AL "
        "CORREO INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


# ─────────────────────────── Caso M: tope SOAT no agotado ───────────────────────────
def soat_tope_no_agotado(texto: str) -> dict | None:
    """Si la glosa prueba con números consistentes que el tope SOAT NO se agotó,
    devuelve {tope, demostrado, faltante, cobrado_eps}; si no, None.

    Caso M (espejo del Caso 6): la EPS SÍ tiene razón. Tope $34.600.000, la IPS
    solo agotó $10.000.000, quedan $24.600.000 de cobertura — más que los
    $15.000.000 cobrados a la EPS. El motor NO puede abstenerse: acepta y
    redirige el cobro a la aseguradora. Solo dispara con las cifras explícitas
    en el texto y la aritmética cuadrando (nunca inventa).
    """
    u = texto or ""
    m_tope = re.search(r"\bTOPE\b[^$%]{0,50}?\$\s*([\d][\d.,]{4,})", u, re.IGNORECASE)
    m_dem = re.search(
        r"(?:DEMUESTRA|AGOTAD[OA]S?|GASTOS?\s+SOAT|EJECUTAD[OA]S?)[^$%]{0,40}?\$\s*([\d][\d.,]{4,})",
        u,
        re.IGNORECASE,
    )
    if not (m_tope and m_dem):
        return None
    tope = _num_cop(m_tope.group(1))
    dem = _num_cop(m_dem.group(1))
    if tope <= 0 or dem < 0 or dem >= tope:
        return None
    m_cob = re.search(
        r"(?:COBRAN?|FACTURAN?|SE\s+COBRA)[^$%]{0,50}?(?:A\s+LA\s+EPS)?[^$%]{0,20}?\$\s*([\d][\d.,]{4,})",
        u,
        re.IGNORECASE,
    )
    if not m_cob:
        m_cob = re.search(r"\bGLOSA\b[^$%]{0,20}?\$\s*([\d][\d.,]{4,})", u, re.IGNORECASE)
    cobrado = _num_cop(m_cob.group(1)) if m_cob else 0.0
    if cobrado <= 0:
        return None
    faltante = tope - dem
    # La cobertura disponible debe alcanzar para lo cobrado a la EPS: si no,
    # el caso es mixto y no se resuelve por esta regla simple.
    if cobrado > faltante + 1:
        return None
    # Si el texto declara un «faltante», debe cuadrar con tope - demostrado.
    m_falt = re.search(r"FALTAN?[^$%]{0,20}?\$\s*([\d][\d.,]{4,})", u, re.IGNORECASE)
    if m_falt:
        declarado = _num_cop(m_falt.group(1))
        if abs(declarado - faltante) > max(1.0, faltante * 0.02):
            return None
    return {"tope": tope, "demostrado": dem, "faltante": faltante, "cobrado_eps": cobrado}


def texto_cobro_soat_remanente(datos: dict) -> str:
    tope, dem, falt, cob = (
        datos["tope"],
        datos["demostrado"],
        datos["faltante"],
        datos["cobrado_eps"],
    )
    return (
        "REVISADA LA OBJECIÓN, ESE HUS LA ACEPTA. CONFORME AL DECRETO 780 DE 2016 "
        "(RÉGIMEN ECAT/SOAT), EN ACCIDENTE DE TRÁNSITO LA PÓLIZA SOAT RESPONDE EN "
        "PRIMER LUGAR HASTA SU TOPE, AGOTADO ÉSTE RESPONDE EL ADRES Y SOLO DESPUÉS LA "
        f"ENTIDAD PROMOTORA DE SALUD. LA ENTIDAD DEMUESTRA QUE DEL TOPE DE {_fmt_cop(tope)} "
        f"SOLO SE HAN AGOTADO {_fmt_cop(dem)}, QUEDANDO {_fmt_cop(falt)} DE COBERTURA "
        f"DISPONIBLE, SUMA SUPERIOR A LOS {_fmt_cop(cob)} FACTURADOS A LA EPS. POR TANTO, "
        f"ESOS {_fmt_cop(cob)} DEBEN RECLAMARSE PRIMERO A LA ASEGURADORA DEL SOAT Y, "
        "AGOTADO EL TOPE, AL ADRES; NO A LA EPS. ESE HUS PROCEDERÁ A REDIRIGIR EL COBRO "
        "A LA ASEGURADORA Y A EMITIR LA NOTA CRÉDITO QUE CORRESPONDA. CUALQUIER "
        "INFORMACIÓN AL CORREO INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


# ─────────────────────────── Caso F: objeción documental con código de tarifa ───────────────────────────
_RE_FALTA_SOPORTE = re.compile(
    r"\bNO\s+SE\s+ADJUNT\w*|\bNO\s+ADJUNT\w*|\bNO\s+SE\s+APORT\w*|\bNO\s+APORT\w*|"
    r"\bNO\s+SE\s+ALLEG\w*|\bNO\s+SE\s+ANEX\w*|\bNO\s+SE\s+REMIT\w*|\bNO\s+OBRA\b|"
    r"\bSIN\s+ADJUNTAR\b|\bAUSENCIA\s+DE\b|\bNO\s+SE\s+PUEDE\s+VERIFICAR\b|\bILEGIBLE\w*",
    re.IGNORECASE,
)
_DOCS_CLINICOS = (
    (r"NOTA\s+(?:OPERATORIA|QUIR[ÚU]RGICA)|DESCRIPCI[ÓO]N\s+QUIR[ÚU]RGICA", "la nota operatoria"),
    (
        r"R[ÉE]CORD\s+(?:DE\s+)?ANESTESIA|REGISTRO\s+(?:DE\s+)?ANESTESIA|HOJA\s+(?:DE\s+)?ANESTESIA",
        "el récord de anestesia",
    ),
    (r"HISTORIA\s+CL[ÍI]NICA", "la historia clínica"),
    (r"EPICRISIS", "la epicrisis"),
    (r"HOJA\s+DE\s+ADMINISTRACI[ÓO]N", "la hoja de administración de medicamentos"),
    (r"KARDEX", "el kardex"),
    (r"CONSENTIMIENTO\s+INFORMADO", "el consentimiento informado"),
    (r"ORDEN\s+M[ÉE]DICA", "la orden médica"),
    (r"\bRIPS\b", "los RIPS"),
)


def objecion_realmente_documental(texto: str, prefijo: str) -> list[str] | None:
    """Cuando el código es de tarifa (TA) pero el texto reclama la falta de un
    soporte clínico concreto, devuelve la lista de documentos echados de menos.

    Caso F: `TA0101 … NO SE ADJUNTA LA NOTA QUIRURGICA NI EL RECORD DE ANESTESIA`.
    El texto manda sobre el código: la objeción es documental, no de tarifa.
    """
    if prefijo != "TA":
        return None
    u = texto or ""
    if not _RE_FALTA_SOPORTE.search(u):
        return None
    docs = [nombre for patron, nombre in _DOCS_CLINICOS if re.search(patron, u, re.IGNORECASE)]
    return docs or None


def parrafo_soportes_faltantes(codigo: str, docs: list[str]) -> str:
    cod = codigo if codigo and codigo != "N/A" else "INDICADA EN EL EXPEDIENTE"
    lst = ", ".join(docs)
    return (
        f"LA OBJECIÓN {cod} SE FUNDA EN LA FALTA DE SOPORTES —{lst.upper()}—, NO EN UNA "
        "DIFERENCIA TARIFARIA, POR LO QUE SE ATIENDE COMO REQUERIMIENTO DOCUMENTAL. "
        f"ESE HUS APORTARÁ {lst.upper()}, QUE REPOSA EN LA HISTORIA CLÍNICA DEL PACIENTE, "
        "PARA ACREDITAR LA PRESTACIÓN Y PERMITIR LA VERIFICACIÓN DEL COBRO. SE SOLICITA "
        "A LA ENTIDAD LEVANTAR LA GLOSA UNA VEZ VERIFICADOS LOS SOPORTES. CUALQUIER "
        "INFORMACIÓN AL CORREO INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


# ─────────────────────────── Caso J: ratificación en el texto ───────────────────────────
# Marcador de ETAPA, no la palabra «ratifica» a secas. «La EPS ratifica la
# glosa» describe lo que hizo la entidad y aparece en glosas iniciales (y en la
# de una ratificación EXTEMPORÁNEA, que debe ir al motor con su defensa de
# tiempo — caso SO0601). Lo que marca la etapa de conciliación es «respuesta a
# conciliación», «mesa de conciliación», «segunda respuesta a la glosa».
_RE_RATIFICACION_TEXTO = re.compile(
    r"\bRESPUESTA\s+A\s+(?:LA\s+)?CONCILIACI[ÓO]N\b|\bMESA\s+DE\s+CONCILIACI[ÓO]N\b|"
    r"\bETAPA\s+DE\s+CONCILIACI[ÓO]N\b|\bSEGUNDA\s+RESPUESTA\s+A\s+(?:LA\s+)?GLOSA\b|"
    r"\bRESPUESTA\s+A\s+(?:LA\s+)?RATIFICACI[ÓO]N\b",
    re.IGNORECASE,
)


def texto_es_ratificacion(texto: str) -> bool:
    """Caso J: la etapa venía como respuesta inicial pero el texto marca la
    etapa de conciliación («respuesta a conciliación», «mesa de conciliación»,
    «segunda respuesta a la glosa»). Se enruta al camino de ratificada
    (mantener la respuesta, solicitar conciliación), no a la subsanación
    inicial. NO basta la palabra «ratifica» suelta: es ambigua y una
    ratificación extemporánea debe ir al motor con su defensa de tiempo."""
    return bool(_RE_RATIFICACION_TEXTO.search(texto or ""))


# ── Clasificador de ETAPA PROCESAL (refactor del ciclo de vida, 02-09-2026) ──
# Amplio a propósito: sirve para AVISARLE al gestor (badge en pantalla) y para
# ORDENARLE al modelo, cuando el caso va por IA, que no responda una segunda
# instancia como si fuera el día uno. NO decide el ruteo al texto fijo de
# ratificada (eso lo sigue haciendo `texto_es_ratificacion`, más estricto, para
# que una ratificación extemporánea siga yendo al motor con su defensa de
# tiempo — caso SO0601). Por eso aquí sí entra la palabra «ratifica» a secas.
_RE_ETAPA_CONCILIACION = re.compile(
    r"\bRESPUESTA\s+A\s+(?:LA\s+)?CONCILIACI[ÓO]N\b|\bMESA\s+DE\s+CONCILIACI[ÓO]N\b|"
    r"\bACTA\s+DE\s+(?:CONCILIACI[ÓO]N|AUDITOR[ÍI]A)\b|\bAUDIENCIA\s+DE\s+CONCILIACI[ÓO]N\b|"
    r"\bEN\s+(?:ETAPA\s+DE\s+)?CONCILIACI[ÓO]N\b",
    re.IGNORECASE,
)
_RE_ETAPA_RATIFICACION = re.compile(
    r"\bRATIFICA\w*\b|(?:\bSE\s+)?MANTIENE\s+(?:LA\s+)?GLOSA\b|\bSEGUNDA\s+INSTANCIA\b|"
    r"\bSEGUNDA\s+RESPUESTA\s+A\s+(?:LA\s+)?GLOSA\b|\bINSISTE\s+EN\s+LA\s+GLOSA\b|"
    r"\bREITERA\s+LA\s+GLOSA\b|\bNO\s+ACEPTA\s+(?:LA\s+)?RESPUESTA\b|"
    r"\bRESPUESTA\s+A\s+(?:LA\s+)?RATIFICACI[ÓO]N\b",
    re.IGNORECASE,
)


def clasificar_etapa_procesal(texto: str, etapa_form: str = "") -> str:
    """Devuelve la etapa del ciclo de vida de la glosa: "INICIAL",
    "RATIFICACION" o "CONCILIACION".

    Requisito 1 del Caso J: el texto se escanea en busca de marcadores de etapa
    avanzada. La conciliación es una etapa posterior a la ratificación, así que
    manda si aparecen las dos. El campo `etapa` del formulario también cuenta.
    """
    ef = (etapa_form or "").upper()
    u = texto or ""
    if "CONCILIA" in ef or _RE_ETAPA_CONCILIACION.search(u):
        return "CONCILIACION"
    if "RATIF" in ef or _RE_ETAPA_RATIFICACION.search(u):
        return "RATIFICACION"
    return "INICIAL"


# ─────────────────────────── Caso G: norma inventada por la entidad ───────────────────────────
_RE_NORMA_CITADA = re.compile(
    r"\b(RESOLUCI[ÓO]N|DECRETO|LEY|CIRCULAR)\s+(\d{1,5})\s+DE\s+(\d{4})",
    re.IGNORECASE,
)


def _norma_en_corpus(tipo: str, numero: str, anio: str) -> bool:
    """¿La norma existe en el corpus normativo del sistema?"""
    objetivo = _sin_tildes_mayus(f"{tipo} {numero} DE {anio}")
    # Normaliza 'RESOLUCION'/'LEY'/'DECRETO' — el corpus usa esas palabras.
    try:
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        for k in _TODAS_LAS_NORMAS:
            kk = _sin_tildes_mayus(str(k))
            if objetivo in kk or (f"{_sin_tildes_mayus(tipo)} {numero} DE {anio}") in kk:
                return True
        return False
    except Exception:
        # Sin corpus disponible no se afirma inexistencia (no romper la defensa).
        return True


def normas_inexistentes_citadas(texto: str) -> list[str]:
    """Devuelve las normas citadas EN LA GLOSA que no existen en el corpus.

    Caso G: la entidad invoca «Artículo 99 de la Resolución 8888 de 2025». No
    existe: no se debate su aplicabilidad, se ignora y se argumenta con normas
    vigentes.
    """
    fuera: list[str] = []
    for tipo, numero, anio in _RE_NORMA_CITADA.findall(texto or ""):
        # Futura o inexistente en el corpus.
        futura = int(anio) > datetime.date.today().year
        if futura or not _norma_en_corpus(tipo, numero, anio):
            etiqueta = f"{tipo.upper()} {numero} DE {anio}"
            if etiqueta not in fuera:
                fuera.append(etiqueta)
    return fuera


def _numeros_de(etiqueta: str) -> tuple[str, str]:
    m = re.search(r"(\d{1,5})\s+DE\s+(\d{4})", etiqueta)
    return (m.group(1), m.group(2)) if m else ("", "")


def no_legitimar_normas_ajenas(argumento: str, inexistentes: list[str]) -> "tuple[str, list[str]]":
    """Borra del argumento las oraciones que debaten como reales las normas que
    la entidad inventó, y deja constancia de que no existen. Conserva el resto
    de la defensa (fundada en normas vigentes)."""
    if not argumento or not inexistentes:
        return argumento, []
    pares = [(_numeros_de(e)) for e in inexistentes]
    pares = [(n, a) for n, a in pares if n]
    if not pares:
        return argumento, []
    oraciones = re.split(r"(?<=[.;])\s+", argumento)
    quedan, borradas = [], []
    for o in oraciones:
        if any(num in o and anio in o for num, anio in pares):
            borradas.append(o.strip()[:160])
        else:
            quedan.append(o)
    if not borradas:
        return argumento, []
    limpio = re.sub(r"\s{2,}", " ", " ".join(quedan)).strip()
    lista = " Y ".join(inexistentes)
    coletilla = (
        f" LA {lista} INVOCADA POR LA ENTIDAD NO SE ENCUENTRA EN EL ORDENAMIENTO "
        "JURÍDICO VIGENTE, POR LO QUE NO PRODUCE EFECTO ALGUNO; ESTA RESPUESTA SE "
        "FUNDA EN LAS NORMAS REALMENTE APLICABLES A LA ATENCIÓN."
    )
    return (limpio + coletilla).strip(), borradas


# ─────────────────────────── Caso N: MIPRES obligatorio ───────────────────────────
_RE_EVASION_DEVOLUCION = re.compile(
    r"NO\s+EXISTE\s+EVIDENCIA\s+SUFICIENTE|DEVOLUCI[ÓO]N\s+ADMINISTRATIVA|"
    r"NO\s+IDENTIFICA\s+EL\s+SERVICIO",
    re.IGNORECASE,
)


def glosa_exige_mipres(texto: str) -> bool:
    """Caso N: la entidad objeta la falta del formato MIPRES (medicamento NO PBS).

    Substring, no `\\bMIPRES\\b`: en un nombre de archivo «mipres_123.pdf» el
    guion bajo rompe el límite de palabra (mismo problema del Caso K).
    """
    return "MIPRES" in (texto or "").upper()


def hay_mipres_en_soportes(contexto_pdf: str) -> bool:
    return "MIPRES" in (contexto_pdf or "").upper()


def es_evasion_devolucion(argumento: str) -> bool:
    return bool(_RE_EVASION_DEVOLUCION.search(argumento or ""))


def parrafo_mipres(con_mipres: bool) -> str:
    base = (
        "EN CUANTO A LA OBJECIÓN POR EL FORMATO MIPRES: PARA LOS MEDICAMENTOS NO "
        "FINANCIADOS CON LA UPC (NO PBS), EL FORMATO MIPRES DILIGENCIADO POR EL "
        "MÉDICO TRATANTE ES SOPORTE OBLIGATORIO DE LA PRESCRIPCIÓN. "
    )
    if con_mipres:
        return base + (
            "DICHO FORMATO OBRA ENTRE LOS SOPORTES DE ESTA RESPUESTA, POR LO QUE SE "
            "SOLICITA LEVANTAR LA GLOSA."
        )
    return base + (
        "ESE HUS RECONOCE EL REQUERIMIENTO Y APORTARÁ EL FORMATO MIPRES GENERADO POR "
        "EL MÉDICO TRATANTE COMO ANEXO OBLIGATORIO; LA FÓRMULA MANUAL NO LO SUSTITUYE. "
        "ESTA RESPUESTA NO CONSTITUYE DEVOLUCIÓN: EL SERVICIO ESTÁ IDENTIFICADO Y LA "
        "OBJECIÓN SE ATIENDE APORTANDO EL SOPORTE ECHADO DE MENOS."
    )


# ─────────────────────────── orquestador de camino forzado ───────────────────────────
def dictamen_forzado_por_contradiccion(
    texto: str, prefijo: str, codigo: str, valor_raw: str, eps: str = ""
) -> dict | None:
    """Decide, sin llamar al modelo, el dictamen de los casos en que la propia
    glosa contiene una contradicción o un hecho que el motor debe reconocer.

    Devuelve un dict {arg, cod, desc, accion, tipo, nota} o None. El orden es de
    prioridad: informativa $0 → incoherencia clínica → fechas invertidas →
    tope SOAT no agotado → objeción documental con código de tarifa.
    """
    if glosa_es_informativa_cero(texto):
        return {
            "tipo": "INFORMATIVA_CERO",
            "accion": "",
            "cod": "RE9701",
            "desc": "GLOSA INFORMATIVA - VALOR GLOSADO $0, SIN CONTROVERSIA ECONÓMICA",
            "arg": parrafo_informativa(codigo),
            "nota": "La glosa objeta $0 (informativa): no lleva defensa jurídica ni devolución.",
        }
    motivo_bio = incoherencia_biologica(texto)
    if motivo_bio:
        return {
            "tipo": "ACEPTADA_ERROR_FACTURA",
            "accion": "ACEPTAR_TOTAL",
            "cod": "RE9702",
            "desc": "GLOSA ACEPTADA - ERROR DE FACTURACIÓN (INCOHERENCIA CLÍNICA)",
            "arg": texto_aceptacion_error_factura(codigo, valor_raw, motivo_bio),
            "nota": "La glosa evidencia "
            + motivo_bio
            + "; se acepta por error de facturación, no se defiende con autonomía médica.",
        }
    fechas = fechas_ingreso_alta_invertidas(texto)
    if fechas:
        return {
            "tipo": "ACEPTADA_FECHA_INVERTIDA",
            "accion": "ACEPTAR_TOTAL",
            "cod": "RE9702",
            "desc": "GLOSA ACEPTADA - FECHAS INCONGRUENTES (ALTA ANTERIOR AL INGRESO)",
            "arg": texto_aceptacion_fecha_invertida(codigo, valor_raw, fechas),
            "nota": "La fecha de egreso es anterior a la de ingreso; se reconoce el error y se corrige la factura, sin inventar teorías.",
        }
    if prefijo == "CO" or _es_cobertura_soat(texto):
        datos = soat_tope_no_agotado(texto)
        if datos:
            return {
                "tipo": "ACEPTADA_SOAT_REMANENTE",
                "accion": "ACEPTAR_TOTAL",
                "cod": "RE9702",
                "desc": "GLOSA ACEPTADA - TOPE SOAT NO AGOTADO, SE COBRA A LA ASEGURADORA",
                "arg": texto_cobro_soat_remanente(datos),
                "nota": "La entidad prueba con números que el tope SOAT no se agotó; se acepta y se redirige el cobro a la aseguradora.",
            }
    docs = objecion_realmente_documental(texto, prefijo)
    if docs:
        return {
            "tipo": "FA_SOPORTES_FORZADO",
            "accion": "DEFENDER_TOTAL",
            "cod": "RE9901",
            "desc": "GLOSA NO ACEPTADA - SE APORTAN LOS SOPORTES REQUERIDOS",
            "arg": parrafo_soportes_faltantes(codigo, docs),
            "nota": "El código dice tarifa pero el texto reclama soportes ("
            + ", ".join(docs)
            + "); se responde como documental.",
        }
    return None


def _es_cobertura_soat(texto: str) -> bool:
    try:
        from app.services.glosa_ia_prompts import es_glosa_cobertura_soat

        return bool(es_glosa_cobertura_soat(texto))
    except Exception:
        return False
