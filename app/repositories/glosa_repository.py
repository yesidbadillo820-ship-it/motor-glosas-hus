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
        numero_radicado: Optional[str] = None,
        factura: Optional[str] = None,
        texto_glosa_original: Optional[str] = None,
        codigo_respuesta: Optional[str] = None,
        cups_servicio: Optional[str] = None,
        servicio_descripcion: Optional[str] = None,
        concepto_glosa: Optional[str] = None,
        fecha_recepcion=None,
        fecha_entrega=None,
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
            numero_radicado=numero_radicado,
            factura=factura,
            texto_glosa_original=texto_glosa_original,
            codigo_respuesta=codigo_respuesta,
            cups_servicio=cups_servicio,
            servicio_descripcion=servicio_descripcion,
            concepto_glosa=concepto_glosa,
            fecha_recepcion=fecha_recepcion,
            fecha_entrega=fecha_entrega,
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

    def listar_paginado(
        self,
        page: int = 1,
        per_page: int = 20,
        eps: Optional[str] = None,
        estado: Optional[str] = None,
        search: Optional[str] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        valor_min: Optional[float] = None,
        valor_max: Optional[float] = None,
        tipo: Optional[str] = None,
        semaforo: Optional[str] = None,
        workflow: Optional[str] = None,
    ) -> dict:
        """Lista glosas con paginación y filtros avanzados."""
        q = self._query_con_filtros(
            eps=eps, estado=estado, search=search,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            valor_min=valor_min, valor_max=valor_max,
            tipo=tipo, semaforo=semaforo, workflow=workflow,
        )

        total = q.count()
        offset = (page - 1) * per_page
        items = q.offset(offset).limit(per_page).all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }

    def _query_con_filtros(
        self,
        eps: Optional[str] = None,
        estado: Optional[str] = None,
        search: Optional[str] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        valor_min: Optional[float] = None,
        valor_max: Optional[float] = None,
        tipo: Optional[str] = None,
        semaforo: Optional[str] = None,
        workflow: Optional[str] = None,
    ):
        from datetime import datetime as _dt
        q = self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc())

        if eps:
            # Soporta múltiples EPS separadas por coma
            eps_list = [e.strip().upper() for e in eps.split(",") if e.strip()]
            if len(eps_list) == 1:
                q = q.filter(GlosaRecord.eps == eps_list[0])
            elif eps_list:
                q = q.filter(GlosaRecord.eps.in_(eps_list))
        if estado:
            q = q.filter(GlosaRecord.estado == estado.upper())
        if semaforo:
            q = q.filter(GlosaRecord.prioridad == semaforo.upper())
        if workflow:
            q = q.filter(GlosaRecord.workflow_state == workflow.upper())
        if tipo:
            # TA, SO, AU, CO, PE, FA, IN, ME, CL
            q = q.filter(GlosaRecord.codigo_glosa.ilike(f"{tipo.upper()}%"))
        if valor_min is not None:
            q = q.filter(GlosaRecord.valor_objetado >= valor_min)
        if valor_max is not None:
            q = q.filter(GlosaRecord.valor_objetado <= valor_max)
        if fecha_desde:
            try:
                d = _dt.fromisoformat(fecha_desde)
                q = q.filter(GlosaRecord.creado_en >= d)
            except ValueError:
                pass
        if fecha_hasta:
            try:
                d = _dt.fromisoformat(fecha_hasta)
                q = q.filter(GlosaRecord.creado_en <= d)
            except ValueError:
                pass
        if search:
            q = q.filter(
                (GlosaRecord.paciente.ilike(f'%{search}%')) |
                (GlosaRecord.eps.ilike(f'%{search}%')) |
                (GlosaRecord.codigo_glosa.ilike(f'%{search}%')) |
                (GlosaRecord.numero_radicado.ilike(f'%{search}%')) |
                (GlosaRecord.factura.ilike(f'%{search}%')) |
                (GlosaRecord.cups_servicio.ilike(f'%{search}%'))
            )
        return q

    def listar_para_export(self, **filtros) -> list[GlosaRecord]:
        """Lista sin paginación, aplicando los mismos filtros que listar_paginado."""
        return self._query_con_filtros(**filtros).limit(5000).all()

    def analitica_predictiva(self, ventana_dias: int = 180) -> dict:
        """Analítica agregada últimos N días:
        - top EPS por valor y cantidad
        - tasa de éxito por código de glosa
        - tasa de éxito por tipo
        - distribución por día de la semana
        - recomendaciones automáticas
        """
        from datetime import datetime, timedelta
        from sqlalchemy import case
        desde = datetime.now() - timedelta(days=ventana_dias)

        # Top EPS glosadoras
        top_eps = (
            self.db.query(
                GlosaRecord.eps,
                func.count(GlosaRecord.id).label("cnt"),
                func.sum(GlosaRecord.valor_objetado).label("obj"),
                func.sum(GlosaRecord.valor_aceptado).label("acept"),
            )
            .filter(GlosaRecord.creado_en >= desde)
            .group_by(GlosaRecord.eps)
            .order_by(func.sum(GlosaRecord.valor_objetado).desc())
            .limit(10)
            .all()
        )
        top_eps_data = []
        for r in top_eps:
            obj = float(r.obj or 0)
            ace = float(r.acept or 0)
            recuperado = obj - ace
            exito = (recuperado / obj * 100) if obj > 0 else 0
            top_eps_data.append({
                "eps": r.eps or "—",
                "glosas": int(r.cnt or 0),
                "objetado": obj,
                "aceptado": ace,
                "recuperado": recuperado,
                "tasa_exito": round(exito, 1),
            })

        # Tasa de éxito por código de glosa (top 15 por volumen)
        por_codigo = (
            self.db.query(
                GlosaRecord.codigo_glosa,
                func.count(GlosaRecord.id).label("cnt"),
                func.sum(GlosaRecord.valor_objetado).label("obj"),
                func.sum(GlosaRecord.valor_aceptado).label("acept"),
            )
            .filter(GlosaRecord.creado_en >= desde)
            .filter(GlosaRecord.codigo_glosa.isnot(None))
            .group_by(GlosaRecord.codigo_glosa)
            .order_by(func.count(GlosaRecord.id).desc())
            .limit(15)
            .all()
        )
        codigos_data = []
        for r in por_codigo:
            obj = float(r.obj or 0)
            ace = float(r.acept or 0)
            rec = obj - ace
            exito = (rec / obj * 100) if obj > 0 else 0
            codigos_data.append({
                "codigo": r.codigo_glosa,
                "glosas": int(r.cnt or 0),
                "objetado": obj,
                "recuperado": rec,
                "tasa_exito": round(exito, 1),
            })

        # Éxito por tipo (prefijo 2 letras)
        tipo_case = case(
            (GlosaRecord.codigo_glosa.like('TA%'), 'TARIFAS'),
            (GlosaRecord.codigo_glosa.like('SO%'), 'SOPORTES'),
            (GlosaRecord.codigo_glosa.like('AU%'), 'AUTORIZACIÓN'),
            (GlosaRecord.codigo_glosa.like('CO%'), 'COBERTURA'),
            (GlosaRecord.codigo_glosa.like('PE%'), 'PERTINENCIA'),
            (GlosaRecord.codigo_glosa.like('FA%'), 'FACTURACIÓN'),
            (GlosaRecord.codigo_glosa.like('IN%'), 'INSUMOS'),
            (GlosaRecord.codigo_glosa.like('ME%'), 'MEDICAMENTOS'),
            (GlosaRecord.codigo_glosa.like('CL%'), 'CLÍNICO'),
            else_='OTROS'
        )
        por_tipo = (
            self.db.query(
                tipo_case.label("tipo"),
                func.count(GlosaRecord.id).label("cnt"),
                func.sum(GlosaRecord.valor_objetado).label("obj"),
                func.sum(GlosaRecord.valor_aceptado).label("acept"),
            )
            .filter(GlosaRecord.creado_en >= desde)
            .group_by(tipo_case)
            .all()
        )
        tipos_data = []
        for r in por_tipo:
            obj = float(r.obj or 0)
            ace = float(r.acept or 0)
            rec = obj - ace
            exito = (rec / obj * 100) if obj > 0 else 0
            tipos_data.append({
                "tipo": r.tipo,
                "glosas": int(r.cnt or 0),
                "objetado": obj,
                "recuperado": rec,
                "tasa_exito": round(exito, 1),
            })
        tipos_data.sort(key=lambda x: x["objetado"], reverse=True)

        # Totales de la ventana
        totales_q = self.db.query(
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        ).filter(GlosaRecord.creado_en >= desde).first()
        total_cnt = int(totales_q[0] or 0)
        total_obj = float(totales_q[1] or 0)
        total_ace = float(totales_q[2] or 0)
        total_rec = total_obj - total_ace
        tasa_global = round((total_rec / total_obj * 100) if total_obj > 0 else 0, 1)

        # Recomendaciones automáticas (simples)
        recomendaciones = []
        if top_eps_data:
            peor = min(top_eps_data, key=lambda x: x["tasa_exito"])
            if peor["tasa_exito"] < 50 and peor["glosas"] >= 3:
                recomendaciones.append(
                    f"Baja tasa de éxito con {peor['eps']} ({peor['tasa_exito']}%). "
                    "Revisar plantillas y contrato vigente."
                )
            mayor = top_eps_data[0]
            recomendaciones.append(
                f"{mayor['eps']} concentra ${mayor['objetado']:,.0f} objetados "
                f"({mayor['glosas']} glosas). Priorizar gestor senior."
            )
        if codigos_data:
            codigo_critico = min(
                [c for c in codigos_data if c["glosas"] >= 3] or codigos_data,
                key=lambda x: x["tasa_exito"]
            )
            if codigo_critico["tasa_exito"] < 50:
                recomendaciones.append(
                    f"Código {codigo_critico['codigo']}: tasa {codigo_critico['tasa_exito']}% "
                    f"en {codigo_critico['glosas']} casos. Reforzar argumentación."
                )
        if tipos_data:
            mejor_tipo = max(tipos_data, key=lambda x: x["tasa_exito"])
            if mejor_tipo["tasa_exito"] > 70 and mejor_tipo["glosas"] >= 3:
                recomendaciones.append(
                    f"Tipo {mejor_tipo['tipo']}: excelente tasa ({mejor_tipo['tasa_exito']}%). "
                    "Mantener flujo actual."
                )
        if total_cnt == 0:
            recomendaciones.append(
                "Sin datos suficientes en la ventana seleccionada. "
                "Amplía el rango o importa más glosas."
            )

        # Distribución día de la semana (0=lunes). SQLite y PostgreSQL
        # no comparten función — iteramos en Python sobre las fechas.
        dias_labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        dias_counts = [0] * 7
        try:
            fechas = (
                self.db.query(GlosaRecord.creado_en)
                .filter(GlosaRecord.creado_en >= desde)
                .all()
            )
            for (f,) in fechas:
                if f:
                    # Python weekday: 0=Monday, 6=Sunday — coincide con dias_labels
                    dias_counts[f.weekday()] += 1
        except Exception:  # nosec - mejor zeros que romper el endpoint
            pass

        return {
            "ventana_dias": ventana_dias,
            "totales": {
                "glosas": total_cnt,
                "objetado": total_obj,
                "aceptado": total_ace,
                "recuperado": total_rec,
                "tasa_exito": tasa_global,
            },
            "top_eps": top_eps_data,
            "por_codigo": codigos_data,
            "por_tipo": tipos_data,
            "por_dia_semana": {"labels": dias_labels, "counts": dias_counts},
            "recomendaciones": recomendaciones,
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
        from datetime import datetime
        from sqlalchemy import extract
        now = datetime.now()
        
        stats = self.db.query(
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        ).filter(
            extract('year', GlosaRecord.creado_en) == now.year,
            extract('month', GlosaRecord.creado_en) == now.month,
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

    def semaforo_counts(self) -> dict:
        """Cuenta glosas agrupadas por color de semáforo (columna prioridad)."""
        resultados = self.db.query(
            GlosaRecord.prioridad,
            func.count(GlosaRecord.id),
        ).filter(
            GlosaRecord.estado.notin_(["LEVANTADA", "CONCILIADA", "ACEPTADA"])
        ).group_by(GlosaRecord.prioridad).all()
        base = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0, "NEGRO": 0}
        for color, cnt in resultados:
            if color in base:
                base[color] = int(cnt or 0)
        return base

    def listar_por_gestor(
        self,
        gestor_email: str,
        gestor_nombre: Optional[str] = None,
        limit: int = 200,
    ) -> list[GlosaRecord]:
        """Glosas asignadas a un gestor.

        Matches, en orden:
        - glosa.auditor_email == gestor_email
        - glosa.gestor_nombre ILIKE '%<nombre del usuario>%'
        - glosa.gestor_nombre ILIKE '%<prefijo-email>%' (fallback)
        """
        from sqlalchemy import or_
        condiciones = [GlosaRecord.auditor_email == gestor_email]
        if gestor_nombre:
            condiciones.append(GlosaRecord.gestor_nombre.ilike(f"%{gestor_nombre.strip()}%"))
        prefijo_email = gestor_email.split("@")[0]
        condiciones.append(GlosaRecord.gestor_nombre.ilike(f"%{prefijo_email}%"))

        return (
            self.db.query(GlosaRecord)
            .filter(or_(*condiciones))
            .order_by(GlosaRecord.dias_restantes.asc())
            .limit(limit)
            .all()
        )
