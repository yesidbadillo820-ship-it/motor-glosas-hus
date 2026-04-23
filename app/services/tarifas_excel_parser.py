"""Parser de Excel de tarifas contratadas tipo Famisanar.

El Excel viene con hasta 3 hojas:
  - Anexo 3   — Servicios y Tarifas (CUPS con fórmula SOAT ± %)
  - Anexo 3.1 — Tarifas Medicamentos (valor fijo por CUM/código prestador)
  - Anexo 3.2 — Tarifas Suministros (valor fijo, con IVA opcional)

Cada hoja trae un encabezado con NÚMERO DE CONTRATO, VIGENCIA, NOMBRE EPS, etc.
Luego viene una tabla con columnas fijas. Detectamos dónde arranca la tabla
buscando los encabezados esperados en cada hoja.

Exporta:
  parsear_excel_tarifas(bytes, filename) -> dict con:
    - eps, contrato, vigencia_desde, vigencia_hasta (metadata global)
    - filas: list[dict] con {codigo_cups, descripcion, valor_pactado,
      modalidad, tipo_tarifa, factor_ajuste}
    - hojas_detectadas: list[str]
    - errores: list[str]
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import load_workbook


# ─── Normalización ──────────────────────────────────────────────────────────

def _normalizar_texto(s: Any) -> str:
    """Quita tildes, pasa a mayúsculas, colapsa espacios."""
    if s is None:
        return ""
    t = str(s).strip()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).upper()


def _normalizar_valor(v: Any) -> float:
    """Parsea valores COP desde celda Excel (puede venir número o string)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(" ", "")
    if not s or s.upper() in ("N/A", "NA", "-"):
        return 0.0
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        m = re.match(r"^(\d+)[\.,](\d{1,2})$", s)
        if m:
            s = f"{m.group(1)}.{m.group(2)}"
        else:
            s = s.replace(".", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parsear_fecha(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    # Fix typo común "14//04/2027"
    s = re.sub(r"/+", "/", s)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parsear_porcentaje(v: Any) -> float:
    """Parsea strings tipo '-5%', '-15%', '+10%', '-5', '0%' → -5.0, -15.0, 10.0, -5.0, 0.0"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        # En Excel, 5% puede venir como 0.05 o 5. Heurística: si |v|<1 y ≠0 → fracción.
        f = float(v)
        if -1 < f < 1 and f != 0:
            return f * 100
        return f
    s = str(v).strip().replace("%", "").replace(" ", "").replace(",", ".")
    if not s:
        return 0.0
    try:
        f = float(s)
        if -1 < f < 1 and f != 0:
            return f * 100
        return f
    except ValueError:
        return 0.0


# ─── Detección de hojas ─────────────────────────────────────────────────────

HEADERS_ANEXO3_SERVICIOS = {
    "CUPS / CUMS / MIPRES", "CUPS/CUMS/MIPRES", "CUPS",
    "CODIGO PROPIO", "TIPO TARIFA", "HOSPITALARIO", "AMBULATORIO", "URGENCIA",
}
HEADERS_ANEXO31_MEDICAMENTOS = {
    "CODIGO DCI", "DESCRIPCION DCI", "CUM/IUM", "MAPIISS",
    "TARIFA UNITARIA", "APLICA IVA", "TIPO PLAN",
}
HEADERS_ANEXO32_SUMINISTROS = {
    "CODIGO DEL PRESTADOR", "DESCRIPCION DEL PRESTADOR",
    "TARIFA UNITARIA", "TARIFA FINAL", "APLICA IVA",
}


def _tipo_hoja(headers_normalizados: list[str]) -> str | None:
    """Devuelve 'ANEXO3' | 'ANEXO31' | 'ANEXO32' según los encabezados."""
    hset = set(headers_normalizados)
    # 3.1 (medicamentos) tiene CODIGO DCI y CUM/IUM — muy distintivo
    if {"CODIGO DCI", "DESCRIPCION DCI"} & hset and "CUM/IUM" in hset:
        return "ANEXO31"
    # 3.2 (suministros) tiene TARIFA FINAL + MAPIISS
    if "TARIFA FINAL" in " ".join(hset) and "MAPIISS" in hset:
        return "ANEXO32"
    if "CODIGO DEL PRESTADOR" in hset and "DESCRIPCION DEL PRESTADOR" in hset:
        return "ANEXO32"
    # Anexo 3 servicios: CUPS + TIPO TARIFA + HOSPITALARIO/AMBULATORIO/URGENCIA
    cups_like = any("CUPS" in h for h in hset)
    if cups_like and "TIPO TARIFA" in hset and ("HOSPITALARIO" in hset or "AMBULATORIO" in hset):
        return "ANEXO3"
    return None


def _buscar_fila_encabezado(ws) -> tuple[int, list[str]] | tuple[None, None]:
    """Escanea las primeras 50 filas buscando la fila de encabezados.

    Una fila es considerada "encabezado de tabla" si tiene ≥4 celdas no vacías
    y contiene al menos una palabra clave conocida (CUPS, TARIFA, MAPIISS,
    CODIGO DEL PRESTADOR, etc.).
    """
    keywords = [
        "CUPS", "TARIFA", "MAPIISS", "CODIGO DEL PRESTADOR",
        "CODIGO DCI", "CUM/IUM", "TIPO TARIFA", "DESCRIPCION DEL PRESTADOR",
    ]
    for fila_idx in range(1, min(50, ws.max_row + 1)):
        fila = [ws.cell(row=fila_idx, column=c).value for c in range(1, ws.max_column + 1)]
        no_vacios = [c for c in fila if c is not None and str(c).strip()]
        if len(no_vacios) < 4:
            continue
        fila_norm = [_normalizar_texto(c) for c in fila]
        if any(any(kw in celda for kw in keywords) for celda in fila_norm):
            return fila_idx, fila_norm
    return None, None


def _extraer_metadata(ws) -> dict:
    """Extrae eps, contrato, vigencia desde las primeras 50 filas de la hoja.

    Busca celdas con labels como 'NOMBRE DE LA EPS', 'NUMERO DE CONTRATO',
    'INICIO DE CONTRATO', 'VIGENCIA … INICIO/FINAL'. Dado que el layout varía,
    toma la primera celda no-vacía a la derecha como el valor.
    """
    meta = {"eps": None, "contrato": None, "vigencia_desde": None, "vigencia_hasta": None}
    for fila_idx in range(1, min(50, ws.max_row + 1)):
        for col_idx in range(1, ws.max_column + 1):
            celda = ws.cell(row=fila_idx, column=col_idx).value
            if not celda:
                continue
            etiqueta = _normalizar_texto(celda)
            # Tomar el primer valor no-vacío a la derecha
            def valor_derecha(offset_min: int = 1) -> Any:
                for c in range(col_idx + offset_min, min(ws.max_column + 1, col_idx + 15)):
                    v = ws.cell(row=fila_idx, column=c).value
                    if v is not None and str(v).strip() and _normalizar_texto(v) not in (
                        "CORREO:", "CEDULA:", "CEDULA", "TELEFONO:", "TELEFONO",
                        "CORREO", "HORARIO DE ATENCION", "CORREO ELECTRONICO",
                    ):
                        return v
                return None

            if not meta["eps"] and "NOMBRE DE LA EPS" in etiqueta:
                v = valor_derecha()
                if v:
                    meta["eps"] = str(v).strip()
            elif not meta["contrato"] and ("NUMERO DE CONTRATO" in etiqueta or "NÚMERO DE CONTRATO" in etiqueta):
                v = valor_derecha()
                if v and _normalizar_texto(v) not in ("N/A", "NA", "-"):
                    meta["contrato"] = str(v).strip()
            elif "INICIO DE CONTRATO" in etiqueta or ("VIGENCIA" in etiqueta and "INICIO" in etiqueta):
                v = valor_derecha()
                f = _parsear_fecha(v)
                if f and not meta["vigencia_desde"]:
                    meta["vigencia_desde"] = f
            elif "FINAL" in etiqueta and ("VIGENCIA" in etiqueta or "CONTRATO" in etiqueta):
                v = valor_derecha()
                f = _parsear_fecha(v)
                if f and not meta["vigencia_hasta"]:
                    meta["vigencia_hasta"] = f
    return meta


# ─── Parsers por tipo de hoja ───────────────────────────────────────────────

def _indice_columna(headers: list[str], *candidatos: str) -> int | None:
    """Busca el índice de la primera columna cuyo header coincida con algún candidato."""
    cands_norm = [_normalizar_texto(c) for c in candidatos]
    for i, h in enumerate(headers):
        for c in cands_norm:
            if c in h or h in c:
                return i
    return None


def _parsear_anexo3(ws, fila_encabezado: int, headers: list[str]) -> list[dict]:
    """Anexo 3 — Servicios CUPS con fórmula SOAT ± %."""
    idx_cups = _indice_columna(headers, "CUPS / CUMS / MIPRES", "CUPS/CUMS/MIPRES", "CUPS")
    idx_desc = _indice_columna(headers, "DESCRIPCION CUPS", "DESCRIPCION", "DESCRIPCIÓN")
    idx_tipo = _indice_columna(headers, "TIPO TARIFA")
    idx_hosp = _indice_columna(headers, "HOSPITALARIO")
    idx_amb = _indice_columna(headers, "AMBULATORIO")
    idx_urg = _indice_columna(headers, "URGENCIA")
    idx_obs = _indice_columna(headers, "OBSERVACION", "OBSERVACIÓN")

    if idx_cups is None:
        return []

    filas: list[dict] = []
    for fila_idx in range(fila_encabezado + 1, ws.max_row + 1):
        cups_raw = ws.cell(row=fila_idx, column=idx_cups + 1).value
        if not cups_raw:
            continue
        cups = str(cups_raw).strip()
        if not cups or not re.search(r"[A-Za-z0-9]", cups):
            continue
        desc = str(ws.cell(row=fila_idx, column=idx_desc + 1).value or "").strip() if idx_desc is not None else ""
        tipo = str(ws.cell(row=fila_idx, column=idx_tipo + 1).value or "").strip() if idx_tipo is not None else ""
        # Elegir factor: preferir Hospitalario, luego Ambulatorio, luego Urgencia
        factor = 0.0
        for idx in (idx_hosp, idx_amb, idx_urg):
            if idx is None:
                continue
            f = _parsear_porcentaje(ws.cell(row=fila_idx, column=idx + 1).value)
            if f != 0:
                factor = f
                break
        obs = str(ws.cell(row=fila_idx, column=idx_obs + 1).value or "").strip() if idx_obs is not None else ""
        filas.append({
            "codigo_cups": cups,
            "descripcion": desc[:500] if desc else None,
            "valor_pactado": 0.0,  # no aplica para SOAT_PORCENTAJE
            "modalidad": (tipo or "SOAT UVB VIGENTE")[:80],
            "tipo_tarifa": "SOAT_PORCENTAJE",
            "factor_ajuste": factor,
            "observacion": obs[:300] if obs else None,
        })
    return filas


def _parsear_anexo31(ws, fila_encabezado: int, headers: list[str]) -> list[dict]:
    """Anexo 3.1 — Medicamentos, valor fijo."""
    idx_cod_prest = _indice_columna(headers, "CODIGO DEL PRESTADOR")
    idx_cum = _indice_columna(headers, "CUM/IUM", "CUM", "IUM")
    idx_mapiiss = _indice_columna(headers, "MAPIISS")
    idx_desc_dci = _indice_columna(headers, "DESCRIPCION DCI")
    idx_desc = _indice_columna(headers, "DESCRIPCION", "DESCRIPCIÓN")
    idx_agrup = _indice_columna(headers, "AGRUPADOR")
    idx_tarifa = _indice_columna(headers, "TARIFA UNITARIA")
    idx_iva = _indice_columna(headers, "APLICA IVA")

    # Preferir "CODIGO DEL PRESTADOR" como CUPS principal; fallback a MAPIISS / CUM
    idx_codigo = idx_cod_prest if idx_cod_prest is not None else (idx_cum if idx_cum is not None else idx_mapiiss)
    idx_descripcion = idx_desc_dci if idx_desc_dci is not None else idx_desc
    if idx_codigo is None or idx_tarifa is None:
        return []

    filas: list[dict] = []
    for fila_idx in range(fila_encabezado + 1, ws.max_row + 1):
        cod_raw = ws.cell(row=fila_idx, column=idx_codigo + 1).value
        if not cod_raw:
            continue
        codigo = str(cod_raw).strip()
        if not codigo or not re.search(r"[A-Za-z0-9]", codigo):
            continue
        desc = str(ws.cell(row=fila_idx, column=idx_descripcion + 1).value or "").strip() if idx_descripcion is not None else ""
        tarifa = _normalizar_valor(ws.cell(row=fila_idx, column=idx_tarifa + 1).value)
        if tarifa <= 0:
            continue
        iva_si = False
        if idx_iva is not None:
            iva_val = str(ws.cell(row=fila_idx, column=idx_iva + 1).value or "").strip().upper()
            iva_si = iva_val in ("SI", "SÍ", "S", "YES", "Y", "1")
        # Si aplica IVA y hay columna de tarifa final, usarla; si no, sumar 19% al unitario
        valor_final = tarifa * 1.19 if iva_si else tarifa
        agrup = str(ws.cell(row=fila_idx, column=idx_agrup + 1).value or "").strip() if idx_agrup is not None else ""
        filas.append({
            "codigo_cups": codigo,
            "descripcion": desc[:500] if desc else None,
            "valor_pactado": round(valor_final, 2),
            "modalidad": (agrup or "MEDICAMENTOS")[:80],
            "tipo_tarifa": "VALOR_FIJO",
            "factor_ajuste": 0.0,
            "observacion": None,
        })
    return filas


def _parsear_anexo32(ws, fila_encabezado: int, headers: list[str]) -> list[dict]:
    """Anexo 3.2 — Suministros, valor fijo (TARIFA FINAL si trae IVA)."""
    idx_cod_prest = _indice_columna(headers, "CODIGO DEL PRESTADOR")
    idx_mapiiss = _indice_columna(headers, "MAPIISS")
    idx_desc = _indice_columna(headers, "DESCRIPCION DEL PRESTADOR", "DESCRIPCION", "DESCRIPCIÓN")
    idx_agrup = _indice_columna(headers, "AGRUPADOR")
    idx_unitaria = _indice_columna(headers, "TARIFA UNITARIA")
    idx_final = _indice_columna(headers, "TARIFA FINAL")
    idx_iva = _indice_columna(headers, "APLICA IVA")

    idx_codigo = idx_cod_prest if idx_cod_prest is not None else idx_mapiiss
    if idx_codigo is None:
        return []

    filas: list[dict] = []
    for fila_idx in range(fila_encabezado + 1, ws.max_row + 1):
        cod_raw = ws.cell(row=fila_idx, column=idx_codigo + 1).value
        if not cod_raw:
            continue
        codigo = str(cod_raw).strip()
        if not codigo or not re.search(r"[A-Za-z0-9]", codigo):
            continue
        desc = str(ws.cell(row=fila_idx, column=idx_desc + 1).value or "").strip() if idx_desc is not None else ""

        iva_si = False
        if idx_iva is not None:
            iva_val = str(ws.cell(row=fila_idx, column=idx_iva + 1).value or "").strip().upper()
            iva_si = iva_val in ("SI", "SÍ", "S", "YES", "Y", "1")

        # Estrategia: si APLICA IVA=SI y hay TARIFA FINAL válida → usarla.
        # Si APLICA IVA=NO → TARIFA UNITARIA (ya es final).
        valor = 0.0
        if iva_si and idx_final is not None:
            valor = _normalizar_valor(ws.cell(row=fila_idx, column=idx_final + 1).value)
        if valor <= 0 and idx_unitaria is not None:
            valor_unit = _normalizar_valor(ws.cell(row=fila_idx, column=idx_unitaria + 1).value)
            valor = valor_unit * (1.19 if iva_si else 1.0)
        if valor <= 0:
            continue

        agrup = str(ws.cell(row=fila_idx, column=idx_agrup + 1).value or "").strip() if idx_agrup is not None else ""
        filas.append({
            "codigo_cups": codigo,
            "descripcion": desc[:500] if desc else None,
            "valor_pactado": round(valor, 2),
            "modalidad": (agrup or "SUMINISTROS")[:80],
            "tipo_tarifa": "VALOR_FIJO",
            "factor_ajuste": 0.0,
            "observacion": None,
        })
    return filas


# ─── API pública ────────────────────────────────────────────────────────────

def parsear_excel_tarifas(contenido: bytes, filename: str = "") -> dict:
    """Parsea un Excel de tarifas contratadas (tipo Famisanar) de 1-3 hojas.

    Retorna:
        {
          "eps": str | None,
          "contrato": str | None,
          "vigencia_desde": datetime | None,
          "vigencia_hasta": datetime | None,
          "filas": [ { codigo_cups, descripcion, valor_pactado, modalidad,
                       tipo_tarifa, factor_ajuste, observacion }, ... ],
          "hojas_detectadas": [ "ANEXO3", "ANEXO31", "ANEXO32" ],
          "errores": [ str, ... ],
        }
    """
    errores: list[str] = []
    try:
        wb = load_workbook(BytesIO(contenido), data_only=True, read_only=False)
    except Exception as e:
        return {
            "eps": None, "contrato": None,
            "vigencia_desde": None, "vigencia_hasta": None,
            "filas": [], "hojas_detectadas": [],
            "errores": [f"No se pudo abrir el archivo: {type(e).__name__}: {e}"],
        }

    meta_global = {"eps": None, "contrato": None, "vigencia_desde": None, "vigencia_hasta": None}
    filas_total: list[dict] = []
    hojas_detectadas: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if ws.max_row < 2:
            continue
        try:
            meta = _extraer_metadata(ws)
            for k in meta_global:
                if meta.get(k) and not meta_global[k]:
                    meta_global[k] = meta[k]

            fila_hdr, headers = _buscar_fila_encabezado(ws)
            if fila_hdr is None:
                continue
            tipo = _tipo_hoja(headers)
            if tipo is None:
                continue
            hojas_detectadas.append(f"{tipo}:{sheet_name}")
            if tipo == "ANEXO3":
                nuevas = _parsear_anexo3(ws, fila_hdr, headers)
            elif tipo == "ANEXO31":
                nuevas = _parsear_anexo31(ws, fila_hdr, headers)
            elif tipo == "ANEXO32":
                nuevas = _parsear_anexo32(ws, fila_hdr, headers)
            else:
                nuevas = []
            filas_total.extend(nuevas)
        except Exception as e:
            errores.append(f"Hoja '{sheet_name}': {type(e).__name__}: {e}")
            continue

    return {
        "eps": meta_global["eps"],
        "contrato": meta_global["contrato"],
        "vigencia_desde": meta_global["vigencia_desde"],
        "vigencia_hasta": meta_global["vigencia_hasta"],
        "filas": filas_total,
        "hojas_detectadas": hojas_detectadas,
        "errores": errores,
    }
