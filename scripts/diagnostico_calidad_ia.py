"""Diagnóstico de calidad del dictamen — con datos REALES, no supuestos.

09-09-2026. El auditor preguntó por qué la confianza no sube de ~40% y qué
hay que cambiar. La respuesta tiene partes que solo se pueden confirmar
mirando la base de datos REAL del hospital — que desde el entorno de
desarrollo de Claude Code no se puede ver (vive en el servidor del HUS).

Este script corre AHÍ, de forma segura (solo LEE, no cambia nada), y
contesta con números reales:

  · cuántas glosas se han analizado y con qué modelo de IA cada una,
  · qué fracción quedó con la EPS en «OTRA / SIN DEFINIR» (genérica),
  · si el catálogo de tarifas pactadas por CUPS está poblado o vacío,
  · si el catálogo de cláusulas de contrato cubre las EPS reales,
  · cuántas glosas tienen ya un veredicto final de la EPS (LEVANTADA/
    RATIFICADA/ACEPTADA) — de ahí sale el «precedente interno» y los
    ejemplos de la IA (few-shot gold); sin esto, los dos se quedan sin
    combustible por más glosas que se analicen,
  · la distribución de la confianza (score) por mes y por modelo de IA.

Uso (en el servidor del HUS, con el entorno del motor activado):
    python scripts/diagnostico_calidad_ia.py

No hace falta ningún permiso especial: usa la misma base de datos que ya
usa el motor (`DATABASE_URL` del .env), en modo solo lectura.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _linea(titulo: str) -> None:
    print(f"\n{'═' * 70}\n {titulo}\n{'═' * 70}")


def main() -> int:
    from app.database import SessionLocal
    from app.models.db import ClausulaContrato, ContratoRecord, GlosaRecord, TarifaContratadaRecord

    db = SessionLocal()
    try:
        total = db.query(GlosaRecord).count()
        _linea("1) VOLUMEN REAL")
        print(f"Glosas analizadas por el motor (tabla GlosaRecord): {total}")
        if total == 0:
            print("No hay ninguna glosa registrada todavía. El resto de este")
            print("reporte no tiene con qué calcularse.")
            return 0
        if total < 200:
            print(
                "Con este volumen, «precedente interno» (exige una glosa YA "
                "levantada con la misma EPS + mismo tipo de código) va a tener "
                "pocas coincidencias por pura estadística, no porque algo esté "
                "roto. Crece solo, con el tiempo y con el punto 4 de abajo."
            )

        # ── 2) EPS: cuántas quedan genéricas ──────────────────────────
        _linea("2) EPS — ¿CUÁNTAS QUEDAN COMO «OTRA / SIN DEFINIR»?")
        genericas = {"", "OTRA", "SIN DEFINIR", "OTRA / SIN DEFINIR", "OTRA/SIN DEFINIR"}
        contador_eps = Counter(
            (r[0] or "").strip().upper() for r in db.query(GlosaRecord.eps).all()
        )
        n_generico = sum(n for eps, n in contador_eps.items() if eps in genericas)
        pct = 100 * n_generico / total
        print(f"Genéricas (sin nombre de entidad): {n_generico} de {total} ({pct:.1f}%)")
        print("Top 15 EPS con nombre real:")
        for eps, n in sorted(
            ((e, n) for e, n in contador_eps.items() if e not in genericas),
            key=lambda x: -x[1],
        )[:15]:
            print(f"   {n:5}  {eps}")
        if pct > 15:
            print(
                "\nMás de 1 de cada 7 glosas sin entidad identificada es mucho: "
                "revise si el desplegable de Analizar ya trae la corrección del "
                "09-09-2026 (PR «catálogo de EPS»). Antes de esa fecha, cualquier "
                "EPS sin contrato SOLO se podía elegir como «OTRA / SIN DEFINIR»."
            )

        # ── 3) Tarifas pactadas por CUPS ───────────────────────────────
        _linea("3) TARIFAS PACTADAS POR CUPS (tabla tarifas_contratadas)")
        n_tarifas = db.query(TarifaContratadaRecord).count()
        print(f"Filas cargadas: {n_tarifas}")
        if n_tarifas == 0:
            print(
                "VACÍA. Para una glosa de TARIFAS (TA*, el tipo más simple y "
                "mecánico: comparar un valor facturado contra uno pactado), el "
                "motor no tiene con qué comparar cifra-contra-cifra por ítem — "
                "solo el texto general del contrato (SOAT -15%, etc.). Si hay "
                "un Excel de tarifas pactadas por CUPS de alguna EPS (aunque "
                "sea de una sola), cargarlo en la pantalla Tarifas sube la "
                "precisión de ESE tipo de glosa de inmediato."
            )

        # ── 4) Cláusulas de contrato ────────────────────────────────────
        _linea("4) CLÁUSULAS DE CONTRATO (tabla clausulas_contrato)")
        eps_con_clausula = {r[0] for r in db.query(ClausulaContrato.eps).distinct().all()}
        eps_con_contrato_registro = {r[0] for r in db.query(ContratoRecord.eps).all() if r[0]}
        print(f"EPS con al menos una cláusula extraída: {len(eps_con_clausula)}")
        print(
            f"EPS con fila en ContratoRecord (con o sin cláusulas): {len(eps_con_contrato_registro)}"
        )
        sin_clausulas = sorted(eps_con_contrato_registro - eps_con_clausula)
        if sin_clausulas:
            print(f"Tienen registro pero CERO cláusulas: {sin_clausulas}")

        # ── 5) Veredicto final de la EPS (combustible de precedente + few-shot) ──
        _linea("5) VEREDICTO FINAL DE LA EPS (decision_eps / estado)")
        cerrados = {"LEVANTADA", "RATIFICADA", "ACEPTADA", "CONCILIADA"}
        contador_estado = Counter(
            (r[0] or "SIN ESTADO").upper() for r in db.query(GlosaRecord.estado).all()
        )
        n_cerrados = sum(n for e, n in contador_estado.items() if e in cerrados)
        print(
            f"Con un veredicto final registrado: {n_cerrados} de {total} ({100 * n_cerrados / total:.1f}%)"
        )
        for estado, n in contador_estado.most_common(12):
            print(f"   {n:5}  {estado}")
        if n_cerrados / total < 0.30:
            print(
                "\nMenos de 3 de cada 10 tienen el veredicto de la EPS registrado. "
                "«Precedente interno» Y el banco de argumentos ganadores "
                "(few_shot_gold) LEEN de acá — si esto no se actualiza cuando la "
                "EPS responde semanas después, los dos se quedan sin combustible "
                "aunque el volumen de glosas siga creciendo. Vale la pena revisar "
                "si hay glosas viejas cuya respuesta de la EPS ya se conoce y "
                "nadie volvió a marcarla."
            )

        # ── 6) Confianza (score) — el número que preocupa ────────────────
        _linea("6) CONFIANZA (score) — promedio y por modelo de IA")
        filas = (
            db.query(GlosaRecord.score, GlosaRecord.modelo_ia)
            .filter(GlosaRecord.score.isnot(None), GlosaRecord.score > 0)
            .all()
        )
        if not filas:
            print("Ninguna glosa tiene `score` guardado todavía.")
        else:
            promedio = sum(s for s, _ in filas) / len(filas)
            print(f"Promedio general: {promedio:.1f}  (sobre {len(filas)} glosas con score)")
            por_modelo: dict[str, list[float]] = {}
            for score, modelo in filas:
                por_modelo.setdefault(modelo or "sin registrar", []).append(score)
            print("\nPor modelo de IA que lo generó:")
            for modelo, scores in sorted(por_modelo.items(), key=lambda x: -len(x[1])):
                print(
                    f"   {len(scores):5} glosas · promedio {sum(scores) / len(scores):5.1f}  · {modelo}"
                )
            print(
                "\nSi ve un promedio marcadamente más alto en las filas donde "
                "`modelo_ia` empieza por un modelo de Anthropic/Claude que en "
                "las de Groq, esa es la prueba directa —con SUS datos, no con "
                "casos inventados— de si cambiar el proveedor primario sube la "
                "calidad real."
            )

        # ── 7) Costo real de Anthropic (tabla ai_calls) ──────────────────
        _linea("7) COSTO REAL DE ANTHROPIC (tabla ai_calls)")
        try:
            from app.models.db import AICallRecord

            llamadas = db.query(AICallRecord).filter(AICallRecord.proveedor == "anthropic").all()
            if not llamadas:
                print(
                    "Ninguna llamada a Anthropic registrada todavía (hoy solo entra "
                    "como respaldo técnico de Groq). El día que se pruebe como "
                    "proveedor principal —aunque sea con un lote de 20-30 glosas—, "
                    "el costo REAL de esa prueba queda aquí, ya calculado en dólares: "
                    "no hace falta estimarlo, esta tabla ya lo hace por cada llamada."
                )
            else:
                costo_total = sum(c.cost_usd or 0 for c in llamadas)
                print(f"Llamadas registradas: {len(llamadas)}")
                print(f"Costo acumulado histórico: USD ${costo_total:.4f}")
                print(f"Costo promedio por llamada: USD ${costo_total / len(llamadas):.4f}")
                print(
                    "\nPara proyectar el costo mensual de usar Anthropic como "
                    "principal: (costo promedio por llamada) × (glosas del mes)."
                )
        except Exception as e:  # noqa: BLE001
            print(f"No se pudo leer ai_calls: {e}")

        _linea("FIN DEL DIAGNÓSTICO")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
