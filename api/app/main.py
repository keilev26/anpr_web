import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.routers import auth, cars, detections, events, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("anpr")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


settings = get_settings()

app = FastAPI(
    title="ANPR FIM-UNI API",
    version="1.0.0",
    description="Implementa contracts/openapi.yaml. Ver también contracts/db-schema.md.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,  # necesario para la cookie HttpOnly del refresh
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    El legacy tragaba las excepciones: `except Exception as e` devolvía un 500
    genérico y descartaba `e` sin registrarlo, así que un fallo en producción
    no dejaba rastro.
    """
    log.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno del servidor"},
    )


@app.get("/health", tags=["auth"])
async def health() -> dict:
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        log.exception("Healthcheck: la base de datos no responde")
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(cars.router)
app.include_router(events.router)
app.include_router(detections.router)
