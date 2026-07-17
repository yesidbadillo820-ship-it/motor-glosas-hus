# Agente de Lotes — aplicación de escritorio

Conecta la app web (Motor Glosas) con los bots de portal que corren en el
PC del hospital. El auditor sube el Excel consolidado en la sección
**Lotes** de la app; el agente reclama la tarea, corre el bot
(`responder_glosas_coosalud.py`) y reporta el estado factura por factura,
que la app muestra como semáforo en vivo.

```
[App /lotes]  ←­ polling HTTP →  [Agente de Lotes en el PC del hospital]
   cola de tareas                    corre el bot Playwright
   semáforo por factura              sube reporte + estados
```

## Uso normal: la ventana (doble clic) 🖥️

1. Abre la **carpeta del proyecto** (`motor-glosas-hus`) en el Explorador
   de Windows y entra a `tools`.
2. Doble clic en **`AgenteLotes.pyw`** → se abre la ventana del agente.
   - Si en vez de abrirse la ventana se abre un editor de texto: clic
     derecho → *Abrir con* → *Python* (elige `pythonw.exe`) y marca
     "usar siempre".
3. La primera vez, escribe:
   - **URL de la app**: `http://<servidor-app>:8000`
   - **Token del agente**: el mismo `AGENTE_LOTES_TOKEN` del `.env` del
     servidor (pídeselo al administrador).

   Se guardan solos (en `%APPDATA%\MotorGlosasHUS\agente_lotes.json`) —
   no hay que volver a escribirlos ni usar `setx`.
4. Presiona **▶ Iniciar agente** y déjalo abierto. Cada lote que se suba
   en la app se procesa automáticamente; el log de la ventana y el
   semáforo de la app muestran el avance.

**Acceso directo en el escritorio**: clic derecho sobre `AgenteLotes.pyw`
→ *Enviar a* → *Escritorio (crear acceso directo)*. Queda como cualquier
otra aplicación.

**Opciones de la ventana**: carpeta de trabajo (donde quedan Excel,
`reporte.csv`, `bot.log` y la carpeta `EVIDENCIA` de cada lote), índice de
soportes PDX (opcional), mostrar el navegador del bot (debug) y cierre de
residuales con RE9901.

## Requisitos

- El mismo PC donde ya corren los bots: Python instalado con
  `playwright` + `openpyxl`, y las credenciales `COOSALUD_USER` /
  `COOSALUD_PASSWORD` en el entorno (igual que siempre).
- La **carpeta del proyecto completa** copiada en el PC (el agente ejecuta
  `tools\responder_glosas_coosalud.py`, que debe estar al lado).
- En el **servidor de la app**: `AGENTE_LOTES_TOKEN` definido en el `.env`
  (cualquier cadena larga aleatoria). Sin esa variable, los endpoints del
  agente responden 503.

## Flujo de una tarea

1. `POST /agente/lotes/tareas/reclamar` — reclama la tarea pendiente más
   antigua (204 si no hay nada).
2. `GET /agente/lotes/tareas/<id>/excel` — descarga el Excel original.
3. Corre el bot con `--todas --reporte reporte.csv` (más
   `--incluir-calidad` si el lote se subió con esa opción).
4. Cada 30 s relee el `reporte.csv` (el bot escribe incremental) y hace
   `POST .../progreso` — el semáforo de la app avanza en vivo.
5. Al terminar, `POST .../completar`; la app calcula el estado final del
   lote (`COMPLETADO`, `COMPLETADO_CON_PENDIENTES` o `ERROR`).

## Uso avanzado: línea de comandos

El CLI sigue disponible (misma configuración guardada por la ventana, o
variables `MOTOR_GLOSAS_URL` / `AGENTE_LOTES_TOKEN`, o `--url`/`--token`):

```powershell
# IMPORTANTE: pararse primero en la carpeta del proyecto
cd C:\ruta\a\motor-glosas-hus

py tools\agente_lotes.py                 # loop infinito
py tools\agente_lotes.py --una-vez --con-cabeza   # prueba piloto
```

## Problemas comunes

- **`can't open file '...\tools\agente_lotes.py': No such file or
  directory`** → la terminal está parada en otra carpeta (p. ej.
  `C:\Users\cartera`). Haz `cd` a la carpeta del proyecto primero — o
  simplemente usa la ventana (`AgenteLotes.pyw`), que no depende de la
  carpeta actual.
- **La ventana dice "Sin conexión con la app"** → revisa la URL (¿el
  servidor está prendido y alcanzable desde este PC?) y que el token sea
  exactamente el del `.env` del servidor.
- **El lote queda en ERROR con "código 2"** → casi siempre faltan
  `playwright` o las credenciales del portal en este PC; abre
  `bot.log` dentro de la carpeta del lote para ver el motivo exacto.
