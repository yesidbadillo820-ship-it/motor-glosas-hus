"""siifa_client.py — Cliente HTTP para la API oficial de interoperabilidad de SIIFA
(Ministerio de Salud, módulos 2/3: Factura y Seguimiento de facturas).

No es un script para correr solo: lo importan `siifa_reporte_seguimientos.py`
y `responder_glosas_siifa.py`. Ver docs/CONTEXTO_SIIFA.md para el detalle de
los endpoints, roles y plazos.

A diferencia de los bots de COOSALUD/SIMED (Playwright, porque esos portales
no tienen API), SIIFA sí publica una API REST oficial para el módulo de
Seguimiento — por eso este cliente habla HTTP directo, sin navegador.

POR QUÉ ESTE CLIENTE RENUEVA EL TOKEN SOLO (leer si alguna vez "se cuelga"):
    El token de SIIFA (JWT) VENCE a los pocos minutos. Si un cargue largo pide
    el token una sola vez al arrancar, funciona las primeras páginas y después
    TODO falla con 401 — y reintentar no sirve, porque el token ya está muerto.
    Ese es el síntoma clásico: "las primeras 7 páginas bien, de la 8 en adelante
    todas mal". Este cliente detecta el 401, vuelve a autenticarse solo y sigue.

    Igual de importante: sólo reintenta lo que TIENE SENTIDO reintentar (caídas
    de red, 429, 5xx). Un error definitivo (400, 403, 404) se informa de una,
    sin dormir — dormir 15s x 5 intentos sobre un error permanente es lo que
    hace que un proceso parezca "colgado" durante 45 minutos.

CREDENCIALES (variables de entorno, NUNCA en el código):
    setx SIIFA_USER <usuario_sispro>
    setx SIIFA_PASSWORD <password>

INSTALACIÓN (una vez):
    py -m pip install httpx openpyxl
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

try:
    import httpx
except ImportError:  # pragma: no cover
    raise SystemExit("ERROR: falta httpx. py -m pip install httpx")

logger = logging.getLogger("siifa_client")

# URLs CONFIRMADAS (verificadas contra el propio portal SIIFA: la configuración
# de la aplicación web declara apiSeguridad / apiFactura / apiContrato).
BASE_URL_FACTURA_PROD = "https://siifa.sispro.gov.co/siifa-factura"
AUTH_URL_PROD = "https://siifa.sispro.gov.co/siifa-seguridad"
BASE_URL_CONTRATO_PROD = "https://siifa.sispro.gov.co/siifa-contrato"

# El endpoint permite hasta 1500, pero pedir tandas grandes hace que el
# servidor tarde mucho y el proceso parezca colgado. 200 es un punto sano:
# 2.579 registros salen en 13 llamadas rápidas en vez de 2 lentísimas.
REGISTROS_POR_PAGINA_DEFECTO = 200
REGISTROS_POR_PAGINA_MAX = 1500

# Tope de seguridad: si la API ignorara el número de página, el recorrido
# quedaría en bucle infinito acumulando filas y nunca escribiría el informe.
MAX_PAGINAS = 2000

# Códigos que SÍ vale la pena reintentar (problemas pasajeros).
REINTENTABLES = {429, 500, 502, 503, 504}


class SiifaApiError(RuntimeError):
    """Error de negocio devuelto por la API de SIIFA (400/401/403/404/500)."""

    def __init__(self, status_code: int, detail: str, raw: Any = None):
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
        self.raw = raw


def buscar_clave(dato: dict, *claves, default=None):
    """Busca una clave sin importar mayúsculas/minúsculas.

    La API documenta los campos en PascalCase (IdSeguimientoFactura) y los
    ejemplos vienen en camelCase (idSeguimientoFactura). Si el código buscara
    una sola forma, el informe saldría con TODAS las filas vacías — que se ve
    igual que "no trajo nada". Con esto da lo mismo cómo vengan.
    """
    if not isinstance(dato, dict):
        return default
    for clave in claves:
        if clave in dato and dato[clave] not in (None, ""):
            return dato[clave]
    minusculas = {str(k).lower(): v for k, v in dato.items()}
    for clave in claves:
        valor = minusculas.get(str(clave).lower())
        if valor not in (None, ""):
            return valor
    return default


@dataclass
class SiifaClient:
    base_url: str = field(
        default_factory=lambda: os.environ.get("SIIFA_BASE_URL", BASE_URL_FACTURA_PROD)
    )
    auth_url: str = field(default_factory=lambda: os.environ.get("SIIFA_AUTH_URL", AUTH_URL_PROD))
    # Timeout separado: conectar tiene que fallar RÁPIDO (si no hay salida a
    # internet o el firewall traga los paquetes, no tiene sentido esperar 30s),
    # pero leer la respuesta puede tardar si la consulta es grande. 60s por
    # intento acota la espera total del peor caso a ~2 minutos, avisando en
    # cada reintento — en vez de dejar la pantalla muda un cuarto de hora.
    timeout_conexion: float = 10.0
    timeout_lectura: float = 60.0
    max_reintentos: int = 3

    _token: str | None = field(default=None, init=False, repr=False)
    _usuario: str | None = field(default=None, init=False, repr=False)
    _password: str | None = field(default=None, init=False, repr=False)
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.auth_url = self.auth_url.rstrip("/")
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                self.timeout_lectura,
                connect=self.timeout_conexion,
            )
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> "SiifaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ auth

    def guardar_credenciales(self, usuario: str, password: str) -> None:
        """Deja las credenciales listas EN MEMORIA (nunca en disco ni en log),
        sin autenticar todavía. Lo usa el diagnóstico, que autentica él mismo."""
        self._usuario = usuario
        self._password = password

    def login(self, usuario: str, password: str) -> str:
        """Autentica contra /api/Auth/login y guarda el JWT.

        Guarda también las credenciales EN MEMORIA para poder renovar el token
        solo cuando venza a mitad de un cargue largo.
        """
        self.guardar_credenciales(usuario, password)
        return self._autenticar()

    def _autenticar(self) -> str:
        url = f"{self.auth_url}/api/Auth/login"
        logger.info("Autenticando en SIIFA (%s) como usuario '%s'...", self.auth_url, self._usuario)
        try:
            resp = self._client.post(
                url,
                json={"userName": self._usuario, "password": self._password},
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError as exc:
            raise SiifaApiError(
                0,
                f"No se pudo conectar con el servidor de autenticación de SIIFA ({url}). "
                f"Revisá que el equipo tenga salida a internet y que el antivirus/proxy "
                f"del hospital no esté bloqueando el sitio. Detalle técnico: {exc}",
            ) from exc

        if resp.status_code == 401:
            raise SiifaApiError(
                401, "Usuario o contraseña incorrectos (revisá SIIFA_USER y SIIFA_PASSWORD)."
            )
        if resp.status_code >= 400:
            raise SiifaApiError(resp.status_code, _error_detail(resp), _safe_json(resp))

        data = _safe_json(resp)
        if data is None:
            raise SiifaApiError(
                resp.status_code,
                "El servidor de autenticación no devolvió datos válidos (respondió una página "
                "web en vez de la respuesta esperada). Verificá la dirección en SIIFA_AUTH_URL.",
            )
        if not buscar_clave(data, "success", default=False) or not buscar_clave(data, "token"):
            errores = buscar_clave(data, "errors", default="") or "sin detalle"
            raise SiifaApiError(resp.status_code, f"SIIFA rechazó el ingreso: {errores}", data)

        self._token = buscar_clave(data, "token")
        logger.info("Ingreso a SIIFA correcto.")
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            raise RuntimeError("Llamar login() antes de usar el cliente.")
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # -------------------------------------------------------------- request

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        ultimo_error: Exception | None = None
        renovado = False

        for intento in range(1, self.max_reintentos + 1):
            try:
                resp = self._client.request(method, url, headers=self._headers(), **kwargs)
            except httpx.RequestError as exc:
                ultimo_error = exc
                if intento >= self.max_reintentos:
                    break
                espera = 2 * intento
                logger.warning(
                    "Falla de red en %s (intento %d de %d). Reintento en %ds. Detalle: %s",
                    path,
                    intento,
                    self.max_reintentos,
                    espera,
                    exc,
                )
                time.sleep(espera)
                continue

            # Token vencido a mitad del trabajo: renovarlo y seguir. Es LA causa
            # típica de "las primeras páginas bien y de ahí en adelante todas mal".
            if resp.status_code == 401 and not renovado and self._usuario:
                renovado = True
                logger.info("El token de SIIFA venció — renovando y continuando...")
                self._autenticar()
                continue

            if resp.status_code in REINTENTABLES and intento < self.max_reintentos:
                espera = 2 * intento
                logger.warning(
                    "SIIFA respondió %d en %s (intento %d de %d). Reintento en %ds.",
                    resp.status_code,
                    path,
                    intento,
                    self.max_reintentos,
                    espera,
                )
                time.sleep(espera)
                continue

            # Error definitivo: informar de una, SIN dormir ni reintentar.
            if resp.status_code >= 400:
                raise SiifaApiError(resp.status_code, _error_detail(resp), _safe_json(resp))

            return _safe_json(resp) or {}

        raise SiifaApiError(
            0,
            f"No hubo respuesta de SIIFA tras {self.max_reintentos} intentos. "
            f"Último detalle: {ultimo_error}",
        )

    # ----------------------------------------------------------- consultas

    def listar_seguimientos(
        self,
        tipo_seguimiento: str | None = None,
        tiene_respuesta: bool | None = None,
        numero_factura: str | None = None,
        fecha_creacion_inicio: str | None = None,
        fecha_creacion_final: str | None = None,
        registros_por_pagina: int = REGISTROS_POR_PAGINA_DEFECTO,
    ) -> Iterator[dict]:
        """Recorre TODAS las páginas de GET /api/SeguimientoFactura/List y va
        entregando cada seguimiento (glosa o devolución) uno por uno."""
        registros_por_pagina = max(1, min(registros_por_pagina, REGISTROS_POR_PAGINA_MAX))
        pagina = 1
        entregados = 0
        huellas_vistas: set = set()

        while pagina <= MAX_PAGINAS:
            params = {"NumeroPagina": pagina, "RegistrosPorPagina": registros_por_pagina}
            if tipo_seguimiento:
                params["TipoSeguimiento"] = tipo_seguimiento
            if tiene_respuesta is not None:
                params["TieneRespuesta"] = str(tiene_respuesta).lower()
            if numero_factura:
                params["NumeroFactura"] = numero_factura
            if fecha_creacion_inicio:
                params["FechaCreacionInicio"] = fecha_creacion_inicio
            if fecha_creacion_final:
                params["FechaCreacionFinal"] = fecha_creacion_final

            # Avisar ANTES de pedir: si la consulta tarda, el usuario ve en qué anda.
            logger.info(
                "Consultando página %d (de a %d registros)...", pagina, registros_por_pagina
            )
            data = self._request("GET", "/api/SeguimientoFactura/List", params=params)

            resultado = buscar_clave(data, "resultado", "Resultado", default=[]) or []
            total_registros = buscar_clave(data, "totalRegistros", "TotalRegistros", default=None)
            total_paginas = buscar_clave(data, "totalPaginas", "TotalPaginas", default=1) or 1

            if not resultado:
                logger.info("La página %d vino vacía — fin del recorrido.", pagina)
                break

            # Protección contra API que ignore el número de página: si esta página
            # trae exactamente lo mismo que una anterior, cortamos (si no, el
            # proceso quedaría dando vueltas para siempre y nunca escribiría nada).
            huella = _huella_pagina(resultado)
            if huella in huellas_vistas:
                logger.warning(
                    "La página %d repite datos ya recibidos — corto acá para no quedar en bucle.",
                    pagina,
                )
                break
            huellas_vistas.add(huella)

            for fila in resultado:
                yield fila
            entregados += len(resultado)

            logger.info(
                "Página %d de %s lista — %d registros acumulados%s.",
                pagina,
                total_paginas,
                entregados,
                f" de {total_registros}" if total_registros else "",
            )

            if pagina >= total_paginas:
                break
            pagina += 1
        else:
            logger.warning("Se alcanzó el tope de %d páginas — corto por seguridad.", MAX_PAGINAS)

    def catalogo_tipo_codigo(self, grupo: str) -> list[dict]:
        """GET /api/SeguimientoTipoCodigo/ByGrupo — catálogo oficial de códigos
        (Grupo='RESPUESTA' para códigos de respuesta, 'GLOSA' para causales)."""
        data = self._request("GET", "/api/SeguimientoTipoCodigo/ByGrupo", params={"Grupo": grupo})
        if isinstance(data, list):
            return data
        resultado = buscar_clave(data, "resultado", "Resultado")
        if isinstance(resultado, list):
            return resultado
        return [data] if data else []

    def resumen_glosas_factura(self, id_factura: int) -> dict:
        return self._request(
            "GET", f"/api/SeguimientoFacturaGlosa/Resumen/ByIdFactura/{id_factura}"
        )

    # ------------------------------------------------------------ escritura

    def responder_glosa(
        self,
        id_seguimiento_factura_glosa: int,
        id_seguimiento_tipo_codigo_respuesta: str,
        observacion_respuesta: str | None = None,
        fecha_respuesta: str | None = None,
    ) -> dict:
        """PUT /api/SeguimientoFacturaGlosa/Respuesta — registra la respuesta del
        HUS a una glosa ya formulada por la EPS."""
        body = {
            "idSeguimientoFacturaGlosa": id_seguimiento_factura_glosa,
            "idSeguimientoTipoCodigoRespuesta": id_seguimiento_tipo_codigo_respuesta,
            "fechaRespuesta": fecha_respuesta or _ahora_iso(),
        }
        if observacion_respuesta:
            body["observacionRespuesta"] = observacion_respuesta
        return self._request("PUT", "/api/SeguimientoFacturaGlosa/Respuesta", json=body)

    def responder_reiteracion_glosa(
        self,
        id_seguimiento_factura_glosa: int,
        id_seguimiento_tipo_codigo_reiteracion_respuesta: str,
        observacion_reiteracion_respuesta: str | None = None,
        fecha_reiteracion_respuesta: str | None = None,
    ) -> dict:
        """PUT /api/SeguimientoFacturaGlosa/ReiteracionRespuesta — subsanación:
        respuesta del HUS a una glosa que la EPS reiteró (no levantó)."""
        body = {
            "idSeguimientoFacturaGlosa": id_seguimiento_factura_glosa,
            "idSeguimientoTipoCodigoGlosaReiteracionRespuesta": (
                id_seguimiento_tipo_codigo_reiteracion_respuesta
            ),
            "fechaFormulacionGlosaReiteracionRespuesta": (
                fecha_reiteracion_respuesta or _ahora_iso()
            ),
        }
        if observacion_reiteracion_respuesta:
            body["observacionReiteracionRespuesta"] = observacion_reiteracion_respuesta
        return self._request("PUT", "/api/SeguimientoFacturaGlosa/ReiteracionRespuesta", json=body)

    # ----------------------------------------------------------- diagnóstico

    def diagnostico(self) -> list[tuple[str, bool, str]]:
        """Chequeo paso a paso para cuando algo no funciona.

        Devuelve una lista de (paso, ok, detalle) para imprimir al usuario.
        """
        pasos: list[tuple[str, bool, str]] = []

        try:
            resp = self._client.get(f"{self.auth_url}/", timeout=httpx.Timeout(15.0, connect=8.0))
            pasos.append(
                ("Conexión con el sitio de SIIFA", True, f"responde (HTTP {resp.status_code})")
            )
        except httpx.RequestError as exc:
            pasos.append(
                (
                    "Conexión con el sitio de SIIFA",
                    False,
                    f"no responde — revisar internet/proxy del hospital ({exc})",
                )
            )
            return pasos

        try:
            self._autenticar()
            pasos.append(("Usuario y contraseña", True, "ingreso correcto"))
        except SiifaApiError as exc:
            pasos.append(("Usuario y contraseña", False, str(exc)))
            return pasos

        try:
            data = self._request(
                "GET",
                "/api/SeguimientoFactura/List",
                params={"NumeroPagina": 1, "RegistrosPorPagina": 1},
            )
            total = buscar_clave(data, "totalRegistros", "TotalRegistros", default="?")
            pasos.append(("Consulta de seguimientos", True, f"el hospital tiene {total} registros"))
        except SiifaApiError as exc:
            pasos.append(("Consulta de seguimientos", False, str(exc)))

        return pasos


def _huella_pagina(resultado: list) -> str:
    """Identifica una página por sus primeros/últimos ids, para detectar repetidos."""

    def ident(fila):
        return str(
            buscar_clave(
                fila,
                "idSeguimientoFactura",
                "IdSeguimientoFactura",
                "idSeguimientoFacturaGlosa",
                default="",
            )
        )

    return f"{len(resultado)}|{ident(resultado[0])}|{ident(resultado[-1])}"


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_json(resp: "httpx.Response") -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _error_detail(resp: "httpx.Response") -> str:
    data = _safe_json(resp)
    if isinstance(data, dict):
        errores = data.get("errors") or data.get("Errors")
        if errores:
            return f"{data.get('title') or 'Datos inválidos'} — {errores}"
        return data.get("detail") or data.get("title") or str(data)
    texto = (resp.text or "").strip()
    if texto.lstrip().lower().startswith(("<!doctype", "<html")):
        return (
            "el servidor devolvió una página web en vez de datos "
            "(probablemente la dirección configurada no es la de la API)"
        )
    return texto[:300] or "sin detalle"


def credenciales_desde_env() -> tuple[str, str]:
    usuario = os.environ.get("SIIFA_USER")
    password = os.environ.get("SIIFA_PASSWORD")
    if not usuario or not password:
        raise SystemExit(
            "ERROR: faltan las credenciales. Definir SIIFA_USER y SIIFA_PASSWORD "
            "como variables de entorno (setx SIIFA_USER ...; setx SIIFA_PASSWORD ...) "
            "y reabrir la terminal. Nunca se escriben en el código."
        )
    return usuario, password
