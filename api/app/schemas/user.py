from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import Role
from app.schemas.common import Plate, UtcDatetime


class CarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate: str
    user_id: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None = None
    email: EmailStr
    role: Role
    is_active: bool
    created_at: UtcDatetime | None = None


class UserWithCars(UserOut):
    cars: list[CarOut] = []


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr
    role: Role = Role.student
    plates: list[Plate] = []
    password: str | None = Field(default=None, min_length=8)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None


class CarCreate(BaseModel):
    plate: Plate
    user_id: int
