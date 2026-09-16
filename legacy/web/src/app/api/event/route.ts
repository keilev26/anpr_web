// app/api/event/route.ts (App Router)
import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:5000"

export async function GET() {
  const r = await fetch(`${BACKEND}/v1/event`, { cache: "no-store" })
  if (!r.ok) return NextResponse.json({ error: `Upstream ${r.status}` }, { status: 502 })
  const data = await r.json()
  return NextResponse.json(data)
}
