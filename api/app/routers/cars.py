from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models import Car, User
from app.schemas.common import Page, Plate, decode_cursor, encode_cursor
from app.schemas.user import CarCreate, CarOut, UserOut
from app.services.authorization import resolve_plate

router = APIRouter(prefix="/cars", tags=["cars"])


@router.get("", response_model=Page[CarOut])
async def list_cars(
    db: DbSession,
    _: CurrentUser,
    user_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> Page[CarOut]:
    stmt = select(Car).order_by(Car.id)
    if user_id is not None:
        stmt = stmt.where(Car.user_id == user_id)

    after = decode_cursor(cursor)
    if after is not None:
        stmt = stmt.where(Car.id > after)

    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]

    return Page[CarOut](
        items=[CarOut.model_validate(c) for c in items],
        next_cursor=encode_cursor(items[-1].id) if has_more and items else None,
    )


@router.post("", response_model=CarOut, status_code=status.HTTP_201_CREATED)
async def create_car(body: CarCreate, db: DbSession, _: AdminUser) -> CarOut:
    if await db.get(User, body.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    car = Car(plate=body.plate, user_id=body.user_id)
    db.add(car)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"La placa {body.plate} ya está registrada"
        ) from None

    await db.refresh(car)
    return CarOut.model_validate(car)


@router.patch("/{car_id}", response_model=CarOut)
async def update_car(car_id: int, body: CarCreate, db: DbSession, _: AdminUser) -> CarOut:
    car = await db.get(Car, car_id)
    if car is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Placa no encontrada")

    car.plate = body.plate
    car.user_id = body.user_id
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa placa ya está registrada") from None

    await db.refresh(car)
    return CarOut.model_validate(car)


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_car(car_id: int, db: DbSession, _: AdminUser) -> None:
    car = await db.get(Car, car_id)
    if car is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Placa no encontrada")
    await db.delete(car)
    await db.commit()


@router.get("/by-plate/{plate}")
async def check_plate(plate: Plate, db: DbSession, _: CurrentUser) -> dict:
    """Consulta de autorización. En el legacy era un POST, siendo una lectura."""
    authorized, owner = await resolve_plate(db, plate)
    return {
        "authorized": authorized,
        "user": UserOut.model_validate(owner).model_dump(mode="json") if owner else None,
    }
