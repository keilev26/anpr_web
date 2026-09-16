from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Car, User


async def resolve_plate(db: AsyncSession, plate: str) -> tuple[bool, User | None]:
    """
    Regla de acceso, en un solo sitio.

    Autorizado = la placa está en la lista blanca Y su propietario está activo.
    Lo segundo es nuevo: el legacy solo miraba que la placa existiera, así que
    dar de baja a alguien obligaba a borrar sus placas a mano.
    """
    stmt = select(Car).where(Car.plate == plate)
    car = (await db.execute(stmt)).scalar_one_or_none()
    if car is None:
        return False, None

    owner = await db.get(User, car.user_id)
    if owner is None or not owner.is_active:
        return False, owner
    return True, owner
