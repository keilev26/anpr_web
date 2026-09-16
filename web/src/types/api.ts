/**
 * Tipos derivados de `contracts/openapi.yaml`.
 *
 * Mientras F2 no exista, se mantienen a mano. En cuanto la API publique su
 * `openapi.json`, este archivo se GENERA con `openapi-typescript` y deja de
 * editarse: el contrato es la fuente de verdad, no este archivo.
 */

export type Role = "student" | "teacher" | "administrator"

export const ROLE_LABELS: Record<Role, string> = {
  student: "Estudiante",
  teacher: "Docente",
  administrator: "Administrativo",
}

export interface User {
  id: number
  name: string
  phone: string | null
  email: string
  role: Role
  is_active: boolean
  created_at?: string
}

export interface Car {
  id: number
  plate: string
  user_id: number
}

export interface UserWithCars extends User {
  cars: Car[]
}

export interface UserCreate {
  name: string
  phone?: string
  email: string
  role: Role
  plates?: string[]
}

export type UserUpdate = Partial<Omit<UserCreate, "plates">> & { is_active?: boolean }

export interface AnprEvent {
  id: number
  plate: string
  /** Siempre UTC. Se convierte a America/Lima solo al mostrar. */
  detected_at: string
  authorized: boolean
  confidence: number | null
  image_url: string | null
  gate_opened: boolean | null
  latency_ms: number | null
  camera_id: string | null
  /** Null si la placa no está en la lista blanca. */
  user: User | null
}

export interface Page<T> {
  items: T[]
  next_cursor?: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: "bearer"
  expires_in: number
  user: User
}

export interface ApiError {
  detail: string
  code?: string
}
