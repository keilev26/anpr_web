"""
Crea el primer administrador.

Problema de arranque: POST /users exige rol administrativo, así que con la base
vacía nadie podría crear al primero. Este script es la única vía de entrada, y
se ejecuta una sola vez tras aplicar las migraciones.

    python scripts/seed.py --email admin@uni.pe --name "Nombre Apellido"
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Role, User
from app.db.session import SessionLocal, engine


async def main() -> int:
    ap = argparse.ArgumentParser(description="Crea el administrador inicial")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--phone", default=None)
    args = ap.parse_args()

    password = getpass.getpass("Contraseña: ")
    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repetir contraseña: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1

    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == args.email))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"Ya existe un usuario con {args.email}.", file=sys.stderr)
            return 1

        db.add(User(
            name=args.name,
            email=args.email,
            phone=args.phone,
            role=Role.administrator,
            is_active=True,
            password_hash=hash_password(password),
        ))
        await db.commit()

    await engine.dispose()
    print(f"Administrador creado: {args.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
