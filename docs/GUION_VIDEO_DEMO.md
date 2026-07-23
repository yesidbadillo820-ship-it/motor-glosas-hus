# Guión del Video de Demostración — HOSPIAI v1.0

**Duración objetivo:** 5–10 minutos · **Público:** gerencia y equipo de Cuentas Médicas
**Formato:** grabación de pantalla (PowerShell + paneles HTML) con voz en off.

> No hace falta editar nada elaborado. Es una demo honesta: se muestran los
> comandos corriendo sobre los **datos reales** del lote y se leen las cifras que
> ya salieron en la corrida del 23-jul (ver `docs/ACTA_LINEA_BASE.md`).

**Antes de grabar:** tener hecha la corrida del día (`corrida_diaria.ps1`), con
`panel_ejecutivo.html` en el Escritorio y PowerShell abierto en
`C:\Users\cartera\motor-glosas-hus`.

---

## Escena 1 — El problema (0:00–1:00)
**En cámara:** una carpeta del servidor con miles de PDFs.
**Voz:** "El hospital radica más de 12.000 facturas al mes. Cada una necesita sus
soportes completos, o la EPS la devuelve. Hasta ahora eso se revisaba a mano,
factura por factura. HOSPIAI lo hace en minutos y, además, dice qué hacer."

## Escena 2 — Una corrida real (1:00–2:00)
**En pantalla:** correr
```powershell
powershell -ExecutionPolicy Bypass -File tools\corrida_diaria.ps1
```
Mostrar el avance del índice y el radicador.
**Voz:** "Con un comando, HOSPIAI recorre los tres servidores, cruza los soportes
y audita las 12.523 facturas. Todo en modo solo lectura: no toca ni un archivo."

## Escena 3 — El panel que abre con decisiones (2:00–3:30)
**En pantalla:** abrir `panel_ejecutivo.html`. Detenerse en la banda "SITUACIÓN
DEL DÍA" y el **Hospital Operational Score**.
**Voz:** "El panel no arranca con gráficos: arranca con decisiones. Arriba, la
nota de salud de la operación. Debajo: cuánto se puede recuperar hoy, la prioridad
máxima, el riesgo y el cuello de botella. Un gerente entiende en menos de un
minuto dónde actuar."
**Leer las cifras reales:** 7.840 facturas listas (62,6 %), $38.646 millones
listos para radicar.

## Escena 4 — El "buenos días" (3:30–4:30)
**En pantalla:**
```powershell
py tools\hospiai.py iniciar-dia
```
**Voz:** "Cada mañana el sistema llega con las acciones del día, ordenadas por el
dinero que liberan, y fija el objetivo del día en pesos. No espera preguntas."

## Escena 5 — La palanca del mes (4:30–6:00)
**En pantalla:**
```powershell
py tools\hospiai.py oportunidades
```
**Voz:** "Aquí está el hallazgo grande: 3.275 facturas están a un solo soporte —la
hoja de evidencia— de quedar listas. Son $1.256 millones. Resolver solo eso sube
las facturas listas del 63 % al 89 %. Y el sistema distingue cuáles ya están
escaneadas —basta asociarlas— de cuáles hay que conseguir. No ejecuta nada: propone."

## Escena 6 — El copiloto responde (6:00–7:30)
**En pantalla:**
```powershell
py tools\hospiai.py preguntar "¿Dónde está detenido el dinero?"
py tools\hospiai.py preguntar "¿Qué EPS debo llamar primero?"
```
**Voz:** "Se le pregunta en español normal. Y cada respuesta trae evidencia,
indicadores y confianza. Nunca opiniones: todo sale de los datos, las reglas y la
memoria del hospital."

## Escena 7 — Trazabilidad (7:30–8:30)
**En pantalla:**
```powershell
py tools\hospiai.py evidencia HUS528043
```
**Voz:** "Cada dictamen se puede defender ante una auditoría: la factura, el
soporte que falta, la regla que lo exige y la norma que la respalda. Todo queda
registrado y versionado."

## Escena 8 — Cierre (8:30–9:30)
**En cámara / diapositiva:** las cifras de la línea base.
**Voz:** "Esta es la versión 1.0, funcionando con datos reales. El punto de
partida quedó medido: 62,6 % de facturas listas. El objetivo de las próximas
semanas es llevarlo por encima del 88 %, sin más personal, usando lo que el
sistema ya señala. HOSPIAI dejó de ser una idea: es la operación diaria del área."

---

## Cifras para tener a la mano (de la corrida real del 23-jul)
- 12.523 facturas · $49.293 millones auditados.
- 7.840 listas (62,6 %) · $38.646 millones listos.
- Palanca HEV: 3.275 facturas · $1.256 millones → llevaría a 88,8 % listas.
- Quick-win: 29 facturas ($551 millones) solo esperan que se agregue la entidad al catálogo.
- El cruce anexó soportes solo a 10.823 facturas.

*(No mostrar en el video datos de pacientes ni números de factura en primer plano:
la demo se apoya en cifras agregadas.)*
