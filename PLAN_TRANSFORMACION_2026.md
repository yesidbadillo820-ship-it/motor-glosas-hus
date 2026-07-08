# Plan de Transformación Motor Glosas HUS 2.0 — Mayo 2026

> Aprobado por Yesid (21 mayo 2026): "Plan completo 4 semanas".

## Visión

Cuando un auditor abre la app, debe sentir en orden:
1. **0.5s**: "esto se ve diferente, premium"
2. **3s**: "ya sabe qué necesito sin que yo lo pida"
3. **15s** (primer dictamen): "esto es MEJOR que lo que yo escribiría"
4. **1 semana**: "no puedo trabajar sin esto"

## Los 6 ejes

### EJE 1 — Cerebro Multi-Modelo Orquestado
Cada modelo hace lo que mejor sabe:
- **Claude Sonnet 4.5**: razonamiento legal complejo, redacción jurídica formal
- **Gemini 2.0 Flash**: extracción multimodal de PDFs, clasificación rápida
- **Groq Llama 3.3**: velocidad masiva, batches

Multi-agente: 1 escritor + 1 crítico + 1 verificador de citas en paralelo.

### EJE 2 — Calidad Determinística End-to-End
Pipeline que GARANTIZA calidad antes de mostrar:
1. **Pre-validador** (deterministic, antes de IA)
2. **Generación** (IA con plantilla HUS verbatim)
3. **Post-validador** (deterministic, después de IA)
4. Si falla → **regenerar con otro modelo** (max 3 intentos)
5. Si sigue fallando → **escalar a humano** con razón específica

### EJE 3 — UX Premium "Futuro"
- Modo Enfocado (default al click Analizar)
- Comando Palette ⌘K
- Dictamen como documento vivo con secciones colapsables
- Atajos de teclado para power users
- Design System propio (no Bootstrap genérico)
- Glassmorphism selectivo

### EJE 4 — Inteligencia Ambiental
- Auto-completar contexto desde número de factura
- Predicción de plantilla óptima EN VIVO mientras escribes
- Sugerencias contextuales ("esta glosa se parece a la #X")
- Avisos proactivos en topbar
- Aprendizaje continuo del gestor

### EJE 5 — Datos como Protagonista
- Dashboard que cuenta una historia
- Mapa de calor EPS × Código
- Funnel Sankey de flujo de glosas
- Predicciones para hoy
- Comparativa entre auditores

### EJE 6 — Confianza Visible
- Citas con preview (hover muestra texto completo de la norma)
- Score desglosado siempre visible
- Botón "Explícame" (IA explica decisiones)
- Trazabilidad de plantilla
- Auditoría visual de cómo se generó

## Roadmap — 4 Olas en 4 Semanas

### 🌊 Ola 1 (Semana 1) — Eliminar bugs raíz
**Quality Gate Determinístico**

- [x] Pre-validador (`app/services/quality_gate/pre_validator.py`) — PR-A
- [ ] Post-validador con corpus normativo real — PR-B
- [ ] Orchestrator con regeneración multi-modelo — PR-C

**Métrica objetivo**: tasa de regeneración < 15%, cero citas inventadas llegando al usuario.

### 🌊 Ola 2 (Semana 2) — Cerebro multi-modelo
- [ ] `app/services/ia_router.py` con clasificación de complejidad
- [ ] Multi-agente paralelo (escritor / crítico / verificador)
- [ ] Cache semántico (no solo hash exacto)
- [ ] Dashboard `/sistema/orquestador`

**Métrica objetivo**: latencia p50 < 8s, costo/dictamen baja 30%.

### 🌊 Ola 3 (Semana 3) — UX Premium
- [ ] Design System en `/static/css/sinac-ds.css`
- [ ] Refactor `index.html` modular
- [ ] Modo enfocado
- [ ] Comando palette ⌘K
- [ ] Atajos de teclado completos
- [ ] Animaciones intencionales

**Métrica objetivo**: Lighthouse > 90.

### 🌊 Ola 4 (Semana 4) — Inteligencia ambiental
- [ ] Auto-context desde factura
- [ ] Predicción de plantilla en vivo
- [ ] Sugerencias contextuales
- [ ] Avisos proactivos
- [ ] Aprendizaje del gestor

**Métrica objetivo**: gestor llena 60% menos campos para mismo dictamen.

## Garantías de calidad transversales

1. **TDD estricto** — tests ANTES del código
2. **Feature flags** — rollback en 1 segundo
3. **Métricas observables** — cada PR mide antes/después
4. **Snapshot testing** — dictámenes reales como golden files

## Progreso

| Ola | Item | Estado | Tests |
|---|---|---|---|
| 1 | Pre-validador determinístico | ✅ | 49 |
| 1 | Post-validador con corpus real | ✅ | 24 |
| 1 | Orchestrator con regeneración multi-modelo | ✅ | 9 |
| 2 | IA Router multi-modelo (Claude/Groq/Gemini) | ✅ | 23 |
| 3 | Design System propio (Inter + Source Serif) | ✅ | UI |
| 3 | Modo Enfocado | ✅ | UI |
| 3 | Command Palette ⌘K | ✅ | UI |
| 3 | Atajos de teclado | ✅ | UI |
| 3 | Dictamen como documento jurídico premium | ✅ | UI |
| 4 | Análisis predictivo en tiempo real | ✅ | 18 |
| 4 | Predicción de plantilla óptima | ✅ | — |
| 4 | Sugerencias contextuales (casos similares) | ✅ | — |
| 4 | Detección de complejidad + ratificación auto | ✅ | — |
| 4 | Frontend con debounce 250ms | ✅ | UI |

**Total: 123 tests verdes** (49+24+9+23+18). Cero regresiones.
