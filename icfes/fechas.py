"""Fechas en español, para que el plan no salga con los días en inglés.

Python formatea los días y meses según el idioma del sistema operativo, que en
un servidor casi siempre es inglés. Como el plan lo lee un estudiante
colombiano, aquí se traducen a mano: es una tabla de catorce palabras y evita
depender de cómo esté configurado el computador donde se corra.
"""

from __future__ import annotations

from datetime import date

DIAS: tuple[str, ...] = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

MESES: tuple[str, ...] = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def dia_semana(dia: date, corto: bool = False) -> str:
    """El nombre del día de la semana en español."""
    nombre = DIAS[dia.weekday()]
    return nombre[:3] if corto else nombre


def mes(dia: date) -> str:
    """El nombre del mes en español."""
    return MESES[dia.month - 1]


def largo(dia: date) -> str:
    """Fecha completa: «jueves 20 de agosto de 2026»."""
    return f"{dia_semana(dia)} {dia.day} de {mes(dia)} de {dia.year}"


def corto(dia: date) -> str:
    """Fecha corta con día de la semana: «jue 20/08»."""
    return f"{dia_semana(dia, corto=True)} {dia.day:02d}/{dia.month:02d}"


def cuenta_regresiva(desde: date, hasta: date) -> str:
    """«Faltan 353 días (50 semanas y 3 días)» — el recordatorio que motiva."""
    dias = (hasta - desde).days
    if dias < 0:
        return "El examen ya pasó."
    if dias == 0:
        return "El examen es HOY."
    if dias == 1:
        return "Falta 1 día."
    semanas, sueltos = divmod(dias, 7)
    if semanas == 0:
        return f"Faltan {dias} días."
    parte = f"{semanas} semana{'s' if semanas != 1 else ''}"
    if sueltos:
        parte += f" y {sueltos} día{'s' if sueltos != 1 else ''}"
    return f"Faltan {dias} días ({parte})."
