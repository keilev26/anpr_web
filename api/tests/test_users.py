async def test_alta_guarda_el_rol(client, admin_headers):
    """El legacy omitía `role` en el INSERT y todos quedaban como 'student'."""
    r = await client.post(
        "/users",
        headers=admin_headers,
        json={"name": "Nuevo Docente", "email": "nuevo@uni.pe",
              "role": "teacher", "plates": ["QRS-111"]},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "teacher"


async def test_alta_normaliza_la_placa(client, admin_headers):
    r = await client.post(
        "/users",
        headers=admin_headers,
        json={"name": "X", "email": "x@uni.pe", "role": "student", "plates": ["qrs222"]},
    )
    assert r.status_code == 201
    assert r.json()["cars"][0]["plate"] == "QRS-222"


async def test_alta_es_transaccional(client, admin_headers):
    """Placa duplicada: no debe quedar el usuario creado a medias."""
    r = await client.post(
        "/users",
        headers=admin_headers,
        json={"name": "Colisión", "email": "colision@uni.pe",
              "role": "student", "plates": ["CUB-604"]},
    )
    assert r.status_code == 409

    listado = await client.get("/users", headers=admin_headers, params={"q": "colision@uni.pe"})
    assert listado.json()["items"] == [], "el usuario quedó huérfano tras fallar la placa"


async def test_email_duplicado_da_409(client, admin_headers):
    r = await client.post(
        "/users", headers=admin_headers,
        json={"name": "Otro", "email": "admin@uni.pe", "role": "student"},
    )
    assert r.status_code == 409


async def test_busqueda_por_placa(client, admin_headers):
    r = await client.get("/users", headers=admin_headers, params={"q": "ABC-123"})
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["email"] == "docente@uni.pe"


async def test_filtro_por_rol(client, admin_headers):
    r = await client.get("/users", headers=admin_headers, params={"role": "teacher"})
    assert [u["role"] for u in r.json()["items"]] == ["teacher"]


async def test_edicion(client, admin_headers, seed):
    r = await client.patch(
        f"/users/{seed['teacher']}", headers=admin_headers,
        json={"name": "Docente Editado", "is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Docente Editado"
    assert r.json()["is_active"] is False


async def test_baja_arrastra_las_placas(client, admin_headers, seed):
    r = await client.delete(f"/users/{seed['teacher']}", headers=admin_headers)
    assert r.status_code == 204
    cars = await client.get("/cars", headers=admin_headers)
    assert "ABC-123" not in [c["plate"] for c in cars.json()["items"]]


async def test_no_puede_eliminarse_a_si_mismo(client, admin_headers, seed):
    r = await client.delete(f"/users/{seed['admin']}", headers=admin_headers)
    assert r.status_code == 400


async def test_no_admin_no_puede_crear_ni_borrar(client, teacher_headers, seed):
    assert (await client.post(
        "/users", headers=teacher_headers,
        json={"name": "Z", "email": "z@uni.pe", "role": "student"},
    )).status_code == 403
    assert (await client.delete(
        f"/users/{seed['inactive']}", headers=teacher_headers
    )).status_code == 403


async def test_no_admin_si_puede_leer(client, teacher_headers):
    assert (await client.get("/users", headers=teacher_headers)).status_code == 200


async def test_paginacion_por_cursor(client, admin_headers):
    # 3 del seed + 22 nuevos = 25
    for i in range(22):
        await client.post(
            "/users", headers=admin_headers,
            json={"name": f"U{i}", "email": f"u{i}@uni.pe", "role": "student"},
        )

    vistos, cursor, paginas = [], None, 0
    while paginas < 10:
        params = {"limit": 10, **({"cursor": cursor} if cursor else {})}
        body = (await client.get("/users", headers=admin_headers, params=params)).json()
        vistos += [u["id"] for u in body["items"]]
        cursor = body["next_cursor"]
        paginas += 1
        if not cursor:
            break

    assert paginas == 3
    assert len(vistos) == 25
    assert len(set(vistos)) == 25, "el cursor devolvió duplicados"
