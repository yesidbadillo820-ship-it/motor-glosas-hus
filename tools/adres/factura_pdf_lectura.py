"""factura_pdf_lectura.py — Parser del 'Detalle de cargos' del PDF del HUS.

El PDF de la factura del HUS trae, además de la representación DIAN genérica,
un detalle con código SOAT del manual tarifario, nombre completo, cantidad y
valor por línea (reporte FCRPFacturaEntidad), incluyendo la descomposición
quirúrgica marcada con `[GQ : NN]` y sus 5 sub-renglones (cirujano,
anestesiólogo, ayudantía, sala, materiales).

Devuelve una lista normalizada de líneas listas para el FUR SERVICIOS, con:
    nro, codigo, descripcion, cantidad, vr_unitario, vr_total, seccion,
    es_quirurgico, cod_general_quirurgico, consecutivo_quirurgico, gq_grupo

Sólo se procesan las páginas del primer reporte (FCRPFacturaEntidad). El
"Detalle de Cargos" se repite en páginas 5+; lo deduplicamos por `nro`.

DEPENDENCIA: pdfplumber.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Secciones reconocidas (mayúsculas) → categoría usada para inferir Tipo FUR
SECCIONES = {
    "CONSULTAS MEDICAS": "consultas",
    "PROTESIS Y ORTESIS": "osteo",
    "MEDICAMENTOS POS": "medicamentos",
    "MEDICAMENTOS": "medicamentos",
    "PROCEDIMIENTOS TERAPEUTICOS QUIRURGICOS": "quirurgico",
    "PROCEDIMIENTOS TERAPEUTICOS NO QUIRURGICO": "procedimientos",
    "ESTANCIAS": "estancias",
    "DERECHOS DE SALA": "derechos_sala",
    "MATERIALES E INSUMOS": "insumos",
    "LABORATORIOS": "procedimientos",
    "IMAGENOLOGIA": "procedimientos",
}

# Tokens que aparecen en la fila de la cirugía "padre" para detectar el GQ.
_RE_GQ = re.compile(r"\[GQ\s*:\s*(\d+)\s*\]")
# Importe COP en el formato "$ 1.234.567,89" o "1.234.567,89" — devolvemos sin separadores.
_RE_IMP = re.compile(r"\$?\s*([\d\.]+),(\d{2})")
# Cantidad "1,00" o "12,00" al inicio del bloque numérico
_RE_CANT = re.compile(r"(\d+),(\d{2})")
# Códigos de servicio: letras+dígitos (FMQ0050, FMO00404, 19908236-07, 25040-2…) o solo dígitos (39140).
_RE_COD = re.compile(r"^[A-Z]{1,4}\d[\w\-]*$|^\d{4,8}(?:-\d+)?$")


def _imp(s: str) -> str:
    """Devuelve un importe normalizado (sin puntos de miles, con dos decimales)."""
    m = _RE_IMP.search(s.replace(" ", ""))
    if not m:
        return ""
    entero = m.group(1).replace(".", "")
    return f"{int(entero)}"  # decimales descartados (siempre vienen 00 en estos PDFs)


def _parsear_montos(cola: str) -> tuple[str, str, str]:
    """Dado el 'final' de una línea (cant + 3 importes), devuelve (cant, vrUnit, vrTotal).

    Ejemplo: "1,00 $ 83.400,00 $ 0,00 $ 166.800,00" → ("1", "83400", "166800").
    """
    # 4 valores numéricos con coma decimal
    nums = re.findall(r"[\d\.]+,\d{2}", cola)
    if len(nums) < 4:
        return "", "", ""
    cant_raw = nums[0]
    vr_unit_raw = nums[1]
    # nums[2] es VR PAC (siempre 0,00) — lo ignoramos
    vr_total_raw = nums[3]
    cant = cant_raw.split(",")[0].lstrip("0") or "0"
    return cant, _imp(vr_unit_raw), _imp(vr_total_raw)


def _es_seccion(linea: str) -> str | None:
    """Si la línea es un encabezado de sección, devuelve la etiqueta canónica."""
    s = linea.strip().upper()
    for clave, cat in SECCIONES.items():
        if s == clave:
            return cat
    return None


def extraer_texto(pdf_path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.stderr.write("ERROR: falta pdfplumber. Instalalo: py -m pip install pdfplumber\n")
        sys.exit(2)
    partes = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            partes.append(t)
    return "\n".join(partes)


_LINEAS_RUIDO = (
    "Carrrera 33",
    "NIT 900.006.037",
    "Bucaramanga",
    "CUFE:",
    "FACTURA ELECTRONICA",
    "DETALLE DE CARGOS",
    "CLIENTE",
    "Dirección",
    "Plan U22",
    "Paciente",
    "Tipo Doc",
    "Fec Ingreso",
    "CÓDIGO NOMBRE",
    "AUTORIZACIÓN",
    "LA PRESENTE",
    "UNA VEZ",
    "POR LA SUPERINTENDENCIA",
    "Nombre reporte",
    "LICENCIADO",
    "VALOR SUBTOTAL",
    "VALOR CUOTA",
    "VALOR ANTICIPO",
    "VALOR TOTAL",
    "TOTAL:",
    "NOTAS FINALES",
    "LUDY YADIRA",
    "ELABORO",
    "SEGURIDAD SOCIAL",
    "CODIGO EPS",
    "Página",
)


def _es_ruido(ln: str) -> bool:
    return any(x in ln for x in _LINEAS_RUIDO)


# Patrón compacto: línea que termina con cant + 3 importes (cant, vr_unit, vr_pac, vr_total)
_RE_COLA_MONTOS = re.compile(r"\d+,\d{2}\s+\$.*?\$.*?\$\s*[\d\.]+,\d{2}\s*$")
# Mismo patrón pero detecta SI APARECE EN MEDIO de la cadena fusionada (varias colas)
_RE_COLA_MONTOS_DIVISOR = re.compile(
    r"(\d+,\d{2})\s+(\$\s*[\d\.]+,\d{2})\s+(\$\s*[\d\.]+,\d{2})\s+(\$\s*[\d\.]+,\d{2})"
)


def _agrupar_lineas_por_nro(texto: str) -> list[dict]:
    """Devuelve un dict por cada línea numerada (1..N) o sub-línea quirúrgica.

    El PDF parte filas en dos visuales: pdfplumber a veces deja el código en una
    línea y el nombre en la siguiente (o viceversa). Acá juntamos por número de
    ítem y por presencia de un código en la línea.

    Estrategia: avanzamos línea a línea. Cuando vemos un patrón "<n> <CODIGO>"
    o "<n>\n<CODIGO>", abrimos un registro. Vamos acumulando el nombre y los
    importes hasta que aparezca el siguiente número de ítem o un sub-renglón
    (renglón quirúrgico con código numérico de 5 dígitos al inicio y SIN número
    de ítem) o un cambio de sección.
    """
    # PASO 1: fusionar líneas por sección y juntar las que componen un ítem.
    # Un ítem termina SIEMPRE con "cant,xx $ ... $ ... $ ..." (cant + 3 importes).
    # Acumulamos líneas hasta encontrar esa cola, y entonces emitimos un bloque.
    raw_lines = [ln.rstrip() for ln in texto.splitlines() if ln.strip()]
    bloques: list[tuple[str, str]] = []  # (seccion, texto_unido)
    seccion = ""
    buffer: list[str] = []

    def emitir_bloque(s: str, txt: str):
        # Si el texto fusionado contiene MÚLTIPLES colas de montos, separar en
        # tantos sub-bloques como colas haya. Esto evita que pdfplumber pegue
        # la cirugía padre con su primer sub-renglón en un solo bloque.
        spans = [m.end() for m in _RE_COLA_MONTOS_DIVISOR.finditer(txt)]
        if len(spans) <= 1:
            bloques.append((s, txt.strip()))
            return
        prev = 0
        emitidos: list[str] = []
        for end in spans:
            chunk = txt[prev:end].strip()
            emitidos.append(chunk)
            bloques.append((s, chunk))
            prev = end
        cola = txt[prev:].strip()
        if cola:
            # Lo que queda después de la última cola normalmente pertenece al
            # PRIMER bloque emitido (es el resto del nombre/[GQ:NN] del padre
            # cirugía, que el PDF puso después de los montos). Lo concatenamos.
            if bloques and emitidos:
                primer_idx = len(bloques) - len(emitidos)
                seccion_anterior, txt_anterior = bloques[primer_idx]
                bloques[primer_idx] = (seccion_anterior, txt_anterior + " " + cola)

    def flush_buffer():
        if buffer:
            emitir_bloque(seccion, " ".join(buffer))
            buffer.clear()

    for ln in raw_lines:
        sec = _es_seccion(ln)
        if sec:
            flush_buffer()
            seccion = sec
            continue
        if _es_ruido(ln):
            continue
        buffer.append(ln.strip())
        if _RE_COLA_MONTOS.search(ln):
            flush_buffer()
    flush_buffer()

    # PASO 2: parsear cada bloque en una línea estructurada
    registros: list[dict] = []
    consecutivo_q = 0
    cod_quirurgico_actual = ""

    for sec, bloque in bloques:
        # Cortamos por la cola de montos
        m_cola = re.search(
            r"(\d+,\d{2})\s+(\$\s*[\d\.]+,\d{2})\s+(\$\s*[\d\.]+,\d{2})\s+(\$\s*[\d\.]+,\d{2})\s*$",
            bloque,
        )
        if not m_cola:
            continue
        cabeza = bloque[: m_cola.start()].strip()
        cant_raw = m_cola.group(1)
        cant = cant_raw.split(",")[0].lstrip("0") or "0"
        vr_unit = _imp(m_cola.group(2))
        vr_total = _imp(m_cola.group(4))

        # Cabeza típica:
        #   "<nro> <CODIGO> <NOMBRE>"          → ítem normal
        #   "<nro> <NOMBRE> <CODIGO>"           → variante (código aparece después del nombre, p.ej. ítem 1)
        #   "<nro> <NOMBRE> [GQ : NN] <CODIGO>" → cirugía padre con código intercalado
        #   "<CODIGO_QX>" sin nro               → sub-renglón quirúrgico (39010…)
        tokens = cabeza.split()
        if not tokens:
            continue

        nro = ""
        codigo = ""
        descripcion = ""

        # ¿Empieza con un número de ítem (1..3 dígitos)?
        if re.fullmatch(r"\d{1,3}", tokens[0]):
            nro = tokens[0]
            resto_tokens = tokens[1:]
        else:
            resto_tokens = tokens[:]

        # Buscar el código en los tokens. Estrategia: el primer token que
        # cumpla _RE_COD se toma como código; el resto es la descripción.
        for idx, tok in enumerate(resto_tokens):
            if _RE_COD.match(tok):
                codigo = tok
                descripcion = " ".join(resto_tokens[:idx] + resto_tokens[idx + 1 :]).strip()
                break
        else:
            descripcion = " ".join(resto_tokens).strip()

        # Detectar cirugía "padre" por [GQ : NN]
        es_quirurgico = False
        gq_grupo = ""
        mgq = _RE_GQ.search(descripcion)
        if mgq:
            es_quirurgico = True
            gq_grupo = mgq.group(1)
            consecutivo_q += 1
            cod_quirurgico_actual = codigo

        # ¿Sub-renglón quirúrgico? Sin nro, código numérico de 5 dígitos (39XXX) y sección quirúrgico
        es_subrenglon = (
            not nro
            and codigo
            and re.fullmatch(r"3\d{4}", codigo)
            and sec == "quirurgico"
            and not es_quirurgico
        )

        reg = {
            "nro": nro,
            "codigo": codigo,
            "descripcion": descripcion,
            "cantidad": cant,
            "vr_unitario": vr_unit,
            "vr_total": vr_total,
            "seccion": "quirurgico" if es_subrenglon or es_quirurgico else sec,
            "es_quirurgico": es_quirurgico or es_subrenglon,
            "es_subrenglon": es_subrenglon,
            "cod_general_quirurgico": (
                codigo if es_quirurgico else (cod_quirurgico_actual if es_subrenglon else "")
            ),
            "consecutivo_quirurgico": (
                str(consecutivo_q) if (es_quirurgico or es_subrenglon) else ""
            ),
            "gq_grupo": gq_grupo,
        }
        registros.append(reg)

    # Dedup: el "Detalle de Cargos" se repite en hojas 5+
    vistos: set[str] = set()
    final: list[dict] = []
    for r in registros:
        clave = f"{r['nro']}|{r['codigo']}|{r['vr_total']}|{r['descripcion'][:40]}"
        if clave in vistos:
            continue
        vistos.add(clave)
        final.append(r)
    return final


def leer_factura_pdf(pdf_path: Path) -> list[dict]:
    """Punto de entrada: lee el PDF y devuelve las líneas del detalle."""
    texto = extraer_texto(pdf_path)
    return _agrupar_lineas_por_nro(texto)


def hallar_factura_pdf(carpeta: Path) -> Path | None:
    for p in sorted(carpeta.iterdir()):
        if (
            p.is_file()
            and p.suffix.lower() == ".pdf"
            and "FACTURA" in p.name.upper()
            and "FACOSTE" not in p.name.upper()
        ):
            return p
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Uso: py factura_pdf_lectura.py <factura.pdf>\n")
        sys.exit(1)
    lineas = leer_factura_pdf(Path(sys.argv[1]))
    print(f"Líneas: {len(lineas)}")
    for ln in lineas[:80]:
        flag = "Q" if ln["es_quirurgico"] else ("·" if ln.get("es_subrenglon") else " ")
        print(
            f"  {flag} {ln['nro']:>3} {ln['codigo']:<14} {ln['descripcion'][:60]:<60} "
            f"x{ln['cantidad']:<3} ${ln['vr_unitario']:>10} = ${ln['vr_total']:>10}  "
            f"[cgq={ln['cod_general_quirurgico']} cons={ln['consecutivo_quirurgico']}]"
        )
