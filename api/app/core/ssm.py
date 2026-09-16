"""
Carga de secretos desde SSM Parameter Store al arrancar el Lambda.

Los secretos no van en las variables de entorno del Lambda ni en el estado de
Terraform (que los guarda en texto plano): Terraform crea los parámetros con un
valor de relleno y se rellenan a mano con `aws ssm put-parameter`.
"""

import os
from typing import Any


def load_parameters_into_env(prefix: str, client: Any = None) -> list[str]:
    """
    Copia cada parámetro bajo `prefix` a una variable de entorno.

    `/anpr/prueba/database_url` -> `DATABASE_URL`. Una variable que ya existe NO se
    sobrescribe: el entorno explícito manda, lo que permite pruebas locales.
    Devuelve los nombres cargados (nunca los valores).
    """
    if client is None:
        import boto3  # incluido en el runtime de Lambda

        client = boto3.client("ssm")

    base = prefix.rstrip("/") + "/"
    cargados: list[str] = []
    kwargs = {"Path": base, "WithDecryption": True, "Recursive": False}
    while True:
        resp = client.get_parameters_by_path(**kwargs)
        for p in resp.get("Parameters", []):
            name = p["Name"][len(base) :].upper()
            if name and name not in os.environ:
                os.environ[name] = p["Value"]
                cargados.append(name)
        token = resp.get("NextToken")
        if not token:
            return cargados
        kwargs["NextToken"] = token
