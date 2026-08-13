# Cargue de respuestas a SIIFA — paso a paso

Guía para el auditor. Es todo lo que hay que hacer, en orden, para empezar a
subir las respuestas a la plataforma del Ministerio. Contexto de la
plataforma en `docs/CONTEXTO_SIIFA.md`; el cargue **a mano** en el portal
está en la sección 5.ter de ese mismo documento.

**La forma fácil:** doble clic en `tools\CARGAR_SIIFA.cmd`. Ese bot hace todo
lo de abajo desde un menú, instala solo lo que falte y guarda el usuario y la
clave la primera vez. Los comandos sueltos quedan escritos aquí por si hay
que correr uno por separado o revisar qué hace cada paso.

---

## 0) Una sola vez, antes de empezar

```powershell
cd C:\temp-notas
git pull
py -m pip install httpx openpyxl
setx SIIFA_USER <usuario_del_portal>
setx SIIFA_PASSWORD <clave_del_portal>
```

Cerrar y volver a abrir PowerShell para que tome el usuario y la clave. La
clave nunca se escribe en un archivo del proyecto.

Si algo no conecta, antes de cualquier otra cosa:

```powershell
py tools\siifa_reporte_seguimientos.py --diagnostico
```

Dice en qué paso exacto falla: conexión, credenciales o consulta.

---

> **La carpeta de trabajo es una CARPETA**, algo como
> `D:\USUARIO CARTERA\Documents\SIIFA`. Enter usa esa misma por defecto. Si
> se escribe otra cosa, el bot lo dice de una y vuelve a preguntar — antes
> se daba cuenta al final, después de siete minutos bajando el informe. Con
> la opción [8] se puede cambiar sin cerrar el bot.

## 1) Bajar de SIIFA el informe de seguimientos

```powershell
py tools\siifa_reporte_seguimientos.py `
  --salida "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx"
```

Tarda varios minutos: son más de 2.500 registros. Es la lista de trabajo —
de aquí sale todo lo demás.

---

## 2) Armar los archivos de respuestas

```powershell
py tools\siifa_redactar_respuestas.py `
  --informe  "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx" `
  --tramites "D:\USUARIO CARTERA\Documents\TRAMITES_ENE_A_JUL_2026.xlsx" `
  --salida-glosas       "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_GLOSAS.xlsx" `
  --salida-devoluciones "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_DEVOLUCIONES.xlsx" `
  --solo-lo-ya-respondido
```

Salen **cuatro** archivos:

| Archivo | Qué trae | Qué se hace con él |
|---|---|---|
| `respuestas_GLOSAS.xlsx` | Las glosas que el hospital **ya respondió** en DGH | Se sube ya |
| `respuestas_DEVOLUCIONES.xlsx` | Las devoluciones que el hospital ya respondió en DGH | Se sube ya |
| `respuestas_GLOSAS_REDACTADAS.xlsx` | Las que redactó el motor | **NO se suben todavía**: revisar por tandas |
| `respuestas_DEVOLUCIONES_REDACTADAS.xlsx` | Ídem, devoluciones | **NO se suben todavía** |

Cada fila trae la columna **REVISAR** (qué verificar antes de subirla) y la
columna **FECHA_RESPUESTA**, que es la fecha en que el hospital respondió de
verdad — la misma que se digita a mano en el portal.

> **Por qué importa la fecha.** Si una respuesta que el HUS dio en mayo se
> sube con la fecha de hoy, en el histórico de SIIFA queda contestada meses
> después de la glosa, es decir **fuera del término** del artículo 57 de la
> Ley 1438 de 2011. Es lo primero que mira la EPS en la conciliación.

---

## 3) Piloto: UNA sola glosa (regla del hospital)

```powershell
py tools\responder_glosas_siifa.py `
  --excel   "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_GLOSAS.xlsx" `
  --piloto  1 `
  --reporte "D:\USUARIO CARTERA\Documents\SIIFA\piloto_siifa.csv"
```

**Y antes de seguir, verificar en el portal:**

1. Entrar a <https://siifa.sispro.gov.co/auth/login>.
2. **Seguimiento → Listar seguimientos**, filtrar por esa factura.
3. Tres puntos → **Ver Histórico**.
4. Confirmar que abajo aparece la **Respuesta** con su código y **con la
   fecha que traía DGH** (no la de hoy).
5. Pantallazo de esa pantalla: es la evidencia para el PDF de soportes.

Si algo salió distinto, **no seguir** con el cargue masivo.

---

## 4) Cargue de todas las glosas

```powershell
py tools\responder_glosas_siifa.py `
  --excel      "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_GLOSAS.xlsx" `
  --reporte    "D:\USUARIO CARTERA\Documents\SIIFA\reporte_GLOSAS.csv" `
  --saltar-csv "D:\USUARIO CARTERA\Documents\SIIFA\piloto_siifa.csv"
```

`--saltar-csv` evita repetir la del piloto. El reporte deja una línea por
glosa con OK o ERROR.

## 5) Cargue de todas las devoluciones

```powershell
py tools\responder_glosas_siifa.py `
  --excel   "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_DEVOLUCIONES.xlsx" `
  --reporte "D:\USUARIO CARTERA\Documents\SIIFA\reporte_DEVOLUCIONES.csv"
```

---

## 6) Si algo quedó con error

Se reintenta solo lo que falló, sin volver a subir lo que ya quedó bien:

```powershell
py tools\responder_glosas_siifa.py `
  --excel      "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_GLOSAS.xlsx" `
  --reporte    "D:\USUARIO CARTERA\Documents\SIIFA\reporte_GLOSAS_2.csv" `
  --saltar-csv "D:\USUARIO CARTERA\Documents\SIIFA\reporte_GLOSAS.csv"
```

Si el cargue se corta a la mitad (se cayó el internet, se cerró la ventana),
es exactamente lo mismo: se relanza con `--saltar-csv` apuntando al reporte
de la corrida anterior.

---

## 7) Comprobar que SÍ quedó subido (y sacar la evidencia)

Que el bot diga OK significa que la API contestó bien. Lo que vale en una
conciliación es lo que SIIFA tiene guardado, y con 1.082 respuestas no se
pueden tomar 1.082 pantallazos. Esto se lo pregunta a la plataforma:

```powershell
py tools\siifa_verificar_cargue.py `
  --excel        "D:\USUARIO CARTERA\Documents\SIIFA\respuestas_GLOSAS.xlsx" `
  --reporte      "D:\USUARIO CARTERA\Documents\SIIFA\reporte_GLOSAS.csv" `
  --salida       "D:\USUARIO CARTERA\Documents\SIIFA\verificacion_GLOSAS.xlsx" `
  --constancias  "D:\USUARIO CARTERA\Documents\SIIFA\EVIDENCIAS"
```

Salen dos cosas:

- **`verificacion_GLOSAS.xlsx`** — una fila por glosa, con la columna
  RESULTADO:

  | RESULTADO | Qué significa |
  |---|---|
  | `REGISTRADA` (verde) | Quedó en SIIFA con el mismo código y la misma fecha |
  | `REGISTRADA CON DIFERENCIAS` (amarillo) | Quedó, pero el código o **la fecha** no son los que se mandaron |
  | `NO APARECE RESPONDIDA` (rojo) | SIIFA la sigue mostrando sin respuesta: hay que volver a subirla |
  | `NO SE ENCONTRO EN SIIFA` (rojo) | La plataforma no devuelve esa glosa |

- **Una constancia en PDF por factura** en la carpeta `EVIDENCIAS`, con el
  membrete del hospital, la fecha y hora de la consulta, y por cada glosa su
  código, su valor, la respuesta registrada y su fecha. Eso es lo que se
  anexa a los soportes — reemplaza al pantallazo del portal y dice lo mismo,
  pero consultado a la API oficial del Ministerio.

En el bot de doble clic es la opción **[9]**.

## 8) Lo que queda pendiente después de esto

Las respuestas **redactadas por el motor** (los archivos `_REDACTADAS`) no
se han subido. Son las que no tenían antecedente en DGH. Hay que revisarlas
y subirlas por tandas, y **no se pueden dejar vencer**: la glosa que no se
contesta dentro del término se entiende aceptada.

Orden sugerido para revisarlas:

1. **Las de mayor valor**, siempre primero.
2. **Tarifas (`TA*`), facturación (`FA*`) y pertinencia (`CL*`)**: la
   respuesta se sostiene con el contrato y el manual tarifario, sin tener
   que buscar papeles.
3. **Soportes (`SO*`)**: exigen ubicar y anexar el soporte. Si el soporte no
   existe, esa glosa se acepta — la respuesta no se sostiene.
4. **Devoluciones `DE5601`** (radicación fuera de término): exigen confirmar
   el acuse de radicación antes de responder.

Para subir una tanda ya revisada, es el mismo comando del paso 4 apuntando
al archivo `_REDACTADAS` correspondiente (y con su propio reporte).
