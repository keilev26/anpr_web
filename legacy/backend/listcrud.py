from flask import Blueprint, request, jsonify
from .db import get_db
import pymysql  # para capturar excepciones específicas
import requests
from .mqqt import publish_authorization
bp = Blueprint('list', __name__)
@bp.route('/cars', methods=['GET'])
def list_cars():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id, plate, user_id FROM list_car;")
        cars = cur.fetchall()
    return jsonify(cars), 200
    
@bp.route('/cars/<int:car_id>', methods=['GET', 'PUT','DELETE'])
def manage_cars(car_id):
    conn = get_db()

    if request.method == 'GET':
        with conn.cursor() as cur:
            cur.execute("SELECT id, plate, user_id FROM list_car WHERE id = %s;", (car_id,))
            car = cur.fetchone()
        if car is None:
            return jsonify({"error": "Car not found."}), 404
        return jsonify(car), 200

    elif request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        plate = data.get('plate')
        user_id = data.get('user_id')

        if not plate or not user_id:
            return jsonify({"error": "Plate and user_id are required."}), 400

        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE list_car SET plate = %s, user_id = %s WHERE id = %s;", (plate, user_id, car_id))
            conn.commit()
        except Exception as e:  
            return jsonify({"error": "DB update failed"}), 500

        return jsonify({"message": "Car updated", "id": car_id, "plate": plate, "user_id": user_id}), 200

    elif request.method == 'DELETE':
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM list_car WHERE id = %s;", (car_id,))
            conn.commit()
        except Exception as e:  
            return jsonify({"error": "DB delete failed"}), 500

        return jsonify({"message": "Car deleted", "id": car_id}), 200

@bp.route('/cars', methods=['POST'])
def create_car():
    conn = get_db()
    data = request.get_json(silent=True) or {}
    plate = data.get('plate')
    user_id = data.get('user_id')

    if not plate or not user_id:
        return jsonify({"error": "Plate and user_id are required."}), 400

    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO list_car (plate, user_id) VALUES (%s, %s);", (plate, user_id))
            car_id = cur.lastrowid
        conn.commit()
    except pymysql.err.IntegrityError:
        return jsonify({"error": "Duplicate or integrity constraint"}), 409
    except Exception as e:  
        return jsonify({"error": "DB insert failed"}), 500

    return jsonify({"message": "Car created", "id": car_id, "plate": plate, "user_id": user_id}), 201

@bp.route('/users', methods=['POST'])
def create_user():
    conn = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    phone = data.get('phone')
    email = data.get('email')

    if not name or not phone or not email:
        return jsonify({"error": "Name, phone, and email are required."}), 400

    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO user (name, phone, email) VALUES (%s, %s, %s);", (name, phone, email))
            user_id = cur.lastrowid
        conn.commit()
    except pymysql.err.IntegrityError:
        return jsonify({"error": "Duplicate or integrity constraint"}), 409
    except Exception as e:  
        return jsonify({"error": "DB insert failed"}), 500

    return jsonify({"message": "User created", "id": user_id, "name": name, "phone": phone, "email": email}), 201
@bp.route('/users', methods=['GET'])
def list_users():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, phone, email FROM user;")
        users = cur.fetchall()
    return jsonify(users), 200
@bp.route('/users/<int:user_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_users(user_id):
    conn = get_db()

    if request.method == 'GET':
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, phone, email FROM user WHERE id = %s;", (user_id,))
            user = cur.fetchone()
        if user is None:
            return jsonify({"error": "User not found."}), 404
        return jsonify(user), 200

    elif request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        phone = data.get('phone')
        email = data.get('email')

        if not name or not phone or not email:
            return jsonify({"error": "Name, phone, and email are required."}), 400

        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE user SET name = %s, phone = %s, email = %s WHERE id = %s;", (name, phone, email, user_id))
            conn.commit()
        except Exception as e:  
            return jsonify({"error": "DB update failed"}), 500

        return jsonify({"message": "User updated", "id": user_id, "name": name, "phone": phone, "email": email}), 200

    elif request.method == 'DELETE':
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user WHERE id = %s;", (user_id,))
            conn.commit()
        except Exception as e:  
            return jsonify({"error": "DB delete failed"}), 500

        return jsonify({"message": "User deleted", "id": user_id}), 200


@bp.route('/getlist', methods=['GET'])
def view_list():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT lc.id, u.name, u.phone, u.email, u.role, lc.plate FROM list_car lc JOIN user u ON lc.user_id = u.id;")
        cars = cur.fetchall()
    return jsonify(cars), 200