# PROYECTO — Tablero maestro

**Última actualización:** 05-08-2026
**Uso:** este archivo es el centro de control. Se actualiza cuando cambia el
estado de un módulo, el objetivo actual o las próximas tareas. No es
documentación: es un tablero de trabajo.

---

## MÓDULOS

### 1. Motor de Glosas — aplicación web
- **Estado:** Activo · **Prioridad:** Crítica
- **Entrada:** `app/main.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** FastAPI · SQLite (`glosas.db`) · `static/index.html`
- **Próximo objetivo:** ninguno propio; sostiene el objetivo actual del proyecto
- **Riesgo:** una sola pantalla (`static/index.html`) concentra toda la interfaz

### 2. Dictamen con IA
- **Estado:** Activo · **Prioridad:** Crítica
- **Entrada:** `app/services/glosa_service.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** `glosa_ia_prompts.py` · Groq (primario) · Anthropic (respaldo)
- **Próximo objetivo:** cerrar los 5 defectos de la segunda ronda de pruebas
- **Riesgo:** puede afirmar cosas falsas (cláusula de contrato inventada)

### 3. Quality Gate — verificación del dictamen
- **Estado:** Experimental · **Prioridad:** Media
- **Entrada:** `app/services/quality_gate/orchestrator.py`
- **Responsable:** PENDIENTE DE VALIDAR
- **Dependencias:** `post_validator.py` · `citation_verifier.py` · `quality_gate_adapter.py`
- **Próximo objetivo:** decidir si se enciende (`QUALITY_GATE_ENABLED`)
- **Riesgo:** está apagado por defecto, así que sus guardas hoy no protegen nada

### 4. Pre-auditoría SINAC
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `app/api/routers/preauditoria.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** módulo 1 · base de datos · Excel de fuentes
- **Próximo objetivo:** decidir si el buscador lento de la pestaña Fuentes molesta en el día a día
- **Riesgo:** el buscador recorre 189.452 filas en cada consulta

### 5. Glosas ADRES — pantalla web
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `app/api/routers/glosas_adres.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** módulo 1 · `tools/preauditar_glosas_adres.py`
- **Próximo objetivo:** piloto con un gestor real (paquete 31068, 5 facturas)
- **Riesgo:** nunca se ha usado con un gestor real

### 6. Conciliación y acta
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `app/api/routers/conciliacion.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** módulo 1 · módulo 16 · plantilla de acta
- **Próximo objetivo:** firmar el acta de las 147 facturas
- **Riesgo:** bloqueado por la cuenta contable y por la discrepancia del aceptado

### 7. Contratos, cláusulas y tarifas
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `app/api/routers/contratos.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** `extractor_clausulas_contrato.py` · `tarifa_lookup_service.py` · base de datos
- **Próximo objetivo:** cargar el PDF de al menos un contrato y extraer sus cláusulas
- **Riesgo:** hay 0 cláusulas cargadas, así que ninguna cita de cláusula se puede verificar

### 8. Gobierno de IA y Diagnóstico
- **Estado:** Activo · **Prioridad:** Media
- **Entrada:** `app/api/routers/diagnostico.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** módulo 1 · `ia_status.py` · `motor_proceso.py`
- **Próximo objetivo:** PENDIENTE DE VALIDAR
- **Riesgo:** ninguno conocido

### 9. Agente local de lotes y bots
- **Estado:** Activo · **Prioridad:** Media
- **Entrada:** `tools/agente_lotes.py`
- **Responsable:** PENDIENTE DE VALIDAR
- **Dependencias:** módulo 1 · token `AGENTE_LOTES_TOKEN` · `tools/agente_bots_hus.py`
- **Próximo objetivo:** PENDIENTE DE VALIDAR
- **Riesgo:** si el token queda vacío, los endpoints del agente devuelven 503

### 10. Bot SIMED — Dispensario Médico
- **Estado:** Activo · **Prioridad:** Crítica
- **Entrada:** `tools/responder_glosas_simed.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** Playwright · credenciales SIMED · `tools/cargar_soportes_simed.py`
- **Próximo objetivo:** cargar las 23 pendientes (piloto con HUS0000513796 y luego la corrida completa)
- **Riesgo:** el portal acepta notas con CUV inválido y quedan mal radicadas

### 11. Bot COOSALUD
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `tools/responder_glosas_coosalud.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** Playwright · credenciales vco.ctamedicas.com · Excel consolidado
- **Próximo objetivo:** correr la pertinencia fusionada (37 facturas / 5.736 glosas) y cerrar los lotes 06, 07 y 08
- **Riesgo:** quedan lotes sin confirmar resultado (02, 06, 07, 08)

### 12. Bot SIIFA — Ministerio de Salud
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `tools/responder_glosas_siifa.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** `tools/siifa_client.py` · API oficial de interoperabilidad · credenciales SIIFA
- **Próximo objetivo:** piloto de 1 glosa y cargue de las 1.082 respuestas reales del hospital
- **Riesgo:** 1.497 respuestas redactadas por el motor siguen sin revisar y la glosa sin responder se entiende aceptada

### 13. Bot Dinámica Gerencial (DGH)
- **Estado:** Activo · **Prioridad:** Media
- **Entrada:** `tools/responder_glosas_dgh.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** programa de escritorio DGH · `tools/login_dg.py` · red del hospital
- **Próximo objetivo:** PENDIENTE DE VALIDAR
- **Riesgo:** PENDIENTE DE VALIDAR

### 14. Bots de portales secundarios (FOMAG, Mutual Ser)
- **Estado:** Activo · **Prioridad:** Baja
- **Entrada:** `tools/responder_glosas_fomag.py`
- **Responsable:** PENDIENTE DE VALIDAR
- **Dependencias:** Playwright · credenciales del portal · `tools/responder_glosas_mutual_ser.py`
- **Próximo objetivo:** PENDIENTE DE VALIDAR
- **Riesgo:** sin uso registrado desde su entrega

### 15. Validador FURIPS (escritorio)
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `tools/adres/validar_furips.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** Circular 022/2023 · RIPS y XML DIAN · OCR para PDF escaneados
- **Próximo objetivo:** copiar el paquete completo al servidor y correr la v2.1 del bot DE4401
- **Riesgo:** ninguno conocido

### 16. Validador ADRES (web)
- **Estado:** Activo · **Prioridad:** Media
- **Entrada:** `validador-adres/app.py`
- **Responsable:** PENDIENTE DE VALIDAR
- **Dependencias:** módulo 15 · puerto 8010 · `VALIDADOR_ADRES_WEB.cmd`
- **Próximo objetivo:** PENDIENTE DE VALIDAR
- **Riesgo:** ninguno conocido

### 17. Conciliación del Dispensario (cadena de escritorio)
- **Estado:** Activo · **Prioridad:** Alta
- **Entrada:** `tools/piloto_conciliacion_dispensario.py`
- **Responsable:** Yesid (dueño)
- **Dependencias:** `indexar_soportes_dispensario.py` · `motor_evidencia_dispensario.py` · `motor_decision_dispensario.py`
- **Próximo objetivo:** cerrar el listado de las 147 facturas para la mesa
- **Riesgo:** 29 facturas con diferencia entre el valor glosado del lote y el de cartera

### 18. Servidor y túnel local (motor en línea)
- **Estado:** Activo · **Prioridad:** Crítica
- **Entrada:** `tools/servidor_motor_local.cmd`
- **Responsable:** Yesid (dueño)
- **Dependencias:** `tools/tunel_motor_local.cmd` · Cloudflare Tunnel · PC de cartera
- **Próximo objetivo:** ninguno; mantener en línea
- **Riesgo:** el hospital bloquea UDP, el túnel solo funciona con `--protocol http2`

---

## OBJETIVO ACTUAL DEL PROYECTO

✔ **Cerrar los 5 defectos del dictamen detectados en la segunda ronda de pruebas (05-08-2026).**

---

## PRÓXIMAS TAREAS

1. **Cláusula de contrato inventada** — el dictamen cita "CLÁUSULA 4.2" de un contrato del que no hay ninguna cláusula cargada.
2. **Resolución 3047/2008** — se cita como fundamento propio pese a que la propia base de normas del motor registra que la 2284/2023 la reemplazó.
3. **Aritmética no detectada** — la EPS glosó $1.850.000 sobre una factura de $1.500.000 y el motor no lo señaló.
4. **Pertinencia respondida como tarifa** — la glosa TA0601 preguntaba por pertinencia y se respondió con argumento tarifario.
5. **Contradicción no señalada** — FA0302 ("servicio no prestado") y TA0801 ("tarifa superior") sobre el mismo ítem no pueden ser ciertas a la vez.

---

## BLOQUEANTES

1. **Cuenta contable del acta** — es el único campo del acta de las 147 facturas que no existe en ninguna base disponible. Depende de contabilidad/DGH.
2. **Discrepancia del aceptado** — el lote dice $0 y cartera registra $1.758.956 en 8 facturas. Sin resolverlo no se firma el acta.
3. **CUV rechazados** — SISTEMAS no ha corregido el RIPS de las 3 facturas con RVC086 ni reejecutado la validación de las otras 6. Sin eso no se radican en SIMED.
4. **Faltan 2 PDF del DIAN** — HUS413266 (radicado 492346) y HUS417459 (radicado 521665). Sin el PDF no se arman las carpetas.
5. **0 cláusulas de contrato cargadas** — mientras la base esté vacía, ninguna cita de cláusula del dictamen se puede verificar contra el contrato firmado.

---

## REGLAS DEL PROYECTO

1. No modificar código estable sin una razón técnica demostrable.
2. Un solo objetivo a la vez.
3. Cambio mínimo: se elige la solución que toque menos archivos.
4. No crear módulos duplicados: primero revisar si ya existe.
5. Nunca commitear usuarios ni contraseñas.
6. Nunca incluir el identificador del modelo en commits, PR ni código.
7. Antes de un cargue masivo con un robot, piloto de 1 factura.
8. Validar el CUV antes de cargar notas crédito al SIMED.
9. No confundir plataformas: COOSALUD, SIMED y DGH son sistemas distintos.
10. Toda entrega pasa la suite completa de pruebas antes del push.
