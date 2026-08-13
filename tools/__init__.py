"""`tools` es un paquete de verdad, no una carpeta suelta. No borrar.

04-08-2026: **Mako 1.4.0** (dependencia indirecta, llega con alembic) se
publicó ese día con un error de empaquetado: su rueda incluye una carpeta
`tools/` propia —`toxnox.py`, `warn_tox.py`, sus ayudantes internos— que
queda instalada al mismo nivel que las librerías. Sin este archivo, la
`tools/` del repo era un *namespace package*, y en Python un paquete de
verdad le gana a uno de esos aunque esté después en la ruta de búsqueda:
todo el sistema pasó a ver la `tools` de Mako y el CI murió con

    ModuleNotFoundError: No module named 'tools._dinero'

Con este archivo, `tools` es un paquete normal y gana el que esté primero
en la ruta — que siempre es el del repo. Vale para el CI, para la imagen
Docker (hay que mantener `!tools/__init__.py` en `.dockerignore`) y para
cualquier otro paquete que mañana se llame igual.

No poner nada aquí: los bots de `tools/` se importan sueltos y este
archivo se carga antes que todos.
"""
