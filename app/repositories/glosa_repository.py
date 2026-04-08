from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.db import GlosaRecord
from app.models.schemas import AnalyticsResult


class GlosaRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(
        self,
        eps: str,
        paciente: str,
        codigo_glosa: str,
        valor_objetado: float,
        valor_aceptado: float,
        etapa: str,
        estado: str,
        dictamen: str,
        dias_restantes: int,
        modelo_ia: Optional[str] = None,
        request_id: Optional[str] = None,
        workflow_state: Optional[str] = "RADICADA",
        score: Optional[float] = 0.0,
        prioridad: Optional[str] = "BAJA",
    ) -> GlosaRecord:
        record = GlosaRecord(
            eps=eps,
            paciente=paciente,
            codigo_glosa=codigo_glosa,
            valor_objetado=valor_objetado,
            valor_aceptado=valor_aceptado,
            etapa=etapa,
            estado=estado,
            dictamen=dictamen,
            dias_restantes=dias_restantes,
            modelo_ia=modelo_ia,
            request_id=request_id,
            workflow_state=workflow_state,
            score=score,
            prioridad=prioridad,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def listar(self, limit: int = 50, eps: Optional[str] = None) -> list[GlosaRecord]:
        q = self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc())
        if eps:
            q = q.filter(GlosaRecord.eps == eps.upper())
        return q.limit(limit).all()

    def listar_paginado(self, page: int = 1, per_page: int = 20, eps: Optional[str] = None, 
                        estado: Optional[str] = None, search: Optional[str] = None) -> dict:
        """Lista glosas con paginación y filtros"""
        q = self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc())
        
        if eps:
            q = q.filter(GlosaRecord.eps == eps.upper())
        if estado:
            q = q.filter(GlosaRecord.estado == estado.upper())
        if search:
            q = q.filter(
                (GlosaRecord.paciente.ilike(f'%{search}%')) |
                (GlosaRecord.eps.ilike(f'%{search}%')) |
                (GlosaRecord.codigo_glosa.ilike(f'%{search}%'))
            )
        
        # Total sin filtros para paginación
        total = q.count()
        
        # Aplicar paginación
        offset = (page - 1) * per_page
        items = q.offset(offset).limit(per_page).all()
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }

    def obtener_por_id(self, glosa_id: int) -> Optional[GlosaRecord]:
        return self.db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()

    def alertas_proximas(self, dias_limite: int = 5) -> list[GlosaRecord]:
        return (
            self.db.query(GlosaRecord)
            .filter(
                GlosaRecord.dias_restantes <= dias_limite,
                GlosaRecord.dias_restantes > 0,
                GlosaRecord.estado != "LEVANTADA",
            )
            .order_by(GlosaRecord.dias_restantes.asc())
            .all()
        )

    def analytics(self) -> AnalyticsResult:
        stats = self.db.query(
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        ).first()

        total = stats[0] or 0
        v_objetado = float(stats[1] or 0)
        v_aceptado = float(stats[2] or 0)
        v_recuperado = v_objetado - v_aceptado

        return AnalyticsResult(
            glosas_mes=total,
            valor_objetado_mes=v_objetado,
            valor_recuperado_mes=v_recuperado,
            tasa_exito_pct=round((v_recuperado / v_objetado * 100) if v_objetado > 0 else 0, 1),
        )

    def metrics(self) -> dict:
        by_eps = self.db.query(
            GlosaRecord.eps,
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        ).group_by(GlosaRecord.eps).all()

        by_estado = self.db.query(
            GlosaRecord.estado,
            func.count(GlosaRecord.id),
        ).group_by(GlosaRecord.estado).all()

        # Métricas por tipo de glosa (basado en prefijo del código)
        from sqlalchemy import case
        tipo_cases = case(
            (GlosaRecord.codigo_glosa.like('TA%'), 'TARIFA'),
            (GlosaRecord.codigo_glosa.like('SO%'), 'SOPORTES'),
            (GlosaRecord.codigo_glosa.like('AU%'), 'AUTORIZACION'),
            (GlosaRecord.codigo_glosa.like('CO%'), 'COBERTURA'),
            (GlosaRecord.codigo_glosa.like('PE%'), 'PERTINENCIA'),
            (GlosaRecord.codigo_glosa.like('FA%'), 'FACTURACION'),
            (GlosaRecord.codigo_glosa.like('IN%'), 'INSUMOS'),
            (GlosaRecord.codigo_glosa.like('ME%'), 'MEDICAMENTOS'),
            else_='OTROS'
        )
        
        by_tipo = self.db.query(
            tipo_cases.label('tipo'),
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
        ).group_by(tipo_cases).all()

        return {
            "by_eps": [{"eps": r[0], "count": r[1], "obj": float(r[2] or 0), "acept": float(r[3] or 0)} for r in by_eps],
            "by_estado": [{"estado": r[0], "count": r[1]} for r in by_estado],
            "by_tipo": [{"tipo": r[0], "count": r[1], "obj": float(r[2] or 0)} for r in by_tipo],
        }

    def tendencias_mensuales(self, meses: int = 6) -> list:
        """Obtiene tendencias de los últimos N meses"""
        from datetime import datetime, timedelta
        desde = datetime.now() - timedelta(days=meses * 30)
        
        resultados = self.db.query(
            func.extract('year', GlosaRecord.creado_en).label('year'),
            func.extract('month', GlosaRecord.creado_en).label('month'),
            func.count(GlosaRecord.id).label('count'),
            func.sum(GlosaRecord.valor_objetado).label('obj'),
            func.sum(GlosaRecord.valor_aceptado).label('acept'),
        ).filter(
            GlosaRecord.creado_en >= desde
        ).group_by(
            func.extract('year', GlosaRecord.creado_en),
            func.extract('month', GlosaRecord.creado_en)
        ).order_by('year', 'month').all()
        
        return [
            {
                "mes": f"{int(r.year)}-{int(r.month):02d}",
                "count": r.count,
                "objetado": float(r.obj or 0),
                "aceptado": float(r.acept or 0),
                "recuperado": float((r.obj or 0) - (r.acept or 0))
            }
            for r in resultados
        ]

    def top_glosas(self, limit: int = 10) -> list:
        """Top glosas por valor objetado"""
        resultados = self.db.query(GlosaRecord).order_by(
            GlosaRecord.valor_objetado.desc()
        ).limit(limit).all()
        
        return [
            {
                "id": r.id,
                "eps": r.eps,
                "paciente": r.paciente,
                "codigo": r.codigo_glosa,
                "valor": r.valor_objetado,
                "estado": r.estado,
                "creado": r.creado_en.isoformat() if r.creado_en else None
            }
            for r in resultados
        ]

    def actualizar_estado(self, glosa_id: int, nuevo_estado: str, responsable: str = None) -> Optional[GlosaRecord]:
        glosa = self.obtener_por_id(glosa_id)
        if glosa:
            glosa.estado = nuevo_estado
            if responsable:
                glosa.responsable = responsable
            self.db.commit()
            self.db.refresh(glosa)
        return glosa

    def listar_todos(self) -> list[GlosaRecord]:
        return self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).all()
