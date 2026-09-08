"""Dónde está el RIPS de una factura en el servidor de facturación electrónica.

POR QUÉ EXISTE (08-09-2026). El RIPS de cada factura vive en un servidor
distinto al de los soportes de radicación:

    \\\\172.16.32.83\\factura_electronica_net22\\
      <AAAAMM>\\FACTURAS_SALUD\\<HUSxxxx>\\        ← factura de venta
        [RIPS\\]Rips_<HUSxxxx>.json
      <AAAAMM>\\FACTURAS_NOTA\\<NExxxx>\\          ← notas crédito

El indexador de soportes que ya tiene el motor (`soportes_autodiscovery`)
recorre el OTRO share, el de radicación, y lo hace con un `os.walk` completo
de la raíz. Contra este servidor eso no sirve: son años de facturas en una
unidad de red, y recorrerlo entero para buscar una sola factura tardaría
horas.

Por eso acá se va **DIRECTO a la carpeta**: con el número de factura y el
período se arma la ruta y se mira si está. Es el mismo camino que ya usa el
bot `tools/auditar_devoluciones_eps.py` (`indexar_directo`) contra este mismo
servidor, y que el equipo dio por bueno.

TOLERANCIAS QUE VIENEN DE LA REALIDAD, no de la teoría:

  · la factura puede estar archivada en el mes de la factura, en el anterior
    o en el siguiente (se radica a caballo entre dos meses);
  · el nombre de la carpeta a veces trae los ceros y a veces no
    (`HUS0000556635` / `HUS556635`);
  · el RIPS a veces cuelga de una subcarpeta `RIPS\\` y a veces está suelto
    en la carpeta de la factura;
  · el archivo puede llamarse `Rips_...`, `RIPS_...` o `rips_...`.

Si el servidor no responde, no está montado o la factura no aparece, se
devuelve `None` con el motivo. **No se recorre el árbol entero como
consuelo**: una pantalla que se cuelga diez minutos es peor que una que
dice «no lo encontré».
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

# Nombre del archivo del RIPS dentro de la carpeta de la factura.
_RE_RIPS = re.compile(r"^rips[_\- ]?.*\.json$", re.IGNORECASE)
# Subcarpetas donde suele colgar, además de la raíz de la factura.
SUBCARPETAS = ("", "RIPS", "Rips", "rips")
# Carpetas de primer nivel por tipo de documento.
CARPETAS_TIPO = ("FACTURAS_SALUD", "FACTURAS_NOTA")


@dataclass(frozen=True)
class RipsUbicado:
    ruta: Optional[str] = None
    carpeta_factura: Optional[str] = None
    problema: str = ""

    @property
    def encontrado(self) -> bool:
        return bool(self.ruta)


def _raiz_configurada() -> Optional[str]:
    """Lee la carpeta del servidor de `config/facturacion_electronica_root.txt`.

    Un archivo local (no versionado) de una sola línea, igual que el de los
    soportes. Así el auditor cambia el servidor sin tocar código y sin que el
    autodeploy se lo borre.
    """
    try:
        ruta = (
            Path(__file__).resolve().parent.parent.parent
            / "config"
            / "facturacion_electronica_root.txt"
        )
        if not ruta.is_file():
            return None
        for linea in ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            valor = linea.strip().strip('"').strip("'")
            if valor and not valor.startswith("#"):
                return valor
    except OSError:
        return None
    return None


def raiz_facturacion_electronica() -> str:
    """La carpeta del servidor de facturación electrónica. Una sola respuesta.

    Mismo orden y mismo motivo que `raiz_de_soportes()`: el archivo de
    configuración va primero porque el vigilante que revive el motor conserva
    las variables de cuando ÉL arrancó.

      1. `config/facturacion_electronica_root.txt`
      2. `FACTURACION_ELECTRONICA_ROOT`
      3. `FE_ROOT`
      4. vacío — sin configurar, el módulo dice que no está configurado en vez
         de inventarse una ruta que no existe.
    """
    return (
        _raiz_configurada()
        or os.getenv("FACTURACION_ELECTRONICA_ROOT")
        or os.getenv("FE_ROOT")
        or ""
    )


def _digitos(factura: str) -> str:
    """`HUS0000556635` → `556635` (sin prefijo ni ceros de relleno)."""
    solo = re.sub(r"\D", "", str(factura or ""))
    return solo.lstrip("0") or solo


def periodo_de(fecha: Any) -> Optional[str]:
    """La carpeta de período `AAAAMM` que corresponde a una fecha."""
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    if not isinstance(fecha, date):
        try:
            fecha = date.fromisoformat(str(fecha).replace("T", " ").split(" ")[0])
        except (ValueError, TypeError):
            return None
    return f"{fecha.year:04d}{fecha.month:02d}"


def periodo_vecino(periodo: str, salto: int) -> Optional[str]:
    """El período `salto` meses adelante o atrás. `202601` -1 → `202512`."""
    try:
        anio, mes = int(str(periodo)[:4]), int(str(periodo)[4:6])
    except (ValueError, TypeError):
        return None
    if not 1 <= mes <= 12:
        return None
    total = (anio * 12 + mes - 1) + salto
    return f"{total // 12:04d}{total % 12 + 1:02d}"


def _nombres_de_carpeta(factura: str) -> list[str]:
    """Las formas en que puede estar nombrada la carpeta de la factura."""
    crudo = str(factura or "").strip()
    num = _digitos(crudo)
    nombres = [crudo, f"HUS{num}", f"HUS{num.zfill(6)}", f"HUS{num.zfill(10)}"]
    vistos, salida = set(), []
    for n in nombres:
        if n and n not in vistos:
            vistos.add(n)
            salida.append(n)
    return salida


def _rips_en(carpeta: Path) -> Optional[Path]:
    """El primer archivo que parezca un RIPS dentro de la carpeta."""
    for sub in SUBCARPETAS:
        destino = carpeta / sub if sub else carpeta
        try:
            if not destino.is_dir():
                continue
            for hijo in sorted(destino.iterdir()):
                if hijo.is_file() and _RE_RIPS.match(hijo.name):
                    return hijo
        except OSError:
            continue
    return None


def localizar(
    factura: str,
    fecha_factura: Any = None,
    raiz: Optional[str] = None,
    meses_alrededor: int = 1,
) -> RipsUbicado:
    """Busca el RIPS de una factura yendo directo a su carpeta.

    `fecha_factura` decide por cuál período se empieza. Sin ella no se puede
    ir directo, y se dice — antes que recorrer el servidor entero.
    """
    base_txt = raiz if raiz is not None else raiz_facturacion_electronica()
    if not base_txt:
        return RipsUbicado(
            problema=(
                "No está configurado el servidor de facturación electrónica. "
                "Escriba la ruta en config/facturacion_electronica_root.txt."
            )
        )
    base = Path(base_txt)
    try:
        if not base.is_dir():
            return RipsUbicado(problema=f"No se puede llegar al servidor: {base_txt}")
    except OSError as e:
        return RipsUbicado(problema=f"No se puede llegar al servidor ({e}): {base_txt}")

    periodo = periodo_de(fecha_factura)
    if not periodo:
        return RipsUbicado(
            problema=(
                "La factura no tiene fecha, así que no se sabe en qué período "
                "del servidor buscarla."
            )
        )

    periodos = [periodo]
    for salto in range(1, max(0, meses_alrededor) + 1):
        for vecino in (periodo_vecino(periodo, salto), periodo_vecino(periodo, -salto)):
            if vecino and vecino not in periodos:
                periodos.append(vecino)

    for per in periodos:
        for tipo in CARPETAS_TIPO:
            for nombre in _nombres_de_carpeta(factura):
                carpeta = base / per / tipo / nombre
                hallado = _rips_en(carpeta)
                if hallado is not None:
                    return RipsUbicado(ruta=str(hallado), carpeta_factura=str(carpeta))

    return RipsUbicado(
        problema=(
            f"No se encontró el RIPS de {factura} en el servidor "
            f"(se miraron los períodos {', '.join(periodos)})."
        )
    )
