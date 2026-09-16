from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.core.security import hash_password
from app.db.models import Car, Role, User
from app.schemas.common import Page, decode_cursor, encode_cursor
from app.schemas.user import UserCreate, UserUpdate, UserWithCars

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserWithCars])
async def list_users(
    db: DbSession,
    _: CurrentUser,
    q: str | None = None,
    role: Role | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> Page[UserWithCars]:
    stmt = select(User).order_by(User.id)

    if q:
        like = f"%{q}%"
        # La búsqueda por placa necesita el subselect: el filtro va en SQL,
        # no sobre un array en memoria como hacía el legacy.
        stmt = stmt.where(
            or_(
                User.name.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
                User.id.in_(select(Car.user_id).where(Car.plate.ilike(like))),
            )
        )
    if role is not None:
        stmt = stmt.where(User.role == role)

    after = decode_cursor(cursor)
    if after is not None:
        stmt = stmt.where(User.id > after)

    # Se pide uno de más para saber si hay página siguiente sin un COUNT extra.
    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]

    return Page[UserWithCars](
        items=[UserWithCars.model_validate(u) for u in items],
        next_cursor=encode_cursor(items[-1].id) if has_more and items else None,
    )


@router.post("", response_model=UserWithCars, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: DbSession, _: AdminUser) -> UserWithCars:
    """
    Alta transaccional: usuario y placas se crean juntos o no se crea nada.

    El legacy encadenaba dos POST desde el proxy de Next y, si el segundo
    fallaba, intentaba un "rollback best-effort" dentro de un catch vacío.
    """
    user = User(
        name=body.name,
        phone=body.phone,
        email=body.email,
        role=body.role,  # el legacy omitía esto y todos quedaban como 'student'
        password_hash=hash_password(body.password) if body.password else None,
    )
    user.cars = [Car(plate=p) for p in body.plates]

    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El correo o alguna placa ya están registrados"
        ) from None

    await db.refresh(user)
    return UserWithCars.model_validate(user)


@router.get("/{user_id}", response_model=UserWithCars)
async def get_user(user_id: int, db: DbSession, _: CurrentUser) -> UserWithCars:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return UserWithCars.model_validate(user)


@router.patch("/{user_id}", response_model=UserWithCars)
async def update_user(
    user_id: int, body: UserUpdate, db: DbSession, _: AdminUser
) -> UserWithCars:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese correo ya está registrado") from None

    await db.refresh(user)
    return UserWithCars.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession, admin: AdminUser) -> None:
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes eliminarte a ti mismo")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    await db.delete(user)  # las placas caen por ON DELETE CASCADE
    await db.commit()
