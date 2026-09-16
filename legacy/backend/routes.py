# routes.py
from flask import Blueprint, request, jsonify
from .connect import execute_query

bp = Blueprint('main', __name__)

@bp.route('/')
def hello():
    return 'Hello, World!'

@bp.route('/users', methods=['GET'])
def get_users():
    users = execute_query("SELECT id, email FROM users", fetch=True)
    return jsonify(users)
