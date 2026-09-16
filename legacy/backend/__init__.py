import os
from flask import Flask
from dotenv import load_dotenv
from flask import request, jsonify
import json
load_dotenv()   


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY='dev',  
        DATABASE_URL=os.getenv("DATABASE_URL")
    )
    from . import db
    db.init_app(app)
    
    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import routes
    app.register_blueprint(routes.bp)
    app.cli.add_command(db.check_db_command)
    app.cli.add_command(db.init_db_command)
        

    from . import vehicle
    from . import auth
    app.register_blueprint(auth.bp)
    app.register_blueprint(vehicle.bp,url_prefix='/v1')

    from . import mqqt
    app.register_blueprint(mqqt.bp,url_prefix='/mqqt')

    from . import listcrud
    app.register_blueprint(listcrud.bp,url_prefix='/list')
    
    return app
