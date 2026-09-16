from flask import Blueprint, request, jsonify
from .db import get_db
import pymysql  # para capturar excepciones específicas
import requests
from .mqqt import publish_authorization
from datetime import timedelta

bp = Blueprint('vehicle', __name__)


def check_authorization(conn, plate):
    """Devuelve (authorized: bool, car: dict|None)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, plate, user_id FROM list_car WHERE plate = %s;", (plate,))
        car = cur.fetchone()
    return (car is not None, car)

@bp.route('/event', methods=['GET', 'POST'])
def event_vehicle():
    conn = get_db()

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        plate = data.get('plate')

        if not plate:
            return jsonify({"error": "Plate is required."}), 400

        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO event_detection (plate) VALUES (%s);", (plate,))
            conn.commit()
        except pymysql.err.IntegrityError:
            return jsonify({"error": "Duplicate or integrity constraint"}), 409
        except Exception as e:  
            return jsonify({"error": "DB insert failed"}), 500

        authorized, car = check_authorization(conn, plate)
        payload = {"authorized": authorized}
        if authorized:
            payload["car"] = car
        
        ok,info = publish_authorization(plate, authorized) 
        if not ok:
            print("[WARN] MQTT publish failed:", info)


        return jsonify({"message": "created", "plate": plate, "authorization": payload}), 201
    # GET
    with conn.cursor() as cur:
        cur.execute("SELECT e.id, e.plate, e.datetime,(case when l.user_id is not null then 'authorized' else 'unauthorized' end) as authorization, (case when u.id is not null then u.role else 'unknown' end) as type FROM event_detection e left JOIN list_car l ON e.plate = l.plate LEFT JOIN user u ON l.user_id = u.id ORDER BY id DESC;")
        vehicles = cur.fetchall()  # gracias a DictCursor ya es lista de dicts
        for v in vehicles:
            v['datetime'] =  v["datetime"] - timedelta(hours=5)

    return jsonify({"vehicles": vehicles}), 200

@bp.route('/authorization',methods=['POST'])
def authorization_vehicle():
    conn = get_db()
    plate = request.json.get('plate')

    if not plate:
        return jsonify({"error": "Plate is required."}), 400

    with conn.cursor() as cur:
        cur.execute("SELECT id, plate, user_id FROM list_car WHERE plate = %s ;", (plate,))
        car = cur.fetchone()  # gracias a DictCursor ya es dict o None

    if car:
        return jsonify({"authorized": True, "car": car}), 200
    else:
        return jsonify({"authorized": False}), 200