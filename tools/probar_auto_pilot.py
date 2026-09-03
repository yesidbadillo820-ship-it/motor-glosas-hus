"""Prueba en vivo del Auto-Pilot Zero-Touch — para correr EN EL SERVIDOR.

Qué hace (03-09-2026, por orden del auditor):

  1. Corre UN ciclo del worker sobre las glosas más recientes con dictamen
     (el «lote»), con el tope que usted diga (--limite, 25 por defecto).
  2. Muestra los borradores que quedaron en cuarentena
     PENDIENTE_APROBACION_HUMANA — la IA no puede escribir otra cosa.
  3. Muestra las últimas filas de la bitácora inmutable
     (auto_pilot_bitacora): glosa, decisión, regla, confianza, riesgo,
     soportes analizados y el modelo que produjo el dictamen
     (columna `modelo_utilizado` — Claude de Anthropic o el respaldo Groq).

Nada queda «RESPONDIDA»: liberar un borrador sigue siendo un clic humano
en la pantalla (botón 📤 Borradores Auto-Pilot).

Cómo correrlo en el PC del servidor (PowerShell o doble consola):

    cd C:\\motor-glosas\\repo
    venv\\Scripts\\python.exe tools\\probar_auto_pilot.py
    venv\\Scripts\\python.exe tools\\probar_auto_pilot.py --limite 5   (piloto corto)

Interruptor: respeta AUTO_PILOT_ENABLED con la misma regla del arranque —
la consola le gana al .env, el .env le gana al valor por defecto del repo
(encendido desde el 03-09-2026). Con AUTO_PILOT_ENABLED=0 en el .env, este
script reporta «deshabilitado» y no toca nada.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_env_como_el_arranque() -> None:
    """Misma precedencia que tools/servidor_motor_local.cmd:
    consola > .env local > valor por defecto del repo (encendido)."""
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())
    os.environ.setdefault("AUTO_PILOT_ENABLED", "true")


def correr_prueba(db, limite: int) -> dict:
    """Ejecuta el ciclo y arma el informe con las tres evidencias.
    Devuelve {"parte", "borradores", "bitacora"} para poder probarlo."""
    from app.models.db import AutoPilotBitacoraRecord, GlosaRecord
    from app.services.auto_pilot_worker import ESTADO_CUARENTENA, procesar

    parte = procesar(db, limite=limite)

    borradores = []
    bitacora = []
    if parte.get("estado") == "ok":
        filas_b = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.workflow_state == ESTADO_CUARENTENA)
            .order_by(GlosaRecord.id.desc())
            .limit(max(limite, 20))
            .all()
        )
        borradores = [
            {
                "glosa_id": g.id,
                "factura": g.factura,
                "eps": g.eps,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": g.valor_objetado,
                "workflow_state": g.workflow_state,
                "nota_workflow": g.nota_workflow,
            }
            for g in filas_b
        ]
        filas_l = (
            db.query(AutoPilotBitacoraRecord)
            .order_by(AutoPilotBitacoraRecord.id.desc())
            .limit(max(limite, 20))
            .all()
        )

        def _soportes(s):
            try:
                return json.loads(s or "[]")
            except Exception:
                return []

        bitacora = [
            {
                "id": f.id,
                "glosa_id": f.glosa_id,
                "decision": f.decision,
                "regla_aplicada": f.regla_aplicada,
                "confianza": f.confianza,
                "riesgo": f.riesgo,
                "modelo_utilizado": f.modelo_utilizado,
                "soportes_analizados": _soportes(f.soportes_analizados),
                "actor": f.actor,
            }
            for f in filas_l
        ]
    return {"parte": parte, "borradores": borradores, "bitacora": bitacora}


def _imprimir(informe: dict) -> None:
    parte = informe["parte"]
    print("═══ 1) CICLO DEL WORKER (segundo plano, un solo comando) ═══")
    print(json.dumps(parte, ensure_ascii=False, indent=2))
    if parte.get("estado") == "deshabilitado":
        print(
            "\nEl interruptor está APAGADO (AUTO_PILOT_ENABLED). No se tocó nada.\n"
            "Para encenderlo: quite AUTO_PILOT_ENABLED=0 del .env (o póngalo en true)."
        )
        return
    if parte.get("estado") == "abortado_por_indexador":
        print(
            "\nEl indexador de soportes está a medio construir: el ciclo se canceló\n"
            "entero sin evaluar nada (escudo nº 2). Espere a que termine y repita."
        )
        return

    print("\n═══ 2) BORRADORES EN CUARENTENA (PENDIENTE_APROBACION_HUMANA) ═══")
    if informe["borradores"]:
        for b in informe["borradores"]:
            print(json.dumps(b, ensure_ascii=False))
    else:
        print(
            "Ninguna glosa pasó las reglas estrictas en este lote (confianza > 92 %,\n"
            "valor < $500.000, riesgo BAJO). Los rechazos quedaron en la bitácora."
        )

    print("\n═══ 3) BITÁCORA INMUTABLE (auto_pilot_bitacora) ═══")
    for f in informe["bitacora"]:
        print(json.dumps(f, ensure_ascii=False))
    print(
        "\nListo. Nada quedó RESPONDIDA: liberar un borrador sigue siendo un clic\n"
        "humano en la pantalla (botón 📤 Borradores Auto-Pilot)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba en vivo del Auto-Pilot Zero-Touch")
    parser.add_argument(
        "--limite",
        type=int,
        default=25,
        help="Cuántas glosas recientes evaluar en el ciclo (por defecto 25).",
    )
    args = parser.parse_args(argv)

    _cargar_env_como_el_arranque()
    sys.path.insert(0, str(RAIZ))

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        informe = correr_prueba(db, limite=max(1, args.limite))
    finally:
        db.close()
    _imprimir(informe)
    estado = informe["parte"].get("estado")
    return {"ok": 0, "deshabilitado": 2, "abortado_por_indexador": 3}.get(estado, 1)


if __name__ == "__main__":
    raise SystemExit(main())
