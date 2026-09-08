"""La revisión de fechas y plazo de una factura del ADRES, de punta a punta.

POR QUÉ EXISTE (08-09-2026, pedido de Yesid). Junta en un solo paso lo que
antes eran cuatro piezas sueltas, para responder una pregunta que el gestor
hace factura por factura: **¿esta cuenta todavía se puede cobrar?**

    1. buscar el RIPS de la factura en el servidor de facturación
       electrónica (`rips_localizador`),
    2. sacar de ahí el ingreso y el egreso (`rips_fechas_atencion`),
    3. cotejarlos contra lo que dice la factura y el oficio
       (`cotejo_fechas_atencion`),
    4. contar el plazo desde el egreso (`prescripcion_adres`).

SOLO PARA EL ADRES. La regla del plazo desde el egreso es del ADRES; a las
facturas de EPS no se les aplica. Quién es del ADRES lo decide `es_adres()`,
el mismo criterio que ya usa el resto del flujo — no otro.

POR QUÉ SE CALCULA CUANDO EL GESTOR LO PIDE Y NO AL CARGAR EL ENVÍO. Cargar
un envío mete decenas de facturas de un golpe, y cada revisión toca una
unidad de red. Meterlo ahí volvería lentísima la carga —el paso que el
gestor hace todos los días— por un dato que solo mira cuando audita. Se
calcula por factura, cuando se abre, que es cuando sirve.

NADA DE ESTO DECIDE POR EL GESTOR. Devuelve el dictamen para que lo lea:
no devuelve la factura, no la marca en la base, no bloquea nada. Si el RIPS
no aparece, lo dice y no supone que la cuenta esté bien ni mal.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.cotejo_fechas_atencion import cotejar, hay_reparos_graves
from app.services.fechas_declaradas_factura import buscar as buscar_declaradas
from app.services.prescripcion_adres import MESES_PLAZO_ADRES, evaluar
from app.services.rips_fechas_atencion import fechas_de_archivo
from app.services.rips_localizador import localizar

# Motivo por el que no se revisó, cuando no aplica.
NO_ES_ADRES = "Esta factura no es del ADRES: el plazo desde el egreso no le aplica."


def revisar(
    db: Session,
    factura: str,
    *,
    hoy: Optional[date] = None,
    meses_plazo: int = MESES_PLAZO_ADRES,
    ingreso_declarado: Any = None,
    egreso_declarado: Any = None,
) -> dict[str, Any]:
    """Revisa una factura y devuelve el dictamen completo, listo para pantalla.

    Siempre devuelve un dict con la misma forma, aunque no haya podido
    revisar: `aplica` dice si la regla corría, `motivo` por qué no.
    """
    from app.services.preauditoria_service import datos_fuente, es_adres

    fuente = datos_fuente(db, factura)
    if not es_adres(fuente.get("nit"), fuente.get("entidad")):
        return {
            "factura": factura,
            "aplica": False,
            "motivo": NO_ES_ADRES,
            "entidad": fuente.get("entidad"),
            "fechas": None,
            "prescripcion": None,
            "hallazgos": [],
            "hay_reparos_graves": False,
        }

    ubicado = localizar(factura, fuente.get("f_factura"))
    fechas = fechas_de_archivo(ubicado.ruta) if ubicado.encontrado else None

    # Las fechas que el hospital DECLARÓ: salen del XML de la factura
    # electrónica (o del resultado del validador), que están en la misma
    # carpeta del servidor. Solo se buscan si no vinieron dadas.
    declaradas = None
    if ingreso_declarado is None and egreso_declarado is None:
        declaradas = buscar_declaradas(factura, fuente.get("f_factura"))
        if declaradas.completas:
            ingreso_declarado = declaradas.fecha_ingreso
            egreso_declarado = declaradas.fecha_egreso

    hallazgos = cotejar(
        fechas,
        ingreso_declarado=ingreso_declarado,
        egreso_declarado=egreso_declarado,
        fecha_factura=fuente.get("f_factura"),
        fecha_recibido=fuente.get("f_recibido"),
    )
    # Cuando ni siquiera se pudo llegar al archivo, el motivo del localizador
    # es más útil que el genérico del cotejo: se cambia el mensaje, no el código.
    if not ubicado.encontrado and hallazgos and hallazgos[0].codigo == "RIPS_NO_ENCONTRADO":
        hallazgos = [
            type(hallazgos[0])(
                hallazgos[0].codigo,
                hallazgos[0].gravedad,
                ubicado.problema or hallazgos[0].mensaje,
            )
        ] + hallazgos[1:]

    prescripcion = None
    if fechas is not None and fechas.fecha_egreso is not None:
        prescripcion = evaluar(fechas.fecha_egreso, hoy=hoy, meses_plazo=meses_plazo)

    return {
        "factura": factura,
        "aplica": True,
        "motivo": "",
        "entidad": fuente.get("entidad"),
        "archivo_rips": ubicado.ruta,
        "fechas": fechas.a_dict() if fechas is not None else None,
        "declaradas": declaradas.a_dict() if declaradas is not None else None,
        "prescripcion": prescripcion.a_dict() if prescripcion is not None else None,
        "hallazgos": [h.a_dict() for h in hallazgos],
        "hay_reparos_graves": hay_reparos_graves(hallazgos),
    }
