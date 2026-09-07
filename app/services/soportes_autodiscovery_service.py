"""Auto-descubrimiento de soportes en el share de radicación.

El share de cartera tiene la estructura:

    {SOPORTES_ROOT}/
      {MES} {AÑO} - SOPORTES RADICACION/
        1. DD FACTURACION/
          ESCANEO/
            {EPS}/
              ENV-{lote}[-OK]/
                FEV_{nit}_{factura}.pdf       ← Factura electrónica
                HEV_{nit}_{factura}.pdf       ← Historia clínica / Epicrisis
                CRC_{nit}_{factura}.PDF       ← Comprobante recibido a cobro
                OPF_{nit}_{factura}.pdf       ← Otros procedimientos
                PDE_{nit}_{factura}.pdf
                PDX_{nit}_{factura}.pdf
                Rips_{factura}.json           ← RIPS
                FURIPS{...}.txt               ← FURIPS plano
                ResultadosMSPS_{factura}_*    ← Resultados validador
                ad{...}.xml                   ← XML CUFE

La llave de búsqueda es el número de factura embebido en el nombre del
archivo. Normalizamos quitando ceros a la izquierda y comparamos por la
parte numérica para tolerar formatos `HUS487523` vs `HUS0000495050`.

El indexador se construye on-demand y cachea en memoria. La salida del
lookup es una lista de soportes con metadata (tipo, ruta absoluta, EPS,
ENV, mes, tamaño) lista para inyectar en el flujo de análisis.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("motor_glosas.soportes")

# Prefijos de soportes reconocidos. El orden importa para `clasificar` —
# patrones más específicos primero.
TIPOS_SOPORTE = {
    "FEV": "factura_electronica",
    # FVS = Factura de Venta en Salud (código ADRES). El servidor de
    # radicación del HUS nombra la factura así: FVS_900006037_HUSxxxx.pdf.
    # Sin esta entrada esos PDF quedaban etiquetados «otro» en vez de la
    # factura, aunque sí se encontraban por número. 18-08-2026.
    "FVS": "factura_electronica",
    "HEV": "historia_clinica",
    # Códigos del anexo técnico que el servidor de radicación sí usa y que el
    # indexador no reconocía. Se vieron el 19-08-2026 en la factura HUS468334,
    # respondiendo una glosa SO0201 por «ausencia de soportes de la CONSULTA DE
    # URGENCIAS»: el documento que prueba esa consulta es justamente la HAU, y
    # el sistema la tenía como archivo suelto. De doce soportes, seis quedaban
    # sin clasificar — y como el Auditor Forense escoge por tipo, la epicrisis
    # y la hoja de medicamentos competían de últimas.
    "EPI": "epicrisis",
    "HAM": "hoja_administracion_medicamentos",
    "HAU": "hoja_atencion_urgencias",
    "CRC": "comprobante_recibido_cobro",
    "OPF": "otros_procedimientos",
    "PDE": "pde",
    "PDX": "pdx",
    "RIPS": "rips",
    "FURIPS": "furips",
    "RESULTADOSMSPS": "resultados_msps",
    "AD": "xml_cufe",
}

# Regex para extraer factura del filename. Acepta `HUS` + dígitos
# variables (HUS487523, HUS0000495050). No usamos \b porque el char
# previo suele ser `_` (word char) lo que invalida el boundary.
_RE_FACTURA = re.compile(r"(HUS\d{4,12})", re.IGNORECASE)
# Mes inicial de la carpeta raíz: "ABRIL 2026 - SOPORTES RADICACION"
_MESES = (
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)
# Las carpetas reales del 2026 llevan un ordinal delante: "8. AGOSTO 2026 -
# SOPORTES RADICACION". Sin tolerar ese "8. " (o "12. ") el mes, el año y —lo
# que de verdad importa— la EPS de cada soporte salían vacíos. 18-08-2026.
_RE_MES_RAIZ = re.compile(
    r"^\s*(?:\d{1,2}\.?\s*)?(" + "|".join(_MESES) + r")\s+(\d{4})\s*-\s*SOPORTES",
    re.IGNORECASE,
)


@dataclass
class SoporteEntry:
    factura: str  # `HUS487523` (raw, como aparece en el filename)
    factura_norm: str  # solo dígitos sin ceros a la izquierda
    tipo: str  # `factura_electronica`, `historia_clinica`, etc.
    tipo_codigo: str  # `FEV`, `HEV`, etc.
    ruta: str  # path absoluto
    nombre_archivo: str
    extension: str
    eps: Optional[str]  # carpeta EPS
    env: Optional[str]  # carpeta ENV-NNN
    mes: Optional[str]  # ABRIL
    anio: Optional[int]  # 2026
    tamano_kb: int  # sin ñ para compat JSON con front-end
    fecha_mod: float  # epoch


def normalizar_factura(factura: str) -> str:
    """Normaliza una factura para matching robusto.

    `HUS487523` → `487523`. `HUS0000495050` → `495050`. Tolera prefijos
    en minúscula y otros formatos. Si no hay parte numérica, devuelve
    cadena vacía.
    """
    if not factura:
        return ""
    m = re.search(r"\d+", factura)
    if not m:
        return ""
    return m.group(0).lstrip("0") or "0"


def _clasificar_archivo(nombre: str) -> Optional[tuple[str, str]]:
    """Devuelve (tipo_codigo, tipo_descripcion) o None si no coincide.

    Match insensible a mayúsculas. Usamos prefijo + delimitador (`_` o
    espacio) para no confundir `RIPS` con `FURIPS`.
    """
    n = nombre.upper()
    # Patrones específicos primero
    if n.startswith("FURIPS"):
        return ("FURIPS", TIPOS_SOPORTE["FURIPS"])
    if n.startswith("RESULTADOSMSPS"):
        return ("RESULTADOSMSPS", TIPOS_SOPORTE["RESULTADOSMSPS"])
    if n.startswith("RIPS_") or n.startswith("RIPS "):
        return ("RIPS", TIPOS_SOPORTE["RIPS"])
    for prefijo, descripcion in TIPOS_SOPORTE.items():
        if prefijo in ("FURIPS", "RESULTADOSMSPS", "RIPS"):
            continue
        if n.startswith(prefijo + "_") or n.startswith(prefijo + " "):
            return (prefijo, descripcion)
    # XML CUFE: típicamente `ad{19}numeros{...}.xml`
    if n.startswith("AD") and n.endswith(".XML"):
        return ("AD", TIPOS_SOPORTE["AD"])
    # El servidor de radicación nombra estos tres SOLO con el número de
    # factura —`HUS468334.json`, `HUS468334.xml`, `HUS468334_CUV.json`—, sin
    # prefijo que los delate. Se reconocen por la extensión. 19-08-2026.
    if n.endswith(".XML"):
        return ("AD", TIPOS_SOPORTE["AD"])
    if n.endswith(".JSON"):
        if "CUV" in n:
            return ("CUV", "cuv")
        return ("RIPS", TIPOS_SOPORTE["RIPS"])
    return None


# Carpetas del servidor que NO son una EPS: son pasos del archivado.
_CARPETAS_ESTRUCTURALES = {
    "DD FACTURACION",
    "ESCANEO",
    "RIPS",
    "SOPORTES",
    "CORRESPONDENCIA",
}


def _nombre_estructural(nombre: str) -> bool:
    """True si la carpeta es un paso del archivado y no el nombre de una EPS.

    Tolera el ordinal delante y los espacios: «1. DD FACTURACION»,
    «1.DD FACTURACION» y «DD  FACTURACION» son la misma carpeta.
    """
    limpio = re.sub(r"^\s*\d{1,2}\s*\.\s*", "", str(nombre or "").upper())
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio in _CARPETAS_ESTRUCTURALES


def _extraer_metadata_path(p: Path, raiz: Path) -> dict:
    """Extrae mes, año, EPS y ENV recorriendo el path desde la raíz.

    Estructuras soportadas:
      1. {MES AÑO - SOPORTES RADICACION}/{EPS}/{Persona}/ENV-NNN/.../archivo
         (formato 2026 — más común)
      2. {MES AÑO - ...}/1. DD FACTURACION/ESCANEO/{EPS}/ENV-NNN/...
         (formato histórico con escaneo intermedio)
    """
    try:
        rel = p.relative_to(raiz)
    except ValueError:
        return {}
    partes = rel.parts
    meta: dict = {}
    upper_parts = [pp.upper() for pp in partes]

    # Mes raíz
    for i, parte in enumerate(partes):
        m = _RE_MES_RAIZ.match(parte)
        if m:
            meta["mes"] = m.group(1).upper()
            try:
                meta["anio"] = int(m.group(2))
            except ValueError:
                pass
            # La EPS es lo que viene DESPUÉS del mes, salvo que sea una
            # carpeta estructural (DD FACTURACION, ESCANEO, RIPS…).
            #
            # 19-08-2026 — La lista se comparaba tal cual y decía
            # "1. DD FACTURACION" CON espacio; en el servidor real la carpeta
            # se llama "1.DD FACTURACION" SIN espacio, así que no coincidía y
            # se tomaba como si fuera la EPS: los soportes de ALIANZA MEDELLIN
            # salían con EPS = "1.DD FACTURACION". Ahora se compara sin el
            # ordinal y sin espacios de sobra, para que dé igual cómo esté
            # escrito.
            for j in range(i + 1, len(partes)):
                pj_up = upper_parts[j]
                if (
                    _nombre_estructural(pj_up)
                    or "SOPORTES RADICACION" in pj_up
                    or pj_up.startswith("ENV-")
                ):
                    continue
                meta["eps"] = partes[j]
                break
            break

    # ENV (carpeta de envío/lote)
    for parte in partes:
        if parte.upper().startswith("ENV-"):
            meta["env"] = parte
            break
    return meta


def _raiz_configurada() -> Optional[str]:
    """Lee la carpeta de soportes de `config/soportes_root.txt`, si existe.

    Un archivo local (no versionado) con una sola línea, por ejemplo:
        \\\\Prime\\radicacion_2026
    Así el auditor cambia el servidor sin tocar código y sin que el autodeploy
    se lo borre. Si no está, devuelve None y se usan las variables de entorno.
    """
    try:
        ruta = Path(__file__).resolve().parent.parent.parent / "config" / "soportes_root.txt"
        if not ruta.is_file():
            return None
        for linea in ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            valor = linea.strip().strip('"').strip("'")
            if valor and not valor.startswith("#"):
                return valor
    except OSError:
        return None
    return None


def raiz_de_soportes() -> str:
    """La carpeta de soportes del hospital. UNA sola respuesta para todos.

    20-08-2026. El indexador resolvía la carpeta acá y el router de subida la
    resolvía por su cuenta, en otro orden — y sin leer `config/soportes_root.txt`,
    que es justamente donde el hospital dejó escrita la suya. El auditor subía
    un .zip, el motor decía «subido», y los PDFs quedaban en una carpeta que el
    índice nunca recorre: buscaba la factura, no aparecía, y no había manera de
    entender por qué.

    Dos lugares decidiendo lo mismo con reglas distintas es un defecto
    esperando el momento. Acá queda uno solo.

    Orden:
      1. `config/soportes_root.txt` — la carpeta que escogió el hospital. Va
         primero a propósito: el vigilante que revive el motor conserva las
         variables de cuando ÉL arrancó, así que cambiar el .cmd no servía de
         nada hasta reiniciar el vigilante entero.
      2. `SOPORTES_ROOT` — mount directo del share.
      3. `SOPORTES_LOCAL_ROOT` — el agente sube por HTTP y el motor escribe acá.
      4. `/tmp/motor-soportes` — sin configurar nada.
    """
    return (
        _raiz_configurada()
        or os.getenv("SOPORTES_ROOT")
        or os.getenv("SOPORTES_LOCAL_ROOT")
        or "/tmp/motor-soportes"
    )


class SoportesIndexer:
    """Indexador on-demand del share de soportes.

    Construye un mapa `{factura_normalizada: [SoporteEntry, ...]}` y lo
    cachea en memoria. La reconstrucción se dispara explícitamente
    (`rebuild()`) o automáticamente si pasaron más de `ttl_segundos`
    desde el último build.
    """

    def __init__(self, raiz: Optional[str] = None, ttl_segundos: int = 6 * 3600):
        # Resolución de raíz (orden de prioridad):
        #   1. arg explícito (tests / overrides)
        #   2. SOPORTES_ROOT (Plan A — mount CIFS directo)
        #   3. SOPORTES_LOCAL_ROOT (Plan B — jump-box agent sube acá)
        #   4. default /tmp/motor-soportes (Plan B sin config — coincide
        #      con el default de _local_root en el router de upload, así
        #      que el motor lee exactamente lo que el agente subió).
        #   1.b config/soportes_root.txt — la carpeta que escogió el hospital.
        #      Va ANTES de las variables de entorno a propósito: el vigilante
        #      que revive el motor guarda las variables de cuando ÉL arrancó,
        #      así que cambiar el .cmd no servía de nada hasta reiniciar el
        #      vigilante entero. Leyendo el archivo acá, el motor toma la
        #      carpeta correcta arranque como arranque. 18-08-2026.
        if raiz is None:
            raiz = raiz_de_soportes()
        self.raiz = Path(raiz)
        # Crear si no existe — el agente puede subir antes del primer
        # rebuild. Sin esto el indexador reporta "raíz no existe" aunque
        # el upload-bulk sí esté funcionando.
        try:
            self.raiz.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.ttl_segundos = ttl_segundos
        self._lock = threading.Lock()
        self._indice: dict[str, list[SoporteEntry]] = {}
        self._construido_en: float = 0.0
        self._ultimo_error: Optional[str] = None
        self._archivos_escaneados: int = 0
        self._archivos_indexados: int = 0
        self._construyendo: bool = False
        # Escaneo diferencial (04-09-2026): huella de cada carpeta ya vista,
        # para no volver a listarla si no ha cambiado.
        self._firmas: dict[str, tuple[float, int]] = {}
        self._carpetas_saltadas: int = 0
        self._cargado_de_disco: bool = False
        self._cargar_de_disco()

    def _esta_caliente(self) -> bool:
        if not self._indice:
            return False
        return (time.time() - self._construido_en) < self.ttl_segundos

    # ── El índice sobrevive al reinicio (04-09-2026) ────────────────────
    #
    # ANTES: el índice vivía SOLO en memoria. Cada reinicio de uvicorn —y hay
    # varios al día por el autodespliegue— lo borraba, y el motor volvía a
    # recorrer 473.581 archivos por red: horas. Durante todo ese rato el
    # buscador de soportes contestaba vacío.
    #
    # AHORA se guarda en disco y se recupera al arrancar. El motor abre con el
    # índice de la última vez —utilizable desde el primer segundo— y encima
    # la reconstrucción salta las carpetas que no han cambiado.

    def _ruta_cache(self) -> Path:
        return Path(__file__).resolve().parents[2] / "data" / "soportes_indice.json"

    def _cargar_de_disco(self) -> None:
        """Recupera el índice de la corrida anterior. Nunca revienta: si el
        archivo no está o quedó a medias, se sigue como antes (desde cero)."""
        ruta = self._ruta_cache()
        try:
            if not ruta.is_file():
                return
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            # Si cambió la raíz, el índice viejo no sirve para nada.
            if str(datos.get("raiz") or "") != str(self.raiz):
                logger.info("[SOPORTES] El índice guardado es de otra carpeta; se ignora.")
                return
            indice: dict[str, list[SoporteEntry]] = {}
            for factura, filas in (datos.get("indice") or {}).items():
                indice[factura] = [SoporteEntry(**fila) for fila in filas]
            self._indice = indice
            self._firmas = {k: (v[0], v[1]) for k, v in (datos.get("firmas") or {}).items()}
            self._construido_en = float(datos.get("construido_en") or 0.0)
            self._archivos_indexados = int(datos.get("archivos_indexados") or 0)
            self._cargado_de_disco = True
            logger.info(
                f"[SOPORTES] Índice recuperado del disco: {len(self._indice)} facturas, "
                f"{self._archivos_indexados} archivos. No hay que empezar de cero."
            )
        except Exception as e:  # noqa: BLE001 — un caché ilegible no tumba el motor
            logger.warning(f"[SOPORTES] No se pudo recuperar el índice guardado: {e}")

    def _guardar_en_disco(self) -> None:
        """Deja el índice listo para el próximo arranque. Se escribe a un
        temporal y se renombra: si se corta la luz a mitad, el archivo bueno
        de la vez pasada sigue intacto."""
        ruta = self._ruta_cache()
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            datos = {
                "raiz": str(self.raiz),
                "construido_en": self._construido_en,
                "archivos_indexados": self._archivos_indexados,
                "firmas": {k: list(v) for k, v in self._firmas.items()},
                "indice": {
                    factura: [asdict(e) for e in filas] for factura, filas in self._indice.items()
                },
            }
            tmp = ruta.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
            tmp.replace(ruta)
            logger.info(f"[SOPORTES] Índice guardado en {ruta.name}")
        except Exception as e:  # noqa: BLE001 — no poder guardar no invalida el índice
            logger.warning(f"[SOPORTES] No se pudo guardar el índice: {e}")

    def _entradas_por_carpeta(self) -> dict[str, list[SoporteEntry]]:
        """Lo ya sabido, ordenado por la carpeta donde vive cada archivo.

        Es lo que permite reusar una carpeta intacta sin volver a leerla.
        """
        por_carpeta: dict[str, list[SoporteEntry]] = {}
        for filas in self._indice.values():
            for entry in filas:
                try:
                    padre = str(Path(entry.ruta).parent)
                except Exception:  # noqa: BLE001
                    continue
                por_carpeta.setdefault(padre, []).append(entry)
        return por_carpeta

    @staticmethod
    def _recorrer_carpetas(raiz: Path):
        """Todas las carpetas colgando de la raíz, la raíz incluida.

        Se usa `os.walk`, que va listando sin traerse el árbol entero a
        memoria: en el servidor de radicación hay cientos de miles de
        archivos y cargarlos de golpe no cabe.
        """
        yield raiz
        for actual, subcarpetas, _archivos in os.walk(raiz, onerror=lambda e: None):
            for sub in subcarpetas:
                yield Path(actual) / sub

    @staticmethod
    def _firma_de(carpeta: Path) -> Optional[tuple[float, int]]:
        """Huella barata de una carpeta: cuándo cambió y cuántas cosas tiene.

        Con esas dos, si nada cambió, no hace falta volver a mirar archivo por
        archivo —que es lo caro cuando la carpeta vive en el servidor de red.
        """
        try:
            with os.scandir(carpeta) as it:
                n = sum(1 for _ in it)
            return (carpeta.stat().st_mtime, n)
        except OSError:
            return None

    def _construir_entry(
        self,
        archivo: Path,
        factura_raw: str,
        factura_norm: str,
    ) -> SoporteEntry:
        nombre = archivo.name
        clas = _clasificar_archivo(nombre)
        tipo_cod, tipo_desc = clas if clas else ("OTRO", "otro")
        meta = _extraer_metadata_path(archivo, self.raiz)
        try:
            st = archivo.stat()
            # Si el archivo es <1KB, redondeamos hacia arriba para que
            # NO muestre "0 KB" en la UI (cosmético).
            tamano_kb = max(1, st.st_size // 1024) if st.st_size > 0 else 0
            fmod = st.st_mtime
        except OSError:
            tamano_kb = 0
            fmod = 0.0
        return SoporteEntry(
            factura=factura_raw,
            factura_norm=factura_norm,
            tipo=tipo_desc,
            tipo_codigo=tipo_cod,
            ruta=str(archivo),
            nombre_archivo=nombre,
            extension=archivo.suffix.lower().lstrip("."),
            eps=meta.get("eps"),
            env=meta.get("env"),
            mes=meta.get("mes"),
            anio=meta.get("anio"),
            tamano_kb=tamano_kb,
            fecha_mod=fmod,
        )

    def rebuild(self) -> dict:
        """Reconstruye el índice completo. Devuelve estadísticas.

        Estrategia de dos pasadas:

        1. Pasa 1 — recorre todos los archivos. Si el filename contiene
           `HUS\\d+`, lo asocia a esa factura. Si no, lo guarda como
           "compartido del lote" agrupado por carpeta padre (ENV).

        2. Pasa 2 — para cada carpeta padre con compartidos, los asocia
           a TODAS las facturas detectadas en esa carpeta. Esto cubre
           FURIPS, XML CUFE y ResultadosMSPS que vienen a nivel de lote.
        """
        # 18-08-2026 — El candado se pedía bloqueando. Con el servidor real
        # (miles de archivos por red) el recorrido dura minutos, y CUALQUIER
        # otra petición que tocara el índice —una búsqueda, por ejemplo— se
        # quedaba esperando su turno hasta que el proxy la cortaba con un
        # «Error 524». Ahora, si ya hay una reconstrucción en curso, esta se
        # devuelve de inmediato en vez de hacer cola.
        if not self._lock.acquire(blocking=False):
            logger.info("Ya hay una reconstrucción de soportes en curso; no se arranca otra.")
            return self.stats()
        try:
            self._construyendo = True
            inicio = time.time()
            # EL ÍNDICE VIEJO NO SE BORRA (04-09-2026). Antes se hacía
            # `self._indice = {}` aquí, y durante las HORAS que dura el
            # recorrido el buscador contestaba vacío a todo el mundo: el motor
            # quedaba ciego justo mientras trabajaba. Ahora se construye uno
            # nuevo aparte y se cambia de golpe al final; mientras tanto se
            # sigue respondiendo con el de la última vez.
            nuevo_indice: dict[str, list[SoporteEntry]] = {}
            nuevas_firmas: dict[str, tuple[float, int]] = {}
            self._archivos_escaneados = 0
            self._archivos_indexados = 0
            self._carpetas_saltadas = 0
            self._ultimo_error = None

            if not self.raiz.exists():
                self._ultimo_error = f"Raíz no existe: {self.raiz}"
                logger.warning(self._ultimo_error)
                return self.stats()
            if not self.raiz.is_dir():
                self._ultimo_error = f"Raíz no es directorio: {self.raiz}"
                logger.warning(self._ultimo_error)
                return self.stats()

            # Pasa 1: con-factura vs sin-factura por carpeta padre
            facturas_por_carpeta: dict[Path, set[tuple[str, str]]] = {}
            compartidos_por_carpeta: dict[Path, list[Path]] = {}

            # ESCANEO DIFERENCIAL. Se recorren las carpetas una por una; si
            # una carpeta tiene la misma huella que la última vez (misma fecha
            # de cambio y misma cantidad de elementos), NO se vuelve a mirar
            # archivo por archivo: se reusa lo que ya se sabía de ella. Eso es
            # lo caro cuando la carpeta está al otro lado de la red.
            cache_por_carpeta = self._entradas_por_carpeta()

            for carpeta in self._recorrer_carpetas(self.raiz):
                firma = self._firma_de(carpeta)
                clave = str(carpeta)
                if firma is not None:
                    nuevas_firmas[clave] = firma

                # Ojo con el `or []`: una carpeta intacta se salta AUNQUE no
                # tenga archivos indexados. Las carpetas intermedias del árbol
                # (año, mes, EPS…) son la mayoría y no indexan nada; si se
                # releyeran todas, el escaneo diferencial no ahorraría casi
                # nada. Lo que manda es la firma, no que hubiera contenido.
                reutilizables = cache_por_carpeta.get(clave) or []
                if firma is not None and self._firmas.get(clave) == firma:
                    # Carpeta intacta: se reusa tal cual.
                    # Se reusa TODO lo de esa carpeta —incluidos los
                    # compartidos del lote (FURIPS, XML CUFE), que ya venían
                    # asociados a su factura en la corrida anterior—, así que
                    # no hace falta rehacer la pasada 2 para ella.
                    self._carpetas_saltadas += 1
                    for entry in reutilizables:
                        nuevo_indice.setdefault(entry.factura_norm, []).append(entry)
                        self._archivos_indexados += 1
                    continue

                # Carpeta nueva o cambiada: se mira de verdad.
                try:
                    with os.scandir(carpeta) as it:
                        hijos = [Path(e.path) for e in it if e.is_file()]
                except OSError as e:
                    logger.debug(f"[SOPORTES] No se pudo leer {carpeta}: {e}")
                    continue

                for archivo in hijos:
                    self._archivos_escaneados += 1
                    nombre = archivo.name
                    m = _RE_FACTURA.search(nombre)
                    if m:
                        factura_raw = m.group(1).upper()
                        factura_norm = normalizar_factura(factura_raw)
                        if not factura_norm:
                            continue
                        entry = self._construir_entry(archivo, factura_raw, factura_norm)
                        nuevo_indice.setdefault(factura_norm, []).append(entry)
                        self._archivos_indexados += 1
                        facturas_por_carpeta.setdefault(carpeta, set()).add(
                            (factura_raw, factura_norm)
                        )
                    else:
                        # Solo nos interesan compartidos clasificables (FURIPS,
                        # XML CUFE, ResultadosMSPS). Files random como
                        # leeme.txt se ignoran.
                        if _clasificar_archivo(nombre) is not None:
                            compartidos_por_carpeta.setdefault(carpeta, []).append(archivo)

            # Pasa 2: asociar compartidos a las facturas de su carpeta
            for carpeta, archivos_compartidos in compartidos_por_carpeta.items():
                facturas_carpeta = facturas_por_carpeta.get(carpeta, set())
                if not facturas_carpeta:
                    continue
                for archivo in archivos_compartidos:
                    for factura_raw, factura_norm in facturas_carpeta:
                        entry = self._construir_entry(archivo, factura_raw, factura_norm)
                        nuevo_indice.setdefault(factura_norm, []).append(entry)
                        self._archivos_indexados += 1

            # El cambiazo: hasta esta línea se estuvo respondiendo con el
            # índice anterior.
            self._indice = nuevo_indice
            self._firmas = nuevas_firmas
            self._construido_en = time.time()
            duracion = round(self._construido_en - inicio, 2)
            logger.info(
                f"Soportes indexados: {self._archivos_indexados} archivos / "
                f"{len(self._indice)} facturas únicas en {duracion}s "
                f"({self._carpetas_saltadas} carpetas sin cambios, no se releyeron)"
            )
            self._guardar_en_disco()
            return self.stats()
        finally:
            self._construyendo = False
            self._lock.release()

    def lookup(self, factura: str, auto_rebuild: bool = True) -> list[dict]:
        """Devuelve los soportes detectados para una factura.

        Acepta cualquier formato (`HUS0000495050`, `495050`, etc.) y
        reconstruye el índice si está frío y `auto_rebuild=True`.
        """
        # Si hay una reconstrucción en curso se responde con lo que ya haya
        # en el índice: esperar a que termine deja la pantalla colgada.
        if auto_rebuild and not self._construyendo and not self._esta_caliente():
            self.rebuild()
        norm = normalizar_factura(factura)
        if not norm:
            return []
        entries = self._indice.get(norm, [])
        # Orden por tipo (factura/historia/RIPS primero, otros al final)
        prioridad = {
            "factura_electronica": 0,
            "historia_clinica": 1,
            "rips": 2,
            "comprobante_recibido_cobro": 3,
            "furips": 4,
            "resultados_msps": 5,
            "xml_cufe": 6,
        }
        ordenados = sorted(entries, key=lambda e: (prioridad.get(e.tipo, 99), e.nombre_archivo))
        return [asdict(e) for e in ordenados]

    def stats(self) -> dict:
        return {
            "raiz": str(self.raiz),
            "raiz_existe": self.raiz.exists() if self.raiz else False,
            "facturas_indexadas": len(self._indice),
            "archivos_escaneados": self._archivos_escaneados,
            "archivos_indexados": self._archivos_indexados,
            "construido_en_epoch": self._construido_en,
            "construido_hace_seg": (
                round(time.time() - self._construido_en, 1) if self._construido_en else None
            ),
            "ttl_segundos": self.ttl_segundos,
            "construyendo": self._construyendo,
            "ultimo_error": self._ultimo_error,
        }

    def buscar(self, query: str, limite: int = 30, auto_rebuild: bool = True) -> list[dict]:
        """Búsqueda flexible sobre el índice — soporta facturas, ENV, EPS,
        nombres de archivos parciales. Devuelve hasta `limite` resultados
        AGRUPADOS por factura para que la UI los pueda mostrar como cards.

        Reglas de matching (en orden de prioridad):
          1. Si query parece factura (contiene 4+ dígitos), busca numérico
             exacto primero (igual que lookup).
          2. Sino, busca substring case-insensitive en eps, env, ruta,
             nombre_archivo de TODOS los entries.
          3. Si query tiene varias palabras, todas deben matchear (AND).

        Output: lista de grupos por factura:
            [
              {
                "factura": "HUS245200",
                "factura_norm": "245200",
                "eps": "ALIANZA MEDELLIN",
                "env": "ENV-189840-OK",
                "anio": 2024,
                "mes": "ENERO",
                "ruta_carpeta": "X:\\RADICACION DIGITAL\\...\\HUS245200",
                "archivos_count": 5,
                "archivos": [...],
                "tipos_detectados": ["FEV", "HEV", "RIPS"],
              },
              ...
            ]
        """
        # Igual que en lookup: con una reconstrucción en curso se responde con
        # lo que ya hay, nunca se hace esperar a la pantalla.
        if auto_rebuild and not self._construyendo and not self._esta_caliente():
            self.rebuild()
        if not query or len(query.strip()) < 2:
            return []

        q = query.strip().lower()
        # Limpiar query para detección numérica (ignorar HUS/guiones)
        q_solo_digitos = re.sub(r"[^\d]", "", q)
        es_factura_query = len(q_solo_digitos) >= 4

        # 1. Match exacto por factura si el query es numérico
        if es_factura_query:
            norm = normalizar_factura(q_solo_digitos)
            if norm in self._indice:
                entries = self._indice[norm]
                grupo = self._agrupar_entries_por_factura(entries)
                return list(grupo.values())[:limite]

        # 2. Búsqueda substring sobre todos los entries
        # Tokenizamos el query — todas las palabras deben matchear (AND)
        tokens = [t for t in re.split(r"\s+", q) if len(t) >= 2]
        if not tokens:
            return []

        coincidencias_por_factura: dict[str, list[SoporteEntry]] = {}
        for entries in self._indice.values():
            for e in entries:
                # Texto buscable: ruta + nombre archivo + eps + env + factura
                blob = " ".join(
                    [
                        (e.ruta or "").lower(),
                        (e.nombre_archivo or "").lower(),
                        (e.eps or "").lower(),
                        (e.env or "").lower(),
                        (e.factura or "").lower(),
                    ]
                )
                if all(tok in blob for tok in tokens):
                    coincidencias_por_factura.setdefault(e.factura, []).append(e)

        # Agrupar y ordenar
        grupos_dict = {}
        for factura, entries in coincidencias_por_factura.items():
            grupos_dict[factura] = self._agrupar_entries_por_factura(entries)[factura]

        # Ordenar: año desc, luego eps alfabético, luego factura
        grupos_ordenados = sorted(
            grupos_dict.values(),
            key=lambda g: (-(g.get("anio") or 0), g.get("eps") or "", g.get("factura") or ""),
        )
        return grupos_ordenados[:limite]

    def _agrupar_entries_por_factura(self, entries: list[SoporteEntry]) -> dict:
        """Helper para agrupar entries por factura. Devuelve dict
        {factura: grupo_dict}."""
        if not entries:
            return {}
        prioridad = {
            "factura_electronica": 0,
            "historia_clinica": 1,
            "rips": 2,
            "comprobante_recibido_cobro": 3,
            "furips": 4,
            "resultados_msps": 5,
            "xml_cufe": 6,
        }
        out: dict[str, dict] = {}
        for e in entries:
            fac = e.factura
            if fac not in out:
                # La carpeta del HUS — sube 1 nivel desde el archivo
                ruta_carpeta = e.ruta
                try:
                    import os as _os

                    ruta_carpeta = _os.path.dirname(e.ruta)
                except Exception:
                    pass
                out[fac] = {
                    "factura": fac,
                    "factura_norm": e.factura_norm,
                    "eps": e.eps,
                    "env": e.env,
                    "anio": e.anio,
                    "mes": e.mes,
                    "ruta_carpeta": ruta_carpeta,
                    "archivos": [],
                    "tipos_detectados": set(),
                }
            out[fac]["archivos"].append(
                {
                    "tipo": e.tipo,
                    "tipo_codigo": e.tipo_codigo,
                    "nombre_archivo": e.nombre_archivo,
                    "ruta": e.ruta,
                    "extension": e.extension,
                    "tamano_kb": e.tamano_kb,
                }
            )
            if e.tipo_codigo:
                out[fac]["tipos_detectados"].add(e.tipo_codigo)

        # Ordenar archivos dentro de cada grupo + convertir set a list
        for fac, g in out.items():
            g["archivos"].sort(key=lambda a: (prioridad.get(a["tipo"], 99), a["nombre_archivo"]))
            g["archivos_count"] = len(g["archivos"])
            g["tipos_detectados"] = sorted(g["tipos_detectados"])
        return out


# Singleton lazy
_indexer_singleton: Optional[SoportesIndexer] = None
_singleton_lock = threading.Lock()


def get_indexer() -> SoportesIndexer:
    global _indexer_singleton
    if _indexer_singleton is None:
        with _singleton_lock:
            if _indexer_singleton is None:
                _indexer_singleton = SoportesIndexer()
    return _indexer_singleton
