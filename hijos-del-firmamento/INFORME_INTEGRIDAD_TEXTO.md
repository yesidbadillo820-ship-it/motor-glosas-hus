# Informe de integridad del texto

### «Hijos del Firmamento» · Libro Primero — auditoría del archivo de origen

> **Resumen.** El `.docx` de origen llega dañado por el proceso que lo generó (un volcado desde un original ya maquetado), no por la escritura del autor. El daño **mecánico** (párrafos partidos, guiones de corte, espacios perdidos) se reparó de forma **automática, trazable y sin cambiar ni una letra**. Sólo quedan **27 palabras con las letras barajadas** que no se pueden restaurar sin inventar texto: se catalogan aquí y se señalan en violeta en el PDF de revisión.

---

## 1. Reparaciones automáticas aplicadas (sin alterar el texto)

| Reparación | Qué hace | Casos |
|---|---|---:|
| Reunión de párrafos | Une los renglones partidos en el párrafo real, por flujo de puntuación | ~200 |
| De-partición de palabra | «des-‸pués» → «después»; «Algu-»+«nas» → «Algunas» | 66 |
| Renglones en blanco espurios | Elimina blancos dentro de una frase | 28 |
| **Restauración de espacios** | Repone los espacios perdidos (ver §2), sin cambiar letras | 29 tokens |
| Cursivas del autor | Preservadas | 521 |

Se verificó que **no existe ningún guion (-) legítimo** en la novela: los 66 eran cortes de línea; las 879 rayas de diálogo (—) se respetaron intactas.

## 2. Espacios restaurados (puro re-espaciado, verificado)

Para cada palabra, quitar los espacios reproduce **exactamente** el token dañado: no se cambió, añadió ni quitó ninguna letra. Es la misma clase de reparación que los guiones y los párrafos.

| Venía como | Se restauró como |
|---|---|
| `Caminarapidísimo` | Camina rapidísimo |
| `conelsombreroenlasmanos` | con el sombrero en las manos |
| `DonTuliosequedópensando` | Don Tulio se quedó pensando |
| `elarchivo` | el archivo |
| `esoque` | eso que |
| `Ledijeolvídaloamiesposaparanotenerque` | Le dije olvídalo a mi esposa para no tener que |
| `loscuadernos` | los cuadernos |
| `mirepues` | mire pues |
| `quélindo` | qué lindo |
| `Teestoycontando` | Te estoy contando |
| `Teníarazón` | Tenía razón |
| `Todoslosjueves` | Todos los jueves |
| `Vacíauna` | Vacía una |
| `Veinteminutos` | Veinte minutos |
| `Volveríaahacerlo` | Volvería a hacerlo |
| `Yaloleí` | Ya lo leí |
| `Yodije` | Yo dije |
| `Yolamiré` | Yo la miré |
| `Yolepuse` | Yo le puse |
| `Yomecallé` | Yo me callé |
| `Yomedetuve` | Yo me detuve |
| `Yomereí` | Yo me reí |
| `Yosabíaperfectamenteloqueganaba` | Yo sabía perfectamente lo que ganaba |
| `Yosalté` | Yo salté |
| `Yosonreí` | Yo sonreí |
| `Yotampoco` | Yo tampoco |
| `Yoteníarazón` | Yo tenía razón |
| `Yotuvequeapurarelpaso` | Yo tuve que apurar el paso |
| `yyosoymásalto` | y yo soy más alto |

## 3. Pendiente: letras barajadas (necesito tu confirmación)

Estas palabras tienen las **letras desordenadas** (los *runs* del documento se barajaron). No las toco porque restaurarlas sería adivinar tu texto. Dime qué decía cada una — con el contexto suele bastar. En el PDF de revisión están en **violeta con un °**.

| # | ¶ | En el texto (contexto) | Palabra | ¿Decía…? |
|---:|---:|:--|:--|:--|
| 1 | 262 | …—tenEesro «reaszótrna».mpa —dijo.… | `reaszótrna` | — *(dímelo tú)* |
| 2 | 262 | …—«tenEesro» reaszótrna.mpa —dijo.… | `tenEesro` | — *(dímelo tú)* |
| 3 | 304 | …—«pSiagruaee»—so.dijo—. ¿Qué pasó?… | `pSiagruaee` | — *(dímelo tú)* |
| 4 | 330 | …—«deHscaoynmocuicdhoa».s maneras de traducirlo —le dije—…… | `deHscaoynmocuicdhoa` | — *(dímelo tú)* |
| 5 | 364 | …De«bídecirle»: acabas de hacer una cosa enormDe…… | `bídecirle` | — *(dímelo tú)* |
| 6 | 364 | ……decirle: acabas de hacer una cosa «enormDee».bídecirle:esoque hiciste tiene no…… | `enormDee` | enorme |
| 7 | 476 | ……rible el mejor guerrero del mundo «rersatacabdaoe».mbe-… | `rersatacabdaoe` | — *(dímelo tú)* |
| 8 | 498 | ……logo, todo lo que un hombre podía «YquAeqrueirl».es les dijo que no.… | `YquAeqrueirl` | — *(dímelo tú)* |
| 9 | 886 | ……en que yo he oído las cosas en mi «vidDaa». nia estaba en el corredor con un…… | `vidDaa` | — *(dímelo tú)* |
| 10 | 948 | …«ELos» mesecnritbiríad. e buena fe. Así …… | `ELos` | — *(dímelo tú)* |
| 11 | 948 | …ELos «mesecnritbiríad». e buena fe. Así lo tenía archiva…… | `mesecnritbiríad` | — *(dímelo tú)* |
| 12 | 1035 | ……No dijo nada, no me miró, no hizo «comnienngtúanrio», no dijo qué lindo ni dijo por fi…… | `comnienngtúanrio` | — *(dímelo tú)* |
| 13 | 1062 | …me gustaba mós «despuós» de pegado. No a pesar del pegante…… | `despuós` | después |
| 14 | 1164 | …… tener toda la razón del mundo. Y «quNeollalosréd».os cosas son ciertas al tiempo.… | `quNeollalosréd` | — *(dímelo tú)* |
| 15 | 1344 | ……e no tiene nada, un rato largo. Y «vAollavsíad».os de la mañana. Cuatro horas des…… | `vAollavsíad` | — *(dímelo tú)* |
| 16 | 1369 | …—«QYuméi». hija, que tenía siete años, que …… | `QYuméi` | — *(dímelo tú)* |
| 17 | 1391 | ……pia, la comida salía a tiempo, la «nYioñallesgaalíbaapaeilnaas» dsaie.te y ella decía ¿comiste?, …… | `nYioñallesgaalíbaapaeilnaas` | — *(dímelo tú)* |
| 18 | 1538 | ……cía, y la puerta del patio estaba «abiEesrttaab». a afuera.… | `abiEesrttaab` | abierta |
| 19 | 1555 | ……y me había dicho te oí, y no dijo «nadYayomnáos».aguanté.… | `nadYayomnáos` | — *(dímelo tú)* |
| 20 | 1582 | ……lícula vimos el martes en que nos «enaTmenogroamtroesin». ta y una cajas.… | `enaTmenogroamtroesin` | — *(dímelo tú)* |
| 21 | 1980 | ……rrigiendo a la profesora, que era «disYtindteos».pués dijo la frase por la que est…… | `disYtindteos` | — *(dímelo tú)* |
| 22 | 1987 | …—pe¿«nLsoióqnu»:e dijo la niña era falso o era ve…… | `nLsoióqnu` | — *(dímelo tú)* |
| 23 | 2206 | ……un metro de ella, rotulando otras «cosLaas».destapé.… | `cosLaas` | — *(dímelo tú)* |
| 24 | 2237 | …esAtheolribarsoé: «ceosntatasrehñaosrtaa» edsótnádleocllae.gaba esa locura:…… | `ceosntatasrehñaosrtaa` | — *(dímelo tú)* |
| 25 | 2237 | ……olribarsoé: ceosntatasrehñaosrtaa «edsótnádleocllae».gaba esa locura: llegaba hasta da…… | `edsótnádleocllae` | — *(dímelo tú)* |
| 26 | 2237 | …«esAtheolribarsoé»: ceosntatasrehñaosrtaa edsótnádle…… | `esAtheolribarsoé` | — *(dímelo tú)* |
| 27 | 2343 | ……que la memoria solo entrega en la «maDneo».bajo de las tachaduras puse: Preg…… | `maDneo` | — *(dímelo tú)* |

## 4. Para cerrar el texto

- **Opción rápida:** respóndeme en un solo mensaje qué decía cada palabra de la §3.
- **Opción ideal:** mándame el manuscrito original *antes de que fuera PDF* (Google Docs, Word, `.txt`…); con él el libro sale limpio sin ninguna consulta.

*(Informe generado automáticamente del archivo entregado; no modifica el manuscrito salvo las restauraciones de espacio de §2, todas reversibles y trazables.)*