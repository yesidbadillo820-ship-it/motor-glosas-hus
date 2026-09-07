"""Curso de noruego para hispanohablantes, de cero a nivel avanzado.

Paquete autónomo: no importa nada de `app/` ni de `tools/` y solo usa la
librería estándar de Python 3.11. Genera una aplicación web instalable en el
celular (PWA) que funciona sin internet.

Módulos:

- ``dominio``      — niveles MCER, temas, tipos de ejercicio, géneros, grupos verbales.
- ``lexico``       — carga y valida los datos lingüísticos (JSON en ``lexico/``).
- ``curso``        — la ruta de aprendizaje: módulos y lecciones.
- ``ejercicios``   — genera ejercicios a partir de los datos lingüísticos.
- ``repaso``       — repetición espaciada con detección de palabras difíciles.
- ``progreso``     — XP, niveles, rachas, dominio por tema.
- ``exportar_web`` — arma la PWA (HTML + manifest + service worker).
- ``cli``          — programa de consola.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
