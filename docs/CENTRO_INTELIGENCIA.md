# Centro de Inteligencia

**Qué es.** La primera opción del menú. El sistema barre toda la operación y
responde una sola pregunta: **¿qué hay que hacer hoy y por cuánta plata?**
El número rojo del menú son los frentes urgentes — se actualiza solo, sin
abrir la pantalla.

## Qué vigila

| Fuente | Qué detecta | Prioridad |
|---|---|---|
| Vencimientos | Glosas ya vencidas (con su valor en riesgo) y las que vencen en ≤5 días | 1 / 2 |
| Malla contractual | Contratos vencidos y por vencer (aviso a contratación) | 2 |
| Verificaciones | Análisis del mes defendidos SIN contrato vigente (a SOAT pleno) o con pagador fuera de malla | 2 / 3 |
| Conciliaciones | Audiencias que ya pasaron sin resultado registrado, y las de los próximos 7 días | 1 / 2 |
| Actas de mesa | Actas subidas que siguen con hallazgos de cuadre sin corregir | 3 |

Cada acción dice **qué pasa, por qué importa, cuánto vale** y trae el botón
que lleva a la pantalla donde se resuelve. Se ordena por prioridad y plata.

Si una fuente falla, las demás llegan igual y el barrido lo declara
(«No se pudo revisar: …») — un diagnóstico incompleto avisa; uno caído no
dirige nada.

## La IA como directora

El asistente del chat tiene la misma información (herramienta
`diagnostico_operacion`) y una regla dura nueva: cuando se le pregunta
«¿qué hago hoy?», «¿qué es urgente?» o «¿cómo va la operación?», no
improvisa — corre el barrido y dirige: empieza por lo rojo, dice la plata
en juego y qué pantalla abrir primero.

## Para consultarlo desde fuera

`GET /inteligencia/diagnostico` — solo lectura, cualquier usuario
autenticado. Devuelve titular, frentes urgentes, valor en juego y la lista
de acciones con sus destinos.
