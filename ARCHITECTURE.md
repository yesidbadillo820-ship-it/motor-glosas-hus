# Arquitectura — Motor de Glosas HUS

## Visión general

Sistema FastAPI de defensa automatizada de glosas médicas para la ESE Hospital Universitario de Santander (HUS). Genera dictámenes técnico-jurídicos usando IA (Claude/Gemini/Groq) conforme al marco normativo colombiano.

```
Cliente (browser)  →  FastAPI  →  GlosaService  →  LLM (Anthropic/Gemini/Groq)
                                ↕
                          SQLite / PostgreSQL
```

---

## Estructura de módulos

### `app/api/routers/`

| Módulo | Prefijo | Descripción |
|--------|---------|-------------|
| `glosas.py` | `/glosas` | CRUD principal (~119 rutas): historial, importar, analizar, reanalizar, workflow |
| `glosas_stats.py` | `/glosas/stats` | Analítica (~171 rutas): todas las estadísticas agregadas del módulo |
| `health.py` | — | `GET /health`, `GET /health/detail`, `GET /mi-dia` |
| `auditoria_forense.py` | `/auditoria-forense` | Búsqueda forense por IP, IPs frecuentes |
| `consulta_normativa.py` | `/normas` | Catálogo de 101 normas colombianas + export JSON |
| `tareas_diarias.py` | `/usuarios/yo/tareas` | Checklist diario del gestor (CRUD) |
| `firma.py` | `/dictamenes` | Firma HMAC-SHA256 de dictámenes |
| `eventos_live.py` | `/eventos` | Server-Sent Events para progreso de importación |
| `auth_router.py` | `/auth` | Login, refresh token, 2FA TOTP |
| `admin.py` | `/admin` | Gestión de usuarios, contratos, configuración |

### `app/services/`

| Servicio | Función |
|----------|---------|
| `glosa_service.py` | Orquestador principal: genera dictámenes, maneja IA fallback |
| `glosa_ia_prompts.py` | Construcción del system/user prompt + detección excedente facturado |
| `validador_dictamen.py` | 12 checks de calidad del dictamen (score 0-100) |
| `firma_digital.py` | HMAC-SHA256 para integridad de dictámenes |
| `memoria_gestor.py` | Aprende el estilo de cada auditor desde sus refinamientos |
| `ia_auditora_proactiva.py` | Scheduler 6AM: pre-análisis de glosas críticas |
| `autopilot_service.py` | Decisión autónoma para glosas con texto fijo |
| `recepcion_service.py` | Parser de Excel de recepción (hoja INICIAL/RATIFICADA) |

### `app/core/`

| Módulo | Función |
|--------|---------|
| `correlation.py` | Middleware `X-Request-ID` — trazabilidad end-to-end |
| `logging_utils.py` | Logger JSON estructurado con request_id, user_email, glosa_id |
| `config.py` | Settings via `pydantic-settings` (env vars + `.env`) |
| `rate_limit.py` | Rate limiting vía `slowapi` |

---

## Cerebro IA — flujo de generación de dictamen

```
1. AUDITORÍA PRE-IA
   ├── Detectar excedente facturado (valor > pactado) → ACEPTAR_TOTAL
   ├── Detectar glosa extemporánea (>20 días hábiles)
   └── Detectar textos fijos (RE9701/RE9702/RE9602 → sin LLM)

2. ROUTING DE MODELO (solo Anthropic)
   ├── HAIKU  — valor < 500k + ≤1 PDF + texto < 800c (−75% costo)
   ├── SONNET — caso por defecto
   └── OPUS   — valor ≥ 10M + ≥2 PDFs (máxima calidad)

3. PROMPT CACHING (Anthropic)
   └── system_prompt ≥ 3000 chars → cache_control: ephemeral, ttl: 1h
       (−90% costo en llamadas repetidas con mismo system)

4. GENERACIÓN LLM
   └── Retry con backoff (3 intentos: httpx timeouts + protocol errors)

5. AUTO-CRÍTICA (nuevo — Fase 3)
   ├── evaluar_dictamen() → score + checks fallidos
   └── Si score < 70 → 1 llamada de refinamiento (temperature=0.05)

6. POST-PROCESADO
   ├── Sanitizadores: "injustificado/a" → sinónimos, typos IA
   ├── Anti-alucinación: $[PLACEHOLDER] → "EL VALOR INDICADO EN EL EXPEDIENTE"
   ├── Mayúsculas institucionales (estándar ESE HUS)
   └── _truncar_runaway(): detecta bucles de repetición
```

---

## Base de datos — modelos clave

| Tabla | Modelo | Descripción |
|-------|--------|-------------|
| `historial` | `GlosaRecord` | Glosa principal (600+ campos) |
| `dictamen_versiones` | `DictamenVersionRecord` | Historial inmutable de dictámenes |
| `audit_log` | `AuditLogRecord` | Trazabilidad forense de cambios |
| `contratos` | `ContratoRecord` | Contratos EPS con tarifas |
| `usuarios` | `UsuarioRecord` | Gestores con rol, 2FA, workload |
| `tareas_diarias` | `TareaDiariaRecord` | Checklist diario por gestor |
| `conciliaciones` | `ConciliacionRecord` | Mesas de conciliación |

---

## Marco normativo incorporado

- Ley 1438 de 2011, Art. 57 — glosas, plazo respuesta (5 días hábiles)
- Decreto 4747 de 2007, Art. 20 — conciliación de auditorías
- Resolución 2284 de 2023 — procedimientos glosas (deroga Res. 3047/2008)
- Ley 100 de 1993 — sistema general de seguridad social en salud
- Sentencia T-760/2008, T-1025/2002 — obligaciones constitucionales EPS

---

## Migración de datos

Alembic configurado con autogenerate apuntando a `app.models.db`.

```bash
# Verificar estado de migraciones
DATABASE_URL=sqlite:///./glosas.db alembic current

# Aplicar migraciones en producción
DATABASE_URL=postgresql://... alembic upgrade head

# Generar nueva migración tras cambios al modelo
alembic revision --autogenerate -m "descripcion_cambio"
```

---

## CI / Calidad

| Check | Herramienta | Configuración |
|-------|-------------|---------------|
| Linting | ruff (F, W6) | pyproject.toml |
| Formato | ruff format | pyproject.toml |
| Tests | pytest | pytest.ini |
| Seguridad | pip-audit | .github/workflows/ci.yml |
| Pre-commit | ruff + pre-commit-hooks | .pre-commit-config.yaml |

```bash
# Ejecutar suite completa localmente
PYTHONPATH=/tmp/crypto_fix python -m pytest tests/ -q

# Lint rápido
ruff check . --select F,W6
ruff format --check .
```

---

## Variables de entorno clave

| Variable | Requerido | Descripción |
|----------|-----------|-------------|
| `SECRET_KEY` | Sí | Clave HMAC y JWT (nunca el default en prod) |
| `DATABASE_URL` | No | SQLite por defecto, PostgreSQL en prod |
| `ANTHROPIC_API_KEY` | No | Modelo primario recomendado |
| `GROQ_API_KEY` | No | Fallback gratuito |
| `GEMINI_API_KEY` | No | Fallback alternativo |
| `PRIMARY_AI` | No | `anthropic` \| `groq` \| `gemini` (default: anthropic) |
| `SENTRY_DSN` | No | Monitoreo de errores |
| `POSTHOG_API_KEY` | No | Analytics de producto |
