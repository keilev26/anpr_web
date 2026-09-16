import type { AnprEvent, Car, Role, User, UserWithCars } from "@/types/api"

export const MOCK_PASSWORD = "anpr12345"

export const currentUser: User = {
  id: 1,
  name: "Caleb Camargo Saavedra",
  phone: "964136821",
  email: "caleb.camargo.saavedra@uni.pe",
  role: "administrator",
  is_active: true,
  created_at: "2025-01-15T14:00:00Z",
}

let nextUserId = 1
let nextCarId = 1

const NAMES = [
  "María Quispe Rojas", "Luis Fernández Paz", "Ana Torres Vega", "Jorge Mendoza Ríos",
  "Carmen Huamán Soto", "Diego Salazar Núñez", "Rosa Ccahuana Lima", "Pedro Vargas Ruiz",
  "Elena Castro Díaz", "Miguel Ángel Peña", "Sofía Ramírez Cruz", "Andrés Chávez Loayza",
  "Lucía Flores Ibarra", "Raúl Espinoza Mena", "Patricia Aguilar Ponce", "Iván Zegarra Ortiz",
  "Gabriela Ríos Alván", "Marco Antonio Lira", "Verónica Palomino Sáenz", "Héctor Bautista Roca",
]
const ROLES: Role[] = ["student", "teacher", "administrator"]
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

/** Determinista: el mock debe dar el mismo resultado en cada recarga. */
function seededPlate(i: number): string {
  const a = LETTERS[i % 26]!
  const b = LETTERS[(i * 7) % 26]!
  const c = LETTERS[(i * 13) % 26]!
  const n = String(((i * 137) % 900) + 100)
  return `${a}${b}${c}-${n}`
}

function makeUser(i: number): UserWithCars {
  const id = ++nextUserId
  const name = NAMES[i % NAMES.length]!
  const role = ROLES[i % ROLES.length]!
  const slug = name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .split(" ").slice(0, 2).join(".")
  // Algunos usuarios con dos placas, para ejercitar la UI de varias placas.
  const plateCount = i % 5 === 0 ? 2 : 1
  const cars: Car[] = Array.from({ length: plateCount }, (_, k) => ({
    id: ++nextCarId,
    plate: seededPlate(i * 3 + k),
    user_id: id,
  }))
  return {
    id, name, role, cars,
    phone: `9${String(10_000_000 + i * 37_117).slice(0, 8)}`,
    email: `${slug}${i}@uni.pe`,
    is_active: i % 11 !== 0,
    created_at: new Date(Date.UTC(2025, i % 12, (i % 27) + 1, 9, 30)).toISOString(),
  }
}

export const users: UserWithCars[] = [
  { ...currentUser, cars: [{ id: ++nextCarId, plate: "CUB-604", user_id: 1 }] },
  ...Array.from({ length: 37 }, (_, i) => makeUser(i)),
]
nextUserId = Math.max(...users.map((u) => u.id))

/** ~120 eventos repartidos en 5 días, para que la paginación sea visible. */
export const events: AnprEvent[] = Array.from({ length: 120 }, (_, i) => {
  const known = i % 3 !== 0
  const owner = known ? users[i % users.length]! : null
  const plate = owner ? owner.cars[0]!.plate : seededPlate(i + 500)
  const opened = known
  return {
    id: 1000 - i,
    plate,
    detected_at: new Date(Date.now() - i * 61 * 60_000).toISOString(),
    authorized: known,
    confidence: Number((0.70 + ((i * 17) % 30) / 100).toFixed(3)),
    image_url: null,
    gate_opened: opened,
    latency_ms: 1800 + ((i * 53) % 1600),
    camera_id: "puerta-2",
    user: owner,
  }
})

// ---------- Mutaciones ----------

export function addUser(data: {
  name: string; email: string; phone?: string; role: Role; plates?: string[]
}): UserWithCars {
  const id = ++nextUserId
  const cars: Car[] = (data.plates ?? []).map((plate) => ({
    id: ++nextCarId, plate, user_id: id,
  }))
  const user: UserWithCars = {
    id, name: data.name, email: data.email, phone: data.phone ?? null,
    role: data.role, is_active: true,
    created_at: new Date().toISOString(), cars,
  }
  users.unshift(user)
  return user
}

export function patchUser(
  id: number,
  patch: Partial<Pick<User, "name" | "email" | "phone" | "role" | "is_active">>,
): UserWithCars | null {
  const u = users.find((x) => x.id === id)
  if (!u) return null
  Object.assign(u, patch)
  return u
}

export function removeUser(id: number): boolean {
  const i = users.findIndex((u) => u.id === id)
  if (i === -1) return false
  users.splice(i, 1)
  return true
}

export function addCar(plate: string, userId: number): Car | null {
  const u = users.find((x) => x.id === userId)
  if (!u) return null
  const car: Car = { id: ++nextCarId, plate, user_id: userId }
  u.cars.push(car)
  return car
}

export function removeCar(carId: number): boolean {
  for (const u of users) {
    const i = u.cars.findIndex((c) => c.id === carId)
    if (i !== -1) {
      u.cars.splice(i, 1)
      return true
    }
  }
  return false
}

export function plateTaken(plate: string, exceptCarId?: number): boolean {
  return users.some((u) => u.cars.some((c) => c.plate === plate && c.id !== exceptCarId))
}

export function emailTaken(email: string, exceptUserId?: number): boolean {
  return users.some((u) => u.email === email && u.id !== exceptUserId)
}

/**
 * Paginación por cursor sobre un array ya ordenado.
 * El cursor es el índice del siguiente elemento, codificado en base64 —
 * opaco para el cliente, igual que lo será el de la API real.
 */
export function paginate<T>(all: T[], limit: number, cursor: string | null) {
  const start = cursor ? Number(atob(cursor)) : 0
  const slice = all.slice(start, start + limit)
  const next = start + limit < all.length ? btoa(String(start + limit)) : null
  return { items: slice, next_cursor: next }
}
