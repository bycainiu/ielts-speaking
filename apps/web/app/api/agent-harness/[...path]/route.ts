import { NextRequest, NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{
    path?: string[];
  }>;
};

const agentHarnessBaseUrl = (process.env.AGENT_HARNESS_URL || "http://localhost:8000").replace(/\/+$/, "");

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
    const responseBody = await response.text();
    const responseHeaders = new Headers();
    const responseContentType = response.headers.get("content-type");
    if (responseContentType) {
      responseHeaders.set("content-type", responseContentType);
    }
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
