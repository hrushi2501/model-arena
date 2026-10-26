import { NextResponse } from "next/server";

export async function GET() {
  const apiUrl = process.env.MODEL_ARENA_API_URL || "http://127.0.0.1:8080";

  try {
    const response = await fetch(new URL("/health/live", apiUrl), { cache: "no-store" });
    const body: unknown = await response.json();

    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
