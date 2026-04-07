from typing import List, Optional
from datetime import datetime
from app.domain.entities.glosa import Glosa, EstadoGlosa, Etapa
from app.database import SessionLocal
from app.models.db import GlosaRecord


class GlosaRepository:
    def __init__(self):
        session = SessionLocal()
        session.close()

    def guardar(self, glosa: Glosa) -> int:
        db = SessionLocal()
        try:
            record = GlosaRecord(
                eps=glosa.eps.upper(),
                paciente=glosa.paciente,
                factura=glosa.factura,
                codigo_glosa=glosa.codigo_glosa,
                valor_objetado=glosa.valor_objetado,
                valor_aceptado=glosa.valor_aceptado,
                etapa=glosa.etapa.value if hasattr(glosa.etapa, 'value') else str(glosa.etapa),
                estado=glosa.estado.value if hasattr(glosa.estado, 'value') else str(glosa.estado),
                dictamen=glosa.dictamen,
                dias_restantes=glosa.dias_restantes,
                modelo_ia=glosa.modelo_ia,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        finally:
            db.close()

    def buscar_por_id(self, glosa_id: int) -> Optional[Glosa]:
        db = SessionLocal()
        try:
            record = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
            if not record:
                return None
            return self._to_entity(record)
        finally:
            db.close()

    def listar_todos(self, limite: int = 100) -> List[Glosa]:
        db = SessionLocal()
        try:
            records = db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).limit(limite).all()
            return [self._to_entity(r) for r in records]
        finally:
            db.close()

    def listar_por_eps(self, eps: str, limite: int = 50) -> List[Glosa]:
        db = SessionLocal()
        try:
            records = db.query(GlosaRecord).filter(
                GlosaRecord.eps == eps.upper()
            ).order_by(GlosaRecord.creado_en.desc()).limit(limite).all()
            return [self._to_entity(r) for r in records]
        finally:
            db.close()

    def listar_por_estado(self, estado: str, limite: int = 50) -> List[Glosa]:
        db = SessionLocal()
        try:
            records = db.query(GlosaRecord).filter(
                GlosaRecord.estado == estado.upper()
            ).order_by(GlosaRecord.dias_restantes.asc()).limit(limite).all()
            return [self._to_entity(r) for r in records]
        finally:
            db.close()

    def listar_vencidas(self, limite: int = 50) -> List[Glosa]:
        db = SessionLocal()
        try:
            records = db.query(GlosaRecord).filter(
                GlosaRecord.dias_restantes < 0
            ).order_by(GlosaRecord.dias_restantes.asc()).limit(limite).all()
            return [self._to_entity(r) for r in records]
        finally:
            db.close()

    def actualizar(self, glosa_id: int, datos: dict) -> bool:
        db = SessionLocal()
        try:
            db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).update(datos)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def eliminar(self, glosa_id: int) -> bool:
        db = SessionLocal()
        try:
            record = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
            if record:
                db.delete(record)
                db.commit()
                return True
            return False
        finally:
            db.close()

    def _to_entity(self, record: GlosaRecord) -> Glosa:
        return Glosa(
            id=record.id,
            eps=record.eps,
            paciente=record.paciente,
            factura=record.factura or "N/A",
            codigo_glosa=record.codigo_glosa or "",
            valor_objetado=record.valor_objetado or 0.0,
            valor_aceptado=record.valor_aceptado or 0.0,
            etapa=Etapa(record.etapa) if record.etapa else Etapa.INICIAL,
            estado=EstadoGlosa(record.estado) if record.estado else EstadoGlosa.RADICADA,
            dictamen=record.dictamen or "",
            dias_restantes=record.dias_restantes or 0,
            modelo_ia=record.modelo_ia,
            creado_en=record.creado_en,
        )