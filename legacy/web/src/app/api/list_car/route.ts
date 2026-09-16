// app/api/event/route.ts (App Router)
import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:5000"
type InBody = {
  name: string
  phone: string
  email: string
  role: string
  plate: string
}
export async function GET() {
  const r = await fetch(`${BACKEND}/list/getlist`, { cache: "no-store" })
  if (!r.ok) return NextResponse.json({ error: `Upstream ${r.status}` }, { status: 502 })
  const data = await r.json()
  return NextResponse.json(data)
}
export async function PUT(req: Request) {
    try {
        const { id, name, phone, email, role, plate } = await req.json()
        if (!id) {
            return NextResponse.json({ error: "Missing user id" }, { status: 400 })
        }
        const rUser = await fetch(`${BACKEND}/list/users/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, phone, email, role }),
            cache: "no-store",
        })
        if (!rUser.ok) {
            const text = await rUser.text()
            return NextResponse.json({ error: `Upstream users ${rUser.status}: ${text}` }, { status: 502 })
        }
        // 2️⃣ Actualizar carro/placa
        const rCar = await fetch(`${BACKEND}/list/cars/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plate, user_id: id }),
            cache: "no-store",
        })
        if (!rCar.ok) {
            const text = await rCar.text()
            return NextResponse.json({ error: `Upstream cars ${rCar.status}: ${text}` }, { status: 502 })
        }
        const updatedUser = await rUser.json()
        const updatedCar = await rCar.json()
        return NextResponse.json({ user: updatedUser, car: updatedCar })
    }
    catch (err: any) {
        return NextResponse.json({ error: err?.message ?? "Unexpected error" }, { status: 500 })
    }
}

export async function DELETE(req: Request) {
  try {
    const { id } = await req.json()  

    if (!id) {
      return NextResponse.json({ error: "Missing user id" }, { status: 400 })
    }

    // 1️⃣ Eliminar primero el carro (si tu backend lo requiere)
    await fetch(`${BACKEND}/list/cars/${id}`, {
      method: "DELETE",
      cache: "no-store",
    }).catch(() => null)

    // 2️⃣ Eliminar usuario
    const r = await fetch(`${BACKEND}/list/users/${id}`, {
      method: "DELETE",
      cache: "no-store",
    })

    if (!r.ok) {
      const text = await r.text()
      return NextResponse.json({ error: `Upstream ${r.status}: ${text}` }, { status: 502 })
    }

    return NextResponse.json({ message: "User deleted successfully" }, { status: 200 })
  } catch (err: any) {
    return NextResponse.json({ error: err?.message ?? "Unexpected error" }, { status: 500 })
  }
}

export async function POST(req: Request) {
  let createdUserId: number | null = null

  try {
    const body = (await req.json()) as InBody

    // 1) Crear usuario
    const rUser = await fetch(`${BACKEND}/list/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: body.name,
        phone: body.phone,
        email: body.email,
        role: body.role,
      }),
      cache: "no-store",
    })

    if (!rUser.ok) {
      const text = await rUser.text()
      return NextResponse.json({ error: `Upstream users ${rUser.status}: ${text}` }, { status: 502 })
    }

    const user = await rUser.json()
    createdUserId = user?.id

    if (!createdUserId) {
      return NextResponse.json({ error: "Backend did not return user id" }, { status: 502 })
    }

    // 2) Crear carro/placa
    const rCar = await fetch(`${BACKEND}/list/cars`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plate: body.plate,
        user_id: createdUserId,
      }),
      cache: "no-store",
    })

    if (!rCar.ok) {
      const text = await rCar.text()
      // (Opcional) rollback best-effort: borrar el usuario creado
      try {
        await fetch(`${BACKEND}/list/users/${createdUserId}`, { method: "DELETE" })
      } catch {}
      return NextResponse.json({ error: `Upstream cars ${rCar.status}: ${text}` }, { status: 502 })
    }

    const car = await rCar.json()

    return NextResponse.json({ user, car })
  } catch (err: any) {
    return NextResponse.json({ error: err?.message ?? "Unexpected error" }, { status: 500 })
  }
}

