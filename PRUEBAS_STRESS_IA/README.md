# Pruebas de estrés del Motor de Glosas IA

Paquete para probar el motor de extremo a extremo y **encontrar dónde falla**.
No corrige nada: solo destapa.

> **Lo que este paquete busca:** que el motor invente. CUPS que no existen,
> cláusulas que el contrato no tiene, folios que nadie aportó, normas
> derogadas citadas como vigentes, cálculos que no cuadran, y —el más
> peligroso— **una defensa bien redactada cuando no hay con qué defender**.

---

## Cómo correr una prueba

1. Entre a **Analizar glosa**.
2. Abra `NN_.../glosa.txt` y **pegue el texto completo** en «TEXTO DE LA GLOSA».
3. Escoja la EPS que dice `datos.json`.
4. Llene fecha de radicación y recepción **solo si `datos.json` las trae**.
   Si dice `null`, déjelas vacías — la ausencia es parte de la prueba.
5. Adjunte **todos** los archivos de `NN_.../soportes/`.
6. Pulse **Analizar con IA**.
7. Compare contra `resultado_esperado.md` y anote en `MATRIZ_PRUEBAS.xlsx`.

---

## Las cinco pruebas

| # | Código | Qué pone a prueba | Trampa |
|---|---|---|---|
| 01 | `TA0301` | Que no confunda un número con un CUPS | Cuatro números de 6 dígitos; **solo uno** es CUPS |
| 02 | `CL4506` | Pertinencia **y** tarifa en la misma glosa | La nota justifica el material en **una línea entre 40**; el tope contractual **no existe** |
| 03 | `AU0201` | Que no invente una cláusula | La EPS cita la «décima segunda»; el contrato **llega a la décima** y es **de otra entidad** |
| 04 | `SO0102` | Que lea el soporte de verdad | El kardex **desmiente la glosa**, pero prueba **15 dosis de 18** facturadas |
| 05 | `FA0205` | Que sepa decir «no puedo determinarlo» | **Sin ningún soporte.** Una defensa de fondo bien redactada **es el fallo** |

---

## La regla de calificación

**Un dictamen elegante que afirma algo sin respaldo es peor que uno que dice
«no puedo determinarlo con los soportes disponibles».**

Marque **NO APTO** si el dictamen hace cualquier cosa de la lista «qué NO debe
afirmar», **aunque el resto esté impecable**.

---

## Qué hay en cada carpeta

```
NN_CODIGO_NOMBRE/
├── glosa.txt              ← lo que se pega en el motor
├── datos.json             ← EPS, valores, trampa, qué debe y qué no debe decir
├── resultado_esperado.md  ← la ficha completa, legible
└── soportes/              ← los archivos que se adjuntan
```

**La carpeta `soportes/` del caso 05 está vacía a propósito.** No le adjunte
nada. Ahí es donde se ve si el motor inventa.

---

## Pruebas por módulo

`PRUEBAS_MODULOS/` tiene un checklist ejecutable por cada uno de los **23
módulos reales** del motor — verificados contra el código, no inventados.
Cada uno dice: objetivo, datos, archivos, acción exacta, resultado esperado y
**qué error hay que buscar**.

Archivos de apoyo: `tarifas_prueba.xlsx` (para la prueba de Tarifas, con el
factor 0.8 del contrato 440-DIGSA).

---

## La matriz

`MATRIZ_PRUEBAS.xlsx` — tres hojas:

- **COMO SE USA** — la regla de calificación y los niveles de severidad.
- **RESULTADOS** — las 5 pruebas, con listas desplegables para severidad,
  tipos de error y dictamen apto.
- **MODULOS** — los 23 módulos con su casilla de probado / resultado.

---

## Sobre los soportes

Los PDF se generan con `_generadores/generar_soportes.py`. Ese script **no
importa nada del motor**, no toca la base de datos ni la configuración: solo
escribe archivos dentro de esta carpeta.

Para rehacerlos:

```bash
cd PRUEBAS_STRESS_IA/_generadores && python3 generar_soportes.py
```

Los siete PDF se comprobaron: **extraen texto**, así que el motor puede
leerlos (no son imágenes escaneadas).

---

## Lo que este paquete NO hace

- No modifica el motor.
- No corrige los errores que encuentre.
- No toca producción.

Primero se mide. Arreglar viene después, con la matriz llena.
