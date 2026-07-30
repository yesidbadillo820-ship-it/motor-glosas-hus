"""siifa_client.py — Cliente HTTP para la API oficial de interoperabilidad de SIIFA
(Ministerio de Salud, módulos 2/3: Factura y Seguimiento de facturas).

No es un script para correr solo: lo importan `siifa_reporte_seguimientos.py`
y `responder_glosas_siifa.py`. Ver docs/CONTEXTO_SIIFA.md para el detalle de
los endpoints, roles y plazos.

A diferencia de los bots de COOSALUD/SIMED (Playwright, porque esos portales
no tienen API), SIIFA sí publica una API REST oficial para el módulo de
Seguimiento — por eso este cliente habla HTTP directo, sin navegador.

CREDENCIALES (variables de entorno, NUNCA en el código):
    setx SIIFA_USER <usuario_sispro>
    setx SIIFA_PASSWORD <password>
    setx SIIFA_AUTH_URL <url del servicio de Auth>   (ver docs/CONTEXTO_SIIFA.md — no confirmada)

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

BASE_URL_FACTURA_PROD = "https://siifa.sispro.gov.co/siifa-factura"

# No confirmada en los manuales disponibles — ver docs/CONTEXTO_SIIFA.md §3.1.
# Se usa solo si el auditor no define SIIFA_AUTH_URL.
AUTH_URL_HIPOTESIS = "https://siifa.sispro.gov.co/siifa-seguridad"

REGISTROS_POR_PAGINA_MAX = 1500


class SiifaApiError(RuntimeError):
    """Error de negocio devuelto por la API de SIIFA (400/401/403/404/500)."""

    def __init__(self, status_code: int, detail: str, raw: Any = None):
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
        self.raw = raw


@dataclass
class SiifaClient:
    base_url: str = field(default_factory=lambda: os.environ.get("SIIFA_BASE_URL", BASE_URL_FACTURA_PROD))
    auth_url: str = field(default_factory=lambda: os.environ.get("SIIFA_AUTH_URL", AUTH_URL_HIPOTESIS))
    timeout: float = 30.0
    max_reintentos: int = 3

    _token: str | None = field(default=None, init=False, repr=False)
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.auth_url = self.auth_url.rstrip("/")
        self._client = httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> "SiifaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ auth

    def login(self, usuario: str, password: str) -> str:
        """Autentica contra /api/Auth/login y guarda el JWT para las siguientes llamadas."""
        url = f"{self.auth_url}/api/Auth/login"
        try:
            resp = self._client.post(url, json={"userName": usuario, "password": password})
        except httpx.RequestError as exc:
            raise SiifaApiError(
                0,
                f"No se pudo conectar a {url}. Si SIIFA_AUTH_URL no está confirmada, "
                f"esto es lo primero a revisar (docs/CONTEXTO_SIIFA.md §3.1). Detalle: {exc}",
            ) from exc

        if resp.status_code != 200:
            raise SiifaApiError(resp.status_code, "Login falló", _safe_json(resp))

        data = resp.json()
        if not data.get("success") or not data.get("token"):
            raise SiifaApiError(resp.status_code, f"Login rechazado: {data.get('errors')}", data)

        self._token = data["token"]
        logger.info("Login SIIFA OK (usuario=%s)", usuario)
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
        last_exc: Exception | None = None
        for intento in range(1, self.max_reintentos + 1):
            try:
                resp = self._client.request(method, url, headers=self._headers(), **kwargs)
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning("Error de red (%s), intento %d/%d: %s", path, intento, self.max_reintentos, exc)
                time.sleep(2 * intento)
                continue

            if resp.status_code in (429, 500, 502, 503, 504) and intento < self.max_reintentos:
                logger.warning("HTTP %d en %s, reintentando (%d/%d)", resp.status_code, path, intento, self.max_reintentos)
                time.sleep(2 * intento)
                continue

            if resp.status_code >= 400:
                raise SiifaApiError(resp.status_code, _error_detail(resp), _safe_json(resp))

            return _safe_json(resp) or {}

        raise SiifaApiError(0, f"Fallo de red tras {self.max_reintentos} intentos: {last_exc}")

    # ----------------------------------------------------------- consultas

    def listar_seguimientos(
        self,
        tipo_seguimiento: str | None = None,
        tiene_respuesta: bool | None = None,
        numero_factura: str | None = None,
        fecha_creacion_inicio: str | None = None,
        fecha_creacion_final: str | None = None,
        registros_por_pagina: int = REGISTROS_POR_PAGINA_MAX,
    ) -> Iterator[dict]:
        """Recorre TODAS las páginas de GET /api/SeguimientoFactura/List y va
        entregando cada seguimiento (glosa o devolución) uno por uno."""
        pagina = 1
        while True:
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

            data = self._request("GET", "/api/SeguimientoFactura/List", params=params)
            resultado = data.get("resultado") or []
            for fila in resultado:
                yield fila

            total_paginas = data.get("totalPaginas") or 1
            logger.info("Página %d/%d de seguimientos (%d registros)", pagina, total_paginas, len(resultado))
            if pagina >= total_paginas or not resultado:
                break
            pagina += 1

    def catalogo_tipo_codigo(self, grupo: str) -> list[dict]:
        """GET /api/SeguimientoTipoCodigo/ByGrupo — catálogo oficial de códigos
        (Grupo='RESPUESTA' para códigos de respuesta, 'GLOSA' para causales)."""
        data = self._request("GET", "/api/SeguimientoTipoCodigo/ByGrupo", params={"Grupo": grupo})
        if isinstance(data, list):
            return data
        return data.get("resultado") or [data]

    def resumen_glosas_factura(self, id_factura: int) -> dict:
        return self._request("GET", f"/api/SeguimientoFacturaGlosa/Resumen/ByIdFactura/{id_factura}")

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
            "idSeguimientoTipoCodigoGlosaReiteracionRespuesta": id_seguimiento_tipo_codigo_reiteracion_respuesta,
            "fechaFormulacionGlosaReiteracionRespuesta": fecha_reiteracion_respuesta or _ahora_iso(),
        }
        if observacion_reiteracion_respuesta:
            body["observacionReiteracionRespuesta"] = observacion_reiteracion_respuesta
        return self._request("PUT", "/api/SeguimientoFacturaGlosa/ReiteracionRespuesta", json=body)


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
        return data.get("detail") or data.get("title") or str(data)
    return resp.text[:500]


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
