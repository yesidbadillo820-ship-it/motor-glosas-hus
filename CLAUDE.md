# Instrucciones del proyecto — Motor de Glosas HUS

## ⭐ PROTOCOLO DE BITÁCORA (leer y cumplir SIEMPRE)

Este repositorio usa **`BITACORA.md`** (en la raíz) como memoria común de
todas las sesiones y todos los chats de Claude Code.

- **Al INICIAR cualquier sesión:** lee primero **`BITACORA.md`**. Ahí está el
  resumen de todo lo trabajado, lo que quedó pendiente y lo que sigue.
- **Al TERMINAR la sesión:** actualiza **`BITACORA.md`** con:
  - lo que **se hizo hoy** (agregado en "LO YA HECHO" con la **fecha**),
  - lo que **quedó pendiente** (sección **PENDIENTE**),
  - lo próximo a trabajar (sección **PARA MAÑANA**).
  Mantén el formato existente del archivo e incluye la actualización en el
  commit final (y push).
- Escribe la bitácora en **español claro, sin tecnicismos**, pensando en el
  área de Cartera / Auditoría de Cuentas Médicas del HUS (no en programadores).

## Contexto del proyecto

- Dueño: auditoría de facturación de la E.S.E. Hospital Universitario de
  Santander (HUS). Los mensajes del usuario llegan en español; responde
  siempre en español.
- **Motor de Glosas** (`app/`): aplicación web que genera con IA las respuestas
  técnico-jurídicas a las glosas de las EPS, según la norma colombiana. Incluye
  el módulo de **Pre-auditoría SINAC** (página `/preauditoria`) y los flujos de
  Dispensario/SIMED y COOSALUD.
- **Bots de carga** (`tools/`): suben las respuestas a cada portal — COOSALUD,
  SIMED (Dispensario Médico), Dinámica Gerencial (DGH), Mutual Ser, FOMAG, etc.
- **Módulo ADRES/FURIPS** (`tools/adres/`, `validador-adres/`, `tools/*.cmd`):
  validación de reclamaciones FURIPS (Circular 022/2023), informes Excel/Word
  y bots de doble clic para Windows.
- **Suite Cartera HUS** (`tools/suite_cartera_hus/`): programa de escritorio del
  analista (organizar portales → consolidar glosas → cruzar DGH → OBJECIONES),
  con una **caja de Herramientas PDF** (botón 🧰), el bot de **correos de
  pagos .msg → Excel** (botón 📧) y el bot de **unir Exceles** (botón 📊).
  Tiene versión de ventana (`suite_cartera_hus.py`) y de consola (`suite_cli.py`).
- Los `.cmd` de `tools/` son bots de doble clic para auditores en Windows:
  deben conservar finales de línea CRLF (ya hay regla en `.gitattributes`)
  y autoinstalar sus dependencias.
- Las entregas al usuario suelen ser: archivo(s) listos para copiar al
  servidor de cartera + commit/push + pull request en borrador.
- Historia detallada por fechas: ver `CHANGELOG.md` y, en lenguaje llano,
  `BITACORA.md`.

## Reglas del repo

- Escribir para el auditor: español claro, sin tecnicismos innecesarios.
- Nunca commitear usuarios ni contraseñas (siempre variables de entorno o
  archivos locales no versionados — ver "Secretos" abajo).
- Nunca incluir el identificador del modelo en commits, PRs ni código pusheado.
- No confundir plataformas: COOSALUD (vco.ctamedicas.com), SIMED (Dispensario)
  y Dinámica Gerencial (DGH) son sistemas distintos con bots distintos.
- Si el auditor pasa un archivo con más contenido del que menciona el pedido
  (varias hojas, listados de más), trabajar SOLO sobre la parte pedida
  inicialmente; si no es obvio qué hoja o grupo usar, preguntar antes de
  procesar todo el archivo. (Lección del 24-08: el cruce se hizo con la Hoja1
  de 10.017 facturas cuando el trabajo del auditor era la hoja de 5.122.)
- Antes de cargar notas crédito al SIMED, validar el CUV
  (`tools/verificar_cuv_notas.py`) — el portal acepta notas con CUV inválido
  pero quedan mal radicadas.
- Antes de un cargue masivo con un robot, correr un piloto de 1 factura.
- Claude Code no tiene acceso al disco D:, al share del hospital ni a los
  portales: para tocar esos recursos, entregar el comando PowerShell listo
  para copiar/pegar y pedir la salida al auditor.

## Trabajo holístico y calidad total

### Principio de impacto sistémico

- **Prohibido el trabajo aislado.** Al modificar una ruta o un modelo del
  backend (`app/`), hay que revisar y actualizar en el mismo cambio el
  frontend que la consume (`static/`), sus pruebas (`tests/`) y su
  documentación (`docs/`). El caso que lo enseñó: la pantalla «Salud Total»
  estuvo tres meses devolviendo «Not Found» porque se borró su router sin
  mirar que el JavaScript seguía llamándolo.
- **Visibilidad.** Cada cambio debe notarse: o el auditor lo ve en pantalla,
  o el sistema queda demostrablemente más robusto (con la prueba que lo
  demuestra).

### Los cuatro pilares de cada intervención

1. **Diseño y experiencia.** Usar las variables y componentes de
   `static/sinac-ds.css` (tokens `--sds-*`) y `static/sinac-ux.js`
   (`window.SDS_UX`). Toda pantalla necesita estado de carga, error visible
   y entendible, estado vacío, y moneda y fechas con el formato único
   (`fmtCOP`, no `toLocaleString` suelto).
2. **Arquitectura y código.** Tipado estricto (Pydantic en las respuestas,
   *type hints* en Python), sin lógica duplicada, y la lógica de negocio en
   `app/services/` — los routers de `app/api/routers/` solo reciben, validan
   y responden.
3. **Rendimiento.** Sin consultas dentro de bucles (N+1), índices en los
   campos por los que de verdad se busca, y sin llamadas repetidas a la IA
   por lo mismo.
4. **Funcionalidad y pruebas.** Toda mejora va con su prueba de `pytest` y
   sus casos borde: glosa extemporánea, factura en cero, archivo vacío,
   fecha al revés, red caída.

### Lo que estas reglas NO autorizan

Estas reglas se subordinan a las de arriba y a las tres del proyecto:

- **No reescribir lo que funciona.** Un pilar no es permiso para refactorizar
  código estable: hace falta una razón técnica demostrable y una prueba que
  muestre el defecto antes de tocarlo.
- **Cambio mínimo.** Cien cambios pequeños y reversibles, no uno gigante.
- **No inventar.** Ni datos, ni contratos, ni artículos, ni CUPS, ni tarifas.
  Sin evidencia, el dictamen dice «no existe evidencia suficiente».

El tablero de este programa es `MASTER_IMPROVEMENT_PLAN.md`: sus casillas se
marcan solo cuando el trabajo está hecho **y probado**, nunca por adelantado.

Contexto adicional por flujo de trabajo (léelos cuando el tema aplique):
- `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` — respuesta de glosas del Dispensario en SIMED.
- `docs/CONTEXTO_DISPENSARIO_NOTAS.md` — cargue de notas crédito en SIMED.
- `docs/CONTEXTO_COOSALUD.md` — respuesta de glosas COOSALUD.
- `docs/ENTREGA_MODULO_ADRES_FURIPS.md` — entrega técnica del módulo ADRES/FURIPS.

## Notas técnicas útiles

- **Pruebas:** `pytest` (config en `pytest.ini`, tests en `tests/`). CI corre
  `ruff check . --select F,W6` + `ruff format --check .` + `pytest`. Antes de
  hacer commit, deja el código formateado con `ruff format` y sin errores F/W6.
- **Secretos:** nunca subir contraseñas ni claves. Las claves de los portales
  de la Suite Cartera HUS van en `config/entidades.credenciales.json` (local,
  no versionado).
