# 4 ejemplos de glosas difíciles + dictamen ESPERADO

Referencia de calidad para validar la salida del motor tras la **Ronda 21**
(auditoría del caso MEDIMÁS da Vinci). Para cada ejemplo se da:

1. **GLOSA** (la objeción de la EPS, tal como entra al motor).
2. **DATOS** del caso (EPS, valor, contrato, CUPS).
3. **DICTAMEN ESPERADO** — lo que un auditor experto + el motor corregido
   deberían producir.
4. **CHECKLIST** — qué DEBE aparecer y qué NO debe aparecer (criterios
   objetivos para comparar contra la salida real).

> Cómo usar: pega la GLOSA en "Analizar glosa", compara el dictamen real
> contra el ESPERADO y el checklist. Si un criterio del checklist falla,
> es un bug a reportar.

---

## Ejemplo 1 — MEDIMÁS da Vinci (prostatectomía robótica) · $273.180.000

**EPS:** MEDIMÁS EPS-S (en liquidación) · **Contrato:** CTR-2024-MEDIMAS-HUS
· **CUPS:** 60.1.2.01

### GLOSA
> OBSERVACIONES MEDIMÁS EPS-S (LIQUIDACIÓN): (I) PERTINENCIA: la
> prostatectomía radical ABIERTA es alternativa válida con resultados
> oncológicos equivalentes según la GPC Cáncer de Próstata MinSalud 2023;
> el uso de plataforma robótica da Vinci Xi NO se justifica y representa un
> sobrecosto del 340%. (II) EVENTO ADVERSO PREVENIBLE: la fístula urinaria
> post-operatoria es complicación EVITABLE atribuible a falla en la técnica
> quirúrgica; conforme al Decreto 4747/2007 Art. 20 + Res. 0112/2012, el
> costo lo asume el prestador. (III) TARIFA: el contrato vigente
> CTR-2024-MEDIMAS-HUS define para CUPS 60.1.2.01 una tarifa de SOAT × 0.85;
> la facturación aplicó SOAT pleno + adicional 35% por plataforma robótica,
> modificación unilateral. (IV) SOPORTES: no se aporta el consentimiento
> informado específico para plataforma robótica ni la cotización
> comparativa requerida por la cláusula 31 del contrato. (V) Dado el
> proceso de liquidación, el reconocimiento queda condicionado a la
> verificación de saldos por la agente liquidadora.

### DICTAMEN ESPERADO
**ESE HUS NO ACEPTA LA GLOSA — CÓDIGO RESPUESTA RE9901.**

La ESE Hospital Universitario de Santander no acepta la glosa formulada por
MEDIMÁS EPS-S sobre la prostatectomía radical asistida por plataforma
robótica da Vinci Xi (CUPS 60.1.2.01), facturada **en el marco del contrato
CTR-2024-MEDIMAS-HUS**, por las siguientes razones, una por cada concepto
objetado:

**(I) Pertinencia clínica.** La elección de la vía robótica corresponde al
médico tratante en ejercicio de su autonomía profesional (Art. 17 Ley
1751/2015; T-478/1995). Frente a la GPC de Cáncer de Próstata MinSalud 2023
invocada por la EPS, se precisa que **las Guías de Práctica Clínica son
recomendativas, no imperativas, y admiten excepción según la condición
concreta del paciente (Sentencia T-121/2015)**; no constituyen norma de
exclusión de cobertura. La EPS reconoce equivalencia oncológica; la
indicación de la plataforma robótica se sustenta en **outcomes funcionales
y de seguridad de nivel de evidencia 1A** (menor sangrado intraoperatorio,
menor estancia, recuperación funcional de continencia y potencia — revisión
sistemática Cochrane / guías EAU), documentados en la historia clínica.

**(II) Evento adverso.** Se rechaza la calificación unilateral de la
fístula urinaria como "evento adverso prevenible": es una complicación
**conocida e inherente** a la prostatectomía radical, independiente de la
vía quirúrgica, no atribuible per se a falla en la técnica. El **Decreto
4747/2007 Art. 20** invocado por la EPS exige precisamente **auditoría
médica conjunta** para calificar un evento adverso — no la imposición
unilateral del pagador; y la **Res. 0112/2012** (Seguridad del Paciente)
establece un enfoque sistémico, no punitivo. La carga de probar la
prevenibilidad y el nexo causal recae en quien la alega (Art. 57 Ley
1438/2011), carga no satisfecha en la objeción.

**(III) Tarifa.** Existiendo el contrato CTR-2024-MEDIMAS-HUS, **rige el
factor pactado y no procede afirmar que se aplique SOAT pleno por ausencia
de contrato**. La defensa se concentra en el adicional objetado: el
componente por plataforma robótica está soportado clínicamente como
prestación necesaria y debe reconocerse dentro del marco del contrato y su
anexo tarifario. Ninguna parte puede modificar unilateralmente lo pactado
(Pacta Sunt Servanda — Art. 1602 C.C. y Art. 871 C.Co.).

**(IV) Soportes — cláusula 31.** Respecto del **consentimiento informado**,
el expediente contiene el consentimiento institucional con el valor
probatorio de la Res. 1995/1999; el procedimiento robótico se ejecutó bajo
dicho consentimiento. Respecto de la **cotización comparativa exigida por la
cláusula 31 del contrato**, la plataforma da Vinci es de **proveedor
exclusivo**, lo que hace inaplicable la comparación de tres proveedores;
se aporta la justificación de exclusividad correspondiente.

**(V) Liquidación.** El proceso de liquidación de MEDIMÁS EPS-S **no
extingue el crédito por los servicios efectivamente prestados**. Las
acreencias por servicios de salud tienen **prelación** en el proceso
liquidatorio; la agente liquidadora designada por la SuperSalud debe
reconocer la obligación conforme a dicha prelación, procediendo el giro
directo de ADRES cuando aplique (Auto 116/2024 Corte Constitucional).

Por lo expuesto, se solicita el levantamiento total de la glosa y el pago
íntegro del valor facturado.

**Fundamento normativo:** Art. 17 Ley 1751/2015 · Sentencia T-121/2015 ·
Decreto 4747/2007 Art. 20 · Res. 0112/2012 · Res. 1995/1999 · Art. 57 Ley
1438/2011 · Auto 116/2024.

### CHECKLIST
- ✅ **NO** dice "sin contrato pactado" / "no existir contrato pactado" en NINGÚN lugar del cuerpo.
- ✅ Reconoce el contrato CTR-2024-MEDIMAS-HUS y defiende DENTRO de él (no afirma "SOAT pleno por ausencia de contrato").
- ✅ Responde los **5 conceptos** (I–V), cada uno por su tema.
- ✅ Menciona la **cláusula 31** por su número y la responde (proveedor exclusivo).
- ✅ Rebate **por nombre** el Decreto 4747/2007 Art. 20 y la Res. 0112/2012.
- ✅ Defensa de da Vinci con **evidencia 1A** (no solo "autonomía médica").
- ✅ Defensa de liquidación anclada (prelación / Auto 116/2024), no relleno.
- ✅ Cierra sin coda procesal pegada ("...de la glosa." y punto).
- ❌ No inventa CUPS, valores ni EPS distintas a MEDIMÁS.

---

## Ejemplo 2 — ECOOPSOS implante coclear bilateral pediátrico · $389.700.000

**EPS:** ECOOPSOS · **Contrato:** CTR-2025-ECOOPSOS-HUS · paciente 14 meses

### GLOSA
> OBSERVACIONES ECOOPSOS: La paciente cuenta con 14 meses de edad. (I) el
> implante coclear bilateral es PREMATURO; (II) se objeta la BILATERALIDAD
> por costo del segundo dispositivo Med-El; (III) el procesador SONNET 2 es
> de gama PREMIUM no justificada. La cláusula 24 del Contrato
> CTR-2025-ECOOPSOS-HUS exige cotización comparativa de al menos 3
> proveedores, NO aportada.

### DICTAMEN ESPERADO
**ESE HUS NO ACEPTA LA GLOSA — CÓDIGO RESPUESTA RE9901.**

La ESE HUS no acepta la glosa de ECOOPSOS sobre el implante coclear
bilateral, facturado en el marco del contrato CTR-2025-ECOOPSOS-HUS:

**(I) Oportunidad (no "prematuro").** La implantación coclear en menores
está indicada **desde los 12 meses** (e incluso antes en hipoacusia
profunda bilateral), siendo la intervención temprana determinante para el
desarrollo del lenguaje por la plasticidad de la vía auditiva
(recomendaciones FDA y guías NICE / Joint Committee on Infant Hearing). A
los 14 meses la indicación es **oportuna**, no prematura; el retraso
comprometería el resultado (ventana crítica auditiva).

**(II) Bilateralidad.** La implantación **bilateral** es el estándar de
cuidado en hipoacusia profunda bilateral pediátrica: aporta localización
sonora, audición en ambientes ruidosos y desarrollo simétrico de la
corteza auditiva (evidencia nivel 1A). No es un costo redundante sino una
indicación clínica diferenciada del oído contralateral.

**(III) Gama del procesador.** El procesador corresponde a la indicación
del especialista tratante conforme a la compatibilidad del sistema Med-El;
la auditoría administrativa no sustituye el criterio clínico (Art. 17 Ley
1751/2015).

**Cláusula 24 — cotización comparativa.** Respecto de la **cláusula 24 del
contrato CTR-2025-ECOOPSOS-HUS**, el sistema Med-El (procesador SONNET 2) es
de **distribuidor único** en el país, lo que hace materialmente inaplicable
la cotización de tres proveedores; se aporta la certificación de
exclusividad del distribuidor, que satisface el supuesto de excepción de la
propia cláusula.

Se solicita el levantamiento total de la glosa y el pago íntegro.

**Fundamento normativo:** Art. 17 Ley 1751/2015 · Res. 1995/1999 · Ley
1751/2015 Art. 8 (continuidad) · cláusula 24 del contrato.

### CHECKLIST
- ✅ Responde los 3 conceptos + la cláusula 24 por su número (proveedor único).
- ✅ Defiende con evidencia clínica (no solo "autonomía médica").
- ✅ **NO** invoca "atención inicial de urgencias" (es cirugía electiva).
- ✅ Reconoce el contrato; no lo niega.
- ✅ EPS = ECOOPSOS en todo el dictamen (no inventa otra).

---

## Ejemplo 3 — Hemofilia A con inhibidores + SANCIÓN ilegal · $156.000.000

**EPS:** NUEVA EPS · **Concepto:** ME (medicamentos) — factor VII recombinante

### GLOSA
> NUEVA EPS objeta: (1) el uso de factor VII activado recombinante
> (eptacog alfa) NO está justificado, debe usarse factor VIII estándar; (2)
> el esquema de dosis excede lo recomendado. SE APLICA SANCIÓN DEL 10% AL
> VALOR FACTURADO por facturación improcedente.

### DICTAMEN ESPERADO
**ESE HUS NO ACEPTA LA GLOSA — CÓDIGO RESPUESTA RE9901.**

La ESE HUS no acepta la glosa de NUEVA EPS sobre el factor VII activado
recombinante:

**(1) Pertinencia del agente de baña (bypassing).** En hemofilia A **con
inhibidores**, el factor VIII estándar es **inefectivo** porque el inhibidor
lo neutraliza; el estándar de manejo son los **agentes de baña** (factor VII
activado recombinante o CCPa), conforme a las guías de la World Federation
of Hemophilia (WFH) y la evidencia clínica nivel 1A. La sustitución
propuesta por la EPS es clínicamente inviable y pondría en riesgo vital al
paciente.

**(2) Dosis.** El esquema corresponde al peso del paciente y a la severidad
del episodio hemorrágico, conforme al protocolo institucional y a la
indicación del hematólogo tratante (Art. 17 Ley 1751/2015), documentado en
la historia clínica.

**Sobre la sanción del 10%.** Se **rechaza de plano** la pretensión de
imponer una sanción del 10% sobre el valor facturado. **Las EPS carecen de
facultad sancionatoria** sobre los prestadores: la potestad sancionatoria en
el sistema de salud es exclusiva de la Superintendencia Nacional de Salud
(Art. 126 y concordantes de la Ley 1438/2011). Una glosa es una objeción
técnica sujeta a respuesta y conciliación (Arts. 56–57 Ley 1438/2011), no un
título habilitante para sanciones unilaterales. La imposición adolece de
**vicio de competencia** y es inoponible al HUS.

Se solicita el levantamiento total de la glosa y el pago íntegro, así como
el retiro de la sanción por carecer de fundamento legal.

**Fundamento normativo:** Art. 17 Ley 1751/2015 · Art. 126 Ley 1438/2011 ·
Arts. 56–57 Ley 1438/2011 · Res. 1995/1999.

### CHECKLIST
- ✅ **Rechaza la sanción** del 10% por vicio de competencia (Ley 1438 Art. 126).
- ✅ **NO** acepta ni se "ajusta" a la sanción.
- ✅ Defiende el factor VII con evidencia (hemofilia con inhibidores → bypassing).
- ✅ EPS = NUEVA EPS; no inventa otra.
- ✅ Responde los 2 conceptos clínicos + la sanción.

---

## Ejemplo 4 — SALUD TOTAL TMS salud mental refractaria (multi-concepto) · $98.000.000

**EPS:** SALUD TOTAL (dropdown llegó como "OTRA / SIN DEFINIR") · **Contrato:**
CTR-2024-SALUDTOTAL-HUS

### GLOSA
> SALUD TOTAL: Se objeta integralmente la atención: (1) la terapia de
> Estimulación Magnética Transcraneal (TMS) NO está en el PBS conforme a la
> Resolución 2292 de 2021; (2) la hospitalización psiquiátrica de 22 días
> excede los lineamientos de pertinencia (máximo 14 días); (3) la atención
> NO fue tramitada vía autorización previa (AU0301). SE APLICA SANCIÓN DEL
> 10% AL VALOR FACTURADO, conforme a la cláusula 18 del contrato
> CTR-2024-SALUDTOTAL-HUS. Adicionalmente, se objeta el acompañamiento
> familiar protocolizado por no estar en el PBS.

### DICTAMEN ESPERADO
**ESE HUS NO ACEPTA LA GLOSA — CÓDIGO RESPUESTA RE9901.**

La ESE HUS no acepta la glosa de **SALUD TOTAL**, formulada en el marco del
contrato CTR-2024-SALUDTOTAL-HUS. Se responde **cada concepto** objetado:

**(1) TMS y PBS.** La Estimulación Magnética Transcraneal está indicada en
**depresión / trastorno mental refractario** que no respondió a manejo
farmacológico, con respaldo de evidencia nivel 1A (aprobación FDA, guías
NICE). Lo NO incluido expresamente en el PBS **no equivale a exclusión**:
solo está excluido lo taxativamente listado (Art. 15 Ley 1751/2015); ante
una condición que amenaza la vida o la funcionalidad, la cobertura procede
y, de requerirse, por la vía de tecnologías no financiadas con cargo a la
UPC (MIPRES), sin que ello habilite el no pago del servicio prestado.

**(2) Estancia de 22 días.** La duración de la hospitalización psiquiátrica
corresponde a la **gravedad y evolución clínica** del paciente (riesgo,
respuesta al tratamiento), decisión del psiquiatra tratante documentada en
la historia clínica; el "máximo de 14 días" es un promedio administrativo,
no un límite de cobertura (Art. 17 Ley 1751/2015).

**(3) Autorización previa.** La atención de salud mental con riesgo
corresponde a una situación que no admite dilación; **la falta de
autorización previa no es causal de no pago** cuando el servicio fue
efectivamente prestado y es pertinente (Art. 8 Ley 1751/2015 — continuidad;
prohibición de trasladar al usuario/prestador las fallas administrativas).

**(4) Sanción del 10%.** Se **rechaza** la sanción del 10%: las EPS carecen
de facultad sancionatoria (Art. 126 Ley 1438/2011); la cláusula 18 del
contrato no puede pactar una potestad que la ley reserva a la SuperSalud
(vicio de competencia). La glosa es objeción técnica, no título
sancionatorio.

**(5) Acompañamiento familiar.** El acompañamiento protocolizado en el
paciente psiquiátrico es parte del **manejo integral** y de la seguridad del
paciente, no un servicio accesorio excluible; su pertinencia está
documentada.

Se solicita el levantamiento total de la glosa y el pago íntegro, y el
retiro de la sanción.

**Fundamento normativo:** Art. 15 Ley 1751/2015 · Art. 17 Ley 1751/2015 ·
Art. 8 Ley 1751/2015 · Art. 126 Ley 1438/2011 · Res. 1995/1999.

### CHECKLIST
- ✅ Detecta y usa **SALUD TOTAL** (corrige el dropdown "OTRA / SIN DEFINIR").
- ✅ Responde los **5 sub-conceptos** (TMS, estancia, autorización, sanción, acompañamiento).
- ✅ **Rechaza la sanción** del 10% (cláusula no puede pactar lo que la ley reserva a SuperSalud).
- ✅ Responde la cláusula 18 por su número.
- ✅ Defiende TMS con evidencia (FDA/NICE), no solo autonomía.
- ✅ Reconoce el contrato; no lo niega.
- ✅ Banner si quedara algún concepto sin responder.

---

## Resumen de criterios transversales (los 4 ejemplos)

| Criterio | Regla |
|---|---|
| Contrato citado | NUNCA negarlo; defender dentro de él |
| Conceptos | Responder TODOS, uno por uno |
| Cláusula citada | Responder por su número |
| Norma de la EPS | Rebatir por nombre (silencio = concesión) |
| Sanción EPS | Rechazar por vicio de competencia (Ley 1438 Art. 126) |
| Tecnología cara | Evidencia 1A (FDA/NICE/Cochrane/WFH), no "autonomía" a secas |
| Liquidación | Prelación de acreencias + Auto 116/2024, no relleno |
| EPS | La efectiva del texto (no el dropdown si contradice) |
| Cierre | Sin coda procesal pegada; sin placeholders; sin CUPS/valores inventados |
