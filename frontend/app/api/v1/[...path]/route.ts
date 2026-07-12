import { getDevResponse } from "@/lib/dev-data";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

async function proxyOrFallback(request: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const target = `${BACKEND_URL}/api/v1/${path}${request.nextUrl.search}`;

  try {
    const response = await fetch(target, { cache: "no-store" });
    if (response.ok) {
      const body = await response.arrayBuffer();
      return new NextResponse(body, {
        status: response.status,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "X-Locater-Source": "backend"
        }
      });
    }
  } catch {
    // Backend unavailable; fall back to local seed data for development.
  }

  const dev = getDevResponse(path, request.nextUrl.searchParams);
  if (dev !== null) {
    return NextResponse.json(dev, {
      headers: { "X-Locater-Source": "dev-fallback" }
    });
  }

  return NextResponse.json(
    {
      detail:
        "Backend unavailable. Start the API with docker compose up or run uvicorn locally on port 8000."
    },
    { status: 503 }
  );
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const { path } = await context.params;
  return proxyOrFallback(request, path);
}
