# Expediente Inteligente

**Qué es.** La pantalla **Expediente** (menú lateral, sección Análisis) reúne
en un solo lugar todo lo de una glosa: quién es, con qué contrato se
defiende, qué ha pasado desde que llegó y qué soportes existen. Lo que antes
exigía abrir el historial, un popup de timeline, la pantalla de conciliación
y el buscador de soportes.

## Cómo se usa

1. Abrir **Expediente** en el menú y escribir el **ID de la glosa** o el
   **número de factura** (HUS000…). Enter.
2. Si hay varias coincidencias se listan; un clic abre el expediente.
3. El botón **📜 Timeline** de cualquier glosa también entra directo acá.

## Qué muestra

- **Ficha**: pagador, factura, código, estado, valores, auditor, versiones
  del dictamen.
- **Contrato** (⚖️, con color): la verificación contractual registrada al
  analizar — verde = contrato vigente el día del hecho, ámbar = ese día no
  regía ninguno (se defendió a SOAT pleno), rojo = pagador fuera de la
  malla.
- **Conciliaciones**: actas y resultados de mesa de esa glosa.
- **Soportes conocidos**: lo que el indexador encontró para esa factura.
- **Línea de tiempo completa** con filtros de un clic (IA, Auditoría,
  Dictamen, Comentarios, Estado): cada análisis, versión, cambio de estado,
  comentario y llamada de IA, con su actor y su fecha.

## Todo termina en el expediente

Cada acción del sistema deja constancia que aparece aquí sin configurar
nada: los análisis dejan la **verificación contractual**, las actas de mesa
dejan **ACTA EXCEL OPTIMIZADA / PDF**, los cambios de estado y las
conciliaciones quedan como eventos. Regla de construcción: si algo no queda
registrado y consultable en el expediente, no está terminado.

## Para consultarlo desde fuera de la pantalla

- **API**: `GET /glosas/{id}/expediente` (todo consolidado) y
  `GET /glosas/expediente/buscar?q=…` (por ID o factura). Cualquier usuario
  autenticado puede leer; escribir sigue exigiendo rol de auditor o
  superior en cada acción de origen.
- **Chat IA**: preguntar «¿qué ha pasado con la factura HUS…?» — el
  asistente usa la herramienta `consultar_expediente`, que lee exactamente
  la misma consolidación que la pantalla.

## Qué se retiró

El popup de timeline (ventana aparte con `document.write`) se eliminó: la
línea de tiempo ahora vive dentro de la aplicación, con búsqueda y filtros.
