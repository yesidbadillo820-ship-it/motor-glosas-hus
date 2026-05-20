# Auditoría Motor Glosas SINAC SC HUS — 20 Mayo 2026

**Cliente:** ESE Hospital Universitario de Santander (NIT 900.006.037-4)
**Sistema:** Motor Glosas HUS (FastAPI + frontend HTML/JS)
**Producción:** https://motor-glosas-hus.fly.dev
**Repo:** `yesidbadillo820-ship-it/motor-glosas-hus`

---

## 1. Resumen ejecutivo

| Dimensión | Estado | Detalle |
|-----------|--------|---------|
| **Disponibilidad prod** | ✅ Healthy | Smoke test 12/12 OK (`scripts/smoke_test_prod.py`) |
| **Cobertura tests** | ✅ Buena | 2673 tests pasan en 206s con `DISABLE_SCHEDULERS=1` |
| **CI** | ✅ Arreglado | Job de tests ya no se cuelga (era OOM por schedulers) |
| **Deploy automático** | ⚠️ Pendiente token | `fly-deploy.yml` listo; falta `FLY_API_TOKEN` en GitHub Secrets |
| **Frontend↔Backend** | ✅ Sin huérfanos | 0 botones llaman endpoints inexistentes |
| **Auditoría endpoints** | ⚠️ Riesgos detectados | 5 críticos (ver §3) |
| **Plantillas HUS** | ⚠️ Pendiente verificar prod | PR #66 merged; falta deploy + caso real |

**Tamaño del sistema:**
- 69 routers · 472 endpoints · 88 servicios · 29 modelos DB
- 521 archivos de tests · 4 páginas HTML

---

## 2. Lo que funciona bien

### Backend
- **Estructura modular limpia**: 69 routers separados por dominio (glosas, contratos, plantillas-gold, sistema, admin, etc.)
- **Auth centralizada en `deps.py`**: 3 dependencias (`get_usuario_actual`, `get_coordinador_o_admin`, `get_super_admin`)
- **Multi-proveedor IA con fallback**: Groq primary → Anthropic / Gemini / OpenRouter
- **Caché de llamadas IA** (`ai_cache`) con TTL para reducir costos
- **Audit log centralizado** (`AuditRepository`) en mutaciones críticas

### Frontend
- **4 páginas HTML mapeadas correctamente** al backend (`index.html`, `importar-masiva.html`, `importar-recepcion.html`, `presentacion-ia.html`)
- **Polling async** para procesos largos (batch import, análisis)
- **JWT + localStorage** para sesión persistente

### Tests
- 2673 tests, 100% pasan localmente con `DISABLE_SCHEDULERS=1`
- Cobertura sólida en servicios (parsers, validador, retry, workflow, wrapper auditoría)
- Cobertura de API parcial pero presente para los routers principales

---

## 3. Riesgos críticos (TOP 5)

| # | Router | Línea | Severidad | Problema | Fix |
|---|--------|-------|-----------|----------|-----|
| 1 | `admin.py` | ~140 | ALTO | SQL injection patrón frágil en `ALTER TABLE … TYPE VARCHAR()` con f-string | Usar SQLAlchemy DDL o whitelist explícito de columnas permitidas |
| 2 | `admin.py` | ~77 | ALTO | `db.query(GlosaRecord).delete()` en dedup sin double-check post-filter | Validar conteo antes vs después + soft-delete a papelera primero |
| 3 | `usuarios.py` | password change | ALTO | Cambio de contraseña no pide la anterior | Agregar campo `password_actual` requerido en `PATCH /usuarios/{id}/password` |
| 4 | `usuarios.py` | global | MEDIO | Sin rate-limit en cambio password / 2FA setup | Aplicar `slowapi.Limiter` con `5/minute` |
| 5 | `contratos.py` | 541-563 | MEDIO | Si extracción IA del PDF falla, gestor no recibe alerta | Webhook/email post-extract-failed cuando `len(clausulas_nuevas) == 0` y `len(clausulas_viejas) > 0` |

---

## 4. Estado por router (top 10 por tamaño)

| Router | Endpoints | Tests | Type hints | Exception handlers | Riesgo |
|--------|-----------|-------|------------|--------------------|--------|
| `/glosas` | 119 | PARTIAL | 11% | OK | ALTO (núcleo del sistema) |
| `/admin` | 77 | TESTED | 1% | OK | ALTO (operaciones destructivas) |
| `/usuarios` | 48 | TESTED | 2% | parcial | ALTO (auth/permisos) |
| `/sistema` | 42 | TESTED | 5% | bueno (20/42) | MEDIO (read-only mayormente) |
| `/contratos` | 13 | TESTED | 0% | escaso (2/13) | MEDIO |
| `/plantillas-gold` | 12 | TESTED | parcial | parcial | MEDIO |
| `/analytics` | 9 | NO TESTS | parcial | escaso | BAJO |
| `/conciliaciones` | 9 | NO TESTS | parcial | escaso | MEDIO |
| `/pwa` | 9 | NO TESTS | parcial | escaso | BAJO |
| `/soportes-auto` | 9 | NO TESTS | parcial | escaso | MEDIO |

**Brechas observadas:**
- Type hints: 24% de endpoints sin return type explícito
- Pydantic response_model: usado en 1/287 endpoints relevantes
- 17 routers sin archivo de tests directo (cobertura indirecta via integration)

---

## 5. Estado de funcionalidades clave

### Importación masiva ✅
- Endpoint: `POST /glosas/importar-masiva` (paste Excel)
- Polling: `GET /glosas/batch/{batch_id}`
- Plantilla CSV pública: `GET /glosas/importar-masiva/plantilla.csv` (fix de PR #65)
- Status: **funciona en prod**

### Importación de recepción ✅
- Endpoint: `POST /glosas/importar-recepcion`
- Polling: `GET /glosas/importar-recepcion/{id}/status`
- Genera Excel-respuesta descargable
- Status: **funciona en prod**

### Análisis IA + dictamen ⚠️
- Endpoint: `POST /analizar` (PDF + glosa → dictamen HTML)
- SSE: `GET /eventos/analizar/{trace_id}` (progreso real-time)
- Auto-crítica multi-proveedor (PR #63)
- **Pendiente:** verificar que el banco HUS de 50 plantillas (PR #66) se cargue al primer arranque post-deploy

### Plantillas gold ✅
- CRUD completo + importación masiva (JSON/CSV) + cobertura
- Banco HUS de 50 plantillas como fallback de familia
- Status: código deployable, pendiente seed real

### 2FA ✅
- Setup TOTP funcional con QR
- ⚠️ Sin rate-limit en endpoints de setup/activar

### Diagnóstico IA (`GET /sistema/diagnostico-ia`) ✅
- Métricas por proveedor (latency p50/p95/p99, hit rate, costo)
- Estado global OK/DEGRADADO/SIN_DATOS

---

## 6. Plan de acción priorizado

### Fase 1 — Esta semana (CRÍTICO)
- [ ] Configurar `FLY_API_TOKEN` en GitHub Secrets para auto-deploy
- [ ] Trigger deploy manual desde Actions → "Deploy a Fly.io" → Run workflow
- [ ] Verificar en logs: `Seed banco HUS: 50 plantillas creadas.`
- [ ] Probar 1 dictamen real para un (EPS, código) sin GOLD → ver si usa plantilla HUS

### Fase 2 — Próximas 2 semanas (ALTO)
- [ ] **Fix riesgo #1**: SQLAlchemy DDL en `admin.py` migracion_emergencia
- [ ] **Fix riesgo #2**: validar conteos antes/después de dedup
- [ ] **Fix riesgo #3**: requerir `password_actual` en cambio de password
- [ ] Rate-limit en endpoints auth-sensibles (5/min con slowapi)

### Fase 3 — Próximo mes (MEDIO)
- [ ] Migrar 119 endpoints de `/glosas` a respuestas con Pydantic `response_model`
- [ ] Webhook/email al gestor cuando extracción IA de contrato falla
- [ ] Limpieza de 147 funciones dead-code identificadas (mayormente migraciones viejas)
- [ ] Minificación de `index.html` (1.1MB) — gzip ya está via fly.toml pero el bundle es pesado

### Fase 4 — Backlog (BAJO)
- [ ] Tests E2E con Playwright para los 3 flujos críticos
- [ ] Phase 6 original: firma X.509, A/B testing prompts, backups Postgres
- [ ] Métricas hardcodeadas en `sistema.py:93` sincronizar con realidad

---

## 7. Cómo verificar continuamente

### Smoke test producción (rápido, 10s)
```bash
python scripts/smoke_test_prod.py
```

### Test suite completo (3.5 min)
```bash
SECRET_KEY=test DISABLE_SCHEDULERS=1 python -m pytest tests/ -q
```

### Auto-deploy (post-config del token)
- Push a `motor-glosas` → CI corre → si pasa, deploy automático
- Manual: GitHub → Actions → "Deploy a Fly.io" → Run workflow

---

## 8. Archivos relevantes generados

- `scripts/smoke_test_prod.py` — smoke test
- `scripts/seed_plantillas_hus.py` — seed manual (alternativa al auto-seed)
- `scripts/banco_objeciones_glosas_hus.py` — fuente de las 50 plantillas
- `data/plantillas_hus_base.json` — JSON listo para importar
- `.github/workflows/fly-deploy.yml` — auto-deploy
- `AUDITORIA.md` (este archivo)

---

_Auditoría generada el 20 de mayo de 2026 — sesión `01XHjopLrqyFtGdTtT4v1bHU`_
