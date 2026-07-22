#!/usr/bin/env python3
"""HOSPIAI — AG010 Supervisor (Fase 2 · Sprint 1).

El ÚNICO responsable de ejecutar misiones. Nunca ejecuta trabajo, nunca
interpreta documentos, nunca consulta reglas de negocio. Solo decide:
¿qué misión sigue? → ¿qué agente puede atenderla? → ¿está permitida por las
políticas? → la asigna → espera la respuesta → actualiza el estado → genera
la siguiente misión (si una cadena lo indica).

Seis responsabilidades, seis piezas separadas:

- **Scheduler**    ordena la cola (prioridad, dependencias, backoff `no_antes`).
- **Dispatcher**   elige el agente SOLO por el Registro Central y sus
                   capacidades/compatibilidad — jamás instancia clases directas.
- **RetryManager** ERROR → backoff creciente → reintento → error definitivo
                   (nada queda bloqueado; el fallo final deja Decision Record).
- **PolicyEngine** aplica `data/politicas.json` (concurrencia por tipo, horario,
                   aprobación humana). Las políticas nunca van en código.
- **MissionLogger** persiste CADA transición en la tabla `mision_log`.
- **Supervisor**   el ciclo que los une.

Uso:
    py tools\\hospiai_supervisor.py correr [--db data\\hospiai.db] [--max 100]
    py tools\\hospiai_supervisor.py estado
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402
from hospiai_agentes import registro_con_implementaciones  # noqa: E402
from hospiai_sdk import VERSION_SDK, ColaMisiones, Mision, RegistroAgentes, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
RUTA_POLITICAS = RAIZ / "data" / "politicas.json"
DB_DEFAULT = RAIZ / "data" / "hospiai.db"


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─── Policy Engine ───────────────────────────────────────────────────────────


class PolicyEngine:
    """Aplica las políticas de ejecución (data/politicas.json). Responde una
    sola pregunta: ¿esta misión puede correr AHORA? (y si no, por qué)."""

    def __init__(self, ruta: Path | None = None, ahora=None):
        ruta = ruta or RUTA_POLITICAS
        self.politicas = (
            json.loads(ruta.read_text(encoding="utf-8-sig")) if Path(ruta).is_file() else {}
        )
        self._ahora = ahora or datetime.now  # inyectable para probar horarios

    def permitida(self, mision: Mision, en_curso_por_tipo: dict[str, int]) -> tuple[bool, str]:
        p = self.politicas
        if mision.tipo in (p.get("requiere_aprobacion_humana") or []):
            return False, "requiere aprobación humana (política): no se auto-ejecuta"
        tope = (p.get("max_procesos_por_tipo") or {}).get(mision.tipo)
        if tope is not None and en_curso_por_tipo.get(mision.tipo, 0) >= tope:
            return False, f"tope de {tope} proceso(s) simultáneo(s) para {mision.tipo}"
        horario = p.get("horario_laboral") or {}
        if mision.tipo in (horario.get("aplica_a_tipos") or []):
            hhmm = self._ahora().strftime("%H:%M")
            if not (horario.get("desde", "00:00") <= hhmm <= horario.get("hasta", "23:59")):
                return False, (
                    f"fuera de horario permitido ({horario.get('desde')}–{horario.get('hasta')})"
                )
        return True, ""

    def backoff(self, intento: int) -> int:
        escala = self.politicas.get("backoff_segundos") or [5, 60, 300]
        return escala[min(intento - 1, len(escala) - 1)]

    def cadena(self, tipo_terminado: str) -> list[dict]:
        cadenas = self.politicas.get("cadenas") or {}
        return [c for c in cadenas.get(tipo_terminado, []) if isinstance(c, dict)]


# ─── Mission Logger ──────────────────────────────────────────────────────────


class MissionLogger:
    """Cada transición de estado queda persistida (tabla mision_log)."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def transicion(
        self, mision: Mision, de: str, a: str, agente: str = "", detalle: str = ""
    ) -> None:
        con = hospiai_db.abrir(self.db_path)
        try:
            with con:
                con.execute(
                    "INSERT INTO mision_log(mision_codigo, de_estado, a_estado, agente, fecha,"
                    " detalle) VALUES(?,?,?,?,?,?)",
                    (mision.codigo, de, a, agente, _ahora(), detalle[:300]),
                )
        finally:
            con.close()


# ─── Scheduler ───────────────────────────────────────────────────────────────


class Scheduler:
    """Ordena la cola: prioridad ALTA primero (lo hace la propia cola), salta
    misiones con dependencias sin cumplir y respeta el backoff (no_antes)."""

    def __init__(self, cola: ColaMisiones):
        self.cola = cola

    def elegibles(self) -> list[Mision]:
        listas = []
        for m in self.cola.pendientes():
            dependencias = [str(c) for c in (m.datos.get("depende_de") or [])]
            if dependencias:
                estados = self.cola.estados_de(dependencias)
                if any(estados.get(c) != "OK" for c in dependencias):
                    continue  # aún no le toca
            listas.append(m)
        return listas


# ─── Dispatcher ──────────────────────────────────────────────────────────────


class Dispatcher:
    """Elige QUIÉN atiende una misión consultando SOLO el Registro Central:
    capacidad → estado ACTIVO → compatibilidad de SDK. Jamás conoce clases."""

    def __init__(self, registro: RegistroAgentes):
        self.registro = registro
        self._mayor_sdk = VERSION_SDK.split(".")[0]

    def candidato(self, mision: Mision) -> str | None:
        for ficha in self.registro.por_capacidad(mision.tipo):
            requiere = str(ficha.get("requiere_sdk", "")).split(".")[0]
            if requiere and requiere != self._mayor_sdk:
                continue
            return ficha["id"]
        return None

    def existe_capacidad(self, tipo: str) -> bool:
        """¿ALGÚN agente (en cualquier estado) declara esta capacidad?"""
        return any(tipo in (a.get("capacidades") or []) for a in self.registro.listar())


# ─── Retry Manager ───────────────────────────────────────────────────────────


class RetryManager:
    """ERROR → backoff → reintento → error definitivo. Nada queda bloqueado:
    el fallo definitivo deja un Decision Record operativo, auditable."""

    def __init__(self, cola: ColaMisiones, politicas: PolicyEngine, logger: MissionLogger):
        self.cola = cola
        self.politicas = politicas
        self.logger = logger

    def gestionar_fallo(self, mision: Mision, res: ResultadoAgente) -> str:
        if mision.intentos >= mision.max_intentos:
            self.cola.fallar(mision, res)
            self.logger.transicion(
                mision, "EJECUTANDO", "ERROR", res.agente, f"definitivo: {res.detalle}"
            )
            self._decision_fallo(mision, res)
            return "ERROR"
        espera = self.politicas.backoff(mision.intentos)
        self.cola.fallar(mision, res)  # vuelve a PENDIENTE (aún hay intentos)
        self.cola.reprogramar(mision, espera)
        self.logger.transicion(
            mision,
            "EJECUTANDO",
            "REINTENTO",
            res.agente,
            f"intento {mision.intentos}/{mision.max_intentos}; backoff {espera}s: {res.detalle}",
        )
        return "REINTENTO"

    def _decision_fallo(self, mision: Mision, res: ResultadoAgente) -> None:
        con = hospiai_db.abrir(self.cola.db_path)
        try:
            with con:
                cur = con.execute(
                    "INSERT INTO decisiones(codigo, factura_norm, dictamen, motivo, agente,"
                    " version_motor, version_reglas, confianza, fecha)"
                    " VALUES('', ?, 'ERROR_OPERATIVO', ?, ?, ?, ?, 0.0, ?)",
                    (
                        mision.expediente or "-",
                        f"{mision.codigo} ({mision.tipo}) agotó {mision.max_intentos} "
                        f"intento(s): {res.detalle}"[:300],
                        res.agente or "AG010",
                        res.versiones.get("agente", ""),
                        res.versiones.get("reglas", ""),
                        _ahora(),
                    ),
                )
                con.execute(
                    "UPDATE decisiones SET codigo=? WHERE id=?",
                    (f"DEC-{cur.lastrowid:06d}", cur.lastrowid),
                )
        finally:
            con.close()


# ─── Supervisor (AG010) ──────────────────────────────────────────────────────


class Supervisor:
    """El ciclo que une las piezas. No ejecuta trabajo: asigna, espera,
    actualiza y encadena."""

    id = "AG010"
    version = "1.0"

    def __init__(self, db_path: Path, registro: RegistroAgentes | None = None,
                 politicas: PolicyEngine | None = None):  # fmt: skip
        self.db_path = Path(db_path)
        self.cola = ColaMisiones(self.db_path)
        self.registro = registro or registro_con_implementaciones()
        self.politicas = politicas or PolicyEngine()
        self.logger = MissionLogger(self.db_path)
        self.scheduler = Scheduler(self.cola)
        self.dispatcher = Dispatcher(self.registro)
        self.retry = RetryManager(self.cola, self.politicas, self.logger)
        self._en_curso_por_tipo: dict[str, int] = {}

    def paso(self) -> dict | None:
        """Procesa UNA misión elegible. None si no hay trabajo asignable."""
        for mision in self.scheduler.elegibles():
            permitida, motivo = self.politicas.permitida(mision, self._en_curso_por_tipo)
            if not permitida:
                self.logger.transicion(mision, "PENDIENTE", "PENDIENTE", "AG010", motivo)
                continue
            agente_id = self.dispatcher.candidato(mision)
            if agente_id is None:
                if not self.dispatcher.existe_capacidad(mision.tipo):
                    res = ResultadoAgente(
                        agente="AG010", version=self.version, resultado="ERROR",
                        detalle=f"ningún agente declara la capacidad '{mision.tipo}'",
                    )  # fmt: skip
                    mision.intentos = mision.max_intentos  # sin candidato no hay reintento útil
                    self.retry.gestionar_fallo(mision, res)
                    return {"mision": mision.codigo, "resultado": "ERROR", "agente": None}
                self.logger.transicion(
                    mision, "PENDIENTE", "PENDIENTE", "AG010",
                    f"capacidad '{mision.tipo}' existe pero sin agente ACTIVO/compatible",
                )  # fmt: skip
                continue

            self.cola.asignar(mision, agente_id)
            self.logger.transicion(mision, "PENDIENTE", "ASIGNADA", agente_id)
            self._en_curso_por_tipo[mision.tipo] = self._en_curso_por_tipo.get(mision.tipo, 0) + 1
            self.logger.transicion(mision, "ASIGNADA", "EJECUTANDO", agente_id)
            try:
                agente = self.registro.instanciar(agente_id)
                res = agente.ejecutar(mision, {"db_path": self.db_path})
            finally:
                self._en_curso_por_tipo[mision.tipo] -= 1

            if res.resultado == "OK":
                self.cola.completar(mision, res)
                self.logger.transicion(
                    mision, "EJECUTANDO", "FINALIZADA", agente_id, f"{res.duracion_ms} ms"
                )
                self._encadenar(mision)
                return {"mision": mision.codigo, "resultado": "OK", "agente": agente_id}
            if res.resultado == "OMITIDO":
                self.cola.completar(mision, res)  # atendida: no aplicaba
                self.logger.transicion(mision, "EJECUTANDO", "FINALIZADA", agente_id, res.detalle)
                return {"mision": mision.codigo, "resultado": "OMITIDO", "agente": agente_id}
            estado = self.retry.gestionar_fallo(mision, res)
            return {"mision": mision.codigo, "resultado": estado, "agente": agente_id}
        return None

    def correr(self, max_misiones: int = 200) -> dict:
        """Drena la cola hasta agotar lo elegible (o el tope de seguridad)."""
        conteo: dict[str, int] = {}
        for _ in range(max_misiones):
            r = self.paso()
            if r is None:
                break
            conteo[r["resultado"]] = conteo.get(r["resultado"], 0) + 1
        return conteo

    def _encadenar(self, mision: Mision) -> None:
        for espec in self.politicas.cadena(mision.tipo):
            nueva = self.cola.crear(
                espec["tipo"],
                expediente=mision.expediente,
                prioridad=espec.get("prioridad", "NORMAL"),
                datos={**mision.datos, "origen_cadena": mision.codigo},
                creada_por="AG010",
            )
            self.logger.transicion(nueva, "", "PENDIENTE", "AG010", f"cadena de {mision.codigo}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AG010 Supervisor — orquestador de misiones HOSPIAI.")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("correr", help="Drena la cola de misiones aplicando las políticas.")
    sc.add_argument("--max", type=int, default=200, help="Tope de misiones por pasada.")
    sub.add_parser("estado", help="Cola + últimas transiciones del log.")
    args = p.parse_args(argv)

    if args.cmd == "correr":
        sup = Supervisor(args.db)
        conteo = sup.correr(args.max)
        total = sum(conteo.values())
        print(f"Supervisor AG010: {total} misión(es) procesadas — {conteo or 'cola vacía'}")
        return 0

    cola = ColaMisiones(args.db)
    print("Cola:", cola.estado() or "(vacía)")
    con = hospiai_db.abrir(args.db)
    try:
        filas = con.execute(
            "SELECT mision_codigo, de_estado, a_estado, agente, fecha, detalle"
            " FROM mision_log ORDER BY id DESC LIMIT 15"
        ).fetchall()
    finally:
        con.close()
    for f in filas:
        print(
            f"  {f['fecha']}  {f['mision_codigo']}  {f['de_estado'] or '·':<10}→ "
            f"{f['a_estado']:<10} {f['agente']:<7} {f['detalle']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
