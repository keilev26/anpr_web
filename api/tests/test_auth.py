from tests.conftest import TEST_PASSWORD


async def test_login_correcto_devuelve_token_y_cookie(client):
    r = await client.post(
        "/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "administrator"
    assert "anpr_refresh" in r.cookies


async def test_cookie_de_refresh_es_httponly(client):
    r = await client.post(
        "/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD}
    )
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
    r = await client.post(
        "/auth/login", json={"email": "baja@uni.pe", "password": TEST_PASSWORD}
    )
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
    r = await client.post(
        "/auth/login", json={"email": "admin@uni.pe", "password": TEST_PASSWORD}
    )
    cookie = r.headers["set-cookie"]
    assert "Path=/;" in cookie or cookie.rstrip().endswith("Path=/"), cookie
