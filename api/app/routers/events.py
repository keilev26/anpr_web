from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.db.models import EventDetection, Role, User
from app.schemas.common import Page, decode_cursor, encode_cursor
from app.schemas.event import EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=Page[EventOut])
async def list_events(
    db: DbSession,
    _: CurrentUser,
    plate: str | None = None,
    authorized: bool | None = None,
    role: Role | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> Page[EventOut]:
    """
    Historial paginado. Los filtros se resuelven en SQL: el legacy devolvía la
    tabla `event_detection` entera ordenada por id y filtraba en el navegador.
    """
    stmt = select(EventDetection).order_by(EventDetection.id.desc())

    if plate:
        stmt = stmt.where(EventDetection.plate.ilike(f"%{plate.upper()}%"))
    if authorized is not None:
        stmt = stmt.where(EventDetection.authorized.is_(authorized))
    if role is not None:
        stmt = stmt.where(
            EventDetection.user_id.in_(select(User.id).where(User.role == role))
        )
    if from_ is not None:
        stmt = stmt.where(EventDetection.detected_at >= from_)
    if to is not None:
        stmt = stmt.where(EventDetection.detected_at <= to)

    # Orden descendente: la página siguiente son los ids MENORES que el cursor.
    after = decode_cursor(cursor)
    if after is not None:
        stmt = stmt.where(EventDetection.id < after)

    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]

    return Page[EventOut](
        items=[EventOut.model_validate(e) for e in items],
        next_cursor=encode_cursor(items[-1].id) if has_more and items else None,
    )


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: int, db: DbSession, _: CurrentUser) -> EventOut:
    event = await db.get(EventDetection, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento no encontrado")
    return EventOut.model_validate(event)
