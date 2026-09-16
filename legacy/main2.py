import requests, cv2, numpy as np

LIVEVIEW_URL = None  # la pondremos tras preguntar a la cámara

# 1) pedir la URL del liveview
def rpc(method):
    url = "http://192.168.122.1:10000/sony/camera"
    payload = {"method": method, "params": [], "id": 1, "version": "1.0"}
    r = requests.post(url, json=payload, timeout=5)
    r.raise_for_status()
    return r.json()

# (opcional) activar modo rec
try:
    rpc("startRecMode","HQ")
except Exception:
    pass  # algunas cámaras ya están listas

resp = rpc("startLiveview")
LIVEVIEW_URL = resp["result"][0]
print("Liveview stream:", LIVEVIEW_URL)

# 2) abrir el stream multipart (MJPEG con “boundary”)
r = requests.get(LIVEVIEW_URL, stream=True, timeout=10)

# Sony envía paquetes con cabeceras + JPEG; buscamos los SOI/EOI
bytes_buf = b""
for chunk in r.iter_content(chunk_size=4096):
    if not chunk:
        continue
    bytes_buf += chunk
    # Buscar inicio y fin de un JPEG
    start = bytes_buf.find(b'\xff\xd8')  # SOI
    end   = bytes_buf.find(b'\xff\xd9')  # EOI
    if start != -1 and end != -1 and end > start:
        jpg = bytes_buf[start:end+2]
        bytes_buf = bytes_buf[end+2:]
        img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        cv2.imshow("AS100V Live", img)
        if cv2.waitKey(1) & 0xFF == 27:  # ESC para salir
            break

cv2.destroyAllWindows()
