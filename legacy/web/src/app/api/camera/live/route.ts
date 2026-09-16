// app/api/camera/live/route.ts
import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CAMERA_RPC = process.env.CAMERA_RPC ?? "http://192.168.122.1:10000/sony/camera";
const CAM_TIMEOUT_MS = Number(process.env.CAM_TIMEOUT_MS ?? 10000);

async function rpc(method: string) {
  const payload = { method, params: [], id: 1, version: "1.0" };
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), CAM_TIMEOUT_MS);
  try {
    const r = await fetch(CAMERA_RPC, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
      cache: "no-store",
    });
    if (!r.ok) throw new Error(`RPC ${method} -> ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

export async function GET(_req: NextRequest) {
  try {
    // 1) Intenta poner en modo grabación (ignora errores)
    try { await rpc("startRecMode"); } catch {}

    // 2) Pide liveview
    const resp = await rpc("startLiveview");
    const liveUrl: string = resp?.result?.[0];
    if (!liveUrl) {
      return new Response(JSON.stringify({ error: "No live_url" }), { status: 502 });
    }

    // 3) Abre el MJPEG y lo retransmite tal cual
    const camRes = await fetch(liveUrl, { cache: "no-store" });
    if (!camRes.ok || !camRes.body) {
      return new Response(JSON.stringify({ error: `Upstream ${camRes.status}` }), { status: 502 });
    }

    // Propaga el content-type original (incluye boundary)
    const contentType = camRes.headers.get("content-type") || "multipart/x-mixed-replace";

    const headers = new Headers();
    headers.set("Content-Type", contentType);
    headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
    headers.set("Pragma", "no-cache");
    headers.set("Expires", "0");
    headers.set("Connection", "keep-alive");
    // CORS opcional si lo necesitas desde otro origen:
    // headers.set("Access-Control-Allow-Origin", "*");

    return new Response(camRes.body, {
      status: 200,
      headers,
    });
  } catch (e: any) {
    return new Response(JSON.stringify({ error: String(e?.message ?? e) }), { status: 500 });
  }
}
