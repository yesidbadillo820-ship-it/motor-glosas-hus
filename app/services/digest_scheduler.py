"""DEPRECATED: digest scheduler removido en cleanup mayo 2026.

Stub para que imports legacy en sistema.py no rompan.
"""

_task = None


def obtener_estado() -> dict:
    return {"activo": False, "removido": True, "ultima": None}


def iniciar_scheduler():
    pass


def detener_scheduler():
    pass
