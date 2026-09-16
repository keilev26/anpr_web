from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT = "cambiar-esto-en-produccion-o-la-api-se-niega-a-arrancar"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./anpr.db"
    secret_key: str = INSECURE_DEFAULT
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cors_origins: str = "http://localhost:3000"
    device_api_key: str = ""
    dev_mode: bool = True

    max_page_limit: int = Field(default=200, description="Tope de `limit`, igual que el contrato")

    # --- Despliegue en AWS (vacíos en desarrollo local) ---

    db_ssl_ca: str = ""
    """Certificado PEM de la CA de la base de datos. Aiven exige TLS con su propia CA."""

    db_pool_size: int = 1
    """Conexiones que el pool mantiene abiertas (solo MySQL). En Lambda cada contenedor
    atiende una petición a la vez y Mangum reutiliza el mismo bucle de eventos entre
    invocaciones, así que una conexión basta y ahorra ~0,65 s de handshake TLS."""

    db_pool_recycle: int = 300
    """Segundos antes de reabrir una conexión. Por debajo de los cortes por inactividad
    de Aiven; pool_pre_ping cubre además los cortes imprevistos."""

    login_max_failures: int = 5
    """Intentos fallidos seguidos permitidos por correo antes de bloquearlo."""

    login_lock_minutes: int = 15
    """Duración del bloqueo. Corta a propósito: quien conozca un correo puede
    bloquear esa cuenta a voluntad, y un bloqueo largo lo convertiría en denegación."""

    origin_verify_secret: str = ""
    """Si tiene valor, solo se aceptan peticiones con la cabecera X-Origin-Verify
    igual a este secreto. CloudFront la añade; así la Function URL, que es pública,
    no se puede llamar directamente saltándose CloudFront."""

    infer_function_name: str = ""
    """Lambda de inferencia (F4). Vacío = StubPlateReader (desarrollo y tests)."""

    @field_validator("secret_key")
    @classmethod
    def _reject_default_secret_in_prod(cls, v: str, info) -> str:
        # Falla al arrancar, no en la primera petición: un despliegue con la
        # clave de ejemplo permitiría falsificar cualquier token.
        if v == INSECURE_DEFAULT and not info.data.get("dev_mode", True):
            raise ValueError("SECRET_KEY debe cambiarse cuando DEV_MODE=false")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
