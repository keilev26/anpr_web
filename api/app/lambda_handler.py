"""
Entrypoint de la API en AWS Lambda, detrás de CloudFront.

CloudFront reenvía `/api/*` a la Function URL conservando el prefijo; Mangum lo
quita (`api_gateway_base_path`) para que las rutas de FastAPI sigan siendo
`/auth/login`, `/users`, etc., igual que en local con el proxy de Vite.
"""

import os

from app.core.ssm import load_parameters_into_env

# ANTES de importar la app: la configuración se lee al importar (get_settings está
# cacheada y el motor de BD se crea a nivel de módulo).
if os.environ.get("SSM_PREFIX"):
    load_parameters_into_env(os.environ["SSM_PREFIX"])

from mangum import Mangum  # noqa: E402

from app.main import app  # noqa: E402

handler = Mangum(app, api_gateway_base_path="/api", lifespan="off")
