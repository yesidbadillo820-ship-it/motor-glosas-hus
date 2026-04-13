from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.db import ConciliacionRecord


class ConciliacionRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(self, glosa_id, creado_por, fecha_audiencia, lugar="",
              participantes_hus="", participantes_eps="", resultado="PENDIENTE",
              valor_conciliado=0.0, observaciones="", siguiente_paso="", acta_numero=""):
        c = ConciliacionRecord(
            glosa_id=glosa_id, creado_por=creado_por, fecha_audiencia=fecha_audiencia,
            lugar=lugar, participantes_hus=participantes_hus,
            participantes_eps=participantes_eps, resultado=resultado,
            valor_conciliado=valor_conciliado, observaciones=observaciones,
            siguiente_paso=siguiente_paso, acta_numero=acta_numero,
        )
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return c

    def obtener_por_id(self, conciliacion_id: int):
        return self.db.query(ConciliacionRecord).filter(
            ConciliacionRecord.id == conciliacion_id).first()

    def listar_por_glosa(self, glosa_id: int):
        return (self.db.query(ConciliacionRecord)
                .filter(ConciliacionRecord.glosa_id == glosa_id)
                .order_by(desc(ConciliacionRecord.creado_en)).all())

    def listar(self, page=1, per_page=20, resultado=None) -> dict:
        q = self.db.query(ConciliacionRecord).order_by(desc(ConciliacionRecord.fecha_audiencia))
        if resultado:
            q = q.filter(ConciliacionRecord.resultado == resultado.upper())
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return {"items": items, "total": total, "page": page,
                "per_page": per_page, "pages": (total + per_page - 1) // per_page}

    def actualizar_resultado(self, conciliacion_id, resultado, valor_conciliado,
                              observaciones="", siguiente_paso="", acta_numero=""):
        c = self.obtener_por_id(conciliacion_id)
        if not c:
            return None
        c.resultado = resultado
        c.valor_conciliado = valor_conciliado
        if observaciones:
            c.observaciones = observaciones
        if siguiente_paso:
            c.siguiente_paso = siguiente_paso
        if acta_numero:
            c.acta_numero = acta_numero
        self.db.commit()
        self.db.refresh(c)
        return c

    def estadisticas(self) -> dict:
        resultados = self.db.query(
            ConciliacionRecord.resultado,
            func.count(ConciliacionRecord.id).label("total"),
            func.sum(ConciliacionRecord.valor_conciliado).label("valor"),
        ).group_by(ConciliacionRecord.resultado).all()
        total_general = sum(r.total for r in resultados)
        return {
            "total": total_general,
            "por_resultado": [
                {"resultado": r.resultado, "total": r.total,
                 "valor_conciliado": float(r.valor or 0),
                 "porcentaje": round(r.total / total_general * 100, 1) if total_general > 0 else 0}
                for r in resultados
            ],
        }
