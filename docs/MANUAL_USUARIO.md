# Manual de Usuario — HOSPIAI v1.0

**Para el equipo de Cuentas Médicas y Cartera · ESE HUS**

Este manual es para usar HOSPIAI en el día a día. No hay que saber programar.
Todo se escribe en la ventana azul de **PowerShell**, una línea a la vez.

> 🔒 **HOSPIAI solo LEE.** Nunca mueve, borra ni cambia archivos de los servidores.
> Únicamente genera reportes y paneles nuevos. Puede correrse sin miedo.

---

## 1. Antes de empezar (una sola vez al día)

Abrí PowerShell y entrá a la carpeta del proyecto:

```powershell
cd C:\Users\cartera\motor-glosas-hus
```

Traé la última versión (si hay):

```powershell
git pull
```

---

## 2. La corrida del día (un solo comando)

Esto arma el índice de soportes, revisa las facturas, genera los paneles y el
"buenos días". Dejalo correr; muestra el avance en pantalla.

```powershell
powershell -ExecutionPolicy Bypass -File tools\corrida_diaria.ps1
```

Al terminar quedan en tu **Escritorio**:
- `radicacion_fe.csv` y `radicacion_fe.xlsx` — el reporte factura por factura.
- `panel_hospiai.html` y `panel_ejecutivo.html` — los paneles (se abren con doble clic).

> Si vas a radicar de **otro mes**, abrí `tools\corrida_diaria.ps1` con el Bloc de
> notas y cambiá `202606` por el mes que toque (por ejemplo `202607` para julio).

---

## 3. El "buenos días" — qué hacer hoy

```powershell
py tools\hospiai.py iniciar-dia
```

Te muestra, en orden de plata:
- las acciones que más dinero liberan hoy,
- el **objetivo del día** en pesos,
- el riesgo principal y el cuello de botella,
- la carga de cada funcionario.

---

## 4. Las oportunidades de plata (lo más importante)

```powershell
py tools\hospiai.py oportunidades
```

Encuentra las **soluciones masivas**: cuántas facturas se destraban con una sola
acción y cuánto dinero liberan. Distingue dos casos:
- **"Asociar" (ya existe):** el soporte ya está escaneado en un servidor; basta
  volver a correr la corrida y el cruce lo anexa solo. Cuesta $0.
- **"Conseguir":** el soporte hay que escanearlo o pedirlo al área que lo genera.

> **No ejecuta nada por su cuenta.** Solo propone. La decisión siempre es humana.

---

## 5. Preguntarle al sistema (en español normal)

```powershell
py tools\hospiai.py preguntar "¿Dónde está detenido el dinero?"
py tools\hospiai.py preguntar "¿Qué EPS debo llamar primero?"
py tools\hospiai.py preguntar "¿Qué funcionario necesita apoyo?"
py tools\hospiai.py preguntar "¿Qué mejoró desde ayer?"
```

Si lo corrés sin pregunta, contesta una batería de ejemplo:

```powershell
py tools\hospiai.py preguntar
```

Cada respuesta trae **evidencia, indicadores, confianza y recomendaciones**.
Nunca da opiniones: todo sale de los datos.

---

## 6. Una factura en concreto

```powershell
py tools\hospiai.py plan HUS528043
```

Da el **plan de recuperación**: qué le falta, quién lo consigue, cuánto tarda, con
qué probabilidad queda LISTA y cuánto libera. Si el soporte ya existe en un
servidor, lo dice.

Otras consultas por factura:
```powershell
py tools\hospiai.py recomendar HUS528043     # acciones con su base y casos
py tools\hospiai.py evidencia  HUS528043     # por qué se bloqueó (norma incluida)
py tools\hospiai.py decision   HUS528043     # el dictamen auditable
```

---

## 7. Ver el estado general

```powershell
py tools\hospiai.py resumen                  # en pantalla
py tools\hospiai_comando.py situacion        # la "situación del día"
py tools\hospiai_comando.py hos              # el Hospital Operational Score
```

El **HOS** es la nota de salud de la operación (0 a 100): 92–100 Excelente,
80–91 Bueno, 60–79 Aceptable, menos de 60 Crítico. Aparece arriba del panel
ejecutivo.

---

## 8. "¿Qué pasaría si…?" (simulador)

```powershell
py tools\hospiai.py simular
py tools\hospiai.py simular --codigo HEV
```

Calcula cuántas facturas y cuánta plata se liberan si se corrige un soporte en
todo el lote. Los cálculos exactos van marcados "EXACTO por reglas"; las
estimaciones van marcadas como tales.

---

## 9. Cierre de la semana (los viernes)

```powershell
py tools\hospiai_operacion.py mejora
```

Responde: qué mejoró, qué empeoró, qué aprendimos y qué cambiar el lunes.
(La corrida diaria ya lo hace sola los viernes.)

---

## 10. Dejar el panel actualizado solo cada mañana

Una sola vez, para programar la corrida a las 6:00 a. m.:

```
schtasks /Create /TN "HOSPIAI corrida diaria" /SC DAILY /ST 06:00 ^
  /TR "powershell -ExecutionPolicy Bypass -File C:\Users\cartera\motor-glosas-hus\tools\corrida_diaria.ps1"
```

Así el panel amanece actualizado sin que nadie lo corra.

---

## Si algo sale mal

- **"not a git repository"** → no estás en la carpeta. Corré `cd C:\Users\cartera\motor-glosas-hus`.
- **"can't open file ... hospiai.py"** → lo mismo: carpeta equivocada, o falta `git pull`.
- **La pantalla muestra `:` y no responde** → es el visor de git; apretá la tecla `q`.
- **Una unidad `Y:\` / `Z:\` / `X:\` "no existe"** → el servidor no está conectado; hay que mapearlo (ver `docs/CONECTAR_SERVIDOR_PASO_A_PASO.md`).
- **Cualquier duda** → los archivos `BITACORA.md` (qué se hizo) y `docs/MANUAL_TECNICO.md` (cómo funciona) son la memoria del proyecto.
