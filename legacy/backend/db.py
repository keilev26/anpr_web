import sqlite3
from datetime import datetime

import click
from flask import current_app, g

import pymysql
from urllib.parse import urlparse
from datetime import datetime
from pymysql.constants import CLIENT


def get_db():
    if 'db' not in g:
        url = urlparse(current_app.config['DATABASE_URL'])
        g.db = pymysql.connect(
            host=url.hostname, user="avnadmin", password=url.password,
            db=url.path.lstrip('/'), port=url.port or 21752,
            cursorclass=pymysql.cursors.DictCursor, ssl={"ssl": {}},
            client_flag=CLIENT.MULTI_STATEMENTS  # Habilita múltiples sentencias en un execute()

        )
    return g.db
def check_db():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            for t in tables:
                table_name=list(t.values())[0]
                click.echo(f"-{table_name}")
    except pymysql.MySQLError as e:
        print(f"Database connection error: {e}")
        return False
    return True

def init_db():
    db = get_db()

    with current_app.open_resource("schema.sql") as f:
        sql = f.read().decode("utf-8")

    with db.cursor() as cur:
        cur.execute(sql)
        while cur.nextset():
            pass
    db.commit()

@click.command('check-db')
def check_db_command():
    """Check the database connection."""
    if check_db():
        click.echo('Database connection is healthy.')
    else:
        click.echo('Database connection failed.')

@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')


sqlite3.register_converter(
    "timestamp", lambda v: datetime.fromisoformat(v.decode())
)

def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)