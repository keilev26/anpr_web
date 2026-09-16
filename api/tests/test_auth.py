from tests.conftest import TEST_PASSWORD


async def test_login_correcto_devuelve_token_y_cookie(client):
    r = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "administrator"
    assert "anpr_refresh" in r.cookies


async def test_cookie_de_refresh_es_httponly(client):
    r = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie, "un XSS podría robar la sesión sin HttpOnly"


async def test_password_incorrecta_da_401(client):
    r = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": "mala"})
    assert r.status_code == 401


async def test_usuario_inexistente_da_el_mismo_error(client):
    """No debe permitir enumerar correos registrados."""
    r1 = await client.post("/auth/login", json={"email": "nadie@uni.pe", "password": "x"})
    r2 = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": "x"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


async def test_usuario_inactivo_no_entra(client):
    r = await client.post("/auth/login", json={"email": "baja@uni.pe", "password": TEST_PASSWORD})
    assert r.status_code == 401


async def test_sin_token_no_se_accede(client):
    assert (await client.get("/users")).status_code == 401
    assert (await client.get("/events")).status_code == 401
    assert (await client.get("/auth/me")).status_code == 401


async def test_token_invalido_da_401(client):
    r = await client.get("/users", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401


async def test_refresh_token_no_sirve_como_access_token(client):
    """Si sirviera, la sesión duraría 14 días en vez de 15 minutos."""
    login = await client.post(
        "/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD}
    )
    refresh = login.cookies["anpr_refresh"]
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


async def test_refresh_renueva_la_sesion(client):
    await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    r = await client.post("/auth/refresh")
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_me_devuelve_al_autenticado(client, admin_headers):
    r = await client.get("/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "admin@uni.pe"


async def test_cookie_de_refresh_tiene_path_raiz(client):
    """
    El frontend llama a la API bajo un prefijo (/api/auth/refresh). Con
    Path=/auth el navegador nunca enviaría la cookie y la sesión se perdería
    en cada recarga.
    """
    r = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    cookie = r.headers["set-cookie"]
    assert "Path=/;" in cookie or cookie.rstrip().endswith("Path=/"), cookie


# ---------- bloqueo por fuerza bruta ----------


async def _fallar(client, email, veces):
    for _ in range(veces):
        r = await client.post("/auth/login", json={"email": email, "password": "mala-clave"})
    return r


async def test_bloquea_tras_cinco_fallos_incluso_con_la_clave_correcta(client):
    r = await _fallar(client, "admin@uni.pe", 5)
    assert r.status_code == 401
    r = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


async def test_correo_inexistente_se_bloquea_igual(client):
    """Si solo se bloquearan correos registrados, el 429 los delataría."""
    await _fallar(client, "nadie@uni.pe", 5)
    r = await client.post("/auth/login", json={"email": "nadie@uni.pe", "password": "x"})
    assert r.status_code == 429


async def test_login_correcto_reinicia_el_contador(client):
    await _fallar(client, "admin@uni.pe", 4)
    ok = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    assert ok.status_code == 200
    r = await _fallar(client, "admin@uni.pe", 4)
    assert r.status_code == 401


async def test_el_bloqueo_vence(client, session_factory):
    from datetime import timedelta

    from app.db.models import LoginAttempt, utcnow

    await _fallar(client, "admin@uni.pe", 5)
    async with session_factory() as s:
        attempt = await s.get(LoginAttempt, "admin@uni.pe")
        attempt.locked_until = utcnow() - timedelta(seconds=1)
        await s.commit()
    r = await client.post("/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD})
    assert r.status_code == 200


async def test_bloqueo_de_un_correo_no_afecta_a_otro(client):
    await _fallar(client, "admin@uni.pe", 5)
    r = await client.post(
        "/auth/login", json={"email": "docente@uni.pe", "password": TEST_PASSWORD}
    )
    assert r.status_code == 200
