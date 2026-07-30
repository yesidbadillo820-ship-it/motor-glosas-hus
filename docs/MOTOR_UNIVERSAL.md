# Motor Universal — el perfil único de cada pagador

**Qué es.** Un solo lugar que responde «¿qué sabe hacer el sistema con
este pagador?». No copia datos: consulta los registros que ya existen y
los junta.

| Registro | Qué aporta al perfil |
|---|---|
| Malla contractual (`malla_contractual.py`) | El contrato vigente por fecha del hecho y el histórico |
| Perfiles de lote (`perfiles_lote.py`) | Cómo leer su Excel masivo y qué bot lo carga |
| Centro de Automatización (`automatizaciones.py`) | Los conversores que le aplican (SAVIA, VCO, EMSSANAR…) |
| Catálogo de defensa (`glosa_ia_prompts.py`) | Contacto de radicación y notas curadas |

## Dónde se ve

- **Pantalla Contratos**: al expandir cualquier pagador aparece «El
  sistema con este pagador» con sus capacidades (🤖).
- **API**: `GET /malla/perfil?pagador=X` y `GET /malla/pagadores` (el
  mapa completo).
- **Chat IA**: «¿qué se puede hacer con COOSALUD?» → herramienta
  `perfil_pagador`.

## La regla del motor

**Agregar un pagador o una capacidad NUNCA es tocar código de despacho:**
es agregar una ficha en el registro correspondiente (un contrato en la
malla, un perfil de lote, una automatización en el catálogo). El perfil
la recoge y aparece en pantalla, API y chat a la vez. Si una fuente se
cae, las demás llegan igual.
