# connect.py
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

timeout = 10

def get_connection():
    """Crea y devuelve una nueva conexión a la base de datos."""
    return pymysql.connect(
        charset="utf8mb4",
        connect_timeout=timeout,
        cursorclass=pymysql.cursors.DictCursor,
        db=os.getenv("DB_NAME"),
        host=os.getenv("HOST"),
        user="avnadmin",
        password=os.getenv("PASSWORD"),
        port=int(os.getenv("PORT")),
        read_timeout=timeout,
        write_timeout=timeout,
        ssl={"ssl": {}}
    )

def execute_query(query, params=None, fetch=False):
    """
    Ejecuta una consulta SQL en la base de datos Aiven (MySQL).
    - query: cadena SQL (usa %s para los parámetros)
    - params: tupla con los valores
    - fetch: True si se desea retornar resultados (SELECT)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            result = cursor.fetchall() if fetch else None
        conn.commit()
        return result
    except Exception as e:
        print("[ERROR] Error ejecutando query:", e)
        conn.rollback()
        raise
    finally:
        conn.close()
