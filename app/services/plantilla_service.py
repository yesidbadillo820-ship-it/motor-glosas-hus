import re
from typing import Optional
from datetime import datetime

VARIABLES_DISPONIBLES = {
    "{{EPS}}": "Nombre de la EPS",
    "{{CODIGO_GLOSA}}": "Código de la glosa",
    "{{VALOR_OBJETADO}}": "Valor objetado",
    "{{VALOR_ACEPTADO}}": "Valor aceptado",
    "{{FECHA_RADICACION}}": "Fecha de radicación",
    "{{FECHA_RECEPCION}}": "Fecha de recepción",
    "{{DIAS_HABILES}}": "Días hábiles",
    "{{NUMERO_FACTURA}}": "Número de factura",
    "{{NUMERO_RADICADO}}": "Número de radicado",
    "{{SERVICIO}}": "Servicio médico",
    "{{CUPS}}": "Código CUPS",
    "{{NUMERO_CONTRATO}}": "Número de contrato",
    "{{TARIFA_PACTADA}}": "Tarifa pactada",
    "{{FECHA_HOY}}": "Fecha actual",
    "{{ANIO_ACTUAL}}": "Año actual",
}


class PlantillaService:
    def resolver_variables(self, plantilla: str, data: dict) -> str:
        if not plantilla:
            return ""
        ahora = datetime.now()
        # Defaults contextuales: usar "N/A" suelto en un dictamen oficial es
        # antitécnico y la EPS lo descarta de pinta. Si el dato no viene, en
        # vez de "N/A" ponemos la frase neutra que correspondería al campo
        # ("el código de la glosa aplicada", "el procedimiento facturado",
        # etc.) — el dictamen sigue siendo legible incluso con datos faltantes.
        # Bug detectado 23-jun-2026 en 4 de 6 casos pegados por Yesid.
        reemplazos = {
            "{{EPS}}": str(data.get("eps", "")).upper() or "la EPS",
            "{{CODIGO_GLOSA}}": str(data.get("codigo_glosa") or "el código de la glosa aplicada"),
            "{{VALOR_OBJETADO}}": f"$ {float(data.get('valor_objetado', 0)):,.0f}",
            "{{VALOR_ACEPTADO}}": f"$ {float(data.get('valor_aceptado', 0)):,.0f}",
            "{{FECHA_RADICACION}}": str(data.get("fecha_radicacion") or "según expediente"),
            "{{FECHA_RECEPCION}}": str(data.get("fecha_recepcion") or "según expediente"),
            "{{DIAS_HABILES}}": str(data.get("dias_habiles") or "según calendario hábil"),
            "{{NUMERO_FACTURA}}": str(data.get("numero_factura") or "según factura electrónica"),
            "{{NUMERO_RADICADO}}": str(data.get("numero_radicado") or "según radicado"),
            "{{SERVICIO}}": str(data.get("servicio") or "el servicio objetado"),
            "{{CUPS}}": str(data.get("cups") or "el procedimiento facturado"),
            "{{NUMERO_CONTRATO}}": str(data.get("numero_contrato") or "según contrato vigente"),
            "{{TARIFA_PACTADA}}": str(data.get("tarifa_pactada") or "tarifa contractual"),
            "{{FECHA_HOY}}": ahora.strftime("%d de %B de %Y"),
            "{{ANIO_ACTUAL}}": str(ahora.year),
        }
        resultado = plantilla
        for var, val in reemplazos.items():
            resultado = resultado.replace(var, val)
        for v in re.findall(r"\{\{[A-Z_]+\}\}", resultado):
            resultado = resultado.replace(v, f"[{v.strip('{}').lower()}]")
        return resultado

    def validar_plantilla(self, plantilla: str) -> dict:
        encontradas = re.findall(r"\{\{[A-Z_]+\}\}", plantilla)
        validas = [v for v in encontradas if v in VARIABLES_DISPONIBLES]
        invalidas = [v for v in encontradas if v not in VARIABLES_DISPONIBLES]
        return {
            "variables_encontradas": encontradas,
            "variables_validas": validas,
            "variables_invalidas": invalidas,
            "es_valida": len(invalidas) == 0,
        }

    def preview(self, plantilla: str, data: Optional[dict] = None) -> str:
        ejemplo = {
            "eps": "NUEVA EPS",
            "codigo_glosa": "TA0201",
            "valor_objetado": 1500000,
            "valor_aceptado": 0,
            "fecha_radicacion": "2026-03-01",
            "fecha_recepcion": "2026-03-15",
            "dias_habiles": 10,
            "numero_factura": "FV-2026-00123",
            "numero_radicado": "GLS-2026-00456",
            "servicio": "Consulta de urgencias",
            "cups": "890201",
            "numero_contrato": "02-01-06-00077-2017",
            "tarifa_pactada": "SOAT -20%",
        }
        return self.resolver_variables(plantilla, data or ejemplo)
