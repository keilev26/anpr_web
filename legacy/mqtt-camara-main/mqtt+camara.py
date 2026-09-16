#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import time
import socket
import sys
import re
import cv2
import numpy as np
import requests
import torch
from paho.mqtt import client as mqtt
from ultralytics import YOLO
from paddleocr import PaddleOCR

# =======================
# 1. Configuración General
# =======================

# --- Configuración MQTT ---
MQTT_BROKER   = os.environ.get("MQTT_HOST", "10.95.239.139")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC_IN      = os.environ.get("TOPIC_CMD_PC", "app/rx")
TOPIC_ACK     = os.environ.get("TOPIC_ACK_PC", "ack/pc")
RUN_TOKEN     = os.environ.get("RUN_TOKEN", "entro")
CID           = f"pc-alpr-{socket.gethostname()}"

# --- Configuración ALPR / Cámara ---
API_URL             = "http://172.18.197.173:5000/v1/event"
CAMERA_RPC          = "http://192.168.122.1:10000/sony/camera"
CAM_TIMEOUT         = 10
DETECTION_TIMEOUT_S = 30
CONF_THRESH         = 0.30
PLATE_PATTERN       = re.compile(r'^[A-Z][A-Z0-9]{2}-\d{3}$')

# =======================
# 2. Inicialización de Modelos y Sesiones
# =======================
print("[INIT] Cargando modelos de IA (esto puede tardar un poco)...")

# Configuración de Hardware
device = 0 if torch.cuda.is_available() else 'cpu'

# Sesiones HTTP (Reutilizables para velocidad)
api_session = requests.Session()
cam_session = requests.Session()

# Carga de Modelos (Solo una vez)
try:
    model = YOLO("best.pt")
    # CORREGIDO: Eliminado show_log y usando paddlex_config como pediste
    ocr = PaddleOCR(paddlex_config="ocr_config.yaml") 
except Exception as e:
    print(f"[ERROR] Fallo al cargar modelos: {e}")
    sys.exit(1)

# Bandera para evitar ejecuciones simultáneas
is_processing = False

print(f"[INIT] Modelos cargados en {device}. Listo para conectar MQTT.")

# =======================
# 3. Clases y Funciones de Cámara (Sony)
# =======================

def rpc(method, params=None):
    payload = {"method": method, "params": params or [], "id": 1, "version": "1.0"}
    r = cam_session.post(CAMERA_RPC, json=payload, timeout=CAM_TIMEOUT)
    r.raise_for_status()
    return r.json()

def start_rec_mode():
    try:
        rpc("startRecMode")
        time.sleep(1)
    except:
        pass

def start_liveview_url():
    try:
        return rpc("startLiveviewWithSize", ["M"])["result"][0]
    except:
        return rpc("startLiveview")["result"][0]

class SonyLiveviewReader:
    def __init__(self, url):
        self.url = url
        self.resp = None

    def __enter__(self):
        self.resp = cam_session.get(self.url, stream=True, timeout=CAM_TIMEOUT)
        self.resp.raise_for_status()
        return self

    def __exit__(self, *args):
        if self.resp:
            self.resp.close()

    def frames(self):
        buf = b""
        soi, eoi = b"\xff\xd8", b"\xff\xd9"
        for chunk in self.resp.iter_content(chunk_size=4096):
            if not chunk:
                continue
            buf += chunk
            while True:
                i = buf.find(soi)
                j = buf.find(eoi, i + 2) if i != -1 else -1
                if i != -1 and j != -1:
                    jpg = buf[i:j+2]
                    buf = buf[j+2:]
                    img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        yield img
                else:
                    break

# =======================
# 4. Lógica de Detección y Backend
# =======================

def post_event(plate_text):
    """Envía la placa al backend"""
    try:
        r = api_session.post(API_URL, json={"plate": plate_text}, timeout=5)
        print(f"[POST] '{plate_text}' → Status: {r.status_code}")
        return 200 <= r.status_code < 300
    except Exception as e:
        print(f"[POST ERROR] No se pudo enviar al backend: {e}")
        return False

def run_ocr_logic(plate_img):
    """Procesa la imagen recortada para extraer texto"""
    rgb = cv2.cvtColor(plate_img, cv2.COLOR_BGR2RGB)
    out = ocr.predict(rgb)
    texts = [str(t) for t in out[0].get("rec_texts", [])] if out else []
    
    wl = re.compile(r'^.{7}$')
    candidates = [t.upper().replace(" ", "") for t in texts if wl.fullmatch(t.upper().replace(" ", ""))]
    
    for cand in candidates:
        if PLATE_PATTERN.fullmatch(cand):
            return cand
            
    return candidates[0] if candidates else None

def process_detection_cycle():
    """
    Ciclo principal: Conecta cámara -> Busca placa -> Envía -> Desconecta
    """
    print("\n[PROCESO] Iniciando ciclo de detección...")
    
    start_rec_mode()
    
    try:
        url = start_liveview_url()
        print(f"[CAM] Liveview URL: {url}")
    except Exception as e:
        print(f"[CAM ERROR] No se pudo obtener URL: {e}")
        return "Error Camara"

    start_time = time.time()
    found_plate = False

    try:
        with SonyLiveviewReader(url) as reader:
            for frame in reader.frames():
                
                # 1. Detección de objetos (YOLO)
                results = model.predict(frame, device=device, half=(device==0), imgsz=640, verbose=False)
                
                for r in results:
                    idxs = (r.boxes.cls == 0).nonzero(as_tuple=True)[0]
                    
                    for idx in idxs:
                        conf = float(r.boxes.conf[idx].item())
                        if conf < CONF_THRESH: continue

                        # Coordenadas
                        x1, y1, x2, y2 = map(int, r.boxes.xyxy[idx].tolist())
                        crop = frame[y1:y2, x1:x2]
                        
                        if crop.size == 0: continue

                        # 2. OCR
                        text = run_ocr_logic(crop)
                        
                        if text:
                            print(f"[OCR] Detectado: {text} (conf object={conf:.2f})")
                            
                            # 3. Validación y Envío
                            if PLATE_PATTERN.fullmatch(text):
                                print(f"✅ PLACA VÁLIDA: {text}")
                                success = post_event(text)
                                if success:
                                    found_plate = True
                                    return f"OK: {text}"
                
                # Timeout check
                if time.time() - start_time > DETECTION_TIMEOUT_S:
                    print("⏳ Tiempo agotado. No se detectó placa válida.")
                    return "Timeout"

    except Exception as e:
        print(f"[ERROR CICLO] {e}")
        return f"Error: {str(e)}"

    return "No Detectado"

# =======================
# 5. Configuración MQTT
# =======================

def make_client():
    """Crea el cliente MQTT. Usa el método simple para compatibilidad con versiones antiguas."""
    try:
        # Intenta usar la versión moderna si la librería lo soporta (por si acaso)
        return mqtt.Client(client_id=CID, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        # Si falla (tu caso), usa la versión antigua simple
        return mqtt.Client(client_id=CID)

cli = make_client()


def ack(text):
    cli.publish(TOPIC_ACK, text, qos=0)

def on_connect(c, u, f, rc):
    print(f"[MQTT] Conectado al broker {MQTT_BROKER} (rc={rc})")
    print(f"[MQTT] Suscrito a '{TOPIC_IN}'")
    c.subscribe(TOPIC_IN, qos=1)

def on_message(c, u, msg):
    global is_processing
    
    raw = msg.payload.decode(errors="ignore").strip()
    print(f"[RX] {msg.topic}: {raw}")

    trigger = False
    if raw.lower() == RUN_TOKEN.lower():
        trigger = True
    else:
        try:
            data = json.loads(raw)
            if str(data.get("cmd","")).lower() == RUN_TOKEN.lower():
                trigger = True
        except:
            pass

    if trigger:
        if is_processing:
            print("[WARN] Ya se está procesando una solicitud. Ignorando.")
            ack("busy")
        else:
            is_processing = True
            result_msg = process_detection_cycle()
            ack(result_msg)
            is_processing = False
    else:
        print("[IGNORAR] Token no coincide")

cli.on_connect = on_connect
cli.on_message = on_message

# =======================
# 6. Main Loop
# =======================
if __name__ == "__main__":
    print("--- SISTEMA UNIFICADO MQTT + ALPR ---")
    print(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Esperando comando: '{RUN_TOKEN}'")
    
    try:
        cli.connect(MQTT_BROKER, MQTT_PORT, 60)
        cli.loop_forever()
    except KeyboardInterrupt:
        print("\n[SALIR] Deteniendo sistema...")
    except Exception as e:
        print(f"\n[FATAL] Error de conexión MQTT: {e}")