import { HttpResponse, http, delay } from "msw"
import {
  addCar, addUser, currentUser, emailTaken, events, MOCK_PASSWORD, paginate,
  patchUser, plateTaken, removeCar, removeUser, users,
} from "./data"
import type { Role } from "@/types/api"

const TOKEN = "mock-access-token"
let loggedIn = false

const unauthorized = () =>
  HttpResponse.json({ detail: "No autenticado" }, { status: 401 })

const notFound = (what: string) =>
  HttpResponse.json({ detail: `${what} no encontrado` }, { status: 404 })

const conflict = (detail: string, code: string) =>
  HttpResponse.json({ detail, code }, { status: 409 })

function page(url: URL) {
  return {
    limit: Number(url.searchParams.get("limit") ?? 50),
    cursor: url.searchParams.get("cursor"),
  }
}

export const handlers = [
  http.get("/api/health", () => HttpResponse.json({ status: "ok", db: true })),

  // ---------- auth ----------

  http.post("/api/auth/login", async ({ request }) => {
    const { email, password } = (await request.json()) as {
      email: string; password: string
    }
    await delay(400)
    if (password !== MOCK_PASSWORD) {
      return HttpResponse.json({ detail: "Credenciales inválidas" }, { status: 401 })
    }
    loggedIn = true
    return HttpResponse.json({
      access_token: TOKEN, token_type: "bearer", expires_in: 900,
      user: { ...currentUser, email },
    })
  }),

  http.post("/api/auth/refresh", () =>
    loggedIn
      ? HttpResponse.json({
          access_token: TOKEN, token_type: "bearer", expires_in: 900, user: currentUser,
        })
      : unauthorized(),
  ),

  http.post("/api/auth/logout", () => {
    loggedIn = false
    return new HttpResponse(null, { status: 204 })
  }),

  http.get("/api/auth/me", () =>
    loggedIn ? HttpResponse.json(currentUser) : unauthorized(),
  ),

  // ---------- events ----------

  http.get("/api/events", async ({ request }) => {
    if (!loggedIn) return unauthorized()
    const url = new URL(request.url)
    const plate = url.searchParams.get("plate")?.toUpperCase()
    const authorized = url.searchParams.get("authorized")
    const { limit, cursor } = page(url)

    await delay(cursor ? 350 : 250) // páginas siguientes algo más lentas, como en red real

    let items = events
    if (plate) items = items.filter((e) => e.plate.includes(plate))
    if (authorized !== null) {
      items = items.filter((e) => e.authorized === (authorized === "true"))
    }
    return HttpResponse.json(paginate(items, limit, cursor))
  }),

  // ---------- users ----------

  http.get("/api/users", async ({ request }) => {
    if (!loggedIn) return unauthorized()
    const url = new URL(request.url)
    const q = url.searchParams.get("q")?.toLowerCase()
    const role = url.searchParams.get("role")
    const { limit, cursor } = page(url)

    await delay(cursor ? 350 : 250)

    let items = users
    if (q) {
      items = items.filter((u) =>
        [u.name, u.email, u.phone ?? "", ...u.cars.map((c) => c.plate)]
          .join(" ").toLowerCase().includes(q),
      )
    }
    if (role) items = items.filter((u) => u.role === role)
    return HttpResponse.json(paginate(items, limit, cursor))
  }),

  http.post("/api/users", async ({ request }) => {
    if (!loggedIn) return unauthorized()
    const body = (await request.json()) as {
      name: string; email: string; phone?: string; role: Role; plates?: string[]
    }
    await delay(400)

    if (emailTaken(body.email)) {
      return conflict("Ese correo ya está registrado", "EMAIL_ALREADY_REGISTERED")
    }
    const dup = (body.plates ?? []).find((p) => plateTaken(p))
    if (dup) {
      return conflict(`La placa ${dup} ya está registrada`, "PLATE_ALREADY_REGISTERED")
    }
    return HttpResponse.json(addUser(body), { status: 201 })
  }),

  http.get("/api/users/:id", ({ params }) => {
    if (!loggedIn) return unauthorized()
    const u = users.find((x) => x.id === Number(params.id))
    return u ? HttpResponse.json(u) : notFound("Usuario")
  }),

  http.patch("/api/users/:id", async ({ params, request }) => {
    if (!loggedIn) return unauthorized()
    const id = Number(params.id)
    const patch = (await request.json()) as Record<string, unknown>
    await delay(400)

    if (typeof patch.email === "string" && emailTaken(patch.email, id)) {
      return conflict("Ese correo ya está registrado", "EMAIL_ALREADY_REGISTERED")
    }
    const updated = patchUser(id, patch)
    return updated ? HttpResponse.json(updated) : notFound("Usuario")
  }),

  http.delete("/api/users/:id", async ({ params }) => {
    if (!loggedIn) return unauthorized()
    await delay(300)
    return removeUser(Number(params.id))
      ? new HttpResponse(null, { status: 204 })
      : notFound("Usuario")
  }),

  // ---------- cars ----------

  http.post("/api/cars", async ({ request }) => {
    if (!loggedIn) return unauthorized()
    const { plate, user_id } = (await request.json()) as { plate: string; user_id: number }
    await delay(300)

    if (plateTaken(plate)) {
      return conflict(`La placa ${plate} ya está registrada`, "PLATE_ALREADY_REGISTERED")
    }
    const car = addCar(plate, user_id)
    return car ? HttpResponse.json(car, { status: 201 }) : notFound("Usuario")
  }),

  http.delete("/api/cars/:id", async ({ params }) => {
    if (!loggedIn) return unauthorized()
    await delay(300)
    return removeCar(Number(params.id))
      ? new HttpResponse(null, { status: 204 })
      : notFound("Placa")
  }),
]
