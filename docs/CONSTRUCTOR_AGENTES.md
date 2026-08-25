# Constructor de Agentes

**Qué es.** Menú → Herramientas → **Agentes**. Un agente es una **ficha**,
no código: nombre, misión (qué hace y para qué), instrucciones (cómo debe
trabajar) y las herramientas del sistema que tiene permitidas. Se
construye desde la pantalla en un minuto y corre de inmediato.

## Cómo funciona por dentro

El agente corre con el **mismo motor del asistente maestro**: su misión e
instrucciones se montan encima del sistema base, y las herramientas se
**recortan a las permitidas por su ficha** — un agente de vencimientos no
puede tocar soportes ni contratos si no se le dieron. Por eso un agente
nuevo hereda todo lo que el sistema ya sabe (expediente, malla,
diagnóstico, soportes, tarifas…) sin una línea de código.

## Plantillas de fábrica

- **Vigilante de vencimientos** — corre el diagnóstico, ordena por plata
  en riesgo y dice qué glosas responder primero.
- **Preparador de mesa** — arma el panorama completo de un pagador o una
  factura antes de la audiencia de conciliación.

Un clic llena el formulario; se ajusta y se guarda como propio.

## Trazabilidad y permisos

| Acción | Quién puede | Queda en auditoría |
|---|---|---|
| Ver agentes y plantillas | Cualquier usuario autenticado | — |
| Construir | Auditor o superior | `AGENTE_CREADO` (misión + herramientas) |
| Correr | Auditor o superior (consume cupo IA) | `AGENTE_CORRIDO` (pregunta + herramientas usadas) |
| Retirar | Coordinador o administrador | `AGENTE_RETIRado` — la ficha no se borra |

## API

`GET /agentes` · `POST /agentes` · `POST /agentes/{id}/correr` ·
`DELETE /agentes/{id}`.
