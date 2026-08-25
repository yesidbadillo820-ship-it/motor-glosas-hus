"""Snippets: los atajos de texto del gestor.

Qué es, en palabras del auditor: usted define `/ratif` y, al escribirlo en
cualquier casilla del portal y pulsar Tab, se convierte en su párrafo de
ratificación completo. Sirve para no volver a pegar a mano los textos que se
repiten treinta veces al día.

20-08-2026 — por qué existe este archivo. La tabla `snippets` estaba creada en
la base de datos con todas sus columnas, y la pantalla «Gestionar mis
snippets» estaba hecha y funcionando. Lo que faltaba era el medio del camino:
el router era un cascarón que devolvía lista vacía y no tenía ni crear, ni
borrar, ni registrar el uso. Así que el botón «Gestionar mis snippets» abría,
usted escribía su atajo, le daba guardar… y salía «Falló».

Se implementa contra el modelo que ya estaba. No se inventó ninguna columna.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.db import SnippetRecord

# Los que puede ver alguien que no es el dueño.
_VISIBILIDADES_COMPARTIDAS = ("EQUIPO", "GLOBAL")
_VISIBILIDADES_VALIDAS = ("PRIVADO", "EQUIPO", "GLOBAL")

MAX_ATAJO = 50
MAX_CONTENIDO = 20_000
MAX_DESCRIPCION = 200


def normalizar_atajo(atajo: str) -> str:
    """El atajo siempre empieza por «/» y va en minúsculas.

    La pantalla expande buscando «/loquesea» en el texto y comparándolo tal
    cual contra el atajo guardado. Si alguien guarda «ratif» sin la barra, el
    snippet queda vivo en la lista pero NO se expande nunca: un atajo muerto
    que parece bueno. Se normaliza al guardar para que eso no pueda pasar.
    """
    limpio = (atajo or "").strip().lower()
    limpio = limpio.lstrip("/")
    limpio = "".join(c for c in limpio if c.isalnum() or c in "-_")
    return f"/{limpio}" if limpio else ""


def como_dict(s: SnippetRecord) -> dict:
    """La forma exacta que la pantalla espera de cada snippet."""
    return {
        "id": s.id,
        "atajo": s.atajo,
        "contenido": s.contenido,
        "descripcion": s.descripcion or "",
        "visibilidad": s.visibilidad or "PRIVADO",
        "uso_count": s.uso_count or 0,
        "es_mio": True,  # lo ajusta el llamador cuando corresponde
    }


def listar(db: Session, email: str) -> list[dict]:
    """Los del usuario, más los que el equipo o la institución comparten.

    Ordenados por uso: los que más usa quedan arriba, que es donde los busca.
    """
    filas = (
        db.query(SnippetRecord)
        .filter(
            or_(
                SnippetRecord.usuario_email == email,
                SnippetRecord.visibilidad.in_(_VISIBILIDADES_COMPARTIDAS),
            )
        )
        .order_by(SnippetRecord.uso_count.desc(), SnippetRecord.atajo.asc())
        .all()
    )
    salida = []
    for s in filas:
        d = como_dict(s)
        d["es_mio"] = s.usuario_email == email
        salida.append(d)
    return salida


def crear(
    db: Session,
    *,
    email: str,
    atajo: str,
    contenido: str,
    descripcion: str = "",
    visibilidad: str = "PRIVADO",
) -> tuple[dict | None, str]:
    """Crea un snippet. Devuelve (snippet, error). Uno de los dos va vacío."""
    atajo_ok = normalizar_atajo(atajo)
    if not atajo_ok or atajo_ok == "/":
        return None, "El atajo no puede estar vacío. Escriba algo como «/ratif»."
    if len(atajo_ok) > MAX_ATAJO:
        return None, f"El atajo no puede pasar de {MAX_ATAJO} caracteres."
    cuerpo = (contenido or "").strip()
    if not cuerpo:
        return None, "El contenido no puede estar vacío."
    if len(cuerpo) > MAX_CONTENIDO:
        return None, "El contenido es demasiado largo."

    vis = (visibilidad or "PRIVADO").strip().upper()
    if vis not in _VISIBILIDADES_VALIDAS:
        vis = "PRIVADO"

    # Un mismo atajo dos veces sería una ruleta: la pantalla expande el
    # primero que encuentra. Mejor decirlo que dejar el azar.
    ya = (
        db.query(SnippetRecord)
        .filter(SnippetRecord.usuario_email == email, SnippetRecord.atajo == atajo_ok)
        .first()
    )
    if ya:
        return None, f"Ya tiene un snippet con el atajo {atajo_ok}."

    fila = SnippetRecord(
        usuario_email=email,
        atajo=atajo_ok,
        contenido=cuerpo,
        descripcion=(descripcion or "").strip()[:MAX_DESCRIPCION] or None,
        visibilidad=vis,
        uso_count=0,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return como_dict(fila), ""


def borrar(db: Session, *, email: str, snippet_id: int) -> tuple[bool, str]:
    """Borra un snippet propio. Los de otros no se tocan."""
    fila = db.query(SnippetRecord).filter(SnippetRecord.id == snippet_id).first()
    if fila is None:
        return False, "Ese snippet ya no existe."
    if fila.usuario_email != email:
        # Un snippet GLOBAL lo ve todo el mundo, pero solo lo borra su dueño.
        return False, "Ese snippet es de otra persona; solo su dueño puede borrarlo."
    db.delete(fila)
    db.commit()
    return True, ""


def registrar_uso(db: Session, *, email: str, snippet_id: int) -> bool:
    """Suma uno al contador de uso. Es lo que ordena la lista.

    Se puede registrar el uso de un snippet compartido aunque no sea propio:
    usarlo es justamente para lo que está.
    """
    fila = db.query(SnippetRecord).filter(SnippetRecord.id == snippet_id).first()
    if fila is None:
        return False
    if fila.usuario_email != email and (fila.visibilidad or "PRIVADO") == "PRIVADO":
        return False
    fila.uso_count = (fila.uso_count or 0) + 1
    fila.ultimo_uso = datetime.now(timezone.utc)
    db.commit()
    return True
