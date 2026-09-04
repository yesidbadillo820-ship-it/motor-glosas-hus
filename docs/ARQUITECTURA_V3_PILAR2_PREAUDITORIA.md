# V3 · Pilar 2 — Pre-Auditoría Concurrente (antes de timbrar)

**Estado:** arquitectura aprobada por el auditor (04-09-2026). Esta entrega
cubre **solo el backend y sus pruebas**. La pantalla se hace después.

---

## 1. Qué problema resuelve

Hoy el hospital audita **después**: la EPS glosa, y el área de cartera pelea
la plata durante meses. La pre-auditoría concurrente le da vuelta al reloj:
**el HIS del hospital nos consulta ANTES de timbrar la factura electrónica**,
y el motor le dice si esa factura va a ser glosada y por cuánto.

Cada peso que se corrige antes de timbrar es un peso que nunca entra en
cartera. Corregir después cuesta un ciclo completo de glosa y respuesta.

## 2. Cómo se conecta el HIS

El HIS manda un **JSON** con la factura que está a punto de timbrar y recibe
un **JSON** con el dictamen. Una sola llamada, sincrónica:

```
POST /pre-auditoria/evaluar
Header: X-Agente-Token: <token de máquina>     (o sesión de auditor)
```

**Latencia.** El facturador tolera hasta **15 segundos**. Nosotros nos
comprometemos a **10 segundos como techo duro** — el resto es margen de red.
El presupuesto se reparte así, y se vigila con reloj dentro del motor:

| Tramo | Techo | Qué pasa si se pasa |
|---|---|---|
| Reglas duras (Python) | ~0,1 s | No aplica: son cuentas, no llamadas |
| Cruce clínico (Groq) | 6 s | Se corta y se responde sin él, con aviso |
| Escritura del evento | 0,5 s | Reservado |
| **Total** | **10 s** | Nunca se supera: el reloj manda |

Si al llegar al cruce clínico quedan menos de 1,5 s de presupuesto, **ni se
intenta**: se responde con lo que las reglas duras ya dictaminaron.

## 3. La cadena de validación (Chain of Responsibility)

Primero lo barato y seguro; al final lo caro e incierto. **Python decide,
la IA opina** — la misma doctrina del motor de glosas.

```
payload del HIS
      │
      ├─ 1. REGLAS DURAS (deterministas, sin red, sin IA)
      │     · aritmética de la factura
      │     · topes tarifarios (tarifa pactada / catálogo oficial)
      │     · cruce de género   (procedimiento vs. sexo registrado)
      │     · cruce de edad     (neonatal / pediátrico / obstétrico)
      │     · vías quirúrgicas  (abierta vs. laparoscópica, excluyentes)
      │     · coherencia de fechas y estancia
      │     · doble facturación
      │     · contrato vigente el día de la atención
      │     · UCI sin marcador clínico en la epicrisis
      │
      └─ 2. CRUCE CLÍNICO (Groq)
            · ¿cada CUPS facturado tiene respaldo en la epicrisis?
            · devuelve JSON estricto; lo que no venga en forma se descarta
```

Una regla dura que dispara **BLOQUEO** no impide que corran las demás: el
facturador quiere ver **todos** los reparos de una vez, no de uno en uno.

## 4. El contrato de salida (rígido)

```json
{
  "status": "APROBADO | ADVERTENCIA | BLOQUEO",
  "alertas": [
    {
      "codigo_glosa": "TA5801",
      "titulo": "Valor por encima de la tarifa pactada",
      "detalle": "...",
      "severidad": "BLOQUEO",
      "origen": "REGLA_DURA | IA",
      "regla": "topes_tarifarios",
      "item": "470302",
      "valor_en_riesgo": 120000.0
    }
  ],
  "valor_en_riesgo": 120000.0,
  "recomendacion_accion": "TIMBRAR | REVISAR_ANTES_DE_TIMBRAR | CORREGIR_ANTES_DE_TIMBRAR"
}
```

Más los metadatos de trazabilidad (`evento_id`, `duracion_ms`,
`cruce_clinico`, `modelo_utilizado`). El HIS puede ignorarlos; el hospital no.

**Los códigos de glosa son los oficiales** del Manual Único (Anexo Técnico 3),
tomados de `app/services/catalogo_glosas.py`. No se inventa ninguno: la alerta
proyecta la causal con la que la EPS glosaría, no una etiqueta nuestra.

**El valor en riesgo no se cuenta dos veces.** Si un mismo ítem dispara tres
reglas, el riesgo de ese ítem es el mayor de los tres, no la suma; y el total
nunca supera el valor de la factura.

## 5. Qué queda escrito

Tabla **`pre_auditoria_eventos`**: una fila por evaluación, con el payload
tal como llegó, el dictamen, el valor en riesgo y cuánto tardó cada tramo.
No se edita nunca. Sirve para tres preguntas que hoy no tienen respuesta:

- ¿esta factura pasó por la pre-auditoría y qué le dijimos?
- ¿cuánta plata evitamos que se glosara este mes?
- ¿se timbró a pesar del bloqueo? (se cruza cuando llega la glosa real)

## 6. Lo que este pilar NO hace

- **No detiene el timbrado.** Nosotros dictaminamos; quien decide es el
  facturador. El motor deja constancia, no bloquea la caja.
- **No inventa.** Si no hay tarifa pactada cargada para ese CUPS, la regla de
  topes **no opina**: guarda silencio en vez de estimar un valor.
- **No reemplaza al médico auditor.** El cruce clínico levanta la mano; la
  pertinencia la decide una persona.
