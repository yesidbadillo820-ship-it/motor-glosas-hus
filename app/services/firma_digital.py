"""DEPRECATED: firma digital removida en cleanup mayo 2026.

Stub mantenido para que imports legacy en glosas.py no rompan el deploy.
La funcion firmar_dictamen() devuelve un payload neutro.
"""

def firmar_dictamen(*args, **kwargs) -> dict:
    return {
        "firma": None,
        "alg": "removed",
        "verificable": False,
        "removido": True,
        "timestamp": None,
        "firmante": None,
    }
