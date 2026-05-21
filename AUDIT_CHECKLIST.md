# Checklist accionable — Motor Glosas HUS

> Lista de TODOs priorizada para ir tachando.
> Ver `AUDITORIA.md` para contexto completo.

## 🔴 BLOQUEANTE — Esta semana

- [ ] **Configurar `FLY_API_TOKEN` en GitHub** — sin esto, no hay deploys automáticos
  - `fly tokens create deploy -a motor-glosas-hus` (desde Fly Web Shell)
  - GitHub → Settings → Secrets → New repository secret
  - Name: `FLY_API_TOKEN` · Value: token completo (incluye `FlyV1`)
- [ ] **Trigger primer deploy manual** desde Actions → "Deploy a Fly.io" → Run workflow
- [ ] **Verificar en Fly logs**: buscar `Seed banco HUS: 50 plantillas creadas.`
- [ ] **Validar con caso real**: generar dictamen para (cualquier_EPS, código TA0201/SO0501/CO0101/FA0101/CL0101) y confirmar que el dictamen usa la cita normativa de la plantilla HUS correspondiente

## 🟠 ALTO — 2 semanas

### Seguridad (bloqueos potenciales)
- [ ] **`admin.py:~140`** — reemplazar f-string SQL en `migracion_emergencia` por whitelist explícito de columnas o SQLAlchemy DDL
- [ ] **`admin.py:~77`** — agregar `assert count_antes - count_despues == esperadas` en dedup_historial; mover a `papelera` antes de delete real
- [ ] **`usuarios.py` password change** — requerir campo `password_actual` en `PATCH /usuarios/{id}/password` y validar con `verify_password()` antes de cambiar
- [ ] **Rate-limit endpoints sensibles** — aplicar `@limiter.limit("5/minute")` a:
  - `POST /auth/login`
  - `PATCH /usuarios/{id}/password`
  - `POST /2fa/setup`, `POST /2fa/activar`

### Pre-existentes documentados
- [ ] **CI Tests job verde** — ✅ ya arreglado en este branch (`DISABLE_SCHEDULERS=1`)
- [ ] **Plantillas HUS cargan al arranque** — ✅ ya implementado en este branch (PR #66 merged)

## 🟡 MEDIO — Próximo mes

### Consistencia de datos
- [ ] **`contratos.py:541-563`** — webhook/email al subir PDF cuando IA extrae 0 cláusulas (gestor cree que se guardó pero no)
- [ ] **`contratos.py:696-740`** — validar duplicados antes de insertar cláusula manual (mismo numero = error 409)
- [ ] **`glosas.py:_normalizar_eps`** — auditar matches por substring; reemplazar por whitelist exacta de EPSs conocidas

### Calidad de código
- [ ] **Pydantic `response_model`** en endpoints de `/glosas` más usados (top 20 por tráfico)
- [ ] **Type hints** en `/admin` (1% de cobertura) y `/contratos` (0%)
- [ ] **Reemplazar `bare except:` con logging**: `glosas.py:575`, `sistema.py:75-88`

### Frontend
- [ ] **Minificar `index.html`** (1.1MB) — gzip ya activo via fly.toml pero el bundle JS+HTML inline es pesado
- [ ] **Lazy-load secciones** del dashboard (analytics + utilidades cargan al click, no al boot)

## 🟢 BAJO — Backlog

### Limpieza
- [ ] **Eliminar 147 funciones dead-code** identificadas (mayormente migraciones viejas en `/admin/migracion-*`)
- [ ] **Métricas hardcodeadas** en `sistema.py:93` — sincronizar con realidad (tests reales: 2673, endpoints reales: 472)
- [ ] **17 routers sin tests directos** — agregar al menos 1 happy-path test por router

### Observabilidad
- [ ] Configurar Sentry para errores en producción (DSN ya importado en main.py:48)
- [ ] Dashboard de métricas IA → exponer en `/static/index.html` (datos ya están en `/sistema/diagnostico-ia`)

### Features pendientes (Phase 6 original)
- [ ] Firma digital X.509 en PDFs descargados
- [ ] A/B testing de prompts (versiones múltiples + seleccionar por performance)
- [ ] Backups automáticos de PostgreSQL prod (snapshot diario S3)
- [ ] Tests E2E con Playwright para los 3 flujos críticos

---

## ✅ Verificación contínua

| Comando | Qué verifica | Tiempo |
|---------|--------------|--------|
| `python scripts/smoke_test_prod.py` | Endpoints prod responden con status correcto | ~10s |
| `DISABLE_SCHEDULERS=1 pytest tests/ -q` | Test suite completo pasa | ~3.5min |
| `ruff check . --select F,W6 && ruff format --check .` | Lint + format | ~5s |

## 📊 Estado actual (snapshot)

- ✅ Producción **healthy** (smoke 12/12)
- ✅ Tests **2673/2673 pasan** localmente
- ✅ CI **arreglado** en branch `claude/fix-import-audit-issues-xRJw7`
- ⚠️ Auto-deploy **pendiente token** en GitHub Secrets
- ⚠️ Banco HUS **deployable** pero sin caso real probado todavía
