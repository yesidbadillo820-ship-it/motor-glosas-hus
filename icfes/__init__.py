"""Sistema de preparación para el examen Saber 11 del ICFES.

Este paquete es autónomo: **no depende de nada más del repositorio ni de
librerías externas**. Solo usa la librería estándar de Python 3.11, para que
pueda copiarse a cualquier computador y funcionar sin instalar nada.

Módulos:

- ``dominio``      — cómo es el examen de verdad (áreas, pesos, competencias).
- ``banco``        — carga y valida el banco de preguntas.
- ``puntaje``      — convierte respuestas correctas en puntaje 0-100 y 0-500.
- ``repaso``       — repetición espaciada (qué repasar y cuándo).
- ``plan``         — arma el plan de estudio hasta el día del examen.
- ``simulacro``    — arma simulacros con la estructura y el tiempo reales.
- ``progreso``     — mide el avance y proyecta el puntaje del día del examen.
- ``almacen``      — guarda todo en un archivo SQLite local.
- ``cli``          — el programa de consola.
- ``exportar_web`` — genera la aplicación web que funciona sin internet.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
