"""
noticias_salud_co.py — Fetcher de noticias del sector salud Colombia.

Fuentes (RSS-first, scraping como fallback):

  ConsultorSalud  → https://consultorsalud.com/feed/  (RSS oficial)
  MinSalud         → https://www.minsalud.gov.co/sala-de-prensa/  (HTML scrape)
  ACHC             → https://achc.org.co/feed/  (RSS si existe)
  Acemi            → https://acemi.org.co/  (HTML scrape)

Estrategia robusta:
  1. Cada fuente es un fetcher pluggable con su propia función.
  2. Si una fuente falla (timeout, HTML cambió, RSS roto), las demás
     continúan trayendo noticias.
  3. Dedupe por hash(titulo + url): la misma noticia traída de
     varias fuentes solo se guarda una vez.
  4. Cap de 50 noticias activas — si llegan más, marcamos las viejas
     como activa=0 para no inflar la BD.

Llamado por el scheduler `noticias_scheduler.py` cada 4 horas.
"""
from __future__ import annotations
import os
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx

logger = logging.getLogger("motor_glosas")


# URLs configurables vía env var (cuando una fuente cambia, el admin
# puede reapuntar sin redeploy). Defaults conocidos al cierre 2026-05.
FUENTES_RSS = {
    "consultorsalud": os.getenv(
        "RSS_CONSULTORSALUD",
        "https://consultorsalud.com/feed/",
    ),
    "achc": os.getenv(
        "RSS_ACHC",
        "https://achc.org.co/feed/",
    ),
}

FUENTES_HTML_SCRAPE = {
    "minsalud": os.getenv(
        "URL_MINSALUD_PRENSA",
        "https://www.minsalud.gov.co/sala-de-prensa/Paginas/default.aspx",
    ),
}


def _hash_unico(titulo: str, url: str) -> str:
    """SHA-256 trunc 16 chars para dedupe noticia."""
    base = (titulo or "").strip().lower() + "|" + (url or "").strip().lower()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def _categorizar(titulo: str, resumen: str) -> str:
    """Heurística simple para asignar categoría según palabras clave."""
    t = ((titulo or "") + " " + (resumen or "")).lower()
    if any(w in t for w in ("decreto", "resolución", "ley ", "circular")):
        return "NORMATIVA"
    if any(w in t for w in ("alerta", "urgente", "emergencia", "brote")):
        return "ALERTA"
    if any(w in t for w in ("opinión", "editorial", "columna")):
        return "OPINION"
    return "NOTICIA"


async def fetch_rss(url: str, fuente: str, max_items: int = 10) -> list[dict]:
    """Fetcha un feed RSS y devuelve lista de items normalizados.

    Devuelve [] si falla (no levanta — el caller continúa con otras fuentes).
    """
    try:
        import feedparser
    except ImportError:
        logger.warning("[NOTICIAS] feedparser no instalado — saltando RSS")
        return []

    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    # User-Agent realista para no ser bloqueado por anti-bot
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                },
            )
        logger.info(f"[NOTICIAS:{fuente}] GET {url} → HTTP {resp.status_code} ({len(resp.content)} bytes)")
        if resp.status_code != 200:
            return []
    except Exception as e:
        logger.warning(f"[NOTICIAS:{fuente}] Error fetch ({url}): {e}")
        return []

    parsed = feedparser.parse(resp.text)
    if parsed.bozo and parsed.bozo_exception:
        logger.warning(f"[NOTICIAS:{fuente}] feedparser warning: {parsed.bozo_exception}")
    logger.info(f"[NOTICIAS:{fuente}] feedparser entries={len(parsed.entries or [])}")
    items = []
    for entry in (parsed.entries or [])[:max_items]:
        titulo = (entry.get("title") or "").strip()
        if not titulo:
            continue
        link = (entry.get("link") or "").strip()
        # Resumen: prefiere `summary`, luego `description`. Limpia HTML básico.
        resumen_raw = entry.get("summary") or entry.get("description") or ""
        import re as _re
        resumen = _re.sub(r"<[^>]+>", " ", resumen_raw)
        resumen = _re.sub(r"\s+", " ", resumen).strip()[:500]

        # Fecha publicación: distintos campos según el feed
        fecha = None
        for fld in ("published_parsed", "updated_parsed"):
            if entry.get(fld):
                try:
                    import time as _time
                    fecha = datetime.fromtimestamp(_time.mktime(entry[fld]), tz=timezone.utc)
                    break
                except Exception:
                    pass

        items.append({
            "titulo": titulo[:480],
            "resumen": resumen or None,
            "url": link[:780] if link else None,
            "fuente": fuente,
            "fecha_publicacion": fecha,
            "categoria": _categorizar(titulo, resumen),
            "hash_unico": _hash_unico(titulo, link),
        })
    if items:
        logger.info(f"[NOTICIAS:{fuente}] {len(items)} items extraídos")
    return items


async def fetch_html_scrape_minsalud(url: str, max_items: int = 10) -> list[dict]:
    """Scraper específico para minsalud.gov.co/sala-de-prensa.

    Usa regex simple sobre el HTML — frágil pero sin deps extra. Si el
    sitio cambia su estructura, devuelve [] sin romper.
    """
    try:
        timeout = httpx.Timeout(connect=10.0, read=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Motor-Glosas-HUS/1.0"})
        if resp.status_code != 200:
            return []
    except Exception as e:
        logger.warning(f"[NOTICIAS:minsalud] Error fetch: {e}")
        return []

    import re as _re
    # Patrón heurístico para enlaces a noticias: <a href="...Noticias..."
    # title="..." o texto del link. Como minsalud cambia layout a menudo,
    # esto es best-effort. Si no encuentra nada, devolverá [].
    pat = _re.compile(
        r'<a[^>]+href="([^"]*[Nn]oticias?[^"]*)"[^>]*>\s*([^<]{20,200})\s*</a>',
        _re.IGNORECASE,
    )
    matches = pat.findall(resp.text)
    seen = set()
    items = []
    for href, titulo in matches:
        if len(items) >= max_items:
            break
        titulo_clean = _re.sub(r"\s+", " ", titulo).strip()
        if not titulo_clean or titulo_clean.lower() in seen:
            continue
        seen.add(titulo_clean.lower())
        # Hacer URL absoluta si es relativa
        if href.startswith("/"):
            href = "https://www.minsalud.gov.co" + href
        items.append({
            "titulo": titulo_clean[:480],
            "resumen": None,
            "url": href[:780],
            "fuente": "minsalud",
            "fecha_publicacion": None,  # scraping no nos da fecha confiable
            "categoria": _categorizar(titulo_clean, ""),
            "hash_unico": _hash_unico(titulo_clean, href),
        })
    if items:
        logger.info(f"[NOTICIAS:minsalud] {len(items)} items extraídos por scraping")
    return items


async def fetch_todas_las_fuentes(max_por_fuente: int = 8) -> list[dict]:
    """Fetcha todas las fuentes en paralelo y devuelve lista combinada."""
    import asyncio
    tareas = []
    for fuente, url in FUENTES_RSS.items():
        tareas.append(fetch_rss(url, fuente, max_items=max_por_fuente))
    for fuente, url in FUENTES_HTML_SCRAPE.items():
        if fuente == "minsalud":
            tareas.append(fetch_html_scrape_minsalud(url, max_items=max_por_fuente))

    resultados = await asyncio.gather(*tareas, return_exceptions=True)
    todos = []
    for r in resultados:
        if isinstance(r, list):
            todos.extend(r)
        else:
            logger.warning(f"[NOTICIAS] Fuente falló: {r}")
    return todos


def upsert_noticias(items: list[dict]) -> dict:
    """Inserta noticias nuevas en BD. Dedupe por hash_unico.

    Marca como inactivas las > 30 días para no inflar la tabla.
    Devuelve dict con conteos: {nuevas, ya_existian, archivadas}.
    """
    from app.database import SessionLocal
    from app.models.db import NoticiaSaludRecord
    from datetime import timedelta

    db = SessionLocal()
    nuevas = 0
    ya_existian = 0
    archivadas = 0
    try:
        # Hashes ya en BD
        hashes_existentes = {
            h[0] for h in db.query(NoticiaSaludRecord.hash_unico).all()
        }
        for item in items:
            if item["hash_unico"] in hashes_existentes:
                ya_existian += 1
                continue
            db.add(NoticiaSaludRecord(
                titulo=item["titulo"],
                resumen=item["resumen"],
                url=item["url"],
                fuente=item["fuente"],
                fecha_publicacion=item.get("fecha_publicacion"),
                hash_unico=item["hash_unico"],
                categoria=item.get("categoria") or "NOTICIA",
                activa=1,
            ))
            nuevas += 1
        db.commit()

        # Archivar > 30 días
        umbral = datetime.now(timezone.utc) - timedelta(days=30)
        archivadas = (
            db.query(NoticiaSaludRecord)
            .filter(
                NoticiaSaludRecord.indexada_en < umbral,
                NoticiaSaludRecord.activa == 1,
            )
            .update({"activa": 0})
        )
        db.commit()
    except Exception as e:
        logger.error(f"[NOTICIAS] Error upsert: {e}")
        db.rollback()
    finally:
        db.close()

    logger.info(
        f"[NOTICIAS] Upsert: nuevas={nuevas} ya_existian={ya_existian} archivadas={archivadas}"
    )
    return {"nuevas": nuevas, "ya_existian": ya_existian, "archivadas": archivadas}


async def actualizar_noticias() -> dict:
    """Punto de entrada del scheduler. Fetcha + upsert. Devuelve stats."""
    items = await fetch_todas_las_fuentes()
    if not items:
        logger.info("[NOTICIAS] Ningún item recuperado de las fuentes")
        return {"nuevas": 0, "ya_existian": 0, "archivadas": 0}
    return upsert_noticias(items)
