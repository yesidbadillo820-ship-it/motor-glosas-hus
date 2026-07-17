# Agente local de lotes

Servicio que conecta la app (Motor Glosas) con los bots de portal que corren
en el PC del hospital. El auditor sube el Excel consolidado en la sección
**Lotes** de la app; este agente reclama la tarea, corre el bot
(`responder_glosas_coosalud.py`) y reporta el estado factura por factura,
que la app muestra como semáforo en vivo.

```
[App /lotes]  ←­ polling HTTP →  [agente_lotes.py en el PC del hospital]
   cola de tareas                    corre el bot Playwright
   semáforo por factura              sube reporte + estados
```

## Requisitos

- El mismo PC donde ya corren los bots (Python, playwright, openpyxl,
  credenciales `COOSALUD_USER`/`COOSALUD_PASSWORD` en el entorno).
- En el **servidor de la app**: definir `AGENTE_LOTES_TOKEN` en el `.env`
  (cualquier cadena larga aleatoria). Sin esa variable los endpoints del
  agente responden 503.

## Configuración (PowerShell, una sola vez)

```powershell
setx MOTOR_GLOSAS_URL "http://<servidor-app>:8000"
setx AGENTE_LOTES_TOKEN "<el mismo token del .env del servidor>"
# cerrar y reabrir la terminal
```

## Uso

```powershell
# Loop infinito (dejarlo corriendo; procesa cada lote que se suba)
py tools\agente_lotes.py

# Procesar una sola tarea y salir (prueba piloto)
py tools\agente_lotes.py --una-vez --con-cabeza

# Con índice de soportes PDX y cierre de residuales
py tools\agente_lotes.py --indice indice_soportes.txt --cerrar-residuales
```

Todo lo de cada corrida queda en `lotes_agente\lote_<id>\`: el Excel
descargado, `reporte.csv`, `bot.log` y la carpeta `EVIDENCIA` con los
pantallazos de cierre.

## Flujo de una tarea

1. `POST /agente/lotes/tareas/reclamar` — reclama la tarea pendiente más
   antigua (204 si no hay nada).
2. `GET /agente/lotes/tareas/<id>/excel` — descarga el Excel original.
3. Corre el bot con `--todas --reporte reporte.csv` (más `--incluir-calidad`
   si el lote se subió con esa opción).
4. Cada 30 s relee el `reporte.csv` (el bot escribe incremental) y hace
   `POST .../progreso` — el semáforo de la app avanza en vivo.
5. Al terminar, `POST .../completar` con todas las filas; la app calcula el
   estado final del lote (`COMPLETADO`, `COMPLETADO_CON_PENDIENTES` o
   `ERROR`).
