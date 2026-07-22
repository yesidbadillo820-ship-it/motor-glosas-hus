#!/usr/bin/env python3
"""HOSPIAI — Agent SDK (Fase 1.6 · Plataforma de Agentes).

El kit con el que se construye TODO agente de la plataforma. Garantiza que
agregar un agente nuevo no requiera modificar el núcleo:

- **Contrato único** (`Agente`): identidad (AGxxx), dominio, versión, entradas,
  salidas, dependencias, capacidades; métodos `ejecutar / validar / registrar /
  explicar`. Las subclases SOLO implementan `_trabajar()`.
- **Formato estándar de resultado** (`ResultadoAgente`): todos los agentes
  devuelven exactamente la misma estructura (agente, expediente, resultado,
  confianza, hallazgos, evidencias, duracion_ms, versiones). Nunca salidas
  distintas.
- **Misiones** (`Mision`, `ColaMisiones`): los agentes NUNCA se llaman entre
  sí — publican misiones en una cola persistente (tabla `misiones` del
  Expediente Digital) y el Supervisor las asigna. Desacoplamiento total.
- **Registro Central** (`RegistroAgentes`): la plataforma conoce a sus agentes
  por `data/agentes.json` (identidad, versión, estado, capacidades). El
  Supervisor consume EXCLUSIVAMENTE este registro, jamás clases concretas.
- **Versionado reproducible**: cada resultado registra la versión del agente,
  de las reglas y del catálogo con que se produjo.

Solo lectura sobre los shares: los agentes escriben únicamente en el
Expediente Digital y en reportes locales.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import hospiai_db

RUTA_REGISTRO_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "agentes.json"

ESTADOS_AGENTE = ("ACTIVO", "MANTENIMIENTO", "EXPERIMENTAL", "PLANEADO", "RETIRADO")
ESTADOS_MISION = ("PENDIENTE", "EN_CURSO", "OK", "ERROR", "CANCELADA")
PRIORIDADES = ("ALTA", "NORMAL", "BAJA")


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─── Formato estándar de resultado ───────────────────────────────────────────


@dataclass
class ResultadoAgente:
    """Lo ÚNICO que un agente puede devolver. Mismo formato para todos."""

    agente: str
    version: str
    expediente: str = ""
    resultado: str = "OK"  # OK / ERROR / OMITIDO
    confianza: float = 1.0
    hallazgos: list[dict] = field(default_factory=list)
    evidencias: list[dict] = field(default_factory=list)
    salida: dict = field(default_factory=dict)  # datos producidos (contrato `salidas`)
    detalle: str = ""
    duracion_ms: int = 0
    versiones: dict = field(default_factory=dict)  # reglas, catálogo, modelo…

    def a_dict(self) -> dict:
        return {
            "agente": self.agente,
            "version": self.version,
            "expediente": self.expediente,
            "resultado": self.resultado,
            "confianza": self.confianza,
            "hallazgos": self.hallazgos,
            "evidencias": self.evidencias,
            "salida": self.salida,
            "detalle": self.detalle,
            "duracion_ms": self.duracion_ms,
            "versiones": self.versiones,
        }


# ─── Misiones ────────────────────────────────────────────────────────────────


@dataclass
class Mision:
    """Unidad de trabajo. Un agente no llama a otro: crea una misión."""

    codigo: str
    tipo: str
    expediente: str = ""
    prioridad: str = "NORMAL"
    estado: str = "PENDIENTE"
    datos: dict = field(default_factory=dict)
    creada_por: str = ""
    intentos: int = 0
    max_intentos: int = 2
    id: int = 0


class ColaMisiones:
    """Cola persistente de misiones sobre el Expediente Digital.

    El flujo del desacoplamiento: `crear()` publica; `tomar()` la pasa a
    EN_CURSO para un agente; `completar()`/`fallar()` cierran (fallar reintenta
    hasta max_intentos). Todo queda auditable en la tabla `misiones`."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def crear(
        self,
        tipo: str,
        *,
        expediente: str = "",
        prioridad: str = "NORMAL",
        datos: dict | None = None,
        creada_por: str = "",
        max_intentos: int = 2,
    ) -> Mision:
        ahora = _ahora()
        con = hospiai_db.abrir(self.db_path)
        try:
            with con:
                cur = con.execute(
                    "INSERT INTO misiones(codigo, expediente, tipo, prioridad, estado, creada,"
                    " actualizada, creada_por, max_intentos, datos)"
                    " VALUES('', ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?, ?)",
                    (
                        expediente,
                        tipo,
                        prioridad,
                        ahora,
                        ahora,
                        creada_por,
                        max_intentos,
                        json.dumps(datos or {}, ensure_ascii=False),
                    ),
                )
                mid = cur.lastrowid
                codigo = f"MISION-{mid:06d}"
                con.execute("UPDATE misiones SET codigo=? WHERE id=?", (codigo, mid))
        finally:
            con.close()
        return Mision(
            codigo=codigo,
            tipo=tipo,
            expediente=expediente,
            prioridad=prioridad,
            datos=datos or {},
            creada_por=creada_por,
            max_intentos=max_intentos,
            id=mid,
        )

    def tomar(self, tipos: list[str], agente_id: str) -> Mision | None:
        """Asigna la siguiente misión PENDIENTE de esos tipos (prioridad ALTA
        primero, luego orden de llegada). Devuelve None si no hay trabajo."""
        con = hospiai_db.abrir(self.db_path)
        try:
            with con:
                fila = con.execute(
                    "SELECT * FROM misiones WHERE estado='PENDIENTE' AND tipo IN (%s)"
                    " ORDER BY CASE prioridad WHEN 'ALTA' THEN 0 WHEN 'NORMAL' THEN 1"
                    " ELSE 2 END, id LIMIT 1" % ",".join("?" * len(tipos)),
                    tipos,
                ).fetchone()
                if fila is None:
                    return None
                con.execute(
                    "UPDATE misiones SET estado='EN_CURSO', agente_asignado=?, actualizada=?,"
                    " intentos=intentos+1 WHERE id=?",
                    (agente_id, _ahora(), fila["id"]),
                )
            return Mision(
                codigo=fila["codigo"],
                tipo=fila["tipo"],
                expediente=fila["expediente"],
                prioridad=fila["prioridad"],
                estado="EN_CURSO",
                datos=json.loads(fila["datos"] or "{}"),
                creada_por=fila["creada_por"],
                intentos=fila["intentos"] + 1,
                max_intentos=fila["max_intentos"],
                id=fila["id"],
            )
        finally:
            con.close()

    def completar(self, mision: Mision, resultado: ResultadoAgente) -> None:
        self._cerrar(mision, "OK", resultado)

    def fallar(self, mision: Mision, resultado: ResultadoAgente) -> None:
        """ERROR definitivo si agotó reintentos; si no, vuelve a PENDIENTE."""
        estado = "ERROR" if mision.intentos >= mision.max_intentos else "PENDIENTE"
        self._cerrar(mision, estado, resultado)

    def _cerrar(self, mision: Mision, estado: str, resultado: ResultadoAgente) -> None:
        con = hospiai_db.abrir(self.db_path)
        try:
            with con:
                con.execute(
                    "UPDATE misiones SET estado=?, actualizada=?, resultado=? WHERE id=?",
                    (
                        estado,
                        _ahora(),
                        json.dumps(resultado.a_dict(), ensure_ascii=False),
                        mision.id,
                    ),
                )
        finally:
            con.close()

    def estado(self) -> dict[str, int]:
        con = hospiai_db.abrir(self.db_path)
        try:
            filas = con.execute(
                "SELECT estado, COUNT(*) n FROM misiones GROUP BY estado"
            ).fetchall()
            return {f["estado"]: f["n"] for f in filas}
        finally:
            con.close()


# ─── Contrato único de agente ────────────────────────────────────────────────


class Agente:
    """Contrato que TODO agente de HOSPIAI obedece. Las subclases declaran su
    identidad como atributos de clase e implementan SOLO `_trabajar()`.

    El template method `ejecutar()` garantiza el resto: validación de la
    misión, medición de duración, captura de errores (un agente que falla
    nunca tumba la plataforma), formato estándar de salida y registro en el
    Expediente Digital."""

    id: str = "AG000"
    nombre: str = "AgenteBase"
    dominio: str = ""  # D1..D6 (docs/ARQUITECTURA_HOSPIAI.md §3)
    version: str = "1.0"
    prioridad: str = "NORMAL"
    entradas: list[str] = []  # claves que exige en mision.datos
    salidas: list[str] = []  # claves que produce en resultado.salida
    depende_de: list[str] = []  # ids de agentes cuyo producto necesita
    herramientas: list[str] = []  # p.ej. "expediente", "shares-solo-lectura"
    capacidades: list[str] = []  # tipos de misión que sabe atender
    estado: str = "ACTIVO"

    # ── Ciclo de vida ──────────────────────────────────────────────────────

    def ejecutar(self, mision: Mision, contexto: dict | None = None) -> ResultadoAgente:
        contexto = contexto or {}
        res = ResultadoAgente(agente=self.id, version=self.version, expediente=mision.expediente)
        res.versiones = {
            "agente": self.version,
            "reglas": contexto.get("version_reglas", ""),
            "catalogo": contexto.get("version_catalogo", ""),
        }
        error = self.validar(mision)
        t0 = time.perf_counter()
        if error:
            res.resultado = "OMITIDO"
            res.detalle = error
            res.confianza = 0.0
        else:
            try:
                self._trabajar(mision, contexto, res)
            except Exception as e:  # el agente falla; la plataforma sigue
                res.resultado = "ERROR"
                res.confianza = 0.0
                res.detalle = f"{type(e).__name__}: {e}"
                res.salida["traza"] = traceback.format_exc(limit=3)
        res.duracion_ms = int((time.perf_counter() - t0) * 1000)
        db = contexto.get("db_path")
        if db:
            self.registrar(res, mision, Path(db))
        return res

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        raise NotImplementedError(f"{self.id} no implementa _trabajar()")

    def validar(self, mision: Mision) -> str:
        """'' si la misión es atendible; si no, el motivo (→ OMITIDO)."""
        if self.capacidades and mision.tipo not in self.capacidades:
            return (
                f"{self.id} no atiende misiones '{mision.tipo}' (capacidades: {self.capacidades})"
            )
        faltan = [k for k in self.entradas if k not in mision.datos and k != "expediente"]
        if "expediente" in self.entradas and not mision.expediente:
            faltan.append("expediente")
        if faltan:
            return f"misión {mision.codigo} sin entradas requeridas: {faltan}"
        return ""

    def registrar(self, res: ResultadoAgente, mision: Mision, db_path: Path) -> None:
        """Deja la huella en el Expediente Digital: un evento por ejecución y
        los hallazgos con su evidencia y confianza (corrida_id=0 = producido
        por misión, no por corrida del radicador; el detalle referencia la
        misión)."""
        ahora = _ahora()
        con = hospiai_db.abrir(db_path)
        try:
            with con:
                con.execute(
                    "INSERT INTO eventos(factura_norm, fecha, agente, tipo, resultado,"
                    " version_reglas, corrida_id, detalle) VALUES(?,?,?,?,?,?,0,?)",
                    (
                        mision.expediente or "-",
                        ahora,
                        f"{self.id} v{self.version}",
                        mision.tipo,
                        res.resultado,
                        res.versiones.get("reglas", ""),
                        f"{mision.codigo} · {res.duracion_ms} ms · {res.detalle}".strip(" ·"),
                    ),
                )
                for h in res.hallazgos:
                    con.execute(
                        "INSERT INTO hallazgos(factura_norm, corrida_id, agente, tipo, codigo,"
                        " criticidad, detalle, regla_id, evidencia, confianza, fecha)"
                        " VALUES(?,0,?,?,?,?,?,?,?,?,?)",
                        (
                            mision.expediente or "-",
                            f"{self.id} v{self.version}",
                            h.get("tipo", mision.tipo),
                            h.get("codigo", ""),
                            h.get("criticidad", "ADVERTENCIA"),
                            h.get("detalle", ""),
                            h.get("regla_id", ""),
                            h.get("evidencia", ""),
                            float(h.get("confianza", res.confianza)),
                            ahora,
                        ),
                    )
        finally:
            con.close()

    def explicar(self) -> dict:
        """Qué soy, qué hago, qué necesito y qué produzco — legible por el
        Supervisor y por humanos, sin mirar el código."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "dominio": self.dominio,
            "version": self.version,
            "estado": self.estado,
            "capacidades": list(self.capacidades),
            "entradas": list(self.entradas),
            "salidas": list(self.salidas),
            "depende_de": list(self.depende_de),
            "herramientas": list(self.herramientas),
        }


# ─── Registro Central de Agentes ─────────────────────────────────────────────


class RegistroAgentes:
    """La plataforma conoce a sus agentes por este registro (data/agentes.json),
    no por sus clases. El Supervisor pregunta aquí: ¿qué agentes existen?,
    ¿cuáles están disponibles?, ¿quién atiende 'OCR'?"""

    def __init__(self, ruta: Path | None = None):
        self.ruta = Path(ruta) if ruta else RUTA_REGISTRO_DEFAULT
        self._agentes: dict[str, dict] = {}
        self._clases: dict[str, type[Agente]] = {}
        if self.ruta.is_file():
            data = json.loads(self.ruta.read_text(encoding="utf-8-sig"))
            for a in data.get("agentes", []):
                self._agentes[a["id"]] = a

    def registrar_clase(self, cls: type[Agente]) -> None:
        """Vincula una implementación concreta a su ficha del registro. La ficha
        (JSON) manda sobre versión/estado si difieren."""
        ficha = self._agentes.setdefault(cls.id, {})
        ficha.update(
            {
                "id": cls.id,
                "nombre": ficha.get("nombre", cls.nombre),
                "dominio": ficha.get("dominio", cls.dominio),
                "version": ficha.get("version", cls.version),
                "estado": ficha.get("estado", cls.estado),
                "capacidades": ficha.get("capacidades", list(cls.capacidades)),
                "depende_de": ficha.get("depende_de", list(cls.depende_de)),
            }
        )
        self._clases[cls.id] = cls

    def listar(self) -> list[dict]:
        return [self._agentes[k] for k in sorted(self._agentes)]

    def disponibles(self) -> list[dict]:
        return [a for a in self.listar() if a.get("estado") == "ACTIVO"]

    def por_capacidad(self, capacidad: str) -> list[dict]:
        return [a for a in self.disponibles() if capacidad in (a.get("capacidades") or [])]

    def instanciar(self, agente_id: str) -> Agente:
        """El Supervisor pide por id; la implementación concreta es un detalle."""
        if agente_id not in self._clases:
            raise KeyError(f"El agente {agente_id} no tiene implementación registrada.")
        inst = self._clases[agente_id]()
        ficha = self._agentes.get(agente_id, {})
        if ficha.get("version"):
            inst.version = ficha["version"]
        if ficha.get("estado"):
            inst.estado = ficha["estado"]
        return inst

    def explicar(self, agente_id: str) -> dict:
        if agente_id in self._clases:
            return self.instanciar(agente_id).explicar()
        if agente_id in self._agentes:
            return self._agentes[agente_id]
        raise KeyError(f"Agente desconocido: {agente_id}")
