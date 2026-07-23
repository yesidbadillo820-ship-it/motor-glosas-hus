# Seguimiento Semanal de Impacto — HOSPIAI (Entrega 2)

**ESE HUS · Cuentas Médicas y Cartera**

Se llena **cada viernes**, contra la línea base del 23-jul-2026
(ver `docs/ACTA_LINEA_BASE.md`). El objetivo es demostrar el impacto con números:
más facturas LISTAS, más valor recuperado, mejor HOS. **No se construyen agentes
nuevos en esta etapa** — solo se usa la plataforma y se mide.

---

## Tabla de seguimiento

| Semana (viernes) | Facturas LISTAS | % LISTAS | Valor listo | Δ facturas vs. semana previa | HEV pendientes | Entidad sin resolver | HOS | Notas |
|---|---|---|---|---|---|---|---|---|
| **23-jul (LÍNEA BASE)** | 7.840 | 62,6 % | $ 38.646.727.859 | — | 3.275 | 29 | *(capturar)* | Primera corrida real. Palanca: HEV $1.256 M. |
| 30-jul | | | | | | | | |
| 06-ago | | | | | | | | |
| 13-ago | | | | | | | | |
| 20-ago | | | | | | | | |

---

## De dónde sale cada número (comandos)

- **Facturas LISTAS / % / Valor listo** → `py tools\hospiai.py resumen` (fila LISTA), o el `panel_ejecutivo.html`.
- **HEV pendientes** → `py tools\hospiai.py oportunidades` (grupo HEV).
- **Entidad sin resolver** → `py tools\hospiai.py resumen` (fila ENTIDAD_NO_RESUELTA).
- **HOS** → `py tools\hospiai_comando.py hos`, o arriba del panel ejecutivo.
- **Δ facturas** → LISTAS de esta semana − LISTAS de la semana anterior.

> Corré `py tools\hospiai_operacion.py mejora` cada viernes: te resume qué mejoró,
> qué empeoró y qué cambiar el lunes. Pegá lo relevante en la columna **Notas**.

---

## Metas del primer mes (contra la línea base)

| Métrica | Día 0 | Meta |
|---|---|---|
| Facturas LISTAS | 7.840 (62,6 %) | **9.000+** (dirección) · techo 11.115 (88,8 %) por HEV |
| Entidad sin resolver | 29 ($ 551 M) | **0** (quick-win de config) |
| Valor recuperado acumulado | $ 0 | *(sumar semana a semana)* |
| HOS | *(capturar)* | subir de nivel |

---

## Cómo leer el resultado ante gerencia

El caso de éxito se cuenta en una frase: *"En el primer mes pasamos de 7.840 a
[N] facturas listas y liberamos $[X] millones, sin contratar a nadie, atacando la
HEV y las entidades sin resolver que HOSPIAI señaló el día 1."*
