import { NextRequest, NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{
    path?: string[];
  }>;
};

const agentHarnessBaseUrl = (process.env.AGENT_HARNESS_URL || "http://localhost:8000").replace(/\/+$/, "");
const apiBaseUrl = (
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:18080"
).replace(/\/+$/, "");

export async function GET(request: NextRequest, context: RouteContext) {
  return proxyAgentHarnessRequest(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxyAgentHarnessRequest(request, context);
}

async function proxyAgentHarnessRequest(request: NextRequest, context: RouteContext) {
  const authorization = request.headers.get("authorization");
  if (!authorization) {
    return NextResponse.json({ message: "Authentication required." }, { status: 401 });
  }

  const { path = [] } = await context.params;
  if (isSensitiveAgentPath(path)) {
    const allowed = await isAdminAuthorization(authorization);
    if (!allowed) {
      return NextResponse.json({ message: "当前账号没有权限查看 Agent Trace。" }, { status: 403 });
    }
  }

  const target = new URL(`${agentHarnessBaseUrl}/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  headers.set("x-forwarded-by", "ielts-speaking-web");

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  try {
    const response = await fetch(target, init);
    const responseHeaders = new Headers();
    const responseContentType = response.headers.get("content-type");
    if (responseContentType) {
      responseHeaders.set("content-type", responseContentType);
    }
    const cacheControl = response.headers.get("cache-control");
    if (cacheControl) {
      responseHeaders.set("cache-control", cacheControl);
    }
    const xAccelBuffering = response.headers.get("x-accel-buffering");
    if (xAccelBuffering) {
      responseHeaders.set("x-accel-buffering", xAccelBuffering);
    }
    if (responseContentType?.includes("text/event-stream")) {
      return new NextResponse(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    }
    const responseBody = await response.text();
    return new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      {
        message: "Agent Harness is unavailable.",
        target: target.origin,
      },
      { status: 502 },
    );
  }
}

function isSensitiveAgentPath(path: string[]) {
  const joined = path.join("/");
  return joined.startsWith("agent/observability") || joined.startsWith("agent/runs/") || joined.startsWith("agent/audit");
}

async function isAdminAuthorization(authorization: string) {
  try {
    const response = await fetch(`${apiBaseUrl}/api/me`, {
      headers: { authorization },
      cache: "no-store",
    });
    if (!response.ok) return false;
    const body = await response.json();
    const role = body?.user?.role;
    return role === "operator" || role === "admin";
  } catch {
    return false;
  }
}
